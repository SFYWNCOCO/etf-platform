import sys
import json
from pathlib import Path

# Fallback for running as script: python src/etf_platform/cli.py
# When executed directly, relative imports fail. Resolve by adding src/ to sys.path.
_here = Path(__file__).resolve().parent.parent.parent
_src = _here.parent  # _here is etf_platform/, so parent is src/
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from etf_platform.pipeline import run_full, batch_full, format_full


def _print_health_table(health_results):
    print(f"\n{'='*55}")
    print("  ETF \u6570\u636e\u6e90\u5065\u5eb7\u68c0\u67e5")
    print(f"{'='*55}")
    print(f"  {'\u6e90\u540d\u79f0':<20} {'\u72b6\u6001':<12} {'\u5ef6\u8fdf':<8}")
    print(f"  {'-'*40}")
    for h in health_results:
        icon = {"healthy": "\u2705", "degraded": "\u26a0\ufe0f", "failed": "\u274c"}
        status_str = f"{icon.get(h.status.value, '?')} {h.status.value}"
        latency_str = f"{h.latency_ms:.0f}ms" if h.latency_ms >= 0 else "-"
        print(f"  {h.source_name:<20} {status_str:<12} {latency_str:<8}")
        if h.error:
            print(f"  {'':>20} \u2514 {h.error}")
    print(f"{'='*55}\n")


def _print_screen_results(results):
    if not results:
        print("\n  No results.\n")
        return
    
    # v5.6: l003 knowledge-aware dual-mode display
    l003 = None
    if results and isinstance(results[0], dict) and "_l003_insight" in results[0]:
        l003 = results[0]["_l003_insight"]
        results = results[1:]

    # Screen results may also carry non-ETF entries (_cash_signal/_risk_flags).
    # Strip them BEFORE iterating so r["code"]/r["name"] below never KeyErrors.
    results = [r for r in results if isinstance(r, dict) and "code" in r and "name" in r]
    
    if l003:
        print(f"\n  {'='*70}")
        print("  \u2620\ufe0f l003\u77e5\u8bc6\u5e93: \u7a7f\u900f\u8bc4\u5206=\u98ce\u9669\u6307\u6807(\u975e\u6536\u76ca\u6307\u6807)")
        print(f"  {'='*70}")
        print("  \u9ad8\u5206(>7)=\u5b89\u5168\u65e0\u50ac\u5316\u5242 | \u4f4e\u5206(<4)=\u9ad8\u5f39\u6027\u77ed\u7a97\u53e3\u535a\u5f08")
        safe = l003.get("safe_mode", [])
        if safe:
            print(f"\n  \U0001f6e1\ufe0f \u5b89\u5168\u914d\u7f6e (Top {min(5, len(safe))}):")
            for s in safe[:5]:
                print(f"     {s['code']} {s['name'][:18]:<19} score={s['score']} | {s['note']}")
        catalyst = l003.get("catalyst_mode", [])
        if catalyst:
            print(f"\n  \U0001f680 \u50ac\u5316\u5242\u5f39\u6027 (Top {min(5, len(catalyst))}):")
            for c in catalyst[:5]:
                print(f"     {c['code']} {c['name'][:18]:<19} score={c['score']} momentum={c['momentum']} elasticity={c['elasticity']} | {c['note']}")
        elif l003.get("top_catalyst_by_elasticity"):
            print("\n  \U0001f680 \u5f39\u6027\u6392\u540d (\u4f4e\u5206+\u9ad8\u52a8\u91cf):")
            for c in l003["top_catalyst_by_elasticity"][:5]:
                print(f"     {c['code']} {c['name'][:18]:<19} elasticity={c['elasticity']}")
        print()

    print(f"\n  {'='*70}")
    print("  ETF \u63a8\u8350\u6392\u540d")
    print(f"  {'='*70}")
    print(f"  {'#':<3} {'\u4ee3\u7801':<8} {'\u540d\u79f0':<22} {'\u884c\u4e1a':<12} {'\u603b\u5206':<6} {'\u98ce\u9669':<5} {'\u8d8b\u52bf':<14}")
    print(f"  {'-'*70}")
    ticons = {"oversold":"\U0001f7e2\u8d85\u5356","weak":"\U0001f7e1\u56de\u8c03","neutral":"\u26aa\u4e2d\u6027","strong":"\U0001f7e1\u58ee\u6001","overbought":"\U0001f534\u8d85\u4e70","plunging":"\U0001f534\u6025\u8dcc","surging":"\U0001f7e2\u6025\u6da8"}
    for r in results:
        rl = r.get("risk_level", 0)
        risk_icon = "\U0001f7e2" if rl < 0.3 else ("\U0001f7e1" if rl < 0.6 else "\U0001f534")
        trend = r.get("trend", {})
        sig = trend.get("signal", "")
        tag = ticons.get(sig, "")
        chg = trend.get("change_20d", 0)
        trend_str = f"{tag} {chg:+.1f}%" if tag else ""
        c = r["code"]
        n = r["name"][:20]
        sec = r["sector"][:10]
        sc = r["composite_score"]
        print(f"  {r['rank']:<3} {c:<8} {n:<22} {sec:<12} {sc:<6.1f} {risk_icon}{rl:.2f} {trend_str:<14}")
    print(f"  {'='*70}")
    print("  \u6838\u5fc3\u7406\u7531:")
    for r in results[:5]:
        print(f"  #{r['rank']} {r['name']}")
        print(f"      {r['reason']}")
    print()
def _print_comparison(ra, rb, va, vb):
    """Side-by-side comparison of two ETFs."""
    name_a = ra.get("name", ra.get("etf_code", "?"))
    name_b = rb.get("name", rb.get("etf_code", "?"))
    code_a = ra.get("etf_code", "?")
    code_b = rb.get("etf_code", "?")
    sa = ra.get("layer_scores", {})
    sb = rb.get("layer_scores", {})
    
    print(f"\n  {'='*65}")
    print("  ETF \u5bf9\u6bd4")
    print(f"  {'='*65}")
    
    # Basic info
    print(f"  {'':<5} {code_a:<20} {code_b:<20}")
    print(f"  {'\u540d\u79f0':<5} {name_a[:18]:<20} {name_b[:18]:<20}")
    print(f"  {'\u884c\u4e1a':<5} {ra.get('sector','?')[:16]:<20} {rb.get('sector','?')[:16]:<20}")
    print()
    
    # Layer scores
    print(f"  {'\u5c42':<15} {code_a:<20} {code_b:<20}")
    print(f"  {'-'*55}")
    all_layers = sorted(set(list(sa.keys()) + list(sb.keys())))
    names = {"L1_ETF":"\u57fa\u7840\u9762","L2_Holdings":"\u6301\u4ed3\u7ed3\u6784","L3_Material":"\u6750\u6599\u5b89\u5168","L4_SupplyChain":"\u4ea7\u80fd\u7269\u6d41","L5_Tech":"\u6280\u672f\u58c1\u5792","L6_Politics":"\u653f\u6cbb\u98ce\u9669","L7_Irreplaceable":"\u4e0d\u53ef\u66ff\u4ee3","L8_CapitalFlow":"\u8d44\u91d1\u9762","L9_Signals":"\u4fe1\u53f7","L10_Demand":"\u6d88\u8d39\u9700\u6c42","L11_SectorRisk":"\u884c\u4e1a\u98ce\u9669"}
    for layer in all_layers:
        lname = names.get(layer, layer)
        va_score = sa.get(layer, "-")
        vb_score = sb.get(layer, "-")
        icon_a = "\U0001f7e2" if isinstance(va_score, (int,float)) and va_score >= 7 else ("\U0001f7e1" if isinstance(va_score, (int,float)) and va_score >= 4 else "\U0001f534")
        icon_b = "\U0001f7e2" if isinstance(vb_score, (int,float)) and vb_score >= 7 else ("\U0001f7e1" if isinstance(vb_score, (int,float)) and vb_score >= 4 else "\U0001f534")
        print(f"  {lname:<15} {icon_a} {str(va_score):<16} {icon_b} {str(vb_score):<16}")
    print()
    
    # Valuation
    print(f"  {'\u4f30\u503c':<15} {code_a:<20} {code_b:<20}")
    print(f"  {'-'*55}")
    if va:
        print(f"  {'NAV':<15} {va.nav:<20.4f} ", end="")
        print(f"{vb.nav:<20.4f}" if vb else "{'N/A':<20}")
        print(f"  {'\u5e02\u4ef7':<15} {va.market_price:<20.4f} ", end="")
        print(f"{vb.market_price:<20.4f}" if vb else "{'N/A':<20}")
        print(f"  {'\u6298\u4ef7\u7387':<15} {va.premium_pct:+.2f}%", end="")
        print(f"  {vb.premium_pct:+.2f}%" if vb else "{'N/A'}")
    print()
    
    # Trend comparison
    print(f"  {'\u8d8b\u52bf':<15} {code_a:<20} {code_b:<20}")
    print(f"  {'-'*55}")
    def get_trend_simple(code):
        try:
            from etf_platform.data.kline import get_trend
            return get_trend(code)
        except (KeyError, ValueError, TypeError, AttributeError, ImportError):
            return None
    ta = get_trend_simple(code_a)
    tb = get_trend_simple(code_b)
    t_names = {"oversold":"\u8d85\u5356","weak":"\u56de\u8c03","neutral":"\u4e2d\u6027","strong":"\u58ee\u6001","overbought":"\u8d85\u4e70","plunging":"\u6025\u8dcc","surging":"\u6025\u6da8"}
    if ta:
        print(f"  {'\u4fe1\u53f7':<15} {t_names.get(ta.trend_signal,'?'):<20} {t_names.get(tb.trend_signal,'?') if tb else 'N/A':<20}")
        print(f"  {'20\u65e5\u6da8\u8dcc':<15} {ta.change_20d:+.1f}%", end="")
        print(f"  {tb.change_20d:+.1f}%" if tb else "{'N/A'}")
        print(f"  {'\u56de\u64a4':<15} {ta.max_drawdown:.1f}%", end="")
        print(f"  {tb.max_drawdown:.1f}%" if tb else "{'N/A'}")
    print()

def app():
    args = sys.argv[1:] if len(sys.argv) > 1 else []

    # Pre-warm pipeline + spot data in background (hides ~24s startup latency)
    import threading as _t
    def _pre_warm():
        run_full("159995", live=False)  # pipeline layers (~2s)
        try:  # spot data for screen() — saves ~22s on first scan
            import akshare as ak
            df = ak.fund_etf_spot_em()
            from src.etf_platform.decision.screener import _spot_cache, _SPOT_CACHE_LOCK
            import time as _time
            with _SPOT_CACHE_LOCK:
                _spot_cache["df"] = df
                _spot_cache["ts"] = _time.time()
        except (ImportError, KeyError, ValueError, TypeError, AttributeError, OSError, IndexError, StopIteration):
            pass  # silent catch — pre-warm is non-critical
    _t.Thread(target=_pre_warm, name="etf-pre-warm", daemon=True).start()

    if not args or args[0] in ("-h", "--help"):
        print("Usage:")
        print("  etf run <CODE>           Single ETF 11-layer penetration (JSON)")
        print("  etf report <CODE>        Full formatted report")
        print("")
        print("  etf analyze <CODE>       Deep analysis (7 modules)")
        print("  etf patrol               Daily patrol (scan+rotation+prices)")
        print("  etf portfolio [--profile=] [--budget=N]  Portfolio allocation")
        print("  etf chain [CODE]         Supply chain risk analysis")
        print("  etf health <CODE>        ETF ecosystem health score")
        print("  etf holdings <CODE>      Top-10 holdings penetration")
        print("  etf holdings-refresh [--limit=N] [--codes=a,b] 全量刷新持仓缓存 ★NEW")
        print("  etf insight [--json]     Decision history analysis")
        print("  etf rotation             Sector rotation snapshot")
        print("  etf screen [--top=N]     Market scan & ranking [--profile=均衡]")
        print("  etf recommend            Quick top-5 recommendation")
        print("  etf compare <A> <B>      Side-by-side comparison")
        print("  etf price <CODE>         Live price")
        print("  etf valu <CODE>          NAV & premium data")
        print("  etf news [keyword]       Latest finance news")
        print("  etf check                Data source health check")
        print("  etf status               System status")
        print("  etf archive [collect|list|show]  Daily data archive")
        print("  etf events [recent|log]          Market event timeline")
        print("  etf batch [--limit=N]    Batch analysis")
        print("  etf cycle [sector]       Three-cycle macro report (k001+k002)")
        print("  etf factor <CODE>        Fama-French factor exposure (k003)")
        print("  etf factors              Full sector factor map")
        print("  etf stoic <sector>       Stoic risk analysis (k004)")
        print("  etf state [sector]       Market state similarity (k005)")
        print("  etf live <CODE>          Live premium/liquidity/quality (k006-k009)")
        print("  etf dip                ETF折溢价实时监控 ★NEW")
        print("  etf flow               ETF资金流向分析 ★NEW")
        print("  etf ranking            ETF同类排名与评级 ★NEW")
        print("  etf overlap [CODE_A] [CODE_B] 持仓重叠度分析 ★NEW")
        print("  etf estimate <CODE>    收益测算器 ★NEW")
        print("  etf picker [--profile=]   2-week upside prediction Top 3  ★NEW")
        print("  etf picker [--profile=]   2-week upside prediction Top 3  ★NEW")
        print("  etf --help               This help")
        return
    
    cmd = args[0]
    
    if cmd == "run":
        code = args[1] if len(args) > 1 else ""
        if not code:
            print("Error: need ETF code, e.g. etf run 159995")
            return
        result = run_full(code)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    
    elif cmd == "report":
        code = args[1] if len(args) > 1 else ""
        if not code:
            print("Error: need ETF code, e.g. etf report 159995")
            return
        result = run_full(code)
        print(format_full(result))
    
    elif cmd == "batch":
        limit = 50
        for a in args[1:]:
            if a.startswith("--limit="):
                limit = int(a.split("=")[1])
        results = batch_full(limit=limit)
        print(f"\nBatch complete: {len(results)} ETFs analyzed")
        for r in results[:10]:
            code = r.get("etf_code", "?")
            s = r.get("layer_scores", {})
            total = sum(s.values()) / max(len(s), 1)
            print(f"  {code}: avg={total:.1f} | {s.get('L10_Demand','?')}/{s.get('L11_SectorRisk','?')}")
        if len(results) > 10:
            print(f"  ... ({len(results)-10} more)")
    
    elif cmd == "check":
        from etf_platform.data.manager import check_all_sources
        health_results = check_all_sources()
        _print_health_table(health_results)
        healthy = sum(1 for h in health_results if h.status.value == "healthy")
        failed = sum(1 for h in health_results if h.status.value == "failed")
        print(f"  {healthy} healthy, {failed} failed\n")
    
    elif cmd == "price":
        code = args[1] if len(args) > 1 else ""
        if not code:
            print("Error: need ETF code, e.g. etf price 159995")
            return
        from etf_platform.data.manager import get_price
        price, source = get_price(code)
        if price:
            print(f"\n  {price.name} ({price.code})")
            print(f"  \u4ef7\u683c: {price.price:.3f}  |  \u6da8\u8dcc: {price.change_pct:+.2f}%")
            print(f"  \u6210\u4ea4\u989d: {price.amount/1e8:.2f}\u4ebf  |  \u6362\u624b\u7387: {price.turnover_rate:.2f}%")
            print(f"  \u6765\u6e90: {source}\n")
        else:
            print(f"  No price data available for {code}\n")
    
    elif cmd == "news":
        keyword = args[1] if len(args) > 1 else ""
        if not keyword:
            keyword = "ETF"
        from etf_platform.data.manager import get_news
        items = get_news(keyword, limit=10)
        print(f"\n  {len(items)} news results for: {keyword}\n")
        for item in items:
            print(f"  * {item.title}")
            if item.source:
                print(f"    Source: {item.source} | {item.time}")
            print()
    
    elif cmd == "screen":
        top_n = 10
        profile = "\u5747\u8861"
        for a in args[1:]:
            if a.startswith("--top="):
                top_n = int(a.split("=")[1])
            if a.startswith("--profile="):
                profile = a.split("=")[1]
        from etf_platform.decision.screener import screen
        results = screen(top_n=top_n, profile=profile)
        _print_screen_results(results)
    
    elif cmd == "recommend":
        from etf_platform.decision.screener import recommend
        results = recommend()
        _print_screen_results(results)
    
    elif cmd == "compare":
        if len(args) < 3:
            print("Error: need two ETF codes, e.g. etf compare 159263 159995")
            return
        code_a, code_b = args[1], args[2]
        from etf_platform.data.valuation import get_valuation
        ra = run_full(code_a)
        rb = run_full(code_b)
        va = get_valuation(code_a)
        vb = get_valuation(code_b)
        _print_comparison(ra, rb, va, vb)
    
    elif cmd == "valu":
        code = args[1] if len(args) > 1 else ""
        if not code:
            print("Error: need ETF code")
            return
        from etf_platform.data.valuation import get_fund_snapshot
        v = get_fund_snapshot(code)
        if v and v.nav > 0:
            print(f"\n  {v.name} ({v.code})")
            print(f"  类型:     {v.fund_type}")
            print(f"  NAV:      {v.nav:.4f}")
            print(f"  市价:     {v.market_price:.4f}")
            print(f"  折价率:   {v.premium_pct:+.2f}%")
            print(f"  日回报:   {v.daily_return:+.2f}%")
            if v.change_1m != 0:
                print(f"  阶段涨幅: 1月{v.change_1m:+.1f}%  3月{v.change_3m:+.1f}%")
            if v.tracking_index:
                print(f"  跟踪标的: {v.tracking_index}")
            print()
        else:
            print(f"  No data for {code}\n")
    
    elif cmd == "analyze":
        """全面分析: 穿透+轮动+宏观+建议"""
        code = args[1] if len(args) > 1 else ""
        profile = "balanced"
        for a in args[2:]:
            if a.startswith("--profile="):
                profile = a.split("=")[1]
        if not code:
            print("Error: need ETF code")
            return
        from etf_platform.analyst import analyze as _analyse
        r = _analyse(code, profile=profile)
        layers = r.get("layer_scores", {})
        print("")
        print("  [深度学习] %s %s" % (code, r.get("name","")))
        print("  %s" % ("="*50))
        print("  行业: %s | 类型: %s" % (r.get("sector","?"), r.get("sector_type","?")))
        print("  综合评分: %.2f/10 | 风险: %s" % (r.get("composite_score",0), r.get("risk_level","?")))
        print("  供给端: %.1f  资金面: %.1f" % (r.get("supply_score",0), r.get("capital_score",0)))
        print("  信号面: %.1f  需求端: %.1f" % (r.get("signal_score",0), r.get("demand_score",0)))
        for k, v in sorted(layers.items()):
            print("    %s: %s" % (k, v))
        rs = r.get("rotation_signal")
        if rs:
            print("  轮动信号: %s %+.2f%% (%s)" % (rs.get("icon",""), rs.get("change_pct",0), rs.get("signal","?")))
        print("  建议: %s" % r.get("advice","?"))
        print("")
    
    elif cmd == "patrol":
        """每日巡逻: 全市场扫描+轮动+行情+建议"""
        from etf_platform.analyst import patrol as _patrol
        print(_patrol())
    
    elif cmd == "rotation":
        """行业轮动快照"""
        from etf_platform.analysis.rotation import detect_rotation
        r = detect_rotation()
        if r.get("sectors"):
            print("")
            print("  %-14s %-8s %-8s %-8s" % ("行业", "涨跌", "信号", "成交额"))
            print("  %s" % ("-"*40))
            for sec, info in sorted(r["sectors"].items(), key=lambda x: x[1]["change_pct"], reverse=True):
                print("  %s %-12s %+.2f%%  %-8s %.2f亿" % (info["icon"], sec, info["change_pct"], info["signal"], info["amount_yi"]))
            print("")
            print("  领涨: %s" % r["top_gainers"])
            if r.get("top_losers"):
                print("  领跌: %s" % r["top_losers"])
            print("")
    


    elif cmd == "portfolio":
        """投资组合分配"""
        budget = 1000
        profile = "balanced"
        codes = []
        for a in args[1:]:
            if a.startswith("--budget="):
                budget = int(a.split("=")[1])
            elif a.startswith("--profile="):
                profile = a.split("=")[1]
            elif not a.startswith("--"):
                codes.append(a)
        from etf_platform.optimize.portfolio import generate_portfolio_report
        from etf_platform.analyst import analyze
        results = {}
        if codes:
            for code in codes:
                r = analyze(code, profile=profile)
                results[code] = r
        else:
            for code in ["512890","159995","159819","518880","159201","511010"]:
                r = analyze(code, profile=profile)
                results[code] = r
        print(generate_portfolio_report(results, budget=budget, profile=profile))

    elif cmd == "health":
        """ETF生态健康评分"""
        code = args[1] if len(args) > 1 else ""
        if not code:
            print("Usage: etf health <CODE>")
            return
        from etf_platform.analysis.macro import full_eco_report
        r = full_eco_report(code)
        h = r["health"]
        if h:
            print("")
            print("  [生态健康] %s" % code)
            print("  %s" % ("="*45))
            print("  综合健康: %d分 %s" % (h["score"], h["level"]))
            print("  模块分解:")
            for mod, sc in sorted(h["modules"].items()):
                print("    %s: %.1f" % (mod.replace("_"," "), sc))
            m = r["macro"]
            print("  宏观阶段: %s" % m["phase"])
            print("  防御推荐: %s" % m["recommended"]["defensive"])
            print("  进攻推荐: %s" % m["recommended"]["offensive"])
            print("")
        else:
            print("  ⚠️ %s 暂无生态健康数据, 可用 etf report %s" % (code, code))


    elif cmd == "holdings":
        """持仓穿透数据：真实持仓缓存/在线抓取，静态版 fallback"""
        code = args[1] if len(args) > 1 else ""
        from etf_platform.analysis.holdings_fetcher import get_top_holdings, get_concentration_metrics
        from etf_platform.analysis.holdings import list_covered_etfs
        if code:
            top = get_top_holdings(code, top_n=10)
            conc = get_concentration_metrics(code)
            if top:
                print("")
                print("  [持仓穿透] %s (%s)" % (code, top[0]["quarter"]))
                print("  %s" % ("="*55))
                print("  前10集中度: %.1f%% | 总持仓: %d只" % (conc["top10_pct"], conc["total_holdings"]))
                print("  持仓明细:")
                print("  %-16s %-8s %-7s" % ("股票","代码","权重"))
                for s in top:
                    print("  %-16s %-8s %.2f%%" % (s["name"], s["code"], s["pct_nav"]))
                print("")
            else:
                # 静态手工版 fallback（覆盖 import_dep 供应链字段）
                from etf_platform.analysis.holdings import get_holdings, get_concentration_analysis
                h = get_holdings(code)
                ca = get_concentration_analysis(code)
                if h:
                    print("")
                    print("  [持仓穿透(静态)] %s %s" % (code, h["name"]))
                    print("  %s" % ("="*55))
                    print("  前10集中度: %.0f%% | 加权进口依赖: %.1f%%" % (ca["top10_weight"]*100, ca["weighted_import_dep"]*100))
                    print("  风险: %s" % ca["risk_summary"])
                    print("  持仓明细:")
                    print("  %-14s %-8s %-6s %-16s %s" % ("股票","代码","权重","链位置","技术等级"))
                    for s in h["top10"]:
                        print("  %-14s %-8s %.1f%% %-16s %s" % (s["stock"],s["code"],s["weight"]*100,s["chain"][:16],s["tech"][:24]))
                    print("")
                else:
                    print("  ⚠️ %s 暂无持仓数据(在线+静态均无), 可先 etf holdings-refresh --codes=%s" % (code, code))
                    print("  静态已覆盖:", ", ".join(list_covered_etfs()))
        else:
            print("  Usage: etf holdings <CODE>")
            print("  静态已覆盖:", ", ".join(list_covered_etfs()))
            print("  提示: etf holdings-refresh 可全量刷新真实持仓缓存")

    elif cmd == "holdings-refresh":
        """全量刷新持仓缓存（eastmoney 直连）"""
        limit = None
        codes = None
        for a in args[1:]:
            if a.startswith("--limit="):
                limit = int(a.split("=")[1])
            elif a.startswith("--codes="):
                codes = [c for c in a.split("=")[1].split(",") if c]
        from etf_platform.analysis.holdings_fetcher import refresh_all
        stats = refresh_all(codes=codes, limit=limit)
        print("  total=%d ok=%d empty=%d failed=%d ratio=%.0f%% saved=%s" % (
            stats["total"], stats["ok"], stats["empty"], stats["failed"],
            stats["success_ratio"]*100, stats["saved"]))
        if not stats["saved"]:
            print("  ⚠️ 有效请求比例过低，已保留旧缓存（源故障保护）")

    elif cmd == "insight":
        """策略决策分析"""
        from etf_platform.optimize.decision import print_report, analyze
        if "--json" in args:
            print(json.dumps(analyze(), ensure_ascii=False, indent=2))
        else:
            print_report()

    elif cmd == "chain":
        """供应链风险分析"""
        code = args[1] if len(args) > 1 else ""
        from etf_platform.analysis.chain import get_chain_report, find_safest_etfs, find_riskiest_etfs
        if code:
            r = get_chain_report(code)
            if r and "risk_level" in r:
                print("")
                print("  [供应链风险] %s %s" % (r["code"], r["name"]))
                print("  %s" % ("="*50))
                print("  风险等级: %s (%.1f分)" % (r["risk_level"], r["risk_score"]))
                print("  直接瓶颈: %d  间接链: %d  连锁场景: %d" % (
                    r["direct_bottlenecks"], r["indirect_chains"], r["cascade_scenarios_count"]))
                print("  隐藏连接: %s" % r["hidden_link"])
                if r.get("cascade_scenarios"):
                    print("  影响场景:")
                    for sc in r["cascade_scenarios"]:
                        print("    • %s (%s)" % (sc["scene"], sc["probability"]))
                print("")
            else:
                print("  ⚠️ %s 暂无供应链数据, 可用 etf analyze %s" % (code, code))
        else:
            print("")
            print("  [供应链风险排名]")
            print("  %s" % ("="*50))
            print("  最脆弱的ETF:")
            for etf in find_riskiest_etfs(5):
                rs = etf["risk_score"]
                risk_icon = "🔴" if rs >= 3.0 else ("🸀" if rs >= 2.0 else "⚪")
                print("  %s %s %s: %.1f分" % (risk_icon, etf["code"], etf["name"], rs))
            print("  最安全的ETF:")
            for etf in find_safest_etfs(5):
                print("  🟢 %s %s: %.1f分" % (etf["code"], etf["name"], etf["risk_score"]))
            print("")
    elif cmd == "status":
        """系统状态概览"""
        from etf_platform.data.manager import check_all_sources
        from etf_platform.config_loader import load_etfs
        etfs = load_etfs()
        health = check_all_sources()
        healthy = sum(1 for h in health if h.status.value == "healthy")
        failed = sum(1 for h in health if h.status.value == "failed")
        print("")
        print("  ETF系统状态")
        print("  %s" % ("="*40))
        print("  ETF数量: %d" % len(etfs))
        print("  数据源: %s healthy, %s failed (8s timeout)" % (str(healthy), str(failed)))
        print("  版本: 0.2.0 (integrated)")
        print("  模块: penetration + rotation + demand + analyst")
        for h in health:
            print("    %s: %s (%dms)" % (h.source_name, h.status.value, h.latency_ms))
        print("")

    elif cmd == "causal":
        code = args[1] if len(args) > 1 else ""
        from etf_platform.analysis.causal import CausalEngine
        from etf_platform.data.events import inject_events
        engine = CausalEngine()
        inject_events(engine, verbose=False)
        if code:
            total, paths = engine.evaluate(code)
            print(f"\n  Causal: {code} | Total Impact: {total:+.6f}")
            for i, p in enumerate(paths[:5]):
                print(f"  Path {i+1}: {p['event'][:40]} -> {p['directional']:+.4f} {p['level']}")
        else:
            results = engine.scan_all()
            engine.report(results)

    elif cmd == "signals":
        from etf_platform.analysis.signals import ProfitSignalEngine
        ProfitSignalEngine().run_all()

    elif cmd == "events":
        """Market event timeline — log or query events."""
        sub = args[1] if len(args) > 1 else "recent"
        from etf_platform.archive.collector import log_event, load_events
        if sub == "log":
            if len(args) < 3:
                print("Usage: etf events log <type> <message>")
                print('Example: etf events log sector_rotation "黄金领涨, AI急跌"')
            else:
                etype = args[2]
                msg = " ".join(args[3:]) if len(args) > 3 else ""
                log_event(etype, {"message": msg})
                print(f"  Event logged: {etype}")
        elif sub in ("recent", "list"):
            limit = int(args[2]) if len(args) > 2 else 20
            etype = args[3] if len(args) > 3 else None
            events = load_events(limit=limit, event_type=etype)
            if not events:
                print("\n  No events yet. Run: etf events log type message\n")
            else:
                print(f"\n  Event Timeline ({len(events)} events)")
                print(f"  {'='*55}")
                for ev in events:
                    ts = ev.get("timestamp", "")[:16]
                    et = ev.get("type", "?")
                    msg = ev.get("message", "")
                    print(f"  {ts} | {et:<20} | {msg[:60]}")
        elif sub == "causal":
            from etf_platform.data.events import EVENT_PRESETS, PRESET_COMBOS
            print("\n  Causal Events:")
            for pn, evs in EVENT_PRESETS.items():
                print(f"  [{pn}]: {len(evs)} events")
            print(f"  Combos: {list(PRESET_COMBOS.keys())}")
        else:
            print("Usage: etf events [recent|log <type> <msg>|causal]")

    elif cmd == "select":
        mode = "balanced"; top_n = 10
        for a in args[1:]:
            if a.startswith("--mode="): mode = a.split("=")[1]
            if a.startswith("--top="): top_n = int(a.split("=")[1])
        from etf_platform.decision.select import select, report as sel_report
        results = select(mode=mode, top_n=top_n)
        sel_report(results)

    elif cmd == "backtest":
        from etf_platform.optimize.backtest import run_backtest, run_rolling_backtest
        rolling = "--rolling" in args
        if rolling:
            result = run_rolling_backtest()
        else:
            result = run_backtest()
        if result.get("trades"):
            print(f"\n  Backtest: {result['total']} trades, {result['accuracy']}% accuracy")

    elif cmd == "hook":
        sub = args[1] if len(args) > 1 else "summary"
        from etf_platform.hook_harness import hook_patrol, hook_backtest, hook_daily_summary

        if sub == "patrol":
            from etf_platform.decision.screener import screen
            results = screen(top_n=10, profile="均衡")
            hook_patrol(results)
            print(f"Hooked patrol: {len(results)} screened → Harness Loop")
        elif sub == "backtest":
            from etf_platform.optimize.backtest import run_backtest
            report = run_backtest()
            hook_backtest(report)
            print(f"Hooked backtest: {report.get('accuracy')}% → Harness Loop")
        elif sub == "summary":
            hook_daily_summary()
            print("Hooked daily summary → Harness Loop")
        elif sub == "verify":
            from etf_platform.hook_harness import load_json
            fw = load_json()
            etf_fws = {k: v for k, v in fw.get("frameworks", {}).items() if v.get("scope") == "etf"}
            print(f"ETF Thompson frameworks: {len(etf_fws)}")
            for n, f in sorted(etf_fws.items()):
                wr = f.get("win_rate", 0)
                print(f"  {n}: wins={f.get('wins',0)} losses={f.get('losses',0)} wr={wr:.1%}")
        else:
            print("Usage: etf hook [patrol|backtest|summary|verify]")

    elif cmd == "material":
        sub = args[1] if len(args) > 1 else "scan"
        from etf_platform.analysis.material_watchdog import scan_news, quick_add, confirm_discovery, list_pending

        if sub == "scan":
            limit = int(args[2]) if len(args) > 2 else 20
            scan_news(limit)
        elif sub == "add":
            if len(args) < 4:
                print("用法: etf material add <材料名> <趋势> <ETF1,ETF2>")
                print('示例: etf material add "固态电解质(LLZO)" "↑ 日韩量产突破" "516160,515030"')
            else:
                name = args[2]
                trend = args[3]
                etf_str = args[4] if len(args) > 4 else "510300"
                affects = [e.strip() for e in etf_str.split(",")]
                quick_add(name, trend, affects)
                print(f"✅ '{name}' 已注册")
        elif sub == "confirm":
            if len(args) < 3:
                print("用法: etf material confirm <材料名>")
            else:
                confirm_discovery(args[2])
        elif sub == "list":
            list_pending()
        else:
            print("用法: etf material [scan|add|confirm|list]")

    elif cmd == "deep":
        from etf_platform.analysis.deep import DeepMonitor
        dm = DeepMonitor()
        dm.run()

    elif cmd == "optimize":
        from etf_platform.decision.optimizer import load_decision_log, compare_strategies
        decisions = load_decision_log()
        if decisions:
            result = compare_strategies(decisions, {})
            print(f"\n  {len(decisions)} decisions analyzed")
            for s in result.get("suggestions", []):
                print(f"  - {s['recommendation']}: {s['reason']}")
        else:
            print("  No decision log data yet")

    elif cmd == "archive":
        """Daily data archive — collect, query, or list."""
        sub = args[1] if len(args) > 1 else "collect"
        from etf_platform.archive.collector import collect_full_snapshot, list_archives, load_day, log_event
        if sub == "collect":
            quick = "--quick" in args
            collect_full_snapshot(quick=quick)
        elif sub == "list":
            archives = list_archives()
            if not archives:
                print("\n  No archives yet. Run: etf archive collect\n")
            else:
                print(f"\n  ETF 数据归档 ({len(archives)} 天)")
                print(f"  {'='*55}")
                for a in archives[:20]:
                    tp = a.get("top_pick", {}) or {}
                    print(f"  {a['date']} | QVIX:{a.get('qvix_regime','?')[:8]:<8} | {a.get('qvix_50',0):.0f} | Top:{tp.get('code','?')} {tp.get('name','?')[:12]}")
        elif sub == "show":
            date_str = args[2] if len(args) > 2 else ""
            if not date_str:
                print("Usage: etf archive show YYYY-MM-DD")
            else:
                day = load_day(date_str)
                if not day:
                    print(f"  No archive for {date_str}")
                else:
                    import json as _json
                    print(_json.dumps(day, ensure_ascii=False, indent=2))
        else:
            print("Usage: etf archive [collect|list|show YYYY-MM-DD]")


    elif cmd == "cycle":
        """三周期宏观状态报告 (k001+k002)"""
        sector = args[1] if len(args) > 1 else None
        from etf_platform.layers.l12_macro_cycle import format_cycle_report
        print(format_cycle_report(sector))

    elif cmd == "factor":
        """Fama-French因子暴露分析 (k003)"""
        code = args[1] if len(args) > 1 else ""
        if not code:
            print("Usage: etf factor <CODE>")
            return
        from etf_platform.config_loader import load_etfs
        from etf_platform.layers.l13_factor_loading import get_factor_exposure
        etfs = load_etfs()
        info = etfs.get(code, {})
        sector = info.get("sector", "未知")
        factors = get_factor_exposure(sector)
        print(f"\n  [{code}] {info.get('name','')} 因子暴露")
        print(f"  {'='*55}")
        for k, v in sorted(factors.items()):
            print(f"  {k}: {v}")
        print()

    elif cmd == "factors":
        """全市场因子暴露概览"""
        from etf_platform.layers.l13_factor_loading import FACTOR_MAP
        print(f"\n  行业因子暴露映射表 ({len(FACTOR_MAP)} sectors)")
        print(f"  {'='*55}")
        print(f"  {'行业':<16} {'SMB':<6} {'HML':<6} {'RMW':<6} {'CMA':<6} {'LowVol':<6}")
        for sector, factors in sorted(FACTOR_MAP.items()):
            print(f"  {sector:<16} {factors.get('SMB',0):<6.2f} {factors.get('HML',0):<6.2f} {factors.get('RMW',0):<6.2f} {factors.get('CMA',0):<6.2f} {factors.get('LowVol',0):<6.2f}")
        print()

    elif cmd == "stoic":
        """斯多葛风险分析 (k004)"""
        if len(args) < 2:
            print("Usage: etf stoic <sector>")
            return
        sector = args[1]
        from etf_platform.layers.l14_stoic_risk import score_stoic_layer
        r = score_stoic_layer(sector, 0.5)
        print(f"\n  斯多葛风险分析: {sector}")
        print(f"  {'='*55}")
        print(f"  可控性评分: {r['controllability']}/10")
        print(f"  尾部风险:   {r['tail_risk']}/10")
        print(f"  平均回撤:   {r['avg_drawdown']:.1f}%")
        print(f"  综合斯多葛分: {r['score']}/10")
        if r.get('scenarios'):
            print("\n  压力测试:")
            for sc, dd in r['scenarios'].items():
                icon = "🔴" if dd < -30 else ("🟡" if dd < -15 else "🟢")
                print(f"    {icon} {sc}: {dd:.0f}%")
        print()

    elif cmd == "state":
        """市场状态相似度 (k005)"""
        sector = args[1] if len(args) > 1 else ""
        from etf_platform.layers.l15_state_similarity import find_similar_states, score_state_similarity
        matches = find_similar_states()
        print("\n  市场状态匹配")
        print(f"  {'='*55}")
        for m in matches:
            sim_pct = m['similarity'] * 100
            icon = "🟢" if sim_pct > 70 else ("🟡" if sim_pct > 50 else "⚪")
            print(f"  {icon} [{m['name']}] sim={sim_pct:.0f}%")
            print(f"     {m['description']}")
            print(f"     策略: {m['strategy']}")
        if sector:
            state_r = score_state_similarity(sector)
            print(f"\n  {sector} 在该状态下的评分: {state_r['score']}/10")
            if state_r.get('sector_benefits'):
                print("  🟢 该行业受益于当前市场状态")
        print()

    elif cmd == "estimate":
        """收益测算器"""
        code = args[1] if len(args) > 1 else ""
        amount = 10000
        for a in args[2:]:
            if a.startswith("--amount="):
                amount = float(a.split("=")[1])
        if not code:
            print("Usage: etf estimate <CODE> [--amount=10000]")
            return

        # 优先从ETF实时行情获取名称和收益率
        name = code
        try:
            import akshare as ak
            from etf_platform.utils.thread_timeout import run_with_timeout
            spot_df = run_with_timeout(ak.fund_etf_spot_em, timeout=30)
            if spot_df is None or spot_df.empty:
                raise RuntimeError("实时行情超时或为空")
            etf_row = spot_df[spot_df['代码'].astype(str) == code]
            if not etf_row.empty:
                r = etf_row.iloc[0]
                name = str(r.get('名称', code))
                # 用折价率列附近的数据，尝试从净值估算接口补充
                print(f"\n  [{code}] {name} 收益测算")
                print(f"  {'='*55}")
                print(f"  当前市价: {r.get('最新价', '?')} | IOPV: {r.get('IOPV实时估值', '?')} | 折溢价: {r.get('基金折价率', '?')}%")
                print(f"  日涨跌幅: {r.get('涨跌幅', '?')}%")
                print(f"  本金: {amount:,.0f}元")
                print("  ⚠️ 注: 东财实时行情不提供历史阶段收益率，请使用 fund_info_index_em 获取")
                print()
            else:
                print(f"⚠️ 未找到ETF {code}")
                return
        except Exception as e:
            print(f"⚠️ 获取ETF数据失败: {e}")
            return

    elif cmd == "dip":
        """ETF折溢价实时监控"""
        from etf_platform.analysis.dip_monitor import DIPMonitor
        monitor = DIPMonitor()
        report, alerts = monitor.run()
        print(report)
        print(f"\n共 {len(alerts)} 条预警")

    elif cmd == "flow":
        """ETF资金流向分析"""
        from etf_platform.analysis.fund_flow import FundFlowAnalyzer
        analyzer = FundFlowAnalyzer()
        report, alerts = analyzer.run()
        print(report)
        print(f"\n共 {len(alerts)} 条预警")

    elif cmd == "ranking":
        """ETF同类排名与评级"""
        from etf_platform.analysis.ranking import RankingManager
        manager = RankingManager()
        report, df = manager.run()
        print(report[:5000])

    elif cmd == "overlap":
        """持仓重叠度分析"""
        from etf_platform.analysis.holdings_overlap import HoldingsOverlapAnalyzer
        analyzer = HoldingsOverlapAnalyzer()
        if len(args) >= 3:
            print("使用示例数据演示重叠度分析:")
        else:
            print("使用示例数据演示重叠度分析:")
        report, results = analyzer.run_demo()
        print(report)

    elif cmd == "live":
        """折溢价+流动性+基金质量 (k006+k007+k008+k009)"""
        code = args[1] if len(args) > 1 else ""
        if not code:
            print("Usage: etf live <CODE> [amount_yi] [premium_pct]")
            print("  amount_yi: 日均成交额(亿), 默认1.0")
            print("  premium_pct: 折溢价率%, 默认0.0")
            return
        amount_yi = float(args[2]) if len(args) > 2 else 1.0
        premium_pct = float(args[3]) if len(args) > 3 else 0.0
        from etf_platform.config_loader import load_etfs
        from etf_platform.layers.l16_live_signals import get_live_signals
        etfs = load_etfs()
        info = etfs.get(code, {})
        sector = info.get("sector", "未知")
        is_cross = "QDII" in info.get("type", "") or info.get("access") == "qdii"
        r = get_live_signals(sector, amount_yi, premium_pct, is_cross)
        print(f"\n  [{code}] {info.get('name','')} 实时信号")
        print(f"  {'='*55}")
        print(f"  综合评分: {r['score']}/10")
        print(f"  流动性:   {r['liquidity']['label']} ({amount_yi:.1f}亿/日)")
        if r['premium']['signal'] != 'neutral':
            print(f"  折溢价:   {r['premium']['signal']} ({premium_pct:+.2f}%)")
        print(f"  基金质量: {r['fund_quality']['score']}/10")
        print()


    elif cmd == "picker":
        """2周涨幅预测 Top 3"""
        profile = "均衡"
        for a in args[1:]:
            if a.startswith("--profile="):
                profile = a.split("=")[1]
        from etf_platform.decision.two_week_picker import pick_top3, format_report
        from etf_platform.decision.prediction_monitor import log_prediction
        top3, scored = pick_top3(profile)
        log_prediction(top3, profile)
        print(format_report(top3))
        print(chr(10) + f"  候选池: {len(scored)}只ETF" if len(scored) > 3 else "")

    else:
        print(f"Unknown command: {cmd}")
        print("Use: etf --help")


if __name__ == "__main__":
    app()