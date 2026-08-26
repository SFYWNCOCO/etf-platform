"""CC T8 / P1-C: 负相关层配置化降权回测门禁 (tool-proven)。

两路径对比 pipeline composite 等权 vs 加权(yaml) 的 top5 等权组合:
  baseline  : weights=None (纯等权)
  treatment : 加载 config/weights.yaml 的 composite_layer_weights 加权
池: 前 50 只数字 code, batch_full(live=False) 穿透。K线 datalen=800 取共同
交易日按周重采样(每周最后交易日), 期初等权买入持有。窗口 <81 周 → 如实报错退出。
门禁: treatment 夏普 ≥ baseline×0.9 且 最大回撤不深于 baseline×1.1 → PASS;
FAIL → 把 config/weights.yaml 的 enabled 改回 false, 机制保留(行为关闭)。
"""
import copy
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from etf_platform import pipeline
from etf_platform.config_loader import load_etfs
from etf_platform.data.kline import _fetch_kline
from etf_platform.pipeline import _compute_composite_score
from etf_platform.utils.layer_weights import load_composite_layer_weights

PROFILE = "均衡"
N_SELECT = 5
N_CODES = 50
SCREEN_POOL = 80   # 候选池: 数字 code 前80只(先筛查上市时长再取前50)
SCREEN_DAYS = 500  # 筛查 K 线窗口
MIN_KLINE = 405    # 达标 K 线根数 ≈81周×5交易日
KLINE_DAYS = 800
MIN_WEEKS = 81
SHARPE_FLOOR = 0.9   # treatment 夏普 ≥ baseline × 0.9
MDD_FLOOR = 1.1      # treatment 回撤不深于 baseline × 1.1 (mdd 为负值)

WEIGHTS_YAML = ROOT / "config" / "weights.yaml"
OUT_JSON = ROOT / "knowledge" / "p1_negcorr_backtest_gate_20260826.json"
OUT_MD = ROOT / "knowledge" / "p1_negcorr_backtest_gate_20260826.md"

_kline_cache = {}


def _fetch_cached(code, days):
    """带缓存的 _fetch_kline; 缓存 key 含 days, 避免筛查(500)污染回测(800)。失败重试一次。"""
    key = (code, days)
    if key not in _kline_cache:
        rows = _fetch_kline(code, days)
        if not rows:
            rows = _fetch_kline(code, days)
        _kline_cache[key] = rows
    return _kline_cache[key]


def _weekly_prices(code):
    """800 天 K 线 → {ISO周键(年,周): 该周最后交易日收盘}。拉取失败重试一次。"""
    rows = _fetch_cached(code, KLINE_DAYS)
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
    """共同周 + 期初等权买入持有组合周净值序列。返回 (common, nav) 或 None(无共同周)。"""
    series = {}
    for c in codes:
        wm = _weekly_prices(c)
        if wm:
            series[c] = wm
    if not series:
        return None
    common = sorted(set.intersection(*[set(s.keys()) for s in series.values()]))
    if not common:
        return None
    base = {c: series[c][common[0]] for c in series}
    nav = []
    for wk in common:
        nav.append(sum(series[c][wk] / base[c] for c in series) / len(series))
    return common, nav


def _per_code_weeks(codes):
    """每只 code 的周数明细(诊断用)。"""
    out = {}
    for c in codes:
        wm = _weekly_prices(c)
        out[c] = len(wm) if wm else 0
    return out


def _stats_from_nav(nav):
    """整段窗口: 总收益 / 年化夏普(周收益×√52) / 最大回撤。"""
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


def _rank(results, weights):
    """pipeline composite 排序: weights=None=等权, dict=加权 Σ(w·s)/Σw。"""
    scored = []
    for r in results:
        ls = r.get("layer_scores", {})
        scored.append({
            "code": r.get("etf_code", ""),
            "score": _compute_composite_score(ls, weights),
        })
    scored.sort(key=lambda x: -x["score"])
    return scored


def _top5(ranked):
    return [r["code"] for r in ranked[:N_SELECT]]


def _path_stats(codes):
    """一条路径的 top5 组合三指标; 数据不足(共同周<81)返回 None。"""
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


def _set_enabled(value: bool) -> bool:
    """把 weights.yaml 的 composite_layer_weights.enabled 设为 value, 保留注释与其余内容。"""
    if not WEIGHTS_YAML.exists():
        print("⚠️ weights.yaml 不存在, 无法修改 enabled")
        return False
    text = WEIGHTS_YAML.read_text(encoding="utf-8")
    repl = r"\1 " + ("true" if value else "false")
    new, n = re.subn(r"(composite_layer_weights:\n\s+enabled:) (true|false)", repl, text, count=1)
    if n:
        WEIGHTS_YAML.write_text(new, encoding="utf-8")
        return True
    print("⚠️ weights.yaml 中未找到 enabled 字段, 修改未执行")
    return False


def _rollback_enabled():
    """FAIL 回滚: enabled 改回 false。"""
    return _set_enabled(False)


def main():
    etfs = load_etfs()
    pool_all = [c for c in etfs if c.isdigit()][:SCREEN_POOL]
    qualified, dropped = [], []
    for c in pool_all:
        rows = _fetch_cached(c, SCREEN_DAYS)
        if rows and len(rows) >= MIN_KLINE:
            qualified.append(c)
        else:
            dropped.append(c)
    print(f"池子筛查(v2): 候选{len(pool_all)}只 → 达标{len(qualified)}只, "
          f"剔除{len(dropped)}只(K线<{MIN_KLINE}根): {','.join(dropped) if dropped else '无'}")
    if len(qualified) < N_SELECT:
        print("达标池不足, 无法选 top5, 如实退出非零")
        return 2
    codes = qualified[:N_CODES]
    print(f"进入 batch_full: 前{len(codes)}只: {codes[:10]}...")

    raw = pipeline.batch_full(codes=codes, live=False, profile=PROFILE)
    ok = [r for r in raw if not r.get("error")]
    if len(ok) < N_SELECT:
        print("穿透成功数不足, 重试一次 batch_full")
        raw = pipeline.batch_full(codes=codes, live=False, profile=PROFILE)
        ok = [r for r in raw if not r.get("error")]
    print(f"穿透成功 {len(ok)}/{len(codes)}")
    if len(ok) < N_SELECT:
        print("穿透失败过多, 无法选 top5, 如实退出非零")
        return 2

    loaded = load_composite_layer_weights()
    if not loaded:
        print("⚠️ composite_layer_weights 未启用或加载失败(loaded=None), 无法评估 treatment, 如实退出非零")
        return 3

    base = copy.deepcopy(ok)
    r_b = _rank(base, None)
    r_t = _rank(base, loaded)
    c_b = _top5(r_b)
    c_t = _top5(r_t)
    print(f"baseline  top5: {c_b}")
    print(f"treatment top5: {c_t}")

    res_b = _portfolio_weekly(c_b)
    res_t = res_b if c_b == c_t else _portfolio_weekly(c_t)
    if res_b is None or res_t is None:
        print("❌ 无共同交易日周, 无法回测, 如实报错退出非零")
        return _write_window_insufficient(c_b, c_t, 0, loaded)
    common_weeks = len(res_b[0])
    if common_weeks < MIN_WEEKS:
        print(f"❌ 回测窗口不足: 共同周={common_weeks} < {MIN_WEEKS}, 如实报错退出非零")
        return _write_window_insufficient(c_b, c_t, common_weeks, loaded)

    if c_b == c_t:
        print("两路径 top5 完全重合 → 三指标相同 → 权重幅度在排序边界无影响")
        return _write_no_difference(c_b, loaded)

    s_b = _path_stats(c_b)
    s_t = _path_stats(c_t)
    for name, s in (("baseline", s_b), ("treatment", s_t)):
        print(f"  {name}: 总收益={s['total_return']:+.2%} 夏普={s['annualized_sharpe']:.3f} "
              f"回撤={s['max_drawdown']:.2%} (共{s['weeks']}周)")

    sh_b, sh_t = s_b["annualized_sharpe"], s_t["annualized_sharpe"]
    mdd_b, mdd_t = s_b["max_drawdown"], s_t["max_drawdown"]
    pass_sharpe = sh_t >= sh_b * SHARPE_FLOOR
    pass_mdd = mdd_t >= mdd_b * MDD_FLOOR
    gate_pass = pass_sharpe and pass_mdd
    print(f"\n门禁-夏普: treatment={sh_t:.3f} >= baseline×0.9={sh_b * SHARPE_FLOOR:.3f} → "
          f"{'PASS' if pass_sharpe else 'FAIL'}")
    print(f"门禁-回撤: treatment={mdd_t:.2%} >= baseline×1.1={mdd_b * MDD_FLOOR:.2%} → "
          f"{'PASS' if pass_mdd else 'FAIL'}")
    print(f"结论: {'PASS ✅ 机制保留' if gate_pass else 'FAIL ❌ 触发回滚'}")

    rolled_back = False
    if not gate_pass:
        rolled_back = _rollback_enabled()
        print(f"⚠️ 门禁 FAIL, 已把 weights.yaml enabled 改回 false: {rolled_back}")

    payload = {
        "config": _config_snap(loaded),
        "judged": True,
        "verdict": "pass" if gate_pass else "fail",
        "baseline": {
            "codes_top5": s_b["codes_top5"],
            "total_return": round(s_b["total_return"], 6),
            "annualized_sharpe": round(s_b["annualized_sharpe"], 6),
            "max_drawdown": round(s_b["max_drawdown"], 6),
            "weeks": s_b["weeks"],
        },
        "treatment": {
            "codes_top5": s_t["codes_top5"],
            "total_return": round(s_t["total_return"], 6),
            "annualized_sharpe": round(s_t["annualized_sharpe"], 6),
            "max_drawdown": round(s_t["max_drawdown"], 6),
            "weeks": s_t["weeks"],
        },
        "gate": {
            "sharpe_pass": pass_sharpe,
            "mdd_pass": pass_mdd,
            "gate_pass": gate_pass,
            "rolled_back": rolled_back,
        },
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写 JSON: {OUT_JSON}")

    md = _build_md(s_b, s_t, gate_pass, pass_sharpe, pass_mdd, rolled_back, _config_snap(loaded), c_b, c_t)
    OUT_MD.write_text(md, encoding="utf-8")
    print(f"已写 MD : {OUT_MD}")

    if not OUT_JSON.exists() or not OUT_MD.exists():
        print("❌ 产物文件未生成")
        return 1
    print("\n✅ 回测门禁脚本完成。")
    return 0 if gate_pass else 1


def _config_snap(loaded):
    return {
        "pool": N_CODES,
        "screen_pool": SCREEN_POOL,
        "screen_days": SCREEN_DAYS,
        "min_kline": MIN_KLINE,
        "kline_days": KLINE_DAYS,
        "min_weeks": MIN_WEEKS,
        "sharpe_floor": SHARPE_FLOOR,
        "mdd_floor": MDD_FLOOR,
        "weights_loaded": loaded,
        "weights_yaml_enabled_at_run": True,
    }


def _write_window_insufficient(c_b, c_t, common_weeks, loaded):
    """窗口不足: 落盘说明产物(证据留存)后如实退出非零, 不伪造门禁数字。"""
    per = {}
    for c in sorted(set(c_b) | set(c_t)):
        wm = _weekly_prices(c)
        per[c] = len(wm) if wm else 0
    payload = {
        "config": _config_snap(loaded),
        "judged": False,
        "reason": "window_insufficient",
        "common_weeks": common_weeks,
        "min_weeks": MIN_WEEKS,
        "baseline_top5": c_b,
        "treatment_top5": c_t,
        "per_code_weeks": per,
        "gate": {"gate_pass": None, "rolled_back": False},
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md = (
        "# CC T8 / P1-C: 负相关层配置化降权回测门禁证据(窗口不足)\n\n"
        f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  \n\n"
        "## 判定\n"
        f"- **未判定**: 组合共同交易周 = {common_weeks} < 门槛 {MIN_WEEKS} 周, 按规格如实报错退出非零。\n"
        "- **未触发回滚**: 门禁未判定, config/weights.yaml 的 enabled 保持原样。\n"
        "- **根因**: top5 组合含上市时间短(不足 81 周)的 ETF, 把共同窗口拉低。\n"
        "## 两路径 top5\n"
        f"- baseline : {','.join(c_b)}\n"
        f"- treatment: {','.join(c_t)}\n"
        "## 成分周数明细\n"
        "| code | weeks |\n|---|---|\n"
        + "".join(f"| {c} | {per[c]} |\n" for c in sorted(per))
        + "\n## 结论\n"
        "`verdict: needs-repair — 窗口不足, 门禁未产出 PASS/FAIL 数字, 机制未启用判定`\n"
    )
    OUT_MD.write_text(md, encoding="utf-8")
    print(f"已写 JSON: {OUT_JSON}")
    print(f"已写 MD : {OUT_MD}")
    return 4


def _write_no_difference(codes, loaded):
    """两路径 top5 完全重合 → 三指标必然相同 → 权重幅度在排序边界无影响。
    verdict=no-difference(非PASS): 保守关闭 enabled(机制保留、行为关闭), 待有效幅度证据再启用。"""
    per = _per_code_weeks(codes)
    res = _portfolio_weekly(codes)
    common_weeks = len(res[0]) if res else 0
    s = _path_stats(codes) if res else None
    disabled = _set_enabled(False)
    payload = {
        "config": _config_snap(loaded),
        "judged": True,
        "verdict": "no-difference",
        "reason": "top5_identical",
        "common_weeks": common_weeks,
        "min_weeks": MIN_WEEKS,
        "baseline_top5": codes,
        "treatment_top5": codes,
        "per_code_weeks": per,
        "baseline": s,
        "treatment": s,
        "gate": {"gate_pass": None, "no_difference": True, "enabled_disabled": disabled},
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md = _build_md_no_diff(codes, per, common_weeks, s, disabled, _config_snap(loaded))
    OUT_MD.write_text(md, encoding="utf-8")
    print(f"已写 JSON: {OUT_JSON}")
    print(f"已写 MD : {OUT_MD}")
    print(f"⚠️ verdict=no-difference(非PASS), enabled 已改为 false: {disabled}")
    if not OUT_JSON.exists() or not OUT_MD.exists():
        print("❌ 产物文件未生成")
        return 1
    print("\n✅ 回测门禁脚本完成(no-difference)。")
    return 0


def _build_md_no_diff(codes, per, common_weeks, s, disabled, config):
    lines = []
    lines.append("# CC T8 / P1-C: 负相关层配置化降权回测门禁证据(no-difference)\n")
    lines.append(f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  \n")
    lines.append("## 背景\n")
    lines.append("依据 `knowledge/composite_score_architecture_issue.md` 层-综合分相关表: "
                 "L20_OptionVol(-0.266) / L1_ETF(-0.187) / L12_PoliticalRisk(-0.142) 负相关拖累排序。"
                 "本门禁验证对这三层配置化降权(0.3/0.5/0.6)后, pipeline composite 加权路径选出的 top5 "
                 "等权组合, 相对等权 baseline 是否劣化。\n")
    lines.append("## 方法学(v2 口径)\n")
    lines.append(f"- **池子(v2)**: 前 {config['screen_pool']} 只数字 code ETF 逐只 "
                 f"`_fetch_kline(code, {config['screen_days']})` 筛查 K线根数≥{config['min_kline']}(≈81周), "
                 f"不足剔除并打印剔除清单; 从达标者取前 {config['pool']} 只 `batch_full(live=False)` 穿透。\n")
    lines.append(f"- **首轮未判定原因**: 首轮未做上市时长筛查, top5 含上市仅 59 周的 159263, "
                 f"组合共同周 59<{config['min_weeks']}, 未产出 PASS/FAIL 数字。\n")
    lines.append(f"- **窗口门槛**: 组合共同周 ≥ {config['min_weeks']} 周, 不足如实报错退出非零。\n")
    lines.append("- **持有口径**: 期初等权买入持有, 组合周净值 = 各成分首周归一化等权均值, "
                 "整段窗口三指标(总收益/年化夏普=周收益×√52/最大回撤)。\n")
    lines.append("- **两路径**: baseline=weights None(纯等权 composite top5); "
                 "treatment=加载 weights.yaml 加权(Σ(w·s)/Σw) composite top5。\n")
    lines.append("## 两路径 top5(完全重合)\n")
    lines.append(f"- baseline : {','.join(codes)}\n")
    lines.append(f"- treatment: {','.join(codes)}\n")
    if s:
        lines.append(f"- 组合共同周: {s['weeks']}  |  总收益 {s['total_return']:+.2%}  |  "
                     f"夏普 {s['annualized_sharpe']:.3f}  |  最大回撤 {s['max_drawdown']:.2%}\n")
    lines.append("## 成分周数明细\n")
    lines.append("| code | weeks |\n|---|---|\n")
    lines += [f"| {c} | {w} |\n" for c, w in sorted(per.items())]
    lines.append("\n## 判定\n")
    lines.append(f"- **no-difference**: 等权与加权两路径 top5 完全重合, 三指标必然相同, "
                 f"说明在 {common_weeks}-周共同窗口内该权重幅度(0.3/0.5/0.6)在排序边界无影响。\n")
    lines.append(f"- **非 PASS**: 无法证明加权带来改善, 保守默认关闭 — 已把 config/weights.yaml 的 "
                 f"composite_layer_weights.enabled 改为 false ({'成功' if disabled else '失败'}), "
                 f"机制保留(行为关闭), 待有效幅度证据再启用。\n")
    lines.append("## 结论\n")
    lines.append("`verdict: no-difference — 两路径 top5 完全重合, 权重幅度无边界影响, 保守关闭 enabled=false`\n")
    return "\n".join(lines)


def _build_md(s_b, s_t, gate_pass, pass_sharpe, pass_mdd, rolled_back, config, c_b, c_t):
    lines = []
    lines.append("# CC T8 / P1-C: 负相关层配置化降权回测门禁证据\n")
    lines.append(f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  \n")
    lines.append("## 背景\n")
    lines.append("依据 `knowledge/composite_score_architecture_issue.md` 层-综合分相关表: "
                 "L20_OptionVol(-0.266) / L1_ETF(-0.187) / L12_PoliticalRisk(-0.142) 负相关拖累排序。"
                 "本门禁验证对这三层配置化降权(0.3/0.5/0.6)后, pipeline composite 加权路径选出的 top5 "
                 "等权组合, 相对等权 baseline 是否劣化。\n")
    lines.append("## 方法学\n")
    lines.append(f"- **池子(v2)**: 前 {config['screen_pool']} 只数字 code ETF 逐只 "
                 f"`_fetch_kline(code, {config['screen_days']})` 筛查 K线根数≥{config['min_kline']}(≈81周), "
                 f"不足剔除; 从达标者取前 {config['pool']} 只 `batch_full(live=False)` 穿透。\n")
    lines.append(f"- **首轮未判定原因**: 首轮未做上市时长筛查, top5 含上市仅 59 周的 159263, "
                 f"组合共同周 59<{config['min_weeks']}, 未产出数字; v2 修正为筛查后取前 50 只复跑。\n")
    lines.append(f"- **K线窗口**: `_fetch_kline(code, {config['kline_days']})`, 失败重试一次; "
                 f"取全部成分共同交易日按 ISO 周重采样(每周最后一个交易日收盘)。\n")
    lines.append(f"- **窗口门槛**: 组合共同周 ≥ {config['min_weeks']} 周, 不足如实报错退出非零。\n")
    lines.append("- **持有口径**: 期初等权买入持有, 组合周净值 = 各成分首周归一化等权均值, "
                 "整段窗口三指标(总收益/年化夏普=周收益×√52/最大回撤)。\n")
    lines.append("- **两路径**: baseline=weights None(纯等权 composite top5); "
                 "treatment=加载 weights.yaml 加权(Σ(w·s)/Σw) composite top5。\n")
    lines.append(f"- **门禁判据**: treatment 夏普 ≥ baseline×{config['sharpe_floor']} 且 "
                 f"最大回撤不深于 baseline×{config['mdd_floor']} → PASS。\n")
    lines.append("## 两路径对比表\n")
    lines.append("| path | codes_top5 | total_return | annualized_sharpe | max_drawdown | weeks |")
    lines.append("|---|---|---|---|---|---|")
    for label, s in (("baseline", s_b), ("treatment", s_t)):
        lines.append(f"| {label} | {','.join(s['codes_top5'])} | {s['total_return']:+.2%} | "
                     f"{s['annualized_sharpe']:.3f} | {s['max_drawdown']:.2%} | {s['weeks']} |")
    lines.append("\n## 判定\n")
    lines.append(f"- **夏普门禁**: treatment={s_t['annualized_sharpe']:.3f} vs "
                 f"baseline×{config['sharpe_floor']}={s_b['annualized_sharpe'] * config['sharpe_floor']:.3f} "
                 f"→ {'PASS ✅' if pass_sharpe else 'FAIL ❌'}。\n")
    lines.append(f"- **回撤门禁**: treatment={s_t['max_drawdown']:.2%} vs "
                 f"baseline×{config['mdd_floor']}={s_b['max_drawdown'] * config['mdd_floor']:.2%} "
                 f"→ {'PASS ✅' if pass_mdd else 'FAIL ❌'}。\n")
    if gate_pass:
        lines.append(f"- **总判定: PASS ✅** — 负相关层降权未劣化 top5 等权组合, 机制保留 "
                     f"(enabled=true)。\n")
        lines.append("- **回滚**: 未触发。\n")
    else:
        lines.append("- **总判定: FAIL ❌** — 加权路径劣化超限, 已触发回滚。\n")
        lines.append(f"- **回滚**: 已把 config/weights.yaml 的 composite_layer_weights.enabled "
                     f"改回 false ({'成功' if rolled_back else '失败'}), 机制保留(行为关闭, pipeline 恢复纯等权)。\n")
    lines.append("## 结论\n")
    if gate_pass:
        verdict = "pass — 门禁通过, 机制保留"
    else:
        verdict = "fail — 门禁否决, 已回滚 enabled=false, 机制保留待后续调参"
    lines.append(f"`verdict: {verdict}`\n")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
