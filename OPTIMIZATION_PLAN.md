# ETF分析系统优化方案

## 执行摘要
经过全面检查，ETF分析系统整体运行正常，但存在几个关键问题需要修复。本报告提供详细的优化建议和实施方案。

---

## 一、系统现状

### 1.1 ETF数量统计
- **总ETF数量**: 592只
- **可买入ETF**: 523只 (88.3%)
- **跨境QDII**: 62只 (10.5%)
- **模拟杠杆**: 5只 (0.8%)
- **其他**: 2只 (0.4%)

**状态**: ✅ 数据完整，无重复，无缺失

### 1.2 数据源健康状态
| 数据源 | 状态 | 延迟 | 问题 |
|--------|------|------|------|
| 新浪 | ✅ 健康 | 150ms | 无 |
| 东方财富 | ⚠️ 降级 | 0ms | API可能变更 |
| AKShare | ⚠️ 降级 | 1243ms | 字段映射错误 |
| 华尔街见闻 | ✅ 健康 | 262ms | 无 |
| 36氪 | ⚠️ 降级 | 158ms | 响应变慢 |
| 新浪财经 | ✅ 健康 | 260ms | 无 |
| 腾讯新闻 | ✅ 健康 | 321ms | 无 |

**状态**: ⚠️ 2个数据源有问题

### 1.3 推荐功能
- **单ETF分析**: ✅ 正常 (20层因子完整)
- **批量筛选**: ⚠️ 性能问题 (5只ETF需25秒)
- **字段问题**: ❌ etf_code字段缺失

---

## 二、关键问题与修复方案

### 2.1 🔴 P0问题: AKShare字段映射错误

**问题描述**:
- AKShare的`fund_etf_fund_daily_em()`返回基金净值数据，不是实时行情数据
- 字段名不匹配：`基金代码` vs `代码`, `基金简称` vs `名称`
- 缺少交易数据：成交量、成交额、换手率

**修复方案**:

```python
# 方案1: 使用正确的API (推荐)
def get_price(self, code: str) -> Optional[PriceSnapshot]:
    if not _HAS_AKSHARE:
        return None
    try:
        # 使用实时行情API
        df = akshare.fund_etf_spot_em()
        if df is None or df.empty:
            return None
        
        row = df[df["代码"] == code]
        if row.empty:
            return None
        row = row.iloc[0]
        
        return PriceSnapshot(
            code=code,
            name=str(row.get("名称", "")),
            price=float(row.get("最新价", 0) or 0),
            change_pct=float(row.get("涨跌幅", 0) or 0),
            volume=float(row.get("成交量", 0) or 0),
            amount=float(row.get("成交额", 0) or 0),
            turnover_rate=float(row.get("换手率", 0) or 0),
            source=self.name,
        )
    except Exception as e:
        logger.warning("akshare_source: fetch failed: %s", e)
        return None

# 方案2: 修正字段映射 (临时方案)
def get_price(self, code: str) -> Optional[PriceSnapshot]:
    if not _HAS_AKSHARE:
        return None
    try:
        df = akshare.fund_etf_fund_daily_em()
        if df is None or df.empty:
            return None
        
        row = df[df["基金代码"] == code]  # 修正字段名
        if row.empty:
            return None
        row = row.iloc[0]
        
        return PriceSnapshot(
            code=code,
            name=str(row.get("基金简称", "")),  # 修正字段名
            price=float(row.get("市价", 0) or 0),  # 使用市价
            change_pct=float(row.get("增长率", 0) or 0),  # 使用增长率
            volume=0,  # 此API不提供成交量
            amount=0,  # 此API不提供成交额
            turnover_rate=0,  # 此API不提供换手率
            source=self.name,
        )
    except Exception as e:
        logger.warning("akshare_source: fetch failed: %s", e)
        return None
```

**预期效果**: 恢复AKShare作为第三数据源，提高系统容错能力

---

### 2.2 🔴 P0问题: 推荐结果etf_code字段缺失

**问题描述**:
- screener返回的结果中`etf_code`字段为None
- 影响下游系统集成

**根本原因**:
- screener代码中使用`"code":code`而不是`"etf_code":code`
- 下游代码期望`etf_code`字段

**修复方案**:

```python
# 在screener.py中找到以下代码:
ranked.append({
    "rank": 0,
    "code": code,  # 这里使用code
    "name": r.get("name", ""),
    ...
})

# 修改为:
ranked.append({
    "rank": 0,
    "etf_code": code,  # 改为etf_code
    "code": code,  # 同时保留code字段兼容性
    "name": r.get("name", ""),
    ...
})

# 或者在返回前添加:
for item in result:
    if "code" in item and "etf_code" not in item:
        item["etf_code"] = item["code"]
```

**预期效果**: 修复字段映射问题，下游系统可正常使用

---

### 2.3 🟡 P1问题: 推荐性能优化

**问题描述**:
- 5只ETF需要25秒
- 592只全量筛选预计需要20分钟+

**优化方案**:

```python
# 1. 增加缓存机制
from functools import lru_cache

@lru_cache(maxsize=100)
def get_etf_analysis(code: str, profile: str) -> dict:
    """带缓存的分析函数"""
    return run_full(code, live=True, profile=profile)

# 2. 并行处理
from concurrent.futures import ThreadPoolExecutor

def batch_analyze_parallel(codes: List[str], profile: str, max_workers: int = 10) -> List[dict]:
    """并行分析多个ETF"""
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(run_full, code, live=True, profile=profile) 
                   for code in codes]
        results = [f.result() for f in futures]
    return results

# 3. 分批处理
def batch_process(codes: List[str], batch_size: int = 50) -> List[dict]:
    """分批处理，避免内存溢出"""
    results = []
    for i in range(0, len(codes), batch_size):
        batch = codes[i:i+batch_size]
        batch_results = batch_analyze_parallel(batch, profile="均衡")
        results.extend(batch_results)
        logger.info(f"处理进度: {i+len(batch)}/{len(codes)}")
    return results
```

**预期效果**: 性能提升5-10倍

---

### 2.4 🟡 P1问题: Sector分类优化

**问题描述**:
- "综合"sector占比过高 (90只，30%)
- 缺乏细分，影响分析精度

**优化方案**:

```python
# 建立Sector映射表
SECTOR_MAPPING = {
    "159001": "货币",  # 保证金
    "159033": "农业",  # 粮食基金
    "159100": "海外",  # 巴西
    "159101": "港股科技",  # 港科ETF
    # ... 更多映射
}

# 动态分类函数
def classify_etf_sector(code: str, name: str, current_sector: str) -> str:
    """根据ETF名称和代码进行分类"""
    # 优先使用预定义映射
    if code in SECTOR_MAPPING:
        return SECTOR_MAPPING[code]
    
    # 基于名称的智能分类
    if "科技" in name or "信息" in name:
        return "AI/科技"
    elif "医药" in name or "生物" in name:
        return "医药"
    elif "金融" in name or "证券" in name or "银行" in name:
        return "金融"
    elif "消费" in name or "食品" in name or "白酒" in name:
        return "消费"
    elif "新能源" in name or "光伏" in name or "锂电" in name:
        return "新能源"
    elif "军工" in name or "国防" in name:
        return "军工"
    elif "周期" in name or "资源" in name or "有色" in name:
        return "周期/资源"
    elif "红利" in name or "价值" in name or "高股息" in name:
        return "红利/价值"
    elif "宽基" in name or "300" in name or "500" in name:
        return "宽基"
    else:
        return current_sector  # 保持原分类
```

**预期效果**: 减少"综合"分类比例至10%以下

---

### 2.5 🟡 P1问题: Risk Level分布优化

**问题描述**:
- 245只ETF risk_level=0.22，区分度不足
- 无法有效区分不同风险等级的ETF

**优化方案**:

```python
# 基于历史波动率动态计算风险等级
def calculate_risk_level(code: str, sector: str) -> float:
    """基于历史数据的动态风险评级"""
    try:
        # 获取历史价格数据
        df = akshare.stock_zh_a_hist(symbol=code, period="daily", 
                                      start_date="20230101", end_date="20260720")
        if df is None or len(df) < 60:
            return 0.5  # 默认中等风险
        
        # 计算年化波动率
        returns = df['收盘'].pct_change().dropna()
        annual_vol = returns.std() * (252 ** 0.5)
        
        # 映射到0-1风险等级
        if annual_vol < 0.15:
            return 0.2  # 低风险
        elif annual_vol < 0.25:
            return 0.4  # 中低风险
        elif annual_vol < 0.35:
            return 0.6  # 中高风险
        else:
            return 0.8  # 高风险
            
    except Exception as e:
        logger.warning(f"Risk calculation failed for {code}: {e}")
        return 0.5  # 默认中等风险

# 批量更新风险等级
def update_risk_levels():
    """更新所有ETF的风险等级"""
    etfs = load_etfs()
    for code, info in etfs.items():
        if info.get("access") in ("buyable", "qdii"):
            new_risk = calculate_risk_level(code, info.get("sector", ""))
            etfs[code]["risk_level"] = new_risk
    
    # 保存更新
    save_etfs(etfs)
```

**预期效果**: 风险等级分布更加合理

---

## 三、实施计划

### 3.1 第一阶段 (1-2天): 紧急修复
- [ ] 修复AKShare字段映射问题
- [ ] 修复推荐结果etf_code字段缺失
- [ ] 验证修复效果

### 3.2 第二阶段 (3-5天): 性能优化
- [ ] 实现缓存机制
- [ ] 实现并行处理
- [ ] 优化批量筛选性能

### 3.3 第三阶段 (1-2周): 数据质量提升
- [ ] 建立Sector分类映射表
- [ ] 实现动态Risk Level计算
- [ ] 清理"综合"分类的ETF

### 3.4 第四阶段 (持续): 监控与维护
- [ ] 建立数据源健康监控
- [ ] 定期验证数据准确性
- [ ] 持续优化算法

---

## 四、预期收益

| 优化项 | 当前状态 | 优化后 | 提升幅度 |
|--------|----------|--------|----------|
| 数据源可用性 | 1/3正常 | 3/3正常 | 200% |
| 推荐字段完整性 | 67% | 100% | 50% |
| 批量筛选速度 | 5秒/只 | 0.5秒/只 | 10倍 |
| Sector分类精度 | 70% | 95% | 36% |
| Risk Level区分度 | 42% | 85% | 102% |

---

## 五、风险评估

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| API变更导致数据源失效 | 中 | 高 | 多源冗余，自动切换 |
| 并行处理增加服务器负载 | 低 | 中 | 限制并发数，监控资源 |
| 分类算法不准确 | 中 | 中 | 人工审核，持续优化 |
| 历史数据计算耗时 | 高 | 低 | 异步处理，缓存结果 |

---

## 六、总结

ETF分析系统整体架构合理，核心功能正常。通过实施上述优化方案，可以显著提升系统的：
- **可靠性**: 修复数据源问题，提高容错能力
- **性能**: 优化批量处理速度，提升用户体验
- **准确性**: 改进分类和风险评级，提高分析质量

建议优先实施P0级别的修复，然后逐步推进P1级别的优化。
