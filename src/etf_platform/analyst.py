"""analyst.py - Unified ETF analysis entry point.

Single call performs full analysis: penetration + rotation + macro + advice.
"""
from .pipeline import run_full as _run_full
from .analysis.rotation import detect_rotation as _detect_rotation
from .analysis.demand import add_demand_layers
from .config_loader import load_etfs, load_general

# 风险偏好模板
PROFILES = {
    "conservative": {"supply": 0.45, "capital": 0.10, "signal": 0.05, "demand": 0.40, "label": "保守型"},
    "balanced":     {"supply": 0.35, "capital": 0.25, "signal": 0.10, "demand": 0.30, "label": "均衡型"},
    "aggressive":   {"supply": 0.20, "capital": 0.40, "signal": 0.20, "demand": 0.20, "label": "进取型"},
}

# 行业分类（用于判断消费 vs B2B）
CONSUMER_SECTORS = {"消费","白酒","食品饮料","家电","医药","医疗","养殖","农牧","汽车","旅游","传媒"}


def _get_sector_type(sector):
    if not sector:
        return "B2B"
    for cs in CONSUMER_SECTORS:
        if cs in sector or sector in cs:
            return "消费"
    # B2B sectors: all tech, finance, resources, etc.
    return "B2B"


def analyse(code, profile="balanced", live=True):
    """单只ETF全链路分析——穿透+需求+轮动+建议"""
    
    # 1. 运行穿透 (L1-L9 from pipeline, L10-L11 from demand adapter)
    result = _run_full(code, live=live)
    
    # 2. 获取ETF基本信息
    etfs = load_etfs()
    info = etfs.get(code, {})
    sector = info.get("sector", result.get("sector", "其他"))
    sector_type = "消费" if sector in CONSUMER_SECTORS else \
                  "B2B" if sector not in ("宽基", "跨境") else "分散"
    result["sector"] = sector
    result["sector_type"] = sector_type
    
    # 3. 获取轮动信号
    rotation = _detect_rotation()
    rot_signal = rotation.get("sectors", {}).get(sector, {})
    result["rotation_signal"] = rot_signal
    
    # 4. 获取风险偏好模板
    pf = PROFILES.get(profile, PROFILES["balanced"])
    result["profile"] = pf["label"]
    
    # 5. 综合评分
    layers = result.get("layer_scores", {})
    exclude = {"L1_ETF", "L2_Holdings"}
    valid = {k: v for k, v in layers.items() 
             if k not in exclude and isinstance(v, (int, float))}
    
    # 分层类别
    supply_layers = {"L3_Material", "L4_SupplyChain", "L5_Tech", "L6_Politics", "L7_Irreplaceable"}
    capital_layer = {"L8_CapitalFlow"}
    signal_layer = {"L9_Signals"}
    demand_layers = {"L10_Demand", "L11_SectorRisk"}
    
    supply_score = sum(valid.get(k, 0) for k in supply_layers) / max(len(supply_layers & set(valid.keys())), 1)
    capital_score = valid.get("L8_CapitalFlow", 0)
    signal_score = valid.get("L9_Signals", 0)
    demand_score = sum(valid.get(k, 0) for k in demand_layers) / max(len(demand_layers & set(valid.keys())), 1)
    
    composite = (supply_score * pf["supply"] + 
                 capital_score * pf["capital"] + 
                 signal_score * pf["signal"] + 
                 demand_score * pf["demand"])
    
    result["composite_score"] = round(composite, 2)
    result["supply_score"] = round(supply_score, 1)
    result["capital_score"] = round(capital_score, 1)
    result["signal_score"] = round(signal_score, 1)
    result["demand_score"] = round(demand_score, 1)
    
    # 6. 投资建议
    if composite >= 7:
        risk_level = "低风险"
        advice = "适合保守/均衡配置" if supply_score > 7 else "高分但注意催化剂不足"
    elif composite >= 5:
        risk_level = "中等风险"
        advice = "可配置，建议结合催化剂择时"
    else:
        risk_level = "高风险"
        advice = "高弹性品种，需催化剂配合，设止损"
    
    # 轮动调整
    if rot_signal:
        if rot_signal.get("level") in ("hot", "rising"):
            advice += " | 轮动信号积极，短期动能向上"
        elif rot_signal.get("level") in ("plunging", "falling"):
            advice += " | 轮动信号偏弱，注意回调风险"
    
    result["risk_level"] = risk_level    
    # 7. 供应链风险 (chain analysis)
    try:
        from .analysis.chain import get_chain_report
        chain = get_chain_report(code)
        if chain and "risk_level" in chain:
            result["chain_risk"] = chain["risk_level"]
            result["chain_score"] = chain["risk_score"]
            result["chain_hidden_link"] = chain.get("hidden_link", "")
            if chain["risk_level"] in ("P0-致命", "P1-严重"):
                result["advice"] += " | 供应链: %s (%.1f分) - 需设止损" % (chain["risk_level"], chain["risk_score"])
        else:
            result["chain_risk"] = None
    except Exception:
        result["chain_risk"] = None
    
    result["advice"] = advice
    
    # 8. 生态健康评分
    try:
        from .analysis.macro import health_score
        h = health_score(code)
        if h:
            result["health_score"] = h["score"]
            result["health_level"] = h["level"]
            if h["score"] < 50:
                result["advice"] += " | 生态健康: %d分 - 注意风险" % h["score"]
        else:
            result["health_score"] = None
    except Exception:
        result["health_score"] = None
    
    return result


def patrol():
    """每日巡逻：全市场扫描+轮动+关键标的分析"""
    from .decision.screener import screen
    from .data.manager import check_all_sources, get_price
    import datetime
    
    report = []
    report.append("=" * 65)
    report.append(f"  ETF Patrol — {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
    report.append("=" * 65)
    
    # 1. Data source health
    report.append("\n【数据源健康】")
    health = check_all_sources()
    for h in health:
        icon = {"healthy": "\u2705", "degraded": "\u26a0\ufe0f", "failed": "\u274c"}
        report.append(f"  {icon.get(h.status.value, '?')} {h.source_name}: {h.status.value} ({h.latency_ms:.0f}ms)")
    
    # 2. Rotation
    report.append("\n【行业轮动】")
    rot = _detect_rotation()
    for sec, info in sorted(rot.get("sectors", {}).items(), key=lambda x: x[1]["change_pct"], reverse=True):
        report.append(f"  {info['icon']} {sec:<12} {info['change_pct']:+.2f}%  {info['signal']:<6} {info['amount_yi']:.2f}亿")
    
    # 3. Key prices
    report.append("\n【关键标的行情】")
    key_codes = ["512890","159995","159819","518880","513100","159201"]
    for code in key_codes:
        try:
            p, src = get_price(code)
            if p:
                report.append(f"  {code} {p.name[:16]:<18} {p.price:.3f}  {p.change_pct:+.2f}%  {p.amount/1e8:.2f}亿")
        except:
            pass
    
    # 4. Top screen
    report.append("\n【全市场Top 5】")
    try:
        results = screen(limit=50, profile="\u5747\u8861", top_n=5)
        ticons = {"oversold":"\U0001f7e2\u8d85\u5356","weak":"\U0001fe00\u56de\u8c03","neutral":"\u26aa\u4e2d\u6027",
                  "strong":"\U0001fe00\u58ee\u6001","overbought":"\U0001f534\u8d85\u4e70","plunging":"\U0001f534\u6025\u8dcc"}
        for r in results:
            sig = ticons.get(r.get("trend", {}).get("signal", ""), "")
            report.append(f"  #{r['rank']} {r['code']} {r['name'][:18]:<20} {r['composite_score']:.1f}分 {sig}")
    except Exception as e:
        report.append(f"  (扫描暂不可用: {e})")
    
    report.append("\n" + "=" * 65)
    return "\n".join(report)


def rank_by_risk(profile="balanced", top_n=10):
    """按风险偏好排序全市场ETF"""
    from .decision.screener import screen
    results = screen(limit=200, profile=profile, top_n=top_n)
    return results


if __name__ == "__main__":
    # Demo
    print(patrol())