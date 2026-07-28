"""deep.py — 薄包装层.

原文件已拆分到 deep_sub/ 子包以提升可维护性.本文件保留以维持向后兼容:
    from etf_platform.analysis.deep import xxx  # 仍可用

P1-P2 增强引擎: 实时材料价格监控 + 人员事件触发器 + 技术里程碑进度
================================================================
用法:
  python deep_monitor.py              # 全量监控
  python deep_monitor.py --live       # 拉取实时价格
  python deep_monitor.py --material   # 仅材料价格
  python deep_monitor.py --personnel  # 仅人员风险
  python deep_monitor.py --tech       # 仅技术里程碑

实际实现位于:
    deep_sub/materials_data.py   — 内置材料价格数据字典
    deep_sub/materials.py        — 插件注册表 + 动态加载函数
    deep_sub/personnel.py        — 人员风险数据库
    deep_sub/tech_milestones.py  — 技术里程碑进度
    deep_sub/monitor.py          — DeepMonitor 引擎 + main 入口
    deep_sub/_common.py          — 共享 imports
"""
from .deep_sub.materials_data import MATERIAL_PRICE_MONITOR
from .deep_sub.materials import (
    MATERIAL_PLUGIN_REGISTRY,
    _REGISTRY_LOCK,
    _DEFAULTS,
    register_material,
    register_from_file,
    get_all_materials,
    _auto_load_plugins,
)
from .deep_sub.personnel import PERSONNEL_RISK_DB
from .deep_sub.tech_milestones import TECH_MILESTONES_V2
from .deep_sub.monitor import DeepMonitor, main


__all__ = [
    "MATERIAL_PRICE_MONITOR",
    "MATERIAL_PLUGIN_REGISTRY",
    "_REGISTRY_LOCK",
    "_DEFAULTS",
    "register_material",
    "register_from_file",
    "get_all_materials",
    "_auto_load_plugins",
    "PERSONNEL_RISK_DB",
    "TECH_MILESTONES_V2",
    "DeepMonitor",
    "main",
]


if __name__ == "__main__":
    main()
