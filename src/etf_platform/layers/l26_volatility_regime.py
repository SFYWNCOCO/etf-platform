"""L26 Volatility Regime Layer — 波动率制度+GARCH信号(k063+k091).

KB来源:
  - k063-volatility-trading-vix.md: VIX/波动率交易框架
  - k091-quant-time-series-garch-pairs-trading.md: GARCH+配对交易

核心规则:
  - 低波动率环境→动量/成长因子占优
  - 高波动率环境→防御/低波/价值因子占优
  - GARCH聚类效应: 高波动持续→谨慎
  - 波动率均值回归: 极端高/低波动率→反转信号
  - 配对交易: 行业ETF相对偏离→均值回归机会

设计:
  - 纯KB+规则驱动，无HTTP
  - 按sector映射波动率敏感度和当前制度评分
  - 中心5.0，微调±2.0
"""
from __future__ import annotations

from typing import Any

# k063: 行业波动率敏感度
SECTOR_VOL_SENSITIVITY: dict[str, float] = {
    "半导体": 1.5,
    "AI算力": 1.4,
    "新能源": 1.3,
    "光伏": 1.4,
    "医药": 0.9,
    "创新药": 1.2,
    "军工": 1.1,
    "消费": 0.6,
    "白酒": 0.7,
    "金融": 0.8,
    "银行": 0.5,
    "券商": 1.3,
    "红利": 0.4,
    "公用事业": 0.3,
    "通信": 0.8,
    "电子": 1.0,
    "计算机": 1.1,
    "传媒": 1.0,
    "游戏": 1.2,
    "电力": 0.4,
    "煤炭": 0.7,
    "有色金属": 1.1,
    "钢铁": 0.9,
    "房地产": 1.0,
    "建筑装饰": 0.7,
    "商业航天": 1.2,
    "低空经济": 1.1,
    "AI4S": 1.0,
    "具身智能": 1.1,
    "合成生物": 1.0,
    "脑机接口": 1.2,
    "量子计算": 1.3,
}

# k063: 波动率制度→推荐策略
VOL_REGIME_STRATEGY: dict[str, dict[str, Any]] = {
    "low_vol_bull": {
        "score_adj": 1.0,
        "strategy": "momentum_growth",
        "description": "低波动牛市：动量/成长占优",
    },
    "normal": {
        "score_adj": 0.0,
        "strategy": "balanced",
        "description": "正常波动：均衡配置",
    },
    "high_vol_caution": {
        "score_adj": -0.8,
        "strategy": "defense_value",
        "description": "高波动谨慎：防御/价值占优",
    },
    "extreme_vol_fear": {
        "score_adj": -1.5,
        "strategy": "capital_preservation",
        "description": "极端波动恐慌：资本保全",
    },
}

# k091: GARCH聚类效应修正
GARCH_CLUSTERING_PENALTY: dict[str, float] = {
    "low_vol_bull": 0.3,
    "normal": 0.0,
    "high_vol_caution": -0.5,
    "extreme_vol_fear": -1.0,
}


def _normalize_sector(sector: str) -> str:
    """Normalize sector aliases."""
    aliases = {
        "半导体设备": "半导体",
        "半导体材料": "半导体",
        "芯片": "半导体",
        "AI/科技": "AI算力",
        "AI/半导体": "AI算力",
        "云计算/算力": "AI算力",
        "通信/光模块": "AI算力",
        "通信/5G": "AI算力",
        "5G/PCB": "AI算力",
        "机器人/智造": "具身智能",
        "新能源车": "新能源",
        "电池": "新能源",
        "储能": "新能源",
        "绿电": "新能源",
        "电力": "新能源",
        "医药生物": "医药",
        "医药器械": "医药",
        "中药": "医药",
        "国防军工": "军工",
        "红利/价值": "红利",
        "食品饮料": "消费",
        "家电": "消费",
        "人形机器人": "具身智能",
    }
    return aliases.get(sector, sector)


def infer_vol_regime(
    realized_vol: float | None = None,
    vix_level: float | None = None,
    sector: str = "",
) -> str:
    """Infer volatility regime from available signals.

    Args:
        realized_vol: Annualized realized volatility (e.g., 0.15=15%)
        vix_level: VIX/QVIX level (e.g., 15=low, 25=high)
        sector: Sector for sector-specific thresholds

    Returns:
        Regime string: low_vol_bull/normal/high_vol_caution/extreme_vol_fear
    """
    sector_norm = _normalize_sector(sector)
    vol_sens = SECTOR_VOL_SENSITIVITY.get(sector_norm, 1.0)

    # Use VIX as primary signal if available
    if vix_level is not None:
        if vix_level < 15:
            return "low_vol_bull"
        if vix_level > 35:
            return "extreme_vol_fear"
        if vix_level > 25:
            return "high_vol_caution"
        return "normal"

    # Fallback to realized volatility
    if realized_vol is not None:
        threshold_base = 0.20 / vol_sens
        if realized_vol < threshold_base * 0.6:
            return "low_vol_bull"
        if realized_vol > threshold_base * 1.8:
            return "extreme_vol_fear"
        if realized_vol > threshold_base * 1.2:
            return "high_vol_caution"
        return "normal"

    return "normal"


def score_l26_layer(
    sector: str = "",
    vol_regime: str | None = None,
    realized_vol: float | None = None,
    vix_level: float | None = None,
    pair_deviation: float | None = None,
) -> dict[str, Any]:
    """Score volatility regime alignment for sector.

    Args:
        sector: ETF sector
        vol_regime: Pre-computed regime (optional)
        realized_vol: Annualized realized volatility
        vix_level: VIX/QVIX level
        pair_deviation: Sector ETF pair deviation for mean-reversion signal

    Returns:
        dict with 'score'(float), 'detail'(dict)
    """
    sector_norm = _normalize_sector(sector)
    vol_sens = SECTOR_VOL_SENSITIVITY.get(sector_norm, 1.0)

    # Infer regime if not provided
    if vol_regime is None:
        vol_regime = infer_vol_regime(realized_vol, vix_level, sector_norm)

    regime_info = VOL_REGIME_STRATEGY.get(vol_regime, VOL_REGIME_STRATEGY["normal"])
    regime_adj = regime_info["score_adj"]
    clustering = GARCH_CLUSTERING_PENALTY.get(vol_regime, 0.0)

    # Sector volatility sensitivity adjustment
    # High-vol sectors get penalized more in high-vol regimes
    if vol_regime in ("high_vol_caution", "extreme_vol_fear"):
        sens_penalty = -(vol_sens - 1.0) * 0.5
    elif vol_regime == "low_vol_bull":
        sens_penalty = (vol_sens - 1.0) * 0.3
    else:
        sens_penalty = 0.0

    # k091: Pair deviation mean-reversion signal
    pair_signal = "neutral"
    pair_adj = 0.0
    if pair_deviation is not None:
        abs_dev = abs(pair_deviation)
        if abs_dev > 3.0:
            pair_adj = 1.2  # Strong mean-reversion opportunity
            pair_signal = "strong_reversion"
        elif abs_dev > 2.0:
            pair_adj = 0.7
            pair_signal = "moderate_reversion"
        elif abs_dev > 1.0:
            pair_adj = 0.3
            pair_signal = "mild_reversion"

    # Combine
    raw = 5.0 + regime_adj + clustering + sens_penalty + pair_adj
    score = round(max(1.0, min(10.0, raw)), 1)

    # Recommended strategy
    strategy = regime_info["strategy"]
    if pair_signal != "neutral":
        strategy += "+mean_reversion"

    detail = {
        "sector": sector_norm,
        "vol_sensitivity": vol_sens,
        "vol_regime": vol_regime,
        "regime_strategy": regime_info["description"],
        "realized_vol": realized_vol,
        "vix_level": vix_level,
        "pair_deviation": pair_deviation,
        "pair_signal": pair_signal,
        "recommended_strategy": strategy,
        "kb_source": "k063+k091",
    }
    return {"score": score, "detail": detail}
