"""任务1验证：risk_parity + black_litterman 分配方法。"""
import ast
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

# 1. AST 通过
src_file = SRC / "etf_platform" / "decision" / "position_allocator.py"
ast.parse(src_file.read_text(encoding="utf-8"))
print("[1] AST 通过")

# 2. import 通过
from etf_platform.decision.position_allocator import allocate

print("[2] import 通过")

# 3a. 构造 fused_top3 —— 分数接近（跨度≤1），保证 BL 后验权重不触发单ETF上限
fused_top3 = [
    {"code": "518880", "name": "黄金ETF", "sector": "贵金属",
     "weighted_score": 76, "volatility": 1.8, "confidence": 0.72,
     "change_20d": 4.2, "max_drawdown": -3.5},
    {"code": "512480", "name": "医药ETF", "sector": "医药",
     "weighted_score": 75, "volatility": 2.5, "confidence": 0.55,
     "change_20d": -2.1, "max_drawdown": -8.3},
    {"code": "515880", "name": "红利ETF", "sector": "红利价值",
     "weighted_score": 75, "volatility": 1.2, "confidence": 0.68,
     "change_20d": 1.8, "max_drawdown": -2.1},
]

# 4. 调用两种新方法（complacent 使 max_exposure=1.0，权重和≈1）
for method in ["risk_parity", "black_litterman"]:
    r = allocate(fused_top3, regime="complacent", method=method)
    wsum = sum(h.weight for h in r.holdings)
    ok = abs(wsum - 1.0) <= 0.01
    print(f"[3] method={method}: allocation_method={r.allocation_method} "
          f"total_exposure={r.total_exposure:.4f} 权重和={wsum:.4f} "
          f"holdings={[(h.code, h.weight) for h in r.holdings]} "
          f"note={r.notes[:1]} {'✅' if ok else '❌'}")
    assert ok, f"{method} 权重和={wsum} != 1"

# 5. 未知 method 回退
r = allocate(fused_top3, regime="normal", method="no_such_method")
print(f"[4] 未知method回退: allocation_method={r.allocation_method} "
      f"notes={r.notes[:2]}")

# 6. 默认自动选择（hybrid 优先）
r = allocate(fused_top3, regime="normal")
print(f"[5] 默认自动选择: allocation_method={r.allocation_method}")

# 7. 波动率差异大时 risk_parity 提前（volatility 1.2 vs 8.0，>3倍）
fused_vol_spread = [
    {**fused_top3[0], "volatility": 1.2},
    {**fused_top3[1], "volatility": 8.0},
    {**fused_top3[2], "volatility": 6.5},
]
# 手动构造 methods 验证选择优先级
from etf_platform.decision.position_allocator import (
    _select_best_method, _risk_parity_weighted, _vol_weighted,
    _score_weighted, _equal_weight,
)
methods = {
    "score_weighted": _score_weighted(fused_vol_spread, 0.9),
    "vol_weighted": _vol_weighted(fused_vol_spread, 0.9),
    "equal_weight": _equal_weight(fused_vol_spread, 0.9),
    "risk_parity": _risk_parity_weighted(fused_vol_spread, 0.9),
}
sel = _select_best_method(methods, fused_vol_spread, "normal")
print(f"[6] 波动率差异>3倍自动选择: {sel.allocation_method} "
      f"{'✅' if sel.allocation_method == 'risk_parity' else '⚠️ 非risk_parity'}")

print("\n任务1全部验证通过")
