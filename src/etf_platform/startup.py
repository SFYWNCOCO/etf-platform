#!/usr/bin/env python3
"""
启动加速模块 — 懒加载 + 候选池预缓存

问题: 每次跑预测都要重新解析etfs.yaml、过滤候选池。
优化: 首次构建后缓存到pickle，后续秒级加载。

懒加载: sklearn/xgboost/transformers等重依赖只在真正使用时才import。

用法:
  from etf_platform.startup import get_cached_candidates, lazy_import
  candidates = get_cached_candidates()  # 首次~0.5s, 后续~0.01s
"""
import logging
logger = logging.getLogger(__name__)

import pickle
import time
from pathlib import Path
from typing import Optional

BASE = Path(__file__).resolve().parent.parent.parent  # etf-platform/
CACHE_DIR = BASE / "data" / "startup_cache"
CANDIDATE_CACHE = CACHE_DIR / "candidates.pkl"
CACHE_TTL = 3600  # 1 hour

# ── Lazy imports ────────────────────────────────────────────────────

_LAZY_MODULES: dict[str, Optional[object]] = {}


def lazy_import(module_name: str):
    """Import a module lazily — only on first access.

    Usage:
        sklearn = lazy_import("sklearn")
        model = sklearn.ensemble.RandomForestClassifier()
    """
    if module_name not in _LAZY_MODULES:
        try:
            import importlib
            _LAZY_MODULES[module_name] = importlib.import_module(module_name)
        except ImportError:
            _LAZY_MODULES[module_name] = None
    return _LAZY_MODULES[module_name]


# ── Candidate pool caching ─────────────────────────────────────────

def get_cached_candidates(
    max_candidates: int = 80,
    force_refresh: bool = False,
) -> list[tuple[str, dict]]:
    """Get filtered ETF candidates with caching.

    Filters: buyable only, no wide-base, no bonds/currency.
    Caches to pickle for sub-second reloads.
    """
    if not force_refresh and CANDIDATE_CACHE.exists():
        age = time.time() - CANDIDATE_CACHE.stat().st_mtime
        if age < CACHE_TTL:
            try:
                with open(CANDIDATE_CACHE, "rb") as f:
                    cached = pickle.load(f)
                return cached[:max_candidates]
            except (pickle.PickleError, OSError, EOFError):
                pass  # Corrupted cache → rebuild

    # Build fresh
    from etf_platform.config_loader import load_etfs

    etfs = load_etfs()
    EXCLUDE_SECTORS = {"货币基金", "利率债", "信用债", "债券", "国债", "货币"}
    EXCLUDE_KEYWORDS = [
        "沪深300", "中证500", "中证1000", "上证50", "科创50", "科创100", "创业板"
    ]

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
        candidates.append((code, info))

    # Cache
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(CANDIDATE_CACHE, "wb") as f:
            pickle.dump(candidates, f, protocol=pickle.HIGHEST_PROTOCOL)
    except OSError as e:
            logger.debug(f"[startup] cache write failed: {e}")

    return candidates[:max_candidates]


def invalidate_caches():
    """Clear all startup caches."""
    if CANDIDATE_CACHE.exists():
        CANDIDATE_CACHE.unlink()
    _LAZY_MODULES.clear()


# ── Import time profiler ────────────────────────────────────────────

def profile_imports(top_modules: list[str]) -> dict[str, float]:
    """Measure import time for each module.

    Returns {module_name: seconds}.
    """
    results: dict[str, float] = {}
    for mod in top_modules:
        t0 = time.time()
        try:
            lazy_import(mod)
            elapsed = time.time() - t0
            results[mod] = round(elapsed, 3)
        except ImportError:
            results[mod] = -1.0
    return results


# ── CLI ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if "--profile" in sys.argv:
        print("⏱️ 启动耗时分析:")
        heavy_mods = [
            "sklearn", "xgboost", "lightgbm", "numpy", "pandas",
            "scipy", "akshare", "yaml",
        ]
        for mod, t in sorted(profile_imports(heavy_mods).items(), key=lambda x: -x[1]):
            status = f"{t:.2f}s" if t >= 0 else "未安装"
            print(f"  {mod:<20s} {status}")

    elif "--bench" in sys.argv:
        print("⏱️ 候选池缓存基准:")
        # Cold start
        invalidate_caches()
        t0 = time.time()
        candidates = get_cached_candidates(force_refresh=True)
        t_cold = time.time() - t0
        print(f"  冷启动(构建): {t_cold:.2f}s → {len(candidates)}只ETF")

        # Warm start
        t0 = time.time()
        candidates = get_cached_candidates()
        t_warm = time.time() - t0
        print(f"  热启动(缓存): {t_warm:.3f}s → {len(candidates)}只ETF")
        print(f"  加速: {t_cold/t_warm:.0f}x" if t_warm > 0 else "  加速: ∞")

    else:
        # Default: show cache status
        if CANDIDATE_CACHE.exists():
            age = time.time() - CANDIDATE_CACHE.stat().st_mtime
            candidates = get_cached_candidates()
            print(f"✅ 候选池缓存: {len(candidates)}只ETF ({age/60:.0f}min前)")
        else:
            print("❌ 无缓存, 运行 --bench 构建")
