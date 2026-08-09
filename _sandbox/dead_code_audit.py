# -*- coding: utf-8 -*-
"""死代码清理第一步：完整引用复核。
对候选死模块逐个 grep：代码 import、文档引用、cron script 引用。
输出每个模块的引用计数 + 引用位置，供归档决策。
"""
import subprocess, sys, os, json
from pathlib import Path

ROOT = Path(r"D:/龙虾/.openclaw/etf-platform")
SRC = ROOT / "src"
CANDIDATES = [
    "kb_sector_momentum", "pherosome_decay", "meta_predictor",
    "position_allocator", "regime_transition", "prediction_explainer",
    "realtime_data", "deep_sub._common",
    # scripts.* 39个
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

def grep_count(pattern, paths):
    """返回 (count, first_locations)"""
    locs = []
    for p in paths:
        try:
            r = subprocess.run(
                ["grep", "-rn", pattern, str(p), "--include=*.py", "--include=*.md", "--include=*.yaml", "--include=*.json"],
                capture_output=True, text=True, timeout=30, encoding="utf-8", errors="replace",
            )
            for line in r.stdout.splitlines():
                # 排除自身定义文件
                if ".archive_" in line or "_archived" in line:
                    continue
                locs.append(line)
        except Exception:
            pass
    return len(locs), locs[:3]

print(f"{'模块':<32} {'代码+文档引用':<6} 位置")
print("-" * 90)
results = {}
for mod in CANDIDATES:
    n, locs = grep_count(mod, [SRC, ROOT / "tests", ROOT / "docs", ROOT / "knowledge"])
    results[mod] = {"count": n, "locs": locs}
    status = "🔴零引用" if n == 0 else f"🟡{n}处"
    loc_str = "; ".join(locs[:2])[:60] if locs else "-"
    print(f"{mod:<32} {status:<8} {loc_str}")

# 汇总
zero = [k for k, v in results.items() if v["count"] == 0]
referenced = {k: v for k, v in results.items() if v["count"] > 0}
print(f"\n零引用(可归档): {len(zero)}")
print(f"有引用(需复核): {len(referenced)}")
for k, v in referenced.items():
    print(f"  {k}: {v['count']}处 -> {v['locs'][:2]}")

with open(ROOT / "_sandbox" / "dead_code_audit_20260809.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print(f"\n明细已存 _sandbox/dead_code_audit_20260809.json")
