"""Precompute Qlib Handler features into parquet for fast walk-forward."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from quant_lab.us_stock_selection.local_qlib_provider_builder import default_local_provider_uri
from quant_lab.us_stock_selection.qlib_workflow_runner import LABEL_CONFIGS
from quant_lab.us_stock_selection.utils import ensure_dir, save_dataframe, save_json, save_parquet


DEFAULT_LABELS = {
    "label_5d": LABEL_CONFIGS["label_5d"][0][0],
    "label_20d": LABEL_CONFIGS["label_20d"][0][0],
}


def build_feature_cache(
    out_dir: Path | str,
    provider_uri: Path | str | None = None,
    feature_sets: list[str] | None = None,
    start_time: str = "2020-01-02",
    end_time: str = "2026-04-17",
    fit_start_time: str = "2020-01-02",
    fit_end_time: str = "2022-12-31",
    overwrite: bool = False,
) -> dict[str, Any]:
    """Build one parquet cache per Qlib feature set.

    Each cache stores date, instrument, feature_set, f000... feature columns,
    and label_5d/label_20d. Handler calculation happens once per feature set.
    """
    out_path = ensure_dir(out_dir)
    provider = Path(provider_uri).expanduser() if provider_uri else default_local_provider_uri()
    feature_sets = feature_sets or ["Alpha158", "Alpha360"]
    rows = []
    for feature_set in feature_sets:
        cache_file = out_path / f"{feature_set.lower()}_cache.parquet"
        map_file = out_path / f"{feature_set.lower()}_feature_map.json"
        if cache_file.exists() and map_file.exists() and not overwrite:
            cached = pd.read_parquet(cache_file, columns=["date", "instrument", "feature_set", "label_5d", "label_20d"])
            row = {
                "feature_set": feature_set,
                "status": "cached",
                "cache_file": str(cache_file),
                "rows": int(len(cached)),
                "date_start": str(pd.to_datetime(cached["date"]).min().date()) if not cached.empty else None,
                "date_end": str(pd.to_datetime(cached["date"]).max().date()) if not cached.empty else None,
                "instrument_count": int(cached["instrument"].nunique()) if not cached.empty else 0,
                "feature_count": int(len(load_feature_columns(map_file))),
                "error": "",
            }
            rows.append(row)
            continue
        try:
            frame, feature_map = _compute_handler_cache(
                provider=provider,
                feature_set=feature_set,
                start_time=start_time,
                end_time=end_time,
                fit_start_time=fit_start_time,
                fit_end_time=fit_end_time,
            )
            save_parquet(frame, cache_file)
            save_json(feature_map, map_file)
            rows.append(
                {
                    "feature_set": feature_set,
                    "status": "completed",
                    "cache_file": str(cache_file),
                    "rows": int(len(frame)),
                    "date_start": str(pd.to_datetime(frame["date"]).min().date()) if not frame.empty else None,
                    "date_end": str(pd.to_datetime(frame["date"]).max().date()) if not frame.empty else None,
                    "instrument_count": int(frame["instrument"].nunique()) if not frame.empty else 0,
                    "feature_count": int(len(feature_map["feature_columns"])),
                    "label_5d_non_na": int(frame["label_5d"].notna().sum()) if "label_5d" in frame else 0,
                    "label_20d_non_na": int(frame["label_20d"].notna().sum()) if "label_20d" in frame else 0,
                    "error": "",
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "feature_set": feature_set,
                    "status": "failed",
                    "cache_file": str(cache_file),
                    "rows": 0,
                    "date_start": None,
                    "date_end": None,
                    "instrument_count": 0,
                    "feature_count": 0,
                    "error": str(exc),
                }
            )
    status_df = pd.DataFrame(rows)
    save_dataframe(status_df, out_path / "feature_cache_status.csv")
    save_json({"provider_uri": str(provider), "feature_sets": feature_sets, "rows": rows}, out_path / "feature_cache_status.json")
    return {"status": status_df, "out_dir": str(out_path)}


def load_feature_cache(cache_dir: Path | str, feature_set: str) -> tuple[pd.DataFrame, list[str]]:
    """Load a feature cache and return frame plus feature columns."""
    base = Path(cache_dir)
    cache_file = base / f"{feature_set.lower()}_cache.parquet"
    map_file = base / f"{feature_set.lower()}_feature_map.json"
    if not cache_file.exists():
        raise FileNotFoundError(f"feature cache not found: {cache_file}")
    frame = pd.read_parquet(cache_file)
    frame["date"] = pd.to_datetime(frame["date"])
    return frame, load_feature_columns(map_file)


def load_feature_columns(map_file: Path | str) -> list[str]:
    with Path(map_file).open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return list(data.get("feature_columns", []))


def _compute_handler_cache(
    provider: Path,
    feature_set: str,
    start_time: str,
    end_time: str,
    fit_start_time: str,
    fit_end_time: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    import qlib
    from qlib.config import REG_US
    from qlib.contrib.data.handler import Alpha158, Alpha360
    from qlib.data.dataset import DatasetH
    from qlib.data.dataset.handler import DataHandlerLP

    qlib.init(provider_uri=str(provider), region=REG_US, expression_cache=None, dataset_cache=None)
    cls = Alpha360 if feature_set == "Alpha360" else Alpha158
    label_config = (list(DEFAULT_LABELS.values()), list(DEFAULT_LABELS.keys()))
    handler = cls(
        instruments="all",
        start_time=start_time,
        end_time=end_time,
        fit_start_time=fit_start_time,
        fit_end_time=fit_end_time,
        label=label_config,
    )
    dataset = DatasetH(handler=handler, segments={"all": (start_time, end_time)})
    data = dataset.prepare("all", col_set=["feature", "label"], data_key=DataHandlerLP.DK_L)
    if data.empty:
        raise ValueError(f"{feature_set} Handler returned empty data")

    feature_frame = data["feature"].replace([np.inf, -np.inf], np.nan)
    label_frame = data["label"].replace([np.inf, -np.inf], np.nan)
    feature_columns = [f"f{i:04d}" for i in range(feature_frame.shape[1])]
    original_columns = [str(col) for col in feature_frame.columns]
    feature_frame = feature_frame.copy()
    feature_frame.columns = feature_columns
    label_frame = label_frame.copy()
    if len(label_frame.columns) >= 2:
        label_frame = label_frame.iloc[:, :2]
        label_frame.columns = ["label_5d", "label_20d"]
    elif len(label_frame.columns) == 1:
        label_frame.columns = ["label_5d"]
        label_frame["label_20d"] = np.nan
    else:
        label_frame["label_5d"] = np.nan
        label_frame["label_20d"] = np.nan

    idx = data.index.to_frame(index=False)
    date_col = "datetime" if "datetime" in idx.columns else idx.columns[-1]
    inst_col = "instrument" if "instrument" in idx.columns else idx.columns[0]
    out = pd.concat([feature_frame.reset_index(drop=True), label_frame.reset_index(drop=True)], axis=1)
    out.insert(0, "feature_set", feature_set)
    out.insert(0, "instrument", idx[inst_col].astype(str).str.upper().to_numpy())
    out.insert(0, "date", pd.to_datetime(idx[date_col]).to_numpy())
    out = out.sort_values(["date", "instrument"]).reset_index(drop=True)
    feature_map = {
        "feature_set": feature_set,
        "feature_columns": feature_columns,
        "original_feature_columns": dict(zip(feature_columns, original_columns)),
        "label_expressions": DEFAULT_LABELS,
        "label_note": "Labels are generated by Qlib Handler and shifted forward via Ref($close, -N) / Ref($close, -1) - 1.",
        "provider_uri": str(provider),
    }
    return out, feature_map
