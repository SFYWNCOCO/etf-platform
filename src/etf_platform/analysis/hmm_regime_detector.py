# -*- coding: utf-8 -*-
"""HMM Regime Detector — 基于多因子阈值的四态市场制度识别。

从 k187-hidden-markov-model-regime-switching.md 提取的规则：

市场制度四态:
    State 0: Low Volatility Bull (低波上涨/趋势期)
        -> 风险资产占优，趋势跟踪策略有效，年化约12%，最大回撤<15%
    State 1: High Volatility Bear (高波下跌/危机期)
        -> 现金/债券/黄金占优，传统股债相关性逆转，分散化失效
    State 2: Neutral Moderate (中性震荡期)
        -> 均值回归策略有效，ETF轮动频率最低
    State 3: Transition (制度转换期/过渡态)
        -> 波动率突然变化，信号最强，最容易误判，需要快速反应

特征向量定义 (与 L15_STATE_SIMILARITY 一致):
    [volatility, momentum, correlation, volume, breadth]

关键规则:
    - 低波牛市: 低波动(<0.45 vol), 正动量(>0.10), 中等相关(0.2-0.5)
    - 高波熊市: 高波动(>0.60), 负动量(<-0.15), 高相关(>0.55)
    - 中性震荡: 中等波动(0.35-0.55), 动量弱(|-0.25~0.10|), 低相关(<0.4), 缩量
    - 转换期: 波动率突变(delta > 0.75), 或同时满足高波+方向不确定

转移矩阵示例 (可配置, 初始值为 Hamilton 1989 + Ang-Bekaert 2002 典型估计):
    [0.97, 0.02, 0.005, 0.005]  # Low→Low / Low→中波/高波/转换
    [0.02, 0.85, 0.10, 0.03]   # 中波→...
    [0.01, 0.05, 0.80, 0.14]   # 高波→...
    [0.03, 0.10, 0.20, 0.67]   # 转换→...

集成: 可替代当前 qvix_regime.py 的简单三阈值规则，提供更丰富的 regime 语义。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Dict, List, Optional, Tuple


# ═══════════════════════════════════════════════════════════
# Enums & Data Classes
# ═══════════════════════════════════════════════════════════


class Regime(IntEnum):
    """HMM 四态编码。用于数组索引和直接比较。"""
    LOW_VOL_BULL = 0
    HIGH_VOL_BEAR = 1
    NEUTRAL_MODERATE = 2
    TRANSITION = 3


# String label map keyed by Regime int index
REGIME_LABELS: Dict[int, str] = {
    Regime.LOW_VOL_BULL: "low_vol_bull",
    Regime.HIGH_VOL_BEAR: "high_vol_bear",
    Regime.NEUTRAL_MODERATE: "neutral_moderate",
    Regime.TRANSITION: "transition",
}

# Chinese name map
REGIME_NAMES_CN: Dict[str, str] = {
    "low_vol_bull": "低波上涨(趋势期)",
    "high_vol_bear": "高波下跌(危机期)",
    "neutral_moderate": "中性震荡期",
    "transition": "制度转换期",
}

REGIME_STRATEGIES: Dict[int, str] = {
    Regime.LOW_VOL_BULL: (
        "风险资产占优，趋势跟踪策略有效。科技/成长/周期优先。"
    ),
    Regime.HIGH_VOL_BEAR: (
        "现金/债券/黄金占优。降低高Beta敞口，防御型配置。"
    ),
    Regime.NEUTRAL_MODERATE: (
        "均值回归策略有效。红利/价值/宽基为主，减少轮动频率。"
    ),
    Regime.TRANSITION: (
        "波动率突变，信号最强也最易误判。降低仓位，等待方向确认。"
    ),
}

ALL_REGIME_INDICES: Tuple[int, ...] = (0, 1, 2, 3)


@dataclass
class RegimeFeatures:
    """市场状态五维特征向量。

    维度说明 (标准化到 [-1, 1] 区间, 与 L15 一致):
        volatility: 波动率 (0=低, 1=高)
        momentum: 动量 (负=下跌, 0=持平, 正=上涨)
        correlation: 相关性 (0=分化, 1=普涨普跌同向)
        volume: 成交量活跃度 (0=地量, 1=巨量)
        breadth: 市场宽度 (0=极少数上涨, 1=广泛上涨)
    """
    volatility: float = 0.25
    momentum: float = 0.10
    correlation: float = 0.30
    volume: float = 0.35
    breadth: float = 0.35

    def vector(self) -> List[float]:
        """返回五维权度列表。"""
        return [self.volatility, self.momentum, self.correlation, self.volume, self.breadth]

    def delta(self) -> float:
        """波动率与动量的综合变动幅度，用于检测制度切换。"""
        return math.sqrt(self.volatility ** 2 + self.momentum ** 2)


@dataclass
class RegimeResult:
    """单个时刻的 regime 判定结果。"""
    regime: Regime
    label: str                      # 人类可读标签, e.g. "low_vol_bull"
    score: float                    # 后验分数 [0, 1]
    certainty: float                # 确信度 [0, 1]
    features: RegimeFeatures
    transition_prob: float          # 下一期仍处该状态的自转移概率
    strategy: str
    recommendations: List[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════
# Transition Matrix (可配置)
# ═══════════════════════════════════════════════════════════

DEFAULT_TRANSITION_MATRIX: List[List[float]] = [
    [0.97, 0.02, 0.005, 0.005],   # LOW_BULL → [LOW_BULL, BEAR, NEUTRAL, TRANS]
    [0.01, 0.80, 0.10, 0.09],     # BEAR → ...
    [0.02, 0.10, 0.85, 0.03],     # NEUTRAL → ...
    [0.03, 0.10, 0.20, 0.67],     # TRANS → ...
]


class HMMTransitionMatrix:
    """转移概率矩阵封装器。

    每行和为1: M[i][j] = P(S_{t+1}=j | S_t=i)

    典型解读:
        M[LOW_BULL][LOW_BULL]=0.97: 低波牛市持续97%的概率
        M[BEAR][BEAR]=0.80: 熊市平均持续 ~6.7 天 (1/(1-0.80))
        M[TRANS][TRANS]=0.67: 转换态最容易留在转换态 (~3.3 天)
    """

    def __init__(self, matrix: Optional[List[List[float]]] = None) -> None:
        self._matrix = matrix if matrix is not None else DEFAULT_TRANSITION_MATRIX
        self._validate()

    def _validate(self) -> None:
        if len(self._matrix) != 4 or any(len(row) != 4 for row in self._matrix):
            raise ValueError("Transition matrix must be 4x4")
        for i, row in enumerate(self._matrix):
            total = sum(row)
            if not (0.99 <= total <= 1.01):
                raise ValueError(f"Row {i} sums to {total:.4f}, expected ~1.0")

    def probability(self, from_regime: Regime, to_regime: Regime) -> float:
        """返回 P(S_{t+1}=to_regime | S_t=from_regime)。"""
        return self._matrix[int(from_regime)][int(to_regime)]

    def self_transition_prob(self, regime: Regime) -> float:
        """返回该状态自我延续概率。"""
        return self.probability(regime, regime)

    def expected_duration(self, regime: Regime) -> float:
        """Expected days in current regime before leaving = 1/(1-P_self)."""
        p = self.self_transition_prob(regime)
        if p >= 1.0:
            return float("inf")
        return round(1.0 / (1.0 - p), 2)

    def next_step_distribution(
        self, current: Regime, smoothing: float = 0.0
    ) -> Dict[str, float]:
        """下一期的 regime 分布，可选加平滑。"""
        dist: Dict[str, float] = {}
        for j in ALL_REGIME_INDICES:
            p = self.probability(current, Regime(j))
            if smoothing > 0:
                p = max(p, smoothing)
            dist[REGIME_LABELS[j]] = round(p, 4)
        return dist

    def update_from_observations(self, history: List[Regime]) -> List[List[float]]:
        """从 regime 历史序列估计转移矩阵（计数归一化）。"""
        counts = [[0.0] * 4 for _ in range(4)]
        for i in range(len(history) - 1):
            fr = int(history[i])
            to = int(history[i + 1])
            counts[fr][to] += 1.0

        result = []
        for row in counts:
            total = sum(row)
            if total == 0:
                result.append([0.25] * 4)
            else:
                result.append([c / total for c in row])
        self._matrix = result
        return result


# ═══════════════════════════════════════════════════════════
# Regime Scoring Functions
# ═══════════════════════════════════════════════════════════

# 各 regime 的特征中心与半径（归一化空间）
REGIME_PROFILES: Dict[Regime, Tuple[List[float], List[float]]] = {
    Regime.LOW_VOL_BULL: ([0.25, 0.65, 0.35, 0.45, 0.60], [0.20, 0.20, 0.15, 0.20, 0.20]),
    Regime.HIGH_VOL_BEAR: ([0.75, -0.40, 0.75, 0.30, 0.15], [0.20, 0.25, 0.15, 0.20, 0.15]),
    Regime.NEUTRAL_MODERATE: ([0.40, 0.05, 0.25, 0.30, 0.35], [0.20, 0.15, 0.20, 0.20, 0.20]),
    Regime.TRANSITION: ([0.55, 0.10, 0.50, 0.55, 0.40], [0.30, 0.30, 0.25, 0.25, 0.25]),
}


def _gaussian_log_score(
    volatility: float,
    momentum: float,
    correlation: float,
    volume: float,
    breadth: float,
    center: List[float],
    spread: List[float],
) -> float:
    """计算高斯似然对数（各维度独立）。"""
    vec = [volatility, momentum, correlation, volume, breadth]
    log_s = 0.0
    for v, c, s in zip(vec, center, spread):
        diff = v - c
        log_s += -0.5 * (diff / s) ** 2 - math.log(s)
    return log_s


def compute_regime_scores(features: RegimeFeatures) -> Dict[Regime, float]:
    """计算四个 regime 的非归一化得分。

    使用高斯核对每个 regime 特征分布打分。
    得分越高 → 当前特征越符合该 regime。

    Args:
        features: 当前市场的五维特征。

    Returns:
        {regime: raw_score} 字典。
    """
    scores: Dict[Regime, float] = {}
    for regime, (center, spread) in REGIME_PROFILES.items():
        scores[regime] = _gaussian_log_score(
            features.volatility, features.momentum,
            features.correlation, features.volume, features.breadth,
            center, spread,
        )
    return scores


def soft_argmax(scores: Dict[Regime, float]) -> Tuple[Regime, float]:
    """Softmax argmax，返回最可能 regime 及其归属概率。"""
    max_val = max(scores.values())
    exp_scores = {k: math.exp(v - max_val) for k, v in scores.items()}
    total = sum(exp_scores.values())
    probabilities = {k: v / total for k, v in exp_scores.items()}

    best = max(probabilities, key=probabilities.get)
    return best, probabilities[best]


def determine_regime(features: RegimeFeatures) -> Regime:
    """仅根据特征硬判定 regime（阈值规则）。

    优先级:
        1. 转换态优先检测: 波动率突变且方向不确定
        2. 高波熊检测: 高波动 + 负动量 + 高相关
        3. 低波牛检测: 低波动 + 正动量 + 正宽度
        4. 否则: 中性震荡

    Args:
        features: 当前市场特征。

    Returns:
        Regime 枚举值。
    """
    vol = features.volatility
    mom = features.momentum
    corr = features.correlation

    # Rule 1: Transition detection — high combined movement magnitude
    if features.delta() > 0.75 or (vol > 0.55 and abs(mom) < 0.25):
        return Regime.TRANSITION

    # Rule 2: High-vol bear
    if vol > 0.60 and mom < -0.15 and corr > 0.55:
        return Regime.HIGH_VOL_BEAR

    # Rule 3: Low-vol bull
    if vol < 0.45 and mom > 0.10 and features.breadth > 0.30:
        return Regime.LOW_VOL_BULL

    # Rule 4: Default to neutral moderate
    return Regime.NEUTRAL_MODERATE


# ═══════════════════════════════════════════════════════════
# Forward Filtering (简化版前向-后向)
# ═══════════════════════════════════════════════════════════

class HMMFilter:
    """简化版前向过滤 (Forward Filtering)。

    用于在已知 regime 概率分布的情况下，结合转移矩阵进行递推更新。
    不训练模型参数（训练需 Baum-Welch），只做 online filtering。

    使用前:
        filter_ = HMMFilter(transitions=...)
        probs = filter_.update(features)
    """

    def __init__(
        self,
        transitions: Optional[HMMTransitionMatrix] = None,
        initial_probs: Optional[List[float]] = None,
    ) -> None:
        self.transitions = transitions or HMMTransitionMatrix()
        n = 4
        if initial_probs is not None:
            self._state_probs = [p / sum(initial_probs) for p in initial_probs]
        else:
            self._state_probs = [0.25] * n

    def update(self, features: RegimeFeatures) -> Dict[str, float]:
        """执行一次预测→观测→归一化的步骤，返回后验状态分布。

        Args:
            features: 当前时刻观测特征。

        Returns:
            {label: posterior_probability}
        """
        # Step 1: Predict using transition matrix
        predicted = [0.0] * 4
        for i in ALL_REGIME_INDICES:
            sp_i = self._state_probs[i]
            for j in ALL_REGIME_INDICES:
                predicted[j] += sp_i * self.transitions.probability(Regime(i), Regime(j))

        # Step 2: Score observations
        scores = compute_regime_scores(features)
        max_score = max(scores.values())
        obs_likelihoods = [
            math.exp(scores[Regime(j)] - max_score) for j in ALL_REGIME_INDICES
        ]

        # Step 3: Combine and normalize
        unnormalized = [predicted[j] * obs_likelihoods[j] for j in ALL_REGIME_INDICES]
        total = sum(unnormalized)
        if total <= 0:
            self._state_probs = [0.25] * 4
        else:
            self._state_probs = [x / total for x in unnormalized]

        result: Dict[str, float] = {}
        for j in ALL_REGIME_INDICES:
            result[REGIME_LABELS[j]] = round(self._state_probs[j], 4)
        return result

    def predict_next(self) -> Dict[str, float]:
        """用转移矩阵预测下一期的 regime 分布。"""
        dist: Dict[str, float] = {}
        for j in ALL_REGIME_INDICES:
            p = sum(
                self._state_probs[i] * self.transitions.probability(Regime(i), Regime(j))
                for i in ALL_REGIME_INDICES
            )
            dist[REGIME_LABELS[j]] = round(p, 4)
        return dist

    @property
    def state_probs(self) -> List[float]:
        return self._state_probs.copy()


# ═══════════════════════════════════════════════════════════
# Regime-Aware Weight Adjustments
# ═══════════════════════════════════════════════════════════

WEIGHT_SHIFTS: Dict[Regime, Dict[str, float]] = {
    Regime.LOW_VOL_BULL: {
        "tech": +0.20,
        "growth": +0.15,
        "cyclicals": +0.10,
        "defense": -0.10,
        "bonds": -0.15,
        "gold": -0.05,
    },
    Regime.HIGH_VOL_BEAR: {
        "tech": -0.20,
        "growth": -0.25,
        "cyclicals": -0.15,
        "defense": +0.15,
        "bonds": +0.20,
        "gold": +0.20,
        "cash": +0.25,
    },
    Regime.NEUTRAL_MODERATE: {
        "tech": +0.05,
        "growth": 0.0,
        "cyclicals": 0.0,
        "defense": +0.10,
        "bonds": +0.05,
        "gold": +0.05,
    },
    Regime.TRANSITION: {
        "tech": -0.05,
        "growth": -0.10,
        "cyclicals": -0.10,
        "defense": +0.10,
        "bonds": +0.05,
        "gold": +0.10,
        "cash": +0.15,
    },
}


def get_weight_shifts(regime: Regime) -> Dict[str, float]:
    """返回某 regime 下的权重调整建议。

    Args:
        regime: 当前市场制度。

    Returns:
        {sector_bucket: weight_adjustment} 正值增配，负值减配。
    """
    return WEIGHT_SHIFTS.get(regime, WEIGHT_SHIFTS[Regime.NEUTRAL_MODERATE]).copy()


# ═══════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════

def _build_recommendations(regime: Regime) -> List[str]:
    """为某 regime 生成投资建议列表。"""
    recs: Dict[Regime, List[str]] = {
        Regime.LOW_VOL_BULL: [
            "趋势跟踪有效，可持有高Beta行业",
            "关注半导体/AI/新能源等成长板块",
            "止损位可适当放宽至 -15%",
        ],
        Regime.HIGH_VOL_BEAR: [
            "降低权益敞口，转向防御资产",
            "黄金、国债、货币基金占比提升至 50%+",
            "等待波动率回落至 1.0 以下再考虑加仓",
            "避免在熊市中抄底个股，优先宽基定投",
        ],
        Regime.NEUTRAL_MODERATE: [
            "均值回归策略有效，避免追涨杀跌",
            "高股息+低波动组合为核心仓位",
            "减少交易频率，降低换手成本",
        ],
        Regime.TRANSITION: [
            "降低仓位，等待方向明确",
            "关注政策面变化与市场成交量信号",
            "不要追涨，也不要恐慌性抛售",
            "准备两套方案（向上突破/向下破位）",
        ],
    }
    return recs.get(regime, [])


def detect_regime(features: RegimeFeatures) -> RegimeResult:
    """主入口: 检测当前市场 regime。

    组合硬判定 (determine_regime) 和软概率 (soft_argmax)，
    当两者冲突时，以硬判定为准但降低 certainty。

    Args:
        features: 当前市场五维特征。

    Returns:
        RegimeResult 包含最终判定、概率、策略建议。
    """
    hard_regime = determine_regime(features)
    scores = compute_regime_scores(features)
    best, prob = soft_argmax(scores)

    final_regime = hard_regime
    certainty = prob
    if hard_regime != best:
        certainty = min(certainty, 0.5)

    self_p = HMMTransitionMatrix().self_transition_prob(final_regime)

    return RegimeResult(
        regime=final_regime,
        label=REGIME_LABELS[int(final_regime)],
        score=round(certainty, 3),
        certainty=round(certainty, 3),
        features=features,
        transition_prob=self_p,
        strategy=REGIME_STRATEGIES[int(final_regime)],
        recommendations=_build_recommendations(final_regime),
    )


def detect_regime_with_filter(
    features: RegimeFeatures,
    filter_: Optional[HMMFilter] = None,
    use_smoothed: bool = True,
) -> RegimeResult:
    """带 forward-filtering 的 regime 检测（推荐用于时间序列）。

    相比纯硬判定，此方法通过历史 regime 分布进行平滑，减少短期噪声导致的误判。

    Args:
        features: 当前市场特征。
        filter_: HMM 过滤器实例。若为 None 则新建。
        use_smoothed: 是否使用平滑后的 regime 而非即时判定。

    Returns:
        RegimeResult。
    """
    if filter_ is None:
        filter_ = HMMFilter()

    posteriors = filter_.update(features)
    best_label = max(posteriors, key=posteriors.get)
    best_idx = {
        "low_vol_bull": Regime.LOW_VOL_BULL,
        "high_vol_bear": Regime.HIGH_VOL_BEAR,
        "neutral_moderate": Regime.NEUTRAL_MODERATE,
        "transition": Regime.TRANSITION,
    }[best_label]
    certainty = posteriors[best_label]

    hard_regime = determine_regime(features)

    if use_smoothed:
        final = best_idx
        if hard_regime == Regime.TRANSITION:
            final = Regime.TRANSITION
    else:
        final = hard_regime

    self_p = HMMTransitionMatrix().self_transition_prob(final)

    return RegimeResult(
        regime=final,
        label=REGIME_LABELS[int(final)],
        score=round(certainty, 3),
        certainty=round(certainty, 3),
        features=features,
        transition_prob=self_p,
        strategy=REGIME_STRATEGIES[int(final)],
        recommendations=_build_recommendations(final),
    )


def features_from_qvix(qvix_value: float) -> RegimeFeatures:
    """从 QVIX 单一指标近似构造 RegimeFeatures。

    QVIX 参考范围:
        <16: complacent (低波)
        16-22: normal
        22-28: cautious (中高波)
        >28: fearful (高波)

    注意: 这是简化映射，完整特征需要从多源数据计算。

    Args:
        qvix_value: 当前 QVIX 值。

    Returns:
        近似的 RegimeFeatures。
    """
    vol_norm = max(0.0, min(1.0, (qvix_value - 12) / 30.0))

    if vol_norm < 0.35:
        mom = 0.20
        corr = 0.25
        vol_raw = 0.20
    elif vol_norm < 0.60:
        mom = 0.0
        corr = 0.35
        vol_raw = 0.45
    else:
        mom = -0.30
        corr = 0.65
        vol_raw = 0.75

    return RegimeFeatures(
        volatility=vol_raw,
        momentum=mom,
        correlation=corr,
        volume=max(0.0, min(1.0, vol_norm * 0.8)),
        breadth=max(0.0, min(1.0, mom + 0.3)),
    )


if __name__ == "__main__":
    test_cases = [
        ("Low-vol bull", RegimeFeatures(volatility=0.2, momentum=0.5, correlation=0.3, volume=0.4, breadth=0.6)),
        ("High-vol bear", RegimeFeatures(volatility=0.8, momentum=-0.5, correlation=0.8, volume=0.2, breadth=0.15)),
        ("Neutral", RegimeFeatures(volatility=0.4, momentum=0.05, correlation=0.25, volume=0.3, breadth=0.35)),
        ("Transition", RegimeFeatures(volatility=0.7, momentum=0.1, correlation=0.5, volume=0.6, breadth=0.4)),
    ]

    print("=== HMM Regime Detection ===")
    for name, feat in test_cases:
        result = detect_regime(feat)
        print(f"\n{name}:")
        print(f"  Regime: {result.regime.name} ({result.label})")
        print(f"  Certainty: {result.certainty:.3f}")
        print(f"  Self-transition P: {result.transition_prob:.2f}")
        print(f"  Strategy: {result.strategy[:40]}")

    print("\n\n=== HMM Filter Rolling Update ===")
    filt = HMMFilter()
    for i in range(5):
        f = RegimeFeatures(volatility=0.3 + i * 0.1, momentum=0.1,
                           correlation=0.3, volume=0.3, breadth=0.4)
        post = filt.update(f)
        best_label = max(post, key=post.get)
        best_idx = {
            "low_vol_bull": 0, "high_vol_bear": 1,
            "neutral_moderate": 2, "transition": 3,
        }[best_label]
        print(f"Step {i+1}: best={best_idx} cert={post[best_label]:.3f}")
