"""ETF每日巡检 + 飞书推送"""
from datetime import datetime
import json, os
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent.parent
PATROL_OUT = BASE / "etf-platform" / "data" / "patrol_latest.json"
FEISHU_OUT = BASE / "data" / "etf_patrol_feishu.md"


def _trend_icon(change):
    return "🟢" if change > 2 else "🟡" if change > -2 else "🔴"


def _risk_icon(score):
    return "🔵" if score >= 7 else "🟡" if score >= 5 else "🟠"


def run_patrol(watchlist=None):
    from ..decision.screener import recommend
    from ..data.kline import get_trend
    if watchlist is None:
        watchlist = [
            ("159185", "HK信息", "defensive"),
            ("159247", "创业板TF", "balanced"),
            ("159131", "港股AI科技", "balanced"),
            ("159146", "电力", "aggressive"),
        ]
    now = datetime.now()
    lines = []
    lines.append("=" * 55)
    lines.append(f"  ETF Daily Patrol - {now.strftime('%Y-%m-%d %H:%M')}")
    lines.append("=" * 55)

    watch_results = []
    for code, name, mode in watchlist:
        try:
            trend = get_trend(code)
            sig = trend.trend_signal if trend else "?"
            chg = trend.change_20d if trend else 0
            icon = _trend_icon(chg)
            lines.append(f"  {icon} {code} {name:<12} {mode:<10} {chg:+.1f}% {sig}")
            watch_results.append({"code": code, "name": name, "change": chg, "signal": sig})
        except Exception as e:
            lines.append(f"  ❓ {code} {name:<12} ERROR: {e}")
            watch_results.append({"code": code, "name": name, "error": str(e)[:50]})

    lines.append("\n  Top 5:")
    top5 = []
    try:
        top5 = recommend(top_n=5, profile="均衡")
        for r in top5:
            lines.append(f"  #{r['rank']} {r['code']} {r['name'][:16]:<18} {r['composite_score']:.1f}")
    except Exception as e:
        lines.append(f"  N/A: {e}")

    lines.append("=" * 55)
    report = "\n".join(lines)
    print(report)

    persist_patrol(now, watch_results, top5, report)
    write_feishu_report(now, watch_results, top5)
    return report


def persist_patrol(now, watch_results, top5, report):
    PATROL_OUT.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "timestamp": now.isoformat(),
        "watchlist": watch_results,
        "recommendations": [
            {"rank": r["rank"], "code": r["code"], "name": r["name"][:20], "score": r["composite_score"]}
            for r in top5
        ] if top5 else [],
    }
    with open(PATROL_OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def write_feishu_report(now, watch_results, top5):
    """生成飞书-compatible的 patrol 报告."""
    date_str = now.strftime("%Y-%m-%d %H:%M")
    rpt = [f"**ETF 每日巡检 — {date_str}**\n"]
    rpt.append("📊 重点标的:")

    for w in watch_results:
        if "error" in w:
            rpt.append(f"- ❓ {w['code']} {w['name']}: {w['error']}")
        else:
            icon = _trend_icon(w["change"])
            rpt.append(f"- {icon} {w['code']} {w['name']}: {w['change']:+.1f}% {w['signal']}")

    if top5:
        rpt.append(f"\n🏆 Top {len(top5)} 推荐:")
        for r in top5:
            icon = _risk_icon(r["composite_score"])
            rpt.append(f"{r['rank']}. {icon} **{r['code']}** {r['name'][:16]} — {r['composite_score']:.1f}分")

    text = "\n".join(rpt)
    FEISHU_OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(FEISHU_OUT, "w", encoding="utf-8") as f:
        f.write(text)
    return text
