"""策略优化器 - 历史决策分析"""
import json
from pathlib import Path

def analyze_by_mode(decisions, scores):
    mode_stats = {}
    for mode in ["defensive", "balanced", "aggressive"]:
        md = [d for d in decisions if d.get("mode", "") == mode]
        if not md: mode_stats[mode] = {"count":0,"win_rate":0,"avg_return":0}; continue
        total = len(md); wins = sum(1 for d in md if d.get("pnl_pct",0)>0)
        avg = sum(d.get("pnl_pct",0) for d in md)/total if total else 0
        mode_stats[mode] = {"count":total,"win_rate":round(wins/total*100,1) if total else 0,"avg_return":round(avg,2)}
    return mode_stats

def compare_strategies(decisions, scores):
    ma = analyze_by_mode(decisions, scores)
    best = max(ma.items(), key=lambda x: x[1].get("win_rate",0)) if ma else None
    suggestions = []
    if best and best[1]["win_rate"] > 50:
        suggestions.append({"recommendation": f"提高{best[0]}模式权重", "reason": f"历史胜率{best[1]['win_rate']}%"})
    return {"mode_analysis": ma, "suggestions": suggestions, "total_decisions": len(decisions)}

def load_decision_log(data_dir=None):
    if data_dir is None:
        data_dir = Path(__file__).resolve().parent.parent.parent.parent / "data"
    log = Path(data_dir) / "etf_decisions_log.json"
    if log.exists():
        with open(log, "r", encoding="utf-8") as f: return json.load(f)
    return []
