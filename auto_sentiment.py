#!/usr/bin/env python3
"""auto_sentiment.py — 从 news_raw_sources.json 自动生成 sector 级情绪信号。

替代 7月20日 手工 news_sentiment.json 的自动版本：
1. 读取 news_raw_sources.json（三源：sina/eastmoney/tonghuashun）
2. 每条新闻：关键词方向判定（利好/利空/中性）+ sector 匹配
3. 聚合 sector 级 sentiment → 写 news_sentiment.json
4. 方向阈值对称：只有净倾向显著才判看多/看空，否则中性

用法: python auto_sentiment.py [--stdout]
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent  # etf-platform/
DATA = _HERE / "data"
RAW_FILE = DATA / "news_raw_sources.json"
OUT_FILE = DATA / "news_sentiment.json"

# ── 方向关键词（对称）──
POS_STRONG = ["突破", "新高", "超预期", "暴涨", "涨停", "大涨", "创新高", "业绩预增",
              "同比大增", "翻倍", "爆发", "飙升", "扩产", "中标", "获批", "涨价",
              "上调", "增持", "回购", "净流入", "逆势上涨", "领涨", "创纪录"]
POS_MILD = ["涨", "升", "利好", "反弹", "回升", "回暖", "改善", "收窄", "增长",
            "盈利", "增", "看好", "推荐", "景气", "受益", "突破性进展", "放量"]
NEG_STRONG = ["暴跌", "崩盘", "爆雷", "违约", "退市", "跌停", "大跌", "重挫", "腰斩",
              "预亏", "亏损", "下滑", "减持", "抛售", "净流出", "制裁", "打压",
              "立案", "调查", "处罚", "下调", "评级下调", "跌破", "创年内新低"]
NEG_MILD = ["跌", "跳水", "预警", "萎缩", "低迷", "承压", "拖累", "担忧", "风险",
            "回落", "降温", "走弱", "疲软", "放缓", "利空", "压力", "不确定性"]

# ── sector 关键词映射（对齐 SECTOR_SIGNALS 的 sector 名）──
SECTOR_KEYWORDS = {
    "半导体": ["半导体", "芯片", "存储", "晶圆", "光刻", "封测", "EDA"],
    "AI算力": ["AI", "算力", "大模型", "GPU", "服务器", "数据中心", "AIDC", "云计算"],
    "AI/科技": ["科技", "软件", "互联网", "人工智能", "机器人", "数字经济", "信创"],
    "医药": ["医药", "医疗", "创新药", "生物", "疫苗", "CXO", "药企", "集采", "医保"],
    "新能源": ["新能源", "光伏", "风电", "储能", "锂电", "电池", "充电桩", "氢能", "碳中和"],
    "消费": ["消费", "白酒", "食品", "饮料", "家电", "零售", "旅游", "免税", "白酒"],
    "金融": ["银行", "券商", "证券", "保险", "金融", "信贷", "利率", "降准", "降息"],
    "军工": ["军工", "国防", "航天", "航空", "导弹", "卫星", "兵器"],
    "有色金属": ["铜", "铝", "稀土", "锂", "钴", "镍", "有色", "金属"],
    "贵金属": ["黄金", "白银", "金价", "金ETF"],
    "能源化工": ["原油", "石油", "天然气", "煤炭", "化工", "燃料油", "炼化", "页岩"],
    "基建/地产": ["基建", "地产", "房地产", "建筑", "水泥", "工程机械", "城中村"],
    "通信/5G": ["5G", "通信", "光模块", "光通信", "CPO", "基站", "运营商"],
    "农业": ["养殖", "猪", "鸡", "农业", "粮食", "种业", "农产品", "饲料"],
    "机器人/智造": ["机器人", "智能制造", "工业母机", "人形机器人", "自动化"],
    "消费电子": ["消费电子", "手机", "VR", "AR", "苹果", "华为"],
    "传媒/游戏": ["传媒", "游戏", "影视", "IP", "电竞", "短剧"],
    "汽车": ["汽车", "新能源车", "智能驾驶", "自动驾驶", "零部件"],
    "环保": ["环保", "水务", "固废", "环卫"],
}

# 反向：sector 关键词是否出现在标题+摘要里
def match_sector(text: str) -> list:
    hits = []
    for sec, kws in SECTOR_KEYWORDS.items():
        if any(kw in text for kw in kws):
            hits.append(sec)
    return hits

def judge_direction(text: str, is_bearish: bool = False) -> tuple:
    """返回 (direction, score, reason)
    
    FIX 2026-08-01: 支持 fetch_news_sources 的 is_bearish 标记（立案/处罚/诉讼
    等利空公告标题往往不含情绪词，关键词判定会漏判为中性）。
    """
    pos_s, neg_s, reason = 0, 0, []
    for kw in POS_STRONG:
        if kw in text:
            pos_s += 2
            reason.append(f"利好:{kw}")
    for kw in POS_MILD:
        if kw in text:
            pos_s += 1
            reason.append(f"利好:{kw}")
    for kw in NEG_STRONG:
        if kw in text:
            neg_s += 2
            reason.append(f"利空:{kw}")
    for kw in NEG_MILD:
        if kw in text:
            neg_s += 1
            reason.append(f"利空:{kw}")
    # is_bearish 标记 = 监管处罚/诉讼/立案类公告，强利空信号
    if is_bearish:
        neg_s += 3
        reason.append("利空:监管/处罚公告")
    net = pos_s - neg_s
    if net >= 2:
        return "看多", net, "; ".join(reason[:5])
    elif net <= -2:
        return "看空", net, "; ".join(reason[:5])
    elif abs(net) <= 1:
        return "中性", net, ""
    return "中性", net, ""

def main():
    if not RAW_FILE.exists():
        print(f"[auto_sentiment] 无 {RAW_FILE}，跳过", file=sys.stderr)
        return 1
    raw = json.loads(RAW_FILE.read_text(encoding="utf-8"))
    items = raw.get("items", [])

    # ── P1-1: 合并政策独立源（gov.cn）──
    policy_agg = {}
    policy_file = DATA / "policy_signals.json"
    if policy_file.exists():
        try:
            pdata = json.loads(policy_file.read_text(encoding="utf-8"))
            policy_agg = pdata.get("sectors", {})
        except (json.JSONDecodeError, OSError):
            pass

    # ── P2-1: 源分级权重 + 时间衰减 ──
    # 源分级: A级=政策(gov.cn,权重1.0) B级=权威财经媒体(权重0.6) C级=聚合/自媒体(权重0.3)
    SOURCE_WEIGHT = {
        "sina": 0.6, "eastmoney": 0.6, "tonghuashun": 0.6,
        "gov": 1.0, "policy": 1.0,
        "wallstreetcn": 0.6, "cls": 0.6, "caixin": 0.6,
    }
    DEFAULT_SOURCE_WEIGHT = 0.4
    from datetime import datetime as _dt
    _now = _dt.now()

    def _time_weight(it) -> float:
        """新闻时间衰减：≤1天=1.0，3天=0.5，7天=0.2，无时间=0.5"""
        tstr = it.get("time", "")
        if not tstr or len(tstr) < 10:
            return 0.5
        try:
            t = _dt.strptime(tstr[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            try:
                t = _dt.strptime(tstr[:10], "%Y-%m-%d")
            except ValueError:
                return 0.5
        age_days = (_now - t).days
        if age_days <= 1:
            return 1.0
        elif age_days <= 3:
            return 0.5
        elif age_days <= 7:
            return 0.2
        return 0.05

    # 按 sector 聚合
    from collections import defaultdict
    agg = defaultdict(lambda: {"bullish": 0, "bearish": 0, "neutral": 0, "items": [], "reasons": []})

    for it in items:
        text = f"{it.get('title','')} {it.get('summary','') or ''}"
        # FIX: 优先用 fetch 层推断好的 matched_sectors（公司名映射），
        # 兜底用 SECTOR_KEYWORDS 关键词匹配
        sectors = it.get("matched_sectors") or match_sector(text)
        if isinstance(sectors, str):
            sectors = [sectors]
        # FIX: 传入 is_bearish 标记，让监管/处罚公告正确判看空
        direction, net, reason = judge_direction(text, is_bearish=bool(it.get("is_bearish")))
        w = SOURCE_WEIGHT.get(it.get("source", ""), DEFAULT_SOURCE_WEIGHT) * _time_weight(it)
        for sec in sectors:
            a = agg[sec]
            if direction == "看多":
                a["bullish"] += abs(net) * w
            elif direction == "看空":
                a["bearish"] += abs(net) * w
            else:
                a["neutral"] += 1 * w
            a["items"].append(it.get("title", "")[:60])
            if reason and len(a["reasons"]) < 3:
                a["reasons"].append(f"[{direction}] {reason}")

    # 生成 sector sentiment（对称阈值）
    sectors_out = {}
    for sec, a in sorted(agg.items()):
        total = a["bullish"] + a["bearish"] + a["neutral"]
        if total == 0:
            continue
        net = a["bullish"] - a["bearish"]
        net = a["bullish"] - a["bearish"]
        # 方向判定：净分阈值（支持浮点权重）
        if total >= 1.5 and net >= 1.5:
            direction, strength = "看多", ("强" if net >= 3.0 else "中")
        elif total >= 1.5 and net <= -1.5:
            direction, strength = "看空", ("强" if net <= -3.0 else "中")
        else:
            direction, strength = "中性", "弱"
        note = f"新闻{total:.2f}条(多{a['bullish']:.2f}/空{a['bearish']:.2f}/中{a['neutral']:.2f})"
        if a["reasons"]:
            note += " | " + " | ".join(a["reasons"][:2])
        sectors_out[sec] = {
            "direction": direction,
            "strength": strength,
            "note": note,
        }

    # ── P1-1: 政策信号合并（政策是高权重独立层，覆盖新闻情绪）──
    policy_merged = 0
    for sec, psig in policy_agg.items():
        if psig.get("direction") in ("看多", "看空") and psig.get("strength") in ("强", "中"):
            old = sectors_out.get(sec, {})
            old_dir = old.get("direction", "中性")
            new_dir = psig["direction"]
            # 政策方向与新闻方向冲突时，政策优先（政策是更大的Beta）
            if old_dir != new_dir and old_dir != "中性":
                note = f"{old.get('note','')} | [政策覆盖] {psig['note']}"
                sectors_out[sec] = {
                    "direction": new_dir,
                    "strength": "强" if psig["strength"] == "强" else old.get("strength", "中"),
                    "note": note,
                }
            elif old_dir == "中性":
                sectors_out[sec] = {
                    "direction": new_dir,
                    "strength": psig["strength"],
                    "note": f"[政策] {psig['note']}",
                }
            else:
                # 同向：强度取更高
                if psig["strength"] == "强" and old.get("strength") != "强":
                    sectors_out[sec]["strength"] = "强"
                sectors_out[sec]["note"] = f"{old.get('note','')} | [政策确认] {psig['note']}"
            policy_merged += 1

    out = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        "source": f"auto_sentiment: {len(items)}条新闻 + 政策{policy_merged}行业",
        "sectors": sectors_out,
    }
    OUT_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[auto_sentiment] 写入 {OUT_FILE}")
    print(f"  sectors: {len(sectors_out)} | 政策合并: {policy_merged}")
    from collections import Counter
    c = Counter(v["direction"] for v in sectors_out.values())
    print(f"  方向分布: {dict(c)}")
    if "--stdout" in sys.argv:
        for sec, v in sectors_out.items():
            print(f"  {sec:10s} {v['direction']}/{v['strength']} {v['note'][:60]}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
