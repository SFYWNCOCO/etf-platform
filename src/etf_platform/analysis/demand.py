"""L10+L11 demand scoring with elasticity, correlation, and information chain adjustments.

v8.10: Major B2B_SECTOR_RISK expansion — 52% entries compressed from [5.0, 6.0] to 13 distinct tiers.
       Blended aggregation (min*0.7 + avg*0.3) replaced pure pessimistic min().
"""

# v3.0: Fixed -- these constants were referenced but never defined, causing
# NameError in score_demand_climate() -> pipeline.py try/except caught it ->
# all L10/L11 scores defaulted to 5.0 (the silent failure we observed).
DATA_LAST_UPDATED = "2026-07-07"
DATA_SOURCE_B2B = "b2b_inferred"
DATA_SOURCE_CONSUMER = "consumer_stats"
DATA_SOURCE_ECONOMICS = "economics_model"

# Consumer sectors list (unchanged)
CONSUMER_SECTORS = {
    "消费", "白酒消费", "食品饮料", "白酒", "家电", "汽车",
    "医药", "医疗", "医疗器械", "医药生物",
    "养殖", "农牧", "畜牧", "农产品",
    "旅游", "传媒", "游戏",
    "港股消费",
}

# L10 demand climate (unchanged)
DEMAND_CLIMATE = {
    "消费":      {"retail_growth": 3.5, "confidence": 78, "savings_rate": 32, "unemployment": 15},
    "白酒消费":  {"retail_growth": -1.5, "confidence": 76, "savings_rate": 36, "unemployment": 16},
    "白酒":      {"retail_growth": -2.0, "confidence": 82, "savings_rate": 34, "unemployment": 16},
    "食品饮料":  {"retail_growth": 2.0, "confidence": 82, "savings_rate": 34, "unemployment": 16},
    "家电":      {"retail_growth": 2.0, "confidence": 75, "savings_rate": 34, "unemployment": 15},
    "汽车":      {"retail_growth": 4.0, "confidence": 82, "savings_rate": 34, "unemployment": 16},
    "医药":      {"retail_growth": 5.0, "confidence": 85, "savings_rate": 10, "unemployment": 16},
    "医疗":      {"retail_growth": 5.0, "confidence": 85, "savings_rate": 34, "unemployment": 16},
    "医药器械":  {"retail_growth": 6.0, "confidence": 88, "savings_rate": 12, "unemployment": 14},
    "养殖":      {"retail_growth": 2.0, "confidence": 80, "savings_rate": 34, "unemployment": 16},
    "农产品":    {"retail_growth": 4.0, "confidence": 80, "savings_rate": 30, "unemployment": 14},
    "传媒":      {"retail_growth": 6.0, "confidence": 82, "savings_rate": 34, "unemployment": 16},
    "餐饮":      {"retail_growth": 3.0, "confidence": 79, "savings_rate": 33, "unemployment": 15},
    "旅游酒店":  {"retail_growth": 5.0, "confidence": 81, "savings_rate": 31, "unemployment": 14},
    "体育娱乐":  {"retail_growth": 4.5, "confidence": 80, "savings_rate": 32, "unemployment": 14},
    "default":   {"retail_growth": 4.0, "confidence": 85, "savings_rate": 32, "unemployment": 14},
}

# L11 sector demand risk (unchanged)
SECTOR_DEMAND_RISK = {
    "白酒消费": {"inventory_days": 900, "price_trend": "下跌", "price_change_pct": -24, "demographic": "极高",
                 "substitution": "高", "policy": "中", "scenario": "高"},
    "白酒":     {"inventory_days": 900, "price_trend": "下跌", "price_change_pct": -24, "demographic": "极高",
                 "substitution": "高", "policy": "中", "scenario": "高"},
    "食品饮料": {"inventory_days": 120, "price_trend": "持平", "price_change_pct": -5, "demographic": "中",
                 "substitution": "中", "policy": "低", "scenario": "中"},
    "家电":     {"inventory_days": 90, "price_trend": "下跌", "price_change_pct": -8, "demographic": "中",
                 "substitution": "高", "policy": "中", "scenario": "低"},
    "养殖":     {"inventory_days": 45, "price_trend": "上涨", "price_change_pct": 15, "demographic": "低",
                 "substitution": "低", "policy": "低", "scenario": "低"},
    "医药":     {"inventory_days": 60, "price_trend": "持平", "price_change_pct": 0, "demographic": "低",
                 "substitution": "中", "policy": "高", "scenario": "低"},
    "消费":     {"inventory_days": 90, "price_trend": "持平", "price_change_pct": -3, "demographic": "中",
                 "substitution": "中", "policy": "低", "scenario": "中"},
    "农产品":   {"inventory_days": 30, "price_trend": "上涨", "price_change_pct": 5, "demographic": "低",
                 "substitution": "低", "policy": "高", "scenario": "低"},
    "医药器械": {"inventory_days": 45, "price_trend": "持平", "price_change_pct": 2, "demographic": "低",
                 "substitution": "中", "policy": "高", "scenario": "低"},
    "餐饮":     {"inventory_days": 15, "price_trend": "持平", "price_change_pct": 0, "demographic": "中",
                 "substitution": "高", "policy": "低", "scenario": "中"},
    "旅游酒店": {"inventory_days": 10, "price_trend": "上涨", "price_change_pct": 8, "demographic": "中",
                 "substitution": "高", "policy": "低", "scenario": "低"},
    "体育娱乐": {"inventory_days": 20, "price_trend": "持平", "price_change_pct": 1, "demographic": "中",
                 "substitution": "中", "policy": "低", "scenario": "低"},
}

# === B2B Demand Climate ===
B2B_DEMAND_CLIMATE = {
    "半导体":    {"score": 5.5, "note": "全球芯片库存高位, 下行周期, AI需求对冲"},
    "半导体设备":  {"score": 5.0, "note": "设备订单增速放缓, 国产替代加速, 制裁风险压制需求"},
    "AI/科技":   {"score": 8.0, "note": "云计算Capex扩张+AI军备竞赛+政府补贴"},
    "AI算力":    {"score": 8.0, "note": "GPU需求旺盛, 算力基建加速"},
    "云计算/算力": {"score": 8.0, "note": "AI驱动算力需求, 全球数据中心竞赛"},
    "通信/5G":   {"score": 6.0, "note": "5G建设高峰已过, 6G尚早"},
    "5G/PCB":   {"score": 6.0, "note": "PCB需求平稳"},
    "电子":      {"score": 5.5, "note": "消费电子需求疲软, AI芯片短缺推高价格"},
    "新能源":    {"score": 7.5, "note": "霍尔木兹危机+能源转型加速"},
    "光伏":      {"score": 6.5, "note": "产能过剩但能源危机对冲"},
    "电池":      {"score": 7.0, "note": "钠电池量产+储能需求+能源安全"},
    "军工":      {"score": 8.0, "note": "国防预算增长+地缘紧张+无人机需求"},
    "航空航天":   {"score": 7.5, "note": "商业航天+军机换代"},
    "金融":      {"score": 5.0, "note": "利率下行利好但信贷需求弱+滞胀风险, 净息差承压"},
    "证券":      {"score": 4.5, "note": "市场成交量低迷"},
    "银行":      {"score": 5.5, "note": "净息差收窄+坏账风险上升"},
    "保险":      {"score": 6.0, "note": "保费增长稳定+利率下行利好久期"},
    "券商":      {"score": 4.5, "note": "IPO收紧+交易量低"},
    "红利/价值":  {"score": 6.0, "note": "滞胀下防御属性强但非高增长"},
    "红利价值":   {"score": 6.0, "note": "高股息策略受益于降息+滞胀"},
    "高股息":    {"score": 6.0, "note": "股息率vs存款利率差扩大"},
    "红利+低波":  {"score": 6.0, "note": "滞胀+地缘风险->防御属性强但非高增长"},
    "基建/地产":  {"score": 4.0, "note": "房地产投资持续下行+滞胀抑制需求"},
    "有色":      {"score": 6.0, "note": "铜铝需求稳, 稀土承压, 能源转型需求"},
    "黄金":      {"score": 7.5, "note": "央行购金+降息预期+滞胀避险"},
    "公用事业":   {"score": 6.5, "note": "稳定现金流+防御属性+能源转型"},
    "全市场":    {"score": 5.0, "note": "滞胀+地缘风险->弱复苏, 宽基分散但盈利承压"},
    "宽基":      {"score": 5.2, "note": "沪深300盈利增速低个位数, 滞胀压制"},
    "中盘成长":   {"score": 4.8, "note": "估值修复中但滞胀压力大, 盈利不确定"},
    "跨境":      {"score": 6.0, "note": "海外市场分化"},
    "中概互联网": {"score": 5.5, "note": "监管缓和但增长放缓+科技脱钩"},
    "港股":      {"score": 6.0, "note": "EV强势+科技融资活跃"},
    "硬科技":    {"score": 7.0, "note": "国产替代加速+政策支持+科技脱钩对冲"},
    "中药":      {"score": 6.5, "note": "政策扶持+老龄化需求"},
    "医药器械":   {"score": 6.0, "note": "集采压力+国产替代"},
    "可转债":    {"score": 6.5, "note": "滞胀->股市震荡->转债性价比上升"},
    "信用债":    {"score": 6.5, "note": "城投化债+利率下行"},
    "利率债":    {"score": 7.5, "note": "降息周期+避险需求+滞胀环境"},
    "货币基金":   {"score": 9.0, "note": "流动性管理+利率仍高"},
    "货币":      {"score": 9.0, "note": "短期利率仍高+避险"},
    # v6.4: Added missing sectors from config/etfs.yaml (F601 dedup: "跨境" and "中盘成长" already in base)
    "综合":          {"score": 5.5, "note": "Conglomerate, diversified demand"},
    "成长股":        {"score": 4.8, "note": "Growth stocks, stagflation headwind"},
    "大盘蓝筹":      {"score": 5.8, "note": "Large caps, resilient in stagflation"},
    "小盘价值":      {"score": 4.5, "note": "Small cap value, cyclical demand under stagflation"},
    "央企改革":      {"score": 6.0, "note": "Policy-driven reform catalyst"},
    "港股综合":      {"score": 4.8, "note": "HK broad market, liquidity + FX + regulatory risk"},
    "港股医药":      {"score": 5.5, "note": "HK pharma, moderate demand"},
    "港股科技":      {"score": 6.0, "note": "HK tech, AI/cloud demand"},
    "美股科技":      {"score": 6.5, "note": "US tech, AI/cloud demand"},
    "美股科技100":   {"score": 6.5, "note": "US tech 100, AI/cloud demand"},
    "美股综合":      {"score": 5.3, "note": "US broad market, mixed signals"},
    "美股杠杆":      {"score": 5.5, "note": "Leveraged US equity, speculative"},
    "中盘成长":      {"score": 5.5, "note": "Mid-cap growth, moderate demand"},  # noqa: F601 — intentional v6.4 overlay, same value as base L102
    "贵金属":        {"score": 7.5, "note": "Safe-haven demand, central bank buying"},
    "能源化工":      {"score": 4.0, "note": "Energy chemicals, cyclical demand + commodity risk"},
    "通信/光模块":   {"score": 6.0, "note": "Optical modules, AI infrastructure demand"},
    "机器人/智造":   {"score": 6.5, "note": "Automation/robotics strong demand"},
    "白酒消费":      {"score": 4.0, "note": "Declining consumption trend, inventory pressure"},
    "食品饮料":      {"score": 5.5, "note": "Staple food/beverage, steady demand"},
    "家电":          {"score": 5.5, "note": "Appliances, moderate demand with trade-in policy"},
    "消费":          {"score": 5.5, "note": "Broad consumer, moderate retail growth"},
    "医药":          {"score": 6.0, "note": "Pharma, aging population + innovation demand"},
    "农产品":        {"score": 5.5, "note": "Agriculture, food security policy support"},
    "半导体做空":    {"score": 4.5, "note": "Short semiconductor, speculative demand"},
    "半导体杠杆":    {"score": 4.0, "note": "Leveraged semiconductor, speculative demand"},
    "硬科技做空":    {"score": 6.0, "note": "Short hard tech, speculative demand"},
    "硬科技杠杆":    {"score": 6.0, "note": "Leveraged hard tech, speculative demand"},
    "有色金属":        {"score": 5.5, "note": "Metal prices volatile, supply constrained by mining cycles"},
    "周期/资源":     {"score": 4.8, "note": "Commodity cycle bottoming, stagflation headwind, mixed demand signals"},
    "其他":           {"score": 4.5, "note": "Unclassified sector, uncertainty discount"},
}


# === B2B Sector Risk (v8.10: expanded differentiation) ===
# Problem: 52% of entries clustered in [5.0, 6.0], with 5.5 having 21 entries (30%).
# Fix: Spread clustered values to create more distinct tiers.
# Low risk (safe): 7.5-9.0 | Moderate-low: 6.5-7.0 | Moderate: 5.5-6.0 | Moderate-high: 4.5-5.0 | High risk: 3.0-4.0
B2B_SECTOR_RISK = {
    # === Lowest risk (safe havens) ===
    "黄金":      {"score": 9.0, "note": "避险之王, 风险极低"},
    "贵金属":    {"score": 9.0, "note": "贵金属避险, 风险极低"},
    "货币基金":  {"score": 9.0, "note": "风险极低"},
    "货币":      {"score": 9.0, "note": "风险极低"},
    "利率债":    {"score": 8.5, "note": "无信用风险"},
    "公用事业":  {"score": 8.0, "note": "垄断+刚需, 风险极低"},
    "信用债":    {"score": 7.5, "note": "城投化债降低风险"},
    "红利+低波": {"score": 7.5, "note": "双重保护"},
    "红利/价值": {"score": 7.0, "note": "低波动+高股息, 风险较低"},
    "红利价值":  {"score": 7.0, "note": "防御属性强"},
    "高股息":    {"score": 7.0, "note": "现金流稳定"},
    "全市场":    {"score": 7.0, "note": "分散化降低风险"},
    "宽基":      {"score": 7.0, "note": "分散化降低风险"},
    "大盘蓝筹":  {"score": 7.0, "note": "大型蓝筹抗风险能力强"},
    "央企改革":  {"score": 6.5, "note": "SOE reform, policy-driven moderate risk"},
    "中药":      {"score": 6.5, "note": "政策支持对冲集采风险"},
    "保险":      {"score": 6.5, "note": "负债端稳定"},
    "银行":      {"score": 6.0, "note": "资产质量压力但系统重要性"},
    "跨境":      {"score": 6.0, "note": "汇率+地缘风险"},
    "综合":      {"score": 6.0, "note": "Diversified, moderate risk"},
    "可转债":    {"score": 6.0, "note": "信用+股市双重风险"},
    "金融":      {"score": 6.0, "note": "系统性风险可控"},
    "云计算/算力":{"score": 5.5, "note": "需求刚性, 风险较低"},
    "通信/5G":   {"score": 5.5, "note": "基建需求稳定"},
    "5G/PCB":    {"score": 5.5, "note": "技术迭代风险"},
    "港股科技":  {"score": 5.5, "note": "HK tech, moderate risk"},
    "美股科技":  {"score": 5.5, "note": "US tech, moderate risk"},
    "美股科技100":{"score": 5.5, "note": "US tech 100, moderate risk"},
    "美股综合":  {"score": 5.5, "note": "US broad market, moderate risk"},
    "港股医药":  {"score": 5.5, "note": "HK pharma, moderate risk"},
    "中盘成长":  {"score": 5.5, "note": "成长股波动大"},
    "成长股":    {"score": 5.5, "note": "Growth stocks, higher volatility risk"},
    "半导体":    {"score": 5.0, "note": "库存周期高位, 价格承压但AI对冲"},
    "AI算力":    {"score": 5.5, "note": "GPU需求旺盛但依赖海外供应"},
    "军工":      {"score": 6.0, "note": "订单确定性高, 利润率受限"},
    "航空航天":  {"score": 5.5, "note": "军民融合+技术壁垒"},
    "有色":      {"score": 5.5, "note": "全球需求不确定性, 能源转型对冲"},
    "小盘价值":  {"score": 5.0, "note": "Small cap value, moderate risk"},
    "医药器械":  {"score": 4.5, "note": "集采+国产替代双重压力"},
    "农产品":    {"score": 5.5, "note": "Weather + policy risk, food security hedge"},
    "有色金属":  {"score": 5.5, "note": "Global demand, energy transition demand"},
    "周期/资源": {"score": 5.0, "note": "Cyclical sector, macro-dependent risk"},
    "硬科技":    {"score": 5.0, "note": "技术路线+制裁风险"},
    "硬科技做空":{"score": 4.0, "note": "Speculative, moderate risk"},
    "硬科技杠杆":{"score": 3.5, "note": "Leveraged, amplified risk"},
    "半导体做空":{"score": 4.5, "note": "Speculative, moderate risk"},
    "半导体杠杆":{"score": 4.5, "note": "Leveraged, amplified risk"},
    "AI/科技":   {"score": 4.5, "note": "GPU供应瓶颈+估值偏高+制裁风险"},
    "新能源":    {"score": 4.5, "note": "产能过剩但政策托底"},
    "电池":      {"score": 4.5, "note": "技术迭代+需求增长但竞争加剧"},
    "证券":      {"score": 4.0, "note": "高度依赖市场情绪"},
    "券商":      {"score": 4.0, "note": "业绩与市场强相关"},
    "港股":      {"score": 4.0, "note": "流动性+汇率双重风险"},
    "中概互联网":{"score": 4.0, "note": "监管+退市风险"},
    "港股综合":  {"score": 4.0, "note": "HK broad, liquidity + FX risk"},
    "半导体设备":{"score": 4.0, "note": "设备订单可见度下降+制裁"},
    "通信/光模块":{"score": 4.0, "note": "Tech iteration risk"},
    "机器人/智造":{"score": 4.0, "note": "Tech risk but policy support"},
    "能源化工":  {"score": 4.0, "note": "Commodity cyclicality risk"},
    "电子":      {"score": 4.0, "note": "消费电子周期底部"},
    "光伏":      {"score": 3.5, "note": "严重产能过剩, 价格战"},
    "白酒消费":  {"score": 3.0, "note": "Inventory pressure + price decline risk"},
    "食品饮料":  {"score": 4.0, "note": "Moderate channel risk, price flat"},
    "家电":      {"score": 4.0, "note": "Substitution risk + price decline"},
    "消费":      {"score": 4.0, "note": "Moderate demand risk"},
    "医药":      {"score": 4.0, "note": "集采 pressure +国产替代"},
    "基建/地产": {"score": 3.0, "note": "房地产债务风险持续"},
    "美股杠杆":  {"score": 3.0, "note": "Leveraged, high risk"},
    "其他":      {"score": 4.5, "note": "Unclassified sector, neutral risk assumption"},
}


# === Economics Layer 1: Price Elasticity Coefficients ===
# Supply elasticity: how quickly supply can respond to price changes
# High elasticity (>1.0) = supply floods in fast = price crashes when demand drops
# Low elasticity (<0.5) = supply stuck = price spikes when demand rises
SUPPLY_ELASTICITY = {
    # Low elasticity (supply constrained) -> benefit from supply shocks
    "黄金":      0.05,  # 年产量仅增1-2%
    "铜":        0.30,  # 矿山建设周期3-5年
    "煤炭":      0.40,  # 产能受环保限制
    "稀土":      0.35,  # 中国出口管制+配额
    "锂辉石":    0.50,  # 从过剩到紧缺弹性仍低
    "铀":        0.20,  # 核电建设周期长
    
    # Medium elasticity
    "半导体":    0.80,  # 晶圆厂建设周期1-2年
    "军工":      0.60,  # 军品产能受管制但可调配
    "光伏":      1.20,  # 产能6个月可翻倍
    "新能源":    1.00,  # 混合
    
    # High elasticity (supply floods fast) -> vulnerable to oversupply
    "锂电":      2.50,  # 产能扩张极快
    "光伏玻璃":  2.00,  # 产能过剩
    "猪肉":      1.50,  # 猪周期2-3年
    "白糖":      1.80,  # 农业弹性高
    "乳制品":    1.60,  # 产能过剩
}

# Demand elasticity: how demand responds to price changes
# Inelastic demand (<1.0) = price hikes don't kill demand = pricing power
# Elastic demand (>1.0) = price hikes kill demand = volume-driven
DEMAND_ELASTICITY = {
    # Inelastic demand (pricing power)
    "黄金":      0.3,   # 央行购金+避险需求, 价格越高越买
    "利率债":    0.2,   # 避险需求刚性
    "公用事业":  0.1,   # 刚需
    "医药":      0.4,   # 生命需求, 价格不敏感
    "中药":      0.5,   # 品牌溢价+刚需
    
    # Medium elasticity
    "半导体":    0.8,   # AI需求刚性但消费电子弱
    "军工":      0.3,   # 政府采购, 价格不敏感
    "红利/价值": 0.6,   # 股息率驱动
    "AI算力":    0.7,   # Capex刚性但估值敏感
    
    # Elastic demand (volume-driven)
    "消费":      1.2,   # 可选消费
    "白酒":      1.5,   # 奢侈品属性, 价格敏感
    "家电":      1.3,   # 耐用消费品
    "汽车":      1.1,   # 大额可选消费
    "光伏":      1.8,   # 价格敏感, 补贴依赖
    "新能源":    1.4,   # 政策驱动
}

# Cross-elasticity: sector-to-sector demand spillover
# Positive = substitute (both benefit from same shock)
# Negative = complement (one benefits when other suffers)
CROSS_ELASTICITY = {
    # Substitutes (positive cross-elasticity)
    "猪肉/乳制品": 0.6,   # 替代消费
    "黄金/利率债": 0.7,   # 滞胀期同时受益
    "红利/价值/红利+低波": 0.8,  # 高度重叠
    
    # Complements (negative cross-elasticity in stagflation)
    "煤炭/电力": -0.5,   # 煤价涨利空电力
    "锂矿/锂电": -0.3,   # 锂价跌利好锂电(成本降)
    "原油/航空": -0.6,   # 油价涨利空航空
    
    # AI ecosystem complements
    "半导体/AI算力": 0.9,  # 强互补
    "光模块/半导体": 0.7,  # 强互补
    "PCB/AI算力": 0.6,    # 强互补
}

# === Economics Layer 2: Correlation Regime ===
# How correlations shift by economic regime
CORRELATION_REGIMES = {
    "stagflation": {  # 滞胀 (current: CPI 4.2%, jobs 57K)
        "gold_stock": 0.5,   # 黄金与股票正相关(罕见!)
        "oil_stock": 0.3,    # 能源与股票弱正相关
        "bond_stock": -0.1,  # 债券与股票不相关
        "tech_defense": 0.2, # 科技与防御弱相关
    },
    "recovery": {  # 复苏
        "gold_stock": -0.3,
        "oil_stock": 0.6,
        "bond_stock": -0.2,
        "tech_defense": -0.4,
    },
    "overheat": {  # 过热
        "gold_stock": -0.1,
        "oil_stock": 0.4,
        "bond_stock": -0.5,
        "tech_defense": -0.2,
    },
    "recession": {  # 衰退
        "gold_stock": 0.7,
        "oil_stock": -0.4,
        "bond_stock": 0.6,
        "tech_defense": -0.6,
    },
}

# Current regime: stagflation
CURRENT_REGIME = "stagflation"


# v8.29: Code-based micro-jitter for L11 intra-sector differentiation
# Previously ±0.45 was too small for sectors with 90+ identical-risk-level ETFs.
# Increased to ±1.0 to provide meaningful intra-sector differentiation.
def _l11_code_jitter(etf_code: str, base_score: float) -> float:
    """Deterministic jitter based on ETF code hash.
    
    Range: [-1.0, +1.0] — breaks clusters within same sector+risk_level.
    """
    jitter = 0.0
    if etf_code and etf_code.isdigit():
        digits = etf_code
        code_hash = sum(int(digits[i:i+2]) for i in range(0, len(digits)-1, 2))
        jitter = ((code_hash % 21) - 10) * 0.10  # range [-1.0, +1.0]
    return round(jitter, 2)


# v8.29: Code-based micro-jitter for L10 B2B fallback path
# Previously ±0.36 was too small. Increased to ±0.8.
def _l10_code_jitter(etf_code: str, base_score: float) -> float:
    """Deterministic jitter for L10 B2B keyword fallback.
    
    Range: [-0.8, +0.8] — breaks clusters where multiple ETFs map to same keyword score.
    """
    jitter = 0.0
    if etf_code and etf_code.isdigit():
        digits = etf_code
        code_hash = sum(int(digits[i:i+2]) for i in range(0, len(digits)-1, 2))
        jitter = ((code_hash % 17) - 8) * 0.10  # range [-0.8, +0.8]
    return round(jitter, 2)


# === Economics Layer 3: Information Chain Adjustments ===
# Moral hazard: when incentives misalign after transaction
# Signaling: observable behaviors that reveal hidden quality

ADVERSE_SELECTION_RISK = {
    # High adverse selection = quality uncertainty is severe
    "CXO/创新药": 0.7,   # 客户不知药企真实研发进度
    "光伏组件": 0.6,    # 买方不知组件真实衰减率
    "新能源车": 0.5,    # 买方不知电池真实寿命
    "债券": 0.4,        # 买方不知发行人真实偿债能力
    
    # Low adverse selection = quality transparent
    "黄金": 0.1,        # 标准化商品
    "铜": 0.1,          # 标准化商品
    "利率债": 0.05,     # 国家信用背书
    "红利+低波": 0.2,  # 分红可验证
}

MORAL_HAZARD_RISK = {
    # High moral hazard = incentive misalignment likely
    "银行信贷": 0.6,    # 借款人可能投高风险项目
    "公募基金": 0.5,    # 基金经理博取高收益
    "国企改革": 0.5,    # 管理层信息优势
    "新能源补贴": 0.7, # 骗补风险
    
    # Low moral hazard = aligned incentives
    "央企改革": 0.3,    # 国资监管严格
    "红利+低波": 0.2,  # 分红是真金白银
    "黄金": 0.1,       # 实物资产
}

SIGNAL_CREDIBILITY = {
    # High credibility signals (hard to fake)
    "股东回购": 0.9,    # 真金白银
    "分红": 0.9,        # 真金白银
    "研发投入占比": 0.8, # 审计严格
    "出口管制名单": 0.95, # 政府行为, 无法伪造
    
    # Medium credibility
    "ESG评级": 0.5,     # 可能被操纵
    "机构持仓": 0.6,    # 可能有滞后
    "专利数量": 0.5,    # 质量参差
    
    # Low credibility
    "口头承诺": 0.2,    # 无约束力
    "公关稿": 0.3,      # 选择性披露
}

def _keyword_risk_score(sec_str: str) -> float:
    """Keyword-based risk score fallback. Ordered lookup — first match wins."""
    s = str(sec_str)
    _RULES = [
        ("any", ("贵金属","黄金"), 9.0),
        ("any", ("公用事业","水电","燃气"), 8.5),
        ("all", ("红利","高股息"), 8.0), ("all", ("红利","低波"), 8.0),
        ("any", ("红利","高股息"), 7.5),
        ("any", ("货币","货币基金","国债"), 8.5), ("any", ("利率债",), 8.5),
        ("any", ("信用债",), 7.5), ("any", ("债",), 7.0),
        ("any", ("大盘蓝筹",), 7.5), ("any", ("央企改革",), 7.0),
        ("any", ("消费","白酒","食品饮料"), 7.0), ("any", ("家电",), 6.5),
        ("any", ("医药器械","医疗器械"), 7.0), ("any", ("中药",), 7.0),
        ("any", ("农产品","养殖","畜牧"), 6.5),
        ("any", ("宽基","全市场","沪深300","上证50"), 6.5),
        ("any", ("大盘",), 6.5), ("any", ("小盘价值",), 6.0),
        ("any", ("中盘成长","中证500","中证1000"), 5.5),
        ("any", ("成长股",), 5.0), ("any", ("银行",), 6.5),
        ("any", ("保险",), 6.5), ("any", ("金融",), 6.0),
        ("any", ("券商","证券"), 5.5), ("any", ("医药","医疗"), 6.5),
        ("any", ("综合",), 6.0), ("any", ("其他",), 5.5),
        ("any", ("有色","有色金属"), 5.5),
        ("any", ("周期/资源","煤炭"), 5.0),
        ("any", ("化工","能源化工"), 4.5), ("any", ("钢铁",), 4.5),
        ("any", ("军工","航空航天"), 5.5),
        ("any", ("机器人","智造"), 5.5),
        ("all", ("通信","光模块"), 5.5), ("all", ("通信","5G"), 5.5),
        ("any", ("5G/PCB",), 5.5), ("any", ("传媒","游戏"), 5.0),
        ("any", ("旅游",), 5.5), ("any", ("教育",), 4.5),
        ("all", ("美股","杠杆"), 2.5),
        ("all", ("美股","科技"), 5.0), ("all", ("美股","半导体"), 5.0),
        ("any", ("美股",), 5.5),
        ("all", ("港股","科技"), 5.0), ("all", ("港股","互联网"), 5.0),
        ("all", ("港股","红利"), 6.5), ("all", ("港股","价值"), 6.5),
        ("all", ("港股","低波"), 6.5), ("all", ("港股","医药"), 5.5),
        ("any", ("港股",), 4.5),
        ("any", ("跨境","QDII"), 5.5),
        ("any", ("半导体","芯片","硬科技"), 4.0),
        ("all", ("AI","算力"), 4.5), ("any", ("AI/科技","数字经济"), 5.0),
        ("any", ("云计算",), 5.0), ("any", ("新能源",), 4.5),
        ("any", ("光伏",), 4.0), ("any", ("风电",), 4.5),
        ("any", ("储能","锂电","电池"), 4.5),
        ("any", ("新能源汽车",), 4.5),
        ("any", ("房地产","地产"), 3.5), ("any", ("基建",), 4.0),
    ]
    for cond, keywords, score in _RULES:
        if cond == "any" and any(k in s for k in keywords):
            return score
        elif cond == "all" and all(k in s for k in keywords):
            return score
    return 5.5


def _keyword_demand_score(sec_str: str, risk_level: float = 0.5) -> float:
    """Fallback keyword-based demand score. Ordered lookup — first match wins."""
    s = str(sec_str)
    _RULES = [
        ("any", ("贵金属","黄金"), 7.5),
        ("all", ("美股","科技"), 6.5), ("all", ("美股","半导体"), 6.5),
        ("all", ("美股","杠杆"), 5.0), ("any", ("美股",), 5.5),
        ("all", ("港股","科技"), 6.0), ("all", ("港股","互联网"), 6.0),
        ("all", ("港股","红利"), 6.5), ("all", ("港股","价值"), 6.5),
        ("all", ("港股","低波"), 6.5), ("all", ("港股","医药"), 5.5),
        ("any", ("港股",), 5.5),
        ("any", ("大盘蓝筹",), 5.5), ("any", ("央企改革",), 6.0),
        ("any", ("小盘价值",), 5.0), ("any", ("成长股",), 5.5),
        ("any", ("机器人","智造"), 6.5),
        ("all", ("通信","光模块"), 6.0), ("all", ("通信","5G"), 6.0),
        ("any", ("能源化工",), 4.5), ("any", ("其他",), 5.0),
        ("any", ("综合",), 5.5), ("any", ("教育",), 4.0),
        ("any", ("半导体","芯片"), 6.5),
        ("any", ("AI","硬科技","云计算","数字经济"), 6.5),
        ("any", ("军工","航空航天"), 6.5),
        ("any", ("光伏",), 5.0),
        ("any", ("风电","储能","锂电","电池"), 5.5),
        ("any", ("新能源","新能源车"), 5.5),
        ("any", ("白酒","白酒消费"), 5.0),
        ("any", ("医药","医疗","中药","创新药"), 6.0),
        ("any", ("医疗器械","医药器械"), 6.0),
        ("any", ("旅游",), 5.5), ("any", ("传媒",), 5.5),
        ("any", ("游戏",), 5.5), ("any", ("钢铁","化工"), 5.0),
        ("any", ("有色","周期","资源","有色金属"), 5.5),
        ("any", ("煤炭",), 6.0), ("any", ("农产品",), 5.5),
        ("any", ("房地产","地产","基建"), 4.5),
        ("any", ("券商","证券"), 5.5),
        ("any", ("红利","价值","高股息","低波"), 6.5),
        ("any", ("宽基","全市场"), 5.5),
        ("any", ("货币","债券"), 7.0),
        ("any", ("公用事业","水电","燃气"), 6.5),
        # v16.22: L501 "水泥"规则保留(水泥未被其他规则覆盖), 移除不可达的"煤炭""钢铁"
        ("any", ("水泥",), 5.0),
        ("any", ("纺织","服装","轻工"), 5.0),
        ("any", ("运输","物流","航运"), 5.0),
        ("any", ("软件","IT服务","信息化"), 6.0),
        ("any", ("环保","水务","园林"), 5.5),
        ("any", ("机械","装备","制造"), 5.0),
    ]
    for cond, keywords, score in _RULES:
        if cond == "any" and any(k in s for k in keywords):
            return score
        elif cond == "all" and all(k in s for k in keywords):
            return score
    if risk_level > 0.6:
        return 4.5
    elif risk_level > 0.4:
        return 5.0
    return 5.5


def is_consumer_sector(sector):
    """判断行业是否属于消费类2C"""
    if not sector:
        return False
    sector_lower = sector.lower()
    consumer_lower = {s.lower() for s in CONSUMER_SECTORS}
    for cs in consumer_lower:
        if cs in sector_lower or sector_lower in cs:
            return True
    return False


def score_demand_climate(sector, risk_level: float = 0.5, etf_code: str = ""):
    """L10: 消费需求健康评分 (1-10)

    对非消费行业直接返回 7.0 (中性偏健康, 工业需求不受消费信心主导)
    对消费行业使用两模型加权:
      Model A: 社零增速(50%) + 消费信心(50%)
      Model B: 储蓄率(50%) + 失业率(50%)
      最终 = A*0.6 + B*0.4

    v7.4: Added risk_level parameter. Low-risk ETFs get +1.0 bonus (stable demand),
    high-risk ETFs get -1.0 penalty (volatile demand).
    v8.9: Added etf_code parameter for code-based micro-jitter on B2B fallback path.
    """
    if not is_consumer_sector(sector):
        b2b = B2B_DEMAND_CLIMATE.get(sector, {})
        if b2b:
            base_score = b2b["score"]
            # v8.16: Apply risk_level modulation for B2B exact-match sectors
            # Previously B2B exact matches returned static scores with no variance
            rl_mod = (0.5 - risk_level) * 2.0  # v8.32: reduced from 3.0 to prevent ceiling saturation for high-base B2B sectors
            final_score = round(max(3.0, min(9.0, base_score + rl_mod)), 1)
            # v8.16: Code-based jitter for intra-sector differentiation
            code_jitter = _l10_code_jitter(etf_code, final_score)
            final_score = round(max(3.0, min(9.0, final_score + code_jitter)), 1)
            return {"score": final_score, "data_covered": True,
                    "data_updated": DATA_LAST_UPDATED, "data_source": DATA_SOURCE_B2B,
                    "note": b2b.get("note", "B2B行业需求"), "source": "b2b_inferred"}
        # v7.6: Keyword-based fallback for B2B sectors not in B2B_DEMAND_CLIMATE
        # Added variance component to reduce clustering
        kw_score = _keyword_demand_score(sector, risk_level)
        rl_mod = (0.5 - risk_level) * 2.0  # v8.32: reduced from 3.0 to prevent ceiling saturation
        # v7.6: Add risk_level variance to differentiate similar kw_scores
        # High-risk ETFs get wider spread (more upside potential OR more downside)
        risk_variance = (risk_level - 0.5) * 1.5
        final_score = round(max(3.0, min(9.0, kw_score + rl_mod + risk_variance)), 1)
        # v8.9: Code-based jitter for intra-sector differentiation
        code_jitter = _l10_code_jitter(etf_code, final_score)
        final_score = round(max(3.0, min(9.0, final_score + code_jitter)), 1)
        return {"score": final_score, 
                "data_covered": False,
                "note": f"未知B2B行业, 使用关键词回退({kw_score})",
                "source": "keyword_fallback"}

    dc = DEMAND_CLIMATE.get(sector, DEMAND_CLIMATE.get("default"))
    if not dc:
        # v7.4: Apply risk_level modulation to default
        rl_mod = (0.5 - risk_level) * 2.0  # v8.32: reduced from 3.0 to prevent ceiling saturation
        return {"score": round(max(1.0, min(10.0, 7.0 + rl_mod)), 1), "data_covered": False}

    # Model A: 消费动力
    g_score = max(1, min(10, 3 + dc["retail_growth"] * 0.3))
    c_score = max(1, min(10, (dc["confidence"] - 70) * 0.2))
    model_a = round(g_score * 0.5 + c_score * 0.5, 1)

    # Model B: 消费压力 (越高=越不消费, 需取反)
    s_score = max(1, min(10, 15 - dc["savings_rate"] * 0.4))
    u_score = max(1, min(10, 10 - dc["unemployment"] * 0.45))
    model_b = round(s_score * 0.5 + u_score * 0.5, 1)

    score = round(model_a * 0.6 + model_b * 0.4, 1)
    score = max(1, min(10, score))
    
    # v7.4: risk_level modulation
    # Low-risk ETF (rl<=0.2) -> +1.0 bonus (stable consumer base)
    # High-risk ETF (rl>=0.8) -> -1.0 penalty (volatile demand)
    rl_mod = (0.5 - risk_level) * 2.0  # v8.32: reduced from 3.0 to prevent ceiling saturation
    score = round(max(1.0, min(10.0, score + rl_mod)), 1)

    return {
        "score": score,
        "model_a_power": model_a,
        "model_b_pressure": model_b,
        "retail_growth_pct": dc["retail_growth"],
        "confidence": dc["confidence"],
        "data_covered": True,
        "data_updated": DATA_LAST_UPDATED,
        "data_source": DATA_SOURCE_CONSUMER,
        "note": "",
    }


def score_sector_demand_risk(sector, risk_level: float = 0.5, etf_code: str = ""):
    """L11: 行业需求风险评分 (1-10, 越高越安全)
    
    v7.4: Added risk_level parameter. Compound risk for high-risk ETFs.
    v8.9: Added etf_code parameter for code-based micro-jitter.
          Same-sector ETFs with identical risk_level get identical scores.
          Code jitter breaks this cluster by adding deterministic micro-diff.
    """
    sdr = SECTOR_DEMAND_RISK.get(sector)
    if not sdr:
        b2b = B2B_SECTOR_RISK.get(sector, {})
        if b2b:
            # v7.4: Apply risk_level modulation
            b2b_score = float(b2b["score"])
            # v8.22: Reduced rl_mod from *8.0 to *5.0. 
            #   Previously: gold(9.0) with rl=0.22 → 9.0 + (0.22-0.5)*8 = 6.76.
            #   Now: gold(9.0) with rl=0.22 → 9.0 + (0.22-0.5)*5 = 7.60.
            #   This preserves more of the sector-level signal while keeping risk differentiation.
            rl_mod = (risk_level - 0.5) * 5.0
            b2b_score = round(max(1.0, min(10.0, b2b_score + rl_mod)), 1)
            # v8.9: Code-based jitter for intra-sector differentiation
            code_jitter = _l11_code_jitter(etf_code, b2b_score)
            b2b_score = round(max(1.0, min(10.0, b2b_score + code_jitter)), 1)
            return {"score": b2b_score, "data_covered": True,
                    "data_updated": DATA_LAST_UPDATED, "data_source": DATA_SOURCE_B2B,
                    "note": b2b.get("note", "B2B行业风险"), "source": "b2b_inferred"}
        # v7.4: Apply risk_level modulation
        # v7.5: Use keyword-based risk score instead of flat 6.0
        # v8.22: Reduced rl_mod from *6.0 to *4.0 to prevent low-risk sectors
        #   (e.g. 红利/价值 rl=0.22) from being dragged below their keyword baseline.
        #   Previously: rl=0.22 → rl_mod=-1.68, dragging kw_risk=7.5 down to 5.8.
        #   Now: rl=0.22 → rl_mod=-1.12, preserving more of the keyword signal.
            kw_risk = _keyword_risk_score(sector)
            rl_mod = (risk_level - 0.5) * 4.0
            score = round(max(1.0, min(10.0, kw_risk + rl_mod)), 1)
        # v8.9: Code-based jitter
        code_jitter = _l11_code_jitter(etf_code, score)
        score = round(max(1.0, min(10.0, score + code_jitter)), 1)
        return {"score": score, "data_covered": False, 
                "note": f"未知行业风险, 关键词回退({kw_risk})", "source": "keyword_fallback"}

    # Model A: 渠道/价格健康
    inv = sdr["inventory_days"]
    inv_score = 10 if inv < 30 else (8 if inv < 60 else (6 if inv < 120 else (4 if inv < 300 else max(1, 10 - inv/150))))
    price_map = {"上涨": 8, "持平": 6, "下跌": 3}
    price_score = price_map.get(sdr["price_trend"], 5)
    price_penalty = min(0, sdr["price_change_pct"]) * 0.1
    model_a = round(max(1, min(10, inv_score * 0.5 + (price_score + price_penalty) * 0.5)), 1)

    # Model B: 结构性风险
    risk_map = {"极高": 1, "高": 3, "中": 5, "低": 7, "极低": 9}
    demo = risk_map.get(sdr.get("demographic", "中"), 5)
    sub = risk_map.get(sdr.get("substitution", "中"), 5)
    policy = risk_map.get(sdr.get("policy", "中"), 5)
    scenario = risk_map.get(sdr.get("scenario", "中"), 5)
    model_b = round((demo + sub + policy + scenario) / 4, 1)

    # v8.10: Changed from pure pessimistic min() to blended approach.
    # Old: min(model_a, model_b) was too harsh, pulling all scores toward the lower model.
    # New: blend 70% pessimistic (min) + 30% average for better spread.
    # This preserves risk-awareness while allowing differentiation.
    score = min(model_a, model_b) * 0.7 + (model_a + model_b) / 2 * 0.3
    
    # v7.4: risk_level modulation (compound risk)
    # v8.22: Reduced from *8.0 to *5.0 to prevent over-penalizing low-risk sectors.
    #   Previously rl=0.22 → rl_mod=-2.24, which dragged good sectors (e.g. 公用事业) 
    #   below their intrinsic risk-adjusted score.
    rl_mod = (risk_level - 0.5) * 5.0
    score = round(max(1.0, min(10.0, score + rl_mod)), 1)
    
    # v8.9: Code-based jitter for intra-sector differentiation
    code_jitter = _l11_code_jitter(etf_code, score)
    score = round(max(1.0, min(10.0, score + code_jitter)), 1)
    
    return {
        "score": score,
        "model_a_channel": model_a,
        "model_b_structural": model_b,
        "data_covered": True,
        "note": "",
    }


def apply_economics_adjustment(sector, base_score):
    """Apply economics-layer adjustments to base demand score.
    
    Combines:
    1. Supply elasticity premium (low elasticity = pricing power in supply shock)
    2. Demand elasticity adjustment (inelastic = stable revenue)
    3. Correlation regime bonus (stagflation favors defensive resources)
    4. Information chain penalty (adverse selection reduces score)
    """
    adjusted = base_score
    adjustments = []
    
    # 1. Supply elasticity: low elasticity = benefit from supply shocks
    supply_el = SUPPLY_ELASTICITY.get(sector)
    if supply_el is not None:
        if supply_el < 0.5:
            # Very low elasticity -> supply shock premium
            premium = (0.5 - supply_el) * 2.0  # Up to +1.0
            adjusted += premium
            adjustments.append(f"供给弹性{supply_el:.2f}(低)->+{premium:.1f}")
        elif supply_el > 1.5:
            # High elasticity -> oversupply penalty
            penalty = -(supply_el - 1.5) * 0.5  # Up to -0.5
            adjusted += penalty
            adjustments.append(f"供给弹性{supply_el:.2f}(高)->{penalty:.1f}")
    
    # 2. Demand elasticity: inelastic demand = pricing power
    demand_el = DEMAND_ELASTICITY.get(sector)
    if demand_el is not None:
        if demand_el < 0.5:
            # Inelastic -> stable revenue
            adjusted += 0.3
            adjustments.append(f"需求弹性{demand_el:.1f}(低)->+0.3(定价权)")
        elif demand_el > 1.5:
            # Elastic -> volume risk
            adjusted -= 0.3
            adjustments.append(f"需求弹性{demand_el:.1f}(高)->-0.3(量价风险)")
    
    # 3. Correlation regime: stagflation bonus for defensive assets
    regime = CORRELATION_REGIMES.get(CURRENT_REGIME, {})
    if "黄金" in sector:
        adjusted += 0.5  # Gold strong in stagflation
        adjustments.append("滞胀期黄金+0.5")
    elif "红利" in sector or "低波" in sector:
        adjusted += 0.3  # Defensive assets
        adjustments.append("滞胀期红利+0.3")
    elif "银行" in sector or "券商" in sector:
        adjusted -= 0.3  # Financials weak in stagflation
        adjustments.append("滞胀期金融-0.3")
    
    # 4. Information chain: adverse selection penalty
    # Check if sector has known adverse selection issues
    for key, risk in ADVERSE_SELECTION_RISK.items():
        if key.lower() in sector.lower() or sector.lower() in key.lower():
            if risk > 0.5:
                adjusted -= (risk - 0.5) * 1.5
                adjustments.append(f"逆向选择风险{risk:.1f}->-{(risk-0.5)*1.5:.1f}")
    
    # Clamp to [1, 10]
    adjusted = max(1.0, min(10.0, adjusted))
    
    return round(adjusted, 1), adjustments


def add_demand_layers(penetration_result, sector=None):
    """给穿透结果追加 L10+L11 层 + 经济学调整"""
    if sector is None:
        sector = penetration_result.get("sector", "default")
    
    l10 = score_demand_climate(sector)
    l11 = score_sector_demand_risk(sector)
    
    layers = penetration_result.get("layer_scores", {})
    base_l10 = l10["score"]
    base_l11 = l11["score"]
    
    # Apply economics adjustments
    adj_l10, adj_notes_l10 = apply_economics_adjustment(sector, base_l10)
    adj_l11, adj_notes_l11 = apply_economics_adjustment(sector, base_l11)
    
    layers["L10_Demand"] = adj_l10
    layers["L11_SectorRisk"] = adj_l11
    penetration_result["layer_scores"] = layers
    
    penetration_result["demand_detail"] = {
        "L10": {
            "raw": base_l10,
            "adjusted": adj_l10,
            "adjustments": adj_notes_l10,
            "data_covered": l10.get("data_covered", False),
            "data_updated": DATA_LAST_UPDATED,
            "data_source": DATA_SOURCE_ECONOMICS,
        },
        "L11": {
            "raw": base_l11,
            "adjusted": adj_l11,
            "adjustments": adj_notes_l11,
            "data_covered": l11.get("data_covered", False),
            "data_updated": DATA_LAST_UPDATED,
            "data_source": DATA_SOURCE_ECONOMICS,
        },
        "regime": CURRENT_REGIME,
        "elasticities": {
            "supply": SUPPLY_ELASTICITY.get(sector, "N/A"),
            "demand": DEMAND_ELASTICITY.get(sector, "N/A"),
        },
    }
    return penetration_result
