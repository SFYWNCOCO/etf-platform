#!/usr/bin/env python3
"""
etf_daily_patrol_wrapper.py — ETF 每日轻量巡检 cron 入口

设计原则：必须 <60s 跑完。
- Sina 全量 spot 实时行情（~1.5s）
- 每周 Top3（直接复用 weekly_top3.py --json，已验证 <3s）
- 沪深300 趋势过滤（由 weekly_top3 内部完成）
- 不跑 batch_full / analyst（那些 >60s，不适合 cron）

输出：Markdown 日报 → 飞书投递。
"""

import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parent
SRC = BASE / "src"
SCRIPTS = BASE.parent / "scripts"
for p in (SRC, SCRIPTS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


def _safe(value, decimals=2):
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.{decimals}f}"
    except Exception:
        return str(value)[:8]


def main():
    print(f"# 🦞 ETF 每日巡检快报")
    print(f"> {datetime.now().strftime('%Y-%m-%d %H:%M')} | 轻量模式(<60s)")
    print()

    # ==================== Sina 全量 spot ====================
    print("## 🟢 市场概览 (Sina 实时快照)")
    print()

    try:
        from finance_search import sina_etf_spot
        df = sina_etf_spot()
        total = len(df)

        pct_vals = []
        for v in df.get('涨跌幅', []):
            try:
                pct_vals.append(float(str(v).replace('%', '')))
            except Exception:
                pass

        up = sum(1 for v in pct_vals if v > 0)
        down = sum(1 for v in pct_vals if v < 0)
        flat = total - up - down

        if pct_vals:
            import numpy as np
            arr = np.array(pct_vals)
            best_idx = int(arr.argmax())
            worst_idx = int(arr.argmin())
            median_pct = float(np.median(arr))
            print(f"- 可投 ETF 总数: **{total}**")
            print(f"- 上涨 {up} / 下跌 {down} / 平盘 {flat} / 中位涨幅 **{median_pct:+.2f}%**")
            print(f"- 今日最强: {df.iloc[best_idx]['代码']} {df.iloc[best_idx]['名称']} ({df.iloc[best_idx]['涨跌幅']})")
            print(f"- 今日最弱: {df.iloc[worst_idx]['代码']} {df.iloc[worst_idx]['名称']} ({df.iloc[worst_idx]['涨跌幅']})")
        else:
            print(f"- 可投 ETF 总数: **{total}**，上涨 {up}，下跌 {down}，平盘 {flat}")
            print("- ⚠️ 涨跌幅解析失败，仍给出总量统计")

    except Exception as e:
        print(f"> ⚠️ Sina spot 失败: {type(e).__name__}: {str(e)[:140]}")

    print()

    # ==================== Top3 推荐（直接复用 weekly_top3.py --json）====================
    print("## 🏆 本周 Top 3 推荐")
    print()

    try:
        weekly = BASE / "weekly_top3.py"
        proc = subprocess.run(
            [sys.executable, str(weekly), "--json"],
            cwd=str(BASE),
            capture_output=True, text=True, timeout=120,
        )
        if proc.returncode == 0:
            out = proc.stdout or ""
            # weekly_top3.py prints progress lines (📡/📰) before the JSON payload.
            # Locate the first '{' to strip human-readable prefix noise.
            json_start = out.find("{")
            if json_start < 0:
                raise ValueError("weekly_top3 stdout contains no JSON object")
            data = json.loads(out[json_start:].strip())

            # Extract regime summary from status_text
            print(f"- 市场状态: **{data.get('status_label', data.get('market_state', '?'))}**")
            print(f"- 建议仓位: **{data.get('position_suggestion', data.get('current_position', '?'))}**")
            print()
            print("| Rank | 板块 | ETF | 名称 | 20d动量 | 成交额 |")
            print("|------|------|-----|------|---------|--------|")
            for rec in data.get('recommendations', [])[:3]:
                sector = rec.get('sector', '?')
                code = rec.get('code', '?')
                name = rec.get('name', '?')
                momentum = rec.get('momentum_20d', 0)
                volume = rec.get('volume', 0)
                vol_m = f"{int(volume)/1e6:.1f}M" if isinstance(volume, (int,float)) and volume >= 1e6 else str(volume)
                print(f"| {rec.get('rank','?')} | {sector} | {code} | {name} | {float(momentum):.2f}% | {vol_m} |")

            for rec in data.get('recommendations', [])[:3]:
                ds = rec.get('data_sources') or {}
                if not isinstance(ds, dict):
                    continue
                if not any(ds.get(k) for k in ("kline_as_of", "quote_source", "quote_as_of", "news_status")):
                    continue
                k = ds.get("kline_as_of") or "N/A"
                q = ds.get("quote_source") or "N/A"
                n = ds.get("news_status") or "N/A"
                print(f"- **{rec.get('name', rec.get('code', '?'))}** 溯源: K线<{k}> | 行情<{q}> | 新闻<{n}>")

            top_sectors = data.get("momentum_top3_sectors", data.get("top_sectors", []))
            if top_sectors:
                print()
                print("| 热门板块 | 中位动量 | 新闻情绪 | ETF数 |")
                print("|----------|----------|----------|-------|")
                for s in top_sectors[:5]:
                    sec = s.get('mega_sector', s.get('sector', '?'))
                    mom = s.get('median_momentum', s.get('momentum_20d_pct', 0))
                    sent = s.get('news_sentiment', '?')
                    cnt = s.get('etf_count', '?')
                    try:
                        mom_s = f"{float(mom):.2f}%"
                    except Exception:
                        mom_s = str(mom)
                    print(f"| {sec} | {mom_s} | {sent} | {cnt} |")
        else:
            err = (proc.stderr or proc.stdout).strip()[-300:]
            print(f"> ⚠️ weekly_top3 失败(exit={proc.returncode}): {err}")

    except Exception as e:
        print(f"> ⚠️ Top3 计算失败: {type(e).__name__}: {str(e)[:140]}")
        print("> 跳过推荐模块（不影响市场概览数据）")

    print()
    print("## ⚠️ 风险提示")
    print("- 数据来源: Sina 实时行情 + 20日动量排名")
    print("- 轻量巡检不包含深层 KB 穿透；需要完整分析请手动运行 `python weekly_top3.py`")
    print("- 本报告基于量化模型，不构成投资建议")
    print()
    print("---")
    print("* 报告生成时间目标: <60s *")


if __name__ == "__main__":
    main()
