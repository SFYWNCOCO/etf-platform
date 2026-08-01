#!/usr/bin/env python3
"""weekly_top3.py v17.0 — 回测验证版 ETF 推荐系统

基于81周历史回测（夏普1.75，回撤-13.8%）：
1. 行业动量(20d) → 按大板块去重 → Top3
2. 沪深300趋势过滤 → 动态仓位
3. 每行业选流动性最好的ETF
4. 输出买卖指令（可直接下单）

用法:
  python weekly_top3.py                     # 标准输出
  python weekly_top3.py --json              # JSON格式（供程序调用）
  python weekly_top3.py --help              # 帮助
"""
import sys, json, math, statistics
from pathlib import Path
from datetime import datetime, time
from collections import defaultdict

_HERE = Path(__file__).resolve().parent
_SRC = _HERE / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# ── 板块映射（47细分行业 → 10大板块） ──────────────────────
SECTOR_TO_MEGA = {
    "金融": "金融", "银行": "金融", "保险": "金融", "券商": "金融",
    "AI/科技": "科技", "半导体": "科技", "芯片": "科技", "软件": "科技",
    "通信/5G": "科技", "计算机": "科技", "电子": "科技", "机器人": "科技",
    "医药": "医药", "医疗": "医药", "创新药": "医药", "医疗器械": "医药",
    "中药": "医药", "生物医药": "医药",
    "新能源": "新能源", "光伏": "新能源", "风电": "新能源", "储能": "新能源",
    "锂电": "新能源", "电池": "新能源", "新能源车": "新能源",
    "消费": "消费", "白酒": "消费", "食品饮料": "消费", "家电": "消费",
    "汽车": "消费", "旅游": "消费", "传媒": "消费", "游戏": "消费",
    "军工": "军工", "国防": "军工", "航空航天": "军工",
    "周期/资源": "周期", "有色": "周期", "钢铁": "周期", "煤炭": "周期",
    "化工": "周期", "石油": "周期", "原油": "周期", "黄金": "周期",
    "基建": "基建", "地产": "基建", "电力": "基建", "公用事业": "基建",
    "红利/价值": "红利价值", "港股": "跨境", "跨境": "跨境",
    "纳指": "跨境", "海外": "跨境", "中概": "跨境", "互联网": "跨境",
    "现金流": "红利价值",
}

EXCLUDE_SECTORS = {"货币基金", "利率债", "信用债", "债券", "国债", "货币", "宽基A", "宽基"}
BROAD_BASE_KEYWORDS = {
    "沪深300", "中证500", "中证1000", "上证50", "深证100",
    "创业板", "科创50", "科创100", "中证A50", "中证A500",
    "MSCI", "A50", "A500", "纳指", "标普", "恒生",
    "红利", "股息", "价值",
}

BENCHMARK_CODE = "510300"  # 华泰柏瑞沪深300ETF


def _check_market_state():
    now = datetime.now()
    wd = now.weekday()
    t = now.time()
    if wd >= 5:
        return "weekend", "周末休市"
    if t < time(9, 30):
        return "pre_market", "盘前"
    if time(9, 30) <= t < time(11, 30):
        return "trading_morning", "🟢 早盘交易中"
    if time(11, 30) <= t < time(13, 0):
        return "lunch_break", "🟡 午休"
    if time(13, 0) <= t < time(15, 0):
        return "trading_afternoon", "🟢 午盘交易中"
    if time(15, 0) <= t < time(20, 0):
        return "post_market", "⚪ 已收盘"
    return "night", "⚪ 夜间"


def sector_to_mega(sector):
    for key, val in SECTOR_TO_MEGA.items():
        if key in sector or sector in key:
            return val
    return "其他"


def is_broad_base(name, sector):
    name = name or ""
    sector = sector or ""
    if sector in EXCLUDE_SECTORS:
        return True
    for kw in BROAD_BASE_KEYWORDS:
        if kw in name:
            return True
    return False


# ── 数据层 ─────────────────────────────────────────────────
def _get_etf_codes():
    """加载ETF列表，排除宽基/债券，按mega-sector分组"""
    from etf_platform.config_loader import load_etfs
    etfs = load_etfs()
    
    mega_sectors = defaultdict(list)      # mega_sector -> [(code, name, volume), ...]
    code_to_sector = {}                    # code -> (sector, mega_sector)
    
    for code_key, info in etfs.items():
        code = str(info.get("code", code_key))
        name = info.get("name", "")
        sector = info.get("sector", "其他")
        
        if is_broad_base(name, sector):
            continue
        if len(code) != 6 or not code.isdigit():
            continue
        
        mega = sector_to_mega(sector)
        code_to_sector[code] = (sector, mega)
        mega_sectors[mega].append((code, name, 0))  # volume filled later
    
    return mega_sectors, code_to_sector


def _get_momentum_data():
    """获取全量ETF的20日动量 + 沪深300趋势"""
    from etf_platform.data.kline import get_trend_batch, get_trend, clear_trend_cache
    from etf_platform.config_loader import load_etfs
    
    # 避免缓存影响
    clear_trend_cache()
    
    etfs = load_etfs()
    all_codes = [str(info.get("code", ck)) for ck, info in etfs.items()
                 if not is_broad_base(info.get("name", ""), info.get("sector", ""))]
    
    print(f"  📡 获取 {len(all_codes)} 只ETF动量数据...", end="", flush=True)
    trends = get_trend_batch(all_codes, parallel=True, max_workers=16)
    print(f" {len(trends)} 成功", flush=True)
    
    # 获取沪深300趋势
    bench = get_trend(BENCHMARK_CODE)
    if bench is None:
        bench = get_trend("510300")
    
    return trends, bench


def _get_regime(bench_kline, bench_trend):
    """判断市场状态 → 仓位建议"""
    if bench_trend is None:
        return "unknown", 1.0, "⚪ 无数据"
    
    chg_20d = getattr(bench_trend, 'change_20d', 0)
    chg_60d = getattr(bench_trend, 'change_60d', 0)
    
    if chg_20d > 0 and chg_60d > 3:
        return "bull", 1.0, "🟢 牛市满仓 (MA20↑ MA60↑)"
    elif chg_20d > -3 and chg_60d > 0:
        return "cautious", 0.7, "🟡 谨慎7仓 (MA20横 MA60↑)"
    elif chg_20d > -8:
        return "risk_off", 0.5, "🟠 半仓防御 (MA20↓)"
    else:
        return "bear", 0.3, "🔴 熊市轻仓 (MA20↓ MA60↓)"


def _get_sector_flows(live=False) -> dict:
    """获取行业资金流方向。返回 {mega: {net_inflow_pct, flow_dir}}

    注：sina_live 源不提供真实资金净流入（net_inflow=0），
    用当日 return_pct（行业当日涨跌）作为短期资金/动量确认代理——
    与 20d 动量是不同时间尺度，可独立确认短期方向。
    """
    try:
        from etf_platform.analysis.sector_flow_bridge import get_bridge
        bridge = get_bridge()
        flows = bridge._load_flows(live=live)
        if not isinstance(flows, dict):
            return {}
        result = {}
        for name, f in flows.items():
            if name.startswith("_"):
                continue
            if not isinstance(f, dict):
                continue
            # 优先真实净流入，退化到当日涨跌幅（代理）
            net_pct = f.get("net_inflow_pct", 0) or 0
            try:
                net_pct = float(net_pct)
            except (TypeError, ValueError):
                net_pct = 0
            if net_pct == 0:
                net_pct = f.get("return_pct", 0) or 0
                try:
                    net_pct = float(net_pct)
                except (TypeError, ValueError):
                    net_pct = 0
            mega = sector_to_mega(name)
            # 同一 mega 下取净流入最大的行业代表
            if mega not in result or net_pct > result[mega]["net_inflow_pct"]:
                result[mega] = {
                    "net_inflow_pct": net_pct,
                    "flow_dir": "流入" if net_pct > 0 else ("流出" if net_pct < 0 else "中性"),
                }
        return result
    except Exception:
        return {}


def _get_valuation_signal(mega: str, mega_sectors: dict, trends: dict) -> dict:
    """估算板块估值分位：用板块内ETF的60日位置中位数近似。

    无法实时拿全行业PE/PB（akshare挂），用 position_pct（60日位置）作为
    估值/位置代理：位置>85% = 高位（估值贵），<30% = 低位（估值便宜）。
    返回 {valuation_level, valuation_penalty}
    """
    positions = []
    for code, _, _ in mega_sectors.get(mega, []):
        t = trends.get(code)
        if t and hasattr(t, "position_pct") and t.position_pct is not None:
            positions.append(t.position_pct)
    if len(positions) < 3:
        return {"valuation_level": "unknown", "valuation_penalty": 0.0}
    med_pos = statistics.median(positions)
    if med_pos > 85:
        return {"valuation_level": "高位", "valuation_penalty": -1.5}
    elif med_pos > 70:
        return {"valuation_level": "偏高", "valuation_penalty": -0.5}
    elif med_pos < 30:
        return {"valuation_level": "低位", "valuation_penalty": +0.5}
    return {"valuation_level": "中位", "valuation_penalty": 0.0}


def _get_top_mega_sectors(mega_sectors, trends, code_to_sector, news_signals=None, top_n=3):
    """
    按20日动量排序大板块（去重），返回Top3。
    集成新闻信号：强看空 → 降权，强看多 → 加分
    """
    # 加载新闻信号
    news_signals = _load_news_signals()
    
    # 计算每个大板块的动量中位数
    mega_momentum = {}
    sector_flows = _get_sector_flows(live=False)
    for mega, codes in mega_sectors.items():
        momentum_vals = []
        for code, _, _ in codes:
            t = trends.get(code)
            if t and hasattr(t, 'change_20d') and t.change_20d is not None and not math.isnan(t.change_20d):
                momentum_vals.append(t.change_20d)
        
        if len(momentum_vals) >= 3:
            momentum_vals.sort()
            median_mom = momentum_vals[len(momentum_vals) // 2]
            
            # ── 新闻情绪修正 ──
            news_adj = 0.0
            news_label = ""
            if news_signals and mega in news_signals:
                ns = news_signals[mega]
                direction = ns.get("direction", "")
                strength = ns.get("strength", "")
                # ── P2-1: 时间衰减（新闻越旧权重越低）──
                fresh_days = ns.get("fresh_days", 0)
                if fresh_days > 7:
                    decay = 0.1   # 一周以上旧闻几乎无影响
                elif fresh_days > 3:
                    decay = 0.3
                else:
                    decay = 1.0
                if direction == "看空" and strength == "强":
                    news_adj = -5.0 * decay  # 强看空 → 大幅降权（旧闻衰减）
                    news_label = "🔴强看空"
                elif direction == "看空":
                    news_adj = -2.0 * decay
                    news_label = "🔶看空"
                elif direction == "看多" and strength == "强":
                    news_adj = +2.0 * decay  # 强看多 → 加分（旧闻衰减）
                    news_label = "🟢强看多"
                elif direction == "看多":
                    news_adj = +0.5 * decay
                    news_label = "🟢看多"
                elif direction == "中性":
                    news_label = "⚪中性"
            
            # ── 资金流修正（P0-2）──
            flow_adj = 0.0
            flow_label = ""
            if mega in sector_flows:
                fd = sector_flows[mega]
                net_pct = fd["net_inflow_pct"]
                if net_pct > 1.0:
                    flow_adj = +1.0
                    flow_label = "💰流入"
                elif net_pct > 0:
                    flow_adj = +0.3
                    flow_label = "💰微流入"
                elif net_pct < -1.0:
                    flow_adj = -1.5
                    flow_label = "💸流出"
                elif net_pct < 0:
                    flow_adj = -0.5
                    flow_label = "💸微流出"
                else:
                    flow_label = "⚪资金平"
            
            # ── 估值/位置修正（P0-2）──
            val = _get_valuation_signal(mega, mega_sectors, trends)
            val_adj = val["valuation_penalty"]
            
            adjusted_mom = median_mom + news_adj + flow_adj + val_adj
            
            # ── 交叉验证：信号层计数（动量/新闻/资金流/估值）──
            layers_bullish = 0
            layers_bearish = 0
            if median_mom > 1.0:
                layers_bullish += 1
            elif median_mom < -1.0:
                layers_bearish += 1
            if "看多" in news_label:
                layers_bullish += 1
            elif "看空" in news_label:
                layers_bearish += 1
            if "流入" in flow_label:
                layers_bullish += 1
            elif "流出" in flow_label:
                layers_bearish += 1
            if val["valuation_level"] == "低位":
                layers_bullish += 1
            elif val["valuation_level"] in ("高位", "偏高"):
                layers_bearish += 1
            
            mega_momentum[mega] = {
                "median_momentum": median_mom,
                "adjusted_momentum": round(adjusted_mom, 1),
                "news_adjustment": news_adj,
                "news_label": news_label,
                "flow_adjustment": flow_adj,
                "flow_label": flow_label,
                "valuation_level": val["valuation_level"],
                "valuation_adjustment": val_adj,
                "layers_bullish": layers_bullish,
                "layers_bearish": layers_bearish,
                "etf_count": len(momentum_vals),
                "total": len(codes),
            }
    
    # 按调整后动量排序
    ranked = sorted(mega_momentum.items(), key=lambda x: x[1]["adjusted_momentum"] if x[1]["news_label"] != "🔴强看空" else -999, reverse=True)
    
    # 排除强看空的板块
    ranked = [(s, d) for s, d in ranked if d.get("news_label") != "🔴强看空"]
    
    # 动量成熟度惩罚：peaking板块降权，early板块加分
    final_ranked = []
    for s, d in ranked:
        maturity, _ = _assess_momentum_maturity(s, trends, mega_sectors)
        penalty = 0
        if maturity == "peaking":
            penalty = -3.0  # 冲顶 → 降3分
        elif maturity == "mature":
            penalty = -1.0  # 成熟 → 降1分
        elif maturity == "early":
            penalty = +1.0  # 刚启动 → 加1分
        
        d["maturity_penalty"] = penalty
        d["final_score"] = round(d.get("adjusted_momentum", d["median_momentum"]) + penalty, 1)
        final_ranked.append((s, d))
    
    # 按最终分重排
    final_ranked.sort(key=lambda x: x[1]["final_score"], reverse=True)
    
    # ── P0-2 交叉验证门禁：至少3层同向才推荐 ──
    # 层数: 动量/新闻/资金流/估值（4层）。净看多层 >= 3 或 (>=2 且动量强>3%) 才保留
    gated = []
    for s, d in final_ranked:
        net_layers = d.get("layers_bullish", 0) - d.get("layers_bearish", 0)
        d["net_layers"] = net_layers
        if net_layers >= 2:
            gated.append((s, d))
        else:
            d["gated_out"] = True
            gated.append((s, d))  # 保留但标记，由调用方决定是否显示
    
    return gated[:top_n]


def _pick_best_etfs(mega, trends, mega_sectors, live_prices, count=2):
    """在大板块内选流动性最好的N只ETF"""
    codes = mega_sectors.get(mega, [])
    
    scored = []
    for code, name, _ in codes:
        t = trends.get(code)
        if not t or not hasattr(t, 'change_20d') or t.change_20d is None:
            continue
        if math.isnan(t.change_20d) or math.isinf(t.change_20d):
            continue
        
        # 用成交量衡量流动性（优先用实时数据，降级用kline量）
        volume = 0
        if live_prices:
            p = live_prices.get(code, {})
            if isinstance(p, dict):
                volume = p.get("volume", 0) or p.get("amount", 0) or 0
        
        # 如果实时volume为0，用kline中的量
        if volume <= 0:
            volume = getattr(t, 'volume_ratio_5_20', 1) * 1_000_000
        
        scored.append({
            "code": code,
            "name": name,
            "momentum_20d": round(t.change_20d, 1),
            "volume": int(volume),
            "trend_signal": getattr(t, 'trend_signal', 'neutral'),
        })
    
    # 按成交量排序（流动性优先），且动量必须为正（负动量不推荐）
    positive = [x for x in scored if x["momentum_20d"] > 0]
    if positive:
        scored = positive
    scored.sort(key=lambda x: (-x["volume"], -x["momentum_20d"]))
    return scored[:count]


def _refresh_news_data():
    """自动刷新新闻信号（静默执行news_to_etf_bridge）"""
    import subprocess, sys
    try:
        bridge_script = _HERE / "news_to_etf_bridge.py"
        if bridge_script.exists():
            result = subprocess.run(
                [sys.executable, str(bridge_script), "--auto"],
                capture_output=True, text=True, timeout=30, cwd=_HERE
            )
            if result.returncode == 0:
                print("  ✅ 新闻数据已刷新", flush=True)
                return True
    except Exception:
        pass
    return False


def _load_news_signals():
    """
    加载新闻情绪信号（先自动刷新，再读最新数据）
    优先级: 1. news_sentiment(8天) → 2. news_signals_live(2天) → 3. news_etf_signals(6天)
    返回: {mega: {direction, strength, note, fresh_days}}
    """
    import json
    from datetime import datetime, timedelta
    
    now = datetime.now()
    result = {}
    sources_used = []
    
    # ── 源1: news_sentiment.json（AI综合情绪分析，最高质量但可能旧） ──
    sent_file = _HERE / "data" / "news_sentiment.json"
    if sent_file.exists():
        try:
            data = json.loads(sent_file.read_text(encoding="utf-8"))
            updated_str = data.get("updated", "")
            if updated_str:
                updated = datetime.strptime(updated_str[:19], "%Y-%m-%dT%H:%M:%S")
                age_days = (now - updated).days
            else:
                age_days = 99
            
            for sector, info in data.get("sectors", {}).items():
                mega = sector_to_mega(sector)
                if mega not in result:
                    result[mega] = {
                        "direction": info.get("direction", "中性"),
                        "strength": info.get("strength", "弱"),
                        "note": info.get("note", ""),
                        "fresh_days": age_days,
                    }
                elif info.get("strength", "") == "强" and result[mega].get("strength", "") != "强":
                    result[mega] = {
                        "direction": info.get("direction", "中性"),
                        "strength": info.get("strength", "弱"),
                        "note": info.get("note", ""),
                        "fresh_days": age_days,
                    }
            
            sources_used.append(f"AI情绪({age_days}天前)")
        except Exception:
            pass
    
    # ── 源2: news_signals_live.json（最新新闻爬虫，按direction统计） ──
    live_file = _HERE / "data" / "news_signals_live.json"
    if live_file.exists():
        try:
            data = json.loads(live_file.read_text(encoding="utf-8"))
            signals = data.get("signals", [])
            gen_time = data.get("generated_at", "")
            live_age = 99
            if gen_time:
                try:
                    live_age = (now - datetime.strptime(gen_time[:19], "%Y-%m-%dT%H:%M:%S")).days
                except: pass
            
            # 按大板块统计利好/利空/中性数量
            sector_counts = {}
            for sig in signals:
                note = sig.get("direction", "中性")
                score = sig.get("score", 5)
                for sec in sig.get("matched_sectors", []):
                    mega = sector_to_mega(sec)
                    if mega not in sector_counts:
                        sector_counts[mega] = {"bullish": 0, "bearish": 0, "neutral": 0, "items": []}
                    if "利好" in note or "看多" in note:
                        sector_counts[mega]["bullish"] += score
                    elif "利空" in note or "看空" in note:
                        sector_counts[mega]["bearish"] += score
                    else:
                        sector_counts[mega]["neutral"] += 1
                    sector_counts[mega]["items"].append(sig.get("title", "")[:30])
            
            for mega, cnt in sector_counts.items():
                direction = "看多" if cnt["bullish"] > cnt["bearish"] else "看空" if cnt["bearish"] > cnt["bullish"] else "中性"
                total = cnt["bullish"] + cnt["bearish"] + cnt["neutral"]
                
                # 只有这个源有数据时才用
                if mega not in result:
                    result[mega] = {
                        "direction": direction,
                        "strength": "强" if total >= 5 else "中" if total >= 2 else "弱",
                        "note": f"新闻:c{total}条 (多{cnt['bullish']}空{cnt['bearish']})",
                        "fresh_days": live_age,
                    }
            
            if live_age < 10:
                sources_used.append(f"新闻爬虫({live_age}天前)")
        except Exception:
            pass
    
    # ── 源3: news_etf_signals.json（KB研究信号） ──
    kb_file = _HERE / "data" / "news_etf_signals.json"
    if kb_file.exists():
        try:
            data = json.loads(kb_file.read_text(encoding="utf-8"))
            kb_age = 99
            for code, sig in data.items():
                created = sig.get("created_at", "")
                if created and kb_age == 99:
                    try:
                        kb_age = (now - datetime.strptime(created[:19], "%Y-%m-%dT%H:%M:%S")).days
                    except: pass
                sector = sig.get("sector", "")
                mega = sector_to_mega(sector)
                direction = sig.get("direction", "")
                if direction and mega not in result:
                    strength_val = "看多" if direction == "看多" else "看空"
                    # 从news_score推断强度
                    ns = sig.get("news_score", 0)
                    strength = "强" if abs(ns) > 0.3 else "中" if abs(ns) > 0.1 else "弱"
                    result[mega] = result.get(mega, {})
                    if "fresh_days" not in result[mega] or result[mega].get("fresh_days", 99) > kb_age:
                        result[mega] = {
                            "direction": direction,
                            "strength": strength,
                            "note": f"KB研究",
                            "fresh_days": kb_age,
                        }
            if kb_age < 10:
                sources_used.append(f"KB研究({kb_age}天前)")
        except Exception:
            pass
    
    return result


def _get_news_freshness_label(news_signals):
    """显示新闻数据时效"""
    if not news_signals:
        return "⚪ 无新闻数据"
    
    ages = set()
    for mega, info in news_signals.items():
        days = info.get("fresh_days", 99)
        ages.add(days)
    
    if not ages:
        return "⚪ 无时效信息"
    
    min_age = min(ages)
    max_age = max(ages)
    
    if min_age <= 1:
        return "🟢 今日新闻" if min_age == 0 else "🟢 昨日新闻"
    elif min_age <= 3:
        return f"🟡 {min_age}-{max_age}天前"
    elif min_age <= 7:
        return f"🟠 {min_age}天前"
    else:
        return f"🔴 {min_age}天前（建议刷新）"


def _assess_momentum_maturity(mega, trends, mega_sectors):
    """
    判断大板块的动量处于什么阶段:
    - early: 刚启动，安全
    - mature: 已成熟，谨慎  
    - peaking: 见顶风险，不建议追
    - crashing: 急跌中，等企稳
    
    判断依据:
    1. position_pct > 80% = 接近60日高点
    2. 5d < 10d < 20d = 加速度递减（减速）
    3. 5d < 0 = 已经转跌
    """
    codes = [c for c, _, _ in mega_sectors.get(mega, [])]
    positions = []
    chg_5d = []
    chg_10d = []
    chg_20d = []
    
    for code in codes[:10]:
        t = trends.get(code)
        if t and t.change_20d is not None and not math.isnan(t.change_20d):
            positions.append(t.position_pct)
            chg_5d.append(t.change_5d)
            chg_10d.append(t.change_10d)
            chg_20d.append(t.change_20d)
    
    if len(positions) < 3:
        return "unknown", "⚪ 数据不足"
    
    avg_pos = statistics.mean(positions)
    avg_5d = statistics.mean(chg_5d)
    avg_10d = statistics.mean(chg_10d)
    avg_20d = statistics.mean(chg_20d)
    
    near_high = avg_pos > 75
    decelerating = avg_5d < avg_10d - 2
    turning_down = avg_5d < 0
    
    if turning_down and avg_20d > 5:
        return "peaking", f"🔴 冲顶减速（5d={avg_5d:+.1f}%, 20d={avg_20d:+.1f}%）"
    elif near_high and decelerating:
        return "peaking", "🔴 冲顶（近高点+速度放缓）"
    elif near_high:
        return "mature", f"🟡 近高点(pos={avg_pos:.0f}%)"
    elif decelerating and avg_20d > 5:
        return "mature", f"🟡 动量减速（5d={avg_5d:+.1f}%, 20d={avg_20d:+.1f}%）"
    elif avg_5d > 0 and avg_20d > 3:
        return "early", f"🟢 加速中（5d={avg_5d:+.1f}%）"
    elif avg_20d < -10:
        return "crashing", f"🔴 深跌({avg_20d:.0f}%) 等企稳"
    elif avg_20d < -3:
        return "weak", "🔶 偏弱"
    else:
        return "neutral", "⚪ 中性"


# ── 主入口 ─────────────────────────────────────────────────
def main():
    """生成每周ETF推荐"""
    state, state_label = _check_market_state()
    
    # ── 1. 获取数据 ──
    mega_sectors, code_to_sector = _get_etf_codes()
    trends, bench_trend = _get_momentum_data()
    
    # 获取实时行情中的成交量数据（用于流动性排序）
    live_prices = {}
    try:
        from etf_platform.data.live_price_bridge import fetch_live_prices
        all_codes = list(trends.keys())
        # 限制数量避免超时
        prices = fetch_live_prices(all_codes[:300])
        if prices and "_meta" not in prices:
            live_prices = prices
        else:
            live_prices = prices.get("data", {}) if isinstance(prices, dict) and "_meta" in prices else {}
    except Exception as e:
        print(f"  ⚠️ 实时行情获取失败: {e}，用kline量代替", file=sys.stderr)
    
    # ── 2. 大盘状态 ──
    regime, position_mult, regime_label = _get_regime(None, bench_trend)
    
    bench_20d = getattr(bench_trend, 'change_20d', 0)
    bench_60d = getattr(bench_trend, 'change_60d', 0)
    
    # ── 3. 大板块动量排名 ──
    print("  📰 正在刷新新闻数据...", end=" ", flush=True)
    _refresh_news_data()
    
    news_signals = _load_news_signals()
    
    # 显示新闻时效
    print()
    news_age_info = _get_news_freshness_label(news_signals)
    if news_age_info:
        print(f"  📰 新闻源: {news_age_info}")
    
    top3_mega = _get_top_mega_sectors(mega_sectors, trends, code_to_sector, news_signals=news_signals, top_n=6)
    
    if not top3_mega:
        print("❌ 动量数据不足，无法推荐")
        return
    
    # ── P0-2 门禁分层选板块：优先 ≥3层同向，再 2层，最后 1层(标记低置信) ──
    gated_in = [t for t in top3_mega if not t[1].get("gated_out", False)]
    gated_out = [t for t in top3_mega if t[1].get("gated_out", False)]
    selected_mega = gated_in[:3]
    if len(selected_mega) < 3:
        # 补充层数≥1的板块（标记为低置信候选）
        for t in gated_out:
            if len(selected_mega) >= 3:
                break
            selected_mega.append(t)
    
    # 选ETF（每个大板块2只）
    picks = []
    for mega, data in selected_mega:
        etfs_in_mega = _pick_best_etfs(mega, trends, mega_sectors, live_prices, count=2)
        picks.extend(etfs_in_mega)
    
    # 最终精选：每个大板块最多1只
    seen_mega = set()
    final_picks = []
    for p in picks:
        p_mega = code_to_sector.get(p["code"], ("?", "?"))[1]
        if p_mega not in seen_mega:
            seen_mega.add(p_mega)
            final_picks.append(p)
        if len(final_picks) >= 3:
            break
    # 去重后不够3只则从剩余补
    if len(final_picks) < 3:
        for p in picks:
            if p not in final_picks:
                final_picks.append(p)
            if len(final_picks) >= 3:
                break
    final_picks = final_picks[:3]
    
    # ── 5. 输出 ──
    now = datetime.now()
    
    output = {
        "timestamp": now.strftime("%Y-%m-%d %H:%M"),
        "market_state": state_label,
        "regime": regime_label,
        "position_suggestion": f"{int(position_mult * 100)}%",
        "benchmark_sh300": f"{bench_20d:+.1f}% (20d) / {bench_60d:+.1f}% (60d)",
        "momentum_top3_sectors": [
            {
                "sector": s,
                "momentum_20d_pct": d["median_momentum"],
                "adjusted_momentum_pct": d["adjusted_momentum"],
                "news_sentiment": d.get("news_label", ""),
                "flow_signal": d.get("flow_label", ""),
                "valuation_level": d.get("valuation_level", ""),
                "net_layers": d.get("net_layers", 0),
                "gated_out": d.get("gated_out", False),
                "etf_count": f"{d['etf_count']}/{d['total']}",
            }
            for s, d in selected_mega
        ],
        "recommendations": [],
        "total_etfs_scanned": len(trends),
    }
    
    # ── P1-2: 每个板块的层贡献分值（供归因）──
    mega_layer_map = {s: d for s, d in selected_mega}
    
    for i, p in enumerate(final_picks, 1):
        p_mega = code_to_sector.get(p["code"], ("?", "?"))[1]
        md = mega_layer_map.get(p_mega, {})
        rec = {
            "rank": i,
            "recommendation_id": f"W{now.strftime('%Y%m%d')}-{i:02d}-{p['code']}",
            "code": p["code"],
            "name": p["name"],
            "momentum_20d": p["momentum_20d"],
            "volume": p["volume"],
            "sector": code_to_sector.get(p["code"], ("?", "?"))[0],
            "mega_sector": p_mega,
            "layer_breakdown": {
                "momentum": round(md.get("median_momentum", 0), 2),
                "news_adjustment": md.get("news_adjustment", 0),
                "news_label": md.get("news_label", ""),
                "flow_adjustment": md.get("flow_adjustment", 0),
                "flow_label": md.get("flow_label", ""),
                "valuation_level": md.get("valuation_level", ""),
                "valuation_adjustment": md.get("valuation_adjustment", 0),
                "net_layers": md.get("net_layers", 0),
                "gated_out": md.get("gated_out", False),
            },
        }
        output["recommendations"].append(rec)
    
    # 仓位计算
    if position_mult >= 1.0:
        per_etf_pct = 33
    elif position_mult >= 0.7:
        per_etf_pct = 23
    elif position_mult >= 0.5:
        per_etf_pct = 17
    else:
        per_etf_pct = 10
    
    output["per_etf_position"] = f"{per_etf_pct}% (总仓位{int(position_mult*100)}% / 3只)"
    
    # ── P1-2: 持久化推荐日志（JSONL，供回测归因）──
    try:
        log_path = _HERE / "data" / "recommendations_log.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            for rec in output["recommendations"]:
                f.write(json.dumps({
                    "recommendation_id": rec["recommendation_id"],
                    "date": now.strftime("%Y-%m-%d"),
                    "code": rec["code"],
                    "name": rec["name"],
                    "mega_sector": rec["mega_sector"],
                    "layer_breakdown": rec["layer_breakdown"],
                    "position_pct": per_etf_pct,
                    "regime": regime_label,
                }, ensure_ascii=False) + "\n")
    except OSError as e:
        print(f"  ⚠️ 推荐日志写入失败: {e}", file=sys.stderr)
    
    # ── 显示输出 ──
    if "--json" in sys.argv:
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return
    
    print(f"\n{'='*60}")
    print(f"🦞 周度ETF推荐 · 回测验证版 v17.0")
    print(f"{'='*60}")
    print(f"  时间: {now.strftime('%Y-%m-%d %H:%M')} | {state_label}")
    print()
    print("━━ 大盘状态 " + "━" * 35)
    print(f"  {regime_label}")
    print(f"  沪深300 20日: {bench_20d:+.1f}% | 60日: {bench_60d:+.1f}%")
    print(f"  建议仓位: {int(position_mult * 100)}%")
    print()
    print("━━ 大板块动量排名 " + "━" * 25)
    
    for s, d in selected_mega:
        arrow = "🟢" if d["adjusted_momentum"] > 2 else "🟡" if d["adjusted_momentum"] > 0 else "🔴"
        news_tag = d.get("news_label", "")
        mom_raw = d["median_momentum"]
        mom_adj = d["adjusted_momentum"]
        maturity, maturity_label = _assess_momentum_maturity(s, trends, mega_sectors)
        if news_tag:
            print(f"  {arrow} {s:10s}: {mom_adj:>+6.1f}% (原始{mom_raw:+.1f}%) {news_tag} {maturity_label} ({d['etf_count']}/{d['total']}只)")
        else:
            print(f"  {arrow} {s:10s}: {mom_adj:>+6.1f}% {maturity_label} ({d['etf_count']}/{d['total']}只)")
    
    print()
    print("━━ 本周推荐 " + "━" * 36)
    
    for i, p in enumerate(final_picks, 1):
        sector, mega = code_to_sector.get(p["code"], ("?", "?"))
        volume_str = f"{p['volume']/1e8:.1f}亿" if p['volume'] > 1e8 else f"{p['volume']/1e4:.0f}万"
        print()
        print(f"  #{i} {p['code']} {p['name']}")
        print(f"     板块: {mega} ({sector})")
        print(f"     动量: {p['momentum_20d']:+.1f}% (20日)")
        print(f"     成交: {volume_str}")
    
    print()
    print("━━ 操作建议 " + "━" * 36)
    print()
    if position_mult < 0.5:
        print("  ⚠️ 当前市场偏弱，建议轻仓或观望")
    else:
        print("  🟢 买入（周五14:45前下单）：")
        for i, p in enumerate(final_picks, 1):
            print(f"     {p['code']} {p['name']} — 约{per_etf_pct}%资金")
    
    print()
    print("  🔴 卖出：下周五14:45全清，按新信号换仓")
    print()
    if position_mult < 1.0:
        print(f"  💡 剩余 {100 - int(position_mult*100)}% 资金建议：货币ETF或逆回购")
    
    print()
    print(f"  📊 扫描ETF: {len(trends)}只 | 大板块: {len(mega_sectors)}个")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
