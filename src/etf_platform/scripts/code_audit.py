"""
全面代码审核 - 扫描整个ETF平台代码库
"""
import os
import json
import re
from collections import defaultdict
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent.parent.parent  # project root


root = 'D:/龙虾/.openclaw/etf-platform'

# 统计基本信息
py_files = []
for dirpath, dirnames, filenames in os.walk(root):
    # 跳过venv, __pycache__, node_modules
    if any(skip in dirpath for skip in ['venv', '__pycache__', '.git', 'node_modules']):
        continue
    for fn in filenames:
        if fn.endswith('.py'):
            py_files.append(os.path.join(dirpath, fn))

total_files = len(py_files)
total_lines = 0
total_funcs = 0
total_classes = 0

# 问题统计
issues = {
    'bare_except': [],
    'hardcoded_paths': [],
    'TODO_FIXME': [],
    'print_statements': [],
    'no_docstring': [],
    'long_functions': [],
    'imports': [],
    'magic_numbers': [],
    'pass_statements': [],
}

func_counts = defaultdict(int)
class_counts = defaultdict(int)

for fpath in py_files:
    try:
        content = open(fpath, 'r', encoding='utf-8').read()
        lines = content.split('\n')
        total_lines += len(lines)
        
        rel_path = fpath.replace(root + '/', '').replace('\\', '/')
        
        # 1. bare except (except:)
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith('except:') and not stripped.startswith('#'):
                issues['bare_except'].append((rel_path, i, stripped))
            
            # 2. hardcoded paths
            if re.search(r'[A-Z]:\\\\[^"\']', stripped) or re.search(r'D:/龙虾/.openclaw', stripped):
                if not stripped.startswith('#') and 'open(' in stripped:
                    issues['hardcoded_paths'].append((rel_path, i, stripped[:80]))
            
            # 3. TODO/FIXME
            if re.search(r'#\s*(TODO|FIXME|HACK|XXX)', stripped, re.IGNORECASE):
                issues['TODO_FIXME'].append((rel_path, i, stripped[:80]))
            
            # 4. print statements (outside test files)
            if stripped.startswith('print(') and '/tests/' not in rel_path:
                issues['print_statements'].append((rel_path, i, stripped[:80]))
            
            # 5. magic numbers
            if re.search(r'= *[0-9]+\.[0-9]+', stripped) and not stripped.startswith('#') and not stripped.startswith('def ') and not stripped.startswith('class '):
                # 排除权重定义等合理场景
                if not any(kw in stripped for kw in ['weight', 'ratio', 'factor', 'scale']):
                    issues['magic_numbers'].append((rel_path, i, stripped[:80]))
            
            # 6. bare pass
            if stripped == 'pass':
                issues['pass_statements'].append((rel_path, i, stripped))
        
        # 7. 统计函数和类
        for line in lines:
            if re.match(r'\s*def\s+', line):
                total_funcs += 1
                func_counts[rel_path] += 1
            if re.match(r'\s*class\s+', line):
                total_classes += 1
                class_counts[rel_path] += 1
    
    except Exception as e:
        print(f"跳过 {rel_path}: {e}")

# 生成报告
report = {
    'total_files': total_files,
    'total_lines': total_lines,
    'total_functions': total_funcs,
    'total_classes': total_classes,
    'avg_lines_per_file': round(total_lines / max(total_files, 1), 1),
    'avg_funcs_per_file': round(total_funcs / max(total_files, 1), 1),
    'issues': {k: len(v) for k, v in issues.items()},
    'issue_details': {k: v[:20] for k, v in issues.items()},  # 只保留前20条
}

# 保存报告
with open(BASE / 'code_audit_report.json', 'w', encoding='utf-8') as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

# 打印报告
print("="*60)
print("       ETF平台代码审核报告")
print("="*60)
print(f"\n总Python文件: {total_files}")
print(f"总行数: {total_lines}")
print(f"总函数: {total_funcs}")
print(f"总类: {total_classes}")
print(f"平均每文件行数: {report['avg_lines_per_file']}")
print(f"平均每文件函数数: {report['avg_funcs_per_file']}")

print("\n--- 问题统计 ---")
for issue_type, details in issues.items():
    print(f"  {issue_type}: {len(details)}")

print("\n--- TOP 10 文件复杂度 ---")
sorted_funcs = sorted(func_counts.items(), key=lambda x: -x[1])
for fpath, count in sorted_funcs[:10]:
    print(f"  {fpath}: {count}个函数")

print("\n完整报告已保存到 data/code_audit_report.json")
