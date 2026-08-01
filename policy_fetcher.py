#!/usr/bin/env python3
"""policy_fetcher.py — 政策原文独立源（gov.cn 国务院最新政策）

打破三源同质化（新浪/东财/同花顺都是财经媒体），引入政策原文维度：
gov.cn 政策列表是 JS 渲染，requests 抓不到 → 用 Playwright 浏览器渲染提取。

输出 data/policy_signals.json（行业→政策方向），供 auto_sentiment 合并。

用法: python policy_fetcher.py [--stdout] [--browser]
  --browser 用 Playwright 渲染（默认，需 playwright chromium）
"""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
DATA = _HERE / "data"
OUT_FILE = DATA / "policy_signals.json"

# ── 行业 → 政策关键词 ──
POLICY_KEYWORDS = {
    "半导体": ["半导体", "芯片", "集成电路", "信创", "科技自立"],
    "AI算力": ["人工智能", "算力", "大模型", "数字经济", "数据要素", "东数西算"],
    "AI/科技": ["人工智能", "科技", "数字经济", "互联网", "软件", "知识产权", "科技创新",
                "数字政府", "数字化", "低空经济", "数据"],
    "医药": ["医药", "医疗", "医保", "创新药", "生物医药", "公共卫生", "中医药", "健康",
            "疾病预防", "老龄", "养老", "医养", "银发"],
    "新能源": ["新能源", "光伏", "风电", "储能", "充电桩", "新能源汽车", "双碳", "碳中和",
              "碳达峰", "美丽中国", "水体", "生态", "绿色转型", "绿色"],
    "消费": ["消费", "内需", "以旧换新", "消费品", "文旅", "餐饮", "旅游", "全民健身",
            "支付", "家政", "首发经济", "县域消费"],
    "金融": ["金融", "银行", "资本市场", "证券", "保险", "降准", "降息", "LPR", "货币政策",
            "支付服务", "外汇"],
    "军工": ["国防", "军工", "航天", "军队", "国防科技"],
    "有色金属": ["稀土", "有色金属", "矿产资源", "自然资源"],
    "能源化工": ["能源", "石油", "煤炭", "天然气", "化工", "电力", "碳达峰", "绿色转型"],
    "基建/地产": ["基建", "房地产", "保障房", "城中村", "水利", "交通", "新基建", "防汛",
                "水网", "工程", "建设"],
    "通信/5G": ["通信", "5G", "6G", "信息基础设施"],
    "农业": ["农业", "粮食", "乡村振兴", "种业", "农产品", "生猪", "防汛抗旱", "粮食安全"],
    "机器人/智造": ["机器人", "智能制造", "工业母机", "先进制造", "设备更新"],
    "汽车": ["汽车", "新能源汽车", "智能网联"],
    "环保": ["环保", "生态", "碳交易", "绿色", "美丽中国", "水体", "生物多样性", "污染防治"],
    "央企改革": ["国企", "央企", "国有资本", "现代企业制度", "民营经济"],
}

POS_WORDS = ["支持", "鼓励", "推动", "促进", "加大", "加快", "扩大", "补贴", "减免", "扶持", "利好", "增长", "培育", "壮大", "保障"]
NEG_WORDS = ["限制", "禁止", "整治", "查处", "严格", "规范", "收紧", "压缩", "处罚", "降杠杆", "管控", "防范风险", "遏制"]


def fetch_policy_list() -> list:
    """用 Playwright 渲染 gov.cn 最新政策页，提取 (title, url)"""
    items = []
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("https://www.gov.cn/zhengce/zuixin/", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2500)
            entries = page.evaluate(
                "Array.from(document.querySelectorAll('h4 a')).map(a => ({title: a.textContent.trim(), url: a.href}))"
            )
            browser.close()
            for e in entries:
                if e.get("title"):
                    items.append({"title": e["title"], "url": e.get("url", ""), "source": "gov.cn"})
    except Exception as ex:
        print(f"[policy_fetcher] Playwright 失败: {ex}", file=sys.stderr)
    return items


def match_policy_sector(title: str) -> list:
    hits = []
    for sec, kws in POLICY_KEYWORDS.items():
        if any(kw in title for kw in kws):
            hits.append(sec)
    return hits


def judge_policy_direction(title: str) -> tuple:
    pos = sum(1 for w in POS_WORDS if w in title)
    neg = sum(1 for w in NEG_WORDS if w in title)
    # 政策文件标题本身（印发/规划/批复/通知）不代表方向——
    # 只有明确的产业支持/鼓励词才利好。修正：去掉一律+1
    # FIX 2026-08-01: 规划/方案/意见类公文即使无 POS 词，也隐含"推进该产业"方向
    # （国务院专门为某行业发规划 = 产业地位确认）。给 weak 利好 +0.5，
    # 但"整治/限制/规范"类强监管文件保持利空。
    if pos > neg:
        return "看多", pos - neg
    elif neg > pos:
        return "看空", neg - pos
    # 中性词库无方向词时：规划/方案/意见 = 弱利好（产业被国家提上议程）
    if any(w in title for w in ["规划", "方案", "意见", "行动方案", "纲要", "批复", "通知"]):
        return "看多", 0.5
    return "中性", 0


def main():
    items = fetch_policy_list()
    if not items:
        print("[policy_fetcher] 无政策数据（Playwright 不可用？）", file=sys.stderr)
        return 1

    from collections import defaultdict
    agg = defaultdict(lambda: {"bullish": 0, "bearish": 0, "items": []})
    for it in items:
        sectors = match_policy_sector(it["title"])
        direction, score = judge_policy_direction(it["title"])
        for sec in sectors:
            a = agg[sec]
            if direction == "看多":
                a["bullish"] += score
            elif direction == "看空":
                a["bearish"] += score
            a["items"].append(it["title"])

    sectors_out = {}
    for sec, a in agg.items():
        total = a["bullish"] + a["bearish"]
        if total == 0:
            continue
        net = a["bullish"] - a["bearish"]
        # FIX 2026-08-01: threshold net>=2 dropped single positive policies
        # (net=1) → only 1 sector matched. net>=1 keeps any directional policy.
        if net >= 1:
            direction, strength = "看多", ("强" if net >= 4 else ("中" if net >= 2 else "弱"))
        elif net <= -1:
            direction, strength = "看空", ("强" if net <= -4 else ("中" if net <= -2 else "弱"))
        else:
            direction, strength = "中性", "弱"
        sectors_out[sec] = {
            "direction": direction,
            "strength": strength,
            "note": f"政策{len(a['items'])}条(利好{a['bullish']}/利空{a['bearish']}) | 例: {a['items'][0][:50]}",
        }

    out = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        "source": f"gov.cn政策: {len(items)}条",
        "sectors": sectors_out,
        "total_policies": len(items),
    }
    DATA.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[policy_fetcher] 写入 {OUT_FILE}")
    print(f"  政策总数: {len(items)} | 匹配行业: {len(sectors_out)}")
    if "--stdout" in sys.argv:
        for sec, v in sectors_out.items():
            print(f"  {sec:10s} {v['direction']}/{v['strength']} {v['note'][:60]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
