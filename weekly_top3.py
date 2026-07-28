#!/usr/bin/env python3
"""weekly_top3.py v16.18 — 周度Top3 ETF推荐 (全量实时行情驱动)

v16.18: 行业映射覆盖587→592只 + 市场时段感知 + 方向感知评分 + pipeline集成修复
"""
import json, sys
from pathlib import Path
from datetime import datetime, time

_HERE = Path(__file__).resolve().parent
_SRC = _HERE / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def _check_market_state():
    """检测市场状态"""
    now = datetime.now()
    wd = now.weekday()
    t = now.time()
    
    if wd >= 5:
        return "weekend", "周末休市"
    if t < time(9, 30):
        return "pre_market", "盘前"
    if time(9, 30) <= t < time(11, 30):
        return "trading_morning", "早盘交易中"
    if time(11, 30) <= t < time(13, 0):
        return "lunch_break", "午休"
    if time(13, 0) <= t < time(15, 0):
        return "trading_afternoon", "午盘交易中"
    if time(15, 0) <= t < time(20, 0):
        return "post_market", "已收盘(Sina返回收盘价)"
    return "night", "夜间(Sina返回收盘价)"


def _get_live_data():
    """获取全量实时行情+行业动量"""
    from etf_platform.data.live_price_bridge import fetch_live_prices, get_sector_momentum, _build_code_map
    codes = list(_build_code_map().keys())
    
    print(f"📡 获取全量 {len(codes)} 只ETF实时价格 (Sina)...")
    prices = fetch_live_prices(codes)
    live_count = prices["_meta"]["count"]
    print(f"   ✅ {live_count} 只获取成功")
    
    sectors = get_sector_momentum(prices)
    return prices, sectors


def _pick_top3(prices, sectors, risk="balanced"):
    """v16.18: 方向感知 + 多因子综合评分选Top3"""
    candidates = []
    
    for code, data in prices.items():
        if code.startswith("_"):
            continue
        name = data.get("name", "")
        change = data.get("change_pct", 0)
        volume = data.get("volume", 0)
        
        # 找对应行业动量
        sector_score = 5.0
        sector_momentum = 0.0
        matched_sector = "其他"
        # 先尝试 code→sector 精确匹配
        for sector, sdata in sectors.items():
            if sector.startswith("_"):
                continue
            if code in sdata.get("codes", []):
                sector_momentum = sdata["momentum_score"]
                sector_score = 5 + sector_momentum
                matched_sector = sector
                break
        # v16.18: 如果code查不到，用名称关键词兜底
        if matched_sector == "其他":
            for sector, keywords in {
                "半导体": ["半导体", "芯片", "半导"], "AI": ["AI", "人工智能", "算力", "软件", "计算机", "云计算", "大数据", "互联网"],
                "军工": ["军工", "国防", "航空航天", "卫星"], "新能源": ["新能源", "光伏", "锂电", "电池", "储能", "新能源车"],
                "医药": ["医药", "医疗", "生物", "创新药", "器械"], "消费": ["消费", "食品", "白酒", "家电", "汽车", "传媒"],
                "红利": ["红利", "股息", "高股息", "价值", "低波"], "金融": ["金融", "银行", "券商", "证券", "保险", "金科"],
                "港股": ["港股", "恒生", "中概", "港股通", "HK"], "通信": ["通信", "5G", "物联网", "电信"],
                "基建": ["基建", "电力", "公用", "能源", "煤炭", "电网"], "黄金": ["黄金", "有色"],
                "债券": ["债", "国债", "城投", "可转债", "货币", "日利"], "宽基": ["沪深", "中证", "A500", "创业板", "科创", "上证", "深证", "深100", "成长", "价值100", "创", "300", "500"],
                "机器人": ["机器人", "机械"], "纳指": ["纳指", "纳斯达克", "标普", "海外"],
                "化工": ["化工", "石化", "新材料"], "跨境": ["跨境", "QDII", "全球"],
                "现金流": ["现金流", "自由现金"],
            }.items():
                if any(kw in name for kw in keywords):
                    matched_sector = sector
                    sector_momentum = sectors.get(sector, {}).get("momentum_score", 0)
                    sector_score = 5 + sector_momentum
                    break
        # 方向感知评分 (v16.19 校准):
        # - 领涨(+change): 趋势强度 = |change|*0.6 + sector_momentum*0.3 + volume*0.1
        # - 超跌(-change): 反转机会 = min(|change|*0.2, 4) + max(0, -sector_momentum)*0.3 + volume*0.3
        #   超跌得分上限=7 (防止暴跌过度奖励)
        # - 平盘: 中性 = sector_momentum*0.5 + volume*0.5
        volume_score = min(volume / 500_000_000, 1.0) * 10
        
        if change > 0.5:
            composite = abs(change) * 0.6 + sector_score * 0.3 + volume_score * 0.1
        elif change < -0.5:
            # 超跌: |change|最多贡献4分，行业动量不能为负拉分
            reversal = min(abs(change) * 0.2, 4)
            sector_bonus = max(0, -sector_momentum) * 0.3
            composite = reversal + sector_bonus + volume_score * 0.3
            composite = min(composite, 7.5)  # 上限
        else:
            composite = sector_score * 0.6 + volume_score * 0.4
        
        candidates.append({
            "code": code,
            "name": name,
            "price": data["price"],
            "change_pct": change,
            "sector": matched_sector,
            "sector_momentum": round(sector_momentum, 1),
            "composite": round(composite, 1),
            "volume": volume,
            "direction": "up" if change > 0 else "down",
        })
    
    # 去重 + 行业多样性（每行业最多2只）
    seen_names = set()
    sector_count = {}
    unique = []
    for c in sorted(candidates, key=lambda x: -x["composite"]):
        if c["name"] in seen_names:
            continue
        s = c["sector"]
        if sector_count.get(s, 0) >= 2:
            continue
        seen_names.add(c["name"])
        sector_count[s] = sector_count.get(s, 0) + 1
        unique.append(c)
    
    # 选Top3：至少覆盖2个行业，极端行情自动适配
    top3 = []
    up_picks = [c for c in unique if c["direction"] == "up"]
    down_picks = [c for c in unique if c["direction"] == "down"]
    
    # v16.18: 极端行情适配
    if not up_picks and not down_picks:
        top3 = unique[:3]  # 全平盘
    elif not up_picks:
        # 全跌：选最抗跌的
        top3 = sorted(down_picks, key=lambda x: -x["change_pct"])[:3]
    elif not down_picks:
        # 全涨：选最强的
        top3 = up_picks[:3]
    elif risk == "aggressive" and down_picks:
        top3 = up_picks[:1] + down_picks[:2]
    else:
        top3 = up_picks[:2] + down_picks[:1]
    
    return top3[:3]


def main():
    aggressive = "--aggressive" in sys.argv
    risk_label = "进取型" if aggressive else "均衡型"
    
    state, state_label = _check_market_state()
    freshness = "🟢 盘中实时" if "trading" in state else "🟡 收盘价" if "post" in state else "⚪ 休市"
    
    print(f"# 🦞 周度Top3推荐 ({risk_label})")
    print(f"*{datetime.now().strftime('%Y-%m-%d %H:%M')} | 市场: {state_label} | 数据: Sina实时行情 + 行业动量*")
    print(f"*数据新鲜度: {freshness}*\n")
    
    # 1. 获取全量实时数据
    prices, sectors = _get_live_data()
    
    # 2. 选Top3（纯行情驱动——实时价格+行业动量已足够）
    top3 = _pick_top3(prices, sectors, "aggressive" if aggressive else "balanced")
    
    for i, etf in enumerate(top3, 1):
        direction = "📈" if etf["change_pct"] > 0 else "📉"
        print(f"## {i}. {direction} {etf['code']} {etf['name']}")
        print(f"   行业: {etf['sector']} | 现价: {etf['price']} | 涨跌: {etf['change_pct']:+.2f}%")
        print(f"   行业动量: {etf['sector_momentum']:+.1f} | 综合评分: {etf['composite']}")
        
        # 理由
        reasons = []
        if etf["change_pct"] > 2:
            reasons.append(f"强势领涨{etf['change_pct']:+.2f}%")
        elif etf["change_pct"] > 0:
            reasons.append("逆势抗跌")
        elif etf["change_pct"] < -5:
            reasons.append(f"深度超跌{etf['change_pct']:+.2f}%，反弹弹性大")
        elif etf["change_pct"] < -1:
            reasons.append("回调充分")
        if etf["sector_momentum"] > 2:
            reasons.append(f"{etf['sector']}行业动量领涨")
        if etf["volume"] > 1_000_000_000:
            reasons.append("交投活跃(日成交>10亿)")
        print(f"   理由: {' | '.join(reasons) if reasons else '综合评分领先'}")
        print()
    
    # 行业动量全景
    print("---")
    print("*全市场行业动量 (Sina实时):*")
    sorted_sec = sorted(
        [(k, v) for k, v in sectors.items() if not k.startswith("_")],
        key=lambda x: -x[1]["momentum_score"]
    )
    for s, d in sorted_sec:
        bar = "🟢" if d["momentum_score"] > 1 else "🔴" if d["momentum_score"] < -1 else "⚪"
        etf_n = d["etf_count"]
        if etf_n > 0:
            print(f"  {bar} {s}: {d['momentum_score']:+.2f} ({d['avg_return']:+.2f}%, {etf_n}只)")


if __name__ == "__main__":
    main()
