"""News sources for ETF catalysts and events."""
import json
import urllib.request
import urllib.error
import urllib.parse
import time
import logging
from typing import List
logger = logging.getLogger(__name__)
from .base import NewsSource, NewsItem, DataHealth, SourceStatus

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def _fetch_json(url, headers=None, timeout=5):
    h = {**HEADERS, **(headers or {})}
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))

def _fetch_text(url, headers=None, timeout=10):
    h = {**HEADERS, **(headers or {})}
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")

def _filter_items(items, keyword=None, limit=10):
    if not keyword: return items[:limit]
    kw = keyword.lower()
    return [i for i in items if kw in i.title.lower()][:limit]

# ─── 华尔街见闻 (专业金融新闻) ───
class WallStreetCNSource(NewsSource):
    name = "wallstreetcn"
    def get_news(self, keyword: str, limit: int = 10) -> List[NewsItem]:
        try:
            data = _fetch_json("https://api-one.wallstcn.com/apiv1/content/information-flow?channel=global-channel&accept=article&limit=30", {"Referer": "https://wallstreetcn.com/"})
            items = []
            for item in data.get("data", {}).get("items", []):
                res = item.get("resource")
                if res and (res.get("title") or res.get("content_short")):
                    ts = res.get("display_time", 0)
                    t = time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)) if ts else ""
                    items.append(NewsItem(title=str(res.get("title") or res.get("content_short","")), url=str(res.get("uri","")), source="华尔街见闻", time=t, relevance=0.8))
            return _filter_items(items, keyword, limit)
        except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
            logger.warning("Wallstreet news failed: %s", e)
            return []
        except Exception as e:
            logger.warning("Wallstreet news unexpected error: %s", e)
            return []
    def health(self) -> DataHealth:
        t0 = time.time()
        try:
            items = self.get_news("", 1)
            return DataHealth(self.name, SourceStatus.HEALTHY if items else SourceStatus.DEGRADED, (time.time()-t0)*1000)
        except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
            return DataHealth(self.name, SourceStatus.FAILED, (time.time()-t0)*1000, error=str(e))

# ─── 微博热搜 (社会热点) ───
class WeiboSource(NewsSource):
    name = "weibo"
    def get_news(self, keyword: str, limit: int = 10) -> List[NewsItem]:
        try:
            data = _fetch_json("https://weibo.com/ajax/side/hotSearch", {"Referer": "https://weibo.com/"})
            items = []
            for item in data.get("data", {}).get("realtime", []):
                title = str(item.get("note", "") or item.get("word", ""))
                if not title: continue
                items.append(NewsItem(title=title, url=f"https://s.weibo.com/weibo?q={urllib.parse.quote(title)}&Refer=top", source="微博热搜", time="实时", relevance=0.6))
            return _filter_items(items, keyword, limit)
        except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
            logger.error("Weibo hot search failed: %s", e)
            return []
    def health(self) -> DataHealth:
        t0 = time.time()
        try:
            items = self.get_news("", 1)
            return DataHealth(self.name, SourceStatus.HEALTHY if items else SourceStatus.DEGRADED, (time.time()-t0)*1000)
        except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
            return DataHealth(self.name, SourceStatus.FAILED, (time.time()-t0)*1000, error=str(e))

# ─── 36氪 (科技/创投新闻) ───
class Kr36Source(NewsSource):
    name = "36kr"
    def get_news(self, keyword: str, limit: int = 10) -> List[NewsItem]:
        try:
            from bs4 import BeautifulSoup
            html = _fetch_text("https://36kr.com/newsflashes")
            soup = BeautifulSoup(html, "html.parser")
            items = []
            for item in soup.select(".newsflash-item"):
                el = item.select_one(".item-title")
                if not el: continue
                title = el.get_text(strip=True)
                href = el.get("href", "")
                if not href.startswith("http"): href = f"https://36kr.com{href}"
                tm = (item.select_one(".time") or item.select_one("time"))
                t = tm.get_text(strip=True) if tm else ""
                items.append(NewsItem(title=title, url=href, source="36氪", time=t, relevance=0.7))
            return _filter_items(items, keyword, limit)
        except (urllib.error.URLError, OSError, ValueError, KeyError): return []
    def health(self) -> DataHealth:
        t0 = time.time()
        try:
            items = self.get_news("", 1)
            return DataHealth(self.name, SourceStatus.HEALTHY if items else SourceStatus.DEGRADED, (time.time()-t0)*1000)
        except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
            return DataHealth(self.name, SourceStatus.FAILED, (time.time()-t0)*1000, error=str(e))

# ─── 腾讯新闻 (综合新闻) ───
class TencentSource(NewsSource):
    name = "tencent"
    def get_news(self, keyword: str, limit: int = 10) -> List[NewsItem]:
        try:
            data = _fetch_json("https://i.news.qq.com/web_backend/v2/getTagInfo?tagId=aEWqxLtdgmQ%3D", {"Referer": "https://news.qq.com/"})
            items = []
            for news in data.get("data", {}).get("tabs", [{}])[0].get("articleList", []):
                items.append(NewsItem(
                    title=str(news.get("title","")),
                    url=str(news.get("url","") or news.get("link_info",{}).get("url","")),
                    source="腾讯新闻", time=str(news.get("pub_time","") or news.get("publish_time","")), relevance=0.5))
            return _filter_items(items, keyword, limit)
        except (urllib.error.URLError, OSError, ValueError, KeyError): return []
    def health(self) -> DataHealth:
        t0 = time.time()
        try:
            items = self.get_news("", 1)
            return DataHealth(self.name, SourceStatus.HEALTHY if items else SourceStatus.DEGRADED, (time.time()-t0)*1000)
        except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
            return DataHealth(self.name, SourceStatus.FAILED, (time.time()-t0)*1000, error=str(e))

# ─── V2EX (科技社区热点) ───
class V2EXSource(NewsSource):
    name = "v2ex"
    def get_news(self, keyword: str, limit: int = 10) -> List[NewsItem]:
        try:
            data = _fetch_json("https://www.v2ex.com/api/topics/hot.json")
            items = [NewsItem(title=str(t.get("title","")), url=f"https://www.v2ex.com/t/{t.get('id','')}", source="V2EX", time="", relevance=0.4) for t in data if t.get("title")]
            return _filter_items(items, keyword, limit)
        except (urllib.error.URLError, OSError, ValueError, KeyError): return []
    def health(self) -> DataHealth:
        t0 = time.time()
        try:
            items = self.get_news("", 1)
            return DataHealth(self.name, SourceStatus.HEALTHY if items else SourceStatus.DEGRADED, (time.time()-t0)*1000)
        except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
            return DataHealth(self.name, SourceStatus.FAILED, (time.time()-t0)*1000, error=str(e))

# ─── 新浪财经 (备选) ───
class SinaNewsSource(NewsSource):
    name = "sina_news"
    BASE_URL = "https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2509&num={limit}"
    def get_news(self, keyword: str, limit: int = 10) -> List[NewsItem]:
        try:
            data = _fetch_json(self.BASE_URL.format(limit=limit*2))
        except (urllib.error.URLError, OSError, ValueError, KeyError): return []
        kw = keyword.lower()
        items = []
        for item in data.get("result", {}).get("data", []):
            title = str(item.get("title","") or "")
            summary = str(item.get("summary","") or "")
            if kw and kw not in title.lower() and kw not in summary.lower(): continue
            try: t = time.strftime("%Y-%m-%d %H:%M", time.localtime(int(item.get("ctime",0)))) if item.get("ctime") else ""
            except (ValueError, TypeError, OSError): t = chr(34)*2
            items.append(NewsItem(title=title, url=str(item.get("url","") or item.get("wapurl","") or ""), source=str(item.get("media_name","新浪财经")), time=t, summary=summary, relevance=0.7))
            if len(items) >= limit: break
        return items
    def health(self) -> DataHealth:
        t0 = time.time()
        try:
            data = _fetch_json(self.BASE_URL.format(limit=1))
            items = data.get("result", {}).get("data", [])
            return DataHealth(self.name, SourceStatus.HEALTHY if items else SourceStatus.DEGRADED, (time.time()-t0)*1000)
        except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
            return DataHealth(self.name, SourceStatus.FAILED, (time.time()-t0)*1000, error=str(e))

class BackupNewsSource(NewsSource):
    name = "backup_news"
    def get_news(self, keyword, limit=10): return []
    def health(self): return DataHealth(self.name, SourceStatus.DEGRADED, 0)