# -*- coding: utf-8 -*-
"""死代码清理：归档 48 个零引用模块到 _archived/dead_modules_20260809/（保持路径结构，可恢复）。
已做三轮引用复核（代码 import + 文档 + cron + 活模块依赖），确认零活引用。
"""
import shutil
from pathlib import Path

ROOT = Path(r"D:/龙虾/.openclaw/etf-platform")
ARCHIVE = ROOT / "_archived" / "dead_modules_20260809"

# 核心死模块（6个）
CORE = [
    "src/etf_platform/analysis/kb_sector_momentum.py",
    "src/etf_platform/analysis/pherosome_decay.py",
    "src/etf_platform/analysis/deep_sub/_common.py",
    "src/etf_platform/decision/meta_predictor.py",
    "src/etf_platform/decision/regime_transition.py",
    "src/etf_platform/decision/prediction_explainer.py",
]

# scripts/* 历史审计脚本（42个）
SCRIPTS = [
    "adversarial_self_check", "analyze_gaps", "analyze_materials_structure",
    "analyze_unknown", "audit_materials", "backtest_verification",
    "blind_etf_analysis", "calculate_penetration_scores", "check_coverage",
    "check_derived_materials", "check_fallback", "check_material_structure",
    "check_remaining_blind", "cleanup", "code_audit", "code_audit_detail",
    "data_consistency_audit", "derived_materials_report", "diag_deep",
    "diag_full", "diag_quick", "extract_categories", "final_coverage_report",
    "final_report_all", "final_report_optimization", "final_report_penetration",
    "final_report_round2", "fix_bare_except", "fix_categories",
    "list_all_materials", "list_all_materials_classified", "list_others",
    "next_round_strategy", "penetration_screen", "price_monitor",
    "regime_weights", "round2_learning", "round3_learning", "round4_final",
    "step1_screen", "step4_alert", "step4_alert_fixed", "test_scores",
    "verify_round2",
]

moved = []
missing = []

for rel in CORE:
    src = ROOT / rel
    if not src.exists():
        missing.append(rel)
        continue
    dst = ARCHIVE / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    moved.append(rel)

for name in SCRIPTS:
    src = ROOT / "src" / "etf_platform" / "scripts" / f"{name}.py"
    if not src.exists():
        missing.append(f"scripts/{name}.py")
        continue
    dst = ARCHIVE / "src" / "etf_platform" / "scripts" / f"{name}.py"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    moved.append(f"scripts/{name}.py")

print(f"已归档: {len(moved)}")
print(f"缺失: {len(missing)}")
for m in missing:
    print(f"  MISSING: {m}")
print(f"\n归档目录文件数: {sum(1 for _ in ARCHIVE.rglob('*.py'))}")
