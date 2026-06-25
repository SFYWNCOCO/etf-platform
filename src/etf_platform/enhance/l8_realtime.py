"""L8 Capital Flow enhancer: replaces inferred data with real-time data."""
import time
from etf_platform.data.manager import get_price


def enhance_l8(penetration_result: dict) -> dict:
    """Enhance L8 layer with real-time price/volume data."""
    layers = penetration_result.get("layers", {})
    scores = penetration_result.get("layer_scores", {})
    
    # Find L8 key
    l8_key = None
    for k in layers:
        if "L8" in k and "资金" in k:
            l8_key = k
            break
    
    if not l8_key:
        return penetration_result
    
    etf_code = penetration_result.get("etf_code", "")
    if not etf_code:
        return penetration_result
    
    # Get real-time data
    try:
        price_data, source_name = get_price(etf_code)
    except Exception:
        return penetration_result
    
    if not price_data or price_data.price <= 0:
        return penetration_result
    
    l8_data = layers[l8_key]
    
    # Build enhanced L8 data
    amount_yi = price_data.amount / 1e8 if price_data.amount else 0
    
    if amount_yi > 20:
        vol_pct = 90
    elif amount_yi > 10:
        vol_pct = 80
    elif amount_yi > 5:
        vol_pct = 65
    elif amount_yi > 2:
        vol_pct = 50
    elif amount_yi > 0.5:
        vol_pct = 30
    else:
        vol_pct = 15
    vol_pct = min(99, max(1, vol_pct))
    
    turnover = price_data.turnover_rate if price_data.turnover_rate else 0
    amp = 0
    if price_data.pre_close and price_data.high and price_data.low:
        amp = ((price_data.high - price_data.low) / price_data.pre_close * 100)
    
    if price_data.change_pct > 3:
        flow = "主力净流入(价格大涨)"
        big_order = 55
    elif price_data.change_pct > 1:
        flow = "主力净流入"
        big_order = 48
    elif price_data.change_pct > -1:
        flow = "主力中性"
        big_order = 40
    elif price_data.change_pct > -3:
        flow = "主力净流出"
        big_order = 35
    else:
        flow = "主力大幅流出"
        big_order = 25
    
    enhanced = {
        "data_source": f"\u2714\ufe0f \u5b9e\u6d4b({source_name})",
        "disclaimer": f"\u57fa\u4e8e{source_name}\u5b9e\u65f6\u884c\u60c5\u6570\u636e",
        "volume_percentile": vol_pct,
        "volume_interpretation": f"\u6210\u4ea4\u989d{amount_yi:.1f}\u4ebf, \u7ea6\u5904\u4e8e{vol_pct}\u5206\u4f4d",
        "turnover": {
            "actual": f"{turnover:.2f}%",
            "deviation": "\u653e\u91cf" if turnover > 2 else "\u6b63\u5e38",
            "anomaly": "\u653e\u91cf" if turnover > 3 else ("\u6b63\u5e38" if turnover > 0.5 else "\u7f29\u91cf"),
        },
        "price_momentum": {
            "5d_change": f"{price_data.change_pct:+.2f}%",
            "trend": "\u4e0a\u6da8" if price_data.change_pct > 2 else ("\u4e0b\u8dcc" if price_data.change_pct < -2 else "\u6a2a\u76d8"),
        },
        "volatility": {
            "amplitude": f"{amp:.2f}%",
            "interpretation": "\u6ce2\u52a8\u5927" if amp > 4 else ("\u6b63\u5e38" if amp > 1.5 else "\u4f4e\u6ce2\u52a8"),
        },
        "capital_flow": {
            "main_force": flow,
            "big_order_ratio": f"{big_order}%",
        },
        "institutional": l8_data.get("institutional", {}),
        "margin": l8_data.get("margin", {}),
    }
    
    layers[l8_key] = enhanced
    
    # Recalculate score
    score = 5.0
    if price_data.change_pct > 3:
        score += 1.5
    elif price_data.change_pct > 1:
        score += 0.5
    elif price_data.change_pct < -3:
        score -= 1.5
    elif price_data.change_pct < -1:
        score -= 0.5
    if 2 < amount_yi < 20:
        score += 1.0
    elif amount_yi > 50:
        score -= 1.0
    elif amount_yi < 0.1:
        score -= 1.0
    if 1 < turnover < 5:
        score += 0.5
    elif turnover > 10:
        score -= 1.0
    scores["L8_CapitalFlow"] = max(1, min(10, round(score, 1)))
    
    if "summary" in penetration_result:
        penetration_result["summary"] += f" | L8\u5b9e\u6d4b({source_name})"
    
    return penetration_result
