"""Diagnose per-layer timing for run_full('510300')."""
import sys, time, logging
sys.path.insert(0, r"D:/龙虾/.openclaw/etf-platform/src")
logging.basicConfig(level=logging.WARNING)

from etf_platform.config_loader import load_etfs

def timer(label):
    start = time.time()
    def done():
        elapsed = time.time() - start
        return elapsed
    return done

etfs = load_etfs()
code = '510300'
info = etfs.get(code, {})
if not info:
    print(f"No ETF info for {code}")
    sys.exit(1)

rl = info.get("risk_level", 0.5)
sector = info.get("sector", "未知行业")
name = info.get("name", code)
print(f"ETF: {code} {name}, sector={sector!r}, risk={rl}")

scores = {
    "L1_ETF": 7.0, "L3_Material": 6.0, "L4_SupplyChain": 6.0, "L5_Tech": 6.0,
    "L6_Politics": 6.0, "L7_Irreplaceable": 6.0, "L8_CapitalFlow": 6.0, "L9_Signals": 6.0,
}
etf_type = info.get("type", "")
etf_fee = info.get("fee", 0.005)
is_cross = "QDII" in etf_type or info.get("access") == "qdii"

steps = [
    ("material_bridge", lambda: __import__("etf_platform.analysis.material_bridge", fromlist=["apply_to_layers"]).apply_to_layers(code, scores, sector)),
    ("layer_sector_scores", lambda: (lambda mod: scores.update(mod.get_sector_layer_scores(sector, rl)))(__import__("etf_platform.analysis.layer_sector_scores", fromlist=["get_sector_layer_scores"]))),
    ("differentiate", lambda: __import__("etf_platform.analysis.multi_signal_differentiator", fromlist=["differentiate"]).differentiate(code, sector, scores, info)),
    ("l2_holdings", lambda: __import__("etf_platform.analysis.l2_holdings_bridge", fromlist=["apply_l2_score"]).apply_l2_score(code, sector, scores, risk_level=rl, fee=etf_fee)),
    ("demand", lambda: (_ := __import__("etf_platform.analysis.demand", fromlist=["score_demand_climate", "score_sector_demand_risk"]), scores.update({"L10_Demand": _.score_demand_climate(sector, risk_level=rl).get("score", 5.0), "L11_SectorRisk": _.score_sector_demand_risk(sector, risk_level=rl).get("score", 5.0)}))),
    ("macro_climate", lambda: (__import__("etf_platform.analysis.macro_climate", fromlist=["apply_to_demand"]), scores.__setitem__("L10_Demand", __import__("etf_platform.analysis.macro_climate", fromlist=["apply_to_demand"]).apply_to_demand(sector, scores["L10_Demand"])))),
    ("chain", lambda: __import__("etf_platform.analysis.chain", fromlist=["evaluate_etf_risk"]).evaluate_etf_risk(code)),
    ("live_adjustments", lambda: __import__("etf_platform.analysis.layer_live_adjustments", fromlist=["apply_live_adjustments"]).apply_live_adjustments(sector, scores)),
    ("sector_flow_bridge", lambda: (_bridge := __import__("etf_platform.analysis.sector_flow_bridge", fromlist=["get_bridge"]).get_bridge(), _bridge.score(sector, risk_level=rl, etf_type=etf_type, fee=etf_fee, etf_code=code, live=False)), None),
    ("political_risk", lambda: scores.__setitem__("L12_PoliticalRisk", __import__("etf_platform.analysis.political_risk", fromlist=["calculate_political_risk_score"]).calculate_political_risk_score(sector).get("adjusted_score", 5.0))),
    ("L13_macro_cycle", lambda: scores.__setitem__("L13_MacroCycle", __import__("etf_platform.layers.l12_macro_cycle", fromlist=["score_cycle_layer"]).score_cycle_layer(sector, rl)["score"])),
    ("L13_factor_loading", lambda: (lambda adj: (scores.__setitem__(lyr, round(max(1.0, min(10.0, scores[lyr] + adj)), 1)), None) for lyr in ["L5_Tech", "L7_Irreplaceable"])(list(__import__("etf_platform.layers.l13_factor_loading", fromlist=["score_factor_adjustment"]).score_factor_adjustment(sector))[-1])),
    ("L14_stoic_risk", lambda: (lambda stoic: (scores.__setitem__("L14_StoicRisk", stoic["score"]), scores.__setitem__("L1_ControllabilityBonus", 0.5) if stoic.get("controllability", 5) >= 7 else None))(__import__("etf_platform.layers.l14_stoic_risk", fromlist=["score_stoic_layer"]).score_stoic_layer(sector, rl))),
    ("L15_state_similarity", lambda: scores.__setitem__("L15_StateSim", __import__("etf_platform.layers.l15_state_similarity", fromlist=["score_state_similarity"]).score_state_similarity(sector)["score"])),
    ("L16_live_signals", lambda: scores.__setitem__("L16_LiveSignals", __import__("etf_platform.layers.l16_live_signals", fromlist=["get_live_signals"]).get_live_signals(sector, is_cross_border=is_cross)["score"])),
    ("L17_quantitative_factor", lambda: __import__("etf_platform.layers.l17_quantitative_factor", fromlist=["apply_factor_layer"]).apply_factor_layer(sector, scores)),
    ("L18_var_risk", lambda: __import__("etf_platform.layers.l18_var_risk", fromlist=["apply_var_layer"]).apply_var_layer(sector, scores)),
    ("L19_fx_channel", lambda: __import__("etf_platform.layers.l19_fx_channel", fromlist=["apply_fx_layer"]).apply_fx_layer(sector, scores, info.get("type", ""))),
    ("L20_option_volatility", lambda: __import__("etf_platform.layers.l20_option_volatility", fromlist=["apply_option_layer"]).apply_option_layer(sector, scores)),
    ("L21_investment_psychology", lambda: (lambda p: (scores.__setitem__("L21_Behavior", p["score"]), scores.__setitem__("L21_BiasDetail", p.get("primary_bias", "unknown"))))(__import__("etf_platform.layers.l21_investment_psychology", fromlist=["score_l21_layers"]).score_l21_layers(sector))),
    ("L23_valuation", lambda: (lambda v: (scores.__setitem__("L23_Valuation", v["L23_Valuation"]), scores.__setitem__("L23_PENALTY", v["L23_PENALTY"])))(__import__("etf_platform.layers.l23_valuation", fromlist=["compute_valuation_layer"]).compute_valuation_layer(code, sector, name, info, risk_level=rl))),
    ("L24_dip_monitor", lambda: scores.__setitem__("L24_DipFlow", __import__("etf_platform.analysis.dip_monitor", fromlist=["score_dip_layer"]).score_dip_layer(code=code, sector=sector, premium_pct=0.0, is_cross_border=is_cross)["score"])),
    ("L9_news", lambda: (lambda r: scores.update(r.get("layer_scores", {})))((__import__("etf_platform.enhance.l9_news", fromlist=["enhance_l9"]).enhance_l9({"etf_code": code, "layer_scores": dict(scores), "layers": {}})))),
    ("L8_realtime", lambda: (lambda r: scores.update(r.get("layer_scores", {})))((__import__("etf_platform.enhance.l8_realtime", fromlist=["enhance_l8"]).enhance_l8({"etf_code": code, "layer_scores": dict(scores), "layers": {}})))),
]

total = time.time()
for label, func in steps:
    dt = timer(label)()
    try:
        result = func()
        print(f"{label}: {dt():.3f}s")
    except Exception as e:
        print(f"{label}: {dt():.3f}s  ERROR: {type(e).__name__}: {e}")

print(f"\nTOTAL: {time.time()-total:.3f}s")
