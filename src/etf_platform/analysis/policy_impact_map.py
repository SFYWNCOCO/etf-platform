# -*- coding: utf-8 -*-
"""Policy Impact Map — 政策冲击分类与行业ETF影响映射表。

从 k192-policy-shock-transmission-quantification.md 提取的规则：

政策冲击谱系:
    ├── 货币政策冲击 (Monetary Policy Shocks)
    │   ├── 基准利率调整 → 利率敏感型ETF(银行/地产)
    │   ├── MLF/逆回购操作 → 流动性敏感型ETF
    │   ├── QE/QT → 成长股/债券ETF分化
    │   └── 汇率政策 → 外贸/进口依赖型ETF
    ├── 财政政策冲击 (Fiscal Policy Shocks)
    │   ├── 基建投资/减税 → 建筑/建材/消费ETF
    │   ├── 产业补贴 → 新能源/半导体/医药ETF
    │   ├── 消费券/以旧换新 → 家电/汽车/零售ETF
    │   └── 地方债发行 → 银行/城投相关ETF
    ├── 贸易政策冲击 (Trade Policy Shocks)
    │   ├── 关税 → 进出口产业链ETF
    │   ├── 制裁/出口管制 → 科技/军工ETF
    │   ├── RCEP/FTA → 区域贸易ETF
    │   └── 贸易顺差变化 → 外汇/商品ETF
    ├── 产业政策冲击 (Industrial Policy Shocks)
    │   ├── 行业标准/准入 → 特定行业ETF
    │   ├── 反垄断 → 互联网平台ETF
    │   ├── 数据安全 → AI/云计算ETF
    │   └── ESG合规 → 绿色能源/传统能源ETF
    └── 监管政策冲击 (Regulatory Shocks)
        ├── 金融监管 → 券商/银行ETF
        ├── 医药集采 → 创新药/仿制药ETF分化
        └── 教育"双减" → 教育ETF崩塌

集成: 供 L12_PoliticalRisk 层调用，输出 affected sectors + impact direction + magnitude estimate。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Tuple


# ═══════════════════════════════════════════════════════════
# Enums & Data Classes
# ═══════════════════════════════════════════════════════════


class PolicyShockType(str, Enum):
    """政策冲击一级分类。"""
    MONETARY = "monetary"           # 货币政策冲击
    FISCAL = "fiscal"               # 财政政策冲击
    TRADE = "trade"                 # 贸易政策冲击
    INDUSTRIAL = "industrial"       # 产业政策冲击
    REGULATORY = "regulatory"       # 监管政策冲击


class PolicySubtype(str, Enum):
    """政策冲击二级分类。"""
    # Monetary
    RATE_CUT = "rate_cut"           # 基准利率下调
    RATE_HIKE = "rate_hike"         # 基准利率上调
    MLF_OPE = "mlf_ope"             # MLF/逆回购操作
    QE_QT = "qe_qt"                 # QE/QT
    FX_POLICY = "fx_policy"         # 汇率政策

    # Fiscal
    INFRA_INVEST = "infra_invest"   # 基建投资
    TAX_CUT = "tax_cut"             # 减税
    INDUSTRY_SUBSIDY = "industry_subsidy"  # 产业补贴
    CONSUMPTION_VOUCHER = "consumption_voucher"  # 消费券/以旧换新
    LOCAL_DEBT = "local_debt"       # 地方债发行

    # Trade
    TARIFF = "tariff"               # 关税
    SANCTIONS = "sanctions"         # 制裁/出口管制
    RCEP_FTA = "rcep_ftp"          # RCEP/FTA
    TRADE_SURPLUS = "trade_surplus"  # 贸易顺差变化

    # Industrial
    STANDARDS = "standards"         # 行业标准/准入
    ANTITRUST = "antitrust"         # 反垄断
    DATA_SECURITY = "data_security"  # 数据安全
    ESG_COMPLIANCE = "esg_compliance"  # ESG合规

    # Regulatory
    FINANCIAL_REGULATION = "financial_regulation"  # 金融监管
    MEDICAL_PROCUREMENT = "medical_procurement"  # 医药集采
    EDUCATION_DUAL = "education_dual"            # 教育双减


class ImpactDirection(str, Enum):
    """政策对行业的影响方向。"""
    POSITIVE = "positive"           # 利好
    NEGATIVE = "negative"           # 利空
    NEUTRAL = "neutral"             # 中性/无明显影响
    MIXED = "mixed"                 # 双向分化/待观察


@dataclass
class SectorImpact:
    """单个行业受政策冲击的影响估计。"""
    sector: str
    direction: ImpactDirection
    magnitude: float                # 影响强度 [-1.0, 1.0], 正值利好，负值利空
    confidence: float = 0.7         # 置信度 [0, 1]
    transmission_path: str = ""     # 传导路径描述
    time_horizon: str = "short"     # short/medium/long

    def to_dict(self) -> Dict[str, object]:
        return {
            "sector": self.sector,
            "direction": self.direction.value,
            "magnitude": self.magnitude,
            "confidence": self.confidence,
            "transmission_path": self.transmission_path,
            "time_horizon": self.time_horizon,
        }


@dataclass
class PolicyEvent:
    """政策事件结构。"""
    event_id: str
    date: str
    type: PolicyShockType
    subtype: PolicySubtype
    description: str
    affected_sectors: List[str] = field(default_factory=list)
    expected_magnitude: Dict[str, float] = field(default_factory=dict)
    status: str = "pending"         # pending/active/resolved


# ═══════════════════════════════════════════════════════════
# Policy → Sector Impact Mapping Table
# ═══════════════════════════════════════════════════════════

POLICY_IMPACT_MAP: Dict[PolicySubtype, List[SectorImpact]] = {
    # === 货币政策冲击 ===
    PolicySubtype.RATE_CUT: [
        SectorImpact(
            sector="银行",
            direction=ImpactDirection.NEGATIVE,
            magnitude=-0.3,
            confidence=0.85,
            transmission_path="利率↓ → 净息差收窄 → 银行利润承压",
            time_horizon="short",
        ),
        SectorImpact(
            sector="房地产",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.5,
            confidence=0.8,
            transmission_path="利率↓ → 房贷成本↓ → 购房需求↑ → 房企受益",
            time_horizon="medium",
        ),
        SectorImpact(
            sector="科技",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.7,
            confidence=0.75,
            transmission_path="利率↓ → 折现率↓ → 成长股估值↑",
            time_horizon="medium",
        ),
        SectorImpact(
            sector="AI/科技",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.7,
            confidence=0.75,
            transmission_path="利率↓ → 折现率↓ → 成长股估值↑",
            time_horizon="medium",
        ),
        SectorImpact(
            sector="半导体",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.6,
            confidence=0.7,
            transmission_path="利率↓ → 科技成长估值修复",
            time_horizon="medium",
        ),
        SectorImpact(
            sector="债券",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.6,
            confidence=0.9,
            transmission_path="利率↓ → 债券价格↑",
            time_horizon="short",
        ),
        SectorImpact(
            sector="新能源",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.5,
            confidence=0.7,
            transmission_path="利率↓ → 融资成本↓ → 资本开支↑ → 新能源项目受益",
            time_horizon="medium",
        ),
        SectorImpact(
            sector="消费",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.4,
            confidence=0.65,
            transmission_path="利率↓ → 消费信贷成本↓ → 消费需求↑",
            time_horizon="medium",
        ),
    ],

    PolicySubtype.RATE_HIKE: [
        SectorImpact(
            sector="银行",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.3,
            confidence=0.8,
            transmission_path="利率↑ → 净息差改善 → 银行利润↑",
            time_horizon="short",
        ),
        SectorImpact(
            sector="房地产",
            direction=ImpactDirection.NEGATIVE,
            magnitude=-0.5,
            confidence=0.85,
            transmission_path="利率↑ → 房贷成本↑ → 购房需求↓ → 房企承压",
            time_horizon="medium",
        ),
        SectorImpact(
            sector="科技",
            direction=ImpactDirection.NEGATIVE,
            magnitude=-0.7,
            confidence=0.75,
            transmission_path="利率↑ → 折现率↑ → 成长股估值↓",
            time_horizon="medium",
        ),
        SectorImpact(
            sector="AI/科技",
            direction=ImpactDirection.NEGATIVE,
            magnitude=-0.7,
            confidence=0.75,
            transmission_path="利率↑ → 折现率↑ → 成长股估值↓",
            time_horizon="medium",
        ),
        SectorImpact(
            sector="债券",
            direction=ImpactDirection.NEGATIVE,
            magnitude=-0.6,
            confidence=0.9,
            transmission_path="利率↑ → 债券价格↓",
            time_horizon="short",
        ),
        SectorImpact(
            sector="新能源",
            direction=ImpactDirection.NEGATIVE,
            magnitude=-0.4,
            confidence=0.7,
            transmission_path="利率↑ → 融资成本↑ → 资本开支↓",
            time_horizon="medium",
        ),
    ],

    PolicySubtype.MLF_OPE: [
        SectorImpact(
            sector="宽基",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.3,
            confidence=0.6,
            transmission_path="MLF/逆回购 → 流动性注入 → 市场情绪改善",
            time_horizon="short",
        ),
        SectorImpact(
            sector="全市场",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.3,
            confidence=0.6,
            transmission_path="流动性宽松 → 风险偏好↑",
            time_horizon="short",
        ),
        SectorImpact(
            sector="券商",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.4,
            confidence=0.7,
            transmission_path="流动性↑ → 交易量↑ → 券商受益于经纪业务",
            time_horizon="short",
        ),
    ],

    PolicySubtype.QE_QT: [
        SectorImpact(
            sector="成长股",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.6,
            confidence=0.7,
            transmission_path="QE → 流动性泛滥 → 成长股估值扩张",
            time_horizon="medium",
        ),
        SectorImpact(
            sector="中盘成长",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.6,
            confidence=0.65,
            transmission_path="QE → 风险资产偏好↑",
            time_horizon="medium",
        ),
        SectorImpact(
            sector="债券",
            direction=ImpactDirection.NEGATIVE,
            magnitude=-0.4,
            confidence=0.7,
            transmission_path="QE → 债券被买入 → 收益率↓ → 后续QT时债券承压",
            time_horizon="long",
        ),
        SectorImpact(
            sector="黄金",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.5,
            confidence=0.75,
            transmission_path="QE → 通胀预期↑ → 黄金抗通胀属性",
            time_horizon="medium",
        ),
    ],

    PolicySubtype.FX_POLICY: [
        SectorImpact(
            sector="出口",
            direction=ImpactDirection.NEGATIVE,
            magnitude=-0.4,
            confidence=0.6,
            transmission_path="本币贬值 → 出口竞争力↑但汇率波动风险↑",
            time_horizon="short",
        ),
        SectorImpact(
            sector="进口依赖",
            direction=ImpactDirection.NEGATIVE,
            magnitude=-0.5,
            confidence=0.7,
            transmission_path="本币贬值 → 进口成本↑ → 依赖进口的行业承压",
            time_horizon="short",
        ),
        SectorImpact(
            sector="跨境",
            direction=ImpactDirection.NEGATIVE,
            magnitude=-0.3,
            confidence=0.65,
            transmission_path="汇率波动 → 跨境资本流动不确定性↑",
            time_horizon="short",
        ),
        SectorImpact(
            sector="港股科技",
            direction=ImpactDirection.NEGATIVE,
            magnitude=-0.4,
            confidence=0.6,
            transmission_path="汇率政策 → 港股资金面波动",
            time_horizon="short",
        ),
    ],

    # === 财政政策冲击 ===
    PolicySubtype.INFRA_INVEST: [
        SectorImpact(
            sector="基建",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.7,
            confidence=0.85,
            transmission_path="基建投资↑ → 订单↑ → 建筑/建材企业受益",
            time_horizon="medium",
        ),
        SectorImpact(
            sector="建材",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.6,
            confidence=0.8,
            transmission_path="基建投资↑ → 水泥/钢铁/玻璃需求↑",
            time_horizon="medium",
        ),
        SectorImpact(
            sector="钢铁",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.5,
            confidence=0.75,
            transmission_path="基建投资↑ → 钢材需求↑",
            time_horizon="medium",
        ),
        SectorImpact(
            sector="消费",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.4,
            confidence=0.6,
            transmission_path="基建投资↑ → 就业↑ → 消费信心↑",
            time_horizon="long",
        ),
        SectorImpact(
            sector="有色金属",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.5,
            confidence=0.7,
            transmission_path="基建投资↑ → 铜铝等工业金属需求↑",
            time_horizon="medium",
        ),
    ],

    PolicySubtype.TAX_CUT: [
        SectorImpact(
            sector="消费",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.5,
            confidence=0.75,
            transmission_path="减税 → 居民可支配收入↑ → 消费↑",
            time_horizon="medium",
        ),
        SectorImpact(
            sector="白酒消费",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.4,
            confidence=0.7,
            transmission_path="消费税改革预期 → 白酒板块受益",
            time_horizon="short",
        ),
        SectorImpact(
            sector="家电",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.4,
            confidence=0.65,
            transmission_path="减税 → 耐用消费品需求↑",
            time_horizon="medium",
        ),
        SectorImpact(
            sector="汽车",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.5,
            confidence=0.7,
            transmission_path="购置税减免 → 汽车消费↑",
            time_horizon="short",
        ),
        SectorImpact(
            sector="新能源",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.6,
            confidence=0.75,
            transmission_path="新能源汽车免税延续 → 销量↑",
            time_horizon="medium",
        ),
    ],

    PolicySubtype.INDUSTRY_SUBSIDY: [
        SectorImpact(
            sector="新能源",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.7,
            confidence=0.8,
            transmission_path="产业补贴 → 直接降低成本 → 装机量/销量↑",
            time_horizon="medium",
        ),
        SectorImpact(
            sector="新能源车",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.7,
            confidence=0.8,
            transmission_path="购车补贴 → 销量↑",
            time_horizon="short",
        ),
        SectorImpact(
            sector="光伏",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.6,
            confidence=0.75,
            transmission_path="光伏补贴 → 装机量↑",
            time_horizon="medium",
        ),
        SectorImpact(
            sector="风电",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.6,
            confidence=0.7,
            transmission_path="风电补贴 → 装机量↑",
            time_horizon="medium",
        ),
        SectorImpact(
            sector="储能",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.6,
            confidence=0.7,
            transmission_path="储能补贴 → 项目建设↑",
            time_horizon="medium",
        ),
        SectorImpact(
            sector="锂电池",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.6,
            confidence=0.75,
            transmission_path="新能源补贴 → 电池需求↑",
            time_horizon="medium",
        ),
        SectorImpact(
            sector="半导体",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.7,
            confidence=0.7,
            transmission_path="芯片补贴 → 研发投入↑ → 产能扩张",
            time_horizon="long",
        ),
        SectorImpact(
            sector="医药",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.5,
            confidence=0.7,
            transmission_path="创新药补贴 → 研发激励↑",
            time_horizon="long",
        ),
        SectorImpact(
            sector="创新药",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.6,
            confidence=0.7,
            transmission_path="医保谈判/创新药补贴 → 研发回报↑",
            time_horizon="medium",
        ),
        SectorImpact(
            sector="AI/科技",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.6,
            confidence=0.65,
            transmission_path="AI产业政策 → 算力/算法投资↑",
            time_horizon="long",
        ),
    ],

    PolicySubtype.CONSUMPTION_VOUCHER: [
        SectorImpact(
            sector="消费",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.6,
            confidence=0.8,
            transmission_path="消费券 → 直接刺激消费需求",
            time_horizon="short",
        ),
        SectorImpact(
            sector="家电",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.7,
            confidence=0.85,
            transmission_path="以旧换新补贴 → 家电销量↑",
            time_horizon="short",
        ),
        SectorImpact(
            sector="汽车",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.6,
            confidence=0.8,
            transmission_path="购车补贴 → 汽车销量↑",
            time_horizon="short",
        ),
        SectorImpact(
            sector="零售",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.5,
            confidence=0.75,
            transmission_path="消费券 → 零售额↑",
            time_horizon="short",
        ),
        SectorImpact(
            sector="食品饮料",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.4,
            confidence=0.7,
            transmission_path="消费券 → 食品餐饮需求↑",
            time_horizon="short",
        ),
    ],

    PolicySubtype.LOCAL_DEBT: [
        SectorImpact(
            sector="银行",
            direction=ImpactDirection.MIXED,
            magnitude=+0.2,
            confidence=0.6,
            transmission_path="地方债发行 → 银行配置需求↑但信用风险需观察",
            time_horizon="medium",
        ),
        SectorImpact(
            sector="城投",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.5,
            confidence=0.7,
            transmission_path="地方债发行 → 城投融资环境改善",
            time_horizon="short",
        ),
        SectorImpact(
            sector="基建",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.6,
            confidence=0.75,
            transmission_path="地方债 → 基建项目资金到位 → 订单↑",
            time_horizon="medium",
        ),
    ],

    # === 贸易政策冲击 ===
    PolicySubtype.TARIFF: [
        SectorImpact(
            sector="出口",
            direction=ImpactDirection.NEGATIVE,
            magnitude=-0.8,
            confidence=0.9,
            transmission_path="关税↑ → 出口成本↑ → 海外订单↓",
            time_horizon="short",
        ),
        SectorImpact(
            sector="半导体",
            direction=ImpactDirection.NEGATIVE,
            magnitude=-0.6,
            confidence=0.7,
            transmission_path="关税 → 出口受限 → 收入承压",
            time_horizon="short",
        ),
        SectorImpact(
            sector="通信/5G",
            direction=ImpactDirection.NEGATIVE,
            magnitude=-0.5,
            confidence=0.65,
            transmission_path="关税 → 设备出口受阻",
            time_horizon="short",
        ),
        SectorImpact(
            sector="国内替代",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.7,
            confidence=0.75,
            transmission_path="关税 → 进口替代加速 → 国产替代受益",
            time_horizon="medium",
        ),
        SectorImpact(
            sector="有色金属",
            direction=ImpactDirection.NEGATIVE,
            magnitude=-0.5,
            confidence=0.7,
            transmission_path="关税 → 全球贸易摩擦 → 工业金属需求↓",
            time_horizon="short",
        ),
    ],

    PolicySubtype.SANCTIONS: [
        SectorImpact(
            sector="半导体",
            direction=ImpactDirection.NEGATIVE,
            magnitude=-0.7,
            confidence=0.85,
            transmission_path="制裁/出口管制 → 高端芯片断供 → 半导体产业链承压",
            time_horizon="medium",
        ),
        SectorImpact(
            sector="半导体设备",
            direction=ImpactDirection.NEGATIVE,
            magnitude=-0.6,
            confidence=0.8,
            transmission_path="设备出口管制 → 扩产受阻",
            time_horizon="medium",
        ),
        SectorImpact(
            sector="军工",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.6,
            confidence=0.75,
            transmission_path="地缘紧张 → 国防开支↑ → 军工受益",
            time_horizon="long",
        ),
        SectorImpact(
            sector="AI/科技",
            direction=ImpactDirection.NEGATIVE,
            magnitude=-0.5,
            confidence=0.7,
            transmission_path="技术封锁 → 算力/AI发展受限",
            time_horizon="medium",
        ),
        SectorImpact(
            sector="自主可控",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.8,
            confidence=0.75,
            transmission_path="制裁 → 国产替代加速 → 自主可控主题受益",
            time_horizon="long",
        ),
    ],

    PolicySubtype.RCEP_FTA: [
        SectorImpact(
            sector="出口",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.5,
            confidence=0.7,
            transmission_path="FTA → 关税降低 → 出口竞争力↑",
            time_horizon="medium",
        ),
        SectorImpact(
            sector="跨境",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.4,
            confidence=0.65,
            transmission_path="RCEP → 区域内贸易便利化",
            time_horizon="long",
        ),
        SectorImpact(
            sector="家电",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.4,
            confidence=0.6,
            transmission_path="RCEP → 东盟出口↑",
            time_horizon="medium",
        ),
        SectorImpact(
            sector="汽车",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.5,
            confidence=0.65,
            transmission_path="FTA → 汽车出口关税↓",
            time_horizon="medium",
        ),
    ],

    PolicySubtype.TRADE_SURPLUS: [
        SectorImpact(
            sector="外汇",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.4,
            confidence=0.6,
            transmission_path="贸易顺差↑ → 外汇储备↑ → 本币升值压力",
            time_horizon="short",
        ),
        SectorImpact(
            sector="商品",
            direction=ImpactDirection.MIXED,
            magnitude=0.0,
            confidence=0.5,
            transmission_path="贸易顺差变化 → 大宗商品需求预期变化",
            time_horizon="medium",
        ),
    ],

    # === 产业政策冲击 ===
    PolicySubtype.STANDARDS: [
        SectorImpact(
            sector="特定行业",
            direction=ImpactDirection.MIXED,
            magnitude=0.0,
            confidence=0.5,
            transmission_path="行业标准/准入 → 龙头受益(合规成本门槛)",
            time_horizon="medium",
        ),
        SectorImpact(
            sector="新能源",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.4,
            confidence=0.7,
            transmission_path="新能源标准提升 → 落后产能出清 → 龙头受益",
            time_horizon="medium",
        ),
    ],

    PolicySubtype.ANTITRUST: [
        SectorImpact(
            sector="互联网",
            direction=ImpactDirection.NEGATIVE,
            magnitude=-0.6,
            confidence=0.85,
            transmission_path="反垄断 → 平台企业增速放缓 → 估值承压",
            time_horizon="medium",
        ),
        SectorImpact(
            sector="中概互联网",
            direction=ImpactDirection.NEGATIVE,
            magnitude=-0.5,
            confidence=0.8,
            transmission_path="反垄断 → 中国互联网监管趋严",
            time_horizon="medium",
        ),
        SectorImpact(
            sector="创新",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.3,
            confidence=0.5,
            transmission_path="反垄断 → 长期有利于新进入者/创新生态",
            time_horizon="long",
        ),
    ],

    PolicySubtype.DATA_SECURITY: [
        SectorImpact(
            sector="AI/科技",
            direction=ImpactDirection.MIXED,
            magnitude=-0.2,
            confidence=0.6,
            transmission_path="数据安全法 → 数据使用受限但长期利好合规企业",
            time_horizon="medium",
        ),
        SectorImpact(
            sector="云计算/算力",
            direction=ImpactDirection.MIXED,
            magnitude=-0.1,
            confidence=0.6,
            transmission_path="数据安全 → 云服务商合规成本↑但需求↑",
            time_horizon="medium",
        ),
        SectorImpact(
            sector="网络安全",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.7,
            confidence=0.85,
            transmission_path="数据安全 → 安全支出↑ → 网安企业受益",
            time_horizon="medium",
        ),
    ],

    PolicySubtype.ESG_COMPLIANCE: [
        SectorImpact(
            sector="绿色能源",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.6,
            confidence=0.8,
            transmission_path="ESG合规 → 绿色产业补贴/税收优惠 → 新能源受益",
            time_horizon="long",
        ),
        SectorImpact(
            sector="煤炭",
            direction=ImpactDirection.NEGATIVE,
            magnitude=-0.5,
            confidence=0.75,
            transmission_path="ESG → 高碳行业融资限制 → 煤炭承压",
            time_horizon="long",
        ),
        SectorImpact(
            sector="传统能源",
            direction=ImpactDirection.NEGATIVE,
            magnitude=-0.4,
            confidence=0.7,
            transmission_path="ESG → 化石能源披露要求↑ → 估值折扣",
            time_horizon="long",
        ),
        SectorImpact(
            sector="高股息",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.3,
            confidence=0.6,
            transmission_path="ESG → 投资者偏好稳定现金流企业",
            time_horizon="medium",
        ),
    ],

    # === 监管政策冲击 ===
    PolicySubtype.FINANCIAL_REGULATION: [
        SectorImpact(
            sector="券商",
            direction=ImpactDirection.NEGATIVE,
            magnitude=-0.4,
            confidence=0.8,
            transmission_path="金融监管 → 券商合规成本↑ → 短期利润承压",
            time_horizon="short",
        ),
        SectorImpact(
            sector="银行",
            direction=ImpactDirection.NEGATIVE,
            magnitude=-0.3,
            confidence=0.75,
            transmission_path="金融监管 → 信贷约束↑ → 银行放贷受限",
            time_horizon="short",
        ),
        SectorImpact(
            sector="互联网金融",
            direction=ImpactDirection.NEGATIVE,
            magnitude=-0.6,
            confidence=0.85,
            transmission_path="监管趋严 → 互金业务受限",
            time_horizon="short",
        ),
        SectorImpact(
            sector="保险",
            direction=ImpactDirection.NEGATIVE,
            magnitude=-0.2,
            confidence=0.6,
            transmission_path="金融监管 → 产品规范 → 短期增速放缓",
            time_horizon="short",
        ),
    ],

    PolicySubtype.MEDICAL_PROCUREMENT: [
        SectorImpact(
            sector="创新药",
            direction=ImpactDirection.NEGATIVE,
            magnitude=-0.6,
            confidence=0.85,
            transmission_path="集采 → 药品价格↓ → 药企利润承压",
            time_horizon="short",
        ),
        SectorImpact(
            sector="医药",
            direction=ImpactDirection.NEGATIVE,
            magnitude=-0.4,
            confidence=0.7,
            transmission_path="集采扩围 → 仿制药/成熟品种价格↓",
            time_horizon="short",
        ),
        SectorImpact(
            sector="医疗器械",
            direction=ImpactDirection.NEGATIVE,
            magnitude=-0.5,
            confidence=0.8,
            transmission_path="集采 → 器械价格↓ → 厂商利润压缩",
            time_horizon="short",
        ),
        SectorImpact(
            sector="中药",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.3,
            confidence=0.65,
            transmission_path="集采对中药影响较小 → 相对受益",
            time_horizon="medium",
        ),
        SectorImpact(
            sector="CXO",
            direction=ImpactDirection.NEGATIVE,
            magnitude=-0.4,
            confidence=0.7,
            transmission_path="医保控费 → 药企研发支出压缩 → CXO订单↓",
            time_horizon="medium",
        ),
    ],

    PolicySubtype.EDUCATION_DUAL: [
        SectorImpact(
            sector="教育",
            direction=ImpactDirection.NEGATIVE,
            magnitude=-0.9,
            confidence=0.95,
            transmission_path="双减 → K12学科培训全面取缔 → 教培企业营收归零",
            time_horizon="short",
        ),
        SectorImpact(
            sector="职业教育",
            direction=ImpactDirection.POSITIVE,
            magnitude=+0.5,
            confidence=0.7,
            transmission_path="政策转向职业教育 → 职教赛道受益",
            time_horizon="medium",
        ),
    ],
}


# ═══════════════════════════════════════════════════════════
# Policy Shock Classification Rules
# ═══════════════════════════════════════════════════════════

POLICY_KEYWORD_MAP: Dict[PolicySubtype, List[str]] = {
    PolicySubtype.RATE_CUT: ["降息", "降准", "LPR下调", "宽松", "降息周期"],
    PolicySubtype.RATE_HIKE: ["加息", "收紧", "LPR上调", "紧缩", "加息周期"],
    PolicySubtype.MLF_OPE: ["MLF", "逆回购", "公开市场操作", "流动性投放"],
    PolicySubtype.QE_QT: ["QE", "量化宽松", "QT", "缩表", "美联储"],
    PolicySubtype.FX_POLICY: ["汇率", "外汇", "央行汇率", "人民币"],

    PolicySubtype.INFRA_INVEST: ["基建", "基础设施", "专项债", "铁公基"],
    PolicySubtype.TAX_CUT: ["减税", "降费", "税收优惠", "增值税减免"],
    PolicySubtype.INDUSTRY_SUBSIDY: ["补贴", "产业扶持", "新能源补贴", "芯片补贴"],
    PolicySubtype.CONSUMPTION_VOUCHER: ["消费券", "以旧换新", "促消费"],
    PolicySubtype.LOCAL_DEBT: ["地方债", "城投债", "专项债发行"],

    PolicySubtype.TARIFF: ["关税", "贸易战", "进出口税"],
    PolicySubtype.SANCTIONS: ["制裁", "出口管制", "实体清单", "tech ban"],
    PolicySubtype.RCEP_FTA: ["RCEP", "FTA", "自贸协定", "一带一路"],
    PolicySubtype.TRADE_SURPLUS: ["贸易顺差", "出口数据", "进出口"],

    PolicySubtype.STANDARDS: ["行业标准", "准入门槛", "资质要求"],
    PolicySubtype.ANTITRUST: ["反垄断", "防止资本无序扩张", "平台经济监管"],
    PolicySubtype.DATA_SECURITY: ["数据安全", "个人信息保护", "网络安全法"],
    PolicySubtype.ESG_COMPLIANCE: ["ESG", "碳中和", "碳达峰", "绿色发展"],

    PolicySubtype.FINANCIAL_REGULATION: ["金融监管", "银保监会", "证监会", "整顿金融秩序"],
    PolicySubtype.MEDICAL_PROCUREMENT: ["集采", "带量采购", "医保谈判", "药品降价"],
    PolicySubtype.EDUCATION_DUAL: ["双减", "K12培训", "教培", "学科类培训"],
}


def classify_policy_event(text: str) -> List[Tuple[PolicySubtype, float]]:
    """基于关键词匹配分类政策事件文本。

    Args:
        text: 政策新闻/公告标题或摘要。

    Returns:
        [(PolicySubtype, confidence), ...] 按置信度降序排列。
    """
    hits: List[Tuple[PolicySubtype, float]] = []

    for subtype, keywords in POLICY_KEYWORD_MAP.items():
        for keyword in keywords:
            if keyword.lower() in text.lower():
                hits.append((subtype, 0.8))
                break

    # 去重并按置信度排序
    seen: set[PolicySubtype] = set()
    unique_hits: List[Tuple[PolicySubtype, float]] = []
    for subtype, conf in sorted(hits, key=lambda x: x[1], reverse=True):
        if subtype not in seen:
            seen.add(subtype)
            unique_hits.append((subtype, conf))

    return unique_hits


def get_affected_sectors(
    policy_subtypes: List[PolicySubtype],
    filter_confidence: float = 0.5,
    top_n: int = 10,
) -> List[SectorImpact]:
    """根据政策子类型列表获取受影响行业及影响估计。

    Args:
        policy_subtypes: 已识别的政策子类型列表。
        filter_confidence: 最低置信度阈值。
        top_n: 返回前N个影响最大的行业。

    Returns:
        按 magnitude 绝对值降序排列的 SectorImpact 列表。
    """
    all_impacts: List[SectorImpact] = []

    for subtype in policy_subtypes:
        impacts = POLICY_IMPACT_MAP.get(subtype, [])
        for impact in impacts:
            if impact.confidence >= filter_confidence:
                all_impacts.append(impact)

    # 按 magnitude 绝对值排序，取 top_n
    all_impacts.sort(key=lambda x: abs(x.magnitude), reverse=True)
    return all_impacts[:top_n]


def calculate_net_sector_exposure(
    policy_subtypes: List[PolicySubtype],
    sector_weights: Dict[str, float],
) -> Dict[str, float]:
    """计算政策冲击下各行业组合的净敞口变化。

    用于 L12 政治风险层的加权评分。

    Args:
        policy_subtypes: 当前政策事件识别出的子类型。
        sector_weights: {sector_name: current_weight} 行业权重字典。

    Returns:
        {sector_name: adjusted_weight} 调整后的行业权重。
    """
    impacts = get_affected_sectors(policy_subtypes, top_n=50)

    # 按行业聚合影响
    sector_agg: Dict[str, float] = {}
    for impact in impacts:
        existing = sector_agg.get(impact.sector, 0.0)
        sector_agg[impact.sector] = existing + impact.magnitude * impact.confidence

    # 调整行业权重
    adjusted_weights = sector_weights.copy()
    for sector, net_impact in sector_agg.items():
        if sector in adjusted_weights:
            adjusted_weights[sector] += net_impact * 0.1  # 温和调整
            adjusted_weights[sector] = max(0.0, min(1.0, adjusted_weights[sector]))

    return adjusted_weights


# ═══════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════

def analyze_policy_shock(text: str, top_n: int = 10) -> Dict[str, object]:
    """分析政策事件文本，返回结构化影响评估。

    这是 L12_PoliticalRisk 层的主要入口函数。

    Args:
        text: 政策新闻/公告标题或摘要。
        top_n: 返回前N个受影响行业。

    Returns:
        {
            'policy_subtypes': [(PolicySubtype, confidence)],
            'affected_sectors': [SectorImpact],
            'overall_sentiment': 'positive'/'negative'/'neutral',
            'risk_level': 'low'/'medium'/'high'/'extreme',
        }
    """
    subtypes = classify_policy_event(text)

    if not subtypes:
        return {
            "policy_subtypes": [],
            "affected_sectors": [],
            "overall_sentiment": "neutral",
            "risk_level": "low",
        }

    affected = get_affected_sectors([s for s, _ in subtypes], top_n=top_n)

    # 计算整体情绪
    avg_magnitude = sum(a.magnitude for a in affected) / len(affected) if affected else 0.0
    if avg_magnitude > 0.2:
        sentiment = "positive"
    elif avg_magnitude < -0.2:
        sentiment = "negative"
    else:
        sentiment = "neutral"

    # 计算风险等级
    max_abs_mag = max(abs(a.magnitude) for a in affected) if affected else 0.0
    if max_abs_mag > 0.7 or any(a.magnitude < -0.7 for a in affected):
        risk_level = "extreme"
    elif max_abs_mag > 0.5 or any(a.magnitude < -0.5 for a in affected):
        risk_level = "high"
    elif max_abs_mag > 0.3 or any(a.magnitude < -0.3 for a in affected):
        risk_level = "medium"
    else:
        risk_level = "low"

    return {
        "policy_subtypes": subtypes,
        "affected_sectors": affected,
        "overall_sentiment": sentiment,
        "risk_level": risk_level,
    }


if __name__ == "__main__":
    test_texts = [
        "央行宣布降息0.2个百分点，释放流动性支持经济增长",
        "国务院印发新能源汽车补贴政策，单车补贴最高2万元",
        "美国对中国半导体实施新的出口管制",
        "国家医保局启动新一轮药品集采，平均降价50%",
        "财政部发行1万亿专项债用于基础设施建设",
        "教育部发布\"双减\"政策，禁止学科类培训机构营利",
    ]

    print("=== Policy Impact Map Analysis ===\n")
    for text in test_texts:
        result = analyze_policy_shock(text)
        print(f"Text: {text}")
        print(f"  Subtypes: {[s.value for s, _ in result['policy_subtypes']]}")
        print(f"  Sentiment: {result['overall_sentiment']}")
        print(f"  Risk Level: {result['risk_level']}")
        print("  Top Affected Sectors:")
        for sec in result['affected_sectors'][:5]:
            print(f"    - {sec.sector}: {sec.direction.value} ({sec.magnitude:+.2f})")
        print()
