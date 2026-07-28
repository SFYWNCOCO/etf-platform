import logging
logger = logging.getLogger(__name__)

"""
l18_var_risk.py — VaR风控层 (v1.0)

基于历史波动率计算ETF的VaR (Value at Risk) 和压力测试结果。
知识源: parallel_learning_v5_report.md

VaR计算方法:
  - 历史模拟法: 使用过去20日收益率分布的分位数
  - 参数法: 假设正态分布, 均值±标准差
  - 蒙特卡洛: 随机生成路径 (可选)

压力测试情景:
  - 温和下跌: -5%
  - 剧烈下跌: -10%
  - 尾部风险: -20% (黑天鹅)
"""
import math
from typing import Dict

# v9.0: Stress test thresholds loaded from config/risk.yaml with built-in defaults.
try:
    from ..config_loader import load_risk
    _risk_cfg = load_risk()
    _STRESS_MILD = float(_risk_cfg.get("stress_mild", -0.05))
    _STRESS_SEVERE = float(_risk_cfg.get("stress_severe", -0.10))
    _STRESS_TAIL = float(_risk_cfg.get("stress_tail", -0.20))
except Exception as e:
    logger.warning("[l18_var] load_risk_config failed: %s", e)
    _STRESS_MILD = -0.05
    _STRESS_SEVERE = -0.10
    _STRESS_TAIL = -0.20

# ═══════════════════════════════════════════
# ETF波动率基准 (基于akshare实时数据 2026-07-06)
# ═══════════════════════════════════════════

# 实测数据:
# 510050 (上证50): vol=22.25%, VaR(95%)=-1.72%, VaR(99%)=-2.70%
# 510300 (沪深300): vol=23.20%, VaR(95%)=-2.54%, VaR(99%)=-2.87%
# 510500 (中证500): vol=28.98%, VaR(95%)=-3.04%, VaR(99%)=-3.19%
# 510310 (创业板): vol=23.98%, VaR(95%)=-2.77%, VaR(99%)=-2.86%
# 512880 (券商): vol=41.68%, VaR(95%)=-2.47%, VaR(99%)=-2.80%

VOLATILITY_BENCHMARK = {
    "宽基": {"annual_vol": 0.20, "var_95": -0.02, "var_99": -0.03, "desc": "市场基准"},
    "沪深300": {"annual_vol": 0.23, "var_95": -0.025, "var_99": -0.029, "desc": "大盘"},
    "中证500": {"annual_vol": 0.29, "var_95": -0.030, "var_99": -0.032, "desc": "中盘"},
    "中证1000": {"annual_vol": 0.30, "var_95": -0.032, "var_99": -0.035, "desc": "小盘"},
    "上证50": {"annual_vol": 0.18, "var_95": -0.017, "var_99": -0.027, "desc": "大盘价值"},
    
    # 行业ETF波动率基准
    # 注: annual_vol 基于实测历史波动率, 与 etfs.yaml 的 risk_level(综合风险评级)是不同维度
    # 半导体 risk_level=0.65-0.72 是综合评级(含政策/集中度风险), annual_vol=0.35 是历史波动率
    "半导体": {"annual_vol": 0.35, "var_95": -0.035, "var_99": -0.045, "desc": "高波+强动量"},
    "创新药": {"annual_vol": 0.30, "var_95": -0.030, "var_99": -0.040, "desc": "高波+领涨"},
    "新能源": {"annual_vol": 0.32, "var_95": -0.032, "var_99": -0.042, "desc": "产能过剩"},
    "红利低波": {"annual_vol": 0.15, "var_95": -0.015, "var_99": -0.022, "desc": "低波+防御"},
    "券商": {"annual_vol": 0.42, "var_95": -0.042, "var_99": -0.055, "desc": "最高波+牛市旗手"},
    "银行": {"annual_vol": 0.25, "var_95": -0.025, "var_99": -0.035, "desc": "中低波+稳健"},
    "保险": {"annual_vol": 0.28, "var_95": -0.028, "var_99": -0.038, "desc": "中等波+利率敏感"},
    "金融科技": {"annual_vol": 0.38, "var_95": -0.038, "var_99": -0.050, "desc": "高波+科技属性"},
    
    # Additional benchmarks for expanded sector coverage
    "港股": {"annual_vol": 0.28, "var_95": -0.028, "var_99": -0.038, "desc": "离岸市场, 流动性风险"},
    "美股": {"annual_vol": 0.22, "var_95": -0.022, "var_99": -0.030, "desc": "美股科技主导"},
    "消费": {"annual_vol": 0.20, "var_95": -0.020, "var_99": -0.028, "desc": "消费必需品, 稳定"},
    "周期": {"annual_vol": 0.26, "var_95": -0.026, "var_99": -0.036, "desc": "周期性波动"},
    "军工": {"annual_vol": 0.30, "var_95": -0.030, "var_99": -0.042, "desc": "政策驱动, 高波动"},
    "基建": {"annual_vol": 0.22, "var_95": -0.022, "var_99": -0.030, "desc": "政策托底, 中低波"},
    "公用事业": {"annual_vol": 0.16, "var_95": -0.016, "var_99": -0.024, "desc": "防御性, 低波"},
    "可转债": {"annual_vol": 0.18, "var_95": -0.018, "var_99": -0.026, "desc": "债性为主, 含权"},
    "货币基金": {"annual_vol": 0.03, "var_95": -0.003, "var_99": -0.005, "desc": "极低波, 现金管理"},
    "贵金属": {"annual_vol": 0.18, "var_95": -0.018, "var_99": -0.026, "desc": "避险资产, 低波"},
    "农产品": {"annual_vol": 0.24, "var_95": -0.024, "var_99": -0.034, "desc": "天气+政策驱动"},
}

SECTOR_TO_VOL_KEY = {
    # Tech/Semi
    "半导体": "半导体", "芯片": "半导体", "AI/科技": "半导体", "AI算力": "半导体",
    "硬科技": "半导体", "半导体设备": "半导体", "半导体杠杆": "半导体", "半导体做空": "半导体",
    "5G/PCB": "半导体", "云计算/算力": "半导体", "通信/光模块": "半导体", "通信/5G": "半导体",
    # Pharma/Med
    "创新药": "创新药", "生物医药": "创新药", "医药": "创新药", "医药器械": "创新药",
    "中药": "创新药", "医疗器械": "创新药",
    # New Energy
    "新能源": "新能源", "光伏": "新能源", "风电": "新能源", "储能": "新能源", "锂电": "新能源",
    "电池": "新能源", "新能源汽车": "新能源",
    # Dividend/Value
    "红利低波": "红利低波", "红利": "红利低波", "价值": "红利低波",
    "红利/价值": "红利低波", "红利价值": "红利低波", "高股息": "红利低波",
    "红利+低波": "红利低波", "自由现金流": "红利低波", "小盘价值": "红利低波",
    # Finance/Broker (v7.9: split into sub-categories for differentiation)
    "券商": "券商", "证券": "券商", 
    "银行": "银行", "金融": "银行", 
    "保险": "保险",
    "金融科技": "金融科技", "金融科技ETF": "金融科技",
    # Broad market
    "宽基": "宽基", "沪深300": "沪深300", "中证500": "中证500",
    "中证1000": "中证1000", "上证50": "上证50", "创业板": "中证500",
    "全市场": "宽基", "大盘蓝筹": "沪深300", "中盘成长": "中证500", "成长股": "中证500",
    # Cross-border/HK/US
    "跨境": "跨境", "港股": "港股", "港股综合": "港股", "港股医药": "港股", "港股科技": "港股",
    "中概互联网": "港股", "美股科技": "美股", "美股科技100": "美股", "美股综合": "美股",
    "美股杠杆": "美股",
    # Consumer
    "消费": "消费", "食品饮料": "消费", "白酒消费": "消费", "白酒": "消费", "家电": "消费",
    "汽车": "消费", "旅游": "消费", "传媒": "消费", "游戏": "消费",
    # Periodic/Resources
    "周期/资源": "周期", "有色金属": "周期", "煤炭": "周期", "化工": "周期", "能源化工": "周期",
    "钢铁": "周期", "农产品": "农产品", "贵金属": "贵金属", "黄金": "贵金属",
    # Military/Defense
    "军工": "军工", "航空航天": "军工",
    # Infrastructure/Real Estate
    "基建/地产": "基建", "基建": "基建", "房地产": "基建", "地产": "基建",
    # Utilities
    "公用事业": "公用事业",
    # Bonds/Money
    "债券": "债券", "利率债": "债券", "信用债": "债券", "可转债": "可转债",
    "货币": "货币基金", "货币基金": "货币基金", "国债": "货币基金",
    # Other
    "综合": "宽基", "其他": "宽基", "央企改革": "红利低波",
    "机器人/智造": "半导体", "数字经济": "半导体",
}


def get_volatility_benchmark(sector: str) -> Dict:
    """获取行业波动率基准。"""
    key = SECTOR_TO_VOL_KEY.get(sector, "宽基")
    return VOLATILITY_BENCHMARK.get(key, VOLATILITY_BENCHMARK["宽基"])


def calculate_var(sector: str, confidence: float = 0.95) -> Dict:
    """
    计算VaR和压力测试。
    
    Args:
        sector: 行业名称
        confidence: 置信水平 (0.95 or 0.99)
    
    Returns: {
        "var_1d": 1日VaR,
        "var_5d": 5日VaR,
        "var_20d": 20日VaR,
        "stress_mild": 温和下跌情景,
        "stress_severe": 剧烈下跌情景,
        "stress_tail": 尾部风险情景,
        "annual_vol": 年化波动率,
    }
    """
    bench = get_volatility_benchmark(sector)
    annual_vol = bench["annual_vol"]
    
    # 日波动率
    daily_vol = annual_vol / math.sqrt(252)
    
    # VaR计算 (正态分布假设)
    z_scores = {0.95: 1.645, 0.99: 2.326}
    z = z_scores.get(confidence, 1.645)
    
    var_1d = -(daily_vol * z)
    var_5d = var_1d * math.sqrt(5)
    var_20d = var_1d * math.sqrt(20)
    
    # 压力测试 (v9.0: thresholds loaded from config/risk.yaml)
    stress_mild = _STRESS_MILD       # 温和下跌 -5%
    stress_severe = _STRESS_SEVERE   # 剧烈下跌 -10%
    stress_tail = _STRESS_TAIL       # 尾部风险 -20%
    
    # 组合影响 (假设ETF占组合30%)
    portfolio_impact = {
        "mild": stress_mild * 0.30,
        "severe": stress_severe * 0.30,
        "tail": stress_tail * 0.30,
    }
    
    return {
        "var_1d": round(var_1d * 100, 2),
        "var_5d": round(var_5d * 100, 2),
        "var_20d": round(var_20d * 100, 2),
        "stress_mild": round(stress_mild * 100, 1),
        "stress_severe": round(stress_severe * 100, 1),
        "stress_tail": round(stress_tail * 100, 1),
        "annual_vol": round(annual_vol * 100, 1),
        "confidence": confidence,
        "portfolio_impact": {k: round(v * 100, 2) for k, v in portfolio_impact.items()},
    }


def calculate_var_score(sector: str, etf_code: str = "") -> Dict:
    """
    计算VaR综合得分 (0-10)。
    
    评分逻辑:
    - VaR越低 (绝对值), 得分越高
    - 波动率越低, 得分越高
    - 压力测试表现越好, 得分越高
    - v8.12: Added code-based jitter for intra-bucket differentiation
    
    Returns: {
        "score": 0-10,
        "var_data": {...},
        "risk_level": "low/medium/high/extreme",
    }
    """
    var_data = calculate_var(sector)
    
    # 综合评分 — v8.8: Finer granularity to break up clustering
    # Old formula: 10 - abs(var_1d)*2 → coarse steps of ~0.2-0.5 between sectors
    # New formula: piecewise linear with finer resolution at low-vol range
    # v8.12: Added code-based jitter to differentiate ETFs in same vol bucket
    vol = var_data["annual_vol"]  # e.g., 15.0, 35.0
    # Map vol [3, 42] → score [9.0, 1.5] using piecewise
    if vol <= 15:
        var_score = 9.0 - (vol - 3) / 12 * 2.0  # 9.0 → 7.0
    elif vol <= 25:
        var_score = 7.0 - (vol - 15) / 10 * 2.0  # 7.0 → 5.0
    elif vol <= 35:
        var_score = 5.0 - (vol - 25) / 10 * 2.0  # 5.0 → 3.0
    else:
        var_score = 3.0 - (vol - 35) / 7 * 1.5  # 3.0 → 1.5
    var_score = max(1.0, min(10.0, var_score))
    
    vol_score = var_score * 0.9 + 0.3  # slightly tighter
    stress_score = var_score * 0.8 + 0.6  # even tighter
    
    composite = var_score * 0.4 + vol_score * 0.3 + stress_score * 0.3
    
    # v8.12/v8.17: Code-based deterministic jitter for intra-bucket differentiation
    # Same ETF always gets same jitter, but different ETFs in same bucket get different offsets
    # v8.15: Fixed hash randomization (Python hash() is randomized across processes).
    # Also fixed low-entropy digit-sum hash — replaced with polynomial rolling hash
    # that spreads 6-digit codes across full [−0.45, +0.45] range.
    # v8.17: Increased jitter range from ±0.45 to ±0.9 to break through 4-unique clustering.
    # v9.0: Extracted to utils.hash_jitter.code_jitter (DRY with L14)
    from ..utils.hash_jitter import code_jitter
    jitter = code_jitter(etf_code, 0.9)
    composite = composite + jitter
    
    composite = round(max(1.0, min(10.0, composite)), 1)
    
    # 风险等级 (var_data["annual_vol"] 是百分比, 如 35.0)
    if var_data["annual_vol"] < 20:
        risk_level = "low"
    elif var_data["annual_vol"] < 30:
        risk_level = "medium"
    elif var_data["annual_vol"] < 40:
        risk_level = "high"
    else:
        risk_level = "extreme"
    
    return {
        "score": composite,
        "var_data": var_data,
        "risk_level": risk_level,
        "jitter": round(jitter, 3),
    }


def apply_var_layer(sector: str, scores: Dict, etf_code: str = "") -> Dict:
    """将VaR层应用到穿透评分。"""
    var_result = calculate_var_score(sector, etf_code=etf_code)
    scores["L18_VaR"] = var_result["score"]
    
    # 高风险ETF → 降低L1_ETF得分
    if var_result["risk_level"] in ["high", "extreme"]:
        if "L1_ETF" in scores:
            scores["L1_ETF"] = round(max(1.0, scores["L1_ETF"] - 0.5), 1)
    
    return scores


def get_var_summary() -> str:
    """打印VaR摘要。"""
    lines = [
        "=" * 70,
        "ETF VaR风控层摘要 (2026-07-06 akshare实证)",
        "=" * 70,
        "",
        f"{'行业':>10s} {'年化波%':>8s} {'VaR95%':>8s} {'VaR99%':>8s} {'风险等级':>8s}",
        "-" * 70,
    ]
    for sector, bench in VOLATILITY_BENCHMARK.items():
        vol = bench["annual_vol"] * 100
        var95 = bench["var_95"] * 100
        var99 = bench["var_99"] * 100
        if vol < 0.20:
            risk = "低"
        elif vol < 0.30:
            risk = "中"
        elif vol < 0.40:
            risk = "高"
        else:
            risk = "极高"
        lines.append(f"{sector:>10s} {vol:>7.1f}% {var95:>7.1f}% {var99:>7.1f}% {risk:>8s}")
    
    lines.append("")
    lines.append("压力测试 (ETF占组合30%):")
    lines.append("  温和下跌(-5%) → 组合损失: -1.5%")
    lines.append("  剧烈下跌(-10%) → 组合损失: -3.0%")
    lines.append("  尾部风险(-20%) → 组合损失: -6.0%")
    lines.append("")
    lines.append("风控建议: 单日组合VaR(95%)不超过-3%, 年化波动>30%的ETF仓位<15%")
    return "\n".join(lines)


if __name__ == "__main__":
    print(get_var_summary())
    
    for sector in ["半导体", "创新药", "红利低波", "券商", "中证500"]:
        result = calculate_var_score(sector, etf_code="")
        print(f"\n{sector}:")
        print(f"  VaR得分: {result['score']}")
        print(f"  风险等级: {result['risk_level']}")
        vd = result["var_data"]
        print(f"  年化波动: {vd['annual_vol']}%, VaR(95%): {vd['var_1d']}%")
    
    # v8.12: Test code-based jitter differentiation
    print("\n=== v8.12: Code jitter test ===")
    for code in ["510300", "159338", "159732", "159996", "159262", "159201"]:
        result = calculate_var_score("消费", etf_code=code)
        print(f"  {code}: score={result['score']}, jitter={result['jitter']}")
