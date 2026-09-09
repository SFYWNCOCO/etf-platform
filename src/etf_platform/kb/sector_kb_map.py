"""KB 板块映射 — 高价值产业 KB 按板块归类，供 L34 催化剂与周度推荐消费。

数据来源: ../knowledge 下未集成的高价值行业调查/理论文件，title/source_file
取自每个 k-code 的正式文件（文件名以 k{NNN} 开头）的首个 Markdown H1。
板块口径复用 layers.l34_kb_catalyst.SECTOR_ALIASES，并补充 weekly_top3 的
mega-sector 别名。2026-08-26 T7 批次手工筛选（宁缺毋滥），每条均真实存在于
知识库，且被 get_kb_catalyst_summary / _kb_reasons_for_sector 消费。
"""
from __future__ import annotations

from typing import Any

# 板块 → [{kcode, title, source_file}]。source_file 相对知识库根目录。
SECTOR_KB_CODES: dict[str, list[dict[str, str]]] = {
    "半导体": [
        {"kcode": "k811", "title": "中国半导体产业链 2026H1 深度更新", "source_file": "industry/k811_semiconductor_2026h1_update.md"},
        {"kcode": "k835", "title": "中国半导体 EDA/IP 2026 深度调查", "source_file": "industry/k835_semiconductor_eda_ip_2026.md"},
        {"kcode": "k842", "title": "中国半导体设备 2026 深度调查", "source_file": "industry/k842_semiconductor_equipment_2026.md"},
        {"kcode": "k853", "title": "半导体设备验证进度 2026 深度调查", "source_file": "industry/k853_semiconductor_equipment_validation_deep_dive_2026.md"},
        {"kcode": "k859", "title": "半导体材料 2026深化调查", "source_file": "industry/k859_semiconductor_materials_deep_dive_2026.md"},
        {"kcode": "k866", "title": "半导体材料国产替代 2026深化调查", "source_file": "industry/k866_semiconductor_materials_domestic_substitution_deep_dive_2026.md"},
        {"kcode": "k872", "title": "半导体设备双雄对比 2026深化调查", "source_file": "industry/k872_semiconductor_equipment_dual_comparison_deep_dive_2026.md"},
        {"kcode": "k878", "title": "半导体设备 2026深化调查", "source_file": "industry/k878_semiconductor_equipment_deep_dive_2026.md"},
        {"kcode": "k891", "title": "存储芯片IPO潮 2026深化调查", "source_file": "industry/k891_storage_chips_IPO_wave_2026_deep_dive.md"},
        {"kcode": "k910", "title": "半导体材料 深化 2026", "source_file": "industry/k910_semiconductor_materials_deep_dive_2026.md"},
        {"kcode": "k972", "title": "半导体先进封装与晶圆合格率 — 中国芯片产业的隐形突破口", "source_file": "theory/k972_半导体先进封装晶圆合格率.md"},
    ],
    "AI算力": [
        {"kcode": "k817", "title": "AI算力基础设施 2026 深度调查", "source_file": "industry/k817_ai_computing_infrastructure_2026.md"},
        {"kcode": "k826", "title": "AI应用层 2026 深度调查", "source_file": "industry/k826_ai_application_layer_2026.md"},
        {"kcode": "k845", "title": "AI应用层 2026深化调查", "source_file": "industry/k845_ai_application_deep_dive_2026.md"},
        {"kcode": "k860", "title": "AI应用商业化 2026深化调查", "source_file": "industry/k860_ai_application_monetization_deep_dive_2026.md"},
        {"kcode": "k897", "title": "液冷服务器深化 2026调查", "source_file": "industry/k897_liquid_cooling_deep_dive_2026.md"},
        {"kcode": "k906", "title": "CPO 共封装光模块深化 2026", "source_file": "industry/k906_CPO_optical_module_deep_dive_2026.md"},
        {"kcode": "k911", "title": "AI算力芯片国产替代深化 2026", "source_file": "industry/k911_ai_compute_chip_domestic_substitution_deep_2026.md"},
        {"kcode": "k914", "title": "AI算力液冷深化 2026", "source_file": "industry/k914_ai_compute_liquid_cooling_deep_2026.md"},
        {"kcode": "k919", "title": "AI算力基础设施深化 2026", "source_file": "industry/k919_ai_compute_infrastructure_deep_2026.md"},
        {"kcode": "k928", "title": "AI大模型迭代深化 2026", "source_file": "industry/k928_ai_llm_iteration_deep_2026.md"},
    ],
    "新能源": [
        {"kcode": "k816", "title": "中国固态电池产业化进展 2026", "source_file": "industry/k816_solid_state_battery_2026.md"},
        {"kcode": "k820", "title": "中国氢能产业 2026 深度调查", "source_file": "industry/k820_hydrogen_energy_2026.md"},
        {"kcode": "k825", "title": "光伏/储能新技术 2026 深度调查", "source_file": "industry/k825_solar_storage_new_tech_2026.md"},
        {"kcode": "k838", "title": "中国新型电力系统 2026 深度调查", "source_file": "industry/k838_new_power_system_2026.md"},
        {"kcode": "k843", "title": "中国新能源产业 2026 深化调查", "source_file": "industry/k843_new_energy_deep_dive_2026.md"},
        {"kcode": "k854", "title": "固态电池 2026深化调查", "source_file": "industry/k854_solid_state_battery_deep_dive_2026.md"},
        {"kcode": "k855", "title": "钙钛矿太阳能电池 2026深化调查", "source_file": "industry/k855_perovskite_solar_deep_dive_2026.md"},
        {"kcode": "k863", "title": "储能电池 2026深化调查", "source_file": "industry/k863_储能电池_2026_deep_dive.md"},
        {"kcode": "k869", "title": "钠离子电池产业化 2026深化调查", "source_file": "industry/k869_sodium_ion_battery_industrialization_deep_dive_2026.md"},
        {"kcode": "k883", "title": "钙钛矿太阳能电池 GW级量产 2026深化调查", "source_file": "industry/k883_perovskite_solar_cell_GW_mass_production_2026.md"},
        {"kcode": "k890", "title": "固态电池装车验证 2026深化调查", "source_file": "industry/k890_solid_state_battery_vehicle_mounting_validation_deep_dive_2026.md"},
        {"kcode": "k904", "title": "新能源汽车渗透率 65% 深化 2026", "source_file": "industry/k904_new_energy_vehicle_penetration_deep_2026.md"},
        {"kcode": "k923", "title": "液流电池 长时储能深化 2026", "source_file": "industry/k923_flow_battery_long_duration_storage_deep_2026.md"},
        {"kcode": "k924", "title": "钠离子电池 产业化深化 2026", "source_file": "industry/k924_sodium_ion_battery_industrialization_deep_2026.md"},
    ],
    "医药": [
        {"kcode": "k725", "title": "癌症免疫治疗2026前沿进展", "source_file": "industry/k725_cancer_immunotherapy.md"},
        {"kcode": "k812", "title": "中国医药生物与创新驱动药行业调查 2026", "source_file": "industry/k812_biopharma_innovation_2026.md"},
        {"kcode": "k819", "title": "中国合成生物学产业 2026进展更新", "source_file": "industry/k819_synthetic_biology_2026_update.md"},
        {"kcode": "k827", "title": "生物制造 2026深化调查", "source_file": "industry/k827_biomanufacturing_deep_dive_2026.md"},
        {"kcode": "k839", "title": "中国细胞治疗与基因治疗 2026 深度调查", "source_file": "industry/k839_cell_gene_therapy_2026.md"},
        {"kcode": "k848", "title": "中国创新药 2026深化调查", "source_file": "industry/k848_innovative_drug_deep_dive_2026.md"},
        {"kcode": "k864", "title": "合成生物学 2026深化调查", "source_file": "industry/k864_synthetic_biology_deep_dive_2026.md"},
        {"kcode": "k873", "title": "合成生物学 2026深化调查", "source_file": "industry/k873_synthetic_biology_industrialization_2026.md"},
        {"kcode": "k913", "title": "创新药三重拐点深化 2026", "source_file": "industry/k913_innovative_drug_triple_inflection_deep_2026.md"},
    ],
    "军工": [
        {"kcode": "k161", "title": "军事学与战略研究", "source_file": "theory/k161-military-studies-strategy.md"},
        {"kcode": "k912", "title": "军工信息化 深化 2026", "source_file": "industry/k912_military_informatization_deep_2026.md"},
    ],
    "商业航天": [
        {"kcode": "k815", "title": "中国商业航天 2026进展更新", "source_file": "industry/k815_commercial_space_2026_update.md"},
        {"kcode": "k824", "title": "中国卫星互联网 2026进展更新", "source_file": "industry/k824_satellite_internet_2026.md"},
        {"kcode": "k828", "title": "中国商业航天 2026深化调查", "source_file": "industry/k828_commercial_space_deep_dive_2026.md"},
        {"kcode": "k876", "title": "商业航天 卫星制造 2026深化调查", "source_file": "industry/k876_satellite_manufacturing_deep_dive_2026.md"},
        {"kcode": "k887", "title": "朱雀三号火箭回收 2026深化调查", "source_file": "industry/k887_zhuque3_rocket_recovery_deep_dive_2026.md"},
        {"kcode": "k925", "title": "商业航天 深化 2026", "source_file": "industry/k925_commercial_spaceflight_deep_dive_2026.md"},
    ],
    "低空经济": [
        {"kcode": "k813", "title": "低空经济eVTOL行业 2026进展更新", "source_file": "industry/k813_low_altitude_economy_2026_update.md"},
        {"kcode": "k841", "title": "低空经济 2026深化调查", "source_file": "industry/k841_low_altitude_economy_deep_dive_2026.md"},
        {"kcode": "k852", "title": "低空经济取证深化 2026", "source_file": "industry/k852_low_altitude_TC_certification_deep_dive_2026.md"},
        {"kcode": "k862", "title": "低空经济 eVTOL 商业化 2026深化调查", "source_file": "industry/k862_low_altitude_economy_commercialization_deep_dive_2026.md"},
        {"kcode": "k898", "title": "低空经济出海订单深化 2026调查", "source_file": "industry/k898_low_altitude_economy_export_orders_deep_dive_2026.md"},
        {"kcode": "k917", "title": "低空经济 四小龙取证决胜 2026", "source_file": "industry/k917_low_altitude_economy_four_dragon_TC_2026.md"},
    ],
    "量子计算": [
        {"kcode": "k729", "title": "量子计算2026进展与实用化", "source_file": "theory/k729_quantum_computing.md"},
        {"kcode": "k786", "title": "量子深化——容错量子计算 2026 进展与路线图", "source_file": "theory/k786_容错量子计算2026进展.md"},
        {"kcode": "k821", "title": "中国量子计算 2026 深度调查", "source_file": "industry/k821_quantum_computing_2026.md"},
        {"kcode": "k849", "title": "量子计算 2026深化调查", "source_file": "industry/k849_quantum_computing_deep_dive_2026.md"},
        {"kcode": "k867", "title": "量子计算商业化 2026深化调查", "source_file": "industry/k867_quantum_computing_commercialization_deep_dive_2026.md"},
        {"kcode": "k874", "title": "量子计算商业化 2026深化调查", "source_file": "industry/k874_quantum_computing_commercialization_deep_dive_2026.md"},
        {"kcode": "k875", "title": "量子计算商业化 2026深化调查", "source_file": "industry/k875_quantum_computing_commercialization_deep_dive_2026.md"},
    ],
    "具身智能": [
        {"kcode": "k286", "title": "具身智能与 VLA 模型 (Embodied AI / Vision-Language-Action)", "source_file": "theory/k286-embodied-ai-vla.md"},
        {"kcode": "k818", "title": "人形机器人产业链 2026 深度调查", "source_file": "industry/k818_humanoid_robot_2026.md"},
        {"kcode": "k840", "title": "人形机器人 2026深化调查", "source_file": "industry/k840_humanoid_robot_deep_dive_2026.md"},
        {"kcode": "k844", "title": "人形机器人供应链 2026 深度调查", "source_file": "industry/k844_humanoid_robot_supply_chain_2026.md"},
        {"kcode": "k846", "title": "人形机器人产业链投资映射 2026", "source_file": "industry/k846_humanoid_robot_investment_mapping_2026.md"},
        {"kcode": "k851", "title": "人形机器人量产深化 2026", "source_file": "industry/k851_humanoid_robot_mass_production_deep_dive_2026.md"},
        {"kcode": "k857", "title": "人形机器人量产数据验证 2026", "source_file": "industry/k857_humanoid_robot_production_validation_2026.md"},
        {"kcode": "k858", "title": "人形机器人 2026量产深化调查", "source_file": "industry/k858_humanoid_robot_mass_production_2026_deep_dive.md"},
        {"kcode": "k880", "title": "宇树科技上市 2026深化调查", "source_file": "industry/k880_unitree_IPO_deep_dive_2026.md"},
        {"kcode": "k894", "title": "人形机器人供应链 2026深化调查", "source_file": "industry/k894_humanoid_robot_supply_chain_deep_dive_2026.md"},
        {"kcode": "k915", "title": "宇树科技上市深化 2026", "source_file": "industry/k915_unitree_IPO_deep_dive_2026.md"},
        {"kcode": "k918", "title": "人形机器人 量产深化 2026", "source_file": "industry/k918_humanoid_robot_mass_production_deep_2026.md"},
        {"kcode": "k922", "title": "人形机器人供应链深化 2026", "source_file": "industry/k922_humanoid_robot_supply_chain_deep_2026.md"},
    ],
    "脑机接口": [
        {"kcode": "k804", "title": "脑机接口深化——2026 产业化元年", "source_file": "theory/k804_脑机接口产业化2026.md"},
        {"kcode": "k823", "title": "中国脑机接口 2026 深度调查", "source_file": "industry/k823_brain_computer_interface_2026.md"},
        {"kcode": "k850", "title": "脑机接口 2026深化调查", "source_file": "industry/k850_bci_commercialization_deep_dive_2026.md"},
        {"kcode": "k926", "title": "脑机接口 康复医疗深化 2026", "source_file": "industry/k926_bci_rehabilitation_medical_deep_2026.md"},
    ],
    "金融": [
        {"kcode": "k020", "title": "期权、期货及衍生品定价核心框架", "source_file": "theory/k020-options-derivatives.md"},
        {"kcode": "k022", "title": "现代资产组合理论与资产配置", "source_file": "theory/k022-portfolio-optimization.md"},
        {"kcode": "k047", "title": "多周期基金排行——近3年/定投/债券/指数全维度冠军分析", "source_file": "industry/k047-multi-cycle-fund-ranking.md"},
        {"kcode": "k050", "title": "货币经济学与中央银行：货币创造、政策传导与投资映射", "source_file": "theory/k050-monetary-central-banking.md"},
        {"kcode": "k132", "title": "量化交易算法与A股因子模型 — 从理论到实操", "source_file": "industry/k132-quant-trading-algorithm-factor-model.md"},
        {"kcode": "k172", "title": "ETF定投策略：从纪律投资到估值择时", "source_file": "industry/k172-etf-dca-strategy.md"},
        {"kcode": "k178", "title": "行业估值方法论：从DCF到相对估值", "source_file": "theory/k178-industry-valuation-methodology.md"},
        {"kcode": "k182", "title": "基于主体的计算金融学（Agent-Based Computational Finance）", "source_file": "theory/k182-agent-based-computational-finance.md"},
        {"kcode": "k188", "title": "金融信息论（Financial Information Theory）", "source_file": "theory/k188-financial-information-theory.md"},
        {"kcode": "k252", "title": "杠杆ETF复利效应与收益动力学", "source_file": "theory/k252-leveraged-etf-compounding-effects.md"},
        {"kcode": "k764", "title": "公募基金2026Q2持仓全景 — 前十大重仓股首次全为硬科技", "source_file": "theory/k764-公募基金2026Q2持仓硬科技霸榜.md"},
        {"kcode": "k792", "title": "金融×AI 深化——Agentic Trading 与 LLM 量化 2026", "source_file": "theory/k792_AgenticTrading与LLM量化2026.md"},
        {"kcode": "k935", "title": "中国金融隐性风险数据洞察", "source_file": "theory/k935_金融隐性风险数据洞察.md"},
    ],
    "周期/资源": [
        {"kcode": "k088", "title": "大宗商品系统框架", "source_file": "theory/k088-commodity-systematic-framework.md"},
        {"kcode": "k742", "title": "AI×材料科学交叉知识体系", "source_file": "industry/k742_materials_science_ai.md"},
        {"kcode": "k814", "title": "中国稀土永磁材料行业 2026 深度调查", "source_file": "industry/k814_rare_earth_magnets_2026.md"},
        {"kcode": "k833", "title": "中国新材料 2026 深度调查", "source_file": "industry/k833_advanced_materials_2026.md"},
        {"kcode": "k962", "title": "外汇储备结构真相与黄金困境", "source_file": "theory/k962_外汇储备结构真相与黄金困境.md"},
        {"kcode": "k969", "title": "稀土出口管制与战略资源博弈 — 中国的隐形王牌", "source_file": "theory/k969_稀土出口管制战略资源博弈.md"},
    ],
    "宏观": [
        {"kcode": "k031", "title": "全球债务危机与气候-粮食安全：三重危机的交织", "source_file": "theory/k031-global-debt-climate-food.md"},
        {"kcode": "k060", "title": "中国产业政策与新质生产力全景", "source_file": "theory/k060-china-industrial-policy-nqpf.md"},
        {"kcode": "k065", "title": "中国地方政府债与LGFV：土地财政转型", "source_file": "theory/k065-lgfv-local-government-debt.md"},
        {"kcode": "k093", "title": "全球央行政策大分化", "source_file": "theory/k093-global-central-bank-divergence-2026.md"},
        {"kcode": "k761", "title": "2026年7月宏观数据快照（物价/外贸/汽车）", "source_file": "theory/k761-2026年7月宏观数据快照.md"},
        {"kcode": "k763", "title": "央行\"十五五\"改革发展规划（2026-08-10印发）", "source_file": "theory/k763-央行十五五改革发展规划.md"},
        {"kcode": "k941", "title": "中国地方政府隐性债务隐线数据", "source_file": "theory/k941_地方政府隐性债务隐线数据.md"},
        {"kcode": "k965", "title": "城投债\"冰火两重天\"：标债 vs 非标违约真相", "source_file": "theory/k965_城投债冰火两重天_标债与非标违约真相.md"},
    ],
    "跨境": [
        {"kcode": "k128", "title": "2026年上半年ETF业绩与资金流向深度分析", "source_file": "industry/k128-etf-performance-h1-2026.md"},
        {"kcode": "k961", "title": "跨境电商真实现状：Temu Shein三国杀", "source_file": "theory/k961_跨境电商真实现状_Temu_Shein三国杀.md"},
    ],
    "消费": [
        {"kcode": "k834", "title": "中国消费电子 2026 深度调查", "source_file": "industry/k834_consumer_electronics_2026.md"},
        {"kcode": "k936", "title": "中国消费与就业隐形数据深度分析", "source_file": "theory/k936_消费就业隐形数据洞察.md"},
    ],
}

# weekly_top3 mega-sector 补充别名（l34.SECTOR_ALIASES 未覆盖的 mega 口径）
_EXTRA_ALIASES: dict[str, str] = {
    "科技": "半导体",
    "周期": "周期/资源",
    "基建": "基建/地产",
    "红利价值": "红利/价值",
    "跨境": "跨境",
    "宏观": "宏观",
    "流动性": "宏观",
}


def _normalize_sector(sector: str) -> str:
    """板块别名归一：先用 l34 口径，再补 mega 别名。"""
    if not sector:
        return sector
    from etf_platform.layers.l34_kb_catalyst import SECTOR_ALIASES
    norm = SECTOR_ALIASES.get(sector, sector)
    return _EXTRA_ALIASES.get(norm, norm)


def get_sector_kb_codes(sector: str) -> list[dict[str, str]]:
    """返回板块映射的 KB 依据列表 [{kcode, title, source_file}]，未命中返回 []。"""
    norm = _normalize_sector(sector)
    return [dict(item) for item in SECTOR_KB_CODES.get(norm, [])]
