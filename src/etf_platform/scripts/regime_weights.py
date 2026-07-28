"""
Step2: 动态权重调整
根据市场regime调整各层权重
"""
import json
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent.parent.parent  # project root


# 定义不同市场regime下的权重调整
regime_weights = {
    'bull_market': {
        '半导体/电子': 1.2,
        '新能源/储能': 1.1,
        '传感器': 1.15,
        '半导体补充': 1.2,
        '军工': 1.1,
        '贵金属/稀有金属': 0.9,
        '水电/公用事业': 0.8,
        '医药生物': 1.0,
        '建材': 0.9,
        '金融': 1.1,
    },
    'bear_market': {
        '半导体/电子': 0.8,
        '新能源/储能': 0.9,
        '传感器': 0.85,
        '半导体补充': 0.8,
        '军工': 1.0,
        '贵金属/稀有金属': 1.2,
        '水电/公用事业': 1.1,
        '医药生物': 1.0,
        '建材': 0.7,
        '金融': 0.8,
    },
    'inflation_hedge': {
        '半导体/电子': 0.9,
        '新能源/储能': 1.0,
        '传感器': 0.9,
        '半导体补充': 0.9,
        '军工': 1.0,
        '贵金属/稀有金属': 1.3,
        '水电/公用事业': 1.1,
        '医药生物': 1.0,
        '建材': 0.9,
        '金融': 0.8,
    },
    'tech_bubble': {
        '半导体/电子': 1.3,
        '新能源/储能': 1.2,
        '传感器': 1.25,
        '半导体补充': 1.3,
        '军工': 1.1,
        '贵金属/稀有金属': 0.7,
        '水电/公用事业': 0.6,
        '医药生物': 1.0,
        '建材': 0.8,
        '金融': 1.0,
    },
    'recession': {
        '半导体/电子': 0.7,
        '新能源/储能': 0.8,
        '传感器': 0.75,
        '半导体补充': 0.7,
        '军工': 1.0,
        '贵金属/稀有金属': 1.2,
        '水电/公用事业': 1.1,
        '医药生物': 1.0,
        '建材': 0.6,
        '金融': 0.7,
    }
}

# 保存动态权重配置
with open(BASE / 'regime_weights.json', 'w', encoding='utf-8') as f:
    json.dump(regime_weights, f, ensure_ascii=False, indent=2)

print("="*60)
print("       动态权重调整配置")
print("="*60)
print()
print("已生成5种市场regime的权重调整配置:")
for regime, weights in regime_weights.items():
    print(f"  {regime}: {len(weights)}个类别")
    for cat, weight in sorted(weights.items(), key=lambda x: -x[1])[:3]:
        print(f"    {cat}: {weight}x")

print("\n动态权重配置已保存到 regime_weights.json")
print("\n使用说明:")
print("1. bull_market: 牛市，科技/新能源权重上调")
print("2. bear_market: 熊市，贵金属/公用事业权重上调")
print("3. inflation_hedge: 通胀对冲，贵金属/公用事业权重上调")
print("4. tech_bubble: 科技泡沫，半导体/传感器权重大幅上调")
print("5. recession: 衰退期，防御性板块权重上调")
