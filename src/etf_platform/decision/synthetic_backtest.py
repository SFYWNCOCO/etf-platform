#!/usr/bin/env python3
"""
synthetic_backtest.py — 合成回测引擎 v1.1 (Fast Path)

v1.1: 抛弃逐条akshare调用。使用session缓存的TrendSnapshot做评分，
      前向验证改为可选background模式。快速路径<10s完成100只ETF评分。

用法:
  python -m etf_platform.decision.synthetic_backtest          # 快速评分
  python -m etf_platform.decision.synthetic_backtest --deep   # 深度回测(慢)
"""

import json
import sys
import time
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent.parent  # etf-platform/
DATA_DIR = BASE / "data"


def run_quick_scan(max_etfs: int = 100) -> dict:
    """快速扫描: 用TrendSnapshot评分所有ETF，分析分数分布和行业覆盖。

    不调用akshare（使用session缓存），不验证前向收益。
    用于快速诊断评分体系的统计特性。
    """
    t0 = time.time()

    from etf_platform.data.kline import get_trend
    from etf_platform.config_loader import load_etfs

    etfs = load_etfs()
    EXCLUDE_SECTORS = {"货币基金", "利率债", "信用债", "债券", "国债", "货币"}
    EXCLUDE_KEYWORDS = ["沪深300", "中证500", "中证1000", "上证50", "科创50", "科创100", "创业板"]

    scored: list[dict] = []
    sector_stats: dict[str, list[float]] = defaultdict(list)
    errors: list[str] = []

    count = 0
    for code, info in etfs.items():
        if not code.isdigit():
            continue
        if info.get("sector", "") in EXCLUDE_SECTORS:
            continue
        if info.get("access") != "buyable":
            continue
        name = info.get("name", "")
        if any(kw in name for kw in EXCLUDE_KEYWORDS):
            continue

        count += 1
        if count > max_etfs:
            break

        try:
            trend = get_trend(code)
            if trend is None or trend.data_days < 20:
                continue

            # Simplified score (directionally similar to Z-score)
            change_20d = trend.change_20d
            volatility = trend.volatility_20d
            position = trend.position_pct
            volume_ratio = getattr(trend, "volume_ratio_5_20", 1.0)

            # Score: favor oversold + low vol + low position + high volume
            score = 50.0
            score -= change_20d * 0.25       # Oversold = higher score
            score -= volatility * 0.3         # Lower vol = higher score
            score += max(0, 50 - position) * 0.2  # Room to run
            score += (volume_ratio - 1) * 5   # Volume surge bonus
            score = max(5.0, min(95.0, score))

            sector = info.get("sector", "未知")

            scored.append({
                "code": code,
                "name": name,
                "sector": sector,
                "score": round(score, 1),
                "change_20d": round(change_20d, 1),
                "volatility": round(volatility, 1),
                "position": round(position, 1),
                "volume_ratio": round(volume_ratio, 2),
                "trend_signal": trend.trend_signal,
                "data_days": trend.data_days,
            })

            sector_stats[sector].append(score)

        except (KeyError, ValueError, TypeError, AttributeError, OSError) as e:
            errors.append(f"{code}: {e}")
            continue

    # Sort and dedup
    scored.sort(key=lambda x: -x["score"])
    top3: list[dict] = []
    seen: set[str] = set()
    for s in scored:
        if s["sector"] not in seen:
            top3.append(s)
            seen.add(s["sector"])
        if len(top3) >= 3:
            break

    # Sector analysis
    sector_summary = {}
    for sector, scores in sorted(sector_stats.items(), key=lambda x: -len(x[1])):
        if len(scores) >= 2:
            sector_summary[sector] = {
                "count": len(scores),
                "avg_score": round(sum(scores) / len(scores), 1),
                "max_score": round(max(scores), 1),
                "min_score": round(min(scores), 1),
            }

    # Score distribution
    dist = {"0-20": 0, "20-40": 0, "40-60": 0, "60-80": 0, "80-100": 0}
    for s in scored:
        if s["score"] < 20:
            dist["0-20"] += 1
        elif s["score"] < 40:
            dist["20-40"] += 1
        elif s["score"] < 60:
            dist["40-60"] += 1
        elif s["score"] < 80:
            dist["60-80"] += 1
        else:
            dist["80-100"] += 1

    # Trend signal distribution
    signals = defaultdict(int)
    for s in scored:
        signals[s["trend_signal"]] += 1

    elapsed = time.time() - t0

    return {
        "version": "1.1",
        "mode": "quick_scan",
        "total_etfs_scored": len(scored),
        "errors": len(errors),
        "elapsed_seconds": round(elapsed, 1),
        "top3": top3,
        "score_distribution": dist,
        "trend_signals": dict(signals),
        "sector_summary": sector_summary,
        "all_scored": scored,
    }


def format_report(result: dict) -> str:
    """Format quick scan results."""
    if result.get("total_etfs_scored", 0) == 0:
        return "❌ 无有效数据"

    lines = [
        "🔍 ETF快速评分扫描",
        f"{'=' * 60}",
        "",
        f"  扫描: {result['total_etfs_scored']}只ETF  |  "
        f"耗时: {result['elapsed_seconds']}s",
        f"  错误: {result['errors']}只",
        "",
        "  ── Top 3 (行业去重) ──",
    ]

    for i, etf in enumerate(result.get("top3", []), 1):
        trend_icon = {"oversold": "📉", "uptrend": "📈", "neutral": "➡️"}.get(
            etf["trend_signal"], "❓"
        )
        lines.append(
            f"  {i}. {etf['code']} {etf['name']:<20s} "
            f"[{etf['sector']}] "
            f"评分={etf['score']:.0f}  "
            f"{trend_icon} {etf['trend_signal']}  "
            f"20日={etf['change_20d']:+.1f}%  "
            f"位置={etf['position']:.0f}%"
        )

    lines.append("")
    lines.append("  ── 分数分布 ──")
    dist = result.get("score_distribution", {})
    total = sum(dist.values()) or 1
    for bucket in ["0-20", "20-40", "40-60", "60-80", "80-100"]:
        count = dist.get(bucket, 0)
        bar = "█" * int(count / total * 30) if total > 0 else ""
        lines.append(f"  {bucket:>6}: {bar} {count}只 ({count/total*100:.0f}%)")

    lines.append("")
    lines.append("  ── 趋势信号分布 ──")
    signals = result.get("trend_signals", {})
    for sig, count in sorted(signals.items(), key=lambda x: -x[1]):
        lines.append(f"  {sig:>10}: {count}只")

    lines.append("")
    lines.append("  ── 行业概览 (Top 10) ──")
    sectors = result.get("sector_summary", {})
    for i, (sector, stats) in enumerate(
        sorted(sectors.items(), key=lambda x: -x[1]["count"])[:10]
    ):
        lines.append(
            f"  {sector:<16s} {stats['count']:>3d}只  "
            f"均分={stats['avg_score']:.0f}  "
            f"最高={stats['max_score']:.0f}  "
            f"最低={stats['min_score']:.0f}"
        )

    lines.append("")
    lines.append(f"{'=' * 60}")

    return "\n".join(lines)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ETF合成回测/快速扫描")
    parser.add_argument("--deep", action="store_true", help="深度回测(慢,ahtklib调用)")
    parser.add_argument("--max", type=int, default=100, help="最大ETF数")
    parser.add_argument("--json", action="store_true", help="JSON输出")
    parser.add_argument("--output", type=str, help="保存到文件")
    args = parser.parse_args()

    if args.deep:
        print("深度回测模式暂未实现(需akshare批量接口)", file=sys.stderr)
        print("请使用默认快速扫描模式", file=sys.stderr)
        sys.exit(1)

    result = run_quick_scan(max_etfs=args.max)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"✅ 已保存到 {out_path}")

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_report(result))
