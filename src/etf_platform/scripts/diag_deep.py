"""Deep analysis: L1_ETF scale distortion and L7 saturation."""
import sys
sys.path.insert(0, 'src')
from etf_platform.pipeline import run_full
from etf_platform.config_loader import load_etfs
from collections import Counter

etfs = load_etfs()

# L1: Analyze scale_score calculation
print("=== L1_ETF SCALE SCORE ANALYSIS ===")
scale_scores = Counter()
for code, info in list(etfs.items())[:100]:
    scale = info.get('scale', 0)
    fee = info.get('fee', 0.005)
    risk_level = info.get('risk_level', 0.5)
    
    if scale > 0:
        ss = min(7.0, max(1.0, scale / 50.0))
    else:
        if fee > 0:
            base_score = max(1.0, min(10.0, 10.0 - (fee - 0.001) / 0.014 * 9.0))
        else:
            base_score = 5.0
        ss = base_score + (1.0 - risk_level) * 1.5
        ss = max(1.0, min(7.0, ss))
        ss = round(ss, 1)
    scale_scores[ss] += 1

for v, c in sorted(scale_scores.items()):
    print(f"  L1={v:.1f}: {c} ETFs")

# Show which ETFs have scale > 0
has_scale = [(c, i.get('scale')) for c, i in etfs.items() if i.get('scale', 0) > 0]
print(f"\n  ETFs with scale > 0: {len(has_scale)}")
for c, s in has_scale[:10]:
    print(f"    {c}: scale={s}")

# L7: Analyze why so many ETFs hit 9.4
print("\n=== L7 SATURATION ANALYSIS ===")
l7_at_94 = []
l7_below_94 = []
for code, info in list(etfs.items())[:100]:
    result = run_full(code, live=False)
    l7 = result['layer_scores'].get('L7_Irreplaceable', 0)
    sector = result['sector']
    if l7 >= 9.3:
        l7_at_94.append((code, sector, l7))
    else:
        l7_below_94.append((code, sector, l7))

print(f"  L7 >= 9.3: {len(l7_at_94)}")
for c, s, v in l7_at_94[:10]:
    print(f"    {c} ({s}): L7={v}")

print(f"  L7 < 9.3: {len(l7_below_94)}")

# L5: Same analysis
print("\n=== L5 SATURATION ANALYSIS ===")
l5_at_94 = []
for code, info in list(etfs.items())[:100]:
    result = run_full(code, live=False)
    l5 = result['layer_scores'].get('L5_Tech', 0)
    sector = result['sector']
    if l5 >= 9.3:
        l5_at_94.append((code, sector, l5))

print(f"  L5 >= 9.3: {len(l5_at_94)}")
for c, s, v in l5_at_94[:10]:
    print(f"    {c} ({s}): L5={v}")

# L3/L4 material_bridge: check if adjustments are actually applied
print("\n=== MATERIAL BRIDGE IMPACT ON L3/L4 ===")
from etf_platform.analysis.material_bridge import material_layer_adjustments_cached
for code in ['159995', '512660', '512880', '518880', '159131']:
    adj = material_layer_adjustments_cached(code)
    result = run_full(code, live=False)
    l3 = result['layer_scores']['L3_Material']
    l4 = result['layer_scores']['L4_SupplyChain']
    print(f"  {code}: adj={adj}, L3={l3}, L4={l4}")

# L10: Check keyword fallback behavior
print("\n=== L10 KEYWORD FALLBACK ANALYSIS ===")
from etf_platform.analysis.demand import B2B_DEMAND_CLIMATE, CONSUMER_SECTORS
sectors = set(info.get('sector', '') for info in etfs.values())
for s in sorted(sectors):
    is_cons = s in CONSUMER_SECTORS
    in_b2b = s in B2B_DEMAND_CLIMATE
    if not is_cons and not in_b2b:
        # Check keyword fallback
        if '军工' in s:
            fallback = 7.0
        elif '红利' in s or '价值' in s:
            fallback = 6.5
        elif '科技' in s or '计算机' in s or '通信' in s:
            fallback = 5.0
        elif '新能源' in s or '光伏' in s:
            fallback = 4.5
        else:
            fallback = 5.0
        print(f"  {s}: NOT in B2B, keyword fallback={fallback}")
