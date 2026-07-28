"""
批量修复bare_except: except: → except Exception as e

[DEPRECATED] 一次性修复脚本，已执行完毕，无其他代码引用。保留作历史记录，不再需要运行。
"""
import os
import re

root = 'D:/龙虾/.openclaw/etf-platform'
fixed_count = 0
files_fixed = []

for dirpath, dirnames, filenames in os.walk(root):
    # 跳过虚拟环境和缓存
    dirnames[:] = [d for d in dirnames if d not in ['venv', '__pycache__', '.git', 'node_modules']]
    
    for fn in filenames:
        if not fn.endswith('.py'):
            continue
        
        fpath = os.path.join(dirpath, fn)
        rel_path = fpath.replace(root + '\\', '').replace('\\', '/')
        
        try:
            content = open(fpath, 'r', encoding='utf-8').read()
            lines = content.split('\n')
            modified = False
            new_lines = []
            
            for i, line in enumerate(lines):
                stripped = line.strip()
                # 匹配 bare except
                if stripped == 'except:':
                    indent = line[:len(line) - len(line.lstrip())]
                    new_lines.append(indent + 'except Exception as _bare_except_e:')
                    modified = True
                    fixed_count += 1
                elif re.match(r'^(\s+)except:\s+(.+)$', line):
                    # except: 后面有代码，如 "except: pct = 0"
                    m = re.match(r'^(\s+)except:\s+(.+)$', line)
                    indent = m.group(1)
                    code = m.group(2)
                    new_lines.append(f'{indent}except Exception as _bare_except_e:\n{indent}    {code}')
                    modified = True
                    fixed_count += 1
                else:
                    new_lines.append(line)
            
            if modified:
                new_content = '\n'.join(new_lines)
                with open(fpath, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                files_fixed.append(rel_path)
        
        except Exception as e:
            print(f"跳过 {rel_path}: {e}")

print("="*60)
print("       bare_except 批量修复报告")
print("="*60)
print(f"\n修复数量: {fixed_count}")
print(f"修复文件数: {len(files_fixed)}")
print("\n修复文件列表:")
for f in files_fixed:
    print(f"  {f}")
