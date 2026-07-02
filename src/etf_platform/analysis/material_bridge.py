# -*- coding: utf-8 -*-
"""material_bridge.py — deep.py material/personnel/tech signals -> L3-L7 scoring

Bridges 3 data sources into layer scores:
  MATERIAL_PRICE_MONITOR -> L3(material safety), L4(supply chain)
  PERSONNEL_RISK_DB      -> L6(politics/governance risk)
  TECH_MILESTONES_V2     -> L5(tech barrier), L7(irreplaceable)

Signal formula:
  material_signal = direction * bottleneck_risk * (1 - substitution_years/10) * scale
  personnel_signal = irreplaceable * age_risk * impact
  tech_signal = (prob - 0.5) * progress_pct * scale
"""

def _get_material_signals():
    """Get all materials from deep.py with caching."""
    try:
        from .deep import get_all_materials
        return get_all_materials()
    except Exception:
        return {}

def _get_personnel_risks():
    try:
        from .deep import PERSONNEL_RISK_DB
        return PERSONNEL_RISK_DB
    except Exception:
        return []

def _get_tech_milestones():
    try:
        from .deep import TECH_MILESTONES_V2
        return TECH_MILESTONES_V2
    except Exception:
        return []


def material_layer_adjustments(etf_code: str) -> dict:
    """Calculate L3-L7 adjustments from deep.py data for a given ETF.

    Returns: {layer: adjustment_value} where positive = bonus, negative = penalty
    """
    adjustments = {"L3_Material": 0.0, "L4_SupplyChain": 0.0,
                   "L5_Tech": 0.0, "L6_Politics": 0.0, "L7_Irreplaceable": 0.0}
    
    # === 1. Material price signals -> L3, L4 ===
    materials = _get_material_signals()
    mat_signals = []
    for mat_name, mat in materials.items():
        if etf_code not in mat.get("affects", []):
            continue
        
        direction = 0
        impact = mat.get("impact_direction", "")
        if impact == "利空": direction = -1
        elif impact == "利好": direction = +1
        elif "利空" in str(impact): direction = -1
        elif "利好" in str(impact): direction = +1
        
        if direction == 0:
            continue
        
        bottleneck = mat.get("bottleneck_risk", 0.5)
        sub_years = mat.get("substitution_years", 5)
        tech_readiness = mat.get("technology_readiness", 5)
        
        # Signal = direction * bottleneck * (1-sub_years/10) * readiness_factor
        # High bottleneck + low substitution -> strong signal
        signal = direction * bottleneck * max(0.1, (1 - sub_years/10)) * (tech_readiness / 10)
        mat_signals.append((mat_name, signal, mat.get("warning", ""), bottleneck))
    
    if mat_signals:
        # Aggregate: sum of all material signals, capped at +/- 2.0
        total_signal = sum(s for _, s, _, _ in mat_signals)
        total_signal = max(-2.0, min(2.0, total_signal))
        
        # Materials affect L3 (material safety) and L4 (supply chain)
        adjustments["L3_Material"] = round(total_signal * 0.7, 2)
        adjustments["L4_SupplyChain"] = round(total_signal * 0.3, 2)
    
    # === 2. Personnel risks -> L6 ===
    personnel = _get_personnel_risks()
    personnel_signal = 0.0
    for p in personnel:
        if etf_code not in p.get("affects_etf", []):
            continue
        
        irreplaceable = p.get("irreplaceable", 0.5)
        age = p.get("age") or 60
        age_risk = 0.0
        if age > 70: age_risk = 0.15
        elif age > 65: age_risk = 0.10
        elif age > 60: age_risk = 0.05
        
        impact = p.get("impact", 0)
        # Personnel risk: always negative (penalty)
        p_signal = -(irreplaceable * 0.6 + age_risk) * abs(impact) * 10
        personnel_signal += p_signal
    
    if personnel_signal != 0:
        adjustments["L6_Politics"] = round(personnel_signal, 2)
    
    # === 3. Tech milestones -> L5, L7 ===
    milestones = _get_tech_milestones()
    tech_signal = 0.0
    for m in milestones:
        if etf_code not in m.get("affects", []):
            continue
        
        prob = m.get("probability", 0.5)
        # Count completed steps
        completed = sum(1 for s in m["milestones"] if "完成" in s.get("status", ""))
        total = len(m["milestones"])
        progress = completed / total if total > 0 else 0
        
        # Signal: above 50% prob = positive, progress matters
        t_signal = (prob - 0.5) * progress * 3.0
        tech_signal += t_signal
    
    if tech_signal != 0:
        adjustments["L5_Tech"] = round(tech_signal, 2)
        adjustments["L7_Irreplaceable"] = round(tech_signal * 0.5, 2)
    
    return adjustments




# === Sector-based inference for uncovered ETFs ===
# Maps sectors to their "anchor" ETFs that have real material data
SECTOR_ANCHORS = {
    "半导体": ["159995", "512480", "512760"],
    "新能源": ["515030", "516160"],
    "AI/科技": ["159819", "515050"],
    "军工": ["512660", "512670"],
    "医药": ["159992", "512170"],
    "硬科技": ["588000", "159995"],
    "红利/价值": ["563300", "512040"],
    "金融": ["512880"],
    "通信/5G": ["515050", "515880"],
    "消费": ["512690"],
}

# Related sector groups for cross-sector inference
SECTOR_GROUPS = {
    "tech": ["半导体", "AI/科技", "硬科技", "通信/5G", "电子"],
    "defense": ["军工", "航空航天"],
    "energy": ["新能源", "周期/资源", "有色"],
    "healthcare": ["医药", "医疗", "创新药"],
    "finance": ["金融", "证券", "银行", "保险"],
    "consumer": ["消费", "白酒", "食品饮料", "家电"],
    "broad": ["宽基", "综合", "跨境"],
}

def _get_sector_group(sector):
    for group, sectors in SECTOR_GROUPS.items():
        if sector in sectors:
            return group
    return None

def sector_inferred_adjustments(etf_code: str, sector: str) -> dict:
    """Infer material adjustments for ETFs without direct deep.py coverage.
    
    Strategy: find anchor ETFs in the same sector that have real material data,
    average their adjustments, and apply with a discount factor.
    """
    # If this ETF already has direct coverage, skip inference
    direct = material_layer_adjustments(etf_code)
    has_direct = any(abs(v) > 0.001 for v in direct.values())
    if has_direct:
        return direct
    
    # Find anchor ETFs in same sector
    anchors = SECTOR_ANCHORS.get(sector, [])
    
    # If no direct sector anchors, try related sectors
    if not anchors:
        group = _get_sector_group(sector)
        if group:
            for related_sector, related_anchors in SECTOR_ANCHORS.items():
                if _get_sector_group(related_sector) == group:
                    anchors.extend(related_anchors)
            anchors = list(set(anchors))  # dedupe
    
    if not anchors:
        return {"L3_Material": 0.0, "L4_SupplyChain": 0.0,
                "L5_Tech": 0.0, "L6_Politics": 0.0, "L7_Irreplaceable": 0.0}
    
    # Compute average adjustment from anchors
    anchor_adjs = []
    for anchor_code in anchors:
        if anchor_code == etf_code:
            continue
        adj = material_layer_adjustments(anchor_code)
        anchor_adjs.append(adj)
    
    if not anchor_adjs:
        return {"L3_Material": 0.0, "L4_SupplyChain": 0.0,
                "L5_Tech": 0.0, "L6_Politics": 0.0, "L7_Irreplaceable": 0.0}
    
    # Average across anchors
    avg = {}
    for layer in ["L3_Material", "L4_SupplyChain", "L5_Tech", "L6_Politics", "L7_Irreplaceable"]:
        vals = [a.get(layer, 0) for a in anchor_adjs]
        avg[layer] = sum(vals) / len(vals)
    
    # Discount factor: more anchors = higher confidence
    n_anchors = len(anchor_adjs)
    if n_anchors >= 3:
        discount = 0.7
    elif n_anchors >= 2:
        discount = 0.6
    else:
        discount = 0.4
    
    # Apply discount
    result = {}
    for layer, val in avg.items():
        result[layer] = round(val * discount, 2)
    
    return result


def apply_to_layers(etf_code: str, layer_scores: dict, sector: str = None) -> dict:
    """Apply material/personnel/tech adjustments to layer scores in-place.
    
    Uses sector inference for ETFs without direct coverage.
    Returns the modified layer_scores dict.
    """
    adjustments = material_layer_adjustments(etf_code)
    
    # If no direct data, try sector inference
    has_direct = any(abs(v) > 0.001 for v in adjustments.values())
    if not has_direct and sector:
        adjustments = sector_inferred_adjustments(etf_code, sector)
    
    for layer, adj in adjustments.items():
        if layer in layer_scores and adj != 0:
            old = layer_scores[layer]
            layer_scores[layer] = round(max(1.0, min(10.0, old + adj)), 1)
    
    return layer_scores