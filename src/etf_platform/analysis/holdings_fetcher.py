# -*- coding: utf-8 -*-
"""holdings_fetcher.py — ETF 持仓数据抓取（eastmoney 直连）.

v2.0 重写：
- 修复 akshare fund_portfolio_hold_em 无 UA 被 eastmoney 404 的问题（该接口每次必抛
  JSONDecodeError），改为 requests+浏览器 UA 直连 FundArchivesDatas，返回每年度各季度
  前十大股票持仓。
- 新增磁盘缓存（data/holdings_cache.json）与全量刷新管道 refresh_all()。

字段契约：每个持仓 dict 含 code/name/weight（holdings_overlap 期望）与
pct_nav（百分数）/shares/market_value/quarter；weight = pct_nav/100（小数）。
历史版本曾输出 stock_code/stock_name，读接口统一用
h.get("code") or h.get("stock_code") 兼容。
"""

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ─── 常量 ────────────────────────────────────────────────────────────────
_EASTMONEY_URL = "https://fundf10.eastmoney.com/FundArchivesDatas.aspx"
_UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Referer": "https://fundf10.eastmoney.com/",
}
_HTTP_TIMEOUT = 20
_MAX_RETRIES = 2

_DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"
_CACHE_PATH = _DATA_DIR / "holdings_cache.json"
_CHECKPOINT_PATH = _DATA_DIR / "holdings_refresh_checkpoint.json"
_CACHE_TTL = 7 * 86400  # 7 天：持仓季度披露
_EMPTY_TTL = 86400  # 空持仓缓存 1 天：eastmoney 限流可能返回"假空"，短 TTL 快速自愈
_MIN_SUCCESS_RATIO = 0.5  # 防覆盖保护：有效请求低于此比例视为源故障，保留旧缓存

# 列名别名（pd.read_html 返回的原始表头 → 规范字段）
_COLUMN_ALIASES = {
    "占净值 比例": "占净值比例",
    "占净值\xa0比例": "占净值比例",
    "持股数（万股）": "持股数",
    "持股数 （万股）": "持股数",
    "持股数(万股)": "持股数",
    "持仓市值（万元）": "持仓市值",
    "持仓市值（万元人民币）": "持仓市值",
    "持仓市值 (万元)": "持仓市值",
    "持仓市值（元）": "持仓市值",
}
_HOLDING_FIELDS = ["股票代码", "股票名称", "占净值比例", "持股数", "持仓市值"]


# ─── 内存缓存（同进程避免重复请求/重复读盘） ──────────────────────────────
_holdings_cache: Dict[str, tuple] = {}
_holdings_cache_lock = threading.Lock()


def _load_disk_cache() -> dict:
    try:
        return json.loads(_CACHE_PATH.read_text(encoding="utf-8")).get("holdings", {})
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
        logger.warning("[holdings_fetcher] 持仓缓存损坏/不可读(%s)，按空缓存处理: %s",
                       _CACHE_PATH.name, e)
        return {}
    except Exception:
        return {}


def _save_disk_cache(holdings: dict, updated: float = None) -> bool:
    """写盘。保存时勿重置每条的 ts（避免 TTL 无限顺延）。"""
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(updated or time.time())),
            "holdings": holdings,
        }
        _CACHE_PATH.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return True
    except Exception as e:
        logger.warning("[holdings_fetcher] 写盘失败: %s", e)
        return False


def _safe_float(val) -> float:
    from ..utils import safe_float
    if val is None:
        return 0.0
    s = str(val).replace("%", "").strip()
    if not s:
        return 0.0
    return safe_float(s)


# ─── eastmoney 直连抓取 ──────────────────────────────────────────────────
def _fetch_from_eastmoney(code: str, year: str) -> Optional[List[Dict]]:
    """拉取单只 ETF 某年度各季度前十大持仓。

    返回 None = 网络/解析失败；[] = 正常但无股票持仓（黄金/商品类）；否则持仓列表。
    """
    import requests
    from bs4 import BeautifulSoup
    from io import StringIO
    from akshare.utils import demjson

    try:
        resp = requests.get(
            _EASTMONEY_URL,
            params={
                "type": "jjcc",
                "code": code,
                "topline": "10000",
                "year": year,
                "month": "",
                "rt": "0.913877030254846",
            },
            headers=_UA,
            timeout=_HTTP_TIMEOUT,
        )
    except requests.RequestException as e:
        logger.debug("[holdings_fetcher] %s/%s 请求失败: %s", code, year, e)
        return None

    if resp.status_code != 200 or "apidata" not in resp.text:
        logger.debug("[holdings_fetcher] %s/%s 非预期响应 status=%s", code, year, resp.status_code)
        return None

    try:
        data_text = resp.text
        dj = demjson.decode(data_text[data_text.find("{") : -1])
        soup = BeautifulSoup(dj["content"], features="lxml")
        labels = [x.text.split("\xa0\xa0")[1] for x in soup.find_all(name="h4", attrs={"class": "t"})]
    except Exception as e:
        logger.debug("[holdings_fetcher] %s/%s 解析失败: %s", code, year, e)
        return None

    if not labels:
        return []

    import pandas as pd
    result: List[Dict] = []
    for i, label in enumerate(labels):
        try:
            table = pd.read_html(StringIO(dj["content"]), converters={"股票代码": str})[i]
        except (ValueError, IndexError):
            continue
        table = table.rename(columns=_COLUMN_ALIASES)
        for c in list(table.columns):
            if c not in _HOLDING_FIELDS:
                table = table.drop(columns=c)
        for c in _HOLDING_FIELDS:
            if c not in table.columns:
                table[c] = None
        for _, row in table.iterrows():
            pct = _safe_float(row.get("占净值比例"))
            result.append({
                "code": str(row.get("股票代码") or "").strip(),
                "name": str(row.get("股票名称") or "").strip(),
                "pct_nav": pct,
                "weight": round(pct / 100.0, 6),
                "shares": _safe_float(row.get("持股数")),
                "market_value": _safe_float(row.get("持仓市值")),
                "quarter": label,
            })
    return result


_QUARTER_RE = __import__("re").compile(r"(\d{4})年(\d{1,2})季度")


def _latest_quarter_holdings(holdings: List[Dict]) -> List[Dict]:
    """只保留最新季度持仓。接口返回整年多季度，跨季度累加会重复计数（同一股票多次出现）。"""
    if not holdings:
        return []
    best = None
    for h in holdings:
        m = _QUARTER_RE.search(h.get("quarter", ""))
        if m:
            key = (int(m.group(1)), int(m.group(2)))
            if best is None or key > best:
                best = key
    if best is None:
        return holdings
    return [h for h in holdings
            if _latest_quarter_key(h.get("quarter", "")) == best]


def _latest_quarter_key(quarter: str):
    m = _QUARTER_RE.search(quarter)
    return (int(m.group(1)), int(m.group(2))) if m else None


def _fetch_latest(code: str) -> Optional[List[Dict]]:
    """抓最新季度持仓：先当年，空则回退前一年。"""
    this_year = str(time.localtime().tm_year)
    for year in (this_year, str(time.localtime().tm_year - 1)):
        data = _fetch_from_eastmoney(code, year)
        if data is None:
            # 网络/解析失败：立即回退下一年；都失败才返回 None
            continue
        return data
    return None


# ─── 主入口：单只持仓（缓存优先） ─────────────────────────────────────────
def _get_holdings_for_etf(code: str) -> Optional[List[Dict]]:
    """磁盘缓存 → 在线抓取 → 写回缓存。返回 None = 抓取失败；[] = 正常空。"""
    now = time.time()
    with _holdings_cache_lock:
        if code in _holdings_cache:
            data, ts = _holdings_cache[code]
            if now - ts < _CACHE_TTL:
                return data

    disk = _load_disk_cache()
    entry = disk.get(code)
    if entry:
        ts = entry.get("ts", 0)
        data = entry.get("data", [])
        if now - ts < (_EMPTY_TTL if not data else _CACHE_TTL):
            with _holdings_cache_lock:
                _holdings_cache[code] = (data, ts)
            return data

    data = _fetch_latest(code)
    if data is None:
        return None
    with _holdings_cache_lock:
        _holdings_cache[code] = (data, now)
    disk[code] = {"ts": now, "data": data}
    _save_disk_cache(disk, updated=now)
    return data


# ─── 上层接口（保持兼容） ────────────────────────────────────────────────
def get_cached_holdings(code: str) -> Optional[List[Dict]]:
    """只读缓存（内存→磁盘），不触发网络。miss 返回 None。供 pipeline 高频调用。"""
    now = time.time()
    with _holdings_cache_lock:
        if code in _holdings_cache:
            data, ts = _holdings_cache[code]
            if now - ts < _CACHE_TTL:
                return data
    entry = _load_disk_cache().get(code)
    if entry:
        data = entry.get("data", [])
        if now - entry.get("ts", 0) < (_EMPTY_TTL if not data else _CACHE_TTL):
            return data
    return None


def get_top_holdings(code: str, top_n: int = 10) -> List[Dict]:
    """Get top N holdings for an ETF, sorted by weight."""
    holdings = _get_holdings_for_etf(code)
    holdings = _latest_quarter_holdings(holdings)
    if not holdings:
        return []
    sorted_h = sorted(holdings, key=lambda x: x["pct_nav"], reverse=True)
    return sorted_h[:top_n]


def get_concentration_metrics(code: str) -> Dict:
    """集中度指标：top1/top3/top5/top10 权重(百分数)、HHI、有效持仓数。"""
    holdings = _get_holdings_for_etf(code)
    holdings = _latest_quarter_holdings(holdings)
    if not holdings:
        return {
            "top1_pct": 0, "top3_pct": 0, "top5_pct": 0, "top10_pct": 0,
            "herfindahl": 0, "effective_holdings": 0, "total_holdings": 0,
        }
    weights = sorted([h["pct_nav"] for h in holdings], reverse=True)
    # pct_nav 是百分数（4.75=4.75%），HHI 需转小数权重再平方，否则放大 10000×
    hhi = sum((w / 100.0) ** 2 for w in weights)
    return {
        "top1_pct": weights[0] if weights else 0,
        "top3_pct": sum(weights[:3]),
        "top5_pct": sum(weights[:5]),
        "top10_pct": sum(weights[:10]),
        "total_holdings": len(weights),
        "herfindahl": round(hhi, 4),
        "effective_holdings": round(1.0 / hhi, 1) if hhi > 0 else 0,
    }


def get_sector_exposure(code: str) -> Dict[str, float]:
    """按股票代码前缀启发式估计板块暴露。"""
    holdings = _get_holdings_for_etf(code)
    holdings = _latest_quarter_holdings(holdings)
    if not holdings:
        return {}
    from collections import defaultdict
    sector_map = defaultdict(float)
    for h in holdings:
        weight = h["pct_nav"]
        stock_code = h.get("code") or h.get("stock_code") or ""
        stock_name = h.get("name") or h.get("stock_name") or ""
        if not stock_code:
            continue
        if stock_code.startswith("68"):
            sector_map["硬科技"] += weight
        elif stock_code.startswith("30"):
            sector_map["成长/科技"] += weight
        elif stock_code.startswith("60"):
            if any(k in stock_name for k in ["银行", "保险", "证券"]):
                sector_map["金融"] += weight
            elif any(k in stock_name for k in ["酒", "饮", "食"]):
                sector_map["消费"] += weight
            elif any(k in stock_name for k in ["药", "医"]):
                sector_map["医药"] += weight
            elif any(k in stock_name for k in ["矿", "铜", "铝", "金"]):
                sector_map["周期/资源"] += weight
            elif any(k in stock_name for k in ["电", "力", "能"]):
                sector_map["公用事业/能源"] += weight
            else:
                sector_map["综合/其他"] += weight
        elif stock_code.startswith("00"):
            if any(k in stock_name for k in ["技", "科", "电", "网"]):
                sector_map["科技"] += weight
            elif any(k in stock_name for k in ["药", "医"]):
                sector_map["医药"] += weight
            elif any(k in stock_name for k in ["车", "汽"]):
                sector_map["新能源/汽车"] += weight
            else:
                sector_map["综合/其他"] += weight
        else:
            sector_map["其他"] += weight
    return dict(sector_map)


def get_material_exposure(code: str) -> Dict[str, float]:
    """从持仓识别材料/大宗商品暴露。"""
    holdings = _get_holdings_for_etf(code)
    holdings = _latest_quarter_holdings(holdings)
    if not holdings:
        return {}
    from collections import defaultdict
    material_keywords = {
        "锂": "锂电材料", "钴": "锂电材料", "镍": "锂电材料", "石墨": "锂电材料",
        "正极": "锂电材料", "负极": "锂电材料", "隔膜": "锂电材料", "电解液": "锂电材料",
        "硅": "半导体材料", "碳": "新材料", "钢": "钢铁材料", "铁": "钢铁材料",
        "铜": "有色金属", "铝": "有色金属", "金": "贵金属", "银": "贵金属",
        "锌": "有色金属", "稀土": "稀土材料", "磁": "稀土材料", "光伏": "光伏材料",
        "硅片": "光伏材料", "电池": "电池材料", "半导体": "半导体材料",
        "芯片": "半导体材料", "晶": "半导体材料",
    }
    exposure = defaultdict(float)
    for h in holdings:
        weight = h["pct_nav"]
        name = h.get("name") or h.get("stock_name") or ""
        for kw, mat_type in material_keywords.items():
            if kw in name:
                exposure[mat_type] += weight
                break
    return dict(exposure)


# ─── 全量刷新管道 ────────────────────────────────────────────────────────
def _load_checkpoint() -> dict:
    try:
        return json.loads(_CHECKPOINT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_checkpoint(done: set) -> None:
    try:
        _CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CHECKPOINT_PATH.write_text(
            json.dumps({"updated": time.strftime("%Y-%m-%dT%H:%M:%S"), "done": sorted(done)},
                       ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning("[holdings_fetcher] checkpoint 写盘失败: %s", e)


def _fetch_one(code: str) -> Optional[List[Dict]]:
    """单只抓取 + 重试。None(网络/解析失败) 重试 _MAX_RETRIES 次；
    empty(限流假空) 额外重试 1 次后仍空则按正常空返回。"""
    data = _fetch_latest(code)
    if data is None:
        for attempt in range(_MAX_RETRIES):
            time.sleep(0.6 * (attempt + 1))
            data = _fetch_latest(code)
            if data is not None:
                break
        if data is None:
            logger.warning("[holdings_fetcher] %s 抓取失败（已重试 %d 次），跳过",
                           code, _MAX_RETRIES + 1)
    elif not data:
        time.sleep(0.8)
        again = _fetch_latest(code)
        if again is not None:
            data = again
    return data


def refresh_all(codes: Optional[List[str]] = None, limit: Optional[int] = None,
                workers: int = 4) -> Dict:
    """全量刷新持仓缓存。

    codes=None 时读 config/etfs.yaml 全量。返回统计：
    {"total", "ok", "empty", "failed", "saved", "cache_path"}。
    防覆盖保护：有效请求(ok+empty)比例 < 50% 时不写盘，返回 saved=False。
    """
    if codes is None:
        from ..config_loader import load_etfs
        codes = sorted(load_etfs().keys())
    if limit:
        codes = codes[:limit]

    checkpoint = _load_checkpoint()
    done = set(checkpoint.get("done", []))

    ok, empty, failed = 0, 0, 0
    results: Dict[str, Optional[List[Dict]]] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_fetch_one, code): code for code in codes}
        for fut in as_completed(futures):
            code = futures[fut]
            data = fut.result()
            results[code] = data
            if data is None:
                failed += 1
            elif not data:
                empty += 1
            else:
                ok += 1

    total = len(codes)
    attempted = ok + empty + failed
    success_ratio = (ok + empty) / attempted if attempted else 0.0

    disk = _load_disk_cache()
    now = time.time()
    for code, data in results.items():
        if data is not None:  # 失败的不覆盖旧缓存
            disk[code] = {"ts": now, "data": data}
    done.update(r for r in results if results[r] is not None)

    saved = False
    if success_ratio >= _MIN_SUCCESS_RATIO:
        saved = _save_disk_cache(disk, updated=now)
        logger.info("[holdings_fetcher] 刷新完成 ok=%d empty=%d failed=%d → %s",
                    ok, empty, failed, _CACHE_PATH)
    else:
        logger.warning("[holdings_fetcher] 有效请求比例 %.0f%% < %d%%，视为源故障，保留旧缓存",
                       success_ratio * 100, int(_MIN_SUCCESS_RATIO * 100))
    _save_checkpoint(done)

    return {
        "total": total,
        "ok": ok,
        "empty": empty,
        "failed": failed,
        "success_ratio": round(success_ratio, 3),
        "saved": saved,
        "cache_path": str(_CACHE_PATH),
    }


def clear_cache() -> None:
    """清空内存缓存（磁盘缓存保留）。"""
    with _holdings_cache_lock:
        _holdings_cache.clear()
    logger.info("[holdings_fetcher] memory cache cleared")


if __name__ == "__main__":
    import logging
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if len(sys.argv) > 1 and sys.argv[1] == "--refresh":
        limit = None
        for a in sys.argv[2:]:
            if a.startswith("--limit="):
                limit = int(a.split("=")[1])
        stats = refresh_all(limit=limit)
        print(stats)
    else:
        test_codes = ["510300", "510500", "510050", "159919", "512100"]
        for code in test_codes:
            top = get_top_holdings(code, 5)
            conc = get_concentration_metrics(code)
            print(f"\n{code}:")
            print(f"  Total holdings: {conc['total_holdings']}")
            print(f"  Top1: {conc['top1_pct']:.1f}%, Top3: {conc['top3_pct']:.1f}%, Top10: {conc['top10_pct']:.1f}%")
            if top:
                print("  Top 5:")
                for h in top:
                    print(f"    {h['name']} ({h['code']}): {h['pct_nav']:.2f}%")
