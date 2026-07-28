"""Tests for political_risk.py and operations_research.py."""
import pytest


class TestPoliticalRisk:
    def test_calculate_political_risk_score_semiconductor(self):
        from etf_platform.analysis.political_risk import calculate_political_risk_score
        result = calculate_political_risk_score('半导体')
        assert 'composite_score' in result
        assert 0 <= result['composite_score'] <= 10
        assert result['risk_level'] in ['极低', '低', '中低', '中', '中高', '高', '极高']

    def test_calculate_political_risk_score_gold(self):
        from etf_platform.analysis.political_risk import calculate_political_risk_score
        result = calculate_political_risk_score('黄金')
        assert result['composite_score'] < 5.0  # Gold should have low political risk

    def test_calculate_political_risk_score_unknown(self):
        from etf_platform.analysis.political_risk import calculate_political_risk_score
        result = calculate_political_risk_score('未知行业')
        assert 'composite_score' in result

    def test_political_risk_premium_range(self):
        from etf_platform.analysis.political_risk import calculate_political_risk_score
        result = calculate_political_risk_score('半导体')
        assert 0 <= result['political_risk_premium'] <= 10


class TestOperationsResearch:
    def test_lp_portfolio_allocation_empty(self):
        from etf_platform.analysis.operations_research import lp_portfolio_allocation
        result = lp_portfolio_allocation({}, {}, {})
        assert result == {}

    def test_lp_portfolio_allocation_basic(self):
        from etf_platform.analysis.operations_research import lp_portfolio_allocation
        scores = {'a': 8.0, 'b': 6.0}
        sectors = {'a': '科技', 'b': '消费'}
        risk = {'a': 3.0, 'b': 2.0}
        result = lp_portfolio_allocation(scores, sectors, risk)
        assert result['num_positions'] == 2
        assert 0 < result['portfolio_risk'] < 10

    def test_ip_etf_selection(self):
        from etf_platform.analysis.operations_research import ip_etf_selection
        scores = {'a': 8.0, 'b': 6.0, 'c': 4.0}
        risk = {'a': 3.0, 'b': 2.0, 'c': 1.0}
        selected = ip_etf_selection(scores, risk, num_select=2)
        assert len(selected) == 2

    def test_mm1_queue_stable(self):
        from etf_platform.analysis.operations_research import mm1_queue_metrics
        metrics = mm1_queue_metrics(0.5, 1.0)
        assert metrics['stable'] is True
        assert metrics['utilization'] == 0.5

    def test_mm1_queue_unstable(self):
        from etf_platform.analysis.operations_research import mm1_queue_metrics
        metrics = mm1_queue_metrics(1.0, 0.5)
        assert metrics['stable'] is False

    def test_eoq_positive(self):
        from etf_platform.analysis.operations_research import eoq_optimal_order_quantity
        eoq = eoq_optimal_order_quantity(1000, 50, 5)
        assert eoq > 0

    def test_eoq_zero_demand(self):
        from etf_platform.analysis.operations_research import eoq_optimal_order_quantity
        eoq = eoq_optimal_order_quantity(0, 50, 5)
        assert eoq == 0

    def test_prisoner_dilemma(self):
        from etf_platform.analysis.operations_research import prisoner_dilemma_payoff
        coop, defect = prisoner_dilemma_payoff(0.5)
        assert coop >= 0
        assert defect >= 0
        assert defect > coop  # Defect dominates cooperate

    def test_etf_mdp_simulation(self):
        from etf_platform.analysis.operations_research import ETFMdp as ETF_MDP
        mdp = ETF_MDP()
        traj = mdp.simulate_horizon(3)
        assert len(traj) == 3
        for step in traj:
            assert 'regime' in step
            assert 'best_action' in step
            assert 'reward' in step

    def test_sector_rotation_strategies(self):
        from etf_platform.analysis.operations_research import SECTOR_ROTATION_STRATEGY
        assert 'recovery' in SECTOR_ROTATION_STRATEGY
        assert 'expansion' in SECTOR_ROTATION_STRATEGY
        assert 'slowdown' in SECTOR_ROTATION_STRATEGY
        assert 'recession' in SECTOR_ROTATION_STRATEGY
