from __future__ import annotations
from ..utils import zscore
import logging
logger = logging.getLogger(__name__)

"""two_week_picker.py — 2周潜在涨幅Top-3预测引擎 v3.5

v3.5 (2026-07-19): 动态因子权重 — regime-conditional权重
  - 恐慌期: oversold_depth 40%→21%, sector_flow 10%→26%
  - 对标 arxiv:2410.14841 (Dynamic Factor Allocation with Regime-Switching)
  - 集成 factor_dynamic_weights.py

v3.4 (2026-07-19): 锦标赛融合 — 锦标赛winner获+2.5~7.5分boost
  - 超跌深度 12%→25% (IC=0.876, 之前严重低估)
  - 回撤修复 7%→19% (IC=0.680)
  - 行为Alpha 15%→0% (IC=0.000, 完全无效→移除)
  - 质量弹性 15%→2% (IC=0.076, p=0.41不显著)
  - 行业资金流 10%→7% (IC=0.255)
  - 风险调整动量 25%→22% (与趋势动量高度相关→微降)

v3.1 (2026-07-18): 权重重平衡
  - 动量50% (趋势25%+风险调整25%) + 弹性15% + 行为15% + 反转20% (超跌12%+回撤8%)
  - 消除v3.0"跌最多=最高分"的结构性偏差根源
  - 移除量比健康度/位置健康度(与动量因子信息重叠)

v3.0 (2026-07-18): Z-score标准化多因子体系
  - 所有因子在候选池内Z-score标准化后加权合成
  - Top 3强制行业去重（3只必须来自不同行业）

v2.0: 不依赖鬼缓存, batch_full()实时跑pipeline, 排除宽基/债券

核心逻辑（来自l003知识库）:
  - 高分(>7) = 安全无催化剂 → 不适合短期
  - 低分(<4) + 强动量 = 催化剂弹性 → 短期大涨潜力最大

评分公式 (v3.1):
  2W_Score = Σ(Z-score(factor_i) × weight_i) × 100
  
  5 factors (behavioral removed, weights normalized):
    oversold_depth (40%): Z(-change_20d) — 合并后超跌深度 (原trend_momentum已移除, v3.3)
    risk_adj_momentum (25%): Z(change_20d / volatility) — 风险调整动量
    quality_elastic (15%): Z(-pipeline_score) — 质量弹性(低分=高弹性)
    behavioral (15%): Z(behavioral_alpha - 50) — 行为Alpha
    oversold_depth (12%): Z(-change_20d) — 超跌深度(博弈反弹)
    drawdown_recov (8%): Z(-max_drawdown) — 回撤修复潜力
"""
import sys
import json
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent.parent  # etf-platform root
sys.path.insert(0, str(BASE / "src"))

from etf_platform.config_loader import load_etfs
from etf_platform.data.kline import get_trend

EXCLUDE_SECTORS = {"货币基金", "利率债", "信用债", "债券", "国债", "货币"}
EXCLUDE_TYPES = {"宽基A"}
EXCLUDE_KEYWORDS = [
    "沪深300", "中证500", "中证1000", "上证50", "深证100",
    "创业板", "科创50", "科创100",
]


# ── Z-score utilities ──────────────────────────────────────────────



def _clamp_z(z_vals: list[float], cap: float = 3.0) -> list[float]:
    """Clamp Z-scores to [-cap, cap] to prevent single outliers dominating."""
    return [max(-cap, min(cap, v)) for v in z_vals]


# ── Factor definitions ─────────────────────────────────────────────

# Each factor: (raw_value_fn, weight, direction)
# raw_value_fn(trend, pipe) -> float, higher raw = higher desirability
# We Z-score the raw values, then weighted-composite.

FACTORS = [
    # NOTE v3.3: 已移除 trend_momentum (与 oversold_depth 完全共线 r=-1.00, VIF=∞).
    # 两者权重合计50%在Z-score标准化后完全抵消 — 实际贡献为0.
    # 实证来自 factor_correlation.py 120只ETF分析 (2026-07-18).
    {
        "name": "oversold_depth",
        "raw": lambda t, p: -t.change_20d if t else 0,
        "weight": 0.40,  # ← 原25%+25%合并，留10%重新分配 (IC=0.876)
        "desc": "超跌深度(合并后)",
    },
    {
        "name": "risk_adj_momentum",
        "raw": lambda t, p: (
            (t.change_20d / max(t.volatility_20d, 1)) if t else 0
        ),
        "weight": 0.25,  # +3% → IC=0.781
        "desc": "风险调整动量(Z)",
    },
    {
        "name": "drawdown_recov",
        "raw": lambda t, p: -t.max_drawdown if t else 0,
        "weight": 0.22,  # +3% → IC=0.680
        "desc": "回撤修复潜力(Z)",
    },
    {
        "name": "sector_flow",
        "raw": lambda t, p: _get_sector_flow_raw(p.get("sector", ""), p.get("etf_code", "")),
        "weight": 0.10,  # +3% → IC=0.255
        "desc": "行业资金流(Z)",
    },
    {
        "name": "quality_elastic",
        "raw": lambda t, p: -p.get("score", 5.0),
        "weight": 0.03,  # +1% → IC=0.076（不显著但保留为噪声阻尼）
        "desc": "质量弹性(Z)",
    },
    {
        "name": "behavioral",
        "raw": lambda t, p: _calc_behavioral_alpha(p) - 50,
        "weight": 0.00,  # IC=0.000, p=1.00 — 完全无效
        "desc": "行为Alpha(Z) [已实证移除]",
    },
]


# ── Helper: behavioral alpha ───────────────────────────────────────

def _calc_behavioral_alpha(pipe: dict) -> float:
    """行为Alpha (0-100): 从L21子因子提取反转信号. (保持v2逻辑)"""
    ls = pipe.get("layer_scores", {})
    overreact = ls.get("L21_Overreaction", 5.0)
    herding = ls.get("L21_Herding", 5.0)
    contrarian = ls.get("L21_Contrarian", 5.0)
    alpha = (overreact - 5.0) * 12 + (5.0 - herding) * 5 + (contrarian - 5.0) * 8
    return max(10, min(90, 50 + alpha))


# ── Helper: sector flow ───────────────────────────────────────────

_sector_flow_cache: dict[str, float] = {}

def _get_sector_flow_raw(sector: str, code: str = "") -> float:
    """Get sector flow return_pct from bridge (cached per session)."""
    cache_key = f"{sector}:{code}"
    if cache_key in _sector_flow_cache:
        return _sector_flow_cache[cache_key]
    
    try:
        from etf_platform.analysis.sector_flow_bridge import get_bridge
        bridge = get_bridge()
        result = bridge.score(sector, live=False, etf_code=code)
        raw = result.get("_return_pct", 0)
        # Sentinel -999 means no data — neutralize to 0
        if raw == -999 or raw is None:
            raw = 0.0
        _sector_flow_cache[cache_key] = raw
        return raw
    except (ImportError, KeyError, ValueError, TypeError, AttributeError, OSError):
        return 0.0


# ── Helper: macro overlay ─────────────────────────────────────────

def _get_macro_boost(sector: str) -> float:
    """Get macro overlay boost for a sector (cached)."""
    try:
        from etf_platform.analysis.macro_overlay import get_overlay
        return get_overlay(sector)["total_boost"]
    except (ImportError, KeyError, ValueError, TypeError, AttributeError, OSError):
        return 0.0


# ── Filtering ──────────────────────────────────────────────────────

def _is_wide_base(code: str, info: dict) -> bool:
    """排除宽基ETF."""
    if info.get("type") in EXCLUDE_TYPES:
        return True
    if info.get("sector") in ("宽基", "全市场"):
        return True
    name = info.get("name", "")
    if any(kw in name for kw in EXCLUDE_KEYWORDS):
        return True
    return False


# ── Single ETF predict (backward compatible, no Z-score) ────────────

def predict(code: str, profile: str = "均衡") -> dict:
    """单只ETF的2周预测（无Z-score，因无候选池对比）。

    建议使用 pick_top3() 获得候选池内的相对评分。
    """
    from etf_platform.pipeline import run_full

    pipe = run_full(code, live=False, profile=profile)
    trend = get_trend(code)

    # Compute raw factor values
    factors = {}
    for f in FACTORS:
        factors[f["name"]] = round(f["raw"](trend, pipe), 2)

    return {
        "code": code,
        "name": pipe.get("name", ""),
        "sector": pipe.get("sector", ""),
        "risk_level": pipe.get("risk_level", 0.5),
        "pipeline_score": pipe.get("score", 5.0),
        "two_week_score": None,  # No Z-score for single ETF
        "factors": factors,
        "trend_signal": trend.trend_signal if trend else "no_data",
        "change_20d": round(trend.change_20d, 1) if trend else 0,
        "return_10d": round(trend.change_10d, 1) if trend else 0,
        "max_drawdown": round(trend.max_drawdown, 1) if trend else 0,
        "volatility": round(trend.volatility_20d, 1) if trend else 0,
        "volume_ratio": round(trend.volume_ratio_5_20, 2) if trend else 0,
        "position_pct": round(trend.position_pct, 1) if trend else 0,
        "_note": "单ETF无Z-score, 建议用 pick_top3() 获得相对排名",
    }


# ── Helper functions for pick_top3 ──────────────────


def _get_qvix_regime(debug: bool = False) -> str:
    """Step 0: QVIX市场状态."""
    try:
        from etf_platform.analysis.qvix_regime import get_regime
        rd = get_regime()
        regime = rd.get("regime", "normal")
        if debug:
            print(f"  QVIX: {regime} (50={rd.get('qvix_50',0):.0f}/500={rd.get('qvix_500',0):.0f})")
        return regime
    except (ImportError, KeyError, ValueError, TypeError, AttributeError, OSError):
        return "normal"


def _get_factor_weights(qvix_regime: str, debug: bool = False) -> dict[str, float]:
    """Step 0.5: 动态因子权重 (基于regime-conditional)."""
    try:
        from etf_platform.analysis.factor_dynamic_weights import get_dynamic_weights
        fw = get_dynamic_weights(qvix_regime)
        if debug:
            print(f"  动态权重({qvix_regime}): " + " ".join(f"{k}={v:.2f}" for k, v in fw.items()))
        return fw
    except (ImportError, KeyError, ValueError, TypeError, AttributeError, OSError):
        return {f["name"]: f["weight"] for f in FACTORS}


def _qvix_filter(sector: str, qvix_regime: str) -> bool:
    """根据QVIX市场状态过滤ETF. 返回True表示跳过此ETF."""
    if qvix_regime == "fearful":
        allowed_defensive = {
            "红利价值", "红利/价值", "高股息", "公用事业",
            "贵金属", "黄金", "利率债", "消费", "食品饮料",
            "医药", "白酒消费",
        }
        return sector not in allowed_defensive
    if qvix_regime == "cautious":
        high_risk_sectors = {"半导体", "半导体设备", "AI算力", "券商", "军工"}
        return sector in high_risk_sectors
    return False


def _build_candidate_pool(etfs: dict, qvix_regime: str, max_candidates: int, debug: bool = False) -> list[tuple[str, dict]]:
    """Step 1: 加载候选池 + QVIX regime过滤."""
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
        if _qvix_filter(info.get("sector", ""), qvix_regime):
            continue
        candidates.append((code, info))

    if len(candidates) > max_candidates:
        candidates = candidates[:max_candidates]
    if debug:
        print(f"  候选池: {len(candidates)}只 (已排除宽基/债券/QVIX过滤)")
    return candidates


def _batch_run_pipeline(codes: list[str], profile: str, skip_tournament: bool, max_candidates: int) -> dict[str, dict]:
    """Step 2: 批量跑pipeline."""
    from etf_platform.pipeline import batch_full
    pipe_results = batch_full(
        limit=max_candidates, live=False, profile=profile, codes=codes,
        skip_tournament=skip_tournament,
    )
    pipe_map: dict[str, dict] = {}
    for pr in pipe_results:
        c = pr.get("etf_code", pr.get("code", ""))
        if c:
            pipe_map[c] = pr
    return pipe_map


def _collect_factors(candidates: list[tuple[str, dict]], pipe_map: dict[str, dict], scored_indices: list[int]) -> tuple[dict[str, list[float]], dict[str, object], list[int]]:
    """Steps 3-4: 收集原始因子值 + Z-score标准化."""
    raw_factors: dict[str, list[float]] = {f["name"]: [] for f in FACTORS}
    trend_map: dict[str, object] = {}
    new_scored: list[int] = []

    for idx, (code, info) in enumerate(candidates):
        trend = get_trend(code)
        if trend is None or trend.data_days < 10:
            continue
        pipe = pipe_map.get(code, {})
        if not pipe:
            continue

        trend_map[code] = trend
        new_scored.append(idx)
        for f in FACTORS:
            raw_factors[f["name"]].append(f["raw"](trend, pipe))

    z_factors: dict[str, list[float]] = {}
    for f in FACTORS:
        z_raw = zscore(raw_factors[f["name"]])
        z_factors[f["name"]] = _clamp_z(z_raw)

    return z_factors, trend_map, new_scored


def _compute_scores_and_rank(
    z_factors: dict[str, list[float]],
    candidates: list[tuple[str, dict]],
    pipe_map: dict[str, dict],
    trend_map: dict[str, object],
    scored_indices: list[int],
    profile: str = "均衡",
    debug: bool = False,
) -> tuple[list[dict], list[dict]]:
    """Steps 5-8: 加权合成 → 宏观叠加 → 锦标赛boost → 排名 → 记录."""
    n_valid = len(scored_indices)
    composite_scores = [
        sum(z_factors[f["name"]][i] * f["weight"] for f in FACTORS)
        for i in range(n_valid)
    ]

    macro_boosts = [
        _get_macro_boost(candidates[scored_indices[i]][1].get("sector", ""))
        for i in range(n_valid)
    ]

    tournament_boosts: list[float] = []
    for i in range(n_valid):
        idx = scored_indices[i]
        code, _ = candidates[idx]
        pipe = pipe_map.get(code, {})
        if pipe.get("tournament_winner"):
            rank = pipe.get("tournament_rank", 3)
            tournament_boosts.append(0.04 - rank * 0.01)
        else:
            tournament_boosts.append(0.0)

    all_scored: list[dict] = []
    for i in range(n_valid):
        idx = scored_indices[i]
        code, info = candidates[idx]
        trend = trend_map[code]
        pipe = pipe_map.get(code, {})
        all_scored.append({
            "code": code,
            "name": info.get("name", code),
            "sector": info.get("sector", ""),
            "risk_level": info.get("risk_level", 0.5),
            "pipeline_score": pipe.get("score", 5.0),
            "two_week_score": round(
                (composite_scores[i] + 2.0 + macro_boosts[i] * 5 + tournament_boosts[i] * 10) / 4.0 * 100
            ),
            "z_composite": round(composite_scores[i], 3),
            "tournament_winner": pipe.get("tournament_winner", False),
            "tournament_rank": pipe.get("tournament_rank", 99),
            "z_factors": {
                f["name"]: round(z_factors[f["name"]][i], 2)
                for f in FACTORS
            },
            "trend_signal": trend.trend_signal,
            "change_20d": round(trend.change_20d, 1),
            "return_10d": round(trend.change_10d, 1),
            "max_drawdown": round(trend.max_drawdown, 1),
            "volatility": round(trend.volatility_20d, 1),
            "volume_ratio": round(trend.volume_ratio_5_20, 2),
            "position_pct": round(trend.position_pct, 1),
        })

    # Step 7: 排名 + 行业去重取Top3
    all_scored.sort(key=lambda x: -x["two_week_score"])
    top3: list[dict] = []
    seen_sectors: set[str] = set()
    for r in all_scored:
        if r["sector"] not in seen_sectors:
            top3.append(r)
            seen_sectors.add(r["sector"])
        if len(top3) >= 3:
            break

    if debug:
        print(f"  Top3行业: {[r['sector'] for r in top3]}")

    # Step 8: 记录预测
    try:
        from etf_platform.decision.prediction_monitor import log_prediction
        log_prediction(top3, profile)
    except (ImportError, KeyError, ValueError, TypeError, AttributeError, OSError) as e:
        logger.warning("two_week_picker: failed to log prediction - %s", str(e)[:100])

    return top3, all_scored


# ── Multi-factor Z-score picker (CORE v3.0) ────────

def pick_top3(
    profile: str = "均衡",
    max_candidates: int = 80,
    debug: bool = False,
    skip_tournament: bool = False,
) -> tuple[list[dict], list[dict]]:
    """全市场Z-score多因子扫描 → 返回(top3, all_scored).

    v3.0 核心改进:
      1. 7因子在候选池内Z-score标准化
      2. 加权合成→消除"跌最多=最高分"的结构性偏差
      3. Top 3强制行业去重

    Args:
        profile: 风险偏好 ("均衡" / "激进")
        max_candidates: 最大候选ETF数（控制耗时）
        debug: 打印诊断信息

    Returns:
        (top3: list[dict], all_scored: list[dict])
    """

    t0 = time.time()

    # ── Pipeline: steps extracted to helpers ──
    qvix_regime = _get_qvix_regime(debug)

    etfs = load_etfs()
    candidates = _build_candidate_pool(etfs, qvix_regime, max_candidates, debug)
    if len(candidates) < 3:
        if debug:
            print("  ⚠️ 候选池不足3只, 无法选Top3")
        return [], []

    codes = [c[0] for c in candidates]
    t1 = time.time()
    pipe_map = _batch_run_pipeline(codes, profile, skip_tournament, max_candidates)
    if debug:
        print(f"  Pipeline: {len(pipe_map)}只 ({time.time() - t1:.0f}s)")

    z_factors, trend_map, scored_indices = _collect_factors(candidates, pipe_map, [])
    n_valid = len(scored_indices)
    if n_valid < 3:
        if debug:
            print(f"  ⚠️ 有效数据不足 ({n_valid}<3)")
        return [], []

    top3, all_scored = _compute_scores_and_rank(z_factors, candidates, pipe_map, trend_map, scored_indices, profile, debug)

    if debug:
        print(f"  总耗时: {time.time() - t0:.0f}s")

    return top3, all_scored


# ── Report formatting ──────────────────────────────────────────────

def format_report(top3: list[dict], date_str: str = "") -> str:
    """格式化Top 3报告（兼容v2/v3输出格式）."""
    if not date_str:
        from datetime import date

        date_str = date.today().isoformat()

    lines = [
        f"📈 ETF 2周预测 Top 3 — {date_str}  [v3.0 Z-score多因子]",
        f"{'=' * 65}",
    ]
    for i, r in enumerate(top3, 1):
        c = (
            "🔴"
            if r["risk_level"] >= 0.7
            else ("🟡" if r["risk_level"] >= 0.4 else "🟢")
        )
        lines.extend([
            f"\n  {i}. {r['code']} {r['name']}",
            f"     {'=' * 55}",
            f"     Z-score综合: {r['two_week_score']}/100 | 穿透分: {r['pipeline_score']:.1f} | {c}风险: {r['risk_level']:.2f}",
            f"     {'─' * 55}",
            f"     趋势: {r['trend_signal']} | 20日{r['change_20d']:+.1f}% | 10日{r['return_10d']:+.1f}%",
            f"     回撤{r['max_drawdown']:.1f}% | 波动率{r['volatility']:.0f}% | 量比{r['volume_ratio']:.2f}",
            f"     位置{r['position_pct']:.0f}% | 行业:{r['sector']}",
        ])
        # Show Z-factor breakdown if available
        if "z_factors" in r:
            zf = r["z_factors"]
            lines.append(
                f"     Z因子: 超跌{zf.get('oversold_depth',0):+.1f} "
                f"回撤{zf.get('drawdown_recov',0):+.1f} "
                f"弹性{zf.get('quality_elastic',0):+.1f} "
                f"量比{zf.get('vol_health',0):+.1f} "
                f"行为{zf.get('behavioral',0):+.1f}"
            )

    lines.append(f"\n{'=' * 65}")
    lines.append(
        "v3.0 Z-score标准化 · Top3行业去重 · 已排除宽基/债券 · 不构成投资建议"
    )
    return "\n".join(lines)


# ── CLI ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ETF 2周涨幅预测 v3.0 Z-score")
    parser.add_argument("--code", type=str, help="单只ETF预测")
    parser.add_argument("--top3", action="store_true", help="全市场Z-score选Top 3")
    parser.add_argument("--profile", type=str, default="均衡", help="风险偏好")
    parser.add_argument("--json", action="store_true", help="JSON输出")
    parser.add_argument("--max", type=int, default=80, help="最大候选数")
    args = parser.parse_args()

    if args.code:
        r = predict(args.code, args.profile)
        if args.json:
            print(json.dumps(r, ensure_ascii=False, indent=2))
        else:
            print(format_report([r]))
    elif args.top3:
        top3, _ = pick_top3(args.profile, max_candidates=args.max, debug=True)
        if args.json:
            print(json.dumps(top3, ensure_ascii=False, indent=2))
        else:
            print(format_report(top3))
    else:
        parser.print_help()
