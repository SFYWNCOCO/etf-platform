# 替代PE/PB数据源调研结果

## 总结

| 数据源 | PE | PB | 覆盖度 | 稳定性 | 推荐状态 |
|--------|-----|-----|--------|--------|----------|
| **中证指数网(akshare)** | ✅ | ❌ | 主流宽基ETF | ⭐⭐⭐⭐⭐ | **推荐用于PE** |
| 百度股市通(akshare) | ✅ | ✅ | 单只A股 | ⭐⭐⭐ | 备选：通过ETF持仓加权估算 |
| 新浪财经 hq.sinajs.cn | ❌ | ❌ | 实时行情无估值字段 | - | 不适用 |
| 东方财富push2 | ❌ | ❌ | 连接被拒 | - | 当前环境不可用 |
| 东方财富网页端 | ❌ | ❌ | push2连接失败 | - | 不适用 |
| Tushare | ❓ | ❓ | 需token | - | 未测试完整 |
| BaoStock | ❌ | ❌ | pip安装失败(清华源403) | - | 不可用 |

---

## 1. 中证指数网 — stock_zh_index_value_csindex ⭐ 已验证可用

### 测试结果

```python
import akshare as ak
df = ak.stock_zh_index_value_csindex(symbol='000300')
print(df.columns.tolist())
# ['日期', '指数代码', '指数中文全称', '指数中文简称', '指数英文全称', '指数英文简称', 
#  '市盈率1', '市盈率2', '股息率1', '股息率2']
print(df.iloc[0])
# date=2026-07-22, PE1=14.87, PE2=17.49, Div1=2.64, Div2=2.23
```

### 实测支持的主流指数（各20条最新数据）

| 指数代码 | 名称 | PE1(TTM) | PE2(动态) | 来源 |
|----------|------|----------|-----------|------|
| 000300 | 沪深300 | 14.87 | 17.49 | csindex |
| 000905 | 中证500 | 28.7 | N/A | csindex |
| 000016 | 上证50 | 11.97 | N/A | csindex |
| 000852 | 中证1000 | 30.96 | N/A | csindex |
| H30374 | 创业板等权 | 16.21 | N/A | csindex |
| H30184 | 半导体 | 120.25 | N/A | csindex |
| 000808 | 医药生物 | 25.36 | N/A | csindex |
| 000925 | 基本面50 | 9.91 | N/A | csindex |
| 000932 | 中证红利 | 19.17 | N/A | csindex |
| 000991 | 全指医药卫生 | 24.72 | N/A | csindex |
| 000056 | 上证国企 | 10.34 | N/A | csindex |

### 数据来源
- URL: `https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/file/autofile/indicator/{symbol}indicator.xls`
- Excel文件包含：PE1/TTL, PE2/动态, Dividend Yield
- **没有PB数据**

### 实现路径（PE获取）
```python
def get_csindex_pe(index_code):
    df = ak.stock_zh_index_value_csindex(symbol=index_code)
    return {
        'date': df.iloc[0]['日期'],
        'pe_ttm': df.iloc[0]['市盈率1'],  # 通常即TTM
        'pe_dynamic': df.iloc[0]['市盈率2'],
        'dividend_yield_ttm': df.iloc[0]['股息率1'],
        'dividend_yield_dynamic': df.iloc[0]['股息率2'],
    }

# 支持的代码映射
INDEX_CODE_MAP = {
    '沪深300': '000300',
    '上证50': '000016',
    '中证500': '000905',
    '中证1000': '000852',
    '创业板指': 'H30573',  # 注意：csindex需要正确代码
    '半导体': 'H30184',
    '医药生物': '000808',
    '中证红利': '000932',
}
```

---

## 2. 百度股市通 — stock_zh_valuation_baidu ⭐ 已验证可用（单只股票）

### 测试结果

```python
import akshare as ak

# PE(TTM)
df = ak.stock_zh_valuation_baidu(symbol='000001', indicator='市盈率(TTM)')
# columns: ['date', 'value'], shape=(366, 2)
# Latest: 2025-07-22, PE_TTM=5.55

# PB
df = ak.stock_zh_valuation_baidu(symbol='000001', indicator='市净率')
# Latest: 2025-07-22, PB=0.56
```

### 说明
- 仅支持**单只A股**，不支持ETF代码
- 可用于获取ETF成分股的PE/PB，然后按持仓权重加权计算ETF估值
- 百度有：总市值、市盈率(TTM)、市盈率(静)、市净率、市现率 五个指标

### 实现路径（通过持仓加权估算ETF估值）

```python
# 步骤1: 获取ETF持仓（待进一步确认可用接口）
holdings = get_etf_holdings(etf_code)  # 待实现

# 步骤2: 逐个获取成分股PE/PB
for stock in holdings:
    pe = ak.stock_zh_valuation_baidu(symbol=stock.code, indicator='市盈率(TTM)')
    pb = ak.stock_zh_valuation_baidu(symbol=stock.code, indicator='市净率')

# 步骤3: 按权重加权
etf_pe = sum(h.weight * pe for h in holdings)
etf_pb = sum(h.weight * pb for h in holdings)
```

---

## 3. 新浪财经 hq.sinajs.cn

### 测试结果
```
Status: 200
Response: var hq_str_s_sh510300="沪深300ETF华泰柏瑞,4.765,-0.022,-0.46,12650379,605931";
```
- 仅返回价格、涨跌幅、成交量等基础行情
- **没有PE/PB字段**

---

## 4. 东方财富 push2 API

### 测试结果
- ConnectionError: Remote end closed connection without response
- 当前网络环境无法直接访问 eastmoney push2 端口

---

## 5. 其他 akshare 函数失败状态

| 函数 | 状态 | 错误 |
|------|------|------|
| stock_a_all_pb | ❌ | AttributeError: 'NoneType' object has no attribute 'attrs' |
| stock_market_pe_lg | ❌ | 同上 |
| stock_market_pb_lg | ❌ | 同上 |
| stock_index_pb_lg | ❌ | 同上 |
| stock_index_pe_lg | ❌ | 同上 |
| stock_a_ttm_lyr | ❌ | 同上 |
| fund_portfolio_hold_em | ❌ | JSONDecodeError |
| fund_individual_basic_info_xq | ❌ | KeyError: 'data' |
| fund_individual_analysis_xq | ✅ | 返回风险收益指标，无PE/PB |

---

## 6. Tushare / BaoStock

### Tushare
- 已安装成功 (v1.4.29)，但 pro API 需要 token 认证
- 未进行完整测试

### BaoStock
- pip install 失败（清华源返回403），未安装
- 如需使用需解决依赖问题

---

## 推荐实施方案

### 方案A：PE用中证指数网 + PB从持仓成分股加权估算

**优点**: PE数据权威可靠，PB可通过持仓成分股计算  
**缺点**: PB计算需要额外步骤和更多API调用  

```python
# PE部分
from akshare import stock_zh_index_value_csindex

def get_index_pe(code):
    """获取指数的PE估值"""
    df = stock_zh_index_value_csindex(symbol=code)
    latest = df.iloc[0]
    return latest['市盈率1']  # TTM PE

# PB部分（概念）
def estimate_etf_pb_from_holdings(etf_code):
    """通过成分股持仓加权估算ETF的PB"""
    # TODO: 实现获取ETF持仓的接口
    # TODO: 逐个获取成分股PB
    # TODO: 加权汇总
    pass
```

### 方案B：纯通过单股估值聚合

如果无法获取ETF持仓数据，可以考虑：
1. 固定维护主流ETF的成分股权重表
2. 每个交易日批量查询所有成分股PE/PB
3. 加权得到ETF的估值

---

## 结论

**PE数据可以直接使用**：`stock_zh_index_value_csindex` 能覆盖10+个主流宽基和行业ETF的底层指数PE数据，权威且稳定。

**PB数据需要通过成分股加权计算**，或寻找其他专门提供ETF估值的接口。建议下一步：
1. 优先修复/使用akshare的基金持仓接口
2. 或直接解析东方财富/天天基金的网页获取持仓数据
3. 实现PE+PB的聚合估值系统
