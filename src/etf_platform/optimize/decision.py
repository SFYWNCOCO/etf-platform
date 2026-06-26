"""optimize/decision.py — 决策分析与策略优化引擎

来源: etf_system/strategy_optimizer.py
分析历史ETF决策→自动优化参数→生成迭代报告。

依赖: data/etf_decisions_log.json (首次运行自动创建示例)
"""
import json, os, datetime
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"
DECISION_LOG = DATA_DIR / "etf_decisions_log.json"
OPTIMIZE_REPORT = DATA_DIR / "etf_optimization_report.json"

MODE_CONFIG = {
    "defensive":  {"label": "防御型", "score_weight": 0.60, "event_weight": 0.15, "fee_weight": 0.15, "risk_weight": 0.10},
    "balanced":   {"label": "平衡型", "score_weight": 0.40, "event_weight": 0.25, "fee_weight": 0.10, "risk_weight": 0.25},
    "aggressive": {"label": "进攻型", "score_weight": 0.25, "event_weight": 0.40, "fee_weight": 0.05, "risk_weight": 0.30},
}


def _init_sample_log():
    """如果日志不存在，创建示例数据"""
    if DECISION_LOG.exists():
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    sample = {
        "version": "1.0",
        "created": datetime.date.today().isoformat(),
        "transactions": [
            {"code":"159995","name":"芯片ETF","action":"buy","price":2.5,"amount":200,"total_cost":500,
             "time":"2026-03-15","reason":"国产替代+AI芯片需求爆发","sector":"半导体","mode":"aggressive"},
            {"code":"159995","name":"芯片ETF","action":"sell","price":3.1,"amount":200,"profit":120,"profit_pct":24.0,
             "time":"2026-06-10","hold_days":87,"sector":"半导体","mode":"aggressive"},
            {"code":"512890","name":"红利低波ETF","action":"buy","price":1.12,"amount":500,"total_cost":560,
             "time":"2026-01-10","reason":"低波动防守+高股息","sector":"红利/价值","mode":"defensive"},
            {"code":"512890","name":"红利低波ETF","action":"sell","price":1.08,"amount":500,"profit":-20,"profit_pct":-3.6,
             "time":"2026-06-15","hold_days":156,"sector":"红利/价值","mode":"defensive"},
            {"code":"518880","name":"黄金ETF","action":"buy","price":7.8,"amount":100,"total_cost":780,
             "time":"2026-04-01","reason":"地缘避险+通胀对冲","sector":"黄金","mode":"balanced"},
        ],
        "pitfalls": [],
    }
    with open(DECISION_LOG, "w", encoding="utf-8") as f:
        json.dump(sample, f, ensure_ascii=False, indent=2)


def load_log():
    _init_sample_log()
    with open(DECISION_LOG, "r", encoding="utf-8") as f:
        return json.load(f)


def save_log(log):
    with open(DECISION_LOG, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def add_transaction(code, name, action, price, amount, reason="", sector="", mode="balanced"):
    """记录一笔交易"""
    log = load_log()
    txn = {
        "code": code, "name": name, "action": action,
        "price": price, "amount": amount,
        "total_cost": round(price * amount, 2),
        "time": datetime.datetime.now().isoformat()[:19],
        "reason": reason, "sector": sector, "mode": mode,
    }
    log.setdefault("transactions", []).append(txn)
    save_log(log)
    return txn


def _get_buys_and_sells(txns):
    buys = [t for t in txns if t.get("action")=="buy"]
    sells = [t for t in txns if t.get("action")=="sell"]
    return buys, sells


def analyze():
    """运行完整的决策分析"""
    log = load_log()
    txns = log.get("transactions", [])
    if not txns:
        return {"error": "no transactions"}
    
    buys, sells = _get_buys_and_sells(txns)
    
    result = {"total": len(txns), "buys": len(buys), "sells": len(sells)}
    
    if sells:
        wins = sum(1 for t in sells if t.get("profit",0) > 0)
        total_pnl = sum(t.get("profit",0) for t in sells)
        result["win_rate"] = round(wins/len(sells)*100, 1)
        result["win_count"] = wins
        result["total_pnl"] = round(total_pnl, 2)
        result["avg_pnl"] = round(total_pnl/len(sells), 2)
        
        profits = [t.get("profit_pct",0) for t in sells]
        result["max_profit_pct"] = round(max(profits), 2) if profits else 0
        result["max_loss_pct"] = round(min(profits), 2) if profits else 0
        
        # By sector
        sec_stats = {}
        for t in sells:
            sec = t.get("sector","未知")
            s = sec_stats.setdefault(sec, {"total":0,"win":0,"pnl":0})
            s["total"] += 1
            if t.get("profit",0) > 0: s["win"] += 1
            s["pnl"] += t.get("profit",0)
        result["by_sector"] = {k:{"win_rate":round(v["win"]/v["total"]*100,1) if v["total"]>0 else 0,
                                  "pnl":round(v["pnl"],2),"count":v["total"]}
                               for k,v in sorted(sec_stats.items(),
                                  key=lambda x: x[1]["win"]/max(x[1]["total"],1), reverse=True)}
        
        # By mode
        mode_stats = {}
        for t in sells:
            m = t.get("mode","未标记")
            ms = mode_stats.setdefault(m, {"total":0,"win":0,"pnl":0})
            ms["total"] += 1
            if t.get("profit",0) > 0: ms["win"] += 1
            ms["pnl"] += t.get("profit",0)
        result["by_mode"] = {k:{"win_rate":round(v["win"]/v["total"]*100,1),"pnl":round(v["pnl"],2)}
                             for k,v in sorted(mode_stats.items(),
                                key=lambda x: x[1]["win"]/max(x[1]["total"],1), reverse=True)}
        
        # Holdings analysis
        hold_days = [t.get("hold_days",0) for t in sells if t.get("hold_days",0) > 0]
        if hold_days:
            result["avg_hold_days"] = round(sum(hold_days)/len(hold_days), 1)
            short_pnl = [t.get("profit_pct",0) for t in sells if t.get("hold_days",0) and t["hold_days"] <= 30]
            med_pnl   = [t.get("profit_pct",0) for t in sells if t.get("hold_days",0) and 30 < t["hold_days"] <= 90]
            long_pnl  = [t.get("profit_pct",0) for t in sells if t.get("hold_days",0) and t["hold_days"] > 90]
            if short_pnl: result["short_term_avg"] = round(sum(short_pnl)/len(short_pnl), 2)
            if med_pnl: result["medium_term_avg"] = round(sum(med_pnl)/len(med_pnl), 2)
            if long_pnl: result["long_term_avg"] = round(sum(long_pnl)/len(long_pnl), 2)
    
    # Add pitfalls
    result["pitfalls"] = log.get("pitfalls", [])
    return result


def add_pitfall(description, lesson):
    """记录一个投资教训"""
    log = load_log()
    log.setdefault("pitfalls", []).append({
        "description": description, "lesson": lesson,
        "date": datetime.date.today().isoformat(),
    })
    save_log(log)


def print_report():
    """打印分析报告"""
    r = analyze()
    if "error" in r:
        print("  No transaction data yet.")
        print('  Use: decision.add_transaction() to record trades')
        return
    
    print("")
    print("  [策略决策分析]")
    print("  %s" % ("="*50))
    print("  总交易: %d (买入%d 卖出%d)" % (r["total"], r["buys"], r["sells"]))
    
    if "win_rate" in r:
        wr = r["win_rate"]
        icon = "\U0001f7e2" if wr >= 60 else ("\U0001fe00" if wr >= 40 else "\U0001f534")
        print("  胜率: %s %.1f%% (%d/%d)" % (icon, wr, r["win_count"], r["sells"]))
        print("  总盈亏: %+.2f | 均笔: %+.2f" % (r["total_pnl"], r["avg_pnl"]))
        print("  最大盈利: %+.2f%% | 最大亏损: %.2f%%" % (r["max_profit_pct"], r["max_loss_pct"]))
        if "avg_hold_days" in r:
            print("  平均持有: %.1f天" % r["avg_hold_days"])
            if "short_term_avg" in r:
                print("  短期(<=30d): %+.2f%%  中期(31-90d): %+.2f%%  长期(>90d): %+.2f%%" % (
                    r.get("short_term_avg",0), r.get("medium_term_avg",0), r.get("long_term_avg",0)))
    
    if "by_sector" in r:
        print("\n  按板块胜率:")
        print("  %-14s %-10s %-10s" % ("板块", "胜率", "盈亏"))
        print("  %s" % ("-"*40))
        for sec, s in r["by_sector"].items():
            ic = "\U0001f7e2" if s["win_rate"] >= 60 else ("\U0001fe00" if s["win_rate"] >= 40 else "\U0001f534")
            print("  %s %-12s %s%.1f%%  %+.1f" % (ic, sec[:12], "", s["win_rate"], s["pnl"]))
    
    if "by_mode" in r:
        print("\n  按模式胜率:")
        for mode, s in r["by_mode"].items():
            ic = "\U0001f7e2" if s["win_rate"] >= 60 else ("\U0001fe00" if s["win_rate"] >= 40 else "\U0001f534")
            print("  %s %s: %.1f%% (%+.1f)" % (ic, mode, s["win_rate"], s["pnl"]))
    
    if r.get("pitfalls"):
        print("\n  经验教训:")
        for p in r["pitfalls"]:
            print("  \U0001f4dd %s → %s" % (p["description"][:30], p["lesson"][:40]))
    print("")


if __name__ == "__main__":
    print_report()