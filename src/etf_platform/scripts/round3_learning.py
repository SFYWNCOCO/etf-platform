"""
材料层第三轮学习：精准填补84个盲区ETF
主题：金融类+医疗+贵金属+建材+钢铁+养殖乳业+军工+周期
"""
import json
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent.parent.parent  # project root


capacity = json.load(open(BASE / 'material_capacity.json', 'r', encoding='utf-8'))
etf_to_mat = json.load(open(BASE / 'etf_to_materials.json', 'r', encoding='utf-8'))
simple = json.load(open(BASE / 'etf_materials_simple.json', 'r', encoding='utf-8'))

# 第三轮新材料：针对84个盲区ETF的主题精准补充
new_materials = {
    # === 金融类（填补券商/保险/银行盲区7个ETF）===
    '证券经纪佣金率': {
        'current_status': '万分之2.5(行业平均)',
        'trend': '↓ 佣金率持续下行',
        'unit': '%',
        'capacity_level': '内卷',
        'supply_risk': '低',
        'category': '金融',
        'driver': '互联网券商低价竞争+两融利率下行',
        'price_signal': '万2.5→万1.5趋势',
        'added_date': '2026-07-05'
    },
    '融资融券余额': {
        'current_status': '1.8-2.0万亿元',
        'trend': '↑ 市场活跃度指标',
        'unit': '万亿元',
        'capacity_level': '波动',
        'supply_risk': '低',
        'category': '金融',
        'driver': '杠杆资金情绪指标',
        'price_signal': '融资余额占A股流通市值1.5%',
        'added_date': '2026-07-05'
    },
    'IPO承销规模': {
        'current_status': '注册制全面落地',
        'trend': '↑ 科创板+创业板扩容',
        'unit': '亿元',
        'capacity_level': '活跃',
        'supply_risk': '低',
        'category': '金融',
        'driver': '直接融资占比提升',
        'price_signal': '2024年IPO募资~2000亿',
        'added_date': '2026-07-05'
    },
    '保险新业务价值': {
        'current_status': '寿险改革深化',
        'trend': '↑ 代理人产能提升',
        'unit': '亿元',
        'capacity_level': '复苏',
        'supply_risk': '低',
        'category': '金融',
        'driver': '养老/健康险需求增长',
        'price_signal': 'NBV margin 35-40%',
        'added_date': '2026-07-05'
    },
    '银行净息差(NIM)': {
        'current_status': '1.5-1.7%',
        'trend': '↓ LPR降息压力',
        'unit': '%',
        'capacity_level': '收窄',
        'supply_risk': '低',
        'category': '金融',
        'driver': '让利实体经济+存款定期化',
        'price_signal': '1.5%接近历史低位',
        'added_date': '2026-07-05'
    },
    
    # === 医疗器械类（填补8个医疗影像盲区ETF）===
    'CT球管': {
        'current_status': '国产化率<15%',
        'trend': '↑ 国产替代加速',
        'unit': '万元/支',
        'capacity_level': '供不应求',
        'supply_risk': '中',
        'category': '医疗',
        'driver': 'CT设备装机量增长+球管耗材属性',
        'price_signal': '进口: 8-12万元/支',
        'added_date': '2026-07-05'
    },
    'DR探测器': {
        'current_status': '国产化率<20%',
        'trend': '↑ 基层医疗建设',
        'unit': '万元/套',
        'capacity_level': '稳定',
        'supply_risk': '中',
        'category': '医疗',
        'driver': '县级医院DR配置率提升',
        'price_signal': '平板探测器: 5-8万元/套',
        'added_date': '2026-07-05'
    },
    '超声探头': {
        'current_status': '国产化率<10%',
        'trend': '↑ 高端彩超国产突破',
        'unit': '万元/个',
        'capacity_level': '紧缺',
        'supply_risk': '高',
        'category': '医疗',
        'driver': '压电陶瓷材料+微电子封装',
        'price_signal': '进口探头: 3-5万元/个',
        'added_date': '2026-07-05'
    },
    'MRI超导磁体': {
        'current_status': '完全依赖进口',
        'trend': '↑ 国产MRI突破',
        'unit': '套',
        'capacity_level': '垄断',
        'supply_risk': '高',
        'category': '医疗',
        'driver': '3.0T MRI国产化攻关',
        'price_signal': 'NbTi超导线: 200-300元/米',
        'added_date': '2026-07-05'
    },
    '内镜镜头': {
        'current_status': '国产化率<5%',
        'trend': '↑ 消化内镜渗透率提升',
        'unit': '万元/套',
        'capacity_level': '紧缺',
        'supply_risk': '高',
        'category': '医疗',
        'driver': '早筛意识提升+老龄化',
        'price_signal': '奥林巴斯: 10-20万元/套',
        'added_date': '2026-07-05'
    },
    '医用影像胶片': {
        'current_status': '数字化替代中',
        'trend': '↓ PACS系统替代',
        'unit': '元/张',
        'capacity_level': '萎缩',
        'supply_risk': '低',
        'category': '医疗',
        'driver': '云影像+数字阅片替代',
        'price_signal': '胶片: 5-10元/张',
        'added_date': '2026-07-05'
    },
    'PET/CT示踪剂(18F-FDG)': {
        'current_status': '依赖医用同位素',
        'trend': '↑ 肿瘤筛查需求',
        'unit': 'MBq',
        'capacity_level': '紧缺',
        'supply_risk': '高',
        'category': '医疗',
        'driver': '核医学中心建设加速',
        'price_signal': 'F-18: 依赖加速器生产',
        'added_date': '2026-07-05'
    },
    '医用机器人(手术导航)': {
        'current_status': '国产化率<10%',
        'trend': '↑ 微创手术渗透',
        'unit': '台',
        'capacity_level': '起步',
        'supply_risk': '中',
        'category': '医疗',
        'driver': '达芬奇替代+骨科机器人',
        'price_signal': '手术机器人: 1000-2000万/台',
        'added_date': '2026-07-05'
    },
    
    # === 贵金属类（填补白银/铂金盲区6-8个ETF）===
    '银(工业用)': {
        'current_status': '光伏银浆需求爆发',
        'trend': '↑ 光伏+电子双驱动',
        'unit': '元/千克',
        'capacity_level': '供应紧张',
        'supply_risk': '中',
        'category': '贵金属',
        'driver': '光伏银浆占工业用银40%+',
        'price_signal': '现货银: 6500-7500元/千克',
        'added_date': '2026-07-05'
    },
    '铂(汽车催化)': {
        'current_status': '南非供应集中',
        'trend': '→ 氢能燃料电池新需求',
        'unit': '元/克',
        'capacity_level': '稳定',
        'supply_risk': '中',
        'category': '贵金属',
        'driver': '氢燃料电池Pt催化剂需求',
        'price_signal': '铂: 250-300元/克',
        'added_date': '2026-07-05'
    },
    '钯(汽车催化)': {
        'current_status': '俄/南非供应集中',
        'trend': '↓ 替代趋势(铂代钯)',
        'unit': '元/克',
        'capacity_level': '波动',
        'supply_risk': '中',
        'category': '贵金属',
        'driver': '国六标准催化转化器',
        'price_signal': '钯: 400-500元/克',
        'added_date': '2026-07-05'
    },
    '铑(汽车催化)': {
        'current_status': '全球最小众贵金属',
        'trend': '↑ 尾气处理刚需',
        'unit': '元/克',
        'capacity_level': '极度紧缺',
        'supply_risk': '高',
        'category': '贵金属',
        'driver': '国六B标准提升铑用量',
        'price_signal': '铑: 2000-3000元/克',
        'added_date': '2026-07-05'
    },
    '钌(电子浆料)': {
        'current_status': '稀有铂族金属',
        'trend': '↑ MLCC终端电阻需求',
        'unit': '元/克',
        'capacity_level': '紧缺',
        'supply_risk': '高',
        'category': '贵金属',
        'driver': '电子元器件MLCC扩产',
        'price_signal': '钌: 300-400元/克',
        'added_date': '2026-07-05'
    },
    '铱(溅射靶材)': {
        'current_status': '全球年产量<3吨',
        'trend': '↑ OLED发光层需求',
        'unit': '元/克',
        'capacity_level': '极度紧缺',
        'supply_risk': '极高',
        'category': '贵金属',
        'driver': 'OLED/phosphor材料',
        'price_signal': '铱: 8000-10000元/克',
        'added_date': '2026-07-05'
    },
    
    # === 建材/玻璃类（填补4个玻璃盲区ETF）===
    '光伏玻璃(3.2mm)': {
        'current_status': '产能过剩',
        'trend': '↓ 价格战激烈',
        'unit': '元/平米',
        'capacity_level': '过剩',
        'supply_risk': '低',
        'category': '建材',
        'driver': '光伏装机拉动+产能集中释放',
        'price_signal': '3.2mm: 16-20元/平米',
        'added_date': '2026-07-05'
    },
    'Low-E镀膜玻璃': {
        'current_status': '建筑节能强制标准',
        'trend': '↑ 绿色建筑政策推动',
        'unit': '元/平米',
        'capacity_level': '增长',
        'supply_risk': '低',
        'category': '建材',
        'driver': '双碳+建筑能耗标准提升',
        'price_signal': 'Low-E: 60-80元/平米',
        'added_date': '2026-07-05'
    },
    '钢化玻璃': {
        'current_status': '地产竣工下滑',
        'trend': '↓ 新房需求走弱',
        'unit': '元/平米',
        'capacity_level': '过剩',
        'supply_risk': '低',
        'category': '建材',
        'driver': '建筑安全标准提升',
        'price_signal': '钢化: 30-50元/平米',
        'added_date': '2026-07-05'
    },
    '中空玻璃': {
        'current_status': '节能门窗配套',
        'trend': '→ 存量改造市场稳定',
        'unit': '元/平米',
        'capacity_level': '平稳',
        'supply_risk': '低',
        'category': '建材',
        'driver': '既有建筑节能改造',
        'price_signal': '中空: 50-70元/平米',
        'added_date': '2026-07-05'
    },
    '玻璃纤维(玻纤)': {
        'current_status': '产能扩张',
        'trend': '→ 风电/汽车/电子多应用',
        'unit': '元/吨',
        'capacity_level': '过剩',
        'supply_risk': '低',
        'category': '建材',
        'driver': 'E-glass/C-glass多品类',
        'price_signal': 'E-glass: 3500-4500元/吨',
        'added_date': '2026-07-05'
    },
    '工程塑料(PA/PBT)': {
        'current_status': '新能源车轻量化',
        'trend': '↑ 以塑代钢趋势',
        'unit': '元/吨',
        'capacity_level': '增长',
        'supply_risk': '低',
        'category': '建材',
        'driver': '汽车轻量化+电子电器',
        'price_signal': 'PA66: 25000-30000元/吨',
        'added_date': '2026-07-05'
    },
    
    # === 钢铁类（填补1个钢铁盲区ETF）===
    '热轧卷板(HRC)': {
        'current_status': '地产+制造业双需求',
        'trend': '↓ 地产拖累明显',
        'unit': '元/吨',
        'capacity_level': '过剩',
        'supply_risk': '低',
        'category': '钢铁',
        'driver': '制造业PMI vs 地产投资',
        'price_signal': 'HRC: 3500-4000元/吨',
        'added_date': '2026-07-05'
    },
    '冷轧卷板(CRC)': {
        'current_status': '家电/汽车需求稳定',
        'trend': '→ 镀锌板替代',
        'unit': '元/吨',
        'capacity_level': '平稳',
        'supply_risk': '低',
        'category': '钢铁',
        'driver': '汽车/家电用钢',
        'price_signal': 'CRC: 4000-4500元/吨',
        'added_date': '2026-07-05'
    },
    '不锈钢(304/430)': {
        'current_status': '产能扩张',
        'trend': '→ 化工/食品需求',
        'unit': '元/吨',
        'capacity_level': '过剩',
        'supply_risk': '低',
        'category': '钢铁',
        'driver': '镍铁供应充足',
        'price_signal': '304: 13000-15000元/吨',
        'added_date': '2026-07-05'
    },
    '硅钢(取向/无取向)': {
        'current_status': '电机/变压器核心材料',
        'trend': '↑ 新能源车+电网升级',
        'unit': '元/吨',
        'capacity_level': '紧缺',
        'supply_risk': '中',
        'category': '钢铁',
        'driver': 'EV电机+变压器硅钢需求',
        'price_signal': '取向硅钢: 6000-8000元/吨',
        'added_date': '2026-07-05'
    },
    '钒钢(微合金化)': {
        'current_status': '高强度钢添加剂',
        'trend': '→ 建筑/桥梁用钢',
        'unit': '元/吨',
        'capacity_level': '稳定',
        'supply_risk': '低',
        'category': '钢铁',
        'driver': '抗震钢材标准提升',
        'price_signal': '钒铁: 8-10万元/吨',
        'added_date': '2026-07-05'
    },
    
    # === 养殖/乳业类（填补5-6个乳业盲区ETF）===
    '饲料原料(豆粕/棉粕)': {
        'current_status': '进口大豆依赖度80%',
        'trend': '↓ 国际粮价回落',
        'unit': '元/吨',
        'capacity_level': '平稳',
        'supply_risk': '中',
        'category': '养殖/乳业',
        'driver': '中美贸易+南美大豆',
        'price_signal': '豆粕: 3000-3500元/吨',
        'added_date': '2026-07-05'
    },
    '兽用疫苗(口蹄疫/禽流感)': {
        'current_status': '强制免疫+商业化疫苗',
        'trend': '↑ 非瘟常态化防控',
        'unit': '头份',
        'capacity_level': '增长',
        'supply_risk': '低',
        'category': '养殖/乳业',
        'driver': '规模化养殖防疫升级',
        'price_signal': '口蹄疫疫苗: 0.5-1元/头份',
        'added_date': '2026-07-05'
    },
    '宠物食品': {
        'current_status': '国产替代进口',
        'trend': '↑ 宠物经济爆发',
        'unit': '元/kg',
        'capacity_level': '快速增长',
        'supply_risk': '低',
        'category': '养殖/乳业',
        'driver': '单身经济+情感消费',
        'price_signal': '干粮: 30-80元/kg',
        'added_date': '2026-07-05'
    },
    '奶粉(成人/中老年)': {
        'current_status': '国产份额提升',
        'trend': '↑ 老龄化+健康意识',
        'unit': '元/kg',
        'capacity_level': '竞争',
        'supply_risk': '低',
        'category': '养殖/乳业',
        'driver': '中老年营养需求',
        'price_signal': '成人奶粉: 80-150元/kg',
        'added_date': '2026-07-05'
    },
    '酸奶/乳酸菌': {
        'current_status': '常温+低温双渠道',
        'trend': '↑ 益生菌概念渗透',
        'unit': '元/杯',
        'capacity_level': '红海',
        'supply_risk': '低',
        'category': '养殖/乳业',
        'driver': '肠道健康消费升级',
        'price_signal': '低温酸奶: 3-8元/杯',
        'added_date': '2026-07-05'
    },
    
    # === 军工补充（填补隐身/雷达相关ETF）===
    '军用碳纤维': {
        'current_status': '国产化率<80%',
        'trend': '↑ 军用航空/导弹需求',
        'unit': '万元/吨',
        'capacity_level': '紧缺',
        'supply_risk': '中',
        'category': '军工',
        'driver': '歼-20/运-20/无人机量产',
        'price_signal': 'T700军用: 300-500万元/吨',
        'added_date': '2026-07-05'
    },
    '军用钛合金(TC4)': {
        'current_status': '航空发动机+机身结构',
        'trend': '↑ 军机换代',
        'unit': '万元/吨',
        'capacity_level': '紧缺',
        'supply_risk': '中',
        'category': '军工',
        'driver': '三代机向四代机升级',
        'price_signal': 'TC4钛合金: 20-30万元/吨',
        'added_date': '2026-07-05'
    },
    '军用复合材料(蜂窝夹层)': {
        'current_status': '战斗机/直升机蒙皮',
        'trend': '↑ 隐身+减重需求',
        'unit': '万元/吨',
        'capacity_level': '紧缺',
        'supply_risk': '中',
        'category': '军工',
        'driver': '复合材料替代铝合金',
        'price_signal': '蜂窝芯: 50-100万元/吨',
        'added_date': '2026-07-05'
    },
    '军用连接器': {
        'current_status': '国产化率<30%',
        'trend': '↑ 信息化装备放量',
        'unit': '元/个',
        'capacity_level': '增长',
        'supply_risk': '中',
        'category': '军工',
        'driver': '导弹/雷达/通信系统',
        'price_signal': '军用连接器: 50-500元/个',
        'added_date': '2026-07-05'
    },
    '军用芯片(抗辐射)': {
        'current_status': '完全自主可控',
        'trend': '↑ 航天/导弹需求',
        'unit': '元/颗',
        'capacity_level': '紧缺',
        'supply_risk': '高',
        'category': '军工',
        'driver': '抗辐射加固CPU/FPGA',
        'price_signal': '抗辐射芯片: 500-5000元/颗',
        'added_date': '2026-07-05'
    },
    '军用高温合金(Inconel)': {
        'current_status': '航空发动机涡轮叶片',
        'trend': '↑ 军用航空换代',
        'unit': '万元/吨',
        'capacity_level': '紧缺',
        'supply_risk': '高',
        'category': '军工',
        'driver': '涡扇发动机寿命延长',
        'price_signal': 'Inconel718: 30-50万元/吨',
        'added_date': '2026-07-05'
    },
}

# 计算每个新材料覆盖的ETF
for mat_name, mat_data in new_materials.items():
    matching_etfs = []
    for etf_code, materials in etf_to_mat.items():
        for existing_mat in materials:
            matched = False
            if mat_data['category'] == '金融':
                if any(kw in existing_mat for kw in ['券商', '经纪', '银行', '保险', '金融']):
                    matched = True
            elif mat_data['category'] == '医疗':
                if any(kw in existing_mat for kw in ['医疗器械', '影像', '医疗', 'CXO', '医药']):
                    matched = True
            elif mat_data['category'] == '贵金属':
                if any(kw in existing_mat for kw in ['白银', '铂', '金', '钯', '铑', '贵金属', '有色']):
                    matched = True
            elif mat_data['category'] == '建材':
                if any(kw in existing_mat for kw in ['玻璃', '建材', '水泥', '房地产']):
                    matched = True
            elif mat_data['category'] == '钢铁':
                if any(kw in existing_mat for kw in ['钢铁', '螺纹', '钢', '汽车钢']):
                    matched = True
            elif mat_data['category'] == '养殖/乳业':
                if any(kw in existing_mat for kw in ['乳制', '养殖', '猪', '饲料', '农产']):
                    matched = True
            elif mat_data['category'] == '军工':
                if any(kw in existing_mat for kw in ['军工', '隐身', '雷达', '航天', '航空', '钛合金', '高温合金']):
                    matched = True
            if matched:
                matching_etfs.append(etf_code)
                break
    
    mat_data['etfs'] = matching_etfs
    mat_data['covers_etfs'] = len(matching_etfs)

# 更新capacity
capacity.update(new_materials)
with open(BASE / 'material_capacity.json', 'w', encoding='utf-8') as f:
    json.dump(capacity, f, ensure_ascii=False, indent=2)

# 更新etf_to_materials
for mat_name, mat_data in new_materials.items():
    for etf_code in mat_data['etfs']:
        if etf_code not in etf_to_mat:
            etf_to_mat[etf_code] = []
        if mat_name not in etf_to_mat[etf_code]:
            etf_to_mat[etf_code].append(mat_name)

with open(BASE / 'etf_to_materials.json', 'w', encoding='utf-8') as f:
    json.dump(etf_to_mat, f, ensure_ascii=False, indent=2)

# 更新simple
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
total_links = sum(len(m) for m in etf_to_mat.values())
avg = total_links / total_etfs if total_etfs else 0
blind = sum(1 for m in etf_to_mat.values() if len(m) <= 2)
healthy = sum(1 for m in etf_to_mat.values() if len(m) >= 5)

print("=== 第三轮学习结果 ===")
print(f"新增材料: {len(new_materials)} 个")
total_new_links = sum(len(d['etfs']) for d in new_materials.values())
print(f"新增关联: {total_new_links} 次")
print(f"总材料数: {len(capacity)}")
print(f"总ETF数: {total_etfs}")
print(f"平均材料/ETF: {avg:.1f}")
print(f"盲区ETF(<=2): {blind} ({blind/total_etfs*100:.1f}%)")
print(f"健康ETF(>=5): {healthy} ({healthy/total_etfs*100:.1f}%)")

# 每个新材料覆盖明细
print("\n=== 新材料覆盖明细 ===")
for name, info in sorted(new_materials.items(), key=lambda x: -x[1]['covers_etfs']):
    print(f"  [{info['covers_etfs']:>3}] {name} ({info['category']}): {info.get('driver','?')[:35]}")
