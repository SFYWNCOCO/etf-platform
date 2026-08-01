#!/usr/bin/env python3
"""
ETF 早晨综合检查 — 合并穿透巡检 + 心跳监控
替代两个独立的 cron 任务：ETF每日穿透巡检 + ETF心跳监控

功能：
1. 29层穿透扫描 (均衡配置 Top 10)
2. 行业ETF异常波动监控 (同 etf_monitor.py 逻辑)

输出：Markdown 格式报告，直接 stdout
"""

import sys
import os
from datetime import datetime
from pathlib import Path

# ==================== 路径设置 ====================
BASE = Path(r"D:\龙虾\.openclaw")
SRC = BASE / "etf-platform" / "src" / "etf_platform"
DATA_DIR = BASE / "data" / "etf-platform"
DATA_DIR.mkdir(exist_ok=True)

sys.path.insert(0, str(BASE))
sys.path.insert(0, str(SRC))

# ==================== 功能 1: ETF 穿透巡检 ====================
def run_patrol_scan():
    """运行29层穿透扫描，返回Top 10投资类ETF结果"""
    from etf_platform.pipeline import batch_full
    from etf_platform.config_loader import load_etfs
    
    NOW = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    print(f"# 🦞 ETF 早晨综合检查报告")
    print(f"> {NOW} | 29层穿透管线 + 行业波动监控")
    print()
    
    # Run full scan
    results = batch_full(limit=600, sort_by="score", profile="均衡", live=True)
    etfs = load_etfs()
    
    non_invest = {"货币基金", "货币", "利率债", "信用债", "债券", "国债"}
    invest_results = [r for r in results if r.get("sector", "") not in non_invest]
    
    print(f"## 🟢 均衡配置 Top 10")
    print(f"> 扫描{len(results)}只ETF, 过滤后{len(invest_results)}只投资类")
    print()
    print("| # | 代码 | 名称 | 行业 | 综合分 | L21行为 | L23估值 | L8资金 |")
    print("|---|------|------|------|--------|---------|---------|--------|")
    
    def fmt(v):
        if v is None: return "N/A"
        try: return f"{float(v):.1f}"
        except Exception: return str(v)[:4]
    
    for i, r in enumerate(invest_results[:10]):
        ls = r.get("layer_scores", {})
        code = r.get("etf_code", "?")
        name = r.get("name", "?")
        sector = r.get("sector", "?")
        comp = r.get("composite_score", r.get("composite", r.get("score", "?")))
        l21 = ls.get("L21_Behavior", "N/A")
        l23 = ls.get("L23_Valuation", "N/A")
        l8 = ls.get("L8_CapitalFlow", "N/A")
        
        print(f"| {i+1} | {code} | {name} | {sector} | {fmt(comp)} | {fmt(l21)} | {fmt(l23)} | {fmt(l8)} |")
    
    print()
    print(f"## ⚠️ 风险提示")
    print("- 数据来源: Sina实时行情+KB信号 (live=True)")
    print("- 评分区间: 1-10 (10=最强)")
    print("- 本报告基于量化模型，不构成投资建议")
    
    return invest_results[:10]


# ==================== 功能 2: 心跳监控 ====================
def run_heartbeat_check():
    """监控行业ETF异常波动，类似 etf_monitor.py 逻辑"""
    WATCH = [
        ("159995", "芯片ETF"),
        ("515790", "光伏ETF"), 
        ("512480", "半导体ETF"),
        ("510050", "上证50ETF"),
        ("513500", "标普500ETF"),
        ("512010", "医药ETF"),
    ]
    
    STATE_FILE = DATA_DIR / "etf_morning_state.json"
    
    # 加载状态
    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            state = json.load(f)
    except:
        state = {}
    
    alerts = []
    
    try:
        from etf_platform.analyst import analyse
        from etf_platform.data import get_price
        
        for code, name in WATCH:
            try:
                price, src = get_price(code)
                result = analyse(code, profile="balanced", live=True)
                score = result.get("composite_score", 0)
                layers = result.get("layer_scores", {})
                l9 = layers.get("L9_Signals", 0)
                l8 = layers.get("L8_CapitalFlow", 0)
                
                prev = state.get(code, {})
                ps = prev.get("score", 0)
                delta = score - ps if ps else 0
                
                if abs(delta) >= 0.3 or not ps:
                    d = "↑" if delta > 0 else ("↓" if delta < 0 else "→")
                    alerts.append(f"{name}: {price.price:.2f} ({price.change_pct:+.2f}% 综合{score:.2f} {d}{abs(delta):.2f} L8={l8:.1f} L9={l9:.1f})")
                
                state[code] = {"score": score, "price": price.price, "change_pct": price.change_pct, "l8": l8, "l9": l9}
            except Exception as e:
                alerts.append(f"{name} 检查错误: {str(e)[:40]}")
        
        # 保存状态
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        
    except ImportError:
        alerts.append("⚠️ 无法导入监控模块，跳过心跳检查")
    
    print(f"## 🔔 行业ETF波动监控")
    if alerts:
        print(f"> {len(alerts)} 项预警:")
        for a in alerts:
            print(f"  • {a}")
    else:
        print("> 无显著波动")
    print()
    
    return alerts


if __name__ == "__main__":
    import json
    
    print("=" * 60)
    print(f"ETF Morning Check - {(datetime.now().strftime('%Y-%m-%d %H:%M'))}")
    print("=" * 60)
    print()
    
    # 运行穿透巡检
    print("--- 第一部分：穿透巡检 ---\n")
    patrol_results = run_patrol_scan()
    
    # 运行心跳监控
    print("--- 第二部分：心跳监控 ---\n")
    heartbeat_alerts = run_heartbeat_check()
    
    print("\n" + "=" * 60)
    print("检查完成")
    print("=" * 60)
