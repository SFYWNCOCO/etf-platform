#!/usr/bin/env python3
"""
历史趋势追踪模块 — 跟踪行业新闻情绪的历史变化

功能：
1. 记录每日/每周情绪快照
2. 计算趋势变化（改善/恶化）
3. 提供趋势信号（连续改善/连续恶化）
4. 存储历史数据用于回测和策略调整

用法：
  python scripts/trend_tracker.py --snapshot  # 记录当前快照
  python scripts/trend_tracker.py --analyze    # 分析历史趋势
  python scripts/trend_tracker.py --report     # 生成趋势报告
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

_BASE = Path(__file__).resolve().parent.parent
_DATA = _BASE / "data"
_SENT_FILE = _DATA / "news_sentiment.json"
_HISTORY_FILE = _DATA / "news_sentiment_history.json"


def load_history() -> Dict:
    """加载历史情绪数据"""
    if not _HISTORY_FILE.exists():
        return {"snapshots": []}
    try:
        with open(_HISTORY_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"snapshots": []}


def save_history(history: Dict) -> None:
    """保存历史情绪数据"""
    with open(_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def load_current_sentiment() -> Dict:
    """加载当前情绪数据"""
    if not _SENT_FILE.exists():
        return {}
    try:
        with open(_SENT_FILE) as f:
            d = json.load(f)
        return d.get("sectors", {})
    except (json.JSONDecodeError, OSError):
        return {}


def take_snapshot() -> Dict:
    """记录当前情绪快照"""
    current = load_current_sentiment()
    snapshot = {
        "timestamp": datetime.now().isoformat(),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "sectors": {},
    }
    
    for sector, info in current.items():
        direction = info.get("direction", "中性")
        strength = info.get("strength", "弱")
        
        # 转换为数值便于计算
        direction_map = {
            "看多": 1.0,
            "中性": 0.0,
            "看空": -1.0,
        }
        strength_map = {
            "弱": 0.5,
            "中": 0.75,
            "强": 1.0,
        }
        
        score = direction_map.get(direction, 0.0) * strength_map.get(strength, 0.5)
        
        snapshot["sectors"][sector] = {
            "direction": direction,
            "strength": strength,
            "score": round(score, 2),
            "note": info.get("note", ""),
        }
    
    # 保存快照
    history = load_history()
    history["snapshots"].append(snapshot)
    
    # 只保留最近30天数据
    cutoff = datetime.now() - timedelta(days=30)
    history["snapshots"] = [
        s for s in history["snapshots"]
        if datetime.fromisoformat(s["timestamp"]) > cutoff
    ]
    
    save_history(history)
    return snapshot


def analyze_trend(sector: str, window: int = 7) -> Dict:
    """分析单个行业的情绪趋势"""
    history = load_history()
    snapshots = history.get("snapshots", [])
    
    if len(snapshots) < 2:
        return {
            "sector": sector,
            "trend": "unknown",
            "direction": "无数据",
            "change": 0.0,
            "scores": [],
        }
    
    # 获取最近window天的数据
    recent = []
    for s in snapshots[-window:]:
        if sector in s.get("sectors", {}):
            recent.append({
                "date": s["date"],
                "score": s["sectors"][sector]["score"],
                "direction": s["sectors"][sector]["direction"],
            })
    
    if len(recent) < 2:
        return {
            "sector": sector,
            "trend": "unknown",
            "direction": "数据不足",
            "change": 0.0,
            "scores": recent,
        }
    
    # 计算趋势
    current_score = recent[-1]["score"]
    prev_score = recent[-2]["score"]
    change = current_score - prev_score
    
    # 计算移动平均
    avg_score = sum(r["score"] for r in recent) / len(recent)
    
    # 判断趋势
    if change > 0.1:
        trend = "improving"
        direction = "改善中"
    elif change < -0.1:
        trend = "deteriorating"
        direction = "恶化中"
    else:
        trend = "stable"
        direction = "稳定"
    
    # 连续趋势判断
    if len(recent) >= 3:
        improving_count = sum(1 for i in range(1, len(recent)) if recent[i]["score"] > recent[i-1]["score"])
        deteriorating_count = sum(1 for i in range(1, len(recent)) if recent[i]["score"] < recent[i-1]["score"])
        
        if improving_count >= 2:
            trend = "improving"
            direction = "连续改善"
        elif deteriorating_count >= 2:
            trend = "deteriorating"
            direction = "连续恶化"
    
    return {
        "sector": sector,
        "trend": trend,
        "direction": direction,
        "change": round(change, 2),
        "avg_score": round(avg_score, 2),
        "scores": recent,
    }


def generate_report() -> str:
    """生成趋势报告"""
    history = load_history()
    snapshots = history.get("snapshots", [])
    
    if not snapshots:
        return "暂无历史数据"
    
    report = []
    report.append("=" * 60)
    report.append("📈 行业新闻情绪趋势报告")
    report.append(f"📅 数据范围: {snapshots[0]['date']} ~ {snapshots[-1]['date']}")
    report.append(f"📊 快照数量: {len(snapshots)}")
    report.append("")
    
    # 分析每个行业
    sectors = set()
    for s in snapshots:
        sectors.update(s.get("sectors", {}).keys())
    
    for sector in sorted(sectors):
        trend = analyze_trend(sector, window=7)
        
        # 趋势图标
        trend_icon = {
            "improving": "📈",
            "deteriorating": "📉",
            "stable": "➡️",
            "unknown": "❓",
        }.get(trend["trend"], "❓")
        
        report.append(f"{trend_icon} {sector:12s}: {trend['direction']}")
        report.append(f"     变化: {trend['change']:+.2f} | 平均: {trend.get('avg_score', 0):+.2f}")
        
        if trend["scores"]:
            latest = trend["scores"][-1]
            report.append(f"     当前: {latest['direction']} ({latest['score']:+.2f})")
        
        report.append("")
    
    return "\n".join(report)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="新闻情绪趋势追踪")
    parser.add_argument("--snapshot", action="store_true", help="记录当前快照")
    parser.add_argument("--analyze", type=str, help="分析指定行业的趋势")
    parser.add_argument("--report", action="store_true", help="生成趋势报告")
    args = parser.parse_args()
    
    if args.snapshot:
        snapshot = take_snapshot()
        print(f"✅ 已记录快照: {snapshot['date']}")
        print(f"   行业数: {len(snapshot['sectors'])}")
        for s, info in sorted(snapshot['sectors'].items()):
            print(f"   {s}: {info['direction']} ({info['score']:+.2f})")
    
    elif args.analyze:
        trend = analyze_trend(args.analyze)
        print(f"=== {args.analyze} 趋势分析 ===")
        print(f"趋势: {trend['direction']}")
        print(f"变化: {trend['change']:+.2f}")
        print(f"平均分: {trend['avg_score']:+.2f}")
        if trend['scores']:
            print("最近数据:")
            for s in trend['scores']:
                print(f"  {s['date']}: {s['direction']} ({s['score']:+.2f})")
    
    elif args.report:
        print(generate_report())
    
    else:
        parser.print_help()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
