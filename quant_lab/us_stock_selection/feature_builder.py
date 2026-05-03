"""Feature and label construction for the US stock selection study."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from src.factors import (
    SAFETY_FACTORS,
    compute_external_price_volume_factor_panels,
    list_external_panel_factors,
)

from quant_lab.us_stock_selection.utils import ensure_dir, save_parquet


def _rsi(series: pd.Series, window: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0).rolling(window).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window).mean()
    rs = gain.div(loss.replace(0, np.nan))
    return 100.0 - 100.0 / (1.0 + rs)


def _atr(frame: pd.DataFrame, window: int = 14) -> pd.Series:
    prev_close = frame["close"].shift(1)
    true_range = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - prev_close).abs(),
            (frame["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(window).mean()


def _future_max_drawdown(close: pd.Series, horizon: int) -> pd.Series:
    future_min = close.shift(-1).iloc[::-1].rolling(horizon, min_periods=1).min().iloc[::-1]
    return future_min.div(close.replace(0, np.nan)).sub(1.0)


@dataclass
class FeatureBuildResult:
    ticker: str
    features: pd.DataFrame
    cache_path: str


class FeatureBuilder:
    """Build per-ticker feature tables and cross-asset external factor panels."""

    def __init__(self, config: dict[str, Any], logger):
        self.config = config
        self.logger = logger
        self.feature_cfg = config.get("features", {})
        self.enable_safety_features = bool(self.feature_cfg.get("enable_safety_features", False))
        selected_factor_names = config.get("factor_screen", {}).get("selected_factors", [])
        self.selected_safety_names = [
            name.removeprefix("safe__")
            for name in selected_factor_names
            if str(name).startswith("safe__")
        ]

    def build_feature_cache(
        self,
        ticker: str,
        frame: pd.DataFrame,
        market_panels: dict[str, pd.DataFrame],
        cache_dir: str | None = None,
        external_feature_map: dict[str, pd.Series] | None = None,
    ) -> FeatureBuildResult:
        features = self.compute_feature_frame(
            ticker=ticker,
            frame=frame,
            market_panels=market_panels,
            external_feature_map=external_feature_map,
        )
        cache_root = ensure_dir(cache_dir or self.feature_cfg.get("cache_dir", "data/features_cache/us_stock_selection"))
        cache_path = cache_root / f"{ticker}_features.parquet"
        save_parquet(features.reset_index(), cache_path)
        return FeatureBuildResult(ticker=ticker, features=features, cache_path=str(cache_path))

    def build_external_feature_map(
        self,
        loaded_data: dict[str, pd.DataFrame],
        factor_names: list[str],
        batch_size: int = 25,
    ) -> dict[str, dict[str, pd.Series]]:
        if not factor_names:
            return {}
        known = set(list_external_panel_factors())
        selected = [name for name in factor_names if name in known]
        skipped = [name for name in factor_names if name not in known]
        if skipped:
            self.logger.warning(f"Skipping unsupported external factor names: {skipped}")
        if not selected:
            return {}

        open_panel = pd.DataFrame({ticker: data["open"] for ticker, data in loaded_data.items() if not data.empty}).sort_index()
        high_panel = pd.DataFrame({ticker: data["high"] for ticker, data in loaded_data.items() if not data.empty}).sort_index()
        low_panel = pd.DataFrame({ticker: data["low"] for ticker, data in loaded_data.items() if not data.empty}).sort_index()
        close_panel = pd.DataFrame({ticker: data["close"] for ticker, data in loaded_data.items() if not data.empty}).sort_index()
        volume_panel = pd.DataFrame({ticker: data["volume"] for ticker, data in loaded_data.items() if not data.empty}).sort_index()

        results: dict[str, dict[str, pd.Series]] = {ticker: {} for ticker in loaded_data}
        for start in range(0, len(selected), batch_size):
            batch = selected[start : start + batch_size]
            self.logger.info(f"Computing external factor batch {start} - {start + len(batch) - 1}")
            panels = compute_external_price_volume_factor_panels(
                {
                    "open": open_panel,
                    "high": high_panel,
                    "low": low_panel,
                    "close": close_panel,
                    "volume": volume_panel,
                    "amount": close_panel * volume_panel,
                },
                batch,
            )
            for factor_name, panel in panels.items():
                for ticker in panel.columns:
                    results.setdefault(ticker, {})[f"ext__{factor_name}"] = panel[ticker]
        return results

    def compute_feature_frame(
        self,
        ticker: str,
        frame: pd.DataFrame,
        market_panels: dict[str, pd.DataFrame],
        external_feature_map: dict[str, pd.Series] | None = None,
    ) -> pd.DataFrame:
        close = frame["close"]
        volume = frame["volume"].replace(0, np.nan)
        returns = close.pct_change(fill_method=None)
        atr_14 = _atr(frame, 14)
        qqq_close = market_panels.get("QQQ", pd.DataFrame()).get("QQQ")
        spy_close = market_panels.get("SPY", pd.DataFrame()).get("SPY")
        tlt_close = market_panels.get("TLT", pd.DataFrame()).get("TLT")
        ief_close = market_panels.get("IEF", pd.DataFrame()).get("IEF")

        feature_df = pd.DataFrame(index=frame.index)
        feature_df["ticker"] = ticker
        feature_df["open"] = frame["open"]
        feature_df["high"] = frame["high"]
        feature_df["low"] = frame["low"]
        feature_df["close"] = close
        feature_df["adj_close"] = frame["adj_close"]
        feature_df["volume"] = frame["volume"]
        feature_df["return_1d"] = returns

        for window in (5, 10, 20, 60, 120, 252):
            feature_df[f"return_{window}d"] = close.pct_change(window, fill_method=None)
            ma = close.rolling(window).mean()
            feature_df[f"moving_average_gap_{window}"] = close.div(ma).sub(1.0)
            feature_df[f"price_above_ma_{window}"] = (close > ma).astype(float)
            feature_df[f"breakout_high_{window}"] = close.div(close.rolling(window).max().shift(1)).sub(1.0)
            feature_df[f"distance_from_high_{window}"] = close.div(close.rolling(window).max()).sub(1.0)
            feature_df[f"distance_from_low_{window}"] = close.div(close.rolling(window).min()).sub(1.0)

        feature_df["ma_slope_20"] = close.rolling(20).mean().pct_change(5, fill_method=None)
        feature_df["ma_slope_60"] = close.rolling(60).mean().pct_change(5, fill_method=None)
        feature_df["trend_strength_20_60"] = close.rolling(20).mean().div(close.rolling(60).mean()).sub(1.0)
        feature_df["short_term_reversal"] = -close.pct_change(5, fill_method=None)
        feature_df["rsi_14"] = _rsi(close, 14)
        feature_df["realized_vol_10d"] = returns.rolling(10).std() * np.sqrt(252)
        feature_df["realized_vol_20d"] = returns.rolling(20).std() * np.sqrt(252)
        feature_df["realized_vol_60d"] = returns.rolling(60).std() * np.sqrt(252)
        feature_df["atr_14"] = atr_14
        feature_df["atr_pct_14"] = atr_14.div(close.replace(0, np.nan))
        parkinson = np.log(frame["high"].div(frame["low"].replace(0, np.nan))).pow(2).rolling(20).mean() / (4.0 * np.log(2.0))
        feature_df["parkinson_vol_20d"] = np.sqrt(parkinson) * np.sqrt(252)
        feature_df["downside_volatility_20d"] = returns.where(returns < 0.0).rolling(20).std() * np.sqrt(252)
        feature_df["volatility_contraction_20_60"] = feature_df["realized_vol_20d"].div(feature_df["realized_vol_60d"].replace(0, np.nan))
        feature_df["volume_zscore_20"] = (volume - volume.rolling(20).mean()).div(volume.rolling(20).std().replace(0, np.nan))
        feature_df["turnover_proxy_20"] = (close * volume).rolling(20).mean()
        feature_df["price_volume_corr_20"] = returns.rolling(20).corr(volume.pct_change(fill_method=None))
        feature_df["volume_breakout_20"] = volume.div(volume.rolling(20).mean().replace(0, np.nan))
        feature_df["drawdown_from_peak_60"] = close.div(close.rolling(60).max()).sub(1.0)
        feature_df["drawdown_from_peak_252"] = close.div(close.rolling(252).max()).sub(1.0)
        feature_df["max_dd_rolling_20"] = close.div(close.rolling(20).max()).sub(1.0)
        feature_df["max_dd_rolling_60"] = close.div(close.rolling(60).max()).sub(1.0)
        feature_df["volatility_regime"] = feature_df["realized_vol_20d"].div(
            returns.rolling(120).std().mul(np.sqrt(252)).replace(0, np.nan)
        )

        if qqq_close is not None:
            qqq_ret = qqq_close.pct_change(fill_method=None)
            feature_df["beta_to_QQQ"] = returns.rolling(60).cov(qqq_ret).div(qqq_ret.rolling(60).var().replace(0, np.nan))
            feature_df["correlation_to_QQQ"] = returns.rolling(60).corr(qqq_ret)
            feature_df["QQQ_trend"] = qqq_close.div(qqq_close.rolling(200).mean()).sub(1.0)
        else:
            feature_df["beta_to_QQQ"] = np.nan
            feature_df["correlation_to_QQQ"] = np.nan
            feature_df["QQQ_trend"] = np.nan

        if spy_close is not None:
            spy_ret = spy_close.pct_change(fill_method=None)
            feature_df["beta_to_SPY"] = returns.rolling(60).cov(spy_ret).div(spy_ret.rolling(60).var().replace(0, np.nan))
            feature_df["SPY_trend"] = spy_close.div(spy_close.rolling(200).mean()).sub(1.0)
        else:
            feature_df["beta_to_SPY"] = np.nan
            feature_df["SPY_trend"] = np.nan

        if tlt_close is not None:
            feature_df["TLT_trend"] = tlt_close.div(tlt_close.rolling(100).mean()).sub(1.0)
        else:
            feature_df["TLT_trend"] = np.nan

        if ief_close is not None:
            feature_df["risk_on_proxy"] = feature_df["QQQ_trend"].sub(ief_close.div(ief_close.rolling(100).mean()).sub(1.0))
        else:
            feature_df["risk_on_proxy"] = feature_df["QQQ_trend"] - feature_df["TLT_trend"]

        label_threshold = float(self.feature_cfg.get("trend_threshold", 0.05))
        for horizon in (5, 10, 20, 60):
            feature_df[f"forward_return_{horizon}d"] = close.shift(-horizon).div(close).sub(1.0)
        feature_df["future_max_drawdown_20d"] = _future_max_drawdown(close, horizon=20)
        feature_df["future_volatility_20d"] = returns.shift(-1).rolling(20).std().shift(-19) * np.sqrt(252)
        feature_df["trend_label"] = (feature_df["forward_return_20d"] > label_threshold).astype(float)
        feature_df["risk_adjusted_label"] = feature_df["forward_return_20d"].div(
            feature_df["future_max_drawdown_20d"].abs().replace(0, np.nan)
        )
        feature_df["strategy_fitness_label"] = feature_df["forward_return_20d"] - 0.5 * feature_df["future_max_drawdown_20d"].abs()

        if self.enable_safety_features:
            safety_items = (
                {name: SAFETY_FACTORS[name] for name in self.selected_safety_names if name in SAFETY_FACTORS}
                if self.selected_safety_names
                else SAFETY_FACTORS
            )
            for factor_name, factor in safety_items.items():
                try:
                    feature_df[f"safe__{factor_name}"] = factor.calculate(frame)
                except Exception:
                    feature_df[f"safe__{factor_name}"] = np.nan

        if external_feature_map:
            for name, series in external_feature_map.items():
                feature_df[name] = pd.Series(series).reindex(feature_df.index)

        feature_df = feature_df.replace([np.inf, -np.inf], np.nan)
        return feature_df

    def build_label_audit(self, feature_map: dict[str, pd.DataFrame]) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        for ticker, frame in feature_map.items():
            rows.append(
                {
                    "ticker": ticker,
                    "rows": int(len(frame)),
                    "max_feature_date": frame.index.max().date().isoformat() if not frame.empty else None,
                    "last_forward_return_20d_non_na": (
                        frame["forward_return_20d"].dropna().index.max().date().isoformat()
                        if "forward_return_20d" in frame and frame["forward_return_20d"].dropna().size
                        else None
                    ),
                    "label_shift_tail_na": int(frame["forward_return_20d"].tail(20).isna().sum()) if "forward_return_20d" in frame else 0,
                    "future_max_drawdown_tail_na": int(frame["future_max_drawdown_20d"].tail(20).isna().sum()) if "future_max_drawdown_20d" in frame else 0,
                    "leakage_check_pass": bool(
                        "forward_return_20d" in frame
                        and frame["forward_return_20d"].tail(20).isna().all()
                    ),
                }
            )
        return pd.DataFrame(rows).sort_values("ticker").reset_index(drop=True)

    @staticmethod
    def available_external_factors() -> list[str]:
        return list_external_panel_factors()
