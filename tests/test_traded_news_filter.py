"""d751 Traded News 过滤测试 — 可交易新闻 vs 个股公告/娱乐等噪音。

覆盖规格 10 个用例，item 字段对齐 news_raw_sources.json:
source/lid/channel/title/time/url/summary/is_bearish
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from traded_news_filter import detect_anomaly, filter_tradable, is_tradable

pytestmark = [pytest.mark.unit]


def _item(title, channel="综合财经", summary=""):
    return {
        "source": "test",
        "channel": channel,
        "title": title,
        "time": "2026-08-10 08:00:00",
        "url": "",
        "summary": summary,
        "is_bearish": False,
    }


def test_tradable_sector_news():
    ok, reason = is_tradable(_item("半导体行业Q2业绩预增 国产替代加速"))
    assert ok is True
    assert "行业词" in reason or "半导体" in reason


def test_tradable_policy_news():
    ok, reason = is_tradable(_item("央行降准0.5个百分点 释放流动性"))
    assert ok is True


def test_tradable_industry_event():
    ok, reason = is_tradable(_item("碳酸锂价格突破10万元/吨 锂电产业链受益"))
    assert ok is True
    assert "行业词" in reason or "产业链" in reason


def test_noise_stock_holding():
    ok, reason = is_tradable(_item("天齐锂业遭摩根大通减持约20.74万股"))
    assert ok is False
    assert "减持" in reason


def test_noise_daily_announcement():
    ok, reason = is_tradable(_item("XX公司召开年度股东大会 审议分红方案"))
    assert ok is False
    assert "公告" in reason


def test_noise_entertainment():
    ok, reason = is_tradable(_item("某明星新剧开播 收视率创新高"))
    assert ok is False
    assert "娱乐" in reason or "体育" in reason


def test_filter_tradable_batch():
    items = [
        _item("半导体行业Q2业绩预增 国产替代加速"),
        _item("天齐锂业遭摩根大通减持约20.74万股"),
        _item("某明星新剧开播 收视率创新高"),
        _item("碳酸锂价格突破10万元/吨 锂电产业链受益"),
    ]
    tradable, noise = filter_tradable(items)
    assert len(tradable) == 2
    assert len(noise) == 2
    assert any("半导体" in it["title"] for it in tradable)
    assert any("减持" in it["title"] for it in noise)


def test_empty_input():
    tradable, noise = filter_tradable([])
    assert tradable == []
    assert noise == []


def test_no_industry_word_company_news():
    ok, reason = is_tradable(_item("广合科技获富国基金增持39.25万股"))
    assert ok is False
    assert "增持" in reason


def test_macro_without_industry():
    ok, reason = is_tradable(_item("美联储宣布加息25个基点"))
    assert ok is True
    assert "宏观" in reason


# ── d807 异常/拐点信号识别（多年首次/历史新高/停工重启 = 拐点）──

def test_detect_anomaly_types():
    assert detect_anomaly("SK海力士重启大连NAND二期工厂建设") == ["重启型"]
    assert detect_anomaly("半导体行业历史首次突破万亿产值") == ["首次型"]
    assert detect_anomaly("30年期美债收益率创历史新高") == ["纪录型"]
    assert detect_anomaly("储能从配角变成AI算力标配 行业迎来拐点") == ["拐点型"]
    assert detect_anomaly("某公司发布日常公告") == []


def test_anomaly_restart_industry():
    # d807 信号链2: SK海力士重启大连NAND二期（停工4年）→ 半导体设备信号
    ok, reason = is_tradable(_item("SK海力士重启大连NAND二期工厂建设 规划产能扩大50%"))
    assert ok is True
    assert "异常信号:重启型" in reason


def test_anomaly_record_high_with_macro():
    # d807 信号链3: 30年期美债收益率破5.2% = 2007年来首次（纪录型+宏观锚定）
    ok, reason = is_tradable(_item("30年期美国国债收益率涨破5.2% 创2007年以来历史新高"))
    assert ok is True
    assert "异常信号:纪录型" in reason


def test_anomaly_first_time_without_anchor():
    # 异常但无行业/宏观锚定 → 不误升级（保持原规则）
    ok, reason = is_tradable(_item("某地历史首次举办文化节"))
    assert ok is False


def test_anomaly_does_not_override_noise():
    # 娱乐噪音带"新高" → 仍被社会噪音规则拦截（不因异常信号翻案）
    ok, reason = is_tradable(_item("某明星新剧开播 收视率创新高"))
    assert ok is False
    assert "娱乐" in reason or "体育" in reason
