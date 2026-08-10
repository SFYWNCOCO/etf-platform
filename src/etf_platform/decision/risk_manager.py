r"""
risk_manager.py — stop-loss and drawdown control for ETF screener
==================================================================
v5.6: Tracks positions, enforces -15% individual stop-loss and -20% portfolio max DD.
File-based persistence: D:\龙虾\.openclaw\etf-platform\data\positions.json
"""

import json
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
    except (IOError, OSError, json.JSONDecodeError, KeyError, ValueError):
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
            # M-16 fix: use Decimal for financial calculations to avoid float precision issues
            from decimal import Decimal, ROUND_HALF_UP
            entry = Decimal(str(pos["entry_price"]))
            current = Decimal(str(prices[code]))
            pnl = ((current / entry) - 1) * 100
            pos["pnl_pct"] = float(pnl.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
            pos["last_updated"] = today
            total_value += prices[code] * pos.get("shares", 1)
            total_entry += pos["entry_price"] * pos.get("shares", 1)
    
    # Add new positions from top-3 recommendations
    for rec in recommendations[:3]:
        code = rec.get("code", "")
        if code not in data["positions"] and code in prices and prices[code] > 0:
            # v5.6: Use entry price as weight proxy for PnL calc
            # shares=1 is intentional (equal-weight tracking). 
            # Weighted PnL uses entry_price * shares as weight.
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
        # FIX: guard missing/zero portfolio_peak (old positions files may lack it)
        peak = data.get("portfolio_peak") or 1.0
        if peak <= 0:
            peak = 1.0
        portfolio_dd = portfolio_value / peak - 1
        
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

    # k189 组合分散化检查（无法获取 returns 时 checked=False）
    try:
        holdings = [
            {"code": code, "weight": pos.get("entry_price", 1.0) * pos.get("shares", 1),
             "sector": pos.get("name", code)}
            for code, pos in data["positions"].items()
        ]
        returns_by_code = {}
        if holdings:
            from etf_platform.data.kline import _fetch_kline
            for h in holdings:
                rows = _fetch_kline(h["code"], 120)
                if rows:
                    close = [float(r["close"]) for r in rows]
                    if len(close) >= 30:
                        returns_by_code[h["code"]] = [close[i] / close[i - 1] - 1 for i in range(1, len(close))]
        flags["diversification"] = check_diversification(holdings, returns_by_code)
    except Exception:
        flags["diversification"] = {"checked": False, "reason": "insufficient_data"}

    return flags


def check_diversification(holdings: list[dict], returns_by_code: dict[str, list[float]] | None = None) -> dict:
    """组合级分散化检查（来源: k189 跨资产相关/危机制度）。

    holdings: [{code, weight, sector}]；returns_by_code: {code: [日收益率]}。
    returns 为空或不足时返回 {"checked": False, "reason": "insufficient_data"}。
    高相关(>0.7)对数占比 >0.5 判定分散化失效，返回 warning。
    """
    from etf_platform.analysis.cross_asset_correlation import (
        correlation_matrix,
        detect_diversification_failure,
    )

    if not returns_by_code:
        return {"checked": False, "reason": "insufficient_data"}
    codes = [h["code"] for h in holdings if h.get("code") in returns_by_code]
    if len(codes) < 2:
        return {"checked": False, "reason": "insufficient_data"}

    corr_dict, _meta = correlation_matrix({c: returns_by_code[c] for c in codes})
    if not corr_dict:
        return {"checked": False, "reason": "insufficient_data"}

    info = detect_diversification_failure(corr_dict)
    result = {
        "checked": True,
        "diversification_failure": info["failure"],
        "high_ratio": info["high_ratio"],
        "avg_corr": info["avg_corr"],
    }
    if info["failure"]:
        result["warning"] = f"分散化失效警报：高相关(>0.7)占比 {info['high_ratio']:.0%}，同涨同跌风险高"
    return result


def get_position_summary() -> str:
    """Return human-readable position summary."""
    data = _load_positions()
    if not data["positions"]:
        return "无持仓"
    
    lines = []
    total_weight = 0
    weighted_pnl = 0
    for code, pos in data["positions"].items():
        pnl = pos.get("pnl_pct", 0)
        entry = pos.get("entry_price", 1.0)
        # 权重=当前市值(price×shares); 无市价时回退入场市值
        price = pos.get("current_price") or entry
        weight = price * pos.get("shares", 1)
        weighted_pnl += pnl * weight
        total_weight += weight
        icon = "🔴" if pnl < -10 else ("🟡" if pnl < 0 else "🟢")
        lines.append(f"  {icon} {pos['name']}: {pnl:+.1f}% (入场{pos.get('entry_date','?')})")
    
    avg_pnl = weighted_pnl / total_weight if total_weight > 0 else 0
    icon = "🔴" if avg_pnl < -10 else ("🟡" if avg_pnl < 0 else "🟢")
    lines.insert(0, f"持仓 ({icon} 加权均{avg_pnl:+.1f}%):")
    return "\n".join(lines)