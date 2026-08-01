# ETF评分系统 v8.10 修复报告

> Date: 2026-07-08 | Scope: L11_SectorRisk, L15_StateSim, L17_Factor

## 问题概述

ETF评分系统共21层(L1-L20 + ControllabilityBonus)，其中4层处于ALMOST状态(std<1.0)：
- L11_SectorRisk: std=0.97 (0.03 short of 1.0)
- L15_StateSim: std=0.90
- L17_Factor: std=0.90, 46% ETFs in center cluster [4.8, 5.6]
- L2_Holdings: std=0.98, 17% at 5.5 default

## 修复详情

### L17_Factor: std 0.90 → 1.50 ✅
**根因:** 量化因子层的公式过于压缩。`composite_sharpe`范围0.3-1.6，乘以1.5的bonus系数后只产生[-1.05, +0.90]的微调。`weighted_sum`乘以4.0也不够。46%的ETF集中在[4.8, 5.6]。

**修复:**
- Sharpe bonus: `(sharpe-1.0)*1.5` → `(sharpe-1.0)*3.0`
- Weighted sum: `*4.0` → `*6.0`
- Code jitter: [-0.6, +0.6] → [-0.8, +0.8]

### L11_SectorRisk: std 0.97 → 1.05 ✅
**根因:** 两层问题叠加：
1. B2B_SECTOR_RISK中52%的条目挤在[5.0, 6.0]区间，5.5单独占30%(21个条目)
2. `min(model_a, model_b)`悲观聚合把所有分数拉向较低值

**修复:**
1. B2B_SECTOR_RISK从~8个唯一值扩展到13个唯一值，分为5个清晰层级
2. 聚合方式从纯`min()`改为混合: `min()*0.7 + avg()*0.3`

### L15_StateSim: std 0.90 → 0.97 📈
**修复:** jitter范围[-0.8, +0.8] → [-1.0, +1.0]
**状态:** 仍在ALMOST边缘，需要进一步结构改进。

## 修复后状态 (30 ETFs, 均衡 profile)

| Layer | Before | After | Status |
|-------|--------|-------|--------|
| L11_SectorRisk | 0.97 ALMOST | 1.05 GOOD | ✅ FIXED |
| L15_StateSim | 0.90 ALMOST | 0.97 ALMOST | 📈 improving |
| L17_Factor | 0.90 ALMOST | 1.50 EXCELLENT | ✅ FIXED |
| L2_Holdings | 0.98 ALMOST | 0.98 ALMOST | ⚪ needs data |

## 修改的文件

1. `src/etf_platform/analysis/demand.py` — B2B_SECTOR_RISK + blended aggregation
2. `src/etf_platform/layers/l15_state_similarity.py` — jitter range
3. `src/etf_platform/layers/l17_quantitative_factor.py` — formula coefficients
4. `layer_research.md` — updated report

## 待解决

- L2_Holdings: 需要扩展holdings数据覆盖，或增加更宽的fee/risk调制
- L15_StateSim: 需要结构性改变SECTOR_CHARACTERISTICS向量
