"""ETF 信号系统 - 获利信号 + 上下车判断"""
from collections import defaultdict
from ..config_loader import load_etfs
from ..analysis.causal import CausalEngine
from ..data.events import inject_events

class ProfitSignalEngine:
    def __init__(self, live=False):
        self.live = live; self.realtime = {}
        self.engine = CausalEngine(); inject_events(self.engine, verbose=False)
        self.signals = []; self.pair_trades = []; self.warnings = []
    def scan_event_signals(self):
        import time
        results = self.engine.scan_all()
        etfs = load_etfs()
        for event in self.engine.events:
            now = time.time(); age_hours = (now - event.timestamp) / 3600
            freshness = max(0, 1.0 - age_hours / max(event.duration_days * 24, 1))
            if freshness < 0.2: continue
            affected = {}
            for code, data in results.items():
                for path in data.get("paths", []):
                    if event.title in path.get("event", ""): affected[code] = data; break
            if not affected and event.affected_sectors:
                for code in etfs:
                    if code not in results: continue
                    for s in event.affected_sectors:
                        if s in etfs[code].get("sector", ""): affected[code] = results[code]; break
            for code, impact_data in affected.items():
                abs_impact = abs(impact_data.get("total_impact", 0))
                impact_norm = min(abs_impact * 500, 0.8)
                signal_strength = freshness * max(impact_norm, 0.05)
                if signal_strength < 0.02: continue
                priced_in = getattr(event, "priced_in", 0.0)
                effective_dir = event.direction * (-1.0 if priced_in > 0.5 else 1.0)
                direction = "SHORT" if effective_dir < -0.1 else ("LONG" if effective_dir > 0.1 else "NEUTRAL")
                if direction == "SHORT" and any(kw in event.title for kw in ["芯片","半导体","管制"]): direction = "LONG"
                if direction == "LONG" and any(kw in event.title for kw in ["预算","预期","降准"]): direction = "SHORT"
                self.signals.append({"code": code, "name": etfs[code]["name"], "sector": etfs[code].get("sector",""),
                    "direction": direction, "strength": round(signal_strength, 4),
                    "freshness": round(freshness, 2), "event": event.title, "impact": round(abs_impact, 4)})
    def run_all(self):
        print("=" * 60)
        print("  获利信号引擎")
        print("=" * 60)
        self.scan_event_signals()
        self.signals.sort(key=lambda x: x["strength"], reverse=True)
        print(f"  {len(self.signals)} signals found")
        self._print_report()
        return {"signals": self.signals}
    def _print_report(self):
        short_scores = defaultdict(float); long_scores = defaultdict(float)
        for s in self.signals:
            if s["direction"] == "SHORT": short_scores[s["code"]] += s["strength"]
            elif s["direction"] == "LONG": long_scores[s["code"]] += s["strength"]
        net = {}
        for code in set(list(short_scores.keys()) + list(long_scores.keys())):
            n = long_scores.get(code,0) - short_scores.get(code,0)
            if abs(n) > 0.03: net[code] = n
        etfs = load_etfs()
        print("  TOP LONG:")
        for code, s in sorted([(c,v) for c,v in net.items() if v>0], key=lambda x:-x[1])[:5]:
            print(f"    {code} {etfs.get(code,{}).get('name',code)} {s:.4f}")
        print("  TOP SHORT:")
        for code, s in sorted([(c,-v) for c,v in net.items() if v<0], key=lambda x:-x[1])[:5]:
            print(f"    {code} {etfs.get(code,{}).get('name',code)} {-s:.4f}")
    def get_top_signals(self, n=10):
        if not self.signals: self.scan_event_signals()
        short = defaultdict(float); long = defaultdict(float)
        for s in self.signals:
            if s["direction"] == "SHORT": short[s["code"]] += s["strength"]
            elif s["direction"] == "LONG": long[s["code"]] += s["strength"]
        results = []; etfs = load_etfs()
        for code in set(list(short.keys()) + list(long.keys())):
            net = long.get(code,0) - short.get(code,0)
            if abs(net) > 0.03:
                results.append({"code": code, "name": etfs.get(code,{}).get("name",code),
                    "net_signal": round(net,4), "direction": "LONG" if net>0 else "SHORT"})
        results.sort(key=lambda x: -abs(x["net_signal"]))
        return results[:n]
