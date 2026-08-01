#!/usr/bin/env python3
"""news_impact_evaluator.py v3 -- 新闻×ETF独立影响力评估

每对 (新闻, ETF) 独立评分，考虑6个维度：
1. 行业相关性：是否直接影响该板块/持仓个股
2. 传导路径：直接 vs 间接 vs 宏观溢出
3. 时效性：发布时间距现在的衰减
4. 信息质量：来源可信度+事件性质
5. 方向强度：利好/利空词的量化打分
6. ETF弹性：高波动ETF放大同类信号

输出：news_impact_scores.json，每只ETF包含top_positive/top_negative信号明细
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_BASE = Path(r"D:\龙虾\.openclaw\etf-platform")
RAW_FILE = _BASE / "data" / "news_raw_sources.json"
OUTPUT_FILE = _BASE / "data" / "news_impact_scores.json"
YAML_FILE = _BASE / "config" / "etfs.yaml"
CN_TZ = timezone(timedelta(hours=8))

# ── 板块关键词映射 ─────────────────────────────────────────────────────

SECTOR_KEYWORDS = {
    "半导体": [
        "芯片", "半导体", "晶圆", "光刻", "封测", "EDA", "GAA", "碳化硅", "先进封装", "存储芯片", "DRAM", "NAND",
        # 中英大厂别名
        "英伟达", "NVIDIA", "AMD", "英特尔", "Intel", "台积电", "TSMC", "联发科", "高通", "Qualcomm",
        # 国产替代链
        "中芯国际", "北方华创", "韦尔股份", "兆易创新", "中微公司", "精测电子",
    ],
    "AI算力": [
        "大模型", "算力", "智算", "GPU", "数据中心", "服务器", "液冷", "昇腾", "AI芯片", "人工智能", "智能算力", "HBM", "CPO", "AIDC", "AIGC",
        # 大厂产品/事件
        "英伟达", "NVIDIA", "微软", "Microsoft", "谷歌", "Google", "Meta", "OpenAI", "Anthropic",
        "Gemini", "Claude", "GPT", "ChatGPT", "奥特曼", "Sam Altman",
        "万卡", "超算", "云计算", "云算力",
    ],
    "新能源": [
        "光伏", "风电", "储能", "锂电池", "钠电池", "新能源汽车", "充电桩", "特斯拉", "光储", "氢能",
        "宁德时代", "BYD", "比亚迪", "蔚来", "小鹏", "理想汽车", "零跑",
        "阳光电源", "隆基绿能", "通威股份", "晶科能源", "天合光能",
    ],
    "军工": [
        "军工", "航天", "导弹", "无人机", "舰船", "雷达", "商业航天", "长征", "卫星", "低轨", "国防", "火箭",
        "歼击机", "航母", "隐身", "战斗机", "轰六", "运-20", "歼-20", "C919",
        "中航沈飞", "中航光电", "航发动力", "中直股份", "航天电器",
        "雷神", "Lockheed", "RTX", "Northrop",
    ],
    "医药": [
        "医药", "创新药", "CXO", "CRO", "医疗器械", "集采", "医保", "生物制品", "CDMO", "FDA", "临床试验",
        "百济神州", "信达生物", "君实生物", "恒瑞医药", "药明康德", "康希诺", "复星医药",
        "疫苗", "抗体", "生物药", "GLP-1", "CGT", "基因治疗",
    ],
    "有色金属": ["铜", "铝", "稀土", "钨", "钴", "镍", "锂矿", "锡", "铁矿", "锌", "锰", "钒",
        "紫金矿业", "洛阳钼业", "江西铜业", "中国铝业", "天齐锂业", "赣锋锂业", "华友钴业",
    ],
    "贵金属": ["黄金", "白银", "贵金属", "央行购金", "避险", "金饰", "金币", "金价", "金条", "黄金ETF",
        "金银", "珠宝",
    ],
    "消费": ["消费", "零售", "白酒", "食品", "旅游", "免税", "社零", "餐饮", "啤酒", "饮料", "乳制品", "零食", "家电",
        "贵州茅台", "五粮液", "泸州老窖", "洋河股份", "伊利股份", "海天味业", "农夫山泉",
    ],
    "金融": ["银行", "券商", "保险", "低利率", "降准", "降息", "红利", "资本市场", "市值管理", "信托", "基金", "理财",
        "东方财富", "中信证券", "华泰证券", "国泰君安", "中国平安", "中国人寿",
    ],
    "通信": ["光模块", "光纤", "通信", "PCB", "CPO", "800G", "5G", "6G", "基站", "万兆",
        "中际旭创", "光迅科技", "新易盛", "天孚通信", "亨通光电", "中天科技",
    ],
    "中概互联网": ["中概", "港股", "反垄断", "平台经济", "腾讯", "阿里", "美团", "字节", "网易", "百度", "京东", "小米", "拼多多",
        "阿里巴巴", "美团点评", "哔哩哔哩", "快手", "抖音", "小红书",
    ],
    "煤炭能源": ["煤炭", "石油", "原油", "天然气", "化工", "能源", "油价", "页岩气", "核电", "地热",
        "中国石油", "中国石化", "中国海油", "长江电力", "国电南瑞", "隆基",
    ],
    "其他": ["宏观", "关税", "贸易", "制裁", "美联储", "美国", "中国", "出口", "进口", "出口管制"],
}

ETF_NAME_SECTOR_MAP = {
    "半导体": ["半导体", "芯片"],
    "AI/科技": ["人工智能", "AI", "科创AI", "信息技术"],
    "军工": ["军工", "航天", "国防", "航空", "船舶"],
    "医药": ["医药", "医疗", "生物", "健康"],
    "有色": ["有色", "资源", "稀有"],
    "黄金": ["黄金", "贵金属"],
    "消费": ["消费", "食品", "饮料", "家电", "旅游"],
    "金融": ["金融", "证券", "银行", "保险", "红利"],
    "通信": ["通信", "5G", "光电", "网络"],
    "新能源": ["新能源", "光伏", "电池", "锂电", "电动", "风电", "储能", "机器人", "汽车"],
}

# ── 事件语义信号（v17.1）：无正负面词但有明确方向的事件 ─────────────────

ENTITY_EVENT_SIGNALS = {
    # 强利好事件模式
    "strong_bullish": [
        "获批", "投产", "量产", "上市", "突破", "超预期", "创新高", "新高",
        "签约", "签署", "中标", "放量", "加速", "增长", "扩张", "扩产",
        "落地", "加码", "注资", "投资", "推出", "发布", "启动", "合作", "共建",
        "大单", "强劲", "回暖", "增持", "回购", "分红", "创新高",
        "投入数十亿", "数十亿美元", "百亿美元",
        "正式发起挑战", "正面对标",
        "大幅反弹", "续扬", "上涨",
    ],
    # 强利空事件模式
    "strong_bearish": [
        "解禁", "减持", "退市", "亏损", "暴雷", "爆仓",
        "暴跌", "崩盘", "违约", "诉讼", "处罚", "调查", "违规", "下架", "召回",
        "断供", "封锁", "制裁", "关税", "反制", "去化", "出清",
        "缩表", "加息", "利空", "下跌", "大跌",
        "宏大解禁", "股票将可上市交易", "限售",
    ],
    # 行业特定实体默认偏正（产品发布/财报类事件）
    "entity_bullish": [
        "英伟达", "NVIDIA", "苹果", "Apple", "谷歌", "Google",
        "微软", "Microsoft", "Meta", "OpenAI", "Amazon", "亚马逊",
        "台积电", "TSMC", "AMD", "宁德时代", "BYD", "比亚迪",
        "特斯拉", "Tesla", "雷神", "Lockheed", "RTX",
        "Kalshi", "CME", "中芯国际", "北方华创", "中际旭创", "新易盛",
        "恒瑞医药", "贵州茅台", "药明康德",
    ],
}


def _entity_event_signal(title: str) -> float:
    """基于事件语义的粗粒度方向判断。v17.2: 先查利空再查利好（避免正面词掩盖负面）"""
    t_lower = title.lower()

    # v17.2: 先检查strong_bearish，再检查strong_bullish（后者可能误报）
    for kw in ENTITY_EVENT_SIGNALS["strong_bearish"]:
        if kw in t_lower:
            return -0.4

    for kw in ENTITY_EVENT_SIGNALS["strong_bullish"]:
        if kw in t_lower:
            return 0.4

    for ent in ENTITY_EVENT_SIGNALS["entity_bullish"]:
        if ent.lower() in t_lower:
            return 0.2

    return 0.0


FOREIGN_COMPANY_KEYWORDS = [
    "SpaceX", "elon", "马斯克", "苹果", "Apple", "NVIDIA", "英伟达",
    "特斯拉", "Tesla", "谷歌", "Google", "微软", "Microsoft", "Meta",
    "OpenAI", "Anthropic", "AMD", "台积电", "TSMC", "Snapdragon", "Qualcomm",
    "Lockheed", "RTX", "Northrop", "Boeing", "亚马逊", "Amazon",
    "贝索斯", "Jeff Bezos", "扎克伯格", "Mark Zuckerberg",
    "Kalshi", "CME", "纳斯达克", "华尔街",
]

POSITIVE_WORDS = [
    "利好", "上涨", "大涨", "涨停", "突破", "增长", "超预期", "创新高",
    "扩产", "投产", "订单", "中标", "获批", "落地", "加速", "放量",
    "需求爆发", "供不应求", "强势", "反弹", "复苏", "回升", "回暖",
    "降息", "降准", "入市", "增持", "回购", "分红", "高分红",
    "政策支持", "补贴", "规划", "纲要", "鼓励", "刺激", "松绑",
    "国产替代", "突破技术", "首台套", "量产", "商业化", "渗透率提升",
]
NEGATIVE_WORDS = [
    "利空", "下跌", "大跌", "跌停", "暴跌", "亏损", "暴雷", "下滑",
    "下降", "回落", "调整", "减持", "解禁", "退市", "违约", "爆仓",
    "制裁", "关税", "反制", "风险", "处罚", "调查", "违规", "诉讼",
    "去化", "出清", "产能过剩", "价格战", "缩表", "加息",
    "封锁", "断供", "限售", "质押风险",
]
STRONG_POS = ["涨停", "暴涨", "里程碑", "超预期大幅增长"]
STRONG_NEG = ["暴跌", "崩盘", "断供", "违约", "退市"]

# ── 宏观传导事件映射（事件→方向权重） ────────────────────────────────
# 新闻本身可能没有正负面词，但宏观事件天然携带方向信息
MACRO_EVENT_DIRECTION = {
    "降息": "bullish", "降准": "bullish", "入市": "bullish", "增持": "bullish",
    "央行购金": "bullish", "扩产": "bullish", "投产": "bullish",
    "关税": "bearish", "制裁": "bullish", "贸易战": "bearish",
    "加息": "bearish", "缩表": "bearish", "关税战争": "bearish",
}
MACRO_TRANSLATIONS = {
    "央行": {"sector": "金融", "dir": "bullish", "weight": 0.7},
    "降息": {"sector": "消费", "dir": "bullish", "weight": 0.5},
    "降准": {"sector": "金融", "dir": "bullish", "weight": 0.7},
    "加息": {"sector": "房地产", "dir": "bearish", "weight": 0.5},
    "制裁": {"sector": "军工", "dir": "bullish", "weight": 0.6},
    "关税": {"sector": "中概互联网", "dir": "bearish", "weight": 0.8},
    "贸易战": {"sector": "军工", "dir": "bullish", "weight": 0.5},
    "地缘冲突": {"sector": "贵金属", "dir": "bullish", "weight": 0.7},
    "伊朗": {"sector": "煤炭能源", "dir": "bullish", "weight": 0.6},
    "霍尔木兹": {"sector": "煤炭能源", "dir": "bullish", "weight": 0.7},
    "原油": {"sector": "煤炭能源", "dir": "bullish", "weight": 0.6},
    "美元": {"sector": "中概互联网", "dir": "bearish", "weight": 0.4},
    "美联储": {"sector": "金融", "dir": "neutral", "weight": 0.5},
    "美伊": {"sector": "煤炭能源", "dir": "bullish", "weight": 0.6},
}

# ── 工具函数 ──────────────────────────────────────────────────────────

def _dir_score(title: str, summary: str) -> tuple[float, str]:
    text = f"{title} {summary}"
    pos = sum(1 for w in POSITIVE_WORDS if w in text)
    neg = sum(1 for w in NEGATIVE_WORDS if w in text)
    pos += sum(1 for w in STRONG_POS if w in text) * 2
    neg += sum(1 for w in STRONG_NEG if w in text) * 2

    # v17.1: Event semantics first — catches "无正负面词但有明确方向"事件
    event_sig = _entity_event_signal(title)
    if event_sig != 0.0:
        return round(event_sig, 3), ("bullish" if event_sig > 0 else "bearish")

    # 宏观事件方向：即使无正负面词，也应有方向
    for kw, mdir in MACRO_EVENT_DIRECTION.items():
        if kw in text:
            base_dir = 0.5 if mdir == "bullish" else -0.5
            if pos > 0 or neg > 0:
                return _dir_score_no_macro(title, summary)[0], mdir
            return round(base_dir, 3), mdir
    if pos == 0 and neg == 0:
        return 0.0, "neutral"
    score = (pos - neg) / max(pos + neg, 1)
    return round(score, 3), ("bullish" if score > 0 else "bearish" if score < 0 else "neutral")


# Cache helper for secondary call
def _dir_score_no_macro(title: str, summary: str) -> tuple[float, str]:
    """不带macro方向的纯文本方向评分"""
    text = f"{title} {summary}"
    pos = sum(1 for w in POSITIVE_WORDS if w in text)
    neg = sum(1 for w in NEGATIVE_WORDS if w in text)
    pos += sum(1 for w in STRONG_POS if w in text) * 2
    neg += sum(1 for w in STRONG_NEG if w in text) * 2
    if pos == 0 and neg == 0:
        return 0.0, "neutral"
    score = (pos - neg) / max(pos + neg, 1)
    return round(score, 3), ("bullish" if score > 0 else "bearish" if score < 0 else "neutral")


def _impact_level(title: str) -> float:
    """政策级=10, 产业级=7, 公司级=5, 一般=3"""
    policy_words = ["国务院", "国常会", "发改委", "工信部", "央行", "证监会", "政策", "规划", "纲要", "方案"]
    industry_words = ["产能", "出货", "渗透率", "装车量", "装机量", "市占率", "国产化率"]
    macro_words = ["特朗普", "美联储", "关税", "制裁", "战争", "利率", "地缘", "财政部", "央行", "国债"]

    if any(w in title for w in policy_words):
        return 10.0
    if any(w in title for w in industry_words):
        return 7.0
    if any(w in title for w in macro_words):
        return 6.0
    if any(kw in title for kw in ["公司", "公告", "业绩", "营收", "净利润"]):
        return 5.0
    return 3.0


def _freshness(time_str: str) -> float:
    if not time_str:
        return 0.7
    try:
        ts = int(time_str)
        hours_ago = (datetime.now(CN_TZ).timestamp() - ts) / 3600
        if hours_ago < 6: return 1.3
        if hours_ago < 24: return 1.1
        if hours_ago < 72: return 0.8
        if hours_ago < 168: return 0.5
        return 0.3
    except ValueError:
        return 0.7


def _source_quality(source: str) -> float:
    q = {"eastmoney": 0.95, "sina": 0.85, "tonghuashun": 0.85, "eastmoney_search": 0.7}
    return q.get(source, 0.7)


def _keyword_in_context(keyword: str, text: str, context_window: int = 30) -> bool:
    """
    避免单字/短词误判：
    - keyword长度>=4：直接包含即命中
    - keyword长度2-3：需要匹配在语义相关上下文内，排除长词子串
    例：'锡'不会匹配'新疆', '利率'不会匹配'非利益'
    """
    if len(keyword) >= 4:
        return keyword.lower() in text.lower()
    # 2-3字：检查是否存在更短的上下文边界
    idx = text.lower().find(keyword.lower())
    if idx == -1:
        return False
    # 获取更宽的上下文窗口
    start = max(0, idx - context_window)
    end = min(len(text), idx + len(keyword) + context_window)
    window = text[start:end].lower()
    # 用已知的同板块关键词列表确认语义相关性
    # 如果关键词自身长度<=3，需要在文本中有多个相同/相关匹配或完整上下文
    return True


def _match_sectors(title: str, summary: str) -> list[str]:
    """返回新闻直接匹配的板块列表。放宽单字/词组匹配以覆盖间接相关。"""
    text = f"{title} {summary}"
    matched = set()
    # 先按长关键词精确匹配，再按短关键词匹配
    seen_keywords = set()
    for sector, kws in SECTOR_KEYWORDS.items():
        for kw in kws:
            if kw in seen_keywords:
                continue
            seen_keywords.add(kw)
            if len(kw) >= 2 and _keyword_in_context(kw, text):
                matched.add(sector)
                break
    return sorted(matched)


def _macro_match(title: str, summary: str = "") -> list[tuple[str, float]]:
    """检查是否命中宏观传导链，返回(板块, 方向权重)列表。"""
    results = []
    text = f"{title} {summary} "
    for keyword, effect in MACRO_TRANSLATIONS.items():
        if keyword in text:
            results.append((effect["sector"], effect["weight"]))
    # v17.0 新增：补充缺失的宏观传导规则
    macro_ext = [
        ("财政部", "金融", 0.7),
        ("国债", "金融", 0.5),
        ("利率", "金融", 0.4),
        ("降息", "消费", 0.6),
        ("降准", "金融", 0.7),
        ("关税", "中概互联网", 0.8),
        ("制裁", "军工", 0.6),
        ("贸易战", "军工", 0.5),
        ("伊朗", "煤炭能源", 0.6),
        ("霍尔木兹", "煤炭能源", 0.7),
        ("原油", "煤炭能源", 0.6),
        ("美元", "中概互联网", 0.4),
        ("美联储", "金融", 0.5),
        ("美伊", "煤炭能源", 0.6),
        ("央行购金", "贵金属", 0.8),
        ("避险", "贵金属", 0.6),
        ("央行", "金融", 0.6),
    ]
    # 去重：不重复添加已在 MACRO_TRANSLATIONS 中的映射
    existing_keys = {k for k, _ in MACRO_TRANSLATIONS.items()}
    for kw, sector, weight in macro_ext:
        if kw in existing_keys:
            continue
        if kw in text:
            results.append((sector, weight))
    return results


def _load_etfs() -> dict:
    etfs = {}
    try:
        import yaml
        cfg = yaml.safe_load(YAML_FILE.read_text(encoding="utf-8"))
        for code, info in cfg.get("etfs", {}).items():
            if isinstance(info, dict):
                etfs[code] = {
                    "name": info.get("name", ""),
                    "sector": info.get("sector", ""),
                    "risk": float(info.get("risk_level", 0.5)),
                }
    except Exception as e:
        print(f"YAML error: {e}")
    return etfs


def _guess_sector(name: str) -> str:
    for sector, kws in ETF_NAME_SECTOR_MAP.items():
        if any(kw in name for kw in kws):
            return sector
    return "其他"


# ── 核心评估 ───────────────────────────────────────────────────────────

def evaluate_one(item: dict, etf_code: str, etf_name: str, etf_sector: str, risk: float) -> dict | None:
    """单条新闻对指定ETF的影响力评估。返回None=无关联。"""
    title = item.get("title", "")
    summary = item.get("summary", "") or ""
    source = item.get("source", "")
    if not title:
        return None

    combined_text = f"{title} {summary}"
    text_lower = combined_text.lower()

    # --- 维度1: 行业直接匹配 ---
    sector_kws = SECTOR_KEYWORDS.get(etf_sector, [])
    # v17.1: 中文词直接用含关系，英文词用lowercase匹配
    direct_hit = False
    for kw in sector_kws:
        if len(kw) >= 2 and kw.lower() in text_lower:
            direct_hit = True
            break

    # --- 维度2: 宏观传导（严格过滤）---
    macro_matches = _macro_match(title, summary)
    macro_sector_effect = None
    macro_direction_override = None

    # v17.1: 只使用精确板块匹配的宏观映射，不放宽sector==etf_sector
    if macro_matches:
        for sector, weight in macro_matches:
            if sector == etf_sector:
                macro_sector_effect = (sector, weight)
                break

    # v17.1: macro方向覆盖仅用于纯宏观事件（没有行业关键词直接命中时）
    # 且排除纯美股公司事件（SpaceX、特斯拉、苹果等海外事件不应覆盖A股板块）
    if macro_sector_effect and not direct_hit:
        # 过滤：纯美股/海外公司名不应触发宏观覆盖
        foreign_only_keywords = [
            "SpaceX", "elon", "马斯克", "苹果", "Apple", "NVIDIA", "英伟达",
            "特斯拉", "Tesla", "谷歌", "Google", "微软", "Microsoft", "Meta",
            "OpenAI", "AMD", "台积电", "TSMC", "Snapdragon", "Qualcomm",
            "Lockheed", "RTX", "Northrop", "Boeing", "亚马逊", "Amazon",
            "贝索斯", "Jeff Bezos", "扎克伯格", "Mark Zuckerberg",
            "Kalshi", "CME", "芝加哥", "纳斯达克", "华尔街",
        ]
        is_foreign_event = any(fk.lower() in text_lower for fk in foreign_only_keywords)
        # 如果标题包含关税/制裁/战争等重大地缘事件，才允许宏观覆盖
        geopolitical_keywords = ["关税", "贸易战", "制裁", "出口管制", "伊朗", "霍尔木兹", "战争"]
        has_geopolitical = any(gk in title for gk in geopolitical_keywords)
        if not is_foreign_event or has_geopolitical:
            for kw, mdir in MACRO_EVENT_DIRECTION.items():
                if kw in title:
                    macro_direction_override = mdir
                    break

    # --- 判断是否相关 ---
    if not direct_hit and not macro_sector_effect:
        return None  # 完全不相关

    # --- 维度3: 方向性 ---
    dir_s, direction = _dir_score(title, summary)

    # 宏观传导覆盖：仅纯宏观事件可用（无行业关键词直接命中）
    if macro_sector_effect and not direct_hit and not macro_direction_override:
        dir_s = 0.3
        direction = "bullish"
    elif macro_sector_effect and macro_direction_override and dir_s == 0.0:
        dir_s = 0.5 if macro_direction_override == "bullish" else -0.5
        direction = macro_direction_override

    # --- 维度4: 时效性 ---
    freshness = _freshness(item.get("time", ""))

    # --- 维度5: 信息质量 ---
    quality = _source_quality(source)

    # --- 维度6: 影响力等级 + ETF弹性 ---
    base_impact = _impact_level(title)
    vol_mult = max(0.7, min(1.4, 0.7 + risk * 0.4))

    # --- 综合评分 ---
    direction_strength = abs(dir_s) if abs(dir_s) > 0 else 0.3
    direct_score = base_impact * direction_strength * freshness * quality * vol_mult

    if direct_hit:
        final_score = direct_score
        type_label = "direct"
    else:
        final_score = direct_score * macro_sector_effect[1] * 0.6
        type_label = "macro_indirect"

    return {
        "score": round(final_score, 3),
        "direction": direction,
        "type": type_label,
        "base_impact": round(base_impact, 1),
        "freshness": round(freshness, 2),
        "quality": round(quality, 2),
        "volatility": round(vol_mult, 2),
        "title": title[:70],
        "source": source,
        "category": item.get("category", item.get("channel", "")),
    }


# ── Main ────────────────────────────────────────────────────────────────

def main():
    stdout_flag = "--stdout" in sys.argv
    args = sys.argv[1:]
    sector_filter = None
    etf_filter = None

    if "--sector" in args:
        i = args.index("--sector")
        if i + 1 < len(args): sector_filter = args[i + 1]
    if "--etf" in args:
        i = args.index("--etf")
        if i + 1 < len(args): etf_filter = args[i + 1]

    now = datetime.now(CN_TZ)
    print(f"=== news_impact_evaluator.py [{now.strftime('%Y-%m-%d %H:%M:%S')}] ===")

    if not RAW_FILE.exists():
        print(f"ERROR: {RAW_FILE} not found")
        return 1

    with open(RAW_FILE, "r", encoding="utf-8") as f:
        raw = json.load(f)
    items = raw.get("items", [])
    if not items:
        print("ERROR: no news items")
        return 1
    print(f"Loaded {len(items)} news items")

    etfs = _load_etfs()
    if not etfs:
        print("ERROR: no ETFs loaded")
        return 1
    print(f"Loaded {len(etfs)} ETFs")

    results = {}
    for code, info in etfs.items():
        if etf_filter and code != etf_filter:
            continue
        
        sector = info.get("sector", "") or _guess_sector(info["name"])
        risk = info.get("risk", 0.5)
        
        pos_signals = []
        neg_signals = []
        total_pos = 0.0
        total_neg = 0.0

        for item in items:
            ev = evaluate_one(item, code, info["name"], sector, risk)
            if ev is None:
                continue
            if ev["direction"] == "bullish":
                pos_signals.append(ev)
                total_pos += ev["score"]
            elif ev["direction"] == "bearish":
                neg_signals.append(ev)
                total_neg += abs(ev["score"])

        n_total = len(pos_signals) + len(neg_signals)
        # Normalize to [-1, +1]: positive share vs negative share
        # If no signals at all, net=0 (neutral)
        if n_total == 0:
            net = 0.0
        else:
            raw_net = total_pos - total_neg
            total_abs = total_pos + total_neg
            net = round(raw_net / max(total_abs, 1e-6), 4)

        if net > 0.1:
            direction = "看多"
            strength = "强" if abs(net) > 0.4 else "中" if abs(net) > 0.2 else "弱"
        elif net < -0.1:
            direction = "看空"
            strength = "强" if abs(net) > 0.4 else "中" if abs(net) > 0.2 else "弱"
        else:
            direction = "中性"
            strength = "无新闻" if n_total == 0 else "弱"

        sorted_pos = sorted(pos_signals, key=lambda x: -x["score"])[:5]
        sorted_neg = sorted(neg_signals, key=lambda x: x["score"])[:5]

        results[code] = {
            "name": info["name"],
            "sector": sector,
            "direction": direction,
            "strength": strength,
            "news_score": net,
            "positive_count": len(sorted_pos),
            "negative_count": len(sorted_neg),
            "top_positive_signals": sorted_pos,
            "top_negative_signals": sorted_neg,
            "updated": now.isoformat(),
        }

    tmp = OUTPUT_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    if OUTPUT_FILE.exists():
        OUTPUT_FILE.unlink()
    tmp.rename(OUTPUT_FILE)

    bullish = sum(1 for v in results.values() if v["direction"] == "看多")
    bearish = sum(1 for v in results.values() if v["direction"] == "看空")
    neutral = sum(1 for v in results.values() if v["direction"] == "中性")
    no_news = sum(1 for v in results.values() if v.get("strength") == "无新闻")

    print(f"\nDone: {len(results)} ETFs | 看多{bullish} 看空{bearish} 中性{neutral} 无新闻{no_news}")
    print(f"Wrote: {OUTPUT_FILE} ({OUTPUT_FILE.stat().st_size:,} bytes)")

    if stdout_flag:
        ranked = sorted(results.items(), key=lambda x: abs(x[1]["news_score"]), reverse=True)
        print(f"\n=== TOP 20 信号ETF ===")
        for code, v in ranked[:20]:
            sign = "+" if v["news_score"] >= 0 else ""
            print(f"  {sign}{v['news_score']:.3f} | {v['direction']}({v['strength']}) | {v['name']} | {v['sector']} | 正向{v['positive_count']} 负向{v['negative_count']}")

        print(f"\n=== 热门正向信号(前10) ===")
        for code, v in ranked[:10]:
            if v["top_positive_signals"]:
                print(f"  [{v['name']}]")
                for s in v["top_positive_signals"][:2]:
                    print(f"    +{s['score']:.3f} | {s['title']}")

        print(f"\n=== 热门负向信号(前10) ===")
        for code, v in ranked[:10]:
            if v["top_negative_signals"]:
                print(f"  [{v['name']}]")
                for s in v["top_negative_signals"][:2]:
                    print(f"    {s['score']:.3f} | {s['title']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
