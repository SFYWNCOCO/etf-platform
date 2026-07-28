"""L34 KB Catalyst Layer — 知识库催化剂→ETF行业评分层.

从知识库高价值产业文档(k033/k053/k090/k092/k094/k098/k117/k118/k122/k123/k124/k125/k126/k260)
提取催化剂信号，映射到ETF sector，输出0-10评分+详情。

设计原则:
- 纯KB驱动，无HTTP，live=False也能跑
- 催化剂有valid_until过期机制
- 评分中心5.0，微调±2.0，避免饱和
- 多KB交叉支撑加分
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

# ═══════════════════════════════════════════════
# 催化剂知识库 → ETF sector 映射
# ═══════════════════════════════════════════════

SECTOR_ALIASES: dict[str, str] = {
    # 半导体链
    "半导体设备": "半导体", "半导体材料": "半导体", "芯片": "半导体",
    "电子": "半导体",
    # AI/算力链
    "AI/科技": "AI算力", "AI/半导体": "AI算力", "云计算/算力": "AI算力",
    "通信/光模块": "AI算力", "5G/PCB": "AI算力", "计算机": "AI算力",
    "AI算力": "AI算力",
    # 新能源链
    "新能源": "新能源", "电池": "新能源", "储能": "新能源", "光伏": "新能源",
    "绿电": "新能源", "电力": "新能源", "新能源车": "新能源", "锂电": "新能源",
    "风电": "新能源", "新能源汽车": "新能源",
    # 医药链
    "医药": "医药", "医药生物": "医药", "医药器械": "医药", "创新药": "医药",
    "中药": "医药", "医疗": "医药", "医疗器械": "医药", "港股医药": "医药",
    # 军工/航天
    "军工": "军工", "国防军工": "军工", "航空航天": "商业航天",
    # 前沿主题
    "商业航天": "商业航天", "低空经济": "低空经济", "量子": "量子计算",
    "AI4S": "AI4S", "合成生物": "合成生物", "脑机接口": "脑机接口",
    "具身智能": "具身智能", "人形机器人": "具身智能", "机器人/智造": "具身智能",
    # 金融
    "证券": "券商", "券商": "金融",
    # 红利/价值
    "红利低波": "红利/价值", "红利": "红利/价值", "红利价值": "红利/价值",
    "红利+低波": "红利/价值",
    # 大宗/资源
    "黄金": "贵金属", "煤炭": "周期/资源", "钢铁": "周期/资源",
    # 地产/基建
    "房地产": "基建/地产", "地产": "基建/地产",
    # 消费
    "汽车": "消费",
    # 宽基
    "上证50": "宽基", "沪深300": "宽基", "中证500": "宽基",
    "中证1000": "宽基", "创业板": "宽基",
    # 债券
    "债券": "信用债", "国债": "利率债",
}

# 催化剂定义: sector → [(k_code, catalyst_name, boost, valid_until, detail)]
# boost范围: ±0.3~1.2，多个催化剂叠加后clip到±2.0
CATALYSTS: dict[str, list[dict[str, Any]]] = {
    "半导体": [
        {
            "k_code": "k053",
            "name": "AI算力+HBM存储超级周期",
            "boost": 1.2,
            "valid_until": "2027-06-30",
            "detail": "2026Q1全球半导体营收环比+27%，HBM市场+193%，SK海力士HBM收入份额58%，HBM3E涨价20%，北美云厂商CapEx突破6500亿美元",
        },
        {
            "k_code": "k053",
            "name": "国产替代加速(长鑫IPO+燧原注册)",
            "boost": 0.8,
            "valid_until": "2027-12-31",
            "detail": "长鑫科技科创板IPO、燧原AI芯片注册获批、阿里平头哥真武芯片交付56万片",
        },
        {
            "k_code": "k053",
            "name": "设备订单滞后释放",
            "boost": 0.5,
            "valid_until": "2027-03-31",
            "detail": "设备订单滞后下游盈利改善~2Q，当前处于需求加速释放前夜",
        },
    ],
    "新能源": [
        {
            "k_code": "k090",
            "name": "碳酸锂价格反转(5.8→17.5万)",
            "boost": 0.7,
            "valid_until": "2026-12-31",
            "detail": "碳酸锂自2025年6月低点5.84万反弹至2026年7月约18万+，2026.7.3期货引入境外交易者，累计+200%+",
        },
        {
            "k_code": "k033",
            "name": "储能多元技术路线突破",
            "boost": 0.5,
            "valid_until": "2027-12-31",
            "detail": "钠离子/液流电池产业化加速，LFP全球产能占70%+，储能是能源转型关键瓶颈",
        },
        {
            "k_code": "k090",
            "name": "光伏产业链出清尾声",
            "boost": 0.3,
            "valid_until": "2026-09-30",
            "detail": "光伏产业链价格触底，落后产能出清，龙头集中度提升",
        },
    ],
    "医药": [
        {
            "k_code": "k092",
            "name": "创新药管线估值修复",
            "boost": 0.7,
            "valid_until": "2027-06-30",
            "detail": "2026年7月6款创新药有望获FDA批准，恒瑞rivoceranib+camrelizumab PDUFA 7/23，rNPV估值框架下管线价值重估",
        },
        {
            "k_code": "k123",
            "name": "AI4S提升药物研发成功率",
            "boost": 0.5,
            "valid_until": "2027-12-31",
            "detail": "AI发现药物I期成功率从~5%提升至~9-18%，直接改变rNPV估值参数",
        },
        {
            "k_code": "k124",
            "name": "合成生物赋能生物制造",
            "boost": 0.3,
            "valid_until": "2027-12-31",
            "detail": "合成生物是创新药管线重要使能技术，rNPV框架可应用于合成生物产品商业化估值",
        },
    ],
    "AI算力": [
        {
            "k_code": "k094",
            "name": "AI应用层从基建向落地迁移",
            "boost": 0.8,
            "valid_until": "2027-06-30",
            "detail": "AI从模型训练转向应用部署，SaaS/Agent/多模态应用进入商业化拐点",
        },
        {
            "k_code": "k126",
            "name": "具身智能VLA模型突破",
            "boost": 0.6,
            "valid_until": "2027-12-31",
            "detail": "具身智能是AI从虚拟走向物理世界的终极载体，VLA模型是核心使能技术",
        },
        {
            "k_code": "k125",
            "name": "脑机接口+大模型融合",
            "boost": 0.4,
            "valid_until": "2027-12-31",
            "detail": "脑机接口+大模型=通用神经信号预训练，AI从虚拟走向物理世界的关键路径",
        },
    ],
    "具身智能": [
        {
            "k_code": "k126",
            "name": "人形机器人产业化加速",
            "boost": 0.9,
            "valid_until": "2027-12-31",
            "detail": "2026年融资数据+马太效应分析，VLA模型驱动机器人从demo走向量产",
        },
        {
            "k_code": "k125",
            "name": "脑机+具身=神经假肢/外骨骼",
            "boost": 0.4,
            "valid_until": "2027-12-31",
            "detail": "脑机接口与具身智能交汇，神经假肢/外骨骼/人机融合场景",
        },
    ],
    "军工": [
        {
            "k_code": "k098",
            "name": "国防产业链现代化加速",
            "boost": 0.6,
            "valid_until": "2027-06-30",
            "detail": "军工产业链从传统装备向信息化/智能化升级，无人机/卫星/电子战需求增长",
        },
        {
            "k_code": "k122",
            "name": "低空经济军民融合",
            "boost": 0.4,
            "valid_until": "2027-06-30",
            "detail": "低空经济与军用无人机技术同源，eVTOL适航认证体系独立于军品",
        },
    ],
    "商业航天": [
        {
            "k_code": "k118",
            "name": "商业航天发射成本下降",
            "boost": 0.7,
            "valid_until": "2027-12-31",
            "detail": "可回收火箭+卫星互联网驱动商业航天从政府主导向商业化转型",
        },
        {
            "k_code": "k122",
            "name": "低空经济基础设施共建",
            "boost": 0.3,
            "valid_until": "2027-06-30",
            "detail": "通用航空ETF与低空经济高度重叠，空域管理改革推进",
        },
    ],
    "低空经济": [
        {
            "k_code": "k122",
            "name": "eVTOL适航认证+空域改革",
            "boost": 0.8,
            "valid_until": "2027-06-30",
            "detail": "eVTOL适航认证体系推进，低空智联网依赖AI调度算法和集群控制技术",
        },
        {
            "k_code": "k090",
            "name": "动力电池跨界eVTOL",
            "boost": 0.3,
            "valid_until": "2027-06-30",
            "detail": "动力电池是eVTOL核心零部件，与新能源车共享供应链但标准更严苛",
        },
    ],
    "量子计算": [
        {
            "k_code": "k117",
            "name": "量子计算商业化前夜",
            "boost": 0.6,
            "valid_until": "2027-12-31",
            "detail": "量子计算+量子通信进入工程化阶段，金融/制药/材料模拟场景率先落地",
        },
    ],
    "AI4S": [
        {
            "k_code": "k123",
            "name": "AI for Science垂直应用爆发",
            "boost": 0.7,
            "valid_until": "2027-12-31",
            "detail": "AI4S在药物发现/材料设计/蛋白质折叠领域取得实证突破，改变研发范式",
        },
    ],
    "合成生物": [
        {
            "k_code": "k124",
            "name": "合成生物产业化加速",
            "boost": 0.6,
            "valid_until": "2027-12-31",
            "detail": "生物基材料替代石化材料是双碳目标下长期趋势，与光伏/锂电形成互补",
        },
    ],
    "脑机接口": [
        {
            "k_code": "k125",
            "name": "BCI临床+消费双轮驱动",
            "boost": 0.6,
            "valid_until": "2027-12-31",
            "detail": "脑机接口从医疗康复向消费级扩展，大模型赋能神经信号解码",
        },
    ],
}

# 负面催化剂(风险因子)
RISK_FACTORS: dict[str, list[dict[str, Any]]] = {
    "半导体": [
        {
            "k_code": "k053",
            "name": "估值PE近历史高位",
            "penalty": 0.4,
            "valid_until": "2026-12-31",
            "detail": "半导体设备指数年内+52%，估值已近历史高位，需警惕回调",
        },
    ],
    "AI算力": [
        {
            "k_code": "k094",
            "name": "AI应用商业化不及预期",
            "penalty": 0.3,
            "valid_until": "2026-12-31",
            "detail": "AI应用层从demo到规模化收入仍有gap，部分场景ROI不清晰",
        },
    ],
    "新能源": [
        {
            "k_code": "k090",
            "name": "碳酸锂价格波动风险",
            "penalty": 0.3,
            "valid_until": "2026-12-31",
            "detail": "锂价从5.8万反弹至17.5万后波动加大，上游利润修复但下游成本承压",
        },
    ],
}

# 低置信度KB研究后备: 无强催化剂sector的中性KB覆盖(不加boost, 仅记录研究深度)
FALLBACK_NOTES: dict[str, dict[str, str]] = {
    "中概互联网": {"k_code": "k094", "note": "平台经济AI商业化+互联互通深化"},
    "中盘成长": {"k_code": "k042", "note": "中证500/1000因子轮动中性"},
    "保险": {"k_code": "k192", "note": "险资权益配置+长端利率敏感"},
    "信用债": {"k_code": "k044", "note": "信用利差低位+城投化债"},
    "全市场": {"k_code": "k260", "note": "全球ETF资金流中性配置"},
    "公用事业": {"k_code": "k090", "note": "电力市场化改革+绿电消纳"},
    "其他": {"k_code": "k260", "note": "无明确KB催化剂"},
    "农产品": {"k_code": "k089", "note": "粮食安全+生物育种政策"},
    "利率债": {"k_code": "k089", "note": "货币宽松预期+久期策略"},
    "通信/5G": {"k_code": "k094", "note": "5G-A+卫星互联网基建"},
    "云计算/算力": {"k_code": "k094", "note": "东数西算+AI推理算力需求"},
    "周期/资源": {"k_code": "k100", "note": "供给侧改革+有色/稀土出口管制"},
    "基建/地产": {"k_code": "k089", "note": "专项债加速+REITs扩容"},
    "大盘蓝筹": {"k_code": "k046", "note": "沪深300被动资金流入"},
    "央企改革": {"k_code": "k089", "note": "央企市值管理+专业化整合"},
    "家电": {"k_code": "k089", "note": "以旧换新补贴+出海"},
    "宽基": {"k_code": "k044", "note": "指数化投资长期趋势"},
    "小盘价值": {"k_code": "k042", "note": "小盘价值因子中性"},
    "成长股": {"k_code": "k042", "note": "成长因子轮动中性"},
    "白酒消费": {"k_code": "k089", "note": "消费复苏偏弱+库存去化"},
    "硬科技": {"k_code": "k053", "note": "硬科技自主可控长期主题"},
    "硬科技做空": {"k_code": "k053", "note": "杠杆/做空工具, 反向暴露硬科技"},
    "硬科技杠杆": {"k_code": "k053", "note": "杠杆工具, 放大硬科技波动"},
    "港股科技": {"k_code": "k094", "note": "港股科技AI monetization+南向资金"},
    "港股综合": {"k_code": "k260", "note": "港股互联互通中性"},
    "美股科技": {"k_code": "k094", "note": "北美云厂商CapEx超级周期"},
    "美股科技100": {"k_code": "k094", "note": "纳指100 AI权重集中"},
    "美股综合": {"k_code": "k260", "note": "美股宽基中性配置"},
    "美股杠杆": {"k_code": "k260", "note": "杠杆工具放大美股波动"},
    "能源化工": {"k_code": "k100", "note": "油价中枢+化工品价差"},
    "货币": {"k_code": "k044", "note": "货币基金现金管理工具"},
    "货币基金": {"k_code": "k044", "note": "货币基金现金管理工具"},
    "跨境": {"k_code": "k260", "note": "跨境配置分散化"},
    "金融": {"k_code": "k192", "note": "资本市场改革+券商并购重组"},
    "食品饮料": {"k_code": "k089", "note": "消费复苏+必选消费防御"},
    "高股息": {"k_code": "k046", "note": "险资+长期资金高股息偏好"},
    "红利/价值": {"k_code": "k046", "note": "红利策略+低波因子防御属性"},
    "综合": {"k_code": "k260", "note": "综合类ETF中性配置"},
    "贵金属": {"k_code": "k100", "note": "黄金避险+央行购金+美元信用对冲"},
    "半导体做空": {"k_code": "k053", "note": "做空工具, 反向暴露半导体"},
    "半导体杠杆": {"k_code": "k053", "note": "杠杆工具, 放大半导体波动"},
    "可转债": {"k_code": "k044", "note": "股债 hybrid 中性"},
    "券商": {"k_code": "k192", "note": "资本市场改革+并购重组"},
    "消费": {"k_code": "k089", "note": "以旧换新+服务消费复苏"},
    "有色金属": {"k_code": "k100", "note": "铜/稀土供给约束+新能源需求"},
    "机器人/智造": {"k_code": "k126", "note": "制造业智能化+人形机器人"},
}


def _today() -> date:
    return date.today()


def _is_valid(valid_until: str) -> bool:
    """催化剂是否在有效期内."""
    try:
        return datetime.strptime(valid_until, "%Y-%m-%d").date() >= _today()
    except ValueError:
        return True  # 无日期=永久有效


def _normalize_sector(sector: str) -> str:
    """sector别名→标准sector."""
    return SECTOR_ALIASES.get(sector, sector)


def _active_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """过滤过期催化剂."""
    return [item for item in items if _is_valid(item.get("valid_until", "2099-12-31"))]


def score_l34_layer(sector: str) -> dict[str, Any]:
    """L34 KB Catalyst评分.

    Returns:
        {
            "score": float,          # 0-10
            "detail": {
                "catalysts": [...],   # 正面催化剂
                "risks": [...],       # 风险因子
                "kb_depth": int,      # 支撑KB数量
                "raw_boost": float,   # 原始boost
                "sectors_matched": list,
            }
        }
    """
    norm = _normalize_sector(sector)
    catalysts = _active_items(CATALYSTS.get(norm, []))
    risks = _active_items(RISK_FACTORS.get(norm, []))
    fallback = FALLBACK_NOTES.get(norm)

    raw_boost = sum(c.get("boost", 0.0) for c in catalysts)
    raw_penalty = sum(r.get("penalty", 0.0) for r in risks)
    net = raw_boost - raw_penalty

    # 多KB交叉支撑加分(最多+0.3)
    kb_codes = {c["k_code"] for c in catalysts} | {r["k_code"] for r in risks}
    depth_bonus = min(0.3, 0.1 * max(0, len(kb_codes) - 1))

    # 无催化剂sector: 记录KB研究覆盖但不改变评分(保持5.0中性)
    if not catalysts and not risks and fallback:
        kb_codes = {fallback["k_code"]}

    # clip: 中心5.0，微调±2.0
    clipped = max(-2.0, min(2.0, net + depth_bonus))
    score = round(max(0.0, min(10.0, 5.0 + clipped)), 2)

    detail = {
        "catalysts": [
            {"k_code": c["k_code"], "name": c["name"], "boost": c["boost"], "detail": c["detail"]}
            for c in catalysts
        ],
        "risks": [
            {"k_code": r["k_code"], "name": r["name"], "penalty": r["penalty"], "detail": r["detail"]}
            for r in risks
        ],
        "kb_depth": len(kb_codes),
        "raw_boost": round(raw_boost, 2),
        "raw_penalty": round(raw_penalty, 2),
        "net_adjustment": round(clipped, 2),
        "sectors_matched": [norm] if (catalysts or risks or fallback) else [],
        "fallback_note": fallback.get("note") if fallback and not catalysts and not risks else None,
    }

    return {"score": score, "detail": detail}


def get_kb_catalyst_summary(sector: str) -> str:
    """生成L34催化剂摘要(供报告展示)."""
    result = score_l34_layer(sector)
    detail = result["detail"]
    if not detail["catalysts"] and not detail["risks"]:
        return "L34: 无KB催化剂信号"

    parts = [f"L34={result['score']:.1f}"]
    for c in detail["catalysts"][:3]:
        parts.append(f"+{c['boost']:.1f} {c['name']}({c['k_code']})")
    for r in detail["risks"][:2]:
        parts.append(f"-{r['penalty']:.1f} {r['name']}({r['k_code']})")
    return " | ".join(parts)


# CLI入口
if __name__ == "__main__":
    test_sectors = ["半导体", "新能源", "医药", "AI算力", "具身智能", "军工", "商业航天", "低空经济"]
    for s in test_sectors:
        r = score_l34_layer(s)
        d = r["detail"]
        cats = len(d["catalysts"])
        risks = len(d["risks"])
        print(f"{s:8s} score={r['score']:.2f} cats={cats} risks={risks} kb={d['kb_depth']} net={d['net_adjustment']:+.2f}")
