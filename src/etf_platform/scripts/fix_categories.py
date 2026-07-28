"""
修复174个缺失category的材料
"""
import json
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent.parent.parent  # project root


capacity = json.load(open(BASE / 'material_capacity.json', 'r', encoding='utf-8'))

def classify(n):
    if any(kw in n for kw in ['硅','芯片','光','刻','砂','镓','锗','铟','EDA','HBM','MEMS','封装','基板','靶材','IGBT','半导体设备','隐身','量子点','二维','石墨烯','LCP','PCB','掩模','CMP','特气','氢氟酸','光刻胶(KrF','氦气','ABF封装','钕铁硼','镝','铽','萤石']):
        return '半导体/电子'
    if any(kw in n for kw in ['锂','固','钒','钠','风','碳','氢','储','钙钛矿','隔膜','正极','负极','逆变器','EVA','电解液','光伏胶膜','焊带','接线盒','储能系统','充电桩','锂电池回收']):
        return '新能源/储能'
    if any(kw in n for kw in ['金','铜','银','铝','镍','钴','稀土','铂','钯','铬','钼','钨','铼','锑','锌','铅','锰','铀','银(工业','铂(汽车','钯(汽车','铑(汽车','钌','铱']):
        return '贵金属/稀有金属'
    if any(kw in n for kw in ['油','气','煤','铁','钢','焦','锡','钛','热轧','冷轧','不锈钢','硅钢','钒钢','焦炭','兰炭']):
        return '能源/黑色金属'
    if any(kw in n for kw in ['豆','棉','糖','玉米','麦','菜','高粱','基酒','乳','猪','鸡','饲料','兽用','宠物','奶粉','酸奶']):
        return '农产品/食品'
    if any(kw in n for kw in ['药','医','mRNA','培养基','填料','微球','PEG','生物','CT','DR','超声','MRI','内镜','医用','PET','机器人']):
        return '医药生物'
    if any(kw in n for kw in ['氟','磷','硫','氯','聚氨酯','MDI','白炭黑','PTFE','PVC','PET','PTA','甲醇','尿素','橡胶']):
        return '化工/材料'
    if any(kw in n for kw in ['券商','保险','佣金','融券','IPO','保险','息差']):
        return '金融'
    if any(kw in n for kw in ['水电','火电','核电','风电','太阳能','天然气','配售电','综合能源','电力调度','变压器','电线电缆','抽水蓄能','微电网','无功补偿','电力保护','电力物联网']):
        return '水电/公用事业'
    if any(kw in n for kw in ['玻璃','Low-E','钢化','中空','玻纤','工程塑料','光伏玻璃']):
        return '建材'
    if any(kw in n for kw in ['军用','隐身','雷达','航天','钛合金','高温合金']):
        return '军工'
    if any(kw in n for kw in ['传感器','气体','图像','生物']):
        return '传感器'
    if any(kw in n for kw in ['铜杆']):
        return '有色金属'
    return '未分类'

fixed = 0
for n in capacity:
    if not capacity[n].get('category'):
        capacity[n]['category'] = classify(n)
        fixed += 1

with open(BASE / 'material_capacity.json', 'w', encoding='utf-8') as f:
    json.dump(capacity, f, ensure_ascii=False, indent=2)

print(f"修复 {fixed} 个材料的category字段")
cats = {}
for n in capacity:
    c = capacity[n].get('category', '未分类')
    cats[c] = cats.get(c, 0) + 1
for k, v in sorted(cats.items(), key=lambda x: -x[1]):
    print(f"  {k}: {v}")
