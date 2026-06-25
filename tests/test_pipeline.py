"""Test the pipeline adapter layer."""
import sys
import os

# Add src to path
SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "src")
sys.path.insert(0, SRC)


def test_imports():
    """Verify all adapters import without error."""
    from etf_platform._v7_adapter import run_v7, format_v7
    from etf_platform._v9_adapter import run_v9, format_v9, batch_v9
    from etf_platform._demand_adapter import add_demand_layers
    from etf_platform.pipeline import run_full, format_full, batch_full
    assert callable(run_v7)
    assert callable(run_v9)
    assert callable(add_demand_layers)
    assert callable(run_full)
    print("All imports OK")


def test_full_pipeline():
    """Run full pipeline on a single ETF."""
    from etf_platform.pipeline import run_full
    result = run_full("159995")
    assert result is not None
    assert "etf_code" in result
    assert result["etf_code"] == "159995"
    assert "layer_scores" in result
    print(f"Pipeline OK: {len(result.get('layer_scores', {}))} layers")
    for k, v in result.get("layer_scores", {}).items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    test_imports()
    print("---")
    test_full_pipeline()
