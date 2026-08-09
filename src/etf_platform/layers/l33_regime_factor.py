"""
l33_regime_factor.py — Regime-aware因子制度适配层 (v1.0, k191+k196)

知识库来源:
  - k191-regime-dependent-factor-investing.md: 6因子×4制度矩阵 + 行业→因子暴露映射
  - k196-regime-aware-multi-layer-etf-penetration.md: Layer权重随regime动态调整

设计原则:
  当前factor_dynamic_weights.py的REGIME_MULTIPLIERS只有5个因子：
    oversold_depth / risk_adj_momentum / drawdown_recov / sector_flow / quality_elastic
  
  k191提供了更完整的6因子×4制度矩阵（Fama-French标准因子）：
    Value(HML) / Growth(SMB反向) / Quality(RMW+CMA) / LowVol / Momentum / Size(SMB)
  
  本层不替代已有因子层，而是做两件事：
  1. 计算"regime-factor-alignment"分数 → 注入L21_Behavior作为补充信号
  2. 返回regime权重向量 → 供投资推荐引擎/position_allocator消费

当前状态: Bull/NYSE→complacent, Caution→cautious, Fearful→fearful, Normal→normal
"""
from __future__ import annotations

import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════
# k191: 因子表现 × 制度对照表
# 评级转数值: ★=0.25, ★★=0.5, ★★★=0.75, ★★★★=1.0
# ═══════════════════════════════════════════

FACTOR_REGIME_MATRIX: Dict[str, Dict[str, float]] = {
    # 因子在四种制度下的相对表现(1.0=最强, 0.25=最弱)
    "Value":     {"bull_trend": 0.50, "bear_crisis": 0.75, "sideways": 0.50, "recovery": 0.65},
    "Growth":    {"bull_trend": 0.75, "bear_crisis": 0.25, "sideways": 0.50, "recovery": 0.60},
    "Quality":   {"bull_trend": 0.75, "bear_crisis": 0.75, "sideways": 1.00, "recovery": 0.75},
    "LowVol":    {"bull_trend": 0.25, "bear_crisis": 1.00, "sideways": 1.00, "recovery": 0.75},
    "Momentum":  {"bull_trend": 0.75, "bear_crisis": 0.25, "sideways": 0.50, "recovery": 0.50},
    "Size(SMB)": {"bull_trend": 0.50, "bear_crisis": 0.25, "sideways": 1.00, "recovery": 0.75},
}

# ═══════════════════════════════════════════
# k191: 行业ETF → Fama-French因子暴露映射
# ═══════════════════════════════════════════

# 注意: 这里的因子暴露是"该行业ETF天生偏好的因子方向"
# 正值=多头暴露，负值=空头暴露
SECTOR_FACTOR_EXPOSURE: Dict[str, Dict[str, float]] = {
    # === 宽基 ===
    "沪深300":      {"Value": 0.3, "Growth": 0.1, "Quality": 0.5, "LowVol": 0.2, "Momentum": 0.1, "Size": -0.5},
    "中证500":      {"Value": 0.2, "Growth": 0.3, "Quality": 0.4, "LowVol": -0.3, "Momentum": 0.3, "Size": 1.0},
    "中证1000":     {"Value": 0.0, "Growth": 0.2, "Quality": 0.1, "LowVol": -0.5, "Momentum": 0.2, "Size": 1.5},
    "上证50":       {"Value": 0.5, "Growth": -0.1, "Quality": 0.6, "LowVol": 0.5, "Momentum": -0.1, "Size": -1.0},
    "创业板":       {"Value": -0.5, "Growth": 0.4, "Quality": 0.1, "LowVol": -1.0, "Momentum": 0.4, "Size": 1.2},
    "大盘蓝筹":     {"Value": 0.4, "Growth": 0.0, "Quality": 0.6, "LowVol": 0.3, "Momentum": 0.0, "Size": -0.8},
    "中盘成长":     {"Value": 0.1, "Growth": 0.3, "Quality": 0.3, "LowVol": -0.2, "Momentum": 0.3, "Size": 0.8},
    "小盘价值":     {"Value": 0.8, "Growth": 0.1, "Quality": 0.3, "LowVol": -0.3, "Momentum": 0.1, "Size": 1.2},
    
    # === 科技/半导体 ===
    "半导体":       {"Value": -0.6, "Growth": 0.85, "Quality": 0.3, "LowVol": -1.5, "Momentum": 0.5, "Size": 0.8},
    "AI/科技":      {"Value": -0.5, "Growth": 0.80, "Quality": 0.2, "LowVol": -1.2, "Momentum": 0.6, "Size": 0.3},
    "AI算力":       {"Value": -0.4, "Growth": 0.75, "Quality": 0.3, "LowVol": -1.0, "Momentum": 0.5, "Size": 0.2},
    "硬科技":       {"Value": -0.5, "Growth": 0.80, "Quality": 0.2, "LowVol": -1.2, "Momentum": 0.5, "Size": 0.5},
    "通信/光模块":  {"Value": -0.6, "Growth": 0.70, "Quality": 0.1, "LowVol": -1.0, "Momentum": 0.6, "Size": 0.5},
    "计算机":       {"Value": -0.3, "Growth": 0.60, "Quality": 0.2, "LowVol": -0.8, "Momentum": 0.4, "Size": 0.5},
    "电子":         {"Value": -0.4, "Growth": 0.50, "Quality": 0.2, "LowVol": -0.8, "Momentum": 0.4, "Size": 0.3},
    "芯片":         {"Value": -0.6, "Growth": 0.85, "Quality": 0.3, "LowVol": -1.5, "Momentum": 0.5, "Size": 0.8},
    
    # === 新能源 ===
    "新能源":       {"Value": -0.1, "Growth": -0.5, "Quality": -0.1, "LowVol": -0.6, "Momentum": -0.5, "Size": 0.3},
    "新能源车":     {"Value": -0.2, "Growth": -0.3, "Quality": 0.1, "LowVol": -0.5, "Momentum": -0.2, "Size": 0.5},
    "光伏":         {"Value": -0.5, "Growth": -0.6, "Quality": -0.3, "LowVol": -1.5, "Momentum": -0.6, "Size": 0.8},
    "风电":         {"Value": -0.3, "Growth": -0.3, "Quality": 0.0, "LowVol": -1.0, "Momentum": -0.3, "Size": 0.5},
    "电池":         {"Value": -0.2, "Growth": -0.1, "Quality": 0.2, "LowVol": -0.4, "Momentum": 0.0, "Size": 0.4},
    
    # === 医药 ===
    "创新药":       {"Value": -0.3, "Growth": 0.5, "Quality": 0.3, "LowVol": -0.8, "Momentum": 0.8, "Size": 0.5},
    "医药":         {"Value": -0.3, "Growth": 0.5, "Quality": 0.3, "LowVol": -0.3, "Momentum": 0.4, "Size": 0.5},
    "中药":         {"Value": 0.4, "Growth": 0.3, "Quality": 0.5, "LowVol": 0.3, "Momentum": 0.2, "Size": 0.3},
    "医疗器械":     {"Value": 0.0, "Growth": 0.3, "Quality": 0.4, "LowVol": 0.0, "Momentum": 0.3, "Size": 0.4},
    
    # === 消费 ===
    "消费":         {"Value": 0.3, "Growth": 0.0, "Quality": 0.6, "LowVol": 0.6, "Momentum": 0.1, "Size": 0.0},
    "白酒":         {"Value": 0.4, "Growth": 0.0, "Quality": 0.8, "LowVol": 0.7, "Momentum": 0.0, "Size": -0.3},
    "食品饮料":     {"Value": 0.5, "Growth": 0.1, "Quality": 0.7, "LowVol": 0.8, "Momentum": 0.1, "Size": -0.2},
    "家电":         {"Value": 0.2, "Growth": 0.2, "Quality": 0.5, "LowVol": 0.4, "Momentum": 0.2, "Size": 0.0},
    "旅游":         {"Value": -0.3, "Growth": 0.8, "Quality": -0.1, "LowVol": -0.4, "Momentum": 0.3, "Size": 0.8},
    "传媒":         {"Value": -0.5, "Growth": 1.0, "Quality": -0.1, "LowVol": -0.6, "Momentum": 0.2, "Size": 1.0},
    "游戏":         {"Value": -0.6, "Growth": 1.2, "Quality": 0.0, "LowVol": -0.8, "Momentum": 0.1, "Size": 1.2},
    
    # === 金融 ===
    "银行":         {"Value": 0.6, "Growth": -0.1, "Quality": 0.5, "LowVol": 0.7, "Momentum": -0.1, "Size": -0.5},
    "保险":         {"Value": 0.5, "Growth": 0.0, "Quality": 0.4, "LowVol": 0.6, "Momentum": 0.0, "Size": -0.4},
    "券商":         {"Value": 0.1, "Growth": 0.6, "Quality": 0.1, "LowVol": -1.5, "Momentum": 0.6, "Size": -0.3},
    "金融":         {"Value": 0.3, "Growth": 0.0, "Quality": 0.4, "LowVol": 0.5, "Momentum": 0.0, "Size": -0.3},
    
    # === 防御 ===
    "红利/价值":    {"Value": 0.7, "Growth": -0.5, "Quality": 0.8, "LowVol": 0.8, "Momentum": 0.0, "Size": -0.8},
    "公用事业":     {"Value": 1.0, "Growth": 0.0, "Quality": 0.5, "LowVol": 1.2, "Momentum": 0.0, "Size": -0.5},
    "黄金":         {"Value": 0.0, "Growth": 0.0, "Quality": 0.0, "LowVol": 1.5, "Momentum": 0.0, "Size": 0.0},
    "贵金属":       {"Value": 0.0, "Growth": 0.0, "Quality": 0.0, "LowVol": 1.5, "Momentum": 0.0, "Size": 0.0},
    "债券":         {"Value": 0.5, "Growth": -0.2, "Quality": 0.4, "LowVol": 1.0, "Momentum": -0.2, "Size": -0.3},
    
    # === 周期/资源 ===
    "军工":         {"Value": 0.0, "Growth": 0.6, "Quality": 0.1, "LowVol": -0.7, "Momentum": 0.8, "Size": 0.6},
    "煤炭":         {"Value": 0.8, "Growth": 0.1, "Quality": 0.3, "LowVol": 0.3, "Momentum": 0.1, "Size": 0.0},
    "有色/金属":    {"Value": 0.2, "Growth": 0.2, "Quality": 0.1, "LowVol": -0.6, "Momentum": 0.2, "Size": 0.3},
    "钢铁":         {"Value": 0.8, "Growth": -0.1, "Quality": 0.1, "LowVol": -0.2, "Momentum": -0.1, "Size": 0.2},
    "化工":         {"Value": 0.3, "Growth": 0.5, "Quality": 0.4, "LowVol": 0.0, "Momentum": 0.3, "Size": 0.5},
    "农产品":       {"Value": 0.1, "Growth": 0.1, "Quality": 0.0, "LowVol": -0.2, "Momentum": 0.1, "Size": 0.2},
    "房地产":       {"Value": -0.2, "Growth": -0.5, "Quality": -0.3, "LowVol": -0.2, "Momentum": -0.5, "Size": -0.2},
    "汽车":         {"Value": -0.2, "Growth": 0.5, "Quality": 0.1, "LowVol": -0.6, "Momentum": 0.1, "Size": 0.5},
    "养殖":         {"Value": 0.0, "Growth": 0.0, "Quality": 0.0, "LowVol": 0.0, "Momentum": 0.0, "Size": 0.0},
    "农牧":         {"Value": 0.0, "Growth": 0.0, "Quality": 0.0, "LowVol": 0.0, "Momentum": 0.0, "Size": 0.0},
    "电力":         {"Value": 0.5, "Growth": 0.0, "Quality": 0.5, "LowVol": 0.5, "Momentum": 0.0, "Size": -0.2},
    "低空经济":     {"Value": -0.8, "Growth": 1.0, "Quality": 0.0, "LowVol": -1.5, "Momentum": 0.3, "Size": 1.0},
    "具身智能":     {"Value": -0.8, "Growth": 1.0, "Quality": 0.0, "LowVol": -1.5, "Momentum": 0.4, "Size": 1.0},
    "量子计算":     {"Value": -0.9, "Growth": 1.0, "Quality": 0.0, "LowVol": -1.5, "Momentum": 0.5, "Size": 1.0},
}

# ═══════════════════════════════════════════
# k196: Regime → Layer权重矩阵
# 每个regime下哪些Layer应该高权重/低权重
# ═══════════════════════════════════════════

REGIME_LAYER_WEIGHTS: Dict[str, Dict[str, float]] = {
    "bull_trend": {
        "high_weight_layers": ["L6", "L7", "L8", "L9", "L10", "L26-L30"],
        "low_weight_layers": ["L11", "L12", "L13", "L21", "L22", "L23", "L24"],
        "key_message": "技术面+动量优先，宏观风控降权",
    },
    "bear_crisis": {
        "high_weight_layers": ["L11", "L12", "L13", "L14", "L21", "L22", "L23", "L24", "L25", "L30"],
        "low_weight_layers": ["L6", "L7", "L8", "L9", "L26", "L27", "L28", "L29", "L30"],
        "key_message": "风控+宏观优先，技术面噪音大，质量/低波胜出",
    },
    "sideways": {
        "high_weight_layers": ["L21", "L22", "L23", "L6", "L7", "L8", "L9"],
        "low_weight_layers": ["L11", "L12", "L13", "L16", "L17", "L26", "L27", "L28", "L29", "L30"],
        "key_message": "微观结构+均值回归有效，宏观压力信号弱化",
    },
    "recovery": {
        "high_weight_layers": ["L16", "L17", "L18", "L19", "L20", "L26", "L27", "L28", "L29", "L30"],
        "low_weight_layers": ["L11", "L12", "L13", "L14"],
        "key_message": "政策/估值修复窗口，Quality+Value优先",
    },
}

# ═══════════════════════════════════════════
# QVIX regime → k196 regime 映射
# ═══════════════════════════════════════════

QVIX_TO_REGIME = {
    "complacent": "bull_trend",
    "normal": "sideways",
    "cautious": "sideways",  # 谨慎期更接近震荡市
    "fearful": "bear_crisis",
}


class RegimeFactorLayer:
    """Regime-aware因子制度适配层 (k191+k196)。"""
    
    def __init__(self):
        pass
    
    def get_regime(self, qvix_regime: str = "normal") -> str:
        return QVIX_TO_REGIME.get(qvix_regime, "sideways")
    
    def factor_alignment_score(self, sector: str, regime: str = "sideways") -> float:
        """
        计算给定sector在当前regime下的因子匹配度(0-10)。
        
        逻辑:
        1. 找到sector的因子暴露(来自SECTOR_FACTOR_EXPOSURE)
        2. 找到regime下各因子的表现(来自FACTOR_REGIME_MATRIX)
        3. 对齐分数 = Σ(exposure_i × performance_i) 归一化到0-10
        
        高分 = ETF因子暴露与当前regime偏好一致
        低分 = ETF因子暴露与当前regime冲突
        """
        exposure = SECTOR_FACTOR_EXPOSURE.get(sector)
        if not exposure:
            # Fallback: try common partial matches
            for key, exp in SECTOR_FACTOR_EXPOSURE.items():
                if key in sector or sector in key:
                    exposure = exp
                    break
        if not exposure:
            # Default: broad-based exposure
            exposure = {"Value": 0.0, "Growth": 0.0, "Quality": 0.0, "LowVol": 0.0, "Momentum": 0.0, "Size": 0.0}
        
        regime_perf = FACTOR_REGIME_MATRIX
        
        # Weighted alignment: sum(exposure * performance)
        raw_score = 0.0
        total_exposure = 0.0
        for factor in ["Value", "Growth", "Quality", "LowVol", "Momentum", "Size(SMB)"]:
            perf = regime_perf[factor][regime]
            exp_key = "Size" if factor == "Size(SMB)" else factor
            exp = exposure.get(exp_key, 0.0)
            raw_score += exp * perf
            total_exposure += abs(exp)
        
        if total_exposure == 0:
            return 5.0
        
        # Normalize to 0-10 scale
        # raw_score can be negative (conflicting exposures), so map:
        # max possible = sum(|exp| * max_perf) ≈ total_exposure * 1.0
        normalized = 5.0 + (raw_score / total_exposure) * 5.0
        return round(max(1.0, min(10.0, normalized)), 1)
    
    def get_regime_layer_weights(self, regime: str) -> Dict[str, object]:
        return REGIME_LAYER_WEIGHTS.get(regime, REGIME_LAYER_WEIGHTS["sideways"])
    
    def recommended_overallocate(self, regime: str) -> list:
        """k191实战决策规则: 给定regime下应超配的因子。"""
        rules = {
            "bear_crisis": ["Quality", "LowVol", "Value"],
            "bull_trend": ["Momentum", "Growth"],
            "recovery": ["Quality", "Value", "Size"],
            "sideways": ["Quality", "LowVol", "Value"],
        }
        return rules.get(regime, ["Quality", "LowVol"])
    
    def recommended_underallocate(self, regime: str) -> list:
        """k191实战决策规则: 给定regime下应低配的因子。"""
        rules = {
            "bear_crisis": ["Growth", "Momentum", "Size"],
            "bull_trend": ["Value", "LowVol"],
            "recovery": ["Momentum"],
            "sideways": ["Momentum"],
        }
        return rules.get(regime, ["Momentum"])
    
    def compute_l33_result(self, sector: str, qvix_regime: str = "normal") -> Dict:
        """
        完整L33输出: regime识别→因子对齐分→超额/低配因子→层权重建议。
        可被pipeline.py调用。
        """
        regime = self.get_regime(qvix_regime)
        alignment = self.factor_alignment_score(sector, regime)
        over = self.recommended_overallocate(regime)
        under = self.recommended_underallocate(regime)
        layer_w = self.get_regime_layer_weights(regime)
        
        return {
            "layer_key": "L33_RegimeFactor",
            "score": alignment,
            "regime": regime,
            "qvix_regime": qvix_regime,
            "alignment_score": alignment,
            "overallocate_factors": over,
            "underallocate_factors": under,
            "high_weight_layers": layer_w["high_weight_layers"],
            "low_weight_layers": layer_w["low_weight_layers"],
            "key_message": layer_w["key_message"],
            "kb_source": "k191+k196",
        }


def apply_hurst_calibration(scores: Dict, detail: Dict, H: Optional[float], regime: str) -> Dict:
    """按 Hurst 指数校准 L33 制度因子分数（来源: k190）。

    H>0.55 且处于震荡/正常市 → 趋势制度，趋势因子加分 0.3；
    H<0.45 且处于震荡市 → 均值回归期，对趋势因子降权 0.3。
    分数 clip 到 [0,10]，返回 {"score", "detail"}。
    """
    if H is None or not regime:
        return {"score": scores.get("score", 0.0), "detail": detail}
    new_score = float(scores.get("score", 0.0))
    if H > 0.55 and regime in ("sideways", "normal"):
        new_score += 0.3
    elif H < 0.45 and regime == "sideways":
        new_score -= 0.3
    new_score = round(max(0.0, min(10.0, new_score)), 1)

    from etf_platform.analysis.hurst_regime import classify_regime
    detail = dict(detail)
    detail["hurst"] = H
    detail["hurst_regime"] = classify_regime(H, 0.0)["label"]
    detail["score"] = new_score
    detail["alignment_score"] = new_score
    return {"score": new_score, "detail": detail}


def score_l33_layer(sector: str, qvix_regime: str = "normal", hurst: Optional[float] = None) -> Dict:
    """Pipeline友好接口: 返回{score: float, detail: dict}。可传 hurst 做制度校准(k190)。"""
    layer = RegimeFactorLayer()
    result = layer.compute_l33_result(sector, qvix_regime)
    scores = {
        "score": result["score"],
        "detail": result,
    }
    if hurst is not None:
        scores = apply_hurst_calibration(scores, result, hurst, result.get("regime", "sideways"))
    else:
        result["hurst"] = None
    return scores


if __name__ == "__main__":
    layer = RegimeFactorLayer()
    
    print("=== L33 Regime Factor Score Tests ===\n")
    test_cases = [
        ("半导体", "fearful"),    # 半导体: Growth高+LowVol低; fearful下Growth低配, LowVol超配 → 低分
        ("半导体", "bull_trend"),  # bull: Momentum+Growth超配 → 高分
        ("红利/价值", "fearful"),  # 红利: LowVol高+Quality高; fearful下LowVol+Quality超配 → 高分
        ("红利/价值", "bull_trend"),  # bull: LowVol/Momentum低配 → 低分
        ("消费", "recovery"),      # 消费: Quality+Value; recovery下Quality+Value超配 → 高分
        ("军工", "fearful"),       # 军工: Momentum高; fearful下Momentum低配 → 低分
        ("军工", "bull_trend"),    # bull: Momentum超配 → 高分
        ("银行", "bear_crisis"),   # 银行: Value+LowVol+Quality; bear: 全部超配 → 高分
    ]
    
    for sector, regime in test_cases:
        r = layer.compute_l33_result(sector, regime)
        print(f"{sector:10s} | {regime:14s} | score={r['score']:5.1f} | over={r['overallocate_factors']} | under={r['underallocate_factors']}")
    
    print("\n=== Regime→Layer Weights ===")
    for reg in ["bull_trend", "bear_crisis", "sideways", "recovery"]:
        w = layer.get_regime_layer_weights(reg)
        print(f"\n{reg}:")
        print(f"  High: {', '.join(w['high_weight_layers'])}")
        print(f"  Low:  {', '.join(w['low_weight_layers'])}")
        print(f"  Msg:  {w['key_message']}")
