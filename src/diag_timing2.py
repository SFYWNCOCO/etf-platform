"""Diagnostic: time each layer import/call step in run_full for 510300."""
import sys, time, logging
sys.path.insert(0, r"D:/龙虾/.openclaw/etf-platform/src")
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("timing")

def timer(label):
    start = time.time()
    print(f"\n--- START {label} ---")
    sys.stdout.flush()
    return lambda: print(f"--- END   {label}: {time.time()-start:.3f}s ---"), start

end_l23, t_l23 = timer("L23_valuation")
# But first let's just run with some prints
print("=" * 60)
print("Manually timing run_full('510300')")
print("=" * 60)
t0 = time.time()

# Step through layers manually matching pipeline.py
code = '510300'
etfs = {}
try:
    from etf_platform.config_loader import load_etfs
    etfs = load_etfs()
except Exception as e:
    print(f"load_etfs failed: {e}")
    etfs = {}

info = etfs.get(code, {})
if not info:
    print(f"No ETF info for {code}")
    sys.exit(1)

rl = info.get("risk_level", 0.5)
sector = info.get("sector", "未知行业")
name = info.get("name", code)
print(f"ETF: {code} {name}, sector={sector}, risk={rl}")

scores = {"L1_ETF": 7.0, "L3_Material": 6.0, "L4_SupplyChain": 6.0, "L5_Tech": 6.0,
          "L6_Politics": 6.0, "L7_Irreplaceable": 6.0, "L8_CapitalFlow": 6.0, "L9_Signals": 6.0}

# Material bridge
t = time.time(); 
try:
    from etf_platform.analysis.material_bridge import apply_to_layers
    scores = apply_to_layers(code, scores, sector)
    print(f"material_bridge: {time.time()-t:.3f}s")
except Exception as e:
    print(f"material_bridge fail: {time.time()-t:.3f}s {type(e).__name__}: {e}")

# layer_sector_scores
t = time.time()
try:
    from etf_platform.analysis.layer_sector_scores import get_sector_layer_scores
    sl = get_sector_layer_scores(sector, rl)
    scores.update(sl)
    print(f"layer_sector_scores: {time.time()-t:.3f}s")
except Exception as e:
    print(f"layer_sector_scores fail: {time.time()-t:.3f}s {type(e).__name__}: {e}")

# multi_signal_differentiator
t = time.time()
try:
    from etf_platform.analysis.multi_signal_differentiator import differentiate
    scores = differentiate(code, sector, scores, info)
    print(f"differentiate: {time.time()-t:.3f}s")
except Exception as e:
    print(f"differentiate fail: {time.time()-t:.3f}s {type(e).__name__}: {e}")

# L2 holdings
t = time.time()
try:
    from etf_platform.analysis.l2_holdings_bridge import apply_l2_score
    scores = apply_l2_score(code, sector, scores, risk_level=rl, fee=info.get("fee", 0.005))
    print(f"L2_holdings: {time.time()-t:.3f}s")
except Exception as e:
    print(f"L2_holdings fail: {time.time()-t:.3f}s {type(e).__name__}: {e}")

# demand
t = time.time()
try:
    from etf_platform.analysis.demand import score_demand_climate, score_sector_demand_risk
    l10 = score_demand_climate(sector, risk_level=rl)
    l11 = score_sector_demand_risk(sector, risk_level=rl)
    scores["L10_Demand"] = l10.get("score", 5.0)
    scores["L11_SectorRisk"] = l11.get("score", 5.0)
    print(f"demand: {time.time()-t:.3f}s")
except Exception as e:
    print(f"demand fail: {time.time()-t:.3f}s {type(e).__name__}: {e}")

# macro_climate
t = time.time()
try:
    from etf_platform.analysis.macro_climate import apply_to_demand
    scores["L10_Demand"] = apply_to_demand(sector, scores["L10_Demand"])
    print(f"macro_climate: {time.time()-t:.3f}s")
except Exception as e:
    print(f"macro_climate fail: {time.time()-t:.3f}s {type(e).__name__}: {e}")

# chain
t = time.time()
try:
    from etf_platform.analysis.chain import evaluate_etf_risk
    cr = evaluate_etf_risk(code)
    if cr and cr.get("score", 0) >= 2.0:
        penalty = min(cr["score"] * 0.2, 1.5)
        for layer in ["L3_Material", "L4_SupplyChain", "L5_Tech", "L6_Politics"]:
            scores[layer] = round(max(1.0, scores[layer] - penalty), 1)
    print(f"chain: {time.time()-t:.3f}s")
except Exception as e:
    print(f"chain fail: {time.time()-t:.3f}s {type(e).__name__}: {e}")

# live_adjustments
t = time.time()
try:
    from etf_platform.analysis.layer_live_adjustments import apply_live_adjustments
    scores = apply_live_adjustments(sector, scores)
    print(f"live_adjustments: {time.time()-t:.3f}s")
except Exception as e:
    print(f"live_adjustments fail: {time.time()-t:.3f}s {type(e).__name__}: {e}")

# sector_flow_bridge (L8/L9)
t = time.time()
try:
    from etf_platform.analysis.sector_flow_bridge import get_bridge
    bridge = get_bridge()
    etf_type = info.get("type", "")
    etf_fee = info.get("fee", 0.005)
    flow_scores = bridge.score(sector, risk_level=rl, etf_type=etf_type, fee=etf_fee, etf_code=code, live=True)
    scores["L8_CapitalFlow"] = flow_scores["L8"]
    scores["L9_Signals"] = flow_scores["L9"]
    print(f"sector_flow_bridge: {time.time()-t:.3f}s")
except Exception as e:
    print(f"sector_flow_bridge fail: {time.time()-t:.3f}s {type(e).__name__}: {e}")

# political_risk
t = time.time()
try:
    from etf_platform.analysis.political_risk import calculate_political_risk_score
    pr_info = calculate_political_risk_score(sector)
    scores["L12_PoliticalRisk"] = pr_info.get("adjusted_score", 5.0)
    print(f"political_risk: {time.time()-t:.3f}s")
except Exception as e:
    print(f"political_risk fail: {time.time()-t:.3f}s {type(e).__name__}: {e}")

# L13 MacroCycle
t = time.time()
try:
    from etf_platform.layers.l12_macro_cycle import score_cycle_layer
    cycle_info = score_cycle_layer(sector, rl)
    scores["L13_MacroCycle"] = cycle_info["score"]
    print(f"L13_macro_cycle: {time.time()-t:.3f}s")
except Exception as e:
    print(f"L13_macro_cycle fail: {time.time()-t:.3f}s {type(e).__name__}: {e}")

# L13 Factor loading
t = time.time()
try:
    from etf_platform.layers.l13_factor_loading import score_factor_adjustment
    factor_adj = score_factor_adjustment(sector)
    print(f"L13_factor_loading: {time.time()-t:.3f}s, factor_adj={factor_adj}")
except Exception as e:
    print(f"L13_factor_loading fail: {time.time()-t:.3f}s {type(e).__name__}: {e}")

# L14 Stoic Risk
t = time.time()
try:
    from etf_platform.layers.l14_stoic_risk import score_stoic_layer
    stoic = score_stoic_layer(sector, rl)
    scores["L14_StoicRisk"] = stoic["score"]
    print(f"L14_stoic_risk: {time.time()-t:.3f}s")
except Exception as e:
    print(f"L14_stoic_risk fail: {time.time()-t:.3f}s {type(e).__name__}: {e}")

# L15 State Similarity
t = time.time()
try:
    from etf_platform.layers.l15_state_similarity import score_state_similarity
    state = score_state_similarity(sector)
    scores["L15_StateSim"] = state["score"]
    print(f"L15_state_similarity: {time.time()-t:.3f}s")
except Exception as e:
    print(f"L15_state_similarity fail: {time.time()-t:.3f}s {type(e).__name__}: {e}")

# L16 Live Signals
t = time.time()
try:
    from etf_platform.layers.l16_live_signals import get_live_signals
    is_cross = "QDII" in info.get("type", "") or info.get("access") == "qdii"
    live = get_live_signals(sector, is_cross_border=is_cross)
    scores["L16_LiveSignals"] = live["score"]
    print(f"L16_live_signals: {time.time()-t:.3f}s")
except Exception as e:
    print(f"L16_live_signals fail: {time.time()-t:.3f}s {type(e).__name__}: {e}")

# L17 Quantitative Factor
t = time.time()
try:
    from etf_platform.layers.l17_quantitative_factor import apply_factor_layer
    scores = apply_factor_layer(sector, scores)
    print(f"L17_quantitative_factor: {time.time()-t:.3f}s")
except Exception as e:
    print(f"L17_quantitative_factor fail: {time.time()-t:.3f}s {type(e).__name__}: {e}")

# L18 VaR Risk
t = time.time()
try:
    from etf_platform.layers.l18_var_risk import apply_var_layer
    scores = apply_var_layer(sector, scores)
    print(f"L18_var_risk: {time.time()-t:.3f}s")
except Exception as e:
    print(f"L18_var_risk fail: {time.time()-t:.3f}s {type(e).__name__}: {e}")

# L19 FX Channel
t = time.time()
try:
    from etf_platform.layers.l19_fx_channel import apply_fx_layer
    scores = apply_fx_layer(sector, scores, info.get("type", ""))
    print(f"L19_fx_channel: {time.time()-t:.3f}s")
except Exception as e:
    print(f"L19_fx_channel fail: {time.time()-t:.3f}s {type(e).__name__}: {e}")

# L20 Option Volatility
t = time.time()
try:
    from etf_platform.layers.l20_option_volatility import apply_option_layer
    scores = apply_option_layer(sector, scores)
    print(f"L20_option_volatility: {time.time()-t:.3f}s")
except Exception as e:
    print(f"L20_option_volatility fail: {time.time()-t:.3f}s {type(e).__name__}: {e}")

# L21 Investment Psychology
t = time.time()
try:
    from etf_platform.layers.l21_investment_psychology import score_l21_layers as score_l21_layer
    psych_result = score_l21_layer(sector)
    scores["L21_Behavior"] = psych_result["score"]
    scores["L21_BiasDetail"] = psych_result.get("primary_bias", "unknown")
    print(f"L21_investment_psychology: {time.time()-t:.3f}s")
except Exception as e:
    print(f"L21_investment_psychology fail: {time.time()-t:.3f}s {type(e).__name__}: {e}")

# L23 Valuation Penalty Layer
t = time.time()
try:
    from etf_platform.layers.l23_valuation import compute_valuation_layer
    val_info = compute_valuation_layer(code, sector, name, info, risk_level=rl)
    scores["L23_Valuation"] = val_info["L23_Valuation"]
    scores["L23_PENALTY"] = val_info["L23_PENALTY"]
    print(f"L23_valuation: {time.time()-t:.3f}s")
except Exception as e:
    print(f"L23_valuation fail: {time.time()-t:.3f}s {type(e).__name__}: {e}")

# L24 DipFlow
t = time.time()
try:
    from etf_platform.analysis.dip_monitor import score_dip_layer
    dip_info = score_dip_layer(code=code, sector=sector, premium_pct=0.0, is_cross_border=False)
    scores["L24_DipFlow"] = dip_info["score"]
    print(f"L24_dip_monitor: {time.time()-t:.3f}s")
except Exception as e:
    print(f"L24_dip_monitor fail: {time.time()-t:.3f}s {type(e).__name__}: {e}")

# L9 News enhancement
t = time.time()
try:
    from etf_platform.enhance.l9_news import enhance_l9
    result = enhance_l9({"etf_code": code, "layer_scores": dict(scores), "layers": {}})
    scores.update(result.get("layer_scores", {}))
    print(f"L9_news: {time.time()-t:.3f}s")
except Exception as e:
    print(f"L9_news fail: {time.time()-t:.3f}s {type(e).__name__}: {e}")

# L8 Live enhancement
t = time.time()
try:
    from etf_platform.enhance.l8_realtime import enhance_l8
    result = enhance_l8({"etf_code": code, "layer_scores": dict(scores), "layers": {}})
    scores.update(result.get("layer_scores", {}))
    print(f"L8_realtime: {time.time()-t:.3f}s")
except Exception as e:
    print(f"L8_realtime fail: {time.time()-t:.3f}s {type(e).__name__}: {e}")

total_time = time.time() - t0
print(f"\n{'='*60}")
print(f"TOTAL: {total_time:.3f}s")
print(f"{'='*60}")
