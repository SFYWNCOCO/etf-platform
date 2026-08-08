"""kline.py — Multi-source kline data. Tencent primary, Sina fallback."""
from ..utils import sina_code
import urllib.request
import urllib.error
import json
import statistics
import threading
import logging
from typing import Optional, Dict
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TrendSnapshot:
    code: str = ""
    price: float = 0.0
    change_5d: float = 0.0
    change_10d: float = 0.0
    change_20d: float = 0.0
    change_60d: float = 0.0
    high_60d: float = 0.0
    low_60d: float = 0.0
    position_pct: float = 50.0
    max_drawdown: float = 0.0
    volatility_20d: float = 0.0
    volume_ratio_5_20: float = 1.0
    trend_signal: str = "neutral"
    data_days: int = 0


SINA_KLINE_URL = "http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol=%s%s&scale=240&ma=no&datalen=%d"
TENCENT_KLINE_URL = "http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=%s%s,day,,,%d,qfq"

# Session cache: get_trend results (persists across calls in the same run)
_trend_cache = {}
_TREND_CACHE_LOCK = threading.Lock()

# Disk cache: kline trends survive across runs (daily klines don't change intraday)
# TTL: 6h — market-close data stable; intraday runs reuse yesterday's close trend.
import os
import time as _time
import dataclasses
from pathlib import Path

_KLINE_DISK_CACHE_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "kline_trend_cache.json"
_KLINE_DISK_TTL = 6 * 3600  # 6 hours
_kline_disk_loaded = False


def _load_disk_cache() -> dict:
    global _kline_disk_loaded
    if _kline_disk_loaded:
        return _trend_cache
    _kline_disk_loaded = True
    try:
        if _KLINE_DISK_CACHE_PATH.exists():
            raw = json.loads(_KLINE_DISK_CACHE_PATH.read_text(encoding="utf-8"))
            now = _time.time()
            for code, blob in raw.items():
                if now - blob.get("_ts", 0) > _KLINE_DISK_TTL:
                    continue
                fields = {k: v for k, v in blob.items() if k != "_ts"}
                try:
                    _trend_cache[code] = TrendSnapshot(**fields)
                except TypeError:
                    continue
    except (OSError, ValueError, json.JSONDecodeError) as e:
        logger.debug("kline disk cache load failed: %s", e)
    return _trend_cache


def _save_disk_cache():
    try:
        with _TREND_CACHE_LOCK:
            snapshot = {}
            now = _time.time()
            for code, ts in _trend_cache.items():
                d = dataclasses.asdict(ts)
                d["_ts"] = now
                snapshot[code] = d
        _KLINE_DISK_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _KLINE_DISK_CACHE_PATH.write_text(
            json.dumps(snapshot, ensure_ascii=False), encoding="utf-8"
        )
    except (OSError, ValueError) as e:
        logger.debug("kline disk cache save failed: %s", e)


def clear_trend_cache():
    with _TREND_CACHE_LOCK:
        _trend_cache.clear()




def _fetch_kline(code: str, days: int = 63) -> Optional[list]:
    """Fetch kline data, trying Tencent first then Sina fallback."""
    # Try Tencent (primary, works as of 2026-07)
    try:
        prefix = sina_code(code)
        url = TENCENT_KLINE_URL % (prefix, code, min(days, 200))
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
        data = json.loads(raw)
        rows = data.get("data", {}).get(f"{prefix}{code}", {}).get("qfqday", [])
        if rows and len(rows) >= 5:
            result = []
            for r in rows:
                result.append({
                    "date": r[0], "open": r[1], "close": r[2],
                    "high": r[3], "low": r[4], "volume": r[5],
                })
            return result
    except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
        logger.debug("Tencent kline fetch failed: %s", e)
        pass
    # Fallback to Sina
    try:
        prefix = sina_code(code)
        url = SINA_KLINE_URL % (prefix, code, min(days, 1024))
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0", "Referer": "http://finance.sina.com.cn/"
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("gbk")
        rows = json.loads(raw)
        if rows and len(rows) >= 5:
            return rows
    except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
        logger.debug("Sina kline fallback failed: %s", e)
        pass
    return None


def get_trend(code: str, days: int = 63) -> Optional[TrendSnapshot]:
    """Fetch kline data and compute trend indicators. (session + disk cached)"""
    _load_disk_cache()
    with _TREND_CACHE_LOCK:
        if code in _trend_cache:
            return _trend_cache[code]
    rows = _fetch_kline(code, days)
    if not rows:
        return None

    close_list = [float(r["close"]) for r in rows]
    high_list = [float(r["high"]) for r in rows]
    low_list = [float(r["low"]) for r in rows]
    vol_list = [float(r["volume"]) for r in rows]
    total = len(close_list)
    latest = round(close_list[-1], 3)

    def chg(n):
        return ((close_list[-1] / close_list[-n-1]) - 1) * 100 if total > n else 0.0

    c5 = chg(5) if total >= 6 else 0.0
    c10 = chg(10) if total >= 11 else 0.0
    c20 = chg(20) if total >= 21 else (chg(total-1) if total > 1 else 0.0)
    c60 = chg(60) if total >= 61 else (chg(total-1) if total > 1 else 0.0)

    recent = close_list[-60:] if total >= 60 else close_list
    h60 = max(recent)
    l60 = min(recent)
    pos = (latest - l60) / (h60 - l60) * 100 if h60 > l60 else 50.0

    peak = close_list[0]
    dd = 0.0
    for p in close_list:
        if p > peak:
            peak = p
        dd = min(dd, (p - peak) / peak * 100)

    r_list = [(close_list[i]/close_list[i-1]-1) for i in range(1, total)]
    r20 = r_list[-20:] if len(r_list) >= 20 else r_list
    vol_20d = statistics.stdev(r20) * (252**0.5) * 100 if len(r20) > 1 else 0.0

    if len(vol_list) >= 5:
        v5 = sum(vol_list[-5:])/5
        v20 = sum(vol_list[-20:])/20 if len(vol_list) >= 20 else sum(vol_list)/len(vol_list)
        vr = v5/v20 if v20 > 0 else 1.0
    else:
        vr = 1.0

    if pos < 15:
        signal = "oversold"
    elif pos < 35:
        signal = "weak"
    elif pos < 65:
        signal = "neutral"
    elif pos < 85:
        signal = "strong"
    else:
        signal = "overbought"

    if c5 < -5 and signal in ("weak", "oversold"):
        signal = "plunging"
    elif c5 > 5 and signal in ("strong", "overbought"):
        signal = "surging"

    ts = TrendSnapshot(
        code=code, price=latest,
        change_5d=round(c5, 2), change_10d=round(c10, 2),
        change_20d=round(c20, 2), change_60d=round(c60, 2),
        high_60d=round(h60, 3), low_60d=round(l60, 3),
        position_pct=round(pos, 1), max_drawdown=round(dd, 1),
        volatility_20d=round(vol_20d, 1), volume_ratio_5_20=round(vr, 2),
        trend_signal=signal, data_days=total,
    )
    with _TREND_CACHE_LOCK:
        _trend_cache[code] = ts
    _save_disk_cache()
    return ts


def get_trend_batch(codes: list, parallel: bool = True, max_workers: int = 8) -> Dict[str, TrendSnapshot]:
    """Batch trend fetch. parallel=True uses ThreadPoolExecutor for concurrent HTTP requests."""
    if not parallel or len(codes) <= 3:
        result = {}
        for code in codes:
            try:
                t = get_trend(code)
                if t:
                    result[code] = t
            except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
                logger.debug("get_trend failed for code: %s", e)
                continue
        return result

    from concurrent.futures import ThreadPoolExecutor, as_completed
    result = {}
    with ThreadPoolExecutor(max_workers=min(max_workers, len(codes))) as ex:
        futures = {ex.submit(get_trend, code): code for code in codes}
        for f in as_completed(futures):
            code = futures[f]
            try:
                t = f.result(timeout=30)
                if t:
                    result[code] = t
            except (urllib.error.URLError, OSError, ValueError, KeyError, Exception) as e:
                logger.debug("get_trend failed for %s: %s", code, e)
    return result


if __name__ == "__main__":
    sig_map = {"oversold": "超卖", "weak": "回调", "neutral": "中性",
               "strong": "强势", "overbought": "超买", "plunging": "急跌", "surging": "急涨"}
    for code in ["512890", "159995", "159819", "518880"]:
        t = get_trend(code)
        if t and t.data_days > 0:
            sig = sig_map.get(t.trend_signal, "?")
            print("%s: %.3f | 5d=%+.1f%% 10d=%+.1f%% 20d=%+.1f%% 60d=%+.1f%% | pos=%.0f%% | %s (data=%ddays, dd=%.1f%%)" % (
                code, t.price, t.change_5d, t.change_10d, t.change_20d, t.change_60d,
                t.position_pct, sig, t.data_days, t.max_drawdown))
