"""CLI entry point for ETF platform."""
import sys
import json
from .pipeline import run_full, batch_full, format_full


def app():
    """CLI dispatcher: etf <command> [args...]"""
    args = sys.argv[1:] if len(sys.argv) > 1 else []
    
    if not args or args[0] in ("-h", "--help"):
        print("Usage:")
        print("  etf run <CODE>           Single ETF 11-layer penetration")
        print("  etf batch [--limit=N]    Batch all buyable ETFs")
        print("  etf report <CODE>        Full report (stdout)")
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
        print(json.dumps(results, ensure_ascii=False, indent=2)[:5000])
        print("... (truncated)")
    
    else:
        print(f"Unknown command: {cmd}")
        print("Use: etf --help")


if __name__ == "__main__":
    app()
