"""L2_Holdings sector-based heuristic scoring.

Problem: Only 6 ETFs have direct holdings data in holdings.py.
586 ETFs fall back to 5.0 (neutral) because sector anchors are limited.

Solution: Use sector characteristics to derive L2 scores based on
portfolio structure heuristics:
- Broad index ETFs (宽基): naturally diversified → higher score
- Bond/money ETFs: single-asset class → medium score  
- Commodity ETFs: single commodity → medium score
- Sector ETFs: concentrated → lower score
- Thematic ETFs: very concentrated → lowest score
"""
import logging

logger = logging.getLogger(__name__)

# Sector -> L2 heuristic score (1-10)
# Based on typical portfolio diversification for each sector type
SECTOR_L2_HEURISTIC = {
    # Broad market ETFs - highly diversified across sectors
    "宽基": 8.0,
    "全市场": 8.0,
    "综合": 7.5,
    "大盘蓝筹": 7.5,
    "中盘成长": 7.0,
    "小盘价值": 6.5,
    "成长股": 6.5,
    
    # Fixed income - single asset class but diversified issuers
    "利率债": 8.5,
    "信用债": 7.5,
    "可转债": 6.5,
    "货币": 8.0,
    "货币基金": 8.0,
    
    # Commodities - single commodity exposure
    "贵金属": 7.0,
    "有色金属": 5.5,
    "能源化工": 5.0,
    "农产品": 5.5,
    
    # Cross-border - geographic diversification benefit
    "跨境": 7.0,
    "中概互联网": 6.0,
    "港股科技": 6.0,
    "港股综合": 6.5,
    "美股科技": 6.5,
    "美股科技100": 6.5,
    "美股综合": 7.0,
    "美股杠杆": 5.5,
    
    # Traditional sectors - moderate diversification
    "消费": 6.5,
    "白酒消费": 6.0,
    "白酒": 6.0,
    "食品饮料": 6.5,
    "家电": 6.0,
    "医药": 6.5,
    "中药": 7.0,
    "医药器械": 6.0,
    "医疗器械": 6.0,
    "港股医药": 6.0,
    "养殖": 5.5,
    "农牧": 5.5,
    "传媒": 6.0,
    
    # Financial - diverse holdings
    "金融": 7.0,
    "银行": 7.0,
    "保险": 7.0,
    "证券": 6.5,
    "券商": 6.5,
    
    # Defensive/dividend
    "红利/价值": 7.5,
    "红利价值": 7.5,
    "红利+低波": 7.5,
    "高股息": 7.5,
    "公用事业": 7.0,
    
    # Cyclical/industrial
    "周期/资源": 5.5,
    "钢铁": 5.0,
    "煤炭": 5.0,
    "化工": 5.5,
    "基建/地产": 5.0,
    "房地产": 5.0,
    "交通运输": 6.0,
    "环保": 6.0,
    "央企改革": 6.5,
    
    # Tech-heavy sectors - concentrated by nature
    "半导体": 5.0,
    "半导体设备": 4.5,
    "半导体做空": 4.5,
    "半导体杠杆": 4.5,
    "AI/科技": 5.0,
    "AI算力": 5.0,
    "云计算/算力": 5.5,
    "硬科技": 5.0,
    "硬科技做空": 4.5,
    "硬科技杠杆": 4.5,
    "通信/5G": 5.0,
    "通信/光模块": 5.0,
    "5G/PCB": 5.0,
    "机器人/智造": 5.0,
    "计算机": 5.5,
    "电子": 5.0,
    
    # Energy
    "新能源": 5.5,
    "新能源车": 5.0,
    "光伏": 5.0,
    "风电": 5.5,
    "电池": 5.5,
    
    # Defense
    "军工": 5.5,
    "航空航天": 5.5,
    
    # Default
    "其他": 6.0,
}

# Additional keyword fallbacks for sectors not in the main dict
KEYWORD_FALLBACKS = [
    (["港股"], 6.0),
    (["美股"], 6.5),
    (["科技"], 5.0),
    (["消费"], 6.5),
    (["医药"], 6.5),
    (["金融"], 7.0),
    (["能源"], 5.0),
    (["资源"], 5.5),
    (["红利"], 7.5),
    (["债券"], 7.5),
    (["黄金"], 7.0),
    (["商品"], 6.0),
]


def _heuristic_l2_score(sector: str) -> float:
    """Get L2 score from sector heuristics."""
    if not sector:
        return 5.0
    
    # Direct match
    if sector in SECTOR_L2_HEURISTIC:
        return SECTOR_L2_HEURISTIC[sector]
    
    # Keyword fallback (longest match wins)
    best_score = None
    best_len = 0
    for keywords, score in KEYWORD_FALLBACKS:
        for kw in keywords:
            if kw in sector or sector in kw:
                if len(kw) > best_len:
                    best_len = len(kw)
                    best_score = score
    if best_score is not None:
        return best_score
    
    return 6.0  # ultimate fallback


def get_l2_score_heuristic(code: str, sector: str = None, risk_level: float = 0.5, fee: float = 0.005) -> float:
    """Get L2 score using sector heuristics as primary method.
    
    Falls back to holdings data if available, then to sector anchors,
    then to heuristic scoring.
    
    v7.5: Added risk_level and fee parameters for ETF-level differentiation.
    Without these, all ETFs in the same sector get identical L2 scores.
    """
    # Try direct holdings data first (most accurate)
    try:
        from .holdings import get_holdings
        h = get_holdings(code)
        if h and h.get("top10"):
            top10 = h["top10"]
            weighted_dep = sum(s["weight"] * s.get("import_dep", 0) for s in top10)
            top3_weight = sum(s["weight"] for s in top10[:3])
            base = 10.0
            dep_penalty = weighted_dep * 8.0
            conc_penalty = top3_weight * 4.0
            score = base - dep_penalty - conc_penalty
            # v7.5: Small risk_level modulation on holdings-based scores
            rl_mod = (0.5 - risk_level) * 0.3
            return round(max(1.0, min(10.0, score + rl_mod)), 1)
    except (KeyError, IndexError, TypeError, ValueError) as e:
        logger.debug("holdings-based L2 score failed: %s", e)
        pass

    # Use sector heuristic as the primary fallback
    if sector:
        score = _heuristic_l2_score(sector)
        # v7.5/v8.17: ETF-level differentiation via risk_level and fee
        # Lower risk ETFs have more diversified holdings → slight bonus
        # v8.29: Reduced rl_mod from ±0.5 to ±0.3 to reduce ceiling effect.
        # Previously: rl=0.22 → rl_mod=+0.27, pushing sector=8.0 up to 8.3, then fee_mod+0.5 → 8.8, clamped to 9.0.
        # 27.7% of ETFs ended up at exactly 9.0, creating a massive ceiling cluster.
        # Now: rl_mod range is ±0.3, reducing ceiling pressure.
        rl_mod = (0.5 - risk_level) * 0.3
        # Lower fee ETFs tend to be more popular → slight bonus
        # v8.29: Reduced fee_mod from ±0.5 to ±0.3 to reduce ceiling effect.
        # Previously fee<=0.0003 → +0.5 pushed many sector=8.0 ETFs to 9.0 clamp.
        fee_mod = 0.0
        if fee <= 0.0003:
            fee_mod = 0.3  # reduced from 0.5
        elif fee <= 0.0005:
            fee_mod = 0.2  # reduced from 0.3
        elif fee <= 0.0010:
            fee_mod = 0.1
        elif fee > 0.003:
            fee_mod = -0.2  # reduced from -0.3
        elif fee > 0.0020:
            fee_mod = -0.1  # reduced from -0.15
        return round(max(1.0, min(10.0, score + rl_mod + fee_mod)), 1)
    
    return 6.0


def apply_l2_score(code: str, sector: str, layer_scores: dict, risk_level: float = 0.5, fee: float = 0.005) -> dict:
    """Apply L2 score to layer_scores in-place.
    
    v7.5: Added risk_level and fee parameters for ETF-level differentiation.
    """
    try:
        l2_score = get_l2_score_heuristic(code, sector, risk_level=risk_level, fee=fee)
        layer_scores["L2_Holdings"] = l2_score
    except (KeyError, ValueError, TypeError, AttributeError, ImportError):
        layer_scores["L2_Holdings"] = 6.0
    return layer_scores
