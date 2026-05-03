"""Strategy search across vectorbt templates and ML models."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from quant_lab.us_stock_selection.strategy_templates import DEFAULT_TEMPLATES, expand_template_grid
from quant_lab.us_stock_selection.utils import annualized_return, calmar_ratio, compact_params, max_drawdown, nav_from_returns
from quant_lab.us_stock_selection.validation import TimeSplit, build_time_split, evaluate_segment


@dataclass
class SearchOutputs:
    all_results: pd.DataFrame
    best_by_ticker: pd.DataFrame
    best_bundles: dict[str, Any]
    ml_results: pd.DataFrame


class StrategySearchEngine:
    """Run vectorbt strategy search and ML signal conversion."""

    def __init__(self, config: dict[str, Any], logger):
        self.config = config
        self.logger = logger
        self.selection_rules = config.get("selection_rules", {})

    def run_vectorbt_search(
        self,
        universe_df: pd.DataFrame,
        loaded_data: dict[str, pd.DataFrame],
        market_context_map: dict[str, pd.DataFrame],
        adapter,
        search_space: dict[str, Any],
    ) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any], dict[str, TimeSplit]]:
        rows: list[dict[str, Any]] = []
        best_rows: list[dict[str, Any]] = []
        best_bundles: dict[str, Any] = {}
        split_map: dict[str, TimeSplit] = {}

        metadata = universe_df.set_index("ticker").to_dict(orient="index")
        for ticker in universe_df["ticker"]:
            frame = loaded_data.get(ticker, pd.DataFrame())
            if frame.empty:
                continue
            self.logger.info(f"Strategy search for {ticker}")
            split = build_time_split(frame.index, self.config)
            split_map[ticker] = split
            market_context = market_context_map.get(ticker, pd.DataFrame(index=frame.index))

            ticker_rows = []
            for template_name in search_space.keys():
                if not self._template_applies(template_name, search_space.get(template_name, {}), metadata.get(ticker, {}), ticker):
                    continue
                self.logger.info(f"{ticker}: template {template_name}")
                for params in self._template_param_grid(template_name, search_space):
                    bundle = adapter.run_backtest(
                        ticker=ticker,
                        frame=frame,
                        market_context=market_context,
                        template_name=template_name,
                        params=params,
                        asset_meta=metadata.get(ticker, {}),
                    )
                    if bundle.returns.empty:
                        continue

                    train_metrics = evaluate_segment(bundle.returns, bundle.benchmark_returns, bundle.position, split.train_start, split.train_end)
                    valid_metrics = evaluate_segment(bundle.returns, bundle.benchmark_returns, bundle.position, split.valid_start, split.valid_end)
                    test_metrics = evaluate_segment(bundle.returns, bundle.benchmark_returns, bundle.position, split.test_start, split.test_end)

                    metrics = dict(bundle.metrics)
                    row = {
                        "ticker": ticker,
                        "template_name": template_name,
                        "params": compact_params(params),
                        "strategy_complexity": metrics.get("strategy_complexity", DEFAULT_TEMPLATES.get(template_name, DEFAULT_TEMPLATES["combo_guardrail"]).complexity),
                        "train_cagr": train_metrics["cagr"],
                        "train_calmar": train_metrics["calmar"],
                        "train_max_drawdown": train_metrics["max_drawdown"],
                        "valid_cagr": valid_metrics["cagr"],
                        "valid_calmar": valid_metrics["calmar"],
                        "valid_max_drawdown": valid_metrics["max_drawdown"],
                        "test_cagr": test_metrics["cagr"],
                        "test_calmar": test_metrics["calmar"],
                        "test_max_drawdown": test_metrics["max_drawdown"],
                        "total_return": metrics.get("total_return", 0.0),
                        "cagr": metrics.get("cagr", 0.0),
                        "calmar": metrics.get("calmar", 0.0),
                        "max_drawdown": metrics.get("max_drawdown", 0.0),
                        "sharpe": metrics.get("sharpe", 0.0),
                        "sortino": metrics.get("sortino", 0.0),
                        "volatility": metrics.get("volatility", 0.0),
                        "win_rate": metrics.get("win_rate", 0.0),
                        "profit_factor": metrics.get("profit_factor", 0.0),
                        "number_of_trades": metrics.get("number_of_trades", 0),
                        "average_trade_return": metrics.get("average_trade_return", 0.0),
                        "best_trade": metrics.get("best_trade", 0.0),
                        "worst_trade": metrics.get("worst_trade", 0.0),
                        "exposure": metrics.get("exposure", 0.0),
                        "turnover_proxy": metrics.get("turnover_proxy", 0.0),
                        "benchmark_cagr": test_metrics.get("benchmark_cagr", 0.0),
                        "benchmark_max_drawdown": test_metrics.get("benchmark_max_drawdown", 0.0),
                        "benchmark_calmar": test_metrics.get("benchmark_calmar", 0.0),
                        "bh_test_cagr": test_metrics.get("benchmark_cagr", 0.0),
                        "bh_test_max_drawdown": test_metrics.get("benchmark_max_drawdown", 0.0),
                        "bh_test_calmar": test_metrics.get("benchmark_calmar", 0.0),
                        "strategy_vs_bh_cagr_diff": float(test_metrics.get("cagr", 0.0) - test_metrics.get("benchmark_cagr", 0.0)),
                        "strategy_vs_bh_calmar_diff": float(test_metrics.get("calmar", 0.0) - test_metrics.get("benchmark_calmar", 0.0)),
                        "strategy_beats_bh_cagr": bool(test_metrics.get("cagr", 0.0) > test_metrics.get("benchmark_cagr", 0.0)),
                        "strategy_beats_bh_calmar": bool(test_metrics.get("calmar", 0.0) > test_metrics.get("benchmark_calmar", 0.0)),
                        "strategy_beats_bh_both": bool(
                            test_metrics.get("cagr", 0.0) > test_metrics.get("benchmark_cagr", 0.0)
                            and test_metrics.get("calmar", 0.0) >= test_metrics.get("benchmark_calmar", 0.0)
                        ),
                        "excess_calmar": float(test_metrics.get("calmar", 0.0) - test_metrics.get("benchmark_calmar", 0.0)),
                        "beats_buy_and_hold": bool(test_metrics.get("cagr", 0.0) > test_metrics.get("benchmark_cagr", 0.0)),
                    }
                    row["passes_cagr_rule"] = row["test_cagr"] >= float(self.selection_rules.get("min_oos_cagr", 0.20))
                    row["passes_drawdown_rule"] = abs(row["test_max_drawdown"]) <= float(self.selection_rules.get("max_oos_drawdown", 0.50))
                    row["passes_trade_rule"] = row["number_of_trades"] >= float(self.selection_rules.get("min_oos_trades", 20))
                    row["selection_score"] = row["valid_calmar"] + 0.5 * row["valid_cagr"] + 0.25 * row["test_calmar"]
                    rows.append(row)
                    ticker_rows.append((row, bundle))

            if not ticker_rows:
                continue

            ticker_df = pd.DataFrame([row for row, _bundle in ticker_rows])
            chosen_row = self._choose_best_row(ticker_df)
            if chosen_row is None:
                continue

            same_template = ticker_df.loc[ticker_df["template_name"] == chosen_row["template_name"]].copy()
            stable_threshold = float(chosen_row["valid_calmar"]) * 0.8
            plateau_share = float((same_template["valid_calmar"] >= stable_threshold).mean()) if stable_threshold > 0 else 0.0
            spike_prone = plateau_share < float(self.config.get("validation", {}).get("plateau_share_threshold", 0.15))

            chosen_bundle = next(bundle for row, bundle in ticker_rows if row["ticker"] == chosen_row["ticker"] and row["template_name"] == chosen_row["template_name"] and row["params"] == chosen_row["params"])
            best_bundles[ticker] = chosen_bundle
            best_record = dict(chosen_row)
            best_record["parameter_stability_score"] = plateau_share * 100.0
            best_record["spike_prone"] = spike_prone
            best_record["passes_robustness_prescreen"] = bool(
                best_record["passes_cagr_rule"] and best_record["passes_drawdown_rule"] and best_record["passes_trade_rule"]
            )
            best_rows.append(best_record)

        all_results = pd.DataFrame(rows).sort_values(["ticker", "selection_score"], ascending=[True, False]).reset_index(drop=True)
        best_by_ticker = pd.DataFrame(best_rows).sort_values(["selection_score", "test_calmar"], ascending=[False, False]).reset_index(drop=True)
        return all_results, best_by_ticker, best_bundles, split_map

    def run_rotation_search(
        self,
        loaded_data: dict[str, pd.DataFrame],
        search_config: dict[str, Any],
    ) -> pd.DataFrame:
        """Run a small-pool relative-strength rotation study."""
        if not search_config or not bool(search_config.get("enabled", True)):
            return pd.DataFrame()
        candidates = [str(t) for t in search_config.get("candidate_pool", [])]
        available = [ticker for ticker in candidates if ticker in loaded_data and not loaded_data[ticker].empty]
        if len(available) < 2:
            return pd.DataFrame()
        close = pd.DataFrame({ticker: loaded_data[ticker]["adj_close"].fillna(loaded_data[ticker]["close"]) for ticker in available}).sort_index().ffill()
        returns = close.pct_change(fill_method=None).fillna(0.0)
        params_cfg = search_config.get("params", {})
        names = list(params_cfg.keys())
        rows: list[dict[str, Any]] = []
        grids = [list(params_cfg[name]) for name in names]
        from itertools import product

        for combo in product(*grids):
            params = dict(zip(names, combo))
            lookback = int(params.get("lookback", 120))
            top_k = int(params.get("top_k", 1))
            rebalance = str(params.get("rebalance", "M")).upper()
            safe_asset = str(params.get("safe_asset", "SHY"))
            market_filter = str(params.get("market_filter", "QQQ_MA200"))
            risk_adjust = str(params.get("risk_adjust", "return_div_vol"))
            momentum = close.pct_change(lookback, fill_method=None)
            if risk_adjust == "return_div_vol":
                realized = returns.rolling(lookback).std().replace(0.0, np.nan) * np.sqrt(252)
                score = momentum.div(realized)
            else:
                score = momentum
            rebalance_dates = close.resample("W-FRI").last().index if rebalance == "W" else close.resample("ME").last().index
            rebalance_dates = close.index[close.index.isin(rebalance_dates)]
            weights = pd.DataFrame(np.nan, index=close.index, columns=close.columns)
            qqq_ok = True
            for date in rebalance_dates:
                current_weights = pd.Series(0.0, index=weights.columns)
                if market_filter == "QQQ_MA200" and "QQQ" in close.columns:
                    qqq_ok = bool(close.loc[date, "QQQ"] > close["QQQ"].rolling(200).mean().loc[date])
                elif market_filter == "SPY_MA200" and "SPY" in close.columns:
                    qqq_ok = bool(close.loc[date, "SPY"] > close["SPY"].rolling(200).mean().loc[date])
                else:
                    qqq_ok = True
                current_score = score.loc[date].dropna().sort_values(ascending=False)
                selected = current_score[current_score > 0.0].head(top_k).index.tolist() if qqq_ok else []
                if not selected:
                    if safe_asset in weights.columns:
                        current_weights.loc[safe_asset] = 1.0
                    elif safe_asset.lower() == "cash":
                        pass
                    elif "SHY" in weights.columns:
                        current_weights.loc["SHY"] = 1.0
                    weights.loc[date] = current_weights
                    continue
                current_weights.loc[selected] = 1.0 / len(selected)
                weights.loc[date] = current_weights
            weights = weights.ffill().fillna(0.0)
            portfolio_returns = (weights.shift(1).fillna(0.0) * returns).sum(axis=1)
            nav = nav_from_returns(portfolio_returns)
            dd = max_drawdown(nav)
            rows.append(
                {
                    "strategy_name": "relative_strength_rotation",
                    "params": compact_params(params),
                    "available_assets": ",".join(available),
                    "total_return": float(nav.iloc[-1] - 1.0) if not nav.empty else 0.0,
                    "cagr": annualized_return(portfolio_returns),
                    "max_drawdown": dd,
                    "calmar": calmar_ratio(portfolio_returns),
                    "average_exposure": float(weights.sum(axis=1).mean()),
                    "rebalance_count": int(len(rebalance_dates)),
                }
            )
        return pd.DataFrame(rows).sort_values(["calmar", "cagr"], ascending=[False, False]).reset_index(drop=True)

    def run_ml_search(
        self,
        universe_df: pd.DataFrame,
        feature_map: dict[str, pd.DataFrame],
        market_context_map: dict[str, pd.DataFrame],
        adapter,
    ) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        empty_columns = [
            "ticker",
            "template_name",
            "params",
            "valid_signal_threshold",
            "test_cagr",
            "test_calmar",
            "test_max_drawdown",
            "benchmark_cagr",
            "benchmark_calmar",
            "model_name",
            "feature_count",
        ]
        target_col = self.config.get("ml", {}).get("target_label", "risk_adjusted_label")
        min_train = int(self.config.get("ml", {}).get("min_train_rows", 250))
        feature_blacklist = {
            "ticker",
            "open",
            "high",
            "low",
            "close",
            "adj_close",
            "volume",
            "forward_return_5d",
            "forward_return_10d",
            "forward_return_20d",
            "forward_return_60d",
            "future_max_drawdown_20d",
            "future_volatility_20d",
            "trend_label",
            "risk_adjusted_label",
            "strategy_fitness_label",
        }
        metadata = universe_df.set_index("ticker").to_dict(orient="index")

        for ticker in universe_df["ticker"]:
            frame = feature_map.get(ticker)
            if frame is None or frame.empty or target_col not in frame.columns:
                continue
            self.logger.info(f"ML search for {ticker}")
            split = build_time_split(frame.index, self.config)
            train_mask = (frame.index >= split.train_start) & (frame.index <= split.train_end)
            valid_mask = (frame.index >= split.valid_start) & (frame.index <= split.valid_end)
            test_mask = (frame.index >= split.test_start) & (frame.index <= split.test_end)

            feature_cols = [col for col in frame.columns if col not in feature_blacklist and pd.api.types.is_numeric_dtype(frame[col])]
            prepared = frame[feature_cols + [target_col, "close", "adj_close", "high", "low"]].replace([np.inf, -np.inf], np.nan).dropna()
            train_df = prepared.loc[(prepared.index >= split.train_start) & (prepared.index <= split.train_end)]
            valid_df = prepared.loc[(prepared.index >= split.valid_start) & (prepared.index <= split.valid_end)]
            test_df = prepared.loc[(prepared.index >= split.test_start) & (prepared.index <= split.test_end)]
            if len(train_df) < min_train or len(valid_df) < 60 or len(test_df) < 60:
                continue

            models = self._build_models()
            if not models:
                self.logger.warning(f"{ticker} ML search skipped because no compatible model backend is available.")
                continue
            for model_name, model in models.items():
                try:
                    model.fit(train_df[feature_cols], train_df[target_col])
                except Exception as exc:
                    self.logger.warning(f"{ticker} {model_name} fit failed: {exc}")
                    continue

                valid_pred = pd.Series(model.predict(valid_df[feature_cols]), index=valid_df.index)
                threshold = float(valid_pred.quantile(float(self.config.get("ml", {}).get("entry_quantile", 0.65))))
                exit_threshold = float(valid_pred.quantile(float(self.config.get("ml", {}).get("exit_quantile", 0.35))))

                full_prepared = prepared.copy()
                full_pred = pd.Series(model.predict(full_prepared[feature_cols]), index=full_prepared.index)
                signal_frame = pd.DataFrame(
                    {
                        "open": full_prepared["close"],
                        "high": full_prepared["high"],
                        "low": full_prepared["low"],
                        "close": full_prepared["close"],
                        "adj_close": full_prepared["adj_close"],
                    }
                )
                market_context = market_context_map.get(ticker, pd.DataFrame(index=signal_frame.index))
                params = {
                    "ma_fast": 20,
                    "ma_slow": 100,
                    "max_realized_vol": 0.65,
                    "atr_stop_mult": 3.0,
                    "market_filter_source": "QQQ_trend",
                    "market_filter_threshold": 0.0,
                    "prediction_series": full_pred,
                    "prediction_entry_threshold": threshold,
                    "prediction_exit_threshold": exit_threshold,
                }
                signal_bundle = adapter.run_backtest(
                    ticker=ticker,
                    frame=signal_frame.assign(
                        volume=feature_map[ticker].reindex(signal_frame.index)["volume"].fillna(0.0)
                    ),
                    market_context=market_context.reindex(signal_frame.index),
                    template_name="ml_signal",
                    params=params,
                    asset_meta=metadata.get(ticker, {}),
                )

                test_metrics = evaluate_segment(
                    signal_bundle.returns,
                    signal_bundle.benchmark_returns,
                    signal_bundle.position,
                    split.test_start,
                    split.test_end,
                )
                rows.append(
                    {
                        "ticker": ticker,
                        "template_name": f"ml_{model_name}",
                        "params": compact_params({"entry_threshold": threshold, "exit_threshold": exit_threshold}),
                        "valid_signal_threshold": threshold,
                        "test_cagr": test_metrics["cagr"],
                        "test_calmar": test_metrics["calmar"],
                        "test_max_drawdown": test_metrics["max_drawdown"],
                        "benchmark_cagr": test_metrics["benchmark_cagr"],
                        "benchmark_calmar": test_metrics["benchmark_calmar"],
                        "model_name": model_name,
                        "feature_count": len(feature_cols),
                    }
                )
        if not rows:
            self.logger.warning("ML search finished without producing any valid model results.")
            return pd.DataFrame(columns=empty_columns)
        return pd.DataFrame(rows).sort_values(["ticker", "test_calmar"], ascending=[True, False]).reset_index(drop=True)

    def _choose_best_row(self, ticker_df: pd.DataFrame) -> dict[str, Any] | None:
        if ticker_df.empty:
            return None
        eligible = ticker_df.loc[
            ticker_df["passes_drawdown_rule"] & ticker_df["passes_trade_rule"]
        ].copy()
        if eligible.empty:
            eligible = ticker_df.copy()
        chosen = eligible.sort_values(
            ["passes_cagr_rule", "selection_score", "test_calmar", "test_cagr"],
            ascending=[False, False, False, False],
        ).iloc[0]
        return chosen.to_dict()

    def _template_param_grid(self, template_name: str, search_space: dict[str, Any]) -> list[dict[str, Any]]:
        grid = expand_template_grid(template_name, search_space)
        template_cfg = search_space.get(template_name, {})
        max_combos = int(template_cfg.get("max_combinations", self.config.get("search", {}).get("max_combinations_per_template", 0)) or 0)
        if max_combos > 0 and len(grid) > max_combos:
            idx = np.linspace(0, len(grid) - 1, max_combos).round().astype(int)
            grid = [grid[int(i)] for i in sorted(set(idx))]
        return grid

    @staticmethod
    def _template_applies(template_name: str, template_cfg: dict[str, Any], asset_meta: dict[str, Any], ticker: str) -> bool:
        if not bool(template_cfg.get("enabled", True)):
            return False
        applies = template_cfg.get("applies_to", {}) or {}
        tickers = set(str(item).upper() for item in applies.get("tickers", []))
        if tickers and str(ticker).upper() not in tickers:
            return False
        if bool(applies.get("leveraged_only", False)) and not bool(asset_meta.get("is_leveraged", False)):
            return False
        asset_types = set(str(item).lower() for item in applies.get("asset_types", []))
        if asset_types and str(asset_meta.get("asset_type", "")).lower() not in asset_types:
            return False
        return True

    def _build_models(self) -> dict[str, Any]:
        models: dict[str, Any] = {}
        try:
            from sklearn.ensemble import RandomForestRegressor
            from sklearn.linear_model import ElasticNet, Lasso, Ridge
            from sklearn.pipeline import Pipeline
            from sklearn.preprocessing import StandardScaler

            models.update(
                {
                    "ridge": Pipeline([("scaler", StandardScaler()), ("model", Ridge(alpha=1.0))]),
                    "lasso": Pipeline([("scaler", StandardScaler()), ("model", Lasso(alpha=0.001, max_iter=5000))]),
                    "elasticnet": Pipeline([("scaler", StandardScaler()), ("model", ElasticNet(alpha=0.001, l1_ratio=0.5, max_iter=5000))]),
                    "random_forest": RandomForestRegressor(
                        n_estimators=200,
                        max_depth=6,
                        min_samples_leaf=10,
                        random_state=42,
                        n_jobs=-1,
                    ),
                }
            )
        except Exception as exc:
            self.logger.warning(f"scikit-learn unavailable, skipping sklearn models: {exc}")
        try:
            from lightgbm import LGBMRegressor

            models["lightgbm"] = LGBMRegressor(
                n_estimators=250,
                learning_rate=0.05,
                num_leaves=31,
                random_state=42,
            )
        except Exception as exc:
            self.logger.warning(f"LightGBM unavailable, skipping: {exc}")
        try:
            from xgboost import XGBRegressor

            models["xgboost"] = XGBRegressor(
                n_estimators=250,
                learning_rate=0.05,
                max_depth=4,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=42,
            )
        except Exception as exc:
            self.logger.warning(f"XGBoost unavailable, skipping: {exc}")
        return models
