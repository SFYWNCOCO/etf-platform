# ETF Scoring Fix v8.29 — L9 Signal Expansion + L2 Ceiling Reduction

## Date: 2026-07-10

## Changes

### 1. L9_Signals Adjustment (P0 Fix)
**File:** `src/etf_platform/analysis/multi_signal_differentiator.py` line 316-318

**Before:**
```python
l9_adj = (type_signal * 0.2 + purity_signal * 0.2) * 0.5  # max ±0.11
```

**After:**
```python
l9_adj = combined * 1.5  # max ±1.5, using full 6-dim signal
```

**Impact:** L9 unique values: 5 → 31. L9 at 5.0: 83.6% → 2%.

### 2. L2_Holdings Ceiling Reduction (P1 Fix)
**File:** `src/etf_platform/analysis/l2_holdings_bridge.py` line 199-212

**Changes:**
- `rl_mod`: `(0.5 - risk_level) * 0.5` → `* 0.3`
- `fee_mod`: ±0.5 → ±0.3 (proportionally scaled)

**Impact:** L2 at >= 9.0: 27.7% → 0%.

### 3. L10/L11 Jitter Increase (P1 Fix)
**File:** `src/etf_platform/analysis/demand.py` line 336-361

**Changes:**
- L10 jitter: ±0.36 → ±0.8
- L11 jitter: ±0.45 → ±1.0

## Verification Results (50 ETFs, batch pipeline)

| Metric | Before | After |
|--------|--------|-------|
| L9 unique | 5 | 31 |
| L9 at 5.0 | 83.6% | 2% |
| L2 at >= 9.0 | 27.7% | 0% |
| L2 unique | 8 | 14 |
| L10 unique | 10 | 33 |
| L11 unique | 11 | 30 |

## Remaining P2 Issues (Not fixable in code)
- L1_ETF compression: 41.4% at risk_level=0.22 (requires config/etfs.yaml data fix)
- L1_ControllabilityBonus inherits L1 compression
