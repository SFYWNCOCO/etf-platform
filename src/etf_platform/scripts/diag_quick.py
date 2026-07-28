"""Quick diagnostic: run batch and print scores for analysis."""
import sys
sys.path.insert(0, 'src')
from etf_platform.pipeline import batch_full

results = batch_full(limit=10, live=False)
header = "CODE   NAME             SECTOR       COMP   L1    L2    L3    L4    L5    L6    L7    L8    L9    L10   L11   "
print(header)
print("-" * len(header))
for r in results:
    code = r.get('etf_code', '?')
    name = r.get('name', '?')[:16]
    sector = r.get('sector', '?')[:12]
    ls = r.get('layer_scores', {})
    comp = r.get('composite_score', 0)
    l1 = ls.get('L1_ETF', 0)
    l2 = ls.get('L2_Holdings', 0)
    l3 = ls.get('L3_Material', 0)
    l4 = ls.get('L4_SupplyChain', 0)
    l5 = ls.get('L5_Tech', 0)
    l6 = ls.get('L6_Politics', 0)
    l7 = ls.get('L7_Irreplaceable', 0)
    l8 = ls.get('L8_CapitalFlow', 0)
    l9 = ls.get('L9_Signals', 0)
    l10 = ls.get('L10_Demand', 0)
    l11 = ls.get('L11_SectorRisk', 0)
    print(f"{code:6s} {name:16s} {sector:12s} {comp:6.2f} {l1:5.1f} {l2:5.1f} {l3:5.1f} {l4:5.1f} {l5:5.1f} {l6:5.1f} {l7:5.1f} {l8:5.1f} {l9:5.1f} {l10:5.1f} {l11:5.1f}")
