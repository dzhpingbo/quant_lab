"""Helpers for exporting Qlib workflow predictions into portfolio inputs."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from quant_lab.us_stock_selection.utils import ensure_dir, save_dataframe, save_parquet


def combine_prediction_files(prediction_index: pd.DataFrame, out_dir: Path | str) -> pd.DataFrame:
    """Combine individual prediction parquet files into one long audit file."""
    out_path = ensure_dir(out_dir)
    parts = []
    for row in prediction_index.to_dict(orient="records"):
        pred_file = Path(str(row.get("prediction_file", "")))
        if not pred_file.exists():
            continue
        frame = pd.read_parquet(pred_file)
        for key in ["run_id", "feature_set", "model", "label"]:
            if key in row and key not in frame.columns:
                frame[key] = row[key]
        parts.append(frame)
    combined = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    save_parquet(combined, out_path / "combined_predictions.parquet")
    save_dataframe(combined.head(5000), out_path / "combined_predictions_sample.csv")
    return combined
