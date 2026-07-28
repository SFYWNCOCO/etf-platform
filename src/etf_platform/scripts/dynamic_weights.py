import logging
logger = logging.getLogger(__name__)

"""dynamic_weights.py — 根据市场状态动态调整评级权重"""
import json
import os
import urllib.request

import pathlib; CACHE_DIR = str(pathlib.Path(__file__).resolve().parent.parent.parent.parent / "data_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

def em_api(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.warning("[dynamic_weights] fetch_market_index failed: %s", e)
        return None

def get_market_state():
    """判断市场状态（恐慌/正常/狂热）"""
    url = "https://push2.eastmoney.com/api/qt/stock/fflow/kline/get?secid=1.000001&fields1=f1,f2,f3,f4,f5&fields2=f51,f52,f53,f54,f55&klt=1&lmt=1"
    data = em_api(url)
    if not data or not data.get("data"):
        return "unknown", {}
    
    kline = data["data"]["klines"][0]
    parts = kline.split(",")
    main_flow = float(parts[1]) if len(parts) > 1 else 0  # 主力净流入
    
    # 市场广度（上涨比例）
    url2 = "https://push2.eastmoney.com/api/qt/clist/get?cb=&fid=f62&po=1&pz=5&pn=1&np=1&fltt=2&invt=2&fs=m:90+t:2&fields=f12,f14,f62,f184"
    data2 = em_api(url2)
    flow_top = 0
    if data2 and data2.get("data"):
        for item in data2["data"]["diff"]:
            flow_top += item.get("f62", 0)
    
    flow_b = main_flow / 1e8  # 亿
    
    if flow_b < -500:
        state = "panic"   # 恐慌
    elif flow_b < -200:
        state = "fear"    # 恐惧
    elif flow_b > 500:
        state = "euphoria"  # 狂热
    elif flow_b > 200:
        state = "greed"     # 贪婪
    else:
        state = "normal"    # 正常
    
    return state, {"main_flow": flow_b}

def adjust_weights(profile="balanced"):
    """根据市场状态调整权重"""
    state, signals = get_market_state()
    
    # 基础权重
    base = {
        "conservative": {"supply": 0.45, "capital": 0.10, "signal": 0.05, "demand": 0.40},
        "balanced":     {"supply": 0.35, "capital": 0.25, "signal": 0.10, "demand": 0.30},
        "aggressive":   {"supply": 0.20, "capital": 0.40, "signal": 0.20, "demand": 0.20},
        "激进":       {"supply": 0.15, "capital": 0.45, "signal": 0.25, "demand": 0.15},
    }
    
    _ALIASES = {"保守": "conservative", "均衡": "balanced", "进取": "aggressive", "激进": "激进", "进攻": "激进"}
    profile = _ALIASES.get(profile, profile)
    
    weights = dict(base.get(profile, base["balanced"]))
    
    # 市场状态调整
    adjustments = {
        "panic":    {"capital": +0.10, "supply": +0.05, "signal": -0.05, "demand": -0.10},
        "fear":     {"capital": +0.05, "signal": -0.03, "demand": -0.02},
        "euphoria": {"signal": +0.10, "capital": -0.05, "supply": -0.05},
        "greed":    {"signal": +0.05, "capital": -0.03},
    }
    
    adj = adjustments.get(state, {})
    for k, delta in adj.items():
        weights[k] = max(0.05, min(0.60, weights[k] + delta))
    
    # 归一化
    total = sum(weights.values())
    weights = {k: round(v/total, 2) for k, v in weights.items()}
    
    # 保存
    result = {"state": state, "signals": signals, "weights": weights}
    with open(os.path.join(CACHE_DIR, "dynamic_weights.json"), "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    return result

def load_dynamic_weights(profile="balanced"):
    _ALIASES = {"保守": "conservative", "均衡": "balanced", "进取": "aggressive", "激进": "激进"}
    profile = _ALIASES.get(profile, profile)
    path = os.path.join(CACHE_DIR, "dynamic_weights.json")
    try:
        with open(path) as f:
            data = json.load(f)
        return data["weights"]
    except Exception as e:
        logger.warning("[dynamic_weights] load_weights_yaml failed: %s", e)
        return adjust_weights(profile)["weights"]

if __name__ == "__main__":
    result = adjust_weights("balanced")
    print("市场状态: %s" % result["state"])
    print("调整后权重: %s" % result["weights"])
    print("信号: 主力净流入 %.0f亿" % result["signals"]["main_flow"])