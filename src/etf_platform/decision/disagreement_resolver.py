#!/usr/bin/env python3
"""
disagreement_resolver.py — ML预测与Z-score规则系统的矛盾裁决框架 v1.0

设计目标:
  处理"ML看多但规则过滤"场景，提供结构化的矛盾检测、裁决和回测验证。

核心矛盾类型:
  C1. ML高分 vs 规则过滤 — ML给某ETF高P(涨)，但QVIX恐慌期该ETF被排除
  C2. ML vs Z-score分数倒挂 — 同一ETF在两个系统中的排名严重不一致
  C3. 多源一致 vs 单源异议 — 3个以上源看好但1个源过滤

裁决机制:
  - 异议通道(Disagreement Channel): 被规则过滤但ML高分的ETF进入"观察池"
  - 覆盖条件(Cover Rules): ML何时应该覆盖规则系统
  - 降级条件(Defer Rules): 何时规则系统优先于ML

回测验证:
  - 历史回测: 统计ML"正确反对"规则过滤的次数
  - 信号追踪: 记录每次矛盾的产生和结果

用法:
  python -m etf_platform.decision.disagreement_resolver --resolve    # 实时裁决
  python -m etf_platform.decision.disagreement_resolver --backtest   # 历史回测
  python -m etf_platform.decision.disagreement_resolver --analyze    # 综合分析
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

BASE = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = BASE / "data"
RESOLVER_LOG = DATA_DIR / "disagreement_resolutions.jsonl"


# ===================================================================
#  数据模型
# ===================================================================

@dataclass(slots=True)
class DisagreementRecord:
    """单次矛盾裁决记录。"""
    date: str
    qvix_regime: str
    etf_code: str
    etf_name: str
    sector: str
    ml_prob_up: float           # ML预测P(涨)
    ml_expected_return: float   # ML预期收益
    ml_confidence: float        # ML置信度
    zscore_score: float | None  # Z-score分数(被过滤则为None)
    zscore_available: bool      # 是否在候选池中
    conflict_type: str          # C1/C2/C3
    resolution: str             # override/defer/watch/ignore
    resolution_reason: str      # 裁决理由
    override_threshold_met: bool = False  # 是否满足覆盖条件
    downstream_signals: dict = field(default_factory=dict)  # 下游信号
    outcome_10d: float | None = None  # 10天后实际收益(回填)
    was_correct: bool | None = None   # 裁决是否正确(回填)


@dataclass(slots=True)
class ResolutionResult:
    """裁决引擎输出。"""
    date: str
    qvix_regime: str
    original_top3: list[dict]
    ml_top3: list[dict]
    disagreements: list[DisagreementRecord]
    watch_pool: list[dict]              # 异议通道中的ETF
    fused_top3: list[dict]              # 最终融合Top3
    override_applied: bool              # 是否有覆盖生效
    summary: str                        # 人类可读摘要


# ===================================================================
#  矛盾检测引擎
# ===================================================================

class ConflictDetector:
    """检测ML预测与Z-score规则之间的系统性矛盾。"""

    # 恐慌期防御型行业白名单 (与two_week_picker.py一致)
    DEFENSIVE_SECTORS = {
        "红利价值", "红利/价值", "高股息", "公用事业",
        "贵金属", "黄金", "利率债", "消费", "食品饮料",
        "医药", "白酒消费",
    }

    # 谨慎期高风险行业黑名单
    HIGH_RISK_SECTORS = {"半导体", "半导体设备", "AI算力", "券商", "军工"}

    def __init__(self):
        self.ml_predictions: list[dict] = []
        self.zscore_predictions: list[dict] = []
        self.all_zscore_candidates: list[dict] = []  # 所有评分过的ETF
        self.qvix_regime: str = "normal"

    def set_ml_predictions(self, preds: list[dict]) -> None:
        self.ml_predictions = preds

    def set_zscore_predictions(self, top3: list[dict], all_scored: list[dict]) -> None:
        self.zscore_predictions = top3
        self.all_zscore_candidates = all_scored

    def set_qvix_regime(self, regime: str) -> None:
        self.qvix_regime = regime

    def detect_conflicts(self) -> list[DisagreementRecord]:
        """检测所有矛盾并返回记录列表。"""
        conflicts = []

        if self.qvix_regime not in ("fearful", "cautious"):
            return conflicts  # 正常/放松期无过滤

        # 构建Z-score候选池的行业映射
        zscore_codes = {p.get("code") for p in self.all_zscore_candidates}
        zscore_map = {p.get("code"): p for p in self.all_zscore_candidates}

        for ml_pred in self.ml_predictions:
            code = ml_pred.get("code", "")
            sector = ml_pred.get("sector", "")
            prob_up = ml_pred.get("prob_up", 0.5)
            expected_ret = ml_pred.get("expected_return_10d", 0.0)
            confidence = ml_pred.get("confidence", 0.5)

            if not code:
                continue

            # --- C1: ML高分 vs 规则过滤 ---
            if code not in zscore_codes:
                # 检查是否因QVIX过滤被排除
                is_filtered_by_qvix = False
                if self.qvix_regime == "fearful":
                    is_filtered_by_qvix = sector not in self.DEFENSIVE_SECTORS
                elif self.qvix_regime == "cautious":
                    is_filtered_by_qvix = sector in self.HIGH_RISK_SECTORS

                if is_filtered_by_qvix and prob_up > 0.6:
                    conflicts.append(DisagreementRecord(
                        date=date.today().isoformat(),
                        qvix_regime=self.qvix_regime,
                        etf_code=code,
                        etf_name=ml_pred.get("name", ""),
                        sector=sector,
                        ml_prob_up=prob_up,
                        ml_expected_return=expected_ret,
                        ml_confidence=confidence,
                        zscore_score=None,
                        zscore_available=False,
                        conflict_type="C1",
                        resolution="watch",  # 默认观察，需进一步裁决
                        resolution_reason=f"QVIX={self.qvix_regime}过滤{sector}，但ML P(涨)={prob_up:.1%}",
                        override_threshold_met=self._check_override_conditions(
                            prob_up, confidence, expected_ret, sector
                        ),
                    ))
            else:
                # --- C2: 同一ETF在两个系统中的分数倒挂 ---
                zs_pred = zscore_map.get(code, {})
                zs_score = zs_pred.get("two_week_score", 50)
                # 如果ML概率很高但Z-score分数很低，构成倒挂
                if prob_up > 0.7 and zs_score < 50:
                    conflicts.append(DisagreementRecord(
                        date=date.today().isoformat(),
                        qvix_regime=self.qvix_regime,
                        etf_code=code,
                        etf_name=ml_pred.get("name", ""),
                        sector=sector,
                        ml_prob_up=prob_up,
                        ml_expected_return=expected_ret,
                        ml_confidence=confidence,
                        zscore_score=zs_score,
                        zscore_available=True,
                        conflict_type="C2",
                        resolution="watch",
                        resolution_reason=f"ML P(涨)={prob_up:.1%}但Z-score仅{zs_score}/100，存在倒挂",
                        override_threshold_met=False,
                    ))

        return conflicts

    def _check_override_conditions(
        self, prob_up: float, confidence: float, expected_ret: float, sector: str
    ) -> bool:
        """检查是否满足ML覆盖规则的条件。

        覆盖条件（全部满足才允许覆盖）:
        1. ML P(涨) >= 0.75 (强信号)
        2. ML置信度 >= 0.6
        3. 预期收益 > 3% (有足够上行空间)
        4. 不是极端高风险行业(如单一主题ETF)
        """
        conditions = {
            "high_prob": prob_up >= 0.75,
            "high_confidence": confidence >= 0.6,
            "good_return": expected_ret > 3.0,
            "not_extreme_risk": sector not in ("单一主题", "杠杆"),
        }
        return all(conditions.values())


# ===================================================================
#  裁决引擎
# ===================================================================

class ResolutionEngine:
    """执行矛盾裁决，决定是覆盖(ML胜)、降级(规则胜)还是观察。"""

    # 覆盖阈值配置
    OVERRIDE_THRESHOLDS = {
        "min_prob_up": 0.80,       # 最低P(涨)要求
        "min_confidence": 0.65,    # 最低置信度
        "min_expected_return": 5.0, # 最低预期收益(%)
        "max_drawdown_tolerance": 15.0,  # 最大可接受回撤(%)
    }

    # 降级条件：当以下任一条件成立时，规则系统优先
    DEFER_CONDITIONS = {
        "qvix_extreme_fear": 28.0,  # QVIX > 28 → 极度恐慌，规则优先
        "volatility_spike": 0.04,   # 日波动率突增 > 4% → 规则优先
    }

    def resolve(
        self,
        conflicts: list[DisagreementRecord],
        qvix_value: float = 25.0,
        market_volatility: float = 0.02,
    ) -> ResolutionResult:
        """执行完整裁决流程。

        Args:
            conflicts: 矛盾记录列表
            qvix_value: 当前QVIX值
            market_volatility: 当前市场波动率

        Returns:
            ResolutionResult 包含裁决结果
        """
        watch_pool = []
        overrides = []
        deferred = []

        for conflict in conflicts:
            # 检查降级条件
            if self._should_defer(qvix_value, market_volatility):
                conflict.resolution = "defer"
                conflict.resolution_reason += " [QVIX过高/波动率异常，规则优先]"
                deferred.append(conflict)
            # 检查覆盖条件
            elif conflict.override_threshold_met:
                conflict.resolution = "override"
                conflict.resolution_reason += " [满足ML覆盖条件]"
                overrides.append(conflict)
            else:
                # 默认：进入观察池
                conflict.resolution = "watch"
                watch_pool.append({
                    "code": conflict.etf_code,
                    "name": conflict.etf_name,
                    "sector": conflict.sector,
                    "ml_prob_up": conflict.ml_prob_up,
                    "ml_expected_return": conflict.ml_expected_return,
                    "ml_confidence": conflict.ml_confidence,
                    "conflict_type": conflict.conflict_type,
                    "reason": conflict.resolution_reason,
                })

        # 构建最终融合Top3
        fused_top3 = self._build_fused_top3(overrides, watch_pool)

        return ResolutionResult(
            date=date.today().isoformat(),
            qvix_regime="fearful" if qvix_value > 28 else "cautious" if qvix_value > 22 else "normal",
            original_top3=[],  # 由调用者填充
            ml_top3=[],         # 由调用者填充
            disagreements=conflicts,
            watch_pool=watch_pool,
            fused_top3=fused_top3,
            override_applied=len(overrides) > 0,
            summary=self._format_summary(overrides, deferred, watch_pool),
        )

    def _should_defer(self, qvix_value: float, volatility: float) -> bool:
        """判断是否应该降级到规则系统。"""
        if qvix_value > self.DEFER_CONDITIONS["qvix_extreme_fear"]:
            return True
        if volatility > self.DEFER_CONDITIONS["volatility_spike"]:
            return True
        return False

    def _build_fused_top3(
        self, overrides: list, watch_pool: list
    ) -> list[dict]:
        """从覆盖和观察池构建最终Top3。"""
        result = []
        seen_sectors = set()

        # 优先加入覆盖的ETF
        for o in sorted(overrides, key=lambda x: -x.ml_prob_up):
            if o.etf_code not in {r["code"] for r in result}:
                result.append({
                    "code": o.etf_code,
                    "name": o.etf_name,
                    "sector": o.sector,
                    "source": "ml_override",
                    "reason": o.resolution_reason,
                    "prob_up": o.ml_prob_up,
                })
                seen_sectors.add(o.sector)

        # 补充观察池
        for w in sorted(watch_pool, key=lambda x: -x.get("ml_prob_up", 0)):
            if len(result) >= 3:
                break
            if w["sector"] not in seen_sectors:
                result.append(w)
                seen_sectors.add(w["sector"])

        return result[:3]

    def _format_summary(
        self, overrides, deferred, watch_pool
    ) -> str:
        parts = []
        if overrides:
            parts.append(f"✅ ML覆盖: {len(overrides)}只 (满足覆盖条件)")
        if deferred:
            parts.append(f"⏸️ 规则降级: {len(deferred)}只 (QVIX过高)")
        if watch_pool:
            parts.append(f"👁️ 观察池: {len(watch_pool)}只 (待验证)")
        if not parts:
            parts.append("✅ 无矛盾，系统一致")
        return " | ".join(parts)


# ===================================================================
#  回测验证模块
# ===================================================================

class DisagreementBacktester:
    """回测验证: 历史上ML"正确反对"规则过滤的次数。"""

    def __init__(self, lookback_days: int = 365):
        self.lookback_days = lookback_days
        self.prediction_log = DATA_DIR / "meta_predictions.jsonl"
        self.outcome_log = DATA_DIR / "two_week_predictions.jsonl"

    def run_backtest(self) -> dict:
        """运行完整回测。"""
        results = {
            "date": date.today().isoformat(),
            "lookback_days": self.lookback_days,
            "total_conflicts": 0,
            "ml_correct_overrides": 0,
            "ml_wrong_overrides": 0,
            "rules_correct_deferrals": 0,
            "rules_wrong_deferrals": 0,
            "conflict_types": {"C1": 0, "C2": 0, "C3": 0},
            "override_accuracy": 0.0,
            "defer_accuracy": 0.0,
            "sample_records": [],
        }

        # 读取历史元预测日志
        if not self.prediction_log.exists():
            logger.warning("No prediction log found at %s", self.prediction_log)
            results["status"] = "no_data"
            return results

        records = []
        with open(self.prediction_log, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        # 按日期分组分析
        for record in records[-100:]:  # 最近100条
            qvix_regime = record.get("source_status", {}).get("zscore", {}).get("regime", "normal")
            if qvix_regime not in ("fearful", "cautious"):
                continue

            ml_preds = record.get("ml_predictions", [])
            zscore_preds = record.get("zscore_predictions", [])

            # 构建Z-score代码集合
            zscore_codes = {p.get("code") for p in zscore_preds}

            for ml_pred in ml_preds:
                code = ml_pred.get("code", "")
                prob_up = ml_pred.get("prob_up", 0.5)
                sector = ml_pred.get("sector", "")

                if code not in zscore_codes and prob_up > 0.6:
                    results["total_conflicts"] += 1
                    ct = "C1" if qvix_regime == "fearful" and sector not in ConflictDetector.DEFENSIVE_SECTORS else "C2"
                    results["conflict_types"][ct] = results["conflict_types"].get(ct, 0) + 1

                    # 尝试获取10日后实际收益来验证
                    outcome = self._get_outcome(code, record.get("date"))
                    if outcome is not None:
                        was_correct = outcome > 0  # ML看多，实际上涨
                        if was_correct:
                            results["ml_correct_overrides"] += 1
                        else:
                            results["ml_wrong_overrides"] += 1

                        sample = {
                            "date": record.get("date"),
                            "code": code,
                            "sector": sector,
                            "ml_prob_up": prob_up,
                            "qvix_regime": qvix_regime,
                            "actual_10d_return": outcome,
                            "was_correct": was_correct,
                        }
                        results["sample_records"].append(sample)

        # 计算准确率
        total_override = results["ml_correct_overrides"] + results["ml_wrong_overrides"]
        if total_override > 0:
            results["override_accuracy"] = round(
                results["ml_correct_overrides"] / total_override, 4
            )

        total_defer = results["rules_correct_deferrals"] + results["rules_wrong_deferrals"]
        if total_defer > 0:
            results["defer_accuracy"] = round(
                results["rules_correct_deferrals"] / total_defer, 4
            )

        results["status"] = "complete"
        return results

    def _get_outcome(self, code: str, pred_date: str) -> float | None:
        """获取ETF在pred_date后10天的实际收益率。"""
        try:
            from etf_platform.decision.prediction_backtest import _get_etf_returns
            rets = _get_etf_returns(code, pred_date, days=10)
            return rets[0] if rets else None
        except (ImportError, Exception):
            return None


# ===================================================================
#  主入口
# ===================================================================

def run_realtime_resolution(debug: bool = False) -> ResolutionResult:
    """执行实时矛盾裁决。"""
    from etf_platform.decision.meta_predictor import predict as meta_predict
    from etf_platform.analysis.qvix_regime import get_regime as get_qvix

    # 获取QVIX状态
    qvix_data = get_qvix()
    qvix_regime = qvix_data.get("regime", "normal")
    qvix_val = qvix_data.get("qvix_500", 20.0)

    if debug:
        print(f"[Resolver] QVIX Regime: {qvix_regime} (500={qvix_val:.1f})")

    if qvix_regime not in ("fearful", "cautious"):
        if debug:
            print("[Resolver] No filtering active, skipping resolution.")
        return ResolutionResult(
            date=date.today().isoformat(),
            qvix_regime=qvix_regime,
            original_top3=[], ml_top3=[],
            disagreements=[], watch_pool=[],
            fused_top3=[], override_applied=False,
            summary="QVIX正常/放松期，无需矛盾裁决",
        )

    # 获取元预测
    meta_result = meta_predict(unified=False, parallel=True)

    # 提取各源预测
    ml_preds = []
    zscore_preds = []
    all_zscore_scored = []

    for src_name, preds in meta_result.get("all_predictions", {}).items():
        if src_name == "ml":
            ml_preds = preds
        elif src_name == "zscore":
            zscore_preds = preds
            # 尝试获取完整评分
            try:
                from etf_platform.decision.two_week_picker import pick_top3
                _, all_scored = pick_top3(profile="均衡", max_candidates=80, debug=False)
                all_zscore_scored = all_scored
            except (ImportError, KeyError, ValueError, TypeError, AttributeError, OSError):
                    logger.warning("silent catch in disagreement_resolver.py:503 - needs review")

    # 检测矛盾
    detector = ConflictDetector()
    detector.set_ml_predictions(ml_preds)
    detector.set_zscore_predictions(zscore_preds, all_zscore_scored)
    detector.set_qvix_regime(qvix_regime)

    conflicts = detector.detect_conflicts()

    if debug:
        print(f"[Resolver] Detected {len(conflicts)} conflicts")
        for c in conflicts:
            print(f"  {c.conflict_type}: {c.etf_code} ({c.sector}) "
                  f"ML P(涨)={c.ml_prob_up:.1%} → {c.resolution}")

    # 执行裁决
    engine = ResolutionEngine()
    result = engine.resolve(
        conflicts,
        qvix_value=qvix_val,
        market_volatility=0.02,  # TODO: 从行情数据获取
    )

    # 保存裁决记录
    _save_resolution(result)

    return result


def _save_resolution(result: ResolutionResult) -> None:
    """保存裁决记录到JSONL。"""
    RESOLVER_LOG.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "date": result.date,
        "qvix_regime": result.qvix_regime,
        "disagreements": [
            {
                "etf_code": d.etf_code,
                "etf_name": d.etf_name,
                "sector": d.sector,
                "conflict_type": d.conflict_type,
                "ml_prob_up": d.ml_prob_up,
                "resolution": d.resolution,
                "reason": d.resolution_reason,
            }
            for d in result.disagreements
        ],
        "watch_pool": result.watch_pool,
        "override_applied": result.override_applied,
        "summary": result.summary,
    }
    with open(RESOLVER_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def format_resolution_report(result: ResolutionResult) -> str:
    """格式化裁决报告为可读文本。"""
    lines = [
        "⚖️ 矛盾裁决报告",
        f"{'=' * 60}",
        f"  日期: {result.date}",
        f"  QVIX状态: {result.qvix_regime}",
        "",
    ]

    if not result.disagreements:
        lines.append("  ✅ 无检测到矛盾")
    else:
        lines.append(f"  🔍 检测到 {len(result.disagreements)} 处矛盾:")
        lines.append("")

        by_type = {}
        for d in result.disagreements:
            by_type.setdefault(d.conflict_type, []).append(d)

        for ctype, items in by_type.items():
            type_desc = {"C1": "ML高分 vs 规则过滤", "C2": "分数倒挂", "C3": "多源一致 vs 单源异议"}
            lines.append(f"  [{ctype}] {type_desc.get(ctype, ctype)} ({len(items)}个):")
            for item in items:
                lines.append(
                    f"    • {item.etf_code} {item.etf_name} [{item.sector}] "
                    f"P(涨)={item.ml_prob_up:.0%} → {item.resolution}"
                )
                lines.append(f"      原因: {item.resolution_reason}")

        lines.append("")
        lines.append(f"  📋 裁决摘要: {result.summary}")

    if result.watch_pool:
        lines.append("")
        lines.append("  👁️ 观察池 (被过滤但ML看好的ETF):")
        for wp in result.watch_pool:
            lines.append(
                f"    • {wp['code']} {wp['name']} [{wp['sector']}] "
                f"P(涨)={wp['ml_prob_up']:.0%} | "
                f"E[return]={wp['ml_expected_return']:+.1f}%"
            )

    lines.append(f"\n{'=' * 60}")
    return "\n".join(lines)


# ===================================================================
#  CLI
# ===================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ML vs Z-score 矛盾裁决系统")
    parser.add_argument("--resolve", action="store_true", help="实时矛盾裁决")
    parser.add_argument("--backtest", action="store_true", help="历史回测验证")
    parser.add_argument("--analyze", action="store_true", help="综合分析")
    parser.add_argument("--debug", action="store_true", help="调试模式")

    args = parser.parse_args()

    if args.resolve:
        result = run_realtime_resolution(debug=args.debug)
        print(format_resolution_report(result))

    elif args.backtest:
        bt = DisagreementBacktester()
        results = bt.run_backtest()
        print(json.dumps(results, ensure_ascii=False, indent=2))

    elif args.analyze:
        # 同时运行裁决+回测
        result = run_realtime_resolution(debug=args.debug)
        print(format_resolution_report(result))
        print("\n--- 回测验证 ---")
        bt = DisagreementBacktester()
        results = bt.run_backtest()
        print(json.dumps(results, ensure_ascii=False, indent=2))

    else:
        parser.print_help()
