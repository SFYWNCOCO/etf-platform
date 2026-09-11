# -*- coding: utf-8 -*-
"""
持仓小时监控 v2.1 — 四只ETF（159050/159063/159992/562950）
每小时抓行情 → 计算差异 → 采集学习信号（量能/阶段位置/催化倒计时）→ 写历史JSONL → 告警
学习闭环：快照字段供复盘脚本/LLM读取，沉淀 investment_learnings.md
用法: python position_monitor.py [--once]  （--once 单次不写历史）
v2.1: DNS重试（开盘时段腾讯接口容易抖动）
"""
import sys, os, json, time, io, datetime

import urllib.request
import urllib.error
import socket

# ── 配置 ────────────────────────────────
POSITIONS = [
    {"code": "sz159050", "name": "机器人ETF", "cost": 0.867, "shares": 400},
    {"code": "sz159063", "name": "粮食ETF",   "cost": 1.083, "shares": 400},
    {"code": "sz159992", "name": "创新药ETF", "cost": 0.886, "shares": 200},
    {"code": "sh562950", "name": "消费电子ETF", "cost": 1.604, "shares": 300},
]

# 催化日历：code → (事件, 日期)  —— 用于倒计时信号
CATALYSTS = {
    "sz159050": ("特斯拉Cybercab发布会", "2026-09-03"),
    "sz159063": ("厄尔尼诺高峰启动", "2026-10-01"),
    "sz159992": ("新版基药目录实施", "2026-09-15"),
    "sh562950": ("华为9/7发布会", "2026-09-07"),
}

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # etf-platform/
HISTORY = os.path.join(BASE, "data", "position_history.jsonl")
ALERT_THRESHOLD = 3.0   # 单只单小时涨跌幅绝对值>3% → 告警
DAILY_MOVE = 5.0        # 相对昨收涨跌幅>5% → 告警

def fetch_quotes():
    """拉行情 + 成交量/成交额（腾讯接口 f36=成交量手, f37=成交额万）"""
    codes = [p["code"] for p in POSITIONS]
    url = "https://qt.gtimg.cn/q=" + ",".join(codes)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com"})
    # DNS重试：开盘时段网络抖动容易fail，最多重试3次
    last_err = None
    for _attempt in range(3):
        try:
            resp = urllib.request.urlopen(req, timeout=10)
            break
        except (socket.gaierror, socket.timeout, urllib.error.URLError) as e:
            last_err = e
            continue
    else:
        raise last_err or RuntimeError("fetch_quotes failed after 3 attempts")
    raw = resp.read().decode("gbk")
    quotes = {}
    for line in raw.strip().split(";"):
        line = line.strip()
        if not line or "=" not in line:
            continue
        code = line.split("=")[0].split("_")[-1]
        body = line.split('="')[1].rstrip('"')
        f = body.split("~")
        if len(f) < 40:
            continue
        quotes[code] = {
            "name": f[1], "price": float(f[3]), "prev": float(f[4]),
            "pct": float(f[32]), "ts": f[30] if len(f) > 30 else "",
            "vol": float(f[36]) if len(f) > 36 and f[36] else 0,   # 成交量(手)
            "amount": float(f[37]) if len(f) > 37 and f[37] else 0, # 成交额(万)
            "high": float(f[33]) if len(f) > 33 and f[33] else 0,
            "low": float(f[34]) if len(f) > 34 and f[34] else 0,
        }
    return quotes

def catalyst_days_left(code):
    """催化倒计时（天），已过返回负值"""
    c = CATALYSTS.get(code)
    if not c:
        return None
    try:
        d = datetime.datetime.strptime(c[1], "%Y-%m-%d").date()
        today = datetime.date.today()
        return (d - today).days
    except Exception:
        return None

def stage_position(price, high, low, prev):
    """阶段位置：当日振幅内相对位置 0-100"""
    rng = (high - low) if (high and low and high > low) else 0
    if not rng:
        return None
    return round((price - low) / rng * 100, 1)

def load_history():
    if not os.path.exists(HISTORY):
        return []
    rows = []
    with open(HISTORY, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    return rows

def append_history(entry):
    os.makedirs(os.path.dirname(HISTORY), exist_ok=True)
    with open(HISTORY, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

def format_alerts(alerts):
    """告警行格式化（2026-09-12 修复：reasons 是 list，旧版直接 join 崩 TypeError）"""
    return "、".join(f"{a['name']}:{';'.join(a['reasons'])}" for a in alerts)

def main():
    once = "--once" in sys.argv
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # A股周末休市：周六/周日直接静默退出（cron 每小时跑无意义）
    wd = datetime.datetime.now().weekday()
    if wd >= 5:
        print(f"[持仓监控] {now} | 周末休市, 跳过 (weekday={wd})")
        return 0

    quotes = fetch_quotes()
    history = load_history()
    last = history[-1] if history else None

    # 组装当次快照
    snapshot = {"ts": now, "items": []}
    alerts = []
    for p in POSITIONS:
        q = quotes.get(p["code"], {})
        price = q.get("price", 0)
        pct = q.get("pct", 0)
        cost = p["cost"]
        shares = p["shares"]
        pnl = (price - cost) * shares
        pnl_pct = (price / cost - 1) * 100 if cost else 0

        # 与上次的差异
        diff_price = 0.0
        diff_pct = 0.0
        if last:
            for li in last.get("items", []):
                if li.get("code") == p["code"]:
                    diff_price = price - li.get("price", price)
                    diff_pct = (price / li.get("price", price) - 1) * 100 if li.get("price") else 0
                    break

        # 告警规则：单小时>3% 或 相对昨收>5%
        reason = []
        if abs(diff_pct) > ALERT_THRESHOLD:
            reason.append(f"小时异动{diff_pct:+.2f}%")
        if abs(pct) > DAILY_MOVE:
            reason.append(f"日内异动{pct:+.2f}%")

        item = {
            "code": p["code"], "name": p["name"], "price": price, "pct": pct,
            "cost": cost, "shares": shares, "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2), "diff_price": round(diff_price, 3),
            "diff_pct": round(diff_pct, 2), "prev": q.get("prev", 0),
            # 学习信号
            "vol": q.get("vol", 0), "amount": q.get("amount", 0),
            "stage": stage_position(price, q.get("high", 0), q.get("low", 0), q.get("prev", 0)),
            "cat_days": catalyst_days_left(p["code"]),
            "cat_event": (CATALYSTS.get(p["code"]) or ("", ""))[0],
        }
        snapshot["items"].append(item)
        if reason:
            alerts.append({"name": p["name"], "code": p["code"], "price": price, "reasons": reason})

    if not once:
        append_history(snapshot)

    # 输出（精简版，避免飞书消息截断）
    total_pnl = sum(i["pnl"] for i in snapshot["items"])
    total_cost = sum(i["cost"] * i["shares"] for i in snapshot["items"])
    total_pnl_pct = round(total_pnl / total_cost * 100, 2) if total_cost else 0
    lines = [f"[持仓监控] {now} | vol信号"]
    lines.append(f"  总市值:{sum(i['price']*i['shares'] for i in snapshot['items']):.1f} 成本:{total_cost:.1f} 盈亏:{total_pnl:+.1f}({total_pnl_pct:+.1f}%)")
    for it in snapshot["items"]:
        diff = f" vs{it['diff_price']:+.3f}" if last else ""
        cat = f"⏳{it.get('cat_days')}d" if it.get('cat_days') is not None else ""
        lines.append(f"  {it['code']}: {it['price']:.3f}({it['pct']:+.2f}%) PnL:{it['pnl']:+.1f}{diff} {cat}{it['cat_event'][:4]}")
    if alerts:
        lines.append("")
        lines.append("[警告] " + format_alerts(alerts))
        sys.exit(2)
    lines.append("\nOK 无异动")
    print("\n".join(lines))

if __name__ == "__main__":
    # 仅在直接执行时重包装 stdout（import 场景交给宿主，避免与 pytest 捕获冲突）
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    main()
