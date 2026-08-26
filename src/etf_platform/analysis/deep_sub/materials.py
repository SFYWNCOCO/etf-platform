"""材料插件注册表 + 动态加载函数.

包含:
    - MATERIAL_PLUGIN_REGISTRY: 插件注册表 (运行时填充)
    - _REGISTRY_LOCK: 注册表锁
    - _DEFAULTS: 字段默认值
    - register_material / register_from_file / get_all_materials: 注册 API
    - _auto_load_plugins: 模块加载时自动扫描 config/*.yaml

从原 deep.py 提取,实现逻辑完全一致.仅 _auto_load_plugins 中的项目根目录
路径深度适配新位置 (deep_sub/materials.py 比原 deep.py 多 1 级).
"""
import threading
import yaml
from datetime import datetime
from pathlib import Path

from .materials_data import MATERIAL_PRICE_MONITOR
from ...utils.freshness import as_of


# ═══════════════════════════════════════════════════════════════
# 材料插件注册表 — 支持从 YAML 文件动态加载材料 + 快速添加
# ═══════════════════════════════════════════════════════════════
MATERIAL_PLUGIN_REGISTRY = {}
_REGISTRY_LOCK = threading.Lock()

# 材料字段默认值 — 快速添加时自动补全缺失字段
_DEFAULTS = {
    "current": "待补充", "trend": "→ 待确认", "unit": "N/A",
    "impact_direction": "中性", "note": "快速添加, 待补充详细信息",
    "warning": "⚪ 待评估",
    "sub_grades": "待补充", "supplier_regions": {"待确认": 100},
    "substitution_years": 5, "strategic_days": 30,
    "technology_readiness": 5, "bottleneck_risk": 0.50,
}


def register_material(name, data):
    """注册单个材料 — 自动补全缺失字段的默认值.

    最少只需填 current/warning/affects 三个字段即可注册。
    """
    entry = dict(_DEFAULTS)
    entry.update(data)
    # 确保 affects 是列表
    if isinstance(entry["affects"], str):
        entry["affects"] = [entry["affects"]]
    entry["_source"] = data.get("_source", "plugin")
    entry["_registered_at"] = data.get("_registered_at", datetime.now().isoformat())
    with _REGISTRY_LOCK:
        MATERIAL_PLUGIN_REGISTRY[name] = entry
    return True


def register_from_file(path):
    """从 YAML 文件批量注册 — 支持完整格式和minimal格式."""
    path = Path(path)
    if not path.exists():
        return 0
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if not cfg or "materials" not in cfg:
        return 0
    mats = cfg["materials"]
    if mats is None or not isinstance(mats, dict):
        return 0
    # 静态快照时效: mtime 过旧 → 盖上 _stale, 消费端降权为先验
    freshness = as_of(path)
    count = 0
    for name, data in mats.items():
        # 无 data = 注释占位, 跳过
        if data is None:
            continue
        entry = dict(data)
        entry["_data_as_of"] = freshness["mtime_iso"]
        entry["_stale"] = freshness["status"] == "stale"
        register_material(name, entry)
        count += 1
    return count


def get_all_materials():
    """返回合并后的完整材料字典 (内置核心 + 插件注册)。"""
    merged = {}
    merged.update(MATERIAL_PRICE_MONITOR)
    with _REGISTRY_LOCK:
        merged.update(MATERIAL_PLUGIN_REGISTRY)
    return merged


# _auto_load_plugins 与 materials_freshness 共用的插件扫描范围
_PLUGIN_YAMLS = ("material_prices.yaml", "emerging_materials.yaml", "material_quick_add.yaml")


def _plugin_config_dir():
    # 路径修复: 本模块位于 etf_platform/analysis/deep_sub/materials.py
    # 5 级 .parent 到达 etf-platform/ 项目根目录:
    #   .parent            = deep_sub/
    #   .parent.parent     = analysis/
    #   .parent^3          = etf_platform/
    #   .parent^4          = src/
    #   .parent^5          = etf-platform/  ← + "/config"
    return Path(__file__).resolve().parent.parent.parent.parent.parent / "config"


def materials_freshness():
    """返回三个插件 yaml 的时效快照 {fname: as_of(...)}."""
    return {fname: as_of(_plugin_config_dir() / fname) for fname in _PLUGIN_YAMLS}


def _auto_load_plugins():
    """模块加载时自动扫描 config/ 下的材料 YAML 文件."""
    config_dir = _plugin_config_dir()
    for fname in _PLUGIN_YAMLS:
        p = config_dir / fname
        if p.exists():
            register_from_file(p)


# 模块加载时自动扫描插件 (等价于原 deep.py 第 1906 行的 _auto_load_plugins() 调用)
_auto_load_plugins()
