"""
REGIME-AWARE FACTOR & LAYER WEIGHT CONSTANTS
Extracted from k191, k196, k187, k186 (theory files)

Intended integration targets: factor_dynamic_weights.py, pipeline.py

Key sources:
  - k191: Regime-Dependent Factor Investing & Factor Rotation
  - k196: Regime-Aware Multi-Layer ETF Penetration System v2.0
  - k187: Hidden Markov Model Regime Switching
  - k186: Causal Inference in Financial Markets (Granger + structural breakpoints)
"""

from enum import Enum
from typing import Dict, List, Tuple, Optional
import numpy as np


# ============================================================
# 1. REGIME ENUM — align with HMM state IDs
#    k187/HMM typically: 4 states (LowVol Bull / HighVol Bear / Sideways / Crisis)
#    k196 uses: Bull Trend(0), Bear Crisis(1), Sideways(2), Recovery(3)
#    We use string keys for readability + int aliases for HMM compatibility
# ============================================================

class Regime(Enum):
    """Market regime states from HMM + k187/k196 synthesis."""
    BULL_TREND = 0       # Low volatility bull / trend-following valid
    BEAR_CRISIS = 1      # High volatility bear / crisis
    SIDESWAYS = 2        # Neutral consolidation / mean-reversion valid
    RECOVERY = 3         # Macro/policy recovery phase

    @classmethod
    def from_hmm_state(cls, state_id: int) -> "Regime":
        """Map HMM discrete state index → Regime enum (assumes N=4 HMM)."""
        return cls(state_id % 4)


# ============================================================
# 2. REGIME_FACTOR_MATRIX — k191 core insight
#    Stars: ★ ~ 0.25 · ★★ ~ 0.50 · ★★★ ~ 0.75 · ★★★★ ~ 1.00
#    Used as regime-conditional factor preference scores (0..1).
# ============================================================

FACTOR_NAMES = ["Value", "Growth", "Quality", "LowVol", "Momentum", "Size"]

# Each row = [Value, Growth, Quality, LowVol, Momentum, Size]
REGIME_FACTOR_SCORES: Dict[str, Dict[str, float]] = {
    Regime.BULL_TREND.name:    {f: s for f, s in zip(FACTOR_NAMES,     [0.50, 1.00, 0.75, 0.25, 0.75, 0.50])},
    Regime.BEAR_CRISIS.name:   {f: s for f, s in zip(FACTOR_NAMES,     [1.00, 0.25, 0.75, 1.00, 0.25, 0.25])},
    Regime.SIDESWAYS.name:     {f: s for f, s in zip(FACTOR_NAMES,     [0.50, 0.50, 0.75, 1.00, 0.50, 1.00])},
    Regime.RECOVERY.name:      {f: s for f, s in zip(FACTOR_NAMES,     [0.75, 0.50, 1.00, 1.00, 0.25, 0.25])},
}

# Numeric matrix version for direct computation
# Shape: (n_regimes, n_factors), ordered as Regime order above
REGIME_FACTOR_MATRIX = np.array([
    [0.50, 1.00, 0.75, 0.25, 0.75, 0.50],  # Bull Trend
    [1.00, 0.25, 0.75, 1.00, 0.25, 0.25],  # Bear Crisis
    [0.50, 0.50, 0.75, 1.00, 0.50, 1.00],  # Sideways
    [0.75, 0.50, 1.00, 1.00, 0.25, 0.25],  # Recovery
])

FACTOR_TO_INDEX = {name: idx for idx, name in enumerate(FACTOR_NAMES)}
INDEX_TO_FACTOR = {idx: name for idx, name in enumerate(FACTOR_NAMES)}


# ============================================================
# 3. REGIME MULTIPLIERS (drop-in replacement for existing REGIME_MULTIPLIERS)
#    k191实战决策规则 → numeric multipliers applied to base factor weights.
#    Base weight = 1.0; multiplier adjusts up/down per regime.
#
#    Enhancement vs naive "same weights for all regimes":
#    - Crisis: Quality/LowVol/Value ×1.5, Momentum/Growth/Size ×0.5
#    - Bull:   Momentum/Growth ×1.5, Value/LowVol ×0.5
#    - Recovery: Quality/Value ×1.5, Momentum ×0.25
#    - Sideways: Quality/LowVol ×1.5, Momentum ×0.5
# ============================================================

# Default base factor weight (before regime multiplication)
BASE_FACTOR_WEIGHT = 1.0 / len(FACTOR_NAMES)  # ~0.1667 for 6 factors

REGIME_MULTIPLIERS: Dict[str, Dict[str, float]] = {
    Regime.BULL_TREND.name: {
        "overallocate": ["Momentum", "Growth"],
        "underallocate": ["Value", "LowVol"],
        "multiplier": 1.50,
        "under_multiplier": 0.50,
        "Value": 0.50,
        "Growth": 1.50,
        "Quality": 1.00,
        "LowVol": 0.50,
        "Momentum": 1.50,
        "Size": 1.00,
    },
    Regime.BEAR_CRISIS.name: {
        "overallocate": ["Quality", "LowVol", "Value"],
        "underallocate": ["Growth", "Momentum", "Size"],
        "multiplier": 1.50,
        "under_multiplier": 0.50,
        "Value": 1.50,
        "Growth": 0.50,
        "Quality": 1.50,
        "LowVol": 1.50,
        "Momentum": 0.50,
        "Size": 0.50,
    },
    Regime.SIDESWAYS.name: {
        "overallocate": ["Quality", "LowVol", "Value"],
        "underallocate": ["Momentum"],
        "multiplier": 1.50,
        "under_multiplier": 0.50,
        "Value": 1.50,
        "Growth": 1.00,
        "Quality": 1.50,
        "LowVol": 1.50,
        "Momentum": 0.50,
        "Size": 1.50,
    },
    Regime.RECOVERY.name: {
        "overallocate": ["Quality", "Value", "Size"],
        "underallocate": ["Momentum"],
        "multiplier": 1.50,
        "under_multiplier": 0.25,
        "Value": 1.50,
        "Growth": 1.00,
        "Quality": 1.50,
        "LowVol": 1.50,
        "Momentum": 0.25,
        "Size": 1.50,
    },
}


def apply_regime_multipliers(base_weights: Dict[str, float], regime: str) -> Dict[str, float]:
    """Apply regime-specific multipliers to base factor weights.

    Args:
        base_weights: pre-regime factor allocation weights summing to 1.0
        regime: one of Regime.*.name

    Returns:
        dict normalized weights after regime adjustment, summing to 1.0
    """
    regs = REGIME_MULTIPLIERS[regime]
    adjusted = {}
    for factor, w in base_weights.items():
        adj_w = w * regs.get(factor, 1.0)
        adjusted[factor] = adj_w
    total = sum(adjusted.values())
    if total <= 0:
        total = 1e-8
    return {f: v / total for f, v in adjusted.items()}


# ============================================================
# 4. FACTOR→INDUSTRY ETF MAPPING (k191 §ETF穿透系统直接应用)
#    Each industry ETF decomposed into factor exposures.
#    Exposures are approximate quantitative scores (normalized).
#    Add/remove as your actual ETF universe grows.
# ============================================================

INDUSTRY_FACTOR_EXPOSURE: Dict[str, Dict[str, float]] = {
    # Technology / AI / Semiconductor — high Growth, high Beta
    "AI_Technology": {"Growth": 0.85, "Value": -0.30, "Quality": 0.30, "Momentum": 0.60, "LowVol": 0.10, "Size": 0.20, "Beta": 1.5},
    "Semiconductor": {"Growth": 0.90, "Value": -0.40, "Quality": 0.25, "Momentum": 0.50, "LowVol": 0.10, "Size": 0.15, "Beta": 1.6},
    "New_Energy":    {"Growth": 0.80, "Value": -0.35, "Quality": 0.30, "Momentum": 0.55, "LowVol": 0.15, "Size": 0.25, "Beta": 1.4},
    "Defense_Mil":   {"Growth": 0.60, "Value": 0.10,  "Quality": 0.10, "Momentum": 0.80, "LowVol": 0.20, "Size": 0.10, "Beta": 1.3},

    # Healthcare — high Quality, lower Beta
    "Healthcare":    {"Growth": 0.40, "Value": 0.20,  "Quality": 0.70, "Momentum": -0.10, "LowVol": 0.50, "Size": 0.20, "Beta": 0.7},

    # Financials — high Value, moderate Size
    "Banking":       {"Growth": 0.20, "Value": 0.90,  "Quality": 0.30, "Momentum": 0.10,  "LowVol": 0.40, "Size": 0.10, "Beta": 1.1},

    # Utilities — low Beta, defensive
    "Utilities":     {"Growth": 0.10, "Value": 0.60,  "Quality": 0.60, "Momentum": 0.00,  "LowVol": 0.80, "Size": 0.30, "Beta": 0.5},

    # Broad market proxies
    "Large_Cap":     {"Growth": 0.40, "Value": 0.50,  "Quality": 0.50, "Momentum": 0.30,  "LowVol": 0.30, "Size": 0.80, "Beta": 1.0},
    "Small_Cap":     {"Growth": 0.50, "Value": 0.40,  "Quality": 0.30, "Momentum": 0.40,  "LowVol": 0.10, "Size": 0.90, "Beta": 1.3},
}

# Reverse mapping: factor → industries that primarily embody it
FACTOR_TO_INDUSTRIES: Dict[str, List[str]] = {
    "Value":     ["Banking", "Utilities", "Large_Cap"],
    "Growth":    ["AI_Technology", "Semiconductor", "New_Energy", "Small_Cap"],
    "Quality":   ["Healthcare", "Utilities", "Large_Cap"],
    "LowVol":    ["Utilities", "Healthcare"],
    "Momentum":  ["AI_Technology", "Defense_Mil", "Semiconductor"],
    "Size":      ["Large_Cap", "Small_Cap"],
}


def regime_aligned_industries(regime: str, top_n: int = 4) -> List[str]:
    """Given a regime, return industries ranked by regime-factor alignment score."""
    regs = REGIME_MULTIPLIERS[regime]
    aligned = []
    for industry, exposures in INDUSTRY_FACTOR_EXPOSURE.items():
        score = 0.0
        for factor in exposures:
            if factor in ("Beta",):
                continue
            score += exposures[factor] * regs.get(factor, 1.0)
        aligned.append((industry, score))
    aligned.sort(key=lambda x: x[1], reverse=True)
    return [ind for ind, _ in aligned[:top_n]]


# ============================================================
# 5. HMM REGIME DETECTION CONDITIONS (k187)
#    Observed variables + thresholds for regime classification.
#    These are STARTING POINTS; fine-tune with your data via Baum-Welch/BIC.
# ============================================================

# HMM observation features recommended for regime detection
HMM_OBSERVATION_FEATURES: List[str] = [
    "returns",        # ETF daily returns
    "volatility",     # rolling realized vol (e.g., 20d std)
    "volume_change",  # relative volume vs moving avg
    "spread",         # bid-ask spread proxy
    "vix",            # VIX level (if available)
    "interest_rate",  # rate change / curve slope
    "dxy",            # USD index
    "credit_spread",  # HY spread
]

# Volatility-based regime labels for HMM state interpretation
HMM_STATE_LABELS: Dict[int, str] = {
    0: "Low_Vol_Bull",
    1: "High_Vol_Bear",
    2: "Moderate_Vol_Sideways",
    3: "Transition_State",
}

# Number of HMM states recommendation
HMM_N_STATES_RANGE = (3, 5)  # Use BIC/AIC to select optimal N within this range


# ============================================================
# 6. HMM TRANSITION MATRIX — k187 empirical example
#    Learned from data; this is the example matrix from k187 docs.
#    Rows = current state, columns = next state probabilities.
#    State ordering: [LowVol, Moderate, HighVol, Transition]
# ============================================================

HMM_TRANSITION_MATRIX = np.array([
    [0.97, 0.02, 0.005, 0.005],  # Low Vol → Low/Moderate/High/Transition
    [0.02, 0.85, 0.10,  0.03],   # Moderate → ...
    [0.01, 0.05, 0.80,  0.14],   # High Vol → ...
    [0.03, 0.10, 0.20,  0.67],   # Transition → ...
])

HMM_TRANSITION_INTERPRETATION = {
    "low_vol_persistence": 0.97,       # Bull trend continues 97% probability
    "high_vol_to_low_vol": 0.01,       # Only 1% chance high vol falls back to low vol
    "high_vol_transition_prob": 0.14,  # High vol → transition state: 14%
    "transition_sticky_prob": 0.67,    # Transition tends to persist
    "transition_exit_prob": 0.33,      # Transition leaves other states combined
}

# Decision rule from transition matrix:
# - If current state = HighVol and P(next=LowVol) < 0.05 → do NOT bottom-fish
# - If in Transition state → reduce position size, slow rotation frequency
TRANSITION_DECISION_RULE = {
    "high_vol_bear_do_not_bottom_fish": True,
    "transition_reduce_all_weights": True,
    "transition_decrease_rotation_frequency": True,
    "cross_etf_same_regime_signal_systematic_turning_point": True,
}


# ============================================================
# 7. REGIME → LAYER WEIGHT MATRIX (k196 + k187 synthesis)
#    Two versions exist in literature; we merge them into unified
#    layer_groups with regime-specific weight allocations.
#    Layers grouped as:
#      L1_L5  = Base Data
#      L6_L10 = Industry & Technical
#      L11_L15 = Macro & Policy
#      L16_L20 = Advanced Analytics
#      L21_L25 = Risk Management
#      L26_L30 = Decision & Action
# ============================================================

LAYER_GROUPS = {
    "L1_L5":     "Base_Data",
    "L6_L10":    "Industry_Tech",
    "L11_L15":   "Macro_Policy",
    "L16_L20":   "Advanced_Analytics",
    "L21_L25":   "Risk_Management",
    "L26_L30":   "Decision_Action",
}

# k196 regime → layer weight priorities
# Values are weight shares across 6 layer groups (must sum to 1.0)
REGIME_LAYER_WEIGHTS_K196: Dict[str, Dict[str, float]] = {
    Regime.BULL_TREND.name: {
        "L1_L5":     0.10,  # low weight
        "L6_L10":    0.30,  # HIGH: tech signals dominate
        "L11_L15":   0.05,  # LOW: macro less relevant
        "L16_L20":   0.10,
        "L21_L25":   0.05,  # LOW: risk management secondary
        "L26_L30":   0.40,  # HIGH: factor momentum execution
    },
    Regime.BEAR_CRISIS.name: {
        "L1_L5":     0.05,  # LOW: valuation signals noisy
        "L6_L10":    0.05,  # LOW: technical too noisy
        "L11_L15":   0.30,  # HIGH: macro risk dominates
        "L16_L20":   0.20,  # HIGH: cross-asset correlation
        "L21_L25":   0.30,  # HIGH: risk management critical
        "L26_L30":   0.10,  # LOW: factor growth harmful
    },
    Regime.SIDESWAYS.name: {
        "L1_L5":     0.15,  # neutral
        "L6_L10":    0.25,  # HIGH: mean reversion signals
        "L11_L15":   0.10,  # LOW: macro pressure less useful
        "L16_L20":   0.10,  # LOW: macro pressure
        "L21_L25":   0.35,  # HIGH: microstructure focus
        "L26_L30":   0.05,  # LOW: factor value underperforming
    },
    Regime.RECOVERY.name: {
        "L1_L5":     0.15,  # baseline
        "L6_L10":    0.15,  # baseline
        "L11_L15":   0.10,  # LOW: rate-sensitive less useful
        "L16_L20":   0.35,  # HIGH: macro/policy analysis
        "L21_L25":   0.10,  # baseline
        "L26_L30":   0.15,  # HIGH: quality+value execution
    },
}

# k187 regime → layer priority variant (slightly different lens)
# Use as validation/cross-check against k196
REGIME_LAYER_WEIGHTS_K187: Dict[str, Dict[str, float]] = {
    Regime.BULL_TREND.name: {
        "L1_L5":     0.30,  # HIGH: fundamental data
        "L6_L10":    0.25,  # HIGH: technical signals
        "L11_L15":   0.10,  # LOW: macro secondary
        "L16_L20":   0.10,  # LOW
        "L21_L23":   0.10,  # LOW: micro
        "L24_L29":   0.15,  # behavioral
    },
    Regime.BEAR_CRISIS.name: {
        "L1_L5":     0.05,  # LOW: valuation unreliable
        "L6_L10":    0.05,  # LOW
        "L11_L15":   0.10,  # macro
        "L16_L20":   0.30,  # HIGH: advanced analytics/risk
        "L21_L23":   0.10,  # microstructure
        "L24_L29":   0.40,  # HIGH: behavioral/emotion
    },
    Regime.SIDESWAYS.name: {
        "L1_L5":     0.15,  # baseline
        "L6_L10":    0.30,  # HIGH: industry structure
        "L11_L15":   0.10,  # LOW: macro
        "L16_L20":   0.10,  # LOW
        "L21_L23":   0.35,  # HIGH: microstructure
        "L24_L29":   0.00,  # skip behavioral
    },
    Regime.RECOVERY.name: {
        "L1_L5":     0.10,  # baseline
        "L6_L10":    0.10,  # baseline
        "L11_L15":   0.20,  # policy
        "L16_L20":   0.25,  # HIGH: macro pressure
        "L21_L23":   0.20,  # HIGH: behavior/emotion
        "L24_L29":   0.15,  # behavioral
    },
}


def compute_regime_layer_weights(regime: str, source: str = "k196") -> Dict[str, float]:
    """Compute weighted layer group allocation for a given regime.

    Args:
        regime: Regime enum name or string
        source: 'k196' or 'k187' or 'average' to blend both

    Returns:
        dict mapping layer group key → float weight
    """
    if source == "average":
        w1 = REGIME_LAYER_WEIGHTS_K196[regime]
        w2 = REGIME_LAYER_WEIGHTS_K187[regime]
        return {k: (w1[k] + w2.get(k, 0.0)) / 2.0 for k in w1}
    matrix = REGIME_LAYER_WEIGHTS_K196 if source == "k196" else REGIME_LAYER_WEIGHTS_K187
    return matrix[regime]


# ============================================================
# 8. HURST EXPONENT REGIME ENHANCEMENT (k196 §Hurst指数)
#    Refines regime decisions with fractal market geometry.
# ============================================================

HURST_THRESHOLDS = {
    "trending_lower": 0.55,   # H > 0.55 → trending persistent
    "mean_reversion_upper": 0.45,  # H < 0.45 → mean reversion
}

# Strategy recommendation by Hurst + Regime combo
HURST_STRATEGY_MAP = {
    (">0.55", "Bull_Trend"):        "trend_following / momentum",
    (">0.55", "Bear_Crisis"):       "caution: crash risk amplified in trends",
    (">0.55", "Sideways"):          "rare but indicates breakout expected",
    (">0.55", "Recovery"):          "trend-following on recovery leg",
    ("<0.45", "Bull_Trend"):        "mixed: bull with mean-reversion pulses",
    ("<0.45", "Bear_Crisis"):       "mean-reversion trading around capitulation",
    ("<0.45", "Sideways"):          "mean_reversion / contrarian",
    ("<0.45", "Recovery"):          "contrarian entry on dips",
    ("[0.45,0.55]", "Bull_Trend"):  "reduce position / add hedge",
    ("[0.45,0.55]", "Bear_Crisis"): "reduce position / increase hedge",
    ("[0.45,0.55]", "Sideways"):    "neutral rotation minimal change",
    ("[0.45,0.55]", "Recovery"):    "wait for clearer direction",
}


# ============================================================
# 9. NMI INFORMATION METRIC (k196 §NMI信息论指标)
#    Cross-asset correlation validation for regime detection.
# ============================================================

NMI_THRESHOLDS = {
    "high_correlation_systemic_risk": 0.7,   # NMI > 0.7 → systemic risk window
    "low_correlation_diversification": 0.3,  # NMI < 0.3 → diversification opportunity
}


# ============================================================
# 10. FACTOR MOMENTUM RULES (k191)
#    Cross-sectional factor momentum: past winners tend to keep winning.
#    Add on top of regime filters. WARNING: factor crowding reverses risk.
# ============================================================

FACTOR_MOMENTUM_PARAMS = {
    "lookback_months": 3,      # Past N months factor ranking
    "forward_months": 3,       # Predict next N months
    "crowding_warning": True,  # Always monitor factor crowding
    "crowding_indicators": [
        "factor_etf_aum_growth_rate",
        "factor_correlation_increase",
        "factor_crowding_score",
    ],
}

# If factor momentum contradicts regime signal, trust regime more
# during Crisis/Bear; trust momentum during Bull/Sideways
FACTOR_MOMENTUM_OVERRIDE_RULE = {
    Regime.BEAR_CRISIS.name: "trust_regime_over_momentum",
    Regime.SIDESWAYS.name:   "trust_regime_over_momentum",
    Regime.BULL_TREND.name:  "trust_momentum_if_aligned_with_regime",
    Regime.RECOVERY.name:    "trust_momentum_if_aligned_with_regime",
}


# ============================================================
# 11. CRISIS HML→SMB传导 SIGNAL (k191 §arXiv 2601.10732)
#    Value(HML) leads Size(SMB) in crisis, lagged 9 days, p<10^-4.
#    Practical signal: when Value factor starts declining, reduce
#    high-Beta small-cap ETF exposure proactively.
# ============================================================

CRISIS_HML_SMB_SIGNAL = {
    "description": "HML Granger-causes SMB in crisis regime",
    "lag_days": 9,
    "p_value_threshold": 1e-4,
    "verification_events": 5,  # validated in 5/6 historical stress events
    "action": "When Value factor begins declining → reduce high-Beta small-cap ETF exposure proactively",
    "leading_factor": "Value",
    "lagging_factor": "Size",
    "applicable_regime": "Crisis",
}


# ============================================================
# 12. CAUSAL INFERENCE NETWORK — k186
#    Granger causality links between macro drivers and industry ETFs.
#    Time-scale dependent: short-term (1 day) = tech/sentiment,
#    medium-term (1-4 weeks) = policy/industry cycle,
#    long-term (monthly) = macro cycles.
# ============================================================

GRANGER_CAUSAL_NETWORK: Dict[str, List[Tuple[str, str, str]]] = {
    "policy_uncertainty": [("NonFerrous_Metals", "medium_term"), ("commodity_etfs", "medium_term")],
    "crude_oil_price":    [("New_Energy", "medium_term"), ("transportation_etfs", "short_term")],
    "semiconductor_index":[("AI_Technology", "short_term"), ("tech_etfs", "medium_term")],
    "dollar_index_dxy":   [("Import_Dependent", "medium_term"), ("forex_etfs", "short_term")],
    "real_estate_data":   [("Banking", "medium_term"), ("financial_etfs", "long_term")],
}

CAUSAL_TIME_SCALE_METHODS = {
    "short_term_1day":    "Granger + Transfer Entropy",
    "medium_term_1_4week":"VAR + causal network",
    "long_term_monthly":  "DML + Synthetic Control",
}

# Factor momentum in crisis — Value → Size lead signal (from k191 + k186 synergy)
CRISIS_LEAD_SIGNAL_CHAIN = {
    "trigger": "Value factor decline detected",
    "granger_lag_days": 9,
    "downstream_action": "Reduce high-Beta small-cap ETF exposure",
    "regime_condition": "Crisis only",
}


# ============================================================
# 13. DRL AGENT REWARD FUNCTION STRUCTURE (k196 §DRL Agent集成方案)
#    Can be wired into pipeline reinforcement learning reward.
# ============================================================

DRL_REWARD_CONSTANTS = {
    "base_reward_type": "sharpe_ratio",           # portfolio_return / max(volatility, 1e-6)
    "position_clip_min": 0.05,                    # min weight per asset
    "position_clip_max": 0.30,                    # max weight per asset
    "tail_risk_penalty": True,
    "tail_risk_drawdown_threshold": None,         # configurable
    "turnover_penalty_weight": 0.1,
    "regime_mismatch_penalty_weight": 0.2,
    "regime_match_bonus_weight": 0.3,
}


# ============================================================
# 14. STATE STREET MARKET REGIMES (k186 additional classification)
#    Alternative 4-state classification beyond HMM labels.
#    Use for cross-validation or as complementary regime view.
# ============================================================

STATE_STREET_REGIMES = {
    "Expansion": {
        "description": "股票上涨、信贷宽松、消费强",
        "best_assets": ["equity", "cyclicals", "credit"],
    },
    "Caution_Decline": {
        "description": "增长放缓但尚未崩溃",
        "best_assets": ["balanced", "quality", "bonds"],
    },
    "Market_Turmoil": {
        "description": "股票暴跌、避险资产大涨",
        "best_assets": ["cash", "treasuries", "gold"],
    },
    "Stagflation": {
        "description": "高通胀+低增长",
        "best_assets": ["commodities", "TIPS", "energy"],
    },
}


# ============================================================
# 15. ETF PORTFOLIO WEIGHT BY REGIME (k187 §实操框架)
#    Example tactical allocation from GitHub regime-allocation-strategy.
#    Backtested 2004-2026: annualized 19.41%, Sharpe 1.22, MaxDD 19.54%.
# ============================================================

REGIME_PORTFOLIO_WEIGHTS_EXAMPLE: Dict[str, Dict[str, float]] = {
    "Low_Vol_Bull": {
        "SPY_or_tech_etf": 0.40,
        "growth_etf": 0.20,
        "momentum_etf": 0.20,
        "bond_etf": 0.20,
    },
    "High_Vol_Bear": {
        "tech_etf": 0.0,
        "growth_etf": 0.0,
        "healthcare_etf": 0.10,
        "bond_etf": 0.50,
        "gold_etf": 0.40,
    },
    "Transition": {
        "reduced_all": True,
        "note": "降低仓位, 减少行业轮动频率",
    },
    "Neutral": {
        "note": "neutral_rotation()",
    },
}


# ============================================================
# 16. BACKTEST VALIDATION DATA (k187)
#    For comparing your system's output against published benchmarks.
# ============================================================

REGIME_ALLOCATION_BACKTEST_BENCHMARK = {
    "period": "2004-2026",
    "assets": ["SPY", "TLT", "GLD"],
    "model": "2-state HMM",
    "annualized_return": 0.1941,
    "sharpe_ratio": 1.22,
    "max_drawdown": 0.1954,
    "benchmark_buy_hold_annualized": None,  # fill with SPY buy-hold benchmark
}


# ============================================================
# 17. REGIME→FACTORS ALIGNED INDUSTRIES QUICK LOOKUP
# ============================================================

def get_regime_best_industries(regime: str, top_n: int = 4) -> List[str]:
    """One-liner: which industries best match current regime?"""
    return regime_aligned_industries(regime, top_n=top_n)


# ============================================================
# 18. REGIME_MULTIPLIERS vs CURRENT EXPECTED FORMAT
# ============================================================

# If your current REGIME_MULTIPLIERS look like:
#   REGIME_MULTIPLIERS = {"Bull": {"all": 1.0}, "Bear": {"all": 0.5}}
# or
#   REGIME_MULTIPLIERS = {"bull": 1.0, "bear": 0.5, "sideways": 0.8, "crisis": 0.3}
#
# Then replace with the dict-of-dicts structure above.
# Old format (example — remove when migrating):
REGIME_MULTIPLIERS_LEGACY_EXAMPLE = {
    "Bull":       {"Value": 0.8, "Growth": 1.2, "Quality": 1.0, "LowVol": 0.6, "Momentum": 1.3, "Size": 1.0},
    "Bear":       {"Value": 1.2, "Growth": 0.6, "Quality": 1.0, "LowVol": 1.2, "Momentum": 0.4, "Size": 0.8},
    "Sideways":   {"Value": 1.0, "Growth": 0.8, "Quality": 1.0, "LowVol": 1.0, "Momentum": 0.7, "Size": 1.0},
    "Crisis":     {"Value": 1.3, "Growth": 0.4, "Quality": 1.2, "LowVol": 1.3, "Momentum": 0.3, "Size": 0.6},
}


# ============================================================
# UNIT TEST SANITY CHECK
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("REGIME-AWARE FACTOR & LAYER WEIGHT CONSTANTS — SELF TEST")
    print("=" * 60)

    # Check regime×factor scores
    print("\n[1] REGIME × FACTOR SCORES:")
    for regime, scores in REGIME_FACTOR_SCORES.items():
        print(f"  {regime}: {scores}")

    # Check apply multipliers
    base = {f: 1/6 for f in FACTOR_NAMES}
    print("\n[2] APPLYING MULTIPLIERS (base equal weight):")
    for regime in Regime:
        adj = apply_regime_multipliers(base, regime.name)
        print(f"  {regime.name}: { {k: round(v,3) for k,v in adj.items()} } sum={sum(adj.values()):.4f}")

    # Check layer weights
    print("\n[3] REGIME × LAYER WEIGHTS (k196):")
    for regime in Regime:
        lw = compute_regime_layer_weights(regime.name, source="k196")
        print(f"  {regime.name}: {lw} sum={sum(lw.values()):.4f}")

    # Check industry alignment
    print("\n[4] BEST INDUSTRIES PER REGIME:")
    for regime in Regime:
        best = get_regime_best_industries(regime.name, top_n=3)
        print(f"  {regime.name}: {best}")

    # Check matrices shape and value ranges
    assert REGIME_FACTOR_MATRIX.shape == (4, 6), "Factor matrix shape mismatch"
    assert np.all(REGIME_FACTOR_MATRIX >= 0) and np.all(REGIME_FACTOR_MATRIX <= 1), "Values out of [0,1]"
    print(f"  Factor matrix row sums: {np.sum(REGIME_FACTOR_MATRIX, axis=1)}")
    print("✓ All sanity checks passed.")
