"""News sources for ETF catalysts and events."""
import json
import urllib.request
import urllib.parse
import time
from typing import Optional, List
from .base import NewsSource, NewsItem, DataHealth, SourceStatus


class EastMoneyNewsSource(NewsSource):
    """Primary news source: EastMoney news search API (free, no auth)."""

    name = "eastmoney_news"

    def get_news(self, keyword: str, limit: int = 10) -> List[NewsItem]:
        url = (
            f"https://searchapi.eastmoney.com/bussiness/Web/GetCMSSearchResult"
            f"?type=8196&pageindex=1&pagesize={limit}"
            f"&keyword={urllib.parse.quote(keyword)}"
        )
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://so.eastmoney.com/",
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception:
            return []

        items = []
        for item in data.get("Data", []):
            try:
                items.append(NewsItem(
                    title=item.get("Title", ""),
                    url=item.get("Url", ""),
                    source="东方财富",
                    time=item.get("Date", ""),
                    summary=item.get("Summary", ""),
                    relevance=0.7,
                ))
            except Exception:
                continue
        return items

    def health(self) -> DataHealth:
        t0 = time.time()
        try:
            news = self.get_news("ETF", limit=1)
            latency = (time.time() - t0) * 1000
            if len(news) > 0:
                return DataHealth(self.name, SourceStatus.HEALTHY, latency)
            return DataHealth(self.name, SourceStatus.DEGRADED, latency,
                            error="No results")
        except Exception as e:
            latency = (time.time() - t0) * 1000
            return DataHealth(self.name, SourceStatus.FAILED, latency, error=str(e))


class BackupNewsSource(NewsSource):
    """Backup news source: uses Baidu search (no API key needed).
    NOTE: This is a simple HTTP fallback, not a browser-based scraper.
    """

    name = "backup_news"

    def get_news(self, keyword: str, limit: int = 10) -> List[NewsItem]:
        # Simple RSS-style fallback using Baidu
        url = f"https://www.baidu.com/s?wd={urllib.parse.quote(keyword)}&tn=news"
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                html = resp.read().decode("utf-8", errors="replace")
        except Exception:
            return []

        # Simple HTML parsing - extract news-like links
        items = []
        import re
        # Look for <a> tags with news-like content
        for match in re.finditer(r'<a[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a>', html, re.IGNORECASE):
            url, title = match.group(1), match.group(2)
            title = re.sub(r'<[^>]+>', "", title).strip()
            if len(title) > 10 and keyword[:2] in title:
                items.append(NewsItem(
                    title=title,
                    url=url,
                    source="百度搜索(备选)",
                    relevance=0.4,
                ))
                if len(items) >= limit:
                    break
        return items

    def health(self) -> DataHealth:
        t0 = time.time()
        try:
            news = self.get_news("ETF", limit=1)
            latency = (time.time() - t0) * 1000
            status = SourceStatus.HEALTHY if len(news) > 0 else SourceStatus.DEGRADED
            return DataHealth(self.name, status, latency)
        except Exception as e:
            latency = (time.time() - t0) * 1000
            return DataHealth(self.name, SourceStatus.FAILED, latency, error=str(e))
