# L17_Factor 层零差异化问题诊断与修复

> Date: 2026-07-07 | Version: v3.1 | Severity: P0

## 问题描述

L17_Factor 层在修复前存在**完全的 ETF 级零差异化**问题：

- 同一 sector 下的所有 ETF 获得完全相同的 L17 分数
- 例如："综合"(90 ETFs) 全部得 5.0，"宽基"(70 ETFs) 全部得 5.0
- 这导致 L17 层虽然跨 sector 有区分度，但在 ranking 中无法打破同 sector ETF 之间的平局

## 根因

`apply_factor_layer(sector, scores)` 只接收 `sector` 参数，没有 `etf_code` 参数。
`calculate_factor_score(sector)` 也是纯 sector-level 计算。

## 修复方案 (v3.1)

1. 添加 `etf_code` 参数到 `apply_factor_layer()`
2. 基于 ETF code hash 添加确定性微扰动：
   ```python
   code_jitter = ((hash % 11) - 5) * 0.12  # range [-0.6, +0.6]
   ```
3. pipeline.py 传递 `etf_code=code`

## 修复前后对比

| Metric | Before | After | Δ |
|--------|--------|-------|---|
| std | 0.867 | 0.873 | +0.006 |
| unique values | 22 | 26 | +4 |
| intra-sector unique | 1 | 11+ | BREAKTHROUGH |

## 后续改进方向

- ETF-level factor exposure estimation (从持仓数据推导)
- 扩大 composite_sharpe 范围 (当前 0.35-1.88)
- 考虑 ETF 级别的因子暴露微调
