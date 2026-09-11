# -*- coding: utf-8 -*-
"""构建 theme_catalog.json — 天天基金163主题全量索引 + 未来催化标注（2026-08-27 扫描）"""
import urllib.request, json, io, sys, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# 1. 抓取天天基金主题全量
url = 'https://api.fund.eastmoney.com/ZTJJ/GetBKListByBKTypeNew'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://fund.eastmoney.com/ztjj/'})
resp = urllib.request.urlopen(req, timeout=25)
data = json.loads(resp.read().decode('utf-8'))['Data']

topics = []
for cat_key, cat_name in [('hy1', '行业'), ('gn', '概念')]:
    for item in data[cat_key]:
        topics.append({
            'name': item['INDEXNAME'],
            'code': item['INDEXCODE'],
            'category': cat_name,
            'cluster': None,       # 主题簇（归类）
            'future_catalyst': None,  # 未来1个月催化事件
            'catalyst_window': None,  # 催化时间窗口
            'status': 'unscanned'    # unscanned/scanned/checked
        })

print(f'共 {len(topics)} 个主题')

# 2. 主题簇归类
CLUSTER_MAP = {
    '半导体': ['半导体', '第三代半导体', '电子化学品', '元件', '光刻胶', '芯片', '存储芯片'],
    'AI/科技': ['人工智能', '云计算', '算力', 'CPO', 'PCB', '光模块', '液冷', '数据中心', '软件', '计算机', '网络安全', 'DeepSeek', 'AI应用', 'AI手机', 'AI眼镜', 'TMT', '科技', '超清视频', '元宇宙', 'Web3.0', '数据要素', '信创', '国产软件', 'HALO', '游戏'],
    '消费电子': ['消费电子', '华为', '智能穿戴', '智能家居', 'LED', '光学光电子', '电子', '元件'],
    '医药': ['医药生物', '创新药', '化学制药', '生物制品', '生物疫苗', '医疗器械', '医疗服务', 'CRO', '中药', '精准医疗'],
    '农业/粮食': ['农林牧渔', '猪肉', '养殖业', '农牧主题', '乡村振兴', '种业'],
    '新能源': ['新能源', '新能源车', '锂电池', '电池', '固态电池', '储能', '光伏设备', '充电桩', '锂矿', '绿色电力', '碳中和', '电力设备'],
    '公用事业': ['公用事业', '电力', '环保', '环保设备', '环境治理', '电网设备'],
    '消费': ['消费', '白酒', '食品饮料', '家用电器', '家居用品', '商贸零售', '纺织服饰', '旅游', '影视', '传媒', '文娱用品', '新消费', '可选消费', '黄金股', '教育', '在线教育', '体育产业', '养老产业', '社会服务', '广告营销'],
    '军工': ['国防军工', '航母', '军民融合', '航天装备', '航空装备', '军工电子', '通用航空'],
    '资源/周期': ['有色金属', '贵金属', '黄金', '铜', '稀土永磁', '小金属', '工业金属', '煤炭', '煤炭开采', '石油石化', '钢铁', '基础化工', '化学制品', '化工原料', '大宗商品', '资源', '能源'],
    '金融': ['银行', '保险', '非银金融', '证券', '券商', '金融'],
    '地产/基建': ['房地产', '房地产开发', '房地产服务', '建筑装饰', '建筑材料', '装修建材', '基建'],
    '低空/商业航天': ['低空经济', '商业航天', '卫星互联网', '脑机接口'],
    '高端制造': ['高端装备', '高端制造', '机械设备', '自动化设备', '专用设备', '通用设备', '工程机械', '工业4.0', '工业互联', '制造', '材料'],
    '机器人': ['机器人', '人形机器人'],
    '通信': ['通信', '通信设备', '通信服务', '5G', 'F5G', '毫米波', '光通信'],
    '汽车': ['汽车', '汽车零部件', '汽车服务', '智能驾驶', '无人驾驶', '特斯拉'],
    '物流/交运': ['物流', '交通运输', '航空机场', '一带一路'],
    '红利/价值': ['红利', '中特估', '国企改革', '高股息', '央企改革'],
    '跨境/港股': ['港股', '恒生', '中概', '跨境'],
}

def assign_cluster(name):
    for cluster, kws in CLUSTER_MAP.items():
        for kw in kws:
            if kw in name:
                return cluster
    return '其他'

for t in topics:
    t['cluster'] = assign_cluster(t['name'])

# 3. 未来催化标注（2026-08-27 引擎+新闻扫描结果）
CATALYST_NOTES = {
    '创新药': ('9月新版基药目录实施，首次纳入国产一类创新药', '2026-09'),
    '医药生物': ('基药目录9月实施+医保十五五规划', '2026-09'),
    '化学制药': ('基药目录9月实施', '2026-09'),
    '生物制品': ('基药目录9月实施', '2026-09'),
    '医疗服务': ('医疗需求旺季', '2026-Q4'),
    'CRO': ('创新药BD出海持续超预期', '2026-Q4'),
    '中药': ('基药目录9月实施', '2026-09'),
    '农林牧渔': ('厄尔尼诺10-12月高峰，NOAA 95%概率超强', '2026-10~12'),
    '猪肉': ('厄尔尼诺+养殖旺季', '2026-Q4'),
    '养殖业': ('厄尔尼诺+猪价旺季', '2026-Q4'),
    '消费电子': ('华为9/7 Mate XT2+麒麟2026；苹果9/10 iPhone18+折叠屏', '2026-09-07~10'),
    '华为': ('华为9/7发布会，麒麟2026芯片', '2026-09-07'),
    '机器人': ('特斯拉9/3 Cybercab发布会；Optimus量产', '2026-09-03'),
    '人形机器人': ('特斯拉Optimus 8月量产9月爬坡', '2026-09'),
    '5G': ('中际旭创入港股通+1.6T光模块', '2026-08-27'),
    '通信设备': ('中际旭创入港股通+英伟达指引', '2026-08-27'),
    '通信': ('英伟达产业链+1.6T光模块', '2026-08-27'),
    '光模块': ('英伟达Vera Rubin+1.6T量产', '2026-Q4'),
    'CPO': ('英伟达Vera Rubin全液冷+1.6T', '2026-Q4'),
    'PCB': ('AI服务器28-40层高阶PCB', '2026-Q4'),
    '算力': ('英伟达供给短缺至2028+华为昇腾', '2026-Q4'),
    '数据中心': ('AI算力供给短缺至2028', '2026-Q4'),
    '液冷': ('英伟达Vera Rubin全液冷平台', '2026-Q4'),
    '云计算': ('英伟达指引超预期', '2026-Q4'),
    '固态电池': ('东风9月装车+宁德Q3交付360Wh/kg', '2026-09'),
    '电池': ('电芯涨价潮8-10月+排产破300GWh', '2026-08~10'),
    '锂电池': ('电芯涨价+储能排产超120GWh', '2026-08~10'),
    '储能': ('海外大储订单年末并网前备货', '2026-Q4'),
    '新能源车': ('电芯涨价传导', '2026-08~10'),
    '充电桩': ('新能源车下乡政策', '2026-Q4'),
    '绿色电力': ('绿证价格指数发布+电价市场化', '2026-Q4'),
    '公用事业': ('绿证价格指数+电价改革', '2026-Q4'),
    '电力': ('绿证价格指数7/24发布', '2026-Q4'),
    '黄金股': ('央行购金+避险', '2026-Q4'),
    '贵金属': ('央行购金+地缘避险', '2026-Q4'),
    '证券': ('券商并购重组大年+印花税+99.2%', '2026-Q4'),
    '银行': ('息差企稳+涉房改善+零售激活', '2026-Q4'),
    '保险': ('保险资管新规9/1施行', '2026-09-01'),
    '红利': ('财政支出破30万亿+险资增配', '2026-09'),
    '中特估': ('央企重组+国企改革', '2026-Q4'),
    '国企改革': ('央企重组首单落地', '2026-Q4'),
    '低空经济': ('新民航法7/1施行+规模化元年', '2026-Q4'),
    '商业航天': ('火箭密集发射+卫星互联网部署', '2026-Q4'),
    '卫星互联网': ('卫星互联网时代兴起', '2026-Q4'),
    '脑机接口': ('Neuralink规模化生产预期', '2026-Q4'),
    '稀土永磁': ('出口管制+地缘', '2026-Q4'),
    '半导体': ('英伟达财报已兑现（8/27）；华为麒麟2026在9/7', '2026-09-07'),
    '存储芯片': ('存储涨价扩产+机构预测2027破万亿', '2026-Q4'),
}

# 4. 合并模式：载入旧文件已有标注，保留 future_catalyst/status（避免重建丢失二轮扫描结果）
out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'theme_catalog.json')
out_path = os.path.normpath(out_path)
old_topics = {}
if os.path.exists(out_path):
    try:
        with open(out_path, encoding='utf-8') as f:
            old = json.load(f)
        for t in old.get('topics', []):
            old_topics[t['name']] = t
    except Exception:
        pass

for t in topics:
    if t['name'] in CATALYST_NOTES:
        note, window = CATALYST_NOTES[t['name']]
        t['future_catalyst'] = note
        t['catalyst_window'] = window
        t['status'] = 'scanned'
    elif t['name'] in old_topics and old_topics[t['name']].get('status') == 'scanned':
        # 保留旧的扫描标注（二轮补标）
        t['future_catalyst'] = old_topics[t['name']].get('future_catalyst')
        t['catalyst_window'] = old_topics[t['name']].get('catalyst_window')
        t['status'] = 'scanned'
    else:
        t['status'] = 'unscanned'

with open(out_path, 'w', encoding='utf-8') as f:
    json.dump({'generated_at': '2026-08-27', 'source': '天天基金 ZTJJ/GetBKListByBKTypeNew', 'total': len(topics), 'topics': topics}, f, ensure_ascii=False, indent=1)

print(f'已写入 {out_path}')
print(f'  总计: {len(topics)} 主题')
scanned = sum(1 for t in topics if t['status'] == 'scanned')
print(f'  已标注催化: {scanned}')
print(f'  待扫描: {len(topics) - scanned}')

# 5. 簇分布
from collections import Counter
clusters = Counter(t['cluster'] for t in topics)
print('\n主题簇分布:')
for c, n in clusters.most_common():
    print(f'  {c}: {n}')