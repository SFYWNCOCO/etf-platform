"""Tests for l14_stoic_risk.py and l18_var_risk.py — 核心风控模块.

被测模块:
- etf_platform.layers.l14_stoic_risk: 斯多葛风险哲学层 (可控性/压力测试/综合评分)
- etf_platform.layers.l18_var_risk: VaR风控层 (波动率基准/VaR计算/综合得分)
"""
import pytest

from etf_platform.layers.l14_stoic_risk import (
    CONTROLLABILITY_SCORES,
    get_controllability,
    get_stress_test,
    score_stoic_layer,
)
from etf_platform.layers.l18_var_risk import (
    VOLATILITY_BENCHMARK,
    calculate_var,
    calculate_var_score,
    get_volatility_benchmark,
)

pytestmark = [pytest.mark.unit]


class TestControllability:
    def test_controllability_known_sector(self, etf_sector_chip):
        """已知行业返回正确分数。"""
        score = get_controllability(etf_sector_chip)
        assert score == CONTROLLABILITY_SCORES["半导体"]
        assert 0 <= score <= 10

    def test_controllability_unknown_sector(self):
        """未知行业返回默认5.0。"""
        score = get_controllability("完全不存在的行业XYZ123")
        assert score == 5.0


class TestStressTest:
    def test_stress_test_has_scenarios(self, etf_sector_chip):
        """压力测试含所有情景。"""
        result = get_stress_test(etf_sector_chip)
        assert isinstance(result, dict)
        assert "scenarios" in result
        assert "avg_drawdown" in result
        assert "tail_risk" in result
        # 应包含全部 3 个压力情景
        expected_scenarios = {"极端情景_30pct", "流动性危机", "政策冲击"}
        assert set(result["scenarios"].keys()) == expected_scenarios
        # 所有情景值都是负数（下跌）
        for scenario, val in result["scenarios"].items():
            assert val < 0, f"{scenario} 应为负值, got {val}"
        # avg_drawdown 应为负
        assert result["avg_drawdown"] < 0
        # tail_risk 在 [0, 10]
        assert 0 <= result["tail_risk"] <= 10


class TestVolatilityBenchmark:
    def test_get_volatility_benchmark_known(self, etf_sector_chip):
        """已知行业返回正确波动率基准。"""
        bench = get_volatility_benchmark(etf_sector_chip)
        assert isinstance(bench, dict)
        assert "annual_vol" in bench
        assert "var_95" in bench
        assert "var_99" in bench
        assert "desc" in bench
        # 半导体映射到 VOLATILITY_BENCHMARK["半导体"]
        assert bench == VOLATILITY_BENCHMARK["半导体"]

    def test_get_volatility_benchmark_unknown(self):
        """未知行业回退到宽基基准。"""
        bench = get_volatility_benchmark("不存在的行业XYZ")
        assert bench == VOLATILITY_BENCHMARK["宽基"]


class TestVaRCalculation:
    def test_var_calculation(self, etf_sector_chip):
        """VaR 计算正确 (var_1d < 0, 时间缩放合理)。"""
        result = calculate_var(etf_sector_chip, confidence=0.95)
        assert isinstance(result, dict)
        # VaR 应为负值
        assert result["var_1d"] < 0, "var_1d 应为负值"
        assert result["var_5d"] < 0
        assert result["var_20d"] < 0
        # 时间缩放: |var_5d| = |var_1d| * sqrt(5) > |var_1d|
        assert abs(result["var_5d"]) > abs(result["var_1d"])
        assert abs(result["var_20d"]) > abs(result["var_5d"])
        # 压力测试固定值
        assert result["stress_mild"] == -5.0
        assert result["stress_severe"] == -10.0
        assert result["stress_tail"] == -20.0
        # 组合影响 (30% 仓位)
        assert result["portfolio_impact"]["mild"] == round(-0.05 * 0.30 * 100, 2)
        assert result["confidence"] == 0.95

    def test_var_calculation_confidence_99(self, etf_sector_chip):
        """99% 置信度 VaR 应比 95% 更严格 (绝对值更大)。"""
        r95 = calculate_var(etf_sector_chip, confidence=0.95)
        r99 = calculate_var(etf_sector_chip, confidence=0.99)
        assert abs(r99["var_1d"]) > abs(r95["var_1d"])


class TestVaRScore:
    def test_var_score_range(self, etf_sector_chip, etf_code_chip):
        """VaR 得分在 1-10 范围内。"""
        result = calculate_var_score(etf_sector_chip, etf_code=etf_code_chip)
        assert isinstance(result, dict)
        assert "score" in result
        assert "var_data" in result
        assert "risk_level" in result
        assert "jitter" in result
        assert 1.0 <= result["score"] <= 10.0
        # jitter 范围 [-0.9, +0.9]
        assert -0.9 <= result["jitter"] <= 0.9

    def test_var_risk_level_thresholds(self):
        """risk_level 阈值正确 (vol<20→low, 20-30→medium, 30-40→high, >40→extreme)。"""
        # low: 货币基金 vol=3%
        r_low = calculate_var_score("货币基金")
        assert r_low["risk_level"] == "low"
        assert r_low["var_data"]["annual_vol"] < 20

        # medium: 沪深300 vol=23%
        r_med = calculate_var_score("沪深300")
        assert r_med["risk_level"] == "medium"
        assert 20 <= r_med["var_data"]["annual_vol"] < 30

        # high: 半导体 vol=35%
        r_high = calculate_var_score("半导体")
        assert r_high["risk_level"] == "high"
        assert 30 <= r_high["var_data"]["annual_vol"] < 40

        # extreme: 券商 vol=42%
        r_ext = calculate_var_score("券商")
        assert r_ext["risk_level"] == "extreme"
        assert r_ext["var_data"]["annual_vol"] >= 40


class TestStoicScoreJitter:
    def test_stoic_score_with_code_jitter(self, etf_sector_chip):
        """相同行业不同ETF代码有不同jitter (v8.17 引入)。"""
        codes = ["159995", "510300", "510050", "512880", "159338"]
        scores = [
            score_stoic_layer(etf_sector_chip, risk_level=0.7, etf_code=code)["score"]
            for code in codes
        ]
        # 至少有 2 个不同的得分 (说明 code-based jitter 起作用)
        unique_scores = set(scores)
        assert len(unique_scores) >= 2, (
            f"相同行业不同ETF代码应有不同得分, got scores={scores}"
        )
        # 所有得分在 [1, 10] 范围内
        for s in scores:
            assert 1.0 <= s <= 10.0

    def test_stoic_score_structure(self, etf_sector_chip, etf_code_chip):
        """score_stoic_layer 返回结构完整。"""
        result = score_stoic_layer(
            etf_sector_chip, risk_level=0.5, etf_code=etf_code_chip
        )
        assert isinstance(result, dict)
        expected_keys = {
            "score",
            "controllability",
            "tail_risk_score",
            "avg_drawdown",
            "tail_risk",
            "scenarios",
        }
        assert set(result.keys()) == expected_keys
        assert 1.0 <= result["score"] <= 10.0
        assert 0 <= result["controllability"] <= 10
        assert 0 <= result["tail_risk_score"] <= 10


# ─────────────────────────────────────────────────────────────────────────
# decision/risk_manager.py（持仓跟踪/止损/组合回撤/分散化）— 审计补审转测试
# ─────────────────────────────────────────────────────────────────────────

def _pos(pnl, price=10.0, entry=10.0, shares=1, code="512480", name="半导体ETF"):
    return {
        code: {
            "name": name, "entry_price": entry, "current_price": price,
            "pnl_pct": pnl, "shares": shares, "entry_date": "2026-08-01",
        }
    }


def _flags(positions, peak=None):
    from etf_platform.decision import risk_manager as rm
    data = {"positions": positions, "history": []}
    if peak is not None:
        data["portfolio_peak"] = peak
    rm._load_positions = lambda: data
    return rm.check_risk_flags()


class TestPositionStopLoss:
    def test_no_positions_empty_flags(self):
        f = _flags({})
        assert f["stop_loss_hit"] == []
        assert not f["portfolio_dd_critical"]
        assert not f["portfolio_dd_warning"]

    def test_stop_loss_triggers_at_minus_15(self):
        f = _flags(_pos(pnl=-16.0))
        assert len(f["stop_loss_hit"]) == 1
        assert f["stop_loss_hit"][0]["code"] == "512480"
        assert "止损触发" in f["message"]

    def test_stop_loss_boundary_exact(self):
        """-15.0% 整值触发；-14.9% 不触发。"""
        assert len(_flags(_pos(pnl=-15.0))["stop_loss_hit"]) == 1
        assert _flags(_pos(pnl=-14.9))["stop_loss_hit"] == []


class TestPortfolioDrawdown:
    def test_dd_warning_at_minus_10(self):
        # price/entry = 8.8/10 = 0.88 → DD=-12% → warning（未到临界）
        f = _flags(_pos(pnl=-12.0, price=8.8), peak=1.0)
        assert f["portfolio_dd_warning"]
        assert not f["portfolio_dd_critical"]

    def test_dd_critical_at_minus_20(self):
        f = _flags(_pos(pnl=-25.0, price=7.5), peak=1.0)
        assert f["portfolio_dd_critical"]

    def test_dd_and_stop_loss_messages_both_visible(self):
        """止损与组合回撤临界同时触发 → 消息追加而非覆盖（DD 告警不被吞）。"""
        f = _flags(_pos(pnl=-25.0, price=7.5), peak=1.0)
        assert "清仓" in f["message"], "组合回撤清仓建议被吞"
        assert "止损触发" in f["message"], "止损告警缺失"

    def test_missing_peak_guarded(self):
        """旧 positions.json 缺 portfolio_peak → 兜底 1.0（不崩、不误报临界）。"""
        f = _flags(_pos(pnl=-8.0, price=9.2))
        assert not f["portfolio_dd_critical"]


class TestDiversificationGuard:
    def test_insufficient_returns(self):
        from etf_platform.decision import risk_manager as rm
        out = rm.check_diversification(
            [{"code": "a", "weight": 1}, {"code": "b", "weight": 1}],
            returns_by_code={},
        )
        assert out["checked"] is False
        assert out["reason"] == "insufficient_data"

    def test_single_holding_insufficient(self):
        from etf_platform.decision import risk_manager as rm
        out = rm.check_diversification(
            [{"code": "a", "weight": 1}],
            returns_by_code={"a": [0.01] * 30},
        )
        assert out["checked"] is False
        assert out["reason"] == "insufficient_data"

    def test_high_correlation_warns(self, monkeypatch):
        from etf_platform.decision import risk_manager as rm
        monkeypatch.setattr(
            "etf_platform.analysis.cross_asset_correlation.correlation_matrix",
            lambda *a, **k: ({"a_b": 0.95}, {}),
        )
        monkeypatch.setattr(
            "etf_platform.analysis.cross_asset_correlation.detect_diversification_failure",
            lambda *a, **k: {"failure": True, "high_ratio": 1.0, "avg_corr": 0.95},
        )
        out = rm.check_diversification(
            [{"code": "a", "weight": 1}, {"code": "b", "weight": 1}],
            returns_by_code={"a": [0.01] * 30, "b": [0.01] * 30},
        )
        assert out["checked"] is True
        assert out["diversification_failure"] is True
        assert "分散化失效" in out["warning"]
