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


class TestFwdReturn:
    def test_anchors_at_first_bar_ge_date(self):
        rows = _trend_rows(40, base=100, step=1.0)  # close: 100..139
        # 锚点取 ≥ 06-10 首根(close=109), +10 根 → 119 → +9.17%
        assert wf._fwd_return(rows, date(2026, 6, 10)) == pytest.approx(9.17, abs=0.01)

    def test_no_bar_after_date_returns_none(self):
        rows = _trend_rows(10)
        assert wf._fwd_return(rows, date(2026, 7, 1)) is None


class TestWeeklyDates:
    def test_aligns_to_monday(self):
        from datetime import date as D
        # 2026-02-12 是周四 → 对齐到 02-16(周一)
        dates = wf._weekly_dates("2026-02-12", "2026-03-02")
        assert dates[0] == D(2026, 2, 16)
        assert all(d.weekday() == 0 for d in dates)
        assert dates[-1] <= D(2026, 3, 2)


class TestWeeklyBacktest:
    def _mini_etfs(self):
        return {
            "111111": {"name": "消费ETF", "sector": "消费", "access": "buyable", "type": "行业A"},
            "222222": {"name": "医药ETF", "sector": "医药", "access": "buyable", "type": "行业A"},
            "333333": {"name": "公用ETF", "sector": "公用事业", "access": "buyable", "type": "行业A"},
            "444444": {"name": "黄金ETF", "sector": "贵金属", "access": "buyable", "type": "商品"},
            "555555": {"name": "白酒ETF", "sector": "白酒消费", "access": "buyable", "type": "行业A"},
            "666666": {"name": "食品ETF", "sector": "食品饮料", "access": "buyable", "type": "行业A"},
        }

    def _kline_for(self, code):
        # 每只 code 给 ~70 根日线，从 2026-04-01 起，收盘价按 code 数字随机化确定
        import hashlib
        seed = int(hashlib.md5(code.encode()).hexdigest()[:8], 16) % 1000
        base = 50 + seed % 100
        step = 0.5 if seed % 2 else -0.4
        rows = []
        for i in range(70):
            rows.append({
                "date": f"2026-{4 + (i // 30):02d}-{(i % 30) + 1:02d}",
                "open": base + i * step, "close": base + i * step,
                "high": base + i * step + 0.5, "low": base + i * step - 0.5,
                "volume": 1000,
            })
        return rows

    def test_run_weekly_end_to_end(self, tmp_path, monkeypatch):
        """monkeypatch 合成数据跑通长窗口回测：结构完整、样本>0、QVIX 用临时缓存。"""
        import json as _json
        qvix = {"cached_at": "2026-07-01T00:00:00",
                "50": [{"date": f"2026-06-{i:02d}", "close": 20.0} for i in range(1, 31)],
                "500": [{"date": f"2026-06-{i:02d}", "close": 20.0} for i in range(1, 31)]}
        qvix_path = tmp_path / "qvix.json"
        qvix_path.write_text(_json.dumps(qvix), encoding="utf-8")

        monkeypatch.setattr(wf, "QVIX_CACHE", qvix_path)
        monkeypatch.setattr(wf, "load_etfs", self._mini_etfs)
        monkeypatch.setattr(wf, "_fetch_kline", lambda code, days: self._kline_for(code))

        report = wf.run_weekly_backtest("2026-06-01", "2026-06-29", max_candidates=10)
        assert report["sample"] > 0
        assert 0 <= report["engine"]["hit_rate"] <= 100
        assert report["weeks"] and all(len(w["new_codes"]) == 3 for w in report["weeks"])
        assert "vs_pool_avg_spread" in report["engine"]
        assert "pool_avg" in report
        # 锦标赛策略表完整且每策略都有样本
        assert set(report["strategies"]) == {
            "current_factor", "momentum", "oversold", "low_vol",
            "defensive_momentum", "random"}
        for s in report["strategies"].values():
            assert 0 <= s["hit_rate"] <= 100


class TestStrategyPicks:
    def _trend_map(self):
        rows_a = _trend_rows(30, base=100, step=1.0)    # 缓涨: change_20d≈+18%
        rows_b = _trend_rows(30, base=200, step=-1.0)   # 缓跌: change_20d≈-10%
        rows_c = _trend_rows(30, base=300, step=0.2)    # 微涨: 波动小
        return {
            "AAA": wf._trend_at("AAA", rows_a, date(2026, 6, 30)),
            "BBB": wf._trend_at("BBB", rows_b, date(2026, 6, 30)),
            "CCC": wf._trend_at("CCC", rows_c, date(2026, 6, 30)),
        }

    def _cands(self):
        return [("AAA", {"sector": "半导体", "name": "A"}),
                ("BBB", {"sector": "消费", "name": "B"}),
                ("CCC", {"sector": "医药", "name": "C"})]

    def test_momentum_prefers_strong_steady_riser(self):
        tm = self._trend_map()
        picks = wf._rank_pick(self._cands(), tm, wf.STRATEGIES["momentum"])
        # AAA 涨18%波幅适中 → risk_adj 最高，排第一（3行业去重后 BBB 也入选但垫底）
        assert picks[0] == "AAA"
        assert picks[-1] == "BBB"

    def test_oversold_prefers_dropper(self):
        tm = self._trend_map()
        picks = wf._rank_pick(self._cands(), tm, wf.STRATEGIES["oversold"])
        assert picks[0] == "BBB"

    def test_low_vol_prefers_least_volatile(self):
        tm = self._trend_map()
        picks = wf._rank_pick(self._cands(), tm, wf.STRATEGIES["low_vol"])
        # CCC 波动最小（step=0.2）
        assert picks[0] == "CCC"

    def test_random_is_deterministic_per_seed(self):
        tm = self._trend_map()
        a = wf._random_pick(self._cands(), tm, "2026-06-15")
        b = wf._random_pick(self._cands(), tm, "2026-06-15")
        c = wf._random_pick(self._cands(), tm, "2026-06-22")
        assert a == b and a != c
        assert len(a) == 3
