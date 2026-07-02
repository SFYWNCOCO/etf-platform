"""
ETF Daily Archive Collector — saves structured snapshots for research/backtesting.

Archive structure:
  data/archive/
  ├── INDEX.json                    # All dates with metadata
  ├── events/timeline.jsonl         # Append-only event log
  └── YYYY-MM-DD/
      ├── snapshot.json             # Full daily snapshot
      ├── rotation.json             # Sector rotation state
      ├── recommendations.json      # Top picks with full scores
      ├── qvix.json                 # Market sentiment (QVIX)
      ├── prices.json               # Key ETF prices
      └── news.json                 # Financial headlines

Usage:
  python -m etf_platform.archive.collector          # Full collection
  python -m etf_platform.archive.collector --quick  # Quick (skip prices/news)
"""
from datetime import datetime, date
import json, os, time
from pathlib import Path
from typing import Optional


ARCHIVE_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "data" / "archive"
EVENTS_FILE = ARCHIVE_ROOT / "events" / "timeline.jsonl"
CACHE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "screener_cache"


def _ensure_dirs(d: Path):
    d.mkdir(parents=True, exist_ok=True)


def _today_str() -> str:
    return date.today().isoformat()


def _now_iso() -> str:
    return datetime.now().isoformat()


def _save_json(path: Path, data: dict):
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    tmp.replace(path)


# ============================================================
# Collectors
# ============================================================

def collect_rotation() -> dict:
    """Capture current sector rotation state."""
    try:
        from ..analysis.rotation import detect_rotation
        result = detect_rotation()
        sectors = []
        if isinstance(result, dict):
            for s in result.get("sectors", []):
                sectors.append({
                    "sector": s.get("sector", "?"),
                    "change_pct": s.get("change_pct", 0),
                    "signal": s.get("signal", "?"),
                    "volume": s.get("volume", 0),
                })
        return {
            "timestamp": _now_iso(),
            "sectors": sectors,
            "leaders": result.get("leaders", []) if isinstance(result, dict) else [],
            "laggards": result.get("laggards", []) if isinstance(result, dict) else [],
        }
    except Exception as e:
        return {"timestamp": _now_iso(), "error": str(e)[:200], "sectors": []}


def collect_recommendations(profiles: list = None) -> dict:
    """Capture top recommendations using CACHED scan data (fast, no API calls)."""
    if profiles is None:
        profiles = ["保守", "均衡", "进取"]
    
    result = {"timestamp": _now_iso(), "profiles": {}}
    
    for profile in profiles:
        try:
            # Use cached scan data
            cache_file = CACHE_DIR / f"scan_{profile}.json"
            if not cache_file.exists():
                cache_file = CACHE_DIR / "scan_均衡.json"
            if not cache_file.exists():
                result["profiles"][profile] = {"error": "no_cache", "top10": []}
                continue
            
            with open(cache_file, "r", encoding="utf-8") as f:
                cached = json.load(f)
            
            from ..decision.screener import (
                _compute_composite, _compute_auto_weights, _detect_dead_layers,
                NON_INVESTMENT_SECTORS, RISK_SAFE_THRESHOLD, RISK_ELASTIC_THRESHOLD,
            )
            
            dead = _detect_dead_layers(cached)
            weights = _compute_auto_weights(cached, profile, dead)
            
            ranked = []
            for r in cached:
                code = r.get("etf_code", "")
                sector = r.get("sector", "")
                if sector in NON_INVESTMENT_SECTORS:
                    continue
                ls = r.get("layer_scores", {})
                composite = _compute_composite(ls, weights)
                ranked.append({
                    "code": code, "name": r.get("name", code)[:30],
                    "score": round(composite, 2), "sector": sector,
                    "risk": round(r.get("risk_level", 0), 2),
                    "_ls": ls,
                })
            
            ranked.sort(key=lambda x: -x["score"])
            
            # Build l003 insight
            safe_mode, catalyst_mode = [], []
            for item in ranked[:30]:
                ls = item["_ls"]
                l8, l9 = ls.get("L8_CapitalFlow", 5), ls.get("L9_Signals", 5)
                momentum = l8 + l9
                if item["score"] >= RISK_SAFE_THRESHOLD:
                    safe_mode.append({"code": item["code"], "name": item["name"], "score": item["score"], "sector": item["sector"]})
                if item["score"] < RISK_ELASTIC_THRESHOLD and momentum > 8.0:
                    catalyst_mode.append({"code": item["code"], "name": item["name"], "score": item["score"], "momentum": round(momentum, 1), "elasticity": round(momentum / max(item["score"], 0.1), 1), "sector": item["sector"]})
            
            # Strip internal _ls
            top10_clean = [{k: v for k, v in item.items() if k != "_ls"} for item in ranked[:10]]
            
            result["profiles"][profile] = {
                "top10": top10_clean,
                "l003_insight": {
                    "note": "穿透评分是风险指标不是收益指标。高分=安全缺催化剂，低分=高弹性短窗口。",
                    "safe_mode": safe_mode[:5],
                    "catalyst_mode": catalyst_mode[:5],
                },
                "total_etfs": len(ranked),
            }
        except Exception as e:
            result["profiles"][profile] = {"error": str(e)[:200], "top10": []}
    
    return result


def collect_qvix() -> dict:
    """Capture QVIX market sentiment data."""
    try:
        from ..analysis.qvix_regime import get_regime, get_weight_shift
        regime = get_regime()
        return {
            "timestamp": _now_iso(),
            "regime": regime.get("regime", "unknown"),
            "qvix_50": regime.get("qvix_50", 0),
            "qvix_500": regime.get("qvix_500", 0),
            "qvix_gem": regime.get("qvix_gem", 0),
            "interpretation": regime.get("interpretation", ""),
        }
    except Exception as e:
        return {"timestamp": _now_iso(), "error": str(e)[:200]}


def collect_prices(codes: list = None) -> dict:
    """Capture live prices for key ETFs."""
    if codes is None:
        codes = [
            "510300", "510050", "510500", "159919",
            "159995", "512480", "159819", "515030",
            "512890", "563300", "518880", "512690",
            "512760", "516510",
        ]
    
    result = {"timestamp": _now_iso(), "prices": {}}
    for code in codes:
        try:
            from ..data.kline import get_trend
            trend = get_trend(code)
            if trend:
                result["prices"][code] = {
                    "price": trend.price,
                    "change_5d": round(trend.change_5d, 2),
                    "change_20d": round(trend.change_20d, 2),
                    "signal": trend.trend_signal,
                    "position_pct": round(trend.position_pct, 1),
                    "max_drawdown": round(trend.max_drawdown, 2),
                }
        except Exception:
            result["prices"][code] = None
    
    return result


def collect_news() -> dict:
    """Capture top financial news headlines."""
    try:
        from ..data.manager import get_news
        keywords = ["A股", "ETF", "央行", "芯片", "新能源", "黄金", "红利"]
        result = {"timestamp": _now_iso(), "headlines": {}}
        for kw in keywords:
            try:
                items = get_news(kw, limit=3)
                result["headlines"][kw] = [
                    {"title": n.title[:80], "source": n.source} for n in items
                ]
            except Exception:
                result["headlines"][kw] = []
        return result
    except Exception as e:
        return {"timestamp": _now_iso(), "error": str(e)[:200]}


# ============================================================
# Archive operations
# ============================================================

def collect_full_snapshot(quick: bool = False) -> dict:
    """Run all collectors and save to archive."""
    today = _today_str()
    day_dir = ARCHIVE_ROOT / today
    _ensure_dirs(day_dir)
    
    snapshot = {"date": today, "collected_at": _now_iso(), "quick_mode": quick}
    
    print("  [1/4] 行业轮动...")
    rotation = collect_rotation()
    snapshot["rotation"] = rotation
    _save_json(day_dir / "rotation.json", rotation)
    
    print("  [2/4] 推荐排名(缓存)...")
    recs = collect_recommendations()
    snapshot["recommendations"] = recs
    _save_json(day_dir / "recommendations.json", recs)
    
    print("  [3/4] QVIX市场情绪...")
    qvix = collect_qvix()
    snapshot["qvix"] = qvix
    _save_json(day_dir / "qvix.json", qvix)
    
    if not quick:
        print("  [4/4] 价格+新闻...")
        prices = collect_prices()
        snapshot["prices"] = prices
        _save_json(day_dir / "prices.json", prices)
        
        news = collect_news()
        snapshot["news"] = news
        _save_json(day_dir / "news.json", news)
    
    _save_json(day_dir / "snapshot.json", snapshot)
    _update_index(snapshot)
    log_event("daily_collection", {"date": today, "mode": "quick" if quick else "full"})
    
    return snapshot


def _update_index(snapshot: dict):
    _ensure_dirs(ARCHIVE_ROOT)
    index_file = ARCHIVE_ROOT / "INDEX.json"
    
    index = []
    if index_file.exists():
        try:
            with open(index_file, "r", encoding="utf-8") as f:
                index = json.load(f)
        except Exception:
            index = []
    
    date_str = snapshot["date"]
    index = [e for e in index if e.get("date") != date_str]
    
    qvix = snapshot.get("qvix", {})
    rotation = snapshot.get("rotation", {})
    recs = snapshot.get("recommendations", {})
    eq = recs.get("profiles", {}).get("均衡", {}).get("top10", [])
    
    entry = {
        "date": date_str,
        "collected_at": snapshot["collected_at"],
        "quick_mode": snapshot.get("quick_mode", False),
        "qvix_regime": qvix.get("regime", "?"),
        "qvix_50": qvix.get("qvix_50", 0),
        "rotation_leaders": rotation.get("leaders", [])[:3],
        "rotation_laggards": rotation.get("laggards", [])[:3],
        "top_pick": {"code": eq[0]["code"], "name": eq[0]["name"], "score": eq[0]["score"]} if eq else None,
    }
    
    index.append(entry)
    index.sort(key=lambda x: x["date"], reverse=True)
    
    with open(index_file, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2, default=str)


def log_event(event_type: str, data: dict):
    """Append an event to the timeline (JSONL format)."""
    _ensure_dirs(EVENTS_FILE.parent)
    event = {"timestamp": _now_iso(), "type": event_type, **data}
    with open(EVENTS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")


def list_archives() -> list:
    index_file = ARCHIVE_ROOT / "INDEX.json"
    if not index_file.exists():
        return []
    with open(index_file, "r", encoding="utf-8") as f:
        return json.load(f)


def load_day(date_str: str) -> Optional[dict]:
    snapshot_file = ARCHIVE_ROOT / date_str / "snapshot.json"
    if not snapshot_file.exists():
        return None
    with open(snapshot_file, "r", encoding="utf-8") as f:
        return json.load(f)


def load_events(limit: int = 50, event_type: str = None) -> list:
    if not EVENTS_FILE.exists():
        return []
    events = []
    with open(EVENTS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    ev = json.loads(line)
                    if event_type is None or ev.get("type") == event_type:
                        events.append(ev)
                except Exception:
                    pass
    return events[-limit:]


# ============================================================
# CLI
# ============================================================

if __name__ == "__main__":
    import sys
    quick = "--quick" in sys.argv
    print(f"\n  ETF 每日数据采集 {'(快速模式)' if quick else '(完整模式)'}")
    print(f"  {'='*50}")
    t0 = time.time()
    snap = collect_full_snapshot(quick=quick)
    elapsed = time.time() - t0
    
    print(f"\n  采集完成 ({elapsed:.0f}s)")
    print(f"  日期: {snap['date']}")
    print(f"  存档: {ARCHIVE_ROOT / snap['date']}")
    
    idx = list_archives()
    print(f"  历史: {len(idx)} 天归档")
    
    qvix = snap.get("qvix", {})
    if "regime" in qvix:
        print(f"  QVIX: {qvix['regime']} (50={qvix.get('qvix_50', '?')})")
    
    rotation = snap.get("rotation", {})
    leaders = rotation.get("leaders", [])
    if leaders:
        print(f"  领涨: {', '.join(leaders[:3])}")
    
    recs = snap.get("recommendations", {}).get("profiles", {}).get("均衡", {}).get("top10", [])
    if recs:
        print(f"  Top推荐: {recs[0]['code']} {recs[0]['name']} ({recs[0]['score']})")
