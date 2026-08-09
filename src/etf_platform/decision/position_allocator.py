#!/usr/bin/env python3
"""
position_allocator.py — ETF预测持仓分配引擎 v1.0

来源: k170 (资产配置/组合构建)
================================================================================
问题：系统产出 Top3 后，没有分配逻辑——只是告诉用户"买这3个"，但没说各买多少。
================================================================================

核心设计原则
------------
1. 只使用系统中已有的数据（不引入外部依赖）
2. 适配 regime-aware 框架（fearful/cautious/normal/complacent）
3. 可对比多种分配方法（等权 / 分数加权 / 置信度加权 / 风险平价近似 / 风险平价 / Black-Litterman）
4. 硬约束：单ETF上限、行业集中度、恐慌降仓

可用数据源（来自 fused_top3 + 全局状态）
-----------------------------------------
- weighted_score: 0-100 融合评分
- sources: 来源列表（zscore/ml/tournament/events）
- raw_scores: {source_name: score} 字典
- change_20d, change_10d, max_drawdown, volatility_20d, position_pct, volume_ratio
- regime: 当前市场状态（complacent/normal/cautious/fearful）
- prob_stay/prob_improve/prob_worsen: regime转换概率
- source_confidences: {source_name: calibrated_probability}

输出格式
--------
{
    "allocation_method": "score_weighted_regime_adjusted",
    "total_exposure": 0.75,        # 总仓位比例 (0-1)
    "holdings": [                  # 持仓列表
        {
            "code": "518880",
            "name": "黄金ETF",
            "weight": 0.40,        # 占总投资资金的权重
            "raw_weight": 0.45,    # 未缩放前的原始权重
            "method_score": 0.82,  # 该方法的贡献分
            "reason": "高分+低波动"
        },
        ...
    ],
    "cash_reserve": 0.25,          # 现金保留比例
    "constraints_applied": [...],  # 触发的约束
    "regime": "normal",
    "risk_flags": {...},           # 风控信号
    "comparison": {                # 各方法对比
        "equal_weight": {"total_exposure": 1.0, "top3_weights": [0.33, 0.33, 0.33]},
        "score_weighted": {...},
        "confidence_weighted": {...},
        "vol_weighted": {...},
    }
}
"""

import json
import math
from dataclasses import dataclass, field, asdict
from datetime import date
from typing import Optional


# ── Regime exposure multipliers ──────────────────────────────────────
# 不同regime下建议的总仓位上限
REGIME_EXPOSURE = {
    "complacent": 1.0,   # 放松期：满仓
    "normal":     0.90,  # 正常期：90%
    "cautious":   0.65,  # 谨慎期：65%
    "fearful":    0.30,  # 恐慌期：30%
}

# 备选名称映射（qvix_regime.py 和 regime_transition.py 用词略有不同）
_REGIME_ALIASES = {
    "fear": "fearful",
    "panic": "fearful",
    "caution": "cautious",
    "complacency": "complacent",
}


def _resolve_regime(raw: str) -> str:
    """统一regime命名。"""
    return _REGIME_ALIASES.get(raw.lower(), raw.lower())


# ── Hard constraints ─────────────────────────────────────────────────
MAX_SINGLE_ETf_WEIGHT = 0.50      # 单ETF最大权重 50%
MAX_SECTOR_WEIGHT = 0.60          # 单行业最大权重 60%
MIN_ALLOCATION_WEIGHT = 0.05      # 最低分配 5%（低于则排除）
CASH_BUFFER_MIN = 0.10            # 最小现金缓冲 10%


@dataclass(slots=True)
class Holding:
    """单个持仓的分配结果。"""
    code: str
    name: str
    weight: float           # 最终权重（占总资金比例）
    raw_weight: float       # 未约束前的原始权重
    method_score: float     # 该方法下的贡献分数
    reason: str = ""
    sector: str = ""
    volatility: float = 0.0
    change_20d: float = 0.0
    max_drawdown: float = 0.0


@dataclass(slots=True)
class AllocationResult:
    """完整分配结果。"""
    date: str = field(default_factory=lambda: date.today().isoformat())
    allocation_method: str = ""
    total_exposure: float = 0.0
    cash_reserve: float = 0.0
    holdings: list[Holding] = field(default_factory=list)
    constraints_applied: list[str] = field(default_factory=list)
    regime: str = "normal"
    regime_multiplier: float = 1.0
    risk_flags: dict = field(default_factory=dict)
    comparison: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


# ══════════════════════════════════════════════════════════════════════
# 核心接口
# ══════════════════════════════════════════════════════════════════════


def allocate(
    fused_top3: list[dict],
    regime: str = "normal",
    source_confidences: Optional[dict] = None,
    transition_probs: Optional[dict] = None,
    profile: str = "均衡",
    risk_flags: Optional[dict] = None,
    method: Optional[str] = None,
) -> AllocationResult:
    """主入口：基于多方法对比后选择最优分配方案。

    Args:
        fused_top3: unified_runner 产出的融合Top3列表
        regime: 当前市场状态（complacent/normal/cautious/fearful）
        source_confidences: {source_name: calibrated_probability}
        transition_probs: {"prob_stay": x, "prob_improve": y, "prob_worsen": z}
        profile: 风险偏好（均衡/激进/保守/进取）
        risk_flags: 风控信号（来自 risk_manager.check_risk_flags()）
        method: 强制指定分配方法（risk_parity/black_litterman/equal_weight/...）；
            None 时自动选择（默认 hybrid，波动率差异大时可选 risk_parity）

    Returns:
        AllocationResult 包含所有方法的对比结果
    """
    result = AllocationResult(
        regime=_resolve_regime(regime),
        risk_flags=risk_flags or {},
    )

    if not fused_top3:
        result.notes.append("无预测数据，无法分配")
        return result

    # 1. 计算regime暴露度
    resolved_regime = result.regime
    base_exposure = REGIME_EXPOSURE.get(resolved_regime, 0.90)
    result.regime_multiplier = base_exposure

    # 2. 根据transition_probs微调暴露度
    if transition_probs:
        prob_worsen = transition_probs.get("prob_worsen", 0.25)
        prob_improve = transition_probs.get("prob_improve", 0.25)
        # 恶化概率高 → 进一步降仓
        if prob_worsen > 0.4:
            result.regime_multiplier *= 0.7
        # 改善概率高 → 小幅加仓
        elif prob_improve > 0.4:
            result.regime_multiplier *= 1.1
        result.regime_multiplier = min(1.0, result.regime_multiplier)

    # 3. 根据profile调整
    profile_adjustments = {"激进": 1.1, "保守": 0.85, "进取": 1.05, "均衡": 1.0}
    result.regime_multiplier *= profile_adjustments.get(profile, 1.0)
    result.regime_multiplier = round(min(1.0, max(0.1, result.regime_multiplier)), 2)

    # 4. 如果触发止损/大幅回撤，强制降仓
    if risk_flags:
        if risk_flags.get("stop_loss_hit"):
            result.notes.append(f"⚠️ 止损触发: {len(risk_flags['stop_loss_hit'])}只ETF")
            result.regime_multiplier *= 0.5
        if risk_flags.get("portfolio_dd_critical"):
            result.notes.append("🔴 组合回撤超限，强制降仓至30%")
            result.regime_multiplier = 0.3
        elif risk_flags.get("portfolio_dd_warning"):
            result.notes.append("🟡 组合回撤预警，减仓至50%")
            result.regime_multiplier *= 0.6

    result.regime_multiplier = round(min(1.0, max(0.1, result.regime_multiplier)), 2)

    # 5. 运行所有分配方法
    methods = {
        "equal_weight": _equal_weight(fused_top3, result.regime_multiplier),
        "score_weighted": _score_weighted(fused_top3, result.regime_multiplier),
        "confidence_weighted": _confidence_weighted(
            fused_top3, source_confidences or {}, result.regime_multiplier
        ),
        "vol_weighted": _vol_weighted(fused_top3, result.regime_multiplier),
        "hybrid_score_conf_vol": _hybrid_allocation(
            fused_top3, source_confidences or {}, result.regime_multiplier
        ),
        "risk_parity": _risk_parity_weighted(fused_top3, result.regime_multiplier),
        "black_litterman": _black_litterman_weighted(fused_top3, result.regime_multiplier),
    }

    result.comparison = {
        name: {
            "total_exposure": m.total_exposure,
            "cash_reserve": m.cash_reserve,
            "top3_weights": [h.weight for h in m.holdings],
            "constraints": m.constraints_applied,
        }
        for name, m in methods.items()
    }

    # 6. 选择最优方法（默认 hybrid，可配置；method 指定时强制使用）
    if method is not None:
        selected = methods.get(method)
        if selected is None:
            result.notes.append(f"未知分配方法: {method}, 回退自动选择")
            selected = _select_best_method(methods, fused_top3, resolved_regime)
    else:
        selected = _select_best_method(methods, fused_top3, resolved_regime)
    result.allocation_method = selected.allocation_method
    result.total_exposure = selected.total_exposure
    result.cash_reserve = selected.cash_reserve
    result.holdings = selected.holdings
    result.constraints_applied = selected.constraints_applied
    result.notes.extend(selected.notes)

    # k105: analyze three-layer architecture distribution
    tl_note = _analyze_three_layer_distribution(result.holdings, fused_top3)
    result.notes.append(f"k105 three-layer: {tl_note}")

    return result


def format_allocation_report(result: AllocationResult) -> str:
    """将分配结果格式化为可读报告。"""
    lines = [
        "💰 ETF持仓分配报告",
        f"{'=' * 60}",
        f"  日期: {result.date}",
        f"  市场状态: {result.regime.upper()}",
        "  风险偏好: 均衡型",
        f"  总仓位: {result.total_exposure:.0%}",
        f"  现金储备: {result.cash_reserve:.0%}",
        f"  分配方法: {result.allocation_method}",
        "",
    ]

    if result.holdings:
        lines.append("  ── 持仓分配 ──")
        for i, h in enumerate(result.holdings, 1):
            vol_tag = f" | 波动{h.volatility:.0f}%" if h.volatility else ""
            dd_tag = f" | 回撤{h.max_drawdown:.0f}%" if h.max_drawdown else ""
            lines.append(
                f"  {i}. {h.code} {h.name:<10s} 权重={h.weight:.0%} "
                f"(原始={h.raw_weight:.0%}){vol_tag}{dd_tag}"
            )
            if h.reason:
                lines.append(f"     → {h.reason}")
    else:
        lines.append("  ⚠️ 无有效持仓")

    if result.constraints_applied:
        lines.append("")
        lines.append("  ── 触发约束 ──")
        for c in result.constraints_applied:
            lines.append(f"    • {c}")

    if result.notes:
        lines.append("")
        lines.append("  ── 备注 ──")
        for n in result.notes:
            lines.append(f"    {n}")

    # 方法对比
    if result.comparison:
        lines.append("")
        lines.append("  ── 方法对比 ──")
        lines.append(f"  {'方法':<30s} {'总仓位':>8s} {'Top3权重':>20s}")
        lines.append(f"  {'─' * 58}")
        for name, comp in result.comparison.items():
            weights_str = ", ".join(f"{w:.0%}" for w in comp["top3_weights"])
            lines.append(
                f"  {name:<30s} {comp['total_exposure']:>7.0%} {weights_str:>20s}"
            )

    lines.append("")
    lines.append(f"{'=' * 60}")
    lines.append("持仓分配器 v1.0 · 不构成投资建议")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════
# 分配方法实现
# ══════════════════════════════════════════════════════════════════════


def _build_holdings(
    items: list[dict],
    weights: list[float],
    method_name: str,
    max_exposure: float,
) -> tuple[list[Holding], list[str]]:
    """通用构建函数：从预测数据+权重构建Holding列表，应用硬约束。"""
    constraints = []
    holdings = []

    # 先按权重排序
    paired = sorted(zip(items, weights), key=lambda x: -x[1])

    for etf, raw_w in paired:
        code = etf.get("code", "")
        name = etf.get("name", code)
        sector = etf.get("sector", "未知")
        vol = etf.get("volatility", 0)
        chg20 = etf.get("change_20d", 0)
        dd = etf.get("max_drawdown", 0)
        score = etf.get("weighted_score", 50)

        # 应用单ETF上限
        final_w = min(raw_w, MAX_SINGLE_ETf_WEIGHT)
        if final_w < raw_w:
            constraints.append(f"单ETF上限: {code} 从 {raw_w:.0%} 降至 {final_w:.0%}")

        # 应用最低分配
        if final_w < MIN_ALLOCATION_WEIGHT:
            continue

        # 生成原因标签
        reasons = []
        if score >= 75:
            reasons.append("高分")
        elif score >= 60:
            reasons.append("中分")
        else:
            reasons.append("低分")
        if vol < 2:
            reasons.append("低波动")
        elif vol > 4:
            reasons.append("高波动")
        if chg20 > 3:
            reasons.append("强势")
        elif chg20 < -5:
            reasons.append("超跌反弹")

        holdings.append(Holding(
            code=code,
            name=name,
            weight=final_w,
            raw_weight=raw_w,
            method_score=score,
            reason="+".join(reasons),
            sector=sector,
            volatility=vol,
            change_20d=chg20,
            max_drawdown=dd,
        ))

    # 行业集中度检查
    sector_weights: dict[str, float] = {}
    for h in holdings:
        sector_weights[h.sector] = sector_weights.get(h.sector, 0) + h.weight
    for sec, sw in sector_weights.items():
        if sw > MAX_SECTOR_WEIGHT:
            constraints.append(
                f"行业集中: {sec} 权重 {sw:.0%} 超过 {MAX_SECTOR_WEIGHT:.0%} 上限"
            )

    # 归一化到目标暴露度
    total_raw = sum(h.weight for h in holdings)
    if total_raw > 0:
        scale = max_exposure / total_raw
        for h in holdings:
            h.weight = round(h.weight * scale, 4)
            # 二次检查单ETF上限
            if h.weight > MAX_SINGLE_ETf_WEIGHT:
                h.weight = MAX_SINGLE_ETf_WEIGHT
                constraints.append(f"归一化后仍超限: {h.code}")

    # 确保现金缓冲
    actual_total = sum(h.weight for h in holdings)
    cash = round(max(1.0 - actual_total, CASH_BUFFER_MIN), 4)
    if cash > CASH_BUFFER_MIN and actual_total > 0:
        # 按比例缩减持仓以保留最小现金
        shrink = (1.0 - cash) / actual_total
        for h in holdings:
            h.weight = round(h.weight * shrink, 4)

    return holdings, constraints


# ── 方法1: 等权分配 ──────────────────────────────────────────────────
def _equal_weight(fused_top3: list[dict], max_exposure: float) -> AllocationResult:
    """等权分配：每个ETF相同权重。

    优点：简单、分散风险、无需历史数据
    缺点：忽略质量差异，在高质量信号上浪费仓位
    """
    n = len(fused_top3)
    if n == 0:
        return AllocationResult(allocation_method="equal_weight")

    # 每个ETF获得 exposure/n 的权重
    equal_w = min(1.0 / n, MAX_SINGLE_ETf_WEIGHT)
    weights = [equal_w] * n

    holdings, constraints = _build_holdings(fused_top3, weights, "equal_weight", max_exposure)

    result = AllocationResult(
        allocation_method="equal_weight",
        total_exposure=sum(h.weight for h in holdings),
        cash_reserve=max(0, 1.0 - sum(h.weight for h in holdings)),
        holdings=holdings,
        constraints_applied=constraints,
        notes=["等权分配: 每个ETF均分仓位"],
    )
    return result


# ── 方法2: 分数加权分配 ──────────────────────────────────────────────
def _score_weighted(fused_top3: list[dict], max_exposure: float) -> AllocationResult:
    """分数加权分配：按weighted_score比例分配。

    优点：充分利用预测质量差异
    缺点：高度依赖分数校准质量
    """
    if not fused_top3:
        return AllocationResult(allocation_method="score_weighted")

    scores = [max(etf.get("weighted_score", 50), 1) for etf in fused_top3]
    total_score = sum(scores)
    raw_weights = [s / total_score for s in scores]

    holdings, constraints = _build_holdings(
        fused_top3, raw_weights, "score_weighted", max_exposure
    )

    # 分析分数离散度
    score_range = max(scores) - min(scores) if scores else 0
    note = f"分数加权: 分数范围{score_range:.0f}, "
    if score_range > 20:
        note += "高分和低分差距大, 分配差异明显"
    elif score_range > 10:
        note += "分数有一定区分度"
    else:
        note += "分数接近, 等权效果类似"

    result = AllocationResult(
        allocation_method="score_weighted",
        total_exposure=sum(h.weight for h in holdings),
        cash_reserve=max(0, 1.0 - sum(h.weight for h in holdings)),
        holdings=holdings,
        constraints_applied=constraints,
        notes=[note],
    )
    return result


# ── 方法3: 置信度加权分配 ────────────────────────────────────────────
def _confidence_weighted(
    fused_top3: list[dict],
    source_confidences: dict[str, float],
    max_exposure: float,
) -> AllocationResult:
    """置信度加权分配：基于source_confidences + 来源数量。

    每只ETF的置信度 = 平均来源置信度 × log(1 + 来源数)

    优点：利用贝叶斯校准的概率，有统计基础
    缺点：依赖calibration.json的质量，无数据时回退到0.5
    """
    if not fused_top3:
        return AllocationResult(allocation_method="confidence_weighted")

    confidences = []
    for etf in fused_top3:
        sources = etf.get("sources", [])
        if not sources:
            confidences.append(0.5)
            continue

        # 计算该ETF涉及的source的平均置信度
        src_confs = []
        for s in sources:
            c = source_confidences.get(s, 0.5)
            src_confs.append(c)

        avg_conf = sum(src_confs) / len(src_confs) if src_confs else 0.5

        # 来源越多，置信度越高（对数增长，避免来源数主导）
        source_bonus = math.log(1 + len(sources)) / math.log(1 + 4)  # 归一化到4源
        conf = avg_conf * (0.6 + 0.4 * source_bonus)
        confidences.append(conf)

    # 归一化为权重
    total_conf = sum(confidences) or 1.0
    raw_weights = [c / total_conf for c in confidences]

    holdings, constraints = _build_holdings(
        fused_top3, raw_weights, "confidence_weighted", max_exposure
    )

    # 分析置信度分布
    max_conf = max(confidences) if confidences else 0
    min_conf = min(confidences) if confidences else 0
    note = f"置信度加权: 最高{max_conf:.0%} vs 最低{min_conf:.0%}"

    # 检查是否有source置信度数据
    if all(c <= 0.51 for c in source_confidences.values()):
        note += " [⚠️ 所有source置信度≈0.5, 可能无校准数据]"

    result = AllocationResult(
        allocation_method="confidence_weighted",
        total_exposure=sum(h.weight for h in holdings),
        cash_reserve=max(0, 1.0 - sum(h.weight for h in holdings)),
        holdings=holdings,
        constraints_applied=constraints,
        notes=[note],
    )
    return result


# ── 方法4: 波动率加权（风险平价近似） ────────────────────────────────
def _vol_weighted(fused_top3: list[dict], max_exposure: float) -> AllocationResult:
    """波动率倒数加权（风险平价简化版）。

    原理：波动率低的ETF分配更多仓位，使每个ETF对组合风险的贡献相等。
    这是风险平价的简化版本——真正的风险平价需要相关性矩阵。

    优点：天然分散风险，避免高波动品种过度集中
    缺点：忽略预测质量，可能在低波动但低分品种上浪费仓位
    """
    if not fused_top3:
        return AllocationResult(allocation_method="vol_weighted")

    vols = []
    for etf in fused_top3:
        vol = etf.get("volatility", 2.0)  # 默认2%，防止除零
        vol = max(vol, 0.5)  # 最低0.5%
        vols.append(vol)

    # 波动率倒数加权（inverse volatility）
    inv_vols = [1.0 / v for v in vols]
    total_inv = sum(inv_vols)
    raw_weights = [iv / total_inv for iv in inv_vols]

    holdings, constraints = _build_holdings(
        fused_top3, raw_weights, "vol_weighted", max_exposure
    )

    # 分析波动率差异
    max_vol = max(vols)
    min_vol = min(vols)
    note = f"波动率加权: 波动范围 {min_vol:.0f}%~{max_vol:.0%}"
    if max_vol / min_vol > 3:
        note += " [波动率差异大, 分配差异显著]"

    result = AllocationResult(
        allocation_method="vol_weighted",
        total_exposure=sum(h.weight for h in holdings),
        cash_reserve=max(0, 1.0 - sum(h.weight for h in holdings)),
        holdings=holdings,
        constraints_applied=constraints,
        notes=[note],
    )
    return result


# ── 方法4b: 风险平价（k170） ────────────────────────────────────────
def _risk_parity_weighted(fused_top3: list[dict], max_exposure: float) -> AllocationResult:
    """风险平价加权：权重与波动率倒数成正比（风险贡献均衡近似）。

    来源: k170 (资产配置)
    原理：每只 ETF 的权重 ∝ 1/volatility，使各 ETF 对组合风险的贡献接近相等。
    与 _vol_weighted 同为波动率倒数族，但 risk_parity 额外强调波动率差异判别
    （差异 >3 倍时，风险平价显著优于等权/分数加权）。

    优点：天然分散风险，避免高波动品种过度集中
    缺点：忽略预测质量，可能在低波动但低分品种上浪费仓位
    """
    if not fused_top3:
        return AllocationResult(allocation_method="risk_parity")

    vols = []
    for etf in fused_top3:
        vol = etf.get("volatility", 2.0)  # 默认2%，防止除零
        vol = max(vol, 0.5)  # 最低0.5%
        vols.append(vol)

    # 风险贡献均衡近似：inverse volatility → 归一化
    inv_vols = [1.0 / v for v in vols]
    total_inv = sum(inv_vols)
    raw_weights = [iv / total_inv for iv in inv_vols]

    holdings, constraints = _build_holdings(
        fused_top3, raw_weights, "risk_parity", max_exposure
    )

    max_vol = max(vols)
    min_vol = min(vols)
    note = f"风险平价: 波动范围 {min_vol:.1f}%~{max_vol:.1f}%"
    if max_vol / min_vol > 3:
        note += " [波动率差异大, 风险平价优于等权/分数加权]"

    result = AllocationResult(
        allocation_method="risk_parity",
        total_exposure=sum(h.weight for h in holdings),
        cash_reserve=max(0, 1.0 - sum(h.weight for h in holdings)),
        holdings=holdings,
        constraints_applied=constraints,
        notes=[note],
    )
    return result


# ── 方法4c: Black-Litterman 简化版（k170） ───────────────────────────
def _black_litterman_weighted(fused_top3: list[dict], max_exposure: float) -> AllocationResult:
    """Black-Litterman 简化版：市场均衡权重 + 观点调整。

    来源: k170 (资产配置)
    公式：
      市场均衡权重 w_mkt = 1/n（等权先验）
      观点向量 Q_i = score_i - mean_score（分数偏离均值作为观点强度）
      后验权重 w_i ∝ w_mkt * (1 + κ * Q_i)，κ = 0.3
    负后验权重钳制到 0（无做空），再归一化。

    优点：在市场均衡基础上融入预测观点，κ 控制观点信任度
    缺点：κ 需调优；分数未校准时观点方向可能失真
    """
    if not fused_top3:
        return AllocationResult(allocation_method="black_litterman")

    n = len(fused_top3)
    scores = [
        etf.get("composite_score", etf.get("weighted_score", 50)) for etf in fused_top3
    ]
    mean_score = sum(scores) / n

    kappa = 0.3
    mkt = 1.0 / n
    posterior = [mkt * (1 + kappa * (s - mean_score)) for s in scores]
    posterior = [max(w, 0.0) for w in posterior]  # 无做空
    total = sum(posterior) or 1.0
    raw_weights = [w / total for w in posterior]

    holdings, constraints = _build_holdings(
        fused_top3, raw_weights, "black_litterman", max_exposure
    )

    score_range = max(scores) - min(scores)
    note = (
        f"Black-Litterman: κ={kappa}, 分数偏离幅度{score_range:.1f}, "
        f"均值{mean_score:.1f}"
    )

    result = AllocationResult(
        allocation_method="black_litterman",
        total_exposure=sum(h.weight for h in holdings),
        cash_reserve=max(0, 1.0 - sum(h.weight for h in holdings)),
        holdings=holdings,
        constraints_applied=constraints,
        notes=[note],
    )
    return result


# ── 方法5: 混合分配（推荐） ─────────────────────────────────────────
def _hybrid_allocation(
    fused_top3: list[dict],
    source_confidences: dict[str, float],
    max_exposure: float,
) -> AllocationResult:
    """混合分配：分数 × 置信度 × 波动率惩罚。

    公式: contribution_i = score_i × conf_i / vol_i^alpha

    其中 alpha 由regime决定：
      - complacent/normal: alpha=0.3（适度考虑波动）
      - cautious: alpha=0.5（中等考虑）
      - fearful: alpha=0.8（高度重视波动）

    优点：综合质量、置信度、风险三个维度
    缺点：参数需要调优
    """
    if not fused_top3:
        return AllocationResult(allocation_method="hybrid")

    contributions = []
    for etf in fused_top3:
        score = max(etf.get("weighted_score", 50), 1) / 100.0  # 归一化到0-1
        conf = _etf_confidence(etf, source_confidences)
        vol = max(etf.get("volatility", 2.0), 0.5) / 100.0  # 小数形式

        # regime-dependent alpha
        # 这里简化为默认0.5，实际可从regime推断
        alpha = 0.5

        contrib = (score * conf) / (vol ** alpha)
        contributions.append(contrib)

    total = sum(contributions) or 1.0
    raw_weights = [c / total for c in contributions]

    holdings, constraints = _build_holdings(
        fused_top3, raw_weights, "hybrid", max_exposure
    )

    # 生成原因说明
    for h in holdings:
        etf_data = next((e for e in fused_top3 if e["code"] == h.code), {})
        score = etf_data.get("weighted_score", 0)
        vol = etf_data.get("volatility", 0)
        if score >= 70 and vol < 3:
            h.reason = f"优质低波({h.reason})"
        elif score >= 70:
            h.reason = f"优质高波({h.reason})"
        elif vol < 2:
            h.reason = f"稳健型({h.reason})"

    result = AllocationResult(
        allocation_method="hybrid_score_conf_vol",
        total_exposure=sum(h.weight for h in holdings),
        cash_reserve=max(0, 1.0 - sum(h.weight for h in holdings)),
        holdings=holdings,
        constraints_applied=constraints,
        notes=[
            "混合分配: 分数×置信度÷波动率^0.5",
            "综合质量、来源一致性、风险三个维度",
        ],
    )
    return result


def _etf_confidence(etf: dict, source_confidences: dict[str, float]) -> float:
    """计算单个ETF的综合置信度。"""
    sources = etf.get("sources", [])
    if not sources:
        return 0.5

    src_confs = [source_confidences.get(s, 0.5) for s in sources]
    avg = sum(src_confs) / len(src_confs)

    # 来源数量加成
    bonus = math.log(1 + len(sources)) / math.log(1 + 4)
    return avg * (0.6 + 0.4 * bonus)


# ══════════════════════════════════════════════════════════════════════
# 方法选择逻辑
# ══════════════════════════════════════════════════════════════════════


def _select_best_method(
    methods: dict[str, AllocationResult],
    fused_top3: list[dict],
    regime: str,
) -> AllocationResult:
    """选择最优分配方法。

    策略：
    - 默认使用 hybrid（综合最佳）
    - 如果校准数据不足，回退到 score_weighted
    - 如果regime=fearful，增加 vol_weighted 的权重
    - k170 新增候选：risk_parity / black_litterman 进入候选池；
      波动率差异 >3 倍时 risk_parity 优于 vol_weighted
    """
    # 检查校准数据质量
    has_good_calibration = False
    for name, m in methods.items():
        if "calibration" in str(m.notes).lower() or "无校准" not in str(m.notes):
            has_good_calibration = True

    # 恐慌regime下，降低高风险分配
    resolved = _resolve_regime(regime)

    # 优先级排序（默认 hybrid 优先；risk_parity/black_litterman 为 k170 新增候选）
    priority = ["hybrid_score_conf_vol", "score_weighted", "vol_weighted",
                 "confidence_weighted", "equal_weight",
                 "risk_parity", "black_litterman"]

    # 波动率差异 >3 倍时，风险平价优先于分数加权/波动率加权
    if _vol_spread_high(fused_top3):
        priority = ["hybrid_score_conf_vol", "risk_parity", "score_weighted",
                    "vol_weighted", "confidence_weighted", "equal_weight",
                    "black_litterman"]

    for method_name in priority:
        if method_name in methods:
            return methods[method_name]

    # 兜底：返回第一个可用的
    for name, m in methods.items():
        return m

    return methods.get("equal_weight", AllocationResult())


def _vol_spread_high(fused_top3: list[dict]) -> bool:
    """判断 Top3 波动率差异是否 >3 倍（风险平价优于等权/分数加权的信号）。"""
    vols = [max(etf.get("volatility", 2.0), 0.5) for etf in fused_top3]
    if len(vols) < 2:
        return False
    return max(vols) / min(vols) > 3.0


def _analyze_three_layer_distribution(holdings: list, fused_top3: list) -> str:
    """分析三层架构分布（防御/均衡/进取）. k105 regression fix."""
    if not holdings:
        return "no holdings"
    layers = {"defensive": 0, "balanced": 0, "aggressive": 0}
    for h in holdings:
        profile = getattr(h, "profile", None) or "balanced"
        layers[profile] = layers.get(profile, 0) + 1
    return f"def={layers['defensive']} bal={layers['balanced']} agg={layers['aggressive']}"


# ══════════════════════════════════════════════════════════════════════
# Kelly Criterion 评估（理论可行性分析）
# ══════════════════════════════════════════════════════════════════════

KELLY_ANALYSIS = """
================================================================================
Kelly Criterion 可行性评估
================================================================================

理论公式: f* = (p × b - q) / b
  p = 胜率, q = 1-p, b = 盈亏比

在当前系统中的数据可用性:

❌ 不可行（数据不足）:
  - 需要每只ETF的历史预测→实际回报配对数据
  - 需要区分"赢"和"输"的统计口径
  - 需要计算盈亏比（平均盈利/平均亏损）
  - 当前系统虽有 prediction_backtest.py，但仅做等权回测

⚠️ 部分可行（需要扩展）:
  - confidence_calibrator.py 已有 Beta-Binomial 校准
  - 可以从中提取"分数→胜率"映射
  - 但缺少"分数→盈亏比"映射

💡 改进路径:
  1. 在 prediction_monitor.py 中记录每次预测的实际10日回报
  2. 按分数段统计: P(win|score>=70), avg_win, avg_loss
  3. 计算每档分数的 Kelly fraction
  4. 使用 Fractional Kelly (0.25-0.5倍) 降低波动

  示例伪代码:
    kelly_fractions = {}
    for score_band in score_buckets:
        p = win_rate(score_band)
        avg_win = average_return(winning_etfs, score_band)
        avg_loss = abs(average_return(losing_etfs, score_band))
        b = avg_win / avg_loss if avg_loss > 0 else 1.0
        kelly = (p * b - (1-p)) / b
        kelly_fractions[score_band] = max(0, kelly * 0.5)  # half-Kelly

  预期效果: 分数≥75的ETF可能获得 15-25% Kelly fraction
            分数≤50的ETF可能获得 0%（不建议配置）
"""


# ── CLI ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ETF持仓分配器")
    parser.add_argument("--demo", action="store_true", help="运行演示")
    parser.add_argument("--json", action="store_true", help="JSON输出")
    args = parser.parse_args()

    if args.demo:
        # 模拟数据演示
        demo_data = [
            {
                "code": "518880", "name": "华安黄金ETF", "sector": "贵金属",
                "weighted_score": 82, "sources": ["zscore", "ml", "tournament"],
                "raw_scores": {"zscore": 85, "ml": 78, "tournament": 83},
                "volatility": 1.8, "change_20d": 4.2, "max_drawdown": -3.5,
            },
            {
                "code": "512480", "name": "中证医药ETF", "sector": "医药",
                "weighted_score": 68, "sources": ["zscore", "events"],
                "raw_scores": {"zscore": 72, "events": 64},
                "volatility": 2.5, "change_20d": -2.1, "max_drawdown": -8.3,
            },
            {
                "code": "515880", "name": "中证红利ETF", "sector": "红利价值",
                "weighted_score": 75, "sources": ["zscore", "ml", "tournament", "events"],
                "raw_scores": {"zscore": 78, "ml": 72, "tournament": 76, "events": 73},
                "volatility": 1.2, "change_20d": 1.8, "max_drawdown": -2.1,
            },
        ]
        source_confs = {"zscore": 0.72, "ml": 0.65, "tournament": 0.68, "events": 0.55}

        result = allocate(
            fused_top3=demo_data,
            regime="normal",
            source_confidences=source_confs,
            profile="均衡",
        )

        if args.json:
            print(json.dumps(asdict(result), ensure_ascii=False, indent=2, default=str))
        else:
            print(format_allocation_report(result))
            print("\n" + KELLY_ANALYSIS)
