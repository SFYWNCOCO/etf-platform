# ETF Scoring Layer Diagnostic Report — 2026-07-08

> Cron job v8.8 · 45 ETFs across 10 sectors · 均衡 profile

## Summary

Three critical bugs fixed, two layers significantly improved:

| Layer | Before | After | Status |
|-------|--------|-------|--------|
| L1_ControllabilityBonus | 1 unique, all 5.5 | 13 unique, range [3.5,7.2] | ✅ FIXED |
| L18_VaR | 1 unique, all 1.0 | 12 unique, range [1.6,6.6] | ✅ FIXED |
| L19_FXChannel | 9 unique | 11 unique, range [2.5,8.8] | ✅ IMPROVED |

## Root Causes Identified

### 1. L1_ControllabilityBonus — Binary conditional bug
**File**: `pipeline.py` line ~181
**Bug**: `if controllability >= 7: score = 5.5` — all-or-nothing with hardcoded value.
**Fix**: Linear interpolation `3.5 + (cont - 3.0) / 6.5 * 4.0`

### 2. L18_VaR — Unit mismatch bug  
**File**: `l18_var_risk.py` calculate_var_score()
**Bug**: Piecewise formula used decimal thresholds (0.15, 0.25, 0.35) but `calculate_var()` returns percentage (15.0, 25.0, 35.0). All values fell into `else` branch → clamped to 1.0 → composite ≈ 1.2.
**Fix**: Corrected thresholds to percentage (15, 25, 35, else)

### 3. L19_FXChannel — Coarse score_base values
**File**: `l19_fx_channel.py`
**Issue**: 14 categories with many sharing same score_base (3.0×11, 5.0×8). 
**Fix**: Expanded to 22 categories with finer granularity, split 外资偏好 into 6 sub-categories.

## Remaining Issues

### P1: L12_PoliticalRisk — 22% at 5.0
Fallback to default 5.0 for unmapped sectors. Low-effort fix available.

### P1: Composite score range [4.5, 6.2] — 15 unique/45 ETFs
20 layers averaged together dilute signal. Consider weighted composite.

### P1: L7_Irreplaceable — Mean 6.3, 60% above 6.0
Inflationary bias. Needs differentiation expansion.

### P2: L18_VaR — 22% at single value 3.0
Multiple sectors map to same vol key (半导体→14 ETFs). Could add code-based jitter like L15/L16.

## Comparison: Before vs After (45 ETFs)

| Layer | Before Unique | After Unique | Before Range | After Range | Before StdDev | After StdDev |
|-------|-------------|-------------|-------------|------------|--------------|-------------|
| L1_ControllabilityBonus | 1 | 13 | [5.5,5.5] | [3.5,7.2] | 0.00 | 1.00 |
| L18_VaR | 1 | 12 | [1.0,1.0] | [1.6,6.6] | 0.00 | 1.23 |
| L19_FXChannel | 9 | 11 | [3.0,8.5] | [2.5,8.8] | 1.87 | 2.32 |
| L9_Signals | 32 | 33 | [3.2,8.9] | [3.2,8.9] | 1.42 | 1.43 |
| L8_CapitalFlow | 27 | 28 | [3.5,7.7] | [3.5,7.7] | 1.16 | 1.17 |
| L17_Factor | 29 | 29 | [2.9,7.8] | [2.9,7.8] | 1.08 | 1.08 |
| L15_StateSim | 25 | 25 | [4.1,8.1] | [4.1,8.1] | 0.91 | 0.91 |
| L13_MacroCycle | 25 | 25 | [3.9,8.4] | [3.9,8.4] | 1.00 | 1.00 |
| L4_SupplyChain | 25 | 25 | [2.1,9.0] | [2.1,9.0] | 1.61 | 1.61 |
| L6_Politics | 26 | 26 | [1.7,8.6] | [1.7,8.6] | 1.67 | 1.67 |
| L3_Material | 24 | 24 | [2.1,9.5] | [2.1,9.5] | 1.71 | 1.71 |
| L7_Irreplaceable | 24 | 24 | [3.9,8.5] | [3.9,8.5] | 1.48 | 1.48 |
| L16_LiveSignals | 23 | 23 | [4.5,8.4] | [4.5,8.4] | 0.98 | 0.98 |
| L5_Tech | 23 | 23 | [3.0,7.8] | [3.0,7.8] | 1.20 | 1.20 |
| L1_ETF | 22 | 22 | [1.0,6.7] | [1.0,6.7] | 1.34 | 1.34 |
| L14_StoicRisk | 17 | 17 | [2.1,9.0] | [2.1,9.0] | 1.52 | 1.52 |
| L10_Demand | 17 | 17 | [2.4,8.0] | [2.4,8.0] | 1.37 | 1.37 |
| L12_PoliticalRisk | 18 | 18 | [3.0,8.2] | [3.0,8.2] | 1.22 | 1.22 |
| L2_Holdings | 19 | 19 | [4.2,8.4] | [4.2,8.4] | 1.03 | 1.03 |
| L11_SectorRisk | 20 | 20 | [1.4,6.8] | [1.4,6.8] | 1.05 | 1.05 |
| L20_OptionVol | 15 | 16 | [3.1,7.5] | [3.1,7.5] | 1.14 | 1.10 |

## Pipeline Version
1.2.0
