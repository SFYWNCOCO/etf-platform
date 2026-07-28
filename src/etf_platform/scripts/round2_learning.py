"""
材料层第二轮学习：水电/能源 + 半导体补充材料
目标：填补96个盲区ETF的材料缺口，提升覆盖率到65%+
"""
import json
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent.parent.parent  # project root


# 加载现有数据
capacity = json.load(open(BASE / 'material_capacity.json', 'r', encoding='utf-8'))
simple = json.load(open(BASE / 'etf_materials_simple.json', 'r', encoding='utf-8'))
etf_to_mat = json.load(open(BASE / 'etf_to_materials.json', 'r', encoding='utf-8'))

# 新加入的材料数据（基于行业研究和公开数据）
new_materials = {
    # === 水电/能源类 ===
    '水电(装机容量)': {
        'current_status': '4.2亿kW(全球第一)',
        'trend': '↑ 十四五末目标5.5亿kW',
        'unit': '亿千瓦',
        'capacity_level': '全球领先',
        'supply_risk': '低',
        'covers_etfs': 0,
        'etfs': [],
        'category': '水电/能源',
        'driver': '三峡+溪洛渡+白鹤滩等六大基地投产',
        'price_signal': 'N/A',
        'added_date': '2026-07-05'
    },
    '火电(煤电一体化)': {
        'current_status': '13亿kW装机',
        'trend': '→ 煤电定位转向调节性电源',
        'unit': '亿千瓦',
        'capacity_level': '过剩',
        'supply_risk': '低',
        'covers_etfs': 0,
        'etfs': [],
        'category': '水电/能源',
        'driver': '容量电价机制落地+煤电联营',
        'price_signal': '动力煤5500大卡: 750-850元/吨',
        'added_date': '2026-07-05'
    },
    '核电(商用反应堆)': {
        'current_status': '55GW在运/25GW在建',
        'trend': '↑ 审批常态化6-8台/年',
        'unit': 'GW',
        'capacity_level': '审批加速',
        'supply_risk': '低',
        'covers_etfs': 0,
        'etfs': [],
        'category': '水电/能源',
        'driver': '双碳目标+基荷电源不可替代',
        'price_signal': 'U3O8: $60-80/lb',
        'added_date': '2026-07-05'
    },
    '风电(整机+塔筒)': {
        'current_status': '3.7亿kW装机',
        'trend': '↑ 海上风电招标放量',
        'unit': '亿千瓦',
        'capacity_level': '陆上过剩/海上紧缺',
        'supply_risk': '低',
        'covers_etfs': 0,
        'etfs': [],
        'category': '水电/能源',
        'driver': '15MW+大型风机降本',
        'price_signal': '陆上风机: 3500-4000元/kW',
        'added_date': '2026-07-05'
    },
    '太阳能发电(电站运营)': {
        'current_status': '6.1亿kW光伏装机',
        'trend': '↑ 分布式+集中式双增',
        'unit': '亿千瓦',
        'capacity_level': '产能过剩',
        'supply_risk': '低',
        'covers_etfs': 0,
        'etfs': [],
        'category': '水电/能源',
        'driver': '平价上网+绿电交易',
        'price_signal': '组件: 0.8-1.0元/W',
        'added_date': '2026-07-05'
    },
    '天然气管网': {
        'current_status': '12万公里',
        'trend': '↑ 国家管网公司整合',
        'unit': '万公里',
        'capacity_level': '扩张期',
        'supply_risk': '中',
        'covers_etfs': 0,
        'etfs': [],
        'category': '水电/能源',
        'driver': '天然气占一次能源目标12%',
        'price_signal': 'LNG: $12-15/MMBtu',
        'added_date': '2026-07-05'
    },
    '配售电改革': {
        'current_status': '增量配电试点200+',
        'trend': '→ 试点扩围缓慢',
        'unit': '个',
        'capacity_level': '试点期',
        'supply_risk': '低',
        'covers_etfs': 0,
        'etfs': [],
        'category': '水电/能源',
        'driver': '电价市场化改革',
        'price_signal': 'N/A',
        'added_date': '2026-07-05'
    },
    '综合能源服务': {
        'current_status': '万亿级市场',
        'trend': '↑ 节能+碳管理+微电网',
        'unit': '亿元',
        'capacity_level': '快速增长',
        'supply_risk': '低',
        'covers_etfs': 0,
        'etfs': [],
        'category': '水电/能源',
        'driver': '双碳+能效提升政策',
        'price_signal': 'N/A',
        'added_date': '2026-07-05'
    },
    # === 半导体补充材料 ===
    '光掩模版(光罩)': {
        'current_status': '国产化率<15%',
        'trend': '↑ AI芯片设计复杂度提升',
        'unit': '万元/张',
        'capacity_level': '供应紧张',
        'supply_risk': '中',
        'covers_etfs': 0,
        'etfs': [],
        'category': '半导体补充',
        'driver': '7nm以下多重曝光需求',
        'price_signal': 'EUV光罩: $5-10万/张',
        'added_date': '2026-07-05'
    },
    'CMP抛光液': {
        'current_status': '国产化率<20%',
        'trend': '↑ 先进制程用量倍增',
        'unit': '元/升',
        'capacity_level': '供不应求',
        'supply_risk': '中',
        'covers_etfs': 0,
        'etfs': [],
        'category': '半导体补充',
        'driver': '3D NAND层数增加→CMP步骤增多',
        'price_signal': '铜抛光液: 3-5万元/吨',
        'added_date': '2026-07-05'
    },
    '电子特气(高纯)': {
        'current_status': '国产化率<30%',
        'trend': '↑ 国产替代加速',
        'unit': '元/立方米',
        'capacity_level': '紧张',
        'supply_risk': '中',
        'covers_etfs': 0,
        'etfs': [],
        'category': '半导体补充',
        'driver': '刻蚀/沉积/掺杂工艺刚需',
        'price_signal': 'NF3: 8000-12000元/钢瓶',
        'added_date': '2026-07-05'
    },
    '高纯氢氟酸': {
        'current_status': '国产化率<25%',
        'trend': '↑ 半导体清洗需求',
        'unit': '元/吨',
        'capacity_level': '紧平衡',
        'supply_risk': '中',
        'covers_etfs': 0,
        'etfs': [],
        'category': '半导体补充',
        'driver': '湿法清洗步骤占比40%+',
        'price_signal': '电子级HF: 2-3万元/吨',
        'added_date': '2026-07-05'
    },
    '光刻胶(KrF/i-line)': {
        'current_status': 'KrF国产化率<10%',
        'trend': '→ 成熟制程稳定增长',
        'unit': '元/升',
        'capacity_level': '供应充足',
        'supply_risk': '中',
        'covers_etfs': 0,
        'etfs': [],
        'category': '半导体补充',
        'driver': '28nm以上制程主力光刻胶',
        'price_signal': 'KrF: 8-12万元/升',
        'added_date': '2026-07-05'
    },
    '硅片(8英寸)': {
        'current_status': '国产化率<20%',
        'trend': '→ 功率器件/IoT主力',
        'unit': '英寸',
        'capacity_level': '平稳',
        'supply_risk': '低',
        'covers_etfs': 0,
        'etfs': [],
        'category': '半导体补充',
        'driver': 'IGBT/MCU/传感器需求稳定',
        'price_signal': '8寸硅片: 200-300元/片',
        'added_date': '2026-07-05'
    },
    '氦气(高纯He-4)': {
        'current_status': '90%依赖进口',
        'trend': '↑ 半导体/超导/航天三重需求',
        'unit': '元/立方米',
        'capacity_level': '供应紧张',
        'supply_risk': '高',
        'covers_etfs': 0,
        'etfs': [],
        'category': '半导体补充',
        'driver': '半导体检漏/吹扫+MRI超导冷却',
        'price_signal': '高纯He: 300-500元/m³',
        'added_date': '2026-07-05'
    },
    'ABF封装基板': {
        'current_status': '国产化率<5%',
        'trend': '↑ AI芯片CoWoS瓶颈',
        'unit': '元/平米',
        'capacity_level': '严重供不应求',
        'supply_risk': '高',
        'covers_etfs': 0,
        'etfs': [],
        'category': '半导体补充',
        'driver': 'HBM+AI GPU封装需求爆发',
        'price_signal': 'ABF载板: 800-1500元/平米',
        'added_date': '2026-07-05'
    },
}

# 计算每个新材料覆盖的ETF
updated_count = 0
for mat_name, mat_data in new_materials.items():
    # 找出包含这个材料相关关键词的ETF
    matching_etfs = []
    for etf_code, materials in etf_to_mat.items():
        # 如果ETF已有类似材料，说明它应该也覆盖新材料
        for existing_mat in materials:
            # 基于行业逻辑判断关联
            if mat_name.startswith('水电') and any(kw in existing_mat for kw in ['水电', '能源', '公用', '资源']):
                matching_etfs.append(etf_code)
                break
            if mat_name.startswith('火电') and any(kw in existing_mat for kw in ['火电', '煤电', '电力']):
                matching_etfs.append(etf_code)
                break
            if mat_name.startswith('核电') and any(kw in existing_mat for kw in ['核电', '铀', '能源']):
                matching_etfs.append(etf_code)
                break
            if mat_name.startswith('风电') and any(kw in existing_mat for kw in ['风电', '能源', '碳']):
                matching_etfs.append(etf_code)
                break
            if mat_name.startswith('太阳能') and any(kw in existing_mat for kw in ['光伏', '太阳能', '新能源']):
                matching_etfs.append(etf_code)
                break
            if mat_name.startswith('天然气') and any(kw in existing_mat for kw in ['天然气', '油气', '能源']):
                matching_etfs.append(etf_code)
                break
            if mat_name.startswith('配售电') and any(kw in existing_mat for kw in ['电力', '能源', '公用']):
                matching_etfs.append(etf_code)
                break
            if mat_name.startswith('综合能源') and any(kw in existing_mat for kw in ['能源', '公用', '碳']):
                matching_etfs.append(etf_code)
                break
            if mat_name.startswith('光掩模') and any(kw in existing_mat for kw in ['光刻胶', '半导体', '芯片', 'EDA']):
                matching_etfs.append(etf_code)
                break
            if mat_name.startswith('CMP') and any(kw in existing_mat for kw in ['硅片', '半导体', '芯片', '抛光']):
                matching_etfs.append(etf_code)
                break
            if mat_name.startswith('电子特气') and any(kw in existing_mat for kw in ['半导体', '芯片', '硅片', '光刻胶']):
                matching_etfs.append(etf_code)
                break
            if mat_name.startswith('高纯氢氟酸') and any(kw in existing_mat for kw in ['半导体', '芯片', '硅片', '电子']):
                matching_etfs.append(etf_code)
                break
            if mat_name.startswith('光刻胶(KrF') and any(kw in existing_mat for kw in ['光刻胶', '半导体', '芯片']):
                matching_etfs.append(etf_code)
                break
            if mat_name.startswith('硅片(8英寸)') and any(kw in existing_mat for kw in ['硅片', '半导体', '芯片', '功率']):
                matching_etfs.append(etf_code)
                break
            if mat_name.startswith('氦气') and any(kw in existing_mat for kw in ['半导体', '芯片', 'HBM', '氦']):
                matching_etfs.append(etf_code)
                break
            if mat_name.startswith('ABF封装') and any(kw in existing_mat for kw in ['封装', '基板', 'HBM', '半导体', '芯片']):
                matching_etfs.append(etf_code)
                break
    
    mat_data['etfs'] = matching_etfs
    mat_data['covers_etfs'] = len(matching_etfs)
    updated_count += len(matching_etfs)

# 写入material_capacity.json
capacity.update(new_materials)
with open(BASE / 'material_capacity.json', 'w', encoding='utf-8') as f:
    json.dump(capacity, f, ensure_ascii=False, indent=2)

# 更新etf_to_materials映射
for mat_name, mat_data in new_materials.items():
    for etf_code in mat_data['etfs']:
        if etf_code not in etf_to_mat:
            etf_to_mat[etf_code] = []
        if mat_name not in etf_to_mat[etf_code]:
            etf_to_mat[etf_code].append(mat_name)

with open(BASE / 'etf_to_materials.json', 'w', encoding='utf-8') as f:
    json.dump(etf_to_mat, f, ensure_ascii=False, indent=2)

# 更新etf_materials_simple
for mat_name, mat_data in new_materials.items():
    for etf_code in mat_data['etfs']:
        if etf_code not in simple:
            simple[etf_code] = []
        if mat_name not in simple[etf_code]:
            simple[etf_code].append(mat_name)

with open(BASE / 'etf_materials_simple.json', 'w', encoding='utf-8') as f:
    json.dump(simple, f, ensure_ascii=False, indent=2)

# 统计
total_etfs = len(etf_to_mat)
coverage = sum(len(mats) for mats in etf_to_mat.values())
avg_coverage = coverage / total_etfs if total_etfs > 0 else 0
blind_etfs = sum(1 for mats in etf_to_mat.values() if len(mats) <= 2)

print("=== 第二轮学习结果 ===")
print(f"新增材料: {len(new_materials)} 个")
print(f"关联ETF: {updated_count} 次")
print(f"总ETF数: {total_etfs}")
print(f"平均材料覆盖: {avg_coverage:.1f} 个/ETF")
print(f"盲区ETF(<=2材料): {blind_etfs} 个")

# 打印每个新材料的覆盖情况
print("\n=== 新材料覆盖明细 ===")
for name, info in sorted(new_materials.items(), key=lambda x: -x[1]['covers_etfs']):
    print(f"  [{info['covers_etfs']:>3}] {name}: {info.get('driver','?')[:40]}")
