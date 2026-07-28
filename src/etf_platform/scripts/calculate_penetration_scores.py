"""
穿透评分优化：基于材料层数据的ETF穿透评分计算
目标：将253个材料转化为可操作的穿透评分
"""
import json
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent.parent.parent  # project root


capacity = json.load(open(BASE / 'material_capacity.json', 'r', encoding='utf-8'))
etf_to_mat = json.load(open(BASE / 'etf_to_materials.json', 'r', encoding='utf-8'))

# 定义材料权重（基于驱动因素强度）
material_weights = {
    # 半导体类（高权重）
    '碳化硅(SiC)衬底': 0.9, '氮化镓(GaN)外延片': 0.85, '二维材料(石墨烯/MoS2)': 0.7,
    '固态电解质(硫化物)': 0.8, '钠离子电池': 0.7, '全钒液流电池': 0.65,
    '风电叶片碳纤维': 0.75, '镓/锗金属': 0.8, '铟(ITO靶材)': 0.75,
    'MEMS麦克风': 0.7, 'MEMS压力传感器': 0.75, 'MEMS加速度计': 0.65,
    'MEMS陀螺仪': 0.8, 'MEMS麦克风阵列': 0.7, '气体传感器(MQ)': 0.5,
    '图像传感器(CIS)': 0.85, '生物传感器': 0.6,
    '钕铁硼(NdFeB磁材)': 0.8, '镝/铽(重稀土)': 0.75, '萤石(氟化工原料)': 0.65,
    '电力调度(智能电网)': 0.7, '变压器(电力)': 0.65, '电线电缆(电力)': 0.6,
    '电力保护继电器': 0.55, '无功补偿(SVG/SVC)': 0.6, '抽水蓄能': 0.7,
    '微电网/分布式能源': 0.65, '电力物联网(AMI)': 0.55,
    'CT球管': 0.7, 'DR探测器': 0.65, '超声探头': 0.7, 'MRI超导磁体': 0.75,
    '内镜镜头': 0.6, '医用影像胶片': 0.4, 'PET/CT示踪剂(18F-FDG)': 0.65,
    '医用机器人(手术导航)': 0.7,
    '银(工业用)': 0.7, '铂(汽车催化)': 0.65, '钯(汽车催化)': 0.6,
    '铑(汽车催化)': 0.55, '钌(电子浆料)': 0.5, '铱(溅射靶材)': 0.45,
    '光伏玻璃(3.2mm)': 0.6, 'Low-E镀膜玻璃': 0.55, '钢化玻璃': 0.5,
    '中空玻璃': 0.45, '玻璃纤维(玻纤)': 0.55, '工程塑料(PA/PBT)': 0.5,
    '热轧卷板(HRC)': 0.45, '冷轧卷板(CRC)': 0.4, '不锈钢(304/430)': 0.35,
    '硅钢(取向/无取向)': 0.6, '钒钢(微合金化)': 0.4,
    '饲料原料(豆粕/棉粕)': 0.4, '兽用疫苗(口蹄疫/禽流感)': 0.45,
    '宠物食品': 0.5, '奶粉(成人/中老年)': 0.35, '酸奶/乳酸菌': 0.3,
    '军用碳纤维': 0.7, '军用钛合金(TC4)': 0.65, '军用复合材料(蜂窝夹层)': 0.6,
    '军用连接器': 0.55, '军用芯片(抗辐射)': 0.7, '军用高温合金(Inconel)': 0.65,
    '证券经纪佣金率': 0.3, '融资融券余额': 0.35, 'IPO承销规模': 0.4,
    '保险新业务价值': 0.35, '银行净息差(NIM)': 0.3,
    '风电(整机+塔筒)': 0.7, '综合能源服务': 0.65, '火电(煤电一体化)': 0.5,
    '配售电改革': 0.45, '天然气管网': 0.55, '太阳能发电(电站运营)': 0.6,
    '水电(装机容量)': 0.55, '核电(商用反应堆)': 0.65,
    '光掩模版(光罩)': 0.8, 'CMP抛光液': 0.75, '电子特气(高纯)': 0.7,
    '高纯氢氟酸': 0.65, '光刻胶(KrF/i-line)': 0.6, '硅片(8英寸)': 0.55,
    '氦气(高纯He-4)': 0.7, 'ABF封装基板': 0.85,
    '铜杆(电磁线)': 0.5, '焦炭(冶金)': 0.4, '兰炭(半焦)': 0.35,
}

# 计算每个ETF的穿透评分
def calculate_penetration_score(etf_code):
    materials = etf_to_mat.get(etf_code, [])
    if not materials:
        return 0.0
    
    total_weight = 0
    for mat in materials:
        w = material_weights.get(mat, 0.5)  # 默认权重
        total_weight += w
    
    # 归一化：平均权重 * 材料数量系数
    avg_weight = total_weight / len(materials)
    quantity_factor = min(len(materials) / 10, 1.5)  # 最多1.5倍
    
    score = avg_weight * quantity_factor
    return round(score, 3)

# 计算所有ETF的穿透评分
scores = {}
for etf in etf_to_mat:
    scores[etf] = calculate_penetration_score(etf)

# 按分数排序
sorted_scores = sorted(scores.items(), key=lambda x: -x[1])

print("=== 穿透评分TOP 20 ===")
for etf, score in sorted_scores[:20]:
    mats = etf_to_mat[etf]
    print(f"  {etf}: {score:.3f} | 材料数: {len(mats)}")
    if len(mats) <= 5:
        print(f"    材料: {mats}")

print("\n=== 穿透评分统计 ===")
print(f"总ETF数: {len(scores)}")
print(f"平均分: {sum(scores.values())/len(scores):.3f}")
print(f"最高分: {max(scores.values()):.3f}")
print(f"最低分: {min(scores.values()):.3f}")

# 保存穿透评分
with open(BASE / 'penetration_scores.json', 'w', encoding='utf-8') as f:
    json.dump(scores, f, ensure_ascii=False, indent=2)

print("\n穿透评分已保存到 penetration_scores.json")
