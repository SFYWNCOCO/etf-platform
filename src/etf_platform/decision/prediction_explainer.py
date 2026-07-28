#!/usr/bin/env python3
"""
prediction_explainer.py — 预测解释器 v1.0

把预测分数翻译成人类可读的因果解释。
每个预测来源都有自己的解释模板。

用法:
  python -m etf_platform.decision.prediction_explainer
  python -m etf_platform.decision.prediction_explainer --json
"""

import json
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

BASE = Path(__file__).resolve().parent.parent.parent.parent  # etf-platform/


@dataclass(slots=True)
class FactorExplanation:
    name: str
    value: float
    z_score: float
    interpretation: str
    contribution: str  # e.g., "+2.1分 (超跌深度贡献)"


@dataclass(slots=True)
class PredictionExplanation:
    code: str
    name: str
    sector: str
    score: float
    source: str  # "zscore" | "ml" | "tournament" | "events" | "meta"

    # Z-score specific
    factor_details: list[FactorExplanation] = field(default_factory=list)
    regime_context: str = ""

    # ML specific
    ml_probability: Optional[float] = None
    ml_expected_return: Optional[float] = None
    ml_top_features: list[str] = field(default_factory=list)

    # Event specific
    event_signals: list[str] = field(default_factory=list)

    # Risk
    risk_level: str = "medium"
    risk_factors: list[str] = field(default_factory=list)

    # Summary
    summary: str = ""
    confidence: str = "medium"


# ── Z-score factor explanations ─────────────────────────────────────

FACTOR_NAMES = {
    "trend_momentum": "趋势动量",
    "risk_adj_momentum": "风险调整动量",
    "quality_elastic": "质量弹性",
    "behavioral": "行为Alpha",
    "oversold_depth": "超跌深度",
    "drawdown_recov": "回撤修复",
    "vol_health": "量比健康度",
    "position_health": "位置健康度",
    "sector_flow": "行业资金流",
}

FACTOR_INTERPRETATIONS = {
    "trend_momentum": lambda z: (
        "强上升趋势" if z > 1.5 else
        "温和上升" if z > 0.5 else
        "横盘震荡" if z > -0.5 else
        "温和下跌" if z > -1.5 else
        "深度下跌"
    ),
    "risk_adj_momentum": lambda z: (
        "高性价比上涨" if z > 1.5 else
        "稳健上涨" if z > 0.5 else
        "风险收益均衡" if z > -0.5 else
        "波动拖累" if z > -1.5 else
        "高风险低回报"
    ),
    "quality_elastic": lambda z: (
        "极高弹性(低分=强催化剂潜力)" if z > 1.5 else
        "高弹性" if z > 0.5 else
        "中等弹性" if z > -0.5 else
        "低弹性(安全但无爆发力)" if z > -1.5 else
        "无弹性(高分=缺少催化剂)"
    ),
    "behavioral": lambda z: (
        "强行为Alpha(聪明钱流入)" if z > 1.5 else
        "正行为Alpha" if z > 0.5 else
        "中性" if z > -0.5 else
        "负行为Alpha" if z > -1.5 else
        "行为Alpha恶化"
    ),
    "oversold_depth": lambda z: (
        "深度超跌(历史级买入机会)" if z > 2 else
        "显著超跌" if z > 1 else
        "轻微超跌" if z > 0 else
        "未超跌" if z > -1 else
        "超买区间"
    ),
    "drawdown_recov": lambda z: (
        "大幅回撤后面临修复" if z > 1.5 else
        "中等回撤" if z > 0.5 else
        "正常波动" if z > -0.5 else
        "接近高点" if z > -1.5 else
        "新高附近(追高风险)"
    ),
    "vol_health": lambda z: (
        "放量突破" if z > 1.5 else
        "温和放量" if z > 0.5 else
        "正常量能" if z > -0.5 else
        "缩量整理" if z > -1.5 else
        "严重缩量"
    ),
    "position_health": lambda z: (
        "极低位(巨大上涨空间)" if z > 1.5 else
        "低位" if z > 0.5 else
        "中位" if z > -0.5 else
        "高位" if z > -1.5 else
        "极高位(回调风险大)"
    ),
    "sector_flow": lambda z: (
        "强资金流入" if z > 1.5 else
        "温和流入" if z > 0.5 else
        "资金平衡" if z > -0.5 else
        "温和流出" if z > -1.5 else
        "强资金流出"
    ),
}


def _explain_zscore_factor(key: str, z_score: float) -> FactorExplanation:
    """Generate human-readable explanation for a single Z-score factor."""
    name = FACTOR_NAMES.get(key, key)
    interp_fn = FACTOR_INTERPRETATIONS.get(key, lambda z: "数据不足")
    interpretation = interp_fn(z_score)

    # Contribution to overall score
    if abs(z_score) < 0.3:
        contribution = f"贡献微弱 (z={z_score:+.1f})"
    elif z_score > 0:
        contribution = f"+{abs(z_score)*5:.0f}分 (z={z_score:+.1f}, 正面贡献)"
    else:
        contribution = f"{z_score*5:.0f}分 (z={z_score:+.1f}, 负面拖累)"

    return FactorExplanation(
        name=name,
        value=round(z_score, 2),
        z_score=round(z_score, 2),
        interpretation=interpretation,
        contribution=contribution,
    )


def _explain_regime(regime: str) -> str:
    """Explain what the current market regime means for predictions."""
    contexts = {
        "fearful": "恐慌期: 系统强制过滤高风险板块(半导体/券商/军工), 仅保留防御型ETF(红利/消费/医药/黄金)。当前预测偏向防御。",
        "cautious": "谨慎期: 排除极高波动品种, 风险偏好降低。",
        "normal": "正常期: 全市场候选, 标准权重。",
        "complacent": "贪婪期: 可覆盖高风险高弹性品种, 进攻型配置。",
    }
    return contexts.get(regime, "未知状态")


def _explain_risk(score: float, volatility: float, change_20d: float) -> tuple[str, list[str]]:
    """Assess risk level and risk factors."""
    factors = []

    if volatility > 60:
        level = "high"
        factors.append(f"高波动率({volatility:.0f}%)")
    elif volatility > 35:
        level = "medium"
        factors.append(f"中等波动({volatility:.0f}%)")
    else:
        level = "low"
        factors.append(f"低波动({volatility:.0f}%)")

    if change_20d < -15:
        factors.append("20日暴跌(超跌反弹逻辑)")
    elif change_20d > 15:
        factors.append("20日暴涨(追高风险)")
    else:
        factors.append(f"20日变动{change_20d:+.1f}%(正常范围)")

    if score > 80:
        factors.append("高评分=高置信度但可能拥挤")
    elif score < 30:
        factors.append("低评分=催化剂不足")

    return level, factors


def explain_prediction(pred: dict, source: str = "zscore") -> PredictionExplanation:
    """Generate full explanation for a single prediction.

    Args:
        pred: Prediction dict with code, name, sector, score, and source-specific fields
        source: "zscore" | "ml" | "tournament" | "events"
    """
    code = pred.get("code", "")
    name = pred.get("name", "")
    sector = pred.get("sector", "未知")
    score = pred.get("score", pred.get("two_week_score", 50))

    exp = PredictionExplanation(
        code=code,
        name=name,
        sector=sector,
        score=round(float(score), 1),
        source=source,
    )

    # ── Z-score specific ─────────────────────────────────────────────
    z_factors = pred.get("z_factors", pred.get("z_scores", {}))
    if z_factors:
        for key in ["oversold_depth", "drawdown_recov", "quality_elastic",
                     "vol_health", "position_health", "trend_momentum",
                     "risk_adj_momentum", "behavioral", "sector_flow"]:
            if key in z_factors:
                exp.factor_details.append(_explain_zscore_factor(key, z_factors[key]))

        # Top 3 contributing factors
        top_factors = sorted(exp.factor_details, key=lambda f: abs(f.z_score), reverse=True)[:3]
        factor_summary = " · ".join(
            f"{f.name}({f.interpretation})" for f in top_factors
        )

        # Determine primary driver
        if any("超跌" in f.interpretation for f in top_factors):
            driver = "超跌反弹驱动"
        elif any("动量" in f.name and "正" in f.interpretation for f in top_factors):
            driver = "趋势动量驱动"
        elif any("弹性" in f.name and "高弹" in f.interpretation for f in top_factors):
            driver = "催化剂弹性驱动"
        elif any("资金流" in f.name for f in top_factors):
            driver = "资金面驱动"
        else:
            driver = "多因子均衡驱动"

        volatility = pred.get("volatility", 35)
        change_20d = pred.get("change_20d", 0)
        risk_level, risk_factors = _explain_risk(score, volatility, change_20d)
        exp.risk_level = risk_level
        exp.risk_factors = risk_factors

        exp.summary = (
            f"{driver} · 关键因子: {factor_summary} · "
            f"风险: {risk_level} · "
            f"20日变动{change_20d:+.1f}% · 波动率{volatility:.0f}%"
        )

        # Get regime context
        try:
            from etf_platform.analysis.qvix_regime import get_regime
            rd = get_regime()
            regime = rd.get("regime", "normal")
            exp.regime_context = _explain_regime(regime)
        except (ImportError, KeyError, ValueError, TypeError, AttributeError, OSError):
            exp.regime_context = "无法获取市场状态"

    # ── ML specific ──────────────────────────────────────────────────
    prob_up = pred.get("prob_up")
    if prob_up is not None:
        exp.ml_probability = round(float(prob_up), 3)
    exp_return = pred.get("expected_return_10d")
    if exp_return is not None:
        exp.ml_expected_return = round(float(exp_return), 2)

    # ── Event specific ──────────────────────────────────────────────
    event_count = pred.get("event_count", 0)
    if event_count > 0:
        direction = pred.get("direction", "NEUTRAL")
        exp.event_signals.append(f"{direction}信号: {event_count}个事件触发")

    # ── Confidence ──────────────────────────────────────────────────
    if score > 75:
        exp.confidence = "high"
    elif score > 55:
        exp.confidence = "medium"
    else:
        exp.confidence = "low"

    return exp


def explain_top3(predictions: list[dict], source: str = "meta") -> list[PredictionExplanation]:
    """Generate explanations for Top 3 predictions."""
    return [explain_prediction(p, source) for p in predictions[:3]]


def format_explanation_report(explanations: list[PredictionExplanation]) -> str:
    """Format explanations as readable report."""
    lines = [
        "🔍 预测解读报告",
        f"{'=' * 65}",
        f"  日期: {date.today().isoformat()}",
        "",
    ]

    for i, exp in enumerate(explanations, 1):
        risk_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(exp.risk_level, "⚪")
        conf_icon = {"high": "●●●", "medium": "●●○", "low": "●○○"}.get(exp.confidence, "○○○")

        lines.extend([
            f"  {'─' * 60}",
            f"  {i}. {risk_icon} {exp.code} {exp.name} [{exp.sector}]",
            f"     综合评分: {exp.score:.0f}/100  |  置信度: {conf_icon}",
            f"     来源: {exp.source}",
            "",
            f"     📝 {exp.summary}",
            "",
        ])

        # Factor breakdown
        if exp.factor_details:
            lines.append("     因子分解:")
            for f in exp.factor_details:
                if abs(f.z_score) > 0.3:  # Only show meaningful factors
                    arrow = "▲" if f.z_score > 0 else "▼"
                    lines.append(
                        f"       {arrow} {f.name:<12s} z={f.z_score:+.1f}  {f.interpretation}  [{f.contribution}]"
                    )

        # ML details
        if exp.ml_probability is not None:
            direction = "📈涨" if exp.ml_probability > 0.5 else "📉跌"
            lines.append("")
            lines.append(f"     🤖 ML模型: {direction}概率{exp.ml_probability:.0%}")
            if exp.ml_expected_return is not None:
                lines.append(f"        预期10日收益: {exp.ml_expected_return:+.2f}%")

        # Event signals
        if exp.event_signals:
            lines.append("")
            lines.append("     📰 事件信号:")
            for sig in exp.event_signals:
                lines.append(f"         {sig}")

        # Risk
        if exp.risk_factors:
            lines.append("")
            lines.append(f"     ⚠️ 风险因素: {', '.join(exp.risk_factors)}")

        lines.append("")

    # Regime context
    if explanations and explanations[0].regime_context:
        lines.append("  🌍 市场环境:")
        lines.append(f"     {explanations[0].regime_context}")

    lines.append("")
    lines.append(f"{'=' * 65}")
    lines.append("预测解释器 v1.0 · 不构成投资建议")

    return "\n".join(lines)


if __name__ == "__main__":
    json_mode = "--json" in sys.argv

    # Get current predictions from Z-score
    try:
        from etf_platform.decision.two_week_picker import pick_top3
        top3, _ = pick_top3(profile="均衡", max_candidates=30, debug=False)
    except (ImportError, KeyError, ValueError, TypeError, AttributeError, OSError) as e:
        print(f"无法获取预测: {e}", file=sys.stderr)
        sys.exit(1)

    explanations = explain_top3(top3, source="zscore")

    if json_mode:
        import dataclasses
        output = [dataclasses.asdict(e) for e in explanations]
        print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_explanation_report(explanations))
