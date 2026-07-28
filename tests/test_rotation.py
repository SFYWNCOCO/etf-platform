"""Tests for rotation.py - sector rotation detection."""
import pytest
from etf_platform.analysis.rotation import SECTORS, rotation_check, TREND_ICONS
pytestmark = [pytest.mark.unit]

class TestRotationConstants:
    def test_sectors_defined(self):
        assert len(SECTORS) >= 10
    def test_each_has_codes(self):
        for codes in SECTORS.values():
            assert len(codes) >= 1
            for c in codes:
                assert c.startswith(("sh","sz"))
    def test_trend_icons(self):
        exp = {"oversold","weak","neutral","strong","overbought","plunging","surging"}
        assert exp == set(TREND_ICONS.keys())

class TestRotationCheck:
    def test_empty_returns_empty(self):
        assert rotation_check({}) == {}
    def test_synthetic_data(self):
        prices = {"芯片ETF":{"price":1.5,"change_pct":2.0,"high":1.6,"low":1.4,"volume":1e7,"amount_yi":1.5}}
        r = rotation_check(prices)
        assert isinstance(r, dict)
    def test_multiple_sectors(self):
        prices = {"芯片ETF":{"price":1.5,"change_pct":2.0,"high":1.6,"low":1.4,"volume":1e7,"amount_yi":1.5},"消费ETF":{"price":2.0,"change_pct":-0.5,"high":2.1,"low":1.9,"volume":5e6,"amount_yi":1.0}}
        r = rotation_check(prices)
        assert len(r) >= 1
