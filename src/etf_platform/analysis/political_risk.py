"""L12 Political Risk Layer — 政治风险量化与ETF映射.

Purpose: Quantify political risk for each ETF sector and adjust penetration scores.
Political risk includes: regulatory risk, geopolitical risk, policy uncertainty,
election cycle effects, and regime change risk.

Framework:
1. Regulatory intensity by sector (how much government intervention)
2. Geopolitical exposure (US-China tensions, sanctions risk)
3. Policy uncertainty index (EPU index by sector)
4. Geopolitical risk (GPR index by sector)
5. Political hedging (which sectors naturally hedge political risk)
"""

# === Regulatory Intensity by Sector ===
# How susceptible is each sector to government regulation/intervention?
# Scale: 0 = no regulation, 1 = extreme regulation
REGULATORY_INTENSITY = {
    # Extreme regulation (government controls pricing, licensing, or market access)
    "金融": 0.95,        # 银行/证券/保险 — 强监管
    "医药": 0.90,        # 集采定价+审批许可
    "教育": 0.95,        # 双减后教培几乎全管制
    "房地产": 0.90,      # 限价+限购+预售资金监管
    "白酒": 0.70,        # 消费税+反腐+广告限制
    "互联网": 0.85,      # 数据安全+反垄断+内容审核
    "光伏": 0.75,        # 补贴退坡+产能调控
    "新能源": 0.75,      # 补贴退坡+产能调控
    
    # Moderate regulation
    "半导体": 0.70,      # 出口管制+国产替代政策
    "军工": 0.60,        # 军方采购+保密要求
    "医药器械": 0.70,    # 审批+集采
    "银行": 0.95,        # 资本充足率+信贷政策
    "券商": 0.85,        # IPO暂停/加速=政策驱动
    "保险": 0.90,        # 偿付能力监管
    "基建/地产": 0.85,   # 土地+信贷+限价
    "消费": 0.50,        # 食品安全+广告法
    "食品饮料": 0.50,    # 食品安全+标签法规
    "汽车": 0.60,        # 排放标准+新能源补贴
    "有色金属": 0.55,    # 环保+出口配额
    "周期/资源": 0.60,   # 环保+安全生产
    "煤炭": 0.70,        # 安全+环保+价格指导
    "公用事业": 0.85,    # 电价/水价政府定价
    "通信/5G": 0.75,     # 频谱牌照+建设规划
    "AI/科技": 0.55,     # 数据安全+AI伦理
    "红利/价值": 0.40,   # 分红政策监管
    "黄金": 0.30,        # 市场化定价
    "债券": 0.60,        # 信用评级+发行审批
    "中药": 0.65,        # 医保目录+配方管理
    "可转债": 0.70,      # 发行审核+转股限制
    "利率债": 0.50,     # 国债市场化
    "货币基金": 0.40,    # 流动性监管
    "跨境": 0.65,        # 汇率管制+投资额度
    "港股": 0.60,        # 互联互通+审批
    "中概互联网": 0.85,  # 中美双重监管
    "硬科技": 0.65,      # 补贴+出口管制
    "半导体设备": 0.75,  # 出口管制+国产替代
    "AI算力": 0.50,      # 数据中心审批+能耗指标
    "云计算/算力": 0.50,
    "5G/PCB": 0.45,
    "电子": 0.40,
    "航空航天": 0.65,
    "农林牧渔": 0.55,    # 补贴+最低收购价
    "农产品": 0.55,
    "养殖": 0.50,        # 环保+疫病防控
    "畜牧": 0.55,        # v8.11: adjusted from 0.50
    "传媒": 0.70,        # 内容审查+牌照
    "游戏": 0.75,        # 版号+未成年人保护
    "旅游": 0.40,        # 景区定价+安全
    "家电": 0.35,        # 能效标准+以旧换新
    "全市场": 0.50,
    "宽基": 0.50,
    "中盘成长": 0.50,
    "大盘蓝筹": 0.45,
    "成长股": 0.35,      # v8.11: adjusted from 0.50
    "高股息": 0.40,
    "红利+低波": 0.40,
    "红利价值": 0.40,
    "港股医药": 0.65,
    "贵金属": 0.30,
    "通信/光模块": 0.70,  # v8.11: adjusted from 0.50
    "其他": 0.50,
    # v8.11-v8.14: Previously-missing sectors (F601 dedup: removed keys already in base)
    "电池": 0.65,        # IRA法案+技术管制
    "农牧": 0.55,        # 贸易摩擦+粮食安全
    "CXO/创新药": 0.85,  # BIOSECURE Act
    "钢铁": 0.30,        # 出口关税+贸易摩擦
    "有色": 0.40,        # 稀土出口管制反制
    "港股综合": 0.55,    # 互联互通+审批
    "能源化工": 0.50,    # 环保+出口配额
    "美股科技100": 0.75, # 中美脱钩+审计
    "小盘价值": 0.45,    # 分散化+低波动
}

# === Geopolitical Exposure by Sector ===
# How exposed is each sector to US-China tensions, sanctions, tariffs?
# Scale: 0 = no exposure, 1 = extreme exposure
GEOPOLITICAL_EXPOSURE = {
    # Extreme geopolitical risk
    "半导体": 0.95,       # 芯片禁令+出口管制
    "半导体设备": 0.95,   # ASML/应用材料出口限制
    "中概互联网": 0.90,   # 退市风险+审计争端
    "CXO/创新药": 0.85,   # BIOSECURE Act
    "AI/科技": 0.80,      # AI芯片限制+技术封锁
    "AI算力": 0.80,       # GPU出口管制
    "通信/5G": 0.75,      # 华为禁令+5G安全审查
    "5G/PCB": 0.65,       # 出口管制间接影响
    "电子": 0.60,         # 供应链全球化
    "硬科技": 0.75,       # 技术封锁+国产替代
    
    # Moderate geopolitical risk
    "新能源": 0.55,       # 美国IRA法案排斥中国光伏
    "光伏": 0.60,         # 美国关税+东南亚转口
    "电池": 0.55,         # 美国IRA法案限制中国电池
    "汽车": 0.50,         # 欧盟反补贴调查
    "有色金属": 0.45,      # 稀土出口管制反制
    "周期/资源": 0.40,    # 大宗商品全球定价
    "军工": 0.35,         # 国防自主+不受制裁影响
    "航空航天": 0.40,     # 商用飞机受波音空客影响
    "港股": 0.55,         # 中美关系影响港股流动性
    "跨境": 0.50,         # 汇率+资本管制
    "医药": 0.45,         # 创新药出海审批
    "医药器械": 0.40,     # 医疗器械进口依赖
    "中药": 0.20,         # 纯内需+无供应链风险
    "消费": 0.25,         # 内需为主
    "食品饮料": 0.20,     # 纯内需
    "白酒": 0.15,         # 纯内需+无供应链风险
    "家电": 0.35,         # 出口占比不高
    "传媒": 0.25,         # 内容监管为主
    "游戏": 0.35,         # 版号+出海
    "旅游": 0.20,         # 内需为主
    "券商": 0.35,         # 国内业务+港股通
    "保险": 0.25,         # 国内业务为主
    "红利/价值": 0.20,    # 高股息央企抗地缘风险
    "红利+低波": 0.15,    # 防御+内需
    "黄金": 0.10,         # 避险资产+不受制裁
    "债券": 0.20,         # 国内债券市场
    "利率债": 0.15,       # 国债
    "可转债": 0.25,       # 国内
    "货币基金": 0.10,     # 国内
    "宽基": 0.25,         # 分散化降低地缘风险
    "全市场": 0.25,
    "中盘成长": 0.35,     # 中小科技企业受出口管制影响
    "大盘蓝筹": 0.25,     # 央企蓝筹抗风险
    "公用事业": 0.10,     # 纯内需+垄断
    "煤炭": 0.20,         # 内需为主
    "钢铁": 0.30,         # 出口占比不高
    "基建/地产": 0.15,    # 纯内需
    "养殖": 0.10,         # 纯内需
    "农牧": 0.10,
    "农林牧渔": 0.10,
    "农产品": 0.15,
    "贵金属": 0.10,
    "有色": 0.40,
    "高股息": 0.20,
    "红利价值": 0.20,
    "港股医药": 0.50,     # 港股+医药双重风险
    "云计算/算力": 0.70,  # GPU依赖
    "其他": 0.30,
    # v8.11-v8.14: Previously-missing sectors (F601 dedup: removed keys already in base)
    "金融": 0.10,        # 银行/证券/保险 — 纯国内业务, 低地缘风险 (FIXED: was 0.95, copy-paste error from 半导体)
    "银行": 0.10,        # 资本充足率+信贷政策 (FIXED: was 0.95, copy-paste error from 半导体)
    "房地产": 0.90,      # 限价+限购+预售资金监管
    "畜牧": 0.10,        # 贸易摩擦+疫病
    "通信/光模块": 0.70, # 美国实体清单+出口管制
    "互联网": 0.85,      # 数据安全+反垄断
    "教育": 0.90,        # 双减+中美关系
    "成长股": 0.35,      # 中小科技企业受出口管制影响
    "港股综合": 0.50,    # 中美关系+互联互通
    "能源化工": 0.35,    # 大宗商品定价
    "美股科技100": 0.85, # 脱钩+审计+制裁
    "小盘价值": 0.20,    # 分散化+内需
}

# === Political Risk Premium by Sector ===
# Additional return investors demand for holding politically risky sectors
# Based on: regulatory intensity + geopolitical exposure + policy uncertainty
POLITICAL_RISK_PREMIUM = {
    # High risk premium (investors demand extra return)
    "半导体": 3.5,        # 出口管制+国产替代不确定性
    "CXO/创新药": 3.0,    # BIOSECURE Act+审批不确定性
    "中概互联网": 2.8,    # 退市+审计+监管
    "AI/科技": 2.5,       # AI芯片限制+技术封锁
    "光伏": 2.2,          # 产能调控+补贴退坡
    "券商": 2.0,          # IPO暂停/加速政策驱动
    "游戏": 2.0,          # 版号+未成年人保护
    "互联网": 2.0,        # 反垄断+数据安全
    "房地产": 2.5,        # 政策反复+债务风险
    "白酒": 1.8,          # 反腐+消费税
    "医药": 1.5,          # 集采+审批
    
    # Moderate risk premium
    "新能源": 1.5,        # 补贴退坡+产能调控
    "通信/5G": 1.5,      # 频谱牌照+建设规划
    "电子": 1.2,          # 供应链全球化
    "汽车": 1.2,          # 新能源补贴+排放标准
    "传媒": 1.2,          # 内容审查+牌照
    "有色金属": 1.0,      # 环保+出口配额
    "港股": 1.5,          # 中美关系+流动性
    "跨境": 1.2,          # 汇率+资本管制
    "医药器械": 1.0,      # 集采+进口依赖
    "硬科技": 1.2,        # 补贴+出口管制
    "军工": 0.8,          # 订单确定性高但利润率受限
    "航空航天": 1.0,      # 军民融合
    "煤炭": 0.8,          # 安全+环保约束
    "周期/资源": 1.0,     # 商品价格波动
    "银行": 0.8,          # 信贷政策+坏账
    "保险": 0.6,          # 偿付能力监管
    "消费": 0.5,          # 消费信心+食品安全
    "食品饮料": 0.4,      # 食品安全+标签
    "家电": 0.4,          # 以旧换新+能效
    "中药": 0.5,          # 医保目录+配方
    "公用事业": 0.3,      # 电价政府定价
    "黄金": 0.1,          # 避险资产
    "债券": 0.3,          # 国内债券市场
    "利率债": 0.2,        # 国债
    "红利/价值": 0.3,     # 分红政策
    "红利+低波": 0.2,     # 防御属性
    "宽基": 0.3,
    "全市场": 0.3,
    "中盘成长": 0.5,
    "大盘蓝筹": 0.3,
    "养殖": 0.3,          # 猪周期
    "农牧": 0.3,
    "农林牧渔": 0.3,
    "农产品": 0.3,
    "贵金属": 0.1,
    # "有色": 0.8,  # F601 dedup: moved to v8.11 fill section with corrected value 1.0
    "高股息": 0.3,
    "红利价值": 0.3,
    "港股医药": 2.0,      # 港股+医药双重风险
    "云计算/算力": 2.0,   # GPU依赖
    "半导体设备": 3.0,    # 出口管制+国产替代
    "AI算力": 2.5,        # GPU依赖
    "5G/PCB": 1.0,
    "通信/光模块": 1.5,
    "其他": 0.5,
    # v8.11: Previously-missing sectors (F601 dedup: removed keys already in base)
    "金融": 0.8,          # 银行/证券/保险 — 信贷政策
    "电池": 1.5,          # IRA法案+技术管制
    "畜牧": 0.3,          # 贸易摩擦+疫病
    "钢铁": 0.8,          # 出口关税+贸易摩擦
    "有色": 1.0,          # 稀土出口管制反制 (F601: corrected from 0.8)
    "教育": 2.5,          # 双减+政策不确定性
    "成长股": 0.5,        # 中小科技企业受出口管制影响
}

# === Natural Political Hedges ===
# Which sectors naturally hedge against political risk
POLITICAL_HEDGE = {
    "黄金": {"hedge_against": ["半导体", "中概互联网", "互联网", "AI/科技"]},
    "红利/价值": {"hedge_against": ["券商", "半导体", "光伏", "新能源"]},
    "公用事业": {"hedge_against": ["半导体", "互联网", "中概互联网"]},
    "债券": {"hedge_against": ["券商", "中概互联网"]},
    "宽基": {"hedge_against": ["半导体", "光伏", "新能源"]},
}

# === Economic Policy Uncertainty (EPU) by Sector ===
# Based on Baker-Bloom-Davis EPU Index by sector
EPU_BY_SECTOR = {
    # High uncertainty
    "半导体": 85,        # 出口管制+国产替代
    "中概互联网": 80,    # 退市+审计
    "互联网": 75,        # 反垄断+数据安全
    "光伏": 70,          # 产能调控+补贴退坡
    "券商": 65,          # IPO政策驱动
    "房地产": 70,        # 政策反复
    "医药": 60,          # 集采不确定性
    "CXO/创新药": 75,    # BIOSECURE Act
    
    # Moderate uncertainty
    "新能源": 55,        # 补贴退坡
    "AI/科技": 60,       # AI监管
    "汽车": 50,          # 新能源补贴
    "游戏": 55,          # 版号政策
    "传媒": 50,          # 内容监管
    "电子": 45,          # 供应链
    "港股": 50,          # 中美关系
    "跨境": 45,          # 汇率+资本管制
    "军工": 40,          # 预算公开
    "银行": 45,          # 信贷政策
    "保险": 40,          # 偿付能力
    "有色金属": 40,      # 环保政策
    "周期/资源": 45,     # 商品价格
    "煤炭": 40,          # 安全环保
    "消费": 35,          # 消费信心
    "食品饮料": 30,      # 食品安全
    "家电": 30,          # 以旧换新
    "中药": 35,          # 医保目录
    "公用事业": 25,      # 电价管制
    "黄金": 20,          # 市场化
    "债券": 25,          # 国债
    "利率债": 20,        # 避险
    "红利+低波": 20,     # 防御
    "宽基": 30,          # 分散化
    "全市场": 30,
    "其他": 40,
    # v8.11-v8.14: Previously-missing sectors (F601 dedup: removed keys already in base)
    "金融": 45,          # 信贷政策
    "电池": 50,          # IRA法案
    "农牧": 35,          # 贸易摩擦
    "畜牧": 35,          # 疫病
    "钢铁": 35,          # 出口关税
    "通信/光模块": 55,   # 实体清单
    "有色": 40,          # 稀土出口
    "教育": 80,          # 双减
    "成长股": 40,        # 出口管制
    "港股综合": 45,      # 中美关系+流动性
    "能源化工": 40,      # 环保+价格管制
    "美股科技100": 70,   # 脱钩+审计+制裁
    "小盘价值": 30,      # 分散化
    "红利/价值": 25,     # 分红政策稳定
    "高股息": 25,         # 防御属性
}

# === Geopolitical Risk Index (GPR) by Sector ===
# Based on Caldara-Iacoviello GPR Index
GPR_BY_SECTOR = {
    # High geopolitical risk
    "半导体": 90,        # 芯片禁令
    "军工": 70,          # 台海风险
    "中概互联网": 85,    # 退市风险
    "AI/科技": 80,       # 技术封锁
    "半导体设备": 90,    # ASML限制
    "CXO/创新药": 75,    # BIOSECURE Act
    
    # Moderate geopolitical risk
    "港股": 60,          # 中美关系
    "跨境": 55,          # 汇率+资本管制
    "新能源": 50,        # IRA法案
    "光伏": 55,          # 美国关税
    "汽车": 45,          # 欧盟反补贴
    "电子": 45,          # 供应链
    "医药": 40,          # 出海审批
    "有色金属": 35,      # 稀土管制
    "周期/资源": 30,     # 大宗商品
    "银行": 30,          # 国内业务
    "券商": 30,          # 国内业务
    "保险": 25,          # 国内业务
    "消费": 20,          # 内需为主
    "食品饮料": 15,      # 纯内需
    "白酒": 10,          # 纯内需
    "家电": 25,          # 出口占比不高
    "传媒": 20,          # 内容监管
    "游戏": 25,          # 版号+出海
    "旅游": 15,          # 内需为主
    "公用事业": 10,      # 纯内需垄断
    "黄金": 10,          # 避险资产
    "债券": 15,          # 国内债券市场
    "利率债": 10,        # 极低: 国债
    "红利+低波": 15,    # 极低: 防御
    "宽基": 20,          # 很低: 分散化
    "全市场": 20,
    "其他": 30,
    # v8.11-v8.14: Previously-missing sectors (F601 dedup: removed keys already in base)
    "金融": 30,          # 国内业务
    "房地产": 20,        # 纯内需
    "电池": 50,          # IRA法案
    "农牧": 15,          # 内需为主
    "畜牧": 15,          # 内需为主
    "钢铁": 25,          # 出口关税
    "通信/光模块": 70,   # 实体清单
    "有色": 35,          # 稀土出口
    "互联网": 80,        # 数据安全
    "教育": 60,          # 双减+中美
    "成长股": 35,        # 出口管制
    "港股综合": 50,      # 中美关系+流动性
    "能源化工": 30,      # 大宗商品定价
    "美股科技100": 75,   # 脱钩+审计+制裁
    "小盘价值": 15,      # 分散化+内需
    "红利/价值": 15,     # 防御属性
    "高股息": 15,         # 防御+内需
}


def calculate_political_risk_score(sector, etf_code="", risk_level=0.5):
    """Calculate comprehensive political risk score for a sector + ETF.
    
    Combines:
    1. Regulatory intensity (how much government intervention)
    2. Geopolitical exposure (US-China tensions)
    3. Policy uncertainty (EPU index by sector)
    4. Geopolitical risk (GPR index by sector)
    5. ETF-level modulation via code jitter and risk_level
    
    Returns: dict with composite score and component breakdown
    """
    reg_intensity = REGULATORY_INTENSITY.get(sector, 0.5)
    geo_exposure = GEOPOLITICAL_EXPOSURE.get(sector, 0.5)
    epu = EPU_BY_SECTOR.get(sector, 50) / 100.0
    gpr = GPR_BY_SECTOR.get(sector, 50) / 100.0
    
    # Composite: weighted average
    # Regulatory risk is most direct, geopolitical is secondary
    composite = reg_intensity * 0.4 + geo_exposure * 0.3 + epu * 0.2 + gpr * 0.1
    
    # Map to 0-10 scale
    base_score = round(composite * 10, 1)
    
    # v8.17: ETF-level differentiation — previously same sector = same score
    # Add risk_level modulation (low-risk ETFs face less political risk)
    rl_mod = (0.5 - risk_level) * 1.5
    score = base_score + rl_mod
    
    # v8.17: Code-based jitter for intra-sector differentiation
    # Large sectors like "综合"(90 ETFs) and "宽基"(70 ETFs) need micro-differentiation
    if etf_code and etf_code.isdigit():
        digits = etf_code
        h = 0
        for d in digits:
            h = (h * 31 + int(d)) % 10000
        code_jitter = (h / 10000.0 * 2 - 1) * 0.8  # range [-0.8, +0.8]
        score = score + code_jitter
    
    score = round(max(1.0, min(10.0, score)), 1)
    
    return {
        "composite_score": base_score,
        "adjusted_score": score,
        "regulatory_intensity": round(reg_intensity * 10, 1),
        "geopolitical_exposure": round(geo_exposure * 10, 1),
        "policy_uncertainty": round(epu * 10, 1),
        "geopolitical_risk": round(gpr * 10, 1),
        "risk_level": _risk_level(score),
        "political_risk_premium": POLITICAL_RISK_PREMIUM.get(sector, 1.0),
        "natural_hedges": _get_hedges(sector),
    }


def _risk_level(score):
    """Map risk score to qualitative level."""
    if score >= 8:
        return "极高"
    elif score >= 6:
        return "很高"
    elif score >= 4:
        return "中高"
    elif score >= 2:
        return "中低"
    else:
        return "低"


def _get_hedges(sector):
    """Get natural hedges for a sector."""
    for hedge_name, hedge_data in POLITICAL_HEDGE.items():
        if isinstance(hedge_data, dict) and "hedge_against" in hedge_data:
            if sector in hedge_data["hedge_against"]:
                return hedge_data["hedge_against"]
    return []


def adjust_penetration_for_politics(penetration_result, sector=None):
    """Adjust penetration score for political risk.
    
    Reduces the final score based on political risk premium.
    High political risk sectors get penalized.
    Low political risk sectors (hedges) get a small boost.
    """
    if sector is None:
        sector = penetration_result.get("sector", "default")
    
    risk_info = calculate_political_risk_score(sector)
    risk_score = risk_info["composite_score"]
    
    # Political risk penalty: higher risk = lower adjusted score
    # Scale: 0 risk = no penalty, 10 risk = -2.0 points
    penalty = (risk_score / 10.0) * 2.0
    
    # Get current layers
    layers = penetration_result.get("layer_scores", {})
    base_score = layers.get("L7_Penetration", 5.0)
    
    # Apply penalty
    adjusted_score = max(1.0, base_score - penalty)
    
    return {
        "original_score": base_score,
        "adjusted_score": round(adjusted_score, 1),
        "penalty": round(penalty, 2),
        "political_risk_score": risk_score,
        "risk_level": risk_info["risk_level"],
    }
