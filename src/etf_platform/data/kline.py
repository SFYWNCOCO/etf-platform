"""Historical K-line data for trend analysis.
Uses akshare (Sina backend) which is stable and free.
"""
import time
from typing import Optional, Dict
from dataclasses import dataclass


@dataclass
class TrendSnapshot:
    """Trend indicators derived from historical prices."""
    code: str = ""
    price: float = 0.0
    change_5d: float = 0.0
    change_10d: float = 0.0
    change_20d: float = 0.0
    change_60d: float = 0.0
    high_60d: float = 0.0
    low_60d: float = 0.0
    position_pct: float = 50.0      # 0=60日最低, 100=60日最高
    max_drawdown: float = 0.0
    volatility_20d: float = 0.0
    volume_ratio_5_20: float = 1.0   # 近5日均量/近20日均量
    trend_signal: str = "neutral"
    data_days: int = 0


def get_trend(code: str) -> Optional[TrendSnapshot]:
    """Get trend indicators for an ETF code.
    Uses akshare Sina backend (stable).
    Returns None if data unavailable.
    """
    try:
        import akshare
        import numpy as np
        
        # Determine prefix
        if code.startswith(("5", "6")):
            symbol = f"sh{code}"
        else:
            symbol = f"sz{code}"
        
        df = akshare.fund_etf_hist_sina(symbol=symbol)
        if df is None or len(df) < 5:
            return None
        
        close = df["close"]
        high = df["high"]
        low = df["low"]
        vol = df["volume"]
        latest = float(close.iloc[-1])
        days = len(df)
        
        # Period changes
        chg_5d = float((close.iloc[-1] / close.iloc[-6] - 1) * 100) if days >= 6 else 0
        chg_10d = float((close.iloc[-1] / close.iloc[-11] - 1) * 100) if days >= 11 else 0
        chg_20d = float((close.iloc[-1] / close.iloc[-21] - 1) * 100) if days >= 21 else 0
        chg_60d = float((close.iloc[-1] / close.iloc[0] - 1) * 100)
        
        # Position in 60d range
        recent_close = close.iloc[-60:] if days >= 60 else close
        h60 = float(recent_close.max())
        l60 = float(recent_close.min())
        pos = float((latest - l60) / (h60 - l60) * 100) if h60 > l60 else 50
        
        # Max drawdown
        dd = float((close / close.cummax() - 1).min() * 100)
        
        # Volatility (20d annualized)
        returns = close.pct_change().dropna()
        r20 = returns.iloc[-20:] if len(returns) >= 20 else returns
        vol_20d = float(r20.std() * (252 ** 0.5))
        
        # Volume ratio
        v5 = float(vol.iloc[-5:].mean())
        v20 = float(vol.iloc[-20:].mean()) if days >= 20 else float(vol.mean())
        vr = v5 / v20 if v20 > 0 else 1.0
        
        # Trend signal
        if pos < 15:
            signal = "oversold"  # 超卖/近低点
        elif pos < 35:
            signal = "weak"      # 弱势
        elif pos < 65:
            signal = "neutral"   # 中性
        elif pos < 85:
            signal = "strong"    # 强势
        else:
            signal = "overbought" # 超买/近高点
        
        # Adjust for recent momentum
        if chg_5d < -5 and signal in ("weak", "oversold"):
            signal = "plunging"  # 急跌
        elif chg_5d > 5 and signal in ("strong", "overbought"):
            signal = "surging"   # 急涨
        
        return TrendSnapshot(
            code=code,
            price=latest,
            change_5d=round(chg_5d, 2),
            change_10d=round(chg_10d, 2),
            change_20d=round(chg_20d, 2),
            change_60d=round(chg_60d, 2),
            high_60d=round(h60, 3),
            low_60d=round(l60, 3),
            position_pct=round(pos, 1),
            max_drawdown=round(dd, 1),
            volatility_20d=round(vol_20d * 100, 1),
            volume_ratio_5_20=round(vr, 2),
            trend_signal=signal,
            data_days=days,
        )
    except Exception:
        return None


def get_trend_batch(codes: list) -> Dict[str, TrendSnapshot]:
    """Get trend for multiple ETFs."""
    result = {}
    for code in codes:
        try:
            t = get_trend(code)
            if t:
                result[code] = t
        except Exception:
            continue
    return result
