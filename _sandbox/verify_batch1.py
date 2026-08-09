"""验收: 4个新分析模块合成数据实测。"""
import math
import random

import numpy as np

rng = np.random.default_rng(2026)

print("=" * 60)
print("模块1 hurst_regime (k190)")
print("=" * 60)
from etf_platform.analysis.hurst_regime import hurst_dfa, classify_regime, H_TREND_THRESHOLD, H_REVERSION_THRESHOLD

n = 500
t = np.arange(n)
sine = np.sin(t / 10.0) * 10 + 5.0 * rng.standard_normal(n)
print("H_TREND_THRESHOLD=", H_TREND_THRESHOLD, "H_REVERSION_THRESHOLD=", H_REVERSION_THRESHOLD)
print("hurst_dfa(正弦波+噪声) =", hurst_dfa(sine.tolist()))

rw = np.cumsum(rng.standard_normal(n))
print("hurst_dfa(随机游走)     =", hurst_dfa(rw.tolist()))
print("  R2>0.7检查:", hurst_dfa(rw.tolist())[1] > 0.7)
iid = rng.standard_normal(n)
print("hurst_dfa(iid收益率)   =", hurst_dfa(iid.tolist()))

rw2 = np.cumsum(rng.standard_normal(200))
print("hurst_dfa(200点随机游走)=", hurst_dfa(rw2.tolist()))
print("hurst_dfa(不足200点)    =", hurst_dfa([1.0] * 50))

print("classify(0.62, 0.01) =", classify_regime(0.62, 0.01))
print("classify(0.40, 0.01) =", classify_regime(0.40, 0.01))
print("classify(0.50, 0.03) =", classify_regime(0.50, 0.03))
print("classify(0.62, 0.03) =", classify_regime(0.62, 0.03))
print("classify(0.50, 0.01) =", classify_regime(0.50, 0.01))

print()
print("=" * 60)
print("模块2 style_rotation (k295)")
print("=" * 60)
from etf_platform.analysis.style_rotation import STYLE_ETFS, STYLE_WEIGHTS, calculate_style_scores, style_momentum, recommend_style

print("STYLE_ETFS:", STYLE_ETFS)
print("STYLE_WEIGHTS:", STYLE_WEIGHTS)
macro = {"货币增速": 0.7, "信用增速": 0.6, "GDP增速": 0.5}
micro = {"估值分位": 0.4, "拥挤度": 0.6, "动量": 0.65}
scores = calculate_style_scores(macro, micro)
print("scores:", scores)
print("composite范围检查: all 0<=c<=1 ->", all(0 <= s["composite"] <= 1 for s in scores.values()))
print("缺输入默认0.5:", calculate_style_scores({}, {}))

# 构造 trends: 融资成长强、小微盘弱
code_to_style = {c: s for s, cs in STYLE_ETFS.items() for c in cs}
trends = {}
for c in STYLE_ETFS["融资成长"]:
    trends[c] = {"change_20d": 8.0}
for c in STYLE_ETFS["盈利质量"]:
    trends[c] = {"change_20d": 3.0}
for c in STYLE_ETFS["红利低波"]:
    trends[c] = {"change_20d": 1.0}
for c in STYLE_ETFS["小微盘"]:
    trends[c] = {"change_20d": -2.0}
print("momentum:", style_momentum(trends, code_to_style))
recs = recommend_style(trends, code_to_style, top_n=2)
print("recommend:", recs)
print("recommend非空:", bool(recs))

print()
print("=" * 60)
print("模块3 cross_asset_correlation (k189)")
print("=" * 60)
from etf_platform.analysis.cross_asset_correlation import correlation_matrix, detect_diversification_failure, tail_dependence, get_cross_asset_risk

base = rng.standard_normal(120)
a = base * 1.0 + 0.05 * rng.standard_normal(120)  # 与base高度相关
b = base * 1.0 + 0.05 * rng.standard_normal(120)  # 与base高度相关
c = 0.5 * rng.standard_normal(120)                # 独立
mat, meta = correlation_matrix({"A": a.tolist(), "B": b.tolist(), "C": c.tolist()})
print("meta:", meta)
for k, v in mat.items():
    print("corr", k, "=", round(v, 4))
print("A-B corr>0.8:", mat[("A", "B")] > 0.8)

mat2, _ = correlation_matrix({"X": a.tolist(), "Y": b.tolist()})
print("failure(A,B,C):", detect_diversification_failure(mat))
print("failure(A,B):", detect_diversification_failure(mat2))
print("tail(A,B):", tail_dependence(a.tolist(), b.tolist()))
print("tail(A,C):", tail_dependence(a.tolist(), c.tolist()))
print("correlation_matrix(短序列):", correlation_matrix({"X": [1.0] * 10, "Y": [1.0] * 10}))

print()
print("=" * 60)
print("模块4 performance_metrics (k169)")
print("=" * 60)
from etf_platform.analysis.performance_metrics import (returns_from_prices, annualized_return, sharpe_ratio,
                                                       sortino_ratio, max_drawdown, calmar_ratio, win_rate, summary_metrics)

# 手工核对: 100,110,99,108.9 → 收益率 0.10,-0.10,0.10
prices = [100.0, 110.0, 99.0, 108.9]
rets = returns_from_prices(prices)
print("returns:", rets)
print("annualized(手工): 几何年化 =", annualized_return(rets))
# 手工: 3期几何总收益 = 1.1*0.9*1.1-1 = 0.089, 年化=(1.089)^(252/3)-1
print("  校验: 手工 (1.089)^(84)-1 =", (1.089) ** (252 / 3) - 1)
print("max_drawdown(手工): 谷99 峰110 -> (99-110)/110 =", max_drawdown(prices))
print("  校验: 手工 =", (99 - 110) / 110)
print("sharpe:", sharpe_ratio(rets))
# 手工 sharpe: mean=0.0333, pstdev=0.0943, sqrt(252)=15.87 -> 0.0333/0.0943*15.87
mean = sum(rets) / len(rets)
pstdev = math.sqrt(sum((r - mean) ** 2 for r in rets) / len(rets))
print("  校验: 手工 mean=%.6f pstdev=%.6f sharpe=%.6f" % (mean, pstdev, mean / pstdev * math.sqrt(252)))
print("win_rate:", win_rate(rets), " (2正/3 =", 2 / 3, ")")
print("sortino:", sortino_ratio(rets))
print("calmar:", calmar_ratio(rets, prices))
print("summary:", summary_metrics(prices))
print("summary key数:", len(summary_metrics(prices)))

# 单调上涨序列: 无负收益
up = [100.0 * (1.01 ** i) for i in range(100)]
print("单调上涨 sortino =", sortino_ratio(returns_from_prices(up)))
print("单调上涨 max_drawdown =", max_drawdown(up))
print("sharpe(全等收益,std=0) =", sharpe_ratio([0.01] * 100))
print("annualized(空序列) =", annualized_return([]))
print("max_drawdown(空) =", max_drawdown([]))
