"""Data sources for ETF platform.

Provides unified interface for price, volume, and news data
with automatic fallback between providers.
"""
from .base import PriceSource, NewsSource, DataHealth
from .sina import SinaSource
from .akshare_source import AKShareSource
from .news import WallStreetCNSource, WeiboSource, Kr36Source, TencentSource, V2EXSource, SinaNewsSource
from .manager import get_price, get_news, check_all_sources, get_preferred_source
