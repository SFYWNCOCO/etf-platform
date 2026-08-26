# CC 批次D实施规格 — 批次3: k-code 推荐理由注入 + S5 composite 百分位化

仓库根 = 当前工作目录 (etf-platform)。禁止改动 tests/ 下既有测试文件；只允许新增测试。
⚠️ 本批触碰评分语义，是最后一批：S5 完成后必须跑全量回测对比，夏普/回撤不显著劣化才允许保留。

## 改动1 — k-code 推荐理由注入（KB透明度，G3/C档增强）
背景：src/etf_platform/kb/registry.py 有 KBRegistry(k-code→title/source_file/consumer/mode)，数据 data/kb_registry.json。
- weekly_top3.py：新增轻量函数 `_kb_reasons_for_sector(mega_sector_or_sector)`：
  - 加载 KBRegistry（失败安全：任何异常返回 []）
  - 匹配策略：registry 条目的 title/consumer 中含板块关键词（如 半导体/医药/军工…与 SECTOR_TO_MEGA 键）或 mode=signal/layer 且 consumer 属于分析链 → 取至多 3 条 {kcode, title}
  - 简单关键词映射即可，不做语义检索；匹配不到返回 []
- rec 构建时附 `"kb_reasons": [...]`；recommendations_log 行同步写入。
- patrol wrapper 溯源行后追加 k-code 摘要（.get 容错，空则跳过）。
- 纯增量字段，不改推荐数值逻辑。

## 改动2 — S5 composite 百分位化（P1 区分度问题：44/50 只挤在[5.0,5.9]）
背景：pipeline.py _compute_composite_score 是逐 ETF 独立算术平均 → 中心极限压缩。方案=层内横截面百分位再加权（三方案中改动最小）。
- 在 pipeline.py 新增 `percentile_calibrate(results: list[dict]) -> list[dict]` 后处理函数：
  - 输入为同一批判 ETF 结果列表（每个含 layer_scores dict 与 composite/score）
  - 对每个参与 composite 的层键（沿用 _compute_composite_score 的 EXCLUDE_KEYS 排除规则）：把该层在本批内的原始分转为百分位 [0,100]（rank/(n-1)*100，n=1 时保持原分），再以百分位重算等权均值 → 写入 result["score"]/["composite_score"]；原始层分保留到 result["layer_scores_raw"]，layer_scores 原地替换为百分位值
  - 不改 run_full 单只路径的返回结构；只在批量入口调用
- 找到批量评分聚合点（screener 或 cli/pipeline 的 batch 入口，先 grep 消费者确认真集成链再挂钩，蓝图 t1 结论：仅 pipeline.py→weekly_top3.py 是主链——若 weekly_top3 不消费 pipeline 分数，则在 screener 批量入口挂并在报告说明实际挂点）
- 百分位化必须可关闭：模块级开关 PERCENTILE_CALIBRATION=True 或函数参数 enable

## 测试 — 新建 tests/test_percentile_calibration.py
- percentile_calibrate：同分层单调序保持（原始分高者百分位不低）；n=1 不变；EXCLUDE_KEYS 层不参与
- _kb_reasons_for_sector：注入 tmp registry_path 的 KBRegistry 或 monkeypatch → 命中返回 ≤3 条含 kcode/title；无匹配返回 []
- 断言密度 ≥2，RED 先行（先跑一次确认新测试因功能缺失而失败，再实现）

## 验收（你必须自己跑通并报告数字）
1. PYTHONPATH=src python -m pytest tests/test_percentile_calibration.py tests/test_pipeline.py tests/test_screener.py -q 全过
2. 全量回归 PYTHONPATH=src python -m pytest tests/ -q（记录 passed 数）
3. 回测对比：找到现有回测入口（optimize/walk_forward_bt.py 或 backtest 相关脚本/tests 中的调用方式），在百分位化 ON/OFF 两种状态下各跑一次可比回测，报告 夏普/最大回撤/总收益 对比表。若回测入口耗时 >20 分钟或依赖缺失无法运行，如实报告阻塞点与已尝试的命令，不得伪造数字。
最后输出改动文件清单、挂点位置说明、回测对比表。
