# -*- coding: utf-8 -*-
"""
每日投资复盘数据准备 — 读取当天 position_history.jsonl → 生成复盘上下文
供每日收盘 cron（agent模式）分析，产出 investment_learnings.md 条目
用法: python daily_review_prep.py
"""
import sys, os, json, io, datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # etf-platform/
HISTORY = os.path.join(BASE, "data", "position_history.jsonl")
LEARNINGS = os.path.join(BASE, "data", "investment_learnings.md")

def main():
    rows = []
    if os.path.exists(HISTORY):
        with open(HISTORY, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        pass

    today = datetime.date.today().isoformat()
    today_rows = [r for r in rows if r.get("ts", "").startswith(today)]
    if not today_rows:
        # 无当天数据则取全部
        today_rows = rows

    print("=== 今日持仓轨迹 ===")
    for r in today_rows:
        print(f"--- {r['ts']} ---")
        for it in r.get("items", []):
            print(f"  {it['name']}: {it['price']} ({it['pct']:+.2f}%) 浮盈{it['pnl']:+.2f}元 | 量{it.get('vol',0)/1e4:.1f}万手 位置{it.get('stage','?')}% 催化{it.get('cat_days','?')}天")

    # 当天第一帧 vs 最后一帧差异
    if len(today_rows) >= 2:
        first, last = today_rows[0], today_rows[-1]
        print("\n=== 首尾差异 ===")
        for fi in first.get("items", []):
            for li in last.get("items", []):
                if fi["code"] == li["code"]:
                    delta = (li["price"] - fi["price"]) / fi["price"] * 100 if fi["price"] else 0
                    print(f"  {li['name']}: {fi['price']} → {li['price']} ({delta:+.2f}%) 浮盈{fi['pnl']:+.2f}→{li['pnl']:+.2f}元")

    # 历史经验（供LLM记得过去判断）
    if os.path.exists(LEARNINGS):
        print("\n=== 已有经验库 ===")
        with open(LEARNINGS, encoding="utf-8") as f:
            content = f.read()
        # 提取最近3条经验标题+规则
        import re
        entries = re.findall(r"### (.*?)\n(.*?)(?=\n### |\Z)", content, re.S)
        for title, body in entries[-3:]:
            rule = re.search(r"- \*\*规则\*\*: (.*)", body)
            print(f"  【{title.split('—')[0].strip()}】规则: {rule.group(1) if rule else 'N/A'}")

if __name__ == "__main__":
    main()