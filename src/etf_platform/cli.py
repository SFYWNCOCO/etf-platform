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
    print(f"\n  {'='*60}")
    print(f"  ETF \u63a8\u8350\u6392\u540d")
    print(f"  {'='*60}")
    print(f"  {'#':<3} {'\u4ee3\u7801':<8} {'\u540d\u79f0':<24} {'\u884c\u4e1a':<12} {'\u603b\u5206':<6} {'\u98ce\u9669':<6}")
    print(f"  {'-'*60}")
    for r in results:
        rl = r.get('risk_level', 0)
        risk_icon = "\U0001f7e2" if rl < 0.3 else ("\U0001f7e1" if rl < 0.6 else "\U0001f534")
        print(f"  {r['rank']:<3} {r['code']:<8} {r['name'][:22]:<24} {r['sector'][:10]:<12} {r['composite_score']:<6.1f} {risk_icon}{rl:.2f}")
    print(f"  {'='*60}")
    print(f"  \u6838\u5fc3\u7406\u7531:")
    for r in results[:5]:
        print(f"  #{r['rank']} {r['name']}")
        print(f"      {r['reason']}")
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
    
    else:
        print(f"Unknown command: {cmd}")
        print("Use: etf --help")


if __name__ == "__main__":
    app()