# Changelog

## [0.2.0] - 2026-06-26

### Added
- self_manager: PDCA+OODA 循环学习管理系统
- 7源新闻系统: 华尔街见闻/微博/36氪/腾讯/V2EX/新浪
- 全市场扫描决策系统 (etf screen/recommend)
- 历史K线趋势分析 + 扫描结果趋势列
- 估值维度: NAV/市价/折价率/阶段涨幅/跟踪标的
- ETF对比功能: etf compare
- L8实时数据增强 + L9新闻催化剂注入
- DataSource 抽象层 + 多源自动 fallback
- 深度学习/行业轮动/每日巡逻/组合优化

### Changed
- 评分标准化: min-max归一化解决Top ETF分数扎堆
- 自动权重优化: 高区分度层权重放大,低区分度层压制
- 修复BOM头: 18个文件UTF-8 BOM问题
- UX优化: chain/health/holdings 友好提示
- status命令加8s超时保护

### Infrastructure
- 包结构: pyproject.toml, pip install -e .
- 配置YAML化: etfs.yaml/vulnerability.yaml/materials.yaml
- 测试覆盖: 21个pytest
- git版本管理: 17次提交

## [0.1.0] - 2026-06-25
- ETF 11-layer penetration platform 初始版本
- YAML配置化
- 基本测试覆盖
