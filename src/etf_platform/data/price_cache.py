"""price_cache.py — Persistent ETF price cache with TTL (v16.17).

Offline-first: prices are read from disk cache first, API is used only
when cache is stale or missing. A cron job refreshes the cache daily.

Cache file: data/price_cache.json
Format: {"updated": "ISO", "count": N, "prices": {code: {price, change_pct, name}}}
"""

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_CACHE_FILE = Path(__file__).resolve().parent.parent.parent.parent / "data" / "price_cache.json"
# Trading hours: cache valid for 4 hours. Non-trading: valid for 24 hours.
_CACHE_TTL_TRADING = 4 * 3600
_CACHE_TTL_IDLE = 24 * 3600

# v17: In-memory cache to avoid repeated JSON file reads
_mem_cache: dict = {"data": None, "ts": 0, "file_mtime": 0}
_MEM_CACHE_TTL = 60  # 60s memory TTL


def _is_trading_time() -> bool:
    """Rough check: A-share trading hours Mon-Fri 9:30-15:00."""
    from datetime import datetime
    now = datetime.now()
    if now.weekday() >= 5:  # weekend
        return False
    minutes = now.hour * 60 + now.minute
    return 570 <= minutes < 900  # 9:30-15:00


def load_cache() -> dict:
    """Load price cache from disk. Returns {code: {price, change_pct, name}} or {}.
    v17: In-memory cache avoids repeated JSON reads for each ETF in a batch."""
    import time as _time
    now = _time.time()
    # Check memory cache
    if _mem_cache["data"] is not None and (now - _mem_cache["ts"]) < _MEM_CACHE_TTL:
        # Verify file hasn't changed since cache
        try:
            mtime = _CACHE_FILE.stat().st_mtime if _CACHE_FILE.exists() else 0
            if mtime == _mem_cache["file_mtime"]:
                return _mem_cache["data"]
        except OSError:
                logger.warning("silent catch in price_cache.py:49 - needs review")
    if not _CACHE_FILE.exists():
        return {}
    try:
        data = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
        updated = data.get("updated", "")
        if not updated:
            return {}
        # Check TTL
        try:
            from datetime import datetime
            ts = datetime.fromisoformat(updated)
            age = (datetime.now() - ts).total_seconds()
            ttl = _CACHE_TTL_TRADING if _is_trading_time() else _CACHE_TTL_IDLE
            if age > ttl:
                logger.info("price_cache: expired (age=%.0fs, ttl=%ds)", age, ttl)
                return {}
        except (ValueError, TypeError):
            return {}
        prices = data.get("prices", {})
        # Save to memory cache
        _mem_cache["data"] = prices
        _mem_cache["ts"] = now
        try:
            _mem_cache["file_mtime"] = _CACHE_FILE.stat().st_mtime
        except OSError:
            _mem_cache["file_mtime"] = 0
        return prices
    except (json.JSONDecodeError, OSError, KeyError) as e:
        logger.warning("price_cache: load failed: %s", e)
        return {}


def save_cache(prices: dict) -> bool:
    """Save price cache to disk. Returns True on success."""
    from datetime import datetime
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "updated": datetime.now().isoformat(),
            "count": len(prices),
            "prices": prices,
        }
        _CACHE_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("price_cache: saved %d prices", len(prices))
        return True
    except (OSError, json.JSONDecodeError, ValueError) as e:
        logger.error("price_cache: save failed: %s", e)
        return False


def get_cached_price(code: str) -> Optional[dict]:
    """Get single cached price. Returns {price, change_pct, name} or None."""
    cache = load_cache()
    return cache.get(code)


def get_cached_prices(codes: list = None) -> dict:
    """Get multiple cached prices. Returns {code: {price, change_pct, name}}."""
    cache = load_cache()
    if codes:
        return {c: cache[c] for c in codes if c in cache}
    return cache


def refresh_all(limit: int = 600) -> dict:
    """Fetch all ETF prices from API sources and save to cache.

    Uses the existing data manager's EastMoney→Sina→AKShare fallback chain.
    Returns the price dict that was saved.
    """
    from .manager import get_price

    # Load ETF list
    try:
        from etf_platform.config_loader import load_etfs
        etfs = load_etfs()
    except Exception as e:
        logger.warning("price_cache: load_etfs failed: %s", e)
        return {}

    codes = [c for c in etfs if c.isdigit()][:limit]
    prices = {}
    fail = 0

    for code in codes:
        try:
            snap, source = get_price(code)
            if snap and snap.price > 0:
                prices[code] = {
                    "price": snap.price,
                    "change_pct": snap.change_pct,
                    "name": snap.name or etfs.get(code, {}).get("name", code),
                    "source": source,
                }
            else:
                fail += 1
        except Exception as e:
            logger.warning("price_cache: fetch failed for %s: %s", code, e)
            fail += 1

    if prices:
        save_cache(prices)

    logger.info("price_cache: refreshed %d/%d (failed=%d)", len(prices), len(codes), fail)
    return prices


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = refresh_all()
    print(f"Refreshed {len(result)} prices to {_CACHE_FILE}")
