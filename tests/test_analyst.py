"""test_analyst.py — 与 analyst.py 实际接口对齐。
analyst.py 导出: analyze(code, profile, live, deep), PROFILES, PROFILE_ALIASES
模块属性: _ROTATION_LOCK, _rotation_cache (运行时生成)
"""
import threading
import pytest
from unittest.mock import patch

pytestmark = [pytest.mark.unit]


@pytest.fixture(autouse=True)
def _clean_rotation_cache():
    """清理模块级 _rotation_cache，保证测试隔离。"""
    import etf_platform.analyst as _mod
    from etf_platform.analyst import analyze
    had_mod = hasattr(_mod, "_rotation_cache")
    had_func = hasattr(analyze, "_rotation_cache")
    saved_mod = _mod._rotation_cache if had_mod else None
    saved_fun = analyze._rotation_cache if had_func else None
    if had_mod:
        del _mod._rotation_cache
    if had_func:
        del analyze._rotation_cache
    yield
    if had_mod:
        _mod._rotation_cache = saved_mod
    if had_func:
        analyze._rotation_cache = saved_fun


class TestAnalystModule:
    def test_analyst_module_import(self):
        """模块可正常导入且暴露 analyze 入口。"""
        from etf_platform import analyst
        assert analyst is not None
        assert hasattr(analyst, "analyze")
        assert callable(analyst.analyze)

    def test_analyst_has_rotation_lock(self):
        """_ROTATION_LOCK 存在且为 threading.Lock 实例。"""
        from etf_platform import analyst
        assert hasattr(analyst, "_ROTATION_LOCK")
        assert isinstance(analyst._ROTATION_LOCK, type(threading.Lock()))

    def test_detect_rotation_exists(self):
        """_detect_rotation 从 analysis.rotation 导入且可调用。"""
        from etf_platform import analyst
        assert hasattr(analyst, "_detect_rotation")
        assert callable(analyst._detect_rotation)

    def test_profiles_defined(self):
        """PROFILES 配置表完整。"""
        from etf_platform.analyst import PROFILES, PROFILE_ALIASES
        assert "conservative" in PROFILES
        assert "balanced" in PROFILES
        assert "aggressive" in PROFILES
        assert PROFILE_ALIASES.get("保守") == "conservative"
        assert PROFILE_ALIASES.get("均衡") == "balanced"
        assert PROFILE_ALIASES.get("进取") == "aggressive"


class TestRotationCache:
    def test_rotation_cache_attribute(self):
        """analyze 调用后拥有 _rotation_cache 属性。"""
        from etf_platform.analyst import analyze
        mock_result = {
            "layer_scores": {"L3_Material": 5.0, "L8_CapitalFlow": 6.0, "L9_Signals": 4.0},
            "sector": "半导体",
            "name": "芯片ETF",
        }
        mock_rotation = {"sectors": {"半导体": {"trend": "strong"}}}
        with patch("etf_platform.analyst._run_full", return_value=mock_result), \
             patch("etf_platform.analyst._detect_rotation", return_value=mock_rotation), \
             patch("etf_platform.analyst.load_etfs", return_value={}), \
             patch("etf_platform.analyst.load_dynamic_weights", return_value={}), \
             patch("etf_platform.analyst.generate_insight_report", return_value={"synthesis": "ok"}):
            result = analyze("159995", profile="balanced", live=False, deep=False)
        assert hasattr(analyze, "_rotation_cache")
        assert analyze._rotation_cache is mock_rotation

    def test_rotation_cache_double_checked_locking(self):
        """缓存已存在时不再次调用 _detect_rotation（双重检查锁定）。"""
        from etf_platform.analyst import analyze
        analyze._rotation_cache = {"sectors": {"预设": {"trend": "neutral"}}}
        mock_result = {"layer_scores": {}, "sector": "其他", "name": "测试ETF"}
        with patch("etf_platform.analyst._run_full", return_value=mock_result), \
             patch("etf_platform.analyst._detect_rotation") as mock_detect, \
             patch("etf_platform.analyst.load_etfs", return_value={}), \
             patch("etf_platform.analyst.load_dynamic_weights", return_value={}), \
             patch("etf_platform.analyst.generate_insight_report", return_value={}):
            result = analyze("000000", profile="balanced", live=False, deep=False)
        mock_detect.assert_not_called()


class TestAnalyzeFunction:
    def test_analyze_returns_dict(self):
        """analyze 返回字典，包含聚合后的关键字段（mock pipeline.run_full）。"""
        from etf_platform.analyst import analyze
        mock_result = {
            "layer_scores": {
                "L3_Material": 7.0, "L4_SupplyChain": 6.0, "L5_Tech": 8.0,
                "L6_Politics": 5.0, "L7_Irreplaceable": 6.0,
                "L8_CapitalFlow": 7.0, "L9_Signals": 5.0,
                "L10_Demand": 6.0, "L11_SectorRisk": 5.0,
                "L12_PoliticalRisk": 4.0, "L13_MacroCycle": 5.0,
            },
            "sector": "半导体",
            "name": "芯片ETF",
        }
        mock_rotation = {"sectors": {"半导体": {"trend": "strong"}}}
        with patch("etf_platform.analyst._run_full", return_value=mock_result), \
             patch("etf_platform.analyst._detect_rotation", return_value=mock_rotation), \
             patch("etf_platform.analyst.load_etfs",
                   return_value={"159995": {"sector": "半导体", "name": "芯片ETF"}}), \
             patch("etf_platform.analyst.load_dynamic_weights", return_value={}), \
             patch("etf_platform.analyst.generate_insight_report",
                   return_value={"synthesis": "ok"}):
            result = analyze("159995", profile="balanced", live=False, deep=True)
        assert isinstance(result, dict)
        assert result["sector"] == "半导体"
        assert result["sector_type"] == "B2B"
        assert "composite_score" in result
        assert isinstance(result["composite_score"], (int, float))
        assert "profile" in result
        assert result["profile"] == "均衡型"
        assert "rotation_signal" in result
        assert result["rotation_signal"] == {"trend": "strong"}
        assert "insight" in result
        for key in ("supply_score", "capital_score", "signal_score",
                    "demand_score", "cycle_score", "risk_score", "enhanced_score"):
            assert key in result

    def test_analyze_consumer_sector_type(self):
        """消费类板块 sector_type 正确分类为 '消费'。"""
        from etf_platform.analyst import analyze
        mock_result = {"layer_scores": {}, "sector": "白酒", "name": "白酒ETF"}
        with patch("etf_platform.analyst._run_full", return_value=mock_result), \
             patch("etf_platform.analyst._detect_rotation", return_value={"sectors": {}}), \
             patch("etf_platform.analyst.load_etfs", return_value={}), \
             patch("etf_platform.analyst.load_dynamic_weights", return_value={}), \
             patch("etf_platform.analyst.generate_insight_report", return_value={}):
            result = analyze("161725", profile="保守", live=False, deep=False)
        assert result["sector_type"] == "消费"
        assert result["profile"] == "保守型"
