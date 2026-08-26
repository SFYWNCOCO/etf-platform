# CC 批次C实施规格 — S4 cron 自动验收器（heartbeat 后断言 + 飞书告警字段）

仓库根 = 当前工作目录 (etf-platform)。禁止改动 tests/ 下既有测试文件；只允许新增测试。

## 背景
cron 心跳(etf_heartbeat_latest.json)只记录运行不做验收断言；陈旧产物(如 screener_top20.json 停在07-14)无人报警(G4)。要求每日 patrol 尾部自动验收：今日有推荐/核心产物mtime<24h/stale标记机制在位，fail 写告警字段供飞书日报呈现。

## 新建 acceptance_check.py（仓库根，与 etf_daily_patrol_wrapper.py 同级）
- 函数 `validate_daily_outputs(base_dir=None, now=None)`，base_dir 缺省=脚本所在目录（便于测试注入 tmp 目录）：
  返回 {"checked_at": iso, "all_ok": bool, "checks": [{"name","ok","detail"}...]}，检查项：
  1. "recommendations_today": data/recommendations_log.jsonl 存在且含今天(按传入now的日期)的记录
  2. "artifacts_fresh_24h": 逐一检查 data/price_cache.json、data/kline_trend_cache.json、data/news_etf_signals.json 的 mtime < 24h；缺失或超龄逐项列出（任一失败则本项 fail，detail 列明哪个产物陈旧）
  3. "heartbeat_alive": data/etf_heartbeat_latest.json 存在且 mtime < 48h（心跳自身超期=红灯，防"验收器挂了没人知道"）
  4. "stale_mechanism_armed": 可从 etf_platform.analysis.material_bridge 导入 material_freshness_report 并返回 dict（机制在位即可，不因存在 stale 数据而 fail——stale 已被降权标记）
- 单个检查内部异常 → 该项 ok=False 且 detail 含异常类型（loud failure，不静默）。

## 改 etf_daily_patrol_wrapper.py
- main() 尾部（风险提示之前）调用 validate_daily_outputs()：
  - 打印 "## ✅ 自动验收" 小节：每个 check 一行 ✅/❌ + detail
  - all_ok=False 时首行加 "⚠️ 验收告警"
  - 结果写入 data/etf_acceptance_latest.json（覆盖写）
  - 验收器自身异常 → 打印 ❌ 验收器故障 + 异常信息，不中断日报其余部分

## 测试 — 新建 tests/test_acceptance_check.py（pytestmark unit）
- 用 importlib 从仓库根加载 acceptance_check.py：
  - tmp 目录注入：log 文件含今日记录 + 三个产物新建(mtime现在) + heartbeat 新建 + 伪造 etf_platform 可导入 → all_ok=True
  - 把 price_cache.json mtime 拨回 2 天前(os.utime) → artifacts_fresh_24h ok=False 且 detail 提及该文件
  - 删除 log 文件 → recommendations_today ok=False
  - now 参数传固定 datetime 保证日期判定确定性
- 断言密度 ≥2。

## 新建 scripts/refresh_material_prices.py — 材料价格真实源定期刷新
- 目的：让 config/material_prices.yaml 等静态快照周期性被真实行情刷新，使 S2 守卫自动恢复 fresh 全权（k090 锂价教训的根治侧）。
- 先读 src/etf_platform/analysis/material_live.py 沿用其 akshare 调用与 run_with_timeout 包裹模式；一切外部调用必须带 timeout（akshare 网络不稳，防拖死）。
- 行为：读现有 yaml → 对能取到实时价的材料更新 `current` 数值字段并在条目盖 `price_as_of`(ISO)；顶部写 `_refreshed_at` → 写回原文件（改原文件，不建副本）。取不到价的材料保持原样并在汇总中列出。
- 支持 --dry-run：只打印将更新的条目不写盘。
- 失败处理：单材料失败跳过并计入 failed 列表；全部失败 exit 1 且打印明确错误（loud failure，不静默 exit 0）。
- 结尾打印摘要：updated/kept/failed 计数。
- 本脚本不注册 cron（只交付脚本），但文件头注释写明建议挂法（工作日 15:30 在 price_cache_refresh 之后）。

## 验收（你必须自己跑通）
PYTHONPATH=src python -m pytest tests/test_acceptance_check.py -q 全过；
PYTHONPATH=src python -c "from acceptance_check import validate_daily_outputs; import json; r=validate_daily_outputs(); print(json.dumps(r, ensure_ascii=False, indent=1))" 能出真实结果（当前环境下允许个别 check 红——如实报告哪些红及原因）。
最后输出改动文件清单与验证结果。
