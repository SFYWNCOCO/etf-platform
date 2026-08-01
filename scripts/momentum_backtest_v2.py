#!/usr/bin/env python3
"""
ETF 行业动量历史回测引擎 v2.0

真正的历史回测：用历史日线数据回放策略
- 在每个周五计算过去20日行业动量 → Top3行业等权买入
- 持有1周 → 下周5卖出，计算实际收益
- 对比沪深300基准
- 输出完整资金曲线

用法:
  cd D:/龙虾/.openclaw/etf-platform
  python scripts/momentum_backtest_v2.py              # 完整回测
  python scripts/momentum_backtest_v2.py --days 400   # 更多历史数据
  python scripts/momentum_backtest_v2.py --weekdays 0,1,2,3,4  # 每日调仓(更频繁)
"""
import sys, json, math, time, statistics
from pathlib import Path
from collections import defaultdict, OrderedDict
from datetime import datetime, timedelta

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "src"))

from etf_platform.data.kline import get_trend_batch, get_trend, TrendSnapshot
from etf_platform.config_loader import load_etfs

# ── 过滤配置 ──────────────────────────────────────────────────────
EXCLUDE_SECTORS = {"货币基金", "利率债", "信用债", "债券", "国债", "货币"}
BROAD_BASE_KEYWORDS = {
    "沪深300", "中证500", "中证1000", "上证50", "深证100",
    "创业板", "科创50", "科创100", "中证A50", "中证A500",
    "MSCI", "A50", "A500",
}
BENCHMARK_CODE = "510300"  # 沪深300 ETF

def is_broad_base(name: str, sector: str) -> bool:
    name = name or ""
    sector = sector or ""
    if sector in EXCLUDE_SECTORS or sector in ("宽基A", "宽基"):
        return True
    for kw in BROAD_BASE_KEYWORDS:
        if kw in name:
            return True
    return False

def load_sector_etfs():
    etfs = load_etfs()
    sectors = defaultdict(list)
    for code, info in etfs.items():
        name = info.get("name", "")
        sector = info.get("sector", "其他")
        if is_broad_base(name, sector):
            continue
        sectors[sector].append(code)
    return sectors, etfs

# ── 历史K线数据引擎 ───────────────────────────────────────────
SINA_KLINE_URL = ("http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
                  "CN_MarketData.getKLineData?symbol=%s%s&scale=240&ma=no&datalen=%d")
TENCENT_KLINE_URL = ("http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?"
                     "param=%s%s,day,,,%d,qfq")

def _sina_prefix(code):
    return "sh" if code.startswith(("5","6")) else "sz"

def fetch_historical_kline(code: str, days: int = 400) -> list:
    """获取历史日线数据，返回 [{date, close, volume}, ...] 按日期升序"""
    import urllib.request, urllib.error, json as _json
    prefix = _sina_prefix(code)
    
    # Try Sina first (supports up to 1024 days)
    try:
        url = SINA_KLINE_URL % (prefix, code, min(days, 1024))
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "http://finance.sina.com.cn/"
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("gbk")
        rows = _json.loads(raw)
        if rows and len(rows) >= 5:
            result = []
            for r in rows:
                result.append({
                    "date": str(r.get("day", "")),
                    "close": float(r.get("close", 0)),
                    "volume": float(r.get("volume", 0)),
                    "high": float(r.get("high", 0)),
                    "low": float(r.get("low", 0)),
                    "open": float(r.get("open", 0)),
                })
            result.sort(key=lambda x: x["date"])
            return result
    except Exception as e:
        pass
    
    # Fallback: Tencent
    try:
        url = TENCENT_KLINE_URL % (prefix, code, min(days, 200))
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
        data = _json.loads(raw)
        rows = data.get("data", {}).get(f"{prefix}{code}", {}).get("qfqday", [])
        if rows and len(rows) >= 5:
            result = []
            for r in rows:
                result.append({
                    "date": str(r[0]),
                    "close": float(r[2]),
                    "volume": float(r[5]),
                    "high": float(r[3]),
                    "low": float(r[4]),
                    "open": float(r[1]),
                })
            result.sort(key=lambda x: x["date"])
            return result
    except Exception as e:
        pass
    return []

def compute_return_at(kline: list, offset: int, lookback: int = 20):
    """计算在kline[offset]处的lookback日收益率"""
    if offset - lookback < 0:
        return None
    return (kline[offset]["close"] / kline[offset - lookback]["close"] - 1) * 100

class HistoryBuffer:
    """缓存所有ETF的历史K线数据"""
    def __init__(self, max_days=400):
        self.max_days = max_days
        self.data = {}  # code -> [{date, close, ...}]
        self.loaded = set()
    
    def get(self, code: str):
        if code not in self.data:
            k = fetch_historical_kline(code, self.max_days)
            self.data[code] = k if k else []
        return self.data[code]

# ── 策略 ──────────────────────────────────────────────────────────
def simulate_weekly_rebalance(sectors: dict, etfs: dict, 
                                hist: HistoryBuffer,
                                min_etf_per_sector: int = 3):
    """
    真正的历史回测：
    1. 找到所有周五（或最接近周五的交易日）
    2. 在每个周五：
       a. 计算每个行业的过去20日动量（中位数）
       b. 选出Top3行业
       c. 每个行业选3只ETF，等权买入
       d. 持有到下一个周五，计算实际收益
    3. 对比沪深300
    """
    # 获取所有ETF的历史数据
    all_codes = []
    for codes in sectors.values():
        all_codes.extend(codes)
    
    print(f"  加载 {len(all_codes)} 只ETF的历史K线（{hist.max_days}天）...", flush=True)
    t0 = time.time()
    success = 0
    for i, code in enumerate(all_codes):
        k = hist.get(code)
        if len(k) >= 60:
            success += 1
        if (i+1) % 100 == 0:
            print(f"    {i+1}/{len(all_codes)}... ({time.time()-t0:.0f}s)", flush=True)
    print(f"  完成: {success}/{len(all_codes)} ETF有足够数据 ({time.time()-t0:.1f}s)", flush=True)
    
    if success < 100:
        print(f"⚠️  数据量不足，可能影响回测质量")
    
    # 获取沪深300历史
    bench_kline = hist.get(BENCHMARK_CODE)
    if len(bench_kline) < 60:
        print(f"⚠️  沪深300数据不足 ({len(bench_kline)}天)")
        return []
    
    # 找到所有交易周的周五（或最后交易日）
    all_dates = set()
    for k in hist.data.values():
        for r in k:
            d = r["date"]
            if d and len(d) == 10 and d[4] == "-" and d[7] == "-":
                all_dates.add(d)
    all_dates = sorted([d for d in all_dates if d and d >= bench_kline[0]["date"]])
    
    # 找每周五（或每周最后一个交易日）
    weekly_dates = []
    week_groups = defaultdict(list)
    for d in all_dates:
        try:
            dt = datetime.strptime(d, "%Y-%m-%d")
        except (ValueError, TypeError):
            continue
        week_key = dt.isocalendar()[0] * 100 + dt.isocalendar()[1]
        week_groups[week_key].append(d)
    
    for wk in sorted(week_groups.keys()):
        days = week_groups[wk]
        weekly_dates.append(days[-1])  # 每周最后一个交易日（周五或节前）
    
    # 过滤：至少需要在第一个调仓日之前有20个交易日的数据
    first_date = weekly_dates[0] if weekly_dates else None
    # 回测起点：跳过前60天（需要积累动量数据）
    weeks_to_skip = 3  # 至少3周数据积累
    
    if len(weekly_dates) <= weeks_to_skip:
        print(f"❌ 交易日太少: {len(weekly_dates)}")
        return []
    
    rebalance_dates = weekly_dates[weeks_to_skip:]
    print(f"  回测窗口: {rebalance_dates[0]} → {rebalance_dates[-1]} ({len(rebalance_dates)}周)", flush=True)
    
    # ── 逐周回放 ──
    trades = []
    equity_curve = [1.0]
    portfolio_returns = []
    
    for i in range(len(rebalance_dates) - 1):
        buy_date = rebalance_dates[i]
        sell_date = rebalance_dates[i+1]
        # 找到buy_date在K线中的索引
        bench_idx = None
        for bi, r in enumerate(bench_kline):
            if r.get("date") and r["date"] == buy_date:
                bench_idx = bi
                break
        if bench_idx is None or bench_idx < 20:
            continue
        
        # 计算各行业动量
        sector_mom = {}
        for sector, codes in sectors.items():
            mom_vals = []
            valid_codes = []
            for code in codes:
                k = hist.get(code)
                if not k:
                    continue
                # 找到buy_date在K线中的位置
                idx = None
                for j, r in enumerate(k):
                    if r.get("date") and r["date"] == buy_date:
                        idx = j
                        break
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
                sector_mom[sector] = {
                    "median": mom_vals[len(mom_vals)//2],
                    "count": len(mom_vals),
                    "codes": valid_codes,
                }
        
        if len(sector_mom) < 3:
            continue
        
        # Top3行业
        top3_sectors = sorted(sector_mom.items(), key=lambda x: x[1]["median"], reverse=True)[:3]
        
        # 选ETF：每个行业选流动性最好的3只
        selected = []
        for sector, data in top3_sectors:
            # 按成交量排序
            code_vol = []
            for code in data["codes"][:10]:  # 只看前10只
                k = hist.get(code)
                idx = next((j for j, r in enumerate(k) if r["date"] == buy_date), None)
                if idx:
                    vol = k[idx]["volume"] if idx < len(k) else 0
                    code_vol.append((code, vol))
            code_vol.sort(key=lambda x: x[1], reverse=True)
            for code, _ in code_vol[:3]:
                selected.append((code, sector))
        
        if len(selected) < 3:
            continue
        
        # 计算实际收益：从buy_date到sell_date
        actual_returns = []
        for code, sector in selected:
            k = hist.get(code)
            buy_idx = next((j for j, r in enumerate(k) if r.get("date") and r["date"] == buy_date), None)
            sell_idx = next((j for j, r in enumerate(k) if r.get("date") and r["date"] == sell_date), None)
            if buy_idx is not None and sell_idx is not None and buy_idx < sell_idx:
                b_price = k[buy_idx]["close"]
                s_price = k[sell_idx]["close"]
                if b_price > 0 and s_price > 0:
                    ret = (s_price / b_price - 1) * 100
                if not math.isnan(ret) and not math.isinf(ret):
                    actual_returns.append(ret)
        
        if len(actual_returns) < 3:
            continue
        
        avg_ret = statistics.mean(actual_returns)
        portfolio_returns.append(avg_ret)
        equity_curve.append(equity_curve[-1] * (1 + avg_ret / 100))
        
        # 基准收益
        bench_buy_idx = next((j for j, r in enumerate(bench_kline) if r.get("date") and r["date"] == buy_date), None)
        bench_sell_idx = next((j for j, r in enumerate(bench_kline) if r.get("date") and r["date"] == sell_date), None)
        bench_ret = 0
        if bench_buy_idx is not None and bench_sell_idx is not None:
            bp = bench_kline[bench_buy_idx]["close"]
            sp = bench_kline[bench_sell_idx]["close"]
            if bp > 0 and sp > 0:
                bench_ret = (sp / bp - 1) * 100
        
        trades.append({
            "buy_date": buy_date,
            "sell_date": sell_date,
            "top3_sectors": [s for s, _ in top3_sectors],
            "sector_momentum": {s: round(d["median"], 1) for s, d in top3_sectors},
            "holdings": selected[:9],
            "strategy_return_pct": round(avg_ret, 2),
            "benchmark_return_pct": round(bench_ret, 2),
            "excess_pct": round(avg_ret - bench_ret, 2),
            "cumulative_strategy": round(equity_curve[-1], 4),
        })
    
    return {
        "trades": trades,
        "equity_curve": [round(e, 4) for e in equity_curve],
        "portfolio_returns": [round(r, 2) for r in portfolio_returns],
        "n_trades": len(trades),
        "start_date": trades[0]["buy_date"] if trades else "",
        "end_date": trades[-1]["sell_date"] if trades else "",
    }

# ── 计算指标 ──────────────────────────────────────────────────────
def compute_metrics(result: dict):
    trades = result["trades"]
    if not trades:
        return {"error": "no trades"}
    
    n = len(trades)
    returns = [t["strategy_return_pct"] for t in trades]
    bench_returns = [t["benchmark_return_pct"] for t in trades]
    excess = [t["excess_pct"] for t in trades]
    
    # 总收益
    total_return = (result["equity_curve"][-1] - 1) * 100
    
    # 胜率
    wins = sum(1 for r in returns if r > 0)
    win_rate = wins / n * 100
    
    # 最大回撤
    peak = 1.0
    max_dd = 0.0
    for eq in result["equity_curve"]:
        if eq > peak:
            peak = eq
        dd = (eq - peak) / peak * 100
        max_dd = min(max_dd, dd)
    
    # 夏普比率（年化）
    std_r = statistics.stdev(returns) if len(returns) > 1 else 0.001
    mean_r = statistics.mean(returns)
    weekly_sharpe = (mean_r - 0.02 / 52) / std_r  # 周化，无风险2%
    sharpe = weekly_sharpe * math.sqrt(52)
    
    # 同期沪深300收益
    bench_total = 1.0
    for br in bench_returns:
        bench_total *= (1 + br / 100)
    bench_return = (bench_total - 1) * 100
    
    # 超额收益
    # 信息比率 (excess return / tracking error)
    mean_excess = statistics.mean(excess) if excess else 0
    std_excess = statistics.stdev(excess) if len(excess) > 1 else 0.001
    info_ratio = (mean_excess / std_excess) * math.sqrt(52) if std_excess > 0 else 0
    
    # 月度胜率
    monthly = defaultdict(list)
    for t in trades:
        month = t["buy_date"][:7]
        monthly[month].append(t["strategy_return_pct"])
    
    monthly_stats = {}
    for m, rets in sorted(monthly.items()):
        monthly_stats[m] = {
            "mean": round(statistics.mean(rets), 2),
            "win_rate": round(sum(1 for r in rets if r > 0) / len(rets) * 100, 1),
            "trades": len(rets),
        }
    
    # 按行业表现
    sector_returns = defaultdict(list)
    for t in trades:
        for s in t["top3_sectors"]:
            sector_returns[s].append(t["strategy_return_pct"])
    
    sector_stats = {}
    for s, rets in sorted(sector_returns.items(), key=lambda x: sum(x[1])/len(x[1]), reverse=True):
        sector_stats[s] = {
            "mean_return": round(statistics.mean(rets), 2),
            "win_rate": round(sum(1 for r in rets if r > 0) / len(rets) * 100, 1),
            "count": len(rets),
            "total_contribution": round(sum(rets), 2),
        }
    
    return {
        "period": f"{trades[0]['buy_date']} → {trades[-1]['sell_date']}",
        "total_weeks": n,
        "total_return_pct": round(total_return, 2),
        "annualized_return_pct": round(((1 + total_return/100) ** (52/n) - 1) * 100, 2) if n > 0 else 0,
        "benchmark_return_pct": round(bench_return, 2),
        "excess_return_pct": round(total_return - bench_return, 2),
        "win_rate_pct": round(win_rate, 1),
        "max_drawdown_pct": round(max_dd, 2),
        "sharpe_ratio": round(sharpe, 2),
        "info_ratio": round(info_ratio, 2),
        "best_week_pct": round(max(returns), 2) if returns else 0,
        "worst_week_pct": round(min(returns), 2) if returns else 0,
        "positive_weeks": wins,
        "negative_weeks": n - wins,
        "benchmark_win_rate": round(sum(1 for r in bench_returns if r > 0) / n * 100, 1),
        "monthly": monthly_stats,
        "top_sectors": sector_stats,
    }

def format_report(metrics: dict, result: dict):
    if "error" in metrics:
        return f"❌ {metrics['error']}"
    
    lines = [
        f"{'='*60}",
        f"📊 ETF 行业动量策略 · 真正历史回测报告",
        f"{'='*60}",
        f"",
        f"  回测期: {metrics['period']}  ({metrics['total_weeks']}周)",
        f"  策略: 每周按行业动量(Top3)等权买入",
        f"  基准: 沪深300 ETF (510300)",
        f"",
        f"  ┌─ {'':^48s} ─┐",
        f"  │ {'指标':20s} {'策略':>12s} {'基准':>12s} │",
        f"  ├─{'':─^50s}─┤",
    ]
    
    # Key metrics
    items = [
        ("总收益率", f"{metrics['total_return_pct']:+.1f}%", f"{metrics['benchmark_return_pct']:+.1f}%"),
        ("年化收益", f"{metrics['annualized_return_pct']:+.1f}%", "—"),
        ("胜率", f"{metrics['win_rate_pct']:.0f}%", f"{metrics['benchmark_win_rate']:.0f}%"),
        ("最大回撤", f"{metrics['max_drawdown_pct']:.1f}%", "—"),
        ("夏普比率", f"{metrics['sharpe_ratio']:.2f}", "—"),
        ("信息比率", f"{metrics['info_ratio']:.2f}", "—"),
        ("最佳周收益", f"{metrics['best_week_pct']:+.1f}%", "—"),
        ("最差周收益", f"{metrics['worst_week_pct']:+.1f}%", "—"),
    ]
    
    for label, val_s, val_b in items:
        lines.append(f"  │ {label:20s} {val_s:>12s} {val_b:>12s} │")
    
    lines.extend([
        f"  └─{'':─^50s}─┘",
        f"",
        f"  🎯 超额收益: {metrics['excess_return_pct']:+.1f}%",
        f"     胜率差异: {float(metrics['win_rate_pct']) - float(metrics['benchmark_win_rate']):+.0f}pp",
        f"",
        f"{'='*60}",
    ])
    
    # 月度表现
    if metrics.get("monthly"):
        lines.extend([
            f"📅 月度表现:",
            f"{'月份':10s} {'均收益':>8s} {'胜率':>6s} {'交易次数':>8s}",
            "-"*40,
        ])
        for m, s in metrics["monthly"].items():
            arrow = "🟢" if s["mean"] > 0 else "🔴"
            lines.append(f"  {arrow} {m:8s} {s['mean']:>+7.1f}% {s['win_rate']:>5.0f}% {s['trades']:>5d}次")
    
    # 最佳/最差行业
    if metrics.get("top_sectors"):
        sorted_sec = sorted(metrics["top_sectors"].items(), key=lambda x: x[1]["mean_return"], reverse=True)
        lines.extend([
            f"",
            f"{'='*60}",
            f"🏆 最佳行业贡献 (按均值收益排序):",
            f"{'行业':14s} {'均收益':>8s} {'胜率':>6s} {'总贡献':>8s} {'次数':>5s}",
            "-"*50,
        ])
        for s, st in sorted_sec[:8]:
            arrow = "🟢" if st["mean_return"] > 0 else "🔴"
            lines.append(f"  {arrow} {s:12s} {st['mean_return']:>+7.1f}% {st['win_rate']:>5.0f}% {st['total_contribution']:>+7.1f}% {st['count']:>3d}")
    
    # 最近5笔交易
    if result.get("trades"):
        lines.extend([
            f"",
            f"{'='*60}",
            f"📋 最近5笔交易:",
            f"{'日期':14s} {'Top3行业':30s} {'策略收益':>10s} {'基准收益':>10s}",
            "-"*70,
        ])
        for t in result["trades"][-5:]:
            sectors_str = "/".join(t["top3_sectors"][:2])
            lines.append(f"  {t['buy_date']} {sectors_str:30s} {t['strategy_return_pct']:>+8.2f}% {t['benchmark_return_pct']:>+8.2f}%")
    
    lines.extend([
        f"",
        f"{'='*60}",
        f"💡 解读:",
    ])
    
    if metrics["sharpe_ratio"] > 1.0:
        lines.append(f"  ✅ 夏普 > 1.0：策略有统计显著的超额收益")
    elif metrics["sharpe_ratio"] > 0.5:
        lines.append(f"  ✅ 夏普 > 0.5：策略收益为正")
    else:
        lines.append(f"  ⚠️ 夏普 < 0.5：策略收益不稳定")
    
    if metrics["excess_return_pct"] > 10:
        lines.append(f"  ✅ 超额收益 >10%：动量策略在回测期内有效")
    elif metrics["excess_return_pct"] > 0:
        lines.append(f"  ✅ 超额收益为正，策略有效")
    else:
        lines.append(f"  ⚠️ 超额为负，需优化策略")
    
    if metrics["max_drawdown_pct"] < -15:
        lines.append(f"  ⚠️ 最大回撤 >15%：需要加强风控")
    else:
        lines.append(f"  ✅ 回撤控制合理")
    
    lines.append(f"{'='*60}")
    return "\n".join(lines)

def run(hist_days=400, weekdays_only=True):
    print(f"\n{'='*60}")
    print(f"📊 ETF 行业动量策略 · 真正历史回测")
    print(f"{'='*60}")
    
    sectors, etfs = load_sector_etfs()
    n_etfs = sum(len(v) for v in sectors.values())
    print(f"  行业: {len(sectors)}个 | ETF池: {n_etfs}只 | 历史数据: {hist_days}天")
    
    hist = HistoryBuffer(max_days=hist_days)
    result = simulate_weekly_rebalance(sectors, etfs, hist)
    
    if not result or not result["trades"]:
        print("❌ 回测无法进行（数据不足）")
        return
    
    metrics = compute_metrics(result)
    report = format_report(metrics, result)
    print(report)
    
    # Save results
    out = {
        "metrics": metrics,
        "equity_curve": result["equity_curve"],
        "n_trades": result["n_trades"],
        "generated_at": datetime.now().isoformat(),
    }
    
    out_file = BASE / "data" / "momentum_backtest_v2.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    
    print(f"\n📝 回测结果已保存: {out_file}")
    
    # Summary one-liner
    lines = [
        f"\n📊 一句话总结:",
        f"  回测{metrics['total_weeks']}周 | 总收益 {metrics['total_return_pct']:+.1f}% (基准 {metrics['benchmark_return_pct']:+.1f}%)",
        f"  超额 {metrics['excess_return_pct']:+.1f}% | 夏普 {metrics['sharpe_ratio']:.2f} | 胜率 {metrics['win_rate_pct']:.0f}% | 最大回撤 {metrics['max_drawdown_pct']:.1f}%",
    ]
    print("\n".join(lines))
    
    return out

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=400, help="历史数据天数")
    parser.add_argument("--json", action="store_true", help="JSON输出")
    args = parser.parse_args()
    
    result = run(hist_days=args.days)
    if args.json and result:
        print(json.dumps(result, ensure_ascii=False, indent=2))
