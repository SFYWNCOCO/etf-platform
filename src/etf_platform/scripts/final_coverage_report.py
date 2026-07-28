import yaml
import sys
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent.parent.parent  # project root

# 添加src到路径
sys.path.insert(0, str(Path(str(BASE / 'src'))))

# 导入deep模块
from etf_platform.analysis.deep import get_all_materials, MATERIAL_PLUGIN_REGISTRY

# 加载配置
config_dir = Path(BASE / 'config')

# 1. 读取materials.yaml (ETF->材料映射)
with open(config_dir / 'materials.yaml', 'r', encoding='utf-8') as f:
    mat_config = yaml.load(f, Loader=yaml.FullLoader)
material_map = mat_config.get("material_map", {})

# 2. 读取etfs.yaml (ETF定义)
with open(config_dir / 'etfs.yaml', 'r', encoding='utf-8') as f:
    etf_config = yaml.safe_load(f)
etfs = etf_config.get("etfs", {})

# 3. 获取所有材料
all_materials = get_all_materials()
builtin_count = len([k for k in all_materials.keys() if k not in MATERIAL_PLUGIN_REGISTRY])
plugin_count = len(MATERIAL_PLUGIN_REGISTRY)
total_materials = len(all_materials)

# 4. 统计每个材料的覆盖ETF数
material_coverage = {}
for mat_name in all_materials.keys():
    covered = set()
    mat_info = all_materials[mat_name]
    affects = mat_info.get('affects', [])
    if isinstance(affects, list):
        for code in affects:
            if code in etfs:
                covered.add(code)
    for etf_code, mats in material_map.items():
        if isinstance(mats, dict) and mat_name in mats:
            covered.add(etf_code)
    if covered:
        material_coverage[mat_name] = covered

# 5. 统计总覆盖ETF
all_covered = set()
for etf_set in material_coverage.values():
    all_covered.update(etf_set)

# 6. 按类别分组
categories = {}
for mat_name, mat_info in all_materials.items():
    cat = mat_info.get('category', '其他')
    if cat not in categories:
        categories[cat] = []
    cov = len(material_coverage.get(mat_name, set()))
    categories[cat].append((mat_name, cov, mat_info.get('current', 'N/A')))

print("="*80)
print("ETF穿透评分系统 · 材料覆盖统计报告")
print("="*80)
print("\n📊 总计:")
print(f"  材料总数: {total_materials} (内置核心:{builtin_count} + 插件注册:{plugin_count})")
print(f"  ETF总数: {len(etfs)}")
print(f"  已覆盖ETF: {len(all_covered)} ({len(all_covered)/len(etfs)*100:.1f}%)")
print(f"  未覆盖ETF: {len(etfs) - len(all_covered)}")

print("\n📈 材料覆盖分布:")
cov_dist = {0:0, 1:0, 5:0, 10:0, 50:0, 100:0}
for mat_name, etf_set in material_coverage.items():
    c = len(etf_set)
    if c == 0: cov_dist[0] += 1
    elif c <= 1: cov_dist[1] += 1
    elif c <= 5: cov_dist[5] += 1
    elif c <= 10: cov_dist[10] += 1
    elif c <= 50: cov_dist[50] += 1
    else: cov_dist[100] += 1

for threshold in sorted(cov_dist.keys()):
    count = cov_dist[threshold]
    if count > 0:
        print(f"  覆盖{threshold}+ ETF: {count}个材料")

print("\n🏷️  按类别统计:")
for cat in sorted(categories.keys()):
    mats = categories[cat]
    mats.sort(key=lambda x: x[1], reverse=True)
    total_cov = sum(c for _, c, _ in mats)
    unique_cov = len(set().union(*[material_coverage.get(m[0], set()) for m in mats if m[0] in material_coverage]))
    print(f"\n  {cat} ({len(mats)}个材料, 覆盖{unique_cov}只ETF):")
    for name, cov, current in mats[:5]:
        print(f"    {name}: {cov} ETFs (当前:{current})")
    if len(mats) > 5:
        print(f"    ... 及其他{len(mats)-5}个材料")

print("\n🔝 Top 20 材料覆盖:")
sorted_mats = sorted(material_coverage.items(), key=lambda x: len(x[1]), reverse=True)
for i, (name, etf_set) in enumerate(sorted_mats[:20]):
    print(f"  {i+1:2d}. {name}: {len(etf_set)} ETFs")

print("\n" + "="*80)
