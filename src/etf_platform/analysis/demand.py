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
        return {"score": 7.0, "data_covered": False, "note": "B2B行业, 不受消费需求直接影响"}

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
        return {"score": 8.0, "data_covered": False, "note": "行业无需求侧风险数据"}

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
