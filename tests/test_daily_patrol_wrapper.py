"""test_daily_patrol_wrapper.py — 市场概览回归门。

防 P0 复发：df.iloc 下标形态变更（如误写 df.iloc(n)）导致 TypeError 被裸 except
吞掉、最强/最弱行缺失。monkeypatch finance_search.sina_etf_spot 返回构造 DataFrame，
断言 "今日最强"/"今日最弱" 行真实打印。
"""
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent


def _load_wrapper():
    spec = importlib.util.spec_from_file_location(
        "etf_daily_patrol_wrapper", ROOT / "etf_daily_patrol_wrapper.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_market_overview_prints_best_worst(capsys):
    wrapper = _load_wrapper()

    fake_df = pd.DataFrame(
        {
            "代码": ["510300", "159050", "512890"],
            "名称": ["沪深300", "机器人ETF", "红利ETF"],
            "涨跌幅": ["-1.23%", "+3.45%", "+0.50%"],
        }
    )

    fake_module = ModuleType("finance_search")
    fake_module.sina_etf_spot = lambda: fake_df
    sys.modules["finance_search"] = fake_module

    try:
        wrapper.market_overview()
    finally:
        sys.modules.pop("finance_search", None)

    out = capsys.readouterr().out
    assert "今日最强: 159050 机器人ETF (+3.45%)" in out, out
    assert "今日最弱: 510300 沪深300 (-1.23%)" in out, out
    assert "中位涨幅" in out, out
    # 裸 except 吞 TypeError 的特征：出现 [警告] Sina spot 失败
    assert "Sina spot 失败" not in out, out


def test_market_overview_empty_dataframe(capsys):
    wrapper = _load_wrapper()

    fake_module = ModuleType("finance_search")
    fake_module.sina_etf_spot = lambda: pd.DataFrame(
        columns=["代码", "名称", "涨跌幅", "现价"]
    )
    sys.modules["finance_search"] = fake_module

    try:
        wrapper.market_overview()
    finally:
        sys.modules.pop("finance_search", None)

    out = capsys.readouterr().out
    assert "可投 ETF 总数: **0**" in out, out
    assert "Sina spot 失败" not in out, out
