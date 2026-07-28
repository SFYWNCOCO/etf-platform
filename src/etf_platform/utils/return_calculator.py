"""
收益测算器 - 基于历史收益率模拟不同申购金额的未来收益

学习东方财富天天基金的"收益测算器"功能:
- 输入申购金额
- 根据过往业绩(近1月/3月/6月/1年)估算收益
- 定投 vs 单笔收益比较
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ReturnEstimate:
    """收益估算结果"""
    etf_code: str
    etf_name: str
    principal: float       # 本金(元)
    period: str            # "近1月", "近3月", "近6月", "近1年"
    historical_return: float  # 历史收益率%
    estimated_gain: float  # 预估收益(元)
    estimated_value: float # 预估总市值(元)
    annualized_return: float  # 年化收益率%
    risk_level: str        # "低", "中", "高"
    disclaimer: str = "仅供参考，过往业绩不预示未来表现"
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class DCAComparison:
    """定投vs单笔比较"""
    etf_code: str
    etf_name: str
    monthly_amount: float  # 每月定投金额
    months: int            # 定投月数
    lump_sum_amount: float # 等价单笔金额
    dca_total_cost: float  # 定投总成本
    lump_sum_total: float  # 单笔总金额
    dca_estimated_return: float
    lump_sum_estimated_return: float
    difference: float      # 差额
    winner: str            # "dca" or "lump_sum" or "equal"
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


class ReturnCalculator:
    """
    ETF收益测算器

    功能:
    1. 基于历史收益率估算给定本金的预期收益
    2. 计算年化收益率
    3. 定投 vs 单笔收益比较
    4. 风险提示
    """

    PERIOD_DAYS = {
        "近1月": 21,
        "近3月": 63,
        "近6月": 126,
        "近1年": 252,
    }

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or Path(__file__).parent.parent / "data" / "live_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def estimate_return(self, etf_code: str, etf_name: str,
                        principal: float, period: str,
                        historical_return_pct: float) -> ReturnEstimate:
        """
        估算收益

        Args:
            etf_code: ETF代码
            etf_name: ETF名称
            principal: 申购金额(元)
            period: 时间段
            historical_return_pct: 该时间段的历史收益率(%)

        Returns:
            ReturnEstimate
        """
        days = self.PERIOD_DAYS.get(period, 252)
        annualized = historical_return_pct * (365 / days) if days > 0 else historical_return_pct

        # 预估收益 = 本金 × 历史收益率%
        estimated_gain = principal * historical_return_pct / 100
        estimated_value = principal + estimated_gain

        # 风险等级
        abs_ret = abs(historical_return_pct)
        if abs_ret > 30:
            risk = "高"
        elif abs_ret > 15:
            risk = "中"
        else:
            risk = "低"

        return ReturnEstimate(
            etf_code=etf_code,
            etf_name=etf_name,
            principal=principal,
            period=period,
            historical_return=historical_return_pct,
            estimated_gain=estimated_gain,
            estimated_value=estimated_value,
            annualized_return=annualized,
            risk_level=risk,
        )

    def compare_dca_vs_lump(self, etf_code: str, etf_name: str,
                            monthly_amount: float, months: int,
                            historical_return_pct: float) -> DCAComparison:
        """
        定投 vs 单笔收益比较

        简化模型:
        - 定投: 每月投入固定金额，按历史月收益率复利估算
        - 单笔: 一次性投入等额资金

        注意: 这是简化估算，实际定投收益取决于买入时点
        """
        monthly_rate = historical_return_pct / 100 / 3  # 近似月收益率
        lump_sum_amount = monthly_amount * months

        # 定投终值(普通年金终值公式)
        if monthly_rate != 0:
            dca_fv = monthly_amount * ((1 + monthly_rate) ** months - 1) / monthly_rate
        else:
            dca_fv = monthly_amount * months

        # 单笔终值
        lump_fv = lump_sum_amount * (1 + monthly_rate) ** months

        dca_gain = dca_fv - monthly_amount * months
        lump_gain = lump_fv - lump_sum_amount

        if dca_gain > lump_gain * 1.05:
            winner = "dca"
        elif lump_gain > dca_gain * 1.05:
            winner = "lump_sum"
        else:
            winner = "equal"

        return DCAComparison(
            etf_code=etf_code,
            etf_name=etf_name,
            monthly_amount=monthly_amount,
            months=months,
            lump_sum_amount=lump_sum_amount,
            dca_total_cost=monthly_amount * months,
            lump_sum_total=lump_sum_amount,
            dca_estimated_return=dca_gain,
            lump_sum_estimated_return=lump_gain,
            difference=dca_gain - lump_gain,
            winner=winner,
        )

    def generate_report(self, estimates: list[ReturnEstimate],
                        comparisons: Optional[list[DCAComparison]] = None) -> str:
        """生成收益测算报告"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [
            "# ETF收益测算报告",
            f"**生成时间**: {now}",
            "",
        ]

        if estimates:
            lines.append("## 收益估算")
            for e in estimates:
                lines.append(f"### {e.etf_name} ({e.etf_code})")
                lines.append(f"- 本金: **{e.principal:,.0f}元**")
                lines.append(f"- 参考周期: {e.period}")
                lines.append(f"- 历史收益率: **{e.historical_return:+.2f}%**")
                lines.append(f"- 年化收益率: **{e.annualized_return:+.2f}%**")
                lines.append(f"- 预估收益: **{e.estimated_gain:+,.2f}元**")
                lines.append(f"- 预估市值: **{e.estimated_value:,.2f}元**")
                lines.append(f"- 风险等级: **{e.risk_level}**")
                lines.append(f"- ⚠️ {e.disclaimer}")
                lines.append("")

        if comparisons:
            lines.append("## 定投 vs 单笔比较")
            for c in comparisons:
                lines.append(f"### {c.etf_name} ({c.etf_code})")
                lines.append(f"- 定投金额: {c.monthly_amount:,.0f}元/月 × {c.months}个月")
                lines.append(f"- 定投预估收益: **{c.dca_estimated_return:+,.2f}元**")
                lines.append(f"- 单笔预估收益: **{c.lump_sum_estimated_return:+,.2f}元**")
                lines.append(f"- 差额: {c.difference:+,.2f}元")
                lines.append(f"- 推荐方式: **{'定投' if c.winner == 'dca' else '单笔' if c.winner == 'lump_sum' else '相近'}**")
                lines.append("")

        return "\n".join(lines)

    def run_demo(self) -> str:
        """运行演示"""
        # 示例数据
        demo_data = [
            ("159941", "纳指ETF广发", 10000, "近1年", 17.00),
            ("510300", "沪深300ETF华泰柏瑞", 10000, "近1年", 8.50),
            ("512690", "医药ETF国泰", 10000, "近1年", 12.30),
        ]

        calc = ReturnCalculator()
        estimates = []
        comparisons = []

        for code, name, principal, period, ret in demo_data:
            est = calc.estimate_return(code, name, principal, period, ret)
            estimates.append(est)

            comp = calc.compare_dca_vs_lump(code, name, principal / 12, 12, ret)
            comparisons.append(comp)

        report = calc.generate_report(estimates, comparisons)

        today = datetime.now().date().isoformat()
        report_path = self.cache_dir / f"return_estimate_{today}.md"
        report_path.write_text(report, encoding="utf-8")

        return report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    calc = ReturnCalculator()
    report = calc.run_demo()
    print(report)
