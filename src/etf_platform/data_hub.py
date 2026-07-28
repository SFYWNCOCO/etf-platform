#!/usr/bin/env python3
"""data_hub.py — Shared data layer for MetaPredictor.

All prediction sources (zscore / ml / tournament / events) share the same
kline + pipeline data via session-level cache with 5-minute TTL.

Design:
  - Singleton pattern (DataHub.get_instance())
  - get_kline_data(codes) → dict[code, TrendSnapshot]  (5min TTL)
  - get_pipeline_data(codes) → list[dict]               (5min TTL)
  - get_regime() → delegates to qvix_regime.get_regime() (file-cache, 4hr)
  - invalidate() → force-refresh all cached data
  - Thread-safe via threading.Lock

Usage::

    hub = DataHub.get_instance()
    trends = hub.get_kline_data(['510050', '159570'])
    pipes  = hub.get_pipeline_data(list(trends.keys()))
    regime = hub.get_regime()
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
BASE = Path(__file__).resolve().parent.parent.parent  # etf-platform/
SRC = BASE / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
KLINE_TTL_SECONDS: float = 300.0  # 5 minutes
PIPELINE_TTL_SECONDS: float = 300.0  # 5 minutes
CACHE_DIR = BASE / "data" / "live_cache"


# ---------------------------------------------------------------------------
# DataHub singleton
# ---------------------------------------------------------------------------

class DataHub:
    """Session-level shared data cache for all prediction sources."""

    _instance: DataHub | None = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._cache_lock = threading.Lock()
        # kline cache: {tuple(sorted_codes): {"data": dict, "ts": float}}
        self._kline_cache: dict[tuple[str, ...], dict[str, Any]] = {}
        # pipeline cache: {tuple(sorted_codes): {"data": list, "ts": float}}
        self._pipeline_cache: dict[tuple[str, ...], dict[str, Any]] = {}
        # regime cache: {"data": dict, "ts": float}
        self._regime_cache: dict[str, Any] = {}
        logger.info("[DataHub] initialized")

    @classmethod
    def get_instance(cls) -> DataHub:
        """Return the singleton DataHub instance (thread-safe)."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = DataHub()
        return cls._instance

    # ── Kline data ─────────────────────────────────────────────────────

    def get_kline_data(self, codes: list[str]) -> dict[str, Any]:
        """Fetch kline TrendSnapshots for a batch of ETF codes.

        Returns a dict[code, TrendSnapshot].  Results are cached for
        KLINE_TTL_SECONDS; subsequent calls with the same code set return
        the cached value without re-fetching.
        """
        sorted_codes = tuple(sorted(set(codes)))
        now = time.time()

        with self._cache_lock:
            entry = self._kline_cache.get(sorted_codes)
            if entry is not None and (now - entry["ts"]) < KLINE_TTL_SECONDS:
                logger.debug("[DataHub] kline cache hit: %d codes", len(sorted_codes))
                return entry["data"]

        # Cache miss or expired — fetch fresh data
        logger.info("[DataHub] kline cache miss: %d codes, fetching...", len(sorted_codes))
        t0 = time.time()
        try:
            from etf_platform.data.kline import get_trend_batch

            result = get_trend_batch(list(sorted_codes))
        except (ImportError, KeyError, ValueError, TypeError, AttributeError, OSError) as e:
            logger.error("[DataHub] kline fetch failed: %s", e)
            result = {}

        elapsed = time.time() - t0
        logger.info("[DataHub] kline fetch done: %d codes in %.2fs", len(result), elapsed)

        with self._cache_lock:
            self._kline_cache[sorted_codes] = {"data": result, "ts": time.time()}

        return result

    # ── Pipeline data ──────────────────────────────────────────────────

    def get_pipeline_data(self, codes: list[str]) -> list[dict]:
        """Run penetration pipeline for a batch of ETF codes.

        Returns a list of pipeline result dicts.  Results are cached for
        PIPELINE_TTL_SECONDS.
        """
        sorted_codes = tuple(sorted(set(codes)))
        now = time.time()

        with self._cache_lock:
            entry = self._pipeline_cache.get(sorted_codes)
            if entry is not None and (now - entry["ts"]) < PIPELINE_TTL_SECONDS:
                logger.debug("[DataHub] pipeline cache hit: %d codes", len(sorted_codes))
                return entry["data"]

        # Cache miss or expired — run fresh pipeline
        logger.info("[DataHub] pipeline cache miss: %d codes, running...", len(sorted_codes))
        t0 = time.time()
        try:
            from etf_platform.pipeline import batch_full

            result = batch_full(
                limit=len(sorted_codes), live=False,
                codes=list(sorted_codes), skip_tournament=True,
            )
        except (ImportError, KeyError, ValueError, TypeError, AttributeError, OSError) as e:
            logger.error("[DataHub] pipeline run failed: %s", e)
            result = []

        elapsed = time.time() - t0
        logger.info("[DataHub] pipeline done: %d results in %.2fs", len(result), elapsed)

        with self._cache_lock:
            self._pipeline_cache[sorted_codes] = {"data": result, "ts": time.time()}

        return result

    # ── Regime ─────────────────────────────────────────────────────────

    def get_regime(self) -> dict[str, Any]:
        """Get current QVIX market regime.

        Delegates to qvix_regime.get_regime() which has its own file-based
        cache (4hr TTL).  We add an in-process cache layer for repeated calls
        within the same session.
        """
        now = time.time()
        with self._cache_lock:
            if self._regime_cache:
                entry = self._regime_cache
                if (now - entry["ts"]) < KLINE_TTL_SECONDS:
                    return entry["data"]

        logger.info("[DataHub] regime cache miss, fetching...")
        t0 = time.time()
        try:
            from etf_platform.analysis.qvix_regime import get_regime as _get_regime

            result = _get_regime()
        except (ImportError, KeyError, ValueError, TypeError, AttributeError, OSError) as e:
            logger.error("[DataHub] regime fetch failed: %s", e)
            result = {
                "regime": "normal",
                "description": "QVIX unavailable, using normal regime",
                "trade_signal": "use standard scoring",
                "qvix_50": 20,
                "qvix_500": 22,
            }

        elapsed = time.time() - t0
        logger.info("[DataHub] regime fetched in %.2fs", elapsed)

        with self._cache_lock:
            self._regime_cache = {"data": result, "ts": time.time()}

        return result

    # ── Invalidation ───────────────────────────────────────────────────

    def invalidate(self) -> None:
        """Force-refresh all cached data. Call before re-running analysis."""
        with self._cache_lock:
            self._kline_cache.clear()
            self._pipeline_cache.clear()
            self._regime_cache.clear()
        logger.info("[DataHub] all caches invalidated")

    def invalidate_kline(self) -> None:
        """Invalidate only kline cache."""
        with self._cache_lock:
            self._kline_cache.clear()
        logger.info("[DataHub] kline cache invalidated")

    def invalidate_pipeline(self) -> None:
        """Invalidate only pipeline cache."""
        with self._cache_lock:
            self._pipeline_cache.clear()
        logger.info("[DataHub] pipeline cache invalidated")

    # ── Status ─────────────────────────────────────────────────────────

    def cache_status(self) -> dict[str, Any]:
        """Return cache statistics for debugging."""
        with self._cache_lock:
            now = time.time()
            kline_entries = len(self._kline_cache)
            pipeline_entries = len(self._pipeline_cache)
            regime_age = (
                round(now - self._regime_cache["ts"], 1)
                if self._regime_cache
                else None
            )
            return {
                "kline_cached_sets": kline_entries,
                "pipeline_cached_sets": pipeline_entries,
                "regime_age_seconds": regime_age,
                "regime_cached": bool(self._regime_cache),
            }


# ---------------------------------------------------------------------------
# Convenience function — one-liner for callers
# ---------------------------------------------------------------------------

def get_hub() -> DataHub:
    """Shortcut to get the singleton DataHub."""
    return DataHub.get_instance()


# ---------------------------------------------------------------------------
# Benchmark
# ---------------------------------------------------------------------------

def _benchmark() -> None:
    """Compare cold vs warm cache timings for DataHub."""
    import json as _json
    from etf_platform.config_loader import load_etfs

    print("=" * 60)
    print("📊 DataHub Benchmark — Cold vs Warm Cache")
    print("=" * 60)

    hub = DataHub.get_instance()
    hub.invalidate()  # Ensure clean state

    # Select a representative subset of codes
    etfs = load_etfs()
    sample_codes = [c for c in etfs if c.isdigit()][:10]
    print(f"\nTest codes ({len(sample_codes)}): {sample_codes}")

    # --- Test 1: Kline cold start ---
    print("\n--- Kline Fetch (cold) ---")
    t0 = time.time()
    trends1 = hub.get_kline_data(sample_codes)
    cold_kline = time.time() - t0
    print(f"  First call:  {cold_kline:.2f}s  ({len(trends1)} codes fetched)")

    # --- Test 2: Kline warm ---
    print("\n--- Kline Fetch (warm) ---")
    t0 = time.time()
    trends2 = hub.get_kline_data(sample_codes)
    warm_kline = time.time() - t0
    print(f"  Second call: {warm_kline:.4f}s  ({len(trends2)} codes from cache)")

    # --- Test 3: Pipeline cold start ---
    print("\n--- Pipeline Run (cold) ---")
    hub.invalidate_pipeline()
    t0 = time.time()
    pipes1 = hub.get_pipeline_data(sample_codes)
    cold_pipe = time.time() - t0
    print(f"  First call:  {cold_pipe:.2f}s  ({len(pipes1)} results)")

    # --- Test 4: Pipeline warm ---
    print("\n--- Pipeline Run (warm) ---")
    t0 = time.time()
    pipes2 = hub.get_pipeline_data(sample_codes)
    warm_pipe = time.time() - t0
    print(f"  Second call: {warm_pipe:.4f}s  ({len(pipes2)} results from cache)")

    # --- Test 5: Regime ---
    print("\n--- Regime Fetch ---")
    t0 = time.time()
    regime1 = hub.get_regime()
    regime_time = time.time() - t0
    print(f"  First call:  {regime_time:.2f}s  (regime={regime1.get('regime', '?')})")

    t0 = time.time()
    _regime2 = hub.get_regime()
    regime_warm = time.time() - t0
    print(f"  Second call: {regime_warm:.4f}s  (from cache)")

    # --- Summary ---
    print("\n" + "=" * 60)
    print("Summary:")
    print(f"  Kline cold:  {cold_kline:.2f}s  → warm: {warm_kline:.4f}s  "
          f"(speedup: {cold_kline/max(warm_kline, 0.001):.0f}x)")
    print(f"  Pipeline cold: {cold_pipe:.2f}s  → warm: {warm_pipe:.4f}s  "
          f"(speedup: {cold_pipe/max(warm_pipe, 0.001):.0f}x)")
    print(f"  Regime cold: {regime_time:.2f}s  → warm: {regime_warm:.4f}s  "
          f"(speedup: {regime_time/max(regime_warm, 0.001):.0f}x)")

    # Simulate savings for 4 independent sources
    n_sources = 4
    redundant_kline = cold_kline * (n_sources - 1)
    redundant_pipe = cold_pipe * (n_sources - 1)
    total_savings = redundant_kline + redundant_pipe
    print(f"\n  With {n_sources} sources:")
    print(f"    Redundant kline fetches saved: {redundant_kline:.1f}s")
    print(f"    Redundant pipeline runs saved: {redundant_pipe:.1f}s")
    print(f"    Total estimated savings: {total_savings:.1f}s")
    print("=" * 60)

    # Print cache status
    status = hub.cache_status()
    print(f"\nCache status: {_json.dumps(status, indent=2, ensure_ascii=False)}")


# MN-04: _benchmark function should ideally be in etf-platform/tests/
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="DataHub benchmark")
    parser.add_argument("--bench", action="store_true", help="Run benchmark")
    args = parser.parse_args()

    if args.bench or "--bench" in sys.argv[1:]:
        _benchmark()
    else:
        print("DataHub v1.0 — Shared data layer for MetaPredictor")
        print("Usage: python -m etf_platform.data_hub --bench")
        print("")
        print("Quick example:")
        print("  hub = DataHub.get_instance()")
        print("  trends = hub.get_kline_data(['510050', '159570'])")
        print("  pipes  = hub.get_pipeline_data(list(trends.keys()))")
        print("  regime = hub.get_regime()")
