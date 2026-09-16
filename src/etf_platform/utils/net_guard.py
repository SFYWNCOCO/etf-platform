# -*- coding: utf-8 -*-
"""net_guard  外部数据调用守卫（超时 + V8 熔断）。

背景（2026-09-16 审核 P0-1）
--------------------------------------------------------------------------
utils/thread_timeout.run_with_timeout 的策略是「daemon 线程 + join(timeout)，
超时后遗弃线程」。对普通 requests 调用够用，但对 akshare 依赖 py_mini_racer(V8)
的接口是致命的：V8 上下文初始化不是线程安全的，被遗弃的线程仍停留在
_make_context 中，下一次调用再起一个线程  两个 V8 上下文并发初始化  进程级 abort：

    [FATAL:partition_address_space.cc(243)]
    Check failed: !IsConfigurablePoolInitialized()
    Windows fatal exception: code 0x80000003

实测（2026-09-16 全量 pytest）：跑到 17% 整个进程崩溃，退出码 -2147483645。
生产链路 weekly_top3 -> pipeline.run_full -> apply_live_adjustments ->
_get_sector_momentum -> ak.stock_board_industry_index_ths 走的是同一条路。

两层防护
--------------------------------------------------------------------------
1. call_with_timeout：与 run_with_timeout 同策略，但能区分「超时」与「函数正常
   返回 None」返回值恒为 (ok, value) 二元组。
2. call_v8：V8 类接口（akshare 的 *_ths 系）专用。串行执行 + 超时即进程内永久
   熔断，后续调用直接返回失败、不再创建任何新 V8 上下文。
   效果：把「进程崩溃、当天任务全灭」降级为「这一路数据源当天失效、返回中性值」。
"""

import logging
import threading
from typing import Any, Callable, Tuple, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")
DEFAULT_TIMEOUT = 30.0

# --- V8 熔断状态（进程级） -------------------------------------------------
_V8_LOCK = threading.Lock()
_V8_POISONED = threading.Event()
_V8_REASON = ""


def call_with_timeout(fn: Callable[..., T], *args, timeout: float = DEFAULT_TIMEOUT,
                      **kwargs) -> Tuple[bool, Any]:
    """在 daemon 线程中执行 fn，返回 (ok, value)。

    ok=True  -> value 为 fn 的返回值（可能本身就是 None）
    ok=False -> 超时，线程已遗弃，value 恒为 None
    fn 抛出的异常原样向上抛（与 run_with_timeout 语义一致）。
    """
    out: dict = {}

    def _target():
        try:
            out["v"] = fn(*args, **kwargs)
            out["done"] = True
        except BaseException as e:  # noqa: BLE001  原样抛给调用方
            out["e"] = e

    t = threading.Thread(target=_target, daemon=True,
                         name=f"netguard-{getattr(fn, '__name__', 'call')}")
    t.start()
    t.join(timeout)
    if t.is_alive():
        logger.warning("[net_guard] %s 超时 %.0fs，线程遗弃",
                       getattr(fn, "__name__", "call"), timeout)
        return False, None
    if "e" in out:
        raise out["e"]
    return True, out.get("v")


def call_v8(fn: Callable[..., T], *args, timeout: float = DEFAULT_TIMEOUT,
            **kwargs) -> Tuple[bool, Any]:
    """V8 类接口专用：全局串行 + 超时即熔断。返回 (ok, value)。

    熔断后本进程内所有后续 call_v8 直接返回 (False, None)，不再触碰 V8 
    这是为了避免「遗弃线程仍在初始化 V8 时，第二个线程并发初始化」导致进程 abort。
    """
    global _V8_REASON
    if _V8_POISONED.is_set():
        return False, None
    with _V8_LOCK:
        if _V8_POISONED.is_set():
            return False, None
        ok, value = call_with_timeout(fn, *args, timeout=timeout, **kwargs)
        if not ok:
            _V8_REASON = f"{getattr(fn, '__name__', 'call')} 超时 {timeout:.0f}s"
            _V8_POISONED.set()
            logger.error(
                "[net_guard] V8 接口 %s 超时 -> 本进程内熔断后续 V8 调用（"
                "避免 py_mini_racer 并发初始化导致进程 abort）；本次该数据源降级",
                _V8_REASON)
        return ok, value


def v8_poisoned() -> bool:
    """本进程内 V8 数据源是否已熔断。"""
    return _V8_POISONED.is_set()


def v8_poison_reason() -> str:
    """熔断原因（未熔断时为空串）。"""
    return _V8_REASON


def reset_v8_state() -> None:
    """仅供测试：清除熔断状态。"""
    global _V8_REASON
    _V8_POISONED.clear()
    _V8_REASON = ""
