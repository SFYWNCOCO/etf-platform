# CC T8 / P1-C: 负相关层配置化降权回测门禁证据(no-difference)

> 生成时间: 2026-08-26 14:43:49  

## 背景

依据 `knowledge/composite_score_architecture_issue.md` 层-综合分相关表: L20_OptionVol(-0.266) / L1_ETF(-0.187) / L12_PoliticalRisk(-0.142) 负相关拖累排序。本门禁验证对这三层配置化降权(0.3/0.5/0.6)后, pipeline composite 加权路径选出的 top5 等权组合, 相对等权 baseline 是否劣化。

## 方法学(v2 口径)

- **池子(v2)**: 前 80 只数字 code ETF 逐只 `_fetch_kline(code, 500)` 筛查 K线根数≥405(≈81周), 不足剔除并打印剔除清单; 从达标者取前 50 只 `batch_full(live=False)` 穿透。

- **首轮未判定原因**: 首轮未做上市时长筛查, top5 含上市仅 59 周的 159263, 组合共同周 59<81, 未产出 PASS/FAIL 数字。

- **窗口门槛**: 组合共同周 ≥ 81 周, 不足如实报错退出非零。

- **持有口径**: 期初等权买入持有, 组合周净值 = 各成分首周归一化等权均值, 整段窗口三指标(总收益/年化夏普=周收益×√52/最大回撤)。

- **两路径**: baseline=weights None(纯等权 composite top5); treatment=加载 weights.yaml 加权(Σ(w·s)/Σw) composite top5。

## 两路径 top5(完全重合)

- baseline : 159691,510880,159326,511880,511010

- treatment: 159691,510880,159326,511880,511010

- 组合共同周: 102  |  总收益 +27.07%  |  夏普 1.225  |  最大回撤 -11.62%

## 成分周数明细

| code | weeks |
|---|---|

| 159326 | 102 |

| 159691 | 170 |

| 510880 | 170 |

| 511010 | 170 |

| 511880 | 170 |


## 判定

- **no-difference**: 等权与加权两路径 top5 完全重合, 三指标必然相同, 说明在 102-周共同窗口内该权重幅度(0.3/0.5/0.6)在排序边界无影响。

- **非 PASS**: 无法证明加权带来改善, 保守默认关闭 — 已把 config/weights.yaml 的 composite_layer_weights.enabled 改为 false (成功), 机制保留(行为关闭), 待有效幅度证据再启用。

## 结论

`verdict: no-difference — 两路径 top5 完全重合, 权重幅度无边界影响, 保守关闭 enabled=false`
