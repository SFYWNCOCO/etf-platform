"""strategy_tournament 专项测试（审计补审：此模块原仅[inference]审阅，无测试）。

覆盖：Z-score策略最小样本守卫/行业去重、纯动量排序、Thompson Sampling
权重先验与归一化、bandit α/β 更新。
"""
import types

import pytest

pytestmark = [pytest.mark.unit]

DEFAULT_WEIGHTS = {
    "mean_reversion": 0.20, "zscore_multi": 0.20, "momentum": 0.20,
    "capital_flow": 0.20, "consensus": 0.20,
}


def _trend(change_20d=2.0, vol=20.0, dd=-5.0, days=60):
    return types.SimpleNamespace(
        data_days=days, change_20d=change_20d, change_10d=change_20d / 2,
        volatility_20d=vol, max_drawdown=dd,
    )


def _cand(code, sector, name=None):
    return (code, {"sector": sector, "name": name or f"ETF{code}"})


def _pipe(code, score=5.0):
    return {code: {"score": score}}


def _three_sector_inputs():
    """3 个行业 6 只候选，全部有效。"""
    cands = [
        _cand("512480", "半导体", "半导体ETF"),
        _cand("512481", "半导体", "芯片ETF"),
        _cand("516160", "新能源", "新能源ETF"),
        _cand("516161", "新能源", "光伏ETF"),
        _cand("510150", "消费", "消费ETF"),
        _cand("510151", "消费", "食品ETF"),
    ]
    trends = {
        "512480": _trend(3.0, 25), "512481": _trend(1.0, 20),
        "516160": _trend(2.0, 30), "516161": _trend(0.5, 25),
        "510150": _trend(-1.0, 15), "510151": _trend(-2.0, 12),
    }
    pipes = {c: _pipe(c)[c] for c in trends}
    return cands, trends, pipes


class TestZscoreStrategy:
    def test_requires_3_valid(self):
        from etf_platform.decision import strategy_tournament as st
        cands = [_cand("512480", "半导体"), _cand("516160", "新能源")]
        r = st._zscore_strategy(
            {c: _trend() for c, _ in cands}, _pipe("512480"), cands)
        assert r.picks == [] and r.all_scored == []

    def test_sector_dedup_top3(self):
        from etf_platform.decision import strategy_tournament as st
        cands, trends, pipes = _three_sector_inputs()
        r = st._zscore_strategy(trends, pipes, cands)
        assert len(r.picks) <= 3
        sectors = [p["sector"] for p in r.picks]
        assert len(set(sectors)) == len(sectors), "Top3 行业必须去重"
        assert len(r.all_scored) >= 3

    def test_skips_insufficient_data(self):
        from etf_platform.decision import strategy_tournament as st
        cands, trends, pipes = _three_sector_inputs()
        # 512480 data_days 不足 → 被跳过
        trends["512480"] = _trend(days=5)
        r = st._zscore_strategy(trends, pipes, cands)
        assert all(p["code"] != "512480" for p in r.all_scored)


class TestMomentumStrategy:
    def test_ranks_by_risk_adjusted_return(self):
        from etf_platform.decision import strategy_tournament as st
        cands = [_cand("aaa", "半导体"), _cand("bbb", "新能源")]
        # aaa: 4/10=0.4; bbb: 3/40=0.075 → aaa 第一
        trends = {"aaa": _trend(4.0, 10), "bbb": _trend(3.0, 40)}
        r = st._momentum_strategy(trends, {}, cands)
        assert r.all_scored[0]["code"] == "aaa"
        assert r.all_scored[0]["score"] > r.all_scored[1]["score"]

    def test_zero_vol_guard(self):
        """波动率 0 → max(vol,1) 兜底，不除零崩溃。"""
        from etf_platform.decision import strategy_tournament as st
        cands = [_cand("aaa", "半导体"), _cand("bbb", "新能源")]
        trends = {"aaa": _trend(2.0, 0), "bbb": _trend(2.0, 0)}
        r = st._momentum_strategy(trends, {}, cands)
        assert len(r.all_scored) == 2


class TestThompsonSamplingWeights:
    def test_falls_back_to_prior(self):
        """无 bandit 数据时用 regime 先验（fearful → momentum 0.40）。"""
        from etf_platform.decision import strategy_tournament as st
        st._TS_BANDITS.clear()
        w = st._get_ts_weights("fearful")
        assert w["momentum"] == pytest.approx(0.40, abs=0.001)

    def test_default_regime_weights(self):
        from etf_platform.decision import strategy_tournament as st
        w = st._get_ts_weights("nonexistent_regime")
        assert set(w.keys()) == set(DEFAULT_WEIGHTS.keys())

    def test_bandit_weights_normalize_to_1(self, monkeypatch):
        """有 bandit 数据时权重归一化到 1；随机源固定后结果确定。"""
        from etf_platform.decision import strategy_tournament as st
        st._TS_BANDITS.clear()
        st._update_ts_bandit("normal", "momentum", win=True)
        st._update_ts_bandit("normal", "momentum", win=True)
        st._update_ts_bandit("normal", "momentum", win=False)
        monkeypatch.setattr("random.betavariate", lambda a, b: 0.5)
        w = st._get_ts_weights("normal")
        assert sum(w.values()) == pytest.approx(1.0, abs=0.01)

    def test_bandit_alpha_beta_update(self):
        from etf_platform.decision import strategy_tournament as st
        st._TS_BANDITS.clear()
        st._update_ts_bandit("fearful", "zscore_multi", win=True)
        st._update_ts_bandit("fearful", "zscore_multi", win=True)
        st._update_ts_bandit("fearful", "zscore_multi", win=False)
        b = st._TS_BANDITS["fearful"]["zscore_multi"]
        assert b["alpha"] == 3.0  # 1 + 2 wins
        assert b["beta"] == 2.0   # 1 + 1 loss
        assert b["samples"] == 3
