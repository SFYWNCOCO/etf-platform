"""material_price_refresh 双源刷新 — 纯函数单元测试 (cc_batch_t5).

覆盖:
- 品种→Sina 合约映射查询 (只覆盖脚本实际命中过的品种; 未映射返回 None)
- Sina 批量行情 URL 构建
- hq.sinajs.cn 返回文本解析归一 (nf_ 连续合约字段: [8]最新价 [10]昨结算兜底)
- 空 payload / 双价无效条目跳过
不写依赖真实网络的测试; 网络路径靠 --dry-run 人工验证。
"""
import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"

_LC_ROW = ("碳酸锂连续,112959,150980.000,154940.000,148320.000,0.000,"
           "153420.000,153480.000,153420.000,0.000,153960.000,15,6,"
           "359168.000,165967,,碳酸锂,2026-08-26,1,,,,,,,,,152086.252,"
           "0.000,0,0.000,0,0.000,0,0.000,0,0.000,0,0.000,0,0.000,0,0.000,0")


def _load_script():
    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))
    spec = importlib.util.spec_from_file_location(
        "material_price_refresh", ROOT / "scripts" / "material_price_refresh.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _load_script()


class TestSinaCodeMapping:
    def test_known_base_maps_to_contract(self):
        assert mod._sina_code_for_base("碳酸锂") == "LC"
        assert mod._sina_code_for_base("玉米") == "C"

    def test_never_hit_base_returns_none(self):
        # 铜为美元计价从未成功刷过 → 不建映射, 兜底不适用
        assert mod._sina_code_for_base("铜") is None

    def test_quote_url_format(self):
        url = mod._sina_quote_url(["LC", "AL"])
        assert url == "https://hq.sinajs.cn/list=nf_LC0,nf_AL0"


class TestParseSinaFutures:
    def test_parse_normal_row(self):
        out = mod._parse_sina_futures(f'var hq_str_nf_LC0="{_LC_ROW}";')
        assert out["nf_LC0"]["name"] == "碳酸锂连续"
        assert out["nf_LC0"]["price"] == pytest.approx(153420.0)

    def test_parse_empty_payload_skipped(self):
        # hf_ 前缀接口实测返回空串 → 必须跳过而非报错
        assert mod._parse_sina_futures('var hq_str_hf_LC0="";') == {}

    def test_parse_uses_prev_settle_when_last_zero(self):
        row = ("铝连续,113000,23730.000,24075.000,23720.000,0.000,"
               "0.000,0.000,0.000,0.000,23800.000,13,1,261027.000,"
               "186136,沪,铝,2026-08-26,1")
        out = mod._parse_sina_futures(f'var hq_str_nf_AL0="{row}";')
        assert out["nf_AL0"]["price"] == pytest.approx(23800.0)

    def test_parse_both_prices_invalid_skipped(self):
        row = "螺纹钢连续,113000,0.000,0.000,0.000,0.000,0.000,0.000,0.000,0.000,0.000,0,0,0.000,0,沪,螺纹钢,2026-08-26,1"
        assert mod._parse_sina_futures(f'var hq_str_nf_RB0="{row}";') == {}

    def test_parse_multi_lines_keeps_only_valid(self):
        raw = f'var hq_str_nf_LC0="{_LC_ROW}";\nvar hq_str_nf_AL0="";'
        out = mod._parse_sina_futures(raw)
        assert list(out) == ["nf_LC0"]


class TestConvertSinaPrice:
    def test_sina_price_ton_to_wan_ton(self):
        # Sina 期货价为元/吨 → yaml 万元/吨 (碳酸锂场景)
        assert mod._convert_current(153420.0, "元/吨", "万元/吨") == "15.34万元/吨"

    def test_sina_price_ton_to_ton(self):
        assert mod._convert_current(2299.0, "元/吨", "元/吨") == "2,299元/吨"
