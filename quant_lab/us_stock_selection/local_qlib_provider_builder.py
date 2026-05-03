"""Build and validate a local Qlib bin provider from quant_lab US OHLCV data."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from quant_lab.us_stock_selection.data_loader import USDataLoader
from quant_lab.us_stock_selection.true_qlib_provider import POOL_A
from quant_lab.us_stock_selection.utils import PROJECT_ROOT, ensure_dir, save_dataframe, save_json, save_text


V6_POOL_A = list(
    dict.fromkeys(
        POOL_A
        + [
            "INTC",
            "MSTR",
            "SHOP",
        ]
    )
)


def default_local_provider_uri() -> Path:
    """Return the v6 local provider location."""
    return Path.home() / ".qlib" / "qlib_data" / "us_data_local_2026"


def qlib_source_candidates() -> list[Path]:
    """Candidate microsoft/qlib source roots."""
    return [
        PROJECT_ROOT.parent / "qlib",
        PROJECT_ROOT / "external" / "qlib",
        Path.home() / "qlib",
    ]


def locate_or_clone_qlib_source(out_dir: Path | str, clone_if_missing: bool = True, timeout_sec: int = 600) -> dict[str, Any]:
    """Locate or clone microsoft/qlib source so scripts/dump_bin.py is available."""
    out_path = ensure_dir(out_dir)
    status: dict[str, Any] = {
        "candidates": [str(path) for path in qlib_source_candidates()],
        "selected_source": "",
        "source_exists": False,
        "dump_bin_py": "",
        "get_data_py": "",
        "dump_bin_exists": False,
        "get_data_exists": False,
        "git_available": shutil.which("git") is not None,
        "clone_attempted": False,
        "clone_returncode": None,
        "clone_stdout_tail": "",
        "clone_stderr_tail": "",
        "manual_clone_commands": [
            "git clone https://github.com/microsoft/qlib.git external/qlib",
        ],
    }
    selected = _find_qlib_source()
    if selected is None and clone_if_missing and status["git_available"]:
        target = PROJECT_ROOT / "external" / "qlib"
        ensure_dir(target.parent)
        cmd = ["git", "clone", "https://github.com/microsoft/qlib.git", str(target)]
        status["clone_attempted"] = True
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec, check=False)
        status["clone_returncode"] = int(proc.returncode)
        status["clone_stdout_tail"] = proc.stdout[-4000:]
        status["clone_stderr_tail"] = proc.stderr[-4000:]
        selected = _find_qlib_source()

    if selected is not None:
        dump_bin = selected / "scripts" / "dump_bin.py"
        get_data = selected / "scripts" / "get_data.py"
        status.update(
            {
                "selected_source": str(selected),
                "source_exists": selected.exists(),
                "dump_bin_py": str(dump_bin),
                "get_data_py": str(get_data),
                "dump_bin_exists": dump_bin.exists(),
                "get_data_exists": get_data.exists(),
            }
        )

    save_json(status, out_path / "qlib_source_status.json")
    report = [
        "# Qlib Source Status",
        "",
        f"- selected_source: `{status['selected_source']}`",
        f"- dump_bin_exists: `{status['dump_bin_exists']}`",
        f"- get_data_exists: `{status['get_data_exists']}`",
        f"- git_available: `{status['git_available']}`",
        f"- clone_attempted: `{status['clone_attempted']}`",
        "",
        "Manual fallback:",
        "```powershell",
        *status["manual_clone_commands"],
        "```",
    ]
    save_text("\n".join(report), out_path / "qlib_source_report.md")
    return status


def build_local_qlib_provider(
    out_dir: Path | str,
    config: dict[str, Any],
    env_config: dict[str, Any],
    logger: Any,
    qlib_source_dir: Path | str | None = None,
    provider_uri: Path | str | None = None,
    tickers: list[str] | None = None,
    rebuild: bool = True,
) -> dict[str, Any]:
    """Prepare CSVs, run dump_bin, and validate the resulting local provider."""
    out_path = ensure_dir(out_dir)
    provider = Path(provider_uri).expanduser() if provider_uri else default_local_provider_uri()
    source = Path(qlib_source_dir).resolve() if qlib_source_dir else _find_qlib_source()
    if source is None:
        raise FileNotFoundError("microsoft/qlib source was not found; run 20_clone_qlib_source.py first.")

    prepared = prepare_local_provider_csvs(out_path / "prepared_csv", config, env_config, logger, tickers=tickers)
    dump_status = run_dump_bin(
        out_dir=out_path,
        prepared_csv_dir=Path(prepared["prepared_csv_dir"]),
        qlib_source_dir=source,
        provider_uri=provider,
        rebuild=rebuild,
    )
    health, sample = local_provider_health_check(out_path, provider, tickers=prepared["exported_tickers"])
    alpha_check = alpha_handler_health_check(out_path, provider, health)
    status = {
        "provider_uri": str(provider),
        "prepared": prepared,
        "dump_bin": dump_status,
        "provider_health": health,
        "alpha_handler_check": alpha_check,
        "local_provider_success": bool(
            dump_status.get("returncode") == 0
            and health.get("provider_readable")
            and alpha_check.get("Alpha158", {}).get("success")
            and alpha_check.get("Alpha360", {}).get("success")
        ),
    }
    save_json(status, out_path / "local_provider_build_status.json")
    return status


def prepare_local_provider_csvs(
    prepared_csv_dir: Path | str,
    config: dict[str, Any],
    env_config: dict[str, Any],
    logger: Any,
    tickers: list[str] | None = None,
) -> dict[str, Any]:
    """Export uppercase-symbol CSV files compatible with qlib/scripts/dump_bin.py."""
    csv_dir = ensure_dir(prepared_csv_dir)
    tickers = list(dict.fromkeys([t.upper() for t in (tickers or V6_POOL_A)]))
    start = "2020-01-01"
    end = config.get("study_period", {}).get("end_date", "2026-04-24")
    loader = USDataLoader(config, env_config, logger)
    loaded = loader.load_many(tickers, start_date=start, end_date=end, allow_download=False)
    rows: list[dict[str, Any]] = []
    exported: list[str] = []
    missing: list[str] = []
    all_dates: set[str] = set()

    for ticker, result in loaded.items():
        if result.data.empty:
            missing.append(ticker)
            continue
        frame = result.data.copy()
        frame = frame.loc[(frame.index >= pd.Timestamp(start)) & (frame.index <= pd.Timestamp(end))]
        frame = frame.replace([np.inf, -np.inf], np.nan)
        needed = ["open", "high", "low", "close", "volume"]
        frame = frame.dropna(subset=needed)
        frame = frame.loc[(frame[["open", "high", "low", "close"]] > 0).all(axis=1)]
        if frame.empty:
            missing.append(ticker)
            continue

        raw_close = frame["close"].astype(float)
        adj_close = frame["adj_close"].astype(float) if "adj_close" in frame.columns else raw_close
        factor = (adj_close / raw_close.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).fillna(1.0)
        if factor.sub(1.0).abs().median() < 1e-8:
            factor = pd.Series(1.0, index=frame.index)
            factor_note = "close appears already adjusted or adj_close unavailable; factor set to 1."
        else:
            factor_note = "OHLC adjusted by adj_close / close."

        out = pd.DataFrame(index=frame.index)
        out["symbol"] = ticker
        out["date"] = out.index.strftime("%Y-%m-%d")
        for col in ["open", "high", "low", "close"]:
            out[col] = frame[col].astype(float) * factor
        out["volume"] = frame["volume"].astype(float).clip(lower=0)
        out["factor"] = factor.astype(float)
        out = out.loc[:, ["symbol", "date", "open", "high", "low", "close", "volume", "factor"]]
        save_dataframe(out, csv_dir / f"{ticker}.csv")
        exported.append(ticker)
        all_dates.update(out["date"].tolist())
        rows.append(
            {
                "symbol": ticker,
                "path": str(result.path or ""),
                "start": out["date"].min(),
                "end": out["date"].max(),
                "rows": int(len(out)),
                "factor_note": factor_note,
                "missing_rate": float(out[["open", "high", "low", "close", "volume", "factor"]].isna().mean().mean()),
            }
        )

    instruments = pd.DataFrame(rows).sort_values("symbol") if rows else pd.DataFrame()
    calendar = pd.DataFrame({"date": sorted(all_dates)})
    save_dataframe(instruments, csv_dir.parent / "prepared_instruments.csv")
    save_dataframe(calendar, csv_dir.parent / "prepared_calendar.csv")
    status = {
        "prepared_csv_dir": str(csv_dir),
        "requested_count": len(tickers),
        "exported_count": len(exported),
        "missing_count": len(missing),
        "exported_tickers": exported,
        "missing_tickers": missing,
        "date_start": calendar["date"].min() if not calendar.empty else None,
        "date_end": calendar["date"].max() if not calendar.empty else None,
        "calendar_count": int(len(calendar)),
        "note": "CSV symbol values are uppercase. dump_bin stores instrument names in Qlib's normalized format.",
    }
    save_json(status, csv_dir.parent / "prepared_csv_status.json")
    return status


def run_dump_bin(
    out_dir: Path | str,
    prepared_csv_dir: Path | str,
    qlib_source_dir: Path | str,
    provider_uri: Path | str,
    rebuild: bool = True,
    timeout_sec: int = 900,
) -> dict[str, Any]:
    """Run qlib/scripts/dump_bin.py dump_all for the prepared CSV directory."""
    out_path = ensure_dir(out_dir)
    csv_dir = Path(prepared_csv_dir)
    source = Path(qlib_source_dir)
    provider = Path(provider_uri).expanduser()
    dump_bin = source / "scripts" / "dump_bin.py"
    if not dump_bin.exists():
        raise FileNotFoundError(f"dump_bin.py not found: {dump_bin}")
    if rebuild and provider.exists():
        resolved = provider.resolve()
        allowed_parent = (Path.home() / ".qlib" / "qlib_data").resolve()
        if allowed_parent not in resolved.parents:
            raise ValueError(f"Refusing to delete provider outside ~/.qlib/qlib_data: {resolved}")
        shutil.rmtree(resolved)
    ensure_dir(provider)

    cmd = [
        sys.executable,
        str(dump_bin),
        "dump_all",
        "--data_path",
        str(csv_dir),
        "--qlib_dir",
        str(provider),
        "--include_fields",
        "open,high,low,close,volume,factor",
        "--date_field_name",
        "date",
        "--symbol_field_name",
        "symbol",
        "--file_suffix",
        ".csv",
        "--max_workers",
        "1",
    ]
    save_text(" ".join(cmd), out_path / "build_command.txt")
    status: dict[str, Any] = {"command": cmd, "provider_uri": str(provider), "returncode": None, "stdout_tail": "", "stderr_tail": ""}
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec, check=False)
        status.update(
            {
                "returncode": int(proc.returncode),
                "stdout_tail": proc.stdout[-8000:],
                "stderr_tail": proc.stderr[-8000:],
            }
        )
        save_text(proc.stdout + "\n\nSTDERR:\n" + proc.stderr, out_path / "dump_bin.log")
    except Exception as exc:
        status.update({"returncode": -1, "stderr_tail": str(exc)})
        save_text(str(exc), out_path / "dump_bin.log")
    save_json(status, out_path / "dump_bin_status.json")
    return status


def local_provider_health_check(
    out_dir: Path | str,
    provider_uri: Path | str,
    tickers: list[str] | None = None,
) -> tuple[dict[str, Any], pd.DataFrame]:
    """Validate local provider OHLCV readability and 2022-2026 coverage."""
    out_path = ensure_dir(out_dir)
    provider = Path(provider_uri).expanduser()
    tickers = [t.upper() for t in (tickers or V6_POOL_A)]
    status: dict[str, Any] = {
        "provider_uri": str(provider),
        "provider_exists": provider.exists(),
        "provider_readable": False,
        "calendar_start": None,
        "calendar_end": None,
        "calendar_count": 0,
        "instrument_count": 0,
        "pool_a_available_count": 0,
        "pool_a_missing": [],
        "missing_rate": None,
        "covers_2022_to_2026": False,
        "sample_rows": 0,
        "error": "",
    }
    sample = pd.DataFrame()
    if not provider.exists():
        save_json(status, out_path / "provider_health_check.json")
        save_dataframe(sample, out_path / "qlib_data_sample.csv")
        return status, sample
    try:
        import qlib
        from qlib.config import REG_US
        from qlib.data import D

        qlib.init(provider_uri=str(provider), region=REG_US, expression_cache=None, dataset_cache=None)
        cal = D.calendar(freq="day")
        status["calendar_count"] = int(len(cal))
        status["calendar_start"] = pd.Timestamp(cal[0]).date().isoformat() if len(cal) else None
        status["calendar_end"] = pd.Timestamp(cal[-1]).date().isoformat() if len(cal) else None
        inst_path = provider / "instruments" / "all.txt"
        if inst_path.exists():
            inst = pd.read_csv(inst_path, sep="\t", header=None, names=["symbol", "start", "end"])
            status["instrument_count"] = int(len(inst))
            available = sorted(set(tickers).intersection(set(inst["symbol"].astype(str).str.upper())))
            missing = sorted(set(tickers).difference(set(available)))
            status["pool_a_available_count"] = len(available)
            status["pool_a_missing"] = missing
        else:
            available = tickers
        sample_tickers = available[:12]
        fields = ["$open", "$high", "$low", "$close", "$volume", "$factor"]
        sample = D.features(sample_tickers, fields, start_time="2022-01-01", end_time=status["calendar_end"], freq="day")
        sample = sample.dropna(how="all").tail(1000).reset_index()
        value_cols = [col for col in sample.columns if str(col).startswith("$")]
        status["sample_rows"] = int(len(sample))
        status["missing_rate"] = float(sample[value_cols].isna().mean().mean()) if value_cols else None
        status["provider_readable"] = status["sample_rows"] > 0
        status["covers_2022_to_2026"] = bool(
            status["calendar_start"] is not None
            and status["calendar_end"] is not None
            and pd.Timestamp(status["calendar_start"]) <= pd.Timestamp("2022-01-01")
            and pd.Timestamp(status["calendar_end"]) >= pd.Timestamp("2026-04-01")
        )
    except Exception as exc:
        status["error"] = str(exc)
    save_json(status, out_path / "provider_health_check.json")
    save_dataframe(sample, out_path / "qlib_data_sample.csv")
    return status, sample


def alpha_handler_health_check(out_dir: Path | str, provider_uri: Path | str, provider_health: dict[str, Any]) -> dict[str, Any]:
    """Check Alpha158 and Alpha360 Handler feature/label fetching."""
    out_path = ensure_dir(out_dir)
    checks: dict[str, Any] = {}
    if not provider_health.get("provider_readable"):
        save_json(checks, out_path / "alpha_handler_check.json")
        return checks
    try:
        import qlib
        from qlib.config import REG_US
        from qlib.contrib.data.handler import Alpha158, Alpha360
        from qlib.data.dataset import DatasetH
        from qlib.data.dataset.handler import DataHandlerLP

        qlib.init(provider_uri=str(Path(provider_uri).expanduser()), region=REG_US, expression_cache=None, dataset_cache=None)
        label = (["Ref($close, -6) / Ref($close, -1) - 1"], ["LABEL0"])
        for name, cls in {"Alpha158": Alpha158, "Alpha360": Alpha360}.items():
            row = {"success": False, "rows": 0, "columns": 0, "label_non_na": 0, "error": ""}
            try:
                handler = cls(
                    instruments="all",
                    start_time="2020-01-01",
                    end_time=provider_health.get("calendar_end"),
                    fit_start_time="2020-01-01",
                    fit_end_time="2022-12-31",
                    label=label,
                )
                dataset = DatasetH(handler=handler, segments={"train": ("2020-01-01", "2022-12-31")})
                frame = dataset.prepare("train", col_set=["feature", "label"], data_key=DataHandlerLP.DK_L)
                row.update(
                    {
                        "success": not frame.empty,
                        "rows": int(len(frame)),
                        "columns": int(frame.shape[1]),
                        "label_non_na": int(frame["label"].dropna().shape[0]) if "label" in frame.columns.get_level_values(0) else 0,
                    }
                )
            except Exception as exc:
                row["error"] = str(exc)
            checks[name] = row
    except Exception as exc:
        checks["runtime_error"] = str(exc)
    save_json(checks, out_path / "alpha_handler_check.json")
    return checks


def _find_qlib_source() -> Path | None:
    for path in qlib_source_candidates():
        if (path / "scripts" / "dump_bin.py").exists():
            return path
    return None
