import sys
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent.parent.parent  # project root

sys.path.insert(0, str(Path(str(BASE / 'src'))))
from etf_platform.analysis.deep import get_all_materials

# 获取所有材料
all_materials = get_all_materials()

# 衍生材料关键词
derived_keywords = ['衍生', '复合', '纳米', '涂层', '薄膜', '合金', '陶瓷', '树脂', '纤维', '膜', '浆料', '胶膜', '靶材', '垫片', '模块']
derived_materials = {}
for mat_name, mat_data in all_materials.items():
    for kw in derived_keywords:
        if kw in mat_name:
            derived_materials[mat_name] = mat_data
            break

# 按ETF覆盖数排序
sorted_materials = sorted(derived_materials.items(), key=lambda x: len(x[1].get('affects', [])), reverse=True)

# 输出结果
print('='*80)
print('ETF穿透系统 · 衍生材料详细报告')
print('='*80)
print(f'\n总计: {len(sorted_materials)}个衍生材料')
print('\n衍生材料覆盖ETF数排名:')
for i, (name, data) in enumerate(sorted_materials, 1):
    affects = data.get('affects', [])
    current = data.get('current', 'N/A')
    trend = data.get('trend', 'N/A')
    note = data.get('note', 'N/A')
    supplier = data.get('supplier_regions', {})
    
    print(f'\n{i:3d}. {name}')
    print(f'    覆盖ETF数: {len(affects)}')
    print(f'    当前状态: {current}')
    print(f'    趋势: {trend}')
    print(f'    备注: {note}')
    if supplier:
        print(f'    供应商分布: {supplier}')

# 统计信息
total_etf_coverage = sum(len(data.get('affects', [])) for _, data in sorted_materials)
print('\n\n衍生材料总覆盖ETF数:', total_etf_coverage)
print('平均覆盖ETF数:', total_etf_coverage // len(sorted_materials) if sorted_materials else 0)
