"""Runtime qlib execution checks and optional signal-strategy backtest."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from quant_lab.us_stock_selection.utils import ensure_dir, save_dataframe, save_json
from quant_lab.us_stock_selection.validation import build_time_split, evaluate_segment


class QlibRuntimeRunner:
    """Run a real qlib runtime gate and, when available, a minimal model workflow."""

    def __init__(self, config: dict[str, Any], env_config: dict[str, Any], logger):
        self.config = config
        self.env_config = env_config
        self.logger = logger

    def run(
        self,
        feature_map: dict[str, pd.DataFrame],
        loaded_data: dict[str, pd.DataFrame],
        market_context_map: dict[str, pd.DataFrame],
        universe_df: pd.DataFrame,
        adapter,
        out_dir: Path | str,
    ) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
        out = ensure_dir(out_dir)
        status = self._runtime_status()
        if status["status"] != "available":
            save_json(status, out / "qlib_runtime_status.json")
            empty_metrics = pd.DataFrame(columns=["ticker", "model_name", "status", "reason"])
            empty_results = pd.DataFrame(columns=["ticker", "template_name", "test_cagr", "test_calmar", "test_max_drawdown"])
            save_dataframe(empty_metrics, out / "qlib_model_metrics.csv")
            save_dataframe(empty_results, out / "qlib_signal_strategy_results.csv")
            return status, empty_metrics, empty_results

        init_status = self._init_qlib_runtime(status)
        if init_status["status"] != "ready":
            save_json(init_status, out / "qlib_runtime_status.json")
            empty_metrics = pd.DataFrame(columns=["ticker", "model_name", "status", "reason"])
            empty_results = pd.DataFrame(columns=["ticker", "template_name", "test_cagr", "test_calmar", "test_max_drawdown"])
            save_dataframe(empty_metrics, out / "qlib_model_metrics.csv")
            save_dataframe(empty_results, out / "qlib_signal_strategy_results.csv")
            return init_status, empty_metrics, empty_results

        metrics_df, results_df = self._run_ridge_signal_model(feature_map, loaded_data, market_context_map, universe_df, adapter)
        final_status = {
            **init_status,
            "status": "trained",
            "model_note": "Qlib runtime initialized; Ridge signal model trained on the exported qlib panel feature cache.",
            "model_result_rows": int(len(results_df)),
        }
        save_json(final_status, out / "qlib_runtime_status.json")
        save_dataframe(metrics_df, out / "qlib_model_metrics.csv")
        save_dataframe(results_df, out / "qlib_signal_strategy_results.csv")
        return final_status, metrics_df, results_df

    def _runtime_status(self) -> dict[str, Any]:
        provider_uri = str(
            self.config.get("qlib", {}).get("provider_uri")
            or self.env_config.get("paths", {}).get("qlib_bin", "./data/qlib_bin")
        )
        if importlib.util.find_spec("qlib") is None:
            return {
                "status": "not_installed",
                "qlib_available": False,
                "provider_uri": provider_uri,
                "warning": "Qlib runtime is not installed; this run did not execute qlib model training.",
                "install_hint": "pip install pyqlib",
                "run_hint": "After installing qlib and preparing provider data, rerun scripts/us_stock_selection/run_all_us_stock_selection.py.",
            }
        return {
            "status": "available",
            "qlib_available": True,
            "provider_uri": provider_uri,
        }

    def _init_qlib_runtime(self, status: dict[str, Any]) -> dict[str, Any]:
        try:
            import qlib  # type: ignore

            qlib.init(provider_uri=status["provider_uri"], region=str(self.config.get("qlib", {}).get("region", "us")))
            return {
                **status,
                "status": "ready",
                "warning": "",
                "note": "Qlib runtime imported and initialized.",
            }
        except Exception as exc:  # pragma: no cover - depends on local qlib provider
            self.logger.warning(f"Qlib import succeeded but qlib.init failed: {exc}")
            return {
                **status,
                "status": "init_failed",
                "warning": "Qlib is installed but qlib.init failed; no qlib model training was executed.",
                "error": str(exc),
            }

    def _run_ridge_signal_model(
        self,
        feature_map: dict[str, pd.DataFrame],
        loaded_data: dict[str, pd.DataFrame],
        market_context_map: dict[str, pd.DataFrame],
        universe_df: pd.DataFrame,
        adapter,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        try:
            from sklearn.linear_model import Ridge
            from sklearn.pipeline import Pipeline
            from sklearn.preprocessing import StandardScaler
        except Exception as exc:  # pragma: no cover - dependency varies by env
            reason = f"scikit-learn unavailable for qlib runtime signal model: {exc}"
            self.logger.warning(reason)
            return pd.DataFrame([{"model_name": "ridge", "status": "skipped", "reason": reason}]), pd.DataFrame()

        target_col = self.config.get("qlib", {}).get("target_label", self.config.get("ml", {}).get("target_label", "risk_adjusted_label"))
        max_tickers = int(self.config.get("qlib", {}).get("max_tickers", 6))
        tickers = universe_df["ticker"].tolist()
        if max_tickers > 0:
            tickers = tickers[:max_tickers]
        meta = universe_df.set_index("ticker").to_dict(orient="index")
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
        metrics_rows: list[dict[str, Any]] = []
        result_rows: list[dict[str, Any]] = []
        for ticker in tickers:
            frame = feature_map.get(ticker)
            price_frame = loaded_data.get(ticker)
            if frame is None or frame.empty or price_frame is None or price_frame.empty or target_col not in frame.columns:
                continue
            split = build_time_split(frame.index, self.config)
            feature_cols = [col for col in frame.columns if col not in feature_blacklist and pd.api.types.is_numeric_dtype(frame[col])]
            prepared = frame[feature_cols + [target_col]].replace([np.inf, -np.inf], np.nan).dropna()
            train_df = prepared.loc[(prepared.index >= split.train_start) & (prepared.index <= split.train_end)]
            test_df = prepared.loc[(prepared.index >= split.test_start) & (prepared.index <= split.test_end)]
            if len(train_df) < 250 or len(test_df) < 60 or not feature_cols:
                metrics_rows.append({"ticker": ticker, "model_name": "ridge", "status": "skipped", "reason": "insufficient rows or features"})
                continue

            model = Pipeline([("scaler", StandardScaler()), ("model", Ridge(alpha=1.0))])
            model.fit(train_df[feature_cols], train_df[target_col])
            pred = pd.Series(model.predict(prepared[feature_cols]), index=prepared.index)
            threshold = float(pred.loc[(pred.index >= split.train_start) & (pred.index <= split.train_end)].quantile(0.65))
            exit_threshold = float(pred.loc[(pred.index >= split.train_start) & (pred.index <= split.train_end)].quantile(0.35))

            bundle = adapter.run_backtest(
                ticker=ticker,
                frame=price_frame.reindex(pred.index).dropna(subset=["close"]),
                market_context=market_context_map.get(ticker, pd.DataFrame()).reindex(pred.index),
                template_name="ml_signal",
                params={
                    "prediction_series": pred,
                    "prediction_entry_threshold": threshold,
                    "prediction_exit_threshold": exit_threshold,
                    "ma_fast": 20,
                    "ma_slow": 100,
                    "max_realized_vol": 0.65,
                    "atr_stop_mult": 3.0,
                    "market_filter_source": "QQQ_trend",
                    "market_filter_threshold": 0.0,
                },
                asset_meta=meta.get(ticker, {}),
            )
            test_metrics = evaluate_segment(bundle.returns, bundle.benchmark_returns, bundle.position, split.test_start, split.test_end)
            metrics_rows.append(
                {
                    "ticker": ticker,
                    "model_name": "ridge_on_qlib_panel",
                    "status": "trained",
                    "feature_count": len(feature_cols),
                    "train_rows": len(train_df),
                    "test_rows": len(test_df),
                }
            )
            result_rows.append(
                {
                    "ticker": ticker,
                    "template_name": "qlib_signal_strategy",
                    "model_name": "ridge_on_qlib_panel",
                    "test_cagr": test_metrics["cagr"],
                    "test_calmar": test_metrics["calmar"],
                    "test_max_drawdown": test_metrics["max_drawdown"],
                    "bh_test_cagr": test_metrics["benchmark_cagr"],
                    "bh_test_calmar": test_metrics["benchmark_calmar"],
                    "strategy_vs_bh_cagr_diff": test_metrics["cagr"] - test_metrics["benchmark_cagr"],
                    "strategy_vs_bh_calmar_diff": test_metrics["calmar"] - test_metrics["benchmark_calmar"],
                }
            )

        return pd.DataFrame(metrics_rows), pd.DataFrame(result_rows)
