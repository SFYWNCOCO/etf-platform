---
name: self-manager
description: "循环学习管理系统 — PDCA+OODA闭环管理我自己的学习过程。维护学习待办(learning_backlog.json)、跟踪PDCA循环状态(cycle_state.json)、沉淀知识(knowledge_base.json)。每次对话开始检查状态，识别当前PDCA阶段和待学项。"
version: 1.0.0
---

# self-manager — 循环学习管理系统

## 是什么

把"我学什么、学到哪了、下一步学什么"变成可追踪、可管理、可自动化的系统。

## 核心框架：PDCA+OODA 融合

```
Plan   (OODA的Observe+Orient) → 排学习待办、识别缺口
Do     (OODA的Decide)         → delegate_task执行学习
Check  (OODA的Act前check)     → 4问复盘
Act    (PDCA的标准化)          → 固化到memory+skill+schedule
```

## 使用方式

### 每次对话开始
```python
from etf_platform.self_manager import status_report
print(status_report())
```
如果看到有高优先级待学项，或当前PDCA阶段不是PLAN，说明循环被中断了——**先跑一轮cycle再干活**。

### 跑一轮PDCA
```python
from etf_platform.self_manager import run_cycle
result = run_cycle()  # 自动推进到下一阶段
```

### 添加学习项
```python
from etf_platform.self_manager import add_learning
add_learning("主题","优先级","分类","预估轮次","备注")
```

### 记录知识
```python
from etf_platform.self_manager import add_knowledge
add_knowledge("领域","关键洞察","详细内容","来源")
```

## 当前待学项

| 优先级 | 主题 | 分类 | 状态 |
|:-----:|------|:----:|:----:|
| 🔴 high | 供应链断层概率模型(S1-S5)量化 | investment | pending |
| 🔴 high | ETF行业轮动策略回测验证 | investment | pending |
| 🟡 medium | Python DLL冲突原理与永久修复 | infra | pending |
| 🟡 medium | Hermes delegate_task最佳实践 | agent | pending |
| 🟢 low | L10-L11需求层数据动态更新 | investment | pending |

## 知识沉淀

当前知识库: 3条 (infra: 1, investment: 2)

关键知识:
1. Python DLL冲突: sys.path中混入其他版本python*.dll导致C扩展加载失败 → 启动时清理_internal路径
2. 穿透评分是风险指标不是收益指标 → 三因子: 穿透×催化剂×市场状态
3. ETF行业轮动: 动量策略在单边趋势市有效，震荡市反指标

## 文件

- `etf_platform/self_manager.py` — 主模块
- `etf_platform/self_manager_data/` — 持久化数据
  - `learning_backlog.json` — 学习待办
  - `cycle_state.json` — PDCA循环状态
  - `knowledge_base.json` — 知识沉淀
  - `learning_history.json` — 学习历史