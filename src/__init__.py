"""
QuantLab - 双引擎量化研究平台
===========================

Qlib (深度研究) + VectorBT (快速实验)
"""

__version__ = "0.1.0"
__author__ = "Quant Research Team"

from src.constants import (
    MARKET_CN,
    MARKET_US,
    FACTOR_CATEGORIES,
    LABEL_TYPES,
)

from src.exceptions import (
    QuantLabError,
    DataError,
    FactorError,
    BacktestError,
    ConfigError,
)

__all__ = [
    "MARKET_CN",
    "MARKET_US",
    "FACTOR_CATEGORIES",
    "LABEL_TYPES",
    "QuantLabError",
    "DataError",
    "FactorError",
    "BacktestError",
    "ConfigError",
]
