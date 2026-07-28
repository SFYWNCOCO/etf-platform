"""
l13_factor_loading.py — Fama-French因子暴露估计

知识源: k003 (Fama-French因子模型在A股的实证)

基于行业到因子暴露的经验映射，不依赖实际回测数据。
A股三大特色: 壳价值污染、散户主导、政策干预

因子定义:
  - SMB (规模): 小盘股溢价
  - HML (价值): 价值股溢价 (高B/M)
  - RMW (盈利): 高盈利组合 - 低盈利组合
  - CMA (投资): 低投资组合 - 高投资组合
  - LowVol (低波动): 低波动率溢价
"""
from typing import Dict

# ═══════════════════════════════════════════
# 行业→因子暴露映射 (经验估计)
# ═══════════════════════════════════════════
# 暴露值范围: -3.0 ~ +3.0
# >0: 正向暴露 (受益于该因子)
# <0: 负向暴露 (受损于该因子)
# 0: 中性
#
# A股特色调整:
# - 壳价值污染→小盘因子(SMB)对部分行业的暴露失真
# - 散户主导→动量因子短期化
# - 政策干预→价值因子(HML)受政策影响大
FACTOR_MAP = {
    # === 宽基 ===
    "宽基":          {"SMB": -0.5, "HML": 0.0,  "RMW": 0.3,  "CMA": 0.2,  "LowVol": 0.0,
                      "desc": "市场代表性,因子中性"},
    "沪深300":       {"SMB": -0.8, "HML": 0.4,  "RMW": 0.5,  "CMA": 0.3,  "LowVol": 0.2,
                      "desc": "大市值+价值偏+质量偏"},
    "中证500":       {"SMB": 1.0,  "HML": 0.2,  "RMW": 0.1,  "CMA": 0.0,  "LowVol": -0.3,
                      "desc": "中小盘+中等价值"},
    "中证1000":      {"SMB": 1.5,  "HML": 0.0,  "RMW": -0.2, "CMA": -0.3, "LowVol": -0.5,
                      "desc": "小盘+壳价值污染可能"},
    "国证2000":      {"SMB": 2.0,  "HML": -0.2, "RMW": -0.3, "CMA": -0.4, "LowVol": -0.8,
                      "desc": "超小盘,高SMB暴露但壳价值掺杂"},
    "创业板":        {"SMB": 1.2,  "HML": -0.5, "RMW": 0.2,  "CMA": -0.2, "LowVol": -1.0,
                      "desc": "成长型小盘,高波动"},

    # === 科技 ===
    "AI/科技":       {"SMB": 0.5,  "HML": -0.8, "RMW": 0.6,  "CMA": -0.5, "LowVol": -1.2,
                      "desc": "高成长低价值,高盈利预期,高波动"},
    "AI算力":        {"SMB": 0.3,  "HML": -0.9, "RMW": 0.5,  "CMA": -0.6, "LowVol": -1.3,
                      "desc": "CAPEX+成长,盈利未兑现前RMW偏弱"},
    "半导体":        {"SMB": 0.8,  "HML": -0.6, "RMW": 0.3,  "CMA": -0.7, "LowVol": -1.5,
                      "desc": "国产替代+CAPEX密集,高波动"},
    "芯片":          {"SMB": 0.8,  "HML": -0.6, "RMW": 0.3,  "CMA": -0.7, "LowVol": -1.5,
                      "desc": "同半导体"},
    "硬科技":        {"SMB": 1.0,  "HML": -0.7, "RMW": 0.4,  "CMA": -0.6, "LowVol": -1.4,
                      "desc": "高R&D+长回报期"},
    "互联网":        {"SMB": -0.3, "HML": -0.5, "RMW": 0.8,  "CMA": -0.3, "LowVol": -0.8,
                      "desc": "大平台高盈利,监管风险"},
    "中概互联网":    {"SMB": -0.5, "HML": -0.6, "RMW": 0.7,  "CMA": -0.4, "LowVol": -1.0,
                      "desc": "中美双重风险,高盈利但高不确定"},
    "云计算/算力":   {"SMB": 0.5,  "HML": -0.7, "RMW": 0.4,  "CMA": -0.5, "LowVol": -1.1,
                      "desc": "CAPEX密集型成长"},
    "数字经济":      {"SMB": 0.8,  "HML": -0.5, "RMW": 0.5,  "CMA": -0.4, "LowVol": -0.9,
                      "desc": "政策受益+成长"},

    # === 通信/5G ===
    "通信/5G":       {"SMB": 0.3,  "HML": -0.2, "RMW": 0.4,  "CMA": -0.3, "LowVol": -0.5,
                      "desc": "CAPEX驱动"},
    "通信/光模块":   {"SMB": 0.5,  "HML": -0.6, "RMW": 0.5,  "CMA": -0.5, "LowVol": -1.0,
                      "desc": "AI算力加持的高弹性"},
    "5G/PCB":        {"SMB": 0.6,  "HML": -0.4, "RMW": 0.3,  "CMA": -0.4, "LowVol": -0.8,
                      "desc": "硬件周期+AI需求"},

    # === 新能源 ===
    "新能源":        {"SMB": 0.6,  "HML": -0.5, "RMW": 0.2,  "CMA": -0.6, "LowVol": -1.2,
                      "desc": "CAPEX过剩+产能出清中"},
    "新能源车":      {"SMB": 0.7,  "HML": -0.6, "RMW": 0.1,  "CMA": -0.7, "LowVol": -1.3,
                      "desc": "价格战+产能过剩"},
    "光伏":          {"SMB": 0.8,  "HML": -0.5, "RMW": -0.2, "CMA": -0.8, "LowVol": -1.5,
                      "desc": "产能严重过剩,RMW转负"},
    "风电":          {"SMB": 0.5,  "HML": -0.3, "RMW": 0.1,  "CMA": -0.5, "LowVol": -1.0,
                      "desc": "招标价下行"},

    # === 红利/价值 ===
    "红利/价值":     {"SMB": -0.5, "HML": 1.8,  "RMW": 1.2,  "CMA": 1.0,  "LowVol": 1.5,
                      "desc": "典型价值股,高盈利,低投资,低波动"},
    "自由现金流":    {"SMB": -0.3, "HML": 1.5,  "RMW": 1.5,  "CMA": 1.2,  "LowVol": 1.3,
                      "desc": "极高质量因子暴露"},

    # === 金融 ===
    "金融":          {"SMB": -1.0, "HML": 1.5,  "RMW": 0.8,  "CMA": 0.9,  "LowVol": 0.5,
                      "desc": "大市值+价值+高杠杆"},
    "银行":          {"SMB": -1.2, "HML": 2.0,  "RMW": 1.0,  "CMA": 1.2,  "LowVol": 0.6,
                      "desc": "极致价值,高盈利,高CMA(资本充足率限制投资)"},
    "券商":          {"SMB": -0.5, "HML": 0.3,  "RMW": 0.3,  "CMA": 0.0,  "LowVol": -0.5,
                      "desc": "beta属性强"},
    "保险":          {"SMB": -1.0, "HML": 1.2,  "RMW": 0.6,  "CMA": 0.8,  "LowVol": 0.3,
                      "desc": "金融+红利属性"},

    # === 周期 ===
    "有色金属":      {"SMB": 0.3,  "HML": 0.2,  "RMW": 0.3,  "CMA": -0.3, "LowVol": -0.6,
                      "desc": "商品价格驱动"},
    "煤炭":          {"SMB": 0.2,  "HML": 1.0,  "RMW": 0.8,  "CMA": 0.5,  "LowVol": 0.4,
                      "desc": "高盈利+价值+CAPEX受限"},
    "化工":          {"SMB": 0.5,  "HML": 0.3,  "RMW": 0.4,  "CMA": -0.2, "LowVol": -0.4,
                      "desc": "周期品+CAPEX周期"},
    "钢铁":          {"SMB": 0.2,  "HML": 0.8,  "RMW": 0.3,  "CMA": 0.2,  "LowVol": -0.2,
                      "desc": "产能控制+价值属性"},
    "石油石化":      {"SMB": -0.3, "HML": 0.6,  "RMW": 0.5,  "CMA": 0.3,  "LowVol": 0.2,
                      "desc": "大市值+商品+价值"},
    "周期/资源":     {"SMB": 0.3,  "HML": 0.4,  "RMW": 0.3,  "CMA": -0.1, "LowVol": -0.4,
                      "desc": "周期驱动"},

    # === 消费 ===
    "消费":          {"SMB": 0.0,  "HML": 0.3,  "RMW": 0.8,  "CMA": 0.5,  "LowVol": 0.6,
                      "desc": "稳定盈利+确定性"},
    "食品饮料":      {"SMB": -0.2, "HML": 0.5,  "RMW": 1.2,  "CMA": 0.8,  "LowVol": 0.8,
                      "desc": "高盈利+价值+低波动,顶级组合"},
    "白酒":          {"SMB": -0.3, "HML": 0.4,  "RMW": 1.5,  "CMA": 1.0,  "LowVol": 0.7,
                      "desc": "最强RMW,高roe高利润率"},
    "家电":          {"SMB": 0.0,  "HML": 0.6,  "RMW": 1.0,  "CMA": 0.7,  "LowVol": 0.5,
                      "desc": "高质量+价值+出海"},
    "汽车":          {"SMB": 0.5,  "HML": -0.2, "RMW": 0.3,  "CMA": -0.4, "LowVol": -0.6,
                      "desc": "新能源转型+价格战"},
    "旅游":          {"SMB": 0.8,  "HML": -0.3, "RMW": -0.2, "CMA": -0.3, "LowVol": -0.4,
                      "desc": "小盘+服务消费恢复"},

    # === 医药 ===
    "医药":          {"SMB": 0.5,  "HML": -0.3, "RMW": 0.5,  "CMA": 0.0,  "LowVol": -0.3,
                      "desc": "集采压力+创新驱动"},
    "医疗":          {"SMB": 0.6,  "HML": -0.2, "RMW": 0.4,  "CMA": 0.1,  "LowVol": -0.2,
                      "desc": "器械+服务"},
    "医疗器械":      {"SMB": 0.4,  "HML": 0.0,  "RMW": 0.6,  "CMA": 0.2,  "LowVol": 0.0,
                      "desc": "国产替代+集采控价"},
    "中药":          {"SMB": 0.3,  "HML": 0.4,  "RMW": 0.7,  "CMA": 0.5,  "LowVol": 0.3,
                      "desc": "品牌+政策扶持+价值"},

    # === 军工 ===
    "军工":          {"SMB": 0.6,  "HML": 0.0,  "RMW": 0.2,  "CMA": -0.3, "LowVol": -0.7,
                      "desc": "政策驱动+订单周期"},

    # === 地产/基建 ===
    "房地产":        {"SMB": 0.3,  "HML": 1.2,  "RMW": -0.5, "CMA": 1.5,  "LowVol": -0.8,
                      "desc": "高杠杆+高HML(账面价值)>高CMA(不能投资)=高波动"},
    "基建":          {"SMB": 0.0,  "HML": 0.8,  "RMW": 0.3,  "CMA": 0.6,  "LowVol": 0.2,
                      "desc": "低增长+稳定订单"},
    "基建/地产":     {"SMB": 0.2,  "HML": 1.0,  "RMW": -0.1, "CMA": 1.0,  "LowVol": -0.3,
                      "desc": "混合属性"},
    "公用事业":      {"SMB": -0.5, "HML": 1.0,  "RMW": 0.6,  "CMA": 0.8,  "LowVol": 1.2,
                      "desc": "防御性+低波动+高股息"},

    # === 跨境/商品 ===
    "跨境":          {"SMB": 0.0,  "HML": 0.0,  "RMW": 0.0,  "CMA": 0.0,  "LowVol": 0.0,
                      "desc": "因子暴露取决于底层指数"},
    "港股":          {"SMB": 0.0,  "HML": 0.2,  "RMW": 0.1,  "CMA": 0.0,  "LowVol": 0.2,
                      "desc": "离岸市场,因子暴露较弱"},
    "黄金":          {"SMB": 0.0,  "HML": 0.0,  "RMW": 0.0,  "CMA": 0.0,  "LowVol": 2.0,
                      "desc": "零因子beta,极端低波动(类现金)"},

    # === 其他 ===
    "其他":          {"SMB": 0.0,  "HML": 0.0,  "RMW": 0.0,  "CMA": 0.0,  "LowVol": 0.0,
                      "desc": "未知行业,因子中性"},
    "货币基金":      {"SMB": 0.0,  "HML": 0.0,  "RMW": 0.0,  "CMA": 0.0,  "LowVol": 3.0,
                      "desc": "极低风险"},
    "债券":          {"SMB": 0.0,  "HML": 0.0,  "RMW": 0.0,  "CMA": 0.0,  "LowVol": 3.0,
                      "desc": "类固收"},
    "利率债":        {"SMB": 0.0,  "HML": 0.0,  "RMW": 0.0,  "CMA": 0.0,  "LowVol": 3.0,
                      "desc": "极低风险"},
    "信用债":        {"SMB": 0.0,  "HML": 0.2,  "RMW": 0.0,  "CMA": 0.0,  "LowVol": 2.0,
                      "desc": "信用利差风险"},

    # === ETF系统模糊匹配目标 ===
    "半导体设备":     {"SMB": 0.8,  "HML": -0.6, "RMW": 0.2,  "CMA": -0.7, "LowVol": -1.4,
                      "desc": "半导体上游设备, CAPEX更密集"},
    "红利低波":       {"SMB": -0.3, "HML": 1.5,  "RMW": 1.0,  "CMA": 0.8,  "LowVol": 1.8,
                      "desc": "极致低波动+价值+质量"},
    "传媒":           {"SMB": 1.0,  "HML": -0.5, "RMW": -0.1, "CMA": -0.4, "LowVol": -0.6,
                      "desc": "小盘+内容周期"},
    "游戏":           {"SMB": 1.2,  "HML": -0.6, "RMW": 0.2,  "CMA": -0.5, "LowVol": -0.8,
                      "desc": "版号政策+产品周期+小盘"},
    "教育":           {"SMB": 1.0,  "HML": -0.8, "RMW": -0.5, "CMA": -0.6, "LowVol": -1.0,
                      "desc": "政策管制+高不确定"},
}


def get_factor_exposure(sector: str) -> Dict:
    """返回该行业的五因子暴露值。"""
    factors = FACTOR_MAP.get(sector)
    if factors:
        return dict(factors)

    # 模糊匹配
    for key, val in FACTOR_MAP.items():
        if key in sector or sector in key:
            result = dict(val)
            result["_match"] = f"fuzzy: {key}"
            return result

    # 默认
    return {"SMB": 0.0, "HML": 0.0, "RMW": 0.0, "CMA": 0.0, "LowVol": 0.0,
            "desc": "无匹配,因子中性", "_match": "default"}


# ═══════════════════════════════════════════
# 因子动量 → 评分修正
# ═══════════════════════════════════════════

# 当前市场环境下,各因子的方向偏好
# >0: 该因子当前有利 (因子动量向上)
# <0: 该因子当前不利
# 0: 中性
FACTOR_MOMENTUM = {
    "SMB": -0.3,     # 小盘因子偏弱 (注册制下壳价值消退)
    "HML": 0.5,      # 价值因子偏好 (利率下行+红利行情)
    "RMW": 0.6,      # 盈利因子强 (确定性溢价)
    "CMA": 0.3,      # 投资保守因子中性偏正
    "LowVol": 0.7,   # 低波动因子强 (防御行情)
}

# 因子动量对应的行业偏好调整
FACTOR_MOMENTUM_ADJUSTMENT = {
    # {factor: weight} → 高暴露于该因子的行业获得加分
    "SMB": 0.05,     # 每1单位SMB暴露 → ±5% scoring
    "HML": 0.08,
    "RMW": 0.10,
    "CMA": 0.05,
    "LowVol": 0.12,
}


def score_factor_adjustment(sector: str) -> float:
    """基于因子动量计算对评分的修正 (+/- 范围 0~2.0)。"""
    factors = get_factor_exposure(sector)
    total = 0.0

    for factor, exposure_key in [("SMB", "SMB"), ("HML", "HML"),
                                  ("RMW", "RMW"), ("CMA", "CMA"),
                                  ("LowVol", "LowVol")]:
        exposure = factors.get(exposure_key, 0)
        momentum = FACTOR_MOMENTUM.get(factor, 0)
        weight = FACTOR_MOMENTUM_ADJUSTMENT.get(factor, 0.05)

        # 暴露 × 动量方向 × 权重
        total += exposure * momentum * weight

    # 限幅 ±1.5
    total = max(-1.5, min(1.5, total))
    return round(total, 2)


def get_factor_report(sector: str) -> Dict:
    """完整的因子分析报告。"""
    exposure = get_factor_exposure(sector)
    adj = score_factor_adjustment(sector)

    return {
        "sector": sector,
        "exposure": exposure,
        "momentum_adj": adj,
        "top_factors": sorted(
            [(f, v) for f, v in exposure.items()
             if f in ("SMB", "HML", "RMW", "CMA", "LowVol") and isinstance(v, (int, float))],
            key=lambda x: abs(x[1]), reverse=True
        )[:3],
    }
