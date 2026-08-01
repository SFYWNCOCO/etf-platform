# ETF Platform 系统自诊报告

**扫描时间**: 2026-07-18  
**扫描范围**: D:/龙虾/.openclaw/etf-platform (全平台 .py 文件)  
**扫描模块**: 分数量纲 / 路径 / Bare Except / 集成 / 未使用代码  

---

## 1. 分数量纲不一致 (Severity: HIGH)

### 问题概述
平台存在 **两套完全不同的分数体系**，在 `meta_predictor.py` 中尝试统一但仍有风险。

### 分数体系对照表

| 模块 | 分数范围 | 量纲 | 含义 |
|------|---------|------|------|
| `scorer.py` L10_Demand | 4.0 ~ 8.0 | 1-10 | 消费需求强度 |
| `scorer.py` L11_SectorRisk | 1.0 ~ 10.0 | 1-10 | 行业风险等级 |
| `layers/l12_macro_cycle.py` | 1.0 ~ 10.0 | 1-10 | 宏观周期评分 |
| `layers/l14_stoic_risk.py` | 1.0 ~ 10.0 | 1-10 | 基本面风险 |
| `layers/l15_state_similarity.py` | 1.0 ~ 10.0 | 1-10 | 状态相似度 |
| `layers/l16_live_signals.py` (premium/liquidity/fund_quality) | 1.0 ~ 10.0 | 1-10 | 实时信号 |
| `layers/l17_quantitative_factor.py` | 1.0 ~ 10.0 | 1-10 | 因子评分 |
| `layers/l18_var_risk.py` | 1.0 ~ 10.0 | 1-10 | VaR风险 |
| `layers/l19_fx_channel.py` | 1.0 ~ 10.0 | 1-10 | 外汇通道 |
| `layers/l20_option_volatility.py` | 1.0 ~ 10.0 | 1-10 | 期权波动率 |
| `layers/l22_market_pendulum.py` | 1.0 ~ 10.0 | 1-10 | 市场钟摆 |
| `layers/l23_microstructure.py` | 1.0 ~ 10.0 | 1-10 | 微观结构 |
| `analysis/causal.py` | 0.0 ~ 1.0 | 0-1 | 因果置信度 (加权合成) |
| `analysis/chain.py` | 0.0 ~ 1.0+ | 无界 | 产业链瓶颈强度 |
| **`decision/two_week_picker.py`** | **0 ~ 100** | **0-100** | **Z-score综合分** |
| `decision/ml_predictor.py` | 概率 0-1 + expected_return | 混合 | ML预测 |
| `decision/strategy_tournament.py` | 依赖pipeline_score(1-10) | 1-10 | 锦标赛集成 |
| `analysis/event_nlp.py` | signal_strength 通常 ~50 | 0-100 | NLP事件信号 |
| `optimize/portfolio.py` | 依赖supply/capital/chain | 混合 | 组合优化 |
| `scripts/calculate_penetration_scores.py` | 0-100 | 0-100 | 渗透率评分 |

### 关键发现

**1. `two_week_picker.py` 的 0-100 Z-score 分与其他所有层的 1-10 分不兼容**
```python
# two_week_picker.py L374
"two_week_score": round(zscore_weighted_sum, 1),  # 0-100

# 而 scorer.py L46 返回 max(4.0, min(8.0, ...)) 即 4-8 区间
```

**2. `meta_predictor.py` 的归一化可能掩盖问题**
```python
# meta_predictor.py L137-139
score = p.get("score", p.get("two_week_score", 50))
p["norm_score"] = max(0.0, min(100.0, float(score)))
```
- `two_week_score` (0-100) 直接通过 → 正确
- `pipeline_score` (1-10) 被当作 "score" → 归一化为 1-10 而非 10-100 → **低权重**
- `signal_strength` (~50) → 通过 → 正常

**3. `confidence_calibrator.py` 假设 two_week_score 是 0-100**
```python
# confidence_calibrator.py L229
# score: Raw two_week_score (0-100)
```
但如果输入的是 1-10 的量级的 score，校准曲线会完全错误。

### 建议
1. 在 `meta_predictor.py` 的 `_normalize_scores()` 中区分来源：对 `pipeline_score` (1-10) 乘以 10 归一化到 0-100
2. 或统一所有层输出 0-100 格式（推荐）
3. 添加单元测试验证各模块输出范围

---

## 2. 路径 Bug (Severity: MEDIUM-HIGH)

### 2a. `event_nlp.py` 回退缓存路径错误 (CRITICAL)

**位置**: `src/etf_platform/analysis/event_nlp.py` L1001

```python
# 第971行 (正确):
cache_path = Path(__file__).resolve().parent.parent.parent.parent / "data" / "event_signals_live.json"
# event_nlp.py -> analysis/ -> etf_platform/ -> src/ -> etf-platform/ ✓

# 第1001行 (错误):
old_cache = Path(__file__).resolve().parent.parent.parent / "data" / "event_signals.json"
# 少了一个 .parent! 指向 etf_platform/data/ 而非 etf-platform/data/
```

**影响**: 当主缓存失效时，回退到旧缓存路径永远找不到文件（路径指向 `src/etf_platform/data/` 而非 `D:/龙虾/.openclaw/etf-platform/data/`）。

**修复**:
```python
# L1001 改为:
old_cache = Path(__file__).resolve().parent.parent.parent.parent / "data" / "event_signals.json"
```

### 2b. `ml_predictor.py` BASE 路径少一层 (MEDIUM)

**位置**: `src/etf_platform/decision/ml_predictor.py` L39

```python
BASE = Path(__file__).resolve().parent.parent.parent  # etf-platform root
# decision/ -> etf_platform/ -> src/ -> 停在 etf_platform/ 目录!
# 应该是 parent.parent.parent.parent
```

对比同目录其他文件:
- `meta_predictor.py` L29: `parent.parent.parent.parent` ✓
- `confidence_calibrator.py` L28: `parent.parent.parent.parent` ✓
- `prediction_backtest.py` L23: `parent.parent.parent.parent` ✓
- `strategy_tournament.py` L33: `parent.parent.parent.parent` ✓
- `two_week_picker.py` L34: `parent.parent.parent` ✗ (同样的bug!)

**影响**: `ml_predictor.py` 的 `MODEL_DIR` 和 `PRED_DIR` 指向错误路径 (`src/etf_platform/data/ml_models/` 而非 `D:/龙虾/.openclaw/etf-platform/data/ml_models/`)。

### 2c. `two_week_picker.py` BASE 路径同样错误 (MEDIUM)

**位置**: `src/etf_platform/decision/two_week_picker.py` L34

```python
BASE = Path(__file__).resolve().parent.parent.parent  # 标注 "etf-platform root"
# 但实际停在 etf_platform/ 目录
```

**影响**: `sys.path.insert(0, str(BASE / "src"))` 插入的是 `etf_platform/src` 而非 `etf-platform/src`，可能导致相对导入混乱。

### 2d. `eastmoney.py` 5层 .parent 路径 (LOW)

**位置**: `src/etf_platform/data/eastmoney.py` L18-19

```python
Path(__file__).resolve().parent.parent.parent.parent.parent / "etf_system"
```
这是有意的——它需要跨越 `data/` 再向上找到 `etf_system` 目录（可能是外部项目）。代码中有 fallback 机制（L18-L19 两个候选），所以风险较低。

### 2e. `materials.py` 和 `material_watchdog.py` 5层 .parent (LOW)

**位置**: 
- `src/etf_platform/analysis/deep_sub/materials.py` L95
- `src/etf_platform/analysis/material_watchdog.py` L27

这些也是有意为之，指向 `config/` 或项目根目录。

---

## 3. Bare Except 残留 (Severity: MEDIUM)

### 真正的裸 except (必须修复)

| 文件 | 行号 | 代码 | 风险评估 |
|------|------|------|---------|
| `etf_daily_patrol_wrapper.py` | 49 | `except: return str(v)[:4]` | **高** — 数据格式化中的裸except可能吞掉关键错误 |

### `except Exception` 清单 (共 48 处)

以下文件包含 `except Exception as e:` 或 `except Exception:`，大部分是合理的防御性编程：

| 文件 | 行数 | 说明 |
|------|------|------|
| `src/etf_platform/pipeline.py` | 320 | Pipeline 主流程异常捕获 |
| `src/etf_platform/scripts/dynamic_weights.py` | 14, 100 | 权重计算 |
| `src/etf_platform/data/valuation.py` | 88 | 估值数据获取 |
| `src/etf_platform/data/price_cache.py` | 106, 126 | 缓存读写 |
| `src/etf_platform/data/news.py` | 48 | 新闻抓取 |
| `src/etf_platform/data/akshare_source.py` | 43, 72, 89 | AKShare API |
| `src/etf_platform/data/live_price_bridge.py` | 137, 196 | 实时价格桥接 |
| `src/etf_platform/layers/l14_stoic_risk.py` | 20 | 模块级异常 |
| `src/etf_platform/layers/l18_var_risk.py` | 27 | 模块级异常 |
| `src/etf_platform/analysis/holdings_fetcher.py` | 64 | 持仓数据 |
| `src/etf_platform/analysis/l9_signals_enhanced.py` | 27, 224 | 信号增强 |
| `src/etf_platform/analysis/macro_climate.py` | 33, 46 | 宏观气候 |
| `src/etf_platform/analysis/layer_live_adjustments.py` | 99, 115, 131 | 实时调整 |
| `src/etf_platform/analysis/material_live.py` | 68, 96 | 实时材料 |
| `src/etf_platform/analysis/realtime_data.py` | 67, 209 | 实时数据 |
| `src/etf_platform/analysis/sector_flow_bridge.py` | 87 | 资金流桥接 |
| `src/etf_platform/decision/screener.py` | 256, 404, 556 | 筛选器 |
| `src/etf_platform/optimize/backtest.py` | 39, 90 | 回测 |
| `news_to_etf_bridge.py` | 353 | 桥接脚本 |
| `tests/test_optimizations.py` | 196 | 测试 |
| `scripts/_archived/` | 多处 | 已归档脚本 (不影响) |

**注意**: 大部分 `except Exception as e:` 是合理的（记录日志后降级），但以下值得审查：
- `pipeline.py:320` — 裸 `except Exception:` (无 as e)，无法记录错误详情
- `eastmoney.py` 中的多个 `except Exception` — 如果网络请求失败应区分 HTTPError vs 解析错误

---

## 4. 集成缺失与风险 (Severity: HIGH)

### 4a. `meta_predictor.py` 的 `get_ensemble_picks` 调用方式错误 (CRITICAL)

**问题**: `meta_predictor.py` L127 注册了:
```python
PredictorSource("tournament", "etf_platform.decision.strategy_tournament", "get_ensemble_picks", weight=0.25)
```

但 `get_ensemble_picks` 不是模块级函数，而是 `StrategyTournament` **类的方法** (L601):
```python
class StrategyTournament:
    def get_ensemble_picks(self, results, regime="normal", top_n=3):
        ...
```

**结果**: `PredictorSource.probe()` 会执行:
```python
mod = importlib.import_module("etf_platform.decision.strategy_tournament")
fn = getattr(mod, "get_ensemble_picks", None)  # None! 方法不在模块命名空间
self.available = False  # 标记为不可用
```

**影响**: 策略锦标赛预测源在 meta_predictor 中**始终不可用**。

**修复方案**:
1. 在 `strategy_tournament.py` 中添加模块级 wrapper:
```python
def get_ensemble_picks(regime="normal"):
    """Module-level wrapper for MetaPredictor compatibility."""
    t = StrategyTournament()
    # ... run strategies and return ensemble
```
2. 或者修改 `meta_predictor.py` 的 `_tournament_predict()` 函数来正确实例化类。

### 4b. 循环导入风险

检测到以下潜在的循环导入链:

```
regime_transition.py L289:
  from etf_platform.decision.strategy_tournament import (REGIME_WEIGHT_PRIORS, DEFAULT_WEIGHTS)

strategy_tournament.py → pipeline.py → config_loader.py → (ok)

meta_predictor.py L86:
  from etf_platform.decision.two_week_picker import pick_top3
two_week_picker.py L37-38:
  from etf_platform.config_loader import load_etfs
  from etf_platform.data.kline import get_trend
```

目前这些导入都是延迟的（函数内部import），所以**运行时不会死锁**，但静态分析工具会报红。

### 4c. `_demand_adapter.py` 孤立模块

**位置**: `src/etf_platform/_demand_adapter.py`

```python
from etf_platform.analysis.demand import add_demand_layers as _add_demand
def add_demand_layers(penetration_result):
    ...
```

这个模块从未被任何地方 import（搜索 `import.*_demand_adapter` 无结果）。它是一个适配器/包装器，可能是遗留代码。

### 4d. `__init__.py` 不完整

| 包 | `__init__.py` 导出内容 | 缺失 |
|----|----------------------|------|
| `src/etf_platform/decision/__init__.py` | screener, strategy_tournament | ml_predictor, two_week_picker, meta_predictor 未导出 |
| `src/etf_platform/layers/` | **无 __init__.py** | 11个 layer 模块无包级导出 |
| `src/etf_platform/analysis/__init__.py` | **不存在** | 大量分析模块无包级入口 |

---

## 5. 未使用代码 (Severity: LOW)

### `_archived/` (项目根目录)
- 10 个文件，全部为 `.py`、`.json`、`.md` 归档文件
- 确认：无任何 import 引用

### `scripts/_archived/`
- 20 个 `.py` 和 `.ps1` 文件
- 包括 `system_audit.py`, `diagnostic_scan.py`, `baseline_scores.py` 等诊断脚本
- 确认：无任何 import 引用

### `scripts/dead_scripts/`
- 目录不存在

### 孤立模块
- `src/etf_platform/_demand_adapter.py` — 从未被 import
- `src/etf_platform/enhance/l8_realtime.py` — 仅被 `l9_news.py` 间接引用? (需进一步确认)
- `src/etf_platform/enhance/l9_news.py` — 同上

---

## 6. 综合问题清单 (按严重程度排序)

### 🔴 CRITICAL
1. **[集成] `meta_predictor.py` 注册了不存在的函数** — `get_ensemble_picks` 是类方法非模块函数，导致 tournament 预测源始终不可用
2. **[路径] `event_nlp.py` L1001 回退缓存路径少一层 `.parent`** — 缓存失效时永远找不到旧缓存文件

### 🟠 HIGH
3. **[分数量纲] `two_week_picker.py` 输出 0-100 分，与所有 layer 的 1-10 分不兼容** — `meta_predictor.py` 的归一化逻辑未处理此差异
4. **[路径] `ml_predictor.py` L39 和 `two_week_picker.py` L34 的 BASE 路径少一层 `.parent`** — 模型/预测文件写入错误目录
5. **[集成] `decision/__init__.py` 未导出核心模块** — ml_predictor, two_week_picker, meta_predictor 均缺失

### 🟡 MEDIUM
6. **[Except] `pipeline.py` L320 裸 `except Exception:` 无变量绑定** — 无法记录错误详情
7. **[Except] `etf_daily_patrol_wrapper.py` L49 裸 `except:`** — 唯一真正的裸 except
8. **[集成] `layers/` 目录缺少 `__init__.py`** — 11个 layer 模块无法通过包导入
9. **[集成] `analysis/` 目录缺少 `__init__.py`**

### 🟢 LOW
10. **[未使用] `_archived/` 和 `scripts/_archived/` 共 30 个文件从未被 import**
11. **[孤立] `_demand_adapter.py` 从未被 import**
12. **[路径] `eastmoney.py` 和 `materials.py` 使用 5 层 `.parent`** — 有意为之但有脆弱性

---

## 7. 修复优先级建议

| 优先级 | 操作 | 预计工作量 |
|--------|------|-----------|
| P0 | 修复 `event_nlp.py` L1001 路径 (加一个 `.parent`) | 1分钟 |
| P0 | 修复 `ml_predictor.py` L39 和 `two_week_picker.py` L34 (加一个 `.parent`) | 2分钟 |
| P0 | 在 `strategy_tournament.py` 添加 `get_ensemble_picks` 模块级 wrapper | 10分钟 |
| P1 | 统一分数体系：所有 layer 输出 0-100 或在 meta_predictor 中正确归一化 | 30分钟 |
| P1 | 补充 `decision/__init__.py` 和 `layers/__init__.py` | 10分钟 |
| P2 | 修复 `pipeline.py` L320 裸 except | 1分钟 |
| P2 | 清理 `_archived/` 目录 (确认可删除后 git rm) | 10分钟 |
