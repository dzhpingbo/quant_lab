"""
常量定义
"""

# 市场类型
MARKET_CN = "cn"
MARKET_US = "us"

# 因子类别
FACTOR_CATEGORIES = {
    "momentum": "动量因子",
    "reversal": "反转因子",
    "volatility": "波动率因子",
    "liquidity": "流动性因子",
    "quality": "质量因子",
    "valuation": "估值因子",
}

# 标签类型
LABEL_TYPES = {
    "return": "收益率标签",
    "excess_return": "超额收益标签",
    "rank": "排名标签",
    "binary": "二分类标签",
}

# 数据列名
COL_DATE = "date"
COL_SYMBOL = "symbol"
COL_OPEN = "open"
COL_HIGH = "high"
COL_LOW = "low"
COL_CLOSE = "close"
COL_VOLUME = "volume"
COL_AMOUNT = "amount"
COL_ADJ_CLOSE = "adj_close"
COL_VWAP = "vwap"

# A股特有
COL_ST_FLAG = "st_flag"
COL_SUSPENDED = "suspended"
COL_UP_LIMIT = "up_limit"
COL_DOWN_LIMIT = "down_limit"

# 价格限制（A股）
PRICE_LIMIT_NORMAL = 0.1  # 普通股票 10%
PRICE_LIMIT_KC = 0.2  # 科创板/创业板 20%
PRICE_LIMIT_ST = 0.05  # ST股票 5%

# 交易费用（A股）
COMMISSION_RATE = 0.00025  # 佣金 万分之2.5
STAMP_TAX_RATE = 0.001  # 印花税 千分之1 (卖出)
TRANSFER_FEE_RATE = 0.00002  # 过户费 万分之0.2

# 回测默认参数
DEFAULT_INITIAL_CASH = 1_000_000
DEFAULT_POSITION_PCT = 0.95  # 最大仓位比例

# 因子处理参数
WINSORIZE_LIMITS = (0.01, 0.99)  # 缩尾极值
NEUTRALIZE_FIELDS = ["industry", "market_cap"]  # 中性化字段
