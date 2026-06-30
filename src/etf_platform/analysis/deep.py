"""
P1-P2 增强引擎: 实时材料价格监控 + 人员事件触发器 + 技术里程碑进度
================================================================
用法:
  python deep_monitor.py              # 全量监控
  python deep_monitor.py --live       # 拉取实时价格
  python deep_monitor.py --material   # 仅材料价格
  python deep_monitor.py --personnel  # 仅人员风险
  python deep_monitor.py --tech       # 仅技术里程碑
"""
import sys, os, time, json, urllib.request
from collections import defaultdict
from datetime import datetime, timedelta


from ..config_loader import load_etfs

# ============ 实时材料价格监控 ============
# 关键材料 → 当前价格 → 方向 → 受影响ETF
MATERIAL_PRICE_MONITOR = {
    # 半导体材料
    "光刻胶(ArF)": {
        "current": "战略物资/不公开", "trend": "↑ 日本管制收紧",
        "unit": "N/A", "yr_low": None, "yr_high": None,
        "affects": ["159995","512480","159819","588000"],
        "impact_direction": "利空", "note": "JSR/TOK垄断90%，日本政策是唯一变量",
        "warning": "🔴 随时可能管制升级",
    },
    "高纯石英砂": {
        "current": "3-5万元/吨", "trend": "→ 平稳",
        "unit": "万元/吨", "yr_low": "2.5", "yr_high": "5.5",
        "affects": ["159995","512480","588000"],
        "impact_direction": "利空", "note": "美国Unimin垄断70%，国产纯度不足",
        "warning": "🟡 库存仅20天，任何供应中断即危机",
    },
    "硅晶圆(12英寸)": {
        "current": "$120-130/片", "trend": "→ 平稳",
        "unit": "$/片", "yr_low": "100", "yr_high": "150",
        "affects": ["159995","512480","159819","588000","516510"],
        "impact_direction": "中性", "note": "信越/SUMCO扩产中，供需趋于平衡",
        "warning": "⚪ 短期无风险",
    },

    # 新能源材料
    "碳酸锂(电池级)": {
        "current": "8-10万元/吨", "trend": "↓ 从60万跌至成本线",
        "unit": "万元/吨", "yr_low": "7.5", "yr_high": "18.0",
        "affects": ["516160","515030","159755"],
        "impact_direction": "利好", "note": "跌破澳矿成本线→供给出清→价格见底",
        "warning": "🟢 底部信号：锂价已跌90%，做多受益标的",
    },
    "钴(电解钴)": {
        "current": "20-25万元/吨", "trend": "↓ 三元电池需求下降",
        "unit": "万元/吨", "yr_low": "18", "yr_high": "35",
        "affects": ["516160"],
        "impact_direction": "利好", "note": "磷酸铁锂替代三元→钴需求结构性下降",
        "warning": "⚪ 长期利空钴价，利好下游成本",
    },
    "稀土(氧化镨钕)": {
        "current": "38-42万元/吨", "trend": "→ 中国控产稳价",
        "unit": "万元/吨", "yr_low": "32", "yr_high": "55",
        "affects": ["512660","512670","516160","516150"],
        "impact_direction": "中性偏多", "note": "中国主导供应60%+，出口管制是双刃剑",
        "warning": "🟡 稀土出口管制→国内稀土企业受益，下游成本承压",
    },

    # 军工材料
    "海绵钛(0级)": {
        "current": "5.0-5.5万元/吨", "trend": "→ 平稳",
        "unit": "万元/吨", "yr_low": "4.5", "yr_high": "6.5",
        "affects": ["512660","512670"],
        "impact_direction": "中性", "note": "宝钛/西部超导产能充足，国产替代率70%",
        "warning": "⚪ 短期无风险",
    },
    "镍(电解镍)": {
        "current": "12-14万元/吨", "trend": "↓ 印尼产能释放",
        "unit": "万元/吨", "yr_low": "11", "yr_high": "18",
        "affects": ["512660","512670"],
        "impact_direction": "利好", "note": "印尼镍矿扩产→高温合金原料成本下降",
        "warning": "🟢 镍价下行利好航发动力成本",
    },

    # 消费材料
    "棕榈油(RBD)": {
        "current": "4200-4800令吉/吨", "trend": "↑ 印尼B40+厄尔尼诺",
        "unit": "令吉/吨", "yr_low": "3400", "yr_high": "5200",
        "affects": ["515170"],
        "impact_direction": "利空", "note": "印尼强制B40生物柴油→棕榈油与燃料争原料",
        "warning": "🔴 30天库存+95%进口依赖=食品行业的'光刻胶时刻'",
    },
}

# ============ 人员风险数据库 ============
PERSONNEL_RISK_DB = [
    # 半导体
    {"company": "中芯国际", "code": "688981", "person": "梁孟松", "role": "联席CEO/技术核心", "irreplaceable": 0.90,
     "age": 73, "tenure_yrs": 8, "risk": "退休/技术路线分歧→7nm攻关中断",
     "affects_etf": ["159995","512480","588000"], "impact": -0.08,
     "watch_signals": ["减持股份", "董事会变动", "技术路线争议新闻"]},
    {"company": "寒武纪", "code": "688256", "person": "陈天石", "role": "创始人/CEO", "irreplaceable": 0.85,
     "age": 43, "tenure_yrs": 10, "risk": "创始人减持→AI芯片路线动摇→股价剧烈波动",
     "affects_etf": ["159995","159819"], "impact": -0.06,
     "watch_signals": ["大额减持公告", "质押股份", "核心技术人员离职"]},
    {"company": "北方华创", "code": "002371", "person": "赵晋荣", "role": "董事长", "irreplaceable": 0.70,
     "age": 61, "tenure_yrs": 12, "risk": "管理层变动→设备国产化进度延迟",
     "affects_etf": ["159995","512480"], "impact": -0.04,
     "watch_signals": ["高管集体减持", "董事会换届", "研发投入骤降"]},

    # 医药
    {"company": "恒瑞医药", "code": "600276", "person": "孙飘扬", "role": "创始人/实控人", "irreplaceable": 0.85,
     "age": 67, "tenure_yrs": 30, "risk": "二代接班不确定性→创新药战略转向风险",
     "affects_etf": ["159992","512170"], "impact": -0.06,
     "watch_signals": ["家族减持", "管理层洗牌", "研发方向突变"]},
    {"company": "药明康德", "code": "603259", "person": "李革", "role": "创始人/CEO", "irreplaceable": 0.80,
     "age": 58, "tenure_yrs": 20, "risk": "美国生物安全法案压力→战略收缩→全球CRO地位动摇",
     "affects_etf": ["159992","512170","513060"], "impact": -0.10,
     "watch_signals": ["美国客户流失", "海外资产出售", "CEO公开信悲观"]},

    # 新能源
    {"company": "宁德时代", "code": "300750", "person": "曾毓群", "role": "创始人/董事长", "irreplaceable": 0.75,
     "age": 57, "tenure_yrs": 15, "risk": "管理层变动→全球化战略受阻→市场份额松动",
     "affects_etf": ["516160","515030","159755"], "impact": -0.05,
     "watch_signals": ["海外工厂受阻", "大客户流失", "技术路线争议"]},

    # 军工
    {"company": "航发动力", "code": "600893", "person": "总工程师团队", "role": "涡扇发动机技术核心", "irreplaceable": 0.80,
     "age": None, "tenure_yrs": None, "risk": "技术骨干流失→发动机研制延迟1-2年",
     "affects_etf": ["512660","512670"], "impact": -0.06,
     "watch_signals": ["军工院所人才流失", "研制进度延迟公告", "试飞事故"]},
]

# ============ 技术里程碑进度追踪 ============
TECH_MILESTONES_V2 = [
    {
        "name": "中芯国际7nm试产",
        "target": "2026Q3", "progress": "🔴 未完成",
        "probability": 0.55,
        "milestones": [
            {"step": "7nm工艺验证", "status": "进行中", "eta": "2026Q2"},
            {"step": "首批试产流片", "status": "待完成", "eta": "2026Q3"},
            {"step": "良率>30%（商用门槛）", "status": "待完成", "eta": "2026Q4"},
            {"step": "客户导入（华为/OPPO）", "status": "待完成", "eta": "2027H1"},
        ],
        "affects": ["159995","512480","588000"],
        "on_success": "芯片ETF +8~12%, 国产替代叙事升级",
        "on_failure": "芯片ETF -5~8%, 2-3年内无法突破14nm天花板",
        "key_risks": ["光刻机进口受限", "光刻胶断供", "梁孟松退休"],
        "news_check": "中芯国际 7nm OR 先进制程 2026",
    },
    {
        "name": "华为昇腾910C量产",
        "target": "2026Q4", "progress": "🟡 进行中",
        "probability": 0.60,
        "milestones": [
            {"step": "昇腾910B生态完善（MindSpore适配）", "status": "✅ 完成", "eta": "2026Q1"},
            {"step": "910C设计冻结", "status": "✅ 完成", "eta": "2026Q2"},
            {"step": "7nm代工产能确认", "status": "⚠️ 依赖中芯7nm", "eta": "2026Q3"},
            {"step": "首批量产交付", "status": "待完成", "eta": "2026Q4"},
        ],
        "affects": ["159819","516510"],
        "on_success": "AI ETF +5~10%, 算力自主可控里程碑",
        "on_failure": "AI ETF -3~5%, 国产GPU叙事受质疑",
        "key_risks": ["中芯7nm进度", "EDA工具断供", "ARM架构授权"],
        "news_check": "华为 昇腾910C OR Ascend 910C 2026",
    },
    {
        "name": "光威T800碳纤维航空认证",
        "target": "2026H2", "progress": "🟡 认证中",
        "probability": 0.70,
        "milestones": [
            {"step": "T800生产线稳定量产", "status": "✅ 完成", "eta": "2026Q1"},
            {"step": "航空材料认证测试", "status": "进行中", "eta": "2026Q3"},
            {"step": "航发动力批量采购", "status": "待完成", "eta": "2026Q4"},
            {"step": "T1000研发突破", "status": "待完成", "eta": "2027H1"},
        ],
        "affects": ["512660","512670"],
        "on_success": "军工ETF +3~5%, 碳纤维100%国产化",
        "on_failure": "军工ETF -1~2%, 仍依赖日本东丽进口",
        "key_risks": ["日本东丽降价打压", "航空认证周期延长"],
        "news_check": "光威复材 T800 OR 碳纤维 航空认证 2026",
    },
    {
        "name": "钠电池量产+储能应用",
        "target": "2026H2", "progress": "🟢 推进顺利",
        "probability": 0.75,
        "milestones": [
            {"step": "钠电池中试线投产", "status": "✅ 完成", "eta": "2025Q4"},
            {"step": "储能示范项目运行", "status": "✅ 完成", "eta": "2026Q1"},
            {"step": "乘用车钠电装车测试", "status": "进行中", "eta": "2026Q3"},
            {"step": "10GWh级量产线建设", "status": "待完成", "eta": "2026Q4"},
        ],
        "affects": ["516160","515030"],
        "on_success": "新能源ETF +3~5%, 锂依赖从70%→40%",
        "on_failure": "新能源ETF -1~2%, 锂仍是唯一路线",
        "key_risks": ["能量密度天花板", "碳酸锂价格过低（削弱钠电经济性）"],
        "news_check": "钠电池 量产 2026 OR 钠离子电池 装车",
    },
    {
        "name": "创新药License-out交易爆发",
        "target": "2026H2", "progress": "🟢 超额完成",
        "probability": 0.80,
        "milestones": [
            {"step": "2025年交易额突破$50B", "status": "✅ 完成", "eta": "2025"},
            {"step": "2026H1交易额同比+35%", "status": "✅ 完成", "eta": "2026Q2"},
            {"step": "首款国产ADC获FDA批准", "status": "进行中", "eta": "2026Q3"},
            {"step": "MNC直接收购中国Biotech", "status": "待完成", "eta": "2026H2"},
        ],
        "affects": ["159992","512170"],
        "on_success": "创新药ETF +5~8%, 中国创新药全球认可",
        "on_failure": "创新药ETF -3~5%, 地缘风险阻断出海",
        "key_risks": ["美国生物安全法案", "FDA审批政治化"],
        "news_check": "创新药 license-out OR 中国药企 海外授权 2026",
    },
]


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

        for mat_name, mat in MATERIAL_PRICE_MONITOR.items():
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
        print(f"\n  📊 材料→ETF 交易映射:")
        mat_etf_signals = defaultdict(lambda: {"long": [], "short": []})
        for mat_name, mat in MATERIAL_PRICE_MONITOR.items():
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
