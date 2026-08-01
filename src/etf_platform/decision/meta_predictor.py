#!/usr/bin/env python3
"""
meta_predictor.py — 多源预测集成器 v2.0 (并行化)

设计原则:
  - 每个预测源可以独立存活/死亡，不影响其他源
  - 4个预测源用ThreadPoolExecutor并发执行 (目标: 35s → 12s)
  - 按校准置信度动态加权（贝叶斯→置信度越高权重越大）
  - 同行业冲突时保留更高置信度的预测
  - 输出统一格式，标注来源组合

预测源:
  A. Z-score 8因子 (two_week_picker) — 基础源，始终可用
  B. ML集成 (ml_predictor) — XGBoost+LightGBM+CatBoost，需训练数据
  C. 策略锦标赛 (strategy_tournament) — 多策略按regime加权
  D. NLP事件信号 (event_nlp) — 实时催化剂检测

用法:
  python -m etf_platform.decision.meta_predictor
  python -m etf_platform.decision.meta_predictor --json
  python -m etf_platform.decision.meta_predictor --bench   # 对比顺序vs并行耗时
"""
import logging
logger = logging.getLogger(__name__)

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from datetime import date
from pathlib import Path
from typing import Optional

BASE = Path(__file__).resolve().parent.parent.parent.parent  # etf-platform/
DATA_DIR = BASE / "data"
META_LOG = DATA_DIR / "meta_predictions.jsonl"

# ── Per-source timeouts (seconds) ──────────────────────────────────────
SOURCE_TIMEOUTS: dict[str, float] = {
    "zscore": 30,
    "ml": 15,
    "tournament": 25,
    "events": 10,
}


# ── Predictor registry ────────────────────────────────────────────────

class PredictorSource:
    """Descriptor for a prediction source."""

    def __init__(self, name: str, weight: float = 0.25):
        self.name = name
        self.weight = weight
        self.available = False
        self.error: Optional[str] = None
        self.degraded = False  # True if timed out or errored partially
        self._fn = None

    def probe(self) -> bool:
        """Check if predictor module is importable."""
        try:
            import importlib
            mod = importlib.import_module(f"etf_platform.decision.{self.name}")
            self._fn = getattr(mod, f"{self.name}_predict", None)
            if not self._fn:
                # Try alternate callable names
                alt_names = [
                    f"_{self.name}_predict",
                    f"{self.name}_predict",
                    "predict_top3" if self.name == "ml" else None,
                    "get_ensemble_picks" if self.name == "tournament" else None,
                ]
                for alt in alt_names:
                    if alt:
                        self._fn = getattr(mod, alt, None)
                        if self._fn:
                            break
            self.available = self._fn is not None
            if not self.available:
                self.error = f"function not found in etf_platform.decision.{self.name}"
        except ImportError as e:
            self.available = False
            self.error = str(e)
        return self.available

    def call(self) -> list[dict]:
        """Call the predictor, returning list of prediction dicts."""
        if not self.available or not self._fn:
            return []
        try:
            result = self._fn()
            if isinstance(result, tuple):
                result = result[0]
            if not isinstance(result, list):
                return []
            return result
        except (TypeError, ValueError, AttributeError, OSError, KeyError) as e:
            self.error = str(e)
            return []


# ── Source-specific callable wrappers ──────────────────────────────────

def _zscore_predict() -> list[dict]:
    """Z-score prediction source."""
    from etf_platform.decision.two_week_picker import pick_top3
    top3, _ = pick_top3(profile="均衡", max_candidates=80, debug=False)
    return top3


def _ml_predict() -> list[dict]:
    """ML ensemble prediction source."""
    from etf_platform.decision.ml_predictor import predict_top3
    return predict_top3()


def _tournament_predict() -> list[dict]:
    """Strategy tournament prediction source."""
    from etf_platform.decision.strategy_tournament import get_ensemble_picks
    return get_ensemble_picks()


def _event_predict() -> list[dict]:
    """NLP event signal source — converts events to ETF signals."""
    from etf_platform.analysis.event_nlp import get_sector_signals
    # FIX 2026-08-01: get_sector_signals already returns MetaPredictor-format
    # predictions ({code,name,sector,score,source}) via _signals_to_predictions.
    # Old code read sig["etf_codes"] from the converted output → always empty,
    # so the events source never contributed predictions.
    return get_sector_signals()


# ── Predictor registry ────────────────────────────────────────────────

SOURCES = [
    PredictorSource("zscore", weight=0.35),
    PredictorSource("ml", weight=0.25),
    PredictorSource("tournament", weight=0.25),
    PredictorSource("events", weight=0.15),
]

# Map source name → callable wrapper
_SOURCE_CALLABLES: dict[str, callable] = {
    "zscore": _zscore_predict,
    "ml": _ml_predict,
    "tournament": _tournament_predict,
    "events": _event_predict,
}


# ── Score normalization ───────────────────────────────────────────────

def _normalize_scores(predictions: list[dict]) -> list[dict]:
    """Ensure all predictions have scores in 0-100 range."""
    for p in predictions:
        score = p.get("score", p.get("two_week_score", 50))
        p["norm_score"] = max(0.0, min(100.0, float(score)))
    return predictions


# ── Disagreement channel (ML override for filtered ETFs) ─────────────

def _build_disagreement_channel(
    ml_predictions: list[dict],
    zscore_candidates: set[str],
    qvix_regime: str = "normal",
) -> list[dict]:
    """构建异议通道 — 被Z-score过滤但ML高分的ETF。

    当QVIX处于fearful/cautious时，某些行业被规则系统排除。
    如果ML对这类ETF给出高置信度预测，通过此通道进入融合池。

    Args:
        ml_predictions: ML源的全部预测
        zscore_candidates: Z-score候选池中的ETF代码集合
        qvix_regime: 当前QVIX市场状态

    Returns:
        进入异议通道的ETF列表（带额外元数据）
    """
    if qvix_regime not in ("fearful", "cautious"):
        return []

    # QVIX过滤的行业白名单（与two_week_picker.py一致）
    defensive_sectors = {
        "红利价值", "红利/价值", "高股息", "公用事业",
        "贵金属", "黄金", "利率债", "消费", "食品饮料",
        "医药", "白酒消费",
    }
    high_risk_sectors = {"半导体", "半导体设备", "AI算力", "券商", "军工"}

    channel_entries = []
    for ml_pred in ml_predictions:
        code = ml_pred.get("code", "")
        sector = ml_pred.get("sector", "")
        prob_up = ml_pred.get("prob_up", 0.5)
        confidence = ml_pred.get("confidence", 0.5)
        expected_ret = ml_pred.get("expected_return_10d", 0.0)

        if not code or code in zscore_candidates:
            continue

        # 判断是否因QVIX被过滤
        is_filtered = False
        filter_reason = ""
        if qvix_regime == "fearful" and sector not in defensive_sectors:
            is_filtered = True
            filter_reason = f"fearful期过滤{sector}"
        elif qvix_regime == "cautious" and sector in high_risk_sectors:
            is_filtered = True
            filter_reason = f"cautious期过滤{sector}"

        if is_filtered and prob_up > 0.6:
            # 检查覆盖条件
            meets_override = (
                prob_up >= 0.75
                and confidence >= 0.6
                and expected_ret > 3.0
            )
            channel_entries.append({
                "code": code,
                "name": ml_pred.get("name", ""),
                "sector": sector,
                "norm_score": round(prob_up * 100, 1),  # 转换为0-100分数
                "source": "ml_disagreement",
                "ml_prob_up": prob_up,
                "ml_expected_return": expected_ret,
                "ml_confidence": confidence,
                "filter_reason": filter_reason,
                "meets_override": meets_override,
            })

    return channel_entries


# ── Confidence weighting ──────────────────────────────────────────────

def _get_source_confidence(source_name: str) -> float:
    """Get calibrated confidence for a prediction source."""
    try:
        from etf_platform.decision.confidence_calibrator import predict_probability
        source_priors = {
            "zscore": 65,
            "ml": 60,
            "tournament": 60,
            "events": 55,
        }
        score = source_priors.get(source_name, 60)
        result = predict_probability(score)
        return result.get("calibrated_probability", 0.5)
    except (ImportError, KeyError, ValueError, TypeError, AttributeError, OSError):
        return 0.5


# ── Fusion engine ─────────────────────────────────────────────────────

def _fuse_predictions(
    all_predictions: dict[str, list[dict]],
    source_confidences: dict[str, float],
    disagreement_channel: list[dict] | None = None,
) -> list[dict]:
    """Fuse predictions from multiple sources into unified Top-N.

    Args:
        all_predictions: Dict of source_name → prediction list
        source_confidences: Dict of source_name → calibrated confidence
        disagreement_channel: Optional list of ML-overridden ETFs that were
            filtered by Z-score rules (QVIX regime filter). These are added
            to the fusion pool at reduced weight (override_weight=0.4×ML base).

    Returns:
        Ranked Top-3 list with cross-source metadata.
    """
    etf_scores: dict[str, dict] = {}
    total_weight = sum(source_confidences.values()) or 1.0

    # ── Step 1: Fuse standard source predictions ──
    for source_name, preds in all_predictions.items():
        weight = source_confidences.get(source_name, 0.25) / total_weight
        for p in preds:
            code = p.get("code", "")
            if not code:
                continue
            score = p.get("norm_score", p.get("two_week_score", 50))
            sector = p.get("sector", "未知")

            if code not in etf_scores:
                etf_scores[code] = {
                    "code": code,
                    "name": p.get("name", ""),
                    "sector": sector,
                    "weighted_score": 0.0,
                    "total_weight": 0.0,
                    "sources": [],
                    "raw_scores": {},
                    "is_override": False,
                    "override_reason": "",
                }

            etf_scores[code]["weighted_score"] += score * weight
            etf_scores[code]["total_weight"] += weight
            etf_scores[code]["sources"].append(source_name)
            etf_scores[code]["raw_scores"][source_name] = round(score, 1)

    # ── Step 2: Incorporate disagreement channel ──
    if disagreement_channel:
        # Override weight: ML override gets 40% of full ML weight
        override_weight = 0.4
        ml_confidence = source_confidences.get("ml", 0.6)
        effective_override_weight = ml_confidence * override_weight / total_weight

        for entry in disagreement_channel:
            code = entry.get("code", "")
            if not code:
                continue
            score = entry.get("norm_score", 50.0)
            sector = entry.get("sector", "未知")
            meets_override = entry.get("meets_override", False)

            if code not in etf_scores:
                etf_scores[code] = {
                    "code": code,
                    "name": entry.get("name", ""),
                    "sector": sector,
                    "weighted_score": 0.0,
                    "total_weight": 0.0,
                    "sources": ["ml_disagreement"],
                    "raw_scores": {"ml_disagreement": round(score, 1)},
                    "is_override": True,
                    "override_reason": entry.get("filter_reason", ""),
                    "ml_prob_up": entry.get("ml_prob_up", 0),
                    "meets_override": meets_override,
                }
                # Apply override weight
                etf_scores[code]["weighted_score"] = score * effective_override_weight
                etf_scores[code]["total_weight"] = effective_override_weight
            else:
                # Code already exists — add disagreement signal
                etf_scores[code]["sources"].append("ml_disagreement")
                etf_scores[code]["raw_scores"]["ml_disagreement"] = round(score, 1)
                etf_scores[code]["weighted_score"] += score * effective_override_weight
                etf_scores[code]["total_weight"] += effective_override_weight
                etf_scores[code]["is_override"] = True
                etf_scores[code]["meets_override"] = meets_override

    # ── Step 3: Normalize and rank ──
    for etf in etf_scores.values():
        if etf["total_weight"] > 0:
            etf["weighted_score"] /= etf["total_weight"]
        etf["weighted_score"] = round(etf["weighted_score"], 1)

    ranked = sorted(etf_scores.values(), key=lambda x: -x["weighted_score"])

    # ── Step 4: Select Top-3 with sector diversification ──
    # Process non-override entries first; only fill remaining slots with overrides.
    # This prevents low-confidence watch entries from displacing normal picks.
    top3: list[dict] = []
    seen_sectors: set[str] = set()
    override_in_top3 = False

    # First pass: normal entries
    for etf in ranked:
        if etf.get("is_override"):
            continue
        sector = etf["sector"]
        if sector not in seen_sectors:
            top3.append(etf)
            seen_sectors.add(sector)
        if len(top3) >= 3:
            break

    # Second pass: fill remaining slots with override entries
    if len(top3) < 3:
        remaining = 3 - len(top3)
        for etf in ranked:
            if not etf.get("is_override"):
                continue
            if len(top3) >= 3:
                break
            sector = etf["sector"]
            if sector not in seen_sectors:
                top3.append(etf)
                seen_sectors.add(sector)
                override_in_top3 = True

    return top3


# ── Sequential execution (baseline) ───────────────────────────────────

def _predict_sequential(unified: bool = True) -> dict:
    """Run all predictors sequentially (baseline for benchmarking)."""
    t0 = time.time()

    source_status: dict[str, dict] = {}
    for src in SOURCES:
        src.probe()
        source_status[src.name] = {
            "available": src.available,
            "error": src.error,
        }

    all_predictions: dict[str, list[dict]] = {}
    for src in SOURCES:
        if src.available:
            preds = src.call()
            all_predictions[src.name] = _normalize_scores(preds)

    source_confidences: dict[str, float] = {}
    for src in SOURCES:
        if src.available:
            source_confidences[src.name] = _get_source_confidence(src.name)

    # ── Build disagreement channel ──
    qvix_regime = "normal"
    try:
        from etf_platform.analysis.qvix_regime import get_regime as get_qvix
        rd = get_qvix()
        qvix_regime = rd.get("regime", "normal")
    except (ImportError, Exception) as e:
            logger.debug(f"[meta_predictor] QVIX failed: {e}")

    zscore_codes = {p.get("code") for p in all_predictions.get("zscore", [])}
    ml_preds_raw = all_predictions.get("ml", [])
    disagreement = _build_disagreement_channel(ml_preds_raw, zscore_codes, qvix_regime)

    fused = _fuse_predictions(
        all_predictions, source_confidences,
        disagreement_channel=disagreement if unified else None,
    ) if unified else []

    elapsed = time.time() - t0

    return {
        "date": date.today().isoformat(),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "version": "2.1-seq",
        "sources_available": sum(1 for s in source_status.values() if s["available"]),
        "sources_total": len(SOURCES),
        "source_status": source_status,
        "source_confidences": source_confidences,
        "qvix_regime": qvix_regime,
        "predictions_per_source": {
            name: len(preds) for name, preds in all_predictions.items()
        },
        "disagreement_channel": [
            {
                "code": d["code"],
                "name": d["name"],
                "sector": d["sector"],
                "ml_prob_up": d.get("ml_prob_up", 0),
                "filter_reason": d.get("filter_reason", ""),
                "meets_override": d.get("meets_override", False),
            }
            for d in disagreement
        ],
        "fused_top3": fused,
        "elapsed_seconds": round(elapsed, 2),
        "mode": "sequential",
    }


# ── Parallel execution (optimized) ────────────────────────────────────

def _predict_parallel(unified: bool = True) -> dict:
    """Run all available predictors in parallel using ThreadPoolExecutor.

    Each source runs concurrently with its own timeout.
    Timed-out sources are marked as degraded but don't block others.
    """
    t0 = time.time()

    # Probe all sources first (lightweight, sequential)
    source_status: dict[str, dict] = {}
    for src in SOURCES:
        src.probe()
        source_status[src.name] = {
            "available": src.available,
            "error": src.error,
        }

    # Determine which sources to run in parallel
    runnable_sources = [src for src in SOURCES if src.available]
    if not runnable_sources:
        elapsed = time.time() - t0
        return {
            "date": date.today().isoformat(),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "version": "2.0-par",
            "sources_available": 0,
            "sources_total": len(SOURCES),
            "source_status": source_status,
            "source_confidences": {},
            "predictions_per_source": {},
            "fused_top3": [],
            "elapsed_seconds": round(elapsed, 2),
            "mode": "parallel",
        }

    # Execute all sources in parallel with per-source timeouts
    all_predictions: dict[str, list[dict]] = {}
    degraded_sources: set[str] = set()
    # Map future → source_name for result collection
    future_to_source: dict = {}

    with ThreadPoolExecutor(max_workers=len(runnable_sources)) as executor:
        for src in runnable_sources:
            timeout = SOURCE_TIMEOUTS.get(src.name, 30)
            future = executor.submit(_call_with_timeout, src.name, timeout)
            future_to_source[future] = src.name

        # Collect results as they complete
        for future in as_completed(future_to_source):
            source_name = future_to_source[future]
            try:
                preds, degraded, error = future.result(timeout=0)
                if degraded:
                    degraded_sources.add(source_name)
                    source_status[source_name]["degraded"] = True
                    source_status[source_name]["error"] = error or f"timed out after {SOURCE_TIMEOUTS[source_name]}s"
                if preds:
                    all_predictions[source_name] = _normalize_scores(preds)
            except (TimeoutError, RuntimeError, ImportError, KeyError,
                    ValueError, TypeError, AttributeError, OSError) as e:
                degraded_sources.add(source_name)
                source_status[source_name]["degraded"] = True
                source_status[source_name]["error"] = str(e)

    # Get source confidences (only for non-degraded sources)
    source_confidences: dict[str, float] = {}
    for src in SOURCES:
        if src.available and src.name not in degraded_sources:
            source_confidences[src.name] = _get_source_confidence(src.name)
        elif src.available:
            # Degraded source gets default confidence
            source_confidences[src.name] = 0.3

    # ── Build disagreement channel ──
    qvix_regime = "normal"
    try:
        from etf_platform.analysis.qvix_regime import get_regime as get_qvix
        rd = get_qvix()
        qvix_regime = rd.get("regime", "normal")
    except (ImportError, Exception) as e:
            logger.debug(f"[meta_predictor] qvix failed: {e}")

    zscore_codes = {p.get("code") for p in all_predictions.get("zscore", [])}
    ml_preds_raw = all_predictions.get("ml", [])
    disagreement = _build_disagreement_channel(ml_preds_raw, zscore_codes, qvix_regime)

    # Fuse
    fused = _fuse_predictions(
        all_predictions, source_confidences,
        disagreement_channel=disagreement if unified else None,
    ) if unified else []

    elapsed = time.time() - t0

    result = {
        "date": date.today().isoformat(),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "version": "2.1",
        "sources_available": sum(1 for s in source_status.values() if s["available"]),
        "sources_total": len(SOURCES),
        "source_status": source_status,
        "degraded_sources": sorted(degraded_sources),
        "source_confidences": source_confidences,
        "qvix_regime": qvix_regime,
        "predictions_per_source": {
            name: len(preds) for name, preds in all_predictions.items()
        },
        "disagreement_channel": [
            {
                "code": d["code"],
                "name": d["name"],
                "sector": d["sector"],
                "ml_prob_up": d.get("ml_prob_up", 0),
                "filter_reason": d.get("filter_reason", ""),
                "meets_override": d.get("meets_override", False),
            }
            for d in disagreement
        ],
        "fused_top3": fused,
        "elapsed_seconds": round(elapsed, 2),
        "mode": "parallel",
    }

    return result


def _call_with_timeout(source_name: str, timeout: float):
    """Execute a single source's predictor with a timeout.

    Returns: (predictions_list, was_degraded, error_message)
    """
    fn = _SOURCE_CALLABLES.get(source_name)
    if not fn:
        return [], True, f"no callable for {source_name}"

    try:
        start = time.time()
        result = fn()

        # Handle tuple return (e.g., pick_top3 returns (top3, all_scored))
        if isinstance(result, tuple):
            result = result[0]
        if not isinstance(result, list):
            return [], True, f"unexpected return type for {source_name}"

        elapsed = time.time() - start
        if elapsed > timeout:
            return result, True, f"took {elapsed:.1f}s > timeout {timeout}s"

        return result, False, ""
    except TimeoutError:
        return [], True, f"timed out after {timeout}s"
    except (TypeError, ValueError, AttributeError, OSError, KeyError, RuntimeError) as e:
        return [], True, str(e)


# ── Main entry ────────────────────────────────────────────────────────

def predict(unified: bool = True, parallel: bool = True) -> dict:
    """Run all available predictors and fuse results.

    Args:
        unified: If True, return fused Top3. If False, return raw per-source results.
        parallel: If True, use ThreadPoolExecutor for concurrent execution.

    Returns:
        dict with meta prediction results
    """
    if parallel:
        return _predict_parallel(unified)
    else:
        return _predict_sequential(unified)


def log_meta_prediction(result: dict) -> Path:
    """Log meta prediction to JSONL for future calibration."""
    META_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(META_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(result, ensure_ascii=False) + "\n")
    return META_LOG


# ── Report ────────────────────────────────────────────────────────────

def format_report(result: dict) -> str:
    """Format meta prediction as readable report."""
    lines = [
        "🧠 MetaPredictor — 多源融合预测",
        f"{'=' * 60}",
        "",
        f"  日期: {result['date']}",
        f"  可用源: {result['sources_available']}/{result['sources_total']}",
        f"  模式: {'并行 ⚡' if result.get('mode') == 'parallel' else '顺序'}",
        f"  耗时: {result['elapsed_seconds']}s",
        "",
    ]

    # Degraded sources warning
    degraded = result.get("degraded_sources", [])
    if degraded:
        lines.append(f"  ⚠️ 降级源: {', '.join(degraded)}")
        lines.append("")

    # Source status
    for name, status in result.get("source_status", {}).items():
        icon = "✅" if status["available"] else "❌"
        if status.get("degraded"):
            icon = "⏱️"
        conf = result.get("source_confidences", {}).get(name, 0.0)
        pred_count = result.get("predictions_per_source", {}).get(name, 0)
        lines.append(f"  {icon} {name:12s}  置信度={conf:.0%}  产出={pred_count}条")
        if status.get("error"):
            lines.append(f"                    ⚠️ {status['error'][:60]}")

    lines.append("")
    lines.append("  ── 融合 Top 3 ──")

    if not result.get("fused_top3"):
        lines.append("    ⚠️ 无有效预测（所有源均未产出）")
    else:
        for i, etf in enumerate(result["fused_top3"], 1):
            sources_str = "+".join(etf.get("sources", []))
            scores_str = " | ".join(
                f"{s}={v:.0f}" for s, v in etf.get("raw_scores", {}).items()
            )
            override_tag = ""
            if etf.get("is_override"):
                tag = "🔓" if etf.get("meets_override") else "👁️"
                override_tag = f" [{tag}异议通道]"
            lines.append(
                f"    {i}. {etf['code']:>6s} {etf['name']:<12s} "
                f"[{etf['sector']}] "
                f"融合分={etf['weighted_score']:.0f}{override_tag}  "
                f"来源: {sources_str}  ({scores_str})"
            )

    # Disagreement channel summary
    dc = result.get("disagreement_channel", [])
    if dc:
        lines.append("")
        lines.append("  ── 异议通道 (ML高分但规则过滤的ETF) ──")
        for d in dc:
            flag = "✅覆盖" if d.get("meets_override") else "👁️观察"
            lines.append(
                f"    • {d['code']} {d.get('name','')} [{d['sector']}] "
                f"P(涨)={d.get('ml_prob_up',0):.0%} → {flag} | "
                f"原因: {d.get('filter_reason','')}"
            )

    lines.append("")
    lines.append(f"{'=' * 60}")
    lines.append("MetaPredictor v2.0 · 并行多源融合 · 不构成投资建议")

    return "\n".join(lines)


# ── Benchmark mode ────────────────────────────────────────────────────

def run_benchmark(iterations: int = 3) -> dict:
    """Benchmark: compare sequential vs parallel execution across N iterations.

    Returns dict with timing stats for both modes.
    """
    print("=" * 70)
    print("🔬 MetaPredictor 性能基准测试")
    print(f"   对比: 顺序执行 vs 并行执行 ({iterations}轮)")
    print("=" * 70)

    seq_times: list[float] = []
    par_times: list[float] = []

    for i in range(1, iterations + 1):
        print(f"\n--- 第 {i}/{iterations} 轮 ---")

        # Sequential
        t_start = time.time()
        seq_result = _predict_sequential(unified=True)
        seq_elapsed = time.time() - t_start
        seq_times.append(seq_elapsed)
        print(f"  顺序: {seq_elapsed:.2f}s  |  产出: {sum(seq_result.get('predictions_per_source', {}).values())}条预测")

        # Parallel
        t_start = time.time()
        par_result = _predict_parallel(unified=True)
        par_elapsed = time.time() - t_start
        par_times.append(par_elapsed)
        print(f"  并行: {par_elapsed:.2f}s  |  产出: {sum(par_result.get('predictions_per_source', {}).values())}条预测")

        if seq_elapsed > 0:
            speedup = seq_elapsed / par_elapsed
            reduction = (1 - par_elapsed / seq_elapsed) * 100
            print(f"  ⚡ 加速比: {speedup:.1f}x  |  时间减少: {reduction:.0f}%")

    # Summary statistics
    avg_seq = sum(seq_times) / len(seq_times) if seq_times else 0
    avg_par = sum(par_times) / len(par_times) if par_times else 0
    best_par = min(par_times) if par_times else 0
    worst_seq = max(seq_times) if seq_times else 0

    summary = {
        "iterations": iterations,
        "sequential_times": [round(t, 2) for t in seq_times],
        "parallel_times": [round(t, 2) for t in par_times],
        "avg_sequential": round(avg_seq, 2),
        "avg_parallel": round(avg_par, 2),
        "best_parallel": round(best_par, 2),
        "worst_sequential": round(worst_seq, 2),
        "avg_speedup": round(avg_seq / avg_par, 2) if avg_par > 0 else 0,
        "time_reduction_pct": round((1 - avg_par / avg_seq) * 100, 1) if avg_seq > 0 else 0,
    }

    print("\n" + "=" * 70)
    print("📊 基准测试结果汇总")
    print("=" * 70)
    print(f"  顺序执行平均耗时: {avg_seq:.2f}s")
    print(f"  并行执行平均耗时: {avg_par:.2f}s")
    print(f"  最佳并行耗时:     {best_par:.2f}s")
    print(f"  最差顺序耗时:     {worst_seq:.2f}s")
    print(f"  平均加速比:       {summary['avg_speedup']:.1f}x")
    print(f"  时间减少:         {summary['time_reduction_pct']:.0f}%")
    print("=" * 70)

    return summary


# ── CLI ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    json_mode = "--json" in sys.argv
    bench_mode = "--bench" in sys.argv

    if bench_mode:
        # Run benchmark
        bench_result = run_benchmark(iterations=3)
        if json_mode:
            print(json.dumps(bench_result, ensure_ascii=False, indent=2))
        sys.exit(0)

    result = predict(unified=True, parallel=True)
    log_meta_prediction(result)

    if json_mode:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_report(result))
