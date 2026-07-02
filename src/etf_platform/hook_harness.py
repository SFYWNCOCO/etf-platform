"""hook_harness.py — ETF Platform → Harness Loop bridge.

每次 ETF 分析完成后将结果注入 Hermes 改进循环:
  1. corrections.md  — 如果发现系统性问题
  2. framework_registry.json — Thompson 框架 wins/losses 更新
  3. feedback_anchor.jsonl — 信号蒸馏 (Signal→Distill→Update)

用法:
  python -m etf_platform.hook_harness patrol   # 巡逻后自动回调
  python -m etf_platform.hook_harness backtest # 回测后评估
"""

import json, os, re, sys
from datetime import datetime
from pathlib import Path

OPENCLAW = Path(__file__).resolve().parent.parent.parent.parent
CORRECTIONS = OPENCLAW / "corrections.md"
FW_REG = OPENCLAW / "framework_registry.json"
FEEDBACK = OPENCLAW / "feedback_anchor.jsonl"
HARNESS_LOG = OPENCLAW / "etf-platform" / "data" / "harness_events.jsonl"


def load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.loads(f.read().lstrip("\ufeff"))
        except:
            return default if default is not None else {}


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def record_event(event_type, payload):
    os.makedirs(str(HARNESS_LOG.parent), exist_ok=True)
    entry = {"ts": datetime.now().isoformat(), "type": event_type, **payload}
    with open(HARNESS_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def update_thompson_frameworks(framework_name, wins_delta=0, losses_delta=0):
    fw = load_json(FW_REG, {})
    frameworks = fw.get("frameworks", {})

    if framework_name not in frameworks:
        frameworks[framework_name] = {"wins": 0, "losses": 0, "alpha": 1, "beta": 1, "scope": "etf"}

    f = frameworks[framework_name]
    f["wins"] = f.get("wins", 0) + wins_delta
    f["losses"] = f.get("losses", 0) + losses_delta
    f["alpha"] = f["wins"] + 1
    f["beta"] = f["losses"] + 1
    f["win_rate"] = round(f["alpha"] / (f["alpha"] + f["beta"]), 3) if (f["alpha"] + f["beta"]) > 0 else 0.5
    f["updated"] = datetime.now().isoformat()

    fw["frameworks"] = frameworks
    fw["updated"] = datetime.now().isoformat()
    fw["etf_hook_last_run"] = datetime.now().isoformat()
    save_json(FW_REG, fw)


def write_correction(title, root_cause, fix, lesson):
    num = 1
    if CORRECTIONS.exists():
        text = CORRECTIONS.read_text(encoding="utf-8")
        nums = re.findall(r"#(\d+)", text)
        if nums:
            num = max(int(n) for n in nums) + 1

    entry = (
        f"\n## #{num} | {title} →active\n"
        f"**发现**: {datetime.now().strftime('%Y-%m-%d')} ETF平台自动检测\n"
        f"**现象**: {title}\n"
        f"**根因**: {root_cause}\n"
        f"**修复**: {fix}\n"
        f"**教训**: {lesson}\n"
    )

    with open(CORRECTIONS, "a", encoding="utf-8") as f:
        f.write(entry)

    return num


def append_feedback(signal_type, context, fw_names):
    entry = {
        "epoch": datetime.now().strftime("%Y%m"),
        "session": f"etf-auto-{datetime.now().strftime('%Y%m%d_%H%M')}",
        "ts": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "type": signal_type,
        "user_said": "[ETF平台自动信号]",
        "context": context,
        "frameworks": fw_names,
        "action": "win" if signal_type == "acceptance" else ("loss" if signal_type == "correction" else "observation"),
    }
    with open(FEEDBACK, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ═══════════════════════════════════════════
# Public hooks
# ═══════════════════════════════════════════

def hook_patrol(results):
    """Patrol后回调 — 评估推荐质量."""
    if not results:
        return

    top = results[0] if results else {}
    score = top.get("composite_score", 0)

    record_event("patrol_completed", {
        "top_etf": top.get("code", "?"),
        "top_score": score,
        "total_screened": len(results),
    })

    if score >= 8.0:
        update_thompson_frameworks("ETF筛选器", wins_delta=1)
        append_feedback("acceptance", f"ETF推荐 {top.get('code')} 得分 {score}", ["ETF筛选器", "11层穿透"])
    elif score <= 4.0:
        append_feedback("observation",
                        f"ETF市场信号疲弱: Top得分仅 {score}", ["市场机制", "系统机制"])


def hook_backtest(report):
    """回测后回调 — 评估策略表现."""
    accuracy = report.get("accuracy", 0)
    total = report.get("total", 0)

    record_event("backtest_completed", {
        "accuracy": accuracy,
        "total_trades": total,
        "priced_acc": report.get("priced_accuracy", 0),
        "unpriced_acc": report.get("unpriced_accuracy", 0),
    })

    if accuracy >= 60:
        update_thompson_frameworks("事件驱动策略", wins_delta=1)
        append_feedback("acceptance",
                        f"回测准确率 {accuracy}% ({total}笔交易)", ["事件驱动策略"])
    elif accuracy <= 40:
        update_thompson_frameworks("事件驱动策略", losses_delta=1)
        append_feedback("correction",
                        f"回测准确率仅 {accuracy}% — 需调整事件权重", ["事件驱动策略"])


def hook_anomaly(etf_code, issue_desc, severity="P1"):
    """异常检测回调."""
    record_event("anomaly_detected", {"code": etf_code, "issue": issue_desc, "severity": severity})

    num = write_correction(
        f"ETF {etf_code} {issue_desc[:30]}",
        f"ETF {etf_code}: {issue_desc}",
        "自动标记待修复",
        f"异常{severity}级，需人工审核"
    )
    update_thompson_frameworks("异常检测", losses_delta=1)
    return num


def hook_daily_summary():
    """每日摘要 — 写入 feedback_anchor."""
    from .decision.screener import screen
    from .decision.optimizer import load_decision_log

    try:
        results = screen(top_n=10, profile="均衡")
        decisions = load_decision_log()
        if isinstance(decisions, list) and decisions:
            recent = decisions[-20:]
            win_count = sum(1 for d in recent if isinstance(d, dict) and d.get("pnl_pct", 0) > 0)
            dec_text = f"{win_count}/{len(recent)}"
        else:
            win_count = 0
            dec_text = "0/0"

        if results:
            top = results[0]
            append_feedback("observation",
                            f"ETF每日Top: {top['code']}({top['composite_score']:.1f}) "
                            f"| 决策胜率: {dec_text}",
                            ["ETF筛选器", "事件驱动策略"])

    except Exception as e:
        record_event("hook_error", {"error": str(e)[:200]})


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "summary"

    if cmd == "patrol":
        from .decision.screener import screen
        results = screen(top_n=10, profile="均衡")
        hook_patrol(results)
        print(f"Hooked patrol: {len(results)} screened")

    elif cmd == "backtest":
        from .optimize.backtest import run_backtest
        report = run_backtest()
        hook_backtest(report)
        print(f"Hooked backtest: {report.get('accuracy')}% accuracy")

    elif cmd == "summary":
        hook_daily_summary()
        print("Hooked daily summary")

    elif cmd == "status":
        if HARNESS_LOG.exists():
            lines = HARNESS_LOG.read_text(encoding="utf-8").strip().split("\n")
            print(f"Harness events: {len(lines)} total")
            for l in lines[-5:]:
                e = json.loads(l)
                print(f"  {e['ts'][:19]} [{e['type']}]")
        else:
            print("No harness events yet")

    elif cmd == "verify":
        fw = load_json(FW_REG, {})
        etf_fws = {k: v for k, v in fw.get("frameworks", {}).items() if v.get("scope") == "etf"}
        print(f"ETF scoped frameworks: {len(etf_fws)}")
        for n, f in sorted(etf_fws.items()):
            w, l = f.get("wins", 0), f.get("losses", 0)
            wr = f.get("win_rate", 0)
            print(f"  {n}: wins={w} losses={l} wr={wr:.1%}")
