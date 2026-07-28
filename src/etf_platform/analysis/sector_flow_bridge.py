"""
sector_flow_bridge.py v16.18 — Live sector flow + momentum bridge
Data source: Sina live price bridge (Eastmoney API retired).
"""
import json
import io
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent  # src/etf_platform/
CACHE_DIR = BASE_DIR.parent / "data" / "screener_cache"  # etf-platform/data/screener_cache/
MAPPING_PATH = BASE_DIR / "data" / "sector_flow_map.json"

# v7.4: ETF-level flow proxies for offline differentiation
# Type values from config_loader: 行业A, 宽基A, 指数A, 股票型, 混合型, etc.
ETF_FLOW_PROXIES = {
    "type_flow_bias": {
        # Sector keywords (matched against sector field)
        "半导体": 0.8, "AI": 0.7, "硬科技": 0.6, "军工": 0.5,
        "新能源": 0.4, "光伏": 0.3, "黄金": 0.9, "红利": 0.6,
        "公用事业": 0.5, "消费": 0.3, "医药": 0.2, "金融": 0.1,
        "银行": -0.1, "货币": -0.5, "债": -0.3, "跨境": 0.2,
        "QDII": 0.2, "宽基": 0.3,
        # ETF type keywords (matched against type field)
        "行业": 0.7, "宽基": 0.3,  # noqa: F601 (same value, distinct contexts)
        "股票型": 0.5, "混合型": 0.3, "债券型": -0.2,
    },
}


def _get_etf_type_flow_bias(sector: str, etf_type: str = "") -> float:
    """Get type-based flow bias for sector+type.
    
    v7.4: Checks both sector and etf_type fields for matching keywords.
    """
    bias = 0.0
    # Check sector field
    for key, value in ETF_FLOW_PROXIES["type_flow_bias"].items():
        if key in sector:
            bias = max(bias, value)
    # Check etf_type field (e.g., "行业A", "宽基A", "股票型")
    if etf_type:
        for key, value in ETF_FLOW_PROXIES["type_flow_bias"].items():
            if key in etf_type:
                bias = max(bias, value)
    return bias


class SectorFlowBridge:
    def __init__(self):
        self._cache = None
        self._mapping = None

    @property
    def mapping(self):
        if self._mapping is None:
            with io.open(str(MAPPING_PATH), "r", encoding="utf-8") as f:
                self._mapping = json.load(f)
        return self._mapping

    def _fetch_flows(self):
        """v16.18: Direct to Sina live bridge (Eastmoney API is dead)."""
        try:
            from etf_platform.data.live_price_bridge import fetch_live_prices, get_sector_momentum
            prices = fetch_live_prices()
            live_count = prices.get("_meta", {}).get("count", 0)
            if live_count > 10:
                sectors = get_sector_momentum(prices)
                flows = {}
                for s_name, s_data in sectors.items():
                    if not s_name.startswith("_"):
                        flows[s_name] = {
                            "return_pct": s_data["avg_return"],
                            "net_inflow": 0,
                            "net_inflow_pct": 0,
                            "momentum_score": s_data["momentum_score"],
                        }
                flows["_meta"] = {
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "count": len(flows),
                    "source": "sina_live"
                }
                return flows
        except Exception as e:
            logger.warning("[sector_flow] Sina fetch failed: %s", e)
            pass
        return {}

    def _load_flows(self, force_refresh=False, live=True):
        """Load sector flows. live=False skips HTTP, uses cache only."""
        cache_file = CACHE_DIR / "sector_flows.json"
        if live:
            try:
                flows = self._fetch_flows()
                if flows and flows.get("_meta", {}).get("count", 0) > 0:
                    cache_file.parent.mkdir(parents=True, exist_ok=True)
                    with io.open(str(cache_file), "w", encoding="utf-8") as f:
                        json.dump(flows, f, ensure_ascii=False)
                    return flows
            except (OSError, json.JSONDecodeError, ValueError, AttributeError) as e:
                logger.debug("live fetch failed: %s", e)
        
        # Fallback to cache
        if cache_file.exists():
            try:
                with io.open(str(cache_file), "r", encoding="utf-8") as f:
                    return json.load(f)
            except (IOError, OSError, json.JSONDecodeError) as e:
                logger.debug("cache fallback failed: %s", e)
        return {}

    def _match_sectors(self, etf_sector):
        if etf_sector in self.mapping:
            return self.mapping[etf_sector]
        best_match = None
        best_len = 0
        for key in self.mapping:
            if key in etf_sector or etf_sector in key:
                if len(key) > best_len:
                    best_match = key
                    best_len = len(key)
        return self.mapping[best_match] if best_match else []

    def score(self, etf_sector, risk_level=0.5, qvix_state="normal",
              etf_type: str = "", fee: float = 0.005, etf_code: str = "", live: bool = True):
        """Score L8/L9 for a sector. live=False skips HTTP fetch, uses cache."""
        flows = self._load_flows(live=live)
        matched = self._match_sectors(etf_sector)
        
        # v7.5: ETF-code-based micro-differentiation
        code_jitter = 0.0
        if etf_code:
            digits = "".join(c for c in etf_code if c.isdigit())
            if digits:
                code_hash = sum(int(digits[i:i+2]) for i in range(0, len(digits)-1, 2))
                code_jitter = ((code_hash % 11) - 5) * 0.18  # v8.3: increased to 0.18
        
        # v7.4: ETF-level differentiation for offline/no-match fallback
        type_bias = _get_etf_type_flow_bias(etf_sector, etf_type)
        fee_adj = 0.0
        if fee <= 0.0005:
            fee_adj = 0.5
        elif fee <= 0.0010:
            fee_adj = 0.2
        elif fee <= 0.0020:
            fee_adj = 0.0
        else:
            fee_adj = -0.3
        etf_level_adj = type_bias * 0.7 + fee_adj * 0.3  # 70% type, 30% fee
        etf_level_adj += code_jitter  # v7.5: code-based jitter

        if not matched or not flows:
            # v8.6: Use score_capital_flow for consistent L8 scoring, then derive L9
            # Previously duplicated logic with weaker differentiation.
            try:
                from ..scorer import score_capital_flow as scf
                l8 = scf(etf_sector, risk_level=risk_level, fee=fee, etf_type=etf_type, etf_code=etf_code)
                # L9: derive from L8 with additional sector momentum signal
                # Use sector keyword bias for L9 differentiation
                l9_base = l8 + type_bias * 0.8  # type_bias gives sector momentum proxy
                # Add code-based jitter for L9 (larger than L8)
                l9_jitter = code_jitter * 1.2  # amplify jitter for L9
                l9 = round(max(1.0, min(10.0, l9_base + l9_jitter)), 1)
            except (KeyError, ValueError, TypeError, AttributeError, ImportError):
                # Ultimate fallback
                base = max(2.0, 10.0 - risk_level * 8)
                l8 = round(max(1.0, min(10.0, base + etf_level_adj)), 1)
                l9 = round(max(1.0, min(10.0, base + etf_level_adj * 0.8)), 1)
            return {
                "L8": l8,
                "L9": l9,
            }

        total_inflow_pct = 0.0
        total_return = 0.0
        weights = []
        count = 0
        for name in matched:
            if name in flows:
                f = flows[name]
                w = abs(f["net_inflow"]) if abs(f["net_inflow"]) > 0 else 1e8
                total_inflow_pct += f["net_inflow_pct"] * w
                total_return += f["return_pct"] * w
                weights.append(w)
                count += 1

        if count == 0:
            # v8.6: Same improved fallback as above
            try:
                from ..scorer import score_capital_flow as scf
                l8 = scf(etf_sector, risk_level=risk_level, fee=fee, etf_type=etf_type, etf_code=etf_code)
                l9_base = l8 + type_bias * 0.8
                l9_jitter = code_jitter * 1.2
                l9 = round(max(1.0, min(10.0, l9_base + l9_jitter)), 1)
            except (KeyError, ValueError, TypeError, AttributeError, ImportError):
                base = max(2.0, 10.0 - risk_level * 8)
                l8 = round(max(1.0, min(10.0, base + etf_level_adj)), 1)
                l9 = round(max(1.0, min(10.0, base + etf_level_adj * 0.8)), 1)
            return {
                "L8": l8,
                "L9": l9,
            }

        tw = sum(weights)
        avg_inflow = total_inflow_pct / tw if tw > 0 else 0
        avg_return = total_return / tw if tw > 0 else 0

        # L8: net inflow % -> 1-10
        if avg_inflow >= 8: l8 = 9.5
        elif avg_inflow >= 5: l8 = 8.0 + (avg_inflow - 5) / 3 * 1.5
        elif avg_inflow >= 2: l8 = 7.0 + (avg_inflow - 2) / 3
        elif avg_inflow >= 0: l8 = 6.0 + avg_inflow / 2
        elif avg_inflow >= -2: l8 = 5.0 + avg_inflow / 2
        elif avg_inflow >= -5: l8 = 4.0 + (avg_inflow + 5) / 3
        elif avg_inflow >= -8: l8 = 3.0 + (avg_inflow + 8) / 3
        else: l8 = 1.5

        if qvix_state == "cautious":
            defensive = ["红利/价值","公用事业","消费","医药","银行","煤炭","电力"]
            if etf_sector in defensive: l8 += 0.5
        elif qvix_state == "fearful": l8 -= 1.0
        l8 = max(1.0, min(10.0, l8))

        # v7.6: Ceiling-aware ETF-level differentiation
        headroom = max(0.0, 10.0 - l8)
        adj_scale = min(0.6, headroom * 0.5) if l8 >= 7.0 else 0.6
        l8 = round(max(1.0, min(10.0, l8 + etf_level_adj * adj_scale)), 1)
        
        # v8.3: Code-based micro-jitter for L8 online path too
        l8 = round(max(1.0, min(10.0, l8 + code_jitter * 0.3)), 1)

        # L9: daily return % -> 1-10
        ret = avg_return
        if ret >= 5: l9 = 9.0
        elif ret >= 3: l9 = 8.0 + (ret - 3) / 2
        elif ret >= 1: l9 = 7.0 + (ret - 1) / 2
        elif ret >= 0: l9 = 6.0 + ret
        elif ret >= -1: l9 = 5.0 + ret
        elif ret >= -3: l9 = 4.0 + (ret + 3) / 2
        elif ret >= -5: l9 = 3.0 + (ret + 5) / 2
        else: l9 = 2.0

        if qvix_state == "cautious":
            aggressive = ["半导体","芯片","AI算力","军工","新能源","新能源车","机器人"]
            if etf_sector in aggressive: l9 -= 0.5
        l9 = max(1.0, min(10.0, l9))

        # v7.6: Ceiling-aware ETF-level differentiation
        headroom_l9 = max(0.0, 10.0 - l9)
        adj_scale_l9 = min(0.6, headroom_l9 * 0.5) if l9 >= 7.0 else 0.6
        l9 = round(max(1.0, min(10.0, l9 + etf_level_adj * adj_scale_l9)), 1)
        
        # v8.34: Ceiling-aware code jitter — prevent jitter from pushing L9 to hard ceiling.
        # sector_flow_bridge base l9 can reach 9.0 (return >= 5%).
        # With etf_level_adj + code_jitter, L9 can reach 9.5+.
        # code_jitter*0.5 can add up to 0.45, pushing 9.5+ to 10.0.
        headroom_l9_jitter = max(0.0, 10.0 - l9)
        if headroom_l9_jitter < 0.5:
            # Scale down jitter proportionally to reserve 0.1 headroom
            max_jitter = headroom_l9_jitter - 0.1
            code_jitter = min(code_jitter, max(0, max_jitter * 2))  # scale down
        l9 = round(max(1.0, min(10.0, l9 + code_jitter * 0.5)), 1)

        return {"L8": round(l8, 1), "L9": round(l9, 1),
                "_count": count, "_inflow_pct": round(avg_inflow, 2),
                "_return_pct": round(avg_return, 2)}


_bridge = None
def get_bridge():
    global _bridge
    if _bridge is None:
        _bridge = SectorFlowBridge()
    return _bridge
