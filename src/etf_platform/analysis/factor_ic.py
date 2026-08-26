"""factor_ic — 逐因子信息系数（IC）诊断（08-12 新增，优化路线图 P2）。

目标：回答"two_week_picker 的 6 个因子里，到底哪个真正预测了后续收益"，
服务 P0"回测样本不足/rank1 倒挂"的诊断——用 IC 的符号和量级判断因子是否
有效、是否倒挂，而不是靠文本建议。

局限（如实标注）：
- 预测日志只存 Top3，IC 是 top3-conditional（选择偏倚），只能作诊断参考，
  不能作全池真实 IC。样本充足后再逐步扩展记录池。
- 复用 prediction_monitor._return_since 的 K 线锚点法，避免前视偏差。

用法:
  python -m etf_platform.analysis.factor_ic
  python -m etf_platform.analysis.factor_ic --json
"""
import json
import logging
import math
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

BASE = Path(__file__).resolve().parent.parent.parent.parent  # etf-platform/
DATA_DIR = BASE / "data"
LOG_FILE = DATA_DIR / "two_week_predictions.jsonl"

# 08-12 修复: 对齐 two_week_picker.FACTORS v3.3 — trend_momentum 已因与
# oversold_depth 共线(r=-1.00)移除, sector_flow 是当前实际因子(权重0.08)。
# 08-18 优化: news_sentiment 已接入 two_week_picker（d751），纳入 IC 诊断；
# behavioral 权重为 0，不再进入默认诊断因子。
DEFAULT_FACTORS = ("oversold_depth", "risk_adj_momentum", "drawdown_recov",
                   "sector_flow", "quality_elastic", "news_sentiment")
PSEUDO_FACTORS = ("two_week_score", "z_composite", "pipeline_score")


def _spearman_rank(values: list[float]) -> list[float]:
    """返回每个元素在序列中的排名（并列取平均秩）。"""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    n = len(order)
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg_rank = (i + j) / 2 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        i = j + 1
    return ranks


def spearman_ic(values: list[float], returns: list[float]) -> float | None:
    """Spearman 秩相关（IC）。有效样本 <3 返回 None。"""
    if len(values) != len(returns) or len(values) < 3:
        return None
    rv = _spearman_rank(values)
    rr = _spearman_rank(returns)
    n = len(values)
    mean_rv = sum(rv) / n
    mean_rr = sum(rr) / n
    cov = sum((a - mean_rv) * (b - mean_rr) for a, b in zip(rv, rr, strict=True))
    var_a = sum((a - mean_rv) ** 2 for a in rv)
    var_b = sum((b - mean_rr) ** 2 for b in rr)
    if var_a == 0 or var_b == 0:
        return None
    return cov / math.sqrt(var_a * var_b)


def _load_predictions(log_file: Path) -> list[dict]:
    if not log_file.exists():
        return []
    records = []
    with open(log_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def compute_factor_ic(predictions: list[dict], return_fn,
                      factors: tuple[str, ...] = DEFAULT_FACTORS) -> dict:
    """对预测日志计算逐因子 IC。

    return_fn(code, date) -> 10日收益率(%) 或 None（复用锚点法）。
    返回 {factor: {"ic": float|None, "n": int, "ic_mean": ..., "ic_ir": ...}}。
    """
    # 每个因子收集 (因子值, 收益) 配对
    pairs: dict[str, list[tuple[float, float]]] = {f: [] for f in factors}
    for pred in predictions:
        pred_date = pred.get("date")
        for etf in pred.get("top3", []):
            code = etf.get("code")
            ret = return_fn(code, pred_date)
            if ret is None:
                continue
            for f in factors:
                val = _factor_value(etf, f)
                if val is not None:
                    pairs[f].append((val, ret))

    out = {}
    for f in factors:
        raw = pairs[f]
        n = len(raw)
        if n < 3:
            out[f] = {"ic": None, "n": n}
            continue
        ic = spearman_ic([v for v, _ in raw], [r for _, r in raw])
        out[f] = {
            "ic": round(ic, 4) if ic is not None else None,
            "n": n,
        }
    return {"factors": out, "total_pairs": len(predictions)}


def _factor_value(etf: dict, factor: str) -> float | None:
    if factor in PSEUDO_FACTORS:
        v = etf.get(factor)
        return float(v) if isinstance(v, (int, float)) else None
    zf = etf.get("z_factors") or {}
    v = zf.get(factor)
    return float(v) if isinstance(v, (int, float)) else None


def _real_return_fn(code: str, date: str) -> float | None:
    try:
        from etf_platform.decision.prediction_monitor import _return_since
        ret = _return_since(date, code, 10)
        return float(ret) if ret is not None else None
    except Exception as e:  # 数据缺失/网络抖动按无收益处理，不中断整表
        logger.debug("[factor_ic] %s@%s 收益取数失败: %s", code, date, e)
        return None


def run_report(log_file: Path = LOG_FILE) -> dict:
    predictions = _load_predictions(log_file)
    if not predictions:
        return {"status": "insufficient_data", "error": "无预测历史数据"}
    result = compute_factor_ic(predictions, _real_return_fn)
    result["status"] = "ok"
    result["log_file"] = str(log_file)
    return result


def format_report(result: dict) -> str:
    if result.get("status") != "ok":
        return f"❌ {result.get('error', '未知错误')}"
    lines = ["📊 因子 IC 诊断（top3-conditional，选择偏倚，仅诊断参考）",
             "=" * 60, ""]
    factors = result.get("factors", {})
    if not factors:
        return "❌ 无因子数据"
    rows = sorted(factors.items(), key=lambda kv: (kv[1].get("ic") is None, -(kv[1].get("ic") or 0)))
    for name, info in rows:
        ic = info.get("ic")
        if ic is None:
            lines.append(f"  {name:<22} n={info['n']:<3} IC=  N/A (样本不足)")
        else:
            # 08-12: n<10 的 IC 是噪声, 不标"有效", 避免 3 样本误读为信号
            flag = "⭑ 有效" if (abs(ic) >= 0.2 and info["n"] >= 10) else "·"
            lines.append(f"  {name:<22} n={info['n']:<3} IC={ic:+.4f}  {flag}")
    lines.append("")
    lines.append("  ⭑ |IC|≥0.2 且 n≥10 视为有区分度；IC 恒负说明因子方向倒挂")
    lines.append(f"  样本: {result.get('total_pairs', 0)} 次预测 (n<10 的 IC 不可信)")
    lines.append("=" * 60)
    return "\n".join(lines)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    json_mode = "--json" in sys.argv
    res = run_report()
    if json_mode:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(format_report(res))
