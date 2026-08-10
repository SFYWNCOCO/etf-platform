"""Tests for data/manager.py - data source management with fallback.

Covers:
- Module structure: 3 thread locks (_LAST_PRICE_SOURCE_LOCK / _LAST_HEALTH_LOCK / _NEWS_CACHE_LOCK)
- get_price() fallback logic (first source fails -> second succeeds)
- get_news() caching behavior
"""
import threading
import pytest
from unittest.mock import patch, MagicMock

pytestmark = [pytest.mark.unit]


@pytest.fixture(autouse=True)
def _clean_source_cache():
    """清理 _last_price_source / _news_cache 模块级状态，保证测试隔离。"""
    from etf_platform.data import manager
    with manager._LAST_PRICE_SOURCE_LOCK:
        saved_price = dict(manager._last_price_source)
        manager._last_price_source.clear()
    with manager._NEWS_CACHE_LOCK:
        saved_news = dict(manager._news_cache)
        manager._news_cache.clear()
    yield
    with manager._LAST_PRICE_SOURCE_LOCK:
        manager._last_price_source.clear()
        manager._last_price_source.update(saved_price)
    with manager._NEWS_CACHE_LOCK:
        manager._news_cache.clear()
        manager._news_cache.update(saved_news)


class TestManagerModule:
    def test_manager_module_import(self):
        """模块可正常导入且暴露核心函数。"""
        from etf_platform.data import manager
        assert manager is not None
        assert hasattr(manager, "get_price")
        assert callable(manager.get_price)
        assert hasattr(manager, "get_news")
        assert callable(manager.get_news)
        assert hasattr(manager, "get_prices")
        assert hasattr(manager, "check_all_sources")
        assert hasattr(manager, "get_preferred_source")

    def test_manager_has_locks(self):
        """验证 3 个线程锁同时存在。"""
        from etf_platform.data import manager
        lock_type = type(threading.Lock())
        assert hasattr(manager, "_LAST_PRICE_SOURCE_LOCK")
        assert isinstance(manager._LAST_PRICE_SOURCE_LOCK, lock_type)
        assert hasattr(manager, "_LAST_HEALTH_LOCK")
        assert isinstance(manager._LAST_HEALTH_LOCK, lock_type)
        assert hasattr(manager, "_NEWS_CACHE_LOCK")
        assert isinstance(manager._NEWS_CACHE_LOCK, lock_type)

    def test_news_cache_lock_exists(self):
        """_NEWS_CACHE_LOCK 存在且为锁实例。"""
        from etf_platform.data import manager
        assert hasattr(manager, "_NEWS_CACHE_LOCK")
        assert isinstance(manager._NEWS_CACHE_LOCK, type(threading.Lock()))
        # TTL 配置存在
        assert hasattr(manager, "_NEWS_CACHE_TTL")
        assert isinstance(manager._NEWS_CACHE_TTL, int)
        assert manager._NEWS_CACHE_TTL > 0

    def test_last_price_source_lock_exists(self):
        """_LAST_PRICE_SOURCE_LOCK 存在且为锁实例。"""
        from etf_platform.data import manager
        assert hasattr(manager, "_LAST_PRICE_SOURCE_LOCK")
        assert isinstance(manager._LAST_PRICE_SOURCE_LOCK, type(threading.Lock()))
        # 缓存字典存在
        assert hasattr(manager, "_last_price_source")
        assert isinstance(manager._last_price_source, dict)

    def test_last_health_lock_exists(self):
        """_LAST_HEALTH_LOCK 存在且为锁实例。"""
        from etf_platform.data import manager
        assert hasattr(manager, "_LAST_HEALTH_LOCK")
        assert isinstance(manager._LAST_HEALTH_LOCK, type(threading.Lock()))
        assert hasattr(manager, "_last_health")
        assert isinstance(manager._last_health, dict)

    def test_price_sources_configured(self):
        """_PRICE_SOURCES 已配置且非空。"""
        from etf_platform.data import manager
        assert hasattr(manager, "_PRICE_SOURCES")
        assert isinstance(manager._PRICE_SOURCES, list)
        assert len(manager._PRICE_SOURCES) >= 2
        # 每个源都有 name 属性
        for src in manager._PRICE_SOURCES:
            assert hasattr(src, "name")


class TestPriceFallback:
    def test_get_price_source_fallback(self):
        """数据源故障转移：第一个源抛异常，第二个源成功返回。"""
        from etf_platform.data import manager
        from etf_platform.data.base import PriceSnapshot
        # 构造 mock 数据源
        mock_src_a = MagicMock()
        mock_src_a.name = "source_a"
        mock_src_a.get_price.side_effect = OSError("network down")
        mock_src_b = MagicMock()
        mock_src_b.name = "source_b"
        mock_src_b.get_price.return_value = PriceSnapshot(
            code="159995", price=1.23, source="source_b"
        )
        mock_src_c = MagicMock()
        mock_src_c.name = "source_c"
        mock_src_c.get_price.return_value = None
        with patch.object(manager, "_PRICE_SOURCES",
                          [mock_src_a, mock_src_b, mock_src_c]):
            # 隔离磁盘缓存：本测试意在验证 source fallback，若命中真实
            # price_cache.json（价格随每日刷新变化），断言会脆断。
            # manager.get_price 内是函数级 `from .price_cache import get_cached_price`，
            # 局部导入每次重新绑定，因此 patch 源模块即可拦截。
            with patch("etf_platform.data.price_cache.get_cached_price", return_value=None):
                result, src_name = manager.get_price("159995")
        assert result is not None
        assert result.price == 1.23
        assert src_name == "source_b"
        # 验证第一个源被尝试
        mock_src_a.get_price.assert_called_once_with("159995")
        # 验证第二个源被调用并成功
        mock_src_b.get_price.assert_called_once_with("159995")
        # 验证第三个源未被调用（已成功返回）
        mock_src_c.get_price.assert_not_called()
        # 验证缓存更新为成功的源
        with manager._LAST_PRICE_SOURCE_LOCK:
            assert manager._last_price_source.get("159995") == "source_b"

    def test_get_price_all_sources_fail(self):
        """所有数据源均失败时返回 (None, 'none')。"""
        from etf_platform.data import manager
        mock_src_a = MagicMock()
        mock_src_a.name = "source_a"
        mock_src_a.get_price.side_effect = OSError("down")
        mock_src_b = MagicMock()
        mock_src_b.name = "source_b"
        mock_src_b.get_price.return_value = None
        with patch.object(manager, "_PRICE_SOURCES", [mock_src_a, mock_src_b]):
            result, src_name = manager.get_price("999999")
        assert result is None
        assert src_name == "none"
        # 两个源都被尝试
        mock_src_a.get_price.assert_called_once_with("999999")
        mock_src_b.get_price.assert_called_once_with("999999")

    def test_get_price_zero_price_treated_as_failure(self):
        """price<=0 的快照视为失败，触发后续源回退。"""
        from etf_platform.data import manager
        from etf_platform.data.base import PriceSnapshot
        mock_src_a = MagicMock()
        mock_src_a.name = "source_a"
        mock_src_a.get_price.return_value = PriceSnapshot(code="159995", price=0)
        mock_src_b = MagicMock()
        mock_src_b.name = "source_b"
        mock_src_b.get_price.return_value = PriceSnapshot(
            code="159995", price=1.5, source="source_b"
        )
        with patch.object(manager, "_PRICE_SOURCES", [mock_src_a, mock_src_b]):
            with patch("etf_platform.data.price_cache.get_cached_price", return_value=None):
                result, src_name = manager.get_price("159995")
        assert result is not None
        assert result.price == 1.5
        assert src_name == "source_b"


class TestNewsCache:
    def test_get_news_uses_cache(self, monkeypatch):
        """get_news 第二次调用命中缓存，不再次访问数据源。"""
        from etf_platform.data import manager
        from etf_platform.data.base import NewsItem
        mock_src = MagicMock()
        mock_src.name = "mock_news"
        mock_src.get_news.return_value = [
            NewsItem(title="头条1", relevance=0.9),
            NewsItem(title="头条2", relevance=0.5),
        ]
        # 固定时间避免 TTL 抖动
        fixed_t = [1000.0]
        monkeypatch.setattr(manager.time, "time", lambda: fixed_t[0])
        with patch.object(manager, "_NEWS_SOURCES", [mock_src]):
            r1 = manager.get_news("芯片", limit=5)
            # 第二次调用应命中缓存
            r2 = manager.get_news("芯片", limit=5)
        assert r1 == r2
        assert len(r1) == 2
        # 按相关性降序
        assert r1[0].relevance >= r1[1].relevance
        # 数据源只被调用一次（缓存命中）
        assert mock_src.get_news.call_count == 1

    def test_get_news_cache_expiry(self, monkeypatch):
        """缓存过期后重新拉取数据。"""
        from etf_platform.data import manager
        from etf_platform.data.base import NewsItem
        mock_src = MagicMock()
        mock_src.name = "mock_news"
        mock_src.get_news.return_value = [NewsItem(title="新", relevance=0.8)]
        current = [1000.0]
        monkeypatch.setattr(manager.time, "time", lambda: current[0])
        with patch.object(manager, "_NEWS_SOURCES", [mock_src]):
            manager.get_news("半导体", limit=5)
            # 推进时间超过 TTL
            current[0] = 1000.0 + manager._NEWS_CACHE_TTL + 1
            manager.get_news("半导体", limit=5)
        assert mock_src.get_news.call_count == 2
