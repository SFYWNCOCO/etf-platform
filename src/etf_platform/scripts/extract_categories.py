from pathlib import Path
BASE = Path(__file__).resolve().parent.parent.parent.parent

import re

# 读取deep.py，提取内置材料的分类
with open(BASE / 'src' / 'etf_platform' / 'analysis' / 'deep.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 提取所有注释块中的分类
blocks = re.findall(r'# ═══ (.+?) ═══\s*\n(.*?)(?=# ═══|$)', content, re.DOTALL)

print("="*120)
print("deep.py内置材料分类结构")
print("="*120)

for block_name, block_content in blocks:
    # 提取材料名称
    materials = re.findall(r'"([^"]+)":\s*\{', block_content)
    print(f"\n【{block_name}】({len(materials)}个材料)")
    for mat in materials[:10]:
        print(f"  - {mat}")
    if len(materials) > 10:
        print(f"  ... 及其他{len(materials)-10}个材料")

# 统计总内置材料数
all_materials = re.findall(r'"([^"]+)":\s*\{', content)
print(f"\n\n总计内置材料: {len(all_materials)}个")

# 检查是否有重复
from collections import Counter
counts = Counter(all_materials)
duplicates = {k: v for k, v in counts.items() if v > 1}
if duplicates:
    print(f"\n重复材料: {duplicates}")
else:
    print("\n无重复材料")
