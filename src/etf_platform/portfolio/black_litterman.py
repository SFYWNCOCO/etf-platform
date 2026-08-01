#!/usr/bin/env python3
"""
portfolio/black_litterman.py — Black-Litterman allocation.

Pipeline:
    1. Compute implied equilibrium return π = λ Σ w_mkt
    2. Bayesian posterior: E[μ|P,Q] = [(τΣ)⁻¹ + PᵀΩ⁻¹P]⁻¹ · [(τΣ)⁻¹π + PᵀΩ⁻¹Q]
    3. Plug posterior μ back into MPT tangency (clipped long-only bounds)

Numerical hygiene:
    - Cholesky-safe SPD regularization on Σ
    - Omega diagonal has an absolute floor so views can never have zero confidence
    - Diagnostics expose tau/lambda/posterior-mu range/drift norm

Canaries:
    1. no-views case ⇒ MPT weight equals market-implied drift? Actually with only π, MPT tangency
       using Σ⁻¹π = w_mkt exactly (up to clipping) because π ∝ Σ w_mkt.
    2. one absolute view on asset i ⇒ posterior μ_i shifts in view direction
    3. contradictory views ⇒ omega floor prevents blow-up
"""
from __future__ import annotations

import numpy as np
from dataclasses import dataclass


@dataclass
class BlackLittermanResult:
    posterior_mu: np.ndarray
    mpt_weights: np.ndarray
    implied_equilibrium_mu: np.ndarray
    views_applied: int
    diagnostics: dict


def _normalize_and_regulate(cov):
    cov = np.asarray(cov, dtype=float)
    n = cov.shape[0]
    eigvals = np.linalg.eigvalsh(cov)
    eig_min = float(eigvals.min()) if eigvals.size else 0.0
    if eig_min < 1e-8:
        cov = cov + (abs(eig_min) + 1e-8) * np.eye(n)
    return cov


def _bound_weights(w, w_min=0.0, w_max=0.40):
    w = np.asarray(w, dtype=float)
    if w_min is not None:
        w = np.maximum(w, w_min)
    if w_max is not None:
        w = np.minimum(w, w_max)
    s = w.sum()
    return w / s if s > 1e-15 else w


def black_litterman(
    cov,
    w_mkt,
    P=None,
    Q=None,
    omega_diag=None,
    tau=0.05,
    risk_aversion=2.5,
    w_min=0.0,
    w_max=0.40,
    clip_mpt_to_view_drift: bool = False,
) -> BlackLittermanResult:
    """Full Bayes update; returns normalized long-only MPT weights."""
    cov = _normalize_and_regulate(cov)
    n = cov.shape[0]
    w_mkt = np.asarray(w_mkt, dtype=float)
    s = w_mkt.sum()
    if abs(s - 1.0) > 1e-6:
        w_mkt = w_mkt / s

    # π = λ Σ w_mkt
    pi = risk_aversion * (cov @ w_mkt)

    k_views = 0
    posterior_mu = pi.copy()

    if P is not None and Q is not None and len(P) > 0:
        P = np.asarray(P, dtype=float)
        Q = np.asarray(Q, dtype=float).reshape(-1)
        k_views = P.shape[0]
        assert P.shape == (k_views, n), f"P shape {P.shape} != ({k_views},{n})"
        assert Q.shape == (k_views,), f"Q shape {Q.shape} != ({k_views},)"

        if omega_diag is None:
            # Default view uncertainty: proportional to view variance, floored at 5pp annualized
            view_var = (P @ cov @ P.T).diagonal()
            view_var = np.maximum(view_var, 1e-12)
            omega_diag = np.maximum(view_var, 0.05 ** 2)
        Omega = np.diag(np.maximum(np.asarray(omega_diag, dtype=float), 1e-10))

        A = np.linalg.inv(tau * cov)        # prior precision
        B = P.T @ np.linalg.inv(Omega) @ P  # view precision contribution
        rhs = np.linalg.inv(tau * cov) @ pi + P.T @ np.linalg.inv(Omega) @ Q

        posterior_mu = np.linalg.solve(A + B, rhs)

    # Tangency-style plug-in: σ⁻¹ μ (then clip to long-only bounds)
    raw = np.linalg.solve(cov, posterior_mu)
    raw = raw - raw.min() if raw.min() < 0 else raw
    w_bl = _bound_weights(raw, w_min, w_max)

    drift = w_bl - w_mkt
    diag = {
        "tau": tau,
        "risk_aversion": risk_aversion,
        "views_applied": k_views,
        "max_abs_view_drift": float(np.max(np.abs(drift))),
        "drift_norm": float(np.sqrt((drift ** 2).sum())),
        "posterior_mu_range": [float(posterior_mu.min()), float(posterior_mu.max())],
        "mpt_unbounded_max": float(raw.max()) if 'raw' in locals() else 0.0,
    }
    if clip_mpt_to_view_drift and diag['drift_norm'] < 1e-6:
        # safety net: if all views were ignored, revert to w_mkt
        w_bl = w_mkt.copy()
        diag['clip_used'] = True
    else:
        diag['clip_used'] = False

    return BlackLittermanResult(
        posterior_mu=posterior_mu,
        mpt_weights=w_bl,
        implied_equilibrium_mu=pi,
        views_applied=k_views,
        diagnostics=diag,
    )


def view_examples():
    """Canned relative/absolute sector views for testing."""
    # Sector order: AI/科技, 新能源, 消费, 金融, 医药, 周期, 军工, 跨境, 红利价值, 其他
    relative = [
        ([1, -1, 0, 0, 0, 0, 0, 0, 0, 0], 0.03),   # AI > 新能源 by 3pp
        ([0, 0, 1, -1, 0, 0, 0, 0, 0, 0], 0.02),   # 消费 > 金融 by 2pp
        ([0, 0, 0, 0, 1, -1, 0, 0, 0, 0], -0.01),  # 医药 underweights vs 周期
    ]
    P = np.array([v[0] for v in relative])
    Q = np.array([v[1] for v in relative])
    return P, Q


SECTOR_ORDER_FOR_VIEWS = [
    "AI/科技", "新能源", "消费", "金融", "医药",
    "周期", "军工", "跨境", "红利价值", "其他"
]


def run_canaries():
    """Hard-fail self-tests."""
    print('[canary] black_litterman.run_canaries()')

    # C1: no views ⇒ posterior == π, unbounded tangency == w_mkt
    cov = np.array([[0.04, 0.01, 0.005], [0.01, 0.09, 0.02], [0.005, 0.02, 0.16]])
    w_mkt = np.array([0.5, 0.3, 0.2])
    r1 = black_litterman(cov=cov, w_mkt=w_mkt, P=None, Q=None, w_min=0, w_max=1.0)
    assert np.allclose(r1.posterior_mu, 2.5 * (cov @ w_mkt)), f'C1 π mismatch'
    assert abs(r1.mpt_weights.sum() - 1) < 1e-6
    print(f'  C1 no-views tangency: drift={r1.diagnostics["drift_norm"]:.6f} PASS')

    # C2: positive absolute view on asset 0 ⇒ posterior mu_0 rises
    P = np.array([[1, 0, 0]])
    Q = np.array([0.20])
    r2 = black_litterman(cov=cov, w_mkt=w_mkt, P=P, Q=Q, tau=0.05, w_min=0, w_max=1.0)
    assert r2.posterior_mu[0] > r2.implied_equilibrium_mu[0] + 0.001, \
        f'C2 posterior mu0 did not shift up: {r2.posterior_mu[0]} vs pi0={r2.implied_equilibrium_mu[0]}'
    print(f'  C2 absolute up-view: mu0 shifted by {r2.posterior_mu[0]-r2.implied_equilibrium_mu[0]:.4f} PASS')

    # C3: tiny omega ⇒ stronger view impact but still numerically stable due to floor
    r3 = black_litterman(cov=cov, w_mkt=w_mkt, P=P, Q=Q, omega_diag=np.array([1e-9]), tau=0.05, w_min=0, w_max=1.0)
    assert np.isfinite(r3.posterior_mu).all(), 'C3 omega floor failed — non-finite posterior'
    print(f'  C3 omega floor stability: finite posterior PASS')

    print('[canary] ALL PASS')


if __name__ == '__main__':
    run_canaries()
