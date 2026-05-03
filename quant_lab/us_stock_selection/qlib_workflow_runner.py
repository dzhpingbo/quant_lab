"""Run local-provider Qlib Handler workflows and export predictions."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from quant_lab.us_stock_selection.local_qlib_provider_builder import V6_POOL_A, default_local_provider_uri
from quant_lab.us_stock_selection.utils import ensure_dir, save_dataframe, save_json, save_parquet, save_text, save_yaml


LABEL_CONFIGS = {
    "label_5d": (["Ref($close, -6) / Ref($close, -1) - 1"], ["LABEL0"]),
    "label_20d": (["Ref($close, -21) / Ref($close, -1) - 1"], ["LABEL0"]),
}


def run_local_qlib_workflows(
    out_dir: Path | str,
    provider_uri: Path | str | None = None,
    feature_sets: list[str] | None = None,
    models: list[str] | None = None,
    labels: list[str] | None = None,
    max_runs: int = 12,
    attempt_qrun: bool = True,
) -> dict[str, pd.DataFrame]:
    """Run Qlib-native workflows by code and attempt qrun for auditability."""
    out_path = ensure_dir(out_dir)
    pred_dir = ensure_dir(out_path / "predictions")
    log_dir = ensure_dir(out_path / "qrun_logs")
    provider = Path(provider_uri).expanduser() if provider_uri else default_local_provider_uri()
    feature_sets = feature_sets or ["Alpha158", "Alpha360"]
    models = models or ["LGBModel", "Ridge", "ElasticNet"]
    labels = labels or ["label_5d", "label_20d"]

    runtime_status = _init_qlib(provider)
    split = _infer_split(provider)
    save_json({"provider_uri": str(provider), "runtime": runtime_status, "split": split}, out_path / "workflow_runtime_status.json")

    yaml_rows = []
    for fs in feature_sets:
        for label_name in labels:
            yaml_path = out_path / f"workflow_lgb_{fs.lower()}_{label_name}.yaml"
            save_yaml(_workflow_yaml(provider, fs, label_name, split), yaml_path)
            yaml_rows.append({"feature_set": fs, "label": label_name, "workflow_yaml": str(yaml_path)})
    qrun_status = _attempt_qrun(Path(yaml_rows[0]["workflow_yaml"]), log_dir) if attempt_qrun and yaml_rows else {"attempted": False, "reason": "disabled_or_no_yaml"}
    save_json(qrun_status, out_path / "qrun_status.json")

    if not runtime_status.get("qlib_init_success"):
        empty = pd.DataFrame()
        _write_empty_outputs(out_path)
        return {"model_runs": empty, "predictions_index": empty, "signal_quality": empty, "ic_by_year": empty}

    run_rows: list[dict[str, Any]] = []
    pred_index_rows: list[dict[str, Any]] = []
    quality_rows: list[dict[str, Any]] = []
    yearly_rows: list[pd.DataFrame] = []
    completed = 0

    for fs in feature_sets:
        for label_name in labels:
            if label_name not in LABEL_CONFIGS:
                continue
            handler_info = _build_dataset(provider, fs, label_name, split)
            if not handler_info.get("success"):
                run_rows.append(
                    {
                        "run_id": f"local_{fs}_handler_{label_name}",
                        "feature_set": fs,
                        "model": "handler",
                        "label": label_name,
                        "status": "failed",
                        "failure_reason": handler_info.get("error", "handler failed"),
                    }
                )
                continue
            dataset = handler_info["dataset"]
            for model_name in models:
                if completed >= max_runs:
                    break
                run_id = f"local_{fs}_{model_name}_{label_name}"
                pred_file = pred_dir / f"pred_{run_id}.parquet"
                status_row = {
                    "run_id": run_id,
                    "feature_set": fs,
                    "model": model_name,
                    "label": label_name,
                    "runtime_backend": "local_qlib_bin_provider",
                    "workflow_by_code": True,
                    "qrun_attempted": bool(qrun_status.get("attempted")),
                    "qrun_success": bool(qrun_status.get("success")),
                    "prediction_file": str(pred_file),
                }
                try:
                    pred_df, fit_info = _fit_predict(dataset, model_name)
                    if pred_df.empty:
                        raise ValueError("empty prediction frame")
                    pred_df.insert(0, "run_id", run_id)
                    save_parquet(pred_df, pred_file)
                    quality = signal_quality(pred_df)
                    quality.update(status_row)
                    quality_rows.append(quality)
                    yearly_rows.append(ic_by_year(pred_df, run_id))
                    pred_index_rows.append(
                        {
                            "run_id": run_id,
                            "prediction_file": str(pred_file),
                            "feature_set": fs,
                            "model": model_name,
                            "label": label_name,
                        }
                    )
                    status_row.update({"status": "completed", "failure_reason": "", **fit_info})
                except Exception as exc:
                    status_row.update({"status": "failed", "failure_reason": str(exc)})
                run_rows.append(status_row)
                completed += 1
            if completed >= max_runs:
                break
        if completed >= max_runs:
            break

    model_runs = pd.DataFrame(run_rows)
    pred_index = pd.DataFrame(pred_index_rows)
    quality_df = pd.DataFrame(quality_rows).sort_values(["test_rank_icir", "test_icir"], ascending=[False, False]) if quality_rows else pd.DataFrame()
    yearly_df = pd.concat(yearly_rows, ignore_index=True) if yearly_rows else pd.DataFrame()
    save_dataframe(model_runs, out_path / "model_runs.csv")
    save_dataframe(pred_index, pred_dir / "prediction_index.csv")
    save_dataframe(quality_df, out_path / "signal_quality.csv")
    save_dataframe(yearly_df, out_path / "ic_by_year.csv")
    save_dataframe(pd.DataFrame(yaml_rows), out_path / "workflow_status.csv")
    return {"model_runs": model_runs, "predictions_index": pred_index, "signal_quality": quality_df, "ic_by_year": yearly_df}


def signal_quality(pred_df: pd.DataFrame) -> dict[str, Any]:
    """Compute IC/RankIC and simple quantile diagnostics."""
    row: dict[str, Any] = {}
    for segment in ["train", "valid", "test"]:
        seg = pred_df.loc[pred_df["segment"] == segment].dropna(subset=["score", "label_value"])
        daily = seg.groupby("date").apply(_daily_corr, include_groups=False) if not seg.empty else pd.Series(dtype=float)
        rank_daily = seg.groupby("date").apply(_daily_rank_corr, include_groups=False) if not seg.empty else pd.Series(dtype=float)
        row[f"{segment}_ic_mean"] = float(daily.mean()) if not daily.empty else 0.0
        row[f"{segment}_ic_std"] = float(daily.std(ddof=0)) if not daily.empty else 0.0
        row[f"{segment}_icir"] = row[f"{segment}_ic_mean"] / row[f"{segment}_ic_std"] if row[f"{segment}_ic_std"] else 0.0
        row[f"{segment}_rank_ic_mean"] = float(rank_daily.mean()) if not rank_daily.empty else 0.0
        rank_std = float(rank_daily.std(ddof=0)) if not rank_daily.empty else 0.0
        row[f"{segment}_rank_icir"] = row[f"{segment}_rank_ic_mean"] / rank_std if rank_std else 0.0
        row[f"{segment}_ic_positive_ratio"] = float((daily > 0).mean()) if not daily.empty else 0.0
    test = pred_df.loc[pred_df["segment"] == "test"].dropna(subset=["score", "label_value"]).copy()
    if test.empty:
        row.update({"top_quantile_forward_return": 0.0, "bottom_quantile_forward_return": 0.0, "long_short_spread": 0.0, "turnover": 0.0})
        return row
    qs = test.groupby("date")["score"].transform(lambda s: pd.qcut(s.rank(method="first"), 5, labels=False, duplicates="drop") if s.notna().sum() >= 5 else np.nan)
    test["quantile"] = qs
    top = test.loc[test["quantile"] == test["quantile"].max(), "label_value"].mean()
    bottom = test.loc[test["quantile"] == test["quantile"].min(), "label_value"].mean()
    leaders = test.sort_values(["date", "score"], ascending=[True, False]).groupby("date").head(5)
    holdings = leaders.pivot_table(index="date", columns="ticker", values="score", aggfunc="last").notna().astype(float)
    turnover = holdings.diff().abs().sum(axis=1).mean() / max(holdings.sum(axis=1).mean(), 1e-9) if not holdings.empty else 0.0
    row.update(
        {
            "top_quantile_forward_return": float(top) if pd.notna(top) else 0.0,
            "bottom_quantile_forward_return": float(bottom) if pd.notna(bottom) else 0.0,
            "long_short_spread": float(top - bottom) if pd.notna(top) and pd.notna(bottom) else 0.0,
            "turnover": float(turnover),
        }
    )
    return row


def ic_by_year(pred_df: pd.DataFrame, run_id: str) -> pd.DataFrame:
    rows = []
    data = pred_df.dropna(subset=["score", "label_value"]).copy()
    if data.empty:
        return pd.DataFrame()
    data["year"] = pd.to_datetime(data["date"]).dt.year
    for (segment, year), frame in data.groupby(["segment", "year"]):
        daily = frame.groupby("date").apply(_daily_corr, include_groups=False)
        rows.append({"run_id": run_id, "segment": segment, "year": int(year), "ic_mean": float(daily.mean()), "icir": float(daily.mean() / daily.std(ddof=0)) if daily.std(ddof=0) else 0.0})
    return pd.DataFrame(rows)


def load_close_from_provider(provider_uri: Path | str, tickers: list[str] | None = None, start: str = "2020-01-01", end: str | None = None) -> pd.DataFrame:
    """Load close panel from local Qlib provider."""
    import qlib
    from qlib.config import REG_US
    from qlib.data import D

    provider = Path(provider_uri).expanduser()
    qlib.init(provider_uri=str(provider), region=REG_US, expression_cache=None, dataset_cache=None)
    cal = D.calendar(freq="day")
    end = end or (pd.Timestamp(cal[-1]).date().isoformat() if len(cal) else None)
    tickers = [t.upper() for t in (tickers or V6_POOL_A)]
    frame = D.features(tickers, ["$close"], start_time=start, end_time=end, freq="day").reset_index()
    if frame.empty:
        return pd.DataFrame()
    frame["date"] = pd.to_datetime(frame["datetime"] if "datetime" in frame.columns else frame["date"])
    frame["ticker"] = frame["instrument"].astype(str).str.upper()
    close = frame.pivot_table(index="date", columns="ticker", values="$close", aggfunc="last").sort_index().ffill()
    close.index.name = "date"
    return close


def _init_qlib(provider: Path) -> dict[str, Any]:
    status = {"provider_uri": str(provider), "provider_exists": provider.exists(), "qlib_init_success": False, "error": ""}
    try:
        import qlib
        from qlib.config import REG_US

        qlib.init(provider_uri=str(provider), region=REG_US, expression_cache=None, dataset_cache=None)
        status["qlib_init_success"] = True
    except Exception as exc:
        status["error"] = str(exc)
    return status


def _infer_split(provider: Path) -> dict[str, str]:
    import qlib
    from qlib.config import REG_US
    from qlib.data import D

    qlib.init(provider_uri=str(provider), region=REG_US, expression_cache=None, dataset_cache=None)
    cal = D.calendar(freq="day")
    start = pd.Timestamp(cal[0]).date().isoformat()
    end = pd.Timestamp(cal[-1]).date().isoformat()
    if pd.Timestamp(start) <= pd.Timestamp("2012-01-01"):
        split = {
            "start_time": start,
            "end_time": end,
            "fit_start_time": "2012-01-01",
            "fit_end_time": "2018-12-31",
            "train_start": "2012-01-01",
            "train_end": "2018-12-31",
            "valid_start": "2019-01-01",
            "valid_end": "2021-12-31",
            "test_start": "2022-01-01",
            "test_end": end,
            "split_note": "standard split",
        }
    else:
        split = {
            "start_time": start,
            "end_time": end,
            "fit_start_time": start,
            "fit_end_time": "2022-12-31",
            "train_start": start,
            "train_end": "2022-12-31",
            "valid_start": "2023-01-01",
            "valid_end": "2023-12-31",
            "test_start": "2024-01-01",
            "test_end": end,
            "split_note": "short local provider split: train 2020-2022, valid 2023, test 2024-2026",
        }
    return split


def _build_dataset(provider: Path, feature_set: str, label_name: str, split: dict[str, str]) -> dict[str, Any]:
    try:
        import qlib
        from qlib.config import REG_US
        from qlib.contrib.data.handler import Alpha158, Alpha360
        from qlib.data.dataset import DatasetH

        qlib.init(provider_uri=str(provider), region=REG_US, expression_cache=None, dataset_cache=None)
        cls = Alpha360 if feature_set == "Alpha360" else Alpha158
        handler = cls(
            instruments="all",
            start_time=split["start_time"],
            end_time=split["end_time"],
            fit_start_time=split["fit_start_time"],
            fit_end_time=split["fit_end_time"],
            label=LABEL_CONFIGS[label_name],
        )
        dataset = DatasetH(
            handler=handler,
            segments={
                "train": (split["train_start"], split["train_end"]),
                "valid": (split["valid_start"], split["valid_end"]),
                "test": (split["test_start"], split["test_end"]),
            },
        )
        return {"success": True, "dataset": dataset}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def _fit_predict(dataset: Any, model_name: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    if model_name == "ElasticNet":
        return _fit_predict_sklearn(dataset, estimator="ElasticNet")
    if model_name == "Ridge":
        model = _make_qlib_ridge()
    else:
        model = _make_lgb_model()

    signal_record_status = {"signal_record_success": False, "signal_record_error": ""}
    try:
        from qlib.workflow import R
        from qlib.workflow.record_temp import SignalRecord

        with R.start(experiment_name="us_stock_selection_v6"):
            if model_name == "LGBModel":
                model.fit(dataset, verbose_eval=False)
            else:
                model.fit(dataset)
            recorder = R.get_recorder()
            try:
                SignalRecord(model, dataset, recorder).generate()
                signal_record_status["signal_record_success"] = True
            except Exception as exc:
                signal_record_status["signal_record_error"] = str(exc)
    except Exception:
        if model_name == "LGBModel":
            model.fit(dataset, verbose_eval=False)
        else:
            model.fit(dataset)

    frames = []
    for segment in ["train", "valid", "test"]:
        pred = model.predict(dataset, segment=segment)
        labels = _segment_label(dataset, segment)
        frames.append(_series_to_prediction_frame(pred, labels, segment))
    return pd.concat(frames, ignore_index=True), {"model_backend": "qlib_model", **signal_record_status}


def _fit_predict_sklearn(dataset: Any, estimator: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import ElasticNet
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    from qlib.data.dataset.handler import DataHandlerLP

    train = dataset.prepare("train", col_set=["feature", "label"], data_key=DataHandlerLP.DK_L).dropna(subset=[("label", "LABEL0")])
    x_train = train["feature"].replace([np.inf, -np.inf], np.nan)
    y_train = train["label"].iloc[:, 0].astype(float)
    model = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), ElasticNet(alpha=0.001, l1_ratio=0.25, max_iter=5000, random_state=42))
    model.fit(x_train, y_train)
    frames = []
    for segment in ["train", "valid", "test"]:
        data = dataset.prepare(segment, col_set=["feature", "label"], data_key=DataHandlerLP.DK_L)
        x = data["feature"].replace([np.inf, -np.inf], np.nan)
        pred = pd.Series(model.predict(x), index=x.index)
        labels = data["label"].iloc[:, 0]
        frames.append(_series_to_prediction_frame(pred, labels, segment))
    return pd.concat(frames, ignore_index=True), {"model_backend": "sklearn_elasticnet", "signal_record_success": False, "signal_record_error": "sklearn fallback does not support Qlib SignalRecord"}


def _segment_label(dataset: Any, segment: str) -> pd.Series:
    from qlib.data.dataset.handler import DataHandlerLP

    label_df = dataset.prepare(segment, col_set="label", data_key=DataHandlerLP.DK_L)
    return label_df.iloc[:, 0]


def _series_to_prediction_frame(pred: pd.Series, labels: pd.Series, segment: str) -> pd.DataFrame:
    data = pd.DataFrame({"score": pred.astype(float)})
    data["label_value"] = labels.reindex(data.index).astype(float)
    idx = data.index.to_frame(index=False)
    if "datetime" in idx.columns:
        data["date"] = pd.to_datetime(idx["datetime"]).to_numpy()
    elif "date" in idx.columns:
        data["date"] = pd.to_datetime(idx["date"]).to_numpy()
    else:
        data["date"] = pd.to_datetime(idx.iloc[:, -1]).to_numpy()
    if "instrument" in idx.columns:
        data["ticker"] = idx["instrument"].astype(str).str.upper().to_numpy()
    else:
        data["ticker"] = idx.iloc[:, 0].astype(str).str.upper().to_numpy()
    data["segment"] = segment
    return data.reset_index(drop=True).loc[:, ["date", "ticker", "score", "label_value", "segment"]]


def _make_lgb_model() -> Any:
    from qlib.contrib.model.gbdt import LGBModel

    return LGBModel(
        loss="mse",
        learning_rate=0.05,
        num_leaves=31,
        max_depth=6,
        subsample=0.85,
        colsample_bytree=0.85,
        lambda_l1=0.1,
        lambda_l2=1.0,
        num_threads=4,
        num_boost_round=120,
        early_stopping_rounds=20,
    )


def _make_qlib_ridge() -> Any:
    from qlib.contrib.model.linear import LinearModel

    return LinearModel(estimator="ridge", alpha=1.0, fit_intercept=True)


def _daily_corr(frame: pd.DataFrame) -> float:
    if frame["score"].nunique() < 2 or frame["label_value"].nunique() < 2:
        return np.nan
    return float(frame["score"].corr(frame["label_value"]))


def _daily_rank_corr(frame: pd.DataFrame) -> float:
    if frame["score"].nunique() < 2 or frame["label_value"].nunique() < 2:
        return np.nan
    return float(frame["score"].rank().corr(frame["label_value"].rank()))


def _workflow_yaml(provider: Path, feature_set: str, label_name: str, split: dict[str, str]) -> dict[str, Any]:
    label = LABEL_CONFIGS[label_name]
    return {
        "qlib_init": {"provider_uri": str(provider), "region": "us"},
        "market": "all",
        "task": {
            "model": {
                "class": "LGBModel",
                "module_path": "qlib.contrib.model.gbdt",
                "kwargs": {"loss": "mse", "learning_rate": 0.05, "num_leaves": 31, "num_boost_round": 80, "early_stopping_rounds": 20},
            },
            "dataset": {
                "class": "DatasetH",
                "module_path": "qlib.data.dataset",
                "kwargs": {
                    "handler": {
                        "class": feature_set,
                        "module_path": "qlib.contrib.data.handler",
                        "kwargs": {
                            "instruments": "all",
                            "start_time": split["start_time"],
                            "end_time": split["end_time"],
                            "fit_start_time": split["fit_start_time"],
                            "fit_end_time": split["fit_end_time"],
                            "label": label,
                        },
                    },
                    "segments": {
                        "train": [split["train_start"], split["train_end"]],
                        "valid": [split["valid_start"], split["valid_end"]],
                        "test": [split["test_start"], split["test_end"]],
                    },
                },
            },
            "record": [
                {"class": "SignalRecord", "module_path": "qlib.workflow.record_temp", "kwargs": {"model": "<MODEL>", "dataset": "<DATASET>"}},
            ],
        },
    }


def _attempt_qrun(yaml_path: Path, log_dir: Path, timeout_sec: int = 180) -> dict[str, Any]:
    qrun = shutil.which("qrun")
    status = {"attempted": bool(qrun), "qrun_path": qrun or "", "workflow_yaml": str(yaml_path), "success": False, "returncode": None, "stdout_tail": "", "stderr_tail": ""}
    if not qrun:
        status["stderr_tail"] = "qrun executable not found"
        return status
    try:
        proc = subprocess.run([qrun, str(yaml_path)], capture_output=True, text=True, timeout=timeout_sec, check=False)
        status.update({"returncode": int(proc.returncode), "success": proc.returncode == 0, "stdout_tail": proc.stdout[-6000:], "stderr_tail": proc.stderr[-6000:]})
        save_text(proc.stdout + "\n\nSTDERR:\n" + proc.stderr, log_dir / f"{yaml_path.stem}.log")
    except Exception as exc:
        status.update({"returncode": -1, "stderr_tail": str(exc)})
        save_text(str(exc), log_dir / f"{yaml_path.stem}.log")
    return status


def _write_empty_outputs(out_path: Path) -> None:
    empty = pd.DataFrame()
    save_dataframe(empty, out_path / "model_runs.csv")
    save_dataframe(empty, out_path / "predictions" / "prediction_index.csv")
    save_dataframe(empty, out_path / "signal_quality.csv")
    save_dataframe(empty, out_path / "ic_by_year.csv")
