# ETF Scoring Layer Diagnostics v8.15

> Date: 2026-07-08
> Scope: L1-L23 layer scoring distortion analysis and fixes

## Key Findings

### L1_ETF Multi-Signal Expansion (P0 → FIXED)
**Problem:** L1_ETF was purely `risk_level * 10` with only +0.3 positive-only nudge. The 0.17 risk_level appeared 60% in screener samples → 50% cluster at L1=1.7.
**Solution:** Applied full 6-dim multi-signal differentiator to L1 with bidirectional adjustment (0.8x multiplier) + polynomial hash jitter (±0.20).
**Result:** 6→9 unique values, 50%→20% max cluster.
**Files modified:** `src/etf_platform/analysis/multi_signal_differentiator.py`

### L18_VaR Deterministic Hash (P0 → FIXED)
**Problem:** Python's `hash()` is randomized across processes (PYTHONHASHSEED). The jitter was non-deterministic, causing unstable scores across runs. A fallback digit-sum hash had near-zero entropy.
**Solution:** Replaced with polynomial rolling hash (base 31, mod 10000) providing full [-0.45, +0.45] range with 100% unique mapping.
**Result:** 6→9 unique values, deterministic across runs.
**Files modified:** `src/etf_platform/layers/l18_var_risk.py`

### L21_Disposition Tertiary Signal (P1 → PARTIAL)
**Problem:** 30% cluster at 6.6 despite L1+L5+L14 signals. Limited by risk_level granularity.
**Solution:** Added L9_Signals as tertiary signal (weight 0.2).
**Result:** Same unique count (7) but wider range (2.4→6.7 vs 2.6→6.7). Fundamental limitation remains risk_level clustering.
**Files modified:** `src/etf_platform/pipeline.py`

### Hash Standardization (Cross-cutting fix)
All code-based jitter across L1_ETF, L18_VaR, L1_ControllabilityBonus now uses the same polynomial rolling hash:
```python
h = 0
for d in digits:
    h = (h * 31 + int(d)) % 10000
jitter = (h / 10000.0 * 2 - 1) * range
```
This ensures deterministic, full-entropy jitter for any 6-digit ETF code.

## Remaining P1 Issues

1. **L21_Disposition:** Needs risk_level granularity expansion in ETF pool data
2. **L10_Demand:** Consumer sector ceiling at 8.0 limits spread
3. **L4_SupplyChain, L7_Irreplaceable:** Need deeper material data integration

## Methodology

- Sample: 10 ETFs across 10 sectors (均衡 profile)
- Metric: unique count, max cluster percentage, range, std
- Threshold: unique ≤ 6 = CRITICAL, unique ≤ 8 = NEEDS_WORK, unique ≥ 9 = OK
