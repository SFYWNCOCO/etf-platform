#!/usr/bin/env python3
"""
新闻搜索脚本 — 供Agent调用的工具函数

此脚本提供两个核心功能：
1. 搜索指定行业的新闻并分析情绪
2. 更新news_sentiment.json

注意：此脚本需要hermes agent环境运行（通过hermes_tools.web_search）
或者由Agent手动调用web_search后传入结果。
"""
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).parent.parent))

_BASE = Path(__file__).resolve().parent.parent
_DATA = _BASE / "data"
_RAW_FILE = _DATA / "news_raw_sources.json"
_SENT_FILE = _DATA / "news_sentiment.json"

# 情绪关键词
POS_KEYWORDS = ["突破", "新高", "超预期", "大涨", "涨停", "爆发", "飙升", "扩产", "中标", "获批", "涨价", "上调", "增持", "回购", "净流入", "领涨", "创纪录", "利好", "增长", "盈利", "改善", "回暖", "景气", "受益", "推荐", "加速", "放量", "走强", "强势", "强劲", "乐观", "看好", "核准", "启动", "投产", "签约", "订单", "创新高", "业绩预增", "翻倍"]
NEG_KEYWORDS = ["暴跌", "崩盘", "爆雷", "跌停", "大跌", "重挫", "腰斩", "预亏", "亏损", "下滑", "减持", "抛售", "净流出", "制裁", "打压", "立案", "调查", "处罚", "下调", "评级下调", "跌破", "新低", "利空", "承压", "走弱", "疲软", "放缓", "风险", "担忧", "萎缩", "低迷", "战", "冲突", "危机", "制裁", "打压", "抛售", "减持", "亏损"]


def analyze_sentiment(title: str, description: str) -> tuple:
    """分析新闻情绪"""
    text = f"{title} {description}"
    matched_pos = [kw for kw in POS_KEYWORDS if kw in text]
    matched_neg = [kw for kw in NEG_KEYWORDS if kw in text]
    
    pos_score = len(matched_pos) * 0.3
    neg_score = len(matched_neg) * 0.3
    sentiment = max(-1.0, min(1.0, pos_score - neg_score))
    
    return sentiment, matched_pos + matched_neg


def process_news_data(sector: str, title: str, url: str, description: str, query: str) -> Dict:
    """处理单条新闻"""
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


def main():
    import argparse
    parser = argparse.ArgumentParser(description="新闻搜索工具")
    parser.add_argument("--sector", type=str, required=True, help="行业名称")
    parser.add_argument("--query", type=str, help="搜索关键词")
    parser.add_argument("--json", type=str, help="输入JSON文件（包含search结果）")
    args = parser.parse_args()
    
    if args.json:
        # 从JSON文件读取结果
        with open(args.json) as f:
            data = json.load(f)
        
        items = data.get("items", [])
        processed = []
        for item in items:
            processed.append(process_news_data(
                sector=args.sector,
                title=item.get("title", ""),
                url=item.get("url", ""),
                description=item.get("description", ""),
                query=args.query or item.get("query", ""),
            ))
    else:
        print(f"⚠️ 请提供 --json 参数或直接使用hermes agent的web_search工具")
        return
    
    # 保存结果
    output = {
        "fetched_at": datetime.now().isoformat(),
        "sources": ["web_search_dynamic"],
        "stats": {
            "total_items": len(processed),
            "total_bullish": sum(1 for r in processed if r.get("is_bullish")),
            "total_bearish": sum(1 for r in processed if r.get("is_bearish")),
            "total_neutral": sum(1 for r in processed if not r.get("is_bullish") and not r.get("is_bearish")),
        },
        "items": processed,
    }
    
    with open(_RAW_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    # 更新情绪JSON
    sectors = {}
    for item in processed:
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
    
    result = {
        "updated": datetime.now().isoformat(),
        "source": "dynamic_web_search",
        "sectors": {}
    }
    
    for sector, stats in sectors.items():
        total = stats["count"]
        net = stats["positive"] - stats["negative"]
        ratio = abs(net) / total if total > 0 else 0
        
        if net > 0:
            direction = "看多" if ratio > 0.3 else "中性"
        elif net < 0:
            direction = "看空" if ratio > 0.3 else "中性"
        else:
            direction = "中性"
        
        strength = "强" if ratio > 0.5 else ("中" if ratio > 0.2 else "弱")
        
        result["sectors"][sector] = {
            "direction": direction,
            "strength": strength,
            "note": f"动态新闻{total}条(多{stats['positive']}/空{stats['negative']}/中{stats['neutral']})"
        }
    
    with open(_SENT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 已处理 {len(processed)} 条新闻")
    print(f"📈 看多: {output['stats']['total_bullish']} | 看空: {output['stats']['total_bearish']} | 中性: {output['stats']['total_neutral']}")
    print(f"💾 已保存到: {_RAW_FILE}, {_SENT_FILE}")


if __name__ == "__main__":
    main()
