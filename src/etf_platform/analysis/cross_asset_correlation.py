"""cross_asset_correlation.py — 跨资产相关性矩阵与分散化失效检测

来源: k189 (跨资产相关/危机制度)
行业 ETF 收益率相关性矩阵 + 分散化失效检测 + 左尾依赖。
纯 numpy + stdlib。
"""
from __future__ import annotations

import numpy as np

_MIN_SERIES = 30


def correlation_matrix(returns_by_code: dict[str, list[float]]) -> tuple[dict, dict]:
    """计算各资产收益率的相关性矩阵。

    返回 (corr_dict, meta)；corr_dict = {(codeA, codeB): corr} 上三角。
    任一系列长度 <30 或方差=0 返回空 corr_dict。
    """
    codes = list(returns_by_code)
    if len(codes) < 2:
        return ({}, {"reason": "insufficient_codes"})
    series = [returns_by_code[c] for c in codes]
    if any(len(s) < _MIN_SERIES for s in series):
        return ({}, {"reason": "series_too_short"})

    min_len = min(len(s) for s in series)
    arr = np.asarray([s[:min_len] for s in series], dtype=float)
    if np.any(np.var(arr, axis=1) == 0):
        return ({}, {"reason": "zero_variance"})

    corr = np.corrcoef(arr)
    corr_dict = {}
    vals = []
    for i in range(len(codes)):
        for j in range(i + 1, len(codes)):
            c = float(corr[i, j])
            corr_dict[(codes[i], codes[j])] = c
            vals.append(c)
    avg = float(np.mean(vals)) if vals else 0.0
    meta = {"codes": codes, "pairs": len(vals), "avg_corr": round(avg, 4)}
    return (corr_dict, meta)


def _serialize_keys(corr_dict: dict) -> dict:
    """tuple key → 'A|B' 字符串 key（小的在前，确定性排序）。"""
    return {f"{a}|{b}" if a <= b else f"{b}|{a}": c for (a, b), c in corr_dict.items()}


def correlation_matrix_serializable(returns_by_code: dict[str, list[float]]) -> dict:
    """相关矩阵的可 JSON 序列化版本：内部调 correlation_matrix，tuple key 转 'A|B'。"""
    corr_dict, _ = correlation_matrix(returns_by_code)
    return _serialize_keys(corr_dict)


def detect_diversification_failure(corr_dict: dict, threshold: float = 0.7) -> dict:
    """统计相关性 >threshold 的对数/总对数，判断分散化是否失效。

    high_ratio>0.5 → failure=True。
    """
    pairs = list(corr_dict)
    if not pairs:
        return {"failure": False, "high_corr_pairs": [], "high_ratio": 0.0, "avg_corr": 0.0}
    high = [(a, b, c) for (a, b), c in corr_dict.items() if c > threshold]
    avg = float(np.mean(list(corr_dict.values())))
    return {
        "failure": len(high) / len(pairs) > 0.5,
        "high_corr_pairs": high,
        "high_ratio": round(len(high) / len(pairs), 4),
        "avg_corr": round(avg, 4),
    }


def tail_dependence(returns_a: list[float], returns_b: list[float], quantile: float = 0.1) -> float:
    """左尾依赖系数: P(B在q分位以下 | A在q分位以下)，返回 [0,1]。"""
    if len(returns_a) < _MIN_SERIES or len(returns_b) < _MIN_SERIES:
        return 0.0
    a = np.asarray(returns_a, dtype=float)
    b = np.asarray(returns_b, dtype=float)
    n = min(len(a), len(b))
    a, b = a[:n], b[:n]
    qa = np.quantile(a, quantile)
    qb = np.quantile(b, quantile)
    below_a = a <= qa
    below_b = b <= qb
    a_count = int(np.sum(below_a))
    if a_count == 0:
        return 0.0
    both = int(np.sum(below_a & below_b))
    return round(both / a_count, 4)


def _returns_from_rows(rows: list[dict]) -> list[float]:
    close = [float(r["close"]) for r in rows]
    return [close[i] / close[i - 1] - 1 for i in range(1, len(close))] if len(close) > 1 else []


def get_cross_asset_risk(codes: list[str], days: int = 120) -> dict:
    """批量入口: 拉K线算日收益率→相关矩阵→分散化失效→左尾依赖。

    返回 {"corr_matrix", "failure", "avg_corr", "warnings"}。
    """
    from etf_platform.data.kline import _fetch_kline

    returns_by_code = {}
    for code in codes:
        rows = _fetch_kline(code, days)
        if rows:
            rets = _returns_from_rows(rows)
            if len(rets) >= _MIN_SERIES:
                returns_by_code[code] = rets

    corr_dict, meta = correlation_matrix(returns_by_code)
    if not corr_dict:
        return {"corr_matrix": {}, "failure": False, "avg_corr": 0.0,
                "warnings": [f"数据不足: {meta.get('reason', 'unknown')}"]}

    info = detect_diversification_failure(corr_dict)
    warnings = []
    if info["failure"]:
        warnings.append(f"分散化失效警报：高相关(>0.7)占比 {info['high_ratio']:.0%}")

    for (a, b) in corr_dict:
        if a not in returns_by_code or b not in returns_by_code:
            continue
        t = tail_dependence(returns_by_code[a], returns_by_code[b])
        if t > 0.5:
            warnings.append(f"左尾依赖危险：{a}-{b} 同跌系数 {t:.2f}")

    return {
        "corr_matrix": _serialize_keys(corr_dict),
        "failure": info["failure"],
        "avg_corr": info["avg_corr"],
        "warnings": warnings,
    }


if __name__ == "__main__":
    rng = np.random.default_rng(7)
    base = rng.standard_normal(120)
    a = base + 0.1 * rng.standard_normal(120)
    b = base + 0.1 * rng.standard_normal(120)
    c = 0.1 * rng.standard_normal(120)
    mat, m = correlation_matrix({"A": a.tolist(), "B": b.tolist(), "C": c.tolist()})
    print("corr:", mat)
    print("meta:", m)
    print("failure:", detect_diversification_failure(mat))
    print("tail A-B:", tail_dependence(a.tolist(), b.tolist()))
    print("tail A-C:", tail_dependence(a.tolist(), c.tolist()))
