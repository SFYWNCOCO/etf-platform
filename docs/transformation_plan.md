# ETF分析系统改造方案 v1.0

## 一、目标

学习东方财富/天天基金（fund.eastmoney.com）的ETF分析功能，补齐我们现有etf-platform系统的短板。

## 二、改造模块清单

### 模块1：折溢价实时监控（优先级P0）
- **新增文件**：`src/etf_platform/analysis/dip_monitor.py`
- **数据源**：`akshare.fund_etf_spot_em()` 返回IOPV和折价率字段
- **功能**：
  - 实时计算所有ETF的折溢价率
  - 溢价率>3%自动预警（QDII常见）
  - 折溢价率历史走势图
  - 与IOPV偏差检测
- **集成点**：L16实时信号层 + daily patrol

### 模块2：资金流向分析（优先级P0）
- **新增文件**：`src/etf_platform/analysis/fund_flow.py`
- **数据源**：`akshare.fund_etf_spot_em()` 主力净流入字段
- **功能**：
  - 主力净流入/净占比趋势
  - 超大单/大单/中单/小单分解
  - 资金流向与价格背离检测
  - 行业/主题ETF资金轮动
- **集成点**：L17量化因子层 + L16实时信号层

### 模块3：同类排名与评级整合（优先级P1）
- **新增文件**：`src/etf_platform/analysis/ranking.py`
- **数据源**：`akshare.fund_info_index_em()` + `akshare.fund_name_em()`
- **功能**：
  - 同类ETF百分位排名计算
  - 四家评级机构数据整合
  - 四分位排名（优秀/良好/一般/不佳）
  - 排名走势历史
- **集成点**：scorer.py 评分层

### 模块4：持仓重叠度分析（优先级P1）
- **新增文件**：`src/etf_platform/analysis/holdings_overlap.py`
- **数据源**：东财ETF详情页持仓数据
- **功能**：
  - 两只ETF之间的持仓重叠度计算
  - 行业配置相似度
  - 集中度风险检测
  - Smart Beta ETF重叠分析
- **集成点**：decision/select.py + portfolio.py

### 模块5：收益测算器（优先级P2）
- **新增文件**：`src/etf_platform/utils/return_calculator.py`
- **功能**：
  - 基于历史收益率模拟不同申购金额的未来收益
  - 定投 vs 单笔收益比较
  - 风险调整后收益估算
- **集成点**：CLI工具

### 模块6：ETF多维筛选器增强（优先级P2）
- **修改文件**：`src/etf_platform/decision/screener.py`
- **新增筛选维度**：
  - 折溢价率范围
  - 资金流向方向
  - 同类排名百分位
  - 评级等级
  - 规模区间
  - 换手率
  - 跟踪误差

## 三、实施计划

### Phase 1（本周）：核心数据层
1. 创建 `dip_monitor.py` - 折溢价监控
2. 创建 `fund_flow.py` - 资金流向分析
3. 更新 `data/realtime_data.py` 增加IOPV和资金流字段
4. 更新 `analysis/l16_live_signals.py` 接入新信号

### Phase 2（下周）：分析与决策层
5. 创建 `ranking.py` - 同类排名与评级
6. 创建 `holdings_overlap.py` - 持仓重叠度
7. 更新 `decision/screener.py` 增加新筛选维度
8. 更新 `scorer.py` 增加新评分因子

### Phase 3（下下周）：工具与展示
9. 创建 `return_calculator.py` - 收益测算器
10. 更新 CLI 增加新命令
11. 编写单元测试
12. 更新文档

## 四、预期效果

| 指标 | 改造前 | 改造后 |
|------|--------|--------|
| ETF分析维度 | ~15个因子层 | ~20个因子层 |
| 实时信号 | 价格/成交量 | +折溢价/资金流 |
| 筛选条件 | 基础评分 | +折溢价/评级/排名 |
| 风险管理 | VaR/波动率 | +持仓重叠/折溢价风险 |
| 数据源覆盖 | AKShare+东财 | +IOPV+资金流向+评级 |
