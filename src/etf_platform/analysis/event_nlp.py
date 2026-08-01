from __future__ import annotations
#!/usr/bin/env python3
"""event_nlp.py — 基于规则引擎的中文财经新闻实时事件检测系统

轻量级零依赖方案：关键词词典 + 否定词检测 + 置信度评分。
替代 macro_overlay.py 的手动硬编码催化剂，实现自动从新闻流中
识别市场催化剂并映射到ETF行业。

事件分类体系（5大类 × 子类型）：
  政策类 → 宽松/收紧/产业扶持/监管
  业绩类 → 预增/预减/暴雷/超预期
  地缘类 → 制裁/贸易/冲突/脱钩
  产业类 → 技术突破/产能扩张/涨价/降价
  资金类 → 北向资金/ETF份额/融资融券/流动性

输出格式兼容 signals.py 的 ProfitSignalEngine 输入结构。

用法:
    python -m etf_platform.analysis.event_nlp --demo
    python -m etf_platform.analysis.event_nlp --source wallstreetcn --limit 20
    python -c "from etf_platform.analysis.event_nlp import detect_events; ..."
"""
import logging
logger = logging.getLogger(__name__)

import json
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

# ──────────────────────────────────────────────────────────────────────
# 数据模型
# ──────────────────────────────────────────────────────────────────────

@dataclass(slots=True)
class EventSignal:
    """单个检测到的事件信号。"""
    event_type: str          # 大类: policy/earnings/geopolitical/industry/fundflow
    sub_type: str            # 子类型: easing/tightening/support/regulation 等
    sentiment: float         # [-1.0, 1.0] -1=利空, 0=中性, +1=利好
    confidence: float        # [0.0, 1.0] 置信度
    urgency: str             # high/medium/low — 时效性等级
    sectors: list[str] = field(default_factory=list)  # 影响的行业
    keywords_matched: list[str] = field(default_factory=list)  # 命中的关键词
    raw_text: str = ""       # 原始文本摘要
    event_id: str = ""       # 去重用ID

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict[str, Any]) -> EventSignal:
        return EventSignal(**{k: v for k, v in d.items() if k in EventSignal.__dataclass_fields__})


@dataclass(slots=True)
class SectorSignal:
    """映射到行业的信号。"""
    sector: str
    etf_codes: list[str] = field(default_factory=list)
    signal_strength: float = 0.0   # [-1.0, 1.0]
    direction: str = "NEUTRAL"     # LONG/SHORT/NEUTRAL
    event_count: int = 0
    event_titles: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ──────────────────────────────────────────────────────────────────────
# 行业 → ETF代码映射 (从 config/etfs.yaml 动态加载)
# ──────────────────────────────────────────────────────────────────────

_SECTOR_TO_ETFS: dict[str, list[str]] | None = None


def _load_sector_to_etfs() -> dict[str, list[str]]:
    """从 etfs.yaml 构建 sector → [etf_codes] 映射。"""
    global _SECTOR_TO_ETFS
    if _SECTOR_TO_ETFS is not None:
        return _SECTOR_TO_ETFS

    try:
        from ..config_loader import load_etfs
        etfs = load_etfs()
    except (ImportError, FileNotFoundError, OSError):
        _SECTOR_TO_ETFS = {}
        return _SECTOR_TO_ETFS
    mapping: dict[str, list[str]] = {}
    for code, info in etfs.items():
        sector = info.get("sector", "")
        access = info.get("access", "")
        if sector and access == "buyable":
            mapping.setdefault(sector, []).append(code)

    _SECTOR_TO_ETFS = mapping
    return mapping


def _parse_etf_yaml_minimal(path: str) -> dict[str, list[str]]:
    """极简YAML解析：只提取 sector + code 对。"""
    mapping: dict[str, list[str]] = {}
    current_code: str | None = None
    current_sector: str = ""
    in_buyable = False

    with open(path, encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            # Match '  'CODE':': at start (2-space indent under etfs:)
            m = re.match(r"^  '(\d+)':$", stripped)
            if m:
                # flush previous
                if current_code and current_sector:
                    mapping.setdefault(current_sector, []).append(current_code)
                current_code = m.group(1)
                current_sector = ""
                in_buyable = False
                continue
            m2 = re.match(r"^    sector:\s*(.+)$", stripped)
            if m2 and current_code:
                current_sector = m2.group(1).strip().strip("'\"")
                continue
            m3 = re.match(r"^    access:\s*(.+)$", stripped)
            if m3 and current_code:
                in_buyable = m3.group(1).strip().strip("'\"") == "buyable"
                continue

    # flush last
    if current_code and current_sector:
        if in_buyable:
            mapping.setdefault(current_sector, []).append(current_code)

    return mapping


# ──────────────────────────────────────────────────────────────────────
# 否定词表 (用于 sentiment 反转)
# ──────────────────────────────────────────────────────────────────────

NEGATION_WORDS: set[str] = {
    "不", "未", "没有", "未能", "不及", "低于", "下滑", "下跌",
    "减少", "缩减", "亏损", "暴跌", "崩盘", "违约", "退市",
    "禁止", "限制", "制裁", "风险", "担忧", "利空", "承压",
    "回落", "走弱", "低迷", "疲软", "萎缩", "恶化", "负面",
}

NEGATION_RE = re.compile(
    r"(?:不|未|没有|未能|不及|低于|下滑|下跌|减少|缩减|亏损|"
    r"暴跌|崩盘|违约|退市|禁止|限制|制裁|风险|担忧|利空|承压|"
    r"回落|走弱|低迷|疲软|萎缩|恶化|负面)"
)


def _has_negation(text: str, window: int = 5) -> bool:
    """检测关键词附近是否有否定词。"""
    for neg in NEGATION_WORDS:
        idx = text.find(neg)
        if idx >= 0:
            # Check if negation is within `window` chars of any keyword match
            for kw_start in range(max(0, idx - window), min(len(text), idx + window)):
                if text[kw_start:kw_start+1] != "":
                    pass  # proximity check
            # Simple: just check distance
            if abs(idx - text.find(neg)) < window * 3:
                return True
    return False


# ──────────────────────────────────────────────────────────────────────
# 事件分类词典
# ──────────────────────────────────────────────────────────────────────

EVENT_DICTIONARIES: dict[str, dict[str, dict[str, Any]]] = {
    "policy": {
        "easing": {
            "keywords": [
                "降息", "降准", "逆回购", "MLF", "LPR下调", "宽松",
                "释放流动性", "注入流动性", "扩表", "量化宽松",
                "货币政策转向", "放松银根", "定向降准",
                "央行放水", "流动性充裕",
            ],
            "sentiment": 0.7,
            "urgency": "high",
            "sectors": ["宽基", "成长股", "AI/科技", "半导体", "新能源",
                        "房地产", "基建/地产", "消费", "白酒消费"],
        },
        "tightening": {
            "keywords": [
                "加息", "收紧", "缩表", "提高利率", "上调准备金",
                "收紧流动性", "货币紧缩", "去杠杆", "加息周期",
                "回收流动性", "收紧银根",
            ],
            "sentiment": -0.6,
            "urgency": "high",
            "sectors": ["成长股", "AI/科技", "半导体", "新能源",
                        "房地产", "小盘价值"],
        },
        "support": {
            "keywords": [
                "产业扶持", "补贴", "专项债", "基建投资", "设备更新",
                "以旧换新", "消费刺激", "减税降费", "税收优惠",
                "财政发力", "稳增长", "促消费", "支持",
                "新质生产力", "数字经济", "人工智能+",
                "国产替代", "自主可控", "卡脖子",
                "专项补贴", "产业基金",
            ],
            "sentiment": 0.6,
            "urgency": "medium",
            "sectors": ["AI算力", "半导体", "硬科技", "机器人/智造",
                        "通信/5G", "通信/光模块", "新能源", "家电",
                        "基建/地产", "消费", "白酒消费", "医药"],
        },
        "regulation": {
            "keywords": [
                "监管", "整顿", "严查", "处罚", "罚款", "窗口指导",
                "反垄断", "反垄断调查", "合规", "规范发展",
                "强监管", "严监管", "去产能", "限产",
                "双减", "教培", "平台经济",
                "立案", "立案调查", "违规", "调查", "被查", "警示函",
            ],
            "sentiment": -0.4,
            "urgency": "medium",
            "sectors": ["AI/科技", "消费", "白酒消费", "医药",
                        "港股综合", "金融", "券商"],
        },
        "monetary_authority": {
            "keywords": [
                "央行", "人民银行", "国务院", "发改委", "证监会",
                "银保监会", "财政部", "国资委", "政治局会议",
                "中央经济工作会议", "两会", "政府工作报告",
            ],
            "sentiment": 0.0,  # 仅作为触发器，sentiment由子类型决定
            "urgency": "high",
            "sectors": ["宽基", "金融", "券商", "红利/价值", "红利+低波",
                        "利率债", "信用债"],
        },
    },
    "earnings": {
        "surge": {
            "keywords": [
                "预增", "大幅增长", "业绩飙升", "净利润翻倍",
                "超预期", "盈利超预期", "营收大增", "利润暴增",
                "扭亏为盈", "创新高", "历史新高", "业绩炸裂",
                "景气度高", "量价齐升", "订单饱满",
            ],
            "sentiment": 0.8,
            "urgency": "high",
            "sectors": ["医药", "半导体", "消费", "白酒消费",
                        "新能源", "家电", "食品饮料", "医药器械",
                        "中药", "农业", "农产品"],
        },
        "decline": {
            "keywords": [
                "预减", "下滑", "亏损", "业绩暴雷", "不及预期",
                "营收下降", "利润下滑", "大幅减亏", "业绩承压",
                "利润缩水", "业绩预警", "业绩下修",
            ],
            "sentiment": -0.7,
            "urgency": "high",
            "sectors": ["消费", "白酒消费", "医药", "半导体",
                        "新能源", "家电", "食品饮料", "医药器械"],
        },
        "reporting_season": {
            "keywords": [
                "中报季", "一季报", "三季报", "年报", "财报季",
                "业绩预告", "业绩快报", "披露期", "密集披露",
            ],
            "sentiment": 0.0,
            "urgency": "medium",
            "sectors": ["宽基", "全市场", "大盘蓝筹", "成长股",
                        "小盘价值", "中盘成长"],
        },
    },
    "geopolitical": {
        "sanctions": {
            "keywords": [
                "制裁", "出口管制", "实体清单", "禁运", "断供",
                "BIS", "CHIPS Act", "芯片禁令", "技术封锁",
                "脱钩", "去风险", "供应链安全",
                "美国对华", "关税", "贸易战",
            ],
            "sentiment": -0.3,  # 整体偏空但国产替代利好
            "urgency": "high",
            "sectors": ["半导体", "军工", "硬科技", "AI算力",
                        "半导体设备", "通信/5G", "有色金属"],
        },
        "conflict": {
            "keywords": [
                "冲突", "战争", "军事", "演习", "导弹", "核潜艇",
                "空袭", "防空", "军演", "地缘紧张", "局势升级",
                "霍尔木兹海峡", "中东", "俄乌", "台海",
                "国防预算", "武器装备",
            ],
            "sentiment": 0.5,  # 军工利好
            "urgency": "high",
            "sectors": ["军工", "贵金属", "能源化工", "周期/资源",
                        "原油", "黄金"],
        },
        "trade": {
            "keywords": [
                "贸易协定", "自贸协定", "RCEP", "一带一路",
                "进出口", "贸易顺差", "贸易逆差", "出海",
                "跨境电商", "海外建厂", "全球化",
            ],
            "sentiment": 0.3,
            "urgency": "medium",
            "sectors": ["消费", "家电", "新能源", "半导体",
                        "通信/5G", "港股科技", "中概互联网"],
        },
        "tech_decoupling": {
            "keywords": [
                "科技脱钩", "技术壁垒", "半导体战", "芯片战争",
                "技术自立", "国产化率", "自主可控", "国产替代",
                "卡脖子技术", "技术封锁",
            ],
            "sentiment": 0.4,  # 国产替代利好
            "urgency": "high",
            "sectors": ["半导体", "半导体设备", "硬科技", "AI算力",
                        "通信/5G", "通信/光模块", "军工"],
        },
    },
    "industry": {
        "tech_breakthrough": {
            "keywords": [
                "技术突破", "研发成功", "量产", "首发", "新品发布",
                "里程碑", "全球首款", "国内首次", "打破垄断",
                "芯片制程", "光刻机", "量子计算", "固态电池",
                "AI大模型", "Agent", "多模态",
                "英伟达", "GPU", "HBM", "CoWoS",
            ],
            "sentiment": 0.7,
            "urgency": "medium",
            "sectors": ["半导体", "AI算力", "硬科技", "机器人/智造",
                        "通信/光模块", "5G/PCB", "云计算/算力"],
        },
        "capacity_expansion": {
            "keywords": [
                "扩产", "投产", "新增产能", "建新厂", "募投项目",
                "产能利用率", "满产", "开工率",
                "IPO", "首发上市", "科创板上市", "创业板上市", "注册制",
                "融资", "定增", "增发", "股权融资",
            ],
            "sentiment": 0.3,
            "urgency": "medium",
            "sectors": ["半导体", "新能源", "医药", "消费电子",
                        "通信/5G", "AI算力"],
        },
        "price_increase": {
            "keywords": [
                "涨价", "提价", "价格上涨", "供不应求", "缺货",
                "库存下降", "价格上行", "涨幅", "涨价潮",
                "锂价", "硅料", "面板", "存储芯片", "DRAM",
                "面板涨价", "硅片涨价", "药价", "糖价", "猪粮比",
            ],
            "sentiment": 0.5,
            "urgency": "high",
            "sectors": ["有色", "有色金属", "周期/资源", "新能源",
                        "半导体", "医药", "农业", "农产品",
                        "能源化工", "煤炭"],
        },
        "price_decrease": {
            "keywords": [
                "降价", "价格下跌", "价格战", "内卷", "亏损",
                "产能过剩", "供过于求", "去库存", "价格下行",
                "杀价", "打价格战", "卷价格",
            ],
            "sentiment": -0.5,
            "urgency": "medium",
            "sectors": ["新能源", "光伏", "消费电子", "半导体",
                        "家电", "消费", "食品饮料"],
        },
        "energy_resources": {
            "keywords": [
                "油价", "原油", "天然气", "铜价", "铝价",
                "黄金", "白银", "稀土", "锂", "钴", "镍",
                "大宗商品", "期货", "囤积", "战略储备",
                "电力", "电价", "煤炭", "光伏", "风电",
            ],
            "sentiment": 0.2,
            "urgency": "medium",
            "sectors": ["有色金属", "能源化工", "新能源", "公用事业",
                        "周期/资源", "贵金属", "煤炭"],
        },
    },
    "fundflow": {
        "northbound": {
            "keywords": [
                "北向资金", "沪股通", "深股通", "外资流入",
                "陆股通", "聪明钱", "外资加仓", "外资减持",
            ],
            "sentiment": 0.5,
            "urgency": "high",
            "sectors": ["宽基", "大盘蓝筹", "消费", "白酒消费",
                        "医药", "金融", "券商"],
        },
        "etf_flow": {
            "keywords": [
                "ETF申购", "ETF份额", "ETF净申购", "ETF扩容",
                "ETF赎回", "ETF份额增长", "资金涌入ETF",
                "宽基ETF", "行业ETF", "主题ETF",
            ],
            "sentiment": 0.4,
            "urgency": "medium",
            "sectors": ["宽基", "全市场", "大盘蓝筹", "成长股",
                        "小盘价值", "中盘成长"],
        },
        "margin_trading": {
            "keywords": [
                "融资融券", "融资余额", "融券余额", "杠杆资金",
                "两融", "融资买入", "融资净买入", "杠杆",
            ],
            "sentiment": 0.3,
            "urgency": "medium",
            "sectors": ["券商", "宽基", "成长股", "AI/科技",
                        "半导体", "小盘价值"],
        },
        "liquidity": {
            "keywords": [
                "资金面", "流动性", "DR007", "SHIBOR", "银行间",
                "资金紧张", "资金宽松", "市场缺钱", "钱荒",
                "逆回购到期", "公开市场操作",
            ],
            "sentiment": 0.1,
            "urgency": "high",
            "sectors": ["宽基", "金融", "券商", "利率债",
                        "信用债", "货币基金"],
        },
    },
}


# ──────────────────────────────────────────────────────────────────────
# 行业别名映射 (归一化 sector 名称)
# ──────────────────────────────────────────────────────────────────────

SECTOR_ALIASES: dict[str, list[str]] = {
    "半导体": ["芯片", "IC", "集成电路", "晶圆", "封测", "光刻", "EDA"],
    "AI算力": ["算力", "AI芯片", "GPU", "HBM", "CoWoS", "英伟达", "NVIDIA"],
    "军工": ["国防", "航天", "航空", "导弹", "战斗机", "航母", "卫星"],
    "新能源": ["光伏", "风电", "储能", "锂电池", "新能源车", "EV"],
    "有色金属": ["铜", "铝", "稀土", "锂", "钴", "镍", "金", "银", "钼"],
    "医药": ["创新药", "CXO", "生物药", "疫苗", "GLP-1", "减肥药"],
    "消费": ["消费", "零售", "电商", "餐饮", "旅游"],
    "白酒消费": ["白酒", "烈酒", "茅台", "五粮液", "泸州老窖"],
    "通信/5G": ["5G", "基站", "光模块", "光纤", "通信设备"],
    "通信/光模块": ["光模块", "CPO", "800G", "1.6T", "硅光"],
    "周期/资源": ["周期", "资源", "钢铁", "建材", "化工"],
    "金融": ["银行", "保险", "信托", "非银金融"],
    "券商": ["证券", "券商", "投行"],
    "宽基": ["沪深300", "中证500", "中证A500", "上证50", "创业板指"],
    "红利/价值": ["高股息", "红利", "价值", "防御"],
    "红利+低波": ["低波动", "红利低波"],
    "贵金属": ["黄金", "白银", "贵金属"],
    "能源化工": ["石油", "原油", "化工", "石化"],
    "家电": ["空调", "冰箱", "白电", "黑电", "智能家居"],
    "汽车": ["整车", "零部件", "智能驾驶", "自动驾驶"],
    "港股科技": ["港股科技", "恒生科技", "腾讯", "阿里", "美团"],
    "中概互联网": ["中概", "中概股", "互联网"],
    "硬科技": ["硬科技", "半导体", "芯片", "量子"],
    "机器人/智造": ["机器人", "智能制造", "工业自动化", "人形机器人"],
    "云计算/算力": ["云计算", "IDC", "数据中心", "服务器"],
    "中药": ["中药", "中成药", "同仁堂", "片仔癀"],
    "医药器械": ["医疗器械", "医疗设备", "影像"],
    "港股医药": ["港股医药", "港股生物科技"],
    "农产品": ["农业", "种业", "猪肉", "养殖"],
    "利率债": ["国债", "地方债", "利率债", "债券"],
    "信用债": ["信用债", "公司债", "企业债"],
    "可转债": ["可转债", "转债"],
    "保险": ["保险", "寿险", "财险"],
    "美股科技": ["美股科技", "纳斯达克", "纳指"],
    "美股综合": ["标普", "道琼斯", "美股"],
    "美股杠杆": ["杠杆", "反向"],
    "跨境": ["QDII", "跨境", "港股通"],
    "港股综合": ["港股", "恒生"],
    "大盘蓝筹": ["蓝筹", "权重", "大盘"],
    "小盘价值": ["小盘", "微盘"],
    "成长股": ["成长", "成长股"],
    "中盘成长": ["中盘"],
    "全市场": ["全市场", "市场"],
    "综合": ["综合"],
    "其他": ["其他"],
}


def normalize_sector(sector: str) -> str:
    """将 sector 名称归一化到标准名称。"""
    if sector in SECTOR_ALIASES:
        return sector
    for standard, aliases in SECTOR_ALIASES.items():
        for alias in aliases:
            if alias in sector or sector in alias:
                return standard
    return sector


# ──────────────────────────────────────────────────────────────────────
# 核心检测引擎
# ──────────────────────────────────────────────────────────────────────

def _score_match(text: str, keywords: list[str], negation_window: int = 5) -> tuple[float, list[str]]:
    """计算文本与关键词列表的匹配分数。

    Returns:
        (confidence, matched_keywords)
    """
    text_lower = text.lower()
    matched = []
    score = 0.0

    for kw in keywords:
        kw_lower = kw.lower()
        if kw_lower in text_lower:
            matched.append(kw)
            # 基础分 = 1.0 / num_keywords，越稀有权重越高
            score += 1.0 / max(len(keywords), 1)

    if not matched:
        return 0.0, []

    # 短关键词惩罚：1-2字符的关键词权重减半，减少误匹配
    # FIX 2026-08-01: penalty was ×0.5 per short keyword — with regulation-style
    # keyword lists full of 2-char terms (监管/立案/违规/调查), 2 hits dropped
    # confidence below the 0.15 detection threshold. Relax to ×0.8 so legitimate
    # 2-char events are still detected while 1-char false positives stay damped.
    short_penalty = 1.0
    for kw in matched:
        if len(kw) <= 1:
            short_penalty *= 0.5
        elif len(kw) == 2:
            short_penalty *= 0.8
    score *= short_penalty

    # 归一化到 [0, 1]
    confidence = min(score * len(keywords) / max(len(matched), 1), 1.0)

    # 否定词检测
    if _has_negation_nearby(text, matched, negation_window):
        confidence *= 0.5  # 有否定词时降权

    return confidence, matched


def _has_negation_nearby(text: str, matched_keywords: list[str], window: int = 5) -> bool:
    """检查匹配关键词附近是否有否定词。"""
    text_lower = text.lower()
    for kw in matched_keywords:
        kw_pos = text_lower.find(kw.lower())
        if kw_pos < 0:
            continue
        # 检查关键词前后 window 个字符范围内是否有否定词
        start = max(0, kw_pos - window * 3)
        end = min(len(text), kw_pos + len(kw) + window * 3)
        context = text[start:end].lower()
        for neg in NEGATION_WORDS:
            if neg in context:
                return True
    return False


def detect_events(
    text: str,
    source: str = "",
    timestamp: float | None = None,
) -> list[EventSignal]:
    """从单条文本中检测所有匹配的事件信号。

    Args:
        text: 新闻标题或摘要文本
        source: 新闻来源标识
        timestamp: 时间戳 (Unix epoch)，默认当前时间

    Returns:
        EventSignal 列表，按置信度降序排列
    """
    if not text or not text.strip():
        return []

    results: list[EventSignal] = []
    ts = timestamp or time.time()

    for event_type, sub_types in EVENT_DICTIONARIES.items():
        for sub_type, config in sub_types.items():
            keywords = config["keywords"]
            conf, matched = _score_match(text, keywords)

            if conf < 0.15:  # 阈值过滤
                continue

            sentiment = config["sentiment"]
            # 如果命中否定词，反转 sentiment
            if _has_negation_nearby(text, matched):
                sentiment = -sentiment * 0.6  # 部分反转

            # 生成去重ID
            kw_hash = hash(tuple(sorted(matched))) % (10**8)
            event_id = f"{event_type}:{sub_type}:{kw_hash}"

            signal = EventSignal(
                event_type=event_type,
                sub_type=sub_type,
                sentiment=sentiment,
                confidence=round(conf, 3),
                urgency=config["urgency"],
                sectors=list(config["sectors"]),
                keywords_matched=matched,
                raw_text=text[:100],
                event_id=event_id,
            )
            results.append(signal)

    # 按置信度降序
    results.sort(key=lambda s: s.confidence, reverse=True)
    return results


def deduplicate_events(events: list[EventSignal], similarity_threshold: float = 0.8) -> list[EventSignal]:
    """简单去重：相同 event_type + sub_type + 高度重叠 keywords 的事件只保留最高置信度的。"""
    seen: dict[str, EventSignal] = {}
    for ev in events:
        key = f"{ev.event_type}:{ev.sub_type}"
        if key not in seen or ev.confidence > seen[key].confidence:
            seen[key] = ev
    return list(seen.values())


# ──────────────────────────────────────────────────────────────────────
# 行业映射
# ──────────────────────────────────────────────────────────────────────

def map_to_etf_sectors(
    events: list[EventSignal],
    sector_to_etfs: dict[str, list[str]] | None = None,
) -> list[SectorSignal]:
    """将事件信号映射到ETF行业，聚合信号强度。

    Args:
        events: 检测到的事件信号列表
        sector_to_etfs: sector → [etf_codes] 映射，None则自动加载

    Returns:
        SectorSignal 列表，按 signal_strength 绝对值降序
    """
    if sector_to_etfs is None:
        sector_to_etfs = _load_sector_to_etfs()

    # 聚合: sector → {strength_sum, count, codes, titles}
    agg: dict[str, dict[str, Any]] = {}

    for ev in events:
        for sector in ev.sectors:
            norm_sector = normalize_sector(sector)
            if norm_sector not in agg:
                agg[norm_sector] = {
                    "strength_sum": 0.0,
                    "count": 0,
                    "codes": set(),
                    "titles": [],
                }
            agg[norm_sector]["strength_sum"] += ev.sentiment * ev.confidence
            agg[norm_sector]["count"] += 1
            agg[norm_sector]["titles"].append(ev.raw_text[:60])

    # 构建 SectorSignal
    signals: list[SectorSignal] = []
    for sector, data in agg.items():
        strength = data["strength_sum"] / max(data["count"], 1)
        strength = max(-1.0, min(1.0, strength))

        # 方向判断
        if strength > 0.1:
            direction = "LONG"
        elif strength < -0.1:
            direction = "SHORT"
        else:
            direction = "NEUTRAL"

        # 获取该行业的ETF代码
        etf_codes = sector_to_etfs.get(sector, [])

        sig = SectorSignal(
            sector=sector,
            etf_codes=etf_codes,
            signal_strength=round(strength, 3),
            direction=direction,
            event_count=data["count"],
            event_titles=data["titles"][:3],  # 最多保留3个事件摘要
        )
        signals.append(sig)

    # 按 signal_strength 绝对值排序
    signals.sort(key=lambda s: abs(s.signal_strength), reverse=True)
    return signals


# ──────────────────────────────────────────────────────────────────────
# 批量处理 & 输出
# ──────────────────────────────────────────────────────────────────────

def process_news_batch(
    texts: list[str],
    sources: list[str] | None = None,
) -> dict[str, Any]:
    """批量处理新闻文本，返回完整分析结果。

    Args:
        texts: 新闻标题/摘要列表
        sources: 对应来源列表，与texts等长

    Returns:
        包含 events, sector_signals, summary 的字典
    """
    src_list = sources or [""] * len(texts)
    all_events: list[EventSignal] = []

    for text, source in zip(texts, src_list):
        events = detect_events(text, source=source)
        all_events.extend(events)

    # 去重
    unique_events = deduplicate_events(all_events)

    # 映射到行业
    sector_signals = map_to_etf_sectors(unique_events)

    return {
        "events": [e.to_dict() for e in unique_events],
        "sector_signals": [s.to_dict() for s in sector_signals],
        "summary": {
            "total_raw": len(texts),
            "total_events_detected": len(unique_events),
            "total_sectors_affected": len(sector_signals),
            "long_signals": sum(1 for s in sector_signals if s.direction == "LONG"),
            "short_signals": sum(1 for s in sector_signals if s.direction == "SHORT"),
            "neutral_signals": sum(1 for s in sector_signals if s.direction == "NEUTRAL"),
            "timestamp": datetime.now().isoformat(),
        },
    }


def save_signals(results: dict[str, Any], output_path: str | Path) -> None:
    """将结果保存到JSON文件。"""
    path = Path(output_path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"  已保存至: {path}")


# ──────────────────────────────────────────────────────────────────────
# 新闻采集 (可选，依赖 urllib)
# ──────────────────────────────────────────────────────────────────────

def fetch_wallstreetcn(limit: int = 10) -> list[str]:
    """从华尔街见闻API获取最新新闻标题。"""
    try:
        import urllib.request
        import urllib.error
        url = ("https://api-one.wallstcn.com/apiv1/content/information-flow?"
               "channel=global-channel&accept=article&limit={}".format(limit))
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://wallstreetcn.com/",
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        titles = []
        for item in data.get("data", {}).get("items", []):
            res = item.get("resource", {})
            title = res.get("title") or res.get("content_short", "")
            if title:
                titles.append(title)
        return titles
    except (OSError, json.JSONDecodeError, ValueError, KeyError, AttributeError) as e:
        print(f"  华尔街见闻API获取失败: {e}", file=sys.stderr)
        return []


def fetch_sina_finance(limit: int = 10) -> list[str]:
    """从新浪财经获取新闻。"""
    try:
        import urllib.request
        url = "https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2509&num={}".format(limit * 2)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        titles = []
        for item in data.get("result", {}).get("data", []):
            title = item.get("title", "")
            if title:
                titles.append(title)
        return titles
    except (OSError, json.JSONDecodeError, ValueError, KeyError, AttributeError) as e:
        print(f"  新浪财经获取失败: {e}", file=sys.stderr)
        return []


# ──────────────────────────────────────────────────────────────────────
# Demo 模式
# ──────────────────────────────────────────────────────────────────────

DEMO_NEWS: list[tuple[str, str]] = [
    # (标题, 来源)
    (
        "央行宣布降准0.5个百分点，释放长期资金约1万亿元，支持实体经济",
        "央行",
    ),
    (
        "美国BIS将30家中国科技企业列入实体清单，限制高端芯片出口",
        "路透社",
    ),
    (
        "比亚迪Q2净利润预增120%，新能源汽车销量再创新高",
        "财联社",
    ),
    (
        "中东局势升级，美军空袭伊朗设施，国际油价飙升4%",
        "新华社",
    ),
    (
        "华为发布新一代AI芯片，算力提升3倍，打破英伟达垄断",
        "36氪",
    ),
    (
        "北向资金今日净流入180亿元，创近半年新高",
        "东方财富",
    ),
    (
        "光伏组件价格触底反弹，隆基、通威宣布提价5%",
        "证券时报",
    ),
    (
        "证监会严查财务造假，多家上市公司被立案调查",
        "证监会",
    ),
    (
        "美联储暗示9月可能降息，全球流动性预期改善",
        "彭博社",
    ),
    (
        "生猪价格连续上涨8周，养殖企业盈利改善",
        "农业农村部",
    ),
]


def run_demo() -> None:
    """运行完整的检测→映射→输出演示流程。"""
    print("=" * 70)
    print("  事件检测系统 Demo")
    print("=" * 70)

    # Step 1: 检测事件
    print("\n[1/3] 事件检测 — 分析 {} 条新闻".format(len(DEMO_NEWS)))
    print("-" * 50)

    all_events: list[EventSignal] = []
    for title, source in DEMO_NEWS:
        events = detect_events(title, source=source)
        if events:
            for ev in events:
                ev.raw_text = title  # 用完整标题
                all_events.append(ev)

    # 去重
    unique_events = deduplicate_events(all_events)
    print(f"\n  检测到 {len(unique_events)} 个独立事件信号")

    # 打印每个事件
    for i, ev in enumerate(unique_events, 1):
        sent_label = "🟢利好" if ev.sentiment > 0.1 else ("🔴利空" if ev.sentiment < -0.1 else "🟡中性")
        print(f"\n  [{i}] {sent_label} {ev.event_type}/{ev.sub_type}")
        print(f"      文本: {ev.raw_text[:60]}")
        print(f"      置信度: {ev.confidence:.2f}  情感: {ev.sentiment:+.2f}")
        print(f"      时效: {ev.urgency}  关键词: {', '.join(ev.keywords_matched[:3])}")
        print(f"      影响行业: {', '.join(ev.sectors[:4])}")

    # Step 2: 映射到ETF行业
    print("\n\n[2/3] 行业映射 — 关联ETF代码")
    print("-" * 50)

    sector_signals = map_to_etf_sectors(unique_events)
    print(f"\n  影响 {len(sector_signals)} 个行业板块")

    for sig in sector_signals[:15]:  # 最多显示15个
        dir_icon = {"LONG": "📈", "SHORT": "📉", "NEUTRAL": "➡️"}.get(sig.direction, "?")
        etf_preview = sig.etf_codes[:3] if sig.etf_codes else ["(暂无ETF)"]
        print(f"\n  {dir_icon} {sig.sector} (强度: {sig.signal_strength:+.3f}, 事件数: {sig.event_count})")
        print(f"      ETF示例: {', '.join(etf_preview)}")
        if sig.event_titles:
            print(f"      事件: {sig.event_titles[0][:50]}")

    # Step 3: 输出JSON
    print("\n\n[3/3] 输出结果")
    print("-" * 50)

    results = {
        "events": [e.to_dict() for e in unique_events],
        "sector_signals": [s.to_dict() for s in sector_signals],
        "summary": {
            "total_raw": len(DEMO_NEWS),
            "total_events_detected": len(unique_events),
            "total_sectors_affected": len(sector_signals),
            "long_signals": sum(1 for s in sector_signals if s.direction == "LONG"),
            "short_signals": sum(1 for s in sector_signals if s.direction == "SHORT"),
            "neutral_signals": sum(1 for s in sector_signals if s.direction == "NEUTRAL"),
            "timestamp": datetime.now().isoformat(),
        },
    }

    # 保存到文件
    base = Path(__file__).resolve().parent.parent.parent.parent
    out_path = base / "data" / "event_signals.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    save_signals(results, out_path)

    # 打印摘要
    print(f"\n  新闻总数: {results['summary']['total_raw']}")
    print(f"  事件信号: {results['summary']['total_events_detected']}")
    print(f"  影响板块: {results['summary']['total_sectors_affected']}")
    print(f"    📈 LONG: {results['summary']['long_signals']}")
    print(f"    📉 SHORT: {results['summary']['short_signals']}")
    print(f"    ➡️ NEUTRAL: {results['summary']['neutral_signals']}")

    # 输出兼容 signals.py 的信号列表
    print("\n  === 兼容 signals.py 的 Signal 列表 ===")
    compatible_signals = []
    for sig in sector_signals:
        if abs(sig.signal_strength) < 0.05:
            continue
        compatible_signals.append({
            "code": sig.etf_codes[0] if sig.etf_codes else "",
            "name": sig.sector,
            "sector": sig.sector,
            "direction": sig.direction,
            "strength": round(abs(sig.signal_strength), 4),
            "freshness": 0.95,
            "event": "; ".join(sig.event_titles[:2]),
            "impact": round(abs(sig.signal_strength), 4),
        })
    compatible_signals.sort(key=lambda x: x["strength"], reverse=True)

    for cs in compatible_signals[:10]:
        print(f"    {cs['direction']:>6}  {cs['code']:>8}  {cs['name']:<15}  "
              f"strength={cs['strength']:.4f}  event={cs['event'][:40]}")

    print(f"\n  共 {len(compatible_signals)} 个有效信号可接入预测引擎")
    print("=" * 70)


# ──────────────────────────────────────────────────────────────────────
# MetaPredictor 桥接接口
# ──────────────────────────────────────────────────────────────────────

def get_sector_signals(use_cache: bool = True, cache_ttl_seconds: int = 1800) -> list[dict]:
    """MetaPredictor 标准接口: 返回可接入预测引擎的行业信号列表。

    每个信号 dict 格式:
        {code, name, sector, score, direction, event}

    数据源优先级: 华尔街见闻实时 → 新浪财经 → 30分钟缓存 → 空列表
    """
    cache_path = Path(__file__).resolve().parent.parent.parent.parent / "data" / "event_signals_live.json"

    # Check cache first
    if use_cache and cache_path.exists():
        try:
            cache_age = time.time() - cache_path.stat().st_mtime
            if cache_age < cache_ttl_seconds:
                with open(cache_path, encoding="utf-8") as f:
                    cached = json.load(f)
                sector_signals = cached.get("sector_signals", [])
                if sector_signals:
                    predictions = _signals_to_predictions(sector_signals)
                    return predictions
        except (OSError, json.JSONDecodeError, ValueError, KeyError, AttributeError) as e:
                logger.debug(f"[event_nlp] sector fetch failed: {e}")

    sector_signals = []
    try:
        texts = fetch_wallstreetcn(limit=20)
        if not texts:
            texts = fetch_sina_finance(limit=20)
        if texts:
            results = process_news_batch(texts)
            sector_signals = results.get("sector_signals", [])
            # Save to cache
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
    except (OSError, json.JSONDecodeError, ValueError, KeyError, AttributeError, ImportError):
        # Fallback to old cache
        old_cache = Path(__file__).resolve().parent.parent.parent.parent / "data" / "event_signals.json"
        if old_cache.exists():
            try:
                with open(old_cache, encoding="utf-8") as f:
                    cached = json.load(f)
                sector_signals = cached.get("sector_signals", [])
            except (OSError, json.JSONDecodeError, ValueError, KeyError, AttributeError) as e:
                logger.debug(f"[l9_signals] cache read failed: {e}")

    return _signals_to_predictions(sector_signals)


def _signals_to_predictions(sector_signals: list[dict]) -> list[dict]:
    """Convert sector_signals to MetaPredictor prediction format."""
    predictions: list[dict] = []
    for sig in sector_signals:
        if abs(sig.get("signal_strength", 0)) < 0.05:
            continue
        etf_codes = sig.get("etf_codes", [])
        code = etf_codes[0] if etf_codes else ""
        score = 50 + sig.get("signal_strength", 0) * 40
        predictions.append({
            "code": code,
            "name": sig.get("sector", ""),
            "sector": sig.get("sector", ""),
            "score": round(max(5, min(95, score)), 1),
            "source": "event_nlp",
            "direction": sig.get("direction", "NEUTRAL"),
            "event_count": sig.get("event_count", 0),
        })
    predictions.sort(key=lambda x: -x["score"])
    return predictions


# ──────────────────────────────────────────────────────────────────────
# CLI 入口
# ──────────────────────────────────────────────────────────────────────

def main() -> None:
    """CLI 入口: --demo | --source <name> [--limit N]"""
    args = sys.argv[1:]

    if "--demo" in args:
        run_demo()
        return

    # 实时模式: 从新闻源获取数据
    source_name = "wallstreetcn"
    limit = 10
    for i, arg in enumerate(args):
        if arg == "--source" and i + 1 < len(args):
            source_name = args[i + 1]
        elif arg == "--limit" and i + 1 < len(args):
            limit = int(args[i + 1])

    print(f"从 {source_name} 获取 {limit} 条新闻...")

    if source_name == "wallstreetcn":
        texts = fetch_wallstreetcn(limit)
    elif source_name == "sina":
        texts = fetch_sina_finance(limit)
    else:
        texts = fetch_wallstreetcn(limit)

    if not texts:
        print("未能获取新闻，切换到 demo 模式")
        run_demo()
        return

    print(f"获取到 {len(texts)} 条新闻，开始检测...")

    results = process_news_batch(texts)

    print(f"\n检测到 {results['summary']['total_events_detected']} 个事件信号")
    print(f"影响 {results['summary']['total_sectors_affected']} 个行业")

    base = Path(__file__).resolve().parent.parent.parent.parent
    out_path = base / "data" / "event_signals_live.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    save_signals(results, out_path)


if __name__ == "__main__":
    main()
