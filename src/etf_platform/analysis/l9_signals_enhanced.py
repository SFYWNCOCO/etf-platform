# -*- coding: utf-8 -*-
"""Enhanced L9_Signals — Causal + Sector-Specific Events + Risk-Adjusted + Market Reality.

v7.4: Major signal enhancement:
1. Causal engine scaling increased 5x (5000->25000) for stronger differentiation
2. Sector event relevance weights increased to amplify hot-cold sector gaps
3. Added volume_price_signal component for market reality feedback
4. Weight redistribution: causal 0.30, sector 0.30, risk 0.15, market 0.25
"""
import logging
import sys
import io
from typing import Dict

logger = logging.getLogger(__name__)

_MARKET_API_AVAILABLE = None


def _get_market_api_available() -> bool:
    global _MARKET_API_AVAILABLE
    if _MARKET_API_AVAILABLE is None:
        try:
            import akshare as ak
            df = ak.fund_etf_hist_em(symbol='510300', period='daily', start_date='20260601', end_date='20260705')
            _MARKET_API_AVAILABLE = df is not None and not df.empty and len(df) > 0
        except Exception as e:
            logger.warning("[l9_signals] market API probe failed: %s", e)
            _MARKET_API_AVAILABLE = False
        if _MARKET_API_AVAILABLE:
            logger.info("[l9_signals] market API available")
        else:
            logger.warning("[l9_signals] market API UNAVAILABLE - using hybrid approach")
    return _MARKET_API_AVAILABLE


def get_enhanced_signal_score(code: str, live: bool = True) -> float:
    """Calculate enhanced L9_Signals score for an ETF.
    
    v7.4: Hybrid approach combining:
    1. Causal engine (event impact) - scaled up 5x
    2. Sector-specific event matching - amplified weights
    3. Volume/price signal (market reality) - NEW
    4. Risk-adjusted vulnerability - reduced weight
    """
    causal = _get_causal_signal(code)
    sector_match = _get_sector_event_score(code)
    market_signal = _get_volume_price_signal(code, live)
    risk_adj = _get_risk_adjusted_score(code)
    
    # v7.4: Redistributed weights - market reality gets more weight
    final_score = causal * 0.30 + sector_match * 0.30 + market_signal * 0.25 + risk_adj * 0.15
    
    return round(max(1.0, min(10.0, final_score)), 1)


def _get_causal_signal(code: str) -> float:
    """Get signal score from causal engine with aggressive scaling.
    
    v7.4: Scaling increased from 5000 to 25000 to amplify differentiation.
    """
    try:
        from ..analysis.causal import CausalEngine
        from ..data.events import inject_events
        
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            engine = CausalEngine()
            inject_events(engine, verbose=False)
            results = engine.scan_all()
        finally:
            sys.stdout = old_stdout
        
        if not results or code not in results:
            return 5.0
        
        total_impact = results[code]["total_impact"]
        
        # v7.4: Increased scaling from 5000 to 25000
        # This maps [-0.0002, +0.0002] to [0.0, 10.0] instead of [3.0, 7.0]
        score = 5.0 + total_impact * 25000
        return max(1.0, min(10.0, score))

    except (KeyError, ValueError, TypeError, AttributeError, ImportError) as e:
        logger.debug(f"[l9_signals] causal signal failed for {code}: {e}")
        return 5.0


def _get_sector_event_score(code: str) -> float:
    """Score based on how well an ETF's sector matches current hot events.
    
    v7.4: Amplified weights to increase hot/cold sector gaps.
    Range expanded from [3.5, 7.5] to [2.5, 8.5].
    """
    try:
        from ..config_loader import load_etfs
        etfs = load_etfs()
        info = etfs.get(code, {})
        sector = info.get("sector", "其他")
        
        # v7.4: Amplified event relevance - wider range
        sector_event_relevance = {
            # Very hot sectors
            "半导体": 8.5,
            "半导体设备": 8.5,
            "AI算力": 8.0,
            "AI/科技": 8.0,
            "硬科技": 8.0,
            "通信/光模块": 7.5,
            "云计算/算力": 7.5,
            "数字经济": 7.0,
            "机器人/智造": 7.0,
            
            # Hot sectors
            "新能源": 7.0,
            "新能源电力": 7.0,
            "电池": 7.0,
            "军工": 7.5,
            "军工电子": 7.5,
            "医药": 6.5,
            "中药": 6.0,
            "纳斯达克": 7.0,
            
            # Medium sectors
            "消费": 5.5,
            "白酒消费": 5.5,
            "旅游消费": 5.5,
            "金融": 5.0,
            "银行": 4.5,
            "证券": 5.5,
            "券商": 5.5,
            "家电": 6.0,
            "汽车": 5.5,
            "新能源车": 6.0,
            "碳中和": 6.0,
            
            # Stable/defensive sectors
            "利率债": 4.0,
            "货币基金": 3.0,
            "黄金": 6.0,
            "周期/资源": 5.5,
            "有色": 5.5,
            "公用事业": 5.0,
            "红利/价值": 5.0,
            "红利+低波": 5.0,
            
            # Cross-border
            "跨境": 5.5,
            "美股": 6.0,
            "标普": 6.0,
            "日经": 5.5,
            
            # Broad index
            "宽基A": 5.5,
            "宽基": 5.5,
            "全市场": 5.5,
            "综合": 5.5,
            "大盘蓝筹": 5.5,
            "中盘成长": 5.5,
            "小盘价值": 5.0,
        }
        
        best_score = 5.0
        for key, score in sector_event_relevance.items():
            if key in sector or sector in key:
                best_score = score
                break
        
        if best_score == 5.0:
            for key, score in sector_event_relevance.items():
                if key.lower() in sector.lower() or sector.lower() in key.lower():
                    best_score = score
                    break
        
        return best_score

    except (KeyError, ValueError, TypeError, AttributeError, ImportError) as e:
        logger.debug(f"[l9_signals] sector event score failed for {code}: {e}")
        return 5.0


def _get_volume_price_signal(code: str, live: bool = True) -> float:
    """Market reality signal from price/volume data.
    
    v7.4: NEW component. Uses recent price trend and volume to gauge
    whether the market is actually rewarding this ETF.
    Higher = recent uptrend with healthy volume = positive signal.
    
    Returns 1-10 score.
    """
    if not live:
        # Offline: use a simple heuristic based on code patterns
        # This gives some differentiation even without live data
        return _offline_volume_proxy(code)
    
    try:
        import akshare as ak
        df = ak.fund_etf_hist_em(symbol=code, period='daily', 
                                  start_date='20260601', end_date='20260705')
        if df is None or df.empty or len(df) < 10:
            return 5.0
        
        # Calculate recent momentum (last 5 days vs 5-10 days ago)
        recent = df.tail(5)["涨跌幅"].astype(float).mean()
        older = df.iloc[-10:-5]["涨跌幅"].astype(float).mean()
        momentum = recent - older
        
        # Volume health: is volume increasing with price?
        if "成交量" in df.columns:
            vol_recent = df.tail(5)["成交量"].astype(float).mean()
            vol_older = df.iloc[-10:-5]["成交量"].astype(float).mean()
            vol_ratio = vol_recent / max(vol_older, 1)
        else:
            vol_ratio = 1.0
        
        # Score: momentum + volume confirmation
        # momentum: [-3%, +3%] maps to [-2, +2]
        # volume: ratio < 0.8 = penalty, > 1.2 = bonus
        score = 5.0 + momentum * 30 + (vol_ratio - 1.0) * 2.0
        return max(1.0, min(10.0, score))

    except Exception as e:
        logger.warning("[l9_signals] _online_volume_signal failed: %s", e)
        return 5.0


def _offline_volume_proxy(code: str) -> float:
    """Offline proxy for volume/price signal.
    
    Uses fee + type heuristics as a weak proxy for market activity.
    Lower fee ETFs tend to have higher volume = more signal sensitivity.
    """
    try:
        from ..config_loader import load_etfs
        etfs = load_etfs()
        info = etfs.get(code, {})
        fee = info.get("fee", 0.005)
        etf_type = info.get("type", "")
        sector = info.get("sector", "其他")
        
        # Base: fee-based proxy (lower fee = more volume = more signal potential)
        if fee <= 0.0005:
            base = 6.0
        elif fee <= 0.001:
            base = 5.5
        elif fee <= 0.002:
            base = 5.0
        else:
            base = 4.5
        
        # Type adjustments
        if "杠杆" in etf_type or "杠杆" in str(sector):
            base += 1.0  # Leveraged = more volatile = more signals
        elif "做空" in etf_type or "做空" in str(sector):
            base -= 0.5
        elif "货币" in etf_type or "货币" in str(sector):
            base -= 1.5  # Money funds = boring
        elif "债" in etf_type or "债" in str(sector):
            base -= 0.5
        
        return max(1.0, min(10.0, base))
    except (KeyError, ValueError, TypeError, AttributeError, ImportError):
        return 5.0


def _get_risk_adjusted_score(code: str) -> float:
    """Score based on ETF's risk profile and event sensitivity.
    
    v7.4: Reduced weight in final score (now 0.15 vs 0.30), 
    so this component has less influence.
    """
    try:
        from ..config_loader import load_etfs
        etfs = load_etfs()
        info = etfs.get(code, {})
        
        risk_level = info.get("risk_level", 0.5)
        etf_type = info.get("type", "")
        sector = info.get("sector", "其他")
        
        base_score = 3.0 + risk_level * 5.0
        
        if "货币" in etf_type or "货币" in sector:
            base_score = 2.0
        elif "债" in etf_type or "债" in sector:
            base_score = 3.0 + risk_level * 2.0
        elif "跨境" in etf_type or "QDII" in etf_type:
            base_score = 5.0 + risk_level * 2.0
        elif "商品" in etf_type or "商品" in sector:
            base_score = 4.0 + risk_level * 3.0
        
        leverage = info.get("leverage", 1.0)
        if leverage > 1:
            base_score = min(10.0, base_score * leverage)
        
        return max(1.0, min(10.0, base_score))

    except (KeyError, ValueError, TypeError, AttributeError, ImportError) as e:
        logger.debug(f"[l9_signals] risk adjusted score failed for {code}: {e}")
        return 5.0


def get_signal_components(code: str, live: bool = True) -> Dict:
    """Get detailed breakdown of L9 signal components for debugging."""
    return {
        "causal": _get_causal_signal(code),
        "sector_match": _get_sector_event_score(code),
        "market_signal": _get_volume_price_signal(code, live),
        "risk_adjusted": _get_risk_adjusted_score(code),
    }
