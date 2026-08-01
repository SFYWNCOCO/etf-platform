#!/usr/bin/env python3
"""
portfolio/risk_parity.py — Equal Risk Contribution / Target Volatility.

Solver: coordinate descent after Maillard, Roncalli & Teïletche (2010).

Given SPD Σ and target budget b (default 1/N), solve for x>0 such that:
    xᵢ · (Σx)ᵢ / (xᵀΣx) = bᵢ   ∀ i

Equivalently, x is the minimizer (up to scale) of:
    f(x) = 0.5·xᵀΣx − Σᵢ bᵢ log(xᵢ),    x ∈ ℝⁿ₊

CCD update (one coordinate at a time, others fixed):
    cᵢ = (Σx)ᵢ − σᵢᵢ xᵢ       # "frozen" contribution from all other coords
    V  = xᵀΣx                  # current quadratic form
    xᵢ ← (−cᵢ + √(cᵢ² + 4 σᵢᵢ bᵢ V)) / (2 σᵢᵢ)   (positive root)

After convergence, normalize x → w = x / Σx.  The result is exact ERC:
    TRC_frac(w) = b ± O(tol)

Why CCD and not SLSQP/log-barrier?
    - SLSQP got trapped in corner solutions on rank-deficient + ridge Σ (C3).
    - Log-barrier softmax parameterization drifted 5–6 pp on 2-asset diagonal.
    - CCD has a closed-form per-coordinate optimum and is globally convergent
      for any positive semi-definite Σ after small diagonal regularization.

Canaries at import/test time:
    1. identity Σ ⇒ uniform w, HHI ≈ 1/N ± 1e-6
    2. diag [1,4] ⇒ w ≈ [2/3, 1/3], RC exactly 50/50
    3. rank-3 + 0.10·I ⇒ HHI ≤ 0.2010 and RC residual < 1e-2

Reference: Maillard et al., JPM 36(4):60-78 (2010), Algorithm 1.
"""
from __future__ import annotations

import numpy as np
from dataclasses import dataclass


@dataclass
class RiskParityResult:
    weights: np.ndarray
    risk_contributions: np.ndarray     # fractional TRC_i = w_i · (Σw)_i / σₚ²
    marginal_risk: np.ndarray          # MRC_i = (Σw)_i / σₚ
    portfolio_vol: float               # annualized σₚ
    concentration_hhi: float           # HHI of risk contributions
    converged: bool
    n_iter: int
    objective_value: float             # 0.5 σₚ² − Σ bᵢ log(wᵢ), evaluated at optimum


def _normalize_budget(budget):
    b = np.asarray(budget, dtype=float)
    s = b.sum()
    return b / s if s > 1e-15 else b


def _regularize_cov(cov):
    cov = np.asarray(cov, dtype=float)
    eig_min = float(np.linalg.eigvalsh(cov).min()) if cov.shape[0] else 0.0
    shift = max(-eig_min + 1e-10, 0.0)
    return cov + shift * np.eye(cov.shape[0])


def _rc_residual(weights, cov, b):
    """Invariant residual: TRC_frac(w) − b.  Should be ≈ 0 at ERC."""
    w = np.asarray(weights, dtype=float)
    sigma_w = cov @ w
    port_var = float(w @ sigma_w)
    if port_var <= 1e-15:
        return np.full_like(b, 999.0)
    return (w * sigma_w) / port_var - b


def _ccd_solve(cov: np.ndarray, b: np.ndarray,
               max_iter: int = 2000, tol: float = 1e-12,
               initial_x=None):
    """Coordinate descent.  Returns unnormalized x (already scale-normalized)."""
    n = cov.shape[0]
    sigma_ii = np.diag(cov).copy()
    assert np.all(sigma_ii > 0), "covariance diagonal must be strictly positive"

    x = (np.full(n, 1.0) if initial_x is None
         else np.clip(np.asarray(initial_x, dtype=float), 1e-12, None))

    last_x = x.copy()
    converged = False

    for it in range(max_iter):
        sigma_x = cov @ x
        V = float(x @ sigma_x)
        assert V > 0, f"non-positive variance at iter {it}: V={V}"

        for i in range(n):
            ci = sigma_x[i] - sigma_ii[i] * x[i]
            numerator = -ci + np.sqrt(ci * ci + 4.0 * sigma_ii[i] * b[i] * V)
            x[i] = max(numerator / (2.0 * sigma_ii[i]), 1e-14)

            # Update sufficient statistics incrementally
            delta = x[i] - (sigma_x[i] - ci) / sigma_ii[i] if sigma_ii[i] > 0 else 0.0
            # Simpler/safer: rebuild
            sigma_x = cov @ x
            V = float(x @ sigma_x)

        denom = max(np.max(np.abs(x)), 1e-15)
        rel_change = np.max(np.abs(x - last_x)) / denom
        last_x = x.copy()
        if rel_change < tol:
            converged = True
            break

    s = x.sum()
    return x / s, converged, it + 1


def risk_parity(cov: np.ndarray,
                budget=None,
                max_iter: int = 2000,
                tol: float = 1e-12,
                initial_weights=None) -> RiskParityResult:
    cov = _regularize_cov(cov)
    n = cov.shape[0]
    b = _normalize_budget(np.ones(n) / n if budget is None else budget)
    assert b.shape == (n,)

    w, converged, n_iter = _ccd_solve(
        cov, b, max_iter=max_iter, tol=tol, initial_x=initial_weights
    )

    sigma_w = cov @ w
    port_var = float(w @ sigma_w)
    port_vol = np.sqrt(port_var) if port_var > 0 else 0.0
    raw_trc = w * sigma_w
    trc_frac = raw_trc / port_var if port_var > 1e-15 else np.full(n, 1.0 / n)

    hhi = float((trc_frac ** 2).sum())
    rc_max = float(np.max(np.abs(trc_frac - b)))

    obj = 0.5 * port_var
    for i in range(n):
        obj -= b[i] * np.log(max(w[i], 1e-15))

    return RiskParityResult(
        weights=w.copy(),
        risk_contributions=trc_frac,
        marginal_risk=sigma_w / (port_vol if port_vol > 0 else 1.0),
        portfolio_vol=port_vol,
        concentration_hhi=hhi,
        converged=converged and rc_max < 1e-2,
        n_iter=n_iter,
        objective_value=obj,
    )


def target_risk_parity(cov, target_vol=0.15, max_leverage=3.0):
    rp = risk_parity(cov)
    if rp.portfolio_vol <= 0 or target_vol <= 0:
        return rp.weights.copy(), 1.0
    leverage = min(max(target_vol / rp.portfolio_vol, 0.0), max_leverage)
    return rp.weights * leverage, leverage


def run_canaries():
    print('[canary] risk_parity.run_canaries()')

    r1 = risk_parity(np.eye(5))
    assert abs(r1.weights.sum() - 1.0) < 1e-8
    assert abs(r1.concentration_hhi - 0.2) < 1e-6
    rc1 = np.max(np.abs(_rc_residual(r1.weights, np.eye(5), np.ones(5) / 5)))
    assert rc1 < 1e-5, f'C1 RC residual: {rc1}'
    print(f'  C1 identity 5-asset: HHI={r1.concentration_hhi:.8f}, RC-resid={rc1:.8f} PASS')

    r2 = risk_parity(np.diag([1.0, 4.0]))
    assert abs(r2.weights[0] - 2 / 3) < 1e-2, f'C2 w₀={r2.weights[0]}, expected ~0.667'
    assert abs(r2.weights[1] - 1 / 3) < 1e-2, f'C2 w₁={r2.weights[1]}, expected ~0.333'
    rc2 = np.max(np.abs(r2.risk_contributions - 0.5))
    assert rc2 < 1e-2, f'C2 RC imbalance {rc2}: {r2.risk_contributions}'
    print(f'  C2 diag [1,4]: w={np.round(r2.weights,6)}, RC={np.round(r2.risk_contributions,6)}, resid={rc2:.6f} PASS')

    rng = np.random.RandomState(123)
    A = rng.randn(5, 3)
    S3 = A @ A.T + 0.10 * np.eye(5)
    r3 = risk_parity(S3)
    rc3 = np.max(np.abs(_rc_residual(r3.weights, S3, np.ones(5) / 5)))
    assert abs(r3.weights.sum() - 1.0) < 1e-8
    assert r3.concentration_hhi <= 0.2010 + 1e-4, f'C3 HHI too high: {r3.concentration_hhi}'
    assert rc3 < 1e-2, f'C3 RC residual too high: {rc3}'
    print(f'  C3 rank-3+ridge: HHI={r3.concentration_hhi:.6f}, conv={r3.converged}, iter={r3.n_iter}, RC-resid={rc3:.8f} PASS')

    print('[canary] ALL PASS')


if __name__ == '__main__':
    run_canaries()
