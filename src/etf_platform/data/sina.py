"""Sina Finance data source - stable fallback for price data."""
import urllib.request
import time
from typing import Optional, List, Dict
from .base import PriceSource, PriceSnapshot, DataHealth, SourceStatus

SINA_URL = "https://hq.sinajs.cn/list="

# ETF prefix mapping for sina
def _to_sina_code(code: str) -> str:
    if code.startswith(("5", "6")):
        return f"sh{code}"
    return f"sz{code}"


class SinaSource(PriceSource):
    """Fallback price source: Sina Finance (20+ year track record)."""

    name = "sina"

    def get_price(self, code: str) -> Optional[PriceSnapshot]:
        sina_code = _to_sina_code(code)
        url = f"{SINA_URL}{sina_code}"
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://finance.sina.com.cn/",
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                text = resp.read().decode("gbk")
        except Exception:
            return None

        # Parse sina CSV format: "var hq_str_sh159995="name,open,pre_close,price,high,low,...""
        if "=" not in text:
            return None
        data_part = text.split('"')[1] if '"' in text else ""
        if not data_part:
            return None
        fields = data_part.split(",")
        if len(fields) < 30:
            return None

        try:
            price = float(fields[3]) if fields[3] else 0
            pre_close = float(fields[2]) if fields[2] else 0
            change_pct = ((price - pre_close) / pre_close * 100) if pre_close else 0
            return PriceSnapshot(
                code=code,
                name=fields[0],
                price=price,
                change_pct=round(change_pct, 2),
                volume=float(fields[8]) if fields[8] else 0,
                amount=float(fields[9]) if fields[9] else 0,
                high=float(fields[4]) if fields[4] else 0,
                low=float(fields[5]) if fields[5] else 0,
                open_=float(fields[1]) if fields[1] else 0,
                pre_close=pre_close,
                source=self.name,
            )
        except (ValueError, IndexError):
            return None

    def health(self) -> DataHealth:
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
