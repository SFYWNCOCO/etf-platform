# L9 Floating-Point Ceiling Regression Fix v8.35

**Date:** 2026-07-10  
**Severity:** P0  
**Status:** Fixed

## Problem

L9_Signals=10.0 for 159516 (半导体设备ETF国泰) after v8.34 fix.

## Root Cause

Floating-point comparison bug in ceiling guards:

```python
headroom = 10.0 - 9.7  # = 0.3000000000000007, not exactly 0.3
if headroom <= 0.3:    # False! (float precision)
    adj = min(0.3, headroom - 0.1)
else:
    adj = 0.3          # Full adjustment applied
# 9.7 + 0.3 = 10.0 → clamped to 10.0
```

## Pipeline Trace for 159516

| Step | Component | L9 Value |
|------|-----------|----------|
| 1 | Initial (_score_from_risk) | 3.5 |
| 2 | sector_flow_bridge | 9.2 |
| 3 | multi_signal_differentiator | 9.2 (no change) |
| 4 | l17_factor (bullish momentum) | 9.7 (+0.5) |
| 5 | l19_fx (bullish FX) | **10.0** (+0.3, guard bypassed) |
| 6 | l9_news | 10.0 (already at ceiling) |

## Fix

**l19_fx_channel.py:** Always reserve 0.1 headroom regardless of magnitude:
```python
adj = min(0.3, headroom - 0.1) if headroom > 0.1 else 0.0
```

**l17_quantitative_factor.py:** Same pattern:
```python
adj = min(0.5, headroom - 0.1) if headroom > 0.1 else 0.0
```

## Lesson

Never use `<=` or `>=` with float comparisons for threshold guards. Either:
1. Use `round()` to normalize precision, OR
2. Always reserve headroom unconditionally (preferred — simpler and more robust)

## Files Modified

- `src/etf_platform/layers/l19_fx_channel.py`
- `src/etf_platform/layers/l17_quantitative_factor.py`
