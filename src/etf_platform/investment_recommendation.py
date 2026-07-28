"""Investment recommendation engine — KB + Penetration + News fusion."""
import sys
import json
import time
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parent.parent.parent  # etf-platform root (from src/etf_platform/X.py)
sys.path.insert(0, str(BASE / "src"))

SCORING_WEIGHTS = {
    "kb_signal": 0.15,
    "news_sentiment": 0.10,
    "capital_flow": 0.12,
    "live_signals": 0.08,
    "factor_score": 0.08,
    "political_risk": 0.08,
    "macro_cycle": 0.08,
    "tech_layer": 0.07,
    "supply_chain": 0.06,
    "material_risk": 0.04,
    "var_risk": 0.06,
    "technical_score": 0.06,
    "l33_regime": 0.05,
    "l25_liquidity": 0.03,
    "l26_vol_regime": 0.03,
    "l27_factor_beta": 0.03,
}

SECTOR_NEWS_BIAS = {
    "半导体": -2.0, "AI算力": -2.0, "军工": 1.5, "医药": 2.0,
    "新能源": 0.0, "消费": 0.0, "金融": 1.5, "能源化工": 2.0,
    "贵金属": 0.0, "有色金属": 1.5, "红利价值": 1.5,
    "通信5G": 0.0, "基建地产": -2.0, "稀土": 1.5,
}
# v2.0: 行业别名映射 — pipeline sector name → news_sentiment key
SECTOR_ALIASES = {
    "AI/科技": "AI算力", "AI/半导体": "半导体", "半导体设备": "半导体",
    "医药生物": "医药", "红利/价值": "红利价值", "能源": "能源化工",
    "通信": "通信5G", "国防军工": "军工", "基建": "基建地产",
}


def load_kb_signals():
    """Load KB signals, filtering out zero-value impact_scores rows."""
    sig_file = BASE / "data" / "news_etf_signals.json"
    if not sig_file.exists():
        print(f"[WARN] Missing: {sig_file}")
        return {}
    try:
        raw = json.loads(sig_file.read_text(encoding="utf-8"))
        filtered = {}
        for code, data in raw.items():
            if not isinstance(data, dict):
                continue
            total = data.get("total_events", 0)
            if total > 0:
                filtered[code] = data
        print(f"[INFO] KB signals loaded: {len(filtered)} directional entries")
        return filtered
    except Exception as e:
        print(f"[ERROR] Failed to load KB signals: {e}")
        return {}


def load_news_sentiment():
    """Load cron-generated sector sentiment."""
    sent_file = BASE / "data" / "news_sentiment.json"
    if not sent_file.exists():
        print(f"[WARN] Missing: {sent_file}")
        return {}
    try:
        data = json.loads(sent_file.read_text(encoding="utf-8"))
        sectors = data.get("sectors", {})
        print(f"[INFO] News sentiment loaded: {len(sectors)} sectors ({data.get('updated', '?')})")
        return sectors
    except Exception as e:
        print(f"[ERROR] Failed to load news sentiment: {e}")
        return {}


def compute_l33_factor(sector: str) -> float:
    """L33_RegimeFactor 因子对齐分 (0-10)。最小集成：只取score字段。"""
    try:
        from etf_platform.layers.l33_regime_factor import RegimeFactorLayer
        layer = RegimeFactorLayer()
        return layer.factor_alignment_score(sector)
    except (ImportError, AttributeError):
        return 5.0


def load_kb_momentum_signals():
    """Load KB sector momentum + capital flow + institutional views (k130+k131)。"""
    try:
        from etf_platform.analysis.kb_sector_momentum import (
            KBSectorMomentum, H1_2026_PERFORMANCE, CAPITAL_FLOW_INDEX,
        )
        kb = KBSectorMomentum()
        return {
            "kb_momentum": kb,
            "capital_flow_context": kb.get_capital_flow_context(),
            "institutional_bias": kb.get_institutional_bias(),
            "k128_cycle_anchor": kb.get_k128_cycle_anchor(),
            "fund_manager_themes": H1_2026_PERFORMANCE.get("fund_manager_consensus_themes", []),
            "capital_flow_summary": CAPITAL_FLOW_INDEX["interpretation"],
        }
    except Exception as e:
        print(f"[WARN] Failed to load KB momentum signals: {e}")
        return {"kb_momentum": None, "capital_flow_context": {}, "institutional_bias": {},
                "k128_cycle_anchor": {}, "fund_manager_themes": [], "capital_flow_summary": ""}


def compute_kb_factor(etf_code: str, kb_signals: dict) -> float:
    if not kb_signals or etf_code not in kb_signals:
        return 5.0
    signal = kb_signals[etf_code]
    direction = signal.get("direction", "中性")
    bull = signal.get("bullish", 0)
    bear = signal.get("bearish", 0)
    total = bull + bear
    if total == 0:
        return 5.0
    if direction == "看多":
        return round(min(10.0, 5.0 + bull / max(total, 1) * 5.0), 2)
    elif direction == "看空":
        return round(max(0.0, 5.0 - bear / max(total, 1) * 5.0), 2)
    return 5.0


def _normalize_sector_name(name: str) -> str:
    """标准化行业名：去掉标点符号后匹配"""
    return name.replace("/", "").replace("、", "").replace("·", "").replace(" ", "").replace("_", "")


def compute_news_bias(sector: str, sentiment: dict) -> float:
    # v2.0: 别名映射 → 统一到 news_sentiment 标准 key
    sector = SECTOR_ALIASES.get(sector, sector)
    # 1. 从 news_sentiment.json 获取动态信号（模糊匹配）
    if sentiment:
        sectors_in_sentiment = list(sentiment.keys())
        norm_sector = _normalize_sector_name(sector)
        # 精确匹配
        if norm_sector in sectors_in_sentiment:
            s = sentiment[norm_sector]
            direction = s.get("direction", "")
            strength = s.get("strength", "中")
            if direction == "看多":
                return round(1.5 if strength != "强" else 2.5, 2)
            elif direction == "看空":
                return round(-1.5 if strength != "强" else -2.5, 2)
            return 0.0
        # 模糊匹配：pipeline sector 含 sentiment key 或反之
        for key in sectors_in_sentiment:
            if key in norm_sector or norm_sector in key:
                s = sentiment[key]
                direction = s.get("direction", "")
                strength = s.get("strength", "中")
                if direction == "看多":
                    return round(1.5 if strength != "强" else 2.5, 2)
                elif direction == "看空":
                    return round(-1.5 if strength != "强" else -2.5, 2)
    # 2. 回退到静态字典
    bias = SECTOR_NEWS_BIAS.get(sector, 0.0)
    return round(bias, 2)


def compute_penetration_composite(pipe_result: dict) -> float:
    ls = pipe_result.get("layer_scores", {})
    keys = [
        "L8_CapitalFlow", "L9_Signals", "L16_LiveSignals", "L17_Factor",
        "L12_PoliticalRisk", "L13_MacroCycle", "L5_Tech", "L4_SupplyChain",
        "L3_Material", "L18_VaR",
    ]
    vals = [ls.get(k, 5.0) for k in keys if ls.get(k, 5.0) is not None and ls.get(k, 5.0) >= 0]
    return sum(vals) / len(vals) if vals else 5.0


def compute_var_penalty(pipe_result: dict) -> float:
    var = pipe_result.get("layer_scores", {}).get("L18_VaR", 5.0)
    if var is None or var < 0:
        var = 5.0
    return round(max(0.0, (var - 5.0) * 0.5), 2)


def compute_macro_match(sector: str) -> dict:
    """Get macro overlay context from UIDF v2.0 (knowledge-driven)."""
    try:
        from etf_platform.analysis.macro_overlay import get_overlay, get_macro_context
        overlay = get_overlay(sector)
        ctx = get_macro_context()
        return {
            "macro_regime": ctx["regime"],
            "macro_position_center": ctx["position_center"],
            "asset_layer": overlay["asset_layer"],
            "macro_boost": overlay["total_boost"],
            "rotation": overlay["rotation"],
            "catalyst": overlay["catalyst"],
            "earnings_season": overlay["earnings_phase"],
            "catalyst_event": overlay["catalyst_event"],
        }
    except (KeyError, TypeError, ValueError):
        return {
            "macro_regime": "未知",
            "asset_layer": "未分类",
            "macro_boost": 0.0,
            "earnings_season": "",
        }


def compute_unified_score(
    etf_code: str, sector: str, pipe_result: dict, trend,
    kb_signals: dict, sentiment: dict, kb_momentum: dict | None = None,
) -> dict:
    kb_raw = compute_kb_factor(etf_code, kb_signals)
    news_bias = compute_news_bias(sector, sentiment)
    pen_comp = compute_penetration_composite(pipe_result)
    var_pen = compute_var_penalty(pipe_result)

    # L33: prefer pipeline-injected layer score, fallback to direct computation
    l33_raw = (
        pipe_result.get("layer_scores", {}).get("L33_RegimeFactor", 5.0)
        or compute_l33_factor(sector)
    )
    l33_detail = pipe_result.get("layer_scores", {}).get("L33_Detail", {})

    # L34: KB Catalyst layer — 知识库催化剂信号
    l34_raw = pipe_result.get("layer_scores", {}).get("L34_KBCatalyst", 5.0)
    l34_detail = pipe_result.get("layer_details", {}).get("L34_CatalystDetail", {})

    # L25-L27: KB-driven enhanced layers
    l25_raw = pipe_result.get("layer_scores", {}).get("L25_LiquidityArb", 5.0)
    l26_raw = pipe_result.get("layer_scores", {}).get("L26_VolRegime", 5.0)
    l27_raw = pipe_result.get("layer_scores", {}).get("L27_FactorBeta", 5.0)

    raw_final = (
        kb_raw * SCORING_WEIGHTS["kb_signal"]
        + (5.0 + news_bias) * SCORING_WEIGHTS["news_sentiment"]
        + pen_comp * 0.60
        + (5.0 - var_pen) * SCORING_WEIGHTS["var_risk"]
        + l33_raw * SCORING_WEIGHTS["l33_regime"]
        + l34_raw * 0.08
        + l25_raw * SCORING_WEIGHTS["l25_liquidity"]
        + l26_raw * SCORING_WEIGHTS["l26_vol_regime"]
        + l27_raw * SCORING_WEIGHTS["l27_factor_beta"]
    )
    final = round(max(0.0, min(10.0, raw_final)), 2)
    risk_adjusted = round(final, 2)
    # v2.0: 负收益惩罚 — volatility_adjusted_return<0 降分
    va_ret = trend.change_20d / max(trend.volatility_20d, 1) if trend else 0
    if va_ret < 0:
        risk_adjusted = round(final * max(0.3, 1 + va_ret * 2), 2)

    active_layers = sum(
        1 for v in pipe_result.get("layer_scores", {}).values()
        if v is not None and v != 5.0 and v != 0.0
    )

    # v2.0: UIDF macro context from knowledge base
    macro = compute_macro_match(sector)

    return {
        "code": etf_code,
        "name": pipe_result.get("name", etf_code),
        "sector": sector,
        "asset_layer": macro["asset_layer"],
        "final_score": final,
        "risk_adjusted_score": risk_adjusted,
        "kb_signal": kb_raw,
        "news_bias": news_bias,
        "penetration_composite": round(pen_comp, 2),
        "var_penalty": var_pen,
        "pipeline_score": pipe_result.get("score", 5.0),
        "layers_active": active_layers,
        "change_20d": round(trend.change_20d, 1) if trend else 0,
        "volatility_20d": round(trend.volatility_20d, 1) if trend else 0,
        "volatility_adjusted_return": round(
            trend.change_20d / max(trend.volatility_20d, 1), 2
        ) if trend else 0,
        "macro_boost": macro["macro_boost"],
        "macro_regime": macro["macro_regime"],
        "catalyst_event": macro["catalyst_event"],
        "earnings_season": macro["earnings_season"],
        # L33: regime-factor alignment signal (新增)
        "l33_alignment": round(l33_raw, 1),
        "l33_regime": l33_detail.get("regime", "normal"),
        "l33_overallocate": l33_detail.get("overallocate_factors", []),
        "l33_underallocate": l33_detail.get("underallocate_factors", []),
        # L34: KB Catalyst layer (新增)
        "l34_score": round(l34_raw, 1),
        "l34_detail": {**l34_detail, "score": round(l34_raw, 1)},
        "l34_catalysts": l34_detail.get("catalysts", []),
        "l34_risks": l34_detail.get("risks", []),
        "l34_kb_depth": l34_detail.get("kb_depth", 0),
        # L4 KB deep layer (新增)
        "layer4_score": 5.0,
        "layer4_components": {},
        # KB动量信号: 资金流上下文 + 基金经理共识主题 (新增)
        "capital_flow_context": kb_momentum.get("capital_flow_context", {}) if kb_momentum else {},
        "fund_manager_themes": kb_momentum.get("fund_manager_themes", []) if kb_momentum else [],
    }


def _prefilter_candidates(etfs: dict, n: int = 24, sentiment: dict | None = None,
                          kb_momentum: dict | None = None) -> list[dict]:
    """Cheap prefilter: L34 catalyst + KB momentum + news bias → top N candidates.
    
    Avoids running 600 full pipelines. Pure KB/static data, no HTTP.
    Target: 592 → ~24, so full pipeline stage < 120s.
    24 candidates prevents over-filtering sectors with low prefilter scores
    but high pipeline scores (e.g. 医药 pipeline=5.8 but prefilter=4.94).
    
    Scoring: L34 catalyst dominant (0.70), momentum as opportunity signal (0.20),
    news bias secondary (0.10). Per-sector cap prevents 红利/价值垄断.
    L34 scores are cached per sector to avoid 592 redundant computations.
    """
    from etf_platform.layers.l34_kb_catalyst import score_l34_layer
    from etf_platform.analysis.kb_sector_momentum import KBSectorMomentum
    
    km = KBSectorMomentum()
    sentiment = sentiment if sentiment is not None else load_news_sentiment()
    if kb_momentum is None:
        kb_momentum = load_kb_momentum_signals()
    themes = kb_momentum.get("fund_manager_themes", []) if isinstance(kb_momentum, dict) else []
    
    wide_kw = ["沪深300", "中证500", "创业板", "科创50", "科创100", "宽基"]
    bond_kw = ["货币", "利率债", "信用债", "债券"]
    
    l34_cache: dict[str, float] = {}
    candidates = []
    for code, info in etfs.items():
        if info.get("access") and info["access"] != "buyable":
            continue
        name = info.get("name", "")
        sector = info.get("sector", "")
        if any(kw in name for kw in wide_kw) or any(kw in sector for kw in bond_kw):
            continue
        
        if sector not in l34_cache:
            l34_cache[sector] = score_l34_layer(sector).get("score", 5.0)
        l34 = l34_cache[sector]
        mom = km.get_sector_kline_signal(sector)
        mom_bias = mom.get("kline_score_bias", 0.0)
        news = compute_news_bias(sector, sentiment)
        theme_bonus = 1.0 if any(t.split("（")[0].split("(")[0].strip() in sector for t in themes) else 0.0
        
        # Momentum as opportunity: deep correction = left-side opportunity, not penalty
        mom_opportunity = min(2.0, abs(mom_bias) * 0.4) if mom_bias < -2.0 else max(0.0, mom_bias * 0.3)
        
        pre_score = l34 * 0.70 + mom_opportunity + news * 0.10 + theme_bonus
        candidates.append({
            "code": code, "sector": sector, "name": name,
            "prefilter_score": round(pre_score, 2),
        })
    
    candidates.sort(key=lambda x: -x["prefilter_score"])
    
    # Per-sector cap: max 3 ETFs per sector, then fill remaining slots
    sector_count = {}
    filtered = []
    for c in candidates:
        sec = c["sector"]
        sector_count[sec] = sector_count.get(sec, 0) + 1
        if sector_count[sec] <= 3:
            filtered.append(c)
        if len(filtered) >= n:
            break
    
    return filtered[:n]


def recommend_top_n(n: int = 3, profile: str = "均衡", max_candidates: int = 24) -> dict:
    t0 = time.time()

    kb_signals = load_kb_signals()
    sentiment = load_news_sentiment()
    kb_momentum = load_kb_momentum_signals()

    from etf_platform.pipeline import batch_full, load_etfs
    from etf_platform.data.kline import get_trend_batch

    # Two-stage prefilter: 600→~24 via cheap KB signals, then full pipeline on shortlist
    etfs = load_etfs()
    
    prefiltered = _prefilter_candidates(etfs, n=max_candidates, sentiment=sentiment, kb_momentum=kb_momentum)
    shortlist_codes = [c["code"] for c in prefiltered]
    print(f"[recommend] Prefilter: {len(etfs)} → {len(shortlist_codes)} candidates")

    # Run pipeline + trend in parallel since they're independent
    from concurrent.futures import ThreadPoolExecutor
    
    pipe_results = []
    trends = {}
    with ThreadPoolExecutor(max_workers=2) as ex:
        f_pipe = ex.submit(batch_full, limit=max_candidates, live=False, profile=profile,
                           codes=shortlist_codes, parallel=True, max_workers=8)
        f_trend = ex.submit(get_trend_batch, shortlist_codes, parallel=True, max_workers=8)
        pipe_results = f_pipe.result()
        trends = f_trend.result()
    
    scored = []
    for result in pipe_results:
        code = result.get("etf_code", "")
        sector = result.get("sector", "")
        name = result.get("name", "")

        # Filter wide-base ETFs
        if any(kw in name for kw in ["沪深300", "中证500", "创业板", "科创50", "科创100", "宽基"]):
            continue
        if any(kw in sector for kw in ["货币", "利率债", "信用债", "债券"]):
            continue

        trend = trends.get(code)
        if trend is None or trend.data_days < 10:
            continue

        score_data = compute_unified_score(
            etf_code=code,
            sector=sector,
            pipe_result=result,
            trend=trend,
            kb_signals=kb_signals,
            sentiment=sentiment,
            kb_momentum=kb_momentum,
        )
        scored.append(score_data)

    scored.sort(key=lambda x: -x["risk_adjusted_score"])

    seen_sectors = set()
    top = []
    for item in scored:
        if item["sector"] not in seen_sectors:
            top.append(item)
            seen_sectors.add(item["sector"])
        if len(top) >= n:
            break

    elapsed = time.time() - t0

    return {
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "elapsed_seconds": round(elapsed, 2),
        "total_evaluated": len(scored),
        "prefilter_candidates": len(shortlist_codes),
        "top_n_results": top,
        "scoring_weights": SCORING_WEIGHTS,
    }


def format_report(report: dict):
    top = report.get("top_n_results", [])
    print(f"\n{'='*60}")
    print(f"ETF Investment Recommendations — Top {len(top)}")
    print(f"{'='*60}\n")

    for i, item in enumerate(top, 1):
        dir_word = "看多" if item['news_bias'] > 0 else "看空" if item['news_bias'] < 0 else "中性"
        layer_icon = {"防御核心": "🛡️", "周期进攻": "⚔️", "成长弹性": "🚀"}.get(item.get("asset_layer", ""), "📊")
        print(f"[{i}] {item['name']} ({item['code']}) {layer_icon}")
        print(f"    行业: {item['sector']} | 资产层: {item.get('asset_layer','?')} | 宏观: {item.get('macro_boost','?'):+.2f}")
        print(f"    综合分: {item['risk_adjusted_score']:.2f}/10")
        print(f"    穿透面: Pipeline={item['pipeline_score']:.2f}, 活跃层={item['layers_active']}, 组合={item['penetration_composite']:.2f}")
        print(f"    KB面: L9信号={item['kb_signal']:.2f}/10")
        print(f"    新闻面: {item['news_bias']:+.1f} ({dir_word})")
        print(f"    K线面: 20d={item['change_20d']:+.1f}%, Vol={item['volatility_20d']:.1f}%, 波动调整收益={item['volatility_adjusted_return']:+.2f}")
        print(f"    L33制度适配: {item.get('l33_alignment', '?'):.1f}/10 (regime={item.get('l33_regime','?')})")
        if item.get('catalyst_event'):
            print(f"    催化剂: {item['catalyst_event']}")
        # k128 基金经理共识主题补充展示
        themes = item.get("fund_manager_themes", [])
        if themes:
            print(f"    催化剂补充: {', '.join(themes[:3])}")
        # 资金流语境
        cfc = item.get("capital_flow_context", {})
        if cfc:
            week_net = cfc.get("week_net_inflow_yi", 0)
            narrative = cfc.get("narrative", "")
            print(f"    资金流: 周净流入 {week_net:.0f}亿 | {narrative}")
        print()

    # Print macro context summary
    macro_regime = top[0].get('macro_regime', '') if top else ''
    print(f"📌 宏观判官 (UIDF): {macro_regime}")
    print(f"⏱️ Total time: {report.get('elapsed_seconds', 0):.2f}s | Evaluated: {report.get('total_evaluated', 0)} ETFs")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="ETF Investment Recommendation Engine")
    parser.add_argument("--top3", action="store_true")
    parser.add_argument("--top5", action="store_true")
    parser.add_argument("--etf", type=str)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--max-candidates", type=int, default=24)
    args = parser.parse_args()

    if args.etf:
        from etf_platform.pipeline import run_full
        from etf_platform.data.kline import get_trend

        pipe = run_full(args.etf, live=False)
        trend = get_trend(args.etf)
        kb = load_kb_signals()
        sent = load_news_sentiment()
        kb_mom = load_kb_momentum_signals()
        result = compute_unified_score(
            etf_code=args.etf, sector=pipe.get("sector", ""),
            pipe_result=pipe, trend=trend, kb_signals=kb, sentiment=sent,
            kb_momentum=kb_mom,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if args.top3 and args.top5:
            print("[WARN] --top3 and --top5 both set; using --top3")
        n = 3 if args.top3 else 5 if args.top5 else 3
        
        if args.json:
            import io
            from contextlib import redirect_stdout
            buf = io.StringIO()
            with redirect_stdout(buf):
                report = recommend_top_n(n=n, max_candidates=args.max_candidates)
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            report = recommend_top_n(n=n, max_candidates=args.max_candidates)
            format_report(report)
