"""factor_ic 诊断模块 + log_prediction 因子持久化回归测试 (08-12).

覆盖:
- spearman_ic 秩相关数学正确性 (完美正/负相关、零方差、并列秩)
- compute_factor_ic 对 mock 预测的 n/IC 计算
- _load_predictions 跳过损坏行
- prediction_monitor.log_prediction 持久化 z_factors (回归: 原丢弃导致
  factor_ic 只有 3/87 条有效样本)
"""
import json

import pytest

pytestmark = [pytest.mark.unit]


class TestSpearmanIc:
    def test_perfect_positive(self):
        from etf_platform.analysis.factor_ic import spearman_ic

        assert spearman_ic([1, 2, 3, 4, 5], [1, 2, 3, 4, 5]) == pytest.approx(1.0)

    def test_perfect_negative(self):
        from etf_platform.analysis.factor_ic import spearman_ic

        assert spearman_ic([1, 2, 3, 4, 5], [5, 4, 3, 2, 1]) == pytest.approx(-1.0)

    def test_zero_variance_returns_none(self):
        from etf_platform.analysis.factor_ic import spearman_ic

        assert spearman_ic([1, 2, 3, 4, 5], [1, 1, 1, 1, 1]) is None

    def test_too_few_samples_returns_none(self):
        from etf_platform.analysis.factor_ic import spearman_ic

        assert spearman_ic([1, 2], [1, 2]) is None

    def test_ties_no_crash(self):
        from etf_platform.analysis.factor_ic import spearman_ic

        ic = spearman_ic([1, 1, 2, 2, 3, 3], [1, 2, 1, 3, 2, 3])
        assert ic is not None
        assert -1.0 <= ic <= 1.0


class TestLoadPredictions:
    def test_skips_corrupt_lines(self, tmp_path):
        from etf_platform.analysis.factor_ic import _load_predictions

        f = tmp_path / "log.jsonl"
        f.write_text(
            '{"date": "2026-07-18", "top3": []}\n'
            "this is not json\n"
            '{"date": "2026-07-19", "top3": []}\n',
            encoding="utf-8",
        )
        recs = _load_predictions(f)
        assert len(recs) == 2

    def test_missing_file_returns_empty(self, tmp_path):
        from etf_platform.analysis.factor_ic import _load_predictions

        assert _load_predictions(tmp_path / "none.jsonl") == []


class TestComputeFactorIc:
    def _preds(self):
        """12 个 (code, ret, oversold_depth) 分布到 4 次预测 × 3 top3."""
        od = list(range(12))           # 单调升 → 与 ret 完全正相关
        rets = [x * 0.5 + 1.0 for x in od]
        preds = []
        for rec in range(4):
            top3 = []
            for j in range(3):
                i = rec * 3 + j
                top3.append({"code": f"C{i}", "z_factors": {
                    "oversold_depth": float(od[i]),
                    "risk_adj_momentum": float(od[i] * 2),
                    "drawdown_recov": float(-od[i]),
                    "sector_flow": 0.0,
                    "quality_elastic": float(od[i] % 2),
                    "behavioral": float(od[i] % 2),
                }})
            preds.append({"date": f"2026-07-{18 + rec:02d}", "top3": top3})
        return preds, {f"C{i}": rets[i] for i in range(12)}

    def test_ic_matches_expected(self):
        from etf_platform.analysis.factor_ic import compute_factor_ic

        preds, ret_map = self._preds()
        result = compute_factor_ic(preds, lambda c, d: ret_map[c])

        f = result["factors"]
        assert f["oversold_depth"]["n"] == 12
        assert f["oversold_depth"]["ic"] == pytest.approx(1.0, abs=1e-6)
        # 完全反向
        assert f["drawdown_recov"]["ic"] == pytest.approx(-1.0, abs=1e-6)
        # 同序等比
        assert f["risk_adj_momentum"]["ic"] == pytest.approx(1.0, abs=1e-6)
        # 全零因子 → 方差 0 → ic None (不崩)
        assert f["sector_flow"]["ic"] is None
        assert f["sector_flow"]["n"] == 12

    def test_total_pairs(self):
        from etf_platform.analysis.factor_ic import compute_factor_ic

        preds, ret_map = self._preds()
        result = compute_factor_ic(preds, lambda c, d: ret_map[c])
        assert result["total_pairs"] == 4  # 预测次数

    def test_return_none_excluded(self):
        from etf_platform.analysis.factor_ic import compute_factor_ic

        preds, _ = self._preds()
        # return_fn 全返回 None → 因子 n=0
        result = compute_factor_ic(preds, lambda c, d: None)
        assert result["factors"]["oversold_depth"]["n"] == 0
        assert result["factors"]["oversold_depth"]["ic"] is None


class TestLogPredictionPersistsZFactors:
    def test_z_factors_written(self, tmp_path, monkeypatch):
        from etf_platform.decision import prediction_monitor as pm

        monkeypatch.setattr(pm, "DATA_DIR", tmp_path)
        monkeypatch.setattr(pm, "LOG_FILE", tmp_path / "two_week_predictions.jsonl")
        pred = {
            "code": "159995", "name": "芯片ETF", "sector": "半导体",
            "two_week_score": 72, "pipeline_score": 5.9, "z_composite": 0.6,
            "z_factors": {"oversold_depth": 1.0, "risk_adj_momentum": 0.5,
                          "drawdown_recov": -1.0, "sector_flow": 0.0,
                          "quality_elastic": 0.3, "behavioral": 0.0},
            "trend_signal": "neutral", "change_20d": 12.7, "return_10d": -2.5,
        }
        pm.log_prediction([pred], "均衡")
        records = [json.loads(l) for l in
                   (tmp_path / "two_week_predictions.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        assert len(records) == 1
        assert records[0]["top3"][0]["z_factors"]["oversold_depth"] == 1.0
        assert records[0]["top3"][0]["sector"] == "半导体"

    def test_same_day_profile_dedup(self, tmp_path, monkeypatch):
        """同日同 profile 幂等: 二次记录不重复加权."""
        from etf_platform.decision import prediction_monitor as pm

        monkeypatch.setattr(pm, "DATA_DIR", tmp_path)
        monkeypatch.setattr(pm, "LOG_FILE", tmp_path / "two_week_predictions.jsonl")
        pred = {"code": "159995", "name": "芯片ETF", "sector": "半导体",
                "two_week_score": 72, "pipeline_score": 5.9, "z_composite": 0.6,
                "z_factors": {}, "trend_signal": "neutral",
                "change_20d": 12.7, "return_10d": -2.5}
        pm.log_prediction([pred], "均衡")
        pm.log_prediction([pred], "均衡")
        lines = [l for l in
                 (tmp_path / "two_week_predictions.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        assert len(lines) == 1, "同日同 profile 应覆盖旧记录"
