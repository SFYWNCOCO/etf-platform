"""
l21_investment_psychology.py — Investment Psychology Bias Layer v1.0

Source: knowledge_base k180 (Investment Psychology / Behavioral Finance Biases)

Layer Design:
  - Maps industry/sector to common investor psychological biases
  - L21_Behavior score = (10 - sector_risk_score), higher = lower bias risk = more rational behavior
  - Provides specific bias types and mitigation suggestions
  - Complements L14_StoicRisk (dichotomy of control), L20_OptionVol (psychological strategy)

Sub-layers:
  L21_Behavior       — Sector bias composite score
  L21_Herding        — Herd behavior strength
  L21_Disposition    — Disposition effect / loss aversion risk
  L21_Overreaction   — Overreaction (recency / confirmation bias)
  L21_Contrarian     — Contrarian signal quality (non-consensus opportunities)
  L21_Attention      — Attention bias (hot search / news-driven trading)

Scoring: 0-10, higher score = lower behavioral risk (more rational)
"""
from typing import Dict
import copy


# === Sector to bias risk map (k180) ===

BIAS_RISK_MAP: Dict[str, Dict] = {
    "AI/科技": {
        "overconfidence": True, "recency_bias": True, "herd": True,
        "anchoring": False, "loss_aversion": False, "confirmation_bias": False,
        "sunk_cost": False, "FOMO": False, "regret_aversion": False,
        "disposition_effect": False, "mental_accounting": False,
        "risk_score": 7.5,
        "bias_note": "overconfidence + recency bias + herd behavior",
        "mitigation": [
            "Set hard stop-loss line (e.g. -15%), avoid over-chasing rallies",
            "Reverse check: write down 3 bearish reasons before deciding",
        ],
    },
    "半导体": {
        "overconfidence": True, "recency_bias": False, "herd": True,
        "anchoring": True, "loss_aversion": False, "confirmation_bias": False,
        "sunk_cost": False, "FOMO": False, "regret_aversion": False,
        "disposition_effect": False, "mental_accounting": False,
        "risk_score": 7.0,
        "bias_note": "anchoring effect (historical cost basis) + herd chasing hot sectors",
        "mitigation": [
            "Do not anchor on cost basis; re-evaluate based on future value",
            "Buy in 3 tranches, wait >= 1 week between each to observe",
        ],
    },
    "红利低波": {
        "overconfidence": False, "recency_bias": False, "herd": False,
        "anchoring": False, "loss_aversion": True, "confirmation_bias": False,
        "sunk_cost": False, "FOMO": False, "regret_aversion": False,
        "disposition_effect": False, "mental_accounting": True,
        "risk_score": 3.0,
        "bias_note": "loss aversion + mental accounting (treating dividend ETF as deposit)",
        "mitigation": [
            "Treat dividend reinvestment as separate account, do not confuse with principal",
            "Focus on valuation not historical price, avoid price anchoring",
        ],
    },
    "宽基": {
        "overconfidence": False, "recency_bias": False, "herd": True,
        "anchoring": False, "loss_aversion": False, "confirmation_bias": False,
        "sunk_cost": False, "FOMO": False, "regret_aversion": False,
        "disposition_effect": False, "mental_accounting": False,
        "risk_score": 4.0,
        "bias_note": "herd behavior (blindly following index investing trends)",
        "mitigation": [
            "DCA (dollar-cost averaging) to avoid timing impulses",
            "Compare fee differences; do not just pick the hottest fund",
        ],
    },
    "军工": {
        "overconfidence": True, "recency_bias": False, "herd": False,
        "anchoring": False, "loss_aversion": False, "confirmation_bias": True,
        "sunk_cost": False, "FOMO": False, "regret_aversion": False,
        "disposition_effect": False, "mental_accounting": False,
        "risk_score": 6.5,
        "bias_note": "confirmation bias (only looking at bullish policy/orders)",
        "mitigation": [
            "Proactively search for bearish catalysts: defense budget cuts, qualification cancellations",
            "Set target profit levels and take partial profits incrementally",
        ],
    },
    "黄金": {
        "overconfidence": False, "recency_bias": True, "herd": False,
        "anchoring": False, "loss_aversion": False, "confirmation_bias": False,
        "sunk_cost": False, "FOMO": False, "regret_aversion": False,
        "disposition_effect": False, "mental_accounting": False,
        "risk_score": 2.5,
        "bias_note": "recency bias (chasing highs after gold price hits new records)",
        "mitigation": [
            "After 5 consecutive up days, pause additions and wait for pullback",
            "Use gold as hedge allocation, keep under 15% of total portfolio",
        ],
    },
    "医药": {
        "overconfidence": False, "recency_bias": False, "herd": False,
        "anchoring": False, "loss_aversion": True, "confirmation_bias": False,
        "sunk_cost": False, "FOMO": False, "regret_aversion": False,
        "disposition_effect": True, "mental_accounting": False,
        "risk_score": 5.5,
        "bias_note": "disposition effect (cannot hold winners, stubbornly holds losers) + loss aversion",
        "mitigation": [
            "Strictly execute profit-taking discipline on winning positions, avoid greed",
            "Use fundamentals not price to decide whether to continue holding losers",
        ],
    },
    "新能源": {
        "overconfidence": True, "recency_bias": True, "herd": True,
        "anchoring": False, "loss_aversion": True, "confirmation_bias": False,
        "sunk_cost": True, "FOMO": False, "regret_aversion": False,
        "disposition_effect": False, "mental_accounting": False,
        "risk_score": 7.0,
        "bias_note": "sunk cost fallacy (refusing to cut losses when trapped) + overconfidence (early winners)",
        "mitigation": [
            "Ask: if I were flat now, would I buy at this price? If no, consider reducing",
            "Do not refuse stop-loss because already lost so much",
        ],
    },
    "煤炭": {
        "overconfidence": False, "recency_bias": False, "herd": False,
        "anchoring": True, "loss_aversion": False, "confirmation_bias": False,
        "sunk_cost": False, "FOMO": False, "regret_aversion": False,
        "disposition_effect": False, "mental_accounting": False,
        "risk_score": 3.5,
        "bias_note": "anchoring effect (historical high dividend yield expectations)",
        "mitigation": [
            "Dynamically evaluate dividend yield vs coal price; do not anchor on past high yields",
            "Set dividend yield threshold; trigger reduction below 5%",
        ],
    },
    "港股": {
        "overconfidence": True, "recency_bias": True, "herd": False,
        "anchoring": False, "loss_aversion": False, "confirmation_bias": False,
        "sunk_cost": False, "FOMO": False, "regret_aversion": True,
        "disposition_effect": False, "mental_accounting": False,
        "risk_score": 7.5,
        "bias_note": "regret aversion (fear of missing rebound) + recency bias (chasing single-day spikes)",
        "mitigation": [
            "HK stocks have high volatility; set tighter stop-loss than A-shares (-10%)",
            "Do not blindly chase just because you missed last time",
        ],
    },
    "中概互联网": {
        "overconfidence": True, "recency_bias": True, "herd": True,
        "anchoring": True, "loss_aversion": False, "confirmation_bias": False,
        "sunk_cost": False, "FOMO": True, "regret_aversion": False,
        "disposition_effect": False, "mental_accounting": False,
        "risk_score": 8.0,
        "bias_note": "FOMO + anchoring (historical highs) + herd (US tech mapping)",
        "mitigation": [
            "China internet is policy-sensitive; use position sizing instead of market timing",
            "Set maximum position cap (e.g. 10% of total capital), do not chase",
        ],
    },
}

DEFAULT_BIAS_PROFILE = {
    "overconfidence": False, "recency_bias": False, "herd": False,
    "anchoring": False, "loss_aversion": False, "confirmation_bias": False,
    "sunk_cost": False, "FOMO": False, "regret_aversion": False,
    "disposition_effect": False, "mental_accounting": False,
    "risk_score": 5.0,
    "bias_note": "neutral default",
    "mitigation": ["maintain diversified investing", "review trade log regularly"],
}


def _fuzzy_match(sector: str) -> Dict:
    """Fuzzy match sector to BIAS_RISK_MAP. Exact match first, then longest substring."""
    if sector in BIAS_RISK_MAP:
        return copy.deepcopy(BIAS_RISK_MAP[sector])

    best_key = None
    best_len = 0
    for key in BIAS_RISK_MAP:
        if key in sector or sector in key:
            if len(key) > best_len:
                best_key = key
                best_len = len(key)

    if best_key:
        return copy.deepcopy(BIAS_RISK_MAP[best_key])

    return copy.deepcopy(DEFAULT_BIAS_PROFILE)


def _count_biases(bias: Dict) -> int:
    """Count active bias flags in a sector profile."""
    biased_keys = [
        "overconfidence", "recency_bias", "herd", "anchoring",
        "loss_aversion", "confirmation_bias", "sunk_cost",
        "FOMO", "regret_aversion", "disposition_effect", "mental_accounting",
    ]
    return sum(1 for k in biased_keys if bias.get(k, False))


def _get_primary_bias(bias: Dict) -> str:
    """Get the primary bias label by priority order."""
    order = [
        ("FOMO", "FOMO (fear of missing out)"),
        ("overconfidence", "overconfidence"),
        ("recency_bias", "recency bias"),
        ("herd", "herd behavior"),
        ("loss_aversion", "loss aversion"),
        ("disposition_effect", "disposition effect"),
        ("anchoring", "anchoring effect"),
        ("confirmation_bias", "confirmation bias"),
        ("regret_aversion", "regret aversion"),
        ("sunk_cost", "sunk cost fallacy"),
        ("mental_accounting", "mental accounting"),
    ]
    for key, label in order:
        if bias.get(key, False):
            return label
    return "no prominent bias"


def _get_sub_scores(bias: Dict, risk_level: float = 0.5) -> Dict:
    """Compute sub-layer scores (0-10). Higher = lower behavioral risk."""
    # L21_Behavior = 10 - risk_score
    behavior = round(10 - bias["risk_score"], 1)

    # L21_Herding: herd effect score (high risk => low score)
    herd_risk = 1.0 if bias.get("herd", False) else 0.0
    herding_score = round(max(1.0, min(10.0, 10 - herd_risk * bias["risk_score"])), 1)

    # L21_Disposition: loss aversion + disposition effect
    dispo_keys = ["loss_aversion", "disposition_effect"]
    dispo_risk = sum(1 for k in dispo_keys if bias.get(k, False))
    disposition_score = round(max(1.0, min(10.0, 10 - dispo_risk * 2.5)), 1)

    # L21_Overreaction: overconfidence + recency + confirmation
    over_keys = ["overconfidence", "recency_bias", "confirmation_bias"]
    over_risk = sum(1 for k in over_keys if bias.get(k, False))
    overreaction_score = round(max(1.0, min(10.0, 10 - over_risk * 1.7)), 1)

    # L21_Contrarian: non-FOMO/non-regret => higher score
    contrary_risk = 1.0 if bias.get("FOMO", False) or bias.get("regret_aversion", False) else 0.0
    contrarian_score = round(max(1.0, min(10.0, 10 - contrary_risk * 3.0)), 1)

    # L21_Attention: sunk_cost + FOMO + recency => risk penalty
    attn_keys = ["sunk_cost", "FOMO", "recency_bias"]
    attn_risk = sum(1 for k in attn_keys if bias.get(k, False))
    attention_score = round(max(1.0, min(10.0, 10 - attn_risk * 2.0)), 1)

    # Risk level classification: 1-safe, 2-low, 3-moderate, 4-high, 5-critical
    rs = bias["risk_score"]
    if rs <= 3:
        level = 1
    elif rs <= 5:
        level = 2
    elif rs <= 7:
        level = 3
    elif rs <= 8:
        level = 4
    else:
        level = 5

    return {
        "L21_Behavior": behavior,
        "L21_Herding": herding_score,
        "L21_Disposition": disposition_score,
        "L21_Overreaction": overreaction_score,
        "L21_Contrarian": contrarian_score,
        "L21_Attention": attention_score,
        "_primary_bias": _get_primary_bias(bias),
        "_risk_level": level,
        "_bias_count": _count_biases(bias),
        "_mitigation": bias.get("mitigation", []),
    }


def score_l21_layers(sector: str, risk_level: float = 0.5) -> Dict:
    """Return full L21 scoring dictionary.

    Args:
        sector: ETF sector / industry name
        risk_level: ETF risk level (0-1)

    Returns:
        dict with: score (L21_Behavior composite), primary_bias,
        risk_level (int 1-5), mitigation, bias_count,
        sub_scores (L21_Herding, L21_Disposition, etc.), raw_bias
    """
    bias = _fuzzy_match(sector)
    sub = _get_sub_scores(bias, risk_level)

    # Risk-level adjustment: high volatility ETF gets slight penalty
    risk_adj = 0.0
    if risk_level > 0.8:
        risk_adj = 0.3
    elif risk_level > 0.6:
        risk_adj = 0.1

    base = sub.pop("L21_Behavior")
    behavior = round(max(1.0, min(10.0, base - risk_adj)), 1)
    sub["L21_Behavior"] = behavior

    level = sub.pop("_risk_level")
    if risk_adj >= 0.3:
        level = min(5, level + 1)

    return {
        "score": behavior,
        "primary_bias": sub.pop("_primary_bias"),
        "risk_level": level,
        "mitigation": sub.pop("_mitigation"),
        "bias_count": sub.pop("_bias_count"),
        "sub_scores": sub,
        "raw_bias": bias,
    }
