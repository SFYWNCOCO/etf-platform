"""
验证第二轮学习成果：覆盖率变化 + 盲区减少
"""
import json
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent.parent.parent  # project root


capacity = json.load(open(BASE / 'material_capacity.json', 'r', encoding='utf-8'))
simple = json.load(open(BASE / 'etf_materials_simple.json', 'r', encoding='utf-8'))
etf_to_mat = json.load(open(BASE / 'etf_to_materials.json', 'r', encoding='utf-8'))

# 1. 材料总数
print("=== 材料层统计 ===")
print(f"总材料数: {len(capacity)}")

# 2. 按类别统计
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
    if any(kw in name for kw in ['水电','火电','核电','风电','太阳能','天然气','配售电','综合能源']):
        return '水电/能源'
    if any(kw in name for kw in ['掩模','CMP','特气','氢氟酸','光刻胶','氦气','ABF']):
        return '半导体补充'
    return '未分类'

cats = {}
for name in capacity.keys():
    cat = classify(name)
    cats[cat] = cats.get(cat, 0) + 1

print("\n=== 分类统计 ===")
for k, v in sorted(cats.items(), key=lambda x: -x[1]):
    cov = sum(capacity[n].get('covers_etfs', 0) for n in capacity.keys() if classify(n) == k)
    print(f"  {k}: {v}个材料, 覆盖{cov}次")

# 3. ETF覆盖统计
total_mats = sum(len(mats) for mats in etf_to_mat.values())
avg = total_mats / len(etf_to_mat) if etf_to_mat else 0
blind = sum(1 for mats in etf_to_mat.values() if len(mats) <= 2)
healthy = sum(1 for mats in etf_to_mat.values() if len(mats) >= 5)

print("\n=== ETF覆盖统计 ===")
print(f"总ETF数: {len(etf_to_mat)}")
print(f"总材料-ETF关联: {total_mats}")
print(f"平均每ETF材料数: {avg:.1f}")
print(f"盲区ETF(<=2材料): {blind} ({blind/len(etf_to_mat)*100:.1f}%)")
print(f"健康ETF(>=5材料): {healthy} ({healthy/len(etf_to_mat)*100:.1f}%)")

# 4. 新增材料列表
print("\n=== 本轮新增材料(16个) ===")
new_mats = [n for n in capacity.keys() if capacity[n].get('added_date') == '2026-07-05']
for name in sorted(new_mats, key=lambda x: -capacity[x]['covers_etfs']):
    info = capacity[name]
    print(f"  [{info['covers_etfs']:>3}] {name}: {info.get('driver','?')[:45]}")
