"""
统一事件数据源 v2 — 2026-06-02 更新
新增: 美联储政策/AI应用/新能源/消费电子等事件
用法: from events_data import DEFAULT_EVENTS, inject_events, EVENT_PRESETS
"""
from ..analysis.causal import Event

# ═══ 预设事件集 ═══
EVENT_PRESETS = {
    "chip_war": {  # 芯片战主题
        "BIS": {
            "title": "美国BIS对华先进芯片出口管制持续升级，国产替代加速",
            "etype": "policy", "source_auth": 1.0, "impact_scope": 0.80,
            "duration_days": 180, "surprise": 0.5, "reversibility": 0.1, "direction": -0.7,
            "affected_sectors": ["半导体", "AI算力", "硬科技", "通信/光模块", "5G/PCB"],
            "affected_materials": {
                "光刻胶": {"phys_dep": 0.90, "stock_days": 30, "replace_months": 36, "geo_conc": 0.90},
                "高纯硅片": {"phys_dep": 0.85, "stock_days": 60, "replace_months": 24, "geo_conc": 0.75},
            },
            "priced_in": 0.8,  # 市场充分预期→反向交易
        },
        "lithography": {
            "title": "日本限制KrF光刻胶出口 + 关键研发人员离职冲击国产替代进程",
            "etype": "supply_chain", "source_auth": 0.9, "impact_scope": 0.50,
            "duration_days": 90, "surprise": 0.7, "reversibility": 0.3, "direction": -0.6,
            "affected_materials": {
                "光刻胶": {"phys_dep": 0.90, "stock_days": 30, "replace_months": 36, "geo_conc": 0.90},
            },
            "affected_people": {"critical": 0.8, "replace_difficulty": 0.7, "team_impact": 0.3},
            "priced_in": 0.7,  # ASDA发现: 光刻胶管制→国产替代利好
        }
    },
    "ai_boom": {  # AI热潮
        "csp_capex": {
            "title": "全球CSP资本开支7250亿美元(+77%)，AI算力军备竞赛白热化",
            "etype": "tech_break", "source_auth": 0.6, "impact_scope": 0.70,
            "duration_days": 180, "surprise": 0.4, "reversibility": 0.5, "direction": +0.7,
            "affected_sectors": ["AI算力", "半导体", "云计算/算力", "通信/光模块", "硬科技"],
        },
        "ai_app": {
            "title": "AI应用落地加速：多模态/Agent/代码生成进入产品化阶段",
            "etype": "tech_break", "source_auth": 0.5, "impact_scope": 0.40,
            "duration_days": 90, "surprise": 0.3, "reversibility": 0.6, "direction": +0.5,
            "affected_sectors": ["数字经济", "传媒", "游戏", "云计算/算力"],
        }
    },
    "macro": {  # 宏观
        "debt": {
            "title": "2026年40万亿地方债化解推进，高股息+利率债受益",
            "etype": "macro", "source_auth": 0.7, "impact_scope": 0.60,
            "duration_days": 365, "surprise": 0.2, "reversibility": 0.2, "direction": +0.3,
            "priced_in": 0.6,  # 政策预期充分→利好兑现=中性
        },
        "gold": {
            "title": "全球央行持续增持黄金，金价高位运行(2900+)避险需求强劲",
            "etype": "macro", "source_auth": 0.8, "impact_scope": 0.40,
            "duration_days": 180, "surprise": 0.4, "reversibility": 0.6, "direction": +0.5,
        },
        "fed": {
            "title": "美联储降息周期延续，全球流动性宽松利好成长股+黄金+新兴市场",
            "etype": "macro", "source_auth": 0.9, "impact_scope": 0.70,
            "duration_days": 180, "surprise": 0.2, "reversibility": 0.4, "direction": +0.4,
        },
        "divergence": {
            "title": "A股极致分化：权重股抱团AI龙头创新高，超6成个股下跌",
            "etype": "macro", "source_auth": 0.5, "impact_scope": 0.80,
            "duration_days": 90, "surprise": 0.3, "reversibility": 0.5, "direction": -0.15,
        },
    },
    "sector": {  # 行业
        "new_energy": {
            "title": "光伏组件价格触底反弹+储能装机创新高，新能源产业链回暖",
            "etype": "tech_break", "source_auth": 0.5, "impact_scope": 0.35,
            "duration_days": 60, "surprise": 0.4, "reversibility": 0.5, "direction": +0.3,
            "affected_sectors": ["新能源", "新能源电力", "碳中和"],
        },
        "consumer": {
            "title": "暑期消费旺季临近：旅游/餐饮/家电需求回升，消费板块修复",
            "etype": "macro", "source_auth": 0.4, "impact_scope": 0.30,
            "duration_days": 60, "surprise": 0.2, "reversibility": 0.7, "direction": +0.2,
            "affected_sectors": ["旅游消费", "白酒消费", "家电", "汽车"],
        },
    }
}

# ═══ 默认全量事件 (合并所有预设) ═══
DEFAULT_EVENTS = []
for preset_name, preset_events in EVENT_PRESETS.items():
    for ev_key, ev_data in preset_events.items():
        DEFAULT_EVENTS.append(ev_data)

# ═══ 按场景快速选择 ═══
PRESET_COMBOS = {
    "full": list(EVENT_PRESETS.keys()),           # 全部主题
    "chip_focus": ["chip_war", "ai_boom"],         # 芯片+AI
    "macro_focus": ["macro", "sector"],             # 宏观+行业
    "defense": ["macro", "chip_war"],               # 防御(宏观+芯片)
}


def inject_events(engine, events=None, presets=None, verbose=True):
    """向 CausalEngine 注入事件
    
    Args:
        engine: CausalEngine 实例
        events: 事件dict列表，优先于presets
        presets: 预设名列表如 ['chip_war','macro']，用PRESET_COMBOS快捷选择
        verbose: 是否打印注入日志
    Returns:
        注入事件数量
    """
    if events is None:
        events = []
        if presets:
            for pname in presets:
                if pname in EVENT_PRESETS:
                    for ev_data in EVENT_PRESETS[pname].values():
                        events.append(ev_data)
        if not events:
            events = DEFAULT_EVENTS
    
    count = 0
    for ev in events:
        kw = {}
        for field in ['affected_sectors', 'affected_materials', 'affected_people']:
            if field in ev and ev[field]:
                kw[field] = ev[field]
        
        event = Event(
            title=ev["title"], etype=ev["etype"],
            source_auth=ev["source_auth"], impact_scope=ev["impact_scope"],
            duration_days=ev["duration_days"], surprise=ev["surprise"],
            reversibility=ev["reversibility"], direction=ev["direction"],
            **kw,
        )
        event.priced_in = ev.get("priced_in", 0.0)
        engine.add_event(event)
        
        if verbose:
            d = ev["direction"]
            direction_label = "🟢利好" if d > 0 else ("🔴利空" if d < -0.3 else ("🟠偏空" if d < 0 else "🟡偏多"))
            i0 = ev["source_auth"] * 0.75 + ev["impact_scope"] * 0.25
            print(f"  📡 {direction_label} {ev['title'][:40]} | I₀={i0:.3f} | 方向={d:+.1f}")
        count += 1
    
    return count
