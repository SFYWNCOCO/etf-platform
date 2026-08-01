# L22_P21_Overreaction_Skew_Analysis_v826

> Date: 2026-07-09 | Status: Documented (P2, not code-fixed) | Severity: Medium

## Problem

L21_Overreaction shows extreme low-skew: 42% of 50 ETFs score ≤ 3.0.

## Root Cause Analysis

Formula in `pipeline.py` line ~434:
```python
l22_extreme = abs(l22 - 5.5) / 3.0  # normalize to [0, 1]
l20_amp = l20 / 10.0
raw = l22_extreme * (0.7 + 0.3 * l20_amp) * 9.0 + 1.0
```

**Issue 1: L22 range too narrow.** Observed L22 range is [3.0, 8.5] for 50 ETFs. The normalization divisor of 3.0 assumes L22 can reach [2.5, 8.5], but actual L22 rarely goes below 3.0 or above 8.5.

**Issue 2: Multiplier too aggressive.** The `* 9.0` multiplier combined with `+ 1.0` base creates a steep curve. Even moderate l22_extreme values (0.2-0.5) produce scores of 2.2-4.0.

**Issue 3: L20 amplification too weak.** `l20_amp` ranges [0.3, 0.8] contributing only 0.21-0.24 to the `(0.7 + 0.3*l20_amp)` factor.

## Data Evidence (50 ETFs)

| Metric | Value |
|--------|-------|
| Mean L21_Overreaction | 4.36 |
| Std | 2.43 |
| % ≤ 3.0 | 42% |
| % ≥ 7.0 | 12% |
| Unique values | 36 |
| L22 range | [1.7, 8.8] |

## Impact

- L21_Overreaction contributes to L21_Behavior (mean of 5 sub-scores)
- Low overreaction scores reduce behavioral diversity signal
- ETFs with extreme L22 (panic/euphoria) ARE captured (e.g., 562550 gets 9.8)
- But neutral-moderate ETFs all cluster at 1.8-3.0, losing differentiation

## Proposed Fix (not implemented — P2)

Option A: Reduce normalization divisor from 3.0 to 2.0, increasing sensitivity to moderate L22 deviations.
Option B: Add L9 signal strength as secondary driver (high signal density + moderate L22 = overreaction).
Option C: Use sigmoid mapping instead of linear for U-shape.

Requires testing with full 592-ETF dataset before implementation.
