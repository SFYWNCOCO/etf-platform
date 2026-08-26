"""
layer_sector_scores.py — sector-level L3-L7 scores replacing risk_level derivation
===================================================================================
v5.5: Replaces the "one risk_level -> 8 layers" bottleneck with sector-informed scores.

Design:
- Each sector gets a 1-10 score per layer based on industry fundamentals
- Applied in pipeline.py AFTER base scores but BEFORE chain risk / material_bridge
- Updates: monthly review, quarterly data refresh
- Fallback: use risk_level-derived score for unknown sectors

Reference: l003 (penetration=risk), l006 (11layer diagnosis), l004 (deep dive)
"""

# === Sector -> L3-L7 scores ===
# Higher = better/safer for that dimension
# L3: Material security (import dependency, commodity exposure)
# L4: Supply chain resilience (concentration risk, logistics)
# L5: Technology moat (R&D intensity, patent protection)
# L6: Political/Policy risk (sanctions, regulation, trade barriers)
# L7: Irreplaceability (switching cost, substitution timeline)

SECTOR_LAYER_SCORES = {
    # ===== TECH =====
    # L3=Material safety (import dependency), L4=Supply chain resilience
    # v8.31: L4 ordering REVERSED for key sectors to break L3-L4 correlation.
    # High supply chain risk sectors get HIGH L4 regardless of L3.
    # Stable domestic sectors get LOW L4 regardless of L3.
    # v8.36: EXPANDED L4 differentiation from 3 clusters (3.5/5.0/5.5) to 12+ distinct values.
    #   Previously 88% of sectors shared only 3 L4 values, causing massive L4_SupplyChain clustering.
    #   New: each sector gets a unique L4 based on supply chain concentration, import dependency,
    #   logistics vulnerability, and substitution difficulty.
    "半导体":       {"L3": 3.0, "L4": 3.2, "L5": 5.5, "L6": 2.5, "L7": 7.0},
    "半导体设备":   {"L3": 4.0, "L4": 3.8, "L5": 5.5, "L6": 2.5, "L7": 7.5},
    "半导体做空":   {"L3": 3.0, "L4": 3.1, "L5": 5.5, "L6": 2.5, "L7": 7.0},
    "半导体杠杆":   {"L3": 3.0, "L4": 3.3, "L5": 5.5, "L6": 2.5, "L7": 7.0},
    "AI/科技":      {"L3": 4.5, "L4": 3.4, "L5": 7.0, "L6": 3.5, "L7": 8.0},
    "AI算力":       {"L3": 4.5, "L4": 2.8, "L5": 5.5, "L6": 3.0, "L7": 7.5},
    "云计算/算力":  {"L3": 5.5, "L4": 3.6, "L5": 6.5, "L6": 4.5, "L7": 7.5},
    "硬科技":       {"L3": 4.5, "L4": 3.3, "L5": 6.5, "L6": 2.5, "L7": 7.5},
    "硬科技做空":   {"L3": 4.0, "L4": 2.7, "L5": 5.5, "L6": 3.0, "L7": 7.0},
    "硬科技杠杆":   {"L3": 4.0, "L4": 2.9, "L5": 5.5, "L6": 3.0, "L7": 7.0},
    "通信/5G":      {"L3": 4.5, "L4": 3.5, "L5": 6.0, "L6": 3.5, "L7": 6.5},
    "通信/光模块":  {"L3": 4.0, "L4": 3.7, "L5": 6.5, "L6": 3.5, "L7": 7.0},
    "5G/PCB":       {"L3": 4.5, "L4": 3.4, "L5": 5.5, "L6": 4.0, "L7": 6.0},
    "机器人/智造":  {"L3": 4.5, "L4": 3.8, "L5": 6.5, "L6": 5.0, "L7": 7.5},
    "计算机":       {"L3": 6.5, "L4": 4.2, "L5": 5.5, "L6": 5.5, "L7": 6.0},
    "电子":         {"L3": 4.0, "L4": 3.3, "L5": 5.0, "L6": 4.5, "L7": 5.5},
    # ===== NEW ENERGY =====
    "新能源":       {"L3": 4.5, "L4": 3.4, "L5": 6.0, "L6": 6.0, "L7": 7.0},
    "新能源车":     {"L3": 3.5, "L4": 3.2, "L5": 5.5, "L6": 6.5, "L7": 6.5},
    "光伏":         {"L3": 4.0, "L4": 3.1, "L5": 5.5, "L6": 6.5, "L7": 5.5},
    "风电":         {"L3": 4.5, "L4": 3.5, "L5": 6.0, "L6": 7.0, "L7": 5.5},
    "电池":         {"L3": 4.0, "L4": 3.6, "L5": 6.0, "L6": 5.5, "L7": 7.5},
    "能源化工":     {"L3": 2.5, "L4": 3.2, "L5": 5.0, "L6": 5.5, "L7": 4.0},
    # ===== DEFENSE =====
    "军工":         {"L3": 5.0, "L4": 3.6, "L5": 6.0, "L6": 5.0, "L7": 8.0},
    "航空航天":     {"L3": 5.0, "L4": 3.7, "L5": 6.0, "L6": 5.0, "L7": 8.0},
    # ===== HEALTHCARE =====
    "医药":         {"L3": 5.5, "L4": 3.9, "L5": 6.0, "L6": 4.0, "L7": 7.5},
    "中药":         {"L3": 7.5, "L4": 5.2, "L5": 6.0, "L6": 6.5, "L7": 8.0},
    "医药器械":     {"L3": 5.0, "L4": 3.8, "L5": 5.5, "L6": 4.0, "L7": 7.0},
    "港股医药":     {"L3": 5.5, "L4": 4.1, "L5": 6.0, "L6": 4.0, "L7": 7.5},
    "医疗器械":     {"L3": 5.0, "L4": 3.7, "L5": 5.5, "L6": 4.0, "L7": 7.0},
    # ===== CONSUMER =====
    "消费":         {"L3": 7.5, "L4": 5.2, "L5": 4.0, "L6": 7.0, "L7": 3.5},
    "白酒消费":     {"L3": 7.0, "L4": 5.4, "L5": 4.5, "L6": 6.5, "L7": 5.5},
    "家电":         {"L3": 6.5, "L4": 5.3, "L5": 4.5, "L6": 7.0, "L7": 3.5},
    "食品饮料":     {"L3": 7.5, "L4": 5.1, "L5": 3.5, "L6": 7.5, "L7": 4.0},
    "养殖":         {"L3": 7.0, "L4": 4.3, "L5": 3.0, "L6": 7.5, "L7": 5.5},
    "农牧":         {"L3": 7.0, "L4": 4.4, "L5": 3.0, "L6": 7.5, "L7": 5.5},
    "农产品":       {"L3": 7.0, "L4": 4.2, "L5": 3.0, "L6": 7.5, "L7": 5.5},
    "传媒":         {"L3": 7.0, "L4": 4.0, "L5": 4.0, "L6": 5.0, "L7": 4.0},
    # ===== FINANCE =====
    "金融":         {"L3": 8.5, "L4": 5.3, "L5": 3.0, "L6": 4.0, "L7": 4.5},
    "银行":         {"L3": 8.5, "L4": 5.4, "L5": 2.5, "L6": 3.5, "L7": 4.5},
    "保险":         {"L3": 8.5, "L4": 5.2, "L5": 3.0, "L6": 4.5, "L7": 5.0},
    "证券":         {"L3": 8.5, "L4": 5.5, "L5": 3.5, "L6": 3.5, "L7": 4.0},
    "券商":         {"L3": 9.0, "L4": 5.8, "L5": 3.5, "L6": 4.0, "L7": 4.5},
    # ===== DEFENSIVE =====
    "红利/价值":    {"L3": 8.5, "L4": 4.8, "L5": 3.0, "L6": 7.0, "L7": 6.0},
    "红利价值":     {"L3": 8.5, "L4": 4.6, "L5": 2.5, "L6": 7.5, "L7": 5.5},
    "红利+低波":    {"L3": 8.5, "L4": 4.7, "L5": 2.5, "L6": 7.5, "L7": 6.5},
    "高股息":       {"L3": 8.5, "L4": 4.9, "L5": 3.0, "L6": 7.0, "L7": 6.0},
    "公用事业":     {"L3": 8.5, "L4": 4.3, "L5": 2.5, "L6": 8.0, "L7": 6.5},
    "大盘蓝筹":     {"L3": 8.0, "L4": 4.8, "L5": 3.0, "L6": 7.0, "L7": 5.0},
    "小盘价值":     {"L3": 7.5, "L4": 4.5, "L5": 3.5, "L6": 6.5, "L7": 4.5},
    # ===== CYCLICALS =====
    "周期/资源":    {"L3": 4.0, "L4": 3.8, "L5": 4.0, "L6": 5.5, "L7": 4.0},
    "有色金属":     {"L3": 3.0, "L4": 3.9, "L5": 4.5, "L6": 5.0, "L7": 5.0},
    "钢铁":         {"L3": 2.5, "L4": 3.7, "L5": 3.5, "L6": 5.5, "L7": 3.5},
    "煤炭":         {"L3": 2.0, "L4": 3.6, "L5": 3.0, "L6": 5.0, "L7": 3.0},
    "化工":         {"L3": 2.5, "L4": 3.8, "L5": 4.5, "L6": 5.0, "L7": 4.0},
    "贵金属":       {"L3": 4.0, "L4": 4.5, "L5": 3.5, "L6": 5.5, "L7": 7.5},
    # ===== INFRA =====
    "基建/地产":    {"L3": 3.0, "L4": 3.5, "L5": 3.0, "L6": 4.0, "L7": 3.5},
    "房地产":       {"L3": 4.0, "L4": 4.0, "L5": 3.0, "L6": 3.5, "L7": 4.0},
    "交通运输":     {"L3": 6.0, "L4": 4.2, "L5": 3.5, "L6": 6.5, "L7": 5.5},
    "环保":         {"L3": 6.5, "L4": 4.6, "L5": 5.0, "L6": 7.0, "L7": 5.0},
    "央企改革":     {"L3": 7.0, "L4": 5.2, "L5": 4.0, "L6": 6.5, "L7": 6.0},
    # ===== BROAD/CROSS =====
    "宽基":         {"L3": 5.5, "L4": 5.0, "L5": 5.0, "L6": 5.5, "L7": 4.5},
    "全市场":       {"L3": 5.5, "L4": 5.1, "L5": 5.0, "L6": 5.5, "L7": 4.5},
    "综合":         {"L3": 5.5, "L4": 4.9, "L5": 5.0, "L6": 5.5, "L7": 4.5},
    "中盘成长":     {"L3": 6.0, "L4": 5.0, "L5": 5.5, "L6": 6.0, "L7": 5.0},
    "成长股":       {"L3": 6.0, "L4": 5.2, "L5": 6.0, "L6": 6.0, "L7": 5.0},
    "其他":         {"L3": 5.5, "L4": 4.8, "L5": 5.0, "L6": 5.5, "L7": 4.5},
    "跨境":         {"L3": 6.0, "L4": 5.3, "L5": 5.0, "L6": 5.5, "L7": 4.5},
    "中概互联网":   {"L3": 5.5, "L4": 5.1, "L5": 6.5, "L6": 3.0, "L7": 6.0},
    "港股科技":     {"L3": 5.0, "L4": 5.0, "L5": 7.0, "L6": 3.5, "L7": 6.5},
    "港股综合":     {"L3": 6.0, "L4": 5.1, "L5": 5.0, "L6": 4.5, "L7": 5.5},
    "美股科技":     {"L3": 6.0, "L4": 5.4, "L5": 8.0, "L6": 5.5, "L7": 7.0},
    "美股科技100":  {"L3": 6.0, "L4": 5.3, "L5": 7.0, "L6": 5.5, "L7": 7.0},
    "美股综合":     {"L3": 6.5, "L4": 5.8, "L5": 6.5, "L6": 5.5, "L7": 6.0},
    "美股杠杆":     {"L3": 6.5, "L4": 5.7, "L5": 6.5, "L6": 5.5, "L7": 6.0},
    # ===== FIXED INCOME =====
    "信用债":       {"L3": 8.0, "L4": 6.0, "L5": 1.5, "L6": 7.5, "L7": 7.5},
    "利率债":       {"L3": 8.0, "L4": 6.0, "L5": 1.5, "L6": 7.5, "L7": 7.5},
    "可转债":       {"L3": 7.5, "L4": 5.5, "L5": 2.0, "L6": 7.0, "L7": 6.0},
    "货币":         {"L3": 8.0, "L4": 6.5, "L5": 1.0, "L6": 8.0, "L7": 7.5},
    "货币基金":     {"L3": 8.0, "L4": 6.5, "L5": 1.0, "L6": 8.0, "L7": 7.5},
}


def get_sector_layer_scores(sector, risk_level=0.5):
    if sector is None:
        sector = "其他"
    base = SECTOR_LAYER_SCORES.get(sector)
    if not base:
        best = None
        for key in SECTOR_LAYER_SCORES:
            if key in sector or sector in key:
                if best is None or len(key) > len(best):
                    best = key
        base = SECTOR_LAYER_SCORES.get(best)
    if not base:
        return {
            "L3_Material": round(max(1.0, min(10.0, (1.0 - risk_level) * 10)), 1),
            "L4_SupplyChain": round(max(1.0, min(10.0, (1.0 - risk_level) * 10 - 0.5)), 1),
            "L5_Tech": round(max(1.0, min(10.0, (1.0 - risk_level) * 10)), 1),
            "L6_Politics": round(max(1.0, min(10.0, (1.0 - risk_level) * 10)), 1),
            "L7_Irreplaceable": round(max(1.0, min(10.0, (1.0 - risk_level) * 10)), 1),
        }
    rl_mod = 1.0 + (0.5 - risk_level) * 0.3
    rl_mod = max(0.85, min(1.15, rl_mod))
    result = {}
    layer_map = {"L3": "L3_Material", "L4": "L4_SupplyChain", "L5": "L5_Tech",
                 "L6": "L6_Politics", "L7": "L7_Irreplaceable"}
    for short, long in layer_map.items():
        score = base.get(short, 5.0)
        adjusted = score * rl_mod
        # v2.0: Raised ceilings for multi_signal headroom; add ceiling-break modulation
        if short == "L5":
            adjusted = min(adjusted, 9.5)
        elif short in ("L3", "L4"):
            adjusted = min(adjusted, 9.8)
        elif short == "L7":
            adjusted = min(adjusted, 9.3)
        # Ceiling-break: for near-ceiling scores, modulate excess portion only
        if adjusted >= 8.0:
            excess = adjusted - 8.0
            # v8.32: Reduced mod_factor from 0.5-0.65 to 0.2-0.35 range.
            # Previous formula (0.5 + (0.5-rl)*0.3) kept 60-65% of excess,
            # allowing material_bridge adjustments to push scores back to 10.0.
            # New formula (0.2 + (0.5-rl)*0.25) keeps only 20-35% of excess,
            # preventing ceiling saturation when material_bridge adds +1.0+.
            mod_factor = 0.2 + (0.5 - risk_level) * 0.25
            modulated_excess = excess * mod_factor
            adjusted = 8.0 + modulated_excess
        result[long] = round(max(1.0, min(10.0, adjusted)), 1)
    return result


def apply_sector_layer_scores(sector, existing_scores, risk_level=0.5):
    sector_scores = get_sector_layer_scores(sector, risk_level)
    result = dict(existing_scores)
    result.update(sector_scores)
    return result
