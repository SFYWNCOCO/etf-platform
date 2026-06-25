"""Abstract base classes for data sources."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from enum import Enum


class SourceStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"       # 可用但慢/数据不全
    FAILED = "failed"            # 完全不可用


@dataclass
class DataHealth:
    """Health check result for a data source."""
    source_name: str
    status: SourceStatus
    latency_ms: float
    error: Optional[str] = None
    details: Optional[Dict] = None


@dataclass
class PriceSnapshot:
    """Real-time price data for a single ETF."""
    code: str
    name: str = ""
    price: float = 0.0
    change_pct: float = 0.0      # 涨跌幅%
    volume: float = 0.0           # 成交量
    amount: float = 0.0           # 成交额
    turnover_rate: float = 0.0    # 换手率%
    high: float = 0.0
    low: float = 0.0
    open_: float = 0.0
    pre_close: float = 0.0
    source: str = "unknown"


@dataclass
class NewsItem:
    """A single news/catalyst item."""
    title: str
    url: str = ""
    source: str = ""
    time: str = ""
    summary: str = ""
    relevance: float = 0.5        # 0-1 相关性


class PriceSource(ABC):
    """Abstract price/volume data source."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def get_price(self, code: str) -> Optional[PriceSnapshot]:
        """Get real-time price for a single ETF code.
        Returns None if the code is not found or the request fails.
        """
        ...

    def get_prices(self, codes: List[str]) -> Dict[str, Optional[PriceSnapshot]]:
        """Get prices for multiple ETFs. Default: loop over get_price."""
        result = {}
        for code in codes:
            try:
                result[code] = self.get_price(code)
            except Exception as e:
                result[code] = None
        return result

    @abstractmethod
    def health(self) -> DataHealth:
        """Check if this source is currently functional."""
        ...


class NewsSource(ABC):
    """Abstract news/catalyst data source."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def get_news(self, keyword: str, limit: int = 10) -> List[NewsItem]:
        """Search news by keyword. Returns list of NewsItem."""
        ...

    @abstractmethod
    def health(self) -> DataHealth:
        """Check if this source is functional."""
        ...
