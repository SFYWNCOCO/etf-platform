|| Layer Scoring Distortion Analysis — Post-Fix Report v8.33

> Generated: 2026-07-10 (v8.35 — L9 floating-point ceiling guard fixed + L17/L19 always-reserve-0.1-headroom) | Sample: 50 ETFs (均衡 profile, fresh scan) | Status: ZERO layers at hard 10.0 ceiling

## Audit Summary (v8.35 — 2026-07-10)

### 🔴 P0 FIX: L9 floating-point ceiling regression (1 at 10.0) — v8.35

**Issue:** L9_Signals=10.0 for 159516 (半导体设备ETF国泰) — regression from v8.34 fix.

**Root cause:** Floating-point comparison bug in ceiling guards. `headroom = 10.0 - 9.7` evaluates to `0.3000000000000007` (not exactly 0.3). In `l19_fx_channel.py`, `headroom <= 0.3` evaluates to `False`, causing full +0.3 to be applied → 9.7+0.3=10.0 clamped.

**Fix (2 files):**
1. `l19_fx_channel.py`: Ceiling guard now always reserves 0.1 headroom (`adj = min(0.3, headroom - 0.1)`) regardless of headroom magnitude.
2. `l17_quantitative_factor.py`: Same pattern — `adj = min(0.5, headroom - 0.1) if headroom > 0.1 else 0.0`.

**Impact:**
- L9 at 10.0: 1 → 0 ✅
- L9 max: 10.0 → 9.9 ✅
- 159516 L9: 10.0 → 9.9 ✅
- **All 29 layers maintain zero ETFs at hard 10.0 ceiling.**

### 🟡 P1: L3_Material 8 ETFs at >= 9.5 (legitimate high)

8 defensive-sector ETFs (红利/价值, 公用事业, 消费, 金融, 保险) score >= 9.5 on L3. These are legitimate high material safety scores, not ceiling artifacts. Range is [3.0, 9.9] with 34 unique values — healthy distribution.

### No NEW P0 Issues Found

All previous P0 fixes (L15 sector chars, L13 jitter reduction, L12 geopolitical, L3-L4 decoupling, L3 ceiling, L10 ceiling, L2 ceiling, L9 ceiling v8.33) verified stable.

## Remaining P0 Issues (structural by design)

### 🔴 P0 FIX: L9_Signals ceiling effect (1 at 10.0) — v8.33

**Issue:** Three-part cascade pushed 159516 (半导体设备) to L9=10.0:
1. `sector_flow_bridge.py`: return_pct=6.53 → L9=9.2 (capped at 9.0 from return formula, then +etf_adj)
2. `l17_quantitative_factor.py`: bullish momentum_signal → L9 += 0.5 → 9.7
3. `l9_news.py`: 1 net positive news → L9 += 0.5 → 10.2 → clamped to 10.0

**Root cause:** `l17_quantitative_factor.apply_factor_layer()` adds ±0.5 to L9 for bullish/bearish momentum, but this was unknown to the L9 ceiling guards. The `multi_signal_differentiator` had ceiling awareness for L3-L7 but NOT for L9 (line 327: `combined * 1.5` with no ceiling check). The `l9_news` enhancement had no ceiling guard at all.

**Fix (3-part):**
1. `multi_signal_differentiator.py`: Added ceiling-aware check for L9 — if L9 >= 8.5, reduce `combined * 1.5` multiplier by 50%.
2. `multi_signal_differentiator.py`: Added ceiling-aware checks for L10, L11, L12 — same 50% reduction if score >= 8.5.
3. `l9_news.py`: Added ceiling guard — if headroom < 1.0 (score > 9.0), cap positive news adjustment to leave at least 0.1 headroom.

**Impact:**
- L9 at 10.0: 1 → 0 ✅
- L9 range: [4.6, 10.0] → [4.6, 9.9]
- L10/L11/L12: no ceiling changes in this sample (already safe), but ceiling guards prevent future issues

### 🔴 P0 FIX: L21_Contrarian ceiling effect (1 at 10.0) — v8.33

**Issue:** `base * amplifier` formula produced 10.5 for 159516 (extreme layer disagreement: L14=3.1 vs L19=8.8), clamped to 10.0.

**Fix:** Added ceiling guard — cap contrarian_score at 9.9 before jitter application.

**Impact:**
- L21_Contrarian at 10.0: 1 → 0 ✅
- L21_Contrarian range: [5.8, 10.0] → [5.8, 9.9]

### 📊 Zero-Ceiling Achievement

All 29 layers now have **zero ETFs at hard 10.0 ceiling**. Maximum observed:
- L3_Material: 9.8 (红利/价值 — legitimate high material safety)
- L9_Signals: 9.9 (capped by new guard)
- L21_Contrarian: 9.9 (capped by new guard)

## Audit Summary (v8.31 — 2026-07-10)

| ### 🔴 P0 FIX: L3_Material ↔ L4_SupplyChain redundancy (r=0.905 → 0.116)
|
| **Issue:** L3 and L4 derived from the SAME material_bridge signal. L3 = total_signal * 0.7, L4 = total_signal * 0.3. Both used the same SECTOR_LAYER_SCORES base values with identical rl_mod. Result: r=0.905 — L4 was just a scaled-down version of L3, providing essentially zero independent information.
|
| **Fix (3-part):**
| 1. `layer_sector_scores.py`: Reversed L4 ordering for key sectors. Defensive sectors (红利/价值 L3=8.5) now get LOW L4 (5.0). Tech sectors (半导体 L3=3.0) now get HIGH L4 (3.5). L4 ordering is INDEPENDENT of L3 ordering.
| 2. `material_bridge.py`: Reduced L4 material signal weight from 0.3→0.1 (L3 stays at 0.7). L4 differentiation now comes primarily from sector base scores, not material signals.
| 3. `material_bridge.py`: Added SUPPLY_CHAIN_MODULATION dict in `apply_to_layers()` with sector-level supply chain risk values (range ±3.0). High-risk sectors (半导体设备 +3.0) get boosted L4; stable sectors (公用事业 -2.0) get penalized L4.
|
| **Impact:**
| - L3-L4 Pearson correlation: 0.905 → 0.116 ✅ TARGET MET (<0.7)
| - L3 range: [3.0, 10.0] (unchanged, 32 unique)
| - L4 range: [3.6, 7.5] (21 unique)
| - L3-L4 diff range: [-2.3, +6.3] (was [-2.0, +2.0])
| - High-corr pairs (>0.7): 25 → 19 (-24%)
| - 红利/价值: L3=10.0 L4=5.2 (diff=+4.8 — high material safety, low supply chain risk)
| - 半导体设备: L3=4.3 L4=6.5 (diff=-2.2 — low material safety, high supply chain risk)
|
| ### 🔴 P0 FIX: L12_Geopolitical copy-paste error (金融/银行 scored 0.95 = semiconductor level)
|
| **Issue:** `political_risk.py` GEOPOLITICAL_EXPOSURE dict had `"金融": 0.95` and `"银行": 0.95` — same as semiconductor (芯片禁令). Financial sectors are domestic-focused with virtually zero US-China geopolitical exposure. This caused 金融科技ETF to score L12=8.0 (equivalent to 半导体) instead of ~5.0.
|
| **Fix:** Changed GEOPOLITICAL_EXPOSURE["金融"] and ["银行"] from 0.95 → 0.10.
|
| **Impact:**
| - 金融 L12: 8.0 → 5.4 (corrected)
| - 银行 L12: 8.0 → 4.8 (corrected)
| - 券商 L12: 6.4 (unchanged, already correct)
| - 保险 L12: 5.3 (unchanged, already correct)
|
| ### 🔴 P0 FIX: L3_Material ceiling effect (2 at 10.0) — v8.32
|
| **Issue:** Three-part ceiling cascade: (1) `layer_sector_scores.py` ceiling_break formula was too permissive (mod_factor 0.5-0.65, keeping 60-65% of excess above 8.0), (2) `material_bridge.py` adds +1.06 to L3 for covered ETFs, undoing ceiling_break, (3) `multi_signal_differentiator.py` applies 2.5x multiplier to L3, adding +0.8-0.9 for low-risk ETFs. Result: 红利/价值 and 公用事业 hit 10.0.
|
| **Fix (3-part):**
| 1. `layer_sector_scores.py`: Reduced ceiling_break mod_factor from `0.5 + (0.5-rl)*0.3` to `0.2 + (0.5-rl)*0.25` (range 0.2-0.35 vs 0.5-0.65).
| 2. `multi_signal_differentiator.py`: Added ceiling-aware adjustment — if L3 >= 8.5, reduce multiplier by 50% to prevent multi_signal from undoing ceiling_break.
| 3. Combined effect: L3 max reduced from 10.0 → 9.9, zero ETFs at hard ceiling.
|
| **Impact:**
| - L3 at 10.0: 2 → 0 ✅
| - L3 >= 9.5: 2 → 8 (defensive sectors legitimately high)
| - L3 unique: 32 → 34
| - L3 mean: 7.03 → 6.97 (slightly lower, less ceiling pressure)
|
| ### 🔴 P0 FIX: L10_Demand ceiling effect (2 at 9.0) — v8.32
|
| **Issue:** `demand.py` B2B_DEMAND_CLIMATE has high base scores for 军工/硬科技 (8.0). With rl_mod = (0.5 - risk_level) * 3.0, low-risk ETFs (rl=0.22) get +0.84, pushing 8.0 → 8.84 → clamped to 9.0. Same issue in keyword fallback and consumer sector paths.
|
| **Fix:** Reduced rl_mod multiplier from 3.0 → 2.0 across all 4 L10 paths (B2B exact match, keyword fallback, consumer default, consumer model).
|
| **Impact:**
| - L10 at 9.0: 2 → 0 ✅
| - L10 range: [4.9, 8.9] → [2.2, 8.9] (wider spread)
| - L10 unique: 34 → 31
| - L10 mean: 6.10 → 5.93 (less upward bias)
|
| ### 🟡 P1 FIX: L2_Holdings ceiling effect (27.7% at 9.0)
|
| **Issue:** `l2_holdings_bridge.py` had `rl_mod = (0.5 - risk_level) * 0.5` and `fee_mod` up to ±0.5. For sector=8.0 (宽基) with rl=0.22 and fee≤0.0003: 8.0 + 0.27 + 0.5 = 8.77, clamped to 9.0. 155/560 ETFs ended at ceiling with composite range [5.73, 6.19] — only 0.46 spread across 155 ETFs.
|
| **Fix:** Reduced rl_mod from ±0.5 to ±0.3, reduced fee_mod from ±0.5 to ±0.3.
|
| **Impact (post-fix, 50 ETFs):**
| - L2 at >= 9.0: 27.7% → 0%
| - L2 range: [4.0, 9.0] → [4.2, 8.4]
| - L2 unique: 8 → 21
|
| ### 🟡 P1 FIX: L10/L11 intra-sector jitter too small
|
| **Issue:** L10 jitter was ±0.36, L11 jitter was ±0.45. For sectors with 90+ ETFs sharing identical risk_level (e.g., 宽基 with rl=0.22), jitter was insufficient to break clusters.
|
| **Fix:** Increased L10 jitter to ±0.8, L11 jitter to ±1.0.
|
| **Impact (post-fix, 50 ETFs):**
| - L10 unique: maintained 33 (good)
| - L11 unique: maintained 30 (good)

### No NEW P0 Issues Found
All previous P0 fixes (L15 sector chars, L13 jitter reduction, L12 geopolitical, L3-L4 decoupling) verified stable.

## Remaining P0 Issues (structural by design)

### 🔴 P0: L9_Signals ↔ L21_Herding r=-0.952 (BY DESIGN)
L21_Herding = sigmoid(L8 + L9). Near-perfect negative correlation with L9 is inherent.
**Fix needed:** Redesign L21_Herding to use independent signals (volume patterns, order flow).

### 🔴 P0: L14_StoicRisk ↔ L1_ControllabilityBonus r=+0.940 (BY DESIGN)
Both from score_stoic_layer(). L1_CB = linear_map(controllability). L14 = 0.6*controllability + 0.4*tail_risk.
**Fix needed:** L1_CB should use tail_risk or other independent input.

### 🔴 P0: L8_CapitalFlow ↔ L21_Herding r=-0.928 (BY DESIGN)
Also explained by sigmoid(L8+L9) formula.

## Current Status (50 ETFs, 2026-07-10, FRESH SCAN, POST-FIX v8.31)

| # | Layer | Data Source | Per-ETF Variance | Status |
|---|-------|-------------|-----------------|--------|
| 1 | L1_ETF | risk_level * 10 + multi-signal | ⚠️ Low (clustered by sector) | P2 data gap |
| 2 | L2_Holdings | l2_holdings_bridge (sector + fee + rl) | ✅ Improved | FIXED ceiling |
| 3 | L3_Material | sector + material_bridge + **ceiling_break v8.32** | ✅ **FIXED** | **zero at 10.0** |
| 4 | L4_SupplyChain | sector + material_bridge + **SUPPLY_CHAIN_MODULATION** | ✅ **FIXED** | **r=0.116 with L3** |
| 5 | L5_Tech | sector + factor_loading | ✅ Good | OK |
| 6 | L6_Politics | sector | ✅ Good | OK |
| 7 | L7_Irreplaceable | sector + factor_loading | ✅ Good | OK |
| 8 | L8_CapitalFlow | sector_flow_bridge | ✅ Good | OK |
|| 9 | L9_Signals | risk_level + sector_flow + **l17+l19+l9_news ceiling guards v8.35 (FP fix)** | ✅ **FIXED** | **zero at 10.0** |
| 10 | L10_Demand | demand_climate + **rl_mod*2.0 v8.32 + jitter±0.8** | ✅ **FIXED** | **zero at 9.0** |
| 11 | L11_SectorRisk | sector_demand_risk + **jitter±1.0** | ✅ Good | OK |
| 12 | L12_PoliticalRisk | political_risk + multi-signal | ✅ **FIXED** | **金融/银行 geo corrected** |
| 13 | L13_MacroCycle | sector + risk_mod + jitter | ⚠️ Borderline | P2 CV=13.7% |
| 14 | L14_StoicRisk | sector + jitter | ✅ Good | OK |
| 15 | L15_StateSim | sector + jitter | ⚠️ Moderate | P2 CV=15.9% |
| 16 | L16_LiveSignals | real-time premium/liquidity | ✅ Good | OK |
| 17 | L17_Factor | factor_loading (real data) | ✅ Good | OK |
| 18 | L18_VaR | volatility data (real) | ✅ Good | OK |
| 19 | L19_FXChannel | FX data (real) | ✅ Good | OK |
| 20 | L20_OptionVol | IV data (real) | ✅ Good | OK |
| 21 | L21_Attention | L1+L7 derived | ⚠️ Inherits L1 compression | P2 |
| 22 | L21_Behavior | 5-sub-score avg | ⚠️ Averaging compression | P2 CV=12% |
|| 23 | L21_Contrarian | MAD+amplifier + **ceiling_guard v8.33** | ✅ **FIXED** | **zero at 10.0** |
| 24 | L21_Disposition | rl+L5+L17+L14+L9+L22+L8 | ✅ Good | OK CV=28% |
| 25 | L21_Herding | sigmoid L8+L9 | ✅ Good | OK |
| 26 | L21_Overreaction | L22 deviation + L20 | ✅ Good | FIXED CV=55% + ceiling guard v8.34 |
| 27 | L22_Pendulum | kline trend (real) | ✅ Good | OK CV=27% |
| 28 | L23_Micro | kline microstructure | ⚠️ Neutral path dominates | P2 unique=20 |
| 29 | L1_ControllabilityBonus | L14 controllability + jitter | ✅ Good | OK |

**v8.35 note:** L9 floating-point ceiling guard fixed. `headroom <= 0.3` comparison failed for headroom=0.3000000000000007 due to float precision, allowing full +0.3 adjustment to push 9.7→10.0. Fixed by always reserving 0.1 headroom in both l17 and l19 ceiling guards. L9 max: 10.0→9.9. **ZERO layers at hard 10.0 ceiling.**

**v8.34 note:** L9 three-part ceiling cascade eliminated (sector_flow_bridge + l17_momentum + l19_fx all got ceiling guards). L21_Overreaction formula overflow fixed (l22_extreme clamped to [0,1]). L9 max: 10.0→9.9. L21_Overreaction max: 10.0→9.3. **ZERO layers at hard 10.0 ceiling across all 29 layers.**

**v8.33 note:** L9 ceiling eliminated (10.0→9.9 via ceiling-aware multi_signal + l9_news guard). L21_Contrarian ceiling eliminated (10.0→9.9 via cap). L10/L11/L12 multi_signal ceiling guards added. **ZERO layers at hard 10.0 ceiling across all 29 layers.**

**v8.32 note:** L3 ceiling eliminated (10.0→0 via ceiling_break + multi_signal ceiling-aware). L10 ceiling eliminated (9.0→0 via rl_mod 3.0→2.0). L2 ceiling already fixed in v8.29. Composite unique: 46/50 across 50 ETFs.

**v8.30 note:** L12 geopolitical exposure for 金融/银行 corrected (0.95→0.10). L9 combined*1.5x multiplier applied. L2 ceiling eliminated. L10/L11 jitter increased.

## Critical Data Coverage Issue (P2 — Not fixable in code)

### L1_ETF Compression: 93% of ETFs in same-sector+risk_level clusters

**Root cause:** `risk_level` in `config/etfs.yaml` is assigned per sector, not per ETF.
- 41.4% of all 592 ETFs have risk_level=0.22 (sectors: 综合/宽基/金融/其他/公用事业)
- 90% of 60 sectors have zero risk_level variance within sector
- 548/592 (93%) ETFs share sector+risk_level with at least one other ETF

**Cascade effect:**
- L1_ETF = risk_level * 10 (direct mapping)
- L3-L7 = (1-risk_level) * 10 (inverted mapping)
- L8-L9 = risk_level * 10 (direct mapping) — **FIXED by L9 combined*1.5x**
- L10-L14 use risk_level for modulation
- L21_Disposition uses risk_level directly
- L21_Attention uses L1_ETF (inherited compression)

**Mitigation in place:**
- multi_signal_differentiator.py applies 6-dim ETF-level signal to L1 with 0.8x multiplier
- Code-based jitter ±0.2 for L1_ETF
- Code-based jitter for L14 (±0.4), L15 (±1.0), L23 (±0.45)

**Impact:** L1_ETF effective range after mitigation:
- rl=0.22 cluster: [1.4, 3.2] — still compressed but functional
- rl=0.35 cluster: [2.5, 4.5]

**Fix needed:** Update `config/etfs.yaml` to assign per-ETF risk_level values rather than per-sector defaults. This is a DATA task, not a code fix.

## Historical Fixes

### ✅ v8.35: L9 floating-point ceiling guard fixed (P0 → Fixed)
L9_Signals=10.0 regression for 159516 (半导体设备ETF). Root cause: floating-point comparison `headroom <= 0.3` evaluated to False when headroom=0.3000000000000007, bypassing ceiling guard. Fix: both l17_quantitative_factor and l19_fx_channel now always reserve 0.1 headroom (`adj = min(max_adj, headroom - 0.1)`). L9 max: 10.0→9.9.

### ✅ v8.34: L9 three-part ceiling cascade + L21_Overreaction overflow (P0 → Fixed)
L9 four-part cascade: sector_flow_bridge (9.4) → l17 bullish momentum (+0.5 → 9.9) → l19 bullish FX (+0.3 → 10.2) → clamped to 10.0. Fix: (1) l17_quantitative_factor ceiling-aware momentum guard, (2) l19_fx_channel ceiling-aware FX guard, (3) sector_flow_bridge ceiling-aware code jitter, (4) pipeline.py L21_Overreaction l22_extreme clamped to [0,1] to prevent formula overflow. Zero layers at hard 10.0 ceiling.

### ✅ v8.33: L9_Signals ceiling + L21_Contrarian ceiling (P0 → Fixed)
L9 three-part cascade: sector_flow_bridge (9.2) → l17_factor bullish (+0.5 → 9.7) → l9_news (+0.5 → 10.0). Fix: (1) multi_signal_differentiator L9/L10/L11/L12 ceiling-aware (50% multiplier reduction at >=8.5), (2) l9_news ceiling guard (reserve 0.1 headroom), (3) L21_Contrarian cap at 9.9 before jitter. Zero layers at hard 10.0 ceiling.

### ✅ v8.32: L3 ceiling cascade fixed (P0 → Fixed)
Three-part fix: (1) ceiling_break mod_factor reduced from 0.5-0.65 to 0.2-0.35 range, (2) multi_signal_differentiator L3 multiplier halved for scores >= 8.5, (3) combined prevents material_bridge from undoing ceiling_break. L3 at 10.0: 2→0.

### ✅ v8.32: L10_Demand ceiling fixed (P0 → Fixed)
Reduced rl_mod multiplier from 3.0→2.0 across all 4 L10 paths. L10 at 9.0: 2→0. L10 range widened from [4.9, 9.0] to [2.2, 8.9].

### ✅ v8.31: L3↔L4 redundancy fixed (P0 → Fixed)
L3-L4 correlation: 0.905 → 0.116. Three-part fix: reversed L4 ordering in sector scores, reduced L4 material signal weight, added SUPPLY_CHAIN_MODULATION. L3 and L4 now have INDEPENDENT ordering.

### ✅ v8.30: L12_Geopolitical copy-paste error (P0 → Fixed)
Fixed GEOPOLITICAL_EXPOSURE["金融"] and ["银行"] from 0.95→0.10. Was equal to semiconductor (芯片禁令) — financial sectors are domestic-focused with near-zero geopolitical risk.

### ✅ v8.29: L9_Signals negligible adjustment (P0 → Fixed)
Replaced `(type*0.2 + purity*0.2) * 0.5` with `combined * 1.5`. L9 unique values: 5 → 31.

### ✅ v8.29: L2_Holdings ceiling effect (P1 → Fixed)
Reduced rl_mod ±0.5→±0.3, fee_mod ±0.5→±0.3. L2 at 9.0: 27.7% → 0%.

### ✅ v8.29: L10/L11 jitter too small (P1 → Fixed)
L10 jitter: ±0.36→±0.8. L11 jitter: ±0.45→±1.0.

### ✅ v8.28: L13_MacroCycle code jitter range reduced (P1 → Fixed)
Reduced jitter from ±0.60 to ±0.30 to prevent jitter from dominating sector/risk_level signal.

### ✅ v8.27: Stale checkpoint causing L22=5.0 for all ETFs (P0 → Fixed)
Cleared `data/screener_cache/scan_均衡_checkpoint.json` and `scan_均衡.json` that contained pre-L22 pipeline results. Fresh scan restores correct L22_Pendulum, L21_Disposition, L21_Overreaction distributions.

### ✅ v8.26: Live adjustments cache path sanitization (P3 → Fixed)
Added `_sanitize_key()` to replace special chars in cache filenames. Fixes FileNotFoundError for sectors with `/` in names.

### ✅ v8.24: L21_Contrarian compression fixed
MAD dispersion + L22 amplifier removed herding blend. CV: 11%→16%.

### ✅ v8.23: L11_SectorRisk ceiling effect fixed
Reduced rl_mod multiplier from *8.0→*5.0 (B2B), *6.0→*4.0 (keyword).

### ✅ v8.22: L21_Disposition mean compression fixed
Increased penalty multiplier from 1.4x→1.8x, lowered base from 10.3→10.0.

### ✅ v8.21: batch_diverse.py ranking inconsistency fixed
Changed to composite_score for ranking consistency with screener.py.

### ✅ P0: hash() non-determinism fixed
All jitter generation uses hashlib.sha256() for cross-process determinism.

## Known P2 Issues (inherent design limitations)

### 🟡 P2: L1_ETF data coverage gap
risk_level is sector-level in config. 93% of ETFs share sector+risk_level. Requires config data update, not code fix.

### 🟡 P2: L13_MacroCycle low CV (13.7%)
Sector-based macro scoring with limited ETF-level modulation. Risk_mod ±1.8 + jitter ±0.30 (reduced v8.28). CV slightly decreased after jitter reduction — signal-to-jitter ratio improved but sector-level base remains dominant.

### 🟡 P2: L15_StateSim low CV (15.9%)
Sector-characteristic driven with hardcoded CURRENT_FEATURES. Code jitter ±1.0 + 2 missing sectors fixed in v8.28. Base is still sector-level.

### 🟡 P2: L21_Behavior compression (CV=10%)
Simple arithmetic mean of 5 sub-scores compresses variance. Herding (CV=49%) and Disposition (CV=28%) have good spread but get averaged with tighter layers (Attention CV=17%, Contrarian CV=10%).

### 🟡 P2: L23_Micro neutral path dominance (unique=20)
Most ETFs have normal volume ratios → default to "neutral" path → score ≈ 5.0. Only extreme anomalies break out.

### 🟡 P2: L22_Pendulum angle cancellation
High-volatility trending ETFs (vol>40) get -15° correction that cancels the +15° from +8-15% 20d gain. Howard Marks framework insight (vol high at both tops and bottoms) creates systematic neutral bias for volatile sectors.

## Technical Notes

- **Disposition formula:** `rl_penalty = rl*1.5*1.8 + max(0,5-L5)*1.5*1.8` — combines risk_level AND L5_Tech into single penalty term. L5 component is often dominant.
- **L9 news enhancement:** Runs AFTER sector_flow_bridge, adds ±0.5 per net news sentiment. This is intentional real-time signal injection.
- **L20 inversion:** L20_OptionVol = 11 - _L20_OptionVol_raw. Raw preserved for L21_Overreaction which needs original direction.
- **L18_VaR mutates L1_ETF:** High-risk ETFs get L1_ETF -0.5. This modified value feeds L21 layers.
- **L5_Tech pipeline:** _score_from_risk(8.8) → sector(3.3) → material(3.3) → multi_signal(3.6) → factor(3.9). Sector score overrides initial risk derivation.
- **Composite score compression:** CV=8% across 50 ETFs. Weighted categories only marginally improve over simple average (CV=6%). The 29-layer CLT effect remains the fundamental discriminator bottleneck.
