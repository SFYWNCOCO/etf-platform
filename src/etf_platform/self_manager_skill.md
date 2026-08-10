---
name: self-manager
description: "循环学习管理系统 — PDCA+OODA闭环管理我自己的学习过程。维护学习待办(learning_backlog.json)、跟踪PDCA循环状态(cycle_state.json)、沉淀知识(knowledge_base.json)。每次对话开始检查状态，识别当前PDCA阶段和待学项。"
version: 1.1.0
---

# self-manager — 循环学习管理系统

> **[待建] 2026-08-10 诚实标注**：`etf_platform/self_manager.py` 与 `self_manager_data/` 数据文件当前**未实现**。本文件是声明档（设计意图），不是已落地系统的使用手册。下方所有 `from etf_platform.self_manager import ...` 示例是目标接口，实现前不可直接调用。

## 是什么

把"我学什么、学到哪了、下一步学什么"变成可追踪、可管理、可自动化的系统。

## 核心框架：对齐主平台 Dojo 流程

> 2026-08-10 对齐：本 skill 的循环学习流程**复用主平台 Dojo 七步**（SOUL §Dojo：measure→identify→fix→distill→evolve→verify→report），不再另造一套循环。

```
Plan   (Dojo measure+identify) → 排学习待办、识别缺口
Do     (Dojo fix)              → 执行学习/修复
Check  (Dojo verify)           → 4问复盘 + 证据核验
Act    (Dojo evolve+report)    → 固化到memory+skill+schedule + AAR
```

## 使用方式

> 以下为目标接口（[待建]，模块未实现）。

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

## 分工对齐（2026-08-10，映射统一分工规则）

本 skill 是主平台（OpenClaw/Hermes）分工体系在 ETF 领域的延伸。`.agent_context/` 调度器依赖链 `researcher→analyst→writer→reviewer` 映射到统一分工：

| 调度器角色 | 统一分工归属 | 说明 |
|---|---|---|
| researcher | 集群补充调研/数据收集（S0-S5 B类） | 无依赖起点，先取数 |
| analyst | 数据分析 → Hermes 主线编排 | `analyst_team.py` 4 角色（宏观/技术/基本面/风控）属确定性评分，不另派 LLM 子 agent |
| writer | 集群 write-skill 分章（S5） | 长文按章拆分，绝不用 1 个 subagent 整合全文 |
| reviewer | 独立审查（验证者≠执行者） | 复核结论，不与被审者同人 |

**协作红线**：涉及写代码/改代码的改动，遵循主平台决策矩阵（SOUL P4 / AGENTS §2）——默认交 Claude Code 执行，Hermes 编排/验证/收尾；本 skill 的 PDCA 循环只管理"学什么"，不改变分工归属。

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

- `etf_platform/self_manager.py` — 主模块 **[待建]**
- `etf_platform/self_manager_data/` — 持久化数据 **[待建]**
  - `learning_backlog.json` — 学习待办
  - `cycle_state.json` — PDCA循环状态
  - `knowledge_base.json` — 知识沉淀
  - `learning_history.json` — 学习历史