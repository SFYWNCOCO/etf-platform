#!/usr/bin/env python3
"""KB集成率审计脚本 — 扫描代码中 k-code 引用，与注册表对比，输出集成率。

用法:
    python scripts/kb_integration_audit.py
    python scripts/kb_integration_audit.py --json   # JSON输出

输出:
    total_kb_codes / total_referenced / integrated / integration_rate%
    new_references (代码引用但未注册的k-code) / unregistered
"""

import argparse
import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SRC = BASE / "src"
ROOT_SCRIPTS = [BASE / "weekly_top3.py", BASE / "news_to_etf_bridge.py",
                BASE / "etf_daily_patrol_wrapper.py", BASE / "etf_daily_patrol.py",
                BASE / "auto_sentiment.py", BASE / "policy_fetcher.py",
                BASE / "news_bridge_cron_wrapper.py"]
REGISTRY_FILE = BASE / "data" / "kb_registry.json"
KB_DIR = BASE.parent / "knowledge"

K_CODE_RE = re.compile(r"k\d{3}")


def scan_codebase() -> dict:
    """扫描 src/ + 根目录脚本的 k-code 引用。返回 {code: [files]}"""
    referenced: dict[str, set] = {}
    files = list(SRC.rglob("*.py"))
    for p in ROOT_SCRIPTS:
        if p.exists():
            files.append(p)
    for f in files:
        if "_archived" in str(f) or "_archive" in str(f) or "__pycache__" in str(f):
            continue
        try:
            txt = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for code in K_CODE_RE.findall(txt):
            referenced.setdefault(code, set()).add(str(f.relative_to(BASE)))
    return {k: sorted(v) for k, v in referenced.items()}


def scan_kb() -> set:
    """扫描知识库所有 k-code。"""
    codes = set()
    if not KB_DIR.exists():
        return codes
    for f in KB_DIR.rglob("*.md"):
        try:
            txt = f.read_text(encoding="utf-8", errors="ignore")
            codes.update(K_CODE_RE.findall(txt))
        except Exception:
            continue
    return codes


def load_registry() -> dict:
    """加载注册表。返回 {code: entry}"""
    if REGISTRY_FILE.exists():
        try:
            data = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
            return data.get("registry", data) if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def audit() -> dict:
    referenced = scan_codebase()
    kb_codes = scan_kb()
    registry = load_registry()

    all_ref = set(referenced.keys())
    registered = set(registry.keys())
    # 注册表可能嵌套 {"registry": {...}} 或扁平
    if isinstance(registry, dict) and "registry" in registry:
        registered = set(registry["registry"].keys())

    new_refs = all_ref - registered          # 代码引用但未注册 = 假集成风险
    unregistered = registered - all_ref       # 注册但未引用 = 死注册

    # 知识库总码数（用KB实际扫描，若KB存在）
    total_kb = len(kb_codes) if kb_codes else len(registered)

    return {
        "total_kb_codes": total_kb,
        "total_referenced": len(all_ref),
        "integrated": len(all_ref & registered),
        "integration_rate": round(len(all_ref & registered) / total_kb * 100, 1) if total_kb else 0.0,
        "new_references": sorted(new_refs),
        "unregistered": sorted(unregistered),
        "referenced_codes": sorted(all_ref),
        "registry_count": len(registered),
    }


def main():
    parser = argparse.ArgumentParser(description="KB集成率审计")
    parser.add_argument("--json", action="store_true", help="JSON输出")
    args = parser.parse_args()

    result = audit()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    print(f"=== KB 集成率审计 ===")
    print(f"KB k-code 总数:     {result['total_kb_codes']}")
    print(f"代码引用:           {result['total_referenced']}")
    print(f"已集成(注册∩引用):  {result['integrated']}")
    print(f"集成率:             {result['integration_rate']}%")
    print(f"注册表条目:         {result['registry_count']}")
    if result["new_references"]:
        print(f"\n⚠️ 代码引用但未注册 (假集成风险): {len(result['new_references'])}")
        for c in result["new_references"]:
            print(f"  {c}")
    if result["unregistered"]:
        print(f"\nℹ️ 注册但代码未引用 (死注册): {len(result['unregistered'])}")
        for c in result["unregistered"][:10]:
            print(f"  {c}")


if __name__ == "__main__":
    main()
