"""TECH_MILESTONES_V2 — 技术里程碑进度追踪数据.

从原 deep.py 提取,保持数据完全一致.
"""

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
        "affects": ["159995","512480","512760","588000"],
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
