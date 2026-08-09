"""Unified L1-L13 penetration pipeline — no etf_system dependency."""
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

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


# ── Step helpers ────────────────────────────────────────────────

def _init_base_scores(rl: float, profile: str) -> dict:
    """Initial base scores from risk level + investor profile."""
    if profile == "激进":
        return {
            "L1_ETF": _score_from_risk(rl, invert=False, soft_floor=False),
            "L3_Material": _score_from_risk(rl, invert=True),
            "L4_SupplyChain": _score_from_risk(rl, invert=True),
            "L5_Tech": _score_from_risk(rl, invert=True),
            "L6_Politics": _score_from_risk(rl, invert=True),
            "L7_Irreplaceable": _score_from_risk(rl, invert=True),
            "L8_CapitalFlow": _score_from_risk(rl, invert=False),
            "L9_Signals": _score_from_risk(rl, invert=False),
        }
    return {
        "L1_ETF": _score_from_risk(rl, invert=False, soft_floor=False),
        "L3_Material": _score_from_risk(rl),
        "L4_SupplyChain": _score_from_risk(rl),
        "L5_Tech": _score_from_risk(rl),
        "L6_Politics": _score_from_risk(rl),
        "L7_Irreplaceable": _score_from_risk(rl),
        "L8_CapitalFlow": _score_from_risk(rl),
        "L9_Signals": _score_from_risk(rl),
    }


def _apply_material_bridge(scores: dict, code: str, sector: str) -> dict:
    """Material/Personnel/Tech bridge (deep.py -> L3-L7)."""
    try:
        from .analysis.material_bridge import apply_to_layers
        return apply_to_layers(code, scores, sector)
    except Exception:
        return scores


def _apply_sector_scores(scores: dict, sector: str, rl: float) -> None:
    """v5.5: Sector-informed L3-L7 scores replace risk_level derivation."""
    try:
        from .analysis.layer_sector_scores import get_sector_layer_scores
        scores.update(get_sector_layer_scores(sector, rl))
    except Exception:
        try:
            from .analysis.layer_factors import apply_factors
            scores.update(apply_factors(sector, scores))
        except Exception:
            pass


def _apply_live_material_fusion(scores: dict, code: str, sector: str, live: bool) -> None:
    """Fuse real-time commodity prices into L3/L4 (only when live=True).

    material_live.py was dead code — never referenced by pipeline. This activates it:
    static sector table (from _apply_sector_scores) is the baseline; live commodity
    data then adjusts L3/L4 by a sector weight (upstream sectors benefit from price
    rises, mid/downstream get cost-pressure penalty). Strictly best-effort: any
    network failure keeps the static baseline.
    """
    if not live:
        return
    try:
        from .analysis.material_live import apply_live_material_scores
        apply_live_material_scores(code, sector, scores)
    except Exception:
        pass


def _apply_multi_signal(scores: dict, code: str, sector: str, info: dict) -> None:
    """v2.0: Multi-signal ETF-level diff (replaces v7.5 fee+type micro-adj)."""
    try:
        from .analysis.multi_signal_differentiator import differentiate
        scores.update(differentiate(code, sector, scores, info))
    except Exception:
        pass


def _apply_l2_holdings(scores: dict, code: str, sector: str, rl: float, fee: float) -> None:
    """v5.5: L2 Holdings penetration."""
    try:
        from .analysis.l2_holdings_bridge import apply_l2_score
        scores.update(apply_l2_score(code, sector, scores, risk_level=rl, fee=fee))
    except Exception:
        scores["L2_Holdings"] = 5.0


def _apply_demand(scores: dict, sector: str, rl: float) -> None:
    """Add demand layers (L10+L11)."""
    try:
        from .analysis.demand import score_demand_climate, score_sector_demand_risk
        scores["L10_Demand"] = score_demand_climate(sector, risk_level=rl).get("score", 5.0)
        scores["L11_SectorRisk"] = score_sector_demand_risk(sector, risk_level=rl).get("score", 5.0)
    except Exception:
        scores["L10_Demand"] = 5.0
        scores["L11_SectorRisk"] = 5.0


def _apply_macro_climate(scores: dict, sector: str) -> None:
    """Macro climate adjustment for L10 demand."""
    try:
        from .analysis.macro_climate import apply_to_demand
        scores["L10_Demand"] = apply_to_demand(sector, scores["L10_Demand"])
    except Exception:
        pass


def _apply_chain_penalty(scores: dict, code: str) -> None:
    """Chain risk adjustment for semiconductor/AI ETFs."""
    try:
        from .analysis.chain import evaluate_etf_risk
        cr = evaluate_etf_risk(code)
        if cr and cr.get("score", 0) >= 2.0:
            penalty = min(cr["score"] * 0.2, 1.5)
            for layer in ["L3_Material", "L4_SupplyChain", "L5_Tech", "L6_Politics"]:
                scores[layer] = round(max(1.0, scores[layer] - penalty), 1)
    except Exception:
        pass


def _apply_soft_floor(scores: dict) -> None:
    """Soft floor for supply-side layers."""
    SOFT_FLOOR = 2.0
    for supply_layer in ["L3_Material", "L4_SupplyChain", "L5_Tech", "L6_Politics", "L7_Irreplaceable"]:
        if supply_layer in scores and scores[supply_layer] < SOFT_FLOOR:
            scores[supply_layer] = SOFT_FLOOR


def _apply_sector_flow(scores: dict, info: dict, rl: float, code: str, sector: str = "", live: bool = True) -> None:
    """Sector flow bridge: real L8/L9 from Eastmoney fund flows."""
    try:
        from .analysis.sector_flow_bridge import get_bridge
        bridge = get_bridge()
        etf_type = info.get("type", "")
        etf_fee = info.get("fee", 0.005)
        flow_scores = bridge.score(sector, risk_level=rl, etf_type=etf_type, fee=etf_fee, etf_code=code, live=live)
        scores["L8_CapitalFlow"] = flow_scores["L8"]
        scores["L9_Signals"] = flow_scores["L9"]
    except Exception:
        pass


def _apply_l12_political_risk(scores: dict, sector: str) -> None:
    """L12 Political Risk (sector-based)."""
    try:
        from .analysis.political_risk import calculate_political_risk_score
        pr_info = calculate_political_risk_score(sector)
        scores["L12_PoliticalRisk"] = pr_info.get("adjusted_score", 5.0)
    except Exception:
        pass


def _apply_l13_macro_cycle(scores: dict, sector: str, rl: float) -> dict:
    """L13 MacroCycle — Kondratiev+Kuznets+Juglar (k001+k002)."""
    cycle_info = {}
    try:
        from .layers.l12_macro_cycle import score_cycle_layer
        cycle_info = score_cycle_layer(sector, rl)
        scores["L13_MacroCycle"] = cycle_info["score"]
    except Exception:
        pass
    return cycle_info


def _apply_factor_momentum(scores: dict, sector: str) -> None:
    """Factor momentum adjustment — Fama-French (k003)."""
    try:
        from .layers.l13_factor_loading import score_factor_adjustment
        factor_adj = score_factor_adjustment(sector)
        for layer in ["L5_Tech", "L7_Irreplaceable"]:
            if layer in scores and isinstance(scores[layer], (int, float)):
                scores[layer] = round(max(1.0, min(10.0, scores[layer] + factor_adj)), 1)
    except Exception:
        pass


def _apply_stoic_risk(scores: dict, sector: str, rl: float) -> None:
    """L14 Stoic Risk — dichotomy of control + negative visualization (k004)."""
    try:
        from .layers.l14_stoic_risk import score_stoic_layer
        stoic = score_stoic_layer(sector, rl)
        scores["L14_StoicRisk"] = stoic["score"]
        if stoic.get("controllability", 5) >= 7:
            scores["L1_ControllabilityBonus"] = 0.5
    except Exception:
        pass


def _apply_state_similarity(scores: dict, sector: str) -> None:
    """L15 State Similarity — market state recognition (k005)."""
    try:
        from .layers.l15_state_similarity import score_state_similarity
        state = score_state_similarity(sector)
        scores["L15_StateSim"] = state["score"]
    except Exception:
        pass


def _apply_live_signals(scores: dict, sector: str = "", is_cross: bool = False) -> None:
    """L16 Live Signals — premium/liquidity/quality (k006+k007+k008+k009)."""
    try:
        from .layers.l16_live_signals import get_live_signals
        live = get_live_signals(sector, is_cross_border=is_cross)
        scores["L16_LiveSignals"] = live["score"]
    except Exception:
        pass


def _apply_quantitative_factor(scores: dict, sector: str) -> None:
    """L17 Quantitative Factor — Fama-French + custom factors (akshare实证校准)."""
    try:
        from .layers.l17_quantitative_factor import apply_factor_layer
        scores.update(apply_factor_layer(sector, scores))
    except Exception:
        scores["L17_Factor"] = 5.5


def _apply_var_risk(scores: dict, sector: str) -> None:
    """L18 VaR Risk — Value at Risk + stress testing (akshare波动率)."""
    try:
        from .layers.l18_var_risk import apply_var_layer
        scores.update(apply_var_layer(sector, scores))
    except Exception:
        scores["L18_VaR"] = 5.5


def _apply_fx_channel(scores: dict, sector: str, etf_type: str) -> None:
    """L19 FX Channel — exchange rate impact on cross-border ETFs."""
    try:
        from .layers.l19_fx_channel import apply_fx_layer
        scores.update(apply_fx_layer(sector, scores, etf_type))
    except Exception:
        scores["L19_FXChannel"] = 5.5


def _apply_option_volatility(scores: dict, sector: str) -> None:
    """L20 Option Volatility — implied vol + option strategy recommendation."""
    try:
        from .layers.l20_option_volatility import apply_option_layer
        scores.update(apply_option_layer(sector, scores))
    except Exception:
        scores["L20_OptionVol"] = 5.5


def _apply_behavioral_psychology(scores: dict, details: dict, sector: str, rl: float) -> None:
    """L21 Behavioral Psychology — bias + overconfidence (k010)."""
    try:
        from .layers.l21_investment_psychology import score_l21_layers
        l21 = score_l21_layers(sector, risk_level=rl)
        scores["L21_Behavior"] = l21.get("score", 5.5)
        if l21.get("bias_detail"):
            details["L21_BiasDetail"] = l21["bias_detail"]
    except Exception:
        scores["L21_Behavior"] = 5.5
        details["L21_BiasDetail"] = "unknown"


def _apply_pendulum(scores: dict, details: dict, sector: str, rl: float, code: str = "") -> None:
    """L22 Market Pendulum — fear/greed swing (k011)."""
    try:
        from .layers.l22_market_pendulum import score_pendulum_layer
        # Pass ETF code so pendulum uses real 20d/vol/volume signals
        trend_data = {}
        if code:
            try:
                from .data.kline import get_trend
                t = get_trend(code)
                if t:
                    trend_data = {
                        "change_20d": t.change_20d,
                        "volatility_20d": t.volatility_20d,
                        "volume_ratio_5_20": t.volume_ratio_5_20,
                        "position_pct": t.position_pct,
                        "premium_pct": 0.0,
                    }
            except Exception:
                pass
        pendulum = score_pendulum_layer(sector, risk_level=rl, etf_code=code, trend_data=trend_data)
        scores["L22_Pendulum"] = pendulum.get("score", 5.0)
        if pendulum.get("detail"):
            details["L22_Pendulum"] = pendulum["detail"]
    except Exception:
        scores["L22_Pendulum"] = 5.0


def _apply_valuation(scores: dict, details: dict, code: str, sector: str, name: str, rl: float) -> None:
    """L23 Valuation — PE/PB/dividend yield vs sector median."""
    try:
        from .layers.l23_valuation import compute_valuation_layer
        val = compute_valuation_layer(code, sector, name, risk_level=rl)
        scores["L23_Valuation"] = val.get("L23_Valuation", 5.0)
        if val.get("L23_Detail"):
            details["L23_Valuation"] = val["L23_Detail"]
    except Exception:
        scores["L23_Valuation"] = 5.0


def _apply_microstructure(scores: dict, details: dict, sector: str, rl: float, code: str = "") -> None:
    """L23 Microstructure — OBI/turnover anomaly (k012)."""
    try:
        from .layers.l23_microstructure import score_microstructure
        # Pass ETF code so microstructure uses real volume/volatility signals
        micro = score_microstructure(sector, risk_level=rl, etf_code=code)
        scores["L23_Microstructure"] = micro.get("score", 5.0)
        if micro.get("detail"):
            details["L23_Microstructure"] = micro["detail"]
        else:
            details["L23_Microstructure"] = {
                "signal": micro.get("signal"),
                "turnover_anomaly": micro.get("turnover_anomaly"),
                "vol_distribution": micro.get("vol_distribution"),
                "noise_level": micro.get("noise_level"),
                "volume_ratio": micro.get("volume_ratio"),
                "change_5d": micro.get("change_5d"),
            }
    except Exception:
        scores["L23_Microstructure"] = 5.0


def _apply_dip_flow(scores: dict, details: dict, code: str, sector: str, rl: float, live: bool = False) -> None:
    """L24 Dip Flow — premium/discount signal."""
    try:
        from .analysis.dip_monitor import score_dip_layer
        from .analysis.premium_cache import get_premium_pct
        premium_pct = get_premium_pct(code, sector=sector, live=live)
        # live=False且缓存空时: 用L16行业溢价估计做fallback, 避免L24永远5.0
        if premium_pct is None:
            try:
                from .layers.l16_live_signals import SECTOR_PREMIUM_ESTIMATES
                premium_pct = SECTOR_PREMIUM_ESTIMATES.get(sector, SECTOR_PREMIUM_ESTIMATES.get("default", 0.0))
            except Exception:
                premium_pct = 0.0
        dip = score_dip_layer(code=code, sector=sector, premium_pct=premium_pct)
        scores["L24_DipFlow"] = dip.get("score", 5.0)
        if dip.get("signal"):
            details["L24_DipFlow"] = dip["signal"]
    except Exception:
        scores["L24_DipFlow"] = 5.0



def _apply_system_dynamics(scores: dict, details: dict, sector: str, rl: float, code: str = "") -> None:
    """L24 System Dynamics — feedback loops, leverage points, damping from complex systems theory (k238/k268).
    
    This layer computes SD-based metrics that capture systemic properties invisible to 
    traditional finance-only analysis: dominance of reinforcing vs balancing feedback,
    intervention leverage potential in the underlying economic ecosystem, oscillation 
    damping characteristics, and resonance risk of boom-bust regimes.
    
    Inspired by Donella Meadows' "Leverage Points" and Sterman's "Business Dynamics",
    these metrics help identify ETFs with robust structural resilience versus those 
    prone to destabilizing dynamics under stress.
    """
    try:
        from .layers.l24_system_dynamics import score_l24_layer
        result = score_l24_layer(sector, rl, code)
        scores["L24_SystemDynamics"] = result.get("score", 5.0)
        if "metrics" in result:
            details["L24_SD_Metrics"] = result["metrics"]
        if "insights" in result and result["insights"]:
            details["L24_SD_Incidents"] = "; ".join(result["insights"][:3])
    except Exception:
        scores["L24_SystemDynamics"] = 5.0
        details["L24_SD_Metrics"] = {"error": "failed"}



def _apply_l30_layer(scores: dict, details: dict, sector: str, rl: float, code: str = "") -> None:
    """L30 Multi-Agent Interaction — MAS-based systemic resilience analysis (MAS theory + k275).
    
    This layer quantifies multi-agent system properties underlying the ETF's ecosystem:
    participant heterogeneity diversity, inter-agent coordination density, feedback loop
    strength between agent groups, and overall systemic resilience through self-organization
    
    Draws on multi-agent systems theory, complex adaptive systems principles, and 
    leverage point analysis from Donella Meadows' framework. Identifies whether the 
    market structure is robustly distributed or dangerously concentrated/collusive.
    """
    try:
        from .layers.l30_multiagent import score_l30_layer
        result = score_l30_layer(sector, rl, code)
        scores["L30_MultiAgent"] = result.get("score", 6.0)
        if "metrics" in result:
            details["L30_MA_Metrics"] = result["metrics"]
        if "insights" in result and result["insights"]:
            details["L30_MA_Incidents"] = "; ".join(result["insights"][:2])
    except Exception:
        scores["L30_MultiAgent"] = 6.0
        details["L30_MA_Metrics"] = {"error": "failed"}

def _estimate_hurst(code: str) -> Optional[float]:
    """估算 ETF 的 Hurst 指数（k190）。真实K线优先，失败退化到趋势近似；全程异常安全返回 None。"""
    try:
        from .data.kline import _fetch_kline, get_trend
        from .analysis.hurst_regime import hurst_dfa, _MIN_POINTS
        rows = _fetch_kline(code, 300)
        if rows and len(rows) >= 150:
            prices = [float(r["close"]) for r in rows]
            # hurst_dfa 输入应为日收益率增量序列（价格本身是积分序列，会得到 H≈1.5 失真）
            returns = [prices[i] / prices[i - 1] - 1 for i in range(1, len(prices))]
            H, r2 = hurst_dfa(returns)
            if r2 > 0.0 and H == H:  # 排除 nan
                return H
        t = get_trend(code)
        if t is not None:
            chg = getattr(t, "change_20d", 0.0) or 0.0
            vol = getattr(t, "volatility_20d", 0.0) or 0.0  # 年化百分比（如 30.5 = 30.5%）
            if chg > 8 and vol > 3.0:
                return 0.60
            if vol < 2.0:
                return 0.45
        return None
    except Exception:
        return None


def _apply_regime_factor(scores: dict, details: dict, sector: str, code: str = "") -> None:
    """L33 Regime Factor — dynamic factor alignment by QVIX regime + Hurst calibration (k190)。"""
    try:
        from .analysis.qvix_regime import get_regime
        from .layers.l33_regime_factor import score_l33_layer
        qvix_regime = get_regime().get("regime", "normal")
        hurst = _estimate_hurst(code) if code else None
        regime = score_l33_layer(sector, qvix_regime=qvix_regime, hurst=hurst)
        scores["L33_RegimeFactor"] = regime.get("score", 5.0)
        if regime.get("detail"):
            details["L33_Detail"] = regime["detail"]
    except Exception:
        scores["L33_RegimeFactor"] = 5.0


def _apply_kb_catalyst(scores: dict, details: dict, sector: str) -> None:
    """L34 KB Catalyst — 知识库催化剂信号层(k033/k053/k090/k092/k094/k098/k117/k118/k122/k123/k124/k125/k126/k260)."""
    try:
        from .layers.l34_kb_catalyst import score_l34_layer
        catalyst = score_l34_layer(sector)
        scores["L34_KBCatalyst"] = catalyst.get("score", 5.0)
        if catalyst.get("detail"):
            details["L34_CatalystDetail"] = catalyst["detail"]
    except Exception:
        scores["L34_KBCatalyst"] = 5.0


def _apply_liquidity_arbitrage(scores: dict, details: dict, etf_type: str, sector: str) -> None:
    """L25 Liquidity & Arbitrage — ETF流动性与套利机制(k261)."""
    try:
        from .layers.l25_liquidity_arbitrage import score_l25_layer
        liq = score_l25_layer(etf_type=etf_type, sector=sector)
        scores["L25_LiquidityArb"] = liq.get("score", 5.0)
        if liq.get("detail"):
            details["L25_LiquidityDetail"] = liq["detail"]
    except Exception:
        scores["L25_LiquidityArb"] = 5.0


def _apply_volatility_regime(scores: dict, details: dict, sector: str, code: str = "") -> None:
    """L26 Volatility Regime — 波动率制度+GARCH信号(k063+k091)."""
    try:
        from .layers.l26_volatility_regime import score_l26_layer
        realized_vol = None
        if code:
            try:
                from .data.kline import get_trend
                t = get_trend(code)
                if t:
                    realized_vol = t.volatility_20d / 100  # 70.9% → 0.709
            except Exception:
                pass
        vol = score_l26_layer(sector=sector, realized_vol=realized_vol)
        scores["L26_VolRegime"] = vol.get("score", 5.0)
        if vol.get("detail"):
            details["L26_VolDetail"] = vol["detail"]
    except Exception:
        scores["L26_VolRegime"] = 5.0


def _apply_factor_smart_beta(scores: dict, details: dict, sector: str, regime: str = "sideways") -> None:
    """L27 Factor Smart Beta — 因子投资与Smart Beta(k042+k229)."""
    try:
        from .layers.l27_factor_smart_beta import score_l27_layer
        factor = score_l27_layer(sector=sector, regime=regime)
        scores["L27_FactorBeta"] = factor.get("score", 5.0)
        if factor.get("detail"):
            details["L27_FactorDetail"] = factor["detail"]
    except Exception:
        scores["L27_FactorBeta"] = 5.0


def _compute_composite_score(scores: dict) -> float:
    """Weighted composite: exclude bonus/non-score keys, fall back to arithmetic mean."""
    EXCLUDE_KEYS = {"L1_ControllabilityBonus", "L21_BiasDetail", "L22_Detail",
                    "L23_ValuationDetail", "L23_MicrostructureDetail",
                    "L24_DipFlow", "L24_DipSignal", "L33_Detail",
                    "L34_CatalystDetail", "L25_LiquidityDetail",
                    "L26_VolDetail", "L27_FactorDetail"}
    numeric = {k: v for k, v in scores.items()
               if k not in EXCLUDE_KEYS and isinstance(v, (int, float))}
    if not numeric:
        return 0.0
    # Equal-weight composite (pipeline doesn't own screener's variance-based weights)
    return round(sum(numeric.values()) / len(numeric), 2)


def _build_result(code: str, name: str, sector: str, info: dict, rl: float,
                  scores: dict, cycle_info: dict, profile: str,
                  layer_details: dict) -> dict:
    """Assemble final result dictionary."""
    composite = _compute_composite_score(scores)
    # score must use same exclusion logic as composite_score — previously
    # simple mean over ALL numeric values differed from composite (which
    # excludes bonus/detail keys), causing inconsistent rankings.
    return {
        "etf_code": code,
        "name": name,
        "sector": sector,
        "type": info.get("type", ""),
        "leverage": info.get("leverage", 1.0),
        "risk_level": rl,
        "layer_scores": scores,
        "layer_details": layer_details,
        "layers": {},
        "cycle_info": cycle_info,
        "pipeline_version": "1.3.0-MAPREDUCE+DEBATE",
        "score": composite,
        "composite_score": composite,
        "profile": profile,
    }


def _enhance_news(scores: dict, code: str, details: dict = None, sector: str = "") -> None:
    """L9 News enhancement with integrated SD metrics using production-grade news handler.
    
    This enhanced version now:
    1. Extracts real-time signals from news headlines/content via NewsHandler
    2. Integrates SD-derived feedback ratios and leverage point context
    3. Produces enriched metadata for downstream consumption
    4. Falls back gracefully if any step fails
    
    Reference: etf_platform.analysis.news_handler.NewsHandler
    Integration point: Skill multi-agent-systems-framework + system-dynamics-feedback-loops
    """
    try:
        from etf_platform.analysis.news_handler import get_news_handler
        
        # Sector from caller or layer metadata
        if not sector:
            sector = details.get("sector", "") if details else ""
        if not sector:
            sector = scores.get("sector", "")
        
        # Create handler with tuned sensitivity for ETF analysis
        handler = get_news_handler(sensitivity=0.12, decay_hours=24)
        
        # Load real news signals from data/news_etf_signals.json (produced by
        # news_to_etf_bridge.py --auto cron). Falls back to placeholder if missing.
        cached_signals = None
        try:
            from pathlib import Path
            import json as _json
            _sig_path = Path(__file__).resolve().parent.parent.parent.parent / "data" / "news_etf_signals.json"
            if _sig_path.exists():
                _all = _json.loads(_sig_path.read_text(encoding="utf-8"))
                _sig = _all.get(code, {})
                if _sig and isinstance(_sig, dict) and _sig.get("direction"):
                    cached_signals = [{
                        "title": _sig.get("summary", ""),
                        "direction": _sig.get("direction", "中性"),
                        "score": abs(_sig.get("news_score", 0.5)),
                        "source": _sig.get("source", ""),
                        "category": _sig.get("sector", sector),
                    }]
        except Exception:
            cached_signals = None
        
        # Use the real news-enhanced scoring path (news_handler.enhance_pipeline_scores)
        # instead of the old hardcoded 0.3 placeholder.
        handler.enhance_pipeline_scores(scores, sector, code, cached_signals=cached_signals)
        # layer_scores must stay numeric-only: move non-numeric L9 metadata to details
        for _k in ("L9_Keywords", "L9_LastUpdated", "L9_TotalSignals"):
            if _k in scores and not isinstance(scores[_k], (int, float)):
                details[_k] = scores.pop(_k)
        details["L9_LastUpdated"] = scores.get("L9_LastUpdated", time.strftime("%Y-%m-%d %H:%M"))
        logger.info(f"[_enhance_news] Applied news enhancement for {code}")
        
    except Exception as e:
        logger.warning(f"[_enhance_news] Failed for {code}: {str(e)}")
        # Don't fail the whole pipeline; just skip news enhancement
        pass


def _enhance_realtime(scores: dict, code: str) -> None:
    """L8 Live enhancement (real-time price data — only when live=True)."""
    try:
        from .enhance.l8_realtime import enhance_l8
        result = enhance_l8({"etf_code": code, "layer_scores": dict(scores), "layers": {}})
        scores.update(result.get("layer_scores", {}))
    except Exception:
        pass


def _run_live_adjustments(scores: dict, sector: str) -> None:
    """Live data adjustments."""
    try:
        from .analysis.layer_live_adjustments import apply_live_adjustments
        scores.update(apply_live_adjustments(sector, scores))
    except Exception:
        pass


# ═══════════════════════════════════════
# Public API
# ═══════════════════════════════════════

def run_full(code: str, live: bool = True, profile: str = "均衡") -> dict:
    """Run full 30+ layer penetration pipeline for a single ETF code."""
    etfs = load_etfs()
    info = etfs.get(code, {})
    if not info:
        return {"etf_code": code, "error": "ETF not found", "layer_scores": {}}

    rl = info.get("risk_level", 0.5)
    sector = info.get("sector", "未知行业")
    name = info.get("name", code)

    # Step 1: Initialize base scores
    scores = _init_base_scores(rl, profile)
    layer_details: dict = {}

    # Step 2: Bridge layers (material, sector, multi-signal, L2 holdings)
    scores = _apply_material_bridge(scores, code, sector)
    _apply_sector_scores(scores, sector, rl)
    _apply_live_material_fusion(scores, code, sector, live)
    _apply_multi_signal(scores, code, sector, info)
    _apply_l2_holdings(scores, code, sector, rl, info.get("fee", 0.005))

    # Step 3: Demand + macro climate
    _apply_demand(scores, sector, rl)
    _apply_macro_climate(scores, sector)

    # Step 4: Chain risk penalty
    _apply_chain_penalty(scores, code)

    # Step 5: REMOVED — material_bridge second pass was double-applying adjustments.
    # apply_to_layers() is INCREMENTAL (layer_scores[layer] = old + adj), so calling it
    # twice (Step 2 + Step 5) doubled L3-L7 adjustments (e.g. L4 7.2→9.9, L6 3.5→2.5).
    # Single application in Step 2 is correct.

    # Step 6: Live data adjustments
    _run_live_adjustments(scores, sector)

    # Step 7: Soft floor
    _apply_soft_floor(scores)

    # Step 8: Sector flow bridge (L8/L9)
    _apply_sector_flow(scores, info, rl, code, sector, live=live)

    # Step 9: Layers L12-L15
    _apply_l12_political_risk(scores, sector)
    cycle_info = _apply_l13_macro_cycle(scores, sector, rl)
    _apply_factor_momentum(scores, sector)
    _apply_stoic_risk(scores, sector, rl)
    _apply_state_similarity(scores, sector)

    # Step 10: L16 Live Signals
    is_cross = "QDII" in info.get("type", "") or info.get("access") == "qdii"
    _apply_live_signals(scores, sector, is_cross)

    # Step 11: Layers L17-L20
    _apply_quantitative_factor(scores, sector)
    _apply_var_risk(scores, sector)
    _apply_fx_channel(scores, sector, info.get("type", ""))
    _apply_option_volatility(scores, sector)

    # Step 12: Layers L21-L24 + L33 + L25-L27 (KB-driven)
    _apply_behavioral_psychology(scores, layer_details, sector, rl)
    _apply_pendulum(scores, layer_details, sector, rl, code=code)
    _apply_valuation(scores, layer_details, code, sector, name, rl)
    _apply_microstructure(scores, layer_details, sector, rl, code=code)
    _apply_dip_flow(scores, layer_details, code, sector, rl, live=live)
    _apply_system_dynamics(scores, layer_details, sector, rl, code)
    _apply_regime_factor(scores, layer_details, sector, code)
    _apply_kb_catalyst(scores, layer_details, sector)
    _apply_liquidity_arbitrage(scores, layer_details, info.get("type", ""), sector)
    _apply_volatility_regime(scores, layer_details, sector, code=code)
    _apply_factor_smart_beta(scores, layer_details, sector, regime=cycle_info.get("regime", "sideways"))
    _apply_l30_layer(scores, layer_details, sector, rl, code)

    # Step 13: Enhancements
    _enhance_news(scores, code, layer_details, sector)
    if live:
        _enhance_realtime(scores, code)

    # Step 14: Build result
    return _build_result(code, name, sector, info, rl, scores, cycle_info, profile, layer_details)


def format_full(result: dict) -> str:
    """Format full pipeline layers as text report."""
    code = result.get("etf_code", "?")
    name = result.get("name", code)
    sector = result.get("sector", "?")
    scores = result.get("layer_scores", {})
    lines = [
        f"ETF: {code} {name}",
        f"Sector: {sector} | Risk: {result.get('risk_level', '?')}",
        f"Composite: {result.get('composite_score', result.get('score', 0)):.2f}/10",
        "-" * 40,
    ]
    for k, v in sorted(scores.items()):
        lines.append(f"  {k}: {v}")
    return "\n".join(lines)


def batch_full(limit: int = 50, sort_by: str = "score", codes: list = None,
               live: bool = False, profile: str = "均衡",
               skip_tournament: bool = True, parallel: bool = False,
               max_workers: int = 6) -> list:
    """Batch run for multiple ETFs with full 30+ layer pipeline.
    
    Args:
        parallel: If True, run ETFs concurrently via ThreadPoolExecutor.
        max_workers: Max concurrent pipeline runs (default 6, safe for HTTP-bound layers).
    """
    etfs = load_etfs()
    if codes:
        target = codes
    else:
        target = [c for c in etfs if c.isdigit()][:limit]

    def _run_one(code: str) -> dict:
        try:
            return run_full(code, live=live, profile=profile)
        except Exception:
            return {"etf_code": code, "error": "pipeline_failed", "layer_scores": {}}

    if parallel and len(target) > 3:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        results = []
        with ThreadPoolExecutor(max_workers=min(max_workers, len(target))) as ex:
            futures = {ex.submit(_run_one, code): code for code in target}
            for f in as_completed(futures):
                r = f.result()
                if not r.get("error"):
                    results.append(r)
    else:
        results = [_run_one(code) for code in target]

    if sort_by == "score":
        results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return results
