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
SENT_FILE = BASE / "data" / "news_sentiment.json"


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

# ═══════════════════════════════════════════════════════════════════
# ── 完整行业分类覆盖 (申万31一级 + ETF特有) ───────────────────
# ═══════════════════════════════════════════════════════════════════

_SECTOR_ALIASES = {
    # ── AI/科技产业链 ──
    "半导体": "AI/芯片", "芯片": "AI/芯片", "AI": "AI/芯片",
    "计算机": "AI/芯片", "软件": "AI/芯片", "云计算/算力": "AI/芯片",
    "云计算": "AI/芯片", "算力": "AI/芯片", "AI算力": "AI/芯片",
    "AI/科技": "AI/芯片", "硬科技": "AI/芯片",
    "机器人/智造": "AI/芯片", "机器人": "AI/芯片",
    "通信/5G": "通信", "通信/光模块": "通信", "5G/PCB": "通信",
    "5G": "通信", "光通信": "通信",
    
    # ── 资源/能源 ──
    "煤炭": "能源/煤", "原油": "能源/煤", "石油": "能源/煤",
    "石油石化": "石油石化", "油气": "石油石化", "能源化工": "石油石化",
    "有色金属": "有色", "铜": "有色", "铝": "有色", "稀土": "有色",
    "贵金属": "黄金",
    
    # ── 医药健康 ──
    "医药": "创新药", "生物医药": "创新药", "中药": "创新药",
    "医药器械": "创新药", "港股医药": "创新药",
    
    # ── 新能源/汽车 ──
    "光伏": "新能源", "电池": "新能源", "新能源车": "新能源",
    "储能": "新能源", "风电": "新能源",
    
    # ── 消费/零售 ──
    "白酒": "消费", "白酒消费": "消费", "食品饮料": "消费",
    "家电": "消费", "汽车": "消费",
    
    # ── 金融 ──
    "券商": "金融/券商", "证券": "金融/券商", "保险": "金融/保险",
    "金融": "金融/券商", "银行": "金融/券商",
    
    # ── 政策/改革 ──
    "央企改革": "央企/国企改革",
    
    # ── 农业/公用事业 ──
    "农业": "农业/农产品", "农产品": "农业/农产品",
    "公用事业": "电力", "火电": "电力", "特高压": "电力",
    
    # ── 地产/基建 ──
    "房地产": "基建/地产", "地产": "基建/地产", "基建": "基建/地产",
    "建筑材料": "基建/地产", "建筑装饰": "基建/地产",
    
    # ── 其他 ──
    "钢铁": "周期/资源", "基础化工": "周期/资源", "纺织服饰": "消费",
    "轻工制造": "消费", "传媒": "AI/科技",
    
    # ── 申万一级行业补充 (仅保留新增映射, 已存在 key 不再重复) ──
    "IT服务": "AI/芯片",
    "机械设备": "周期/资源", "电气设备": "电力",
    "农林牧渔": "农业/农产品",
    "医药生物": "创新药",
    "家用电器": "消费",
    "商业贸易": "消费", "社会服务": "消费", "休闲服务": "消费",
    "通信设备": "通信", "电子": "AI/芯片",
    "交通运输": "周期/资源", "环保": "公用事业",
    
    # ── ETF特有细分 ──
    "半导体设备": "半导体",
    "军工电子": "军工",
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
    "防御核心": {"sectors": ["黄金", "国债", "红利", "消费", "金融/保险", "白酒"], "weight_center": 0.40},
    "周期进攻": {"sectors": ["有色", "能源/煤", "军工", "煤炭", "原油", "石油", "石油石化", "金融/券商", "央企/国企改革", "农业/农产品"], "weight_center": 0.30},
    "成长弹性": {"sectors": ["AI/芯片", "半导体", "芯片", "创新药", "医药", "新能源", "通信", "5G", "核电", "电力", "机器人/智造", "存储", "航天"], "weight_center": 0.30},
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
    # ═══════════════════════════════════════════════════════════════
    # ── AI/科技产业链 (申万: 电子、计算机、通信) ──
    # ═══════════════════════════════════════════════════════════════
    "AI/芯片": {
        "event": "全球CSP资本支出+40%达$6000亿+中报>85%预喜，SpaceX/AMD财报本周",
        "boost": 0.06,
        "expires": "2026-08-15",
    },
    "半导体": {
        "event": "A股存储芯片/半导体设备回撤中，但美股费半+6.3%/英伟达+5.6%→全球AI算力逻辑未变",
        "boost": 0.04,
        "expires": "2026-08-15",
    },
    "存储": {
        "event": "DRAM/NAND供不应求+A股短期回撤→布局窗口，兆易创新+1099%",
        "boost": 0.05,
        "expires": "2026-08-15",
    },
    "通信": {
        "event": "1.6T/3.2T光模块规模化出货+中报100%预喜+5G-A商用",
        "boost": 0.08,
        "expires": "2026-08-15",
    },
    "机器人/智造": {
        "event": "人形机器人产业化加速+国产替代+2026年量产元年",
        "boost": 0.06,
        "expires": "2026-08-15",
    },
    
    # ═══════════════════════════════════════════════════════════════
    # ── 能源/资源 (申万: 石油石化、煤炭、有色金属、电力设备) ──
    # ═══════════════════════════════════════════════════════════════
    "核电": {
        "event": "国务院核准4个新建核电项目+总投资超1700亿+久盛电气/百利电气/中国核建涨停",
        "boost": 0.15,
        "expires": "2026-08-31",
    },
    "电力": {
        "event": "新型电力系统十五五规划印发+核电核准加速+特高压建设",
        "boost": 0.10,
        "expires": "2026-08-31",
    },
    "有色": {
        "event": "中报100%预喜+铜铝高位+AI基建拉动；油价暴跌利好下游成本",
        "boost": 0.06,
        "expires": "2026-08-15",
    },
    "煤炭": {
        "event": "供给侧偏紧+夏季用电高峰+中报80%预喜",
        "boost": 0.05,
        "expires": "2026-08-31",
    },
    "原油": {
        "event": "布伦特$83.68(-4.8%)+OPEC+增产计划+伊朗谈判→油价中枢下移",
        "boost": -0.08,
        "expires": "2026-08-18",
    },
    "石油石化": {
        "event": "WTI跌破$80(-5%)+美伊谈判+霍尔木兹重开→上游承压，下游成本下降",
        "boost": -0.06,
        "expires": "2026-08-18",
    },
    
    # ═══════════════════════════════════════════════════════════════
    # ── 医药健康 (申万: 医药生物) ──
    # ═══════════════════════════════════════════════════════════════
    "创新药": {
        "event": "PS 9.7x vs 美股21.4x洼地+创新药出海逻辑+集采压力边际递减",
        "boost": 0.06,
        "expires": "2026-08-15",
    },
    
    # ═══════════════════════════════════════════════════════════════
    # ── 大消费 (申万: 食品饮料、家用电器、汽车、纺织服饰) ──
    # ═══════════════════════════════════════════════════════════════
    "消费": {
        "event": "内需复苏+政策刺激+电商催化，中报预喜率稳健",
        "boost": 0.04,
        "expires": "2026-08-15",
    },
    "白酒": {
        "event": "白酒业绩拐点预期+茅台提价+消费复苏政策，估值历史低位",
        "boost": 0.05,
        "expires": "2026-08-31",
    },
    
    # ═══════════════════════════════════════════════════════════════
    # ── 金融 (申万: 银行、非银金融) ──
    # ═══════════════════════════════════════════════════════════════
    "金融/券商": {
        "event": "A股成交额破317万亿+两融余额2.9万亿+券商PE仅15倍(10年6%分位)+一季度净利+30%+并购重组加速",
        "boost": 0.10,
        "expires": "2026-08-31",
    },
    "金融/保险": {
        "event": "寿险改革成效显现+长端利率企稳+分红险需求旺盛",
        "boost": 0.05,
        "expires": "2026-08-15",
    },
    
    # ═══════════════════════════════════════════════════════════════
    # ── 周期/资源 (申万: 钢铁、基础化工、建筑材料、建筑装饰) ──
    # ═══════════════════════════════════════════════════════════════
    "基建/地产": {
        "event": "城市更新政策催化+房企拿地回暖+央国企主导拿地",
        "boost": 0.03,
        "expires": "2026-08-31",
    },
    
    # ═══════════════════════════════════════════════════════════════
    # ── 政策/改革 (申万: 综合) ──
    # ═══════════════════════════════════════════════════════════════
    "央企/国企改革": {
        "event": "深化国资国企改革方案(2026-2029)下发+央企市值管理考核+央企共赢ETF放量",
        "boost": 0.06,
        "expires": "2026-08-31",
    },
    
    # ═══════════════════════════════════════════════════════════════
    # ── 农业/公用事业 (申万: 农林牧渔、公用事业) ──
    # ═══════════════════════════════════════════════════════════════
    "农业/农产品": {
        "event": "粮食安全政策+猪周期底部+农产品价格企稳，中报业绩分化",
        "boost": 0.03,
        "expires": "2026-08-31",
    },
    
    # ═══════════════════════════════════════════════════════════════
    # ── 国防军工 (申万: 国防军工) ──
    # ═══════════════════════════════════════════════════════════════
    "军工": {
        "event": "美伊冲突降温+停火谈判启动+霍尔木兹重开预期→军工溢价消退",
        "boost": -0.03,
        "expires": "2026-08-18",
    },
    "航天": {
        "event": "商业航天产业化加速+卫星互联网星座建设",
        "boost": 0.08,
        "expires": "2026-08-15",
    },
    
    # ═══════════════════════════════════════════════════════════════
    # ── 贵金属/避险 (申万: 有色金属-贵金属) ──
    # ═══════════════════════════════════════════════════════════════
    "黄金": {
        "event": "多头85%超买+油价暴跌缓解通胀→黄金短期承压，但央行Q2狂买289吨长期支撑",
        "boost": -0.02,
        "expires": "2026-08-18",
    },
    
    # ═══════════════════════════════════════════════════════════════
    # ── 逆风行业 ──
    # ═══════════════════════════════════════════════════════════════
    "新能源": {
        "event": "产能过剩消化中+光伏价格战+新能源车分化，A股资金从硬科技撤离",
        "boost": -0.04,
        "expires": "2026-08-15",
    },
    "光伏": {
        "event": "产能出清中+价格战+估值承压",
        "boost": -0.05,
        "expires": "2026-08-31",
    },
    
    # ═══════════════════════════════════════════════════════════════
    # ── 补充申万一级行业 ──
    # ═══════════════════════════════════════════════════════════════
    "计算机": {
        "event": "AI应用落地+信创国产替代+软件出海",
        "boost": 0.05,
        "expires": "2026-08-15",
    },
    "机械设备": {
        "event": "工程机械周期底部+新能源设备出口+机床国产替代",
        "boost": 0.03,
        "expires": "2026-08-31",
    },
    "电气设备": {
        "event": "特高压建设+储能装机爆发+电网投资加速",
        "boost": 0.04,
        "expires": "2026-08-31",
    },
    "建筑材料": {
        "event": "水泥价格企稳+玻璃需求回暖+建材出口增长",
        "boost": 0.02,
        "expires": "2026-08-31",
    },
    "建筑装饰": {
        "event": "基建投资提速+城市更新项目+装配式建筑渗透率提升",
        "boost": 0.03,
        "expires": "2026-08-31",
    },
    "银行": {
        "event": "净息差收窄压力+资产质量改善+估值修复空间",
        "boost": 0.02,
        "expires": "2026-08-31",
    },
    "房地产": {
        "event": "政策放松预期+房企拿地回暖+城中村改造推进",
        "boost": 0.01,
        "expires": "2026-08-31",
    },
    "家用电器": {
        "event": "智能家居渗透率提升+出口增长+以旧换新政策",
        "boost": 0.03,
        "expires": "2026-08-31",
    },
    "汽车": {
        "event": "新能源车渗透率突破40%+智能驾驶落地+汽车出口增长",
        "boost": 0.04,
        "expires": "2026-08-31",
    },
    "食品饮料": {
        "event": "白酒去库存接近尾声+大众食品稳健增长+餐饮复苏",
        "boost": 0.03,
        "expires": "2026-08-31",
    },
    "农林牧渔": {
        "event": "猪周期触底回升+粮食安全政策+种业振兴加速",
        "boost": 0.02,
        "expires": "2026-08-31",
    },
    "基础化工": {
        "event": "精细化工升级+新能源材料需求+出口增长",
        "boost": 0.03,
        "expires": "2026-08-31",
    },
    "钢铁": {
        "event": "供给侧改革+基建需求+地产政策托底",
        "boost": 0.01,
        "expires": "2026-08-31",
    },
    "纺织服饰": {
        "event": "出口订单恢复+国潮品牌崛起+功能性面料升级",
        "boost": 0.02,
        "expires": "2026-08-31",
    },
    "轻工制造": {
        "event": "造纸价格企稳+家具出口回暖+文创消费升级",
        "boost": 0.02,
        "expires": "2026-08-31",
    },
    "传媒": {
        "event": "AI应用落地加速+短剧/游戏出海+IP商业化",
        "boost": 0.04,
        "expires": "2026-08-15",
    },
    "电子": {
        "event": "消费电子复苏+半导体国产化+显示面板涨价",
        "boost": 0.05,
        "expires": "2026-08-15",
    },
    "交通运输": {
        "event": "物流数字化+跨境电商增长+航空复苏",
        "boost": 0.02,
        "expires": "2026-08-31",
    },
    "商业贸易": {
        "event": "新零售转型+跨境电商增长+消费场景创新",
        "boost": 0.02,
        "expires": "2026-08-31",
    },
    "社会服务": {
        "event": "文旅复苏+教育政策放松+养老服务需求增长",
        "boost": 0.02,
        "expires": "2026-08-31",
    },
    "休闲服务": {
        "event": "旅游出行恢复+酒店RevPAR回升+免税政策优化",
        "boost": 0.02,
        "expires": "2026-08-31",
    },
    "医药生物": {
        "event": "创新药审批加速+医疗器械国产替代+CXO订单回暖",
        "boost": 0.05,
        "expires": "2026-08-15",
    },
    "环保": {
        "event": "碳中和政策+污水处理升级+固废资源化",
        "boost": 0.02,
        "expires": "2026-08-31",
    },
    "综合": {
        "event": "国企改革+资产重组+多元化经营转型",
        "boost": 0.01,
        "expires": "2026-08-31",
    },
    
    # ═══════════════════════════════════════════════════════════════
    # ── ETF特有细分行业 ──
    # ═══════════════════════════════════════════════════════════════
    "半导体设备": {
        "event": "国产替代加速+成熟制程扩产+先进封装需求",
        "boost": 0.07,
        "expires": "2026-08-15",
    },
    "医药器械": {
        "event": "国产替代+集采温和+高端设备突破",
        "boost": 0.04,
        "expires": "2026-08-15",
    },
    "中药": {
        "event": "品牌中药提价+经典名方获批+政策支持",
        "boost": 0.03,
        "expires": "2026-08-31",
    },
    "电池": {
        "event": "储能需求爆发+固态电池突破+出口增长",
        "boost": 0.03,
        "expires": "2026-08-31",
    },
    "军工电子": {
        "event": "信息化装备升级+雷达/通信需求+国产替代",
        "boost": 0.05,
        "expires": "2026-08-15",
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
    """Load latest news sentiment signals from news_sentiment.json (sector-level)."""
    if not SENT_FILE.exists():
        return {}
    try:
        with open(SENT_FILE, encoding="utf-8") as f:
            d = json.load(f)
        return d.get("sectors", {})
    except (json.JSONDecodeError, OSError):
        return {}


def get_news_boost(sector: str) -> float:
    """Get news sentiment boost for a sector (-0.1 to +0.1).

    Reads from news_sentiment.json (sector-level dynamic web search data).
    Maps: 看多强→+0.1, 看多弱→+0.05, 看空强→-0.1, 看空弱→-0.05, 中性→0.0
    """
    signals = _load_news_signals()
    if not signals:
        return 0.0

    # Direct match
    for key, value in signals.items():
        if not isinstance(value, dict):
            continue
        if key in sector or sector in key:
            direction = value.get("direction", "")
            strength = value.get("strength", "")
            boost_map = {
                ("看多", "强"): 0.10, ("看多", "中"): 0.06, ("看多", "弱"): 0.03,
                ("看空", "强"): -0.10, ("看空", "中"): -0.06, ("看空", "弱"): -0.03,
            }
            return boost_map.get((direction, strength), 0.0)

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
