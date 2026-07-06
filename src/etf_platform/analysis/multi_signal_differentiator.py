"""
multi_signal_differentiator.py — 多维度ETF级评分差异化引擎 v2.0
================================================================
替代旧的fee+type单一微调(±0.3)，用5维信号做同sector ETF的精细区分。

v2.0: 扩大信号幅度 (原版幅度太弱，同fee ETF几乎无区分)
  - fee幅度从 ±0.5 → ±0.8
  - type幅度从 ±0.3 → ±0.6  
  - border幅度从 ±0.4 → ±0.6
  - 加权后最小差异化提升到 ±0.2

设计目标:
- 同一sector+同一risk_level的ETF，composite差异≥0.2
- 每维度信号独立计算，最后加权合并
- 所有调整在±1.5范围内，钳制到±1.0
"""
from typing import Dict, Any


def _calc_fee_tier(fee: float) -> float:
    """费率梯度: 越低越好 (低费=机构认可=加分)
    fee: 0.0003~0.008, 返回 -0.5 ~ +0.8
    """
    if fee <= 0.0003:
        return 0.8
    elif fee <= 0.0005:
        return 0.6
    elif fee <= 0.0008:
        return 0.4
    elif fee <= 0.0015:
        return 0.2
    elif fee <= 0.002:
        return 0.0
    elif fee <= 0.003:
        return -0.2
    elif fee <= 0.005:
        return -0.3
    elif fee <= 0.008:
        return -0.5
    else:
        return -0.5


def _calc_type_breadth(etf_type: str) -> float:
    """类型因子: 策略/宽基=加分(稳健), 行业窄基=中性, 商品/跨境=微负
    返回 -0.3 ~ +0.6
    """
    if not etf_type:
        return 0.0
    # 策略型 = 主动管理/smart-beta = 加分 (超额收益潜力)
    if "策略" in etf_type:
        return 0.6
    # 宽基 = 分散化好 = 加分
    if any(k in etf_type for k in ["宽基", "全市场"]):
        return 0.5
    # 指数型 = 分散化 = 微正
    if "指数" in etf_type:
        return 0.3
    # 纯行业型 = 中性 (集中暴露)
    if "行业" in etf_type:
        return 0.0
    # 货币/债券 = 非权益 = 小扣分
    if any(k in etf_type for k in ["货币", "债券", "利率"]):
        return -0.2
    # QDII = 减分 (额外费用+汇率风险)
    if "QDII" in etf_type:
        return -0.3
    # 商品型
    if "商品" in etf_type:
        return -0.1
    return 0.1


def _calc_cross_border(sector: str, name: str) -> float:
    """跨境因子: 纯内资=加分, 含港=微扣, QDII/QDII=减分
    返回 -0.5 ~ +0.5
    """
    combined = f"{sector} {name}"
    
    # A股纯内资 = 无跨境风险 = 最大加分
    if any(k in combined for k in ["A股", "沪深", "中证", "科创50", "创业板"]):
        return 0.5
    
    # 纯内地行业 (不包含"港"、"美"等跨境字样)
    pure_cn_keywords = ["红利", "银行", "券商", "基建", "军工", "白酒",
                         "消费", "医药", "新能源", "芯片", "光伏", "煤炭",
                         "钢铁", "化工", "有色", "通信", "机器人", "家电"]
    has_pure_cn = any(k in sector for k in pure_cn_keywords)
    has_cross = any(k in combined for k in ["港股", "恒生", "美", "QDII",
                                              "纳指", "标普", "日经"])
    
    if has_pure_cn and not has_cross:
        return 0.4
    elif has_pure_cn and has_cross:
        return -0.1
    
    # 含港股
    if any(k in combined for k in ["港股", "恒生", "H股", "港"]):
        return -0.2
    # 中概 = 跨境上市 = 减分
    if "中概" in combined:
        return -0.3
    # QDII海外市场
    if any(k in combined for k in ["纳指", "标普", "QDII", "美元", "美股",
                                     "日经", "德国", "法国", "越南", "印度"]):
        return -0.5
    # 黄金/商品 = 全球定价
    if any(k in combined for k in ["黄金", "原油", "商品"]):
        return -0.2
    
    # 默认: 含"沪深"等的不在上面的 -> 算A股
    if any(k in combined for k in ["沪深", "中证", "上证", "深圳"]):
        return 0.3
    return 0.0


def _calc_leverage_penalty(leverage: float, sector: str, name: str) -> float:
    """杠杆/做空惩罚: 杠杆越高=风险越大=扣分
    返回 -1.0 ~ 0
    """
    combined = f"{sector} {name}"
    if any(k in combined for k in ["做空", "反向"]):
        return -0.8
    if any(k in combined for k in ["两倍", "三倍", "杠杆"]):
        return -0.6
    if leverage and leverage > 1.0:
        return -0.5 * min(leverage, 3.0) / 3.0
    return 0.0


def _calc_sector_purity(sector: str, name: str) -> float:
    """行业纯正度: 纯正行业=加分, 综合/混合=减分
    返回 -0.4 ~ +0.5
    """
    combined = f"{sector} {name}"
    
    # 综合/宽基 = 分散但无聚焦 = 微负
    if sector in ["综合", "全市场", "宽基"]:
        return -0.3
    if sector == "其他":
        return -0.4
    
    # 纯正行业 (正面的)
    pure_sectors = ["半导体", "芯片", "新能源", "光伏", "医药", "军工",
                     "白酒", "消费", "银行", "券商", "黄金", "煤炭",
                     "有色", "钢铁", "化工", "计算机", "AI", "算力",
                     "机器人", "家电", "红利", "公用事业", "地产"]
    for ps in pure_sectors:
        if ps in sector:
            # 纯正单行业 = 分析确定性高
            return 0.5 if "/" not in sector else 0.3
    
    # 混合性行业 (如 "周期/资源" 跨品种)
    if "/" in sector or "&" in sector:
        return -0.1
    return 0.0


def differentiate(
    code: str,
    sector: str,
    scores: Dict[str, float],
    etf_info: Dict[str, Any],
) -> Dict[str, float]:
    """
    主入口: 对已有layer_scores做ETF级多信号微调。

    v2.0: 信号幅度放大，加权后最小值差异化±0.2
    """
    if not scores:
        return scores

    name = etf_info.get("name", code)
    fee = etf_info.get("fee", 0.005)
    etf_type = etf_info.get("type", "")
    leverage = etf_info.get("leverage", 1.0)

    # 1. 计算5维信号
    fee_signal = _calc_fee_tier(fee)
    type_signal = _calc_type_breadth(etf_type)
    border_signal = _calc_cross_border(sector, name)
    lev_signal = _calc_leverage_penalty(leverage, sector, name)
    purity_signal = _calc_sector_purity(sector, name)

    # 2. 加权合并
    # v2.0: 权重更均衡, type+border 占大头
    combined = (
        fee_signal * 0.20
        + type_signal * 0.25
        + border_signal * 0.25
        + lev_signal * 0.10
        + purity_signal * 0.20
    )
    combined = max(-1.0, min(1.0, round(combined, 2)))

    # 3. 应用到 L3-L7 层
    layer_multipliers = {
        "L3_Material": 1.0,
        "L4_SupplyChain": 0.9,
        "L5_Tech": 0.6,
        "L6_Politics": 1.0,
        "L7_Irreplaceable": 0.5,
    }
    for layer, mult in layer_multipliers.items():
        if layer in scores:
            adj = combined * mult
            scores[layer] = round(max(1.0, min(10.0, scores[layer] + adj)), 1)

    # 4. L8/L9 轻微调整
    if "L8_CapitalFlow" in scores:
        l8_adj = (fee_signal * 0.2 + type_signal * 0.15 + border_signal * 0.2) * 0.5
        scores["L8_CapitalFlow"] = round(
            max(1.0, min(10.0, scores["L8_CapitalFlow"] + l8_adj)), 1
        )
    if "L9_Signals" in scores:
        l9_adj = (type_signal * 0.2 + purity_signal * 0.2) * 0.5
        scores["L9_Signals"] = round(
            max(1.0, min(10.0, scores["L9_Signals"] + l9_adj)), 1
        )

    return scores
