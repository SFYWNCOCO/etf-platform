from __future__ import annotations
from ..utils import zscore
import logging
logger = logging.getLogger(__name__)

"""strategy_tournament.py — Multi-strategy prediction tournament v1.0"""

import json
import statistics
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE = Path(__file__).resolve().parent.parent.parent.parent  # etf-platform root
DATA_DIR = BASE / "data" / "live_cache"
TOURNAMENT_LOG = DATA_DIR / "tournament_predictions.jsonl"
RESULT_JSON = DATA_DIR / "tournament_60day_result.json"

# ---------------------------------------------------------------------------
# Result cache (shared by get_ensemble_for_pipeline & get_ensemble_picks)
# ---------------------------------------------------------------------------
_last_result: dict[str, Any] | None = None
_last_result_time: float = 0.0
_result_ttl: int = 300  # 5 minutes


def invalidate_tournament_cache() -> None:
    """Invalidate the tournament result cache.

    Call this when you want to force a fresh tournament run
    (e.g. after new kline data is available).
    """
    global _last_result, _last_result_time
    _last_result = None
    _last_result_time = 0.0


def _check_tournament_cache(
    regime: str,
    n_candidates: int,
    n_trend: int,
) -> list[dict] | None:
    """Check result cache. Returns cached picks if valid, else None.

    Cache key = (regime, n_candidates, n_trend) -- covers the main
    variables between pipeline.py and meta_predictor.py calls.
    """
    global _last_result, _last_result_time
    if _last_result is None:
        return None
    ck = _last_result.get("_cache_key")
    if ck != (regime, n_candidates, n_trend):
        return None
    if time.time() - _last_result_time > _result_ttl:
        return None
    # Return picks without internal cache metadata
    return [p for p in _last_result["_picks"] if not p.get("_cache_meta")]


def _store_tournament_cache(
    regime: str,
    n_candidates: int,
    n_trend: int,
    picks: list[dict],
) -> None:
    """Store result in module-level cache."""
    global _last_result, _last_result_time
    _last_result = {
        "_cache_key": (regime, n_candidates, n_trend),
        "_picks": picks,
    }
    _last_result_time = time.time()


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class StrategyResult:
    """Single strategy's Top-3 output."""
    name: str
    picks: list[dict]          # list of {code, name, sector, score, ...}
    all_scored: list[dict]     # full ranking
    timestamp: str = ""
    regime: str = ""


@dataclass(slots=True)
class RegimeRecord:
    """Historical performance of a strategy in a given regime."""
    strategy: str
    regime: str
    wins: int = 0
    losses: int = 0
    total_return: float = 0.0       # sum of returns (%)
    sharpe: float = 0.0             # rolling Sharpe
    avg_return: float = 0.0         # mean return per pick
    sample_count: int = 0

    @property
    def win_rate(self) -> float:
        if self.sample_count == 0:
            return 0.0
        return self.wins / self.sample_count * 100

    @property
    def mean_return_pct(self) -> float:
        if self.sample_count == 0:
            return 0.0
        return self.total_return / self.sample_count


# Regime → strategy weight map (updated 2026-07-18 from 60-day backtest)
# fearful: momentum(100%胜率)>>zscore(67%)>capital_flow(33%)>mean_reversion(0%)
# other regimes: theoretical priors pending empirical data
REGIME_WEIGHT_PRIORS: dict[str, dict[str, float]] = {
    "fearful": {
        "momentum":       0.40,  # 100% win rate in 60-day backtest
        "zscore_multi":   0.30,  # 67% win rate
        "capital_flow":   0.20,  # 33% win rate
        "mean_reversion": 0.10,  # 0% win rate — overreaction in panic
    },
    "cautious": {
        "mean_reversion": 0.20,
        "zscore_multi":   0.35,
        "momentum":       0.20,
        "capital_flow":   0.25,
    },
    "normal": {
        "mean_reversion": 0.15,
        "zscore_multi":   0.30,
        "momentum":       0.30,
        "capital_flow":   0.25,
    },
    "complacent": {
        "mean_reversion": 0.10,
        "zscore_multi":   0.20,
        "momentum":       0.40,
        "capital_flow":   0.30,
    },
}

# Default equal-weight fallback
DEFAULT_WEIGHTS: dict[str, float] = {
    "mean_reversion": 0.20,
    "zscore_multi":   0.20,
    "momentum":       0.20,
    "capital_flow":   0.20,
    "consensus":      0.20,
}

# ---------------------------------------------------------------------------
# Thompson Sampling adaptive weights (v2.0)
# ---------------------------------------------------------------------------
# Instead of hardcoded REGIME_WEIGHT_PRIORS, maintain Beta(α,β) per strategy
# per regime. After each tournament round: α += win, β += loss.
# Expected value α/(α+β) → dynamic, empirically-grounded weight.
# Prior: Beta(1,1) = uniform (no prior knowledge), mixed 30% with empirical
# to prevent overfitting on small samples.

_TS_BANDITS: dict[str, dict[str, dict[str, float]]] = {}
# {regime: {strategy: {"alpha": float, "beta": float, "samples": int}}}


def _get_ts_weights(regime: str) -> dict[str, float]:
    """Get Thompson Sampling adaptive weights for current regime.

    Returns dict {strategy_name: weight} normalized to sum to 1.0.
    For regimes with no data, falls back to REGIME_WEIGHT_PRIORS.
    """
    import random as _random

    bandits = _TS_BANDITS.get(regime, {})
    if not bandits:
        # No data yet — use theoretical priors
        return dict(REGIME_WEIGHT_PRIORS.get(regime, DEFAULT_WEIGHTS))

    raw_weights: dict[str, float] = {}
    for sname, stats in bandits.items():
        alpha = stats.get("alpha", 1.0)
        beta_val = stats.get("beta", 1.0)
        # Prior mix: 30% Beta(1,1) prior + 70% empirical
        prior_alpha = 0.3 * 1.0 + 0.7 * alpha
        prior_beta = 0.3 * 1.0 + 0.7 * beta_val
        # Sample from Beta(prior_alpha, prior_beta)
        sample = _random.betavariate(prior_alpha, prior_beta)
        raw_weights[sname] = sample

    # Normalize to sum 1.0
    total = sum(raw_weights.values()) or 1.0
    return {k: round(v / total, 3) for k, v in raw_weights.items()}


def _update_ts_bandit(
    regime: str,
    strategy: str,
    win: bool,
) -> None:
    """Update Thompson Sampling bandit after a tournament round.

    Args:
        regime: QVIX regime (fearful/cautious/normal/complacent)
        strategy: Strategy name
        win: True if strategy's pick was profitable, False otherwise
    """
    if regime not in _TS_BANDITS:
        _TS_BANDITS[regime] = {}
    if strategy not in _TS_BANDITS[regime]:
        _TS_BANDITS[regime][strategy] = {"alpha": 1.0, "beta": 1.0, "samples": 0}

    bandit = _TS_BANDITS[regime][strategy]
    if win:
        bandit["alpha"] += 1.0
    else:
        bandit["beta"] += 1.0
    bandit["samples"] += 1

# ---------------------------------------------------------------------------
# Helper: Z-score (reuse from two_week_picker)
# ---------------------------------------------------------------------------



def _clamp_z(z_vals: list[float], cap: float = 3.0) -> list[float]:
    """Clamp Z-scores to [-cap, cap]."""
    return [max(-cap, min(cap, v)) for v in z_vals]


# ---------------------------------------------------------------------------
# Strategy A: Z-score 多因子 (复用 two_week_picker 逻辑)
# ---------------------------------------------------------------------------

EXCLUDE_SECTORS = {"货币基金", "利率债", "信用债", "债券", "国债", "货币"}
EXCLUDE_TYPES = {"宽基A"}
EXCLUDE_KEYWORDS = [
    "沪深300", "中证500", "中证1000", "上证50", "深证100",
    "创业板", "科创50", "科创100",
]


def _is_wide_base(code: str, info: dict) -> bool:
    if info.get("type") in EXCLUDE_TYPES:
        return True
    if info.get("sector") in ("宽基", "全市场"):
        return True
    name = info.get("name", "")
    if any(kw in name for kw in EXCLUDE_KEYWORDS):
        return True
    return False


def _zscore_strategy(
    trend_map: dict[str, Any],
    pipe_map: dict[str, dict],
    candidates: list[tuple[str, dict]],
) -> StrategyResult:
    """Z-score 多因子策略."""
    raw_factors: dict[str, list[float]] = {
        "trend_momentum": [],
        "risk_adj_momentum": [],
        "quality_elastic": [],
        "oversold_depth": [],
        "drawdown_recov": [],
    }
    scored_indices: list[int] = []

    for idx, (code, info) in enumerate(candidates):
        t = trend_map.get(code)
        if t is None or t.data_days < 10:
            continue
        p = pipe_map.get(code, {})
        if not p:
            continue

        scored_indices.append(idx)
        raw_factors["trend_momentum"].append(t.change_20d)
        raw_factors["risk_adj_momentum"].append(
            t.change_20d / max(t.volatility_20d, 1)
        )
        raw_factors["quality_elastic"].append(-p.get("score", 5.0))
        raw_factors["oversold_depth"].append(-t.change_20d)
        raw_factors["drawdown_recov"].append(-t.max_drawdown)

    n = len(scored_indices)
    if n < 3:
        return StrategyResult(name="zscore_multi", picks=[], all_scored=[])

    z_factors: dict[str, list[float]] = {}
    for k, v in raw_factors.items():
        z_factors[k] = _clamp_z(zscore(v))

    composite: list[float] = []
    weights = {
        "trend_momentum": 0.30,
        "risk_adj_momentum": 0.25,
        "quality_elastic": 0.15,
        "oversold_depth": 0.15,
        "drawdown_recov": 0.15,
    }
    for i in range(n):
        s = sum(z_factors[k][i] * w for k, w in weights.items())
        composite.append(s)

    all_scored: list[dict] = []
    for i in range(n):
        si = scored_indices[i]
        code, info = candidates[si]
        t = trend_map[code]
        p = pipe_map.get(code, {})
        all_scored.append({
            "code": code,
            "name": info.get("name", code),
            "sector": info.get("sector", ""),
            "score": round(composite[i], 3),
            "pipeline_score": p.get("score", 5.0),
            "change_20d": round(t.change_20d, 1),
            "volatility": round(t.volatility_20d, 1),
            "max_drawdown": round(t.max_drawdown, 1),
        })

    all_scored.sort(key=lambda x: -x["score"])
    top3: list[dict] = []
    seen: set[str] = set()
    for r in all_scored:
        if r["sector"] not in seen:
            top3.append(r)
            seen.add(r["sector"])
        if len(top3) >= 3:
            break

    return StrategyResult(name="zscore_multi", picks=top3, all_scored=all_scored)


# ---------------------------------------------------------------------------
# Strategy B: 纯动量策略 (过去N日收益排序)
# ---------------------------------------------------------------------------

def _momentum_strategy(
    trend_map: dict[str, Any],
    pipe_map: dict[str, dict],
    candidates: list[tuple[str, dict]],
    window: int = 20,
) -> StrategyResult:
    """纯动量策略: 按过去window日收益率排序."""
    scored: list[dict] = []

    for code, info in candidates:
        t = trend_map.get(code)
        if t is None or t.data_days < window + 1:
            continue
        change = t.change_20d if window >= 20 else t.change_10d
        # Risk-adjusted momentum: return / volatility
        vol = max(t.volatility_20d, 1)
        ram = change / vol

        scored.append({
            "code": code,
            "name": info.get("name", code),
            "sector": info.get("sector", ""),
            "score": round(ram, 3),
            "raw_return": round(change, 2),
            "volatility": round(vol, 1),
            "risk_level": info.get("risk_level", 0.5),
        })

    scored.sort(key=lambda x: -x["score"])
    top3: list[dict] = []
    seen: set[str] = set()
    for r in scored:
        if r["sector"] not in seen:
            top3.append(r)
            seen.add(r["sector"])
        if len(top3) >= 3:
            break

    return StrategyResult(name="momentum", picks=top3, all_scored=scored)


# ---------------------------------------------------------------------------
# Strategy C: 均值回归 / 超跌反弹 (布林带下轨)
# ---------------------------------------------------------------------------

def _mean_reversion_strategy(
    trend_map: dict[str, Any],
    pipe_map: dict[str, dict],
    candidates: list[tuple[str, dict]],
) -> StrategyResult:
    """均值回归策略: 基于布林带下轨超跌信号 + 回撤修复潜力."""
    scored: list[dict] = []

    for code, info in candidates:
        t = trend_map.get(code)
        if t is None or t.data_days < 20:
            continue

        # Position within 60-day range → lower = more oversold
        pos_pct = t.position_pct
        # Max drawdown recovery potential
        dd_recovery = -t.max_drawdown  # negative dd → positive score
        # Recent short-term momentum (5d) — look for reversal
        c5 = t.change_5d

        # Composite mean-reversion score:
        # - Low position_pct (oversold) → high score
        # - Large drawdown → potential for recovery
        # - Recent plunge → reversal signal
        mr_score = (
            (100 - pos_pct) * 0.40       # oversold depth
            + abs(min(dd_recovery, 30)) * 0.30  # drawdown recovery
            + max(0, -c5) * 0.30          # recent plunge = reversal signal
        )

        scored.append({
            "code": code,
            "name": info.get("name", code),
            "sector": info.get("sector", ""),
            "score": round(mr_score, 3),
            "position_pct": round(pos_pct, 1),
            "max_drawdown": round(t.max_drawdown, 1),
            "change_5d": round(c5, 2),
            "change_20d": round(t.change_20d, 1),
            "risk_level": info.get("risk_level", 0.5),
        })

    scored.sort(key=lambda x: -x["score"])
    top3: list[dict] = []
    seen: set[str] = set()
    for r in scored:
        if r["sector"] not in seen:
            top3.append(r)
            seen.add(r["sector"])
        if len(top3) >= 3:
            break

    return StrategyResult(name="mean_reversion", picks=top3, all_scored=scored)


# ---------------------------------------------------------------------------
# Strategy D: 资金流策略 (sector_flow_bridge 数据)
# ---------------------------------------------------------------------------

def _capital_flow_strategy(
    trend_map: dict[str, Any],
    pipe_map: dict[str, dict],
    candidates: list[tuple[str, dict]],
) -> StrategyResult:
    """资金流策略: 基于 L8_CapitalFlow + 近期资金流入趋势."""
    scored: list[dict] = []

    for code, info in candidates:
        t = trend_map.get(code)
        if t is None or t.data_days < 10:
            continue
        p = pipe_map.get(code, {})

        # Primary signal: L8 capital flow score from pipeline
        l8 = p.get("layer_scores", {}).get("L8_CapitalFlow", 5.0)
        l9 = p.get("layer_scores", {}).get("L9_Signals", 5.0)

        # Secondary: volume ratio as flow proxy
        vr = t.volume_ratio_5_20
        vol_signal = (vr - 1.0) * 10  # >1 = rising volume = inflow

        # Combine: L8/L9 dominate, volume ratio confirms
        cf_score = l8 * 0.40 + l9 * 0.35 + max(vol_signal, 0) * 0.25

        scored.append({
            "code": code,
            "name": info.get("name", code),
            "sector": info.get("sector", ""),
            "score": round(cf_score, 3),
            "l8_capital_flow": round(l8, 1),
            "l9_signals": round(l9, 1),
            "volume_ratio": round(vr, 2),
            "pipeline_score": p.get("score", 5.0),
            "risk_level": info.get("risk_level", 0.5),
        })

    scored.sort(key=lambda x: -x["score"])
    top3: list[dict] = []
    seen: set[str] = set()
    for r in scored:
        if r["sector"] not in seen:
            top3.append(r)
            seen.add(r["sector"])
        if len(top3) >= 3:
            break

    return StrategyResult(name="capital_flow", picks=top3, all_scored=scored)


# ---------------------------------------------------------------------------
# Strategy E: 跨策略共识 (Cross-Strategy Consensus) — v2.0
# ---------------------------------------------------------------------------
# 识别被多个独立策略同时选中的ETF，利用"方法多样性"降低假阳性。
# 共识度≥3的ETF直接入选，共识度=2的作为高优先级候补。
# 零数据依赖 — 仅分析其他策略的输出。


def _consensus_strategy(
    trend_map: dict[str, Any],
    pipe_map: dict[str, dict],
    candidates: list[tuple[str, dict]],
    regime: str = "normal",
    other_strategy_picks: dict[str, list[str]] | None = None,
) -> StrategyResult:
    """Cross-strategy consensus: reward ETFs picked by multiple strategies.

    Args:
        other_strategy_picks: {strategy_name: [code, ...]} from other strategies.
            If None, runs on raw factor consensus (simpler fallback).

    Returns:
        StrategyResult with consensus-ranked picks.
    """
    scored: list[dict] = []

    if other_strategy_picks and len(other_strategy_picks) >= 3:
        # Count how many strategies picked each ETF
        consensus_count: dict[str, int] = {}
        for codes in other_strategy_picks.values():
            for c in codes[:3]:
                consensus_count[c] = consensus_count.get(c, 0) + 1

        for code, info in candidates:
            if code not in trend_map:
                continue
            count = consensus_count.get(code, 0)
            if count >= 2:  # At least 2 strategies agree
                pipe = pipe_map.get(code, {})
                scored.append({
                    "code": code,
                    "name": info.get("name", code),
                    "sector": info.get("sector", ""),
                    "score": count * 30.0 + pipe.get("score", 5.0),  # 共识度为主，pipeline为辅
                    "source": "consensus",
                    "consensus_count": count,
                })
    else:
        # Fallback: rank by pipeline score × trend depth (simple quality filter)
        for code, info in candidates:
            if code not in trend_map:
                continue
            trend = trend_map[code]
            pipe = pipe_map.get(code, {})
            depth = abs(trend.change_20d) if trend.change_20d else 0
            scored.append({
                "code": code,
                "name": info.get("name", code),
                "sector": info.get("sector", ""),
                "score": pipe.get("score", 5.0) * (1 + depth / 20),
                "source": "consensus",
                "consensus_count": 0,
            })

    scored.sort(key=lambda x: -x["score"])

    # Sector dedup → Top 3
    top3: list[dict] = []
    seen: set[str] = set()
    for r in scored:
        if r["sector"] not in seen:
            top3.append(r)
            seen.add(r["sector"])
        if len(top3) >= 3:
            break

    return StrategyResult(name="consensus", picks=top3, all_scored=scored)


# ---------------------------------------------------------------------------
# Tournament Engine
# ---------------------------------------------------------------------------

class StrategyTournament:
    """Multi-strategy prediction tournament engine.

    Runs all strategies, records predictions, tracks performance by regime,
    and produces dynamic ensemble picks.
    """
    import logging
    logger = logging.getLogger(__name__)

    STRATEGIES: list[Any] = [
        _zscore_strategy,
        _momentum_strategy,
        _mean_reversion_strategy,
        _capital_flow_strategy,
        _consensus_strategy,
    ]

    def __init__(self) -> None:
        self._regime_records: dict[str, dict[str, RegimeRecord]] = defaultdict(dict)
        self._prediction_log: list[dict] = []
        self._weights = dict(DEFAULT_WEIGHTS)

    # ── Run all strategies ────────────────────────────────────────────

    @staticmethod
    def _normalize_picks(
        picks: list[dict],
        all_scored: list[dict],
    ) -> tuple[list[dict], list[dict]]:
        """Min-max normalize scores in-place; return (normalized_picks, normalized_all_scored)."""
        raw_scores = [p.get("score", 0.0) for p in all_scored]
        mn = min(raw_scores)
        mx = max(raw_scores)
        rng = mx - mn if mx > mn else 1.0
        for item in all_scored:
            raw = item.get("score", 0.0)
            item["norm_score"] = (raw - mn) / rng  # 0..1
            item["raw_score"] = raw
        # Re-sort all_scored by normalized score descending
        all_scored.sort(key=lambda x: -x.get("norm_score", 0))
        # Update picks to reflect new ordering
        pick_codes = {p["code"] for p in picks}
        picks = [item for item in all_scored if item["code"] in pick_codes]
        return picks[:3], all_scored

    def run_strategies(
        self,
        trend_map: dict[str, Any],
        pipe_map: dict[str, dict],
        candidates: list[tuple[str, dict]],
        regime: str = "normal",
    ) -> dict[str, StrategyResult]:
        """Run all strategies and return results keyed by strategy name.

        Each strategy's scores are min-max normalized to [0, 1] so that
        different-score-scale strategies don't dominate the ensemble.
        """
        results: dict[str, StrategyResult] = {}
        for strat_fn in self.STRATEGIES:
            try:
                result = strat_fn(trend_map, pipe_map, candidates)
                result.regime = regime
                result.timestamp = datetime.now().isoformat()
                # Normalize scores so different-scale strategies don't dominate
                result.picks, result.all_scored = self._normalize_picks(
                    result.picks, result.all_scored
                )
                results[result.name] = result
            except (ValueError, AttributeError, TypeError, OSError, KeyError) as e:
                print(f"  ⚠️ 策略 {strat_fn.__name__} 失败: {e}")
        return results

    # ── Record prediction → verify later ─────────────────────────────

    def log_prediction(
        self,
        results: dict[str, StrategyResult],
        regime: str,
        date_str: str = "",
    ) -> None:
        """Log current predictions for future verification."""
        if not date_str:
            date_str = date.today().isoformat()

        entry: dict[str, Any] = {
            "date": date_str,
            "regime": regime,
            "timestamp": datetime.now().isoformat(),
            "strategies": {},
        }
        for name, res in results.items():
            entry["strategies"][name] = {
                "top3": [{"code": p["code"], "score": p.get("score", 0)}
                         for p in res.picks[:3]],
            }

        self._prediction_log.append(entry)

        # Append to JSONL file for persistence
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(TOURNAMENT_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            logger.warning("strategy_tournament: failed to write tournament log")

    # ── Verify past predictions ───────────────────────

    def verify_prediction(
        self,
        strategy_name: str,
        picks: list[dict],
        actual_returns: dict[str, float],
    ) -> None:
        """Record verification results for a strategy's picks.

        Args:
            strategy_name: Which strategy to credit
            picks: Top3 picks from the prediction
            actual_returns: {code: actual_10d_return_pct}
        """
        for pick in picks[:3]:
            code = pick["code"]
            ret = actual_returns.get(code, 0.0)
            is_win = ret > 0

            # Find or create regime record
            key = f"{strategy_name}"  # simplified: no regime tracking here
            if key not in self._regime_records:
                self._regime_records[key] = {}

            # Aggregate across all regimes for now (can be extended)
            rec_key = "all_regimes"
            if rec_key not in self._regime_records[key]:
                self._regime_records[key][rec_key] = RegimeRecord(
                    strategy=strategy_name, regime="all"
                )
            rec = self._regime_records[key][rec_key]
            rec.sample_count += 1
            rec.total_return += ret
            if is_win:
                rec.wins += 1
            else:
                rec.losses += 1

            # Recompute Sharpe
            if rec.sample_count >= 2:
                # Simplified: use running stats
                rec.avg_return = rec.total_return / rec.sample_count
                rec.sharpe = rec.avg_return / max(abs(rec.avg_return) * 0.1, 0.01)

    def verify_by_regime(
        self,
        strategy_name: str,
        picks: list[dict],
        actual_returns: dict[str, float],
        regime: str,
    ) -> None:
        """Record verification results tagged with regime."""
        for pick in picks[:3]:
            code = pick["code"]
            ret = actual_returns.get(code, 0.0)
            is_win = ret > 0

            if strategy_name not in self._regime_records:
                self._regime_records[strategy_name] = {}

            if regime not in self._regime_records[strategy_name]:
                self._regime_records[strategy_name][regime] = RegimeRecord(
                    strategy=strategy_name, regime=regime
                )
            rec = self._regime_records[strategy_name][regime]
            rec.sample_count += 1
            rec.total_return += ret
            if is_win:
                rec.wins += 1
            else:
                rec.losses += 1

            if rec.sample_count >= 2:
                rec.avg_return = rec.total_return / rec.sample_count
                ret_list = []
                for p in picks[:3]:
                    ret_list.append(actual_returns.get(p["code"], 0.0))
                if len(ret_list) >= 2:
                    std_r = statistics.stdev(ret_list)
                    rec.sharpe = (
                        rec.avg_return / max(std_r, 0.01)
                        if std_r > 0 else 0.0
                    )

    # ── Dynamic weight update from historical performance ────────────

    def update_weights_from_performance(self) -> None:
        """Update strategy weights based on historical Sharpe/win-rate per regime."""
        # For each regime, find best-performing strategy
        for regime, records in self._regime_records.items():
            if regime == "all_regimes" or regime == "all":
                continue
            best_name = ""
            best_score = -999
            for sname, rec in records.items():
                # Composite score: 60% win_rate + 40% normalized_sharpe
                nr = rec.sharpe / max(abs(rec.sharpe), 1) if rec.sharpe != 0 else 0
                score = rec.win_rate * 0.6 + nr * 40 * 0.4
                if score > best_score:
                    best_score = score
                    best_name = sname

            if best_name:
                # Boost best strategy, reduce others proportionally
                # FIX: use DEFAULT_WEIGHTS as baseline (was hardcoded 0.25,
                # out of sync after DEFAULT_WEIGHTS changed to 0.20)
                boost = 0.15
                base_default = DEFAULT_WEIGHTS.get(best_name, 0.20)
                for sname in DEFAULT_WEIGHTS:
                    if sname == best_name:
                        self._weights[sname] = min(
                            0.50,
                            self._weights.get(sname, base_default) + boost,
                        )
                    else:
                        self._weights[sname] = max(
                            0.05,
                            self._weights.get(sname, DEFAULT_WEIGHTS.get(sname, 0.20)) * (1 - boost / 3),
                        )

        # Normalize weights
        total = sum(self._weights.values())
        if total > 0:
            self._weights = {k: v / total for k, v in self._weights.items()}

    # ── Ensemble picks ───────────────────────────────────────────────

    def get_ensemble_picks(
        self,
        results: dict[str, StrategyResult],
        regime: str = "normal",
        top_n: int = 3,
    ) -> list[dict]:
        """Produce ensemble picks weighted by regime-aware strategy performance.

        Method:
          1. Get regime-specific weights
          2. Collect all picks from all strategies
          3. Score each unique ETF by weighted average of strategy scores
          4. Return Top-N with industry dedup

        Returns:
            List of {code, name, sector, ensemble_score, contributing_strategies}
        """
        # Get weights for current regime — blend TS adaptive + theoretical priors
        ts_weights = _get_ts_weights(regime)
        prior_weights = REGIME_WEIGHT_PRIORS.get(regime, DEFAULT_WEIGHTS).copy()
        # Merge: TS weights for strategies with data, prior for new ones
        weights = prior_weights.copy()
        for sname, ts_w in ts_weights.items():
            if sname in weights:
                # 60% TS empirical + 40% theoretical prior
                weights[sname] = 0.6 * ts_w + 0.4 * weights.get(sname, DEFAULT_WEIGHTS.get(sname, 0.20))

        # If we have historical performance data, blend it with priors
        if self._regime_records:
            regime_records = self._regime_records.get(regime, {})
            if regime_records:
                # Blend: 70% prior + 30% empirical
                for sname, rec in regime_records.items():
                    if rec.sample_count >= 3:
                        empirical_weight = rec.win_rate / 100.0
                        current = weights.get(sname, DEFAULT_WEIGHTS.get(sname, 0.20))
                        weights[sname] = 0.7 * current + 0.3 * empirical_weight

        # Normalize weights
        w_total = sum(weights.values())
        if w_total > 0:
            weights = {k: v / w_total for k, v in weights.items()}

        # Scores are already min-max normalized to [0, 1] in run_strategies().
        # Use the pre-computed norm_score; fall back to raw score / 100 if missing.
        all_picks: dict[str, dict] = {}  # code → aggregated info
        strategy_contributions: dict[str, list[str]] = defaultdict(list)

        for sname, res in results.items():
            w = weights.get(sname, DEFAULT_WEIGHTS.get(sname, 0.20))
            for pick in res.picks[:3]:
                code = pick["code"]
                raw_score = pick.get("raw_score", pick.get("score", 0))
                norm_score = pick.get("norm_score", raw_score / 100.0 if raw_score > 1 else raw_score)
                if code in all_picks:
                    existing = all_picks[code]
                    existing["weighted_score"] += norm_score * w
                    existing["weight_sum"] += w
                    if sname not in existing["strategies"]:
                        existing["strategies"].append(sname)
                else:
                    all_picks[code] = {
                        "code": code,
                        "name": pick.get("name", code),
                        "sector": pick.get("sector", ""),
                        "weighted_score": norm_score * w,
                        "weight_sum": w,
                        "strategies": [sname],
                        "raw_score": raw_score,
                        "norm_score": round(norm_score, 3),
                    }
                    strategy_contributions[sname].append(code)

        # Average weighted scores
        ensemble: list[dict] = []
        for code, info in all_picks.items():
            avg_score = info["weighted_score"] / max(info["weight_sum"], 0.001)
            ensemble.append({
                "code": code,
                "name": info["name"],
                "sector": info["sector"],
                "ensemble_score": round(avg_score, 3),
                "contributing_strategies": info["strategies"],
                "strategy_weights": {
                    s: round(weights.get(s, 0), 3) for s in info["strategies"]
                },
            })

        # Sort by ensemble score descending
        ensemble.sort(key=lambda x: -x["ensemble_score"])

        # Industry dedup
        top: list[dict] = []
        seen_sectors: set[str] = set()
        for item in ensemble:
            if item["sector"] not in seen_sectors:
                top.append(item)
                seen_sectors.add(item["sector"])
            if len(top) >= top_n:
                break

        return top

    # ── Performance matrix ───────────────────────────────────────────

    def get_performance_matrix(self) -> dict[str, dict[str, dict]]:
        """Return performance matrix: {strategy: {regime: {win_rate, sharpe, ...}}}."""
        matrix: dict[str, dict[str, dict]] = {}
        for sname, regimes in self._regime_records.items():
            matrix[sname] = {}
            for regime, rec in regimes.items():
                matrix[sname][regime] = {
                    "win_rate": round(rec.win_rate, 1),
                    "avg_return_pct": round(rec.avg_return, 2),
                    "sharpe": round(rec.sharpe, 3),
                    "sample_count": rec.sample_count,
                    "wins": rec.wins,
                    "losses": rec.losses,
                }
        return matrix

    # ── Format report ────────────────────────────────────────────────

    @staticmethod
    def format_tournament_report(
        results: dict[str, StrategyResult],
        ensemble: list[dict],
        regime: str,
        weights_used: dict[str, float],
        matrix: dict[str, dict[str, dict]],
    ) -> str:
        """Format full tournament report."""
        lines = [
            "🏆 多策略预测锦标赛 — " + regime.upper() + " 状态",
            "=" * 60,
            "",
            "  市场状态: " + regime + " | 策略权重:",
        ]
        for sname, w in sorted(weights_used.items(), key=lambda x: -x[1]):
            lines.append(f"    {sname}: {w:.1%}")

        # Individual strategy results
        lines.extend([
            "",
            "  ── 各策略 Top3 ──",
        ])
        for sname, res in sorted(results.items()):
            icon = "🥇" if res.picks else "⚪"
            lines.append(f"\n  {icon} [{sname}] ({len(res.picks)} picks)")
            for i, p in enumerate(res.picks[:3], 1):
                lines.append(
                    f"    {i}. {p['code']} {p.get('name', '')} "
                    f"({p.get('sector', '')}) "
                    f"raw={p.get('raw_score', p.get('score', 0)):.3f} "
                    f"norm={p.get('norm_score', 0):.3f}"
                )

        # Ensemble picks
        lines.extend([
            "",
            f"  ── Ensemble Top{min(len(ensemble), 3)} (动态加权) ──",
        ])
        for i, p in enumerate(ensemble[:3], 1):
            strategies = ", ".join(p.get("contributing_strategies", []))
            lines.append(
                f"  {i}. {p['code']} {p.get('name', '')} "
                f"[{p.get('sector', '')}] "
                f"score={p['ensemble_score']:.3f} "
                f"(策略: {strategies})"
            )

        # Performance matrix
        if matrix:
            lines.extend([
                "",
                "  ── 历史表现矩阵 ──",
            ])
            for sname, regimes in matrix.items():
                lines.append(f"\n  [{sname}]")
                for regime, stats in regimes.items():
                    lines.append(
                        f"    {regime}: 胜率{stats['win_rate']:.0f}% | "
                        f"均收益{stats['avg_return_pct']:+.2f}% | "
                        f"Sharpe{stats['sharpe']:.2f} | "
                        f"样本{stats['sample_count']}"
                    )

        lines.append(f"{'=' * 60}")
        lines.append("锦标赛结果 · 不构成投资建议")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Quick backtest helper: simulate N days of predictions → verify
# ---------------------------------------------------------------------------

def simulate_60day_backtest(
    days: int = 60,
    max_candidates: int = 60,
) -> dict[str, Any]:
    """Quick 60-trading-day simulated backtest.

    Uses real kline data to produce predictions, then verifies against
    actual returns. Does NOT wait 10 days — uses available data.

    Returns:
        dict with tournament_results, performance_matrix, ensemble_picks
    """
    from etf_platform.config_loader import load_etfs
    from etf_platform.data.kline import get_trend_batch
    from etf_platform.pipeline import batch_full
    from etf_platform.analysis.qvix_regime import get_regime

    print("=" * 60)
    print("🏆 60日模拟回测 — 多策略锦标赛")
    print("=" * 60)

    # Load ETFs
    etfs = load_etfs()
    tournament = StrategyTournament()

    # Filter candidates
    candidates: list[tuple[str, dict]] = []
    for code, info in etfs.items():
        if not code.isdigit():
            continue
        if _is_wide_base(code, info):
            continue
        if info.get("sector", "") in EXCLUDE_SECTORS:
            continue
        if info.get("access") != "buyable":
            continue
        candidates.append((code, info))

    if len(candidates) > max_candidates:
        candidates = candidates[:max_candidates]

    print(f"\n候选池: {len(candidates)} 只行业ETF")

    # Get QVIX regime
    try:
        qvix_data = get_regime()
        regime = qvix_data.get("regime", "normal")
    except (ImportError, KeyError, ValueError, TypeError, AttributeError, OSError):
        regime = "normal"
    print(f"当前 QVIX 状态: {regime}")

    # Fetch kline data for all candidates
    codes = [c[0] for c in candidates]
    print("\n正在获取行情数据...")
    trend_map = get_trend_batch(codes)
    valid_codes = list(trend_map.keys())
    print(f"有效数据: {len(valid_codes)} 只")

    # Batch pipeline
    print("正在运行穿透评分...")
    pipe_results = batch_full(limit=len(valid_codes), live=False, codes=valid_codes)
    pipe_map: dict[str, dict] = {}
    for pr in pipe_results:
        c = pr.get("etf_code", pr.get("code", ""))
        if c:
            pipe_map[c] = pr
    print(f"Pipeline 完成: {len(pipe_map)} 只")

    # Build filtered candidate list
    filtered_candidates = [
        (code, info) for code, info in candidates if code in trend_map
    ]

    # ── Run tournament ──────────────────────────────────────────────
    print(f"\n运行多策略锦标赛 ({regime} 状态)...")
    t0 = time.time()
    results = tournament.run_strategies(
        trend_map, pipe_map, filtered_candidates, regime=regime
    )
    elapsed = time.time() - t0
    print(f"策略运行耗时: {elapsed:.1f}s")

    # Log predictions
    tournament.log_prediction(results, regime)

    # ── Verify against actual returns ───────────────────────────────
    print("\n验证各策略预测准确性...")
    for sname, res in results.items():
        actual_returns: dict[str, float] = {}
        for pick in res.picks:
            code = pick["code"]
            t = trend_map.get(code)
            if t:
                actual_returns[code] = t.change_10d
        tournament.verify_by_regime(sname, res.picks, actual_returns, regime)

    # Update weights from performance
    tournament.update_weights_from_performance()

    # ── Ensemble picks ──────────────────────────────────────────────
    ensemble = tournament.get_ensemble_picks(results, regime, top_n=3)

    # ── Compare: Z-score vs Ensemble ────────────────────────────────
    zscore_result = results.get("zscore_multi")
    zscore_codes = [p["code"] for p in zscore_result.picks[:3]] if zscore_result else []
    ensemble_codes = [p["code"] for p in ensemble[:3]]

    print(f"\n  Z-score Top3: {zscore_codes}")
    print(f"  Ensemble Top3: {ensemble_codes}")
    overlap = set(zscore_codes) & set(ensemble_codes)
    print(f"  重叠: {len(overlap)}/3")

    # ── Performance matrix ──────────────────────────────────────────
    matrix = tournament.get_performance_matrix()

    # ── Print full report ───────────────────────────────────────────
    weights_used = REGIME_WEIGHT_PRIORS.get(regime, DEFAULT_WEIGHTS)
    report = StrategyTournament.format_tournament_report(
        results, ensemble, regime, weights_used, matrix
    )
    print(report)

    # ── Per-regime breakdown (if we have data) ──────────────────────
    print(f"\n{'=' * 60}")
    print("详细性能分析:")
    print("=" * 60)
    for sname, regimes in matrix.items():
        print(f"\n  [{sname}]")
        for reg, stats in regimes.items():
            bar_len = int(stats["win_rate"] / 5)
            bar = "█" * bar_len + "░" * (20 - bar_len)
            print(
                f"    {reg:12s} | {bar} | 胜率 {stats['win_rate']:5.1f}% | "
                f"收益 {stats['avg_return_pct']:+6.2f}% | "
                f"Sharpe {stats['sharpe']:6.2f} | n={stats['sample_count']}"
            )

    # ── Save results ────────────────────────────────────────────────
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        summary = {
            "regime": regime,
            "candidates": len(filtered_candidates),
            "strategies_run": list(results.keys()),
            "ensemble_picks": ensemble,
            "performance_matrix": matrix,
            "weights_used": weights_used,
            "zscore_top3": zscore_codes,
            "ensemble_top3": ensemble_codes,
            "overlap": len(overlap),
            "elapsed_seconds": round(elapsed, 2),
            "timestamp": datetime.now().isoformat(),
        }
        with open(RESULT_JSON, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2, default=str)
        print(f"\n结果已保存: {RESULT_JSON}")
    except OSError as e:
        print(f"保存结果失败: {e}")

    return summary


# ---------------------------------------------------------------------------
# Pipeline integration helper
# ---------------------------------------------------------------------------

def get_ensemble_for_pipeline(
    trend_map: dict[str, Any],
    pipe_map: dict[str, dict],
    candidates: list[tuple[str, dict]],
    regime: str = "normal",
) -> list[dict]:
    """Convenience wrapper for pipeline.py integration.

    Called from pipeline.py's run_full() or batch_full() exit path.
    Returns ensemble picks and prints comparison vs Z-score.
    """
    tournament = StrategyTournament()
    results = tournament.run_strategies(
        trend_map, pipe_map, candidates, regime
    )
    ensemble = tournament.get_ensemble_picks(results, regime, top_n=3)

    # Comparison
    zscore_picks = results.get("zscore_multi")
    if zscore_picks and zscore_picks.picks:
        z_codes = [p["code"] for p in zscore_picks.picks[:3]]
        e_codes = [p["code"] for p in ensemble[:3]]
        overlap = len(set(z_codes) & set(e_codes))

        print(f"\n  📊 [锦标赛] Z-score picks: {z_codes}")
        print(f"  📊 [锦标赛] Ensemble picks: {e_codes}")
        print(f"  📊 [锦标赛] 对比: 重叠{overlap}/3")

    return ensemble


# ---------------------------------------------------------------------------
# MetaPredictor 桥接：模块级 wrapper
# ---------------------------------------------------------------------------

def get_ensemble_picks() -> list[dict]:
    """MetaPredictor 标准接口：运行锦标赛并返回Ensemble Top3。

    这是一个模块级函数（非类方法），供 meta_predictor.py 调用。
    自动检测当前QVIX regime，运行所有策略，返回融合后的Top3。
    """
    from etf_platform.config_loader import load_etfs
    from etf_platform.data.kline import get_trend_batch
    from etf_platform.pipeline import batch_full
    from etf_platform.analysis.qvix_regime import get_regime

    try:
        rd = get_regime()
        regime = rd.get("regime", "normal")
    except (ImportError, KeyError, ValueError, TypeError, AttributeError, OSError):
        regime = "normal"

    etfs = load_etfs()
    candidates: list[tuple[str, dict]] = []
    EXCLUDE_SECTORS = {"货币基金", "利率债", "信用债", "债券", "国债", "货币"}
    for code, info in etfs.items():
        if not code.isdigit():
            continue
        if info.get("sector", "") in EXCLUDE_SECTORS:
            continue
        if info.get("access") != "buyable":
            continue
        name = info.get("name", "")
        if any(kw in name for kw in ["沪深300", "中证500", "上证50", "科创50", "创业板"]):
            continue
        candidates.append((code, info))
        if len(candidates) >= 40:
            break

    codes = [c[0] for c in candidates]
    trend_map = get_trend_batch(codes)
    pipe_results = batch_full(limit=len(codes), live=False, codes=list(trend_map.keys()))
    pipe_map: dict[str, dict] = {}
    for pr in pipe_results:
        c = pr.get("etf_code", pr.get("code", ""))
        if c:
            pipe_map[c] = pr

    filtered = [(c, i) for c, i in candidates if c in trend_map]
    tournament = StrategyTournament()
    results = tournament.run_strategies(trend_map, pipe_map, filtered, regime)
    ensemble = tournament.get_ensemble_picks(results, regime, top_n=3)

    # Convert to MetaPredictor format
    predictions: list[dict] = []
    for p in ensemble:
        score = p.get("ensemble_score", p.get("norm_score", 50))
        if isinstance(score, (int, float)) and score <= 1.0:
            score = score * 100  # Normalize 0-1 → 0-100
        predictions.append({
            "code": p.get("code", ""),
            "name": p.get("name", ""),
            "sector": p.get("sector", ""),
            "score": round(min(100, max(0, float(score))), 1),
            "source": "tournament",
            "contributing_strategies": p.get("strategies", p.get("contributing_strategies", [])),
        })

    return predictions


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="ETF 多策略预测锦标赛 v1.0"
    )
    parser.add_argument(
        "--simulate", action="store_true",
        help="Run 60-day simulated backtest",
    )
    parser.add_argument(
        "--quick", action="store_true",
        help="Quick single-run tournament (no backtest)",
    )
    parser.add_argument(
        "--regime", type=str, default="",
        help="Force regime (fearful/cautious/normal/complacent)",
    )
    args = parser.parse_args()

    if args.simulate:
        result = simulate_60day_backtest()
        print(f"\n✅ 回测完成: {result.get('strategies_run')}")
    elif args.quick:
        regime = args.regime or "normal"
        from etf_platform.config_loader import load_etfs
        from etf_platform.data.kline import get_trend_batch
        from etf_platform.pipeline import batch_full

        etfs = load_etfs()
        candidates = []
        for code, info in etfs.items():
            if not code.isdigit():
                continue
            if _is_wide_base(code, info):
                continue
            if info.get("sector", "") in EXCLUDE_SECTORS:
                continue
            if info.get("access") != "buyable":
                continue
            candidates.append((code, info))

        if len(candidates) > 50:
            candidates = candidates[:50]

        codes = [c[0] for c in candidates]
        trend_map = get_trend_batch(codes)
        pipe_results = batch_full(limit=len(codes), live=False, codes=list(trend_map.keys()))
        pipe_map = {}
        for pr in pipe_results:
            c = pr.get("etf_code", pr.get("code", ""))
            if c:
                pipe_map[c] = pr

        filtered = [(c, i) for c, i in candidates if c in trend_map]
        result = StrategyTournament()
        outcomes = result.run_strategies(trend_map, pipe_map, filtered, regime)
        ensemble = result.get_ensemble_picks(outcomes, regime, top_n=3)

        report = StrategyTournament.format_tournament_report(
            outcomes, ensemble, regime,
            REGIME_WEIGHT_PRIORS.get(regime, DEFAULT_WEIGHTS),
            result.get_performance_matrix(),
        )
        print(report)
    else:
        parser.print_help()
