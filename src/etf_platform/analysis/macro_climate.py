"""
macro_climate.py - Macro climate → L10 B2B demand adjustment
=============================================================
Replaces static B2B_DEMAND_CLIMATE with PMI/social-financing/M2-driven
macro adjustment factor. Updates monthly with cache.

PMI < 50 → contraction → cyclical sectors get demand penalty
Social financing ↓ → tight credit → capital-intensive sectors get penalty
PPI ↓ → deflation → commodity sectors get penalty
"""
import json
import io
import logging
from datetime import datetime
from pathlib import Path

from ..utils.thread_timeout import run_with_timeout

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent.parent.parent.parent / "data" / "screener_cache"

CYCLICAL_SECTORS = ["半导体","芯片","新能源","新能源车","光伏","风电","化工","有色金属","钢铁","煤炭"]
CAPITAL_SECTORS = ["房地产","基建","金融","银行","保险","证券"]
COMMODITY_SECTORS = ["有色金属","钢铁","煤炭","化工","石油石化"]

def _fetch_pmi():
    """Latest PMI. <50 = contraction."""
    try:
        import akshare as ak
        df = run_with_timeout(ak.macro_china_pmi_yearly, timeout=30)
        if df is None:
            return 50.0
        last = df.dropna(subset=["今值"]).tail(1)
        if not last.empty:
            return float(last.iloc[0]["今值"])
    except Exception as e:
        logger.debug("PMI fetch failed: %s", e)
        pass
    return 50.0  # neutral default

def _fetch_social_financing():
    """Latest social financing (亿元)."""
    try:
        import akshare as ak
        df = run_with_timeout(ak.macro_china_shrzgm, timeout=30)
        if df is None:
            return 30000
        last = df.tail(3)
        vals = [float(last.iloc[i]["社会融资规模增量"]) for i in range(len(last))]
        return sum(vals) / len(vals)  # 3-month avg
    except Exception as e:
        logger.debug("social financing fetch failed: %s", e)
        pass
    return 30000  # neutral default

def get_macro_adjustment(force_refresh=False):
    """Returns {sector_type: adjustment_factor} where 1.0=neutral."""
    cache_file = CACHE_DIR / "macro_climate.json"
    if not force_refresh and cache_file.exists():
        try:
            with io.open(str(cache_file), "r", encoding="utf-8") as f:
                data = json.load(f)
            cached_date = data.get("_date", "")
            if cached_date == datetime.now().strftime("%Y-%m"):
                return data
        except (IOError, OSError, json.JSONDecodeError, KeyError, ValueError) as e:
            logger.debug("macro cache load failed: %s", e)
            pass

    pmi = _fetch_pmi()
    sf = _fetch_social_financing()

    # PMI adjustment: each point below 50 = 2% demand penalty for cyclical
    pmi_impact = max(-0.10, min(0.05, (pmi - 50) * 0.02))
    # SF adjustment: below 20k = tight, above 40k = loose
    sf_impact = max(-0.08, min(0.05, (sf - 30000) / 30000 * 0.05))

    adjustments = {
        "_date": datetime.now().strftime("%Y-%m"),
        "_pmi": pmi,
        "_sf_3m_avg": sf,
        "_pmi_impact": round(pmi_impact, 3),
        "_sf_impact": round(sf_impact, 3),
    }

    for sector in CYCLICAL_SECTORS:
        adjustments[sector] = round(pmi_impact + sf_impact * 0.5, 3)
    for sector in CAPITAL_SECTORS:
        adjustments[sector] = round(sf_impact, 3)
    for sector in COMMODITY_SECTORS:
        adjustments[sector] = round(pmi_impact * 1.2 + sf_impact * 0.3, 3)

    # Save cache
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    with io.open(str(cache_file), "w", encoding="utf-8") as f:
        json.dump(adjustments, f, ensure_ascii=False)

    return adjustments

def apply_to_demand(sector: str, base_score: float) -> float:
    """Apply macro adjustment to L10 demand score."""
    adj = get_macro_adjustment()
    factor = adj.get(sector, 0.0)
    adjusted = base_score + factor * 5  # scale to meaningful impact
    return round(max(1.0, min(10.0, adjusted)), 1)

if __name__ == "__main__":
    adj = get_macro_adjustment(force_refresh=True)
    print(f"PMI={adj['_pmi']}, SF_3M={adj['_sf_3m_avg']:.0f}亿")
    print(f"PMI impact={adj['_pmi_impact']:.3f}, SF impact={adj['_sf_impact']:.3f}")
    for s in ["半导体","新能源车","红利/价值","金融","房地产"]:
        if s in adj:
            print(f"  {s:10s}: {adj[s]:+.3f}")