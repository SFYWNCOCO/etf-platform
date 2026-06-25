"""Adapter: wrap penetration_v9.py (L8-L9)"""
import sys
import os
from pathlib import Path

ETFDIR = Path(__file__).resolve().parent.parent.parent.parent / "etf_system"
if str(ETFDIR) not in sys.path:
    sys.path.insert(0, str(ETFDIR))

_cwd = os.getcwd()
os.chdir(str(ETFDIR))
try:
    from penetration_v9 import (
        run_penetration_v9 as _run_v9,
        format_v9_report as _fmt_v9,
        batch_penetrate_v9 as _batch_v9,
    )
finally:
    os.chdir(_cwd)


def run_v9(code: str, causal_data: dict = None) -> dict:
    """Run L1-L9 (v9 includes v7 internally)."""
    return dict(_run_v9(code, causal_data))


def format_v9(result: dict) -> str:
    return _fmt_v9(result)


def batch_v9(limit: int = 50, sort_by: str = "score", codes: list = None) -> list:
    return _batch_v9(limit=limit, sort_by=sort_by, codes=codes)
