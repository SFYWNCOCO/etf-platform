# ETF Platform Layer Research — v8.0 Findings

> Date: 2026-07-07 | Author: Cron Job (ETF scoring researcher)

## Executive Summary

This session focused on fixing L13_MacroCycle (P0), improving L15_StateSim and L17_Factor, and massively expanding L16_LiveSignals dictionaries. Two layers (L11 and L16) remain below std=1.0 threshold and require architectural changes.

## Changes Made

### L13_MacroCycle (P0 — Fixed)
- File: `src/etf_platform/layers/l12_macro_cycle.py`
- Rewrote fallback section with 25+ granular categories
- Previously: 军工, 医药, 红利/价值, 跨境, 高股息 all scored 6.0
- After: 军工=6.8, 医药=6.2, 红利/价值=5.8, 跨境=5.6, 高股息=5.8
- Std: 0.92 → 1.00 (now ✅ GOOD)

### L15_StateSim (P1 — Improved)
- File: `src/etf_platform/layers/l15_state_similarity.py`
- v6.3 formula: increased keyword multiplier (5.5→7.0), char_multiplier (2.5→3.5)
- Changed blend weights: 65% keyword + 35% char
- Std: 0.68 → 0.80 (still 🟡 but significant improvement)

### L17_Factor (P1 — Fixed)
- File: `src/etf_platform/layers/l17_quantitative_factor.py`
- Differentiated neutral sectors: 全市场, 宽基, 跨境, 其他
- Eliminated 5.0 cluster

### L16_LiveSignals (P1 — Expanded)
- File: `src/etf_platform/layers/l16_live_signals.py`
- SECTOR_PREMIUM_ESTIMATES: 50 → 100+ entries
- SECTOR_LIQUIDITY_ESTIMATES: 40 → 80+ entries
- FUND_QUALITY_MAP: 40 → 100+ entries
- Std: 0.64 → 0.65 (modest — needs architectural fix)

## Remaining Issues

### L11_SectorRisk (std=0.78)
- Root cause: Static dictionary lookup, formula doesn't amplify differences
- Needs architectural change (continuous scoring or secondary differentiator)
- **Needs human review**

### L16_LiveSignals (std=0.65)
- Root cause: Formula compression when live data unavailable
- Dictionary expansion helped but not enough
- **Needs human review**

## Verification

All changes verified with: `python batch_diverse.py --limit 30 --profile 均衡`
Results saved to: `data/scan_均衡_latest.json`
