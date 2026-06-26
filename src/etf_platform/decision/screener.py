"""ETF screener: scan all buyable ETFs, rank by composite score, output top N."""
import time
import json
from pathlib import Path
from typing import List, Dict, Optional

# Layer categories for auto-weighting
LAYER_CATEGORIES = {
    "供给侧": ["L3_Material", "L4_SupplyChain", "L5_Tech", "L6_Politics", "L7_Irreplaceable"],
    "资金面": ["L8_CapitalFlow"],
    "信号面": ["L9_Signals"],
    "需求面": ["L10_Demand", "L11_SectorRisk"],
}

# Exclude L1 (metadata) and L2 (always missing) from scoring
EXCLUDED_LAYERS = {"L1_ETF", "L2_Holdings"}

CATEGORY_WEIGHTS = {
    "保守": {"供给侧": 0.45, "资金面": 0.10, "信号面": 0.05, "需求面": 0.40},
    "均衡": {"供给侧": 0.35, "资金面": 0.25, "信号面": 0.10, "需求面": 0.30},
    "进取": {"供给侧": 0.20, "资金面": 0.40, "信号面": 0.20, "需求面": 0.20},
}

TREND_ICONS = {"oversold":"🟢超卖","weak":"🟡回调","neutral":"⚪中性","strong":"🟡强势","overbought":"🔴超买","plunging":"🔴急跌","surging":"🟢急涨"}
LN = {"L3_Material":"材料","L4_SupplyChain":"物流","L5_Tech":"技术","L6_Politics":"政治","L7_Irreplaceable":"替代","L8_CapitalFlow":"资金","L9_Signals":"信号","L10_Demand":"需求","L11_SectorRisk":"行业风险"}


def _compute_auto_weights(results: list, profile: str = "均衡") -> Dict[str, float]:
    """Compute weights: higher variance = higher weight. Exclude dead layers."""
    import statistics
    layer_scores = {}
    for r in results:
        scores = r.get("layer_scores", {}) if isinstance(r, dict) else {}
        for layer, score in scores.items():
            if isinstance(score, (int, float)) and layer not in EXCLUDED_LAYERS:
                layer_scores.setdefault(layer, []).append(score)
    
    # Calculate coefficients of variation (CV)
    layer_cv = {}
    for layer, scores in layer_scores.items():
        if len(scores) > 1 and max(scores) > min(scores):
            mean = statistics.mean(scores)
            if mean > 0:
                cv = statistics.stdev(scores) / mean
            else:
                cv = 0.1
        else:
            cv = 0.05  # Minimum for dead layers
        layer_cv[layer] = cv
    
    # Boost CV: layers with CV > 15% get amplified, layers with CV < 8% get suppressed
    adjusted_cv = {}
    for layer, cv in layer_cv.items():
        if cv > 0.20:
            adjusted_cv[layer] = cv * 1.5  # Boost high-differentiation layers
        elif cv < 0.08:
            adjusted_cv[layer] = cv * 0.3  # Suppress low-differentiation layers
        else:
            adjusted_cv[layer] = cv
    
    # Distribute category weights proportionally to adjusted CV
    cat_weights = CATEGORY_WEIGHTS.get(profile, CATEGORY_WEIGHTS["均衡"])
    weights = {}
    for cat, layers in LAYER_CATEGORIES.items():
        cat_w = cat_weights.get(cat, 0)
        eligible = [l for l in layers if l in adjusted_cv]
        if not eligible:
            continue
        total_adj = sum(adjusted_cv[l] for l in eligible)
        if total_adj > 0:
            for layer in eligible:
                weights[layer] = round(cat_w * (adjusted_cv[layer] / total_adj), 4)
        else:
            for layer in eligible:
                weights[layer] = round(cat_w / len(eligible), 4)
    
    # Normalize to sum = 1.0
    total = sum(weights.values())
    if total > 0:
        weights = {k: round(v / total, 4) for k, v in weights.items()}
    return weights



def _normalize_batch(results: list) -> None:
    all_layers = set()
    for r in results:
        all_layers.update(r["layer_scores"].keys())
    for layer in all_layers:
        vals = [float(r["layer_scores"].get(layer, 5.0)) for r in results]
        mn, mx = min(vals), max(vals)
        if mx - mn < 0.01:
            for r in results:
                r["layer_scores"][layer] = 5.0
        else:
            for r in results:
                raw = float(r["layer_scores"].get(layer, 5.0))
                r["layer_scores"][layer] = round(max(0, min(10, (raw - mn) / (mx - mn) * 10)), 2)
def _compute_composite(scores: dict, weights: dict) -> float:
    """Weighted composite, excluding dead layers."""
    total = 0.0
    ws = 0.0
    for layer, weight in weights.items():
        score = scores.get(layer)
        if score is not None and isinstance(score, (int, float)):
            total += score * weight
            ws += weight
    return round(total / max(ws, 0.01), 2) if ws > 0 else 0


def _generate_reason(result: dict, trend: dict = None) -> str:
    scores = result.get("layer_scores", {})
    name = result.get("name", "")
    sector = result.get("sector", "") or "未知行业"
    parts = [f"行业:{sector}"]
    if trend:
        sig = trend.get("signal", "")
        tag = TREND_ICONS.get(sig, "⚪")
        chg20 = trend.get("change_20d", 0)
        pos = trend.get("position_pct", 50)
        parts.append(f"趋势:{tag} {chg20:+.1f}%({pos:.0f}%分位)")
        dd = trend.get("max_drawdown", 0)
        if dd < -10:
            parts.append(f"回撤{dd:.0f}%")
    scored = [(k, v) for k, v in scores.items() if isinstance(v, (int, float)) and k not in EXCLUDED_LAYERS]
    scored.sort(key=lambda x: -x[1])
    strengths = [f"{LN.get(k,k)}({v})" for k, v in scored[:2] if v >= 6]
    if strengths:
        parts.append("优势:" + ",".join(strengths))
    weaknesses = [f"{LN.get(k,k)}({v})" for k, v in scored[-2:] if v <= 4]
    if weaknesses:
        parts.append("短板:" + ",".join(weaknesses))
    l10 = scores.get("L10_Demand", 5)
    l11 = scores.get("L11_SectorRisk", 5)
    if l10 >= 7:
        parts.append(f"需求旺盛({l10})")
    elif l10 <= 3:
        parts.append(f"需求偏弱({l10})")
    if l11 >= 7:
        parts.append(f"行业健康({l11})")
    elif l11 <= 3:
        parts.append(f"行业危险({l11})")
    # News count
    news_cnt = result.get("_news_count", 0)
    if news_cnt > 0:
        parts.append(f"📰{news_cnt}条新闻")
    return " | ".join(parts)


def screen(limit: int = 523, profile: str = "均衡", top_n: int = 10) -> List[dict]:
    from ..pipeline import batch_full
    from ..config_loader import load_etfs
    from ..enhance.l8_realtime import enhance_l8
    from ..enhance.l9_news import enhance_l9
    from ..data.kline import get_trend
    from ..data.manager import get_news

    etfs = load_etfs()
    print(f"\n  🔍 全市场扫描: {profile}型投资者")
    print(f"  {'='*50}")
    print(f"  分析 {min(limit, len(etfs))}/{len(etfs)} 只ETF")

    # Cache
    cache_dir = Path(__file__).resolve().parent.parent.parent.parent / "data" / "screener_cache"
    cache_file = cache_dir / f"scan_{profile}.json"
    results = None
    if cache_file.exists():
        age = time.time() - cache_file.stat().st_mtime
        if age < 7200:
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    results = json.load(f)
                print(f"  缓存 ({age:.0f}s前, {len(results)}只)")
            except:
                results = None

    if results is None:
        t0 = time.time()
        results = batch_full(limit=limit, live=False)
        elapsed = time.time() - t0
        print(f"  穿透完成 ({elapsed:.0f}s)")
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            clean = [{k:v for k,v in r.items() if isinstance(v,(dict,list,str,int,float,bool)) or v is None} for r in results]
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(clean, f, ensure_ascii=False, default=str)
        except:
            pass

    weights = _compute_auto_weights(results, profile)
    print(f"  自动权重: {weights}")

    # Normalize scores across batch
    _normalize_batch(results)
    # Score and rank
    ranked = []
    for r in results:
        code = r.get("etf_code", "")
        ls = r.get("layer_scores", {})
        l1 = ls.get("L1_ETF", 5)
        rl = max(0.1, min(0.9, (10 - l1) / 10)) if isinstance(l1, (int, float)) else 0.5
        composite = _compute_composite(ls, weights)
        ranked.append({"rank":0,"code":code,"name":r.get("name",""),"sector":r.get("sector",""),"risk_level":rl,"composite_score":composite,"layer_scores":ls,"reason":"","trend":{}, "_news_count": 0})

    ranked.sort(key=lambda x: -x["composite_score"])
    for i, item in enumerate(ranked):
        item["rank"] = i + 1

    top_results = ranked[:max(top_n, 20)]  # Get 20, then enhance top 10
    print(f"  获取实时数据+趋势+新闻动态评分...")
    
    for item in top_results:
        code = item["code"]
        # Trend
        try:
            trend = get_trend(code)
            if trend:
                item["trend"] = {"change_5d":trend.change_5d,"change_20d":trend.change_20d,"change_60d":trend.change_60d,"position_pct":trend.position_pct,"max_drawdown":trend.max_drawdown,"signal":trend.trend_signal,"price":trend.price,"volatility":trend.volatility_20d}
        except:
            pass
        # Enhance + news for top 10 only
        if item["rank"] <= top_n:
            for raw in results:
                if raw.get("code") == code or raw.get("etf_code") == code:
                    try:
                        # Get news for this ETF's sector
                        sector = item.get("sector", "")
                        if sector and sector not in ("其他", "综合", "未知行业"):
                            news_items = get_news(sector, limit=3)
                            item["_news_count"] = len(news_items)
                            # Adjust L9 score based on news sentiment
                            if news_items:
                                ls = item["layer_scores"]
                                neg = sum(1 for n in news_items if any(k in n.title for k in ["跌","降","利空","风险","跳水","暴跌"]))
                                pos = sum(1 for n in news_items if any(k in n.title for k in ["涨","升","利好","突破","反弹"]))
                                old_l9 = ls.get("L9_Signals", 5.0)
                                adj = (pos - neg) * 0.5
                                ls["L9_Signals"] = max(1, min(10, old_l9 + adj))
                                # Recalculate composite
                                item["composite_score"] = _compute_composite(ls, weights)
                        # Live data
                        raw = enhance_l8(raw)
                        item["layer_scores"].update(raw.get("layer_scores", {}))
                    except:
                        pass
                    break
        item["reason"] = _generate_reason(item, item.get("trend"))

    return top_results[:top_n]


def recommend(top_n: int = 5, profile: str = "均衡") -> List[dict]:
    return screen(limit=50, profile=profile, top_n=top_n)