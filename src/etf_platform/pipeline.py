"""Unified L1-L11 penetration pipeline."""
from ._v9_adapter import run_v9, batch_v9, format_v9
from ._demand_adapter import add_demand_layers


def run_full(code: str, causal_data: dict = None) -> dict:
    """Run all 11 layers for a single ETF code.
    
    Args:
        code: ETF code (e.g. '159995')
        causal_data: Optional causal model data
        
    Returns:
        dict with L1-L11 scores and layers
    """
    result = run_v9(code, causal_data)
    result = add_demand_layers(result)
    result["etf_code"] = code
    result["pipeline_version"] = "0.1.0"
    return result


def format_full(result: dict) -> str:
    """Format all 11 layers as report."""
    return format_v9(result)


def batch_full(limit: int = 50, sort_by: str = "score", codes: list = None) -> list:
    """Batch run for multiple ETFs with all 11 layers."""
    results = batch_v9(limit=limit, sort_by=sort_by, codes=codes)
    enriched = []
    for r in results:
        try:
            enriched.append(add_demand_layers(r))
        except Exception:
            enriched.append(r)
    return enriched
