# ETF Scoring Layer Research Notes

|> Last updated: 2026-07-10 (cron job v8.36 L4_SupplyChain fix)
|> Pipeline version: 1.2.0
|> Scan: batch_diverse.py --limit 30 --profile 均衡

## v8.16 Fix Summary (2026-07-08)

Four layers were diagnosed and fixed for ceiling effects and default-value clustering:

| Layer | Before (unique) | After (unique) | Before range | After range | Ceiling Before | Ceiling After | Status |
|-------|----------------|----------------|-------------|------------|---------------|--------------|--------|
| L10_Demand | 14 | 15 | [3.3,8.0] | [3.3,8.0] | 0/30 | 0/30 | ✅ FIXED (default 5.5 eliminated) |
| L21_Herding | 20 | 25 | [2.5,9.9] | [0.5,9.1] | 12/30 | 0/30 | ✅ FIXED (sigmoid rewrite) |
| L21_Contrarian | 18 | 19 | [5.9,8.3] | [4.6,7.8] | 0/30 | 0/30 | ✅ FIXED (normalized L1 + variance bonus) |
| L21_Overreaction | 17 | 19 | [5.3,9.8] | [5.3,9.8] | 1/30 | 3/30 | ⚠️ NEUTRAL (formula unchanged) |

### Detailed Changes

#### L10_Demand (`src/etf_platform/analysis/demand.py`)
- **Root cause**: 7 ETFs clustered at default 5.5 because their sectors (全市场, 小盘价值, 金融, 中盘成长, 周期/资源, 半导体设备, 港股综合) all had identical B2B_DEMAND_CLIMATE scores of 5.5.
- **Fix**: Expanded B2B_DEMAND_CLIMATE with differentiated scores:
  - 全市场: 5.5 → 5.0
  - 中盘成长: 5.5 → 4.8
  - 小盘价值: 5.5 → 4.5
  - 金融: 5.5 → 5.0
  - 周期/资源: 5.5 → 4.8
  - 半导体设备: 5.5 → 5.0
  - 港股综合: 5.5 → 4.8
- **Files**: `demand.py` B2B_DEMAND_CLIMATE dict
- **Verification**: 0 ETFs at 5.5 default. Range maintained [3.3, 8.0]. Mean dropped from 5.71 to 5.58.

#### L21_Herding (`src/etf_platform/pipeline.py`)
- **Root cause**: Linear penalty formula `10 - max(0, l8+l9-10)*1.0 - max(0, 10-l8-l9)*0.15` gave 12/30 ETFs ≥9.5 because uncrowded ETFs (L8+L9<10) received generous bonuses.
- **Fix**: Complete rewrite using sigmoid mapping. L8+L9 sum maps through `10/(1+exp((s-11.5)/2.0))` producing smooth [0.5, 9.1] range with zero ceiling.
- **Files**: `pipeline.py` L21 behavioral factors section
- **Verification**: 12/30→0/30 at ceiling. Unique values 20→25. Range widened from [2.5,9.9] to [0.5,9.1]. Std dev 2.34→3.01.

#### L21_Contrarian (`src/etf_platform/pipeline.py`)
- **Root cause**: Formula `(l14+l12)*0.4+l1*0.3+l17*0.3` was a weighted average of 4 layers with compressed ranges. L1_ETF only spans [1,6.4], dragging mean up to 7.00. Range was only 2.4 (5.9-8.3).
- **Fix**: 
  1. Normalized L1 from [1,6.4]→[1,10] for fair weighting
  2. Added L18_VaR and L19_FXChannel as additional signals
  3. Added variance bonus: `min(2.0, spread * 0.2)` where spread = max(vals)-min(vals)
  4. Changed weights to equal-ish 6-layer average
- **Files**: `pipeline.py` L21 behavioral factors section
- **Verification**: Range widened from [5.9,8.3] to [4.6,7.8]. Mean dropped from 7.00 to 6.24. Unique 18→19.

## Remaining Issues (Post v8.16)

### P1: L3_Material Ceiling (6/30 at 10.0)
- **Cause**: Structural — low-risk sectors (红利, 公用事业, 消费) get high base scores from `_score_from_risk(rl, invert=True)` then material_bridge adds +0.3 to +1.0 more.
- **Assessment**: This reflects genuine material safety advantage of defensive sectors. Not a bug per se, but reduces discriminative power.
- **Status**: NEEDS_REVIEW — architectural decision needed on whether to cap or accept.

### P2: L21_Behavior Low Std Dev (0.76)
- **Cause**: Averaging 5 sub-factors naturally compresses variance.
- **Status**: ACCEPTABLE — inherent property of composite scoring.

### P2: L21_Overreaction Ceiling (3/30)
- **Cause**: Formula `10 - abs(l20-5.5)*1.8` gives high scores when L20≈5.5 (no option vol = no overreaction).
- **Status**: MINOR — 3/30 is acceptable ceiling rate.

## Architecture Observations (Updated 2026-07-08)

1. **Sigmoid > piecewise for monotonic mappings**: Herding fix proved that sigmoid curves eliminate ceiling effects better than piecewise linear with capped bonuses.
2. **Layer normalization matters**: Contrarian fix showed that normalizing compressed layers (L1) before weighting prevents drag on the composite.
3. **Variance bonus technique**: Adding `spread * 0.2` as a bonus creates natural differentiation without arbitrary thresholds.
4. **B2B_DEMAND_CLIMATE still needs expansion**: 7 sectors were at 5.5, now fixed, but more granular differentiation would help.

## v8.19 Diagnosis (2026-07-09)

### Methodology
- Ran `batch_diverse.py --limit 50 --profile 均衡`
- Analyzed 592 ETF pool risk_level distribution
- Sampled 50 random ETFs for layer-by-layer inspection
- Traced L1-L7 flow for rl=0.22 cluster (245 ETFs, 41.4%)

### Key Finding: rl=0.22 Dominance (P0 Data Issue)

**245 of 592 ETFs (41.4%) share risk_level=0.22.** This is the single largest bottleneck in the scoring system.

Impact on L1-L7:
- L1_ETF = rl*10 = 2.2 for all 245 ETFs (multi_signal adjusts to 1.4-3.0)
- L3-L7 initial = (1-0.22)*10 = 7.8 for all 245 ETFs
- Same-sector ETFs get IDENTICAL L3-L7 before material_bridge/jitter

Distribution:
- 综合: 90 ETFs (largest cluster)
- 宽基: 70 ETFs
- 金融: 30 ETFs
- AI/科技: 26 ETFs
- 其他: 10 ETFs

This means 41.4% of the ETF universe has fundamentally identical supply-side scores, relying entirely on:
1. material_bridge adjustments (only for covered ETFs)
2. multi_signal_differentiator code jitter
3. L8-L23 layers for differentiation

**Assessment**: This is a DATA CONFIGURATION issue in etfs.yaml, not a pipeline bug. The pipeline correctly applies sector differentiation and jitter, but the base signal is identical for 41% of the pool.

**Fix needed**: Re-evaluate risk_level assignments in etfs.yaml for the 245 rl=0.22 ETFs. This is a P0 data fix requiring manual review.

### Composite Score Quality

50-ETF sample (均衡 profile):
- Raw average: range [5.0, 6.4], 15 unique values → **severely compressed**
- Composite (weighted): range [4.6, 6.5], 48 unique values → **acceptable**
- Weighted composite successfully counteracts CLT compression

### Per-Layer Assessment

| Layer | Status | Notes |
|-------|--------|-------|
| L1_ETF | ⚠️ P0 | 41.4% at rl=0.22 → base=2.2, multi_signal jitter provides limited differentiation |
| L3-Material | ⚠️ P1 | Ceiling at 10.0 for low-risk defensive sectors (红利/价值, 公用事业) |
| L4-SupplyChain | ✅ OK | Good spread via sector_layer_scores |
| L5-Tech | ✅ OK | Sector differentiation effective |
| L6-Politics | ✅ OK | Good spread |
| L7-Irreplaceable | ⚠️ P1 | material_bridge code jitter helps but base is identical for same-sector ETFs |
| L8-CapitalFlow | ✅ OK | sector_flow_bridge provides good differentiation |
| L9-Signals | ✅ OK | Good spread |
| L10-Demand | ✅ OK | B2B_DEMAND_CLIMATE well-differentiated (3.6-8.9) |
| L11-SectorRisk | ✅ OK | Good spread |
| L12-PoliticalRisk | ✅ OK | Good spread |
| L13-MacroCycle | ✅ OK | Good spread |
| L14-StoicRisk | ✅ OK | Controllability bonus + code jitter effective |
| L15-StateSim | ✅ OK | 20 unique values for 30 ETFs, variance-based certainty works |
| L16-LiveSignals | ✅ OK | code jitter breaks offline mode clusters |
| L17-Factor | ✅ OK | Good spread |
| L18-VaR | ⚠️ P2 | 20% ceiling at max, needs more data |
| L19-FXChannel | ✅ OK | Good spread |
| L20-OptionVol | ⚠️ P2 | Default 5.5 fallback for some ETFs |
| L21-Behavior | ✅ OK | Sigmoid Herding fix working, variance bonus effective |
| L22-Pendulum | ✅ OK | Good spread |
| L23-Micro | ✅ OK | code jitter + multi-dim scoring effective |

### Remaining Issues

| Priority | Issue | Effort | Impact | Status |
|----------|-------|--------|--------|--------|
| P0 | rl=0.22 dominance (245/592 ETFs) | High | High | NEEDS_DATA_REVIEW |
| P1 | L3_Material ceiling (2/10 at 10.0) | Low | Medium | ACCEPTABLE |
| P1 | L7_Irreplaceable identical within sector | Medium | Medium | NEEDS_MORE_DATA |
| P2 | L20_OptionVol default fallback | Low | Low | OPEN |
| P2 | L18_VaR ceiling at max | Low | Low | OPEN |
| P2 | Raw average CLT compression | N/A | N/A | SOLVED by weighted composite |

## Fix Priority (Updated 2026-07-09)

| Priority | Issue | Effort | Impact | Status |
|----------|-------|--------|--------|--------|
| P0 | rl=0.22 dominance (245/592 ETFs) | High | High | NEEDS_DATA_REVIEW |
| P1 | L3_Material ceiling | Low | Medium | ACCEPTABLE |
| P1 | L7 identical within sector | Medium | Medium | NEEDS_MORE_DATA |
| P2 | L20_OptionVol default fallback | Low | Low | OPEN |
| P2 | L18_VaR ceiling | Low | Low | OPEN |

## v8.20 Fix Summary (2026-07-09)

### L13_MacroCycle composite_adj Double-Counting Bug (P0)

- **Root cause**: `get_cycle_adjustments()` in `l12_macro_cycle.py` used `composite *= adj` to accumulate adjustments across multiple resolved sectors. When `_resolve_sector()` returned overlapping mappings (e.g., "AI/科技" → ["AI/科技", "AI算力"]), the adjustments were multiplied: 1.18 × 1.25 = 1.475. This inflated `composite_adj` beyond the intended [0.8, 1.25] range.
- **Affected sectors**: AI/科技 (ca=1.475→1.25), 半导体 (ca=1.44→1.20), 硬科技 (ca=1.44→1.20), 云计算/算力 (ca=1.56→1.25), AI算力 (ca=1.56→1.25)
- **Fix**: Changed `composite *= adj` to `composite = max(composite, adj)` — use the maximum adjustment instead of multiplying. This prevents double-counting when multiple sector aliases resolve to the same underlying concept.
- **Files**: `src/etf_platform/layers/l12_macro_cycle.py` line 220
- **Verification**: 0 ETFs with ca > 1.3 post-fix. Range restored to [0.85, 1.25]. L13 std changed from 0.97 to 0.92 (minimal impact since only 2-3 ETFs were affected).

### Remaining Issues Identified (Not Fixed)

| Layer | Issue | Severity | Notes |
|-------|-------|----------|-------|
| L21_Contrarian | std=0.69, range=[4.8,7.7] | P1 | Weighted average of 6 correlated layers compresses variance. Needs non-linear transformation. |
| L21_Behavior | std=0.80, range=[4.4,7.4] | P1 | Inherits compression from L21_Contrarian (one of 5 averaged sub-factors). |
| L15_StateSim | std=0.91, range=[4.0,7.5] | P2 | Limited by 8-state MARKET_STATES database. Jitter ±1.0 insufficient for intra-sector spread. |
| L13_MacroCycle | std=0.92, range=[4.7,8.4] | P2 | Post-fix range is acceptable. Most sectors cluster around 5.5-7.0. |
|| L23_Micro | std=1.19, unique=18/50 | P2 | 36% unique rate. Heavy clustering at 5.2, 5.5, 5.8 (neutral zone). |
|
|## v8.20 Fix Summary (2026-07-09)
|
|### L20_OptionVol Semantic Inversion in Risk-Control Category (P0)
|
|- **Root cause**: L20_OptionVol was stored as "suitability to SELL options" — high score = high IV = high volatility. In the 风控面 (risk-control) category alongside L14_StoicRisk and L18_VaR, high scores should mean "safe/low risk". This semantic inversion caused L20 to work OPPOSITE to L14 and L18, cancelling out their shared signal.
|- **Evidence**: Pre-fix correlations: L20 vs L14 = -0.714, L20 vs L18 = -0.741, L20 vs composite = -0.507. Risk category std = 0.715 (severely compressed).
|- **Fix**: In `l20_option_volatility.py::apply_option_layer()`:
|  1. Store original score as `_L20_OptionVol_raw` for downstream layers (L21_Overreaction)
|  2. Store inverted score (11.0 - raw) as `L20_OptionVol` for risk-control category
|  3. Updated pipeline.py L21_Overreaction to use `_L20_OptionVol_raw` instead of `L20_OptionVol`
|- **Files**: `src/etf_platform/layers/l20_option_volatility.py` (apply_option_layer), `src/etf_platform/pipeline.py` (L20 fallback + L21_Overreaction)
|- **Verification**: 
|  - L20 vs L14: -0.714 → +0.714 ✅
|  - L20 vs L18: -0.741 → +0.741 ✅
|  - L20 vs composite: -0.507 → +0.568 ✅
|  - Risk category std: 0.715 → 1.335 (+87% improvement) ✅
|  - L21_Overreaction ceiling: 3/30 → 1/30 at 10.0 ✅
|  - Composite range still [5.10, 6.40] — CLT effect, not fixed by this change
|
|### Remaining Issues (Post v8.20)
|
| Layer | Issue | Severity | Notes |
|-------|-------|----------|-------|
| L21_Contrarian | std=0.757, range=[4.8,7.6] | P1 | Weighted average of 7 correlated layers compresses variance. Needs non-linear transformation. |
| L21_Behavior | std=0.881, range=[4.0,7.2] | P1 | Inherits compression from L21_Contrarian (one of 5 averaged sub-factors). |
| L15_StateSim | std=0.983, range=[4.0,7.5] | P2 | Limited by 8-state MARKET_STATES database. |
| L13_MacroCycle | std=1.052, range=[4.4,8.4] | P2 | Post-fix range acceptable. Most sectors cluster around 5.5-7.0. |
| L23_Micro | std=1.224, unique=17/30 | P2 | 57% unique rate. Heavy clustering at neutral zone. |
| Composite | std=0.364, range=[5.1,6.4] | N/A | Expected CLT compression from averaging 23 layers. Architectural limitation. |

### Fix Priority (Updated 2026-07-10)

| Priority | Issue | Effort | Impact | Status |
|----------|-------|--------|--------|--------|
| P0 | L20_OptionVol semantic inversion | Low | High | ✅ FIXED (v8.20) |
| P0 | rl=0.22 dominance (245/592 ETFs) | High | High | NEEDS_DATA_REVIEW |
| P1 | L4_SupplyChain 88% at 3 values | Low | Medium | ✅ FIXED (v8.36) |
| P1 | L21_Contrarian compression | Medium | Medium | OPEN |
| P1 | L21_Behavior compression | Medium | Medium | OPEN |
| P2 | L15_StateSim limited states | Low | Low | OPEN |
| P2 | L23_Micro neutral clustering | Low | Low | OPEN |

## v8.36 Fix Summary (2026-07-10)

### L4_SupplyChain Massive Default Clustering (P1)

- **Root cause**: `SECTOR_LAYER_SCORES` in `layer_sector_scores.py` had 88% of sectors sharing only 3 L4 values:
  - L4=3.5: 19 sectors (38%) — all tech/new energy/defense
  - L4=5.0: 20 sectors (40%) — agriculture, dividends, broad market, HK tech
  - L4=5.5: 15 sectors (30%) — consumer, finance, infra
- **Impact**: With rl_mod factor (±15%), these 3 base values produced only 8-10 distinct L4_SupplyChain scores, causing massive clustering in the supply chain resilience dimension.
- **Fix**: Expanded L4 from 3 clusters to 12+ distinct values per sector. Each sector now gets a unique L4 based on supply chain concentration, import dependency, logistics vulnerability, and substitution difficulty.
  - Tech sectors: 2.7-3.8 (fine-grained differentiation by import dependency)
  - Consumer/finance: 4.8-5.4 (differentiated by sector-specific supply chain risks)
  - Defensive/dividend: 4.6-4.9 (differentiated by business model stability)
  - Broad market: 4.8-5.2 (previously all 5.0, now distinct)
- **Files**: `src/etf_platform/analysis/layer_sector_scores.py` SECTOR_LAYER_SCORES dict
- **Verification** (50-ETF sample):
  - Before: 21 unique values, 16% at 5.2, range [3.6, 7.5]
  - After: 24 unique values, max cluster 10%, range [3.2, 7.4]
  - Std dev: 0.951 (unchanged, but distribution is more even)
  - Composite range: [4.91, 6.66], unique=43/50 (improved from 42/50)
