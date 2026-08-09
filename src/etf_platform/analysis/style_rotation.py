"""style_rotation.py — A股风格四周期评分卡与轮动信号

来源: k295 (A股风格四周期)
四风格(融资成长/盈利质量/红利低波/小微盘)评分卡 + 20日动量轮动推荐。
纯 numpy + stdlib。
"""
from __future__ import annotations

# 四风格代表 ETF 代码（融资成长/盈利质量/红利低波/小微盘）
STYLE_ETFS: dict[str, list[str]] = {
    "融资成长": ["159915", "159949", "588000"],  # 创业板/创50/科创50
    "盈利质量": ["510300", "510310"],  # 沪深300
    "红利低波": ["512890", "510880"],  # 红利/红利低波
    "小微盘": ["512100", "159629"],  # 中证1000/1000增强
}

STYLE_WEIGHTS = {"odds": 0.25, "probability": 0.30, "trend": 0.25, "crowding": 0.20}

# 各风格对宏观/微观因子的敏感方向: 系数为正表示该因子越高越有利
_STYLE_LOGIC = {
    "融资成长": {"money": 0.30, "credit": 0.20, "gdp": 0.20, "valuation": -0.60, "momentum": 0.25, "crowding": -0.40},
    "盈利质量": {"money": 0.10, "credit": 0.15, "gdp": 0.05, "valuation": -0.40, "momentum": 0.20, "crowding": -0.30},
    "红利低波": {"money": -0.15, "credit": 0.10, "gdp": -0.20, "valuation": -0.70, "momentum": 0.15, "crowding": -0.50},
    "小微盘": {"money": 0.25, "credit": 0.25, "gdp": 0.15, "valuation": -0.50, "momentum": 0.30, "crowding": -0.60},
}

# 输入别名: (中文键, 英文键)，缺输入时默认 0.5 中性
_MACRO_KEYS = {"money": ("货币增速", "money_growth"), "credit": ("信用增速", "credit_growth"), "gdp": ("GDP增速", "gdp_growth")}
_MICRO_KEYS = {"valuation": ("估值分位", "valuation_percentile"), "crowding": ("拥挤度", "crowding"), "momentum": ("动量", "momentum")}


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _val(d: dict, aliases: tuple, default: float = 0.5) -> float:
    if not d:
        return default
    for k in aliases:
        v = d.get(k)
        if v is not None:
            try:
                return _clamp01(float(v))
            except (TypeError, ValueError):
                return default
    return default


def _component(coef: float, x: float) -> float:
    """以 0.5 为中性点，按系数做线性偏移后夹到 [0,1]。"""
    return _clamp01(0.5 + coef * (x - 0.5))


def calculate_style_scores(macro: dict, micro: dict) -> dict:
    """四周期评分卡: odds(赔率)/probability(胜率)/trend(趋势)/crowding(拥挤度)。

    macro: {货币增速, 信用增速, GDP增速}；micro: {估值分位, 拥挤度, 动量}。
    缺输入时默认 0.5 中性，composite 在 [0,1]。
    """
    macro = macro or {}
    micro = micro or {}
    m = {k: _val(macro, aliases) for k, aliases in _MACRO_KEYS.items()}
    mi = {k: _val(micro, aliases) for k, aliases in _MICRO_KEYS.items()}

    out = {}
    for style, logic in _STYLE_LOGIC.items():
        odds = _component(logic["valuation"], mi["valuation"])
        probability = _component(logic["money"], m["money"]) * 0.5 + \
                      _component(logic["credit"], m["credit"]) * 0.3 + \
                      _component(logic["gdp"], m["gdp"]) * 0.2
        trend = _component(logic["momentum"], mi["momentum"])
        crowding = _component(logic["crowding"], mi["crowding"])
        composite = (odds * STYLE_WEIGHTS["odds"] + probability * STYLE_WEIGHTS["probability"]
                     + trend * STYLE_WEIGHTS["trend"] + crowding * STYLE_WEIGHTS["crowding"])
        out[style] = {
            "odds": round(odds, 3),
            "probability": round(probability, 3),
            "trend": round(trend, 3),
            "crowding": round(crowding, 3),
            "composite": round(_clamp01(composite), 3),
        }
    return out


def _get_20d(snapshot) -> float:
    if hasattr(snapshot, "change_20d"):
        try:
            return float(snapshot.change_20d)
        except (TypeError, ValueError):
            return 0.0
    if isinstance(snapshot, dict):
        try:
            return float(snapshot.get("change_20d", 0.0))
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def style_momentum(trends: dict, code_to_style: dict) -> dict:
    """用 20 日动量给四风格打分: {style: {"momentum", "etf_count"}}。"""
    agg: dict[str, list[float]] = {}
    for code, style in code_to_style.items():
        if style not in STYLE_ETFS or code not in trends:
            continue
        agg.setdefault(style, []).append(_get_20d(trends[code]))
    result = {}
    for style, vals in agg.items():
        if vals:
            result[style] = {"momentum": round(sum(vals) / len(vals), 2), "etf_count": len(vals)}
    return result


def recommend_style(trends: dict, code_to_style: dict, top_n: int = 2) -> list[dict]:
    """按 20 日动量排序推荐风格: [{style, momentum, representative_etf, reason}]。"""
    mom = style_momentum(trends, code_to_style)
    ranked = sorted(mom.items(), key=lambda kv: kv[1]["momentum"], reverse=True)
    out = []
    for style, info in ranked[:top_n]:
        rep = next((c for c in STYLE_ETFS[style] if c in trends), STYLE_ETFS[style][0])
        out.append({
            "style": style,
            "momentum": info["momentum"],
            "representative_etf": rep,
            "reason": f"{style} 20日动量 {info['momentum']:+.2f}%，代表ETF {rep}",
        })
    return out


if __name__ == "__main__":
    macro = {"货币增速": 0.7, "信用增速": 0.6, "GDP增速": 0.5}
    micro = {"估值分位": 0.4, "拥挤度": 0.6, "动量": 0.65}
    print("scores:", calculate_style_scores(macro, micro))
    fake = {c: {"change_20d": 5.0} for c in STYLE_ETFS["融资成长"]}
    code_to_style = {c: s for s, cs in STYLE_ETFS.items() for c in cs}
    print("momentum:", style_momentum(fake, code_to_style))
    print("recommend:", recommend_style(fake, code_to_style))
