#!/usr/bin/env python3
"""
动态新闻搜索驱动 — 基于网页搜索实时更新行业新闻情绪

用法:
  python scripts/dynamic_news_search.py                # 搜索所有CATALYSTS行业
  python scripts/dynamic_news_search.py --sectors "核电,电力,原油" --count 3
  python scripts/dynamic_news_search.py --quick        # 只搜Top5行业,每个2条
"""
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

_BASE = Path(__file__).resolve().parent.parent
_DATA = _BASE / "data"
_RAW_FILE = _DATA / "news_raw_sources.json"
_SENT_FILE = _DATA / "news_sentiment.json"


# 搜索关键词模板 — 每个行业2-3个精准查询
SEARCH_TEMPLATES = {
    "核电": ["核电项目审批 国务院 2026", "核电建设 投资 核准", "核能 电力 ETF"],
    "电力": ["电力改革 电价 2026", "特高压 建设 项目", "新型电力系统 十五五"],
    "半导体": ["半导体 芯片 国产替代 2026", "存储芯片 涨价 市场", "半导体设备 ETF"],
    "AI/芯片": ["AI 人工智能 大模型 2026", "算力 芯片 英伟达", "SpaceX AMD 财报"],
    "创新药": ["创新药 审批 医保 2026", "医药 出海 政策", "创新药 ETF"],
    "军工": ["军工 订单 国防预算 2026", "航空 航天 装备", "军工 ETF"],
    "黄金": ["黄金 价格 央行 购金 2026", "贵金属 ETF 金价", "避险资产 黄金"],
    "原油": ["原油 价格 OPEC 2026", "伊朗 谈判 霍尔木兹", "油价 暴跌 上涨"],
    "有色": ["有色金属 铜 铝 价格 2026", "稀土 战略资源", "有色 ETF"],
    "新能源": ["光伏 产能 价格 2026", "新能源车 销量 渗透率", "新能源 ETF"],
    "消费": ["消费 复苏 政策 2026", "白酒 业绩 电商", "消费 ETF"],
    "煤炭": ["煤炭 价格 供应 2026", "电力 供应 能源安全"],
    "石油石化": ["石油 石化 业绩 2026", "炼化 利润 油价"],
    "航天": ["商业航天 卫星 互联网 2026", "北斗 应用 导航"],
    "存储": ["存储芯片 DRAM NAND 2026", "内存 涨价 兆易创新"],
    "通信": ["5G 光模块 订单 2026", "通信 ETF 5G基站"],
    "机器人/智造": ["人形机器人 量产 2026", "工业自动化 机器人 ETF"],
    "贵金属": ["黄金 价格 央行 购金 2026", "贵金属 ETF 金价"],
}


# 情绪关键词
POS_KEYWORDS = [
    "突破", "新高", "超预期", "大涨", "涨停", "爆发", "飙升", "扩产", "中标",
    "获批", "涨价", "上调", "增持", "回购", "净流入", "领涨", "创纪录",
    "利好", "增长", "盈利", "改善", "回暖", "景气", "受益", "推荐",
    "加速", "放量", "走强", "强势", "强劲", "乐观", "看好",
    "核准", "启动", "投产", "签约", "订单", "创新高", "业绩预增", "翻倍",
    "重开", "谈判", "合作", "签约", "获批",
]
NEG_KEYWORDS = [
    "暴跌", "崩盘", "爆雷", "跌停", "大跌", "重挫", "腰斩", "预亏",
    "亏损", "下滑", "减持", "抛售", "净流出", "制裁", "打压", "立案",
    "调查", "处罚", "下调", "评级下调", "跌破", "新低", "利空",
    "承压", "走弱", "疲软", "放缓", "风险", "担忧", "萎缩", "低迷",
    "战", "冲突", "危机", "制裁", "打压", "抛售", "减持", "亏损",
    "衰退", "萧条", "恶化", "恶化", "恶化",
]

SECTOR_PRIORITY = {
    "核电": 10, "电力": 9, "半导体": 8, "AI/芯片": 8,
    "原油": 7, "黄金": 7, "军工": 6, "有色": 6,
    "创新药": 5, "新能源": 5, "消费": 5, "通信": 4,
    "机器人/智造": 4, "存储": 4, "煤炭": 3, "石油石化": 3,
    "航天": 3, "光伏": 2, "贵金属": 2,
}


def analyze_sentiment(title: str, description: str) -> Tuple[float, List[str]]:
    """分析新闻情绪，返回情绪分数和匹配的关键词"""
    text = f"{title} {description}"
    matched_pos = [kw for kw in POS_KEYWORDS if kw in text]
    matched_neg = [kw for kw in NEG_KEYWORDS if kw in text]
    
    pos_score = len(matched_pos) * 0.25
    neg_score = len(matched_neg) * 0.25
    sentiment = max(-1.0, min(1.0, pos_score - neg_score))
    
    return sentiment, matched_pos + matched_neg


def search_news_for_sector(sector: str, max_results: int = 5) -> List[Dict]:
    """搜索单个行业的新闻"""
    from hermes_tools import web_search
    
    queries = SEARCH_TEMPLATES.get(sector, [f"{sector} 最新新闻"])
    results = []
    
    for query in queries[:2]:
        try:
            search_result = web_search(query=query, limit=5)
            if search_result.get("success") and search_result.get("data", {}).get("web"):
                for item in search_result["data"]["web"][:max_results]:
                    title = item.get("title", "")
                    desc = item.get("description", "")
                    # 过滤掉不相关的结果
                    if sector not in title and sector not in desc:
                        # 检查标题中是否有行业相关词
                        if any(kw in title for kw in [sector[:2], sector[:3]]):
                            pass  # 保留
                        elif not any(kw in title for kw in ["新闻", "直播", "价格", "行情", "资讯", "报告"]):
                            continue
                    results.append({
                        "title": title,
                        "url": item.get("url", ""),
                        "description": desc,
                        "sector": sector,
                        "query": query,
                    })
        except Exception as e:
            print(f"      ⚠️ 搜索失败: {e}")
        time.sleep(0.3)
        if len(results) >= max_results:
            break
    
    return results[:max_results]


def process_all(sectors: List[str], max_per_sector: int = 5) -> Dict:
    """处理所有指定行业的新闻搜索"""
    print(f"\n🎯 动态新闻搜索启动")
    print(f"📊 目标行业: {len(sectors)} 个")
    print(f"⏱️  开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    all_items = []
    stats = {}
    
    for sector in sorted(sectors, key=lambda s: SECTOR_PRIORITY.get(s, 0), reverse=True):
        print(f"\n📰 {sector}")
        print("-" * 50)
        
        items = search_news_for_sector(sector, max_results=max_per_sector)
        bullish = sum(1 for it in items if analyze_sentiment(it["title"], it.get("description", ""))[0] > 0.2)
        bearish = sum(1 for it in items if analyze_sentiment(it["title"], it.get("description", ""))[0] < -0.2)
        
        stats[sector] = {
            "searches": len(items),
            "bullish": bullish,
            "bearish": bearish,
            "neutral": len(items) - bullish - bearish,
        }
        
        for item in items:
            sentiment, keywords = analyze_sentiment(item["title"], item.get("description", ""))
            parsed = {
                "source": "web_search_dynamic",
                "title": item["title"],
                "url": item["url"],
                "description": item.get("description", ""),
                "sector": sector,
                "query": item["query"],
                "sentiment": round(sentiment, 2),
                "keywords_matched": keywords[:5],
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "is_bearish": sentiment < -0.2,
                "is_bullish": sentiment > 0.2,
                "timestamp": datetime.now().isoformat(),
            }
            all_items.append(parsed)
            
            label = "🟢" if parsed["is_bullish"] else ("🔴" if parsed["is_bearish"] else "⚪")
            print(f"  {label} {parsed['title'][:55]}...")
            print(f"     情绪: {sentiment:+.2f} | 关键词: {', '.join(keywords[:3])}")
        
        time.sleep(0.5)
    
    print("\n" + "=" * 70)
    print(f"✅ 完成！共获取 {len(all_items)} 条新闻")
    
    # 保存原始数据
    output = {
        "fetched_at": datetime.now().isoformat(),
        "sources": ["web_search_dynamic"],
        "stats": {
            "total_items": len(all_items),
            "total_bullish": sum(1 for r in all_items if r.get("is_bullish")),
            "total_bearish": sum(1 for r in all_items if r.get("is_bearish")),
            "total_neutral": sum(1 for r in all_items if not r.get("is_bullish") and not r.get("is_bearish")),
            "sectors_processed": len(stats),
        },
        "sector_stats": stats,
        "items": all_items,
    }
    
    with open(_RAW_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\n💾 已保存: {_RAW_FILE}")
    print(f"📈 看多: {output['stats']['total_bullish']} | 看空: {output['stats']['total_bearish']} | 中性: {output['stats']['total_neutral']}")
    
    return output


def update_sentiment_json(raw_data: Dict) -> Dict:
    """根据新闻数据更新news_sentiment.json"""
    items = raw_data.get("items", [])
    
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
            "note": f"动态新闻{total}条(多{stats['positive']}/空{stats['negative']}/中{stats['neutral']})",
        }
    
    with open(_SENT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"💾 已更新: {_SENT_FILE}")
    return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description="动态新闻搜索驱动系统")
    parser.add_argument("--sectors", type=str, default=None, help="逗号分隔的行业列表")
    parser.add_argument("--count", type=int, default=3, help="每个行业搜索的新闻条数")
    parser.add_argument("--quick", action="store_true", help="快速模式：只搜Top5行业，每个2条")
    args = parser.parse_args()
    
    # 提取活跃行业
    if args.sectors:
        sectors = [s.strip() for s in args.sectors.split(",")]
    else:
        try:
            from etf_platform.analysis.macro_overlay import CATALYSTS
            today = datetime.now().date().isoformat()
            sectors = [s for s, info in CATALYSTS.items() if info.get("expires", "0000-00-00") >= today]
        except ImportError:
            sectors = list(SEARCH_TEMPLATES.keys())
    
    if args.quick:
        sectors = sorted(sectors, key=lambda s: SECTOR_PRIORITY.get(s, 0), reverse=True)[:5]
        count = 2
    else:
        count = args.count
    
    print(f"📊 目标行业: {len(sectors)} 个: {sectors}")
    
    # 搜索新闻
    raw_data = process_all(sectors, max_per_sector=count)
    
    # 更新情绪JSON
    sentiment = update_sentiment_json(raw_data)
    
    print("\n" + "=" * 70)
    print("📈 行业情绪概览:")
    for sector, info in sorted(sentiment.get("sectors", {}).items(), 
                                key=lambda x: SECTOR_PRIORITY.get(x[0], 0), reverse=True):
        print(f"  {sector:12s}: {info['direction']} ({info['strength']}) - {info['note']}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
