"""Safety and formula-style factors.

All factor values are oriented so that larger values are preferable for a
long-only stock selection model unless a class docstring says otherwise.
"""

from __future__ import annotations

from typing import Dict, Iterable

import numpy as np
import pandas as pd

from src.factors.base import BaseFactor, FactorMeta


class DownsideVolatility(BaseFactor):
    """Negative downside volatility. Larger means lower downside risk."""

    def __init__(self, window: int = 20, annualize: bool = True):
        super().__init__(window=window, annualize=annualize)

    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"safe_downside_vol_{self.window}",
            category="safety",
            description=f"Negative {self.window}d downside volatility",
            params=self.params,
        )

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        ret = data["close"].pct_change(fill_method=None)
        downside = ret.where(ret < 0, 0.0).rolling(self.window).std()
        if self.annualize:
            downside = downside * np.sqrt(252)
        return -downside


class RollingMaxDrawdown(BaseFactor):
    """Negative rolling max drawdown. Larger means smaller drawdown."""

    def __init__(self, window: int = 60):
        super().__init__(window=window)

    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"safe_maxdd_{self.window}",
            category="safety",
            description=f"Negative {self.window}d rolling max drawdown",
            params=self.params,
        )

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        close = data["close"]
        rolling_high = close.rolling(self.window, min_periods=max(5, self.window // 4)).max()
        drawdown = close.div(rolling_high).sub(1)
        return drawdown


class ConditionalValueAtRisk(BaseFactor):
    """Negative historical CVaR. Larger means smaller tail loss."""

    def __init__(self, window: int = 60, quantile: float = 0.05):
        super().__init__(window=window, quantile=quantile)

    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"safe_cvar_{self.window}_{int(self.quantile * 100)}",
            category="safety",
            description=f"Negative {self.window}d historical CVaR at {self.quantile:.0%}",
            params=self.params,
        )

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        ret = data["close"].pct_change(fill_method=None)

        def _cvar(x: np.ndarray) -> float:
            clean = x[~np.isnan(x)]
            if len(clean) == 0:
                return np.nan
            cutoff = np.quantile(clean, self.quantile)
            tail = clean[clean <= cutoff]
            return tail.mean() if len(tail) else np.nan

        return -ret.rolling(self.window, min_periods=max(10, self.window // 3)).apply(_cvar, raw=True)


class AmihudLiquidity(BaseFactor):
    """Negative Amihud illiquidity. Larger means more liquid."""

    def __init__(self, window: int = 20):
        super().__init__(window=window)

    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"safe_liquidity_amihud_{self.window}",
            category="safety",
            description=f"Negative {self.window}d Amihud illiquidity",
            params=self.params,
        )

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        amount = data["close"] * data["volume"]
        ret_abs = data["close"].pct_change(fill_method=None).abs()
        illiq = ret_abs.div(amount.replace(0, np.nan)).rolling(self.window).mean()
        return -illiq


class PriceVolumeCorrelation(BaseFactor):
    """Negative rolling return-volume correlation, inspired by formula alphas."""

    def __init__(self, window: int = 20):
        super().__init__(window=window)

    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"alpha_pv_corr_{self.window}",
            category="formula_alpha",
            description=f"Negative {self.window}d return-volume correlation",
            params=self.params,
        )

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        ret = data["close"].pct_change(fill_method=None)
        vol_chg = data["volume"].pct_change(fill_method=None)
        return -ret.rolling(self.window).corr(vol_chg)


class TrendStability(BaseFactor):
    """Medium-term momentum divided by volatility."""

    def __init__(self, mom_window: int = 60, vol_window: int = 20):
        super().__init__(mom_window=mom_window, vol_window=vol_window)

    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"safe_trend_stability_{self.mom_window}_{self.vol_window}",
            category="safety",
            description=f"{self.mom_window}d momentum scaled by {self.vol_window}d volatility",
            params=self.params,
        )

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        close = data["close"]
        mom = close.pct_change(self.mom_window, fill_method=None)
        vol = close.pct_change(fill_method=None).rolling(self.vol_window).std() * np.sqrt(252)
        return mom.div(vol.replace(0, np.nan))


class ReturnMomentum(BaseFactor):
    """Price momentum with optional skip window."""

    def __init__(self, window: int = 60, skip: int = 0):
        super().__init__(window=window, skip=skip)

    def _get_meta(self) -> FactorMeta:
        suffix = f"skip{self.skip}" if self.skip else "raw"
        return FactorMeta(
            name=f"alpha_mom_{self.window}_{suffix}",
            category="formula_alpha",
            description=f"{self.window}d return momentum with {self.skip}d skip",
            params=self.params,
        )

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        close = data["close"]
        if self.skip:
            return close.shift(self.skip).pct_change(self.window, fill_method=None)
        return close.pct_change(self.window, fill_method=None)


class ReturnReversal(BaseFactor):
    """Negative short-term return. Larger means more oversold."""

    def __init__(self, window: int = 5):
        super().__init__(window=window)

    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"alpha_reversal_{self.window}",
            category="formula_alpha",
            description=f"Negative {self.window}d return reversal",
            params=self.params,
        )

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        return -data["close"].pct_change(self.window, fill_method=None)


class MovingAverageDistance(BaseFactor):
    """Close divided by moving average minus one."""

    def __init__(self, window: int = 60):
        super().__init__(window=window)

    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"alpha_ma_distance_{self.window}",
            category="formula_alpha",
            description=f"Close / MA{self.window} - 1",
            params=self.params,
        )

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        close = data["close"]
        return close.div(close.rolling(self.window).mean()).sub(1)


class MovingAverageRatio(BaseFactor):
    """Short moving average divided by long moving average minus one."""

    def __init__(self, short_window: int = 20, long_window: int = 60):
        super().__init__(short_window=short_window, long_window=long_window)

    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"alpha_ma_ratio_{self.short_window}_{self.long_window}",
            category="formula_alpha",
            description=f"MA{self.short_window} / MA{self.long_window} - 1",
            params=self.params,
        )

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        close = data["close"]
        short = close.rolling(self.short_window).mean()
        long = close.rolling(self.long_window).mean()
        return short.div(long).sub(1)


class ChannelPosition(BaseFactor):
    """Position inside a rolling high-low channel."""

    def __init__(self, window: int = 60):
        super().__init__(window=window)

    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"alpha_channel_pos_{self.window}",
            category="formula_alpha",
            description=f"Close position in {self.window}d high-low channel",
            params=self.params,
        )

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        close = data["close"]
        high = data["high"].rolling(self.window).max()
        low = data["low"].rolling(self.window).min()
        return close.sub(low).div(high.sub(low).replace(0, np.nan))


class EfficiencyRatio(BaseFactor):
    """Kaufman-style trend efficiency ratio."""

    def __init__(self, window: int = 60):
        super().__init__(window=window)

    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"alpha_efficiency_{self.window}",
            category="formula_alpha",
            description=f"{self.window}d trend efficiency ratio",
            params=self.params,
        )

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        close = data["close"]
        direction = close.sub(close.shift(self.window)).abs()
        noise = close.diff().abs().rolling(self.window).sum()
        return direction.div(noise.replace(0, np.nan))


class LowRealizedVolatility(BaseFactor):
    """Negative realized volatility. Larger means lower volatility."""

    def __init__(self, window: int = 20, annualize: bool = True):
        super().__init__(window=window, annualize=annualize)

    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"safe_low_vol_{self.window}",
            category="safety",
            description=f"Negative {self.window}d realized volatility",
            params=self.params,
        )

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        ret = data["close"].pct_change(fill_method=None)
        vol = ret.rolling(self.window).std()
        if self.annualize:
            vol = vol * np.sqrt(252)
        return -vol


class VolumeMomentum(BaseFactor):
    """Volume trend factor."""

    def __init__(self, short_window: int = 5, long_window: int = 20):
        super().__init__(short_window=short_window, long_window=long_window)

    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"alpha_volume_mom_{self.short_window}_{self.long_window}",
            category="formula_alpha",
            description=f"Volume MA{self.short_window} / MA{self.long_window} - 1",
            params=self.params,
        )

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        volume = data["volume"]
        short = volume.rolling(self.short_window).mean()
        long = volume.rolling(self.long_window).mean()
        return short.div(long.replace(0, np.nan)).sub(1)


class IntradayStrength(BaseFactor):
    """Close location inside the daily high-low range."""

    def __init__(self, window: int = 20):
        super().__init__(window=window)

    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"alpha_intraday_strength_{self.window}",
            category="formula_alpha",
            description=f"{self.window}d mean close location in daily range",
            params=self.params,
        )

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        raw = data["close"].sub(data["low"]).div(data["high"].sub(data["low"]).replace(0, np.nan))
        return raw.rolling(self.window).mean()


class ReturnSkewness(BaseFactor):
    """Rolling return skewness."""

    def __init__(self, window: int = 60):
        super().__init__(window=window)

    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"alpha_ret_skew_{self.window}",
            category="formula_alpha",
            description=f"{self.window}d return skewness",
            params=self.params,
        )

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        return data["close"].pct_change(fill_method=None).rolling(self.window).skew()


class TDSequentialBuySetup(BaseFactor):
    """TD9/神奇九转 buy setup progress.

    Larger values mean a stronger buy setup: the close has been below the close
    four bars earlier for more consecutive days. Values are capped at 1 when
    the setup reaches nine.
    """

    def __init__(self, lookback: int = 4, setup: int = 9):
        super().__init__(lookback=lookback, setup=setup)

    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"alpha_td9_buy_setup_{self.lookback}_{self.setup}",
            category="formula_alpha",
            description=f"TD9 buy setup progress: close < close[-{self.lookback}]",
            params=self.params,
        )

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        condition = data["close"] < data["close"].shift(self.lookback)
        count = np.zeros(len(condition), dtype=float)
        running = 0
        for i, flag in enumerate(condition.fillna(False).to_numpy(dtype=bool)):
            running = running + 1 if flag else 0
            count[i] = min(running, self.setup) / self.setup
        return pd.Series(count, index=data.index, name=self.meta.name)


class TDSequentialSellPressure(BaseFactor):
    """Negative TD9/神奇九转 sell setup progress.

    Larger values are better for a long-only model because sell pressure is
    negated. When many stocks are deep in a sell setup, this factor falls.
    """

    def __init__(self, lookback: int = 4, setup: int = 9):
        super().__init__(lookback=lookback, setup=setup)

    def _get_meta(self) -> FactorMeta:
        return FactorMeta(
            name=f"alpha_td9_sell_pressure_{self.lookback}_{self.setup}",
            category="formula_alpha",
            description=f"Negative TD9 sell setup progress: close > close[-{self.lookback}]",
            params=self.params,
        )

    def calculate(self, data: pd.DataFrame) -> pd.Series:
        condition = data["close"] > data["close"].shift(self.lookback)
        count = np.zeros(len(condition), dtype=float)
        running = 0
        for i, flag in enumerate(condition.fillna(False).to_numpy(dtype=bool)):
            running = running + 1 if flag else 0
            count[i] = -min(running, self.setup) / self.setup
        return pd.Series(count, index=data.index, name=self.meta.name)


def cross_section_zscore(panel: pd.DataFrame) -> pd.DataFrame:
    """Row-wise z-score for a date x asset factor panel."""

    mean = panel.mean(axis=1)
    std = panel.std(axis=1).replace(0, np.nan)
    return panel.sub(mean, axis=0).div(std, axis=0)


def compute_safety_factor_panel(
    price_data: Dict[str, pd.DataFrame],
    factors: Iterable[BaseFactor] | None = None,
) -> Dict[str, pd.DataFrame]:
    """Compute safety factor panels for many assets.

    Returns a dict of factor_name -> DataFrame(date x code).
    """

    factor_list = list(factors) if factors is not None else list(SAFETY_FACTORS.values())
    panels: Dict[str, pd.DataFrame] = {}
    for factor in factor_list:
        values = {}
        for code, data in price_data.items():
            values[code] = factor.calculate(data)
        panels[factor.meta.name] = pd.DataFrame(values).sort_index()
    return panels


def composite_safety_score(panels: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Equal-weight composite safety score from factor panels."""

    if not panels:
        raise ValueError("No factor panels supplied.")
    standardized = [cross_section_zscore(panel) for panel in panels.values()]
    return pd.concat(standardized, axis=0).groupby(level=0).mean().sort_index()


SAFETY_FACTORS = {
    "safe_downside_vol_20": DownsideVolatility(window=20),
    "safe_downside_vol_60": DownsideVolatility(window=60),
    "safe_low_vol_20": LowRealizedVolatility(window=20),
    "safe_low_vol_60": LowRealizedVolatility(window=60),
    "safe_low_vol_120": LowRealizedVolatility(window=120),
    "safe_maxdd_60": RollingMaxDrawdown(window=60),
    "safe_maxdd_120": RollingMaxDrawdown(window=120),
    "safe_cvar_60_5": ConditionalValueAtRisk(window=60, quantile=0.05),
    "safe_cvar_120_5": ConditionalValueAtRisk(window=120, quantile=0.05),
    "safe_liquidity_amihud_20": AmihudLiquidity(window=20),
    "safe_liquidity_amihud_60": AmihudLiquidity(window=60),
    "safe_trend_stability_60_20": TrendStability(mom_window=60, vol_window=20),
    "safe_trend_stability_120_20": TrendStability(mom_window=120, vol_window=20),
    "alpha_pv_corr_20": PriceVolumeCorrelation(window=20),
    "alpha_pv_corr_60": PriceVolumeCorrelation(window=60),
    "alpha_mom_20_raw": ReturnMomentum(window=20),
    "alpha_mom_60_raw": ReturnMomentum(window=60),
    "alpha_mom_120_raw": ReturnMomentum(window=120),
    "alpha_mom_60_skip20": ReturnMomentum(window=60, skip=20),
    "alpha_mom_120_skip20": ReturnMomentum(window=120, skip=20),
    "alpha_reversal_5": ReturnReversal(window=5),
    "alpha_reversal_20": ReturnReversal(window=20),
    "alpha_ma_distance_20": MovingAverageDistance(window=20),
    "alpha_ma_distance_60": MovingAverageDistance(window=60),
    "alpha_ma_distance_120": MovingAverageDistance(window=120),
    "alpha_ma_ratio_20_60": MovingAverageRatio(short_window=20, long_window=60),
    "alpha_ma_ratio_60_120": MovingAverageRatio(short_window=60, long_window=120),
    "alpha_channel_pos_60": ChannelPosition(window=60),
    "alpha_channel_pos_120": ChannelPosition(window=120),
    "alpha_efficiency_60": EfficiencyRatio(window=60),
    "alpha_efficiency_120": EfficiencyRatio(window=120),
    "alpha_volume_mom_5_20": VolumeMomentum(short_window=5, long_window=20),
    "alpha_volume_mom_20_60": VolumeMomentum(short_window=20, long_window=60),
    "alpha_intraday_strength_20": IntradayStrength(window=20),
    "alpha_intraday_strength_60": IntradayStrength(window=60),
    "alpha_ret_skew_60": ReturnSkewness(window=60),
    "alpha_td9_buy_setup_4_9": TDSequentialBuySetup(lookback=4, setup=9),
    "alpha_td9_sell_pressure_4_9": TDSequentialSellPressure(lookback=4, setup=9),
}
