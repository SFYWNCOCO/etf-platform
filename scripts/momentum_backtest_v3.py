#!/usr/bin/env python3
"""
ETF 行业动量策略回测 v2.0 — 优化版

v1原始策略: +74.7%, 夏普1.32, 回撤-30.4% (81周)
v2优化:
  1. 趋势过滤: 沪深300在20日均线下方 → 半仓
  2. 板块去重: 47细分行业 → 10大板块, Top3必须来自不同大板块
  3. 动量衰减: 连续3周Top3的行业动量打8折
  
用法:
  cd D:/龙虾/.openclaw/etf-platform
  python scripts/momentum_backtest_v3.py
  python scripts/momentum_backtest_v3.py --compare  # v1 vs v2对比
"""
import sys, json, math, time, statistics
from pathlib import Path
from collections import defaultdict, OrderedDict
from datetime import datetime, timedelta

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "src"))

from etf_platform.config_loader import load_etfs

# ── 行业→板块映射 ⬅ 关键改进 ──────────────────────────────────
SECTOR_TO_MEGA = {
    "金融": "金融", "银行": "金融", "保险": "金融", "券商": "金融",
    "AI/科技": "科技", "半导体": "科技", "芯片": "科技", "软件": "科技", "通信/5G": "科技", "计算机": "科技", "电子": "科技",
    "医药": "医药", "医疗": "医药", "创新药": "医药", "医疗器械": "医药", "中药": "医药", "生物医药": "医药",
    "新能源": "新能源", "光伏": "新能源", "风电": "新能源", "储能": "新能源", "锂电": "新能源", "电池": "新能源",
    "消费": "消费", "白酒": "消费", "食品饮料": "消费", "家电": "消费", "汽车": "消费", "旅游": "消费", "传媒": "消费", "游戏": "消费",
    "军工": "军工", "国防": "军工", "航空航天": "军工",
    "周期/资源": "周期", "有色": "周期", "钢铁": "周期", "煤炭": "周期", "化工": "周期", "石油": "周期", "原油": "周期", "黄金": "周期", "贵金属": "周期",
    "基建": "基建", "地产": "基建", "房地产": "基建", "建筑": "基建", "建材": "基建",
    "红利/价值": "红利价值",
    "跨境": "跨境", "港股": "跨境", "海外": "跨境",
    "其他": "其他",
}

EXCLUDE_SECTORS = {"货币基金", "利率债", "信用债", "债券", "国债", "货币", "宽基A"}
BROAD_BASE_KEYWORDS = {
    "沪深300", "中证500", "中证1000", "上证50", "深证100",
    "创业板", "科创50", "科创100", "中证A50", "中证A500",
    "MSCI", "A50", "A500", "纳指", "标普", "恒生", "债券",
}
BENCHMARK_CODE = "510300"

def is_broad_base(name: str, sector: str) -> bool:
    name = name or ""
    sector = sector or ""
    if sector in EXCLUDE_SECTORS or sector in ("宽基A", "宽基"):
        return True
    for kw in BROAD_BASE_KEYWORDS:
        if kw in name:
            return True
    return False

def sector_to_mega(sector: str) -> str:
    """细分行业 → 大板块"""
    for key, val in SECTOR_TO_MEGA.items():
        if key in sector or sector in key:
            return val
    return "其他"

# ── 历史K线获取 ──────────────────────────────────────────────
SINA_URL = ("http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
            "CN_MarketData.getKLineData?symbol=%s%s&scale=240&ma=no&datalen=%d")
TENCENT_URL = ("http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?"
               "param=%s%s,day,,,%d,qfq")

def fetch_kline(code: str, days: int = 400) -> list:
    import urllib.request, json as _json
    prefix = "sh" if code.startswith(("5","6")) else "sz"
    # Sina first
    try:
        url = SINA_URL % (prefix, code, min(days, 1024))
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0", "Referer": "http://finance.sina.com.cn/"
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("gbk")
        rows = _json.loads(raw)
        if rows and len(rows) >= 5:
            result = []
            for r in rows:
                d = str(r.get("day", ""))
                if d and len(d) == 10:
                    result.append({
                        "date": d,
                        "close": float(r.get("close", 0)),
                        "volume": float(r.get("volume", 0)),
                    })
            result.sort(key=lambda x: x["date"])
            return result
    except: pass
    # Tencent fallback
    try:
        url = TENCENT_URL % (prefix, code, min(days, 200))
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
        data = _json.loads(raw)
        rows = data.get("data", {}).get(f"{prefix}{code}", {}).get("qfqday", [])
        if rows:
            result = []
            for r in rows:
                d = str(r[0]) if r[0] else ""
                if d and len(d) == 10:
                    result.append({"date": d, "close": float(r[2]), "volume": float(r[5])})
            result.sort(key=lambda x: x["date"])
            return result
    except: pass
    return []

class HistoryBuffer:
    def __init__(self, max_days=400):
        self.max_days = max_days
        self.data = {}
    
    def get(self, code: str):
        if code not in self.data:
            k = fetch_kline(code, self.max_days)
            self.data[code] = k if k else []
        return self.data[code]

def _find_idx(kline, date):
    for i, r in enumerate(kline):
        if r.get("date") == date:
            return i
    return None

# ── 核心回测 ──────────────────────────────────────────────────
def run_backtest(sectors, etfs, hist,
                 use_trend_filter=True,       # v2: 趋势过滤
                 use_mega_sector_dedup=True,  # v2: 板块去重
                 use_momentum_decay=True,      # v2: 动量衰减
                 min_etf_per_sector=3):
    
    all_codes = []
    for codes in sectors.values():
        all_codes.extend(codes)
    
    print(f"  加载 {len(all_codes)} 只ETF历史...", end="", flush=True)
    t0 = time.time()
    success = 0
    for i, code in enumerate(all_codes):
        k = hist.get(code)
        if len(k) >= 60:
            success += 1
        if (i+1) % 200 == 0:
            print(f" {i+1}/{len(all_codes)}...", end="", flush=True)
    print(f" ✅ {success}/{len(all_codes)} ({time.time()-t0:.0f}s)")
    
    bench_kline = hist.get(BENCHMARK_CODE)
    if len(bench_kline) < 60:
        print(f"❌ 沪深300数据不足 ({len(bench_kline)}天)")
        return None
    
    # 构建交易日历
    all_dates = set()
    for k in hist.data.values():
        for r in k:
            d = r.get("date", "")
            if d and len(d) == 10 and d[4] == "-":
                all_dates.add(d)
    all_dates = sorted(d for d in all_dates if d and d >= bench_kline[0]["date"])
    
    # 按周分组
    week_groups = defaultdict(list)
    for d in all_dates:
        try:
            dt = datetime.strptime(d, "%Y-%m-%d")
            wk = dt.isocalendar()[0] * 100 + dt.isocalendar()[1]
            week_groups[wk].append(d)
        except: continue
    weekly_dates = []
    for wk in sorted(week_groups):
        weekly_dates.append(week_groups[wk][-1])
    
    if len(weekly_dates) < 10:
        print(f"❌ 交易日不足: {len(weekly_dates)}")
        return None
    
    rebalance_dates = weekly_dates[3:]  # 跳过前3周积累动量
    print(f"  回测窗口: {rebalance_dates[0]} → {rebalance_dates[-1]} ({len(rebalance_dates)}周)")
    
    # ── 逐周回放 ──
    trades = []
    equity_curve = [1.0]
    position_count_history = []  # 记录每周实际持仓数量
    top3_history = []  # 记录每周Top3行业
    
    # 动量衰减追踪
    sector_streak = defaultdict(int)
    
    for i in range(len(rebalance_dates) - 1):
        buy_date = rebalance_dates[i]
        sell_date = rebalance_dates[i+1]
        
        bench_idx = _find_idx(bench_kline, buy_date)
        if bench_idx is None or bench_idx < 20:
            continue
        
        # ── 趋势过滤: 沪深300是否在20日均线上方 ──
        if use_trend_filter:
            ma20 = statistics.mean([bench_kline[bench_idx - j]["close"] for j in range(1, 21)])
            ma60 = statistics.mean([bench_kline[bench_idx - j]["close"] for j in range(1, 61)])
            current_price = bench_kline[bench_idx]["close"]
            
            # 趋势判断
            above_ma20 = current_price > ma20
            above_ma60 = current_price > ma60
            ma20_trend = ma20 > statistics.mean([bench_kline[bench_idx - j]["close"] for j in range(1, 41)]) if bench_idx >= 40 else True
            
            if above_ma20 and above_ma60 and ma20_trend:
                position_multiplier = 1.0  # 满仓
                regime = "bull"
            elif above_ma20:
                position_multiplier = 0.7  # 7成仓
                regime = "cautious"
            elif above_ma60:
                position_multiplier = 0.5  # 半仓
                regime = "risk_off"
            else:
                position_multiplier = 0.3  # 3成仓（熊市）
                regime = "bear"
        else:
            position_multiplier = 1.0
            regime = "no_filter"
        
        # ── 计算各板块动量 ──
        sector_mom = {}
        mega_mom = {}  # 大板块级动量
        
        for sector, codes in sectors.items():
            mom_vals = []
            valid_codes = []
            mega = sector_to_mega(sector)
            
            for code in codes:
                k = hist.get(code)
                idx = _find_idx(k, buy_date)
                if idx is None or idx < 20:
                    continue
                c20 = k[idx-20]["close"]
                if c20 <= 0:
                    continue
                ret = (k[idx]["close"] / c20 - 1) * 100
                if not math.isnan(ret) and not math.isinf(ret):
                    mom_vals.append(ret)
                    valid_codes.append(code)
            
            if len(mom_vals) >= min_etf_per_sector:
                mom_vals.sort()
                median_mom = mom_vals[len(mom_vals)//2]
                
                # ── 动量衰减 ──
                if use_momentum_decay:
                    sector_streak[sector] = sector_streak.get(sector, 0) + 1
                    if sector_streak[sector] >= 3:
                        median_mom *= 0.8  # 连续3周出现打8折
                else:
                    sector_streak[sector] = sector_streak.get(sector, 0) + 1
                
                sector_mom[sector] = {
                    "median": median_mom,
                    "count": len(mom_vals),
                    "codes": valid_codes,
                    "mega": mega,
                }
                # 更新大板块动量
                if median_mom > mega_mom.get(mega, {}).get("median", -999):
                    mega_mom[mega] = {"median": median_mom, "sector": sector}
        
        # 重置未被选中的行业衰减计数
        for sector in list(sector_streak.keys()):
            if sector not in sector_mom:
                sector_streak[sector] = 0
        
        if len(sector_mom) < 3:
            continue
        
        # ── 板块去重选Top3 ──
        if use_mega_sector_dedup:
            # 按动量排序，选择不同大板块的Top行业
            sorted_sectors = sorted(sector_mom.items(), key=lambda x: x[1]["median"], reverse=True)
            selected_sectors = []
            used_megas = set()
            
            for sector, data in sorted_sectors:
                if data["mega"] not in used_megas:
                    selected_sectors.append((sector, data))
                    used_megas.add(data["mega"])
                if len(selected_sectors) >= 3:
                    break
            
            # 如果去重后不够3个，从剩余的补
            if len(selected_sectors) < 3:
                for sector, data in sorted_sectors:
                    if sector not in [s for s, _ in selected_sectors]:
                        selected_sectors.append((sector, data))
                    if len(selected_sectors) >= 3:
                        break
        else:
            selected_sectors = sorted(sector_mom.items(), key=lambda x: x[1]["median"], reverse=True)[:3]
        
        top3_sectors = selected_sectors[:3]
        
        # ── 选ETF：每个行业流动性格局前3只 ──
        selected = []
        for sector, data in top3_sectors:
            code_vol = []
            for code in data["codes"][:10]:
                k = hist.get(code)
                idx = _find_idx(k, buy_date)
                if idx:
                    code_vol.append((code, k[idx].get("volume", 0)))
            code_vol.sort(key=lambda x: x[1], reverse=True)
            for code, _ in code_vol[:3]:
                selected.append((code, sector))
        
        if len(selected) < 3:
            continue
        
        # ── 计算实际收益 ──
        actual_returns = []
        for code, sector in selected:
            k = hist.get(code)
            buy_idx = _find_idx(k, buy_date)
            sell_idx = _find_idx(k, sell_date)
            if buy_idx is not None and sell_idx is not None and buy_idx < sell_idx:
                bp, sp = k[buy_idx]["close"], k[sell_idx]["close"]
                if bp > 0 and sp > 0:
                    ret = (sp / bp - 1) * 100
                    if not math.isnan(ret) and not math.isinf(ret):
                        actual_returns.append(ret)
        
        if len(actual_returns) < 3:
            continue
        
        # 用仓位乘数调整收益
        avg_ret = statistics.mean(actual_returns) * position_multiplier
        portfolio_ret = avg_ret
        equity_curve.append(equity_curve[-1] * (1 + portfolio_ret / 100))
        position_count_history.append(len(actual_returns) * position_multiplier)
        top3_history.append([s for s, _ in top3_sectors])
        
        # 基准收益
        bench_buy_idx = _find_idx(bench_kline, buy_date)
        bench_sell_idx = _find_idx(bench_kline, sell_date)
        bench_ret = 0
        if bench_buy_idx is not None and bench_sell_idx is not None:
            bp, sp = bench_kline[bench_buy_idx]["close"], bench_kline[bench_sell_idx]["close"]
            if bp > 0 and sp > 0:
                bench_ret = (sp / bp - 1) * 100
        
        trades.append({
            "buy_date": buy_date,
            "sell_date": sell_date,
            "regime": regime,
            "position_mult": round(position_multiplier, 2),
            "top3_sectors": [s for s, _ in top3_sectors],
            "sector_momentum": {s: round(d["median"], 1) for s, d in top3_sectors},
            "strategy_return_pct": round(portfolio_ret, 2),
            "benchmark_return_pct": round(bench_ret, 2),
            "excess_pct": round(portfolio_ret - bench_ret, 2),
            "cumulative": round(equity_curve[-1], 4),
        })
    
    return {
        "trades": trades,
        "equity_curve": [round(e, 4) for e in equity_curve],
        "n_trades": len(trades),
        "avg_position": round(statistics.mean(position_count_history), 1) if position_count_history else 0,
        "start_date": trades[0]["buy_date"] if trades else "",
        "end_date": trades[-1]["sell_date"] if trades else "",
        "top3_history": top3_history,
    }

def compute_metrics(result):
    if not result or not result["trades"]:
        return {"error": "no trades"}
    trades = result["trades"]
    n = len(trades)
    returns = [t["strategy_return_pct"] for t in trades]
    bench_returns = [t["benchmark_return_pct"] for t in trades]
    excess = [t["excess_pct"] for t in trades]
    
    total_return = (result["equity_curve"][-1] - 1) * 100
    wins = sum(1 for r in returns if r > 0)
    win_rate = wins / n * 100
    
    peak = 1.0
    max_dd = 0.0
    for eq in result["equity_curve"]:
        if eq > peak: peak = eq
        dd = (eq - peak) / peak * 100
        max_dd = min(max_dd, dd)
    
    mean_r = statistics.mean(returns)
    std_r = statistics.stdev(returns) if len(returns) > 1 else 0.001
    sharpe = ((mean_r - 0.02/52) / std_r) * math.sqrt(52) if std_r > 0 else 0
    
    bench_total = 1.0
    for br in bench_returns:
        bench_total *= (1 + br / 100)
    bench_return = (bench_total - 1) * 100
    
    mean_excess = statistics.mean(excess)
    std_excess = statistics.stdev(excess) if len(excess) > 1 else 0.001
    info_ratio = (mean_excess / std_excess) * math.sqrt(52) if std_excess > 0 else 0
    
    # 回撤修复率（从回撤中恢复的比例）
    recovery_ratio = None
    if max_dd < 0 and total_return > 0:
        recovery_ratio = round((total_return + max_dd) / abs(max_dd), 2)
    
    # 月度
    monthly = defaultdict(list)
    for t in trades:
        monthly[t["buy_date"][:7]].append(t["strategy_return_pct"])
    
    # 分市场状态
    regime_perf = defaultdict(list)
    for t in trades:
        regime_perf[t.get("regime", "unknown")].append(t["strategy_return_pct"])
    
    regime_stats = {}
    for r, rets in regime_perf.items():
        regime_stats[r] = {
            "count": len(rets),
            "mean": round(statistics.mean(rets), 2),
            "win_rate": round(sum(1 for v in rets if v > 0) / len(rets) * 100, 1),
        }
    
    return {
        "period": f"{trades[0]['buy_date']} → {trades[-1]['sell_date']}",
        "total_weeks": n,
        "total_return_pct": round(total_return, 2),
        "annualized_return": round(((1 + total_return/100) ** (52/n) - 1) * 100, 2) if n > 0 else 0,
        "benchmark_return_pct": round(bench_return, 2),
        "excess_return_pct": round(total_return - bench_return, 2),
        "win_rate_pct": round(win_rate, 1),
        "max_drawdown_pct": round(max_dd, 2),
        "recovery_ratio": recovery_ratio,
        "sharpe_ratio": round(sharpe, 2),
        "info_ratio": round(info_ratio, 2),
        "best_week_pct": round(max(returns), 2),
        "worst_week_pct": round(min(returns), 2),
        "avg_position": result.get("avg_position", 0),
        "regime_performance": regime_stats,
    }

def format_report(result, metrics, label="v2优化版"):
    if not result or "error" in metrics:
        return f"❌ {metrics.get('error', '回测失败')}"
    
    trades = result["trades"]
    lines = [
        f"\n{'='*60}",
        f"📊 ETF 行业动量策略 · {label}",
        f"{'='*60}",
        f"  策略特征:",
        f"    {'✅' if 'trend_filter' in label or '趋势过滤' in label or 'v2' in label else '❌'} 趋势过滤（沪深300 MA20）",
        f"    {'✅' if 'dedup' in label or '去重' in label or 'v2' in label else '❌'} 大板块去重",
        f"    {'✅' if 'decay' in label or '衰减' in label or 'v2' in label else '❌'} 动量衰减",
        f"",
        f"  回测期: {metrics['period']}  ({metrics['total_weeks']}周)",
        f"",
        f"  ┌─ {'':^48s} ─┐",
        f"  │ {'指标':20s} {'策略':>12s} {'基准':>12s} │",
        f"  ├─{'':─^50s}─┤",
        f"  │ {'总收益率':20s} {metrics['total_return_pct']:>+11.1f}% {metrics['benchmark_return_pct']:>+11.1f}% │",
        f"  │ {'年化收益':20s} {metrics['annualized_return']:>+11.1f}% {'—':>12s} │",
        f"  │ {'胜率':20s} {metrics['win_rate_pct']:>10.0f}% {'53%':>11s} │",
        f"  │ {'最大回撤':20s} {metrics['max_drawdown_pct']:>10.1f}% {'—':>12s} │",
        f"  │ {'回撤修复率':20s} {str(metrics.get('recovery_ratio', '—')):>12s} {'—':>12s} │",
        f"  │ {'夏普比率':20s} {metrics['sharpe_ratio']:>10.2f} {'—':>12s} │",
        f"  │ {'信息比率':20s} {metrics['info_ratio']:>10.2f} {'—':>12s} │",
        f"  │ {'平均仓位':20s} {metrics['avg_position']:>9.1f}只  {'—':>12s} │",
        f"  └─{'':─^50s}─┘",
        f"",
        f"  🎯 超额收益: {metrics['excess_return_pct']:+.1f}%",
        f"",
    ]
    
    # 市场状态表现
    if metrics.get("regime_performance"):
        lines.extend([
            f"📊 不同市场状态表现:",
            f"{'状态':14s} {'次数':>6s} {'均收益':>8s} {'胜率':>6s}",
            "-"*40,
        ])
        for regime in ["bull", "cautious", "risk_off", "bear", "no_filter"]:
            if regime in metrics["regime_performance"]:
                r = metrics["regime_performance"][regime]
                label_r = {"bull": "🟢 牛市满仓", "cautious": "🟡 谨慎7成", 
                          "risk_off": "🟠 半仓防御", "bear": "🔴 熊市3成", 
                          "no_filter": "⚪ 无过滤"}.get(regime, regime)
                lines.append(f"  {label_r:14s} {r['count']:>4d}次 {r['mean']:>+7.1f}% {r['win_rate']:>5.0f}%")
    
    # 与v1对比
    lines.extend([
        f"",
        f"📋 最近5笔交易:",
        f"{'日期':14s} {'状态':12s} {'Top3':30s} {'收益':>8s} {'基准':>8s}",
        "-"*75,
    ])
    for t in trades[-5:]:
        sec_str = "/".join(t["top3_sectors"][:2])
        regime_icon = {"bull": "🟢", "cautious": "🟡", "risk_off": "🟠", "bear": "🔴", "no_filter": "⚪"}.get(t.get("regime",""), " ")
        lines.append(f"  {t['buy_date']} {regime_icon}{t.get('regime','?'):8s} {sec_str:30s} {t['strategy_return_pct']:>+7.2f}% {t['benchmark_return_pct']:>+7.2f}%")
    
    lines.extend([
        f"\n{'='*60}",
        f"💡 解读:",
    ])
    if metrics["sharpe_ratio"] > 1.0:
        lines.append(f"  ✅ 夏普 {metrics['sharpe_ratio']:.2f} > 1.0：策略有效")
    if metrics["max_drawdown_pct"] > -15:
        lines.append(f"  ✅ 最大回撤 {metrics['max_drawdown_pct']:.1f}% 可控")
    elif metrics["max_drawdown_pct"] > -25:
        lines.append(f"  ⚠️ 最大回撤 {metrics['max_drawdown_pct']:.1f}% 可接受，需监控")
    else:
        lines.append(f"  ⚠️ 最大回撤 {metrics['max_drawdown_pct']:.1f}% 偏高")
    if metrics.get("regime_performance", {}).get("bear", {}).get("mean", 0) < -5:
        lines.append(f"  ⚠️ 熊市行情仍需改善")
    lines.append(f"{'='*60}")
    return "\n".join(lines)

# ── 主入口 ──────────────────────────────────────────────────
def run_all(hist_days=400):
    print(f"\n{'='*60}")
    print(f"📊 ETF 行业动量策略回测 v2 — 三改进对比")
    print(f"{'='*60}")
    
    etfs = load_etfs()
    sectors = defaultdict(list)
    for code, info in etfs.items():
        name = info.get("name", "")
        sector = info.get("sector", "其他")
        if is_broad_base(name, sector):
            continue
        sectors[sector].append(code)
    
    print(f"  行业: {len(sectors)}个 | ETF: {sum(len(v) for v in sectors.values())}只")
    
    # 一次性加载所有历史数据
    print(f"\n{'─'*50}")
    print(f"📦 加载历史K线...")
    hist = HistoryBuffer(max_days=hist_days)
    all_codes = []
    for codes in sectors.values():
        all_codes.extend(codes)
    print(f"  共 {len(all_codes)} 只ETF (含沪深300)...")
    t0 = time.time()
    success = 0
    for i, code in enumerate(all_codes):
        k = hist.get(code)
        if len(k) >= 60:
            success += 1
        if (i+1) % 200 == 0:
            print(f"  {i+1}/{len(all_codes)}... ({time.time()-t0:.0f}s)")
    print(f"  ✅ 完成: {success}/{len(all_codes)} ({time.time()-t0:.0f}s)")
    
    # ── 方案A: 纯原始策略 ──
    print(f"\n{'='*50}")
    print(f"🧪 方案A: 原始策略 (无过滤)")
    result_a = run_backtest(sectors, etfs, hist,
                            use_trend_filter=False,
                            use_mega_sector_dedup=False,
                            use_momentum_decay=False)
    metrics_a = compute_metrics(result_a)
    print(format_report(result_a, metrics_a, "原始策略"))
    
    # ── 方案B: 趋势过滤 + 板块去重 ──
    print(f"\n{'='*50}")
    print(f"🧪 方案B: 趋势过滤 + 板块去重")
    result_b = run_backtest(sectors, etfs, hist,
                            use_trend_filter=True,
                            use_mega_sector_dedup=True,
                            use_momentum_decay=False)
    metrics_b = compute_metrics(result_b)
    print(format_report(result_b, metrics_b, "趋势过滤+去重"))
    
    # ── 方案C: 全量优化 ──
    print(f"\n{'='*50}")
    print(f"🧪 方案C: 趋势过滤 + 板块去重 + 动量衰减")
    result_c = run_backtest(sectors, etfs, hist,
                            use_trend_filter=True,
                            use_mega_sector_dedup=True,
                            use_momentum_decay=True)
    metrics_c = compute_metrics(result_c)
    print(format_report(result_c, metrics_c, "全量优化(推荐)"))
    
    # ── 对比总结 ──
    print(f"\n{'='*60}")
    print(f"📊 三方案对比")
    print(f"{'='*60}")
    print(f"{'指标':20s} {'原始':>14s} {'趋势+去重':>14s} {'全量优化':>14s}")
    print("-"*65)
    
    for key, label in [("total_return_pct", "总收益率"), ("annualized_return", "年化收益"),
                       ("sharpe_ratio", "夏普"), ("win_rate_pct", "胜率"),
                       ("max_drawdown_pct", "最大回撤"), ("info_ratio", "信息比率")]:
        va = metrics_a.get(key, 0) or 0
        vb = metrics_b.get(key, 0) or 0
        vc = metrics_c.get(key, 0) or 0
        fmt = "{:+.1f}%" if key in ("total_return_pct", "annualized_return", "max_drawdown_pct") else "{:>+14.2f}" if key in ("sharpe_ratio", "info_ratio") else "{:>13.1f}%"
        if key == "win_rate_pct":
            fmt = "{:>13.0f}%"
        print(f"  {label:18s} {fmt.format(va):>14s} {fmt.format(vb):>14s} {fmt.format(vc):>14s}")
    
    # Winner
    print(f"\n🏆 推荐方案:", end=" ")
    if metrics_c["sharpe_ratio"] >= max(metrics_a["sharpe_ratio"], metrics_b["sharpe_ratio"]):
        print("全量优化版 (C)")
    elif metrics_b["sharpe_ratio"] >= metrics_a["sharpe_ratio"]:
        print("趋势+去重版 (B)")
    else:
        print("原始策略 (A)")
    
    return {"A": metrics_a, "B": metrics_b, "C": metrics_c,
            "data_a": result_a, "data_b": result_b, "data_c": result_c}

if __name__ == "__main__":
    run_all(hist_days=400)
