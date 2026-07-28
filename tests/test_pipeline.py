"""Tests for pipeline.py — unified dual-mode penetration pipeline (L1-L24 + L30).
Layer output keys updated to match v8.17+ pipeline (24 layers + metadata).
Uses session-scoped caching to avoid running full pipeline per test (~9s/call).
"""
import pytest

pytestmark = [pytest.mark.unit]

ETF_CODE_CHIP = "159995"  # 芯片ETF
ETF_CODE_HS300 = "510300"  # 沪深300ETF


@pytest.fixture(scope="session")
def chip_result():
    """Session-scoped: run_full once, share across all tests (~9s total vs 45s)."""
    from etf_platform.pipeline import run_full
    return run_full(ETF_CODE_CHIP)


@pytest.fixture(scope="session")
def hs300_result():
    """Session-scoped: 沪深300 result for cross-ETF comparison."""
    from etf_platform.pipeline import run_full
    return run_full(ETF_CODE_HS300)


@pytest.fixture
def etf_code_chip():
    return ETF_CODE_CHIP


class TestPipelineCore:
    def test_import_pipeline(self):
        from etf_platform import pipeline
        assert hasattr(pipeline, "run_full")

    def test_run_full_returns_dict(self, chip_result):
        assert isinstance(chip_result, dict)
        assert chip_result["etf_code"] == ETF_CODE_CHIP
        assert "layer_scores" in chip_result
        assert "layers" in chip_result

    def test_run_full_has_all_12_layers(self, chip_result):
        scores = chip_result["layer_scores"]
        core_layers = [
            "L1_ETF", "L3_Material", "L4_SupplyChain",
            "L5_Tech", "L6_Politics", "L7_Irreplaceable",
            "L8_CapitalFlow", "L9_Signals", "L12_PoliticalRisk",
        ]
        for layer in core_layers:
            assert layer in scores, f"Missing core layer: {layer}"

    def test_scores_are_numeric(self, chip_result):
        for layer, score in chip_result["layer_scores"].items():
            if layer in ("L21_BiasDetail",):
                continue
            assert isinstance(score, (int, float)), f"{layer}={score!r} not numeric"
            assert 0 <= score <= 10, f"{layer}={score} out of range"

    def test_format_full_returns_string(self, chip_result):
        from etf_platform.pipeline import format_full
        report = format_full(chip_result)
        assert isinstance(report, str)
        assert len(report) > 200
        assert ETF_CODE_CHIP in report

    def test_different_etfs_differ(self, chip_result, hs300_result):
        s1 = chip_result["layer_scores"]
        s2 = hs300_result["layer_scores"]
        diffs = sum(1 for k in s1 if k in s2 and s1[k] != s2[k])
        assert diffs >= 2


class TestPipelineBatch:
    def test_batch_full_returns_list(self):
        from etf_platform.pipeline import batch_full
        results = batch_full(limit=3)
        assert hasattr(results, '__iter__'), "batch_full result must be iterable"
        assert hasattr(results, '__len__'), "batch_full result must have len()"
        items = list(results)
        assert len(items) == 3

    def test_batch_has_all_layers(self):
        from etf_platform.pipeline import batch_full
        results = batch_full(limit=2)
        core_layers = {
            "L1_ETF", "L3_Material", "L4_SupplyChain",
            "L5_Tech", "L6_Politics", "L7_Irreplaceable",
            "L8_CapitalFlow", "L9_Signals", "L12_PoliticalRisk",
        }
        for r in results:
            scores = set(r.get("layer_scores", {}).keys())
            missing = core_layers - scores
            assert not missing, f"Missing: {missing}"
