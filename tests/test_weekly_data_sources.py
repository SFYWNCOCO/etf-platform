"""test_weekly_data_sources.py — 验证 weekly_top3._build_data_sources 溯源字段映射"""
import importlib.util
import sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"


def _load_weekly_top3():
    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))
    spec = importlib.util.spec_from_file_location("weekly_top3", ROOT / "weekly_top3.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_build_data_sources_full_mapping():
    mod = _load_weekly_top3()
    kline_ts = 1750000000.0
    ds = mod._build_data_sources(
        "510300",
        kline_ts,
        {"source": "sina_live", "ts": "2026-08-26T10:00:00"},
        "🟢 今日新闻",
    )
    assert ds["kline_as_of"] == datetime.fromtimestamp(kline_ts).isoformat()
    assert ds["quote_source"] == "sina_live"
    assert ds["quote_as_of"] == "2026-08-26T10:00:00"
    assert ds["news_status"] == "🟢 今日新闻"


def test_build_data_sources_none_graceful():
    mod = _load_weekly_top3()
    ds = mod._build_data_sources("510300", None, None, "")
    assert ds["kline_as_of"] is None
    assert ds["quote_source"] is None
    assert ds["quote_as_of"] is None
    assert ds["news_status"] == ""
