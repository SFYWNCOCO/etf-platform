"""ETF Platform Health Check + Analysis"""
import sys
sys.path.insert(0, r'D:\龙虾\.openclaw\etf-platform\src')
sys.path = [p for p in sys.path if '_internal' not in p]

from etf_platform.data import check_all_sources, get_price
from etf_platform.data.base import SourceStatus

print("=== Source Health Check ===")
results = check_all_sources()
for r in results:
    icon = {"healthy": "✓", "degraded": "⚠", "failed": "✗"}
    s = icon.get(r.status.value, "?")
    print(f"  {s} {r.source_name}: {r.status.value} ({r.latency_ms:.0f}ms)")

print("\n=== Top ETFs by EastMoney ===")
from etf_platform.data.eastmoney import EastMoneySource
em = EastMoneySource()
try:
    etfs = em.list_etfs()
    print(f"  Found {len(etfs)} ETFs")
    for e in etfs[:3]:
        print(f"  {e}")
except Exception as ex:
    print(f"  list_etfs failed: {ex}")

print("\n=== Sector >20% day gainers ===")
import urllib.request, json
url = "https://push2.eastmoney.com/api/qt/clist/get?cb=&fid=f62&po=0&pz=15&pn=1&np=1&fltt=2&invt=2&fs=m:90+t:2&fields=f12,f14,f62,f184"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
resp = urllib.request.urlopen(req, timeout=15)
data = json.loads(resp.read().decode("utf-8"))
items = data.get("data", {}).get("diff", [])
print(f"  {'行业':<20} {'涨跌幅':>8} {'主力净流入':>12}")
print(f"  {'-'*40}")
for item in items:
    pct = item.get("f184", 0)
    if isinstance(pct, str):
        try: pct = float(pct.replace("%",""))
        except: pct = 0
    if abs(pct) > 15:
        name = item.get("f14", "?")
        flow = item.get("f62", 0)
        if isinstance(flow, (int,float)):
            flow_s = f"{flow/1e8:.1f}亿"
        else:
            flow_s = str(flow)
        print(f"  {name:<20} {pct:>+7.2f}% {flow_s:>12}")

print("\n=== Done ===")