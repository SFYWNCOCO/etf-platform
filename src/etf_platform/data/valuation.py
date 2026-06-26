"""Valuation data for ETFs: NAV, premium/discount."""
from dataclasses import dataclass
from typing import Optional


@dataclass
class ValuationSnapshot:
    code: str = ""
    name: str = ""
    nav: float = 0.0
    market_price: float = 0.0
    premium_pct: float = 0.0
    daily_return: float = 0.0
    fund_type: str = ""


def get_valuation(code: str) -> Optional[ValuationSnapshot]:
    """Get NAV/premium data for an ETF."""
    try:
        import akshare
        import warnings
        warnings.filterwarnings("ignore")
        
        df = akshare.fund_etf_fund_daily_em()
        row = df[df.iloc[:, 0].astype(str) == code]
        if row.empty:
            return None
        r = row.iloc[0]
        
        nav_col = [c for c in df.columns if "单位净值" in c]
        if not nav_col:
            return None
        nav = float(r[nav_col[0]]) if r[nav_col[0]] else 0.0
        mkt = float(r["市价"]) if "市价" in df.columns and r["市价"] else 0.0
        
        premium_str = str(r["折价率"]) if "折价率" in df.columns else "0"
        premium = float(premium_str.replace("%", ""))
        
        ret_str = str(r["增长率"]) if "增长率" in df.columns else "0"
        daily_ret = float(ret_str.replace("%", ""))
        
        return ValuationSnapshot(
            code=code,
            name=str(r.iloc[1]) if len(r) > 1 else "",
            nav=nav, market_price=mkt, premium_pct=premium,
            daily_return=daily_ret, fund_type=str(r.iloc[2]) if len(r) > 2 else "",
        )
    except Exception:
        return None