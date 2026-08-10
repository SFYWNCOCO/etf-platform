"""Tests for data/kline.py TTL + divide-by-zero 修复 + live_price_bridge 深市前缀。

锁定的回归：
1. disk cache TTL：保存时若重置全部 _ts，TTL 无限顺延、缓存永不失效。
2. close=0（停牌/缺口）时 get_trend 不抛 ZeroDivisionError。
3. _market_for 对 167 前缀判深市（167301 实测 sz）。
"""
import pytest

pytestmark = [pytest.mark.unit]


@pytest.fixture(autouse=True)
def _clean_kline_state(monkeypatch, tmp_path):
    from etf_platform.data import kline
    # 隔离磁盘缓存路径，避免测试污染真实 data/kline_trend_cache.json
    monkeypatch.setattr(kline, "_KLINE_DISK_CACHE_PATH",
                        tmp_path / "kline_trend_cache.json")
    monkeypatch.setattr(kline, "_kline_disk_loaded", False)
    kline.clear_trend_cache()
    yield
    kline.clear_trend_cache()


def _fake_rows(n=30):
    return [
        {"date": f"2026-07-{i:02d}", "open": 1.0,
         "close": round(1.0 + i * 0.01, 3),
         "high": 1.1, "low": 0.9, "volume": 1000}
        for i in range(n)
    ]


class TestKlineTTL:
    def test_expired_entry_is_refetched(self, monkeypatch):
        """session 缓存条目超过 TTL 后重新获取（旧逻辑永不重新获取）。"""
        from etf_platform.data import kline
        fetched = []
        monkeypatch.setattr(kline, "_fetch_kline",
                            lambda code, days=63: (fetched.append(code) or _fake_rows()))
        monkeypatch.setattr(kline._time, "time", lambda: 1000.0)
        t1 = kline.get_trend("512890")
        assert len(fetched) == 1
        # 把 fetch 时间推到 TTL 之前 → 下次调用应视为 miss
        kline._trend_ts["512890"] = 1000.0 - kline._KLINE_DISK_TTL - 1
        t2 = kline.get_trend("512890")
        assert len(fetched) == 2
        assert t1 is not None and t2 is not None
        assert t1.code == t2.code == "512890"

    def test_fresh_entry_not_refetched(self, monkeypatch):
        """TTL 内命中缓存，不重复 fetch。"""
        from etf_platform.data import kline
        fetched = []
        monkeypatch.setattr(kline, "_fetch_kline",
                            lambda code, days=63: (fetched.append(code) or _fake_rows()))
        monkeypatch.setattr(kline._time, "time", lambda: 1000.0)
        kline.get_trend("512890")
        kline.get_trend("512890")
        assert len(fetched) == 1


class TestKlineZeroClose:
    def test_zero_close_does_not_crash(self, monkeypatch):
        """close=0 的 bar（停牌/缺口）不触发 ZeroDivisionError。"""
        from etf_platform.data import kline
        rows = []
        for i in range(30):
            close = 0.0 if i in (0, 5) else round(1.0 + i * 0.01, 3)
            rows.append({"date": f"2026-07-{i:02d}", "open": 1.0,
                         "close": close, "high": 1.1, "low": 0.9, "volume": 1000})
        monkeypatch.setattr(kline, "_fetch_kline", lambda code, days=63: rows)
        monkeypatch.setattr(kline._time, "time", lambda: 2000.0)
        t = kline.get_trend("159995")
        assert t is not None
        assert t.data_days == 30
        assert t.change_20d >= -100  # 不抛错且数值合理


class TestMarketFor:
    def test_167_prefix_is_sz(self):
        """167 前缀判深市（167301 实测返回 sz 数据）。"""
        from etf_platform.data.live_price_bridge import _market_for
        assert _market_for("167301") == "sz"
        assert _market_for("159995") == "sz"
        assert _market_for("512890") == "sh"
        assert _market_for("588000") == "sh"
