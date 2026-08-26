# CC 批次EVIDENCE规格 — S5 门禁否决补证：复跑"原方案"回测并落盘 tool-proven 证据

仓库根 = 当前工作目录。产物落 knowledge/，脚本留 _sandbox/。禁止改 src/ 与 tests/。

## 背景
reviewer 判定：cc_batch_d_fix.md 中"评分层百分位 夏普1.53→1.06"是[自报]级证据（原始产物未留存）。要求复跑原方案回测，把对比产物落盘升级为 tool-proven。
原方案定义：percentile_calibrate 以**原地替换 layer_scores** 方式挂在 screener 权重计算之前（现行代码已改为纯注解函数，不复现需在脚本内模拟旧行为）。

## 新建 _sandbox/s5_original_variant_evidence.py
参考同目录 compare_percentile_onoff.py 的骨架（batch_full 穿透 / _detect_dead_layers / _compute_auto_weights / _compute_composite / port_stats），但做以下差异：
1. 池子扩到 20 只（codes = 前20个数字code，与原始自报口径一致）
2. K线窗口拉长：_fetch_kline(code, 600)，取共同交易日后按周重采样（每周最后一个交易日），做每周前向持有对比——简化版：固定组合整段窗口收益/年化夏普/最大回撤三指标即可，不强求逐周换仓；方法学在报告里写清楚
3. 四条路径各算一次组合指标：
   - equal_weight_OFF：层分简单平均排序取top5
   - equal_weight_ON(old)：layer_scores 先横截面百分位化(rank/(n-1)*100, EXCLUDE_KEYS同_COMPOSITE_EXCLUDE_KEYS, n=1保50) 再简单平均
   - screener_OFF：原始layer_scores走 死层检测→自动权重→composite 排序top5
   - screener_ON(old)：**原地替换** layer_scores 为百分位后走同一链条（复现被否决的挂点语义）
4. 输出：
   - knowledge/s5_backtest_results_20260826.json：{config(pool/window/method), four_paths:{path:{codes_top5,total_return,annualized_sharpe,max_drawdown}}, degradation:{screener_sharpe_off, screener_sharpe_on, ratio}, generated_at}
   - knowledge/s5_percentile_backtest_evidence_20260826.md：方法学、四路径对比表、ON/OFF结论（screener路径劣化幅度 + equal_weight是否重合）、与[自报]数字的关系声明（方向性复现，不承诺数值一致——池子/窗口不同）、verdict
5. 数字必须来自真实运行打印，禁止硬编码；若网络失败重试一次后仍失败则如实退出非零

## 验收（自己跑通）
python _sandbox/s5_original_variant_evidence.py 跑通且两个产物文件生成；md 中 screener_ON 的夏普劣于 screener_OFF（方向复现）——若方向不复现也如实写入 md 并说明，不得修饰。
最后输出两产物路径 + 四路径数字表。
