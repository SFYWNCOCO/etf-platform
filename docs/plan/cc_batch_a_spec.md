# CC 批次A实施规格 — S1 freshness 工具 + S2 静态物料层时效守卫

仓库根 = 当前工作目录 (etf-platform)。全部改动在此仓库内。禁止改动 tests/ 下既有测试文件；只允许新增测试。

## 背景
config/material_prices.yaml 是静态物料价格快照(mtime 可能数周旧)，经 src/etf_platform/analysis/deep_sub/materials.py 的 register_from_file 加载进 L3/L4 打分，无任何时效标记 → 陈旧价冒充现价(k090 锂价教训)。目标：给静态数据加 as_of/stale 标记并降权为"先验"，不静默当实时。

## S1 — 新建 src/etf_platform/utils/freshness.py (~60行)
- 函数 `as_of(path, stale_days=14)` → dict:
  - {"exists": bool, "path": str, "mtime_iso": str|None, "age_days": float|None, "status": "fresh"|"stale"|"missing", "checked_at": iso}
  - status 判定：不存在=missing；age_days > stale_days=stale；否则 fresh
- 简洁实现，标准库 only (pathlib/datetime)。注释只写"为什么"。

## S2a — 改 src/etf_platform/analysis/deep_sub/materials.py
- register_from_file(path)：加载成功后调用 utils.freshness.as_of(path)，给本文件注册的每个 entry 盖上 `_data_as_of`(mtime_iso) 与 `_stale`(bool) 字段。
- 新增 `materials_freshness()`：返回 {fname: freshness_dict}（对 _auto_load_plugins 扫描的三个 yaml）。

## S2b — 改 src/etf_platform/analysis/material_bridge.py
- material_layer_adjustments 中计算 mat signal 时：若 mat.get("_stale") 为 True，signal 乘以 0.3（降权为先验），并在该条 tuple 后追加 stale 标记（注意聚合处解包同步改）。
- 新增模块级 `MATERIAL_FRESHNESS_REPORT`（dict）+ 函数 `material_freshness_report()`：在 _get_material_signals 合并后填充 {mat_name: {"_data_as_of":..., "_stale":...}}（仅 _source 含 yaml/plugin 的条目）。

## 测试 — 新建 tests/test_freshness.py
- tmp_path 建新文件 → as_of status=fresh
- os.utime 把 mtime 拨回 30 天前 → status=stale
- 不存在路径 → status=missing
- register_from_file 对旧 mtime 的 tmp yaml 注册后 entry 带 _stale=True 且带 _data_as_of
- 断言密度 ≥2，不写空测试

## 验收（你必须自己跑通才算完成）
PYTHONPATH=src python -m pytest tests/test_freshness.py tests/test_material_bridge.py -q 全过。
最后输出改动文件清单与测试结果摘要。
