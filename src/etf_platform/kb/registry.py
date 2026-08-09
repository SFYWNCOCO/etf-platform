"""KB Registry 模块：k-code 统一注册表。

目标：终结"假集成"——代码中引用的每个 k\\d{3} 都必须有登记记录
（来源 KB 文件、消费模块、集成模式、验证状态）。数据落盘到
data/kb_registry.json，首次访问时自动以内置 64 个 k-code 初始化。
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

# 本模块固定位于 src/etf_platform/kb/ 下，parents[3] 即项目根目录
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_REGISTRY_PATH = _PROJECT_ROOT / "data" / "kb_registry.json"
_DEFAULT_SRC_ROOT = _PROJECT_ROOT

_CODE_RE = re.compile(r"\bk\d{3}\b")

# 扫描时跳过的目录名：归档死模块、沙盒、缓存与数据目录
_SKIP_PARTS = {
    "_archived",
    "_archive",
    "_sandbox",
    "data_cache",
    "catboost_info",
    "__pycache__",
}

# 内置初始数据：现有代码已消费的 64 个 k-code
_BUILTIN_CODES = (
    "k001", "k002", "k003", "k004", "k005", "k006", "k007", "k008", "k009", "k010",
    "k011", "k012", "k019", "k021", "k033", "k042", "k044", "k046", "k053", "k063",
    "k069", "k071", "k072", "k076", "k087", "k089", "k090", "k091", "k092", "k094",
    "k098", "k099", "k100", "k104", "k105", "k117", "k118", "k122", "k123", "k124",
    "k125", "k126", "k127", "k129", "k130", "k131", "k180", "k186", "k187", "k191",
    "k192", "k196", "k229", "k238", "k260", "k261", "k268", "k275",
    "k168", "k169", "k170", "k189", "k190", "k295",
)

# 6 个新模块的元信息：内置种子即含 consumer，保证干净环境可复现（data/*.json 被 gitignore）
_BUILTIN_META = {
    "k168": {"title": "技术分析基础", "source_file": "knowledge/theory/k168-technical-analysis-fundamentals.md",
             "consumer": "analysis/technical_indicators.py", "mode": "data_source"},
    "k169": {"title": "量化投资绩效评估", "source_file": "knowledge/theory/k169-quant-performance-evaluation.md",
             "consumer": "analysis/performance_metrics.py", "mode": "research"},
    "k170": {"title": "资产配置模型", "source_file": "knowledge/theory/k170-asset-allocation-models.md",
             "consumer": "decision/position_allocator.py", "mode": "weight"},
    "k189": {"title": "跨资产相关性结构与危机制度", "source_file": "knowledge/theory/k189-cross-asset-correlation-and-crisis-regime.md",
             "consumer": "analysis/cross_asset_correlation.py", "mode": "layer"},
    "k190": {"title": "Hurst指数与分形市场假说", "source_file": "knowledge/theory/k190-hurst-exponent-and-fractal-market.md",
             "consumer": "analysis/hurst_regime.py", "mode": "layer"},
    "k295": {"title": "A股风格四周期框架与ETF轮动策略", "source_file": "knowledge/k295-A股风格四周期框架与ETF轮动策略.md",
             "consumer": "analysis/style_rotation.py", "mode": "signal"},
}


class KBRegistry:
    """k-code 注册表：登记每个 k-code 的来源、消费方、集成模式与状态。"""

    def __init__(self, registry_path=None):
        """加载已有注册表；文件不存在时以内置 64 个 k-code 初始化并生成数据文件。

        registry_path 为 None 时使用项目内 data/kb_registry.json。
        """
        self.path = Path(registry_path) if registry_path else _DEFAULT_REGISTRY_PATH
        self._registry: dict[str, dict] = {}
        self._load_or_seed()

    def _load_or_seed(self):
        """从数据文件加载注册表；文件缺失或损坏时回退到内置初始数据。"""
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = None
        if isinstance(data, dict):
            self._registry = {k: v for k, v in data.items() if isinstance(v, dict)}
            return
        for code in _BUILTIN_CODES:
            meta = _BUILTIN_META.get(code, {})
            self._registry[code] = {
                "code": code,
                "title": meta.get("title", "<unknown>"),
                "source_file": meta.get("source_file", "<unknown>"),
                "consumer": meta.get("consumer", "<unknown>"),
                "mode": meta.get("mode", "research"),
                "status": "active",
            }
        self._save()

    def _save(self):
        """将注册表写入数据文件，目录不存在时自动创建。

        数据目录不可写时降级为内存态：不影响审计，仅不落盘。
        """
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(self.to_json(), encoding="utf-8")
        except OSError:
            pass

    def register(self, code, title, source_file, consumer, mode, status="active"):
        """登记或更新一个 k-code 的元信息。

        mode 取值: layer|fallback|signal|weight|data_source|research
        status 取值: active|archived|pending
        """
        entry = {
            "code": code,
            "title": title,
            "source_file": source_file,
            "consumer": consumer,
            "mode": mode,
            "status": status,
        }
        self._registry[code] = entry
        self._save()
        return entry

    def get(self, code):
        """返回指定 k-code 的登记信息，未登记返回 None。"""
        return self._registry.get(code)

    def scan_codebase(self, src_root=None):
        """递归扫描 src_root 下所有 .py，提取 k-code 引用。

        src_root 为 None 时扫描项目根目录；跳过隐藏目录、归档/沙盒/缓存
        目录及 registry 自身，避免把死代码或元数据当成真实消费。注释与
        docstring 中的 k-code 也会被收集，由 audit 统一判定。
        返回 {"referenced": {code: [文件相对路径]}, "unregistered": [未登记 code]}。
        """
        root = Path(src_root).resolve() if src_root else _DEFAULT_SRC_ROOT
        referenced = defaultdict(list)
        for f in root.rglob("*.py"):
            rel = f.relative_to(root)
            if f.name == "registry.py":
                continue
            if any(p.startswith(".") or p in _SKIP_PARTS for p in rel.parts):
                continue
            try:
                text = f.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for code in sorted(set(_CODE_RE.findall(text))):
                referenced[code].append(rel.as_posix())
        unregistered = sorted(c for c in referenced if c not in self._registry)
        return {"referenced": dict(referenced), "unregistered": unregistered}

    def audit(self, src_root=None):
        """输出注册表与代码引用对比的审计结果。

        total_registered: 注册表条目数
        total_referenced: 代码中引用的唯一 k-code 数
        integrated: 已登记且被引用的 k-code
        unregistered: 被引用但未登记的 k-code
        fake_integration: 假集成（同 unregistered，被引用但未登记）
        """
        scan = self.scan_codebase(src_root)
        referenced = set(scan["referenced"])
        registered = set(self._registry)
        fake = sorted(referenced - registered)
        return {
            "total_registered": len(registered),
            "total_referenced": len(referenced),
            "integrated": sorted(referenced & registered),
            "unregistered": fake,
            "fake_integration": fake,
        }

    def to_json(self):
        """返回注册表 JSON 字符串，按 k-code 排序保证稳定输出。"""
        return json.dumps(
            {k: self._registry[k] for k in sorted(self._registry)},
            ensure_ascii=False,
            indent=2,
        )


_registry_singleton: KBRegistry | None = None


def get_registry():
    """返回全局懒加载的 KBRegistry 单例。"""
    global _registry_singleton
    if _registry_singleton is None:
        _registry_singleton = KBRegistry()
    return _registry_singleton


def audit_kb():
    """一键审计：返回 get_registry().audit() 的结果。"""
    return get_registry().audit()
