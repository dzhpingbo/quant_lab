"""Safely refresh the v8.2 frozen Qlib provider for the daily automation.

This script is scoped to the current approved frozen mainline only:
top5_ytdcap80p_derisk100p. It refreshes only the v8.2 required ticker set,
builds a temporary provider first, validates it, and only then syncs the
approved provider path when replacement is enabled.

It does not train models, recompute scores, search strategies, expand pools,
enter v10/MVE, connect brokers, trade, commit, or push.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.automation.daily_v82_provider_check import (  # noqa: E402
    DEFAULT_PROVIDER_DIR,
    PRIMARY_STRATEGY_ID,
    build_markdown as build_provider_check_markdown,
    load_required_tickers,
    run_check,
)


FIELDS = ["open", "high", "low", "close", "volume", "factor"]
DEFAULT_STAGING_ROOT = PROJECT_ROOT / "outputs" / "daily_quant_lab_runs" / "provider_refresh_staging"
DEFAULT_BACKUP_ROOT = PROJECT_ROOT / "outputs" / "daily_quant_lab_runs" / "provider_refresh_backups"
STRATEGY_COMMAND = "python scripts/us_stock_selection/51_run_v82_frozen_formal_audit.py --skip-bridge"


@dataclass(frozen=True)
class DownloadResult:
    ticker: str
    data: pd.DataFrame
    source: str
    error: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Safely refresh the v8.2 frozen provider required ticker data.")
    parser.add_argument("--provider-dir", default=str(DEFAULT_PROVIDER_DIR), help="Current v8.2 frozen Qlib provider.")
    parser.add_argument("--tickers-file", default="", help="Optional ticker file. Must be a subset of the default v8.2 required universe.")
    parser.add_argument("--start-date", default="", help="Optional download start date. Defaults to current provider calendar start.")
    parser.add_argument("--end-date", default=date.today().isoformat(), help="Download end date, inclusive where available. Defaults to today.")
    parser.add_argument("--source", default="yfinance", choices=["yfinance"], help="Data source. Only existing project yfinance logic is supported.")
    parser.add_argument("--temp-dir", default="", help="Temporary staging directory. Must not already contain files.")
    parser.add_argument("--backup-dir", default=str(DEFAULT_BACKUP_ROOT), help="Backup root for the current provider before sync.")
    parser.add_argument("--dry-run", action="store_true", help="Plan only; no download, no temp provider build, no replacement.")
    parser.add_argument("--no-replace", action="store_true", help="Build and validate temp provider but do not sync to provider-dir.")
    parser.add_argument("--json-out", default="", help="Optional JSON report path.")
    parser.add_argument("--md-out", default="", help="Optional Markdown report path.")
    parser.add_argument("--max-stale-days", type=int, default=7, help="Maximum allowed age for refreshed provider latest data date.")
    return parser.parse_args()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except Exception:
        return str(path)


def ensure_empty_dir(path: Path) -> None:
    if path.exists() and any(path.iterdir()):
        raise FileExistsError(f"Refusing to reuse non-empty staging directory: {path}")
    path.mkdir(parents=True, exist_ok=True)


def read_provider_calendar(provider: Path) -> pd.DatetimeIndex:
    path = provider / "calendars" / "day.txt"
    if not path.exists():
        raise FileNotFoundError(f"Provider calendar not found: {path}")
    values = pd.read_csv(path, header=None)[0]
    calendar = pd.DatetimeIndex(pd.to_datetime(values, errors="coerce").dropna()).normalize().sort_values()
    if calendar.empty:
        raise ValueError(f"Provider calendar is empty or unparsable: {path}")
    return calendar


def read_bin_end_date(provider: Path, ticker: str, field: str, calendar: pd.DatetimeIndex) -> str:
    path = provider / "features" / ticker.lower() / f"{field}.day.bin"
    if not path.exists():
        return ""
    arr = np.fromfile(path, dtype="<f4")
    if len(arr) < 2:
        return ""
    offset = int(arr[0])
    end_index = min(max(offset + len(arr) - 2, 0), len(calendar) - 1)
    return calendar[end_index].date().isoformat()


def load_default_tickers() -> list[str]:
    required = load_required_tickers(STRATEGY_COMMAND, "")
    tickers = [str(item).upper() for item in required.get("tickers", [])]
    if len(tickers) != 36:
        raise RuntimeError(f"Expected 36 v8.2 required tickers, got {len(tickers)} from {required.get('source')}")
    return sorted(tickers)


def load_tickers_file(path: Path, default_tickers: list[str]) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"tickers-file not found: {path}")
    values: list[str] = []
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload = payload.get("tickers") or payload.get("required_tickers") or []
        values = [str(item).strip().upper() for item in payload if str(item).strip()]
    else:
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            sample = fh.read(2048)
            fh.seek(0)
            if "," in sample:
                reader = csv.DictReader(fh)
                if reader.fieldnames:
                    field_map = {name.lower(): name for name in reader.fieldnames}
                    col = field_map.get("ticker") or field_map.get("symbol") or reader.fieldnames[0]
                    values = [str(row.get(col, "")).strip().upper() for row in reader if str(row.get(col, "")).strip()]
            else:
                values = [line.strip().upper() for line in fh if line.strip() and not line.lstrip().startswith("#")]
    tickers = sorted(set(values))
    default_set = set(default_tickers)
    extra = sorted(set(tickers) - default_set)
    if extra:
        raise ValueError(f"tickers-file would expand beyond v8.2 required universe: {', '.join(extra)}")
    if not tickers:
        raise ValueError(f"tickers-file did not contain usable tickers: {path}")
    return tickers


def flatten_yfinance_columns(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    out = df.copy()
    if isinstance(out.columns, pd.MultiIndex):
        levels0 = [str(x) for x in out.columns.get_level_values(0)]
        levels1 = [str(x) for x in out.columns.get_level_values(1)]
        upper = ticker.upper()
        if upper in {x.upper() for x in levels1}:
            out.columns = out.columns.get_level_values(0)
        elif upper in {x.upper() for x in levels0}:
            out.columns = out.columns.get_level_values(1)
        else:
            out.columns = ["_".join(str(v) for v in tup if str(v)) for tup in out.columns.to_flat_index()]
    return out


def normalize_yfinance_download(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = flatten_yfinance_columns(df, ticker).reset_index()
    rename: dict[Any, str] = {}
    for col in out.columns:
        key = str(col).strip().lower().replace(" ", "_")
        if key in {"date", "datetime"}:
            rename[col] = "date"
        elif key in {"open", "high", "low", "close", "volume", "dividends"}:
            rename[col] = key
        elif key in {"adj_close", "adjclose", "adjusted_close"}:
            rename[col] = "adj_close"
        elif key in {"stock_splits", "stock_splits_", "splits"}:
            rename[col] = "splits"
    out = out.rename(columns=rename)
    if "date" not in out.columns:
        return pd.DataFrame()
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.tz_localize(None).dt.normalize()
    out = out.dropna(subset=["date"]).sort_values("date").drop_duplicates("date", keep="last")
    for col in ["open", "high", "low", "close", "adj_close", "volume", "dividends", "splits"]:
        if col not in out.columns:
            out[col] = 0.0 if col in {"dividends", "splits"} else np.nan
        out[col] = pd.to_numeric(out[col], errors="coerce")
    if out["adj_close"].isna().all() and not out["close"].isna().all():
        out["adj_close"] = out["close"]
    out["ticker"] = ticker.upper()
    return out[["date", "ticker", "open", "high", "low", "close", "adj_close", "volume", "dividends", "splits"]].copy()


def download_yfinance(ticker: str, start_date: str, end_date: str, retries: int = 2) -> DownloadResult:
    try:
        import yfinance as yf
    except Exception as exc:
        return DownloadResult(ticker=ticker, data=pd.DataFrame(), source="yfinance", error=f"yfinance import failed: {exc}")

    start = pd.Timestamp(start_date).date().isoformat()
    end_exclusive = (pd.Timestamp(end_date).date() + timedelta(days=1)).isoformat()
    last_error = ""
    for attempt in range(retries + 1):
        try:
            raw = yf.download(
                ticker,
                start=start,
                end=end_exclusive,
                auto_adjust=False,
                actions=True,
                progress=False,
                threads=False,
            )
            frame = normalize_yfinance_download(raw, ticker)
            if frame.empty:
                raise ValueError("yfinance returned no usable rows")
            required = ["open", "high", "low", "close", "adj_close", "volume"]
            missing_required = [col for col in required if col not in frame or frame[col].isna().all()]
            if missing_required:
                raise ValueError(f"missing required columns: {', '.join(missing_required)}")
            return DownloadResult(ticker=ticker, data=frame, source="yfinance(auto_adjust=False,actions=True)")
        except Exception as exc:
            last_error = str(exc)
            time.sleep(1.0 + attempt)
    return DownloadResult(ticker=ticker, data=pd.DataFrame(), source="yfinance(auto_adjust=False,actions=True)", error=last_error)


def prepare_adjusted_qlib_csv(ticker: str, data: pd.DataFrame, calendar: pd.DatetimeIndex) -> pd.DataFrame:
    frame = data.copy().sort_values("date")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.tz_localize(None).dt.normalize()
    frame = frame.dropna(subset=["date"]).drop_duplicates("date", keep="last").set_index("date").sort_index()
    frame = frame.loc[(frame.index >= calendar.min()) & (frame.index <= calendar.max())].copy()
    frame = frame.replace([np.inf, -np.inf], np.nan)
    frame = frame.dropna(subset=["open", "high", "low", "close", "adj_close", "volume"])
    frame = frame.loc[(frame[["open", "high", "low", "close"]] > 0).all(axis=1)]
    if frame.empty:
        raise ValueError(f"{ticker}: no valid OHLCV rows after clipping to provider calendar")
    raw_close = frame["close"].astype(float)
    adj_close = frame["adj_close"].astype(float)
    factor = (adj_close / raw_close.replace(0.0, np.nan)).replace([np.inf, -np.inf], np.nan).fillna(1.0)
    if factor.sub(1.0).abs().median() < 1e-8:
        factor = pd.Series(1.0, index=frame.index)
    adjusted = pd.DataFrame(index=frame.index)
    adjusted["date"] = adjusted.index.normalize()
    adjusted["symbol"] = ticker.upper()
    for col in ["open", "high", "low", "close"]:
        adjusted[col] = frame[col].astype(float) * factor
    adjusted["volume"] = frame["volume"].astype(float).clip(lower=0.0)
    adjusted["factor"] = factor.astype(float)
    idx = calendar[(calendar >= adjusted.index.min()) & (calendar <= calendar.max())]
    adjusted = adjusted.reindex(idx)
    adjusted["date"] = adjusted.index.strftime("%Y-%m-%d")
    adjusted["symbol"] = ticker.upper()
    adjusted[["open", "high", "low", "close", "factor"]] = adjusted[["open", "high", "low", "close", "factor"]].ffill()
    adjusted["volume"] = adjusted["volume"].fillna(0.0)
    return adjusted.loc[:, ["symbol", "date", "open", "high", "low", "close", "volume", "factor"]].dropna(subset=["close"])


def write_feature_bins(provider: Path, ticker: str, prepared: pd.DataFrame, calendar: pd.DatetimeIndex) -> None:
    feature_dir = provider / "features" / ticker.lower()
    feature_dir.mkdir(parents=True, exist_ok=True)
    dates = pd.to_datetime(prepared["date"], errors="coerce").dropna()
    if dates.empty:
        raise ValueError(f"{ticker}: prepared frame has no dates")
    offset = int(calendar.searchsorted(dates.min()))
    for field in FIELDS:
        values = pd.to_numeric(prepared[field], errors="coerce").astype("float32").to_numpy()
        arr = np.concatenate([np.array([offset], dtype="<f4"), values.astype("<f4")])
        arr.tofile(feature_dir / f"{field}.day.bin")


def rewrite_calendar(provider: Path, calendar: pd.DatetimeIndex) -> None:
    out = provider / "calendars" / "day.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(pd.DatetimeIndex(calendar).strftime("%Y-%m-%d")) + "\n", encoding="utf-8")


def rewrite_instruments(provider: Path, calendar: pd.DatetimeIndex) -> None:
    rows: list[dict[str, str]] = []
    features = provider / "features"
    for child in sorted(features.iterdir() if features.exists() else []):
        if not child.is_dir():
            continue
        arr_path = child / "close.day.bin"
        if not arr_path.exists():
            continue
        arr = np.fromfile(arr_path, dtype="<f4")
        if len(arr) < 2:
            continue
        offset = int(arr[0])
        start_index = max(0, min(offset, len(calendar) - 1))
        end_index = max(start_index, min(offset + len(arr) - 2, len(calendar) - 1))
        rows.append(
            {
                "symbol": child.name.upper(),
                "start": calendar[start_index].date().isoformat(),
                "end": calendar[end_index].date().isoformat(),
            }
        )
    out = provider / "instruments" / "all.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).sort_values("symbol").to_csv(out, sep="\t", header=False, index=False)


def copy_required_feature_bins(temp_provider: Path, provider: Path, tickers: list[str]) -> None:
    for ticker in tickers:
        source_dir = temp_provider / "features" / ticker.lower()
        target_dir = provider / "features" / ticker.lower()
        target_dir.mkdir(parents=True, exist_ok=True)
        for field in FIELDS:
            src = source_dir / f"{field}.day.bin"
            if not src.exists():
                raise FileNotFoundError(f"Missing temp feature file: {src}")
            shutil.copy2(src, target_dir / src.name)


def provider_check(provider: Path, max_stale_days: int, json_path: Path | None = None, md_path: Path | None = None) -> dict[str, Any]:
    args = argparse.Namespace(
        provider_dir=str(provider),
        strategy_command=STRATEGY_COMMAND,
        strategy_config="",
        max_stale_days=max_stale_days,
        dry_run=False,
        json_out="",
        md_out="",
    )
    payload = run_check(args)
    if json_path is not None:
        write_json(json_path, payload)
    if md_path is not None:
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(build_provider_check_markdown(payload), encoding="utf-8")
    return payload


def required_bin_end_dates(provider: Path, tickers: list[str], calendar: pd.DatetimeIndex) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    for ticker in tickers:
        rows[ticker] = {
            "close": read_bin_end_date(provider, ticker, "close", calendar),
            "volume": read_bin_end_date(provider, ticker, "volume", calendar),
        }
    return rows


def validate_temp_provider(temp_provider: Path, tickers: list[str], max_stale_days: int, out_dir: Path) -> tuple[bool, dict[str, Any], list[str]]:
    errors: list[str] = []
    check = provider_check(
        temp_provider,
        max_stale_days=max_stale_days,
        json_path=out_dir / "temp_provider_check.json",
        md_path=out_dir / "temp_provider_check.md",
    )
    if check.get("final_status") != "PASS":
        errors.append(f"Temp provider check final_status is {check.get('final_status')}.")
    if int(check.get("file_count") or 0) <= 0:
        errors.append("Temp provider has no files.")
    if float(check.get("total_size_mb") or 0.0) <= 0.0:
        errors.append("Temp provider total_size_mb is zero.")
    coverage = check.get("required_ticker_coverage", {})
    if coverage.get("status") != "PASS":
        errors.append(f"Temp provider required ticker coverage is {coverage.get('status')}.")
    calendar = read_provider_calendar(temp_provider)
    latest = calendar[-1].date().isoformat()
    end_dates = required_bin_end_dates(temp_provider, tickers, calendar)
    stale_required = [
        ticker
        for ticker, fields in end_dates.items()
        if fields.get("close") != latest or fields.get("volume") != latest
    ]
    if stale_required:
        errors.append(f"Required ticker bins do not extend to temp calendar latest date {latest}: {', '.join(stale_required)}")
    check["required_bin_end_dates"] = end_dates
    return not errors, check, errors


def allowed_provider_path(provider: Path) -> bool:
    try:
        resolved = provider.resolve()
        allowed_parent = (Path.home() / ".qlib" / "qlib_data").resolve()
        return allowed_parent in resolved.parents
    except Exception:
        return False


def build_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# refresh_v82_provider_safe - {payload.get('final_status')}",
        "",
        f"- Generated at: `{payload.get('generated_at')}`",
        f"- Provider: `{payload.get('provider_dir')}`",
        f"- Source: `{payload.get('source')}`",
        f"- Strategy id: `{payload.get('strategy_id')}`",
        f"- Ticker count: `{payload.get('refreshed_ticker_count')}`",
        f"- Dry run: `{payload.get('dry_run')}`",
        f"- No replace: `{payload.get('no_replace')}`",
        f"- Data download performed: `{payload.get('data_download_performed')}`",
        f"- Replacement performed: `{payload.get('replacement_performed')}`",
        f"- Backup dir: `{payload.get('backup_dir')}`",
        f"- Old latest data date: `{payload.get('old_latest_data_date')}`",
        f"- New latest data date: `{payload.get('new_latest_data_date')}`",
        f"- Provider check final_status: `{payload.get('provider_check_final_status')}`",
        "",
        "## Tickers",
        "",
        "`" + ", ".join(payload.get("tickers", [])) + "`",
        "",
        "## Warnings",
        "",
    ]
    lines.extend([f"- {item}" for item in payload.get("warnings", [])] or ["- none"])
    lines.extend(["", "## Errors", ""])
    lines.extend([f"- {item}" for item in payload.get("errors", [])] or ["- none"])
    return "\n".join(lines) + "\n"


def run_refresh(args: argparse.Namespace) -> dict[str, Any]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    provider = Path(args.provider_dir).expanduser()
    backup_root = Path(args.backup_dir).expanduser()
    temp_root = Path(args.temp_dir).expanduser() if args.temp_dir else DEFAULT_STAGING_ROOT / f"refresh_{timestamp}"
    temp_provider = temp_root / provider.name
    warnings: list[str] = []
    errors: list[str] = []

    default_tickers = load_default_tickers()
    tickers = load_tickers_file(Path(args.tickers_file), default_tickers) if args.tickers_file else default_tickers
    old_check = provider_check(provider, max_stale_days=args.max_stale_days)
    old_latest = str(old_check.get("latest_data_date") or "")
    old_calendar = read_provider_calendar(provider) if provider.exists() else pd.DatetimeIndex([])
    if old_calendar.empty:
        errors.append("Current provider calendar is empty.")
    if not allowed_provider_path(provider):
        errors.append(f"Provider path is outside the allowed ~/.qlib/qlib_data tree: {provider}")

    start_date = args.start_date or (old_calendar.min().date().isoformat() if not old_calendar.empty else "")
    end_date = args.end_date or date.today().isoformat()
    refresh_needed = bool(old_check.get("final_status") != "PASS")

    payload: dict[str, Any] = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "script": rel(Path(__file__)),
        "provider_dir": str(provider),
        "strategy_id": PRIMARY_STRATEGY_ID,
        "source": args.source,
        "source_policy": "existing project yfinance logic with auto_adjust=False and adjusted OHLC via Adj Close / Close factor; raw volume preserved",
        "tickers": tickers,
        "refreshed_ticker_count": len(tickers),
        "old_latest_data_date": old_latest,
        "new_latest_data_date": "",
        "start_date": start_date,
        "end_date": end_date,
        "dry_run": bool(args.dry_run),
        "no_replace": bool(args.no_replace),
        "temp_dir": str(temp_root),
        "temp_provider_dir": str(temp_provider),
        "backup_dir": "",
        "data_download_performed": False,
        "replacement_performed": False,
        "provider_check_final_status": old_check.get("final_status"),
        "old_provider_check": old_check,
        "refresh_needed": refresh_needed,
        "download_summary": [],
        "warnings": warnings,
        "errors": errors,
        "final_status": "FAIL",
    }

    if errors:
        payload["final_status"] = "FAIL"
        return payload

    if args.dry_run:
        payload["final_status"] = "PASS"
        payload["warnings"].append("Dry run only: no download, no temp provider build, no replacement.")
        return payload

    ensure_empty_dir(temp_root)
    if temp_provider.exists():
        raise FileExistsError(f"Temp provider already exists: {temp_provider}")
    shutil.copytree(provider, temp_provider)

    downloads_dir = temp_root / "downloaded_ohlcv"
    downloads_dir.mkdir(parents=True, exist_ok=True)
    download_results: dict[str, DownloadResult] = {}
    all_dates = list(old_calendar)
    for ticker in tickers:
        result = download_yfinance(ticker, start_date=start_date, end_date=end_date)
        download_results[ticker] = result
        if result.error:
            errors.append(f"{ticker}: {result.error}")
        if not result.data.empty:
            result.data.to_csv(downloads_dir / f"{ticker}.csv", index=False, encoding="utf-8")
            dates = pd.DatetimeIndex(pd.to_datetime(result.data["date"], errors="coerce").dropna()).normalize()
            all_dates.extend(list(dates))
        payload["download_summary"].append(
            {
                "ticker": ticker,
                "source": result.source,
                "rows": int(len(result.data)),
                "first_date": result.data["date"].min().date().isoformat() if not result.data.empty else "",
                "last_date": result.data["date"].max().date().isoformat() if not result.data.empty else "",
                "error": result.error,
            }
        )

    payload["data_download_performed"] = any(not result.data.empty for result in download_results.values())
    if errors:
        payload["errors"] = errors
        payload["final_status"] = "FAIL"
        return payload

    new_calendar = pd.DatetimeIndex(pd.to_datetime(pd.Series(all_dates), errors="coerce").dropna()).normalize().unique().sort_values()
    if new_calendar.empty:
        errors.append("New calendar would be empty.")
    else:
        rewrite_calendar(temp_provider, new_calendar)
        prepared_dir = temp_root / "prepared_qlib_csv"
        prepared_dir.mkdir(parents=True, exist_ok=True)
        for ticker in tickers:
            result = download_results[ticker]
            try:
                prepared = prepare_adjusted_qlib_csv(ticker, result.data, new_calendar)
                prepared.to_csv(prepared_dir / f"{ticker}.csv", index=False, encoding="utf-8")
                write_feature_bins(temp_provider, ticker, prepared, new_calendar)
            except Exception as exc:
                errors.append(f"{ticker}: provider bin write failed: {exc}")
        rewrite_instruments(temp_provider, new_calendar)

    if errors:
        payload["errors"] = errors
        payload["final_status"] = "FAIL"
        return payload

    temp_ok, temp_check, temp_errors = validate_temp_provider(temp_provider, tickers, args.max_stale_days, temp_root)
    payload["temp_provider_check"] = temp_check
    payload["provider_check_final_status"] = temp_check.get("final_status")
    payload["new_latest_data_date"] = str(temp_check.get("latest_data_date") or "")
    if not temp_ok:
        errors.extend(temp_errors)
        payload["errors"] = errors
        payload["final_status"] = "FAIL"
        return payload

    if args.no_replace:
        payload["final_status"] = "PASS"
        payload["warnings"].append("No-replace mode: temp provider validated, current provider was not modified.")
        return payload

    backup_path = backup_root / f"{provider.name}_{timestamp}"
    if backup_path.exists():
        raise FileExistsError(f"Backup path already exists: {backup_path}")
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(provider, backup_path)
    payload["backup_dir"] = str(backup_path)

    shutil.copy2(temp_provider / "calendars" / "day.txt", provider / "calendars" / "day.txt")
    copy_required_feature_bins(temp_provider, provider, tickers)
    rewrite_instruments(provider, read_provider_calendar(provider))
    payload["replacement_performed"] = True

    final_check = provider_check(
        provider,
        max_stale_days=args.max_stale_days,
        json_path=Path(args.json_out).with_name("v82_provider_check_after_refresh.json") if args.json_out else None,
        md_path=Path(args.md_out).with_name("v82_provider_check_after_refresh.md") if args.md_out else None,
    )
    payload["provider_check_after_refresh"] = final_check
    payload["provider_check_final_status"] = final_check.get("final_status")
    payload["new_latest_data_date"] = str(final_check.get("latest_data_date") or payload["new_latest_data_date"])
    if final_check.get("final_status") != "PASS":
        errors.append(f"Provider check after sync is {final_check.get('final_status')}; backup retained at {backup_path}.")
        payload["errors"] = errors
        payload["final_status"] = "FAIL"
        return payload

    payload["final_status"] = "PASS"
    return payload


def main() -> int:
    args = parse_args()
    try:
        payload = run_refresh(args)
    except Exception as exc:
        payload = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "script": rel(Path(__file__)),
            "provider_dir": str(Path(args.provider_dir).expanduser()),
            "strategy_id": PRIMARY_STRATEGY_ID,
            "source": args.source,
            "dry_run": bool(args.dry_run),
            "no_replace": bool(args.no_replace),
            "data_download_performed": False,
            "replacement_performed": False,
            "backup_dir": "",
            "old_latest_data_date": "",
            "new_latest_data_date": "",
            "refreshed_ticker_count": 0,
            "provider_check_final_status": "",
            "warnings": [],
            "errors": [str(exc)],
            "final_status": "FAIL",
        }
    default_report_dir = Path(str(payload.get("temp_dir") or DEFAULT_STAGING_ROOT / "latest_report")).expanduser()
    json_out = Path(args.json_out) if args.json_out else default_report_dir / "refresh_v82_provider_safe.json"
    md_out = Path(args.md_out) if args.md_out else default_report_dir / "refresh_v82_provider_safe.md"
    write_json(json_out, payload)
    md_out.parent.mkdir(parents=True, exist_ok=True)
    md_out.write_text(build_markdown(payload), encoding="utf-8")
    payload["json_out"] = str(json_out)
    payload["md_out"] = str(md_out)
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    return 0 if payload.get("final_status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
