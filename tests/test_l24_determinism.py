# -*- coding: utf-8 -*-
"""T9 determinism guard: L24 must be jitter-free - same input, identical output.

Regression for da972aa lesson: random.uniform(0.85, 1.15) in
_compute_feedback_ratio caused score/insights to flip across runs.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from etf_platform.layers.l24_system_dynamics import score_l24_layer


def test_l24_score_deterministic():
    """Same input called twice must produce identical score and insights."""
    r1 = score_l24_layer("半导体", 0.5, "512480")
    r2 = score_l24_layer("半导体", 0.5, "512480")
    assert isinstance(r1, dict) and isinstance(r2, dict)
    assert r1.get("score") == r2.get("score"), (
        "L24 score not deterministic: %s vs %s" % (r1.get("score"), r2.get("score"))
    )
    assert r1.get("insights") == r2.get("insights"), (
        "L24 insights not deterministic: %s vs %s" % (r1.get("insights"), r2.get("insights"))
    )


def test_l24_no_random_import():
    """Source must not import random (jitter ban)."""
    src = Path(__file__).resolve().parents[1] / "src" / "etf_platform" / "layers" / "l24_system_dynamics.py"
    text = src.read_text(encoding="utf-8")
    assert "import random" not in text
    assert "random.uniform" not in text
