# ETF 分析平台架构文档

> 生成：2026-08-09 | 项目根：`D:/龙虾/.openclaw/etf-platform/` | 知识库：`D:/龙虾/.openclaw/knowledge/`

---

## 1. 系统定位

**全A股行业ETF智能分析平台** — 覆盖 1071 只 ETF、61 个细分行业（FINE_TO_BROAD 映射 17 broad）。
核心目标：每周推 2-3 只行业ETF、基于真实数据流、全 cron 自动化、推荐来源透明（知识库 k-code 可追溯）。

| 维度 | 值（实测） |
|------|-----------|
| ETF 总数 | 1071（config/etfs.yaml 嵌套结构 `{'etfs': {...}, '_meta': {...}}`） |
| 行业数 | 61 fine sector → 17 broad |
| 代码库 | src/etf_platform ~120 模块，~33K 行 |
| 核心管道 | pipeline.py 745 行，36 层穿透评分 |
| 测试 | 173 用例全过（`python -m pytest`，pythonpath 已配 pytest.ini） |
| KB 集成率 | 15.5%（64/413 k-code），KB注册表审计 0 假集成 |

---

## 2. 架构分层

```
┌─────────────────────────────────────────────────────────────┐
│                      输出层 (Output)                        │
│  weekly_top3.py / etf_daily_patrol_wrapper.py (cron)        │
│  买卖指令格式 · 宽基过滤 · 每日巡检日报                     │
├─────────────────────────────────────────────────────────────┤
│                      决策层 (Decision)                      │
│  decision/: screener / two_week_picker / position_allocator │
│  strategy_tournament / risk_manager / prediction_backtest   │
├─────────────────────────────────────────────────────────────┤
│                      评分层 (Scoring)                       │
│  pipeline.py run_full(): 36层穿透评分 L1-L34                │
│  layers/: l12-l34 (宏观/估值/微观结构/制度因子/KB催化剂)     │
│  composite_score 加权聚合 + L30 MultiAgent 辩论层            │
├─────────────────────────────────────────────────────────────┤
│                      分析层 (Analysis)                      │
│  macro_overlay(k104/105/127) · qvix_regime(k187)            │
│  hurst_regime(k190) · style_rotation(k295)                  │
│  cross_asset_correlation(k189) · performance_metrics(k169)  │
│  technical_indicators(k168) · sector_flow_bridge            │
│  news_signal_extractor · material_live · premium_cache      │
├─────────────────────────────────────────────────────────────┤
│                      数据层 (Data)                          │
│  config/etfs.yaml(1071) · data/kline.py(Sina K线)           │
│  data/live_price_bridge(Sina spot) · sector_flow_bridge     │
│  price_cache / kline_trend_cache / premium_cache            │
├─────────────────────────────────────────────────────────────┤
│                      知识库层 (KB)                          │
│  kb/registry.py: k-code 注册表 + 审计 (data/kb_registry.json)│
│  scripts/kb_integration_audit.py: 集成率审计                │
│  知识库源: D:/龙虾/.openclaw/knowledge/ (1254文件/413 k-code)│
└─────────────────────────────────────────────────────────────┘
```

**生产消费链（真集成，08-09 审计确认）**：
`pipeline.py → weekly_top3.py → etf_daily_patrol_wrapper.py(cron) + news_bridge_cron_wrapper.py(cron)`
只有这条链上的模块是活的。声称"已集成"前必须 grep 消费者。

---

## 3. 数据流

```
etfs.yaml(1071) ──► Sina hq.sinajs.cn 实时行情 (586只, ~3s) ──► price_cache.json (15:10 cron 刷新)
      │                    │
      ▼                    ▼
 config_loader      live_price_bridge (FINE_TO_BROAD 60→17)
      │                    │
      ▼                    ▼
 行业动量 ←──────── K线趋势 (Sina CN_MarketData, get_trend_batch)
      │                    │
      ▼                    ▼
 weekly_top3 (20日动量 → 大板块去重 → 沪深300趋势过滤 → 新闻对冲)
      │                    │
      ▼                    ▼
 Top3 推荐(买卖指令)  ◄── news_to_etf_bridge.py (L9信号, ±2.0)
      │                    ▲
      ▼                    │
 etf_daily_patrol_wrapper.py (cron 工作日8:00)
      │
      ▼
 飞书日报
```

**数据源优先级（08-10 精简）**：价格源 = Sina(主力实时) → akshare(兜底, 必须 timeout 包裹) → KB先验(降级fallback)。东方财富 push2 仅用于资金流/板块/估值等非价格数据（sector_flow_bridge / valuation），不再作为价格源——原 EastMoneySource 是死源（包装已清除的 etf_system/ETFDataFetcher），已删除。

**08-10 数据层修复**：
- 深市代码识别：`live_price_bridge._SZ_PREFIXES` 补 "167"（167301 实测走深圳市场接口），修复深市 K 线/行情断供
- kline 磁盘缓存 TTL 失效：`_save_disk_cache` 原把所有 `_ts` 重置为 now → 磁盘缓存永不过期。改为 `_trend_ts` 字典记录原始 fetch 时间，TTL 语义恢复（6h）
- kline 除零防护：`change`/`max_drawdown`/`r_list` 增加 close>0 前置检查，历史数据含 0 收盘价不再崩溃

**金律**：所有外部数据必须 try-except + timeout + fallback；任何数据桥优先级读取必须检查"数据有意义"（total>0）否则降级。

---

## 4. 36层穿透评分（pipeline.py）

`run_full('512890', live=False)` → score=5.91, layers=36, version=1.3.0-MAPREDUCE+DEBATE

| 层级 | 名称 | 来源KB | 说明 |
|------|------|--------|------|
| L1 | ETF基础/Controllability | k001-k012 | 基础面/可控制性 |
| L2 | Holdings | k007 | 持仓穿透 |
| L3 | Material | k088 | 物料/商品实时 |
| L4 | SupplyChain | k088 | 供应链 |
| L5 | Tech | k005 | 技术面 |
| L6 | Politics | k192 | 政策面 |
| L7 | Irreplaceable | - | 不可替代性 |
| L8 | CapitalFlow | k131 | 资金流（live 桥接） |
| L9 | Signals/News | k104 | 新闻信号（KB桥 ±2.0） |
| L10 | Demand | k023 | 需求 |
| L11 | SectorRisk | k003 | 行业风险 |
| L12 | PoliticalRisk | k192 | 政治风险 |
| L13 | MacroCycle | k001/k104 | 宏观周期 |
| L14 | StoicRisk | k004 | 斯多葛风险 |
| L15 | StateSim | k006 | 状态相似 |
| L16 | LiveSignals | k009 | 实时信号 |
| L17 | Factor | k132 | 量化因子 |
| L18 | VaR | k059 | 风险价值 |
| L19 | FXChannel | k019 | 汇率通道 |
| L20 | OptionVol | k020/k063 | 期权波动 |
| L21 | Behavior | k044 | 行为因子 |
| L22 | Pendulum | k021 | 周期钟摆 |
| L23 | Valuation/Microstructure | k178/k185 | 估值+微观结构 |
| L24 | DipFlow/SystemDynamics | k189 | 折溢价+系统动力学 |
| L25 | LiquidityArb | k226 | 流动性套利 |
| L26 | VolRegime | k063/k091 | 波动率制度 |
| L27 | FactorBeta | k042/k229 | 因子β |
| L30 | MultiAgent | k184 | Bull/Bear辩论层(bear×1.3) |
| L33 | RegimeFactor | k191/k196 | 制度因子（get_regime() 真实 regime） |
| L34 | KBCatalyst | k033/k090等13个 | KB催化剂（无催化=5.0正常） |

**新增层模板（Phase 3.6）**：模块文件 `layers/lXX_xxx.py` → 导出 `score_lXX_layer(...) -> {"score", "detail"}` → pipeline `_apply_xxx(scores, details, ...)` → `EXCLUDE_KEYS` 同步 → 推荐引擎 `SCORING_WEIGHTS` 加权重 → 验证 ast+ruff+pytest+run_full。

---

## 5. KB 注册表（kb/registry.py）

**目的**：终结"假集成"——代码中引用的每个 k-code 必须有登记记录。

```
class KBRegistry:
    register(code, title, source_file, consumer, mode, status)
    get(code) -> dict | None
    scan_codebase(src_root) -> {"referenced": {...}, "unregistered": [...]}
    audit(src_root) -> {total_registered, total_referenced, integrated, unregistered, fake_integration}
```

- 数据文件：`data/kb_registry.json`（自动生成/加载）
- 模式枚举：layer / fallback / signal / weight / data_source / research
- 审计脚本：`python scripts/kb_integration_audit.py`（集成率/假集成/死注册）

**集成模式选择**：
| 模式 | 适用 | 代码位置 |
|------|------|---------|
| 直接嵌入层 | 结构化理论规则矩阵 | `layers/lXX_xxx.py` |
| 降级fallback | API失败安全网 | `analysis/xxx_fallback.py` |
| 推荐引擎增强 | 综合评分权重补充 | `investment_recommendation.py` |
| 催化剂信号层 | KB产业文档→行业催化 | `layers/l34_kb_catalyst.py` |
| 共享数据缓存 | 跨层昂贵实时数据 | `analysis/premium_cache.py` |
| 独立分析模块 | 可独立计算的量化指标 | `analysis/xxx.py`（hurst/style/corr/perf） |

---

## 6. 推荐引擎

### weekly_top3 v17.0（生产入口）
- 回测验证：507 ETF × 400天 × 81周，夏普 1.75（原1.31），回撤 -13.8%（原-30.4%）
- 流程：K线20日动量 → 大板块去重 → 沪深300趋势过滤动态仓位 → 新闻情绪自动刷新对冲 → 动量成熟度检测
- **强看空永否决修复（08-10）**：强看空新闻原本无条件把板块整段排除（news_adj=-5.0*decay 已衰减仍被永久锁死）。现仅排除新鲜强看空（news_adjustment<=-2.5），旧闻按衰减减分即可；另修复 `news_signals` 参数被无条件覆盖为磁盘加载的 bug（注入失效）
- 输出：买卖指令格式，用户偏好"只要3只、不要报价表格、过滤宽基"

### two_week_picker（2周预测）
- 6因子 Z-score + 锦标赛融合（5策略）+ regime 条件动态权重 + macro_overlay 叠加
- **动态权重接入（08-10 修复）**：`_get_factor_weights(qvix_regime)` 此前是死代码（定义后从未被调用），composite 一直用静态 FACTORS weight → QVIX 切换恐惧市时红利/防御因子不增权。已接入 `_compute_scores_and_rank`，缺失 key 回退静态权重
- **候选池行业均衡（08-10 修复）**：`_build_candidate_pool` 原按 etfs.yaml 键序截断到 80 只（924 只 buyable 里截掉 91%），排在 yaml 尾部的行业整段饿死、池内 Z-score 失去对比基准。改为按行业轮询截断，保证各行业有代表
- 预测写入 `data/two_week_predictions.jsonl`，每周一由 `etf_prediction_cron.py` 回测 + 生成新预测（cron 0170f59b3e44）
- **回测方法论（08-10 修复）**：`evaluate_prediction` 用 K 线锚点法（预测日起 10 交易日后价格），不用当前动量
- **深市 K 线断供（08-10 修复）**：腾讯 K 线对深市 ETF 返回 `day` 字段、沪市返回 `qfqday`，只读 qfqday 导致深市样本被静默丢弃 → 回测系统性偏向沪市
- **log_prediction 幂等**：同一天同 profile 只保留一条，防 cron/手动重复触发污染回测样本
- **样本现状（08-10）**：独立预测日仅 5-6 个（n≈15-87），命中率 ~55% 接近随机、rank1 倒挂（胜率 7-20% vs rank3 86-100%）。**样本不足以调权**（auto_tune_weights 已归档 dead module），继续积累后再验证

### position_allocator（k170 增强）
- 7种方法：等权/分数加权/置信度加权/波动率倒数/混合/风险平价(risk_parity)/Black-Litterman(black_litterman)
- risk_parity: 权重∝1/volatility，风险贡献均衡；波动率差异>3倍时优于等权
- black_litterman: 市场均衡权重(等权) + 观点调整(score偏离均值, κ=0.3)
- **现金缓冲修复（08-10）**：持仓权重和被挤出缓冲时按比例收缩到 `CASH_BUFFER_MIN`，不再盲目超配/忽略现金
- **CVaR 符号修复（08-10）**：`cvar_portfolio` 梯度原为 `-μ - k·dσ`（风险偏好型，收敛到高波动资产）；已改为 `-μ + k·dσ`（风险厌恶，最小化尾部损失 CVaR(L)=-μ+σ·k）
- **screener break 修复（08-10）**：`screener.py` 内层循环错误缩进的一个无条件 `break` 在第 1 只 ETF 后就退出候选扫描，已删除
- **超限截断（08-10）**：`optimize/portfolio.allocate` 增加 `i >= max_positions` 边界，防止 amount=0 的溢出标的撑破持仓数

---

## 7. 新闻管线（08-03 升级后）

```
fetch_news_sources.py (6源: sina/eastmoney/tonghuashun/360news/search_pipeline)
  → news_raw_sources.json (103条实测)
  → auto_sentiment.py (AI情绪)
  → news_to_etf_bridge.py --auto (看多558/看空214/中性284)
  → data/news_etf_signals.json (722KB)
  → pipeline L9_Signals (±2.0)
```

动态词表 v2：三层动态词源（平台12 + 持仓ETF行业60 + 历史热点），共63词。

**08-10 新闻/政策修复**：
- 中文情绪恒 0：`extract_sentiment` 原 `split()` 切不开中文（无空格），整句成单 token 导致词表词永远匹配不上 → 改为子串匹配（专项测试 4 过）
- 政策误判：`policy_fetcher` 弱看多触发词中移除 "批复"/"通知"（监管类公文被自动当利好），仅保留 规划/方案/意见/行动方案/纲要
- auto=中性 矛盾：`news_to_etf_bridge` auto 中性不再覆盖 KB 方向，保留 KB note 追加 `[AUTO中性]` 标记（专项测试 11 过）

---

## 8. Cron 自动化（ETF 相关核心）

| Job | 名称 | 调度 | 状态 |
|-----|------|------|------|
| d1febc893708 | ETF每日穿透巡检+Top3 | 工作日 8:00 | ✅ no_agent wrapper |
| da3a5c97555c | ETF新闻信号每日刷新 | 工作日 8:05 | ✅ no_agent wrapper |
| a60a666331d9 | ETF价格缓存每日刷新 | 工作日 15:10 | ✅ no_agent wrapper |
| 0170f59b3e44 | ETF 2周预测+回测闭环 | 周一 8:45 | ✅ no_agent wrapper |
| 6e878757cfc7 | 生产级健康巡检 | 每日 10:00 | ✅ |

**price_cache 刷新坑**：`price_cache.refresh_all()` 逐只 get_price → EastMoney/Sina 挂了就回退 akshare（587 只 × ~25s ≈ 4h）不可行。真源用 `price_cache_refresh.py`（Sina 批量全量 ~13s）+ prev_close 兜底 + 有效条目 <50 保留旧缓存不覆盖。

**历史坑**：cron 引用不存在脚本（静默失败）→ 统一 wrapper + workdir 模式；归档文件前必须 grep 活引用（wrapper/cron 也算）。

---

## 9. 验证命令

```bash
# 全量测试（pythonpath 已配，无需 PYTHONPATH）
cd D:/龙虾/.openclaw/etf-platform && python -m pytest tests/ -v --tb=short

# 单只穿透
python -c "from etf_platform.pipeline import run_full; r=run_full('512890', live=False); print(f'score={r[\"score\"]:.2f} layers={len(r[\"layer_scores\"])}')"

# KB 集成率审计
python scripts/kb_integration_audit.py

# 周度推荐
python weekly_top3.py

# 新闻信号刷新
python news_to_etf_bridge.py --auto

# 每日巡检
python etf_daily_patrol_wrapper.py

# 新模块验证
python -c "from etf_platform.analysis.hurst_regime import hurst_dfa; print(hurst_dfa([i%7 for i in range(300)]))"
python -c "from etf_platform.analysis.style_rotation import recommend_style; print(recommend_style({}, {}))"
python -c "from etf_platform.analysis.performance_metrics import summary_metrics; print(summary_metrics([100,105,102,110]))"
python -c "from etf_platform.analysis.technical_indicators import rsi; print(rsi([100+i for i in range(30)]))"
```

---

## 10. 已知限制 / 待办

- ~~**policy_fetcher playwright 版本不匹配**（08-06）~~ 已解决：chromium 内置浏览器版本不匹配时回退 msedge channel；Playwright 整体不可用时回退 requests 直取 gov.cn 同源 `ZUIXINZHENGCE.json`（08-10 实测 20 条政策→8 行业，降级路径生效）
- **KB 集成率 15.5%**：还有 349 个 k-code 未消费，其中 ~48 个 ETF/投资相关（k062全天候/k132量化因子/k172定投/k178行业估值等）
- **data_integrity.py 未自动集成 pipeline**：手动门禁，非自动
- **skill 文档与代码漂移**：skill 说 592 只 ETF，实际 1071；层数 29→30→36 漂移
- **宽基过滤硬性**：所有输出必须过滤宽基（38关键词+正则），用户明确要求
- **输出偏好**：不要报价表格、只要3只ETF、数据优先（先展示裸数据让用户选角度）

---

## 11. 质量基线与纪律

**质量基线（07-19 审计 v2，评级 B+）**：bare except 0 / eval 0 / mutable default 0 / 硬编码密钥 0 / SQL拼接 0

**纪律铁律**：
1. 声称"已集成"前必须 grep 消费者（skill 曾大量假集成声明）
2. 声称"已验证"必须真实 import+运行确认
3. 归档前 grep 活引用（wrapper/cron 也算）
4. 外部 cron 写盘的 JSON 字段永远用 `.get()` 防御
5. docstring 必须与实际返回类型一致
6. 修复后必须补专项回归测试
7. 测试已配 pythonpath = src（pytest.ini）
8. 新增代码引用 k-code 必须注册（kb/registry.py），否则 audit 报假集成
