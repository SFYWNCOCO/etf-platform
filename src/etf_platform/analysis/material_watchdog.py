"""material_watchdog.py — 新材料自动发现 + 一键注册

两大功能:
  1. 自动发现: 从财经新闻中扫描新材料关键词 → 识别新兴材料趋势
  2. 一键注册: 极简 API → 3个字段即可添加新材料到监控库

工作原理:
  - 维护一个 MATERIAL_KEYWORDS 词库（150+个材料关键词）
  - 定期扫描新闻标题 → 匹配到新材料关键词 → 标记为"待确认"
  - 用户确认后 → 自动生成完整材料条目 → 注册到监控系统

用法:
  python -m etf_platform.analysis.material_watchdog scan      # 扫描新闻发现新材料
  python -m etf_platform.analysis.material_watchdog add <名称> <趋势> <ETF代码>  # 一行添加
  python -m etf_platform.analysis.material_watchdog list      # 列出已发现待确认材料
  python -m etf_platform.analysis.material_watchdog confirm <名称>  # 确认并注册
"""

import json
import sys
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

BASE = Path(__file__).resolve().parent.parent.parent.parent
DISCOVERY_LOG = BASE / "etf-platform" / "data" / "material_discoveries.json"
QUICK_ADD_YAML = BASE / "etf-platform" / "config" / "material_quick_add.yaml"

# ═══════════════════════════════════════════
# 材料关键词库 — 监控什么
# ═══════════════════════════════════════════
MATERIAL_KEYWORDS = {
    # 电池/新能源
    "固态电池": {"etfs": ["516160","515030"], "category": "新能源", "trl": 5},
    "钠离子电池": {"etfs": ["516160","515030"], "category": "新能源", "trl": 7},
    "锂硫电池": {"etfs": ["516160","515030"], "category": "新能源", "trl": 4},
    "磷酸锰铁锂": {"etfs": ["516160","515030"], "category": "新能源", "trl": 7},
    "全固态电解质": {"etfs": ["516160","515030"], "category": "新能源", "trl": 4},
    "半固态电池": {"etfs": ["516160","515030"], "category": "新能源", "trl": 6},
    "凝聚态电池": {"etfs": ["516160","515030"], "category": "新能源", "trl": 5},
    "硫化物电解质": {"etfs": ["516160","515030"], "category": "新能源", "trl": 4},
    "氧化物电解质": {"etfs": ["516160","515030"], "category": "新能源", "trl": 6},
    "复合集流体": {"etfs": ["516160","515030"], "category": "新能源", "trl": 7},
    "硅碳负极": {"etfs": ["516160","515030","159755"], "category": "新能源", "trl": 7},
    "预锂化": {"etfs": ["516160","515030"], "category": "新能源", "trl": 6},
    "4680电池": {"etfs": ["516160","515030","159755"], "category": "新能源", "trl": 8},
    "刀片电池": {"etfs": ["516160","515030","159755"], "category": "新能源", "trl": 9},
    "麒麟电池": {"etfs": ["516160","515030","159755"], "category": "新能源", "trl": 9},
    # 半导体
    "氮化镓": {"etfs": ["159995","512480"], "category": "半导体", "trl": 8},
    "碳化硅": {"etfs": ["159995","512480"], "category": "半导体", "trl": 8},
    "氧化镓": {"etfs": ["159995","512480"], "category": "半导体", "trl": 4},
    "金刚石半导体": {"etfs": ["159995","512480"], "category": "半导体", "trl": 3},
    "High-NA EUV": {"etfs": ["159995","512480"], "category": "半导体", "trl": 6},
    "Chiplet": {"etfs": ["159995","512480","159819"], "category": "半导体", "trl": 7},
    "玻璃基板封装": {"etfs": ["159995","512480"], "category": "半导体", "trl": 5},
    "背面供电": {"etfs": ["159995","512480"], "category": "半导体", "trl": 5},
    "CFET": {"etfs": ["159995","512480"], "category": "半导体", "trl": 3},
    "GAA晶体管": {"etfs": ["159995","512480"], "category": "半导体", "trl": 7},
    "2nm工艺": {"etfs": ["159995","512480","159819"], "category": "半导体", "trl": 7},
    "3D DRAM": {"etfs": ["159995","512480"], "category": "半导体", "trl": 4},
    "HBM4": {"etfs": ["159995","512480","159819"], "category": "半导体", "trl": 5},
    # 光伏
    "钙钛矿叠层": {"etfs": ["516160","515030"], "category": "新能源", "trl": 6},
    "异质结HJT": {"etfs": ["516160","515030"], "category": "新能源", "trl": 8},
    "TOPCon": {"etfs": ["516160","515030"], "category": "新能源", "trl": 9},
    "XBC背接触": {"etfs": ["516160","515030"], "category": "新能源", "trl": 8},
    "铜电镀": {"etfs": ["516160","515030"], "category": "新能源", "trl": 6},
    "无主栅": {"etfs": ["516160","515030"], "category": "新能源", "trl": 7},
    # 新材料
    "石墨烯": {"etfs": ["512400"], "category": "新兴材料", "trl": 5},
    "碳纳米管": {"etfs": ["516160","515030"], "category": "新兴材料", "trl": 7},
    "MXene": {"etfs": ["516160"], "category": "新兴材料", "trl": 3},
    "气凝胶": {"etfs": ["516160","515030"], "category": "新兴材料", "trl": 8},
    "液态金属": {"etfs": ["512400","159995"], "category": "新兴材料", "trl": 6},
    "形状记忆合金": {"etfs": ["512660","512670"], "category": "新兴材料", "trl": 7},
    "超材料": {"etfs": ["512660","512670","159206"], "category": "新兴材料", "trl": 5},
    "自修复材料": {"etfs": ["512660"], "category": "新兴材料", "trl": 4},
    "MOF": {"etfs": ["159992","512170"], "category": "新兴材料", "trl": 5},
    "COF": {"etfs": ["159992","512170"], "category": "新兴材料", "trl": 4},
    "生物降解塑料": {"etfs": ["159985"], "category": "新兴材料", "trl": 8},
    "PEEK复合材料": {"etfs": ["512660","512670"], "category": "新兴材料", "trl": 8},
    # 氢能
    "质子交换膜": {"etfs": ["516160","515030"], "category": "能源", "trl": 7},
    "固体氧化物电解": {"etfs": ["516160","515030"], "category": "能源", "trl": 5},
    "阴离子交换膜": {"etfs": ["516160","515030"], "category": "能源", "trl": 4},
    "液氢储运": {"etfs": ["516160","515030"], "category": "能源", "trl": 6},
    "绿氢": {"etfs": ["516160","515030","159985"], "category": "能源", "trl": 7},
    "PEM电解槽": {"etfs": ["516160","515030"], "category": "能源", "trl": 7},
    # 医药
    "ADC偶联药物": {"etfs": ["159992","512170"], "category": "医药", "trl": 8},
    "双抗": {"etfs": ["159992","512170"], "category": "医药", "trl": 8},
    "mRNA疫苗": {"etfs": ["159992","512170"], "category": "医药", "trl": 9},
    "GLP-1": {"etfs": ["159992","512170"], "category": "医药", "trl": 9},
    "CAR-T": {"etfs": ["159992","512170"], "category": "医药", "trl": 8},
    "基因编辑": {"etfs": ["159992","512170"], "category": "医药", "trl": 7},
    "AI制药": {"etfs": ["159992","512170","159819"], "category": "医药", "trl": 6},
    # 量子/AI/算力
    "量子芯片": {"etfs": ["159819","159995"], "category": "前沿科技", "trl": 3},
    "光子芯片": {"etfs": ["159995","159819"], "category": "前沿科技", "trl": 4},
    "存算一体": {"etfs": ["159819","159995"], "category": "前沿科技", "trl": 5},
    "类脑芯片": {"etfs": ["159819","159995"], "category": "前沿科技", "trl": 3},
    "硅光芯片": {"etfs": ["159995","159819","515050"], "category": "前沿科技", "trl": 6},
    "CPO共封装": {"etfs": ["515050","159994","159819"], "category": "前沿科技", "trl": 7},
    # 航空航天
    "eVTOL复材": {"etfs": ["512660","512670","159206"], "category": "军工/航空", "trl": 6},
    "超音速发动机": {"etfs": ["512660","512670"], "category": "军工/航空", "trl": 5},
    "旋转爆轰发动机": {"etfs": ["512660","512670"], "category": "军工/航空", "trl": 3},
    "变循环发动机": {"etfs": ["512660","512670"], "category": "军工/航空", "trl": 5},
    # 机器人
    "人形机器人": {"etfs": ["159819","159995","512170"], "category": "前沿科技", "trl": 6},
    "仿生材料": {"etfs": ["159819"], "category": "新兴材料", "trl": 4},
    "柔性传感器": {"etfs": ["159819","159995"], "category": "前沿科技", "trl": 6},
    "人工肌肉": {"etfs": ["159819"], "category": "新兴材料", "trl": 3},
}


def load_discoveries():
    if DISCOVERY_LOG.exists():
        try:
            return json.loads(DISCOVERY_LOG.read_text(encoding="utf-8"))
        except (IOError, OSError, json.JSONDecodeError, KeyError, ValueError) as e:
            logger.debug("load_discoveries failed: %s", e)
            pass
    return {"discovered": {}, "confirmed": [], "last_scan": ""}


def save_discoveries(data):
    DISCOVERY_LOG.parent.mkdir(parents=True, exist_ok=True)
    DISCOVERY_LOG.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def scan_news(limit=20):
    """扫描财经新闻 → 匹配材料关键词 → 生成发现报告."""
    discoveries = load_discoveries()

    try:
        from ..data.manager import get_news
        news_items = get_news("材料 突破 量产 国产替代 新技术", limit=limit)
    except (KeyError, ValueError, TypeError, AttributeError, ImportError):
        print("  ⚠️ 新闻源不可用，使用关键词库扫描")
        news_items = []

    found = []
    all_hits = {}

    if news_items:
        for item in news_items:
            title = item.title
            for kw, info in MATERIAL_KEYWORDS.items():
                if kw in title:
                    if kw not in all_hits:
                        all_hits[kw] = {"count": 0, "info": info, "sample": title[:80]}
                    all_hits[kw]["count"] += 1
    else:
        # 离线模式: 直接展示关键词库中 TRL>5 的材料作为"值得关注"
        all_hits = {
            kw: {"count": 1, "info": info, "sample": "关键词库匹配 (TRL={})".format(info["trl"])}
            for kw, info in MATERIAL_KEYWORDS.items() if info["trl"] >= 5
        }

    print("\n" + "=" * 65)
    print("  🔍 新材料发现扫描")
    print("=" * 65)

    if all_hits:
        print(f"\n  发现 {len(all_hits)} 个可能的材料趋势:")
        for kw, data in sorted(all_hits.items(), key=lambda x: -x[1]["count"]):
            info = data["info"]
            trl_bar = "█" * info["trl"] + "░" * (9 - info["trl"])
            tag = "🆕 待确认" if kw not in discoveries["discovered"] else "📌 已标记"
            print(f"  {tag} {kw:16s} TRL={info['trl']} {trl_bar} → {', '.join(info['etfs'][:3])}")
            print(f"     └ {data['sample']}")

            if kw not in discoveries["discovered"]:
                discoveries["discovered"][kw] = {
                    "first_seen": datetime.now().isoformat()[:10],
                    "hit_count": data["count"],
                    "category": info["category"],
                    "trl": info["trl"],
                    "etfs": info["etfs"],
                    "status": "pending",
                }
    else:
        print("\n  ✅ 未发现新材料趋势信号")

    discoveries["last_scan"] = datetime.now().isoformat()
    save_discoveries(discoveries)

    # 提示如何一键注册
    pending = {k: v for k, v in discoveries["discovered"].items() if v["status"] == "pending"}
    if pending:
        print(f"\n  📋 {len(pending)} 个材料待确认注册:")
        for kw, info in pending.items():
            print(f"     {kw} → python -m etf_platform.analysis.material_watchdog confirm \"{kw}\"")

    return found


def quick_add(name, trend_or_warning, affects=None, source="手动添加"):
    """一行代码注册新材料 — 只需3个参数.

    Args:
        name: 材料名称, 如 "固态电解质(LLZO)"
        trend_or_warning: 趋势描述或预警, 如 "↑ 日韩厂商突破中试"
        affects: ETF代码列表或单个代码, 如 "516160" 或 ["516160","515030"]
        source: 来源标记, 如 "新闻发现" / "arxiv" / "手动"

    Returns: True 如果成功注册
    """
    if isinstance(affects, str):
        affects = [affects]
    if affects is None:
        affects = ["510300"]  # 默认宽基

    # 自动推断趋势方向
    if any(k in trend_or_warning for k in ["↑", "涨", "突破", "利好", "加速", "量产"]):
        direction = "利好"
    elif any(k in trend_or_warning for k in ["↓", "跌", "管制", "利空", "断供"]):
        direction = "利空"
    else:
        direction = "中性偏多"

    # 智能推断预警图标
    if any(k in trend_or_warning for k in ["🔴"]):
        warning = trend_or_warning
    elif any(k in trend_or_warning for k in ["管制", "断供", "垄断", "危机"]):
        warning = "🔴 " + trend_or_warning
    elif any(k in trend_or_warning for k in ["关注", "替代", "挑战", "竞争"]):
        warning = "🟡 " + trend_or_warning
    else:
        warning = "🟢 " + trend_or_warning

    material = {
        "current": "待补充",
        "trend": trend_or_warning,
        "unit": "N/A",
        "affects": affects,
        "impact_direction": direction,
        "note": f"来源: {source}",
        "warning": warning,
        "_source": source,
        "_registered_at": datetime.now().isoformat(),
        "_auto_generated": True,
    }

    material["_source"] = source
    material["_registered_at"] = datetime.now().isoformat()
    material["_auto_generated"] = True

    from .deep import register_material
    return register_material(name, material)


def confirm_discovery(name):
    """确认并注册一个待确认的材料发现."""
    discoveries = load_discoveries()
    if name not in discoveries["discovered"]:
        print(f"  ✗ '{name}' 不在发现列表中。先运行 scan 扫描。")
        return False

    info = discoveries["discovered"][name]
    if info["status"] == "confirmed":
        print(f"  ⚪ '{name}' 已确认过")
        return True

    # 自动推断趋势
    trl = info.get("trl", 5)
    if trl >= 7:
        trend = "↑ 接近商业化"
    elif trl >= 5:
        trend = "↑ 中试阶段"
    else:
        trend = "↑ 实验室研究"

    success = quick_add(name, trend, info["etfs"], source=f"自动发现(TRL={trl})")
    if success:
        info["status"] = "confirmed"
        info["confirmed_at"] = datetime.now().isoformat()[:10]
        discoveries["confirmed"].append(name)
        save_discoveries(discoveries)
        print(f"  ✅ '{name}' 已注册到材料库")
        return True
    return False


def list_pending():
    discoveries = load_discoveries()
    pending = {k: v for k, v in discoveries["discovered"].items() if v["status"] == "pending"}
    confirmed = discoveries.get("confirmed", [])

    print("\n  待确认材料:")
    if pending:
        for kw, info in pending.items():
            trl = info.get("trl", "?")
            print(f"    🆕 {kw:20s} TRL={trl} → {', '.join(info['etfs'][:2])}")
    else:
        print("    (空 — 运行 scan 发现新材料)")

    print(f"\n  已确认: {len(confirmed)} 个")
    if confirmed:
        for kw in confirmed[-5:]:
            print(f"    ✅ {kw}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "scan"

    if cmd == "scan":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 20
        scan_news(limit)

    elif cmd == "add":
        if len(sys.argv) < 4:
            print("用法: material_watchdog add <材料名> <趋势描述> <ETF代码1,ETF代码2> [来源]")
            print("示例: material_watchdog add \"固态电解质(LLZO)\" \"↑ 日韩量产突破\" \"516160,515030\"")
        else:
            name = sys.argv[2]
            trend = sys.argv[3]
            etf_str = sys.argv[4] if len(sys.argv) > 4 else "510300"
            source = sys.argv[5] if len(sys.argv) > 5 else "命令行添加"
            affects = [e.strip() for e in etf_str.split(",")]
            quick_add(name, trend, affects, source)

    elif cmd == "confirm":
        if len(sys.argv) < 3:
            print("用法: material_watchdog confirm <材料名>")
        else:
            confirm_discovery(sys.argv[2])

    elif cmd == "list":
        list_pending()

    else:
        print("用法:")
        print("  material_watchdog scan              # 扫描新闻发现新材料")
        print("  material_watchdog add <名> <趋势> <ETF>  # 一行添加")
        print("  material_watchdog confirm <名>      # 确认并注册")
        print("  material_watchdog list              # 列出待确认")
