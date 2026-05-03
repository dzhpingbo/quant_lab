"""Prepare local quant_lab OHLCV data for Qlib dump_bin conversion."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from quant_lab.us_stock_selection.data_loader import USDataLoader
from quant_lab.us_stock_selection.true_qlib_provider import POOL_A
from quant_lab.us_stock_selection.utils import PROJECT_ROOT, ensure_dir, save_dataframe, save_json, save_text


def prepare_local_qlib_dump_inputs(
    out_dir: Path | str,
    config: dict[str, Any],
    env_config: dict[str, Any],
    logger: Any | None = None,
    tickers: list[str] | None = None,
) -> dict[str, Any]:
    """Export one CSV per ticker in a shape accepted by qlib/scripts/dump_bin.py."""
    out_path = ensure_dir(out_dir)
    csv_dir = ensure_dir(out_path / "dump_bin_csv")
    tickers = tickers or POOL_A
    loader = USDataLoader(config, env_config, logger or _NullLogger())
    loaded = loader.load_many(tickers=tickers, start_date=config.get("study_period", {}).get("start_date"), end_date=config.get("study_period", {}).get("end_date"), allow_download=False)
    instruments = []
    calendar_values = set()
    exported = []
    missing = []
    for ticker, result in loaded.items():
        if result.data.empty:
            missing.append(ticker)
            continue
        frame = result.data.reset_index().rename(columns={"date": "date"})
        frame["symbol"] = ticker.lower()
        frame["factor"] = 1.0
        out_frame = frame.loc[:, ["date", "symbol", "open", "high", "low", "close", "volume", "factor"]].copy()
        out_frame["date"] = pd.to_datetime(out_frame["date"]).dt.strftime("%Y-%m-%d")
        save_dataframe(out_frame, csv_dir / f"{ticker.lower()}.csv")
        instruments.append({"symbol": ticker.lower(), "start": out_frame["date"].min(), "end": out_frame["date"].max()})
        calendar_values.update(out_frame["date"].tolist())
        exported.append(ticker)
    instruments_df = pd.DataFrame(instruments).sort_values("symbol") if instruments else pd.DataFrame(columns=["symbol", "start", "end"])
    calendar_df = pd.DataFrame({"date": sorted(calendar_values)})
    save_dataframe(instruments_df, out_path / "instruments.csv")
    save_dataframe(calendar_df, out_path / "calendar.csv")
    dump_command = (
        "python scripts/dump_bin.py dump_all "
        f"--csv_path {csv_dir} "
        "--qlib_dir ~/.qlib/qlib_data/us_data_local "
        "--include_fields open,high,low,close,volume,factor --freq day"
    )
    status = {
        "csv_dir": str(csv_dir),
        "exported_count": len(exported),
        "missing_count": len(missing),
        "exported_tickers": exported,
        "missing_tickers": missing,
        "factor_note": "factor is set to 1.0 because no reliable adjustment factor is available in the local CSV source.",
        "dump_bin_command": dump_command,
        "script_note": "pyqlib pip wheel may not include scripts/dump_bin.py; clone microsoft/qlib if the script is absent.",
        "clone_commands": [
            "git clone https://github.com/microsoft/qlib.git",
            "cd qlib",
            dump_command,
        ],
    }
    save_json(status, out_path / "local_conversion_status.json")
    save_text("\n".join(["# Local Qlib Bin Conversion", "", "```powershell", dump_command, "```", "", status["factor_note"]]), out_path / "local_conversion_commands.md")
    return status


class _NullLogger:
    def info(self, *_args, **_kwargs):
        return None

    def warning(self, *_args, **_kwargs):
        return None
