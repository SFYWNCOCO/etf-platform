#!/usr/bin/env python3
"""dividend_timing_cron_wrapper.py — 红利ETF择时信号 cron 入口

每交易日收盘后运行，计算红利ETF股息率与国债利差，输出信号。
脚本保留在 etf-platform/scripts/，cron 指向此 wrapper。
"""
import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parent
PLATFORM_ROOT = BASE.parent if BASE.name == "scripts" else BASE.parent.parent
SRC = PLATFORM_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def main():
    """运行红利ETF择时信号，输出JSON结果"""
    script = BASE / "dividend_timing_signal.py"
    if not script.exists():
        print(f"[FAIL] 脚本不存在: {script}", file=sys.stderr)
        sys.exit(1)

    try:
        proc = subprocess.run(
            [sys.executable, str(script), "--json"],
            cwd=str(BASE),
            capture_output=True,
            text=True,
            timeout=60,
        )

        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout).strip()[-500:]
            print(f"[FAIL] 择时信号失败: {err}", file=sys.stderr)
            sys.exit(proc.returncode)

        signal = json.loads(proc.stdout.strip())

        # 输出关键信息
        print(f"红利ETF择时信号 ({signal.get('timestamp', '?')})")
        print(f"  国债收益率: {signal.get('bond_yield')}%")
        print(f"  红利ETF股息率: {signal.get('aggregate_dividend_yield')}%")
        print(f"  利差: {signal.get('spread')}%")
        print(f"  建议: {signal.get('recommendation')}")
        print(f"  原因: {signal.get('reason', '')}")

        # 如果信号有变化，输出详细警告
        rec = signal.get("recommendation", "")
        if rec == "减持":
            print(f"\n[警告] 利差 {signal.get('spread')}% < {1.5}% 阈值，建议减持红利ETF")
        elif rec == "增持":
            print(f"\n[OK] 利差 {signal.get('spread')}% > {2.5}% 阈值，建议增持红利ETF")

        sys.exit(0)

    except subprocess.TimeoutExpired:
        print("[FAIL] 超时 (60s)", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[FAIL] {type(e).__name__}: {str(e)[:200]}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
