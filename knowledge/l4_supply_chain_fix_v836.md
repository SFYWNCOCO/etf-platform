# L4_SupplyChain Clustering Fix (v8.36)

Date: 2026-07-10
Author: Cron job v8.36
Severity: P1

## Problem

`SECTOR_LAYER_SCORES` in `layer_sector_scores.py` had 88% of sectors sharing only 3 L4 values:

| L4 Value | Sectors | Percentage |
|----------|---------|------------|
| 3.5 | 19 sectors (all tech/new energy/defense) | 38% |
| 5.0 | 20 sectors (agriculture, dividends, broad market, HK tech) | 40% |
| 5.5 | 15 sectors (consumer, finance, infra) | 30% |

With rl_mod factor (±15%), these 3 base values produced only 8-10 distinct L4_SupplyChain scores.

## Impact

- L4_SupplyChain unique values: only 21/50 in 50-ETF sample
- Max cluster: 16% at value 5.2
- Range: [3.6, 7.5] — severely compressed for a 10-point scale

## Fix

Expanded L4 from 3 clusters to 12+ distinct values per sector:

- **Tech sectors**: 2.7-3.8 (fine-grained by import dependency: GPU/chip = lowest, PCB/5G = mid, software = highest)
- **New energy**: 3.1-3.6 (solar worst due to overcapacity, battery best due to storage demand)
- **Consumer/finance**: 4.8-5.4 (differentiated by supply chain type)
- **Defensive/dividend**: 4.6-4.9 (differentiated by business model stability)
- **Broad market**: 4.8-5.2 (previously all 5.0, now distinct per type)
- **Cross-border/US**: 5.1-5.8 (differentiated by geographic supply chain complexity)

## Verification (50-ETF sample)

| Metric | Before | After |
|--------|--------|-------|
| Unique values | 21/50 | 24/50 |
| Max cluster | 16% at 5.2 | 10% at 6.2/5.5 |
| Range | [3.6, 7.5] | [3.2, 7.4] |
| Std | 0.951 | 0.951 |
| Composite unique | 42/50 | 43/50 |

## Files Changed

- `src/etf_platform/analysis/layer_sector_scores.py` — SECTOR_LAYER_SCORES dict L4 values

## Related

- L3_Material: also uses SECTOR_LAYER_SCORES, but L3 values were already well-differentiated (8 distinct tiers)
- L5_Tech, L6_Politics, L7_Irreplaceable: also in SECTOR_LAYER_SCORES, not affected by this fix
- material_bridge: still applies post-L4 adjustments, so downstream layers see the improved spread
