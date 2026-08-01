# L8.18 Scoring Audit — 2026-07-09

## Summary
Comprehensive audit of L1-L23 scoring layers across 50 ETFs (均衡 profile). Found and fixed one CRITICAL bug and one P1 improvement.

## P0 Bug Fixed: L21_Overreaction Flatlined at 1.0

**Symptom:** L21_Overreaction score was exactly 1.0 for ALL 50 ETFs. Zero variance.

**Root Cause:** Two issues combined:
1. **Ordering bug:** L22_Pendulum was computed AFTER L21 Behavioral Factors in `pipeline.py`. L21_Overreaction reads `scores.get("L22_Pendulum", 5.5)` but L22 wasn't in scores yet → always got default 5.5.
2. **Formula bug:** Old formula `10 - abs(L20-5.5)*1.8` had ceiling effect because L20 clusters around 5.5, giving scores 8.2-10.

**Fix:**
1. Moved L22 computation block BEFORE L21 block in pipeline.py (line 338→355)
2. Rewrote overreaction formula: U-shaped mapping using L22 deviation from neutral + L20 vol amplification
   - `l22_extreme = abs(l22 - 5.5) / 3.0` (both high and low L22 = overreaction)
   - `l20_amp = l20 / 10.0` (high vol confirms)
   - `raw = l22_extreme * (0.7 + 0.3*l20_amp) * 9.0 + 1.0`

**Result:** range=[1.3, 10.0], mean=4.80, std=2.54, unique=34/50

## P1 Improvement: L21_Disposition RL Dominance Reduced

**Symptom:** L21_Disposition had mean=8.78, std=1.03, range=[5.9, 9.9]. rl*4.0 term dominated (56% of penalty), causing clustering.

**Fix:** Reduced rl weight from 4.0 to 1.5 (21% of total). Added L22_Pendulum as new signal.
- Old: `rl*4.0 + L5_penalty*2.0 + L17*0.5 + L14*0.3 + L9*0.2`
- New: `rl*1.5 + L5_penalty*1.5 + L17*0.5 + L14*0.3 + L9*0.2 + L22*0.3`

**Result:** range=[4.8, 9.9], std=1.12 (+9%), unique=24/50 (+2)

## Remaining Issues (P2/P3)

### L21_Behavior — std=0.69, CV=11% (P3)
Inherent to averaging 5 sub-scores. Sub-scores now have good spread individually.

### L21_Contrarian — std=0.90, CV=15% (P3)
Could add L21_Herding as seventh signal for more spread.

### L11_SectorRisk — ceiling at 6.3 (P2)
High-quality demand sectors can't score above 6.3. Needs expanded SECTOR_DEMAND_RISK data.

### L13_MacroCycle — std=0.88 (P2)
Sector-based macro cycle scoring with limited modulation.

### Simple Score Compression (P2)
Pipeline `score` field (simple average) has only 15 unique values in 50 ETFs, range [5.0, 6.4]. This is by design — the composite_score is the proper ranking metric.

## Files Modified
- `src/etf_platform/pipeline.py`: L22 ordering fix, Overreaction rewrite, Disposition rl reduction
- `layer_research.md`: Updated with v8.18 findings

## Verification
- `python batch_diverse.py --limit 10 --profile 均衡` runs successfully
- All 29 layers present in all ETFs
- No zero-score layers
- Composite score unique=47/50, range=[4.7, 6.4]
