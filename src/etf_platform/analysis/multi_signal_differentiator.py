"""
multi_signal_differentiator.py — 多维度ETF级评分差异化引擎 v2.1
================================================================
v2.1: 新增第6维 IndexType信号 — 按跟踪指数类型/子分类做区分。
  宽基ETF按指数(沪深300/中证500/创业板/科创50)区分
  综合ETF按name关键词(红利/价值/成长/央企)拆分子类
  AI/科技按细分赛道(算力/芯片/云计算)区分
  跨境按市场(美股/港股/欧股/新兴)区分
"""
from typing import Dict, Any


def _calc_fee_tier(fee: float) -> float:
    """费率梯度: 越低越好。 fee: 0.0003~0.008, 返回 -0.5 ~ +0.8"""
    if fee <= 0.0003: return 0.8
    elif fee <= 0.0005: return 0.6
    elif fee <= 0.0008: return 0.4
    elif fee <= 0.0015: return 0.2
    elif fee <= 0.002: return 0.0
    elif fee <= 0.003: return -0.2
    elif fee <= 0.005: return -0.3
    elif fee <= 0.008: return -0.5
    else: return -0.5


def _calc_type_breadth(etf_type: str) -> float:
    """类型因子: 策略/宽基=加分, 行业=中性, 货币/债券=微扣"""
    if not etf_type: return 0.0
    if "策略" in etf_type: return 0.6
    if any(k in etf_type for k in ["宽基", "全市场"]): return 0.5
    if "指数" in etf_type: return 0.3
    if "行业" in etf_type: return 0.0
    if any(k in etf_type for k in ["货币", "债券", "利率"]): return -0.2
    if "QDII" in etf_type: return -0.3
    if "商品" in etf_type: return -0.1
    return 0.1


def _calc_cross_border(sector: str, name: str) -> float:
    """跨境因子: 纯内资=加分, 含港=微扣, QDII=减分"""
    combined = f"{sector} {name}"
    if any(k in combined for k in ["A股", "沪深", "中证", "科创50", "创业板"]): return 0.5
    pure_cn_keywords = ["红利", "银行", "券商", "基建", "军工", "白酒",
                         "消费", "医药", "新能源", "芯片", "光伏", "煤炭",
                         "钢铁", "化工", "有色", "通信", "机器人", "家电"]
    has_pure_cn = any(k in sector for k in pure_cn_keywords)
    has_cross = any(k in combined for k in ["港股", "恒生", "美", "QDII",
                                              "纳指", "标普", "日经"])
    if has_pure_cn and not has_cross: return 0.4
    if has_pure_cn and has_cross: return -0.1
    if any(k in combined for k in ["港股", "恒生", "H股", "港"]): return -0.2
    if "中概" in combined: return -0.3
    if any(k in combined for k in ["纳指", "标普", "QDII", "美元", "美股",
                                     "日经", "德国", "法国", "越南", "印度"]): return -0.5
    if any(k in combined for k in ["黄金", "原油", "商品"]): return -0.2
    if any(k in combined for k in ["沪深", "中证", "上证", "深圳"]): return 0.3
    return 0.0


def _calc_leverage_penalty(leverage: float, sector: str, name: str) -> float:
    """杠杆/做空惩罚"""
    combined = f"{sector} {name}"
    if any(k in combined for k in ["做空", "反向"]): return -0.8
    if any(k in combined for k in ["两倍", "三倍", "杠杆"]): return -0.6
    if leverage and leverage > 1.0: return -0.5 * min(leverage, 3.0) / 3.0
    return 0.0


def _calc_sector_purity(sector: str, name: str) -> float:
    """行业纯正度: 纯正行业=加分, 综合/混合=减分"""
    if sector in ["综合", "全市场", "宽基"]: return -0.3
    if sector == "其他": return -0.4
    pure_sectors = ["半导体", "芯片", "新能源", "光伏", "医药", "军工",
                     "白酒", "消费", "银行", "券商", "黄金", "煤炭",
                     "有色", "钢铁", "化工", "计算机", "AI", "算力",
                     "机器人", "家电", "红利", "公用事业", "地产"]
    for ps in pure_sectors:
        if ps in sector:
            return 0.5 if "/" not in sector else 0.3
    if "/" in sector or "&" in sector: return -0.1
    return 0.0


# ============================================================
# v2.1: Index Type — 数据驱动规则表
# ============================================================

# Rule tuple: (pattern_kind, payload, score, exclude_patterns)
#   pattern_kind:
#     "any"   → any payload word in combined (sector+name)
#     "sector" → any payload word in sector only
#     "__default__" → unconditional fallback
#   exclude_patterns: optional; ALL must be absent from combined to fire.


def _match_rules(rules: tuple, combined: str, sector: str) -> float:
    """按顺序匹配规则列表，返回第一个命中项的 score；无命中返回 0.0。"""
    for kind, payload, score, negs in rules:
        if kind == "__default__":
            return score
        ctx = combined if kind == "any" else sector if kind == "sector" else ""
        matched = any(p in ctx for p in payload)
        if matched and all(n not in combined for n in negs):
            return score
    return 0.0


# Sector keyword → (rule-key, require_composite_in_sector)
_SECTOR_RULE_MAP: dict[str, tuple[str, bool]] = {
    "宽基": ("wide", False),
    "全市场": ("wide", False),
    "综合": ("composite", True),
    "AI": ("aitech", False),
    "科技": ("aitech", False),
    "算力": ("aitech", False),
    "云计算": ("aitech", False),
    "跨境": ("crossborder", False),
    "QDII": ("crossborder", False),
    "周期": ("cyclical", False),
    "资源": ("cyclical", False),
    "新能源": ("newenergy", False),
    "医药": ("pharma", False),
    "医疗": ("pharma", False),
    "药": ("pharma", False),
}

_INDEX_TYPE_RULES: dict[str, tuple] = {
    # ---- 宽基: 按指数区分 ----
    "wide": (
        ("any", ["沪深300", "300", "上证50", "50ETF", "A500", "中证A", "MSCI"], 0.5, ()),
        ("any", ["中证500", "500"], 0.3, ("沪深300", "300")),
        ("any", ["创业板", "创"], -0.1, ()),
        ("any", ["科创", "科创板"], -0.2, ()),
        ("any", ["深证", "深100"], 0.2, ()),
        ("any", ["1000", "中证1000"], 0.0, ()),
        ("any", ["2000"], -0.2, ()),
        ("__default__", (), 0.1, ()),
    ),
    # ---- 综合: 红利/价值/成长/ESG/央企/增强 ----
    "composite": (
        ("any", ["红利"], 0.4, ()),
        ("any", ["价值"], 0.3, ()),
        ("any", ["央企", "国企", "改革", "一带一路"], 0.2, ()),
        ("any", ["ESG", "责任", "可持续"], 0.1, ()),
        ("any", ["成长", "创新"], -0.1, ()),
        ("any", ["增强"], 0.2, ()),
        ("__default__", (), -0.2, ()),
    ),
    # ---- AI/科技: 细分赛道 ----
    "aitech": (
        ("any", ["AI", "人工智能", "大模型", "GPT"], 0.2, ()),
        ("any", ["算力"], -0.1, ()),
        ("any", ["云计算", "云", "数据", "大数据"], 0.1, ()),
        ("any", ["机器人", "自动化", "机器"], 0.0, ()),
        ("any", ["芯片", "半导体", "集成电路"], -0.2, ()),
        ("any", ["软件", "信息", "IT"], 0.1, ()),
        ("__default__", (), 0.0, ()),
    ),
    # ---- 跨境: 按市场 ----
    "crossborder": (
        ("any", ["纳指", "标普", "美股", "科技100"], -0.3, ()),
        ("any", ["恒生", "港股", "H股"], -0.1, ()),
        ("any", ["中概"], -0.2, ()),
        ("any", ["日经", "日本"], -0.2, ()),
        ("any", ["越南", "印度", "新兴"], -0.1, ()),
        ("any", ["德国", "法国", "欧洲", "英国"], -0.2, ()),
        ("__default__", (), -0.2, ()),
    ),
    # ---- 周期/资源: 品种 ----
    "cyclical": (
        ("any", ["黄金"], 0.3, ()),
        ("sector", ["贵金属"], 0.3, ()),
        ("any", ["有色"], -0.1, ()),
        ("any", ["钢铁", "煤炭", "化工"], -0.2, ()),
        ("__default__", (), 0.0, ()),
    ),
    # ---- 新能源: 子赛道 ----
    "newenergy": (
        ("any", ["车", "汽车"], -0.1, ()),
        ("any", ["光伏"], 0.0, ()),
        ("any", ["风", "风电"], 0.1, ()),
        ("any", ["电池"], -0.1, ()),
        ("__default__", (), 0.0, ()),
    ),
    # ---- 医药: 子赛道 ----
    "pharma": (
        ("any", ["创新", "生物"], -0.1, ()),
        ("any", ["中药", "传统"], 0.3, ()),
        ("any", ["器械", "设备"], 0.0, ()),
        ("any", ["服务", "医"], 0.1, ()),
        ("__default__", (), 0.0, ()),
    ),
}


def _calc_index_type(sector: str, name: str) -> float:
    """跟踪指数类型/子分类信号（数据驱动版）。

    对宽基/综合/AI科技/跨境等大类sector，按ETF名称推断其跟踪指数
    或子赛道，做更精细的评分区分。

    Returns: -0.4 ~ +0.5
    """
    entry = next((v for kw, v in _SECTOR_RULE_MAP.items() if kw in sector), None)
    if entry is None:
        return 0.0
    rule_key, need_composite = entry
    if need_composite and "综合" not in sector:
        return 0.0

    return _match_rules(_INDEX_TYPE_RULES[rule_key], f"{sector} {name}", sector)


def differentiate(
    code: str,
    sector: str,
    scores: Dict[str, float],
    etf_info: Dict[str, Any],
) -> Dict[str, float]:
    """
    主入口: 对已有layer_scores做ETF级多信号微调。
    v2.1: 新增第6维 IndexType 信号
    """
    if not scores:
        return scores

    name = etf_info.get("name", code)
    fee = etf_info.get("fee", 0.005)
    etf_type = etf_info.get("type", "")
    leverage = etf_info.get("leverage", 1.0)

    # 1. 计算6维信号
    fee_signal = _calc_fee_tier(fee)
    type_signal = _calc_type_breadth(etf_type)
    border_signal = _calc_cross_border(sector, name)
    lev_signal = _calc_leverage_penalty(leverage, sector, name)
    purity_signal = _calc_sector_purity(sector, name)
    index_signal = _calc_index_type(sector, name)  # v2.1 新增

    # 2. 加权合并 (6维, index占15%)
    combined = (
        fee_signal * 0.15
        + type_signal * 0.20
        + border_signal * 0.20
        + lev_signal * 0.10
        + purity_signal * 0.20
        + index_signal * 0.15
    )
    combined = max(-1.0, min(1.0, round(combined, 2)))

    # 3. 全层应用 (v2.1: 加大倍数覆盖所有层)
    layer_multipliers = {
        "L3_Material": 2.5,
        "L4_SupplyChain": 2.0,
        "L5_Tech": 1.5,
        "L6_Politics": 2.5,
        "L7_Irreplaceable": 1.2,
    }
    for layer, mult in layer_multipliers.items():
        if layer in scores:
            adj = combined * mult
            # Ceiling-aware adjustment — don't let multi_signal undo ceiling_break.
            if scores[layer] >= 8.5:
                adj *= 0.5
            scores[layer] = round(max(1.0, min(10.0, scores[layer] + adj)), 1)

    # L1/L10/L11/L12
    if "L1_ETF" in scores:
        l1_adj = combined * 0.8
        scores["L1_ETF"] = round(max(0.0, min(10.0, scores["L1_ETF"] + l1_adj)), 1)
        if code and code.isdigit():
            digits = code
            h = 0
            for d in digits:
                h = (h * 31 + int(d)) % 10000
            code_jitter = (h / 10000.0 * 2 - 1) * 0.20
            scores["L1_ETF"] = round(max(0.0, min(10.0, scores["L1_ETF"] + code_jitter)), 1)
    if "L10_Demand" in scores:
        l10_adj = combined * 1.0
        if scores["L10_Demand"] >= 8.5:
            l10_adj *= 0.5
        scores["L10_Demand"] = round(max(1.0, min(10.0, scores["L10_Demand"] + l10_adj)), 1)
    if "L11_SectorRisk" in scores:
        l11_adj = combined * 1.0
        if scores["L11_SectorRisk"] >= 8.5:
            l11_adj *= 0.5
        scores["L11_SectorRisk"] = round(max(1.0, min(10.0, scores["L11_SectorRisk"] + l11_adj)), 1)
    if "L12_PoliticalRisk" in scores:
        l12_adj = combined * 0.8
        if scores["L12_PoliticalRisk"] >= 8.5:
            l12_adj *= 0.5
        scores["L12_PoliticalRisk"] = round(max(1.0, min(10.0, scores["L12_PoliticalRisk"] + l12_adj)), 1)
    if "L8_CapitalFlow" in scores:
        l8_adj = (fee_signal * 0.2 + type_signal * 0.15 + border_signal * 0.2) * 0.5
        scores["L8_CapitalFlow"] = round(max(1.0, min(10.0, scores["L8_CapitalFlow"] + l8_adj)), 1)
    if "L9_Signals" in scores:
        l9_adj = combined * 1.5
        if scores["L9_Signals"] >= 8.5:
            l9_adj *= 0.5
        scores["L9_Signals"] = round(max(1.0, min(10.0, scores["L9_Signals"] + l9_adj)), 1)

    return scores
