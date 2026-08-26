#!/usr/bin/env python3
"""L30 Multi-Agent Interaction Layer — 多智能体互动穿透层

Analyzes interactions between different types of market participants ("agents") 
in the ecosystem underlying an ETF. Draws from multi-agent systems (MAS) theory 
and complex adaptive systems principles.

Author: Agnes-2.5-Flash / Sapiens AI
Date: 2026-08-02
"""

from typing import Dict, List, Optional


def _get_agent_profile(sector: str) -> Optional[Dict]:
    """Map sector to typical agent structure characteristics."""
    if not sector:
        return None
    
    sector_lower = sector.lower()
    
    # New Energy/Clean Tech
    new_energy_keywords = ["new energy", "clean energy", "renewable", "solar", "wind", 
                           "battery", "EV", "electric vehicle", "hydrogen", "storage"]
    if any(kw in sector_lower for kw in new_energy_keywords):
        return {
            "num_agent_types": 6,
            "network_effect_strength": 0.6,
            "coordination_tendency": 0.7,
            "decentralization_level": 0.4,
        }
    
    # Digital Economy/Platforms
    digital_keywords = ["digital economy", "platform economy", "e-commerce", 
                        "social media", "marketplace", "app ecosystem", "data services",
                        "cloud computing", "digital transformation", "internet platforms"]
    if any(kw in sector_lower for kw in digital_keywords):
        return {
            "num_agent_types": 8,
            "network_effect_strength": 0.95,
            "coordination_tendency": 0.75,
            "decentralization_level": 0.3,
        }
    
    # AI/Machine Learning
    ai_keywords = ["artificial intelligence", "ai", "machine learning", "deep learning",
                   "large language model", "llm", "generative ai", "transformer",
                   "neural network", "algorithmic ai"]
    if any(kw in sector_lower for kw in ai_keywords):
        return {
            "num_agent_types": 8,
            "network_effect_strength": 0.85,
            "coordination_tendency": 0.65,
            "decentralization_level": 0.4,
        }
    
    # Semiconductor Equipment
    semiconductor_eq_keywords = ["semiconductor equipment", "semiconductor manufacturing",
                                 "chip making equipment", "semiconductor lithography",
                                 "fabrication equipment", "EDA tools", "mask making"]
    if any(kw in sector_lower for kw in semiconductor_eq_keywords):
        return {
            "num_agent_types": 5,
            "network_effect_strength": 0.7,
            "coordination_tendency": 0.75,
            "decentralization_level": 0.35,
        }
    
    # Chip/Fabrication (Foundries)
    chip_fab_keywords = ["semiconductor fabrication", "wafer foundry", "chip manufacturing",
                         "semiconductor foundry", "semiconductors", "integrated circuits"]
    if any(kw in sector_lower for kw in chip_fab_keywords):
        return {
            "num_agent_types": 6,
            "network_effect_strength": 0.75,
            "coordination_tendency": 0.65,
            "decentralization_level": 0.4,
        }
    
    # Biotechnology/Drug Discovery
    bio_keywords = ["biotechnology", "bio", "biotech", "drug discovery", "gene therapy",
                    "precision medicine", "cell therapy", "immunotherapy", "vaccine development"]
    if any(kw in sector_lower for kw in bio_keywords):
        return {
            "num_agent_types": 7,
            "network_effect_strength": 0.5,
            "coordination_tendency": 0.55,
            "decentralization_level": 0.6,
        }
    
    # Innovative Pharma
    pharma_keywords = ["pharmaceutical", "innovative drug", "biopharma", "small molecule",
                       "monoclonal antibody", "first-in-class", "new chemical entity"]
    if any(kw in sector_lower for kw in pharma_keywords):
        return {
            "num_agent_types": 6,
            "network_effect_strength": 0.6,
            "coordination_tendency": 0.6,
            "decentralization_level": 0.5,
        }
    
    # Advanced Manufacturing / Robotics
    robot_industrial_keywords = ["industrial robotics", "collaborative robot", "cobots",
                                 "smart factory", "industry 4.0", "manufacturing automation",
                                 "robotic process automation", "RPA"]
    if any(kw in sector_lower for kw in robot_industrial_keywords):
        return {
            "num_agent_types": 6,
            "network_effect_strength": 0.5,
            "coordination_tendency": 0.55,
            "decentralization_level": 0.65,
        }
    
    # Tech/Innovation
    tech_keywords = ["tech", "technology", "computer", "software", "internet", 
                     "saaS", "enterprise software", "cloud", "platform", "big data",
                     "computer", "IT", "information technology"]
    if any(kw in sector_lower for kw in tech_keywords):
        return {
            "num_agent_types": 7,
            "network_effect_strength": 0.9,
            "coordination_tendency": 0.6,
            "decentralization_level": 0.75,
        }
    
    # Financial Services
    finance_keywords = ["finance", "banking", "insurance", "securities",
                       "asset management", "investment banking", "hedge fund",
                       "fintech", "payment processing", "credit", "derivatives"]
    if any(kw in sector_lower for kw in finance_keywords):
        return {
            "num_agent_types": 8,
            "network_effect_strength": 0.7,
            "coordination_tendency": 0.8,
            "decentralization_level": 0.5,
        }
    
    # Healthcare (general)
    health_keywords = ["healthcare", "hospital", "medical devices", "telemedicine",
                       "health insurance", "treatment", "diagnosis", "clinical care"]
    if any(kw in sector_lower for kw in health_keywords):
        return {
            "num_agent_types": 5,
            "network_effect_strength": 0.4,
            "coordination_tendency": 0.45,
            "decentralization_level": 0.7,
        }
    
    # Advanced Manufacturing (traditional)
    manufacturing_keywords = ["advanced manufacturing", "industrial automation", 
                              "heavy machinery", "industrial supplies", "capital goods",
                              "equipment", "machinery", "fabricated metal products",
                              "manufacturing", "industrial"]
    if any(kw in sector_lower for kw in manufacturing_keywords):
        return {
            "num_agent_types": 5,
            "network_effect_strength": 0.5,
            "coordination_tendency": 0.6,
            "decentralization_level": 0.65,
        }
    
    # Consumer/Staples
    consumer_keywords = ["consumer", "retail", "food", "beverage", "personal care",
                        "household products", "discretionary spending", "supermarket",
                        "consumer goods"]
    if any(kw in sector_lower for kw in consumer_keywords):
        return {
            "num_agent_types": 4,
            "network_effect_strength": 0.3,
            "coordination_tendency": 0.4,
            "decentralization_level": 0.8,
        }
    
    # Energy/Resources
    energy_keywords = ["energy", "oil", "natural gas", "coal", "mining",
                       "metal", "commodity", "agriculture", "fossil fuels", "minerals"]
    if any(kw in sector_lower for kw in energy_keywords):
        return {
            "num_agent_types": 5,
            "network_effect_strength": 0.5,
            "coordination_tendency": 0.7,
            "decentralization_level": 0.6,
        }
    
    return {
        "num_agent_types": 5,
        "network_effect_strength": 0.5,
        "coordination_tendency": 0.5,
        "decentralization_level": 0.7,
    }


def _compute_coordination_density(profile: Dict, rl: float) -> float:
    """Coordination density (0-1): propensity for emergent coordinated behavior."""
    base = profile.get("coordination_tendency", 0.5)
    adjustment = 1.0 + rl * 0.3
    result = base * adjustment
    return max(0.2, min(0.95, result))


def _compute_heterogeneity(profile: Dict) -> float:
    """Agent heterogeneity (0-1): diversity of agent types & independence.

    More agent types → higher heterogeneity; decentralization further amplifies
    (distributed agents are more likely to diverge in strategy/behavior).
    """
    num_types = profile.get("num_agent_types", 4)
    # 3 types ≈ 0.35, 5 types ≈ 0.55, 8+ types ≈ 0.85 (diminishing returns)
    type_component = 0.25 + min(0.6, (num_types - 2) * 0.12)
    decentralization = profile.get("decentralization_level", 0.5)
    result = type_component * 0.7 + decentralization * 0.3
    return max(0.1, min(0.95, result))


def _compute_feedback_strength(profile: Dict) -> float:
    """Inter-agent feedback strength (0-1): intensity of reinforcing loops."""
    ne = profile.get("network_effect_strength", 0.5)
    result = ne * 0.8 + profile.get("coordination_tendency", 0.5) * 0.2
    return max(0.1, min(0.95, result))


def _compute_resilience(coord_density: float, heterogeneity: float) -> float:
    """Systemic resilience index (0-1): capacity for self-organization without collapse."""
    homo_penalty = max(0, 0.5 - heterogeneity) * 2
    coord_penalty = max(0, coord_density - 0.6) * 1.5
    base_resilience = 0.7
    result = base_resilience - homo_penalty - coord_penalty
    return max(0.1, min(0.95, result))


def _compute_l30_composite(heterogeneity: float, coordination_density: float,
                          feedback_strength: float, resilience: float) -> float:
    """Composite L30 score (0-10) aggregating all MAS metrics.

    08-12 修复：原 ×12 缩放为 0-12，与平台 0-10 约定不符，pipeline 等权
    平均时 L30 系统性超重；改 ×10。
    """
    weighted = (heterogeneity * 0.35 +
                (1.0 - feedback_strength) * 0.30 +
                resilience * 0.20 +
                (1.0 - abs(coordination_density - 0.5)) * 0.15)
    scaled = weighted * 10.0
    return max(0.0, min(10.0, scaled))


def _generate_mas_insights(heterogeneity: float, coordination_density: float,
                          feedback_strength: float, resilience: float,
                          sector: str, code: str) -> List[str]:
    """Generate MAS-based qualitative insights."""
    insights = []
    
    if heterogeneity > 0.7:
        insights.append("🔬 High agent heterogeneity supports adaptive evolution.")
    elif heterogeneity < 0.4:
        insights.append("⚠️ Low agent concentration risk.")
    else:
        insights.append("📊 Moderate agent heterogeneity offers reasonable resilience.")
    
    if feedback_strength > 0.7:
        insights.append("🔥 Strong inter-agent feedback potential for boom/bust cycles.")
    elif feedback_strength < 0.3:
        insights.append("💧 Weak feedback environment — more efficient pricing.")
    else:
        insights.append("↔ Balanced feedback suggests moderate informational efficiency.")
    
    if resilience > 0.7 and coordination_density < 0.5:
        insights.append("🏗️ Highly resilient ecosystem with sustained adaptation capacity.")
    elif resilience < 0.4:
        insights.append("🚨 Low systemic resilience — increased probability of sudden shifts.")
    else:
        insights.append("⚖️ Average resilience — monitor during heightened volatility.")
    
    return insights


def score_l30_layer(sector: str, risk_level: float, code: str = "") -> Dict:
    """Main entry point for L30 Multi-Agent Interaction layer.
    
    Computes MAS-based metrics analyzing the underlying ecosystem structure.
    
    Args:
        sector: ETF sector category
        risk_level: Risk level (0-1) from foundational layers
        code: Specific ETF code
    
    Returns:
        Dict containing score (0-12), metrics dict, and insights list
    """
    profile = _get_agent_profile(sector)
    
    if not profile:
        return {
            "score": 6.0,
            "metrics": {
                "agent_heterogeneity": 0.5,
                "coordination_density": 0.5,
                "inter_agent_feedback": 0.5,
                "systemic_resilience": 0.5
            },
            "insights": ["Sector information unavailable; default assessment applied."],
        }
    
    heterogeneity = _compute_heterogeneity(profile)
    coordination_density = _compute_coordination_density(profile, risk_level)
    feedback_strength = _compute_feedback_strength(profile)
    resilience = _compute_resilience(coordination_density, heterogeneity)
    
    l30_score = _compute_l30_composite(heterogeneity, coordination_density, 
                                      feedback_strength, resilience)
    
    insights = _generate_mas_insights(heterogeneity, coordination_density, 
                                     feedback_strength, resilience, sector, code)
    
    return {
        "score": round(l30_score, 1),
        "metrics": {
            "agent_heterogeneity": round(heterogeneity, 3),
            "coordination_density": round(coordination_density, 3),
            "inter_agent_feedback": round(feedback_strength, 3),
            "systemic_resilience": round(resilience, 3)
        },
        "insights": insights,
    }
