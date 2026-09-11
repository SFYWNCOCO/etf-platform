"""P0 量纲归一 + 真门禁 单测（weekly_top3）。

覆盖三块：
1. 归一分值：news/flow/val 修正 = M0*w*s（衰减阶梯 1.0/0.3/0.1）
2. 真门禁：net>=3 或（net>=2 且 20d动量>3%），gate=False 退化旧行为（net>=2）
3. 基线退化金丝雀：gate=False + 无 news/flow 信号 → 无板块被门禁
   且 adjusted_momentum 数值上等于纯动量基线（各层贡献为 0）
"""
import sys
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


def _stub_catalyst(monkeypatch):
    """隔离 live 催化层：单测不依赖 scripts/catalyst_status 实时数据。"""
    fake = types.ModuleType("scripts.catalyst_status")
    fake.get_sector_boost = lambda mega: {"status": "none", "boost": 0.0}
    monkeypatch.setitem(sys.modules, "scripts.catalyst_status", fake)


def _build(megapos=None, mom_by_mega=None, pos_by_mega=None):
    """构造 3 个板块各 3 只ETF的 fixture；可注入动量与60日位置。"""
    mom_by_mega = mom_by_mega or {"科技": 2.0, "新能源": 3.0, "消费": 1.0}
    pos_by_mega = pos_by_mega or {}
    mega_sectors = {}
    trends = {}
    code_to_sector = {}
    for i, (mega, sub) in enumerate(megapos or [
            ("科技", "半导体"), ("新能源", "新能源"), ("消费", "消费")]):
        for j in range(3):
            code = f"5{i:02d}0{j}"
            name = f"{sub}ETF{j}"
            mega_sectors[mega] = mega_sectors.get(mega, []) + [(code, name, sub)]
            m = mom_by_mega[mega]
            p = pos_by_mega.get(mega, 40.0)
            trends[code] = _trend(change_20d=m, position_pct=p)
            code_to_sector[code] = sub
    return mega_sectors, trends, code_to_sector


def _run(mega_sectors, trends, code_to_sector, news_signals=None,
         monkeypatch=None, gate=True, flows=None):
    import weekly_top3 as wt
    if monkeypatch is not None:
        _stub_catalyst(monkeypatch)
        monkeypatch.setattr(wt, "_load_news_signals", lambda: news_signals)
        if flows is not None:
            monkeypatch.setattr(wt, "_get_sector_flows", lambda live=False: flows)
    return wt._get_top_mega_sectors(
        mega_sectors, trends, code_to_sector,
        news_signals=news_signals, top_n=3, gate=gate,
    )


class TestNormalizedScoring:
    """P0-3：修正项 = M0*w*s，s∈[-1,1]，量纲与动量%一致。"""

    def test_fresh_strong_bearish_excluded(self, monkeypatch):
        """新鲜强看空（s*decay=-1.0 ≤ -0.5）整板块排除（P0 新阈值行为）。"""
        ms, tr, cs = _build()
        news = {"科技": {"direction": "看空", "strength": "强", "fresh_days": 1},
                "消费": {"direction": "中性", "strength": "弱", "fresh_days": 1}}
        out = _run(ms, tr, cs, news, monkeypatch=monkeypatch, flows={})
        assert [s for s, _ in out] == ["新能源", "消费"]

    def test_mid_age_news_decay(self, monkeypatch):
        ms, tr, cs = _build()
        news = {"科技": {"direction": "看空", "strength": "强", "fresh_days": 5}}
        out = _run(ms, tr, cs, news, monkeypatch=monkeypatch, flows={})
        tech = {s: d for s, d in out if s == "科技"}
        # 5天 → decay=0.3 → -5*0.5*0.3 = -0.75
        assert tech["科技"]["news_adjustment"] == -0.75

    def test_stale_news_decay(self, monkeypatch):
        ms, tr, cs = _build()
        news = {"科技": {"direction": "看空", "strength": "强", "fresh_days": 8}}
        out = _run(ms, tr, cs, news, monkeypatch=monkeypatch, flows={})
        tech = {s: d for s, d in out if s == "科技"}
        # 8天 → fallback decay=0.1 → -5*0.5*0.1 = -0.25
        assert tech["科技"]["news_adjustment"] == -0.25

    def test_strong_bullish_news_adj(self, monkeypatch):
        ms, tr, cs = _build()
        news = {"科技": {"direction": "看多", "strength": "强", "fresh_days": 1}}
        out = _run(ms, tr, cs, news, monkeypatch=monkeypatch, flows={})
        tech = {s: d for s, d in out if s == "科技"}
        # M0*0.5*(+0.4)*1.0 = +1.0
        assert tech["科技"]["news_adjustment"] == 1.0

    def test_flow_adj_full_inflow(self, monkeypatch):
        ms, tr, cs = _build()
        flows = {"科技": {"net_inflow_pct": 2.0}}
        out = _run(ms, tr, cs, None, monkeypatch=monkeypatch, flows=flows)
        tech = {s: d for s, d in out if s == "科技"}
        # M0*0.15*(+1.0) = +0.75
        assert tech["科技"]["flow_adjustment"] == 0.75

    def test_flow_adj_outflow(self, monkeypatch):
        ms, tr, cs = _build()
        flows = {"科技": {"net_inflow_pct": -2.0}}
        out = _run(ms, tr, cs, None, monkeypatch=monkeypatch, flows=flows)
        tech = {s: d for s, d in out if s == "科技"}
        # M0*0.15*(-1.0) = -0.75
        assert tech["科技"]["flow_adjustment"] == -0.75

    def test_valuation_adj_high_position(self, monkeypatch):
        ms, tr, cs = _build(pos_by_mega={"科技": 90.0})
        out = _run(ms, tr, cs, None, monkeypatch=monkeypatch, flows={})
        tech = {s: d for s, d in out if s == "科技"}
        # M0*0.10*(-1.0) = -0.5
        assert tech["科技"]["valuation_adjustment"] == -0.5

    def test_valuation_adj_low_position(self, monkeypatch):
        ms, tr, cs = _build(pos_by_mega={"科技": 10.0})
        out = _run(ms, tr, cs, None, monkeypatch=monkeypatch, flows={})
        tech = {s: d for s, d in out if s == "科技"}
        # M0*0.10*(+1.0) = +0.5
        assert tech["科技"]["valuation_adjustment"] == 0.5


class TestTrueGate:
    """P0-1：_passes_gate(net, mom) 与 gated_out 分流。"""

    def test_passes_gate_pure_unit(self):
        import weekly_top3 as wt
        assert wt._passes_gate(3, 0.0) is True       # net>=3 直接过
        assert wt._passes_gate(2, 4.0) is True       # net>=2 且动量>3%
        assert wt._passes_gate(2, 3.0) is False      # 动量恰=3% 不过
        assert wt._passes_gate(2, 2.9) is False
        assert wt._passes_gate(1, 99.0) is False     # 动量再高也需 net>=2
        assert wt._passes_gate(0, 5.0) is False

    def test_gate_flags_gated_out(self, monkeypatch):
        # 科技: 动量2.0>1(bull) + 中位位置(net=1) → gated
        # 新能源: 动量3.5>1 + 低位(val bull) → net=2 且 3.5>3% → 过
        # 消费:  动量1.5>1(bull) + 低位(val bull) → net=2 但 1.5<3% → gated
        ms, tr, cs = _build(mom_by_mega={"科技": 2.0, "新能源": 3.5, "消费": 1.5},
                            pos_by_mega={"新能源": 10.0, "消费": 10.0})
        out = _run(ms, tr, cs, None, monkeypatch=monkeypatch, flows={}, gate=True)
        by_mega = {s: d for s, d in out}
        assert by_mega["科技"]["gated_out"] is True
        assert by_mega["消费"]["net_layers"] == 2
        assert by_mega["消费"]["gated_out"] is True  # net=2 但动量1.5 不>3%
        assert by_mega["新能源"].get("gated_out", False) is False

    def test_gate_false_legacy_behavior(self, monkeypatch):
        """gate=False 退化：net>=2 即过（81周基线对照路径）。"""
        ms, tr, cs = _build(mom_by_mega={"科技": 2.0, "新能源": 3.0, "消费": 1.0},
                            pos_by_mega={"科技": 10.0})
        out = _run(ms, tr, cs, None, monkeypatch=monkeypatch, flows={}, gate=False)
        by_mega = {s: d for s, d in out}
        assert by_mega["科技"].get("gated_out", False) is False  # net=2 旧规则即过
        assert by_mega["新能源"].get("gated_out", False) is True  # net=1 旧规则也不过


class TestBaselineDegradation:
    """金丝雀：无 news/flow 信号时归一层贡献全0，adjusted==median（纯动量基线）。"""

    def test_adjusted_equals_median_without_signals(self, monkeypatch):
        ms, tr, cs = _build(mom_by_mega={"科技": 2.0, "新能源": 3.0, "消费": 1.0})
        out = _run(ms, tr, cs, None, monkeypatch=monkeypatch, flows={})
        for s, d in out:
            assert d["adjusted_momentum"] == d["median_momentum"], (
                f"{s}: 无信号层时 adjusted 应等于纯动量, "
                f"got {d['adjusted_momentum']} vs {d['median_momentum']}")
            assert d["news_adjustment"] == 0.0
            assert d["flow_adjustment"] == 0.0

    def test_gate_false_no_gated_out_without_layers(self, monkeypatch):
        """中性位置 + 无news/flow：net=1 的板块 gate=False 下也不该被误伤为
        '全数 gated'——旧行为至少保留返回顺序不变（调用方补位语义一致）。"""
        ms, tr, cs = _build()
        out = _run(ms, tr, cs, None, monkeypatch=monkeypatch, flows={}, gate=False)
        assert [s for s, _ in out] == ["新能源", "科技", "消费"]  # 按动量降序

    def test_low_confidence_backfill(self, monkeypatch):
        """main() 补位语义：gated_in 为空时全部用 gated_out 补位并标 low_confidence。
        这里复刻 main() :853-862 的分流逻辑做行为断言。"""
        ms, tr, cs = _build(mom_by_mega={"科技": 2.0, "新能源": 3.0, "消费": 1.5},
                            pos_by_mega={"科技": 10.0, "消费": 10.0})
        out = _run(ms, tr, cs, None, monkeypatch=monkeypatch, flows={}, gate=True)
        gated_in = [t for t in out if not t[1].get("gated_out", False)]
        gated_out = [t for t in out if t[1].get("gated_out", False)]
        selected = gated_in[:3]
        for t in gated_out:
            if len(selected) >= 3:
                break
            t[1]["low_confidence"] = True
            selected.append(t)
        # 科技(net=2, 动量2.0≤3%)与消费(net=2, 1.5≤3%) 都被门禁 → 全补位
        assert [s for s, _ in selected] == ["新能源", "科技", "消费"]
        by_mega = {s: d for s, d in selected}
        assert by_mega["新能源"]["gated_out"] is True
        assert by_mega["新能源"].get("low_confidence") is True
