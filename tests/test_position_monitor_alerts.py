# -*- coding: utf-8 -*-
"""position_monitor 告警格式化回归测试（T2 档：核心生产路径修复防复发）。

背景（corrections #98, 2026-09-12）：
旧版 main() 中 `lines.append("[警告] " + "、".join(a["reasons"] for a in alerts))`
在单次告警触发 >=2 条规则（reasons 为 list[str] 多项）时抛
TypeError: sequence item 0: expected str instance, list found，
导致 cron mktmon000001 在 09-08/09-11 两个大跌日连续 crash 且告警文本零输出。
修复：抽出 format_alerts()，按 名称:原因1;原因2 逐告警扁平化后再 join。
"""
import importlib.util
import os

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.normpath(os.path.join(HERE, "..", "scripts", "position_monitor.py"))


@pytest.fixture(scope="module")
def pm():
    assert os.path.exists(SCRIPT), f"script missing: {SCRIPT}"
    spec = importlib.util.spec_from_file_location("position_monitor", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_format_alerts_multi_reason_single_alert(pm):
    out = pm.format_alerts([
        {"name": "机器人ETF", "code": "sz159050", "price": 0.84,
         "reasons": ["小时异动-3.50%", "日内异动-5.20%"]},
    ])
    assert out == "机器人ETF:小时异动-3.50%;日内异动-5.20%"


def test_format_alerts_multiple_alerts(pm):
    out = pm.format_alerts([
        {"name": "机器人ETF", "price": 0.84, "reasons": ["小时异动-3.50%"]},
        {"name": "创新药ETF", "price": 0.85, "reasons": ["日内异动+6.10%"]},
    ])
    assert out == "机器人ETF:小时异动-3.50%、创新药ETF:日内异动+6.10%"


def test_format_alerts_returns_str_not_list(pm):
    # 已知必错对照：旧实现的缺陷形态（reasons 直接进 join 参数）必须炸
    alerts = [{"name": "X", "reasons": ["a", "b"]}]
    with pytest.raises(TypeError):
        "、".join(a["reasons"] for a in alerts)
    # 新实现永远返回 str
    assert isinstance(pm.format_alerts(alerts), str)


def test_format_alerts_empty(pm):
    assert pm.format_alerts([]) == ""
