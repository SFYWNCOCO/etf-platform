"""analyst_team.py — 分析师团队（TradingAgents 启发：角色分解 + 结构化报告）

将ETF穿透的各层评分按角色分组，每个角色输出结构化报告。
模仿 TradingAgents 的团队结构：

  Analyst Team → [宏观分析师, 技术分析师, 基本面分析师, 新闻情绪分析师]
                   ↓ 并行分析
               ConsensusGate → RiskGate → PortfolioManager

与已有架构的关系：
  - 不替代 pipeline.py / run_full()，而是包装其输出
  - 不替代 debate_layer.py，而是赋予辩论双方角色身份
  - 不替代 risk_manager.py，risk_gate.py 是独立的评分时门禁
"""

import logging
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# 分析师角色定义
# ═══════════════════════════════════════════

ANALYST_ROLES = {
    "宏观分析师": {
        "alias": "Macro",
        "layers": ["L13_MacroCycle", "L12_PoliticalRisk", "L15_StateSim", "L33_RegimeFactor"],
        "description": "宏观周期/政治风险/市场状态/制度因子分析",
        "weight": 0.20,
    },
    "技术分析师": {
        "alias": "Technical",
        "layers": ["L16_LiveSignals", "L18_VaR", "L20_OptionVol", "L17_Factor",
                    "L8_CapitalFlow", "L9_Signals", "L24_DipFlow"],
        "description": "实时信号/波动率/VaR/期权/因子动量/资金流",
        "weight": 0.25,
    },
    "基本面分析师": {
        "alias": "Fundamental",
        "layers": ["L3_Material", "L4_SupplyChain", "L5_Tech", "L6_Politics",
                    "L7_Irreplaceable", "L10_Demand", "L23_Valuation",
                    "L4_KBDeep_Score"],
        "description": "供应链/技术/不可替代性/需求/估值",
        "weight": 0.30,
    },
    "行为风控师": {
        "alias": "Risk",
        "layers": ["L11_SectorRisk", "L14_StoicRisk", "L19_FXChannel",
                    "L21_Behavior", "L1_ETF"],
        "description": "行业风险/Stoic/汇兑/行为偏差/基准",
        "weight": 0.25,
    },
}


# ═══════════════════════════════════════════
# 分析师报告
# ═══════════════════════════════════════════

class AnalystReport:
    """单个分析师的输出报告。"""
    
    def __init__(self, role_name: str, score: float, layer_scores: Dict[str, float],
                 key_factors: List[str], confidence: float = 0.5, polarity: str = "neutral"):
        self.role_name = role_name
        self.score = score          # 0-10
        self.layer_scores = layer_scores
        self.key_factors = key_factors
        self.confidence = confidence  # 0-1
        self.polarity = polarity      # "bullish", "bearish", "neutral"
    
    def to_dict(self) -> Dict:
        return {
            "role": self.role_name,
            "alias": ANALYST_ROLES.get(self.role_name, {}).get("alias", self.role_name),
            "score": self.score,
            "layer_scores": self.layer_scores,
            "key_factors": self.key_factors,
            "confidence": self.confidence,
            "polarity": self.polarity,
        }


# ═══════════════════════════════════════════
# 团队分析
# ═══════════════════════════════════════════

def _calc_polarity(name: str, score: float, layer_count: int) -> str:
    """根据分析师名称和评分判断倾向。"""
    if name == "行为风控师":
        return "bearish" if score < 4.0 else "neutral"
    if score >= 7.0:
        return "bullish"
    if score <= 3.0:
        return "bearish"
    return "neutral"


def _extract_key_factors(name: str, scores: Dict[str, float]) -> List[str]:
    """从评分中提取关键驱动因素（最低和最高的layer）。"""
    layers = ANALYST_ROLES.get(name, {}).get("layers", [])
    available = {k: v for k, v in scores.items() if k in layers and isinstance(v, (int, float))}
    if not available:
        return ["无数据"]
    sorted_items = sorted(available.items(), key=lambda x: x[1])
    lowest = sorted_items[:2]
    highest = sorted_items[-2:]
    factors = []
    for k, v in lowest:
        if v < 3.0:
            factors.append(f"{k}={v:.1f} (风险)")
    for k, v in highest:
        if v >= 7.0:
            factors.append(f"{k}={v:.1f} (优势)")
    return factors[:5]  # 最多5个


def team_analyze(layer_scores: Dict[str, float], risk_level: float = 0.5) -> Dict:
    """运行分析师团队分析，返回结构化团队报告。

    Args:
        layer_scores: pipeline.py run_full() 返回的 layer_scores
        risk_level: ETF风险等级 (0-1)

    Returns:
        {
            "team_reports": [AnalystReport, ...],
            "consensus_score": float,   # 加权共识评分
            "consensus_polarity": str,  # 共识倾向
            "disagreement": float,      # 分析师分歧度 (0-1)
        }
    """
    reports: List[Dict] = []
    total_weight = 0.0
    weighted_sum = 0.0
    polarities: List[Tuple[str, float]] = []

    for role_name, role_cfg in ANALYST_ROLES.items():
        layers = role_cfg["layers"]
        available = {k: v for k, v in layer_scores.items()
                     if k in layers and isinstance(v, (int, float))}
        
        if not available:
            continue
        
        # 该分析师的平均分
        score = round(sum(available.values()) / len(available), 2)
        polarity = _calc_polarity(role_name, score, len(available))
        key_factors = _extract_key_factors(role_name, layer_scores)
        
        # 置信度：层数越多越可信
        confidence = min(1.0, len(available) / max(len(layers), 1) * 0.8 + 0.2)
        
        report = AnalystReport(
            role_name=role_name,
            score=score,
            layer_scores=available,
            key_factors=key_factors,
            confidence=confidence,
            polarity=polarity,
        )
        reports.append(report.to_dict())
        
        weight = role_cfg["weight"]
        weighted_sum += score * weight * confidence
        total_weight += weight * confidence
        polarities.append((polarity, confidence))
    
    # 共识评分
    consensus_score = round(weighted_sum / max(total_weight, 0.01), 2)
    
    # 共识倾向：按置信度加权的多数投票
    bullish_weight = sum(c for p, c in polarities if p == "bullish")
    bearish_weight = sum(c for p, c in polarities if p == "bearish")
    if bullish_weight > bearish_weight and bullish_weight > 0.5:
        consensus_polarity = "bullish"
    elif bearish_weight > bullish_weight and bearish_weight > 0.5:
        consensus_polarity = "bearish"
    else:
        consensus_polarity = "neutral"
    
    # 分歧度：分析师评分的标准差
    scores_list = [r["score"] for r in reports]
    if len(scores_list) >= 2:
        mean = sum(scores_list) / len(scores_list)
        variance = sum((s - mean) ** 2 for s in scores_list) / len(scores_list)
        disagreement = min(1.0, variance / 6.25)  # 归一化：方差6.25对应最大分歧
    else:
        disagreement = 0.0

    return {
        "team_reports": reports,
        "consensus_score": consensus_score,
        "consensus_polarity": consensus_polarity,
        "disagreement": round(disagreement, 3),
        "risk_level": risk_level,
    }
