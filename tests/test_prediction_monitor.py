"""prediction_monitor evaluate_prediction 专项测试（K线锚点 + 修复后 cohort 隔离）。

修复后 cohort（≥2026-08-10 引擎产出的预测）从总命中率中单独统计，
避免前视偏差引擎的旧样本稀释新引擎的真实表现。
"""
import json
from datetime import date, timedelta

import pytest

pytestmark = [pytest.mark.unit]


def _pred(date_str, profile="均衡", codes=("512480", "518880")):
    return {
        "date": date_str, "profile": profile,
        "top3": [{"code": c, "name": f"ETF{c}", "two_week_score": 80 - i}
                 for i, c in enumerate(codes)],
    }


def _write_log(tmp_path, preds):
    p = tmp_path / "two_week_predictions.jsonl"
    p.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in preds) + "\n", encoding="utf-8")
    return p


class TestEvaluateHitRate:
    def _run(self, log_path, returns):
        from etf_platform.decision import prediction_monitor as pm
        pm.LOG_FILE = log_path
        pm._return_since = lambda d, c, h=10: returns.get(c)
        return pm.evaluate_prediction()

    def test_hit_rate_uses_anchor_returns(self, tmp_path):
        log = _write_log(tmp_path, [
            _pred("2026-07-20", codes=("AAA", "BBB")),
        ])
        res = self._run(log, {"AAA": 3.0, "BBB": -2.0})
        assert res["total_predictions"] == 2
        assert res["hits"] == 1
        assert res["hit_rate"] == 50.0

    def test_recent_prediction_excluded(self, tmp_path):
        """5 天内预测不可验证 → 跳过。"""
        from etf_platform.decision import prediction_monitor as pm
        recent_date = (date.today() - timedelta(days=2)).isoformat()
        log = _write_log(tmp_path, [_pred(recent_date, codes=("AAA",))])
        pm.LOG_FILE = log
        pm._return_since = lambda d, c, h=10: 1.0
        res = pm.evaluate_prediction()
        assert res.get("total_predictions", 0) == 0 or "error" in res

    def test_none_return_skipped(self, tmp_path):
        """K线数据不足返回 None → 不计入命中率分母。"""
        log = _write_log(tmp_path, [
            _pred("2026-07-20", codes=("AAA", "BBB")),
        ])
        res = self._run(log, {"AAA": 1.0, "BBB": None})
        assert res["total_predictions"] == 1
        assert res["hits"] == 1


class TestPostFixCohort:
    def _run(self, log_path, returns, today, monkeypatch):
        from etf_platform.decision import prediction_monitor as pm
        from datetime import date as _date

        class FakeDate(_date):
            @classmethod
            def today(cls):
                return _date.fromisoformat(today)

        monkeypatch.setattr(pm, "date", FakeDate)
        pm.LOG_FILE = log_path
        pm._return_since = lambda d, c, h=10: returns.get(c, 0.0)
        return pm.evaluate_prediction()

    def test_cohort_isolates_fixed_engine(self, tmp_path, monkeypatch):
        """旧(07月)样本 50%，新(≥08-10)样本 100% → 总命中率 < 修复后命中率。"""
        log = _write_log(tmp_path, [
            _pred("2026-07-20", codes=("A1", "A2")),   # 旧: 全错
            _pred("2026-08-10", codes=("B1", "B2")),   # 新: 全对
        ])
        returns = {"A1": -1.0, "A2": -1.0, "B1": 2.0, "B2": 2.0}
        # 模拟"今天"为 08-25：两条预测都已过 5 天验证期
        res = self._run(log, returns, "2026-08-25", monkeypatch)
        pf = res["post_fix_cohort"]
        # 旧 2 只全错 + 新 2 只全对 → 总 50%
        assert res["hit_rate"] == 50.0
        # 修复后 cohort 只含 ≥08-10 的 2 只 → 100%
        assert pf["count"] == 2
        assert pf["hits"] == 2
        assert pf["hit_rate"] == 100.0

    def test_empty_cohort_when_no_fix_predictions(self, tmp_path, monkeypatch):
        log = _write_log(tmp_path, [_pred("2026-07-20", codes=("A1",))])
        res = self._run(log, {"A1": 1.0}, "2026-08-25", monkeypatch)
        assert res["post_fix_cohort"]["count"] == 0
