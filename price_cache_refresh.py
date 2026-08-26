#!/usr/bin/env python3
"""price_cache_refresh.py — 每日刷新 price_cache.json（收盘后 cron 入口）.

问题根因：price_cache.py 的 refresh_all() 逐只 get_price → EastMoney/Sina 挂了就
回退 akshare，587 只 × ~25s = 4 小时不可行。而 Sina 批量接口全量只要 ~13s
（live_price_bridge.fetch_live_prices，~12 批 × 50 只）。

本脚本：
  1. 主路径：Sina 批量全量 → 归一化为 price_cache 格式
  2. 兜底：price<=0（盘前/停牌）时用 prev_close，change_pct=0
  3. 保护：有效条目过少（<50）视为源故障 → 保留旧缓存不覆盖

尾部挂钩 (t5, 15:10 同批): save_cache 成功后 subprocess 调 scripts/material_price_refresh.py
(timeout=180s); 挂钩失败只 loud 打印, 不影响主职责退出码。
"""
import json
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
SRC = BASE / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

CACHE_FILE = BASE / "data" / "price_cache.json"
MIN_VALID = 50  # 低于此数视为源故障，保留旧缓存
MATERIAL_SCRIPT = BASE / "scripts" / "material_price_refresh.py"


def _hook_material_refresh():
    """材料刷新挂钩: 双检(存在+py_compile)后运行, 失败 loud 打印不中断主职责."""
    if not MATERIAL_SCRIPT.exists():
        print(f"[price_cache] ⚠️ 未找到 {MATERIAL_SCRIPT.name}, 跳过材料刷新", file=sys.stderr); return
    if subprocess.run([sys.executable, "-m", "py_compile", str(MATERIAL_SCRIPT)],
                      capture_output=True).returncode != 0:
        print(f"[price_cache] ⚠️ {MATERIAL_SCRIPT.name} py_compile 失败, 跳过挂钩", file=sys.stderr); return
    try:
        p = subprocess.run([sys.executable, str(MATERIAL_SCRIPT)], capture_output=True, text=True, errors="replace", timeout=180)
    except subprocess.TimeoutExpired:
        print("[price_cache] ❌ 材料刷新超时(>180s), 不中断主职责", file=sys.stderr); return
    for line in (p.stdout or "").splitlines():
        print(f"  [material] {line}")
    if p.returncode != 0:
        print(f"[price_cache] ❌ 材料刷新失败 rc={p.returncode}", file=sys.stderr)
        if p.stderr:
            print(f"[price_cache]   stderr: {(p.stderr or '').strip()[:300]}", file=sys.stderr)


def _load_old_cache() -> dict:
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8")).get("prices", {})
    except Exception:
        return {}


def _normalize(raw: dict) -> dict:
    """fetch_live_prices 结果 → price_cache 格式，price=0 用 prev_close 兜底."""
    out = {}
    for code, d in raw.items():
        if code.startswith("_"):
            continue
        price = float(d.get("price") or 0)
        prev_close = float(d.get("prev_close") or 0)
        if price <= 0:
            if prev_close > 0:
                price = prev_close  # 盘前/停牌：昨收兜底
            else:
                continue  # 无任何价格参考
        out[code] = {
            "price": round(price, 4),
            "change_pct": float(d.get("change_pct") or 0),
            "name": d.get("name") or code,
        }
    return out


def main() -> int:
    from etf_platform.data.live_price_bridge import fetch_live_prices
    from etf_platform.data.price_cache import save_cache

    raw = fetch_live_prices()
    prices = _normalize(raw)

    if len(prices) < MIN_VALID:
        old = _load_old_cache()
        print(f"[price_cache] ⚠️ 有效条目过少({len(prices)}<{MIN_VALID})，视为源故障，保留旧缓存({len(old)}条)")
        return 1

    if save_cache(prices):
        print(f"[price_cache] ✅ 刷新 {len(prices)} 只 → {CACHE_FILE.name}")
        _hook_material_refresh()
        return 0
    print("[price_cache] ❌ save_cache 失败", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
