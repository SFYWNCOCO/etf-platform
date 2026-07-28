"""risk_gate.py — 评分时风控门禁（TradingAgents 启发：独立风控Agent）

在评分链出口、最终推荐前运行。与传统 risk_manager.py（事后追踪PnL）不同，
risk_gate 在**评分时**就阻止高风险ETF进入推荐池。

与 TradingAgents 映射：
  Risk Manager Agent → risk_gate()  → 通过：允许进入推荐池
                                    → 拒绝：标记 blocked 原因

用法：
  from .decision.risk_gate import risk_gate
  gate_result = risk_gate(scores, profile="均衡", risk_level=0.5)
"""

import logging
from typing import Dict, List

logger = logging.getLogger(__name__)

# ── 各profile的风险容忍阈值 ──────────────────────────────

PROFILE_RISK_LIMITS = {
    "保守": {
        "max_risk_level": 0.30,         # 最高允许风险等级
        "min_composite": 4.0,           # 最低综合分
        "min_l18_var": 3.0,             # VaR评分下限
        "min_l14_stoic": 3.0,           # Stoic风险评分下限
        "max_l11_sector_risk": 7.0,     # 行业风险上限
        "max_l23_valuation": 8.5,       # 估值过热上限
        "min_demand": 4.0,              # 最低需求评分
    },
    "均衡": {
        "max_risk_level": 0.50,
        "min_composite": 3.5,
        "min_l18_var": 2.5,
        "min_l14_stoic": 2.5,
        "max_l11_sector_risk": 8.0,
        "max_l23_valuation": 9.0,
        "min_demand": 3.5,
    },
    "进取": {
        "max_risk_level": 0.70,
        "min_composite": 3.0,
        "min_l18_var": 2.0,
        "min_l14_stoic": 2.0,
        "max_l11_sector_risk": 8.5,
        "max_l23_valuation": 9.5,
        "min_demand": 3.0,
    },
    "激进": {
        "max_risk_level": 0.90,
        "min_composite": 2.5,
        "min_l18_var": 1.5,
        "min_l14_stoic": 1.5,
        "max_l11_sector_risk": 9.5,
        "max_l23_valuation": 10.0,
        "min_demand": 2.5,
    },
}

# Profile 别名映射
PROFILE_ALIASES = {
    "conservative": "保守", "defensive": "保守", "保守型": "保守",
    "balanced": "均衡", "neutral": "均衡", "均衡型": "均衡", "中性": "均衡",
    "aggressive": "进取", "进攻": "进取", "进取型": "进取",
    "激进型": "激进", "ultra_aggressive": "激进",
}


def _resolve_profile(profile: str) -> str:
    """解析profile别名为标准名称。"""
    return PROFILE_ALIASES.get(profile.lower(), profile)


def risk_gate(
    scores: Dict[str, float],
    risk_level: float = 0.5,
    profile: str = "均衡",
    etf_code: str = "",
    etf_name: str = "",
) -> Dict:
    """评分时风控门禁。

    Args:
        scores: 各层评分字典
        risk_level: ETF风险等级 (0-1)
        profile: 投资者画像
        etf_code: ETF代码（仅日志用）
        etf_name: ETF名称（仅日志用）

    Returns:
        {
            "passed": True/False,
            "blocked_reasons": [...],  # 未通过的原因列表
            "warnings": [...],         # 通过但有警告
            "adjusted_scores": {...}   # 调整后的评分（如有降级）
        }
    """
    pk = _resolve_profile(profile)
    limits = PROFILE_RISK_LIMITS.get(pk, PROFILE_RISK_LIMITS["均衡"])

    blocked_reasons: List[str] = []
    warnings: List[str] = []
    adjusted = dict(scores)

    # 1. 风险等级检查
    if risk_level > limits["max_risk_level"]:
        blocked_reasons.append(
            f"风险等级 {risk_level:.2f} > profile上限 {limits['max_risk_level']:.2f}"
        )

    # 2. 综合分检查
    composite = scores.get("composite_score", scores.get("score", 5.0))
    if composite < limits["min_composite"]:
        blocked_reasons.append(
            f"综合评分 {composite:.1f} < profile下限 {limits['min_composite']:.1f}"
        )

    # 3. VaR风险
    l18 = scores.get("L18_VaR", 5.0)
    if l18 < limits["min_l18_var"]:
        blocked_reasons.append(
            f"VaR评分 {l18:.1f} < 下限 {limits['min_l18_var']:.1f}（尾部风险过高）"
        )

    # 4. Stoic风险
    l14 = scores.get("L14_StoicRisk", 5.0)
    if l14 < limits["min_l14_stoic"]:
        blocked_reasons.append(
            f"Stoic风险 {l14:.1f} < 下限 {limits['min_l14_stoic']:.1f}"
        )

    # 5. 行业风险
    l11 = scores.get("L11_SectorRisk", 5.0)
    if l11 > limits["max_l11_sector_risk"]:
        blocked_reasons.append(
            f"行业风险 {l11:.1f} > 上限 {limits['max_l11_sector_risk']:.1f}"
        )

    # 6. 估值过热
    l23 = scores.get("L23_Valuation", 5.0)
    if l23 > limits["max_l23_valuation"]:
        warnings.append(
            f"估值评分 {l23:.1f} > {limits['max_l23_valuation']:.1f}（接近过热）"
        )

    # 7. 需求端检查
    l10 = scores.get("L10_Demand", 5.0)
    if l10 < limits["min_demand"]:
        warnings.append(
            f"需求评分 {l10:.1f} < {limits['min_demand']:.1f}（需求不足）"
        )

    # 8. Debate方向加严：Bear占优时额外检查
    bull = scores.get("L30_BullScore", 0)
    bear = scores.get("L30_BearScore", 0)
    if bear > bull and bear > 6.0:
        warnings.append(
            f"辩论层熊方占优 (bull={bull:.1f} vs bear={bear:.1f})"
        )

    # ── 汇总 ──
    passed = len(blocked_reasons) == 0

    if not passed and etf_code:
        logger.info(
            f"⛔ risk_gate 拦截 {etf_code} {etf_name}: {'; '.join(blocked_reasons)}"
        )
    if warnings and etf_code:
        logger.debug(
            f"⚠️ risk_gate 警告 {etf_code} {etf_name}: {'; '.join(warnings)}"
        )

    return {
        "passed": passed,
        "blocked_reasons": blocked_reasons,
        "warnings": warnings,
        "adjusted_scores": adjusted,
        "profile": pk,
        "etf_code": etf_code,
    }
