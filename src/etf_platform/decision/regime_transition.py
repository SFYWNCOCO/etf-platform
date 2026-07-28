#!/usr/bin/env python3
"""
regime_transition.py — 市场状态转换预测器 v1.0

核心理念: 策略锦标赛发现不同regime下最优策略完全不同。
与其等regime变了再切换策略，不如提前预判转换概率。

方法:
  - 使用4个先行指标估算转换概率
  - 市场广度(breath): 站上20日均线的ETF比例
  - 波动率趋势(vol_trend): VIX是升还是降
  - 量能方向(volume): 恐慌放量 vs 缩量企稳
  - 指数动量(momentum): 主要指数短期方向
  
  - 输出: 转换概率矩阵 (当前regime → 各可能regime的概率)
  - 用于 tournament 的策略权重前瞻调整

用法:
  python -m etf_platform.decision.regime_transition
  python -m etf_platform.decision.regime_transition --json
"""

import json
import sys
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

BASE = Path(__file__).resolve().parent.parent.parent.parent  # etf-platform/
DATA_DIR = BASE / "data"

# Regime ordering (monotonic risk scale)
REGIME_ORDER = ["complacent", "normal", "cautious", "fearful"]
REGIME_SCORE = {"complacent": 0, "normal": 1, "cautious": 2, "fearful": 3}


@dataclass(slots=True)
class TransitionPrediction:
    """Regime transition forecast."""
    current_regime: str
    timestamp: str = field(default_factory=lambda: date.today().isoformat())

    # Transition probabilities (must sum to ~1.0)
    prob_stay: float = 0.5       # Stay in current regime
    prob_improve: float = 0.25   # Move toward complacent (e.g., fearful→cautious)
    prob_worsen: float = 0.25    # Move toward fearful (e.g., cautious→fearful)

    # Raw indicators
    breadth_pct: float = 50.0    # % ETFs above 20MA
    vol_trend: float = 0.0       # Volatility trend (-1 falling, +1 rising)
    volume_signal: float = 0.0   # Volume direction (-1 panic, +1 calm)
    momentum_signal: float = 0.0 # Index momentum (-1 down, +1 up)

    # Blended weights for tournament (前瞻调整)
    blended_weights: dict[str, float] = field(default_factory=dict)

    confidence: str = "medium"   # high/medium/low


def _estimate_breadth() -> tuple[float, int]:
    """Estimate market breadth: % of ETFs above 20-day MA.

    Uses TrendSnapshot data (session-cached).
    """
    try:
        from etf_platform.data.kline import get_trend
        from etf_platform.config_loader import load_etfs

        etfs = load_etfs()
        above_ma = 0
        total = 0

        for code, info in etfs.items():
            if not code.isdigit():
                continue
            if info.get("access") != "buyable":
                continue
            sector = info.get("sector", "")
            if sector in {"货币基金", "利率债", "信用债", "债券", "国债", "货币"}:
                continue

            try:
                trend = get_trend(code)
                if trend and trend.data_days >= 20:
                    total += 1
                    # Above 20MA: latest price > 20-day average
                    # Approximation: change_20d > 0 means price above 20-day ago
                    if trend.change_20d > -2:  # Slight tolerance
                        above_ma += 1
            except (KeyError, ValueError, TypeError, AttributeError, OSError):
                continue

            if total >= 60:
                break

        if total == 0:
            return 50.0, 0

        pct = (above_ma / total) * 100
        return round(pct, 1), total
    except (ImportError, KeyError, ValueError, TypeError, AttributeError, OSError):
        return 50.0, 0


def _estimate_vol_trend() -> float:
    """Estimate volatility trend from QVIX data.

    Returns:
        -1.0 to +1.0: negative = vol falling (improving), positive = vol rising
    """
    try:
        from etf_platform.analysis.qvix_regime import get_regime

        rd = get_regime()
        qvix_50 = rd.get("qvix_50", 20)
        qvix_500 = rd.get("qvix_500", 25)
        regime = rd.get("regime", "normal")

        # Normalize QVIX values relative to thresholds
        # fearful > 28, cautious 22-28, normal 16-22, complacent < 16
        avg_qvix = (qvix_50 + qvix_500) / 2

        # Where are we in the current regime band?
        regime_ranges = {
            "complacent": (0, 16),
            "normal": (16, 22),
            "cautious": (22, 28),
            "fearful": (28, 50),
        }
        lo, hi = regime_ranges.get(regime, (16, 28))
        position_in_band = (avg_qvix - lo) / max(hi - lo, 1)

        # -1 = at bottom of band (improving), +1 = at top (worsening)
        vol_trend = (position_in_band - 0.5) * 2
        return round(max(-1.0, min(1.0, vol_trend)), 2)
    except (ImportError, KeyError, ValueError, TypeError, AttributeError, OSError):
        return 0.0


def _estimate_volume_signal() -> float:
    """Estimate volume direction: panic selling vs calm accumulation.

    Uses volume ratio from TrendSnapshot data.
    """
    try:
        from etf_platform.data.kline import get_trend
        from etf_platform.config_loader import load_etfs

        etfs = load_etfs()
        volume_ratios = []

        for code, info in etfs.items():
            if not code.isdigit():
                continue
            try:
                trend = get_trend(code)
                if trend and trend.data_days >= 20:
                    vr = getattr(trend, "volume_ratio_5_20", 1.0)
                    volume_ratios.append(vr)
            except (KeyError, ValueError, TypeError, AttributeError, OSError):
                continue
            if len(volume_ratios) >= 30:
                break

        if not volume_ratios:
            return 0.0

        avg_vr = sum(volume_ratios) / len(volume_ratios)
        # vr > 1 = higher recent volume (could be panic or accumulation)
        # vr < 1 = lower volume (calm/consolidation)
        # In fearful regime, high volume tends to be panic
        # In normal regime, high volume tends to be accumulation
        signal = (avg_vr - 1.0) * 2  # Map to [-1, 1] roughly
        return round(max(-1.0, min(1.0, signal)), 2)
    except (ImportError, KeyError, ValueError, TypeError, AttributeError, OSError):
        return 0.0


def _estimate_momentum_signal() -> float:
    """Estimate index momentum from major ETFs.

    Returns:
        -1.0 to +1.0: negative = downward momentum, positive = upward
    """
    try:
        from etf_platform.data.kline import get_trend

        # Check major index ETFs
        index_codes = ["510050", "510300", "510500", "159915"]  # 50, 300, 500, 创业板
        momentums = []

        for code in index_codes:
            try:
                trend = get_trend(code)
                if trend and trend.data_days >= 20:
                    # Normalize 5-day momentum: anything beyond ±5% is extreme
                    mom = trend.change_20d / 20 * 5  # Scale to weekly-ish
                    momentums.append(max(-1.0, min(1.0, mom / 5.0)))
            except (KeyError, ValueError, TypeError, AttributeError, OSError):
                continue

        if not momentums:
            return 0.0

        return round(sum(momentums) / len(momentums), 2)
    except (ImportError, KeyError, ValueError, TypeError, AttributeError, OSError):
        return 0.0


def predict_transition(current_regime: Optional[str] = None) -> TransitionPrediction:
    """Predict regime transition probabilities.

    Args:
        current_regime: Force a regime. Auto-detects from QVIX if None.

    Returns:
        TransitionPrediction with probabilities and blended weights
    """
    t0 = time.time()

    # Detect current regime
    if current_regime is None:
        try:
            from etf_platform.analysis.qvix_regime import get_regime
            rd = get_regime()
            current_regime = rd.get("regime", "normal")
        except (ImportError, KeyError, ValueError, TypeError, AttributeError, OSError):
            current_regime = "normal"

    # Collect indicators
    breadth, breadth_n = _estimate_breadth()
    vol_trend = _estimate_vol_trend()
    volume_signal = _estimate_volume_signal()
    momentum_signal = _estimate_momentum_signal()

    # ── Transition probability model ────────────────────────────────
    # Logic: combine 4 signals into transition probabilities
    # Each signal votes on direction: improve (toward complacent) or worsen

    improve_score = 0.0
    worsen_score = 0.0

    # Breadth: high breadth → improving, low breadth → worsening
    if breadth > 60:
        improve_score += 2.0
    elif breadth < 30:
        worsen_score += 2.0

    # Vol trend: falling vol → improving, rising vol → worsening
    if vol_trend < -0.3:
        improve_score += 1.5
    elif vol_trend > 0.3:
        worsen_score += 1.5

    # Volume: calm → improving, panic → worsening
    # In fearful regime, high volume = panic → worsening
    # In complacent, high volume = accumulation → improving
    if current_regime in ("fearful", "cautious"):
        if volume_signal < -0.2:
            worsen_score += 1.5
        elif volume_signal > 0.2:
            improve_score += 1.0
    else:
        if volume_signal > 0.2:
            improve_score += 1.5
        elif volume_signal < -0.2:
            worsen_score += 1.0

    # Momentum: positive → improving, negative → worsening
    if momentum_signal > 0.3:
        improve_score += 1.5
    elif momentum_signal < -0.3:
        worsen_score += 1.5

    # Convert scores to probabilities using softmax
    stay_score = 2.0  # Base inertia — regimes tend to persist
    total = improve_score + stay_score + worsen_score
    if total == 0:
        total = 1

    prob_improve = improve_score / total
    prob_stay = stay_score / total
    prob_worsen = worsen_score / total

    # ── Blended weights for tournament ──────────────────────────────
    from etf_platform.decision.strategy_tournament import (
        REGIME_WEIGHT_PRIORS,
        DEFAULT_WEIGHTS,
    )

    current_weights = REGIME_WEIGHT_PRIORS.get(current_regime, DEFAULT_WEIGHTS)

    # Determine next regime in each direction
    current_idx = REGIME_SCORE.get(current_regime, 1)
    improve_regime = REGIME_ORDER[max(0, current_idx - 1)] if current_idx > 0 else current_regime
    worsen_regime = REGIME_ORDER[min(3, current_idx + 1)] if current_idx < 3 else current_regime

    improve_weights = REGIME_WEIGHT_PRIORS.get(improve_regime, DEFAULT_WEIGHTS)
    worsen_weights = REGIME_WEIGHT_PRIORS.get(worsen_regime, DEFAULT_WEIGHTS)

    # Blend: prob_stay * current + prob_improve * improve + prob_worsen * worsen
    blended: dict[str, float] = {}
    all_strategies = set(list(current_weights.keys()) + list(improve_weights.keys()) + list(worsen_weights.keys()))
    for s in all_strategies:
        blended[s] = (
            prob_stay * current_weights.get(s, 0.25)
            + prob_improve * improve_weights.get(s, 0.25)
            + prob_worsen * worsen_weights.get(s, 0.25)
        )

    # Normalize
    w_total = sum(blended.values())
    if w_total > 0:
        blended = {k: round(v / w_total, 3) for k, v in blended.items()}

    # Confidence assessment
    max_prob = max(prob_stay, prob_improve, prob_worsen)
    if max_prob > 0.6:
        confidence = "high"
    elif max_prob > 0.4:
        confidence = "medium"
    else:
        confidence = "low"

    elapsed = time.time() - t0

    return TransitionPrediction(
        current_regime=current_regime,
        prob_stay=round(prob_stay, 3),
        prob_improve=round(prob_improve, 3),
        prob_worsen=round(prob_worsen, 3),
        breadth_pct=breadth,
        vol_trend=vol_trend,
        volume_signal=volume_signal,
        momentum_signal=momentum_signal,
        blended_weights=blended,
        confidence=confidence,
    )


def format_report(pred: TransitionPrediction) -> str:
    """Format transition prediction as readable report."""
    lines = [
        "🔮 市场状态转换预测",
        f"{'=' * 55}",
        "",
        f"  当前状态: {pred.current_regime.upper()}",
        f"  置信度: {pred.confidence}",
        "",
        "  ── 转换概率 ──",
    ]

    stay_bar = "█" * int(pred.prob_stay * 25) + "░" * (25 - int(pred.prob_stay * 25))
    imp_bar = "█" * int(pred.prob_improve * 25) + "░" * (25 - int(pred.prob_improve * 25))
    wor_bar = "█" * int(pred.prob_worsen * 25) + "░" * (25 - int(pred.prob_worsen * 25))

    lines.append(f"  维持:  {stay_bar} {pred.prob_stay:.0%}")
    lines.append(f"  改善:  {imp_bar} {pred.prob_improve:.0%}")
    lines.append(f"  恶化:  {wor_bar} {pred.prob_worsen:.0%}")

    lines.append("")
    lines.append("  ── 先行指标 ──")
    lines.append(f"  市场广度: {pred.breadth_pct:.0f}% ETF站上20日均线")
    lines.append(f"  波动趋势: {pred.vol_trend:+.2f} (负=回落/正=上升)")
    lines.append(f"  量能信号: {pred.volume_signal:+.2f} (负=恐慌/正=平静)")
    lines.append(f"  指数动量: {pred.momentum_signal:+.2f} (负=下行/正=上行)")

    if pred.blended_weights:
        lines.append("")
        lines.append("  ── 前瞻权重(已混合转换概率) ──")
        for s, w in sorted(pred.blended_weights.items(), key=lambda x: -x[1]):
            bar = "█" * int(w * 20) + "░" * (20 - int(w * 20))
            lines.append(f"  {s:<18s} {bar} {w:.1%}")

    # Interpretation
    lines.append("")
    lines.append("  ── 解读 ──")
    if pred.prob_stay > 0.6:
        lines.append(f"  状态大概率维持，沿用{pred.current_regime}策略权重")
    elif pred.prob_improve > pred.prob_worsen:
        lines.append(f"  改善概率>{'恶化'}概率，可提前增加风险敞口")
    elif pred.prob_worsen > pred.prob_improve:
        lines.append(f"  恶化概率>{'改善'}概率，应提前防御")
    else:
        lines.append("  方向不明，维持当前配置")

    lines.append("")
    lines.append(f"{'=' * 55}")

    return "\n".join(lines)


if __name__ == "__main__":
    json_mode = "--json" in sys.argv

    print("🔮 计算市场状态转换概率...", file=sys.stderr)
    pred = predict_transition()

    if json_mode:
        import dataclasses
        print(json.dumps(dataclasses.asdict(pred), ensure_ascii=False, indent=2))
    else:
        print(format_report(pred))
