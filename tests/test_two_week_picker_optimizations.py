# -*- coding: utf-8 -*-
"""two_week_picker 优化回归测试（2026-08-18）。

覆盖:
- news_sentiment 因子已接入 FACTORS 且静态权重保持 sum=1.0
- format_report 对单 ETF 预测（two_week_score=None）不崩溃
- format_report 的 Z 因子行使用当前字段，不再引用已移除 vol_health
- factor_ic 默认诊断因子与 two_week_picker 活动因子一致
- cli help 不再重复 archive 命令
"""
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

BASE = Path(__file__).resolve().parent.parent
SRC = BASE / "src"


def test_factors_include_news_sentiment_and_weights_sum_1():
    from etf_platform.decision.two_week_picker import FACTORS

    names = [f["name"] for f in FACTORS]
    assert "news_sentiment" in names
    total = sum(f["weight"] for f in FACTORS)
    assert total == pytest.approx(1.0, abs=1e-6)


def test_format_report_handles_none_two_week_score():
    from etf_platform.decision.two_week_picker import format_report

    rec = {
        "code": "510300", "name": "测试ETF", "risk_level": 0.3,
        "pipeline_score": 5.0, "two_week_score": None,
        "trend_signal": "neutral", "change_20d": 1.0, "return_10d": 0.5,
        "max_drawdown": -2.0, "volatility": 12, "volume_ratio": 1.0,
        "position_pct": 50, "sector": "宽基",
    }
    out = format_report([rec])
    assert "N/A" in out
    assert "测试ETF" in out


def test_format_report_z_factors_uses_current_fields():
    from etf_platform.decision.two_week_picker import format_report

    rec = {
        "code": "512480", "name": "芯片ETF", "risk_level": 0.6,
        "pipeline_score": 5.5, "two_week_score": 72,
        "trend_signal": "weak", "change_20d": -8.0, "return_10d": -2.0,
        "max_drawdown": -15.0, "volatility": 30, "volume_ratio": 1.2,
        "position_pct": 30, "sector": "半导体",
        "z_factors": {"oversold_depth": 1.2, "risk_adj_momentum": -0.5,
                      "drawdown_recov": 0.8, "sector_flow": 0.4,
                      "news_sentiment": 1.0, "behavioral": 0.0},
    }
    out = format_report([rec])
    assert "情绪+1.0" in out
    assert "vol_health" not in out


def test_factor_ic_default_factors_match_active_factors():
    from etf_platform.analysis.factor_ic import DEFAULT_FACTORS

    assert "news_sentiment" in DEFAULT_FACTORS
    assert "behavioral" not in DEFAULT_FACTORS


def test_cli_help_has_single_archive_entry():
    cli_path = SRC / "etf_platform" / "cli.py"
    lines = cli_path.read_text(encoding="utf-8").splitlines()
    archive_help = [line for line in lines if "etf archive [collect|list|show]" in line]
    assert len(archive_help) == 1