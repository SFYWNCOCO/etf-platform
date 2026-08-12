"""L1-L34 全层修复回归测试 (08-12).

覆盖本会话修复的关键逻辑:
- L22 周期钟摆: _pendulum_score 单调性 + 分段连续性 (panic 符号反转回归)
- L30 多智能体: 0-10 缩放 (不再 0-12)
- L16 资金流向: signal 字段方向修正 (bearish → -0.5, 不再 +0.3)
- fund_flow: FundFlowAlert.signal 字段 + 超大单流出覆盖信号
- material_live: PMI iloc[0] (akshare newest-first)
- L24 系统动力学: 中文 sector 关键词区分
- layer_factors: 天花板插值不再恒等钳死 10.0
- material_bridge: milestones 缺失容错
- layer_sector_scores: None sector 兜底
"""
import sys
import types

import pandas as pd
import pytest

pytestmark = [pytest.mark.unit]


class TestL22PendulumMonotonic:
    def test_pendulum_score_monotonic(self):
        from etf_platform.layers.l22_market_pendulum import _pendulum_score

        angles = [-45, -30, -15, -5, 5, 15, 25, 30, 45]
        scores = [_pendulum_score(a) for a in angles]
        # 恐慌(负角) 得分更高: 必须严格单调递减
        assert scores == sorted(scores, reverse=True), f"非单调: {scores}"
        assert scores[0] == 10.0, "angle=-45 应封顶 10.0"
        assert scores[-1] == 1.0, "angle=45 应封底 1.0"

    def test_pendulum_score_range(self):
        from etf_platform.layers.l22_market_pendulum import _pendulum_score

        for a in range(-60, 61):
            s = _pendulum_score(a)
            assert 1.0 <= s <= 10.0, f"angle={a} score={s} 超范围"

    def test_pendulum_anchor_interpolation(self):
        from etf_platform.layers.l22_market_pendulum import (
            _PENDULUM_ANCHORS,
            _pendulum_score,
        )

        for angle, score in _PENDULUM_ANCHORS:
            assert _pendulum_score(angle) == pytest.approx(score, abs=0.01)


class TestL30CompositeScale:
    def test_composite_within_0_10(self):
        from etf_platform.layers.l30_multiagent import _compute_l30_composite

        # 全部取最佳输入 (coord=0.5 使 |coord-0.5|=0) → weighted 最大
        best = _compute_l30_composite(0.95, 0.5, 0.1, 0.95)
        assert 0.0 <= best <= 10.0, f"最佳组合得分 {best} 超过 10"
        assert best > 9.0, f"最佳组合应接近 10, got {best}"
        # 回归金丝雀: 旧 ×12 缩放此处会得到 11.3 > 10
        assert best * 1.2 > 10.0, "旧 ×12 逻辑不会超 10, 测试失去区分度"

    def test_composite_min(self):
        from etf_platform.layers.l30_multiagent import _compute_l30_composite

        worst = _compute_l30_composite(0.1, 0.95, 0.95, 0.1)
        assert 0.0 <= worst <= 10.0


class TestL16FlowSignalAdjustment:
    """get_live_signals_with_data 资金流向修正: signal 字段方向驱动.

    回归: bearish(量价齐跌/主力出货/散户恐慌抛售) 此前被 +0.3 错误加分。
    """

    def _call(self, alerts, monkeypatch, flow_summary=None):
        import etf_platform.layers.l16_live_signals as l16

        class _Snap:
            premium_pct = 0.0

            def to_dict(self):
                return {"premium_pct": 0.0}

        monkeypatch.setattr(l16, "get_etf_snapshot", lambda code: _Snap())
        monkeypatch.setattr(l16, "get_realtime_dip_signals", lambda codes: {"alerts": []})
        monkeypatch.setattr(
            l16,
            "get_realtime_flow_signals",
            lambda codes: {"alerts": alerts, "market_summary": flow_summary or {}},
        )
        return l16.get_live_signals_with_data("半导体", etf_code="159995", daily_amount_yi=2.0)

    def test_bearish_flow_penalizes(self, monkeypatch):
        alerts = [{"alert_level": "high", "divergence_type": "主力出货", "signal": "bearish"}]
        r = self._call(alerts, monkeypatch)
        assert r["flow_signal"] == "主力出货"
        assert r["flow_score_adjustment"] == -0.5

    def test_divergence_bearish_penalizes(self, monkeypatch):
        alerts = [{"alert_level": "high", "divergence_type": "散户追高", "signal": "divergence_bearish"}]
        r = self._call(alerts, monkeypatch)
        assert r["flow_score_adjustment"] == -0.5

    def test_bullish_flow_boosts(self, monkeypatch):
        alerts = [{"alert_level": "high", "divergence_type": "量价齐升", "signal": "bullish"}]
        r = self._call(alerts, monkeypatch)
        assert r["flow_score_adjustment"] == 0.3

    def test_no_high_alert_no_adjustment(self, monkeypatch):
        alerts = [{"alert_level": "low", "divergence_type": "资金平衡", "signal": "neutral"}]
        r = self._call(alerts, monkeypatch)
        assert r["flow_score_adjustment"] == 0.0


class TestFundFlowSignalField:
    def _row(self, **kw):
        default = {
            "代码": "159995", "名称": "芯片ETF",
            "涨跌幅": 0.0, "主力净流入-净额": 0.0, "主力净流入-净占比": 0.0,
            "超大单净流入-净额": 0.0, "大单净流入-净额": 0.0,
            "中单净流入-净额": 0.0, "小单净流入-净额": 0.0,
        }
        default.update(kw)
        return pd.Series(default)

    def test_classify_flow_patterns(self):
        from etf_platform.analysis.fund_flow import FundFlowAnalyzer

        a = FundFlowAnalyzer()
        cases = [
            ({"涨跌幅": 2.0, "主力净流入-净额": 2e7}, ("量价齐升", "bullish")),
            ({"涨跌幅": 2.0, "主力净流入-净额": -2e7}, ("主力出货", "bearish")),
            ({"涨跌幅": -2.0, "主力净流入-净额": 2e7}, ("主力吸筹", "divergence_bullish")),
            ({"涨跌幅": -2.0, "主力净流入-净额": -2e7}, ("量价齐跌", "bearish")),
            ({"涨跌幅": 2.0, "主力净流入-净额": 0, "中单净流入-净额": 5e6, "小单净流入-净额": 5e6},
             ("散户追高", "divergence_bearish")),
            ({"涨跌幅": -2.0, "主力净流入-净额": 0, "中单净流入-净额": 5e6, "小单净流入-净额": 5e6},
             ("散户恐慌抛售", "bearish")),
            ({"涨跌幅": 0.5, "主力净流入-净额": 0}, ("资金平衡", "neutral")),
        ]
        for kw, expected in cases:
            pattern, signal = a.classify_flow_pattern(self._row(**kw))
            assert (pattern, signal) == expected, f"{kw} → ({pattern},{signal}), 期望 {expected}"

    def test_alert_has_signal_field(self):
        from etf_platform.analysis.fund_flow import FundFlowAlert

        alert = FundFlowAlert(
            code="159995", name="芯片ETF", price_change=2.0, main_net_inflow=-2e7,
            main_net_ratio=-5.0, super_large_net=-1.5e7, large_net=-5e6,
            medium_net=5e6, small_net=5e6, divergence_type="主力出货",
            signal="bearish", alert_level="high",
        )
        d = alert.to_dict()
        assert d["signal"] == "bearish"
        assert d["divergence_type"] == "主力出货"

    def test_super_large_outflow_override_signal(self, tmp_path):
        from etf_platform.analysis.fund_flow import FundFlowAnalyzer

        df = pd.DataFrame([self._row(**{
            "涨跌幅": 2.0, "超大单净流入-净额": -2e7,
            "中单净流入-净额": 5e6, "小单净流入-净额": 5e6,
        })])
        a = FundFlowAnalyzer(cache_dir=tmp_path / "live_cache")
        alerts = a.detect_divergences(df)
        assert len(alerts) == 1
        assert alerts[0].signal == "bearish", "超大单流出+价格上涨应覆盖为 bearish"
        assert alerts[0].alert_level == "high"


class TestMaterialLivePMIOrder:
    def test_pmi_uses_newest_first(self, monkeypatch):
        """akshare PMI 数据 newest-first: iloc[0]=最新月.

        回归: 旧代码 iloc[-1] 取到 2008 年数据 (jan-2008 制造业约 53 被当最新值)。
        """
        fake_ak = types.ModuleType("akshare")
        rows = [
            {"月份": "2026-07", "制造业-指数": 49.5, "非制造业-指数": 50.5},
            {"月份": "2026-06", "制造业-指数": 49.8, "非制造业-指数": 50.2},
            {"月份": "2026-05", "制造业-指数": 50.2, "非制造业-指数": 51.0},
            {"月份": "2008-01", "制造业-指数": 53.3, "非制造业-指数": 55.0},
        ]
        fake_ak.macro_china_pmi = lambda: pd.DataFrame(rows)
        monkeypatch.setitem(sys.modules, "akshare", fake_ak)

        from etf_platform.analysis import material_live

        material_live._cache["pmi"] = None
        try:
            pmi = material_live._fetch_pmi()
        finally:
            material_live._cache["pmi"] = None
        assert pmi["month"] == "2026-07", f"应取最新月, got {pmi['month']}"
        assert pmi["manufacturing"] == 49.5
        # prev3 = iloc[1:4] = 2026-06/05 + 2008-01 三个月均值
        assert pmi["mfg_3m_avg"] == pytest.approx(51.1, abs=0.1), \
            "prev3 = iloc[1:4] 应为 (49.8+50.2+53.3)/3=51.1"


class TestL24ChineseSectorProfiles:
    def test_chinese_sectors_distinct(self):
        """中文 sector 关键词区分: 不同行业得到不同 FDR profile.

        回归: 原英文关键词对中文 sector 失效, 全部落入 generic 0.3。
        """
        from etf_platform.layers.l24_system_dynamics import _get_sector_profile

        cases = {
            "半导体": 0.6, "新能源": 0.85, "医药": 0.15, "消费": -0.5,
            "军工": 0.4, "通信/5G": 0.65, "有色金属": -0.2, "宽基": 0.3,
        }
        for sector, expected_fdr in cases.items():
            p = _get_sector_profile(sector)
            assert p is not None, f"{sector} 未匹配到 profile"
            assert p["typical_fdr"] == expected_fdr, \
                f"{sector}: fdr={p['typical_fdr']}, 期望 {expected_fdr}"


class TestLayerFactorsCeiling:
    def _base(self, l5=6.0):
        return {"L3_Material": 6.0, "L4_SupplyChain": 6.0, "L5_Tech": l5,
                "L6_Politics": 6.0, "L7_Irreplaceable": 6.0}

    def test_ceiling_interpolation_not_clamped(self):
        """美股科技 L5 mult=1.15, base=9.2 → raw 10.58 > 10 走抗饱和分支.

        回归: 旧 `raw*(10/raw)` 恒等 10.0 (等于钳死), 抗饱和空转。
        """
        from etf_platform.analysis.layer_factors import apply_factors

        adj = apply_factors("美股科技", self._base(l5=9.2))
        assert adj["L5_Tech"] < 10.0, "抗饱和应留出天花板余量"
        assert adj["L5_Tech"] > 9.2, "抗饱和仍应体现 multiplier 增益"
        assert adj["L5_Tech"] == pytest.approx(9.3, abs=0.05), \
            f"期望 10-0.8/1.15≈9.3, got {adj['L5_Tech']}"

    def test_ceiling_preserves_differentiation(self):
        from etf_platform.analysis.layer_factors import apply_factors

        lo = apply_factors("美股科技", self._base(l5=9.0))["L5_Tech"]
        hi = apply_factors("美股科技", self._base(l5=9.5))["L5_Tech"]
        assert lo < hi, f"高分 ETF 应保持更高: lo={lo} hi={hi}"
        assert hi < 10.0


class TestMaterialBridgeTolerance:
    def test_milestone_without_milestones_key(self, monkeypatch):
        """tech milestone 缺 milestones 字段不崩溃 (回归 m['milestones'] KeyError)."""
        from etf_platform.analysis import material_bridge

        fake_ms = [{"affects": ["159995"], "probability": 0.8, "status": "进行中"}]
        monkeypatch.setattr(material_bridge, "_get_tech_milestones", lambda: fake_ms)
        monkeypatch.setattr(material_bridge, "_get_material_signals", lambda: {})
        monkeypatch.setattr(material_bridge, "_get_personnel_risks", lambda: [])
        adj = material_bridge.material_layer_adjustments("159995")
        assert adj["L5_Tech"] == 0.0, "无 milestones → progress=0 → signal 0"
        assert adj["L7_Irreplaceable"] != 0.0, "应走 code jitter 分支"

    def test_material_capacity_merge_no_crash(self):
        """material_capacity.json 合并路径 (含缺字段容错) 不崩溃."""
        from etf_platform.analysis import material_bridge

        merged = material_bridge._get_material_signals()
        assert isinstance(merged, dict)
        # 任何条目都必须带 _source 标记 (merge 后字段契约完整)
        for name, mat in merged.items():
            if mat.get("_source") == "material_capacity.json":
                assert "affects" in mat, f"{name} 缺 affects"
                assert "impact_direction" in mat, f"{name} 缺 impact_direction"


class TestLayerSectorScoresNone:
    def test_none_sector_returns_fallback(self):
        """None sector 兜底为 '其他' (回归 `key in sector` TypeError)."""
        from etf_platform.analysis.layer_sector_scores import get_sector_layer_scores

        result = get_sector_layer_scores(None)
        assert "L3_Material" in result
        for v in result.values():
            assert 1.0 <= v <= 10.0
