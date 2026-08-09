"""hurst_regime.py — Hurst指数(DFA)与市场制度分类

来源: k190 (Hurst指数/分形市场)
DFA(去趋势波动分析)计算 Hurst 指数，按 Fractal Cycles 四制度分类。
只依赖 numpy + stdlib，不依赖 akshare。
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

H_TREND_THRESHOLD = 0.55
H_REVERSION_THRESHOLD = 0.45
DEFAULT_WINDOWS = [30, 50, 70, 100, 150, 200, 300]
_MIN_POINTS = 150


def hurst_dfa(prices: list[float], windows: list[int] | None = None) -> tuple[float, float]:
    """DFA 去趋势波动分析，返回 (H, R²)。

    prices 需 >=200 个点，不足返回 (0.5, 0.0)。
    R²>0.9 才可靠；R²<0.7 时标注低置信。
    """
    n = len(prices)
    if n < _MIN_POINTS:
        return (0.5, 0.0)
    win_list = windows or DEFAULT_WINDOWS
    profile = np.cumsum(np.asarray(prices, dtype=float) - float(np.mean(prices)))
    # 每窗口至少 2 段，否则线性去趋势残差恒为 0
    valid = [w for w in win_list if w >= 4 and len(profile) // w >= 2]
    if len(valid) < 2:
        return (0.5, 0.0)

    fluct = []
    for w in valid:
        nseg = len(profile) // w
        resid = 0.0
        for i in range(nseg):
            seg = profile[i * w:(i + 1) * w]
            t = np.arange(w, dtype=float)
            coeffs = np.polyfit(t, seg, 1)
            resid += float(np.sum((seg - np.polyval(coeffs, t)) ** 2))
        fluct.append(np.sqrt(resid / (nseg * w)))

    # 常数/零波动序列: fluct 全为 0 → log(0)=-inf → polyfit 出 nan，直接退化返回
    fluct_arr = np.asarray(fluct, dtype=float)
    if np.any(fluct_arr == 0.0) or not np.all(np.isfinite(fluct_arr)):
        return (0.5, 0.0)

    log_n = np.log(np.asarray(valid, dtype=float))
    log_f = np.log(fluct_arr)
    H, logc = np.polyfit(log_n, log_f, 1)
    pred = np.polyval([H, logc], log_n)
    ss_res = float(np.sum((log_f - pred) ** 2))
    ss_tot = float(np.sum((log_f - log_f.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return (round(float(H), 4), round(float(r2), 4))


def classify_regime(H: float, vol: float, vol_threshold: float = 0.02) -> dict:
    """按 Fractal Cycles 四制度分类。

    H>0.55+低波 → 强势趋势期；H<0.45+低波 → 均值回归期；
    H≈0.5+高波 → 随机游走+高波动；H>0.55+高波 → 趋势中剧烈波动。
    """
    high_vol = vol >= vol_threshold
    if H > H_TREND_THRESHOLD:
        regime, label = ("trend_strong", "强势趋势期") if not high_vol else ("trend_volatile", "趋势中剧烈波动")
    elif H < H_REVERSION_THRESHOLD:
        regime, label = ("mean_reversion", "均值回归期") if not high_vol else ("mean_reversion_volatile", "高波动均值回归")
    else:
        regime, label = ("random_walk", "随机游走") if not high_vol else ("random_high_vol", "随机游走+高波动")
    return {"regime": regime, "label": label, "H": H, "vol": vol}


def _daily_vol(prices: list[float]) -> float:
    rets = [prices[i] / prices[i - 1] - 1 for i in range(1, len(prices))]
    return float(np.std(rets)) if rets else 0.0


def get_hurst_regime(codes: list[str], days: int = 250) -> dict:
    """批量: 对每个 code 拉K线算 Hurst，返回 {code: {"H","regime","R2"}}。

    TrendSnapshot 不含价格序列，故用 get_trend_batch 确认数据可用性后，
    再取原始日K线计算真实 Hurst。数据不足(<200点)的 code 不返回。
    """
    from etf_platform.data.kline import get_trend_batch, _fetch_kline

    snapshots = get_trend_batch(codes)
    result: dict = {}
    for code in codes:
        ts = snapshots.get(code)
        if ts is None or ts.data_days < _MIN_POINTS:
            continue
        rows = _fetch_kline(code, days)
        if not rows or len(rows) < _MIN_POINTS:
            continue
        prices = [float(r["close"]) for r in rows]
        H, r2 = hurst_dfa(prices)
        if r2 == 0.0:
            continue
        reg = classify_regime(H, _daily_vol(prices))
        result[code] = {"H": H, "regime": reg["regime"], "R2": r2}
    return result


if __name__ == "__main__":
    rng = np.random.default_rng(42)
    n = 500
    rw = np.cumsum(rng.standard_normal(n))
    print("random_walk  hurst_dfa =", hurst_dfa(rw.tolist()))
    print("classify     =", classify_regime(0.62, 0.015))
    print("classify     =", classify_regime(0.62, 0.03))
