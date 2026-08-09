"""performance_metrics.py — 统一绩效指标计算

来源: k169 (绩效评估)
Sharpe/Sortino/Calmar/最大回撤/年化/胜率 等统一指标。
纯 stdlib + math，不依赖 numpy。
"""
from __future__ import annotations

import math
import statistics


def returns_from_prices(prices: list[float]) -> list[float]:
    """简单日收益率列表（去首日）。"""
    if len(prices) < 2:
        return []
    return [prices[i] / prices[i - 1] - 1 for i in range(1, len(prices))]


def annualized_return(returns: list[float], periods_per_year: int = 252) -> float:
    """几何年化收益。"""
    n = len(returns)
    if n == 0:
        return 0.0
    product = 1.0
    for r in returns:
        product *= (1.0 + r)
        if product <= 0.0:
            return -1.0
    return product ** (periods_per_year / n) - 1.0


def sharpe_ratio(returns: list[float], risk_free: float = 0.0, periods_per_year: int = 252) -> float:
    """(均值-无风险)/标准差 * sqrt(periods)。标准差=0返回0.0。"""
    n = len(returns)
    if n == 0:
        return 0.0
    std = statistics.pstdev(returns)
    if std == 0:
        return 0.0
    mean = sum(returns) / n
    return (mean - risk_free) / std * math.sqrt(periods_per_year)


def sortino_ratio(returns: list[float], risk_free: float = 0.0, periods_per_year: int = 252) -> float:
    """下行标准差（仅负收益）替代总标准差。无下行波动返回0.0。"""
    n = len(returns)
    if n == 0:
        return 0.0
    downs = [r * r for r in returns if r < 0.0]
    if not downs:
        return 0.0
    downside = math.sqrt(sum(downs) / n)
    if downside == 0:
        return 0.0
    mean = sum(returns) / n
    return (mean - risk_free) / downside * math.sqrt(periods_per_year)


def max_drawdown(prices: list[float]) -> float:
    """(谷值-峰值)/峰值，返回负数。"""
    if len(prices) < 2:
        return 0.0
    peak = prices[0]
    dd = 0.0
    for p in prices:
        if p > peak:
            peak = p
        dd = min(dd, (p - peak) / peak)
    return dd


def calmar_ratio(returns: list[float], prices: list[float], periods_per_year: int = 252) -> float:
    """年化收益 / |最大回撤|。回撤=0返回0.0。"""
    dd = max_drawdown(prices)
    if dd == 0:
        return 0.0
    return annualized_return(returns, periods_per_year) / abs(dd)


def win_rate(returns: list[float]) -> float:
    """正收益天数占比。"""
    if not returns:
        return 0.0
    return sum(1 for r in returns if r > 0.0) / len(returns)


def summary_metrics(prices: list[float], risk_free: float = 0.0) -> dict:
    """一键汇总绩效指标。"""
    returns = returns_from_prices(prices)
    periods = 252
    vol = statistics.pstdev(returns) * math.sqrt(periods) if returns else 0.0
    total_return = prices[-1] / prices[0] - 1 if len(prices) >= 2 else 0.0
    return {
        "annual_return": annualized_return(returns, periods),
        "sharpe": sharpe_ratio(returns, risk_free, periods),
        "sortino": sortino_ratio(returns, risk_free, periods),
        "max_drawdown": max_drawdown(prices),
        "calmar": calmar_ratio(returns, prices, periods),
        "win_rate": win_rate(returns),
        "total_return": total_return,
        "volatility": vol,
    }


if __name__ == "__main__":
    # 手工可核对序列: 100,110,99,108.9 → 收益率 10%,-10%,10%
    prices = [100.0, 110.0, 99.0, 108.9]
    print("returns:", returns_from_prices(prices))
    print("annualized:", annualized_return(returns_from_prices(prices)))
    print("max_drawdown:", max_drawdown(prices))
    print("summary:", summary_metrics(prices))
