# ETF 分析系统 BUG 与优化清单

> **审计日期**: 2026-07-15
> **审计范围**: etf-platform/src/etf_platform 核心代码
> **测试状态**: 165 passed / 68.67s
> **数据来源**: 静态代码分析, 无虚构发现

---

## 1. 实际 BUG

### BUG-1: engine.py 三个函数缺少 return (HIGH)

| 属性 | 内容 |
|------|------|
| 文件 | `src/etf_platform/engine.py` |
| 行号 | L74, L105, L133 |
| 问题 | `build_portfolio()`, `quick_report()`, `analyze_etf()` 计算完结果后没有 `return`, 函数返回 `None` |
| 影响 | 当前无模块引用 engine.py, 实际无影响; 但若未来被集成会直接崩溃 |
| 修复 | 在三个函数末尾添加 `return result` / `return advice` / `return "\n".join(lines)` |
| 验证 | `python -m py_compile engine.py` 通过, 运行函数返回非 None |

### BUG-2: engine.py 字段拼写错误 (MEDIUM)

| 属性 | 内容 |
|------|------|
| 文件 | `src/etf_platform/engine.py` |
| 行号 | L58 |
| 问题 | `result.rationale` 写成了 `result.rale` (缺少 'n') |
| 影响 | 运行时 AttributeError, 但当前无引用 |
| 修复 | `result.rationale = ...` |

### BUG-3: two_week_picker.py TypeError 分支存在 IndexError 风险 (HIGH)

| 属性 | 内容 |
|------|------|
| 文件 | `src/etf_platform/decision/two_week_picker.py` |
| 行号 | L215-L219 |
| 问题 | 当 `batch_full()` 不支持 `codes` 参数触发 TypeError 时, 回退到列表推导式生成 60 个结果; 但下一行 `pipe_results = [pipe_results[0]]` 在 `pipe_results` 为空时会抛出 IndexError |
| 影响 | 在非交易时段或候选池为空时, `pick_top3()` 直接崩溃 |
| 修复 | 改为 `pipe_results = [pipe_results[0]] if pipe_results else []` |
| 代码 |
```python
pipe_results = [predict(code, profile) for code in codes[:60]]
pipe_results = [pipe_results[0]] if pipe_results and isinstance(pipe_results[0], dict) else pipe_results
``` |

### BUG-4: backtest.py 日期字符串比较 (MEDIUM)

| 属性 | 内容 |
|------|------|
| 文件 | `src/etf_platform/optimize/backtest.py` |
| 行号 | L117 |
| 问题 | `if recs[0]["date"] > event["d"]:` — 两个都是字符串, 依赖 ISO 格式 `YYYY-MM-DD` 的字典序恰好等于时间序。如果某数据源返回 `YYYY/MM/DD` 会出错 |
| 影响 | 日期格式不一致时, 过滤逻辑错误, 可能误跳过或误保留事件 |
| 修复 | 统一转换为 `datetime.date` 比较:
```python
from datetime import date
first_date = date.fromisoformat(str(recs[0]["date"]).replace("/", "-"))
event_date = date.fromisoformat(str(event["d"]))
if first_date > event_date:
    continue
``` |

### BUG-5: backtest.py pre/post 价格查找逻辑有缺陷 (MEDIUM)

| 属性 | 内容 |
|------|------|
| 文件 | `src/etf_platform/optimize/backtest.py` |
| 行号 | L121-L130 |
| 问题 | `pre` 取事件日前最后一个 close, 但循环覆盖到了事件日当天; `post` 取事件日当天或之后第一个 close, 但 `window_days` 参数名不副实 —— 实际用的是事件日当天而非 N 天后 |
| 影响 | 事件日当天的价格已部分反映事件, 会导致回测收益被低估; `window_days` 参数无效 |
| 修复 | 改为滚动窗口:
```python
# Pre-event: window_days 天前
pre_idx = next((i for i, r in enumerate(recs) if r["date"] >= event["d"]), None)
if pre_idx is None or pre_idx < window_days:
    continue
pre = recs[pre_idx - window_days]["close"]
# Post-event: window_days 天后
post_idx = pre_idx + window_days
if post_idx >= len(recs):
    continue
post = recs[post_idx]["close"]
``` |

### BUG-6: l18_var_risk.py 摘要函数阈值错误 (MEDIUM)

| 属性 | 内容 |
|------|------|
| 文件 | `src/etf_platform/layers/l18_var_risk.py` |
| 行号 | L286-L293 |
| 问题 | `get_var_summary()` 中 `vol = bench["annual_vol"] * 100` 已转百分比, 但阈值仍用 `0.20/0.30/0.40` 比较, 导致所有行业都被判为 "极高" |
| 影响 | 仅影响 `if __name__ == "__main__"` 的打印摘要, 不影响评分函数 |
| 修复 | 阈值改为 `20/30/40` |

### BUG-7: cli.py help 中 `archive` 命令重复 (LOW)

| 属性 | 内容 |
|------|------|
| 文件 | `src/etf_platform/cli.py` |
| 行号 | L176-L180 |
| 问题 | `etf archive [collect|list|show]` 的帮助文本出现两次, 且第二次描述变为 "Daily archive for research" |
| 影响 | 用户困惑, 但不影响功能 |
| 修复 | 删除 L179-L180 的重复帮助 |

---

## 2. 代码异味 / 可优化点

### OPT-1: pipeline.py L21 行为金融学代码重复 (MEDIUM)

| 属性 | 内容 |
|------|------|
| 文件 | `src/etf_platform/pipeline.py` |
| 行号 | L514-L615 (disposition/contrarian/attention jitter) |
| 问题 | 3 处 code-based jitter 代码几乎相同 (hash 计算重复 3 次), 与 `utils/hash_jitter.py` 重复 |
| 优化 | 统一调用 `utils.hash_jitter.code_jitter()` |
| 收益 | 减少 ~20 行重复代码, 避免未来修改不一致 |

### OPT-2: pipeline.py _apply_kb_signals 吞异常 (MEDIUM)

| 属性 | 内容 |
|------|------|
| 文件 | `src/etf_platform/pipeline.py` |
| 行号 | L314-L317 |
| 问题 | `except Exception:` 无任何限定, 会吞掉知识库信号模块的内部错误 |
| 优化 | 改为 `except (KeyError, ValueError, TypeError, AttributeError, ImportError)` 或至少 `exc_info=True` |
| 收益 | 更快定位 KB 信号失败原因 |

### OPT-3: holdings_fetcher.py 和 realtime_data.py 重复配置 logging (LOW)

| 属性 | 内容 |
|------|------|
| 文件 | `src/etf_platform/analysis/holdings_fetcher.py`, `src/etf_platform/analysis/realtime_data.py` |
| 行号 | L256, L258 |
| 问题 | 两个模块在 `if __name__ == "__main__"` 中设置 `logging.basicConfig(level=logging.DEBUG)`, 会覆盖全局日志级别 |
| 优化 | 移除或改为仅在未配置 handler 时设置 |

### OPT-4: except Exception 仍有 28 处可继续收敛 (LOW)

| 位置 | 数量 | 状态 |
|------|:--:|------|
| 数据层 (akshare_source/live_price_bridge/valuation/price_cache) | 8 | 网络边界, 合理保留 |
| 分析层 (sector_flow_bridge/layer_live_adjustments/macro_climate/...) | 10 | 部分可细化 |
| 决策层 (screener/two_week_picker/select/optimizer/risk_manager) | 6 | 回退逻辑, 基本合理 |
| 因子层 (l14/l18/l12/l17/l19/l20/l22) | 4 | 配置加载回退, 合理 |

**建议**: 对分析层的 10 处 `except Exception` 逐步改为更具体异常类型, 提升可观测性。

### OPT-5: scripts/ 目录膨胀 (MEDIUM)

| 属性 | 内容 |
|------|------|
| 路径 | `src/etf_platform/scripts/` |
| 数量 | 35+ 文件 |
| 问题 | round2/round3/round4 系列大量重复, 多个 `final_report_*.py`, `step*.py`, `check*.py` 为一次性脚本 |
| 优化 | 将非核心脚本归档到 `scripts/_archived/` 或删除, 只保留 `code_audit.py`, `dynamic_weights.py`, `data_consistency_audit.py` 等日常运行脚本 |

### OPT-6: materials_data.py 1692 行字典 (MEDIUM)

| 属性 | 内容 |
|------|------|
| 文件 | `src/etf_platform/analysis/deep_sub/materials_data.py` |
| 行数 | ~1692 |
| 问题 | 巨大的静态字典, 与配置外部化原则冲突 |
| 优化 | 迁移到 `config/materials.yaml` + `lru_cache` 加载 |

### OPT-7: 双轨架构 engine.py vs pipeline.py (HIGH)

| 属性 | 内容 |
|------|------|
| 问题 | engine.py 独立 v2.0 引擎 (133 行) 与 pipeline.py (613 行) 功能重叠, 但未被引用 |
| 优化 | 决策: (A) 修复 engine.py 并替代 pipeline.py; (B) 废弃 engine.py; (C) 合并两者。推荐 B 或 C |
| 收益 | 消除维护两份代码的成本 |

### OPT-8: live_price_bridge.py 代码映射硬编码 (LOW)

| 属性 | 内容 |
|------|------|
| 文件 | `src/etf_platform/data/live_price_bridge.py` |
| 行号 | L44-L48, L56-L58 |
| 问题 | ETF 市场判断硬编码 (`159`→`sz`, 其他→`sh`), 不覆盖 560/58x 等沪市代码 |
| 优化 | 从 etfs.yaml 的 `market` 字段读取, 或在 etfs.yaml 中维护 `sina_symbol` |

### OPT-9: two_week_picker.py QVIX 异常静默 (MEDIUM)

| 属性 | 内容 |
|------|------|
| 文件 | `src/etf_platform/decision/two_week_picker.py` |
| 行号 | L185-L186 |
| 问题 | `except Exception: pass` 完全静默, 如果 QVIX 模块损坏无法感知 |
| 优化 | 改为 `logger.warning("QVIX failed: %s", e)` |

### OPT-10: 测试覆盖率不足 40% (MEDIUM)

| 未覆盖模块 | 建议测试数 |
|-----------|:--:|
| `engine.py` | 修复后再决定是否测试 |
| `optimize/decision.py` | 3 |
| `decision/risk_manager.py` | 已有 test_risk_manager.py, 需扩展 |
| `decision/optimizer.py` | 4 |
| `analysis/macro_climate.py` | 3 |
| `layers/l17_quantitative_factor.py` | 3 |
| `layers/l12_macro_cycle.py` | 3 |
| `data/live_price_bridge.py` | mock requests, 3 |
| `decision/two_week_picker.py` | 4 |

---

## 3. 性能优化

### PERF-1: pipeline.py 21+ 层串行计算

| 属性 | 内容 |
|------|------|
| 文件 | `src/etf_platform/pipeline.py` |
| 问题 | 单只 ETF 的 21+ 层因子串行计算, 部分层 (L12/L13/L22/L23) 依赖 get_trend 网络请求 |
| 优化 | 对无依赖的层并行化; 已使用 ThreadPoolExecutor 于 batch_full, 但单只 run_full 仍可优化 |
| 收益 | 单只分析耗时预计减少 30-40% |

### PERF-2: live_price_bridge.py 全量拉取 500+ ETF

| 属性 | 内容 |
|------|------|
| 文件 | `src/etf_platform/data/live_price_bridge.py` |
| 问题 | `fetch_live_prices()` 默认拉取全部 ETF, 每次 10-12 批网络请求 |
| 优化 | 增加结果缓存 TTL (当前无缓存); 按需拉取 |
| 收益 | 减少重复请求, 降低被 Sina 限流风险 |

### PERF-3: backtest.py 无缓存的历史数据获取

| 属性 | 内容 |
|------|------|
| 文件 | `src/etf_platform/optimize/backtest.py` |
| 问题 | `HISTORY_CACHE` 仅在内存中, 进程重启后失效; 且 `window_days` 不同会重复拉取同一 ETF 数据 |
| 优化 | 增加磁盘缓存, 同一 ETF 只拉取一次 |
| 收益 | 滚动回测 4 个 window 时减少 75% 网络请求 |

---

## 4. 修复优先级

| 优先级 | 项 | 预计工作量 |
|:--:|------|:--:|
| **P0** | BUG-1 engine.py 三个 return | 15min |
| **P0** | BUG-2 engine.py 字段拼写 | 5min |
| **P0** | BUG-3 two_week_picker IndexError | 15min |
| P1 | BUG-4 backtest 日期字符串比较 | 30min |
| P1 | BUG-5 backtest window_days 不生效 | 1h |
| P1 | OPT-7 双轨架构决策 | 2h |
| P1 | OPT-9 QVIX 异常静默 | 15min |
| P2 | BUG-6 l18_var_summary 阈值 | 15min |
| P2 | BUG-7 cli.py help 重复 | 5min |
| P2 | OPT-1 L21 jitter 去重 | 30min |
| P2 | OPT-2 KB 异常细化 | 30min |
| P2 | PERF-3 backtest 磁盘缓存 | 1h |
| P3 | OPT-5 scripts 归档 | 2h |
| P3 | OPT-6 materials_data 外部化 | 4h |
| P3 | OPT-10 补测试 | 20h |

---

**审计人**: AI Agent (DeepSeek-V4-Pro)
**生成时间**: 2026-07-15
**更新时间**: 2026-07-15 (v2.0 深度代码审查)

---

## 5. 深度代码审查 — 新增发现 (v2.0)

### BUG-8: l14_stoic_risk.py logger 未定义 (CRITICAL)

| 属性 | 内容 |
|------|------|
| 文件 | `src/etf_platform/layers/l14_stoic_risk.py` |
| 行号 | L20-23 |
| 问题 | `except Exception as e:` 块中调用 `logger.warning(...)`, 但模块顶部**从未导入 logging 或定义 logger** |
| 影响 | 一旦 `load_risk()` 配置加载失败, `logger` 未定义会抛出 `NameError: name 'logger' is not defined`, 导致整个 l14 模块导入崩溃, 连锁影响 pipeline.py |
| 严重度 | **CRITICAL** — 配置文件缺失时系统直接不可用 |
| 修复 | 在文件顶部添加 `import logging; logger = logging.getLogger(__name__)` |
| 代码 |
```python
# 文件顶部添加:
import logging
logger = logging.getLogger(__name__)

# L14-23 改为:
try:
    from ..config_loader import load_risk
    _risk_cfg = load_risk()
    _STOIC_CONTROLLABILITY_WEIGHT = float(_risk_cfg.get("stoic_controllability_weight", 0.6))
    _STOIC_TAIL_RISK_WEIGHT = float(_risk_cfg.get("stoic_tail_risk_weight", 0.4))
except Exception as e:
    logger.warning("[l14_stoic] load_risk_config failed: %s", e)
    _STOIC_CONTROLLABILITY_WEIGHT = 0.6
    _STOIC_TAIL_RISK_WEIGHT = 0.4
``` |

### BUG-9: layer_live_adjustments.py sector momentum 不按 sector 过滤 (HIGH)

| 属性 | 内容 |
|------|------|
| 文件 | `src/etf_platform/analysis/layer_live_adjustments.py` |
| 行号 | L120-133 |
| 问题 | `_get_sector_momentum(sector)` 接收 sector 参数, 但 `ak.stock_board_industry_index_ths()` 返回所有行业指数, 代码直接取 `df["收盘价"].tail(21)` **没有按 sector 过滤** |
| 影响 | 所有 sector 得到相同的 momentum 值 (最后一个行业指数的 20 日动量), L5_Tech 调整完全错误 |
| 严重度 | **HIGH** — L5 技术层评分基于错误数据 |
| 修复 | 按 sector 名称过滤 DataFrame:
```python
def _get_sector_momentum(sector: str) -> float:
    try:
        import akshare as ak
        df = ak.stock_board_industry_index_ths()
        if df is None or len(df) == 0:
            return 0.0
        # 按 sector 名称过滤
        sector_col = "行业" if "行业" in df.columns else df.columns[0]
        mask = df[sector_col].astype(str).str.contains(sector, na=False)
        sector_df = df[mask]
        if len(sector_df) < 21:
            return 0.0
        closes = sector_df["收盘价"].tail(21).astype(float)
        pct = (closes.iloc[-1] / closes.iloc[0] - 1) * 100
        signal = max(-1.0, min(1.0, pct / 15.0))
        return round(signal, 3)
    except Exception as e:
        logger.warning("[layer_live] sector momentum failed for %s: %s", sector, e)
        return 0.0
``` |

### BUG-10: CVaR 协方差矩阵伪造 (HIGH)

| 属性 | 内容 |
|------|------|
| 文件 | `src/etf_platform/optimize/portfolio.py` |
| 行号 | L96-101 |
| 问题 | CVaR 优化的协方差矩阵用评分方差构造, 所有资产间相关性固定为 0.5:
```python
scores_val = [max(s["score"], 0.01) for s in candidates]
mean_s = sum(scores_val) / n
var_s = sum((s - mean_s)**2 for s in scores_val) / max(n-1, 1)
cov = [[var_s if i == j else var_s * 0.5 for j in range(n)] for i in range(n)]
```
1. `scores_val` 用 ETF 评分 (0-10 范围) 作为"收益代理" — CVaR 的 means 应该是预期收益率 (如 0.05=5%), 不是综合评分
2. 协方差矩阵所有非对角线元素 = `var_s * 0.5`, 即所有资产间相关性恒为 0.5 |
| 影响 | CVaR 优化结果毫无金融意义, 产出的权重与 softmax 方法差异不大, 但给用户虚假的"鲁棒优化"印象 |
| 严重度 | **HIGH** — 金融逻辑错误 |
| 修复 | 要么 (A) 获取历史收益率数据计算真实协方差; 要么 (B) 在文档和 CLI 中明确标注此方法为 "score-based heuristic, not true CVaR" |

### BUG-11: student_t_cvar 不是真正的 Student-t CVaR (MEDIUM)

| 属性 | 内容 |
|------|------|
| 文件 | `src/etf_platform/optimize/cvar_portfolio.py` |
| 行号 | L91-95 |
| 问题 | `student_t_cvar` 使用正态分布的分位数 (`PHI.inv_cdf`) 和 PDF (`PHI_PDF`), 只是乘了一个经验调整因子 `(1 + 4.0/(nu-2))` |
| 影响 | 不是真正的 Student-t CVaR。真正的 t 分布 CVaR 应使用 `scipy.stats.t.ppf()` 和 t 分布 PDF |
| 修复 | 使用 scipy:
```python
from scipy.stats import t as t_dist

def student_t_cvar(mu, sigma, nu=5, alpha=0.95):
    t_ppf = t_dist.ppf(alpha, df=nu)
    t_pdf = t_dist.pdf(t_ppf, df=nu)
    k = t_pdf * (nu + t_ppf**2) / ((1 - alpha) * (nu - 1))
    return mu - sigma * k
``` |

### BUG-12: select.py aggressive 模式 min_score 不生效 (MEDIUM)

| 属性 | 内容 |
|------|------|
| 文件 | `src/etf_platform/decision/select.py` |
| 行号 | L31 |
| 问题 | `if cfg["score_direction"] == "high" and base_score < cfg["min_score"]: continue` — 只有 `score_direction == "high"` 时才执行 min_score 过滤。aggressive 模式 (`score_direction="low"`, `min_score=20`) 的 min_score 永远不会生效 |
| 影响 | aggressive 模式不会过滤低分 ETF, 但配置中 min_score=20 暗示应该过滤 |
| 修复 | 改为通用过滤:
```python
if base_score < cfg["min_score"]:
    continue
``` |

### BUG-13: l17_quantitative_factor.py 全局代理污染 (MEDIUM)

| 属性 | 内容 |
|------|------|
| 文件 | `src/etf_platform/layers/l17_quantitative_factor.py` |
| 行号 | L16-19 |
| 问题 | 模块级别删除 `HTTP_PROXY`/`HTTPS_PROXY` 等环境变量:
```python
for key in ['HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy','ALL_PROXY']:
    if key in os.environ: del os.environ[key]
os.environ['NO_PROXY'] = '*'
```
每次 import 该模块都会清除全局代理设置, 影响整个进程中其他需要代理的模块 (如 akshare 网络请求) |
| 影响 | 如果用户在代理环境下运行, l17 的 import 会破坏其他模块的网络连接 |
| 修复 | 移除模块级副作用, 改为在具体网络请求函数中局部设置 `NO_PROXY` |

### BUG-14: 三处 code_jitter 实现不一致 (MEDIUM)

| 属性 | 内容 |
|------|------|
| 文件 | `l12_macro_cycle.py` L387-392, `l17_quantitative_factor.py` L595-599, `utils/hash_jitter.py` |
| 问题 | 三处不同的 jitter 实现: <br>- l12: `code_hash = sum(int(digits[i:i+2])...)`, multiplier=`0.06`, range=±0.30<br>- l17: 相同 hash, multiplier=`0.16`, range=±0.80<br>- l14: 已用 `from ..utils.hash_jitter import code_jitter` (正确) |
| 影响 | l12 和 l17 手动实现与 `hash_jitter.py` 重复, 未来修改 hash 算法时容易遗漏 |
| 修复 | l12 和 l17 都改为调用 `utils.hash_jitter.code_jitter()`, 传入不同 amplitude 参数 |

### BUG-15: risk_manager.py 加权 PnL 用入场价作权重 (LOW)

| 属性 | 内容 |
|------|------|
| 文件 | `src/etf_platform/decision/risk_manager.py` |
| 行号 | L143 |
| 问题 | `weight = entry * pos.get("shares", 1)` — 用入场价作为权重, 高价 ETF 在加权 PnL 中权重更大 |
| 影响 | 加权平均 PnL 偏向高价 ETF, 不反映真实组合表现 |
| 修复 | 应使用实际投入资金比例作权重, 或记录买入时的金额 |

---

## 6. v2.0 修复优先级 (合并)

| 优先级 | 项 | 预计工作量 |
|:--:|------|:--:|
| **P0** | BUG-8 l14_stoic_risk logger 未定义 | 5min |
| **P0** | BUG-1 engine.py 三个 return | 15min |
| **P0** | BUG-2 engine.py 字段拼写 | 5min |
| **P0** | BUG-3 two_week_picker IndexError | 15min |
| **P0** | BUG-9 layer_live sector momentum 不过滤 | 30min |
| P1 | BUG-10 CVaR 协方差伪造 | 4h |
| P1 | BUG-11 student_t_cvar 不正确 | 1h |
| P1 | BUG-4 backtest 日期字符串比较 | 30min |
| P1 | BUG-5 backtest window_days 不生效 | 1h |
| P1 | BUG-12 select.py min_score 不生效 | 5min |
| P1 | BUG-13 l17 全局代理污染 | 15min |
| P1 | BUG-14 三处 jitter 不一致 | 30min |
| P1 | OPT-7 双轨架构决策 | 2h |
| P1 | OPT-9 QVIX 异常静默 | 15min |
| P2 | BUG-6 l18_var_summary 阈值 | 15min |
| P2 | BUG-7 cli.py help 重复 | 5min |
| P2 | BUG-15 risk_manager 加权 PnL | 30min |
| P2 | OPT-1 L21 jitter 去重 | 30min |
| P2 | OPT-2 KB 异常细化 | 30min |
| P2 | PERF-3 backtest 磁盘缓存 | 1h |
| P3 | OPT-5 scripts 归档 | 2h |
| P3 | OPT-6 materials_data 外部化 | 4h |
| P3 | OPT-10 补测试 | 20h |

---

## 7. v2.0 总结

### 新增 BUG 统计

| 严重度 | v1.0 | v2.0 新增 | 合计 |
|:--:|:--:|:--:|:--:|
| CRITICAL | 0 | 1 (BUG-8) | 1 |
| HIGH | 2 | 2 (BUG-9, BUG-10) | 4 |
| MEDIUM | 3 | 4 (BUG-11~14) | 7 |
| LOW | 1 | 1 (BUG-15) | 2 |
| **合计** | 6 | 8 | **14** |

### 最严重问题 Top 3

1. **BUG-8 (CRITICAL)**: l14_stoic_risk.py logger 未定义 — 配置加载失败时整个 pipeline 崩溃
2. **BUG-9 (HIGH)**: layer_live_adjustments.py sector momentum 不按 sector 过滤 — L5 技术层评分全错
3. **BUG-10 (HIGH)**: CVaR 协方差矩阵伪造 — "鲁棒优化"是虚假宣传

### 架构层面建议

1. **code_jitter 统一**: 3 处实现 → 1 处 (`utils/hash_jitter.py`)
2. **CVaR 方法决策**: 要么实现真正的历史数据 CVaR, 要么在 UI 标注为 "启发式方法"
3. **l17 代理污染移除**: 模块级环境变量修改是反模式