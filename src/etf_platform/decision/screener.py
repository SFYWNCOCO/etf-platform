"""ETF screener: scan all buyable ETFs, rank by composite score, output top N."""
import time
import json
from typing import List, Dict, Optional

# Layer categories for auto-weighting
LAYER_CATEGORIES = {
    "供给侧": ["L3_Material", "L4_SupplyChain", "L5_Tech", "L6_Politics", "L7_Irreplaceable"],
    "资金面": ["L8_CapitalFlow"],
    "信号面": ["L9_Signals"],
    "需求面": ["L10_Demand", "L11_SectorRisk"],
}

# Risk profile category weights (auto-distributed among layers in each category)
CATEGORY_WEIGHTS = {
    "保守": {"供给侧": 0.45, "资金面": 0.10, "信号面": 0.05, "需求面": 0.40},
    "均衡": {"供给侧": 0.35, "资金面": 0.25, "信号面": 0.10, "需求面": 0.30},
    "进取": {"供给侧": 0.20, "资金面": 0.40, "信号面": 0.20, "需求面": 0.20},
}


def _compute_auto_weights(results: list, profile: str = "均衡") -> Dict[str, float]:
    """Compute layer weights automatically based on score variance.
    Higher variance = more discriminating power = higher weight.
    """
    import statistics

    # Collect scores for each layer across all ETFs
    layer_scores = {}
    for r in results:
        scores = r.get("layer_scores", {}) if isinstance(r, dict) else {}
        for layer, score in scores.items():
            if isinstance(score, (int, float)):
                if layer not in layer_scores:
                    layer_scores[layer] = []
                layer_scores[layer].append(score)

    # Get category weight for this profile
    cat_weights = CATEGORY_WEIGHTS.get(profile, CATEGORY_WEIGHTS["均衡"])

    # Build flat weight dict
    weights = {}
    for cat, layers in LAYER_CATEGORIES.items():
        cat_w = cat_weights.get(cat, 0)
        # Get variance for each layer in this category
        vars_in_cat = []
        for layer in layers:
            scores = layer_scores.get(layer, [])
            if len(scores) > 1 and max(scores) > min(scores):
                # Use coefficient of variation (std/mean) for scale-invariant variance
                mean = statistics.mean(scores)
                if mean > 0:
                    cv = statistics.stdev(scores) / mean
                    vars_in_cat.append((layer, cv))
                else:
                    vars_in_cat.append((layer, 0.1))
            else:
                vars_in_cat.append((layer, 0.1))

        # Distribute category weight proportionally to variance
        total_var = sum(v for _, v in vars_in_cat)
        if total_var > 0:
            for layer, v in vars_in_cat:
                weights[layer] = round(cat_w * (v / total_var), 3)
        else:
            # Equal distribution
            for layer in layers:
                weights[layer] = round(cat_w / len(layers), 3)

    # Normalize to sum = 1.0
    total = sum(weights.values())
    if total > 0:
        weights = {k: round(v / total, 3) for k, v in weights.items()}

    return weights


# Risk profile presets (kept for backward compat)
RISK_PROFILES = {
    "保守": {"L3_Material": 0.09, "L4_SupplyChain": 0.09, "L5_Tech": 0.03, "L6_Politics": 0.12, "L7_Irreplaceable": 0.12, "L8_CapitalFlow": 0.10, "L9_Signals": 0.05, "L10_Demand": 0.20, "L11_SectorRisk": 0.20},
    "均衡": {"L3_Material": 0.07, "L4_SupplyChain": 0.07, "L5_Tech": 0.04, "L6_Politics": 0.09, "L7_Irreplaceable": 0.08, "L8_CapitalFlow": 0.25, "L9_Signals": 0.10, "L10_Demand": 0.15, "L11_SectorRisk": 0.15},
    "进取": {"L3_Material": 0.04, "L4_SupplyChain": 0.04, "L5_Tech": 0.04, "L6_Politics": 0.04, "L7_Irreplaceable": 0.04, "L8_CapitalFlow": 0.40, "L9_Signals": 0.20, "L10_Demand": 0.10, "L11_SectorRisk": 0.10},
}


def _flatten_weights(profile: str = "均衡") -> Dict[str, float]:
    """Get flat {layer_name: weight} dict for a risk profile."""
    return RISK_PROFILES.get(profile, RISK_PROFILES["均衡"])


def _compute_composite(scores: dict, weights: dict) -> float:
    """Compute weighted composite score."""
    total = 0.0
    weight_sum = 0.0
    for layer, weight in weights.items():
        score = scores.get(layer)
        if score is not None and isinstance(score, (int, float)):
            total += score * weight
            weight_sum += weight
    return round(total / max(weight_sum, 0.01), 2) if weight_sum > 0 else 0


def _generate_reason(result: dict, profile: str) -> str:
    """Generate one-line reason why this ETF ranks where it does."""
    scores = result.get("layer_scores", {})
    layers = result.get("layers", {})
    name = result.get("name", "")
    code = result.get("etf_code", result.get("code", ""))
    sector = result.get("sector", "")
    if not name:
        name = f"ETF-{code}"
    if not sector:
        sector = "未知行业"

    # Strongest and weakest points
    scored_layers = [(k, v) for k, v in scores.items() if isinstance(v, (int, float))]
    scored_layers.sort(key=lambda x: x[1], reverse=True)
    top1, top1_score = scored_layers[0] if scored_layers else ("?", 0)
    worst1, worst1_score = scored_layers[-1] if scored_layers else ("?", 10)

    # Layer name mapping
    layer_names = {
        "L1_ETF": "基础面", "L2_Holdings": "持仓结构",
        "L3_Material": "材料安全", "L4_SupplyChain": "产能物流",
        "L5_Tech": "技术壁垒", "L6_Politics": "政治风险",
        "L7_Irreplaceable": "不可替代性", "L8_CapitalFlow": "资金面",
        "L9_Signals": "催化剂", "L10_Demand": "消费需求",
        "L11_SectorRisk": "行业风险",
    }
    top_name = layer_names.get(top1, top1)
    worst_name = layer_names.get(worst1, worst1)

    # Check if L8 is real-time
    l8_source = ""
    for k, v in layers.items():
        if "L8" in k:
            l8_source = v.get("data_source", "")
            break
    live_tag = "📡" if "实测" in str(l8_source) else "⚙️"

    # Check L10/L11
    l10 = scores.get("L10_Demand", 0)
    l11 = scores.get("L11_SectorRisk", 0)

    reason_parts = []
    reason_parts.append(f"行业:{sector}")
    reason_parts.append(f"优势:{top_name}({top1_score})")

    # Dynamic insight
    if l10 >= 7:
        reason_parts.append(f"需求旺盛(L10={l10})")
    elif l10 <= 3:
        reason_parts.append(f"需求疲软(L10={l10})")

    if worst1_score <= 3:
        reason_parts.append(f"⚠️短板:{worst_name}({worst1_score})")

    # Check if there are news catalysts
    for k, v in layers.items():
        if "L9" in k:
            dyn = v.get("dynamic_catalysts", [])
            if dyn:
                top_news = dyn[0].get("title", "")
                reason_parts.append(f"📰新闻:{top_news[:30]}")
            break

    return " | ".join(reason_parts)


def screen(limit: int = 523, profile: str = "均衡", top_n: int = 10) -> List[dict]:
    """Scan all buyable ETFs, score and rank them.

    Args:
        limit: Max ETFs to scan (default: all)
        profile: Risk profile - "保守" / "均衡" / "进取"
        top_n: Number of top results to return

    Returns:
        List of ranked result dicts with composite_score and reason
    """
    from ..pipeline import batch_full
    from ..config_loader import load_etfs

    weights = _flatten_weights(profile)
    etfs = load_etfs()

    print(f"\n  🔍 全市场扫描: {profile}型投资者")
    print(f"  {'='*50}")
    print(f"  正在分析 {min(limit, len(etfs))}/{len(etfs)} 只ETF...")

    # Run batch
    t0 = time.time()
    results = batch_full(limit=limit, live=True)
    elapsed = time.time() - t0

    print(f"  完成 ({elapsed:.0f}s), 正在评分排序...")

    # Score and rank
    ranked = []
    for r in results:
        code = r.get("etf_code", "")
        info = etfs.get(code, {})
        r["info"] = info
        composite = _compute_composite(r.get("layer_scores", {}), weights)
        reason = _generate_reason(r, profile)
        ranked.append({
            "rank": 0,
            "code": code,
            "name": info.get("name", ""),
            "sector": info.get("sector", ""),
            "risk_level": info.get("risk_level", 0),
            "composite_score": composite,
            "layer_scores": r.get("layer_scores", {}),
            "reason": reason,
        })

    # Sort by composite score descending
    ranked.sort(key=lambda x: x["composite_score"], reverse=True)

    # Assign ranks
    for i, item in enumerate(ranked):
        item["rank"] = i + 1

    return ranked[:top_n]


def recommend(top_n: int = 5, profile: str = "均衡") -> List[dict]:
    """Quick recommendation: scan + rank + return top N."""
    return screen(limit=50, profile=profile, top_n=top_n)
