#!/usr/bin/env python3
"""
factor_correlation.py — Z-score 7因子共线性诊断 v1.0

诊断内容:
  1. 因子定义层面的数学关系 (恒定相关)
  2. 实证Spearman相关矩阵 (基于120只ETF实际因子值)
  3. VIF方差膨胀因子 (检测多重共线性)
  4. 主成分分析 (识别独立维度数量)
  5. 去冗余方案建议

用法:
  python -m etf_platform.analysis.factor_correlation
  python -m etf_platform.analysis.factor_correlation --json
"""

from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

BASE = Path(__file__).resolve().parent.parent.parent.parent
SRC = BASE / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


# ── Factor definitions (mirrors two_week_picker.py FACTORS) ─────────

FACTOR_DEFS: list[dict[str, Any]] = [
    {
        "name": "trend_momentum",
        "label": "趋势动量",
        "formula": "change_20d",
        "weight": 0.25,
        "ic": 0.876,
    },
    {
        "name": "risk_adj_momentum",
        "label": "风险调整动量",
        "formula": "change_20d / volatility_20d",
        "weight": 0.22,
        "ic": 0.781,
    },
    {
        "name": "quality_elastic",
        "label": "质量弹性",
        "formula": "-pipeline_score",
        "weight": 0.02,
        "ic": 0.076,
    },
    {
        "name": "behavioral",
        "label": "行为Alpha",
        "formula": "L21 subfactors",
        "weight": 0.00,
        "ic": 0.000,
    },
    {
        "name": "oversold_depth",
        "label": "超跌深度",
        "formula": "-change_20d",
        "weight": 0.25,
        "ic": 0.876,
    },
    {
        "name": "drawdown_recov",
        "label": "回撤修复潜力",
        "formula": "-max_drawdown",
        "weight": 0.19,
        "ic": 0.680,
    },
    {
        "name": "sector_flow",
        "label": "行业资金流",
        "formula": "sector_flow_bridge.score()",
        "weight": 0.07,
        "ic": 0.255,
    },
]


# ── Mathematical relationship analysis ────────────────────────────

def analyze_mathematical_relationships() -> list[dict]:
    """Detect exact mathematical dependencies between factor formulas.

    Returns list of relationship dicts with type/strength/explanation.
    """
    relationships = []

    # trend_momentum = change_20d, oversold_depth = -change_20d
    relationships.append({
        "pair": ("trend_momentum", "oversold_depth"),
        "type": "perfect_negative",
        "strength": -1.0,
        "explanation": (
            "两者用同一输入(t.change_20d)，仅符号相反。"
            "趋势动量=+change_20d，超跌深度=-change_20d。"
            "数学上完全共线(r=-1.0)，合计权重50%实为内部对冲。"
        ),
        "action": "merge_or_drop_one",
    })

    # risk_adj_momentum shares numerator with trend_momentum
    relationships.append({
        "pair": ("trend_momentum", "risk_adj_momentum"),
        "type": "shared_numerator",
        "strength": "high_positive (est. 0.85~0.95)",
        "explanation": (
            "风险调整动量 = change_20d/volatility_20d，"
            "趋势动量 = change_20d。两者共享分子change_20d，"
            "除以波动率仅做缩放，不改变方向。预期高度正相关。"
        ),
        "action": "keep_one_or_orthogonalize",
    })

    # oversold_depth and drawdown_recov both measure downside
    relationships.append({
        "pair": ("oversold_depth", "drawdown_recov"),
        "type": "conceptual_overlap",
        "strength": "moderate_positive (est. 0.5~0.7)",
        "explanation": (
            "超跌深度=-(20日涨跌幅)，回撤修复=-(最大回撤)。"
            "大幅下跌通常伴随大回撤，两者概念重叠。"
            "20日跌幅与期间最大回撤高度相关但不完全等同。"
        ),
        "action": "monitor_or_weight_down",
    })

    return relationships


# ── Empirical correlation analysis ────────────────────────────────

def collect_factor_values(max_etfs: int = 120) -> dict[str, list[float]]:
    """Collect raw factor values for all available ETFs.

    Returns dict[factor_name, list[float]].
    """
    from etf_platform.config_loader import load_etfs
    from etf_platform.data.kline import get_trend
    from etf_platform.pipeline import run_full

    etfs = load_etfs()

    # Filter candidates (same logic as two_week_picker)
    EXCLUDE_SECTORS = {"货币基金", "利率债", "信用债", "债券", "国债", "货币"}
    EXCLUDE_KEYWORDS = [
        "沪深300", "中证500", "中证1000", "上证50", "科创50", "科创100", "创业板"
    ]
    EXCLUDE_TYPES = {"宽基", "全市场"}

    candidates: list[tuple[str, dict]] = []
    for code, info in etfs.items():
        if not code.isdigit():
            continue
        if info.get("sector", "") in EXCLUDE_SECTORS:
            continue
        if info.get("type") in EXCLUDE_TYPES:
            continue
        if info.get("access") != "buyable":
            continue
        name = info.get("name", "")
        if any(kw in name for kw in EXCLUDE_KEYWORDS):
            continue
        candidates.append((code, info))
        if len(candidates) >= max_etfs:
            break

    raw_values: dict[str, list[float]] = defaultdict(list)
    valid_count = 0

    for code, info in candidates:
        trend = get_trend(code)
        if trend is None or trend.data_days < 10:
            continue

        try:
            pipe = run_full(code, live=False)
        except (ImportError, KeyError, ValueError, TypeError,
                AttributeError, OSError, RuntimeError):
            continue

        if not pipe:
            continue

        raw_values["trend_momentum"].append(trend.change_20d)
        raw_values["oversold_depth"].append(-trend.change_20d)
        raw_values["risk_adj_momentum"].append(
            trend.change_20d / max(trend.volatility_20d, 0.01)
        )
        raw_values["drawdown_recov"].append(-trend.max_drawdown)
        raw_values["quality_elastic"].append(-pipe.get("score", 5.0))

        # sector_flow
        try:
            from etf_platform.analysis.sector_flow_bridge import get_bridge
            bridge = get_bridge()
            sf = bridge.score(
                info.get("sector", ""), live=False, etf_code=code
            )
            raw_values["sector_flow"].append(sf.get("_return_pct", 0))
        except (ImportError, KeyError, ValueError, TypeError,
                AttributeError, OSError):
            raw_values["sector_flow"].append(0.0)

        valid_count += 1

    print(f"  [collect] {valid_count}/{len(candidates)} ETFs with valid data")
    return dict(raw_values)


def compute_correlation_matrix(
    raw_values: dict[str, list[float]],
) -> dict[str, Any]:
    """Compute Spearman correlation matrix and VIF.

    Returns dict with correlation_matrix, vif, condition_number.
    """
    # Select active factors (exclude behavioral which is 0-weight)
    active_factors = [
        "trend_momentum", "risk_adj_momentum", "quality_elastic",
        "oversold_depth", "drawdown_recov", "sector_flow",
    ]

    n = len(active_factors)
    matrix = np.zeros((n, n))
    labels = active_factors

    for i, fi in enumerate(active_factors):
        for j, fj in enumerate(active_factors):
            if i == j:
                matrix[i][j] = 1.0
                continue
            x = np.array(raw_values.get(fi, []))
            y = np.array(raw_values.get(fj, []))
            if len(x) < 3 or len(y) < 3:
                matrix[i][j] = 0.0
                continue
            # Pearson for linear relationships
            corr = np.corrcoef(x, y)[0, 1]
            matrix[i][j] = round(float(corr), 4) if not np.isnan(corr) else 0.0

    # Build labeled matrix
    corr_matrix: list[list[float]] = matrix.tolist()

    # VIF computation
    vif_values: dict[str, float] = {}
    for i, fi in enumerate(active_factors):
        y = np.array(raw_values.get(fi, []))
        if len(y) < 3:
            vif_values[fi] = 1.0
            continue
        # Build X from other factors
        other_cols = []
        for j, fj in enumerate(active_factors):
            if i == j:
                continue
            other_cols.append(np.array(raw_values.get(fj, [])))
        if not other_cols:
            vif_values[fi] = 1.0
            continue
        X = np.column_stack(other_cols)
        try:
            # OLS: y = Xβ + ε
            beta = np.linalg.lstsq(X, y, rcond=None)[0]
            y_pred = X @ beta
            ss_res = np.sum((y - y_pred) ** 2)
            ss_tot = np.sum((y - np.mean(y)) ** 2)
            r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0
            vif = 1.0 / (1.0 - r_squared) if r_squared < 1 else float("inf")
            vif_values[fi] = round(float(vif), 2)
        except np.linalg.LinAlgError:
            vif_values[fi] = float("inf")

    # Condition number of correlation matrix
    try:
        eigenvalues = np.linalg.eigvals(matrix)
        cond_num = float(max(abs(eigenvalues)) / min(abs(eigenvalues)))
    except (np.linalg.LinAlgError, ValueError):
        cond_num = float("inf")

    return {
        "labels": labels,
        "correlation_matrix": corr_matrix,
        "vif": vif_values,
        "condition_number": round(cond_num, 1),
        "n_samples": min(len(v) for v in raw_values.values() if v),
    }


def analyze_pca(raw_values: dict[str, list[float]]) -> dict[str, Any]:
    """PCA to determine effective number of independent dimensions."""
    active_factors = [
        "trend_momentum", "risk_adj_momentum", "quality_elastic",
        "oversold_depth", "drawdown_recov", "sector_flow",
    ]

    cols = []
    for fi in active_factors:
        vals = raw_values.get(fi, [])
        if vals:
            cols.append(vals)
    if not cols:
        return {"effective_dimensions": 0, "explained_variance": []}

    X = np.column_stack(cols)
    # Standardize
    X_centered = X - np.mean(X, axis=0)
    X_std = np.std(X_centered, axis=0)
    X_std[X_std == 0] = 1.0
    X_scaled = X_centered / X_std

    # SVD
    _, S, _ = np.linalg.svd(X_scaled, full_matrices=False)
    explained = (S ** 2) / np.sum(S ** 2)
    cumulative = np.cumsum(explained)

    effective_dim = int(np.sum(cumulative < 0.95)) + 1

    return {
        "effective_dimensions": effective_dim,
        "total_factors": len(active_factors),
        "explained_variance_ratio": [round(float(e), 4) for e in explained],
        "cumulative_variance": [round(float(c), 4) for c in cumulative],
    }


# ── De-duplication proposals ──────────────────────────────────────

def generate_proposals(
    math_relations: list[dict],
    corr_result: dict,
    pca_result: dict,
) -> list[dict]:
    """Generate concrete de-duplication proposals based on all analyses."""
    proposals = []

    vif = corr_result.get("vif", {})

    # Proposal 1: Merge trend_momentum + oversold_depth
    tm_vif = vif.get("trend_momentum", 0)
    od_vif = vif.get("oversold_depth", 0)
    props_1 = {
        "id": "P1",
        "title": "合并趋势动量+超跌深度为单一动量因子",
        "rationale": (
            "两者相关系数r=-1.0(数学恒等)，合计权重50%但内部对冲。"
            f"VIF: trend_momentum={tm_vif}, oversold_depth={od_vif}"
        ),
        "implementation": (
            "保留一个(建议保留超跌深度，因为IC相同且方向与选股逻辑一致"
            "——跌越多分越高)，权重=原两因子之和的80%(避免过重)=40%。"
            "或者取两者的方向强度: sign(change_20d)*|change_20d| 等价于change_20d本身。"
        ),
        "expected_impact": "减少1个冗余因子，消除完美共线，释放~20%权重给其他因子",
    }
    proposals.append(props_1)

    # Proposal 2: risk_adj_momentum orthogonalization
    props_2 = {
        "id": "P2",
        "title": "风险调整动量正交化",
        "rationale": (
            "风险调整动量与趋势动量共享分子change_20d，预期高度正相关。"
            "应改为独立信号(如Sharpe ratio或Sortino ratio)。"
        ),
        "implementation": (
            "新公式: (change_20d - risk_free) / volatility_20d，"
            "或直接用Sortino ratio仅惩罚下行波动。"
            "当前公式除以volatility_20d仅做缩放在Z-score标准化后无意义。"
        ),
        "expected_impact": "提升因子独立性，降低与趋势动量的共线性",
    }
    proposals.append(props_2)

    # Proposal 3: Innovation — regime-aware dynamic weights
    props_3 = {
        "id": "P3",
        "title": "基于市场状态的动态因子权重",
        "rationale": (
            "当前权重固定(基于历史IC均值)，但因子有效性随市场状态变化。"
            "如: 恐慌期超跌深度更有效，趋势期动量更有效。"
        ),
        "implementation": (
            "根据QVIX regime切换权重预设:"
            "\n  fearful: 超跌35% + 回撤25% + 资金流20% + 趋势10% + 质量10%"
            "\n  normal:  趋势30% + 风险调整25% + 回撤15% + 资金流20% + 质量10%"
            "\n  complacent: 趋势35% + 风险调整30% + 资金流20% + 质量15%"
        ),
        "expected_impact": "提升regime适应性，实证来自锦标赛的regime-策略表现",
    }
    proposals.append(props_3)

    # Proposal 4: Innovation — ETF-specific normalization
    props_4 = {
        "id": "P4",
        "title": "行业内Z-score标准化替代全局标准化",
        "rationale": (
            "当前全局Z-score标准化将所有行业ETF混在一起比较，"
            "导致高波动行业(半导体、券商)天然有更极端的Z-score，"
            "低波动行业(消费、公用事业)被系统性低估。"
        ),
        "implementation": (
            "改为两步标准化: (1)行业内Z-score → (2)跨行业rank percentile。"
            "这样每个行业内部选出最优，再跨行业比较。"
        ),
        "expected_impact": "消除行业波动率偏差，让消费/医药等防御行业获得公平评分",
    }
    proposals.append(props_4)

    return proposals


# ── Report ────────────────────────────────────────────────────────

def format_report(
    math_relations: list[dict],
    corr_result: dict,
    pca_result: dict,
    proposals: list[dict],
) -> str:
    """Format complete analysis as readable text."""
    lines = [
        "=" * 70,
        "🔬 Z-score 7因子共线性诊断报告",
        "=" * 70,
        "",
        "── 1. 数学关系分析 ──",
        "",
    ]

    for rel in math_relations:
        a, b = rel["pair"]
        lines.append(f"  {a} ↔ {b}")
        lines.append(f"    类型: {rel['type']} ({rel['strength']})")
        lines.append(f"    {rel['explanation']}")
        lines.append(f"    建议: {rel['action']}")
        lines.append("")

    lines.append("── 2. Pearson相关矩阵 ──")
    lines.append("")
    labels = corr_result.get("labels", [])
    matrix = corr_result.get("correlation_matrix", [])

    # Header
    short_labels = [label.replace("_", " ")[:12] for label in labels]
    header = " " * 14 + "".join(f"{s:>8s}" for s in short_labels)
    lines.append(header)

    for i, label in enumerate(labels):
        row = f"  {label:<12s}"
        for j in range(len(labels)):
            val = matrix[i][j] if i < len(matrix) and j < len(matrix[i]) else 0
            # Highlight extreme correlations
            prefix = "⚠️" if abs(val) > 0.85 and i != j else "  "
            row += f"{prefix}{val:>6.2f}"
        lines.append(row)

    lines.append("")
    lines.append("  (>0.85 = ⚠️极强相关, 建议合并或正交化)")
    lines.append("")

    lines.append("── 3. VIF (方差膨胀因子) ──")
    lines.append("")
    vif = corr_result.get("vif", {})
    for name, val in sorted(vif.items(), key=lambda x: -x[1]):
        if val == float("inf"):
            flag = "💀 完全共线! "
            val_str = "∞"
        elif val > 10:
            flag = "🔴 严重 "
            val_str = f"{val:.1f}"
        elif val > 5:
            flag = "🟡 中度 "
            val_str = f"{val:.1f}"
        else:
            flag = "🟢 "
            val_str = f"{val:.1f}"
        lines.append(f"  {flag}{name:<20s} VIF={val_str}")

    lines.append("")
    lines.append(f"  条件数: {corr_result.get('condition_number', '?')}")
    lines.append(f"  样本数: {corr_result.get('n_samples', 0)}只ETF")
    lines.append("")

    lines.append("── 4. PCA主成分分析 ──")
    lines.append("")
    eff_dim = pca_result['effective_dimensions']
    total = pca_result['total_factors']
    lines.append(f"  有效独立维度: {eff_dim}/{total}")
    evr = pca_result.get("explained_variance_ratio", [])
    cum = pca_result.get("cumulative_variance", [])
    for i, (e, c) in enumerate(zip(evr, cum)):
        lines.append(f"  PC{i+1}: {e:.1%} (累计{c:.1%})")
    lines.append("")

    lines.append("── 5. 去冗余方案 ──")
    lines.append("")
    for p in proposals:
        lines.append(f"  [{p['id']}] {p['title']}")
        lines.append(f"  理由: {p['rationale'][:120]}...")
        lines.append(f"  改动: {p['implementation'][:120]}...")
        lines.append(f"  预期: {p['expected_impact']}")
        lines.append("")

    lines.append("=" * 70)
    lines.append("因子共线性诊断完成 · 建议优先执行 P1(合并) + P4(行业标准化)")

    return "\n".join(lines)


# ── CLI ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    json_mode = "--json" in sys.argv

    print("🔬 因子共线性诊断中...")
    t0 = time.time()

    # 1. Mathematical analysis
    print("  [1/4] 数学关系分析...")
    math_relations = analyze_mathematical_relationships()

    # 2. Empirical correlation
    print("  [2/4] 收集因子值并计算相关性...")
    raw_values = collect_factor_values(max_etfs=120)
    corr_result = compute_correlation_matrix(raw_values)

    # 3. PCA
    print("  [3/4] PCA主成分分析...")
    pca_result = analyze_pca(raw_values)

    # 4. Proposals
    print("  [4/4] 生成去冗余方案...")
    proposals = generate_proposals(math_relations, corr_result, pca_result)

    elapsed = time.time() - t0
    print(f"  ✅ 完成 ({elapsed:.1f}s)")

    if json_mode:
        output = {
            "math_relations": math_relations,
            "correlation": corr_result,
            "pca": pca_result,
            "proposals": proposals,
            "elapsed_seconds": round(elapsed, 1),
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(format_report(math_relations, corr_result, pca_result, proposals))
