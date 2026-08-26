#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""material_price_refresh.py — 材料价格真实源定期刷新 (cc_batch_c + t5)

S2 守卫的根治侧: config/material_prices.yaml 等静态快照周期性被真实行情刷新,
文件 mtime 更新 → freshness 守卫自动恢复 fresh 全权 (k090 锂价教训)。

主源: akshare futures_spot_price_previous (现货价), 复用 material_live.py 的
抓取模式; 一切外部调用经 run_with_timeout 包裹, 防 akshare 网络不稳拖死。

兜底源 (t5): Sina 期货行情 (hq.sinajs.cn, nf_ 前缀主力连续合约)。实测 hf_
前缀接口返回空串而 nf_ 可正常取数 (2026-08 探针验证)。akshare 个别品种取不到
→ 查品种→合约映射表 (只覆盖本脚本实际命中过的品种) → 取 Sina 期货价, 条目盖
price_source (akshare/sina_fallback) 便于审计。单品种双源都取不到 → 保持原样。

刷新目标: config/material_prices.yaml + config/emerging_materials.yaml
(两文件同结构 materials{current,unit} 才刷; 结构不同则跳过并在摘要说明)。
每个文件独立汇总 updated/kept/failed; --dry-run 对两文件同时生效。

建议挂法 (工作日 15:10, price_cache_refresh 同批 cron, 行情收盘后取数):
  10 15 * * 1-5  cd /path/to/etf-platform && PYTHONPATH=src python scripts/material_price_refresh.py
先跑 --dry-run 观察将更新哪些条目再启用 cron。
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

REFRESH_TARGETS = [
    BASE / "config" / "material_prices.yaml",
    BASE / "config" / "emerging_materials.yaml",
]
FETCH_TIMEOUT = 30

SINA_QUOTE_URL = "https://hq.sinajs.cn/list="
SINA_MAIN_SUFFIX = "0"  # Sina 连续合约后缀: 0 = 主力连续

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

# 材料主名 → Sina 期货合约代码 (只覆盖本脚本 akshare 实际命中过的品种,
# 即 material_prices.yaml 中带 price_as_of 的真实刷新条目; 美元计价/无期货的
# 品种如铜、光伏玻璃不在内 — 从未成功刷过不建映射)
_SINA_FUTURE_CODE = {
    "碳酸锂": "LC", "镍": "NI", "铝": "AL", "锌": "ZN", "铅": "PB",
    "锡": "SN", "硅铁": "SF", "PTA": "TA", "甲醇": "MA", "PVC": "V",
    "尿素": "UR", "大豆": "A", "玉米": "C", "生猪": "LH",
    "白糖": "SR", "棉花": "CF", "天然橡胶": "RU", "螺纹钢": "RB", "沥青": "BU",
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


def _sina_code_for_base(base: str):
    """材料主名 → Sina 期货合约代码 (如 碳酸锂→LC); 未映射返回 None."""
    return _SINA_FUTURE_CODE.get(base)


def _sina_quote_url(codes: list) -> str:
    """连续合约代码列表 → Sina 批量行情 URL (nf_ 主力连续)."""
    return SINA_QUOTE_URL + ",".join(f"nf_{c}{SINA_MAIN_SUFFIX}" for c in codes)


def _to_positive_float(raw):
    """字符串 → 正有限浮点; 无效/0/NaN 返回 None."""
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) and v > 0 else None


def _parse_sina_futures(raw_text: str) -> dict:
    """解析 hq.sinajs.cn 批量返回 → {完整代码: {name, price}}.

    字段 (nf_ 连续合约, 2026-08 探针实测): [0]名称 [8]最新价 [10]昨结算.
    最新价无效时用昨结算兜底 (收盘后两者一致); 空 payload / 双价都无效 → 跳过.
    """
    out = {}
    for line in raw_text.splitlines():
        line = line.strip()
        if not line.startswith("var hq_str_"):
            continue
        var, _, body = line.partition("=")
        code = var.replace("var hq_str_", "").strip()
        payload = body.strip().strip('";').strip('"')
        if not payload:
            continue
        fields = payload.split(",")
        if len(fields) < 11:
            continue
        price = _to_positive_float(fields[8]) or _to_positive_float(fields[10])
        if price is None:
            continue
        out[code] = {"name": fields[0], "price": price}
    return out


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
        spot = _to_positive_float(row.get("现货价格", 0))
        if spot is None:
            continue
        out[name] = spot
    return out


def _fetch_sina_quotes(codes: list) -> dict:
    """拉取 Sina 期货行情 → {完整代码: {name, price}}. 失败抛异常 (loud)."""
    import requests
    url = _sina_quote_url(codes)
    resp = run_with_timeout(
        requests.get, url, timeout=FETCH_TIMEOUT,
        headers={"Referer": "https://finance.sina.com.cn"})
    if resp is None:
        raise TimeoutError(f"Sina 期货行情超时(>{FETCH_TIMEOUT}s)")
    resp.encoding = "gbk"
    return _parse_sina_futures(resp.text)


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
    """源价格 → yaml current 字符串; 单位不可可靠换算返回 None (保持原样)."""
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
    # 外币/其他单位 ($/oz, $/吨, 令吉/吨, 元/克, 万元/kg ...) 不做换算, 保持原样
    return None


def _is_mat_line(line: str, indent: int, stripped: str) -> bool:
    return (indent == 2 and stripped and not stripped.startswith("#")
            and stripped.endswith(":") and not stripped.startswith("- "))


def _write_back(path: Path, updates: dict, refreshed_at: str):
    """文本级精准写回: 替换 current / 维护 price_as_of / price_source / 顶部 _refreshed_at.

    updates: {mat_name: {"current": str, "price_source": str}};
    price_as_of 统一用 refreshed_at; price_source 只在更新条目上盖 (akshare/sina_fallback).
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
        ins = inserted.setdefault(current_mat, set())
        if stripped.startswith("current:"):
            out.append(f"{' ' * indent}current: \"{upd['current']}\"")
            continue
        if stripped.startswith("price_as_of:"):
            out.append(f"{' ' * indent}price_as_of: '{refreshed_at}'")
            ins.add("as_of")
            continue
        if stripped.startswith("price_source:"):
            out.append(f"{' ' * indent}price_source: \"{upd['price_source']}\"")
            ins.add("source")
            continue
        if "as_of" not in ins:
            out.append(f"{' ' * indent}price_as_of: '{refreshed_at}'")
            ins.add("as_of")
        if "source" not in ins:
            out.append(f"{' ' * indent}price_source: \"{upd['price_source']}\"")
            ins.add("source")
        out.append(line)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def _refresh_one_file(path: Path, ak_map: dict, sina_map: dict, dry_run: bool) -> dict:
    """处理单文件: 逐材料主源 akshare → 兜底 Sina → 转换. 返回独立汇总."""
    summary = {"file": path.name, "updated": [], "kept_no_price": [],
               "kept_unit": [], "failed": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = pyyaml.safe_load(f)
    except Exception as e:
        summary["error"] = f"读取失败: {type(e).__name__}: {e}"
        return summary
    if not isinstance(data, dict) or "materials" not in data:
        summary["error"] = "无 materials 顶层键, 跳过"
        return summary

    mats = data["materials"] or {}
    updates = {}
    for mat_name, mat in mats.items():
        if mat is None or not isinstance(mat, dict):
            summary["kept_no_price"].append(mat_name)
            continue
        try:
            yaml_unit = str(mat.get("unit", "")).strip()
            if not yaml_unit or yaml_unit in ("N/A", "无", "暂无"):
                # 无计价单位 (战略物资/不公开等), 即使命中商品也取不到可比价
                summary["kept_no_price"].append(mat_name)
                continue
            base = _base_name(mat_name)
            ak_name = _match_ak_name(base, ak_map)
            if ak_name:
                ak_price = ak_map[ak_name]
                ak_unit = _AK_SPOT_UNIT.get(ak_name, "元/吨")
                new_current = _convert_current(ak_price, ak_unit, yaml_unit)
                source = "akshare"
            else:
                # 主源取不到 → Sina 期货兜底 (映射表只覆盖实际命中过的品种)
                code = _sina_code_for_base(base)
                quote = sina_map.get(f"nf_{code}{SINA_MAIN_SUFFIX}") if code else None
                if not quote:
                    summary["kept_no_price"].append(mat_name)
                    continue
                new_current = _convert_current(quote["price"], "元/吨", yaml_unit)
                source = "sina_fallback"
            if new_current is None:
                summary["kept_unit"].append(mat_name)
                continue
            print(f"[refresh] {mat_name}: {new_current} ← {source}")
            updates[mat_name] = {"current": new_current, "price_source": source}
            summary["updated"].append(mat_name)
        except Exception as e:
            summary["failed"].append((mat_name, f"{type(e).__name__}: {str(e)[:120]}"))
            print(f"[refresh] ❌ {mat_name} 更新失败: {summary['failed'][-1][1]}", file=sys.stderr)

    if dry_run:
        summary["dry_run"] = True
        return summary
    if not updates:
        summary["no_write"] = "没有任何材料更新(全部保持原样), 不写盘"
        return summary
    try:
        refreshed_at = datetime.now().isoformat(timespec="seconds")
        _write_back(path, updates, refreshed_at)
        summary["written"] = True
    except Exception as e:
        summary["failed"].append((path.name, f"写回失败: {type(e).__name__}: {e}"))
        print(f"[refresh] ❌ 写回 {path.name} 失败: {type(e).__name__}: {e}", file=sys.stderr)
    return summary


def _print_summary(s: dict):
    if s.get("error"):
        print(f"[refresh] ⚠️ {s['file']}: {s['error']}", file=sys.stderr)
        return
    tag = "[dry-run] " if s.get("dry_run") else ""
    kept = len(s["kept_no_price"]) + len(s["kept_unit"])
    print(f"{tag}[refresh] {s['file']} 摘要: updated={len(s['updated'])} kept={kept} "
          f"(无行情{len(s['kept_no_price'])} + 单位不可换算{len(s['kept_unit'])}) failed={len(s['failed'])}")
    if s.get("kept_no_price"):
        print(f"{tag}[refresh] {s['file']} 无行情保持原样: {'、'.join(s['kept_no_price'])}")
    if s.get("kept_unit"):
        print(f"{tag}[refresh] {s['file']} 单位不可换算保持原样: {'、'.join(s['kept_unit'])}")
    if s.get("no_write"):
        print(f"{tag}[refresh] {s['file']}: {s['no_write']}", file=sys.stderr)
    if s.get("written"):
        print(f"[refresh] ✅ 已写回 {s['file']} (mtime 已刷新 → S2 守卫恢复 fresh)")
    if s.get("failed"):
        print(f"[refresh] {s['file']} 失败条目: {s['failed']}", file=sys.stderr)


def _collect_sina_codes(ak_map: dict) -> list:
    """预扫描刷新目标: akshare 取不到但存在 Sina 映射的品种 → 短合约代码列表."""
    codes = set()
    for path in REFRESH_TARGETS:
        try:
            data = pyyaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        for mat_name in (data.get("materials") or {}):
            base = _base_name(mat_name)
            code = _sina_code_for_base(base)
            if code and _match_ak_name(base, ak_map) is None:
                codes.add(code)
    return sorted(codes)


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    try:
        ak_map = _fetch_ak_spot()
    except Exception as e:
        print(f"[refresh] ❌ akshare 现货行情拉取失败(全部材料保持原样): "
              f"{type(e).__name__}: {str(e)[:200]}", file=sys.stderr)
        return 1

    print(f"[refresh] akshare 现货行情: {len(ak_map)} 个商品")

    sina_map = {}
    codes = _collect_sina_codes(ak_map)
    if codes:
        try:
            sina_map = _fetch_sina_quotes(codes)
            print(f"[refresh] Sina 兜底行情: {len(sina_map)}/{len(codes)} 个合约")
        except Exception as e:
            print(f"[refresh] ⚠️ Sina 兜底拉取失败(仅 akshare 取不到的品种无兜底): "
                  f"{type(e).__name__}: {str(e)[:200]}", file=sys.stderr)

    for path in REFRESH_TARGETS:
        summary = _refresh_one_file(path, ak_map, sina_map, dry_run)
        _print_summary(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
