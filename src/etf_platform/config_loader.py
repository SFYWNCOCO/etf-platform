"""Config loader: reads from YAML files in config/ directory."""
import yaml
from pathlib import Path
from functools import lru_cache

_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"


def _load_yaml(name):
    path = _CONFIG_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def load_etfs():
    """Load all ETF definitions from YAML (cached)."""
    data = _load_yaml("etfs.yaml")
    return data.get("etfs", {})


@lru_cache(maxsize=1)
def load_meta():
    """Load _meta section from etfs.yaml (cached).

    Contains count, generated, delisted_codes (幸存者偏差防护).
    """
    data = _load_yaml("etfs.yaml")
    return data.get("_meta", {})


@lru_cache(maxsize=1)
def load_delisted_codes():
    """Load delisted ETF codes list (幸存者偏差防护).

    Returns empty list if not configured. Used by screener to exclude
    delisted ETFs and by backtest to flag delisted events.
    """
    meta = load_meta()
    return list(meta.get("delisted_codes", []))


@lru_cache(maxsize=1)
def load_vulnerability():
    """Load vulnerability matrix (cached)."""
    return _load_yaml("vulnerability.yaml")


@lru_cache(maxsize=1)
def load_materials():
    """Load material dependency map (cached).

    Uses FullLoader because materials.yaml contains !!python/tuple tags
    (e.g. (0.90, 30, 36, 0.90)) that safe_load cannot parse.
    This is a local config file — no untrusted input risk.
    """
    path = _CONFIG_DIR / "materials.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.load(f, Loader=yaml.FullLoader)
    return data.get("material_map", {})


@lru_cache(maxsize=1)
def load_general():
    """Load general configuration (cached)."""
    return _load_yaml("general.yaml")


@lru_cache(maxsize=1)
def load_weights():
    """Load profile→category weights from weights.yaml (cached).

    Returns dict of {profile: {category: weight}}. Used by pipeline
    to compute profile-aware weighted composite score.
    """
    return _load_yaml("weights.yaml")


@lru_cache(maxsize=1)
def load_layers():
    """Load layer→category mapping from layers.yaml (cached).

    Returns dict with key 'layer_to_category' mapping layer names
    (e.g. L3_Material) to category names (e.g. 供给侧).
    """
    return _load_yaml("layers.yaml")


@lru_cache(maxsize=1)
def load_backtest():
    """Load backtest configuration from backtest.yaml (cached).

    Contains transaction_cost, cost_bps, cutoff_date.
    """
    return _load_yaml("backtest.yaml")


@lru_cache(maxsize=1)
def load_risk():
    """Load risk layer configuration from risk.yaml (cached).

    Contains stress test thresholds (stress_mild/severe/tail) and
    stoic composite score weights (stoic_controllability_weight/tail_risk_weight).
    """
    return _load_yaml("risk.yaml")


def get_buyable_etfs():
    """Return only buyable ETFs."""
    etfs = load_etfs()
    return {k: v for k, v in etfs.items() if v.get("access") == "buyable"}


if __name__ == "__main__":
    etfs = load_etfs()
    print(f"ETFs loaded: {len(etfs)}")
    buyable = get_buyable_etfs()
    print(f"Buyable: {len(buyable)}")
