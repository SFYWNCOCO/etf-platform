"""
L12_macro_cycle.py — Kondratiev+王朝周期+三周期嵌套宏观层 (v3.0)

Key changes from v2.0:
- Expanded fallback sector adjustments: added 20+ new granular mappings
- Previously ~10 categories in fallback → many sectors hit ca=1.0 (no adjustment)
- Now covers: 军工, 半导体, 新能源, 白酒, 家电, 地产, 券商, 中药, 通信/光模块, 旅游/传媒/游戏, etc.
- Expected: L13_MacroCycle neutral zone clustering drops from 53% to <30%
"""
from datetime import datetime, timezone
from typing import Dict, Tuple, Optional

# ═══════════════════════════════════════════
# 第6波 Kondratiev (AI/生物技术/新能源)
# ═══════════════════════════════════════
KONDRATIEV_CURRENT_WAVE = 6
KONDRATIEV_START_YEAR = 2020
KONDRATIEV_LENGTH = 55

K_PHASE_RATIOS = [0.20, 0.30, 0.30, 0.20]

K_CURRENT_PHASE = "spring_accelerating"

# ═══════════════════════════════════════════
# Kuznets周期 (建筑/人口/房地产)
# ═══════════════════════════════════════
KUZNETS_LENGTH = 20
KUZNETS_CURRENT_PHASE = "bottom_transition"

# ═══════════════════════════════════════════
# Juglar周期 (设备投资/库存)
# ═══════════════════════════════════════
JUGLAR_LENGTH = 9
JUGLAR_CURRENT_PHASE = "restocking_mid"

# ═══════════════════════════════════════════
# China institutional 周期
# ═══════════════════════════════════════
CYCLE_PHASE = "spring"

# ═══════════════════════════════════════════
# 三周期 → 行业权重映射
# ═══════════════════════════════════════

PHASE_SECTOR_ADJUSTMENT = {
    ("spring_accelerating", "bottom_transition", "restocking_mid"): {
        "AI/科技": 1.20,
        "AI算力": 1.25,
        "半导体": 1.20,
        "硬科技": 1.20,
        "新能源": 1.15,
        "红利/价值": 1.10,
        "军工": 1.10,
        "医药": 1.10,
        "房地产": 0.80,
        "金融": 0.90,
        "消费": 1.05,
        "传统基建": 0.85,
        "煤炭": 0.80,
        "有色金属": 0.95,
        "跨境": 1.10,
        "宽基": 1.05,
        "黄金": 1.10,
    },
}

PHASE_DESCRIPTIONS = {
    "kondratiev": {
        "spring": "第6波(AI/生物/新能源) Spring阶段——技术革命爆发期, 新兴技术从实验室走向商业化",
        "spring_accelerating": "第6波 Spring加速期——AI应用落地加速, 资本开支暴增, 产业格局初定",
        "summer": "第6波 Summer阶段——大规模应用推广期, 渗透率快速提升, 龙头确立",
        "autumn": "第6波 Autumn阶段——产能过剩+竞争加剧, 利润率压缩, 行业洗牌",
        "winter": "第6波 Winter阶段——泡沫出清, 旧技术淘汰, 为下一波积蓄力量",
    },
    "kuznets": {
        "peak": "Kuznets周期顶——房地产/基建投资见顶, 城镇化率放缓",
        "decline": "Kuznets下行——去房地产化, 传统基建收缩, 新旧动能转换",
        "bottom": "Kuznets底部震荡——新型城镇化+保障房+城市更新托底",
        "recovery": "Kuznets复苏——新基建/城市群/TOD模式驱动新一轮建设",
        "bottom_transition": "Kuznets底部→复苏过渡——传统地产触底, 新模式萌芽",
    },
    "juglar": {
        "recovery": "Juglar补库初期——库存见底, 企业开始补库, PMI回升",
        "boom": "Juglar繁荣——补库高峰, 产能利用率高, 通胀压力",
        "recession": "Juglar衰退——去库存, 订单下降, 工业利润压缩",
        "depression": "Juglar萧条——库存底部, 产能出清, 等待拐点",
        "restocking_mid": "Juglar补库中后期——库存已回补至中性水平, 补库动能减弱",
    },
}


def get_cycle_adjustments(sector: str) -> Dict[str, float]:
    """返回三周期对给定行业的综合权重调整。"""
    key = (K_CURRENT_PHASE, KUZNETS_CURRENT_PHASE, JUGLAR_CURRENT_PHASE)
    adjustments = PHASE_SECTOR_ADJUSTMENT.get(key, {})

    sector_map = _resolve_sector(sector)
    composite = 1.0

    result = {
        "kondratiev_adj": 1.0,
        "kuznets_adj": 1.0,
        "juglar_adj": 1.0,
        "composite_adj": 1.0,
    }

    for s in sector_map:
        adj = adjustments.get(s, 1.0)
        if adj != 1.0:
            k_adj = 1.0 + (adj - 1.0) * 0.50
            kuz_adj = 1.0 + (adj - 1.0) * 0.30
            j_adj = 1.0 + (adj - 1.0) * 0.20
            composite *= adj

            result["kondratiev_adj"] = max(result["kondratiev_adj"], k_adj)
            result["kuznets_adj"] = max(result["kuznets_adj"], kuz_adj)
            result["juglar_adj"] = max(result["juglar_adj"], j_adj)

    result["composite_adj"] = round(composite, 3)
    result["kondratiev_adj"] = round(result["kondratiev_adj"], 3)
    result["kuznets_adj"] = round(result["kuznets_adj"], 3)
    result["juglar_adj"] = round(result["juglar_adj"], 3)

    result["kondratiev_phase"] = K_CURRENT_PHASE
    result["kuznets_phase"] = KUZNETS_CURRENT_PHASE
    result["juglar_phase"] = JUGLAR_CURRENT_PHASE
    result["cycle_phase"] = CYCLE_PHASE
    result["kondratiev_wave"] = KONDRATIEV_CURRENT_WAVE
    result["phase_desc_k"] = PHASE_DESCRIPTIONS["kondratiev"].get(K_CURRENT_PHASE, "")
    result["phase_desc_kuz"] = PHASE_DESCRIPTIONS["kuznets"].get(KUZNETS_CURRENT_PHASE, "")
    result["phase_desc_j"] = PHASE_DESCRIPTIONS["juglar"].get(JUGLAR_CURRENT_PHASE, "")

    return result


def _resolve_sector(sector: str) -> list:
    """将ETF系统sector映射到周期调整表用的标准行业名。"""
    mapping = {
        "AI/科技": ["AI/科技", "AI算力"],
        "AI算力": ["AI算力"],
        "半导体": ["半导体", "硬科技"],
        "芯片": ["半导体", "硬科技"],
        "新能源": ["新能源"],
        "新能源车": ["新能源"],
        "光伏": ["新能源"],
        "风电": ["新能源"],
        "军工": ["军工"],
        "医药": ["医药"],
        "医疗": ["医药"],
        "医疗器械": ["医药"],
        "红利/价值": ["红利/价值"],
        "消费": ["消费"],
        "食品饮料": ["消费"],
        "白酒": ["消费"],
        "家电": ["消费"],
        "金融": ["金融"],
        "银行": ["金融"],
        "券商": ["金融"],
        "保险": ["金融"],
        "房地产": ["房地产"],
        "基建/地产": ["传统基建", "房地产"],
        "基建": ["传统基建"],
        "公用事业": ["传统基建"],
        "有色金属": ["有色金属"],
        "煤炭": ["煤炭"],
        "周期/资源": ["有色金属"],
        "化工": ["有色金属"],
        "跨境": ["跨境"],
        "港股": ["跨境"],
        "中概互联网": ["跨境"],
        "宽基": ["宽基"],
        "黄金": ["黄金"],
        "互联网": ["AI/科技"],
        "通信/5G": ["AI/科技"],
        "通信/光模块": ["AI/科技"],
        "5G/PCB": ["AI/科技"],
        "云计算/算力": ["AI算力"],
        "数字经济": ["AI/科技"],
        "其他": ["宽基"],
        "教育": [],
    }
    return mapping.get(sector, [sector])


def score_cycle_layer(sector: str, risk_level: float) -> Dict:
    """返回L12周期宏观层评分 (0-10).

    v3.0: Expanded fallback sector adjustments from 10 to 30+ categories.
    """
    adj = get_cycle_adjustments(sector)
    ca = adj["composite_adj"]

    # v3.1: Granular fallback for sectors not in PHASE_SECTOR_ADJUSTMENT
    # Expanded from 15 distinct ca values to 25+ by splitting overlapping categories
    if ca == 1.0 and sector:
        _s = sector
        # === Debt/Fixed Income (split into 3 tiers) ===
        if any(k in _s for k in ["国债", "利率债"]):
            ca = 0.95  # lower risk, stable
        elif any(k in _s for k in ["信用债", "可转债"]):
            ca = 0.97  # slight credit risk premium
        elif any(k in _s for k in ["货币", "货币基金"]):
            ca = 0.93  # lowest yield environment
        elif any(k in _s for k in ["债"]):
            ca = 0.95  # generic bond
        # === Precious metals ===
        elif any(k in _s for k in ["黄金", "贵金属"]):
            ca = 1.08  # strong safe-haven in current cycle
        # === Dividend/value (split into 2 tiers) ===
        elif any(k in _s for k in ["红利", "高股息"]):
            ca = 1.10  # strong dividend cycle
        elif any(k in _s for k in ["价值", "低波"]):
            ca = 1.06  # moderate value
        elif any(k in _s for k in ["自由现金流"]):
            ca = 1.08  # quality factor
        # === Utilities/banking/insurance ===
        elif any(k in _s for k in ["公用事业"]):
            ca = 1.05  # regulated utility
        elif any(k in _s for k in ["银行"]):
            ca = 1.02  # rate-sensitive
        elif any(k in _s for k in ["保险"]):
            ca = 1.03  # investment income sensitive
        # === Consumer/pharma (split into 3 tiers) ===
        elif any(k in _s for k in ["白酒", "食品饮料"]):
            ca = 1.07  # top consumer quality
        elif any(k in _s for k in ["消费", "医药"]):
            ca = 1.04  # moderate consumer/pharma
        elif any(k in _s for k in ["医药器械", "医疗器械"]):
            ca = 1.06  # medical device innovation
        # === Broad market ===
        elif any(k in _s for k in ["宽基", "全市场"]):
            ca = 1.03
        elif any(k in _s for k in ["沪深300", "大盘蓝筹"]):
            ca = 1.04
        # === Resources/commodities ===
        elif any(k in _s for k in ["有色金属", "有色"]):
            ca = 0.97  # mild commodity cycle
        elif any(k in _s for k in ["煤炭", "能源化工"]):
            ca = 0.93  # coal/energy under pressure
        elif any(k in _s for k in ["周期/资源"]):
            ca = 0.95
        elif any(k in _s for k in ["农产品"]):
            ca = 0.96  # food security support
        # === Cross-border ===
        elif any(k in _s for k in ["跨境"]):
            ca = 1.05  # diversification benefit
        elif any(k in _s for k in ["港股综合", "港股"]):
            ca = 1.02  # HK discount
        elif any(k in _s for k in ["美股科技100", "美股科技"]):
            ca = 1.06  # US tech strength
        elif any(k in _s for k in ["中概互联网"]):
            ca = 0.98  # dual-regulation drag
        # === Tech/AI ===
        elif any(k in _s for k in ["半导体设备"]):
            ca = 1.18  # equipment leader
        elif any(k in _s for k in ["半导体", "芯片", "硬科技"]):
            ca = 1.15
        elif any(k in _s for k in ["AI算力", "云计算/算力"]):
            ca = 1.12
        elif any(k in _s for k in ["AI/科技", "数字经济"]):
            ca = 1.10
        elif any(k in _s for k in ["通信", "光模块", "5G", "PCB"]):
            ca = 1.12
        # === New energy ===
        elif any(k in _s for k in ["光伏"]):
            ca = 1.03  # overcapacity drag
        elif any(k in _s for k in ["风电"]):
            ca = 1.04
        elif any(k in _s for k in ["储能", "锂电", "电池"]):
            ca = 1.05
        elif any(k in _s for k in ["新能源"]):
            ca = 1.04
        # === Defense ===
        elif any(k in _s for k in ["军工", "航空航天"]):
            ca = 1.12  # strong defense spending
        # === Real estate/infra ===
        elif any(k in _s for k in ["房地产", "地产"]):
            ca = 0.82  # severe drag
        elif any(k in _s for k in ["基建"]):
            ca = 0.90  # moderate infra support
        # === Finance ===
        elif any(k in _s for k in ["券商", "证券"]):
            ca = 0.97  # market-cycle dependent
        elif any(k in _s for k in ["金融"]):
            ca = 0.95
        # === Pharma sub-sectors ===
        elif any(k in _s for k in ["中药", "创新药"]):
            ca = 1.08  # policy support
        # === Consumer services ===
        elif any(k in _s for k in ["旅游", "传媒", "游戏"]):
            ca = 1.03
        elif any(k in _s for k in ["家电"]):
            ca = 1.04
        elif any(k in _s for k in ["汽车"]):
            ca = 1.03
        # === Heavy industry ===
        elif any(k in _s for k in ["钢铁"]):
            ca = 0.92
        elif any(k in _s for k in ["化工"]):
            ca = 0.94
        # === Small/mid cap ===
        elif any(k in _s for k in ["小盘"]):
            ca = 0.96
        elif any(k in _s for k in ["中盘"]):
            ca = 0.98
        elif any(k in _s for k in ["成长股"]):
            ca = 1.02
        elif any(k in _s for k in ["小盘价值"]):
            ca = 1.00
        # === Generic fallback ===
        elif any(k in _s for k in ["其他", "综合", "教育"]):
            ca = 1.00
        else:
            ca = 1.00
        adj["composite_adj"] = round(ca, 3)

    # 基础分 5.0, 调整幅度 max ±2.0
    base = 5.0
    if ca > 1.0:
        bonus = min(2.0, (ca - 1.0) * 10)
        score = base + bonus
    elif ca < 1.0:
        penalty = min(2.0, (1.0 - ca) * 10)
        score = base - penalty
    else:
        score = base

    # 高风险行业(risk_level>0.5)在逆周期时额外惩罚
    if risk_level > 0.5 and ca < 1.0:
        extra = min(1.0, (risk_level - 0.5) * 2)
        score -= extra

    score = max(1.0, min(10.0, score))

    return {
        "score": round(score, 1),
        "composite_adj": ca,
        "kondratiev_adj": adj["kondratiev_adj"],
        "kuznets_adj": adj["kuznets_adj"],
        "juglar_adj": adj["juglar_adj"],
        "kondratiev_phase": adj["kondratiev_phase"],
        "kuznets_phase": adj["kuznets_phase"],
        "juglar_phase": adj["juglar_phase"],
        "cycle_phase": adj["cycle_phase"],
        "kondratiev_wave": adj["kondratiev_wave"],
        "phase_desc_k": adj["phase_desc_k"],
        "phase_desc_kuz": adj["phase_desc_kuz"],
        "phase_desc_j": adj["phase_desc_j"],
    }


def format_cycle_report(sector: str = None) -> str:
    """格式化输出三周期状态报告。"""
    lines = []
    lines.append("\n  ═══ 三周期宏观状态 ═══")
    lines.append(f"  Kondratiev 第{ KONDRATIEV_CURRENT_WAVE }波 ({KONDRATIEV_START_YEAR}-{KONDRATIEV_START_YEAR+KONDRATIEV_LENGTH})")
    lines.append(f"    相位: {K_CURRENT_PHASE}")
    lines.append(f"    描述: {PHASE_DESCRIPTIONS['kondratiev'].get(K_CURRENT_PHASE, '')}")
    lines.append(f"  Kuznets周期 (~{KUZNETS_LENGTH}年)")
    lines.append(f"    相位: {KUZNETS_CURRENT_PHASE}")
    lines.append(f"    描述: {PHASE_DESCRIPTIONS['kuznets'].get(KUZNETS_CURRENT_PHASE, '')}")
    lines.append(f"  Juglar周期 (~{JUGLAR_LENGTH}年)")
    lines.append(f"    相位: {JUGLAR_CURRENT_PHASE}")
    lines.append(f"    描述: {PHASE_DESCRIPTIONS['juglar'].get(JUGLAR_CURRENT_PHASE, '')}")

    if sector:
        adj = get_cycle_adjustments(sector)
        lines.append(f"\n  ═══ {sector} 周期暴露 ═══")
        lines.append(f"  综合调整: {adj['composite_adj']:.3f}x")
        lines.append(f"  Kondratiev: {adj['kondratiev_adj']:.3f}x")
        lines.append(f"  Kuznets:    {adj['kuznets_adj']:.3f}x")
        lines.append(f"  Juglar:     {adj['juglar_adj']:.3f}x")

    return "\n".join(lines)


def detect_cycle_from_data() -> Dict:
    """未来扩展: 从实际宏观数据自动检测周期相位。"""
    return {
        "kondratiev": {"phase": K_CURRENT_PHASE, "wave": KONDRATIEV_CURRENT_WAVE},
        "kuznets": {"phase": KUZNETS_CURRENT_PHASE},
        "juglar": {"phase": JUGLAR_CURRENT_PHASE},
        "institutional": {"phase": CYCLE_PHASE},
    }
