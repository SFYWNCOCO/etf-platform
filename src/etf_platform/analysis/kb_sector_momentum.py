"""
kb_sector_momentum.py — KB驱动的行业动量/资金流先验层 (v1.0)

知识库来源:
  - k130-etf-kline-analysis-20260719.md: 587只ETF 20日涨跌统计，行业动量排名
  - k131-etf-market-adjustment-analysis-20260719.md: 真实资金流向(2113亿/周净流入)，机构观点，调整归因

集成方式:
  1. sector_kline_stats: k130提取的行业20日收益先验 → L17因子层/sector_scores参考
  2. capital_flow_index: k131提取的资金流向数据 → L8_CapitalFlow增强(当akshare失败时fallback)
  3. institutional_view: k131机构观点 → macro_overlay CATALYSTS补充
  4. adjustment_attribution: 调整原因(韩国/日经/SOX/存储芯片) → L5_Tech/L9_Signals归因

设计理念:
  KB数据不是静态死数字，而是pipeline的"冷启动锚定"和"数据故障时的安全网"。
  akshare挂死时，sector_kline_stats仍能提供有意义的动量信号。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)

KB_ROOT = Path("D:/龙虾/.openclaw/knowledge")
CACHE_FILE = KB_ROOT / "meta" / "_kb_sector_momentum_cache.json"

# ═══════════════════════════════════════════
# k130: 20日行业K线动量统计 (2026-07-19, 587只ETF)
# 全市场普跌格局，无一只正收益
# ═══════════════════════════════════════════

SECTOR_KLINE_STATS: Dict[str, Dict] = {
    "红利/价值": {"ret_20d": -2.11, "count": 33, "label": "最优防御", "strategies": ["hold", "accumulate"], "notes": "相对抗跌，避险需求强烈"},
    "消费":       {"ret_20d": -3.91, "count": 16, "label": "跌幅适中", "strategies": ["watch", "buy_dip"], "notes": "估值回归合理区间"},
    "新能源":     {"ret_20d": -4.52, "count": 28, "label": "中幅回调", "strategies": ["wait"], "notes": "产能过剩+价格战"},
    "其他":       {"ret_20d": -4.63, "count": 391, "label": "普跌", "strategies": ["wait"], "notes": "大盘拖累"},
    "跨境":       {"ret_20d": -5.37, "count": 17, "label": "海外联动下跌", "strategies": ["wait"], "notes": "跟踪美股/港股指数"},
    "医药":       {"ret_20d": -6.41, "count": 24, "label": "深度回调", "strategies": ["left_side"], "notes": "创新药管线催化待验证"},
    "AI/科技":    {"ret_20d": -6.79, "count": 56, "label": "显著回调", "strategies": ["left_side"], "notes": "WAIC催化+政策支持但高位回调充分"},
    "半导体":     {"ret_20d": -7.88, "count": 17, "label": "深度调整", "strategies": ["left_side", "batch_build"], "notes": "适合短线不适合长持，-15%以下分批建仓"},
    "通信":       {"ret_20d": -8.26, "count": 5, "label": "领跌板块", "strategies": ["wait_deep"], "notes": "CPO/光模块领跌，需等待企稳"},
}

# 弱市TOP15 (跌幅>5%, 来自k130)
WEAK_ETFS_TOP15 = [
    {"code": "159279", "name": "AI创业", "ret_20d": -11.24},
    {"code": "159381", "name": "创AI", "ret_20d": -10.88},
    {"code": "159243", "name": "创业智能", "ret_20d": -10.75},
    {"code": "159242", "name": "创业AIDC", "ret_20d": -10.54},
    {"code": "159246", "name": "创AI富国", "ret_20d": -10.20},
    {"code": "159363", "name": "创业板人工智能ETF华宝", "ret_20d": -10.08},
    {"code": "159382", "name": "AI创业板", "ret_20d": -10.04},
    {"code": "159388", "name": "创业AI", "ret_20d": -9.90},
    {"code": "159248", "name": "AI万家", "ret_20d": -9.88},
    {"code": "159167", "name": "香港医疗", "ret_20d": -9.78},
    {"code": "159139", "name": "华泰AI", "ret_20d": -9.74},
    {"code": "159142", "name": "双创AI", "ret_20d": -9.33},
    {"code": "159546", "name": "集成电路", "ret_20d": -9.32},
    {"code": "159022", "name": "AI双创", "ret_20d": -9.19},
    {"code": "159140", "name": "创智能E", "ret_20d": -9.05},
]

TOTAL_DROP_OVER_5PCT = 282

# k130 → 行业→K线动量因子映射（注入L17/L18）
SECTOR_TO_KLINE_FACTOR = {
    # sector keyword → ret_20d proxy → momentum_signal
    # ret_20d > -4: 防御/抗跌 → LowVol + Quality bonus
    # ret_20d < -7: 深调 → Momentum reversal signal (if支撑)
    "红利": {"momentum_regime": "defensive", "ret_proxy": -2.11, "kline_score_bias": 1.5, "strategy": "hold"},
    "价值": {"momentum_regime": "defensive", "ret_proxy": -2.11, "kline_score_bias": 1.5, "strategy": "hold"},
    "消费": {"momentum_regime": "moderate_drawdown", "ret_proxy": -3.91, "kline_score_bias": 0.0, "strategy": "watch"},
    "白酒": {"momentum_regime": "moderate_drawdown", "ret_proxy": -3.91, "kline_score_bias": 0.5, "strategy": "watch"},
    "食品饮料": {"momentum_regime": "moderate_drawdown", "ret_proxy": -3.91, "kline_score_bias": 0.0, "strategy": "watch"},
    "家电": {"momentum_regime": "moderate_drawdown", "ret_proxy": -3.91, "kline_score_bias": 0.0, "strategy": "watch"},
    "新能源": {"momentum_regime": "moderate_drawdown", "ret_proxy": -4.52, "kline_score_bias": -1.0, "strategy": "wait"},
    "光伏": {"momentum_regime": "deep_correction", "ret_proxy": -4.52, "kline_score_bias": -1.5, "strategy": "wait_deep"},
    "风电": {"momentum_regime": "deep_correction", "ret_proxy": -4.52, "kline_score_bias": -1.0, "strategy": "wait"},
    "医药": {"momentum_regime": "deep_correction", "ret_proxy": -6.41, "kline_score_bias": -2.0, "strategy": "left_side"},
    "中药": {"momentum_regime": "deep_correction", "ret_proxy": -6.41, "kline_score_bias": -1.0, "strategy": "left_side"},
    "创新药": {"momentum_regime": "deep_correction", "ret_proxy": -6.41, "kline_score_bias": -1.5, "strategy": "left_side"},
    "AI/科技": {"momentum_regime": "significant_drawdown", "ret_proxy": -6.79, "kline_score_bias": -2.5, "strategy": "left_side"},
    "AI算力": {"momentum_regime": "significant_drawdown", "ret_proxy": -6.79, "kline_score_bias": -2.0, "strategy": "left_side"},
    "硬科技": {"momentum_regime": "significant_drawdown", "ret_proxy": -6.79, "kline_score_bias": -2.0, "strategy": "left_side"},
    "计算机": {"momentum_regime": "significant_drawdown", "ret_proxy": -6.79, "kline_score_bias": -1.5, "strategy": "left_side"},
    "半导体": {"momentum_regime": "deep_correction", "ret_proxy": -7.88, "kline_score_bias": -3.0, "strategy": "batch_build_below_-15"},
    "芯片": {"momentum_regime": "deep_correction", "ret_proxy": -7.88, "kline_score_bias": -3.0, "strategy": "batch_build_below_-15"},
    "通信": {"momentum_regime": "leading_drop", "ret_proxy": -8.26, "kline_score_bias": -3.5, "strategy": "wait_deep"},
    "光模块": {"momentum_regime": "leading_drop", "ret_proxy": -8.26, "kline_score_bias": -3.5, "strategy": "wait_deep"},
    "银行": {"momentum_regime": "defensive", "ret_proxy": -2.11, "kline_score_bias": 1.0, "strategy": "hold"},
    "金融": {"momentum_regime": "defensive", "ret_proxy": -2.11, "kline_score_bias": 0.5, "strategy": "hold"},
    "券商": {"momentum_regime": "high_beta_pullback", "ret_proxy": -4.0, "kline_score_bias": -1.0, "strategy": "wait_for_confirm"},
    "黄金": {"momentum_regime": "defensive_haven", "ret_proxy": -1.0, "kline_score_bias": 2.0, "strategy": "hold"},
    "贵金属": {"momentum_regime": "defensive_haven", "ret_proxy": -1.0, "kline_score_bias": 2.0, "strategy": "hold"},
    "电力": {"momentum_regime": "defensive_outperform", "ret_proxy": -1.5, "kline_score_bias": 1.5, "strategy": "hold"},
}

# ═══════════════════════════════════════════
# k131: 资金流向 + 机构观点
# ═══════════════════════════════════════════

CAPITAL_FLOW_INDEX: Dict[str, object] = {
    "week_net_inflow_total_etf": 2113.21,      # 亿元, 股票型ETF+跨境型
    "week_net_inflow_broad": 1561.0,           # 亿元, 宽基ETF
    "week_net_inflow_sector": 444.0,            # 亿元, 行业主题ETF
    "month_cumulative_stock_etf": 3300.0,       # 亿元, 7月以来累计(13个交易日中12天净流入)
    "friday_peak_single_day": 763.49,           # 亿元, 本周五单日极值
    "top_volume_etfs": {
        "159915": {"name": "创业板ETF易方达", "daily_volume": ">140亿", "signal": "放量"},
        "510300": {"name": "沪深300ETF华泰柏瑞", "daily_volume": ">140亿", "signal": "规模第一935亿"},
        "588000": {"name": "科创50ETF华夏", "daily_volume": ">140亿", "signal": "放量"},
    },
    "inflow_ratio": {
        "broad_base_pct": 0.680,
        "stock_etf_cross_pct": 0.922,
        "sector_theme_pct": 0.194,
    },
    "data_date": "2026-07-17",
    "interpretation": "资金从科技成长撤出→涌入宽基防御。越跌越买宽基，体现避险+抄底双动机。",
}

# 机构观点 → CATALYST映射
INSTITUTIONAL_VIEWS: Dict[str, Dict] = {
    "方正证券": {
        "stance": "bullish_mean_reversion",
        "quote": "超跌反弹是更大概率事件",
        "drawdown_reference": {
            "typical_sector_drawdown_from_top": -20.0,
            "extreme_drawdown": "-30%~-40%极限区间",
            "current_ai_gpu_drawdown": -28.0,
        },
        "actionable": "半导体/AI调整28%接近历史典型回撤极限，左侧布局窗口",
    },
    "海通国际张忆东": {
        "stance": "left_side_layout_autumn",
        "quote": "夏日寒风已进入余波阶段",
        "three_themes": ["安全资产", "制造出海", "高科技硬科技"],
        "actionable": "推荐防御(安全资产)+进攻(制造/科技)哑铃配置",
    },
    "央视财经(外资共识)": {
        "stance": "bullish_china_ai_chain",
        "quote": "投资中国AI产业链已经成为全球投资者的共识",
        "facts": ["中国平均每天生产芯片超15亿块", "大模型日均调用量数百万亿词元"],
        "actionable": "AI产业链中长期逻辑未破坏，回调即机会",
    },
}

# 调整归因（利空信号）
ADJUSTMENT_ATRIBUTIONS = {
    "external_shocks": [
        {"source": "韩国股市", "impact": "7月10日-5.4%，累计-20%技术性熊市", "etf_impact": ["半导体", "存储芯片", "跨境科技"]},
        {"source": "日经225", "impact": "跌超4%，软银集团-9%", "etf_impact": ["半导体", "科技"]},
        {"source": "费城半导体SOX", "impact": "较6月22日高点-21%技术性熊市", "etf_impact": ["半导体", "通信/光模块"]},
        {"source": "存储芯片", "impact": "SK海力士ADR-13.69%, 闪迪-12.63%", "etf_impact": ["半导体", "存储"]},
        {"source": "CPO/光模块", "impact": "中际旭创/新易盛/天孚通信-10%", "etf_impact": ["通信/光模块", "AI算力"]},
    ],
    "policy_support": [
        {"source": "发改委", "event": "《人工智能合作发展行动计划》发布", "etf_impact": ["AI/科技", "AI算力"], "direction": "positive"},
        {"source": "WAIC 2026", "event": "开幕+60台人形机器人规模化部署", "etf_impact": ["机器人/智造", "AI/科技"], "direction": "positive"},
        {"source": "星枢计划", "event": "首发星座(2颗算力星+12颗边缘计算星)", "etf_impact": ["通信", "卫星导航"], "direction": "positive"},
    ],
}


# ═══════════════════════════════════════════
# k128: H1业绩与资金流向 (2026上半年)
# ═══════════════════════════════════════════

H1_2026_PERFORMANCE: Dict[str, object] = {
    "total_etf_scale": 76700.0,          # 亿元, 全市场ETF规模(7.67万亿), 7年新高
    "stock_etf_scale": 11000.0,          # 亿元, 首次突破万亿
    "h1_net_inflow": 1600.0,             # 亿元, 上半年场外资金持续入场
    "double_gain_etfs": 245,             # 只, 翻倍基创新高
    "historical_comparison": ["2015年", "2007年"],
    "top_performers": [
        {"rank": 1, "name": "方正富邦核心优势A", "type": "主动权益", "return_pct": 183.0, "driver": "AI+半导体"},
        {"rank": 2, "name": "鹏华科创板半导体材料设备ETF", "type": "行业ETF", "return_pct": 177.0, "driver": "科创半导体设备"},
        {"rank": 3, "name": "华夏上证科创板半导体材料设备ETF", "type": "行业ETF", "return_pct": 170.0, "driver": "同指数"},
        {"rank": 8, "name": "中韩半导体ETF华泰柏瑞", "type": "QDII", "return_pct": 100.0, "driver": "韩国半导体"},
    ],
    "fund_manager_consensus_themes": [
        "半导体设备（AI算力需求爆发）",
        "存储芯片（DRAM/NAND涨价）",
        "国产化进程（设备/材料受益）",
        "光通信",
        "半导体设备（嘉实何鸣晓确认下半年主线）",
    ],
    "v_shape_pattern": True,
    "v_shape_narrative": "前期被抛售→后期资金大幅流入；76只ETF份额逆势增长，科技硬件第一方向",
    "single_day_flows_may18": {
        "inflow_510050": 9.78,     # 亿元, 上证50ETF华夏
        "outflow_588000": -17.53,  # 亿元, 科创50ETF华夏
        "outflow_chip_etf": -12.72,# 亿元, 科创芯片ETF嘉实
        "outflow_chem_etf": -11.0, # 亿元, 化工ETF鹏华
    },
}

# ═══════════════════════════════════════════
# Sector-to-Behavior mapping for KB-injected bias
# k130 20日涨跌 → 可用于L21_Behavior 的情绪校准
# ═══════════════════════════════════════════

SECTOR_BEHAVIOR_CALIBRATION = {
    # ret_20d在某个范围时，对应散户行为偏差
    # 全市场普跌 → 恐慌抛售+割肉+追涨杀跌
    "-10_to_minus5": {
        "dominant_bias": "panic_selling",
        "description": "散户恐慌抛售，割肉离场",
        "score_adjustment": -1.0,  # 行为偏差不利
    },
    "-5_to_minus3": {
        "dominant_bias": "loss_aversion_realization",
        "description": "损失厌恶变现，犹豫不决",
        "score_adjustment": -0.5,
    },
    "-3_to_0": {
        "dominant_bias": "disposition_effect_accumulation",
        "description": "处置效应：亏损仓位越跌越拿，右侧观望",
        "score_adjustment": 0.0,
    },
    "0_to_plus3": {
        "dominant_bias": "fomo_chasing",
        "description": "FOMO追涨，热门板块拥挤度上升",
        "score_adjustment": -0.5,
    },
    "plus3_to_plus10": {
        "dominant_bias": "herd_momentum",
        "description": "羊群动量，资金集中涌入",
        "score_adjustment": -1.0,
    },
    "plus10_plus": {
        "dominant_bias": "euphoria_climax",
        "description": "群体狂热见顶信号",
        "score_adjustment": -2.0,
    },
}


class KBSectorMomentum:
    """KB驱动的行业动量/资金流先验引擎。"""

    def __init__(self, force_refresh: bool = False):
        self._force_refresh = force_refresh
        self._cache_loaded = False

    def get_sector_kline_signal(self, sector: str) -> Dict:
        """返回给定sector的行业K线动量信号。"""
        for keyword, sig in SECTOR_TO_KLINE_FACTOR.items():
            if keyword in sector:
                return {
                    "sector": sector,
                    "matched_keyword": keyword,
                    "momentum_regime": sig["momentum_regime"],
                    "ret_20d_proxy": sig["ret_proxy"],
                    "kline_score_bias": sig["kline_score_bias"],
                    "recommended_strategy": sig["strategy"],
                    "kb_source": "k130",
                }
        return {"sector": sector, "matched_keyword": None, "kline_score_bias": 0.0,
                "recommended_strategy": "neutral", "kb_source": "k130"}

    def get_capital_flow_context(self) -> Dict:
        """返回当前资金流向宏观上下文。"""
        return {
            "week_net_inflow_yi": CAPITAL_FLOW_INDEX["week_net_inflow_total_etf"],
            "broad_base_domination_pct": CAPITAL_FLOW_INDEX["inflow_ratio"]["broad_base_pct"],
            "sector_theme_pct": CAPITAL_FLOW_INDEX["inflow_ratio"]["sector_theme_pct"],
            "narrative": CAPITAL_FLOW_INDEX["interpretation"],
            "data_date": CAPITAL_FLOW_INDEX["data_date"],
        }

    def get_institutional_bias(self) -> Dict:
        """返回机构观点综合判断。"""
        bullish = sum(1 for v in INSTITUTIONAL_VIEWS.values() if v["stance"].startswith("bull"))
        neutral = sum(1 for v in INSTITUTIONAL_VIEWS.values() if "neutral" in v["stance"])
        bearish = len(INSTITUTIONAL_VIEWS) - bullish - neutral
        return {
            "bullish_count": bullish,
            "neutral_count": neutral,
            "bearish_count": bearish,
            "consensus": "偏多（回调即买入窗口）",
            "key_themes": ["半导体设备", "光通信", "存储芯片", "安全资产", "制造出海", "高科技硬科技"],
        }

    def get_k128_cycle_anchor(self) -> Dict:
        """k128 H1业绩数据 → L13周期层锚定信号。"""
        return {
            "double_gain_count": H1_2026_PERFORMANCE["double_gain_etfs"],
            "semiconductor_dominance": True,
            "v_shape_active": H1_2026_PERFORMANCE["v_shape_pattern"],
            "fund_manager_top3_themes": H1_2026_PERFORMANCE["fund_manager_consensus_themes"][:3],
            "net_inflow_yi": H1_2026_PERFORMANCE["h1_net_inflow"],
            "cycle_signal": "V型反转进行中: 前期抛售→半导体ETF份额逆势增长",
        }

    def adjust_l17_with_kline(self, raw_l17_score: float, sector: str) -> float:
        """用k130行业动量对L17原始分做微调。"""
        sig = self.get_sector_kline_signal(sector)
        bias = sig.get("kline_score_bias", 0.0)
        adjusted = raw_l17_score + bias * 0.3  # scale down: KB prior is gentle guidance
        return round(max(1.0, min(10.0, adjusted)), 1)


if __name__ == "__main__":
    km = KBSectorMomentum()
    print("=== k130 Sector Kline Signal ===")
    for s in ["半导体", "AI/科技", "红利/价值", "消费", "通信"]:
        print(f"  {s}: {km.get_sector_kline_signal(s)}")

    print("\n=== Capital Flow Context ===")
    print(km.get_capital_flow_context())

    print("\n=== Institutional Bias ===")
    print(km.get_institutional_bias())

    print("\n=== Cycle Anchor ===")
    print(km.get_k128_cycle_anchor())
