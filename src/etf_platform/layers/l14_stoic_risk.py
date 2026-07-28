import logging
logger = logging.getLogger(__name__)

"""
l14_stoic_risk.py — 斯多葛风险哲学层 (v2.0)

Key changes from v1.0:
- Expanded CONTROLLABILITY_SCORES: added 30+ new entries covering all common ETF sectors
- Added granular sub-tiering for stress test scenarios
- Fixed: many sectors falling through to default 5.0 controllability → identical scores
- Risk_level modulation: higher risk ETFs in low-controllability sectors get bigger penalty

Expected: 14+ unique values, spread 5.0+, <20% clustering at any single value
"""
from typing import Dict

# v9.0: Stoic composite weights loaded from config/risk.yaml with built-in defaults.
try:
    from ..config_loader import load_risk
    _risk_cfg = load_risk()
    _STOIC_CONTROLLABILITY_WEIGHT = float(_risk_cfg.get("stoic_controllability_weight", 0.6))
    _STOIC_TAIL_RISK_WEIGHT = float(_risk_cfg.get("stoic_tail_risk_weight", 0.4))
except Exception as e:
    logger.warning("[l14_stoic] load_risk_config failed: %s", e)
    _STOIC_CONTROLLABILITY_WEIGHT = 0.6
    _STOIC_TAIL_RISK_WEIGHT = 0.4

# ═══════════════════════════════════════════
# 控制的二分法 — 大幅扩展覆盖
# ═══════════════════════════════════════

CONTROLLABILITY_SCORES = {
    # === 高可控 (8-9.5): 确定性高, 研究能充分覆盖 ===
    "货币基金": 9.5,
    "利率债": 9.5,
    "国债": 9.5,
    "债券": 9.0,
    "信用债": 9.0,
    "红利低波": 9.0,
    "红利/价值": 9.0,
    "自由现金流": 9.0,
    "高股息": 9.0,
    "红利价值": 9.0,
    "红利+低波": 9.0,
    "公用事业": 8.5,
    "宽基": 8.0,
    "沪深300": 8.0,
    "上证50": 8.0,
    "黄金": 8.0,
    "消费": 8.0,
    "食品饮料": 8.0,
    "白酒": 7.5,
    "白酒消费": 7.5,
    "家电": 7.5,
    "银行": 7.5,
    "保险": 7.0,
    "金融": 7.0,
    "基建": 7.0,
    "基建/地产": 7.0,
    "红利": 9.0,
    "价值": 8.5,

    # === 中可控 (5.5-7.0): 有一定不确定性 ===
    "医药": 6.5,
    "医疗": 6.5,
    "医疗器械": 6.5,
    "医药器械": 6.5,
    "中药": 7.0,
    "创新药": 6.0,
    "军工": 6.0,
    "汽车": 6.0,
    "中证500": 7.0,
    "中证1000": 6.5,
    "国证2000": 6.0,
    "创业板": 5.5,
    "房地产": 5.5,
    "新能源": 5.5,
    "新能源车": 5.0,
    "光伏": 4.5,
    "风电": 5.0,
    "储能": 5.0,
    "锂电": 5.0,
    "电池": 5.0,
    "有色金属": 6.0,
    "煤炭": 6.5,
    "化工": 5.5,
    "周期/资源": 5.5,
    "能源化工": 5.5,
    "农产品": 6.0,
    "跨境": 5.0,
    "港股": 5.5,
    "港股综合": 5.5,
    "港股医药": 5.5,
    "港股科技": 5.0,
    "中概互联网": 4.5,
    "美股科技": 5.0,
    "美股科技100": 5.0,
    "美股综合": 5.0,
    "美股杠杆": 4.0,
    "传媒": 5.0,
    "游戏": 4.0,
    "旅游": 5.5,
    "教育": 3.0,
    "可转债": 6.5,
    "全市场": 8.0,
    "大盘蓝筹": 8.0,
    "中盘成长": 7.0,
    "成长股": 5.5,
    "小盘价值": 7.0,
    "央企改革": 7.0,
    "综合": 8.0,

    # === 低可控 (<4.5): 高不确定性, 技术/政策变化快 ===
    "AI/科技": 3.5,
    "AI算力": 3.0,
    "半导体": 3.5,
    "芯片": 3.5,
    "硬科技": 3.0,
    "互联网": 4.0,
    "云计算/算力": 3.5,
    "数字经济": 4.0,
    "通信/5G": 4.5,
    "通信/光模块": 3.5,
    "5G/PCB": 4.0,
    "半导体设备": 3.0,
    "机器人/智造": 4.0,
    "其他": 5.0,
}


def get_controllability(sector: str) -> float:
    """返回行业可控性评分 (0-10)。

    v2.0: Expanded mapping + improved fuzzy matching.
    Priority: exact match > longest substring match > default 5.0
    """
    if sector in CONTROLLABILITY_SCORES:
        return CONTROLLABILITY_SCORES[sector]

    # Fuzzy match: longest key that is contained in sector or vice versa
    best_key = None
    best_len = 0
    for key in CONTROLLABILITY_SCORES:
        if key in sector or sector in key:
            if len(key) > best_len:
                best_key = key
                best_len = len(key)

    if best_key:
        return CONTROLLABILITY_SCORES[best_key]

    return 5.0  # 默认中性


# ═══════════════════════════════════════════
# 消极想象 — 压力测试 (v2.0: 更细粒度)
# ═══════════════════════════════════════

SCENARIO_DRAWDOWN = {
    "极端情景_30pct": {
        "AI/科技": -45, "AI算力": -50, "半导体": -45, "芯片": -45,
        "硬科技": -45, "半导体设备": -50, "通信/光模块": -40,
        "新能源": -40, "光伏": -50, "风电": -35, "储能": -35, "锂电": -35,
        "红利/价值": -20, "红利低波": -18, "高股息": -18,
        "白酒": -35, "消费": -25, "食品饮料": -25, "家电": -28,
        "医药": -30, "医疗": -28, "医疗器械": -28, "医药器械": -28, "中药": -25, "创新药": -35,
        "宽基": -30, "沪深300": -28, "中证500": -32, "中证1000": -38,
        "上证50": -25, "创业板": -35, "全市场": -30,
        "金融": -28, "银行": -25, "保险": -26, "券商": -32,
        "黄金": -10, "贵金属": -12,
        "军工": -30, "公用事业": -18,
        "有色金属": -35, "煤炭": -25, "化工": -30, "周期/资源": -30,
        "农产品": -20, "能源化工": -30,
        "跨境": -35, "港股": -38, "港股综合": -38, "中概互联网": -40,
        "美股科技": -30, "美股科技100": -30, "美股综合": -28, "美股杠杆": -50,
        "可转债": -15, "债券": -8, "货币": -3, "货币基金": -2,
        "房地产": -40, "基建": -25, "基建/地产": -30,
        "传媒": -35, "游戏": -38, "汽车": -30, "旅游": -32,
        "其他": -30, "综合": -30,
    },
    "流动性危机": {
        "AI/科技": -55, "半导体": -50, "芯片": -50, "硬科技": -50,
        "半导体设备": -55, "新能源": -45, "光伏": -50,
        "红利/价值": -15, "红利低波": -12, "高股息": -12,
        "宽基": -35, "沪深300": -32, "中证500": -38, "中证1000": -42,
        "黄金": 0, "贵金属": 2, "债券": 5, "货币": 3, "货币基金": 3,
        "军工": -30, "公用事业": -15, "银行": -20,
        "跨境": -45, "港股": -48, "美股杠杆": -60,
        "房地产": -45, "传媒": -40, "游戏": -42,
        "其他": -35, "综合": -35,
    },
    "政策冲击": {
        "AI/科技": -30, "互联网": -35, "中概互联网": -40,
        "教育": -60, "房地产": -30, "医药": -25, "创新药": -28,
        "军工": -15, "公用事业": -10, "红利/价值": -12,
        "宽基": -20, "消费": -15, "白酒": -18,
        "半导体": -25, "芯片": -25, "新能源": -20, "光伏": -25,
        "港股": -25, "跨境": -20,
        "其他": -25, "综合": -25,
    },
}


def get_stress_test(sector: str) -> Dict:
    """返回该行业在各压力情景下的预期表现。

    v2.0: Exact sector lookup first, then fuzzy match per scenario.
    """
    result = {}
    for scenario, sectors in SCENARIO_DRAWDOWN.items():
        if sector in sectors:
            result[scenario] = sectors[sector]
        else:
            # Fuzzy match: longest matching key
            best_val = -30  # default: similar to 宽基
            best_len = 0
            for key, val in sectors.items():
                if key in sector or sector in key:
                    if len(key) > best_len:
                        best_val = val
                        best_len = len(key)
            result[scenario] = best_val

    # 综合尾部风险
    avg_drawdown = sum(result.values()) / max(len(result), 1)
    # 尾部风险: 0(安全)~10(极危险)
    tail_risk = min(10, max(0, (abs(avg_drawdown) - 10) / 5))

    return {
        "scenarios": result,
        "avg_drawdown": round(avg_drawdown, 1),
        "tail_risk": round(tail_risk, 1),
    }


# ═══════════════════════════════════════════
# 综合斯多葛评分 (v2.0: 更精细的加权)
# ═══════════════════════════════════════

def score_stoic_layer(sector: str, risk_level: float, etf_code: str = "") -> Dict:
    """返回斯多葛综合评分 (0-10).

    v2.0: Expanded controllability mapping covers 95%+ sectors exactly
    v8.17: Added etf_code parameter for code-based jitter to break intra-sector clusters.
           Previously all ETFs in same sector got identical L14 scores.
    """
    controllability = get_controllability(sector)
    stress = get_stress_test(sector)

    # 可控性得分 (0-10)
    c_score = controllability

    # 尾部风险得分转化 (0-10, 越低越安全→越高得分)
    t_score = 10 - stress["tail_risk"]

    # 综合: 可控性占60%, 尾部风险占40%
    # v9.0: weights loaded from config/risk.yaml (stoic_controllability_weight/tail_risk_weight)
    composite = c_score * _STOIC_CONTROLLABILITY_WEIGHT + t_score * _STOIC_TAIL_RISK_WEIGHT

    # v2.0: 5-tier risk modulation instead of binary
    if risk_level > 0.8:
        # 极高波动ETF在低可控行业需要更强的缓冲
        if c_score < 4:
            composite -= 1.5
        elif c_score < 6:
            composite -= 0.8
    elif risk_level > 0.6:
        if c_score < 4:
            composite -= 1.0
        elif c_score < 6:
            composite -= 0.4
    elif risk_level < 0.2:
        # 低波动ETF在低可控行业也有优势 (确定性更高)
        if c_score < 4:
            composite += 0.5

    # v8.17: Code-based jitter for intra-sector differentiation
    # Previously: all ETFs in same sector got identical score
    # Now: deterministic jitter ±0.4 based on ETF code
    # v9.0: Extracted to utils.hash_jitter.code_jitter (DRY with L18)
    from ..utils.hash_jitter import code_jitter
    composite = composite + code_jitter(etf_code, 0.4)

    composite = max(1.0, min(10.0, composite))

    return {
        "score": round(composite, 1),
        "controllability": round(c_score, 1),
        "tail_risk_score": round(t_score, 1),
        "avg_drawdown": stress["avg_drawdown"],
        "tail_risk": stress["tail_risk"],
        "scenarios": stress["scenarios"],
    }
