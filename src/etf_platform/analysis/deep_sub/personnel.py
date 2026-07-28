"""PERSONNEL_RISK_DB — 关键人员风险数据库.

从原 deep.py 提取,保持数据完全一致.
"""

# ============ 人员风险数据库 ============
PERSONNEL_RISK_DB = [
    # 半导体
    {"company": "中芯国际", "code": "688981", "person": "梁孟松", "role": "联席CEO/技术核心", "irreplaceable": 0.90,
     "age": 73, "tenure_yrs": 8, "risk": "退休/技术路线分歧→7nm攻关中断",
     "affects_etf": ["159995","512480","512760","588000"], "impact": -0.08,
     "watch_signals": ["减持股份", "董事会变动", "技术路线争议新闻"]},
    {"company": "寒武纪", "code": "688256", "person": "陈天石", "role": "创始人/CEO", "irreplaceable": 0.85,
     "age": 43, "tenure_yrs": 10, "risk": "创始人减持→AI芯片路线动摇→股价剧烈波动",
     "affects_etf": ["159995","159819"], "impact": -0.06,
     "watch_signals": ["大额减持公告", "质押股份", "核心技术人员离职"]},
    {"company": "北方华创", "code": "002371", "person": "赵晋荣", "role": "董事长", "irreplaceable": 0.70,
     "age": 61, "tenure_yrs": 12, "risk": "管理层变动→设备国产化进度延迟",
     "affects_etf": ["159995","512480","512760"], "impact": -0.04,
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
