"""News sources for ETF catalysts and events.
Primary: Sina Finance news API (free, no auth, stable).
Backup: Simple HTTP fetch of financial news sites.
"""
import json
import urllib.request
import urllib.parse
import time
import re
from typing import Optional, List
from .base import NewsSource, NewsItem, DataHealth, SourceStatus


class SinaNewsSource(NewsSource):
    """Primary news source: Sina Finance roll news API (free, stable)."""

    name = "sina_news"

    # Sina category IDs for finance news
    # lid=2509 = 全部财经, lid=2510 = 国内财经, lid=2511 = 国际财经
    BASE_URL = "https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2509&num={limit}"

    def get_news(self, keyword: str, limit: int = 10) -> List[NewsItem]:
        url = self.BASE_URL.format(limit=limit * 2)  # Fetch more, filter by keyword
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception:
            return []

        items = []
        news_list = data.get("result", {}).get("data", [])
        kw_lower = keyword.lower()

        for item in news_list:
            title = str(item.get("title", "") or "")
            summary = str(item.get("summary", "") or "")
            keywords = str(item.get("keywords", "") or "")
            combined = (title + summary + keywords).lower()

            # Filter by keyword in title or summary (client-side since API is unfiltered)
            if kw_lower not in title.lower() and kw_lower not in summary.lower():
                continue

            try:
                ctime = int(item.get("ctime", 0))
                time_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(ctime)) if ctime else ""
            except Exception:
                time_str = ""

            items.append(NewsItem(
                title=title,
                url=str(item.get("url", "") or item.get("wapurl", "") or ""),
                source=str(item.get("media_name", "新浪财经")),
                time=time_str,
                summary=summary,
                relevance=0.8,
            ))
            if len(items) >= limit:
                break

        return items

    def health(self) -> DataHealth:
        t0 = time.time()
        try:
            # Test the API endpoint directly (return raw items, ignore keyword filtering)
            import urllib.request, json
            url = self.BASE_URL.format(limit=1)
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            items = data.get("result", {}).get("data", [])
            latency = (time.time() - t0) * 1000
            if items and len(items) > 0:
                return DataHealth(self.name, SourceStatus.HEALTHY, latency)
            return DataHealth(self.name, SourceStatus.DEGRADED, latency, error="API returned no data")
        except Exception as e:
            latency = (time.time() - t0) * 1000
            return DataHealth(self.name, SourceStatus.FAILED, latency, error=str(e))


class BackupNewsSource(NewsSource):
    """Backup: direct fetch of financial news pages."""

    name = "backup_news"

    def get_news(self, keyword: str, limit: int = 10) -> List[NewsItem]:
        # Try multiple sources as fallback
        sources = [
            ("finance", f"https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2510&num={limit}"),
            ("finance_intl", f"https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2511&num={limit}"),
        ]

        for src_name, url in sources:
            try:
                req = urllib.request.Request(url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                })
                with urllib.request.urlopen(req, timeout=8) as resp:
                    data = json.loads(resp.read().decode("utf-8"))

                items = []
                kw_lower = keyword.lower()
                for item in data.get("result", {}).get("data", []):
                    title = str(item.get("title", "") or "")
                    if kw_lower not in title.lower():
                        continue
                    items.append(NewsItem(
                        title=title,
                        url=str(item.get("url", "") or ""),
                        source=src_name,
                        time=str(item.get("ctime", "")),
                        summary=str(item.get("summary", "") or ""),
                        relevance=0.5,
                    ))
                    if len(items) >= limit:
                        break
                if items:
                    return items
            except Exception:
                continue
        return []

    def health(self) -> DataHealth:
        t0 = time.time()
        try:
            items = self.get_news("ETF", limit=1)
            latency = (time.time() - t0) * 1000
            status = SourceStatus.HEALTHY if len(items) > 0 else SourceStatus.DEGRADED
            return DataHealth(self.name, status, latency)
        except Exception as e:
            latency = (time.time() - t0) * 1000
            return DataHealth(self.name, SourceStatus.FAILED, latency, error=str(e))
