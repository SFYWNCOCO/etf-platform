"""
Step4: 实时监控预警
材料价格波动→ETF穿透评分变化预警
"""
import json
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent.parent.parent  # project root


# 加载数据
capacity = json.load(open(BASE / 'material_capacity.json', 'r', encoding='utf-8'))
etf_to_mat = json.load(open(BASE / 'etf_to_materials.json', 'r', encoding='utf-8'))
scores = json.load(open(BASE / 'penetration_scores.json', 'r', encoding='utf-8'))

# 模拟材料价格波动
price_changes = {
    '碳化硅(SiC)衬底': 0.15,  # +15%
    '氮化镓(GaN)外延片': 0.08,  # +8%
    '固态电解质(硫化物)': 0.25,  # +25%
    '锂辉石(6%Li2O)': -0.10,  # -10%
    '钴': -0.15,  # -15%
    '铜(电解铜)': 0.05,  # +5%
}

# 计算对ETF穿透评分的影响
impact = {}
for mat, change in price_changes.items():
    affected_etfs = []
    for etf, mats in etf_to_mat.items():
        if mat in mats:
            old_score = scores.get(etf, 0)
            # 简化计算：材料价格变动±10% → ETF评分变动±2%
            new_score = old_score * (1 + change * 0.2)
            impact[etf] = impact.get(etf, 0) + change * 0.2
            affected_etfs.append(etf)
    
    if affected_etfs:
        print(f"材料: {mat} ({change*100:+.0f}%)")
        print(f"  影响ETF数: {len(affected_etfs)}")
        print(f"  代表ETF: {affected_etfs[:3]}")
        print()

# 生成预警报告
alerts = []
for etf, total_impact in sorted(impact.items(), key=lambda x: -abs(x[1]))[:10]:
    if abs(total_impact) > 0.01:  # 影响超过1%
        alerts.append({
            'etf': etf,
            'impact': total_impact,
            'severity': 'high' if abs(total_impact) > 0.05 else 'medium' if abs(total_impact) > 0.02 else 'low'
        })

print("="*60)
print("       材料价格波动预警报告")
print("="*60)
print()
print(f"预警ETF数量: {len(alerts)}")
print()
print("--- 高影响预警 ---")
for alert in alerts[:5]:
    if alert['severity'] == 'high':
        print(f"  {alert['etf']}: {alert['impact']*100:+.2f}% ({alert['severity']})")

# 保存预警数据
with open(BASE / 'price_alerts.json', 'w', encoding='utf-8') as f:
    json.dump(alerts, f, ensure_ascii=False, indent=2)

print("\n预警数据已保存到 price_alerts.json")
print("\n监控建议:")
print("1. 设置材料价格波动阈值(±5%)触发预警")
print("2. 高频材料(半导体/新能源)优先监控")
print("3. 结合市场regime调整预警灵敏度")
