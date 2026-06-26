import sys
import json
from pathlib import Path
from .pipeline import run_full, batch_full, format_full


def _print_health_table(health_results):
    import datetime
    print(f"\n{'='*55}")
    print(f"  ETF \u6570\u636e\u6e90\u5065\u5eb7\u68c0\u67e5")
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
    print(f"\n  {'='*70}")
    print(f"  ETF \u63a8\u8350\u6392\u540d")
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
    print(f"  \u6838\u5fc3\u7406\u7531:")
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
    print(f"  ETF \u5bf9\u6bd4")
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
            from .data.kline import get_trend
            return get_trend(code)
        except:
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
    
    if not args or args[0] in ("-h", "--help"):
        print("Usage:")
        print("  etf run <CODE>           Single ETF 11-layer penetration (JSON)")
        print("  etf report <CODE>        Full formatted report")
        print("  etf batch [--limit=N]    Batch analysis")
        print("  etf check                Data source health check")
        print("  etf price <CODE>         Live price from best available source")
        print("  etf news [keyword]       Latest finance news")
        print("  etf screen [--top=N] [--profile=均衡]  Full market scan & ranking")
        print("  etf recommend              Quick top-5 recommendation")
        print("  etf compare <A> <B>       Side-by-side comparison of two ETFs")
        print("  etf valu <CODE>            NAV & premium data")
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
        from .data.manager import check_all_sources
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
        from .data.manager import get_price
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
        from .data.manager import get_news
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
        from .decision.screener import screen
        results = screen(top_n=top_n, profile=profile)
        _print_screen_results(results)
    
    elif cmd == "recommend":
        from .decision.screener import recommend
        results = recommend()
        _print_screen_results(results)
    
    elif cmd == "compare":
        if len(args) < 3:
            print("Error: need two ETF codes, e.g. etf compare 159263 159995")
            return
        code_a, code_b = args[1], args[2]
        from .data.valuation import get_valuation
        from .pipeline import run_full
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
        from .data.valuation import get_fund_snapshot
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
    
    else:
        print(f"Unknown command: {cmd}")
        print("Use: etf --help")


if __name__ == "__main__":
    app()