"""
l15_state_similarity.py — 市场状态相似度因子 (v6.0)

Key changes from v5.0:
- Fixed: regime_certainty was producing too-narrow distribution (many sectors at 4.6-4.9)
- Added sector-specific regime_certainty variance using dot-product variance
- Added "market_state_alignment" bonus for sectors that benefit from current regime
- Zero-overlap sectors now get differentiated scores based on characteristic vectors
- Expected: 12+ unique values, spread 5.0+, <25% neutral zone

The key insight: v5.0's concentration metric was too narrow because all sectors
had similar dot-product alignments with the top 3 market states. v6.0 adds
variance-based differentiation and characteristic-vector scoring.
"""
from typing import Dict, List, Optional
from datetime import datetime
import math

# ═══════════════════════════════════════════
# 典型市场状态库
# ═══════════════════════════════════════════

MARKET_STATES = [
    {
        "name": "牛市加速",
        "period": "2014-2015",
        "features": [0.35, 0.85, 0.70, 0.90, 0.85],
        "description": "高波动+强动量+高相关+巨量+宽幅上涨",
        "sectors_benefit": [
            "AI/科技", "互联网", "券商", "创业板",
            "半导体", "半导体设备", "AI算力", "云计算/算力", "数字经济",
            "通信/光模块", "5G/PCB", "机器人/智造",
            "科技", "硬科技", "中盘成长", "成长股",
            "美股科技", "美股科技100", "纳斯达克",
        ],
        "strategy": "进攻型配置, 高Beta优先, 注意泡沫风险",
    },
    {
        "name": "慢牛结构",
        "period": "2019-2020",
        "features": [0.25, 0.60, 0.45, 0.60, 0.65],
        "description": "中低波动+稳定上涨+低相关(结构分化)+温和放量",
        "sectors_benefit": [
            "AI/科技", "消费", "医药", "新能源",
            "白酒消费", "食品饮料", "家电", "医药器械",
            "医疗", "创新药", "中药",
            "新能源汽车", "光伏", "风电", "储能", "锂电", "电池",
            "港股科技", "美股科技",
        ],
        "strategy": "精选赛道, 龙头溢价, 趋势跟踪",
    },
    {
        "name": "震荡牛皮",
        "period": "2016-2017",
        "features": [0.15, 0.10, 0.30, 0.40, 0.50],
        "description": "低波动+横向+低相关+缩量+涨跌各半",
        "sectors_benefit": [
            "红利/价值", "消费", "银行", "保险",
            "高股息", "红利+低波", "红利价值", "红利低波",
            "大盘蓝筹", "小盘价值", "价值",
            "公用事业", "水电", "煤炭",
            "债券", "利率债", "信用债", "可转债",
            "全市场", "宽基", "沪深300", "上证50",
        ],
        "strategy": "高股息+低波动防守, 波段操作, 降低仓位",
    },
    {
        "name": "恐慌下跌",
        "period": "2015Q3, 2018Q4, 2022Q1",
        "features": [0.50, -0.70, 0.85, 0.30, 0.15],
        "description": "高波动+急跌+高相关(普跌)+缩量(流动性枯竭)+极窄上涨",
        "sectors_benefit": [
            "黄金", "贵金属", "债券", "货币基金", "货币",
            "利率债", "信用债", "高股息", "红利+低波",
            "公用事业", "消费", "食品饮料",
        ],
        "strategy": "现金为王/黄金避险, 等待恐慌指数见顶, 分步抄底宽基",
    },
    {
        "name": "V型反转",
        "period": "2020Q1-Q2",
        "features": [0.60, 0.50, 0.60, 0.80, 0.60],
        "description": "极高波动+急跌后急涨+高相关+巨量+宽幅震荡",
        "sectors_benefit": [
            "半导体", "半导体设备", "新能源", "新能源车",
            "光伏", "电池", "锂电", "储能", "风电",
            "创业板", "科创", "科创板", "中盘成长", "成长股",
            "AI/科技", "AI算力", "硬科技", "计算机",
            "券商", "金融", "银行",
        ],
        "strategy": "左侧定投+右侧加仓, 回补仓位, 避免踏空",
    },
    {
        "name": "流动性宽松",
        "period": "2020H2",
        "features": [0.20, 0.40, 0.40, 0.65, 0.60],
        "description": "低波动+温和上涨+中相关+放量+均衡",
        "sectors_benefit": [
            "AI/科技", "消费", "医药", "宽基",
            "全市场", "沪深300", "中证500", "创业板",
            "白酒", "食品饮料", "家电", "汽车",
            "港股", "港股综合", "港股医药", "港股科技",
            "中概互联网", "跨境", "美股科技", "美股综合",
        ],
        "strategy": "核心+卫星配置, DCA定投, 适当加杠杆",
    },
    {
        "name": "政策底/市场底",
        "period": "2018Q4, 2022Q4, 2024Q1",
        "features": [0.30, -0.20, 0.50, 0.35, 0.35],
        "description": "波动放大+继续探底+中相关+地量+少数上涨",
        "sectors_benefit": [
            "宽基", "全市场", "沪深300", "上证50", "中证A500",
            "金融", "银行", "券商", "保险",
            "红利/价值", "高股息", "红利+低波", "红利价值",
            "基建", "基建/地产", "房地产",
            "央企改革", "国企", "大盘蓝筹",
        ],
        "strategy": "左侧分批建仓, 优先宽基ETF, 避免追题材",
    },
    {
        "name": "估值回归(红利)",
        "period": "2023-2024",
        "features": [0.15, 0.20, 0.25, 0.45, 0.45],
        "description": "低波动+慢涨+低相关(分化为红利/成长)+缩量+窄幅",
        "sectors_benefit": [
            "红利/价值", "红利低波", "公用事业", "煤炭",
            "高股息", "红利+低波", "红利价值",
            "银行", "保险", "金融",
            "债券", "利率债", "信用债",
            "消费", "食品饮料", "家电",
        ],
        "strategy": "高股息核心仓位, 国债+红利哑铃策略",
    },
]


# ═══════════════════════════════════════════
# 当前市场特征估计
# ═══════════════════════════════════════════

CURRENT_FEATURES = [0.18, 0.15, 0.35, 0.40, 0.45]  # 波动率, 动量, 相关, 量, 宽度


# ═══════════════════════════════════════════
# v6.0: 行业特征向量 — 大幅扩展覆盖
# ═══════════════════════════════════════════

SECTOR_CHARACTERISTICS = {
    # === 高可控 (8-9.5): 确定性高, 研究能充分覆盖 ===
    "货币基金": [0.1, 0.9, 0.1, 0.0, 0.9],      # 低风险+稳定+防御
    "利率债": [0.1, 0.8, 0.1, 0.0, 0.9],        # 低风险+稳定+避险
    "国债": [0.1, 0.8, 0.1, 0.0, 0.9],          # 同上
    "债券": [0.1, 0.7, 0.1, 0.0, 0.8],          # 低风险+稳定
    "信用债": [0.2, 0.6, 0.2, 0.1, 0.7],        # 略有风险
    "红利低波": [0.1, 0.8, 0.1, 0.0, 0.9],      # 防御+稳定
    "红利/价值": [0.1, 0.8, 0.1, 0.0, 0.9],     # 防御+稳定
    "自由现金流": [0.1, 0.8, 0.1, 0.0, 0.8],    # 高质量+稳定
    "高股息": [0.1, 0.8, 0.1, 0.0, 0.9],        # 防御+稳定
    "红利价值": [0.1, 0.8, 0.1, 0.0, 0.9],      # 防御+稳定
    "红利+低波": [0.1, 0.8, 0.1, 0.0, 0.9],     # 防御+稳定
    "公用事业": [0.2, 0.5, 0.3, 0.1, 0.8],      # 价值+防御+政策
    "宽基": [0.3, 0.3, 0.2, 0.3, 0.4],          # 中性+分散
    "沪深300": [0.3, 0.3, 0.2, 0.3, 0.4],       # 大盘+分散
    "上证50": [0.3, 0.3, 0.2, 0.3, 0.4],        # 大盘蓝筹
    "黄金": [0.1, 0.2, 0.1, 0.0, 0.9],          # 避险+低相关
    "消费": [0.3, 0.5, 0.3, 0.3, 0.5],          # 内需+稳定
    "食品饮料": [0.3, 0.5, 0.3, 0.3, 0.5],      # 刚需+稳定
    "白酒": [0.3, 0.5, 0.4, 0.3, 0.5],          # 消费+品牌溢价
    "白酒消费": [0.3, 0.5, 0.4, 0.3, 0.5],      # 同上
    "家电": [0.3, 0.5, 0.4, 0.4, 0.5],          # 消费+政策+中等波动
    "银行": [0.1, 0.7, 0.5, 0.4, 0.5],          # 价值+政策
    "保险": [0.1, 0.6, 0.4, 0.3, 0.6],          # 价值+防御
    "金融": [0.1, 0.7, 0.5, 0.4, 0.5],          # 价值+政策
    "基建": [0.2, 0.5, 0.4, 0.3, 0.6],          # 政策+中等波动
    "基建/地产": [0.3, 0.2, 0.3, 0.3, 0.2],     # 政策驱动+周期
    "红利": [0.1, 0.8, 0.1, 0.0, 0.9],          # 防御+稳定
    "价值": [0.1, 0.7, 0.2, 0.1, 0.8],          # 价值+稳定

    # === 中可控 (5.5-7.0): 有一定不确定性 ===
    "医药": [0.4, 0.4, 0.5, 0.4, 0.5],          # 成长+政策
    "医疗": [0.4, 0.4, 0.5, 0.4, 0.5],          # 同上
    "医疗器械": [0.4, 0.4, 0.5, 0.4, 0.5],      # 同上
    "医药器械": [0.4, 0.4, 0.5, 0.4, 0.5],      # 同上
    "中药": [0.3, 0.5, 0.4, 0.3, 0.6],          # 消费+政策
    "创新药": [0.6, 0.3, 0.5, 0.5, 0.3],        # 高成长+高风险
    "军工": [0.3, 0.1, 0.9, 0.6, 0.2],          # 政策驱动+高波动
    "汽车": [0.4, 0.4, 0.5, 0.4, 0.5],          # 消费+政策
    "中证500": [0.3, 0.3, 0.3, 0.3, 0.4],       # 中盘+分散
    "中证1000": [0.4, 0.2, 0.4, 0.4, 0.3],      # 小盘+波动
    "国证2000": [0.5, 0.2, 0.4, 0.5, 0.2],      # 小微盘+高波动
    "创业板": [0.6, 0.2, 0.3, 0.6, 0.1],        # 成长+高波动
    "房地产": [0.3, 0.2, 0.3, 0.3, 0.2],        # 周期+政策
    "新能源": [0.5, 0.3, 0.5, 0.5, 0.3],        # 成长+政策+周期
    "新能源车": [0.6, 0.3, 0.5, 0.5, 0.3],      # 同上
    "光伏": [0.5, 0.3, 0.5, 0.5, 0.3],          # 周期+政策
    "风电": [0.5, 0.3, 0.5, 0.5, 0.3],          # 同上
    "储能": [0.5, 0.3, 0.5, 0.5, 0.3],          # 同上
    "锂电": [0.5, 0.3, 0.5, 0.5, 0.3],          # 同上
    "电池": [0.5, 0.3, 0.5, 0.5, 0.3],          # 同上
    "有色金属": [0.4, 0.3, 0.5, 0.5, 0.3],      # 周期+政策
    "煤炭": [0.3, 0.4, 0.5, 0.4, 0.4],          # 周期+政策
    "化工": [0.4, 0.3, 0.5, 0.5, 0.3],          # 周期
    "周期/资源": [0.3, 0.4, 0.5, 0.5, 0.3],     # 周期
    "能源化工": [0.4, 0.3, 0.5, 0.5, 0.3],      # 周期+政策
    "农产品": [0.2, 0.4, 0.5, 0.3, 0.6],        # 防御+政策
    "跨境": [0.4, 0.3, 0.4, 0.5, 0.3],          # 跨市场+政策
    "港股": [0.4, 0.3, 0.4, 0.5, 0.3],          # 港股特征
    "港股综合": [0.3, 0.3, 0.4, 0.5, 0.3],      # 港股特征
    "港股医药": [0.4, 0.4, 0.5, 0.5, 0.3],      # 港股+医药
    "港股科技": [0.5, 0.4, 0.5, 0.6, 0.2],      # 港股+科技
    "中概互联网": [0.5, 0.3, 0.5, 0.5, 0.3],    # 中概+互联网
    "美股科技": [0.4, 0.4, 0.4, 0.5, 0.3],      # 美股+科技
    "美股科技100": [0.4, 0.4, 0.4, 0.5, 0.3],   # 同上
    "美股综合": [0.3, 0.3, 0.3, 0.3, 0.3],      # 美股分散
    "美股杠杆": [0.8, 0.8, 0.7, 0.8, 0.8],      # 极高波动
    "传媒": [0.4, 0.3, 0.5, 0.4, 0.4],          # 政策+消费
    "游戏": [0.4, 0.3, 0.5, 0.4, 0.4],          # 政策+消费
    "旅游": [0.3, 0.4, 0.4, 0.3, 0.5],          # 消费+政策
    "教育": [0.5, 0.3, 0.3, 0.4, 0.3],          # 政策驱动
    "可转债": [0.3, 0.4, 0.3, 0.3, 0.5],        # 混合
    "全市场": [0.3, 0.3, 0.2, 0.3, 0.4],        # 中性
    "大盘蓝筹": [0.2, 0.6, 0.3, 0.3, 0.6],      # 价值+防御
    "中盘成长": [0.6, 0.2, 0.3, 0.5, 0.2],      # 成长+波动
    "成长股": [0.7, 0.1, 0.3, 0.6, 0.1],        # 强成长+高波动
    "小盘价值": [0.1, 0.8, 0.2, 0.4, 0.5],      # 价值+中等波动
    "央企改革": [0.2, 0.2, 0.2, 0.2, 0.2],      # 政策驱动
    "综合": [0.3, 0.3, 0.2, 0.3, 0.4],          # 中性

    # === 低可控 (<4.5): 高不确定性, 技术/政策变化快 ===
    "AI/科技": [0.7, 0.3, 0.6, 0.7, 0.1],       # 高成长+高波动+政策
    "AI算力": [0.7, 0.3, 0.6, 0.7, 0.1],        # 同上
    "半导体": [0.7, 0.3, 0.6, 0.7, 0.1],        # 高成长+高波动+制裁
    "芯片": [0.7, 0.3, 0.6, 0.7, 0.1],          # 同上
    "硬科技": [0.7, 0.3, 0.6, 0.7, 0.1],        # 同上
    "互联网": [0.6, 0.3, 0.5, 0.6, 0.1],        # 高成长+政策
    "云计算/算力": [0.7, 0.3, 0.6, 0.7, 0.1],    # 同上
    "数字经济": [0.6, 0.3, 0.5, 0.6, 0.1],      # 同上
    "通信/5G": [0.6, 0.5, 0.5, 0.6, 0.5],       # 中等波动+政策
    "通信/光模块": [0.7, 0.7, 0.6, 0.7, 0.6],    # 高成长+高波动
    "5G/PCB": [0.6, 0.6, 0.5, 0.6, 0.5],        # 中等波动
    "半导体设备": [0.7, 0.3, 0.6, 0.7, 0.1],    # 高成长+制裁
    "机器人/智造": [0.6, 0.6, 0.5, 0.6, 0.5],   # 中等成长+波动
    "其他": [0.0, 0.0, 0.0, 0.0, 0.0],          # 未知
    "default": [0.0, 0.0, 0.0, 0.0, 0.0],        # 默认
}


def euclidean_distance(a: List[float], b: List[float]) -> float:
    """欧氏距离。"""
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def find_similar_states(features: List[float] = None, top_n: int = 3) -> List[Dict]:
    """找到与给定特征最匹配的历史市场状态。"""
    if features is None:
        features = CURRENT_FEATURES

    scored = []
    for state in MARKET_STATES:
        dist = euclidean_distance(features, state["features"])
        prox = round(1.0 / (1.0 + dist * dist), 3)
        scored.append({**state, "distance": round(dist, 3), "proximity": prox})

    scored.sort(key=lambda x: x["distance"])
    return scored[:top_n]


def _sector_regime_certainty(sector: str, matches: List[Dict]) -> float:
    """v6.0: Variance-based certainty with sector-characteristic weighting.

    v5.0 problem: concentration metric was too narrow (most values 0.6-0.8)
    because all sectors had similar dot-product alignments.

    v6.0 fix: Add sector-characteristic variance as a differentiator.
    - Sectors whose characteristics strongly align with current market → higher certainty
    - Sectors with mixed/contradictory characteristics → lower certainty
    - Uses variance of dot-products across market states
    """
    sector_chars = SECTOR_CHARACTERISTICS.get(sector, SECTOR_CHARACTERISTICS["default"])
    if not matches:
        return 0.5

    # Compute dot-product alignment with each market state
    alignments = []
    for state in matches:
        state_features = state["features"]
        alignment = sum(sc * sf for sc, sf in zip(sector_chars, state_features))
        dist = state["distance"]
        alignments.append(alignment / (1.0 + dist))

    if len(alignments) < 2:
        return 0.5

    # v6.0: Use variance-based differentiation
    max_score = max(alignments)
    min_score = min(alignments)
    mean_score = sum(alignments) / len(alignments)
    variance = sum((a - mean_score) ** 2 for a in alignments) / len(alignments)

    # Concentration (0-1): how dominant the best match is
    total_score = sum(abs(s) for s in alignments)
    if total_score == 0:
        concentration = 0.5
    else:
        concentration = max_score / total_score

    # v6.0: Combined score = weighted average of concentration + variance signal
    # Variance signal: high variance = sector is clearly better in some states than others
    var_norm = min(1.0, variance / 0.1)
    
    # Final certainty: 60% concentration + 40% variance signal
    certainty = 0.6 * concentration + 0.4 * var_norm
    return round(max(0.2, min(1.0, certainty)), 3)


def score_state_similarity(sector: str) -> Dict:
    """返回市场状态相似度因子对给定行业的评分 (0-10).

    v6.0: Major rewrite for wider differentiation.
    - regime_certainty now uses variance-based method
    - Added characteristic_vector_score: how well sector's own characteristics
      align with current market state (CURRENT_FEATURES)
    - Zero-overlap sectors get scores based on characteristic alignment
    """
    scored_states = []
    for state in MARKET_STATES:
        dist = euclidean_distance(CURRENT_FEATURES, state["features"])
        prox = round(1.0 / (1.0 + dist * dist), 3)
        scored_states.append({**state, "distance": round(dist, 3), "proximity": prox})

    scored_states.sort(key=lambda x: x["distance"])
    matches = scored_states[:3]
    best_match = matches[0] if matches else None

    result = {
        "top_match": best_match,
        "all_matches": matches,
        "score": 5.0,
        "deja_vu_factor": 0.0,
    }

    if not matches:
        return result

    # v6.0: Sector-aware regime certainty
    regime_certainty = _sector_regime_certainty(sector, matches)
    result["regime_certainty"] = regime_certainty

    # v6.0: Characteristic vector score — how well does THIS sector's behavior
    # match the CURRENT market state?
    sector_chars = SECTOR_CHARACTERISTICS.get(sector, SECTOR_CHARACTERISTICS["default"])
    char_alignment = sum(sc * sf for sc, sf in zip(sector_chars, CURRENT_FEATURES))
    # Normalize to [0, 10] range
    # char_alignment ranges roughly from -2 to +2
    # v6.1: Increased multiplier from 1.5 to 2.5 for wider spread
    char_score = 5.0 + char_alignment * 2.5
    char_score = max(1.5, min(9.0, char_score))
    result["characteristic_alignment"] = round(char_alignment, 3)
    result["characteristic_score"] = round(char_score, 1)

    total_weighted_score = 0.0
    total_weight = 0.0
    n_benefiting_states = 0
    best_benefit_name = None
    best_benefit_prox = 0.0

    for state in scored_states:
        prox = state["proximity"]
        w = prox * prox

        benefit_keywords = state.get("sectors_benefit", [])
        if not benefit_keywords:
            continue

        max_overlap = 0.0
        for bk in benefit_keywords:
            if bk in sector or sector in bk:
                max_overlap = max(max_overlap, 1.0)
            else:
                sector_chars_set = set(sector)
                bk_chars_set = set(bk)
                if sector_chars_set and bk_chars_set:
                    intersection = len(sector_chars_set & bk_chars_set)
                    union = len(sector_chars_set | bk_chars_set)
                    if intersection > 0 and union > 0:
                        partial = intersection / union
                        max_overlap = max(max_overlap, partial * 0.7)

        contribution = w * prox * max_overlap
        total_weighted_score += contribution
        total_weight += w

        if max_overlap > 0:
            n_benefiting_states += 1
            if prox > best_benefit_prox:
                best_benefit_prox = prox
                best_benefit_name = state["name"]

    if total_weight > 0:
        normalized_score = total_weighted_score / total_weight if total_weight > 0 else 0.0
        if normalized_score > 0:
            # v6.0: Blend keyword overlap score with characteristic vector score
            keyword_score = 3.5 + normalized_score * 5.5
            # Weight: 70% keyword overlap + 30% characteristic alignment
            score = keyword_score * 0.7 + char_score * 0.3
            result["score"] = score
            result["sector_benefits"] = normalized_score > 0.3
            result["normalized_overlap"] = round(normalized_score, 3)
            result["deja_vu_factor"] = round(normalized_score, 3)
            result["signal_strength"] = "strong" if normalized_score > 0.5 else ("moderate" if normalized_score > 0.2 else "weak")
        else:
            # v6.2: Use char_score and char_variance for differentiation even in negative-overlap path
            regime_score = 3.5 + regime_certainty * 3.0
            sector_chars = SECTOR_CHARACTERISTICS.get(sector, SECTOR_CHARACTERISTICS["default"])
            char_variance = sum((sc - 0.0) ** 2 for sc in sector_chars) / len(sector_chars)
            variance_score = 3.0 + char_variance * 2.0
            score = regime_score * 0.4 + char_score * 0.4 + variance_score * 0.2
            result["score"] = score
            result["sector_benefits"] = False
            result["normalized_overlap"] = 0.0
            result["deja_vu_factor"] = round(1.0 - regime_certainty, 3)
            result["signal_strength"] = "weak"
            result["char_variance"] = round(char_variance, 3)
    else:
        # v6.1: Zero-overlap sectors get broader differentiation
        # Previously: 50% regime_score + 50% char_score was too narrow
        # Now: add sector_characteristic_variance as third component
        regime_score = 3.5 + regime_certainty * 3.0
        # v6.1: 40% regime + 40% char + 20% variance signal
        # Variance signal: sectors with more distinctive characteristic vectors get bonus
        sector_chars = SECTOR_CHARACTERISTICS.get(sector, SECTOR_CHARACTERISTICS["default"])
        char_variance = sum((sc - 0.0) ** 2 for sc in sector_chars) / len(sector_chars)
        variance_score = 3.0 + char_variance * 2.0  # Normalize to ~3-8 range
        score = regime_score * 0.4 + char_score * 0.4 + variance_score * 0.2
        result["score"] = score
        result["sector_benefits"] = False
        result["normalized_overlap"] = 0.0
        result["deja_vu_factor"] = round(1.0 - regime_certainty, 3)
        result["signal_strength"] = "weak"
        result["char_variance"] = round(char_variance, 3)

    result["best_benefit_match"] = best_benefit_name
    result["n_benefiting_states"] = n_benefiting_states
    result["current_state"] = matches[0]["name"] if matches else "unknown"

    # v6.1: Wider clamp range to accommodate expanded differentiation
    result["score"] = round(max(2.0, min(9.5, result["score"])), 1)

    return result
