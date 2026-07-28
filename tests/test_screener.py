"""Tests for screener.py core functions — v5.6."""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from etf_platform.decision.screener import (
    _resolve_profile,
    _detect_dead_layers,
    _compute_auto_weights,
    _compute_composite,
    _generate_reason,
    _normalize_batch,
    LAYER_CATEGORIES,
    EXCLUDED_LAYERS,
    NON_INVESTMENT_SECTORS,
)


class TestResolveProfile:
    def test_cn_direct(self):
        assert _resolve_profile("保守") == "保守"
        assert _resolve_profile("均衡") == "均衡"

    def test_en_aliases(self):
        assert _resolve_profile("conservative") == "保守"
        assert _resolve_profile("balanced") == "均衡"
        assert _resolve_profile("aggressive") == "进取"

    def test_unknown_passthrough(self):
        assert _resolve_profile("unknown") == "unknown"


class TestDetectDeadLayers:
    def test_normal_variance_not_dead(self):
        results = [
            {"layer_scores": {"L3_Material": 5.0, "L4_SupplyChain": 8.0}},
            {"layer_scores": {"L3_Material": 7.0, "L4_SupplyChain": 3.0}},
        ]
        dead = _detect_dead_layers(results)
        assert "L3_Material" not in dead
        assert "L4_SupplyChain" not in dead

    def test_zero_variance_is_dead(self):
        results = [
            {"layer_scores": {"L3_Material": 5.0}},
            {"layer_scores": {"L3_Material": 5.0}},
        ]
        dead = _detect_dead_layers(results)
        assert "L3_Material" in dead

    def test_low_variance_is_dead(self):
        results = [
            {"layer_scores": {"L3_Material": 5.0}},
            {"layer_scores": {"L3_Material": 5.4}},
        ]
        dead = _detect_dead_layers(results)
        assert "L3_Material" in dead

    def test_single_sample_is_dead(self):
        results = [{"layer_scores": {"L3_Material": 5.0}}]
        dead = _detect_dead_layers(results)
        assert "L3_Material" in dead

    def test_excluded_layers_ignored(self):
        results = [
            {"layer_scores": {"L1_ETF": 3.0}},
            {"layer_scores": {"L1_ETF": 7.0}},
        ]
        dead = _detect_dead_layers(results)
        assert "L1_ETF" not in dead


class TestComputeAutoWeights:
    @pytest.fixture
    def sample_results(self):
        results = []
        for i in range(10):
            scores = {
                "L3_Material": 3.0 + i * 0.5,
                "L4_SupplyChain": 7.0 - i * 0.3,
                "L5_Tech": 5.0 + (i % 3) * 2,
                "L8_CapitalFlow": 4.0 + i * 0.4,
                "L10_Demand": 6.0 + (i % 5),
                "L11_SectorRisk": 5.0 + i * 0.1,
            }
            results.append({"layer_scores": scores})
        return results

    def test_returns_dict(self, sample_results):
        weights = _compute_auto_weights(sample_results)
        assert isinstance(weights, dict)

    def test_weights_sum_to_one(self, sample_results):
        weights = _compute_auto_weights(sample_results)
        total = sum(weights.values())
        assert abs(total - 1.0) < 0.01, f"Weights sum to {total}, expected 1.0"

    def test_higher_variance_gets_higher_weight(self, sample_results):
        weights = _compute_auto_weights(sample_results)
        w_l3 = weights.get("L3_Material", 0)
        w_l11 = weights.get("L11_SectorRisk", 0)
        assert w_l3 > w_l11, f"L3={w_l3} should > L11={w_l11} (higher variance)"

    def test_dead_layers_excluded(self, sample_results):
        dead = {"L3_Material"}
        weights = _compute_auto_weights(sample_results, dead_layers=dead)
        assert "L3_Material" not in weights

    def test_profile_affects_weights(self, sample_results):
        w_conservative = _compute_auto_weights(sample_results, profile="保守")
        w_aggressive = _compute_auto_weights(sample_results, profile="激进")
        supply = LAYER_CATEGORIES["供给侧"]
        cons_supply = sum(w_conservative.get(l, 0) for l in supply)
        agg_supply = sum(w_aggressive.get(l, 0) for l in supply)
        assert cons_supply > agg_supply


class TestComputeComposite:
    def test_basic_weighted_average(self):
        scores = {"L3_Material": 8.0, "L10_Demand": 4.0}
        weights = {"L3_Material": 0.5, "L10_Demand": 0.5}
        result = _compute_composite(scores, weights)
        assert result == 6.0

    def test_missing_layer_ignored(self):
        scores = {"L3_Material": 8.0}
        weights = {"L3_Material": 0.5, "L10_Demand": 0.5}
        result = _compute_composite(scores, weights)
        assert result == 8.0

    def test_oversold_trend_penalty(self):
        scores = {"L3_Material": 8.0}
        weights = {"L3_Material": 1.0}
        trend = {"signal": "oversold", "max_drawdown": -5}
        result = _compute_composite(scores, weights, trend)
        assert result < 8.0

    def test_plunging_heavier_than_oversold(self):
        scores = {"L3_Material": 8.0}
        weights = {"L3_Material": 1.0}
        r_plunge = _compute_composite(scores, weights, {"signal": "plunging", "max_drawdown": -5})
        r_oversold = _compute_composite(scores, weights, {"signal": "oversold", "max_drawdown": -5})
        assert r_plunge < r_oversold

    def test_deep_drawdown_more_penalty(self):
        scores = {"L3_Material": 8.0}
        weights = {"L3_Material": 1.0}
        r_mild = _compute_composite(scores, weights, {"signal": "neutral", "max_drawdown": -8})
        r_deep = _compute_composite(scores, weights, {"signal": "neutral", "max_drawdown": -30})
        assert r_deep < r_mild

    def test_no_trend_no_penalty(self):
        scores = {"L3_Material": 8.0}
        weights = {"L3_Material": 1.0}
        result = _compute_composite(scores, weights)
        assert result == 8.0


class TestGenerateReason:
    def test_includes_sector(self):
        result = {"layer_scores": {}, "name": "芯片ETF", "sector": "半导体"}
        reason = _generate_reason(result)
        assert "半导体" in reason

    def test_includes_trend_when_available(self):
        result = {"layer_scores": {}, "name": "芯片ETF", "sector": "半导体"}
        trend = {"signal": "strong", "change_20d": 5.2, "position_pct": 75, "max_drawdown": -3}
        reason = _generate_reason(result, trend)
        assert "5.2" in reason

    def test_includes_strengths(self):
        result = {"layer_scores": {"L3_Material": 8.0, "L10_Demand": 7.5, "L4_SupplyChain": 3.0}, "name": "T", "sector": "X"}
        reason = _generate_reason(result)
        assert "优势" in reason or "需求旺盛" in reason

    def test_includes_weaknesses(self):
        result = {"layer_scores": {"L3_Material": 2.0, "L4_SupplyChain": 3.0, "L10_Demand": 8.0}, "name": "T", "sector": "X"}
        reason = _generate_reason(result)
        assert "短板" in reason


class TestNormalizeBatch:
    def test_minmax_normalization(self):
        results = [
            {"layer_scores": {"L3_Material": 2.0}},
            {"layer_scores": {"L3_Material": 8.0}},
        ]
        _normalize_batch(results)
        vals = [r["layer_scores"]["L3_Material"] for r in results]
        assert abs(min(vals) - 0.0) < 0.1
        assert abs(max(vals) - 10.0) < 0.1

    def test_no_variance_stays_midpoint(self):
        results = [
            {"layer_scores": {"L3_Material": 5.0}},
            {"layer_scores": {"L3_Material": 5.0}},
        ]
        _normalize_batch(results)
        for r in results:
            assert r["layer_scores"]["L3_Material"] == 5.0

    def test_missing_layer_defaults_to_5(self):
        # Missing layers default to 5.0, THEN normalization happens.
        # With values [3.0, 5.0], minmax maps 3.0->0, 5.0->10.
        results = [
            {"layer_scores": {"L3_Material": 3.0}},
            {"layer_scores": {}},
        ]
        _normalize_batch(results)
        # After normalization: 5.0 becomes 10.0 (it's the max in [3.0, 5.0])
        assert results[1]["layer_scores"]["L3_Material"] == 10.0

    def test_default_then_normalize(self):
        # Verify that default=5.0 is inserted BEFORE normalization
        results = [
            {"layer_scores": {"L3_Material": 5.0}},
            {"layer_scores": {}},
        ]
        _normalize_batch(results)
        # Both are 5.0, so no variance: stays at 5.0 midpoint
        assert results[1]["layer_scores"]["L3_Material"] == 5.0


class TestNonInvestmentFilter:
    def test_money_fund_excluded(self):
        assert "货币基金" in NON_INVESTMENT_SECTORS

    def test_bonds_excluded(self):
        assert "利率债" in NON_INVESTMENT_SECTORS
        assert "信用债" in NON_INVESTMENT_SECTORS

    def test_equity_not_excluded(self):
        assert "半导体" not in NON_INVESTMENT_SECTORS