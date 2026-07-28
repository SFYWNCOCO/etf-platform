"""Data source manager: handles priority, fallback, and health checking."""
import time
import threading
import logging
from typing import Optional, List, Dict, Tuple
from .base import PriceSource, NewsSource, PriceSnapshot, NewsItem, DataHealth, SourceStatus
from .eastmoney import EastMoneySource
from .sina import SinaSource
from .akshare_source import AKShareSource
from .news import WallStreetCNSource, Kr36Source, TencentSource, SinaNewsSource, BackupNewsSource

logger = logging.getLogger(__name__)

# Priority order for price sources
_PRICE_SOURCES: List[PriceSource] = [
    EastMoneySource(),   # Primary: fast, free
    SinaSource(),        # Fallback 1: very stable
    AKShareSource(),     # Fallback 2: auto-maintained
]

# News sources
_NEWS_SOURCES: List[NewsSource] = [
    WallStreetCNSource(),    # Primary: 华尔街见闻 (专业财经)
    Kr36Source(),            # Tech/VC: 36氪 (科技赛道)
    SinaNewsSource(),        # Finance: 新浪财经 (行业分类新闻)
    TencentSource(),         # General: 腾讯新闻
    BackupNewsSource(),     # Fallback
]
# v5.6: Removed WeiboSource (social noise, relevance=0.6) and V2EXSource (tech forum, relevance=0.4).
# Both contributed noise without ETF-actionable signals.

# Cache for last successful source per code
_last_price_source: Dict[str, str] = {}
_LAST_PRICE_SOURCE_LOCK = threading.Lock()
_last_health: Dict[str, DataHealth] = {}
_LAST_HEALTH_LOCK = threading.Lock()


def get_price(code: str, prefer: str = "") -> Tuple[Optional[PriceSnapshot], str]:
    """Get price with cache-first, API-fallback strategy.

    v16.17: Reads persistent price_cache.json first (refreshed daily by cron).
    Falls back to live API only when cache misses or is stale.

    Args:
        code: ETF code
        prefer: Force a specific source name

    Returns:
        (PriceSnapshot or None, source_name_used)
    """
    # ── Cache-first (v16.17) ──
    try:
        from .price_cache import get_cached_price
        cached = get_cached_price(code)
        if cached and cached.get("price", 0) > 0:
            return PriceSnapshot(
                code=code,
                name=str(cached.get("name", "")),
                price=float(cached["price"]),
                change_pct=float(cached.get("change_pct", 0) or 0),
                volume=0,
                amount=0,
                source="cache",
            ), "cache"
    except (ImportError, OSError, KeyError, ValueError, TypeError):
            logger.warning("silent catch in manager.py:66 - needs review")

    # ── API fallback ──
    sources = _PRICE_SOURCES
    if prefer:
        sources = [s for s in sources if s.name == prefer] or sources
    
    # Try preferred source first (from cache or default order)
    with _LAST_PRICE_SOURCE_LOCK:
        preferred_name = _last_price_source.get(code, sources[0].name)
    preferred = [s for s in sources if s.name == preferred_name]
    ordered = preferred + [s for s in sources if s.name != preferred_name]
    
    for source in ordered:
        try:
            t0 = time.time()
            result = source.get_price(code)
            if result is not None and result.price > 0:
                with _LAST_PRICE_SOURCE_LOCK:
                    _last_price_source[code] = source.name
                return result, source.name
        except (OSError, ValueError, KeyError, TypeError) as e:
            logger.debug("price source failed: %s", e)
            continue

    return None, "none"


def get_prices(codes: List[str], prefer: str = "") -> Dict[str, Optional[PriceSnapshot]]:
    """Get prices for multiple ETFs with fallback."""
    result = {}
    for code in codes:
        price, _ = get_price(code, prefer)
        result[code] = price
    return result


# v5.6: Per-sector news cache (TTL=600s) to avoid redundant API calls
_news_cache: Dict[str, Tuple[float, List[NewsItem]]] = {}
_NEWS_CACHE_LOCK = threading.Lock()
_NEWS_CACHE_TTL = 600
_NEWS_CACHE_GET_COUNT = 0  # v17: lazy prune counter


def get_news(keyword: str, limit: int = 10) -> List[NewsItem]:
    """Get news aggregated from all sources, sorted by relevance.

    v5.6: Aggregates ALL sources (not first-come-first-served), then sorts
    by relevance score. Also caches per keyword to avoid N+1 API calls.
    """
    import time as _time
    now = _time.time()

    # Check cache
    cache_key = f"{keyword}:{limit}"
    with _NEWS_CACHE_LOCK:
        if cache_key in _news_cache:
            cached_time, cached_items = _news_cache[cache_key]
            if now - cached_time < _NEWS_CACHE_TTL:
                return cached_items

    # Aggregate from all sources (parallel — concurrent HTTP, ~3x faster)
    all_items = []
    from concurrent.futures import ThreadPoolExecutor, as_completed
    with ThreadPoolExecutor(max_workers=len(_NEWS_SOURCES)) as ex:
        futures = {ex.submit(s.get_news, keyword, limit * 2): s.name for s in _NEWS_SOURCES}
        for f in as_completed(futures):
            src_name = futures[f]
            try:
                items = f.result(timeout=15)
                if items:
                    all_items.extend(items)
            except (OSError, ValueError, KeyError, TypeError, Exception) as e:
                logger.debug("news source %s failed: %s", src_name, e)

    # Sort by relevance (descending), then take top-N
    all_items.sort(key=lambda x: x.relevance, reverse=True)
    result = all_items[:limit]

    # Cache
    with _NEWS_CACHE_LOCK:
        _news_cache[cache_key] = (now, result)
        # Prune old cache entries lazily (every 50 calls, saves O(n) per get_news)
        global _NEWS_CACHE_GET_COUNT
        _NEWS_CACHE_GET_COUNT += 1
        if _NEWS_CACHE_GET_COUNT % 50 == 0:
            expired = [k for k, (t, _) in _news_cache.items() if now - t > _NEWS_CACHE_TTL * 2]
            for k in expired:
                del _news_cache[k]

    return result


def check_all_sources() -> List[DataHealth]:
    """Run health check on all data sources."""
    results = []
    for source in _PRICE_SOURCES:
        try:
            h = source.health()
        except (OSError, ValueError, KeyError, TypeError) as e:
            h = DataHealth(source.name, SourceStatus.FAILED, 0, error=str(e))
        results.append(h)
        with _LAST_HEALTH_LOCK:
            _last_health[source.name] = h
    for source in _NEWS_SOURCES:
        try:
            h = source.health()
        except (OSError, ValueError, KeyError, TypeError) as e:
            h = DataHealth(source.name, SourceStatus.FAILED, 0, error=str(e))
        results.append(h)
        with _LAST_HEALTH_LOCK:
            _last_health[source.name] = h
    return results


def get_preferred_source() -> str:
    """Return the name of the currently healthiest price source."""
    best = _PRICE_SOURCES[0].name
    best_latency = float("inf")
    with _LAST_HEALTH_LOCK:
        health_snapshot = dict(_last_health)
    for source in _PRICE_SOURCES:
        h = health_snapshot.get(source.name)
        if h and h.status == SourceStatus.HEALTHY and h.latency_ms < best_latency:
            best = source.name
            best_latency = h.latency_ms
    return best
