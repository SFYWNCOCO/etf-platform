"""news_to_etf_bridge build_signals 健壮性回归测试 — P2-4.

覆盖外部 cron 写盘 news_sentiment.json 的边界：sector 不在 SECTOR_SIGNALS、
direction=中性、条目缺 note 键 → build_signals 不得抛 KeyError。
"""
import pytest
import news_to_etf_bridge

pytestmark = [pytest.mark.unit]


class TestBuildSignalsKeyError:
    def test_neutral_sector_missing_note_no_keyerror(self, monkeypatch):
        """中性 + 未收录 sector + 缺 note 键：不崩且该 sector 的 ETF direction=中性."""
        monkeypatch.setattr(news_to_etf_bridge, "load_etf_sectors", lambda: {"159827": "农业"})
        auto = {"农业": {"direction": "中性", "strength": "弱"}}
        signals = news_to_etf_bridge.build_signals(auto_sentiment=auto)
        assert "159827" in signals
        assert signals["159827"]["direction"] == "中性"
