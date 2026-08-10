"""d751 任务1 新闻情绪因子进 factor_dynamic_weights 测试."""
import pytest

from etf_platform.analysis import factor_dynamic_weights as fdw
from etf_platform.analysis.factor_dynamic_weights import _get_sentiment_raw, get_dynamic_weights

pytestmark = [pytest.mark.unit]


def test_dynamic_weights_contains_sentiment():
    w = get_dynamic_weights("normal")
    assert "news_sentiment" in w
    assert abs(sum(w.values()) - 1.0) < 1e-6


def test_sentiment_weights_vary_by_regime():
    w_normal = get_dynamic_weights("normal")["news_sentiment"]
    w_fearful = get_dynamic_weights("fearful")["news_sentiment"]
    assert w_fearful > w_normal


def test_get_sentiment_raw_known():
    val = _get_sentiment_raw("军工")
    assert -1.0 <= val <= 1.0


def test_get_sentiment_raw_missing_file(monkeypatch):
    monkeypatch.setattr(fdw, "SENT_FILE", fdw.BASE / "data" / "_nonexistent_sentiment.json")
    assert _get_sentiment_raw("军工") == 0.0
