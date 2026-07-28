import sys
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent.parent.parent  # project root

sys.path.insert(0, str(Path(str(BASE / 'src'))))
from etf_platform.analysis.deep import get_all_materials, MATERIAL_PLUGIN_REGISTRY

all_materials = get_all_materials()
builtin_count = len([k for k in all_materials.keys() if k not in MATERIAL_PLUGIN_REGISTRY])
plugin_count = len(MATERIAL_PLUGIN_REGISTRY)
total_materials = len(all_materials)

# 打印所有材料的完整信息，包括category字段
print("="*120)
print(f"ETF穿透评分系统 · 全部{total_materials}个材料详细清单")
print("="*120)
print(f"\n总计: {total_materials}个材料 (内置:{builtin_count} + 插件:{plugin_count})")

# 检查每个材料的category字段
uncategorized = []
categorized = {}

for mat_name, mat_info in all_materials.items():
    cat = mat_info.get('category', None)
    if cat is None or cat == '其他':
        uncategorized.append(mat_name)
    else:
        if cat not in categorized:
            categorized[cat] = []
        categorized[cat].append(mat_name)

print(f"\n有category字段的材料: {len(categorized)}个类别")
for cat, mats in categorized.items():
    print(f"  {cat}: {len(mats)}个材料")

print(f"\n未设置category的材料: {len(uncategorized)}个")
print("前20个未分类材料:")
for name in uncategorized[:20]:
    print(f"  - {name}")

# 检查MATERIAL_PLUGIN_REGISTRY的来源
print("\n\n插件注册表来源分析:")
sources = {}
for mat_name, mat_info in MATERIAL_PLUGIN_REGISTRY.items():
    source = mat_info.get('_source', 'unknown')
    if source not in sources:
        sources[source] = []
    sources[source].append(mat_name)

for source, mats in sources.items():
    print(f"  {source}: {len(mats)}个材料")

# 检查所有材料的字段结构
print("\n\n材料字段结构示例 (前5个):")
for i, (name, info) in enumerate(list(all_materials.items())[:5]):
    print(f"\n{i+1}. {name}")
    print(f"   字段: {list(info.keys())}")
    print(f"   category: {info.get('category', 'N/A')}")
    print(f"   affects: {info.get('affects', 'N/A')[:50]}..." if isinstance(info.get('affects'), list) and len(info.get('affects', [])) > 10 else f"   affects: {info.get('affects', 'N/A')}")
    print(f"   current: {info.get('current', 'N/A')[:50]}")
    print(f"   _source: {info.get('_source', 'N/A')}")
