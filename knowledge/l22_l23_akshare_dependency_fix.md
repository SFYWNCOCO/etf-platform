# L22/L23 Akshare Dependency Bug

> Date: 2026-07-09 | Version: v8.19 | Priority: P0

## Problem

L22_Pendulum and L23_Micro are flatlined due to akshare data dependency.

### L22_Pendulum
- **Symptom:** unique=7, range=[4.5, 5.5], mean=5.00, std=0.34
- **Root cause:** `get_trend()` returns None → default chg20=0.0, vol=15.0, vr=1.0 → angle=0 → base_score=5.0 ± jitter(±0.45)
- **Cascade:** L21_Overreaction depends on L22 deviation from 5.5. With L22 stuck at ~5.0, overreaction formula produces range [1.0, 3.7] instead of [1.3, 10.0].

### L23_Micro
- **Symptom:** unique=1, range=[5.0, 5.0], always 5.0
- **Root cause:** `get_trend()` returns None → early return with default 5.0

### L20_OptionVol (similar)
- Also depends on akshare trend data
- Currently functional (range [2.4, 7.5]) but may degrade when akshare unavailable

## Fix Required

Implement sector-based fallback scoring for L22 and L23 when akshare data is unavailable:

1. **L22 fallback:** Use sector-level risk metrics (from SECTOR_DEMAND_RISK or B2B_SECTOR_RISK) to derive a pendulum angle proxy
2. **L23 fallback:** Use sector-level turnover/volume heuristics when kline data unavailable

## Workaround

For offline/testing, mock `get_trend()` to return synthetic data based on sector characteristics.
