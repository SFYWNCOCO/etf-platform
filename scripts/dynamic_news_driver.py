#!/usr/bin/env python3
"""
动态新闻搜索驱动 — 基于网页搜索实时更新行业新闻情绪

Agent调用此脚本的完整流程:
1. 导入 SEARCH_TEMPLATES 和 process_search_results
2. 对每个行业调用 web_search(query=template, limit=N)
3. 调用 process_search_results(sector, results, query) 处理
4. 收集所有处理结果
5. 调用 save_raw_data(items) 和 update_sentiment_from_items(items)

用法 (Agent自动执行):
  python scripts/dynamic_news_driver.py --sectors "核电,电力,半导体,原油" --count 3

用法 (手动测试):
  python scripts/dynamic_news_driver.py --test
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
]
NEG_KEYWORDS = [
    "暴跌", "崩盘", "爆雷", "跌停", "大跌", "重挫", "腰斩", "预亏",
    "亏损", "下滑", "减持", "抛售", "净流出", "制裁", "打压", "立案",
    "调查", "处罚", "下调", "评级下调", "跌破", "新低", "利空",
    "承压", "走弱", "疲软", "放缓", "风险", "担忧", "萎缩", "低迷",
    "战", "冲突", "危机", "制裁", "打压", "抛售", "减持", "亏损",
    "衰退", "萧条", "恶化",
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


def process_search_results(sector: str, search_results: List[Dict], query: str = "") -> List[Dict]:
    """处理web_search返回的结果"""
    from scripts.dynamic_news_integrator import process_search_results as _proc
    return _proc(sector, search_results, query)


def search_and_process(sector: str, count: int = 3) -> List[Dict]:
    """搜索单个行业并处理结果 (Agent调用)"""
    # 注意: 实际搜索由Agent通过web_search工具完成
    # 此函数预留接口，供Agent调用
    return []


def run_full_pipeline(sectors: List[str], count: int = 3) -> Dict:
    """
    运行完整的新闻搜索流程
    
    此函数由Agent调用，需要Agent在执行前准备web_search结果
    """
    all_items = []
    sector_stats = {}
    
    for sector in sectors:
        queries = SEARCH_TEMPLATES.get(sector, [f"{sector} 最新新闻"])
        sector_items = []
        
        for query in queries[:2]:
            # Agent需要在此处调用web_search工具
            # results = agent_call_web_search(query=query, limit=count)
            # processed = process_search_results(sector, results, query)
            pass  # 占位
        
        sector_stats[sector] = {
            "searches": len(sector_items),
            "bullish": sum(1 for it in sector_items if it.get("is_bullish")),
            "bearish": sum(1 for it in sector_items if it.get("is_bearish")),
            "neutral": sum(1 for it in sector_items if not it.get("is_bullish") and not it.get("is_bearish")),
        }
        all_items.extend(sector_items)
    
    # 保存结果
    output = save_raw_data(all_items)
    sentiment = update_sentiment_from_items(all_items)
    
    return {
        "items": all_items,
        "stats": output["stats"],
        "sentiment": sentiment,
        "sector_stats": sector_stats,
    }


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


def update_sentiment_from_items(items: List[Dict]) -> Dict:
    """根据新闻列表更新news_sentiment.json"""
    from scripts.dynamic_news_integrator import update_sentiment_from_items as _update
    return _update(items)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="动态新闻搜索驱动系统")
    parser.add_argument("--sectors", type=str, default=None, help="逗号分隔的行业列表")
    parser.add_argument("--count", type=int, default=3, help="每个行业搜索的新闻条数")
    parser.add_argument("--test", action="store_true", help="测试模式：显示可用模板")
    args = parser.parse_args()
    
    if args.test:
        print("=== 可用搜索模板 ===")
        for sector, queries in SEARCH_TEMPLATES.items():
            print(f"\n{sector}:")
            for q in queries:
                print(f"  - {q}")
        return
    
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
    
    print(f"📊 目标行业: {len(sectors)} 个")
    print(f"💡 请在Agent环境中执行web_search，然后调用process_search_results()")
    print(f"\n可用模板:")
    for sector in sectors[:5]:
        if sector in SEARCH_TEMPLATES:
            print(f"  {sector}: {SEARCH_TEMPLATES[sector]}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
