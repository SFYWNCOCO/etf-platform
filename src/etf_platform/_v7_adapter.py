"""Adapter: wrap penetration_v7.py (L1-L7)"""
import sys
import os
from pathlib import Path

ETFDIR = Path(__file__).resolve().parent.parent.parent.parent / "etf_system"
if str(ETFDIR) not in sys.path:
    sys.path.insert(0, str(ETFDIR))

_cwd = os.getcwd()
os.chdir(str(ETFDIR))
try:
    from penetration_v7 import (
        run_penetration_v7 as _run_v7,
        format_report as _fmt_v7,
    )
finally:
    os.chdir(_cwd)


def run_v7(code: str, causal_data: dict = None) -> dict:
    """Run L1-L7 for a single ETF code."""
    return dict(_run_v7(code, causal_data))


def format_v7(result: dict) -> str:
    """Format L1-L7 report."""
    return _fmt_v7(result)
