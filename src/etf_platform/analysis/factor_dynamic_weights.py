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

import json
from pathlib import Path
from typing import Any

# d751 新闻情绪因子数据源（复用 macro_overlay.news_sentiment.json）
BASE = Path(__file__).resolve().parent.parent.parent.parent  # etf-platform/
SENT_FILE = BASE / "data" / "news_sentiment.json"

# ── Base weights (from IC analysis, factor_correlation.py) ────────
# 这些是"市场中性"状态下的最优权重
# d751: oversold_depth 0.40→0.38, risk_adj_momentum 0.25→0.23,
#       drawdown_recov 0.22→0.20, sector_flow 0.10→0.08，合计让出 0.08 给 news_sentiment
#       (0.38+0.23+0.20+0.08+0.03+0.08 = 1.00)
BASE_WEIGHTS: dict[str, float] = {
    "oversold_depth": 0.38,
    "risk_adj_momentum": 0.23,
    "drawdown_recov": 0.20,
    "sector_flow": 0.08,
    "quality_elastic": 0.03,
    "news_sentiment": 0.08,
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
        "news_sentiment": 1.0,       # 贪婪期情绪跟风有效但易过热
    },
    "normal": {
        # 正常期: 基准权重(乘数=1.0)
        "oversold_depth": 1.0,
        "risk_adj_momentum": 1.0,
        "drawdown_recov": 1.0,
        "sector_flow": 1.0,
        "quality_elastic": 1.0,
        "news_sentiment": 1.0,
    },
    "cautious": {
        # 谨慎期: 防御为主,反转信号开始有效
        "oversold_depth": 1.1,       # 超跌开始有反弹机会
        "risk_adj_momentum": 0.9,    # 动量减弱
        "drawdown_recov": 1.1,       # 回撤修复信号增强
        "sector_flow": 0.8,          # 资金流噪声增大
        "quality_elastic": 1.0,
        "news_sentiment": 1.3,       # 谨慎期情绪信号更重要
    },
    "fearful": {
        # 恐慌期: 反转因子大幅失效(恐慌抛售≠即将反弹)
        # 此regime下QVIX已经过滤候选池到防御型ETF
        "oversold_depth": 0.3,       # ⚠️ 核心修复: 恐慌期超跌≠反弹
        "risk_adj_momentum": 0.5,    # 动量在恐慌期不可靠
        "drawdown_recov": 0.6,       # 回撤修复信号减弱
        "sector_flow": 1.5,          # 资金流向防御板块的信号增强
        "quality_elastic": 1.4,      # 高质量+防御属性更重要
        "news_sentiment": 1.5,       # 恐慌期情绪反转价值高
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
            "name": "news_sentiment",
            "raw": lambda t, p: _get_sentiment_raw(p.get("sector", ""), p.get("etf_code", "")),
            "weight": weights.get("news_sentiment", 0.08),
            "desc": "新闻情绪因子(d751)",
        },
        {
            "name": "behavioral",
            "raw": lambda t, p: _calc_behavioral_alpha(p) - 50,
            "weight": 0.00,  # 永久移除(IC=0.00)
            "desc": "行为Alpha(Z) [已实证移除]",
        },
    ]


# ── 从two_week_picker.py导入的helper ─────────────────────────

def _get_sentiment_raw(sector: str, etf_code: str = "") -> float:
    """新闻情绪原始分(d751)，复用 macro_overlay.get_news_boost 的 sector 匹配逻辑。

    读取 data/news_sentiment.json 的 sectors（key in sector or sector in key），
    返回原始分数: 看多强→+1.0, 看多中→+0.6, 看多弱→+0.3, 看空强→-1.0,
    看空中→-0.6, 看空弱→-0.3, 中性→0.0。文件不存在/异常 → 0.0。
    """
    if not sector or not SENT_FILE.exists():
        return 0.0
    try:
        with open(SENT_FILE, encoding="utf-8") as f:
            d = json.load(f)
        sectors = d.get("sectors", {})
    except (OSError, ValueError):
        return 0.0
    for key, value in sectors.items():
        if not isinstance(value, dict):
            continue
        if key in sector or sector in key:
            direction = value.get("direction", "")
            strength = value.get("strength", "")
            sent_map = {
                ("看多", "强"): 1.0, ("看多", "中"): 0.6, ("看多", "弱"): 0.3,
                ("看空", "强"): -1.0, ("看空", "中"): -0.6, ("看空", "弱"): -0.3,
                ("中性", "强"): 0.0, ("中性", "中"): 0.0, ("中性", "弱"): 0.0,
            }
            return sent_map.get((direction, strength), 0.0)
    return 0.0


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
