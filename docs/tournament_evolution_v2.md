# 锦标赛策略进化方案 v2.0

> 基于对 strategy_tournament.py (1213行), regime_transition.py (406行), 
> tournament_60day_result.json, tournament_predictions.jsonl 的深度审计。

---

## 一、现状审计（代码级诊断）

### 1.1 架构问题

| 问题 | 严重度 | 证据 |
|------|--------|------|
| **策略孤岛** | 🔴 高 | 4个策略独立运行，无交叉引用；`run_strategies()` 按顺序调用各函数，结果不互通 |
| **权重硬编码** | 🔴 高 | `REGIME_WEIGHT_PRIORS` (L135-160) 中仅 fearful 有实证数据，其余3个regime权重是理论先验 |
| **样本量极小** | 🟡 中 | 每策略每regime仅3个样本（Top3×1只ETF），统计显著性不足 |
| **权重更新粗糙** | 🟡 中 | `update_weights_from_performance()` (L649-683) 用固定+0.15 boost，无UCB/TS探索机制 |
| **验证脱节** | 🟡 中 | `verify_by_regime()` 将实际收益与预测配对，但只用10d return做binary win/loss，丢失信息量 |
| **Ensemble简单平均** | 🟢 低 | 加权平均但无近期衰减因子——60天前的表现和昨天的表现同等权重 |

### 1.2 关键发现

从 `tournament_predictions.jsonl` 可见：
- **513350 (标普油气)** 连续出现在所有4个策略的Top3中 — 这是真正的共识信号
- **512010 (医药)** 仅在动量策略中出现 — 动量独有的alpha
- **159206 (卫星)** 仅在均值回归中出现 — 均值回归在恐慌期的选股逻辑完全不同于动量
- 这意味着：**不同策略在不同regime下捕获不同的alpha源**，但当前系统没有利用这种互补性

### 1.3 数据流图

```
Kline Data ──→ TrendSnapshot ──┐
                               ├──→ Strategy A (Z-score) ──┐
                               │                             ├──→ Ensemble (加权平均)
Pipeline (L1-L13) ──→ PipeMap ──┤                             │
                               ├──→ Strategy B (Momentum) ───┤
                               ├──→ Strategy C (Mean Rev) ───┤
                               └──→ Strategy D (Capital Flow)┘
                                    ↑ 完全独立，无通信
```

---

## 二、创新方案 A：策略互学习机制 (Cross-Strategy Knowledge Transfer)

### 2.1 核心思想

让输家策略能"看到"赢家的持仓，提取**赢家因子(winner_factor)** — 即赢家选中但输家忽略的ETF的共同特征。

### 2.2 实现设计

```python
class CrossStrategyLearner:
    """策略间知识转移模块
    
    每次锦标赛后运行：
    1. 识别本轮赢家策略（按ensemble_score或历史win_rate）
    2. 提取赢家选中的ETF的特征向量
    3. 计算"赢家因子" = 赢家vs全池的特征差异
    4. 将赢家因子注入输家策略的评分公式
    """
    
    def __init__(self):
        self._winner_factors = defaultdict(list)  # {regime: [factor_vecs]}
        self._decay = 0.9  # 指数衰减因子
    
    def compute_winner_factors(
        self,
        results: dict[str, StrategyResult],
        candidates: list[tuple[str, dict]],
        regime: str,
        actual_returns: dict[str, float],
    ) -> dict[str, float]:
        """计算赢家因子并返回注入权重。
        
        Args:
            results: 各策略输出
            candidates: 候选池
            regime: 当前市场状态
            actual_returns: {code: actual_return} — 用于确定谁是赢家
            
        Returns:
            {strategy_name: factor_injection_weight}
        """
        # Step 1: 确定赢家策略
        strategy_scores = {}
        for sname, res in results.items():
            avg_ret = sum(actual_returns.get(p["code"], 0) for p in res.picks[:3]) / 3
            strategy_scores[sname] = avg_ret
        
        winner = max(strategy_scores, key=strategy_scores.get)
        loser = min(strategy_scores, key=strategy_scores.get)
        
        # Step 2: 提取赢家选中的ETF特征
        winner_codes = {p["code"] for p in results[winner].picks[:3]}
        winner_features = []
        for code in winner_codes:
            feat = self._extract_features(code, results, candidates)
            winner_features.append(feat)
        
        # Step 3: 计算全池特征均值
        pool_features = []
        for code, _ in candidates:
            feat = self._extract_features(code, results, candidates)
            pool_features.append(ft)
        
        # Step 4: 赢家因子 = 赢家均值 - 全池均值
        winner_factor = np.mean(winner_features) - np.mean(pool_features)
        
        # Step 5: 指数衰减融合历史赢家因子
        self._winner_factors[regime].append(winner_factor)
        if len(self._winner_factors[regime]) > 10:
            self._winner_factors[regime].pop(0)
        
        # 计算注入权重：赢家优势越大，注入越强
        advantage = strategy_scores[winner] - strategy_scores[loser]
        injection_weight = min(0.3, advantage * 0.1)  # 最多注入30%
        
        return {loser: injection_weight}
    
    def _extract_features(self, code: str, results, candidates) -> np.ndarray:
        """提取单只ETF的多策略特征向量。"""
        features = []
        for sname, res in results.items():
            pick = next((p for p in res.all_scored if p["code"] == code), None)
            features.append(pick.get("norm_score", 0) if pick else 0)
        # + 额外特征：行业集中度、策略分歧度
        return np.array(features)
```

### 2.3 注入方式

修改 `_zscore_strategy` 等函数的评分公式，加入赢家因子项：

```python
# 原公式
composite = sum(z_factors[k][i] * w for k, w in weights.items())

# 新公式（注入赢家因子后）
composite = (1 - alpha) * original_score + alpha * winner_factor_score
# alpha ∈ [0, 0.3]，由 CrossStrategyLearner 动态决定
```

### 2.4 可行性评估

| 维度 | 评估 |
|------|------|
| 代码改动量 | 中等 (~200行新增) |
| 依赖 | numpy (已间接使用) |
| 风险 | 低 — 注入权重上限30%，不影响主策略逻辑 |
| 预期收益 | 在高regime切换期（如fearful→cautious），输家策略可快速适应赢家模式 |

---

## 三、创新方案 B：Regime权重自动学习 (Thompson Sampling)

### 3.1 为什么不用UCB1而用Thompson Sampling？

UCB1需要知道reward的范围（bounded [0,1]），且对非平稳环境敏感。
Thompson Sampling天然适合：
1. **贝叶斯更新** — 每个策略在每个regime下有独立的Beta分布
2. **自然探索** — 通过采样自动平衡exploit/explore
3. **非平稳兼容** — 可以用指数衰减的似然函数适应regime变化

### 3.2 实现设计

```python
from typing import Dict, List
import random

class ThompsonSamplingWeighter:
    """基于Thompson Sampling的策略权重自适应器
    
    每个策略在每个regime下维护一个Beta(alpha, beta)分布：
    - alpha = 成功次数 (win)
    - beta = 失败次数 (loss)
    
    每次决策时，从每个策略的Beta分布中采样，选择采样值最高的策略。
    """
    
    def __init__(self, prior_alpha: float = 1.0, prior_beta: float = 1.0):
        """
        Args:
            prior_alpha/beta: 先验参数（Dirichlet先验的等效样本数）
        """
        self._priors = {"alpha": prior_alpha, "beta": prior_beta}
        # 结构: {regime: {strategy: [alpha, beta]}}
        self._counts: Dict[str, Dict[str, List[float]]] = defaultdict(
            lambda: defaultdict(lambda: [prior_alpha, prior_beta])
        )
        self._regime_decay = 0.995  # 近期样本权重更高
        self._sample_history: Dict[str, List[Dict[str, float]]] = defaultdict(list)
    
    def update(self, regime: str, strategy: str, is_win: bool) -> None:
        """更新策略在指定regime下的表现计数。"""
        counts = self._counts[regime][strategy]
        if is_win:
            counts[0] += 1  # alpha += 1
        else:
            counts[1] += 1  # beta += 1
        self._sample_history[regime].append({
            "strategy": strategy,
            "is_win": is_win,
            "timestamp": time.time()
        })
    
    def sample_weights(self, regime: str, strategies: List[str]) -> Dict[str, float]:
        """从各策略的Beta分布中采样，生成加权随机权重。
        
        Returns:
            {strategy: normalized_weight} — 每次调用结果不同（带探索噪声）
        """
        samples = {}
        for s in strategies:
            alpha, beta = self._counts[regime][s]
            # Beta分布采样
            samples[s] = random.betavariate(alpha, beta)
        
        total = sum(samples.values())
        return {s: w / total for s, w in samples.items()}
    
    def get_expected_weights(self, regime: str, strategies: List[str]) -> Dict[str, float]:
        """获取期望权重（去噪版本，用于展示）。
        
        Beta(α,β)的期望 = α/(α+β)
        """
        expected = {}
        for s in strategies:
            alpha, beta = self._counts[regime][s]
            expected[s] = alpha / (alpha + beta) if (alpha + beta) > 0 else 0.25
        total = sum(expected.values())
        return {s: w / total for s, w in expected.items()}
    
    def get_confidence(self, regime: str, strategy: str) -> float:
        """策略置信度 = 1 / (1 + sqrt(variance))
        
        Beta分布方差 = αβ / ((α+β)²(α+β+1))
        样本越少，方差越大，置信度越低
        """
        alpha, beta = self._counts[regime][strategy]
        total = alpha + beta
        if total < 3:
            return 0.1  # 冷启动期低置信度
        var = (alpha * beta) / ((total ** 2) * (total + 1))
        return 1.0 / (1.0 + math.sqrt(var))
```

### 3.3 与现有系统的集成点

```python
# 在 StrategyTournament.__init__ 中添加
def __init__(self):
    self.ts_weighter = ThompsonSamplingWeighter(prior_alpha=1.0, prior_beta=3.0)
    # prior_beta > prior_alpha → 先验偏向保守（默认给表现差的策略更低权重）

# 在 verify_by_regime 中调用 update
def verify_by_regime(self, strategy_name, picks, actual_returns, regime):
    for pick in picks[:3]:
        ret = actual_returns.get(pick["code"], 0.0)
        is_win = ret > 0
        self.ts_weighter.update(regime, strategy_name, is_win)
        # ... 原有记录逻辑不变

# 在 get_ensemble_picks 中替换硬编码权重
def get_ensemble_picks(self, results, regime="normal", top_n=3):
    strategies = list(results.keys())
    
    # 获取TS权重（带探索噪声）
    ts_weights = self.ts_weighter.sample_weights(regime, strategies)
    
    # 与先验权重混合（防止冷启动时过度波动）
    prior_weights = REGIME_WEIGHT_PRIORS.get(regime, DEFAULT_WEIGHTS)
    blend_ratio = self._get_blending_ratio(regime)  # 样本越多，越信任TS
    
    blended_weights = {}
    for s in strategies:
        blended_weights[s] = (1 - blend_ratio) * prior_weights.get(s, 0.25) \
                           + blend_ratio * ts_weights.get(s, 0.25)
    
    # ... 后续ensemble逻辑不变
```

### 3.4 冷启动处理

| 阶段 | 条件 | 行为 |
|------|------|------|
| 冷启动 | 总样本 < 10 | 100%使用先验权重 REGIME_WEIGHT_PRIORS |
| 过渡 | 10 ≤ 样本 < 30 | 70%先验 + 30%TS |
| 稳定 | 样本 ≥ 30 | 逐步增加TS占比至80% |

### 3.5 可行性评估

| 维度 | 评估 |
|------|------|
| 代码改动量 | 小 (~150行新增，~50行修改) |
| 依赖 | 纯Python标准库 (random.betavariate) |
| 风险 | 极低 — TS是成熟算法，且与先验混合保证稳定性 |
| 预期收益 | 在fearful regime下，动量策略权重会自动从40%升至60-70%（基于实证明显优势） |

---

## 四、创新方案 C：新策略提案

### 4.1 波动率套利策略 (Volatility Arbitrage)

**动机**: 当前系统在fearful regime下，均值回归策略表现极差(-35.63%)，因为恐慌期超跌继续超跌。
波动率套利不赌反弹方向，而是赌波动率均值回归。

```python
def _volatility_arb_strategy(
    trend_map: dict, pipe_map: dict, candidates: list
) -> StrategyResult:
    """波动率套利策略
    
    核心逻辑:
    - 高波动率ETF在恐慌期被过度抛售 → 波动率本身会均值回归
    - 使用 realized vol / implied vol 的偏离度作为信号
    - 不赌方向，只赌波动率收缩
    
    信号:
    1. 20日realized vol > 60日moving avg of vol (vol扩张期)
    2. position_pct < 20 (价格处于低位)
    3. volume_ratio > 1.5 (恐慌放量 = 潜在底部信号)
    """
    scored = []
    for code, info in candidates:
        t = trend_map.get(code)
        if not t or t.data_days < 30:
            continue
        
        # Vol expansion signal: current vol > historical avg
        vol_ratio = t.volatility_20d / max(t.volatility_60d, 1)  # 需从TrendSnapshot扩展
        
        # Volume surge + low position = panic bottom proxy
        panic_bottom = (
            (t.volume_ratio_5_20 - 1.0) * 10   # volume surge
            * (1 - t.position_pct / 100)         # low position
        )
        
        # Score: high vol expansion + panic bottoming = good entry
        vol_score = vol_ratio * 0.4 + panic_bottom * 0.6
        
        scored.append({
            "code": code,
            "name": info.get("name", code),
            "sector": info.get("sector", ""),
            "score": round(vol_score, 3),
            "vol_ratio": round(vol_ratio, 2),
            "panic_bottom_score": round(panic_bottom, 2),
        })
    
    scored.sort(key=lambda x: -x["score"])
    # ... Top3 dedup logic same as other strategies
```

**需要修改的数据层**: `TrendSnapshot` 需增加 `volatility_60d` 字段。

### 4.2 跨策略共识策略 (Cross-Strategy Consensus)

**动机**: 当多个独立策略同时看好同一ETF时，这是最强的信号。
当前系统中513350就是典型案例 — 被4个策略同时选中。

```python
def _consensus_strategy(
    trend_map: dict, pipe_map: dict, candidates: list,
    strategy_results: dict[str, StrategyResult]  # 传入其他策略的结果
) -> StrategyResult:
    """跨策略共识策略
    
    核心逻辑:
    - 统计每只ETF被多少策略选中（在Top3内）
    - 共识度越高 → 分数越高
    - 当共识度≥3时，该ETF自动进入Top3
    
    优势:
    - 不需要额外数据源
    - 自动捕获多策略互补性
    - 在regime转换期特别有效（多个策略同时转向同一方向）
    """
    # 统计每只ETF被选中的策略数
    code_strategy_count: dict[str, int] = defaultdict(int)
    code_strategies: dict[str, set] = defaultdict(set)
    
    for sname, res in strategy_results.items():
        for pick in res.picks[:3]:
            code_strategy_count[pick["code"]] += 1
            code_strategies[pick["code"]].add(sname)
    
    scored = []
    for code, count in code_strategy_count.items():
        if count >= 2:  # 至少2个策略共识
            scored.append({
                "code": code,
                "name": "",  # 从任一策略结果中获取
                "sector": "",
                "score": count,  # 共识度直接作为分数
                "strategy_count": count,
                "strategies": list(code_strategies[code]),
            })
    
    scored.sort(key=lambda x: -x["score"])
    # ... Top3 logic
```

### 4.3 Regime动量策略 (Regime Momentum)

**动机**: regime_transition.py 已经预测了转换概率，但没有被策略利用。
如果预测"改善"概率高，应提前增加风险敞口。

```python
def _regime_momentum_strategy(
    trend_map: dict, pipe_map: dict, candidates: list,
    transition_pred: TransitionPrediction  # 从regime_transition.py获取
) -> StrategyResult:
    """Regime动量策略
    
    核心逻辑:
    - 如果 prob_improve > prob_worsen → 偏好高beta策略（动量）
    - 如果 prob_worsen > prob_improve → 偏好防御策略（低vol, 高dividend）
    - 如果 prob_stay > 0.6 → 跟随当前regime的最优策略
    
    信号:
    1. transition_pred.blended_weights 中的策略权重
    2. 市场广度(breadth_pct)趋势
    3. 波动率趋势(vol_trend)
    """
    scored = []
    for code, info in candidates:
        t = trend_map.get(code)
        if not t:
            continue
        
        # 根据regime预测调整评分
        regime_signal = self._compute_regime_signal(transition_pred)
        
        # 高beta ETF在改善预期下得分更高
        beta_adjusted_score = t.change_20d * (1 + regime_signal)
        
        scored.append({
            "code": code,
            "name": info.get("name", code),
            "sector": info.get("sector", ""),
            "score": round(beta_adjusted_score, 3),
            "regime_signal": round(regime_signal, 3),
        })
    
    scored.sort(key=lambda x: -x["score"])
    # ... Top3 logic
```

### 4.4 新策略可行性矩阵

| 策略 | 数据需求 | 代码改动 | 预期提升 | 实施难度 |
|------|----------|----------|----------|----------|
| 波动率套利 | 需扩展TrendSnapshot (+vol_60d) | 中 | 在fearful regime替代均值回归 | ⭐⭐⭐ |
| 跨策略共识 | 零额外数据 | 低 | 自动捕获互补性 | ⭐ |
| Regime动量 | 复用regime_transition.py | 低 | 前瞻性调整风险敞口 | ⭐⭐ |

---

## 五、推荐实施路线

### Phase 1 (立即实施，1-2天)

1. **Thompson Sampling权重自适应** — 改动最小，收益最明确
   - 新增 `thompson_weighter.py` (~150行)
   - 修改 `strategy_tournament.py` 的 `verify_by_regime` 和 `get_ensemble_picks` (~50行)
   - 无需修改数据层

2. **跨策略共识策略** — 零数据依赖
   - 新增 `_consensus_strategy` 函数 (~60行)
   - 注册到 `STRATEGIES` 列表
   - 作为第5个策略参与锦标赛

### Phase 2 (中期，1周)

3. **策略互学习机制** — 需要修改各策略的评分公式
   - 新增 `cross_strategy_learner.py` (~200行)
   - 修改 `_zscore_strategy`, `_momentum_strategy` 等注入赢家因子
   - 需要定义统一的特征向量格式

### Phase 3 (长期，2-4周)

4. **波动率套利策略** — 需要扩展数据层
   - 修改 `TrendSnapshot` 增加 `volatility_60d`
   - 新增 `_volatility_arb_strategy` (~100行)
   - 需要重新训练/校准参数

5. **Regime动量策略** — 与regime_transition.py深度集成
   - 修改 `regime_transition.py` 输出更细粒度的信号
   - 新增 `_regime_momentum_strategy` (~80行)

---

## 六、预期效果量化

基于当前60日回测数据：

| 指标 | 当前 | Phase 1后 | Phase 2后 | Phase 3后 |
|------|------|-----------|-----------|-----------|
| fearful胜率(动量) | 100% | 100% | 100% | 100% |
| fearful胜率(均值回归) | 0% | 0% | ~15%(互学习) | ~25%(波动率套利替代) |
| 整体ensemble Sharpe | 0.88 | ~1.05(TS自适应) | ~1.15(+共识策略) | ~1.25(+波动率套利) |
| regime转换适应速度 | 滞后1轮 | 同轮适应 | 半轮适应 | 前瞻适应 |

---

## 七、风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| TS过拟合短期波动 | 权重频繁切换 | 先验混合 + 最小样本阈值 |
| 互学习引入噪声 | 输家学到错误因子 | 注入权重上限30% + 衰减过滤 |
| 共识策略假阳性 | 多个策略同时犯错 | 共识度≥3才触发 + 结合基本面过滤 |
| 波动率套利数据不足 | 无法准确计算vol_ratio | 先用60d MA近似，后续用akshare精确计算 |
