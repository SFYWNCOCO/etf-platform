"""Diagnose pipeline bottleneck — systematically time every import and function call."""
import sys, time, traceback
sys.path.insert(0, r'D:\龙虾\.openclaw\etf-platform\src')

from etf_platform.config_loader import load_etfs

codes = ['510300', '512890', '588000']

for code in codes[:1]:  # Start with one ETF
    etfs = load_etfs()
    info = etfs.get(code, {})
    sector = info.get('sector', '未知行业')
    rl = info.get('risk_level', 0.5)
    name = info.get('name', code)
    etf_type = info.get('type', '')
    fee = info.get('fee', 0.005)
    is_cross = 'QDII' in etf_type or info.get('access') == 'qdii'

    print(f"\n{'='*60}")
    print(f"TESTING {code} {name} | sector={sector} risk={rl:.2f} type={etf_type} cross={is_cross}")
    print(f"{'='*60}\n")

    def safe_test(label, func, timeout=8):
        t0 = time.time()
        try:
            result = func()
            elapsed = time.time() - t0
            status = "OK" if elapsed < 2 else ("SLOW" if elapsed < timeout else "HANG")
            print(f"[{status:>4}] {label:35s} {elapsed:.3f}s")
            return elapsed
        except Exception as e:
            elapsed = time.time() - t0
            print(f"[ERR ] {label:35s} {elapsed:.3f}s -> {type(e).__name__}: {str(e)[:60]}")
            return -1

    # Module import tests
    print("=== MODULE IMPORT TIMINGS ===")
    import_modules = [
        'etf_platform.analysis.material_bridge',
        'etf_platform.analysis.layer_sector_scores',
        'etf_platform.analysis.multi_signal_differentiator',
        'etf_platform.analysis.l2_holdings_bridge',
        'etf_platform.analysis.demand',
        'etf_platform.analysis.chain',
        'etf_platform.analysis.layer_live_adjustments',
        'etf_platform.analysis.sector_flow_bridge',
        'etf_platform.analysis.political_risk',
        'etf_platform.layers.l12_macro_cycle',
        'etf_platform.layers.l13_factor_loading',
        'etf_platform.layers.l14_stoic_risk',
        'etf_platform.layers.l15_state_similarity',
        'etf_platform.layers.l16_live_signals',
        'etf_platform.layers.l17_quantitative_factor',
        'etf_platform.layers.l18_var_risk',
        'etf_platform.layers.l19_fx_channel',
        'etf_platform.layers.l20_option_volatility',
        'etf_platform.layers.l21_investment_psychology',
        'etf_platform.layers.l23_valuation',
        'etf_platform.analysis.dip_monitor',
        'etf_platform.enhance.l9_news',
        'etf_platform.enhance.l8_realtime',
    ]

    for mod_name in import_modules:
        safe_test(f'import {mod_name}', lambda: __import__(mod_name), timeout=10)

    print("\n=== FUNCTION CALL TIMINGS ===")

    from etf_platform.analysis.material_bridge import apply_to_layers
    safe_test('apply_to_layers', lambda: apply_to_layers(code, {}, sector))

    from etf_platform.analysis.layer_sector_scores import get_sector_layer_scores
    safe_test('get_sector_layer_scores', lambda: get_sector_layer_scores(sector, rl))

    from etf_platform.analysis.multi_signal_differentiator import differentiate
    safe_test('differentiate', lambda: differentiate(code, sector, {}, info))

    from etf_platform.analysis.l2_holdings_bridge import apply_l2_score
    safe_test('apply_l2_score', lambda: apply_l2_score(code, sector, {}, rl, fee))

    from etf_platform.analysis.demand import score_demand_climate, score_sector_demand_risk
    safe_test('score_demand_climate', lambda: score_demand_climate(sector, rl))
    safe_test('score_sector_demand_risk', lambda: score_sector_demand_risk(sector, rl))

    from etf_platform.analysis.macro_climate import apply_to_demand
    safe_test('apply_to_demand', lambda: apply_to_demand(sector, 5.0))

    from etf_platform.analysis.chain import evaluate_etf_risk
    safe_test('evaluate_etf_risk', lambda: evaluate_etf_risk(code))

    from etf_platform.analysis.layer_live_adjustments import apply_live_adjustments
    safe_test('apply_live_adjustments', lambda: apply_live_adjustments(sector, {}))

    from etf_platform.analysis.sector_flow_bridge import get_bridge
    safe_test('bridge.score()', lambda: get_bridge().score(sector, rl, etf_type, fee, code, False))

    from etf_platform.analysis.political_risk import calculate_political_risk_score
    safe_test('calculate_political_risk_score', lambda: calculate_political_risk_score(sector))

    from etf_platform.layers.l12_macro_cycle import score_cycle_layer
    safe_test('score_cycle_layer', lambda: score_cycle_layer(sector, rl))

    from etf_platform.layers.l13_factor_loading import score_factor_adjustment
    safe_test('score_factor_adjustment', lambda: score_factor_adjustment(sector))

    from etf_platform.layers.l14_stoic_risk import score_stoic_layer
    safe_test('score_stoic_layer', lambda: score_stoic_layer(sector, rl))

    from etf_platform.layers.l15_state_similarity import score_state_similarity
    safe_test('score_state_similarity', lambda: score_state_similarity(sector))

    from etf_platform.layers.l16_live_signals import get_live_signals
    safe_test('get_live_signals', lambda: get_live_signals(sector, is_cross))

    from etf_platform.layers.l17_quantitative_factor import apply_factor_layer
    safe_test('apply_factor_layer', lambda: apply_factor_layer(sector, {}))

    from etf_platform.layers.l18_var_risk import apply_var_layer
    safe_test('apply_var_layer', lambda: apply_var_layer(sector, {}))

    from etf_platform.layers.l19_fx_channel import apply_fx_layer
    safe_test('apply_fx_layer', lambda: apply_fx_layer(sector, {}, etf_type))

    from etf_platform.layers.l20_option_volatility import apply_option_layer
    safe_test('apply_option_layer', lambda: apply_option_layer(sector, {}))

    from etf_platform.layers.l21_investment_psychology import score_l21_layers as score_l21
    safe_test('score_l21_layers', lambda: score_l21(sector))

    from etf_platform.layers.l23_valuation import compute_valuation_layer
    safe_test('compute_valuation_layer', lambda: compute_valuation_layer(code, sector, name, info, rl))

    from etf_platform.analysis.dip_monitor import score_dip_layer
    safe_test('score_dip_layer', lambda: score_dip_layer(code=code, sector=sector, premium_pct=0.0, is_cross_border=is_cross))

    from etf_platform.enhance.l9_news import enhance_l9
    safe_test('enhance_l9', lambda: enhance_l9({'etf_code': code, 'layer_scores': {}, 'layers': {}}))

    from etf_platform.enhance.l8_realtime import enhance_l8
    safe_test('enhance_l8', lambda: enhance_l8({'etf_code': code, 'layer_scores': {}, 'layers': {}}))

    # Total run_full test
    print("\n=== FULL RUN TEST ===")
    from etf_platform.pipeline import run_full
    t0 = time.time()
    result = run_full(code, live=False)
    total = time.time() - t0
    print(f"run_full total: {total:.3f}s | score={result.get('score')}")
