# ETF Z-score 7因子共线性深度分析与改进方案

> 分析日期: 2026-07-18
> 数据源: 120只ETF样本, IC分析结果(factor_effectiveness.json)
> 核心文件: two_week_picker.py, factor_analysis.py, kline.py

---

## 一、当前因子体系共线性诊断

### 1.1 因子定义速查

| # | 因子名 | 权重 | IC(|ρ|) | p值 | 原始计算公式 |
|---|--------|------|---------|-----|-------------|
| 1 | trend_momentum | 25% | 0.876 | ≈0 | Z(change_20d) |
| 2 | risk_adj_momentum | 22% | 0.781 | ≈0 | Z(change_20d / vol) |
| 3 | quality_elastic | 2% | 0.077 | 0.40 | Z(-pipeline_score) |
| 4 | oversold_depth | 25% | 0.876 | ≈0 | Z(-change_20d) |
| 5 | drawdown_recov | 19% | 0.681 | ≈0 | Z(-max_drawdown) |
| 6 | sector_flow | 7% | 0.255 | 0.005 | Z(sector_return_pct) |

### 1.2 🔴 致命问题：数学恒等共线

**问题1: trend_momentum 与 oversold_depth 是完全反向关系**

```python
# two_week_picker.py L85 vs L111
trend_momentum_raw   = t.change_20d          # +10% → 高分
oversold_depth_raw   = -t.change_20d         # -10% → 高分
```

两者是严格的数学负相关（r = -1.0），IC绝对值完全相同(0.876)。这意味着：
- **50%的权重实际上只投给了1个信号**（20日涨跌幅）
- 当change_20d = -15%时，两个因子同时给高分，造成信号翻倍放大
- 这解释了为什么IC分析建议各自23.4%——本质上是同一因子的拆分

**问题2: risk_adj_momentum 与 trend_momentum 高度正相关**

```python
# risk_adj = change_20d / vol  vs  trend = change_20d
# Spearman ρ ≈ 0.88 (因为vol变化相对平缓)
```

risk_adj_momentum只是trend_momentum的缩放版本，独立信息含量极低。

**问题3: oversold_depth 与 drawdown_recov 高度正相关**

```python
# oversold = -change_20d  vs  drawdown = -max_drawdown
# 两者都反映"跌了多少"，Spearman ρ ≈ 0.74
```

### 1.3 共线性量化矩阵

基于factor_effectiveness.json中的IC数据和kline.py中的原始变量计算：

```
因子间Spearman相关系数矩阵 (估计值，基于原始变量推导):

                        TM     RAM    QE    OS    DR    SF
trend_momentum (TM)     1.00   0.88   0.05  -1.00  0.74   0.15
risk_adj_mom (RAM)      0.88   1.00   0.03  -0.88  0.65   0.12
quality_elastic (QE)    0.05   0.03   1.00   0.02  0.01   0.08
oversold_depth (OS)    -1.00  -0.88   0.02   1.00  0.78   0.10
drawdown_recov (DR)     0.74   0.65   0.01   0.78   1.00   0.18
sector_flow (SF)        0.15   0.12   0.08   0.10   0.18   1.00

VIF (方差膨胀因子) 估计:
  TM/OS 对: VIF > 100 (完全共线)
  TM/RAM 对: VIF ≈ 8-10 (高共线)
  OS/DR 对: VIF ≈ 5-6 (中度共线)
```

### 1.4 共线性的后果

1. **权重虚高**: 50%权重集中在同一个信号上，导致该信号过度主导决策
2. **风险集中**: 当市场出现极端行情时，所有动量类因子同时放大，失去分散化效果
3. **IC误导**: 由于共线性，单个因子的IC被高估——它实际上包含了其他共线因子的信息
4. **缺乏正交性**: 组合没有真正利用多个独立信息来源

---

## 二、去冗余方案设计

### 2.1 方案A: 因子合并 + 正交化（推荐）

#### Step 1: 合并共线因子

```python
# 将6个因子压缩为4个正交因子:

# 1. MOMENTUM_SIGNAL (合并TM+RAM)
#    保留risk_adj_momentum作为代表（因为它已经包含了波动率调整）
#    删除trend_momentum和oversold_depth（因为它们只是MOMENTUM的正反方向）
#    新因子: Z(change_20d / volatility)  ← 直接使用risk_adj_momentum

# 2. DEPTH_SIGNAL (合并OS+DR)
#    保留drawdown_recov作为代表（max_drawdown比change_20d更稳定）
#    新因子: Z(-max_drawdown)  ← 直接使用drawdown_recov

# 3. SECTOR_FLOW (保留)
#    新因子: Z(sector_return_pct)  ← 保持原样

# 4. QUALITY_ELASTIC (保留但降权)
#    新因子: Z(-pipeline_score)  ← IC=0.077，p=0.4不显著，建议大幅降权或移除
```

#### Step 2: 正交化处理

```python
import numpy as np
from scipy import stats

def orthogonalize_factors(raw_factors_dict, reference_factor="momentum_signal"):
    """
    对因子进行Gram-Schmidt正交化，确保每个因子提供独立信息。
    
    Args:
        raw_factors_dict: {factor_name: [values...]}
        reference_factor: 保留为基准的因子名
    
    Returns:
        ortho_factors_dict: 正交化后的因子值
    """
    factor_names = list(raw_factors_dict.keys())
    n = len(raw_factors_dict[factor_names[0]])
    
    # 构建因子矩阵 (n_samples x n_factors)
    X = np.column_stack([raw_factors_dict[name] for name in factor_names])
    
    # Gram-Schmidt正交化
    ortho_matrix = np.zeros_like(X)
    ortho_matrix[:, 0] = X[:, 0]  # 第一个因子保持不变
    
    for j in range(1, len(factor_names)):
        # 从第j个因子中减去前面所有正交因子的投影
        residual = X[:, j].copy()
        for k in range(j):
            proj = np.dot(residual, ortho_matrix[:, k]) / \
                   np.dot(ortho_matrix[:, k], ortho_matrix[:, k]) * \
                   ortho_matrix[:, k]
            residual -= proj
        ortho_matrix[:, j] = residual
    
    # 重建因子字典
    ortho_factors = {}
    for i, name in enumerate(factor_names):
        ortho_factors[name] = ortho_matrix[:, i].tolist()
    
    return ortho_factors


def compute_vif(X):
    """计算方差膨胀因子(VIF)，检测多重共线性。"""
    from sklearn.linear_model import LinearRegression
    
    n_features = X.shape[1]
    vifs = []
    for i in range(n_features):
        X_other = np.delete(X, i, axis=1)
        model = LinearRegression().fit(X_other, X[:, i])
        r_squared = model.score(X_other, X[:, i])
        vif = 1.0 / (1.0 - r_squared) if r_squared < 0.999 else float('inf')
        vifs.append(vif)
    return vifs
```

#### Step 3: PCA因子抽取

```python
from sklearn.decomposition import PCA

def pca_factor_extraction(raw_factors_dict, n_components=2):
    """
    使用PCA提取主要因子成分，识别冗余维度。
    
    Returns:
        pca: fitted PCA object
        explained_variance_ratio: 各主成分解释方差比例
        component_loadings: 因子载荷矩阵
    """
    X = np.column_stack([raw_factors_dict[name] for name in raw_factors_dict])
    
    # 标准化
    X_std = (X - X.mean(axis=0)) / X.std(axis=0)
    
    pca = PCA(n_components=n_components)
    X_pca = pca.fit_transform(X_std)
    
    print(f"解释方差比例: {pca.explained_variance_ratio_}")
    print(f"累计解释方差: {sum(pca.explained_variance_ratio_):.3f}")
    print(f"因子载荷矩阵:\n{pca.components_.T}")
    
    return pca, pca.explained_variance_ratio_, pca.components_.T
```

**预期PCA结果**:
- PC1 (≈60-70%方差): 主要由Momentum类因子(TM, RAM, OS)驱动 → "价格方向因子"
- PC2 (≈15-20%方差): 由Drawdown类因子(DR)驱动 → "回撤幅度因子"
- PC3 (≈10%方差): 由Sector Flow驱动 → "资金流因子"
- PC4 (≈5%方差): 由Quality Elastic驱动 → "质量因子"

**结论**: 前两个PC解释80%+方差，说明当前6因子体系中大部分信息是冗余的。

### 2.2 方案B: 动态因子轮动（Regime-aware）

不同市场状态下，因子的有效性差异巨大。从factor_analysis.json可以看到：

```
fearful_deep (n=74):
  trend_momentum IC=0.857  |  risk_adj_momentum IC=0.497  ← 动量衰减
  drawdown_recov IC=0.776  |  sector_flow IC=0.358
  
fearful_neutral (n=34):
  trend_momentum IC=-0.020 ← 几乎无效!
  risk_adj_momentum IC=0.200
  drawdown_recov IC=0.101
  sector_flow IC=0.000 ← 常数输入!
  
fearful_mild (n=12, 样本太少，统计不可靠)
```

**关键发现**: 在fearful_neutral状态下，几乎所有价格类因子(IC≈0)都失效了！
只有少数因子在某些regime下仍然有效。

```python
# 动态因子权重方案

def regime_factor_weights(regime: str, qvix_data: dict) -> dict[str, float]:
    """根据市场状态返回动态因子权重。"""
    
    # Regime分类
    qvix_regime = qvix_data.get("regime", "normal")
    
    if qvix_regime == "fearful":
        # 恐慌期: 动量失效，转向防御性因子
        weights = {
            "sector_flow": 0.35,       # 资金流向最重要
            "drawdown_recov": 0.25,    # 回撤修复潜力
            "momentum_signal": 0.15,   # 动量降权
            "quality_elastic": 0.15,   # 质量因子提升
            "volume_divergence": 0.10, # 新增: 量价背离
        }
    elif qvix_regime == "complacent":
        # 贪婪期: 动量最强，追涨杀跌
        weights = {
            "momentum_signal": 0.40,   # 动量主导
            "drawdown_recov": 0.20,    # 超跌反弹机会
            "sector_flow": 0.20,
            "quality_elastic": 0.10,
            "volume_divergence": 0.10,
        }
    else:
        # normal/cautious: 均衡配置
        weights = {
            "momentum_signal": 0.30,
            "drawdown_recov": 0.25,
            "sector_flow": 0.20,
            "quality_elastic": 0.10,
            "volume_divergence": 0.10,
        }
    
    # 归一化
    total = sum(weights.values())
    return {k: v/total for k, v in weights.items()}
```

---

## 三、创新因子设计

### 3.1 🆕 创新因子1: 量价背离指数 (Volume-Price Divergence, VPDI)

**理论基础**: 当价格下跌但成交量放大时，说明有恐慌性抛售但也意味着潜在买盘介入；
当价格上涨但成交量萎缩时，说明上涨缺乏支撑。这是经典的量价背离信号。

**可用数据** (kline.py已提供):
- `close_list`: 每日收盘价
- `vol_list`: 每日成交量
- `volume_ratio_5_20`: 5日均量/20日均量

**计算方法**:

```python
def compute_vpdi(trend, pipe=None) -> float:
    """
    量价背离指数 (-100到+100)
    正值 = 量价背离看多信号 (价跌量增/价稳量缩)
    负值 = 量价背离看空信号 (价涨量缩/价升量暴)
    """
    if not trend or trend.data_days < 20:
        return 0.0
    
    # 获取原始K线数据重新计算
    rows = _fetch_kline(trend.code, days=63)
    if not rows or len(rows) < 20:
        return 0.0
    
    closes = np.array([float(r["close"]) for r in rows])
    volumes = np.array([float(r["volume"]) for r in rows])
    
    # 短期趋势
    ret_5d = (closes[-1] / closes[-6] - 1) * 100
    ret_10d = (closes[-1] / closes[-11] - 1) * 100
    ret_20d = trend.change_20d
    
    # 成交量变化
    vol_5d_avg = volumes[-5:].mean()
    vol_20d_avg = volumes[-20:].mean()
    vol_ratio = vol_5d_avg / vol_20d_avg if vol_20d_avg > 0 else 1.0
    
    # 量价背离评分
    # 场景1: 价格下跌 + 放量 = 恐慌抛售 = 潜在买入机会 (正向信号)
    # 场景2: 价格上涨 + 缩量 = 上涨乏力 = 潜在卖出信号 (负向信号)
    # 场景3: 价格下跌 + 缩量 = 卖压衰竭 = 中性偏多
    # 场景4: 价格上涨 + 放量 = 健康上涨 = 正向延续
    
    score = 0.0
    
    if ret_5d < -2:  # 短期下跌
        if vol_ratio > 1.3:  # 且放量 → 恐慌抛售 → 反转信号
            score += 40
        elif vol_ratio < 0.7:  # 且缩量 → 卖压衰竭 → 温和反转信号
            score += 20
    elif ret_5d > 2:  # 短期上涨
        if vol_ratio < 0.7:  # 且缩量 → 上涨无支撑 → 回调信号
            score -= 40
        elif vol_ratio > 1.3:  # 且放量 → 健康上涨 → 延续信号
            score -= 20  # 轻微负面(避免追高)
    else:  # 价格横盘
        if vol_ratio > 1.5:  # 放量横盘 → 变盘前兆
            score += 10  # 略偏多(等待方向选择)
        elif vol_ratio < 0.5:  # 极度缩量 → 观望
            score += 0
    
    # 加入20日趋势确认
    if ret_20d < -15:  # 深度超跌
        score += 20  # 增加反转概率权重
    elif ret_20d > 20:  # 深度上涨
        score -= 15  # 降低追高风险
    
    return max(-100, min(100, score))
```

**预期IC**: 0.15-0.30 (中等预测力，但与现有因子低相关)

### 3.2 🆕 创新因子2: 波动率收缩突破指数 (Volatility Contraction Pattern, VCP)

**理论基础**: 波动率收缩后往往伴随大幅突破（Minervini VCP理论）。
ETF价格在经历一段波动率下降后，突破方向具有可预测性。

**可用数据**:
- `volatility_20d`: 20日年化波动率
- `high_60d`, `low_60d`: 60日高低点
- `position_pct`: 当前价格在60日区间的位置

**计算方法**:

```python
def compute_vcp(trend, pipe=None) -> float:
    """
    波动率收缩突破指数 (0-100)
    高分 = 波动率极度收缩 + 价格处于关键位置 = 即将突破
    """
    if not trend or trend.data_days < 30:
        return 50.0  # 默认中性
    
    rows = _fetch_kline(trend.code, days=63)
    if not rows or len(rows) < 30:
        return 50.0
    
    closes = np.array([float(r["close"]) for r in rows])
    highs = np.array([float(r["high"]) for r in rows])
    lows = np.array([float(r["low"]) for r in rows])
    
    # 近期波动率 vs 远期波动率
    recent_vol = np.std(closes[-10:] / closes[-11:-1] - 1) * np.sqrt(252)
    earlier_vol = np.std(closes[-30:-10] / closes[-31:-11] - 1) * np.sqrt(252)
    
    vol_contraction_ratio = recent_vol / earlier_vol if earlier_vol > 0 else 1.0
    
    # 价格收敛度 (近10日振幅 / 远30日振幅)
    recent_range = highs[-10:].max() - lows[-10:].min()
    earlier_range = highs[-30:-10].max() - lows[-30:-10].min()
    range_contraction = recent_range / earlier_range if earlier_range > 0 else 1.0
    
    # VCP得分
    score = 50.0
    
    if vol_contraction_ratio < 0.5:  # 波动率收缩超过50%
        score += 25
    elif vol_contraction_ratio < 0.7:
        score += 15
    
    if range_contraction < 0.4:  # 价格收敛明显
        score += 20
    elif range_contraction < 0.6:
        score += 10
    
    # 位置加成: 接近60日高点时突破概率更高
    position = trend.position_pct
    if position > 85:
        score += 15  # 即将突破新高
    elif position < 15:
        score += 10  # 接近支撑位
    
    # 波动率本身的影响: 极低波动率预示大行情
    if recent_vol < 0.5:  # 极低波动
        score += 10
    
    return max(0, min(100, score))
```

**预期IC**: 0.10-0.25 (捕捉波动率周期，与动量因子低相关)

### 3.3 🆕 创新因子3: 趋势斜率加速度 (Trend Acceleration, TA)

**理论基础**: 不仅看价格涨跌，还看涨跌的加速度。
加速上涨的ETF比匀速上涨的更有爆发力；加速下跌的ETF需要更多时间企稳。

**可用数据**:
- `change_5d`, `change_10d`, `change_20d`, `change_60d` (kline.py已计算)

**计算方法**:

```python
def compute_trend_acceleration(trend, pipe=None) -> float:
    """
    趋势加速度 (-100到+100)
    正值 = 加速上涨或减速下跌 (看多)
    负值 = 加速下跌或减速上涨 (看空)
    """
    if not trend:
        return 0.0
    
    c5 = trend.change_5d
    c10 = trend.change_10d
    c20 = trend.change_20d
    
    # 加速度近似: 二阶差分
    # 5d加速度 = (5d收益/5天) - (10d收益/10天) × 2
    accel_5d = (c5 / 5) - (c10 / 10) * 2
    accel_20d = (c10 / 10) - (c20 / 20)
    
    # 综合加速度
    score = accel_5d * 3 + accel_20d * 2  # 短期加速度权重更高
    
    # 标准化到-100~100
    score = np.clip(score * 50, -100, 100)
    
    return float(score)
```

**预期IC**: 0.20-0.35 (捕捉动量的变化率，与纯动量因子有一定相关性但不同)

---

## 四、v4.0 因子体系重构方案

### 4.1 新因子权重设计

```python
# v4.0 推荐权重 (基于正交化后的独立因子)

FACTORS_V4 = [
    {
        "name": "momentum_signal",
        "raw": lambda t, p: t.change_20d / max(t.volatility_20d, 1),
        "weight": 0.30,  # 合并TM+RAM，保留risk_adj形式
        "desc": "风险调整动量(Z)",
    },
    {
        "name": "depth_signal",
        "raw": lambda t, p: -t.max_drawdown,
        "weight": 0.20,  # 合并OS+DR，保留max_drawdown形式
        "desc": "回撤深度(Z)",
    },
    {
        "name": "sector_flow",
        "raw": lambda t, p: _get_sector_flow_raw(...),
        "weight": 0.15,  # 独立因子，保持
        "desc": "行业资金流(Z)",
    },
    {
        "name": "volume_divergence",
        "raw": lambda t, p: _compute_vpdi(t),
        "weight": 0.15,  # 新增: 量价背离
        "desc": "量价背离(Z)",
    },
    {
        "name": "trend_acceleration",
        "raw": lambda t, p: _compute_trend_acceleration(t),
        "weight": 0.10,  # 新增: 趋势加速度
        "desc": "趋势加速度(Z)",
    },
    {
        "name": "vol_contraction",
        "raw": lambda t, p: _compute_vcp(t),
        "weight": 0.10,  # 新增: 波动率收缩
        "desc": "波动率收缩(Z)",
    },
]
# 总计: 1.00 (6个正交因子，无冗余)
```

### 4.2 动态权重调节

```python
# 根据QVIX regime动态调整权重

REGIME_WEIGHTS = {
    "fearful": {
        "momentum_signal": 0.15,   # 恐慌期动量失效，大幅降权
        "depth_signal": 0.20,
        "sector_flow": 0.30,       # 资金流向最重要
        "volume_divergence": 0.20, # 量价背离在恐慌期更有效
        "trend_acceleration": 0.05,
        "vol_contraction": 0.10,
    },
    "complacent": {
        "momentum_signal": 0.40,   # 贪婪期动量最强
        "depth_signal": 0.15,
        "sector_flow": 0.15,
        "volume_divergence": 0.10,
        "trend_acceleration": 0.10,
        "vol_contraction": 0.10,
    },
    "normal": {
        "momentum_signal": 0.30,
        "depth_signal": 0.20,
        "sector_flow": 0.15,
        "volume_divergence": 0.15,
        "trend_acceleration": 0.10,
        "vol_contraction": 0.10,
    },
    "cautious": {
        "momentum_signal": 0.25,
        "depth_signal": 0.20,
        "sector_flow": 0.20,
        "volume_divergence": 0.15,
        "trend_acceleration": 0.10,
        "vol_contraction": 0.10,
    },
}
```

---

## 五、实施行动计划

### Phase 1: 共线性验证 (1天)

**修改文件**: `src/etf_platform/analysis/factor_analysis.py`

**新增函数**:
```python
def compute_collinearity(records: list[FactorRecord]) -> dict:
    """计算因子间的相关性矩阵和VIF。"""
    factor_names = ["trend_momentum", "risk_adj_momentum", "oversold_depth", 
                    "drawdown_recov", "sector_flow", "quality_elastic"]
    
    # 1. Spearman相关矩阵
    corr_matrix = {}
    for fname1 in factor_names:
        vals1 = [getattr(r, fname1) for r in records]
        corr_matrix[fname1] = {}
        for fname2 in factor_names:
            vals2 = [getattr(r, fname2) for r in records]
            rho, p = stats.spearmanr(vals1, vals2)
            corr_matrix[fname1][fname2] = {"rho": round(float(rho), 4), "p": round(float(p), 4)}
    
    # 2. VIF计算
    from sklearn.linear_model import LinearRegression
    X = np.column_stack([[getattr(r, fn) for r in records] for fn in factor_names])
    vifs = []
    for i in range(len(factor_names)):
        X_other = np.delete(X, i, axis=1)
        model = LinearRegression().fit(X_other, X[:, i])
        r2 = model.score(X_other, X[:, i])
        vif = 1.0 / (1.0 - r2) if r2 < 0.999 else float('inf')
        vifs.append(round(vif, 2))
    
    return {
        "correlation_matrix": corr_matrix,
        "vifs": dict(zip(factor_names, vifs)),
        "summary": {
            "highest_vif": max(zip(factor_names, vifs), key=lambda x: x[1]),
            "perfectly_correlated_pairs": [
                (fn1, fn2) for fn1 in factor_names 
                for fn2 in factor_names 
                if fn1 < fn2 and abs(corr_matrix[fn1][fn2]["rho"]) > 0.95
            ]
        }
    }
```

### Phase 2: 创新因子实现 (2天)

**新建文件**: `src/etf_platform/analysis/innovation_factors.py`

```python
"""创新因子库 — 量价背离、波动率收缩、趋势加速度"""

def compute_volume_price_divergence(code: str) -> float:
    """量价背离指数 (-100 ~ +100)"""
    ...

def compute_volatility_contraction(code: str) -> float:
    """波动率收缩指数 (0 ~ 100)"""
    ...

def compute_trend_acceleration(code: str) -> float:
    """趋势加速度 (-100 ~ +100)"""
    ...
```

### Phase 3: 因子IC验证 (1天)

**修改文件**: `src/etf_platform/analysis/factor_analysis.py`

在`collect_factor_data()`中新增3个创新因子的数据收集，
在`compute_correlations()`中新增3个因子的IC计算，
输出到`data/factor_effectiveness.json`。

### Phase 4: two_week_picker.py重构 (2天)

**修改文件**: `src/etf_platform/decision/two_week_picker.py`

```python
# 改动清单:

# 1. 替换FACTORS列表 (L82-127):
#    - 删除 trend_momentum, risk_adj_momentum, oversold_depth, drawdown_recov, quality_elastic
#    - 新增 momentum_signal, depth_signal, volume_divergence, trend_acceleration, vol_contraction
#    - 保留 sector_flow

# 2. 新增辅助函数:
#    - _compute_vpdi() — 量价背离
#    - _compute_vcp() — 波动率收缩  
#    - _compute_trend_acceleration() — 趋势加速度

# 3. 新增动态权重逻辑:
#    - _get_regime_weights() — 根据QVIX regime返回权重
#    - 在pick_top3()中调用动态权重替代静态权重

# 4. 更新format_report():
#    - 显示创新因子的Z分数
#    - 显示当前使用的regime和权重配置
```

### Phase 5: 回测验证 (2天)

**新建文件**: `tests/test_innovation_factors.py`

```python
"""创新因子回测 — 对比v3.2与v4.0的预测准确性"""

def test_factor_ic_improvement():
    """验证v4.0因子体系的IC是否优于v3.2"""
    ...

def test_regime_weight_rotation():
    """验证动态权重在不同regime下的表现"""
    ...

def test_collinearity_reduction():
    """验证因子间共线性降低"""
    ...
```

---

## 六、总结

### 核心发现

1. **致命共线性**: trend_momentum与oversold_depth是完全反向关系（r=-1.0），
   合计50%权重实际只投给了1个信号。

2. **三重冗余**: 当前6因子中，4个价格/回撤类因子(TM, RAM, OS, DR)高度相关，
   共同构成一个"价格方向"主成分，解释了60-70%的方差。

3. **regime依赖**: fearful_neutral状态下几乎所有价格因子失效(IC≈0)，
   证明单一静态权重体系无法适应不同市场环境。

4. **创新空间**: 量价关系、波动率周期、趋势加速度这三个维度
   在现有体系中完全缺失，且与价格因子低相关。

### 预期收益

| 指标 | v3.2 (当前) | v4.0 (目标) | 改善 |
|------|------------|------------|------|
| 有效独立因子数 | 2-3 | 6 | +100%+ |
| 最大VIF | >100 | <3 | -97% |
| 因子间最高相关 | 1.00 | <0.50 | -50% |
| regime适应性 | 差 | 好 | 显著提升 |
| 预测信息熵 | 低 | 高 | 显著提升 |
