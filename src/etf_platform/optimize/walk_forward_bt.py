"""walk_forward_bt.py — two_week_picker 走前向(PIT)回测：新引擎 vs 旧引擎同周对比

动机：修复后引擎(≥2026-08-10)的真实命中率需数周正向样本才能验证。本模块用
**截至各历史预测日**可得的数据重跑当前引擎，与日志里旧引擎实际选出的 top3
在同一批日期上做 A/B，给出无需等待的定向证据。

PIT 复算原则（只信任可精确切片的数据源）：
  - QVIX regime: 用缓存序列截至 D 的最后一个值复刻 get_regime()
  - 趋势因子 (change_20d / volatility_20d / max_drawdown, 权重合计0.87):
    用 kline 截至 D 的切片复刻 get_trend() 数学
  - 候选池: _build_candidate_pool 是 etfs 配置 + regime 的纯函数，精确复现

已知近似（报告里如实标注，不掩盖）：
  - macro_overlay(±0.15) / sector_flow(0.10) / pipeline_score(0.03)：无 PIT
    数据源，取中性值。因此本回测验证的是"QVIX regime 动态权重 + 行业均衡
    候选池"这两个核心修复，不含宏观/资金流/穿透分叠加。
  - 新引擎的因子权重是在历史 IC 上调参的（in-sample），对历史期对比偏乐观，
    真实优劣以正向 cohort（prediction_monitor post_fix）为准。
  - 前向收益复用 prediction_monitor._return_since（K线锚点法），与生产一致；
    距今不足 10 个交易日的日期用已实现部分收益。
"""
import json
from datetime import date
from pathlib import Path

from etf_platform.config_loader import load_etfs
from etf_platform.utils import zscore
from etf_platform.data.kline import _fetch_kline, TrendSnapshot
from etf_platform.decision import two_week_picker as twp
from etf_platform.decision import prediction_monitor as pm

BASE = Path(__file__).resolve().parent.parent.parent.parent
LOG_FILE = BASE / "data" / "two_week_predictions.jsonl"
QVIX_CACHE = BASE / "data" / "live_cache" / "qvix_regime.json"

_REGIME_ORDER = {"complacent": 0, "normal": 1, "cautious": 2, "fearful": 3}


def _classify(qvix_val: float) -> str:
    if qvix_val < 16:
        return "complacent"
    if qvix_val < 22:
        return "normal"
    if qvix_val < 28:
        return "cautious"
    return "fearful"


def _regime_at(qvix_cache: dict, d: date) -> str:
    """截至 d 的 QVIX regime —— 复刻 qvix_regime.get_regime() 的切片版。

    金丝雀：当 d 为最新日期时，结果必须等于 get_regime()["regime"]。
    """
    import pandas as pd

    def _last_close(rows):
        if not rows:
            return None
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        df = df[df["date"] <= pd.Timestamp(d)]
        if df.empty:
            return None
        return float(df.sort_values("date")["close"].iloc[-1])

    q50 = _last_close(qvix_cache.get("50", []))
    q500 = _last_close(qvix_cache.get("500", []))
    if q50 is None and q500 is None:
        return "normal"
    r50 = _classify(q50) if q50 is not None else "normal"
    r500 = _classify(q500) if q500 is not None else "normal"
    return r500 if _REGIME_ORDER[r500] > _REGIME_ORDER[r50] else r50


def _trend_at(code: str, rows: list, d: date, window: int = 64) -> TrendSnapshot | None:
    """用截至 d 的 kline 切片复刻 get_trend() 的指标计算。

    生产引擎调 get_trend(code)（默认 days=63，但实测返回 64 根 → data_days=64），
    窗口=最近 64 根。回测需 fetch 更长（覆盖 D 之后到今天的 bar），切片后取最后
    window 根，使 D 当日的窗口与生产一致（max_drawdown 在全窗计算，深度敏感）。

    金丝雀：当 d 为最新日期且 rows 取自 days=80 fetch 时，指标必须逐字段等于
    get_trend(code, 63)。
    """
    sliced = [r for r in rows if r["date"] <= d.isoformat()]
    if window and len(sliced) > window:
        sliced = sliced[-window:]
    if len(sliced) < 2:
        return None
    close_list = [float(r["close"]) for r in sliced]
    vol_list = [float(r["volume"]) for r in sliced]
    total = len(close_list)
    latest = round(close_list[-1], 3)

    def chg(n):
        if total > n and close_list[-n - 1] > 0:
            return ((close_list[-1] / close_list[-n - 1]) - 1) * 100
        return 0.0

    c5 = chg(5) if total >= 6 else 0.0
    c10 = chg(10) if total >= 11 else 0.0
    c20 = chg(20) if total >= 21 else (chg(total - 1) if total > 1 else 0.0)
    c60 = chg(60) if total >= 61 else (chg(total - 1) if total > 1 else 0.0)

    recent = close_list[-60:] if total >= 60 else close_list
    h60 = max(recent)
    l60 = min(recent)
    pos = (latest - l60) / (h60 - l60) * 100 if h60 > l60 else 50.0

    peak = close_list[0]
    dd = 0.0
    for p in close_list:
        if p > peak:
            peak = p
        if peak > 0:
            dd = min(dd, (p - peak) / peak * 100)

    import statistics
    r_list = [(close_list[i] / close_list[i - 1] - 1) for i in range(1, total) if close_list[i - 1] > 0]
    r20 = r_list[-20:] if len(r_list) >= 20 else r_list
    vol_20d = statistics.stdev(r20) * (252 ** 0.5) * 100 if len(r20) > 1 else 0.0

    if len(vol_list) >= 5:
        v5 = sum(vol_list[-5:]) / 5
        v20 = sum(vol_list[-20:]) / 20 if len(vol_list) >= 20 else sum(vol_list) / len(vol_list)
        vr = v5 / v20 if v20 > 0 else 1.0
    else:
        vr = 1.0

    if pos < 15:
        signal = "oversold"
    elif pos < 35:
        signal = "weak"
    elif pos < 65:
        signal = "neutral"
    elif pos < 85:
        signal = "strong"
    else:
        signal = "overbought"
    if c5 < -5 and signal in ("weak", "oversold"):
        signal = "plunging"
    elif c5 > 5 and signal in ("strong", "overbought"):
        signal = "surging"

    return TrendSnapshot(
        code=code, price=latest,
        change_5d=round(c5, 2), change_10d=round(c10, 2),
        change_20d=round(c20, 2), change_60d=round(c60, 2),
        high_60d=round(h60, 3), low_60d=round(l60, 3),
        position_pct=round(pos, 1), max_drawdown=round(dd, 1),
        volatility_20d=round(vol_20d, 1), volume_ratio_5_20=round(vr, 2),
        trend_signal=signal, data_days=total,
    )


def _collect_factors_pit(candidates, trend_map):
    """PIT 版 _collect_factors：pipeline_score 取标称 5.0（近似，权重仅0.03）。"""
    raw_factors: dict[str, list[float]] = {f["name"]: [] for f in twp.FACTORS}
    scored_indices: list[int] = []
    for idx, (code, info) in enumerate(candidates):
        trend = trend_map.get(code)
        if trend is None or trend.data_days < 10:
            continue
        pipe = {"score": 5.0, "sector": info.get("sector", ""), "etf_code": code}
        scored_indices.append(idx)
        for f in twp.FACTORS:
            raw_factors[f["name"]].append(f["raw"](trend, pipe))
    z_factors = {}
    for f in twp.FACTORS:
        z_factors[f["name"]] = twp._clamp_z(zscore(raw_factors[f["name"]]))
    return z_factors, scored_indices


def _load_old_picks():
    """从预测日志提取 {date_str: [(code, name), ...]}（旧引擎实际选股）。"""
    picks = {}
    if not LOG_FILE.exists():
        return picks
    with open(LOG_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            codes = [(p["code"], p.get("name", p["code"])) for p in row.get("top3", [])]
            if codes:
                picks[row["date"]] = codes
    return picks


def run_walk_forward(profile: str = "均衡", max_candidates: int = 80,
                     min_days_old: int = 5) -> dict:
    """对日志中每个历史预测日重跑新引擎，与旧引擎选股同周 A/B。

    返回结构化报告（含逐日明细 + 聚合命中率 + 已知近似清单）。
    """
    old_picks = _load_old_picks()
    if not old_picks:
        return {"error": "no prediction history"}

    etfs = load_etfs()
    if QVIX_CACHE.exists():
        qvix_cache = json.loads(QVIX_CACHE.read_text(encoding="utf-8"))
    else:
        qvix_cache = {}

    # PIT 中性化：macro_overlay / sector_flow 无历史数据源，取中性 0
    _orig_macro, _orig_sector = twp._get_macro_boost, twp._get_sector_flow_raw
    twp._get_macro_boost = lambda sector: 0.0
    twp._get_sector_flow_raw = lambda sector, code="": 0.0
    _orig_log = pm.log_prediction
    pm.log_prediction = lambda *a, **k: None

    # code → 完整 kline（一次抓取，按日期切片），避免重复网络调用
    _kline_cache: dict[str, list] = {}

    def _kline(code):
        if code not in _kline_cache:
            _kline_cache[code] = _fetch_kline(code, days=80) or []
        return _kline_cache[code]

    days = []
    try:
        for date_str, old_codes in sorted(old_picks.items()):
            d = date.fromisoformat(date_str)
            days_since = (date.today() - d).days
            if days_since < min_days_old:
                continue  # 验证期内，与 evaluate_prediction 一致

            regime = _regime_at(qvix_cache, d)
            candidates = twp._build_candidate_pool(etfs, regime, max_candidates)
            trend_map = {}
            for code, _info in candidates:
                t = _trend_at(code, _kline(code), d)
                if t is not None:
                    trend_map[code] = t

            z_factors, scored_indices = _collect_factors_pit(candidates, trend_map)
            if len(scored_indices) < 3:
                continue
            pipe_map = {code: {"score": 5.0} for code, _ in candidates}
            new_top3, _all = twp._compute_scores_and_rank(
                z_factors, candidates, pipe_map, trend_map, scored_indices,
                profile, regime, False)
            new_codes = [(r["code"], r["name"]) for r in new_top3]

            row = {
                "date": date_str, "regime": regime,
                "pool_size": len(scored_indices),
                "old_picks": old_codes,
                "new_picks": new_codes,
                "old_returns": {c: pm._return_since(date_str, c, 10) for c, _ in old_codes},
                "new_returns": {c: pm._return_since(date_str, c, 10) for c, _ in new_codes},
            }
            days.append(row)
    finally:
        twp._get_macro_boost = _orig_macro
        twp._get_sector_flow_raw = _orig_sector
        pm.log_prediction = _orig_log

    def _agg(rows, key):
        vals = []
        hits = 0
        for r in rows:
            for c, ret in r[key].items():
                if ret is None:
                    continue
                vals.append(ret)
                hits += ret > 0
        return {"count": len(vals), "hits": hits,
                "hit_rate": round(hits / max(len(vals), 1) * 100, 1),
                "avg_return": round(sum(vals) / max(len(vals), 1), 2)} if vals else \
            {"count": 0, "hits": 0, "hit_rate": 0.0, "avg_return": 0.0}

    return {
        "dates": days,
        "old": _agg(days, "old_returns"),
        "new": _agg(days, "new_returns"),
        "caveats": [
            "macro_overlay/sector_flow/pipeline_score PIT 数据源不可得，取中性值——本回测隔离的是 QVIX regime 动态权重 + 行业均衡候选池两个核心修复",
            "新引擎权重为历史 IC in-sample 调参，历史期对比偏乐观；真实优劣以正向 cohort 为准",
            "前向收益用已实现部分（不足 10 交易日），与 evaluate_prediction 一致",
        ],
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="two_week_picker 走前向(PIT)回测")
    parser.add_argument("--max", type=int, default=80, help="候选池上限")
    parser.add_argument("--profile", type=str, default="均衡")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run_walk_forward(profile=args.profile, max_candidates=args.max)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    if "error" in report:
        print(report["error"])
        return
    o, n = report["old"], report["new"]
    print(f"走前向回测（{len(report['dates'])} 周，候选池≤{args.max}）")
    print(f"  旧引擎: 命中率 {o['hit_rate']}% ({o['hits']}/{o['count']}), 均10日收益 {o['avg_return']:+.2f}%")
    print(f"  新引擎: 命中率 {n['hit_rate']}% ({n['hits']}/{n['count']}), 均10日收益 {n['avg_return']:+.2f}%")
    print("\n逐周明细:")
    for d in report["dates"]:
        op = "/".join(c for c, _ in d["old_picks"])
        np = "/".join(c for c, _ in d["new_picks"])
        print(f"  {d['date']} [{d['regime']} 池{d['pool_size']}]")
        print(f"    旧: {op} → {_fmt_ret(d['old_returns'])}")
        print(f"    新: {np} → {_fmt_ret(d['new_returns'])}")
    print("\n已知近似:")
    for c in report["caveats"]:
        print(f"  - {c}")


def _fmt_ret(ret_map):
    parts = []
    for c, v in ret_map.items():
        parts.append(f"{c}:{'--' if v is None else f'{v:+.1f}%'}")
    return " ".join(parts)


if __name__ == "__main__":
    main()
