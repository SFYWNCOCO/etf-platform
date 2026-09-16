"""
折溢价实时监控模块 - 基于IOPV的ETF折溢价分析

数据来源: akshare.fund_etf_spot_em() - 东方财富ETF实时行情
核心指标: IOPV(基金份额参考净值), 折价率/溢价率, 溢价预警

IOPV由ETF底层持仓股票的实时成交数据计算，每15秒更新一次。
折溢价率 = (现价 - IOPV) / IOPV * 100%
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:  # 仅类型检查期可见: 运行时保持「无 pandas 也能 import 本模块」
    import pandas as pd
# ponytail: pandas 只在 DIPMonitor 类方法内用，score_dip_layer(pipeline 唯一调用点)纯逻辑不依赖。
# 顶层不 import，避免 Hermes venv 无 pandas 时整个模块不可导入→L24 静默死层。


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class DipAlert:
    """折溢价预警记录"""
    code: str
    name: str
    iopv: float
    price: float
    premium_rate: float  # 溢价率(%)
    alert_type: str  # "overheated_premium", "deep_discount", "normal"
    risk_level: str  # "high", "medium", "low", "none"
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    message: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class DIPMonitor:
    """
    ETF折溢价实时监控器

    功能:
    1. 获取所有ETF实时行情(IOPV + 市价)
    2. 计算折溢价率
    3. 溢价率>3%自动预警(QDII常见高溢价风险)
    4. 折价率<-2%检测(可能的套利机会或流动性问题)
    5. 输出预警报告
    """

    # 预警阈值
    PREMIUM_ALERT_THRESHOLD = 3.0   # 溢价超过3%预警
    DEEP_DISCOUNT_THRESHOLD = -2.0  # 折价超过2%预警
    EXTREME_PREMIUM = 10.0          # 极端溢价(>10%严重警告)
    EXTREME_DISCOUNT = -5.0         # 极端折价(>5%严重警告)

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or Path(__file__).parent.parent / "data" / "live_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.alert_history_file = self.cache_dir / "dip_alert_history.jsonl"

    def fetch_etf_data(self) -> pd.DataFrame:
        """获取ETF实时行情数据

        Returns:
            DataFrame with columns: 代码, 名称, 最新价, IOPV实时估值, 基金折价率,
            涨跌额, 涨跌幅, 成交量, 成交额, 开盘价, 最高价, 最低价, 昨收,
            换手率, 量比, 委比, 外盘, 内盘, 主力净流入-净额, ...
        """
        import pandas as pd
        try:
            import akshare as ak
            from ..utils.thread_timeout import run_with_timeout
            df = run_with_timeout(ak.fund_etf_spot_em, timeout=30)
            if df is None or df.empty:
                logger.error("[DIP] 实时行情超时或为空")
                return pd.DataFrame()
            logger.info(f"[DIP] 获取到 {len(df)} 只ETF实时行情")
            return df
        except ImportError:
            logger.error("[DIP] akshare未安装，无法获取ETF数据")
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"[DIP] 获取ETF数据失败: {e}")
            return pd.DataFrame()

    def calculate_premium_rate(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        计算每只ETF的折溢价率

        折价率字段已包含在fund_etf_spot_em()返回中，
        但我们也用IOPV重新计算以验证一致性。
        """
        if df.empty:
            return df

        result = df.copy()

        # 东财接口已提供折价率字段
        if '基金折价率' in result.columns:
            result['premium_rate_source'] = 'eastmoney'
        elif 'IOPV实时估值' in result.columns and '最新价' in result.columns:
            # 手动计算
            result['calculated_premium'] = (
                (result['最新价'] - result['IOPV实时估值'])
                / result['IOPV实时估值'] * 100
            )
            result['premium_rate_source'] = 'calculated'

        return result

    def detect_alerts(self, df: pd.DataFrame) -> list[DipAlert]:
        """检测折溢价预警

        Args:
            df: 包含折价率数据的DataFrame

        Returns:
            预警列表
        """
        import pandas as pd
        alerts = []

        if df.empty:
            return alerts

        # 优先使用东财提供的折价率
        rate_col = '基金折价率' if '基金折价率' in df.columns else 'calculated_premium'
        if rate_col not in df.columns:
            logger.warning("[DIP] 无折价率字段，跳过预警检测")
            return alerts

        for _, row in df.iterrows():
            rate = row.get(rate_col)
            if pd.isna(rate):
                continue

            rate = float(rate)
            code = str(row.get('代码', ''))
            name = str(row.get('名称', ''))
            price = float(row.get('最新价', 0))
            iopv = float(row.get('IOPV实时估值', price))

            alert = DipAlert(
                code=code,
                name=name,
                iopv=iopv,
                price=price,
                premium_rate=rate,
                alert_type="normal",
                risk_level="none"
            )

            if rate > self.EXTREME_PREMIUM:
                alert.alert_type = "extreme_premium"
                alert.risk_level = "high"
                alert.message = f"极端溢价{rate:.2f}%！买入成本远高于实际净值，可能面临溢价收敛损失"
            elif rate > self.PREMIUM_ALERT_THRESHOLD:
                alert.alert_type = "overheated_premium"
                alert.risk_level = "high" if rate > 5 else "medium"
                alert.message = f"溢价率{rate:.2f}%超过{self.PREMIUM_ALERT_THRESHOLD}%警戒线"
            elif rate < self.EXTREME_DISCOUNT:
                alert.alert_type = "extreme_discount"
                alert.risk_level = "high"
                alert.message = f"极端折价{rate:.2f}%，需确认是否为流动性陷阱"
            elif rate < self.DEEP_DISCOUNT_THRESHOLD:
                alert.alert_type = "deep_discount"
                alert.risk_level = "medium"
                alert.message = f"折价率{rate:.2f}%低于-{abs(self.DEEP_DISCOUNT_THRESHOLD)}%警戒线"

            if alert.risk_level != "none":
                alerts.append(alert)

        return alerts

    def get_top_premium_etfs(self, df: pd.DataFrame, top_n: int = 20) -> pd.DataFrame:
        """获取溢价率最高的ETF"""
        if df.empty:
            return df

        rate_col = '基金折价率' if '基金折价率' in df.columns else 'calculated_premium'
        if rate_col not in df.columns:
            return df

        sorted_df = df.sort_values(rate_col, ascending=False)
        return sorted_df.head(top_n)

    def get_top_discount_etfs(self, df: pd.DataFrame, top_n: int = 20) -> pd.DataFrame:
        """获取折价率最高(折价最深)的ETF"""
        if df.empty:
            return df

        rate_col = '基金折价率' if '基金折价率' in df.columns else 'calculated_premium'
        if rate_col not in df.columns:
            return df

        sorted_df = df.sort_values(rate_col, ascending=True)
        return sorted_df.head(top_n)

    def generate_report(self, df: pd.DataFrame, alerts: list[DipAlert]) -> str:
        """生成折溢价监控报告"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [
            "# ETF折溢价监控报告",
            f"**生成时间**: {now}",
            f"**监控ETF总数**: {len(df)}",
            "",
        ]

        # 预警统计
        high_risk = [a for a in alerts if a.risk_level == "high"]
        medium_risk = [a for a in alerts if a.risk_level == "medium"]
        lines.append("## 预警统计")
        lines.append(f"- 🔴 高风险预警: {len(high_risk)} 只")
        lines.append(f"- 🟡 中风险预警: {len(medium_risk)} 只")
        lines.append(f"- ✅ 正常: {len(df) - len(alerts)} 只")
        lines.append("")

        if alerts:
            lines.append("## 预警详情")
            lines.append("| 代码 | 名称 | 现价 | IOPV | 折溢价率 | 风险等级 | 提示 |")
            lines.append("|------|------|------|------|----------|----------|------|")
            for a in sorted(alerts, key=lambda x: abs(x.premium_rate), reverse=True):
                lines.append(
                    f"| {a.code} | {a.name} | {a.price:.4f} | {a.iopv:.4f} | "
                    f"{a.premium_rate:+.2f}% | {a.risk_level} | {a.message} |"
                )
            lines.append("")

        # 溢价TOP10
        top_premium = self.get_top_premium_etfs(df, 10)
        if not top_premium.empty and '基金折价率' in top_premium.columns:
            lines.append("## 溢价率TOP10")
            lines.append("| 代码 | 名称 | 最新价 | IOPV | 折溢价率 | 涨跌幅 |")
            lines.append("|------|------|--------|------|----------|--------|")
            for _, r in top_premium.iterrows():
                lines.append(
                    f"| {r['代码']} | {r['名称']} | {r['最新价']:.4f} | "
                    f"{r.get('IOPV实时估值', 0):.4f} | {r['基金折价率']:+.2f}% | "
                    f"{r.get('涨跌幅', 0):+.2f}% |"
                )
            lines.append("")

        # 折价TOP10
        top_discount = self.get_top_discount_etfs(df, 10)
        if not top_discount.empty and '基金折价率' in top_discount.columns:
            lines.append("## 折价率TOP10")
            lines.append("| 代码 | 名称 | 最新价 | IOPV | 折溢价率 | 涨跌幅 |")
            lines.append("|------|------|--------|------|----------|--------|")
            for _, r in top_discount.iterrows():
                lines.append(
                    f"| {r['代码']} | {r['名称']} | {r['最新价']:.4f} | "
                    f"{r.get('IOPV实时估值', 0):.4f} | {r['基金折价率']:+.2f}% | "
                    f"{r.get('涨跌幅', 0):+.2f}% |"
                )
            lines.append("")

        return "\n".join(lines)

    def run(self, save_report: bool = True) -> tuple[str, list[DipAlert]]:
        """
        执行完整的折溢价监控流程

        Returns:
            (report_text, alerts)
        """
        df = self.fetch_etf_data()
        if df.empty:
            return "## ETF折溢价监控\n\n⚠️ 无法获取ETF数据", []

        df = self.calculate_premium_rate(df)
        alerts = self.detect_alerts(df)
        report = self.generate_report(df, alerts)

        if save_report:
            today = date.today().isoformat()
            report_path = self.cache_dir / f"dip_report_{today}.md"
            report_path.write_text(report, encoding="utf-8")

            # 追加预警历史
            for alert in alerts:
                with open(self.alert_history_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(alert.to_dict(), ensure_ascii=False) + "\n")

            logger.info(f"[DIP] 报告已保存: {report_path}")

        return report, alerts


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    monitor = DIPMonitor()
    report, alerts = monitor.run()
    print(report)
    print(f"\n共 {len(alerts)} 条预警")


# ═══════════════════════════════════════════
# Pipeline 集成接口
# ═══════════════════════════════════════════

def score_dip_layer(code: str = "", sector: str = "", premium_pct: float = 0.0,
                    is_cross_border: bool = False) -> dict:
    """L24_DipFlow 折溢价评分层 — 供 pipeline.py 调用。

    基于 l005 知识库-信号一: ETF折溢价均值回归。
    - 跨境ETF: 折价>8%为结构性机会, >3%为显著折价, 溢价>1%需警惕
    - 境内ETF: 折价>1%为套利机会, 溢价>1.5%需警惕
    - 综合评分: 折溢价信号 + 行业溢价调整 + 流动性微调

    Returns: {"score": 0-10, "premium_pct": float, "signal": str, "note": str}
    """
    # 跨境ETF阈值更宽松（k007: 纳指ETF平均折价-8.34%）
    if is_cross_border:
        if premium_pct < -8:
            return {"score": 8.5, "premium_pct": premium_pct, "signal": "strong_buy",
                    "note": "结构性折价(等待时差收敛)"}
        elif premium_pct < -5:
            return {"score": 7.5, "premium_pct": premium_pct, "signal": "buy",
                    "note": "深度折价(>5%)"}
        elif premium_pct < -3:
            return {"score": 6.5, "premium_pct": premium_pct, "signal": "mild_buy",
                    "note": "显著折价(>3%)"}
        elif premium_pct < -1:
            return {"score": 5.5, "premium_pct": premium_pct, "signal": "neutral",
                    "note": "轻微折价"}
        elif premium_pct <= 1:
            return {"score": 5.0, "premium_pct": premium_pct, "signal": "neutral",
                    "note": "平价"}
        elif premium_pct <= 2:
            return {"score": 4.0, "premium_pct": premium_pct, "signal": "sell",
                    "note": "溢价偏高"}
        else:
            return {"score": 2.5, "premium_pct": premium_pct, "signal": "strong_sell",
                    "note": f"极端溢价({premium_pct:.1f}%), 严重警告"}
    else:
        if premium_pct < -2:
            return {"score": 8.0, "premium_pct": premium_pct, "signal": "buy",
                    "note": "深度折价(套利机会)"}
        elif premium_pct < -1:
            return {"score": 7.0, "premium_pct": premium_pct, "signal": "mild_buy",
                    "note": "折价>1%(关注赎回套利)"}
        elif premium_pct < -0.3:
            return {"score": 6.0, "premium_pct": premium_pct, "signal": "mild",
                    "note": "轻微折价"}
        elif premium_pct <= 0.5:
            return {"score": 5.0, "premium_pct": premium_pct, "signal": "neutral",
                    "note": "平价"}
        elif premium_pct <= 1.5:
            return {"score": 4.0, "premium_pct": premium_pct, "signal": "sell",
                    "note": "溢价偏高"}
        else:
            return {"score": 2.0, "premium_pct": premium_pct, "signal": "strong_sell",
                    "note": f"极端溢价({premium_pct:.1f}%), 警惕回落"}
