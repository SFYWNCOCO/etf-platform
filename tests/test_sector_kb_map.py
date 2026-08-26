"""test_sector_kb_map.py — 板块KB映射结构与消费链路测试。

覆盖:
- SECTOR_KB_CODES 结构合法（kcode格式 / title非空 / source_file真实存在）
- 映射密度 ≥ 4 条/板块
- get_sector_kb_codes 别名命中与未命中
- L34 摘要含 KB 依据段（真实消费链路）
- weekly_top3 生产路径优先使用板块映射（真实消费链路）
"""
import importlib.util
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"


@pytest.fixture(autouse=True)
def _ensure_src_on_path():
    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))
    yield


def _load_weekly_top3():
    spec = importlib.util.spec_from_file_location("weekly_top3", ROOT / "weekly_top3.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_mapping_structure_valid():
    from etf_platform.kb.sector_kb_map import SECTOR_KB_CODES

    assert SECTOR_KB_CODES, "板块映射不能为空"
    code_re = re.compile(r"^k\d{3}$")
    for sector, items in SECTOR_KB_CODES.items():
        assert sector, "板块名不能为空"
        assert items, f"{sector} 板块不能为空映射"
        for item in items:
            assert code_re.match(item["kcode"]), f"kcode格式非法: {item['kcode']}"
            assert item["title"].strip(), f"{item['kcode']} title 为空"


def test_mapping_density_at_least_4():
    from etf_platform.kb.sector_kb_map import SECTOR_KB_CODES

    total = sum(len(v) for v in SECTOR_KB_CODES.values())
    assert total >= 4 * len(SECTOR_KB_CODES), "映射密度需≥4条/板块"


def test_source_files_exist_in_knowledge():
    from etf_platform.kb.sector_kb_map import SECTOR_KB_CODES

    kb_root = ROOT.parent / "knowledge"
    for sector, items in SECTOR_KB_CODES.items():
        for item in items:
            src = kb_root / item["source_file"]
            assert src.exists(), f"{item['kcode']} 知识库文件缺失: {item['source_file']}"


def test_get_sector_kb_codes_hit_alias():
    from etf_platform.kb.sector_kb_map import get_sector_kb_codes

    hit = get_sector_kb_codes("半导体")
    assert hit, "半导体应命中映射"
    assert all({"kcode", "title"} <= set(m) for m in hit)
    assert get_sector_kb_codes("芯片") == hit, "别名'芯片'应归一为半导体"
    assert get_sector_kb_codes("科技") == hit, "mega'科技'应归一为半导体"


def test_get_sector_kb_codes_miss_returns_empty():
    from etf_platform.kb.sector_kb_map import get_sector_kb_codes

    assert get_sector_kb_codes("不存在的板块") == []
    assert get_sector_kb_codes("") == []


def test_l34_summary_contains_kb_basis():
    from etf_platform.layers.l34_kb_catalyst import get_kb_catalyst_summary

    summary = get_kb_catalyst_summary("半导体")
    assert "KB依据" in summary
    assert "k811" in summary, "半导体板块首条映射应出现在摘要"


def test_l34_summary_unmapped_sector_no_crash():
    from etf_platform.layers.l34_kb_catalyst import get_kb_catalyst_summary

    summary = get_kb_catalyst_summary("完全无关板块")
    assert isinstance(summary, str)
    assert "KB依据" not in summary


def test_weekly_top3_production_prefers_sector_map():
    mod = _load_weekly_top3()
    reasons = mod._kb_reasons_for_sector("半导体")
    assert reasons, "生产路径应命中板块映射"
    assert reasons[0]["kcode"] == "k811"
    assert all({"kcode", "title"} <= set(r) for r in reasons)
    assert len(reasons) <= 3
