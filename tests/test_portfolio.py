"""test_portfolio.py — 投资组合分配单元测试"""
import pytest

from etf_platform.optimize.portfolio import allocate, score_etf_for_portfolio


@pytest.mark.unit
class TestAllocateBasic:
    def test_basic_allocation(self):
        results = {
            "159995": {"name": "芯片ETF", "composite_score": 8.0, "supply_score": 7,
                       "capital_score": 8, "demand_score": 7, "signal_score": 7, "sector": "半导体"},
            "510300": {"name": "沪深300ETF", "composite_score": 7.0, "supply_score": 6,
                       "capital_score": 6, "demand_score": 7, "signal_score": 6, "sector": "宽基"},
        }
        alloc = allocate(results, budget=1000, profile="balanced", max_positions=2)
        assert len(alloc) > 0
        total = sum(a["amount"] for a in alloc)
        assert total <= 1000

    def test_empty_input(self):
        alloc = allocate({}, budget=1000, profile="balanced")
        assert alloc == []

    def test_amount_non_negative(self):
        results = {
            "159995": {"name": "芯片ETF", "composite_score": 8.0, "supply_score": 7,
                       "capital_score": 8, "demand_score": 7, "signal_score": 7, "sector": "半导体"},
            "510300": {"name": "沪深300ETF", "composite_score": 7.0, "supply_score": 6,
                       "capital_score": 6, "demand_score": 7, "signal_score": 6, "sector": "宽基"},
        }
        alloc = allocate(results, budget=1000, profile="balanced", max_positions=2)
        for a in alloc:
            assert a["amount"] >= 0

    def test_max_pct_cap(self):
        # 单只权重不超过 profile 的 max_single_pct
        results = {
            "159995": {"name": "芯片ETF", "composite_score": 10.0, "supply_score": 10,
                       "capital_score": 10, "demand_score": 10, "signal_score": 10, "sector": "半导体"},
            "510300": {"name": "沪深300ETF", "composite_score": 1.0, "supply_score": 1,
                       "capital_score": 1, "demand_score": 1, "signal_score": 1, "sector": "宽基"},
        }
        alloc = allocate(results, budget=1000, profile="balanced", max_positions=2)
        # balanced profile max_single_pct = 0.30
        for a in alloc:
            assert a["weight_pct"] <= 30.5  # 允许浮点误差

    def test_softmax_vs_cvar_method(self):
        results = {
            "159995": {"name": "芯片ETF", "composite_score": 8.0, "supply_score": 7,
                       "capital_score": 8, "demand_score": 7, "signal_score": 7, "sector": "半导体"},
            "510300": {"name": "沪深300ETF", "composite_score": 7.0, "supply_score": 6,
                       "capital_score": 6, "demand_score": 7, "signal_score": 6, "sector": "宽基"},
        }
        alloc_softmax = allocate(results, budget=1000, profile="balanced", method="softmax")
        alloc_cvar = allocate(results, budget=1000, profile="balanced", method="cvar")
        assert len(alloc_softmax) > 0
        assert len(alloc_cvar) > 0


@pytest.mark.unit
class TestScoreEtfForPortfolio:
    def test_returns_float(self):
        ar = {"composite_score": 7.0, "supply_score": 7, "capital_score": 7,
              "demand_score": 7, "signal_score": 7, "sector": "半导体", "name": "芯片ETF"}
        score = score_etf_for_portfolio("159995", ar, profile="balanced")
        assert isinstance(score, float)
        assert score >= 0
