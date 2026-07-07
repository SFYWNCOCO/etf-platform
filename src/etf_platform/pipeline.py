"""Unified L1-L13 penetration pipeline — no etf_system dependency."""
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
    """Run all 13 layers for a single ETF code."""
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

    # L13 MacroCycle — Kondratiev+Kuznets+Juglar (k001+k002)
    try:
        from .layers.l12_macro_cycle import score_cycle_layer
        cycle_info = score_cycle_layer(sector, rl)
        scores["L13_MacroCycle"] = cycle_info["score"]
    except Exception:
        pass

    # Factor momentum adjustment — Fama-French (k003)
    try:
        from .layers.l13_factor_loading import score_factor_adjustment
        factor_adj = score_factor_adjustment(sector)
        for layer in ["L5_Tech", "L7_Irreplaceable"]:
            if layer in scores and isinstance(scores[layer], (int, float)):
                scores[layer] = round(max(1.0, min(10.0, scores[layer] + factor_adj)), 1)
    except Exception:
        pass

    # L14 Stoic Risk — dichotomy of control + negative visualization (k004)
    try:
        from .layers.l14_stoic_risk import score_stoic_layer
        stoic = score_stoic_layer(sector, rl)
        scores["L14_StoicRisk"] = stoic["score"]
        # Apply stoic adjustment to L1 (controllability bonus for safe sectors)
        # NOTE: L1_ETF is already a pure risk_level proxy. Bonus stored separately.
        if stoic.get("controllability", 5) >= 7:
            scores["L1_ControllabilityBonus"] = 0.5
    except Exception:
        pass

    # L15 State Similarity — market state recognition (k005)
    try:
        from .layers.l15_state_similarity import score_state_similarity
        state = score_state_similarity(sector)
        scores["L15_StateSim"] = state["score"]
    except Exception:
        pass

    # L16 Live Signals — premium/liquidity/quality (k006+k007+k008+k009)
    try:
        from .layers.l16_live_signals import get_live_signals
        is_cross = "QDII" in info.get("type", "") or info.get("access") == "qdii"
        live = get_live_signals(sector, is_cross_border=is_cross)
        scores["L16_LiveSignals"] = live["score"]
    except Exception:
        pass

    # L17 Quantitative Factor — Fama-French + custom factors (akshare实证校准)
    try:
        from .layers.l17_quantitative_factor import apply_factor_layer
        scores = apply_factor_layer(sector, scores)
    except Exception:
        scores["L17_Factor"] = 5.5

    # L18 VaR Risk — Value at Risk + stress testing (akshare波动率)
    try:
        from .layers.l18_var_risk import apply_var_layer
        scores = apply_var_layer(sector, scores)
    except Exception:
        scores["L18_VaR"] = 5.5

    # L19 FX Channel — exchange rate impact on cross-border ETFs
    try:
        from .layers.l19_fx_channel import apply_fx_layer
        scores = apply_fx_layer(sector, scores, info.get("type", ""))
    except Exception:
        scores["L19_FXChannel"] = 5.5

    # L20 Option Volatility — implied vol + option strategy recommendation
    try:
        from .layers.l20_option_volatility import apply_option_layer
        scores = apply_option_layer(sector, scores)
    except Exception:
        scores["L20_OptionVol"] = 5.5

    # L9 News enhancement (always attempt — sector-cached, fast)
    try:
        from .enhance.l9_news import enhance_l9
        result = enhance_l9({"etf_code": code, "layer_scores": dict(scores), "layers": {}})
        scores.update(result.get("layer_scores", {}))
    except Exception:
        pass

    # L8 Live enhancement (real-time price data — only when live=True)
    if live:
        try:
            from .enhance.l8_realtime import enhance_l8
            result = enhance_l8({"etf_code": code, "layer_scores": dict(scores), "layers": {}})
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
        "cycle_info": cycle_info,
        "pipeline_version": "1.2.0",
        "score": round(sum(scores.values()) / max(len(scores), 1), 1),
        "profile": profile,
    }


def format_full(result: dict) -> str:
    """Format all 13 layers as text report."""
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
    """Batch run for multiple ETFs with all 13 layers."""
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
