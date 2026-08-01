# L12 Political Risk — Data Completeness Fix (v8.11)

## Issue
13 sectors were missing from at least one of the 4 political risk dictionaries (REGULATORY_INTENSITY, GEOPOLITICAL_EXPOSURE, EPU_BY_SECTOR, GPR_BY_SECTOR). Missing sectors defaulted to 0.5 across all 4 dicts, producing a composite score of exactly 5.0 — causing 23% clustering at 5.0.

## Root Cause
Incremental development of political_risk.py added entries to some dicts but not all. The `calculate_political_risk_score()` function uses `.get(sector, 0.5)` for each dict independently, so missing entries silently produced the same 5.0 default.

## Fix
Added 14 new sector entries across all 4 dictionaries:
- 金融(0.95), 银行(0.95), 房地产(0.90), 电池(0.65), 农牧(0.55), CXO/创新药(0.85), 畜牧(0.55), 钢铁(0.30), 通信/光模块(0.70), 有色(0.40), 互联网(0.85), 教育(0.95), 成长股(0.35)

## Result
L12 std improved from 1.18 to 1.31 (GOOD→EXCELLENT).

## Lesson
Always maintain parallel dictionaries. When adding a sector to one dict, add to ALL related dicts simultaneously. Consider a validation script that checks all dicts have the same sector keys.
