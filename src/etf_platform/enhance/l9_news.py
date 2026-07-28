"""L9 Signal enhancer: injects real news into catalyst calendar and adjusts score.

v5.6: Uses sector-level cache so multiple ETFs in same sector share news results.
Also uses improved sentiment analysis with context-aware rules.
"""
import threading
from ..data.manager import get_news

# v5.6: Per-sector cache
_sector_news_cache = {}
_SECTOR_NEWS_CACHE_LOCK = threading.Lock()


def _sentiment_score(title: str) -> tuple:
    """Context-aware sentiment scoring. Returns (sentiment_label, confidence).

    v5.6 upgrade from keyword matching:
    - Handles negations: "跌幅收窄" = mild positive, not negative
    - Handles compound patterns: "降息" = positive (not just "降")
    - Weighted: stronger keywords get higher confidence
    """
    pos_strong = ["突破", "新高", "放量", "超预期", "暴涨", "涨停", "主线"]
    pos_mild = ["涨", "升", "利好", "反弹", "回升", "回暖", "改善", "收窄"]
    neg_strong = ["崩盘", "暴跌", "爆雷", "违约", "退市", "踩踏"]
    neg_mild = ["跌", "跳水", "预警", "警告", "下滑", "萎缩", "低迷"]
    # Compound patterns that override simple matching
    negations = {"跌幅收窄": 0.3, "跌势放缓": 0.3, "利空出尽": 0.4,
                 "降息": 0.6, "降准": 0.6, "降价促销": -0.2}

    score = 0.0
    # Check compound patterns first
    for pattern, val in negations.items():
        if pattern in title:
            score += val

    # Strong signals
    for kw in pos_strong:
        if kw in title:
            score += 1.0
    for kw in neg_strong:
        if kw in title:
            score -= 1.0

    # Mild signals (only if no strong signals found)
    if abs(score) < 0.5:
        for kw in pos_mild:
            if kw in title:
                score += 0.5
        for kw in neg_mild:
            if kw in title:
                score -= 0.5

    if score > 0.7:
        return ("利好", min(80, 50 + int(score * 15)))
    elif score > 0.2:
        return ("利好", 55)
    elif score < -0.7:
        return ("利空预警", min(80, 50 + int(abs(score) * 15)))
    elif score < -0.2:
        return ("利空预警", 55)
    else:
        return ("中性", 40)


def enhance_l9(penetration_result: dict) -> dict:
    """Fetch news for the ETF sector, append to catalyst calendar, adjust L9 score."""
    layers = penetration_result.get("layers", {})
    scores = penetration_result.get("layer_scores", {})
    code = penetration_result.get("etf_code", "")

    if not code:
        return penetration_result

    # Get sector from config
    try:
        from etf_platform.config_loader import load_etfs
        etfs = load_etfs()
        info = etfs.get(code, {})
        sector = info.get("sector", "")
    except (KeyError, ValueError, TypeError, AttributeError, ImportError):
        sector = ""

    if not sector or sector in ("其他", "综合", "未知行业"):
        return penetration_result

    # Find L9 key
    l9_key = None
    for k in layers:
        if "L9" in k:
            l9_key = k
            break
    if not l9_key:
        return penetration_result

    # Fetch news (v5.6: sector-level cache)
    with _SECTOR_NEWS_CACHE_LOCK:
        cached = _sector_news_cache.get(sector)
    if cached is not None:
        news_items = cached
    else:
        try:
            news_items = get_news(sector, limit=5)
            with _SECTOR_NEWS_CACHE_LOCK:
                _sector_news_cache[sector] = news_items
        except (KeyError, ValueError, TypeError, AttributeError, ImportError):
            news_items = []

    if not news_items:
        return penetration_result

    l9_data = layers[l9_key]

    # Build catalyst entries from news
    dynamic = []
    for item in news_items:
        title = item.title or ""
        sentiment, conf = _sentiment_score(title)
        dynamic.append({
            "type": "实时新闻", "source": item.source, "title": title,
            "time": item.time, "sentiment": sentiment, "confidence": conf
        })

    # Prepend to existing catalyst list
    existing = l9_data.get("catalyst_calendar", l9_data.get("dynamic_catalysts", []))
    if isinstance(existing, list):
        l9_data["dynamic_catalysts"] = dynamic + existing[:5]
    else:
        l9_data["dynamic_catalysts"] = dynamic

    l9_data["data_source"] = f"静态日历+{len(news_items)}条实时新闻"

    # Adjust L9 score (v8.33: ceiling-aware to prevent L9=10.0)
    old_score = scores.get("L9_Signals", 5.0)
    net = sum(1 for d in dynamic if d["sentiment"] == "利好") - sum(1 for d in dynamic if d["sentiment"] == "利空预警")
    adj = net * 0.5
    # Ceiling guard: reserve 0.5 headroom to prevent L9 from hitting 10.0
    # L9 already gets +0.5 from l17_factor_layer bullish momentum, so news
    # adjustment should not push it to the hard ceiling.
    headroom = 10.0 - old_score
    if headroom < 1.0:
        # Cap positive adjustment to leave at least 0.1 headroom
        adj = min(adj, headroom - 0.1) if adj > 0 else adj
    scores["L9_Signals"] = max(1, min(10, round(old_score + adj, 1)))

    return penetration_result