"""
同类排名与评级整合模块

学习东方财富天天基金的排名体系:
- 同类基金百分位排名
- 四分位排名(优秀/良好/一般/不佳)
- 四家评级机构: 上海证券、招商证券、济安金信、晨星
- 季度/年度阶段涨幅对比

数据来源:
- akshare.fund_info_index_em() - 指数型基金净值+收益率
- akshare.fund_name_em() - 基金基本信息
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RankingResult:
    """排名结果"""
    code: str
    name: str
    fund_type: str
    period: str          # "近1周", "近1月", "近3月", "近6月", "近1年"
    return_rate: float   # 收益率%
    rank: int            # 排名
    total_count: int     # 同类总数
    percentile: float    # 百分位(0-100，越高越好)
    quartile: str        # "优秀"(前25%), "良好"(25-50%), "一般"(50-75%), "不佳"(后25%)
    rating_shanghai: Optional[str] = None
    rating_cmb: Optional[str] = None
    rating_jianan: Optional[str] = None
    rating_morningstar: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


class RankingManager:
    """
    ETF同类排名管理器

    核心功能:
    1. 获取全量ETF数据并计算同类排名
    2. 多周期排名(近1周/1月/3月/6月/1年)
    3. 四分位评级
    4. 评级机构数据整合
    """

    QUARTILE_LABELS = {
        (0, 25): "优秀",
        (25, 50): "良好",
        (50, 75): "一般",
        (75, 101): "不佳",
    }

    RATING_MAP = {
        "5": "★★★★★",
        "4": "★★★★",
        "3": "★★★",
        "2": "★★",
        "1": "★",
    }

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or Path(__file__).parent.parent / "data" / "live_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def fetch_index_funds(self) -> pd.DataFrame:
        """获取指数型基金数据"""
        try:
            import akshare as ak
            from ..utils.thread_timeout import run_with_timeout
            df = run_with_timeout(
                ak.fund_info_index_em, symbol="全部", indicator="被动指数型", timeout=30)
            logger.info(f"[RANK] 获取到 {len(df)} 只指数型基金")
            return df
        except Exception as e:
            logger.error(f"[RANK] 获取指数基金数据失败: {e}")
            return pd.DataFrame()

    def calculate_percentile_rank(self, df: pd.DataFrame, period_col: str) -> pd.DataFrame:
        """
        计算百分位排名

        percentile = (排名 - 1) / (总数 - 1) * 100
        百分位越高说明相对同类表现越好
        """
        if df.empty or period_col not in df.columns:
            return df

        result = df.copy()
        sorted_df = result.sort_values(period_col, ascending=False)
        result['rank'] = range(1, len(sorted_df) + 1)
        result = result.sort_index()

        total = len(result)
        if total > 1:
            result['percentile'] = (result['rank'] - 1) / (total - 1) * 100
        else:
            result['percentile'] = 50.0

        result['quartile'] = result['percentile'].apply(self._percentile_to_quartile)

        return result

    @staticmethod
    def _percentile_to_quartile(p: float) -> str:
        """百分位转四分位"""
        if p < 25:
            return "优秀"
        elif p < 50:
            return "良好"
        elif p < 75:
            return "一般"
        else:
            return "不佳"

    def get_ranking_for_etf(self, df: pd.DataFrame, code: str, periods: list[str] = None) -> list[RankingResult]:
        """获取指定ETF的多周期排名"""
        if df.empty:
            return []

        etf_row = df[df['基金代码'] == code]
        if etf_row.empty:
            return []

        row = etf_row.iloc[0]
        results = []

        period_map = {
            "近1周": "近1周",
            "近1月": "近1月",
            "近3月": "近3月",
            "近6月": "近6月",
            "近1年": "近1年",
        }

        for key, col in period_map.items():
            if col in df.columns and pd.notna(row.get(col)):
                ret = float(row[col])
                rank = int(row.get('rank', 0))
                total = len(df)
                pct = float(row.get('percentile', 50))
                quartile = self._percentile_to_quartile(pct)

                results.append(RankingResult(
                    code=str(row.get('基金代码', code)),
                    name=str(row.get('基金简称', '')),
                    fund_type=str(row.get('基金类型', '')),
                    period=key,
                    return_rate=ret,
                    rank=rank,
                    total_count=total,
                    percentile=pct,
                    quartile=quartile,
                ))

        return results

    def generate_ranking_report(self, df: pd.DataFrame, top_n: int = 30) -> str:
        """生成排名报告"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [
            "# ETF同类排名报告",
            f"**生成时间**: {now}",
            f"**样本数量**: {len(df)} 只指数型基金",
            "",
        ]

        period_cols = ["近1周", "近1月", "近3月", "近6月", "近1年"]
        for period in period_cols:
            if period not in df.columns:
                continue

            lines.append(f"## {period}收益率排名 TOP{top_n}")
            lines.append("| 排名 | 代码 | 名称 | 收益率 | 百分位 | 四分位 |")
            lines.append("|------|------|------|--------|--------|--------|")

            sorted_df = df.sort_values(period, ascending=False).head(top_n)
            for i, (_, r) in enumerate(sorted_df.iterrows(), 1):
                pct = r.get('percentile', 0)
                quartile = self._percentile_to_quartile(float(pct)) if pd.notna(pct) else "N/A"
                lines.append(
                    f"| {i} | {r['基金代码']} | {r['基金简称']} | "
                    f"{r[period]:+.2f}% | {pct:.1f}% | {quartile} |"
                )
            lines.append("")

        return "\n".join(lines)

    def run(self, save_report: bool = True) -> tuple[str, pd.DataFrame]:
        """执行排名分析"""
        df = self.fetch_index_funds()
        if df.empty:
            return "# ETF同类排名\n\n⚠️ 无法获取数据", df

        # 确定使用的收益率列
        period_cols = ["近1周", "近1月", "近3月", "近6月", "近1年"]
        available_cols = [c for c in period_cols if c in df.columns]

        if available_cols:
            primary_col = available_cols[-1]  # 优先用近1年
            df = self.calculate_percentile_rank(df, primary_col)

        report = self.generate_ranking_report(df)

        if save_report:
            today = date.today().isoformat()
            report_path = self.cache_dir / f"ranking_report_{today}.md"
            report_path.write_text(report, encoding="utf-8")
            logger.info(f"[RANK] 报告已保存: {report_path}")

        return report, df


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    manager = RankingManager()
    report, df = manager.run()
    print(report[:3000])
