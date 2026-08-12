#!/usr/bin/env python3
"""etf_holdings_refresh.py — 全量刷新 ETF 持仓缓存（收盘后 cron 入口）.

用法:
    python etf_holdings_refresh.py            # 全量刷新并写盘（exit 0/1）
    python etf_holdings_refresh.py --dry-run  # 只预览统计，不写盘
    python etf_holdings_refresh.py --limit N  # 只刷新前 N 只（调试用）

持仓季度披露、变化慢，建议周度调度（如每交易日收盘后 15:10 后）。
有防覆盖保护：有效请求比例 <50% 视为源故障，保留旧缓存（exit 1）。
"""
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
SRC = BASE / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def main() -> int:
    dry_run = "--dry-run" in sys.argv[1:]
    limit = None
    for a in sys.argv[1:]:
        if a.startswith("--limit="):
            limit = int(a.split("=")[1])

    import etf_platform.analysis.holdings_fetcher as hf

    if dry_run:
        # 只预览不写盘：屏蔽磁盘写入（cache + checkpoint），仍走 refresh_all 统计
        hf._save_disk_cache = lambda *a, **k: False
        hf._save_checkpoint = lambda *a, **k: None

    stats = hf.refresh_all(limit=limit)
    print(
        f"[holdings] total={stats['total']} ok={stats['ok']} empty={stats['empty']} "
        f"failed={stats['failed']} ratio={stats['success_ratio']} saved={stats['saved']}"
    )

    high_fail = stats["failed"] > stats["total"] * 0.3
    if high_fail:
        print(f"[holdings] ⚠️ 失败率过高({stats['failed']}/{stats['total']})", file=sys.stderr)
    if dry_run:
        print("[holdings] dry-run 模式：未写盘，以上为预览统计", file=sys.stderr)
        return 1 if high_fail else 0
    return 0 if stats["saved"] else 1


if __name__ == "__main__":
    sys.exit(main())
