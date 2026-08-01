# Composite Score Architecture Issue

> Discovered: 2026-07-07 v8.5 | Severity: P1 | Status: Diagnosed

## Problem

The composite score is a simple arithmetic mean of 21 layer scores (each 0-10). This creates severe clustering:

- **50 ETFs**: 44 fall within [5.0, 5.9] composite range
- **Max cluster**: 9 ETFs tied at score=5.4
- **Range**: only 1.2 points (4.8 to 6.0)

## Root Cause

Central Limit Theorem effect: averaging 21 independent-ish random variables with mean ~5.5 and std ~1.0 produces a distribution with std ≈ 1.0/√21 ≈ 0.22. This compresses the effective range to ~0.8-1.2 points.

## Evidence

```
Composite score distribution (50 ETFs):
  5.4: 9 ETFs
  5.7: 6 ETFs  
  5.6: 5 ETFs
  5.5: 5 ETFs
  5.2: 5 ETFs
  5.9: 4 ETFs
  5.3: 4 ETFs
  ...
```

## Layer-Composite Correlation

| Layer | Correlation | Interpretation |
|-------|------------|----------------|
| L7_Irreplaceable | 0.544 | Strongest driver |
| L13_MacroCycle | 0.533 | Strong driver |
| L17_Factor | 0.490 | Moderate |
| L3_Material | 0.467 | Moderate |
| L19_FXChannel | 0.438 | Moderate |
| L16_LiveSignals | 0.301 | Weak |
| L5_Tech | 0.007 | Near-zero |
| L12_PoliticalRisk | -0.142 | Negative (works against ranking) |
| L20_OptionVol | -0.266 | Strongly negative |
| L1_ETF | -0.187 | Negative |

## Potential Solutions

1. **Weighted average** instead of simple mean — weight by layer std or correlation
2. **Percentile ranking** per layer before averaging — removes absolute scale issues
3. **Z-score normalization** per layer — ensures equal contribution
4. **Remove negative-correlation layers** from average — L20, L12, L1 actively hurt ranking

## Impact

- Rankings are noisy — small changes in input data can flip adjacent ETFs
- The 9-way tie at 5.4 means the top-ranked ETF isn't meaningfully better than the 8 tied below it
- Layer improvements (jitter, formula fixes) have diminishing returns on composite

## Next Steps

- P2: Implement weighted composite score using layer correlation weights
- P2: Consider z-score normalization per layer
- Monitor: Does weighted average improve ranking stability?
