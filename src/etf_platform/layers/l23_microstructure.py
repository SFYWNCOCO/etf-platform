"""l23_microstructure.py — 微观结构增强层 (k019 Market Microstructure)

基于 O'Hara/Kyle/Hasbrouck 市场微观结构理论:
  - 成交量分布: 早盘放量(主力布局) vs 尾盘放量(短线博弈)
  - 换手率异常: >2倍均线 = 信息事件或操纵 (k019§四)
  - 订单簿不平衡(OBI)简化: 从涨跌幅+成交量推导买卖力量

不依赖订单簿API(免费API不可得), 从可观测数据推导微观结构信号
"""
from typing import Dict


# ── Helper: 换手率异常检测 ──────────────────────────

def _detect_turnover_anomaly(vol_ratio: float) -> tuple[str, float]:
    if vol_ratio > 2.0:
        return "extreme_high", vol_ratio
    if vol_ratio > 1.3:
        return "high", vol_ratio
    if vol_ratio < 0.35:
        return "extreme_low", vol_ratio
    if vol_ratio < 0.55:
        return "low", vol_ratio
    return "normal", vol_ratio


# ── Helper: 量价推导买卖力量 ──────────────────────

def _derive_obi_proxy(chg5: float, vol_ratio: float) -> str:
    if chg5 < -8 and vol_ratio > 1.2:
        return "panic_selling"
    if chg5 < -4 and vol_ratio > 1.3:
        return "panic_selling"
    if chg5 > 5 and vol_ratio < 0.8:
        return "accumulation"
    if chg5 > 3 and vol_ratio > 1.4:
        return "distribution"
    if chg5 < -3 and vol_ratio < 0.7:
        return "silent_drop"
    return "neutral"


# ── Helper: 微观结构噪声 ──────────────────────────

def _compute_noise(vol: float, vol_ratio: float) -> str:
    if vol > 50 and vol_ratio < 0.8:
        return "high"
    if vol < 15 and vol_ratio > 1.2:
        return "low"
    return "medium"


# ── Helper: neutral路径评分 ───────────────────────

def _score_neutral(turnover_signal: str, vol_ratio: float, chg5: float, noise: str, pos: float, vol: float) -> float:
    turnover_deviation = abs(vol_ratio - 1.0)
    if turnover_signal in ("extreme_high", "high"):
        base = 5.5 + min(2.0, turnover_deviation * 2.0)
    elif turnover_signal in ("extreme_low", "low"):
        base = 4.5 - min(1.5, turnover_deviation * 1.5)
    else:
        base = 5.0
        if chg5 > 8:
            base += 1.0
        elif chg5 > 3:
            base += 0.5
        elif chg5 < -8:
            base -= 1.0
        elif chg5 < -3:
            base -= 0.5

    if noise == "low":
        base += 0.5
    elif noise == "high":
        base -= 0.5

    if pos is not None:
        if pos < 15:
            base += 1.0
        elif pos < 25:
            base += 0.5
        elif pos > 90:
            base -= 1.0
        elif pos > 80:
            base -= 0.5

    if vol > 40 and abs(chg5) > 3:
        base += 0.5

    return base


# ── Main ──────────────────────────────────────────

def score_microstructure(sector: str, risk_level: float = 0.5,
                         etf_code: str = "") -> Dict:
    """L23 微观结构 — 从量价关系推导市场微观信号"""
    from etf_platform.data.kline import get_trend

    trend = get_trend(etf_code) if etf_code else None
    if not trend:
        return {"score": 5.0, "signal": "no_data", "turnover_anomaly": 1.0,
                "vol_distribution": "unknown", "noise_level": 0.0}

    vol_ratio = trend.volume_ratio_5_20
    chg5 = trend.change_5d
    pos = trend.position_pct
    vol = trend.volatility_20d

    turnover_signal, turnover_anomaly = _detect_turnover_anomaly(vol_ratio)
    obi_proxy = _derive_obi_proxy(chg5, vol_ratio)
    noise = _compute_noise(vol, vol_ratio)

    # ── 评分 (0-10) ──
    OBI_SCORES = {
        "panic_selling": lambda: 7.5 + min(2.5, (vol_ratio - 1.0) * 2.5),
        "accumulation": lambda: 7.0,
        "distribution": lambda: max(2.0, 3.5 - (vol_ratio - 1.2) * 2.0),
        "silent_drop": lambda: 4.5,
    }
    score_fn = OBI_SCORES.get(obi_proxy)
    score = score_fn() if score_fn else _score_neutral(turnover_signal, vol_ratio, chg5, noise, pos, vol)
    score = round(max(1.0, min(10.0, score)), 1)

    if risk_level >= 0.7:
        score += 1.0
    if obi_proxy == "panic_selling" and pos < 25:
        score += 0.5
    if score > 9.5:
        score = 9.5 + (score - 9.5) * 0.3

    # Intra-score jitter by ETF code hash
    from ..utils.hash_jitter import pair_sum_jitter
    score += pair_sum_jitter(etf_code, 7, 0.15)  # range [-0.45, +0.45]

    score = round(max(1.0, min(10.0, score)), 1)

    return {
        "score": score,
        "signal": obi_proxy,
        "turnover_anomaly": round(turnover_anomaly, 2),
        "vol_distribution": str(turnover_signal),
        "noise_level": noise,
        "volume_ratio": round(vol_ratio, 2),
        "change_5d": round(chg5, 1),
    }
