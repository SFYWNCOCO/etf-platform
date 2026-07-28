"""pherosome_decay.py — K181 Stigmergy 信息素蒸发映射（v1.0）

将蚁群信息素蒸发机制映射到 ETF 信号时效性：
  - 信息素浓度 = news_score（信号强度）
  - 信息素蒸发 = 指数衰减 e^(-λ·t)
  - TTL = 信号最大存活窗口
  - 蒸发后信号进入"半衰区"，保留残余影响但加权降级

K181 设计文档: knowledge/theory/k181-stigmergy-swarm-intelligence.md
触发: 写入 signals 时标注 created_at；读取 signals 时计算 evaporation 系数。

用法:
  python etf-platform/scripts/apply_pherosomes.py
"""

import math
import time
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

BASE = Path(__file__).resolve().parent.parent.parent
SIGNAL_FILE = BASE / "data" / "news_etf_signals.json"

# ─── 蒸发参数 ────────────────────────────────────────────────
# λ=ln(2)/T_half：半衰期后剩余 50% 影响
DEFAULT_HALF_LIFE_HOURS = 48  # 信息素半衰期：2天
MAX_TTL_HOURS = 168          # 最大存活：7天
DEFAULT_EVAPORATION_RATE = {
    "科技/AI/半导体/通信": 0.025,    # 快变行业：蒸发快（半天一阶）
    "军工": 0.030,                    # 地缘驱动：极快
    "医药": 0.020,                    # 政策驱动：中快
    "消费/金融/公用事业": 0.012,      # 慢变：蒸发慢
    "周期/资源": 0.018,               # 商品驱动：中等
    "default": 0.015,
}

# ─── 时间戳工具 ──────────────────────────────────────────────

def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_ts(ts_str: Optional[str]) -> float:
    """解析 ISO timestamp，返回 epoch seconds；无法解析则当前时间。"""
    if not ts_str:
        return time.time()
    try:
        # UTC 尾缀处理
        if ts_str.endswith("Z"):
            dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        else:
            dt = datetime.fromisoformat(ts_str)
        return dt.timestamp()
    except Exception:
        return time.time()


def hours_since(ts_str: Optional[str]) -> float:
    """信号创建至今的小时数。"""
    return max(0.0, (time.time() - _parse_ts(ts_str)) / 3600.0)


# ─── 信息素蒸发计算 ──────────────────────────────────────────

def evaporation_factor(h: float, half_life_hours: float = DEFAULT_HALF_LIFE_HOURS) -> float:
    """指数衰减因子：f(t)=e^{-λt}=2^{-t/T_{1/2}}
    
    t=0    → 1.0   （新鲜信号，满信息素浓度）
    t=T_1/2 → 0.5  （半衰期，一半影响力）
    t=2T_1/2 → 0.25（残余信号）
    t > MAX_TTL → 0.0（完全蒸发）
    """
    if h <= 0:
        return 1.0
    lam = math.log(2) / half_life_hours  # ln(2) / T_1/2
    if h >= MAX_TTL_HOURS:
        return 0.001  # 最小残余，防止全零污染下游计算
    return round(math.exp(-lam * h), 6)


def compute_pherosome_score(signal: dict, sector: str) -> float:
    """根据信号原始强度和时间衰减计算 effective score。
    
    返回: (effective_news_score, factor, metadata)
    """
    raw_score = signal.get("news_score", 0.0)
    direction = signal.get("direction", "中性")
    
    # 选择蒸发率
    rate_category = "default"
    if any(kw in sector for kw in ["科技", "AI", "半导体", "通信", "光模块"]):
        rate_category = "科技/AI/半导体/通信"
    elif "军工" in sector:
        rate_category = "军工"
    elif "医药" in sector:
        rate_category = "医药"
    elif "消费" in sector or "金融" in sector or "公用事业" in sector:
        rate_category = "消费/金融/公用事业"
    elif "周期" in sector or "资源" in sector or "有色" in sector or "能源" in sector:
        rate_category = "周期/资源"
    
    elapsed_h = hours_since(signal.get("created_at"))
    half_life = DEFAULT_HALF_LIFE_HOURS
    
    factor = evaporation_factor(elapsed_h, half_life)
    
    # 方向性调整：看多信号蒸发为中性后不再产生正向影响；看空同理
    base_value = abs(raw_score)
    if factor == 0.0:
        effective = 0.0
        status = "evaporated"
    elif base_value < 0.05:
        effective = 0.0
        status = "below_threshold"
    else:
        effective = raw_score * factor
        # 低于阈值视为中性
        if abs(effective) < 0.02:
            effective = 0.0
            status = "below_threshold"
        else:
            status = "active" if factor > 0.5 else "decaying"
    
    return {
        "raw_score": raw_score,
        "factor": factor,
        "effective_score": round(effective, 4),
        "elapsed_hours": round(elapsed_h, 1),
        "half_life_hours": half_life,
        "status": status,
        "sector_category": rate_category,
        "direction": direction,
    }


def apply_decay_to_signals(signals: dict) -> tuple[dict, dict]:
    """对 signals JSON 中的所有条目应用衰减并生成新文件。
    
    策略：原地更新，保留原始数据并追加蒸发元数据。
    旧 signal 没有 created_at → 视为刚刚创建（factor=1.0）。
    """
    out = {}
    decay_stats = {"total": 0, "evaporated": 0, "decaying": 0, "active": 0, "below_threshold": 0}
    
    for code, sig in signals.items():
        decay_stats["total"] += 1
        
        # 添加缺失的时间戳
        if "created_at" not in sig:
            sig["created_at"] = now_iso()
        
        result = compute_pherosome_score(sig, sig.get("sector", ""))
        sig["pherosome_decay"] = result
        decay_stats[result["status"]] += 1
        
        # 更新 effective news_score
        sig["news_score_effective"] = result["effective_score"]
        
        # 如果完全蒸发，可以标记 inactive；否则正常存储
        if result["status"] == "evaporated":
            sig["pherosome_status"] = "inactive"
        else:
            sig["pherosome_status"] = "active"
        
        out[code] = sig
    
    return out, decay_stats


def run_decay_check() -> None:
    """独立运行：加载、应用衰减、写回文件，打印统计。"""
    if not SIGNAL_FILE.exists():
        print(f"SIGNAL_FILE not found: {SIGNAL_FILE}")
        return
    
    with open(SIGNAL_FILE, "r", encoding="utf-8") as f:
        signals = json.load(f)
    
    new_signals, stats = apply_decay_to_signals(signals)
    
    with open(SIGNAL_FILE, "w", encoding="utf-8") as f:
        json.dump(new_signals, f, ensure_ascii=False, indent=2)
    
    print(f"✅ pherosome_decay applied to {stats['total']} signals:")
    print(f"  active: {stats['active']}, decaying: {stats['decaying']}, below_threshold: {stats['below_threshold']}, evaporated: {stats['evaporated']}")


if __name__ == "__main__":
    run_decay_check()
