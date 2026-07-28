#!/usr/bin/env python3
"""
Layer 4: KB Deep Integration — 综合知识层增强推荐引擎

来源:
- k128: 行业周期定位 + V型反转信号
- k191: Regime-dependent factor rotation (6因子×4制度矩阵)
- k196: Regime-aware multi-layer penetration weights
- k130: K线动量状态 (20日涨跌幅统计)
- k131: 资金流向强度 + 机构观点共识度

设计原则:
1. 不替代已有三层融合(KB + Pipeline + News)
2. Layer 4 作为 sector-level boost/penalty 注入最终评分
3. 利用现有 L33 regime factor + Kline trend 数据
4. 输出可直接被 recommend_top_n() / compute_unified_score() 消费
5. L4 评分中心为 5.0，正数=看多，负数=看空
6. **L4微调定位**: 综合调整范围应控制在 ±1.5 以内

L4 评分公式:
  base = 5.0
  regime_adj = (regime_factor_alignment - 5.0) × w_regime        # k191+k196: ±0.4
  flow_adj   = (capital_flow_strength - 5.0) × w_flow            # k131:    ±0.25
  inst_adj   = (institutional_consensus - 5.0) × w_inst          # k131:    ±0.25
  mom_adj    = kline_momentum_adjustment                         # k130:    ±0.5
  v_rev_adj  = V型反转信号 bonus                                 # k128:    +0.3
  cycle_adj  = industry_cycle_bonus                              # k128:    ±0.1
  final      = clip(base + Σ adj, 0, 10)

推荐引擎集成:
  enhanced_final = original_final × (1 - l4_weight) + layer4_score × l4_weight
  where l4_weight ∈ [0.05, 0.15]
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# K128: 行业周期阶段定义 (k128-etf-performance-h1-2026.md)
# ═══════════════════════════════════════════

INDUSTRY_CYCLE_STAGES: Dict[str, str] = {
    # 半导体/科技 — H1 翻倍基主力
    "半导体":       "semiconductor_super_cycle",
    "AI算力":       "ai_infrastructure_buildout",
    "通信":         "optical_communication_bull",
    "硬科技":       "tech_innovation_bull",
    "芯片":         "chip_design_foundry",

    # 防御/稳健 — 宽基+避险资金青睐
    "红利/价值":    "defensive_yield_station",
    "消费":         "consumption_recovery_early",
    "医药":         "healthcare_quality_defense",
    "银行":         "banking_value_repair",
    "保险":         "insurance_stable_quality",

    # 周期/资源 — 通胀对冲
    "能源化工":     "energy_inflation_hedge",
    "贵金属":       "gold_safe_haven",
    "煤炭":         "coal_value_dividend",
    "有色/金属":    "industrial_commodity_cycle",
    "军工":         "defense_momentum_event",
}

# K128: V型反转检测信号
V_TYPE_REVERSAL_SIGNALS: Dict[str, dict] = {
    "半导体": {
        "pattern":       "deep_drawdown_then_strong_recovery",
        "h1_2026_return": "+177% (设备ETF)",
        "mid_year_adjust": "-7.88% (20日)",
        "trigger":       "中报业绩预喜 + AI算力capex上调",
        "confidence":    0.85,
        "reversal_zone": (-15.0, -6.0),
    },
    "AI算力": {
        "pattern":       "concept_to_earnings_translation",
        "h1_2026_return": "翻倍基主力",
        "mid_year_adjust": "-6.79% (20日)",
        "trigger":       "WAIC催化 + 云厂商capex上调",
        "confidence":    0.80,
        "reversal_zone": (-15.0, -6.0),
    },
    "宽基": {
        "pattern":       "steady_inflow_during_selloff",
        "h1_2026_return": "沪深300最大回撤<13%",
        "mid_year_adjust": "净流入1561亿",
        "trigger":       "北向资金+场外资金持续入场",
        "confidence":    0.90,
        "reversal_zone": (-10.0, -3.0),
    },
}

# ═══════════════════════════════════════════
# K131: 资金流向强度 (k131-etf-market-adjustment-analysis-20260719.md)
# ═══════════════════════════════════════════

CAPITAL_FLOW_LABELS: Dict[str, str] = {
    "broad_based_inflow":   "宽基资金净流入 (>3300亿/月, 68%占比)",
    "sector_thematic_inflow": "行业主题净流入 (444亿, 19.4%)",
    "single_day_extreme":   "单日极值流入 (本周五763亿)",
    "institutional_bull":   "机构共识看多 (方正+海通+外资)",
}

# K131: 机构观点映射 — sector → bias/strength/key views
INSTITUTIONAL_BIAS: Dict[str, dict] = {
    "半导体": {
        "bias":     "bullish",
        "strength": 0.75,
        "key_views": [
            "设备高景气周期(AI算力驱动)",
            "存储芯片涨价(DRAM/NAND)",
            "国产化进程加速(长鑫科技IPO)",
            "当前回撤28%接近极限回撤区间(20-40%)",
        ],
    },
    "AI算力": {
        "bias":     "bullish",
        "strength": 0.70,
        "key_views": [
            "AI硬件从主题预期转向订单利润兑现",
            "光通信/存储/半导体设备三大主线",
            "中期聚焦高科技硬科技",
            "全球投资者投资中国AI产业链成共识",
        ],
    },
    "红利/价值": {
        "bias":     "bullish_defensive",
        "strength": 0.85,
        "key_views": [
            "相对抗跌(-2.11% vs 全市场-5%)",
            "宽基资金青睐(上证50ETF华夏+9.78亿净流入)",
            "价值因子在震荡/危机期表现优异",
            "避险资金首选",
        ],
    },
    "消费": {
        "bias":     "neutral_bullish",
        "strength": 0.60,
        "key_views": [
            "跌幅适中(-3.91%)，估值回归合理区间",
            "茅台提价打破惯例，市场化定价落地",
            "内需复苏早期信号",
        ],
    },
    "宽基": {
        "bias":     "bullish_defensive",
        "strength": 0.80,
        "key_views": [
            "7月以来股票ETF净流入超3300亿",
            "13个交易日中12天净流入",
            "宽基本身占68%资金流向",
        ],
    },
}

# ═══════════════════════════════════════════
# K130: K线动量状态 (k130-etf-kline-analysis-20260719.md)
# ═══════════════════════════════════════════

KLINE_MOMENTUM_STATUS: Dict[str, dict] = {
    "strong_uptrend":        {"range": (5.0, float("inf")),   "status": "强势上涨",    "adjustment": +1.0},
    "moderate_uptrend":      {"range": (0.0, 5.0),            "status": "温和上涨",    "adjustment": +0.5},
    "sideways_consolidation":{"range": (-3.0, 0.0),           "status": "横盘整理",    "adjustment":  0.0},
    "weak_downtrend":        {"range": (-6.0, -3.0),          "status": "轻度回调",    "adjustment": -0.5},
    "deep_downtrend":        {"range": (-15.0, -6.0),         "status": "深度回调",    "adjustment": -1.0},
    "crisis_crash":          {"range": (float("-inf"), -15.0),"status": "危机暴跌",    "adjustment": -2.0},
}

# K130: 各行业20日跌幅统计 (2026-07-17 收盘数据)
SECTOR_20D_RETURN_STATS: Dict[str, dict] = {
    "红利/价值":  {"mean": -2.11, "median": -1.72, "best":  -1.18, "worst": -7.09},
    "消费":       {"mean": -3.91, "median": -3.16, "best":  -1.46, "worst": -8.86},
    "新能源":     {"mean": -4.52, "median": -4.49, "best":  -3.91, "worst": -5.19},
    "其他":       {"mean": -4.63, "median": -4.63, "best":   0.00, "worst": -10.75},
    "跨境":       {"mean": -5.37, "median": -6.37, "best":  -1.77, "worst": -7.86},
    "医药":       {"mean": -6.41, "median": -6.52, "best":  -4.67, "worst": -9.78},
    "AI/科技":    {"mean": -6.79, "median": -6.52, "best":  -1.80, "worst": -11.24},
    "半导体":     {"mean": -7.88, "median": -7.89, "best":  -7.28, "worst": -8.52},
    "通信":       {"mean": -8.26, "median": -8.06, "best":  -7.79, "worst": -9.02},
}

# ═══════════════════════════════════════════
# K191 + K196: Regime因子轮动 + 层权重
# ═══════════════════════════════════════════

REGIME_SECTOR_BOOST: Dict[str, Dict[str, float]] = {
    "bull_trend": {
        "半导体":   0.5, "AI算力":   0.5, "军工":     0.4,
        "通信":     0.4, "计算机":   0.3, "电子":     0.3,
        "芯片":     0.5, "低空经济": 0.3, "具身智能": 0.3,
        "传媒":     0.2, "游戏":     0.2, "旅游":     0.2,
        "汽车":     0.2, "新能源车": 0.1, "电池":     0.1,
        "光伏":    -0.2, "风电":    -0.2,
    },
    "bear_crisis": {
        "红利/价值":  0.6, "公用事业": 0.6, "医药":     0.4,
        "银行":       0.4, "保险":     0.3, "贵金属":   0.5,
        "黄金":       0.5, "消费":     0.3, "白酒":     0.2,
        "食品饮料":   0.2, "中药":     0.2, "煤炭":     0.2,
        "电力":       0.2, "半导体":-0.4, "AI算力":-0.4,
        "通信":     -0.4, "计算机":  -0.2, "电子":     -0.2,
        "军工":     -0.2, "低空经济":-0.4, "具身智能":-0.4,
    },
    "sideways": {
        "红利/价值":  0.5, "医药":     0.3, "消费":     0.3,
        "银行":       0.3, "保险":     0.2, "公用事业": 0.4,
        "白酒":       0.2, "食品饮料": 0.2, "煤炭":     0.1,
        "电力":       0.1, "贵金属":   0.3, "半导体":-0.3,
        "AI算力":   -0.3, "通信":    -0.3, "军工":    -0.2,
    },
    "recovery": {
        "银行":       0.5, "红利/价值": 0.3, "消费":     0.4,
        "医药":       0.3, "公用事业": 0.2, "白酒":     0.2,
        "食品饮料":   0.2, "半导体":   0.2, "AI算力":   0.1,
        "通信":       0.1, "房地产":    0.2, "基建":      0.2,
    },
}


# ═══════════════════════════════════════════
# 因子→行业快捷映射 (k191)
# ═══════════════════════════════════════════

FACTOR_TO_SECTOR_CATEGORIES: Dict[str, list] = {
    "Momentum":   ["军工", "半导体", "AI算力", "通信", "游戏", "传媒"],
    "Growth":     ["半导体", "AI算力", "计算机", "电子", "芯片", "低空经济", "具身智能"],
    "Quality":    ["红利/价值", "消费", "医药", "银行", "白酒", "食品饮料", "中药"],
    "LowVol":     ["红利/价值", "公用事业", "银行", "白酒", "食品饮料", "医药", "电力", "煤炭"],
    "Value":      ["红利/价值", "银行", "保险", "煤炭", "钢铁", "公用事业", "食品饮料"],
    "Size(SMB)":  ["中证500", "中证1000", "小盘价值", "创业板", "通信", "游戏", "传媒"],
}


# ═══════════════════════════════════════════
# L4 组件权重 — 中心化为5.0, 总调整控制在±1.2内
# ═══════════════════════════════════════════

L4_WEIGHTS: Dict[str, float] = {
    "regime_alignment":  0.25,    # (score-5) × 0.25 → max ±0.25 (5~10 range)
    "regime_sector":     0.50,    # boost[-0.5,+0.6] × 0.5 → max ±0.30
    "capital_flow":      0.20,    # (score-5) × 0.20 → max ±0.20
    "institutional":     0.15,    # (score-5) × 0.15 → max ±0.15
    "momentum":          0.35,    # adjustment[-2,+1] × 0.35 → max ±0.70 (cap later)
    "v_type_reversal":   0.30,    # binary +0.3
    "cycle_stage":       0.10,    # bonus × 0.1 → small
}


# ═══════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════

def qvix_regime_to_model_regime(qvix_regime: str) -> str:
    """QVIX regime → model regime (k196 mapping)."""
    return {
        "complacent": "bull_trend",
        "normal":     "sideways",
        "cautious":   "sideways",
        "fearful":    "bear_crisis",
    }.get(qvix_regime, "sideways")


def detect_kline_momentum(change_20d: float) -> str:
    """根据20日涨跌幅检测K线动量状态."""
    for status, cfg in KLINE_MOMENTUM_STATUS.items():
        low, high = cfg["range"]
        if low <= change_20d <= high:
            return status
    return "unknown"


def get_momentum_adjustment(momentum_status: str) -> float:
    """获取动量状态对应的评分调整."""
    if momentum_status == "unknown":
        return 0.0
    return KLINE_MOMENTUM_STATUS.get(momentum_status, {}).get("adjustment", 0.0)


def identify_industry_cycle(sector: str) -> str:
    """识别行业周期阶段."""
    return INDUSTRY_CYCLE_STAGES.get(sector, "unknown")


def detect_v_type_reversal(sector: str, change_20d: float) -> bool:
    """检测V型反转信号 (k128)."""
    info = V_TYPE_REVERSAL_SIGNALS.get(sector)
    if not info:
        return False
    zone = info.get("reversal_zone", (-15.0, -6.0))
    return zone[0] < change_20d < zone[1]


def sector_contains_keywords(sector: str, keywords: list) -> bool:
    """检查sector字符串是否包含任何关键词."""
    return any(kw in sector for kw in keywords)


# ═══════════════════════════════════════════
# 主计算类
# ═══════════════════════════════════════════

class KBDeepLayer:
    """Layer 4: KB深度知识层集成器 (k128+k130+k131+k191+k196).

    定位: L4是微调层，给final_score贡献幅度控制在 ±1.0 左右。
    """

    def __init__(self):
        self.layer_name = "L4_KB_Deep"

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def compute_l4_score(
        self,
        etf_code: str,
        sector: str,
        pipe_result: Optional[dict] = None,
        trend_data: Optional[dict] = None,
        qvix_regime: str = "normal",
        kb_signals: Optional[dict] = None,
        news_sentiment: Optional[dict] = None,
    ) -> dict:
        """
        计算Layer 4综合评分 (0-10, center=5.0).

        Args:
            etf_code: ETF代码
            sector:   行业分类
            pipe_result: pipeline穿透结果 (可选)
            trend_data:  {change_20d, volatility_20d} (可选)
            qvix_regime: QVIX制度状态
            kb_signals: KB信号 (unused by L4 directly)
            news_sentiment: 新闻情绪 (unused by L4 directly)

        Returns:
            dict with score (0-10), all component breakdowns.
        """
        model_regime = qvix_regime_to_model_regime(qvix_regime)

        change_20d = 0.0
        if trend_data:
            change_20d = trend_data.get("change_20d", 0.0)

        # --- 7个组件 ---
        regime_align_raw = self._compute_regime_alignment(sector, model_regime)
        regime_sector = self._compute_regime_sector_boost(sector, model_regime)
        cap_flow = self._compute_capital_flow_strength(sector)
        inst_cons = self._compute_institutional_consensus(sector)
        mom_status = detect_kline_momentum(change_20d)
        mom_adj = get_momentum_adjustment(mom_status)
        v_rev = detect_v_type_reversal(sector, change_20d)
        cycle_stage = identify_industry_cycle(sector)
        cycle_bonus = self._cycle_stage_bonus(cycle_stage, sector, change_20d)

        # --- 加权合成, 中心化为5.0 ---
        w = L4_WEIGHTS

        regime_align_adj = round((regime_align_raw - 5.0) * w["regime_alignment"], 2)
        regime_sector_adj = round(regime_sector * w["regime_sector"], 2)
        cap_flow_adj = round((cap_flow - 5.0) * w["capital_flow"], 2)
        inst_adj = round((inst_cons - 5.0) * w["institutional"], 2)
        # Momentum: cap raw adjustment before weighting
        mom_capped = max(-1.0, min(1.0, mom_adj))
        mom_weighted = round(mom_capped * w["momentum"], 2)
        v_rev_adj = round(w["v_type_reversal"] if v_rev else 0.0, 2)
        cycle_adj = round(cycle_bonus * w["cycle_stage"], 2)

        total_adj = (
            regime_align_adj + regime_sector_adj + cap_flow_adj +
            inst_adj + mom_weighted + v_rev_adj + cycle_adj
        )
        final_score = round(max(0.0, min(10.0, 5.0 + total_adj)), 1)

        return {
            "layer_key":              self.layer_name,
            "score":                  final_score,
            "regime":                 model_regime,
            "qvix_regime_input":      qvix_regime,
            "components":             {
                "regime_alignment_raw":   round(regime_align_raw, 1),
                "regime_alignment_adj":   regime_align_adj,
                "regime_sector_boost":    round(regime_sector, 2),
                "regime_sector_adj":      regime_sector_adj,
                "capital_flow_raw":       round(cap_flow, 1),
                "capital_flow_adj":       cap_flow_adj,
                "institutional_raw":      round(inst_cons, 1),
                "institutional_adj":      inst_adj,
                "momentum_status":        mom_status,
                "momentum_adj":           mom_adj,
                "momentum_weighted":      mom_weighted,
                "v_type_reversal":        v_rev,
                "v_type_reversal_adj":    v_rev_adj,
                "industry_cycle_stage":   cycle_stage,
                "cycle_bonus":            round(cycle_bonus, 2),
                "cycle_adj":              cycle_adj,
            },
            "total_kb_adjustment": round(total_adj, 2),
            "etf_code":               etf_code,
            "sector":                 sector,
            "kb_source":              "k128+k130+k131+k191+k196",
        }

    # ------------------------------------------------------------------
    # private helpers
    # ------------------------------------------------------------------

    def _compute_regime_alignment(self, sector: str, regime: str) -> float:
        """
        k191: 计算sector在当前regime下的因子对齐分数(0-10).

        策略: 优先使用现有L33的因子暴露矩阵; fallback到硬编码
        regime_sector_boost 表.
        """
        try:
            from etf_platform.layers.l33_regime_factor import RegimeFactorLayer
            layer = RegimeFactorLayer()
            return round(float(layer.factor_alignment_score(sector, regime)), 1)
        except ImportError:
            pass
        except Exception:
            logger.debug(f"L33 regime alignment failed for {sector}/{regime}")

        # Fallback: derive from REGIME_SECTOR_BOOST table
        boosts = REGIME_SECTOR_BOOST.get(regime, {})
        boost = boosts.get(sector, 0.0)
        # Map [-0.6, +0.6] boost → [3.5, 7.5] centered at 5.0
        return round(max(1.0, min(10.0, 5.0 + boost * 5.0)), 1)

    def _compute_regime_sector_boost(self, sector: str, regime: str) -> float:
        """k196: regime特定行业bonus, 范围约 [-0.5, +0.6]."""
        boosts = REGIME_SECTOR_BOOST.get(regime, {})
        return round(boosts.get(sector, 0.0), 2)

    def _compute_capital_flow_strength(self, sector: str) -> float:
        """
        k131: 资金流向强度评分 (0-10).

        规则:
        - 宽基ETF: 8.0 (68%资金流入)
        - 红利/价值/贵金属: 7.5 (避险资金首选)
        - 消费/医药/金融: 7.0
        - 半导体/AI: 6.5 (行业主题+强机构看多)
        - 新能源/光伏: 5.5
        """
        broad_keywords = ["宽基", "沪深300", "中证500", "科创50", "科创100", "上证50", "中证1000"]
        if sector_contains_keywords(sector, broad_keywords):
            return 8.0

        if sector in ("红利/价值", "贵金属", "黄金"):
            return 7.5
        if sector in ("消费", "医药", "中药", "银行", "保险", "金融"):
            return 7.0
        if sector in ("半导体", "AI算力", "AI/科技", "通信", "芯片", "硬科技"):
            return 6.5
        if sector in ("能源化工", "煤炭", "钢铁", "军工"):
            return 6.5
        if sector in ("新能源", "光伏", "风电"):
            return 5.5
        return 5.0

    def _compute_institutional_consensus(self, sector: str) -> float:
        """
        k131: 机构观点共识度 (0-10).

        基于方正/海通/央视等机构公开观点.
        strength 0.0~1.0 → score 5.0~10.0
        """
        info = INSTITUTIONAL_BIAS.get(sector)
        if not info:
            return 5.0
        strength = info.get("strength", 0.5)
        return round(5.0 + strength * 5.0, 1)

    def _cycle_stage_bonus(self, cycle_stage: str, sector: str, change_20d: float) -> float:
        """k128: 行业周期阶段催化奖励, 范围约 [-0.5, +1.0]."""
        if cycle_stage == "semiconductor_super_cycle":
            return 0.0 if change_20d < -7.0 else 1.0
        if cycle_stage == "ai_infrastructure_buildout":
            return 0.5 if change_20d < -5.0 else 0.8
        if cycle_stage in ("defensive_yield_station", "gold_safe_haven"):
            return 0.3
        if cycle_stage == "consumption_recovery_early":
            return 0.2
        if cycle_stage == "banking_value_repair":
            return 0.3
        return 0.0


# ═══════════════════════════════════════════
# 便捷函数
# ═══════════════════════════════════════════

RECOMMENDATION_LABELS = {
    "strong_buy": "强烈买入",
    "buy": "买入",
    "accumulate": "逢低布局",
    "hold": "持有",
    "reduce": "减仓",
    "wait": "观望",
}


def classify_recommendation(enhanced: float, layer4: float, boost: float) -> str:
    """基于增强分数和L4方向生成投资建议."""
    if enhanced >= 7.0 and layer4 >= 6.0:
        return "strong_buy"
    if enhanced >= 6.5 and boost > 0:
        return "buy"
    if enhanced >= 6.0 and layer4 >= 5.5:
        return "accumulate"
    if enhanced >= 5.0:
        return "hold"
    if enhanced >= 4.5:
        return "reduce"
    return "wait"


def calculate_enhanced_recommendation(
    etf_code: str,
    sector: str,
    pipe_result: Optional[dict] = None,
    trend_data: Optional[dict] = None,
    qvix_regime: str = "normal",
    kb_signals: Optional[dict] = None,
    news_sentiment: Optional[dict] = None,
    current_score: float = 5.0,
    layer4_weight: float = 0.10,
) -> dict:
    """
    计算增强推荐分数 — Layer 4 注入.

    综合公式:
      enhanced = current_score × (1 - weight) + layer4_final × weight

    Args:
        etf_code:       ETF代码
        sector:         行业分类
        pipe_result:    pipeline穿透结果 (可选)
        trend_data:     {change_20d, ...} K线趋势 (可选)
        qvix_regime:    QVIX制度 (complacent/normal/cautious/fearful)
        kb_signals:     KB信号数据 (可选)
        news_sentiment: 新闻情绪 (可选)
        current_score:  当前三层融合综合分 (0-10)
        layer4_weight:  Layer 4权重 (默认10%, 可配0.05~0.15)

    Returns:
        {
            "code", "sector",
            "original_score": 原始综合分,
            "layer4_score": L4独立评分,
            "layer4_boost":  L4相对原分的调整,
            "enhanced_score": 融合后分数,
            "recommendation": "strong_buy|buy|accumulate|hold|reduce|wait",
            "kb_deep_components": {...},
            "source_layers": "k128+k130+k131+k191+k196",
        }
    """
    layer = KBDeepLayer()
    l4_result = layer.compute_l4_score(
        etf_code=etf_code,
        sector=sector,
        pipe_result=pipe_result,
        trend_data=trend_data,
        qvix_regime=qvix_regime,
        kb_signals=kb_signals,
        news_sentiment=news_sentiment,
    )

    original = float(current_score)
    layer4 = float(l4_result["score"])
    weighted = round(original * (1.0 - layer4_weight) + layer4 * layer4_weight, 2)
    boost = round(layer4 - original, 2)
    recommendation = classify_recommendation(weighted, layer4, boost)

    comp = l4_result["components"]
    total_adj = (
        comp["regime_alignment_adj"] + comp["regime_sector_adj"]
        + comp["capital_flow_adj"] + comp["institutional_adj"]
        + comp["momentum_weighted"] + comp["v_type_reversal_adj"]
        + comp["cycle_adj"]
    )

    return {
        "code": etf_code,
        "sector": sector,
        "original_score": original,
        "layer4_score": layer4,
        "layer4_boost": boost,
        "enhanced_score": weighted,
        "layer4_weight_used": layer4_weight,
        "recommendation": recommendation,
        "recommendation_cn": RECOMMENDATION_LABELS.get(recommendation, recommendation),
        "kb_deep_components": {
            "regime":               l4_result["regime"],
            "regime_alignment":     comp["regime_alignment_raw"],
            "regime_alignment_adj": comp["regime_alignment_adj"],
            "regime_sector":        comp["regime_sector_boost"],
            "regime_sector_adj":    comp["regime_sector_adj"],
            "capital_flow_strength":comp["capital_flow_raw"],
            "capital_flow_adj":     comp["capital_flow_adj"],
            "institutional_consensus": comp["institutional_raw"],
            "institutional_adj":    comp["institutional_adj"],
            "momentum_status":      comp["momentum_status"],
            "momentum_adj":         comp["momentum_adj"],
            "momentum_weighted":    comp["momentum_weighted"],
            "v_type_reversal":      comp["v_type_reversal"],
            "v_type_reversal_adj":  comp["v_type_reversal_adj"],
            "industry_cycle":       comp["industry_cycle_stage"],
            "cycle_bonus":          comp["cycle_bonus"],
            "cycle_adj":            comp["cycle_adj"],
            "total_kb_adjustment":  round(total_adj, 2),
        },
        "source_layers": "k128+k130+k131+k191+k196",
    }


def integrate_into_unified_score(
    existing: dict,
    etf_code: str,
    sector: str,
    qvix_regime: str = "normal",
    trend_data: Optional[dict] = None,
    layer4_weight: float = 0.10,
) -> dict:
    """
    将Layer 4整合进现有 compute_unified_score() 输出.

    Usage:
        result = compute_unified_score(...)
        result = integrate_into_unified_score(
            result, etf_code, sector,
            qvix_regime="fearful",
            trend_data={"change_20d": -7.88},
            layer4_weight=0.10,
        )

    不破坏现有schema, 在result dict上追加 layer4_kb_deep key.
    """
    enhanced = calculate_enhanced_recommendation(
        etf_code=etf_code,
        sector=sector,
        trend_data=trend_data,
        qvix_regime=qvix_regime,
        current_score=existing.get("final_score", 5.0),
        layer4_weight=layer4_weight,
    )

    existing["layer4_kb_deep"] = {
        "enabled": True,
        "weight": layer4_weight,
        "score": enhanced["layer4_score"],
        "boost": enhanced["layer4_boost"],
        "enhanced_score": enhanced["enhanced_score"],
        "recommendation": enhanced["recommendation"],
        "components": enhanced["kb_deep_components"],
    }
    existing["final_score"] = enhanced["enhanced_score"]
    existing["risk_adjusted_score"] = enhanced["enhanced_score"]
    return existing


# ═══════════════════════════════════════════
# CLI test
# ═══════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 70)
    print("Layer 4: KB Deep Enhancement Test (Calibrated)")
    print("=" * 70)

    test_cases = [
        ("512480", "半导体",    -7.88, "fearful",   6.5),
        ("512480", "半导体",    -7.88, "complacent",6.5),
        ("515880", "红利/价值", -2.11, "fearful",   7.0),
        ("510300", "沪深300",   -2.0,  "fearful",   7.5),
        ("159928", "消费",      -3.91, "fearful",   6.0),
        ("512880", "银行",      -1.5,  "fearful",   7.0),
        ("512660", "军工",      -4.0,  "complacent",6.5),
        ("159915", "科技ETF",   -6.8,  "fearful",   5.5),
    ]

    for code, sector, change_20d, regime, current in test_cases:
        r = calculate_enhanced_recommendation(
            etf_code=code,
            sector=sector,
            trend_data={"change_20d": change_20d},
            qvix_regime=regime,
            current_score=current,
            layer4_weight=0.10,
        )
        c = r["kb_deep_components"]
        print(f"\n{r['code']} | {sector:10s} | 20d={change_20d:+6.2f}% | regime={regime}")
        print(f"  Original={r['original_score']:.1f} → L4={r['layer4_score']:.1f} | Boost={r['layer4_boost']:+.2f}")
        print(f"  Enhanced={r['enhanced_score']:.2f} | Rec={r['recommendation_cn']}")
        print(f"  Regime={c['regime']} | Align={c['regime_alignment']} | Sector={c['regime_sector']:+.2f}")
        print(f"  Flow={c['capital_flow_strength']} | Inst={c['institutional_consensus']} | Mom={c['momentum_status']}")
        print(f"  VRev={c['v_type_reversal']} | Cycle={c['industry_cycle']} | TotalAdj={c['total_kb_adjustment']:+.2f}")