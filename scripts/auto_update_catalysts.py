# -*- coding: utf-8 -*-
"""催化状态日更脚本 — 每日收盘后自动把"已兑现催化"标为 triggered

逻辑（对应投资经验第一课：催化已兑现=追高危险）：
1. 读 catalyst_status.json 当前 pending 催化
2. 检查每条催化的时间窗口是否已过（catalyst_window 在今日之前 = 事件已发生）
3. 时间窗口已过 → mark_triggered（自动降权）
4. 输出变更报告

用法: python auto_update_catalysts.py [--dry-run]
"""
import sys, os, io, json, datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # etf-platform/
sys.path.insert(0, os.path.join(BASE, "scripts"))
from catalyst_status import load_status, save_status, mark_triggered

def parse_window_start(window: str):
    """解析催化窗口起始日期（如 '2026-09' → 2026-09-01；'2026-09-07~10' → 2026-09-07）。"""
    if not window:
        return None
    w = str(window).strip()
    # 取区间起点 (YYYY-MM 或 YYYY-MM-DD)
    m = w.split('~')[0].split('-')
    try:
        if len(m) >= 3:
            return datetime.date(int(m[0]), int(m[1]), int(m[2]))
        if len(m) == 2:
            return datetime.date(int(m[0]), int(m[1]), 1)
        if len(m) == 1:
            return datetime.date(int(m[0]), 1, 1)
    except Exception:
        return None
    return None


def parse_window_end(window: str):
    """解析催化窗口结束日期：~ 后的部分（如 '2026-08~10' → 2026-10-28；'2026-09-07~10' → 2026-09-10）。无~则取起点。"""
    if not window:
        return None
    w = str(window).strip()
    if '~' not in w:
        return parse_window_start(w)
    head = w.split('~')[0].strip()
    tail = w.split('~')[1].strip()
    head_parts = head.split('-')
    tail_parts = tail.split('-')
    try:
        if len(tail_parts) >= 3:
            return datetime.date(int(tail_parts[0]), int(tail_parts[1]), int(tail_parts[2]))
        if len(tail_parts) == 2:
            return datetime.date(int(tail_parts[0]), int(tail_parts[1]), 28)
        if len(tail_parts) == 1:
            # 单段继承前缀：'2026-08~10' → year=2026, month=10；'2026-09-07~10' → 日区间
            if len(head_parts) >= 3:
                return datetime.date(int(head_parts[0]), int(head_parts[1]), int(tail_parts[0]))
            if len(head_parts) == 2:
                return datetime.date(int(head_parts[0]), int(tail_parts[0]), 28)
            if len(head_parts) == 1:
                return datetime.date(int(tail_parts[0]), 12, 31)
    except Exception:
        return None
    return None


def main():
    dry = "--dry-run" in sys.argv
    today = datetime.date.today()
    st = load_status()
    triggered = []
    in_progress = []
    for sector, sec in st.get("sectors", {}).items():
        if sec.get("status") != "pending":
            continue
        for c in sec.get("catalysts", []):
            window = c.get("window", "")
            wstart = parse_window_start(window)
            wend = parse_window_end(window)
            if not wstart:
                continue
            if wstart < today:
                if wend and wend >= today:
                    # 窗口进行中（如 8~10月跨度）→ in-progress，保留加分但标记
                    in_progress.append((sector, c.get("name"), str(window)))
                else:
                    # 窗口已完全结束 → 催化已兑现，降权
                    triggered.append((sector, c.get("name"), str(window)))
                    if not dry:
                        mark_triggered(sector, c.get("name"))
    print(f"[催化状态日更] {today} | {'DRY-RUN' if dry else '执行'}")
    print(f"  已兑现(triggered): {len(triggered)} 条")
    for sector, name, window in triggered:
        print(f"     {sector} / {name} — 窗口 {window} 已结束 → triggered")
    print(f"  进行中(in-progress): {len(in_progress)} 条（保留加分，仅标记）")
    for sector, name, window in in_progress:
        print(f"     {sector} / {name} — 窗口 {window} 进行中")
    secs = st.get("sectors", {})
    pending = sum(1 for s in secs.values() if s.get("status") == "pending")
    trig = sum(1 for s in secs.values() if s.get("status") in ("triggered", "partial"))
    print(f"  当前状态: pending={pending} triggered/partial={trig}")

if __name__ == "__main__":
    main()