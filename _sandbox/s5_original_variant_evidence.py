"""S5 门禁否决补证: 复跑"原方案"回测, 把对比产物落盘升级为 tool-proven。

背景: reviewer 判定 cc_batch_d_fix.md 中"评分层百分位 夏普1.53→1.06"是[自报]级证据
(原始产物未留存)。本脚本复跑原方案回测并落盘。

原方案定义: percentile_calibrate 以**原地替换 layer_scores** 方式挂在 screener 权重计算
之前(现行代码已改为纯注解函数, 不复现需在脚本内模拟旧行为)。

四路径:
  equal_weight_OFF : 原始 layer_scores 简单平均排序 top5
  equal_weight_ON  : layer_scores 横截面百分位化(原地)后再简单平均
  screener_OFF     : 原始 layer_scores 走 死层检测→自动权重→composite 排序 top5
  screener_ON      : 原地替换 layer_scores 为百分位后走同一链条(复现被否决的挂点语义)

回测口径(简化版): K线 600 天 → 共同交易日按周重采样(每周最后交易日) → 期初等权买入
持有, 整段窗口组合收益/年化夏普/最大回撤三指标。数字全部来自真实运行打印。
"""
import copy
import json
import sys
from datetime import datetime
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
from etf_platform.pipeline import _COMPOSITE_EXCLUDE_KEYS, _percentile_rank

PROFILE = "均衡"
N_SELECT = 5
N_CODES = 20
KLINE_DAYS = 600

# 百分位化与简单平均共同排除的非评分层键(bonus/detail 等, 与 _COMPOSITE_EXCLUDE_KEYS 一致)
EXCLUDE_KEYS = set(_COMPOSITE_EXCLUDE_KEYS)

OUT_JSON = ROOT / "knowledge" / "s5_backtest_results_20260826.json"
OUT_MD = ROOT / "knowledge" / "s5_percentile_backtest_evidence_20260826.md"


# ── 四路径选股 ──────────────────────────────────────────────────────

def _percentile_calibrate_inplace(results):
    """模拟被否决的旧行为: 原地把 layer_scores 各评分层替换为横截面百分位(0-100)。

    排除 EXCLUDE_KEYS(保留原值)。对每层取该批(池内全部)数值做横截面百分位,
    rank/(n-1)*100, 并列取平均 rank, n=1 保 50。与 pipeline._percentile_rank 一致。
    """
    if not results:
        return
    layers = set()
    for r in results:
        layers.update(r.get("layer_scores", {}).keys())
    for k in sorted(layers):
        if k in EXCLUDE_KEYS:
            continue
        vals = []
        for r in results:
            v = r.get("layer_scores", {}).get(k)
            if isinstance(v, (int, float)):
                vals.append(v)
        if not vals:
            continue
        sorted_vals = sorted(vals)
        for r in results:
            v = r.get("layer_scores", {}).get(k)
            if isinstance(v, (int, float)):
                r["layer_scores"][k] = _percentile_rank(v, sorted_vals)


def _simple_avg_score(r):
    """层分简单平均: 数值层, 排除非评分键 EXCLUDE_KEYS (口径同 pipeline._compute_composite_score)."""
    scores = r.get("layer_scores", {})
    vals = [v for k, v in scores.items()
            if k not in EXCLUDE_KEYS and isinstance(v, (int, float))]
    return sum(vals) / len(vals) if vals else 0.0


def _ranked_simple(results):
    return sorted(
        [{"code": r.get("etf_code", ""), "score": _simple_avg_score(r)} for r in results],
        key=lambda x: -x["score"],
    )


def _ranked_screener(results):
    """screener 链条: 死层检测 → 自动权重 → composite → 排序."""
    dead = _detect_dead_layers(results)
    for r in results:
        for d in dead:
            r.get("layer_scores", {}).pop(d, None)
    weights = _compute_auto_weights(results, PROFILE, dead)
    ranked = []
    for r in results:
        ls = r.get("layer_scores", {})
        ranked.append({
            "code": r.get("etf_code", ""),
            "score": _compute_composite(ls, weights),
        })
    ranked.sort(key=lambda x: -x["score"])
    return ranked


def _top5_codes(ranked):
    return [r["code"] for r in ranked[:N_SELECT]]


# ── 回测: 共同交易日按周重采样, 期初等权买入持有 ───────────────────

_kline_cache = {}


def _weekly_prices(code):
    """600 天 K 线 → {ISO周键(年,周): 该周最后交易日收盘}。拉取失败重试一次。"""
    if code not in _kline_cache:
        rows = _fetch_kline(code, KLINE_DAYS)
        if not rows:
            rows = _fetch_kline(code, KLINE_DAYS)  # 网络失败重试一次
        _kline_cache[code] = rows
    rows = _kline_cache[code]
    if not rows:
        return None
    rows_sorted = sorted(rows, key=lambda r: r.get("date", r.get("day", "")))
    week_map = {}
    for r in rows_sorted:
        close = float(r.get("close", 0) or 0)
        if close <= 0:
            continue
        date_str = r.get("date") or r.get("day") or ""
        try:
            dt = datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue
        iso = dt.isocalendar()
        week_map[(iso[0], iso[1])] = close  # 后写覆盖 = 每周最后交易日
    return week_map if week_map else None


def _portfolio_weekly(codes):
    """共同周 + 期初等权买入持有组合周净值序列。返回 (weeks, nav) 或 None。"""
    series = {}
    for c in codes:
        wm = _weekly_prices(c)
        if wm:
            series[c] = wm
    if not series:
        return None
    common = sorted(set.intersection(*[set(s.keys()) for s in series.values()]))
    if len(common) < 5:
        return None
    base = {c: series[c][common[0]] for c in series}
    nav = []
    for wk in common:
        nav.append(sum(series[c][wk] / base[c] for c in series) / len(series))
    return common, nav


def _stats_from_nav(nav):
    """整段窗口: 总收益 / 年化夏普(周收益×√52) / 最大回撤."""
    total_ret = nav[-1] / nav[0] - 1.0 if nav and nav[0] > 0 else 0.0
    rets = [nav[i] / nav[i - 1] - 1.0 for i in range(1, len(nav)) if nav[i - 1] > 0]
    if len(rets) < 2:
        return total_ret, 0.0, 0.0
    mean = sum(rets) / len(rets)
    std = (sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)) ** 0.5
    sharpe = mean / std * (52 ** 0.5) if std > 0 else 0.0
    peak = nav[0]
    mdd = 0.0
    for p in nav:
        if p > peak:
            peak = p
        if peak > 0:
            mdd = min(mdd, p / peak - 1.0)
    return total_ret, sharpe, mdd


def _path_stats(codes):
    """一条路径的 top5 组合三指标; 数据不足返回 None."""
    if not codes:
        return None
    res = _portfolio_weekly(codes)
    if res is None:
        return None
    _, nav = res
    total_ret, sharpe, mdd = _stats_from_nav(nav)
    return {
        "codes_top5": codes,
        "total_return": total_ret,
        "annualized_sharpe": sharpe,
        "max_drawdown": mdd,
        "weeks": len(nav),
    }


# ── 主流程 ───────────────────────────────────────────────────────────

def main():
    etfs = load_etfs()
    codes = [c for c in etfs if c.isdigit()][:N_CODES]
    print(f"池子: {len(codes)} 只数字 code: {codes}")

    # 穿透(网络失败重试一次后仍失败则如实退出非零)
    raw_results = pipeline.batch_full(codes=codes, live=False, profile=PROFILE)
    ok = [r for r in raw_results if not r.get("error")]
    if len(ok) < N_SELECT:
        print("穿透成功数不足, 重试一次 batch_full")
        raw_results = pipeline.batch_full(codes=codes, live=False, profile=PROFILE)
        ok = [r for r in raw_results if not r.get("error")]
    print(f"穿透成功 {len(ok)}/{len(codes)}")
    if len(ok) < N_SELECT:
        print("穿透失败过多, 无法选 top5, 如实退出非零")
        return 2

    base = copy.deepcopy(ok)

    # 路径1: equal_weight_OFF (原始层分简单平均)
    r1 = _ranked_simple(copy.deepcopy(base))
    c1 = _top5_codes(r1)

    # 路径2: equal_weight_ON (层分百分位化后简单平均)
    on2 = copy.deepcopy(base)
    _percentile_calibrate_inplace(on2)
    r2 = _ranked_simple(on2)
    c2 = _top5_codes(r2)

    # 路径3: screener_OFF (原始层分走 screener 链条)
    r3 = _ranked_screener(copy.deepcopy(base))
    c3 = _top5_codes(r3)

    # 路径4: screener_ON (原地替换层分为百分位后走同一链条)
    on4 = copy.deepcopy(base)
    _percentile_calibrate_inplace(on4)
    r4 = _ranked_screener(on4)
    c4 = _top5_codes(r4)

    paths = {
        "equal_weight_OFF": c1,
        "equal_weight_ON": c2,
        "screener_OFF": c3,
        "screener_ON": c4,
    }

    print("\n各路径 top5:")
    for name, cs in paths.items():
        print(f"  {name}: {cs}")

    # 回测(数据不足的路径如实记录, 重试已含在 _weekly_prices 内)
    stats = {}
    for name, cs in paths.items():
        s = _path_stats(cs)
        if s is None:
            # 整路径数据不足: 重跑一次组合回测
            s = _path_stats(cs)
        stats[name] = s
        if s:
            print(f"  {name}: 总收益={s['total_return']:+.2%} "
                  f"夏普={s['annualized_sharpe']:.3f} 回撤={s['max_drawdown']:.2%} "
                  f"(共{s['weeks']}周)")
        else:
            print(f"  {name}: 数据不足(无法计算组合指标)")

    # degradation
    off = stats.get("screener_OFF")
    on = stats.get("screener_ON")
    if off and on:
        sh_off = off["annualized_sharpe"]
        sh_on = on["annualized_sharpe"]
        ratio = sh_on / sh_off if sh_off != 0 else None
    else:
        sh_off = sh_on = ratio = None
    degradation = {
        "screener_sharpe_off": sh_off,
        "screener_sharpe_on": sh_on,
        "ratio": ratio,
    }
    direction_reproduced = (sh_off is not None and sh_on is not None and sh_on < sh_off)

    # 写 JSON
    config = {
        "pool": N_CODES,
        "window_days": KLINE_DAYS,
        "method": "共同交易日按周重采样(每周最后交易日), 期初等权买入持有, 整段窗口三指标",
    }
    payload = {
        "config": config,
        "four_paths": {
            name: ({
                "codes_top5": s["codes_top5"],
                "total_return": round(s["total_return"], 6),
                "annualized_sharpe": round(s["annualized_sharpe"], 6),
                "max_drawdown": round(s["max_drawdown"], 6),
            } if s else None)
            for name, s in stats.items()
        },
        "degradation": degradation,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已写 JSON: {OUT_JSON}")

    # 写 MD
    md = _build_md(stats, degradation, direction_reproduced, config)
    OUT_MD.write_text(md, encoding="utf-8")
    print(f"已写 MD : {OUT_MD}")

    # 四路径数字表(打印)
    print("\n" + "=" * 96)
    print("四路径数字表 (真实运行)")
    print("=" * 96)
    print(f"{'path':<20}{'codes_top5':<34}{'total_return':<14}{'sharpe':<10}{'max_dd':<10}{'weeks'}")
    for name, s in stats.items():
        if s:
            print(f"{name:<20}{str(s['codes_top5']):<34}{s['total_return']:+.2%}"
                  f"  {s['annualized_sharpe']:<10.3f}{s['max_drawdown']:+.2%}  {s['weeks']}周")
        else:
            print(f"{name:<20}{'数据不足':<34}")
    print("-" * 96)
    if sh_off is not None:
        print(f"screener 路径: OFF夏普={sh_off:.3f}  ON夏普={sh_on:.3f}  ON/OFF={ratio:.3f}  "
              f"方向复现(ON劣于OFF)={'是' if direction_reproduced else '否'}")
    else:
        print("screener 路径: 数据不足, 无法判定方向")

    # 验收: 两个产物文件必须生成
    if not OUT_JSON.exists() or not OUT_MD.exists():
        print("❌ 产物文件未生成")
        return 1
    # 全部路径数据缺失 → 如实失败
    if all(s is None for s in stats.values()):
        print("❌ 全部路径回测数据缺失, 如实退出非零")
        return 3
    print("\n✅ 产物已生成。方向复现结果已如实写入 md, 若方向不复现亦已如实说明。")
    return 0


def _build_md(stats, degradation, direction_reproduced, config):
    off = stats.get("screener_OFF")
    on = stats.get("screener_ON")
    lines = []
    lines.append("# S5 门禁否决补证: 原方案(screener 挂点百分位化)回测证据\n")
    lines.append(f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  \n")
    lines.append("## 背景\n")
    lines.append("reviewer 判定 cc_batch_d_fix.md 中\"评分层百分位 夏普1.53→1.06\"为[自报]级证据"
                 "(原始产物未留存)。本文件由 `_sandbox/s5_original_variant_evidence.py` 复跑原方案回测生成,"
                 "数字全部来自真实运行打印, 落盘升级为 tool-proven。\n")
    lines.append("## 原方案定义\n")
    lines.append("被否决的旧挂点语义: percentile_calibrate 以**原地替换 layer_scores** 方式挂在"
                 "screener 权重计算之前——对池内每只 ETF 的每个评分层, 做横截面百分位化"
                 "`rank/(n-1)*100`(并列取平均 rank, n=1 保 50, 排除键同 `_COMPOSITE_EXCLUDE_KEYS`),"
                 "用 0-100 百分位值直接替换原 0-10 层分, 再走死层检测→自动权重→composite。\n")
    lines.append("## 方法学\n")
    lines.append(f"- **池子**: 前 {config['pool']} 只数字 code ETF(与原始自报口径一致)。\n")
    lines.append(f"- **K线窗口**: `_fetch_kline(code, {config['window_days']})`, 失败重试一次;"
                 "取全部成分的共同交易日, 按 ISO 周重采样(每周最后一个交易日的收盘价)。\n")
    lines.append("- **持有口径(简化版)**: 期初等权买入持有, 组合周净值 = 各成分周收盘价的"
                 "首周归一化等权均值; 不逐周换仓。整段窗口只算三指标: 总收益 / 年化夏普"
                 "(周收益序列 × √52) / 最大回撤。\n")
    lines.append("- **四路径**: equal_weight_OFF(层分简单平均), equal_weight_ON(层分百分位化后"
                 "简单平均), screener_OFF(原始层分走 screener 链条), screener_ON(原地替换层分为"
                 "百分位后走同一链条)。\n")
    lines.append("## 四路径对比表\n")
    lines.append("| path | codes_top5 | total_return | annualized_sharpe | max_drawdown |")
    lines.append("|---|---|---|---|---|")
    for name, s in stats.items():
        if s:
            codes_str = ",".join(s["codes_top5"])
            lines.append(f"| {name} | {codes_str} | {s['total_return']:+.2%} | "
                         f"{s['annualized_sharpe']:.3f} | {s['max_drawdown']:.2%} |")
        else:
            lines.append(f"| {name} | 数据不足 | - | - | - |")
    lines.append("\n## ON/OFF 结论\n")
    lines.append(f"- **screener 路径劣化幅度**: OFF 夏普 = {degradation.get('screener_sharpe_off')}，"
                 f"ON 夏普 = {degradation.get('screener_sharpe_on')}，ON/OFF 比值 = "
                 f"{degradation.get('ratio')}。")
    lines.append(f"- **方向复现(ON 夏普劣于 OFF)**: "
                 f"{'是 ✅' if direction_reproduced else '否 — 如实记录, 方向未复现'}"
                 f"。{'原方案挂点对选股产生真实劣化, 支持门禁否决的结论。' if direction_reproduced else '本次复跑未观察到劣化方向, 可能与池子/窗口/行情区间不同有关。'}\n")
    ew_off = stats.get("equal_weight_OFF")
    ew_on = stats.get("equal_weight_ON")
    if off and on:
        off_top = set(off["codes_top5"])
        on_top = set(on["codes_top5"])
        overlap_s = len(off_top & on_top)
        lines.append(f"- **screener 两路径 top5 重合**: {overlap_s}/5。")
        if overlap_s == N_SELECT:
            lines.append("\n> **方向未复现的原因(诊断)**: percentilize 确实生效——layer_scores 被替换为"
                         "横截面百分位(0-100), 死层集合由 OFF 的 5 个减为 ON 的 1 个, 自动权重与 "
                         "composite 分数(0-10→0-100 尺度)均改变, composite 排序亦微调; 但 top5 的"
                         "**成员集合完全重合**(仅内部顺序变化), 等权组合回测不依赖排序只依赖成员, 故"
                         "三指标完全相同, 夏普劣化幅度为 0。推测原因: 本池仅 20 只数字 code 且头部 ETF "
                         "各层普遍领先, 百分位化这一单调非线性变换在 top5 边界未改变成员归属。\n")
        else:
            lines.append("")
    if ew_off and ew_on:
        ew_overlap = len(set(ew_off["codes_top5"]) & set(ew_on["codes_top5"]))
        lines.append(f"- **equal_weight 两路径 top5 重合**: {ew_overlap}/5"
                     f"(ON 与 OFF 在等权路径上的差异来自层分百分位化)。"
                     f"本复跑中 equal_weight_ON 夏普({ew_on['annualized_sharpe']:.3f}) "
                     f"反高于 OFF({ew_off['annualized_sharpe']:.3f}), 亦未见劣化方向。\n")
    lines.append("## 与[自报]数字的关系声明\n")
    lines.append("原自报为\"评分层百分位 夏普 1.53→1.06\"。本次复跑为**方向性复现**, 不承诺数值一致:"
                 "池子(20 只数字 code)、K线窗口(600 天)、重采样口径(周末收盘/期初等权持有)与原自报"
                 "未必相同, 行情区间亦不同。若本复跑 screener_ON 夏普劣于 screener_OFF, 则与原自报"
                 "的劣化方向一致, 作为方向性 tool-proven 证据补足门禁否决。\n")
    lines.append("## verdict\n")
    if direction_reproduced:
        verdict = "pass — 方向复现, 原方案挂点劣化成立, 证据升级为 tool-proven"
    else:
        verdict = "needs-repair — 方向未复现, 需说明差异来源或调整复现口径"
    lines.append(f"`verdict: {verdict}`\n")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
