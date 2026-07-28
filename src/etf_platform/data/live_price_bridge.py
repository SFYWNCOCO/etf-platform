"""
live_price_bridge.py — Sina实时行情桥接
替换 broken Eastmoney push2 API → 提供ETF实时价格+动量数据
"""
import logging
from datetime import datetime
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent  # src/etf_platform/
CACHE_DIR = BASE_DIR.parent.parent / "data" / "live_cache"  # etf-platform/data/live_cache/
SINA_URL = "https://hq.sinajs.cn/list="

# ETF代码→Sina symbol映射
CODE_TO_SINA = {}  # lazy load from config


def _build_code_map():
    """从etfs.yaml加载全量ETF代码→Sina symbol映射"""
    global CODE_TO_SINA
    if CODE_TO_SINA:
        return CODE_TO_SINA
    
    # 使用 config_loader (已lru_cache'd, 避免重复读yaml)
    yaml_loaded = 0
    try:
        from ..config_loader import load_etfs
        etfs = load_etfs()
        for code_key, etf in etfs.items():
            if isinstance(etf, dict):
                code = str(etf.get("code", code_key))
                if not (code and len(code) == 6 and code.isdigit()):
                    continue
                if code.startswith("159"):
                    market = "sz"
                else:
                    market = "sh"
                CODE_TO_SINA[f"{market}{code}"] = code
                yaml_loaded += 1
    except ImportError:
            logger.warning("silent catch in live_price_bridge.py:43 - needs review")
    
    if yaml_loaded == 0:
        # 降级：从 data/price_cache.json 读取代码列表
        price_path = BASE_DIR.parent.parent / "data" / "price_cache.json"
        if price_path.exists():
            import json
            with open(price_path, encoding="utf-8") as f:
                cache = json.load(f)
            # v16.20: 修复——price_cache.json格式为{prices:{code:{...}}}，不是{codes:[]}
            prices_dict = cache.get("prices", {})
            for code in prices_dict:
                if len(code) == 6:
                    # 根据代码前缀判断市场——避免同时创建sh+sz的无效条目
                    if code.startswith("159"):
                        CODE_TO_SINA[f"sz{code}"] = code
                    else:
                        CODE_TO_SINA[f"sh{code}"] = code
            yaml_loaded = len(prices_dict)
    
    return CODE_TO_SINA


def fetch_live_prices(codes: list[str] = None) -> dict:
    """
    从Sina获取实时ETF价格。默认全量。
    返回: {code: {name, price, change_pct, volume, turnover, high, low, open, prev_close}}
    """
    if codes is None:
        codes = list(_build_code_map().keys())  # 全量

    # Cache code map locally — saves ~500 _build_code_map() calls per run
    _local_code_map = _build_code_map()

    results = {}
    batch_size = 50  # Sina一次最多约50个，全量500+需要~12批
    headers = {"Referer": "https://finance.sina.com.cn/"}
    
    for i in range(0, len(codes), batch_size):
        batch = codes[i:i+batch_size]
        url = SINA_URL + ",".join(batch)
        try:
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code != 200:
                continue
            
            for line in r.text.strip().split("\n"):
                if not line.strip() or "=" not in line:
                    continue
                try:
                    var_part = line.split('"')[1] if '"' in line else ""
                    if not var_part:
                        continue
                    fields = var_part.split(",")
                    if len(fields) < 10:
                        continue
                    
                    sina_code = line.split("=")[0].replace("var hq_str_", "")
                    etf_code = _local_code_map.get(sina_code, sina_code)
                    
                    results[etf_code] = {
                        "name": fields[0],
                        "open": float(fields[1]) if fields[1] else 0,
                        "prev_close": float(fields[2]) if fields[2] else 0,
                        "price": float(fields[3]) if fields[3] else 0,
                        "high": float(fields[4]) if fields[4] else 0,
                        "low": float(fields[5]) if fields[5] else 0,
                        "volume": int(fields[8]) if fields[8] else 0,
                        "turnover": float(fields[9]) if fields[9] else 0,
                        "change_pct": round((float(fields[3]) - float(fields[2])) / float(fields[2]) * 100, 2) if fields[2] and fields[3] and float(fields[2]) > 0 else 0,
                        "ts": datetime.now().isoformat(),
                    }
                    # v16.18: 数据验证——过滤异常值
                    if results[etf_code]["price"] <= 0:
                        del results[etf_code]
                    elif abs(results[etf_code]["change_pct"]) > 20:
                        del results[etf_code]  # 涨跌停限制，超20%为数据异常
                    elif results[etf_code]["price"] < 0.01:
                        del results[etf_code]
                except (IndexError, ValueError, ZeroDivisionError):
                    continue
        except Exception as e:
            logger.warning("Sina fetch batch failed: %s", e)
    
    results["_meta"] = {
        "source": "sina_live",
        "ts": datetime.now().isoformat(),
        "count": len([k for k in results if not k.startswith("_")]),
    }
    return results


def get_sector_momentum(etf_prices: dict, sector_map: dict = None) -> dict:
    """
    从ETF实时价格计算行业动量得分
    v16.21: 使用etfs.yaml code→sector精准映射替代关键词匹配
    返回: {sector: {avg_return, avg_volume_ratio, momentum_score, etf_count}}
    """
    # Cache code_to_broad as module-level singleton (saves yaml read per call)
    global _cached_code_to_broad
    if '_cached_code_to_broad' not in globals():
        _cached_code_to_broad = None
    
    if sector_map is None:
        # v16.21: etfs.yaml fine_sector → broad_sector 统一映射（60→19）
        # 替换v16.18的关键词匹配，消除17.2%的匹配缺口
        FINE_TO_BROAD = {
            "半导体": "半导体", "半导体设备": "半导体", "半导体杠杆": "半导体", "半导体做空": "半导体",
            "AI/科技": "AI", "AI算力": "AI", "云计算/算力": "AI", "通信/光模块": "AI",
            "硬科技": "AI", "硬科技杠杆": "AI", "硬科技做空": "AI", "5G/PCB": "AI",
            "军工": "军工",
            "新能源": "新能源",
            "医药": "医药", "医药器械": "医药", "港股医药": "医药", "中药": "医药",
            "消费": "消费", "白酒消费": "消费", "食品饮料": "消费", "家电": "消费", "农产品": "消费",
            "红利/价值": "红利", "红利价值": "红利", "红利+低波": "红利",
            "高股息": "红利", "小盘价值": "红利", "大盘蓝筹": "红利",
            "金融": "金融", "保险": "金融", "券商": "金融",
            "港股综合": "港股", "港股科技": "港股", "中概互联网": "港股",
            "跨境": "跨境", "美股科技": "跨境", "美股科技100": "跨境",
            "美股综合": "跨境", "美股杠杆": "跨境",
            "通信/5G": "通信",
            "基建/地产": "基建", "公用事业": "基建",
            "周期/资源": "黄金", "有色金属": "黄金", "贵金属": "黄金",
            "货币": "债券", "货币基金": "债券", "利率债": "债券", "信用债": "债券", "可转债": "债券",
            "宽基": "宽基", "综合": "宽基", "全市场": "宽基", "成长股": "宽基", "中盘成长": "宽基",
            "央企改革": "宽基", "其他": "宽基",
            "机器人/智造": "机器人",
            "能源化工": "化工",
        }
        # 构建 code→broad_sector 查找表 (cached after first call)
        if _cached_code_to_broad is not None:
            code_to_broad = _cached_code_to_broad
        else:
            code_to_broad = {}
        try:
            from ..config_loader import load_etfs
            etfs_data = load_etfs()
            for code_key, etf in etfs_data.items():
                if isinstance(etf, dict):
                    code = str(etf.get("code", code_key))
                    if code and len(code) == 6:
                        fine = etf.get("sector", "其他")
                        code_to_broad[code] = FINE_TO_BROAD.get(fine, "宽基")
        except Exception as e:
            logger.warning("Failed to load etfs for sector mapping: %s", e)
        if code_to_broad:
            _cached_code_to_broad = code_to_broad

    broad_sectors = set(code_to_broad.values()) if code_to_broad else set(FINE_TO_BROAD.values())
    sectors = {s: {"returns": [], "volumes": [], "codes": []} for s in broad_sectors}

    keyword_fallback = 0
    for code, data in etf_prices.items():
        if code.startswith("_"):
            continue
        # 优先使用code→sector精准映射
        sector = code_to_broad.get(code)
        if sector:
            sectors[sector]["returns"].append(data.get("change_pct", 0))
            sectors[sector]["volumes"].append(data.get("volume", 0))
            sectors[sector]["codes"].append(code)
        else:
            keyword_fallback += 1

    if keyword_fallback > 0:
        logger.info("sector_momentum: %d/%d ETFs fell back (no etfs.yaml mapping)",
                     keyword_fallback, len(etf_prices) - 1)
    
    result = {}
    for sector, vals in sectors.items():
        returns = vals["returns"]
        if returns:
            avg_ret = sum(returns) / len(returns)
            # 动量得分: 综合涨跌幅+数量+活跃度
            momentum = avg_ret * (1 + min(len(returns) / 10, 1))
            result[sector] = {
                "avg_return": round(avg_ret, 2),
                "etf_count": len(returns),
                "momentum_score": round(momentum, 2),
                "codes": vals["codes"],
            }
    
    result["_meta"] = {
        "source": "sina_live_sector",
        "ts": datetime.now().isoformat(),
        "sector_count": len(result),
    }
    return result


if __name__ == "__main__":
    print("🦞 Live Price Bridge Test")
    codes = list(_build_code_map().keys())[:30]
    prices = fetch_live_prices(codes)
    print(f"获取 {prices['_meta']['count']} 只ETF实时价格")
    
    for code, data in list(prices.items())[:5]:
        if code.startswith("_"):
            continue
        print(f"  {code} {data['name']}: {data['price']} ({data['change_pct']:+.2f}%)")
    
    sectors = get_sector_momentum(prices)
    print("\n行业动量 (Top 5):")
    sorted_sectors = sorted(
        [(k, v) for k, v in sectors.items() if not k.startswith("_")],
        key=lambda x: -x[1]["momentum_score"]
    )
    for sector, data in sorted_sectors[:5]:
        print(f"  {sector}: {data['momentum_score']:+.2f} ({data['avg_return']:+.2f}%, {data['etf_count']}只)")
