# -*- coding: utf-8 -*-
"""holdings_fetcher.py — Batch ETF holdings data fetcher.

Fetches real stock holdings for ETFs from akshare, with:
  - Per-ETF top 10 holdings with weight %
  - Sector breakdown from holdings
  - Concentration metrics
  - Material/commodity exposure detection

Cache: in-memory with configurable TTL.
"""

import time
import logging
import threading
from typing import Dict, List, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)

# ─── Cache ────────────────────────────────────────────────────────────────
_holdings_cache = {}  # code -> (data, timestamp)
_HOLDINGS_CACHE_LOCK = threading.Lock()
_CACHE_TTL = 86400  # 24 hours (holdings change quarterly)


def _get_holdings_for_etf(code: str) -> Optional[List[Dict]]:
    """Fetch holdings for a single ETF.

    Returns list of dicts: [{stock_code, stock_name, pct_nav}, ...]
    """
    now = time.time()
    with _HOLDINGS_CACHE_LOCK:
        if code in _holdings_cache:
            data, ts = _holdings_cache[code]
            if now - ts < _CACHE_TTL:
                return data

    try:
        import akshare as ak
        df = ak.fund_portfolio_hold_em(symbol=code, date='2024')
        if df is None or df.empty:
            # Try 2023
            df = ak.fund_portfolio_hold_em(symbol=code, date='2023')

        if df is None or df.empty:
            return []

        # Extract key columns
        result = []
        for _, row in df.iterrows():
            result.append({
                "stock_code": str(row.get("股票代码", "")),
                "stock_name": str(row.get("股票名称", "")),
                "pct_nav": _safe_float(row.get("占净值比例", 0)),
                "shares": _safe_float(row.get("持股数", 0)),
                "market_value": _safe_float(row.get("持仓市值", 0)),
                "quarter": str(row.get("季度", "")),
            })

        with _HOLDINGS_CACHE_LOCK:
            _holdings_cache[code] = (result, now)
        return result
    except Exception as e:
        logger.debug(f"[holdings_fetcher] failed for {code}: {e}")
        return []


def _safe_float(val) -> float:
    """Safely convert to float. Delegates to utils.safe_float."""
    from ..utils import safe_float
    return safe_float(val)


def get_top_holdings(code: str, top_n: int = 10) -> List[Dict]:
    """Get top N holdings for an ETF, sorted by weight."""
    holdings = _get_holdings_for_etf(code)
    if not holdings:
        return []
    sorted_h = sorted(holdings, key=lambda x: x["pct_nav"], reverse=True)
    return sorted_h[:top_n]


def get_concentration_metrics(code: str) -> Dict:
    """Calculate concentration/diversification metrics.
    
    Returns:
      - top1_pct: top 1 holding weight %
      - top3_pct: top 3 holdings weight %
      - top5_pct: top 5 holdings weight %
      - top10_pct: top 10 holdings weight %
      - herfindahl: HHI concentration index
      - effective_holdings: 1/HHI (effective number of holdings)
      - total_holdings: count of all stock holdings
    """
    holdings = _get_holdings_for_etf(code)
    if not holdings:
        return {
            "top1_pct": 0, "top3_pct": 0, "top5_pct": 0, "top10_pct": 0,
            "herfindahl": 0, "effective_holdings": 0, "total_holdings": 0,
        }
    
    weights = sorted([h["pct_nav"] for h in holdings], reverse=True)
    
    result = {
        "top1_pct": weights[0] if weights else 0,
        "top3_pct": sum(weights[:3]),
        "top5_pct": sum(weights[:5]),
        "top10_pct": sum(weights[:10]),
        "total_holdings": len(weights),
    }
    
    # Herfindahl-Hirschman Index
    hhi = sum(w ** 2 for w in weights)
    result["herfindahl"] = round(hhi, 4)
    result["effective_holdings"] = round(1.0 / hhi, 1) if hhi > 0 else 0
    
    return result


def get_sector_exposure(code: str) -> Dict[str, float]:
    """Estimate sector exposure from actual holdings.
    
    Maps stock codes to sectors using simple heuristics.
    Returns dict: {sector: weight%}
    
    Stock code heuristics:
      - 60xxxx: Shanghai main board (state-owned heavy)
      - 00xxxx: Shenzhen main board (mixed)
      - 30xxxx: ChiNext (tech/growth heavy)
      - 68xxxx: STAR market (hard tech)
    """
    holdings = _get_holdings_for_etf(code)
    if not holdings:
        return {}
    
    sector_map = defaultdict(float)
    
    # Simple sector classification by stock code prefix
    for h in holdings:
        weight = h["pct_nav"]
        stock_code = h["stock_code"]
        stock_name = h["stock_name"]
        
        if not stock_code:
            continue
        
        # Code-based classification
        if stock_code.startswith("68"):  # STAR market = hard tech
            sector_map["硬科技"] += weight
        elif stock_code.startswith("30"):  # ChiNext = growth/tech
            sector_map["成长/科技"] += weight
        elif stock_code.startswith("60"):  # Shanghai = mixed, lean SOE
            if any(k in stock_name for k in ["银行", "保险", "证券"]):
                sector_map["金融"] += weight
            elif any(k in stock_name for k in ["酒", "饮", "食"]):
                sector_map["消费"] += weight
            elif any(k in stock_name for k in ["药", "医"]):
                sector_map["医药"] += weight
            elif any(k in stock_name for k in ["矿", "铜", "铝", "金"]):
                sector_map["周期/资源"] += weight
            elif any(k in stock_name for k in ["电", "力", "能"]):
                sector_map["公用事业/能源"] += weight
            else:
                sector_map["综合/其他"] += weight
        elif stock_code.startswith("00"):  # Shenzhen = mixed
            if any(k in stock_name for k in ["技", "科", "电", "网"]):
                sector_map["科技"] += weight
            elif any(k in stock_name for k in ["药", "医"]):
                sector_map["医药"] += weight
            elif any(k in stock_name for k in ["车", "汽"]):
                sector_map["新能源/汽车"] += weight
            else:
                sector_map["综合/其他"] += weight
        else:
            sector_map["其他"] += weight
    
    return dict(sector_map)


def get_material_exposure(code: str) -> Dict[str, float]:
    """Detect material/commodity exposure from holdings.
    
    Maps holdings to materials sector for L3/L4 scoring.
    Returns dict: {material_type: weight%}
    """
    holdings = _get_holdings_for_etf(code)
    if not holdings:
        return {}
    
    material_keywords = {
        "锂": "锂电材料",
        "钴": "锂电材料",
        "镍": "锂电材料",
        "石墨": "锂电材料",
        "正极": "锂电材料",
        "负极": "锂电材料",
        "隔膜": "锂电材料",
        "电解液": "锂电材料",
        "硅": "半导体材料",
        "碳": "新材料",
        "钢": "钢铁材料",
        "铁": "钢铁材料",
        "铜": "有色金属",
        "铝": "有色金属",
        "金": "贵金属",
        "银": "贵金属",
        "锌": "有色金属",
        "稀土": "稀土材料",
        "磁": "稀土材料",
        "光伏": "光伏材料",
        "硅片": "光伏材料",
        "电池": "电池材料",
        "半导体": "半导体材料",
        "芯片": "半导体材料",
        "晶": "半导体材料",
    }
    
    exposure = defaultdict(float)
    for h in holdings:
        weight = h["pct_nav"]
        name = h["stock_name"]
        for kw, mat_type in material_keywords.items():
            if kw in name:
                exposure[mat_type] += weight
                break  # One match per stock
    
    return dict(exposure)


def batch_get_holdings(codes: List[str]) -> Dict[str, List[Dict]]:
    """Batch fetch holdings for multiple ETFs."""
    result = {}
    for code in codes:
        result[code] = _get_holdings_for_etf(code)
    return result


def batch_get_concentration(codes: List[str]) -> Dict[str, Dict]:
    """Batch get concentration metrics."""
    result = {}
    for code in codes:
        result[code] = get_concentration_metrics(code)
    return result


def clear_cache():
    """Clear holdings cache."""
    with _HOLDINGS_CACHE_LOCK:
        _holdings_cache.clear()
    logger.info("[holdings_fetcher] cache cleared")


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.DEBUG)
    
    test_codes = ["510300", "510500", "510050", "159919", "512100"]
    for code in test_codes:
        top = get_top_holdings(code, 5)
        conc = get_concentration_metrics(code)
        print(f"\n{code}:")
        print(f"  Total holdings: {conc['total_holdings']}")
        print(f"  Top1: {conc['top1_pct']:.1f}%, Top3: {conc['top3_pct']:.1f}%, Top10: {conc['top10_pct']:.1f}%")
        print(f"  HHI: {conc['herfindahl']:.4f}, Effective: {conc['effective_holdings']:.1f}")
        if top:
            print("  Top 5:")
            for h in top:
                print(f"    {h['stock_name']} ({h['stock_code']}): {h['pct_nav']:.2f}%")
