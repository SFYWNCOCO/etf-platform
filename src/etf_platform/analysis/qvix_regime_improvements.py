# -*- coding: utf-8 -*-
"""QVIX多源校验与异常检测模块 — 改进方案1

解决的核心问题：
1. 单数据源脆弱性 — akshare接口失效时系统完全失明
2. 无数据质量校验 — 异常值、跳变、过期数据不被检测
3. 降级策略不透明 — fallback硬编码值无告警

设计原则：
- 多源校验：主源(akshare) + 备源(东方财富/新浪) + 缓存
- 分级降级：live→cache→secondary→fallback_with_alert
- 异常检测：范围检查 + 跳变检测 + 多源一致性评分
"""
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_CACHE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "live_cache"
CACHE_FILE = _CACHE_DIR / "qvix_regime_v2.json"
CACHE_TTL = timedelta(hours=4)

# ── 阈值常量（可配置） ──────────────────────────────────────────────
REGIME_THRESHOLDS = {"complacent": 16, "normal": 22, "cautious": 28}

# ── 数据合理性边界 ──────────────────────────────────────────────────
QVIX_MIN = 5.0     # QVIX通常不低于5
QVIX_MAX = 150.0   # QVIX极端情况不超过150
MAX_SINGLE_JUMP = 15.0  # 单次跳变超过此值标记为异常
MAX_CONSENSUS_GAP = 8.0   # 多源QVIX差异超过此值标记为不一致


class QVIXDataQuality:
    """QVIX数据质量检查器。"""

    @staticmethod
    def check_range(value: float, name: str = "qvix") -> tuple[bool, str]:
        """检查数值是否在合理范围内。"""
        if value < QVIX_MIN:
            return False, f"{name}={value} 低于最小合理值{QVIX_MIN}"
        if value > QVIX_MAX:
            return False, f"{name}={value} 高于最大合理值{QVIX_MAX}"
        return True, "ok"

    @staticmethod
    def check_jump(current: float, previous: float, name: str = "qvix") -> tuple[bool, str]:
        """检查数值跳变是否过大。"""
        jump = abs(current - previous)
        if jump > MAX_SINGLE_JUMP:
            return False, f"{name}跳变{jump:.1f}超过阈值{MAX_SINGLE_JUMP} ({previous}→{current})"
        return True, "ok"

    @staticmethod
    def check_consensus(values: dict[str, float]) -> tuple[bool, str, float]:
        """检查多源QVIX值的一致性。

        Returns:
            (is_consistent, reason, max_gap)
        """
        if len(values) < 2:
            return True, "single_source", 0.0

        vals = list(values.values())
        max_gap = max(vals) - min(vals)
        if max_gap > MAX_CONSENSUS_GAP:
            return False, f"多源差异过大(max_gap={max_gap:.1f}): {values}", max_gap

        return True, f"consistent(gap={max_gap:.1f})", max_gap


class SecondaryDataSource:
    """备用QVIX数据源。

    实现两个备选数据获取路径：
    1. 新浪期权隐含波动率页面解析
    2. 从ETF价格历史计算已实现波动率作为代理
    """

    @staticmethod
    def fetch_sina_option_iv(code: str = "510050") -> Optional[float]:
        """从新浪财经获取ETF期权隐含波动率近似值。

        注意：这是简化实现，实际需根据新浪期权页面结构调整。
        返回近似QVIX值。
        """
        try:
            import urllib.request
            import json as _json

            # 新浪期权页面 — 50ETF期权
            prefix = "sh"
            url = f"http://stock.finance.sina.com.cn/option/api/openinterest.php?symbol={prefix}{code}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                raw = resp.read().decode("utf-8")
            data = _json.loads(raw)
            if data and isinstance(data, list):
                # 简化：用持仓量加权平均IV作为代理
                total_oi = sum(item.get("total_position", 0) for item in data)
                if total_oi > 0:
                    weighted_iv = sum(
                        item.get("avg_price", 0) * item.get("total_position", 0)
                        for item in data
                    ) / total_oi
                    return round(weighted_iv, 1)
        except Exception as e:
            logger.debug("[secondary] sina option fetch failed: %s", e)
        return None

    @staticmethod
    def compute_realized_vol_proxy(codes: list[str], days: int = 20) -> Optional[float]:
        """从ETF价格历史计算已实现波动率作为QVIX代理。

        使用Tencent/Sina kline数据计算过去N日的年化波动率。
        这是一个粗糙但可靠的替代指标。
        """
        try:
            from etf_platform.data.kline import _fetch_kline

            vols = []
            for code in codes[:3]:  # 只用前3只宽基ETF
                rows = _fetch_kline(code, days=days + 10)
                if not rows or len(rows) < days:
                    continue
                closes = [float(r["close"]) for r in rows[-(days + 1):]]
                returns = [(closes[i] / closes[i - 1] - 1) for i in range(1, len(closes))]
                if len(returns) < 5:
                    continue
                import statistics
                std = statistics.stdev(returns)
                annualized = std * (252 ** 0.5) * 100  # 转成百分比
                vols.append(annualized)

            if vols:
                # 已实现波动率通常比QVIX低10-20%（QVIX是前瞻的）
                avg_realized = sum(vols) / len(vols)
                # 粗略转换：realized_vol * 1.2 ≈ QVIX proxy
                return round(avg_realized * 1.2, 1)
        except Exception as e:
            logger.debug("[secondary] realized vol proxy failed: %s", e)
        return None


class QVIXValidator:
    """QVIX数据验证器 — 带历史记录和异常检测。"""

    def __init__(self, history_size: int = 50):
        self._history: list[dict] = []  # 最近N条记录
        self._history_size = history_size
        self.quality_checker = QVIXDataQuality()

    def validate(self, qvix_50: float, qvix_500: float) -> dict:
        """验证一对QVIX值。

        Returns:
            {
                "valid": bool,
                "checks": {"range_50": ok, "range_500": ok, "jump_50": ok, ...},
                "consensus_score": 0.0-1.0,
                "alerts": [...],
                "recommendation": "use|investigate|reject"
            }
        """
        checks = {}
        alerts = []

        # 1. 范围检查
        ok_50, msg_50 = self.quality_checker.check_range(qvix_50, "qvix_50")
        ok_500, msg_500 = self.quality_checker.check_range(qvix_500, "qvix_500")
        checks["range_50"] = ok_50
        checks["range_500"] = ok_500
        if not ok_50:
            alerts.append(f"QVIX_50范围异常: {msg_50}")
        if not ok_500:
            alerts.append(f"QVIX_500范围异常: {msg_500}")

        # 2. 跳变检查
        prev_50 = self._history[-1].get("qvix_50") if self._history else None
        prev_500 = self._history[-1].get("qvix_500") if self._history else None
        checks["jump_50"] = True
        checks["jump_500"] = True
        if prev_50 is not None:
            ok_j50, msg_j50 = self.quality_checker.check_jump(qvix_50, prev_50, "qvix_50")
            checks["jump_50"] = ok_j50
            if not ok_j50:
                alerts.append(f"QVIX_50跳变异常: {msg_j50}")
        if prev_500 is not None:
            ok_j500, msg_j500 = self.quality_checker.check_jump(qvix_500, prev_500, "qvix_500")
            checks["jump_500"] = ok_j500
            if not ok_j500:
                alerts.append(f"QVIX_500跳变异常: {msg_j500}")

        # 3. 50/500一致性
        values = {"50": qvix_50, "500": qvix_500}
        ok_cons, cons_msg, gap = self.quality_checker.check_consensus(values)
        checks["consistency_50_500"] = ok_cons
        consensus_score = max(0.0, 1.0 - gap / MAX_CONSENSUS_GAP)
        if not ok_cons:
            alerts.append(f"50/500不一致: {cons_msg}")

        # 4. 综合推荐
        bad_checks = sum(1 for v in checks.values() if v is False)
        if bad_checks >= 2:
            recommendation = "reject"
        elif bad_checks == 1:
            recommendation = "investigate"
        else:
            recommendation = "use"

        result = {
            "valid": recommendation != "reject",
            "checks": checks,
            "consensus_score": round(consensus_score, 2),
            "alerts": alerts,
            "recommendation": recommendation,
        }

        # 仅当通过范围检查时才加入历史
        if ok_50 and ok_500:
            self._history.append({
                "qvix_50": qvix_50,
                "qvix_500": qvix_500,
                "timestamp": datetime.now().isoformat(),
                "recommendation": recommendation,
            })
            if len(self._history) > self._history_size:
                self._history.pop(0)

        return result

    def get_alert_summary(self) -> dict:
        """获取最近历史的异常摘要。"""
        if not self._history:
            return {"total_checks": 0, "rejected_count": 0, "investigated_count": 0, "rejection_rate": 0.0}

        total = len(self._history)
        rejected = sum(1 for h in self._history if h.get("recommendation") == "reject")
        investigated = sum(1 for h in self._history if h.get("recommendation") == "investigate")

        return {
            "total_checks": total,
            "rejected_count": rejected,
            "investigated_count": investigated,
            "rejection_rate": round(rejected / total, 3) if total > 0 else 0,
        }


def classify_regime_with_quality(
    qvix_val: float, quality_result: Optional[dict] = None
) -> tuple[str, str, list[str]]:
    """带质量检查的regime分类。

    Returns:
        (regime, description, quality_alerts)
    """
    regime = "unknown"
    desc = "unknown"
    alerts = []

    if quality_result:
        if quality_result.get("recommendation") == "reject":
            alerts.append("QVIX数据被标记为不可信，使用保守fallback")
            return "normal", "data_quality_rejected", alerts

    # 标准分类
    if qvix_val < REGIME_THRESHOLDS["complacent"]:
        regime, desc = "complacent", f"低恐慌(QVIX={qvix_val:.1f})"
    elif qvix_val < REGIME_THRESHOLDS["normal"]:
        regime, desc = "normal", f"正常(QVIX={qvix_val:.1f})"
    elif qvix_val < REGIME_THRESHOLDS["cautious"]:
        regime, desc = "cautious", f"警惕(QVIX={qvix_val:.1f})"
    else:
        regime, desc = "fearful", f"恐慌(QVIX={qvix_val:.1f})"

    # 添加质量相关提示
    if quality_result and quality_result.get("consensus_score", 1.0) < 0.5:
        alerts.append(f"多源一致性低(consensus={quality_result['consensus_score']:.2f})")

    return regime, desc, alerts


if __name__ == "__main__":
    # 快速测试
    validator = QVIXValidator()

    # 测试1: 正常值
    r1 = validator.validate(18.5, 20.3)
    print(f"测试1 (正常): valid={r1['valid']}, rec={r1['recommendation']}, consensus={r1['consensus_score']}")

    # 测试2: 异常值
    r2 = validator.validate(200.0, 20.3)
    print(f"测试2 (超范围): valid={r2['valid']}, alerts={r2['alerts']}")

    # 测试3: 跳变
    r3 = validator.validate(18.0, 19.5)
    print(f"测试3 (跳变): valid={r3['valid']}, alerts={r3['alerts']}")

    # 测试4: 一致性
    r4 = validator.validate(30.0, 12.0)
    print(f"测试4 (不一致): valid={r4['valid']}, gap={r4['consensus_score']}")

    print(f"\n历史摘要: {validator.get_alert_summary()}")
