"""Tests for freshness.py + materials.py 时效标记."""
import os
from datetime import datetime, timedelta

import pytest
import yaml

from etf_platform.utils.freshness import as_of
from etf_platform.analysis.deep_sub.materials import (
    MATERIAL_PLUGIN_REGISTRY,
    materials_freshness,
    register_from_file,
)

pytestmark = [pytest.mark.unit]

_STALE_MAT_NAME = "测试时效材料"


@pytest.fixture
def _cleanup_stale_mat():
    yield
    MATERIAL_PLUGIN_REGISTRY.pop(_STALE_MAT_NAME, None)


class TestAsOf:
    def test_new_file_is_fresh(self, tmp_path):
        p = tmp_path / "snap.yaml"
        p.write_text("materials: {}", encoding="utf-8")
        snap = as_of(p)
        assert snap["exists"] is True
        assert snap["status"] == "fresh"
        assert snap["mtime_iso"] is not None
        assert snap["age_days"] is not None

    def test_old_mtime_is_stale(self, tmp_path):
        p = tmp_path / "snap.yaml"
        p.write_text("materials: {}", encoding="utf-8")
        old = datetime.now() - timedelta(days=30)
        os.utime(p, (old.timestamp(), old.timestamp()))
        snap = as_of(p)
        assert snap["status"] == "stale"
        assert snap["age_days"] > 14

    def test_missing_path_is_missing(self, tmp_path):
        snap = as_of(tmp_path / "nope.yaml")
        assert snap["exists"] is False
        assert snap["status"] == "missing"
        assert snap["mtime_iso"] is None
        assert snap["age_days"] is None


class TestRegisterFromFileStale:
    def test_stale_yaml_marks_entries(self, tmp_path, _cleanup_stale_mat):
        p = tmp_path / "stale.yaml"
        p.write_text(yaml.safe_dump({
            "materials": {_STALE_MAT_NAME: {"current": "1", "affects": ["159995"], "impact_direction": "利好"}}
        }), encoding="utf-8")
        old = datetime.now() - timedelta(days=30)
        os.utime(p, (old.timestamp(), old.timestamp()))
        assert register_from_file(p) == 1
        entry = MATERIAL_PLUGIN_REGISTRY[_STALE_MAT_NAME]
        assert entry["_stale"] is True
        assert entry["_data_as_of"] is not None

    def test_materials_freshness_covers_all_three(self):
        fr = materials_freshness()
        assert set(fr) == {"material_prices.yaml", "emerging_materials.yaml", "material_quick_add.yaml"}
        assert all(f["path"] and f["status"] in ("fresh", "stale") for f in fr.values())
