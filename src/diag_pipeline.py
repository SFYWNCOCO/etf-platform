"""Diagnostic timing wrapper — adds timestamps to every layer in pipeline.run_full."""
import time
from etf_platform.pipeline import run_full

def timed_run(code="510300", live=False):
    t0 = time.time()
    print(f"[{t0:.2f}] START run_full({code}, live={live})")
    
    # Pre-layer timings
    stages = [
        "load_etfs",
        "initial_scores",
        "material_bridge",
        "layer_sector_scores",
        "multi_signal_differentiator",
        "l2_holdings_bridge",
        "demand",
        "chain",
        "layer_live_adjustments",
        "sector_flow_bridge",
        "political_risk",
        "l12_macro_cycle",
        "l13_factor_loading",
        "l14_stoic_risk",
        "l15_state_similarity",
        "l16_live_signals",
        "l17_quantitative_factor",
        "l18_var_risk",
        "l19_fx_channel",
        "l20_option_volatility",
        "l21_investment_psychology",
        "l23_valuation",
        "dip_monitor",
        "l9_news",
        "l8_realtime",
        "weighted_composite",
    ]
    
    # We'll patch run_full to log timing per stage by using monkey-patching approach
    # Actually simpler: just time the whole thing first, then test layers individually
    
    t_entry = time.time()
    result = run_full(code, live=live)
    total = time.time() - t_entry
    print(f"[{t_entry+total:.2f}] DONE total={total:.2f}s")
    return result, total

if __name__ == "__main__":
    result, total = timed_run("510300", live=False)
    print(f"\nScore: {result.get('score')}")
    print(f"Total time: {total:.2f}s")
