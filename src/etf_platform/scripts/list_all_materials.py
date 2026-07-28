import yaml
import sys
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent.parent.parent  # project root

sys.path.insert(0, str(Path(str(BASE / 'src'))))
from etf_platform.analysis.deep import get_all_materials, MATERIAL_PLUGIN_REGISTRY

config_dir = Path(BASE / 'config')
with open(config_dir / 'etfs.yaml', 'r', encoding='utf-8') as f:
    etf_config = yaml.safe_load(f)
etfs = etf_config.get("etfs", {})

all_materials = get_all_materials()
builtin_count = len([k for k in all_materials.keys() if k not in MATERIAL_PLUGIN_REGISTRY])
plugin_count = len(MATERIAL_PLUGIN_REGISTRY)
total_materials = len(all_materials)

# 统计每个材料的覆盖ETF数
material_coverage = {}
for mat_name in all_materials.keys():
    covered = set()
    mat_info = all_materials[mat_name]
    affects = mat_info.get('affects', [])
    if isinstance(affects, list):
        for code in affects:
            if code in etfs:
                covered.add(code)
    if covered:
        material_coverage[mat_name] = covered

# 按覆盖数排序
sorted_mats = sorted(material_coverage.items(), key=lambda x: len(x[1]), reverse=True)

# 手动分类规则
def classify_material(name):
    """根据材料名称自动分类"""
    name_lower = name.lower()
    
    # 半导体相关
    semi_keywords = ['碳化硅', '氮化镓', '光刻胶', 'LCP', 'PCB', 'EDA', 'HBM', '光芯片', '传感器', 'MEMS', 
                     '硅片', '晶圆', '封装', '半导体设备', '电子气体', 'CMP', '光掩模', 'ABF', 'SiC', 'GaN',
                     '石墨烯', 'MoS2', '二维材料', '隐身材料', '军工芯片', '射频']
    for kw in semi_keywords:
        if kw in name:
            return '半导体'
    
    # 新能源相关
    new_energy_keywords = ['固态电解质', '钠离子', '液流电池', '碳纤维', '绿氢', '氨', '光伏', '锂电', '储能',
                          '电池', '风电', '氢能', '钙钛矿', '锂辉石', '银浆', '光伏组件', '隔膜', '正极', '负极',
                          '逆变器', 'IGBT', '储能电芯', '固态电池']
    for kw in new_energy_keywords:
        if kw in name:
            return '新能源'
    
    # 周期资源相关
    resource_keywords = ['稀土', '锑', '铟', '镓', '锗', '铂族', '煤炭', '油气', '钢铁', '水泥', '化工',
                        '有色金属', '铝', '锌', '铅', '铜', '白银', '铀', '玻璃', '氦气', '高纯石英', '钛合金',
                        '高温合金', '气凝胶', '碳纳米管', '白炭黑', '糖', '乳制', '猪肉', '生猪']
    for kw in resource_keywords:
        if kw in name:
            return '周期资源'
    
    # 医药相关
    medical_keywords = ['mRNA', '基因测序', '创新药', '抗体', 'CXO', '中药', '医疗器械', '生物反应器',
                       '色谱填料', '药用玻璃', '原料药', 'API']
    for kw in medical_keywords:
        if kw in name:
            return '医药健康'
    
    # 金融相关
    finance_keywords = ['券商', '保险', '银行', '不良资产', '准备金', '碳信用']
    for kw in finance_keywords:
        if kw in name:
            return '金融服务'
    
    # 国防军工
    defense_keywords = ['军用', '航天', '雷达', 'T/R组件', '隐身', '推进剂']
    for kw in defense_keywords:
        if kw in name:
            return '国防军工'
    
    return '其他'

# 按分类统计
categories = {}
for mat_name, etf_set in sorted_mats:
    cat = classify_material(mat_name)
    if cat not in categories:
        categories[cat] = []
    categories[cat].append((mat_name, len(etf_set)))

print("="*120)
print(f"ETF穿透评分系统 · 全部{total_materials}个材料覆盖清单（已分类）")
print("="*120)
print(f"\n总计: {total_materials}个材料 (内置:{builtin_count} + 插件:{plugin_count})")
print(f"覆盖ETF: {len(set().union(*[s for _, s in sorted_mats]))}/{len(etfs)} ({len(set().union(*[s for _, s in sorted_mats]))/len(etfs)*100:.1f}%)")

# 按类别输出
print(f"\n{'='*120}")
print("按类别统计:")
print(f"{'='*120}")

for cat in sorted(categories.keys(), key=lambda x: sum(c for _, c in categories[x]), reverse=True):
    mats = categories[cat]
    total_cov = sum(c for _, c in mats)
    print(f"\n【{cat}】({len(mats)}个材料, 总覆盖{total_cov}次)")
    print(f"{'排名':<4} {'材料名称':<45} {'覆盖ETF':<8} {'当前状态'}")
    print(f"{'-'*100}")
    for i, (name, count) in enumerate(mats[:30]):  # 每类最多显示30个
        mat_info = all_materials.get(name, {})
        current = mat_info.get('current', 'N/A')
        if len(str(current)) > 30:
            current = str(current)[:30] + '..'
        print(f"{i+1:<4} {name:<45} {count:<8} {current}")
    if len(mats) > 30:
        print(f"... 及其他{len(mats)-30}个材料")

# 保存完整清单
with open(BASE / 'all_materials_list.txt', 'w', encoding='utf-8') as f:
    f.write(f"ETF穿透评分系统 · 全部{total_materials}个材料覆盖清单（已分类）\n")
    f.write("生成时间: 2026-07-05\n")
    f.write(f"总计: {total_materials}个材料 (内置:{builtin_count} + 插件:{plugin_count})\n")
    f.write(f"覆盖ETF: {len(set().union(*[s for _, s in sorted_mats]))}/{len(etfs)} ({len(set().union(*[s for _, s in sorted_mats]))/len(etfs)*100:.1f}%)\n\n")
    
    for cat in sorted(categories.keys(), key=lambda x: sum(c for _, c in categories[x]), reverse=True):
        mats = categories[cat]
        total_cov = sum(c for _, c in mats)
        f.write(f"\n【{cat}】({len(mats)}个材料, 总覆盖{total_cov}次)\n")
        f.write(f"{'排名':<4} {'材料名称':<45} {'覆盖ETF':<8} {'当前状态'}\n")
        f.write("-"*100 + "\n")
        for i, (name, count) in enumerate(mats):
            mat_info = all_materials.get(name, {})
            current = mat_info.get('current', 'N/A')
            if len(str(current)) > 30:
                current = str(current)[:30] + '..'
            f.write(f"{i+1:<4} {name:<45} {count:<8} {current}\n")

print("\n\n完整清单已保存至: docs/all_materials_list.txt")
