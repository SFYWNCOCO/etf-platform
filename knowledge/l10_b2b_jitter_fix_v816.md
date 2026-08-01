# L10_Demand B2B Exact-Match Blind Spot + L21_Disposition Redundant Signal Fix

> Date: 2026-07-08 | Version: v8.16 | Author: ETF scoring research cron

## P0 Finding: L10_Demand B2B Exact-Match Missing Jitter

### Symptom
B2B_DEMAND_CLIMATE exact-match sectors (军工=8.0, AI/科技=8.0, 红利/价值=6.0, etc.) returned static scores with:
- Zero code-based jitter
- Zero risk_level modulation
- Identical scores for all ETFs in the same sector

### Root Cause
`demand.py:score_demand_climate()` line 686-689:
```python
if b2b:
    return {"score": b2b["score"], ...}  # STATIC, no jitter, no rl_mod
```

The keyword fallback path (line 692-700) had both jitter and risk_level modulation, but the exact-match path did not. This created a two-tier system where B2B exact-match sectors had zero intra-sector differentiation.

### Fix Applied
Added risk_level modulation and code jitter to B2B exact-match path:
```python
if b2b:
    base_score = b2b["score"]
    rl_mod = (0.5 - risk_level) * 3.0
    final_score = round(max(3.0, min(9.0, base_score + rl_mod)), 1)
    code_jitter = _l10_code_jitter(etf_code, final_score)
    final_score = round(max(3.0, min(9.0, final_score + code_jitter)), 1)
    return {"score": final_score, ...}
```

### Result
- Before: unique=7, range=[4.5, 8.0], std=1.15
- After: unique=10, range=[4.5, 8.9], std=1.54
- All 10 ETFs now have unique L10 scores

## P1 Finding: L21_Disposition Redundant L1 Signal

### Symptom
L21_Disposition formula had 4 components:
1. `rl * 4.0` — primary risk penalty
2. `(10 - L1) * 0.3` — claimed "finer granularity"
3. `max(0, 5-L14) * 0.3` — floor adjustment
4. `max(0, 5-L9) * 0.2` — signal strength

### Root Cause
L1_ETF is derived from risk_level: `L1 ≈ rl * 10 + small_jitter`
Therefore `(10 - L1) * 0.3 ≈ (10 - rl*10) * 0.3 = (1-rl) * 3.0`
This is almost perfectly anti-correlated with `rl * 4.0`, meaning the L1 component was double-counting the risk_level signal.

### Fix Applied
Replaced L1 component with L17_Factor (Fama-French factor loading), which is independent of risk_level:
```python
# Before: l1_penalty = (10.0 - l1) * 0.3
# After:  l17_signal = max(0, 5.0 - l17) * 0.4
```

Weight increased from 0.3 to 0.4 to compensate for losing the L1 component's (redundant) contribution.

### Result
- Before: unique=7, range=[2.4, 6.7], 30% at 6.6
- After: unique=8, range=[4.8, 9.1], 20% at 9.1
- Eliminated redundant signal, gained genuine intra-sector differentiation

## Files Modified
- `src/etf_platform/analysis/demand.py` — L10_Demand B2B exact-match path (line 686-689)
- `src/etf_platform/pipeline.py` — L21_Disposition formula (line 358-375)
- `layer_research.md` — Updated to v8.16

## Verification
- `python batch_diverse.py --limit 10 --profile 均衡` — ran successfully
- All formulas manually verified against stored scores
- Composite score distribution unaffected (still unique=10/10)
