"""Tests for layers/ — L14/L18 风控层集成测试.

被测模块:
- etf_platform.layers.l14_stoic_risk: score_stoic_layer / get_controllability
- etf_platform.layers.l18_var_risk: apply_var_layer / get_var_summary / SECTOR_TO_VOL_KEY
"""
import pytest

from etf_platform.layers.l14_stoic_risk import (
    CONTROLLABILITY_SCORES,
    get_controllability,
    score_stoic_layer,
)
from etf_platform.layers.l18_var_risk import (
    SECTOR_TO_VOL_KEY,
    VOLATILITY_BENCHMARK,
    apply_var_layer,
    calculate_var_score,
    get_var_summary,
)

pytestmark = [pytest.mark.unit]


class TestApplyVarLayer:
    def test_apply_var_layer_adds_score(self, etf_code_chip):
        """apply_var_layer 添加 L18_VaR 分数 (用低风险行业隔离降分行为)。"""
        # 红利低波 vol=15% → low, 不会触发 L1_ETF 降分, 可单独验证添加行为
        scores = {"L1_ETF": 8.0, "L2_Holdings": 7.0}
        result = apply_var_layer("红利低波", scores, etf_code=etf_code_chip)
        assert "L18_VaR" in result, "apply_var_layer 应添加 L18_VaR 键"
        assert 1.0 <= result["L18_VaR"] <= 10.0
        # 原有分数应保留 (低风险不触发降分)
        assert result["L1_ETF"] == 8.0
        assert result["L2_Holdings"] == 7.0
        # 返回的是同一 dict (就地修改)
        assert result is scores

    def test_apply_var_layer_high_risk_penalty(self, etf_code_chip):
        """高风险ETF降低L1_ETF得分。"""
        # 券商 vol=42% → extreme
        scores = {"L1_ETF": 8.0}
        result = apply_var_layer("券商", scores, etf_code=etf_code_chip)
        assert result["L1_ETF"] < 8.0, "高风险ETF应降低L1_ETF得分"
        assert result["L1_ETF"] == 7.5  # 8.0 - 0.5
        assert "L18_VaR" in result

    def test_apply_var_layer_low_risk_no_penalty(self):
        """低风险ETF不降低L1_ETF得分。"""
        # 货币基金 vol=3% → low
        scores = {"L1_ETF": 8.0}
        result = apply_var_layer("货币基金", scores, etf_code="159995")
        assert result["L1_ETF"] == 8.0, "低风险ETF不应降低L1_ETF得分"
        assert "L18_VaR" in result

    def test_apply_var_layer_missing_l1_etf(self, etf_sector_chip, etf_code_chip):
        """scores 中没有 L1_ETF 时也不报错。"""
        scores = {"L2_Holdings": 7.0}
        result = apply_var_layer(etf_sector_chip, scores, etf_code=etf_code_chip)
        assert "L18_VaR" in result
        # 不应新增 L1_ETF
        assert "L1_ETF" not in result


class TestVarSummary:
    def test_var_summary_is_string(self):
        """get_var_summary 返回字符串。"""
        summary = get_var_summary()
        assert isinstance(summary, str)
        assert len(summary) > 0
        # 包含关键信息
        assert "VaR" in summary
        assert "压力测试" in summary
        assert "风控建议" in summary


class TestStoicLayerStructure:
    def test_score_stoic_layer_structure(self, etf_sector_chip, etf_code_chip):
        """L14: score_stoic_layer 返回结构正确。"""
        result = score_stoic_layer(
            etf_sector_chip, risk_level=0.5, etf_code=etf_code_chip
        )
        assert isinstance(result, dict)
        expected_keys = {
            "score",
            "controllability",
            "tail_risk_score",
            "avg_drawdown",
            "tail_risk",
            "scenarios",
        }
        assert set(result.keys()) == expected_keys
        # 半导体 controllability = 3.5
        assert result["controllability"] == CONTROLLABILITY_SCORES["半导体"]
        # scenarios 应有 3 个情景
        assert len(result["scenarios"]) == 3


class TestControllabilityFuzzyMatch:
    def test_controllability_fuzzy_match(self):
        """模糊匹配: 不在字典中的字符串通过 substring 匹配最长 key。"""
        # "半导体ETF" 不在字典中, fuzzy match "半导体" (len=3) = 3.5
        # 注意 "半导体设备" (len=5) 不在 "半导体ETF" 中, 所以不会匹配它
        score = get_controllability("半导体ETF")
        assert score == 3.5, f"模糊匹配应返回'半导体'的3.5, got {score}"

        # "白酒LOF" fuzzy match "白酒" = 7.5
        score2 = get_controllability("白酒LOF")
        assert score2 == 7.5, f"模糊匹配应返回'白酒'的7.5, got {score2}"

        # "新能源车ETF" fuzzy match "新能源车" (len=4) = 5.0
        score3 = get_controllability("新能源车ETF")
        assert score3 == 5.0, f"模糊匹配应返回'新能源车'的5.0, got {score3}"

    def test_controllability_fuzzy_longest_match(self):
        """模糊匹配优先选择最长的 key。"""
        # "半导体设备ETF" 不在字典中
        # "半导体" (len=3) 和 "半导体设备" (len=5) 都是其 substring
        # 应选最长的 "半导体设备" = 3.0
        score = get_controllability("半导体设备ETF")
        assert score == 3.0, (
            f"模糊匹配应选最长 key '半导体设备'=3.0, got {score}"
        )


class TestSectorToVolKeyCoverage:
    def test_sector_to_vol_key_coverage(self):
        """SECTOR_TO_VOL_KEY 覆盖常见行业且映射目标有效。"""
        common_sectors = [
            "半导体", "创新药", "新能源", "红利低波", "券商",
            "银行", "保险", "金融科技", "宽基", "沪深300",
            "中证500", "中证1000", "上证50", "港股", "美股科技",
            "消费", "周期/资源", "军工", "基建", "公用事业",
            "可转债", "货币基金", "贵金属", "农产品",
        ]
        for sector in common_sectors:
            assert sector in SECTOR_TO_VOL_KEY, (
                f"常见行业 '{sector}' 未在 SECTOR_TO_VOL_KEY 中"
            )
            vol_key = SECTOR_TO_VOL_KEY[sector]
            assert vol_key in VOLATILITY_BENCHMARK, (
                f"'{sector}' 映射到 '{vol_key}' 但不在 VOLATILITY_BENCHMARK 中"
            )

    def test_sector_to_vol_key_all_resolve(self):
        """所有 SECTOR_TO_VOL_KEY 的 key 通过 get_volatility_benchmark 都能返回有效基准。

        注: 源码中 '跨境' → '跨境' 但 VOLATILITY_BENCHMARK 无 '跨境' key,
        get_volatility_benchmark 有 fallback 到 '宽基' 兜底, 此测试验证兜底生效。
        """
        from etf_platform.layers.l18_var_risk import get_volatility_benchmark

        for sector in SECTOR_TO_VOL_KEY.keys():
            bench = get_volatility_benchmark(sector)
            assert isinstance(bench, dict), f"'{sector}' 返回非 dict"
            assert "annual_vol" in bench, f"'{sector}' 基准缺 annual_vol"
            assert "var_95" in bench, f"'{sector}' 基准缺 var_95"
            assert "var_99" in bench, f"'{sector}' 基准缺 var_99"
            assert 0 < bench["annual_vol"] < 1, (
                f"'{sector}' annual_vol 异常: {bench['annual_vol']}"
            )
