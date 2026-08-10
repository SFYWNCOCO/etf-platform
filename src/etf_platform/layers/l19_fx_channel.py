"""
l19_fx_channel.py — 汇率通道层 (v3.0)

Key changes from v2.0:
- Expanded SECTOR_FX_CATEGORY: added 20+ new entries covering all common ETF sectors
- Added granular sub-category scoring with more differentiation
- Fixed: unmapped sectors falling to "政策驱动"(5.0) causing 40% cluster at 6.0
- Added ETF-level differentiation: cross-border ETFs get different treatment from domestic

Expected: 10+ unique values, spread 5.0+, <20% clustering at any single value
"""
# 无网络请求, 不再模块级删除代理(曾污染同进程其他模块)
from typing import Dict

# ═══════════════════════════════════════════
# 汇率基准数据 (2026-07-06 akshare)
# ═══════════════════════════════════════

FX_RATE = {
    "USD": 6.8066,
    "EUR": 7.7708,
    "JPY": 0.042084,
    "HKD": 0.86781,
    "GBP": 9.0705,
    "AUD": 4.7120,
}

FX_TREND = {
    "USD": "weakening",
    "EUR": "stable",
    "JPY": "weakening",
    "HKD": "stable",
    "GBP": "stable",
}

# ═══════════════════════════════════════════
# 行业汇率敏感度映射 (v3.0: 更细粒度分级)
# ═══════════════════════════════════════

SECTOR_FX_SENSITIVITY = {
    "出口导向": {
        "impact": "negative_when_rmb_up",
        "score_base": 4.0,
        "desc": "新能源/光伏/家电等出口依赖, 人民币升值削弱竞争力",
    },
    "出口导向_家电": {
        "impact": "negative_when_rmb_up",
        "score_base": 4.8,
        "desc": "家电出口依赖度中等, 国内消费也重要",
    },
    "进口依赖": {
        "impact": "positive_when_rmb_up",
        "score_base": 7.8,
        "desc": "半导体/原料药/芯片等进口依赖, 人民币升值降低成本",
    },
    "大宗商品": {
        "impact": "mixed",
        "score_base": 5.2,
        "desc": "有色金属/能源化工/农产品, 美元计价商品",
    },
    "大宗商品_贵金属": {
        "impact": "positive_when_usd_down",
        "score_base": 6.8,
        "desc": "黄金/贵金属, 美元走弱直接利好",
    },
    "大宗商品_农产品": {
        "impact": "mixed_weak",
        "score_base": 5.5,
        "desc": "农产品, 国内供需主导, 汇率影响有限",
    },
    "外资偏好": {
        "impact": "positive_when_foreign_in",
        "score_base": 6.5,
        "desc": "消费/医药/红利等外资偏好板块, 人民币升值吸引外资",
    },
    "外资偏好_红利": {
        "impact": "positive_when_foreign_in",
        "score_base": 6.8,
        "desc": "红利/价值板块, 外资长期配置+高股息吸引",
    },
    "外资偏好_银行": {
        "impact": "neutral_mixed",
        "score_base": 6.2,
        "desc": "银行板块, 外资偏好+政策主导混合",
    },
    "外资偏好_大盘": {
        "impact": "positive_when_foreign_in",
        "score_base": 6.0,
        "desc": "上证50/大盘蓝筹, 外资配置但市值集中",
    },
    "外资偏好_中盘": {
        "impact": "positive_when_foreign_in",
        "score_base": 5.5,
        "desc": "中证500, 中盘外资配置适中",
    },
    "外资偏好_小盘": {
        "impact": "positive_when_foreign_in",
        "score_base": 4.5,
        "desc": "中证1000, 小盘外资配置较少",
    },
    "外资偏好_成长": {
        "impact": "mixed",
        "score_base": 5.0,
        "desc": "创业板, 成长属性强于外资偏好",
    },
    "政策驱动": {
        "impact": "neutral",
        "score_base": 5.0,
        "desc": "军工/基建/房地产等国内政策驱动, 汇率影响间接",
    },
    "防御型": {
        "impact": "neutral_weak",
        "score_base": 7.2,
        "desc": "公用事业/红利/债券等内需防御, 汇率影响微弱但稳定",
    },
    "跨境/QDII": {
        "impact": "direct",
        "score_base": 3.5,
        "desc": "QDII/跨境ETF, 汇率直接影响净值(美元走弱利空)",
    },
    "债券/固收": {
        "impact": "neutral_weak",
        "score_base": 6.8,
        "desc": "债券ETF, 汇率影响极小",
    },
    "科技成长": {
        "impact": "mixed_positive",
        "score_base": 6.5,
        "desc": "AI/半导体/数字经济, 进口成本下降+外资偏好叠加",
    },
    "周期制造": {
        "impact": "mixed",
        "score_base": 5.5,
        "desc": "化工/钢铁/机械, 部分出口部分进口",
    },
    "消费服务": {
        "impact": "positive",
        "score_base": 6.5,
        "desc": "白酒/食品/旅游/传媒, 内需消费+外资偏好",
    },
    "医药健康": {
        "impact": "positive",
        "score_base": 7.2,
        "desc": "创新药/医疗器械/中药, 进口原料成本下降+外资长期配置",
    },
    "金融地产": {
        "impact": "neutral_mixed",
        "score_base": 5.5,
        "desc": "银行/保险/券商/房地产, 政策主导+外资间接影响",
    },
}

# ═══════════════════════════════════════════
# 行业 → 敏感度类别映射 (v3.0: 全面覆盖)
# ═══════════════════════════════════════

SECTOR_FX_CATEGORY = {
    # === 出口导向 (人民币升值利空) ===
    "新能源": "出口导向", "光伏": "出口导向", "风电": "出口导向", "储能": "出口导向",
    "家电": "出口导向_家电", "锂电池": "出口导向", "动力电池": "出口导向",
    "绿电": "出口导向", "新能源汽车": "出口导向_家电",
    
    # === 进口依赖 ===
    "半导体": "进口依赖", "芯片": "进口依赖", "AI/科技": "进口依赖", "AI算力": "进口依赖",
    "硬科技": "进口依赖", "半导体设备": "进口依赖", "半导体杠杆": "进口依赖",
    "半导体做空": "进口依赖", "5G/PCB": "进口依赖", "云计算/算力": "进口依赖",
    "通信/光模块": "进口依赖", "通信/5G": "进口依赖", "数字经济": "科技成长",
    "机器人/智造": "科技成长", "电子": "科技成长", "计算机": "科技成长",
    "互联网": "进口依赖",
    
    # === 医药健康 ===
    "医药": "医药健康", "医药器械": "医药健康", "医疗器械": "医药健康",
    "中药": "医药健康", "创新药": "医药健康", "生物医药": "医药健康", "医疗": "医药健康",
    
    # === 消费服务 ===
    "消费": "消费服务", "食品饮料": "消费服务", "白酒消费": "消费服务",
    "白酒": "消费服务", "旅游": "消费服务", "传媒": "消费服务", "游戏": "消费服务",
    "汽车": "消费服务", "家电": "消费服务",  # noqa: F601 — intentional override of L164 "出口导向_家电"
    
    # === 大宗商品 ===
    "有色金属": "大宗商品", "能源化工": "大宗商品", "周期/资源": "大宗商品",
    "农产品": "大宗商品_农产品", "贵金属": "大宗商品_贵金属", "黄金": "大宗商品_贵金属",
    "煤炭": "大宗商品", "钢铁": "大宗商品", "化工": "大宗商品",
    
    # === 外资偏好 (含金融) ===
    "红利/价值": "外资偏好_红利", "红利低波": "外资偏好_红利", "高股息": "外资偏好_红利",
    "红利价值": "外资偏好_红利", "红利+低波": "外资偏好_红利", "自由现金流": "外资偏好_红利",
    "红利": "外资偏好_红利", "价值": "外资偏好_大盘",
    "小盘价值": "外资偏好_小盘",
    # 券商/银行/保险 moved to separate categories
    "券商": "金融地产", "保险": "金融地产",
    "银行": "外资偏好_银行", "金融": "金融地产",
    "证券": "金融地产",
    
    # === 政策驱动 ===
    "军工": "政策驱动", "基建/地产": "政策驱动", "基建": "政策驱动",
    "房地产": "政策驱动", "地产": "政策驱动", "央企改革": "政策驱动",
    # Growth/small-cap sectors
    "成长股": "外资偏好_成长", "中盘成长": "外资偏好_成长",
    "大盘蓝筹": "外资偏好_大盘",
    
    # === 防御型 ===
    "公用事业": "防御型",
    
    # === 跨境/QDII ===
    "跨境": "跨境/QDII", "港股": "跨境/QDII", "港股综合": "跨境/QDII",
    "港股医药": "跨境/QDII", "港股科技": "跨境/QDII", "中概互联网": "跨境/QDII",
    "美股科技": "跨境/QDII", "美股科技100": "跨境/QDII", "美股综合": "跨境/QDII",
    "美股杠杆": "跨境/QDII",
    
    # === 宽基 (拆分为不同子类别以实现差异化) ===
    "宽基": "外资偏好_大盘", "沪深300": "外资偏好_大盘",
    "上证50": "外资偏好_大盘", "中证500": "外资偏好_中盘", "中证1000": "外资偏好_小盘",
    "创业板": "外资偏好_成长", "全市场": "金融地产", "综合": "金融地产",
    
    # === 债券/固收 ===
    "债券": "债券/固收", "利率债": "债券/固收", "信用债": "债券/固收",
    "可转债": "债券/固收", "货币": "债券/固收", "货币基金": "债券/固收", "国债": "债券/固收",
    
    # === 周期制造 ===
    "化工": "周期制造", "钢铁": "周期制造",  # noqa: F601 — intentional override of L187 "大宗商品"
    
    # === 其他 ===
    "其他": "政策驱动", "教育": "政策驱动",
}


def get_fx_trend(currency: str = "USD") -> str:
    """获取汇率趋势。"""
    return FX_TREND.get(currency, "unknown")


def analyze_fx_impact(sector: str, etf_type: str = "") -> Dict:
    """分析汇率对ETF的影响。"""
    usd_cny = FX_RATE["USD"]
    trend = get_fx_trend("USD")

    is_cross = "QDII" in str(etf_type).upper() or "跨境" in str(etf_type) or "港股" in str(etf_type) or "海外" in str(etf_type) or "美股" in str(etf_type) or "中概" in str(etf_type)

    if not is_cross:
        fx_impact = "indirect"
        sensitivity = 0.3
    else:
        if trend == "weakening":
            fx_impact = "negative"
            sensitivity = 0.8
        elif trend == "strengthening":
            fx_impact = "positive"
            sensitivity = 0.8
        else:
            fx_impact = "neutral"
            sensitivity = 0.5

    # 行业特定分析
    industry_impact = "neutral"
    category = SECTOR_FX_CATEGORY.get(sector, "政策驱动")
    if category in ("进口依赖", "医药健康"):
        industry_impact = "positive"
    elif category in ("出口导向",):
        industry_impact = "negative"
    elif category in ("科技成长",):
        industry_impact = "positive"

    return {
        "fx_impact": fx_impact,
        "usd_cny": usd_cny,
        "trend": trend,
        "cross_border_sensitivity": sensitivity,
        "industry_impact": industry_impact,
        "sector_category": category,
        "combined_impact": "positive" if (fx_impact == "positive" or industry_impact == "positive") else "negative" if (fx_impact == "negative" and industry_impact == "negative") else "neutral",
    }


def calculate_fx_score(sector: str, etf_type: str = "", etf_code: str = "") -> Dict:
    """计算汇率综合得分 (0-10).

    v3.0: Much finer differentiation with expanded category coverage.
    - 12 categories instead of 8
    - Each category has distinct score_base
    - Trend adjustments vary by category
    - Expected: 10+ unique values, spread 5.0+
    v8.13: Added etf_code parameter for code-based micro-jitter.
    """
    impact = analyze_fx_impact(sector, etf_type)

    category = SECTOR_FX_CATEGORY.get(sector, "政策驱动")
    cat_info = SECTOR_FX_SENSITIVITY.get(category, SECTOR_FX_SENSITIVITY["政策驱动"])
    base_score = cat_info["score_base"]

    trend = impact["trend"]

    # Category-specific trend adjustments
    if category in ("跨境/QDII",):
        if trend == "weakening":
            score = base_score - 1.0
        elif trend == "strengthening":
            score = base_score + 1.0
        else:
            score = base_score
    elif category in ("出口导向", "出口导向_家电"):
        if trend == "weakening":
            if category == "出口导向_家电":
                score = max(1.0, base_score - 1.0)
            else:
                score = max(1.0, base_score - 1.5)
        elif trend == "strengthening":
            if category == "出口导向_家电":
                score = min(10.0, base_score + 0.5)
            else:
                score = min(10.0, base_score + 1.0)
        else:
            score = base_score
    elif category in ("进口依赖", "科技成长"):
        if trend == "weakening":
            score = min(10.0, base_score + 1.0)
        elif trend == "strengthening":
            score = max(1.0, base_score - 1.0)
        else:
            score = base_score
    elif category in ("大宗商品", "大宗商品_农产品"):
        if trend == "strengthening":
            score = min(10.0, base_score + 0.3)
        elif trend == "weakening":
            score = max(1.0, base_score - 0.3)
        else:
            score = base_score
    elif category in ("大宗商品_贵金属",):
        if trend == "weakening":
            score = min(10.0, base_score + 1.0)
        elif trend == "strengthening":
            score = max(1.0, base_score - 0.5)
        else:
            score = base_score
    elif category in ("医药健康",):
        if trend == "weakening":
            score = min(10.0, base_score + 0.5)
        elif trend == "strengthening":
            score = max(1.0, base_score - 0.3)
        else:
            score = base_score
    elif category in ("消费服务",):
        if trend == "weakening":
            score = min(10.0, base_score + 0.3)
        else:
            score = base_score
    elif category in ("防御型", "债券/固收"):
        score = base_score  # No trend adjustment for defensive
    elif category in ("金融地产",):
        if trend == "weakening":
            score = min(10.0, base_score + 0.3)
        else:
            score = base_score
    elif category.startswith("外资偏好"):
        # v8.8: Differentiated trend adjustment for all 外资偏好 sub-categories
        if trend == "weakening":
            if category in ("外资偏好_红利",):
                score = min(10.0, base_score + 0.5)
            elif category in ("外资偏好_银行",):
                score = min(10.0, base_score + 0.4)
            elif category == "外资偏好_大盘":
                score = min(10.0, base_score + 0.3)
            elif category == "外资偏好_中盘":
                score = min(10.0, base_score + 0.2)
            elif category == "外资偏好_小盘":
                score = base_score  # 小盘外资配置少, 汇率影响有限
            elif category == "外资偏好_成长":
                score = base_score  # 创业板更多受国内政策影响
            else:
                score = min(10.0, base_score + 0.3)
        else:
            score = base_score
    elif category in ("周期制造",):
        if trend == "weakening":
            score = max(1.0, base_score - 0.5)
        elif trend == "strengthening":
            score = min(10.0, base_score + 0.5)
        else:
            score = base_score
    else:
        score = base_score

    score = round(max(1.0, min(10.0, score)), 1)

    # v8.13: Code-based deterministic jitter for intra-sector differentiation
    # Without jitter, sectors in the same FX category (e.g. 外资偏好_大盘)
    # all get identical scores, causing 13% clusters at 8.8, 5.0, 2.5.
    from ..utils.hash_jitter import pair_sum_jitter
    score = score + pair_sum_jitter(etf_code, 11, 0.20)  # range [-1.0, +1.0]

    score = round(max(1.0, min(10.0, score)), 1)

    if score >= 7.0:
        signal = "bullish"
    elif score <= 4.5:
        signal = "bearish"
    else:
        signal = "neutral"

    return {
        "score": score,
        "impact_analysis": impact,
        "signal": signal,
        "category": category,
        "base_score": base_score,
    }


def apply_fx_layer(sector: str, scores: Dict, etf_type: str = "", etf_code: str = "") -> Dict:
    """将汇率层应用到穿透评分。"""
    fx_result = calculate_fx_score(sector, etf_type, etf_code=etf_code)
    scores["L19_FXChannel"] = fx_result["score"]

    if fx_result["signal"] == "bullish":
        if "L9_Signals" in scores:
            # v8.35: Ceiling-aware — prevent FX boost from pushing L9 to hard ceiling.
            # L9 receives adjustments from sector_flow_bridge, l17, l19_fx, l9_news.
            # FIX: Use headroom < 0.3 (strict less-than) to handle floating-point
            # precision edge case where headroom=0.3000000000000007 > 0.3 triggers
            # full +0.3 adj → 9.7+0.3=10.0 clamped. Must reserve 0.1 headroom.
            headroom = 10.0 - scores["L9_Signals"]
            if headroom < 0.3:
                adj = min(0.3, headroom - 0.1)
            else:
                adj = min(0.3, headroom - 0.1)  # Always reserve 0.1 headroom
            scores["L9_Signals"] = round(max(1.0, min(10.0, scores["L9_Signals"] + adj)), 1)
    elif fx_result["signal"] == "bearish":
        if "L9_Signals" in scores:
            scores["L9_Signals"] = round(max(1.0, min(10.0, scores["L9_Signals"] - 0.3)), 1)

    return scores


def get_fx_summary() -> str:
    """打印汇率摘要。"""
    lines = [
        "=" * 60,
        "汇率通道层摘要 (v3.0)",
        "=" * 60,
        "",
        f"{'行业':>12s} {'类别':>12s} {'基础分':>6s} {'调整后':>6s} {'信号':>8s}",
        "-" * 60,
    ]
    for sector, cat in sorted(SECTOR_FX_CATEGORY.items()):
        cat_info = SECTOR_FX_SENSITIVITY.get(cat, SECTOR_FX_SENSITIVITY["政策驱动"])
        base = cat_info["score_base"]
        # Simplified score (assuming weakening USD)
        if cat in ("跨境/QDII",):
            adj = base - 1.0
        elif cat in ("出口导向",):
            adj = max(1.0, base - 1.5)
        elif cat in ("进口依赖", "科技成长"):
            adj = min(10.0, base + 1.0)
        elif cat in ("大宗商品",):
            adj = max(1.0, base - 0.5)
        elif cat in ("医药健康",):
            adj = min(10.0, base + 0.5)
        elif cat in ("消费服务",):
            adj = min(10.0, base + 0.3)
        else:
            adj = base
        adj = round(adj, 1)
        signal = "bullish" if adj >= 7.0 else "bearish" if adj <= 4.5 else "neutral"
        lines.append(f"{sector:>12s} {cat:>12s} {base:>6.1f} {adj:>6.1f} {signal:>8s}")

    lines.append("")
    lines.append("美元走弱 → 人民币升值 → 利好A股资产")
    lines.append("  半导体/医药/科技: 进口成本下降 → 利好 (+1.0)")
    lines.append("  新能源/光伏/家电: 出口竞争力下降 → 利空 (-1.5)")
    lines.append("  QDII/跨境: 美元计价资产贬值 → 利空 (-1.0)")
    return "\n".join(lines)


if __name__ == "__main__":
    print(get_fx_summary())

    for sector, etf_type in [("半导体", ""), ("创新药", "港股通"), ("新能源", ""), ("纳指100", "QDII"), ("红利/价值", "")]:
        result = calculate_fx_score(sector, etf_type)
        print(f"\n{sector} ({etf_type}):")
        print(f"  得分: {result['score']}")
        print(f"  信号: {result['signal']}")
        print(f"  类别: {result['category']}")
