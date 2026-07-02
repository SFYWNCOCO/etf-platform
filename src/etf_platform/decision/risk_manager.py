"""
risk_manager.py — stop-loss and drawdown control for ETF screener
==================================================================
v5.6: Tracks positions, enforces -15% individual stop-loss and -20% portfolio max DD.
File-based persistence: D:\龙虾\.openclaw\etf-platform\data\positions.json
"""

import json, os
from pathlib import Path
from datetime import datetime

POSITIONS_FILE = Path(__file__).resolve().parent.parent.parent.parent / "data" / "positions.json"
STOP_LOSS_PCT = -0.15      # Individual ETF stop-loss: -15%
PORTFOLIO_MAX_DD = -0.20   # Portfolio max drawdown: -20% triggers cash


def _load_positions() -> dict:
    """Load current positions from file."""
    if not POSITIONS_FILE.exists():
        return {"positions": {}, "portfolio_peak": 1.0, "history": []}
    try:
        with open(POSITIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"positions": {}, "portfolio_peak": 1.0, "history": []}


def _save_positions(data: dict):
    """Save positions to file."""
    POSITIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(POSITIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


def update_positions(recommendations: list, prices: dict):
    """Update position tracker with new recommendations and current prices.
    
    Args:
        recommendations: list of {code, name, composite_score, ...}
        prices: dict of {code: current_price}
    """
    data = _load_positions()
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Update existing positions with current prices
    total_value = 0
    total_entry = 0
    for code, pos in list(data["positions"].items()):
        if code in prices and prices[code] > 0:
            pos["current_price"] = prices[code]
            pos["pnl_pct"] = round((prices[code] / pos["entry_price"] - 1) * 100, 2)
            pos["last_updated"] = today
            total_value += prices[code] * pos.get("shares", 1)
            total_entry += pos["entry_price"] * pos.get("shares", 1)
    
    # Add new positions from top-3 recommendations
    for rec in recommendations[:3]:
        code = rec.get("code", "")
        if code not in data["positions"] and code in prices and prices[code] > 0:
            data["positions"][code] = {
                "name": rec.get("name", code),
                "entry_price": prices[code],
                "entry_date": today,
                "current_price": prices[code],
                "pnl_pct": 0.0,
                "shares": 1,
                "last_updated": today
            }
    
    # Update portfolio peak
    if total_entry > 0:
        portfolio_value = total_value / total_entry if total_entry > 0 else 1.0
        if portfolio_value > data["portfolio_peak"]:
            data["portfolio_peak"] = portfolio_value
    
    _save_positions(data)
    return data


def check_risk_flags() -> dict:
    """Check for risk conditions. Returns dict with flags and reasons."""
    data = _load_positions()
    flags = {
        "stop_loss_hit": [],
        "portfolio_dd_warning": False,
        "portfolio_dd_critical": False,
        "message": ""
    }
    
    # Check individual stop-losses
    for code, pos in data["positions"].items():
        pnl = pos.get("pnl_pct", 0)
        if pnl <= STOP_LOSS_PCT * 100:  # -15% or worse
            flags["stop_loss_hit"].append({
                "code": code, "name": pos.get("name", code),
                "entry": pos.get("entry_price", 0),
                "current": pos.get("current_price", 0),
                "pnl_pct": pnl,
                "entry_date": pos.get("entry_date", "?")
            })
    
    # Check portfolio drawdown
    total_value = 0
    total_entry = 0
    for code, pos in data["positions"].items():
        total_value += pos.get("current_price", 0) * pos.get("shares", 1)
        total_entry += pos.get("entry_price", 0) * pos.get("shares", 1)
    
    if total_entry > 0:
        portfolio_value = total_value / total_entry
        portfolio_dd = portfolio_value / data["portfolio_peak"] - 1
        
        if portfolio_dd <= PORTFOLIO_MAX_DD:
            flags["portfolio_dd_critical"] = True
            flags["message"] = f"组合回撤 {portfolio_dd:.1%} 超过 -20% 阈值, 建议清仓持有现金"
        elif portfolio_dd <= -0.10:
            flags["portfolio_dd_warning"] = True
            flags["message"] = f"组合回撤 {portfolio_dd:.1%}, 建议减仓至50%"
    
    # Build stop-loss message
    if flags["stop_loss_hit"]:
        names = [s["name"] for s in flags["stop_loss_hit"]]
        flags["message"] = f"止损触发: {', '.join(names)} 跌幅超15%, 建议立即卖出"

    return flags


def get_position_summary() -> str:
    """Return human-readable position summary."""
    data = _load_positions()
    if not data["positions"]:
        return "无持仓"
    
    lines = []
    total_pnl = 0
    for code, pos in data["positions"].items():
        pnl = pos.get("pnl_pct", 0)
        total_pnl += pnl
        icon = "🔴" if pnl < -10 else ("🟡" if pnl < 0 else "🟢")
        lines.append(f"  {icon} {pos['name']}: {pnl:+.1f}% (入场{pos.get('entry_date','?')})")
    
    avg_pnl = total_pnl / len(data["positions"]) if data["positions"] else 0
    icon = "🔴" if avg_pnl < -10 else ("🟡" if avg_pnl < 0 else "🟢")
    lines.insert(0, f"持仓 ({icon} 均{avg_pnl:+.1f}%):")
    return "\n".join(lines)