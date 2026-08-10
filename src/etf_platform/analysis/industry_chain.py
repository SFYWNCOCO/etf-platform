#!/usr/bin/env python3
"""
industry_chain.py — 产业链传导 v1.0 (d751 ③)

来源 d751: 新闻情绪存在地理/产业链外部性——上游新闻传导到中游/下游 ETF。
独立模块，不依赖 traded_news_filter / auto_sentiment。
sector 名对齐 auto_sentiment.SECTOR_KEYWORDS / news_sentiment.json。
"""
from __future__ import annotations

# 产业链传导表: 上游→下游。每个节点含 related(相关)/downstream(下游)/upstream(上游需求)。
INDUSTRY_CHAIN: dict[str, dict[str, dict[str, list[str] | str]]] = {
    "上游资源": {
        "碳酸锂/锂矿": {"related": ["新能源", "有色金属"], "downstream": ["汽车", "新能源"], "note": "锂价上涨→电池成本→新能源车"},
        "稀土": {"related": ["有色金属", "军工"], "downstream": ["军工", "机器人/智造"]},
        "铜": {"related": ["有色金属", "基建/地产"], "downstream": ["基建/地产", "新能源"]},
        "原油/天然气": {"related": ["能源化工"], "downstream": ["能源化工", "化工"]},
        "煤炭": {"related": ["能源化工"], "downstream": ["能源化工", "电力"]},
    },
    "中游制造": {
        "半导体设备": {"related": ["半导体"], "downstream": ["半导体", "AI算力"]},
        "光伏组件": {"related": ["新能源"], "downstream": ["新能源"]},
        "电池/储能": {"related": ["新能源"], "downstream": ["汽车", "新能源"]},
    },
    "下游需求": {
        "新能源车销量": {"related": ["汽车"], "upstream": ["新能源", "有色金属"]},
        "手机出货": {"related": ["消费电子"], "upstream": ["半导体", "消费电子"]},
    },
}

# 传导强度降级: 原始强→传导中, 原始中→传导弱, 弱→不传导
_STRENGTH_DEGRADE = {"强": "中", "中": "弱", "弱": None}
_STRENGTH_RANK = {"强": 3, "中": 2, "弱": 1}


def _match(sector: str, target: str) -> bool:
    """sector 与链上目标匹配: 精确或包含（复用 macro_overlay 的 key in sector or sector in key）。"""
    if not sector or not target:
        return False
    return sector == target or (target in sector or sector in target)


def propagate_signal(sector: str, direction: str, strength: str) -> list[dict]:
    """某 sector 的原始信号沿产业链传导到相关 sector。

    Args:
        sector: 板块名，如 "新能源"
        direction: 看多/看空（中性不传导）
        strength: 强/中/弱（弱不传导，强→传导中，中→传导弱）

    Returns:
        [{sector, direction, strength, propagation, note}]，同一 sector 多条链路只保留强度最高者。
    """
    if direction not in ("看多", "看空"):
        return []
    new_strength = _STRENGTH_DEGRADE.get(strength)
    if new_strength is None:
        return []

    hits: list[dict] = []
    for nodes in INDUSTRY_CHAIN.values():
        for chain in nodes.values():
            for targets in chain.values():
                if not isinstance(targets, list):
                    continue
                if not any(_match(sector, t) for t in targets):
                    continue
                for t in targets:
                    if _match(sector, t):
                        continue
                    hits.append({
                        "sector": t,
                        "direction": direction,
                        "strength": new_strength,
                        "propagation": "下游传导",
                        "note": chain.get("note", "") if isinstance(chain.get("note"), str) else "",
                    })

    # 去重: 同一 sector 多条链路只保留一条（传导强度由原始 strength 唯一决定）
    seen: dict[str, dict] = {}
    for h in hits:
        if h["sector"] not in seen:
            seen[h["sector"]] = h
    return list(seen.values())


def apply_chain_to_signals(signals: dict) -> dict:
    """对 news_sentiment.json sectors 结构做产业链传导合并。

    原信号保留且优先；传导信号标记 source="chain:下游传导"。
    多条传导到达同一 sector 时保留强度最高者。
    """
    result = dict(signals)
    for sector, info in signals.items():
        if not isinstance(info, dict):
            continue
        direction = info.get("direction", "")
        strength = info.get("strength", "")
        if direction not in ("看多", "看空"):
            continue
        for p in propagate_signal(sector, direction, strength):
            target = p["sector"]
            existing = result.get(target)
            if existing is not None:
                if not isinstance(existing, dict) or not str(existing.get("source", "")).startswith("chain:"):
                    continue  # 原信号优先，不覆盖
                if _STRENGTH_RANK.get(existing.get("strength", ""), 0) >= _STRENGTH_RANK.get(p["strength"], 0):
                    continue  # 已有同等/更强传导
            result[target] = {
                "direction": p["direction"],
                "strength": p["strength"],
                "source": "chain:下游传导",
                "note": p.get("note", ""),
            }
    return result


if __name__ == "__main__":
    for sec, direction, strength in [("新能源", "看多", "强"), ("新能源", "看空", "中"), ("军工", "看多", "中")]:
        print(f"propagate_signal({sec}, {direction}, {strength}) = {propagate_signal(sec, direction, strength)}")
