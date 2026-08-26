#!/usr/bin/env python3
"""L24 System Dynamics Layer — 系统动力学穿透层

Inspired by Donella Meadows' "Leverage Points" and Sterman's "Business Dynamics",
these metrics help identify ETFs with robust structural resilience versus those
prone to destabilizing dynamics under stress.

Source knowledge: k238 (systems thinking), k268 (self-improvement research with SD)
"""

from typing import Dict, Optional


def _get_sector_profile(sector: str) -> Optional[Dict]:
    """Map sector to representative SD profile characteristics."""
    if not sector:
        return None
    
    sector_lower = sector.lower()
    
    # New Energy/Clean Tech - policy-driven strong positive feedback
    new_energy_keywords = ["new energy", "clean energy", "renewable", "solar", "wind",
                           "battery", "EV", "electric vehicle", "hydrogen", "storage",
                           "新能源", "光伏", "风电", "储能", "锂电", "电池", "氢能"]
    if any(kw in sector_lower for kw in new_energy_keywords):
        return {
            "typical_fdr": 0.85,
            "typical_lp": 9.0,
            "typical_damping": 0.3,
        }
    
    # Digital Economy/Platforms
    digital_keywords = ["digital economy", "platform economy", "e-commerce",
                        "social media", "marketplace", "app ecosystem", "data services",
                        "cloud computing", "digital transformation", "internet platforms",
                        "数字经济", "互联网", "平台", "云计算", "5g", "通信"]
    if any(kw in sector_lower for kw in digital_keywords):
        return {
            "typical_fdr": 0.65,
            "typical_lp": 8.5,
            "typical_damping": 0.35,
        }
    
    # AI/Machine Learning
    ai_keywords = ["artificial intelligence", "ai", "machine learning", "deep learning",
                   "large language model", "llm", "generative ai", "transformer",
                   "neural network", "algorithmic trading ai", "人工智能", "算力"]
    if any(kw in sector_lower for kw in ai_keywords):
        return {
            "typical_fdr": 0.8,
            "typical_lp": 9.5,
            "typical_damping": 0.25,
        }
    
    # Semiconductor Equipment
    semiconductor_eq_keywords = ["semiconductor equipment", "semiconductor manufacturing",
                                 "chip making equipment", "semiconductor lithography",
                                 "fabrication equipment", "EDA tools", "mask making"]
    if any(kw in sector_lower for kw in semiconductor_eq_keywords):
        return {
            "typical_fdr": 0.15,
            "typical_lp": 7.0,
            "typical_damping": 0.8,
        }
    
    # Chip/Fabrication (Foundries)
    chip_fab_keywords = ["semiconductor fabrication", "wafer foundry", "chip manufacturing",
                         "semiconductor foundry", "semiconductors", "integrated circuits",
                         "半导体", "芯片", "集成电路"]
    if any(kw in sector_lower for kw in chip_fab_keywords):
        return {
            "typical_fdr": 0.6,
            "typical_lp": 8.0,
            "typical_damping": 0.35,
        }
    
    # Biotechnology/Drug Discovery
    bio_keywords = ["biotechnology", "bio", "biotech", "drug discovery", "gene therapy",
                    "precision medicine", "cell therapy", "immunotherapy", "vaccine development",
                    "医药", "生物", "创新药", "医疗器械", "疫苗", "制药"]
    if any(kw in sector_lower for kw in bio_keywords):
        return {
            "typical_fdr": 0.15,
            "typical_lp": 7.5,
            "typical_damping": 1.1,
        }
    
    # Innovative Pharma
    pharma_keywords = ["pharmaceutical", "innovative drug", "biopharma", "small molecule",
                       "monoclonal antibody", "first-in-class", "new chemical entity"]
    if any(kw in sector_lower for kw in pharma_keywords):
        return {
            "typical_fdr": 0.25,
            "typical_lp": 8.0,
            "typical_damping": 1.0,
        }
    
    # Advanced Manufacturing / Robotics
    robot_industrial_keywords = ["industrial robotics", "collaborative robot", "cobots",
                                 "smart factory", "industry 4.0", "manufacturing automation",
                                 "robotic process automation", "RPA", "军工", "机器人", "自动化"]
    if any(kw in sector_lower for kw in robot_industrial_keywords):
        return {
            "typical_fdr": 0.4,
            "typical_lp": 6.5,
            "typical_damping": 0.7,
        }
    
    # Traditional Tech/Software
    tech_keywords = ["tech", "technology", "computer", "software", "internet",
                     "saaS", "enterprise software", "cloud", "platform", "big data",
                     "软件", "计算机", "电子", "信息技术"]
    if any(kw in sector_lower for kw in tech_keywords):
        return {
            "typical_fdr": 0.75,
            "typical_lp": 8.2,
            "typical_damping": 0.4,
        }
    
    # Financial Services
    finance_keywords = ["finance", "banking", "insurance", "securities",
                       "asset management", "investment banking", "hedge fund",
                       "fintech", "payment processing", "credit", "derivatives",
                       "金融", "银行", "证券", "保险", "地产"]
    if any(kw in sector_lower for kw in finance_keywords):
        return {
            "typical_fdr": 0.4,
            "typical_lp": 7.5,
            "typical_damping": 0.5,
        }
    
    # Healthcare (general)
    health_keywords = ["healthcare", "hospital", "medical devices", "telemedicine",
                       "health insurance", "treatment", "diagnosis", "医疗", "健康"]
    if any(kw in sector_lower for kw in health_keywords):
        return {
            "typical_fdr": 0.0,
            "typical_lp": 5.5,
            "typical_damping": 0.95,
        }
    
    # Advanced Manufacturing / Industrial
    manufacturing_keywords = ["advanced manufacturing", "industrial automation",
                              "heavy machinery", "industrial supplies", "capital goods",
                              "equipment", "machinery", "fabricated metal products",
                              "制造", "机械", "工业", "基建", "高端装备"]
    if any(kw in sector_lower for kw in manufacturing_keywords):
        return {
            "typical_fdr": 0.1,
            "typical_lp": 5.5,
            "typical_damping": 0.95,
        }
    
    # Consumer/Staples
    consumer_keywords = ["consumer", "retail", "food", "beverage", "personal care",
                        "household products", "discretionary spending", "supermarket",
                        "consumer goods", "消费", "食品", "饮料", "零售", "红利", "养殖"]
    if any(kw in sector_lower for kw in consumer_keywords):
        return {
            "typical_fdr": -0.5,
            "typical_lp": 5.0,
            "typical_damping": 0.9,
        }
    
    # Energy/Resources
    energy_keywords = ["energy", "oil", "natural gas", "coal", "mining",
                       "metal", "commodity", "agriculture", "fossil fuels", "minerals",
                       "能源", "石油", "煤炭", "资源", "周期", "化工", "有色", "钢铁",
                       "贵金属", "黄金", "农业", "公用事业"]
    if any(kw in sector_lower for kw in energy_keywords):
        return {
            "typical_fdr": -0.2,
            "typical_lp": 6.5,
            "typical_damping": 0.65,
        }
    
    return {
        "typical_fdr": 0.3,
        "typical_lp": 6.0,
        "typical_damping": 0.7,
    }


def _compute_feedback_ratio(profile: Dict) -> float:
    """Compute FDR from raw input, scaled and bounded [-1, 1]."""
    raw = profile.get("typical_fdr", 0.0)
    # deterministic: no jitter — same input must yield identical score/insights (T9)
    result = raw * 0.92
    return max(-1.0, min(1.0, result))


def _compute_leverage_points(profile: Dict) -> float:
    """Compute LP score on [0, 10] scale."""
    base = profile.get("typical_lp", 5.0)
    result = base * 0.95
    return max(0.0, min(10.0, result))


def _compute_damping_ratio(profile: Dict) -> float:
    """Compute approximate damping ratio ζ."""
    raw = profile.get("typical_damping", 0.7)
    result = raw * 0.98
    return max(0.3, min(1.5, result))


def _compute_resonance_risk(fdr: float, damping: float) -> float:
    """Resonance risk index combining feedback strength and damping quality."""
    fdr_weight = max(0, (fdr + 1) / 2) if fdr > 0 else 0
    damping_penalty = max(0, 1 - damping / 1.0)
    risk = fdr_weight * damping_penalty * 1.0
    return max(0.0, min(1.0, risk))


def _compute_sd_composite(fdr: float, lp: float, damping: float, rr: float) -> float:
    """Final composite SD score calculation (0-10 scale, consistent with all layers).

    Relative weights preserved from original (5:4:3:2), only scale capped 15→10.
    """
    fdr_comp = (1 - abs(fdr)) * 5.0
    lp_comp = (lp / 10.0) * 4.0
    damp_comp = (1 - abs(damping - 1.0)) * 3.0
    rr_comp = (1 - rr) * 2.0

    total = fdr_comp + lp_comp + damp_comp + rr_comp
    scaled = total * (10.0 / 14.0)
    return max(0.0, min(10.0, scaled))


def _generate_insights(fdr: float, lp: float, damping: float, rr: float, 
                      sector: str, code: str) -> list:
    """Generate human-readable qualitative insights from SD metrics."""
    insights = []

    if fdr > 0.6:
        insights.append("⚠️ Strong positive feedback detected: momentum-driven regime with bubble potential.")
    elif fdr < -0.6:
        insights.append("💼 Dominant mean-reversion feedback: defensive characteristics suited for contrarian positioning.")
    else:
        insights.append("🔄 Mixed feedback pattern: monitor regime shifts closely.")

    if lp > 7:
        insights.append(f"🔑 High leverage point potential ({lp:.1f}/10): multiple intervention opportunities.")
    elif lp > 4:
        insights.append(f"📍 Moderate leverage point relevance ({lp:.1f}/10): some structural windows available.")
    else:
        insights.append(f"📉 Low leverage point activity ({lp:.1f}/10): focus on micro-level factors instead.")

    if damping < 0.6:
        insights.append("📉 Underdamped system: pronounced oscillations expected after shocks.")
    elif damping > 1.2:
        insights.append("⏳ Overdamped system: slow adjustment to new fundamentals may lag developments.")
    else:
        insights.append("⚖️ Near-critically damped response: stable equilibrium-seeking behavior.")

    if rr > 0.6:
        insights.append("🔴 HIGH resonance risk: dangerous combination of strong feedback + weak damping.")
    elif rr > 0.3:
        insights.append("🟡 Elevated resonance risk: monitor for accelerating positive feedback or liquidity drying up.")
    else:
        insights.append("🟢 Low resonance risk: system appears robust against destabilizing amplification.")

    return insights


def score_l24_layer(sector: str, risk_level: float, code: str = "") -> Dict:
    """Main entry point for L24 System Dynamics layer."""
    profile = _get_sector_profile(sector)

    if not profile:
        return {
            "score": 5.0,
            "metrics": {"feedback_ratio": 0.0, "leverage_point_score": 5.0,
                       "damping_ratio": 1.0, "resonance_risk": 0.1},
            "insights": ["Sector information missing; using conservative assessment."],
        }

    fdr = _compute_feedback_ratio(profile)
    lp = _compute_leverage_points(profile)
    damping = _compute_damping_ratio(profile)
    resonance = _compute_resonance_risk(fdr, damping)
    sd_score = _compute_sd_composite(fdr, lp, damping, resonance)

    insights = _generate_insights(fdr, lp, damping, resonance, sector, code)

    return {
        "score": round(sd_score, 1),
        "metrics": {
            "feedback_ratio": round(fdr, 3),
            "leverage_point_score": round(lp, 2),
            "damping_ratio": round(damping, 3),
            "resonance_risk": round(resonance, 3)
        },
        "insights": insights,
    }
