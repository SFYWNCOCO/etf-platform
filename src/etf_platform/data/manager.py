"""Data source manager: handles priority, fallback, and health checking."""
import time
from typing import Optional, List, Dict, Tuple
from .base import PriceSource, NewsSource, PriceSnapshot, NewsItem, DataHealth, SourceStatus
from .eastmoney import EastMoneySource
from .sina import SinaSource
from .akshare_source import AKShareSource
from .news import SinaNewsSource, BackupNewsSource

# Priority order for price sources
_PRICE_SOURCES: List[PriceSource] = [
    EastMoneySource(),   # Primary: fast, free
    SinaSource(),        # Fallback 1: very stable
    AKShareSource(),     # Fallback 2: auto-maintained
]

# News sources
_NEWS_SOURCES: List[NewsSource] = [
    SinaNewsSource(),       # Primary: Sina Finance
    BackupNewsSource(),     # Fallback
]

# Cache for last successful source per code
_last_price_source: Dict[str, str] = {}
_last_health: Dict[str, DataHealth] = {}


def get_price(code: str, prefer: str = "") -> Tuple[Optional[PriceSnapshot], str]:
    """Get price with automatic fallback.
    
    Args:
        code: ETF code
        prefer: Force a specific source name
        
    Returns:
        (PriceSnapshot or None, source_name_used)
    """
    sources = _PRICE_SOURCES
    if prefer:
        sources = [s for s in sources if s.name == prefer] or sources
    
    # Try preferred source first (from cache or default order)
    preferred_name = _last_price_source.get(code, sources[0].name)
    preferred = [s for s in sources if s.name == preferred_name]
    ordered = preferred + [s for s in sources if s.name != preferred_name]
    
    for source in ordered:
        try:
            t0 = time.time()
            result = source.get_price(code)
            if result is not None and result.price > 0:
                _last_price_source[code] = source.name
                return result, source.name
        except Exception:
            continue
    
    return None, "none"


def get_prices(codes: List[str], prefer: str = "") -> Dict[str, Optional[PriceSnapshot]]:
    """Get prices for multiple ETFs with fallback."""
    result = {}
    for code in codes:
        price, _ = get_price(code, prefer)
        result[code] = price
    return result


def get_news(keyword: str, limit: int = 10) -> List[NewsItem]:
    """Get news with fallback."""
    for source in _NEWS_SOURCES:
        try:
            items = source.get_news(keyword, limit)
            if items:
                return items
        except Exception:
            continue
    return []


def check_all_sources() -> List[DataHealth]:
    """Run health check on all data sources."""
    results = []
    for source in _PRICE_SOURCES:
        try:
            h = source.health()
        except Exception as e:
            h = DataHealth(source.name, SourceStatus.FAILED, 0, error=str(e))
        results.append(h)
        _last_health[source.name] = h
    for source in _NEWS_SOURCES:
        try:
            h = source.health()
        except Exception as e:
            h = DataHealth(source.name, SourceStatus.FAILED, 0, error=str(e))
        results.append(h)
        _last_health[source.name] = h
    return results


def get_preferred_source() -> str:
    """Return the name of the currently healthiest price source."""
    best = _PRICE_SOURCES[0].name
    best_latency = float("inf")
    for source in _PRICE_SOURCES:
        h = _last_health.get(source.name)
        if h and h.status == SourceStatus.HEALTHY and h.latency_ms < best_latency:
            best = source.name
            best_latency = h.latency_ms
    return best
