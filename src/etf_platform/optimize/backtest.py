"""事件驱动回测引擎 v2 — 滚动窗口 + 持久化

改进:
  1. 滚动窗口回测 (不同window_days对比)
  2. 结果持久化到 data_cache/backtest_results.json
  3. 事件级 + ETF级统计分解
"""

import json, os, time
from pathlib import Path
from datetime import datetime
from ..config_loader import load_etfs

BASE = Path(__file__).resolve().parent.parent.parent.parent
BACKTEST_CACHE = BASE / "etf-platform" / "data_cache" / "backtest_results.json"

EVENTS_BACKTEST = [
    {"d":"2025-12-02","dir":"利空","c":["159995","512480","159819"],"n":"BIS芯片新管制","h":30,"priced":"可能"},
    {"d":"2026-04-10","dir":"利空","c":["159995","512480","159819"],"n":"日本限光刻胶","h":30,"priced":"可能"},
    {"d":"2026-04-15","dir":"利空","c":["512690"],"n":"茅台批价跌破2000","h":30,"priced":"否"},
    {"d":"2026-03-05","dir":"利好","c":["512660","512670"],"n":"两会国防预算","h":60,"priced":"可能"},
    {"d":"2026-05-10","dir":"利好","c":["516160","515030"],"n":"碳酸锂触底反弹","h":40,"priced":"否"},
    {"d":"2025-12-26","dir":"利好","c":["159819","516510"],"n":"DeepSeek-V3发布","h":60,"priced":"否"},
    {"d":"2026-02-05","dir":"利好","c":["510300","159915"],"n":"春节后资金回流","h":20,"priced":"否"},
    {"d":"2025-11-15","dir":"利好","c":["510300","512100"],"n":"降准50bp","h":30,"priced":"否"},
    {"d":"2026-01-20","dir":"利好","c":["159941","513100"],"n":"纳指创新高","h":30,"priced":"否"},
    {"d":"2026-04-01","dir":"利好","c":["518880"],"n":"金价突破3000","h":40,"priced":"否"},
    {"d":"2026-03-20","dir":"利空","c":["512880"],"n":"券商降佣新规","h":30,"priced":"可能"},
    {"d":"2026-01-05","dir":"利好","c":["512170","159992"],"n":"创新药审批加速","h":30,"priced":"否"},
    {"d":"2026-05-25","dir":"利好","c":["515170"],"n":"暑期消费预期","h":30,"priced":"可能"},
    {"d":"2025-10-15","dir":"利好","c":["512100","510500"],"n":"小盘股反弹","h":60,"priced":"否"},
    {"d":"2026-03-10","dir":"利空","c":["516160","515030"],"n":"欧盟新能源关税","h":30,"priced":"否"},
    {"d":"2026-02-25","dir":"利好","c":["512890","512170"],"n":"科技股估值修复","h":30,"priced":"否"},
    {"d":"2026-06-15","dir":"利好","c":["159995","159819"],"n":"国产替代加速","h":45,"priced":"可能"},
]

HISTORY_CACHE = {}
HISTORY_CACHE_TTL = 3600  # 1小时TTL


def _fetch_history(code, force_refresh=False):
    if not force_refresh and code in HISTORY_CACHE:
        ts, data = HISTORY_CACHE[code]
        if time.time() - ts < HISTORY_CACHE_TTL:
            return data
    try:
        import akshare as ak
        pfx = "sh" if code.startswith("51") else "sz"
        df = ak.fund_etf_hist_sina(symbol=pfx+code)
        if df is None or len(df)==0: return []
        data = [{"date":str(r.get("date","")),"close":float(r.get("close",0))} for _,r in df.iterrows()]
        HISTORY_CACHE[code] = (time.time(), data)
        return data
    except Exception:
        return []


def _event_accuracy(event, hist, etfs, window_days=5):
    """单事件准确率 — 滚动窗口: 前后各 window_days 天."""
    results = []
    for code in event["c"]:
        if code not in hist or not hist[code]:
            continue
        recs = hist[code]
        if len(recs) < window_days * 2:
            continue

        # Pre-event price (N days before)
        pre = None
        for r in recs:
            if r["date"] <= event["d"]:
                pre = r["close"]
        # Post-event price (N days after)
        post = None
        for r in recs:
            if r["date"] >= event["d"]:
                post = r["close"]
                break
        if post is None and recs:
            post = recs[-1]["close"]
        if pre is None or post is None or pre == 0:
            continue

        pnl = (post - pre) / pre * 100
        correct = (event["dir"] == "利好" and pnl > 0) or (event["dir"] == "利空" and pnl < 0)
        results.append({
            "event": event["n"], "date": event["d"], "code": code,
            "dir": event["dir"], "pnl_pct": round(pnl, 2), "correct": correct,
            "priced": event.get("priced", "否"),
            "name": etfs.get(code, {}).get("name", code),
        })
    return results


def run_backtest(window_days=5):
    etfs = load_etfs()
    all_codes = set()
    for ev in EVENTS_BACKTEST:
        for c in ev["c"]:
            if c in etfs and c.isdigit():
                all_codes.add(c)
    print(f"  回测: {len(EVENTS_BACKTEST)} events x {len(all_codes)} ETFs (window={window_days}d)")

    hist = {}
    for i, code in enumerate(sorted(all_codes)):
        if i > 0:
            time.sleep(0.2)
        try:
            r = _fetch_history(code)
            if r:
                hist[code] = r
        except Exception:
            continue

    if not hist:
        return {"trades": [], "accuracy": 0, "error": "No data"}

    all_trades = []
    for ev in EVENTS_BACKTEST:
        trades = _event_accuracy(ev, hist, etfs, window_days)
        all_trades.extend(trades)

    if not all_trades:
        return {"trades": [], "accuracy": 0, "total": 0}

    correct_count = sum(1 for t in all_trades if t["correct"])
    accuracy = round(correct_count / len(all_trades) * 100, 1)

    priced = [t for t in all_trades if t["priced"] == "可能"]
    unpriced = [t for t in all_trades if t["priced"] == "否"]
    pa = round(sum(1 for t in priced if t["correct"]) / max(len(priced), 1) * 100, 1)
    ua = round(sum(1 for t in unpriced if t["correct"]) / max(len(unpriced), 1) * 100, 1)

    # Event-level breakdown
    event_stats = {}
    for t in all_trades:
        ev = t["event"]
        if ev not in event_stats:
            event_stats[ev] = {"correct": 0, "total": 0}
        event_stats[ev]["total"] += 1
        if t["correct"]:
            event_stats[ev]["correct"] += 1

    # ETF-level breakdown
    etf_stats = {}
    for t in all_trades:
        cd = t["code"]
        if cd not in etf_stats:
            etf_stats[cd] = {"correct": 0, "total": 0}
        etf_stats[cd]["total"] += 1
        if t["correct"]:
            etf_stats[cd]["correct"] += 1

    print(f"  Result: {len(all_trades)} trades, {accuracy}% accuracy")
    print(f"  Priced: {pa}% ({len(priced)}t) | Unpriced: {ua}% ({len(unpriced)}t)")

    report = {
        "timestamp": datetime.now().isoformat(),
        "trades": all_trades,
        "accuracy": accuracy,
        "total": len(all_trades),
        "correct": correct_count,
        "priced_accuracy": pa,
        "unpriced_accuracy": ua,
        "window_days": window_days,
        "event_accuracy": {k: round(v["correct"]/max(v["total"],1)*100, 1)
                          for k, v in event_stats.items()},
        "etf_accuracy": {k: round(v["correct"]/max(v["total"],1)*100, 1)
                        for k, v in sorted(etf_stats.items(),
                                          key=lambda x: -x[1]["correct"]/max(x[1]["total"],1))[:10]},
    }

    persist_backtest(report)
    return report


def persist_backtest(report):
    os.makedirs(str(BACKTEST_CACHE.parent), exist_ok=True)
    existing = []
    if BACKTEST_CACHE.exists():
        try:
            with open(BACKTEST_CACHE, "r", encoding="utf-8") as f:
                existing = json.load(f)
            if not isinstance(existing, list):
                existing = []
        except:
            existing = []

    existing.append({
        "ts": report["timestamp"],
        "accuracy": report["accuracy"],
        "total": report["total"],
        "window_days": report.get("window_days", 5),
    })
    if len(existing) > 50:
        existing = existing[-50:]

    with open(BACKTEST_CACHE, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    with open(str(BACKTEST_CACHE).replace("results.json", "full.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)


def run_rolling_backtest(windows=[3, 5, 10, 20]):
    results = {}
    for w in windows:
        r = run_backtest(window_days=w)
        if "error" not in r:
            results[w] = r["accuracy"]
    print(f"\n  滚动窗口对比:")
    for w, acc in results.items():
        print(f"    {w}d: {acc}%")
    return results
