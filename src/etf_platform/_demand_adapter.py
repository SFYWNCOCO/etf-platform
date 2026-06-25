"""Adapter: wrap demand_scoring.py (L10-L11)"""
import sys
import os
from pathlib import Path

ETFDIR = Path(__file__).resolve().parent.parent.parent.parent / "etf_system"
if str(ETFDIR) not in sys.path:
    sys.path.insert(0, str(ETFDIR))

import io
_cwd = os.getcwd()
os.chdir(str(ETFDIR))
try:
    # Suppress demand_layer startup prints
    sys.stdout = io.StringIO()
    from demand_scoring import add_demand_layers_to_result as _add_demand
finally:
    sys.stdout = sys.__stdout__
    os.chdir(_cwd)


def add_demand_layers(penetration_result: dict) -> dict:
    """Append L10+L11 to penetration result dict."""
    return dict(_add_demand(penetration_result))
