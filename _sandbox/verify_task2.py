"""任务2验证：technical_indicators.py (k168) 纯函数技术指标库。"""
import ast
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

# 1. AST + import
f = SRC / "etf_platform" / "analysis" / "technical_indicators.py"
ast.parse(f.read_text(encoding="utf-8"))
from etf_platform.analysis.technical_indicators import (
    sma, ema, macd, rsi, kdj, golden_cross, all_indicators,
)
print("[1] AST + import 通过")

# 2. 上升趋势 close 序列
uptrend = list(range(100, 140))  # 100..139 单调上升
s5 = sma(uptrend, 5)
s20 = sma(uptrend, 20)
assert s5[:4] == [None] * 4, "sma 前 period-1 应为 None"
assert s5[4] is not None and s20[19] is not None
assert s5[-1] > s20[-1], f"上升趋势中 sma5={s5[-1]} 应 > sma20={s20[-1]}"
assert all(not x for x in [None] + [v is None for v in s5[4:]]), "sma5 有效段非 None"
print(f"[2] sma: sma5[-1]={s5[-1]:.2f} > sma20[-1]={s20[-1]:.2f} "
      f"(上升趋势短期均线在上方) ✅")

# 3. ema
e5 = ema(uptrend, 5)
assert e5[:4] == [None] * 4 and e5[-1] is not None
assert abs(e5[-1] - 137.0) < 10, "EMA 应接近当前价"
print(f"[3] ema: e5[-1]={e5[-1]:.2f} ✅")

# 4. MACD：V形序列，金叉发生在趋势转折后
# 100 跌到 80（40点）再涨回 100（40点），转折点 idx=39
vshape = [100.0 - 0.5 * i for i in range(40)] + [80.0 + 0.5 * i for i in range(40)]
m = macd(vshape)
dif = m["dif"]
dea = m["dea"]
hist = m["hist"]
# 转折点 index 20 (80)
trough = vshape.index(80)
# 找 hist 由负转正的位置
cross = None
for i in range(1, len(hist)):
    if hist[i] is not None and hist[i - 1] is not None and hist[i - 1] < 0 < hist[i]:
        cross = i
        break
assert cross is not None, "应存在 MACD 金叉（hist 由负转正）"
assert cross > trough, f"金叉 index {cross} 应在转折点 {trough} 之后"
# DIF 在转折前为负，转折后转正
assert dif[trough] is not None and dif[trough] < 0, f"转折点 DIF={dif[trough]} 应为负"
assert dif[-1] > 0, f"末端 DIF={dif[-1]} 应转正"
print(f"[4] macd: 转折点 idx={trough}(close={vshape[trough]}), "
      f"金叉 idx={cross}, DIF={dif[trough]:.2f}→{dif[-1]:.2f} ✅")

# 5. RSI 在 [0,100]
r14 = rsi(vshape, 14)
r_valid = [x for x in r14 if x is not None]
assert r_valid, "RSI 应有有效值"
assert all(0 <= x <= 100 for x in r_valid), f"RSI 越界: {r_valid}"
print(f"[5] rsi: 有效{len(r_valid)}个, 范围[{min(r_valid):.1f}, {max(r_valid):.1f}] ✅")

# 6. KDJ
high = [v + 1 for v in vshape]
low = [v - 1 for v in vshape]
kd = kdj(high, low, vshape)
k_valid = [x for x in kd["k"] if x is not None]
assert k_valid and all(0 <= x <= 100 for x in k_valid)
assert kd["j"][-1] is not None
print(f"[6] kdj: K范围[{min(k_valid):.1f},{max(k_valid):.1f}], J[-1]={kd['j'][-1]:.1f} ✅")

# 7. golden_cross：构造短上穿长
short = [None, 1.0, 2.0, 3.0, 4.0, 5.0]
long_ = [None, 2.5, 2.6, 2.0, 1.5, 1.0]
gc = golden_cross(short, long_)
assert gc == [False, False, False, True, False, False], f"金叉检测错误: {gc}"
print(f"[7] golden_cross: {gc} 上穿点 index=3 ✅")

# 8. all_indicators
full = all_indicators(vshape, high, low)
assert set(full) == {"sma5", "sma10", "sma20", "sma60", "macd", "rsi14", "kdj"}
assert full["kdj"] is not None and full["macd"]["dif"][-1] is not None
no_hl = all_indicators(vshape)
assert no_hl["kdj"] is None, "未提供 high/low 时 kdj 应为 None"
print(f"[8] all_indicators: keys={sorted(full)}, kdj/无hl分支 ✅")

# 9. 边界：输入不足返回 None 填充
short_data = [1.0, 2.0, 3.0]
assert sma(short_data, 5) == [None, None, None]
assert rsi(short_data, 14) == [None, None, None]
assert macd(short_data)["dif"] == [None, None, None]
assert kdj(short_data, short_data, short_data)["k"] == [None, None, None]
print("[9] 边界: 输入不足返回 None 填充 ✅")

print("\n任务2全部验证通过")
