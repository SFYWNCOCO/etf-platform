"""
L16增强: 接入折溢价+资金流实时信号到现有L16 live_signals层

从东财AKShare获取:
- IOPV实时估值 + 折价率 → 折溢价信号
- 主力/超大单/大单净流入 → 资金流信号

集成点:
- get_live_signals() 增加 fund_flow 参数
- score_premium_signal() 升级为基于实时IOPV的精确评分
- 新增资金流评分函数
"""

from __future__ import annotations

import logging
from typing import Dict

logger = logging.getLogger(__name__)


def score_fund_flow_signal(
    main_net_inflow: float = 0.0,      # 主力净流入净额(元)
    main_net_ratio: float = 0.0,       # 主力净流入净占比(%)
    super_large_net: float = 0.0,      # 超大单净流入(元)
    price_change: float = 0.0,         # 当日涨跌幅(%)
) -> Dict:
    """
    基于资金流向生成交易信号。

    信号逻辑:
    - 主力大幅净流入 + 价格上涨 = 量价齐升(bullish)
    - 主力大幅净流出 + 价格上涨 = 主力出货(bearish divergence)
    - 主力大幅净流入 + 价格下跌 = 主力吸筹(bullish divergence)
    - 超大单持续流出 = 机构离场警告

    Score范围: 2-9
    """
    # 归一化资金流强度 (万元为单位)
    main_net_wan = main_net_inflow / 10000
    super_large_wan = super_large_net / 10000

    # 资金流评分基准
    if main_net_wan > 5000:
        flow_score = 8.5
        flow_label = "强流入"
    elif main_net_wan > 1000:
        flow_score = 7.0
        flow_label = "净流入"
    elif main_net_wan > 100:
        flow_score = 5.5
        flow_label = "小幅流入"
    elif main_net_wan > -100:
        flow_score = 5.0
        flow_label = "平衡"
    elif main_net_wan > -1000:
        flow_score = 4.0
        flow_label = "小幅流出"
    elif main_net_wan > -5000:
        flow_score = 3.0
        flow_label = "净流出"
    else:
        flow_score = 2.0
        flow_label = "强流出"

    # 资金流与价格背离检测
    divergence = "none"
    divergence_penalty = 0.0

    if price_change > 1.0 and main_net_wan < -1000:
        divergence = "出货背离"
        divergence_penalty = -1.5  # 价格上涨但主力大幅流出
    elif price_change < -1.0 and main_net_wan > 1000:
        divergence = "吸筹背离"
        divergence_penalty = +1.0  # 价格下跌但主力吸筹，加分
    elif price_change > 0 and super_large_wan < -2000:
        divergence = "超大单撤离"
        divergence_penalty = -1.0

    final_score = max(1.0, min(10.0, flow_score + divergence_penalty))

    return {
        "score": round(final_score, 1),
        "label": flow_label,
        "main_net_wan": round(main_net_wan, 0),
        "super_large_wan": round(super_large_wan, 0),
        "divergence": divergence,
        "divergence_penalty": divergence_penalty,
        "signal": "buy" if final_score >= 7 else ("sell" if final_score <= 3 else "neutral"),
    }


def get_etf_realtime_signals(code: str = "", sector: str = "") -> Dict:
    """
    从东财AKShare获取ETF实时数据并生成综合信号。

    Args:
        code: ETF代码
        sector: 行业板块

    Returns:
        包含 premium, fund_flow, composite 信号的字典
    """
    try:
        import akshare as ak
        df = ak.fund_etf_spot_em()

        if code:
            row_df = df[df['代码'].astype(str) == code]
            if row_df.empty:
                return {"error": f"ETF {code} not found", "code": code}
            row = row_df.iloc[0]
        else:
            # 无指定code时返回市场概览
            return _get_market_overview(df)

        # 折溢价信号
        premium_rate = float(row.get('基金折价率', 0))
        iopv = float(row.get('IOPV实时估值', row.get('最新价', 0)))
        price = float(row.get('最新价', 0))

        # 资金流信号
        main_net = float(row.get('主力净流入-净额', 0))
        main_ratio = float(row.get('主力净流入-净占比', 0))
        super_large = float(row.get('超大单净流入-净额', 0))
        large = float(row.get('大单净流入-净额', 0))
        price_chg = float(row.get('涨跌幅', 0))

        from .dip_monitor import DIPMonitor
        from .fund_flow import FundFlowAnalyzer

        dip_monitor = DIPMonitor()
        premium_signal = dip_monitor._detect_premium_category(premium_rate) if hasattr(dip_monitor, '_detect_premium_category') else {
            "rate": premium_rate,
            "level": "normal",
            "signal": "neutral",
        }

        flow_analyzer = FundFlowAnalyzer()
        flow_signal = score_fund_flow_signal(main_net, main_ratio, super_large, price_chg)

        # 综合信号
        composite_score = premium_signal.get("score", 5) * 0.4 + flow_signal["score"] * 0.6
        composite_score = round(max(1.0, min(10.0, composite_score)), 1)

        return {
            "code": code,
            "name": row.get('名称', ''),
            "price": price,
            "iopv": iopv,
            "premium_rate": premium_rate,
            "premium_signal": premium_signal,
            "fund_flow": flow_signal,
            "composite_score": composite_score,
            "data_timestamp": row.get('更新时间', ''),
        }

    except Exception as e:
        logger.error(f"[L16_ENHANCED] 获取实时信号失败: {e}")
        return {"error": str(e), "code": code}


def _get_market_overview(df) -> Dict:
    """市场资金流概览"""
    total_main = df['主力净流入-净额'].sum() if '主力净流入-净额' in df.columns else 0
    total_super = df['超大单净流入-净额'].sum() if '超大单净流入-净额' in df.columns else 0

    return {
        "market_overview": True,
        "total_etfs": len(df),
        "total_main_flow_yi": round(total_main / 1e8, 2),
        "total_super_large_flow_yi": round(total_super / 1e8, 2),
        "inflow_count": int((df['主力净流入-净额'] > 0).sum()) if '主力净流入-净额' in df.columns else 0,
        "outflow_count": int((df['主力净流入-净额'] < 0).sum()) if '主力净流入-净额' in df.columns else 0,
    }
