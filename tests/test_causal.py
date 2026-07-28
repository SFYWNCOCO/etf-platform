"""Tests for causal.py - 6-layer causal impact engine."""
import pytest
from etf_platform.analysis.causal import CausalEngine
pytestmark = [pytest.mark.unit]

class TestCausalEngineInit:
    def test_instantiates(self):
        assert CausalEngine() is not None
    def test_has_scan_all(self):
        assert hasattr(CausalEngine(), "scan_all")

class TestCausalEngineScan:
    def test_scan_all_returns_dict(self):
        r = CausalEngine().scan_all()
        assert isinstance(r, dict)
    def test_results_have_impact(self):
        for code, data in CausalEngine().scan_all().items():
            assert "total_impact" in data
            assert isinstance(data["total_impact"], (int,float))
    def test_impact_reasonable(self):
        for data in CausalEngine().scan_all().values():
            assert abs(data["total_impact"]) < 1.0
