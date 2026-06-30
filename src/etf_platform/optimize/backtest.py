"""事件驱动回测引擎"""
import time
from ..config_loader import load_etfs

EVENTS_BACKTEST = [
    {"d":"2025-12-02","dir":"利空","c":["159995","512480","159819"],"n":"BIS芯片新管制","h":30,"priced":"可能"},
    {"d":"2026-04-10","dir":"利空","c":["159995","512480","159819"],"n":"日本限光刻胶","h":30,"priced":"可能"},
    {"d":"2026-04-15","dir":"利空","c":["512690"],"n":"茅台批价跌破2000","h":30,"priced":"否"},
    {"d":"2026-03-05","dir":"利好","c":["512660","512670"],"n":"两会国防预算","h":60,"priced":"可能"},
    {"d":"2026-05-10","dir":"利好","c":["516160","515030"],"n":"碳酸锂触底反弹","h":40,"priced":"否"},
    {"d":"2025-12-26","dir":"利好","c":["159819","516510"],"n":"DeepSeek-V3发布","h":60,"priced":"否"},
    {"d":"2026-02-05","dir":"利好","c":["510300","159915"],"n":"春节后资金回流","h":20,"priced":"否"},
    {"d":"2025-11-15","dir":"利好","c":["510300","512100"],"n":"降准50bp","h":30,"priced":"否"},
    {"d":"2026-01-20","dir":"利好","c":["159941","513100"],"n":"纳指创新高","h":30,"priced":"否"},
    {"d":"2026-04-01","dir":"利好","c":["518880"],"n":"金价突破3000","h":40,"priced":"否"},
    {"d":"2026-03-20","dir":"利空","c":["512880"],"n":"券商降佣新规","h":30,"priced":"可能"},
    {"d":"2026-01-05","dir":"利好","c":["512170","159992"],"n":"创新药审批加速","h":30,"priced":"否"},
    {"d":"2026-05-25","dir":"利好","c":["515170"],"n":"暑期消费预期","h":30,"priced":"可能"},
    {"d":"2025-10-15","dir":"利好","c":["512100","510500"],"n":"小盘股反弹","h":60,"priced":"否"},
    {"d":"2026-03-10","dir":"利空","c":["516160","515030"],"n":"欧盟新能源关税","h":30,"priced":"否"},
]

def _fetch_history(code):
    try:
        import akshare as ak
        pfx = "sh" if code.startswith("51") else "sz"
        df = ak.fund_etf_hist_sina(symbol=pfx+code)
        if df is None or len(df)==0: return []
        return [{"date":str(r.get("date","")),"close":float(r.get("close",0))} for _,r in df.iterrows()]
    except Exception: return []

def run_backtest():
    etfs = load_etfs()
    all_codes = set()
    for ev in EVENTS_BACKTEST:
        for c in ev["c"]:
            if c in etfs and c.isdigit(): all_codes.add(c)
    print(f"  回测: {len(EVENTS_BACKTEST)} events x {len(all_codes)} ETFs")
    hist = {}
    for i,code in enumerate(sorted(all_codes)):
        if i>0: time.sleep(0.3)
        try:
            r = _fetch_history(code)
            if r: hist[code]=r
        except Exception: continue
    if not hist: return {"trades":[],"accuracy":0,"error":"No data"}
    trades = []
    for ev in EVENTS_BACKTEST:
        for code in ev["c"]:
            if code not in hist: continue
            recs = hist[code]
            if len(recs)<5: continue
            ep = xp = None
            for r in recs:
                if r["date"]<=ev["d"]: ep=r["close"]
            for r in recs:
                if r["date"]>=ev["d"]: xp=r["close"]; break
            if xp is None and recs: xp=recs[-1]["close"]
            if ep is None or xp is None or ep==0: continue
            pnl = (xp-ep)/ep*100
            correct = (ev["dir"]=="利好" and pnl>0) or (ev["dir"]=="利空" and pnl<0)
            trades.append({"event":ev["n"],"date":ev["d"],"code":code,"dir":ev["dir"],"pnl_pct":round(pnl,2),"correct":correct,"priced":ev.get("priced","否"),"name":etfs.get(code,{}).get("name",code)})
    if not trades: return {"trades":[],"accuracy":0}
    correct_count = sum(1 for t in trades if t["correct"])
    accuracy = round(correct_count/len(trades)*100,1)
    priced = [t for t in trades if t["priced"]=="可能"]
    unpriced = [t for t in trades if t["priced"]=="否"]
    pa = round(sum(1 for t in priced if t["correct"])/max(len(priced),1)*100,1)
    ua = round(sum(1 for t in unpriced if t["correct"])/max(len(unpriced),1)*100,1)
    print(f"  Result: {len(trades)} trades, {accuracy}% accuracy")
    print(f"  Priced: {pa}% | Unpriced: {ua}%")
    return {"trades":trades,"accuracy":accuracy,"total":len(trades),"correct":correct_count,"priced_accuracy":pa,"unpriced_accuracy":ua}
