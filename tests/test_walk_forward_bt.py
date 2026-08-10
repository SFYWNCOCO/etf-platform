"""walk_forward_bt PIT 复刻函数金丝雀测试。

金丝雀原则：复刻函数必须与生产实现在"当前数据"上一致，
否则回测数字就是被污染的（复刻挂了但测试没失败）。
"""
import json
from datetime import date

import pytest

from etf_platform.optimize import walk_forward_bt as wf
from etf_platform.decision import two_week_picker as twp
from etf_platform.analysis import qvix_regime as qr

pytestmark = [pytest.mark.unit]


def _synthetic_qvix():
    """50 序列全部 normal，500 序列 07-01~07-09 complacent / 07-10 跳至 fearful。"""
    def _series(close_fn):
        rows = []
        for i in range(1, 11):
            rows.append({"date": f"2026-07-{i:02d}", "close": close_fn(i)})
        return rows
    return {
        "50": _series(lambda i: 20.0),                      # 20 < 22 → normal
        "500": _series(lambda i: 30.0 if i == 10 else 15.0),  # 07-10 → 30 fearful
    }


class TestRegimeAt:
    def test_slices_by_date(self):
        """07-09 前 500 序列是 complacent(15) → 50 normal 胜出；07-10 500 跳 fearful 胜出。"""
        cache = _synthetic_qvix()
        assert wf._regime_at(cache, date(2026, 7, 8)) == "normal"
        assert wf._regime_at(cache, date(2026, 7, 10)) == "fearful"

    def test_empty_series_falls_back_normal(self):
        assert wf._regime_at({}, date(2026, 7, 10)) == "normal"

    def test_pins_to_get_regime(self, monkeypatch):
        """复刻与生产 get_regime 在相同输入上必须一致（金丝雀）。"""
        cache = _synthetic_qvix()
        monkeypatch.setattr(qr, "_get_qvix_data", lambda: cache)
        expected = qr.get_regime()["regime"]
        got = wf._regime_at(cache, date.today())
        assert got == expected, f"复刻 {got} != 生产 {expected}"


def _trend_rows(n=30, base=100.0, step=1.0):
    """n 根日线，close 线性递增 base + i*step，日期从 2026-06-01 起。"""
    rows = []
    for i in range(n):
        rows.append({
            "date": f"2026-06-{i + 1:02d}", "open": base + i * step,
            "close": base + i * step, "high": base + i * step + 0.5,
            "low": base + i * step - 0.5, "volume": 1000 + i,
        })
    return rows


class TestTrendAt:
    def test_matches_get_trend_math(self):
        """单调上涨：change_20d 精确手算值，max_drawdown=0，趋势 overbought。"""
        rows = _trend_rows(30)
        t = wf._trend_at("TEST", rows, date(2026, 6, 30))
        assert t is not None
        assert t.data_days == 30
        # close[-1]=129, close[-21]=109 → 129/109-1 = 18.35%
        assert t.change_20d == pytest.approx(18.35, abs=0.01)
        assert t.max_drawdown == 0.0
        assert t.volatility_20d > 0
        assert t.trend_signal == "overbought"

    def test_short_window_fallback(self):
        """<21 根时 change_20d 回退到 chg(total-1)，用全窗首个收盘。"""
        rows = _trend_rows(15)
        t = wf._trend_at("TEST", rows, date(2026, 6, 15))
        assert t.data_days == 15
        # 15 根: close[-1]=114, close[0]=100 → 14%
        assert t.change_20d == pytest.approx(14.0, abs=0.01)

    def test_slice_excludes_future(self):
        """日期切片后只看 D 之前的数据：06-10 时只含前 10 根。"""
        rows = _trend_rows(30)
        t = wf._trend_at("TEST", rows, date(2026, 6, 10))
        assert t.data_days == 10
        assert t.change_20d == pytest.approx(9.0, abs=0.01)  # close[-1]=109, close[0]=100

    def test_too_few_bars_returns_none(self):
        assert wf._trend_at("TEST", _trend_rows(1), date(2026, 6, 1)) is None

    def test_window_truncated_to_production_depth(self):
        """生产 get_trend(63) 实测返回 64 根 → 回测切片后取末 64 根，深度一致。"""
        rows = _trend_rows(80, base=100, step=1.0)  # 80 根, 日期 06-01..06-80
        t = wf._trend_at("TEST", rows, date(2026, 6, 20))  # 06-01..06-20 = 20 根 < 64，不截断
        assert t.data_days == 20
        t2 = wf._trend_at("TEST", rows, date(2026, 7, 1))  # > 所有 06 月日期，取末 64
        assert t2.data_days == 64
        assert t2.max_drawdown == 0.0  # 单调上涨仍无回撤


class TestPoolReproduction:
    def test_build_pool_is_pure_function(self):
        """同一 regime 下候选池可精确复现（etfs 配置 + regime 的纯函数）。"""
        etfs = {}
        for i, (code, sector) in enumerate([
            ("512480", "半导体"), ("518880", "黄金"), ("510150", "消费"),
            ("512690", "白酒消费"), ("516160", "新能源"), ("512880", "券商"),
        ]):
            etfs[code] = {
                "name": f"ETF{i}", "sector": sector, "access": "buyable",
                "type": "行业",
            }
        # fearful: 防御行业过滤 → 只剩黄金/消费/白酒消费
        pool = twp._build_candidate_pool(etfs, "fearful", 100)
        sectors = {info["sector"] for _c, info in pool}
        assert sectors == {"黄金", "消费", "白酒消费"}

    def test_collect_factors_pit_zscore(self):
        """PIT 因子收集：pipeline 标称化，zscore 在池内标准化（需≥3候选）。"""
        rows_a = _trend_rows(30, base=100, step=1.0)   # 缓涨
        rows_b = _trend_rows(30, base=200, step=-1.0)  # 缓跌
        rows_c = _trend_rows(30, base=300, step=0.5)   # 缓涨(较慢)
        cands = [("AAA", {"sector": "半导体", "name": "A"}),
                 ("BBB", {"sector": "消费", "name": "B"}),
                 ("CCC", {"sector": "医药", "name": "C"})]
        trend_map = {
            "AAA": wf._trend_at("AAA", rows_a, date(2026, 6, 30)),
            "BBB": wf._trend_at("BBB", rows_b, date(2026, 6, 30)),
            "CCC": wf._trend_at("CCC", rows_c, date(2026, 6, 30)),
        }
        z_factors, scored = wf._collect_factors_pit(cands, trend_map)
        assert scored == [0, 1, 2]
        assert "oversold_depth" in z_factors
        # BBB 跌最多 → oversold_depth(=-change_20d) 的 z 值应为三者最高
        assert z_factors["oversold_depth"][1] == max(z_factors["oversold_depth"])
