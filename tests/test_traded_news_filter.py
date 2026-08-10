"""d751 Traded News 过滤测试 — 可交易新闻 vs 个股公告/娱乐等噪音。

覆盖规格 10 个用例，item 字段对齐 news_raw_sources.json:
source/lid/channel/title/time/url/summary/is_bearish
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from traded_news_filter import filter_tradable, is_tradable

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
