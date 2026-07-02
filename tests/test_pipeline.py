import pytest

pytestmark = [pytest.mark.integration]

class TestPipelineCore:
    def test_import_pipeline(self):
        from etf_platform.pipeline import run_full, format_full, batch_full
        assert callable(run_full)
        assert callable(format_full)
        assert callable(batch_full)

    def test_run_full_returns_dict(self, etf_code_chip):
        from etf_platform.pipeline import run_full
        result = run_full(etf_code_chip)
        assert isinstance(result, dict)
        assert result["etf_code"] == etf_code_chip
        assert "layer_scores" in result
        assert "layers" in result

    def test_run_full_has_all_11_layers(self, etf_code_chip):
        from etf_platform.pipeline import run_full
        result = run_full(etf_code_chip)
        scores = result["layer_scores"]
        expected = [
            "L1_ETF", "L2_Holdings", "L3_Material", "L4_SupplyChain",
            "L5_Tech", "L6_Politics", "L7_Irreplaceable",
            "L8_CapitalFlow", "L9_Signals",
            "L10_Demand", "L11_SectorRisk",
        ]
        for layer in expected:
            assert layer in scores, f"Missing layer: {layer}"

    def test_scores_are_numeric(self, etf_code_chip):
        from etf_platform.pipeline import run_full
        result = run_full(etf_code_chip)
        for layer, score in result["layer_scores"].items():
            assert isinstance(score, (int, float))
            assert 0 <= score <= 10

    def test_format_full_returns_string(self, etf_code_chip):
        from etf_platform.pipeline import run_full, format_full
        result = run_full(etf_code_chip)
        report = format_full(result)
        assert isinstance(report, str)
        assert len(report) > 200  # v5.5: format shortened after adapter merge
        assert etf_code_chip in report

    def test_different_etfs_differ(self):
        from etf_platform.pipeline import run_full
        r1 = run_full("159995")
        r2 = run_full("159919")
        s1 = r1["layer_scores"]
        s2 = r2["layer_scores"]
        diffs = sum(1 for k in s1 if s1[k] != s2[k])
        assert diffs >= 2

class TestPipelineBatch:
    def test_batch_full_returns_list(self):
        from etf_platform.pipeline import batch_full
        results = batch_full(limit=3)
        assert isinstance(results, list)
        assert len(results) == 3

    def test_batch_has_all_layers(self):
        from etf_platform.pipeline import batch_full
        results = batch_full(limit=2)
        expected = {
            "L1_ETF", "L2_Holdings", "L3_Material", "L4_SupplyChain",
            "L5_Tech", "L6_Politics", "L7_Irreplaceable",
            "L8_CapitalFlow", "L9_Signals",
            "L10_Demand", "L11_SectorRisk",
        }
        for r in results:
            scores = set(r.get("layer_scores", {}).keys())
            missing = expected - scores
            assert not missing, f"Missing: {missing}"
