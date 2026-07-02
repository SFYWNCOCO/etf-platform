"""kline.py — Fixed: Sina money finance API (no akshare dependency)."""
import urllib.request, json, statistics
from typing import Optional, Dict
from dataclasses import dataclass


@dataclass
class TrendSnapshot:
    code: str = ""
    price: float = 0.0
    change_5d: float = 0.0
    change_10d: float = 0.0
    change_20d: float = 0.0
    change_60d: float = 0.0
    high_60d: float = 0.0
    low_60d: float = 0.0
    position_pct: float = 50.0
    max_drawdown: float = 0.0
    volatility_20d: float = 0.0
    volume_ratio_5_20: float = 1.0
    trend_signal: str = "neutral"
    data_days: int = 0


SINA_KLINE_URL = "http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol=%s%s&scale=240&ma=no&datalen=%d"

def _sina_code(code):
    return "sh" if code.startswith(("5","6")) else "sz"


def get_trend(code: str, days: int = 63) -> Optional[TrendSnapshot]:
    """Fetch kline data and compute trend indicators."""
    try:
        url = SINA_KLINE_URL % (_sina_code(code), code, min(days, 1024))
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "http://finance.sina.com.cn/"
        })
        resp = urllib.request.urlopen(req, timeout=10)
        raw = resp.read().decode("gbk")
        rows = json.loads(raw)
        if not rows or len(rows) < 5:
            return None
        
        close_list = [float(r["close"]) for r in rows]
        high_list = [float(r["high"]) for r in rows]
        low_list = [float(r["low"]) for r in rows]
        vol_list = [float(r["volume"]) for r in rows]
        total = len(close_list)
        latest = close_list[-1]
        
        def chg(n):
            return ((close_list[-1] / close_list[-n-1]) - 1) * 100 if total > n else 0
        
        c5 = chg(5) if total >= 6 else 0
        c10 = chg(10) if total >= 11 else 0
        c20 = chg(20) if total >= 21 else (chg(total-1) if total > 1 else 0)
        c60 = chg(60) if total >= 61 else (chg(total-1) if total > 1 else 0)
        
        recent = close_list[-60:] if total >= 60 else close_list
        h60 = max(recent)
        l60 = min(recent)
        pos = (latest - l60) / (h60 - l60) * 100 if h60 > l60 else 50
        
        peak = close_list[0]
        dd = 0.0
        for p in close_list:
            if p > peak: peak = p
            dd = min(dd, (p - peak) / peak * 100)
        
        r_list = [(close_list[i]/close_list[i-1]-1) for i in range(1,total)]
        r20 = r_list[-20:] if len(r_list) >= 20 else r_list
        vol_20d = statistics.stdev(r20) * (252**0.5) * 100 if len(r20) > 1 else 0
        
        if len(vol_list) >= 5:
            v5 = sum(vol_list[-5:])/5
            v20 = sum(vol_list[-20:])/20 if len(vol_list)>=20 else sum(vol_list)/len(vol_list)
            vr = v5/v20 if v20 > 0 else 1.0
        else:
            vr = 1.0
        
        if pos < 15: signal = "oversold"
        elif pos < 35: signal = "weak"
        elif pos < 65: signal = "neutral"
        elif pos < 85: signal = "strong"
        else: signal = "overbought"
        
        if c5 < -5 and signal in ("weak","oversold"): signal = "plunging"
        elif c5 > 5 and signal in ("strong","overbought"): signal = "surging"
        
        return TrendSnapshot(
            code=code, price=latest,
            change_5d=round(c5,2), change_10d=round(c10,2),
            change_20d=round(c20,2), change_60d=round(c60,2),
            high_60d=round(h60,3), low_60d=round(l60,3),
            position_pct=round(pos,1), max_drawdown=round(dd,1),
            volatility_20d=round(vol_20d,1), volume_ratio_5_20=round(vr,2),
            trend_signal=signal, data_days=total,
        )
    except Exception:
        return None


def get_trend_batch(codes: list) -> Dict[str, TrendSnapshot]:
    result = {}
    for code in codes:
        try:
            t = get_trend(code)
            if t: result[code] = t
        except: continue
    return result


if __name__ == "__main__":
    sig_map = {"oversold":"超卖","weak":"回调","neutral":"中性",
               "strong":"强势","overbought":"超买","plunging":"急跌","surging":"急涨"}
    for code in ["512890","159995","159819","518880"]:
        t = get_trend(code)
        if t and t.data_days > 0:
            sig = sig_map.get(t.trend_signal, "?")
            print("%s: %.3f | 5d=%+.1f%% 10d=%+.1f%% 20d=%+.1f%% 60d=%+.1f%% | pos=%.0f%% | %s (data=%ddays, dd=%.1f%%)" % (
                code, t.price, t.change_5d, t.change_10d, t.change_20d, t.change_60d, t.position_pct, sig, t.data_days, t.max_drawdown))
        else:
            print("%s: No data" % code)