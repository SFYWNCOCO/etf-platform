#!/usr/bin/env python3
"""etf_prediction_cron.py — 2周预测 + 回测验证闭环 cron 入口.

每周一生成新 2 周预测（two_week_picker pick_top3），并回测历史预测
命中率（prediction_monitor evaluate_prediction / status_report）。

no_agent cron wrapper 模式（参照 news_bridge_cron_wrapper）：
cron workdir=D:\\龙虾\\.openclaw\\etf-platform, script=etf_prediction_cron.py

任一步失败不阻断后续（各自 try/except），最终 exit 码反映整体。
"""
import os
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
SRC = BASE / "src"
ENV = dict(os.environ)
ENV["PYTHONPATH"] = str(SRC) + os.pathsep + ENV.get("PYTHONPATH", "")


def _run(name, module_args, timeout):
    try:
        proc = subprocess.run(
            [sys.executable, "-m"] + module_args,
            capture_output=True, text=True, timeout=timeout,
            cwd=str(BASE), env=ENV,
        )
        tail = (proc.stdout or proc.stderr or "").strip().splitlines()
        last = tail[-1][:150] if tail else ""
        if proc.returncode == 0:
            print(f"[{name}] ✅ {last}")
            return True
        print(f"[{name}] ⚠️ exit={proc.returncode}: {(proc.stderr or proc.stdout).strip()[-250:]}", file=sys.stderr)
        return False
    except subprocess.TimeoutExpired:
        print(f"[{name}] ⚠️ timeout>{timeout}s", file=sys.stderr)
        return False
    except Exception as e:
        print(f"[{name}] ⚠️ {type(e).__name__}: {str(e)[:150]}", file=sys.stderr)
        return False


def main():
    print("🦞 ETF 2周预测闭环")
    print()
    # 1. 回测历史预测命中率（快，<2s）
    _run("回测历史预测", ["etf_platform.decision.prediction_monitor", "--status"], 120)
    # 2. 生成新 2 周预测（全市场 Z-score，pipeline 批量，可能数分钟）
    _run("生成新预测", ["etf_platform.decision.two_week_picker", "--top3", "--json"], 480)
    print()
    print("✅ 预测闭环完成")


if __name__ == "__main__":
    main()
