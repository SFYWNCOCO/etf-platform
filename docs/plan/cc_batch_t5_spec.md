# CC 批次T5实施规格 — P0收尾：材料刷新脚本升级(改名+Sina兜底+emerging) + 15:10 cron挂钩

仓库根 = 当前工作目录 (etf-platform)。禁止改动 tests/ 下既有测试文件；只允许新增测试。
蓝图依据：refactor_blueprint.md v2 §一 C档 —— 真实源刷新器 akshare + Sina期货兜底双源，挂入 15:10 price_cache_refresh 同批 cron。

## 改动1 — git mv 改名
- `git mv scripts/refresh_material_prices.py scripts/material_price_refresh.py`（captain 指定名，git 管历史不建副本）
- grep 全仓库确认无其他引用残留；文件内 docstring 同步更新

## 改动2 — Sina 期货兜底双源（v2 风险点2）
- 先读 src/etf_platform/analysis/material_live.py 学习现有 akshare 调用与超时模式
- 主源 akshare 现货/前收盘接口维持现状；新增兜底源：Sina 期货行情(hq.sinajs.cn, 形如 hf_ 前缀连续合约)，主源某品种取不到 → 走 Sina 映射表(品种→合约代码，只映射脚本里已有命中过的品种，如 碳酸锂=hf_LC 等，先 grep material_live.py 复用已有映射若有)
- 兜底也必须 timeout 包裹；来源标注：条目盖 `price_source`(akshare/sina_fallback) 字段便于审计
- 单品种双源都失败 → 保持原样计入 failed（现状行为不变）

## 改动3 — 支持 emerging_materials.yaml 刷新
- 刷新目标从仅 material_prices.yaml 扩为 [material_prices.yaml, config/emerging_materials.yaml]（先读该文件确认字段结构相同才刷，结构不同则跳过并在摘要说明原因——不硬刷坏格式）
- 每个文件独立汇总 updated/kept/failed；--dry-run 对两文件同时生效

## 改动4 — price_cache_refresh.py 尾部挂钩（15:10 同批 cron）
- main() 在 save_cache 成功后追加：subprocess 调 scripts/material_price_refresh.py（timeout=180s，capture 输出打摘要行）
- finance_search 教训双检：①挂钩前确认脚本存在且 py_compile 过，不存在则打 ⚠️ 不中断 ②失败不影响 price_cache 主职责退出码（主职责成功仍 return 0），但必须打印 loud 的 ❌/⚠️ 行供日报可见
- price_cache_refresh.py 自身改动 ≤25 行

## 测试 — 新增 tests/test_material_refresh_sources.py
- 抽出纯函数（如 品种→Sina合约映射查询 / 价格解析归一）做单元测试 ≥4 断言
- 不写依赖真实网络的测试；网络路径靠 --dry-run 人工验证

## 验收（你必须自己跑通并如实报告数字）
1. PYTHONPATH=src python -m pytest tests/test_material_refresh_sources.py -q 全过
2. PYTHONPATH=src python scripts/material_price_refresh.py --dry-run 打印两文件更新计划（网络失败如实报告，不得伪造）
3. python price_cache_refresh.py 实跑一次确认挂钩生效且主职责正常（或说明为何跳过实跑）
4. 全量回归 PYTHONPATH=src python -m pytest tests/ -q 记录 passed 数
输出改动清单+刷新摘要。
