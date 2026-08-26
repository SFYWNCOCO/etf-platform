"""推荐引擎修复专项测试：
1. weekly_top3 强看空永否决（旧闻衰减后不该被永久排除）
2. two_week_picker 动态因子权重死代码（_get_factor_weights 此前从未被调用）
3. two_week_picker 候选池 yaml 顺序截断（尾部行业整段饿死）
"""
import types

import pytest

pytestmark = [pytest.mark.unit]


def _trend(**kw):
    defaults = {
        "change_5d": 1.0, "change_10d": 1.0, "change_20d": 2.0,
        "position_pct": 40.0, "max_drawdown": -5.0, "volatility_20d": 20.0,
        "volume_ratio_5_20": 1.2, "trend_signal": "neutral",
    }
    defaults.update(kw)
    return types.SimpleNamespace(**defaults)


class TestWeeklyTop3StrongBearishVeto:
    """修复前：news_label==🔴强看空 → 无条件过滤，旧闻永久锁死板块。

    修复后：仅新鲜强看空（news_adjustment <= -2.5，即 decay>=0.5）排除；
    旧闻已在 adjusted_momentum 里按 -5.0*decay 减分，不该整段删除。
    """
    def _run(self, news_signals):
        import weekly_top3 as wt
        # 每板块 3 只（_get_top_mega_sectors 要求 >=3 才算中位数动量）
        mega_sectors = {
            "科技": [("512480", "半导体ETF", "半导体"), ("512481", "芯片ETF", "半导体"),
                     ("512482", "科创芯片ETF", "半导体")],
            "新能源": [("516160", "新能源ETF", "新能源"), ("516161", "光伏ETF", "新能源"),
                      ("516162", "储能ETF", "新能源")],
            "消费": [("510150", "消费ETF", "消费"), ("510151", "家电ETF", "消费"),
                    ("510152", "食品ETF", "消费")],
        }
        trends = {c: _trend(change_20d=2.0) for c in ("512480", "512481", "512482")}
        trends.update({c: _trend(change_20d=3.0) for c in ("516160", "516161", "516162")})
        trends.update({c: _trend(change_20d=1.0) for c in ("510150", "510151", "510152")})
        code_to_sector = {c: "半导体" for c in ("512480", "512481", "512482")}
        code_to_sector.update({c: "新能源" for c in ("516160", "516161", "516162")})
        code_to_sector.update({c: "消费" for c in ("510150", "510151", "510152")})
        return wt._get_top_mega_sectors(
            mega_sectors, trends, code_to_sector, news_signals=news_signals, top_n=3
        )

    def test_stale_strong_bearish_not_excluded(self):
        """旧闻（fresh_days=8, decay=0.1）强看空只减 -0.5，不应被排除。"""
        news = {
            "科技": {"direction": "看空", "strength": "强", "fresh_days": 8},
            "消费": {"direction": "中性", "strength": "弱", "fresh_days": 1},
        }
        out = self._run(news)
        sectors = [s for s, _ in out]
        assert "科技" in sectors, "旧闻强看空板块被永久排除"
        tech = [d for s, d in out if s == "科技"]
        assert tech and tech[0]["news_adjustment"] == -0.5, \
            f"衰减后 news_adjustment 应为 -0.5, 实得 {tech[0]['news_adjustment'] if tech else None}"

    def test_fresh_strong_bearish_excluded(self):
        """新鲜强看空（decay=1.0, news_adjustment=-5.0）仍应排除。"""
        news = {
            "新能源": {"direction": "看空", "strength": "强", "fresh_days": 1},
            "消费": {"direction": "中性", "strength": "弱", "fresh_days": 1},
        }
        out = self._run(news)
        sectors = [s for s, _ in out]
        assert "新能源" not in sectors, "新鲜强看空板块应被排除"
        assert "消费" in sectors

    def test_all_fresh_strong_bearish_empty(self):
        """全池新鲜强看空 → 无推荐（不崩）。"""
        news = {
            "科技": {"direction": "看空", "strength": "强", "fresh_days": 0},
            "新能源": {"direction": "看空", "strength": "强", "fresh_days": 0},
            "消费": {"direction": "看空", "strength": "强", "fresh_days": 0},
        }
        out = self._run(news)
        assert out == []


class TestTwoWeekPickerDynamicWeights:
    """修复前：_get_factor_weights(qvix_regime) 定义了但从未调用，
    composite 用静态 FACTORS weight → QVIX 市场状态切换无效果。
    """
    def test_scores_use_dynamic_weights(self, monkeypatch):
        from etf_platform.decision import two_week_picker as tw

        captured = {}

        def fake_weights(qvix_regime, debug=False):
            captured["regime"] = qvix_regime
            # 只有 risk_adj_momentum 有权重 → composite = z(1.0)*1.0 = 1.0
            return {
                "oversold_depth": 0.0, "risk_adj_momentum": 1.0,
                "drawdown_recov": 0.0, "sector_flow": 0.0,
                "quality_elastic": 0.0, "behavioral": 0.0,
                "news_sentiment": 0.0,
            }

        monkeypatch.setattr(tw, "_get_factor_weights", fake_weights)
        monkeypatch.setattr(
            "etf_platform.decision.prediction_monitor.log_prediction",
            lambda *a, **k: None,
        )

        z_factors = {f["name"]: [1.0] for f in tw.FACTORS}
        candidates = [("512480", {"sector": "半导体", "name": "半导体ETF", "risk_level": 0.5})]
        pipe_map = {"512480": {"score": 5.0, "tournament_winner": False, "layer_scores": {}}}
        trend_map = {"512480": _trend()}
        scored_indices = [0]

        top3, _ = tw._compute_scores_and_rank(
            z_factors, candidates, pipe_map, trend_map, scored_indices,
            profile="均衡", qvix_regime="fearful",
        )
        assert captured.get("regime") == "fearful", "动态权重未收到 QVIX regime"
        assert top3 and top3[0]["z_composite"] == 1.0, \
            f"应按动态权重得 1.0, 实得 {top3[0]['z_composite'] if top3 else None}"

    def test_default_regime_normal_when_absent(self, monkeypatch):
        """不传 qvix_regime → 默认 normal。"""
        from etf_platform.decision import two_week_picker as tw
        captured = {}

        def fake_weights(qvix_regime, debug=False):
            captured["regime"] = qvix_regime
            return {f["name"]: f["weight"] for f in tw.FACTORS}

        monkeypatch.setattr(tw, "_get_factor_weights", fake_weights)
        monkeypatch.setattr(
            "etf_platform.decision.prediction_monitor.log_prediction",
            lambda *a, **k: None,
        )
        z_factors = {f["name"]: [1.0] for f in tw.FACTORS}
        candidates = [("512480", {"sector": "半导体", "name": "半导体ETF", "risk_level": 0.5})]
        pipe_map = {"512480": {"score": 5.0, "tournament_winner": False, "layer_scores": {}}}
        tw._compute_scores_and_rank(
            z_factors, candidates, pipe_map, {"512480": _trend()}, [0],
        )
        assert captured.get("regime") == "normal"


class TestCandidatePoolSectorBalance:
    """修复前：candidates[:max_candidates] 按 etfs.yaml 键序截断——
    排在 yaml 尾部的行业整段饿死，候选池行业单一会破坏池内 Z-score 基准。
    """
    def _etfs(self):
        etfs = {}
        for i in range(20):  # 半导体 20 只
            etfs[f"5124{i:02d}"] = {
                "name": f"半导体ETF{i}", "sector": "半导体",
                "type": "股票ETF", "access": "buyable",
            }
        for i in range(20):  # 消费 20 只
            etfs[f"5156{i:02d}"] = {
                "name": f"消费ETF{i}", "sector": "消费",
                "type": "股票ETF", "access": "buyable",
            }
        return etfs

    def test_truncation_keeps_sector_diversity(self):
        from etf_platform.decision import two_week_picker as tw
        pool = tw._build_candidate_pool(self._etfs(), "normal", max_candidates=10)
        sectors = {info.get("sector") for _, info in pool}
        assert sectors == {"半导体", "消费"}, \
            f"轮询截断应保留两行业, 实得 {sectors}"

    def test_under_cap_no_truncation(self):
        from etf_platform.decision import two_week_picker as tw
        pool = tw._build_candidate_pool(self._etfs(), "normal", max_candidates=40)
        assert len(pool) == 40  # 40 只全保留

    def test_cap_is_hard_boundary(self):
        """轮询不能整轮超发——cap 是硬上限（40 只里取 7 必须正好 7 只）。"""
        from etf_platform.decision import two_week_picker as tw
        pool = tw._build_candidate_pool(self._etfs(), "normal", max_candidates=7)
        assert len(pool) == 7, f"轮询超发, 实得 {len(pool)}"
        assert len({info.get("sector") for _, info in pool}) >= 2  # 仍跨行业

    def test_qvix_filter_still_applies(self):
        from etf_platform.decision import two_week_picker as tw
        pool = tw._build_candidate_pool(self._etfs(), "fearful", max_candidates=40)
        sectors = {info.get("sector") for _, info in pool}
        assert sectors == {"消费"}  # 恐惧市排除半导体
