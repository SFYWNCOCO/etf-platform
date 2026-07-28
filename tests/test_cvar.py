"""test_cvar.py — CVaR 优化器单元测试"""
import math
import pytest

from etf_platform.optimize.cvar_portfolio import (
    PHI_PDF, gaussian_cvar, gaussian_cvar_gradient,
    optimize_gaussian, historical_cvar, optimize_historical,
    student_t_cvar,
)


@pytest.mark.unit
class TestPhiPdf:
    def test_returns_float(self):
        assert isinstance(PHI_PDF(0.0), float)

    def test_positive(self):
        # 概率密度函数返回正值
        for x in [-3.0, -1.0, 0.0, 1.0, 3.0]:
            assert PHI_PDF(x) > 0

    def test_peak_at_zero(self):
        # 标准正态分布在 x=0 处取最大值 ~0.3989
        assert abs(PHI_PDF(0.0) - 1/math.sqrt(2*math.pi)) < 1e-9


@pytest.mark.unit
class TestGaussianCvar:
    def test_returns_float(self):
        cvar = gaussian_cvar(0.0, 0.1, alpha=0.95)
        assert isinstance(cvar, float)

    def test_negative_for_zero_mean(self):
        # 零均值正态分布的 CVaR 应为负
        assert gaussian_cvar(0.0, 0.1, alpha=0.95) < 0


@pytest.mark.unit
class TestOptimizeGaussian:
    def test_weights_sum_to_one(self):
        means = [0.01, 0.02, 0.015]
        cov = [[0.04, 0.01, 0.005], [0.01, 0.09, 0.01], [0.005, 0.01, 0.04]]
        w, info = optimize_gaussian(means, cov, alpha=0.95, max_iter=100)
        assert abs(sum(w) - 1.0) < 1e-4

    def test_weights_non_negative(self):
        means = [0.01, 0.02, -0.01]
        cov = [[0.04, 0.01, 0.005], [0.01, 0.09, 0.01], [0.005, 0.01, 0.04]]
        w, _ = optimize_gaussian(means, cov, alpha=0.95, max_iter=100)
        for weight in w:
            assert weight >= 0

    def test_convergence_tolerance(self):
        # tol 较大时应更快收敛,结果不应显著不同
        means = [0.01, 0.02, 0.015]
        cov = [[0.04, 0.01, 0.005], [0.01, 0.09, 0.01], [0.005, 0.01, 0.04]]
        w1, _ = optimize_gaussian(means, cov, alpha=0.95, max_iter=500, tol=1e-6)
        w2, _ = optimize_gaussian(means, cov, alpha=0.95, max_iter=500, tol=1e-3)
        for a, b in zip(w1, w2):
            assert abs(a - b) < 0.1

    def test_returns_info_dict(self):
        means = [0.01, 0.02]
        cov = [[0.04, 0.01], [0.01, 0.09]]
        w, info = optimize_gaussian(means, cov, alpha=0.95)
        assert "cvar" in info
        assert "vol" in info
        assert "ret" in info
        assert info["method"] == "gaussian"


@pytest.mark.unit
class TestOptimizeHistorical:
    def test_weights_sum_to_one(self):
        scenarios = [[0.01, 0.02], [0.0, 0.01], [-0.01, 0.03], [0.02, -0.01]]
        w, _ = optimize_historical(scenarios, alpha=0.95, max_iter=100)
        assert abs(sum(w) - 1.0) < 1e-4

    def test_convergence(self):
        scenarios = [[0.01, 0.02], [0.0, 0.01], [-0.01, 0.03], [0.02, -0.01]]
        # 增大 tol 仍应得到有效权重
        w, _ = optimize_historical(scenarios, alpha=0.95, max_iter=500, tol=1e-3)
        assert len(w) == 2
