#!/usr/bin/env python3
"""news_bridge_cron_wrapper.py — no_agent cron wrapper 完整新闻管线 v2.

profile scripts 版（cron 从 profile scripts 目录解析 script）。
顺序执行: fetch_news_sources → policy_fetcher(gov.cn) → auto_sentiment → news_to_etf_bridge
任一步失败不阻断后续（各自 try/except），最终 exit 码反映整体。
"""
import subprocess
import sys
from pathlib import Path

BASE = Path(r"D:\龙虾\.openclaw\etf-platform")

STEPS = [
    ("fetch_news_sources", ["scripts/fetch_news_sources.py"], 180, False),
    ("policy_fetcher", ["policy_fetcher.py"], 120, False),
    ("auto_sentiment", ["auto_sentiment.py"], 60, False),
    ("news_to_etf_bridge", ["news_to_etf_bridge.py", "--auto"], 180, False),
]

if __name__ == "__main__":
    failures = []
    for name, args, timeout, _ in STEPS:
        # fetch_news_sources 在 .openclaw/scripts/ 下，其余在 etf-platform/
        if name == "fetch_news_sources":
            script = Path(r"D:\龙虾\.openclaw") / args[0]
            cwd = Path(r"D:\龙虾\.openclaw")
            cmd = [sys.executable, str(script)]
        else:
            script = BASE / args[0]
            cwd = BASE
            cmd = [sys.executable, str(script)] + args[1:]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=str(cwd))
            if proc.returncode == 0:
                print(f"[{name}] ✅ {(proc.stdout or '').strip().splitlines()[-1] if proc.stdout.strip() else ''}")
            else:
                err = (proc.stderr or proc.stdout).strip()[-200:]
                print(f"[{name}] ⚠️ exit={proc.returncode}: {err}")
                failures.append(name)
        except subprocess.TimeoutExpired:
            print(f"[{name}] ⚠️ timeout>{timeout}s")
            failures.append(name)
        except Exception as e:
            print(f"[{name}] ⚠️ {type(e).__name__}: {str(e)[:120]}")
            failures.append(name)

    if failures:
        print(f"\n新闻管线部分失败: {failures}")
        sys.exit(1)
    print("\n✅ 新闻管线全链完成")
    sys.exit(0)
