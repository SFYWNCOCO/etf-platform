"""ETF穿透分析：获取干净数据"""
import subprocess, json

def em_api(url):
    r = subprocess.run(["curl.exe", "-s", "-H", "User-Agent: Mozilla/5.0", url], 
                       capture_output=True, text=True, timeout=15)
    return json.loads(r.stdout)

# 1. 行业20日资金流（判断趋势持续性）
url = "https://push2.eastmoney.com/api/qt/clist/get?cb=&fid=f62&po=1&pz=10&pn=1&np=1&fltt=2&invt=2&fs=m:90+t:2&fields=f12,f14,f62,f184,f267,f268,f269"
data = em_api(url)

print("=== 行业TOP10 - 今日/5日/10日/20日 ===")
print(f"{'行业':<16} {'今日':>8} {'5日':>8} {'10日':>8} {'20日':>8} {'涨跌':>6}")
print("-"*60)
for item in data["data"]["diff"]:
    n = item["f14"]
    t = item.get("f62", 0) / 1e8
    d5 = item.get("f267", 0) / 1e8
    d10 = item.get("f268", 0) / 1e8 if item.get("f268") else 0
    d20 = item.get("f269", 0) / 1e8 if item.get("f269") else 0
    pct = item.get("f184", 0)
    print(f"{n:<16} {t:>+8.1f} {d5:>+8.1f} {d10:>+8.1f} {d20:>+8.1f} {pct:>6}")

# 2. 概念板块热点
url2 = "https://push2.eastmoney.com/api/qt/clist/get?cb=&fid=f62&po=1&pz=10&pn=1&np=1&fltt=2&invt=2&fs=m:90+t:3&fields=f12,f14,f62,f184"
data2 = em_api(url2)
print("\n=== 概念板块TOP10 ===")
for item in data2["data"]["diff"]:
    n = item["f14"]
    t = item.get("f62", 0) / 1e8
    pct = item.get("f184", 0)
    print(f"{n:<20} {t:>+8.1f}亿 {pct:>6}")

# 3. 获取具体ETF数据
etfs = ["159915", "510050", "512880", "159949", "513100", "512010", "515790", "512480", "159766", "516970"]
codes_str = ",".join(f"0.{c}" for c in etfs)
url3 = f"https://push2.eastmoney.com/api/qt/ulist.np/get?fields=f43,f44,f45,f46,f47,f48,f50,f57,f58,f170,f62,f115&secids={codes_str}"
data3 = em_api(url3)
print("\n=== 重点ETF行情 ===")
print(f"{'代码':<8} {'名称':<18} {'最新':>8} {'涨跌':>7} {'成交额':>10} {'换手率':>6}")
print("-"*60)
for item in data3.get("data", {}).get("diff", []):
    code = item.get("f57", "")
    name = item.get("f58", "")
    price = item.get("f43", 0) / 1000
    chg = item.get("f170", 0)
    # f170 is price change, not percentage; f62 might be something else
    amount = item.get("f62", 0) / 1e8 if isinstance(item.get("f62"), (int,float)) else 0
    turnover = item.get("f115", 0)
    print(f"{code:<8} {name:<18} {price:>8.3f} {chg:>+7} {amount:>10.1f}亿 {turnover:>6.2f}%")