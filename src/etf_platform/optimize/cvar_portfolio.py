"""optimize/cvar_portfolio.py — CVaR portfolio optimization.
Based on: Appiah et al. (2026) arXiv:2606.26625.
Methods: gaussian (fast), historical (accurate), student-t (heavy-tail).
"""
import math
from statistics import NormalDist

PHI = NormalDist()
PHI_PDF = lambda x: math.exp(-x*x/2) / math.sqrt(2*math.pi)

def gaussian_cvar(mu, sigma, alpha=0.95):
    z = PHI.inv_cdf(alpha)
    return mu - sigma * PHI_PDF(z) / (1 - alpha)

def gaussian_cvar_gradient(w, means, cov, alpha=0.95):
    n = len(w)
    var_p = sum(w[i]*w[j]*cov[i][j] for i in range(n) for j in range(n))
    sigma_p = math.sqrt(max(var_p, 1e-12))
    z = PHI.inv_cdf(alpha)
    k = PHI_PDF(z) / (1 - alpha)
    grad = []
    for i in range(n):
        ds = sum(w[j]*cov[i][j] for j in range(n)) / sigma_p if sigma_p > 0 else 0
        grad.append(-means[i] - k * ds)
    return grad

def optimize_gaussian(means, cov, alpha=0.95, lr=0.01, max_iter=500, tol=1e-6):
    n = len(means)
    w = [1.0/n] * n
    for step in range(max_iter):
        g = gaussian_cvar_gradient(w, means, cov, alpha)
        w2 = [max(w[i] - lr*g[i], 0.0) for i in range(n)]
        s = sum(w2)
        w = [x/s for x in w2] if s > 0 else [1.0/n]*n
        if sum(abs(w[i]-w2[i]) for i in range(n)) < tol:
            break
    mu_p = sum(w[i]*means[i] for i in range(n))
    var_p = sum(w[i]*w[j]*cov[i][j] for i in range(n) for j in range(n))
    sigma_p = math.sqrt(max(var_p, 1e-12))
    return [round(x,6) for x in w], dict(cvar=round(gaussian_cvar(mu_p,sigma_p,alpha),6),
        vol=round(sigma_p,6), ret=round(mu_p,6), alpha=alpha, method='gaussian')

def historical_cvar(w, scenarios, alpha=0.95):
    pret = sorted(sum(w[i]*s[i] for i in range(len(w))) for s in scenarios)
    k = max(1, int(len(pret)*(1-alpha)))
    return sum(pret[:k]) / k

def optimize_historical(scenarios, alpha=0.95, lr=0.01, max_iter=500):
    n = len(scenarios[0]); m = len(scenarios)
    k = max(1, int(m*(1-alpha)))
    w = [1.0/n]*n
    for step in range(max_iter):
        pret = [sum(w[j]*s[j] for j in range(n)) for s in scenarios]
        thr = sorted(pret)[k-1]
        sg = [0.0]*n; tc = 0
        for idx, p in enumerate(pret):
            if p <= thr:
                tc += 1
                for j in range(n): sg[j] += scenarios[idx][j]
        sg = [-x/max(tc,1) for x in sg]
        w2 = [max(w[j] - lr*sg[j], 0.0) for j in range(n)]
        s = sum(w2)
        w = [x/s for x in w2] if s > 0 else [1.0/n]*n
    return [round(x,6) for x in w], dict(cvar=round(historical_cvar(w,scenarios,alpha),6),
        alpha=alpha, method='historical', scenarios=m)

def student_t_cvar(mu, sigma, nu=5, alpha=0.95):
    z = PHI.inv_cdf(alpha)
    k = PHI_PDF(z) / (1 - alpha)
    if nu <= 30: k *= (1 + 4.0/max(nu-2, 1))
    return mu - sigma * k
