"""
第三轮学习：精准打击盲区ETF
策略：针对84个盲区ETF，补充其所属主题的材料层
"""
import json
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent.parent.parent  # project root


capacity = json.load(open(BASE / 'material_capacity.json', 'r', encoding='utf-8'))
etf_to_mat = json.load(open(BASE / 'etf_to_materials.json', 'r', encoding='utf-8'))

# 找出所有盲区ETF及其现有材料
blind_etfs = {etf: mats for etf, mats in etf_to_mat.items() if len(mats) <= 2}

# 按现有材料推断ETF主题
def infer_theme(materials):
    themes = []
    for m in materials:
        if any(kw in m for kw in ['水电','水资源','公用']):
            themes.append('水电/公用事业')
        elif any(kw in m for kw in ['券商','经纪']):
            themes.append('券商/金融')
        elif any(kw in m for kw in ['保险','偿付']):
            themes.append('保险')
        elif any(kw in m for kw in ['银行','不良']):
            themes.append('银行')
        elif any(kw in m for kw in ['铜','电解']):
            themes.append('有色金属')
        elif any(kw in m for kw in ['煤炭','动力']):
            themes.append('煤炭')
        elif any(kw in m for kw in ['油气','原油']):
            themes.append('油气')
        elif any(kw in m for kw in ['稀土','氧化']):
            themes.append('稀土')
        elif any(kw in m for kw in ['乳制','原奶']):
            themes.append('乳业')
        elif any(kw in m for kw in ['MEMS','传感器']):
            themes.append('半导体/电子')
        elif any(kw in m for kw in ['生猪','猪肉']):
            themes.append('养殖')
        elif any(kw in m for kw in ['糖','白糖']):
            themes.append('农产品')
        elif any(kw in m for kw in ['医药','CXO']):
            themes.append('医药')
        elif any(kw in m for kw in ['白酒','酒类']):
            themes.append('白酒/消费')
        else:
            themes.append('未知')
    return themes if themes else ['未知']

# 统计盲区主题分布
theme_count = {}
for etf, mats in blind_etfs.items():
    theme = infer_theme(mats)[0]
    theme_count[theme] = theme_count.get(theme, 0) + 1

print("=== 盲区ETF主题分布 ===")
for t, c in sorted(theme_count.items(), key=lambda x: -x[1]):
    print(f"  {t}: {c}个ETF")

# 列出各主题的代表性盲区ETF
print("\n=== 各主题盲区ETF示例 ===")
for theme in ['券商/金融', '保险', '银行', '养殖', '乳业', '油气', '煤炭', '白酒/消费', '医药', '有色金属']:
    examples = [etf for etf, mats in blind_etfs.items() if theme in infer_theme(mats)]
    if examples:
        print(f"\n{theme} ({len(examples)}个):")
        for etf in examples[:5]:
            mats = blind_etfs[etf]
            print(f"  {etf}: {mats}")
