# -*- coding: utf-8 -*-
"""material_live.py — real-time commodity prices + PMI + news confirmation for L3/L4 scoring.

v5.6: Replaces hardcoded deep.py materials with live akshare data.
"""

import math
import sys
import time
import statistics
import threading

from ..utils.thread_timeout import run_with_timeout

COMMODITY_SECTOR_MAP = {
    "原油": ["能源化工", "周期/资源"], "燃料油": ["能源化工"], "动力煤": ["煤炭", "周期/资源"],
    "焦煤": ["煤炭", "钢铁"], "焦炭": ["煤炭", "钢铁"],
    "铜": ["有色金属", "周期/资源"], "铝": ["有色金属", "周期/资源"],
    "锌": ["有色金属"], "镍": ["有色金属", "新能源"], "锡": ["有色金属"],
    "黄金": ["贵金属"], "白银": ["贵金属"],
    "螺纹钢": ["钢铁", "基建/地产"], "热轧卷板": ["钢铁", "基建/地产"],
    "铁矿石": ["钢铁"], "不锈钢": ["钢铁"],
    "PTA": ["化工", "消费"], "甲醇": ["化工", "能源化工"],
    "纯碱": ["化工"], "尿素": ["化工", "农产品"],
    "PVC": ["化工", "基建/地产"], "聚丙烯": ["化工", "消费"],
    "塑料": ["化工", "消费"], "乙二醇": ["化工"], "苯乙烯": ["化工"],
    "碳酸锂": ["新能源", "电池"], "工业硅": ["新能源", "光伏"],
    "豆粕": ["农产品", "养殖"], "豆油": ["农产品", "消费"],
    "棕榈油": ["农产品", "消费"], "菜籽油": ["农产品", "消费"],
    "玉米": ["农产品", "养殖"], "白糖": ["农产品", "消费"],
    "棉花": ["消费"], "天然橡胶": ["化工"],
    "玻璃": ["基建/地产"], "纤维板": ["基建/地产"],
}

SECTOR_COMMODITY_WEIGHT = {
    "有色金属": 0.40, "煤炭": 0.40, "钢铁": 0.35, "能源化工": 0.40,
    "新能源": 0.25, "电池": 0.30, "光伏": 0.20,
    "贵金属": 0.45, "化工": 0.30,
    "农产品": 0.25, "养殖": 0.20, "消费": 0.10,
    "基建/地产": 0.15, "周期/资源": 0.35,
}

_cache = {"commodities": None, "pmi": None, "ts": 0}
_CACHE_LOCK = threading.Lock()
CACHE_TTL = 3600


def _fetch_commodities():
    now = time.time()
    with _CACHE_LOCK:
        if _cache["commodities"] is not None and now - _cache["ts"] < CACHE_TTL:
            return _cache["commodities"]
    try:
        import akshare as ak
        df = run_with_timeout(ak.futures_spot_price_previous, timeout=30)
        commodities = []
        if df is None:
            raise TimeoutError("futures_spot_price_previous 超时")
        for _, row in df.iterrows():
            name = str(row.get("\u5546\u54c1", "")).strip()
            spot = float(row.get("\u73b0\u8d27\u4ef7\u683c", 0) or 0)
            future = float(row.get("\u4e3b\u529b\u5408\u7ea6\u4ef7\u683c", 0) or 0)
            change_pct = float(row.get("\u4e3b\u529b\u5408\u7ea6\u53d8\u52a8\u767e\u5206\u6bd4", 0) or 0)
            basis = spot - future if spot > 0 and future > 0 else 0
            basis_pct = (basis / future * 100) if future > 0 else 0
            # NaN 过滤: float(x or 0) 不滤 NaN，abs(nan)>15 恒 False 会漏进均值
            if math.isnan(spot) or math.isnan(future) or math.isnan(change_pct) or math.isnan(basis_pct):
                continue
            # 异常值过滤: 期货单日涨跌停一般 <=10-12%, 超 15% 为合约切换/除权等数据异常,
            # 不算入信号(否则 -19.6% 焦炭这类异常值会与真实行情对冲掩盖)
            if abs(change_pct) > 15 or abs(basis_pct) > 15:
                continue
            if spot > 0:
                commodities.append({"name": name, "spot": spot, "future": future,
                    "change_pct": change_pct, "basis": round(basis, 2), "basis_pct": round(basis_pct, 2)})
        with _CACHE_LOCK:
            _cache["commodities"] = commodities
            _cache["ts"] = now
        return commodities
    except Exception as e:
        print(f"  [WARN] commodity fetch failed: {e}", file=sys.stderr)
        with _CACHE_LOCK:
            return _cache.get("commodities") or []


def _fetch_pmi():
    now = time.time()
    with _CACHE_LOCK:
        if _cache["pmi"] is not None and now - _cache["ts"] < CACHE_TTL * 24:
            return _cache["pmi"]
    try:
        import akshare as ak
        df = ak.macro_china_pmi()
        # v5.6 fix: akshare PMI data is newest-first (iloc[0] = latest month)
        latest = df.iloc[0]
        # v5.6: Data is newest-first, so prev 3 months = iloc[1:4]
        prev3 = df.iloc[1:4] if len(df) >= 4 else df.iloc[1:]
        mfg = float(latest["\u5236\u9020\u4e1a-\u6307\u6570"])
        non_mfg = float(latest["\u975e\u5236\u9020\u4e1a-\u6307\u6570"])
        mfg_prev = float(prev3["\u5236\u9020\u4e1a-\u6307\u6570"].mean()) if len(prev3) > 0 else mfg
        trend = "rising" if mfg > mfg_prev + 0.3 else ("falling" if mfg < mfg_prev - 0.3 else "stable")
        pmi = {"manufacturing": mfg, "non_manufacturing": non_mfg,
               "mfg_3m_avg": round(mfg_prev, 1), "trend": trend,
               "month": str(latest.get("\u6708\u4efd", ""))}
        with _CACHE_LOCK:
            _cache["pmi"] = pmi
        return pmi
    except Exception as e:
        print(f"  [WARN] PMI fetch failed: {e}", file=sys.stderr)
        with _CACHE_LOCK:
            return _cache.get("pmi") or {"manufacturing": 50, "non_manufacturing": 50, "trend": "stable"}


def _pmi_to_score(pmi):
    mfg = pmi.get("manufacturing", 50)
    trend = pmi.get("trend", "stable")
    base = 5.0 + (mfg - 50) * 0.3
    if trend == "rising": base += 0.5
    elif trend == "falling": base -= 0.5
    return round(max(1.0, min(10.0, base)), 1)


# 上游资源型 sector：商品涨价 = 盈利利好 → L3 正向计分（高价格分=高L3）
# 中下游制造型 sector：商品涨价 = 成本压力 → L3 反向计分（高价格分=低L3）
UPSTREAM_SECTORS = {"煤炭", "钢铁", "有色金属", "贵金属", "能源化工", "石油", "农产品", "周期/资源"}


def get_sector_commodity_score(sector):
    commodities = _fetch_commodities()
    pmi = _fetch_pmi()
    if not commodities:
        return {"L3_score": 5.0, "L4_score": 5.0, "details": {"source": "no_data"}}

    sector_commodities = []
    for comm in commodities:
        name = comm["name"]
        for keyword, sectors in COMMODITY_SECTOR_MAP.items():
            if keyword in name and sector in sectors:
                sector_commodities.append(comm)
                break

    if not sector_commodities:
        l3_default = _pmi_to_score(pmi)
        return {"L3_score": l3_default, "L4_score": l3_default,
                "details": {"source": "pmi_proxy", "pmi": pmi, "commodities_found": 0}}

    scores = []
    for comm in sector_commodities:
        change = comm["change_pct"]
        if change > 5: price_score = 8.0
        elif change > 2: price_score = 6.5
        elif change > -2: price_score = 5.0
        elif change > -5: price_score = 3.5
        else: price_score = 2.0
        basis = comm["basis_pct"]
        if basis > 5: basis_score = 7.5
        elif basis > 2: basis_score = 6.0
        elif basis > -2: basis_score = 5.0
        elif basis > -5: basis_score = 4.0
        else: basis_score = 2.5
        combined = round(price_score * 0.6 + basis_score * 0.4, 1)
        scores.append(combined)

    l3_raw = statistics.mean(scores)
    # 上游资源 sector：涨价利好 → 正向；中下游制造：涨价成本压力 → 反向
    if sector in UPSTREAM_SECTORS:
        l3_score = round(max(1.0, min(10.0, l3_raw)), 1)
    else:
        l3_score = round(max(1.0, min(10.0, 10.0 - l3_raw)), 1)
    pmi_score = _pmi_to_score(pmi)
    l4_raw = (statistics.mean(scores) + pmi_score) / 2
    l4_score = round(max(1.0, min(10.0, l4_raw)), 1)

    return {"L3_score": l3_score, "L4_score": l4_score,
            "details": {"source": "akshare_live", "commodities_found": len(sector_commodities),
                       "commodities": [c["name"] for c in sector_commodities[:5]],
                       "avg_change_pct": round(statistics.mean(c["change_pct"] for c in sector_commodities), 1),
                       "pmi": pmi}}


def get_news_confirmation(sector):
    try:
        from etf_platform.data.manager import get_news
        items = get_news(sector, limit=5)
        if not items:
            return {"signal": "neutral", "confidence": 0, "summary": "\u65e0\u65b0\u95fb"}
        pos_kws = ["\u6da8\u4ef7", "\u4f9b\u4e0d\u5e94\u6c42", "\u7d27\u7f3a", "\u53bb\u5e93\u5b58", "\u9700\u6c42\u65fa\u76db", "\u6269\u4ea7", "\u7a81\u7834"]
        neg_kws = ["\u8dcc\u4ef7", "\u8fc7\u5269", "\u5e93\u5b58\u79ef\u538b", "\u9700\u6c42\u75b2\u8f6f", "\u505c\u5de5", "\u51cf\u4ea7\u8b66\u544a", "\u8d38\u6613\u6469\u64e6"]
        pos = sum(1 for i in items for k in pos_kws if k in (i.title or ""))
        neg = sum(1 for i in items for k in neg_kws if k in (i.title or ""))
        if pos > neg + 1:
            return {"signal": "confirm_tight", "confidence": min(80, 50+pos*10), "summary": f"{pos}\u6761\u5229\u597d\u4fe1\u53f7"}
        elif neg > pos + 1:
            return {"signal": "confirm_loose", "confidence": min(80, 50+neg*10), "summary": f"{neg}\u6761\u5229\u7a7a\u4fe1\u53f7"}
        else:
            return {"signal": "neutral", "confidence": 30, "summary": f"\u6df7\u6742({pos}\u5229\u597d/{neg}\u5229\u7a7a)"}
    except (KeyError, ValueError, TypeError, AttributeError, ImportError):
        return {"signal": "neutral", "confidence": 0, "summary": "\u65b0\u95fb\u4e0d\u53ef\u7528"}


def apply_live_material_scores(code, sector, existing_scores):
    commodity = get_sector_commodity_score(sector)
    news = get_news_confirmation(sector)
    # v5.6: Non-commodity sectors use PMI proxy with meaningful weight
    weight = SECTOR_COMMODITY_WEIGHT.get(sector, 0.30)
    old_l3 = existing_scores.get("L3_Material", 5.0)
    old_l4 = existing_scores.get("L4_SupplyChain", 5.0)
    new_l3 = round(old_l3 * (1 - weight) + commodity["L3_score"] * weight, 1)
    new_l4 = round(old_l4 * (1 - weight) + commodity["L4_score"] * weight, 1)
    if news["confidence"] > 50:
        nudge = 0.3 if news["signal"] == "confirm_tight" else (-0.3 if news["signal"] == "confirm_loose" else 0)
        new_l3 = round(max(1.0, min(10.0, new_l3 + nudge)), 1)
    existing_scores["L3_Material"] = new_l3
    existing_scores["L4_SupplyChain"] = new_l4
    return existing_scores