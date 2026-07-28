import json
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent.parent.parent  # project root


data = json.load(open(BASE / 'material_capacity.json', 'r', encoding='utf-8'))

keywords = ['硅','芯片','光','刻','砂','镓','锗','铟','锂','固','钒','钠','风','碳','氢','储','金','铜','银','铝','镍','钴','稀土','铂','钯','铬','钼','钨','油','气','煤','铁','钢','焦','豆','棉','糖','玉米','麦','菜','乳','猪','鸡','药','医','生','氟','磷','硫','氯','冰','水','盐']

others = []
for name, info in data.items():
    is_other = not any(kw in name for kw in keywords)
    if is_other:
        others.append((name, info))

# 按覆盖ETF数排序
others.sort(key=lambda x: -x[1].get('covers_etfs', 0))

print(f'"其他"类材料共 {len(others)} 个:')
print()
for name, info in others:
    etfs = info.get('covers_etfs', 0)
    status = info.get('current_status', '?')
    trend = info.get('trend', '?')
    print(f'[{etfs:>3}] {name}: {status[:35]} | 趋势: {trend}')
