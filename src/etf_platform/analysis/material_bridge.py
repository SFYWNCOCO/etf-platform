# -*- coding: utf-8 -*-
"""material_bridge.py — deep.py material/personnel/tech signals -> L3-L7 scoring

Bridges 3 data sources into layer scores:
  MATERIAL_PRICE_MONITOR -> L3(material safety), L4(supply chain)
  PERSONNEL_RISK_DB      -> L6(politics/governance risk)
  TECH_MILESTONES_V2     -> L5(tech barrier), L7(irreplaceable)

v6.2: Merges material_capacity.json (253 materials, different field names).

Signal formula:
  material_signal = direction * bottleneck_risk * (1 - substitution_years/10) * scale
"""
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _get_material_signals():
    """Get all materials from deep.py with caching.
    
    v6.2: Also loads material_capacity.json (253 materials) and merges
    them into the pipeline. Field name mapping:
      cap.json `etfs` → `affects`
      cap.json `supply_risk`(高/中/低) → `bottleneck_risk`(0.7/0.5/0.3)
      cap.json `trend`(↑/↓/→) → `impact_direction`(利好/利空/中性)
    """
    try:
        from .deep import get_all_materials
        merged = get_all_materials()
    except (KeyError, ValueError, TypeError, AttributeError, ImportError):
        merged = {}
    
    # Merge material_capacity.json (253 materials, different field names)
    try:
        _cap_path = Path(__file__).resolve().parent.parent.parent.parent / "data" / "material_capacity.json"
        if _cap_path.exists():
            with open(_cap_path, "r") as f:
                cap_data = json.load(f)
        
        SR_MAP = {"极高": 0.95, "高": 0.7, "中": 0.5, "低": 0.3}
        TREND_MAP = {
            "↑": "利好", "↓": "利空", "→": "中性",
            "上涨": "利好", "下跌": "利空", "平稳": "中性",
        }
        
        for mat_name, mat in cap_data.items():
            if mat_name in merged:
                # Already in deep.py — keep deep.py's version (has richer field data)
                continue
            
            # Convert field names
            supply_risk = str(mat.get("supply_risk", "低"))
            trend_str = str(mat.get("trend", "→"))
            
            # Map supply_risk → bottleneck_risk
            bottleneck = SR_MAP.get(supply_risk, 0.3)
            
            # Map trend → impact_direction
            impact = "中性"
            for key, val in TREND_MAP.items():
                if key in trend_str:
                    impact = val
                    break
            
            merged[mat_name] = {
                "affects": mat.get("etfs", []),
                "impact_direction": impact,
                "bottleneck_risk": bottleneck,
                "substitution_years": 3,  # default
                "technology_readiness": 7,  # default
                "warning": f"来自material_capacity: {supply_risk}风险, {mat.get('capacity_level','')}",
                "_source": "material_capacity.json",  # source marker
            }
    except (IOError, OSError, json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
        logger.debug("material_capacity merge failed: %s", e)
        pass

    return merged

def _get_personnel_risks():
    try:
        from .deep import PERSONNEL_RISK_DB
        return PERSONNEL_RISK_DB
    except (KeyError, ValueError, TypeError, AttributeError, ImportError):
        return []

def _get_tech_milestones():
    try:
        from .deep import TECH_MILESTONES_V2
        return TECH_MILESTONES_V2
    except (KeyError, ValueError, TypeError, AttributeError, ImportError):
        return []


def material_layer_adjustments(etf_code: str) -> dict:
    """Calculate L3-L7 adjustments from deep.py data for a given ETF.

    Returns: {layer: adjustment_value} where positive = bonus, negative = penalty
    """
    adjustments = {"L3_Material": 0.0, "L4_SupplyChain": 0.0,
                   "L5_Tech": 0.0, "L6_Politics": 0.0, "L7_Irreplaceable": 0.0}
    
    # === 1. Material price signals -> L3, L4 ===
    materials = _get_material_signals()
    mat_signals = []
    for mat_name, mat in materials.items():
        if etf_code not in mat.get("affects", []):
            continue
        
        direction = 0
        impact = mat.get("impact_direction", "")
        if impact == "利空": direction = -1
        elif impact == "利好": direction = +1
        elif "利空" in str(impact): direction = -1
        elif "利好" in str(impact): direction = +1
        
        if direction == 0:
            continue
        
        bottleneck = mat.get("bottleneck_risk", 0.5)
        sub_years = mat.get("substitution_years", 5)
        tech_readiness = mat.get("technology_readiness", 5)
        
        # Signal = direction * bottleneck * (1-sub_years/10) * readiness_factor
        # High bottleneck + low substitution -> strong signal
        signal = direction * bottleneck * max(0.1, (1 - sub_years/10)) * (tech_readiness / 10)
        mat_signals.append((mat_name, signal, mat.get("warning", ""), bottleneck))
    
    if mat_signals:
        # Aggregate: sum of all material signals, capped at +/- 2.0
        total_signal = sum(s for _, s, _, _ in mat_signals)
        total_signal = max(-2.0, min(2.0, total_signal))
        
        # Materials affect L3 (material safety) and L4 (supply chain)
        # v8.31: L3 gets the full material signal. L4 gets minimal material signal
        # (only 10%) because L4 should measure supply chain structure, not material prices.
        # The bulk of L4 differentiation comes from SUPPLY_CHAIN_MODULATION in apply_to_layers.
        adjustments["L3_Material"] = round(total_signal * 0.7, 2)
        adjustments["L4_SupplyChain"] = round(total_signal * 0.1, 2)
    
    # === 2. Personnel risks -> L6 ===
    personnel = _get_personnel_risks()
    personnel_signal = 0.0
    for p in personnel:
        if etf_code not in p.get("affects_etf", []):
            continue
        
        irreplaceable = p.get("irreplaceable", 0.5)
        age = p.get("age") or 60
        age_risk = 0.0
        if age > 70: age_risk = 0.15
        elif age > 65: age_risk = 0.10
        elif age > 60: age_risk = 0.05
        
        impact = p.get("impact", 0)
        # Personnel risk: always negative (penalty)
        p_signal = -(irreplaceable * 0.6 + age_risk) * abs(impact) * 10
        personnel_signal += p_signal
    
    if personnel_signal != 0:
        adjustments["L6_Politics"] = round(personnel_signal, 2)
    
    # === 3. Tech milestones -> L5, L7 ===
    milestones = _get_tech_milestones()
    tech_signal = 0.0
    for m in milestones:
        if etf_code not in m.get("affects", []):
            continue
        
        prob = m.get("probability", 0.5)
        # Count completed steps
        completed = sum(1 for s in m["milestones"] if "完成" in s.get("status", ""))
        total = len(m["milestones"])
        progress = completed / total if total > 0 else 0
        
        # Signal: above 50% prob = positive, progress matters
        t_signal = (prob - 0.5) * progress * 3.0
        tech_signal += t_signal
    
    if tech_signal != 0:
        adjustments["L5_Tech"] = round(tech_signal, 2)
        adjustments["L7_Irreplaceable"] = round(tech_signal * 0.5, 2)
    else:
        # v8.17: For ETFs without tech milestone data (majority), add code-based
        # micro-jitter to L7 to break intra-sector clustering. The sector_layer_scores
        # gives a base score, but without real milestone data all ETFs in the same
        # sector get identical L7. Code jitter adds deterministic differentiation.
        if etf_code and etf_code.isdigit():
            digits = etf_code
            h = 0
            for d in digits:
                h = (h * 31 + int(d)) % 10000
            l7_jitter = (h / 10000.0 * 2 - 1) * 0.6  # range [-0.6, +0.6]
            adjustments["L7_Irreplaceable"] = round(l7_jitter, 2)
    
    return adjustments




# === Sector-based inference for uncovered ETFs ===
# Maps sectors to their "anchor" ETFs that have real material data
SECTOR_ANCHORS = {
    "半导体": ["159995", "512480", "512760"],
    "新能源": ["515030", "516160"],
    "AI/科技": ["159819", "515050"],
    "军工": ["512660", "512670"],
    "医药": ["159992", "512170"],
    "硬科技": ["588000", "159995"],
    "红利/价值": ["563300", "512040"],
    "金融": ["512880"],
    "通信/5G": ["515050", "515880"],
    "消费": ["512690"],
    # === v6.7: Expanded sector anchors for previously uncovered sectors ===
    "宽基":         ["159363", "159382", "510300", "510050", "159915", "159949", "159901"],
    "跨境":         ["513280", "513290", "513500"],
    "周期/资源":    ["159870", "512400", "517400", "518660"],
    "贵金属":       ["518880", "159934"],
    "有色金属":     ["159870", "512400"],
    "能源化工":     ["159981", "510300"],
    "家电":         ["159996", "159994"],
    "白酒消费":     ["512690", "159928"],
    "公用事业":     ["159326", "516160"],
    "基金/综合":    ["159053", "159141", "159055", "159208"],
    "中盘成长":     ["510500", "159915"],
    "小盘价值":     ["512100", "159345"],
    "信用债":       ["511220", "110030"],
    "利率债":       ["511010", "511260"],
    "可转债":       ["511380", "110059"],
    "货币":         ["511880", "511990", "511660"],
    "货币基金":     ["511880", "511990"],
    # === v6.7: Cross-sector anchors for uncovered sectors ===
    # These use the closest related sector's material data as proxy
    "家电":         ["159732", "159928"],  # 消费电子/消费ETF有材料数据  # noqa: F601
    "机器人/智造":  ["159819", "512760"],  # proxies from AI/半导体
    "其他":         ["518600", "159053"],  # has data (gold/rare metals)
    "综合":         ["159053", "159141", "159208"],  # rare metals, AI, aerospace have data
    "港股科技":     ["159819", "159262"],  # proxy — canonical value at L259 below
    "港股综合":     ["159920", "159141"],  # proxy — canonical value at L261 below
    "央企改革":     ["512950", "510150"],
    "基建/地产":    ["159519", "512200"],
    "农产品":       ["159985", "159825"],
    "保险":         ["167301", "512000"],
    "券商":         ["512000", "512670"],
    "半导体设备":   ["159516", "512480"],
    "半导体杠杆":   ["L2X芯片", "512480"],
    "半导体做空":   ["S芯片", "512480"],
    "硬科技杠杆":   ["L2X科创", "588000"],
    "硬科技做空":   ["S科创", "588000"],
    "AI算力":       ["159819", "515050"],
    "云计算/算力":  ["159819", "515050"],
    "通信/光模块":  ["515050", "515880"],
    "5G/PCB":       ["515880", "515050"],
    "电子":         ["515260", "159819"],
    "计算机":       ["512720", "159819"],
    "港股科技":     ["159262", "159636"],  # noqa: F601
    "港股医药":     ["159506", "159570"],
    "港股综合":     ["159920", "159605"],  # noqa: F601
    "美股科技":     ["159509", "513100"],
    "美股科技100":  ["159941", "513100"],
    "美股综合":     ["159659", "513500"],
    "美股杠杆":     ["L2X纳指"],
    "中概互联网":   ["159605", "513050"],
    "红利价值":     ["512890", "563300"],
    "红利+低波":    ["512890", "563300"],
    "高股息":       ["512890", "563300"],
    "债券":         ["511010", "511220", "511380"],
    "中药":         ["159842", "159992"],
    "医药器械":     ["159898", "159506"],
    "黄金":         ["518880", "159934"],
    "黄金股":       ["518880", "159937"],
    "食品饮料":     ["512690", "159928"],
    "养殖":         ["159865", "159999"],
    "农牧":         ["159865", "159999"],
    "白酒":         ["512690", "159928"],
    "传媒":         ["512980", "159869"],
    "房地产":       ["159981", "512200"],
    "建筑":         ["159519", "516160"],
    "环保":         ["159811", "512500"],
    "交通运输":     ["159761", "516680"],
    "煤炭":         ["159870", "515220"],
    "化工":         ["159870", "517010"],
    "有色":         ["159870", "512400"],
    "电池":         ["159755", "159566"],
    "风电":         ["516160", "159609"],
    "新能源车":     ["515030", "159755"],
    "航空":         ["516670", "159790"],
    "航天":         ["512660", "159206"],
    "医疗":         ["159992", "159506"],
    "创新药":       ["159992", "159506"],
    "银行":         ["512800", "515200"],
    }

# Related sector groups for cross-sector inference
SECTOR_GROUPS = {
    "tech": ["半导体", "半导体设备", "半导体杠杆", "半导体做空", "AI/科技", "硬科技", "硬科技杠杆", "硬科技做空", "通信/5G", "电子", "通信/光模块", "5G/PCB", "机器人/智造", "计算机", "AI算力", "云计算/算力", "中概互联网"],
    "defense": ["军工", "航空航天"],
    "energy": ["新能源", "周期/资源", "有色", "有色金属", "煤炭", "化工", "能源化工", "光伏", "电池", "风电", "新能源车"],
    "healthcare": ["医药", "医疗", "创新药", "医疗器械", "医药器械", "港股医药", "中药"],
    "finance": ["金融", "证券", "银行", "保险", "券商", "信用债", "利率债", "可转债", "货币", "货币基金", "红利/价值", "红利价值", "红利+低波", "高股息"],
    "consumer": ["消费", "白酒", "食品饮料", "家电", "白酒消费", "养殖", "农牧", "农产品", "传媒"],
    "broad": ["宽基", "综合", "跨境", "中盘成长", "小盘价值", "大盘蓝筹", "成长股", "全市场", "其他", "贵金属"],
    "us_equity": ["美股科技", "美股科技100", "美股综合", "美股杠杆", "港股科技", "港股综合"],
    "infra": ["基建/地产", "公用事业", "央企改革", "交通运输", "环保", "房地产", "建筑"],
}

def _get_sector_group(sector):
    for group, sectors in SECTOR_GROUPS.items():
        if sector in sectors:
            return group
    return None

def sector_inferred_adjustments(etf_code: str, sector: str) -> dict:
    """Infer material adjustments for ETFs without direct deep.py coverage.
    
    Strategy: find anchor ETFs in the same sector that have real material data,
    average their adjustments, and apply with a discount factor.
    """
    # If this ETF already has direct coverage, skip inference
    direct = material_layer_adjustments(etf_code)
    has_direct = any(abs(v) > 0.001 for v in direct.values())
    if has_direct:
        return direct
    
    # Find anchor ETFs in same sector
    anchors = SECTOR_ANCHORS.get(sector, [])
    
    # If no direct sector anchors, try related sectors
    if not anchors:
        group = _get_sector_group(sector)
        if group:
            for related_sector, related_anchors in SECTOR_ANCHORS.items():
                if _get_sector_group(related_sector) == group:
                    anchors.extend(related_anchors)
            anchors = list(set(anchors))  # dedupe
    
    if not anchors:
        return {"L3_Material": 0.0, "L4_SupplyChain": 0.0,
                "L5_Tech": 0.0, "L6_Politics": 0.0, "L7_Irreplaceable": 0.0}
    
    # Compute average adjustment from anchors
    anchor_adjs = []
    for anchor_code in anchors:
        if anchor_code == etf_code:
            continue
        adj = material_layer_adjustments(anchor_code)
        anchor_adjs.append(adj)
    
    # If all anchors returned zero, try cross-sector group fallback
    if not anchor_adjs:
        group = _get_sector_group(sector)
        if group:
            for related_sector, related_anchors in SECTOR_ANCHORS.items():
                if _get_sector_group(related_sector) == group and related_sector != sector:
                    for ra in related_anchors:
                        if ra != etf_code:
                            adj = material_layer_adjustments(ra)
                            if any(abs(v) > 0.001 for v in adj.values()):
                                anchor_adjs.append(adj)
        if not anchor_adjs:
            # v6.7: Global average fallback instead of zeros
            # Most covered ETFs have positive L3 adjustments (bottleneck premium)
            return {"L3_Material": 0.3, "L4_SupplyChain": 0.2,
                    "L5_Tech": 0.1, "L6_Politics": -0.1, "L7_Irreplaceable": 0.1}
    
    # Average across anchors
    avg = {}
    for layer in ["L3_Material", "L4_SupplyChain", "L5_Tech", "L6_Politics", "L7_Irreplaceable"]:
        vals = [a.get(layer, 0) for a in anchor_adjs]
        avg[layer] = sum(vals) / len(vals)
    
    # Discount factor: more anchors = higher confidence
    n_anchors = len(anchor_adjs)
    if n_anchors >= 3:
        discount = 0.7
    elif n_anchors >= 2:
        discount = 0.6
    else:
        discount = 0.4
    
    # Apply discount
    result = {}
    for layer, val in avg.items():
        result[layer] = round(val * discount, 2)
    
    return result


# v8.31: Supply chain modulation map for L4 independence from L3.
# Breaks the r=0.905 L3-L4 redundancy by adding sector-level supply chain
# risk signals that are independent of material price signals.
# Modulation range: [-3.0, +3.0] to meaningfully shift L4 away from L3 trajectory.
SUPPLY_CHAIN_MODULATION = {
    # High supply chain risk (fragile, import-dependent, sanction-vulnerable)
    "半导体": 2.5, "半导体设备": 3.0, "半导体杠杆": 2.5, "半导体做空": -2.5,
    "AI/科技": 1.8, "硬科技": 2.0, "硬科技杠杆": 1.8, "硬科技做空": -1.8,
    "军工": 2.0, "航空航天": 2.0,
    "通信/5G": 1.8, "通信/光模块": 1.8, "5G/PCB": 1.8,
    "电子": 1.5, "计算机": 1.2, "机器人/智造": 1.5,
    "AI算力": 1.5, "云计算/算力": 1.5,
    "中概互联网": 1.2,
    # Medium supply chain risk
    "新能源": 1.0, "光伏": 0.8, "风电": 0.8, "电池": 0.8, "新能源车": 0.8,
    "医药": 0.8, "医疗": 0.8, "创新药": 0.8, "中药": 0.5,
    "医疗器械": 0.8, "医药器械": 0.8, "港股医药": 0.8,
    "消费": 0.5, "白酒": 0.3, "食品饮料": 0.3, "白酒消费": 0.3,
    "家电": 0.5, "养殖": 0.5, "农牧": 0.5, "农产品": 0.5,
    "金融": 0.0, "银行": 0.0, "券商": 0.0, "保险": 0.0,
    "跨境": 1.0, "港股科技": 1.0, "港股综合": 0.8,
    "美股科技": 0.8, "美股科技100": 0.8, "美股综合": 0.5, "美股杠杆": 0.8,
    # Low supply chain risk (stable, domestic, regulated)
    "公用事业": -2.0, "红利/价值": -1.5, "红利价值": -1.5, "高股息": -1.5,
    "红利+低波": -1.5, "红利低波": -1.5, "自由现金流": -1.5,
    "宽基": -1.0, "综合": -1.0, "大盘蓝筹": -1.0, "全市场": -1.0,
    "上证50": -1.0, "沪深300": -1.0, "中证500": -1.0, "中证1000": -1.0,
    "中盘成长": -1.0, "小盘价值": -1.0, "成长股": -1.0, "创业板": -0.8,
    "黄金": -1.5, "贵金属": -1.5, "黄金股": -1.5,
    "有色金属": -0.8, "周期/资源": -0.8, "煤炭": -0.8, "化工": -0.5,
    "能源化工": -0.8, "建筑": -1.0, "基建/地产": -1.0, "房地产": -1.0,
    "环保": -1.2, "交通运输": -0.8, "央企改革": -0.8,
    "债券": -1.5, "利率债": -1.8, "信用债": -1.5, "可转债": -1.2,
    "货币": -1.8, "货币基金": -1.8,
    "传媒": -0.5, "游戏": -0.5, "旅游": -0.5,
    "航空": -0.8, "航天": 2.0,
    "其他": 0.0,
}


def apply_to_layers(etf_code: str, layer_scores: dict, sector: str = None) -> dict:
    """Apply material/personnel/tech adjustments to layer scores in-place.
    
    Uses sector inference for ETFs without direct coverage.
    Returns the modified layer_scores dict.
    """
    adjustments = material_layer_adjustments(etf_code)
    
    # If no direct data, try sector inference
    has_direct = any(abs(v) > 0.001 for v in adjustments.values())
    if not has_direct and sector:
        adjustments = sector_inferred_adjustments(etf_code, sector)
    
    # v8.31: Add independent supply chain modulation to L4 to break L3-L4 redundancy.
    # L4 measures supply chain disruption risk (import dependence, sanctions, etc.)
    # which is fundamentally different from L3's material price safety.
    if sector and sector in SUPPLY_CHAIN_MODULATION:
        sc_mod = SUPPLY_CHAIN_MODULATION[sector]
        adjustments["L4_SupplyChain"] = round(
            adjustments.get("L4_SupplyChain", 0) + sc_mod, 2
        )
    
    for layer, adj in adjustments.items():
        if layer in layer_scores and adj != 0:
            old = layer_scores[layer]
            # v8.35: Ceiling-aware — prevent material_bridge from undoing ceiling_break.
            # After ceiling_break modulation, scores near 9.0+ with material_bridge +1.0+
            # can push back to 10.0. Cap positive adjustments for high-scoring layers.
            if layer == "L3_Material" and old > 8.5 and adj > 0:
                headroom = 10.0 - old
                if headroom < 0.5:
                    adj = adj * (headroom - 0.1) / 0.5
            layer_scores[layer] = round(max(1.0, min(10.0, old + adj)), 1)
    
    return layer_scores