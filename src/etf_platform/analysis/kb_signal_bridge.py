"""
kb_signal_bridge.py v1.0 — KB + 事件信号 → screener 融合层

解决 SOUL v17.0 审计发现的核心问题：
- signals.py 有 ProfitSignalEngine 产出事件信号但 screener 未消费
- knowledge/ 119 条 ETF 模式信号从未注入评分流水线
- 新闻穿透层(l9_news)独立运行

用法:
  from .analysis.kb_signal_bridge import KB SignalBridge
  bridge = KB SignalBridge(profile="进取")
  l9_score = bridge.score_sector("半导体")

注入 screener:
  screener.py 的 L9_Signals 层调用 bridge.score_etf(code, sector)
  screener.py 的 L16_LiveSignals 层调用 bridge.score_live_events(code, sector)
"""
import json
import logging
from pathlib import Path
from typing import Dict, Optional
from functools import lru_cache
from .pherosome_decay import compute_pherosome_score

logger = logging.getLogger(__name__)

# 信号面配置
SIGNAL_CATEGORY_WEIGHT = {
    "消费": 0.8,
    "科技": 1.0,
    "医药": 0.7,
    "金融": 0.6,
    "军工": 1.2,
    "能源": 0.9,
    "材料": 0.8,
    "公用事业": 0.5,
    "房地产": 0.7,
    "通信": 0.9,
    "工业": 0.8,
    "可选消费": 0.8,
    "default": 0.7,
}

# L16 实时信号权重
LIVE_SIGNAL_WEIGHT = {
    "大额申购": 0.8,
    "资金流入": 0.7,
    "政策催化": 1.0,
    "技术突破": 1.2,
    "业绩超预期": 0.9,
    "地缘风险": -0.8,
    "监管收紧": -0.7,
    "估值过高": -0.6,
    "default": 0.3,
}


class KBSignalBridge:
    """知识库 + 事件信号 → 评分桥接器"""

    def __init__(self, profile: str = "均衡", kb_path: str = None):
        self.profile = profile
        if kb_path:
            self.kb_root = Path(kb_path)
        else:
            self.kb_root = Path("D:/龙虾/.openclaw/knowledge")
        self._patterns: Optional[dict] = None
        self._signal_index: Optional[Dict[str, list]] = None
        self._event_engine = None
        self._loaded = False

    def _ensure_loaded(self):
        if self._loaded:
            return
        self._load_patterns()
        self._build_index()
        self._loaded = True

    def _load_patterns(self):
        """加载 etf_signal_patterns_master.json"""
        pattern_file = self.kb_root / "meta" / "etf_signal_patterns_master.json"
        if pattern_file.exists():
            with open(pattern_file, encoding="utf-8") as f:
                self._patterns = json.load(f)
            logger.info(f"KBSignalBridge: loaded {len(self._patterns)} patterns")
        else:
            self._patterns = []
            logger.warning("KBSignalBridge: patterns file not found")

    def _build_index(self):
        """构建 sector → patterns 倒排索引"""
        self._signal_index = {}
        if not self._patterns:
            return
        # patterns 格式: [{id, source, domain, signal, trigger, direction, etf_mapping, confidence}]
        for p in self._patterns:
            # 从 source 文件名提取 sector：k056-behavioral-macro → behavioral macro
            # 跨域映射见 SCHEMA（sector 推断由 _infer_sectors 完成）
            sectors = self._infer_sectors(p)
            weight = self._category_weight(p)
            for sector in sectors:
                self._signal_index.setdefault(sector, []).append({
                    "pattern_id": p.get("id", ""),
                    "signal": p.get("signal", ""),
                    "direction": p.get("direction", "neutral"),
                    "confidence": p.get("confidence", 0.5),
                    "weight": weight,
                    "notes": p.get("notes", "")[:80],
                })

    def _infer_sectors(self, pattern: dict) -> list:
        """从 signal/trigger/etf_mapping 推断行业"""
        text = f"{pattern.get('signal','')} {pattern.get('trigger','')} "
        etf_map = pattern.get("etf_mapping", {})
        if isinstance(etf_map, dict):
            for v in etf_map.values():
                text += f" {v}"

        sectors = set()
        KEYWORDS = {
            "半导体": ["半导体", "芯片", "算力", "AI芯片"],
            "光伏": ["光伏", "太阳能", "储能", "新能源"],
            "军工": ["军工", "国防", "武器", "军事"],
            "医药": ["医药", "生物", "医疗", "疫苗"],
            "AI": ["人工智能", "AI", "机器人", "大模型"],
            "消费": ["消费", "零售", "白酒", "食品"],
            "金融": ["银行", "券商", "保险", "金融"],
            "地产": ["地产", "房地产", "REITs"],
            "能源": ["能源", "石油", "煤炭", "天然气"],
            "汽车": ["汽车", "新能源车", "电动车", "锂电"],
            "通信": ["通信", "5G", "6G", "光模块"],
            "农业": ["农业", "粮食", "种业", "养殖"],
            "黄金": ["黄金", "贵金属", "避险"],
            "债券": ["国债", "债券", "利率债"],
            "低空": ["低空", "eVTOL", "无人机"],
            "量子": ["量子", "量子计算"],
        }
        for sector, keywords in KEYWORDS.items():
            for kw in keywords:
                if kw in text:
                    sectors.add(sector)
        if not sectors:
            sectors.add("综合")
        return list(sectors)

    def _category_weight(self, pattern: dict) -> float:
        """根据 signal 领域确定类别权重"""
        domain = pattern.get("domain", "")
        weights = {
            "supply_chain_risk": 1.2,
            "behavioral_macro": 0.9,
            "esg_green_finance": 0.7,
            "risk_management": 1.0,
            "geopolitics": 1.1,
        }
        return weights.get(domain, 0.8)

    # ── 对外接口 ──────────────────────────────────

    @lru_cache(maxsize=1024)
    def score_sector(self, sector: str) -> float:
        """为 sector 计算 L9 评分（KB模式信号）——高分=强信号"""
        self._ensure_loaded()
        if not self._signal_index:
            return 5.0  # 无信号时中性

        patterns = self._signal_index.get(sector, [])
        # 也尝试模糊匹配
        if not patterns:
            for idx_sector, idx_patterns in self._signal_index.items():
                if sector in idx_sector or idx_sector in sector:
                    patterns = idx_patterns
                    break

        if not patterns:
            return 5.0

        total_weight = 0
        total_score = 0
        for p in patterns:
            confidence = p["confidence"]
            weight = p["weight"]
            direction = p["direction"]
            # 方向性加分：正向 +cfg*weight, 负向 -cfg*weight
            if "正向" in direction or "增持" in direction or "buy" in direction.lower():
                dir_factor = 1.0
            elif "反向" in direction or "减持" in direction or "sell" in direction.lower():
                dir_factor = -1.0
            else:
                dir_factor = 0.5
            score = 5.0 + dir_factor * confidence * weight * 3
            total_score += score * confidence * weight
            total_weight += confidence * weight

        if total_weight == 0:
            return 5.0
        return round(max(1.0, min(10.0, total_score / total_weight)), 1)

    @lru_cache(maxsize=2048)
    def score_etf(self, code: str, sector: str) -> float:
        """为单个 ETF 计算综合 L9 评分"""
        base = self.score_sector(sector)
        # TODO: 叠加 ETF 特定的历史表现权重
        return base

    def score_live_events(self, code: str, sector: str) -> dict:
        """为 L16 实时信号评分

        返回: {score, signals: [...], strength}
        """
        self._ensure_loaded()
        # 获取事件信号（来自 ProfitSignalEngine）
        event_signals = self._get_event_signals(code)
        # 获取新闻信号（来自 news_etf_signals）
        news_signals = self._get_news_signals(code, sector)
        # 获取实时数据中的信号
        live_signals = event_signals + news_signals

        if not live_signals:
            return {"score": 5.0, "signals": [], "strength": 0}

        total = 0
        count = 0
        for s in live_signals:
            w = LIVE_SIGNAL_WEIGHT.get(s.get("type", ""), LIVE_SIGNAL_WEIGHT["default"])
            strength = s.get("strength", 0.5)
            total += 5.0 + w * strength * 4
            count += 1

        avg = round(total / count, 1) if count else 5.0
        return {
            "score": max(1.0, min(10.0, avg)),
            "signals": live_signals,
            "strength": round(count * 0.1, 2),
        }

    def _get_event_signals(self, code: str) -> list:
        """从 ProfitSignalEngine 获取事件信号（惰性加载）"""
        if self._event_engine is None:
            try:
                from .signals import ProfitSignalEngine
                self._event_engine = ProfitSignalEngine(live=True)
            except ImportError:
                self._event_engine = False
                return []
        if self._event_engine is False:
            return []
        try:
            signals = self._event_engine.get_top_signals(50)
            return [s for s in signals if s.get("code") == code]
        except Exception:
            return []

    def _get_news_signals(self, code: str, sector: str) -> list:
        """从 news_etf_signals.json 读取 ETF 特定信号，应用 pherosome_decay 蒸发衰减（K181）。"""
        self._ensure_loaded()
        
        # Read news_etf_signals.json
        signal_file = Path(__file__).resolve().parent.parent.parent / "data" / "news_etf_signals.json"
        signals = {}
        try:
            if signal_file.exists():
                signals = json.loads(signal_file.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"_get_news_signals: failed loading {signal_file}: {e}")

        sig = signals.get(code)
        if not sig:
            return []

        result = []

        # Primary: this ETF's news signal (with pherosome decay)
        if sig.get("created_at"):
            decay = compute_pherosome_score(sig, sig.get("sector", ""))
            if decay["status"] == "active":
                strength = min(1.0, abs(decay["effective_score"]) * 2)
                result.append({
                    "type": "sector_signal",
                    "direction": sig.get("direction", "中性"),
                    "strength": round(strength, 3),
                    "source": "news_etf_signals",
                    "decay_factor": decay["factor"],
                    "elapsed_hours": decay["elapsed_hours"],
                })

        # Secondary: KB pattern signals from existing logic
        if self._patterns:
            for p in self._patterns:
                sectors = self._infer_sectors(p)
                if sector in sectors or any(s in sector for s in sectors):
                    confidence = p.get("confidence", 0.5)
                    if confidence > 0.6:
                        result.append({
                            "type": p.get("signal", "KB信号"),
                            "strength": confidence,
                            "source": p.get("id", ""),
                        })

        return result[:5]


# ── 全局单例 ──────────────────────────────────

_bridge_instance: Optional[KBSignalBridge] = None


def get_bridge(profile: str = "均衡", reset: bool = False) -> "KBSignalBridge":
    """获取全局 KB 信号桥接器（惰性初始化）"""
    global _bridge_instance
    if _bridge_instance is None or reset:
        _bridge_instance = KBSignalBridge(profile=profile)
    return _bridge_instance
