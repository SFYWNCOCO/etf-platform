"""
ETF Layer Scoring Research Report — Batch v7.0 (2026-07-07)

## Mission
Research unseen scoring problems in L1-L16 layers, fix P0 issues immediately.

## Fixes Applied (v7.0)

### 1. L10_Demand — Consumer sector expansion
- **Problem:** DEMAND_CLIMATE had only 11 consumer entries. Sectors like 消费, 家电, 农产品, 医药器械 
  fell through to default scoring (uniform 5.5).
- **Fix:** Added 8 new entries (农产品, 医药器械, 餐饮, 旅游酒店, 体育娱乐) + updated existing 
  (消费, 家电) with differentiated parameters.
- **Result:** Consumer sectors now have real differentiated scores (消费=3.4, 医药=5.2, 农产品=5.5).

### 2. L11_SectorRisk — Consumer sector expansion  
- **Problem:** SECTOR_DEMAND_RISK had only 8 entries. Missing 农产品, 医药器械, etc.
- **Fix:** Added 7 new consumer entries + updated 家电 (inventory 90→60, price trend 下跌→持平).
- **Result:** All consumer sectors now have proper inventory/price/demographic data.

### 3. L16_LiveSignals — Premium integration
- **Problem:** `SECTOR_PREMIUM_ESTIMATES` dict existed since v3.0 but was NEVER used by `get_live_signals()`.
  All sectors got premium_score=5 (hardcoded default).
- **Fix:** Integrated SECTOR_PREMIUM_ESTIMATES into get_live_signals() with ±1.5 capped adjustment.
  Tech sectors: +2.0~2.8, dividend: -0.2~-0.3, cross-border: +1.0~1.5.
- **Result:** Spread increased 35% (1.7→2.3), 9 unique values.

## Files Modified
1. `src/etf_platform/analysis/demand.py` — DEMAND_CLIMATE + SECTOR_DEMAND_RISK expansions
2. `src/etf_platform/layers/l16_live_signals.py` — SECTOR_PREMIUM_ESTIMATES integration

## Remaining P0 Issues
- L13_MacroCycle: 11/30 at exactly 6.0 (11 unique → should be 15+)
- L17_Factor: 13/30 at exactly 5.0 (wide "宽基" fallback)
- L18_VaR: 14/30 at exactly 5.9 (coarse volatility tiers)

## Next Steps
- Expand L13 keyword fallback with more granular composite_adj values
- Reduce L17 "宽基" fallback rate
- Add L18 sub-tiering for volatility bands
