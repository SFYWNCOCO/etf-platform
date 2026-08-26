"""l22_market_pendulum.py — 周期钟摆层 (k021 Howard Marks)

基于 Howard Marks《Mastering the Market Cycle》框架:
  价格 = 价值 × 周期因子 (0.5底部 → 2.0+顶部)
  顶级投资者从周期位置获取大部分超额收益

实现: 从ETF的20d趋势分布反推当前市场的周期位置(钟摆角度)
替代当前不可用的QVIX(akshare broken → always "unknown")
"""
from typing import Dict

# 连续分段线性锚点 (角度, 分数)：恐慌底→高分，过热→低分。端点之间线性插值。
# 08-12 修复：原 panic 分支 (angle+25)/5 符号反转（越恐慌得分越低），且分段
# 边界跳变 1.5~2.5 分。改为单调连续，angle<-30 逼近 10，>30 封底 1.0。
_PENDULUM_ANCHORS = (
    (-30, 9.5), (-15, 8.0), (-5, 6.5), (5, 5.0), (15, 3.5), (25, 2.0), (30, 1.0),
)


def _pendulum_score(angle: float) -> float:
    if angle <= _PENDULUM_ANCHORS[0][0]:
        return min(10.0, _PENDULUM_ANCHORS[0][1] + (_PENDULUM_ANCHORS[0][0] - angle) * 0.1)
    for (a0, s0), (a1, s1) in zip(_PENDULUM_ANCHORS, _PENDULUM_ANCHORS[1:]):
        if angle <= a1:
            t = (angle - a0) / (a1 - a0)
            return s0 + t * (s1 - s0)
    return max(1.0, _PENDULUM_ANCHORS[-1][1] - (angle - _PENDULUM_ANCHORS[-1][0]) * 0.1)


def _pendulum_angle(change_20d_pct: float, vol_20d: float,
                    volume_ratio: float, premium_pct: float) -> float:
    """计算周期钟摆角度 (-45°=恐慌底, +45°=狂热顶)
    
    核心洞察 (k021§三):
      - 顶部: 价格远高于价值, 波动率被压制(所有人乐观)
      - 底部: 价格远低于价值, 波动率飙升(恐慌)
      - "传统风险度量在顶部最低, 底部最高" — 倒置!
    
    钟摆 = f(涨跌幅方向, 波动率抑制/放大, 量比, 折溢价)
    """
    angle = 0.0
    
    # 1. 20日涨跌幅方向
    if change_20d_pct > 15:
        angle += 25  # 暴涨 → 钟摆偏向过热
    elif change_20d_pct > 8:
        angle += 15
    elif change_20d_pct > 3:
        angle += 8
    elif change_20d_pct > -3:
        angle += 0
    elif change_20d_pct > -8:
        angle -= 8
    elif change_20d_pct > -15:
        angle -= 15
    else:
        angle -= 25  # 暴跌 → 钟摆偏向恐慌
    
    # 2. 波动率修正 (k021§四: 波动率在顶部低/底部高)
    if vol_20d < 12:
        angle += 10  # 低波 → 过度乐观 → 钟摆偏顶
    elif vol_20d > 40:
        angle -= 15  # 高波 → 恐慌 → 钟摆偏底
    elif vol_20d > 25:
        angle -= 5
    
    # 3. 量比信号 (放量上涨=过热, 缩量下跌=恐慌底)
    if volume_ratio > 1.5 and change_20d_pct > 3:
        angle += 10  # 放量上攻 → 可能过热
    elif volume_ratio < 0.6 and change_20d_pct < -5:
        angle -= 10  # 缩量阴跌 → 底部磨底
    
    # 4. 折溢价信号 (k007: 溢价=过热, 折价=恐慌)
    if abs(premium_pct) < 0.001:
        pass  # no data
    elif premium_pct > 2:
        angle += 8
    elif premium_pct > 1:
        angle += 4
    elif premium_pct < -2:
        angle -= 8
    elif premium_pct < -1:
        angle -= 4
    
    return max(-45, min(45, angle))


def _angle_to_regime(angle: float) -> Dict:
    """钟摆角度 → 市场状态 + 投资建议
    
    -45° ─────── 0° ─────── +45°
    恐慌底        中性         狂热顶
    """
    if angle <= -30:
        return {
            "regime": "panic",
            "label": "🔴 恐慌底",
            "risk_mult": 0.6,  # 低风险: 买入安全边际大
            "advice": "价格远低于价值 → 逐步建仓, 买入超跌优质资产",
            "cycle_factor": 0.5,  # 价格=价值×0.5
        }
    elif angle <= -15:
        return {
            "regime": "fear",
            "label": "🟠 恐慌",
            "risk_mult": 0.8,
            "advice": "市场偏弱 → 配置防御型+超跌反弹标的",
            "cycle_factor": 0.7,
        }
    elif angle <= -5:
        return {
            "regime": "cautious",
            "label": "🟡 谨慎",
            "risk_mult": 0.9,
            "advice": "弱势格局 → 减仓等待确认信号",
            "cycle_factor": 0.9,
        }
    elif angle <= 5:
        return {
            "regime": "neutral",
            "label": "⚪ 中性",
            "risk_mult": 1.0,
            "advice": "周期中位 → 均衡配置, 关注行业轮动",
            "cycle_factor": 1.0,
        }
    elif angle <= 15:
        return {
            "regime": "optimistic",
            "label": "🟢 乐观",
            "risk_mult": 1.1,
            "advice": "市场偏强 → 持有为主, 警惕过热信号",
            "cycle_factor": 1.2,
        }
    elif angle <= 30:
        return {
            "regime": "greed",
            "label": "🟠 贪婪",
            "risk_mult": 1.3,
            "advice": "市场过热 → 逐步减仓, 增加防御配置",
            "cycle_factor": 1.6,
        }
    else:
        return {
            "regime": "euphoria",
            "label": "🔴 狂热顶",
            "risk_mult": 1.0,  # 实际风险最高但传统度量最低
            "advice": "⚠️ 价格远高于价值 → 大幅减仓, 锁定利润",
            "cycle_factor": 2.0,
        }


def score_pendulum_layer(sector: str, risk_level: float = 0.5, 
                         etf_code: str = "", trend_data: dict = None) -> Dict:
    """L22 周期钟摆层 — 市场周期位置评分
    
    返回钟摆角度 + 市场状态 + 周期调整系数
    可直接替代QVIX作为市场状态指示器
    
    评分逻辑 (0-10):
      - 恐慌底(angle≤-30): 8分 — 买入机会最大
      - 中性(angle≈0): 5分 — 标准配置
      - 狂热顶(angle≥30): 2分 — 风险最高
    """
    from etf_platform.data.kline import get_trend
    
    angle = 0.0
    chg20 = 0.0
    vol = 15.0
    vr = 1.0
    prem = 0.0
    
    # 尝试获取ETF趋势数据, 用单只ETF的趋势反推整体市场位置
    if etf_code:
        trend = get_trend(etf_code)
        if trend:
            chg20 = trend.change_20d
            vol = trend.volatility_20d
            vr = trend.volume_ratio_5_20
    
    if trend_data:
        chg20 = trend_data.get("change_20d", chg20)
        vol = trend_data.get("volatility_20d", vol)
        vr = trend_data.get("volume_ratio_5_20", vr)
        prem = trend_data.get("premium_pct", prem)
    
    angle = _pendulum_angle(chg20, vol, vr, prem)
    regime = _angle_to_regime(angle)
    
    # 钟摆越接近恐慌底, 潜在收益越高
    # v8.15: 连续分段线性评分（08-12 修复 panic 符号反转 + 分段边界跳变）
    base_score = _pendulum_score(angle)

    score = base_score
    
    # 行业修正: 防御型行业在过热期加分, 进攻型在恐慌期加分
    defensive = any(kw in str(sector) for kw in ["红利", "消费", "公用", "医疗", "黄金"])
    aggressive = any(kw in str(sector) for kw in ["科技", "半导体", "AI", "军工", "新能源"])
    
    if defensive and regime["regime"] in ("greed", "euphoria"):
        score += 1.0  # 防御型在过热期更安全
    if aggressive and regime["regime"] in ("panic", "fear"):
        score += 0.5  # 进攻型在恐慌底弹性更大
    
    # v8.14: Intra-angle jitter for same-angle ETFs (e.g., same 20d trend across sectors)
    # Uses code-based deterministic hash so same ETF always gets same jitter
    from ..utils.hash_jitter import pair_sum_jitter
    score += pair_sum_jitter(etf_code, 7, 0.15)  # range [-0.45, +0.45]
    
    score = round(max(1.0, min(10.0, score)), 1)
    
    return {
        "score": score,
        "angle": round(angle, 1),
        "regime": regime["regime"],
        "label": regime["label"],
        "cycle_factor": regime["cycle_factor"],
        "risk_mult": regime["risk_mult"],
        "advice": regime["advice"],
        "change_20d": round(chg20, 1),
        "volatility_20d": round(vol, 1),
        "volume_ratio": round(vr, 2),
    }
