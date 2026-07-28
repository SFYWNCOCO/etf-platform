# Clean up temporary fix scripts
import os
from pathlib import Path
BASE = Path(__file__).resolve().parent.parent.parent.parent  # project root

scripts_dir = BASE / 'src' / 'etf_platform' / 'scripts/'
to_remove = [
    'fix_ceiling.py', 'fix_ceiling2.py', 'fix_factors.py', 'fix_demand.py',
    'fix_l8.py', 'fix_l1_l2.py', 'fix_typo.py', 'fix_l2_sector.py',
    'verify_fixes.py', 'check_l2_l9.py', 'final_verify.py'
]
for f in to_remove:
    path = os.path.join(scripts_dir, f)
    if os.path.exists(path):
        os.remove(path)
        print(f'Removed: {f}')
print('Cleanup complete')
