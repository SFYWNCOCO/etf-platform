"""ETF选股引擎 - 4模式推荐"""
from ..config_loader import load_etfs

MODE_CONFIG = {
    "defensive": {"label": "防御型", "score_direction": "high", "min_score": 50, "max_risk": 0.30,
        "sector_preference": ["红利/价值", "宽基", "消费", "金融", "医药"]},
    "balanced": {"label": "平衡型", "score_direction": "balanced", "min_score": 40, "max_risk": 0.50,
        "sector_preference": ["宽基", "红利/价值", "消费", "医药", "AI/科技"]},
    "aggressive": {"label": "进攻型", "score_direction": "low", "min_score": 20, "max_risk": 0.80,
        "sector_preference": ["半导体", "AI/科技", "新能源", "军工"]},
    "value": {"label": "价值型", "score_direction": "high", "min_score": 45, "max_risk": 0.40,
        "sector_preference": ["红利/价值", "红利+低波", "高股息", "央企改革", "宽基"]},
}

def select(mode="balanced", top_n=10):
    cfg = MODE_CONFIG.get(mode, MODE_CONFIG["balanced"])
    etfs = load_etfs()
    try:
        from ..decision.screener import recommend
        scored = recommend(top_n=min(100, len(etfs)))
        score_map = {r["code"]: r["composite_score"] for r in scored}
    except Exception:
        score_map = {}
    results = []
    for code, info in etfs.items():
        if not code.isdigit(): continue
        sector = info.get("sector", "")
        risk_level = info.get("risk_level", 0.5)
        if risk_level > cfg["max_risk"]: continue
        base_score = score_map.get(code, 5.0)
        if cfg["score_direction"] == "high" and base_score < cfg["min_score"]: continue
        sector_bonus = 0.5 if sector in cfg.get("sector_preference", []) else 0
        final_score = base_score + sector_bonus
        results.append({"code": code, "name": info.get("name", code), "sector": sector,
            "risk_level": risk_level, "final_score": round(final_score, 1)})
    results.sort(key=lambda x: -x["final_score"])
    return results[:top_n]

def report(results):
    if not results: return
    print(f"\n  ETF Selection (Top {len(results)})")
    for r in results:
        print(f"  {r['code']:<8} {r['name'][:18]:<20} {r['sector'][:10]:<12} {r['final_score']:<6.1f} {r['risk_level']:.2f}")
