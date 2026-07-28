"""L25 Liquidity & Arbitrage Layer — ETF流动性与套利机制(k261).

KB来源: k261-etf-liquidity-arbitrage-2026.md
核心规则:
  - ETF流动性来自AP套利机制，非二级交易量
  - CRF>1.5 = 流动性压力信号
  - 跨境/QDII/债券ETF套利效率低→折溢价风险高
  - 极端折溢价是风险信号，不是买入信号
  - 股票大盘ETF套利效率高→流动性加分

设计:
  - 纯KB驱动，无HTTP
  - 按ETF类型+sector映射流动性评分
  - 中心5.0，微调±2.0
"""
from __future__ import annotations

from typing import Any

# ETF类型→基础流动性评分
TYPE_LIQUIDITY_BASE: dict[str, float] = {
    "股票ETF": 7.5,
    "行业ETF": 7.0,
    "宽基ETF": 8.0,
    "跨境ETF": 4.5,
    "QDII": 4.0,
    "债券ETF": 5.5,
    "商品ETF": 5.0,
    "货币ETF": 8.5,
    "杠杆ETF": 4.5,
    "反向ETF": 4.0,
    "LOF": 5.0,
}

# sector→流动性修正
SECTOR_LIQUIDITY_ADJ: dict[str, float] = {
    "半导体": 0.5,
    "AI算力": 0.5,
    "新能源": -0.3,
    "光伏": -0.5,
    "医药": 0.0,
    "创新药": -0.2,
    "军工": -0.3,
    "消费": 0.3,
    "白酒": 0.5,
    "金融": 0.4,
    "银行": 0.6,
    "券商": -0.2,
    "红利": 0.5,
    "公用事业": 0.4,
    "通信": 0.2,
    "电子": 0.3,
    "计算机": 0.0,
    "传媒": -0.3,
    "游戏": -0.3,
    "电力": 0.2,
    "煤炭": 0.1,
    "有色金属": -0.1,
    "钢铁": -0.2,
    "房地产": -0.5,
    "建筑装饰": -0.2,
    "国防军工": -0.3,
    "商业航天": -0.3,
    "低空经济": -0.3,
    "AI4S": 0.0,
    "具身智能": -0.2,
    "合成生物": -0.2,
    "脑机接口": -0.2,
    "量子计算": -0.2,
}

# k261: 不同类型ETF套利效率
ARBITRAGE_EFFICIENCY: dict[str, float] = {
    "股票ETF": 8.5,
    "行业ETF": 7.5,
    "宽基ETF": 9.0,
    "跨境ETF": 4.0,
    "QDII": 3.5,
    "债券ETF": 5.5,
    "商品ETF": 5.0,
    "货币ETF": 9.0,
    "杠杆ETF": 5.0,
    "反向ETF": 4.5,
    "LOF": 5.5,
}


def _normalize_sector(sector: str) -> str:
    """Normalize sector aliases to canonical names."""
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
        "商业航天": "商业航天",
        "低空经济": "低空经济",
        "量子": "量子计算",
        "AI4S": "AI4S",
        "合成生物": "合成生物",
        "脑机接口": "脑机接口",
        "人形机器人": "具身智能",
        "红利/价值": "红利",
        "食品饮料": "消费",
        "家电": "消费",
    }
    return aliases.get(sector, sector)


def score_l25_layer(
    etf_type: str = "",
    sector: str = "",
    premium_pct: float = 0.0,
    turnover_ratio: float | None = None,
) -> dict[str, Any]:
    """Score ETF liquidity & arbitrage efficiency.

    Args:
        etf_type: ETF type from etfs.yaml (股票ETF/跨境ETF/债券ETF etc.)
        sector: ETF sector
        premium_pct: Current premium/discount percentage (optional)
        turnover_ratio: Turnover ratio for secondary market liquidity proxy

    Returns:
        dict with 'score'(float), 'detail'(dict)
    """
    sector_norm = _normalize_sector(sector)

    # Base score from ETF type
    base = TYPE_LIQUIDITY_BASE.get(etf_type, 6.0)
    arb_eff = ARBITRAGE_EFFICIENCY.get(etf_type, 6.0)

    # Sector adjustment
    sector_adj = SECTOR_LIQUIDITY_ADJ.get(sector_norm, 0.0)

    # Premium/discount penalty (k261: extreme premium/discount = risk signal)
    premium_penalty = 0.0
    premium_signal = "normal"
    abs_premium = abs(premium_pct)
    if abs_premium > 5.0:
        premium_penalty = -2.0
        premium_signal = "extreme_premium_risk" if premium_pct > 0 else "extreme_discount_risk"
    elif abs_premium > 2.0:
        premium_penalty = -1.0
        premium_signal = "elevated_premium" if premium_pct > 0 else "elevated_discount"
    elif abs_premium > 0.5:
        premium_penalty = -0.3
        premium_signal = "mild_premium" if premium_pct > 0 else "mild_discount"

    # Turnover bonus (secondary market liquidity proxy)
    turnover_bonus = 0.0
    if turnover_ratio is not None:
        if turnover_ratio > 5.0:
            turnover_bonus = 0.8
        elif turnover_ratio > 2.0:
            turnover_bonus = 0.4
        elif turnover_ratio < 0.3:
            turnover_bonus = -0.5

    # Combine: weighted average of base + arb efficiency + adjustments
    raw = (base * 0.45 + arb_eff * 0.35) + sector_adj + premium_penalty + turnover_bonus
    score = round(max(1.0, min(10.0, raw)), 1)

    # CRF proxy: cross-border/QDII get structural liquidity warning
    crf_status = "normal"
    if etf_type in ("跨境ETF", "QDII"):
        crf_status = "structural_low_efficiency"
    elif abs_premium > 2.0:
        crf_status = "potential_stress"

    detail = {
        "base_type": etf_type or "unknown",
        "sector": sector_norm,
        "arbitrage_efficiency": round(arb_eff, 1),
        "sector_adj": sector_adj,
        "premium_pct": premium_pct,
        "premium_signal": premium_signal,
        "turnover_ratio": turnover_ratio,
        "crf_status": crf_status,
        "kb_source": "k261",
    }
    return {"score": score, "detail": detail}


def get_liquidity_category(score: float) -> str:
    """Categorize liquidity score."""
    if score >= 7.5:
        return "high_liquidity"
    if score >= 6.0:
        return "adequate_liquidity"
    if score >= 4.5:
        return "moderate_liquidity"
    return "low_liquidity_risk"
