"""Shared utility functions for ETF Platform.

Consolidates duplicate implementations that previously lived in multiple files.
"""


def safe_float(val) -> float:
    """Safely convert to float, return 0.0 for None/NaN/invalid."""
    if val is None or (isinstance(val, float) and val != val):
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0
