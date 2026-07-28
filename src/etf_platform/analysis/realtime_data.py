# -*- coding: utf-8 -*-
"""realtime_data.py — Real-time ETF data from akshare (EastMoney).

Provides real AUM, share count, capital flow, and liquidity data
to replace the fee/type heuristic scoring in pipeline.py.

Data sources:
  - fund_etf_spot_em(): 1528 ETFs with real-time price, AUM, shares, capital flow
  - fund_etf_hist_em(): historical daily OHLCV for trend analysis
  - fund_portfolio_hold_em(): top holdings per quarter

Cache: in-memory with 3600s TTL to avoid rate limiting.
"""

import time
import math
import logging
import threading
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)

# ─── Cache ────────────────────────────────────────────────────────────────
_cache = {
    "spot": None,
    "hist": {},  # code -> (df, timestamp)
    "ts": 0,
}
_CACHE_LOCK = threading.Lock()
_CACHE_TTL_SPOT = 3600  # 1 hour for spot data
_CACHE_TTL_HIST = 86400  # 24 hours for historical data


def _get_spot_df():
    """Fetch ETF spot data from akshare, with caching."""
    now = time.time()
    with _CACHE_LOCK:
        if _cache["spot"] is not None and (now - _cache["ts"]) < _CACHE_TTL_SPOT:
            return _cache["spot"]
    try:
        import akshare as ak
        df = ak.fund_etf_spot_em()
        if df is not None and not df.empty:
            # Normalize column names for consistency
            col_map = {
                "代码": "code",
                "名称": "name",
                "最新价": "price",
                "涨跌幅": "change_pct",
                "成交额": "amount",
                "成交量": "volume",
                "换手率": "turnover_rate",
                "最新份额": "shares",
                "总市值": "total_market_cap",
                "流通市值": "float_market_cap",
                "主力净流入-净占比": "main_net_flow_pct",
                "超大单净流入-净占比": "super_large_net_flow_pct",
                "大单净流入-净占比": "large_net_flow_pct",
                "中单净流入-净占比": "medium_net_flow_pct",
                "小单净流入-净占比": "small_net_flow_pct",
            }
            df = df.rename(columns=col_map)
            with _CACHE_LOCK:
                _cache["spot"] = df
                _cache["ts"] = now
            return df
    except Exception as e:
        logger.warning(f"[realtime_data] spot fetch failed: {e}")
    with _CACHE_LOCK:
        return _cache["spot"]


def get_etf_realtime_data(code: str) -> Optional[Dict]:
    """Get real-time data for a single ETF.
    
    Returns dict with:
      - shares: float (unit: 份)
      - total_market_cap: float (unit: yuan)
      - float_market_cap: float
      - main_net_flow_pct: float (percentage)
      - super_large_net_flow_pct: float
      - large_net_flow_pct: float
      - turnover_rate: float (percentage)
      - amount: float (trading volume in yuan)
      - price: float
      - change_pct: float
    """
    df = _get_spot_df()
    if df is None:
        return None
    row = df[df["code"] == code]
    if row.empty:
        return None
    r = row.iloc[0]
    return {
        "shares": _safe_float(r.get("shares")),
        "total_market_cap": _safe_float(r.get("total_market_cap")),
        "float_market_cap": _safe_float(r.get("float_market_cap")),
        "main_net_flow_pct": _safe_float(r.get("main_net_flow_pct")),
        "super_large_net_flow_pct": _safe_float(r.get("super_large_net_flow_pct")),
        "large_net_flow_pct": _safe_float(r.get("large_net_flow_pct")),
        "turnover_rate": _safe_float(r.get("turnover_rate")),
        "amount": _safe_float(r.get("amount")),
        "price": _safe_float(r.get("price")),
        "change_pct": _safe_float(r.get("change_pct")),
    }


def get_batch_realtime_data(codes: List[str]) -> Dict[str, Optional[Dict]]:
    """Get real-time data for multiple ETFs in one API call."""
    df = _get_spot_df()
    if df is None:
        return {c: None for c in codes}
    result = {}
    for code in codes:
        row = df[df["code"] == code]
        if row.empty:
            result[code] = None
            continue
        r = row.iloc[0]
        result[code] = {
            "shares": _safe_float(r.get("shares")),
            "total_market_cap": _safe_float(r.get("total_market_cap")),
            "float_market_cap": _safe_float(r.get("float_market_cap")),
            "main_net_flow_pct": _safe_float(r.get("main_net_flow_pct")),
            "super_large_net_flow_pct": _safe_float(r.get("super_large_net_flow_pct")),
            "large_net_flow_pct": _safe_float(r.get("large_net_flow_pct")),
            "turnover_rate": _safe_float(r.get("turnover_rate")),
            "amount": _safe_float(r.get("amount")),
            "price": _safe_float(r.get("price")),
            "change_pct": _safe_float(r.get("change_pct")),
        }
    return result


def _safe_float(val) -> float:
    """Safely convert to float, return 0.0 for None/NaN/invalid. Delegates to utils.safe_float."""
    from ..utils import safe_float
    return safe_float(val)


def get_etf_scale_score(code: str) -> float:
    """Score L1_ETF based on real market cap data.
    
    Uses LOGARITHMIC scale for better differentiation across orders of magnitude.
    Maps 100万-1万亿 to 1-10 range.
    Falls back to 5.0 if data unavailable.
    """
    data = get_etf_realtime_data(code)
    if data is None:
        return 5.0
    
    mcap = data.get("total_market_cap", 0)
    shares = data.get("shares", 0)
    
    if mcap > 0:
        # Log scale: log10(1e6)=6 -> score=1, log10(1e12)=12 -> score=10
        log_mcap = math.log10(max(mcap, 1e6))
        score = 1.0 + (log_mcap - 6.0) / 6.0 * 9.0
        score = max(1.0, min(10.0, score))
    elif shares > 0:
        log_shares = math.log10(max(shares, 1e6))
        score = 1.0 + (log_shares - 6.0) / 6.0 * 9.0
        score = max(1.0, min(10.0, score))
    else:
        score = 5.0
    
    return round(score, 1)


def get_etf_holding_score(code: str) -> float:
    """Score L2_Holdings based on real concentration/diversification.
    
    Uses top-10 holding concentration as proxy for diversification.
    Lower concentration = higher diversification = higher score.
    """
    try:
        import akshare as ak
        df = ak.fund_portfolio_hold_em(symbol=code, date='2024')
        if df is None or df.empty:
            return 5.5  # default
        
        # Get top 10 holdings concentration
        top10_pct = df.head(10)["占净值比例"].sum()
        total_holdings = len(df)
        
        # Diversification score: more holdings + lower concentration = higher
        # Range: 1-10
        if total_holdings >= 50 and top10_pct <= 40:
            score = 9.0
        elif total_holdings >= 30 and top10_pct <= 50:
            score = 8.0
        elif total_holdings >= 20 and top10_pct <= 60:
            score = 7.0
        elif total_holdings >= 10:
            score = 6.0
        elif total_holdings >= 5:
            score = 5.0
        else:
            score = 4.0
        
        # Adjust for extreme concentration
        if top10_pct > 80:
            score = max(1.0, score - 3.0)  # Heavy concentration penalty
        elif top10_pct < 20 and total_holdings > 100:
            score = min(10.0, score + 1.0)  # Well diversified bonus
        
        return round(score, 1)
    except Exception as e:
        logger.debug(f"[realtime_data] holdings fetch failed for {code}: {e}")
        return 5.5


def get_capital_flow_score(code: str) -> float:
    """Score L8_CapitalFlow from real main net flow data.
    
    Returns 1-10 score based on institutional money flow.
    Falls back to 5.0 if data unavailable.
    """
    data = get_etf_realtime_data(code)
    if data is None:
        return 5.0
    
    main_flow = data.get("main_net_flow_pct", 0)
    super_large = data.get("super_large_net_flow_pct", 0)
    large = data.get("large_net_flow_pct", 0)
    
    # Institutional flow = super_large + large
    inst_flow = super_large + large
    
    # Score: positive flow = bonus, negative = penalty
    # Range: 1-10, centered at 5
    score = 5.0 + main_flow * 0.3 + inst_flow * 0.2
    
    # Also factor in turnover rate (higher = more active)
    turnover = data.get("turnover_rate", 0)
    if turnover > 30:
        score += 0.5  # Very active
    elif turnover > 15:
        score += 0.3
    elif turnover < 1:
        score -= 0.3  # Very illiquid
    
    return round(max(1.0, min(10.0, score)), 1)


def refresh_cache():
    """Force cache refresh (call periodically or on demand)."""
    with _CACHE_LOCK:
        _cache["spot"] = None
        _cache["ts"] = 0
    logger.info("[realtime_data] cache refreshed")


if __name__ == "__main__":
    # Quick test
    import logging
    logging.basicConfig(level=logging.DEBUG)
    
    test_codes = ["510300", "510500", "510050", "159919", "512100"]
    for code in test_codes:
        data = get_etf_realtime_data(code)
        if data:
            print(f"{code}: mcap={data['total_market_cap']/1e8:.1f}亿 "
                  f"shares={data['shares']/1e8:.1f}亿 "
                  f"main_flow={data['main_net_flow_pct']:.2f}%")
        else:
            print(f"{code}: NO DATA")
