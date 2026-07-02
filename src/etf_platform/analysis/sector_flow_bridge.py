"""
sector_flow_bridge.py - L8/L9 real fund flow + momentum bridge
Replaces risk_level-derived L8/L9 with actual Eastmoney sector fund flows.
Data source: Eastmoney push2 API (496 sectors, daily).
"""
import json, io, sys, os, time
import requests
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent  # src/etf_platform/
CACHE_DIR = BASE_DIR.parent / "data" / "screener_cache"  # etf-platform/data/screener_cache/
MAPPING_PATH = BASE_DIR / "data" / "sector_flow_map.json"

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
        """Direct Eastmoney API call - no akshare dependency."""
        url = "https://push2.eastmoney.com/api/qt/clist/get"
        all_items = []
        for pn in range(1, 8):
            params = {
                "pn": str(pn), "pz": "100", "po": "1", "np": "1",
                "fltt": "2", "invt": "2", "fid": "f62", "fs": "m:90+t:2",
                "fields": "f2,f3,f12,f14,f62,f184",
                "_": str(int(time.time() * 1000))
            }
            try:
                r = requests.get(url, params=params, timeout=10)
                data = r.json()
                items = data.get("data", {}).get("diff")
                if not items:
                    break
                all_items.extend(items)
            except Exception:
                break

        flows = {}
        for item in all_items:
            name = item.get("f14", "")
            flows[name] = {
                "return_pct": float(item.get("f3", 0) or 0),
                "net_inflow": float(item.get("f62", 0) or 0),
                "net_inflow_pct": float(item.get("f184", 0) or 0),
            }
        flows["_meta"] = {"date": datetime.now().strftime("%Y-%m-%d"), "count": len(flows)}
        return flows

    def _load_flows(self, force_refresh=False):
        cache_file = CACHE_DIR / "sector_flows.json"
        if not force_refresh and cache_file.exists():
            try:
                with io.open(str(cache_file), "r", encoding="utf-8") as f:
                    data = json.load(f)
                cached_date = data.get("_meta", {}).get("date", "")
                today = datetime.now().strftime("%Y-%m-%d")
                if cached_date == today:
                    return data
            except:
                pass
        try:
            flows = self._fetch_flows()
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            with io.open(str(cache_file), "w", encoding="utf-8") as f:
                json.dump(flows, f, ensure_ascii=False)
            return flows
        except Exception as e:
            if cache_file.exists():
                with io.open(str(cache_file), "r", encoding="utf-8") as f:
                    return json.load(f)
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

    def score(self, etf_sector, risk_level=0.5, qvix_state="normal"):
        flows = self._load_flows()
        matched = self._match_sectors(etf_sector)
        if not matched or not flows:
            base = max(2.0, 10.0 - risk_level * 8)
            return {"L8": round(base, 1), "L9": round(base, 1)}

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
            base = max(2.0, 10.0 - risk_level * 8)
            return {"L8": round(base, 1), "L9": round(base, 1)}

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

        return {"L8": round(l8, 1), "L9": round(l9, 1),
                "_count": count, "_inflow_pct": round(avg_inflow, 2),
                "_return_pct": round(avg_return, 2)}

_bridge = None
def get_bridge():
    global _bridge
    if _bridge is None:
        _bridge = SectorFlowBridge()
    return _bridge