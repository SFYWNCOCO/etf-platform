#!/usr/bin/env python3
"""
integration_test.py — 全系统集成测试 v1.0

一键验证ETF预测系统所有模块的可用性和数据新鲜度。
绿色=正常, 黄色=降级, 红色=异常。

用法:
  python -m etf_platform.decision.integration_test
  python -m etf_platform.decision.integration_test --json
"""

import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

BASE = Path(__file__).resolve().parent.parent.parent.parent  # etf-platform/
DATA_DIR = BASE / "data"


@dataclass(slots=True)
class TestResult:
    name: str
    status: str  # ok / degraded / error
    detail: str = ""
    elapsed_ms: float = 0
    data_freshness: Optional[str] = None  # ISO timestamp or "stale" or "missing"


def _test(name: str, fn, *args, **kwargs) -> TestResult:
    """Run a test and return result."""
    t0 = time.time()
    try:
        result = fn(*args, **kwargs)
        elapsed = (time.time() - t0) * 1000
        if result is None:
            return TestResult(name=name, status="degraded", detail="返回None", elapsed_ms=elapsed)
        if isinstance(result, dict) and result.get("error"):
            return TestResult(name=name, status="degraded", detail=str(result["error"])[:100], elapsed_ms=elapsed)
        if isinstance(result, (list, tuple)) and len(result) == 0:
            return TestResult(name=name, status="degraded", detail="空结果", elapsed_ms=elapsed)
        return TestResult(name=name, status="ok", detail="", elapsed_ms=elapsed)
    except ImportError as e:
        return TestResult(name=name, status="error", detail=f"ImportError: {e}", elapsed_ms=(time.time()-t0)*1000)
    except AttributeError as e:
        # Module exists but function not exported — try direct import
        return TestResult(name=name, status="degraded", detail=f"未导出: {e}", elapsed_ms=(time.time()-t0)*1000)
    except Exception as e:
        return TestResult(name=name, status="error", detail=f"{type(e).__name__}: {e}", elapsed_ms=(time.time()-t0)*1000)


def _import_call(module_path: str, func_name: str):
    """Import a module and call a function from it."""
    import importlib
    mod = importlib.import_module(module_path)
    fn = getattr(mod, func_name)
    return fn()


def _import_only(module_path: str):
    """Just verify module is importable."""
    import importlib
    importlib.import_module(module_path)
    return True


def run_all() -> dict:
    """Run all integration tests."""
    t0 = time.time()
    results: list[TestResult] = []

    # ── Data sources ─────────────────────────────────────────────────
    results.append(_test("akshare import", _import_only, "akshare"))
    results.append(_test("config loader", _import_call, "etf_platform.config_loader", "load_etfs"))

    # ── Kline & Trends ───────────────────────────────────────────────
    results.append(_test(
        "kline.get_trend (510050)",
        lambda: __import__("etf_platform.data.kline", fromlist=["get_trend"]).get_trend("510050"),
    ))

    # ── QVIX ─────────────────────────────────────────────────────────
    def _test_qvix():
        from etf_platform.analysis.qvix_regime import get_regime
        rd = get_regime()
        return {"regime": rd.get("regime"), "qvix_50": rd.get("qvix_50")}
    results.append(_test("QVIX regime", _test_qvix))

    # ── Z-score predictor ────────────────────────────────────────────
    def _test_zscore():
        from etf_platform.decision.two_week_picker import pick_top3
        top3, _ = pick_top3(profile="均衡", max_candidates=20, debug=False)
        return top3
    results.append(_test("Z-score pick_top3 (20只)", _test_zscore))

    # ── NLP events ───────────────────────────────────────────────────
    def _test_events():
        from etf_platform.analysis.event_nlp import process_news_batch
        texts = ["央行降准释放万亿流动性", "芯片制裁升级限制出口", "北向资金净流入创新高"]
        return process_news_batch(texts)
    results.append(_test("NLP事件检测 (3条)", _test_events))

    # ── Confidence calibrator ────────────────────────────────────────
    results.append(_test(
        "置信度校准器",
        _import_call, "etf_platform.decision.confidence_calibrator", "calibrate",
    ))

    # ── Meta predictor ───────────────────────────────────────────────
    def _test_meta():
        from etf_platform.decision.meta_predictor import predict
        return predict(unified=True)
    results.append(_test("MetaPredictor融合", _test_meta))

    # ── Regime transition ────────────────────────────────────────────
    results.append(_test(
        "Regime转换预测",
        _import_call, "etf_platform.decision.regime_transition", "predict_transition",
    ))

    # ── Synthetic backtest ───────────────────────────────────────────
    results.append(_test(
        "合成回测 (5只)",
        _import_call, "etf_platform.decision.synthetic_backtest", "run_quick_scan",
    ))

    # ── ML predictor (import only) ───────────────────────────────────
    results.append(_test(
        "ML预测器 (import)",
        _import_only, "etf_platform.decision.ml_predictor",
    ))

    # ── Strategy tournament (import only) ────────────────────────────
    results.append(_test(
        "策略锦标赛 (import)",
        _import_only, "etf_platform.decision.strategy_tournament",
    ))

    # ── Data freshness ───────────────────────────────────────────────
    def _check_freshness():
        fresh: dict[str, str] = {}
        # QVIX cache
        qvix_cache = DATA_DIR / "live_cache" / "qvix_regime.json"
        if qvix_cache.exists():
            age = time.time() - qvix_cache.stat().st_mtime
            fresh["qvix_cache"] = f"{age/3600:.1f}h前" if age > 3600 else f"{age/60:.0f}min前"
        else:
            fresh["qvix_cache"] = "missing"

        # Event signals
        event_cache = DATA_DIR / "event_signals_live.json"
        if event_cache.exists():
            age = time.time() - event_cache.stat().st_mtime
            fresh["event_signals"] = f"{age/60:.0f}min前"
        else:
            fresh["event_signals"] = "missing"

        # ML models
        ml_dir = DATA_DIR / "ml_models"
        if ml_dir.exists() and list(ml_dir.iterdir()):
            fresh["ml_models"] = "exists"
        else:
            fresh["ml_models"] = "missing"

        return fresh
    results.append(_test("数据新鲜度", _check_freshness))

    total_elapsed = time.time() - t0

    # Summarize
    ok = sum(1 for r in results if r.status == "ok")
    degraded = sum(1 for r in results if r.status == "degraded")
    error = sum(1 for r in results if r.status == "error")

    return {
        "timestamp": datetime.now().isoformat(),
        "total_tests": len(results),
        "ok": ok,
        "degraded": degraded,
        "error": error,
        "health_pct": round(ok / max(len(results), 1) * 100, 1),
        "elapsed_seconds": round(total_elapsed, 1),
        "results": [
            {
                "name": r.name,
                "status": r.status,
                "detail": r.detail,
                "elapsed_ms": round(r.elapsed_ms, 0),
            }
            for r in results
        ],
    }


def format_report(result: dict) -> str:
    """Format integration test results."""
    status_icon = {"ok": "✅", "degraded": "🟡", "error": "❌"}

    lines = [
        "🧪 ETF系统集成测试",
        f"{'=' * 60}",
        "",
        f"  通过: {result['ok']}  |  降级: {result['degraded']}  |  异常: {result['error']}",
        f"  健康度: {result['health_pct']}%  |  耗时: {result['elapsed_seconds']}s",
        "",
        f"  {'─' * 55}",
    ]

    for r in result["results"]:
        icon = status_icon.get(r["status"], "?")
        elapsed = f"{r['elapsed_ms']:.0f}ms" if r["elapsed_ms"] < 1000 else f"{r['elapsed_ms']/1000:.1f}s"
        line = f"  {icon} {r['name']:<30s} [{elapsed:>6s}]"
        if r["detail"]:
            line += f"\n     └─ {r['detail'][:80]}"
        lines.append(line)

    lines.append("")
    lines.append(f"{'=' * 60}")

    # Recommendations
    recommendations = []
    for r in result["results"]:
        if r["status"] == "error":
            recommendations.append(f"  ⚠️ {r['name']}: 需修复 — {r['detail'][:60]}")
        elif r["status"] == "degraded":
            recommendations.append(f"  💡 {r['name']}: 可优化 — {r['detail'][:60]}")

    if recommendations:
        lines.append("\n  建议:")
        lines.extend(recommendations[:5])

    return "\n".join(lines)


if __name__ == "__main__":
    json_mode = "--json" in sys.argv
    print("🧪 运行集成测试...", file=sys.stderr)
    result = run_all()

    if json_mode:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_report(result))
