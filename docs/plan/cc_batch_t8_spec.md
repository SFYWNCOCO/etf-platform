# CC 批次T8实施规格 — P1-C 负相关层配置化降权 + ≥81周回测门禁（劣化即回滚）

仓库根 = 当前工作目录。禁止改 tests/ 既有文件。⚠️ S5前车之鉴：只动 pipeline 分析层 composite，**禁止触碰 screener 权重/死层检测语义**；回测门禁不过则默认关闭机制并如实落盘证据。

## 依据
knowledge/composite_score_architecture_issue.md 层-综合分相关表(tool实测): L20_OptionVol -0.266 / L1_ETF -0.187 / L12_PoliticalRisk -0.142 负相关拖累排序。

## 改动1 — 新建 config/weights.yaml
```yaml
composite_layer_weights:
  enabled: true          # 回测门禁失败时改回 false(机制保留行为关闭)
  default: 1.0
  overrides:             # 权重=按负相关强度衰减, 依据上表
    L20_OptionVol: 0.3
    L1_ETF: 0.5
    L12_PoliticalRisk: 0.6
source_note: knowledge/composite_score_architecture_issue.md correlation table (2026-08-26)
```

## 改动2 — 加载器 + pipeline 接线
- 新建 src/etf_platform/utils/layer_weights.py：load_composite_layer_weights() 读 yaml（缺文件/enabled=false/字段异常 → 返回 None=纯等权原行为；loud 日志）
- src/etf_platform/pipeline.py 的 _compute_composite_score：weights 存在时改为加权平均 Σ(w·s)/Σw，否则保持现有等权——**默认数值行为仅在有 enabled:true 配置时改变**；EXCLUDE_KEYS 规则不变
- 不改 screener.py / two_week_picker / strategy_tournament

## 改动3 — 回测门禁脚本（tool-proven）
新建 _sandbox/p1_negcorr_backtest_gate.py：
- 池：前50个数字code（batch_full live=False 穿透），K线 datalen≥800 取共同交易日按周重采样 → **窗口≥81周**，不足则如实报错退出
- 两路径各取 pipeline composite top5 等权组合：baseline(weights=None) vs treatment(加载yaml加权)，三指标 总收益/年化夏普/最大回撤
- 门禁判据：treatment 夏普 ≥ baseline×0.9 且 最大回撤不深于 baseline×1.1 → PASS；写明判定
- 产物落盘 knowledge/：p1_negcorr_backtest_gate_20260826.json(全部数字+config快照) + p1_negcorr_backtest_gate_20260826.md(方法学/对比表/判定)
- **若 FAIL：把 config/weights.yaml 的 enabled 改回 false，md 记录'已回滚'，机制保留**

## 改动4 — calibration 重算（仅门禁 PASS 时）
- 读 decision/confidence_calibrator.py 找历史重建入口（如 build from historical outcomes）；PASS 则重算并落盘新 calibration.json（旧文件先备份 calibration.json.bak-p1 到 data/）；FAIL 或入口不存在则跳过并在报告说明

## 测试 — 新增 tests/test_layer_weights.py
- yaml 缺失→等权；enabled=false→None；加权平均数学正确性(构造两层手算)；EXCLUDE_KEYS 不参与；断言密度≥4

## 验收（自己跑通并报告数字）
1. pytest tests/test_layer_weights.py tests/test_pipeline.py -q 全过
2. 门禁脚本跑通，两产物落盘，报告 PASS/FAIL 与四组数字
3. 全量回归 pytest tests/ -q 记录 passed 数
输出：改动清单 + 门禁数字表 + 是否触发回滚。
