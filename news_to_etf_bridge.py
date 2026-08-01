#!/usr/bin/env python3
"""news_to_etf_bridge.py — 知识库研究→ETF信号映射 (v16.16 重建)

将 knowledge/ 中的最新研究成果映射为板块ETF信号，写入
data/news_etf_signals.json 供 pipeline._apply_kb_signals() 消费。

用法:
  python news_to_etf_bridge.py              # 使用内置信号
  python news_to_etf_bridge.py --auto       # 合并 data/news_sentiment.json 自动信号
  python news_to_etf_bridge.py --kb-scan    # 扫描 knowledge/ 自动提取

输出: data/news_etf_signals.json
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timezone

_HERE = Path(__file__).resolve().parent
_SRC = _HERE / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

SIGNAL_FILE = _HERE / "data" / "news_etf_signals.json"
AUTO_SENTIMENT_FILE = _HERE / "data" / "news_sentiment.json"


def _load_auto_sentiment() -> dict:
    """Load auto-detected sector sentiment from cron's web_search analysis.

    Format: {"updated": "ISO", "source": "...", "sectors": {sector: {direction, strength, note}}}
    Returns empty dict if file missing.
    """
    if not AUTO_SENTIMENT_FILE.exists():
        return {}
    try:
        data = json.loads(AUTO_SENTIMENT_FILE.read_text(encoding="utf-8"))
        return data.get("sectors", {})
    except (json.JSONDecodeError, OSError, KeyError):
        return {}


# ── Sector → Signal mapping (from KB k090-k105 research) ──────────
# Format: {sector: {news_score, bullish, bearish, total_events, direction, strength}}
# news_score = (bullish - bearish) / total_events * strength_factor
# Update this dict to reflect latest knowledge base research conclusions.

SECTOR_SIGNALS = {
    "半导体": {
        "bullish": 8, "bearish": 1, "total_events": 15,
        "direction": "看多", "strength": "强",
        "note": "k053: AI算力+HBM驱动半导体超级周期; 国产替代(设备/材料)加速"
    },
    "半导体设备": {
        "bullish": 8, "bearish": 1, "total_events": 15,
        "direction": "看多", "strength": "强",
        "note": "k053: 半导体设备国产替代加速; 材料零部件进口替代"
    },
    "半导体杠杆": {
        "bullish": 8, "bearish": 2, "total_events": 15,
        "direction": "看多", "strength": "强",
        "note": "带杠杆的半导体敞口，高波动"
    },
    "半导体做空": {
        "bullish": 1, "bearish": 8, "total_events": 15,
        "direction": "看空", "strength": "强",
        "note": "逆半导体方向"
    },
    "AI/科技": {
        "bullish": 7, "bearish": 2, "total_events": 14,
        "direction": "看多", "strength": "中",
        "note": "k094: AI应用层投资; k099: 量子/脑机前沿突破"
    },
    "AI算力": {
        "bullish": 7, "bearish": 2, "total_events": 14,
        "direction": "看多", "strength": "中",
        "note": "AI算力军备竞赛持续"
    },
    "云计算/算力": {
        "bullish": 7, "bearish": 2, "total_events": 14,
        "direction": "看多", "strength": "中",
        "note": "云+AI双驱动"
    },
    "硬科技": {
        "bullish": 7, "bearish": 2, "total_events": 14,
        "direction": "看多", "strength": "中",
        "note": "硬科技是政策重点方向"
    },
    "硬科技杠杆": {
        "bullish": 7, "bearish": 3, "total_events": 14,
        "direction": "看多", "strength": "中",
        "note": "带杠杆硬科技敞口"
    },
    "硬科技做空": {
        "bullish": 2, "bearish": 7, "total_events": 14,
        "direction": "看空", "strength": "中",
        "note": "逆硬科技方向"
    },
    "机器人/智造": {
        "bullish": 6, "bearish": 2, "total_events": 12,
        "direction": "看多", "strength": "中",
        "note": "特斯拉Gen3+人形量产元年"
    },
    "新能源": {
        "bullish": 6, "bearish": 4, "total_events": 15,
        "direction": "看多", "strength": "中",
        "note": "k090: 锂电强势反弹(锂价+125%), 光伏仍在出清, 储能高增"
    },
    "军工": {
        "bullish": 7, "bearish": 1, "total_events": 12,
        "direction": "看多", "strength": "强",
        "note": "k098: 全球军费飙升+AI战争+中国军贸出海"
    },
    "医药": {
        "bullish": 4, "bearish": 5, "total_events": 14,
        "direction": "看空", "strength": "中",
        "note": "k092: CXO地缘政治风险; BIOTECH法案压制未解除"
    },
    "医药器械": {
        "bullish": 4, "bearish": 5, "total_events": 14,
        "direction": "看空", "strength": "中",
        "note": "与医药板块同步"
    },
    "港股医药": {
        "bullish": 3, "bearish": 6, "total_events": 14,
        "direction": "看空", "strength": "中",
        "note": "港股医药受地缘政治影响更直接"
    },
    "中药": {
        "bullish": 5, "bearish": 3, "total_events": 10,
        "direction": "看多", "strength": "弱",
        "note": "中药政策独立于化药/生物药"
    },
    "有色金属": {
        "bullish": 6, "bearish": 3, "total_events": 12,
        "direction": "看多", "strength": "中",
        "note": "k100: 铜长期牛市; 稀土出口管制利好"
    },
    "贵金属": {
        "bullish": 7, "bearish": 2, "total_events": 10,
        "direction": "看多", "strength": "强",
        "note": "k100: 央行购金+降息预期; 黄金历史高位"
    },
    "周期/资源": {
        "bullish": 6, "bearish": 3, "total_events": 12,
        "direction": "看多", "strength": "中",
        "note": "k100: 基础材料产业链; 供给侧约束"
    },
    "能源化工": {
        "bullish": 5, "bearish": 3, "total_events": 10,
        "direction": "看多", "strength": "弱",
        "note": "能源价格受地缘政治+供给约束影响; 煤炭中枢上移"
    },
    "消费": {
        "bullish": 3, "bearish": 4, "total_events": 10,
        "direction": "看空", "strength": "弱",
        "note": "k076: 房地产周期拖累消费; k071: 人口老龄化压力"
    },
    "白酒消费": {
        "bullish": 3, "bearish": 4, "total_events": 10,
        "direction": "看空", "strength": "弱",
        "note": "消费降级+库存压力"
    },
    "食品饮料": {
        "bullish": 4, "bearish": 3, "total_events": 10,
        "direction": "中性", "strength": "弱",
        "note": "必选消费相对防御"
    },
    "家电": {
        "bullish": 4, "bearish": 2, "total_events": 8,
        "direction": "看多", "strength": "弱",
        "note": "以旧换新补贴延续利好"
    },
    "金融": {
        "bullish": 3, "bearish": 3, "total_events": 9,
        "direction": "中性", "strength": "弱",
        "note": "k069: 资本市场改革进行中; 息差收窄压力"
    },
    "券商": {
        "bullish": 4, "bearish": 2, "total_events": 8,
        "direction": "看多", "strength": "弱",
        "note": "资本市场改革利好券商"
    },
    "保险": {
        "bullish": 3, "bearish": 2, "total_events": 7,
        "direction": "中性", "strength": "弱",
        "note": "利率下行压力vs权益弹性"
    },
    "基建/地产": {
        "bullish": 2, "bearish": 5, "total_events": 10,
        "direction": "看空", "strength": "中",
        "note": "k076: 房地产长周期下行"
    },
    "公用事业": {
        "bullish": 4, "bearish": 1, "total_events": 7,
        "direction": "看多", "strength": "弱",
        "note": "防御性配置+电价改革"
    },
    "红利/价值": {
        "bullish": 5, "bearish": 1, "total_events": 8,
        "direction": "看多", "strength": "中",
        "note": "低利率环境利好高股息策略"
    },
    "红利+低波": {
        "bullish": 5, "bearish": 1, "total_events": 8,
        "direction": "看多", "strength": "中",
        "note": "防御+低利率双重利好"
    },
    "红利价值": {
        "bullish": 5, "bearish": 1, "total_events": 8,
        "direction": "看多", "strength": "中",
        "note": "红利策略持续占优"
    },
    "高股息": {
        "bullish": 5, "bearish": 1, "total_events": 8,
        "direction": "看多", "strength": "中",
        "note": "低利率驱动的确定性收益"
    },
    "通信/5G": {
        "bullish": 5, "bearish": 2, "total_events": 11,
        "direction": "看多", "strength": "中",
        "note": "AI算力+5G升级驱动"
    },
    "通信/光模块": {
        "bullish": 6, "bearish": 1, "total_events": 10,
        "direction": "看多", "strength": "强",
        "note": "800G/1.6T光模块放量"
    },
    "5G/PCB": {
        "bullish": 5, "bearish": 2, "total_events": 11,
        "direction": "看多", "strength": "中",
        "note": "5G+AI双驱动"
    },
    "中概互联网": {
        "bullish": 4, "bearish": 4, "total_events": 12,
        "direction": "中性", "strength": "弱",
        "note": "地缘政治风险vs估值修复"
    },
    "港股科技": {
        "bullish": 4, "bearish": 4, "total_events": 12,
        "direction": "中性", "strength": "弱",
        "note": "与中概同步"
    },
    "港股综合": {
        "bullish": 4, "bearish": 3, "total_events": 10,
        "direction": "中性", "strength": "弱",
        "note": "港股整体受地缘政治+流动性影响"
    },
    "跨境": {
        "bullish": 4, "bearish": 3, "total_events": 10,
        "direction": "中性", "strength": "弱",
        "note": "跨境ETF受汇率+政策影响"
    },
    "美股科技": {
        "bullish": 5, "bearish": 3, "total_events": 12,
        "direction": "看多", "strength": "中",
        "note": "AI驱动美股科技龙头"
    },
    "美股科技100": {
        "bullish": 5, "bearish": 3, "total_events": 12,
        "direction": "看多", "strength": "中",
        "note": "与美股科技同步"
    },
    "美股杠杆": {
        "bullish": 5, "bearish": 4, "total_events": 12,
        "direction": "看多", "strength": "中",
        "note": "杠杆放大美股敞口"
    },
    "美股综合": {
        "bullish": 4, "bearish": 3, "total_events": 10,
        "direction": "中性", "strength": "弱",
        "note": "美股整体"
    },
    "农产品": {
        "bullish": 4, "bearish": 3, "total_events": 9,
        "direction": "中性", "strength": "弱",
        "note": "k072: 粮食安全; 天气+关税影响"
    },
    "央企改革": {
        "bullish": 5, "bearish": 1, "total_events": 8,
        "direction": "看多", "strength": "中",
        "note": "央企市值管理+改革红利"
    },
    "宽基": {
        "bullish": 4, "bearish": 2, "total_events": 8,
        "direction": "中性", "strength": "弱",
        "note": "市场整体中性"
    },
    "大盘蓝筹": {
        "bullish": 4, "bearish": 2, "total_events": 8,
        "direction": "中性", "strength": "弱",
        "note": "防御性优于进攻性"
    },
    "全市场": {
        "bullish": 4, "bearish": 2, "total_events": 8,
        "direction": "中性", "strength": "弱",
        "note": "与宽基同步"
    },
    "成长股": {
        "bullish": 4, "bearish": 3, "total_events": 10,
        "direction": "看多", "strength": "弱",
        "note": "成长风格阶段性占优"
    },
    "中盘成长": {
        "bullish": 4, "bearish": 3, "total_events": 10,
        "direction": "看多", "strength": "弱",
        "note": "与成长股同步"
    },
    "小盘价值": {
        "bullish": 3, "bearish": 3, "total_events": 8,
        "direction": "中性", "strength": "弱",
        "note": "小盘股流动性风险"
    },
    "综合": {
        "bullish": 4, "bearish": 2, "total_events": 8,
        "direction": "中性", "strength": "弱",
        "note": "综合类ETF"
    },
    "利率债": {
        "bullish": 3, "bearish": 1, "total_events": 5,
        "direction": "看多", "strength": "弱",
        "note": "k087: 降息周期利好利率债"
    },
    "信用债": {
        "bullish": 3, "bearish": 2, "total_events": 5,
        "direction": "中性", "strength": "弱",
        "note": "信用利差低位"
    },
    "可转债": {
        "bullish": 4, "bearish": 2, "total_events": 7,
        "direction": "看多", "strength": "弱",
        "note": "权益弹性+债券底"
    },
    "货币": {
        "bullish": 2, "bearish": 0, "total_events": 3,
        "direction": "中性", "strength": "弱",
        "note": "现金等价物"
    },
    "货币基金": {
        "bullish": 2, "bearish": 0, "total_events": 3,
        "direction": "中性", "strength": "弱",
        "note": "现金等价物"
    },
}


def load_etf_sectors() -> dict[str, str]:
    """Load ETF code → sector from etfs.yaml."""
    try:
        from etf_platform.config_loader import load_etfs
        etfs = load_etfs()
        return {code: info.get("sector", "其他") for code, info in etfs.items()}
    except Exception as e:
        # Fallback: read YAML directly if config_loader fails (e.g., missing etfs.yaml in src/)
        import yaml
        cfg_file = _HERE / "config" / "etfs.yaml"
        if cfg_file.exists():
            cfg = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
            return {code: v.get("sector", "其他") for code, v in cfg.get("etfs", {}).items()}
        return {}


def _load_impact_scores() -> dict:
    """Load per-ETF impact scores from news_impact_scores.json.

    Format: {code: {direction, strength, news_score, positive_count, ...}}
    Returns {} if file missing.
    """
    IMPACT_FILE = _HERE / "data" / "news_impact_scores.json"
    if not IMPACT_FILE.exists():
        return {}
    try:
        data = json.loads(IMPACT_FILE.read_text(encoding="utf-8"))
        return data
    except (json.JSONDecodeError, OSError):
        return {}


def _build_summary(direction: str, bullish: int, bearish: int, sector: str,
                   pos_items=None, neg_items=None) -> str:
    """构建可解释的信号摘要：方向 + 数量 + 代表性新闻标题"""
    pos_items = pos_items or []
    neg_items = neg_items or []
    parts = [f"{sector}板块 {direction}"]
    parts.append(f"利好{bullish}条/利空{bearish}条")
    if pos_items:
        parts.append(f"例: {pos_items[0].get('title', '')[:40]}")
    elif neg_items:
        parts.append(f"例: {neg_items[0].get('title', '')[:40]}")
    return " | ".join(parts)


def build_signals(auto_sentiment=None, impact_scores=None) -> dict:
    """Map sector signals to individual ETF codes.

    Priority order (highest wins):
      1. impact_scores (news_impact_scores.json) — per-ETF granular evaluation
      2. auto_sentiment (news_sentiment.json) — sector-level cron analysis
      3. built-in SECTOR_SIGNALS dictionary — KB knowledge base

    Args:
        auto_sentiment: Optional sector-level sentiment dict.
        impact_scores: Optional per-ETF impact scores dict.
    """
    merged = dict(SECTOR_SIGNALS)

    # FIX 2026-08-01: fetch/auto_sentiment 层行业命名与 SECTOR_SIGNALS 不一致
    # （煤炭能源→能源化工、消费电子→消费、汽车→汽车、AI/科技→AI/科技...），
    # 直接合并会丢失信号。归一化映射到 canonical 名。
    SECTOR_NAME_ALIASES = {
        "煤炭能源": "能源化工",
        "能源": "能源化工",
        "消费电子": "消费",
        "通信": "通信/5G",
        "AI": "AI/科技",
        "AI科技": "AI/科技",
        "港股": "港股科技",
        "医药器械": "医药",
        "医疗器械": "医药",
        "红利": "红利/价值",
        "周期": "周期/资源",
    }
    if auto_sentiment:
        norm_sent = {}
        for sec, sent in auto_sentiment.items():
            canon = SECTOR_NAME_ALIASES.get(sec, sec)
            # 若 canonical 已存在且不同，合并计数；否则直接放 canonical
            if canon in norm_sent:
                old = norm_sent[canon]
                norm_sent[canon] = {
                    "direction": sent.get("direction", old.get("direction", "中性")),
                    "strength": max(sent.get("strength", "弱"), old.get("strength", "弱"), key=lambda s: {"强": 3, "中": 2, "弱": 1}[s]),
                    "note": f"{old.get('note','')} | {sent.get('note','')}",
                }
            else:
                norm_sent[canon] = sent
        auto_sentiment = norm_sent

    # Layer 2: Auto sentiment overrides sector signals
    # P2-1 修复: 中性不覆盖KB方向（避免 auto 中性抹掉 KB 看空/看多）
    if auto_sentiment:
        for sector, sent in auto_sentiment.items():
            if sector not in merged:
                merged[sector] = {"bullish": 5, "bearish": 3, "total_events": 10, "strength": "中"}
            new_dir = sent.get("direction")
            # 只有明确方向（看多/看空）才覆盖；中性保留 KB 原方向
            if new_dir in ("看多", "看空") and new_dir != merged[sector].get("direction"):
                merged[sector]["direction"] = new_dir
                if new_dir == "看多":
                    merged[sector]["bullish"] = max(merged[sector]["bullish"], merged[sector]["bearish"] + 2)
                elif new_dir == "看空":
                    merged[sector]["bearish"] = max(merged[sector]["bearish"], merged[sector]["bullish"] + 2)
            # 同向或中性时，强度取 auto 的（中性可降 KB 强信号强度）
            if new_dir == "中性" and merged[sector].get("direction") == "看多" and sent.get("strength") == "弱":
                merged[sector]["strength"] = "弱"
            elif new_dir in ("看多", "看空"):
                merged[sector]["strength"] = sent.get("strength", merged[sector].get("strength", "中"))
            if sent.get("note"):
                merged[sector]["note"] = f"[AUTO] {sent['note']}"

    etf_sectors = load_etf_sectors()
    signals = {}
    
    # Load news items for enrichment
    raw_file = _HERE / "data" / "news_raw_sources.json"
    news_items = []
    if raw_file.exists():
        try:
            news_items = json.loads(raw_file.read_text(encoding="utf-8")).get("items", [])
        except (json.JSONDecodeError, OSError):
            pass
    item_by_title = {it.get("title", ""): it for it in news_items}

    for code, sector in etf_sectors.items():
        # v16.20: filter simulated/leveraged/short ETFs
        if not (code.isdigit() and len(code) == 6):
            continue

        # Layer 1: Per-ETF impact score (highest priority ONLY if non-zero)
        # v17.0: 592条全zero impact_scores导致L9_Signals永远0 → 要求total>0才覆盖
        use_impact = False
        if impact_scores and code in impact_scores:
            imp = impact_scores[code]
            positive_count = imp.get("positive_count", 0)
            negative_count = imp.get("negative_count", 0)
            total_imp = positive_count + negative_count
            net_score = imp.get("news_score", 0.0)
            if total_imp > 0:
                use_impact = True

        if use_impact:
            direction = imp.get("direction", "中性")
            strength = imp.get("strength", "弱")

            bullish = imp.get("positive_count", 0)
            bearish = imp.get("negative_count", 0)
            total = bullish + bearish

            # Direction from impact score (overrides sector signals)
            if net_score > 0.1:
                direction = "看多"
            elif net_score < -0.1:
                direction = "看空"

            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            summary = _build_summary(direction, bullish, bearish, sector, imp.get("top_positive_signals", []), imp.get("top_negative_signals", []))
            signals[code] = {
                "sector": sector,
                "news_score": round(net_score, 4),
                "bullish": bullish,
                "bearish": bearish,
                "total_events": total,
                "direction": direction,
                "strength": strength,
                "summary": summary,
                "source": "impact_scores",
                "created_at": ts,
                "last_seen": ts,
            }
            continue

        # Fallback to sector signals
        if sector in merged:
            ss = merged[sector]
            bullish = ss["bullish"]
            bearish = ss["bearish"]
            total = ss["total_events"]
            raw = (bullish - bearish) / max(total, 1)
            # v16.22: no double sign flip — raw already directional
            strength_map = {"强": 1.5, "中": 1.0, "弱": 0.5}
            raw *= strength_map.get(ss["strength"], 1.0)

            signals[code] = {
                "sector": sector,
                "news_score": round(raw, 4),
                "bullish": bullish,
                "bearish": bearish,
                "total_events": total,
                "direction": ss["direction"],
                "strength": ss["strength"],
                "summary": ss.get("note", f"{sector}板块 {ss['direction']}"),
                "source": "sector_signal",
                "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "last_seen": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
    
    # ── v17.2: 为每只ETF附加真实新闻条目 ────────────────
    for code, sig in signals.items():
        items_list = []
        
        # From impact_scores top_positive/top_negative
        imp = impact_scores.get(code, {}) if impact_scores else {}
        pos_items = imp.get("top_positive_signals", []) or []
        neg_items = imp.get("top_negative_signals", []) or []
        
        for s in pos_items[:3]:
            title = s.get("title", "")
            raw_item = item_by_title.get(title, {})
            items_list.append({
                "type": "positive", "direction": "看多",
                "score": round(float(s.get("score", 0)), 3),
                "title": title,
                "source": s.get("source", ""),
                "category": s.get("category", ""),
            })
        
        for s in neg_items[:3]:
            title = s.get("title", "")
            raw_item = item_by_title.get(title, {})
            items_list.append({
                "type": "negative", "direction": "看空",
                "score": round(abs(float(s.get("score", 0))), 3),
                "title": title,
                "source": s.get("source", ""),
                "category": s.get("category", ""),
            })
        
        # Fallback: KB static events for sector-only signals
        if not items_list:
            sector_name = sig.get("sector", "")
            for ss_key, ss_val in SECTOR_SIGNALS.items():
                if ss_val.get("note") and sector_name in ss_key:
                    items_list.append({
                        "type": "kb_signal", "direction": sig["direction"],
                        "score": abs(round((ss_val["bullish"] - ss_val["bearish"]) / max(ss_val["total_events"], 1), 3)),
                        "title": f"[KB研究] {ss_key}：{ss_val['note'][:60]}",
                        "source": "knowledge_base",
                        "category": ss_key,
                    })
                    break
        
        sig["items"] = items_list

    return signals


def main():
    auto_sentiment = None
    impact_scores = None
    mode = "sector_only"

    for arg in sys.argv:
        if arg == "--auto":
            auto_sentiment = _load_auto_sentiment()
            n = len(auto_sentiment)
            if n > 0:
                mode = "auto"
        elif arg == "--kb-scan":
            print("news_to_etf_bridge: --kb-scan temporarily disabled, using sector signals")
        elif arg == "--impact":
            impact_scores = _load_impact_scores()
            n = len(impact_scores) if isinstance(impact_scores, dict) else 0
            if n > 0:
                mode = "impact"
            else:
                print(f"news_to_etf_bridge: impact_scores.json empty or missing")

    signals = build_signals(auto_sentiment, impact_scores)
    SIGNAL_FILE.parent.mkdir(parents=True, exist_ok=True)
    SIGNAL_FILE.write_text(
        json.dumps(signals, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    bullish_count = sum(1 for s in signals.values() if s["direction"] == "看多")
    bearish_count = sum(1 for s in signals.values() if s["direction"] == "看空")
    print(f"news_to_etf_bridge: {len(signals)} ETF信号已写入 {SIGNAL_FILE}")
    print(f"  看多: {bullish_count}  看空: {bearish_count}  中性: {len(signals) - bullish_count - bearish_count}")


if __name__ == "__main__":
    main()
