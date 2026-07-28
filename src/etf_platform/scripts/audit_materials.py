"""
材料层审计与去重脚本
1. 发现重复材料（不同名称但实质相同）
2. 按类别统计覆盖率
3. 识别高价值但未充分覆盖的ETF
"""
import json
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent.parent.parent  # project root


data = json.load(open(BASE / 'material_capacity.json', 'r', encoding='utf-8'))
etf_to_mat = json.load(open(BASE / 'etf_to_materials.json', 'r', encoding='utf-8'))

# 1. 找重复材料（基于ETF集合相似度）
def etf_set(name):
    info = data.get(name, {})
    return set(info.get('etfs', []))

names = list(data.keys())
duplicates = []

for i in range(len(names)):
    for j in range(i+1, len(names)):
        s1 = etf_set(names[i])
        s2 = etf_set(names[j])
        if not s1 or not s2:
            continue
        overlap = s1 & s2
        union = s1 | s2
        jaccard = len(overlap) / len(union) if union else 0
        if jaccard > 0.7 and len(overlap) >= 3:
            duplicates.append((names[i], names[j], jaccard, len(overlap)))

print(f"=== 潜在重复材料 ({len(duplicates)} 对) ===")
for a, b, jac, ov in sorted(duplicates, key=lambda x: -x[2]):
    print(f"  [{jac:.2f}] {a} <-> {b} (重叠{ov}个ETF)")

# 2. 按类别统计
print("\n=== 材料统计 ===")
print(f"总材料数: {len(data)}")
total_covers = sum(info.get('covers_etfs', 0) for info in data.values())
print(f"总覆盖次数: {total_covers}")
print(f"平均每个材料覆盖: {total_covers/len(data):.1f} ETF")

# 3. 找出被最少材料覆盖的ETF（盲区）
all_etfs = set(etf_to_mat.keys())
min_materials = []
for etf, mats in etf_to_mat.items():
    if len(mats) <= 2:
        min_materials.append((etf, len(mats), mats[:5]))

print("\n=== ETF覆盖盲区 (<3个材料) ===")
print(f"盲区ETF数: {len(min_materials)} / {len(all_etfs)}")
for etf, cnt, mats in sorted(min_materials, key=lambda x: x[1])[:20]:
    print(f"  {etf}: {cnt}个材料 -> {mats}")

# 4. 按名称特征粗分类
print("\n=== 粗分类统计 ===")

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

cats = {}
for name in data.keys():
    cat = classify(name)
    cats[cat] = cats.get(cat, 0) + 1

for k, v in sorted(cats.items(), key=lambda x: -x[1]):
    total_cov = sum(data[n].get('covers_etfs', 0) for n in data.keys() if classify(n) == k)
    print(f"  {k}: {v}个材料, 覆盖{total_cov}次")
