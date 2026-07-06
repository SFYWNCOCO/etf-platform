"""Unified L1-L12 penetration pipeline — no etf_system dependency."""
from .config_loader import load_etfs


def _score_from_risk(risk_level: float, base: float = 5.0, invert: bool = True, soft_floor: bool = True) -> float:
    """Convert risk_level (0-1) to layer score (0-10).
    invert=True: high risk → low score (safer ETF scores higher)
    invert=False: high risk → high score (more volatile ETF scores higher)
    soft_floor=True: floor at 1.0 for non-L1 layers.
    soft_floor=False: no floor (for L1_ETF which must reflect true risk_level)."""
    if invert:
        val = (1.0 - risk_level) * 10
    else:
        val = risk_level * 10
    if soft_floor:
        val = max(1.0, val)
    return round(min(10.0, val), 1)


def run_full(code: str, live: bool = True, profile: str = "均衡") -> dict:
    """Run all 12 layers for a single ETF code."""
    etfs = load_etfs()
    info = etfs.get(code, {})
    if not info:
        return {"etf_code": code, "error": "ETF not found", "layer_scores": {}}

    rl = info.get("risk_level", 0.5)
    sector = info.get("sector", "未知行业")
    name = info.get("name", code)

    # Aggressive profile: invert risk scoring to reward volatility/catalyst potential
    if profile == "激进":
        scores = {
            "L1_ETF": _score_from_risk(rl, invert=False, soft_floor=False),
            "L3_Material": _score_from_risk(rl, invert=True),
            "L4_SupplyChain": _score_from_risk(rl, invert=True),
            "L5_Tech": _score_from_risk(rl, invert=True),
            "L6_Politics": _score_from_risk(rl, invert=True),
            "L7_Irreplaceable": _score_from_risk(rl, invert=True),
            "L8_CapitalFlow": _score_from_risk(rl, invert=False),
            "L9_Signals": _score_from_risk(rl, invert=False),
        }
    else:
        scores = {
            "L1_ETF": _score_from_risk(rl, invert=False, soft_floor=False),
            "L3_Material": _score_from_risk(rl),
            "L4_SupplyChain": _score_from_risk(rl),
            "L5_Tech": _score_from_risk(rl),
            "L6_Politics": _score_from_risk(rl),
            "L7_Irreplaceable": _score_from_risk(rl),
            "L8_CapitalFlow": _score_from_risk(rl),
            "L9_Signals": _score_from_risk(rl),
        }

    # Material/Personnel/Tech bridge (deep.py -> L3-L7)
    try:
        from .analysis.material_bridge import apply_to_layers
        scores = apply_to_layers(code, scores, sector)
    except Exception:
        pass

    # v5.5: Sector-informed L3-L7 scores replace risk_level derivation
    try:
        from .analysis.layer_sector_scores import get_sector_layer_scores
        sector_layers = get_sector_layer_scores(sector, rl)
        scores.update(sector_layers)
    except Exception:
        try:
            from .analysis.layer_factors import apply_factors
            scores = apply_factors(sector, scores)
        except Exception:
            pass

    # v2.0: Multi-signal ETF-level diff (replaces v7.5 fee+type micro-adj)
    # Uses 5 dimensions: fee_tier, type_breadth, cross_border, leverage, sector_purity
    try:
        from .analysis.multi_signal_differentiator import differentiate
        scores = differentiate(code, sector, scores, info)
    except Exception:
        pass

    # v5.5: L2 Holdings penetration
    try:
        from .analysis.l2_holdings_bridge import apply_l2_score
        scores = apply_l2_score(code, sector, scores, risk_level=rl, fee=info.get("fee", 0.005))
    except Exception:
        scores["L2_Holdings"] = 5.0

    # Add demand layers (L10+L11)
    try:
        from .analysis.demand import score_demand_climate, score_sector_demand_risk
        l10_result = score_demand_climate(sector, risk_level=rl)
        l11_result = score_sector_demand_risk(sector, risk_level=rl)
        scores["L10_Demand"] = l10_result.get("score", 5.0)
        scores["L11_SectorRisk"] = l11_result.get("score", 5.0)
    except Exception:
        scores["L10_Demand"] = 5.0
        scores["L11_SectorRisk"] = 5.0

    # Macro climate adjustment for L10 demand
    try:
        from .analysis.macro_climate import apply_to_demand
        scores["L10_Demand"] = apply_to_demand(sector, scores["L10_Demand"])
    except Exception:
        pass

    # Chain risk adjustment for semiconductor/AI ETFs
    try:
        from .analysis.chain import evaluate_etf_risk
        cr = evaluate_etf_risk(code)
        if cr and cr.get("score", 0) >= 2.0:
            penalty = min(cr["score"] * 0.2, 1.5)
            for layer in ["L3_Material", "L4_SupplyChain", "L5_Tech", "L6_Politics"]:
                scores[layer] = round(max(1.0, scores[layer] - penalty), 1)
    except Exception:
        pass

    # Material bridge (second pass)
    try:
        from .analysis.material_bridge import apply_to_layers
        scores = apply_to_layers(code, scores, sector)
    except Exception:
        pass

    # Live data adjustments
    try:
        from .analysis.layer_live_adjustments import apply_live_adjustments
        scores = apply_live_adjustments(sector, scores)
    except Exception:
        pass

    # Soft floor for supply-side layers
    SOFT_FLOOR = 2.0
    for supply_layer in ["L3_Material", "L4_SupplyChain", "L5_Tech", "L6_Politics", "L7_Irreplaceable"]:
        if supply_layer in scores and scores[supply_layer] < SOFT_FLOOR:
            scores[supply_layer] = SOFT_FLOOR

    # Sector flow bridge: real L8/L9 from Eastmoney fund flows
    try:
        from .analysis.sector_flow_bridge import get_bridge
        bridge = get_bridge()
        etf_type = info.get("type", "")
        etf_fee = info.get("fee", 0.005)
        flow_scores = bridge.score(sector, risk_level=rl, etf_type=etf_type, fee=etf_fee, etf_code=code)
        scores["L8_CapitalFlow"] = flow_scores["L8"]
        scores["L9_Signals"] = flow_scores["L9"]
    except Exception:
        pass

    # L12 Political Risk (sector-based)
    try:
        from .analysis.political_risk import calculate_political_risk_score
        pr_info = calculate_political_risk_score(sector)
        scores["L12_PoliticalRisk"] = pr_info.get("adjusted_score", 5.0)
    except Exception:
        pass

    # Live enhancement (real-time price/news)
    if live:
        try:
            from .enhance.l8_realtime import enhance_l8
            result = enhance_l8({"etf_code": code, "layer_scores": dict(scores), "layers": {}})
            scores.update(result.get("layer_scores", {}))
        except Exception:
            pass
        try:
            from .enhance.l9_news import enhance_l9
            result = enhance_l9({"etf_code": code, "layer_scores": dict(scores), "layers": {}})
            scores.update(result.get("layer_scores", {}))
        except Exception:
            pass

    return {
        "etf_code": code,
        "name": name,
        "sector": sector,
        "type": info.get("type", ""),
        "leverage": info.get("leverage", 1.0),
        "risk_level": rl,
        "layer_scores": scores,
        "layers": {},
        "pipeline_version": "1.0.0",
        "score": round(sum(scores.values()) / max(len(scores), 1), 1),
        "profile": profile,
    }


def format_full(result: dict) -> str:
    """Format all 12 layers as text report."""
    code = result.get("etf_code", "?")
    name = result.get("name", code)
    sector = result.get("sector", "?")
    scores = result.get("layer_scores", {})
    lines = [
        f"ETF: {code} {name}",
        f"Sector: {sector} | Risk: {result.get('risk_level', '?')}",
        f"Composite: {result.get('score', 0):.1f}/10",
        "-" * 40,
    ]
    for k, v in sorted(scores.items()):
        lines.append(f"  {k}: {v}")
    return "\n".join(lines)


def batch_full(limit: int = 50, sort_by: str = "score", codes: list = None, live: bool = False, profile: str = "均衡") -> list:
    """Batch run for multiple ETFs with all 12 layers."""
    etfs = load_etfs()
    if codes:
        target = codes
    else:
        target = [c for c in etfs if c.isdigit()][:limit]

    results = []
    for code in target:
        try:
            r = run_full(code, live=live, profile=profile)
            results.append(r)
        except Exception:
            continue

    if sort_by == "score":
        results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return results
