"""KB重构回归测试 — 覆盖 k190/k295/k189/k169/k170/k168 新模块。"""

import math

import numpy as np
import pytest


# ── k190 hurst_regime ──────────────────────────────────────────────
def test_hurst_dfa_random_walk():
    from etf_platform.analysis.hurst_regime import hurst_dfa
    np.random.seed(42)
    rw = list(np.cumsum(np.random.randn(300)))
    H, r2 = hurst_dfa(rw)
    # 输入是价格序列（积分序列）时 H 会偏大；这里仅验证能返回有限值且 R² 有效
    assert math.isfinite(H)
    assert r2 >= 0.0


def test_hurst_dfa_constant_returns_zero():
    from etf_platform.analysis.hurst_regime import hurst_dfa
    H, r2 = hurst_dfa([1.0] * 300)
    assert H == 0.5
    assert r2 == 0.0


def test_hurst_dfa_short_returns_default():
    from etf_platform.analysis.hurst_regime import hurst_dfa
    H, r2 = hurst_dfa([1.0] * 50)
    assert H == 0.5
    assert r2 == 0.0


def test_hurst_classify_regime():
    from etf_platform.analysis.hurst_regime import classify_regime
    assert classify_regime(0.62, 0.01)["regime"] == "trend_strong"
    assert classify_regime(0.40, 0.01)["regime"] == "mean_reversion"
    assert classify_regime(0.50, 0.03)["regime"] == "random_high_vol"


# ── k295 style_rotation ────────────────────────────────────────────
def test_style_scores_in_range():
    from etf_platform.analysis.style_rotation import calculate_style_scores
    scores = calculate_style_scores(
        {"货币增速": 0.6, "信用增速": 0.5, "GDP增速": 0.4},
        {"估值分位": 0.7, "拥挤度": 0.3, "动量": 0.8},
    )
    assert len(scores) == 4
    for style, v in scores.items():
        assert 0.0 <= v["composite"] <= 1.0


def test_style_scores_default_neutral():
    from etf_platform.analysis.style_rotation import calculate_style_scores
    scores = calculate_style_scores({}, {})
    for v in scores.values():
        assert v["composite"] == 0.5


def test_style_etfs_exists():
    from etf_platform.analysis.style_rotation import STYLE_ETFS
    assert len(STYLE_ETFS) == 4
    assert "融资成长" in STYLE_ETFS


# ── k189 cross_asset_correlation ───────────────────────────────────
def test_correlation_matrix_positive():
    from etf_platform.analysis.cross_asset_correlation import correlation_matrix
    np.random.seed(1)
    base = np.random.randn(100)
    a = list(base * 0.9 + np.random.randn(100) * 0.1)
    b = list(base * 0.9 + np.random.randn(100) * 0.1)
    corr, meta = correlation_matrix({"A": a, "B": b})
    assert corr[("A", "B")] > 0.5


def test_correlation_matrix_short_returns_empty():
    from etf_platform.analysis.cross_asset_correlation import correlation_matrix
    corr, meta = correlation_matrix({"A": [1.0, 2.0], "B": [1.0, 2.0]})
    assert corr == {}
    assert meta.get("reason") == "series_too_short"


def test_diversification_failure_high_corr():
    from etf_platform.analysis.cross_asset_correlation import (
        correlation_matrix,
        detect_diversification_failure,
    )
    np.random.seed(2)
    base = np.random.randn(100)
    returns = {
        "A": list(base * 0.9 + np.random.randn(100) * 0.1),
        "B": list(base * 0.9 + np.random.randn(100) * 0.1),
        "C": list(base * 0.9 + np.random.randn(100) * 0.1),
    }
    corr, _ = correlation_matrix(returns)
    fail = detect_diversification_failure(corr, threshold=0.7)
    assert fail["failure"] is True


def test_correlation_serializable():
    from etf_platform.analysis.cross_asset_correlation import correlation_matrix_serializable
    import json
    np.random.seed(3)
    r = correlation_matrix_serializable(
        {"A": list(np.random.randn(50)), "B": list(np.random.randn(50))}
    )
    # 不抛 TypeError
    json.dumps(r)


# ── k169 performance_metrics ───────────────────────────────────────
def test_performance_metrics_known_values():
    from etf_platform.analysis.performance_metrics import max_drawdown, win_rate, summary_metrics
    prices = [100, 110, 99, 108.9]
    assert max_drawdown(prices) == pytest.approx(-0.1, abs=1e-6)
    returns = [0.1, -0.1, 0.1]
    assert win_rate(returns) == pytest.approx(2 / 3, abs=1e-6)
    sm = summary_metrics(prices)
    assert sm["total_return"] == pytest.approx(0.089, abs=1e-3)


def test_sharpe_zero_std():
    from etf_platform.analysis.performance_metrics import sharpe_ratio
    assert sharpe_ratio([0.0, 0.0, 0.0]) == 0.0


# ── k170 position_allocator ────────────────────────────────────────
def _fused_top3():
    return [
        {"code": "512890", "name": "红利低波", "weighted_score": 85, "volatility": 1.5,
         "confidence": 0.8, "sector": "红利低波"},
        {"code": "159915", "name": "创业板", "weighted_score": 72, "volatility": 3.0,
         "confidence": 0.7, "sector": "成长"},
        {"code": "512100", "name": "中证1000", "weighted_score": 65, "volatility": 2.5,
         "confidence": 0.6, "sector": "小微盘"},
    ]


def test_allocator_risk_parity():
    from etf_platform.decision.position_allocator import allocate
    r = allocate(_fused_top3(), method="risk_parity", regime="normal")
    total = sum(h.weight for h in r.holdings)
    assert total == pytest.approx(0.9, abs=0.05)
    # 低波动ETF权重应高于高波动
    weights = {h.code: h.weight for h in r.holdings}
    assert weights["512890"] > weights["159915"]


def test_allocator_black_litterman():
    from etf_platform.decision.position_allocator import allocate
    r = allocate(_fused_top3(), method="black_litterman", regime="normal")
    weights = {h.code: h.weight for h in r.holdings}
    # 高分ETF权重应不低于低分（BL观点调整）
    assert weights.get("512890", 0) >= weights.get("512100", 0)


def test_vol_weighted_note_percent_format():
    """回归：note 的 max_vol 曾用 :.0% 把 30.5（%）显示成 3050%。"""
    from etf_platform.decision.position_allocator import _vol_weighted
    fused = [
        {"code": "510300", "name": "沪深300", "volatility": 20.0, "weighted_score": 80, "sector": "宽基"},
        {"code": "510500", "name": "中证500", "volatility": 30.5, "weighted_score": 60, "sector": "宽基"},
    ]
    r = _vol_weighted(fused, max_exposure=1.0)
    note = r.notes[0]
    assert "30%" in note
    assert "3050%" not in note


# ── k190 hurst → L33 校准 ──────────────────────────────────────────
def test_l33_hurst_calibration():
    from etf_platform.layers.l33_regime_factor import score_l33_layer
    base = score_l33_layer("半导体", qvix_regime="normal")
    calib = score_l33_layer("半导体", qvix_regime="normal", hurst=0.60)
    # 趋势制度(H>0.55)在震荡市应加分0.3
    assert calib["score"] - base["score"] == pytest.approx(0.3, abs=0.05)
    assert "hurst" in calib["detail"]


# ── k189 risk_manager diversification ─────────────────────────────
def test_risk_manager_diversification_high():
    from etf_platform.decision.risk_manager import check_diversification
    np.random.seed(4)
    base = np.random.randn(100)
    returns = {
        "A": list(base * 0.9 + np.random.randn(100) * 0.1),
        "B": list(base * 0.9 + np.random.randn(100) * 0.1),
    }
    holdings = [{"code": "A", "weight": 0.3, "sector": "x"},
                {"code": "B", "weight": 0.3, "sector": "y"}]
    r = check_diversification(holdings, returns)
    assert r["checked"] is True
    assert r["diversification_failure"] is True


def test_risk_manager_diversification_insufficient():
    from etf_platform.decision.risk_manager import check_diversification
    holdings = [{"code": "A", "weight": 0.3, "sector": "x"}]
    r = check_diversification(holdings, {})
    assert r["checked"] is False


# ── k168 kline/technical_indicators ────────────────────────────────
def test_kline_snapshot_has_tech_fields():
    import dataclasses
    from etf_platform.data.kline import TrendSnapshot
    fields = {f.name for f in dataclasses.fields(TrendSnapshot)}
    assert {"rsi14", "macd_hist", "ma20", "ma60"} <= fields


def test_technical_indicators_rsi_range():
    from etf_platform.analysis.technical_indicators import rsi
    vals = rsi([100 + i for i in range(40)])
    valid = [v for v in vals if v is not None]
    assert valid
    assert all(0 <= v <= 100 for v in valid)


def test_technical_indicators_sma_padding():
    from etf_platform.analysis.technical_indicators import sma
    out = sma([1.0, 2.0, 3.0, 4.0], period=3)
    assert out[0] is None and out[1] is None
    assert out[2] == pytest.approx(2.0)


# ── KB registry ────────────────────────────────────────────────────
def test_kb_registry_builtin_seed():
    from etf_platform.kb.registry import get_registry
    r = get_registry()
    audit = r.audit("src")
    assert audit["total_registered"] >= 64
    assert r.get("k295") is not None


def test_kb_audit_no_fake_integration():
    from etf_platform.kb.registry import get_registry
    r = get_registry()
    audit = r.audit("src")
    assert audit["fake_integration"] == []
