"""ETF每日巡检 + 飞书推送 + 归档 + 事件记录"""
from datetime import datetime
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

BASE = Path(__file__).resolve().parent.parent.parent.parent
# 2026-09-16 审核: BASE 已是项目根, 再拼 "etf-platform" 会写到 etf-platform/etf-platform/,
# 而无人从该处读取(顶层 data/patrol_latest.json 一直缺失)。修正为与 FEISHU_OUT 同级。
PATROL_OUT = BASE / "data" / "patrol_latest.json"
FEISHU_OUT = BASE / "data" / "etf_patrol_feishu.md"


def _trend_icon(change):
    if change > 2: return "🟢"
    if change > -2: return "🟡"
    return "🔴"


def _risk_icon(score):
    if score >= 7: return "🔵"
    if score >= 5: return "🟡"
    return "🟠"


def run_patrol(watchlist=None, archive: bool = True):
    from ..decision.screener import recommend
    from ..data.kline import get_trend
    
    if watchlist is None:
        watchlist = [
            ("159185", "HK信息", "defensive"),
            ("159247", "创业板TF", "balanced"),
            ("159131", "港股AI科技", "balanced"),
            ("159146", "电力", "aggressive"),
        ]
    
    now = datetime.now()
    lines = []
    lines.append("=" * 55)
    lines.append(f"  ETF Daily Patrol - {now.strftime('%Y-%m-%d %H:%M')}")
    lines.append("=" * 55)
    
    events_today = []

    watch_results = []
    for code, name, mode in watchlist:
        try:
            trend = get_trend(code)
            sig = trend.trend_signal if trend else "?"
            chg = trend.change_20d if trend else 0
            icon = _trend_icon(chg)
            lines.append(f"  {icon} {code} {name:<12} {mode:<10} {chg:+.1f}% {sig}")
            watch_results.append({"code": code, "name": name, "change": chg, "signal": sig})
            
            # Log significant moves
            if abs(chg) > 8:
                events_today.append({"type": "big_move", "code": code, "name": name, "change": round(chg, 1)})
        except (KeyError, ValueError, TypeError, AttributeError, ImportError) as e:
            lines.append(f"  ❓ {code} {name:<12} ERROR: {e}")
            watch_results.append({"code": code, "name": name, "error": str(e)[:50]})

    # Rotation check
    try:
        from ..analysis.rotation import detect_rotation
        rot = detect_rotation()
        leaders = rot.get("leaders", []) if isinstance(rot, dict) else []
        laggards = rot.get("laggards", []) if isinstance(rot, dict) else []
        if leaders:
            lines.append(f"\n  🔥 领涨: {', '.join(leaders[:3])}")
        if laggards:
            lines.append(f"  📉 领跌: {', '.join(laggards[:3])}")
        if leaders or laggards:
            events_today.append({"type": "rotation", "leaders": leaders[:3], "laggards": laggards[:3]})
    except (KeyError, ValueError, TypeError, AttributeError, ImportError) as e:
        logger.debug("rotation check failed: %s", e)
        pass

    # QVIX check
    try:
        from ..analysis.qvix_regime import get_regime
        regime_data = get_regime()
        regime = regime_data.get("regime", "?")
        qvix_50 = regime_data.get("qvix_50", 0)
        lines.append(f"\n  📊 QVIX: {regime} (50={qvix_50:.0f})")
        if regime in ("fear", "panic"):
            lines.append("  ⚠️ 市场恐慌 — 建议减仓或持有现金")
            events_today.append({"type": "market_regime", "regime": regime, "qvix_50": qvix_50})
    except (KeyError, ValueError, TypeError, AttributeError, ImportError) as e:
        logger.debug("QVIX check failed: %s", e)
        pass

    # L16增强: 折溢价+资金流信号
    lines.append("\n  📡 L16增强信号:")
    try:
        from ..analysis.dip_monitor import DIPMonitor
        from ..analysis.fund_flow import FundFlowAnalyzer
        dip = DIPMonitor()
        flow = FundFlowAnalyzer()

        # 折溢价概览
        dip_df = dip.fetch_etf_data()
        if not dip_df.empty:
            dip_alerts = dip.detect_alerts(dip_df)
            high_risk = [a for a in dip_alerts if a.risk_level == "high"]
            lines.append(f"    折溢价: {len(dip_alerts)}预警 ({len(high_risk)}高风险)")
            if high_risk[:3]:
                top_dip = high_risk[:3]
                lines.append(f"    极端折价: {' | '.join(f'{a.code}({a.premium_rate:+.1f}%)' for a in top_dip)}")

        # 资金流概览
        flow_df = flow.fetch_data()
        if not flow_df.empty and '主力净流入-净额' in flow_df.columns:
            total_flow = flow_df['主力净流入-净额'].sum() / 1e8
            lines.append(f"    资金流: 主力净{total_flow:+.2f}亿 ({(flow_df['主力净流入-净额']>0).sum()}流入/{(flow_df['主力净流入-净额']<0).sum()}流出)")
    except Exception as e:
        lines.append(f"    L16增强: ⚠️ {str(e)[:40]}")

    # 归档L16增强数据
    l16_data = {}
    try:
        dip_df = dip.fetch_etf_data()
        if not dip_df.empty:
            dip_alerts = dip.detect_alerts(dip_df)
            l16_data["dip_alerts"] = len(dip_alerts)
            l16_data["dip_high_risk"] = len([a for a in dip_alerts if a.risk_level == "high"])
        flow_df = flow.fetch_data()
        if not flow_df.empty and '主力净流入-净额' in flow_df.columns:
            l16_data["total_main_flow_yi"] = round(flow_df['主力净流入-净额'].sum() / 1e8, 2)
    except (ImportError, KeyError, ValueError, TypeError, AttributeError, OSError):
            logger.warning("silent catch in daily.py:130 - needs review")
    top5 = []
    try:
        top5 = recommend(top_n=5, profile="均衡")
        for r in top5:
            lines.append(f"  #{r['rank']} {r['code']} {r['name'][:16]:<18} {r['composite_score']:.1f}")
    except (KeyError, ValueError, TypeError, AttributeError, ImportError) as e:
        lines.append(f"  N/A: {e}")

    lines.append("=" * 55)
    report = "\n".join(lines)
    print(report)

    persist_patrol(now, watch_results, top5, report, l16_data)
    write_feishu_report(now, watch_results, top5)
    
    # Archive snapshot
    if archive:
        try:
            from ..archive.collector import collect_full_snapshot, log_event
            print("\n  📦 归档每日数据...")
            collect_full_snapshot(quick=True)
        except (KeyError, ValueError, TypeError, AttributeError, ImportError) as e:
            print(f"  ⚠️ 归档失败: {e}")
    
    # Log today's events
    for ev in events_today:
        try:
            from ..archive.collector import log_event
            log_event(ev.pop("type"), ev)
        except (KeyError, ValueError, TypeError, AttributeError, ImportError) as e:
            logger.debug("log_event failed: %s", e)
            pass
    
    return report


def persist_patrol(now, watch_results, top5, report, l16_data=None):
    PATROL_OUT.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "timestamp": now.isoformat(),
        "watchlist": watch_results,
        "recommendations": [
            {"rank": r["rank"], "code": r["code"], "name": r["name"][:20], "score": r["composite_score"]}
            for r in top5
        ] if top5 else [],
        "l16_enhanced": l16_data if l16_data else None,
    }
    with open(PATROL_OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def write_feishu_report(now, watch_results, top5):
    """生成飞书-compatible的 patrol 报告."""
    date_str = now.strftime("%Y-%m-%d %H:%M")
    rpt = [f"**ETF 每日巡检 — {date_str}**\n"]
    rpt.append("📊 重点标的:")
    
    for w in watch_results:
        if "error" in w:
            rpt.append(f"- ❓ {w['code']} {w['name']}: {w['error']}")
        else:
            icon = _trend_icon(w["change"])
            rpt.append(f"- {icon} {w['code']} {w['name']}: {w['change']:+.1f}% {w['signal']}")
    
    if top5:
        rpt.append(f"\n🏆 Top {len(top5)} 推荐:")
        for r in top5:
            icon = _risk_icon(r["composite_score"])
            rpt.append(f"{r['rank']}. {icon} **{r['code']}** {r['name'][:16]} — {r['composite_score']:.1f}分")
    
    text = "\n".join(rpt)
    FEISHU_OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(FEISHU_OUT, "w", encoding="utf-8") as f:
        f.write(text)
    return text
