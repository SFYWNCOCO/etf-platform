"""Tests for utils/thread_timeout.py — akshare watchdog（08-12 新增，审核 #6）。"""
import logging
import time

import pytest

from etf_platform.utils.thread_timeout import run_with_timeout

pytestmark = [pytest.mark.unit]


def test_returns_value_when_fast():
    assert run_with_timeout(lambda: 42, timeout=1) == 42


def test_timeout_returns_none_and_warns(caplog):
    with caplog.at_level(logging.WARNING):
        out = run_with_timeout(lambda: time.sleep(5), timeout=0.1)
    assert out is None
    assert "超时" in caplog.text


def test_exception_propagates_to_caller():
    def boom():
        raise ValueError("boom")
    with pytest.raises(ValueError):
        run_with_timeout(boom, timeout=1)


def test_args_kwargs_passed_through():
    assert run_with_timeout(lambda a, b=0: a + b, 10, b=5, timeout=1) == 15
