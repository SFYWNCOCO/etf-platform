"""
数据一致性审核
"""
import json
import os
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent.parent.parent  # project root


data_dir = BASE / 'data'

files = [
    'material_capacity.json',
    'etf_to_materials.json',
    'penetration_scores.json',
    'screened_etfs.json',
    'regime_weights.json',
    'price_alerts_fixed.json',
    'code_audit_report.json',
]

print("="*60)
print("       数据文件一致性审核")
print("="*60)

for f in files:
    fpath = os.path.join(data_dir, f)
    if os.path.exists(fpath):
        size = os.path.getsize(fpath)
        try:
            data = json.load(open(fpath, 'r', encoding='utf-8'))
            if isinstance(data, dict):
                keys = len(data.keys())
                print(f"  OK {f}: {size/1024:.1f}KB, {keys} keys")
            elif isinstance(data, list):
                print(f"  OK {f}: {size/1024:.1f}KB, {len(data)} items")
            else:
                print(f"  OK {f}: {size/1024:.1f}KB, {type(data).__name__}")
        except Exception as e:
            print(f"  FAIL {f}: {size/1024:.1f}KB, parse error: {e}")
    else:
        print(f"  FAIL {f}: file not found")

print("\n--- 材料层一致性 ---")
capacity = json.load(open(os.path.join(data_dir, 'material_capacity.json'), 'r', encoding='utf-8'))
etf_to_mat = json.load(open(os.path.join(data_dir, 'etf_to_materials.json'), 'r', encoding='utf-8'))
scores = json.load(open(os.path.join(data_dir, 'penetration_scores.json'), 'r', encoding='utf-8'))

print(f"  Materials: {len(capacity)}")
print(f"  ETFs: {len(etf_to_mat)}")
print(f"  Scores: {len(scores)}")

missing_scores = [etf for etf in etf_to_mat if etf not in scores]
if missing_scores:
    print(f"  FAIL {len(missing_scores)} ETFs missing scores")
else:
    print("  OK All ETFs have scores")

score_values = list(scores.values())
print(f"  Score range: {min(score_values):.3f} - {max(score_values):.3f}")
print(f"  Score mean: {sum(score_values)/len(score_values):.3f}")

all_mats_in_etf = set()
for mats in etf_to_mat.values():
    all_mats_in_etf.update(mats)

missing_mats = [m for m in all_mats_in_etf if m not in capacity]
if missing_mats:
    print(f"  FAIL {len(missing_mats)} materials referenced but not in capacity")
else:
    print("  OK All ETF materials exist in capacity")

exist_count = len([f for f in files if os.path.exists(os.path.join(data_dir, f))])
total_size = sum(os.path.getsize(os.path.join(data_dir, f)) for f in files if os.path.exists(os.path.join(data_dir, f)))
print("\n--- Data Summary ---")
print(f"  Total data size: {total_size/1024:.1f}KB")
print(f"  Data files: {exist_count}/{len(files)}")
