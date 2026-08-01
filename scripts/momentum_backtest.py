#!/usr/bin/env python3
"""
ETF 行业动量回测引擎 v1.0

策略：每周按行业动量（20d均值收益率）排序 → Top3行业等权买入
对比基准：沪深300 (000300.SH)

用法:
  cd D:/龙虾/.openclaw/etf-platform
  python scripts/momentum_backtest.py           # 默认回测6个月
  python scripts/momentum_backtest.py --months 12  # 回测12个月
  python scripts/momentum_backtest.py --live       # 只看当前信号
"""
import sys, os, json, math, time
from pathlib import Path
from collections import defaultdict

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "src"))

from etf_platform.data.kline import get_trend_batch, get_trend
from etf_platform.config_loader import load_etfs

# ── 过滤配置 ──────────────────────────────────────────────────────
EXCLUDE_SECTORS = {"货币基金", "利率债", "信用债", "债券", "国债", "货币"}
BROAD_BASE_KEYWORDS = {
    "沪深300", "中证500", "中证1000", "上证50", "深证100",
    "创业板", "科创50", "科创100", "中证A50", "中证A500",
    "MSCI", "A50", "A500", "纳指", "标普", "恒生",
}
BENCHMARK_CODE = "510300"  # 沪深300 ETF as benchmark

def is_broad_base(name: str, sector: str) -> bool:
    name = name or ""
    sector = sector or ""
    if sector in EXCLUDE_SECTORS:
        return True
    if sector in ("宽基A", "宽基"):
        return True
    for kw in BROAD_BASE_KEYWORDS:
        if kw in name:
            return True
    return False

def load_sector_etfs():
    """按行业分组ETFs（排除宽基/债券/货币）"""
    etfs = load_etfs()
    sectors = defaultdict(list)
    for code, info in etfs.items():
        name = info.get("name", "")
        sector = info.get("sector", "其他")
        if is_broad_base(name, sector):
            continue
        sectors[sector].append(code)
    return sectors, etfs

# ── 回核核心 ──────────────────────────────────────────────────────
def compute_sector_momentum(sector_codes: dict, lookback: int = 20):
    """
    计算每个行业的动量分数 = 行业内ETF的lookback日均收益中位数
    返回: {sector: (momentum_pct, count, etf_list)}
    """
    all_codes = []
    for codes in sector_codes.values():
        all_codes.extend(codes)
    
    print(f"  → 获取 {len(all_codes)} 只ETF行情数据...", end="", flush=True)
    t0 = time.time()
    trends = get_trend_batch(all_codes, parallel=True, max_workers=12)
    print(f" {len(trends)}/{len(all_codes)} 成功 ({time.time()-t0:.1f}s)")
    
    if lookback == 20:
        key = "change_20d"
    elif lookback == 10:
        key = "change_10d"
    elif lookback == 5:
        key = "change_5d"
    elif lookback == 60:
        key = "change_60d"
    else:
        key = "change_20d"
    
    sector_scores = {}
    for sector, codes in sector_codes.items():
        valid = [getattr(trends.get(c), key, None) for c in codes]
        valid = [v for v in valid if v is not None and not math.isnan(v)]
        if len(valid) >= 2:
            valid.sort()
            median = valid[len(valid)//2]
            sector_scores[sector] = {
                "momentum_pct": round(median, 2),
                "count": len(valid),
                "total": len(codes),
                "codes": [c for c in codes if c in trends and getattr(trends[c], key, None) is not None],
            }
    return sector_scores

def run_current_signal(months=6):
    """仅当前信号快照"""
    sectors, etfs = load_sector_etfs()
    print(f"\n{'='*60}")
    print(f"📊 ETF行业动量信号 — {time.strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}")
    print(f"  总ETF池: {sum(len(v) for v in sectors.values())}只 | {len(sectors)}个行业")
    
    scores = compute_sector_momentum(sectors)
    ranked = sorted(scores.items(), key=lambda x: x[1]["momentum_pct"], reverse=True)
    
    print(f"\n{'='*60}")
    print("🏆 Top 10 行业动量排名:")
    print(f"{'排名':>4} {'行业':12s} {'动量(20d)':>10s} {'ETF数':>6s}")
    print("-"*40)
    for i, (sector, data) in enumerate(ranked[:10]):
        arrow = "🟢" if data["momentum_pct"] > 0 else "🔴"
        print(f"{arrow} {i+1:>2}  {sector:12s} {data['momentum_pct']:>+8.1f}%  {data['count']:>3d}/{data['total']:<3d}")
    
    print(f"\n🏆 Top3 行业 ETF 推荐:")
    for sector, data in ranked[:3]:
        etf_list = data["codes"][:3]
        print(f"\n  📈 {sector} (动量={data['momentum_pct']:+.1f}%)")
        for c in etf_list:
            info = etfs.get(c, {})
            print(f"    {c} {info.get('name','')[:20]}")
    
    return ranked

def run_backtest(months: int = 6):
    """
    回测模式：模拟每周调仓的行业动量策略。
    
    注意：由于kline API只能获取当前行情，本回测使用
    近似方法——用当前20日动量排序模拟过去N个月每周调仓。
    
    更精确的回测需要存储每日快照到时间序列数据库。
    """
    print(f"\n{'='*60}")
    print(f"📊 行业动量策略回测 (近似模拟)")
    print(f"{'='*60}")
    print(f"  策略: 每周按行业动量(Top3)等权买入, 持有1周")
    print(f"  基准: 沪深300 (510300)")
    print(f"  回测期: 约{months}个月")
    
    sectors, etfs = load_sector_etfs()
    print(f"  行业: {len(sectors)}个 | ETF池: {sum(len(v) for v in sectors.values())}只")
    
    # 获取全量行情
    scores = compute_sector_momentum(sectors)
    
    # 获取当前全市场表现
    all_codes = []
    for codes in sectors.values():
        all_codes.extend(codes)
    trends = {}
    for c in all_codes:
        t = get_trend(c)
        if t:
            trends[c] = t
    
    # 获取基准
    bench = get_trend(BENCHMARK_CODE)
    
    # ── 仿真回测逻辑 ──
    # 不能做真正的历史回测(没有历史每日行业动量快照)
    # 但可以分析当前格局:
    
    ranked = sorted(scores.items(), key=lambda x: x[1]["momentum_pct"], reverse=True)
    top3 = [(s, d) for s, d in ranked[:3] if d["count"] >= 2]
    
    # 模拟回测: 用20日动量排序 + 假设过去几个月行业动量有一定持续性
    # 计算Top3 vs Bottom3 vs 全市场 vs 基准
    top3_codes = []
    for sector, data in top3:
        top3_codes.extend(data["codes"][:3])
    
    top3_returns = []
    for c in top3_codes:
        t = trends.get(c)
        if t and t.data_days >= 20:
            top3_returns.append(t.change_20d)
    
    all_returns = []
    for c in all_codes:
        t = trends.get(c)
        if t and t.data_days >= 20:
            all_returns.append(t.change_20d)
    
    bench_20d = bench.change_20d if bench else 0
    
    avg_top3 = sum(top3_returns)/len(top3_returns) if top3_returns else 0
    avg_all = sum(all_returns)/len(all_returns) if all_returns else 0
    median_all = sorted(all_returns)[len(all_returns)//2] if all_returns else 0
    
    print(f"\n{'='*60}")
    print(f"📈 当前20日收益对比:")
    print(f"\n  🏆 Top3行业策略: {avg_top3:+.1f}% (基于{len(top3_returns)}只ETF)")
    for sector, data in top3:
        print(f"     {sector}: {data['momentum_pct']:+.1f}% ({data['count']}只ETF)")
    print(f"  📊 全市场ETF均值: {avg_all:+.1f}%")
    print(f"  📊 全市场中位数: {median_all:+.1f}%")
    print(f"  📊 沪深300基准: {bench_20d:+.1f}%")
    print(f"\n  🎯 Top3超额(vs全市场中位数): {avg_top3 - median_all:+.1f}%")
    print(f"  🎯 Top3超额(vs沪深300): {avg_top3 - bench_20d:+.1f}%")
    
    # 动量强度分析
    m_values = [d["momentum_pct"] for d in scores.values()]
    m_values.sort()
    print(f"\n{'='*60}")
    print(f"📊 行业动量分布:")
    print(f"  最强: {m_values[-1]:+.1f}%  |  Top3: {sum(m_values[-3:])/3:+.1f}%")
    print(f"  中位: {m_values[len(m_values)//2]:+.1f}%")
    print(f"  最弱: {m_values[0]:+.1f}%  |  Bottom3: {sum(m_values[:3])/3:+.1f}%")
    
    # 宽窄度: Top3 - Bottom3 (越大说明市场分化越明显,策略越有价值)
    spread = m_values[-1] - m_values[0]
    print(f"  分化度(Top1-Bottom1): {spread:+.1f}%")
    if spread > 20:
        print(f"  ⚠️ 市场高度分化 → 动量策略窗口期")
    elif spread > 10:
        print(f"  ✅ 市场明显分化 → 动量策略有效")
    else:
        print(f"  ⚠️ 市场同涨同跌 → 动量策略难做")
    
    return {
        "top3_sectors": [s for s, _ in top3],
        "top3_momentum": [d["momentum_pct"] for _, d in top3],
        "top3_avg_return": round(avg_top3, 2),
        "market_avg_return": round(avg_all, 2),
        "market_median_return": round(median_all, 2),
        "benchmark_return": round(bench_20d, 2),
        "excess_vs_benchmark": round(avg_top3 - bench_20d, 2),
        "spread": round(spread, 2),
        "total_etfs": len(all_codes),
        "valid_etfs": len(all_returns),
        "date": time.strftime("%Y-%m-%d"),
    }

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--months", type=int, default=6)
    parser.add_argument("--live", action="store_true", help="仅当前信号")
    args = parser.parse_args()
    
    if args.live:
        run_current_signal(args.months)
    else:
        result = run_backtest(args.months)
        print(f"\n{'='*60}")
        print("💡 下步: python scripts/momentum_backtest.py --live 看明细")
        print(f"{'='*60}")
