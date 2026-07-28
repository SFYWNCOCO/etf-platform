"""Deterministic ETF-code-based jitter utilities.

Polynomial rolling hash maps an ETF code (6-digit numeric string) to a
deterministic float in [-amplitude, +amplitude]. Same code always returns
the same jitter; different codes get different values.

Used by L14 (Stoic Risk) and L18 (VaR) to break intra-sector/intra-bucket
clustering where multiple ETFs in the same sector/bucket would otherwise
receive identical scores.
"""


def code_jitter(etf_code: str, amplitude: float = 0.5) -> float:
    """基于ETF代码的确定性jitter (polynomial rolling hash).

    相同代码总是返回相同jitter,不同代码得到不同值.

    Args:
        etf_code: ETF代码字符串 (期望6位数字, 如 '510300')
        amplitude: jitter幅度, 返回值在 [-amplitude, +amplitude] 范围内

    Returns:
        float: 在 [-amplitude, +amplitude] 范围内的确定性jitter.
              非数字代码或空字符串返回 0.0.
    """
    if not etf_code or not etf_code.isdigit():
        return 0.0
    h = 0
    for d in etf_code:
        h = (h * 31 + int(d)) % 10000
    return (h / 10000.0 * 2 - 1) * amplitude


__all__ = ["code_jitter"]
