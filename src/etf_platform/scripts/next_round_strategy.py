"""
材料层学习策略：下一轮新增材料优先级排序
基于盲区分析 + 覆盖潜力评估
"""
import json
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent.parent.parent  # project root


data = json.load(open(BASE / 'material_capacity.json', 'r', encoding='utf-8'))
etf_to_mat = json.load(open(BASE / 'etf_to_materials.json', 'r', encoding='utf-8'))

# 策略1：为"水电燃料/水资源"盲区ETF补充更多材料
# 这些ETF（512040, 512890, 510880, 159263, 159691等）只覆盖了1个材料
# 水电/公用事业ETF应该覆盖的材料：
water_energy_materials = [
    ('水电(装机容量)', 'N/A', '↑ 三峡+溪洛渡等六大基地投产'),
    ('火电(煤电一体化)', 'N/A', '→ 煤电联动+容量电价'),
    ('核电(商用 reactors)', '$N/A', '↑ 审批加速6-8台/年'),
    ('风电(整机+塔筒)', 'N/A', '↑ 海上风电招标放量'),
    ('太阳能发电(电站运营)', 'N/A', '↑ 分布式+集中式双增'),
    ('天然气管网', 'N/A', '↑ 国家管网公司成立'),
    ('配售电改革', 'N/A', '→ 增量配电试点扩围'),
    ('综合能源服务', 'N/A', '↑ 节能+碳管理'),
]

# 策略2：为"券商/保险/银行"金融盲区ETF补充材料
financial_materials = [
    ('证券经纪佣金率', 'N/A', '↓ 行业佣金率下行'),
    ('融资融券余额', 'N/A', '↑ 杠杆资金活跃度'),
    ('IPO承销规模', 'N/A', '↑ 注册制全面落地'),
    ('保险新业务价值', 'N/A', '↑ 寿险改革成效'),
    ('银行净息差(NIM)', 'N/A', '↓ LPR降息压力'),
    ('银行不良贷款率', 'N/A', '→ 地产+城投风险暴露'),
    ('财富管理AUM', 'N/A', '↑ 基金代销+理财子'),
    ('信托资产规模', 'N/A', '↓ 压降通道业务'),
]

# 策略3：为"生猪/养殖"盲区补充
animal_materials = [
    ('仔猪价格', 'N/A', '↑ 能繁母猪存栏下降'),
    ('饲料(豆粕/玉米)', 'N/A', '↓ 国际粮价回落'),
    ('兽用疫苗', 'N/A', '↑ 非瘟常态化'),
    ('养殖设备(自动化)', 'N/A', '↑ 人工成本上升'),
]

# 策略4：为"乳制品"盲区补充
dairy_materials = [
    ('奶粉(大包粉)', 'N/A', '↓ 海外低价进口冲击'),
    ('奶酪', 'N/A', '↑ 消费渗透率提升'),
    ('低温鲜奶', 'N/A', '↑ 消费升级'),
]

# 策略5：为"油气"盲区补充
oil_gas_materials = [
    ('LNG(液化天然气)', '$N/A', '↑ 进口依存度60%+'),
    ('成品油(汽油/柴油)', 'N/A', '→ 国际油价联动'),
    ('石化(乙烯/丙烯)', 'N/A', '↓ 产能过剩'),
    ('页岩气', 'N/A', '↑ 勘探开发加速'),
    ('油服(钻井/完井)', 'N/A', '↑ 国内产量目标1.9亿吨'),
]

# 策略6：高价值但未覆盖的半导体材料
semiconductor_gaps = [
    ('光掩模版(光罩)', 'N/A', '↑ AI芯片设计复杂度提升'),
    ('CMP抛光液', 'N/A', '↑ 先进制程用量倍增'),
    ('电子特气(高纯)', 'N/A', '↑ 国产替代加速'),
    ('高纯氢氟酸', 'N/A', '↑ 半导体清洗需求'),
    ('光刻胶(KrF/i-line)', 'N/A', '→ 成熟制程稳定'),
    ('硅片(8英寸)', 'N/A', '→ 功率器件主力'),
    ('氦气(高纯He-4)', 'N/A', '↑ 半导体/超导/航天三重需求'),
    ('ABF封装基板', 'N/A', '↑ AI芯片CoWoS瓶颈'),
]

# 策略7：高价值但未覆盖的新能源材料
energy_gaps = [
    ('光伏胶膜(EVA/POE)', 'N/A', '→ 透明EVA→POE转换'),
    ('焊带(镀锡/铜)', 'N/A', '→ 组件出货量驱动'),
    ('接线盒/连接器', 'N/A', '↑ 大尺寸组件配套'),
    ('储能系统集成', 'N/A', '↑ 大储+工商业双增'),
    ('充电桩/超充', 'N/A', '↑ 800V高压平台普及'),
    ('锂电池回收', 'N/A', '↑ 首批动力电池退役潮'),
]

# 策略8：高价值但未覆盖的医药材料
pharma_gaps = [
    ('CDMO合同定制', 'N/A', '↑ 全球外包渗透率提升'),
    ('创新药专利悬崖', 'N/A', '↓ 专利到期仿制药冲击'),
    ('中药配方颗粒', 'N/A', '↑ 国标替代省标'),
    ('耗材(高值/低值)', 'N/A', '↓ 集采降价压力'),
    ('IVD体外诊断', 'N/A', '→ 新冠后常态化'),
    ('医疗信息化(HIS)', 'N/A', '↑ 智慧医院建设'),
]

# 策略9：高价值但未覆盖的周期/建材材料
cycle_gaps = [
    ('玻璃(钢化/中空)', 'N/A', '↓ 地产竣工下滑'),
    ('涂料/油漆', 'N/A', '→ 翻新市场稳定'),
    ('防水(卷材/涂料)', 'N/A', '↓ 地产拖累'),
    ('耐火材料', 'N/A', '→ 钢铁/水泥需求'),
    ('磨料磨具', 'N/A', '→ 制造业PMI'),
]

# 策略10：高价值但未覆盖的军工材料
military_gaps = [
    ('航空发动机(整机)', 'N/A', '↑ 军用航空换代'),
    ('导弹/火箭', 'N/A', '↑ 实战化训练消耗'),
    ('军用雷达(相控阵)', 'N/A', '↑ 预警+火控需求'),
    ('军用通信(卫星)', 'N/A', '↑ 北斗+低轨卫星'),
    ('单兵装备', 'N/A', '↑ 信息化单兵系统'),
]

# 输出优先级排序
all_candidates = []
for name, status, trend in water_energy_materials:
    all_candidates.append(('水电/能源', name, status, trend, 'high'))
for name, status, trend in financial_materials:
    all_candidates.append(('金融', name, status, trend, 'medium'))
for name, status, trend in animal_materials:
    all_candidates.append(('养殖', name, status, trend, 'low'))
for name, status, trend in dairy_materials:
    all_candidates.append(('乳业', name, status, trend, 'low'))
for name, status, trend in oil_gas_materials:
    all_candidates.append(('油气', name, status, trend, 'medium'))
for name, status, trend in semiconductor_gaps:
    all_candidates.append(('半导体补充', name, status, trend, 'high'))
for name, status, trend in energy_gaps:
    all_candidates.append(('新能源补充', name, status, trend, 'medium'))
for name, status, trend in pharma_gaps:
    all_candidates.append(('医药补充', name, status, trend, 'medium'))
for name, status, trend in cycle_gaps:
    all_candidates.append(('周期建材', name, status, trend, 'low'))
for name, status, trend in military_gaps:
    all_candidates.append(('军工补充', name, status, trend, 'low'))

print("=== 下一轮学习优先级 ===\n")
for cat, name, status, trend, prio in sorted(all_candidates, key=lambda x: {'high':0,'medium':1,'low':2}[x[4]]):
    print(f"[{prio}] {cat}: {name} | {status} | {trend}")
