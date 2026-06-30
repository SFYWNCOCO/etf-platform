"""6层因果传导模型 - ETF事件影响分析引擎
================================================================
Layer 0: 基础材料(e) → Layer 1: 事件(I0+direction) → Layer 2: 上游(d)
→ Layer 3: 中游(g) → Layer 4: 成分股(b) → Layer 5: ETF(a) + 人员(z) 跨层穿透
"""
import math, time
from ..config_loader import load_etfs

IMPACT_LEVEL = (
    (0.01, "L0", "几乎无影响", 0), (0.02, "L1", "轻微", 1),
    (0.04, "L2", "中等", 2), (0.06, "L3", "显著", 3),
    (0.10, "L4", "重大", 4), (0.15, "L5", "严重", 5),
    (0.25, "L6", "危机", 6), (0.40, "L7", "灾难性", 7),
)

SECTOR_MATERIAL_MAP = {
    "半导体": {"光刻胶": (0.90, 30, 36, 0.90), "高纯硅片": (0.85, 60, 24, 0.75)},
    "AI/科技": {"AI芯片": (0.70, 45, 18, 0.80), "GPU模块": (0.65, 30, 12, 0.70)},
    "通信/5G": {"射频芯片": (0.60, 45, 12, 0.60), "光模块": (0.55, 30, 6, 0.50)},
    "新能源": {"锂/钴": (0.75, 60, 12, 0.85), "光伏硅片": (0.70, 45, 6, 0.60)},
    "消费": {"包装材料": (0.20, 30, 3, 0.10), "食品原料": (0.30, 15, 1, 0.20)},
    "医药": {"原料药": (0.50, 45, 6, 0.60), "特殊气体": (0.40, 30, 3, 0.50)},
    "军工": {"钛合金": (0.70, 90, 12, 0.70), "军工电子": (0.65, 60, 18, 0.60)},
    "周期/资源": {"铜/铝": (0.60, 30, 3, 0.60), "稀土": (0.75, 45, 6, 0.80)},
    "金融": {"信用周期": (0.30, 30, 3, 0.20), "利率敏感性": (0.25, 15, 1, 0.15)},
    "红利/价值": {"利率敏感性": (0.15, 10, 1, 0.10)},
    "基建/地产": {"建材": (0.40, 30, 3, 0.30), "政策周期": (0.45, 15, 1, 0.20)},
    "跨境": {"汇率波动": (0.30, 10, 1, 0.50), "QDII额度": (0.40, 5, 1, 0.30)},
    "宽基": {"市场流动性": (0.10, 5, 1, 0.05)},
    "其他": {"通用风险": (0.20, 5, 1, 0.10)},
}

def _compute_vulnerability(etfs):
    vuln = {}
    for code, info in etfs.items():
        rl = info.get("risk_level", 0.5)
        vuln[code] = {
            "material": round(max(0.1, rl * 0.7), 2),
            "policy": round(max(0.1, rl * 0.5), 2),
            "tech": round(max(0.1, rl * 0.6), 2),
            "supply": round(max(0.1, rl * 0.5), 2),
            "people": round(max(0.05, rl * 0.3), 2),
            "overall": round(max(0.1, rl * 0.6), 2),
        }
    return vuln

def _compute_material_map(etfs):
    mm = {}
    for code, info in etfs.items():
        sector = info.get("sector", "其他")
        mats = SECTOR_MATERIAL_MAP.get(sector, SECTOR_MATERIAL_MAP["其他"])
        mm[code] = dict(mats)
    return mm

_etfs = None
_vuln = None
_material_map = None

def _ensure_loaded():
    global _etfs, _vuln, _material_map
    if _etfs is None:
        _etfs = load_etfs()
        _vuln = _compute_vulnerability(_etfs)
        _material_map = _compute_material_map(_etfs)

class Event:
    def __init__(self, title, etype, source_auth, impact_scope, duration_days,
                 surprise, reversibility, direction=0.0, description="",
                 affected_materials=None, affected_sectors=None, affected_people=None):
        self.title = title; self.etype = etype; self.description = description
        self.direction = max(-1.0, min(1.0, direction)); self.duration_days = duration_days
        self.priced_in = 0.0
        self.I0 = self._calc_I0(source_auth, impact_scope, duration_days, surprise, reversibility)
        self.affected_materials = affected_materials or []
        self.affected_sectors = affected_sectors or []
        self.affected_people = affected_people or {}
        self.timestamp = time.time()
        self.price_in_coefficient = 0.6

    def _calc_I0(self, auth, scope, duration, surprise, reversible):
        score = auth * 0.25 + scope * 0.30 + self._duration_score(duration) * 0.20 + surprise * 0.15 + (1.0 - reversible) * 0.10
        return round(min(score, 1.0), 4)

    def _duration_score(self, days):
        if days <= 1: return 0.2
        if days <= 3: return 0.4
        if days <= 28: return 0.6
        if days <= 180: return 0.8
        return 1.0

    def direction_label(self):
        if self.direction > 0.3: return "利好"
        if self.direction > 0.05: return "偏多"
        if self.direction < -0.3: return "利空"
        if self.direction < -0.05: return "偏空"
        return "中性"

class CausalEngine:
    def __init__(self):
        self.events = []
        self.price_in_coefficient = 0.6

    def add_event(self, event):
        self.events.append(event)

    def calc_material_epsilon(self, etf_code, event):
        _ensure_loaded()
        etf_sector = _etfs[etf_code]["sector"]
        base_epsilon = 0.1
        if event.affected_sectors:
            for sector in event.affected_sectors:
                if sector in etf_sector or etf_sector in sector:
                    base_epsilon = max(base_epsilon, 0.35)
                    break
                if ("半导体" in sector and "半导体" in etf_sector) or ("AI" in sector and "AI" in etf_sector):
                    base_epsilon = max(base_epsilon, 0.40)
        if etf_code not in _material_map or not event.affected_materials:
            return base_epsilon
        if not isinstance(event.affected_materials, dict):
            return base_epsilon
        materials = _material_map[etf_code]
        total_epsilon = 0; hit_count = 0
        for mat_name, mat_params in event.affected_materials.items():
            if mat_name not in materials: continue
            dep, stock_days, replace_months, geo_conc = materials[mat_name]
            phys_dep = mat_params.get("phys_dep", dep) * 0.40
            stock = mat_params.get("stock_days", stock_days)
            if stock < 7: stock_score = 0.9
            elif stock < 30: stock_score = 0.7
            elif stock < 60: stock_score = 0.5
            else: stock_score = 0.2
            stock_buf = stock_score * 0.25
            repl = mat_params.get("replace_months", replace_months)
            if repl > 24: repl_score = 1.0
            elif repl > 12: repl_score = 0.7
            elif repl > 6: repl_score = 0.5
            else: repl_score = 0.3
            repl_cycle = repl_score * 0.20
            geo = mat_params.get("geo_conc", geo_conc) * 0.15
            total_epsilon += phys_dep + stock_buf + repl_cycle + geo
            hit_count += 1
        material_epsilon = round(total_epsilon / hit_count if hit_count > 0 else 0.1, 4)
        return max(base_epsilon, material_epsilon)

    def calc_layer_delta(self, etf_code, event, epsilon):
        v = _vuln[etf_code]
        base_delta = (v["policy"] if event.etype == "policy" else v["tech"] if event.etype == "tech_break"
                 else v["supply"] if event.etype == "supply_chain" else v["material"] if event.etype == "material"
                 else v["people"] if event.etype == "people" else 0.3)
        return round(base_delta * (1.0 + epsilon * 0.5), 4)

    def calc_personnel_multiplier(self, etf_code, event):
        if not event.affected_people: return 1.0
        people_factor = _vuln[etf_code]["people"]
        critical = event.affected_people.get("critical", 0.5)
        replace = event.affected_people.get("replace_difficulty", 0.3)
        team_impact = event.affected_people.get("team_impact", 0.3)
        personnel = critical * 0.50 + replace * 0.30 + team_impact * 0.20
        if personnel > 0.6: return 1.3 + people_factor * 0.2
        elif personnel > 0.3: return 1.0
        else: return 0.8

    def evaluate(self, etf_code):
        _ensure_loaded()
        total_impact = 0; paths = []
        for event in self.events:
            epsilon = self.calc_material_epsilon(etf_code, event)
            delta = self.calc_layer_delta(etf_code, event, epsilon)
            gamma = round(delta * 0.7, 4); beta = round(gamma * 0.6, 4)
            alpha = round(0.08 + _etfs[etf_code]["risk_level"] * 0.35, 3)
            zeta = self.calc_personnel_multiplier(etf_code, event)
            raw_impact = event.I0 * epsilon * delta * gamma * beta * alpha * zeta
            directional_impact = round(-event.direction * raw_impact, 6)
            total_impact += directional_impact
            level = self.impact_level(abs(directional_impact))
            paths.append({"event": event.title, "I0": event.I0, "direction": event.direction,
                "e": epsilon, "d": delta, "g": gamma, "b": beta, "a": alpha, "z": zeta,
                "raw": round(raw_impact, 5), "directional": directional_impact,
                "level": level[0], "meaning": level[1]})
        total_impact = round(total_impact * self.price_in_coefficient, 6)
        return round(total_impact, 6), paths

    def impact_level(self, impact):
        for threshold, level, meaning, _ in IMPACT_LEVEL:
            if impact <= threshold: return (level, meaning)
        return ("S", "危机")

    def scan_all(self):
        _ensure_loaded()
        print("\n" + "=" * 65)
        print("  6层因果传导扫描 - 全ETF冲击评估")
        print("=" * 65)
        results = {}
        for code in sorted(_etfs.keys()):
            if code not in _etfs or code not in _vuln: continue
            if not code.isdigit(): continue
            total, paths = self.evaluate(code)
            vuln = _vuln[code]; composite_vuln = sum(vuln.values()) / len(vuln)
            results[code] = {"name": _etfs[code]["name"], "type": _etfs[code].get("type",""),
                "sector": _etfs[code].get("sector",""), "leverage": _etfs[code].get("leverage",1.0),
                "risk_level": _etfs[code].get("risk_level",0.5), "total_impact": total,
                "abs_impact": abs(total), "composite_vuln": composite_vuln, "paths": paths[:5],
                "is_safe": total < 0.0}
            if total < -0.05: flag = "++"
            elif total < -0.01: flag = "+"
            elif total < 0.01: flag = "o"
            elif total < 0.05: flag = "-"
            else: flag = "--"
            print(f"  {flag} {code:<10}{_etfs[code]['name']:<14}| {total:+.4f} | {composite_vuln:.2f}")
        return results

    def report(self, results):
        print("\n传导路径 Top5:")
        sorted_by_abs = sorted(results.items(), key=lambda x: abs(x[1]["total_impact"]), reverse=True)
        for code, data in sorted_by_abs[:5]:
            print(f"\n  {code} {data['name']} | {data['total_impact']:+.4f}")
            for i, p in enumerate(data["paths"][:3]):
                print(f"  Path {i+1}: {p['event'][:30]} -> {p['directional']:+.4f} {p['level']}")
