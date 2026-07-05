"""
layer_factors.py - L3-L7 industry-specific multipliers
======================================================
Breaks the "same risk_level = identical L3-L9" problem by applying
sector-archetype multipliers to each layer based on industry characteristics.

No API dependency - works purely from sector classification.
Applied AFTER base _score_from_risk but BEFORE material_bridge.
"""
import json, io
from pathlib import Path

# Sector -> {layer: multiplier} where 1.0 is neutral
# >1.0 = this sector gets a BUMP on this layer (e.g., tech sector -> L5 boosted)
# <1.0 = this sector gets a PENALTY on this layer (e.g., commodity sector -> L3 penalized)
FACTORS = {
    # L3=Material(资源依赖), L4=SupplyChain, L5=Tech, L6=Politics, L7=Irreplaceable
    "半导体":     {"L3": 0.85, "L4": 0.90, "L5": 1.08, "L6": 0.85, "L7": 1.10},
    "芯片":       {"L3": 0.85, "L4": 0.90, "L5": 1.08, "L6": 0.85, "L7": 1.10},
    "AI算力":     {"L3": 0.90, "L4": 0.95, "L5": 1.10, "L6": 0.95, "L7": 1.05},
    "硬科技":     {"L3": 0.90, "L4": 0.95, "L5": 1.10, "L6": 0.90, "L7": 1.05},
    "新能源":     {"L3": 0.75, "L4": 0.85, "L5": 1.05, "L6": 1.10, "L7": 0.85},
    "新能源车":   {"L3": 0.75, "L4": 0.85, "L5": 1.10, "L6": 1.05, "L7": 0.90},
    "光伏":       {"L3": 0.70, "L4": 0.85, "L5": 1.05, "L6": 1.15, "L7": 0.80},
    "风电":       {"L3": 0.80, "L4": 0.90, "L5": 1.05, "L6": 1.10, "L7": 0.85},
    "军工":       {"L3": 0.90, "L4": 0.80, "L5": 1.05, "L6": 0.75, "L7": 1.08},
    "红利/价值":  {"L3": 1.10, "L4": 1.05, "L5": 0.80, "L6": 1.05, "L7": 1.05},
    "红利+低波":  {"L3": 1.10, "L4": 1.05, "L5": 0.80, "L6": 1.05, "L7": 1.05},
    "红利价值":   {"L3": 1.10, "L4": 1.05, "L5": 0.80, "L6": 1.05, "L7": 1.05},
    "高股息":     {"L3": 1.10, "L4": 1.05, "L5": 0.80, "L6": 1.05, "L7": 1.05},
    "消费":       {"L3": 1.05, "L4": 1.00, "L5": 0.85, "L6": 0.95, "L7": 1.05},
    "医药":       {"L3": 0.95, "L4": 0.95, "L5": 1.08, "L6": 0.80, "L7": 1.10},
    "中药":       {"L3": 0.95, "L4": 0.95, "L5": 1.08, "L6": 0.80, "L7": 1.10},
    "金融":       {"L3": 1.10, "L4": 1.10, "L5": 0.75, "L6": 0.80, "L7": 1.05},
    "银行":       {"L3": 1.15, "L4": 1.10, "L5": 0.70, "L6": 0.80, "L7": 1.05},
    "保险":       {"L3": 1.10, "L4": 1.05, "L5": 0.75, "L6": 0.85, "L7": 1.10},
    "证券":       {"L3": 1.05, "L4": 1.05, "L5": 0.85, "L6": 0.75, "L7": 0.95},
    "券商":       {"L3": 1.05, "L4": 1.05, "L5": 0.85, "L6": 0.75, "L7": 0.95},
    # v6.2: Reduce 公用事业 L7 factor from 1.25 to 1.10 to prevent ceiling saturation.
    # 公用事业 base L7=9.5 * 1.25 = 11.875 -> clamped to 9.4.
    # New: 9.5 * 1.10 = 10.45 -> clamped to 9.4, but leaves more room for material_bridge.
    # Also reduce L3 from 1.10 to 1.05 to prevent L3 saturation.
    "公用事业":   {"L3": 1.05, "L4": 1.00, "L5": 0.70, "L6": 0.85, "L7": 1.10},
    "基建":       {"L3": 0.80, "L4": 0.85, "L5": 0.85, "L6": 1.05, "L7": 0.85},
    "房地产":     {"L3": 0.90, "L4": 0.95, "L5": 0.75, "L6": 0.75, "L7": 0.85},
    "有色金属":   {"L3": 0.75, "L4": 0.90, "L5": 0.85, "L6": 0.95, "L7": 0.90},
    "钢铁":       {"L3": 0.70, "L4": 0.90, "L5": 0.80, "L6": 0.95, "L7": 0.80},
    "煤炭":       {"L3": 0.65, "L4": 0.90, "L5": 0.75, "L6": 0.95, "L7": 0.85},
    "化工":       {"L3": 0.75, "L4": 0.85, "L5": 0.90, "L6": 0.95, "L7": 0.85},
    "贵金属":     {"L3": 0.80, "L4": 0.95, "L5": 0.85, "L6": 0.95, "L7": 0.95},
    "传媒":       {"L3": 1.10, "L4": 1.05, "L5": 0.85, "L6": 0.75, "L7": 0.95},
    "交通运输":   {"L3": 1.05, "L4": 0.95, "L5": 0.80, "L6": 0.95, "L7": 0.90},
    "环保":       {"L3": 1.05, "L4": 1.00, "L5": 0.85, "L6": 1.10, "L7": 0.90},
    "机器人":     {"L3": 0.90, "L4": 0.95, "L5": 1.10, "L6": 0.95, "L7": 1.10},
    "通信":       {"L3": 0.95, "L4": 0.95, "L5": 1.05, "L6": 0.85, "L7": 1.00},
    "计算机":     {"L3": 1.05, "L4": 1.00, "L5": 1.05, "L6": 0.90, "L7": 1.00},
    "半导体设备": {"L3": 0.85, "L4": 0.90, "L5": 1.00, "L6": 0.85, "L7": 1.10},
    "半导体杠杆": {"L3": 0.85, "L4": 0.90, "L5": 1.08, "L6": 0.85, "L7": 1.10},
    "半导体做空": {"L3": 0.85, "L4": 0.90, "L5": 1.08, "L6": 0.85, "L7": 1.10},
    "硬科技杠杆": {"L3": 0.90, "L4": 0.95, "L5": 1.10, "L6": 0.90, "L7": 1.05},
    "硬科技做空": {"L3": 0.90, "L4": 0.95, "L5": 1.10, "L6": 0.90, "L7": 1.05},
    "宽基":       {"L3": 1.00, "L4": 1.00, "L5": 1.00, "L6": 1.00, "L7": 1.00},
    "全市场":     {"L3": 1.00, "L4": 1.00, "L5": 1.00, "L6": 1.00, "L7": 1.00},
    "其他":       {"L3": 1.00, "L4": 1.00, "L5": 1.00, "L6": 1.00, "L7": 1.00},
    "跨境":       {"L3": 1.00, "L4": 1.00, "L5": 1.00, "L6": 1.00, "L7": 1.00},
    "中概互联网": {"L3": 0.90, "L4": 0.90, "L5": 1.10, "L6": 0.80, "L7": 1.05},
    "港股科技":   {"L3": 0.90, "L4": 0.90, "L5": 1.10, "L6": 0.85, "L7": 1.05},
    "港股综合":   {"L3": 0.95, "L4": 0.95, "L5": 1.00, "L6": 0.90, "L7": 1.00},
    "美股科技":   {"L3": 0.90, "L4": 0.90, "L5": 1.15, "L6": 1.00, "L7": 1.15},
    "美股科技100":{"L3": 0.90, "L4": 0.90, "L5": 1.15, "L6": 1.00, "L7": 1.15},
    "美股综合":   {"L3": 0.95, "L4": 0.95, "L5": 1.05, "L6": 1.00, "L7": 1.05},
    "美股杠杆":   {"L3": 0.95, "L4": 0.95, "L5": 1.05, "L6": 1.00, "L7": 1.05},
    "货币":       {"L3": 1.10, "L4": 1.10, "L5": 0.60, "L6": 0.70, "L7": 1.00},
    "货币基金":   {"L3": 1.10, "L4": 1.10, "L5": 0.60, "L6": 0.70, "L7": 1.00},
    "信用债":     {"L3": 1.10, "L4": 1.10, "L5": 0.65, "L6": 0.75, "L7": 1.00},
    "利率债":     {"L3": 1.10, "L4": 1.10, "L5": 0.60, "L6": 0.70, "L7": 1.00},
    "可转债":     {"L3": 1.05, "L4": 1.05, "L5": 0.75, "L6": 0.80, "L7": 1.00},
}

def apply_factors(sector: str, base_scores: dict) -> dict:
    """Apply industry multipliers to L3-L7 scores."""
    factors = FACTORS.get(sector)
    if not factors:
        # Fuzzy match
        best = None
        for key in FACTORS:
            if key in sector or sector in key:
                if best is None or len(key) > len(best):
                    best = key
        factors = FACTORS.get(best, {"L3":1,"L4":1,"L5":1,"L6":1,"L7":1})

    layer_keys = ["L3_Material", "L4_SupplyChain", "L5_Tech", "L6_Politics", "L7_Irreplaceable"]
    factor_keys = ["L3", "L4", "L5", "L6", "L7"]

    adjusted = dict(base_scores)
    for lk, fk in zip(layer_keys, factor_keys):
        if lk in adjusted:
            mult = factors.get(fk, 1.0)
            adjusted[lk] = round(max(1.0, min(10.0, adjusted[lk] * mult)), 1)

    return adjusted

if __name__ == "__main__":
    # Test
    for s in ["半导体","新能源车","红利/价值","军工","金融"]:
        base = {"L3_Material": 6.0, "L4_SupplyChain": 6.0, "L5_Tech": 6.0, "L6_Politics": 6.0, "L7_Irreplaceable": 6.0}
        adj = apply_factors(s, base)
        print(f"{s:10s} L3:{adj['L3_Material']:.1f} L4:{adj['L4_SupplyChain']:.1f} L5:{adj['L5_Tech']:.1f} L6:{adj['L6_Politics']:.1f} L7:{adj['L7_Irreplaceable']:.1f}")
