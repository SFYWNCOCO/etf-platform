# CC T8门禁补跑指令 — 池子口径修正(剔除K线<81周标的)后复跑出真实数字

背景：首轮门禁因 top5 含新上市 ETF(159263, 59周)致共同窗口 59<81 未判定。
只改 _sandbox/p1_negcorr_backtest_gate.py，不改 src/ 与 config/。

## 修正
1. 池子筛选前移：候选池仍取数字code前80只，先逐只用 _fetch_kline(code, 500) 检查K线根数≥405(≈81周)，不足者剔除并打印剔除清单；从达标者取前50只进入 batch_full
2. 组合共同周仍须≥81 才判定；两路径逻辑/权重配置不变
3. 判定与落盘规则不变(PASS/FAIL/回滚规则照旧)；产物覆盖更新同名 json/md，md 中记录 v2 口径与首轮未判定原因

## 预案(如实执行)
- 若两路径 top5 依旧完全重合且三指标相同 → verdict 写 'no-difference'（非 PASS）：说明该权重幅度在排序边界无影响，并把 config/weights.yaml 的 enabled 改为 **false**（保守默认：机制保留、行为关闭、待有效幅度证据再启用），md 记录该决定
- 若有数字且 FAIL → enabled=false 回滚
- 若有数字且显著改善 → 保持 true

## 验收
脚本跑通、产物更新、报告最终 verdict 与四组数字、明确 enabled 最终状态。
