#!/usr/bin/env python3
"""
新闻处理与情绪分析 — 处理web_search结果并更新ETF系统

用法：
  # 方式1: 从JSON文件处理
  python scripts/process_news.py --input search_results.json
  
  # 方式2: 从stdin接收JSON
  cat search_results.json | python scripts/process_news.py --stdin
  
  # 方式3: 直接运行（演示模式）
  python scripts/process_news.py
"""
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

_BASE = Path(__file__).resolve().parent.parent
_DATA = _BASE / "data"
_RAW_FILE = _DATA / "news_raw_sources.json"
_SENT_FILE = _DATA / "news_sentiment.json"

# 情绪关键词映射
POS_KEYWORDS = [
    "突破", "新高", "超预期", "大涨", "涨停", "爆发", "飙升", "扩产", "中标",
    "获批", "涨价", "上调", "增持", "回购", "净流入", "领涨", "创纪录",
    "利好", "增长", "盈利", "改善", "回暖", "景气", "受益", "推荐",
    "加速", "放量", "走强", "强势", "强劲", "乐观", "看好",
    "核准", "启动", "投产", "签约", "订单", "创新高", "业绩预增", "翻倍",
    "上涨", "利好", "增长", "盈利", "改善", "回暖", "景气", "受益", "推荐",
]
NEG_KEYWORDS = [
    "暴跌", "崩盘", "爆雷", "跌停", "大跌", "重挫", "腰斩", "预亏",
    "亏损", "下滑", "减持", "抛售", "净流出", "制裁", "打压", "立案",
    "调查", "处罚", "下调", "评级下调", "跌破", "新低", "利空",
    "承压", "走弱", "疲软", "放缓", "风险", "担忧", "萎缩", "低迷",
    "战", "冲突", "危机", "制裁", "打压", "抛售", "减持", "亏损",
    "下跌", "利空", "下滑", "承压", "走弱", "疲软", "放缓", "风险",
]


def analyze_sentiment(title: str, description: str) -> Tuple[float, List[str]]:
    """分析新闻情绪，返回情绪分数和匹配的关键词"""
    text = f"{title} {description}"
    matched_pos = []
    matched_neg = []
    
    for kw in POS_KEYWORDS:
        if kw in text:
            matched_pos.append(kw)
    for kw in NEG_KEYWORDS:
        if kw in text:
            matched_neg.append(kw)
    
    # 计算情绪分数 [-1, 1]
    pos_score = len(matched_pos) * 0.3
    neg_score = len(matched_neg) * 0.3
    sentiment = max(-1.0, min(1.0, pos_score - neg_score))
    
    return sentiment, matched_pos + matched_neg


def process_news_item(sector: str, item: Dict, query: str = "") -> Dict:
    """处理单条新闻"""
    title = item.get("title", "")
    url = item.get("url", "")
    description = item.get("description", "")
    
    sentiment, keywords = analyze_sentiment(title, description)
    
    return {
        "source": "web_search_dynamic",
        "title": title,
        "url": url,
        "description": description,
        "sector": sector,
        "query": query,
        "sentiment": round(sentiment, 2),
        "keywords_matched": keywords,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "is_bearish": sentiment < -0.2,
        "is_bullish": sentiment > 0.2,
        "timestamp": datetime.now().isoformat(),
    }


def update_sentiment_json(items: List[Dict]) -> Dict:
    """根据新闻列表更新news_sentiment.json"""
    sectors = {}
    for item in items:
        sector = item.get("sector", "unknown")
        sentiment = item.get("sentiment", 0)
        
        if sector not in sectors:
            sectors[sector] = {"positive": 0, "negative": 0, "neutral": 0, "count": 0}
        
        sectors[sector]["count"] += 1
        if sentiment > 0.2:
            sectors[sector]["positive"] += 1
        elif sentiment < -0.2:
            sectors[sector]["negative"] += 1
        else:
            sectors[sector]["neutral"] += 1
    
    # 计算综合情绪
    result = {
        "updated": datetime.now().isoformat(),
        "source": "dynamic_web_search",
        "sectors": {}
    }
    
    for sector, stats in sectors.items():
        total = stats["count"]
        if total == 0:
            direction = "中性"
            strength = "弱"
        else:
            net = stats["positive"] - stats["negative"]
            ratio = abs(net) / total
            
            if net > 0:
                direction = "看多" if ratio > 0.3 else "中性"
            elif net < 0:
                direction = "看空" if ratio > 0.3 else "中性"
            else:
                direction = "中性"
            
            if ratio > 0.5:
                strength = "强"
            elif ratio > 0.2:
                strength = "中"
            else:
                strength = "弱"
        
        result["sectors"][sector] = {
            "direction": direction,
            "strength": strength,
            "note": f"动态新闻{total}条(多{stats['positive']}/空{stats['negative']}/中{stats['neutral']})"
        }
    
    with open(_SENT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description="新闻处理与情绪分析")
    parser.add_argument("--input", type=str, help="输入JSON文件路径")
    parser.add_argument("--stdin", action="store_true", help="从stdin读取JSON")
    args = parser.parse_args()
    
    # 读取输入
    if args.stdin:
        input_data = json.load(sys.stdin)
    elif args.input:
        with open(args.input) as f:
            input_data = json.load(f)
    else:
        # 演示模式：使用预设数据
        print("⚠️ 未指定输入，使用演示模式")
        input_data = {"items": []}
    
    # 处理新闻
    all_items = []
    if "items" in input_data:
        for item in input_data["items"]:
            sector = item.get("sector", "unknown")
            processed = process_news_item(sector, item)
            all_items.append(processed)
    
    # 保存原始数据
    output = {
        "fetched_at": datetime.now().isoformat(),
        "sources": ["web_search_dynamic"],
        "stats": {
            "total_items": len(all_items),
            "total_bullish": sum(1 for r in all_items if r.get("is_bullish")),
            "total_bearish": sum(1 for r in all_items if r.get("is_bearish")),
            "total_neutral": sum(1 for r in all_items if not r.get("is_bullish") and not r.get("is_bearish")),
        },
        "sector_stats": {},
        "items": all_items,
    }
    
    with open(_RAW_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"💾 已保存: {_RAW_FILE}")
    print(f"📈 看多: {output['stats']['total_bullish']} | 看空: {output['stats']['total_bearish']} | 中性: {output['stats']['total_neutral']}")
    
    # 更新情绪JSON
    sentiment = update_sentiment_json(all_items)
    print(f"💾 已更新: {_SENT_FILE}")
    
    print("\n" + "=" * 60)
    print("📈 行业情绪概览:")
    for sector, info in sorted(sentiment.get("sectors", {}).items()):
        print(f"  {sector:12s}: {info['direction']} ({info['strength']}) - {info['note']}")
    
    return 0


if __name__ == "__main__":
    main()
