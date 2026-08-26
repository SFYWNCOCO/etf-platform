# -*- coding: utf-8 -*-
"""acceptance_check 自动验收器单元测试 (cc_batch_c).

覆盖:
- 全绿: 今日推荐 + 三产物 mtime<24h + 心跳<48h + 伪造 etf_platform 可导入 → all_ok
- 单个产物 mtime 拨回 2 天 → artifacts_fresh_24h fail 且 detail 指名文件
- 删除 log → recommendations_today fail
- 心跳超龄 → heartbeat_alive fail
- now 固定保证日期判定确定性 (不依赖真实时钟)
"""
import importlib.util
import os
import sys
import types
from datetime import datetime, timedelta
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

REPO_ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 8, 26, 12, 0, 0)
TODAY = "2026-08-26"
ARTIFACTS = ("price_cache.json", "kline_trend_cache.json", "news_etf_signals.json")


def _load_module():
    spec = importlib.util.spec_from_file_location("acceptance_check", REPO_ROOT / "acceptance_check.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _touch(path: Path, content: str, mtime: datetime):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    ts = mtime.timestamp()
    os.utime(path, (ts, ts))


def _install_fake_etf_platform(monkeypatch):
    """伪造 etf_platform.analysis.material_bridge，让验收器不依赖真实 src 包."""
    etf_pkg = types.ModuleType("etf_platform")
    etf_pkg.__path__ = []
    etf_pkg.__package__ = "etf_platform"
    analysis = types.ModuleType("etf_platform.analysis")
    analysis.__path__ = []
    analysis.__package__ = "etf_platform.analysis"
    bridge = types.ModuleType("etf_platform.analysis.material_bridge")
    bridge.__package__ = "etf_platform.analysis"
    bridge.material_freshness_report = lambda: {"碳酸锂(电池级)": {"_data_as_of": None, "_stale": False}}
    etf_pkg.analysis = analysis
    analysis.material_bridge = bridge
    monkeypatch.setitem(sys.modules, "etf_platform", etf_pkg)
    monkeypatch.setitem(sys.modules, "etf_platform.analysis", analysis)
    monkeypatch.setitem(sys.modules, "etf_platform.analysis.material_bridge", bridge)


@pytest.fixture
def fresh_tmp(tmp_path, monkeypatch):
    _install_fake_etf_platform(monkeypatch)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _touch(data_dir / "recommendations_log.jsonl",
           '{"date": "%s", "code": "159995"}\n' % TODAY, NOW)
    for name in ARTIFACTS:
        _touch(data_dir / name, "{}", NOW)
    _touch(data_dir / "etf_heartbeat_latest.json", "{}", NOW)
    return tmp_path


class TestValidateDailyOutputs:
    def test_all_ok_when_fresh(self, fresh_tmp):
        mod = _load_module()
        r = mod.validate_daily_outputs(base_dir=fresh_tmp, now=NOW)

        assert r["all_ok"] is True
        assert len(r["checks"]) == 4
        assert all(c["ok"] for c in r["checks"])
        assert r["checked_at"].startswith("2026-08-26")

    def test_stale_price_cache_fails(self, fresh_tmp):
        mod = _load_module()
        p = fresh_tmp / "data" / "price_cache.json"
        ts = (NOW - timedelta(days=2)).timestamp()
        os.utime(p, (ts, ts))

        r = mod.validate_daily_outputs(base_dir=fresh_tmp, now=NOW)
        art = next(c for c in r["checks"] if c["name"] == "artifacts_fresh_24h")

        assert art["ok"] is False
        assert "price_cache.json" in art["detail"]
        assert r["all_ok"] is False

    def test_missing_log_fails_recommendations(self, fresh_tmp):
        mod = _load_module()
        (fresh_tmp / "data" / "recommendations_log.jsonl").unlink()

        r = mod.validate_daily_outputs(base_dir=fresh_tmp, now=NOW)
        rec = next(c for c in r["checks"] if c["name"] == "recommendations_today")

        assert rec["ok"] is False
        assert "recommendations_log.jsonl" in rec["detail"]
        assert r["all_ok"] is False

    def test_stale_heartbeat_fails(self, fresh_tmp):
        mod = _load_module()
        hb = fresh_tmp / "data" / "etf_heartbeat_latest.json"
        ts = (NOW - timedelta(hours=60)).timestamp()
        os.utime(hb, (ts, ts))

        r = mod.validate_daily_outputs(base_dir=fresh_tmp, now=NOW)
        beat = next(c for c in r["checks"] if c["name"] == "heartbeat_alive")

        assert beat["ok"] is False
        assert "48h" in beat["detail"]
        assert r["all_ok"] is False
