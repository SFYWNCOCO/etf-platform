# CC 批次D修正指令 — S5 挂点改为选项3（展示层注解，零行为变更）

背景：你的回测已证明挂 screener 权重计算之前会劣化（夏普 1.53→1.06），违反蓝图合入门禁。选定选项3。

## 修正内容
1. src/etf_platform/pipeline.py：percentile_calibrate 改为**纯函数**——不再原地改 results，返回新列表，每个 result 增加键 `composite_percentile`（该批内最终 score 的横截面百分位 0~100）与 `layer_scores_raw`(保留原层分)；**不改 score/composite_score/layer_scores 的任何既有值**。
2. src/etf_platform/decision/screener.py：挂点移到批量结果**汇总报告/返回之后**的注解位置——调用纯函数拿注解列表并 merge 回 results（只加 composite_percentile 字段）；确保权重计算、死层检测读到的仍是原始 layer_scores。
3. weekly_top3.py / wrapper 的 kb_reasons 部分保持不变（那部分没问题）。
4. tests/test_percentile_calibration.py（本批新增文件允许改）：断言改为——
   - 输出对象的 score/composite_score/layer_scores 与输入完全相等（零行为变更）
   - 新增 composite_percentile 键且单调序保持
   - n=1 时 composite_percentile=50 或原分等确定性行为
   - KB 两测试保留

## 验收
1. PYTHONPATH=src python -m pytest tests/test_percentile_calibration.py tests/test_screener.py tests/test_pipeline.py -q 全过
2. 快速复跑你之前的等权+screener 对比脚本：ON 与 OFF 的选股结果必须完全一致（top5 重合 5/5、收益/夏普数字相同），仅多 composite_percentile 字段——给出对比表证明"零劣化"
3. 全量回归 PYTHONPATH=src python -m pytest tests/ -q 记录 passed 数
输出改动清单+对比表。
