#!/usr/bin/env python3
"""
调研国内主流量化交易API可用性

目标：找一条直接把信号变成交易的路
"""
import sys, textwrap

apis = [
    {
        "name": "华泰 xtquant",
        "type": "券商官方API",
        "cost": "免费（华泰客户）",
        "门槛": "华泰证券开户",
        "features": "实时行情+交易+回测，Python API",
        "pros": ["官方支持", "功能完整", "Python直接调用", "实盘+仿真"],
        "cons": ["仅限华泰客户", "需开通量化权限", "Windows限定"],
        "verdict": "✅ 首选：华泰客户可以直接用",
    },
    {
        "name": "国泰君安 GPTrade",
        "type": "券商官方API",
        "cost": "免费",
        "门槛": "国泰君安开户 + 量化权限",
        "features": "Python量化API，支持程序化交易",
        "pros": ["大券商", "稳定性好"],
        "cons": ["权限门槛高", "文档不透明"],
        "verdict": "⚠️ 备选：权限审批较慢",
    },
    {
        "name": "掘金量化 (MyQuant)",
        "type": "第三方平台",
        "cost": "免费（基础版）",
        "门槛": "关联券商账户",
        "features": "回测+仿真+实盘，支持多券商",
        "pros": ["多券商支持", "回测功能强", "社区活跃"],
        "cons": ["实盘需要券商关联", "高级功能收费"],
        "verdict": "✅ 好选择：支持华泰/中信等",
    },
    {
        "name": "QMT (迅投)",
        "type": "量化终端",
        "cost": "部分券商免费",
        "门槛": "部分券商开户即可",
        "features": "极速交易+量化策略+回测",
        "pros": ["速度极快", "Level2行情", "券商合作多"],
        "cons": ["C++/Python混合", "上手复杂", "需特定券商"],
        "verdict": "⚠️ 专业级但重",
    },
    {
        "name": "东方财富 Choice",
        "type": "数据终端",
        "cost": "收费 ~5000/年",
        "features": "数据+回测，不开户可用",
        "pros": ["数据全", "回测方便"],
        "cons": ["收费", "实盘需另外接"],
        "verdict": "❌ 性价比不高",
    },
    {
        "name": "vnpy",
        "type": "开源框架",
        "cost": "免费开源",
        "features": "全栈量化交易框架，对接30+接口",
        "pros": ["开源", "功能极全", "社区大"],
        "cons": ["部署复杂", "学习曲线陡"],
        "verdict": "⚠️ 适合深度用户",
    },
    {
        "name": "easytrader",
        "type": "开源模拟操作",
        "cost": "免费",
        "features": "模拟人工操作同花顺/东方财富客户端",
        "pros": ["免券商API", "简单直接"],
        "cons": ["不稳定", "券商风控可能封", "非官方"],
        "verdict": "❌ 风险高不推荐",
    },
]

print("=" * 60)
print("📊 国内量化交易API调研")
print("=" * 60)

for api in apis:
    print(f"\n{'─' * 50}")
    print(f"  {api['name']}")
    print(f"  类型: {api['type']}")
    print(f"  费用: {api['cost']}")
    if '门槛' in api:
        print(f"  门槛: {api['门槛']}")
    print(f"  特点: {api['features']}")
    print(f"  优势: {' | '.join(api['pros'])}")
    print(f"  劣势: {' | '.join(api['cons'])}")
    print(f"  结论: {api['verdict']}")

print(f"\n{'=' * 60}")
print("💡 推荐方案")
print(f"{'=' * 60}")
print(textwrap.dedent("""
  🥇 首选：华泰 xtquant（如果你已经是华泰客户）
     - 官方Python API，直接调
     - 仿真环境可以先测试
     - 最快路径：信号→xtquant→交易

  🥈 备选：掘金量化（如果不是华泰客户）
     - 关联常见券商
     - 自带回测
     - 熟社区

  🥉 终极：自己跑信号 + 手动执行
     - 回测验证策略有效 → 每周按信号手动下单
     - 零API风险
     - 适合初期
"""))
