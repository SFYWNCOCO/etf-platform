"""optimize/portfolio.py — Portfolio allocation based on penetration + rotation + chain analysis.

Simplified cleaner version of etf_system/portfolio.py.
Uses analyst scores instead of causal model.
"""
from ..config_loader import load_etfs, load_general
from ..analysis.chain import evaluate_etf_risk

# Risk profile templates (weights for score categories)
PORTFOLIO_PROFILES = {
    "conservative": {
        "supply_weight": 0.40, "capital_weight": 0.15, "signal_weight": 0.05, "demand_weight": 0.30,
        "chain_penalty": 0.10,  # penalty for bad supply chain
        "preferred_types": ["策略", "债券", "宽基A"],
        "avoid_types": ["行业A", "跨境QDII"],
        "max_single_pct": 0.25,  # max 25% in one ETF
        "label": "保守型",
    },
    "balanced": {
        "supply_weight": 0.25, "capital_weight": 0.25, "signal_weight": 0.10, "demand_weight": 0.25,
        "chain_penalty": 0.15,
        "preferred_types": ["宽基A", "策略", "行业A"],
        "avoid_types": [],
        "max_single_pct": 0.30,
        "label": "均衡型",
    },
    "aggressive": {
        "supply_weight": 0.15, "capital_weight": 0.35, "signal_weight": 0.20, "demand_weight": 0.15,
        "chain_penalty": 0.15,
        "preferred_types": ["行业A", "跨境QDII", "宽基A"],
        "avoid_types": ["债券", "货币"],
        "max_single_pct": 0.35,
        "label": "进取型",
    },
}


def score_etf_for_portfolio(code, analyst_result, profile="balanced"):
    """Score a single ETF for portfolio inclusion."""
    pf = PORTFOLIO_PROFILES.get(profile, PORTFOLIO_PROFILES["balanced"])
    
    composite = analyst_result.get("composite_score", 0) or 0
    supply = analyst_result.get("supply_score", 5) or 5
    capital = analyst_result.get("capital_score", 5) or 5
    demand = analyst_result.get("demand_score", 5) or 5
    signal_s = analyst_result.get("signal_score", 5) or 5
    
    # Weighted score
    score = (supply * pf["supply_weight"] + 
             capital * pf["capital_weight"] +
             signal_s * pf["signal_weight"] +
             demand * pf["demand_weight"])
    
    # Chain risk penalty
    chain = evaluate_etf_risk(code)
    if chain and chain["score"] >= 2.0:
        penalty = chain["score"] * pf["chain_penalty"]
        score -= penalty
    
    # Type preference bonus/penalty
    info = load_etfs().get(code, {})
    etype = info.get("type", "")
    if etype in pf["preferred_types"]:
        score += 0.5
    elif etype in pf["avoid_types"]:
        score -= 0.5
    
    return round(max(score, 0), 2)


def allocate(analyst_results, budget=1000, profile="balanced", max_positions=5):
    """Allocate budget across ETFs based on analyst scores.
    
    Args:
        analyst_results: dict of {code: analyst_result} 
        budget: total amount to invest
        profile: conservative/balanced/aggressive
        max_positions: max number of ETFs
    Returns:
        list of {code, name, score, amount, pct}
    """
    pf = PORTFOLIO_PROFILES.get(profile, PORTFOLIO_PROFILES["balanced"])
    etfs = load_etfs()
    general = load_general()
    min_pos = general.get("min_position", 100)
    
    # Score each ETF
    scored = []
    for code, ar in analyst_results.items():
        s = score_etf_for_portfolio(code, ar, profile)
        name = ar.get("name", etfs.get(code, {}).get("name", code))
        scored.append({"code": code, "name": name, "score": s})
    
    # Sort by score descending
    scored.sort(key=lambda x: x["score"], reverse=True)
    
    # Take top candidates (2x max_positions for selection)
    candidates = [s for s in scored if s["score"] > 0][:max_positions * 2]
    
    if not candidates:
        return []
    
    # Normalize scores to weights
    total_score = sum(max(s["score"], 0.01) for s in candidates)
    for s in candidates:
        s["weight"] = round(s["score"] / total_score, 4)
    
    # Allocate budget
    allocated = []
    remaining = float(budget)
    for i, s in enumerate(candidates[:max_positions]):
        pct = s["weight"]
        if i == max_positions - 1:
            amount = remaining
        else:
            amount = round(budget * pct, 0)
            amount = max(amount, min_pos)
        pct_actual = amount / budget * 100
        allocated.append({
            "code": s["code"],
            "name": s["name"],
            "score": s["score"],
            "amount": amount,
            "pct": round(pct_actual, 1),
        })
        remaining -= amount
    
    return allocated


def generate_portfolio_report(analyst_results, budget=1000, profile="balanced"):
    """Generate a full portfolio allocation report."""
    pf = PORTFOLIO_PROFILES.get(profile, PORTFOLIO_PROFILES["balanced"])
    alloc = allocate(analyst_results, budget, profile)
    
    lines = []
    lines.append("")
    lines.append("  [投资组合分配] %s | 预算: %d元" % (pf["label"], budget))
    lines.append("  %s" % ("="*55))
    
    if not alloc:
        lines.append("  无合适标的")
        return "\n".join(lines)
    
    total_pct = 0
    for a in alloc:
        total_pct += a["pct"]
        lines.append("  %-8s %-20s %6.0f元 %5.1f%% (评分:%.1f)" % (
            a["code"], a["name"][:18], a["amount"], a["pct"], a["score"]))
    
    lines.append("  %s" % ("-"*55))
    lines.append("  %-30s %6d元 %5.1f%%" % ("合计", sum(a["amount"] for a in alloc), total_pct))
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    # Test with mock data
    mock_results = {
        "512890": {"composite_score": 7.39, "supply_score": 8.2, "capital_score": 6.0, 
                   "signal_score": 7.6, "demand_score": 7.5, "name": "红利低波ETF"},
        "159995": {"composite_score": 5.30, "supply_score": 3.5, "capital_score": 5.5,
                   "signal_score": 4.5, "demand_score": 7.5, "name": "芯片ETF"},
        "159819": {"composite_score": 5.27, "supply_score": 3.8, "capital_score": 4.5,
                   "signal_score": 5.6, "demand_score": 7.5, "name": "AI智能"},
        "518880": {"composite_score": 7.0, "supply_score": 8.2, "capital_score": 6.0,
                   "signal_score": 5.0, "demand_score": 7.0, "name": "黄金ETF"},
        "159201": {"composite_score": 7.0, "supply_score": 8.4, "capital_score": 4.5,
                   "signal_score": 5.0, "demand_score": 7.5, "name": "自由现金流ETF"},
        "511010": {"composite_score": 7.5, "supply_score": 9.0, "capital_score": 7.0,
                   "signal_score": 6.0, "demand_score": 8.0, "name": "国债ETF"},
    }
    
    from ..analysis.chain import evaluate_etf_risk
    # Mock evaluate_etf_risk
    
    for profile in ["conservative", "balanced", "aggressive"]:
        print(generate_portfolio_report(mock_results, budget=1000, profile=profile))