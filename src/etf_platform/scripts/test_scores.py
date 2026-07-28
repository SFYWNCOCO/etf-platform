import sys
sys.path.insert(0, 'src')
from etf_platform.pipeline import run_full

codes = ['512660', '512480', '512690', '518880', '510300', '159995', '512880', '515030']
for code in codes:
    try:
        r = run_full(code, live=False)
        ls = r['layer_scores']
        print(f"{code}: L1={ls['L1_ETF']}, L2={ls['L2_Holdings']}, L3={ls['L3_Material']}, L4={ls['L4_SupplyChain']}, L5={ls['L5_Tech']}, L6={ls['L6_Politics']}, L7={ls['L7_Irreplaceable']}, L8={ls['L8_CapitalFlow']}, L9={ls['L9_Signals']}, L10={ls['L10_Demand']}, L11={ls['L11_SectorRisk']}, comp={r['composite_score']}")
    except Exception as e:
        print(f"{code}: ERROR {e}")
