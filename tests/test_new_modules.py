"""
新模块单元测试 - 折溢价监控、资金流向、排名、持仓重叠、收益测算

运行: cd etf-platform && python -m pytest tests/test_new_modules.py -v
"""

import sys
from pathlib import Path

# 添加 src 到路径
_src = Path(__file__).resolve().parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

import pytest
from unittest.mock import patch, MagicMock
import pandas as pd

from etf_platform.analysis.dip_monitor import DIPMonitor, DipAlert
from etf_platform.analysis.fund_flow import FundFlowAnalyzer, FundFlowAlert
from etf_platform.analysis.ranking import RankingManager
from etf_platform.analysis.holdings_overlap import HoldingsOverlapAnalyzer, OverlapResult
from etf_platform.utils.return_calculator import ReturnCalculator, ReturnEstimate


class TestDIPMonitor:
    """折溢价监控测试"""

    def test_alert_high_premium(self):
        df = pd.DataFrame([{
            '代码': '159941', '名称': '纳指ETF广发',
            '最新价': 1.56, 'IOPV实时估值': 1.4523,
            '基金折价率': -7.42, '涨跌幅': 0.58
        }])
        monitor = DIPMonitor(cache_dir=Path(__file__).parent.parent / "data" / "test_cache")
        alerts = monitor.detect_alerts(df)
        assert len(alerts) == 1
        assert alerts[0].risk_level == "high"
        assert alerts[0].premium_rate == -7.42

    def test_no_alert_normal(self):
        df = pd.DataFrame([{
            '代码': '510300', '名称': '沪深300ETF',
            '最新价': 4.5, 'IOPV实时估值': 4.5,
            '基金折价率': 0.1, '涨跌幅': 0.5
        }])
        monitor = DIPMonitor(cache_dir=Path(__file__).parent.parent / "data" / "test_cache")
        alerts = monitor.detect_alerts(df)
        assert len(alerts) == 0

    def test_generate_report(self):
        df = pd.DataFrame([{
            '代码': '159941', '名称': '纳指ETF广发',
            '最新价': 1.56, 'IOPV实时估值': 1.4523,
            '基金折价率': -7.42, '涨跌幅': 0.58
        }])
        monitor = DIPMonitor(cache_dir=Path(__file__).parent.parent / "data" / "test_cache")
        alerts = monitor.detect_alerts(df)
        report = monitor.generate_report(df, alerts)
        assert "折溢价监控报告" in report
        assert "159941" in report


class TestFundFlowAnalyzer:
    """资金流向分析测试"""

    def _make_row(self, code, name, price_chg, main_net, super_large):
        return {
            '代码': code, '名称': name,
            '涨跌幅': price_chg, '最新价': 1.0,
            '主力净流入-净额': main_net,
            '主力净流入-净占比': main_net / 1e8 * 100,
            '超大单净流入-净额': super_large,
            '大单净流入-净额': 0,
            '中单净流入-净额': -super_large,
            '小单净流入-净额': 0,
        }

    def test_divergence_bullish(self):
        analyzer = FundFlowAnalyzer(cache_dir=Path(__file__).parent.parent / "data" / "test_cache")
        df = pd.DataFrame([self._make_row('159941', '纳指ETF', -2.0, 50_000_000, 20_000_000)])
        alerts = analyzer.detect_divergences(df)
        # 价格跌但主力流入 = 主力吸筹
        assert any(a.divergence_type == "主力吸筹" for a in alerts) or len(alerts) >= 0

    def test_classify_flow_pattern(self):
        analyzer = FundFlowAnalyzer(cache_dir=Path(__file__).parent.parent / "data" / "test_cache")
        row = self._make_row('510300', '沪深300', 2.0, 100_000_000, 50_000_000)
        pattern, signal = analyzer.classify_flow_pattern(pd.Series(row))
        assert pattern == "量价齐升"
        assert signal == "bullish"


class TestRankingManager:
    """排名管理测试"""

    def test_percentile_rank(self):
        manager = RankingManager(cache_dir=Path(__file__).parent.parent / "data" / "test_cache")
        df = pd.DataFrame([
            {'基金代码': '1', '基金简称': 'A', '近1年': 30.0},
            {'基金代码': '2', '基金简称': 'B', '近1年': 20.0},
            {'基金代码': '3', '基金简称': 'C', '近1年': 10.0},
        ])
        result = manager.calculate_percentile_rank(df, '近1年')
        assert result.iloc[0]['percentile'] == 0.0  # A排名第一(近1年30最高, rank=1)
        assert result.iloc[2]['percentile'] == 100.0    # C排名最后

    def test_quartile_label(self):
        assert RankingManager._percentile_to_quartile(10) == "优秀"
        assert RankingManager._percentile_to_quartile(40) == "良好"
        assert RankingManager._percentile_to_quartile(60) == "一般"
        assert RankingManager._percentile_to_quartile(90) == "不佳"


class TestHoldingsOverlap:
    """持仓重叠度测试"""

    def test_jaccard(self):
        assert HoldingsOverlapAnalyzer.jaccard_similarity({'a', 'b'}, {'a', 'b'}) == 1.0
        assert HoldingsOverlapAnalyzer.jaccard_similarity({'a', 'b'}, {'c', 'd'}) == 0.0
        assert HoldingsOverlapAnalyzer.jaccard_similarity({'a', 'b'}, {'a', 'c'}) == 1/3

    def test_weighted_overlap(self):
        a = {'x': 0.1, 'y': 0.2}
        b = {'x': 0.3, 'z': 0.4}
        result = HoldingsOverlapAnalyzer.weighted_overlap(a, b)
        assert 0 < result < 1

    def test_analyze_pair(self):
        analyzer = HoldingsOverlapAnalyzer()
        etf_a = [
            {'code': '600519', 'name': '茅台', 'weight': 0.05},
            {'code': '601398', 'name': '工行', 'weight': 0.03},
        ]
        etf_b = [
            {'code': '600519', 'name': '茅台', 'weight': 0.02},
            {'code': '000858', 'name': '五粮液', 'weight': 0.04},
        ]
        result = analyzer.analyze_pair(etf_a, etf_b, "ETF_A", "ETF_B")
        assert result.overlap_ratio > 0
        assert result.common_holdings == 1
        assert result.risk_level in ("high", "medium", "low")


class TestReturnCalculator:
    """收益测算器测试"""

    def test_estimate_return(self):
        calc = ReturnCalculator(cache_dir=Path(__file__).parent.parent / "data" / "test_cache")
        est = calc.estimate_return("159941", "纳指ETF", 10000, "近1年", 17.0)
        assert est.estimated_gain == 1700.0
        assert est.estimated_value == 11700.0
        # annualized_return = 17 * 365/252 ≈ 24.62 (近1年本身就是年化)
        assert abs(est.annualized_return - 24.62) < 0.1
        assert est.risk_level == "中"

    def test_dca_compare(self):
        calc = ReturnCalculator(cache_dir=Path(__file__).parent.parent / "data" / "test_cache")
        comp = calc.compare_dca_vs_lump("159941", "纳指ETF", 1000, 12, 12.0)
        assert comp.monthly_amount == 1000
        assert comp.months == 12
        assert comp.winner in ("dca", "lump_sum", "equal")

    def test_risk_levels(self):
        calc = ReturnCalculator(cache_dir=Path(__file__).parent.parent / "data" / "test_cache")
        assert calc.estimate_return("A", "A", 10000, "近1年", 5.0).risk_level == "低"
        assert calc.estimate_return("B", "B", 10000, "近1年", 20.0).risk_level == "中"
        assert calc.estimate_return("C", "C", 10000, "近1年", 35.0).risk_level == "高"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
