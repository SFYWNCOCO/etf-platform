#!/usr/bin/env python3
"""
macro_overlay.py — 宏观事件叠加层 v2.0

知识库驱动升级 (k104+k127+k129+k105):
1. UIDF四维宏观打分卡 (k104) — 通胀/利率/增长/地缘→仓位中枢
2. 行业轮动矩阵 (k104) — 12大行业×4种宏观情景映射
3. 三层资产架构 (k105) — 防御核心/周期进攻/成长弹性
4. 实时CATALYSTS — 来自k127 7月宏观+中报实证数据

用于 two_week_picker/investment_recommendation 的评分调整。输出范围 ±0.15。
"""
import json
from pathlib import Path
from datetime import date

BASE = Path(__file__).resolve().parent.parent.parent.parent  # etf-platform/
NEWS_FILE = BASE / "data" / "news_etf_signals.json"


# ═══════════════════════════════════════════════════════════════════
# ── UIDF 四维宏观打分卡 (k104, 2026-07更新) ──────────────────
# ═══════════════════════════════════════════════════════════════════

MACRO_CARD_2026Q3 = {
    "通胀": {"indicator": "美PCE", "value": "2.7%", "signal": "🟡", "weight": 0.30},
    "利率": {"indicator": "Fed stance", "value": "暂停(4票反对加息)", "signal": "🟡", "weight": 0.25},
    "增长": {"indicator": "全球PMI/GDP", "value": "~3.1%", "signal": "🟡", "weight": 0.25},
    "地缘": {"indicator": "美伊+中东", "value": "重燃(霍尔木兹)", "signal": "🔴", "weight": 0.20},
}

# 宏观九宫格→仓位中枢 (k104 §1.2)
# 基于当前：通胀=中 + 地缘=高 → 仓位中枢 30%
POSITION_CENTER = 0.30  # 30%仓位建议


def get_macro_regime() -> dict:
    """Return current macro regime assessment (UIDF Layer 0)."""
    today = date.today()
    return {
        "regime": "滞胀边缘+地缘高温",
        "position_center": POSITION_CENTER,
        "favored": ["黄金", "军工", "有色", "创新药"],
        "caution": ["新能源", "光伏", "白酒", "房地产"],
        "earnings_season": "mid_report" if (today.month in (7, 8)) else "normal",
        "timestamp": today.isoformat(),
        "note": "Fed鹰派+美伊升级→防御为主，黄金打底；中报季利好AI/半导体/通信",
    }


# ═══════════════════════════════════════════════════════════════════
# ── 行业轮动矩阵 (k104 §2.1) — 12行业×4宏观情景 ──────────────
# ═══════════════════════════════════════════════════════════════════

# 评分: 5=最优, 4=良好, 3=中性, 2=谨慎, 1=回避
SECTOR_ROTATION_MATRIX = {
    "黄金":     {"滞胀": 5, "衰退": 5, "复苏": 3, "过热": 4},
    "军工":     {"滞胀": 5, "衰退": 4, "复苏": 3, "过热": 4},
    "能源/煤":  {"滞胀": 5, "衰退": 3, "复苏": 3, "过热": 5},
    "有色":     {"滞胀": 4, "衰退": 3, "复苏": 5, "过热": 5},
    "AI/芯片":  {"滞胀": 3, "衰退": 1, "复苏": 5, "过热": 4},
    "创新药":   {"滞胀": 4, "衰退": 5, "复苏": 4, "过热": 3},
    "新能源":   {"滞胀": 3, "衰退": 1, "复苏": 5, "过热": 4},
    "通信":     {"滞胀": 3, "衰退": 2, "复苏": 4, "过热": 4},
    "消费":     {"滞胀": 3, "衰退": 2, "复苏": 5, "过热": 4},
    "国债":     {"滞胀": 4, "衰退": 5, "复苏": 3, "过热": 1},
    "金融":     {"滞胀": 3, "衰退": 1, "复苏": 4, "过热": 4},
    "房地产":   {"滞胀": 2, "衰退": 1, "复苏": 3, "过热": 3},
}

_SECTOR_ALIASES = {
    "半导体": "AI/芯片", "芯片": "AI/芯片", "AI": "AI/芯片",
    "煤炭": "能源/煤", "原油": "能源/煤", "石油": "能源/煤",
    "有色金属": "有色", "铜": "有色", "铝": "有色",
    "医药": "创新药", "生物医药": "创新药",
    "光伏": "新能源", "电池": "新能源", "新能源车": "新能源",
    "5G": "通信", "光通信": "通信",
    "黄金ETF": "黄金",
    "军工ETF": "军工",
}


def get_sector_rotation_score(sector: str, regime: str = "滞胀") -> float:
    """Get UIDF sector rotation score for a sector under a macro regime."""
    # Normalize via aliases
    lookup = _SECTOR_ALIASES.get(sector, sector)
    for matrix_key in SECTOR_ROTATION_MATRIX:
        if matrix_key in lookup or lookup in matrix_key:
            score = SECTOR_ROTATION_MATRIX[matrix_key].get(regime, 3)
            # Map 1-5 to -0.15 to +0.15 boost range
            return round((score - 3) * 0.05, 3)
    return 0.0


# ═══════════════════════════════════════════════════════════════════
# ── 三层资产架构 (k105) ───────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════

ASSET_LAYER_MAP = {
    "防御核心": {"sectors": ["黄金", "国债", "红利", "消费"], "weight_center": 0.40},
    "周期进攻": {"sectors": ["有色", "能源/煤", "军工", "煤炭", "原油", "石油"], "weight_center": 0.30},
    "成长弹性": {"sectors": ["AI/芯片", "半导体", "芯片", "创新药", "医药", "新能源", "通信", "5G"], "weight_center": 0.30},
}


def get_asset_layer(sector: str) -> str:
    """Return asset layer category (防御核心/周期进攻/成长弹性)."""
    lookup = _SECTOR_ALIASES.get(sector, sector)
    for layer, info in ASSET_LAYER_MAP.items():
        for s in info["sectors"]:
            if s in lookup or lookup in s:
                return layer
    return "未分类"


# ═══════════════════════════════════════════════════════════════════
# ── Earnings season detection ─────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════

# 2026年7月中报实证数据 (源自k127 + k129)
_EARNINGS_VISIBILITY = {
    # 高预喜率行业 (中报预喜>85%)
    "半导体": {"pre_rate": 0.95, "bias": 0.08},
    "存储": {"pre_rate": 0.95, "bias": 0.08},
    "通信": {"pre_rate": 1.00, "bias": 0.08},
    "消费电子": {"pre_rate": 1.00, "bias": 0.08},
    "有色": {"pre_rate": 1.00, "bias": 0.06},
    "黄金": {"pre_rate": 1.00, "bias": 0.05},
    "煤炭": {"pre_rate": 0.80, "bias": 0.04},
    "消费": {"pre_rate": 0.60, "bias": 0.03},
    # 低预喜/逆风行业
    "新能源": {"pre_rate": 0.30, "bias": -0.03},
    "光伏": {"pre_rate": 0.20, "bias": -0.05},
    "白酒": {"pre_rate": 0.40, "bias": -0.02},
}


def is_earnings_season() -> dict:
    """Check if we're in earnings season and return sector-aware adjustment.

    A-share earnings seasons:
    - Q1/Annual: Jan 1 - Apr 30 (peak: Mar-Apr)
    - Semi-annual: Jul 1 - Aug 31 (peak: Jul-Aug) ← NOW
    - Q3: Oct 1 - Oct 31
    """
    today = date.today()
    m = today.month

    result = {"active": False, "phase": "normal", "adjustment": 0.0, "note": ""}

    if m in (7, 8):
        result["active"] = True
        result["phase"] = "中报季"
        result["adjustment"] = 0.05
        result["note"] = "中报密集披露期(2026.7-8)：AI/半导体100%预喜率，光伏/新能源承压"
    elif m == 4:
        result["active"] = True
        result["phase"] = "年报/一季报季"
        result["adjustment"] = 0.03
        result["note"] = "年报收官+一季报披露，关注业绩拐点"
    elif m == 10:
        result["active"] = True
        result["phase"] = "三季报季"
        result["adjustment"] = 0.03
        result["note"] = "三季报窗口，全年业绩可预期性增强"

    return result


def get_earnings_sector_boost(sector: str) -> float:
    """Get earnings-season sector-specific boost based on actual pre-good rates."""
    season = is_earnings_season()
    if not season["active"]:
        return 0.0

    lookup = _SECTOR_ALIASES.get(sector, sector)
    for keyword, info in _EARNINGS_VISIBILITY.items():
        if keyword in lookup or lookup in keyword:
            return info["bias"]
    # Generic mid-report boost for unknown sectors
    return 0.01


# ═══════════════════════════════════════════════════════════════════
# ── Updated CATALYSTS (2026-07-23, 源自k127/k129) ───────────────
# ═══════════════════════════════════════════════════════════════════

CATALYSTS = {
    # ── 地缘 (k127: 美伊升级, 全球军费11连增) ──
    "军工": {
        "event": "美伊冲突升级+全球军费11连增+装备现代化加速",
        "boost": 0.12,
        "expires": "2026-08-15",
    },
    "航天": {
        "event": "商业航天产业化加速+卫星互联网星座建设",
        "boost": 0.08,
        "expires": "2026-08-15",
    },
    # ── 避险 (k127: 黄金打底) ──
    "黄金": {
        "event": "地缘避险+通胀对冲+Fed鹰派美元走弱预期",
        "boost": 0.10,
        "expires": "2026-08-15",
    },
    # ── 科技 (k127: AI算力, 中报100%预喜) ──
    "半导体": {
        "event": "中报100%预喜率+存储涨价+AI算力需求爆发+国产替代加速",
        "boost": 0.08,
        "expires": "2026-08-15",
    },
    "通信": {
        "event": "1.6T/3.2T光模块规模化出货+中报100%预喜+5G-A商用",
        "boost": 0.08,
        "expires": "2026-08-15",
    },
    "AI/芯片": {
        "event": "全球CSP资本支出+40%达$6000亿+中报>85%预喜",
        "boost": 0.06,
        "expires": "2026-08-15",
    },
    "存储": {
        "event": "DRAM/NAND供不应求+兆易创新+1099%+佰维+3200%",
        "boost": 0.10,
        "expires": "2026-08-15",
    },
    # ── 资源品 (k127: 油价暴涨, 有色100%预喜) ──
    "有色": {
        "event": "中报100%预喜+铜铝价格高位+AI基建拉动+美伊推高油价",
        "boost": 0.08,
        "expires": "2026-08-15",
    },
    "煤炭": {
        "event": "供给侧偏紧+夏季用电高峰+中报80%预喜",
        "boost": 0.05,
        "expires": "2026-08-31",
    },
    # ── 医药 (k105: PS 9.7x洼地) ──
    "创新药": {
        "event": "PS 9.7x vs 美股21.4x洼地+创新药出海逻辑+集采压力边际递减",
        "boost": 0.06,
        "expires": "2026-08-15",
    },
    # ── 逆风行业 (k129: 光伏/新能源车承压) ──
    "新能源": {
        "event": "产能过剩消化中+光伏价格战+新能源车分化",
        "boost": -0.04,
        "expires": "2026-08-15",
    },
    "光伏": {
        "event": "产能出清中+价格战+估值承压",
        "boost": -0.05,
        "expires": "2026-08-31",
    },
}


def get_catalyst_boost(sector: str) -> float:
    """Get known catalyst boost for a sector. Falls back to rotation matrix."""
    today = date.today().isoformat()
    lookup = _SECTOR_ALIASES.get(sector, sector)

    for key, info in CATALYSTS.items():
        if key in lookup or lookup in key:
            if info["expires"] > today:
                return info["boost"]

    # Fallback to UIDF rotation matrix if no specific catalyst
    return get_sector_rotation_score(sector)


# ── News sentiment loading ────────────────────────────────────────

def _load_news_signals() -> dict:
    """Load latest news sentiment signals."""
    if not NEWS_FILE.exists():
        return {}
    try:
        with open(NEWS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def get_news_boost(sector: str) -> float:
    """Get news sentiment boost for a sector (-0.1 to +0.1)."""
    signals = _load_news_signals()
    if not signals:
        return 0.0

    for key, value in signals.items():
        if isinstance(value, dict):
            sentiment = value.get("sentiment", value.get("score", 0))
        else:
            sentiment = float(value) if isinstance(value, (int, float)) else 0

        if key in sector or sector in key:
            return max(-0.1, min(0.1, float(sentiment) * 0.02))

    return 0.0


# ═══════════════════════════════════════════════════════════════════
# ── Composite overlay ─────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════

def get_overlay(sector: str) -> dict:
    """Get composite macro overlay for a sector (UIDF v2.0).

    Fuses: UIDF rotation + catalyst + earnings + news sentiment.
    Returns a dict with total_boost and breakdown.
    Positive boost = favor this sector, negative = penalize.
    Range: approximately -0.15 to +0.15
    """
    # Layer 1: UIDF rotation (k104)
    rotation = get_sector_rotation_score(sector)

    # Layer 2: Known catalysts (updated from k127/k129)
    catalyst = get_catalyst_boost(sector)

    # Layer 3: Earnings season sector bias (实证数据驱动)
    earnings_boost = get_earnings_sector_boost(sector)

    # Layer 4: News sentiment
    news = get_news_boost(sector)

    total = rotation + catalyst + earnings_boost + news
    total = max(-0.15, min(0.20, total))

    # Find catalyst event description
    catalyst_event = ""
    lookup = _SECTOR_ALIASES.get(sector, sector)
    for key, info in CATALYSTS.items():
        if key in lookup or lookup in key:
            if info["expires"] > date.today().isoformat():
                catalyst_event = info["event"]
                break

    return {
        "total_boost": round(total, 3),
        "rotation": round(rotation, 3),
        "catalyst": round(catalyst, 3),
        "earnings_season": round(earnings_boost, 3),
        "news": round(news, 3),
        "asset_layer": get_asset_layer(sector),
        "earnings_phase": is_earnings_season()["phase"],
        "catalyst_event": catalyst_event,
        "uidf_regime": "滞胀边缘+地缘高温",
        "position_center": POSITION_CENTER,
    }


def get_macro_context() -> dict:
    """Get full macro context for report generation."""
    regime = get_macro_regime()
    season = is_earnings_season()
    return {
        "regime": regime["regime"],
        "position_center": regime["position_center"],
        "favored_sectors": regime["favored"],
        "caution_sectors": regime["caution"],
        "earnings_phase": season["phase"],
        "earnings_note": season["note"],
        "layers": {
            "防御核心": ASSET_LAYER_MAP["防御核心"]["sectors"],
            "周期进攻": ASSET_LAYER_MAP["周期进攻"]["sectors"],
            "成长弹性": ASSET_LAYER_MAP["成长弹性"]["sectors"],
        },
    }


# ═══════════════════════════════════════════════════════════════════
# ── CLI ──────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        sector = sys.argv[1]
    else:
        sector = "半导体"

    print(f"=== UIDF v2.0 宏观叠加: {sector} ===")
    overlay = get_overlay(sector)
    for k, v in overlay.items():
        print(f"  {k}: {v}")

    print("\n=== 宏观判官 ===")
    ctx = get_macro_context()
    for k, v in ctx.items():
        print(f"  {k}: {v}")

    print("\n=== 催化剂(活跃) ===")
    today = date.today().isoformat()
    for k, v in sorted(CATALYSTS.items()):
        active = "✅" if v["expires"] > today else "⛔"
        print(f"  {active} {k}: {v['event']} ({v['boost']:+.2f}, 至{v['expires']})")
