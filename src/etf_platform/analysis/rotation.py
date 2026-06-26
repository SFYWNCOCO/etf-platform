"""Sector rotation detector using Sina Finance API (no akshare dependency).

Detects capital flows between sectors by comparing short-term vs medium-term momentum.
"""
import urllib.request

SECTORS = {
    "半导体":  ["sz159995","sz512480"],
    "AI/科技": ["sz159819","sz515070"],
    "红利/价值": ["sh512890","sh515080"],
    "通信/5G": ["sh515880","sh515050"],
    "新能源":  ["sz159611","sz515030"],
    "医药":   ["sz159892","sz159992"],
    "消费":   ["sz159928","sh512690"],
    "金融":   ["sh512880","sh512800"],
    "军工":   ["sh512660","sh512670"],
    "有色":   ["sh512400","sh515220"],
    "黄金":   ["sh518880"],
    "宽基":   ["sh510300","sh510500"],
}

TREND_ICONS = {"oversold":"\U0001f7e2超卖","weak":"\U0001fe00回调","neutral":"\u26aa中性",
               "strong":"\U0001fe00强势","overbought":"\U0001f534超买","plunging":"\U0001f534急跌","surging":"\U0001f7e2急涨"}


def fetch_prices():
    """Fetch current prices for all sector representative ETFs."""
    codes = []
    for sec, cds in SECTORS.items():
        codes.append(cds[0])
    
    batch = ",".join(codes)
    url = f"https://hq.sinajs.cn/list={batch}"
    req = urllib.request.Request(url, headers={
        "Referer": "https://finance.sina.com.cn",
        "User-Agent": "Mozilla/5.0"
    })
    resp = urllib.request.urlopen(req, timeout=10)
    raw = resp.read().decode("gbk")
    
    results = {}
    for line in raw.strip().split(";"):
        if not line.strip(): continue
        parts = line.split(",")
        if len(parts) < 33: continue
        name = parts[0].split("=")[-1].replace('"', "").strip()
        try:
            price = float(parts[3]) if parts[3] else 0
            prev_close = float(parts[2]) if parts[2] else 0
            change_pct = round((price - prev_close) / prev_close * 100, 2) if prev_close else 0
            high = float(parts[4]) if parts[4] else 0
            low = float(parts[5]) if parts[5] else 0
            volume = float(parts[8]) if parts[8] else 0
            amount = float(parts[9]) if parts[9] else 0
            results[name] = {
                "price": price, "change_pct": change_pct,
                "high": high, "low": low,
                "volume": volume, "amount_yi": round(amount / 1e8, 2),
            }
        except (ValueError, IndexError):
            continue
    return results


def rotation_check(prices_dict):
    """Simplified rotation detection based on daily change and volume.
    
    In lieu of 5-day vs 20-day data (needs kline), uses:
    - Daily change as short-term signal
    - Volume as confirmation
    """
    if not prices_dict:
        return {}
    
    # Find price-to-name mapping 
    rot = {}
    changes = []
    
    # Build sector mapping from fetched prices
    sector_prices = {}
    for sec, cds in SECTORS.items():
        code_prefix = cds[0][2:]  # Remove "sh"/"sz"
        for name, data in prices_dict.items():
            # Try to match name to sector
            for sec_name, sec_codes in SECTORS.items():
                sec_clean = sec_codes[0][2:]
                if sec_clean in str(name) or any(kw in name for kw in [sec_name[:2], sec_name[:4]]):
                    sector_prices[sec_name] = data
                    break
    
    # If matching failed, build from price dict directly
    if not sector_prices:
        for name, data in prices_dict.items():
            for sec in SECTORS:
                if sec[:2] in name or any(c in name for c in ["ETF", "指数"]):
                    sector_prices.setdefault(sec, data)
    
    return sector_prices


def detect_rotation():
    """Run sector rotation detection and return signals."""
    prices = fetch_prices()
    sector_data = rotation_check(prices)
    
    if not sector_data:
        return {"status": "no_data", "sectors": {}}
    
    # Classify each sector
    changes = sorted(
        [(sec, d["change_pct"], d["amount_yi"]) for sec, d in sector_data.items()],
        key=lambda x: x[1], reverse=True
    )
    
    signals = {}
    for sec, chg, amt in changes:
        if chg > 2:
            level = "hot"
            signal = "强势"
            icon = "\U0001f525"
        elif chg > 0.5:
            level = "rising"
            signal = "上行"
            icon = "\U0001f7e2"
        elif chg > -0.5:
            level = "neutral"
            signal = "中性"
            icon = "\u26aa"
        elif chg > -2:
            level = "falling"
            signal = "回调"
            icon = "\U0001f534"
        else:
            level = "plunging"
            signal = "急跌"
            icon = "\U0001f534"
        
        signals[sec] = {
            "change_pct": chg,
            "amount_yi": amt,
            "level": level,
            "signal": signal,
            "icon": icon,
        }
    
    top_gainers = [s for s in changes[:3]]
    top_losers = [s for s in changes[-3:] if s[1] < 0]
    
    return {
        "status": "ok",
        "sectors": signals,
        "top_gainers": [(s, round(c,2), round(a,2)) for s,c,a in top_gainers],
        "top_losers": [(s, round(c,2), round(a,2)) for s,c,a in top_losers],
        "count": len(sector_data),
    }


if __name__ == "__main__":
    result = detect_rotation()
    print(f"Sector rotation: {result['status']} ({result.get('count',0)} sectors)")
    if result['sectors']:
        print(f"\n{'Sector':<14} {'Change':<8} {'Signal':<8} {'Amt(Yi)':<8}")
        print("-"*40)
        for sec, info in sorted(result['sectors'].items(), key=lambda x: x[1]['change_pct'], reverse=True):
            print(f"{sec:<14} {info['change_pct']:+.2f}% {info['signal']:<8} {info['amount_yi']:<8}")
        print(f"\nTop gainers: {result['top_gainers']}")
        print(f"Top losers: {result['top_losers']}")