"""L9 Signal enhancer: injects real news into catalyst calendar and adjusts score."""
from etf_platform.data.manager import get_news


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
    except Exception:
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

    # Fetch news
    try:
        news_items = get_news(sector, limit=5)
    except Exception:
        news_items = []

    if not news_items:
        return penetration_result

    l9_data = layers[l9_key]

    # Build catalyst entries from news
    dynamic = []
    for item in news_items:
        title = item.title or ""
        neg_kws = ["跌", "降", "利空", "风险", "跳水", "暴跌", "警告", "崩盘"]
        pos_kws = ["涨", "升", "利好", "突破", "反弹", "新高", "放量"]
        neg = sum(1 for k in neg_kws if k in title)
        pos = sum(1 for k in pos_kws if k in title)
        if pos > neg:
            sentiment, conf = "利好", 55
        elif neg > pos:
            sentiment, conf = "利空预警", 55
        else:
            sentiment, conf = "中性", 40
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

    # Adjust L9 score
    old_score = scores.get("L9_Signals", 5.0)
    net = sum(1 for d in dynamic if d["sentiment"] == "利好") - sum(1 for d in dynamic if d["sentiment"] == "利空预警")
    adj = net * 0.5
    scores["L9_Signals"] = max(1, min(10, round(old_score + adj, 1)))

    return penetration_result