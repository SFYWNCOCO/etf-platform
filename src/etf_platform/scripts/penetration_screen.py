"""
Step1: 穿透评分ETF筛选器
基于253个材料层的穿透评分，筛选高覆盖ETF
"""
import json
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent.parent.parent  # project root


capacity = json.load(open(BASE / 'material_capacity.json', 'r', encoding='utf-8'))
etf_to_mat = json.load(open(BASE / 'etf_to_materials.json', 'r', encoding='utf-8'))
scores = json.load(open(BASE / 'penetration_scores.json', 'r', encoding='utf-8'))

# 按穿透评分排序
sorted_scores = sorted(scores.items(), key=lambda x: -x[1])

print("="*60)
print("       穿透评分ETF筛选器")
print("="*60)
print()

# 筛选条件
min_score = 0.8
min_mats = 15

print(f"筛选条件: 评分>={min_score}, 材料数>={min_mats}")
print()

qualified = [(etf, score, len(etf_to_mat[etf])) for etf, score in sorted_scores 
             if score >= min_score and len(etf_to_mat[etf]) >= min_mats]

print(f"符合条件的ETF: {len(qualified)}个")
print()
print("--- TOP 20 高穿透评分ETF ---")
for etf, score, mat_count in qualified[:20]:
    mats = etf_to_mat[etf]
    # 提取主要材料类别
    categories = set()
    for m in mats:
        if m in capacity:
            cat = capacity[m].get('category', '未知')
            categories.add(cat)
    cat_str = ', '.join(list(categories)[:3])
    print(f"  {etf}: {score:.3f} | 材料:{mat_count} | 类别: {cat_str}")

# 按类别统计
print("\n--- 高穿透ETF类别分布 ---")
cat_dist = {}
for etf, score, mat_count in qualified:
    for m in etf_to_mat[etf]:
        if m in capacity:
            cat = capacity[m].get('category', '未知')
            cat_dist[cat] = cat_dist.get(cat, 0) + 1

for c, n in sorted(cat_dist.items(), key=lambda x: -x[1])[:10]:
    print(f"  {c}: {n}次")

# 保存筛选结果
with open(BASE / 'screened_etfs.json', 'w', encoding='utf-8') as f:
    json.dump([{'etf': etf, 'score': score, 'mat_count': mat_count} for etf, score, mat_count in qualified], 
              f, ensure_ascii=False, indent=2)

print("\n筛选结果已保存到 screened_etfs.json")
