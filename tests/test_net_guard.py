# -*- coding: utf-8 -*-
"""net_guard 回归测试  2026-09-16 审核 P0-1（V8 熔断）。"""
import time

import pytest

from etf_platform.utils import net_guard


def test_call_with_timeout_distinguishes_none_from_timeout():
    """正常返回 None 与超时返回 None 必须可区分（旧 run_with_timeout 做不到）。"""
    ok, v = net_guard.call_with_timeout(lambda: None, timeout=1)
    assert ok is True and v is None

    ok2, v2 = net_guard.call_with_timeout(lambda: time.sleep(5), timeout=0.1)
    assert ok2 is False and v2 is None


def test_call_with_timeout_reraises_exception():
    def boom():
        raise ValueError("boom")

    with pytest.raises(ValueError):
        net_guard.call_with_timeout(boom, timeout=1)


def test_call_v8_poisons_after_timeout_and_short_circuits():
    """超时 -> 熔断 -> 后续 call_v8 不再执行（这是避免进程 abort 的关键）。"""
    net_guard.reset_v8_state()
    calls = []

    def slow():
        calls.append(1)
        time.sleep(5)

    ok, v = net_guard.call_v8(slow, timeout=0.1)
    assert ok is False and v is None
    assert net_guard.v8_poisoned() is True
    assert "超时" in net_guard.v8_poison_reason()

    ok2, v2 = net_guard.call_v8(slow, timeout=0.1)
    assert ok2 is False and v2 is None
    assert len(calls) == 1, "熔断后不应再执行 V8 调用"

    net_guard.reset_v8_state()
    assert net_guard.v8_poisoned() is False
    assert net_guard.v8_poison_reason() == ""


def test_call_v8_passes_through_success():
    net_guard.reset_v8_state()
    ok, v = net_guard.call_v8(lambda a, b=0: a + b, 10, b=5, timeout=1)
    assert ok is True and v == 15
    assert net_guard.v8_poisoned() is False


def test_sector_momentum_returns_neutral_when_v8_fails(monkeypatch):
    """layer_live_adjustments 在 V8 熔断/失败时必须降级为中性 0.0，而不是抛错。"""
    from etf_platform.analysis import layer_live_adjustments as lla

    monkeypatch.setattr(lla, "call_v8", lambda *a, **k: (False, None))
    assert lla._get_sector_momentum("半导体") == 0.0
