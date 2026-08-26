#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""refresh_material_prices.py — 材料价格真实源定期刷新 (cc_batch_c)

S2 守卫的根治侧: config/material_prices.yaml 等静态快照周期性被真实行情刷新,
文件 mtime 更新 → freshness 守卫自动恢复 fresh 全权 (k090 锂价教训)。

对能匹配到 akshare 现货行情的材料:
  - 更新 `current` 为实时价数值字符串 (单位与 yaml 的 unit 字段对齐)
  - 条目盖 `price_as_of` (ISO 时间戳)
顶部写 `_refreshed_at` (ISO)。
取不到价 / 单位不可可靠换算的材料保持原样, 在摘要中列出。

写回用文本级精准编辑 (只动 current 行/price_as_of 行/顶部 _refreshed_at),
不重排其余字节 — ruamel/PyYAML dump 会把 flow list 逗号格式规范化产生噪音 diff。

建议挂法 (工作日 15:30, price_cache_refresh 之后, 行情收盘后取数):
  30 15 * * 1-5  cd /path/to/etf-platform && PYTHONPATH=src python scripts/refresh_material_prices.py
先跑 --dry-run 观察将更新哪些条目再启用 cron。

数据源: akshare futures_spot_price_previous (现货价), 复用 material_live.py 的
抓取模式; 一切外部调用经 run_with_timeout 包裹, 防 akshare 网络不稳拖死。
"""
import math
import sys
from datetime import datetime
from pathlib import Path

import yaml as pyyaml

BASE = Path(__file__).resolve().parent.parent  # etf-platform/
SRC = BASE / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from etf_platform.utils.thread_timeout import run_with_timeout

CONFIG_FILE = BASE / "config" / "material_prices.yaml"
FETCH_TIMEOUT = 30

# 材料名 → akshare 现货商品名 (子串匹配覆盖不了的别名)
_ALIAS = {
    "PVC": "聚氯乙烯",
    "大豆": "豆一",
    "沥青": "石油沥青",
}

# akshare 现货价原单位 (未列出的按元/吨)
_AK_SPOT_UNIT = {
    "黄金": "元/克", "白银": "元/千克", "玻璃": "元/㎡",
    "鸡蛋": "元/斤", "生猪": "元/公斤",
}


def _base_name(mat_name: str) -> str:
    """去括号取主名: '碳酸锂(电池级)' → '碳酸锂', '黄金(Au9999)' → '黄金'."""
    return mat_name.split("(")[0].split("（")[0].strip()


def _normalize_ak_name(raw: str) -> str:
    """去交易所/合约后缀: '甲醇MA' → '甲醇', '菜籽油OI' → '菜籽油'."""
    for suffix in ("MA", "OI"):
        if raw.endswith(suffix) and len(raw) > len(suffix):
            return raw[: -len(suffix)]
    return raw


def _fetch_ak_spot() -> dict:
    """拉取 akshare 现货行情 → {商品名: 现货价}. 失败抛异常 (loud)."""
    import akshare as ak
    df = run_with_timeout(ak.futures_spot_price_previous, timeout=FETCH_TIMEOUT)
    if df is None:
        raise TimeoutError(f"futures_spot_price_previous 超时(>{FETCH_TIMEOUT}s)")
    out = {}
    for _, row in df.iterrows():
        name = str(row.get("商品", "")).strip()
        if not name:
            continue
        try:
            spot = float(row.get("现货价格", 0) or 0)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(spot) or spot <= 0:
            continue
        out[name] = spot
    return out


def _match_ak_name(base: str, ak_map: dict):
    """材料主名 → ak 商品名; 未命中返回 None."""
    norm_to_raw = {}
    for raw in ak_map:
        norm_to_raw.setdefault(_normalize_ak_name(raw), raw)
    if base in norm_to_raw:
        return norm_to_raw[base]
    alias = _ALIAS.get(base)
    if alias and alias in norm_to_raw:
        return norm_to_raw[alias]
    for norm, raw in norm_to_raw.items():
        if len(base) >= 2 and (base in norm or norm in base):
            return raw
    return None


def _convert_current(ak_price: float, ak_unit: str, yaml_unit: str):
    """ak 现货价 → yaml current 字符串; 单位不可可靠换算返回 None (保持原样)."""
    if yaml_unit == "元/吨":
        if ak_unit == "元/吨":
            return f"{ak_price:,.0f}元/吨"
        return None
    if yaml_unit == "万元/吨":
        if ak_unit == "元/吨":
            return f"{ak_price / 10000:.2f}万元/吨"
        return None
    if yaml_unit == "元/kg":
        if ak_unit == "元/公斤":
            return f"{ak_price:.2f}元/kg"
        if ak_unit == "元/吨":
            return f"{ak_price / 1000:.2f}元/kg"
        return None
    if yaml_unit == "元/㎡":
        if ak_unit == "元/㎡":
            return f"{ak_price:.2f}元/㎡"
        return None
    # 外币/其他单位 ($/oz, $/吨, 令吉/吨 ...) 不做汇率换算, 保持原样
    return None


def _is_mat_line(line: str, indent: int, stripped: str) -> bool:
    return (indent == 2 and stripped and not stripped.startswith("#")
            and stripped.endswith(":") and not stripped.startswith("- "))


def _write_back(path: Path, updates: dict, refreshed_at: str):
    """文本级精准写回: 替换 current / 维护 price_as_of / 顶部插 _refreshed_at.

    updates: {mat_name: {"current": str}}; price_as_of 统一用 refreshed_at。
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    out = [f"_refreshed_at: '{refreshed_at}'"]
    current_mat = None
    inserted = {}
    for line in lines:
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        if _is_mat_line(line, indent, stripped):
            current_mat = stripped[:-1].strip()
            out.append(line)
            continue
        upd = updates.get(current_mat)
        if upd is None:
            out.append(line)
            continue
        if stripped.startswith("current:"):
            out.append(f"{' ' * indent}current: \"{upd['current']}\"")
            continue
        if stripped.startswith("price_as_of:"):
            out.append(f"{' ' * indent}price_as_of: '{refreshed_at}'")
            inserted[current_mat] = True
            continue
        if not inserted.get(current_mat):
            out.append(f"{' ' * indent}price_as_of: '{refreshed_at}'")
            inserted[current_mat] = True
        out.append(line)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = pyyaml.safe_load(f)
    except Exception as e:
        print(f"[refresh] ❌ 读取 {CONFIG_FILE.name} 失败: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    if not isinstance(data, dict) or "materials" not in data:
        print(f"[refresh] ❌ {CONFIG_FILE.name} 无 materials 顶层键", file=sys.stderr)
        return 1

    try:
        ak_map = _fetch_ak_spot()
    except Exception as e:
        print(f"[refresh] ❌ akshare 现货行情拉取失败(全部材料保持原样): {type(e).__name__}: {str(e)[:200]}", file=sys.stderr)
        return 1

    print(f"[refresh] akshare 现货行情: {len(ak_map)} 个商品")

    mats = data["materials"] or {}
    updated, failed = [], []
    kept_no_price, kept_unit = [], []
    updates = {}

    for mat_name, mat in mats.items():
        if mat is None or not isinstance(mat, dict):
            kept_no_price.append(mat_name)
            continue
        try:
            yaml_unit = str(mat.get("unit", "")).strip()
            if not yaml_unit or yaml_unit in ("N/A", "无", "暂无"):
                # 无计价单位 (战略物资/不公开等), 即使子串命中 ak 商品也取不到可比价
                kept_no_price.append(mat_name)
                continue
            base = _base_name(mat_name)
            ak_name = _match_ak_name(base, ak_map)
            if not ak_name:
                kept_no_price.append(mat_name)
                continue
            ak_price = ak_map[ak_name]
            ak_unit = _AK_SPOT_UNIT.get(ak_name, "元/吨")
            new_current = _convert_current(ak_price, ak_unit, yaml_unit)
            if new_current is None:
                kept_unit.append(mat_name)
                continue
            print(f"[refresh] {mat_name}: {new_current} ← {ak_name} {ak_price:g}{ak_unit}")
            updates[mat_name] = {"current": new_current}
            updated.append(mat_name)
        except Exception as e:
            failed.append((mat_name, f"{type(e).__name__}: {str(e)[:120]}"))
            print(f"[refresh] ❌ {mat_name} 更新失败: {failed[-1][1]}", file=sys.stderr)

    if dry_run:
        print(f"\n[dry-run] 不写盘。将更新 {len(updated)} 条; 取不到价 {len(kept_no_price)} 条; "
              f"单位不可换算 {len(kept_unit)} 条; 失败 {len(failed)} 条")
        if kept_no_price:
            print(f"[dry-run] 无行情保持原样: {'、'.join(kept_no_price)}")
        if kept_unit:
            print(f"[dry-run] 单位不可换算保持原样: {'、'.join(kept_unit)}")
        return 0

    if not updates:
        print("[refresh] ❌ 没有任何材料更新(全部保持原样), 不写盘", file=sys.stderr)
        return 1

    try:
        refreshed_at = datetime.now().isoformat(timespec="seconds")
        _write_back(CONFIG_FILE, updates, refreshed_at)
    except Exception as e:
        print(f"[refresh] ❌ 写回 {CONFIG_FILE.name} 失败: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    print(f"\n[refresh] 摘要: updated={len(updated)} kept={len(kept_no_price) + len(kept_unit)} "
          f"(无行情{len(kept_no_price)} + 单位不可换算{len(kept_unit)}) failed={len(failed)}")
    if kept_no_price:
        print(f"[refresh] 无行情保持原样: {'、'.join(kept_no_price)}")
    if kept_unit:
        print(f"[refresh] 单位不可换算保持原样: {'、'.join(kept_unit)}")
    if failed:
        print(f"[refresh] 失败条目: {failed}", file=sys.stderr)
    print(f"[refresh] ✅ 已写回 {CONFIG_FILE.name} (mtime 已刷新 → S2 守卫恢复 fresh)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
