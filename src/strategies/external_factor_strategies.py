"""Reusable strategy helpers for external factor panels."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ExternalFactorRankStrategySpec:
    """Cross-sectional long/flat rank strategy over a factor panel."""

    name: str
    factor_name: str
    top_quantile: float = 0.2
    direction: str = "high"
    signal_lag: int = 1


@dataclass(frozen=True)
class ExternalFactorThresholdStrategySpec:
    """Time-series threshold strategy over one factor series."""

    name: str
    factor_name: str
    buy_threshold: float
    sell_threshold: float
    direction: str = "high"
    signal_lag: int = 1


def _validate_direction(direction: str) -> None:
    if direction not in {"high", "low"}:
        raise ValueError("direction must be 'high' or 'low'")


def zscore_factor_panel(panel: pd.DataFrame) -> pd.DataFrame:
    """Row-wise z-score a date x asset factor panel."""

    mean = panel.mean(axis=1)
    std = panel.std(axis=1).replace(0.0, np.nan)
    return panel.sub(mean, axis=0).div(std, axis=0)


def combine_factor_panels(
    panels: Mapping[str, pd.DataFrame],
    weights: Mapping[str, float] | None = None,
    standardize: bool = True,
) -> pd.DataFrame:
    """Create a weighted composite factor panel from aligned panels."""

    if not panels:
        raise ValueError("No factor panels supplied.")

    if weights is None:
        weights = {name: 1.0 for name in panels}

    composite: pd.DataFrame | None = None
    for name, panel in panels.items():
        weight = float(weights.get(name, 0.0))
        if weight == 0.0:
            continue
        values = zscore_factor_panel(panel) if standardize else panel
        composite = values.mul(weight) if composite is None else composite.add(values.mul(weight), fill_value=np.nan)

    if composite is None:
        raise ValueError("All factor weights are zero.")

    return composite


def rank_signal_from_factor_panel(
    factor_panel: pd.DataFrame,
    spec: ExternalFactorRankStrategySpec,
) -> pd.DataFrame:
    """Return a date x asset binary long/flat signal from factor ranks."""

    _validate_direction(spec.direction)
    if not 0 < spec.top_quantile <= 1:
        raise ValueError("top_quantile must be in (0, 1].")
    if spec.signal_lag < 0:
        raise ValueError("signal_lag must be non-negative.")

    pct_rank = factor_panel.rank(axis=1, pct=True)
    if spec.direction == "high":
        signal = pct_rank > (1.0 - spec.top_quantile)
    else:
        signal = pct_rank <= spec.top_quantile

    result = signal.astype(float)
    if spec.signal_lag:
        result = result.shift(spec.signal_lag)
    return result.fillna(0.0)


def threshold_signal_from_factor_series(
    factor_series: pd.Series,
    spec: ExternalFactorThresholdStrategySpec,
) -> pd.Series:
    """Return a binary timing signal from buy/sell factor thresholds."""

    _validate_direction(spec.direction)
    if spec.signal_lag < 0:
        raise ValueError("signal_lag must be non-negative.")

    values = factor_series.astype(float)
    signal = pd.Series(0.0, index=values.index)
    position = 0.0

    for i, value in enumerate(values.to_numpy(dtype=float)):
        if np.isnan(value):
            signal.iloc[i] = position
            continue

        if spec.direction == "high":
            if value >= spec.buy_threshold:
                position = 1.0
            elif value <= spec.sell_threshold:
                position = 0.0
        else:
            if value <= spec.buy_threshold:
                position = 1.0
            elif value >= spec.sell_threshold:
                position = 0.0

        signal.iloc[i] = position

    if spec.signal_lag:
        signal = signal.shift(spec.signal_lag)
    return signal.fillna(0.0)


def signal_breadth(signal_panel: pd.DataFrame) -> pd.Series:
    """Share of assets selected by a binary date x asset signal panel."""

    return signal_panel.astype(float).mean(axis=1)
