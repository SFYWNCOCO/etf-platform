"""Tests for material_bridge.py - L3-L7 signal adjustments."""
import pytest
from etf_platform.analysis.material_bridge import material_layer_adjustments
pytestmark = [pytest.mark.unit]

class TestMaterialBridgeShape:
    def test_returns_dict_with_all_layers(self):
        r = material_layer_adjustments("159995")
        assert isinstance(r, dict)
        exp = {"L3_Material","L4_SupplyChain","L5_Tech","L6_Politics","L7_Irreplaceable"}
        assert exp == set(r.keys())
    def test_all_values_are_float(self):
        for v in material_layer_adjustments("159995").values():
            assert isinstance(v,(int,float))
    def test_values_in_range(self):
        for v in material_layer_adjustments("159995").values():
            assert -3.0 <= v <= 3.0

class TestMaterialBridgeUncovered:
    def test_unknown_etf_zeros_for_non_l7(self):
        """Unknown ETFs get zero adjustments for L3-L6 (no material data)."""
        r = material_layer_adjustments("000000")
        for layer in ("L3_Material", "L4_SupplyChain", "L5_Tech", "L6_Politics"):
            assert r[layer] == 0.0, f"{layer} should be 0.0 for unknown ETF"
    def test_l7_has_jitter_for_unknown_etf(self):
        """L7 gets code-based jitter ±0.6 for ETFs without tech milestone data."""
        r = material_layer_adjustments("000000")
        assert -0.6 <= r["L7_Irreplaceable"] <= 0.6, "L7 jitter should be in [-0.6, +0.6]"
        # Deterministic: same code always gets same jitter
        r2 = material_layer_adjustments("000000")
        assert r["L7_Irreplaceable"] == r2["L7_Irreplaceable"]
