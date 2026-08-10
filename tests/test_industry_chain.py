"""d751 任务2 产业链传导测试."""
import pytest

from etf_platform.analysis.industry_chain import apply_chain_to_signals, propagate_signal

pytestmark = [pytest.mark.unit]


def test_propagate_bullish_downstream():
    out = propagate_signal("新能源", "看多", "强")
    car = next((x for x in out if x["sector"] == "汽车"), None)
    assert car is not None
    assert car["direction"] == "看多"
    assert car["strength"] == "中"


def test_propagate_strength_degrades():
    strong = propagate_signal("新能源", "看多", "强")
    assert strong and all(x["strength"] == "中" for x in strong)
    medium = propagate_signal("新能源", "看多", "中")
    assert medium and all(x["strength"] == "弱" for x in medium)


def test_neutral_not_propagated():
    assert propagate_signal("新能源", "中性", "强") == []


def test_weak_not_propagated():
    assert propagate_signal("新能源", "看多", "弱") == []


def test_apply_chain_to_signals():
    s = {"新能源": {"direction": "看多", "strength": "强"}}
    out = apply_chain_to_signals(s)
    # 原信号保留且不被覆盖
    assert "新能源" in out
    assert out["新能源"] == s["新能源"]
    # 传导信号已生成且标记来源
    chain_hits = {k: v for k, v in out.items() if k != "新能源"}
    assert chain_hits
    assert all(str(v.get("source", "")).startswith("chain:") for v in chain_hits.values())


def test_propagate_unknown_sector():
    assert propagate_signal("不存在的板块", "看多", "强") == []
