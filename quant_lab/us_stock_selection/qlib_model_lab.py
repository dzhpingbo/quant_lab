"""Qlib-first model lab with a local cross-sectional fallback backend."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from quant_lab.us_stock_selection.utils import ensure_dir, save_dataframe, save_parquet, save_yaml


BASE_BLACKLIST = {
    "ticker",
    "open",
    "high",
    "low",
    "close",
    "adj_close",
    "volume",
    "dividends",
    "splits",
    "forward_return_5d",
    "forward_return_10d",
    "forward_return_20d",
    "forward_return_60d",
    "future_max_drawdown_20d",
    "future_volatility_20d",
    "trend_label",
    "risk_adjusted_label",
    "strategy_fitness_label",
    "risk_adj_10d",
}


class QlibModelLab:
    """Train cross-sectional prediction models and export Qlib-style signals."""

    def __init__(self, config: dict[str, Any], logger: Any):
        self.config = config
        self.logger = logger
        self.v4_cfg = config.get("qlib_v4", {})

    def run(
        self,
        panel: pd.DataFrame,
        out_dir: Path | str,
        qlib_env_status: dict[str, Any] | None = None,
        qlib_data_status: dict[str, Any] | None = None,
    ) -> dict[str, pd.DataFrame]:
        out_path = ensure_dir(out_dir)
        pred_dir = ensure_dir(out_path / "predictions")
        metrics_dir = ensure_dir(out_path / "metrics")
        config_dir = ensure_dir(out_path / "configs")
        ensure_dir(out_path / "logs")
        qlib_env_status = qlib_env_status or {}
        qlib_data_status = qlib_data_status or {}

        model_panel = self._prepare_panel(panel)
        if model_panel.empty:
            empty = pd.DataFrame()
            for name in ("model_runs", "signal_ic_summary", "signal_rank_ic_summary", "model_metric_summary", "signal_quality_by_model", "yearly_signal_quality", "regime_signal_quality"):
                save_dataframe(empty, metrics_dir / f"{name}.csv" if name != "model_runs" else out_path / "model_runs.csv")
            return {
                "model_runs": empty,
                "signal_quality": empty,
                "predictions_index": empty,
                "yearly_signal_quality": empty,
                "regime_signal_quality": empty,
            }

        feature_sets = self._feature_sets(model_panel)
        models = self._build_models()
        labels = self._label_columns(model_panel)
        max_runs = int(self.v4_cfg.get("max_model_runs", 24))
        run_rows: list[dict[str, Any]] = []
        prediction_index_rows: list[dict[str, Any]] = []
        ic_rows: list[pd.DataFrame] = []
        rank_ic_rows: list[pd.DataFrame] = []
        quality_rows: list[dict[str, Any]] = []
        yearly_rows: list[pd.DataFrame] = []
        regime_rows: list[pd.DataFrame] = []
        completed = 0

        for feature_set_name, feature_cols in feature_sets.items():
            usable_cols = list(dict.fromkeys([col for col in feature_cols if col in model_panel.columns]))
            if not usable_cols:
                continue
            for label_name in labels:
                required_cols = [label_name, "close", "asset_return_1d", "QQQ_trend"]
                prepared_cols = list(dict.fromkeys(usable_cols + [col for col in required_cols if col in model_panel.columns]))
                prepared = model_panel[prepared_cols].replace([np.inf, -np.inf], np.nan)
                prepared = prepared.dropna(subset=[label_name])
                split = self._split_frame(prepared)
                if len(split["train"]) < int(self.v4_cfg.get("min_train_rows", 1500)) or len(split["test"]) < 200:
                    continue
                for model_name, model in models.items():
                    if completed >= max_runs:
                        break
                    run_id = self._run_id(feature_set_name, model_name, label_name, completed)
                    self.logger.info(f"v4 model run {run_id}: {feature_set_name}/{model_name}/{label_name}")
                    try:
                        train_x = split["train"][usable_cols]
                        train_y = split["train"][label_name]
                        model.fit(train_x, train_y)
                        pred_parts = []
                        for segment_name, segment_df in split.items():
                            if segment_df.empty:
                                continue
                            segment_pred = pd.DataFrame(
                                {
                                    "date": segment_df.index.get_level_values("date"),
                                    "ticker": segment_df.index.get_level_values("ticker"),
                                    "score": model.predict(segment_df[usable_cols]),
                                    "label_value": segment_df[label_name].to_numpy(dtype=float),
                                    "segment": segment_name,
                                }
                            )
                            pred_parts.append(segment_pred)
                        pred_df = pd.concat(pred_parts, ignore_index=True).sort_values(["date", "ticker"])
                    except Exception as exc:
                        self.logger.warning(f"v4 model run failed {feature_set_name}/{model_name}/{label_name}: {exc}")
                        run_rows.append(
                            {
                                "run_id": run_id,
                                "feature_set": feature_set_name,
                                "model": model_name,
                                "label": label_name,
                                "status": "failed",
                                "failure_reason": str(exc),
                                "feature_count": len(usable_cols),
                            }
                        )
                        completed += 1
                        continue

                    pred_file = pred_dir / f"pred_{run_id}.parquet"
                    save_parquet(pred_df, pred_file)
                    save_yaml(
                        {
                            "run_id": run_id,
                            "runtime_backend": self._runtime_backend(qlib_env_status, qlib_data_status),
                            "feature_set": feature_set_name,
                            "model": model_name,
                            "label": label_name,
                            "feature_count": len(usable_cols),
                            "feature_columns": usable_cols,
                            "split": self._split_config(),
                        },
                        config_dir / f"workflow_{run_id}.yaml",
                    )

                    quality = self._signal_quality(pred_df, label_name=label_name, run_id=run_id)
                    quality.update(
                        {
                            "feature_set": feature_set_name,
                            "model": model_name,
                            "label": label_name,
                            "feature_count": len(usable_cols),
                            "prediction_file": str(pred_file),
                            "runtime_backend": self._runtime_backend(qlib_env_status, qlib_data_status),
                        }
                    )
                    quality_rows.append(quality)
                    run_rows.append(
                        {
                            "run_id": run_id,
                            "feature_set": feature_set_name,
                            "model": model_name,
                            "label": label_name,
                            "status": "completed",
                            "failure_reason": "",
                            "feature_count": len(usable_cols),
                            "train_rows": len(split["train"]),
                            "valid_rows": len(split["valid"]),
                            "test_rows": len(split["test"]),
                            "prediction_file": str(pred_file),
                            "runtime_backend": self._runtime_backend(qlib_env_status, qlib_data_status),
                        }
                    )
                    prediction_index_rows.append(
                        {
                            "run_id": run_id,
                            "prediction_file": str(pred_file),
                            "feature_set": feature_set_name,
                            "model": model_name,
                            "label": label_name,
                        }
                    )
                    ic_rows.append(self._daily_ic(pred_df, run_id, method="pearson"))
                    rank_ic_rows.append(self._daily_ic(pred_df, run_id, method="spearman"))
                    yearly_rows.append(self._yearly_quality(pred_df, run_id))
                    regime_rows.append(self._regime_quality(pred_df, run_id, model_panel))
                    completed += 1
                if completed >= max_runs:
                    break
            if completed >= max_runs:
                break

        model_runs = pd.DataFrame(run_rows)
        signal_quality = pd.DataFrame(quality_rows).sort_values(["test_rank_icir", "test_icir"], ascending=[False, False]) if quality_rows else pd.DataFrame()
        prediction_index = pd.DataFrame(prediction_index_rows)
        signal_ic = pd.concat(ic_rows, ignore_index=True) if ic_rows else pd.DataFrame()
        signal_rank_ic = pd.concat(rank_ic_rows, ignore_index=True) if rank_ic_rows else pd.DataFrame()
        yearly_quality = pd.concat(yearly_rows, ignore_index=True) if yearly_rows else pd.DataFrame()
        regime_quality = pd.concat(regime_rows, ignore_index=True) if regime_rows else pd.DataFrame()

        save_dataframe(model_runs, out_path / "model_runs.csv")
        save_dataframe(signal_ic, metrics_dir / "signal_ic_summary.csv")
        save_dataframe(signal_rank_ic, metrics_dir / "signal_rank_ic_summary.csv")
        save_dataframe(signal_quality, metrics_dir / "model_metric_summary.csv")
        save_dataframe(signal_quality, metrics_dir / "signal_quality_by_model.csv")
        save_dataframe(yearly_quality, metrics_dir / "yearly_signal_quality.csv")
        save_dataframe(regime_quality, metrics_dir / "regime_signal_quality.csv")
        save_dataframe(prediction_index, pred_dir / "prediction_index.csv")
        return {
            "model_runs": model_runs,
            "signal_quality": signal_quality,
            "predictions_index": prediction_index,
            "yearly_signal_quality": yearly_quality,
            "regime_signal_quality": regime_quality,
        }

    def anchored_walk_forward_predictions(
        self,
        panel: pd.DataFrame,
        run_row: pd.Series | dict[str, Any],
        start_year: int = 2020,
        test_months: int = 12,
    ) -> pd.DataFrame:
        """Retrain an anchored expanding model and predict future windows."""
        row = dict(run_row)
        model_panel = self._prepare_panel(panel)
        feature_cols = self._feature_sets(model_panel).get(row.get("feature_set", ""), [])
        label_name = str(row.get("label", "forward_return_10d"))
        model_name = str(row.get("model", "ridge"))
        if not feature_cols or label_name not in model_panel.columns:
            return pd.DataFrame()

        result_rows: list[pd.DataFrame] = []
        max_date = model_panel.index.get_level_values("date").max()
        window_start = pd.Timestamp(f"{start_year}-01-01")
        while window_start < max_date:
            train_end = window_start - pd.Timedelta(days=1)
            test_end = min(window_start + pd.DateOffset(months=test_months) - pd.Timedelta(days=1), max_date)
            train = model_panel.loc[(slice(None), slice(None)), feature_cols + [label_name]].copy()
            train = train.loc[train.index.get_level_values("date") <= train_end].replace([np.inf, -np.inf], np.nan).dropna(subset=[label_name])
            test = model_panel.loc[(slice(None), slice(None)), feature_cols + [label_name]].copy()
            test = test.loc[(test.index.get_level_values("date") >= window_start) & (test.index.get_level_values("date") <= test_end)]
            test = test.replace([np.inf, -np.inf], np.nan).dropna(subset=[label_name])
            if len(train) >= int(self.v4_cfg.get("min_train_rows", 1500)) and len(test) > 0:
                models = self._build_models()
                model = models.get(model_name) or models.get("ridge")
                if model is None:
                    break
                try:
                    model.fit(train[feature_cols], train[label_name])
                    pred = pd.DataFrame(
                        {
                            "date": test.index.get_level_values("date"),
                            "ticker": test.index.get_level_values("ticker"),
                            "score": model.predict(test[feature_cols]),
                            "label_value": test[label_name].to_numpy(dtype=float),
                            "segment": "walk_forward_test",
                            "train_start": train.index.get_level_values("date").min(),
                            "train_end": train_end,
                            "test_start": window_start,
                            "test_end": test_end,
                            "feature_set": row.get("feature_set", ""),
                            "model": model_name,
                            "label": label_name,
                            "run_id": row.get("run_id", ""),
                        }
                    )
                    result_rows.append(pred)
                except Exception as exc:
                    self.logger.warning(f"v4 anchored walk-forward fit failed: {exc}")
            window_start = window_start + pd.DateOffset(months=test_months)
        return pd.concat(result_rows, ignore_index=True) if result_rows else pd.DataFrame()

    def _prepare_panel(self, panel: pd.DataFrame) -> pd.DataFrame:
        if panel.empty:
            return pd.DataFrame()
        prepared = panel.copy()
        if not isinstance(prepared.index, pd.MultiIndex):
            prepared = prepared.reset_index().set_index(["date", "ticker"]).sort_index()
        prepared.index = pd.MultiIndex.from_arrays(
            [pd.to_datetime(prepared.index.get_level_values("date")), prepared.index.get_level_values("ticker").astype(str)],
            names=["date", "ticker"],
        )
        prepared = prepared.sort_index()
        if "close" in prepared.columns:
            prepared["asset_return_1d"] = prepared.groupby(level="ticker")["close"].pct_change(fill_method=None)
            prepared["future_vol_10d"] = (
                prepared.groupby(level="ticker")["asset_return_1d"]
                .transform(lambda s: s.shift(-1).rolling(10).std().shift(-9) * np.sqrt(252))
            )
            if "forward_return_10d" in prepared.columns:
                prepared["risk_adj_10d"] = prepared["forward_return_10d"].div(prepared["future_vol_10d"].replace(0, np.nan))
            prepared["custom_close_ma20_gap"] = prepared.groupby(level="ticker")["close"].transform(lambda s: s.div(s.rolling(20).mean()).sub(1.0))
            prepared["custom_close_ma60_gap"] = prepared.groupby(level="ticker")["close"].transform(lambda s: s.div(s.rolling(60).mean()).sub(1.0))
            prepared["custom_high_low_range"] = prepared.get("high", prepared["close"]).sub(prepared.get("low", prepared["close"])).div(prepared["close"].replace(0, np.nan))
        if "volume" in prepared.columns:
            prepared["custom_volume_20_60"] = prepared.groupby(level="ticker")["volume"].transform(lambda s: s.rolling(20).mean().div(s.rolling(60).mean()).sub(1.0))
        return prepared.replace([np.inf, -np.inf], np.nan)

    def _feature_sets(self, panel: pd.DataFrame) -> dict[str, list[str]]:
        numeric_cols = [col for col in panel.columns if col not in BASE_BLACKLIST and pd.api.types.is_numeric_dtype(panel[col])]
        alpha158_terms = (
            "return_",
            "moving_average_gap",
            "price_above_ma",
            "ma_slope",
            "breakout",
            "distance_from",
            "rsi",
            "realized_vol",
            "atr",
            "parkinson",
            "downside",
            "volume",
            "turnover",
            "beta",
            "correlation",
            "trend",
            "risk_on",
        )
        alpha360_terms = ("return_", "moving_average_gap", "distance_from", "volatility", "volume", "custom_")
        custom_terms = ("custom_", "price_volume_corr", "volume_breakout", "volatility_contraction", "drawdown_from_peak", "max_dd_rolling")
        alpha158 = list(dict.fromkeys([col for col in numeric_cols if col.startswith(alpha158_terms) or any(term in col for term in alpha158_terms)]))
        alpha360 = list(dict.fromkeys([col for col in numeric_cols if col.startswith(alpha360_terms) or any(term in col for term in alpha360_terms)]))
        custom = sorted(set(alpha158 + [col for col in numeric_cols if col.startswith(custom_terms) or any(term in col for term in custom_terms)]))
        max_features = int(self.v4_cfg.get("max_features_per_set", 80))
        return {
            "alpha158_like": alpha158[:max_features],
            "alpha360_like": alpha360[:max_features],
            "alpha158_custom": custom[:max_features],
        }

    def _label_columns(self, panel: pd.DataFrame) -> list[str]:
        requested = self.v4_cfg.get("labels", ["forward_return_5d", "forward_return_10d", "forward_return_20d", "risk_adj_10d"])
        return [label for label in requested if label in panel.columns]

    def _split_config(self) -> dict[str, str]:
        cfg = self.config.get("validation", {})
        return {
            "train_start": cfg.get("preferred_train_start", "2012-01-01"),
            "train_end": self.v4_cfg.get("train_end", "2018-12-31"),
            "valid_start": self.v4_cfg.get("valid_start", "2019-01-01"),
            "valid_end": self.v4_cfg.get("valid_end", "2021-12-31"),
            "test_start": cfg.get("preferred_test_start", "2022-01-01"),
            "test_end": cfg.get("preferred_test_end", self.config.get("study_period", {}).get("end_date", "2026-04-24")),
        }

    def _split_frame(self, frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
        split = self._split_config()
        dates = frame.index.get_level_values("date")
        return {
            "train": frame.loc[(dates >= pd.Timestamp(split["train_start"])) & (dates <= pd.Timestamp(split["train_end"]))].copy(),
            "valid": frame.loc[(dates >= pd.Timestamp(split["valid_start"])) & (dates <= pd.Timestamp(split["valid_end"]))].copy(),
            "test": frame.loc[(dates >= pd.Timestamp(split["test_start"])) & (dates <= pd.Timestamp(split["test_end"]))].copy(),
        }

    def _build_models(self) -> dict[str, Any]:
        models: dict[str, Any] = {}
        try:
            from sklearn.impute import SimpleImputer
            from sklearn.linear_model import ElasticNet, Ridge
            from sklearn.neural_network import MLPRegressor
            from sklearn.pipeline import Pipeline
            from sklearn.preprocessing import StandardScaler

            models["ridge"] = Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler()), ("model", Ridge(alpha=5.0))])
            models["elasticnet"] = Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler()), ("model", ElasticNet(alpha=0.001, l1_ratio=0.2, max_iter=5000))])
            if bool(self.v4_cfg.get("enable_mlp", False)):
                models["mlp"] = Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler()), ("model", MLPRegressor(hidden_layer_sizes=(64, 32), max_iter=250, random_state=42))])
        except Exception as exc:
            self.logger.warning(f"sklearn fallback models unavailable: {exc}")
        try:
            from lightgbm import LGBMRegressor

            models["lightgbm"] = LGBMRegressor(n_estimators=180, learning_rate=0.04, num_leaves=31, subsample=0.85, colsample_bytree=0.85, random_state=42, verbose=-1)
        except Exception as exc:
            self.logger.warning(f"LightGBM unavailable for v4: {exc}")
        try:
            from xgboost import XGBRegressor

            models["xgboost"] = XGBRegressor(n_estimators=180, learning_rate=0.04, max_depth=4, subsample=0.85, colsample_bytree=0.85, random_state=42, n_jobs=2, objective="reg:squarederror")
        except Exception as exc:
            self.logger.warning(f"XGBoost unavailable for v4: {exc}")
        try:
            from catboost import CatBoostRegressor

            models["catboost"] = CatBoostRegressor(iterations=180, learning_rate=0.04, depth=5, loss_function="RMSE", random_seed=42, verbose=False)
        except Exception as exc:
            self.logger.info(f"CatBoost unavailable for v4, skipped: {exc}")
        allowed = self.v4_cfg.get("models", [])
        if allowed:
            models = {name: model for name, model in models.items() if name in set(allowed)}
        return models

    def _runtime_backend(self, env_status: dict[str, Any], data_status: dict[str, Any]) -> str:
        if env_status.get("qlib_import_ok") and data_status.get("true_qlib_data_used"):
            return "true_qlib_runtime_provider"
        if env_status.get("qlib_import_ok"):
            return "qlib_runtime_installed_local_panel_fallback"
        return "local_panel_fallback_no_qlib_runtime"

    @staticmethod
    def _run_id(feature_set: str, model: str, label: str, counter: int) -> str:
        raw = f"{feature_set}_{model}_{label}_{counter}"
        digest = hashlib.md5(raw.encode("utf-8")).hexdigest()[:6]
        return f"{feature_set}_{model}_{label}_{digest}"

    @staticmethod
    def _daily_ic(pred_df: pd.DataFrame, run_id: str, method: str) -> pd.DataFrame:
        rows = []
        for date, group in pred_df.groupby("date"):
            if group["score"].nunique(dropna=True) < 2 or group["label_value"].nunique(dropna=True) < 2:
                continue
            rows.append(
                {
                    "run_id": run_id,
                    "date": date,
                    "segment": group["segment"].iloc[0],
                    "ic_method": method,
                    "ic": group["score"].corr(group["label_value"], method=method),
                    "n": len(group),
                }
            )
        return pd.DataFrame(rows)

    @staticmethod
    def _signal_quality(pred_df: pd.DataFrame, label_name: str, run_id: str) -> dict[str, Any]:
        result: dict[str, Any] = {"run_id": run_id, "label_name": label_name}
        for segment in ("train", "valid", "test"):
            segment_df = pred_df.loc[pred_df["segment"] == segment]
            pearson = QlibModelLab._daily_ic(segment_df, run_id, "pearson") if not segment_df.empty else pd.DataFrame()
            spearman = QlibModelLab._daily_ic(segment_df, run_id, "spearman") if not segment_df.empty else pd.DataFrame()
            result[f"{segment}_ic_mean"] = float(pearson["ic"].mean()) if not pearson.empty else 0.0
            result[f"{segment}_ic_std"] = float(pearson["ic"].std(ddof=0)) if not pearson.empty else 0.0
            result[f"{segment}_icir"] = float(result[f"{segment}_ic_mean"] / result[f"{segment}_ic_std"]) if result[f"{segment}_ic_std"] else 0.0
            result[f"{segment}_rank_ic_mean"] = float(spearman["ic"].mean()) if not spearman.empty else 0.0
            rank_std = float(spearman["ic"].std(ddof=0)) if not spearman.empty else 0.0
            result[f"{segment}_rank_icir"] = float(result[f"{segment}_rank_ic_mean"] / rank_std) if rank_std else 0.0
            result[f"{segment}_ic_positive_ratio"] = float((pearson["ic"] > 0).mean()) if not pearson.empty else 0.0
        test_df = pred_df.loc[pred_df["segment"] == "test"].copy()
        if not test_df.empty:
            quant = test_df.groupby("date", group_keys=False).apply(_assign_quantiles)
            top = quant.loc[quant["quantile"] == 4, "label_value"].mean()
            bottom = quant.loc[quant["quantile"] == 0, "label_value"].mean()
            result["top_quantile_forward_return"] = float(top) if pd.notna(top) else 0.0
            result["bottom_quantile_forward_return"] = float(bottom) if pd.notna(bottom) else 0.0
            result["long_short_spread"] = result["top_quantile_forward_return"] - result["bottom_quantile_forward_return"]
            top_names = quant.loc[quant["quantile"] == 4].groupby("date")["ticker"].apply(lambda s: tuple(sorted(s)))
            result["turnover"] = float((top_names != top_names.shift(1)).mean()) if len(top_names) > 1 else 0.0
        else:
            result.update({"top_quantile_forward_return": 0.0, "bottom_quantile_forward_return": 0.0, "long_short_spread": 0.0, "turnover": 0.0})
        return result

    @staticmethod
    def _yearly_quality(pred_df: pd.DataFrame, run_id: str) -> pd.DataFrame:
        rows = []
        test_df = pred_df.loc[pred_df["segment"] == "test"].copy()
        if test_df.empty:
            return pd.DataFrame()
        test_df["year"] = pd.to_datetime(test_df["date"]).dt.year
        for year, group in test_df.groupby("year"):
            ic = QlibModelLab._daily_ic(group, run_id, "spearman")
            rows.append(
                {
                    "run_id": run_id,
                    "year": int(year),
                    "rank_ic_mean": float(ic["ic"].mean()) if not ic.empty else 0.0,
                    "rank_icir": float(ic["ic"].mean() / ic["ic"].std(ddof=0)) if not ic.empty and ic["ic"].std(ddof=0) else 0.0,
                    "row_count": int(len(group)),
                }
            )
        return pd.DataFrame(rows)

    @staticmethod
    def _regime_quality(pred_df: pd.DataFrame, run_id: str, model_panel: pd.DataFrame) -> pd.DataFrame:
        if pred_df.empty or "QQQ_trend" not in model_panel.columns:
            return pd.DataFrame()
        trend = model_panel["QQQ_trend"].groupby(level="date").mean()
        test_df = pred_df.loc[pred_df["segment"] == "test"].copy()
        test_df["regime"] = np.where(pd.to_datetime(test_df["date"]).map(trend).fillna(0.0) >= 0.0, "risk_on", "risk_off")
        rows = []
        for regime, group in test_df.groupby("regime"):
            ic = QlibModelLab._daily_ic(group, run_id, "spearman")
            rows.append(
                {
                    "run_id": run_id,
                    "regime": regime,
                    "rank_ic_mean": float(ic["ic"].mean()) if not ic.empty else 0.0,
                    "rank_icir": float(ic["ic"].mean() / ic["ic"].std(ddof=0)) if not ic.empty and ic["ic"].std(ddof=0) else 0.0,
                    "row_count": int(len(group)),
                }
            )
        return pd.DataFrame(rows)


def _assign_quantiles(group: pd.DataFrame) -> pd.DataFrame:
    out = group.copy()
    if len(out) < 5 or out["score"].nunique(dropna=True) < 5:
        out["quantile"] = pd.Series(out["score"].rank(method="first"), index=out.index).gt(out["score"].median()).astype(int) * 4
        return out
    out["quantile"] = pd.qcut(out["score"].rank(method="first"), 5, labels=False, duplicates="drop")
    return out
