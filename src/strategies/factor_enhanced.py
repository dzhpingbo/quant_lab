"""Factor-enhanced portfolio construction strategies.

The helpers in this module turn broad factor panels into target-weight
matrices that can be passed to `PortfolioFactory.run_weighted_portfolio_simple`.
They are intentionally model-light: the goal is to expose more of the existing
factor library through better portfolio construction, not to force one ML stack.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Mapping, Optional, Sequence

import numpy as np
import pandas as pd


STRATEGY_RESEARCH_SOURCES = (
    {
        "name": "Qlib TopkDropoutStrategy",
        "url": "https://qlib.readthedocs.io/en/latest/component/strategy.html",
        "applied_as": "top-k selection with controlled dropout turnover",
    },
    {
        "name": "Alphalens factor weights and quantile analysis",
        "url": "https://quantopian.github.io/alphalens/alphalens.html",
        "applied_as": "demeaned factor-score portfolio weights and quantile portfolios",
    },
    {
        "name": "Cross-sectional momentum",
        "url": "https://www.bauer.uh.edu/rsusmel/phd/jegadeesh-titman93.pdf",
        "applied_as": "rank winners versus losers and rebalance periodically",
    },
    {
        "name": "Time-series momentum",
        "url": "https://pages.stern.nyu.edu/~lpederse/papers/TimeSeriesMomentum.pdf",
        "applied_as": "absolute momentum overlay for long/cash risk gating",
    },
    {
        "name": "Fama-French factor families",
        "url": "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html",
        "applied_as": "value, size, profitability, investment, and momentum blend template",
    },
)


@dataclass(frozen=True)
class FactorBlendSpec:
    """How to normalize and combine multiple date x asset factor panels."""

    name: str = "factor_blend"
    weights: Optional[Mapping[str, float]] = None
    directions: Optional[Mapping[str, object]] = None
    normalize: str = "rank_zscore"
    winsor_quantile: Optional[float] = 0.01
    group_neutral: bool = False


@dataclass(frozen=True)
class QuantilePortfolioSpec:
    """Parameters for a factor quantile long-only or long/short portfolio."""

    name: str = "factor_quantile"
    long_quantile: float = 0.2
    short_quantile: float = 0.0
    weighting: str = "equal"
    gross_exposure: float = 1.0
    market_neutral: bool = False
    max_abs_weight: Optional[float] = None


@dataclass(frozen=True)
class TopKDropoutSpec:
    """Qlib-inspired top-k portfolio with limited rebalance turnover."""

    name: str = "topk_dropout"
    top_k: int = 50
    n_drop: int = 5
    rebalance_freq: str = "D"
    gross_exposure: float = 1.0
    force_drop: bool = False


@dataclass(frozen=True)
class TimeSeriesOverlaySpec:
    """Per-asset timing filters applied on top of cross-sectional weights."""

    name: str = "ts_overlay"
    momentum_window: Optional[int] = None
    min_momentum: float = 0.0
    ma_window: Optional[int] = None
    vol_window: Optional[int] = None
    max_annual_vol: Optional[float] = None
    renormalize: bool = True


def _panel_shape(panels: Mapping[str, pd.DataFrame]) -> tuple[pd.Index, pd.Index]:
    if not panels:
        raise ValueError("No factor panels supplied.")

    iterator = iter(panels.values())
    first = next(iterator)
    index = first.index
    columns = first.columns
    for panel in iterator:
        index = index.union(panel.index)
        columns = columns.union(panel.columns)
    return index, columns


def align_factor_panels(panels: Mapping[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    """Align factor panels to a common date x asset shape."""

    index, columns = _panel_shape(panels)
    return {
        name: panel.reindex(index=index, columns=columns).astype(float)
        for name, panel in panels.items()
    }


def winsorize_panel(panel: pd.DataFrame, quantile: Optional[float] = 0.01) -> pd.DataFrame:
    """Row-wise winsorization to reduce single-name outlier dominance."""

    if quantile is None or quantile <= 0:
        return panel.replace([np.inf, -np.inf], np.nan)
    if quantile >= 0.5:
        raise ValueError("quantile must be smaller than 0.5")

    clean = panel.replace([np.inf, -np.inf], np.nan)
    lower = clean.quantile(quantile, axis=1)
    upper = clean.quantile(1.0 - quantile, axis=1)
    return clean.clip(lower=lower, upper=upper, axis=0)


def cross_section_zscore(panel: pd.DataFrame) -> pd.DataFrame:
    """Row-wise z-score normalization."""

    mean = panel.mean(axis=1)
    std = panel.std(axis=1).replace(0.0, np.nan)
    return panel.sub(mean, axis=0).div(std, axis=0)


def rank_normalize_panel(panel: pd.DataFrame, center: bool = True) -> pd.DataFrame:
    """Convert raw values to row-wise percentile ranks."""

    rank = panel.rank(axis=1, pct=True)
    if center:
        return rank.mul(2.0).sub(1.0)
    return rank


def neutralize_panel_by_group(
    panel: pd.DataFrame,
    groups: Mapping[str, object] | pd.Series,
) -> pd.DataFrame:
    """Subtract each row's group mean from assets in that group."""

    group_series = pd.Series(groups).reindex(panel.columns)
    known = group_series.dropna()
    if known.empty:
        return panel

    result = panel.copy()
    for _group, cols in known.groupby(known).groups.items():
        col_list = list(cols)
        result.loc[:, col_list] = result.loc[:, col_list].sub(
            result.loc[:, col_list].mean(axis=1),
            axis=0,
        )
    return result


def normalize_factor_panel(
    panel: pd.DataFrame,
    method: str = "rank_zscore",
    winsor_quantile: Optional[float] = 0.01,
    groups: Optional[Mapping[str, object] | pd.Series] = None,
    group_neutral: bool = False,
) -> pd.DataFrame:
    """Normalize one factor panel for cross-sectional combination."""

    clean = winsorize_panel(panel, winsor_quantile)
    if method == "raw":
        normalized = clean
    elif method == "rank":
        normalized = rank_normalize_panel(clean)
    elif method == "zscore":
        normalized = cross_section_zscore(clean)
    elif method == "rank_zscore":
        normalized = cross_section_zscore(rank_normalize_panel(clean))
    else:
        raise ValueError("method must be one of raw, rank, zscore, rank_zscore")

    if group_neutral:
        if groups is None:
            raise ValueError("groups are required when group_neutral=True")
        normalized = neutralize_panel_by_group(normalized, groups)
        normalized = cross_section_zscore(normalized)

    return normalized.replace([np.inf, -np.inf], np.nan)


def _direction_multiplier(value: object) -> float:
    if value in (-1, "-1", "low", "lower", "inverse", "short"):
        return -1.0
    return 1.0


def combine_enhanced_factor_panels(
    panels: Mapping[str, pd.DataFrame],
    spec: Optional[FactorBlendSpec] = None,
    groups: Optional[Mapping[str, object] | pd.Series] = None,
) -> pd.DataFrame:
    """Create a robust weighted composite factor score."""

    aligned = align_factor_panels(panels)
    spec = spec or FactorBlendSpec()
    weights = spec.weights or {name: 1.0 for name in aligned}
    directions = spec.directions or {}

    composite: Optional[pd.DataFrame] = None
    abs_weight_sum = 0.0
    for name, panel in aligned.items():
        if spec.weights is not None and name not in spec.weights:
            continue

        weight = float(weights.get(name, 0.0))
        if weight == 0.0:
            continue

        normalized = normalize_factor_panel(
            panel,
            method=spec.normalize,
            winsor_quantile=spec.winsor_quantile,
            groups=groups,
            group_neutral=spec.group_neutral,
        )
        signed_weight = weight * _direction_multiplier(directions.get(name, 1))
        contribution = normalized.mul(signed_weight)
        composite = contribution if composite is None else composite.add(contribution, fill_value=0.0)
        abs_weight_sum += abs(weight)

    if composite is None or abs_weight_sum == 0.0:
        raise ValueError("No non-zero factor weights were supplied.")

    return composite.div(abs_weight_sum)


def factor_ic_series(
    factor_panel: pd.DataFrame,
    forward_returns: pd.DataFrame,
    method: str = "spearman",
    min_assets: int = 5,
) -> pd.Series:
    """Cross-sectional IC series between one factor and future returns."""

    factor_panel = factor_panel.reindex_like(forward_returns)
    out = pd.Series(np.nan, index=forward_returns.index, dtype=float)
    for date in forward_returns.index:
        f = factor_panel.loc[date]
        r = forward_returns.loc[date]
        valid = f.notna() & r.notna()
        if int(valid.sum()) < min_assets:
            continue
        if method in {"spearman", "rank"}:
            out.loc[date] = f[valid].rank().corr(r[valid].rank())
        elif method == "pearson":
            out.loc[date] = f[valid].corr(r[valid])
        else:
            raise ValueError("method must be spearman/rank or pearson")
    return out


def rolling_ic_weights(
    panels: Mapping[str, pd.DataFrame],
    forward_returns: pd.DataFrame,
    lookback: int = 60,
    min_periods: int = 20,
    ic_lag: int = 1,
    method: str = "spearman",
    positive_only: bool = False,
    fallback_equal: bool = True,
) -> pd.DataFrame:
    """Estimate rolling IC weights using only lagged IC observations."""

    if lookback <= 0:
        raise ValueError("lookback must be positive")
    if min_periods <= 0:
        raise ValueError("min_periods must be positive")
    if ic_lag < 0:
        raise ValueError("ic_lag must be non-negative")

    aligned = align_factor_panels(panels)
    ic_columns = {}
    for name, panel in aligned.items():
        ic = factor_ic_series(panel, forward_returns, method=method)
        ic_columns[name] = ic.rolling(lookback, min_periods=min_periods).mean().shift(ic_lag)

    raw = pd.DataFrame(ic_columns).reindex(forward_returns.index)
    if positive_only:
        raw = raw.clip(lower=0.0)

    weights = raw.copy()
    for date in weights.index:
        row = weights.loc[date].replace([np.inf, -np.inf], np.nan).fillna(0.0)
        denom = row.abs().sum()
        if denom > 0:
            weights.loc[date] = row / denom
        elif fallback_equal and len(row) > 0:
            weights.loc[date] = 1.0 / len(row)
        else:
            weights.loc[date] = 0.0

    return weights


def ic_weighted_composite(
    panels: Mapping[str, pd.DataFrame],
    forward_returns: pd.DataFrame,
    blend_spec: Optional[FactorBlendSpec] = None,
    lookback: int = 60,
    min_periods: int = 20,
    ic_lag: int = 1,
    method: str = "spearman",
    positive_only: bool = False,
    groups: Optional[Mapping[str, object] | pd.Series] = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Create a dynamic composite score and return both score and IC weights."""

    aligned = align_factor_panels(panels)
    blend_spec = blend_spec or FactorBlendSpec()
    ic_weights = rolling_ic_weights(
        aligned,
        forward_returns=forward_returns,
        lookback=lookback,
        min_periods=min_periods,
        ic_lag=ic_lag,
        method=method,
        positive_only=positive_only,
    )

    score = pd.DataFrame(0.0, index=forward_returns.index, columns=forward_returns.columns)
    directions = blend_spec.directions or {}
    for name, panel in aligned.items():
        normalized = normalize_factor_panel(
            panel.reindex_like(score),
            method=blend_spec.normalize,
            winsor_quantile=blend_spec.winsor_quantile,
            groups=groups,
            group_neutral=blend_spec.group_neutral,
        )
        direction = _direction_multiplier(directions.get(name, 1))
        score = score.add(normalized.mul(ic_weights[name] * direction, axis=0), fill_value=0.0)

    return score, ic_weights


def _selected_side_weights(
    score_row: pd.Series,
    mask: pd.Series,
    exposure: float,
    weighting: str,
    long_side: bool,
) -> pd.Series:
    weights = pd.Series(0.0, index=score_row.index)
    selected = score_row[mask.fillna(False)].dropna()
    if selected.empty or exposure == 0.0:
        return weights

    if weighting == "equal":
        raw = pd.Series(1.0, index=selected.index)
    elif weighting == "score":
        raw = selected - selected.min() if long_side else selected.max() - selected
        raw = raw.clip(lower=0.0)
        if raw.sum() == 0:
            raw = pd.Series(1.0, index=selected.index)
    elif weighting == "rank":
        raw = selected.rank(method="first") if long_side else selected.rank(ascending=False, method="first")
    else:
        raise ValueError("weighting must be equal, score, or rank")

    raw_sum = raw.sum()
    if raw_sum > 0:
        weights.loc[raw.index] = raw / raw_sum * exposure
    return weights


def _cap_and_gross_normalize(
    weights: pd.DataFrame,
    gross_exposure: float,
    max_abs_weight: Optional[float] = None,
) -> pd.DataFrame:
    capped = weights.copy().replace([np.inf, -np.inf], np.nan).fillna(0.0)
    if max_abs_weight is not None and max_abs_weight > 0:
        capped = capped.clip(lower=-max_abs_weight, upper=max_abs_weight)

    gross = capped.abs().sum(axis=1).replace(0.0, np.nan)
    return capped.div(gross, axis=0).mul(gross_exposure).fillna(0.0)


def quantile_weights_from_score(
    score: pd.DataFrame,
    spec: Optional[QuantilePortfolioSpec] = None,
) -> pd.DataFrame:
    """Convert a factor score panel into long-only or long/short weights."""

    spec = spec or QuantilePortfolioSpec()
    if not 0 < spec.long_quantile <= 1:
        raise ValueError("long_quantile must be in (0, 1]")
    if not 0 <= spec.short_quantile <= 1:
        raise ValueError("short_quantile must be in [0, 1]")

    short_quantile = spec.short_quantile
    if spec.market_neutral and short_quantile == 0.0:
        short_quantile = spec.long_quantile

    valid_count = score.notna().sum(axis=1).astype(float)
    long_count = np.ceil(valid_count * spec.long_quantile).clip(lower=1)
    long_rank = score.rank(axis=1, ascending=False, method="first")
    long_mask = long_rank.le(long_count, axis=0)
    if short_quantile > 0:
        short_count = np.ceil(valid_count * short_quantile).clip(lower=1)
        short_rank = score.rank(axis=1, ascending=True, method="first")
        short_mask = short_rank.le(short_count, axis=0)
    else:
        short_mask = pd.DataFrame(False, index=score.index, columns=score.columns)

    has_short = short_quantile > 0
    long_exposure = spec.gross_exposure / 2.0 if has_short else spec.gross_exposure
    short_exposure = spec.gross_exposure / 2.0 if has_short else 0.0

    out = pd.DataFrame(0.0, index=score.index, columns=score.columns)
    for date in score.index:
        row = score.loc[date]
        weights = _selected_side_weights(
            row,
            long_mask.loc[date],
            exposure=long_exposure,
            weighting=spec.weighting,
            long_side=True,
        )
        if has_short:
            short_weights = _selected_side_weights(
                row,
                short_mask.loc[date],
                exposure=short_exposure,
                weighting=spec.weighting,
                long_side=False,
            )
            weights = weights.sub(short_weights, fill_value=0.0)
        out.loc[date] = weights

    return _cap_and_gross_normalize(out, spec.gross_exposure, spec.max_abs_weight)


def alphalens_style_factor_weights(
    score: pd.DataFrame,
    demeaned: bool = True,
    group_neutral: bool = False,
    groups: Optional[Mapping[str, object] | pd.Series] = None,
    equal_weight: bool = False,
    gross_exposure: float = 1.0,
) -> pd.DataFrame:
    """Alphalens-style factor weights from continuous factor scores."""

    def row_weights(row: pd.Series, exposure: float) -> pd.Series:
        clean = row.replace([np.inf, -np.inf], np.nan).dropna().astype(float)
        out = pd.Series(0.0, index=row.index)
        if clean.empty:
            return out
        if demeaned:
            clean = clean - clean.mean()
        if equal_weight:
            pos = clean > 0
            neg = clean < 0
            if pos.any():
                out.loc[clean[pos].index] = 1.0 / int(pos.sum())
            if neg.any():
                out.loc[clean[neg].index] = -1.0 / int(neg.sum())
        else:
            denom = clean.abs().sum()
            if denom > 0:
                out.loc[clean.index] = clean / denom
        gross = out.abs().sum()
        if gross > 0:
            out = out / gross * exposure
        return out

    if not group_neutral:
        return pd.DataFrame(
            [row_weights(score.loc[date], gross_exposure) for date in score.index],
            index=score.index,
            columns=score.columns,
        )

    if groups is None:
        raise ValueError("groups are required when group_neutral=True")
    group_series = pd.Series(groups).reindex(score.columns).dropna()
    if group_series.empty:
        return alphalens_style_factor_weights(
            score,
            demeaned=demeaned,
            group_neutral=False,
            equal_weight=equal_weight,
            gross_exposure=gross_exposure,
        )

    out = pd.DataFrame(0.0, index=score.index, columns=score.columns)
    per_group_exposure = gross_exposure / group_series.nunique()
    for _group, cols in group_series.groupby(group_series).groups.items():
        col_list = list(cols)
        out.loc[:, col_list] = alphalens_style_factor_weights(
            score.loc[:, col_list],
            demeaned=demeaned,
            group_neutral=False,
            equal_weight=equal_weight,
            gross_exposure=per_group_exposure,
        )
    return out


def _rebalance_mask(index: pd.Index, rebalance_freq: str) -> pd.Series:
    if rebalance_freq == "D":
        return pd.Series(True, index=index)
    dates = pd.DatetimeIndex(index)
    if rebalance_freq == "W":
        periods = dates.to_period("W")
    elif rebalance_freq == "M":
        periods = dates.to_period("M")
    else:
        raise ValueError("rebalance_freq must be D, W, or M")
    period_series = pd.Series(periods, index=index)
    mask = period_series.ne(period_series.shift(-1))
    if len(mask) > 0:
        mask.iloc[-1] = True
    return mask


def topk_dropout_weights(
    score: pd.DataFrame,
    spec: Optional[TopKDropoutSpec] = None,
) -> pd.DataFrame:
    """Build Qlib-style top-k target weights with limited turnover."""

    spec = spec or TopKDropoutSpec()
    if spec.top_k <= 0:
        raise ValueError("top_k must be positive")
    if spec.n_drop < 0:
        raise ValueError("n_drop must be non-negative")

    rebalance = _rebalance_mask(score.index, spec.rebalance_freq)
    out = pd.DataFrame(0.0, index=score.index, columns=score.columns)
    holdings: list[str] = []

    for date in score.index:
        row = score.loc[date].replace([np.inf, -np.inf], np.nan).dropna().sort_values(ascending=False)
        if bool(rebalance.loc[date]) and not row.empty:
            ranked_assets = list(row.index)
            top_assets = ranked_assets[: spec.top_k]
            if not holdings:
                holdings = top_assets
            else:
                held_with_scores = [asset for asset in holdings if asset in row.index]
                if spec.force_drop:
                    sell_count = min(spec.n_drop, len(held_with_scores))
                    sell_assets = list(row.loc[held_with_scores].sort_values().index[:sell_count])
                else:
                    out_of_top = [asset for asset in held_with_scores if asset not in top_assets]
                    sell_count = min(spec.n_drop, len(out_of_top))
                    sell_assets = list(row.loc[out_of_top].sort_values().index[:sell_count]) if sell_count else []

                kept = [asset for asset in holdings if asset not in sell_assets and asset in row.index]
                slots = max(spec.top_k - len(kept), 0)
                buy_assets = [asset for asset in top_assets if asset not in kept][:slots]
                holdings = kept + buy_assets
                if len(holdings) > spec.top_k:
                    holdings = list(row.loc[holdings].sort_values(ascending=False).index[: spec.top_k])

        if holdings:
            weight = spec.gross_exposure / len(holdings)
            out.loc[date, holdings] = weight

    return out


def apply_time_series_overlay(
    weights: pd.DataFrame,
    close: pd.DataFrame,
    spec: Optional[TimeSeriesOverlaySpec] = None,
) -> pd.DataFrame:
    """Apply absolute-momentum, MA, and volatility filters to target weights."""

    spec = spec or TimeSeriesOverlaySpec()
    close = close.reindex(index=weights.index, columns=weights.columns)
    allowed = pd.DataFrame(True, index=weights.index, columns=weights.columns)

    if spec.momentum_window is not None:
        momentum = close.pct_change(spec.momentum_window, fill_method=None)
        allowed &= momentum > spec.min_momentum
    if spec.ma_window is not None:
        allowed &= close > close.rolling(spec.ma_window).mean()
    if spec.vol_window is not None and spec.max_annual_vol is not None:
        ann_vol = close.pct_change(fill_method=None).rolling(spec.vol_window).std() * np.sqrt(252)
        allowed &= ann_vol <= spec.max_annual_vol

    filtered = weights.where(allowed, 0.0).fillna(0.0)
    if spec.renormalize:
        gross = weights.abs().sum(axis=1)
        target_gross = gross.where(gross > 0, 0.0)
        current_gross = filtered.abs().sum(axis=1).replace(0.0, np.nan)
        filtered = filtered.div(current_gross, axis=0).mul(target_gross, axis=0).fillna(0.0)
    return filtered


def volatility_target_weights(
    weights: pd.DataFrame,
    close: pd.DataFrame,
    target_annual_vol: float = 0.15,
    vol_window: int = 20,
    max_leverage: float = 1.0,
    min_leverage: float = 0.0,
) -> tuple[pd.DataFrame, pd.Series]:
    """Scale target weights by trailing realized portfolio volatility."""

    if target_annual_vol <= 0:
        raise ValueError("target_annual_vol must be positive")
    if vol_window <= 1:
        raise ValueError("vol_window must be greater than 1")

    close = close.reindex(index=weights.index, columns=weights.columns)
    returns = close.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    base_returns = (weights.shift(1, fill_value=0.0) * returns).sum(axis=1)
    realized_vol = base_returns.rolling(vol_window).std() * np.sqrt(252)
    leverage = target_annual_vol / realized_vol.replace(0.0, np.nan)
    leverage = leverage.clip(lower=min_leverage, upper=max_leverage).fillna(0.0)
    return weights.mul(leverage, axis=0), leverage


def make_factor_strategy_grid(
    long_quantiles: Sequence[float] = (0.1, 0.2, 0.3),
    short_quantiles: Sequence[float] = (0.0, 0.1, 0.2),
    weighting_methods: Sequence[str] = ("equal", "score", "rank"),
    top_k_values: Sequence[int] = (20, 50, 100),
    drop_values: Sequence[int] = (1, 5, 10),
) -> Dict[str, Iterable[object]]:
    """Return a compact search grid of reusable factor strategy specs."""

    quantile_specs = []
    for long_q in long_quantiles:
        for short_q in short_quantiles:
            for weighting in weighting_methods:
                if short_q >= long_q and short_q != 0.0:
                    continue
                suffix = "longonly" if short_q == 0 else f"ls{int(short_q * 100)}"
                quantile_specs.append(
                    QuantilePortfolioSpec(
                        name=f"quantile_{int(long_q * 100)}_{suffix}_{weighting}",
                        long_quantile=long_q,
                        short_quantile=short_q,
                        weighting=weighting,
                        market_neutral=short_q > 0,
                    )
                )

    topk_specs = []
    for top_k in top_k_values:
        for n_drop in drop_values:
            if n_drop >= top_k:
                continue
            topk_specs.append(
                TopKDropoutSpec(
                    name=f"topk_dropout_{top_k}_{n_drop}",
                    top_k=top_k,
                    n_drop=n_drop,
                )
            )

    return {
        "quantile": quantile_specs,
        "topk_dropout": topk_specs,
    }
