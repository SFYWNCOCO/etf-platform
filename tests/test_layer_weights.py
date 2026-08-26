"""tests for composite layer weights (CC T8 / P1-C).

覆盖: yaml 缺失→等权; enabled=false→None; 加权平均数学正确性(两层手算);
EXCLUDE_KEYS 不参与; 未覆盖层用 default 1.0。
"""
import pytest

from etf_platform.pipeline import _COMPOSITE_EXCLUDE_KEYS, _compute_composite_score
from etf_platform.utils.layer_weights import load_composite_layer_weights


def _write_yaml(tmp_path, body: str):
    p = tmp_path / "weights.yaml"
    p.write_text(body, encoding="utf-8")
    return p


def test_yaml_missing_returns_none(tmp_path):
    """yaml 缺失 → None（=纯等权原行为）。"""
    assert load_composite_layer_weights(str(tmp_path / "no_such.yaml")) is None


def test_enabled_false_returns_none(tmp_path):
    """enabled=false → None。"""
    p = _write_yaml(tmp_path, "composite_layer_weights:\n  enabled: false\n  default: 1.0\n  overrides:\n    L20_OptionVol: 0.3\n")
    assert load_composite_layer_weights(str(p)) is None


def test_load_returns_overrides(tmp_path):
    """enabled=true 正常 → 返回 overrides 映射。"""
    p = _write_yaml(tmp_path, "composite_layer_weights:\n  enabled: true\n  default: 1.0\n  overrides:\n    L20_OptionVol: 0.3\n    L1_ETF: 0.5\n")
    w = load_composite_layer_weights(str(p))
    assert w == {"L20_OptionVol": 0.3, "L1_ETF": 0.5}


def test_compute_equal_weight_when_no_weights():
    """weights=None/空 → 等权平均。"""
    scores = {"L1_ETF": 4.0, "L2_Holdings": 6.0}
    assert _compute_composite_score(scores) == 5.0
    assert _compute_composite_score(scores, weights={}) == 5.0


def test_weighted_avg_math_two_layers():
    """加权平均数学正确性: Σ(w·s)/Σw = (0.5*4+1.5*6)/(0.5+1.5) = 11/2 = 5.5。"""
    scores = {"L1_ETF": 4.0, "L2_Holdings": 6.0}
    weights = {"L1_ETF": 0.5, "L2_Holdings": 1.5}
    assert _compute_composite_score(scores, weights) == 5.5


def test_exclude_keys_not_counted():
    """EXCLUDE_KEYS 键不参与 composite（等权与加权都排除）。"""
    detail_key = "L21_BiasDetail"
    assert detail_key in _COMPOSITE_EXCLUDE_KEYS
    scores = {"L1_ETF": 4.0, "L2_Holdings": 6.0, detail_key: 10.0, "L22_Detail": 0.0}
    assert _compute_composite_score(scores) == 5.0
    weights = {"L1_ETF": 0.5, "L2_Holdings": 1.5}
    assert _compute_composite_score(scores, weights) == 5.5


def test_uncovered_layer_uses_default_weight():
    """未覆盖层用 default 1.0: (0.5*4+1.0*6)/(0.5+1.0)=8/1.5≈5.33。"""
    scores = {"L1_ETF": 4.0, "L2_Holdings": 6.0}
    weights = {"L1_ETF": 0.5}
    assert _compute_composite_score(scores, weights) == 5.33
