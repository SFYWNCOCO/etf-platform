"""
详细审核关键问题
"""
import json
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent.parent.parent  # project root


report = json.load(open(BASE / 'code_audit_report.json', 'r', encoding='utf-8'))

print("="*60)
print("       关键问题详细分析")
print("="*60)

# 1. bare_except详情
print("\n--- 1. Bare Except (except:) 问题 ---")
details = report.get('issue_details', {}).get('bare_except', [])
for path, line_num, content in details[:10]:
    print(f"  {path}:{line_num}")
    print(f"    {content}")

# 2. hardcoded_paths详情
print("\n--- 2. Hardcoded Paths 问题 ---")
details = report.get('issue_details', {}).get('hardcoded_paths', [])
print(f"  总计: {len(details)}个硬编码路径")
print("  前10个:")
for path, line_num, content in details[:10]:
    print(f"    {path}:{line_num}")
    print(f"      {content}")

# 3. print_statements详情
print("\n--- 3. Print Statements 问题 ---")
details = report.get('issue_details', {}).get('print_statements', [])
print(f"  总计: {len(details)}个print语句")
print("  前10个:")
for path, line_num, content in details[:10]:
    print(f"    {path}:{line_num}")
    print(f"      {content}")

# 4. magic_numbers详情
print("\n--- 4. Magic Numbers 问题 ---")
details = report.get('issue_details', {}).get('magic_numbers', [])
print(f"  总计: {len(details)}个魔法数字")
print("  前10个:")
for path, line_num, content in details[:10]:
    print(f"    {path}:{line_num}")
    print(f"      {content}")

# 5. pass_statements详情
print("\n--- 5. Bare Pass 问题 ---")
details = report.get('issue_details', {}).get('pass_statements', [])
print(f"  总计: {len(details)}个bare pass")
print("  前10个:")
for path, line_num, content in details[:10]:
    print(f"    {path}:{line_num}")
    print(f"      {content}")
