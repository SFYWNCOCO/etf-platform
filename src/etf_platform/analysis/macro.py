"""macro.py — ETF生态健康 + 宏观环境评分

来源: etf_system/eco_monitor.py (6大模块) + money_bond_kb.py
"""
import datetime

# ── ETF流动性档案 (硬编码参考数据) ──
ETF_LIQUIDITY = {
    "510300": {"ap_30d":8,"ap_180d":12,"spread":0.0003,"depth":5000,"vol_wan":35000},
    "159995": {"ap_30d":3,"ap_180d":5,"spread":0.0012,"depth":1500,"vol_wan":12000},
    "159819": {"ap_30d":2,"ap_180d":4,"spread":0.0015,"depth":800,"vol_wan":8000},
    "512890": {"ap_30d":5,"ap_180d":7,"spread":0.0005,"depth":3000,"vol_wan":20000},
    "518880": {"ap_30d":6,"ap_180d":8,"spread":0.0003,"depth":6000,"vol_wan":22000},
    "511010": {"ap_30d":8,"ap_180d":10,"spread":0.0001,"depth":10000,"vol_wan":40000},
    "513100": {"ap_30d":4,"ap_180d":7,"spread":0.0008,"depth":2000,"vol_wan":15000},
    "516510": {"ap_30d":2,"ap_180d":4,"spread":0.0013,"depth":1000,"vol_wan":5000},
}

# ── 持有人结构 ──
HOLDER_PROFILE = {
    "510300": {"top10":0.35,"inst":0.65,"redeem_days":2},
    "159995": {"top10":0.62,"inst":0.50,"redeem_days":5},
    "159819": {"top10":0.68,"inst":0.45,"redeem_days":5},
    "512890": {"top10":0.55,"inst":0.52,"redeem_days":3},
    "516510": {"top10":0.72,"inst":0.38,"redeem_days":5},
}


def _clamp(v, best, worst):
    """Map value to 0-100 score (best=100, worst=0)."""
    if best == worst: return 50
    return max(0, min(100, round((v - worst) / (best - worst) * 100)))


def health_score(code):
    """Compute ETF ecosystem health score (0-100, higher=healthier).
    
    6 modules from eco_monitor (simplified):
    1. AP/Arbitrage (25%)
    2. Market Maker (20%)
    3. Holder/Run (25%)
    4. Premium/Info (10%)
    5. Derivatives (15%)
    6. Index Risk (5%)
    """
    liq = ETF_LIQUIDITY.get(code, {})
    hol = HOLDER_PROFILE.get(code, {})
    if not liq:
        return None
    
    scores = []
    
    # 1. AP活跃度 (25%)
    ap_30 = liq.get("ap_30d", 3)
    ap_180 = liq.get("ap_180d", 5)
    ap_ratio = ap_30 / max(ap_180, 1)
    ap_score = _clamp(ap_ratio, 1.0, 0.3)
    s1 = ap_score * 0.25
    
    # 2. 做市商 (20%) - 价差
    spread = liq.get("spread", 0.001)
    spread_score = _clamp(spread, 0.0002, 0.002)
    depth = liq.get("depth", 2000)
    depth_score = _clamp(depth, 10000, 500)
    s2 = (spread_score * 0.5 + depth_score * 0.5) * 0.20
    
    # 3. 持有人/挤兑 (25%)
    top10 = hol.get("top10", 0.50)
    holder_score = _clamp(top10, 0.30, 0.85)
    vol = liq.get("vol_wan", 10000)
    vol_score = _clamp(vol, 50000, 1000)
    s3 = (holder_score * 0.5 + vol_score * 0.5) * 0.25
    
    # 4-6. 简化: 根据ETF类型估算
    etf_type = "行业" if code.startswith("159") else "宽基"
    if etf_type == "宽基":
        s4 = 80 * 0.10  # 宽基折溢价风险低
        s5 = 80 * 0.15
        s6 = 85 * 0.05
    else:
        s4 = 60 * 0.10  # 行业ETF折溢价风险高
        s5 = 50 * 0.15
        s6 = 65 * 0.05
    
    total = round(s1 + s2 + s3 + s4 + s5 + s6)
    
    if total < 40: level = "🔴 红色"
    elif total < 60: level = "🟡 黄色"
    else: level = "🟢 绿色"
    
    return {
        "score": total,
        "level": level,
        "modules": {
            "ap_arbitrage": round(s1/0.25, 1),
            "market_maker": round(s2/0.20, 1),
            "holder_risk": round(s3/0.25, 1),
            "premium_info": round(s4/0.10, 1),
            "derivatives": round(s5/0.15, 1),
            "index_risk": round(s6/0.05, 1),
        },
    }


def get_macro_climate():
    """简化的宏观环境评分 (from money_bond_kb.py concepts).
    
    基于市场公开数据估算当前所处周期位置。
    """
    # 使用固定基准值（后续可从数据源动态获取）
    return {
        "phase": "衰退末期→复苏早期",
        "pmi": "49~50 (震荡)",
        "lpr_direction": "下行",
        "bond_yield": "~1.8%",
        "recommended": {
            "defensive": ["债券ETF", "红利低波", "黄金ETF"],
            "offensive": ["沪深300", "科创50", "芯片ETF"],
        },
        "avoid": ["周期/资源"],
    }


def full_eco_report(code):
    """Combine health + macro for one ETF."""
    health = health_score(code)
    macro = get_macro_climate()
    return {
        "code": code,
        "health": health,
        "macro": macro,
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


if __name__ == "__main__":
    for code in ["512890","159995","159819","518880","511010","516510"]:
        h = health_score(code)
        if h:
            print("%s: %d分 %s | AP=%.1f MM=%.1f Holder=%.1f" % (
                code, h["score"], h["level"],
                h["modules"]["ap_arbitrage"],
                h["modules"]["market_maker"],
                h["modules"]["holder_risk"]))
    print("\n宏观: %s" % get_macro_climate()["phase"])
    print("推荐: %s / %s" % (
        get_macro_climate()["recommended"]["defensive"],
        get_macro_climate()["recommended"]["offensive"]))