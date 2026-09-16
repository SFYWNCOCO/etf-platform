"""Valuation & fundamentals for ETFs.
Sources: fund daily API, K-line data, static index mapping."""
import logging
import re
import urllib.request
from dataclasses import dataclass, field
from typing import Optional, List, Dict
import urllib.error

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class FundSnapshot:
    """Complete fund snapshot combining multiple data sources."""
    code: str = ""
    name: str = ""
    # NAV data
    nav: float = 0.0
    market_price: float = 0.0
    premium_pct: float = 0.0
    daily_return: float = 0.0
    fund_type: str = ""
    # Stage returns (from K-line)
    change_1m: float = 0.0    # 近1月≈20交易日
    change_3m: float = 0.0    # 近3月≈60交易日
    change_6m: float = 0.0    # 近6月
    # Fund info (static, expandable)
    fund_size_yi: Optional[float] = None
    fund_manager: str = ""
    establish_date: str = ""
    tracking_index: str = ""
    # Holdings summary
    top_holdings: List[Dict] = field(default_factory=list)
    sector_allocation: Dict = field(default_factory=dict)


# ETF -> Tracking index mapping (seeded from 天天基金网, expand over time)
TRACKING_INDEX_MAP = {
    "159263": "国证价值100指数",
    "159995": "国证半导体芯片指数",
    "159919": "沪深300指数",
    "159915": "创业板指数",
    "159363": "创业板人工智能指数",
    "159327": "中证半导体材料设备指数",
    "159201": "中证自由现金流指数",
    "159206": "中证卫星产业指数",
    "159105": "恒生生物科技指数",
    "510300": "沪深300指数",
    "512880": "中证全指证券指数",
    "518880": "黄金现货实盘合约",
    "513100": "纳斯达克100指数",
}

KNOWN_INDEX_CODES = {
    "国证价值100指数": "399370",
    "沪深300指数": "000300",
    "创业板指数": "399006",
    "国证半导体芯片指数": "990001",
}


def get_fund_snapshot(code: str) -> Optional[FundSnapshot]:
    """Get comprehensive fund data from all available sources."""
    from ..data.kline import get_trend
    
    snap = FundSnapshot(code=code)
    
    # 1. NAV data from fund daily API (fast)
    try:
        import akshare
        import warnings
        from ..utils.thread_timeout import run_with_timeout
        warnings.filterwarnings("ignore")
        df = run_with_timeout(akshare.fund_etf_fund_daily_em, timeout=30)
        row = df[df.iloc[:, 0].astype(str) == code]
        if not row.empty:
            r = row.iloc[0]
            nav_col = [c for c in df.columns if "单位净值" in c]
            if nav_col:
                snap.nav = float(r[nav_col[0]]) if r[nav_col[0]] else 0.0
            snap.market_price = float(r["市价"]) if "市价" in df.columns and r["市价"] else 0.0
            prem = str(r["折价率"]) if "折价率" in df.columns else "0"
            snap.premium_pct = float(prem.replace("%", ""))
            ret_str = str(r["增长率"]) if "增长率" in df.columns else "0"
            snap.daily_return = float(ret_str.replace("%", ""))
            snap.name = str(r.iloc[1]) if len(r) > 1 else ""
            snap.fund_type = str(r.iloc[2]) if len(r) > 2 else ""
    except Exception as e:
        logger.debug("fund NAV fetch failed: %s", e)
        pass

    # 2. Stage returns from K-line
    try:
        trend = get_trend(code)
        if trend:
            snap.change_1m = trend.change_20d
            snap.change_3m = trend.change_60d
            # approx 6m from available data
            snap.change_6m = round(trend.change_60d * 2.5, 1) if trend.data_days > 120 else trend.change_60d
    except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
        logger.debug("stage returns fetch failed: %s", e)
        pass

    # 3. Static info
    snap.tracking_index = TRACKING_INDEX_MAP.get(code, "")
    
    return snap


def get_holdings(code: str) -> List[Dict]:
    """Get top holdings via web scraping.
    Uses direct HTTP to 天天基金网 holdings page.
    Returns empty list if unavailable."""
    url = f"https://fundf10.eastmoney.com/ccmx_{code}.html"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
        
        holdings = []
        # Try to find holding rows: stock code + name + percentage
        # Pattern: stock code in td
        codes = re.findall(r"<td[^>]*>(\d{6})</td>", html)
        names = re.findall(r'<a[^>]*>([\u4e00-\u9fff]{2,10})</a>', html)
        
        # Filter: names that look like stock names (not navigation links)
        nav_words = {"首页", "基金净值", "基金排行", "基金公司", "我的"}
        stock_names = [n for n in names if n not in nav_words and len(n) >= 2]
        
        # Match codes with names
        for i, code in enumerate(codes[:20]):
            name = stock_names[i] if i < len(stock_names) else f"股票{code}"
            holdings.append({"code": code, "name": name})
        
        return holdings
    except (urllib.error.URLError, OSError, ValueError, KeyError):
        return []
