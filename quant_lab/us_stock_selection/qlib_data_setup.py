"""Qlib data readiness and qlib-like local panel export for v4."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from quant_lab.us_stock_selection.qlib_env import default_provider_uri
from quant_lab.us_stock_selection.utils import ensure_dir, save_dataframe, save_json, save_parquet


LABEL_COLUMNS = {
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


def prepare_qlib_data_status(
    out_dir: Path | str,
    qlib_env_status: dict[str, Any],
    feature_map: dict[str, pd.DataFrame] | None = None,
    loaded_data: dict[str, pd.DataFrame] | None = None,
    universe_df: pd.DataFrame | None = None,
    provider_uri: str | Path | None = None,
    logger: Any | None = None,
) -> tuple[dict[str, Any], pd.DataFrame]:
    """Inspect true Qlib data and always export a local fallback panel for v4 models."""
    out_path = ensure_dir(out_dir)
    provider_path = Path(provider_uri).expanduser() if provider_uri else default_provider_uri()
    feature_map = feature_map or {}
    loaded_data = loaded_data or {}
    universe_df = universe_df if universe_df is not None else pd.DataFrame()

    fallback_panel = build_local_qlib_like_panel(feature_map, loaded_data)
    sample = fallback_panel.head(250).copy()
    if not sample.empty:
        save_dataframe(sample.reset_index(), out_path / "qlib_data_sample.csv")
        save_parquet(fallback_panel.reset_index(), out_path / "fallback_qlib_like_panel.parquet")
    else:
        save_dataframe(pd.DataFrame(), out_path / "qlib_data_sample.csv")

    true_qlib_ready = bool(qlib_env_status.get("runtime_status") == "ready_with_provider")
    status: dict[str, Any] = {
        "provider_uri": str(provider_path),
        "qlib_runtime_installed": bool(qlib_env_status.get("qlib_import_ok")),
        "qlib_provider_exists": bool(provider_path.exists()),
        "qlib_provider_readable": bool(qlib_env_status.get("provider_readable")),
        "true_qlib_data_used": true_qlib_ready,
        "data_mode": "true_qlib_provider" if true_qlib_ready else "fallback_qlib_like_panel",
        "fallback_panel_rows": int(len(fallback_panel)),
        "fallback_panel_tickers": int(fallback_panel.index.get_level_values("ticker").nunique()) if not fallback_panel.empty else 0,
        "pool_a_tickers": sorted(universe_df["ticker"].unique().tolist()) if not universe_df.empty and "ticker" in universe_df else [],
        "download_command": "python -m qlib.cli.data qlib_data --target_dir ~/.qlib/qlib_data/us_data --region us",
        "fallback_note": (
            "Qlib runtime is available but US provider data is missing or unreadable; "
            "v4 used local yfinance/legacy OHLCV data to build a qlib-like cross-sectional panel."
            if not true_qlib_ready
            else "Qlib provider is readable; local fallback panel is still exported for audit."
        ),
    }

    if true_qlib_ready:
        true_sample = try_read_true_qlib_sample(provider_path, universe_df, logger=logger)
        if not true_sample.empty:
            save_dataframe(true_sample, out_path / "qlib_true_provider_sample.csv")
            status["true_provider_sample_rows"] = int(len(true_sample))
    else:
        status["true_provider_sample_rows"] = 0

    save_json(status, out_path / "qlib_data_status.json")
    return status, fallback_panel


def build_local_qlib_like_panel(
    feature_map: dict[str, pd.DataFrame],
    loaded_data: dict[str, pd.DataFrame] | None = None,
) -> pd.DataFrame:
    """Create a MultiIndex date/ticker panel with OHLCV, features, and shifted labels."""
    rows: list[pd.DataFrame] = []
    for ticker, features in feature_map.items():
        if features is None or features.empty:
            continue
        frame = features.copy()
        frame["ticker"] = ticker
        frame.index = pd.to_datetime(frame.index)
        frame.index.name = "date"
        rows.append(frame)

    if not rows:
        return pd.DataFrame()

    panel = pd.concat(rows, axis=0).sort_index()
    panel = panel.reset_index().set_index(["date", "ticker"]).sort_index()
    numeric_cols = [col for col in panel.columns if pd.api.types.is_numeric_dtype(panel[col])]
    panel = panel[numeric_cols].replace([np.inf, -np.inf], np.nan)
    return panel


def try_read_true_qlib_sample(
    provider_uri: Path,
    universe_df: pd.DataFrame,
    logger: Any | None = None,
) -> pd.DataFrame:
    """Read a small OHLCV sample from a true Qlib provider when available."""
    try:
        import qlib
        from qlib.config import REG_US
        from qlib.data import D

        qlib.init(provider_uri=str(provider_uri), region=REG_US, expression_cache=None, dataset_cache=None)
        tickers = universe_df["ticker"].head(5).tolist() if not universe_df.empty and "ticker" in universe_df else ["AAPL", "MSFT"]
        fields = ["$open", "$high", "$low", "$close", "$volume"]
        sample = D.features(tickers, fields, start_time="2022-01-01", end_time="2022-01-31", freq="day")
        return sample.reset_index()
    except Exception as exc:
        if logger:
            logger.warning(f"True Qlib data sample read failed: {exc}")
        return pd.DataFrame()
