"""holdings.py — ETF持仓穿透数据 (手动维护)

来源: etf_system/holdings_survey.py
每只ETF的前10大持仓、供应链位置、技术等级、进口依赖度。
"""
ETF_HOLDINGS = {
    "159995": {
        "name": "芯片ETF", "total": 50, "top10_pct": 0.52,
        "top10": [
            {"stock":"中芯国际","code":"688981","weight":0.098,"chain":"晶圆代工","tech":"14nm量产/7nm研发","import_dep":0.55},
            {"stock":"北方华创","code":"002371","weight":0.072,"chain":"半导体设备","tech":"刻蚀/薄膜/PVD","import_dep":0.40},
            {"stock":"韦尔股份","code":"603501","weight":0.065,"chain":"CIS传感器","tech":"手机/车载CIS","import_dep":0.25},
            {"stock":"中微公司","code":"688012","weight":0.058,"chain":"刻蚀设备","tech":"5nm刻蚀机","import_dep":0.30},
            {"stock":"海光信息","code":"688041","weight":0.052,"chain":"CPU/GPU设计","tech":"x86兼容CPU","import_dep":0.60},
            {"stock":"寒武纪","code":"688256","weight":0.048,"chain":"AI芯片设计","tech":"AI训练/推理芯片","import_dep":0.55},
            {"stock":"澜起科技","code":"688008","weight":0.043,"chain":"内存接口芯片","tech":"DDR5接口","import_dep":0.15},
            {"stock":"长电科技","code":"600584","weight":0.039,"chain":"封装测试","tech":"先进封装","import_dep":0.20},
            {"stock":"兆易创新","code":"603986","weight":0.035,"chain":"MCU/NOR Flash","tech":"32位MCU","import_dep":0.35},
            {"stock":"卓胜微","code":"300782","weight":0.031,"chain":"射频前端","tech":"5G射频开关","import_dep":0.30},
        ],
        "risk": "前3占23.5%: 中芯+北华+韦尔, 制造层落后台积电2-3代",
    },
    "159819": {
        "name": "AI ETF", "total": 40, "top10_pct": 0.58,
        "top10": [
            {"stock":"海康威视","code":"002415","weight":0.105,"chain":"AI安防","tech":"视觉AI全球领先","import_dep":0.20},
            {"stock":"科大讯飞","code":"002230","weight":0.088,"chain":"AI语音/NLP","tech":"星火大模型","import_dep":0.30},
            {"stock":"金山办公","code":"688111","weight":0.075,"chain":"AI办公","tech":"WPS AI","import_dep":0.10},
            {"stock":"中科曙光","code":"603019","weight":0.068,"chain":"AI服务器","tech":"国产AI服务器","import_dep":0.65},
            {"stock":"浪潮信息","code":"000977","weight":0.062,"chain":"AI服务器","tech":"AI服务器龙头","import_dep":0.75},
            {"stock":"寒武纪","code":"688256","weight":0.058,"chain":"AI芯片","tech":"AI训练芯片","import_dep":0.55},
            {"stock":"海光信息","code":"688041","weight":0.052,"chain":"CPU/GPU","tech":"x86兼容CPU","import_dep":0.60},
            {"stock":"商汤科技","code":"000020","weight":0.048,"chain":"AI视觉/大模型","tech":"日日新大模型","import_dep":0.25},
            {"stock":"云从科技","code":"688327","weight":0.038,"chain":"AI行业应用","tech":"人机协同OS","import_dep":0.15},
            {"stock":"格灵深瞳","code":"688207","weight":0.028,"chain":"AI视觉","tech":"计算机视觉","import_dep":0.20},
        ],
        "risk": "中科曙光+浪潮信息占13%, 均依赖进口GPU→单点断裂风险",
    },
    "516510": {
        "name": "云计算ETF", "total": 35, "top10_pct": 0.62,
        "top10": [
            {"stock":"中科曙光","code":"603019","weight":0.115,"chain":"AI服务器","tech":"国产AI服务器","import_dep":0.65},
            {"stock":"浪潮信息","code":"000977","weight":0.105,"chain":"AI服务器","tech":"AI服务器龙头","import_dep":0.75},
            {"stock":"紫光股份","code":"000938","weight":0.088,"chain":"网络设备","tech":"交换机/路由器","import_dep":0.30},
            {"stock":"光环新网","code":"300383","weight":0.068,"chain":"IDC运营","tech":"数据中心运营","import_dep":0.15},
            {"stock":"数据港","code":"603881","weight":0.058,"chain":"IDC运营","tech":"数据中心运营","import_dep":0.10},
            {"stock":"网宿科技","code":"300017","weight":0.052,"chain":"CDN/边缘计算","tech":"CDN全球领先","import_dep":0.10},
            {"stock":"宝信软件","code":"600845","weight":0.048,"chain":"工业云","tech":"钢铁工业互联网","import_dep":0.05},
            {"stock":"用友网络","code":"600588","weight":0.042,"chain":"企业云","tech":"ERP/SaaS","import_dep":0.05},
            {"stock":"广联达","code":"002410","weight":0.038,"chain":"建筑云","tech":"工程造价SaaS","import_dep":0.05},
            {"stock":"恒生电子","code":"600570","weight":0.032,"chain":"金融云","tech":"金融IT系统","import_dep":0.05},
        ],
        "risk": "前2名(曙光+浪潮)占22%, 均100%依赖进口GPU→断供即腰斩",
    },
    "512890": {
        "name": "红利低波ETF", "total": 50, "top10_pct": 0.45,
        "top10": [
            {"stock":"中国神华","code":"601088","weight":0.065,"chain":"煤炭","tech":"煤电一体化","import_dep":0.05},
            {"stock":"中国石油","code":"601857","weight":0.058,"chain":"石油","tech":"油气开采","import_dep":0.30},
            {"stock":"招商银行","code":"600036","weight":0.055,"chain":"银行","tech":"零售银行龙头","import_dep":0},
            {"stock":"大秦铁路","code":"601006","weight":0.052,"chain":"铁路运输","tech":"西煤东运主干线","import_dep":0.02},
            {"stock":"中国石化","code":"600028","weight":0.048,"chain":"石化","tech":"炼化一体化","import_dep":0.35},
            {"stock":"宝钢股份","code":"600019","weight":0.045,"chain":"钢铁","tech":"汽车板龙头","import_dep":0.20},
            {"stock":"华能国际","code":"600011","weight":0.042,"chain":"电力","tech":"火电龙头","import_dep":0.10},
            {"stock":"中国建筑","code":"601668","weight":0.038,"chain":"建筑","tech":"基建龙头","import_dep":0.05},
            {"stock":"工商银行","code":"601398","weight":0.035,"chain":"银行","tech":"最大商业银行","import_dep":0},
            {"stock":"农业银行","code":"601288","weight":0.032,"chain":"银行","tech":"大型商业银行","import_dep":0},
        ],
        "risk": "低: 高度分散, 金融+能源占主导, 无实物链外依赖",
    },
    "518880": {
        "name": "黄金ETF", "total": 1, "top10_pct": 1.0,
        "top10": [
            {"stock":"AU99.99","code":"Au9999","weight":0.985,"chain":"黄金现货","tech":"实物黄金","import_dep":0},
        ],
        "risk": "极低: 实物黄金, 无供应链风险",
    },
    "512690": {
        "name": "酒ETF", "total": 30, "top10_pct": 0.68,
        "top10": [
            {"stock":"贵州茅台","code":"600519","weight":0.165,"chain":"白酒酿造","tech":"酱香型白酒","import_dep":0},
            {"stock":"五粮液","code":"000858","weight":0.135,"chain":"白酒酿造","tech":"浓香型白酒","import_dep":0},
            {"stock":"泸州老窖","code":"000568","weight":0.095,"chain":"白酒酿造","tech":"浓香型白酒","import_dep":0},
            {"stock":"山西汾酒","code":"600809","weight":0.075,"chain":"白酒酿造","tech":"清香型白酒","import_dep":0},
            {"stock":"洋河股份","code":"002304","weight":0.058,"chain":"白酒酿造","tech":"绵柔型白酒","import_dep":0},
            {"stock":"古井贡酒","code":"000596","weight":0.045,"chain":"白酒酿造","tech":"浓香型白酒","import_dep":0},
            {"stock":"青岛啤酒","code":"600600","weight":0.038,"chain":"啤酒","tech":"啤酒龙头","import_dep":0.05},
            {"stock":"今世缘","code":"603369","weight":0.028,"chain":"白酒酿造","tech":"次高端白酒","import_dep":0},
            {"stock":"重庆啤酒","code":"600132","weight":0.022,"chain":"啤酒","tech":"高端啤酒","import_dep":0.10},
            {"stock":"水井坊","code":"600779","weight":0.018,"chain":"白酒酿造","tech":"高端白酒","import_dep":0},
        ],
        "risk": "极低: 100%内循环, 3年基酒库存, 无进口依赖",
    },
}


def get_holdings(code):
    """获取ETF持仓穿透数据"""
    return ETF_HOLDINGS.get(code)


def list_covered_etfs():
    """列出有持仓数据的ETF"""
    return list(ETF_HOLDINGS.keys())


def get_concentration_analysis(code):
    """分析持仓集中度和进口依赖"""
    h = ETF_HOLDINGS.get(code)
    if not h:
        return None
    top10 = h["top10"]
    total_dep = sum(s["weight"] * s["import_dep"] for s in top10)
    max_dep_stock = max(top10, key=lambda x: x["import_dep"] * x["weight"])
    return {
        "code": code,
        "name": h["name"],
        "top10_weight": h["top10_pct"],
        "weighted_import_dep": round(total_dep, 3),
        "max_dep_stock": max_dep_stock["stock"],
        "max_dep_value": round(max_dep_stock["import_dep"] * max_dep_stock["weight"], 3),
        "risk_summary": h["risk"],
    }


if __name__ == "__main__":
    for code in ETF_HOLDINGS:
        c = get_concentration_analysis(code)
        print("%s %s: top10=%.0f%% 进口依赖=%.1f%% 风险: %s" % (
            code, c["name"], c["top10_weight"]*100, c["weighted_import_dep"]*100, c["risk_summary"][:40]))