"""technical_indicators.py — 标准技术指标纯函数库

来源: k168 (技术分析)
numpy 实现，无外部依赖、无 IO，输入不足时以 None 填充。
"""
from __future__ import annotations

import math

import numpy as np


def _to_list(arr) -> list:
    """numpy 数组转 list：NaN -> None，其余转 float。"""
    return [
        None if (v is None or (isinstance(v, float) and math.isnan(v))) else float(v)
        for v in arr
    ]


def sma(values: list[float], period: int) -> list[float]:
    """简单移动平均线，前 period-1 个为 None。"""
    arr = np.asarray(values, dtype=float)
    n = len(arr)
    out = np.full(n, np.nan)
    if period > 0 and n >= period:
        csum = np.cumsum(np.insert(arr, 0, 0.0))
        out[period - 1:] = (csum[period:] - csum[:-period]) / period
    return _to_list(out)


def ema(values: list[float], period: int) -> list[float]:
    """指数移动平均线，前 period-1 个为 None，种子用前 period 个的 SMA。"""
    arr = np.asarray(values, dtype=float)
    n = len(arr)
    out = np.full(n, np.nan)
    if period > 0 and n >= period:
        alpha = 2.0 / (period + 1.0)
        out[period - 1] = np.mean(arr[:period])
        for i in range(period, n):
            out[i] = alpha * arr[i] + (1.0 - alpha) * out[i - 1]
    return _to_list(out)


def macd(
    values: list[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> dict:
    """MACD：返回 {"dif", "dea", "hist"}，hist = 2 * (dif - dea)。"""
    n = len(values)
    res = {"dif": [None] * n, "dea": [None] * n, "hist": [None] * n}
    if n < max(fast, slow) + signal:
        return res

    ema_fast = ema(values, fast)
    ema_slow = ema(values, slow)
    start = max(fast, slow) - 1
    dif = [None] * n
    for i in range(start, n):
        if ema_fast[i] is not None and ema_slow[i] is not None:
            dif[i] = ema_fast[i] - ema_slow[i]

    valid = [d for d in dif[start:] if d is not None]
    dea_valid = ema(valid, signal)
    dea = [None] * n
    for k, dv in enumerate(dea_valid):
        if dv is not None:
            dea[start + k] = dv

    hist = [
        None if (dif[i] is None or dea[i] is None) else 2.0 * (dif[i] - dea[i])
        for i in range(n)
    ]
    return {"dif": dif, "dea": dea, "hist": hist}


def rsi(values: list[float], period: int = 14) -> list[float]:
    """Wilder 平滑 RSI，前 period 个为 None，取值 [0,100]。"""
    arr = np.asarray(values, dtype=float)
    n = len(arr)
    out = [None] * n
    if n < period + 1:
        return out

    deltas = np.diff(arr)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = float(np.mean(gains[:period]))
    avg_loss = float(np.mean(losses[:period]))

    def _value(ag: float, al: float) -> float:
        if al == 0.0:
            return 100.0
        rs = ag / al
        return 100.0 - 100.0 / (1.0 + rs)

    out[period] = _value(avg_gain, avg_loss)
    for i in range(period + 1, n):
        avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
        out[i] = _value(avg_gain, avg_loss)
    return out


def kdj(
    values_high: list,
    values_low: list,
    values_close: list,
    n: int = 9,
    k_period: int = 3,
    d_period: int = 3,
) -> dict:
    """KDJ：返回 {"k", "d", "j"}，前 n-1 个为 None，K/D 初值 50。"""
    h = np.asarray(values_high, dtype=float)
    l = np.asarray(values_low, dtype=float)
    c = np.asarray(values_close, dtype=float)
    N = len(c)
    res = {"k": [None] * N, "d": [None] * N, "j": [None] * N}
    if N < n or n <= 0:
        return res

    k = 50.0
    d = 50.0
    for i in range(n - 1, N):
        hh = float(np.max(h[i - n + 1:i + 1]))
        ll = float(np.min(l[i - n + 1:i + 1]))
        rng = hh - ll
        rsv = 50.0 if rng == 0 else (c[i] - ll) / rng * 100.0
        k = (k * (k_period - 1) + rsv) / k_period
        d = (d * (d_period - 1) + k) / d_period
        res["k"][i] = k
        res["d"][i] = d
        res["j"][i] = 3.0 * k - 2.0 * d
    return res


def golden_cross(sma_short: list, sma_long: list) -> list[bool]:
    """金叉检测：短线上穿上长线返回 True（首元素恒 False）。"""
    n = min(len(sma_short), len(sma_long))
    out = [False] * n
    for i in range(1, n):
        a0, a1 = sma_short[i - 1], sma_short[i]
        b0, b1 = sma_long[i - 1], sma_long[i]
        if None in (a0, a1, b0, b1):
            continue
        if a0 <= b0 and a1 > b1:
            out[i] = True
    return out


def all_indicators(
    close: list[float],
    high: list[float] | None = None,
    low: list[float] | None = None,
) -> dict:
    """一键汇总 {"sma5","sma10","sma20","sma60","macd","rsi14","kdj"}。"""
    close = list(close)
    out = {
        "sma5": sma(close, 5),
        "sma10": sma(close, 10),
        "sma20": sma(close, 20),
        "sma60": sma(close, 60),
        "macd": macd(close),
        "rsi14": rsi(close, 14),
    }
    if high is not None and low is not None:
        out["kdj"] = kdj(list(high), list(low), close)
    else:
        out["kdj"] = None
    return out
