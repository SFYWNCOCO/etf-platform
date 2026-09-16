"""实时ETF数据层 — 统一IOPV/折溢价/资金流字段采集。

v1.0: 基于 akshare.fund_etf_spot_em() 的轻量封装，供 dip_monitor、
fund_flow、l16_live_signals 和 screener 复用。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = {
    "代码", "名称", "最新价", "涨跌幅", "成交量", "成交额",
    "IOPV实时估值", "基金折价率",
    "主力净流入-净额", "主力净流入-净占比",
    "超大单净流入-净额", "大单净流入-净额",
    "中单净流入-净额", "小单净流入-净额",
}


@dataclass(slots=True)
class RealtimeSnapshot:
    """单只ETF实时快照。"""
    code: str
    name: str
    price: float
    change_pct: float
    volume: float
    amount: float
    iopv: Optional[float]
    premium_pct: Optional[float]
    main_net_inflow: Optional[float]
    main_net_ratio: Optional[float]
    super_large_net: Optional[float]
    large_net: Optional[float]
    medium_net: Optional[float]
    small_net: Optional[float]
    timestamp: str

    def to_dict(self) -> dict:
        from dataclasses import asdict
        return asdict(self)


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None or value == "" or value == "---":
            return default
        return float(value)
    except (ValueError, TypeError):
        return default


def fetch_realtime_etf_data() -> pd.DataFrame:
    """获取全量ETF实时行情。

    Returns:
        空DataFrame表示获取失败，调用方需降级处理。
    """
    try:
        import akshare as ak
        from ..utils.thread_timeout import run_with_timeout
        df = run_with_timeout(ak.fund_etf_spot_em, timeout=30)
        if df is None or df.empty:
            logger.warning("[realtime] akshare返回空数据")
            return pd.DataFrame()
        logger.info(f"[realtime] 获取到 {len(df)} 只ETF实时行情")
        return df
    except ImportError:
        logger.error("[realtime] akshare未安装")
        return pd.DataFrame()
    except Exception as e:
        logger.error(f"[realtime] 获取ETF数据失败: {e}")
        return pd.DataFrame()


def normalize_row(row: pd.Series, timestamp: Optional[str] = None) -> RealtimeSnapshot:
    """将akshare单行数据转为标准RealtimeSnapshot。"""
    ts = timestamp or datetime.now().isoformat()
    return RealtimeSnapshot(
        code=str(row.get("代码", "")),
        name=str(row.get("名称", "")),
        price=_safe_float(row.get("最新价")),
        change_pct=_safe_float(row.get("涨跌幅")),
        volume=_safe_float(row.get("成交量")),
        amount=_safe_float(row.get("成交额")),
        iopv=_safe_float(row.get("IOPV实时估值"), default=float("nan")) or None,
        premium_pct=_safe_float(row.get("基金折价率"), default=float("nan")) or None,
        main_net_inflow=_safe_float(row.get("主力净流入-净额")),
        main_net_ratio=_safe_float(row.get("主力净流入-净占比")),
        super_large_net=_safe_float(row.get("超大单净流入-净额")),
        large_net=_safe_float(row.get("大单净流入-净额")),
        medium_net=_safe_float(row.get("中单净流入-净额")),
        small_net=_safe_float(row.get("小单净流入-净额")),
        timestamp=ts,
    )


def normalize_dataframe(df: pd.DataFrame) -> list[RealtimeSnapshot]:
    """批量标准化。"""
    if df.empty:
        return []
    ts = datetime.now().isoformat()
    return [normalize_row(row, ts) for _, row in df.iterrows()]


def get_etf_snapshot(code: str, df: Optional[pd.DataFrame] = None) -> Optional[RealtimeSnapshot]:
    """获取单只ETF实时快照。

    Args:
        code: ETF代码，如"510300"
        df: 可选预加载DataFrame，避免重复请求

    Returns:
        RealtimeSnapshot 或 None
    """
    if df is None:
        df = fetch_realtime_etf_data()
    if df.empty:
        return None

    row = df[df["代码"] == code]
    if row.empty:
        logger.warning(f"[realtime] 未找到ETF: {code}")
        return None
    return normalize_row(row.iloc[0])


def has_required_columns(df: pd.DataFrame) -> bool:
    """检查数据是否包含必要字段。"""
    if df.empty:
        return False
    available = set(df.columns)
    missing = REQUIRED_COLUMNS - available
    if missing:
        logger.warning(f"[realtime] 缺少字段: {sorted(missing)}")
        return False
    return True


def enrich_with_premium(df: pd.DataFrame) -> pd.DataFrame:
    """确保DataFrame包含折溢价率字段。

    优先使用东财已有的'基金折价率'，缺失时用IOPV计算。
    """
    if df.empty:
        return df

    result = df.copy()
    if "基金折价率" not in result.columns:
        if "IOPV实时估值" in result.columns and "最新价" in result.columns:
            result["基金折价率"] = (
                (result["最新价"] - result["IOPV实时估值"])
                / result["IOPV实时估值"] * 100
            )
        else:
            result["基金折价率"] = 0.0
    return result


def enrich_with_flow_totals(df: pd.DataFrame) -> pd.DataFrame:
    """确保DataFrame包含资金流向汇总字段。"""
    if df.empty:
        return df

    result = df.copy()
    if "主力净流入-净额" not in result.columns:
        result["主力净流入-净额"] = 0.0
    if "主力净流入-净占比" not in result.columns:
        result["主力净流入-净占比"] = 0.0
    for col in ["超大单净流入-净额", "大单净流入-净额", "中单净流入-净额", "小单净流入-净额"]:
        if col not in result.columns:
            result[col] = 0.0
    return result


def get_market_flow_summary(df: pd.DataFrame) -> dict:
    """市场资金流向概览。"""
    if df.empty or "主力净流入-净额" not in df.columns:
        return {"total": 0.0, "inflow_count": 0, "outflow_count": 0, "net_ratio": 0.0}

    total = float(df["主力净流入-净额"].sum())
    inflow = int((df["主力净流入-净额"] > 0).sum())
    outflow = int((df["主力净流入-净额"] < 0).sum())
    net_ratio = total / max(float(df["成交额"].sum()), 1.0) * 100 if "成交额" in df.columns else 0.0

    return {
        "total": total,
        "inflow_count": inflow,
        "outflow_count": outflow,
        "net_ratio": round(net_ratio, 2),
    }
