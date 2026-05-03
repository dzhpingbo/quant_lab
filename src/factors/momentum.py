"""
动量因子
"""
import pandas as pd
import numpy as np
from src.factors.base import BaseFactor, FactorMeta


class MomentumFactor(BaseFactor):
    """动量因子基类"""
    
    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name="momentum_base",
            category="momentum",
            description="动量因子基类",
        )


class PriceMomentum(MomentumFactor):
    """价格动量"""
    
    def __init__(self, window: int = 20, skip: int = 0):
        super().__init__(window=window, skip=skip)
        self.window = window
        self.skip = skip
        
    def _get_meta(self) -> FactorMeta:
        name = f"mom_{self.window}d" if self.skip == 0 else f"mom_{self.window}d_skip{self.skip}"
        return FactorMeta(
            name=name,
            category="momentum",
            description=f"{self.window}日价格动量（跳过{self.skip}日）",
            params={"window": self.window, "skip": self.skip}
        )
        
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        close = data["close"]
        if self.skip:
            return close.shift(self.skip).pct_change(self.window)
        return close.pct_change(self.window)


class VolumeMomentum(MomentumFactor):
    """成交量动量"""
    
    def __init__(self, window: int = 20):
        super().__init__(window=window)
        self.window = window
        
    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"vol_mom_{self.window}",
            category="momentum",
            description=f"{self.window}日成交量动量",
            params={"window": self.window}
        )
        
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        return data["volume"].pct_change(self.window)


class MACD(MomentumFactor):
    """MACD信号"""
    
    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9):
        super().__init__(fast=fast, slow=slow, signal=signal)
        self.fast = fast
        self.slow = slow
        self.signal = signal
        
    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"macd_{self.fast}_{self.slow}_{self.signal}",
            category="momentum",
            description=f"MACD({self.fast},{self.slow},{self.signal})",
            params={"fast": self.fast, "slow": self.slow, "signal": self.signal}
        )
        
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        close = data["close"]
        ema_fast = close.ewm(span=self.fast).mean()
        ema_slow = close.ewm(span=self.slow).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=self.signal).mean()
        return macd_line - signal_line  # MACD柱


class RSI(MomentumFactor):
    """RSI指标"""
    
    def __init__(self, window: int = 14):
        super().__init__(window=window)
        self.window = window
        
    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"rsi_{self.window}",
            category="momentum",
            description=f"{self.window}日RSI",
            params={"window": self.window}
        )
        
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        delta = data["close"].diff()
        gain = delta.where(delta > 0, 0).rolling(self.window).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(self.window).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi


MOMENTUM_FACTORS = {
    "mom_20d": PriceMomentum(window=20),
    "mom_60d": PriceMomentum(window=60),
    "mom_120d": PriceMomentum(window=120),
    "vol_mom_20": VolumeMomentum(window=20),
    "macd_12_26_9": MACD(),
    "rsi_14": RSI(window=14),
}
