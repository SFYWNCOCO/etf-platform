"""test_backtest.py — 回测引擎单元测试"""
from unittest.mock import patch, MagicMock
import pytest

from etf_platform.optimize.backtest import (
    _event_accuracy, run_backtest, COST_BPS, TRANSACTION_COST,
)


@pytest.mark.unit
class TestEventAccuracyBasic:
    def test_basic_correct_prediction(self):
        # 利好事件,价格从 10 涨到 11,应判 correct=True(扣除成本后仍正)
        # window_days=2 需要 len(recs) >= 4,提供 4 条数据
        # 事件日 2026-01-15 无数据点,pre 取 01-13(10.2),post 取 01-20(11.0)
        event = {"d": "2026-01-15", "dir": "利好", "c": ["159995"], "n": "test_event", "h": 30}
        hist = {"159995": [
            {"date": "2026-01-10", "close": 10.0},
            {"date": "2026-01-13", "close": 10.2},
            {"date": "2026-01-17", "close": 10.5},
            {"date": "2026-01-20", "close": 11.0},
        ]}
        etfs = {"159995": {"name": "芯片ETF"}}
        results = _event_accuracy(event, hist, etfs, window_days=2)
        assert len(results) == 1
        # pre=10.2 (01-13, <= 01-15), post=10.5 (01-17, >= 01-15)
        # pnl = (10.5-10.2)/10.2*100 - 0.2 = 2.94 - 0.2 = 2.74 > 0 → correct=True
        assert results[0]["correct"] is True
        assert results[0]["pnl_pct"] > 0

    def test_cost_deduction(self):
        # 价格仅微涨,扣除交易成本后应判 correct=False
        # window_days=2 需要 len(recs) >= 4
        event = {"d": "2026-01-15", "dir": "利好", "c": ["159995"], "n": "test_event", "h": 30}
        hist = {"159995": [
            {"date": "2026-01-10", "close": 10.0},
            {"date": "2026-01-13", "close": 10.003},
            {"date": "2026-01-15", "close": 10.005},
            {"date": "2026-01-20", "close": 10.01},
        ]}
        etfs = {"159995": {"name": "芯片ETF"}}
        results = _event_accuracy(event, hist, etfs, window_days=2)
        assert len(results) == 1
        # pnl = (10.01 - 10.0)/10.0 * 100 - COST_BPS = 0.1 - 0.2 = -0.1 → correct=False
        assert results[0]["correct"] is False


@pytest.mark.unit
class TestEventAccuracyDelisted:
    def test_delisted_flag_false_by_default(self):
        event = {"d": "2026-01-15", "dir": "利好", "c": ["159995"], "n": "test_event", "h": 30}
        hist = {"159995": [
            {"date": "2026-01-10", "close": 10.0},
            {"date": "2026-01-13", "close": 10.2},
            {"date": "2026-01-15", "close": 10.5},
            {"date": "2026-01-20", "close": 11.0},
        ]}
        etfs = {"159995": {"name": "芯片ETF"}}
        results = _event_accuracy(event, hist, etfs, window_days=2, delisted_codes=[])
        assert results[0]["delisted"] is False

    def test_delisted_flag_true(self):
        event = {"d": "2026-01-15", "dir": "利好", "c": ["159995"], "n": "test_event", "h": 30}
        hist = {"159995": [
            {"date": "2026-01-10", "close": 10.0},
            {"date": "2026-01-13", "close": 10.2},
            {"date": "2026-01-15", "close": 10.5},
            {"date": "2026-01-20", "close": 11.0},
        ]}
        etfs = {"159995": {"name": "芯片ETF"}}
        results = _event_accuracy(event, hist, etfs, window_days=2, delisted_codes=["159995"])
        assert results[0]["delisted"] is True


@pytest.mark.unit
class TestEventAccuracyEdgeCases:
    def test_skip_no_history(self):
        # 代码不在 hist 中,应跳过
        event = {"d": "2026-01-15", "dir": "利好", "c": ["999999"], "n": "test_event", "h": 30}
        hist = {"159995": [{"date": "2026-01-10", "close": 10.0}]}
        etfs = {"159995": {"name": "芯片ETF"}}
        results = _event_accuracy(event, hist, etfs, window_days=2)
        assert len(results) == 0

    def test_skip_empty_history(self):
        event = {"d": "2026-01-15", "dir": "利好", "c": ["159995"], "n": "test_event", "h": 30}
        hist = {"159995": []}
        etfs = {"159995": {"name": "芯片ETF"}}
        results = _event_accuracy(event, hist, etfs, window_days=2)
        assert len(results) == 0

    def test_skip_insufficient_data(self):
        # 数据不足 window_days*2,应跳过
        event = {"d": "2026-01-15", "dir": "利好", "c": ["159995"], "n": "test_event", "h": 30}
        hist = {"159995": [{"date": "2026-01-10", "close": 10.0}]}
        etfs = {"159995": {"name": "芯片ETF"}}
        results = _event_accuracy(event, hist, etfs, window_days=5)
        assert len(results) == 0

    def test_start_date_check(self):
        # 事件日早于数据起始日,应跳过
        event = {"d": "2025-01-01", "dir": "利好", "c": ["159995"], "n": "old_event", "h": 30}
        hist = {"159995": [
            {"date": "2026-01-10", "close": 10.0},
            {"date": "2026-01-20", "close": 11.0},
        ]}
        etfs = {"159995": {"name": "芯片ETF"}}
        results = _event_accuracy(event, hist, etfs, window_days=2)
        assert len(results) == 0


@pytest.mark.unit
class TestConstants:
    def test_transaction_cost_value(self):
        assert TRANSACTION_COST == 0.002  # 0.2%

    def test_cost_bps_value(self):
        assert COST_BPS == 0.2  # 0.2% = 20 bps (TRANSACTION_COST*100)
