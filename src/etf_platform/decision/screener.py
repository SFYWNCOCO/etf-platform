"""ETF screener: scan all buyable ETFs, rank by composite score, output top N."""
import time
import json
from pathlib import Path
from typing import List, Dict, Optional

# v5.5: Module-level import to avoid NameError when invoked outside package context
try:
    from ..config_loader import load_etfs
except ImportError:
    load_etfs = None  # Fallback: only callable via CLI path

# Layer categories for auto-weighting
LAYER_CATEGORIES = {
    "供给侧": ["L3_Material", "L4_SupplyChain", "L5_Tech", "L6_Politics", "L7_Irreplaceable"],
    "资金面": ["L8_CapitalFlow"],
    "信号面": ["L9_Signals"],
    "需求面": ["L10_Demand", "L11_SectorRisk"],
}

# v5.5: L2 now has holdings data via l2_holdings_bridge
EXCLUDED_LAYERS = {"L1_ETF"}

CATEGORY_WEIGHTS = {
    "保守": {"供给侧": 0.45, "资金面": 0.10, "信号面": 0.05, "需求面": 0.40},
    "均衡": {"供给侧": 0.35, "资金面": 0.25, "信号面": 0.10, "需求面": 0.30},
    "进取": {"供给侧": 0.20, "资金面": 0.40, "信号面": 0.20, "需求面": 0.20},
    "激进": {"供给侧": 0.15, "资金面": 0.45, "信号面": 0.25, "需求面": 0.15},
}

PROFILE_ALIASES = {
    "conservative": "保守", "defensive": "保守",
    "balanced": "均衡",
    "aggressive": "进取",
    "激进": "激进", "激进型": "激进",
    "进攻": "激进",
}

def _resolve_profile(profile: str) -> str:
    return PROFILE_ALIASES.get(profile, profile)

TREND_ICONS = {"oversold":"🟢超卖","weak":"🟡回调","neutral":"⚪中性","strong":"🟡强势","overbought":"🔴超买","plunging":"🔴急跌","surging":"🟢急涨"}
LN = {"L3_Material":"材料","L4_SupplyChain":"物流","L5_Tech":"技术","L6_Politics":"政治","L7_Irreplaceable":"替代","L8_CapitalFlow":"资金","L9_Signals":"信号","L10_Demand":"需求","L11_SectorRisk":"行业风险"}

# v5.6: l003 knowledge-base integration
# Penetration score IS a risk metric, NOT a return metric (per l003 + correction #30)
# High score (>7) = safe but zero alpha; Low score (<4) = high catalyst elasticity
NON_INVESTMENT_SECTORS = {"货币基金", "货币", "利率债", "信用债", "债券", "国债"}
RISK_SAFE_THRESHOLD = 7.0
RISK_ELASTIC_THRESHOLD = 4.0


def _detect_dead_layers(results: list) -> set:
    """Detect layers with zero variance across batch. These should be excluded."""
    layer_vals = {}
    for r in results:
        scores = r.get("layer_scores", {}) if isinstance(r, dict) else {}
        for layer, score in scores.items():
            if isinstance(score, (int, float)) and layer not in EXCLUDED_LAYERS:
                layer_vals.setdefault(layer, []).append(score)
    dead = set()
    for layer, vals in layer_vals.items():
        if len(vals) < 2:
            dead.add(layer)
        elif max(vals) - min(vals) < 0.5:  # Less than 0.5 range = effectively dead
            dead.add(layer)
    return dead

def _compute_auto_weights(results: list, profile: str = "均衡", dead_layers: set = None) -> Dict[str, float]:
    """Compute weights: higher variance = higher weight. Exclude dead layers.
    v5.5: weight hard caps 3%-22%, CV<0.03 excluded from category distribution."""
    import statistics
    if dead_layers is None:
        dead_layers = set()
    MIN_CV_THRESHOLD = 0.03
    layer_scores = {}
    for r in results:
        scores = r.get("layer_scores", {}) if isinstance(r, dict) else {}
        for layer, score in scores.items():
            if isinstance(score, (int, float)) and layer not in EXCLUDED_LAYERS:
                layer_scores.setdefault(layer, []).append(score)
    layer_cv = {}
    for layer, scores in layer_scores.items():
        if layer in dead_layers:
            continue
        if len(scores) > 1 and max(scores) > min(scores):
            mean = statistics.mean(scores)
            if mean > 0:
                cv = statistics.stdev(scores) / mean
            else:
                cv = 0.1
        else:
            cv = 0.05
        layer_cv[layer] = cv
    adjusted_cv = {}
    for layer, cv in layer_cv.items():
        if cv > 0.25:
            adjusted_cv[layer] = cv * 1.2
        elif cv > 0.15:
            adjusted_cv[layer] = cv * 1.1
        elif cv < MIN_CV_THRESHOLD:
            adjusted_cv[layer] = 0
        elif cv < 0.05:
            adjusted_cv[layer] = cv * 0.2
        elif cv < 0.08:
            adjusted_cv[layer] = cv * 0.5
        else:
            adjusted_cv[layer] = cv
    resolved = _resolve_profile(profile)
    cat_weights = CATEGORY_WEIGHTS.get(resolved, CATEGORY_WEIGHTS["均衡"])
    weights = {}
    for cat, layers in LAYER_CATEGORIES.items():
        cat_w = cat_weights.get(cat, 0)
        eligible = [l for l in layers if l in adjusted_cv and adjusted_cv[l] > 0]
        if not eligible:
            continue
        total_adj = sum(adjusted_cv[l] for l in eligible)
        if total_adj > 0:
            for layer in eligible:
                weights[layer] = round(cat_w * (adjusted_cv[layer] / total_adj), 4)
        else:
            for layer in eligible:
                weights[layer] = round(cat_w / len(eligible), 4)
    MIN_W = 0.03
    MAX_W = 0.22
    capped = {}
    for k, v in weights.items():
        capped[k] = max(MIN_W, min(MAX_W, v))
    total = sum(capped.values())
    if total > 0:
        weights = {k: round(v / total, 4) for k, v in capped.items()}
    else:
        weights = capped
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
def _compute_composite(scores: dict, weights: dict, trend: dict = None) -> float:
    """Weighted composite with trend penalty, excluding dead layers."""
    total = 0.0
    ws = 0.0
    for layer, weight in weights.items():
        score = scores.get(layer)
        if score is not None and isinstance(score, (int, float)):
            total += score * weight
            ws += weight
    base = round(total / max(ws, 0.01), 2) if ws > 0 else 0
    # v5.4: 趋势惩罚 — 超卖/急跌信号扣分，防止推荐下跌趋势ETF
    if trend:
        sig = trend.get("signal", "")
        dd = trend.get("max_drawdown", 0)
        penalty = 0.0
        # v5.4: 乘法惩罚 — 趋势信号对评分直接打折
        trend_mult = 1.0
        # v5.5: Optimized via grid search (729 combos, Sharpe 0.027->0.031)
        if sig in ("oversold", "超卖"):
            trend_mult = 0.70   # 超卖: 打7折
        elif sig in ("plunging", "急跌"):
            trend_mult = 0.55   # 急跌: 打55折 (grid-search最优)
        elif sig in ("overbought", "超买"):
            trend_mult = 0.85   # 超买: 打85折
        elif sig in ("weak", "回调"):
            trend_mult = 0.90   # 弱势/回调: 轻微打折
        # 回撤加法惩罚 (叠加在乘法后)
        dd_penalty = 0.0
        if dd < -25:
            dd_penalty = 1.5   # grid-search最优
        elif dd < -20:
            dd_penalty = 1.5
        elif dd < -15:
            dd_penalty = 1.0
        elif dd < -10:
            dd_penalty = 0.5
        base = max(0, base * trend_mult - dd_penalty)
    return base



def _premium_penalty(code: str, spot_df=None) -> dict:
    """获取ETF折溢价率并计算评分惩罚.
    
    基于l005知识库-信号一: ETF折溢价均值回归
    优先用IOPV实时计算(盘中), 回退到日末折价率(盘后).
    """
    try:
        import akshare as ak
        
        # 方法1: 用IOPV实时计算折溢价(盘中可用)
        try:
            spot = spot_df if spot_df is not None else ak.fund_etf_spot_em()
            row = spot[spot["代码"] == code]
            if not row.empty:
                r = row.iloc[0]
                price = float(r.get("最新价", 0) or 0)
                iopv = r.get("IOPV实时估值", None)
                if iopv and float(iopv) > 0:
                    premium = (price / float(iopv) - 1) * 100
                else:
                    # 回退到日末数据
                    df = ak.fund_etf_fund_daily_em()
                    frow = df[df["基金代码"] == code]
                    if not frow.empty:
                        raw = frow.iloc[0].get("折价率", 0)
                        try:
                            premium = float(raw) if raw not in (None, "---", "") else 0.0
                        except (ValueError, TypeError):
                            premium = 0.0
                    else:
                        return {"premium_pct": 0, "penalty": 0, "signal": "no_data"}
            else:
                return {"premium_pct": 0, "penalty": 0, "signal": "no_data"}
        except Exception:
            return {"premium_pct": 0, "penalty": 0, "signal": "no_data"}
        
        if premium < -2.0:
            penalty = +0.8
            signal = "discount_buy"
        elif premium < -1.0:
            penalty = +0.3
            signal = "discount_light"
        elif premium > 3.0:
            penalty = -2.0
            signal = "premium_avoid"
        elif premium > 2.0:
            penalty = -1.0
            signal = "premium_high"
        elif premium > 1.0:
            penalty = -0.3
            signal = "premium_light"
        else:
            penalty = 0
            signal = "normal"
        
        return {"premium_pct": round(premium, 2), "penalty": penalty, "signal": signal}
    except Exception:
        return {"premium_pct": 0, "penalty": 0, "signal": "error"}

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


CHUNK_SIZE = 50
MAX_RETRIES = 2


def _batch_with_retry(limit: int, checkpoint_file: Path, profile: str = "均衡") -> list:
    """分批扫描 + 断点续扫 + 失败重试."""
    from ..pipeline import batch_full
    from ..config_loader import load_etfs

    # Load checkpoint
    done_codes = set()
    results_so_far = []
    if checkpoint_file.exists():
        try:
            with open(checkpoint_file, "r", encoding="utf-8") as f:
                ck = json.load(f)
                done_codes = set(ck.get("done_codes", []))
                results_so_far = ck.get("results", [])
                print(f"  📌 断点续扫: {len(done_codes)}只已完成")
        except:
            done_codes = set()
            results_so_far = []

    all_codes = list(load_etfs().keys())
    all_codes = [c for c in all_codes if c.isdigit()][:limit]
    remaining = [c for c in all_codes if c not in done_codes]

    for i in range(0, len(remaining), CHUNK_SIZE):
        chunk = remaining[i:i + CHUNK_SIZE]
        for attempt in range(MAX_RETRIES):
            try:
                chunk_results = batch_full(codes=chunk, live=False, profile=profile)
                if chunk_results:
                    results_so_far.extend(chunk_results)
                    done_codes.update(r.get("etf_code", "") for r in chunk_results)
                    # Save checkpoint
                    checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(checkpoint_file, "w", encoding="utf-8") as f:
                        json.dump({"done_codes": list(done_codes), "results": results_so_far}, f, ensure_ascii=False)
                    print(f"    ✓ {min(i + CHUNK_SIZE, len(remaining))}/{len(remaining)} ({len(results_so_far)}只) "
                          f"[{len(chunk_results)} in chunk]")
                    break
                else:
                    print(f"    ⚠ chunk returned empty (attempt {attempt+1})")
            except Exception as e:
                print(f"    ✗ chunk failed (attempt {attempt+1}): {str(e)[:80]}")
                if attempt >= MAX_RETRIES - 1:
                    print(f"    ✗ chunk {i//CHUNK_SIZE+1} failed after {MAX_RETRIES} retries, continuing...")
                else:
                    time.sleep(1.5)

    return results_so_far


# v5.5: Liquidity filter - exclude ETFs with daily volume < 10M
_MIN_DAILY_AMOUNT = 10000000
_liquidity_cache = {"data": None, "ts": 0}
_LIQUIDITY_CACHE_TTL = 3600

def _get_liquid_codes(etf_dict):
    import time as _time
    global _liquidity_cache
    if _liquidity_cache["data"] is not None and _time.time() - _liquidity_cache["ts"] < _LIQUIDITY_CACHE_TTL:
        return _liquidity_cache["data"]
    liquid = set()
    try:
        import akshare as ak
        df = ak.fund_etf_spot_em()
        for _, row in df.iterrows():
            code = str(row.get("代码", ""))
            amount = float(row.get("成交额", 0) or 0)
            if code in etf_dict and amount >= _MIN_DAILY_AMOUNT:
                liquid.add(code)
    except Exception:
        liquid = set(etf_dict.keys())
    _liquidity_cache["data"] = liquid
    _liquidity_cache["ts"] = _time.time()
    excluded = len(etf_dict) - len(liquid)
    if excluded > 0:
        print(f"  流动性过滤: {excluded}只僵尸ETF (日成交<1000万)")
    return liquid


def screen(limit: int = None, profile: str = "均衡", top_n: int = 10, codes: list = None) -> List[dict]:
    from ..pipeline import batch_full
    from ..config_loader import load_etfs
    from ..enhance.l8_realtime import enhance_l8
    from ..enhance.l9_news import enhance_l9
    from ..data.kline import get_trend
    from ..data.manager import get_news

    etfs = load_etfs()
    
    # v5.5: Liquidity filter (skip for user-specified codes)
    if codes is None:
        liquid_codes = _get_liquid_codes(etfs)
        etfs = {k: v for k, v in etfs.items() if k in liquid_codes}
    
    if codes is not None:
        target_codes = [c for c in codes if c in etfs]
        if not target_codes:
            print(f"  指定ETF均不在配置中: {codes}")
            return []
        print(f"\n  🔍 指定ETF分析: {profile}型投资者")
        print(f"  {'='*50}")
        print(f"  目标: {len(target_codes)}只 ({', '.join(target_codes[:10])})")
        results = batch_full(codes=target_codes, live=False, profile=profile)
        limit = len(target_codes)
    else:
        if limit is None:
            limit = len(etfs)
        limit = min(limit, len(etfs))
        target_codes = None

        print(f"\n  🔍 全市场扫描: {profile}型投资者")
        print(f"  {'='*50}")
        print(f"  分析 {limit}/{len(etfs)} 只ETF")

    # Cache (skip for direct code mode)
    cache_dir = Path(__file__).resolve().parent.parent.parent.parent / "data" / "screener_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"scan_{profile}.json"
    checkpoint_file = cache_dir / f"scan_{profile}_checkpoint.json"

    if codes is not None:
        pass  # results already populated in direct mode
    else:
        results = None
    if codes is None and cache_file.exists():
        age = time.time() - cache_file.stat().st_mtime
        if age < 7200:
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    results = json.load(f)
                print(f"  缓存 ({age:.0f}s前, {len(results)}只)")
            except:
                results = None

    if results is None and codes is None:
        t0 = time.time()
        results = _batch_with_retry(limit=limit, checkpoint_file=checkpoint_file)
        elapsed = time.time() - t0
        print(f"  穿透完成 ({elapsed:.0f}s, {len(results)}/{limit}只)")
        try:
            clean = [{k:v for k,v in r.items() if isinstance(v,(dict,list,str,int,float,bool)) or v is None} for r in results]
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(clean, f, ensure_ascii=False, default=str)
        except:
            pass
    elif codes is not None and results is not None:
        print(f"  穿透完成 ({len(results)}只)")

    # v5.4: Always detect dead layers (not just on first run)
    dead = _detect_dead_layers(results)
    if dead:
        print(f"  检测到{len(dead)}个死层(差异<0.5): {dead}")
        # 从results中移除死层的scores避免影响归一化
        for r in results:
            for d in dead:
                r.get("layer_scores", {}).pop(d, None)
    weights = _compute_auto_weights(results, profile, dead)
    print(f"  自动权重: {weights}")

    # QVIX市场情绪权重调整 (l005 signal-2)
    try:
        from ..analysis.qvix_regime import get_regime, get_weight_shift
        regime_data = get_regime()
        qvix_regime = regime_data.get("regime", "normal")
        qvix_shift = get_weight_shift(profile)
        if qvix_shift and qvix_regime != "normal":
            print(f"  QVIX市场状态: {qvix_regime} (50={regime_data.get('qvix_50','?')} 500={regime_data.get('qvix_500','?')})")
            print(f"  权重调整: {qvix_shift}")
            import copy
            local_cat_weights = copy.deepcopy(CATEGORY_WEIGHTS)
            resolved = _resolve_profile(profile)
            for cat_en, cat_cn in [("supply","供给侧"),("capital","资金面"),("signal","信号面"),("demand","需求面")]:
                shift = qvix_shift.get(cat_en, 0)
                if shift != 0 and cat_cn in local_cat_weights.get(resolved, {}):
                    old_w = local_cat_weights[resolved][cat_cn]
                    new_w = max(0.05, min(0.50, old_w + shift))
                    local_cat_weights[resolved][cat_cn] = new_w
                    print(f"    {cat_cn}: {old_w:.2f} -> {new_w:.2f}")
            weights = _compute_auto_weights(results, profile, dead)
    except Exception as e:
        print(f"  QVIX调整失败(不影响主流程): {str(e)[:80]}")
        qvix_regime = "unknown"

    # v5.4: 归一化已废弃 — 扭曲信号(小差异被放大为0-10)。原始评分已是0-10尺度
    # _normalize_batch(results)
    # Score and rank
    ranked = []
    for r in results:
        code = r.get("etf_code", "")
        ls = r.get("layer_scores", {})
        l1 = ls.get("L1_ETF", 5)
        rl = max(0.1, min(0.9, (10 - l1) / 10)) if isinstance(l1, (int, float)) else 0.5
        composite = _compute_composite(ls, weights)  # trend not yet available at batch stage
        ranked.append({"rank":0,"code":code,"name":r.get("name",""),"sector":r.get("sector",""),"risk_level":rl,"composite_score":composite,"layer_scores":ls,"reason":"","trend":{}, "_news_count": 0})

    # v5.6: Filter non-investment sectors (cash equivalents have no alpha)
    investable = [r for r in ranked if r.get("sector", "") not in NON_INVESTMENT_SECTORS]
    skipped = len(ranked) - len(investable)
    if skipped > 0:
        print(f"  过滤非投资标的: {skipped}只 (货币基金/债券)")
    ranked = investable
    
    ranked.sort(key=lambda x: -x["composite_score"])
    for i, item in enumerate(ranked):
        item["rank"] = i + 1

    top_results = ranked[:max(top_n, 20)]  # Get 20, then enhance top 10
    # Pre-load spot data for premium calculation (avoid N API calls)
    spot_df = None
    try:
        import akshare as ak
        spot_df = ak.fund_etf_spot_em()
        print(f"  获取实时数据(行情+折溢价)+趋势+新闻动态评分...")
    except Exception:
        spot_df = None
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
        # Enhance all top_results items
        for raw in results:
            if raw.get("etf_code", raw.get("code", "")) == code:
                try:
                    # Get news for this ETF's sector
                    sector = item.get("sector", "")
                    if sector and sector not in ("其他", "综合", "未知行业"):
                        news_items = get_news(sector, limit=3)
                        item["_news_count"] = len(news_items)
                        if news_items:
                            ls = item["layer_scores"]
                            neg = sum(1 for n in news_items if any(k in n.title for k in ["跌","降","利空","风险","跳水","暴跌"]))
                            pos = sum(1 for n in news_items if any(k in n.title for k in ["涨","升","利好","突破","反弹"]))
                            old_l9 = ls.get("L9_Signals", 5.0)
                            adj = (pos - neg) * 0.5
                            ls["L9_Signals"] = max(1, min(10, old_l9 + adj))
                    # Live data
                    raw2 = enhance_l8(raw)
                    item["layer_scores"].update(raw2.get("layer_scores", {}))
                    # Recalculate with trend after all enhancements
                    td = item.get("trend")
                    item["composite_score"] = _compute_composite(item["layer_scores"], weights, td)
                    # Premium/discount penalty (l005 signal-1) — applied AFTER trend
                    try:
                        pp = _premium_penalty(code, spot_df)
                        item["premium"] = pp
                        item["composite_score"] += pp["penalty"]
                    except Exception:
                        pass
                except Exception as e:
                    print(f"    ⚠ enhance failed for {code}: {e}")
                break
        item["reason"] = _generate_reason(item, item.get("trend"))

    # v5.4: 用趋势调整后的评分重新排序
    top_results.sort(key=lambda x: -x["composite_score"])
    for i, item in enumerate(top_results):
        item["rank"] = i + 1
    
    # v5.5: Cash/Defense signal — check QVIX regime for market stress
    cash_signal = None
    try:
        from ..analysis.qvix_regime import get_regime
        rd = get_regime()
        qvix_50 = rd.get("qvix_50", 0)
        qvix_500 = rd.get("qvix_500", 0)
        regime = rd.get("regime", "normal")
        if regime in ("fear", "panic") or qvix_50 > 30:
            cash_signal = {
                "active": True,
                "reason": f"QVIX恐慌({qvix_50:.0f}/{qvix_500:.0f}), 建议持有现金或防御资产",
                "qvix_50": qvix_50,
                "qvix_500": qvix_500,
                "regime": regime
            }
            print(f"\n  ⚠️ 空仓信号: QVIX={qvix_50:.0f}/{qvix_500:.0f} ({regime}), 以下排名仅供参考")
        elif regime == "cautious" and qvix_50 > 25:
            cash_signal = {
                "active": False,
                "warning": True,
                "reason": f"QVIX谨慎({qvix_50:.0f}), 建议减仓或只买防御型ETF",
                "qvix_50": qvix_50,
                "qvix_500": qvix_500,
                "regime": regime
            }
    except Exception:
        pass
    
    result = top_results[:top_n]
    
    # v5.6: Risk manager — stop-loss and portfolio drawdown checks
    risk_flags = None
    try:
        from .risk_manager import check_risk_flags, update_positions, get_position_summary
        risk_flags = check_risk_flags()
        if risk_flags and risk_flags.get("message"):
            print(f"\n  {'⚠️' if risk_flags.get('stop_loss_hit') or risk_flags.get('portfolio_dd_critical') else '⚡'} 风控: {risk_flags['message']}")
            # Update positions with current prices
            prices = {}
            for r in result:
                trend = r.get("trend", {})
                if trend.get("price", 0) > 0:
                    prices[r["code"]] = trend["price"]
            if prices:
                update_positions(result, prices)
    except Exception:
        pass
    
    if cash_signal:
        result = [{"_cash_signal": cash_signal}] + result
    if risk_flags and risk_flags.get("message"):
        result = [{"_risk_flags": risk_flags}] + result
    
    # v5.6: Track recommendations for feedback loop
    try:
        import json as _json
        from pathlib import Path as _Path
        from datetime import datetime as _dt
        tracking_file = _Path(__file__).resolve().parent.parent.parent.parent / "data" / "live_cache" / "recommendation_tracking.json"
        tracking_file.parent.mkdir(parents=True, exist_ok=True)
        tracking = []
        if tracking_file.exists():
            with open(tracking_file, "r", encoding="utf-8") as f:
                tracking = _json.load(f)
        tracking.append({
            "date": _dt.now().strftime("%Y-%m-%d"),
            "profile": profile,
            "codes": [r["code"] for r in result if isinstance(r, dict) and "code" in r],
            "scores": [r.get("composite_score", 0) for r in result if isinstance(r, dict) and "code" in r]
        })
        # Keep last 12 months
        tracking = tracking[-12:]
        with open(tracking_file, "w", encoding="utf-8") as f:
            _json.dump(tracking, f, ensure_ascii=False, indent=2, default=str)
    except Exception:
        pass
    
    return result


def recommend(top_n: int = 5, profile: str = "均衡") -> List[dict]:
    return screen(limit=50, profile=profile, top_n=top_n)