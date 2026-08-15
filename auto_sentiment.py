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
HISTORY_FILE = DATA / "news_sentiment_history.jsonl"  # d762: 历史方向分布校准
HISTORY_KEEP = 60       # history 只保留最近 60 行
CALIB_WINDOW = 30       # 校准读取最近 30 次记录
CALIB_MIN_RECORDS = 5   # 有效记录 < 5 次不校准（向后兼容）
CALIB_MAX_BUMP = 3      # 阈值最多上调 3 次 (1.5→3.0)

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
    "半导体": ["半导体", "芯片", "存储", "晶圆", "光刻", "封测", "EDA", "NAND", "DRAM", "海力士", "美光", "闪存"],
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

def _archive_old_sentiment() -> None:
    """d762: 把上次 news_sentiment.json 归档为 history 一行，仅保留最近 60 行。"""
    if not OUT_FILE.exists():
        return
    try:
        old = json.loads(OUT_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    secs = old.get("sectors")
    if not isinstance(secs, dict) or not secs:
        return
    row = {"updated": old.get("updated", ""),
           "sectors": {s: v["direction"] for s, v in secs.items()
                       if isinstance(v, dict) and v.get("direction")
                       and "[政策" not in v.get("note", "")}}
    lines = HISTORY_FILE.read_text(encoding="utf-8").splitlines() if HISTORY_FILE.exists() else []
    lines.append(json.dumps(row, ensure_ascii=False))
    HISTORY_FILE.write_text("\n".join(lines[-HISTORY_KEEP:]) + "\n", encoding="utf-8")

def calibrate_directions(sectors_out: dict, history_file: Path, max_bump: int = CALIB_MAX_BUMP) -> tuple:
    """d762: 历史分布校准——用历史方向比例对齐动态阈值，修正固定阈值系统性偏差。

    返回 (sectors_out, stats)。只校准新闻 sector（带 net 且非政策层）——政策是
    高权重独立层，不参与降级。net 由调用方在校准后剥离。
    """
    def _hist_ratio() -> tuple:
        if not history_file.exists():
            return None, None, []
        recs = []
        for ln in history_file.read_text(encoding="utf-8").splitlines()[-CALIB_WINDOW:]:
            if not ln.strip():
                continue
            try:
                secs = json.loads(ln).get("sectors")
            except (json.JSONDecodeError, AttributeError):
                continue
            if isinstance(secs, dict) and secs:
                recs.append(secs)
        if len(recs) < CALIB_MIN_RECORDS:
            return None, None, recs
        from collections import Counter
        cnt = Counter(d for secs in recs for d in secs.values())
        total = sum(cnt.values()) or 1
        return cnt.get("看多", 0) / total, cnt.get("看空", 0) / total, recs

    bull_ratio, bear_ratio, recs = _hist_ratio()
    if bull_ratio is None:
        return sectors_out, {"bull_ratio": None, "bear_ratio": None, "threshold": 1.5,
                             "bumped": 0, "note": f"history<{CALIB_MIN_RECORDS}({len(recs)})"}

    # 候选：排除政策层（policy 合并写 "[政策" 标记，高权重独立层）
    cand = {s: v for s, v in sectors_out.items()
            if isinstance(v, dict) and "net" in v and "[政策" not in v.get("note", "")}
    if not cand:
        return sectors_out, {"bull_ratio": None, "bear_ratio": None, "threshold": 1.5,
                             "bumped": 0, "note": "no_candidates"}

    def _now_ratio() -> tuple:
        b = sum(1 for v in cand.values() if v["direction"] == "看多")
        r = sum(1 for v in cand.values() if v["direction"] == "看空")
        return b / len(cand), r / len(cand)

    bull_now, bear_now = _now_ratio()
    threshold, bumped = 1.5, 0
    for _ in range(max_bump):
        bull_over = bull_now - bull_ratio > 0.15
        bear_over = bear_now - bear_ratio > 0.15
        if not bull_over and not bear_over:
            break
        threshold += 0.5
        bumped += 1
        if bull_over:
            for v in cand.values():
                if v["direction"] == "看多" and v["net"] < threshold:
                    v["direction"], v["strength"] = "中性", "弱"
        if bear_over:
            for v in cand.values():
                if v["direction"] == "看空" and v["net"] > -threshold:
                    v["direction"], v["strength"] = "中性", "弱"
        bull_now, bear_now = _now_ratio()

    # 强度校准：降级后剩余看多/看空 net>=3.0 为强（原逻辑不变）
    for v in cand.values():
        if v["direction"] == "看多":
            v["strength"] = "强" if v["net"] >= 3.0 else "中"
        elif v["direction"] == "看空":
            v["strength"] = "强" if v["net"] <= -3.0 else "中"
        else:
            v["strength"] = "弱"
    return sectors_out, {"bull_ratio": bull_ratio, "bear_ratio": bear_ratio,
                         "threshold": threshold, "bumped": bumped}

def main():
    if not RAW_FILE.exists():
        print(f"[auto_sentiment] 无 {RAW_FILE}，跳过", file=sys.stderr)
        return 1
    _archive_old_sentiment()  # d762: 确认是真运行（RAW 存在）后再归档上次输出 → history
    raw = json.loads(RAW_FILE.read_text(encoding="utf-8"))
    raw_items = raw.get("items", [])

    # ── d751: 可交易性门禁（过滤个股公告/娱乐等噪音，只对可交易新闻出信号）──
    from traded_news_filter import filter_tradable, is_tradable
    items, noise_items = filter_tradable(raw_items)
    from collections import Counter
    noise_reasons = Counter(is_tradable(it)[1] for it in noise_items)

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
            "net": net,  # d762: 校准用临时字段，输出前剥离
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

    # d762: 历史分布校准（政策合并后、产业链传导前；校准最终新闻+政策信号，政策层除外）
    sectors_out, calib_stats = calibrate_directions(sectors_out, HISTORY_FILE)

    # d751 ③: 产业链传导 — 上游信号联动下游（新能源看多→有色/汽车传导）
    try:
        from src.etf_platform.analysis.industry_chain import apply_chain_to_signals
    except ImportError:
        from etf_platform.analysis.industry_chain import apply_chain_to_signals
    sectors_after = apply_chain_to_signals(sectors_out)
    chain_added = len(sectors_after) - len(sectors_out)

    # 剥离校准临时字段 net，保持 sectors 输出结构不变（policy 覆盖/产业链 sector 无此字段，pop 安全）
    for v in sectors_after.values():
        if isinstance(v, dict):
            v.pop("net", None)

    out = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        "source": f"auto_sentiment: {len(raw_items)}条新闻(可交易{len(items)}/噪音{len(noise_items)}) + 政策{policy_merged}行业",
        "sectors": sectors_after,
        "stats": {
            "total": len(raw_items),
            "tradable_count": len(items),
            "noise_count": len(noise_items),
            "chain_propagated": chain_added,
            "calibration": calib_stats,
            "filtered_reasons": dict(noise_reasons),
        },
    }
    OUT_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[auto_sentiment] 写入 {OUT_FILE}")
    print(f"  过滤噪音新闻: {len(noise_items)}条 (增持减持公告/个股日常/娱乐体育等)")
    print(f"  sectors: {len(sectors_out)} | 政策合并: {policy_merged}")
    c = Counter(v["direction"] for v in sectors_out.values())
    print(f"  方向分布: {dict(c)}")
    if "--stdout" in sys.argv:
        for sec, v in sectors_out.items():
            print(f"  {sec:10s} {v['direction']}/{v['strength']} {v['note'][:60]}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
