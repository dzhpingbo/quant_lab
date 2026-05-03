"""
估值因子（P/E、P/B、P/S代理，价格水平）
"""

import pandas as pd
import numpy as np
from src.factors.base import BaseFactor, FactorMeta


class ValuationFactor(BaseFactor):
    """估值因子基类"""
    
    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name="valuation_base",
            category="valuation",
            description="估值因子基类",
            neutralize=["industry"],
        )


class PriceToMovingAverage(ValuationFactor):
    """价格/均价（相对估值）"""
    
    def __init__(self, window: int = 60):
        super().__init__(window=window)
        self.window = window
        
    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"price_to_ma_{self.window}",
            category="valuation",
            description=f"价格/MA{self.window}",
            neutralize=[],
            params={"window": self.window}
        )
        
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        """价格相对均价越高 -> 估值越贵"""
        close = data["close"]
        ma = close.rolling(self.window).mean()
        return -close / ma  # 负号：越贵越差


class VolumePriceRatio(ValuationFactor):
    """成交额/市值代理（流通换手 = 隐含估值）"""
    
    def __init__(self, window: int = 20):
        super().__init__(window=window)
        self.window = window
        
    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"vpr_{self.window}",
            category="valuation",
            description=f"{self.window}日成交额/价格代理",
            neutralize=["market_cap"],
            params={"window": self.window}
        )
        
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        """
        成交额 / 收盘价 = 隐含成交股数
        反映市场对股票定价的活跃度
        """
        amount = data.get("amount", data["volume"] * data["close"])
        close = data["close"]
        
        ratio = amount / close
        return ratio.rolling(self.window).mean()


class PEProxy(ValuationFactor):
    """PE代理（价格 / 滚动收益）"""
    
    def __init__(self, window: int = 60):
        super().__init__(window=window)
        self.window = window
        
    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"pe_proxy_{self.window}",
            category="valuation",
            description=f"{self.window}日PE代理",
            neutralize=["industry"],
            params={"window": self.window}
        )
        
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        """
        PE代理 = 当前价格 / 滚动期间收益
        """
        close = data["close"]
        
        # 累计对数收益率（代理每股盈利）
        log_ret = np.log(close).diff()
        cum_earnings_proxy = log_ret.rolling(self.window).sum()
        cum_earnings_proxy = cum_earnings_proxy.replace(0, np.nan)
        
        pe_proxy = close / (close * cum_earnings_proxy)
        return -pe_proxy  # 负号：PE越低越好


class PBProxy(ValuationFactor):
    """PB代理（价格/账面价值估计）"""
    
    def __init__(self, window: int = 120):
        super().__init__(window=window)
        self.window = window
        
    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"pb_proxy_{self.window}",
            category="valuation",
            description=f"{self.window}日PB代理",
            neutralize=["industry"],
            params={"window": self.window}
        )
        
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        """
        PB代理 = 当前价格 / 历史最低价（作为账面价值估计）
        """
        close = data["close"]
        
        low_ma = close.rolling(self.window).min()
        pb_proxy = close / low_ma
        
        return -pb_proxy  # 负号：PB越低越好


class ReversalValuation(ValuationFactor):
    """反转估值（跌多了 = 相对低估）"""
    
    def __init__(self, window: int = 20):
        super().__init__(window=window)
        self.window = window
        
    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"reversal_val_{self.window}",
            category="valuation",
            description=f"{self.window}日反转估值",
            neutralize=[],
            params={"window": self.window}
        )
        
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        """短期跌幅越大 -> 相对低估"""
        close = data["close"]
        ret = close.pct_change(self.window)
        
        return -ret  # 跌得多的估值低


class HistoricalPricePercentile(ValuationFactor):
    """历史价格分位数（当前价处于多少分位）"""
    
    def __init__(self, window: int = 252):
        super().__init__(window=window)
        self.window = window
        
    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"price_pct_{self.window}",
            category="valuation",
            description=f"{self.window}日价格分位",
            neutralize=[],
            params={"window": self.window}
        )
        
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        """价格越处于历史高位 -> 估值越贵"""
        close = data["close"]
        
        rank_pct = close.rolling(self.window).rank(pct=True)
        return -rank_pct  # 负号：估值高的排名低


class AmountToMarketCap(ValuationFactor):
    """成交额/收盘价（流动性估值）"""
    
    def __init__(self, window: int = 20):
        super().__init__(window=window)
        self.window = window
        
    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"amount_to_price_{self.window}",
            category="valuation",
            description=f"{self.window}日成交额/价格",
            neutralize=["market_cap"],
            params={"window": self.window}
        )
        
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        """成交额代理市场活跃度"""
        amount = data.get("amount", data["volume"] * data["close"])
        close = data["close"]
        
        return amount.rolling(self.window).mean() / close


# 可用因子
VALUATION_FACTORS = {
    "price_to_ma_60": PriceToMovingAverage(window=60),
    "vpr_20": VolumePriceRatio(window=20),
    "pe_proxy_60": PEProxy(window=60),
    "pb_proxy_120": PBProxy(window=120),
    "reversal_val_20": ReversalValuation(window=20),
    "price_pct_252": HistoricalPricePercentile(window=252),
    "amount_to_price_20": AmountToMarketCap(window=20),
}
