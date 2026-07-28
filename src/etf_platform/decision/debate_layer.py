#!/usr/bin/env python3
"""
debate_layer.py — K184 辩论式ETF推荐验证层（Bull vs Bear）

L30 辩论层：在综合评分之后、最终推荐之前运行。
将穿透评分拆分为两个阵营，各自生成论点，仲裁者做风险加权裁决。

架构映射（K184）：
  Bull Agent: 基本面/技术面/信号面高分项 → 做多理由
  Bear Agent: 风控面/周期面/行为面/缺口项 → 做空/谨慎理由
  Arbitrator: 风险优先（bear权重1.3x），输出 verdict

用法:
  from .decision.debate_layer import debate_etf
  result = debate_etf(layer_scores, profile="均衡")
"""
import json
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

# ─── 阵营划分 ──────────────────────────────────────────────

BULL_LAYERS = {
    "L3_Material", "L4_SupplyChain", "L5_Tech",
    "L6_Politics", "L7_Irreplaceable",
    "L9_Signals", "L10_Demand", "L12_PoliticalRisk",
    "L13_MacroCycle", "L16_LiveSignals",
    "L17_Factor", "L19_FXChannel", "L24_DipFlow",
}

BEAR_LAYERS = {
    "L1_ETF", "L8_CapitalFlow",
    "L11_SectorRisk", "L14_StoicRisk", "L15_StateSim",
    "L18_VaR", "L20_OptionVol", "L21_Behavior", "L23_Valuation",
}

RISK_LAYERS = {
    "L14_StoicRisk", "L18_VaR", "L20_OptionVol",
    "L11_SectorRisk", "L12_PoliticalRisk", "L15_StateSim",
}

NEUTRAL_LAYERS = {"L1_ETF", "L24_DipFlow"}


def _arg_score(score: float, layer: str, invert: bool = True) -> float:
    """Score → strength for argument generation.
    
    Higher score means 'safer'. So:
    - Bull arg is stronger when layer score is HIGH (good conditions)
    - Bear arg is stronger when layer score is LOW (bad conditions)
    """
    if score < 1.0 or score > 10.0:
        return 0.5  # neutral fallback
    if invert:
        return (score - 5.0) / 5.0  # [−1, +1]
    return (5.0 - score) / 5.0


def _generate_bull_case(scores: Dict[str, float]) -> list:
    """Generate bullish arguments from positive indicators."""
    args = []
    strong_signals = []
    moderate_signals = []
    
    layer_names = {
        "L3_Material": "材料/资源供给",
        "L4_SupplyChain": "供应链稳定性",
        "L5_Tech": "技术竞争力",
        "L6_Politics": "政策支持",
        "L7_Irreplaceable": "不可替代性",
        "L9_Signals": "信号面强度",
        "L10_Demand": "需求景气度",
        "L12_PoliticalRisk": "政治风险评估",
        "L13_MacroCycle": "宏观周期",
        "L16_LiveSignals": "实时信号",
        "L17_Factor": "量化因子",
        "L24_DipFlow": "折溢价环境",
    }
    
    for layer in sorted(BULL_LAYERS | RISK_LAYERS):
        score = scores.get(layer, 5.0)
        if isinstance(score, (int, float)):
            name = layer_names.get(layer, layer)
            diff = score - 5.0
            if diff >= 1.0:
                args.append({
                    "layer": layer,
                    "name": name,
                    "score": round(score, 1),
                    "strength": round(diff / 5.0, 3),
                    "text": f"{name}(L:{layer[1:]})={score:.1f}/10，显著正向",
                })
                strong_signals.append(name)
            elif diff >= 0.3:
                args.append({
                    "layer": layer,
                    "name": name,
                    "score": round(score, 1),
                    "strength": round(diff / 5.0, 3),
                    "text": f"{name}(L:{layer[1:]})={score:.1f}/10，偏正向",
                })
                moderate_signals.append(name)
    
    return {
        "arguments": args,
        "strong_count": len(strong_signals),
        "moderate_count": len(moderate_signals),
        "summary": f"多头论据：强信号{len(strong_signals)}个，温和信号{len(moderate_signals)}个",
    }


def _generate_bear_case(scores: Dict[str, float]) -> list:
    """Generate bearish/cautionary arguments from negative indicators."""
    args = []
    danger_zones = []
    caution_zones = []
    
    layer_names = {
        "L1_ETF": "ETF本身风险",
        "L8_CapitalFlow": "资金流向",
        "L11_SectorRisk": "行业风险敞口",
        "L14_StoicRisk": "斯多葛风控",
        "L15_StateSim": "状态相似性(均值回归)",
        "L18_VaR": "VaR尾部风险",
        "L20_OptionVol": "期权隐含波动率",
        "L21_Behavior": "投资心理偏差",
        "L23_Valuation": "估值惩罚",
    }
    
    for layer in sorted(BEAR_LAYERS | RISK_LAYERS):
        score = scores.get(layer, 5.0)
        if isinstance(score, (int, float)):
            name = layer_names.get(layer, layer)
            diff = 5.0 - score
            if diff >= 1.5:
                args.append({
                    "layer": layer,
                    "name": name,
                    "score": round(score, 1),
                    "strength": round(min(1.0, diff / 5.0), 3),
                    "text": f"⚠️ {name}(L:{layer[1:]})={score:.1f}/10，显著反向/高风险",
                })
                danger_zones.append(name)
            elif diff >= 0.5:
                args.append({
                    "layer": layer,
                    "name": name,
                    "score": round(score, 1),
                    "strength": round(min(1.0, diff / 5.0), 3),
                    "text": f"⚠ {name}(L:{layer[1:]})={score:.1f}/10，偏谨慎",
                })
                caution_zones.append(name)
    
    return {
        "arguments": args,
        "danger_count": len(danger_zones),
        "caution_count": len(caution_zones),
        "summary": f"空头论据：危险区{len(danger_zones)}个，谨慎区{len(caution_zones)}个",
    }


def _arbitrate(bull: dict, bear: dict, scores: Dict[str, float], profile: str = "均衡") -> dict:
    """Weighted arbitration: risk matters more."""
    bull_score = bull["strong_count"] * 1.0 + bull["moderate_count"] * 0.5
    bear_score = bear["danger_count"] * 1.3 + bear["caution_count"] * 0.7  # Risk premium
    
    total = bull_score + bear_score
    if total <= 0:
        verdict = "中性/数据不足"
        confidence = 0.0
        direction = 0.0
    else:
        bull_pct = bull_score / total
        bear_pct = bear_score / total
        
        # Weighted direction: -1(bear) to +1(bull)
        direction = bull_pct - bear_pct
        
        if abs(direction) < 0.15:
            verdict = "中性分歧"
        elif direction > 0.4:
            verdict = "看多（Bull优势）"
        elif direction > 0.15:
            verdict = "谨慎看多（Bull微弱优势）"
        elif direction < -0.4:
            verdict = "看空（Bear优势）"
        elif direction < -0.15:
            verdict = "谨慎看空（Bear微弱优势）"
        else:
            verdict = "平衡对立"
        
        confidence = min(1.0, total / max(bull["strong_count"] + bear["danger_count"] + bull["moderate_count"] + bear["caution_count"], 1))
    
    # Risk veto: if any critical risk layer is below 2.0, flag it
    vetoes = []
    critical_thresholds = {"L14_StoicRisk": 2.0, "L18_VaR": 2.5, "L11_SectorRisk": 2.0}
    for layer, threshold in critical_thresholds.items():
        score = scores.get(layer, 5.0)
        if isinstance(score, (int, float)) and score < threshold:
            vetoes.append(f"{layer}={score:.1f} 低于阈值{threshold}")
    
    return {
        "verdict": verdict,
        "direction": round(direction, 3),
        "confidence": round(confidence, 3),
        "bull_weighted": round(bull_score, 2),
        "bear_weighted": round(bear_score, 2),
        "vetoes": vetoes,
    }


def debate_etf(
    layer_scores: Dict[str, Any],
    profile: str = "均衡",
    etf_code: str = "",
    etf_name: str = "",
) -> dict:
    """Run the full Bull vs Bear debate on one ETF's penetration scores.
    
    Returns:
        {
            "code": str,
            "name": str,
            "bull_case": {...},
            "bear_case": {...},
            "verdict": str,
            "direction": float,
            "confidence": float,
            "vetoes": list,
        }
    """
    bull = _generate_bull_case(layer_scores)
    bear = _generate_bear_case(layer_scores)
    arb = _arbitrate(bull, bear, layer_scores, profile)
    
    result = {
        "code": etf_code,
        "name": etf_name,
        "profile": profile,
        "bull_case": bull,
        "bear_case": bear,
        **arb,
    }
    
    return result


# Export for testing
if __name__ == "__main__":
    # Demo
    demo_scores = {
        "L3_Material": 7.5, "L4_SupplyChain": 6.0, "L5_Tech": 8.0,
        "L6_Politics": 5.0, "L7_Irreplaceable": 6.5,
        "L8_CapitalFlow": 4.0, "L9_Signals": 7.0, "L10_Demand": 6.5,
        "L11_SectorRisk": 3.0, "L12_PoliticalRisk": 5.5,
        "L13_MacroCycle": 4.5, "L14_StoicRisk": 7.0,
        "L15_StateSim": 6.0, "L16_LiveSignals": 5.5,
        "L17_Factor": 5.0, "L18_VaR": 3.5,
        "L20_OptionVol": 4.0, "L21_Behavior": 6.0,
        "L23_Valuation": 3.0, "L24_DipFlow": 5.5,
    }
    
    print(json.dumps(debate_etf(demo_scores, etf_code="000001", etf_name="测试"), ensure_ascii=False, indent=2))
