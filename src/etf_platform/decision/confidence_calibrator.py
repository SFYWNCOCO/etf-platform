#!/usr/bin/env python3
"""
confidence_calibrator.py — 预测置信度校准器 v1.0

问题: Z-score输出的72分意味着什么？是72%概率正确还是别的？
答案: 需要历史数据来校准——把原始分数映射到经验概率。

方法: 贝叶斯校准(Beta-Binomial)
  - 将分数分桶(每5分一桶,如60-65)
  - 每桶内: (正确次数 + alpha_prior) / (总次数 + alpha_prior + beta_prior)
  - 无数据时回退到先验(50%),样本越多越信任数据
  - Wilson置信区间用于不确定性估计

用法:
  python -m etf_platform.decision.confidence_calibrator
  python -m etf_platform.decision.confidence_calibrator --score 72
  python -m etf_platform.decision.confidence_calibrator --plot

输出:
  calibration.json — 校准曲线(分数→概率+置信区间)
"""

import json
import math
from pathlib import Path
from collections import defaultdict

BASE = Path(__file__).resolve().parent.parent.parent.parent  # etf-platform/
DATA_DIR = BASE / "data"
LOG_FILE = DATA_DIR / "two_week_predictions.jsonl"
CALIBRATION_FILE = DATA_DIR / "calibration.json"

# ── Bayesian calibration ────────────────────────────────────────────

def _load_outcomes() -> list[dict]:
    """Load predictions with verified 10-day outcomes."""
    if not LOG_FILE.exists():
        return []

    from etf_platform.decision.prediction_backtest import _get_etf_returns

    records = []
    with open(LOG_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                pred = json.loads(line)
            except json.JSONDecodeError:
                continue

            for etf in pred.get("top3", []):
                score = etf.get("two_week_score", 50)
                code = etf["code"]
                rets = _get_etf_returns(code, pred["date"], days=10)
                if rets:
                    records.append({
                        "date": pred["date"],
                        "code": code,
                        "name": etf.get("name", ""),
                        "score": score,
                        "return_10d": rets[0],
                        "correct": rets[0] > 0,
                    })

    return records


def _wilson_ci(wins: int, total: int, z: float = 1.96) -> tuple[float, float, float]:
    """Wilson score confidence interval for a proportion.

    Returns (center, lower, upper) for the observed win rate.
    Handles edge cases with zero or all wins.
    """
    if total == 0:
        return 0.5, 0.0, 1.0

    p = wins / total
    denom = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denom
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom

    return p, max(0.0, center - margin), min(1.0, center + margin)


def calibrate(alpha_prior: float = 2.0, beta_prior: float = 2.0) -> dict:
    """Build calibration curve from historical outcomes.

    Args:
        alpha_prior: Prior pseudo-successes (default 2 = weak prior toward 50%)
        beta_prior: Prior pseudo-failures (default 2 = weak prior toward 50%)

    Returns:
        dict with bucket_stats, calibration_curve, and diagnostics
    """
    outcomes = _load_outcomes()
    bucket_size = 5  # Group scores into 5-point buckets

    # Group into buckets
    buckets: dict[int, dict] = defaultdict(lambda: {"wins": 0, "total": 0, "scores": []})

    for o in outcomes:
        bucket_key = int(o["score"] // bucket_size) * bucket_size
        buckets[bucket_key]["total"] += 1
        buckets[bucket_key]["scores"].append(o["score"])
        if o["correct"]:
            buckets[bucket_key]["wins"] += 1

    # Build calibration curve (fill empty buckets with prior)
    calibration_curve: list[dict] = []
    bucket_stats: dict[str, dict] = {}

    for bucket_start in range(30, 100, bucket_size):
        bucket_end = bucket_start + bucket_size
        b = buckets.get(bucket_start, {"wins": 0, "total": 0, "scores": []})

        # Bayesian estimate: (wins + alpha) / (total + alpha + beta)
        wins = b["wins"]
        total = b["total"]
        bayes_prob = (wins + alpha_prior) / (total + alpha_prior + beta_prior) if total >= 0 else 0.5

        # Wilson CI on raw data
        raw_p, ci_low, ci_high = _wilson_ci(wins, total)

        bucket_label = f"{bucket_start}-{bucket_end}"
        entry = {
            "bucket": bucket_label,
            "score_range": [bucket_start, bucket_end],
            "samples": total,
            "wins": wins,
            "raw_win_rate": round(raw_p, 4) if total > 0 else None,
            "calibrated_probability": round(bayes_prob, 4),
            "ci_lower": round(ci_low, 4),
            "ci_upper": round(ci_high, 4),
            "confidence": "high" if total >= 10 else ("medium" if total >= 3 else "low"),
        }
        calibration_curve.append(entry)
        bucket_stats[bucket_label] = entry

    # Overall diagnostics
    total_correct = sum(b["wins"] for b in buckets.values())
    total_samples = sum(b["total"] for b in buckets.values())
    overall_accuracy = total_correct / max(total_samples, 1)

    # Calibration error (how much predicted probability deviates from observed)
    calibration_errors = []
    for entry in calibration_curve:
        if entry["samples"] >= 3:
            mid_score = (entry["score_range"][0] + entry["score_range"][1]) / 2
            predicted_p = mid_score / 100.0  # Assuming score≈probability
            observed_p = entry["raw_win_rate"]
            if observed_p is not None:
                calibration_errors.append({
                    "bucket": entry["bucket"],
                    "mid_score": mid_score,
                    "predicted_p": round(predicted_p, 3),
                    "observed_p": round(observed_p, 3),
                    "error": round(abs(predicted_p - observed_p), 3),
                })

    mean_calibration_error = (
        sum(e["error"] for e in calibration_errors) / len(calibration_errors)
        if calibration_errors else None
    )

    result = {
        "version": "1.0",
        "method": "bayesian_beta_binomial",
        "prior": {"alpha": alpha_prior, "beta": beta_prior},
        "total_predictions": len(outcomes),
        "total_samples": total_samples,
        "total_correct": total_correct,
        "overall_accuracy": round(overall_accuracy, 4),
        "calibration_curve": calibration_curve,
        "calibration_errors": calibration_errors,
        "mean_calibration_error": round(mean_calibration_error, 4) if mean_calibration_error else None,
        "diagnosis": _diagnose(calibration_curve, overall_accuracy),
    }

    return result


def _diagnose(curve: list[dict], accuracy: float) -> list[str]:
    """Generate human-readable diagnosis of calibration quality."""
    diagnoses = []

    valid_buckets = [e for e in curve if e["samples"] >= 3]
    if len(valid_buckets) < 2:
        diagnoses.append("⚠️ 有效样本不足(需要≥3个bucket各≥3样本)，校准曲线不可靠")
        diagnoses.append("   建议: 积累更多预测数据(当前贝叶斯先验主导)")
        return diagnoses

    # Check monotonicity: higher scores should have higher win rates
    rates = [(e["score_range"][0], e["raw_win_rate"]) for e in valid_buckets if e["raw_win_rate"] is not None]
    if len(rates) >= 2:
        monotonic = all(rates[i][1] <= rates[i + 1][1] for i in range(len(rates) - 1))
        if monotonic:
            diagnoses.append("✅ 单调性良好: 高分桶确实对应更高胜率")
        else:
            diagnoses.append("⚠️ 非单调: 高分桶胜率不总是高于低分桶—因子权重可能需要调整")

    # Check if model is systematically over/under confident
    high_buckets = [e for e in valid_buckets if e["score_range"][0] >= 70 and e["raw_win_rate"] is not None]
    if high_buckets:
        avg_observed = sum(e["raw_win_rate"] for e in high_buckets) / len(high_buckets)
        avg_predicted = sum((e["score_range"][0] + e["score_range"][1]) / 200 for e in high_buckets)
        if avg_observed < avg_predicted - 0.1:
            diagnoses.append(f"⚠️ 高分区间过度自信: 预测{avg_predicted:.0%}实际{avg_observed:.0%}")
        elif avg_observed > avg_predicted + 0.1:
            diagnoses.append(f"💡 高分区间过于保守: 预测{avg_predicted:.0%}实际{avg_observed:.0%}")
        else:
            diagnoses.append(f"✅ 高分区间校准良好: 预测{avg_predicted:.0%}≈实际{avg_observed:.0%}")

    if accuracy < 0.45:
        diagnoses.append("⚠️ 整体准确率<45%: 预测模型可能需要根本性重构")
    elif accuracy > 0.65:
        diagnoses.append("✅ 整体准确率>65%: 模型有显著预测能力")
    else:
        diagnoses.append("📊 整体准确率在45-65%: 接近随机但有边际优势")

    return diagnoses


def predict_probability(score: float) -> dict:
    """Convert a raw score to calibrated probability using saved calibration.

    Args:
        score: Raw two_week_score (0-100)

    Returns:
        dict with calibrated_probability, confidence_interval, and source
    """
    if CALIBRATION_FILE.exists():
        with open(CALIBRATION_FILE, encoding="utf-8") as f:
            cal = json.load(f)
    else:
        # No calibration data yet — use prior
        return {
            "score": score,
            "calibrated_probability": 0.5,
            "ci_lower": 0.0,
            "ci_upper": 1.0,
            "confidence": "low",
            "method": "prior_only",
            "note": "无历史数据，使用先验概率50%。积累≥30个预测样本后校准生效。",
        }

    # Find matching bucket
    bucket_size = 5
    bucket_start = int(score // bucket_size) * bucket_size
    bucket_label = f"{bucket_start}-{bucket_start + bucket_size}"

    for entry in cal.get("calibration_curve", []):
        if entry["bucket"] == bucket_label:
            return {
                "score": score,
                "bucket": bucket_label,
                "calibrated_probability": entry["calibrated_probability"],
                "ci_lower": entry["ci_lower"],
                "ci_upper": entry["ci_upper"],
                "samples_in_bucket": entry["samples"],
                "confidence": entry["confidence"],
                "method": "bayesian_calibrated",
            }

    # Score out of range
    return {
        "score": score,
        "calibrated_probability": 0.5,
        "ci_lower": 0.0,
        "ci_upper": 1.0,
        "confidence": "low",
        "method": "extrapolated",
        "note": f"分数{score}超出校准范围(30-100)",
    }


# ── Persistence ─────────────────────────────────────────────────────

def save_calibration(result: dict) -> Path:
    """Save calibration result to disk for fast lookup."""
    CALIBRATION_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CALIBRATION_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return CALIBRATION_FILE


# ── Report ──────────────────────────────────────────────────────────

def format_report(result: dict) -> str:
    """Format calibration results as readable report."""
    lines = [
        "📐 预测置信度校准报告",
        f"{'=' * 60}",
        "",
        "  方法: 贝叶斯Beta-Binomial校准",
        f"  先验: Beta({result['prior']['alpha']}, {result['prior']['beta']}) → 50%弱先验",
        f"  样本: {result['total_samples']}个预测×结果对",
        f"  整体准确率: {result['overall_accuracy']:.1%}",
        "",
        "  校准曲线 (分数 → 校准概率 [95%CI]):",
        f"  {'─' * 52}",
    ]

    for entry in result["calibration_curve"]:
        samples_str = f"n={entry['samples']:>3d}" if entry["samples"] > 0 else "n=  0"
        prob = entry["calibrated_probability"]
        ci = f"[{entry['ci_lower']:.0%}-{entry['ci_upper']:.0%}]"
        conf_mark = {"high": "●", "medium": "◐", "low": "○"}.get(entry["confidence"], "?")
        bar = "█" * int(prob * 20) + "░" * (20 - int(prob * 20))

        lines.append(
            f"  {entry['bucket']:>7}分  {bar} {prob:.0%} {ci} {conf_mark} {samples_str}"
        )

    lines.append("")
    lines.append("  诊断:")
    for d in result.get("diagnosis", []):
        lines.append(f"    {d}")

    if result.get("mean_calibration_error") is not None:
        lines.append("")
        lines.append(f"  平均校准误差: {result['mean_calibration_error']:.3f} "
                     f"(越小越好, <0.05为优秀)")

    lines.append("")
    lines.append(f"{'=' * 60}")

    return "\n".join(lines)


# ── Main ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if "--score" in sys.argv:
        # Quick lookup mode
        idx = sys.argv.index("--score")
        score = float(sys.argv[idx + 1])
        prob = predict_probability(score)
        print(json.dumps(prob, ensure_ascii=False, indent=2))
    else:
        # Full calibration mode
        result = calibrate()
        save_calibration(result)
        print(format_report(result))
