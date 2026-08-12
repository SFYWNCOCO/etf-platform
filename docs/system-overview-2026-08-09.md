# ETF 分析平台系统概况

> 生成时间：2026-08-09（基于实测 + skill v4.13.0）
> 路径：`D:/龙虾/.openclaw/etf-platform/`

---

## 1. 系统定位

**全A股行业ETF智能分析平台** — 覆盖 1071 只 ETF（实测 etfs.yaml），61 个细分行业。核心目标：每周推 2-3 只行业ETF、基于真实数据流、全 cron 自动化、推荐来源透明。

| 维度 | 值（实测） |
|------|-----------|
| ETF 总数 | 1071（config/etfs.yaml，嵌套结构 `{'etfs': {...}, '_meta': {...}}`） |
| 行业数 | 61 个 fine sector → FINE_TO_BROAD 映射 17 broad |
| 代码库 | src/etf_platform ~110 个模块，32,415 行 |
| 核心管道 | pipeline.py 745 行，36 层穿透评分 |
| 测试 | 19 文件 / 173 用例全过（PYTHONPATH=src 必设） |
| 最新 commit | caa1086（2026-08-09 死模块归档 50 个） |

---

## 2. 总体架构

```
                    ┌─────────────────────────────────────┐
  etfs.yaml(1071)   │          pipeline.py run_full()      │
  → Sina实时行情    │  36层穿透评分 (L1-L34)               │
  → live_price_     │  MapReduce: L1-L5并行(7任务/4线程)   │
    bridge          │  composite_score加权聚合             │
  → 行业动量        │  L30 MultiAgent辩论层(bear×1.3)      │
  → weekly_top3     └─────────────────────────────────────┘
         │                        ↑
         ▼                        │
  Top3推荐(买卖指令)      news_to_etf_bridge.py (L9信号)
         │                        ↑
         ▼                auto_sentiment.py ← 6源新闻抓取
  etf_daily_patrol_wrapper.py (cron 工作日8:00)
```

**生产消费链（真集成，08-09 审计确认）**：`pipeline.py → weekly_top3.py → etf_daily_patrol_wrapper.py(cron) + news_bridge_cron_wrapper.py(cron)`。只有这条链上的模块是活的。

---

## 3. 36层穿透评分（实测 512890）

`run_full('512890', live=False)` → score=5.91, layers=36, version=1.3.0-MAPREDUCE+DEBATE

| 层级 | 名称 | 实测分 | 说明 |
|------|------|--------|------|
| L1 | ETF基础/Controllability | 1.5 / 0.5 | 基础面 |
| L2 | Holdings | 9.0 | 持仓穿透 |
| L3 | Material | 9.0 | 物料/商品实时 |
| L4 | SupplyChain | 5.7 | 供应链 |
| L5 | Tech | 3.9 | 技术面 |
| L6 | Politics | 8.3 | 政策面 |
| L7 | Irreplaceable | 7.3 | 不可替代性 |
| L8 | CapitalFlow | 7.7 | 资金流（live 桥接） |
| L9 | Signals/News | 8.3 | 新闻信号（KB桥） |
| L10 | Demand | 6.8 | 需求 |
| L11 | SectorRisk | 5.1 | 行业风险 |
| L12 | PoliticalRisk | 2.9 | 政治风险 |
| L13 | MacroCycle | 7.5 | 宏观周期 |
| L14 | StoicRisk | 9.0 | 斯多葛风险 |
| L15 | StateSim | 6.9 | 状态相似 |
| L16 | LiveSignals | 6.0 | 实时信号 |
| L17 | Factor | 9.5 | 量化因子 |
| L18 | VaR | 6.6 | 风险价值 |
| L19 | FXChannel | 7.3 | 汇率通道 |
| L20 | OptionVol | 7.5 | 期权波动 |
| L21 | Behavior | 5.0 | 行为因子 |
| L22 | Pendulum | 3.4 | 周期钟摆 |
| L23 | Valuation/Microstructure | 7.7 / 4.2 | 估值+微观结构 |
| L24 | DipFlow/SystemDynamics | 5.0 / 6.9 | 折溢价+系统动力学 |
| L25 | LiquidityArb | 5.3 | 流动性套利 |
| L26 | VolRegime | 6.1 | 波动率制度 |
| L27 | FactorBeta | 5.6 | 因子β |
| L30 | MultiAgent | 7.9 | Bull/Bear辩论层 |
| L33 | RegimeFactor | 8.2 | 制度因子（get_regime() 真实 regime） |
| L34 | KBCatalyst | 5.0 | KB催化剂（无催化=5.0正常） |

注意：部分层在特定条件返回默认值属正常降级（如 L24_DipFlow 无溢价数据=5.0、L9_NewsEnhanced 无新闻=0）。

---

## 4. 数据源

| 数据源 | 用途 | 状态 |
|--------|------|------|
| Sina hq.sinajs.cn | 实时行情主力（586只，~3秒精度） | ✅ 稳定 |
| 东方财富 push2 API | 资金流/板块（秒级） | ✅ 主力 |
| akshare | 离线批量（估值/历史K线） | ⚠️ 网络不稳，必须 timeout 包裹 |
| Tencent qt.gtimg.cn | ~~估值字段~~ | ❌ 已禁用（字段不可靠） |
| 新闻6源 | sina/eastmoney/tonghuashun/360news/搜索管线 | ✅ 08-03 扩到 6 源 |

**金律**：所有外部数据必须 try-except + timeout + fallback（INDEX_PROXY / 缓存 / KB先验）；任何数据桥优先级读取必须检查"数据有意义"（total>0）否则降级。

---

## 5. 推荐引擎

### weekly_top3 v17.0（生产入口）
- **回测验证**：507 ETF × 400天 × 81周，夏普 **1.75**（原1.31），回撤 **-13.8%**（原-30.4%），手续费万2.5下年化+26.8%
- 流程：K线20日动量 → 大板块去重 → 沪深300趋势过滤动态仓位 → 新闻情绪自动刷新对冲 → 动量成熟度检测（防追高）
- 输出：买卖指令格式（非分析理由），用户偏好"只要3只、不要报价表格、过滤宽基"

### two_week_picker（2周预测）
- 6因子 Z-score：动量50%（trend 25%+risk_adj 25%）+ 弹性15% + 行为15% + 反转20%
- 锦标赛融合（5策略）+ regime 条件动态权重 + macro_overlay 叠加
- 预测写入 `data/two_week_predictions.jsonl`，每周回测验证命中率

### 宏观叠加 macro_overlay v2.0
- UIDF 四维宏观打分卡（通胀/利率/增长/地缘→仓位30%）
- CATALYSTS 催化剂字典（手动维护 expires）+ 12行业×4情景轮动矩阵 + 三层资产架构

---

## 6. 新闻管线（08-03 升级后）

```
fetch_news_sources.py (6源: sina/eastmoney/tonghuashun/360news/search_pipeline)
  → news_raw_sources.json (103条实测)
  → auto_sentiment.py (AI情绪)
  → news_to_etf_bridge.py --auto (看多558/看空214/中性284，实测)
  → data/news_etf_signals.json (722KB, 08-09 更新)
  → pipeline L9_Signals (±2.0)
```

- 动态词表 v2：三层动态词源（平台12 + 持仓ETF行业60 + 历史热点），共63词，每轮3核心+5动态
- 变化检测：prev/curr 快照对比 → NEW/RISING/DROPPING/CONTINUOUS

---

## 7. Cron 自动化（15个任务，ETF 相关核心 3 个）

| Job | 名称 | 调度 | 状态 |
|-----|------|------|------|
| d1febc893708 | ETF每日穿透巡检+Top3 | 工作日 8:00 | ✅ no_agent wrapper |
| da3a5c97555c | ETF新闻信号每日刷新 | 工作日 8:05 | ✅ no_agent wrapper |
| 6e878757cfc7 | 生产级健康巡检 | 每日 10:00 | ✅ |
| 其他12个 | 记忆管道/进化周期/脚本膨胀防护/学习循环等 | 每日/每周 | ✅ 与ETF系统互补 |

**已修复的历史坑**：cron 引用不存在脚本（静默失败）→ 统一 wrapper + workdir 模式；`finance_search.py` 归档致 wrapper 市场概览静默降级 → 归档前必须 grep 活引用。

---

## 8. 数据产物（08-09 实时）

| 文件 | 大小 | 更新时间 | 用途 |
|------|------|---------|------|
| kline_trend_cache.json | 290KB | 08-09 20:37 | K线趋势缓存 |
| news_etf_signals.json | 722KB | 08-09 20:29 | 新闻→ETF信号 |
| recommendations_log.jsonl | 42KB | 08-09 20:29 | 推荐历史 |
| etf_valuation.json | 185KB | 08-09 20:20 | 估值 |
| news_sentiment.json | 2.8KB | 08-09 20:13 | 板块情绪（17 sectors） |
| policy_signals.json | 2.2KB | 08-09 20:13 | 政策信号 |
| news_raw_sources.json | 40KB | 08-09 20:12 | 原始新闻 |

---

## 9. 质量基线与纪律

**质量基线（07-19 审计 v2，评级 B+）**：bare except 0 / eval 0 / mutable default 0 / 硬编码密钥 0 / SQL拼接 0

**08-09 最新修复闭环**：
- finance_search.py 归档致 patrol wrapper 静默降级 → 已恢复
- news_to_etf_bridge KeyError 'direction' → 已修 + 专项回归测试（172→173）
- 死代码 50 模块归档（-6057 行）→ 保留 3 个误报活模块

**纪律铁律**：
1. 声称"已集成"前必须 grep 消费者（skill 曾大量假集成声明）
2. 声称"已验证"必须真实 import+运行确认
3. 归档前 grep 活引用（wrapper/cron 也算）
4. 外部 cron 写盘的 JSON 字段永远用 `.get()` 防御
5. docstring 必须与实际返回类型一致
6. 修复后必须补专项回归测试
7. 测试必须 `PYTHONPATH=src`（pytest.ini 未配 pythonpath）

---

## 10. 已知限制 / 待办

- **policy_fetcher playwright 版本不匹配**（08-06）：chromium_headless_shell-1200 vs 期望 -1234，cron 08:05 失败，未修
- **L9_NewsEnhanced / L9_SentimentWeight 无新闻时=0**：属降级正常，但输出可读性可优化
- **data_integrity.py 未自动集成 pipeline**：手动门禁，非自动
- **skill 文档与代码漂移**：skill 说 592 只 ETF，实际 1071（etfs.yaml 扩充后未同步文档）；层数 29→30→36 也在漂移 → 08-12 已治理：删除 `config/etfs_additions.yaml`（479 只全与 etfs.yaml 重叠），`etfs.yaml`=1071 为唯一事实源；`market_etfs_full.json`(1560)=行情抓取快照、非配置
- **宽基过滤硬性**：所有输出必须过滤宽基（38关键词+正则），用户明确要求
- **输出偏好**：不要报价表格、只要3只ETF、数据优先（先展示裸数据让用户选角度）

---

## 11. 快速上手命令

```bash
# 单只穿透
cd D:/龙虾/.openclaw/etf-platform && PYTHONPATH=src python -c "
from etf_platform.pipeline import run_full
r = run_full('512890', live=False)
print(f'score={r[\"score\"]:.2f} layers={len(r[\"layer_scores\"])}')"

# 周度推荐
python weekly_top3.py

# 新闻信号刷新
python news_to_etf_bridge.py --auto

# 全量测试
PYTHONPATH=src python -m pytest tests/ -v --tb=short

# 每日巡检
python etf_daily_patrol_wrapper.py
```
