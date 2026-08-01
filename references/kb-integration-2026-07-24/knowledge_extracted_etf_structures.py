"""
从 k130-etf-kline-analysis-20260719.md 和 k131-etf-market-adjustment-analysis-20260719.md
提取的量化数据结构，可直接注入 pipeline 层。

生成时间: 2026-07-24
覆盖日期: 2026-07-19
"""

ETF_KNOWLEDGE = {

    # ============================================================
    # 1. 数据概况 & 元信息
    # ============================================================
    "meta": {
        "report_date": "2026-07-19",
        "analysis_date": "2026-07-17",           # K线收盘价基准日
        "time_range": {
            "start": "2026-06-19",
            "end": "2026-07-17",
            "trading_days": 20
        },
        "data_source": "东方财富实时API / Wind / Choice",
        "total_etf_count": 592,
        "successful_fetch": 587,
        "fetch_success_rate": 0.992,
    },

    # ============================================================
    # 2. 主题板块 20 日涨跌统计 → 可映射到 pipeline: sector_score / filter
    # ============================================================
    "sector_20d_returns": {
        "红利/价值": {
            "count": 33,
            "avg_return_pct": -2.11,
            "median_return_pct": -1.72,
            "best_return_pct": -1.18,
            "worst_return_pct": -7.09,
            "risk_level": "低",                    # 相对抗跌
            "strategy_signal": "防御优先"
        },
        "消费": {
            "count": 16,
            "avg_return_pct": -3.91,
            "median_return_pct": -3.16,
            "best_return_pct": -1.46,
            "worst_return_pct": -8.86,
            "risk_level": "中低",
            "strategy_signal": "关注 / 估值回归合理区间"
        },
        "新能源": {
            "count": 28,
            "avg_return_pct": -4.52,
            "median_return_pct": -4.49,
            "best_return_pct": -3.91,
            "worst_return_pct": -5.19,
            "risk_level": "中",
            "strategy_signal": "回避"
        },
        "其他": {
            "count": 391,
            "avg_return_pct": -4.63,
            "median_return_pct": -4.63,
            "best_return_pct": -0.00,
            "worst_return_pct": -10.75,
            "risk_level": "中",
        },
        "跨境": {
            "count": 17,
            "avg_return_pct": -5.37,
            "median_return_pct": -6.37,
            "best_return_pct": -1.77,
            "worst_return_pct": -7.86,
            "risk_level": "中高",
        },
        "医药": {
            "count": 24,
            "avg_return_pct": -6.41,
            "median_return_pct": -6.52,
            "best_return_pct": -4.67,
            "worst_return_pct": -9.78,
            "risk_level": "高",
        },
        "AI/科技": {
            "count": 56,
            "avg_return_pct": -6.79,
            "median_return_pct": -6.52,
            "best_return_pct": -1.80,
            "worst_return_pct": -11.24,
            "risk_level": "高",
            "strategy_signal": "回避 / 等待-15%分批建仓"
        },
        "半导体": {
            "count": 17,
            "avg_return_pct": -7.88,
            "median_return_pct": -7.89,
            "best_return_pct": -7.28,
            "worst_return_pct": -8.52,
            "risk_level": "极高",
            "strategy_signal": "回避 / 左侧布局关注"
        },
        "通信": {
            "count": 5,
            "avg_return_pct": -8.26,
            "median_return_pct": -8.06,
            "best_return_pct": -7.79,
            "worst_return_pct": -9.02,
            "risk_level": "极高",
            "strategy_signal": "回避"
        },
    },

    # ============================================================
    # 3. 弱势 ETF TOP15（跌幅>5%，实际均>9%）→ pipeline: blacklist / risk_filter
    # ============================================================
    "top_weak_etfs": [
        {"code": "159279", "name": "AI创业",          "close_price": 1.327, "change_20d_pct": -11.24},
        {"code": "159381", "name": "创AI",            "close_price": 1.106, "change_20d_pct": -10.88},
        {"code": "159243", "name": "创业智能",         "close_price": 1.187, "change_20d_pct": -10.75},
        {"code": "159242", "name": "创业AIDC",         "close_price": 1.970, "change_20d_pct": -10.54},
        {"code": "159246", "name": "创AI富国",         "close_price": 1.100, "change_20d_pct": -10.20},
        {"code": "159363", "name": "创业板人工智能ETF华宝", "close_price": 1.168, "change_20d_pct": -10.08},
        {"code": "159382", "name": "AI创业板",          "close_price": 2.501, "change_20d_pct": -10.04},
        {"code": "159388", "name": "创业AI",           "close_price": 0.956, "change_20d_pct": -9.90},
        {"code": "159248", "name": "AI万家",           "close_price": 1.770, "change_20d_pct": -9.88},
        {"code": "159167", "name": "香港医疗",          "close_price": 0.812, "change_20d_pct": -9.78},
        {"code": "159139", "name": "华泰AI",           "close_price": 1.251, "change_20d_pct": -9.74},
        {"code": "159142", "name": "双创AI",           "close_price": 1.205, "change_20d_pct": -9.33},
        {"code": "159546", "name": "集成电路",          "close_price": 0.808, "change_20d_pct": -9.32},
        {"code": "159022", "name": "AI双创",           "close_price": 1.018, "change_20d_pct": -9.19},
        {"code": "159140", "name": "创智能E",          "close_price": 1.256, "change_20d_pct": -9.05},
    ],

    # ============================================================
    # 4. 市场级统计指标 → pipeline: aggregate thresholds
    # ============================================================
    "market_aggregates": {
        "all_negative_etf_count": 587,              # 无一只正收益
        "decline_over_5pct_count": 282,             # 跌幅超5%的数量
        "decline_over_5pct_ratio": 282 / 587,       # ≈0.4804 (48.0%)
        "dominant_trend": "全市场普跌，无一正收益",
    },

    # ============================================================
    # 5. 本周 ETF 资金流向 → pipeline: fund_flow_signal
    # ============================================================
    "capital_flow_weekly": {
        "period": "2026-07-13 ~ 2026-07-17",
        "stock_etf_plus_crossborder_inflow_billion": 2113.21,
        "stock_etf_plus_crossborder_share_pct": 0.922,
        "broad_based_inflow_billion": 1561.0,
        "broad_based_share_pct": 0.680,
        "industry_theme_inflow_billion": 444.0,
        "industry_theme_share_pct": 0.194,
    },

    # ============================================================
    # 6. 月度资金流 → pipeline: medium_term_flow_trend
    # ============================================================
    "capital_flow_monthly": {
        "period_start": "2026-07-01",
        "trading_days_with_net_inflow": 12,
        "total_trading_days": 13,
        "net_inflow_billion": 3300.0,
        "single_day_peak_billion": 763.49,
        "peak_day": "本周五(2026-07-17)",
        "trend_label": "持续净流入，底部放量信号"
    },

    # ============================================================
    # 7. 头部宽基 ETF 成交放量 → pipeline: liquidity_monitor
    # ============================================================
    "top_etf_volume": [
        {"name": "创业板ETF易方达", "code": "159915", "daily_volume_billion_gt": 140, "signal": "集体放量"},
        {"name": "沪深300ETF华泰柏瑞", "code": "510300", "daily_volume_billion_gt": 140, "signal": "规模重回第一", "aum_billion": 935},
        {"name": "科创50ETF华夏", "code": "588000", "daily_volume_billion_gt": 140, "signal": "集体放量"},
    ],

    # ============================================================
    # 8. 主要股指表现 → pipeline: benchmark_context
    # ============================================================
    "index_performance": {
        "上证指数": {"level": "<3800", "note": "跌破3800点", "friday_single_day_drop_pct_gt": 3},
        "创业板指": {"change_pct": -7.15, "note": "单日重挫"},
        "科创50": {"change_pct": -7.0, "note": "科技成长领跌", "change_pct_gt_exact": True},
        "中证2000": {"status": "面临技术熊市", "note": "小盘股承压"},
        "中证1000": {"status": "面临技术熊市", "note": "小盘股承压"},
    },

    # ============================================================
    # 9. 外围冲击指标 → pipeline: external_shock_filter
    # ============================================================
    "external_shocks": {
        "韩国股市": {
            "july10_drop_pct": -5.4,
            "cumulative_drop_pct": -20.0,
            "status": "技术性熊市"
        },
        "日经225": {
            "drop_pct_gt": -4.0,
            "softbank_drop_pct_gt": -9.0
        },
        "费城半导体SOX": {
            "drop_from_high_pct": -21.0,
            "reference_date": "2026-06-22",
            "status": "技术性熊市"
        },
    },

    # ============================================================
    # 10. 科技股/个股回调事件 → pipeline: event_filter
    # ============================================================
    "tech_stocks_drawdown": {
        "存储芯片": {
            "SK海力士ADR_drop_pct": -13.69,
            "闪迪_drop_pct": -12.63,
        },
        "A股半导体": {
            "德明利": "3连跌停",
            "兆易创新": "跌停",
        },
        "CPO/光模块": {
            "affected": ["中际旭创", "新易盛", "天孚通信"],
            "drop_pct_gt": -10.0
        },
    },

    # ============================================================
    # 11. 政策催化 → pipeline: catalyst_scoring
    # ============================================================
    "policy_catalysts": [
        {
            "source": "国家发改委",
            "event": "发布《人工智能合作发展行动计划》",
            "sector_impact": "AI/科技",
            "sentiment": "positive",
            "strength": "high"
        },
        {
            "source": "WAIC 2026",
            "event": "开幕，60台人形机器人规模化部署",
            "sector_impact": "AI/机器人",
            "sentiment": "positive",
            "strength": "medium"
        },
        {
            "source": "星枢计划",
            "event": "首发星座发布（2颗算力星+12颗边缘计算星）",
            "sector_impact": "卫星互联网/边缘计算",
            "sentiment": "positive",
            "strength": "medium"
        },
    ],

    # ============================================================
    # 12. 机构观点 → pipeline: sentiment_layer / expert_consensus
    # ============================================================
    "institutional_views": [
        {
            "institution": "方正证券",
            "key_message": "科技股调整已较为充分，超跌反弹是更大概率事件",
            "historical_reference": "2010年以来典型赛道抱团回撤高点回撤约20%",
            "extreme_zone": "-30%~-40%",
            "current_drawdown_pct": -28.0,
            "recommendation": "超跌反弹概率大",
            "sentiment": "positive_reversal"
        },
        {
            "institution": "海通国际",
            "analyst": "张忆东",
            "key_message": "左侧布局中国股市秋季行情时机呼之欲出",
            "three_focus_areas": ["安全资产", "制造出海", "高科技硬科技"],
            "sentiment": "cautiously_positive"
        },
        {
            "institution": "央视财经",
            "key_message": "多家外资机构看好中国AI产业链，已成全球共识",
            "supporting_data": {
                "china_daily_chip_production": "超15亿块",
                "llm_daily_call_volume": "数百万亿词元",
                "global_rank": "世界首位"
            },
            "sentiment": "strongly_positive"
        },
    ],

    # ============================================================
    # 13. ETF 配置建议 → pipeline: allocation_scorer / final_selection
    # ============================================================
    "sector_allocation_recommendations": {
        "defensive": {
            "label": "防御配置（当前环境）",
            "items": [
                {
                    "sector": "红利/价值",
                    "example_etf": "沪深300红利ETF",
                    "logic": "相对抗跌，避险属性",
                    "weight_priority": 1,             # 最高优先级
                    "pipeline_tag": "defensive_core"
                },
                {
                    "sector": "宽基",
                    "example_etf": "沪深300ETF(510300)",
                    "logic": "规模第一，资金青睐",
                    "weight_priority": 2,
                    "pipeline_tag": "defensive_core"
                },
                {
                    "sector": "电力",
                    "example_etf": "电力ETF",
                    "logic": "逆势走强 +2%",
                    "weight_priority": 3,
                    "pipeline_tag": "defensive_alpha"
                },
            ]
        },
        "left_side": {
            "label": "左侧布局（等待企稳）",
            "items": [
                {
                    "sector": "科创50",
                    "example_etf": "科创50ETF(588000)",
                    "logic": "成交放量，资金提前布局",
                    "entry_condition": "市场情绪企稳",
                    "pipeline_tag": "contrarian_entry"
                },
                {
                    "sector": "半导体",
                    "example_etf": "半导体ETF(512480)",
                    "logic": "调整28%，超跌反弹概率大",
                    "entry_condition": "-15%以下分批建仓",
                    "pipeline_tag": "oversold_rebound"
                },
                {
                    "sector": "AI/科技",
                    "example_etf": "人工智能ETF",
                    "logic": "WAIC催化+政策支持",
                    "entry_condition": "企稳信号确认",
                    "pipeline_tag": "catalyst_play"
                },
            ]
        },
        "avoid": {
            "label": "回避",
            "items": [
                {"reason": "高波动科技成长类短期继续承压", "pipeline_tag": "risk_off"},
                {"reason": "小盘股ETF面临技术熊市（中证2000/1000）", "pipeline_tag": "risk_off"},
            ]
        }
    },

    # ============================================================
    # 14. Pipeline 过滤阈值汇总 → 可直接写死在 config/rules 层
    # ============================================================
    "pipeline_thresholds": {
        "avoid_20d_drop_gt_pct": {
            "AI_科技": -6.0,
            "半导体设备材料": -7.0,
            "通信光模块": -8.0,
        },
        "oversold_build_position_pct": -15.0,   # 低于此值考虑分批建仓
        "defensive_prefer_sectors": ["红利/价值", "消费"],
        "high_risk_sectors": ["AI/科技", "半导体", "通信"],
        "externalbear_market_threshold_pct": -20.0,
        "phx_semiconductor_bear_market_threshold_pct": -20.0,
        "weekly_net_inflow_billion_trigger": 1000.0,   # 周净流入超1000亿为强信号
        "single_day_inflow_peak_billion": 763.49,
    },

    # ============================================================
    # 15. 关键观察点 → pipeline: next_event_watchlist
    # ============================================================
    "next_watchpoints": [
        {
            "item": "下周前半周市场止跌修复",
            "type": "technical",
            "timeframe": "1周内",
            "importance": "high"
        },
        {
            "item": "宽基ETF放量信号解读",
            "type": "liquidity",
            "interpretation": "可能是短期底部信号或下跌中继",
            "importance": "high"
        },
        {
            "item": "茅台提价",
            "type": "fundamental",
            "impact_sector": "消费/白酒",
            "importance": "medium"
        },
        {
            "item": "长鑫科技IPO",
            "type": "event",
            "detail": "科创板史上最大IPO",
            "valuation_billion": 5792,
            "importance": "high"
        },
    ],
}


# ============================================================
# 便捷访问函数
# ============================================================

def get_pipeline_summary():
    """返回可供 pipeline 直接消费的摘要 dict。"""
    return {
        "date": ETF_KNOWLEDGE["meta"]["report_date"],
        "market_status": "全市场普跌，无一正收益",
        "best_sectors": sorted(
            ETF_KNOWLEDGE["sector_20d_returns"].keys(),
            key=lambda s: ETF_KNOWLEDGE["sector_20d_returns"][s]["avg_return_pct"],
            reverse=True
        )[:3],
        "worst_sectors": sorted(
            ETF_KNOWLEDGE["sector_20d_returns"].keys(),
            key=lambda s: ETF_KNOWLEDGE["sector_20d_returns"][s]["avg_return_pct"]
        )[:3],
        "weekly_fund_flow_billion": ETF_KNOWLEDGE["capital_flow_weekly"]["stock_etf_plus_crossborder_inflow_billion"],
        "monthly_fund_flow_billion": ETF_KNOWLEDGE["capital_flow_monthly"]["net_inflow_billion"],
        "defensive_picks": [x["sector"] for x in ETF_KNOWLEDGE["sector_allocation_recommendations"]["defensive"]["items"]],
        "contrarian_picks": [x["sector"] for x in ETF_KNOWLEDGE["sector_allocation_recommendations"]["left_side"]["items"]],
        "positive_catalysts_count": len(ETF_KNOWLEDGE["policy_catalysts"]),
        "institutional_sentiment_avg": "cautiously_positive",
    }


if __name__ == "__main__":
    import json
    print(json.dumps(get_pipeline_summary(), ensure_ascii=False, indent=2))
