"""Price source: wraps existing working ETFDataFetcher from etf_system."""
import sys
import os
import time
from pathlib import Path
from typing import Optional, List, Dict
from .base import PriceSource, PriceSnapshot, DataHealth, SourceStatus

# Resolve etf_system path dynamically from this file's location
_ETFDIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "etf_system"
if str(_ETFDIR) not in sys.path:
    sys.path.insert(0, str(_ETFDIR))


class EastMoneySource(PriceSource):
    """Price source wrapping the existing ETFDataFetcher (Sina API, proven stable)."""

    name = "eastmoney"

    def __init__(self):
        self._fetcher = None

    def _get_fetcher(self):
        if self._fetcher is None:
            _old_cwd = os.getcwd()
            os.chdir(str(_ETFDIR))
            try:
                from data_fetcher import ETFDataFetcher
                self._fetcher = ETFDataFetcher()
            finally:
                os.chdir(_old_cwd)
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
        except Exception:
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
        except Exception:
            return {}

    def health(self) -> DataHealth:
        t0 = time.time()
        try:
            result = self.get_price("159995")
            latency = (time.time() - t0) * 1000
            if result and result.price > 0:
                return DataHealth(self.name, SourceStatus.HEALTHY, latency)
            return DataHealth(self.name, SourceStatus.DEGRADED, latency, error="No valid price")
        except Exception as e:
            latency = (time.time() - t0) * 1000
            return DataHealth(self.name, SourceStatus.FAILED, latency, error=str(e))
