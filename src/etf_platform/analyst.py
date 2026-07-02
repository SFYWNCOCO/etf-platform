"""analyst.py - Unified ETF analysis entry point.
Single call performs full analysis: penetration + rotation + macro + depth insight.
v2: integrates insight_engine for step-back, dual-argument, analogical, self-critique.
Papers: Gu/Kelly/Xiu 2024, Shapiro/Xu 2024, Chavez-Demoulin 2024"""
from .pipeline import run_full as _run_full
from .analysis.rotation import detect_rotation as _detect_rotation
from .analysis.insight import generate_insight_report
from .config_loader import load_etfs
from .scripts.dynamic_weights import load_dynamic_weights

PROFILES = {
    "conservative": {"supply": 0.45, "capital": 0.10, "signal": 0.05, "demand": 0.40, "label": "保守型"},
    "balanced":     {"supply": 0.35, "capital": 0.25, "signal": 0.10, "demand": 0.30, "label": "均衡型"},
    "aggressive":   {"supply": 0.20, "capital": 0.40, "signal": 0.20, "demand": 0.20, "label": "进取型"},
    "激进":     {"supply": 0.15, "capital": 0.45, "signal": 0.25, "demand": 0.15, "label": "激进型"},
}

PROFILE_ALIASES = {
    "conservative": "conservative", "defensive": "conservative",
    "保守": "conservative", "保守型": "conservative",
    "balanced": "balanced",
    "均衡": "balanced", "均衡型": "balanced",
    "aggressive": "aggressive",
    "进取": "aggressive", "进取型": "aggressive",
    "激进": "激进", "激进型": "激进",
    "进攻": "激进",
}

def _resolve_profile(profile: str) -> str:
    return PROFILE_ALIASES.get(profile, profile)
CONSUMER_SECTORS = {"消费","白酒","食品饮料","家电","医药","医疗","养殖","农牧","汽车","旅游","传媒"}

def analyse(code, profile="balanced", live=True, deep=True):
    """分析单个ETF"""
    result = _run_full(code, live=live)
    etfs = load_etfs()
    info = etfs.get(code, {})
    sector = info.get("sector", result.get("sector", "其他"))
    sector_type = "消费" if sector in CONSUMER_SECTORS else "B2B" if sector not in ("宽基","跨境") else "分散"
    result["sector"] = sector
    result["sector_type"] = sector_type
    # Cache rotation detection (avoid 592 API calls in batch)
    if not hasattr(analyse, "_rotation_cache"):
        analyse._rotation_cache = _detect_rotation()
    rotation = analyse._rotation_cache
    rot_signal = rotation.get("sectors", {}).get(sector, {})
    result["rotation_signal"] = rot_signal
    resolved = _resolve_profile(profile)
    pf = dict(PROFILES.get(resolved, PROFILES["balanced"]))
    try:
        dw = load_dynamic_weights(profile)
        if dw: pf.update({k: v for k, v in dw.items() if k in pf})
    except: pass
    result["profile"] = pf["label"]
    layers = result.get("layer_scores", {})
    exclude = {"L1_ETF", "L2_Holdings"}
    valid = {k: v for k, v in layers.items() if k not in exclude and isinstance(v, (int, float))}
    supply_layers = {"L3_Material","L4_SupplyChain","L5_Tech","L6_Politics","L7_Irreplaceable"}
    capital_layer = {"L8_CapitalFlow"}
    signal_layer = {"L9_Signals"}
    demand_layers = {"L10_Demand","L11_SectorRisk"}
    supply_score = sum(valid.get(k, 0) for k in supply_layers) / max(len(supply_layers & set(valid.keys())), 1)
    capital_score = valid.get("L8_CapitalFlow", 0)
    signal_score = valid.get("L9_Signals", 0)
    demand_score = sum(valid.get(k, 0) for k in demand_layers) / max(len(demand_layers & set(valid.keys())), 1)
    composite = (supply_score * pf["supply"] + capital_score * pf["capital"] +
                 signal_score * pf["signal"] + demand_score * pf["demand"])
    result["composite_score"] = round(composite, 2)
    result["supply_score"] = round(supply_score, 1)
    result["capital_score"] = round(capital_score, 1)
    result["signal_score"] = round(signal_score, 1)
    result["demand_score"] = round(demand_score, 1)
    if deep:
        try:
            etf_name = result.get("name", info.get("name", code))
            insight = generate_insight_report(
                etf_name=etf_name, code=code, sector=sector,
                composite_score=result["composite_score"],
                layer_scores=layers, rotation_signal=rot_signal or None,
                profile=pf["label"])
            result["insight"] = insight
        except Exception as e:
            result["insight"] = {"error": str(e), "synthesis": "洞察生成失败"}
    return result

def analyse_deep(code, profile="balanced", live=True):
    """快速深度分析"""
    return analyse(code, profile=profile, live=live, deep=True)
