"""L27 Factor Smart Beta Layer — 因子投资与Smart Beta(k042+k229).

KB来源:
  - k042-factor-investing-smart-beta.md: Fama-French到多因子组合
  - k229-factor-investing-system.md: 量化因子投资体系

核心规则:
  - 价值/质量/低波因子在防御期占优
  - 动量/成长因子在趋势期占优
  - Size因子在小盘/成长行业有暴露
  - 多因子组合优于单因子
  - 因子拥挤度: 过度拥挤→反转风险

设计:
  - 纯KB+规则驱动，无HTTP
  - 按sector映射因子暴露+当前regime适配度
  - 中心5.0，微调±1.5
"""
from __future__ import annotations

from typing import Any

# k042+k229: 行业→因子暴露矩阵
SECTOR_FACTOR_EXPOSURE: dict[str, dict[str, float]] = {
    "半导体": {"Value": -0.5, "Quality": 0.3, "Momentum": 0.7, "LowVol": -0.8, "Size": 0.5, "Growth": 0.9},
    "AI算力": {"Value": -0.4, "Quality": 0.3, "Momentum": 0.8, "LowVol": -0.7, "Size": 0.3, "Growth": 0.8},
    "新能源": {"Value": -0.2, "Quality": -0.1, "Momentum": -0.3, "LowVol": -0.5, "Size": 0.2, "Growth": 0.4},
    "光伏": {"Value": -0.4, "Quality": -0.2, "Momentum": -0.5, "LowVol": -0.8, "Size": 0.3, "Growth": 0.2},
    "医药": {"Value": -0.2, "Quality": 0.4, "Momentum": 0.3, "LowVol": -0.3, "Size": 0.2, "Growth": 0.5},
    "创新药": {"Value": -0.3, "Quality": 0.3, "Momentum": 0.5, "LowVol": -0.5, "Size": 0.3, "Growth": 0.7},
    "军工": {"Value": -0.1, "Quality": 0.2, "Momentum": 0.2, "LowVol": -0.4, "Size": 0.1, "Growth": 0.4},
    "消费": {"Value": 0.3, "Quality": 0.6, "Momentum": 0.1, "LowVol": 0.4, "Size": 0.0, "Growth": 0.2},
    "白酒": {"Value": 0.4, "Quality": 0.7, "Momentum": 0.0, "LowVol": 0.5, "Size": -0.2, "Growth": 0.1},
    "金融": {"Value": 0.3, "Quality": 0.4, "Momentum": 0.0, "LowVol": 0.3, "Size": -0.2, "Growth": 0.1},
    "银行": {"Value": 0.6, "Quality": 0.5, "Momentum": -0.1, "LowVol": 0.5, "Size": -0.4, "Growth": -0.1},
    "券商": {"Value": 0.1, "Quality": 0.1, "Momentum": 0.5, "LowVol": -0.8, "Size": -0.2, "Growth": 0.4},
    "红利": {"Value": 0.7, "Quality": 0.6, "Momentum": 0.0, "LowVol": 0.7, "Size": -0.5, "Growth": -0.2},
    "公用事业": {"Value": 0.8, "Quality": 0.5, "Momentum": 0.0, "LowVol": 0.9, "Size": -0.3, "Growth": 0.0},
    "通信": {"Value": -0.3, "Quality": 0.2, "Momentum": 0.4, "LowVol": -0.5, "Size": 0.2, "Growth": 0.5},
    "电子": {"Value": -0.3, "Quality": 0.2, "Momentum": 0.3, "LowVol": -0.5, "Size": 0.2, "Growth": 0.5},
    "计算机": {"Value": -0.3, "Quality": 0.2, "Momentum": 0.3, "LowVol": -0.5, "Size": 0.3, "Growth": 0.6},
    "传媒": {"Value": -0.4, "Quality": -0.1, "Momentum": 0.2, "LowVol": -0.4, "Size": 0.5, "Growth": 0.6},
    "游戏": {"Value": -0.5, "Quality": 0.0, "Momentum": 0.2, "LowVol": -0.5, "Size": 0.6, "Growth": 0.7},
    "电力": {"Value": 0.7, "Quality": 0.4, "Momentum": 0.0, "LowVol": 0.8, "Size": -0.3, "Growth": 0.0},
    "煤炭": {"Value": 0.5, "Quality": 0.3, "Momentum": 0.1, "LowVol": 0.2, "Size": -0.2, "Growth": -0.1},
    "有色金属": {"Value": 0.0, "Quality": 0.1, "Momentum": 0.2, "LowVol": -0.3, "Size": 0.1, "Growth": 0.2},
    "房地产": {"Value": 0.2, "Quality": -0.2, "Momentum": -0.3, "LowVol": -0.2, "Size": 0.0, "Growth": -0.1},
    "建筑装饰": {"Value": 0.3, "Quality": 0.2, "Momentum": -0.1, "LowVol": 0.0, "Size": -0.1, "Growth": 0.0},
    "商业航天": {"Value": -0.3, "Quality": 0.1, "Momentum": 0.5, "LowVol": -0.5, "Size": 0.3, "Growth": 0.7},
    "低空经济": {"Value": -0.2, "Quality": 0.1, "Momentum": 0.4, "LowVol": -0.4, "Size": 0.3, "Growth": 0.6},
    "AI4S": {"Value": -0.3, "Quality": 0.3, "Momentum": 0.4, "LowVol": -0.4, "Size": 0.2, "Growth": 0.7},
    "具身智能": {"Value": -0.4, "Quality": 0.1, "Momentum": 0.4, "LowVol": -0.5, "Size": 0.3, "Growth": 0.7},
    "合成生物": {"Value": -0.3, "Quality": 0.2, "Momentum": 0.3, "LowVol": -0.4, "Size": 0.3, "Growth": 0.6},
    "脑机接口": {"Value": -0.4, "Quality": 0.1, "Momentum": 0.4, "LowVol": -0.5, "Size": 0.4, "Growth": 0.8},
    "量子计算": {"Value": -0.4, "Quality": 0.1, "Momentum": 0.3, "LowVol": -0.6, "Size": 0.4, "Growth": 0.8},
}

# k042: Regime→因子权重
REGIME_FACTOR_WEIGHTS: dict[str, dict[str, float]] = {
    "bull_trend": {"Value": 0.10, "Quality": 0.15, "Momentum": 0.30, "LowVol": 0.05, "Size": 0.10, "Growth": 0.30},
    "bear_crisis": {"Value": 0.25, "Quality": 0.25, "Momentum": 0.05, "LowVol": 0.25, "Size": 0.05, "Growth": 0.15},
    "sideways": {"Value": 0.20, "Quality": 0.25, "Momentum": 0.10, "LowVol": 0.20, "Size": 0.10, "Growth": 0.15},
    "recovery": {"Value": 0.15, "Quality": 0.20, "Momentum": 0.20, "LowVol": 0.10, "Size": 0.15, "Growth": 0.20},
}

# k229: 因子拥挤度惩罚(简化版)
FACTOR_CROWDING_PENALTY: dict[str, float] = {
    "Momentum": -0.3,
    "Growth": -0.2,
    "Quality": 0.0,
    "Value": 0.1,
    "LowVol": 0.0,
    "Size": -0.1,
}


def _normalize_sector(sector: str) -> str:
    """Normalize sector aliases."""
    aliases = {
        "半导体设备": "半导体",
        "半导体材料": "半导体",
        "芯片": "半导体",
        "AI/科技": "AI算力",
        "AI/半导体": "AI算力",
        "云计算/算力": "AI算力",
        "通信/光模块": "AI算力",
        "通信/5G": "AI算力",
        "5G/PCB": "AI算力",
        "机器人/智造": "具身智能",
        "新能源车": "新能源",
        "电池": "新能源",
        "储能": "新能源",
        "绿电": "新能源",
        "电力": "新能源",
        "医药生物": "医药",
        "医药器械": "医药",
        "中药": "医药",
        "国防军工": "军工",
        "红利/价值": "红利",
        "食品饮料": "消费",
        "家电": "消费",
        "人形机器人": "具身智能",
    }
    return aliases.get(sector, sector)


def score_l27_layer(
    sector: str = "",
    regime: str = "normal",
) -> dict[str, Any]:
    """Score factor smart-beta alignment for sector.

    Args:
        sector: ETF sector
        regime: Market regime (bull_trend/bear_crisis/sideways/recovery/normal)

    Returns:
        dict with 'score'(float), 'detail'(dict)
    """
    sector_norm = _normalize_sector(sector)
    exposure = SECTOR_FACTOR_EXPOSURE.get(sector_norm, {})

    if not exposure:
        return {
            "score": 5.0,
            "detail": {
                "sector": sector_norm,
                "regime": regime,
                "factor_alignment": 0.0,
                "dominant_factors": [],
                "kb_source": "k042+k229",
            },
        }

    # Map regime to factor weights
    regime_key = regime if regime in REGIME_FACTOR_WEIGHTS else "sideways"
    weights = REGIME_FACTOR_WEIGHTS[regime_key]

    # Calculate factor alignment score
    alignment = 0.0
    factor_scores = {}
    for factor, weight in weights.items():
        exp = exposure.get(factor, 0.0)
        # Alignment: positive exposure in favorable factor = good
        raw_alignment = exp * weight * 4.0  # Scale to ~[-2,+2] per factor
        crowding = FACTOR_CROWDING_PENALTY.get(factor, 0.0)
        factor_score = raw_alignment + crowding
        factor_scores[factor] = round(factor_score, 2)
        alignment += factor_score * weight

    # Normalize alignment to ±1.5 range
    alignment = max(-1.5, min(1.5, alignment * 2.0))

    # Dominant factors
    sorted_factors = sorted(factor_scores.items(), key=lambda x: abs(x[1]), reverse=True)
    dominant = [f for f, s in sorted_factors[:3] if abs(s) > 0.1]

    score = round(max(1.0, min(10.0, 5.0 + alignment)), 1)

    detail = {
        "sector": sector_norm,
        "regime": regime,
        "factor_alignment": round(alignment, 2),
        "dominant_factors": dominant,
        "factor_scores": factor_scores,
        "kb_source": "k042+k229",
    }
    return {"score": score, "detail": detail}


def get_factor_style(score: float, detail: dict[str, Any]) -> str:
    """Classify factor style from score and detail."""
    alignment = detail.get("factor_alignment", 0.0)
    if alignment > 0.5:
        return "factor_favorable"
    if alignment < -0.5:
        return "factor_unfavorable"
    return "factor_neutral"
