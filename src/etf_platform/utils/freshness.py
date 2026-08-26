"""静态数据文件时效工具.

config 下的材料价格等静态快照 mtime 可能数周旧 (k090 锂价教训):
消费方需要 as-of 标记来区分"实时数据"与"陈旧先验", 而不是静默当作现价。
"""
from datetime import datetime
from pathlib import Path


def as_of(path, stale_days=14):
    """返回文件时效快照 dict.

    不存在 → status=missing; mtime 距今超过 stale_days 天 → status=stale;
    否则 → status=fresh。
    """
    p = Path(path)
    now = datetime.now()
    snap = {
        "exists": p.exists(),
        "path": str(path),
        "mtime_iso": None,
        "age_days": None,
        "status": "missing",
        "checked_at": now.isoformat(timespec="seconds"),
    }
    if not snap["exists"]:
        return snap
    mtime = datetime.fromtimestamp(p.stat().st_mtime)
    snap["mtime_iso"] = mtime.isoformat(timespec="seconds")
    snap["age_days"] = (now - mtime).total_seconds() / 86400.0
    # 阈值比较: 超过 stale_days 未更新的静态快照降级为"先验"而非现价
    snap["status"] = "stale" if snap["age_days"] > stale_days else "fresh"
    return snap
