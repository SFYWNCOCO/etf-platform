# L21 Behavioral Factor Ceiling Effects - Diagnosis & Fix

## Date: 2026-07-08
## Version: v8.14

## Problem Summary

Four L21 behavioral sub-factors and L12_PoliticalRisk exhibited severe ceiling/default-value clustering, reducing their discriminative power in composite scoring.

## L12_PoliticalRisk - Missing Sector Mappings

### Root Cause
6 sectors were completely missing from all 4 political risk mapping dictionaries:
- 港股综合, 能源化工, 美股科技100, 小盘价值, 红利/价值, 高股息

When all 4 dicts return defaults (0.5/50/50), composite = 0.5*0.4 + 0.5*0.3 + 0.5*0.2 + 0.5*0.1 = 0.5 → score = 5.0.

### Fix
Added all 6 sectors to REGULATORY_INTENSITY, GEOPOLITICAL_EXPOSURE, EPU_BY_SECTOR, GPR_BY_SECTOR with differentiated scores.

### Result
- Before: 6/30 ETFs at exact 5.0
- After: 1/30 at ceiling, range [2.9, 8.2], 23 unique values

## L21_Overreaction - Anchor Point Too Close to Mean

### Root Cause
Formula: `10 - abs(L20_OptionVol - 5.5) * 1.2`
Mean L20 = 5.53, anchor = 5.5. Mean absolute deviation = 0.96.
Mean overreaction = 10 - 0.96*1.2 = 8.85 → massive ceiling effect.
17/30 ETFs ≥ 9.0.

### Fix
Increased multiplier from 1.2 to 1.8.
New mean overreaction = 10 - 0.96*1.8 = 8.27.

### Result
- Range: [7.2, 9.9] → [5.1, 9.8]
- Mean: 8.84 → 8.09
- Unique: 15 → 19

## L21_Disposition - Insufficient Risk Coefficient

### Root Cause
Formula: `10 - (rl * 3.0 + max(0, 5-L5) * 1.0)`
Max rl penalty: 0.85*3.0 = 2.55. Too small to differentiate across risk levels.
Most rl values are low (0.1-0.3), giving penalties of 0.3-0.9.
Combined with L5 penalty (0-1.6), total penalty rarely exceeds 2.5.
Result: scores cluster [6.5, 9.5], mean 8.52.

### Fix
Increased rl multiplier from 3.0 to 5.0, L5 penalty from 1.0 to 1.5.
New max penalty: 0.85*5.0 + 1.6*1.5 = 6.65.
Min score: 10 - 6.65 = 3.35 (clamped to 0).

### Result
- Range: [6.5, 9.5] → [4.7, 9.1]
- Mean: 8.52 → 7.64
- Unique: 18 → 20

## L21_Herding - Formula Saturation

### Root Cause
Old formula: `10 - (L8+L9-10) * 1.5`
When L8+L9 ≤ 10, the subtraction becomes positive → score > 10 → capped at 10.
Many low-risk sectors have L8~3.5, L9~4.3 → sum=7.8 → 10+3.3 = 13.3 → capped at 10.
11/30 ETFs at ceiling 10.0.

### Fix
New formula: `10 - max(0, L8+L9-10)*1.0 - max(0, 10-L8-L9)*0.3`
Asymmetric gradient: high L8+L9 (crowded) penalizes -1.0/unit, low L8+L9 (uncrowded) adds +0.3/unit.
No longer saturates at 10 because the low-sum side only adds a small positive.

### Result
- Ceiling at 10: 11/30 → 1/30
- Mean: 6.63 → 7.53
- Range: [0, 10] → [3.0, 9.8]
- Unique: 19 → 21

## Files Modified
1. `src/etf_platform/analysis/political_risk.py` - Added 6 missing sectors to all 4 mappings
2. `src/etf_platform/pipeline.py` - Fixed L21_Overreaction, L21_Disposition, L21_Herding formulas

## Remaining Concerns
- L21_Overreaction still has mean 8.21, some ceiling clustering remains
- L21_Behavior composite (equal-weight average of 5 sub-factors) inherits sub-factor distributions
- Consider dynamic anchor points instead of hardcoded 5.5 for L20
