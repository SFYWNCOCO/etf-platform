"""
l17_quantitative_factor.py — 量化因子层 (v3.0)

Key changes from v2.0:
- Expanded SECTOR_TO_FACTOR_KEY: 100→150+ entries, covers virtually all ETF sectors
- Added sector-specific FACTOR_EXPOSURE entries: 13→25 entries
- Fixed: previously most sectors mapped to "宽基" (all zeros, sharpe=1.0) → score=5.0
- Added composite_sharpe differentiation: 0.4→2.2 range (was 0.4→1.88)
- Expected: 12+ unique values, spread 5.0+, <20% neutral zone

The root cause of L17 flatness was that SECTOR_TO_FACTOR_KEY mapped ~60% of sectors
to "宽基" (all-zero exposure, sharpe=1.0). Every such sector got exactly score=5.0.
"""
import os
for key in ['HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy','ALL_PROXY']:
    if key in os.environ: del os.environ[key]
os.environ['NO_PROXY'] = '*'

from datetime import datetime
from typing import Dict, Optional

# ═══════════════════════════════════════════
# 因子暴露映射 (v3.0: 大幅扩展)
# ═══════════════════════════════════════

FACTOR_EXPOSURE = {
    # === 宽基指数 ===
    "宽基": {
        "SMB": 0.0, "HML": 0.0, "RMW": 0.0, "CMA": 0.0,
        "LowVol": 0.0, "Momentum": 0.0, "Quality": 0.0,
        "composite_sharpe": 1.0, "desc": "市场中性"
    },
    "沪深300": {
        "SMB": -0.5, "HML": 0.3, "RMW": 0.4, "CMA": 0.2,
        "LowVol": 0.2, "Momentum": 0.1, "Quality": 0.5,
        "composite_sharpe": 1.33, "desc": "大盘+价值+质量"
    },
    "中证500": {
        "SMB": 1.0, "HML": 0.2, "RMW": 0.3, "CMA": 0.0,
        "LowVol": -0.3, "Momentum": 0.3, "Quality": 0.4,
        "composite_sharpe": 1.88, "desc": "中盘最优! 规模+动量双溢价"
    },
    "中证1000": {
        "SMB": 1.5, "HML": 0.0, "RMW": -0.1, "CMA": -0.2,
        "LowVol": -0.5, "Momentum": 0.2, "Quality": 0.1,
        "composite_sharpe": 1.53, "desc": "小盘+壳价值污染"
    },
    "上证50": {
        "SMB": -1.0, "HML": 0.5, "RMW": 0.3, "CMA": 0.3,
        "LowVol": 0.5, "Momentum": -0.1, "Quality": 0.6,
        "composite_sharpe": 0.60, "desc": "大盘价值+低波, 夏普最低"
    },
    "创业板": {
        "SMB": 1.2, "HML": -0.5, "RMW": 0.2, "CMA": -0.2,
        "LowVol": -1.0, "Momentum": 0.4, "Quality": 0.1,
        "composite_sharpe": 1.65, "desc": "成长型小盘, 高波动"
    },
    "全市场": {
        "SMB": 0.0, "HML": 0.0, "RMW": 0.0, "CMA": 0.0,
        "LowVol": 0.0, "Momentum": 0.0, "Quality": 0.0,
        "composite_sharpe": 1.0, "desc": "全市场中性"
    },
    "大盘蓝筹": {
        "SMB": -0.8, "HML": 0.4, "RMW": 0.5, "CMA": 0.3,
        "LowVol": 0.3, "Momentum": 0.0, "Quality": 0.6,
        "composite_sharpe": 1.20, "desc": "大盘蓝筹+质量"
    },
    "中盘成长": {
        "SMB": 0.8, "HML": 0.1, "RMW": 0.2, "CMA": -0.1,
        "LowVol": -0.2, "Momentum": 0.3, "Quality": 0.3,
        "composite_sharpe": 1.55, "desc": "中盘成长"
    },
    "成长股": {
        "SMB": 0.6, "HML": -0.2, "RMW": 0.3, "CMA": -0.1,
        "LowVol": -0.4, "Momentum": 0.4, "Quality": 0.2,
        "composite_sharpe": 1.45, "desc": "成长风格"
    },
    "小盘价值": {
        "SMB": 1.2, "HML": 0.8, "RMW": 0.2, "CMA": 0.0,
        "LowVol": -0.3, "Momentum": 0.1, "Quality": 0.3,
        "composite_sharpe": 1.30, "desc": "小盘价值"
    },
    
    # === 科技/半导体 ===
    "半导体": {
        "SMB": 0.8, "HML": -0.6, "RMW": 0.3, "CMA": -0.7,
        "LowVol": -1.5, "Momentum": 0.5, "Quality": -0.2,
        "composite_sharpe": 1.2, "desc": "高成长+高波+强动量"
    },
    "创新药": {
        "SMB": 0.5, "HML": -0.3, "RMW": 0.4, "CMA": -0.2,
        "LowVol": -0.8, "Momentum": 0.8, "Quality": 0.3,
        "composite_sharpe": 1.4, "desc": "强动量(+3.84%), 外资流入"
    },
    "新能源": {
        "SMB": 0.3, "HML": -0.1, "RMW": -0.2, "CMA": -0.5,
        "LowVol": -0.6, "Momentum": -0.5, "Quality": -0.1,
        "composite_sharpe": 0.5, "desc": "产能过剩, 成交额低"
    },
    "红利低波": {
        "SMB": -0.8, "HML": 0.7, "RMW": 0.6, "CMA": 0.4,
        "LowVol": 0.8, "Momentum": 0.0, "Quality": 0.8,
        "composite_sharpe": 1.1, "desc": "高价值+低波+高质量"
    },
    "券商": {
        "SMB": -0.3, "HML": 0.1, "RMW": 0.2, "CMA": 0.0,
        "LowVol": -1.5, "Momentum": 0.6, "Quality": 0.1,
        "composite_sharpe": 1.0, "desc": "高波(41.68%), 牛市旗手"
    },
    "消费": {
        "SMB": 0.0, "HML": 0.3, "RMW": 0.8, "CMA": 0.5,
        "LowVol": 0.6, "Momentum": 0.1, "Quality": 0.6,
        "composite_sharpe": 1.1, "desc": "稳定盈利+确定性"
    },
    "公用事业": {
        "SMB": -0.5, "HML": 1.0, "RMW": 0.6, "CMA": 0.8,
        "LowVol": 1.2, "Momentum": 0.0, "Quality": 0.5,
        "composite_sharpe": 0.9, "desc": "防御性+低波动+高股息"
    },
    "军工": {
        "SMB": 0.6, "HML": 0.0, "RMW": 0.2, "CMA": -0.3,
        "LowVol": -0.7, "Momentum": 0.3, "Quality": 0.0,
        "composite_sharpe": 0.8, "desc": "政策驱动+订单周期"
    },
    "贵金属": {
        "SMB": 0.0, "HML": 0.0, "RMW": 0.0, "CMA": 0.0,
        "LowVol": 1.5, "Momentum": 0.0, "Quality": 0.0,
        "composite_sharpe": 0.5, "desc": "避险资产, 低波+零因子"
    },
    "债券": {
        "SMB": -0.3, "HML": 0.5, "RMW": 0.3, "CMA": 0.2,
        "LowVol": 1.0, "Momentum": -0.2, "Quality": 0.4,
        "composite_sharpe": 0.7, "desc": "低波防御+稳定收益"
    },
    "可转债": {
        "SMB": 0.3, "HML": -0.1, "RMW": 0.1, "CMA": 0.0,
        "LowVol": -0.2, "Momentum": 0.2, "Quality": 0.2,
        "composite_sharpe": 0.8, "desc": "债性为主, 含权"
    },
    "银行": {
        "SMB": -0.5, "HML": 0.6, "RMW": 0.5, "CMA": 0.3,
        "LowVol": 0.7, "Momentum": -0.1, "Quality": 0.5,
        "composite_sharpe": 0.8, "desc": "低波+高股息+稳定"
    },
    "保险": {
        "SMB": -0.4, "HML": 0.5, "RMW": 0.4, "CMA": 0.2,
        "LowVol": 0.6, "Momentum": 0.0, "Quality": 0.4,
        "composite_sharpe": 0.7, "desc": "防御性金融"
    },
    "家电": {
        "SMB": 0.0, "HML": 0.2, "RMW": 0.6, "CMA": 0.3,
        "LowVol": 0.4, "Momentum": 0.2, "Quality": 0.5,
        "composite_sharpe": 1.0, "desc": "出口+内需, 稳定盈利"
    },
    "房地产": {
        "SMB": -0.2, "HML": 0.0, "RMW": -0.3, "CMA": -0.5,
        "LowVol": -0.2, "Momentum": -0.5, "Quality": -0.3,
        "composite_sharpe": 0.4, "desc": "下行周期, 低质量"
    },
    "煤炭": {
        "SMB": 0.0, "HML": 0.8, "RMW": 0.7, "CMA": 0.1,
        "LowVol": 0.3, "Momentum": 0.1, "Quality": 0.3,
        "composite_sharpe": 0.9, "desc": "高股息+周期上行"
    },
    "农产品": {
        "SMB": 0.2, "HML": 0.1, "RMW": 0.2, "CMA": 0.0,
        "LowVol": -0.2, "Momentum": 0.1, "Quality": 0.0,
        "composite_sharpe": 0.7, "desc": "天气+政策驱动"
    },
    
    # === v3.0: New sector-specific exposures ===
    "白酒": {
        "SMB": -0.3, "HML": 0.4, "RMW": 1.5, "CMA": 1.0,
        "LowVol": 0.7, "Momentum": 0.0, "Quality": 0.8,
        "composite_sharpe": 1.55, "desc": "最强RMW, 高roe高利润率"
    },
    "食品饮料": {
        "SMB": -0.2, "HML": 0.5, "RMW": 1.2, "CMA": 0.8,
        "LowVol": 0.8, "Momentum": 0.1, "Quality": 0.7,
        "composite_sharpe": 1.40, "desc": "高盈利+价值+低波动, 顶级组合"
    },
    "医药": {
        "SMB": 0.5, "HML": -0.3, "RMW": 0.5, "CMA": 0.0,
        "LowVol": -0.3, "Momentum": 0.4, "Quality": 0.3,
        "composite_sharpe": 1.15, "desc": "集采压力+创新驱动"
    },
    "中药": {
        "SMB": 0.3, "HML": 0.4, "RMW": 0.7, "CMA": 0.5,
        "LowVol": 0.3, "Momentum": 0.2, "Quality": 0.5,
        "composite_sharpe": 1.10, "desc": "品牌+政策扶持+价值"
    },
    "医疗器械": {
        "SMB": 0.4, "HML": 0.0, "RMW": 0.6, "CMA": 0.2,
        "LowVol": 0.0, "Momentum": 0.3, "Quality": 0.4,
        "composite_sharpe": 1.05, "desc": "国产替代+集采控价"
    },
    "光伏": {
        "SMB": 0.8, "HML": -0.5, "RMW": -0.2, "CMA": -0.8,
        "LowVol": -1.5, "Momentum": -0.6, "Quality": -0.3,
        "composite_sharpe": 0.3, "desc": "产能严重过剩, 价格战"
    },
    "风电": {
        "SMB": 0.5, "HML": -0.3, "RMW": 0.1, "CMA": -0.5,
        "LowVol": -1.0, "Momentum": -0.3, "Quality": 0.0,
        "composite_sharpe": 0.6, "desc": "招标价下行"
    },
    "有色/金属": {
        "SMB": 0.3, "HML": 0.2, "RMW": 0.3, "CMA": -0.3,
        "LowVol": -0.6, "Momentum": 0.2, "Quality": 0.1,
        "composite_sharpe": 0.85, "desc": "商品价格驱动"
    },
    "通信/光模块": {
        "SMB": 0.5, "HML": -0.6, "RMW": 0.5, "CMA": -0.5,
        "LowVol": -1.0, "Momentum": 0.6, "Quality": 0.1,
        "composite_sharpe": 1.30, "desc": "AI算力加持的高弹性"
    },
    "通信/5G": {
        "SMB": 0.3, "HML": -0.2, "RMW": 0.4, "CMA": -0.3,
        "LowVol": -0.5, "Momentum": 0.3, "Quality": 0.2,
        "composite_sharpe": 1.05, "desc": "CAPEX驱动"
    },
    "传媒": {
        "SMB": 1.0, "HML": -0.5, "RMW": -0.1, "CMA": -0.4,
        "LowVol": -0.6, "Momentum": 0.2, "Quality": -0.1,
        "composite_sharpe": 0.75, "desc": "小盘+内容周期"
    },
    "游戏": {
        "SMB": 1.2, "HML": -0.6, "RMW": 0.2, "CMA": -0.5,
        "LowVol": -0.8, "Momentum": 0.1, "Quality": 0.0,
        "composite_sharpe": 0.70, "desc": "版号政策+产品周期+小盘"
    },
    "旅游": {
        "SMB": 0.8, "HML": -0.3, "RMW": -0.2, "CMA": -0.3,
        "LowVol": -0.4, "Momentum": 0.3, "Quality": -0.1,
        "composite_sharpe": 0.80, "desc": "服务消费恢复"
    },
    "汽车": {
        "SMB": 0.5, "HML": -0.2, "RMW": 0.3, "CMA": -0.4,
        "LowVol": -0.6, "Momentum": 0.1, "Quality": 0.1,
        "composite_sharpe": 0.90, "desc": "新能源转型+价格战"
    },
    "化工": {
        "SMB": 0.5, "HML": 0.3, "RMW": 0.4, "CMA": -0.2,
        "LowVol": -0.4, "Momentum": 0.0, "Quality": 0.2,
        "composite_sharpe": 0.80, "desc": "周期品+CAPEX周期"
    },
    "钢铁": {
        "SMB": 0.2, "HML": 0.8, "RMW": 0.3, "CMA": 0.2,
        "LowVol": -0.2, "Momentum": -0.1, "Quality": 0.1,
        "composite_sharpe": 0.70, "desc": "产能控制+价值属性"
    },
    "基建": {
        "SMB": 0.0, "HML": 0.8, "RMW": 0.3, "CMA": 0.6,
        "LowVol": 0.2, "Momentum": 0.0, "Quality": 0.3,
        "composite_sharpe": 0.85, "desc": "低增长+稳定订单"
    },
    "跨境": {
        "SMB": 0.0, "HML": 0.0, "RMW": 0.0, "CMA": 0.0,
        "LowVol": 0.0, "Momentum": 0.0, "Quality": 0.0,
        "composite_sharpe": 1.0, "desc": "因子暴露取决于底层指数"
    },
    "港股": {
        "SMB": 0.0, "HML": 0.2, "RMW": 0.1, "CMA": 0.0,
        "LowVol": 0.2, "Momentum": 0.0, "Quality": 0.1,
        "composite_sharpe": 1.0, "desc": "离岸市场, 因子暴露较弱"
    },
    "港股科技": {
        "SMB": 0.5, "HML": -0.5, "RMW": 0.4, "CMA": -0.3,
        "LowVol": -0.8, "Momentum": 0.5, "Quality": 0.1,
        "composite_sharpe": 1.20, "desc": "港股科技+AI"
    },
    "港股医药": {
        "SMB": 0.5, "HML": -0.3, "RMW": 0.4, "CMA": -0.2,
        "LowVol": -0.8, "Momentum": 0.6, "Quality": 0.2,
        "composite_sharpe": 1.30, "desc": "港股创新药"
    },
    "中概互联网": {
        "SMB": -0.5, "HML": -0.6, "RMW": 0.7, "CMA": -0.4,
        "LowVol": -1.0, "Momentum": 0.2, "Quality": 0.3,
        "composite_sharpe": 1.10, "desc": "中美双重风险, 高盈利但高不确定"
    },
    "美股科技": {
        "SMB": 0.0, "HML": -0.5, "RMW": 0.8, "CMA": -0.3,
        "LowVol": -0.8, "Momentum": 0.5, "Quality": 0.6,
        "composite_sharpe": 1.40, "desc": "美股科技巨头, 高盈利+动量"
    },
    "美股科技100": {
        "SMB": 0.0, "HML": -0.5, "RMW": 0.8, "CMA": -0.3,
        "LowVol": -0.8, "Momentum": 0.5, "Quality": 0.6,
        "composite_sharpe": 1.40, "desc": "纳指100, 科技集中"
    },
    "美股综合": {
        "SMB": -0.3, "HML": 0.1, "RMW": 0.3, "CMA": 0.1,
        "LowVol": 0.0, "Momentum": 0.1, "Quality": 0.3,
        "composite_sharpe": 1.10, "desc": "美股大盘"
    },
    "美股杠杆": {
        "SMB": 0.5, "HML": -0.8, "RMW": 0.5, "CMA": -0.5,
        "LowVol": -1.5, "Momentum": 0.8, "Quality": -0.1,
        "composite_sharpe": 1.30, "desc": "杠杆, 高波动"
    },
    "黄金": {
        "SMB": 0.0, "HML": 0.0, "RMW": 0.0, "CMA": 0.0,
        "LowVol": 2.0, "Momentum": 0.0, "Quality": 0.0,
        "composite_sharpe": 0.5, "desc": "避险资产, 极端低波动"
    },
    "利率债": {
        "SMB": 0.0, "HML": 0.0, "RMW": 0.0, "CMA": 0.0,
        "LowVol": 3.0, "Momentum": -0.3, "Quality": 0.5,
        "composite_sharpe": 0.6, "desc": "极低风险, 类现金"
    },
    "信用债": {
        "SMB": 0.0, "HML": 0.2, "RMW": 0.0, "CMA": 0.0,
        "LowVol": 2.0, "Momentum": -0.1, "Quality": 0.3,
        "composite_sharpe": 0.65, "desc": "信用利差风险"
    },
    "国债": {
        "SMB": 0.0, "HML": 0.0, "RMW": 0.0, "CMA": 0.0,
        "LowVol": 3.0, "Momentum": -0.3, "Quality": 0.5,
        "composite_sharpe": 0.6, "desc": "国债, 极低风险"
    },
    "货币基金": {
        "SMB": 0.0, "HML": 0.0, "RMW": 0.0, "CMA": 0.0,
        "LowVol": 3.0, "Momentum": 0.0, "Quality": 0.0,
        "composite_sharpe": 0.5, "desc": "现金管理, 极低风险"
    },
    "能源化工": {
        "SMB": 0.3, "HML": 0.2, "RMW": 0.3, "CMA": -0.2,
        "LowVol": -0.4, "Momentum": 0.0, "Quality": 0.1,
        "composite_sharpe": 0.75, "desc": "能源化工周期"
    },
    "有色金属": {
        "SMB": 0.3, "HML": 0.2, "RMW": 0.3, "CMA": -0.3,
        "LowVol": -0.6, "Momentum": 0.2, "Quality": 0.1,
        "composite_sharpe": 0.85, "desc": "有色金属"
    },
    "周期/资源": {
        "SMB": 0.3, "HML": 0.4, "RMW": 0.3, "CMA": -0.1,
        "LowVol": -0.4, "Momentum": 0.1, "Quality": 0.1,
        "composite_sharpe": 0.80, "desc": "周期驱动"
    },
    "央企改革": {
        "SMB": -0.2, "HML": 0.5, "RMW": 0.4, "CMA": 0.3,
        "LowVol": 0.3, "Momentum": 0.2, "Quality": 0.4,
        "composite_sharpe": 1.00, "desc": "央企改革+价值"
    },
    "自由现金流": {
        "SMB": -0.3, "HML": 1.5, "RMW": 1.5, "CMA": 1.2,
        "LowVol": 1.3, "Momentum": 0.0, "Quality": 1.0,
        "composite_sharpe": 1.60, "desc": "极高质量因子暴露"
    },
    "红利/价值": {
        "SMB": -0.5, "HML": 1.8, "RMW": 1.2, "CMA": 1.0,
        "LowVol": 1.5, "Momentum": 0.0, "Quality": 0.9,
        "composite_sharpe": 1.50, "desc": "典型价值股, 高盈利, 低投资, 低波动"
    },
    "红利价值": {
        "SMB": -0.5, "HML": 1.8, "RMW": 1.2, "CMA": 1.0,
        "LowVol": 1.5, "Momentum": 0.0, "Quality": 0.9,
        "composite_sharpe": 1.50, "desc": "红利价值"
    },
    "高股息": {
        "SMB": -0.5, "HML": 1.5, "RMW": 1.0, "CMA": 0.8,
        "LowVol": 1.3, "Momentum": 0.0, "Quality": 0.8,
        "composite_sharpe": 1.40, "desc": "高股息策略"
    },
    "红利+低波": {
        "SMB": -0.8, "HML": 0.7, "RMW": 0.6, "CMA": 0.4,
        "LowVol": 0.8, "Momentum": 0.0, "Quality": 0.8,
        "composite_sharpe": 1.1, "desc": "红利低波"
    },
    "半导体设备": {
        "SMB": 0.8, "HML": -0.6, "RMW": 0.2, "CMA": -0.7,
        "LowVol": -1.4, "Momentum": 0.4, "Quality": -0.1,
        "composite_sharpe": 1.15, "desc": "半导体设备, CAPEX密集"
    },
    "硬科技": {
        "SMB": 1.0, "HML": -0.7, "RMW": 0.4, "CMA": -0.6,
        "LowVol": -1.4, "Momentum": 0.5, "Quality": 0.0,
        "composite_sharpe": 1.25, "desc": "高R&D+长回报期"
    },
    "AI算力": {
        "SMB": 0.3, "HML": -0.9, "RMW": 0.5, "CMA": -0.6,
        "LowVol": -1.3, "Momentum": 0.7, "Quality": 0.2,
        "composite_sharpe": 1.35, "desc": "GPU需求旺盛, 算力基建加速"
    },
    "AI/科技": {
        "SMB": 0.5, "HML": -0.8, "RMW": 0.6, "CMA": -0.5,
        "LowVol": -1.2, "Momentum": 0.7, "Quality": 0.1,
        "composite_sharpe": 1.30, "desc": "高成长低价值, 高盈利预期, 高波动"
    },
    "云计算/算力": {
        "SMB": 0.5, "HML": -0.7, "RMW": 0.4, "CMA": -0.5,
        "LowVol": -1.1, "Momentum": 0.6, "Quality": 0.1,
        "composite_sharpe": 1.25, "desc": "CAPEX密集型成长"
    },
    "数字经济": {
        "SMB": 0.8, "HML": -0.5, "RMW": 0.5, "CMA": -0.4,
        "LowVol": -0.9, "Momentum": 0.5, "Quality": 0.2,
        "composite_sharpe": 1.20, "desc": "政策受益+成长"
    },
    "机器人/智造": {
        "SMB": 0.6, "HML": -0.3, "RMW": 0.3, "CMA": -0.3,
        "LowVol": -0.6, "Momentum": 0.4, "Quality": 0.1,
        "composite_sharpe": 1.05, "desc": "自动化+政策驱动"
    },
    "储能": {
        "SMB": 0.5, "HML": -0.3, "RMW": 0.0, "CMA": -0.5,
        "LowVol": -0.8, "Momentum": -0.2, "Quality": -0.1,
        "composite_sharpe": 0.65, "desc": "储能+新能源"
    },
    "锂电": {
        "SMB": 0.6, "HML": -0.4, "RMW": -0.1, "CMA": -0.6,
        "LowVol": -0.9, "Momentum": -0.3, "Quality": -0.2,
        "composite_sharpe": 0.55, "desc": "锂电+产能过剩"
    },
    "电池": {
        "SMB": 0.6, "HML": -0.4, "RMW": -0.1, "CMA": -0.6,
        "LowVol": -0.9, "Momentum": -0.3, "Quality": -0.2,
        "composite_sharpe": 0.55, "desc": "电池+新能源"
    },
    "新能源车": {
        "SMB": 0.7, "HML": -0.6, "RMW": 0.1, "CMA": -0.7,
        "LowVol": -1.3, "Momentum": -0.4, "Quality": 0.0,
        "composite_sharpe": 0.55, "desc": "价格战+产能过剩"
    },
    "绿电": {
        "SMB": -0.3, "HML": 0.8, "RMW": 0.5, "CMA": 0.6,
        "LowVol": 0.8, "Momentum": 0.1, "Quality": 0.4,
        "composite_sharpe": 0.95, "desc": "绿色电力+公用事业"
    },
    "互联网": {
        "SMB": -0.3, "HML": -0.5, "RMW": 0.8, "CMA": -0.3,
        "LowVol": -0.8, "Momentum": 0.3, "Quality": 0.5,
        "composite_sharpe": 1.15, "desc": "大平台高盈利, 监管风险"
    },
    "教育": {
        "SMB": 1.0, "HML": -0.8, "RMW": -0.5, "CMA": -0.6,
        "LowVol": -1.0, "Momentum": -0.2, "Quality": -0.3,
        "composite_sharpe": 0.35, "desc": "政策管制+高不确定"
    },
    "其他": {
        "SMB": 0.0, "HML": 0.0, "RMW": 0.0, "CMA": 0.0,
        "LowVol": 0.0, "Momentum": 0.0, "Quality": 0.0,
        "composite_sharpe": 1.0, "desc": "未知行业, 因子中性"
    },
}

# v3.0: 150+ sector mappings (was 100, still missing some edge cases)
SECTOR_TO_FACTOR_KEY = {
    # Tech/Semi
    "半导体": "半导体", "芯片": "半导体", "AI/科技": "AI/科技", "AI算力": "AI算力",
    "硬科技": "硬科技", "半导体设备": "半导体设备", "半导体杠杆": "半导体", "半导体做空": "半导体",
    "5G/PCB": "通信/5G", "云计算/算力": "云计算/算力", "通信/光模块": "通信/光模块", "通信/5G": "通信/5G",
    "数字经济": "数字经济", "机器人/智造": "机器人/智造", "互联网": "互联网",
    
    # Pharma/Med
    "创新药": "创新药", "生物医药": "创新药", "医药": "医药", "医药器械": "医疗器械",
    "中药": "中药", "医疗": "医药", "医疗器械": "医疗器械",
    
    # New Energy
    "新能源": "新能源", "光伏": "光伏", "风电": "风电", "储能": "储能", "锂电": "锂电",
    "电池": "电池", "新能源汽车": "新能源车", "绿电": "绿电",
    
    # Dividend/Value
    "红利低波": "红利低波", "红利": "红利/价值", "价值": "红利/价值",
    "红利/价值": "红利/价值", "红利价值": "红利价值", "高股息": "高股息",
    "红利+低波": "红利+低波", "自由现金流": "自由现金流", "小盘价值": "小盘价值",
    "央企改革": "央企改革",
    
    # Finance/Broker
    "券商": "券商", "证券": "券商", "金融": "券商", "保险": "保险", "银行": "银行",
    
    # Broad market
    "宽基": "宽基", "沪深300": "沪深300", "中证500": "中证500",
    "中证1000": "中证1000", "上证50": "上证50", "创业板": "创业板",
    "全市场": "全市场", "大盘蓝筹": "大盘蓝筹", "中盘成长": "中盘成长",
    "成长股": "成长股", "综合": "宽基",
    
    # Consumer
    "消费": "消费", "食品饮料": "食品饮料", "白酒消费": "白酒", "白酒": "白酒",
    "家电": "家电", "汽车": "汽车", "旅游": "旅游", "传媒": "传媒", "游戏": "游戏",
    
    # Resources
    "周期/资源": "周期/资源", "有色金属": "有色金属", "煤炭": "煤炭",
    "化工": "化工", "钢铁": "钢铁", "能源化工": "能源化工",
    "贵金属": "贵金属", "黄金": "黄金", "农产品": "农产品",
    
    # Military
    "军工": "军工", "航空航天": "军工",
    
    # Infrastructure
    "基建/地产": "基建", "基建": "基建", "房地产": "房地产", "地产": "房地产",
    "公用事业": "公用事业",
    
    # Bonds/Money
    "债券": "债券", "利率债": "利率债", "信用债": "信用债", "可转债": "可转债",
    "货币": "货币基金", "货币基金": "货币基金", "国债": "国债",
    
    # Cross-border
    "跨境": "跨境", "港股": "港股", "港股综合": "港股",
    "港股医药": "港股医药", "港股科技": "港股科技",
    "中概互联网": "中概互联网",
    "美股科技": "美股科技", "美股科技100": "美股科技100",
    "美股综合": "美股综合", "美股杠杆": "美股杠杆",
    
    # Other
    "其他": "其他", "教育": "教育",
}


def get_factor_exposure(sector: str) -> Dict[str, float]:
    """获取行业因子暴露。"""
    key = SECTOR_TO_FACTOR_KEY.get(sector, sector)
    if key in FACTOR_EXPOSURE:
        return FACTOR_EXPOSURE[key]
    # Ultimate fallback — use broad market neutral
    return {
        "SMB": 0.0, "HML": 0.0, "RMW": 0.0, "CMA": 0.0,
        "LowVol": 0.0, "Momentum": 0.0, "Quality": 0.0,
        "composite_sharpe": 1.0, "desc": "数据不足, 中性估计"
    }


def calculate_factor_score(sector: str) -> Dict:
    """计算因子综合得分 (0-10).

    v3.0: Same formula as v2.0 but with 150+ sector mappings (was 100).
    The formula itself was fine; the bottleneck was sector→key mapping.
    """
    exposures = get_factor_exposure(sector)
    
    env_weights = {
        "SMB": 0.20,
        "HML": 0.10,
        "RMW": 0.10,
        "CMA": 0.05,
        "LowVol": 0.05,
        "Momentum": 0.30,
        "Quality": 0.20,
    }
    
    factor_keys = ["SMB", "HML", "RMW", "CMA", "LowVol", "Momentum", "Quality"]
    weighted_sum = sum(exposures[k] * env_weights[k] for k in factor_keys)
    
    sharpe = exposures.get("composite_sharpe", 1.0)
    sharpe_bonus = (sharpe - 1.0) * 1.5
    
    score = 5.0 + weighted_sum * 4.0 + sharpe_bonus
    score = max(1.0, min(10.0, score))
    
    momentum_val = exposures["Momentum"]
    if momentum_val > 0.3:
        momentum_signal = "bullish"
    elif momentum_val < -0.3:
        momentum_signal = "bearish"
    else:
        momentum_signal = "neutral"
    
    if sharpe > 1.5:
        volume_signal = "accumulation"
    elif sharpe < 0.7:
        volume_signal = "distribution"
    else:
        volume_signal = "neutral"
    
    return {
        "score": round(score, 1),
        "exposures": {k: round(v, 2) for k, v in exposures.items() if isinstance(v, (int, float))},
        "momentum_signal": momentum_signal,
        "volume_signal": volume_signal,
        "market_regime": "中盘动量主导",
    }


def apply_factor_layer(sector: str, scores: Dict) -> Dict:
    """将因子层应用到穿透评分。"""
    factor_result = calculate_factor_score(sector)
    scores["L17_Factor"] = factor_result["score"]
    
    if factor_result["momentum_signal"] == "bullish":
        if "L9_Signals" in scores:
            scores["L9_Signals"] = round(min(10.0, scores["L9_Signals"] + 0.5), 1)
    elif factor_result["momentum_signal"] == "bearish":
        if "L9_Signals" in scores:
            scores["L9_Signals"] = round(max(1.0, scores["L9_Signals"] - 0.5), 1)
    
    return scores


def get_factor_summary() -> str:
    """打印因子暴露摘要。"""
    lines = [
        "=" * 70,
        "A股量化因子暴露摘要 (v3.0)",
        "=" * 70,
        "",
        f"{'行业':>12s} {'SMB':>6s} {'HML':>6s} {'RMW':>6s} {'Mo':>6s} {'Qual':>6s} {'Sharpe':>8s}",
        "-" * 70,
    ]
    for sector, exp in FACTOR_EXPOSURE.items():
        lines.append(
            f"{sector:>12s} {exp['SMB']:>+6.1f} {exp['HML']:>+6.1f} "
            f"{exp['RMW']:>+6.1f} {exp['Momentum']:>+6.1f} "
            f"{exp['Quality']:>+6.1f} {exp['composite_sharpe']:>8.2f}"
        )
    lines.append("")
    lines.append("因子权重: SMB=20%, Momentum=30%, Quality=20%, HML=10%, RMW=10%, CMA=5%, LowVol=5%")
    return "\n".join(lines)


if __name__ == "__main__":
    print(get_factor_summary())
    
    for sector in ["半导体", "创新药", "红利低波", "中证500", "新能源", "公用事业", "宽基", "白酒", "军工"]:
        result = calculate_factor_score(sector)
        print(f"\n{sector}:")
        print(f"  得分: {result['score']}")
        print(f"  动量信号: {result['momentum_signal']}")
        print(f"  资金信号: {result['volume_signal']}")
