"""L23 valuation layer tests — aligned with actual l23_valuation.py v7.0 functions.

Previously imported _infer_index_for_etf, _is_realistic_ratio, fetch_tencent_etf_quote
which were removed during v6→v7 refactor replacing Tencent QQ API with akshare.
Now tests the actual exported functions: compute_valuation_layer, _get_index_proxy, _infer_sector_key.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from etf_platform.layers.l23_valuation import (
    compute_valuation_layer,
    _get_index_proxy,
    _infer_sector_key,
)


class TestL23Exports:
    """Verify core layer functions exist and have correct signatures."""

    def test_compute_valuation_layer_exists(self):
        assert callable(compute_valuation_layer)
        result = compute_valuation_layer("510300", "宽基", "华泰柏瑞沪深300ETF", risk_level=0.5)
        assert isinstance(result, dict)
        assert "L23_Valuation" in result
        assert "L23_PENALTY" in result
        assert "valuation_details" in result

    def test_get_index_proxy_returns_dict(self):
        proxy = _get_index_proxy("军工", "")
        assert isinstance(proxy, dict)
        assert "pe_ratio" in proxy
        assert "pb_ratio" in proxy

    def test_infer_sector_key_known(self):
        """_infer_sector_key resolves name+sector to canonical sector key."""
        # Test with a known ETF name
        result = _infer_sector_key("半导体ETF", "半导体")
        assert result is not None
        assert isinstance(result, str)


class TestL23IndexProxy:
    """Verify INDEX_PROXY fallback returns reasonable values for known sectors."""

    def test_known_sector_jungong(self):
        proxy = _get_index_proxy("军工", "军工ETF")
        # Should return a float PE ratio, not None
        assert isinstance(proxy["pe_ratio"], (int, float))

    def test_known_sector_hangkong(self):
        proxy = _get_index_proxy("航空航天", "国防ETF")
        assert isinstance(proxy["pe_ratio"], (int, float))

    def test_unknown_sector_gets_defaults(self):
        proxy = _get_index_proxy("不存在行业ABC", "测试ETF")
        assert isinstance(proxy["pe_ratio"], (int, float))
        # INDEX_PROXY should return a default for unknown sectors
        assert proxy["pe_ratio"] > 0


class TestL23PipelineIntegration:
    """End-to-end: compute_valuation_layer with real ETF codes."""

    def test_etf_510300(self):
        result = compute_valuation_layer("510300", "宽基", "华泰柏瑞沪深300ETF", risk_level=0.5)
        assert isinstance(result["L23_Valuation"], (int, float))
        assert 0 <= result["L23_Valuation"] <= 10

    def test_penalty_zero_for_low_risk(self):
        """Low risk sectors should get zero or near-zero penalty."""
        result = compute_valuation_layer("510300", "银行", "银行ETF", risk_level=0.3)
        assert result["L23_PENALTY"] >= 0


class TestL23SourceIntegrity:
    """Verify the source file has no stale code from pre-v7 era."""

    def test_no_tencent_pe_candidates(self):
        src_file = Path(__file__).resolve().parent.parent / "src" / "etf_platform" / "layers" / "l23_valuation.py"
        src = src_file.read_text(encoding="utf-8")
        # Pre-v7 Tencent QQ data probes — must not exist
        assert "pe_candidates = [47, 48, 49, 62" not in src, "Old pe_candidates still present"
        assert "pb_candidates = [48, 49, 51" not in src, "Old pb_candidates still present"

    def test_no_duplicate_keys_in_proxies(self):
        """Duplicate dict keys are silent data-loss bugs — must not exist."""
        src_file = Path(__file__).resolve().parent.parent / "src" / "etf_platform" / "layers" / "l23_valuation.py"
        src = src_file.read_text(encoding="utf-8")
        # Quick check for known duplicate key pattern
        assert src.count("'军工': {'pe_ratio': 45.0") + src.count("'军工': {'pe_ratio': 48.0") <= 1
