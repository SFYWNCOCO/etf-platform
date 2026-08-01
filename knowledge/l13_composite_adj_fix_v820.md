# L13 MacroCycle composite_adj Double-Counting Fix (v8.20)

## Date
2026-07-09

## Issue
L13_MacroCycle `composite_adj` was inflated for sectors where `_resolve_sector()` returned multiple mapped sectors. The accumulation formula `composite *= adj` multiplied adjustments, causing double-counting.

### Example
- "AI/科技" resolves to ["AI/科技", "AI算力"]
- AI/科技 adj=1.18, AI算力 adj=1.25
- Old: composite = 1.18 × 1.25 = 1.475 (inflated!)
- New: composite = max(1.18, 1.25) = 1.25 (correct for adj > 1.0)

### Fix Logic
- **adj > 1.0**: Use `max()` to prevent double-counting (aliases for same concept shouldn't compound)
- **adj < 1.0**: Keep `multiply()` because multiple weak sectors should compound risk

### Affected Sectors (Upward Adj)
| Sector | Old ca | New ca |
|--------|--------|--------|
| AI/科技 | 1.475 | 1.25 |
| 半导体 | 1.44 | 1.20 |
| 硬科技 | 1.44 | 1.20 |
| 云计算/算力 | 1.56 | 1.25 |
| AI算力 | 1.56 | 1.25 |

### Unchanged (Downward Adj - single sector)
| Sector | ca |
|--------|-----|
| 公用事业 | 0.85 |
| 金融 | 0.90 |
| 煤炭 | 0.80 |
| 房地产 | 0.80 |

## Fix
Changed `composite *= adj` to conditional: `max()` for adj > 1.0, `multiply()` for adj < 1.0, in `l12_macro_cycle.py:get_cycle_adjustments()`.

## Verification
- All 98 tests pass
- 0 ETFs with ca > 1.3 post-fix (was 2)
- Range restored to [0.8, 1.25]
- Downward adjustments preserved correctly
