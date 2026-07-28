"""
分析22个未知主题的盲区ETF
"""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent.parent
DATA = BASE / 'data'
etf_to_mat = json.load(open(DATA / 'etf_to_materials.json', 'r', encoding='utf-8'))
simple = json.load(open(DATA / 'etf_materials_simple.json', 'r', encoding='utf-8'))
capacity = json.load(open(DATA / 'material_capacity.json', 'r', encoding='utf-8'))

# 找出所有盲区ETF
blind = {k:v for k,v in etf_to_mat.items() if len(v) <= 2}

# 未知主题的定义：现有材料不包含水电/券商/保险/银行/养殖/乳业/油气/煤炭/稀土/医药/MEMS
known_keywords = ['水电','水资源','公用','券商','经纪','保险','偿付','银行','不良','养殖','乳制','原奶','油气','原油','煤炭','动力','稀土','氧化','医药','CXO','MEMS','传感器','生猪','猪肉','糖','白糖']

unknown = []
for etf, mats in blind.items():
    mat_str = ' '.join(mats)
    if not any(kw in mat_str for kw in known_keywords):
        unknown.append((etf, mats))

print(f"=== 未知主题盲区ETF ({len(unknown)}个) ===")
for etf, mats in unknown:
    # 从simple中看这个ETF有哪些材料
    simple_mats = simple.get(etf, [])
    print(f"  {etf}: capacity材料={mats}, simple材料={simple_mats[:5]}")

# 再细分：按simple中的材料推断
print("\n=== 按simple材料推断未知主题 ===")
from collections import Counter
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent.parent.parent  # project root

simple_theme = Counter()
for etf, mats in unknown:
    simple_mats = simple.get(etf, [])
    for sm in simple_mats:
        if any(kw in sm for kw in ['水泥','熟料']):
            simple_theme['建材/水泥'] += 1
        elif any(kw in sm for kw in ['降解','塑料']):
            simple_theme['环保/降解'] += 1
        elif any(kw in sm for kw in ['化工','聚氨酯']):
            simple_theme['化工'] += 1
        elif any(kw in sm for kw in ['钢铁','螺纹']):
            simple_theme['钢铁'] += 1
        elif any(kw in sm for kw in ['有色','铝','锌']):
            simple_theme['工业有色'] += 1
        elif any(kw in sm for kw in ['农化','化肥']):
            simple_theme['农化'] += 1
        elif any(kw in sm for kw in ['军工','国防']):
            simple_theme['军工'] += 1
        elif any(kw in sm for kw in ['游戏','传媒']):
            simple_theme['传媒/游戏'] += 1
        elif any(kw in sm for kw in ['旅游','酒店']):
            simple_theme['旅游'] += 1
        elif any(kw in sm for kw in ['教育']):
            simple_theme['教育'] += 1
        elif any(kw in sm for kw in ['食品','饮料']):
            simple_theme['食品饮料'] += 1
        elif any(kw in sm for kw in ['纺织','服装']):
            simple_theme['纺织'] += 1
        else:
            simple_theme[f'其他({sm})'] += 1

for t, c in simple_theme.most_common():
    print(f"  {t}: {c}个")
