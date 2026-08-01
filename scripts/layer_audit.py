#!/usr/bin/env python3
"""穿透层全量审计 — 运行时 + 代码映射 + 评分分布"""
import sys, json, statistics, math, os
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from etf_platform.config_loader import load_etfs
from etf_platform.pipeline import run_full

BASE = Path(__file__).resolve().parent.parent  # etf-platform/

CONFIG_PATH = BASE / "config" / "layers.yaml"
LAYERS_DIR = BASE / "src" / "etf_platform" / "layers"

# ── 1. 从config提取L2-L34声明 ──────────────────────────────
def parse_config_layers():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        text = f.read()
    
    configured = {}
    in_block = False
    for line in text.splitlines():
        s = line.strip()
        if s == "layer_to_category:":
            in_block = True
            continue
        if in_block and s.startswith("three_layer_index"):
            in_block = False
        if not in_block or not s:
            continue
        if "#" in s:
            s = s[:s.index("#")].strip()
        if not s:
            continue
        parts = s.split(":")
        if len(parts) < 2:
            continue
        key = parts[0].strip().strip("'\"")
        if key.startswith("L") and "_" in key:
            cat = ":".join(parts[1:]).strip().split("#")[0].strip().strip("'\"")
            configured[key] = cat
    return configured

# ── 2. 扫描实际layer模块 ────────────────────────────────────
def scan_layer_modules():
    modules = []
    if LAYERS_DIR.exists():
        for p in sorted(LAYERS_DIR.glob("l*.py")):
            stem = p.stem
            parts = stem.split("_", 1)
            num = int(parts[0][1:])
            label = parts[1].upper() if len(parts) > 1 else ""
            
            # 读函数签名
            funcs = []
            for line in p.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.startswith("def ") and not stripped.startswith("def _"):
                    fname = stripped[4:].split("(")[0]
                    funcs.append(fname)
            modules.append({
                "path": str(p.relative_to(BASE)),
                "module_num": num,
                "label": label,
                "functions": funcs,
            })
    
    # 扫描analysis和enhance中的lxx_模块
    for subdir in ["analysis", "enhance"]:
        d = BASE / "src" / "etf_platform" / subdir
        if d.exists():
            for p in sorted(d.glob("l*.py")):
                stem = p.stem
                parts = stem.split("_", 1)
                try:
                    num = int(parts[0][1:])
                except ValueError:
                    continue
                label = parts[1].upper() if len(parts) > 1 else ""
                funcs = []
                for line in p.read_text(encoding="utf-8").splitlines():
                    stripped = line.strip()
                    if stripped.startswith("def ") and not stripped.startswith("def _"):
                        funcs.append(stripped[4:].split("(")[0])
                modules.append({
                    "path": str(p.relative_to(BASE)),
                    "subdir": subdir,
                    "module_num": num,
                    "label": label,
                    "functions": funcs,
                })
    
    return modules

# ── 3. 抽样跑pipeline，看每层实际产出 ────────────────────────
def sample_pipeline(etf_codes, risk_profiles):
    results = {}
    etfs = load_etfs()
    
    for code in etf_codes:
        info = etfs.get(code, {})
        t0 = __import__('time').time()
        try:
            r = run_full(code, live=False)
            dt = __import__('time').time() - t0
            scores = r.get('layer_scores', {}) if isinstance(r, dict) else {}
            weighted = r.get('weighted_categories', {}) if isinstance(r, dict) else {}
            debate = r.get('debate_info', {}) if isinstance(r, dict) else {}
            meta = {
                'score': r.get('score') if isinstance(r, dict) else None,
                'sector': info.get('sector', '?'),
                'risk_level': info.get('risk_level', '?'),
                'name': info.get('name', '?'),
                'elapsed': round(dt, 2),
                'layer_count': len(scores),
                'debate_verdict': debate.get('verdict'),
                'debate_confidence': debate.get('confidence'),
                'weighted_categories': weighted,
                'flags': r.get('flags', {}) if isinstance(r, dict) else {},
                'scores': scores,
            }
            results[code] = meta
        except Exception as e:
            results[code] = {'error': f"{type(e).__name__}: {e}",
                           'sector': info.get('sector','?'),
                           'name': info.get('name','?')}
    return results

# ── 4. 分析：每层是否有空值/硬编码/缺失 ─────────────────────
def analyze_samples(results):
    ok_results = {c: r for c, r in results.items() if 'error' not in r}
    
    all_layers = set()
    for r in ok_results.values():
        all_layers.update(r['scores'].keys())
    
    layer_stats = {}
    for layer in sorted(all_layers):
        values = []
        for r in ok_results.values():
            v = r['scores'].get(layer)
            if isinstance(v, (int, float)):
                values.append(float(v))
        
        # 统计基本特征
        if values:
            unique = len(set(round(v,1) for v in values))
            std = statistics.stdev(values) if len(values) > 1 else 0
            rng = (min(values), max(values))
        else:
            unique = 0; std = 0; rng = (0,0)
        
        # 判断问题
        issues = []
        if len(values) < len(ok_results) * 0.5:
            issues.append("缺失率高")
        if unique <= 1 and len(values) > 1:
            issues.append("无区分度")
        if std < 0.05 and len(values) > 1:
            issues.append("std≈0")
        
        # 特殊检查: 5.0/6.0固定值
        if values and len(set(values)) <= 2:
            vals_set = sorted(set(values))
            if all(abs(v - 5.0) < 0.01 or abs(v - 6.0) < 0.01 for v in vals_set):
                issues.append("疑似硬编码")
        
        layer_stats[layer] = {
            "present_in": len(values),
            "unique_values": unique,
            "min": round(rng[0], 1) if values else None,
            "max": round(rng[1], 1) if values else None,
            "std": round(std, 3),
            "issues": issues,
        }
    
    return layer_stats

# ── 5. 对照表：Lxx → module/function是否真实存在 ───────────
def build_truth_table(configured, modules, stats):
    table = []
    
    # 建立L号→模块映射
    module_by_num_label = {}
    for m in modules:
        n = m["module_num"]
        l = m["label"]
        module_by_num_label[(n,l)] = m
        module_by_num_label.setdefault(n, []).append(m)
    
    for layer_name, category in sorted(configured.items()):
        # 提取L号和标签
        n = int(layer_name.split("_")[0][1:])
        suffix = layer_name.split("_",1)[1]
        
        # 找对应模块
        module = module_by_num_label.get((n, suffix), None)
        if not module and isinstance(module_by_num_label.get(n), list):
            candidates = [m for m in module_by_num_label[n]]
            for c in candidates:
                if any(s.lower().startswith(suffix.lower()) for s in [c["label"], c["path"]]):
                    module = c; break
            if not module:
                module = candidates[0] if candidates else None
        
        # 运行时数据
        st = stats.get(layer_name, {})
        
        # 功能检查
        functions = module["functions"] if module else []
        pipeline_helpers = {
            "L3_Material": ["apply_to_layers", "material_bridge"],
            "L9_Signals": ["score_signals_layer", "l9_signals_enhanced", "enhance_l9"],
            "L10_Demand": ["score_demand_climate", "_calc_l10"],
            "L12_PoliticalRisk": ["calculate_political_risk_score", "political_risk"],
            "L21_Behavior": ["score_l21_layers", "investment_psychology"],
            "L23_Microstructure": ["compute_microstructure", "microstructure"],
        }
        helper_keys = pipeline_helpers.get(layer_name, [])
        function_status = "✅" if any(any(h.lower() in f.lower() for h in helper_keys) for f in functions) or not helper_keys else "⚠️"
        
        issue_level = "✅" if not st.get("issues") else ("⚠️" if "硬编码" in " ".join(st["issues"]) else "❌")
        
        table.append({
            "layer": layer_name,
            "category": category,
            "module": module["path"] if module else "❌ 不存在",
            "functions": ",".join(functions[:3]),
            "function_match": function_status,
            "runtime_count": st.get("present_in", 0),
            "runtime_minmax": f"{st.get('min', '?')}~{st.get('max', '?')}" if st else "?",
            "runtime_std": st.get("std", "?"),
            "runtime_issues": ",".join(st.get("issues", ["-"])),
            "level": issue_level,
        })
    
    return table

# ── 输出 ─────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", default="510300,159792,159647,159570,159920")
    parser.add_argument("--json-out", action="store_true")
    args = parser.parse_args()
    
    print("=" * 70)
    print("📊 ETF 穿透层系统审计 — 三层验证")
    print("=" * 70)
    
    configured = parse_config_layers()
    modules = scan_layer_modules()
    samples = sample_pipeline(args.sample.split(","), {})
    stats = analyze_samples(samples)
    table = build_truth_table(configured, modules, stats)
    
    # 摘要
    total_declared = len(table)
    with_runtime = sum(1 for r in table if r["runtime_count"] > 0)
    has_module = sum(1 for r in table if "❌" not in r["module"])
    clean = sum(1 for r in table if r["level"] == "✅")
    warnings = sum(1 for r in table if r["level"] == "⚠️")
    critical = sum(1 for r in table if r["level"] == "❌")
    fixed_values = sum(1 for r in table if "无区分度" in r["runtime_issues"] or "std≈0" in r["runtime_issues"] or "疑似硬编码" in r["runtime_issues"])
    missing_runtime = sum(1 for r in table if r["runtime_count"] == 0)
    
    print(f"\n{'─'*70}")
    print(f"📈 总览")
    print(f"{'─'*70}")
    print(f"  声明层级数:    {total_declared}")
    print(f"  有对应模块:    {has_module}/{total_declared}")
    print(f"  运行时产生分数: {with_runtime}/{total_declared}")
    print(f"  无异常:        {clean}/{total_declared}")
    print(f"  有警告:        {warnings}/{total_declared}")
    print(f"  有问题:        {critical}/{total_declared}")
    print(f"  疑似硬编码/无区分: {fixed_values}/{total_declared}")
    print(f"  运行时完全缺失:   {missing_runtime}/{total_declared}")
    
    print(f"\n{'─'*70}")
    print(f"🔍 逐层明细")
    print(f"{'─'*70}")
    
    fmt = "{:<26s} {:>4s} {:>8s} {:>8s} {:>8s}  {:15s}"
    print(fmt.format("Layer", "状态", "模块", "std", "#ETF", "主要问题"))
    print("-"*80)
    
    problem_rows = []
    for r in sorted(table, key=lambda x: (x["level"] != "✅", x["level"] != "⚠️", x["layer"])):
        status = r["level"]
        module_short = r["module"].replace("D:/龙虾/.openclaw/etf-platform/", "")
        module_short = module_short[:28]
        std_val = r["runtime_std"]
        runtime_n = r["runtime_count"]
        issues = r["runtime_issues"]
        if not issues or issues == "-":
            issues = "—"
        elif len(issues) > 30:
            issues = issues[:27] + "..."
        print(fmt.format(r["layer"], status, module_short, 
                        f"{std_val:.2f}" if isinstance(std_val, (int, float)) else str(std_val),
                        str(runtime_n), issues))
        if status in ("⚠️","❌"):
            problem_rows.append(r)
    
    # 深入: 哪些层的值完全固定
    print(f"\n{'─'*70}")
    print(f"⚠️ 固定值/低方差层（可能是装饰性评分）")
    print(f"{'─'*70}")
    low_variance = [r for r in table if float(r.get("runtime_std", 0) if isinstance(r.get("runtime_std", 0), (int,float)) else 0) < 0.05 and r["runtime_count"] > 0]
    if not low_variance:
        print("  未发现低方差层 ✅")
    else:
        for r in low_variance:
            issues = r["runtime_issues"] or "—"
            print(f"  {r['layer']:20s} std={r['runtime_std']:.4f} minmax={r['runtime_minmax']}  →  {issues}")
    
    # 缺失模块
    print(f"\n{'─'*70}")
    print(f"❌ 配置声明但找不到独立模块的层")
    print(f"{'─'*70}")
    no_mod = [r for r in table if "❌ 不存在" in r["module"]]
    if not no_mod:
        print("  所有声明层都有独立模块 ✅")
    else:
        for r in no_mod:
            print(f"  ❌ {r['layer']} ({r['category']})")
            print(f"     可能由pipeline/scorer内联计算，需确认")
    
    # 保存完整报告
    report_path = BASE / "audit" / "layer_audit_full.json"
    report = {
        "summary": {
            "total_declared": total_declared,
            "with_module": has_module,
            "with_runtime": with_runtime,
            "clean": clean,
            "warnings": warnings,
            "critical": critical,
            "low_variance": len(low_variance),
            "no_module": len(no_mod),
        },
        "table": table,
        "samples": {k: {kk:vv for kk,vv in v.items() if kk != "scores"} for k,v in samples.items()},
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    
    print(f"\n📝 完整报告已保存到: {report_path}")
    print(f"{'='*70}")
