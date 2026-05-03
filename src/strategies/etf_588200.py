"""Reusable 588200 ETF strategy specs, grids, and signal builders.

This module keeps strategy definitions out of one-off research scripts.  The
functions here only build desired positions after the close; execution and
portfolio accounting stay in the backtest layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.strategies.safety import (
    BinaryStrategySpec,
    MovingAverageCrossoverSpec,
    RegimeFilteredMASpec,
    moving_average_crossover_signal,
    regime_filtered_ma_signal,
    rolling_vol_percentile,
)


def _row_bool(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _maybe_float(row: pd.Series, name: str) -> Optional[float]:
    value = row.get(name, np.nan)
    return None if pd.isna(value) else float(value)


def _maybe_int(row: pd.Series, name: str) -> Optional[int]:
    value = row.get(name, np.nan)
    return None if pd.isna(value) else int(value)


def rsi_series(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def make_ma_crossover_specs() -> List[MovingAverageCrossoverSpec]:
    windows = [5, 20, 60, 120]
    pairs = [(fast, slow) for fast in windows for slow in windows if fast < slow]
    specs: List[MovingAverageCrossoverSpec] = []
    for fast, slow in pairs:
        specs.append(
            MovingAverageCrossoverSpec(
                name=f"ma_cross__ma{fast}_{slow}",
                fast_window=fast,
                slow_window=slow,
            )
        )
        for buy, sell in [(0.55, 0.45), (0.60, 0.50), (0.65, 0.50)]:
            specs.append(
                MovingAverageCrossoverSpec(
                    name=f"ma_cross_pool__ma{fast}_{slow}__bb{int(buy * 100)}__bs{int(sell * 100)}",
                    fast_window=fast,
                    slow_window=slow,
                    breadth_buy=buy,
                    breadth_sell=sell,
                )
            )
        for vol_window in [20, 60, 120]:
            for vol_max in [0.90, 0.95]:
                specs.append(
                    MovingAverageCrossoverSpec(
                        name=f"ma_cross_vol__ma{fast}_{slow}__vol{vol_window}__vp{int(vol_max * 100)}",
                        fast_window=fast,
                        slow_window=slow,
                        vol_window=vol_window,
                        vol_max=vol_max,
                    )
                )
                for buy, sell in [(0.55, 0.45), (0.60, 0.50), (0.65, 0.50)]:
                    for require_pool_mom in [False, True]:
                        name = (
                            f"ma_cross_pool_vol__ma{fast}_{slow}__bb{int(buy * 100)}__bs{int(sell * 100)}"
                            f"__vol{vol_window}__vp{int(vol_max * 100)}"
                        )
                        if require_pool_mom:
                            name += "__poolmom"
                        specs.append(
                            MovingAverageCrossoverSpec(
                                name=name,
                                fast_window=fast,
                                slow_window=slow,
                                breadth_buy=buy,
                                breadth_sell=sell,
                                vol_window=vol_window,
                                vol_max=vol_max,
                                require_pool_mom=require_pool_mom,
                            )
                        )
    return specs


def ma_crossover_signal_for(
    asset: pd.DataFrame,
    breadth: pd.DataFrame,
    spec: MovingAverageCrossoverSpec,
) -> pd.Series:
    needs_breadth = (
        spec.breadth_buy is not None
        or spec.breadth_sell is not None
        or spec.require_pool_mom
    )
    return moving_average_crossover_signal(asset, spec, breadth=breadth if needs_breadth else None)


def ma_crossover_spec_from_row(row: pd.Series) -> MovingAverageCrossoverSpec:
    return MovingAverageCrossoverSpec(
        name=str(row["strategy"]),
        fast_window=int(row["fast_window"]),
        slow_window=int(row["slow_window"]),
        breadth_buy=_maybe_float(row, "breadth_buy"),
        breadth_sell=_maybe_float(row, "breadth_sell"),
        vol_window=_maybe_int(row, "vol_window"),
        vol_max=_maybe_float(row, "vol_max"),
        require_pool_mom=_row_bool(row.get("require_pool_mom", False)),
    )


def make_regime_filtered_ma_specs() -> List[RegimeFilteredMASpec]:
    pairs = [(5, 20), (5, 60), (5, 120), (20, 60), (20, 120), (60, 120)]
    breadth_sets = [(0.55, 0.45), (0.60, 0.50), (0.65, 0.50)]
    filters: List[Dict[str, object]] = []

    for adx_min in [15, 20, 25]:
        filters.append({"tag": f"adx14_{adx_min}", "adx_window": 14, "adx_min": adx_min})
        filters.append({"tag": f"adx20_{adx_min}", "adx_window": 20, "adx_min": adx_min})
    for er_min in [0.20, 0.30, 0.40]:
        filters.append({"tag": f"er20_{int(er_min * 100)}", "er_window": 20, "er_min": er_min})
        filters.append({"tag": f"er40_{int(er_min * 100)}", "er_window": 40, "er_min": er_min})
    for chop_max in [45, 50, 55]:
        filters.append({"tag": f"chop14_{chop_max}", "chop_window": 14, "chop_max": chop_max})
        filters.append({"tag": f"chop20_{chop_max}", "chop_window": 20, "chop_max": chop_max})
    for gap_min in [0.20, 0.40, 0.60]:
        filters.append({"tag": f"gap_{int(gap_min * 100)}", "ma_gap_atr_min": gap_min})

    for adx_min in [15, 20]:
        for gap_min in [0.20, 0.40]:
            filters.append(
                {
                    "tag": f"adx14_{adx_min}_gap_{int(gap_min * 100)}",
                    "adx_window": 14,
                    "adx_min": adx_min,
                    "ma_gap_atr_min": gap_min,
                }
            )
    for er_min in [0.20, 0.30]:
        for gap_min in [0.20, 0.40]:
            filters.append(
                {
                    "tag": f"er20_{int(er_min * 100)}_gap_{int(gap_min * 100)}",
                    "er_window": 20,
                    "er_min": er_min,
                    "ma_gap_atr_min": gap_min,
                }
            )
    for adx_min in [15, 20]:
        for er_min in [0.20, 0.30]:
            filters.append(
                {
                    "tag": f"adx14_{adx_min}_er20_{int(er_min * 100)}",
                    "adx_window": 14,
                    "adx_min": adx_min,
                    "er_window": 20,
                    "er_min": er_min,
                }
            )
    for chop_max in [45, 50]:
        for gap_min in [0.20, 0.40]:
            filters.append(
                {
                    "tag": f"chop14_{chop_max}_gap_{int(gap_min * 100)}",
                    "chop_window": 14,
                    "chop_max": chop_max,
                    "ma_gap_atr_min": gap_min,
                }
            )

    specs: List[RegimeFilteredMASpec] = []
    for fast, slow in pairs:
        for buy, sell in breadth_sets:
            for vol_window, vol_max in [(120, 0.90), (120, 0.95), (60, 0.95)]:
                for require_pool_mom in [False, True]:
                    for hold_days, cooldown_days in [(0, 0), (3, 1), (5, 2)]:
                        for filter_spec in filters:
                            tag = str(filter_spec["tag"])
                            name = (
                                f"sideways_filter__ma{fast}_{slow}__bb{int(buy * 100)}__bs{int(sell * 100)}"
                                f"__vol{vol_window}__vp{int(vol_max * 100)}__{tag}"
                            )
                            if require_pool_mom:
                                name += "__poolmom"
                            if hold_days:
                                name += f"__hold{hold_days}"
                            if cooldown_days:
                                name += f"__cool{cooldown_days}"
                            kwargs = {k: v for k, v in filter_spec.items() if k != "tag"}
                            specs.append(
                                RegimeFilteredMASpec(
                                    name=name,
                                    fast_window=fast,
                                    slow_window=slow,
                                    breadth_buy=buy,
                                    breadth_sell=sell,
                                    vol_window=vol_window,
                                    vol_max=vol_max,
                                    require_pool_mom=require_pool_mom,
                                    min_hold_days=hold_days,
                                    cooldown_days=cooldown_days,
                                    **kwargs,
                                )
                            )
    return specs


def regime_filtered_signal_for(
    asset: pd.DataFrame,
    breadth: pd.DataFrame,
    spec: RegimeFilteredMASpec,
) -> pd.Series:
    return regime_filtered_ma_signal(asset, spec, breadth=breadth)


def regime_filtered_ma_spec_from_row(row: pd.Series) -> RegimeFilteredMASpec:
    return RegimeFilteredMASpec(
        name=str(row["strategy"]),
        fast_window=int(row["fast_window"]),
        slow_window=int(row["slow_window"]),
        breadth_buy=float(row["breadth_buy"]),
        breadth_sell=float(row["breadth_sell"]),
        vol_window=_maybe_int(row, "vol_window"),
        vol_max=_maybe_float(row, "vol_max"),
        require_pool_mom=_row_bool(row.get("require_pool_mom", False)),
        adx_window=_maybe_int(row, "adx_window"),
        adx_min=_maybe_float(row, "adx_min"),
        er_window=_maybe_int(row, "er_window"),
        er_min=_maybe_float(row, "er_min"),
        chop_window=_maybe_int(row, "chop_window"),
        chop_max=_maybe_float(row, "chop_max"),
        ma_gap_atr_min=_maybe_float(row, "ma_gap_atr_min"),
        min_hold_days=int(row.get("min_hold_days", 0) or 0),
        cooldown_days=int(row.get("cooldown_days", 0) or 0),
    )


def make_safety_upgrade_specs() -> List[BinaryStrategySpec]:
    specs = [
        BinaryStrategySpec(
            name="baseline_prev_best__mom60__breadth65_50__vol20_vp95",
            mom_window=60,
            breadth_window=60,
            breadth_buy=0.65,
            breadth_sell=0.50,
            vol_window=20,
            vol_max=0.95,
        )
    ]
    breadth_pairs = [(0.55, 0.45), (0.60, 0.50), (0.65, 0.50)]
    safety_pairs = [(0.50, 0.40), (0.55, 0.45), (0.60, 0.50)]
    for mom in [20, 60, 120]:
        for vol_window in [20, 60, 120]:
            for vol_max in [0.80, 0.90, 0.95]:
                for breadth_buy, breadth_sell in breadth_pairs:
                    for safety_buy, safety_sell in safety_pairs:
                        for require_pool_mom in [False, True]:
                            name = (
                                f"safety_mv__mom{mom}__bb{int(breadth_buy * 100)}"
                                f"__bs{int(breadth_sell * 100)}__vol{vol_window}"
                                f"__vp{int(vol_max * 100)}__sb{int(safety_buy * 100)}"
                                f"__ss{int(safety_sell * 100)}"
                            )
                            if require_pool_mom:
                                name += "__poolmom"
                            specs.append(
                                BinaryStrategySpec(
                                    name=name,
                                    mom_window=mom,
                                    breadth_window=60,
                                    breadth_buy=breadth_buy,
                                    breadth_sell=breadth_sell,
                                    vol_window=vol_window,
                                    vol_max=vol_max,
                                    safety_buy=safety_buy,
                                    safety_sell=safety_sell,
                                    require_pool_mom=require_pool_mom,
                                )
                            )
    return specs


def build_safety_signal_cache(
    asset: pd.DataFrame,
    breadth: pd.DataFrame,
    safety_breadth: pd.Series,
    specs: Iterable[BinaryStrategySpec],
) -> Dict[str, object]:
    spec_list = list(specs)
    idx = asset.index
    close = asset["close"]
    ret = close.pct_change(fill_method=None)
    cache: Dict[str, object] = {
        "index": idx,
        "breadth_ma20": breadth["breadth_ma20"].reindex(idx).ffill().to_numpy(dtype=float),
        "breadth_ma60": breadth["breadth_ma60"].reindex(idx).ffill().to_numpy(dtype=float),
        "pool_ret20_median": breadth["pool_ret20_median"].reindex(idx).ffill().to_numpy(dtype=float),
        "safety_breadth": safety_breadth.reindex(idx).ffill().to_numpy(dtype=float),
    }
    for window in sorted({spec.mom_window for spec in spec_list}):
        cache[f"mom_{window}"] = close.pct_change(window, fill_method=None).to_numpy(dtype=float)
    for window in sorted({spec.vol_window for spec in spec_list}):
        cache[f"volpct_{window}"] = rolling_vol_percentile(ret, window).reindex(idx).to_numpy(dtype=float)
    return cache


def safety_signal_from_cache(cache: Dict[str, object], spec: BinaryStrategySpec) -> pd.Series:
    idx = cache["index"]
    mom = cache[f"mom_{spec.mom_window}"]
    vol_pct = cache[f"volpct_{spec.vol_window}"]
    breadth_ma = cache["breadth_ma60"] if spec.breadth_window >= 60 else cache["breadth_ma20"]
    pool_mom = cache["pool_ret20_median"]
    safety = cache["safety_breadth"]

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
        if spec.safety_buy is not None and spec.safety_sell is not None:
            enter = enter and safety[i] >= spec.safety_buy
            exit_ = exit_ or safety[i] <= spec.safety_sell

        if not held and bool(enter):
            held = True
        elif held and bool(exit_):
            held = False
        desired[i] = 1.0 if held else 0.0
    return pd.Series(desired, index=idx, name=spec.name)


def safety_spec_from_row(row: pd.Series) -> BinaryStrategySpec:
    return BinaryStrategySpec(
        name=str(row["strategy"]),
        mom_window=int(row["mom_window"]),
        breadth_window=int(row.get("breadth_window", 60)),
        breadth_buy=float(row["breadth_buy"]),
        breadth_sell=float(row["breadth_sell"]),
        vol_window=int(row["vol_window"]),
        vol_max=float(row["vol_max"]),
        safety_buy=_maybe_float(row, "safety_buy"),
        safety_sell=_maybe_float(row, "safety_sell"),
        require_pool_mom=_row_bool(row.get("require_pool_mom", False)),
    )


@dataclass(frozen=True)
class GeneralizedStrategySpec:
    family: str
    ma_window: int = 60
    breadth_buy: float = 0.55
    breadth_sell: float = 0.45
    mom_window: int = 60
    vol_window: int = 60
    vol_max: float = 0.80
    rsi_buy: float = 40.0
    rsi_exit: float = 60.0
    require_pool_mom: bool = False

    @property
    def name(self) -> str:
        parts = [
            self.family,
            f"ma{self.ma_window}",
            f"bb{int(self.breadth_buy * 100)}",
            f"bs{int(self.breadth_sell * 100)}",
        ]
        if self.family == "momentum_vol":
            parts.extend(
                [
                    f"mom{self.mom_window}",
                    f"vol{self.vol_window}",
                    f"vp{int(self.vol_max * 100)}",
                ]
            )
        if self.family == "pullback_trend":
            parts.extend([f"rsi{int(self.rsi_buy)}_{int(self.rsi_exit)}"])
        if self.require_pool_mom:
            parts.append("poolmom")
        return "__".join(parts)


def generalized_specs_grid(grid: str = "compact") -> List[GeneralizedStrategySpec]:
    specs: List[GeneralizedStrategySpec] = []
    if grid == "compact":
        for ma in [60, 120]:
            for buy, sell in [(0.50, 0.40), (0.55, 0.45), (0.60, 0.50)]:
                for require_mom in [False, True]:
                    specs.append(
                        GeneralizedStrategySpec(
                            "trend_breadth",
                            ma_window=ma,
                            breadth_buy=buy,
                            breadth_sell=sell,
                            require_pool_mom=require_mom,
                        )
                    )
        for mom in [60, 120]:
            for buy, sell in [(0.50, 0.40), (0.55, 0.45)]:
                for vol_max in [0.80, 0.90]:
                    specs.append(
                        GeneralizedStrategySpec(
                            "momentum_vol",
                            ma_window=60,
                            breadth_buy=buy,
                            breadth_sell=sell,
                            mom_window=mom,
                            vol_window=60,
                            vol_max=vol_max,
                        )
                    )
        for buy, sell in [(0.50, 0.40), (0.55, 0.45)]:
            for rsi_buy_value, rsi_exit_value in [(35, 55), (40, 60)]:
                specs.append(
                    GeneralizedStrategySpec(
                        "pullback_trend",
                        ma_window=60,
                        breadth_buy=buy,
                        breadth_sell=sell,
                        rsi_buy=rsi_buy_value,
                        rsi_exit=rsi_exit_value,
                    )
                )
        return specs

    breadth_pairs = [
        (0.45, 0.35),
        (0.50, 0.35),
        (0.50, 0.40),
        (0.55, 0.40),
        (0.55, 0.45),
        (0.60, 0.45),
        (0.60, 0.50),
        (0.65, 0.50),
    ]
    for ma in [20, 40, 60, 90, 120, 180, 240]:
        for buy, sell in breadth_pairs:
            for require_mom in [False, True]:
                specs.append(
                    GeneralizedStrategySpec(
                        "trend_breadth",
                        ma_window=ma,
                        breadth_buy=buy,
                        breadth_sell=sell,
                        require_pool_mom=require_mom,
                    )
                )
    for mom in [20, 40, 60, 90, 120, 180]:
        for vol_window in [20, 40, 60, 120]:
            for vol_max in [0.60, 0.70, 0.80, 0.90, 0.95]:
                for buy, sell in breadth_pairs:
                    for require_mom in [False, True]:
                        specs.append(
                            GeneralizedStrategySpec(
                                "momentum_vol",
                                ma_window=60,
                                breadth_buy=buy,
                                breadth_sell=sell,
                                mom_window=mom,
                                vol_window=vol_window,
                                vol_max=vol_max,
                                require_pool_mom=require_mom,
                            )
                        )
    for ma in [20, 60, 90, 120, 180]:
        for buy, sell in breadth_pairs:
            for rsi_buy_value, rsi_exit_value in [(25, 50), (30, 55), (35, 60), (40, 65)]:
                specs.append(
                    GeneralizedStrategySpec(
                        "pullback_trend",
                        ma_window=ma,
                        breadth_buy=buy,
                        breadth_sell=sell,
                        rsi_buy=rsi_buy_value,
                        rsi_exit=rsi_exit_value,
                    )
                )
    return specs


def generalized_signal(
    asset: pd.DataFrame,
    breadth: pd.DataFrame,
    spec: GeneralizedStrategySpec,
) -> pd.Series:
    idx = asset.index
    close = asset["close"]
    ret = close.pct_change(fill_method=None)
    ma = close.rolling(spec.ma_window).mean()
    trend = close > ma
    breadth_ma = breadth["breadth_ma60" if spec.ma_window >= 60 else "breadth_ma20"].reindex(idx).ffill()
    pool_mom = breadth["pool_ret20_median"].reindex(idx).ffill()
    mom = close.pct_change(spec.mom_window, fill_method=None)
    vol_pct = rolling_vol_percentile(ret, spec.vol_window).reindex(idx)
    rsi14 = rsi_series(close).reindex(idx)

    desired = pd.Series(0, index=idx, dtype=float)
    held = False
    for dt in idx:
        if spec.family == "trend_breadth":
            enter = trend.loc[dt] and breadth_ma.loc[dt] >= spec.breadth_buy
            if spec.require_pool_mom:
                enter = enter and pool_mom.loc[dt] > 0
            exit_ = (not trend.loc[dt]) or breadth_ma.loc[dt] <= spec.breadth_sell
        elif spec.family == "momentum_vol":
            enter = (
                mom.loc[dt] > 0
                and breadth_ma.loc[dt] >= spec.breadth_buy
                and vol_pct.loc[dt] <= spec.vol_max
            )
            if spec.require_pool_mom:
                enter = enter and pool_mom.loc[dt] > 0
            exit_ = (
                mom.loc[dt] <= 0
                or breadth_ma.loc[dt] <= spec.breadth_sell
                or vol_pct.loc[dt] > min(spec.vol_max + 0.10, 0.98)
            )
        elif spec.family == "pullback_trend":
            enter = (
                trend.loc[dt]
                and breadth_ma.loc[dt] >= spec.breadth_buy
                and rsi14.loc[dt] <= spec.rsi_buy
            )
            exit_ = (
                (not trend.loc[dt])
                or breadth_ma.loc[dt] <= spec.breadth_sell
                or rsi14.loc[dt] >= spec.rsi_exit
            )
        else:
            raise ValueError(f"Unknown strategy family: {spec.family}")

        if not held and bool(enter):
            held = True
        elif held and bool(exit_):
            held = False
        desired.loc[dt] = 1.0 if held else 0.0
    return desired


def build_generalized_indicator_cache(
    assets: Dict[str, pd.DataFrame],
    breadth: pd.DataFrame,
    specs: Iterable[GeneralizedStrategySpec],
) -> Dict[str, pd.DataFrame]:
    spec_list = list(specs)
    ma_windows = sorted({spec.ma_window for spec in spec_list})
    mom_windows = sorted({spec.mom_window for spec in spec_list})
    vol_windows = sorted({spec.vol_window for spec in spec_list})
    cache: Dict[str, pd.DataFrame] = {}
    for code, asset in assets.items():
        idx = asset.index
        close = asset["close"]
        ret = close.pct_change(fill_method=None)
        indicators = pd.DataFrame(index=idx)
        for window in ma_windows:
            indicators[f"trend_ma{window}"] = close > close.rolling(window).mean()
        for window in mom_windows:
            indicators[f"mom{window}"] = close.pct_change(window, fill_method=None)
        for window in vol_windows:
            indicators[f"volpct{window}"] = rolling_vol_percentile(ret, window).reindex(idx)
        indicators["rsi14"] = rsi_series(close).reindex(idx)
        indicators["breadth_ma20"] = breadth["breadth_ma20"].reindex(idx).ffill()
        indicators["breadth_ma60"] = breadth["breadth_ma60"].reindex(idx).ffill()
        indicators["pool_ret20_median"] = breadth["pool_ret20_median"].reindex(idx).ffill()
        cache[code] = indicators
    return cache


def generalized_signal_from_indicators(
    indicators: pd.DataFrame,
    spec: GeneralizedStrategySpec,
) -> pd.Series:
    idx = indicators.index
    trend = indicators[f"trend_ma{spec.ma_window}"].fillna(False).to_numpy(dtype=bool)
    breadth_ma = indicators["breadth_ma60" if spec.ma_window >= 60 else "breadth_ma20"].to_numpy(dtype=float)
    pool_mom = indicators["pool_ret20_median"].to_numpy(dtype=float)
    mom = indicators[f"mom{spec.mom_window}"].to_numpy(dtype=float)
    vol_pct = indicators[f"volpct{spec.vol_window}"].to_numpy(dtype=float)
    rsi14 = indicators["rsi14"].to_numpy(dtype=float)

    desired = np.zeros(len(idx), dtype=float)
    held = False
    for i in range(len(idx)):
        if spec.family == "trend_breadth":
            enter = trend[i] and breadth_ma[i] >= spec.breadth_buy
            if spec.require_pool_mom:
                enter = enter and pool_mom[i] > 0
            exit_ = (not trend[i]) or breadth_ma[i] <= spec.breadth_sell
        elif spec.family == "momentum_vol":
            enter = (
                mom[i] > 0
                and breadth_ma[i] >= spec.breadth_buy
                and vol_pct[i] <= spec.vol_max
            )
            if spec.require_pool_mom:
                enter = enter and pool_mom[i] > 0
            exit_ = (
                mom[i] <= 0
                or breadth_ma[i] <= spec.breadth_sell
                or vol_pct[i] > min(spec.vol_max + 0.10, 0.98)
            )
        elif spec.family == "pullback_trend":
            enter = (
                trend[i]
                and breadth_ma[i] >= spec.breadth_buy
                and rsi14[i] <= spec.rsi_buy
            )
            exit_ = (not trend[i]) or breadth_ma[i] <= spec.breadth_sell or rsi14[i] >= spec.rsi_exit
        else:
            raise ValueError(f"Unknown strategy family: {spec.family}")

        if not held and bool(enter):
            held = True
        elif held and bool(exit_):
            held = False
        desired[i] = 1.0 if held else 0.0
    return pd.Series(desired, index=idx, dtype=float)


@dataclass(frozen=True)
class LongRunStrategySpec:
    family: str
    name: str
    mom_window: int = 60
    breadth_buy: float = 0.65
    breadth_sell: float = 0.50
    vol_window: int = 20
    vol_max: float = 0.95
    factor_signal: Optional[str] = None
    factor_buy: Optional[float] = None
    factor_sell: Optional[float] = None
    require_pool_mom: bool = False


def make_longrun_specs(factor_signals: Iterable[str]) -> List[LongRunStrategySpec]:
    specs: List[LongRunStrategySpec] = []
    specs.append(LongRunStrategySpec("baseline", "baseline_prev_best__mom60__bb65__bs50__vol20__vp95"))

    for mom in [20, 60, 120]:
        for buy, sell in [(0.55, 0.45), (0.60, 0.50), (0.65, 0.50)]:
            for vol_window in [20, 60, 120]:
                for vol_max in [0.80, 0.90, 0.95]:
                    name = f"base_mv__mom{mom}__bb{int(buy * 100)}__bs{int(sell * 100)}__vol{vol_window}__vp{int(vol_max * 100)}"
                    specs.append(LongRunStrategySpec("base_momentum_vol", name, mom, buy, sell, vol_window, vol_max))

    for factor in factor_signals:
        for mom in [20, 60, 120]:
            for vol_window in [20, 120]:
                for vol_max in [0.90, 0.95]:
                    for fbuy, fsell in [(0.50, 0.40), (0.55, 0.45), (0.60, 0.50)]:
                        for require_pool_mom in [False, True]:
                            name = (
                                f"factor_overlay__{factor}__mom{mom}__vol{vol_window}"
                                f"__vp{int(vol_max * 100)}__fb{int(fbuy * 100)}__fs{int(fsell * 100)}"
                            )
                            if require_pool_mom:
                                name += "__poolmom"
                            specs.append(
                                LongRunStrategySpec(
                                    family="factor_overlay",
                                    name=name,
                                    mom_window=mom,
                                    breadth_buy=0.65,
                                    breadth_sell=0.50,
                                    vol_window=vol_window,
                                    vol_max=vol_max,
                                    factor_signal=factor,
                                    factor_buy=fbuy,
                                    factor_sell=fsell,
                                    require_pool_mom=require_pool_mom,
                                )
                            )
    return specs


def build_longrun_signal_cache(
    asset: pd.DataFrame,
    breadth: pd.DataFrame,
    factor_breadths: Dict[str, pd.Series],
    specs: Iterable[LongRunStrategySpec],
) -> Dict[str, object]:
    spec_list = list(specs)
    idx = asset.index
    close = asset["close"]
    ret = close.pct_change(fill_method=None)
    cache: Dict[str, object] = {
        "index": idx,
        "breadth_ma60": breadth["breadth_ma60"].reindex(idx).ffill().to_numpy(dtype=float),
        "pool_ret20_median": breadth["pool_ret20_median"].reindex(idx).ffill().to_numpy(dtype=float),
        "factors": {
            name: series.reindex(idx).ffill().to_numpy(dtype=float)
            for name, series in factor_breadths.items()
        },
    }
    for window in sorted({spec.mom_window for spec in spec_list}):
        cache[f"mom_{window}"] = close.pct_change(window, fill_method=None).to_numpy(dtype=float)
    for window in sorted({spec.vol_window for spec in spec_list}):
        cache[f"volpct_{window}"] = rolling_vol_percentile(ret, window).reindex(idx).to_numpy(dtype=float)
    return cache


def longrun_signal_from_cache(cache: Dict[str, object], spec: LongRunStrategySpec) -> pd.Series:
    idx = cache["index"]
    mom = cache[f"mom_{spec.mom_window}"]
    vol_pct = cache[f"volpct_{spec.vol_window}"]
    breadth_ma = cache["breadth_ma60"]
    pool_mom = cache["pool_ret20_median"]
    factor_values = cache["factors"].get(spec.factor_signal) if spec.factor_signal else None
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
        if factor_values is not None and spec.factor_buy is not None and spec.factor_sell is not None:
            enter = enter and factor_values[i] >= spec.factor_buy
            exit_ = exit_ or factor_values[i] <= spec.factor_sell

        if not held and bool(enter):
            held = True
        elif held and bool(exit_):
            held = False
        desired[i] = 1.0 if held else 0.0
    return pd.Series(desired, index=idx, name=spec.name)


def longrun_spec_from_row(row: pd.Series) -> LongRunStrategySpec:
    return LongRunStrategySpec(
        family=str(row["family"]),
        name=str(row["strategy"]),
        mom_window=int(row["mom_window"]),
        breadth_buy=float(row["breadth_buy"]),
        breadth_sell=float(row["breadth_sell"]),
        vol_window=int(row["vol_window"]),
        vol_max=float(row["vol_max"]),
        factor_signal=str(row["factor_signal"]) if pd.notna(row["factor_signal"]) else None,
        factor_buy=_maybe_float(row, "factor_buy"),
        factor_sell=_maybe_float(row, "factor_sell"),
        require_pool_mom=_row_bool(row.get("require_pool_mom", False)),
    )


@dataclass(frozen=True)
class TD9ComboSpec:
    name: str
    td9_signal: str
    td9_buy: float
    td9_sell: float
    trend_rule: str
    breadth_buy: Optional[float] = None
    breadth_sell: Optional[float] = None
    vol_window: Optional[int] = None
    vol_max: Optional[float] = None
    require_pool_mom: bool = False
    boll_rule: str = "none"
    vix_rule: str = "none"
    family: str = "td9_indicator_combo"


def make_td9_combo_specs(factor_breadths: Dict[str, pd.Series]) -> List[TD9ComboSpec]:
    td9_candidates = [
        "alpha_td9_sell_pressure_4_9",
        "alpha_td9_buy_setup_4_9",
        "combo2__alpha_intraday_strength_60__alpha_td9_sell_pressure_4_9",
        "combo_td9_lowrisk",
    ]
    td9_signals = [name for name in td9_candidates if name in factor_breadths]
    thresholds = [(0.50, 0.40), (0.55, 0.45), (0.60, 0.50)]
    trends = ["mom20", "mom60", "mom120", "close_ma60", "cross5_20", "cross5_60", "cross20_60"]
    breadth_sets: List[Tuple[Optional[float], Optional[float], str]] = [
        (None, None, "nobb"),
        (0.55, 0.45, "bb55_bs45"),
        (0.65, 0.50, "bb65_bs50"),
    ]
    vol_sets: List[Tuple[Optional[int], Optional[float], str]] = [
        (None, None, "novol"),
        (20, 0.95, "vol20_vp95"),
        (120, 0.90, "vol120_vp90"),
    ]
    boll_rules = ["none", "boll20_mid_not_extreme", "boll60_mid_not_extreme"]
    vix_rules = ["none", "vix_lt25", "vix_lt30", "vix_below_ma20"]
    specs: List[TD9ComboSpec] = []
    for td9 in td9_signals:
        for td9_buy, td9_sell in thresholds:
            for trend in trends:
                for breadth_buy, breadth_sell, breadth_tag in breadth_sets:
                    for vol_window, vol_max, vol_tag in vol_sets:
                        for poolmom in [False, True]:
                            for boll in boll_rules:
                                for vix in vix_rules:
                                    name = "__".join(
                                        [
                                            "td9_combo",
                                            td9,
                                            trend,
                                            f"td{int(td9_buy * 100)}_{int(td9_sell * 100)}",
                                            breadth_tag,
                                            vol_tag,
                                            "poolmom" if poolmom else "nopoolmom",
                                            boll,
                                            vix,
                                        ]
                                    )
                                    specs.append(
                                        TD9ComboSpec(
                                            name=name,
                                            td9_signal=td9,
                                            td9_buy=td9_buy,
                                            td9_sell=td9_sell,
                                            trend_rule=trend,
                                            breadth_buy=breadth_buy,
                                            breadth_sell=breadth_sell,
                                            vol_window=vol_window,
                                            vol_max=vol_max,
                                            require_pool_mom=poolmom,
                                            boll_rule=boll,
                                            vix_rule=vix,
                                        )
                                    )
    return specs


def td9_combo_spec_from_row(row: pd.Series) -> TD9ComboSpec:
    return TD9ComboSpec(
        name=str(row["strategy"]),
        td9_signal=str(row["td9_signal"]),
        td9_buy=float(row["td9_buy"]),
        td9_sell=float(row["td9_sell"]),
        trend_rule=str(row["trend_rule"]),
        breadth_buy=_maybe_float(row, "breadth_buy"),
        breadth_sell=_maybe_float(row, "breadth_sell"),
        vol_window=_maybe_int(row, "vol_window"),
        vol_max=_maybe_float(row, "vol_max"),
        require_pool_mom=_row_bool(row.get("require_pool_mom", False)),
        boll_rule=str(row["boll_rule"]),
        vix_rule=str(row["vix_rule"]),
        family=str(row.get("family", "td9_indicator_combo")),
    )


def td9_windows_from_specs(specs: Iterable[TD9ComboSpec]) -> Tuple[set[int], set[int]]:
    ma_windows = {20, 60}
    vol_windows: set[int] = set()
    for spec in specs:
        if spec.vol_window:
            vol_windows.add(spec.vol_window)
        rule = spec.trend_rule
        if rule.startswith("mom"):
            ma_windows.add(int(rule.replace("mom", "")))
        elif rule.startswith("close_ma"):
            ma_windows.add(int(rule.replace("close_ma", "")))
        elif rule.startswith("cross"):
            left, right = rule.replace("cross", "").split("_")
            ma_windows.update([int(left), int(right)])
    return ma_windows, vol_windows


def build_td9_combo_cache(
    asset: pd.DataFrame,
    breadth: pd.DataFrame,
    factor_breadths: Dict[str, pd.Series],
    vix: pd.DataFrame,
    specs: List[TD9ComboSpec],
) -> Dict[str, object]:
    idx = asset.index
    close = asset["close"]
    ret = close.pct_change(fill_method=None)
    ma_windows, vol_windows = td9_windows_from_specs(specs)
    cache: Dict[str, object] = {
        "index": idx,
        "close": close.to_numpy(dtype=float),
        "breadth_ma60": breadth["breadth_ma60"].reindex(idx).ffill().to_numpy(dtype=float),
        "pool_ret20_median": breadth["pool_ret20_median"].reindex(idx).ffill().to_numpy(dtype=float),
        "td9": {
            name: series.reindex(idx).ffill().to_numpy(dtype=float)
            for name, series in factor_breadths.items()
            if "td9" in name
        },
        "vix_close": vix.get("vix_close", pd.Series(np.nan, index=idx)).reindex(idx).ffill().to_numpy(dtype=float),
        "vix_ma20": vix.get("vix_ma20", pd.Series(np.nan, index=idx)).reindex(idx).ffill().to_numpy(dtype=float),
        "vix_chg5": vix.get("vix_chg5", pd.Series(np.nan, index=idx)).reindex(idx).ffill().to_numpy(dtype=float),
    }
    for window in sorted(ma_windows):
        cache[f"mom{window}"] = close.pct_change(window, fill_method=None).to_numpy(dtype=float)
        cache[f"ma{window}"] = close.rolling(window).mean().to_numpy(dtype=float)
    for window in sorted(vol_windows):
        cache[f"volpct{window}"] = rolling_vol_percentile(ret, window).reindex(idx).to_numpy(dtype=float)
    for window in [20, 60]:
        mid = close.rolling(window).mean()
        std = close.rolling(window).std()
        cache[f"boll{window}_mid"] = mid.to_numpy(dtype=float)
        cache[f"boll{window}_pos"] = close.sub(mid).div(2 * std.replace(0, np.nan)).to_numpy(dtype=float)
    return cache


def td9_trend_ok(cache: Dict[str, object], rule: str, i: int) -> Tuple[bool, bool]:
    if rule.startswith("mom"):
        value = cache[rule][i]
        return bool(value > 0), bool(value <= 0)
    if rule.startswith("close_ma"):
        window = rule.replace("close_ma", "")
        close = cache["close"][i]
        ma = cache[f"ma{window}"][i]
        return bool(close > ma), bool(close <= ma)
    if rule.startswith("cross"):
        left, right = rule.replace("cross", "").split("_")
        fast = cache[f"ma{left}"][i]
        slow = cache[f"ma{right}"][i]
        return bool(fast > slow), bool(fast <= slow)
    raise ValueError(f"Unknown trend rule: {rule}")


def td9_boll_ok(cache: Dict[str, object], rule: str, i: int) -> Tuple[bool, bool]:
    if rule == "none":
        return True, False
    window = 20 if rule.startswith("boll20") else 60
    close = cache["close"][i]
    mid = cache[f"boll{window}_mid"][i]
    pos = cache[f"boll{window}_pos"][i]
    return bool(close > mid and pos <= 0.90), bool(close <= mid or pos > 1.10)


def td9_vix_ok(cache: Dict[str, object], rule: str, i: int) -> Tuple[bool, bool]:
    if rule == "none":
        return True, False
    close = cache["vix_close"][i]
    ma20 = cache["vix_ma20"][i]
    if np.isnan(close):
        return False, True
    if rule == "vix_lt25":
        return bool(close < 25), bool(close > 30)
    if rule == "vix_lt30":
        return bool(close < 30), bool(close > 35)
    if rule == "vix_below_ma20":
        return bool(close < ma20), bool(close > ma20 * 1.05)
    raise ValueError(f"Unknown VIX rule: {rule}")


def td9_combo_signal_from_cache(cache: Dict[str, object], spec: TD9ComboSpec) -> pd.Series:
    idx = cache["index"]
    td9 = cache["td9"][spec.td9_signal]
    breadth = cache["breadth_ma60"]
    pool_mom = cache["pool_ret20_median"]
    desired = np.zeros(len(idx), dtype=float)
    held = False
    for i in range(len(idx)):
        trend_enter, trend_exit = td9_trend_ok(cache, spec.trend_rule, i)
        boll_enter, boll_exit = td9_boll_ok(cache, spec.boll_rule, i)
        vix_enter, vix_exit = td9_vix_ok(cache, spec.vix_rule, i)
        enter = td9[i] >= spec.td9_buy and trend_enter and boll_enter and vix_enter
        exit_ = td9[i] <= spec.td9_sell or trend_exit or boll_exit or vix_exit
        if spec.breadth_buy is not None and spec.breadth_sell is not None:
            enter = enter and breadth[i] >= spec.breadth_buy
            exit_ = exit_ or breadth[i] <= spec.breadth_sell
        if spec.vol_window is not None and spec.vol_max is not None:
            vol = cache[f"volpct{spec.vol_window}"][i]
            enter = enter and vol <= spec.vol_max
            exit_ = exit_ or vol > min(spec.vol_max + 0.10, 0.98)
        if spec.require_pool_mom:
            enter = enter and pool_mom[i] > 0
            exit_ = exit_ or pool_mom[i] <= 0
        if not held and bool(enter):
            held = True
        elif held and bool(exit_):
            held = False
        desired[i] = 1.0 if held else 0.0
    return pd.Series(desired, index=idx, name=spec.name)
