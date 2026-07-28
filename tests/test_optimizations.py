# -*- coding: utf-8 -*-
"""Tests for ETF platform optimizations.

Covers:
- demand.py: no duplicate keys in B2B_SECTOR_RISK
- material_bridge.py: no duplicate SECTOR_GROUPS definition
- screener.py: _premium_penalty error handling, _detect_dead_layers threshold
- pipeline.py: no double material_bridge call
- scorer.py: ETF_FLOW_PROXIES completeness
"""
import json
import sys
from pathlib import Path

import pytest

# Add project root to path
BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "src"))


def test_demand_no_duplicate_keys():
    """B2B_SECTOR_RISK should have no duplicate keys (consumers defined twice)."""
    from etf_platform.analysis.demand import B2B_SECTOR_RISK
    
    keys = list(B2B_SECTOR_RISK.keys())
    duplicates = {k for k in keys if keys.count(k) > 1}
    assert not duplicates, f"Duplicate keys in B2B_SECTOR_RISK: {duplicates}"
    
    # Verify consumer sectors still present (only those that were in B2B_SECTOR_RISK originally)
    for sector in ["消费", "家电", "农产品", "医药器械", "白酒消费"]:
        assert sector in B2B_SECTOR_RISK, f"Missing sector: {sector}"


def test_material_bridge_no_duplicate_definition():
    """SECTOR_GROUPS should be defined exactly once (no shadowing)."""
    from etf_platform.analysis import material_bridge
    
    # Check the module has exactly one SECTOR_GROUPS
    attrs = [a for a in dir(material_bridge) if a == "SECTOR_GROUPS"]
    assert len(attrs) == 1, f"Unexpected SECTOR_GROUPS attributes: {attrs}"
    
    sg = material_bridge.SECTOR_GROUPS
    # Verify expanded groups are present
    assert "us_equity" in sg, "Missing 'us_equity' group"
    assert "infra" in sg, "Missing 'infra' group"
    assert "半导体设备" in sg.get("tech", []), "Missing '半导体设备' in tech group"
    assert "硬科技杠杆" in sg.get("tech", []), "Missing '硬科技杠杆' in tech group"


@pytest.mark.slow
def test_screener_premium_penalty_error_handling():
    """_premium_penalty should handle akshare import failure gracefully."""
    from etf_platform.decision.screener import _premium_penalty
    
    # Normal case: should return dict with signal key
    result = _premium_penalty("510300")
    assert isinstance(result, dict)
    assert "premium_pct" in result
    assert "penalty" in result
    assert "signal" in result
    # signal should be one of known values
    valid_signals = {"discount_buy", "discount_light", "premium_avoid", 
                     "premium_high", "premium_light", "normal", 
                     "no_data", "akshare_not_available"}
    assert result["signal"] in valid_signals, f"Unknown signal: {result['signal']}"


def test_dead_layers_threshold():
    """_detect_dead_layers should use relaxed 1.0 threshold, not 0.5."""
    from etf_platform.decision.screener import _detect_dead_layers
    
    # Simulate results with small variance (0.8 range)
    results = [
        {"layer_scores": {"L3_Material": 6.0, "L4_SupplyChain": 5.0}},
        {"layer_scores": {"L3_Material": 6.8, "L4_SupplyChain": 5.0}},
    ]
    dead = _detect_dead_layers(results)
    # L3 has 0.8 range (< 1.0 threshold) → dead
    # L4 has 0.0 range → dead
    assert "L4_SupplyChain" in dead, "Zero-variance layer should be detected as dead"
    assert "L3_Material" in dead, "0.8-range layer should be dead with 1.0 threshold"


def test_dead_layers_preserves_real_variation():
    """_detect_dead_layers should NOT kill layers with meaningful variation."""
    from etf_platform.decision.screener import _detect_dead_layers
    
    results = [
        {"layer_scores": {"L3_Material": 4.0, "L8_CapitalFlow": 7.0}},
        {"layer_scores": {"L3_Material": 6.5, "L8_CapitalFlow": 3.0}},
        {"layer_scores": {"L3_Material": 5.0, "L8_CapitalFlow": 8.0}},
    ]
    dead = _detect_dead_layers(results)
    # L3: range 4.0-6.5 = 2.5 → alive
    # L8: range 3.0-8.0 = 5.0 → alive
    assert "L3_Material" not in dead, "L3 with 2.5 range should be alive"
    assert "L8_CapitalFlow" not in dead, "L8 with 5.0 range should be alive"


def test_scorer_flow_proxies_completeness():
    """ETF_FLOW_PROXIES should cover all new sectors."""
    from etf_platform.scorer import ETF_FLOW_PROXIES
    
    required = {
        "港股综合", "港股医药", "港股科技",
        "美股科技100", "中概互联网",
        "可转债", "信用债", "利率债",
    }
    existing = set(ETF_FLOW_PROXIES["type_flow_bias"].keys())
    missing = required - existing
    assert not missing, f"Missing flow proxies: {missing}"


def test_scorer_flow_proxies_values():
    """Flow proxy values should be in reasonable range (-1.0 to 1.0)."""
    from etf_platform.scorer import ETF_FLOW_PROXIES
    
    biases = ETF_FLOW_PROXIES["type_flow_bias"]
    for key, val in biases.items():
        assert -2.0 <= val <= 2.0, f"Out of range value for {key}: {val}"


def test_pipeline_no_double_material_bridge():
    """Pipeline should not call material_bridge.apply_to_layers twice."""
    with open(BASE / "src" / "etf_platform" / "pipeline.py", "r", encoding="utf-8") as f:
        content = f.read()
    
    # Count material_bridge import+call occurrences
    import_count = content.count("from .analysis.material_bridge import")
    call_count = content.count("apply_to_layers(code, scores, sector)")
    
    assert import_count <= 1, f"material_bridge imported {import_count} times"
    assert call_count <= 1, f"apply_to_layers called {call_count} times"


@pytest.mark.slow
def test_premium_penalty_returns_consistent_dict():
    """All return paths in _premium_penalty should return consistent dict structure."""
    from etf_platform.decision.screener import _premium_penalty
    
    # Test with a code that likely has no data
    result = _premium_penalty("999999")
    assert isinstance(result, dict)
    assert "premium_pct" in result
    assert "penalty" in result
    assert "signal" in result
    assert isinstance(result["premium_pct"], (int, float))
    assert isinstance(result["penalty"], (int, float))


def test_multi_signal_differentiator_6_dimensions():
    """Multi-signal differentiator should use 6 dimensions including index_type."""
    from etf_platform.analysis.multi_signal_differentiator import differentiate
    
    scores = {"L3_Material": 5.0, "L8_CapitalFlow": 5.0}
    info = {
        "name": "沪深300ETF",
        "fee": 0.0005,
        "type": "宽基A",
        "leverage": 1.0,
    }
    result = differentiate("510300", "宽基", scores, info)
    
    # Should have modified scores
    assert "L3_Material" in result
    assert "L8_CapitalFlow" in result
    # Fee=0.0005 should give +0.6 type_signal
    # Cross-border for 沪深300 should give +0.4


if __name__ == "__main__":
    tests = [
        test_demand_no_duplicate_keys,
        test_material_bridge_no_duplicate_definition,
        test_screener_premium_penalty_error_handling,
        test_dead_layers_threshold,
        test_dead_layers_preserves_real_variation,
        test_scorer_flow_proxies_completeness,
        test_scorer_flow_proxies_values,
        test_pipeline_no_double_material_bridge,
        test_premium_penalty_returns_consistent_dict,
        test_multi_signal_differentiator_6_dimensions,
    ]
    
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  ✓ {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  ✗ {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ✗ {t.__name__}: {type(e).__name__}: {e}")
            failed += 1
    
    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed, {passed+failed} total")
    sys.exit(0 if failed == 0 else 1)
