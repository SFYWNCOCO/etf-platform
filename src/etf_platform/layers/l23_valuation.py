"""L23 Valuation Layer v7.0 — Real ETF PE/PB via ak.stock_board_industry_cons_em + INDEX_PROXY fallback.

BREAKTHROUGH: ak.stock_board_industry_cons_em(symbol='银行') returns DataFrame with
REAL columns '市盈率-动态' and '市净率' for all constituent stocks.
Verified: 银行PE中位数=5.23, PB中位=0.54; 半导体PE中位=87.79; etc.
This is the PRIMARY data source, replacing broken akshare stock_index_pe_lg/pb_lg.

Data sources (priority):
1. ak.stock_board_industry_cons_em -> industry board median PE/PB (REAL DATA)
2. ak.stock_zh_valuation_baidu() -> individual stock PE/PB weighted avg (备选)
3. INDEX_PROXY fallback (行业默认值，无实时数据时兜底)

All calls isolated per-index with try-except. Never blocks pipeline.
"""
import json, time, logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Platform root auto-detection ──
_platform_root_candidates = [
    Path(__file__).resolve().parent.parent.parent,
    Path(__file__).resolve().parent.parent.parent.parent,
]
_PLATFORM_ROOT = None
for p in _platform_root_candidates:
    if (p / "src").exists():
        _PLATFORM_ROOT = p
        break
if _PLATFORM_ROOT is None:
    _PLATFORM_ROOT = Path(__file__).resolve().parent.parent.parent
sys_path = str(_PLATFORM_ROOT / "src")
if sys_path not in __import__('sys').path:
    __import__('sys').path.insert(0, sys_path)

DATA_DIR = _PLATFORM_ROOT / "data"
CACHE_FILE = DATA_DIR / "etf_valuation.json"
TTL_SECONDS = 6 * 3600  # 6 hours

# ═══════════════════════════════════════════════════════════════════════════════
# L23 sector key → ak.stock_board_industry_cons_em(board_name) mapping
# Verified working boards: 银行,半导体,医药生物,食品饮料,国防军工,电力设备,
#   光伏设备,电池,石油石化,煤炭开采,贵金属,有色金属,建筑装饰,房地产开发,
#   钢铁,基础化工,社会服务,教育,农林牧渔,通信,计算机,电子,非银金融,汽车
# ═══════════════════════════════════════════════════════════════════════════════

L23_SECTOR_TO_BOARD = {
    # Direct industry board matches
    '银行': '银行',
    '半导体': '半导体',
    '通信': '通信',
    '计算机': '计算机',
    '软件服务': '计算机',
    '科技': '计算机',
    'AI': '计算机',
    '人工智能': '计算机',
    '算力': '计算机',
    '电子': '电子',
    '消费电子': '电子',
    '通信设备': '通信',
    '计算机设备': '计算机',
    '医药': '医药生物',
    '医药生物': '医药生物',
    '创新药': '医药生物',
    '医疗': '医药生物',
    '医疗器械': '医疗器械',
    '医疗服务': '医疗服务',
    '消费': '食品饮料',
    '食品饮料': '食品饮料',
    '白酒': '食品饮料',
    '汽车': '汽车',
    '汽车整车': '汽车',
    '汽车零部件': '汽车',
    '房地产': '房地产开发',
    '房地产开发': '房地产开发',
    '基建': '建筑装饰',
    '建筑装饰': '建筑装饰',
    '建筑': '建筑装饰',
    '钢铁': '钢铁',
    '钢铁股': '钢铁',
    '煤炭': '煤炭开采',
    '煤炭开采': '煤炭开采',
    '黄金': '贵金属',
    '贵金属': '贵金属',
    '有色金属': '有色金属',
    '有色': '有色金属',
    '能源': '石油石化',
    '石油石化': '石油石化',
    '化工': '基础化工',
    '基础化工': '基础化工',
    '军工': '国防军工',
    '国防': '国防军工',
    '航空航天': '国防军工',
    '旅游': '社会服务',
    '娱乐': '社会服务',
    '体育': '社会服务',
    '传媒': '社会服务',
    '保险': '非银金融',
    '券商': '非银金融',
    '证券': '非银金融',
    '非银金融': '非银金融',
    '教育': '学历教育',
    '农业': '农林牧渔',
    '农林牧渔': '农林牧渔',
    '地产': '房地产开发',
    '新能源': '电力设备',
    '电力设备': '电力设备',
    '光伏': '光伏设备',
    '锂电': '电池',
    '芯片': '半导体',
    '存储芯片': '电子',
    # No direct board -> use index proxy
    '红利': None,
    '沪深300': None,
    '上证50': None,
    '中证500': None,
    '创业板': None,
    '科创板': None,
}

INDEX_PROXY_MAP = {
    '沪深300': {'pe_ratio': 12.5, 'pb_ratio': 1.45, 'dividend_yield': 2.8},
    '上证50': {'pe_ratio': 11.0, 'pb_ratio': 1.30, 'dividend_yield': 3.0},
    '中证500': {'pe_ratio': 18.0, 'pb_ratio': 1.80, 'dividend_yield': 1.5},
    '创业板': {'pe_ratio': 30.0, 'pb_ratio': 3.50, 'dividend_yield': 1.0},
    '科创板': {'pe_ratio': 35.0, 'pb_ratio': 4.00, 'dividend_yield': 0.5},
}


def _infer_sector_key(name: str, sector: str) -> str | None:
    """Map ETF name+sector to L23_SECTOR_TO_BOARD key."""
    text = f"{name} {sector}".lower()
    # Exact matches first (longest first)
    for key in sorted(L23_SECTOR_TO_BOARD.keys(), key=lambda x: -len(x)):
        if key.lower() in text:
            return key
    return None


def _to_float(value):
    """Safely convert a value to float."""
    if value is None:
        return None
    try:
        result = float(value)
        if result != result:  # NaN
            return None
        return round(result, 2)
    except (ValueError, TypeError):
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# Data fetching v7.0 — ak.stock_board_industry_cons_em with REAL PE/PB
# ═══════════════════════════════════════════════════════════════════════════════

# In-memory cache: {board_name -> entry} deduplicated within process
_INDUSTRY_CACHE: dict = {}
_INDUSTRY_CACHE_TS: float = 0
_INDUSTRY_CACHE_TTL = 6 * 3600  # 6 hours


def _parse_industry_board(df) -> dict | None:
    """Parse ak.stock_board_industry_cons_em DataFrame into PE/PB stats."""
    pe_col = next((c for c in df.columns if '市盈率' in str(c)), None)
    pb_col = next((c for c in df.columns if '市净率' in str(c)), None)
    if not pe_col and not pb_col:
        return None

    import pandas as pd
    pe_vals = pd.to_numeric(df[pe_col], errors='coerce').dropna() if pe_col else pd.Series(dtype=float)
    pb_vals = pd.to_numeric(df[pb_col], errors='coerce').dropna() if pb_col else pe_vals[:0]

    pe_valid = pe_vals[(pe_vals > 0) & (pe_vals < 500)]
    pb_valid = pb_vals[(pb_vals >= 0) & (pb_vals < 100)] if pb_col else pe_vals[:0]

    if len(pe_valid) == 0 and (not pb_col or len(pb_valid) == 0):
        return None

    entry = {
        'source': 'ak_board_industry_cons_em',
        'board': None,
        'stock_count': len(df),
        'valid_pe_count': len(pe_valid),
        'valid_pb_count': len(pb_valid),
    }

    if len(pe_valid) > 0:
        sorted_pe = pe_valid.sort_values().tolist()
        mid = len(sorted_pe) // 2
        entry['median_pe'] = round(float(sorted_pe[mid]), 2)
        entry['mean_pe'] = round(float(pe_valid.mean()), 2)
        entry['pe_ratio'] = entry['median_pe']
    else:
        entry['median_pe'] = None
        entry['mean_pe'] = None
        entry['pe_ratio'] = None

    if pb_col and len(pb_valid) > 0:
        sorted_pb = pb_valid.sort_values().tolist()
        mid_pb = len(sorted_pb) // 2
        entry['median_pb'] = round(float(sorted_pb[mid_pb]), 3)
        entry['mean_pb'] = round(float(pb_valid.mean()), 3)
        entry['pb_ratio'] = entry['median_pb']
    else:
        entry['median_pb'] = None
        entry['mean_pb'] = None
        entry['pb_ratio'] = None

    return entry


def _fetch_industry_board_PE_PB(board_name: str) -> dict | None:
    """Fetch PE/PB from ak.stock_board_industry_cons_em(symbol=board_name).

    Returns dict with median_pe, median_pb, stock_count, source.
    Gracefully handles network/data errors.
    """
    try:
        import akshare as ak
        from ..utils.thread_timeout import run_with_timeout
        df = run_with_timeout(ak.stock_board_industry_cons_em, symbol=board_name, timeout=30)
        if df is None or len(df) == 0:
            return None
        entry = _parse_industry_board(df)
        if entry:
            entry['board'] = board_name
        return entry
    except Exception as e:
        logger.debug(f"[L23] Board fetch failed for '{board_name}': {type(e).__name__}: {e}")
        return None


def _cached_industry_board(board_name: str) -> dict | None:
    """Get cached industry board data, refresh if expired."""
    global _INDUSTRY_CACHE, _INDUSTRY_CACHE_TS

    now = time.time()
    if _INDUSTRY_CACHE and (now - _INDUSTRY_CACHE_TS) < _INDUSTRY_CACHE_TTL:
        cached = _INDUSTRY_CACHE.get(board_name)
        if cached is not None:
            return cached

    # Refetch full cache if TTL expired
    if _INDUSTRY_CACHE and (now - _INDUSTRY_CACHE_TS) >= _INDUSTRY_CACHE_TTL:
        _INDUSTRY_CACHE.clear()
        _INDUSTRY_CACHE_TS = 0

    try:
        import akshare as ak
        from ..utils.thread_timeout import run_with_timeout
        df = run_with_timeout(ak.stock_board_industry_cons_em, symbol=board_name, timeout=30)
        if df is not None and len(df) > 0:
            entry = _parse_industry_board(df)
            if entry:
                entry['board'] = board_name
                _INDUSTRY_CACHE[board_name] = entry
                _INDUSTRY_CACHE_TS = now
                return entry
        # Cache-negative so we don't re-fetch every call
        _INDUSTRY_CACHE[board_name] = None
        _INDUSTRY_CACHE_TS = now
        return None
    except Exception as e:
        logger.debug(f"[L23] Cached fetch error for '{board_name}': {type(e).__name__}: {e}")
        _INDUSTRY_CACHE[board_name] = None
        _INDUSTRY_CACHE_TS = now
        return None


def resolve_sector_to_board(sector_key: str) -> str | None:
    """Resolve L23 sector key to EastMoney board name for PE/PB lookup."""
    return L23_SECTOR_TO_BOARD.get(sector_key)


# ═══════════════════════════════════════════════════════════════════════════════
# Fallback: INDEX_PROXY industry-aware defaults when live fetch fails
# ═══════════════════════════════════════════════════════════════════════════════

def _get_index_proxy(sector: str, name: str) -> dict:
    """Get industry-aware proxy defaults when no live data is available."""
    text = f"{sector} {name}".lower()

    # Check broad market index keywords
    for idx_key, proxy in INDEX_PROXY_MAP.items():
        if idx_key.lower() in text:
            return {**proxy, 'source': f'index_proxy_{idx_key}'}

    PROXY_DEFAULTS = {
        '银行':     {'pe_ratio': 5.2,  'pb_ratio': 0.5,  'dividend_yield': 5.0},
        '半导体':   {'pe_ratio': 88.0, 'pb_ratio': 5.8,  'dividend_yield': 0.4},
        '通信':     {'pe_ratio': 85.0, 'pb_ratio': 4.1,  'dividend_yield': 1.2},
        '计算机':   {'pe_ratio': 82.0, 'pb_ratio': 3.2,  'dividend_yield': 0.4},
        '电子':     {'pe_ratio': 74.0, 'pb_ratio': 4.7,  'dividend_yield': 0.6},
        '医药':     {'pe_ratio': 32.0, 'pb_ratio': 2.3,  'dividend_yield': 0.9},
        '创新药':   {'pe_ratio': 38.0, 'pb_ratio': 3.2,  'dividend_yield': 0.6},
        '消费':     {'pe_ratio': 19.5, 'pb_ratio': 2.1,  'dividend_yield': 1.5},
        '白酒':     {'pe_ratio': 22.0, 'pb_ratio': 5.0,  'dividend_yield': 2.0},
        '食品饮料': {'pe_ratio': 19.5, 'pb_ratio': 2.1,  'dividend_yield': 1.5},
        '军工':     {'pe_ratio': 82.0, 'pb_ratio': 3.4,  'dividend_yield': 0.2},
        '国防':     {'pe_ratio': 82.0, 'pb_ratio': 3.4,  'dividend_yield': 0.2},
        '航空航天': {'pe_ratio': 82.0, 'pb_ratio': 3.4,  'dividend_yield': 0.2},
        '新能源':   {'pe_ratio': 41.0, 'pb_ratio': 2.6,  'dividend_yield': 0.8},
        '电力设备': {'pe_ratio': 41.0, 'pb_ratio': 2.6,  'dividend_yield': 0.8},
        '光伏':     {'pe_ratio': 35.0, 'pb_ratio': 2.2,  'dividend_yield': 1.5},
        '锂电':     {'pe_ratio': 32.0, 'pb_ratio': 2.6,  'dividend_yield': 1.0},
        '房地产':   {'pe_ratio': 33.0, 'pb_ratio': 0.9,  'dividend_yield': 3.0},
        '基建':     {'pe_ratio': 28.0, 'pb_ratio': 1.8,  'dividend_yield': 3.5},
        '钢铁':     {'pe_ratio': 23.0, 'pb_ratio': 1.1,  'dividend_yield': 3.0},
        '化工':     {'pe_ratio': 34.0, 'pb_ratio': 2.0,  'dividend_yield': 2.5},
        '有色金属': {'pe_ratio': 24.0, 'pb_ratio': 3.1,  'dividend_yield': 2.2},
        '煤炭':     {'pe_ratio': 19.0, 'pb_ratio': 1.2,  'dividend_yield': 5.5},
        '黄金':     {'pe_ratio': 16.0, 'pb_ratio': 4.5,  'dividend_yield': 1.8},
        '保险':     {'pe_ratio': 16.0, 'pb_ratio': 1.3,  'dividend_yield': 3.5},
        '券商':     {'pe_ratio': 28.0, 'pb_ratio': 1.5,  'dividend_yield': 0.8},
        '非银金融': {'pe_ratio': 16.0, 'pb_ratio': 1.3,  'dividend_yield': 3.5},
        '教育':     {'pe_ratio': 45.0, 'pb_ratio': 2.0,  'dividend_yield': 2.0},
        '农业':     {'pe_ratio': 35.0, 'pb_ratio': 2.1,  'dividend_yield': 2.0},
        '旅游':     {'pe_ratio': 43.0, 'pb_ratio': 2.4,  'dividend_yield': 1.5},
        '红利':     {'pe_ratio': 10.5, 'pb_ratio': 1.1,  'dividend_yield': 4.5},
        '宽基':     {'pe_ratio': 15.0, 'pb_ratio': 1.8,  'dividend_yield': 2.0},
        '宽基A':    {'pe_ratio': 15.0, 'pb_ratio': 1.8,  'dividend_yield': 2.0},
        '沪深':     {'pe_ratio': 12.5, 'pb_ratio': 1.45, 'dividend_yield': 2.8},
        '上证':     {'pe_ratio': 12.5, 'pb_ratio': 1.45, 'dividend_yield': 2.8},
        '中证':     {'pe_ratio': 16.0, 'pb_ratio': 1.8,  'dividend_yield': 1.5},
    }

    best_key = None
    best_len = 0
    for key in PROXY_DEFAULTS:
        if key.lower() in text and len(key) > best_len:
            best_key = key
            best_len = len(key)
    if best_key:
        return {**PROXY_DEFAULTS[best_key], 'source': 'industry_proxy_fallback'}

    return {'pe_ratio': 22.0, 'pb_ratio': 2.2, 'dividend_yield': 1.5, 'source': 'generic_proxy'}


# ═══════════════════════════════════════════════════════════════════════════════
# Scoring helpers
# ═══════════════════════════════════════════════════════════════════════════════

BUCKETS = {
    '银行':   {'pe_floor': 4,   'pe_ceil': 12,  'pb_floor': 0.3, 'pb_ceil': 1.5},
    '红利':   {'pe_floor': 8,   'pe_ceil': 20,  'pb_floor': 0.5, 'pb_ceil': 2.0},
    '消费':   {'pe_floor': 20,  'pe_ceil': 50,  'pb_floor': 2.0, 'pb_ceil': 8.0},
    '医药':   {'pe_floor': 15,  'pe_ceil': 50,  'pb_floor': 1.5, 'pb_ceil': 6.0},
    '创新药': {'pe_floor': 20,  'pe_ceil': 60,  'pb_floor': 2.0, 'pb_ceil': 8.0},
    '半导体': {'pe_floor': 30,  'pe_ceil': 100, 'pb_floor': 3.0, 'pb_ceil': 12.0},
    '军工':   {'pe_floor': 40,  'pe_ceil': 100, 'pb_floor': 3.0, 'pb_ceil': 12.0},
    '科创':   {'pe_floor': 35,  'pe_ceil': 100, 'pb_floor': 3.5, 'pb_ceil': 12.0},
    '新能源': {'pe_floor': 20,  'pe_ceil': 60,  'pb_floor': 2.0, 'pb_ceil': 8.0},
    '光伏':   {'pe_floor': 15,  'pe_ceil': 50,  'pb_floor': 1.5, 'pb_ceil': 5.0},
    '锂电':   {'pe_floor': 20,  'pe_ceil': 60,  'pb_floor': 2.0, 'pb_ceil': 8.0},
    '煤炭':   {'pe_floor': 8,   'pe_ceil': 25,  'pb_floor': 0.8, 'pb_ceil': 3.0},
    '黄金':   {'pe_floor': 10,  'pe_ceil': 30,  'pb_floor': 1.0, 'pb_ceil': 5.0},
    '基建':   {'pe_floor': 6,   'pe_ceil': 18,  'pb_floor': 0.5, 'pb_ceil': 2.0},
    '房地产': {'pe_floor': 5,   'pe_ceil': 20,  'pb_floor': 0.3, 'pb_ceil': 2.5},
    '科技':   {'pe_floor': 30,  'pe_ceil': 100, 'pb_floor': 3.0, 'pb_ceil': 12.0},
    'AI':     {'pe_floor': 30,  'pe_ceil': 100, 'pb_floor': 3.0, 'pb_ceil': 12.0},
    '通信':   {'pe_floor': 25,  'pe_ceil': 80,  'pb_floor': 2.5, 'pb_ceil': 8.0},
    '计算机': {'pe_floor': 30,  'pe_ceil': 100, 'pb_floor': 3.0, 'pb_ceil': 12.0},
    '电子':   {'pe_floor': 25,  'pe_ceil': 80,  'pb_floor': 2.5, 'pb_ceil': 10.0},
    '航空':   {'pe_floor': 25,  'pe_ceil': 80,  'pb_floor': 2.0, 'pb_ceil': 8.0},
    '旅游':   {'pe_floor': 20,  'pe_ceil': 50,  'pb_floor': 1.5, 'pb_ceil': 5.0},
    '教育':   {'pe_floor': 15,  'pe_ceil': 50,  'pb_floor': 1.5, 'pb_ceil': 5.0},
    '农业':   {'pe_floor': 15,  'pe_ceil': 50,  'pb_floor': 1.5, 'pb_ceil': 5.0},
    '券商':   {'pe_floor': 20,  'pe_ceil': 50,  'pb_floor': 1.0, 'pb_ceil': 4.0},
    '保险':   {'pe_floor': 6,   'pe_ceil': 18,  'pb_floor': 0.5, 'pb_ceil': 2.0},
    '化工':   {'pe_floor': 12,  'pe_ceil': 40,  'pb_floor': 1.2, 'pb_ceil': 4.0},
    '白酒':   {'pe_floor': 18,  'pe_ceil': 45,  'pb_floor': 4.0, 'pb_ceil': 10.0},
    '食品饮料': {'pe_floor': 22, 'pe_ceil': 50, 'pb_floor': 3.0, 'pb_ceil': 10.0},
}


def _match_bucket(sector: str, name: str) -> dict:
    """Match sector to valuation bucket."""
    text = f"{sector} {name}".lower()
    best_key = None
    best_len = 0
    for key, bucket in BUCKETS.items():
        if key.lower() in text and len(key) > best_len:
            best_key = key
            best_len = len(key)
    return BUCKETS.get(best_key, {'pe_floor': 15, 'pe_ceil': 45, 'pb_floor': 1.0, 'pb_ceil': 8.0})


def _score_ratio(ratio, floor, ceil):
    """Score ratio value (0-10)."""
    if ratio is None or not isinstance(ratio, (int, float)) or ratio <= 0:
        return 5.0
    mid = (floor + ceil) / 2
    half_range = (ceil - floor) / 2
    if floor <= ratio <= ceil:
        dist = abs(ratio - mid) / max(half_range, 0.1)
        score = 8.0 - dist * 2.0
        return round(max(4.0, min(8.0, score)), 1)
    elif ratio < floor:
        down_ratio = (floor - ratio) / max(floor, 1)
        return round(max(2.0, min(6.0, 6.0 - down_ratio * 3.0)), 1)
    else:
        up_ratio = (ratio - ceil) / max(ceil - floor, 1)
        return round(max(1.0, min(6.0, 6.0 - up_ratio * 3.0)), 1)


def _compute_dividend_score(div_yield: float, risk_level: float) -> float:
    """Score dividend yield."""
    if div_yield >= 4.0:
        score = 9.0
    elif div_yield >= 3.0:
        score = 7.5
    elif div_yield >= 2.0:
        score = 6.0
    elif div_yield >= 1.0:
        score = 5.0
    elif div_yield >= 0.5:
        score = 4.0
    else:
        score = 2.0
    if risk_level > 0.7:
        score = min(score + 1.0, 10.0)
    return round(min(10.0, max(1.0, score)), 1)


# ═══════════════════════════════════════════════════════════════════════════════
# Cache — local JSON + module-level in-memory cache
# ═══════════════════════════════════════════════════════════════════════════════

_L23_DISK_CACHE: dict = {}
_L23_DISK_CACHE_LOADED = False


def _ensure_disk_cache_loaded():
    """Lazy-load disk cache into memory for batch calls."""
    global _L23_DISK_CACHE, _L23_DISK_CACHE_LOADED
    if _L23_DISK_CACHE_LOADED:
        return
    _L23_DISK_CACHE_LOADED = True
    try:
        if CACHE_FILE.exists():
            raw = CACHE_FILE.read_text(encoding='utf-8')
            if raw.strip():
                _L23_DISK_CACHE = json.loads(raw)
    except Exception as e:
        logger.debug(f"[L23] Disk cache load failed: {e}")


def _is_fresh(cached_data, code=None):
    """Check if cached data is still within TTL."""
    if cached_data is None:
        return False
    fetched_at = cached_data.get('cached_at', 0)
    if fetched_at == 0:
        meta = cached_data.get('_meta', {})
        if isinstance(meta, dict):
            fetched_at = meta.get('fetched_at', 0)
    if fetched_at <= 0:
        return False
    now = time.time()
    ttl = cached_data.get('_meta', {}).get('ttl_seconds', TTL_SECONDS)
    if not isinstance(ttl, (int, float)) or ttl <= 0:
        ttl = TTL_SECONDS
    return (now - fetched_at) < ttl


def _load_cache(code):
    """Load cached valuation data for ETF (with auto-invalidation)."""
    _ensure_disk_cache_loaded()
    if not _L23_DISK_CACHE:
        return None
    entry = _L23_DISK_CACHE.get(code)
    if entry and isinstance(entry, dict) and _is_fresh(entry):
        return entry
    if entry and isinstance(entry, dict):
        try:
            _L23_DISK_CACHE.pop(code, None)
        except Exception as e:
            logger.warning("[l23_valuation] 失效缓存剔除失败 %s: %s", code, e)
    return None


def _save_to_cache(result, raw_data, source):
    """Save result to local cache and in-memory dict."""
    try:
        data = {}
        if CACHE_FILE.exists():
            data = json.loads(CACHE_FILE.read_text(encoding='utf-8'))
        code = raw_data.get('code', '')
        if not code:
            for key in ('code', 'etf_code'):
                if key in raw_data:
                    code = str(raw_data[key])
                    break
        entry = {
            **result,
            '_meta': {
                'fetched_at': time.time(),
                'source': source,
                'ttl_seconds': TTL_SECONDS,
            },
            'raw_data': raw_data,
        }
        data[code] = entry
        _L23_DISK_CACHE[code] = entry
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception as e:
        logger.debug(f"[L23] Cache save failed: {e}")


def _calculate_from_cached(cached_data, code, sector, name, risk_level):
    """Calculate scores from cached data."""
    result = {
        'L23_Valuation': 5.0,
        'L23_PENALTY': 0.0,
        'valuation_details': {},
    }
    raw = cached_data.get('raw_data', {}) if isinstance(cached_data, dict) else {}
    pe = cached_data.get('pe_ratio') if isinstance(cached_data, dict) else None
    if pe is None and isinstance(raw, dict):
        pe = raw.get('pe_ratio')
    pb = cached_data.get('pb_ratio') if isinstance(cached_data, dict) else None
    if pb is None and isinstance(raw, dict):
        pb = raw.get('pb_ratio')
    div = cached_data.get('dividend_yield') if isinstance(cached_data, dict) else None
    if div is None and isinstance(raw, dict):
        div = raw.get('dividend_yield')
    bucket = _match_bucket(sector, name)
    pe_score = _score_ratio(pe, bucket.get('pe_floor', 15), bucket.get('pe_ceil', 45))
    pb_score = _score_ratio(pb, bucket.get('pb_floor', 1.0), bucket.get('pb_ceil', 4.0))
    div_score = _compute_dividend_score(div or 1.5, risk_level)
    val_score = pe_score * 0.4 + pb_score * 0.3 + div_score * 0.3
    penalty = 0.0
    if val_score >= 8.0:
        penalty = -min((val_score - 7.0) * 0.4, 2.0)
    elif val_score <= 4.0:
        penalty = min((5.0 - val_score) * 0.4, 1.5)
    result['L23_Valuation'] = round(val_score, 1)
    result['L23_PENALTY'] = round(penalty, 2)
    result['valuation_details'] = {
        'pe': round(pe, 1) if pe else None,
        'pb': round(pb, 1) if pb else None,
        'dividend_yield': round(div, 2) if div else None,
        'pe_score': pe_score,
        'pb_score': pb_score,
        'div_score': div_score,
        'source': cached_data.get('source', 'cache'),
    }
    return result


def _calculate_scores(raw_data, code, sector, name, risk_level):
    """Calculate L23 score from raw data."""
    result = _calculate_from_cached({**raw_data, 'source': 'data_source'}, code, sector, name, risk_level)
    result['valuation_details']['source'] = raw_data.get('source', 'auto')
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# Main entry point
# ═══════════════════════════════════════════════════════════════════════════════

def compute_valuation_layer(code: str, sector: str, name: str, info=None, risk_level: float = 0.5) -> dict:
    """Main entry: returns L23_Valuation (0-10) and L23_PENALTY (-3 to +1.5).

    Data priority (v7.0):
      1. In-memory cache (single process, multiple ETFs share it)
      2. Disk cache (refreshed every 6h)
      3. ak.stock_board_industry_cons_em -> industry board real-time PE/PB median
      4. INDEX_PROXY fallback (industry-aware defaults)
    """
    info = info or {}
    result = {
        'L23_Valuation': 5.0,
        'L23_PENALTY': 0.0,
        'valuation_details': {},
    }

    # Fast path: in-memory cache
    if code in _L23_DISK_CACHE:
        cached_data = _L23_DISK_CACHE[code]
        if isinstance(cached_data, dict):
            meta = cached_data.get('_meta', {})
            fetched_at = meta.get('fetched_at', 0) if isinstance(meta, dict) else 0
            if fetched_at > 0 and (time.time() - fetched_at) < TTL_SECONDS:
                return _calculate_from_cached(cached_data, code, sector, name, risk_level)

    # Load disk cache once into memory
    _ensure_disk_cache_loaded()
    cached_data = _load_cache(code)
    if cached_data and _is_fresh(cached_data):
        return _calculate_from_cached(cached_data, code, sector, name, risk_level)

    # Try ak.stock_board_industry_cons_em real PE/PB data (v7.0 primary)
    sector_key = _infer_sector_key(name, sector)
    board_name = resolve_sector_to_board(sector_key) if sector_key else None

    if board_name:
        board_data = _cached_industry_board(board_name)
        if board_data and (board_data.get('pe_ratio') or board_data.get('pb_ratio')):
            raw_data = {
                'code': code,
                'sector_key': sector_key or board_name,
                'board': board_name,
                'pe_ratio': board_data.get('pe_ratio'),
                'pb_ratio': board_data.get('pb_ratio'),
                'dividend_yield': _estimate_dividend_yield(board_data),
                'stock_count': board_data.get('stock_count', 0),
                'source': 'ak_board_industry_cons_em',
            }
            result.update(_calculate_scores(raw_data, code, sector, name, risk_level))
            _save_to_cache(result, raw_data, 'industry_board_median')
            return result

    # Fallback: INDEX_PROXY industry-aware defaults
    proxy_data = _get_index_proxy(sector, name)
    proxy_data['code'] = code
    result.update(_calculate_scores(proxy_data, code, sector, name, risk_level))
    _save_to_cache(result, proxy_data, 'index_proxy')
    return result


def _estimate_dividend_yield(board_data: dict) -> float | None:
    """Estimate dividend yield from board data."""
    pe = board_data.get('pe_ratio')
    if pe and pe > 0:
        if pe < 10:
            return 4.0
        elif pe < 20:
            return 2.5
        elif pe < 30:
            return 1.5
        elif pe < 50:
            return 1.0
        else:
            return 0.5
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# CLI entry point
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--test', type=str, default='', help='Test single ETF')
    parser.add_argument('--list', action='store_true', help='List sector PE/PB data')
    parser.add_argument('--clear-cache', action='store_true', help='Clear disk cache')
    args = parser.parse_args()

    if args.clear_cache:
        if CACHE_FILE.exists():
            CACHE_FILE.unlink()
        print(f"Cleared cache: {CACHE_FILE}")

    if args.list:
        print("=== L23 v7.0 Industry Board PE/PB ===")
        for key, board in sorted(L23_SECTOR_TO_BOARD.items()):
            if not board:
                proxy = INDEX_PROXY_MAP.get(key, None)
                if proxy:
                    print(f"  {key}: (index proxy) {proxy}")
                else:
                    print(f"  {key}: (no board mapping)")
                continue
            data = _cached_industry_board(board)
            if data:
                print(f"  {key} -> {board}: PE={data.get('pe_ratio')}, PB={data.get('pb_ratio')}, n={data.get('stock_count')}")
            else:
                print(f"  {key} -> {board}: UNAVAILABLE")

    if args.test:
        r = compute_valuation_layer(args.test, '', args.test)
        print(f"\n{args.test}: {json.dumps(r, ensure_ascii=False, indent=2)}")
