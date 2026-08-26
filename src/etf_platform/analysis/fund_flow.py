"""
资金流向分析模块 - ETF主力资金/大单/中单/小单净流入分析

数据来源: akshare.fund_etf_spot_em() 返回37列，包含:
- 主力净流入-净额, 主力净流入-净占比
- 超大单净流入-净额, 超大单净流入-净占比
- 大单净流入-净额, 大单净流入-净占比
- 中单净流入-净额, 中单净流入-净占比
- 小单净流入-净额, 小单净流入-净占比

功能:
1. 实时资金流向监控
2. 资金与价格背离检测
3. 行业/主题ETF资金轮动分析
4. 资金流向趋势判断
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class FundFlowAlert:
    """资金流向预警记录"""
    code: str
    name: str
    price_change: float      # 涨跌幅(%)
    main_net_inflow: float   # 主力净流入净额
    main_net_ratio: float    # 主力净流入净占比(%)
    super_large_net: float   # 超大单净流入
    large_net: float         # 大单净流入
    medium_net: float        # 中单净流入
    small_net: float         # 小单净流入
    divergence_type: str     # "price_up_flow_out", "price_down_flow_in", "none"
    signal: str              # "bullish", "bearish", "divergence_bullish", "divergence_bearish", "neutral"
    alert_level: str         # "high", "medium", "low", "none"
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    message: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class FundFlowAnalyzer:
    """
    ETF资金流向分析器

    核心逻辑:
    - 主力净流入 > 0 且 价格上涨 = 量价齐升(健康)
    - 主力净流入 < 0 且 价格上涨 = 主力出货(危险信号)
    - 主力净流入 > 0 且 价格下跌 = 主力吸筹(可能机会)
    - 主力净流入 < 0 且 价格下跌 = 量价齐跌(弱势)
    - 超大单/大单方向与中单/小单相反 = 机构vs散户博弈
    """

    # 资金流向阈值
    MAIN_FLOW_THRESHOLD = 10_000_000      # 1000万主力净流入阈值
    LARGE_ORDER_RATIO_THRESHOLD = 5.0     # 超大单占比>5%视为显著
    DIVERGENCE_PRICE_THRESHOLD = 1.0      # 涨跌幅>1%才检测背离

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or Path(__file__).parent.parent / "data" / "live_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.alert_history_file = self.cache_dir / "fund_flow_alert_history.jsonl"

    def fetch_data(self) -> pd.DataFrame:
        """获取ETF实时行情数据"""
        try:
            import akshare as ak
            from ..utils.thread_timeout import run_with_timeout
            df = run_with_timeout(ak.fund_etf_spot_em, timeout=30)
            logger.info(f"[FLOW] 获取到 {len(df)} 只ETF资金流数据")
            return df
        except ImportError:
            logger.error("[FLOW] akshare未安装")
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"[FLOW] 获取数据失败: {e}")
            return pd.DataFrame()

    def classify_flow_pattern(self, row: pd.Series) -> tuple[str, str]:
        """
        分类资金流向模式

        Returns:
            (pattern_name, signal_type)
            pattern: "量价齐升", "主力出货", "主力吸筹", "量价齐跌", "散户接盘", "机构离场"
            signal: "bullish", "bearish", "divergence_bullish", "divergence_bearish", "neutral"
        """
        price_chg = float(row.get('涨跌幅', 0))
        main_net = float(row.get('主力净流入-净额', 0))
        medium = float(row.get('中单净流入-净额', 0))
        small = float(row.get('小单净流入-净额', 0))

        # 价格方向
        price_up = price_chg > self.DIVERGENCE_PRICE_THRESHOLD
        price_down = price_chg < -self.DIVERGENCE_PRICE_THRESHOLD

        # 资金方向
        money_in = main_net > self.MAIN_FLOW_THRESHOLD
        money_out = main_net < -self.MAIN_FLOW_THRESHOLD

        # 大单 vs 小单
        retail_money_in = medium + small > 0

        if price_up and money_in:
            return "量价齐升", "bullish"
        elif price_up and money_out:
            return "主力出货", "bearish"
        elif price_down and money_in:
            return "主力吸筹", "divergence_bullish"
        elif price_down and money_out:
            return "量价齐跌", "bearish"
        elif price_up and not money_out and retail_money_in:
            return "散户追高", "divergence_bearish"
        elif price_down and not money_in and retail_money_in:
            return "散户恐慌抛售", "bearish"
        else:
            return "资金平衡", "neutral"

    def detect_divergences(self, df: pd.DataFrame) -> list[FundFlowAlert]:
        """
        检测资金与价格背离

        关键背离类型:
        1. 价格上涨但主力净流出 → 主力在高位出货
        2. 价格下跌但主力净流入 → 主力在低位吸筹
        3. 超大单流出但小单流入 → 机构离场散户接盘
        """
        alerts = []

        if df.empty:
            return alerts

        required_cols = ['代码', '名称', '涨跌幅', '主力净流入-净额',
                         '超大单净流入-净额', '大单净流入-净额',
                         '中单净流入-净额', '小单净流入-净额']

        for _, row in df.iterrows():
            missing = [c for c in required_cols if c not in row.index or pd.isna(row[c])]
            if missing:
                continue

            price_chg = float(row['涨跌幅'])
            main_net = float(row['主力净流入-净额'])
            main_ratio = float(row.get('主力净流入-净占比', 0))
            super_large = float(row['超大单净流入-净额'])
            large = float(row['大单净流入-净额'])
            medium = float(row['中单净流入-净额'])
            small = float(row['小单净流入-净额'])

            pattern, signal = self.classify_flow_pattern(row)

            alert = FundFlowAlert(
                code=str(row['代码']),
                name=str(row['名称']),
                price_change=price_chg,
                main_net_inflow=main_net,
                main_net_ratio=main_ratio,
                super_large_net=super_large,
                large_net=large,
                medium_net=medium,
                small_net=small,
                divergence_type=pattern,
                signal=signal,
                alert_level="none"
            )

            # 生成预警
            if signal == "bearish" and abs(price_chg) > self.DIVERGENCE_PRICE_THRESHOLD:
                alert.alert_level = "high"
                alert.message = f"{pattern}: 涨幅{price_chg:+.2f}%但主力净流出{main_net/1e8:.2f}亿"
            elif signal == "divergence_bullish" and abs(price_chg) > self.DIVERGENCE_PRICE_THRESHOLD:
                alert.alert_level = "medium"
                alert.message = f"{pattern}: 跌幅{price_chg:+.2f}%但主力净流入{main_net/1e8:.2f}亿，关注反弹机会"
            elif signal == "divergence_bearish" and abs(price_chg) > self.DIVERGENCE_PRICE_THRESHOLD:
                alert.alert_level = "medium"
                # FIX 2026-08-01: parenthesize before /1e8 — previously `super_large + large/1e8`
                # only divided large, leaving super_large in raw yuan (huge number in message).
                alert.message = f"{pattern}: 涨幅{price_chg:+.2f}%但超大单+大单净流出{(super_large+large)/1e8:.2f}亿"

            if super_large < -self.MAIN_FLOW_THRESHOLD and price_chg > 0:
                alert.alert_level = "high"
                alert.signal = "bearish"
                alert.message = f"⚠️ 超大单大幅流出{abs(super_large)/1e8:.2f}亿，股价却涨{price_chg:+.2f}%，警惕出货"

            if alert.alert_level != "none":
                alerts.append(alert)

        return alerts

    def get_flow_ranking(self, df: pd.DataFrame, top_n: int = 20) -> pd.DataFrame:
        """资金净流入排名"""
        if df.empty or '主力净流入-净额' not in df.columns:
            return df

        return df.sort_values('主力净流入-净额', ascending=False).head(top_n)

    def get_flow_leaving_ranking(self, df: pd.DataFrame, top_n: int = 20) -> pd.DataFrame:
        """资金净流出排名(主力撤离)"""
        if df.empty or '主力净流入-净额' not in df.columns:
            return df

        return df.sort_values('主力净流入-净额', ascending=True).head(top_n)

    def generate_report(self, df: pd.DataFrame, alerts: list[FundFlowAlert]) -> str:
        """生成资金流向分析报告"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [
            "# ETF资金流向分析报告",
            f"**生成时间**: {now}",
            f"**分析ETF总数**: {len(df)}",
            "",
        ]

        if not df.empty and '主力净流入-净额' in df.columns:
            total_main_flow = df['主力净流入-净额'].sum()
            inflow_count = (df['主力净流入-净额'] > 0).sum()
            outflow_count = (df['主力净流入-净额'] < 0).sum()

            lines.append("## 市场资金概况")
            lines.append(f"- 主力净流入合计: **{total_main_flow/1e8:.2f}亿元**")
            lines.append(f"- 资金净流入ETF数: {inflow_count}")
            lines.append(f"- 资金净流出ETF数: {outflow_count}")
            lines.append("")

        # 预警统计
        high_risk = [a for a in alerts if a.alert_level == "high"]
        medium_risk = [a for a in alerts if a.alert_level == "medium"]
        lines.append("## 预警统计")
        lines.append(f"- 🔴 高风险: {len(high_risk)} 条")
        lines.append(f"- 🟡 中风险: {len(medium_risk)} 条")
        lines.append("")

        if alerts:
            lines.append("## 预警详情")
            lines.append("| 代码 | 名称 | 涨跌幅 | 主力净流入 | 模式 | 风险 | 提示 |")
            lines.append("|------|------|--------|-----------|------|------|------|")
            for a in sorted(alerts, key=lambda x: (0 if x.alert_level=="high" else 1, abs(x.price_change)), reverse=False):
                net_yi = a.main_net_inflow / 1e8 if a.main_net_inflow else 0
                lines.append(
                    f"| {a.code} | {a.name} | {a.price_change:+.2f}% | "
                    f"{net_yi:+.2f}亿 | {a.divergence_type} | {a.alert_level} | {a.message} |"
                )
            lines.append("")

        # 资金流入TOP10
        top_inflow = self.get_flow_ranking(df, 10)
        if not top_inflow.empty and '主力净流入-净额' in top_inflow.columns:
            lines.append("## 资金净流入TOP10")
            lines.append("| 代码 | 名称 | 最新价 | 涨跌幅 | 主力净流入 | 超大单 | 大单 |")
            lines.append("|------|------|--------|--------|-----------|--------|------|")
            for _, r in top_inflow.iterrows():
                lines.append(
                    f"| {r['代码']} | {r['名称']} | {r['最新价']:.4f} | "
                    f"{r.get('涨跌幅', 0):+.2f}% | "
                    f"{r['主力净流入-净额']/1e8:+.2f}亿 | "
                    f"{r.get('超大单净流入-净额',0)/1e8:+.2f}亿 | "
                    f"{r.get('大单净流入-净额',0)/1e8:+.2f}亿 |"
                )
            lines.append("")

        # 资金流出TOP10
        top_outflow = self.get_flow_leaving_ranking(df, 10)
        if not top_outflow.empty and '主力净流入-净额' in top_outflow.columns:
            lines.append("## 资金净流出TOP10")
            lines.append("| 代码 | 名称 | 最新价 | 涨跌幅 | 主力净流入 | 超大单 | 大单 |")
            lines.append("|------|------|--------|--------|-----------|--------|------|")
            for _, r in top_outflow.iterrows():
                lines.append(
                    f"| {r['代码']} | {r['名称']} | {r['最新价']:.4f} | "
                    f"{r.get('涨跌幅', 0):+.2f}% | "
                    f"{r['主力净流入-净额']/1e8:+.2f}亿 | "
                    f"{r.get('超大单净流入-净额',0)/1e8:+.2f}亿 | "
                    f"{r.get('大单净流入-净额',0)/1e8:+.2f}亿 |"
                )
            lines.append("")

        return "\n".join(lines)

    def run(self, save_report: bool = True) -> tuple[str, list[FundFlowAlert]]:
        """执行完整的资金流向分析"""
        df = self.fetch_data()
        if df.empty:
            return "## ETF资金流向分析\n\n⚠️ 无法获取数据", []

        alerts = self.detect_divergences(df)
        report = self.generate_report(df, alerts)

        if save_report:
            today = date.today().isoformat()
            report_path = self.cache_dir / f"fund_flow_report_{today}.md"
            report_path.write_text(report, encoding="utf-8")

            for alert in alerts:
                with open(self.alert_history_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(alert.to_dict(), ensure_ascii=False) + "\n")

            logger.info(f"[FLOW] 报告已保存: {report_path}")

        return report, alerts


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    analyzer = FundFlowAnalyzer()
    report, alerts = analyzer.run()
    print(report)
    print(f"\n共 {len(alerts)} 条预警")
