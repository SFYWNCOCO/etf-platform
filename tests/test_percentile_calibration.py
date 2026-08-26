"""S5 composite 百分位化 + k-code 推荐理由注入 — 批次D修正 (选项3: 展示层注解, 零行为变更)"""
import copy
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"


def _load_weekly_top3():
    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))
    spec = importlib.util.spec_from_file_location("weekly_top3", ROOT / "weekly_top3.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestPercentileCalibrate:
    def test_zero_behavior_change(self):
        """零行为变更：纯函数不修改输入，输出 score/composite_score/layer_scores 与输入完全相等"""
        from etf_platform.pipeline import percentile_calibrate
        results = [
            {"etf_code": "A", "layer_scores": {"L3_Material": 3.0, "L8_CapitalFlow": 7.0},
             "score": 5.0, "composite_score": 5.0},
            {"etf_code": "B", "layer_scores": {"L3_Material": 5.0, "L8_CapitalFlow": 5.0},
             "score": 6.0, "composite_score": 6.0},
            {"etf_code": "C", "layer_scores": {"L3_Material": 8.0, "L8_CapitalFlow": 4.0},
             "score": 7.0, "composite_score": 7.0},
        ]
        snapshot = copy.deepcopy(results)
        out = percentile_calibrate(results)
        # 输入未被修改（纯函数）
        assert results == snapshot
        # 返回的是新列表而非原对象
        assert out is not results
        # score/composite_score/layer_scores 与输入完全相等
        for orig, new in zip(results, out):
            assert new["score"] == orig["score"]
            assert new["composite_score"] == orig["composite_score"]
            assert new["layer_scores"] == orig["layer_scores"]

    def test_composite_percentile_monotonic(self):
        """新增 composite_percentile 键且单调序保持（score 高者百分位不低）"""
        from etf_platform.pipeline import percentile_calibrate
        results = [
            {"etf_code": "A", "layer_scores": {"L3_Material": 3.0}, "score": 3.0, "composite_score": 3.0},
            {"etf_code": "B", "layer_scores": {"L3_Material": 6.0}, "score": 6.0, "composite_score": 6.0},
            {"etf_code": "C", "layer_scores": {"L3_Material": 9.0}, "score": 9.0, "composite_score": 9.0},
        ]
        out = percentile_calibrate(results)
        pcts = [r["composite_percentile"] for r in out]
        assert pcts[0] == 0.0      # 最低 → 0
        assert pcts[1] == 50.0     # 中位 → 50
        assert pcts[2] == 100.0    # 最高 → 100
        assert pcts[0] <= pcts[1] <= pcts[2]
        # 每个输出都带 composite_percentile 与 layer_scores_raw
        for r in out:
            assert "composite_percentile" in r
            assert "layer_scores_raw" in r
            assert r["layer_scores_raw"] == r["layer_scores"]

    def test_n1_deterministic(self):
        """n=1 时 composite_percentile=50（确定性行为），score/composite_score/layer_scores 不变"""
        from etf_platform.pipeline import percentile_calibrate
        results = [{"etf_code": "A", "layer_scores": {"L3_Material": 6.3},
                    "score": 6.3, "composite_score": 6.3}]
        out = percentile_calibrate(results)
        assert out[0]["layer_scores"]["L3_Material"] == 6.3
        assert out[0]["score"] == 6.3
        assert out[0]["composite_score"] == 6.3
        assert out[0]["composite_percentile"] == 50.0
        assert out[0]["layer_scores_raw"] == {"L3_Material": 6.3}

    def test_disable_returns_original_values(self):
        """enable=False 返回新列表副本但不加注解，分值不变"""
        from etf_platform.pipeline import percentile_calibrate
        results = [
            {"etf_code": "A", "layer_scores": {"L3_Material": 4.0}, "score": 4.0,
             "composite_score": 4.0},
            {"etf_code": "B", "layer_scores": {"L3_Material": 6.0}, "score": 6.0,
             "composite_score": 6.0},
        ]
        out = percentile_calibrate(results, enable=False)
        assert out[0]["layer_scores"]["L3_Material"] == 4.0
        assert out[1]["layer_scores"]["L3_Material"] == 6.0
        assert "composite_percentile" not in out[0]
        assert out is not results  # 仍返回新列表


class TestKbReasonsForSector:
    def _registry(self, tmp_path, entries):
        reg_path = tmp_path / "kb_registry.json"
        reg_path.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
        from etf_platform.kb.registry import KBRegistry
        return KBRegistry(registry_path=reg_path)

    def test_hit_returns_up_to_3_with_kcode_title(self, tmp_path):
        mod = _load_weekly_top3()
        reg = self._registry(tmp_path, {
            "k900": {"code": "k900", "title": "半导体材料研究", "source_file": "x",
                     "consumer": "analysis/mat.py", "mode": "research", "status": "active"},
            "k901": {"code": "k901", "title": "医药产业链分析", "source_file": "x",
                     "consumer": "analysis/med.py", "mode": "layer", "status": "active"},
            "k902": {"code": "k902", "title": "军工景气度观察", "source_file": "x",
                     "consumer": "decision/xx.py", "mode": "signal", "status": "active"},
            "k903": {"code": "k903", "title": "无关内容", "source_file": "x",
                     "consumer": "y", "mode": "research", "status": "active"},
        })
        reasons = mod._kb_reasons_for_sector("半导体", registry=reg)
        assert len(reasons) <= 3
        assert reasons, "应至少命中一条 KB 依据"
        for r in reasons:
            assert {"kcode", "title"} <= set(r)

    def test_no_match_returns_empty(self, tmp_path):
        mod = _load_weekly_top3()
        reg = self._registry(tmp_path, {
            "k910": {"code": "k910", "title": "纯数学研究", "source_file": "x",
                     "consumer": "y", "mode": "research", "status": "active"},
        })
        reasons = mod._kb_reasons_for_sector("半导体", registry=reg)
        assert reasons == []
