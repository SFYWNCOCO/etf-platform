# -*- coding: utf-8 -*-
"""QVIX Market Regime Indicator — l005 signal-2

QVIX intervals:
  <16: complacent → aggressive ETFs +10% weight
  16-22: normal → standard weights
  22-28: cautious → aggressive -10%, defensive +10%
  >28: fearful → aggressive -20%, wait for reversal
"""

import warnings
from typing import Dict, Tuple
from datetime import datetime

def _get_qvix_data():
    try:
        import akshare as ak
        qvix_50 = ak.index_option_50etf_qvix()
        qvix_500 = ak.index_option_500etf_qvix()
        return {"50": qvix_50, "500": qvix_500, "updated": datetime.now().isoformat()}
    except Exception:
        return None

def get_regime() -> dict:
    data = _get_qvix_data()
    if data is None:
        return {"regime": "unknown", "description": "QVIX data unavailable", "trade_signal": "use standard scoring"}
    try:
        import pandas as pd
        def _latest_qvix(df):
            df = df.copy()
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date")
            return float(df["close"].iloc[-1])
        def _classify(qvix_val):
            if qvix_val < 16: return ("complacent", "complacent, low vol")
            elif qvix_val < 22: return ("normal", "normal range")
            elif qvix_val < 28: return ("cautious", "elevated fear")
            else: return ("fearful", "fear regime, defensive")
        q50 = _latest_qvix(data["50"])
        q500 = _latest_qvix(data["500"])
        regime_50, desc_50 = _classify(q50)
        regime_500, desc_500 = _classify(q500)
        regime_order = {"complacent": 0, "normal": 1, "cautious": 2, "fearful": 3}
        if regime_order[regime_500] > regime_order[regime_50]:
            regime = regime_500
            desc = "500ETF QVIX={:.1f} {}".format(q500, desc_500)
        else:
            regime = regime_50
            desc = "50ETF QVIX={:.1f} {}".format(q50, desc_50)
        signals = {
            "complacent": "trend-following effective, aggressive ETFs preferred",
            "normal": "standard screening, no adjustment",
            "cautious": "reduce aggressive weight, add broad-base defense",
            "fearful": "wait for QVIX<25, currently broad-base/bond ETFs",
        }
        return {
            "qvix_50": round(q50, 1), "qvix_500": round(q500, 1),
            "regime": regime, "regime_50": regime_50, "regime_500": regime_500,
            "description": desc, "trade_signal": signals.get(regime, signals["normal"]),
        }
    except Exception as e:
        return {"regime": "error", "description": str(e)[:100], "trade_signal": "use standard scoring"}

def get_weight_shift(profile="aggressive") -> Dict[str, float]:
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
    print("QVIX Regime: {}".format(r["regime"]))
    print("  50ETF QVIX: {}".format(r.get("qvix_50", "N/A")))
    print("  500ETF QVIX: {}".format(r.get("qvix_500", "N/A")))
    print("  Description: {}".format(r["description"]))
    print("  Signal: {}".format(r["trade_signal"]))
    print("  Weight shift: {}".format(get_weight_shift()))