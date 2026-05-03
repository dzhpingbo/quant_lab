"""Safety-first timing strategy helpers.

The functions in this module intentionally keep the execution model simple:
signals are generated after the close and executed at the next open.  This
matches the research reports and avoids same-bar lookahead.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BinaryStrategySpec:
    """Parameters for a long/cash ETF timing strategy."""

    name: str
    mom_window: int = 60
    breadth_window: int = 60
    breadth_buy: float = 0.65
    breadth_sell: float = 0.50
    vol_window: int = 20
    vol_max: float = 0.95
    safety_buy: Optional[float] = None
    safety_sell: Optional[float] = None
    require_pool_mom: bool = False


@dataclass(frozen=True)
class MovingAverageCrossoverSpec:
    """Parameters for a long/cash moving-average crossover strategy."""

    name: str
    fast_window: int
    slow_window: int
    breadth_window: int = 60
    breadth_buy: Optional[float] = None
    breadth_sell: Optional[float] = None
    vol_window: Optional[int] = None
    vol_max: Optional[float] = None
    require_pool_mom: bool = False


@dataclass(frozen=True)
class RegimeFilteredMASpec(MovingAverageCrossoverSpec):
    """Moving-average crossover with sideways-market filters."""

    adx_window: Optional[int] = None
    adx_min: Optional[float] = None
    er_window: Optional[int] = None
    er_min: Optional[float] = None
    chop_window: Optional[int] = None
    chop_max: Optional[float] = None
    ma_gap_atr_min: Optional[float] = None
    min_hold_days: int = 0
    cooldown_days: int = 0


def rolling_vol_percentile(ret: pd.Series, vol_window: int, rank_window: int = 252) -> pd.Series:
    """Return rolling realized-volatility percentile."""

    vol = ret.rolling(vol_window).std() * np.sqrt(252)
    return vol.rolling(rank_window, min_periods=80).rank(pct=True)


def average_true_range(data: pd.DataFrame, window: int = 14) -> pd.Series:
    """Average true range using Wilder-style smoothing."""

    high = data["high"]
    low = data["low"]
    close = data["close"]
    tr = pd.concat(
        [
            high - low,
            high.sub(close.shift()).abs(),
            low.sub(close.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()


def average_directional_index(data: pd.DataFrame, window: int = 14) -> pd.Series:
    """Average directional index. Higher values mean stronger trend."""

    high = data["high"]
    low = data["low"]
    close = data["close"]
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=data.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=data.index)
    atr = average_true_range(data, window)
    plus_di = 100 * plus_dm.ewm(alpha=1 / window, adjust=False, min_periods=window).mean().div(atr)
    minus_di = 100 * minus_dm.ewm(alpha=1 / window, adjust=False, min_periods=window).mean().div(atr)
    dx = 100 * plus_di.sub(minus_di).abs().div(plus_di.add(minus_di).replace(0, np.nan))
    return dx.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()


def efficiency_ratio(close: pd.Series, window: int = 20) -> pd.Series:
    """Kaufman efficiency ratio. Higher values mean cleaner directional movement."""

    direction = close.sub(close.shift(window)).abs()
    path = close.diff().abs().rolling(window).sum()
    return direction.div(path.replace(0, np.nan))


def choppiness_index(data: pd.DataFrame, window: int = 14) -> pd.Series:
    """Choppiness index. Lower values mean more trend-like movement."""

    high = data["high"]
    low = data["low"]
    close = data["close"]
    tr = pd.concat(
        [
            high - low,
            high.sub(close.shift()).abs(),
            low.sub(close.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr_sum = tr.rolling(window).sum()
    price_range = high.rolling(window).max().sub(low.rolling(window).min())
    return 100 * np.log10(atr_sum.div(price_range.replace(0, np.nan))).div(np.log10(window))


def defensive_timing_signal(
    asset: pd.DataFrame,
    breadth: pd.DataFrame,
    spec: BinaryStrategySpec,
    safety_breadth: Optional[pd.Series] = None,
) -> pd.Series:
    """Generate long/cash desired position from close-time indicators.

    Required columns:
    - asset: open, close
    - breadth: breadth_ma20, breadth_ma60, pool_ret20_median
    - safety_breadth: optional cross-sectional safety breadth, high is safer
    """

    idx = asset.index
    close = asset["close"]
    mom = close.pct_change(spec.mom_window, fill_method=None).to_numpy(dtype=float)
    ret = close.pct_change(fill_method=None)
    vol_pct = rolling_vol_percentile(ret, spec.vol_window).reindex(idx).to_numpy(dtype=float)
    breadth_col = "breadth_ma60" if spec.breadth_window >= 60 else "breadth_ma20"
    breadth_ma = breadth[breadth_col].reindex(idx).ffill().to_numpy(dtype=float)
    pool_mom = breadth["pool_ret20_median"].reindex(idx).ffill().to_numpy(dtype=float)
    safety = safety_breadth.reindex(idx).ffill().to_numpy(dtype=float) if safety_breadth is not None else None

    desired = np.zeros(len(idx), dtype=float)
    held = False
    for i in range(len(idx)):
        enter = (
            mom[i] > 0
            and breadth_ma[i] >= spec.breadth_buy
            and vol_pct[i] <= spec.vol_max
        )
        exit_ = (
            mom[i] <= 0
            or breadth_ma[i] <= spec.breadth_sell
            or vol_pct[i] > min(spec.vol_max + 0.10, 0.98)
        )
        if spec.require_pool_mom:
            enter = enter and pool_mom[i] > 0
            exit_ = exit_ or pool_mom[i] <= 0
        if safety is not None and spec.safety_buy is not None and spec.safety_sell is not None:
            enter = enter and safety[i] >= spec.safety_buy
            exit_ = exit_ or safety[i] <= spec.safety_sell

        if not held and bool(enter):
            held = True
        elif held and bool(exit_):
            held = False
        desired[i] = 1.0 if held else 0.0

    return pd.Series(desired, index=idx, name=spec.name)


def moving_average_crossover_signal(
    asset: pd.DataFrame,
    spec: MovingAverageCrossoverSpec,
    breadth: Optional[pd.DataFrame] = None,
) -> pd.Series:
    """Generate a close-time moving-average crossover desired position.

    A signal is generated after the close and should be executed at the next
    open by `backtest_binary_position`.
    """

    if spec.fast_window >= spec.slow_window:
        raise ValueError("fast_window must be smaller than slow_window")

    idx = asset.index
    close = asset["close"]
    fast_ma = close.rolling(spec.fast_window).mean().to_numpy(dtype=float)
    slow_ma = close.rolling(spec.slow_window).mean().to_numpy(dtype=float)
    ret = close.pct_change(fill_method=None)
    vol_pct = (
        rolling_vol_percentile(ret, spec.vol_window).reindex(idx).to_numpy(dtype=float)
        if spec.vol_window is not None and spec.vol_max is not None
        else None
    )

    breadth_ma = None
    pool_mom = None
    if spec.breadth_buy is not None or spec.breadth_sell is not None or spec.require_pool_mom:
        if breadth is None:
            raise ValueError("breadth data is required for breadth or pool momentum filters")
        breadth_col = "breadth_ma60" if spec.breadth_window >= 60 else "breadth_ma20"
        breadth_ma = breadth[breadth_col].reindex(idx).ffill().to_numpy(dtype=float)
        pool_mom = breadth["pool_ret20_median"].reindex(idx).ffill().to_numpy(dtype=float)

    desired = np.zeros(len(idx), dtype=float)
    held = False
    for i in range(len(idx)):
        enter = fast_ma[i] > slow_ma[i]
        exit_ = fast_ma[i] <= slow_ma[i]

        if breadth_ma is not None and spec.breadth_buy is not None and spec.breadth_sell is not None:
            enter = enter and breadth_ma[i] >= spec.breadth_buy
            exit_ = exit_ or breadth_ma[i] <= spec.breadth_sell
        if spec.require_pool_mom and pool_mom is not None:
            enter = enter and pool_mom[i] > 0
            exit_ = exit_ or pool_mom[i] <= 0
        if vol_pct is not None and spec.vol_max is not None:
            enter = enter and vol_pct[i] <= spec.vol_max
            exit_ = exit_ or vol_pct[i] > min(spec.vol_max + 0.10, 0.98)

        if not held and bool(enter):
            held = True
        elif held and bool(exit_):
            held = False
        desired[i] = 1.0 if held else 0.0

    return pd.Series(desired, index=idx, name=spec.name)


def regime_filtered_ma_signal(
    asset: pd.DataFrame,
    spec: RegimeFilteredMASpec,
    breadth: Optional[pd.DataFrame] = None,
) -> pd.Series:
    """Generate MA-crossover signals with trend/regime filters."""

    idx = asset.index
    close = asset["close"]
    fast_ma = close.rolling(spec.fast_window).mean().to_numpy(dtype=float)
    slow_ma = close.rolling(spec.slow_window).mean().to_numpy(dtype=float)
    ret = close.pct_change(fill_method=None)
    vol_pct = (
        rolling_vol_percentile(ret, spec.vol_window).reindex(idx).to_numpy(dtype=float)
        if spec.vol_window is not None and spec.vol_max is not None
        else None
    )
    atr_window = spec.adx_window or spec.chop_window or spec.slow_window
    atr = average_true_range(asset, max(2, int(atr_window))).reindex(idx).to_numpy(dtype=float)
    adx = (
        average_directional_index(asset, spec.adx_window).reindex(idx).to_numpy(dtype=float)
        if spec.adx_window is not None and spec.adx_min is not None
        else None
    )
    er = (
        efficiency_ratio(close, spec.er_window).reindex(idx).to_numpy(dtype=float)
        if spec.er_window is not None and spec.er_min is not None
        else None
    )
    chop = (
        choppiness_index(asset, spec.chop_window).reindex(idx).to_numpy(dtype=float)
        if spec.chop_window is not None and spec.chop_max is not None
        else None
    )

    breadth_ma = None
    pool_mom = None
    if spec.breadth_buy is not None or spec.breadth_sell is not None or spec.require_pool_mom:
        if breadth is None:
            raise ValueError("breadth data is required for breadth or pool momentum filters")
        breadth_col = "breadth_ma60" if spec.breadth_window >= 60 else "breadth_ma20"
        breadth_ma = breadth[breadth_col].reindex(idx).ffill().to_numpy(dtype=float)
        pool_mom = breadth["pool_ret20_median"].reindex(idx).ffill().to_numpy(dtype=float)

    desired = np.zeros(len(idx), dtype=float)
    held = False
    held_days = 0
    cooldown = 0
    for i in range(len(idx)):
        ma_gap = abs(fast_ma[i] - slow_ma[i]) / atr[i] if atr[i] and not np.isnan(atr[i]) else np.nan
        enter = fast_ma[i] > slow_ma[i]
        exit_ = fast_ma[i] <= slow_ma[i]

        if spec.ma_gap_atr_min is not None:
            enter = enter and ma_gap >= spec.ma_gap_atr_min
        if breadth_ma is not None and spec.breadth_buy is not None and spec.breadth_sell is not None:
            enter = enter and breadth_ma[i] >= spec.breadth_buy
            exit_ = exit_ or breadth_ma[i] <= spec.breadth_sell
        if spec.require_pool_mom and pool_mom is not None:
            enter = enter and pool_mom[i] > 0
            exit_ = exit_ or pool_mom[i] <= 0
        if vol_pct is not None and spec.vol_max is not None:
            enter = enter and vol_pct[i] <= spec.vol_max
            exit_ = exit_ or vol_pct[i] > min(spec.vol_max + 0.10, 0.98)
        if adx is not None and spec.adx_min is not None:
            enter = enter and adx[i] >= spec.adx_min
        if er is not None and spec.er_min is not None:
            enter = enter and er[i] >= spec.er_min
        if chop is not None and spec.chop_max is not None:
            enter = enter and chop[i] <= spec.chop_max

        if cooldown > 0:
            enter = False
            cooldown -= 1
        if held and held_days < spec.min_hold_days:
            exit_ = False

        if not held and bool(enter):
            held = True
            held_days = 0
        elif held and bool(exit_):
            held = False
            held_days = 0
            cooldown = spec.cooldown_days
        desired[i] = 1.0 if held else 0.0
        if held:
            held_days += 1

    return pd.Series(desired, index=idx, name=spec.name)


def backtest_binary_position(
    asset: pd.DataFrame,
    desired_after_close: pd.Series,
    cost_rate: float = 0.001,
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Backtest close-time signal executed at next open."""

    idx = asset.index
    open_px = asset["open"].reindex(idx)
    open_ret = open_px.shift(-1).div(open_px).sub(1).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    position = desired_after_close.shift(1).reindex(idx).fillna(0.0)
    turnover = position.diff().abs().fillna(position.abs())
    returns = position * open_ret - turnover * cost_rate
    nav = (1 + returns).cumprod()
    return nav, returns, position


def compute_performance_metrics(
    returns: pd.Series,
    start: pd.Timestamp,
    end: pd.Timestamp,
    risk_free: float = 0.02,
) -> Dict[str, float]:
    """Compute compact performance metrics for a return series."""

    r = returns.loc[start:end].dropna()
    if len(r) < 60:
        return {
            "total_return": np.nan,
            "annual_return": np.nan,
            "annual_vol": np.nan,
            "sharpe": np.nan,
            "max_drawdown": np.nan,
            "calmar": np.nan,
            "exposure": np.nan,
            "days": float(len(r)),
        }
    nav = (1 + r).cumprod()
    years = len(r) / 252
    annual_return = nav.iloc[-1] ** (1 / years) - 1
    annual_vol = r.std() * np.sqrt(252)
    drawdown = nav / nav.cummax() - 1
    max_drawdown = drawdown.min()
    return {
        "total_return": float(nav.iloc[-1] - 1),
        "annual_return": float(annual_return),
        "annual_vol": float(annual_vol),
        "sharpe": float((annual_return - risk_free) / annual_vol) if annual_vol > 1e-12 else np.nan,
        "max_drawdown": float(max_drawdown),
        "calmar": float(annual_return / abs(max_drawdown)) if max_drawdown < 0 else np.nan,
        "exposure": float((r != 0).mean()),
        "days": float(len(r)),
    }
