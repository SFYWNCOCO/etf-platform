"""
分析未分类材料和盲区ETF，找出下一轮学习的优先方向
"""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent.parent
DATA = BASE / 'data'
data = json.load(open(DATA / 'material_capacity.json', 'r', encoding='utf-8'))
etf_to_mat = json.load(open(DATA / 'etf_to_materials.json', 'r', encoding='utf-8'))
simple = json.load(open(DATA / 'etf_materials_simple.json', 'r', encoding='utf-8'))

def classify(name):
    if any(kw in name for kw in ['硅','芯片','光','刻','砂','镓','锗','铟','EDA','HBM','MEMS','封装','基板','靶材','IGBT','半导体设备','隐身','量子点','二维','石墨烯','LCP','PCB']):
        return '半导体/电子'
    if any(kw in name for kw in ['锂','固','钒','钠','风','碳','氢','储','钙钛矿','隔膜','正极','负极','逆变器','EVA','电解液']):
        return '新能源/储能'
    if any(kw in name for kw in ['金','铜','银','铝','镍','钴','稀土','铂','钯','铬','钼','钨','铼','锑','锌','铅','锰','铀']):
        return '贵金属/稀有金属'
    if any(kw in name for kw in ['油','气','煤','铁','钢','焦','锡','钛']):
        return '能源/黑色金属'
    if any(kw in name for kw in ['豆','棉','糖','玉米','麦','菜','高粱','基酒','乳','猪','鸡']):
        return '农产品/食品'
    if any(kw in name for kw in ['药','医','mRNA','培养基','填料','微球','PEG','生物']):
        return '医药生物'
    if any(kw in name for kw in ['氟','磷','硫','氯','聚氨酯','MDI','白炭黑','PTFE','PVC','PET','PTA','甲醇','尿素','橡胶']):
        return '化工/材料'
    if any(kw in name for kw in ['券商','玻璃','沥青','PE管','玻璃瓶','瓦楞纸','特高压']):
        return '其他工业/金融'
    return '未分类'

# 1. 未分类材料详情
uncategorized = [(n, d) for n, d in data.items() if classify(n) == '未分类']
print("=== 未分类材料 ===")
for name, info in sorted(uncategorized, key=lambda x: -x[1].get('covers_etfs', 0)):
    print(f"  [{info.get('covers_etfs',0):>3}] {name}: {info.get('current_status','?')[:40]} | ETFs: {info.get('etfs',[])}")

# 2. 盲区ETF详情（只覆盖<=2个材料的）
print("\n=== 盲区ETF分析 ===")
blind_etfs = [(etf, mats) for etf, mats in etf_to_mat.items() if len(mats) <= 2]
print(f"盲区ETF总数: {len(blind_etfs)}")

# 按ETF代码段分组看主题
from collections import Counter
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent.parent.parent  # project root

prefixes = Counter()
for etf, mats in blind_etfs:
    # 提取ETF主题特征
    prefix = etf[:6]
    prefixes[prefix] += 1

print("\n盲区ETF前缀分布:")
for p, c in prefixes.most_common(15):
    print(f"  {p}: {c}个")

# 展示几个代表性盲区ETF的材料关联
print("\n=== 代表性盲区ETF ===")
sample_blind = blind_etfs[:15]
for etf, mats in sample_blind:
    mat_details = [data.get(m, {}) for m in mats if m in data]
    statuses = [md.get('current_status', '?') for md in mat_details]
    print(f"  {etf}: [{len(mats)}个材料] {mats[:3]}")
    if statuses:
        print(f"    状态: {statuses[0][:50] if len(statuses) == 1 else statuses[:2]}")

# 3. 找出高频ETF代码段（主题集群）
print("\n=== 高频ETF主题分析 ===")
# 从simple中提取ETF的常见材料类型
etf_material_counts = Counter()
for etf, mats in simple.items():
    for m in mats:
        etf_material_counts[m] += 1

# 哪些材料覆盖了很多ETF但还没被加入material_capacity?
all_materials_in_simple = set()
for etf, mats in simple.items():
    all_materials_in_simple.update(mats)

existing_materials = set(data.keys())
missing_materials = all_materials_in_simple - existing_materials
print(f"\nsimple中有但capacity中没有的材料: {len(missing_materials)}")
for m in sorted(missing_materials, key=lambda x: -etf_material_counts[x])[:20]:
    print(f"  [{etf_material_counts[m]:>3}] {m}")
