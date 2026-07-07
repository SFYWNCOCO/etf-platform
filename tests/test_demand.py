"""Tests for demand.py - L10+L11 demand layer scoring."""
import pytest
from etf_platform.analysis.demand import CONSUMER_SECTORS, DEMAND_CLIMATE, SECTOR_DEMAND_RISK, B2B_DEMAND_CLIMATE, B2B_SECTOR_RISK, DATA_LAST_UPDATED
pytestmark = [pytest.mark.unit]

class TestDemandConstants:
    def test_consumer_count(self):
        assert len(CONSUMER_SECTORS) >= 8
    def test_demand_climate_has_default(self):
        assert "default" in DEMAND_CLIMATE
    def test_data_freshness(self):
        assert DATA_LAST_UPDATED == "2026-07-07"

class TestB2BDemand:
    def test_covers_major(self):
        for s in {"半导体","AI/科技","新能源","军工","金融","宽基"}:
            assert s in B2B_DEMAND_CLIMATE
    def test_scores_in_range(self):
        for data in B2B_DEMAND_CLIMATE.values():
            assert 1 <= data.get("score",0) <= 10
    def test_risk_covers_major(self):
        for s in {"半导体","AI/科技","新能源","军工","金融","宽基"}:
            assert s in B2B_SECTOR_RISK
    def test_risk_scores_in_range(self):
        for data in B2B_SECTOR_RISK.values():
            assert 1 <= data.get("score",0) <= 10

class TestCrossSectors:
    def test_combined_coverage(self):
        total = len(SECTOR_DEMAND_RISK) + len(B2B_SECTOR_RISK)
        assert total >= 30
