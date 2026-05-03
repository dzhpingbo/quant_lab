"""
质量因子（ROE, ROA, 毛利率, 盈利稳定性, 财务健康度）
"""

import pandas as pd
import numpy as np
from src.factors.base import BaseFactor, FactorMeta


class QualityFactor(BaseFactor):
    """质量因子基类"""
    
    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name="quality_base",
            category="quality",
            description="质量因子基类",
            neutralize=["industry"],
        )


class ROE(QualityFactor):
    """净资产收益率，基于价格代理（避免财务数据缺失）"""
    
    def __init__(self, window: int = 60):
        super().__init__(window=window)
        self.window = window
        
    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"roe_proxy_{self.window}",
            category="quality",
            description=f"{self.window}日ROE代理指标",
            neutralize=["market_cap"],
            params={"window": self.window}
        )
        
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        """
        使用纯价格数据计算ROE代理：
        ROE_proxy = 累计收益率标准化
        """
        # 累计收益率作为盈利能力代理
        ret = data["close"].pct_change()
        cum_ret = (1 + ret).rolling(self.window).apply(np.prod, raw=True) - 1
        
        return cum_ret


class EarningsQuality(QualityFactor):
    """盈利质量（收盘价趋势稳定性）"""
    
    def __init__(self, window: int = 60):
        super().__init__(window=window)
        self.window = window
        
    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"earn_quality_{self.window}",
            category="quality",
            description=f"{self.window}日盈利质量",
            neutralize=["market_cap"],
            params={"window": self.window}
        )
        
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        """
        价格趋势的R²作为盈利质量代理
        """
        import warnings
        warnings.filterwarnings('ignore')
        
        close = data["close"]
        
        def calc_r2(x):
            if len(x) < 10:
                return np.nan
            t = np.arange(len(x))
            corr = np.corrcoef(t, x)[0, 1]
            return corr ** 2
            
        return close.rolling(self.window).apply(calc_r2, raw=True)


class GrossMarginProxy(QualityFactor):
    """毛利率代理（收益率稳定性）"""
    
    def __init__(self, window: int = 20, short_window: int = 5):
        super().__init__(window=window, short_window=short_window)
        self.window = window
        self.short_window = short_window
        
    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"gross_margin_proxy_{self.window}",
            category="quality",
            description=f"{self.window}日毛利率代理",
            neutralize=["market_cap"],
            params={"window": self.window}
        )
        
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        """
        使用价格数据：稳定的上行趋势代理高毛利率
        """
        ret = data["close"].pct_change()
        
        # 正收益比例
        pos_ratio = (ret > 0).rolling(self.window).mean()
        
        # 平均收益 / 收益波动 (类似夏普)
        mean_ret = ret.rolling(self.window).mean()
        std_ret = ret.rolling(self.window).std()
        
        sharpe_proxy = mean_ret / std_ret
        
        return sharpe_proxy


class ReturnOnAssetProxy(QualityFactor):
    """ROA代理（资产效率）"""
    
    def __init__(self, window: int = 60):
        super().__init__(window=window)
        self.window = window
        
    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"roa_proxy_{self.window}",
            category="quality",
            description=f"{self.window}日ROA代理",
            neutralize=["market_cap"],
            params={"window": self.window}
        )
        
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        """
        用成交额 / 市值变化代理资产利用效率
        """
        amount = data.get("amount", data["volume"] * data["close"])
        close = data["close"]
        
        # 单位成交额带来的价格变化
        price_change = close.pct_change()
        amount_norm = amount / amount.rolling(self.window).mean()
        
        # 价格效率
        price_eff = price_change / amount_norm.replace(0, np.nan)
        
        return price_eff.rolling(self.window).mean()


class EarningsStabilityProxy(QualityFactor):
    """盈利稳定性代理（价格波动稳定性）"""
    
    def __init__(self, window: int = 60, short_window: int = 10):
        super().__init__(window=window, short_window=short_window)
        self.window = window
        self.short_window = short_window
        
    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"earn_stability_{self.window}",
            category="quality",
            description=f"{self.window}日盈利稳定性代理",
            neutralize=["market_cap"],
            params={"window": self.window}
        )
        
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        """
        收益稳定性 = 1 / 收益标准差变化系数
        """
        ret = data["close"].pct_change()
        
        long_std = ret.rolling(self.window).std()
        short_std = ret.rolling(self.short_window).std()
        
        # 短期波动相对长期波动的稳定性
        stability = -short_std / long_std
        
        return stability


class ProfitGrowthProxy(QualityFactor):
    """盈利增长代理（价格动量）"""
    
    def __init__(self, window: int = 60, lag: int = 5):
        super().__init__(window=window, lag=lag)
        self.window = window
        self.lag = lag
        
    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"profit_growth_{self.window}",
            category="quality",
            description=f"{self.window}日盈利增长代理",
            neutralize=["market_cap"],
            params={"window": self.window, "lag": self.lag}
        )
        
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        """
        加速增长的价格动量作为盈利增长代理
        """
        close = data["close"]
        
        # 长期收益
        long_ret = close.pct_change(self.window)
        # 当前短期收益
        short_ret = close.pct_change(self.lag)
        
        # 动量加速度
        prev_short_ret = short_ret.shift(self.lag)
        growth = short_ret - prev_short_ret
        
        return growth


# 可用因子
QUALITY_FACTORS = {
    "roe_proxy_60": ROE(window=60),
    "earn_quality_60": EarningsQuality(window=60),
    "gross_margin_proxy_20": GrossMarginProxy(window=20),
    "roa_proxy_60": ReturnOnAssetProxy(window=60),
    "earn_stability_60": EarningsStabilityProxy(window=60),
    "profit_growth_60": ProfitGrowthProxy(window=60),
}
