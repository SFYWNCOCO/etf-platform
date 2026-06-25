"""L9 Signal enhancer: injects real news into catalyst calendar."""
import time


def enhance_l9(penetration_result: dict) -> dict:
    """Enhance L9 layer with real news from data sources.
    
    Fetches recent news relevant to the ETF's sector and appends
    them to the L9 catalyst calendar as dynamic items.
    """
    layers = penetration_result.get("layers", {})
    scores = penetration_result.get("layer_scores", {})
    etf_code = penetration_result.get("etf_code", "")
    
    if not etf_code:
        return penetration_result
    
    # Get sector info
    try:
        from ..config_loader import load_etfs
        etfs = load_etfs()
        info = etfs.get(etf_code, {})
        sector = info.get("sector", "")
    except Exception:
        sector = ""
    
    if not sector:
        return penetration_result
    
    # Find L9 key
    l9_key = None
    for k in layers:
        if "L9" in k:
            l9_key = k
            break
    
    if not l9_key:
        return penetration_result
    
    l9_data = layers[l9_key]
    
    # Fetch news for this sector
    try:
        from ..data.manager import get_news
        news_items = get_news(sector, limit=5)
    except Exception:
        news_items = []
    
    if not news_items:
        return penetration_result
    
    # Build dynamic catalyst entries
    dynamic_catalysts = []
    for item in news_items:
        # Rough sentiment from title
        title_lower = item.title.lower()
        if any(kw in title_lower for kw in ["涨", "升", "利好", "突破", "增持", "放量"]):
            sentiment = "利好"
            conf = 55
        elif any(kw in title_lower for kw in ["跌", "降", "利空", "减持", "风险", "警告"]):
            sentiment = "利空预警"
            conf = 55
        else:
            sentiment = "中性"
            conf = 40
        
        dynamic_catalysts.append({
            "type": "动态新闻",
            "source": item.source,
            "title": item.title,
            "url": item.url,
            "time": item.time,
            "sentiment": sentiment,
            "confidence": conf,
        })
    
    # Append to existing catalyst list
    existing = l9_data.get("catalyst_calendar", l9_data.get("dynamic_catalysts", []))
    if isinstance(existing, list):
        l9_data["dynamic_catalysts"] = dynamic_catalysts + existing[:8]
    else:
        l9_data["dynamic_catalysts"] = dynamic_catalysts
    
    # Tag L9 as enhanced
    l9_data["data_source"] = f"静态日历+{len(news_items)}条实时新闻"
    
    # Adjust L9 score slightly based on real news
    if dynamic_catalysts:
        positive = sum(1 for c in dynamic_catalysts if c["sentiment"] == "利好")
        negative = sum(1 for c in dynamic_catalysts if c["sentiment"] == "利空预警")
        adj = (positive - negative) * 0.3
        old_score = scores.get("L9_Signals", 5.0)
        scores["L9_Signals"] = max(1, min(10, round(old_score + adj, 1)))
    
    return penetration_result
