# -*- coding: utf-8 -*-
"""QVIX Market Regime Indicator — with timeout + cache + fallback.

QVIX intervals:
  <16: complacent → aggressive ETFs +10% weight
  16-22: normal → standard weights
  22-28: cautious → aggressive -10%, defensive +10%
  >28: fearful → aggressive -20%, wait for reversal
"""
import json
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)

_CACHE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "live_cache"
_CACHE_FILE = _CACHE_DIR / "qvix_regime.json"
_CACHE_TTL = timedelta(hours=4)


def _fetch_qvix_with_timeout(timeout: float = 15.0) -> dict | None:
    """Fetch QVIX data with timeout via thread."""
    result = [None]

    def _fetch():
        try:
            import akshare as ak
            qvix_50 = ak.index_option_50etf_qvix()
            qvix_500 = ak.index_option_500etf_qvix()
            result[0] = {"50": qvix_50, "500": qvix_500, "updated": datetime.now().isoformat()}
        except (OSError, ValueError, KeyError, AttributeError, ImportError) as e:
            logger.warning("[qvix_regime] fetch failed: %s", e)

    t = threading.Thread(target=_fetch, daemon=True)
    t.start()
    t.join(timeout=timeout)
    return result[0]


def _load_cache() -> dict | None:
    """Load cached QVIX regime data."""
    try:
        if _CACHE_FILE.exists():
            data = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
            age = datetime.now() - datetime.fromisoformat(data.get("cached_at", "2000-01-01"))
            if age < _CACHE_TTL:
                return data
    except (OSError, json.JSONDecodeError, ValueError, KeyError) as e:
        logger.debug("[qvix_regime] cache load failed: %s", e)
    return None


def _save_cache(data: dict) -> None:
    """Save QVIX raw data to cache (convert DataFrames to JSON-safe dicts)."""
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_data = {"cached_at": datetime.now().isoformat()}
        for key in ("50", "500"):
            if key in data:
                df = data[key]
                try:
                    import pandas as pd
                    if isinstance(df, pd.DataFrame):
                        # Convert dates to strings for JSON serialization
                        records = df.to_dict(orient="records")
                        for r in records:
                            for k, v in r.items():
                                if hasattr(v, 'isoformat'):
                                    r[k] = v.isoformat()
                        cache_data[key] = records
                    else:
                        cache_data[key] = df
                except ImportError:
                    cache_data[key] = str(df)
        _CACHE_FILE.write_text(json.dumps(cache_data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    except OSError as e:
        logger.debug("[qvix_regime] cache save failed: %s", e)


def _get_qvix_data() -> dict | None:
    """Get raw QVIX data from akshare: cache-first, live refresh if expired (8s timeout)."""
    # 1. Try cache first (stores raw akshare format with "50"/"500" keys)
    cached = _load_cache()
    if cached is not None and "50" in cached:
        return cached
    
    # 2. Cache miss/expired/wrong-format → try live
    live = _fetch_qvix_with_timeout(timeout=8.0)
    if live is not None and "50" in live:
        return live
    
    # 3. Live failed → try any cache as last resort
    try:
        if _CACHE_FILE.exists():
            data = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
            if "50" in data:
                logger.info("[qvix_regime] using expired cache")
                return data
    except (OSError, json.JSONDecodeError, ValueError, KeyError):
        pass
    return None


def get_regime() -> dict:
    """Get current QVIX market regime. Returns fallback if data unavailable."""
    fallback = {"regime": "normal", "description": "QVIX unavailable, using normal regime",
                "trade_signal": "use standard scoring", "qvix_50": 20, "qvix_500": 22}

    data = _get_qvix_data()
    if data is None:
        return fallback

    try:
        import pandas as pd

        def _latest_qvix(df):
            """Get latest QVIX close value from DataFrame or cached dict list."""
            if isinstance(df, pd.DataFrame):
                df = df.copy()
                df["date"] = pd.to_datetime(df["date"])
                df = df.sort_values("date")
                return float(df["close"].iloc[-1])
            # Cached format: list of dicts with date/close keys
            if isinstance(df, list) and len(df) > 0:
                rows = pd.DataFrame(df)
                rows["date"] = pd.to_datetime(rows["date"])
                rows = rows.sort_values("date")
                return float(rows["close"].iloc[-1])
            return 20.0  # fallback

        def _classify(qvix_val: float) -> tuple:
            if qvix_val < 16:
                return ("complacent", "complacent, low vol")
            if qvix_val < 22:
                return ("normal", "normal range")
            if qvix_val < 28:
                return ("cautious", "elevated fear")
            return ("fearful", "fear regime, defensive")

        q50 = _latest_qvix(data["50"])
        q500 = _latest_qvix(data["500"])
        regime_50, desc_50 = _classify(q50)
        regime_500, desc_500 = _classify(q500)

        regime_order = {"complacent": 0, "normal": 1, "cautious": 2, "fearful": 3}
        if regime_order.get(regime_500, 1) > regime_order.get(regime_50, 1):
            regime, desc = regime_500, f"500ETF QVIX={q500:.1f} {desc_500}"
        else:
            regime, desc = regime_50, f"50ETF QVIX={q50:.1f} {desc_50}"

        signals = {
            "complacent": "trend-following effective, aggressive ETFs preferred",
            "normal": "standard screening, no adjustment",
            "cautious": "reduce aggressive weight, add broad-base defense",
            "fearful": "wait for QVIX<25, currently broad-base/bond ETFs",
        }

        result = {
            "qvix_50": round(q50, 1), "qvix_500": round(q500, 1),
            "regime": regime, "regime_50": regime_50, "regime_500": regime_500,
            "description": desc, "trade_signal": signals.get(regime, signals["normal"]),
        }
        _save_cache(data)  # Save raw akshare data for cache-first reuse
        return result

    except (KeyError, ValueError, TypeError, AttributeError, ImportError) as e:
        logger.warning("[qvix_regime] regime classification failed: %s", e)
        return fallback


def get_weight_shift(profile: str = "aggressive") -> Dict[str, float]:
    """Get weight shift based on current QVIX regime."""
    regime_data = get_regime()
    regime = regime_data.get("regime", "normal")
    shifts = {
        "complacent": {"supply": 0.0, "capital": +0.10, "signal": -0.05, "demand": -0.05},
        "normal":     {"supply": 0.0, "capital": 0.0, "signal": 0.0, "demand": 0.0},
        "cautious":   {"supply": +0.10, "capital": -0.10, "signal": -0.05, "demand": +0.05},
        "fearful":    {"supply": +0.15, "capital": -0.15, "signal": -0.10, "demand": +0.10},
        "unknown":    {"supply": 0.0, "capital": -0.05, "signal": 0.0, "demand": +0.05},
        "error":      {"supply": 0.0, "capital": 0.0, "signal": 0.0, "demand": 0.0},
    }
    return shifts.get(regime, shifts["normal"])


if __name__ == "__main__":
    r = get_regime()
    print(f"QVIX Regime: {r['regime']}")
    print(f"  50ETF QVIX: {r.get('qvix_50', 'N/A')}")
    print(f"  500ETF QVIX: {r.get('qvix_500', 'N/A')}")
    print(f"  Description: {r['description']}")
    print(f"  Signal: {r['trade_signal']}")
    print(f"  Weight shift: {get_weight_shift()}")
