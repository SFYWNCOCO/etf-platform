"""L22 Valuation Penalty Layer — PE/PB/Dividend Yield based valuation filter.

核心逻辑：高估值 ETF 应受到综合分惩罚，低估值 ETF 可获适当加分。
数据来源：akshare + 缓存文件 (data/etf_valuation.json)
输出层：L22_Valuation (0-10), L22_PENALTY (额外扣减，-3到+1.5)
"""
import json
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent / "data"
CACHE_FILE = BASE_DIR / "etf_valuation.json"

# 各行业/宽基ETF合理PE区间 (简化阈值)
VALUATION_BUCKETS = {
    # 宽基/稳健类 (低估值优先)
    "沪深": {"pe_floor": 8, "pe_ceil": 25, "pb_floor": 0.8, "pb_ceil": 3.5},
    "中证": {"pe_floor": 8, "pe_ceil": 25, "pb_floor": 0.8, "pb_ceil": 3.5},
    "上证": {"pe_floor": 8, "pe_ceil": 25, "pb_floor": 0.8, "pb_ceil": 3.5},
    "创业板": {"pe_floor": 25, "pe_ceil": 60, "pb_floor": 3.0, "pb_ceil": 7.0},
    "科创板": {"pe_floor": 30, "pe_ceil": 80, "pb_floor": 3.5, "pb_ceil": 9.0},
    "红利": {"pe_floor": 5, "pe_ceil": 20, "pb_floor": 0.5, "pb_ceil": 2.0},
    "债券": {"pe_floor": None, "pe_ceil": None, "pb_floor": None, "pb_ceil": None},  # 不适用
    # 行业类
    "科技": {"pe_floor": 30, "pe_ceil": 80, "pb_floor": 3.0, "pb_ceil": 8.0},
    "半导体": {"pe_floor": 25, "pe_ceil": 70, "pb_floor": 2.5, "pb_ceil": 7.0},
    "AI": {"pe_floor": 25, "pe_ceil": 70, "pb_floor": 2.5, "pb_ceil": 7.0},
    "创新药": {"pe_floor": 20, "pe_ceil": 60, "pb_floor": 2.0, "pb_ceil": 6.0},
    "医药": {"pe_floor": 15, "pe_ceil": 50, "pb_floor": 1.5, "pb_ceil": 5.0},
    "消费": {"pe_floor": 20, "pe_ceil": 50, "pb_floor": 3.0, "pb_ceil": 8.0},
    "金融": {"pe_floor": 4, "pe_ceil": 18, "pb_floor": 0.4, "pb_ceil": 2.0},
    "银行": {"pe_floor": 4, "pe_ceil": 12, "pb_floor": 0.3, "pb_ceil": 1.5},
    "券商": {"pe_floor": 15, "pe_ceil": 40, "pb_floor": 1.0, "pb_ceil": 3.0},
    "军工": {"pe_floor": 40, "pe_ceil": 100, "pb_floor": 3.0, "pb_ceil": 10.0},
    "新能源": {"pe_floor": 20, "pe_ceil": 60, "pb_floor": 2.0, "pb_ceil": 6.0},
    "光伏": {"pe_floor": 10, "pe_ceil": 40, "pb_floor": 1.5, "pb_ceil": 5.0},
    "有色": {"pe_floor": 10, "pe_ceil": 30, "pb_floor": 1.0, "pb_ceil": 4.0},
    "能源": {"pe_floor": 5, "pe_ceil": 20, "pb_floor": 0.5, "pb_ceil": 2.5},
    "黄金": {"pe_floor": 10, "pe_ceil": 25, "pb_floor": 1.0, "pb_ceil": 4.0},
    "稀土": {"pe_floor": 15, "pe_ceil": 40, "pb_floor": 1.5, "pb_ceil": 5.0},
    "通信": {"pe_floor": 20, "pe_ceil": 50, "pb_floor": 2.0, "pb_ceil": 6.0},
    "基建": {"pe_floor": 6, "pe_ceil": 18, "pb_floor": 0.6, "pb_ceil": 2.0},
}


def _match_bucket(sector: str, name: str) -> dict:
    """根据 sector/name 匹配估值分桶."""
    text = f"{sector} {name}".lower()
    for key, bucket in VALUATION_BUCKETS.items():
        if key.lower() in text:
            return bucket.copy()
    return {"pe_floor": 15, "pe_ceil": 45, "pb_floor": 1.0, "pb_ceil": 4.0}


def _score_pe(pe: float | None, bucket: dict) -> float:
    """PE 评分：偏低更好，过高惩罚."""
    if pe is None or pe <= 0:
        return 5.0
    floor = bucket.get("pe_floor", 10)
    ceil = bucket.get("pe_ceil", 50)
    mid = (floor + ceil) / 2
    # 中位附近最佳, 偏离越远越差
    ratio = (pe - mid) / max(mid - floor, 1)
    # 映射到 1-10, 中位=8, 极端=2
    score = 8.0 - abs(ratio) * 2.5
    return round(max(1.0, min(10.0, score)), 1)


def _score_pb(pb: float | None, bucket: dict) -> float:
    """PB 评分：类似 PE."""
    if pb is None or pb <= 0:
        return 5.0
    floor = bucket.get("pb_floor", 0.5)
    ceil = bucket.get("pb_ceil", 4.0)
    mid = (floor + ceil) / 2
    ratio = (pb - mid) / max(mid - floor, 0.1)
    score = 8.0 - abs(ratio) * 2.5
    return round(max(1.0, min(10.0, score)), 1)


def compute_valuation_layer(code: str, sector: str, name: str,
                            info: dict | None = None) -> dict:
    """
    计算估值惩罚层.
    
    Returns:
        {"L22_Valuation": score, "L22_PENALTY": penalty, "valuation_details": {...}}
    """
    result = {
        "L22_Valuation": 5.0,
        "L22_PENALTY": 0.0,
        "valuation_details": {},
    }
    
    try:
        bucket = _match_bucket(sector, name)
        info = info or {}
        
        # PE
        pe = info.get("pe_ratio", info.get("PE", None))
        pe_score = _score_pe(pe, bucket) if pe else 5.0
        
        # PB
        pb = info.get("pb_ratio", info.get("PB", None))
        pb_score = _score_pb(pb, bucket) if pb else 5.0
        
        # Dividend yield bonus (divided by risk_level, dividend_yield=3%+)
        div_yield = info.get("dividend_yield", 0.0)
        if div_yield > 3.0:
            div_bonus = min(div_yield * 0.2, 2.0)
        elif div_yield > 1.0:
            div_bonus = min(div_yield * 0.1, 0.8)
        else:
            div_bonus = 0.0
        
        val_score = (pe_score + pb_score + div_bonus) / 3.0
        
        # 估值惩罚: 高分ETF(>8)或低分ETF(<3)都产生penalty
        # 高PE行业ETF惩罚更大
        overvalued_penalty = max(0, (pe_score - 5.0)) * 0.15 if pe else 0
        undervalued_bonus = min(0, (pe_score - 5.0)) * 0.2 if pe else 0
        net_penalty = round(undervalued_bonus - overvalued_penalty, 2)
        
        result["L22_Valuation"] = round(val_score, 1)
        result["L22_PENALTY"] = net_penalty
        result["valuation_details"] = {
            "pe": round(pe, 1) if pe else None,
            "pe_score": pe_score,
            "pb": round(pb, 1) if pb else None,
            "pb_score": pb_score,
            "dividend_yield": round(div_yield, 2),
            "bucket": list(bucket.keys()),
            "net_penalty": net_penalty,
        }
    except Exception as e:
        logger.warning(f"L22_Valuation failed for {code}: {e}")
        result["L22_Valuation"] = 5.0
        result["L22_PENALTY"] = 0.0
    
    return result


def load_valuation_cache(code: str = None) -> dict:
    """从缓存加载估值数据,用于批量处理."""
    if not CACHE_FILE.exists():
        return {}
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        if code:
            return data.get(code, {})
        return data
    except Exception:
        return {}
