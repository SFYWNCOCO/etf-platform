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

CATEGORY_WEIGHTS = {
    "保守": {"供给侧": 0.45, "资金面": 0.10, "信号面": 0.05, "需求面": 0.40},
    "均衡": {"供给侧": 0.35, "资金面": 0.25, "信号面": 0.10, "需求面": 0.30},
    "进取": {"供给侧": 0.20, "资金面": 0.40, "信号面": 0.20, "需求面": 0.20},
}

RISK_PROFILES = {
    "保守": {"L3_Material": 0.09, "L4_SupplyChain": 0.09, "L5_Tech": 0.03, "L6_Politics": 0.12, "L7_Irreplaceable": 0.12, "L8_CapitalFlow": 0.10, "L9_Signals": 0.05, "L10_Demand": 0.20, "L11_SectorRisk": 0.20},
    "均衡": {"L3_Material": 0.07, "L4_SupplyChain": 0.07, "L5_Tech": 0.04, "L6_Politics": 0.09, "L7_Irreplaceable": 0.08, "L8_CapitalFlow": 0.25, "L9_Signals": 0.10, "L10_Demand": 0.15, "L11_SectorRisk": 0.15},
    "进取": {"L3_Material": 0.04, "L4_SupplyChain": 0.04, "L5_Tech": 0.04, "L6_Politics": 0.04, "L7_Irreplaceable": 0.04, "L8_CapitalFlow": 0.40, "L9_Signals": 0.20, "L10_Demand": 0.10, "L11_SectorRisk": 0.10},
}


def _compute_auto_weights(results: list, profile: str = "均衡") -> Dict[str, float]:
    import statistics
    layer_scores = {}
    for r in results:
        scores = r.get("layer_scores", {}) if isinstance(r, dict) else {}
        for layer, score in scores.items():
            if isinstance(score, (int, float)):
                layer_scores.setdefault(layer, []).append(score)
    cat_weights = CATEGORY_WEIGHTS.get(profile, CATEGORY_WEIGHTS["均衡"])
    weights = {}
    for cat, layers in LAYER_CATEGORIES.items():
        cat_w = cat_weights.get(cat, 0)
        vars_in_cat = []
        for layer in layers:
            scores = layer_scores.get(layer, [])
            if len(scores) > 1 and max(scores) > min(scores):
                mean = statistics.mean(scores)
                cv = statistics.stdev(scores) / mean if mean > 0 else 0.1
                vars_in_cat.append((layer, cv))
            else:
                vars_in_cat.append((layer, 0.1))
        total_var = sum(v for _, v in vars_in_cat)
        if total_var > 0:
            for layer, v in vars_in_cat:
                weights[layer] = round(cat_w * (v / total_var), 3)
        else:
            for layer in layers:
                weights[layer] = round(cat_w / len(layers), 3)
    total = sum(weights.values())
    if total > 0:
        weights = {k: round(v / total, 3) for k, v in weights.items()}
    return weights


def _flatten_weights(profile: str = "均衡") -> Dict[str, float]:
    return RISK_PROFILES.get(profile, RISK_PROFILES["均衡"])


def _compute_composite(scores: dict, weights: dict) -> float:
    total = 0.0
    ws = 0.0
    for layer, weight in weights.items():
        score = scores.get(layer)
        if score is not None and isinstance(score, (int, float)):
            total += score * weight
            ws += weight
    return round(total / max(ws, 0.01), 2) if ws > 0 else 0


TREND_ICONS = {"oversold": "🟢超卖", "weak": "🟡回调", "neutral": "⚪中性", "strong": "🟡强势", "overbought": "🔴超买", "plunging": "🔴急跌", "surging": "🟢急涨"}
LN = {"L1_ETF":"基础","L2_Holdings":"持仓","L3_Material":"材料","L4_SupplyChain":"物流","L5_Tech":"技术","L6_Politics":"政治","L7_Irreplaceable":"替代","L8_CapitalFlow":"资金","L9_Signals":"信号","L10_Demand":"需求","L11_SectorRisk":"行业风险"}


def _generate_reason(result: dict, trend: dict = None) -> str:
    scores = result.get("layer_scores", {})
    layers = result.get("layers", {})
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
    scored = [(k, v) for k, v in scores.items() if isinstance(v, (int, float))]
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
        parts.append(f"需求疲软({l10})")
    if l11 >= 7:
        parts.append(f"行业健康({l11})")
    elif l11 <= 3:
        parts.append(f"行业危险({l11})")
    return " | ".join(parts)


def screen(limit: int = 523, profile: str = "均衡", top_n: int = 10) -> List[dict]:
    from ..pipeline import batch_full
    from ..config_loader import load_etfs
    from ..enhance.l8_realtime import enhance_l8
    from ..enhance.l9_news import enhance_l9
    from ..data.kline import get_trend

    etfs = load_etfs()
    print(f"\n  🔍 全市场扫描: {profile}型投资者")
    print(f"  {'='*50}")
    print(f"  正在分析 {min(limit, len(etfs))}/{len(etfs)} 只ETF (离线模式)...")
    print(f"  Top候选将获取实时+趋势增强")

    # Cache check
    cache_dir = Path(__file__).resolve().parent.parent.parent.parent / "data" / "screener_cache"
    cache_file = cache_dir / f"scan_{profile}.json"
    results = None
    if cache_file.exists():
        age = time.time() - cache_file.stat().st_mtime
        if age < 7200:
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    results = json.load(f)
                print(f"  使用缓存 ({age:.0f}s前生成, {len(results)}只)")
            except:
                results = None

    if results is None:
        t0 = time.time()
        results = batch_full(limit=limit, live=False)
        elapsed = time.time() - t0
        print(f"  完成 ({elapsed:.0f}s), 计算自动权重...")
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            clean = [{k:v for k,v in r.items() if isinstance(v,(dict,list,str,int,float,bool)) or v is None} for r in results]
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(clean, f, ensure_ascii=False, default=str)
        except:
            pass
    else:
        elapsed = 0

    weights = _compute_auto_weights(results, profile)
    print(f"  自动权重: {weights}")

    ranked = []
    for r in results:
        code = r.get("etf_code", "")
        ls = r.get("layer_scores", {})
        l1 = ls.get("L1_ETF", 5)
        rl = max(0.1, min(0.9, (10 - l1) / 10)) if isinstance(l1, (int, float)) else 0.5
        composite = _compute_composite(ls, weights)
        ranked.append({"rank":0,"code":code,"name":r.get("name",""),"sector":r.get("sector",""),"risk_level":rl,"composite_score":composite,"layer_scores":ls,"reason":"","trend":{}})

    ranked.sort(key=lambda x: -x["composite_score"])
    for i, item in enumerate(ranked):
        item["rank"] = i + 1

    top_results = ranked[:top_n]
    print(f"  获取 Top {top_n} 实时数据+趋势分析...")
    for item in top_results:
        code = item["code"]
        try:
            trend = get_trend(code)
            if trend:
                item["trend"] = {"change_5d":trend.change_5d,"change_20d":trend.change_20d,"change_60d":trend.change_60d,"position_pct":trend.position_pct,"max_drawdown":trend.max_drawdown,"signal":trend.trend_signal,"price":trend.price,"volatility":trend.volatility_20d}
        except:
            pass
        for raw in results:
            if raw.get("code") == code or raw.get("etf_code") == code:
                try:
                    raw = enhance_l8(raw)
                    raw = enhance_l9(raw)
                    item["layer_scores"] = raw.get("layer_scores", {})
                    item["composite_score"] = _compute_composite(item["layer_scores"], weights)
                except:
                    pass
                break
        item["reason"] = _generate_reason(item, item.get("trend"))

    return top_results


def recommend(top_n: int = 5, profile: str = "均衡") -> List[dict]:
    return screen(limit=50, profile=profile, top_n=top_n)