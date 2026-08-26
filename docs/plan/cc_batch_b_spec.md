# CC 批次B实施规格 — S3 推荐溯源输出（weekly_top3 data_sources + patrol wrapper 兼容）

仓库根 = 当前工作目录 (etf-platform)。禁止改动 tests/ 下既有测试文件；只允许新增测试。

## 背景
weekly_top3.py 输出买卖指令但无逐只数据溯源(G3)。要求每只推荐附 data_sources：K线截止日期 + 行情源名 + 新闻对冲状态。下游 etf_daily_patrol_wrapper.py 解析 --json，必须新旧字段兼容不破坏。

## 改动1 — weekly_top3.py
1. 新增纯函数 `_build_data_sources(code, kline_ts, quote_meta, news_label)`：
   - 返回 {"kline_as_of": iso|None, "quote_source": str|None, "quote_as_of": iso|None, "news_status": str}
   - kline_ts 来自 `etf_platform.data.kline._trend_ts.get(code)`（epoch秒→ISO；取不到给 None）
   - quote_meta 来自 live_prices 的 "_meta"（含 source/timestamp 字段时取用；结构以实际代码为准，先读代码再写）
   - news_label 为已有变量 news_age_info 的值
2. 在构建 rec 时加 `"data_sources": _build_data_sources(...)`（p 的 trend 对象可从 trends dict 取 code）。
3. recommendations_log.jsonl 行内同步写入 "data_sources" 字段。
4. 不改任何推荐逻辑/数值行为——纯增量字段。

## 改动2 — etf_daily_patrol_wrapper.py
- Top3 表格后，若 rec 含 data_sources 则追加一行溯源摘要（如 `溯源: K线<iso> | 行情<sina> | 新闻<状态>`），字段全部 .get 容错——旧格式(无 data_sources)不得报错。

## 测试 — 新建 tests/test_weekly_data_sources.py
- 用 importlib 从仓库根加载 weekly_top3.py 模块（sys.path 先插 src），直接测 _build_data_sources：
  - 全参数 → 各字段正确映射
  - kline_ts=None / quote_meta=None / news_label="" → 返回 None/None/"" 且不抛异常
- 断言密度 ≥2。

## 验收（你必须自己跑通）
PYTHONPATH=src python -m pytest tests/test_weekly_data_sources.py -q 全过；
PYTHONPATH=src python weekly_top3.py --json 跑通且 recommendations[0] 含 data_sources 键（网络失败可重试一次，仍失败则如实报告）。
最后输出改动文件清单与验证结果。
