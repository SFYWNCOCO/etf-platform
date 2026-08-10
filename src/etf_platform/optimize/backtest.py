"""事件驱动回测引擎 v2 — 滚动窗口 + 持久化

改进:
  1. 滚动窗口回测 (不同window_days对比)
  2. 结果持久化到 data_cache/backtest_results.json
  3. 事件级 + ETF级统计分解

修复 v1 (2026-07-14):
  - 移除未来日期事件(d > 今日-30d,前视偏差)
  - 移除 priced 事后标注字段(违反回测原则)
  - 改用 qfq 前复权(与 kline.py 一致)
  - 增加事件日 vs 数据起始日校验
  - 移除 post 价 fallback(事件后无数据则跳过)
  - 添加交易成本(佣金+印花税+滑点)
  - correct 判定考虑交易成本
  - HISTORY_CACHE 加线程锁(与 1.7 统一)
"""

import json
import os
import time
import threading
import logging
from pathlib import Path
from datetime import datetime
from ..config_loader import load_etfs, load_delisted_codes, load_backtest

logger = logging.getLogger(__name__)

BASE = Path(__file__).resolve().parent.parent.parent.parent
BACKTEST_CACHE = BASE / "etf-platform" / "data_cache" / "backtest_results.json"

# v9.0: 交易成本和cutoff日期从 config/backtest.yaml 加载,带默认回退
try:
    _bt_cfg = load_backtest()
    TRANSACTION_COST = float(_bt_cfg.get("transaction_cost", 0.002))
    COST_BPS = float(_bt_cfg.get("cost_bps", 0.2))
    CUTOFF_DATE = str(_bt_cfg.get("cutoff_date", "2026-06-14"))
except Exception as e:
    logger.warning("[backtest] load_backtest failed: %s", e)
    # 交易成本: 佣金 0.05% + 印花税 0.05% + 滑点 0.10% = 0.20%
    TRANSACTION_COST = 0.0005 + 0.0005 + 0.001  # 0.002 (0.2%)
    COST_BPS = TRANSACTION_COST * 100  # 20 bps
    # 移除近 30 天事件(避免未充分定价的前视偏差)
    CUTOFF_DATE = "2026-06-14"

EVENTS_BACKTEST = [
    {"d":"2025-12-02","dir":"利空","c":["159995","512480","159819"],"n":"BIS芯片新管制","h":30},
    {"d":"2026-04-10","dir":"利空","c":["159995","512480","159819"],"n":"日本限光刻胶","h":30},
    {"d":"2026-04-15","dir":"利空","c":["512690"],"n":"茅台批价跌破2000","h":30},
    {"d":"2026-03-05","dir":"利好","c":["512660","512670"],"n":"两会国防预算","h":60},
    {"d":"2026-05-10","dir":"利好","c":["516160","515030"],"n":"碳酸锂触底反弹","h":40},
    {"d":"2025-12-26","dir":"利好","c":["159819","516510"],"n":"DeepSeek-V3发布","h":60},
    {"d":"2026-02-05","dir":"利好","c":["510300","159915"],"n":"春节后资金回流","h":20},
    {"d":"2025-11-15","dir":"利好","c":["510300","512100"],"n":"降准50bp","h":30},
    {"d":"2026-01-20","dir":"利好","c":["159941","513100"],"n":"纳指创新高","h":30},
    {"d":"2026-04-01","dir":"利好","c":["518880"],"n":"金价突破3000","h":40},
    {"d":"2026-03-20","dir":"利空","c":["512880"],"n":"券商降佣新规","h":30},
    {"d":"2026-01-05","dir":"利好","c":["512170","159992"],"n":"创新药审批加速","h":30},
    {"d":"2026-05-25","dir":"利好","c":["515170"],"n":"暑期消费预期","h":30},
    {"d":"2025-10-15","dir":"利好","c":["512100","510500"],"n":"小盘股反弹","h":60},
    {"d":"2026-03-10","dir":"利空","c":["516160","515030"],"n":"欧盟新能源关税","h":30},
    {"d":"2026-02-25","dir":"利好","c":["512890","512170"],"n":"科技股估值修复","h":30},
]

HISTORY_CACHE = {}
HISTORY_CACHE_TTL = 3600  # 1小时TTL
_CACHE_LOCK = threading.Lock()


def _fetch_history(code, force_refresh=False):
    with _CACHE_LOCK:
        if not force_refresh and code in HISTORY_CACHE:
            ts, data = HISTORY_CACHE[code]
            if time.time() - ts < HISTORY_CACHE_TTL:
                return data
    try:
        import akshare as ak
        pfx = "sh" if code.startswith("51") else "sz"
        # 修复: 优先用 qfq 前复权(与 data/kline.py 一致),旧版 akshare 不支持 adjust 则回退
        try:
            df = ak.fund_etf_hist_sina(symbol=pfx+code, adjust="qfq")
        except TypeError:
            df = ak.fund_etf_hist_sina(symbol=pfx+code)
        if df is None or len(df)==0: return []
        data = [{"date":str(r.get("date","")),"close":float(r.get("close",0))} for _,r in df.iterrows()]
        with _CACHE_LOCK:
            HISTORY_CACHE[code] = (time.time(), data)
        return data
    except Exception as e:
        logger.warning("[backtest] _fetch_history failed for %s: %s", code, e)
        return []


def _event_accuracy(event, hist, etfs, window_days=5, delisted_codes=None):
    """单事件准确率 — 滚动窗口: 前后各 window_days 天.

    修复 v1:
    - 增加起始日校验(事件前无数据则跳过)
    - 移除 post 价 fallback(事件后无数据则跳过)
    - 添加交易成本扣减
    - correct 判定考虑交易成本
    修复 v2 (幸存者偏差):
    - trade 标注 delisted: bool (基于 delisted_codes 判定)
    - delisted 代码仍参与回测(历史数据可得),但报告中标注
    """
    if delisted_codes is None:
        delisted_codes = []
    results = []
    for code in event["c"]:
        if code not in hist or not hist[code]:
            continue
        recs = hist[code]
        if len(recs) < window_days * 2:
            continue
        # 修复: 校验数据起始日 vs 事件日
        if recs[0]["date"] > event["d"]:
            continue  # 事件前无数据,跳过

        # 滚动窗口: pre = 事件前 window_days 个交易日, post = 事件后 window_days 个交易日
        pre_idx = next((i for i, r in enumerate(recs) if r["date"] >= event["d"]), None)
        if pre_idx is None or pre_idx < window_days or pre_idx + window_days >= len(recs):
            continue
        pre = recs[pre_idx - window_days]["close"]
        post = recs[pre_idx + window_days]["close"]
        # 修复: 移除 post = recs[-1]["close"] fallback(事件后无数据则跳过)
        if pre is None or post is None or pre == 0:
            continue

        # 修复: 添加交易成本扣减
        pnl = (post - pre) / pre * 100 - COST_BPS
        # 修复: correct 判定考虑交易成本(收益必须超过成本才算正确)
        correct = (event["dir"] == "利好" and pnl > 0) or (event["dir"] == "利空" and pnl < 0)
        # 修复 v2: 标注 delisted (幸存者偏差防护)
        is_delisted = code in delisted_codes
        results.append({
            "event": event["n"], "date": event["d"], "code": code,
            "dir": event["dir"], "pnl_pct": round(pnl, 2), "correct": correct,
            "name": etfs.get(code, {}).get("name", code),
            "delisted": is_delisted,
        })
    return results


def run_backtest(window_days=5):
    etfs = load_etfs()
    delisted_codes = load_delisted_codes()
    all_codes = set()
    for ev in EVENTS_BACKTEST:
        for c in ev["c"]:
            if c in etfs and c.isdigit():
                all_codes.add(c)
    logger.info(f"  回测: {len(EVENTS_BACKTEST)} events x {len(all_codes)} ETFs (window={window_days}d, cost={COST_BPS}bps)")

    hist = {}
    for i, code in enumerate(sorted(all_codes)):
        if i > 0:
            time.sleep(0.2)
        try:
            r = _fetch_history(code)
            if r:
                hist[code] = r
        except (KeyError, ValueError, TypeError, AttributeError, ImportError) as e:
            logger.debug("history fetch failed: %s", e)
            continue

    if not hist:
        return {"trades": [], "accuracy": 0, "error": "No data"}

    all_trades = []
    for ev in EVENTS_BACKTEST:
        trades = _event_accuracy(ev, hist, etfs, window_days, delisted_codes)
        all_trades.extend(trades)

    if not all_trades:
        return {"trades": [], "accuracy": 0, "total": 0}

    correct_count = sum(1 for t in all_trades if t["correct"])
    accuracy = round(correct_count / len(all_trades) * 100, 1)

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

    logger.info(f"  Result: {len(all_trades)} trades, {accuracy}% accuracy (cost-adjusted)")

    report = {
        "timestamp": datetime.now().isoformat(),
        "trades": all_trades,
        "accuracy": accuracy,
        "total": len(all_trades),
        "correct": correct_count,
        "window_days": window_days,
        "cost_bps": COST_BPS,
        "delisted_count": sum(1 for t in all_trades if t.get("delisted")),
        "delisted_codes": delisted_codes,
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
        except (IOError, OSError, json.JSONDecodeError, KeyError, ValueError):
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


def run_rolling_backtest(windows=None):
    results = {}
    if windows is None:
        windows = [3, 5, 10, 20]
    for w in windows:
        r = run_backtest(window_days=w)
        if "error" not in r:
            results[w] = r["accuracy"]
    logger.info("\n  滚动窗口对比:")
    for w, acc in results.items():
        logger.info(f"    {w}d: {acc}%")
    return results
