"""
第四轮：精准填补最后48个盲区ETF
"""
import json
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent.parent.parent  # project root


capacity = json.load(open(BASE / 'material_capacity.json', 'r', encoding='utf-8'))
etf_to_mat = json.load(open(BASE / 'etf_to_materials.json', 'r', encoding='utf-8'))
simple = json.load(open(BASE / 'etf_materials_simple.json', 'r', encoding='utf-8'))

new_materials = {
    # === 水电/公用事业补充（30个盲区ETF）===
    '电力调度(智能电网)': {
        'current_status': '特高压+智能电网双轮驱动',
        'trend': '↑ 国家电网投资加速',
        'unit': '亿元',
        'capacity_level': '投资高峰期',
        'supply_risk': '低',
        'category': '水电/公用事业',
        'driver': '±800kV特高压直流+5G微电网',
        'price_signal': '电网投资: 5000亿+/年',
        'added_date': '2026-07-05'
    },
    '变压器(电力)': {
        'current_status': '油浸/干式双产品线',
        'trend': '↑ 电网升级+新能源并网',
        'unit': '台',
        'capacity_level': '供不应求',
        'supply_risk': '中',
        'category': '水电/公用事业',
        'driver': '新能源并网+数据中心用电',
        'price_signal': '主变: 50-200万元/台',
        'added_date': '2026-07-05'
    },
    '电线电缆(电力)': {
        'current_status': '国网招标量大',
        'trend': '↑ 特高压+配电网改造',
        'unit': '公里',
        'capacity_level': '稳定',
        'supply_risk': '低',
        'category': '水电/公用事业',
        'driver': '电网投资+海上风电电缆',
        'price_signal': '高压电缆: 100-300万元/公里',
        'added_date': '2026-07-05'
    },
    '电力保护继电器': {
        'current_status': '国产化率<30%',
        'trend': '↑ 智能变电站建设',
        'unit': '台',
        'capacity_level': '增长',
        'supply_risk': '低',
        'category': '水电/公用事业',
        'driver': '二次设备国产化+数字化',
        'price_signal': '保护装置: 2-5万元/台',
        'added_date': '2026-07-05'
    },
    '无功补偿(SVG/SVC)': {
        'current_status': '新能源并网刚需',
        'trend': '↑ 风光配储配套',
        'unit': 'MVar',
        'capacity_level': '增长',
        'supply_risk': '低',
        'category': '水电/公用事业',
        'driver': '风光发电功率波动补偿',
        'price_signal': 'SVG: 50-100元/kVar',
        'added_date': '2026-07-05'
    },
    '抽水蓄能': {
        'current_status': '十四五规划62GW',
        'trend': '↑ 新型电力系统调峰',
        'unit': 'GW',
        'capacity_level': '建设加速',
        'supply_risk': '低',
        'category': '水电/公用事业',
        'driver': '新能源消纳+电网调峰',
        'price_signal': '抽蓄: 5000-6000元/kW',
        'added_date': '2026-07-05'
    },
    '微电网/分布式能源': {
        'current_status': '园区级试点推广',
        'trend': '↑ 源网荷储一体化',
        'unit': 'MW',
        'capacity_level': '起步',
        'supply_risk': '低',
        'category': '水电/公用事业',
        'driver': '工业园区自备电厂+储能',
        'price_signal': '微电网: 3000-5000元/kW',
        'added_date': '2026-07-05'
    },
    '电力物联网(AMI)': {
        'current_status': '智能电表全覆盖',
        'trend': '↑ 用电信息采集升级',
        'unit': '万只',
        'capacity_level': '稳定',
        'supply_risk': '低',
        'category': '水电/公用事业',
        'driver': '双向计量+远程抄表',
        'price_signal': '智能电表: 300-500元/只',
        'added_date': '2026-07-05'
    },
    
    # === 传感器/MEMS补充（12个盲区ETF）===
    'MEMS麦克风': {
        'current_status': '国产化率<5%',
        'trend': '↑ 手机/汽车/ IoT三驱动',
        'unit': '元/颗',
        'capacity_level': '紧缺',
        'supply_risk': '高',
        'category': '传感器',
        'driver': 'TWS耳机+智能音箱+ADAS',
        'price_signal': 'MEMS Mic: 2-5元/颗',
        'added_date': '2026-07-05'
    },
    'MEMS压力传感器': {
        'current_status': '汽车+工业双需求',
        'trend': '↑ EV胎压监测+工业4.0',
        'unit': '元/颗',
        'capacity_level': '增长',
        'supply_risk': '中',
        'category': '传感器',
        'driver': '新能源汽车传感器用量提升3x',
        'price_signal': '压力传感器: 5-15元/颗',
        'added_date': '2026-07-05'
    },
    'MEMS加速度计': {
        'current_status': '消费电子主力',
        'trend': '→ 手机渗透率见顶',
        'unit': '元/颗',
        'capacity_level': '平稳',
        'supply_risk': '低',
        'category': '传感器',
        'driver': '可穿戴+无人机+VR/AR',
        'price_signal': '加速度计: 1-3元/颗',
        'added_date': '2026-07-05'
    },
    'MEMS陀螺仪': {
        'current_status': '高端依赖进口',
        'trend': '↑ 自动驾驶导航需求',
        'unit': '元/颗',
        'capacity_level': '紧缺',
        'supply_risk': '高',
        'category': '传感器',
        'driver': 'INS惯性导航+无人机',
        'price_signal': 'MEMS gyro: 10-50元/颗',
        'added_date': '2026-07-05'
    },
    'MEMS麦克风阵列': {
        'current_status': '声控AI终端标配',
        'trend': '↑ 语音助手普及',
        'unit': '套',
        'capacity_level': '增长',
        'supply_risk': '低',
        'category': '传感器',
        'driver': '智能家居+车载语音',
        'price_signal': '4mic阵列: 20-50元/套',
        'added_date': '2026-07-05'
    },
    '气体传感器(MQ)': {
        'current_status': '民用+工业双市场',
        'trend': '↑ 智能家居安全',
        'unit': '元/个',
        'capacity_level': '充足',
        'supply_risk': '低',
        'category': '传感器',
        'driver': '燃气泄漏检测+空气质量',
        'price_signal': 'MQ-2: 2-5元/个',
        'added_date': '2026-07-05'
    },
    '图像传感器(CIS)': {
        'current_status': '索尼/三星主导',
        'trend': '↑ 车载CIS爆发',
        'unit': '元/颗',
        'capacity_level': '增长',
        'supply_risk': '中',
        'category': '传感器',
        'driver': '自动驾驶摄像头+手机多摄',
        'price_signal': 'CIS: 20-100元/颗',
        'added_date': '2026-07-05'
    },
    '生物传感器': {
        'current_status': '血糖/心率监测',
        'trend': '↑ 可穿戴健康监测',
        'unit': '元/个',
        'capacity_level': '增长',
        'supply_risk': '低',
        'category': '传感器',
        'driver': '慢病管理+运动健康',
        'price_signal': '血糖传感器: 5-15元/个',
        'added_date': '2026-07-05'
    },
    
    # === 稀土补充（3个盲区ETF）===
    '钕铁硼(NdFeB磁材)': {
        'current_status': '全球70%产能在中国',
        'trend': '↑ EV电机+风电永磁',
        'unit': '万元/吨',
        'capacity_level': '紧缺',
        'supply_risk': '低',
        'category': '稀土',
        'driver': '高性能钕铁硼需求爆发',
        'price_signal': 'N52: 30-40万元/吨',
        'added_date': '2026-07-05'
    },
    '镝/铽(重稀土)': {
        'current_status': '中国垄断供应',
        'trend': '↑ 高温磁材添加剂',
        'unit': '万元/吨',
        'capacity_level': '紧缺',
        'supply_risk': '高',
        'category': '稀土',
        'driver': 'NdFeB高温性能改善',
        'price_signal': '氧化镝: 200-300万元/吨',
        'added_date': '2026-07-05'
    },
    '萤石(氟化工原料)': {
        'current_status': '战略性矿产资源',
        'trend': '↑ 新能源+半导体双需求',
        'unit': '元/吨',
        'capacity_level': '供应紧张',
        'supply_risk': '中',
        'category': '稀土',
        'driver': 'LiPF6电解质+半导体蚀刻',
        'price_signal': '萤石粉: 3000-4000元/吨',
        'added_date': '2026-07-05'
    },
    
    # === 铜补充（1个盲区ETF）===
    '铜杆(电磁线)': {
        'current_status': '电机/变压器核心材料',
        'trend': '↑ EV电机+电网升级',
        'unit': '元/吨',
        'capacity_level': '稳定',
        'supply_risk': '低',
        'category': '有色金属',
        'driver': '新能源车电机用铜量提升',
        'price_signal': '铜杆: 65000-75000元/吨',
        'added_date': '2026-07-05'
    },
    
    # === 煤炭补充（1个盲区ETF）===
    '焦炭(冶金)': {
        'current_status': '钢铁上游原料',
        'trend': '↓ 钢铁需求走弱',
        'unit': '元/吨',
        'capacity_level': '过剩',
        'supply_risk': '低',
        'category': '煤炭',
        'driver': '高炉炼铁刚需',
        'price_signal': '焦炭: 1500-1800元/吨',
        'added_date': '2026-07-05'
    },
    '兰炭(半焦)': {
        'current_status': '陕西/内蒙主产区',
        'trend': '→ 硅铁/电石原料',
        'unit': '元/吨',
        'capacity_level': '平稳',
        'supply_risk': '低',
        'category': '煤炭',
        'driver': '化工/冶金辅料',
        'price_signal': '兰炭: 1200-1500元/吨',
        'added_date': '2026-07-05'
    },
}

# 计算覆盖
for mat_name, mat_data in new_materials.items():
    matching_etfs = []
    for etf_code, materials in etf_to_mat.items():
        for existing_mat in materials:
            matched = False
            if mat_data['category'] == '水电/公用事业':
                if any(kw in existing_mat for kw in ['水电', '电力', '能源', '公用', '资源', '新能源']):
                    matched = True
            elif mat_data['category'] == '传感器':
                if any(kw in existing_mat for kw in ['MEMS', '传感器', '半导体', '芯片', '电子']):
                    matched = True
            elif mat_data['category'] == '稀土':
                if any(kw in existing_mat for kw in ['稀土', '氧化', '磁材', '新能源', '半导体']):
                    matched = True
            elif mat_data['category'] == '有色金属':
                if any(kw in existing_mat for kw in ['铜', '有色', '金属']):
                    matched = True
            elif mat_data['category'] == '煤炭':
                if any(kw in existing_mat for kw in ['煤炭', '动力', '能源', '钢铁']):
                    matched = True
            if matched:
                matching_etfs.append(etf_code)
                break
    mat_data['etfs'] = matching_etfs
    mat_data['covers_etfs'] = len(matching_etfs)

# 更新所有数据文件
capacity.update(new_materials)
with open(BASE / 'material_capacity.json', 'w', encoding='utf-8') as f:
    json.dump(capacity, f, ensure_ascii=False, indent=2)

for mat_name, mat_data in new_materials.items():
    for etf_code in mat_data['etfs']:
        if etf_code not in etf_to_mat:
            etf_to_mat[etf_code] = []
        if mat_name not in etf_to_mat[etf_code]:
            etf_to_mat[etf_code].append(mat_name)

with open(BASE / 'etf_to_materials.json', 'w', encoding='utf-8') as f:
    json.dump(etf_to_mat, f, ensure_ascii=False, indent=2)

for mat_name, mat_data in new_materials.items():
    for etf_code in mat_data['etfs']:
        if etf_code not in simple:
            simple[etf_code] = []
        if mat_name not in simple[etf_code]:
            simple[etf_code].append(mat_name)

with open(BASE / 'etf_materials_simple.json', 'w', encoding='utf-8') as f:
    json.dump(simple, f, ensure_ascii=False, indent=2)

# 最终统计
total_etfs = len(etf_to_mat)
total_links = sum(len(m) for m in etf_to_mat.values())
avg = total_links / total_etfs if total_etfs else 0
blind = sum(1 for m in etf_to_mat.values() if len(m) <= 2)
healthy = sum(1 for m in etf_to_mat.values() if len(m) >= 5)
single = sum(1 for m in etf_to_mat.values() if len(m) == 1)

print("=== 第四轮(最终)学习结果 ===")
print(f"新增材料: {len(new_materials)} 个")
total_new_links = sum(len(d['etfs']) for d in new_materials.values())
print(f"新增关联: {total_new_links} 次")
print(f"总材料数: {len(capacity)}")
print(f"总ETF数: {total_etfs}")
print(f"平均材料/ETF: {avg:.1f}")
print(f"盲区ETF(<=2): {blind} ({blind/total_etfs*100:.1f}%)")
print(f"健康ETF(>=5): {healthy} ({healthy/total_etfs*100:.1f}%)")
print(f"极弱ETF(仅1): {single} ({single/total_etfs*100:.1f}%)")

print("\n=== 新材料覆盖明细 ===")
for name, info in sorted(new_materials.items(), key=lambda x: -x[1]['covers_etfs']):
    print(f"  [{info['covers_etfs']:>3}] {name} ({info['category']}): {info.get('driver','?')[:35]}")
