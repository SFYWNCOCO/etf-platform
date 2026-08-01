#!/usr/bin/env python3
"""
portfolio_comparison_backtest.py — Three-framework portfolio allocation comparison on A-share ETFs.

Usage:
    cd etf-platform && PYTHONPATH=src python scripts/portfolio_comparison_backtest.py

Pipeline:
    1. Load 592 ETF universe from config/etfs.yaml
    2. Filter out broad-base/bond/money/QDII/leverage; group by mega-sector
    3. Select top-liquid 3 ETFs per sector (or fewer if not available)
    4. Fetch 1-year daily klines via akshare.fund_etf_hist_sina (no proxy needed)
    5. Build annualized covariance + trailing 60d expected returns
    6. Run three allocation strategies:
        a. MPT tangency (long-only, bounded)
        b. Risk parity (ERC, exact Maillard solution)
        c. Black-Litterman (market equilibrium + sector views)
    7. Rolling monthly rebalance backtest (60-day window)
    8. Compare against CSI 300 benchmark (510300)

Outputs:
    - Console report
    - reports/portfolio_three_framework_bt.json
    - Per-strategy weights snapshot

Evidence labels:
    [calibration] = real execution with actual akshare data
    [inference]   = theory-based expectation, not yet empirically validated

"""
from __future__ import annotations

import sys
import os
import json
import argparse
import warnings
from pathlib import Path
from datetime import datetime
from collections import defaultdict

import numpy as np
import pandas as pd
import yaml

warnings.filterwarnings('ignore')

_HERE = Path(__file__).resolve().parents[1]
_SRC = _HERE / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Clear proxies so akshare/Sina works even when Clash proxy is dead
for k in list(os.environ.keys()):
    if k.endswith('_PROXY') or k.lower().endswith('_proxy'):
        del os.environ[k]

BENCHMARK_CODE = "510300"  # CSI 300 ETF
HISTORY_START = "20250701"
HISTORY_END = "20260728"
REBAL_DAYS = 20
WINDOW_DAYS = 60

EXCLUDE_SECTORS = {"货币基金", "利率债", "信用债", "债券", "国债", "货币", "宽基A", "宽基"}
BROAD_BASE_KEYWORDS = {
    "沪深300", "中证500", "中证1000", "上证50", "深证100",
    "创业板", "科创50", "科创100", "中证A50", "中证A500",
    "MSCI", "A50", "A500", "纳指", "标普", "恒生",
}

SECTOR_ORDER = ["科技", "新能源", "消费", "金融", "医药", "周期", "军工", "跨境", "红利价值", "基建"]
SECTOR_TO_MEGA = {
    "金融": "金融", "银行": "金融", "保险": "金融", "券商": "金融",
    "AI/科技": "科技", "半导体": "科技", "芯片": "科技", "软件": "科技",
    "通信/5G": "科技", "计算机": "科技", "电子": "科技", "机器人": "科技",
    "医药": "医药", "医疗": "医药", "创新药": "医药", "医疗器械": "医药",
    "中药": "医药", "生物医药": "医药",
    "新能源": "新能源", "光伏": "新能源", "风电": "新能源", "储能": "新能源",
    "锂电": "新能源", "电池": "新能源", "新能源车": "新能源",
    "消费": "消费", "白酒": "消费", "食品饮料": "消费", "家电": "消费",
    "汽车": "消费", "旅游": "消费", "传媒": "消费", "游戏": "消费",
    "军工": "军工", "国防": "军工", "航空航天": "军工",
    "周期/资源": "周期", "有色": "周期", "钢铁": "周期", "煤炭": "周期",
    "化工": "周期", "石油": "周期", "原油": "周期", "黄金": "周期",
    "基建": "基建", "地产": "基建", "电力": "基建", "公用事业": "基建",
    "红利/价值": "红利价值", "港股": "跨境", "跨境": "跨境",
    "纳指": "跨境", "标普": "跨境", "恒生": "跨境", "中概": "跨境", "互联网": "跨境",
    "现金流": "红利价值",
}

SECTOR_VIEW_Q = {"科技": +0.03, "新能源": -0.02, "周期": -0.01, "红利价值": +0.015, "消费": +0.01}


def is_excluded(name: str, sector: str, info: dict) -> bool:
    if sector in EXCLUDE_SECTORS:
        return True
    if any(kw in name for kw in BROAD_BASE_KEYWORDS):
        return True
    if info.get("leverage", 1) != 1:
        return True
    if info.get("access") == "fake":
        return True
    return False


def load_universe(n_per_sector: int = 3) -> tuple[list[str], dict[str, list[dict]]]:
    """Load etfs.yaml, filter, sample n_per_sector from each mega-sector sorted by risk_level ascending."""
    etf_cfg_path = _HERE / "config" / "etfs.yaml"
    with open(etf_cfg_path, encoding='utf-8') as f:
        cfg = yaml.safe_load(f)['etfs']

    groups = defaultdict(list)
    n_raw = len(cfg)
    n_sector = 0
    for key, info in cfg.items():
        code = str(info.get("code", key))
        name = info.get("name", "")
        sector = info.get("sector", "其他")
        if len(code) != 6 or not code.isdigit():
            continue
        if is_excluded(name, sector, info):
            continue
        mega = SECTOR_TO_MEGA.get(sector, "其他")
        n_sector += 1
        groups[mega].append({
            "code": code, "name": name, "sector": sector,
            "risk_level": float(info.get("risk_level", 0.5)),
        })

    selected = []
    for mega in SECTOR_ORDER:
        pool = sorted(groups.get(mega, []), key=lambda x: x['risk_level'])[:n_per_sector]
        selected.extend(pool)

    print(f"[calibration] Universe loaded: {n_raw} raw → {n_sector} eligible → {len(selected)} sampled across {sum(1 for v in groups.values() if v)} sectors")
    if selected:
        for item in selected:
            print(f"  - {item['code']} {item['name']} ({item['sector']})")

    codes = [item["code"] for item in selected]
    return codes, {item["code"]: item for item in selected}, groups


def fetch_one(code: str) -> pd.DataFrame | None:
    """Fetch single ETF history via akshare Sina interface. Handles both zh/en column names."""
    import akshare as ak
    prefix = "sh" if code.startswith(("5", "6")) else "sz"
    try:
        df = ak.fund_etf_hist_sina(symbol=f"{prefix}{code}")
        if df is None or df.empty:
            return None
        df = df.copy()

        # akshare may return either Chinese column names (date, open, close...)
        # or English column names (date, prevclose, open, high, low, close, volume...).
        rename_map = {
            "日期": "date", "开盘": "open", "最高": "high",
            "最低": "low", "收盘": "close", "成交量": "volume",
            "成交额": "amount", "涨跌幅": "pct_change", "涨跌额": "change",
            "换手率": "turnover", "振幅": "amplitude", "prevclose": "prev_close",
            "postVol": "post_volume", "postAmt": "post_amount",
        }
        df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns}, inplace=True)

        if "date" not in df.columns:
            print(f"  ⚠️ fetch {code}: missing 'date' column; actual cols={list(df.columns)[:10]}")
            return None
        if "close" not in df.columns:
            # try to find the closest match (case-insensitive)
            close_col = next((c for c in df.columns if c.lower() in {"close", "收盘价"}), None)
            if close_col is None:
                print(f"  ⚠️ fetch {code}: no close column; actual cols={list(df.columns)}")
                return None
            df.rename(columns={close_col: "close"}, inplace=True)

        df["date"] = pd.to_datetime(df["date"])

        # Normalize start/end for robust comparison
        _start = pd.to_datetime(HISTORY_START.replace("-", "")) if "-" not in HISTORY_START else pd.to_datetime(HISTORY_START)
        _end = pd.to_datetime(HISTORY_END.replace("-", "")) if "-" not in HISTORY_END else pd.to_datetime(HISTORY_END)

        df = df.sort_values("date").reset_index(drop=True)
        df = df[(df["date"] >= _start) & (df["date"] <= _end)]
        if df.empty:
            return None

        out_cols = ["date", "close"]
        for candidate in ["volume", "amount"]:
            if candidate in df.columns:
                out_cols.append(candidate)
        return df[out_cols]
    except Exception as e:
        print(f"  ⚠️ fetch {code}: FAIL {type(e).__name__}: {str(e)[:240]}")
        return None


def fetch_klines(codes: list[str]) -> dict[str, pd.DataFrame]:
    all_df = {}
    failed = []
    print(f"\n--- Fetching {len(codes)} ETF klines (akshare Sina) ---")
    for i, code in enumerate(codes, 1):
        d = fetch_one(code)
        if d is None:
            failed.append(code)
            continue
        all_df[code] = d
        if i % 10 == 0 or i == len(codes):
            print(f"  [{i}/{len(codes)}]")

    print(f"[calibration] Kline fetch: success={len(all_df)}, failed={len(failed)}")
    if failed:
        print(f"  failures: {failed[:5]}{'...' if len(failed) > 5 else ''}")
    return all_df


def build_returns_panel(hist: dict[str, pd.DataFrame]):
    """Align klines into panel, compute daily close-to-close returns. Returns (panel, daily_rets)."""
    frames = []
    for code, df in hist.items():
        s = df.set_index("date")["close"].astype(float).sort_index()
        s.name = code
        frames.append(s)
    panel = pd.concat(frames, axis=1).dropna(how="all").sort_index()
    daily_rets = panel.pct_change().dropna()
    return panel, daily_rets


def annualized_cov(daily_rets: pd.DataFrame) -> np.ndarray:
    return daily_rets.cov().to_numpy() * 252


def mpt_tangency(mu: np.ndarray, cov: np.ndarray, w_min: float = 0.0, w_max: float = 0.25) -> np.ndarray:
    """Long-only MPT tangency with box constraints.  Uses inverse-variance clipping."""
    eigvals = np.linalg.eigvalsh(cov)
    eig_min = float(eigvals.min())
    if eig_min < 1e-8:
        cov = cov + (abs(eig_min) + 1e-8) * np.eye(cov.shape[0])
    raw = np.linalg.solve(cov, mu)
    raw -= raw.min() if raw.min() < 0 else 0
    raw = np.clip(raw, w_min, w_max)
    s = raw.sum()
    return raw / s if s > 0 else np.full_like(raw, 1.0 / len(raw))


def allocate_mpt(daily_rets: pd.DataFrame) -> tuple[np.ndarray, dict]:
    mu = daily_rets.mean().to_numpy() * 252
    cov = annualized_cov(daily_rets)
    w = mpt_tangency(mu, cov)
    port_ret = float(mu @ w)
    port_vol = float(np.sqrt(w @ cov @ w))
    sharpe = port_ret / port_vol if port_vol > 0 else 0.0
    hhi = float((w ** 2).sum())
    return w, {
        "method": "MPT",
        "portfolio_return_annual": port_ret,
        "portfolio_vol_annual": port_vol,
        "sharpe_annualized": sharpe,
        "hhi": hhi,
        "nonzero_weights": int((w > 0.005).sum()),
    }


def allocate_risk_parity(daily_rets: pd.DataFrame) -> tuple[np.ndarray, dict]:
    from etf_platform.portfolio.risk_parity import risk_parity
    cov = annualized_cov(daily_rets)
    rp = risk_parity(cov)
    return rp.weights, {
        "method": "Risk Parity",
        "portfolio_vol_raw": rp.portfolio_vol,
        "concentration_hhi": rp.concentration_hhi,
        "converged": rp.converged,
        "n_iter": rp.n_iter,
        "rc_range": [float(rp.risk_contributions.min()), float(rp.risk_contributions.max())],
        "nonzero_weights": int((rp.weights > 0.005).sum()),
    }


def allocate_black_litterman(daily_rets: pd.DataFrame, selected_info: dict) -> tuple[np.ndarray, dict]:
    """Black-Litterman with sector-level relative/absolute views."""
    from etf_platform.portfolio.black_litterman import black_litterman
    codes = list(selected_info.keys())
    cov = annualized_cov(daily_rets)

    # P: one row per sector view, distributed equally over ETFs in that sector
    P_rows = []
    Q_vals = []
    sector_to_cols = defaultdict(list)
    for idx, code in enumerate(codes):
        info = selected_info[code]
        sector = SECTOR_TO_MEGA.get(info.get("sector", "其他"), "其他")
        sector_to_cols[sector].append(idx)

    for sector, q in SECTOR_VIEW_Q.items():
        cols = sector_to_cols.get(sector, [])
        if not cols:
            continue
        row = np.zeros(len(codes))
        for c in cols:
            row[c] = 1.0 / len(cols)
        P_rows.append(row)
        Q_vals.append(q)

    if not P_rows:
        # fallback: uniform weights
        return np.ones(len(codes)) / len(codes), {
            "method": "BL (fallback)",
            "views_applied": 0,
            "drift_norm": 0.0,
            "nonzero_weights": int(((np.ones(len(codes)) / len(codes)) > 0.005).sum()),
        }

    P = np.array(P_rows)
    Q = np.array(Q_vals)
    w_mkt = np.ones(len(codes)) / len(codes)

    bl = black_litterman(
        cov=cov, w_mkt=w_mkt, P=P, Q=Q, tau=0.05,
        risk_aversion=2.5, w_min=0.0, w_max=0.35,
    )

    return bl.mpt_weights, {
        "method": "Black-Litterman",
        "views_applied": bl.views_applied,
        "tau": bl.diagnostics["tau"],
        "max_abs_view_drift": bl.diagnostics["max_abs_view_drift"],
        "drift_norm": bl.diagnostics["drift_norm"],
        "posterior_mu_range": bl.diagnostics["posterior_mu_range"],
        "concentration_hhi": float((bl.mpt_weights ** 2).sum()),
        "nonzero_weights": int((bl.mpt_weights > 0.005).sum()),
    }


def backtest_rolling(
    daily_rets: pd.DataFrame,
    allocators: dict[str, callable],
    rebal_days: int = REBAL_DAYS,
    window: int = WINDOW_DAYS,
) -> dict[str, dict]:
    """Rolling monthly rebalance. Each allocator receives a trailing `window` days of daily returns."""
    results = {}
    dates = daily_rets.index
    n_dates = len(dates)

    for name, allocator in allocators.items():
        pnl = np.zeros(n_dates)
        current_w = None
        last_rebal = -rebal_days

        for t in range(n_dates):
            # Rebalance every `rebal_days` trading days
            if t == 0 or t - last_rebal >= rebal_days:
                sub = daily_rets.iloc[max(0, t - window):t] if t > 0 else daily_rets
                if len(sub) < 10:
                    sub = daily_rets
                try:
                    current_w, meta = allocator(sub)
                except Exception as e:
                    print(f"  ⚠️ [{name}] allocation @t={t}: FAIL {type(e).__name__}: {e}")
                    continue
                last_rebal = t

            if current_w is None or len(current_w) != len(daily_rets.columns):
                continue

            port_ret = float(current_w @ daily_rets.iloc[t].to_numpy())
            if t == 0:
                pnl[t] = 1.0 + port_ret
            else:
                pnl[t] = pnl[t - 1] * (1.0 + port_ret)

        nav_s = pd.Series(pnl, index=dates[:len(pnl)])
        total_rets = nav_s.pct_change().dropna()

        cumulative = float(nav_s.iloc[-1] / nav_s.iloc[0] - 1) if not nav_s.empty else 0.0
        sharpe = float(total_rets.mean() / total_rets.std() * np.sqrt(252)) if total_rets.std() > 0 else 0.0
        downside = total_rets[total_rets < 0]
        sortino = float(total_rets.mean() / downside.std() * np.sqrt(252)) if len(downside) > 0 and downside.std() > 0 else 0.0
        max_dd = float(((nav_s / nav_s.cummax()) - 1).min()) if not nav_s.empty else 0.0

        results[name] = {
            "cumulative_return": cumulative,
            "annualized_sharpe": sharpe,
            "sortino": sortino,
            "max_drawdown": max_dd,
            "final_nav": float(nav_s.iloc[-1]) if not nav_s.empty else 0.0,
            "rebalance_events": int(last_rebal // rebal_days) if last_rebal >= 0 else 0,
        }

    return results


def benchmark_csi300(hist: dict[str, pd.DataFrame]) -> dict:
    """Use 510300 as CSI 300 benchmark."""
    bench = hist.get(BENCHMARK_CODE)
    if bench is None or bench.empty:
        return {}
    s = bench.set_index("date")["close"].astype(float).pct_change().dropna()
    nav = (1 + s).cumprod()
    cumulative = float(nav.iloc[-1] / nav.iloc[0] - 1)
    sharpe = float(s.mean() / s.std() * np.sqrt(252)) if s.std() > 0 else 0.0
    max_dd = float(((nav / nav.cummax()) - 1).min())
    return {
        "cumulative_return": cumulative,
        "annualized_sharpe": sharpe,
        "max_drawdown": max_dd,
        "trading_days": len(nav),
    }


def main():
    parser = argparse.ArgumentParser(description="Three-framework portfolio backtest.")
    parser.add_argument("--n-per-sector", type=int, default=3, help="ETFs per mega-sector")
    parser.add_argument("--start", default=HISTORY_START)
    parser.add_argument("--end", default=HISTORY_END)
    args = parser.parse_args()

    print("=" * 72)
    print(f"PORTFOLIO THREE-FRAMEWORK BACKTEST  |  {datetime.now():%Y-%m-%d %H:%M}")
    print("=" * 72)

    # 1. Load universe
    print("\n[1/6] Loading ETF universe...")
    codes, selected_info, groups = load_universe(args.n_per_sector)

    # 2. Fetch benchmark
    print(f"\n[2/6] Fetching CSI 300 benchmark: {BENCHMARK_CODE}...")
    all_hist = {}
    bench_df = fetch_one(BENCHMARK_CODE)
    if bench_df is not None:
        all_hist[BENCHMARK_CODE] = bench_df
        print(f"  ✓ {BENCHMARK_CODE}: rows={len(bench_df)}")
    else:
        print("  ✗ benchmark unavailable")

    # 3. Fetch selected ETFs
    print("\n[3/6] Fetching selected ETF klines...")
    selected_hist = fetch_klines(codes)
    all_hist.update(selected_hist)

    valid_codes = [c for c in codes if c in selected_hist]
    if len(valid_codes) < 10:
        raise SystemExit(f"ERROR: only {len(valid_codes)} valid ETF klines; need ≥10")

    # 4. Build returns panel
    print("\n[4/6] Building aligned returns panel...")
    panel, daily_rets = build_returns_panel(selected_hist)
    common_codes = list(daily_rets.columns)
    n = len(common_codes)
    print(f"  Panel shape: {daily_rets.shape} (trading days × ETFs)")
    print(f"  Common dates: {daily_rets.index[0].date()} → {daily_rets.index[-1].date()}")

    # 5. Allocations on full sample
    print("\n[5/6] Computing allocation snapshots...")
    allocators = {
        "MPT": allocate_mpt,
        "Risk_Parity": allocate_risk_parity,
        "Black_Litterman": lambda dr: allocate_black_litterman(dr, selected_info),
    }

    snapshot = {}
    for name, allocator in allocators.items():
        try:
            w, meta = allocator(daily_rets)
            snapshot[name] = {
                "weights": dict(zip(common_codes, [round(float(x), 5) for x in w])),
                "meta": meta,
            }
            top_idx = np.argsort(w)[-min(5, n):][::-1]
            print(f"\n[{name}]  sum={w.sum():.4f}  HHI={float(meta.get('concentration_hhi', meta.get('hhi', -1))):.4f}")
            print("  top5:")
            for i in top_idx:
                print(f"    {common_codes[i]:>6}  {w[i]:7.3%}")
        except Exception as e:
            print(f"\n[{name}] ALLOCATION FAIL: {type(e).__name__}: {e}")

    # 6. Backtest
    print("\n[6/6] Running rolling rebalance backtest...")
    bt_results = backtest_rolling(daily_rets, allocators, rebal_days=args.n_per_sector * 6)

    # Benchmark
    bench_metrics = benchmark_csi300(all_hist)

    print("\n" + "=" * 72)
    print("BACKTEST RESULTS")
    print("=" * 72)
    table_header = f"{'Strategy':<22} {'Cum Ret':>10} {'Sharpe':>8} {'Sortino':>8} {'MaxDD':>8} {'Final NAV':>10}"
    print(table_header)
    print("-" * len(table_header))

    def fmt_pct(x): return f"{x:>9.2%}"
    def fmt_num(x): return f"{x:>7.3f}"
    def fmt_nav(x): return f"{x:>10.4f}"

    for name, metrics in bt_results.items():
        row = f"{name:<22} {fmt_pct(metrics['cumulative_return'])} {fmt_num(metrics['annualized_sharpe'])} {fmt_num(metrics['sortino'])} {fmt_pct(metrics['max_drawdown'])} {fmt_nav(metrics['final_nav'])}"
        print(row)

    if bench_metrics:
        bm = bench_metrics
        row = f"{'CSI300 510300':<22} {fmt_pct(bm['cumulative_return'])} {fmt_num(bm['annualized_sharpe'])} {'N/A':>8} {fmt_pct(bm['max_drawdown'])} {fmt_nav(bm['cumulative_return']+1)}"
        print(row)

    # Save JSON report
    report = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "universe": {
            "raw_count": len(selected_info),
            "valid_codes": valid_codes,
            "bench_code": BENCHMARK_CODE,
        },
        "allocations": snapshot,
        "backtest": bt_results,
        "benchmark": bench_metrics,
        "settings": {
            "history_start": args.start,
            "history_end": args.end,
            "rebalance_window_days": WINDOW_DAYS,
            "rebalance_frequency_days": args.n_per_sector * 6,
            "covariance_method": "sample_daily_returns * 252",
            "mu_method_for_mpt": "mean_daily_returns * 252",
        },
    }
    report_dir = _HERE / "reports"
    report_dir.mkdir(exist_ok=True)
    report_path = report_dir / "portfolio_three_framework_bt.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n[delivery] Report saved: {report_path}")

    # Negative canary: intentionally bad strategy should be reported separately
    def inverse_rp(dr):
        w, meta = allocate_risk_parity(dr)
        return -w, {**meta, "method": "Inverse_RP_canary"}

    bad_result = backtest_rolling(
        daily_rets,
        {"Inverse_RP_canary": inverse_rp},
        rebal_days=20,
        window=60,
    )
    print("\n--- Negative Canary ---")
    for k, v in bad_result.items():
        print(f"  {k}: cum_ret={v['cumulative_return']:.4f}, max_dd={v['max_drawdown']:.4f}")
    assert bad_result["Inverse_RP_canary"]["max_drawdown"] < -0.05, \
        f"Negative canary did NOT lose money? max_dd={bad_result['Inverse_RP_canary']['max_dd']}"

    # Hard-fail canary
    assert len(valid_codes) >= 10, f"Need ≥10 valid ETFs, got {len(valid_codes)}"
    assert set(bt_results.keys()) == {"MPT", "Risk_Parity", "Black_Litterman"}, \
        f"Backtest missing methods: {bt_results.keys()}"

    print("\n[calibration] CANARY PASS: real ETF data, 3 methods, negative control, hard assertions OK")
    return report


if __name__ == "__main__":
    main()
