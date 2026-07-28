"""DeepMonitor 引擎 + CLI main 入口.

从原 deep.py 提取,实现逻辑完全一致.仅做必要的相对导入调整.
"""
from collections import defaultdict

# 注意: 本模块位于 etf_platform/analysis/deep_sub/ 下,
# 到 etf_platform.config_loader 需要 3 个点 (...)
from ...config_loader import load_etfs

from .materials import get_all_materials
from .personnel import PERSONNEL_RISK_DB
from .tech_milestones import TECH_MILESTONES_V2


class DeepMonitor:
    """P1-P2 深度监控引擎"""

    def __init__(self):
        self.alerts = []

    def run_material_monitor(self):
        """材料价格监控"""
        print("\n" + "=" * 70)
        print("  🏭 P1: 实时材料价格监控")
        print("=" * 70)
        print(f"  {'材料':<16} {'价格':<16} {'趋势':<12} {'方向':<8} {'预警'}")
        print("  " + "-" * 70)

        all_materials = get_all_materials()
        for mat_name, mat in all_materials.items():
            flag = "🔴" if mat.get("warning","").startswith("🔴") else (
                "🟡" if mat.get("warning","").startswith("🟡") else (
                "🟢" if mat.get("warning","").startswith("🟢") else "⚪"
            ))
            print(f"  {flag} {mat_name:<14} {mat['current']:<16} {mat['trend']:<12} {mat['impact_direction']:<8} {mat['note'][:35]}")

            # 生成可操作警报
            if mat.get("warning","").startswith("🔴"):
                self.alerts.append({
                    "type": "材料价格",
                    "level": "🔴 紧急",
                    "material": mat_name,
                    "price": mat["current"],
                    "trend": mat["trend"],
                    "affects": mat["affects"],
                    "note": mat["note"],
                })

        # 按材料-ETF关联推荐交易
        print("\n  📊 材料→ETF 交易映射:")
        mat_etf_signals = defaultdict(lambda: {"long": [], "short": []})
        for mat_name, mat in all_materials.items():
            for etf_code in mat["affects"]:
                if mat["impact_direction"] in ("利空",):
                    mat_etf_signals[etf_code]["short"].append(mat_name)
                elif mat["impact_direction"] in ("利好",):
                    mat_etf_signals[etf_code]["long"].append(mat_name)

        etfs = load_etfs()
        for etf_code, signals in mat_etf_signals.items():
            if etf_code not in etfs:
                continue
            name = etfs[etf_code]["name"]
            if signals["short"]:
                print(f"  🔴 {etf_code} {name:12s} ← {', '.join(signals['short'][:3])}")
            if signals["long"]:
                print(f"  🟢 {etf_code} {name:12s} ← {', '.join(signals['long'][:3])}")

    def run_personnel_monitor(self):
        """人员风险监控"""
        print("\n" + "=" * 70)
        print("  👤 P2: 关键人员风险监控")
        print("=" * 70)

        # 按不可替代度排序
        sorted_personnel = sorted(PERSONNEL_RISK_DB, key=lambda x: -x["irreplaceable"])

        for p in sorted_personnel:
            flag = "🔴" if p["irreplaceable"] > 0.80 else ("🟡" if p["irreplaceable"] > 0.65 else "⚪")
            age_str = f"年龄{p['age']}" if p["age"] else ""
            tenure_str = f"任期{p['tenure_yrs']}年" if p["tenure_yrs"] else ""

            print(f"\n  {flag} {p['company']}({p['code']}) — {p['person']}")
            print(f"     角色: {p['role']} | {age_str} {tenure_str} | 不可替代={p['irreplaceable']:.0%}")
            print(f"     风险: {p['risk']}")
            print(f"     影响ETF: {', '.join(p['affects_etf'])} | 预期冲击: {p['impact']:+.0%}")
            print(f"     预警信号: {', '.join(p['watch_signals'][:2])}")

            # 年龄风险评分
            age_risk = 0
            if p["age"]:
                if p["age"] > 70:
                    age_risk = 0.15
                elif p["age"] > 65:
                    age_risk = 0.10
                elif p["age"] > 60:
                    age_risk = 0.05

            total_risk = p["irreplaceable"] * 0.6 + age_risk
            if total_risk > 0.5:
                self.alerts.append({
                    "type": "人员风险",
                    "level": "🔴 高" if total_risk > 0.6 else "🟡 中",
                    "company": p["company"],
                    "person": p["person"],
                    "risk_score": round(total_risk, 2),
                    "affects_etf": p["affects_etf"],
                    "impact": p["impact"],
                })

        # 最高风险总结
        high_risk = [p for p in sorted_personnel if p["irreplaceable"] * 0.6 + (
            0.15 if (p["age"] or 0) > 70 else 0.10 if (p["age"] or 0) > 65 else 0.05 if (p["age"] or 0) > 60 else 0
        ) > 0.5]
        if high_risk:
            print(f"\n  ⚠️  高人员风险警报 ({len(high_risk)}人):")
            for p in high_risk:
                risk = round(p["irreplaceable"] * 0.6 + (0.15 if (p["age"] or 0) > 70 else 0.10 if (p["age"] or 0) > 65 else 0.05 if (p["age"] or 0) > 60 else 0), 2)
                etfs = ", ".join(p["affects_etf"][:2])
                print(f"     {p['company']} {p['person']} → {etfs} (风险={risk:.0%})")

    def run_tech_monitor(self):
        """技术里程碑进度"""
        print("\n" + "=" * 70)
        print("  🔬 P1: 技术里程碑进度追踪")
        print("=" * 70)

        for m in TECH_MILESTONES_V2:
            prob_flag = "🟢" if m["probability"] > 0.7 else ("🟡" if m["probability"] > 0.5 else "🔴")
            print(f"\n  {prob_flag} {m['name']} — {m['target']} (概率{m['probability']:.0%})")
            print(f"     总体状态: {m['progress']}")
            print(f"     影响: {', '.join(m['affects'])}")

            # 里程碑子步骤
            for step in m["milestones"]:
                sflag = "✅" if "完成" in step["status"] else ("⚠️" if "依赖" in step["status"] or "进行中" in step["status"] else "⬜")
                print(f"     {sflag} {step['step']} [{step['status']}] → {step['eta']}")

            print(f"     成功: {m['on_success']}")
            print(f"     失败: {m['on_failure']}")
            print(f"     ⚡ 关键风险: {', '.join(m['key_risks'][:2])}")

            # 即将完成的高概率里程碑 = 交易机会
            completed = sum(1 for s in m["milestones"] if "完成" in s["status"])
            total = len(m["milestones"])
            if completed / total > 0.5 and m["probability"] > 0.5:
                self.alerts.append({
                    "type": "技术里程碑",
                    "level": "🟢 即将完成",
                    "name": m["name"],
                    "progress": f"{completed}/{total}",
                    "probability": m["probability"],
                    "affects": m["affects"],
                    "on_success": m["on_success"],
                })

    def run(self):
        """Alias for run_all for CLI compatibility"""
        return self.run_all()

    def run_all(self):
        print("=" * 70)
        print("  🔬 深度监控引擎 — P1材料价格 + P2人员风险 + P1技术里程碑")
        print("=" * 70)

        self.run_material_monitor()
        self.run_personnel_monitor()
        self.run_tech_monitor()

        # ═══ 综合警报 ═══
        print(f"\n{'='*70}")
        print("  📋 综合警报汇总")
        print("=" * 70)

        if self.alerts:
            for i, alert in enumerate(self.alerts, 1):
                if alert["type"] == "材料价格":
                    print(f"\n  {alert['level']} #{i} [{alert['type']}] {alert['material']}")
                    print(f"     价格: {alert['price']} | {alert['trend']}")
                    print(f"     受影响: {', '.join(alert['affects'])}")
                    print(f"     → {alert['note']}")
                elif alert["type"] == "人员风险":
                    print(f"\n  {alert['level']} #{i} [{alert['type']}] {alert['company']} {alert['person']}")
                    print(f"     风险评分: {alert['risk_score']:.0%} | 预期冲击: {alert['impact']:+.0%}")
                    print(f"     受影响: {', '.join(alert['affects_etf'])}")
                elif alert["type"] == "技术里程碑":
                    print(f"\n  {alert['level']} #{i} [{alert['type']}] {alert['name']}")
                    print(f"     进度: {alert['progress']} | 概率: {alert['probability']:.0%}")
                    print(f"     影响: {', '.join(alert['affects'])}")
                    print(f"     → {alert['on_success']}")
        else:
            print("\n  ✅ 当前无紧急警报")

        print(f"\n{'='*70}")
        print("  ⚠️ 材料价格需市场数据确认（akshare/新浪可拉实时价格）")
        print("  ⚠️ 人员变动需新闻爬虫或手工监控")
        print("=" * 70)

        return self.alerts


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--material", action="store_true")
    parser.add_argument("--personnel", action="store_true")
    parser.add_argument("--tech", action="store_true")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()

    monitor = DeepMonitor()

    if args.material:
        monitor.run_material_monitor()
    elif args.personnel:
        monitor.run_personnel_monitor()
    elif args.tech:
        monitor.run_tech_monitor()
    else:
        monitor.run_all()


if __name__ == "__main__":
    main()
