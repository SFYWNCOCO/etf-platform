"""chain.py — 供应链依赖分析（终极材料层）

数据来源: etf_system/chain_analysis.py v4
核心内容: 依赖图谱 × 连锁故障场景 × 交叉依赖热力图 × ETF风险评估
"""
import json

# ═══ 1. 完整依赖图谱 — 材料(L0)→组件(L1)→芯片(L2)→系统(L3)→ETF(L4) ═══
DEPENDENCY_GRAPH = {
    "L0:高纯石英砂": {"depends_on": [], "feeds": ["L1:单晶硅棒"],
        "supplier": "尤尼明(美)/TQC(挪威)", "替代性": "0%", "库存": "20天",
        "切断影响": "20天后全球硅片生产停摆"},
    "L0:EUV光刻胶": {"depends_on": [], "feeds": ["L1:EUV光刻"],
        "supplier": "JSR/东京应化(日本100%)", "替代性": "0%", "库存": "30天",
        "切断影响": "30天后7nm以下芯片停产"},
    "L0:高纯硅砂": {"depends_on": [], "feeds": ["L1:硅晶圆"],
        "supplier": "信越/SUMCO(日本+台湾)", "替代性": "10%", "库存": "60天",
        "切断影响": "60天后功率+逻辑芯片同时短缺"},
    "L1:单晶硅棒": {"depends_on": ["L0:高纯石英砂"], "feeds": ["L2:硅晶圆"]},
    "L1:EUV光刻": {"depends_on": ["L0:EUV光刻胶", "L2:硅晶圆"], "feeds": ["L2:7nm以下芯片"]},
    "L1:硅晶圆": {"depends_on": ["L0:高纯硅砂", "L0:高纯石英砂"],
        "feeds": ["L2:功率芯片(IGBT/SiC)", "L2:逻辑芯片", "L1:EUV光刻"]},
    "L2:GPU/AI芯片": {"depends_on": ["L1:EUV光刻", "L2:硅晶圆"],
        "feeds": ["L3:AI服务器", "L3:自动驾驶域控"],
        "supplier": "NVIDIA/AMD(美国100%)", "替代性": "昇腾910B(60-70%性能)", "库存": "45天"},
    "L2:7nm以下芯片": {"depends_on": ["L1:EUV光刻"], "feeds": ["L2:手机SoC", "L2:GPU/AI芯片", "L2:5G基带"]},
    "L2:功率芯片(IGBT/SiC)": {"depends_on": ["L1:硅晶圆"],
        "feeds": ["L3:新能源车电驱", "L3:工业变频器", "L3:电网设备"],
        "supplier": "英飞凌/ST(欧洲)", "替代性": "比亚迪/中车(IGBT可部分, SiC仍弱)", "库存": "90天"},
    "L2:MCU/传感器": {"depends_on": ["L1:硅晶圆"],
        "feeds": ["L3:机器人控制器", "L3:汽车ECU", "L3:工业PLC"],
        "supplier": "ST/TI/瑞萨(欧+日)", "替代性": "兆易创新(低端可替)", "库存": "60天"},
    "L2:光模块芯片": {"depends_on": ["L1:硅晶圆"],
        "feeds": ["L3:数据中心互联", "L3:5G基站回传"],
        "supplier": "国产为主+Lumentum(美)", "替代性": "75%", "库存": "90天"},
    "L3:AI服务器": {"depends_on": ["L2:GPU/AI芯片", "L2:光模块芯片"], "feeds": ["L4:云计算服务"]},
    "L3:新能源车电驱": {"depends_on": ["L2:功率芯片(IGBT/SiC)", "L2:MCU/传感器"], "feeds": ["L4:新能源车"]},
    "L3:机器人控制器": {"depends_on": ["L2:MCU/传感器", "L2:GPU/AI芯片"], "feeds": ["L4:工业机器人"]},
    "L3:数据中心互联": {"depends_on": ["L2:光模块芯片"], "feeds": ["L4:云计算服务"]},
    "L4:芯片ETF(159995)": {"depends_on": ["L2:7nm以下芯片", "L2:功率芯片", "L2:MCU"], "暴露节点": 5},
    "L4:AI ETF(159819)": {"depends_on": ["L2:GPU/AI芯片", "L3:AI服务器"], "暴露节点": 3},
    "L4:云计算ETF(516510)": {"depends_on": ["L3:AI服务器", "L3:数据中心互联"], "暴露节点": 4},
    "L4:新能源ETF(516160)": {"depends_on": ["L2:功率芯片", "L2:MCU", "L3:新能源车电驱"], "暴露节点": 3},
    "L4:机器人ETF(562500)": {"depends_on": ["L2:MCU", "L3:机器人控制器"], "暴露节点": 2},
    "L4:通信ETF(515880)": {"depends_on": ["L2:光模块芯片", "L3:数据中心互联"], "暴露节点": 2},
    "L4:5G ETF(515050)": {"depends_on": ["L2:光模块芯片"], "暴露节点": 1},
}

# ═══ 2. 连锁故障场景 ═══
CASCADE_SCENARIOS = [
    {"场景": "S1: 石英砂+光刻胶双断供", "概率": "30% (日本禁运扩展+美国限制石英砂)",
     "触发链": "高纯石英砂(20天)→单晶硅棒→硅晶圆→EUV光刻→GPU→AI服务器→云计算停摆",
     "波及ETF": ["159995+0.15","512480+0.14","159819+0.12","516510+0.18","516160+0.06","562500+0.04"],
     "评估": "系统性危机: 4层链全部断裂, 6支ETF同时承压"},
    {"场景": "S2: GPU+光刻胶双断供", "概率": "45% (BIS扩大禁运范围)",
     "触发链": "GPU禁运(45天)+光刻胶断供(30天)→AI训练中断+国产GPU无法制造(无光刻胶)",
     "波及ETF": ["159819+0.18","516510+0.15","513100+0.08","159995+0.10"],
     "评估": "AI断崖: 既无进口GPU也无国产GPU→AI产业停滞"},
    {"场景": "S3: MCU+功率芯片双短缺", "概率": "25% (欧洲跟进出口管制)",
     "触发链": "MCU短缺(60天)+IGBT短缺(90天)→新能源车停产+机器人停产+工业自动化降速",
     "波及ETF": ["516160+0.12","562500+0.10"],
     "评估": "制造断裂: 影响集中在新能源+机器人"},
    {"场景": "S4: 光模块+5G芯片短缺", "概率": "15% (高端芯片管制扩展)",
     "触发链": "800G光芯片短缺→数据中心互联降速→云计算延迟→AI训练效率下降",
     "波及ETF": ["515880+0.06","516510+0.04","515050+0.04"],
     "评估": "可承受: 国产替代率高, 影响可控"},
    {"场景": "S5: 全面禁运", "概率": "5% (中美全面脱钩)",
     "触发链": "全部L0材料断供→全部L1组件停产→全部L2芯片停供→全部L3系统崩溃→全部ETF暴跌",
     "波及ETF": ["ALL: +0.20~+0.50"],
     "评估": "系统性崩溃: 概率低但一旦发生全市场无幸免"},
]

# ═══ 3. 交叉依赖热力图 ═══
CROSS_IMPACT = {
    "159995": {"name": "芯片ETF", "direct_bottlenecks": 3, "indirect_chains": 4, "cascade_scenarios": 3,
               "hidden_link": "石英砂→硅片→芯片: 这个链路市场完全未关注"},
    "512480": {"name": "半导体ETF", "direct_bottlenecks": 3, "indirect_chains": 3, "cascade_scenarios": 2,
               "hidden_link": "半导体设备是卖铲人→芯片厂停产→设备订单取消→双杀"},
    "159819": {"name": "AI ETF", "direct_bottlenecks": 2, "indirect_chains": 4, "cascade_scenarios": 2,
               "hidden_link": "国产替代假象: 即使有昇腾设计, 无光刻胶也造不出来"},
    "516510": {"name": "云计算ETF", "direct_bottlenecks": 1, "indirect_chains": 5, "cascade_scenarios": 4,
               "hidden_link": "隐性受害者: 没有一条链断裂不伤及云计算, 是系统性最脆弱节点"},
    "516160": {"name": "新能源ETF", "direct_bottlenecks": 1, "indirect_chains": 2, "cascade_scenarios": 2,
               "hidden_link": "光伏回暖是假信号: 新能源车产能才是决定因素"},
    "562500": {"name": "机器人ETF", "direct_bottlenecks": 1, "indirect_chains": 2, "cascade_scenarios": 2,
               "hidden_link": "工业4.0泡沫: 机器人量产依赖进口MCU, 国产替代至少3年"},
    "512170": {"name": "医疗ETF", "direct_bottlenecks": 1, "indirect_chains": 1, "cascade_scenarios": 2,
               "hidden_link": "集采降价被关注, API供应安全被忽略"},
    "159992": {"name": "创新药ETF", "direct_bottlenecks": 3, "indirect_chains": 1, "cascade_scenarios": 2,
               "hidden_link": "创新建立在进口耗材之上, 国产替代仅30%"},
    "512660": {"name": "军工ETF", "direct_bottlenecks": 2, "indirect_chains": 1, "cascade_scenarios": 2,
               "hidden_link": "镍/钴断供风险被市场忽略"},
    "512690": {"name": "酒ETF", "direct_bottlenecks": 0, "indirect_chains": 0, "cascade_scenarios": 1,
               "hidden_link": "最安全的供应链: 3年基酒+85%国产"},
    "518880": {"name": "黄金ETF", "direct_bottlenecks": 0, "indirect_chains": 0, "cascade_scenarios": 1,
               "hidden_link": "避险资产, 系统性对冲"},
    "511010": {"name": "国债ETF", "direct_bottlenecks": 0, "indirect_chains": 0, "cascade_scenarios": 1,
               "hidden_link": "利率债, 无供应链风险"},
    "563300": {"name": "中证红利低波", "direct_bottlenecks": 0, "indirect_chains": 0, "cascade_scenarios": 1,
               "hidden_link": "防御型, 系统性风险低"},
    "512890": {"name": "红利低波ETF", "direct_bottlenecks": 0, "indirect_chains": 0, "cascade_scenarios": 1,
               "hidden_link": "防御型, 系统性风险低 (红利低波同类 563300)"},
}


def evaluate_etf_risk(code):
    """评估单个ETF的供应链风险等级"""
    ci = CROSS_IMPACT.get(code)
    if not ci:
        return None
    score = ci["direct_bottlenecks"] * 0.4 + ci["indirect_chains"] * 0.3 + ci["cascade_scenarios"] * 0.3
    if score >= 3.5: level = "P0-致命"
    elif score >= 2.5: level = "P1-严重"
    elif score >= 1.5: level = "P2-关注"
    else: level = "P3-低风险"
    return {"level": level, "score": round(score, 1), "detail": ci}


def get_chain_report(code=None):
    """获取供应链分析报告.
    
    Args:
        code: ETF代码, 为None时返回全量排名
    Returns:
        dict with analysis results
    """
    if code:
        risk = evaluate_etf_risk(code)
        if not risk:
            return {"code": code, "error": "no chain data"}
        
        # Find relevant cascade scenarios
        scenarios = []
        for sc in CASCADE_SCENARIOS:
            affected = [e.split("+")[0] for e in sc["波及ETF"]]
            if code in affected or "ALL" in affected:
                scenarios.append({
                    "scene": sc["场景"],
                    "probability": sc["概率"],
                    "chain": sc["触发链"],
                    "impact": sc["评估"],
                })
        
        return {
            "code": code,
            "name": risk["detail"]["name"],
            "risk_level": risk["level"],
            "risk_score": risk["score"],
            "direct_bottlenecks": risk["detail"]["direct_bottlenecks"],
            "indirect_chains": risk["detail"]["indirect_chains"],
            "cascade_scenarios_count": risk["detail"]["cascade_scenarios"],
            "hidden_link": risk["detail"]["hidden_link"],
            "cascade_scenarios": scenarios,
        }
    
    # 全量排名
    ranked = []
    for c, ci in CROSS_IMPACT.items():
        risk = evaluate_etf_risk(c)
        if risk:
            ranked.append({"code": c, "name": ci["name"], "level": risk["level"],
                          "score": risk["score"], "hidden_link": ci["hidden_link"]})
    ranked.sort(key=lambda x: x["score"], reverse=True)
    return {"ranked": ranked, "scenarios": CASCADE_SCENARIOS, "total_covered": len(ranked)}


def find_safest_etfs(top_n=5):
    """找到供应链最安全的ETF (高分=安全)"""
    ranked = []
    for c, ci in CROSS_IMPACT.items():
        risk = evaluate_etf_risk(c)
        if risk:
            ranked.append({"code": c, "name": ci["name"], "risk_score": risk["score"],
                          "hidden_link": ci["hidden_link"]})
    ranked.sort(key=lambda x: x["risk_score"])
    return ranked[:top_n]


def find_riskiest_etfs(top_n=5):
    """找到供应链最脆弱的ETF (高分=脆弱)"""
    ranked = []
    for c, ci in CROSS_IMPACT.items():
        risk = evaluate_etf_risk(c)
        if risk:
            ranked.append({"code": c, "name": ci["name"], "risk_score": risk["score"],
                          "hidden_link": ci["hidden_link"]})
    ranked.sort(key=lambda x: x["risk_score"], reverse=True)
    return ranked[:top_n]


if __name__ == "__main__":
    import json
    # Test
    print("=== 单只评估 ===")
    r = get_chain_report("516510")
    print(json.dumps(r, ensure_ascii=False, indent=2))
    
    print("\n=== 最脆弱Top3 ===")
    for etf in find_riskiest_etfs(3):
        print("  %s %s: %.1f分 - %s" % (etf["code"], etf["name"], etf["risk_score"], etf["hidden_link"]))
    
    print("\n=== 最安全Top3 ===")
    for etf in find_safest_etfs(3):
        print("  %s %s: %.1f分 - %s" % (etf["code"], etf["name"], etf["risk_score"], etf["hidden_link"]))