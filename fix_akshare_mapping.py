#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Fix AKShare field mapping issue
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

# Current broken code in akshare_source.py
BROKEN_CODE = '''
def get_price(self, code: str) -> Optional[PriceSnapshot]:
    if not _HAS_AKSHARE:
        return None
    try:
        # Use akshare's ETF realtime function
        df = akshare.fund_etf_fund_daily_em()
        if df is None or df.empty:
            return None
        row = df[df["代码"] == code]  # WRONG FIELD NAME
        if row.empty:
            return None
        row = row.iloc[0]
        return PriceSnapshot(
            code=code,
            name=str(row.get("名称", "")),  # WRONG FIELD NAME
            price=float(row.get("最新价", 0) or 0),  # WRONG FIELD NAME
            change_pct=float(row.get("涨跌幅", 0) or 0),  # WRONG FIELD NAME
            volume=float(row.get("成交量", 0) or 0),  # WRONG FIELD NAME
            amount=float(row.get("成交额", 0) or 0),  # WRONG FIELD NAME
            turnover_rate=float(row.get("换手率", 0) or 0),  # WRONG FIELD NAME
            source=self.name,
        )
    except Exception as e:
        logger.warning("akshare_source: fetch failed: %s", e)
        return None
'''

FIXED_CODE = '''
def get_price(self, code: str) -> Optional[PriceSnapshot]:
    if not _HAS_AKSHARE:
        return None
    try:
        # Use akshare's ETF realtime function
        df = akshare.fund_etf_fund_daily_em()
        if df is None or df.empty:
            return None
        
        # Fix field mapping - AKShare uses different column names
        row = df[df["基金代码"] == code]  # FIXED: 基金代码 instead of 代码
        if row.empty:
            return None
        row = row.iloc[0]
        
        # Map AKShare fields to our expected fields
        # AKShare returns: 基金代码, 基金简称, 类型, 最新净值日期-单位净值, ...
        # We need: code, name, price, change_pct, volume, amount, turnover_rate
        
        # For fund data, we use 市价 (market price) and 增长率 (growth rate)
        price = float(row.get("市价", 0) or 0)
        change_pct = float(row.get("增长率", 0) or 0)  # This is percentage change
        
        # Note: AKShare's fund_etf_fund_daily_em() doesn't provide volume/amount data
        # For real-time trading data, we should use fund_etf_spot_em() instead
        return PriceSnapshot(
            code=code,
            name=str(row.get("基金简称", "")),  # FIXED: 基金简称 instead of 名称
            price=price,
            change_pct=change_pct,
            volume=float(row.get("成交量", 0) or 0),  # May be 0 for this API
            amount=float(row.get("成交额", 0) or 0),  # May be 0 for this API
            turnover_rate=float(row.get("换手率", 0) or 0),  # May be 0 for this API
            source=self.name,
        )
    except Exception as e:
        logger.warning("akshare_source: fetch failed: %s", e)
        return None
'''

# Better solution: use the correct API
BETTER_CODE = '''
def get_price(self, code: str) -> Optional[PriceSnapshot]:
    if not _HAS_AKSHARE:
        return None
    try:
        # Use the correct API for real-time ETF data
        df = akshare.fund_etf_spot_em()
        if df is None or df.empty:
            return None
        
        # fund_etf_spot_em() returns real-time trading data
        # Columns typically include: 代码, 名称, 最新价, 涨跌幅, 成交量, 成交额, 换手率
        row = df[df["代码"] == code]
        if row.empty:
            return None
        row = row.iloc[0]
        
        return PriceSnapshot(
            code=code,
            name=str(row.get("名称", "")),
            price=float(row.get("最新价", 0) or 0),
            change_pct=float(row.get("涨跌幅", 0) or 0),
            volume=float(row.get("成交量", 0) or 0),
            amount=float(row.get("成交额", 0) or 0),
            turnover_rate=float(row.get("换手率", 0) or 0),
            source=self.name,
        )
    except Exception as e:
        logger.warning("akshare_source: fetch failed: %s", e)
        return None
'''

print("AKShare Field Mapping Fix")
print("=" * 50)
print("\nPROBLEM:")
print("- fund_etf_fund_daily_em() returns FUND NAV data, not REAL-TIME trading data")
print("- Column names are different: 基金代码 vs 代码, 基金简称 vs 名称")
print("- Missing trading data: volume, amount, turnover_rate")
print("\nSOLUTION 1 (Quick Fix):")
print("- Change field names to match AKShare's actual output")
print("- Accept that volume/amount may be 0")
print("\nSOLUTION 2 (Better):")
print("- Use fund_etf_spot_em() instead of fund_etf_fund_daily_em()")
print("- This API provides real-time trading data with correct fields")
print("\nSOLUTION 3 (Best):")
print("- Keep Sina as primary source (already working)")
print("- Use AKShare as secondary source with corrected field mapping")
print("- Add proper error handling and logging")
