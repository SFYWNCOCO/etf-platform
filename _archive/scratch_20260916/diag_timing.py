"""Instrument pipeline.py to measure per-module import/call times."""
import sys, time, logging, traceback

sys.path.insert(0, r"D:/龙虾/.openclaw/etf-platform/src")
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("timing")

from etf_platform.pipeline import run_full

# Patch run_full layer calls with timing via monkey-patching modules
import etf_platform.layers.l23_valuation as l23mod
orig_l23 = l23mod.compute_valuation_layer
def timed_l23(*a, **kw):
    t=time.time()
    try:
        r=orig_l23(*a, **kw)
        logger.info(f"L23_valuation took {time.time()-t:.3f}s")
        return r
    except Exception as e:
        logger.warning(f"L23 error in {time.time()-t:.3f}s: {e}")
        raise
l23mod.compute_valuation_layer = timed_l23

# Also patch other potentially slow modules
modules_to_check = [
    ("etf_platform.analysis.sector_flow_bridge", "get_bridge"),
    ("etf_platform.enhance.l9_news", "enhance_l9"),
    ("etf_platform.enhance.l8_realtime", "enhance_l8"),
    ("etf_platform.layers.l18_var_risk", "apply_var_layer"),
    ("etf_platform.layers.l17_quantitative_factor", "apply_factor_layer"),
]

for mod_path, func_name in modules_to_check:
    try:
        import importlib
        m = importlib.import_module(mod_path)
        orig = getattr(m, func_name)
        def make_timed(fn, label):
            def wrapped(*a, **kw):
                t=time.time()
                try:
                    r=fn(*a, **kw)
                    logger.info(f"{label} took {time.time()-t:.3f}s")
                    return r
                except Exception as e:
                    logger.warning(f"{label} error in {time.time()-t:.3f}s: {type(e).__name__}: {e}")
                    raise
            return wrapped
        setattr(m, func_name, make_timed(orig, func_name))
    except Exception as e:
        print(f"Could not patch {mod_path}.{func_name}: {e}")

# Time each major import step
print("=== Timing run_full('510300') ===")
t0 = time.time()
r = run_full('510300', skip_tournament=True) if hasattr(run_full.__wrapped__ if False else run_full, '__wrapped__') else run_full('510300')
total = time.time()-t0
print(f"Total: {total:.2f}s")
print(f"Sector: {r.get('sector')}")
print(f"Score: {r.get('score')}")
for k,v in sorted(r.get('layer_scores',{}).items()):
    print(f"  {k}: {v}")
