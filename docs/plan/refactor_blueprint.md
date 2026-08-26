# ETF 平台改造蓝图（refactor_blueprint）

> v2 2026-08-26 | scout(t2) | 依据: t1 只读侦察实证 | 迭代改本文件(git管版本)
> 架构铁律: weekly_top3 动量链=决策引擎(不动其选股逻辑)；36层 pipeline=分析层(只修展示/区分度/溯源)
> 纪律: 实施>50行交 Claude Code 执行+独立审查；最小改动从生产入口改造

---

## 〇、前提修正（比初稿更准）
material_live.py 已是真 akshare 期货(1h TTL)。"假实时"真缺口 = **deep 静态层**：
config/material_prices.yaml(mtime 07-01,46KB) → analysis/deep_sub/materials.py:96 插件加载 → material_bridge.py → L3/L4 打分，全程无 as_of/stale 守卫（k090 锂价教训机制根源）。

## 一、P0 材料真实源 + 全桥时效守卫（k090 闭环）

| 档 | 内容 | 文件 | 行数 |
|----|------|------|------|
| A | 仅输出标注: materials 层结果附 as_of 日期字段 | deep_sub/materials.py | ~40 |
| B | A + freshness 守卫: 加载时查 mtime/as_of>14d → 标 stale_prior 降权为"先验"，material_bridge 透传标记；全数据桥(live_price/kline/premium/news)补齐缺失 ts | 新增 utils/freshness.py(~60) + materials.py + material_bridge.py + 各桥散改 | ~180 |
| **C 完整** | B + 真实源刷新器: 新脚本 akshare futures_spot_price_previous(复用 material_live 抓取模式)+Sina 期货兜底 → 定期刷写 material_prices.yaml 并盖 as_of meta；run_with_timeout 包裹防拖慢 cron；挂入 15:10 price_cache_refresh 同批 cron | 新增 scripts/material_price_refresh.py(~150) + freshness.py + materials.py + material_bridge.py + price_cache_refresh.py 挂钩 | **~380** |

C档验收: material_prices.yaml 当日刷新且含 as_of；人工把 yaml mtime 回拨模拟过期 → 层输出显式 stale 标记且该物料不计现价信号；pytest 全过。

## 二、P1 composite 区分度修复（倾向层内百分位）

| 档 | 内容 | 文件 | 行数 |
|----|------|------|------|
| A | 只读增强: batch 结果附 percentile_rank 字段，不动分数 | pipeline.py format 段 | ~20 |
| B | 层内百分位: composite 改为各层横截面百分位再加权(消除 CLT 压缩)；单只 run_full 无横截面时退化原分 | pipeline.py composite 段 | ~60 |
| **C 完整** | B + 负相关层治理(L20 -0.27/L12/L1 按 knowledge 相关性表配置化降权进 weights.yaml) + 重跑 backtest/two_week 历史对比(夏普/回撤不显著劣化才合入) + calibration.json 重算 | pipeline.py + config/weights.yaml + optimize/backtest.py 复跑 + decision/confidence_calibrator.py | **~220** |

风险: 评分分布变化使历史校准失效 → P1 放最后独立批次，回测对比窗口 ≥81 周。遵守架构铁律: 只改分析层排序参考，不接入 weekly_top3 决策链。

## 三、P2 KB 集成率 + 推荐 k-code 透明度

| 档 | 内容 | 文件 | 行数 |
|----|------|------|------|
| A | 快赢: weekly_top3 --json 每只附所属板块 k-code 列表(kb_registry.json 静态映射) | weekly_top3.py | ~40 |
| B | A + patrol 日报每只推荐带理由链一行(动量值+过滤通过项+k-code+数据源名) | weekly_top3.py + etf_daily_patrol_wrapper.py(新旧字段兼容) | ~100 |
| **C 完整** | B + 集成率提升: kb_integration_audit.py 圈出高价值未集成 k-code(413 中 349 未集成, 现15.5%) → 按板块挑 top~30 注入 layer_sector_scores/l34_kb_catalyst 映射 → 集成率≥25%，audit 复跑留证 | scripts/kb_integration_audit.py + analysis/layer_sector_scores.py + layers/l34_kb_catalyst.py | **~300** |

C档验收: 任一推荐输出 grep 得到 k-code+行情源名；scripts/kb_integration_audit.py 集成率数字上升且 0 假集成。

## 四、实施顺序与执行方式

`P0(C档) → P2(A→B→C) → P1(C档最后)`，三个 CC 委托批次（P0/P2 可并行启动，P1 必须等前两批回归绿）。
每批: CC 执行(`claude -p --allowedTools Read,Write,Edit,Glob,Grep,Bash`) → 文件级产物验证 → pytest tests/ -q 全量 → 独立审查(CC reviewer 读 diff+实测) → 收据落任务 output。
全包 C 档总量 ≈900 行 / 约 1-1.5 周；若用户只要 P0-C + 其余 B ≈580 行 / 约 1 周。

## 五、全局风险点

1. weekly_top3 输出变更断下游解析 → P2-B 必须新旧字段兼容并同步 wrapper。
2. akshare 不稳 → 一切新外部调用 run_with_timeout 包裹(material_live.py 为范本)；Sina 兜底双源(push2被墙教训)。
3. cron 静默失败前科(finance_search 教训) → 新脚本挂 cron 前 cronjob list + grep import 双检。
4. 版本纪律: 迭代改原文件禁 _v2 副本；一次性探针脚本跑完归档。
5. P1 触碰校准/回测基线 → 独立批次+回测门禁，劣化即回滚。

## 六、总验收标准（硬性）

1. **cron 跑通**: 每周 patrol+周一预测链产出 2-3 只行业ETF(宽基已滤)，recommendations_log.jsonl 当周有记录。
2. **逐条可溯源**: 每只推荐 JSON 含 data_sources(K线截止日+源名+新闻对冲状态) 且 P2 后可 grep 到 k-code。
3. **无静态假实时**: 全链 fallback 带来源标注；mtime/as_of 超 TTL 数据显式 stale 标记不作现价(P0 后 material_prices.yaml 当日新鲜)；grep 无裸 except-pass 吞错。
4. **回归**: PYTHONPATH=src pytest tests/ -q 全过(基线173用例)；P1 另加回测夏普/回撤对比门禁。
5. **自动验收**: heartbeat 断言(当日有推荐+核心产物<24h)连续 5 个工作日绿灯。

## 七、下一步
captain 将本蓝图呈用户定档(A/B/C 或 P0-C+其余B) → 创建 P0/P2/P1 三个实施任务(建议 assignee=engineer 角色, CC 执行)。
