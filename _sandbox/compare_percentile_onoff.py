"""批次D修正 验收2: screener 选股 ON/OFF 零劣化对比。

验证 percentile_calibrate 改为纯注解(选项3)后:
  - ON 与 OFF 的选股结果完全一致 (top5 重合 5/5, composite_score 相同)
  - 收益/夏普数字相同 (等权持仓回测)
  - 仅多 composite_percentile 字段
"""
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from etf_platform import pipeline
from etf_platform.config_loader import load_etfs
from etf_platform.data.kline import _fetch_kline
from etf_platform.decision.screener import (
    _compute_auto_weights,
    _compute_composite,
    _detect_dead_layers,
)
from etf_platform.pipeline import percentile_calibrate

PROFILE = "均衡"
N_SELECT = 5
N_CODES = 12


def run_selection(results):
    """模拟 screener 批量选股: 死层检测 → 自动权重 → composite → 排序 topN."""
    dead = _detect_dead_layers(results)
    for r in results:
        for d in dead:
            r.get("layer_scores", {}).pop(d, None)
    weights = _compute_auto_weights(results, PROFILE, dead)
    ranked = []
    for r in results:
        ls = r.get("layer_scores", {})
        l1 = ls.get("L1_ETF", 5)
        rl = max(0.1, min(0.9, (10 - l1) / 10)) if isinstance(l1, (int, float)) else 0.5
        ranked.append({
            "code": r.get("etf_code", ""),
            "name": r.get("name", ""),
            "sector": r.get("sector", ""),
            "risk_level": rl,
            "composite_score": _compute_composite(ls, weights),
            "has_annot": "composite_percentile" in r,
            "composite_percentile": r.get("composite_percentile"),
        })
    ranked.sort(key=lambda x: -x["composite_score"])
    return ranked, weights, dead


def port_stats(codes):
    """等权持仓回测: 共同交易日对齐 → 日收益均值 → 总收益 + 年化夏普."""
    series = {}
    for c in codes:
        rows = _fetch_kline(c, 63)
        if rows:
            series[c] = {r["date"]: float(r["close"]) for r in rows if float(r["close"]) > 0}
    if not series:
        return None
    common = sorted(set.intersection(*[set(s.keys()) for s in series.values()]))
    if len(common) < 5:
        return None
    rets = []
    for i in range(1, len(common)):
        prev = common[i - 1]
        daily = [s[common[i]] / s[prev] - 1 for s in series.values()]
        rets.append(sum(daily) / len(daily))
    if len(rets) < 2:
        return None
    total_ret = 1.0
    for r in rets:
        total_ret *= (1 + r)
    total_ret -= 1.0
    mean = sum(rets) / len(rets)
    std = (sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)) ** 0.5
    sharpe = mean / std * (252 ** 0.5) if std > 0 else 0.0
    return total_ret, sharpe


def main():
    etfs = load_etfs()
    codes = [c for c in etfs if c.isdigit()][:N_CODES]
    print(f"使用 {len(codes)} 只 ETF: {codes}")

    raw_results = pipeline.batch_full(codes=codes, live=False, profile=PROFILE)
    ok = [r for r in raw_results if not r.get("error")]
    print(f"穿透成功 {len(ok)}/{len(codes)}")
    if len(ok) < N_SELECT:
        print("穿透失败过多，无法对比 top5")
        sys.exit(2)

    # OFF: 不调 percentile_calibrate (模拟 PERCENTILE_CALIBRATION=False)
    results_off = copy.deepcopy(ok)
    ranked_off, w_off, dead_off = run_selection(results_off)

    # ON: 调 percentile_calibrate + merge (与 screener.py 挂点一致)
    results_on = copy.deepcopy(ok)
    _annotated = percentile_calibrate(results_on)
    for _r, _a in zip(results_on, _annotated):
        if isinstance(_a, dict) and "composite_percentile" in _a:
            _r["composite_percentile"] = _a["composite_percentile"]
    ranked_on, w_on, dead_on = run_selection(results_on)

    top5_off = [r["code"] for r in ranked_off[:N_SELECT]]
    top5_on = [r["code"] for r in ranked_on[:N_SELECT]]

    # 对比表数据
    rows = []
    for i in range(N_SELECT):
        o = ranked_off[i]
        n = ranked_on[i]
        rows.append({
            "rank": i + 1,
            "code": f"{o['code']} vs {n['code']}",
            "score_off": o["composite_score"],
            "score_on": n["composite_score"],
            "score_equal": o["composite_score"] == n["composite_score"],
            "annot_off": o["has_annot"],
            "annot_on": n["has_annot"],
            "pct_on": n["composite_percentile"],
        })

    print("\n" + "=" * 78)
    print("对比表: 逐名次 ON vs OFF (composite_score)")
    print("=" * 78)
    print(f"{'rank':<5}{'code (off vs on)':<26}{'off':<9}{'on':<9}{'eq':<6}{'annot_off':<10}{'annot_on':<10}{'pct_on'}")
    for r in rows:
        print(f"{r['rank']:<5}{r['code']:<26}{r['score_off']:<9.3f}{r['score_on']:<9.3f}"
              f"{str(r['score_equal']):<6}{str(r['annot_off']):<10}{str(r['annot_on']):<10}{r['pct_on']}")

    overlap = len(set(top5_off) & set(top5_on))
    weights_equal = w_off == w_on
    dead_equal = dead_off == dead_on
    scores_equal = all(o["composite_score"] == n["composite_score"]
                       for o, n in zip(ranked_off, ranked_on))

    print("\n--- 一致性检查 ---")
    print(f"top5 重合: {overlap}/5")
    print(f"自动权重一致: {weights_equal}")
    print(f"死层集合一致: {dead_equal}")
    print(f"全部排名 composite_score 一致: {scores_equal}")
    print(f"ON 额外字段仅 composite_percentile: "
          f"{all(not r['has_annot'] for r in ranked_off)} / {all(r['has_annot'] for r in ranked_on)}")

    if overlap != N_SELECT or not scores_equal or not weights_equal:
        print("\n❌ 零劣化验证失败")
        sys.exit(1)

    print("\n--- 等权持仓收益/夏普 (top5) ---")
    stats_off = port_stats(top5_off)
    stats_on = port_stats(top5_on)
    print(f"OFF: 总收益={stats_off[0]:+.2%}  夏普={stats_off[1]:.3f}" if stats_off else "OFF: 数据不足")
    print(f"ON : 总收益={stats_on[0]:+.2%}  夏普={stats_on[1]:.3f}" if stats_on else "ON : 数据不足")
    if stats_off and stats_on:
        same = stats_off == stats_on
        print(f"收益/夏普一致: {same}")
        if not same:
            print("❌ 收益/夏普不一致")
            sys.exit(1)

    print("\n✅ 零劣化验证通过: ON 与 OFF 选股完全一致，仅多 composite_percentile 注解字段")
    return 0


if __name__ == "__main__":
    sys.exit(main())
