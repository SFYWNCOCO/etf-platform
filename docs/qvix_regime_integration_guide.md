# QVIX Regime 改进 — 集成指南

## 新增文件

| 文件 | 用途 |
|------|------|
| `src/etf_platform/analysis/qvix_regime_improvements.py` | QVIX多源校验 + 异常检测 |
| `src/etf_platform/decision/regime_transition_improvements.py` | 状态转换回测验证框架 |
| `docs/qvix_regime_audit.md` | 完整审计报告 |

---

## 方案1: QVIX多源校验（集成到 qvix_regime.py）

### 改动清单

**1. 在 `qvix_regime.py` 顶部导入新模块：**
```python
from etf_platform.analysis.qvix_regime_improvements import (
    QVIXValidator,
    SecondaryDataSource,
    classify_regime_with_quality,
)
```

**2. 添加模块级验证器实例：**
```python
_qvix_validator = QVIXValidator(history_size=50)
_secondary = SecondaryDataSource()
```

**3. 改造 `_get_qvix_data()` — 增加多源 fallback：**
```python
def _get_qvix_data():
    cached = _load_cache()
    if cached is not None and "50" in cached:
        return cached
    
    live = _fetch_qvix_with_timeout(timeout=8.0)
    if live is not None and "50" in live:
        # 验证数据质量
        try:
            q50 = _latest_qvix(live["50"])
            q500 = _latest_qvix(live["500"])
            quality = _qvix_validator.validate(q50, q500)
            if quality["recommendation"] == "reject":
                logger.warning("[qvix] live data rejected, trying secondary source")
                live = None
        except Exception:
            pass
    
    # 新增：live失败 → 尝试第二数据源
    if live is None:
        secondary_50 = _secondary.compute_realized_vol_proxy(["510050", "510300", "510500"])
        if secondary_50:
            logger.info("[qvix] using realized vol proxy as secondary source: %.1f", secondary_50)
            live = {"50": [{"date": datetime.now().isoformat(), "close": secondary_50}],
                    "500": live.get("500"), "updated": datetime.now().isoformat()}
    
    # ... existing cache fallback ...
```

**4. 改造 `get_regime()` — 使用带质量的分类：**
```python
def get_regime():
    data = _get_qvix_data()
    if data is None:
        logger.warning("[qvix] NO DATA SOURCE AVAILABLE — using ALERT fallback")
        return {**FALLBACK, "alert": "no_data_source"}
    
    # 验证后分类
    q50 = _latest_qvix(data["50"])
    q500 = _latest_qvix(data["500"])
    quality = _qvix_validator.validate(q50, q500)
    
    regime_50, desc_50, alerts_50 = classify_regime_with_quality(q50, quality)
    regime_500, desc_500, alerts_500 = classify_regime_with_quality(q500, quality)
    
    result = {
        "qvix_50": round(q50, 1),
        "qvix_500": round(q500, 1),
        "regime": regime_500 if regime_order[regime_500] > regime_order[regime_50] else regime_50,
        "quality_check": quality,
        "data_alerts": alerts_50 + alerts_500,
        "validator_summary": _qvix_validator.get_alert_summary(),
    }
    return result
```

---

## 方案2: 状态转换回测框架（集成到 regime_transition.py）

### 改动清单

**1. 在 `regime_transition.py` 的 `predict_transition()` 末尾添加日志：**
```python
from etf_platform.decision.regime_transition_improvements import TransitionRecord

# 在返回前记录预测
record = TransitionRecord(
    date=date.today().isoformat(),
    timestamp=datetime.now().isoformat(),
    current_regime=current_regime,
    qvix_50=qvix_50, qvix_500=qvix_500,
    prob_stay=prob_stay, prob_improve=prob_improve, prob_worsen=prob_worsen,
    breadth_pct=breadth, vol_trend=vol_trend,
    volume_signal=volume_signal, momentum_signal=momentum_signal,
    confidence=confidence, blended_weights=blended,
)
try:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(TRANSITION_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
except OSError:
    pass
```

**2. 在 pipeline.py 的每日运行结束时触发验证：**
```python
from etf_platform.decision.regime_transition_improvements import TransitionBacktester

# 每周日运行一次完整回测
if datetime.now().weekday() == 6:  # Sunday
    bt = TransitionBacktester()
    n = bt.load_predictions()
    if n > 0:
        results = bt.run_full_backtest()
        logger.info("[backtest] transition model: %s", results)
```

**3. 关键指标监控阈值：**

| 指标 | 健康值 | 警告值 | 危险值 |
|------|--------|--------|--------|
| 预测准确率 | >50% | 40-50% | <40% |
| Brier Score | <0.15 | 0.15-0.20 | >0.20 |
| Log Loss | <0.80 | 0.80-1.00 | >1.00 |
| 超额收益 | >5% | 0-5% | <0% |

---

## 方案3: Regime阈值统计校准（长期改进）

### 当前问题
硬编码阈值 16/22/28 无任何统计依据。

### 改进方向
1. 收集至少3个月历史QVIX数据
2. 计算分位数：P10→complacent, P30→normal, P70→cautious
3. 按季度重新校准

```python
# 伪代码
def compute_dynamic_thresholds(historical_qvix_50: list[float], historical_qvix_500: list[float]):
    all_vals = sorted(historical_qvix_50 + historical_qvix_500)
    n = len(all_vals)
    return {
        "complacent": all_vals[int(n * 0.10)],   # 底部10%
        "normal":     all_vals[int(n * 0.30)],   # 30%分位
        "cautious":   all_vals[int(n * 0.70)],   # 70%分位
    }
```

---

## 实施优先级

| 优先级 | 改进项 | 工作量 | 风险降低 |
|--------|--------|--------|----------|
| P0 | QVIXValidator集成到qvix_regime.py | 2h | HIGH — 防止静默错误决策 |
| P0 | 预测自动记录到JSONL | 1h | MEDIUM — 使模型可验证 |
| P1 | TransitionBacktester周度运行 | 2h | MEDIUM — 量化模型质量 |
| P2 | SecondaryDataSource实现 | 4h | HIGH — 数据源冗余 |
| P2 | 动态阈值校准 | 3h | LOW — 改善阈值合理性 |
| P3 | 在线Brier score监控告警 | 2h | MEDIUM — 实时质量感知 |
