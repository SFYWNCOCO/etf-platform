#!/usr/bin/env python3
"""
unified_runner.py — ETF预测统一入口 v1.1

设计目标: 一个命令跑完全流程，自动利用所有优化。
  - DataHub 共享数据（消除重复请求）
  - 并行执行4个预测源 (ThreadPoolExecutor, max ≈ 最慢源而非总和)
  - 锦标赛缓存去重
  - 自动记录预测 + 校准 + 解释

用法:
  python -m etf_platform.decision.unified_runner               # 全量预测
  python -m etf_platform.decision.unified_runner --quick       # 快速模式(仅zscore)
  python -m etf_platform.decision.unified_runner --json        # JSON输出
  python -m etf_platform.decision.unified_runner --bench       # 性能基准
"""

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent.parent  # etf-platform/
DATA_DIR = BASE / "data"
LOG_FILE = DATA_DIR / "unified_predictions.jsonl"


@dataclass(slots=True)
class RunStats:
    """Performance metrics for a prediction run."""
    mode: str = ""
    total_seconds: float = 0
    source_timings: dict[str, float] = field(default_factory=dict)
    sources_active: int = 0
    sources_total: int = 4
    data_fetch_seconds: float = 0
    fusion_seconds: float = 0
    cache_hits: int = 0


def _try_import(module_path: str):
    """Safe import that returns None on failure."""
    import importlib
    try:
        return importlib.import_module(module_path)
    except ImportError:
        return None


def run_prediction(
    profile: str = "均衡",
    quick: bool = False,
    debug: bool = False,
) -> dict:
    """Run unified prediction across all available sources.

    Args:
        profile: Risk profile ("均衡" / "激进")
        quick: Only run Z-score (skip ML, tournament, events)
        debug: Verbose output

    Returns:
        dict with predictions, explanations, meta_info, run_stats
    """
    t0 = time.time()
    stats = RunStats(mode="quick" if quick else "full")

    # ── Step 1: Shared data (try DataHub first) ──────────────────────
    t_data = time.time()
    regime = "normal"

    # Try DataHub (may not exist yet — sub-agent building it)
    data_hub = _try_import("etf_platform.data_hub")
    if data_hub:
        try:
            from etf_platform.startup import get_cached_candidates
            codes = [c for c, _ in get_cached_candidates(max_candidates=80)]

            hub = data_hub.DataHub.get_instance()
            trends = hub.get_kline_data(codes)
            _pipes = hub.get_pipeline_data(list(trends.keys()))  # noqa: F841 — cached for subsequent source access
            regime_data = hub.get_regime()
            regime = regime_data.get("regime", "normal")
            stats.cache_hits = 1
            if debug:
                print(f"[DataHub] 共享缓存命中, 数据获取: {time.time()-t_data:.1f}s")
        except (AttributeError, KeyError, ValueError, TypeError, OSError) as e:
            if debug:
                print(f"[DataHub] 不可用: {e}, 降级到独立获取")
    else:
        # Fallback: each source fetches independently
        try:
            from etf_platform.analysis.qvix_regime import get_regime
            rd = get_regime()
            regime = rd.get("regime", "normal")
        except (ImportError, KeyError, ValueError, TypeError, AttributeError, OSError):
            pass

    stats.data_fetch_seconds = round(time.time() - t_data, 2)

    # ── Step 2: Run prediction sources (parallel) ───────────────────
    predictions: dict[str, list[dict]] = {}
    explanations: list[dict] = []

    def _source_zscore() -> list[dict]:
        from etf_platform.decision.two_week_picker import pick_top3
        n = 30 if quick else 80
        top3, _ = pick_top3(profile=profile, max_candidates=n, debug=debug,
                            skip_tournament=True)
        return top3

    def _source_ml() -> list[dict]:
        from etf_platform.decision.ml_predictor import predict_top3
        return predict_top3(retrain=False, debug=debug)

    def _source_tournament() -> list[dict]:
        from etf_platform.decision.strategy_tournament import get_ensemble_picks
        return get_ensemble_picks()

    def _source_events() -> list[dict]:
        from etf_platform.analysis.event_nlp import get_sector_signals
        return get_sector_signals(use_cache=True)

    def _run_source(name: str, fn) -> tuple[str, list[dict], float, str | None]:
        """Execute a source, return (name, predictions, elapsed, error)."""
        t_src = time.time()
        try:
            preds = fn()
            return (name, preds, time.time() - t_src, None)
        except (ImportError, KeyError, ValueError, TypeError,
                AttributeError, OSError, RuntimeError) as e:
            return (name, [], time.time() - t_src, str(e))

    if quick:
        _, preds, elapsed, _ = _run_source("zscore", _source_zscore)
        predictions["zscore"] = preds
        stats.source_timings["zscore"] = round(elapsed, 2)
        stats.sources_active = 1 if preds else 0
        stats.sources_total = 1
        if debug and not preds:
            print("[Z-score] 失败: 无产出")
    else:
        SOURCE_MAP = [
            ("zscore", _source_zscore),
            ("ml", _source_ml),
            ("tournament", _source_tournament),
            ("events", _source_events),
        ]
        with ThreadPoolExecutor(max_workers=len(SOURCE_MAP)) as executor:
            futures = {
                executor.submit(_run_source, name, fn): name
                for name, fn in SOURCE_MAP
            }
            for future in as_completed(futures):
                name, preds, elapsed, error = future.result()
                predictions[name] = preds
                stats.source_timings[name] = round(elapsed, 2)
                if preds:
                    stats.sources_active += 1
                elif error and debug:
                    print(f"[{name}] 失败: {error}")

    # ── Step 3: Fuse predictions ────────────────────────────────────
    t_fuse = time.time()
    fused_top3: list[dict] = []

    try:
        from etf_platform.decision.meta_predictor import _fuse_predictions, _get_source_confidence
        source_confs = {
            name: _get_source_confidence(name)
            for name in predictions
            if predictions[name]
        }
        fused_top3 = _fuse_predictions(predictions, source_confs)
    except (ImportError, KeyError, ValueError, TypeError, AttributeError, OSError):
        # Fallback: just use Z-score top3
        fused_top3 = predictions.get("zscore", [])[:3]

    # Ensure source_confs is always defined for allocation step
    if "source_confs" not in dir():
        source_confs = {}

    stats.fusion_seconds = round(time.time() - t_fuse, 2)

    # ── Step 4: Generate explanations ────────────────────────────────
    try:
        from etf_platform.decision.prediction_explainer import explain_top3
        expls = explain_top3(fused_top3, source="unified")
        import dataclasses
        explanations = [dataclasses.asdict(e) for e in expls]
    except (ImportError, KeyError, ValueError, TypeError, AttributeError, OSError):
        pass

    # ── Step 4.5: Generate allocation ─────────────────────────────────
    allocation_result = {}
    try:
        from etf_platform.decision.position_allocator import allocate as run_allocate
        # Get transition probs if available
        transition_probs = {}
        try:
            from etf_platform.decision.regime_transition import predict_transition
            tp = predict_transition(current_regime=regime)
            import dataclasses
            transition_probs = dataclasses.asdict(tp)
        except (ImportError, KeyError, ValueError, TypeError, AttributeError, OSError):
            pass

        # Get risk flags if available
        risk_flags = None
        try:
            from etf_platform.decision.risk_manager import check_risk_flags
            risk_flags = check_risk_flags()
        except (ImportError, KeyError, ValueError, TypeError, AttributeError, OSError):
            pass

        alloc = run_allocate(
            fused_top3=fused_top3,
            regime=regime,
            source_confidences=source_confs,
            transition_probs=transition_probs,
            profile=profile,
            risk_flags=risk_flags,
        )
        import dataclasses
        allocation_result = dataclasses.asdict(alloc)
    except (ImportError, KeyError, ValueError, TypeError, AttributeError, OSError):
        pass

    # ── Step 5: Log prediction ───────────────────────────────────────
    try:
        from etf_platform.decision.prediction_monitor import log_prediction
        log_prediction(fused_top3, profile)
    except (ImportError, KeyError, ValueError, TypeError, AttributeError, OSError):
        pass

    stats.total_seconds = round(time.time() - t0, 2)

    # ── Build result ─────────────────────────────────────────────────
    result = {
        "date": date.today().isoformat(),
        "timestamp": datetime.now().isoformat(),
        "profile": profile,
        "regime": regime,
        "mode": stats.mode,
        "fused_top3": fused_top3,
        "explanations": explanations,
        "allocation": allocation_result,
        "predictions_by_source": {
            name: len(preds) for name, preds in predictions.items()
        },
        "run_stats": {
            "total_seconds": stats.total_seconds,
            "source_timings": stats.source_timings,
            "sources_active": stats.sources_active,
            "sources_total": stats.sources_total,
            "data_fetch_seconds": stats.data_fetch_seconds,
            "fusion_seconds": stats.fusion_seconds,
            "cache_hits": stats.cache_hits,
        },
    }

    # Log to JSONL
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(result, ensure_ascii=False) + "\n")
    except OSError:
        pass

    return result


def format_report(result: dict) -> str:
    """Format unified prediction as readable report."""
    rs = result.get("run_stats", {})
    lines = [
        "🚀 ETF预测统一报告",
        f"{'=' * 65}",
        f"  日期: {result['date']}",
        f"  市场: {result.get('regime', '?').upper()}",
        f"  模式: {result.get('mode', '?')}",
        f"  耗时: {rs.get('total_seconds', 0)}s",
        f"  在线: {rs.get('sources_active', 0)}/{rs.get('sources_total', 4)}源",
        "",
    ]

    # Top 3
    fused = result.get("fused_top3", [])
    if fused:
        lines.append("  ── 融合 Top3 ──")
        for i, p in enumerate(fused, 1):
            sources_str = "+".join(p.get("sources", []))
            score = p.get("weighted_score", p.get("score", "?"))
            lines.append(
                f"  {i}. {p['code']} {p.get('name','')[:20]} "
                f"[{p.get('sector','')}] {score}分 ({sources_str})"
            )
    else:
        lines.append("  ⚠️ 无融合预测")

    # Allocation section
    alloc = result.get("allocation", {})
    if alloc and alloc.get("holdings"):
        lines.append("")
        lines.append("  ── 持仓分配 ──")
        lines.append(f"  方法: {alloc.get('allocation_method', '?')}")
        lines.append(f"  总仓位: {alloc.get('total_exposure', 0):.0%} | 现金: {alloc.get('cash_reserve', 0):.0%}")
        for h in alloc.get("holdings", []):
            lines.append(
                f"  → {h['code']} {h['name'][:10]:<10s} 权重={h['weight']:.0%}"
                f" (原始={h['raw_weight']:.0%})"
            )
            if h.get("reason"):
                lines.append(f"     {h['reason']}")
        if alloc.get("constraints_applied"):
            lines.append("  触发约束:")
            for c in alloc["constraints_applied"]:
                lines.append(f"    • {c}")
        if alloc.get("notes"):
            lines.append("  备注:")
            for n in alloc["notes"]:
                lines.append(f"    {n}")
    else:
        lines.append("")
        lines.append("  ⚠️ 无分配结果（分配模块未加载）")

    # Performance breakdown
    lines.append("")
    lines.append("  ── 性能分解 ──")
    for src, t in rs.get("source_timings", {}).items():
        bar = "█" * min(int(t / rs.get("total_seconds", 1) * 30), 30)
        lines.append(f"  {src:<12s} {bar} {t:.1f}s")

    lines.append("")
    lines.append(f"{'=' * 65}")
    lines.append("统一预测器 v1.0 · 不构成投资建议")

    return "\n".join(lines)


# ── CLI ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ETF预测统一入口")
    parser.add_argument("--quick", action="store_true", help="快速模式(仅Z-score)")
    parser.add_argument("--json", action="store_true", help="JSON输出")
    parser.add_argument("--bench", action="store_true", help="性能基准测试")
    parser.add_argument("--profile", type=str, default="均衡", help="风险偏好")
    args = parser.parse_args()

    if args.bench:
        print("⏱️ 性能基准测试...", file=sys.stderr)
        # Quick mode benchmark
        t0 = time.time()
        r1 = run_prediction(profile=args.profile, quick=True, debug=False)
        t_quick = time.time() - t0
        print(f"  快速模式: {t_quick:.1f}s", file=sys.stderr)

        # Full mode benchmark
        t0 = time.time()
        r2 = run_prediction(profile=args.profile, quick=False, debug=False)
        t_full = time.time() - t0
        print(f"  全量模式: {t_full:.1f}s ({r2['run_stats']['sources_active']}/4源)", file=sys.stderr)

        print("\n  === 基准结果 ===")
        print(f"  快速: {t_quick:.1f}s | 全量: {t_full:.1f}s")
        print(f"  节省: {(1-t_full/t_quick)*100:.0f}% (如果quick更快)")
    else:
        result = run_prediction(
            profile=args.profile,
            quick=args.quick,
            debug=True,
        )

        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(format_report(result))
