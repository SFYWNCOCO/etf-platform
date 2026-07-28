# -*- coding: utf-8 -*-
"""test_regime_transition_improvements.py — 状态转换回测验证单元测试"""
import json
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from etf_platform.decision.regime_transition_improvements import (
    TransitionRecord,
    VerificationRecord,
    TransitionBacktester,
    regime_to_score,
    direction_from_regimes,
    compute_brier_score,
    compute_log_loss,
    TRANSITION_LOG,
    TRANSITION_VERIFY,
    asdict,
)


# ── 工具函数测试 ──────────────────────────────────────────────────────

class TestRegimeHelpers:
    """regime方向判断测试。"""

    def test_same_regime_stay(self):
        assert direction_from_regimes("normal", "normal") == "stay"
        assert direction_from_regimes("fearful", "fearful") == "stay"

    def test_improve_fearful_to_cautious(self):
        assert direction_from_regimes("fearful", "cautious") == "improve"

    def test_improve_normal_to_complacent(self):
        assert direction_from_regimes("normal", "complacent") == "improve"

    def test_worsen_complacent_to_normal(self):
        assert direction_from_regimes("complacent", "normal") == "worsen"

    def test_worsen_cautious_to_fearful(self):
        assert direction_from_regimes("cautious", "fearful") == "worsen"

    def test_jump_two_levels_improve(self):
        assert direction_from_regimes("fearful", "normal") == "improve"

    def test_jump_two_levels_worsen(self):
        assert direction_from_regimes("normal", "fearful") == "worsen"

    def test_regime_to_score(self):
        assert regime_to_score("complacent") == 0
        assert regime_to_score("normal") == 1
        assert regime_to_score("cautious") == 2
        assert regime_to_score("fearful") == 3
        assert regime_to_score("unknown") == 1  # default


class TestBrierAndLogLoss:
    """Brier score和log loss计算测试。"""

    def test_perfect_prediction_brier(self):
        assert compute_brier_score(1.0, 1) == 0.0
        assert compute_brier_score(0.0, 0) == 0.0

    def test_random_prediction_brier(self):
        b = compute_brier_score(0.5, 1)
        assert abs(b - 0.25) < 1e-10

    def test_wrong_prediction_brier(self):
        b = compute_brier_score(0.1, 1)
        assert b > 0.7  # (0.1 - 1)^2 = 0.81

    def test_perfect_log_loss(self):
        ll = compute_log_loss(1.0, 1)
        assert ll < 1e-9  # p clamped to 1-1e-10, -ln(1-1e-10) ≈ 1e-10

    def test_zero_prob_log_loss(self):
        # p clamped to 1e-10
        ll = compute_log_loss(0.0, 1)
        assert ll > 20  # -ln(1e-10) ≈ 23

    def test_moderate_log_loss(self):
        ll = compute_log_loss(0.7, 1)
        assert 0.3 < ll < 0.5  # -ln(0.7) ≈ 0.357


# ── TransitionRecord / VerificationRecord ─────────────────────────────

class TestDataClasses:
    """数据类序列化测试。"""

    def test_transition_record_asdict(self):
        rec = TransitionRecord(
            date="2026-07-18",
            timestamp="2026-07-18T10:00:00",
            current_regime="normal",
            qvix_50=18.0,
            qvix_500=20.0,
            prob_stay=0.6,
            prob_improve=0.25,
            prob_worsen=0.15,
            breadth_pct=55.0,
            vol_trend=-0.2,
            volume_signal=0.1,
            momentum_signal=0.3,
            confidence="high",
            blended_weights={"momentum": 0.4},
        )
        d = asdict(rec)
        assert d["current_regime"] == "normal"
        assert d["prob_stay"] == 0.6
        assert json.dumps(d)  # should serialize without error

    def test_verification_record_asdict(self):
        rec = VerificationRecord(
            prediction_date="2026-07-18",
            verification_date="2026-07-28",
            current_regime="normal",
            actual_regime_after="cautious",
            predicted_direction="stay",
            actual_direction="worsen",
            correct=False,
            predicted_prob=0.6,
            brier_score=0.16,
            log_loss=0.51,
            breadth_at_pred=55.0,
            vol_trend_at_pred=-0.2,
            volume_at_pred=0.1,
            momentum_at_pred=0.3,
            breadth_at_verify=0.0,
            vol_trend_at_verify=0.0,
            volume_at_verify=0.0,
            momentum_at_verify=0.0,
        )
        d = asdict(rec)
        assert d["correct"] is False
        assert json.dumps(d)  # should serialize


# ── TransitionBacktester ──────────────────────────────────────────────

class TestTransitionBacktester:
    """回测引擎测试。"""

    def setup_method(self):
        self.bt = TransitionBacktester()

    def test_no_predictions_returns_error(self):
        result = self.bt.run_full_backtest()
        assert "error" in result

    def test_load_empty_log(self, tmp_path):
        log_file = tmp_path / "transition_predictions.jsonl"
        log_file.write_text("")
        n = self.bt.load_predictions(log_file)
        assert n == 0

    def test_load_invalid_json(self, tmp_path):
        log_file = tmp_path / "transition_predictions.jsonl"
        log_file.write_text("not valid json\n")
        n = self.bt.load_predictions(log_file)
        assert n == 0

    def test_load_valid_predictions(self, tmp_path):
        log_file = tmp_path / "transition_predictions.jsonl"
        records = [
            {
                "date": "2026-07-01",
                "timestamp": "2026-07-01T10:00:00",
                "current_regime": "normal",
                "qvix_50": 18.0,
                "qvix_500": 20.0,
                "prob_stay": 0.6,
                "prob_improve": 0.25,
                "prob_worsen": 0.15,
                "breadth_pct": 55.0,
                "vol_trend": -0.2,
                "volume_signal": 0.1,
                "momentum_signal": 0.3,
                "confidence": "high",
                "blended_weights": {"momentum": 0.4},
            },
            {
                "date": "2026-07-02",
                "timestamp": "2026-07-02T10:00:00",
                "current_regime": "fearful",
                "qvix_50": 30.0,
                "qvix_500": 32.0,
                "prob_stay": 0.5,
                "prob_improve": 0.3,
                "prob_worsen": 0.2,
                "breadth_pct": 25.0,
                "vol_trend": 0.5,
                "volume_signal": 0.8,
                "momentum_signal": -0.6,
                "confidence": "medium",
                "blended_weights": {"mean_reversion": 0.3},
            },
        ]
        with open(log_file, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

        n = self.bt.load_predictions(log_file)
        assert n == 2

    @patch.object(TransitionBacktester, '_get_actual_regime_after_days')
    def test_verify_single_prediction(self, mock_actual):
        mock_actual.return_value = "cautious"

        pred = TransitionRecord(
            date="2026-07-01",
            timestamp="2026-07-01T10:00:00",
            current_regime="normal",
            qvix_50=18.0, qvix_500=20.0,
            prob_stay=0.6, prob_improve=0.25, prob_worsen=0.15,
            breadth_pct=55.0, vol_trend=-0.2,
            volume_signal=0.1, momentum_signal=0.3,
            confidence="high",
            blended_weights={},
        )

        v = self.bt.verify_prediction(pred)
        assert v is not None
        assert v.current_regime == "normal"
        assert v.actual_regime_after == "cautious"
        assert v.actual_direction == "worsen"
        assert v.predicted_direction == "stay"  # highest prob was stay
        assert v.correct is False
        assert v.brier_score > 0

    @patch.object(TransitionBacktester, '_get_actual_regime_after_days')
    def test_correct_prediction(self, mock_actual):
        mock_actual.return_value = "complacent"

        pred = TransitionRecord(
            date="2026-07-01",
            timestamp="2026-07-01T10:00:00",
            current_regime="normal",
            qvix_50=18.0, qvix_500=20.0,
            prob_stay=0.4, prob_improve=0.5, prob_worsen=0.1,
            breadth_pct=70.0, vol_trend=-0.5,
            volume_signal=0.3, momentum_signal=0.5,
            confidence="high",
            blended_weights={},
        )

        v = self.bt.verify_prediction(pred)
        assert v is not None
        assert v.actual_direction == "improve"
        assert v.predicted_direction == "improve"
        assert v.correct is True

    @patch.object(TransitionBacktester, '_get_actual_regime_after_days')
    def test_verify_returns_none_on_failure(self, mock_actual):
        mock_actual.return_value = None

        pred = TransitionRecord(
            date="2026-07-01",
            timestamp="2026-07-01T10:00:00",
            current_regime="normal",
            qvix_50=18.0, qvix_500=20.0,
            prob_stay=0.6, prob_improve=0.25, prob_worsen=0.15,
            breadth_pct=55.0, vol_trend=-0.2,
            volume_signal=0.1, momentum_signal=0.3,
            confidence="high",
            blended_weights={},
        )

        v = self.bt.verify_prediction(pred)
        assert v is None

    @patch.object(TransitionBacktester, '_get_actual_regime_after_days')
    def test_save_verification(self, mock_actual, tmp_path):
        mock_actual.return_value = "cautious"
        verify_file = tmp_path / "verify.jsonl"

        pred = TransitionRecord(
            date="2026-07-01",
            timestamp="2026-07-01T10:00:00",
            current_regime="normal",
            qvix_50=18.0, qvix_500=20.0,
            prob_stay=0.6, prob_improve=0.25, prob_worsen=0.15,
            breadth_pct=55.0, vol_trend=-0.2,
            volume_signal=0.1, momentum_signal=0.3,
            confidence="high",
            blended_weights={},
        )

        v = self.bt.verify_prediction(pred)
        self.bt.save_verification(v, verify_file)

        lines = verify_file.read_text().strip().split("\n")
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["current_regime"] == "normal"
