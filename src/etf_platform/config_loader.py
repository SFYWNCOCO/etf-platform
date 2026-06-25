"""Config loader: reads from YAML files in config/ directory."""
import yaml
from pathlib import Path

_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"


def _load_yaml(name):
    path = _CONFIG_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_etfs():
    """Load all ETF definitions from YAML."""
    data = _load_yaml("etfs.yaml")
    return data.get("etfs", {})


def load_vulnerability():
    """Load vulnerability matrix."""
    return _load_yaml("vulnerability.yaml")


def load_materials():
    """Load material dependency map."""
    path = _CONFIG_DIR / "materials.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.load(f, Loader=yaml.FullLoader)
    return data.get("material_map", {})


def load_general():
    """Load general configuration."""
    return _load_yaml("general.yaml")


def get_buyable_etfs():
    """Return only buyable ETFs."""
    etfs = load_etfs()
    return {k: v for k, v in etfs.items() if v.get("access") == "buyable"}


if __name__ == "__main__":
    etfs = load_etfs()
    print(f"ETFs loaded: {len(etfs)}")
    buyable = get_buyable_etfs()
    print(f"Buyable: {len(buyable)}")
