#!/usr/bin/env python3
"""
动态新闻搜索集成模块 — 供Agent调用进行动态新闻搜索

Agent调用流程:
1. 调用 web_search(query=SEARCH_TEMPLATES[sector], limit=N) 获取搜索结果
2. 调用 process_search_results(sector, results) 处理结果
3. 调用 update_sentiment_from_items(all_items) 更新JSON

用法:
  python scripts/dynamic_news_integrator.py --help
"""
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

_BASE = Path(__file__).resolve().parent.parent
_DATA = _BASE / "data"
_RAW_FILE = _DATA / "news_raw_sources.json"
_SENT_FILE = _DATA / "news_sentiment.json"


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
    "公用事业": ["电网 投资", "电力设备"],
    "金融/券商": ["券商 8月金股 2026", "证券 ETF 行情", "券商并购重组"],
    "白酒": ["白酒 业绩 拐点 2026", "茅台 提价 消费", "白酒 ETF 行情"],
    "央企/国企改革": ["央企重组 整合 2026", "国企改革 ETF", "央企市值管理"],
}


POS_KEYWORDS = [
    "突破", "新高", "超预期", "大涨", "涨停", "爆发", "飙升", "扩产", "中标",
    "获批", "涨价", "上调", "增持", "回购", "净流入", "领涨", "创纪录",
    "利好", "增长", "盈利", "改善", "回暖", "景气", "受益", "推荐",
    "加速", "放量", "走强", "强势", "强劲", "乐观", "看好",
    "核准", "启动", "投产", "签约", "订单", "创新高", "业绩预增", "翻倍",
    "重开", "谈判", "合作", "签约", "获批",
    "领先", "全球", "能力", "自主", "国产", "独立", "创新", "智能",
    "规划", "项目", "投资", "建设", "批准", "获批", "获批",
    "回暖", "复苏", "反弹", "回升", "走强", "利好",
    "放量", "净流入", "增持", "回购", "涨停", "领涨",
    "超预期", "强劲", "景气", "扩产", "中标", "签约",
]
NEG_KEYWORDS = [
    "暴跌", "崩盘", "爆雷", "跌停", "大跌", "重挫", "腰斩", "预亏",
    "亏损", "下滑", "减持", "抛售", "净流出", "制裁", "打压", "立案",
    "调查", "处罚", "下调", "评级下调", "跌破", "新低", "利空",
    "承压", "走弱", "疲软", "放缓", "风险", "担忧", "萎缩", "低迷",
    "战", "冲突", "危机", "制裁", "打压", "抛售", "减持", "亏损",
    "衰退", "萧条", "恶化", "暴跌", "破位", "承压",
    "过剩", "降价", "萎缩", "下滑", "预亏", "亏损", "退场",
    "出清", "淘汰", "出清", "过剩", "低迷", "疲软",
]


def analyze_sentiment(title: str, description: str) -> Tuple[float, List[str]]:
    """分析新闻情绪，返回情绪分数和匹配的关键词"""
    text = f"{title} {description}"
    matched_pos = [kw for kw in POS_KEYWORDS if kw in text]
    matched_neg = [kw for kw in NEG_KEYWORDS if kw in text]
    
    pos_score = len(matched_pos) * 0.25
    neg_score = len(matched_neg) * 0.25
    sentiment = max(-1.0, min(1.0, pos_score - neg_score))
    
    return sentiment, matched_pos + matched_neg


def process_search_results(sector: str, search_results: List[Dict], query: str = "") -> List[Dict]:
    """
    处理web_search返回的结果，转换为标准化格式
    
    Args:
        sector: 行业名称
        search_results: web_search返回的items列表
        query: 搜索关键词
    
    Returns:
        处理后的新闻列表
    """
    processed = []
    for item in search_results:
        title = item.get("title", "")
        url = item.get("url", "")
        description = item.get("description", "")
        
        sentiment, keywords = analyze_sentiment(title, description)
        
        processed.append({
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
        })
    
    return processed


def update_sentiment_from_items(items: List[Dict]) -> Dict:
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
    
    return result


def save_raw_data(items: List[Dict]) -> Dict:
    """保存原始新闻数据"""
    output = {
        "fetched_at": datetime.now().isoformat(),
        "sources": ["web_search_dynamic"],
        "stats": {
            "total_items": len(items),
            "total_bullish": sum(1 for r in items if r.get("is_bullish")),
            "total_bearish": sum(1 for r in items if r.get("is_bearish")),
            "total_neutral": sum(1 for r in items if not r.get("is_bullish") and not r.get("is_bearish")),
        },
        "items": items,
    }
    
    with open(_RAW_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    return output


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="动态新闻搜索集成模块")
    parser.add_argument("--sectors", type=str, required=True, help="逗号分隔的行业列表")
    parser.add_argument("--count", type=int, default=3, help="每个行业搜索条数")
    args = parser.parse_args()
    
    sectors = [s.strip() for s in args.sectors.split(",")]
    print(f"📊 目标行业: {sectors}")
    print(f"⚠️  请在Agent环境中调用web_search工具进行搜索")
    print(f"💡 用法: agent_call_web_search(sector, query) -> results")
    print(f"       process_search_results(sector, results) -> processed_items")
    print(f"       update_sentiment_from_items(processed_items)")
    
    # 显示可用的搜索模板
    for sector in sectors:
        if sector in SEARCH_TEMPLATES:
            print(f"  🔍 {sector}: {SEARCH_TEMPLATES[sector]}")
