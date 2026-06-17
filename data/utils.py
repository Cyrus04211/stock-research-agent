"""
数据层通用工具: 重试、安全类型转换、A 股代码格式化
"""
from __future__ import annotations

import time
from typing import Callable, TypeVar

T = TypeVar("T")


def safe_float(val, digits: int = 2) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        if f != f:  # NaN
            return None
        return round(f, digits)
    except (ValueError, TypeError):
        return None


def to_akshare_em_symbol(symbol: str) -> str:
    """东方财富 EM 接口代码: SH600519 / SZ000001"""
    if symbol.startswith(("SH", "SZ")):
        return symbol
    if symbol.startswith("6"):
        return f"SH{symbol}"
    return f"SZ{symbol}"


def to_akshare_gdfx_symbol(symbol: str) -> str:
    """股东分析接口代码: sh600519 / sz000001"""
    em = to_akshare_em_symbol(symbol)
    return em.lower()


def retry_call(fn: Callable[[], T], retries: int = 2, delay: float = 1.0) -> T:
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return fn()
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(delay * (attempt + 1))
    assert last_err is not None
    raise last_err
