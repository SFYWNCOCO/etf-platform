# L20_OptionVol & L13_MacroCycle hash() Non-Determinism Fix — v8.20

> Date: 2026-07-09 | Priority: P0 | Status: FIXED

## Problem

Both L20_OptionVol and L13_MacroCycle used Python's built-in `hash()` function for generating deterministic jitter. Since Python 3.3, `hash()` is randomized per-process via PYTHONHASHSEED environment variable. This means:

1. **L20_OptionVol:** Same ETF code → different scores between runs
2. **L13_MacroCycle:** Unknown sectors → different scores between runs

This violates reproducibility requirements for a scoring system.

## Root Cause

```python
# L20_OptionVol (broken)
hv_noise = math.sin(hash(sector) % 1000) * 0.02
code_hash = hash(etf_code)

# L13_MacroCycle (broken)
h = hash(sector) % 40
```

## Fix

Replace all `hash()` calls with `hashlib.sha256()`:

```python
# L20_OptionVol (fixed)
hv_seed = int(hashlib.sha256(sector.encode()).hexdigest(), 16) % 1000
code_hash = int(hashlib.sha256(etf_code.encode()).hexdigest(), 16) % 1000

# L13_MacroCycle (fixed)
h = int(hashlib.sha256(sector.encode()).hexdigest(), 16) % 40
```

## Verification

- Cross-process test: Same score (4.6) for 消费/159928 across separate Python processes
- Full batch: 50 ETFs, all layers show healthy distributions

## Files Modified

- `src/etf_platform/layers/l20_option_volatility.py` (v4.0 → v4.1)
- `src/etf_platform/layers/l12_macro_cycle.py` (v3.0 → v3.1)

## Lesson

**Never use `hash()` for deterministic scoring.** Always use `hashlib.sha256()` or similar cryptographic hash for reproducibility.
