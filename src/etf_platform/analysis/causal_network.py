# -*- coding: utf-8 -*-
"""Causal Network — Granger因果 + 结构断点 + 多尺度信号周期优化。

从 k186-causal-inference-financial-markets.md 提取的规则：

核心概念:
    - Granger因果: X的过去值能改善对Y的预测 → X Granger因果于Y
    - VAR(向量自回归): 多个时间序列同时建模彼此的滞后影响
    - 传递熵(Transfer Entropy): 信息论意义上的因果方向，检测非线性因果关系
    - 结构断点: 某个时间点系统行为规则发生根本改变
    - DML(双重机器学习): 消除混淆因子后的因果估计
    - 合成控制法: 构造"虚拟对照组"评估干预效果

多尺度因果框架 (Ataei et al. 2025):
    短期(日):   Granger + TE       → 情绪→量价
    中期(周):   VAR + 传递熵        → 产业链→政策
    长期(月):   DML + SC            → 宏观→行业 / 政策→GDP→需求

关键规则:
    - 不同时间尺度的因果链不同！可据此优化信号周期
    - 当检测到结构断点时，市场制度可能已切换，应调整L层权重配置
    - 建议在L29a层引入regime-aware机制

集成: 供信号周期优化、事件归因、regime-aware layer weighting 使用。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


# ═══════════════════════════════════════════════════════════
# Enums & Data Classes
# ═══════════════════════════════════════════════════════════


class TimeScale(str, Enum):
    """分析时间尺度。"""
    SHORT_TERM = "short_term"      # 短期（日级，1-5交易日）
    MEDIUM_TERM = "medium_term"    # 中期（周级，1-4周）
    LONG_TERM = "long_term"        # 长期（月级，1-12月）


class CausalMethod(str, Enum):
    """因果推断方法。"""
    GRANGER = "granger"                    # Granger因果检验
    TRANSFER_ENTROPY = "transfer_entropy"  # 传递熵
    VAR = "var"                            # 向量自回归
    DML = "dml"                            # 双重机器学习
    SYNTHETIC_CONTROL = "synthetic_control"# 合成控制法


class SignalPhase(str, Enum):
    """信号周期阶段。"""
    PRE_TRIGGER = "pre_trigger"
    TRIGGER = "trigger"
    POST_TRIGGER = "post_trigger"


@dataclass
class CausalEdge:
    """因果网络中的有向边。"""
    source: str
    target: str
    direction: int = 1
    strength: float = 0.5
    confidence: float = 0.7
    time_scale: TimeScale = TimeScale.SHORT_TERM
    significance: float = 0.05
    method: CausalMethod = CausalMethod.GRANGER
    lag_days: int = 3
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "direction": self.direction,
            "strength": self.strength,
            "confidence": self.confidence,
            "time_scale": self.time_scale.value,
            "significance": self.significance,
            "method": self.method.value,
            "lag_days": self.lag_days,
            "description": self.description,
        }


@dataclass
class CausalNode:
    """因果网络中的节点（变量/资产/因子）。"""
    name: str
    node_type: str             # factor / sector / macro / event / sentiment / price
    time_scale: TimeScale = TimeScale.MEDIUM_TERM
    description: str = ""


@dataclass
class GrangerResult:
    """单组 Granger 因果检验结果。"""
    source: str
    target: str
    statistic: float           # F-statistic 或 Wald statistic
    p_value: float
    is_causal: bool            # p < threshold
    direction: int             # 1=source→target, -1=target→source, 0=bidirectional
    lag: int                   # 最优滞后期
    time_scale: TimeScale
    effect_size: float = 0.0   # R² improvement


@dataclass
class BreakpointResult:
    """结构断点检测结果。"""
    breakpoint_date: str
    variable: str
    test_stat: float
    critical_value: float
    is_breakpoint: bool
    regime_before: int
    regime_after: int
    pre_mean: float
    post_mean: float
    magnitude: float


@dataclass
class CounterfactualResult:
    """反事实分析结果。"""
    treatment: str
    control: str
    actual_effect: float
    counterfactual_effect: float
    causal_effect: float
    confidence_interval: Tuple[float, float]
    synthetic_weights: Dict[str, float]


@dataclass
class CausalNetworkAnalysis:
    """完整的因果网络分析输出。"""
    edges: List[CausalEdge] = field(default_factory=list)
    nodes: List[CausalNode] = field(default_factory=list)
    signal_periods: Dict[str, SignalPhase] = field(default_factory=dict)
    breakpoints: List[BreakpointResult] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    summary: str = ""


# ═══════════════════════════════════════════════════════════
# Pre-built Causal Network Tables (from k186)
# ═══════════════════════════════════════════════════════════

DEFAULT_CAUSAL_CHAINS: List[CausalEdge] = [
    # --- 短期(日级) 情绪→量价 ---
    CausalEdge(
        source="新闻情绪",
        target="半导体ETF",
        direction=1,
        strength=0.65,
        confidence=0.7,
        time_scale=TimeScale.SHORT_TERM,
        significance=0.01,
        method=CausalMethod.GRANGER,
        lag_days=1,
        description="新闻情绪(半导体相关) → 半导体ETF价格异动",
    ),
    CausalEdge(
        source="成交量",
        target="AI ETF",
        direction=1,
        strength=0.60,
        confidence=0.75,
        time_scale=TimeScale.SHORT_TERM,
        significance=0.02,
        method=CausalMethod.TRANSFER_ENTROPY,
        lag_days=1,
        description="异常放量 → AI板块资金流入",
    ),
    CausalEdge(
        source="VIX恐慌指数",
        target="黄金ETF",
        direction=-1,
        strength=0.70,
        confidence=0.8,
        time_scale=TimeScale.SHORT_TERM,
        significance=0.001,
        method=CausalMethod.GRANGER,
        lag_days=1,
        description="VIX飙升 → 避险资金涌入黄金(反向)",
    ),
    CausalEdge(
        source="政策不确定性指数",
        target="有色金属ETF",
        direction=1,
        strength=0.55,
        confidence=0.65,
        time_scale=TimeScale.SHORT_TERM,
        significance=0.05,
        method=CausalMethod.GRANGER,
        lag_days=2,
        description="EPU上升 → 有色金属波动加剧",
    ),

    # --- 中期(周级) 产业链→政策 ---
    CausalEdge(
        source="原油价格",
        target="新能源ETF",
        direction=1,
        strength=0.50,
        confidence=0.7,
        time_scale=TimeScale.MEDIUM_TERM,
        significance=0.03,
        method=CausalMethod.VAR,
        lag_days=5,
        description="原油价格↑ → 新能源替代逻辑强化 → 新能源ETF上涨",
    ),
    CausalEdge(
        source="半导体指数",
        target="AI ETF",
        direction=1,
        strength=0.75,
        confidence=0.85,
        time_scale=TimeScale.MEDIUM_TERM,
        significance=0.001,
        method=CausalMethod.GRANGER,
        lag_days=5,
        description="半导体周期领先 → AI板块后续表现",
    ),
    CausalEdge(
        source="产业政策公告",
        target="新能源ETF",
        direction=1,
        strength=0.60,
        confidence=0.75,
        time_scale=TimeScale.MEDIUM_TERM,
        significance=0.01,
        method=CausalMethod.GRANGER,
        lag_days=3,
        description="产业补贴/政策公告 → 新能源板块响应",
    ),
    CausalEdge(
        source="美元指数",
        target="进口依赖型ETF",
        direction=1,
        strength=0.45,
        confidence=0.6,
        time_scale=TimeScale.MEDIUM_TERM,
        significance=0.05,
        method=CausalMethod.TRANSFER_ENTROPY,
        lag_days=5,
        description="美元走强 → 人民币贬值 → 进口依赖行业成本↑",
    ),
    CausalEdge(
        source="房地产销售数据",
        target="银行ETF",
        direction=1,
        strength=0.55,
        confidence=0.7,
        time_scale=TimeScale.MEDIUM_TERM,
        significance=0.02,
        method=CausalMethod.GRANGER,
        lag_days=7,
        description="房地产数据变化 → 银行资产质量预期",
    ),

    # --- 长期(月级) 宏观→行业 / 政策→GDP→需求 ---
    CausalEdge(
        source="货币政策(M2)",
        target="宽基ETF",
        direction=1,
        strength=0.65,
        confidence=0.8,
        time_scale=TimeScale.LONG_TERM,
        significance=0.005,
        method=CausalMethod.DML,
        lag_days=21,
        description="货币宽松 → 全市场流动性改善 → 宽基上涨",
    ),
    CausalEdge(
        source="财政政策支出",
        target="基建ETF",
        direction=1,
        strength=0.70,
        confidence=0.85,
        time_scale=TimeScale.LONG_TERM,
        significance=0.001,
        method=CausalMethod.SYNTHETIC_CONTROL,
        lag_days=21,
        description="财政基建投资↑ → 基建行业订单↑",
    ),
    CausalEdge(
        source="利率(LPR)",
        target="成长股ETF",
        direction=-1,
        strength=0.60,
        confidence=0.75,
        time_scale=TimeScale.LONG_TERM,
        significance=0.01,
        method=CausalMethod.GRANGER,
        lag_days=21,
        description="利率↓ → 成长股折现率↓ → 估值扩张(反向)",
    ),
    CausalEdge(
        source="消费者信心指数",
        target="消费ETF",
        direction=1,
        strength=0.50,
        confidence=0.7,
        time_scale=TimeScale.LONG_TERM,
        significance=0.03,
        method=CausalMethod.DML,
        lag_days=21,
        description="消费信心改善 → 消费需求↑ → 消费板块受益",
    ),
    CausalEdge(
        source="PMI制造业指数",
        target="周期/资源ETF",
        direction=1,
        strength=0.65,
        confidence=0.75,
        time_scale=TimeScale.LONG_TERM,
        significance=0.01,
        method=CausalMethod.VAR,
        lag_days=21,
        description="PMI上行 → 工业活动扩张 → 周期品需求↑",
    ),
]


METHOD_BY_TIMESCALE: Dict[TimeScale, List[CausalMethod]] = {
    TimeScale.SHORT_TERM: [CausalMethod.GRANGER, CausalMethod.TRANSFER_ENTROPY],
    TimeScale.MEDIUM_TERM: [CausalMethod.VAR, CausalMethod.TRANSFER_ENTROPY, CausalMethod.GRANGER],
    TimeScale.LONG_TERM: [CausalMethod.DML, CausalMethod.SYNTHETIC_CONTROL, CausalMethod.GRANGER],
}


SIGNAL_PERIOD_RULES: Dict[TimeScale, Dict[str, float]] = {
    TimeScale.SHORT_TERM: {
        "min_granger_strength": 0.40,
        "max_p_value": 0.10,
        "optimal_lag_days": 1,
        "signal_window_days": 5,
        "turnover_budget": 0.05,
        "filter_noise": True,
    },
    TimeScale.MEDIUM_TERM: {
        "min_granger_strength": 0.50,
        "max_p_value": 0.05,
        "optimal_lag_days": 5,
        "signal_window_days": 20,
        "turnover_budget": 0.15,
        "filter_noise": False,
    },
    TimeScale.LONG_TERM: {
        "min_granger_strength": 0.60,
        "max_p_value": 0.02,
        "optimal_lag_days": 21,
        "signal_window_days": 60,
        "turnover_budget": 0.25,
        "filter_noise": False,
    },
}


# Regime-aware L-layer weight matrix from k187
REGIME_LAYER_WEIGHTS: Dict[int, Dict[str, float]] = {
    0: {"L1-L5基本面": 0.35, "L11-L15技术面": 0.30, "L16-L20宏观": 0.10,
        "L21-L23微观": 0.10, "L24-L29行为": 0.15},
    1: {"L16-L20宏观风险": 0.30, "L24-L29行为": 0.25, "L1-L5基本面": 0.15,
        "L6-L10产业": 0.10, "L11-L15技术面": 0.10, "L21-L23微观": 0.10},
    2: {"L6-L10产业": 0.25, "L21-L23微观": 0.25, "L1-L5基本面": 0.20,
        "L16-L20宏观": 0.10, "L11-L15技术面": 0.10, "L24-L29行为": 0.10},
    3: {"L24-L29情绪": 0.25, "L16-L20宏观压力": 0.25, "L1-L5基本面": 0.15,
        "L6-L10产业": 0.10, "L11-L15技术面": 0.15, "L21-L23微观": 0.10},
}


# ═══════════════════════════════════════════════════════════
# Granger Causality Test (simplified)
# ═══════════════════════════════════════════════════════════

class GrangerCausalTest:
    """Granger 因果检验实现。

    用于量化"X的过去值是否能改善对Y的预测"。

    简化版：基于 F-test of restricted vs unrestricted VAR。
    实际生产中可用 statsmodels.tsa.vector_ar.var_model.VAR。
    """

    def __init__(
        self,
        max_lag: int = 5,
        significance_threshold: float = 0.05,
        aic_bic: bool = True,
    ) -> None:
        self.max_lag = max_lag
        self.significance_threshold = significance_threshold
        self.aic_bic = aic_bic

    @staticmethod
    def _optimal_lag_aicbic(data: List[List[float]], max_lag: int) -> int:
        """根据 AIC/BIC 选择最优滞后期（简化实现）。"""
        best_lag = 1
        best_score = float("inf")
        n = len(data[0])

        for lag in range(1, min(max_lag + 1, n)):
            mse = 0.0
            for i in range(lag, n):
                diff = data[1][i] - 0.5 * (data[1][i - 1] + data[1][i - lag])
                mse += diff ** 2
            mse /= max(1, n - lag)
            bic_penalty = (math.log(max(1, n)) * lag) / max(1, n)
            score = mse * (1.0 + bic_penalty)
            if score < best_score:
                best_score = score
                best_lag = lag

        return best_lag

    def run(
        self,
        x: List[float],
        y: List[float],
        time_scale: TimeScale = TimeScale.SHORT_TERM,
        source_label: str = "",
        target_label: str = "",
    ) -> GrangerResult:
        """执行 Granger 因果检验。

        Args:
            x: 候选原因变量的时间序列。
            y: 目标变量的时间序列。
            time_scale: 时间尺度。
            source_label: 原因变量标签。
            target_label: 目标变量标签。

        Returns:
            GrangerResult 检验结果。
        """
        max_len = min(len(x), len(y))
        if max_len < max(self.max_lag + 1, 10):
            return GrangerResult(
                source=source_label or "X", target=target_label or "Y",
                statistic=0.0, p_value=1.0, is_causal=False,
                direction=0, lag=1, time_scale=time_scale, effect_size=0.0,
            )

        x = x[:max_len]
        y = y[:max_len]

        lag = self._optimal_lag_aicbic([x, y], self.max_lag)

        n = len(y)
        residuals_base = 0.0
        residuals_full = 0.0

        for i in range(lag, n):
            base_pred = 0.5 * y[i - 1] + 0.5 * y[i - lag]
            residuals_base += (y[i] - base_pred) ** 2

            x_contribution = sum(x[i - k] * (0.5 ** k) for k in range(1, lag + 1))
            full_pred = 0.4 * y[i - 1] + 0.3 * x_contribution / max(lag, 1) + 0.3 * y[i - lag]
            residuals_full += (y[i] - full_pred) ** 2

        residuals_base /= max(1, n - lag)
        residuals_full /= max(1, n - lag - lag)

        if residuals_full <= 0:
            f_stat = float("inf")
            p_value = 0.0
        else:
            f_stat = ((residuals_base - residuals_full) * max(1, n - 2 * lag)) / (
                residuals_full * lag
            )
            f_stat = max(0.0, f_stat)
            p_value = self._f_pvalue_approx(f_stat, lag, max(1, n - 2 * lag))

        improvement = max(0.0, 1.0 - residuals_full / max(residuals_base, 1e-10))

        direction = 1 if f_stat > 0 else 0

        return GrangerResult(
            source=source_label or "X", target=target_label or "Y",
            statistic=round(f_stat, 4), p_value=round(min(p_value, 1.0), 6),
            is_causal=p_value < self.significance_threshold, direction=direction,
            lag=lag, time_scale=time_scale, effect_size=round(improvement, 4),
        )

    @staticmethod
    def _f_pvalue_approx(f_stat: float, df1: int, df2: int) -> float:
        """F分布 p-value 近似。"""
        if f_stat <= 0:
            return 1.0
        x = df2 / (df2 + df1 * f_stat)
        a = df2 / 2.0
        b = df1 / 2.0
        z = -0.5 * (a + b) * (1 - x) if x < 1 else 0.0
        return max(0.0, min(1.0, math.exp(-z)))


# ═══════════════════════════════════════════════════════════
# Structural Breakpoint Detection
# ═══════════════════════════════════════════════════════════

class StructuralBreakDetector:
    """结构断点检测器。

    用于识别"某个时间点系统行为规则发生根本改变"。
    基于 t-test 的简单实现，适用于政策事件后收益率分布变化检测。
    """

    def __init__(
        self,
        significance: float = 0.05,
        min_pre_post_samples: int = 10,
    ) -> None:
        self.significance = significance
        self.min_samples = min_pre_post_samples

    def detect(
        self,
        returns: List[float],
        candidate_dates: Optional[List[str]] = None,
        variable_label: str = "ETF",
        dates: Optional[List[str]] = None,
    ) -> List[BreakpointResult]:
        """在给定候选断点附近寻找统计显著的结构性变化。"""
        results: List[BreakpointResult] = []

        if dates is None or candidate_dates is None:
            return results

        for cand_date in candidate_dates:
            if cand_date not in dates:
                continue

            idx = dates.index(cand_date)
            pre_returns = returns[:idx]
            post_returns = returns[idx:]

            if len(pre_returns) < self.min_samples or len(post_returns) < self.min_samples:
                continue

            pre_mean = sum(pre_returns) / len(pre_returns)
            post_mean = sum(post_returns) / len(post_returns)

            pre_var = sum((r - pre_mean) ** 2 for r in pre_returns) / max(1, len(pre_returns) - 1)
            post_var = sum((r - post_mean) ** 2 for r in post_returns) / max(1, len(post_returns) - 1)

            sp = math.sqrt((pre_var + post_var) / 2) if (pre_var + post_var) > 0 else 0
            if sp == 0:
                continue

            se = sp * math.sqrt(1.0 / len(pre_returns) + 1.0 / len(post_returns))
            t_stat = abs(post_mean - pre_mean) / se

            critical = 1.96

            is_break = t_stat > critical

            results.append(BreakpointResult(
                breakpoint_date=cand_date,
                variable=variable_label,
                test_stat=round(t_stat, 4),
                critical_value=critical,
                is_breakpoint=is_break,
                regime_before=0 if pre_mean >= 0 else 1,
                regime_after=0 if post_mean >= 0 else 1,
                pre_mean=round(pre_mean, 6),
                post_mean=round(post_mean, 6),
                magnitude=round(abs(post_mean - pre_mean), 6),
            ))

        results.sort(key=lambda r: r.magnitude, reverse=True)
        return results


# ═══════════════════════════════════════════════════════════
# Policy Event Impact Analyzer (Event Study style)
# ═══════════════════════════════════════════════════════════

def high_freq_event_study(
    policy_event_date: str,
    etf_returns: Dict[str, List[float]],
    all_dates: List[str],
    event_index: int,
    pre_window: int = -3,
    post_window: int = 3,
) -> Dict[str, Dict[str, float]]:
    """高频事件研究：估计各行业ETF对政策事件的反应敏感度。

    基于 k192 中的"高频事件研究方法"：
        回归: ETF_return = α + β * surprise + ε
        - β > 0且显著: ETF正面响应政策
        - β < 0且显著: ETF负面响应政策
        - β不显著: 无明确传导
    """
    results: Dict[str, Dict[str, float]] = {}

    for etf_code, returns in etf_returns.items():
        n = min(len(returns), len(all_dates))
        if event_index + post_window >= n or event_index + pre_window < 0:
            continue

        pre_returns = returns[event_index + pre_window:event_index]
        if not pre_returns:
            continue

        avg_daily = sum(pre_returns) / len(pre_returns)
        window_size = post_window + abs(pre_window) + 1
        surprise = sum(returns[event_index:event_index + post_window + 1]) - avg_daily * window_size

        if abs(surprise) < 1e-10:
            beta = 0.0
        else:
            window_return = sum(returns[event_index:event_index + post_window + 1])
            beta = window_return / surprise if abs(surprise) > 1e-10 else 0.0

        t_stat = abs(beta) * math.sqrt(max(window_size, 1))
        p_val = max(0.001, 1.0 / (1.0 + t_stat))

        results[etf_code] = {
            "beta": round(beta, 4),
            "p_value": round(p_val, 4),
            "is_significant": p_val < 0.05,
            "surprise": round(surprise, 6),
        }

    return results


# ═══════════════════════════════════════════════════════════
# Signal Cycle Optimizer (Granger-optimized)
# ═══════════════════════════════════════════════════════════

def optimize_signal_cycle(
    etf_sector: str,
    causal_network: Optional[List[CausalEdge]] = None,
    current_regime: Optional[int] = None,
) -> Dict[str, Any]:
    """基于 Granger 因果网络的信号周期优化。

    核心思想 (k186):
        - 不同时间尺度的因果链不同，可据此优化信号周期
        - 短期信号应关注情绪→量价驱动
        - 中期信号应关注产业链→政策驱动
        - 长期信号应关注宏观→行业驱动
    """
    network = causal_network or DEFAULT_CAUSAL_CHAINS

    relevant_edges: List[CausalEdge] = []
    for edge in network:
        if (
            etf_sector in edge.source or etf_sector in edge.target
            or "ETF" in edge.target
            or etf_sector.replace("/", "") in edge.source.replace("/", "")
        ):
            relevant_edges.append(edge)

    signal_config: Dict[str, Any] = {}
    for scale in TimeScale:
        rules = SIGNAL_PERIOD_RULES.get(scale, {})
        scale_edges = [e for e in relevant_edges if e.time_scale == scale]

        if scale_edges:
            best_edge = max(scale_edges, key=lambda e: e.strength * e.confidence)
            signal_config[scale.value] = {
                "primary_driver": f"{best_edge.source} → {best_edge.target}",
                "driving_strength": best_edge.strength,
                "driving_confidence": best_edge.confidence,
                "optimal_lag_days": best_edge.lag_days,
                "signal_window_days": rules.get("signal_window_days", 20),
                "min_strength_threshold": rules.get("min_granger_strength", 0.5),
                "max_p_value": rules.get("max_p_value", 0.05),
                "active_signals": [e.to_dict() for e in scale_edges if e.strength >= rules.get("min_granger_strength", 0.5)],
            }
        else:
            signal_config[scale.value] = {
                "primary_driver": "no_data",
                "driving_strength": 0.0,
                "driving_confidence": 0.0,
                "optimal_lag_days": rules.get("optimal_lag_days", 5),
                "signal_window_days": rules.get("signal_window_days", 20),
                "min_strength_threshold": rules.get("min_granger_strength", 0.5),
                "max_p_value": rules.get("max_p_value", 0.05),
                "active_signals": [],
            }

    best_scale = max(
        signal_config.keys(),
        key=lambda s: signal_config[s]["driving_strength"] * signal_config[s]["driving_confidence"],
    )

    signal_config["recommended_primary_scale"] = best_scale
    signal_config["all_scales_total_strength"] = sum(
        signal_config[s]["driving_strength"] * signal_config[s]["driving_confidence"]
        for s in signal_config if s != "recommended_primary_scale"
    )

    if current_regime is not None and current_regime in REGIME_LAYER_WEIGHTS:
        regime_weights = REGIME_LAYER_WEIGHTS[current_regime]
        signal_config["regime"] = current_regime
        signal_config["regime_layer_weights"] = regime_weights
        signal_config["regime_strategy"] = _get_regime_strategy_cn(current_regime)

    return signal_config


def get_regime_aware_layer_weights(regime: int) -> Dict[str, float]:
    """根据市场制度返回 L 层权重配置。

    Args:
        regime: 市场制度索引 (0=低波牛, 1=高波熊, 2=中性震荡, 3=转换期)。

    Returns:
        {layer_group: weight} 字典。
    """
    return REGIME_LAYER_WEIGHTS.get(regime, REGIME_LAYER_WEIGHTS[2]).copy()


def _get_regime_strategy_cn(regime: int) -> str:
    """Regime 对应的策略建议。"""
    strategies = {
        0: "风险资产占优，趋势跟踪有效",
        1: "防御为主，降低权益敞口",
        2: "均值回归，减少交易频率",
        3: "降低仓位，等待方向确认",
    }
    return strategies.get(regime, "未知状态")


# ═══════════════════════════════════════════════════════════
# Synthetic Control / Counterfactual Estimation
# ═══════════════════════════════════════════════════════════

def estimate_counterfactual(
    treated_returns: List[float],
    control_returns: List[List[float]],
    pre_period: bool = True,
) -> CounterfactualResult:
    """合成控制法: 用未被政策影响的ETF构造"反事实对照组"。

    用于剥离市场整体波动后，提取政策的真实效应。
    """
    if not control_returns or not treated_returns:
        return CounterfactualResult(
            treatment="", control="",
            actual_effect=0.0, counterfactual_effect=0.0, causal_effect=0.0,
            confidence_interval=(0.0, 0.0), synthetic_weights={},
        )

    min_len = min(len(treated_returns), min(len(c) for c in control_returns))

    weights = [1.0 / len(control_returns)] * len(control_returns)
    if pre_period and min_len > 5:
        ref = treated_returns[:min_len]
        scored = []
        for i, ctrl in enumerate(control_returns):
            ctrl_slice = ctrl[:min_len]
            corr = 0.0
            mean_ref = sum(ref) / len(ref)
            mean_ctrl = sum(ctrl_slice) / len(ctrl_slice)
            cov = sum((ref[j] - mean_ref) * (ctrl_slice[j] - mean_ctrl) for j in range(min_len))
            var_ref = sum((r - mean_ref) ** 2 for r in ref)
            var_ctrl = sum((c - mean_ctrl) ** 2 for c in ctrl_slice)
            denom = math.sqrt(var_ref * var_ctrl)
            if denom > 0:
                corr = cov / denom
            scored.append((i, abs(corr)))
        scored.sort(key=lambda x: x[1], reverse=True)
        total_corr = sum(c for _, c in scored)
        if total_corr > 0:
            weights = [0.0] * len(control_returns)
            for rank, (idx, corr) in enumerate(scored):
                weights[idx] = (len(scored) - rank) * corr / total_corr
        else:
            weights = [1.0 / len(control_returns)] * len(control_returns)

    synthetic_returns = [
        sum(w * c[i] for w, c in zip(weights, control_returns))
        for i in range(min_len)
    ]

    actual_avg = sum(treated_returns[:min_len]) / min_len
    counterfactual_avg = sum(synthetic_returns) / min_len
    causal_effect = actual_avg - counterfactual_avg

    residuals = [treated_returns[i] - synthetic_returns[i] for i in range(min_len)]
    std_err = math.sqrt(sum(r ** 2 for r in residuals) / max(1, len(residuals) - 1)) if residuals else 0.0
    ci_half_width = 1.96 * std_err * math.sqrt(min_len) / max(1, min_len)

    synth_weights = {
        f"control_{i}": round(w, 4)
        for i, w in enumerate(weights) if w > 0.01
    }

    return CounterfactualResult(
        treatment="treated_etf",
        control=f"synthetic({len(control_returns)}_controls)",
        actual_effect=round(actual_avg, 6),
        counterfactual_effect=round(counterfactual_avg, 6),
        causal_effect=round(causal_effect, 6),
        confidence_interval=(
            round(causal_effect - ci_half_width, 6),
            round(causal_effect + ci_half_width, 6),
        ),
        synthetic_weights=synth_weights,
    )


# ═══════════════════════════════════════════════════════════
# Transfer Entropy (nonlinear causality)
# ═══════════════════════════════════════════════════════════

def transfer_entropy(
    source_series: List[float],
    target_series: List[float],
    embedding_dim: int = 2,
) -> float:
    """计算传递熵 (Transfer Entropy)。

    衡量 source 的过去对 target 的未来信息的"额外贡献"，
    能捕捉非线性因果关系（比普通 Granger 更强）。

    Args:
        source_series: 源序列（如新闻情绪评分）。
        target_series: 目标序列（如ETF收益率）。
        embedding_dim: 嵌入维度（延迟步数）。

    Returns:
        传递熵值 TE(X→Y) ≥ 0，越大表示 X 对 Y 的信息贡献越大。
    """
    min_len = min(len(source_series), len(target_series))
    if min_len < embedding_dim + 2:
        return 0.0

    source = source_series[:min_len]
    target = target_series[:min_len]

    def binarize(series: List[float]) -> List[int]:
        sorted_vals = sorted(set(series))
        if not sorted_vals:
            return [0] * len(series)
        # FIX 2026-08-01: len//2 on even-length sets (e.g. [0,1]) picks the UPPER
        # median (1), making `v > 1` always False → every binary series became all
        # zeros and transfer_entropy was always 0. Use lower median (len-1)//2 so
        # v > median correctly separates the two halves.
        median = sorted_vals[(len(sorted_vals) - 1) // 2]
        return [1 if v > median else 0 for v in series]

    s_bin = binarize(source)
    t_bin = binarize(target)

    n = len(s_bin) - embedding_dim
    if n < 2:
        return 0.0

    counts = {
        "s_prev_t_curr": 0,   # P(T_curr=1 & S_prev=1)
        "s_prev": 0,          # P(S_prev=1)
        "t_prev_t_curr": 0,   # P(T_curr=1 & T_prev=1)
        "t_prev": 0,          # P(T_prev=1)
    }

    for i in range(n):
        t_curr = t_bin[i]
        t_prev = t_bin[i + embedding_dim]
        s_prev = s_bin[i + embedding_dim]

        # FIX 2026-08-01: conditional counts were unconditional (all == n),
        # making p_t_given_s == 1.0 always and corrupting the transfer entropy.
        if s_prev == 1:
            counts["s_prev"] += 1
            if t_curr == 1:
                counts["s_prev_t_curr"] += 1
        if t_prev == 1:
            counts["t_prev"] += 1
            if t_curr == 1:
                counts["t_prev_t_curr"] += 1

    # P(T_curr=1 | S_prev=1): how much the past source predicts current target
    p_t_given_s = counts["s_prev_t_curr"] / counts["s_prev"] if counts["s_prev"] > 0 else 0
    # P(T_curr=1 | T_prev=1): baseline self-persistence of the target
    p_t_given_both = counts["t_prev_t_curr"] / counts["t_prev"] if counts["t_prev"] > 0 else 0

    # FIX 2026-08-01: previously returned 0 whenever p_t_given_s or p_t_given_both
    # was 0, which killed valid TE in alternating sequences. Zero probability is
    # meaningful information (perfect predictability / anti-persistence); the eps
    # clamps in the formula below handle division safely. Only degenerate cases
    # (no data at all) fall back to 0.
    EPS = 1e-10
    if counts["s_prev"] == 0 and counts["t_prev"] == 0:
        return 0.0
    p_s = min(1.0 - EPS, max(EPS, p_t_given_s))
    p_b = min(1.0 - EPS, max(EPS, p_t_given_both))

    te = p_s * math.log2(p_s / p_b) + (1 - p_s) * math.log2((1 - p_s) / (1 - p_b))

    return max(0.0, te)


# ═══════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════

def analyze_causal_network(
    sectors: List[str],
    regime: int = 2,
) -> CausalNetworkAnalysis:
    """综合分析因果网络，生成信号配置与投资建议。

    Args:
        sectors: 待分析的行业列表。
        regime: 当前市场制度 (0-3)。

    Returns:
        CausalNetworkAnalysis 完整分析结果。
    """
    analysis = CausalNetworkAnalysis()

    for sector in sectors:
        related_edges = [
            e for e in DEFAULT_CAUSAL_CHAINS
            if sector in e.target or sector in e.source
        ]
        analysis.edges.extend(related_edges)
        analysis.nodes.append(CausalNode(
            name=sector, node_type="sector",
            description=f"{sector} 相关因果链",
        ))

    seen = set()
    unique_edges = []
    for edge in analysis.edges:
        key = (edge.source, edge.target, edge.time_scale)
        if key not in seen:
            seen.add(key)
            unique_edges.append(edge)
    analysis.edges = unique_edges

    for sector in sectors:
        config = optimize_signal_cycle(sector, DEFAULT_CAUSAL_CHAINS, regime)
        analysis.signal_periods[sector] = config.get("recommended_primary_scale", TimeScale.MEDIUM_TERM).value

    if regime in REGIME_LAYER_WEIGHTS:
        weights = REGIME_LAYER_WEIGHTS[regime]
        strategy_map = {
            0: "风险资产占优，趋势跟踪有效",
            1: "防御为主，降低权益敞口",
            2: "均值回归，减少交易频率",
            3: "降低仓位，等待方向确认",
        }
        analysis.recommendations.append(f"当前市场制度 regime={regime}: {strategy_map.get(regime, '')}")
        for layer, weight in weights.items():
            analysis.recommendations.append(f"  {layer}: 权重 {weight:.0%}")

    strong_edges = [e for e in analysis.edges if e.strength >= 0.6]
    analysis.summary = (
        f"Causal analysis for {len(sectors)} sector(s): "
        f"{len(analysis.edges)} edges found, {len(strong_edges)} strong links."
    )

    return analysis


if __name__ == "__main__":
    print("=== Causal Network Analysis ===\n")

    print("--- Signal Cycle Optimization for Semiconductor ---")
    semicolon_config = optimize_signal_cycle("半导体", current_regime=0)
    for key, value in semicolon_config.items():
        if isinstance(value, dict):
            print(f"  {key}:")
            for sk, sv in value.items():
                print(f"    {sk}: {sv}")
        else:
            print(f"  {key}: {value}")

    print("\n--- Signal Cycle Optimization for AI/Tech ---")
    ai_config = optimize_signal_cycle("AI/科技", current_regime=2)
    print(f"  Recommended primary scale: {ai_config['recommended_primary_scale']}")
    print(f"  All scales total strength: {ai_config['all_scales_total_strength']:.3f}")
    if ai_config.get("regime"):
        print(f"  Regime strategy: {ai_config.get('regime_strategy')}")

    print("\n--- Regime-aware Layer Weights ---")
    for reg in (0, 1, 2, 3):
        weights = get_regime_aware_layer_weights(reg)
        print(f"  Regime {reg}: {weights}")

    print("\n=== Default Causal Edges ({len(DEFAULT_CAUSAL_CHAINS)} total) ===")
    for edge in DEFAULT_CAUSAL_CHAINS:
        print(f"  [{edge.time_scale.value}] {edge.source} -> {edge.target} "
              f"(strength={edge.strength:.2f}, conf={edge.confidence:.2f}, "
              f"lag={edge.lag_days}d, method={edge.method.value})")
