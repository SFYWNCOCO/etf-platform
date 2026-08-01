# QVIX Regime & Transition Model Audit Report

## 审计范围
- `src/etf_platform/analysis/qvix_regime.py` — QVIX恐慌检测（单数据源，4h TTL缓存）
- `src/etf_platform/decision/regime_transition.py` — 状态转换预测（4指标→softmax概率）
- `src/etf_platform/decision/strategy_tournament.py` — 锦标赛策略加权

---

## 一、QVIX数据可靠性审计

### 1.1 数据源脆弱性

| 问题 | 严重程度 | 说明 |
|------|----------|------|
| 单数据源无冗余 | **CRITICAL** | 仅依赖 `ak.index_option_50etf_qvix()` + `ak.index_option_500etf_qvix()`，akshare接口变更或目标网站宕机时系统完全失明 |
| 超时后静默降级 | **HIGH** | `_fetch_qvix_with_timeout` 线程超时后返回 `None`，触发缓存→过期缓存→fallback，每次降级都没有告警 |
| Fallback值硬编码 | **MEDIUM** | fallback 使用 QVIX=20/25 (normal regime)，但实际市场可能在恐慌中，导致策略错误地执行 aggressive 配置 |
| 无数据质量校验 | **HIGH** | 未检查QVIX值的合理性（如负数、>100的异常值）、未检查数据新鲜度（日期是否合理） |

### 1.2 替代/交叉验证数据源

通过web搜索确认以下可用替代数据源：

1. **期权论坛 (optbbs.com)** — 提供50ETF/300ETF/500ETF实时QVIX及历史数据，有API可爬取
2. **CBOE VXFXI** — CBOE中国ETF波动率指数，基于FXI期权，可通过Yahoo Finance获取
3. **东方财富/新浪财经** — 期权链隐含波动率，可手动计算近似QVIX
4. **akshare已实现波动率** — `realized_volatility` 接口提供Oxford-Man已实现波动率

### 1.3 阈值设定缺陷

```python
# 当前硬编码阈值 — 无任何统计依据
if qvix_val < 16:   # complacent
if qvix_val < 22:   # normal
if qvix_val < 28:   # cautious
return "fearful"     # >28
```

**问题：**
- 区间宽度不等 (6/6/6/∞)，但不同标的的历史分布不同
- 未考虑50ETF和500ETF的QVIX分布差异
- 没有动态调整机制（市场结构变化后阈值可能过时）

### 1.4 50/500冲突处理逻辑缺陷

```python
# 当前逻辑：取两者中"更恐惧"的regime
if regime_order.get(regime_500, 1) > regime_order.get(regime_50, 1):
    regime = regime_500
else:
    regime = regime_50
```

**问题：**
- 只在regime层面做比较，忽略了QVIX数值的量级差异
- 当50ETF QVIX=30(fearful)但500ETF QVIX=18(normal)时，选fearful是合理的
- 但当50ETF QVIX=29(fearful) vs 500ETF QVIX=22(cautious)时，只差1个单位却跨了两个regime

---

## 二、Regime Transition 模型审计

### 2.1 四个先行指标的缺陷

#### 指标1: 市场广度 (breadth)
```python
# 问题1: change_20d > -2 作为"站上20日均线"的代理过于粗糙
if trend.change_20d > -2:  # Slight tolerance
    above_ma += 1
```
- `change_20d` 是20日收益率百分比，不是价格与均线的关系
- -2%容忍度意味着价格远低于20日均线的ETF也被计为"above MA"
- 截断在60只ETF，样本代表性不足

#### 指标2: 波动趋势 (vol_trend)
```python
# 问题: 仅基于当前位置在band中的比例，不是真正的趋势
position_in_band = (avg_qvix - lo) / max(hi - lo, 1)
vol_trend = (position_in_band - 0.5) * 2
```
- 这是**静态位置指标**而非趋势指标
- 没有利用时间序列信息（QVIX在过去N日的变化方向）
- 无法区分"刚从normal跌入cautious"和"已在cautious顶部"两种情况

#### 指标3: 量能信号 (volume_signal)
```python
signal = (avg_vr - 1.0) * 2  # Map to [-1, 1] roughly
```
- 未区分恐慌放量 vs 吸筹放量 — 两者都产生 `vr > 1`
- 截断在30只ETF，且未排除行业ETF（行业ETF的成交量特征与宽基完全不同）
- 乘以2的缩放因子没有理论依据

#### 指标4: 指数动量 (momentum_signal)
```python
mom = trend.change_20d / 20 * 5  # Scale to weekly-ish
momentums.append(max(-1.0, min(1.0, mom / 5.0)))
```
- 公式混乱：`change_20d / 20 * 5 / 5 = change_20d / 20`
- 本质上是把20日收益率线性缩放到[-1,1]，但20日收益率本身就可能超过±20%
- 用 `max(-1, min(1))` 强行截断导致信息丢失

### 2.2 概率模型缺陷

```python
# 当前模型：简单的分数累加 → 归一化
stay_score = 2.0  # Base inertia
total = improve_score + stay_score + worsen_score
prob_improve = improve_score / total
```

**问题清单：**
1. **未校准** — 没有任何历史数据来验证这些概率是否准确（Brier score, log loss）
2. **非线性缺失** — softmax被替换为简单的线性归一化，没有温度参数控制置信度
3. **边界条件** — 当所有分数都是0时（默认初始化），`total=1` 导致概率全部分配给 stay
4. **无置信度量化** — confidence 仅基于 `max_prob > 0.6` 判断，未考虑指标分歧程度
5. **单一时间尺度** — 所有指标都是截面快照，没有时间衰减

---

## 三、Strategy Tournament 权重审计

### 3.1 权重来源

```python
# fearful: 来自60天回测 (momentum 100%胜率, zscore 67%, capital_flow 33%, mean_reversion 0%)
# other regimes: 理论先验，无实证数据
REGIME_WEIGHT_PRIORS = {
    "fearful": {"momentum": 0.40, "zscore_multi": 0.30, ...},
    "cautious": {"mean_reversion": 0.20, "zscore_multi": 0.35, ...},  # 理论先验!
    "normal": {...},  # 理论先验!
    "complacent": {...},  # 理论先验!
}
```

**关键发现：**
- 只有 `fearful`  regime的权重有实证支撑
- 其他三个regime的权重完全是主观设定的先验
- 注释明确标注 "theoretical priors pending empirical data"

### 3.2 验证基础设施缺失

- `verify_prediction` 方法存在但从未被调用
- `TOURNAMENT_LOG` 文件路径定义但未实际使用
- 没有自动化的回测验证pipeline
- 没有存储预测-实际的配对数据用于后续分析

---

## 四、改进方案设计

### 改进方案1: QVIX多源校验 + 异常检测

**目标：** 让regime检测在单一数据源失效时仍能工作，并检测数据异常

**核心设计：**
1. 引入第二个数据源（东方财富/新浪期权隐含波动率）
2. 实现QVIX合理性校验（范围检查、跳变检测）
3. 多源一致性评分
4. 分级降级策略（live→cache→secondary_source→fallback）

### 改进方案2: Regime阈值统计校准 + 状态转换模型回测框架

**目标：** 让阈值和数据驱动，让转换概率可验证

**核心设计：**
1. 基于历史QVIX分布的动态阈值（百分位数法）
2. 状态转换概率的Brier score回测
3. 指标质量监控（每个指标的预测力评估）
4. 自动权重更新机制

---

## 五、具体代码改动建议

见 `qvix_regime_improvements.py` 和 `regime_transition_improvements.py`。
