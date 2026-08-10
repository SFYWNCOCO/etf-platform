"""Tests for 新闻/政策管线修复：
1. news_signal_extractor 中文情绪（旧实现 split() 切不开中文 → 恒 0）
2. policy_fetcher 监管类公文（批复/通知）不再误判为利好
3. news_to_etf_bridge auto=中性 时 direction/summary 一致性
"""
import pytest

pytestmark = [pytest.mark.unit]


class TestChineseSentiment:
    def test_chinese_positive(self):
        from etf_platform.analysis.news_signal_extractor import NewsSignalExtractor
        ex = NewsSignalExtractor()
        assert ex.extract_sentiment("芯片业绩超预期增长") > 0

    def test_chinese_negative(self):
        from etf_platform.analysis.news_signal_extractor import NewsSignalExtractor
        ex = NewsSignalExtractor()
        assert ex.extract_sentiment("公司财务造假爆雷") < 0

    def test_empty_or_neutral(self):
        from etf_platform.analysis.news_signal_extractor import NewsSignalExtractor
        ex = NewsSignalExtractor()
        assert ex.extract_sentiment("") == 0.0
        assert ex.extract_sentiment("今天天气不错") == 0.0

    def test_sentiment_bounded(self):
        from etf_platform.analysis.news_signal_extractor import NewsSignalExtractor
        ex = NewsSignalExtractor()
        for t in ["增长 增长 增长 增长", "亏损 亏损 亏损 亏损", "混合信号增长与亏损"]:
            assert -1.0 <= ex.extract_sentiment(t) <= 1.0


class TestPolicyDirection:
    def test_promote_word_bullish(self):
        from policy_fetcher import judge_policy_direction
        d, s = judge_policy_direction("国务院关于促进人工智能产业发展的指导意见")
        assert d == "看多"

    def test_regulation_word_bearish(self):
        from policy_fetcher import judge_policy_direction
        d, s = judge_policy_direction("关于进一步规范直播营销的通知")
        assert d == "看空"

    def test_safety_notice_is_neutral(self):
        """修复：纯"通知"无方向词时不再弱利好（旧实现批复/通知一律看多0.5）。"""
        from policy_fetcher import judge_policy_direction
        d, s = judge_policy_direction("关于新能源安全生产管理的通知")
        assert d == "中性"
        assert s == 0

    def test_plan_still_weak_bullish(self):
        """规划/方案/意见/纲要仍保留弱利好（产业被提上议程）。"""
        from policy_fetcher import judge_policy_direction
        d, s = judge_policy_direction("新能源汽车产业发展规划")
        assert d == "看多"
        assert s == 0.5

    def test_tighten_notice_bearish(self):
        from policy_fetcher import judge_policy_direction
        d, _ = judge_policy_direction("关于进一步收紧房地产融资的通知")
        assert d == "看空"


class TestNewsToEtfBridgeNeutral:
    def test_auto_neutral_keeps_kb_direction_consistent(self):
        """auto=中性 时 direction 沿用 KB 看多，note 不得被中性覆盖（消除矛盾）。"""
        import news_to_etf_bridge as nb
        auto = {"半导体": {"direction": "中性", "strength": "弱", "note": "今日无明确方向"}}
        signals = nb.build_signals(auto_sentiment=auto)
        # 找到半导体 sector 的任一信号
        semi = [s for s in signals.values() if s["sector"] == "半导体"]
        assert semi, "应生成半导体信号"
        sig = semi[0]
        assert sig["direction"] == "看多"  # KB 方向保留
        assert "AUTO中性" in sig["summary"]  # 附标记
        assert "今日无明确方向" not in sig["summary"]  # 不覆盖

    def test_auto_bullish_overrides_to_bullish(self):
        """auto=看多 时方向覆盖为看多。"""
        import news_to_etf_bridge as nb
        auto = {"半导体": {"direction": "看多", "strength": "强", "note": "国产替代加速"}}
        signals = nb.build_signals(auto_sentiment=auto)
        semi = [s for s in signals.values() if s["sector"] == "半导体"]
        assert semi and semi[0]["direction"] == "看多"
