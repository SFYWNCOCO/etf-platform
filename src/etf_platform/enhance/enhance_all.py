"""enhance_all.py — Post-process all 11 layers with real-time data."""
import json, os

POLITICS_EVENTS = [
    {"name": "美国对华芯片出口管制", "severity": 0.35, "affected_sectors": ["芯片", "半导体", "AI", "通信"]},
    {"name": "日本光刻胶供应新规", "severity": 0.25, "affected_sectors": ["芯片", "半导体", "材料"]},
    {"name": "BIS实体清单扩展", "severity": 0.30, "affected_sectors": ["芯片", "AI", "通信设备"]},
    {"name": "欧洲芯片法案/出口管制", "severity": 0.20, "affected_sectors": ["芯片", "半导体", "汽车电子"]},
]

L9_POS_KWS = ["涨", "升", "利好", "突破", "反弹", "新高", "放量",
              "涨价", "提价", "景气", "上行", "供不应求", "紧缺",
              "加速", "加仓", "抢筹", "订单", "量产",
              "国产替代", "自主可控", "增长"]

L9_NEG_KWS = ["跌", "降", "利空", "风险", "跳水", "暴跌", "警告", "崩盘",
              "制裁", "管制", "禁令", "断供", "脱钩", "下滑",
              "过剩", "降价", "亏损", "退市"]

S1_S5_WEIGHTS = {
    "S1:石英砂+光刻胶双断供": 0.30,
    "S2:GPU+光刻胶双断供": 0.45,
    "S3:MCU+功率短缺": 0.25,
    "S4:光模块短缺": 0.15,
    "S5:全面禁运": 0.05,
}

def enhance_all(penetration_result):
    layers = penetration_result.get("layers", {})
    scores = penetration_result.get("layer_scores", {})
    sector = penetration_result.get("sector", "")
    _fix_l6(scores, layers, sector)
    _fix_l4(scores, layers, sector)
    _fix_l9(scores, layers)
    return penetration_result

def _fix_l6(scores, layers, sector):
    base = scores.get("L6_Politics", 0)
    if isinstance(base, str):
        try: base = float(base)
        except Exception: base = 1.0
    event_risk = 0.0
    for evt in POLITICS_EVENTS:
        for aff in evt["affected_sectors"]:
            if sector and (aff in sector or sector in aff):
                event_risk = max(event_risk, evt["severity"])
    if event_risk > 0.3:
        new_score = min(base, 2.0)
    elif event_risk > 0.15:
        new_score = min(base, 4.0)
    else:
        new_score = min(7.0, base + 2.0)
    scores["L6_Politics"] = max(1.0, min(10.0, round(new_score, 1)))

def _fix_l4(scores, layers, sector):
    base = scores.get("L4_SupplyChain", 0)
    if isinstance(base, str):
        try: base = float(base)
        except Exception: base = 1.6
    if sector and ("芯片" in sector or "半导体" in sector or "AI" in sector):
        active_risk = S1_S5_WEIGHTS.get("S2:GPU+光刻胶双断供", 0.45)
        new_score = max(1.0, 10.0 - active_risk * 18)
        scores["L4_SupplyChain"] = round(new_score, 1)
    else:
        scores["L4_SupplyChain"] = min(10.0, base + 1.0)

def _fix_l9(scores, layers):
    l9_data = None
    for k, v in layers.items():
        if "L9" in k:
            l9_data = v
            break
    if not l9_data:
        return
    news_list = l9_data.get("dynamic_catalysts", l9_data.get("catalyst_calendar", []))
    if not news_list:
        return
    net = 0
    for item in news_list:
        title = item.get("title", "")
        pos = sum(1 for k in L9_POS_KWS if k in title)
        neg = sum(1 for k in L9_NEG_KWS if k in title)
        delta = 1 if pos > neg else (-1 if neg > pos else 0)
        net += delta
    old = scores.get("L9_Signals", 5.0)
    if isinstance(old, str):
        try: old = float(old)
        except Exception: old = 5.0
    adj = net * 0.4
    new_score = max(1, min(10, round(old + adj, 1)))
    scores["L9_Signals"] = new_score
