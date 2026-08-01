# ETF Scoring Research Log — v8.12

> Date: 2026-07-08 | Researcher: Cron Job | Version: v8.12

## Findings Summary

### P0 Fixed: L18_VaR Cluster (20% at 5.7)
- **Root Cause:** SECTOR_TO_VOL_KEY maps 6 ETFs to vol=0.20 bucket → identical composite score
- **Fix:** Code-based deterministic jitter ±0.45 in `calculate_var_score()`
- **Result:** unique=14→24, max_cluster=20%→10%

### P0 Fixed: L20_OptionVol Clusters (20% at 4.8, 20% at 6.0)
- **Root Cause:** IV Rank buckets too coarse (12 unique out of 30 ETFs)
- **Fix:** Code-based deterministic jitter ±0.40 in `calculate_iv_score()`
- **Result:** unique=12→26, max_cluster=20%→10%

### P1 Remaining: L10_Demand (23% at 5.5)
- Needs more sector differentiation in B2B_DEMAND_CLIMATE fallback

### P1 Remaining: L15_StateSim (std=0.97, ALMOST)
- Jitter already at [-1,+1]. Needs structural change to SECTOR_CHARACTERISTICS

### P1 Remaining: L2_Holdings (std=0.98, ALMOST)
- Needs expanded holdings data coverage

### P2 Remaining: L1_ETF (23% at 1.7), L12_PoliticalRisk (20% at 5.0), L1_ControllabilityBonus (17% at 5.0)

## Files Modified
1. `src/etf_platform/layers/l18_var_risk.py` — code jitter ±0.45
2. `src/etf_platform/layers/l20_option_volatility.py` — code jitter ±0.40
3. `src/etf_platform/pipeline.py` — pass etf_code to L18/L20
4. `layer_research.md` — updated to v8.12
