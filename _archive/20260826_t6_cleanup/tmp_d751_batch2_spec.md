# d751 落地任务1+2：情绪进因子模型 + 产业链传导

项目: D:/龙虾/.openclaw/etf-platform/
遵守 CLAUDE.md 规则（Ponytail 极简、版本化后缀禁令、具体异常类型）。
所有文件用 Windows 正斜杠绝对路径。

背景（KB d751 新闻情绪因子×LLM 剩余两点）:
- ② 情绪进因子模型: 新闻情绪不应是孤立信号（L9），应进入因子体系与动量/资金流并列
- ③ 产业链传导: 新闻情绪存在地理/产业链外部性——上游新闻传导到中游/下游 ETF

========================================
任务1: sentiment 因子进 factor_dynamic_weights.py（d751 ②）
========================================
文件: D:/龙虾/.openclaw/etf-platform/src/etf_platform/analysis/factor_dynamic_weights.py

1. 新增模块级函数:
   def _get_sentiment_raw(sector: str, etf_code: str = "") -> float:
       - 读取 D:/龙虾/.openclaw/etf-platform/data/news_sentiment.json 的 sectors
       - sector 名匹配（复用 macro_overlay.get_news_boost 的 key in sector or sector in key 逻辑，但返回原始分数）
       - 映射: 看多强→+1.0, 看多中→+0.6, 看多弱→+0.3, 看空强→-1.0, 看空中→-0.6, 看空弱→-0.3, 中性→0.0
       - 文件不存在/异常 → 返回 0.0
       - docstring 注明来源 d751 + macro_overlay.get_news_boost 复用说明

2. 新增因子 "news_sentiment" 到 BASE_WEIGHTS:
   - BASE_WEIGHTS 加 "news_sentiment": 0.08（从 oversold_depth 0.40 减 0.02、risk_adj_momentum 0.25 减 0.02、
     drawdown_recov 0.22 减 0.02、sector_flow 0.10 减 0.02，合计让出 0.08）
   - 最终 BASE_WEIGHTS: oversold_depth 0.38, risk_adj_momentum 0.23, drawdown_recov 0.20, sector_flow 0.08, quality_elastic 0.03, news_sentiment 0.08
   - 注意: sum 应保持 = 1.00（0.38+0.23+0.20+0.08+0.03+0.08 = 1.00）

3. REGIME_MULTIPLIERS 各 regime 加 news_sentiment 乘数:
   - complacent: 1.0（贪婪期情绪跟风有效但易过热）
   - normal: 1.0
   - cautious: 1.3（谨慎期情绪信号更重要）
   - fearful: 1.5（恐慌期情绪反转价值高）
   - 其他 regime（如有）: 1.0

4. get_factor_list() 新增:
   {
       "name": "news_sentiment",
       "raw": lambda t, p: _get_sentiment_raw(p.get("sector", ""), p.get("etf_code", "")),
       "weight": weights.get("news_sentiment", 0.08),
       "desc": "新闻情绪因子(d751)",
   }

验证:
1. python -c "from etf_platform.analysis.factor_dynamic_weights import get_dynamic_weights; w=get_dynamic_weights('normal'); print(w); print('sum=', round(sum(w.values()),4))" → sum=1.0 且含 news_sentiment
2. python -c "from etf_platform.analysis.factor_dynamic_weights import _get_sentiment_raw; print(_get_sentiment_raw('军工'))" → 返回 ±1.0/±0.6/±0.3/0 数值（非异常）
3. 全量测试不破坏

========================================
任务2: 产业链传导（d751 ③）
========================================
文件: D:/龙虾/.openclaw/etf-platform/traded_news_filter.py 或新建 src/etf_platform/analysis/industry_chain.py（推荐后者，独立模块）

新建: D:/龙虾/.openclaw/etf-platform/src/etf_platform/analysis/industry_chain.py

1. 产业链传导表 INDUSTRY_CHAIN（上游→下游传导，sector 名对齐 auto_sentiment.SECTOR_KEYWORDS / news_sentiment.json）:
   {
       "上游资源": {
           "碳酸锂/锂矿": {"related": ["新能源", "有色金属"], "downstream": ["汽车", "新能源"], "note": "锂价上涨→电池成本→新能源车"},
           "稀土": {"related": ["有色金属", "军工"], "downstream": ["军工", "机器人/智造"]},
           "铜": {"related": ["有色金属", "基建/地产"], "downstream": ["基建/地产", "新能源"]},
           "原油/天然气": {"related": ["能源化工"], "downstream": ["能源化工", "化工"]},
           "煤炭": {"related": ["能源化工"], "downstream": ["能源化工", "电力"]},
       },
       "中游制造": {
           "半导体设备": {"related": ["半导体"], "downstream": ["半导体", "AI算力"]},
           "光伏组件": {"related": ["新能源"], "downstream": ["新能源"]},
           "电池/储能": {"related": ["新能源"], "downstream": ["汽车", "新能源"]},
       },
       "下游需求": {
           "新能源车销量": {"related": ["汽车"], "upstream": ["新能源", "有色金属"]},
           "手机出货": {"related": ["消费电子"], "upstream": ["半导体", "消费电子"]},
       },
   }

2. 函数:
   def propagate_signal(sector: str, direction: str, strength: str) -> list[dict]:
       - 输入: 某 sector 的原始信号（如 "新能源" 看多/强）
       - 查 INDUSTRY_CHAIN 找到该 sector 作为 related/downstream/upstream 的所有链路
       - 输出: [{sector: "汽车", direction: "看多", strength: "中", propagation: "下游传导", note: "..."}]
       - 传导强度降级: 原始强→传导中, 原始中→传导弱, 原始弱→不传导
       - 只传导明确方向（看多/看空），中性不传导
       - 去重（同一 sector 多条链路只保留强度最高的）

   def apply_chain_to_signals(signals: dict) -> dict:
       - 输入: news_sentiment.json sectors 结构 {"新能源": {"direction": "看多", "strength": "强", ...}}
       - 对每个有明确方向的 sector 调用 propagate_signal，合并传导结果
       - 输出: 原 signals + 传导生成的信号（原信号不覆盖，传导信号标记 source="chain:下游传导"）
       - 若某 sector 已有原信号，传导不覆盖原信号（原信号优先）

3. 模块 docstring 注明来源 d751（地理外部性→产业链传导）

验证:
1. python -c "from etf_platform.analysis.industry_chain import propagate_signal; print(propagate_signal('新能源', '看多', '强'))" → 输出含下游传导的汽车/有色
2. python -c "from etf_platform.analysis.industry_chain import apply_chain_to_signals; s={'新能源': {'direction':'看多','strength':'强'}}; print(apply_chain_to_signals(s))" → 含新能源原信号 + 传导信号
3. 全量测试不破坏

========================================
任务3: 新增测试 tests/test_industry_chain.py + tests/test_factor_sentiment.py
========================================
新建: D:/龙虾/.openclaw/etf-platform/tests/test_industry_chain.py
用例:
1. test_propagate_bullish_downstream: propagate_signal('新能源','看多','强') 含 '汽车' 且 direction=看多 strength=中
2. test_propagate_strength_degrades: 强→中, 中→弱
3. test_neutral_not_propagated: 中性不传导
4. test_weak_not_propagated: 弱不传导
5. test_apply_chain_to_signals: 原信号 + 传导信号合并，原信号不被覆盖
6. test_propagate_unknown_sector: 未知 sector → 空列表

新建: D:/龙虾/.openclaw/etf-platform/tests/test_factor_sentiment.py
用例:
7. test_dynamic_weights_contains_sentiment: get_dynamic_weights('normal') 含 news_sentiment 且 sum=1.0
8. test_sentiment_weights_vary_by_regime: fearful 的 news_sentiment 权重 > normal 的
9. test_get_sentiment_raw_known: _get_sentiment_raw('军工') 返回 -1.0~1.0 间数值（若 news_sentiment.json 有军工）或 0.0
10. test_get_sentiment_raw_missing_file: 临时改 SENT_FILE 路径为不存在 → 返回 0.0（用 monkeypatch 或 mock）

验证:
1. python -m pytest tests/test_industry_chain.py tests/test_factor_sentiment.py -v 全过（10个）
2. python -m pytest tests/ -q 全过（280 + 10 = 290）
3. 报告每项真实执行输出

========================================
总验收
========================================
1. factor_dynamic_weights: sum=1.0, news_sentiment 因子生效, fearful>normal 权重
2. industry_chain: 传导正确（强度降级/中性不传/原信号优先）
3. 新测试 10 个全过 + 全量 290 全过
4. 报告每项真实执行输出
