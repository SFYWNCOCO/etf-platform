"""Scoring utilities for the ETF platform — shared between pipeline/screener/picker."""


# ═══════════════════════════════════════
# Profile-aware weighted composite scoring (P0 fix)
# ═══════════════════════════════════════

PROFILES_ALIAS = {
    "conservative": "保守", "defensive": "保守", "防守": "保守",
    "balanced": "均衡", "neutral": "均衡", "中性": "均衡",
    "aggressive": "进取", "进攻": "进取",
    "激进型": "激进", "ultra_aggressive": "激进",
}


def compute_weighted_composite(scores: dict, profile: str = "均衡",
                                weights_data: dict = None,
                                layers_map: dict = None) -> tuple:
    """Compute profile-weighted composite score.

    Uses weights.yaml (profile→category→weight) and layers.yaml (layer→category).
    Returns (score, total_weight, used_layers) when config present; falls back to
    simple average (float) if config unavailable — callers should handle both.

    NOTE: this function is currently unused by the live pipeline (dead code kept
    for reference). pipeline._compute_composite_score is the active path.
    """
    import logging
    logger = logging.getLogger("etf_pipeline")

    try:
        from .config_loader import load_weights, load_layers as _load_layers

        # Resolve profile
        pk = PROFILES_ALIAS.get(str(profile).lower(), str(profile))
        try:
            wd = weights_data or load_weights()
        except (ImportError, KeyError, ValueError, TypeError, AttributeError, OSError):
            wd = weights_data or {}
        try:
            lm = layers_map or (_load_layers().get("layer_to_category", {}) if _load_layers() else {})
        except (ImportError, KeyError, ValueError, TypeError, AttributeError, OSError):
            lm = layers_map or {}

        if pk not in wd:
            pk = "均衡"
        cat_weights = wd.get(pk, {})

        total_wt = 0.0
        total_sum = 0.0
        used_layers = []
        for layer_name, category in lm.items():
            score_val = scores.get(layer_name)
            if score_val is None or not isinstance(score_val, (int, float)):
                continue
            w = cat_weights.get(category, 0)
            if w > 0:
                total_sum += score_val * w
                total_wt += w
                used_layers.append((layer_name, category, w, score_val))

        if total_wt > 0:
            return round(total_sum / total_wt, 2), total_wt, used_layers
    except Exception as e:
        logger.debug(f"weighted composite fallback ({e})")

    # Fallback: simple average of numeric scores >= 0
    vals = [v for v in scores.values() if isinstance(v, (int, float)) and v >= 0]
    if vals:
        return round(sum(vals) / len(vals), 2), 0.0, []
    return 0.0, 0.0, []


# ═══════════════════════════════════════
# k105 Three-layer architecture index
# ═══════════════════════════════════════

THREE_LAYER_INDEX = {
    "防御核心": {
        "description": "任何宏观情景都能活——黄金/国债/红利/公用事业/消费刚需",
        "max_weight": 0.40,
        "keywords": [
            "黄金", "贵金属", "国债", "利率债", "信用债", "红利低波", "红利/价值",
            "红利价值", "高股息", "红利+低波", "自由现金流", "公用事业", "白酒",
            "食品饮料", "消费", "家电", "大盘蓝筹", "沪深300", "上证50", "货币",
            "货币基金", "全市场", "宽基", "央企改革", "价值", "小盘价值",
        ],
        "sublayers": {
            "best_evergreen": ["黄金", "国债", "红利/价值"],
            "macro_independent": ["消费", "医药", "公用事业"],
            "defensive_crisis": ["黄金", "国债", "货币"],
        },
    },
    "周期进攻": {
        "description": "宏观顺风时放大收益——有色/能源/军工/资源品/券商",
        "max_weight": 0.30,
        "keywords": [
            "有色金属", "有色", "煤炭", "能源化工", "军工", "航空航天", "稀土",
            "券商", "证券", "保险", "银行", "化工", "钢铁", "农产品", "周期",
            "基建", "房地产", "地产",
        ],
        "sublayers": {
            "inflation_hedge": ["有色金属", "煤炭", "能源化工", "黄金"],
            "military_super_cycle": ["军工", "航空航天"],
            "financial_beta": ["券商", "证券", "银行"],
        },
    },
    "成长弹性": {
        "description": "产业爆发+估值修复——AI/半导体/创新药/新能源/港股科技",
        "max_weight": 0.30,
        "keywords": [
            "AI", "芯片", "半导体", "硬科技", "通信", "光模块", "5G", "云计算",
            "数字经济", "机器人", "智能制造", "创新药", "医药", "医疗", "中药",
            "医疗器械", "新能源", "光伏", "风电", "储能", "锂电", "电池",
            "新能源汽车", "港股科技", "中概互联网", "创业板", "科创",
            "美股科技", "美股科技100", "纳斯达克",
        ],
        "sublayers": {
            "kondratiev_wave6": ["AI", "半导体", "硬科技", "通信", "云计算", "数字经济"],
            "biotech_inflection": ["创新药", "医药", "医疗"],
            "new_energy_recovery": ["新能源", "光伏", "风电", "储能", "锂电"],
            "cross_border_tech": ["港股科技", "中概互联网", "美股科技"],
        },
    },
}

# Backwards-compatible sector → layer mapping for quick lookup
SECTOR_TO_THREE_LAYER = {}
for _layer_name, _info in THREE_LAYER_INDEX.items():
    for _kw in _info["keywords"]:
        SECTOR_TO_THREE_LAYER[_kw] = _layer_name


def classify_three_layer(sector: str) -> str:
    """Classify a sector into one of the three layers (defense/cycle/growth)."""
    for keyword, layer in SECTOR_TO_THREE_LAYER.items():
        if keyword in sector:
            return layer
    return "成长弹性"  # Default: undifferentiated → growth elasticity


def get_layer_allocations(profile: str = "均衡") -> dict:
    """Return recommended weight ranges by three-layer architecture.

    Args:
        profile: investor profile (均衡 default)

    Returns:
        dict with min/max/center for each layer based on profile risk preference.
    """
    if profile in ("保守", "conservative"):
        return {
            "防御核心": {"min": 0.40, "center": 0.50, "max": 0.60},
            "周期进攻": {"min": 0.05, "center": 0.15, "max": 0.25},
            "成长弹性": {"min": 0.05, "center": 0.10, "max": 0.20},
            "现金": {"min": 0.25, "center": 0.25, "max": 0.35},
        }
    elif profile in ("激进", "aggressive", "ultra_aggressive", "进攻"):
        return {
            "防御核心": {"min": 0.05, "center": 0.15, "max": 0.25},
            "周期进攻": {"min": 0.15, "center": 0.30, "max": 0.40},
            "成长弹性": {"min": 0.30, "center": 0.45, "max": 0.55},
            "现金": {"min": 0.00, "center": 0.10, "max": 0.20},
        }
    else:
        # 均衡 / 进取 / default
        return {
            "防御核心": {"min": 0.20, "center": 0.30, "max": 0.40},
            "周期进攻": {"min": 0.15, "center": 0.25, "max": 0.35},
            "成长弹性": {"min": 0.20, "center": 0.30, "max": 0.40},
            "现金": {"min": 0.10, "center": 0.15, "max": 0.20},
        }


def alloc_to_three_layers(top_n_results: list, profile: str = "均衡") -> dict:
    """Analyze how the top-N results distribute across the three layers.

    Useful for post-processing the screener output to show:
    - 组合结构是否合理
    - 单一层级是否过度集中
    """
    allocations = get_layer_allocations(profile)
    counts = {name: 0 for name in ["防御核心", "周期进攻", "成长弹性"]}
    details = {name: [] for name in counts}

    for item in top_n_results:
        sector = item.get("sector", "")
        name = item.get("name", "")
        code = item.get("code", "")
        combined = f"{sector} {name}"
        classified = classify_three_layer(combined)
        counts[classified] += 1
        details[classified].append({"code": code, "name": name, "sector": sector, "score": item.get("composite_score", 0)})

    total = max(sum(counts.values()), 1)
    result = {}
    for layer_name in counts:
        pct = counts[layer_name] / total
        alloc = allocations.get(layer_name, {})
        center = alloc.get("center", 0.25)
        overconcentrated = pct > alloc.get("max", 0.50)
        underallocated = pct < alloc.get("min", 0.05)
        result[layer_name] = {
            "count": counts[layer_name],
            "percentage": round(pct, 2),
            "target_center": center,
            "is_overconcentrated": overconcentrated,
            "is_underallocated": underallocated,
            "holdings": details[layer_name],
        }

    return result
