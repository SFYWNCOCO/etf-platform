"""ETF折溢价率共享缓存 — L24 DipFlow / L16 premium 共用.

设计:
- 模块级缓存，同批次ETF只触发一次HTTP
- 优先东方财富 fund_etf_spot_em (含基金折价率字段)
- 超时/失败→Sina fallback→0.0
- 交易时段TTL=4h, 非交易=24h
"""
from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Optional

os.environ.setdefault("AKSHARE_PROGRESS", "0")

_PREMIUM_CACHE: dict[str, float] = {}
_CACHE_TS: float = 0.0
_CACHE_TTL: int = 14400  # 4h default


def _ttl_seconds() -> int:
    """交易时段4h, 非交易/周末24h."""
    try:
        now = datetime.now()
        weekday = now.weekday()
        if weekday >= 5:
            return 86400
        t = now.hour * 3600 + now.minute * 60
        if 9 * 3600 + 25 <= t <= 15 * 3600 + 5:
            return 14400
        return 86400
    except Exception:
        return 86400


def _cache_valid() -> bool:
    ttl = _ttl_seconds()
    return bool(_PREMIUM_CACHE) and (time.time() - _CACHE_TS) < ttl


def _fetch_eastmoney() -> dict[str, float]:
    """东方财富批量ETF折溢价率. 挂起即丢弃（08-12 修复：docstring 声称超时但调用并无保护）。"""
    import akshare as ak  # noqa: PLC0415

    from ..utils.thread_timeout import run_with_timeout
    df = run_with_timeout(ak.fund_etf_spot_em, timeout=30)
    result: dict[str, float] = {}
    if df is None:
        return result
    for _, row in df.iterrows():
        code = str(row.get("代码", "")).strip()
        if not code or not code[:6].isdigit():
            continue
        code = code[:6]
        try:
            val = float(row.get("基金折价率", 0.0) or 0.0)
            result[code] = val
        except (TypeError, ValueError):
            continue
    return result


def _fetch_sina_fallback(codes: list[str]) -> dict[str, float]:
    """Sina fallback: 只取价格, 折溢价率不可用时返回0."""
    import urllib.request  # noqa: PLC0415

    result: dict[str, float] = {}
    sina_codes = []
    for c in codes:
        prefix = "sz" if c.startswith(("15", "16")) else "sh"
        sina_codes.append(f"{prefix}{c}")
    url = "https://hq.sinajs.cn/list=" + ",".join(sina_codes)
    try:
        req = urllib.request.Request(url, headers={"Referer": "https://finance.sina.com.cn"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = resp.read()
        text = raw.decode("gbk", errors="replace")
        for line in text.splitlines():
            if "=" not in line:
                continue
            code_part = line.split("=")[0].split("_")[-1]
            code = code_part.lstrip("sh").lstrip("sz")[:6]
            if not code.isdigit():
                continue
            fields = line.split('"')[1].split(",") if '"' in line else []
            if len(fields) > 3:
                result[code] = 0.0  # Sina无IOPV, 用0占位
    except Exception:
        pass
    return result


def refresh_premium_cache(codes: Optional[list[str]] = None) -> dict[str, float]:
    """刷新折溢价缓存. codes=None时不主动拉取."""
    global _CACHE_TS  # noqa: PLW0603

    if _cache_valid():
        return dict(_PREMIUM_CACHE)

    target_codes = codes or []
    if not target_codes:
        return {}

    # 1) Eastmoney batch
    try:
        data = _fetch_eastmoney()
        _PREMIUM_CACHE.clear()
        _PREMIUM_CACHE.update(data)
        _CACHE_TS = time.time()
        return dict(_PREMIUM_CACHE)
    except Exception:
        pass

    # 2) Sina fallback
    try:
        sina_data = _fetch_sina_fallback(target_codes)
        _PREMIUM_CACHE.clear()
        _PREMIUM_CACHE.update(sina_data)
        _CACHE_TS = time.time()
        return dict(_PREMIUM_CACHE)
    except Exception:
        pass

    return {}


def get_premium_pct(code: str, sector: str = "", live: bool = False) -> Optional[float]:
    """获取单只ETF折溢价率.

    live=False: 返回缓存值, 无缓存则None (不触发HTTP)
    live=True: 尝试刷新缓存
    返回None表示无数据, 调用方应使用fallback.
    """
    code = str(code).lstrip("sh").lstrip("sz")[:6]

    if code in _PREMIUM_CACHE:
        return _PREMIUM_CACHE[code]

    if live:
        refresh_premium_cache([code])
        if code in _PREMIUM_CACHE:
            return _PREMIUM_CACHE[code]

    return None


def cache_size() -> int:
    """当前缓存ETF数量."""
    return len(_PREMIUM_CACHE)
