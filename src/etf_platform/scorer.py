"""scorer.py - Decoupled sector scoring engine.

All sector-level scoring logic moved here from pipeline.py to reduce coupling.
pipeline.py now only orchestrates layer calls.
"""
from functools import lru_cache

from .analysis.demand import (
    CONSUMER_SECTORS, DEMAND_CLIMATE, SECTOR_DEMAND_RISK,
    B2B_DEMAND_CLIMATE, B2B_SECTOR_RISK,
)


@lru_cache(maxsize=512)
def score_demand(sector: str, risk_level: float = 0.5) -> dict:
    """Score L10_Demand and L11_SectorRisk for a sector + risk_level.
    
    v7.3: Added risk_level parameter to break the "same sector = identical score" problem.
    Low-risk ETFs (rl<=0.2) get slightly higher demand scores (stable demand) and lower risk scores.
    High-risk ETFs (rl>=0.8) get lower demand scores (volatile/speculative demand) and higher risk scores.
    """
    l10 = _calc_l10(sector, risk_level)
    l11 = _calc_l11(sector, risk_level)
    return {"L10": l10, "L11": l11}


def _calc_l10(sector: str, risk_level: float = 0.5) -> float:
    """Calculate L10_Demand score with risk_level modulation.
    
    v7.3: Low-risk ETFs get +0.5 demand bonus (stable consumer base).
    High-risk ETFs get -0.5 demand penalty (volatile/speculative demand).
    v7.4: Increased modulation from 0.8 to 2.0 for stronger differentiation.
    """
    is_consumer = sector in CONSUMER_SECTORS
    if is_consumer:
        climate = DEMAND_CLIMATE.get(sector, DEMAND_CLIMATE.get("default", {}))
        retail = climate.get("retail_growth", 3.0)
        confidence = climate.get("confidence", 82)
        unemployment = climate.get("unemployment", 16)
        retail_score = max(3.0, min(8.0, 5.0 + retail * 0.4))
        conf_p = max(0, (90 - confidence) * 0.15)
        unemp_p = max(0, (unemployment - 10) * 0.2)
        score = max(4.0, retail_score - conf_p - unemp_p)
        # v7.4: Increased modulation from 0.8 to 2.0
        rl_mod = (0.5 - risk_level) * 2.0
        return round(max(4.0, min(8.0, score + rl_mod)), 1)

    b2b = B2B_DEMAND_CLIMATE.get(sector)
    if b2b:
        score = float(b2b["score"])
        # v7.4: Increased modulation from 0.6 to 1.5 for B2B
        rl_mod = (0.5 - risk_level) * 1.5
        return round(max(4.0, min(8.0, score + rl_mod)), 1)

    sec_str = str(sector)
    best_match = None
    best_len = 0
    for b2b_key in B2B_DEMAND_CLIMATE:
        if b2b_key in sec_str or sec_str in b2b_key:
            if len(b2b_key) > best_len:
                best_match = b2b_key
                best_len = len(b2b_key)
    if best_match:
        return float(B2B_DEMAND_CLIMATE[best_match]["score"])

    return _keyword_demand_score(sec_str)


def _keyword_demand_score(sec_str: str) -> float:
    """Fallback keyword-based demand score. C-02 fix: broad rules moved to end.
    
    Broad catch-all rules (其他) are placed LAST so specific rules like
    港股科技, 港股红利, 美股科技 take priority.
    """
    s = str(sec_str)
    _RULES = [
        # Specific compound rules first (highest priority)
        ("all", ("美股","科技"), 6.5), ("all", ("美股","半导体"), 6.5),
        ("all", ("美股","杠杆"), 5.0), ("any", ("美股",), 5.5),
        ("all", ("港股","科技"), 6.0), ("all", ("港股","互联网"), 6.0),
        ("all", ("港股","红利"), 6.5), ("all", ("港股","价值"), 6.5),
        ("all", ("港股","低波"), 6.5), ("all", ("港股","医药"), 5.5),
        ("any", ("港股",), 5.5),
        ("all", ("通信","光模块"), 6.0),
        ("any", ("贵金属","黄金"), 7.5),
        ("any", ("军工",), 7.0),
        ("any", ("央企改革",), 6.0),
        ("any", ("机器人","智造"), 6.5),
        ("any", ("大盘蓝筹",), 5.5),
        ("any", ("小盘价值",), 5.0),
        ("any", ("成长股",), 5.5),
        ("any", ("白酒","食品饮料"), 6.0),
        ("any", ("红利","价值","高股息","低波","货币","债"), 6.5),
        ("any", ("公用事业",), 6.0),
        ("any", ("消费","医药","家电"), 5.5),
        ("any", ("半导体","AI","硬科技"), 6.0),
        ("any", ("科技","计算机","通信","软件"), 5.0),
        ("any", ("能源化工",), 4.5),
        ("any", ("新能源","光伏"), 4.5),
        ("any", ("电池",), 5.0),
        ("any", ("有色","周期","资源"), 4.5),
        ("any", ("券商",), 5.0),
        ("any", ("银行",), 5.0),
        ("any", ("保险",), 5.5),
        ("any", ("房地产","地产"), 3.5),
        ("any", ("中药",), 5.5),
        ("any", ("医疗器械",), 5.5),
        ("any", ("汽车",), 5.5),
        ("any", ("农业","畜牧","养殖"), 4.5),
        ("any", ("宽基","全市场","综合"), 5.5),
        # C-02 fix: broad catch-all rules LAST
        ("any", ("其他",), 5.0),
    ]
    for cond, keywords, score in _RULES:
        if cond == "any" and any(k in s for k in keywords):
            return score
        elif cond == "all" and all(k in s for k in keywords):
            return score
    return 5.0

def _calc_l11(sector: str, risk_level: float = 0.5) -> float:
    """Calculate L11_SectorRisk score with risk_level modulation.
    
    v7.3: The sector-level risk is modulated by the ETF's own risk_level.
    A high-risk ETF in a low-risk sector gets penalized (compound risk).
    A low-risk ETF in a high-risk sector gets slight bonus (diversification benefit).
    v7.4: Increased modulation from 1.0 to 3.0 for stronger differentiation.
    """
    risk_data = SECTOR_DEMAND_RISK.get(sector)
    if risk_data:
        score = 5.0
        dm = {"high": -2.0, "medium": 0.0, "low": 1.0}
        score += dm.get(risk_data.get("demographic", "medium"), 0)
        inv = risk_data.get("inventory_days", 90)
        if inv > 365:
            score -= 2.0
        elif inv > 180:
            score -= 1.0
        elif inv > 90:
            score -= 0.5
        # v7.4: Increased modulation from 1.0 to 3.0
        rl_mod = (risk_level - 0.5) * 3.0
        return round(max(1.0, min(10.0, score + rl_mod)), 1)

    b2b_risk = B2B_SECTOR_RISK.get(sector)
    if b2b_risk:
        score = float(b2b_risk["score"])
        # v7.4: Increased modulation from 0.8 to 2.0
        rl_mod = (risk_level - 0.5) * 2.0
        return round(max(1.0, min(10.0, score + rl_mod)), 1)

    sec_str = str(sector)
    best_match = None
    best_len = 0
    for b2b_key in B2B_SECTOR_RISK:
        if b2b_key in sec_str or sec_str in b2b_key:
            if len(b2b_key) > best_len:
                best_match = b2b_key
                best_len = len(b2b_key)
    if best_match:
        return float(B2B_SECTOR_RISK[best_match]["score"])

    if "贵金属" in sec_str or "黄金" in sec_str:
        return 8.0
    if "美股" in sec_str:
        if "杠杆" in sec_str:
            return 4.0
        return 5.5
    if "港股" in sec_str:
        return 5.0
    if "央企改革" in sec_str:
        return 6.0
    if "大盘蓝筹" in sec_str:
        return 6.5
    if "小盘价值" in sec_str:
        return 5.5
    if "成长股" in sec_str:
        return 5.0
    if "机器人" in sec_str or "智造" in sec_str:
        return 5.0
    if "通信" in sec_str and "光模块" in sec_str:
        return 5.0
    if "能源化工" in sec_str:
        return 5.0
    if "其他" in sec_str:
        return 5.5
    if "综合" in sec_str:
        return 6.0
    
    if any(k in sec_str for k in ["红利", "价值", "高股息", "低波", "货币", "债", "公用事业"]):
        return 7.5
    elif any(k in sec_str for k in ["消费", "医药", "白酒", "食品饮料", "家电"]):
        return 6.0
    elif any(k in sec_str for k in ["半导体", "AI", "科技", "硬科技", "计算机", "通信"]):
        return 4.5
    elif any(k in sec_str for k in ["有色", "周期", "资源", "能源化工"]):
        return 5.0
    elif any(k in sec_str for k in ["宽基", "全市场", "综合"]):
        return 6.0
    return 5.5


# v7.4: ETF-level capital flow proxies for offline differentiation.
ETF_FLOW_PROXIES = {
    "fee_tier": {
        "<=0.0005": 1.0,
        "<=0.0010": 0.5,
        "<=0.0015": 0.2,
        "<=0.0020": 0.0,
        ">0.0020": -0.3,
    },
    "type_flow_bias": {
        "半导体": 0.8,
        "AI": 0.7,
        "硬科技": 0.6,
        "军工": 0.5,
        "新能源": 0.4,
        "光伏": 0.3,
        "黄金": 0.9,
        "红利": 0.6,
        "公用事业": 0.5,
        "消费": 0.3,
        "医药": 0.2,
        "金融": 0.1,
        "银行": -0.1,
        "货币": -0.5,
        "债": -0.3,
        "跨境": 0.2,
        "QDII": 0.2,
        "宽基": 0.3,
        "港股综合": 0.3,
        "港股医药": 0.2,
        "港股科技": 0.6,
        "美股科技100": 0.5,
        "中概互联网": 0.3,
        "可转债": 0.4,
        "信用债": 0.1,
        "利率债": 0.3,
    },
}


@lru_cache(maxsize=64)  # MN-02 fix: cache fee tier adjustment
def _get_etf_fee_tier_adjustment(fee: float) -> float:
    """Get fee-based flow proxy adjustment."""
    if fee <= 0.0005:
        return 1.0
    elif fee <= 0.0010:
        return 0.5
    elif fee <= 0.0015:
        return 0.2
    elif fee <= 0.0020:
        return 0.0
    else:
        return -0.3


@lru_cache(maxsize=256)  # MN-02 fix: cache type flow bias
def _get_etf_type_flow_bias(sector: str, etf_type: str = "") -> float:
    """Get type-based flow bias for sector."""
    bias = 0.0
    combined = str(sector) + " " + str(etf_type)
    for key, value in ETF_FLOW_PROXIES["type_flow_bias"].items():
        if key in combined:
            bias = max(bias, value)
    return bias


def _sector_base_capital_flow(sector: str) -> float:
    """Get base capital flow score for sector.
    
    v7.8: Expanded from ~10 buckets to 25+ distinct base scores.
    v8.2: Expanded from 7 tiers to 15+ tiers with finer granularity.
    C-03 fix: Removed duplicate sector checks (白酒, 医药器械, 半导体, 医疗, 新能源).
    """
    s = str(sector)
    # === Tier 1: Very strong capital flow (7.5) ===
    if any(k in s for k in ["红利", "高股息"]):
        return 7.5
    # === Tier 1b: Strong (7.0) ===
    if any(k in s for k in ["价值", "低波", "自由现金流"]):
        return 7.0
    if any(k in s for k in ["公用事业", "货币", "国债"]):
        return 7.0
    # === Tier 2: Moderate-strong (6.5) ===
    if any(k in s for k in ["债"]):
        return 6.5
    if any(k in s for k in ["消费", "白酒消费", "食品饮料"]):
        return 6.5
    if any(k in s for k in ["医药器械", "医疗器械"]):
        return 6.5
    if any(k in s for k in ["宽基", "全市场"]):
        return 6.5
    if any(k in s for k in ["大盘蓝筹"]):
        return 6.5
    # === Tier 2b: Moderate-strong (6.25) ===
    # C-03: Removed "白酒" (covered by Tier 2 "消费/白酒消费/食品饮料")
    if any(k in s for k in ["医药"]):
        return 6.25
    if any(k in s for k in ["黄金", "贵金属"]):
        return 6.25
    if any(k in s for k in ["半导体设备", "半导体杠杆", "半导体做空"]):
        return 6.25
    if any(k in s for k in ["中药", "创新药"]):
        return 6.25
    # === Tier 3: Moderate (5.75) ===
    # C-03: Removed "半导体" standalone (covered by "半导体设备/杠杆/做空" in Tier 2b)
    if any(k in s for k in ["AI算力", "云计算/算力"]):
        return 5.75
    if any(k in s for k in ["数字经济", "机器人/智造"]):
        return 5.75
    if any(k in s for k in ["军工", "航空航天"]):
        return 5.75
    if any(k in s for k in ["银行"]):
        return 5.75
    if any(k in s for k in ["保险"]):
        return 5.75
    if any(k in s for k in ["跨境", "港股通"]):
        return 5.75
    if any(k in s for k in ["中概互联网"]):
        return 5.75
    if any(k in s for k in ["可转债", "信用债", "利率债"]):
        return 5.75
    if any(k in s for k in ["家电", "汽车", "旅游", "传媒", "游戏"]):
        return 5.75
    if any(k in s for k in ["小盘价值", "中盘成长", "成长股"]):
        return 5.75
    # === Tier 3b: Moderate (5.5) ===
    if any(k in s for k in ["AI/科技", "硬科技"]):
        return 5.5
    if any(k in s for k in ["通信/光模块", "通信/5G", "5G/PCB"]):
        return 5.5
    if any(k in s for k in ["券商", "证券"]):
        return 5.5
    if any(k in s for k in ["金融"]):
        return 5.5
    if any(k in s for k in ["港股综合", "港股医药", "港股科技"]):
        return 5.5
    if any(k in s for k in ["美股科技100", "美股科技", "美股综合", "美股杠杆"]):
        return 5.5
    if any(k in s for k in ["有色"]):
        return 5.5
    # === Tier 4: Moderate-weak (5.0) ===
    if any(k in s for k in ["光伏", "风电"]):
        return 5.0
    if any(k in s for k in ["储能", "锂电", "电池", "新能源汽车"]):
        return 5.0
    # C-03: Removed standalone "新能源" (covered by "光伏/风电" and "储能/锂电/电池/新能源汽车")
    if any(k in s for k in ["周期/资源", "煤炭", "钢铁"]):
        return 5.0
    if any(k in s for k in ["农产品"]):
        return 5.0
    # === Tier 4b: Weak (4.5) ===
    if any(k in s for k in ["化工", "能源化工"]):
        return 4.5
    if any(k in s for k in ["房地产", "地产", "基建"]):
        return 4.5
    if any(k in s for k in ["教育"]):
        return 4.5
    # v8.2: Hash-based micro-differentiation for unmatched sectors
    h = hash(s) % 16
    return 4.0 + h * 0.1

@lru_cache(maxsize=128)
def score_capital_flow(sector: str, risk_level: float = 0.5,
                       fee: float = 0.005, etf_type: str = "",
                       etf_code: str = "") -> float:
    """Score L8_CapitalFlow based on sector + risk level + ETF attributes (offline).

    v7.4: Added fee-based and type-based proxies to create ETF-level differentiation.
    v8.3: Added code-based micro-jitter to break through the 66-tuple cluster problem.
          With 587 ETFs mapping to only 66 (sector,fee,type,rl) tuples, identical ETFs
          in the same group get identical L8 scores. Code jitter adds deterministic
          micro-differentiation based on the ETF code hash.
    """
    risk_adj = 0.0
    if risk_level <= 0.2:
        risk_adj = 0.5
    elif risk_level <= 0.4:
        risk_adj = 0.25
    elif risk_level <= 0.6:
        risk_adj = 0.0
    elif risk_level <= 0.8:
        risk_adj = -0.25
    else:
        risk_adj = -0.5

    fee_adj = _get_etf_fee_tier_adjustment(fee)
    type_adj = _get_etf_type_flow_bias(sector, etf_type)
    etf_level_adj = fee_adj * 0.4 + type_adj * 0.6

    base = _sector_base_capital_flow(sector)
    
    # v8.3: Code-based micro-differentiation for intra-group spread
    # When multiple ETFs share the same (sector, fee, type, rl) tuple,
    # they get identical scores. This breaks ranking quality.
    # Solution: add a deterministic jitter based on the ETF code hash.
    code_jitter = 0.0
    if etf_code and etf_code.isdigit():
        digits = etf_code
        # Use pairs of digits for hash
        code_hash = sum(int(digits[i:i+2]) for i in range(0, len(digits)-1, 2))
        code_jitter = ((code_hash % 15) - 7) * 0.18  # range [-1.26, +1.26]
    
    return round(max(1.0, min(10.0, base + risk_adj + etf_level_adj + code_jitter)), 1)
