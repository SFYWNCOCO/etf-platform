"""Tests for decision/prediction_backtest.py - K线锚点法回测。

锁定的回归：_get_etf_returns 必须从 start_date 锚定收益（复用 prediction_monitor
的 _return_since），而不是返回 get_trend 的"当前动量"——后者是前视偏差，
曾导致回测 win 100% / Sharpe 62 的假象。
"""
import pytest
from unittest.mock import patch

pytestmark = [pytest.mark.unit]


@pytest.fixture(autouse=True)
def _clean_return_cache():
    from etf_platform.decision import prediction_backtest
    prediction_backtest._return_cache.clear()
    yield
    prediction_backtest._return_cache.clear()


class TestGetEtfReturns:
    def test_uses_kline_anchor_return(self):
        """复用 prediction_monitor._return_since 的 K 线锚点法，而非当前动量。"""
        from etf_platform.decision import prediction_backtest
        with patch("etf_platform.decision.prediction_monitor._return_since",
                   return_value=3.21) as mock_since:
            rets = prediction_backtest._get_etf_returns("159732", "2026-07-18", days=10)
        assert rets == [3.21]
        # 锚定参数透传：start_date 必须参与，days 必须生效
        mock_since.assert_called_once_with("2026-07-18", "159732", 10)

    def test_caches_per_code_date(self):
        """同一 (code, start_date, days) 只查询一次；不同日期是新 key。"""
        from etf_platform.decision import prediction_backtest
        with patch("etf_platform.decision.prediction_monitor._return_since",
                   return_value=1.0) as mock_since:
            prediction_backtest._get_etf_returns("159732", "2026-07-18", 10)
            prediction_backtest._get_etf_returns("159732", "2026-07-18", 10)
            prediction_backtest._get_etf_returns("159732", "2026-07-19", 10)
        assert mock_since.call_count == 2  # 第 1、2 次命中缓存，第 3 次是新日期

    def test_none_result_returns_empty(self):
        """K线数据不足（_return_since 返回 None）时返回空列表，调用方跳过。"""
        from etf_platform.decision import prediction_backtest
        with patch("etf_platform.decision.prediction_monitor._return_since",
                   return_value=None):
            assert prediction_backtest._get_etf_returns("999999", "2026-07-18") == []

    def test_exception_returns_empty(self):
        """K线获取异常时返回空列表而非抛错。"""
        from etf_platform.decision import prediction_backtest
        with patch("etf_platform.decision.prediction_monitor._return_since",
                   side_effect=OSError("network down")):
            assert prediction_backtest._get_etf_returns("159732", "2026-07-18") == []


class TestSuggestWeights:
    def test_sample_note_uses_count(self):
        """sample_size_note 应取 rank_1 的 count，而非 dict 的 len（键数）。"""
        from etf_platform.decision import prediction_backtest
        result = prediction_backtest._suggest_weights(
            {"rank_1": {"avg_return": 1.0, "win_rate": 60.0, "count": 5}},
            win_rate=50.0, sharpe=0.5,
        )
        assert "5" in result["sample_size_note"]
