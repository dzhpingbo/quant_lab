"""
异常定义
"""


class QuantLabError(Exception):
    """基础异常类"""
    pass


class DataError(QuantLabError):
    """数据相关错误"""
    pass


class FactorError(QuantLabError):
    """因子计算错误"""
    pass


class BacktestError(QuantLabError):
    """回测错误"""
    pass


class ConfigError(QuantLabError):
    """配置错误"""
    pass


class ValidationError(QuantLabError):
    """数据验证错误"""
    pass


class MarketError(QuantLabError):
    """市场数据错误"""
    pass
