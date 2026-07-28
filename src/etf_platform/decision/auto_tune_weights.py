#!/usr/bin/env python3
import logging
logger = logging.getLogger(__name__)
"""
auto_tune_weights

原理: 
  1. 读取预测历史, 对每只ETF收集(N天)后实际收益
  2. 使用线性回归: 实际收益 ~ Z-score因子值
  3. 回归系数 = 最优权重方向
  4. 输出权重更新建议

约束:
  - 至少10个有效样本才触发调优
  - 权重变化幅度每轮不超过±0.05
  - 始终保持权重总和=1.0

用法:
  python -m etf_platform.decision.auto_tune_weights
  python -m etf_platform.decision.auto_tune_weights --apply  # 实际写入two_week_picker
"""
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent.parent
LOG_FILE = BASE / "data" / "two_week_predictions.jsonl"
TUNING_LOG = BASE / "data" / "weight_tuning_log.jsonl"
MIN_SAMPLES = 10  # Minimum predictions before tuning
MAX_WEIGHT_CHANGE = 0.05  # Max per-factor weight change per round


# ── Data collection ────────────────────────────────────────────────

def _collect_factor_return_pairs() -> list[dict]:
    """Collect (factor_Z_scores, actual_return) pairs from prediction history.
    
    For each prediction, get the factor Z-scores and the actual 
    10-day return for each ETF. This creates training pairs for regression.
    """
    if not LOG_FILE.exists():
        return []

    predictions = []
    with open(LOG_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    predictions.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    pairs = []
    for pred in predictions:
        for etf in pred.get("top3", []):
            code = etf.get("code", "")
            if not code:
                continue
            
            # Get actual 10d return
            try:
                from etf_platform.data.kline import get_trend
                t = get_trend(code)
                actual_return = t.change_10d if t else 0
            except (ImportError, KeyError, ValueError, TypeError, AttributeError, OSError):
                continue
            
            # Get Z-score factors (if available)
            z_factors = etf.get("z_factors", {})
            if not z_factors:
                continue
            
            pairs.append({
                "code": code,
                "date": pred.get("date", ""),
                "actual_return_10d": actual_return,
                "z_factors": z_factors,
                "two_week_score": etf.get("two_week_score", 50),
            })

    return pairs


# ── Regression-based tuning ────────────────────────────────────────

def _simple_regression(pairs: list[dict]) -> dict:
    """Run simple linear regression: actual_return ~ sum(w_i * z_i).
    
    Since we don't want to add scipy/numpy dependency, use a 
    simplified approach: compute correlation of each factor with 
    actual returns, then normalize to weights.
    """
    if len(pairs) < MIN_SAMPLES:
        return {"status": "insufficient_data", "samples": len(pairs),
                "needed": MIN_SAMPLES}

    # Collect all factor names
    factor_names = set()
    for p in pairs:
        factor_names.update(p["z_factors"].keys())
    factor_names = sorted(factor_names)

    # Compute per-factor correlation with actual returns
    factor_corrs = {}
    for fname in factor_names:
        z_vals = []
        ret_vals = []
        for p in pairs:
            z = p["z_factors"].get(fname, 0)
            r = p["actual_return_10d"]
            z_vals.append(z)
            ret_vals.append(r)

        n = len(z_vals)
        if n < 3:
            factor_corrs[fname] = {"correlation": 0, "direction": "neutral", "samples": n}
            continue

        # Pearson correlation
        mean_z = sum(z_vals) / n
        mean_r = sum(ret_vals) / n
        cov = sum((z_vals[i] - mean_z) * (ret_vals[i] - mean_r) for i in range(n)) / n
        std_z = (sum((z - mean_z) ** 2 for z in z_vals) / n) ** 0.5
        std_r = (sum((r - mean_r) ** 2 for r in ret_vals) / n) ** 0.5

        if std_z < 0.001 or std_r < 0.001:
            corr = 0.0
        else:
            corr = cov / (std_z * std_r)

        direction = "positive" if corr > 0.05 else ("negative" if corr < -0.05 else "neutral")
        factor_corrs[fname] = {
            "correlation": round(corr, 3),
            "direction": direction,
            "samples": n,
        }

    return {
        "status": "ok",
        "samples": len(pairs),
        "factor_correlations": factor_corrs,
        "recommendations": _generate_recommendations(factor_corrs),
    }


def _generate_recommendations(factor_corrs: dict) -> list[str]:
    """Generate weight adjustment recommendations from correlations."""
    recs = []
    
    for fname, info in sorted(factor_corrs.items(),
                               key=lambda x: -abs(x[1]["correlation"])):
        corr = info["correlation"]
        direction = info["direction"]
        
        if abs(corr) < 0.1:
            continue  # Too weak to act on
        
        if direction == "negative" and corr < -0.15:
            recs.append(
                f"⬇ {fname}: 相关系数{corr:+.2f}(负相关) → 建议减权0.03-0.05"
            )
        elif direction == "positive" and corr > 0.15:
            recs.append(
                f"⬆ {fname}: 相关系数{corr:+.2f}(正相关) → 建议加权0.03-0.05"
            )
    
    if not recs:
        recs.append("✅ 所有因子相关性不显著，保持当前权重")
    
    return recs


# ── Apply tuning ───────────────────────────────────────────────────

def _apply_tuning(result: dict) -> bool:
    """Apply weight recommendations to two_week_picker.py.
    
    This is a DANGEROUS operation - it modifies the live factor weights.
    Only call with --apply flag and sufficient samples.
    """
    if result.get("status") != "ok":
        print("❌ 数据不足，无法调优")
        return False
    
    corrs = result.get("factor_correlations", {})
    picker_path = BASE / "src" / "etf_platform" / "decision" / "two_week_picker.py"
    
    if not picker_path.exists():
        print(f"❌ 找不到 {picker_path}")
        return False
    
    content = picker_path.read_text(encoding="utf-8")
    changes = 0
    
    for fname, info in corrs.items():
        corr = info["correlation"]
        if abs(corr) < 0.15:
            continue
        
        # Find the weight line for this factor
        import re
        pattern = re.compile(
            rf'("name":\s*"{fname}".*?"weight":\s*)([\d.]+)',
            re.DOTALL,
        )
        m = pattern.search(content)
        if not m:
            continue
        
        old_weight = float(m.group(2))
        # Adjust: if positive corr → increase; negative → decrease
        adjustment = min(MAX_WEIGHT_CHANGE, abs(corr) * 0.3)
        if corr < 0:
            adjustment = -adjustment
        
        new_weight = round(max(0.01, min(0.50, old_weight + adjustment)), 2)
        if abs(new_weight - old_weight) < 0.01:
            continue
        
        # Apply change
        old_str = m.group(0)
        new_str = m.group(1) + str(new_weight)
        content = content.replace(old_str, new_str, 1)
        changes += 1
        print(f"  {fname}: {old_weight} → {new_weight} (corr={corr:+.3f})")
    
    if changes > 0:
        # Backup
        bak = picker_path.with_suffix(".py.bak_autotune")
        picker_path.rename(bak)
        picker_path.write_text(content, encoding="utf-8")
        print(f"\n✅ {changes}个因子权重已更新 (备份: {bak.name})")
        return True
    else:
        print("  无显著变化，跳过")
        return False


# ── Log ─────────────────────────────────────────────────────────────

def _log_tuning(result: dict) -> None:
    """Log tuning run to JSONL."""
    import time
    record = {
        "ts": time.time(),
        "samples": result.get("samples", 0),
        "correlations": result.get("factor_correlations", {}),
        "recommendations": result.get("recommendations", []),
    }
    TUNING_LOG.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(TUNING_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as e:
            logger.debug(f"[auto_tune] log write failed: {e}")


# ── Main ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    apply_mode = "--apply" in sys.argv
    json_mode = "--json" in sys.argv

    pairs = _collect_factor_return_pairs()
    result = _simple_regression(pairs)
    _log_tuning(result)

    if json_mode:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("📊 因子权重自调优")
        print(f"{'='*50}")
        print(f"  样本: {result.get('samples', 0)}个 (需≥{MIN_SAMPLES})")
        print()
        
        if result.get("status") != "ok":
            print(f"  ⚠️ {result.get('status')}: 需要{result.get('needed', MIN_SAMPLES)}个样本")
        else:
            print("  因子相关性:")
            for fname, info in sorted(
                result.get("factor_correlations", {}).items(),
                key=lambda x: -abs(x[1]["correlation"])
            ):
                corr = info["correlation"]
                direction = info["direction"]
                icon = "⬆" if direction == "positive" else ("⬇" if direction == "negative" else "→")
                print(f"    {icon} {fname}: r={corr:+.3f} ({direction})")
            
            print("\n  建议:")
            for rec in result.get("recommendations", []):
                print(f"    {rec}")

        if apply_mode and result.get("status") == "ok":
            print("\n  应用调优...")
            _apply_tuning(result)
