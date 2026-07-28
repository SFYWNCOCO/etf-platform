"""Comprehensive diagnostic: scan all ETFs and find distortion patterns."""
import sys
sys.path.insert(0, 'src')
from collections import Counter
from etf_platform.pipeline import batch_full
from etf_platform.config_loader import load_etfs

# Suppress stdout noise from akshare
class NullWriter:
    def write(self, s): pass
    def flush(self): pass

old_stdout = sys.stdout
sys.stdout = NullWriter()

results = batch_full(limit=100, live=False)
sys.stdout = old_stdout

# Collect layer distributions
layer_dist = {}
for r in results:
    ls = r.get('layer_scores', {})
    for k, v in ls.items():
        if isinstance(v, (int, float)):
            layer_dist.setdefault(k, []).append(v)

print("=== LAYER DISTRIBUTIONS ===")
for k in sorted(layer_dist.keys()):
    vals = layer_dist[k]
    unique = Counter(vals)
    print(f"\n{k}: unique={len(unique)}, range=[{min(vals):.1f}-{max(vals):.1f}], count={len(vals)}")
    for v, c in sorted(unique.items()):
        pct = c/len(vals)*100
        print(f"  {v:8.1f} x{c:3d} ({pct:5.1f}%)")

# Check for dead layers (range < 1.0)
print("\n=== DEAD LAYER CHECK (range < 1.0) ===")
for k in sorted(layer_dist.keys()):
    vals = layer_dist[k]
    rng = max(vals) - min(vals)
    if rng < 1.0:
        print(f"  {k}: range={rng:.1f} [DEAD]")

# Check material_bridge data
print("\n=== MATERIAL BRIDGE ANALYSIS ===")
from etf_platform.analysis.material_bridge import material_layer_adjustments_cached
sample_codes = [r['etf_code'] for r in results[:20]]
zero_count = 0
nonzero_count = 0
for code in sample_codes:
    adj = material_layer_adjustments_cached(code)
    has_nonzero = any(abs(v) > 0.001 for v in adj.values())
    if has_nonzero:
        nonzero_count += 1
    else:
        zero_count += 1
print(f"  Zero-adjustment ETFs: {zero_count}/{len(sample_codes)}")
print(f"  Non-zero-adjustment ETFs: {nonzero_count}/{len(sample_codes)}")

# Check scale defaults
print("\n=== SCALE DEFAULT CHECK ===")
etfs = load_etfs()
no_scale = 0
has_scale = 0
for code, info in list(etfs.items())[:50]:
    scale = info.get('scale', 0)
    if scale == 0:
        no_scale += 1
    else:
        has_scale += 1
print(f"  No scale (0): {no_scale}, Has scale: {has_scale}/50")

# Check holding_count defaults
print("\n=== HOLDING_COUNT DEFAULT CHECK ===")
no_hc = 0
has_hc = 0
for code, info in list(etfs.items())[:50]:
    hc = info.get('holding_count', 0)
    if hc == 0:
        no_hc += 1
    else:
        has_hc += 1
print(f"  No holding_count (0): {no_hc}, Has holding_count: {has_hc}/50")

# Check sector distribution
print("\n=== SECTOR DISTRIBUTION ===")
sector_counts = Counter()
for info in etfs.values():
    s = info.get('sector', 'unknown')
    sector_counts[s] += 1
for s, c in sector_counts.most_common(20):
    print(f"  {s}: {c}")

# Check L10/L11 for non-consumer sectors
print("\n=== L10/L11 SECTOR FALLBACK CHECK ===")
from etf_platform.analysis.demand import B2B_DEMAND_CLIMATE, B2B_SECTOR_RISK
sectors = set(info.get('sector', '') for info in etfs.values())
covered_b2b = 0
covered_risk = 0
uncovered = []
for s in sorted(sectors):
    if s in B2B_DEMAND_CLIMATE:
        covered_b2b += 1
    elif s in B2B_SECTOR_RISK:
        covered_risk += 1
    else:
        uncovered.append(s)
print(f"  Covered in B2B_DEMAND: {covered_b2b}, Covered in B2B_RISK: {covered_risk}")
print(f"  Uncovered sectors ({len(uncovered)}): {uncovered}")

# Check L8 capital flow for live=False fixed values
print("\n=== L8 CAPITAL FLOW CHECK ===")
l8_vals = layer_dist.get('L8_CapitalFlow', [])
if l8_vals:
    unique_l8 = Counter(l8_vals)
    print(f"  L8 unique values: {len(unique_l8)}, range=[{min(l8_vals):.1f}-{max(l8_vals):.1f}]")
    for v, c in sorted(unique_l8.items()):
        pct = c/len(l8_vals)*100
        print(f"  {v:8.1f} x{c:3d} ({pct:5.1f}%)")
