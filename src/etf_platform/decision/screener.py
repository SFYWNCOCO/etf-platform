"""ETF screener: scan all buyable ETFs, rank by composite score, output top N."""
import time
import json
from typing import List, Dict, Optional

# Default weights for composite scoring
# Higher weight = more important
DEFAULT_WEIGHTS = {
    "供给侧安全": {
        "L3_Material": 0.10,
        "L4_SupplyChain": 0.10,
        "L5_Tech": 0.05,
        "L6_Politics": 0.10,
        "L7_Irreplaceable": 0.05,
    },
    "资金面": {
        "L8_CapitalFlow": 0.20,
    },
    "前瞻信号": {
        "L9_Signals": 0.10,
    },
    "需求面": {
        "L10_Demand": 0.15,
        "L11_SectorRisk": 0.15,
    },
}

# Risk profile presets
RISK_PROFILES = {
    "保守": {k: v * 0.6 for k, v in DEFAULT_WEIGHTS["供给侧安全"].items()} | {
        "L8_CapitalFlow": 0.10,
        "L9_Signals": 0.05,
        "L10_Demand": 0.25,
        "L11_SectorRisk": 0.25,
    },
    "均衡": {k: v for k, v in DEFAULT_WEIGHTS["供给侧安全"].items()} | {
        "L8_CapitalFlow": 0.20,
        "L9_Signals": 0.10,
        "L10_Demand": 0.15,
        "L11_SectorRisk": 0.15,
    },
    "进取": {k: v * 0.5 for k, v in DEFAULT_WEIGHTS["供给侧安全"].items()} | {
        "L8_CapitalFlow": 0.35,
        "L9_Signals": 0.20,
        "L10_Demand": 0.10,
        "L11_SectorRisk": 0.10,
    },
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
