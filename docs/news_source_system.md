# 新闻→ETF 动态信号系统 v16.17

## 架构总览

```
新闻采集: fetch_news_sources.py (realtime)
    ↓ news_raw_sources.json
LLM Agent: cron 新闻→ETF 日报 (08:15/13:00)
    ├─ 读取 news_raw_sources.json + web_search 补充
    ├─ 分析行业情绪 → news_sentiment.json
    └─ news_to_etf_bridge.py --auto
        ↓ news_etf_signals.json
pipeline._apply_kb_signals() → L9_Signals ±2.0
```

## 新闻源列表

| 来源 | API | 频率 | 说明 |
|------|-----|:----:|------|
| 新浪财经滚动 | feed.mix.sina.com.cn/api/roll/get | 实时 | 综合财经+国际，JSONP解析 |
| 东方财富快讯 | np-anotice-stock.eastmoney.com | 实时 | 公告/业绩/异动，纯JSON |
| 同花顺个股新闻 | news.10jqka.com.cn/tapp/news/push/stock/ | 实时 | 板块+个股，纯JSON |

## 关键文件

- `scripts/fetch_news_sources.py` — 多源采集器（输出到 `etf-platform/data/news_raw_sources.json`）
- `etf-platform/news_to_etf_bridge.py` — 桥脚本（消费 news_sentiment.json）
- `etf-platform/data/news_sentiment.json` — cron写入的行业情绪
- `etf-platform/data/news_etf_signals.json` — 最终582个ETF信号

## 使用方式

```bash
# 手动刷新新闻源
cd D:/龙虾/.openclaw/etf-platform
python D:/龙虾/.openclaw/scripts/fetch_news_sources.py --stdout

# 查看某板块相关新闻
python D:/龙虾/.openclaw/scripts/fetch_news_sources.py --sector 半导体

# cron每日自动：新闻采集+分析+bridge更新
# job_id: 6f737878118d (08:15 weekday)
```
