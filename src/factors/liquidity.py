"""
流动性因子

包含：
- 换手率
- Amihud非流动性指标
- 成交额波动
- 买卖压力
- 流动性冲击
"""

import pandas as pd
import numpy as np
from src.factors.base import BaseFactor, FactorMeta


class LiquidityFactor(BaseFactor):
    """流动性因子基类"""
    
    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name="liquidity_base",
            category="liquidity",
            description="流动性因子基类",
            neutralize=["market_cap"],
        )


class TurnoverRate(LiquidityFactor):
    """换手率"""
    
    def __init__(self, window: int = 20, use_amount: bool = False):
        super().__init__(window=window, use_amount=use_amount)
        self.window = window
        self.use_amount = use_amount
        
    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"turnover_{self.window}",
            category="liquidity",
            description=f"{self.window}日平均换手率",
            neutralize=["market_cap"],
            params={"window": self.window, "use_amount": self.use_amount}
        )
        
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        """计算换手率"""
        if self.use_amount and "amount" in data.columns:
            # 使用成交额/流通市值
            turnover = data["amount"] / data.get("float_market_cap", data["amount"])
        else:
            # 使用成交量/流通股本
            turnover = data["volume"] / data.get("float_shares", data["volume"])
            
        return turnover.rolling(self.window).mean()


class TurnoverVolatility(LiquidityFactor):
    """换手率波动"""
    
    def __init__(self, window: int = 20):
        super().__init__(window=window)
        self.window = window
        
    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"turnover_vol_{self.window}",
            category="liquidity",
            description=f"{self.window}日换手率波动",
            neutralize=["market_cap"],
            params={"window": self.window}
        )
        
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        """计算换手率波动"""
        turnover = data["volume"] / data.get("float_shares", data["volume"])
        return turnover.rolling(self.window).std()


class AmihudIlliquidity(LiquidityFactor):
    """
    Amihud非流动性指标
    衡量价格对交易量的敏感度
    """
    
    def __init__(self, window: int = 20):
        super().__init__(window=window)
        self.window = window
        
    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"amihud_{self.window}",
            category="liquidity",
            description=f"{self.window}日Amihud非流动性",
            neutralize=["market_cap"],
            params={"window": self.window}
        )
        
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        """
        Amihud = |收益率| / 成交额
        值越大，流动性越差
        """
        returns = data["close"].pct_change().abs()
        amount = data.get("amount", data["volume"] * data["close"])
        
        illiq = returns / amount
        illiq = illiq.replace([np.inf, -np.inf], np.nan)
        
        return illiq.rolling(self.window).mean()


class VolumePriceTrend(LiquidityFactor):
    """量价趋势 (Volume Price Trend)"""
    
    def __init__(self, window: int = 20):
        super().__init__(window=window)
        self.window = window
        
    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"vpt_{self.window}",
            category="liquidity",
            description=f"{self.window}日量价趋势",
            neutralize=["market_cap"],
            params={"window": self.window}
        )
        
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        """
        VPT = Σ(Volume * (Close - PrevClose) / PrevClose)
        """
        close = data["close"]
        volume = data["volume"]
        
        pct_change = close.pct_change()
        vpt = (volume * pct_change).cumsum()
        
        return vpt.rolling(self.window).mean()


class MoneyFlowIndex(LiquidityFactor):
    """资金流量指标 (Money Flow Index)"""
    
    def __init__(self, window: int = 14):
        super().__init__(window=window)
        self.window = window
        
    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"mfi_{self.window}",
            category="liquidity",
            description=f"{self.window}日资金流量指标",
            neutralize=["market_cap"],
            params={"window": self.window}
        )
        
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        """
        MFI = 100 - (100 / (1 + Money Flow Ratio))
        """
        typical_price = (data["high"] + data["low"] + data["close"]) / 3
        raw_money_flow = typical_price * data["volume"]
        
        prev_typical = typical_price.shift(1)
        positive_flow = raw_money_flow.where(typical_price > prev_typical, 0)
        negative_flow = raw_money_flow.where(typical_price < prev_typical, 0)
        
        positive_sum = positive_flow.rolling(self.window).sum()
        negative_sum = negative_flow.rolling(self.window).sum()
        
        money_flow_ratio = positive_sum / negative_sum
        mfi = 100 - (100 / (1 + money_flow_ratio))
        
        return mfi


class VolumeSkewness(LiquidityFactor):
    """成交量偏度"""
    
    def __init__(self, window: int = 20):
        super().__init__(window=window)
        self.window = window
        
    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"volume_skew_{self.window}",
            category="liquidity",
            description=f"{self.window}日成交量偏度",
            neutralize=["market_cap"],
            params={"window": self.window}
        )
        
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        """计算成交量偏度"""
        return data["volume"].rolling(self.window).skew()


class RelativeVolume(LiquidityFactor):
    """相对成交量（当前成交量/历史平均）"""
    
    def __init__(self, short_window: int = 5, long_window: int = 20):
        super().__init__(short_window=short_window, long_window=long_window)
        self.short_window = short_window
        self.long_window = long_window
        
    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"rel_volume_{self.short_window}_{self.long_window}",
            category="liquidity",
            description=f"相对成交量({self.short_window}/{self.long_window})",
            neutralize=["market_cap"],
            params={"short_window": self.short_window, "long_window": self.long_window}
        )
        
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        """计算相对成交量"""
        short_vol = data["volume"].rolling(self.short_window).mean()
        long_vol = data["volume"].rolling(self.long_window).mean()
        
        return short_vol / long_vol


class LiquidityShock(LiquidityFactor):
    """流动性冲击（成交量异常变化）"""
    
    def __init__(self, window: int = 20, zscore_threshold: float = 2.0):
        super().__init__(window=window, zscore_threshold=zscore_threshold)
        self.window = window
        self.zscore_threshold = zscore_threshold
        
    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"liq_shock_{self.window}",
            category="liquidity",
            description=f"{self.window}日流动性冲击",
            neutralize=["market_cap"],
            params={"window": self.window, "zscore_threshold": self.zscore_threshold}
        )
        
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        """计算流动性冲击（成交量Z-Score）"""
        volume = data["volume"]
        vol_mean = volume.rolling(self.window).mean()
        vol_std = volume.rolling(self.window).std()
        
        zscore = (volume - vol_mean) / vol_std
        return zscore


class IntradayLiquidity(LiquidityFactor):
    """日内流动性（基于高低开收）"""
    
    def __init__(self, window: int = 20):
        super().__init__(window=window)
        self.window = window
        
    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"intraday_liq_{self.window}",
            category="liquidity",
            description=f"{self.window}日日内流动性",
            neutralize=["market_cap"],
            params={"window": self.window}
        )
        
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        """
        日内流动性 = (High - Low) / Volume
        值越大，流动性越差
        """
        price_range = data["high"] - data["low"]
        liquidity = price_range / data["volume"]
        
        return liquidity.rolling(self.window).mean()


# 创建具体因子实例
LIQUIDITY_FACTORS = {
    "turnover_20": TurnoverRate(window=20),
    "turnover_60": TurnoverRate(window=60),
    "turnover_vol_20": TurnoverVolatility(window=20),
    "amihud_20": AmihudIlliquidity(window=20),
    "vpt_20": VolumePriceTrend(window=20),
    "mfi_14": MoneyFlowIndex(window=14),
    "volume_skew_20": VolumeSkewness(window=20),
    "rel_volume_5_20": RelativeVolume(short_window=5, long_window=20),
    "liq_shock_20": LiquidityShock(window=20),
    "intraday_liq_20": IntradayLiquidity(window=20),
}
