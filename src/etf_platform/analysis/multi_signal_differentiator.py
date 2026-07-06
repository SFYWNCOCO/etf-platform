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
# v2.1: Index Type — 按跟踪指数/子分类做第6维信号
# ============================================================

def _calc_index_type(sector: str, name: str) -> float:
    """跟踪指数类型/子分类信号。
    
    对宽基/综合/AI科技/跨境等大类sector，按ETF名称推断其跟踪指数
    或子赛道，做更精细的评分区分。
    
    Returns: -0.4 ~ +0.5
    """
    combined = f"{sector} {name}"
    
    # --- 宽基ETF: 按指数区分 ---
    if sector in ("宽基", "全市场"):
        # 大盘蓝筹 (沪深300/上证50/中证A500)
        if any(k in combined for k in ["沪深300", "300", "上证50", "50ETF",
                                         "A500", "中证A", "MSCI"]):
            return 0.5
        # 中盘 (中证500)
        if any(k in combined for k in ["中证500", "500"]):
            # 排除 沪深300 的误匹配 (300 vs 500)
            if "沪深300" not in combined and "300" not in combined:
                return 0.3
        # 创业板 (成长型)
        if any(k in combined for k in ["创业板", "创"]):
            return -0.1
        # 科创50 (硬科技成长)
        if any(k in combined for k in ["科创", "科创板"]):
            return -0.2
        # 深证100/深成指
        if "深证" in combined or "深100" in combined:
            return 0.2
        # 中证1000 (小盘)
        if "1000" in combined or "中证1000" in combined:
            return 0.0
        # 中证2000 (微盘)
        if "2000" in combined:
            return -0.2
        # 其他宽基
        return 0.1
    
    # --- 综合ETF: 按子类型拆分为红利/价值/成长/ESG/央企 ---
    if sector == "综合" or "综合" in sector:
        # 红利综合
        if "红利" in combined:
            return 0.4
        # 价值综合
        if "价值" in combined:
            return 0.3
        # 央企/国企/改革
        if any(k in combined for k in ["央企", "国企", "改革", "一带一路"]):
            return 0.2
        # ESG/责任投资
        if any(k in combined for k in ["ESG", "责任", "可持续"]):
            return 0.1
        # 成长/创新
        if any(k in combined for k in ["成长", "创新"]):
            return -0.1
        # 增强型 (量化增强)
        if "增强" in combined:
            return 0.2
        # 默认综合 (无特征)
        return -0.2
    
    # --- AI/科技: 按细分赛道区分 ---
    if any(k in sector for k in ["AI", "科技", "算力", "云计算"]):
        # AI应用/大模型
        if any(k in combined for k in ["AI", "人工智能", "大模型", "GPT"]):
            return 0.2
        # 算力基础设施 (硬件)
        if "算力" in combined or "算力" in sector:
            return -0.1
        # 云计算/数据
        if any(k in combined for k in ["云计算", "云", "数据", "大数据"]):
            return 0.1
        # 机器人/自动化
        if any(k in combined for k in ["机器人", "自动化", "机器"]):
            return 0.0
        # 硬科技 (含芯片)
        if any(k in combined for k in ["芯片", "半导体", "集成电路"]):
            return -0.2
        # 软件/信息技术
        if any(k in combined for k in ["软件", "信息", "IT"]):
            return 0.1
        return 0.0
    
    # --- 跨境: 按市场区分 ---
    if sector in ("跨境", "QDII") or "跨境" in sector:
        # 美股 (纳指/标普)
        if any(k in combined for k in ["纳指", "标普", "美股", "科技100"]):
            return -0.3
        # 港股 (恒生/国企)
        if any(k in combined for k in ["恒生", "港股", "H股"]):
            return -0.1
        # 中概
        if "中概" in combined:
            return -0.2
        # 日经
        if any(k in combined for k in ["日经", "日本"]):
            return -0.2
        # 新兴市场
        if any(k in combined for k in ["越南", "印度", "新兴"]):
            return -0.1
        # 欧洲
        if any(k in combined for k in ["德国", "法国", "欧洲", "英国"]):
            return -0.2
        return -0.2  # 默认跨境
    
    # --- 周期/资源: 按品种区分 ---
    if "周期" in sector or "资源" in sector:
        # 黄金 = 避险
        if "黄金" in combined or "贵金属" in sector:
            return 0.3
        # 有色 = 工业金属
        if "有色" in combined or "有色" in sector:
            return -0.1
        # 钢铁/煤炭/化工
        if any(k in combined for k in ["钢铁", "煤炭", "化工"]):
            return -0.2
        return 0.0
    
    # --- 新能源: 按子赛道 ---
    if "新能源" in sector:
        if "车" in combined or "汽车" in combined:
            return -0.1
        if "光伏" in combined or "光伏" in sector:
            return 0.0
        if "风" in combined or "风电" in sector:
            return 0.1
        if "电池" in combined or "电池" in sector:
            return -0.1
        return 0.0
    
    # --- 医药: 按子赛道 ---
    if "医药" in sector or "医疗" in sector or "药" in sector:
        if "创新" in combined or "生物" in combined:
            return -0.1
        if "中药" in combined or "传统" in combined:
            return 0.3
        if "器械" in combined or "设备" in combined:
            return 0.0
        if "服务" in combined or "医" in combined:
            return 0.1
        return 0.0
    
    return 0.0


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
    # v2.1: fee 15%, type 20%, border 20%, leverage 10%, purity 20%, index 15%
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
    # 原版: 12层均摊后±0.1差异在composite仅±0.01
    # 修复: L3/L4/L6用2.5x, 同时调L1/L10/L11/L12
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
            scores[layer] = round(max(1.0, min(10.0, scores[layer] + adj)), 1)

    # 全层覆盖: L1/L10/L11/L12
    if "L1_ETF" in scores:
        scores["L1_ETF"] = round(max(0.0, min(10.0, scores["L1_ETF"] + combined * 0.5)), 1)
    if "L10_Demand" in scores:
        scores["L10_Demand"] = round(max(1.0, min(10.0, scores["L10_Demand"] + combined * 1.0)), 1)
    if "L11_SectorRisk" in scores:
        scores["L11_SectorRisk"] = round(max(1.0, min(10.0, scores["L11_SectorRisk"] + combined * 1.0)), 1)
    if "L12_PoliticalRisk" in scores:
        scores["L12_PoliticalRisk"] = round(max(1.0, min(10.0, scores["L12_PoliticalRisk"] + combined * 0.8)), 1)
    if "L8_CapitalFlow" in scores:
        l8_adj = (fee_signal * 0.2 + type_signal * 0.15 + border_signal * 0.2) * 0.5
        scores["L8_CapitalFlow"] = round(max(1.0, min(10.0, scores["L8_CapitalFlow"] + l8_adj)), 1)
    if "L9_Signals" in scores:
        l9_adj = (type_signal * 0.2 + purity_signal * 0.2) * 0.5
        scores["L9_Signals"] = round(max(1.0, min(10.0, scores["L9_Signals"] + l9_adj)), 1)

    return scores
