"""L34 KB Catalyst 催化剂状态动态化 — TDD 测试 (2026-08-27).

覆盖:
- 催化剂 status 字段: pending/triggered/expired 三态
- 已兑现(triggered)催化剂: 从评分中移除, 防止"追已兑现催化"
- 未来(pending)催化剂: 正常加分
- 历史催化剂带 pending 默认值 (无 status 字段 → pending)
- get_kb_catalyst_summary 兼容新 status
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"


@pytest.fixture(autouse=True)
def _ensure_src_on_path():
    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))
    yield


class TestCatalystStatusCompatibility:
    """催化剂无 status 字段 → 默认 pending（旧数据兼容）。"""

    def test_legacy_catalyst_defaults_to_pending(self):
        from etf_platform.layers.l34_kb_catalyst import _active_items

        legacy = [{"k_code": "k053", "name": "旧催化", "boost": 0.5, "valid_until": "2099-12-31"}]
        active = _active_items(legacy)
        assert len(active) == 1
        assert active[0].get("status") == "pending", "无status字段应默认pending"


class TestTriggeredCatalystExcluded:
    """已兑现催化(triggered)不再参与加分 — 防追已兑现催化。"""

    def test_triggered_catalyst_not_counted(self):
        from etf_platform.layers.l34_kb_catalyst import score_l34_layer
        # 通过 monkeypatch 注入一个 triggered 催化到半导体
        import etf_platform.layers.l34_kb_catalyst as l34
        original = dict(l34.CATALYSTS)
        l34.CATALYSTS["半导体"] = [
            {
                "k_code": "k053",
                "name": "英伟达财报催化(已兑现)",
                "boost": 1.2,
                "valid_until": "2027-06-30",
                "status": "triggered",  # 已兑现
                "detail": "英伟达2027Q2营收962亿+106%已公布",
            },
            {
                "k_code": "k053",
                "name": "华为9/7发布会(未兑现)",
                "boost": 0.8,
                "valid_until": "2026-09-30",
                "status": "pending",
                "detail": "华为Mate XT2三折叠+麒麟2026芯片9/7发布",
            },
        ]
        try:
            r = l34.score_l34_layer("半导体")
            d = r["detail"]
            names = [c["name"] for c in d["catalysts"]]
            assert "华为9/7发布会(未兑现)" in names, "pending 催化应保留"
            assert "英伟达财报催化(已兑现)" not in names, "triggered 催化应从活性列表剔除"
        finally:
            l34.CATALYSTS.clear()
            l34.CATALYSTS.update(original)

    def test_triggered_reduces_score(self):
        """全部催化已兑现 → 评分为0 boost, 回到中性5.0。"""
        import etf_platform.layers.l34_kb_catalyst as l34
        original = dict(l34.CATALYSTS)
        l34.CATALYSTS["半导体"] = [
            {
                "k_code": "k053",
                "name": "已兑现催化A",
                "boost": 1.2,
                "valid_until": "2027-06-30",
                "status": "triggered",
                "detail": "详情",
            },
        ]
        try:
            r = l34.score_l34_layer("半导体")
            # 无pending催化 → 不加分；残存RISK_FACTORS惩罚使其≤中性5.0
            assert 4.0 <= r["score"] <= 5.0, \
                f"全部已兑现 → 低于/等于中性, got {r['score']}"
        finally:
            l34.CATALYSTS.clear()
            l34.CATALYSTS.update(original)

    def test_pending_keeps_score(self):
        """未兑现催化正常加分。"""
        import etf_platform.layers.l34_kb_catalyst as l34
        original = dict(l34.CATALYSTS)
        l34.CATALYSTS["半导体"] = [
            {
                "k_code": "k053",
                "name": "未来催化",
                "boost": 1.2,
                "valid_until": "2027-06-30",
                "status": "pending",
                "detail": "详情",
            },
        ]
        try:
            r = l34.score_l34_layer("半导体")
            assert r["score"] > 5.5, f"pending 催化加分, got {r['score']}"
        finally:
            l34.CATALYSTS.clear()
            l34.CATALYSTS.update(original)


class TestExpiredCatalystExcluded:
    """过期催化(valid_until 已过)不再参与 — 原逻辑保留。"""

    def test_expired_not_counted(self):
        import etf_platform.layers.l34_kb_catalyst as l34
        original = dict(l34.CATALYSTS)
        l34.CATALYSTS["半导体"] = [
            {
                "k_code": "k053",
                "name": "过期催化",
                "boost": 1.0,
                "valid_until": "2020-01-01",  # 已过期
                "status": "pending",
                "detail": "详情",
            },
        ]
        try:
            r = l34.score_l34_layer("半导体")
            # 过期催化不参与加分；RISK_FACTORS惩罚可致≤5.0
            assert 4.0 <= r["score"] <= 5.0, "过期催化不应加分"
        finally:
            l34.CATALYSTS.clear()
            l34.CATALYSTS.update(original)


class TestSummaryCompat:
    """get_kb_catalyst_summary 兼容新 status 字段。"""

    def test_summary_no_crash_with_status(self):
        from etf_platform.layers.l34_kb_catalyst import get_kb_catalyst_summary
        summary = get_kb_catalyst_summary("半导体")
        assert isinstance(summary, str)
        assert "L34" in summary