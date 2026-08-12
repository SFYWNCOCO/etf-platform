# -*- coding: utf-8 -*-
"""线程看门狗 — 包裹无法设置 timeout 的外部调用（akshare 等），主流程不挂死。

背景：akshare 内部 requests 无显式 timeout，网络阻塞时调用可无限挂起（cron 场景
直接拖死整个 wrapper）。用 daemon 线程 + join(timeout) 保证主流程最迟等待
timeout 秒；超时后后台线程继续运行（随进程退出被回收），结果丢弃并打 warning。

复用自 analysis/qvix_regime.py::_fetch_qvix_with_timeout 的同款模式。
"""
import logging
import threading
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def run_with_timeout(fn: Callable[..., T], *args, timeout: float = 30.0, **kwargs):
    """在 daemon 线程中执行 fn，超时返回 None（异常原样抛出给调用方处理）。

    返回 None 有两种可能：fn 正常返回 None，或超时（此时已打 warning）。
    """
    out: dict = {}

    def _target():
        try:
            out["v"] = fn(*args, **kwargs)
        except Exception as e:
            out["e"] = e

    t = threading.Thread(
        target=_target,
        daemon=True,
        name=f"timeout-{getattr(fn, '__name__', 'call')}",
    )
    t.start()
    t.join(timeout=timeout)
    if t.is_alive():
        logger.warning("[thread_timeout] %s 执行超时 %.0fs，结果丢弃",
                       getattr(fn, "__name__", "call"), timeout)
        return None
    if "e" in out:
        raise out["e"]
    return out.get("v")
