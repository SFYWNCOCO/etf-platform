"""akshare_upgrage.py — P2: akshare升级为主流数据源

将akshare从3rd fallback提升为2nd priority，并扩展数据用途：
1. 价格数据: fund_etf_spot_em (实时行情)
2. 估值数据: stock_board_industry_cons_em (行业PE/PB)
3. 分红数据: fund_etf_dividend_em (ETF分红历史)
4. 国债收益: bond_china_yield (如可用)
"""
import logging
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# akshare可用性检查
_HAS_AKSHARE = False
try:
    import akshare as ak
    _HAS_AKSHARE = True
    logger.info(f"akshare {_HAS_AKSHARE} 已加载")
except ImportError:
    logger.warning("akshare 未安装，P2升级跳过")


def is_available() -> bool:
    """检查akshare是否可用"""
    return _HAS_AKSHARE


def get_etf_spot(codes: list[str] = None) -> Dict[str, dict]:
    """获取ETF实时行情（主数据源升级）

    替代原 akshare_source.py 的3rd fallback位置
    """
    if not _HAS_AKSHARE:
        return {}

    result = {}
    try:
        df = ak.fund_etf_spot_em()
        if df is None or df.empty:
            return result

        for _, row in df.iterrows():
            code = str(row.get("代码", ""))
            if len(code) != 6 or not code.isdigit():
                continue
            result[code] = {
                "name": str(row.get("名称", "")),
                "price": float(row.get("最新价", 0) or 0),
                "change_pct": float(row.get("涨跌幅", 0) or 0),
                "volume": float(row.get("成交量", 0) or 0),
                "amount": float(row.get("成交额", 0) or 0),
                "source": "akshare_spot",
            }
    except Exception as e:
        logger.debug(f"akshare spot fail: {e}")

    return result


def get_dividend_history(code: str, years: int = 5) -> list[dict]:
    """获取ETF分红历史"""
    if not _HAS_AKSHARE:
        return []

    try:
        df = ak.fund_etf_dividend_em(symbol=code)
        if df is None or df.empty:
            return []

        results = []
        for _, row in df.iterrows():
            results.append({
                "date": str(row.get("分红日期", "")),
                "rate": float(row.get("分红率", 0) or 0),
                "amount": float(row.get("分红金额", 0) or 0),
            })
        return results[:years * 4]  # 最多返回N年的季度数据
    except Exception as e:
        logger.debug(f"akshare dividend fail: {e}")
        return []


def get_bond_yield() -> Optional[float]:
    """获取国债收益率（备用）"""
    if not _HAS_AKSHARE:
        return None

    try:
        df = ak.bond_china_yield()
        if df is None or df.empty:
            return None

        row = df[df['期限'] == '10年'] if '期限' in df.columns else df.iloc[0]
        if isinstance(row, type(df)):
            row = row.iloc[0] if len(row) > 0 else None
        if row is not None:
            rate = row.get('收益率') or row.get('yield')
            if rate is not None:
                return float(rate)
    except Exception as e:
        logger.debug(f"akshare bond fail: {e}")

    return None


def get_industry_valuation(industry: str) -> Optional[dict]:
    """获取行业估值数据（PE/PB/股息率）"""
    if not _HAS_AKSHARE:
        return None

    try:
        df = ak.stock_board_industry_cons_em(symbol=industry)
        if df is None or df.empty:
            return None

        # 计算中位数
        pe_col = '市盈率-动态' if '市盈率-动态' in df.columns else None
        pb_col = '市净率' if '市净率' in df.columns else None

        result = {"industry": industry, "stock_count": len(df)}

        if pe_col and pe_col in df.columns:
            pes = df[pe_col].dropna()
            if len(pes) > 0:
                result["pe_median"] = float(pes.median())
                result["pe_min"] = float(pes.min())
                result["pe_max"] = float(pes.max())

        if pb_col and pb_col in df.columns:
            pbs = df[pb_col].dropna()
            if len(pbs) > 0:
                result["pb_median"] = float(pbs.median())

        return result
    except Exception as e:
        logger.debug(f"akshare industry fail: {e}")
        return None


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="运行基本测试")
    args = parser.parse_args()

    if args.test:
        print(f"akshare available: {_HAS_AKSHARE}")
        if _HAS_AKSHARE:
            print("\n测试ETF行情...")
            spot = get_etf_spot(["512890", "510300"])
            print(f"  获取到 {len(spot)} 只ETF数据")
            for code, data in list(spot.items())[:3]:
                print(f"  {code}: {data.get('name')} price={data.get('price')}")

            print("\n测试国债收益率...")
            yield_rate = get_bond_yield()
            print(f"  10年国债收益率: {yield_rate}%")

            print("\n测试行业估值...")
            val = get_industry_valuation("银行")
            print(f"  银行板块: {val}")
