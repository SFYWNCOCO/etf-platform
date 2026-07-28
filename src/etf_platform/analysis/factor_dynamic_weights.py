#!/usr/bin/env python3
"""
factor_dynamic_weights.py — Regime-conditional动态因子权重 v1.0

基于论文:
  - arxiv:2410.14841 (Dynamic Factor Allocation with Regime-Switching)
  - arxiv:2508.18592 (IC-based Dynamic Weighting, CSI 300实测)

核心理念:
  不同市场regime下，因子的预测能力不同。
  - 恐慌期(fearful): 反转因子(oversold_depth)失效→降权, 动量因子失效→降权
  - 谨慎期(cautious): 平衡配置
  - 正常期(normal): 默认IC权重
  - 贪婪期(complacent): 动量因子权重提升

实现方式: 
  regime → 因子权重乘数 → 归一化 → 替换FACTORS固定权重
  对标MRA-AGRU的简化版(不用GRU,用规则based regime mapping)
"""

from __future__ import annotations

from typing import Any

# ── Base weights (from IC analysis, factor_correlation.py) ────────
# 这些是"市场中性"状态下的最优权重
BASE_WEIGHTS: dict[str, float] = {
    "oversold_depth": 0.40,
    "risk_adj_momentum": 0.25,
    "drawdown_recov": 0.22,
    "sector_flow": 0.10,
    "quality_elastic": 0.03,
}

# ── Regime-conditional weight multipliers ──────────────────────────
# 每个regime对每个因子的权重乘数
# >1.0 = 提升权重, <1.0 = 降低权重
# 基于实证: 
#   - 恐慌期反转因子IC下降70% (arxiv:2410.14841: bear regime下因子active return为负)
#   - 恐慌期资金流向因子更有预测力 (flight-to-safety模式)
REGIME_MULTIPLIERS: dict[str, dict[str, float]] = {
    "complacent": {
        # 贪婪期: 动量强,反转弱
        "oversold_depth": 0.7,       # 超跌反弹在贪婪期不成立
        "risk_adj_momentum": 1.3,    # 动量跟随更有效
        "drawdown_recov": 0.8,       # 回撤修复信号减弱
        "sector_flow": 1.0,          # 资金流正常
        "quality_elastic": 1.2,      # 高质量弹性更重要
    },
    "normal": {
        # 正常期: 基准权重(乘数=1.0)
        "oversold_depth": 1.0,
        "risk_adj_momentum": 1.0,
        "drawdown_recov": 1.0,
        "sector_flow": 1.0,
        "quality_elastic": 1.0,
    },
    "cautious": {
        # 谨慎期: 防御为主,反转信号开始有效
        "oversold_depth": 1.1,       # 超跌开始有反弹机会
        "risk_adj_momentum": 0.9,    # 动量减弱
        "drawdown_recov": 1.1,       # 回撤修复信号增强
        "sector_flow": 0.8,          # 资金流噪声增大
        "quality_elastic": 1.0,
    },
    "fearful": {
        # 恐慌期: 反转因子大幅失效(恐慌抛售≠即将反弹)
        # 此regime下QVIX已经过滤候选池到防御型ETF
        "oversold_depth": 0.3,       # ⚠️ 核心修复: 恐慌期超跌≠反弹
        "risk_adj_momentum": 0.5,    # 动量在恐慌期不可靠
        "drawdown_recov": 0.6,       # 回撤修复信号减弱
        "sector_flow": 1.5,          # 资金流向防御板块的信号增强
        "quality_elastic": 1.4,      # 高质量+防御属性更重要
    },
}


def get_dynamic_weights(regime: str) -> dict[str, float]:
    """返回当前regime下的动态因子权重(归一化到sum=1.0).
    
    Args:
        regime: complacent | normal | cautious | fearful
        
    Returns:
        dict[factor_name, weight] 总和=1.0
    """
    multipliers = REGIME_MULTIPLIERS.get(regime, REGIME_MULTIPLIERS["normal"])
    
    # Apply multipliers to base weights
    raw: dict[str, float] = {}
    for name, base_w in BASE_WEIGHTS.items():
        mult = multipliers.get(name, 1.0)
        raw[name] = base_w * mult
    
    # Normalize to sum=1.0
    total = sum(raw.values())
    if total > 0:
        return {k: v / total for k, v in raw.items()}
    return dict(BASE_WEIGHTS)


def get_factor_list(regime: str) -> list[dict[str, Any]]:
    """返回two_week_picker.py兼容的FACTORS列表格式.
    
    从two_week_picker.py的FACTORS定义中复制raw/desc,
    仅替换weight为动态值.
    """
    weights = get_dynamic_weights(regime)
    
    return [
        {
            "name": "oversold_depth",
            "raw": lambda t, p: -t.change_20d if t else 0,
            "weight": weights.get("oversold_depth", 0.40),
            "desc": "超跌深度(动态)",
        },
        {
            "name": "risk_adj_momentum",
            "raw": lambda t, p: (
                (t.change_20d / max(t.volatility_20d, 1)) if t else 0
            ),
            "weight": weights.get("risk_adj_momentum", 0.25),
            "desc": "风险调整动量(动态)",
        },
        {
            "name": "drawdown_recov",
            "raw": lambda t, p: -t.max_drawdown if t else 0,
            "weight": weights.get("drawdown_recov", 0.22),
            "desc": "回撤修复潜力(动态)",
        },
        {
            "name": "sector_flow",
            "raw": lambda t, p: _get_sector_flow_raw(p.get("sector", ""), p.get("etf_code", "")),
            "weight": weights.get("sector_flow", 0.10),
            "desc": "行业资金流(动态)",
        },
        {
            "name": "quality_elastic",
            "raw": lambda t, p: -p.get("score", 5.0),
            "weight": weights.get("quality_elastic", 0.03),
            "desc": "质量弹性(动态)",
        },
        {
            "name": "behavioral",
            "raw": lambda t, p: _calc_behavioral_alpha(p) - 50,
            "weight": 0.00,  # 永久移除(IC=0.00)
            "desc": "行为Alpha(Z) [已实证移除]",
        },
    ]


# ── 从two_week_picker.py导入的helper ─────────────────────────

def _get_sector_flow_raw(sector: str, etf_code: str = "") -> float:
    """Get sector flow raw value. Fallback to 0 on any error."""
    try:
        from etf_platform.analysis.sector_flow_bridge import get_bridge
        bridge = get_bridge()
        sf = bridge.score(sector, live=False, etf_code=etf_code)
        return sf.get("_return_pct", 0)
    except (ImportError, KeyError, ValueError, TypeError, AttributeError, OSError):
        return 0.0


def _calc_behavioral_alpha(pipe: dict) -> float:
    """Calculate behavioral alpha (0-100)."""
    ls = pipe.get("layer_scores", {})
    l21 = ls.get("L21", {})
    if not l21:
        return 50.0
    sub = l21.get("sub_factors", {})
    if not sub:
        return 50.0
    vals = [
        sub.get("prospect_theory", 50),
        sub.get("herding", 50),
        sub.get("noise_trader", 50),
    ]
    return sum(vals) / len(vals)


# ── CLI ──────────────────────────────────────────────────────

if __name__ == "__main__":
    for regime in ["complacent", "normal", "cautious", "fearful"]:
        w = get_dynamic_weights(regime)
        print(f"\n{regime}:")
        for name, weight in w.items():
            base = BASE_WEIGHTS[name]
            change = (weight - base) / base * 100
            arrow = "↑" if change > 0 else ("↓" if change < 0 else "→")
            print(f"  {name}: {base:.2f} → {weight:.2f} ({arrow}{abs(change):.0f}%)")
