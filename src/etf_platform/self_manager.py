"""self_manager.py — 循环学习管理系统

把我自己的学习过程变成PDCA+OODA闭环:
  P(Plan):   学习待办 + 排程 → learning_backlog.json  
  D(Do):     delegate_task 子 agent 执行学习
  C(Check): 复盘 → 对比之前的知识边界
  A(Act):   固化到 memory + skill + cron schedule

数据存储在: ~/.hermes/profiles/longxia/scripts/self_manager/
"""
import json, os, datetime, time
from pathlib import Path

# ── 数据目录 ──
DATA_DIR = Path(__file__).resolve().parent / "self_manager_data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

BACKLOG_FILE = DATA_DIR / "learning_backlog.json"
HISTORY_FILE = DATA_DIR / "learning_history.json"
CYCLE_FILE   = DATA_DIR / "cycle_state.json"
MEMORY_FILE  = DATA_DIR / "knowledge_base.json"


# ═══════════════════════════════════════════════
# 1. Plan — 学习待办管理
# ═══════════════════════════════════════════════

DEFAULT_BACKLOG = {
    "version": "1.0",
    "items": [
        # 格式: {id, topic, priority, status, category, estimated_cycles, notes}
        {"id": "LRN-001", "topic": "ETF行业轮动策略回测验证", "priority": "high",
         "status": "pending", "category": "investment", "cycles": 3,
         "notes": "用rotation_detector跑历史数据验证动量策略有效性"},
        {"id": "LRN-002", "topic": "供应链断层概率模型(S1-S5)量化", "priority": "high",
         "status": "pending", "category": "investment", "cycles": 3,
         "notes": "给chain_analysis的连锁故障场景加概率权重和敏感度分析"},
        {"id": "LRN-003", "topic": "Python socket模块DLL冲突根因和永久修复", "priority": "medium",
         "status": "pending", "category": "infra", "cycles": 1,
         "notes": "fix_run.py是临时方案，需要深入理解C扩展加载机制"},
        {"id": "LRN-004", "topic": "Hermes Agent delegate_task背景模式最佳实践", "priority": "medium",
         "status": "pending", "category": "agent", "cycles": 2,
         "notes": "研究background notification + context_from + workdir的组合用法"},
        {"id": "LRN-005", "topic": "L10-L11需求层数据动态更新方案", "priority": "low",
         "status": "pending", "category": "investment", "cycles": 2,
         "notes": "当前demand.py是硬编码，需要接入真实社零/PMI数据源"},
    ],
}


def load_backlog():
    if BACKLOG_FILE.exists():
        with open(BACKLOG_FILE, "r") as f:
            return json.load(f)
    return DEFAULT_BACKLOG


def save_backlog(bl):
    with open(BACKLOG_FILE, "w") as f:
        json.dump(bl, f, ensure_ascii=False, indent=2)


def add_learning(topic, priority="medium", category="general", cycles=1, notes=""):
    """添加学习项到待办"""
    bl = load_backlog()
    next_id = len(bl["items"]) + 1
    item = {
        "id": f"LRN-{next_id:03d}",
        "topic": topic, "priority": priority,
        "status": "pending", "category": category,
        "cycles": cycles, "notes": notes,
        "created": datetime.date.today().isoformat(),
    }
    bl["items"].append(item)
    save_backlog(bl)
    return item


def get_next_learning():
    """获取最高优先级待学项"""
    bl = load_backlog()
    pending = [i for i in bl["items"] if i["status"] == "pending"]
    if not pending:
        return None
    priority_map = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    pending.sort(key=lambda x: (priority_map.get(x["priority"], 99), x.get("id", "")))
    return pending[0]


# ═══════════════════════════════════════════════
# 2. Cycle — 循环状态机
# ═══════════════════════════════════════════════

PHASES = ["plan", "do", "check", "act"]

def get_cycle_state():
    if CYCLE_FILE.exists():
        with open(CYCLE_FILE, "r") as f:
            return json.load(f)
    return {
        "current_phase": "plan",
        "cycle_count": 0,
        "current_learning": None,
        "last_cycle_time": None,
        "learning_history_ids": [],
    }


def save_cycle_state(state):
    with open(CYCLE_FILE, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def advance_cycle():
    """推进到下一个PDCA阶段"""
    state = get_cycle_state()
    current_idx = PHASES.index(state["current_phase"])
    next_idx = (current_idx + 1) % len(PHASES)
    state["current_phase"] = PHASES[next_idx]
    if next_idx == 0:  # Completed full cycle
        state["cycle_count"] += 1
        state["last_cycle_time"] = datetime.datetime.now().isoformat()
    save_cycle_state(state)
    return state["current_phase"]

# ═══════════════════════════════════════════════
# 3. Knowledge Base — 知识库(持久化)
# ═══════════════════════════════════════════════

def load_kb():
    if MEMORY_FILE.exists():
        with open(MEMORY_FILE, "r") as f:
            return json.load(f)
    return {"version": "1.0", "entries": [], "domains": {}}


def save_kb(kb):
    with open(MEMORY_FILE, "w") as f:
        json.dump(kb, f, ensure_ascii=False, indent=2)


def add_knowledge(domain, key_insight, details="", source=""):
    """记录学到的一个知识点"""
    kb = load_kb()
    entry = {
        "id": f"KNOW-{len(kb['entries'])+1:03d}",
        "domain": domain,
        "insight": key_insight,
        "details": details[:500],
        "source": source,
        "timestamp": datetime.datetime.now().isoformat(),
    }
    kb["entries"].append(entry)
    if domain not in kb["domains"]:
        kb["domains"][domain] = {"count": 0, "last_updated": None}
    kb["domains"][domain]["count"] += 1
    kb["domains"][domain]["last_updated"] = entry["timestamp"]
    save_kb(kb)
    return entry


# ═══════════════════════════════════════════════
# 4. Learning Cycle Runner
# ═══════════════════════════════════════════════

def run_cycle():
    """执行一个完整的PDCA学习循环"""
    state = get_cycle_state()
    phase = state["current_phase"]
    print(f"[self-manager] Phase: {phase.upper()} (Cycle {state['cycle_count']+1})")
    
    if phase == "plan":
        item = get_next_learning()
        if item:
            state["current_learning"] = item["id"]
            print(f"  Next: [{item['priority']}] {item['topic']}")
            print(f"  Type: {item['category']} | Est: {item['cycles']} cycles")
        else:
            print("  No pending learning items.")
        save_cycle_state(state)
        advance_cycle()
        return {"phase": "plan", "item": item}
    
    elif phase == "do":
        item_id = state["current_learning"]
        bl = load_backlog()
        item = next((i for i in bl["items"] if i["id"] == item_id), None)
        if item:
            print(f"  Executing: {item['topic']}")
            print(f"  Action: delegate_task to study this topic")
            print(f"  Context: {item['notes']}")
            item["status"] = "in_progress"
            save_backlog(bl)
        else:
            print(f"  No item {item_id} found")
        save_cycle_state(state)
        advance_cycle()
        return {"phase": "do", "item": item}
    
    elif phase == "check":
        item_id = state["current_learning"]
        print(f"  Reviewing: {item_id}")
        print(f"  Questions:")
        print(f"    1. What did I learn that I didn't know before?")
        print(f"    2. Does this change my understanding of other domains?")
        print(f"    3. Is this knowledge durable or situational?")
        print(f"    4. What should I do differently now?")
        save_cycle_state(state)
        advance_cycle()
        return {"phase": "check"}
    
    elif phase == "act":
        item_id = state["current_learning"]
        bl = load_backlog()
        item = next((i for i in bl["items"] if i["id"] == item_id), None)
        if item:
            print(f"  Solidifying: {item['topic']}")
            print(f"  Actions:")
            print(f"    1. Add key insight to memory (durable facts)")
            print(f"    2. Update or create skill if workflow")
            print(f"    3. Record in knowledge_base.json")
            item["status"] = "completed"
            item["completed_at"] = datetime.datetime.now().isoformat()
            save_backlog(bl)
            state["learning_history_ids"].append(item_id)
        save_cycle_state(state)
        advance_cycle()
        return {"phase": "act", "item": item}


def status_report():
    """生成学习管理系统状态报告"""
    bl = load_backlog()
    state = get_cycle_state()
    kb = load_kb()
    
    pending = [i for i in bl["items"] if i["status"] == "pending"]
    in_progress = [i for i in bl["items"] if i["status"] == "in_progress"]
    completed = [i for i in bl["items"] if i["status"] == "completed"]
    
    lines = []
    lines.append("")
    lines.append("  [self-manager] 循环学习系统状态")
    lines.append("  %s" % ("="*50))
    lines.append("  PDCA Phase: %s | Cycle: %d" % (state["current_phase"].upper(), state["cycle_count"]))
    lines.append("  待学: %d | 进行中: %d | 已完成: %d" % (len(pending), len(in_progress), len(completed)))
    lines.append("  知识条目: %d | 领域: %s" % (len(kb["entries"]), ", ".join(kb["domains"].keys()) if kb["domains"] else "空"))
    
    if pending:
        lines.append("")
        lines.append("  待学清单:")
        priority_map = {"critical": "\U0001f534", "high": "\U0001fe00", "medium": "\u26aa", "low": "\U0001f7e2"}
        for item in sorted(pending, key=lambda x: {"critical":0,"high":1,"medium":2,"low":3}.get(x["priority"],99)):
            lines.append("  %s [%s] %s" % (priority_map.get(item["priority"], "?"), item["id"], item["topic"]))
    
    if state["current_learning"]:
        lines.append("")
        lines.append("  当前学习: %s" % state["current_learning"])
    
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "status":
            print(status_report())
        elif cmd == "cycle":
            run_cycle()
        elif cmd == "add":
            topic = " ".join(sys.argv[2:])
            if topic:
                add_learning(topic)
                print(f"  Added: {topic}")
            else:
                print("  Usage: self_manager.py add <topic>")
        elif cmd == "kb":
            kb = load_kb()
            for e in kb["entries"]:
                print(f"  [{e['domain']}] {e['insight'][:80]}")
    else:
        print(status_report())