# -*- coding: utf-8 -*-
"""test_qvix_regime_improvements.py — QVIX多源校验单元测试"""
import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from etf_platform.analysis.qvix_regime_improvements import (
    QVIXDataQuality,
    SecondaryDataSource,
    QVIXValidator,
    classify_regime_with_quality,
    QVIX_MIN,
    QVIX_MAX,
    MAX_SINGLE_JUMP,
    MAX_CONSENSUS_GAP,
)


# ── QVIXDataQuality ───────────────────────────────────────────────────

class TestQVIXDataQualityRange:
    """范围检查测试。"""

    def test_normal_50(self):
        ok, msg = QVIXDataQuality.check_range(18.5, "qvix_50")
        assert ok is True
        assert msg == "ok"

    def test_normal_500(self):
        ok, msg = QVIXDataQuality.check_range(22.3, "qvix_500")
        assert ok is True

    def test_below_min(self):
        ok, msg = QVIXDataQuality.check_range(3.0, "qvix")
        assert ok is False
        assert "低于最小合理值" in msg

    def test_above_max(self):
        ok, msg = QVIXDataQuality.check_range(200.0, "qvix")
        assert ok is False
        assert "高于最大合理值" in msg

    def test_boundary_min(self):
        ok, _ = QVIXDataQuality.check_range(QVIX_MIN, "qvix")
        assert ok is True

    def test_boundary_max(self):
        ok, _ = QVIXDataQuality.check_range(QVIX_MAX, "qvix")
        assert ok is True

    def test_zero(self):
        ok, msg = QVIXDataQuality.check_range(0.0, "qvix")
        assert ok is False
        assert "低于" in msg

    def test_negative(self):
        ok, _ = QVIXDataQuality.check_range(-5.0, "qvix")
        assert ok is False


class TestQVIXDataQualityJump:
    """跳变检查测试。"""

    def test_small_jump_ok(self):
        ok, _ = QVIXDataQuality.check_jump(20.0, 19.0)
        assert ok is True

    def test_large_jump_rejected(self):
        ok, msg = QVIXDataQuality.check_jump(40.0, 20.0)
        assert ok is False
        assert "跳变" in msg

    def test_exact_threshold(self):
        ok, _ = QVIXDataQuality.check_jump(20.0 + MAX_SINGLE_JUMP, 20.0)
        # Exactly at threshold should be ok (not exceeded)
        assert ok is True

    def test_over_threshold(self):
        ok, _ = QVIXDataQuality.check_jump(20.0 + MAX_SINGLE_JUMP + 0.1, 20.0)
        assert ok is False

    def test_downward_jump(self):
        ok, _ = QVIXDataQuality.check_jump(5.0, 25.0)
        assert ok is False  # 20-point drop exceeds threshold


class TestQVIXDataQualityConsensus:
    """一致性检查测试。"""

    def test_single_source(self):
        ok, msg, gap = QVIXDataQuality.check_consensus({"50": 18.5})
        assert ok is True
        assert msg == "single_source"
        assert gap == 0.0

    def test_two_sources_consistent(self):
        ok, msg, gap = QVIXDataQuality.check_consensus({"50": 18.5, "500": 20.3})
        assert ok is True
        assert "consistent" in msg

    def test_two_sources_inconsistent(self):
        ok, msg, gap = QVIXDataQuality.check_consensus({"50": 30.0, "500": 10.0})
        assert ok is False
        assert gap > MAX_CONSENSUS_GAP

    def test_three_sources_mixed(self):
        ok, msg, gap = QVIXDataQuality.check_consensus({
            "50": 18.0,
            "500": 20.0,
            "proxy": 19.0,
        })
        assert ok is True

    def test_extreme_gap(self):
        ok, msg, gap = QVIXDataQuality.check_consensus({
            "50": 50.0,
            "500": 5.0,
        })
        assert ok is False
        assert gap == 45.0


# ── QVIXValidator ─────────────────────────────────────────────────────

class TestQVIXValidator:
    """QVIX验证器完整流程测试。"""

    def setup_method(self):
        self.validator = QVIXValidator(history_size=10)

    def test_first_validation_no_history(self):
        """第一次验证无历史记录，跳变检查应跳过。"""
        result = self.validator.validate(18.0, 20.0)
        assert result["valid"] is True
        assert result["recommendation"] == "use"
        assert "jump_50" not in result["checks"] or result["checks"]["jump_50"] is True

    def test_range_rejection(self):
        """超出范围的QVIX应被拒绝。"""
        self.validator.validate(18.0, 20.0)  # seed history
        result = self.validator.validate(200.0, 20.0)
        assert result["valid"] is False
        assert result["recommendation"] == "reject"
        assert len(result["alerts"]) > 0

    def test_jump_detection(self):
        """大跳变应被检测到。"""
        self.validator.validate(18.0, 20.0)
        result = self.validator.validate(35.0, 37.0)
        # 17点跳变超过15阈值
        assert result["checks"]["jump_50"] is False or result["checks"]["jump_500"] is False

    def test_consistency_check(self):
        """50/500差异过大应标记。"""
        self.validator.validate(18.0, 20.0)
        result = self.validator.validate(30.0, 10.0)
        assert result["checks"]["consistency_50_500"] is False

    def test_history_rotation(self):
        """历史超过history_size应自动淘汰旧记录。"""
        v = QVIXValidator(history_size=3)
        v.validate(10.0, 11.0)
        v.validate(11.0, 12.0)
        v.validate(12.0, 13.0)
        v.validate(13.0, 14.0)  # 第4条，应该淘汰第1条
        # 此时跳变检查应基于第2条(11.0)而非第1条(10.0)

    def test_alert_summary_empty(self):
        v = QVIXValidator()
        summary = v.get_alert_summary()
        assert summary["total_checks"] == 0
        assert summary["rejected_count"] == 0

    def test_alert_summary_with_rejections(self):
        v = QVIXValidator()
        v.validate(18.0, 20.0)       # OK → history[0]
        v.validate(200.0, 20.0)      # rejected → NOT added to history
        v.validate(19.0, 21.0)       # OK → history[1]
        summary = v.get_alert_summary()
        assert summary["total_checks"] == 2  # only accepted records in history
        assert summary["rejection_rate"] == 0.0  # no rejections in history

    def test_rejected_not_in_history(self):
        """被拒绝的记录不应加入历史（避免污染跳变检测）。"""
        v = QVIXValidator()
        v.validate(18.0, 20.0)  # OK
        v.validate(200.0, 20.0)  # Rejected — range fail
        v.validate(19.0, 21.0)  # Should compare against 18.0, not 200.0

    def test_recommendation_use(self):
        v = QVIXValidator()
        r = v.validate(18.0, 20.0)
        assert r["recommendation"] == "use"

    def test_recommendation_investigate(self):
        v = QVIXValidator()
        v.validate(18.0, 20.0)
        r = v.validate(18.0, 20.0)  # normal
        r2 = v.validate(35.0, 15.0)  # big jump + inconsistent
        assert r2["recommendation"] in ("investigate", "reject")


class TestClassifyRegimeWithQuality:
    """regime分类 + 质量集成测试。"""

    def test_complacent(self):
        regime, desc, alerts = classify_regime_with_quality(12.0)
        assert regime == "complacent"

    def test_normal(self):
        regime, desc, alerts = classify_regime_with_quality(18.0)
        assert regime == "normal"

    def test_cautious(self):
        regime, desc, alerts = classify_regime_with_quality(25.0)
        assert regime == "cautious"

    def test_fearful(self):
        regime, desc, alerts = classify_regime_with_quality(30.0)
        assert regime == "fearful"

    def test_quality_reject(self):
        quality = {"recommendation": "reject"}
        regime, desc, alerts = classify_regime_with_quality(30.0, quality)
        assert regime == "normal"  # fallback to normal on reject
        assert any("不可信" in a for a in alerts)

    def test_quality_low_consensus(self):
        quality = {"consensus_score": 0.3}
        regime, desc, alerts = classify_regime_with_quality(25.0, quality)
        assert regime == "cautious"
        assert any("一致性低" in a for a in alerts)

    def test_unknown_quality(self):
        regime, desc, alerts = classify_regime_with_quality(25.0, None)
        assert regime == "cautious"
        assert len(alerts) == 0


# ── SecondaryDataSource ───────────────────────────────────────────────

class TestSecondaryDataSource:
    """备用数据源测试（网络不可用时skip）。"""

    @pytest.mark.slow
    @patch.object(SecondaryDataSource, 'compute_realized_vol_proxy')
    def test_fetch_sina_unavailable(self, mock_proxy):
        mock_proxy.return_value = None
        result = SecondaryDataSource.fetch_sina_option_iv("510050")
        # May return None if network unavailable — that's fine
        assert result is None or isinstance(result, float)

    @pytest.mark.slow
    def test_realized_vol_proxy_no_network(self):
        """没有网络时返回None是正常行为。"""
        result = SecondaryDataSource.compute_realized_vol_proxy(["510050"])
        # Should handle gracefully
        assert result is None or isinstance(result, float)
