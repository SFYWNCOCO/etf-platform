import pytest

class TestConfigLoader:
    def test_import(self):
        from etf_platform.config_loader import (
            load_etfs, load_vulnerability, load_materials,
            load_general, get_buyable_etfs,
        )
        assert callable(load_etfs)
        assert callable(load_vulnerability)
        assert callable(load_materials)
        assert callable(load_general)
        assert callable(get_buyable_etfs)

    def test_load_etfs(self):
        from etf_platform.config_loader import load_etfs
        etfs = load_etfs()
        assert isinstance(etfs, dict)
        assert len(etfs) > 500

    def test_etf_structure(self):
        from etf_platform.config_loader import load_etfs
        etfs = load_etfs()
        required = {"name", "type", "sector", "fee", "leverage", "risk_level", "access"}
        for code, info in list(etfs.items())[:20]:
            missing = required - set(info.keys())
            assert not missing, f"ETF {code} missing fields: {missing}"

    def test_get_buyable(self):
        from etf_platform.config_loader import get_buyable_etfs, load_etfs
        buyable = get_buyable_etfs()
        all_etfs = load_etfs()
        assert len(buyable) < len(all_etfs)
        for code, info in buyable.items():
            assert info["access"] == "buyable"

    def test_load_vulnerability(self):
        from etf_platform.config_loader import load_vulnerability
        vuln = load_vulnerability()
        assert isinstance(vuln, dict)
        assert len(vuln) > 500

    def test_load_materials(self):
        from etf_platform.config_loader import load_materials
        mats = load_materials()
        assert isinstance(mats, dict)
        assert len(mats) >= 30

    def test_load_general(self):
        from etf_platform.config_loader import load_general
        cfg = load_general()
        assert "budget" in cfg
        assert cfg["budget"] == 1000

class TestAdapterImports:
    def test_v7_adapter(self):
        from etf_platform._v7_adapter import run_v7, format_v7
        assert callable(run_v7)
        assert callable(format_v7)

    def test_v9_adapter(self):
        from etf_platform._v9_adapter import run_v9, format_v9, batch_v9
        assert callable(run_v9)
        assert callable(format_v9)
        assert callable(batch_v9)

    def test_demand_adapter(self):
        from etf_platform._demand_adapter import add_demand_layers
        assert callable(add_demand_layers)
