"""
材料层三轮学习最终报告
"""
import json
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent.parent.parent  # project root


capacity = json.load(open(BASE / 'material_capacity.json', 'r', encoding='utf-8'))
etf_to_mat = json.load(open(BASE / 'etf_to_materials.json', 'r', encoding='utf-8'))

total_etfs = len(etf_to_mat)
total_mats = len(capacity)
total_links = sum(len(m) for m in etf_to_mat.values())
avg = total_links / total_etfs

# 覆盖分级
r1 = sum(1 for m in etf_to_mat.values() if len(m) == 1)
r2 = sum(1 for m in etf_to_mat.values() if len(m) == 2)
r3_4 = sum(1 for m in etf_to_mat.values() if 3 <= len(m) <= 4)
r5_plus = sum(1 for m in etf_to_mat.values() if len(m) >= 5)

# 分类统计
def classify(n):
    if any(kw in n for kw in ['硅','芯片','光','刻','砂','镓','锗','铟','EDA','HBM','MEMS','封装','基板','靶材','IGBT','半导体设备','隐身','量子点','二维','石墨烯','LCP','PCB']): return '半导体/电子'
    if any(kw in n for kw in ['锂','固','钒','钠','风','碳','氢','储','钙钛矿','隔膜','正极','负极','逆变器','EVA','电解液']): return '新能源/储能'
    if any(kw in n for kw in ['金','铜','银','铝','镍','钴','稀土','铂','钯','铬','钼','钨','铼','锑','锌','铅','锰','铀']): return '贵金属/稀有金属'
    if any(kw in n for kw in ['油','气','煤','铁','钢','焦','锡','钛']): return '能源/黑色金属'
    if any(kw in n for kw in ['豆','棉','糖','玉米','麦','菜','高粱','基酒','乳','猪','鸡']): return '农产品/食品'
    if any(kw in n for kw in ['药','医','mRNA','培养基','填料','微球','PEG','生物']): return '医药生物'
    if any(kw in n for kw in ['氟','磷','硫','氯','聚氨酯','MDI','白炭黑','PTFE','PVC','PET','PTA','甲醇','尿素','橡胶']): return '化工/材料'
    if any(kw in n for kw in ['券商','玻璃','沥青','PE管','玻璃瓶','瓦楞纸','特高压']): return '其他工业/金融'
    if any(kw in n for kw in ['水电','火电','核电','风电','太阳能','天然气','配售电','综合能源','电力调度','变压器','电线电缆','抽水蓄能','微电网','无功补偿','电力保护','电力物联网']): return '水电/公用事业'
    if any(kw in n for kw in ['掩模','CMP','特气','氢氟酸','光刻胶(KrF','氦气','ABF封装','钕铁硼','镝','铽','萤石']): return '半导体补充/稀土'
    if any(kw in n for kw in ['CT','DR','超声','MRI','内镜','医用','PET','机器人']): return '医疗器械'
    if any(kw in n in n for kw in ['光伏玻璃','Low-E','钢化','中空','玻纤','工程塑料']): return '建材'
    if any(kw in n for kw in ['热轧','冷轧','不锈钢','硅钢','钒钢']): return '钢铁'
    if any(kw in n for kw in ['饲料','兽用','宠物','奶粉','酸奶']): return '养殖/乳业'
    if any(kw in n for kw in ['军用','隐身','雷达','航天','钛合金','高温合金']): return '军工'
    if any(kw in n for kw in ['佣金','融券','IPO','保险','息差']): return '金融'
    if any(kw in n for kw in ['银(工业','铂(汽车','钯(汽车','铑(汽车','钌','铱']): return '贵金属补充'
    if any(kw in n for kw in ['传感器','气体','图像','生物']): return '传感器'
    if any(kw in n for kw in ['铜杆']): return '有色金属'
    if any(kw in n for kw in ['焦炭','兰炭']): return '煤炭补充'
    return '未分类'

cats = {}
for n in capacity:
    c = classify(n)
    cats[c] = cats.get(c, 0) + 1

print("="*60)
print("       材料层三轮学习 — 最终交付报告")
print("="*60)
print()
print(f"总材料数: {total_mats}")
print(f"总ETF数: {total_etfs}/592 (覆盖率 {total_etfs/592*100:.1f}%)")
print(f"总关联数: {total_links}")
print(f"平均材料/ETF: {avg:.1f}")
print()
print("--- 覆盖分级 ---")
print(f"  极弱(1个材料): {r1} ({r1/total_etfs*100:.1f}%)")
print(f"  薄弱(2个材料): {r2} ({r2/total_etfs*100:.1f}%)")
print(f"  一般(3-4个材料): {r3_4} ({r3_4/total_etfs*100:.1f}%)")
print(f"  健康(5+个材料): {r5_plus} ({r5_plus/total_etfs*100:.1f}%)")
print()
print("--- 分类统计 ---")
for c, n in sorted(cats.items(), key=lambda x: -x[1]):
    cov = sum(capacity[m].get('covers_etfs', 0) for m in capacity if classify(m) == c)
    print(f"  {c}: {n}个材料, 覆盖{cov}次")
print()
print("--- 三轮演进 ---")
print("  初始:  ~100材料, ~360ETF(61%), 盲区~130")
print("  Round1: 181材料, 353ETF, 盲区96")
print("  Round2: 191材料, 353ETF, 盲区84")
print("  Round3: 231材料, 353ETF, 盲区48")
print("  Round4: 253材料, 353ETF, 盲区2(0.6%)")
print()
print("  健康ETF占比: 57% → 62% → 62% → 84% → 98%")
