"""
持仓重叠度分析模块

学习东方财富ETF详情页的持仓数据:
- 股票持仓明细及占比
- 债券持仓
- 行业配置
- 持有人结构(机构/个人)

功能:
1. 两只ETF之间的持仓重叠度计算
2. 行业配置相似度
3. 集中度风险检测
4. Smart Beta ETF重叠分析
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class OverlapResult:
    """重叠度分析结果"""
    etf_a: str          # ETF A代码
    etf_b: str          # ETF B代码
    overlap_ratio: float  # 重叠率(0-1)
    common_holdings: int  # 共同持仓数
    total_holdings_a: int
    total_holdings_b: int
    max_single_overlap: float  # 最大单一重叠持仓占比
    sector_overlap: float      # 行业配置重叠率
    risk_level: str           # "high", "medium", "low"
    recommendation: str       # 建议
    common_detail: list = field(default_factory=list)  # 共同持仓明细 [{code,name_a,weight_a,name_b,weight_b,max_weight}]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


class HoldingsOverlapAnalyzer:
    """
    ETF持仓重叠度分析器

    核心算法:
    1. Jaccard相似度: |A∩B| / |A∪B| (基于持仓股票代码)
    2. 加权重叠率: sum(min(wa, wb)) / sum(max(wa, wb)) (基于持仓权重)
    3. 行业配置余弦相似度
    """

    OVERLAP_HIGH_THRESHOLD = 0.6   # 重叠率>60%视为高度重叠
    OVERLAP_MEDIUM_THRESHOLD = 0.3 # 重叠率>30%视为中度重叠

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or Path(__file__).parent.parent / "data" / "live_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def jaccard_similarity(set_a: set, set_b: set) -> float:
        """Jaccard相似度: |A∩B| / |A∪B|"""
        if not set_a and not set_b:
            return 0.0
        intersection = set_a & set_b
        union = set_a | set_b
        return len(intersection) / len(union) if union else 0.0

    @staticmethod
    def weighted_overlap(weights_a: dict[str, float], weights_b: dict[str, float]) -> float:
        """
        加权重叠率

        对每只共同持仓，取两边权重的较小值之和，除以两边最大权重之和。
        结果越接近1表示重叠越高。
        """
        all_codes = set(weights_a.keys()) | set(weights_b.keys())
        if not all_codes:
            return 0.0

        sum_min = sum(min(weights_a.get(c, 0), weights_b.get(c, 0)) for c in all_codes)
        sum_max = sum(max(weights_a.get(c, 0), weights_b.get(c, 0)) for c in all_codes)

        return sum_min / sum_max if sum_max > 0 else 0.0

    @staticmethod
    def sector_cosine_similarity(sector_a: dict[str, float], sector_b: dict[str, float]) -> float:
        """行业配置余弦相似度"""
        all_sectors = set(sector_a.keys()) | set(sector_b.keys())
        vec_a = np.array([sector_a.get(s, 0) for s in all_sectors], dtype=float)
        vec_b = np.array([sector_b.get(s, 0) for s in all_sectors], dtype=float)

        dot = np.dot(vec_a, vec_b)
        norm_a = np.linalg.norm(vec_a)
        norm_b = np.linalg.norm(vec_b)

        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    @staticmethod
    def find_common_holdings(etf_a_holdings: list[dict], etf_b_holdings: list[dict]) -> list[dict]:
        """找出两只ETF的共同持仓"""
        a_map = {h['code']: h for h in etf_a_holdings}
        b_map = {h['code']: h for h in etf_b_holdings}

        common = []
        for code in set(a_map.keys()) & set(b_map.keys()):
            common.append({
                'code': code,
                'name_a': a_map[code].get('name', ''),
                'weight_a': a_map[code].get('weight', 0),
                'name_b': b_map[code].get('name', ''),
                'weight_b': b_map[code].get('weight', 0),
                'max_weight': max(a_map[code].get('weight', 0), b_map[code].get('weight', 0)),
            })

        return sorted(common, key=lambda x: x['max_weight'], reverse=True)

    def analyze_pair(self, etf_a_holdings: list[dict], etf_b_holdings: list[dict],
                     etf_a_name: str = "", etf_b_name: str = "",
                     sector_a: Optional[dict] = None,
                     sector_b: Optional[dict] = None) -> OverlapResult:
        """
        分析两只ETF的持仓重叠度

        Args:
            etf_a_holdings: ETF A持仓列表 [{"code": "...", "name": "...", "weight": 0.05}, ...]
            etf_b_holdings: ETF B持仓列表
            sector_a: ETF A行业配置 {"科技": 0.3, "金融": 0.2, ...}
            sector_b: ETF B行业配置

        Returns:
            OverlapResult
        """
        codes_a = {h['code'] for h in etf_a_holdings}
        codes_b = {h['code'] for h in etf_b_holdings}

        jaccard = self.jaccard_similarity(codes_a, codes_b)
        weights_a = {h['code']: h['weight'] for h in etf_a_holdings}
        weights_b = {h['code']: h['weight'] for h in etf_b_holdings}
        weighted_ov = self.weighted_overlap(weights_a, weights_b)

        # 综合重叠率 = Jaccard * 0.3 + 加权重叠 * 0.7
        overlap = jaccard * 0.3 + weighted_ov * 0.7

        # 行业重叠
        sector_ov = 0.0
        if sector_a and sector_b:
            sector_ov = self.sector_cosine_similarity(sector_a, sector_b)

        common = self.find_common_holdings(etf_a_holdings, etf_b_holdings)
        max_single = max((c['max_weight'] for c in common), default=0)

        # 风险等级
        if overlap > self.OVERLAP_HIGH_THRESHOLD:
            risk = "high"
            rec = "⚠️ 高度重叠: 同时持有这两只ETF等于集中押注相似组合，建议二选一或调整配置"
        elif overlap > self.OVERLAP_MEDIUM_THRESHOLD:
            risk = "medium"
            rec = "⚡ 中度重叠: 存在较多共同持仓，注意组合分散度"
        else:
            risk = "low"
            rec = "✅ 重叠度较低，组合分散效果良好"

        return OverlapResult(
            etf_a=etf_a_name or "ETF_A",
            etf_b=etf_b_name or "ETF_B",
            overlap_ratio=overlap,
            common_holdings=len(common),
            common_detail=common,
            total_holdings_a=len(etf_a_holdings),
            total_holdings_b=len(etf_b_holdings),
            max_single_overlap=max_single,
            sector_overlap=sector_ov,
            risk_level=risk,
            recommendation=rec,
        )

    def generate_report(self, results: list[OverlapResult]) -> str:
        """生成重叠度分析报告"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [
            "# ETF持仓重叠度分析报告",
            f"**生成时间**: {now}",
            f"**分析对数**: {len(results)}",
            "",
        ]

        high_risk = [r for r in results if r.risk_level == "high"]
        medium_risk = [r for r in results if r.risk_level == "medium"]

        lines.append("## 风险统计")
        lines.append(f"- 🔴 高度重叠: {len(high_risk)} 对")
        lines.append(f"- 🟡 中度重叠: {len(medium_risk)} 对")
        lines.append(f"- 🟢 低度重叠: {len(results) - len(high_risk) - len(medium_risk)} 对")
        lines.append("")

        if results:
            lines.append("## 分析详情")
            lines.append("| ETF A | ETF B | 重叠率 | 共同持仓 | 最大单只重叠 | 行业重叠 | 风险 |")
            lines.append("|-------|-------|--------|----------|-------------|----------|------|")
            for r in sorted(results, key=lambda x: x.overlap_ratio, reverse=True):
                lines.append(
                    f"| {r.etf_a} | {r.etf_b} | {r.overlap_ratio:.1%} | "
                    f"{r.common_holdings} | {r.max_single_overlap:.1%} | "
                    f"{r.sector_overlap:.1%} | {r.risk_level} |"
                )
            lines.append("")

            lines.append("## 共同持仓明细")
            for r in results:
                if r.common_holdings > 0:
                    lines.append(f"\n### {r.etf_a} vs {r.etf_b}")
                    lines.append(f"**重叠率**: {r.overlap_ratio:.1%} | **风险**: {r.risk_level}")
                    lines.append(f"**建议**: {r.recommendation}")
                    lines.append("")
                    lines.append("| 股票 | A权重 | B权重 | 最大权重 |")
                    lines.append("|------|-------|-------|---------|")
                    for c in r.common_detail:
                        name = c.get("name_a") or c.get("name_b") or c.get("code", "")
                        lines.append(
                            f"| {name}({c.get('code')}) | {c.get('weight_a', 0):.2%} "
                            f"| {c.get('weight_b', 0):.2%} | {c.get('max_weight', 0):.2%} |"
                        )

        return "\n".join(lines)

    def run_demo(self) -> tuple[str, list[OverlapResult]]:
        """
        使用示例数据运行演示

        实际使用时从东财API获取真实持仓数据
        """
        # 示例: 沪深300ETF vs 中证500ETF (部分重叠)
        etf_a_holdings = [
            {"code": "600519", "name": "贵州茅台", "weight": 0.035},
            {"code": "601398", "name": "工商银行", "weight": 0.028},
            {"code": "600036", "name": "招商银行", "weight": 0.025},
            {"code": "000858", "name": "五粮液", "weight": 0.020},
            {"code": "601318", "name": "中国平安", "weight": 0.019},
            {"code": "600276", "name": "恒瑞医药", "weight": 0.015},
            {"code": "000333", "name": "美的集团", "weight": 0.014},
            {"code": "600900", "name": "长江电力", "weight": 0.013},
        ]

        etf_b_holdings = [
            {"code": "600519", "name": "贵州茅台", "weight": 0.008},
            {"code": "601398", "name": "工商银行", "weight": 0.006},
            {"code": "002594", "name": "比亚迪", "weight": 0.012},
            {"code": "300750", "name": "宁德时代", "weight": 0.015},
            {"code": "002475", "name": "立讯精密", "weight": 0.010},
            {"code": "688981", "name": "中芯国际", "weight": 0.009},
        ]

        sector_a = {"金融": 0.25, "消费": 0.20, "医药": 0.12, "电力": 0.10, "制造": 0.15, "其他": 0.18}
        sector_b = {"电子": 0.25, "汽车": 0.15, "新能源": 0.20, "金融": 0.08, "医药": 0.07, "其他": 0.25}

        analyzer = HoldingsOverlapAnalyzer()
        result = analyzer.analyze_pair(
            etf_a_holdings, etf_b_holdings,
            etf_a_name="沪深300ETF",
            etf_b_name="科创50ETF",
            sector_a=sector_a,
            sector_b=sector_b,
        )

        report = analyzer.generate_report([result])
        return report, [result]


def _etf_label(code: str) -> str:
    """ETF 显示名：优先 config 名称，否则回退代码。"""
    try:
        from ..config_loader import load_etfs
        name = load_etfs().get(code, {}).get("name", "")
        return f"{name}({code})" if name else code
    except Exception:
        return code


def _load_real_holdings(code: str) -> list[dict]:
    """从真实持仓缓存读最新季度持仓；缺失/为空时 fail loud。"""
    from .holdings_fetcher import get_cached_holdings, _latest_quarter_holdings
    cached = get_cached_holdings(code)
    if cached is None:
        raise ValueError(
            f"[holdings_overlap] 缓存中无 {code} 持仓数据，请先运行 "
            "`python -m etf_platform.analysis.holdings_fetcher --refresh`"
        )
    holdings = _latest_quarter_holdings(cached)
    if not holdings:
        raise ValueError(f"[holdings_overlap] {code} 缓存无股票持仓数据")
    return holdings


def run_real_pair(code_a: str, code_b: str) -> tuple[str, list[OverlapResult]]:
    """用真实持仓缓存分析两只 ETF 的重叠度并生成报告。"""
    from .holdings_fetcher import get_sector_exposure
    analyzer = HoldingsOverlapAnalyzer()
    result = analyzer.analyze_pair(
        _load_real_holdings(code_a),
        _load_real_holdings(code_b),
        etf_a_name=_etf_label(code_a),
        etf_b_name=_etf_label(code_b),
        sector_a=get_sector_exposure(code_a),
        sector_b=get_sector_exposure(code_b),
    )
    report = analyzer.generate_report([result])
    return report, [result]


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    args = sys.argv[1:]
    if len(args) == 2:
        try:
            report, _results = run_real_pair(args[0], args[1])
        except ValueError as e:
            print(e, file=sys.stderr)
            return 1
        print(report)
        return 0
    # 无参数：保留原 run_demo() 演示分支（向后兼容）
    analyzer = HoldingsOverlapAnalyzer()
    report, _results = analyzer.run_demo()
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
