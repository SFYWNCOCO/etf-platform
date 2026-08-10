"""
layer_live_adjustments.py — live data adjustments for L3-L7 sector scores
========================================================================
v5.5: Monthly/weekly data refreshes to modulate static sector scores.

Data sources:
  L3 (Material): Commodity futures 20d price trend -> sector material stress
  L4 (Supply Chain): Manufacturing PMI -> supply chain health
  L5 (Tech): Sector index relative strength -> tech moat premium

Caching: TTL=86400 (24h). All fetches wrapped in try/except, failures return 0 adjustment.
"""

import time
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_CACHE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "live_cache"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_CACHE_TTL = 86400  # 24 hours


def _sanitize_key(key: str) -> str:
    """Sanitize cache key to avoid path separator issues on Windows.
    Chinese chars and '/' in sector names become '_' in cache filenames."""
    return ''.join(c if c.isalnum() or c in ('_','-',' ') else '_' for c in key)


def _cache_get(key: str) -> dict | None:
    safe_key = _sanitize_key(key)
    path = _CACHE_DIR / f"{safe_key}.json"
    if not path.exists():
        return None
    age = time.time() - path.stat().st_mtime
    if age > _CACHE_TTL:
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (IOError, OSError, json.JSONDecodeError, KeyError, ValueError):
        return None


def _cache_set(key: str, data: dict):
    safe_key = _sanitize_key(key)
    path = _CACHE_DIR / f"{safe_key}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, default=str)


# === Sector -> Futures mapping for L3 Material stress ===
# Higher commodity price = higher material cost = negative for downstream sectors
SECTOR_COMMODITIES = {
    "新能源":     ["碳酸锂", "镍", "铜"],      # battery materials
    "新能源车":   ["碳酸锂", "镍", "铜", "铝"],
    "光伏":       ["银", "铜", "铝", "硅"],
    "半导体":     ["铜", "锡"],
    "半导体设备": ["铜", "锡"],
    "AI/科技":    ["铜"],
    "AI算力":     ["铜"],
    "军工":       ["铜", "镍", "钛"],
    "基建/地产":  ["螺纹钢", "铁矿石", "铜"],
    "周期/资源":  ["螺纹钢", "铁矿石", "铜"],
    "消费":       ["棉花", "白糖"],
    "家电":       ["铜", "铝"],
    "汽车":       ["铝", "铜", "橡胶"],
    "医药":       [],
    "金融":       [],
    "红利/价值":  [],
    "宽基":       [],
}


def _get_commodity_trend(symbol: str) -> float:
    """Get 20-day price trend for a commodity. Returns -1 to +1 signal."""
    try:
        import akshare as ak
        # Map commodity name to futures symbol
        SYMBOL_MAP = {
            "铜": "CU0", "铝": "AL0", "锌": "ZN0", "镍": "NI0", "锡": "SN0",
            "螺纹钢": "RB0", "铁矿石": "I0", "原油": "SC0", "银": "AG0",
            "棉花": "CF0", "白糖": "SR0", "橡胶": "RU0", "PTA": "TA0",
            "碳酸锂": "LC0",
        }
        sym = SYMBOL_MAP.get(symbol)
        if not sym:
            return 0.0
        df = ak.futures_zh_daily_sina(symbol=sym)
        if df is None or len(df) < 21:
            return 0.0
        closes = df["close"].tail(21).astype(float)
        pct_change = (closes.iloc[-1] / closes.iloc[0] - 1) * 100
        # Normalize: >+5% change = strong signal
        signal = max(-1.0, min(1.0, pct_change / 10.0))
        return round(signal, 3)
    except Exception as e:
        logger.warning("[layer_live] commodity signal failed for %s: %s", symbol, e)
        return 0.0


def _get_pmi_signal() -> float:
    """Get latest PMI deviation from 50. Returns -1 to +1."""
    try:
        import akshare as ak
        df = ak.macro_china_pmi()
        if df is None or len(df) == 0:
            return 0.0
        latest = float(df.iloc[-1]["制造业-指数"])
        # PMI 50 = neutral, 55+ = expansion, <45 = contraction
        signal = (latest - 50) / 10.0
        return round(max(-1.0, min(1.0, signal)), 3)
    except Exception as e:
        logger.warning("[layer_live] PMI signal failed: %s", e)
        return 0.0


def _get_sector_momentum(sector: str) -> float:
    """Get sector index 20-day momentum. Returns -1 to +1."""
    try:
        import akshare as ak
        from datetime import datetime
        # symbol=sector 取该行业日线; 默认 end_date 停在 20240108, 必须动态传当前日期
        df = ak.stock_board_industry_index_ths(
            symbol=sector, end_date=datetime.now().strftime("%Y%m%d"))
        if df is None or len(df) < 21:
            return 0.0
        closes = df["收盘价"].tail(21).astype(float)
        pct = (closes.iloc[-1] / closes.iloc[0] - 1) * 100
        signal = max(-1.0, min(1.0, pct / 15.0))
        return round(signal, 3)
    except Exception as e:
        logger.warning("[layer_live] sector momentum failed for %s: %s", sector, e)
        return 0.0


def get_live_adjustments(sector: str) -> dict:
    """Return L3-L5 adjustments based on live data.
    
    Adjustments are in score units (1-10 scale), centered at 0.
    Positive = improvement vs static, Negative = deterioration.
    Applied additively to sector base scores.
    """
    # Try cache
    cache_key = f"live_adj_{sector}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    adjustments = {"L3_Material": 0.0, "L4_SupplyChain": 0.0, "L5_Tech": 0.0}
    
    # === L3: Commodity price stress ===
    commodities = SECTOR_COMMODITIES.get(sector, [])
    if commodities:
        signals = []
        for comm in commodities:
            s = _get_commodity_trend(comm)
            signals.append(s)
        if signals:
            # Average signal, inverted (rising prices = stress = negative adjustment)
            avg_signal = sum(signals) / len(signals)
            # Scale: commodity signal -1..+1 -> adjustment -1.0..+1.0
            adjustments["L3_Material"] = round(-avg_signal * 1.0, 2)

    # === L4: PMI supply chain health ===
    pmi = _get_pmi_signal()
    adjustments["L4_SupplyChain"] = round(pmi * 1.5, 2)

    # === L5: Sector momentum as tech premium signal ===
    # Only for tech-heavy sectors where momentum signals innovation premium
    tech_sectors = ["半导体","半导体设备","AI/科技","AI算力","硬科技","通信/5G",
                    "新能源","新能源车","军工","医药","机器人/智造"]
    if sector in tech_sectors or any(t in sector for t in tech_sectors):
        mom = _get_sector_momentum(sector)
        adjustments["L5_Tech"] = round(mom * 0.8, 2)

    _cache_set(cache_key, adjustments)
    return adjustments


def apply_live_adjustments(sector: str, layer_scores: dict) -> dict:
    """Apply live data adjustments to layer scores in-place."""
    try:
        adjustments = get_live_adjustments(sector)
        for layer, adj in adjustments.items():
            if layer in layer_scores and adj != 0:
                old = layer_scores[layer]
                layer_scores[layer] = round(max(1.0, min(10.0, old + adj)), 1)
    except (KeyError, ValueError, TypeError, AttributeError, ImportError) as e:
        logger.debug("apply_live_adjustments failed: %s", e)
        pass
    return layer_scores