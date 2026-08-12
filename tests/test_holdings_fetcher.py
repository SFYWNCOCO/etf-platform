"""Tests for analysis/holdings_fetcher.py v2.0.

锁定的回归：
1. 磁盘缓存 TTL：保存不重置 _ts（TTL 不无限顺延），过期重新抓取。
2. 空持仓缓存用短 TTL（1 天），限流"假空"能快速自愈。
3. 字段契约：持仓 dict 含 code/name/weight（holdings_overlap 期望）+ pct_nav（旧调用方期望）。
4. 最新季度过滤：多季度数据不跨季重复计数。
5. 防覆盖保护：有效请求比例过低时保留旧缓存。
"""
import pytest

pytestmark = [pytest.mark.unit]

SAMPLE = [
    {"code": "600519", "name": "贵州茅台", "pct_nav": 4.75, "weight": 0.0475,
     "shares": 100, "market_value": 1000, "quarter": "2026年2季度股票投资明细"},
    {"code": "300750", "name": "宁德时代", "pct_nav": 3.55, "weight": 0.0355,
     "shares": 80, "market_value": 900, "quarter": "2026年2季度股票投资明细"},
]


class FakeTime:
    now = 1000.0

    def time(self):
        return FakeTime.now

    def sleep(self, s):
        pass

    def strftime(self, fmt, t=None):
        return "2026-08-12T00:00:00"

    def localtime(self, t=None):
        import time as _t
        return _t.localtime(t or FakeTime.now)


@pytest.fixture(autouse=True)
def _iso_cache_path(monkeypatch, tmp_path):
    import etf_platform.analysis.holdings_fetcher as hf
    monkeypatch.setattr(hf, "_CACHE_PATH", tmp_path / "holdings_cache.json")
    monkeypatch.setattr(hf, "_CHECKPOINT_PATH", tmp_path / "holdings_refresh_checkpoint.json")
    hf._holdings_cache.clear()
    yield
    hf._holdings_cache.clear()


class TestLatestQuarter:
    def test_keeps_only_newest_quarter(self):
        import etf_platform.analysis.holdings_fetcher as hf
        data = [
            {"code": "A", "name": "a", "pct_nav": 1, "quarter": "2025年4季度股票投资明细"},
            {"code": "B", "name": "b", "pct_nav": 2, "quarter": "2026年2季度股票投资明细"},
            {"code": "C", "name": "c", "pct_nav": 3, "quarter": "2026年1季度股票投资明细"},
        ]
        out = hf._latest_quarter_holdings(data)
        assert [h["code"] for h in out] == ["B"]

    def test_unparsable_quarter_keeps_all(self):
        import etf_platform.analysis.holdings_fetcher as hf
        data = [{"code": "A", "name": "a", "pct_nav": 1, "quarter": ""}]
        assert hf._latest_quarter_holdings(data) == data

    def test_none_returns_empty(self):
        import etf_platform.analysis.holdings_fetcher as hf
        assert hf._latest_quarter_holdings(None) == []
        assert hf._latest_quarter_holdings([]) == []


class TestCacheTTL:
    def test_corrupt_cache_warns_and_returns_empty(self, tmp_path, caplog):
        """回归：损坏缓存此前静默返回 {}，触发全量重抓且故障不可见。"""
        import logging
        import etf_platform.analysis.holdings_fetcher as hf
        tmp_path.joinpath("holdings_cache.json").write_text("{broken json", encoding="utf-8")
        with caplog.at_level(logging.WARNING):
            out = hf._load_disk_cache()
        assert out == {}
        assert "损坏" in caplog.text

    def test_fresh_hits_empty_short_ttl_expires(self, monkeypatch):
        import etf_platform.analysis.holdings_fetcher as hf
        fetched = []
        monkeypatch.setattr(hf, "_fetch_latest",
                            lambda code: (fetched.append(code) or list(SAMPLE)))
        monkeypatch.setattr(hf, "time", FakeTime())
        FakeTime.now = 1000.0
        hf.get_top_holdings("510300", 5)
        hf.get_top_holdings("510300", 5)
        assert len(fetched) == 1  # TTL 内命中，不重复抓
        # 过期后重新抓取
        FakeTime.now = 1000.0 + hf._CACHE_TTL + 1
        hf._holdings_cache.clear()
        hf.get_top_holdings("510300", 5)
        assert len(fetched) == 2

    def test_empty_cache_expires_in_1_day(self, monkeypatch):
        import etf_platform.analysis.holdings_fetcher as hf
        fetched = []
        monkeypatch.setattr(hf, "_fetch_latest", lambda code: (fetched.append(code) or []))
        monkeypatch.setattr(hf, "time", FakeTime())
        FakeTime.now = 1000.0
        assert hf.get_top_holdings("518880", 5) == []
        assert len(fetched) == 1
        # 空缓存 1 天后过期（非 7 天），假空可自愈
        FakeTime.now = 1000.0 + hf._EMPTY_TTL + 1
        hf._holdings_cache.clear()
        hf.get_top_holdings("518880", 5)
        assert len(fetched) == 2


class TestFieldContract:
    def test_holdings_dict_has_both_contracts(self, monkeypatch):
        import etf_platform.analysis.holdings_fetcher as hf
        monkeypatch.setattr(hf, "_fetch_latest", lambda code: list(SAMPLE))
        monkeypatch.setattr(hf, "time", FakeTime())
        top = hf.get_top_holdings("510300", 5)
        assert top
        h = top[0]
        # holdings_overlap 契约
        assert h["code"] == "600519"
        assert h["name"] == "贵州茅台"
        assert h["weight"] == pytest.approx(0.0475)
        # 旧调用方字段
        assert h["pct_nav"] == pytest.approx(4.75)
        assert "quarter" in h and "shares" in h and "market_value" in h

    def test_concentration_uses_latest_quarter_only(self, monkeypatch):
        import etf_platform.analysis.holdings_fetcher as hf
        data = [
            {"code": "A", "name": "a", "pct_nav": 5.0, "weight": 0.05, "quarter": "2026年2季度股票投资明细"},
            {"code": "B", "name": "b", "pct_nav": 3.0, "weight": 0.03, "quarter": "2026年2季度股票投资明细"},
            {"code": "A", "name": "a", "pct_nav": 9.0, "weight": 0.09, "quarter": "2026年1季度股票投资明细"},
        ]
        monkeypatch.setattr(hf, "_fetch_latest", lambda code: data)
        monkeypatch.setattr(hf, "time", FakeTime())
        conc = hf.get_concentration_metrics("510300")
        assert conc["total_holdings"] == 2  # 只算最新季度
        assert conc["top1_pct"] == pytest.approx(5.0)


class TestHHI:
    def test_hhi_and_effective_use_decimal_weights(self, monkeypatch):
        import etf_platform.analysis.holdings_fetcher as hf
        monkeypatch.setattr(hf, "_fetch_latest", lambda code: list(SAMPLE))
        monkeypatch.setattr(hf, "time", FakeTime())
        conc = hf.get_concentration_metrics("510300")
        expected_hhi = (4.75 / 100) ** 2 + (3.55 / 100) ** 2
        assert conc["herfindahl"] == pytest.approx(expected_hhi, abs=1e-4)
        assert conc["effective_holdings"] > 0  # 修复前 1/hhi 取整恒为 0.0（金丝雀）
        assert conc["effective_holdings"] == pytest.approx(1.0 / expected_hhi, abs=0.5)


class TestRefreshProtection:
    def test_low_success_ratio_keeps_old_cache(self, monkeypatch):
        import etf_platform.analysis.holdings_fetcher as hf
        # 预置旧缓存
        hf._save_disk_cache({"510300": {"ts": FakeTime.now, "data": SAMPLE}})
        # 大部分请求失败
        monkeypatch.setattr(hf, "_fetch_latest",
                            lambda code: list(SAMPLE) if code == "510300" else None)
        monkeypatch.setattr(hf, "time", FakeTime())
        stats = hf.refresh_all(codes=["510300", "159995", "588000"])
        assert stats["saved"] is False  # 防覆盖保护触发
        assert stats["success_ratio"] == pytest.approx(1 / 3, abs=0.001)
        # 旧缓存保留在磁盘
        cached = hf._load_disk_cache()
        assert "510300" in cached

    def test_high_success_ratio_saves(self, monkeypatch):
        import etf_platform.analysis.holdings_fetcher as hf
        monkeypatch.setattr(hf, "_fetch_latest", lambda code: list(SAMPLE))
        monkeypatch.setattr(hf, "time", FakeTime())
        stats = hf.refresh_all(codes=["510300", "159995"])
        assert stats["saved"] is True
        assert stats["ok"] == 2
        cached = hf._load_disk_cache()
        assert "510300" in cached and "159995" in cached
