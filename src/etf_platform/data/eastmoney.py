"""Price source: wraps existing working ETFDataFetcher from etf_system."""
import importlib
import sys
import time
from pathlib import Path
from typing import Optional, List, Dict
from .base import PriceSource, PriceSnapshot, DataHealth, SourceStatus

_ETFDIR = None


def _resolve_etf_system():
    global _ETFDIR
    if _ETFDIR is not None:
        return _ETFDIR

    candidates = [
        Path(__file__).resolve().parent.parent.parent.parent / "etf_system",
        Path(__file__).resolve().parent.parent.parent.parent / "etf_system",
    ]
    for c in candidates:
        if c.exists():
            _ETFDIR = c
            if str(_ETFDIR) not in sys.path:
                sys.path.insert(0, str(_ETFDIR))
            return _ETFDIR
    return None


class EastMoneySource(PriceSource):
    """Price source wrapping the existing ETFDataFetcher (Sina API, proven stable)."""

    name = "eastmoney"

    def __init__(self):
        self._fetcher = None
        self._fetcher_error = None

    def _get_fetcher(self):
        if self._fetcher is not None:
            return self._fetcher
        if self._fetcher_error is not None:
            return None

        etf_dir = _resolve_etf_system()
        if etf_dir is None:
            self._fetcher_error = "etf_system not found"
            return None

        try:
            module = importlib.import_module("data_fetcher")
            if not hasattr(module, "ETFDataFetcher"):
                self._fetcher_error = "ETFDataFetcher not in data_fetcher"
                return None
            self._fetcher = module.ETFDataFetcher()
        except (ImportError, AttributeError, OSError, ValueError, TypeError) as e:
            self._fetcher_error = str(e)[:100]
            return None

        return self._fetcher

    def get_price(self, code: str) -> Optional[PriceSnapshot]:
        try:
            fetcher = self._get_fetcher()
            if fetcher is None:
                return None
            data = fetcher.fetch_realtime([code])
            item = data.get(code)
            if not item or not item.get("price"):
                return None
            return PriceSnapshot(
                code=code,
                name=str(item.get("name", "")),
                price=float(item.get("price", 0) or 0),
                change_pct=float(item.get("change_pct", 0) or 0),
                volume=float(item.get("volume", 0) or 0),
                amount=float(item.get("amount", 0) or 0),
                source=self.name,
            )
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def get_prices(self, codes: List[str]) -> Dict[str, Optional[PriceSnapshot]]:
        try:
            fetcher = self._get_fetcher()
            if fetcher is None:
                return {}
            data = fetcher.fetch_realtime(codes)
            result = {}
            for code in codes:
                item = data.get(code)
                if item and item.get("price"):
                    result[code] = PriceSnapshot(
                        code=code,
                        name=str(item.get("name", "")),
                        price=float(item.get("price", 0) or 0),
                        change_pct=float(item.get("change_pct", 0) or 0),
                        volume=float(item.get("volume", 0) or 0),
                        amount=float(item.get("amount", 0) or 0),
                        source=self.name,
                    )
                else:
                    result[code] = None
            return result
        except (OSError, ValueError, KeyError, TypeError):
            return {}

    def health(self) -> DataHealth:
        t0 = time.time()
        try:
            result = self.get_price("159995")
            latency = (time.time() - t0) * 1000
            if result and result.price > 0:
                return DataHealth(self.name, SourceStatus.HEALTHY, latency)
            return DataHealth(self.name, SourceStatus.DEGRADED, latency, error="No valid price")
        except (OSError, ValueError, KeyError, TypeError) as e:
            latency = (time.time() - t0) * 1000
            return DataHealth(self.name, SourceStatus.FAILED, latency, error=str(e))
