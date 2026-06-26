"""Adapter: L10+L11 demand layers using the new analysis/demand module."""
from etf_platform.analysis.demand import add_demand_layers as _add_demand

def add_demand_layers(penetration_result):
    """Append L10+L11 to penetration result using fixed demand scoring."""
    return _add_demand(penetration_result)