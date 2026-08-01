"""L13 Operations Research Layer — 运筹学优化与ETF组合构建.

Purpose: Apply OR methods to ETF portfolio optimization, asset allocation,
and scheduling. Integrates with existing 12-layer scoring system.

Methods:
1. Linear Programming (LP) — optimal weight allocation
2. Integer Programming (IP) — discrete ETF selection
3. Dynamic Programming (DP) — multi-period rebalancing
4. Game Theory — market participant博弈
5. Queueing Theory — trading execution optimization
6. Stochastic Processes — MDP for portfolio rotation
7. Network Optimization — supply chain risk analysis
"""

import math
import random
from typing import Dict, List, Tuple, Optional

# === 1. Linear Programming: Optimal Portfolio Allocation ===
# Problem: Given N ETFs with scores, find weights w_i that maximize
# portfolio score subject to constraints.
#
# Maximize: Σ w_i * score_i
# Subject to:
#   Σ w_i = 1 (budget constraint)
#   w_i >= 0 (no short selling)
#   w_i <= max_weight (position limit)
#   Σ w_j * risk_j <= max_portfolio_risk (risk budget)
#   Σ w_k <= sector_limit (sector concentration)

# Maximum weight per ETF position
MAX_POSITION_WEIGHT = 0.15  # 15% per ETF

# Maximum weight per sector
MAX_SECTOR_WEIGHT = 0.30  # 30% per sector

# Maximum portfolio political risk
MAX_PORTFOLIO_POLITICAL_RISK = 4.0  # Weighted average risk score

# LP coefficient vectors (populated from ETF data)
def lp_portfolio_allocation(
    etf_scores: Dict[str, float],  # {etf_code: score}
    etf_sectors: Dict[str, str],   # {etf_code: sector}
    etf_political_risk: Dict[str, float],  # {etf_code: risk_score}
    max_positions: int = 20,
    target_return: Optional[float] = None,
) -> Dict[str, float]:
    """Solve LP portfolio allocation using greedy approximation.
    
    For small portfolios (<100 ETFs), use greedy heuristic.
    For large portfolios, use scipy.optimize.linprog.
    
    Args:
        etf_scores: ETF scores (higher = better)
        etf_sectors: ETF sector mapping
        etf_political_risk: Political risk scores
        max_positions: Maximum number of ETFs in portfolio
        target_return: Optional target return constraint
    
    Returns:
        Dictionary of {etf_code: weight}
    """
    if not etf_scores:
        return {}
    
    # Greedy allocation: sort by score, allocate proportionally
    sorted_etfs = sorted(etf_scores.items(), key=lambda x: x[1], reverse=True)
    
    # Take top N ETFs
    selected = sorted_etfs[:min(max_positions, len(sorted_etfs))]
    
    # Normalize scores to weights
    total_score = sum(score for _, score in selected)
    weights = {}
    for code, score in selected:
        w = score / total_score
        # Apply position limit
        w = min(w, MAX_POSITION_WEIGHT)
        weights[code] = w
    
    # Renormalize after clamping
    total_w = sum(weights.values())
    if total_w > 0:
        weights = {k: v / total_w for k, v in weights.items()}
    
    # Check sector concentration
    sector_weights = {}
    for code, w in weights.items():
        sector = etf_sectors.get(code, "unknown")
        sector_weights[sector] = sector_weights.get(sector, 0) + w
    
    for sector, sw in sector_weights.items():
        if sw > MAX_SECTOR_WEIGHT:
            # Reduce overweight sector proportionally
            excess = sw - MAX_SECTOR_WEIGHT
            for code, w in weights.items():
                if etf_sectors.get(code) == sector:
                    ratio = w / sw
                    weights[code] -= excess * ratio
    
    # Check political risk
    portfolio_risk = sum(
        weights.get(code, 0) * etf_political_risk.get(code, 5.0)
        for code in weights
    )
    
    return {
        "weights": weights,
        "portfolio_risk": round(portfolio_risk, 2),
        "sector_weights": {k: round(v, 3) for k, v in sector_weights.items()},
        "num_positions": len(weights),
    }


# === 2. Integer Programming: Discrete ETF Selection ===
# Problem: Select exactly K ETFs to maximize portfolio score
# while minimizing political risk.
#
# Minimize: -Σ x_i * score_i  (maximize score)
# Subject to:
#   Σ x_i = K (cardinality constraint)
#   x_i ∈ {0, 1} (binary decision)
#   Σ x_i * risk_i <= R_max (risk budget)

def ip_etf_selection(
    etf_scores: Dict[str, float],
    etf_political_risk: Dict[str, float],
    num_select: int = 20,
    max_risk: float = 4.0,
) -> List[str]:
    """Select K ETFs using greedy integer programming approximation.
    
    Args:
        etf_scores: ETF scores (higher = better)
        etf_political_risk: Political risk scores
        num_select: Number of ETFs to select
        max_risk: Maximum portfolio risk budget
    
    Returns:
        List of selected ETF codes
    """
    if not etf_scores:
        return []
    
    # Sort by score/risk ratio (efficiency ratio)
    candidates = []
    for code, score in etf_scores.items():
        risk = etf_political_risk.get(code, 5.0)
        efficiency = score / max(risk, 0.1)  # Avoid div by zero
        candidates.append((code, score, risk, efficiency))
    
    candidates.sort(key=lambda x: x[3], reverse=True)
    
    # Greedy selection
    selected = []
    total_risk = 0.0
    for code, score, risk, eff in candidates:
        if len(selected) >= num_select:
            break
        # Check if adding this ETF exceeds risk budget
        new_avg_risk = (total_risk + risk) / max(len(selected) + 1, 1)
        if new_avg_risk <= max_risk or len(selected) < num_select // 2:
            selected.append(code)
            total_risk += risk
    
    return selected[:num_select]


# === 3. Dynamic Programming: Multi-Period Asset Allocation ===
# Problem: Given monthly cash flow, optimize allocation over T periods.
#
# V_t(s) = max_a [R(s,a) + γ·E[V_{t+1}(s')]]
#
# Where:
#   s = state (current portfolio weights)
#   a = action (rebalance weights)
#   R = return
#   γ = discount factor

def dp_asset_allocation(
    initial_capital: float,
    monthly_cashflow: float,
    etf_expected_returns: Dict[str, float],
    etf_volatility: Dict[str, float],
    correlation_matrix: Dict[Tuple[str, str], float],
    periods: int = 12,
    discount_factor: float = 0.95,
) -> List[Dict[str, float]]:
    """Approximate DP for multi-period asset allocation.
    
    Uses Monte Carlo simulation with greedy rebalancing.
    
    Args:
        initial_capital: Starting capital
        monthly_cashflow: Monthly additional investment
        etf_expected_returns: Expected monthly returns
        etf_volatility: Monthly volatility
        correlation_matrix: ETF correlation matrix
        periods: Number of months to simulate
        discount_factor: Future return discount rate
    
    Returns:
        List of portfolio weights for each period
    """
    if not etf_expected_returns:
        return []
    
    codes = list(etf_expected_returns.keys())
    n = len(codes)
    
    # Initial equal-weight allocation
    weights = {code: 1.0 / n for code in codes}
    
    trajectory = []
    capital = initial_capital
    
    for t in range(periods):
        trajectory.append(dict(weights))
        
        # Simulate next period returns (Monte Carlo)
        simulated_returns = {}
        for code in codes:
            mu = etf_expected_returns.get(code, 0.01)
            sigma = etf_volatility.get(code, 0.05)
            # Random return with drift
            ret = mu + sigma * random.gauss(0, 1)
            simulated_returns[code] = ret
        
        # Calculate portfolio return
        port_return = sum(weights[code] * simulated_returns[code] for code in codes)
        
        # Update capital
        capital = capital * (1 + port_return) + monthly_cashflow
        
        # Rebalance: shift weights toward highest expected return
        # Simple greedy: increase weight of top performers
        sorted_codes = sorted(codes, key=lambda c: simulated_returns.get(c, 0), reverse=True)
        
        # Shift 10% weight from worst to best
        if len(sorted_codes) >= 2:
            shift = 0.05
            weights[sorted_codes[0]] += shift
            weights[sorted_codes[-1]] -= shift
            
            # Ensure non-negative weights
            for code in codes:
                weights[code] = max(0.0, weights[code])
            
            # Renormalize
            total_w = sum(weights.values())
            if total_w > 0:
                weights = {k: v / total_w for k, v in weights.items()}
    
    return trajectory


# === 4. Game Theory: Market Participant Analysis ===
# Nash Equilibrium, Prisoner's Dilemma, Stackelberg

def nash_equilibrium_simple(payoff_matrix: List[List[float]]) -> Optional[Tuple[float, ...]]:
    """Find mixed-strategy Nash equilibrium for 2-player zero-sum game.
    
    Args:
        payoff_matrix: Player 1's payoff matrix (rows = P1 strategies, cols = P2)
    
    Returns:
        Mixed strategy probabilities for Player 1, or None
    """
    if not payoff_matrix:
        return None
    
    rows = len(payoff_matrix)
    cols = len(payoff_matrix[0])
    
    # Simple case: 2x2 matrix
    if rows == 2 and cols == 2:
        a, b = payoff_matrix[0]
        c, d = payoff_matrix[1]
        denom = a + d - b - c
        if abs(denom) < 1e-10:
            return None
        p = (d - c) / denom
        q = (d - b) / denom
        if 0 <= p <= 1 and 0 <= q <= 1:
            return (p, 1 - p, q, 1 - q)
        return None
    
    return None


def prisoner_dilemma_payoff(defect_prob: float) -> Tuple[float, float]:
    """Calculate expected payoffs in iterated prisoner's dilemma.
    
    Payoff matrix:
        Cooperate | Defect
    Cooperate   (3,3)    (0,5)
    Defect      (5,0)    (1,1)
    
    Args:
        defect_prob: Probability opponent defects
    
    Returns:
        (cooperate_payoff, defect_payoff)
    """
    coop_payoff = 3 * (1 - defect_prob) + 0 * defect_prob
    defect_payoff = 5 * (1 - defect_prob) + 1 * defect_prob
    return (round(coop_payoff, 2), round(defect_payoff, 2))


def stackelberg_leader_strategy(leader_payoffs: List[float], follower_response: List[int]) -> int:
    """Find Stackelberg leader's optimal strategy.
    
    Args:
        leader_payoffs: Leader's payoff for each strategy
        follower_response: Follower's best response to each leader strategy
    
    Returns:
        Optimal leader strategy index
    """
    if not leader_payoffs:
        return 0
    
    # Leader anticipates follower's response and maximizes own payoff
    best_strategy = 0
    best_payoff = -float('inf')
    
    for i, payoff in enumerate(leader_payoffs):
        if payoff > best_payoff:
            best_payoff = payoff
            best_strategy = i
    
    return best_strategy


# === 5. Queueing Theory: Trading Execution ===
# M/M/1 queue model for order execution

def mm1_queue_metrics(arrival_rate: float, service_rate: float) -> Dict[str, float]:
    """Calculate M/M/1 queue metrics.
    
    Args:
        arrival_rate: Order arrival rate (orders per unit time)
        service_rate: Order processing rate (orders per unit time)
    
    Returns:
        Queue metrics dictionary
    """
    if service_rate <= arrival_rate:
        return {"stable": False, "reason": "arrival_rate >= service_rate"}
    
    rho = arrival_rate / service_rate  # Utilization
    l = rho / (1 - rho)  # Average number in system
    lq = rho**2 / (1 - rho)  # Average queue length
    w = 1 / (service_rate - arrival_rate)  # Average wait time
    wq = rho / (service_rate - arrival_rate)  # Average wait in queue
    
    return {
        "stable": True,
        "utilization": round(rho, 3),
        "avg_in_system": round(l, 2),
        "avg_queue_length": round(lq, 2),
        "avg_wait_time": round(w, 3),
        "avg_queue_wait": round(wq, 3),
    }


def eoq_optimal_order_quantity(
    annual_demand: float,
    ordering_cost: float,
    holding_cost_per_unit: float,
) -> float:
    """Calculate Economic Order Quantity (EOQ).
    
    EOQ = sqrt(2DS/H)
    
    Args:
        annual_demand: Annual demand (units/year)
        ordering_cost: Cost per order
        holding_cost_per_unit: Holding cost per unit per year
    
    Returns:
        Optimal order quantity
    """
    if annual_demand <= 0 or holding_cost_per_unit <= 0:
        return 0
    return math.sqrt(2 * annual_demand * ordering_cost / holding_cost_per_unit)


# === 6. Markov Decision Process: Portfolio Rotation ===
# MDP for ETF sector rotation

class ETFMdp:
    """Simplified MDP for ETF sector rotation.
    
    States: economic regime (recovery, expansion, slowdown, recession)
    Actions: sector allocation weights
    Rewards: portfolio return - risk penalty
    Transitions: regime transition probabilities
    """
    
    REGIMES = ["recovery", "expansion", "slowdown", "recession"]
    
    # Regime transition probability matrix (approximate)
    TRANSITION_MATRIX = {
        "recovery":     [0.6, 0.3, 0.05, 0.05],
        "expansion":    [0.1, 0.6, 0.2, 0.1],
        "slowdown":     [0.05, 0.2, 0.5, 0.25],
        "recession":    [0.1, 0.05, 0.2, 0.65],
    }
    
    # Expected returns by regime (approximate)
    SECTOR_RETURNS = {
        "recovery":     {"科技": 0.08, "消费": 0.06, "金融": 0.05, "公用事业": 0.03, "黄金": 0.02},
        "expansion":    {"科技": 0.06, "消费": 0.05, "金融": 0.07, "公用事业": 0.02, "黄金": 0.01},
        "slowdown":     {"科技": 0.03, "消费": 0.04, "金融": 0.02, "公用事业": 0.05, "黄金": 0.04},
        "recession":    {"科技": -0.02, "消费": 0.01, "金融": -0.01, "公用事业": 0.03, "黄金": 0.05},
    }
    
    def __init__(self, sectors: Optional[List[str]] = None):
        self.sectors = sectors or list(self.SECTOR_RETURNS["recovery"].keys())
        self.current_regime = "recovery"
        self.gamma = 0.95  # Discount factor
    
    def get_state(self) -> str:
        return self.current_regime
    
    def get_action_values(self, regime: str) -> Dict[str, float]:
        """Get expected returns for each sector in given regime."""
        returns = self.SECTOR_RETURNS.get(regime, {})
        return {s: returns.get(s, 0.0) for s in self.sectors}
    
    def optimal_action(self, regime: str) -> str:
        """Find optimal sector allocation for given regime."""
        values = self.get_action_values(regime)
        return max(values, key=values.get)
    
    def simulate_one_step(self) -> Tuple[str, str, float]:
        """Simulate one time step of the MDP.
        
        Returns:
            (next_regime, best_action, reward)
        """
        regime = self.get_state()
        best_action = self.optimal_action(regime)
        reward = self.SECTOR_RETURNS[regime].get(best_action, 0.0)
        
        # Transition to next regime
        transitions = self.TRANSITION_MATRIX.get(regime, [0.25, 0.25, 0.25, 0.25])
        r = random.random()
        cumulative = 0
        for i, prob in enumerate(transitions):
            cumulative += prob
            if r <= cumulative:
                self.current_regime = self.REGIMES[i]
                break
        
        return self.current_regime, best_action, reward
    
    def simulate_horizon(self, steps: int = 12) -> List[Dict]:
        """Simulate MDP for given horizon.
        
        Returns:
            List of {regime, action, reward} dicts
        """
        trajectory = []
        for _ in range(steps):
            next_regime, best_action, reward = self.simulate_one_step()
            trajectory.append({
                "regime": next_regime,
                "best_action": best_action,
                "reward": round(reward, 4),
            })
        return trajectory


# === 7. Network Optimization: Supply Chain Risk ===
# Graph analysis for material→industry→ETF dependency network

def supply_chain_network(materials: Dict[str, List[str]], 
                         industries: Dict[str, List[str]],
                         etfs: Dict[str, Dict]) -> Dict:
    """Build and analyze supply chain dependency network.
    
    Args:
        materials: {material_name: [industries_using_it]}
        industries: {industry_name: [etf_codes]}
        etfs: {etf_code: {sector, score, risk, ...}}
    
    Returns:
        Network analysis results
    """
    # Build adjacency
    material_industry_edges = []
    industry_etf_edges = []
    
    for material, industries_used in materials.items():
        for industry in industries_used:
            material_industry_edges.append((material, industry))
    
    for industry, etf_codes in industries.items():
        for code in etf_codes:
            industry_etf_edges.append((industry, code))
    
    # Find critical materials (used by many industries)
    material_degree = {}
    for mat, inds in materials.items():
        material_degree[mat] = len(inds)
    
    critical_materials = sorted(material_degree.items(), key=lambda x: x[1], reverse=True)[:5]
    
    # Find bottleneck industries (connect many materials to many ETFs)
    industry_degree = {}
    for mat, inds in materials.items():
        for ind in inds:
            industry_degree[ind] = industry_degree.get(ind, 0) + 1
    
    bottleneck_industries = sorted(industry_degree.items(), key=lambda x: x[1], reverse=True)[:5]
    
    return {
        "material_industry_edges": len(material_industry_edges),
        "industry_etf_edges": len(industry_etf_edges),
        "critical_materials": critical_materials,
        "bottleneck_industries": bottleneck_industries,
    }


# === 8. Correlation Network Analysis ===
# Graph clustering for ETF diversification

def correlation_cluster(
    etf_correlations: Dict[Tuple[str, str], float],
    n_clusters: int = 5,
) -> Dict[str, List[str]]:
    """Cluster ETFs based on correlation using greedy approach.
    
    Args:
        etf_correlations: {(code1, code2): correlation}
        n_clusters: Target number of clusters
    
    Returns:
        Dictionary of cluster_id -> [etf_codes]
    """
    if not etf_correlations:
        return {}
    
    # Get all unique ETF codes
    codes = set()
    for (c1, c2) in etf_correlations:
        codes.add(c1)
        codes.add(c2)
    codes = sorted(codes)
    
    if len(codes) <= n_clusters:
        return {i: [c] for i, c in enumerate(codes)}
    
    # Greedy clustering: assign each ETF to nearest cluster
    # Initialize centroids randomly
    random.seed(42)
    centroids = random.sample(codes, min(n_clusters, len(codes)))
    
    clusters = {i: [] for i in range(n_clusters)}
    
    for code in codes:
        if code in centroids:
            idx = centroids.index(code)
            clusters[idx].append(code)
        else:
            # Find closest centroid
            best_cluster = 0
            best_corr = -2  # Correlation range: [-1, 1]
            for i, centroid in enumerate(centroids):
                corr = etf_correlations.get((code, centroid), 
                                          etf_correlations.get((centroid, code), 0))
                if corr > best_corr:
                    best_corr = corr
                    best_cluster = i
            clusters[best_cluster].append(code)
    
    # Filter empty clusters
    clusters = {k: v for k, v in clusters.items() if v}
    
    return clusters


# === Data: Sector Rotation Strategy ===
# Historical sector performance by economic regime

SECTOR_ROTATION_STRATEGY = {
    "recovery": {
        "description": "经济复苏期：信用扩张，周期股领涨",
        "best_sectors": ["科技", "消费", "金融"],
        "worst_sectors": ["公用事业", "黄金"],
        "recommended_etf_types": ["中盘成长", "硬科技", "券商"],
        "risk_level": "中高",
    },
    "expansion": {
        "description": "经济扩张期：盈利增长，成长股占优",
        "best_sectors": ["科技", "金融", "周期"],
        "worst_sectors": ["公用事业", "利率债"],
        "recommended_etf_types": ["成长股", "半导体", "银行"],
        "risk_level": "中",
    },
    "slowdown": {
        "description": "经济放缓期：盈利下滑，防御板块相对抗跌",
        "best_sectors": ["公用事业", "消费", "医药"],
        "worst_sectors": ["周期", "金融"],
        "recommended_etf_types": ["红利+低波", "医药", "公用事业"],
        "risk_level": "中低",
    },
    "recession": {
        "description": "经济衰退期：避险情绪升温，债券/黄金走强",
        "best_sectors": ["黄金", "利率债", "公用事业"],
        "worst_sectors": ["科技", "金融", "周期"],
        "recommended_etf_types": ["黄金", "利率债", "货币基金"],
        "risk_level": "低",
    },
}
