"""
Step4修正: 实时监控预警
材料价格波动→ETF穿透评分变化预警（修正计算逻辑）
"""
import json
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent.parent.parent  # project root


capacity = json.load(open(BASE / 'material_capacity.json', 'r', encoding='utf-8'))
etf_to_mat = json.load(open(BASE / 'etf_to_materials.json', 'r', encoding='utf-8'))
scores = json.load(open(BASE / 'penetration_scores.json', 'r', encoding='utf-8'))

# 定义材料权重（用于计算ETF评分贡献）
material_weights = {
    '碳化硅(SiC)衬底': 0.9, '氮化镓(GaN)外延片': 0.85, 'MEMS麦克风': 0.7,
    '光掩模版(光罩)': 0.8, 'ABF封装基板': 0.85, '钕铁硼(NdFeB磁材)': 0.8,
    '固态电解质(硫化物)': 0.8, '锂辉石(6%Li2O)': 0.6, '钴': 0.5,
    '铜(电解铜)': 0.5,
}

# 模拟材料价格波动
price_changes = {
    '碳化硅(SiC)衬底': 0.15,
    '氮化镓(GaN)外延片': 0.08,
    '固态电解质(硫化物)': 0.25,
    '锂辉石(6%Li2O)': -0.10,
    '钴': -0.15,
    '铜(电解铜)': 0.05,
    'MEMS麦克风': 0.10,
    '光掩模版(光罩)': 0.12,
    'ABF封装基板': 0.08,
    '钕铁硼(NdFeB磁材)': 0.06,
}

# 修正后的计算：加权平均
impact = {}
for etf, mats in etf_to_mat.items():
    total_weight = sum(material_weights.get(m, 0.5) for m in mats)
    if total_weight == 0:
        continue
    
    weighted_price_change = 0
    weight_sum = 0
    for m in mats:
        w = material_weights.get(m, 0.5)
        pc = price_changes.get(m, 0)
        weighted_price_change += w * pc
        weight_sum += w
    
    # 加权平均价格变动
    avg_price_change = weighted_price_change / weight_sum if weight_sum > 0 else 0
    
    # ETF评分变动 = 加权平均价格变动 × 评分（评分越高，敏感度越高）
    etf_score = scores.get(etf, 0)
    impact[etf] = avg_price_change * etf_score

# 生成预警报告
alerts = []
for etf, total_impact in sorted(impact.items(), key=lambda x: -abs(x[1]))[:10]:
    if abs(total_impact) > 0.001:  # 影响超过0.1%
        alerts.append({
            'etf': etf,
            'impact': total_impact,
            'severity': 'high' if abs(total_impact) > 0.05 else 'medium' if abs(total_impact) > 0.02 else 'low'
        })

print("="*60)
print("       Step4修正: 材料价格波动预警报告")
print("="*60)
print(f"\n预警ETF数量: {len(alerts)}")
print("\n--- 高影响预警 ---")
for alert in alerts[:5]:
    print(f"  {alert['etf']}: {alert['impact']*100:+.2f}% ({alert['severity']})")

with open(BASE / 'price_alerts_fixed.json', 'w', encoding='utf-8') as f:
    json.dump(alerts, f, ensure_ascii=False, indent=2)

print("\n预警数据已保存到 price_alerts_fixed.json")
