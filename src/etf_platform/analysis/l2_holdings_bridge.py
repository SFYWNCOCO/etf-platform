"""
l2_holdings_bridge.py - L2 holdings penetration scoring
=========================================================
v5.5: Converts holdings data (import dependency, concentration) into L2 scores.
Uses sector inference for ETFs without direct coverage (same pattern as material_bridge).
"""

def _compute_l2_score_from_holdings(code: str) -> float | None:
    """Compute L2 score (1-10) from holdings data. Higher = safer holdings structure."""
    try:
        from .holdings import get_holdings
        h = get_holdings(code)
        if not h:
            return None
        
        top10 = h.get("top10", [])
        if not top10:
            return None
        
        # Weighted import dependency
        weighted_dep = sum(s["weight"] * s.get("import_dep", 0) for s in top10)
        
        # Concentration risk: top3 weight
        top3_weight = sum(s["weight"] for s in top10[:3])
        
        # Score calculation:
        # - Import dependency penalty: weighted_dep * 10 (0=no dep, 1=full dep → 10 point penalty)
        # - Concentration penalty: top3_weight * 5
        # Base score 10, subtract penalties
        base = 10.0
        dep_penalty = weighted_dep * 8.0     # max -8 for fully dependent
        conc_penalty = top3_weight * 4.0     # max -4 for fully concentrated
        score = base - dep_penalty - conc_penalty
        
        return round(max(1.0, min(10.0, score)), 1)
    except Exception:
        return None


# Sector→anchor ETF mapping for L2 inference
L2_SECTOR_ANCHORS = {
    "半导体":    ["159995"],
    "AI/科技":   ["159819"],
    "AI算力":    ["159819"],
    "云计算/算力": ["516510"],
    "红利/价值": ["512890"],
    "黄金/贵金属": ["518880"],
    "消费":      ["512690"],
    "白酒消费":  ["512690"],
}

# Sector groups for cross-sector inference
L2_SECTOR_GROUPS = {
    "tech":    ["半导体", "半导体设备", "AI/科技", "AI算力", "硬科技", "通信/5G", "电子", "云计算/算力", "机器人/智造"],
    "defense": ["军工", "航空航天"],
    "energy":  ["新能源", "新能源车", "光伏", "风电", "电池"],
    "health":  ["医药", "中药", "医药器械"],
    "finance": ["金融", "银行", "保险", "证券", "券商"],
    "consumer":["消费", "白酒消费", "食品饮料", "家电", "养殖"],
    "defensive":["红利/价值", "红利+低波", "高股息", "公用事业"],
    "cyclical":["周期/资源", "有色", "钢铁", "煤炭", "化工"],
    "broad":   ["宽基", "全市场", "综合", "跨境"],
}


def get_l2_score(code: str, sector: str = None) -> float:
    """Get L2 score for an ETF, using direct data or sector inference."""
    # Try direct
    score = _compute_l2_score_from_holdings(code)
    if score is not None:
        return score
    
    # Sector inference
    if sector:
        anchors = L2_SECTOR_ANCHORS.get(sector, [])
        if not anchors:
            for group, sectors in L2_SECTOR_GROUPS.items():
                if sector in sectors:
                    for s in sectors:
                        if s in L2_SECTOR_ANCHORS:
                            anchors.extend(L2_SECTOR_ANCHORS[s])
                    anchors = list(set(anchors))
                    break
        
        if anchors:
            scores = []
            for ac in anchors:
                if ac == code:
                    continue
                s = _compute_l2_score_from_holdings(ac)
                if s is not None:
                    scores.append(s)
            if scores:
                return round(sum(scores) / len(scores), 1)
    
    # Fallback: neutral score
    return 5.0


def apply_l2_score(code: str, sector: str, layer_scores: dict) -> dict:
    """Apply L2 score to layer_scores in-place."""
    try:
        l2_score = get_l2_score(code, sector)
        layer_scores["L2_Holdings"] = l2_score
    except Exception:
        layer_scores["L2_Holdings"] = 5.0
    return layer_scores