"""
反转因子
"""
import pandas as pd
import numpy as np
from src.factors.base import BaseFactor, FactorMeta


class ReversalFactor(BaseFactor):
    """反转因子基类"""
    
    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name="reversal_base",
            category="reversal",
            description="反转因子基类",
        )


class ShortTermReversal(ReversalFactor):
    """短期反转"""
    
    def __init__(self, window: int = 5):
        super().__init__(window=window)
        self.window = window
        
    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"reversal_{self.window}d",
            category="reversal",
            description=f"{self.window}日反转",
            params={"window": self.window}
        )
        
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        return -data["close"].pct_change(self.window)


class MeanReversion(ReversalFactor):
    """均值回归（价格偏离均线的程度）"""
    
    def __init__(self, window: int = 20):
        super().__init__(window=window)
        self.window = window
        
    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"mean_rev_{self.window}",
            category="reversal",
            description=f"{self.window}日均值回归",
            params={"window": self.window}
        )
        
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        close = data["close"]
        ma = close.rolling(self.window).mean()
        return -(close - ma) / ma  # 偏高的反转期望下跌


REVERSAL_FACTORS = {
    "reversal_5d": ShortTermReversal(window=5),
    "reversal_20d": ShortTermReversal(window=20),
    "mean_rev_20": MeanReversion(window=20),
}
