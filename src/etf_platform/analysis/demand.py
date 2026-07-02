"""L10+L11 需求层评分 (修正版)

vs 旧版 demand_scoring.py 的区别:
  1. 区分消费2C行业 vs B2B行业 — 半导体/AI/基建等不受消费信心影响
  2. B2B/非消费行业 L10 默认为 7.0 (中性偏健康)
  3. 消费行业才用社零增速+信心指数+储蓄率+失业率模型
  4. L51 保持原有悲观聚合逻辑
"""

# 消费类行业清单（受社零+消费信心直接影响）
CONSUMER_SECTORS = {
    "消费", "白酒消费", "食品饮料", "白酒", "家电", "汽车",
    "医药", "医疗", "医疗器械", "医药生物",
    "养殖", "农牧", "畜牧", "农产品",
    "旅游", "传媒", "游戏",
    "港股消费",
}

# L10 需求气候数据 (仅对消费行业有意义)
DEMAND_CLIMATE = {
    "消费":     {"retail_growth": 3.0, "confidence": 82, "savings_rate": 34, "unemployment": 16},
    "白酒消费": {"retail_growth": -2.0, "confidence": 82, "savings_rate": 34, "unemployment": 16},
    "白酒":     {"retail_growth": -2.0, "confidence": 82, "savings_rate": 34, "unemployment": 16},
    "食品饮料": {"retail_growth": 2.0, "confidence": 82, "savings_rate": 34, "unemployment": 16},
    "家电":     {"retail_growth": 1.5, "confidence": 82, "savings_rate": 34, "unemployment": 16},
    "汽车":     {"retail_growth": 4.0, "confidence": 82, "savings_rate": 34, "unemployment": 16},
    "医药":     {"retail_growth": 5.0, "confidence": 85, "savings_rate": 34, "unemployment": 16},
    "医疗":     {"retail_growth": 5.0, "confidence": 85, "savings_rate": 34, "unemployment": 16},
    "养殖":     {"retail_growth": 2.0, "confidence": 80, "savings_rate": 34, "unemployment": 16},
    "传媒":     {"retail_growth": 6.0, "confidence": 82, "savings_rate": 34, "unemployment": 16},
    "default":  {"retail_growth": 4.0, "confidence": 85, "savings_rate": 32, "unemployment": 14},
}

# L11 行业需求风险数据
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
}

# === B2B行业需求气候 (l006 P0修复) ===
# 非消费行业也有需求周期, 用行业景气指标替代社零+消费信心
# 数据来源: 行业研报+宏观判断, 月度更新
B2B_DEMAND_CLIMATE = {
    "半导体":    {"score": 5.0, "note": "全球芯片库存高位, 下行周期"},
    "半导体设备":  {"score": 5.5, "note": "设备订单增速放缓"},
    "AI/科技":   {"score": 7.5, "note": "云计算Capex扩张+AI投资爆发"},
    "AI算力":    {"score": 7.5, "note": "GPU需求旺盛, 算力基建加速"},
    "云计算/算力": {"score": 7.5, "note": "AI驱动算力需求"},
    "通信/5G":   {"score": 6.0, "note": "5G建设高峰已过, 6G尚早"},
    "5G/PCB":   {"score": 6.0, "note": "PCB需求平稳"},
    "电子":      {"score": 5.5, "note": "消费电子需求疲软"},
    "新能源":    {"score": 6.5, "note": "锂价见底+政策支持+电网投资"},
    "光伏":      {"score": 5.0, "note": "产能过剩, 价格战持续"},
    "电池":      {"score": 6.5, "note": "钠电池量产+储能需求"},
    "军工":      {"score": 7.0, "note": "国防预算增长+地缘紧张"},
    "航空航天":   {"score": 7.0, "note": "商业航天+军机换代"},
    "金融":      {"score": 6.0, "note": "利率下行利好, 信贷需求弱"},
    "证券":      {"score": 5.5, "note": "市场成交量低迷"},
    "银行":      {"score": 5.5, "note": "净息差收窄"},
    "保险":      {"score": 6.0, "note": "保费增长稳定"},
    "券商":      {"score": 5.0, "note": "IPO收紧+交易量低"},
    "红利/价值":  {"score": 6.5, "note": "利率下行→红利吸引力上升"},
    "红利价值":   {"score": 6.5, "note": "高股息策略受益于降息"},
    "高股息":    {"score": 6.5, "note": "股息率vs存款利率差扩大"},
    "红利+低波":  {"score": 7.0, "note": "防御+股息双重优势"},
    "基建/地产":  {"score": 4.5, "note": "房地产投资持续下行"},
    "周期/资源":  {"score": 5.5, "note": "商品周期分化, 铜强煤弱"},
    "有色":      {"score": 5.5, "note": "铜铝需求稳, 稀土承压"},
    "黄金":      {"score": 8.0, "note": "央行购金+降息预期"},
    "公用事业":   {"score": 7.0, "note": "稳定现金流+防御属性"},
    "全市场":    {"score": 6.0, "note": "宏观经济弱复苏"},
    "宽基":      {"score": 6.0, "note": "沪深300盈利增速低个位数"},
    "中盘成长":   {"score": 6.0, "note": "成长股估值修复中"},
    "跨境":      {"score": 6.0, "note": "海外市场分化"},
    "中概互联网": {"score": 5.5, "note": "监管缓和但增长放缓"},
    "港股":      {"score": 5.5, "note": "流动性偏弱"},
    "硬科技":    {"score": 6.5, "note": "科创政策支持+国产替代"},
    "中药":      {"score": 6.5, "note": "政策扶持+老龄化需求"},
    "医药器械":   {"score": 6.0, "note": "集采压力+国产替代"},
    "可转债":    {"score": 6.0, "note": "股市震荡→转债性价比上升"},
    "信用债":    {"score": 7.5, "note": "城投化债+利率下行"},
    "利率债":    {"score": 8.0, "note": "降息周期+避险需求"},
    "货币基金":   {"score": 8.5, "note": "流动性管理工具, 需求刚性"},
    "货币":      {"score": 8.5, "note": "短期利率仍高"},
}

# === B2B行业需求风险 (l006 P0修复) ===
B2B_SECTOR_RISK = {
    "半导体":    {"score": 5.5, "note": "库存周期高位, 价格承压"},
    "半导体设备":  {"score": 5.0, "note": "设备订单可见度下降"},
    "AI/科技":   {"score": 6.0, "note": "GPU供应瓶颈+估值偏高"},
    "AI算力":    {"score": 5.5, "note": "过度依赖海外GPU供应"},
    "云计算/算力": {"score": 6.5, "note": "需求刚性, 风险较低"},
    "通信/5G":   {"score": 6.5, "note": "基建需求稳定"},
    "5G/PCB":   {"score": 6.0, "note": "技术迭代风险"},
    "电子":      {"score": 5.5, "note": "消费电子周期底部"},
    "新能源":    {"score": 6.0, "note": "产能过剩但政策托底"},
    "光伏":      {"score": 4.5, "note": "严重产能过剩, 价格战"},
    "电池":      {"score": 6.5, "note": "技术迭代+需求增长"},
    "军工":      {"score": 5.5, "note": "订单确定性高但利润率受限"},
    "航空航天":   {"score": 5.5, "note": "军民融合+技术壁垒"},
    "金融":      {"score": 6.5, "note": "系统性风险可控"},
    "证券":      {"score": 5.0, "note": "高度依赖市场情绪"},
    "银行":      {"score": 6.0, "note": "资产质量压力"},
    "保险":      {"score": 6.5, "note": "负债端稳定"},
    "券商":      {"score": 4.5, "note": "业绩与市场强相关"},
    "红利/价值":  {"score": 7.0, "note": "低波动+高股息, 风险较低"},
    "红利价值":   {"score": 7.0, "note": "防御属性强"},
    "高股息":    {"score": 7.0, "note": "现金流稳定"},
    "红利+低波":  {"score": 7.5, "note": "双重保护"},
    "基建/地产":  {"score": 4.0, "note": "房地产债务风险持续"},
    "周期/资源":  {"score": 5.5, "note": "商品价格波动大"},
    "有色":      {"score": 5.5, "note": "全球需求不确定性"},
    "黄金":      {"score": 8.0, "note": "避险资产, 风险极低"},
    "公用事业":   {"score": 8.0, "note": "垄断+刚需, 风险极低"},
    "全市场":    {"score": 6.5, "note": "系统性风险中等"},
    "宽基":      {"score": 6.5, "note": "分散化降低风险"},
    "中盘成长":   {"score": 5.5, "note": "成长股波动大"},
    "跨境":      {"score": 6.0, "note": "汇率+地缘风险"},
    "中概互联网": {"score": 5.0, "note": "监管+退市风险"},
    "港股":      {"score": 5.0, "note": "流动性+汇率双重风险"},
    "硬科技":    {"score": 5.5, "note": "技术路线+制裁风险"},
    "中药":      {"score": 6.5, "note": "政策支持对冲集采风险"},
    "医药器械":   {"score": 5.5, "note": "集采+国产替代双重压力"},
    "可转债":    {"score": 6.0, "note": "信用+股市双重风险"},
    "信用债":    {"score": 7.5, "note": "城投化债降低风险"},
    "利率债":    {"score": 8.5, "note": "无信用风险"},
    "货币基金":   {"score": 9.0, "note": "风险极低"},
    "货币":      {"score": 9.0, "note": "风险极低"},
}


def is_consumer_sector(sector):
    """判断行业是否属于消费2C类"""
    if not sector:
        return False
    sector_lower = sector.lower()
    consumer_lower = {s.lower() for s in CONSUMER_SECTORS}
    for cs in consumer_lower:
        if cs in sector_lower or sector_lower in cs:
            return True
    return False


def score_demand_climate(sector):
    """L10: 消费需求健康评分 (1-10)
    
    对非消费行业直接返回 7.0 (中性偏健康, 工业需求不受消费信心主导)
    对消费行业使用两模型加权:
      Model A: 社零增速(50%) + 消费信心(50%)
      Model B: 储蓄率(50%) + 失业率(50%)
      最终 = A*0.6 + B*0.4
    """
    if not is_consumer_sector(sector):
        b2b = B2B_DEMAND_CLIMATE.get(sector, {})
        if b2b:
            return {"score": b2b["score"], "data_covered": True, 
                    "note": b2b.get("note", "B2B行业需求"), "source": "b2b_inferred"}
        return {"score": 5.5, "data_covered": False, 
                "note": "未知B2B行业, 使用中性默认值"}

    dc = DEMAND_CLIMATE.get(sector, DEMAND_CLIMATE.get("default"))
    if not dc:
        return {"score": 7.0, "data_covered": False}

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

    return {
        "score": score,
        "model_a_power": model_a,
        "model_b_pressure": model_b,
        "retail_growth_pct": dc["retail_growth"],
        "confidence": dc["confidence"],
        "data_covered": True,
        "note": "",
    }


def score_sector_demand_risk(sector):
    """L11: 行业需求风险评分 (1-10, 越高越安全)
    
    悲观聚合: min(Model_A 渠道健康, Model_B 结构性风险)
    """
    sdr = SECTOR_DEMAND_RISK.get(sector)
    if not sdr:
        b2b = B2B_SECTOR_RISK.get(sector, {})
        if b2b:
            return {"score": b2b["score"], "data_covered": True,
                    "note": b2b.get("note", "B2B行业风险"), "source": "b2b_inferred"}
        return {"score": 6.0, "data_covered": False, 
                "note": "未知行业需求风险, 使用中性默认值"}

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

    # 悲观聚合: 取较低者
    score = min(model_a, model_b)
    return {
        "score": score,
        "model_a_channel": model_a,
        "model_b_structural": model_b,
        "data_covered": True,
        "note": "",
    }


def add_demand_layers(penetration_result, sector=None):
    """给穿透结果追加 L10+L11 层"""
    if sector is None:
        sector = penetration_result.get("sector", "default")
    
    l10 = score_demand_climate(sector)
    l11 = score_sector_demand_risk(sector)
    
    layers = penetration_result.get("layer_scores", {})
    layers["L10_Demand"] = l10["score"]
    layers["L11_SectorRisk"] = l11["score"]
    penetration_result["layer_scores"] = layers
    
    penetration_result["demand_detail"] = {
        "L10": l10,
        "L11": l11,
    }
    return penetration_result
