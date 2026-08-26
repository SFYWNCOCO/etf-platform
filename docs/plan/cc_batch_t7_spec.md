# CC 批次T7实施规格 — P2-B 理由链一行补全 + P2-C KB集成率≥25%（0假集成）

仓库根 = 当前工作目录。禁止改 tests/ 既有文件；只允许新增测试。禁止为凑数把 k-code 写成死字符串——每条映射必须被真实消费链路读取。

## 基线（已实测）
python scripts/kb_integration_audit.py → 总数597 / 引用64 / 集成率10.7%。目标≥25%（即引用≥150）。

## 改动1 — P2-B：patrol wrapper 理由链一行（新旧兼容）
现状：wrapper 已有两行（溯源行 line~152、KB依据行 line~156-160），缺动量值与过滤通过项。
- 把每只推荐的溯源行升级为单行理由链：
  `理由链: 动量<+X.XX%(20d)> | 过滤<净N层同向/低置信gated> | K线<iso> | 行情<src> | 新闻<状态> | KB<k001,k002>`
- 数据源：rec.layer_breakdown.momentum/net_layers/gated_out + rec.data_sources + rec.kb_reasons，全部 .get 容错；字段缺失时该段省略不打印 NA 堆砌；旧格式(无这些键)退化为现有两行行为，不得报错
- weekly_top3.py 若缺过滤字段透传则补（layer_breakdown 已含 net_layers/gated_out，确认即可）

## 改动2 — P2-C：高价值未集成 k-code 板块化注入
1. 跑 audit 拿到未引用 k-code 清单；从注册表/knowledge 文件读每个 code 的 title/source_file
2. 按 title 关键词映射到板块（半导体/医药/军工/消费/金融/新能源/周期/跨境/宏观/流动性等，复用 l34_kb_catalyst.SECTOR_ALIASES 的板块口径），选相关性明确者约 100 条（宁缺毋滥，凑不满如实报告）
3. 新建 src/etf_platform/kb/sector_kb_map.py：
   - SECTOR_KB_CODES: dict[板块, list[{kcode,title}]]（数据即映射，带生成说明头注释）
   - get_sector_kb_codes(sector) -> list[dict]（别名归一后查询，未命中返回[]）
4. 真实消费接线（0假集成的关键，两处都要接）：
   - l34_kb_catalyst.get_kb_catalyst_summary(sector)：摘要尾部追加映射到的 KB 依据段（如 "KB依据: k123标题; k456标题"，至多3条）
   - weekly_top3._kb_reasons_for_sector()：优先查 sector_kb_map，命中用之（附上title），未命中回退现有关键词匹配
5. 新建 tests/test_sector_kb_map.py：映射结构合法(kcode格式/title非空)；get_sector_kb_codes 别名命中与未命中；l34 摘要含KB依据段；断言密度≥4

## 验收（自己跑通并报告数字）
1. python scripts/kb_integration_audit.py 复跑：集成率≥25%，new_references=0（无假集成）；前后数字写入报告
2. PYTHONPATH=src python -m pytest tests/test_sector_kb_map.py tests/test_weekly_data_sources.py -q 全过
3. python etf_daily_patrol_wrapper.py 实跑：理由链行输出正常（网络失败可降级说明）
4. 全量回归 pytest tests/ -q 记录 passed 数
最后输出：改动清单 + audit 前后对比 + 理由链行样例。
