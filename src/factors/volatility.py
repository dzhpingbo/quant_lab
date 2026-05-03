"""
波动率因子

包含：
- 历史波动率
- 实现波动率
- 波动率变化
- GARCH波动率
- 波动率偏度/峰度
"""

import pandas as pd
import numpy as np
from src.factors.base import BaseFactor, FactorMeta


class VolatilityFactor(BaseFactor):
    """波动率因子基类"""
    
    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name="volatility_base",
            category="volatility",
            description="波动率因子基类",
            neutralize=["market_cap"],
        )


class RealizedVolatility(VolatilityFactor):
    """实现波动率（收益率标准差）"""
    
    def __init__(self, window: int = 20, annualize: bool = True):
        super().__init__(window=window, annualize=annualize)
        self.window = window
        self.annualize = annualize
        
    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"realized_vol_{self.window}",
            category="volatility",
            description=f"{self.window}日实现波动率",
            neutralize=["market_cap"],
            params={"window": self.window, "annualize": self.annualize}
        )
        
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        """计算实现波动率"""
        returns = data["close"].pct_change()
        vol = returns.rolling(self.window).std()
        
        if self.annualize:
            vol = vol * np.sqrt(252)
            
        return vol


class ParkinsonVolatility(VolatilityFactor):
    """Parkinson波动率（使用高低价）"""
    
    def __init__(self, window: int = 20, annualize: bool = True):
        super().__init__(window=window, annualize=annualize)
        self.window = window
        self.annualize = annualize
        
    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"parkinson_vol_{self.window}",
            category="volatility",
            description=f"{self.window}日Parkinson波动率",
            neutralize=["market_cap"],
            params={"window": self.window, "annualize": self.annualize}
        )
        
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        """
        Parkinson波动率公式：
        σ² = (1/4N*ln2) * Σ[ln(Hi/Li)]²
        """
        log_hl = np.log(data["high"] / data["low"])
        var = (log_hl ** 2).rolling(self.window).mean() / (4 * np.log(2))
        vol = np.sqrt(var)
        
        if self.annualize:
            vol = vol * np.sqrt(252)
            
        return vol


class GarmanKlassVolatility(VolatilityFactor):
    """Garman-Klass波动率（使用OHLC）"""
    
    def __init__(self, window: int = 20, annualize: bool = True):
        super().__init__(window=window, annualize=annualize)
        self.window = window
        self.annualize = annualize
        
    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"gk_vol_{self.window}",
            category="volatility",
            description=f"{self.window}日Garman-Klass波动率",
            neutralize=["market_cap"],
            params={"window": self.window, "annualize": self.annualize}
        )
        
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        """
        Garman-Klass波动率公式：
        σ² = 0.5*ln(Hi/Li)² - (2ln2-1)*ln(Ci/Oi)²
        """
        log_hl = np.log(data["high"] / data["low"])
        log_co = np.log(data["close"] / data["open"])
        
        var = 0.5 * (log_hl ** 2) - (2 * np.log(2) - 1) * (log_co ** 2)
        var = var.rolling(self.window).mean()
        vol = np.sqrt(var)
        
        if self.annualize:
            vol = vol * np.sqrt(252)
            
        return vol


class VolatilityChange(VolatilityFactor):
    """波动率变化（当前波动率/历史波动率）"""
    
    def __init__(self, short_window: int = 5, long_window: int = 20):
        super().__init__(short_window=short_window, long_window=long_window)
        self.short_window = short_window
        self.long_window = long_window
        
    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"vol_change_{self.short_window}_{self.long_window}",
            category="volatility",
            description=f"波动率变化({self.short_window}/{self.long_window})",
            neutralize=["market_cap"],
            params={"short_window": self.short_window, "long_window": self.long_window}
        )
        
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        """计算波动率变化率"""
        returns = data["close"].pct_change()
        short_vol = returns.rolling(self.short_window).std()
        long_vol = returns.rolling(self.long_window).std()
        
        return short_vol / long_vol


class VolatilitySkewness(VolatilityFactor):
    """波动率偏度（收益率分布的不对称性）"""
    
    def __init__(self, window: int = 20):
        super().__init__(window=window)
        self.window = window
        
    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"vol_skew_{self.window}",
            category="volatility",
            description=f"{self.window}日收益率偏度",
            neutralize=["market_cap"],
            params={"window": self.window}
        )
        
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        """计算收益率偏度"""
        returns = data["close"].pct_change()
        return returns.rolling(self.window).skew()


class VolatilityKurtosis(VolatilityFactor):
    """波动率峰度（收益率分布的尾部厚度）"""
    
    def __init__(self, window: int = 20):
        super().__init__(window=window)
        self.window = window
        
    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"vol_kurt_{self.window}",
            category="volatility",
            description=f"{self.window}日收益率峰度",
            neutralize=["market_cap"],
            params={"window": self.window}
        )
        
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        """计算收益率峰度"""
        returns = data["close"].pct_change()
        return returns.rolling(self.window).kurt()


class MaxDrawdown(VolatilityFactor):
    """最大回撤"""
    
    def __init__(self, window: int = 20):
        super().__init__(window=window)
        self.window = window
        
    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"max_drawdown_{self.window}",
            category="volatility",
            description=f"{self.window}日最大回撤",
            neutralize=["market_cap"],
            params={"window": self.window}
        )
        
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        """计算最大回撤"""
        close = data["close"]
        rolling_max = close.rolling(self.window).max()
        drawdown = (close - rolling_max) / rolling_max
        return drawdown


class ATRFactor(VolatilityFactor):
    """平均真实波幅 (Average True Range)"""
    
    def __init__(self, window: int = 14):
        super().__init__(window=window)
        self.window = window
        
    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"atr_{self.window}",
            category="volatility",
            description=f"{self.window}日ATR",
            neutralize=["market_cap"],
            params={"window": self.window}
        )
        
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        """计算ATR"""
        high = data["high"]
        low = data["low"]
        close = data["close"]
        prev_close = close.shift(1)
        
        tr1 = high - low
        tr2 = abs(high - prev_close)
        tr3 = abs(low - prev_close)
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(self.window).mean()
        
        return atr


class VolatilityRatio(VolatilityFactor):
    """波动率比率（日内波动/日间波动）"""
    
    def __init__(self, window: int = 20):
        super().__init__(window=window)
        self.window = window
        
    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"vol_ratio_{self.window}",
            category="volatility",
            description=f"{self.window}日波动率比率",
            neutralize=["market_cap"],
            params={"window": self.window}
        )
        
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        """计算波动率比率"""
        # 日内波动
        intraday_vol = (data["high"] - data["low"]) / data["close"]
        intraday_vol = intraday_vol.rolling(self.window).std()
        
        # 日间波动
        overnight_vol = data["close"].pct_change().rolling(self.window).std()
        
        return intraday_vol / overnight_vol


# 创建具体因子实例
VOLATILITY_FACTORS = {
    "realized_vol_20": RealizedVolatility(window=20),
    "realized_vol_60": RealizedVolatility(window=60),
    "parkinson_vol_20": ParkinsonVolatility(window=20),
    "gk_vol_20": GarmanKlassVolatility(window=20),
    "vol_change_5_20": VolatilityChange(short_window=5, long_window=20),
    "vol_skew_20": VolatilitySkewness(window=20),
    "vol_kurt_20": VolatilityKurtosis(window=20),
    "max_drawdown_20": MaxDrawdown(window=20),
    "atr_14": ATRFactor(window=14),
    "vol_ratio_20": VolatilityRatio(window=20),
}
