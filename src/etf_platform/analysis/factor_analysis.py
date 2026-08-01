from __future__ import annotations
#!/usr/bin/env python3
"""factor_analysis.py — Z-score因子有效性实证分析

对two_week_picker.py中定义的8个因子，计算其与10日收益(change_10d)的
Spearman和Pearson相关性，按市场状态(regime)分层分析。

输出:
  - data/factor_effectiveness.json  (因子IC、显著性、推荐权重调整)
"""
import logging
logger = logging.getLogger(__name__)

import json
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scipy import stats

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE = Path(__file__).resolve().parent.parent.parent.parent  # etf-platform root
DATA_DIR = BASE / "data"
OUTPUT_FILE = DATA_DIR / "factor_effectiveness.json"

sys.path.insert(0, str(BASE / "src"))


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class FactorRecord:
    """Single ETF observation: raw factor values + return."""
    code: str
    name: str
    sector: str
    regime: str
    # Raw factor values (pre-Z-score)
    trend_momentum: float = 0.0        # change_20d
    risk_adj_momentum: float = 0.0     # change_20d / vol
    quality_elastic: float = 0.0       # -pipeline_score
    behavioral: float = 0.0            # behavioral_alpha - 50
    oversold_depth: float = 0.0        # -change_20d
    drawdown_recov: float = 0.0        # -max_drawdown
    sector_flow: float = 0.0           # sector flow return_pct
    # Forward return proxy
    change_10d: float = 0.0
    change_20d: float = 0.0
    volatility: float = 0.0
    max_drawdown: float = 0.0
    position_pct: float = 50.0
    volume_ratio: float = 1.0
    pipeline_score: float = 5.0


# ---------------------------------------------------------------------------
# Factor helpers (mirror two_week_picker.py logic)
# ---------------------------------------------------------------------------
def _zscore(values: list[float], cap: float = 3.0) -> list[float]:
    n = len(values)
    if n < 3:
        return [0.0] * n
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / n
    std = variance ** 0.5
    if std < 1e-10:
        return [0.0] * n
    z = [(v - mean) / std for v in values]
    return [max(-cap, min(cap, v)) for v in z]


def _calc_behavioral_alpha(pipe: dict) -> float:
    ls = pipe.get("layer_scores", {})
    overreact = ls.get("L21_Overreaction", 5.0)
    herding = ls.get("L21_Herding", 5.0)
    contrarian = ls.get("L21_Contrarian", 5.0)
    alpha = (overreact - 5.0) * 12 + (5.0 - herding) * 5 + (contrarian - 5.0) * 8
    return max(10, min(90, 50 + alpha))


def _get_sector_flow_raw(sector: str, code: str = "", ttl_secs: int = 600) -> float:
    cache_key = f"{sector}:{code}"
    import time as _time
    now = _time.time()
    if hasattr(_get_sector_flow_raw, "_cache"):
        entry = _get_sector_flow_raw._cache.get(cache_key)  # type: ignore[attr-defined]
        if entry and (now - entry[0]) < ttl_secs:
            return entry[1]  # (timestamp, value)
    try:
        from etf_platform.analysis.sector_flow_bridge import get_bridge
        bridge = get_bridge()
        result = bridge.score(sector, live=False, etf_code=code)
        raw = result.get("_return_pct", 0)
        if not hasattr(_get_sector_flow_raw, "_cache"):
            _get_sector_flow_raw._cache = {}  # type: ignore[attr-defined]
        _get_sector_flow_raw._cache[cache_key] = (now, raw)  # type: ignore[attr-defined]
        return raw
    except (ImportError, KeyError, ValueError, TypeError, AttributeError, OSError):
        return 0.0


# ---------------------------------------------------------------------------
# Regime detection
# ---------------------------------------------------------------------------
def _detect_regime(trend_signal: str, qvix_data: dict) -> str:
    """Map each ETF to a regime based on QVIX + individual trend signal.

    When QVIX has only one regime, we stratify by individual ETF trend
    characteristics to enable meaningful per-regime analysis.
    """
    qvix_regime = qvix_data.get("regime", "normal")
    regime_map = {
        "complacent": "greedy",
        "normal": "neutral",
        "cautious": "neutral",
        "fearful": "fearful",
    }
    primary = regime_map.get(qvix_regime, "neutral")

    # If all ETFs would fall into the same regime, stratify by trend signal
    # to create meaningful sub-groups for comparison
    if primary == "fearful":
        if trend_signal in ("plunging", "oversold"):
            return "fearful_deep"
        elif trend_signal in ("weak",):
            return "fearful_mild"
        else:
            return "fearful_neutral"
    elif primary == "greedy":
        if trend_signal in ("surging", "strong"):
            return "greedy_strong"
        else:
            return "greedy_mild"
    else:
        return primary


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------
def collect_factor_data(max_etfs: int = 120) -> list[FactorRecord]:
    """Collect factor values and returns for all available ETFs.

    Uses get_trend() session cache (no akshare calls). Pipeline scores are
    attempted but optional — missing scores default to 5.0.
    """
    from etf_platform.config_loader import load_etfs
    from etf_platform.data.kline import get_trend

    EXCLUDE_SECTORS = {
        "货币基金", "利率债", "信用债", "债券", "国债", "货币",
    }
    EXCLUDE_KEYWORDS = [
        "沪深300", "中证500", "中证1000", "上证50", "深证100",
        "创业板", "科创50", "科创100",
    ]

    etfs = load_etfs()
    candidates: list[tuple[str, dict]] = []
    for code, info in etfs.items():
        if not code.isdigit():
            continue
        if info.get("sector", "") in EXCLUDE_SECTORS:
            continue
        if info.get("access") != "buyable":
            continue
        name = info.get("name", "")
        if any(kw in name for kw in EXCLUDE_KEYWORDS):
            continue
        if info.get("type") == "宽基A":
            continue
        if info.get("sector") in ("宽基", "全市场"):
            continue
        candidates.append((code, info))

    # Limit for performance
    if len(candidates) > max_etfs:
        candidates = candidates[:max_etfs]

    # QVIX regime
    qvix_data: dict[str, Any] = {"regime": "normal"}
    try:
        from etf_platform.analysis.qvix_regime import get_regime
        qvix_data = get_regime()
    except (ImportError, KeyError, ValueError, TypeError, AttributeError, OSError) as e:
            logger.debug(f"[factor] QVIX regime failed: {e}")

    records: list[FactorRecord] = []
    errors: list[str] = []

    for code, info in candidates:
        try:
            trend = get_trend(code)
            if trend is None or trend.data_days < 10:
                continue

            # Run pipeline for score (optional, may fail silently)
            pipe_score = 5.0
            behavioral_raw = 0.0  # Will be set below
            try:
                from etf_platform.pipeline import run_full
                pipe = run_full(code, live=False, profile="均衡")
                pipe_score = pipe.get("score", 5.0)

                # Compute behavioral proxy from available layers
                # L21 layers may not exist; fall back to L8/L9/L16 signals
                ls = pipe.get("layer_scores", {})
                l9 = ls.get("L9_Signals", 5.0)
                l16 = ls.get("L16_LiveSignals", 5.0)
                l17 = ls.get("L17_Factor", 5.0)
                # Behavioral proxy: signal momentum + factor quality
                # Higher L9/L16/L17 = more positive sentiment/catalyst
                behavioral_raw = (l9 - 5.0) * 0.3 + (l16 - 5.0) * 0.3 + (l17 - 5.0) * 0.4
                behavioral_raw = max(-10, min(10, behavioral_raw))
            except (ImportError, KeyError, ValueError, TypeError, AttributeError, OSError) as e:
                    logger.debug(f"[factor_analysis] L9/L16/L17 proxy failed: {e}")

            sector = info.get("sector", "未知")
            record = FactorRecord(
                code=code,
                name=info.get("name", code),
                sector=sector,
                regime=_detect_regime(trend.trend_signal, qvix_data),
                trend_momentum=trend.change_20d,
                risk_adj_momentum=trend.change_20d / max(trend.volatility_20d, 1),
                quality_elastic=-pipe_score,
                behavioral=behavioral_raw,
                oversold_depth=-trend.change_20d,
                drawdown_recov=-trend.max_drawdown,
                sector_flow=_get_sector_flow_raw(sector, code),
                change_10d=trend.change_10d,
                change_20d=trend.change_20d,
                volatility=trend.volatility_20d,
                max_drawdown=trend.max_drawdown,
                position_pct=trend.position_pct,
                volume_ratio=trend.volume_ratio_5_20,
                pipeline_score=pipe_score,
            )
            records.append(record)

        except (KeyError, ValueError, TypeError, AttributeError, OSError) as e:
            errors.append(f"{code}: {e}")
            continue

    print(f"  有效样本: {len(records)}只ETF | 错误: {len(errors)}只")
    return records, qvix_data


def compute_correlations(records: list[FactorRecord]) -> dict[str, Any]:
    """Compute Spearman and Pearson correlations for each factor vs change_10d."""
    factor_names = [
        "trend_momentum", "risk_adj_momentum", "quality_elastic",
        "behavioral", "oversold_depth", "drawdown_recov", "sector_flow",
    ]

    # Overall correlations
    overall: dict[str, dict[str, float]] = {}
    for fname in factor_names:
        raw_vals = [getattr(r, fname) for r in records]
        returns = [r.change_10d for r in records]
        n = len(raw_vals)
        if n < 5:
            overall[fname] = {"n": n, "pearson_r": 0.0, "spearman_rho": 0.0,
                              "p_pearson": 1.0, "p_spearman": 1.0}
            continue

        # Skip if any input is constant (correlation undefined)
        unique_raw = len(set(raw_vals))
        unique_ret = len(set(returns))
        if unique_raw <= 1 or unique_ret <= 1:
            overall[fname] = {
                "n": n, "pearson_r": 0.0, "spearman_rho": 0.0,
                "p_pearson": 1.0, "p_spearman": 1.0,
                "note": "constant_input",
            }
            continue

        pearson_r, p_pearson = stats.pearsonr(raw_vals, returns)
        spearman_rho, p_spearman = stats.spearmanr(raw_vals, returns)

        overall[fname] = {
            "n": n,
            "pearson_r": round(float(pearson_r), 4),
            "p_pearson": round(float(p_pearson), 4),
            "spearman_rho": round(float(spearman_rho), 4),
            "p_spearman": round(float(p_spearman), 4),
        }

    # Per-regime correlations
    regime_groups: dict[str, list[FactorRecord]] = defaultdict(list)
    for r in records:
        regime_groups[r.regime].append(r)

    regime_results: dict[str, dict[str, dict[str, float]]] = {}
    for regime, group in sorted(regime_groups.items()):
        regime_result = {}
        for fname in factor_names:
            raw_vals = [getattr(r, fname) for r in group]
            returns = [r.change_10d for r in group]
            n = len(raw_vals)
            if n < 5:
                regime_result[fname] = {"n": n, "pearson_r": 0.0, "spearman_rho": 0.0,
                                        "p_pearson": 1.0, "p_spearman": 1.0}
                continue
            # Skip if any input is constant
            if len(set(raw_vals)) <= 1 or len(set(returns)) <= 1:
                regime_result[fname] = {
                    "n": n, "pearson_r": 0.0, "spearman_rho": 0.0,
                    "p_pearson": 1.0, "p_spearman": 1.0,
                    "note": "constant_input",
                }
                continue
            pearson_r, p_pearson = stats.pearsonr(raw_vals, returns)
            spearman_rho, p_spearman = stats.spearmanr(raw_vals, returns)
            regime_result[fname] = {
                "n": n,
                "pearson_r": round(float(pearson_r), 4),
                "p_pearson": round(float(p_pearson), 4),
                "spearman_rho": round(float(spearman_rho), 4),
                "p_spearman": round(float(p_spearman), 4),
            }
        regime_results[regime] = regime_result

    return {
        "overall": overall,
        "by_regime": regime_results,
    }


def generate_recommendations(
    correlations: dict[str, Any],
    records: list[FactorRecord],
) -> dict[str, Any]:
    """Generate weight adjustment recommendations based on IC (|rho|)."""
    factor_names = [
        "trend_momentum", "risk_adj_momentum", "quality_elastic",
        "behavioral", "oversold_depth", "drawdown_recov", "sector_flow",
    ]

    # Current weights from two_week_picker.py
    current_weights = {
        "trend_momentum": 0.25,
        "risk_adj_momentum": 0.25,
        "quality_elastic": 0.15,
        "behavioral": 0.15,
        "oversold_depth": 0.12,
        "drawdown_recov": 0.07,
        "sector_flow": 0.10,
    }

    # Extract overall IC (absolute Spearman rho)
    ic_values: dict[str, float] = {}
    for fname in factor_names:
        ov = correlations["overall"].get(fname, {})
        ic_values[fname] = abs(ov.get("spearman_rho", 0.0))

    # Rank factors by IC
    ranked = sorted(ic_values.items(), key=lambda x: -x[1])

    # Generate recommendations
    recommendations: list[dict[str, Any]] = []
    total_ic = sum(ic_values.values()) or 1.0

    for fname, ic in ranked:
        current_w = current_weights.get(fname, 0.0)
        # Normalize IC to get suggested weight (proportional to |rho|)
        suggested_w = round(ic / total_ic, 3) if total_ic > 0 else 0.0
        delta = round(suggested_w - current_w, 3)

        strength = "强" if abs(ic) > 0.2 else ("中等" if abs(ic) > 0.1 else "弱")
        direction = "增加" if delta > 0.01 else ("减少" if delta < -0.01 else "维持")

        recommendations.append({
            "factor": fname,
            "ic_abs": round(ic, 4),
            "strength": strength,
            "current_weight": current_w,
            "suggested_weight": suggested_w,
            "delta": delta,
            "direction": direction,
            "significant": correlations["overall"].get(fname, {}).get("p_spearman", 1.0) < 0.05,
        })

    # Summary
    summary = {
        "total_samples": len(records),
        "regimes_seen": list(correlations["by_regime"].keys()),
        "regime_counts": {
            r: sum(1 for rec in records if rec.regime == r)
            for r in sorted({rec.regime for rec in records})
        },
        "top_factors_by_ic": [{"factor": f, "ic": round(v, 4)} for f, v in ranked],
        "recommendations": recommendations,
        "notes": [],
    }

    # Add notes about collinearity
    tm_rho = correlations["overall"]["trend_momentum"]["spearman_rho"]
    os_rho = correlations["overall"]["oversold_depth"]["spearman_rho"]
    if abs(tm_rho + os_rho) > 1.5:
        summary["notes"].append(
            "警告: trend_momentum与oversold_depth高度负相关(互为反向)，"
            "同时使用可能导致信号冗余"
        )

    ra_rho = correlations["overall"]["risk_adj_momentum"]["spearman_rho"]
    if abs(tm_rho - ra_rho) < 0.15:
        summary["notes"].append(
            "警告: trend_momentum与risk_adj_momentum高度正相关，"
            "两者合计权重50%可能过度暴露于单一方向"
        )

    zero_ic = [r["factor"] for r in recommendations if abs(r["ic_abs"]) < 0.05]
    if zero_ic:
        summary["notes"].append(
            f"注意: 以下因子IC接近零({zero_ic})，预测力极弱，建议大幅降权或移除"
        )

    return summary


def run_analysis() -> dict[str, Any]:
    """Main entry point: collect data, compute correlations, output JSON."""
    print("=" * 60)
    print("Z-score因子有效性分析")
    print("=" * 60)

    t0 = time.time()

    # Step 1: Collect factor data
    print("\n[1/3] 收集因子数据...")
    records, qvix_data = collect_factor_data(max_etfs=120)

    if len(records) < 10:
        result = {
            "status": "insufficient_data",
            "sample_count": len(records),
            "message": f"有效样本仅{len(records)}只(<10)，无法进行有意义的统计分析",
        }
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n⚠️  数据不足，已保存: {OUTPUT_FILE}")
        return result

    # Step 2: Compute correlations
    print("[2/3] 计算相关性(Spearman + Pearson)...")
    correlations = compute_correlations(records)

    # Step 3: Generate recommendations
    print("[3/3] 生成权重调整建议...")
    recommendations = generate_recommendations(correlations, records)

    # Build output
    elapsed = round(time.time() - t0, 1)

    output = {
        "analysis_version": "1.0",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "elapsed_seconds": elapsed,
        "sample_count": len(records),
        "qvix_regime": qvix_data.get("regime", "unknown"),
        "factor_definitions": {
            "trend_momentum": "Z(change_20d) — 趋势动量",
            "risk_adj_momentum": "Z(change_20d / volatility) — 风险调整动量",
            "quality_elastic": "Z(-pipeline_score) — 质量弹性(低分=高弹性)",
            "behavioral": "Z(behavioral_alpha - 50) — 行为Alpha",
            "oversold_depth": "Z(-change_20d) — 超跌深度(博弈反弹)",
            "drawdown_recov": "Z(-max_drawdown) — 回撤修复潜力",
            "sector_flow": "Z(sector_return_pct) — 行业资金流",
        },
        "correlations": correlations,
        "weight_recommendations": recommendations,
        "raw_records_sample": [
            {
                "code": r.code,
                "sector": r.sector,
                "regime": r.regime,
                "factors": {
                    fn: round(getattr(r, fn), 3)
                    for fn in ["trend_momentum", "risk_adj_momentum",
                               "quality_elastic", "behavioral",
                               "oversold_depth", "drawdown_recov",
                               "sector_flow"]
                },
                "change_10d": round(r.change_10d, 2),
            }
            for r in records[:10]
        ],
    }

    # Save
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 结果已保存: {OUTPUT_FILE}")
    print(f"   耗时: {elapsed}s | 样本: {len(records)}只ETF")

    return output


def print_summary(output: dict[str, Any]) -> None:
    """Print a human-readable summary to stdout."""
    corr = output.get("correlations", {})
    overall = corr.get("overall", {})
    recs = output.get("weight_recommendations", {})

    print("\n" + "=" * 60)
    print("因子有效性分析摘要")
    print("=" * 60)
    print(f"\n样本数: {output.get('sample_count', 0)}只ETF")
    print(f"QVIX状态: {output.get('qvix_regime', '?')}")
    print(f"耗时: {output.get('elapsed_seconds', '?')}s")

    print("\n--- 整体因子IC (Spearman ρ vs 10日收益) ---")
    print(f"{'因子':<22s} {'ρ':>6s} {'p值':>8s} {'显著':>4s} {'|ρ|排名'}")
    print("-" * 55)

    sorted_factors = sorted(
        overall.items(),
        key=lambda x: abs(x[1].get("spearman_rho", 0)),
        reverse=True,
    )

    for rank, (fname, vals) in enumerate(sorted_factors, 1):
        rho = vals.get("spearman_rho", 0)
        p = vals.get("p_spearman", 1)
        sig = "***" if p < 0.001 else ("**" if p < 0.01 else ("*" if p < 0.05 else " "))
        print(f"  {fname:<22s} {rho:>6.3f} {p:>8.4f} {sig:>4s} #{rank}")

    print("\n--- 推荐权重调整 ---")
    for rec in recs.get("recommendations", []):
        icon = "↑" if rec["delta"] > 0.01 else ("↓" if rec["delta"] < -0.01 else "→")
        print(
            f"  {icon} {rec['factor']:<22s} "
            f"IC={rec['ic_abs']:.3f} "
            f"当前={rec['current_weight']:.0%} → "
            f"建议={rec['suggested_weight']:.0%} "
            f"({rec['direction']})"
        )

    notes = recs.get("notes", [])
    if notes:
        print("\n--- 注意事项 ---")
        for note in notes:
            print(f"  ⚠️  {note}")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Z-score因子有效性分析 — 相关性回测"
    )
    parser.add_argument("--max-etfs", type=int, default=120, help="最大ETF数")
    parser.add_argument("--quiet", action="store_true", help="不打印摘要")
    parser.add_argument("--json-only", action="store_true", help="仅输出JSON文件")
    args = parser.parse_args()

    output = run_analysis()

    if not args.quiet and not args.json_only:
        print_summary(output)

    if args.json_only:
        print(json.dumps(output, ensure_ascii=False, indent=2))
