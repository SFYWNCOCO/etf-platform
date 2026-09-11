# -*- coding: utf-8 -*-
"""催化状态统一数据源（#2 催化状态自动化）

- 数据文件: data/catalyst_status.json  ← 唯一事实源（不再代码硬编码 status）
- 读接口:   get_catalyst_status(sector) / get_sector_boost(sector)
- 更新接口: mark_triggered(sector, catalyst_name) / update_from_scan(...)
- weekly_top3 + L34 均从此读取，不再各自硬编码
- 每日复盘cron脚本可调用 mark_triggered 把已兑现催化标为 triggered
"""
import json
import os
import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # repo根（etf-platform/）
STATUS_FILE = os.path.join(BASE, "data", "catalyst_status.json")
THEME_FILE = os.path.join(BASE, "data", "theme_catalog.json")

# 板块别名 → 标准板块（与theme_catalog cluster保持一致）
MEGA_ALIASES = {
    "科技": "AI/科技", "AI": "AI/科技", "AI算力": "AI/科技",
    "半导体": "半导体", "芯片": "半导体", "电子": "半导体",
    "医药": "医药", "医疗": "医药", "创新药": "医药",
    "新能源": "新能源", "光伏": "新能源", "锂电": "新能源",
    "军工": "军工", "国防": "军工", "商业航天": "低空/商业航天",
    "低空经济": "低空/商业航天", "卫星互联网": "低空/商业航天",
    "农业": "农业/粮食", "粮食": "农业/粮食", "养殖": "农业/粮食", "农牧": "农业/粮食",
    "消费": "消费", "白酒": "消费", "家电": "消费", "汽车": "消费",
    "机器人": "机器人", "人形机器人": "机器人",
    "消费电子": "消费电子", "华为": "消费电子",
    "通信/5G": "通信", "通信": "通信", "5G": "通信", "光模块": "通信",
    "周期/资源": "资源/周期", "周期": "资源/周期", "有色": "资源/周期", "黄金": "资源/周期",
    "基建": "基建/地产", "地产": "基建/地产",
    "金融": "金融", "券商": "金融", "银行": "金融",
    "红利/价值": "红利/价值", "红利": "红利/价值", "红利价值": "红利/价值",
    "公用事业": "公用事业", "电力": "公用事业",
    "高端制造": "高端制造", "机械": "高端制造",
    "物流": "物流/交运", "交运": "物流/交运",
    "跨境": "跨境/港股", "港股": "跨境/港股", "中概": "跨境/港股",
    "其他": "其他",
}


def _default_status():
    """初始状态：从 theme_catalog 生成（无催化=中性；有催化=pending）。"""
    return {
        "_meta": {
            "generated": datetime.date.today().isoformat(),
            "note": "催化状态事实源。由 weekly_top3 催化过滤层 + 每日复盘 cron 更新。",
        },
        "sectors": {},
    }


def load_status():
    """加载状态文件，不存在则初始化。"""
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    st = _default_status()
    save_status(st)
    return st


def save_status(st):
    os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)


def normalize_sector(sector: str) -> str:
    """sector → 标准催化板块名。"""
    if not sector:
        return "unknown"
    if sector in MEGA_ALIASES:
        return MEGA_ALIASES[sector]
    return sector


def get_sector_boost(sector: str) -> dict:
    """返回板块催化调整: {boost: float, status: str, catalysts: list, triggered: list}"""
    norm = normalize_sector(sector)
    st = load_status()
    sec = st.get("sectors", {}).get(norm, {})
    boost = sec.get("boost", 0.0)
    status = sec.get("status", "neutral")
    return {
        "boost": boost,
        "status": status,
        "catalysts": sec.get("catalysts", []),
        "triggered": sec.get("triggered", []),
        "events": sec.get("events", []),
    }


def update_sector(sector: str, boost: float, status: str, catalysts: list = None, events: list = None, triggered: list = None):
    """更新板块催化状态。"""
    norm = normalize_sector(sector)
    st = load_status()
    st.setdefault("sectors", {})
    st["sectors"][norm] = {
        "boost": round(float(boost), 2),
        "status": status,
        "catalysts": catalysts or [],
        "events": events or [],
        "triggered": triggered or [],
        "updated": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    save_status(st)


def mark_triggered(sector: str, catalyst_name: str):
    """催化已兑现 → 从 catalysts 移到 triggered，并降低 boost。

    调用时机: 每日复盘 cron 检测到"催化事件已发生"。
    对应规则: 催化已兑现=追高危险（investment_learnings 第一课）。
    """
    norm = normalize_sector(sector)
    st = load_status()
    sec = st.setdefault("sectors", {}).setdefault(norm, {})
    cats = sec.get("catalysts", [])
    trig = sec.get("triggered", [])
    removed = []
    for c in list(cats):
        if isinstance(c, dict) and c.get("name") == catalyst_name:
            cats.remove(c)
            trig.append(c)
            removed.append(c)
        elif isinstance(c, str) and c == catalyst_name:
            cats.remove(c)
            trig.append({"name": c, "status": "triggered"})
            removed.append(c)
    # 降权：按剩余催化剂数重算 boost
    boost = sec.get("boost", 0.0)
    if removed:
        boost = max(0.0, boost - 1.0)  # 每次兑现事件降1.0，最低0
    sec["triggered"] = trig
    sec["boost"] = round(boost, 2)
    sec["status"] = "partial" if cats else ("neutral" if not trig else "triggered")
    sec["updated"] = datetime.datetime.now().isoformat(timespec="seconds")
    save_status(st)
    return len(removed)


# 从 theme_catalog 初始化（一次性，供脚本调用）
def init_from_theme_catalog():
    if not os.path.exists(THEME_FILE):
        return 0
    with open(THEME_FILE, encoding="utf-8") as f:
        tc = json.load(f)
    st = _default_status()
    count = 0
    for t in tc.get("topics", []):
        if t.get("status") == "scanned" and t.get("future_catalyst"):
            cluster = t.get("cluster") or "其他"
            # 聚合同簇的多条催化
            sec = st["sectors"].setdefault(cluster, {
                "boost": 0.0, "status": "pending",
                "catalysts": [], "events": [], "triggered": [],
            })
            if t["name"] not in [c["name"] for c in sec["catalysts"]]:
                sec["catalysts"].append({
                    "name": t["name"],
                    "catalyst": t["future_catalyst"],
                    "window": t.get("catalyst_window", ""),
                    "status": "pending",
                })
                count += 1
    # 按簇催化数设 boost：每条催化+0.7，上限2.0
    for sec in st["sectors"].values():
        n = len(sec["catalysts"])
        sec["boost"] = round(min(2.0, n * 0.7), 2)
        if n > 0:
            sec["status"] = "pending"
    save_status(st)
    return count


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--init":
        n = init_from_theme_catalog()
        print(f"已从 theme_catalog 初始化 {n} 条催化")
    else:
        print("用法: python catalyst_status.py --init （初始化）/ 作为模块import")