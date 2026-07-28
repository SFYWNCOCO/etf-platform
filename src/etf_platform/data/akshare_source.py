"""AKShare data source - 3rd fallback (auto-maintained Python package)."""
import time
import logging
from typing import Optional, List, Dict
from .base import PriceSource, PriceSnapshot, DataHealth, SourceStatus

logger = logging.getLogger(__name__)

try:
    import akshare
    _HAS_AKSHARE = True
except ImportError:
    _HAS_AKSHARE = False


class AKShareSource(PriceSource):
    """3rd fallback: AKShare Python package (community-maintained)."""

    name = "akshare"

    def get_price(self, code: str) -> Optional[PriceSnapshot]:
        if not _HAS_AKSHARE:
            return None
        try:
            # Use akshare's ETF realtime function - fund_etf_spot_em provides real-time trading data
            df = akshare.fund_etf_spot_em()
            if df is None or df.empty:
                return None
            row = df[df["代码"] == code]
            if row.empty:
                return None
            row = row.iloc[0]
            return PriceSnapshot(
                code=code,
                name=str(row.get("名称", "")),
                price=float(row.get("最新价", 0) or 0),
                change_pct=float(row.get("涨跌幅", 0) or 0),
                volume=float(row.get("成交量", 0) or 0),
                amount=float(row.get("成交额", 0) or 0),
                turnover_rate=float(row.get("换手率", 0) or 0),
                source=self.name,
            )
        except Exception as e:
            logger.warning("akshare_source: fetch failed: %s", e)
            return None

    def get_prices(self, codes: List[str]) -> Dict[str, Optional[PriceSnapshot]]:
        """Override: batch fetch all at once (akshare supports this)."""
        if not _HAS_AKSHARE:
            return {}
        result = {}
        try:
            df = akshare.fund_etf_spot_em()
            if df is None or df.empty:
                return result
            for code in codes:
                row = df[df["代码"] == code]
                if row.empty:
                    result[code] = None
                    continue
                row = row.iloc[0]
                result[code] = PriceSnapshot(
                    code=code,
                    name=str(row.get("名称", "")),
                    price=float(row.get("最新价", 0) or 0),
                    change_pct=float(row.get("涨跌幅", 0) or 0),
                    volume=float(row.get("成交量", 0) or 0),
                    amount=float(row.get("成交额", 0) or 0),
                    turnover_rate=float(row.get("换手率", 0) or 0),
                    source=self.name,
                )
        except Exception as e:
            logger.debug("get_prices batch fetch failed: %s", e)
            pass
        return result

    def health(self) -> DataHealth:
        if not _HAS_AKSHARE:
            return DataHealth(self.name, SourceStatus.FAILED, 0,
                            error="akshare not installed")
        t0 = time.time()
        try:
            result = self.get_price("159995")
            latency = (time.time() - t0) * 1000
            if result and result.price > 0:
                return DataHealth(self.name, SourceStatus.HEALTHY, latency)
            return DataHealth(self.name, SourceStatus.DEGRADED, latency,
                            error="No valid price")
        except Exception as e:
            latency = (time.time() - t0) * 1000
            return DataHealth(self.name, SourceStatus.FAILED, latency, error=str(e))
