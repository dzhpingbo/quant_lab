"""v9.1 small-growth data onboarding and provider extension.

This module is deliberately scoped to the 29 formal-v9 excluded growth
tickers.  It may use public yfinance OHLCV data when local files are missing,
but it does not touch brokers, credentials, trading APIs, Nasdaq100/S&P500, or
v10 strategy search.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from quant_lab.us_stock_selection.canonical_replay_engine import (
    CanonicalReplayConfig,
    DEFAULT_PROVIDER_URI,
    DEFAULT_V8_1_RUN,
    DEFAULT_V8_2_RUN,
    replay_formal_v82_baseline,
)
from quant_lab.us_stock_selection.data_loader import TickerLoadResult, USDataLoader
from quant_lab.us_stock_selection.local_qlib_provider_builder import local_provider_health_check
from quant_lab.us_stock_selection.utils import PROJECT_ROOT, ensure_dir, load_env_config, save_dataframe, save_json, save_text


OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "us_stock_selection"
FORMAL_V82_BASELINE_RUN = OUTPUT_ROOT / "v82_canonical_rebuild_20260504_090549" / "formal_v82_baseline"
OLD_PROVIDER_URI = DEFAULT_PROVIDER_URI
NEW_PROVIDER_URI = Path(r"C:\Users\Administrator\.qlib\qlib_data\us_data_local_2026_v91_growth")
EVAL_START = pd.Timestamp("2024-01-01")
EVAL_END = pd.Timestamp("2026-04-17")
TRAIN_START = pd.Timestamp("2020-01-02")
MIN_HISTORY_DAYS = 252

V9_1_GROWTH_TICKERS = [
    "ABNB",
    "AFRM",
    "AMAT",
    "APP",
    "ARM",
    "ASML",
    "COIN",
    "DASH",
    "DDOG",
    "FTNT",
    "KLAC",
    "LRCX",
    "MDB",
    "MPWR",
    "MRVL",
    "OKTA",
    "ON",
    "PATH",
    "PINS",
    "RBLX",
    "ROKU",
    "S",
    "SNAP",
    "SPOT",
    "SQ",
    "TEAM",
    "TSM",
    "U",
    "ZS",
]

FIELDS = ["open", "high", "low", "close", "volume", "factor"]


@dataclass(frozen=True)
class ProviderBuildResult:
    provider_uri: Path
    provider_success: bool
    added_tickers: list[str]
    failed_tickers: list[str]
    health: dict[str, Any]
    provider_sample: pd.DataFrame


class _LoggerAdapter:
    def __init__(self, logger: Any | None = None):
        self._logger = logger

    def info(self, message: str) -> None:
        if self._logger is not None:
            self._logger.info(message)

    def warning(self, message: str) -> None:
        if self._logger is not None:
            self._logger.warning(message)


def pool_a_tickers_from_v82(v8_1_run_dir: Path | str = DEFAULT_V8_1_RUN) -> list[str]:
    audit_path = Path(v8_1_run_dir) / "v8_1_model_switch" / "Alpha360_LGBModel" / "score_rank_audit_trail.csv"
    audit = pd.read_csv(audit_path, usecols=["ticker"])
    tickers = sorted({str(t).upper() for t in audit["ticker"].dropna().astype(str)})
    return tickers


def provider_has_ticker(provider_uri: Path | str, ticker: str) -> bool:
    return (Path(provider_uri).expanduser() / "features" / ticker.lower() / "close.day.bin").exists()


def read_provider_calendar(provider_uri: Path | str) -> pd.DatetimeIndex:
    path = Path(provider_uri).expanduser() / "calendars" / "day.txt"
    if not path.exists():
        raise FileNotFoundError(f"Missing provider calendar: {path}")
    return pd.DatetimeIndex(pd.to_datetime(pd.read_csv(path, header=None)[0])).sort_values()


def run_data_inventory(
    out_dir: Path | str,
    tickers: list[str] | None = None,
    old_provider_uri: Path | str = OLD_PROVIDER_URI,
    allow_yfinance_download: bool = True,
    logger: Any | None = None,
) -> tuple[pd.DataFrame, dict[str, TickerLoadResult]]:
    """Audit local/provider coverage and optionally download missing public OHLCV."""
    out = ensure_dir(out_dir)
    log = _LoggerAdapter(logger)
    requested = [t.upper() for t in (tickers or V9_1_GROWTH_TICKERS)]
    config = {
        "study_period": {"start_date": "1980-01-01", "end_date": EVAL_END.date().isoformat()},
        "data": {"allow_download": False, "download_start": "1980-01-01"},
    }
    loader = USDataLoader(config, load_env_config(), log)
    loaded: dict[str, TickerLoadResult] = {}
    rows: list[dict[str, Any]] = []

    for ticker in requested:
        in_provider = provider_has_ticker(old_provider_uri, ticker)
        local_result = loader.load_ticker(ticker, start_date="1980-01-01", end_date=EVAL_END.date().isoformat(), allow_download=False)
        in_local_raw = not local_result.data.empty
        download_needed = not in_local_raw
        download_success = False
        result = local_result
        if download_needed and allow_yfinance_download:
            result = loader.load_ticker(ticker, start_date="1980-01-01", end_date=EVAL_END.date().isoformat(), allow_download=True)
            download_success = bool(result.downloaded and not result.data.empty)
        loaded[ticker] = result
        row = inventory_row(ticker, result, in_provider, in_local_raw, download_needed, download_success)
        rows.append(row)

    inventory = pd.DataFrame(rows)
    save_dataframe(inventory, out / "v9_1_data_inventory.csv")
    save_json(
        {
            "scope": "formal_v9_excluded_29_small_growth_only",
            "requested_tickers": requested,
            "allow_yfinance_download": bool(allow_yfinance_download),
            "old_provider_uri": str(old_provider_uri),
        },
        out / "v9_1_data_inventory_metadata.json",
    )
    return inventory, loaded


def inventory_row(
    ticker: str,
    result: TickerLoadResult,
    in_provider: bool,
    in_local_raw: bool,
    download_needed: bool,
    download_success: bool,
) -> dict[str, Any]:
    data = result.data.copy()
    reasons: list[str] = []
    if data.empty:
        reasons.append("missing_raw_ohlcv")
        return {
            "ticker": ticker,
            "in_local_qlib_provider": bool(in_provider),
            "in_local_raw_ohlcv": bool(in_local_raw),
            "yfinance_download_needed": bool(download_needed),
            "yfinance_download_success": bool(download_success),
            "date_start": "",
            "date_end": "",
            "row_count": 0,
            "missing_rate": 1.0,
            "adj_close_available": False,
            "volume_available": False,
            "data_quality_status": "missing",
            "listed_after_2020_train_start": None,
            "eligibility_status": "no_data",
            "exclusion_reason": ";".join(reasons),
            "source": result.source,
            "path": str(result.path or ""),
        }
    needed = ["open", "high", "low", "close", "volume"]
    missing_rate = float(data[needed].isna().mean().mean())
    adj_close_available = bool("adj_close" in data and data["adj_close"].notna().any())
    volume_available = bool("volume" in data and data["volume"].notna().any())
    positive_price = bool((data[["open", "high", "low", "close"]] > 0).all().all())
    listed_after = bool(data.index.min() > TRAIN_START)
    obs_before_eval = int((data.index < pd.Timestamp("2024-01-31")).sum())
    dynamic_ready = obs_before_eval >= MIN_HISTORY_DAYS
    latest_ok = bool(data.index.max() >= pd.Timestamp("2026-04-02"))
    if missing_rate > 0.05:
        reasons.append("high_missing_rate")
    if not adj_close_available:
        reasons.append("missing_adj_close")
    if not volume_available:
        reasons.append("missing_volume")
    if not positive_price:
        reasons.append("non_positive_ohlc")
    if not latest_ok:
        reasons.append("latest_data_before_2026_04_02")
    status = "ready_for_provider" if not reasons else "raw_quality_issue"
    eligibility_status = "eligible_after_dynamic_history" if dynamic_ready else "observation_until_min_history"
    return {
        "ticker": ticker,
        "in_local_qlib_provider": bool(in_provider),
        "in_local_raw_ohlcv": bool(in_local_raw),
        "yfinance_download_needed": bool(download_needed),
        "yfinance_download_success": bool(download_success),
        "date_start": data.index.min().date().isoformat(),
        "date_end": data.index.max().date().isoformat(),
        "row_count": int(len(data)),
        "missing_rate": missing_rate,
        "adj_close_available": adj_close_available,
        "volume_available": volume_available,
        "data_quality_status": status,
        "listed_after_2020_train_start": listed_after,
        "eligibility_status": eligibility_status,
        "exclusion_reason": "" if not reasons else ";".join(reasons),
        "source": result.source,
        "path": str(result.path or ""),
    }


def build_extended_provider(
    out_dir: Path | str,
    loaded: dict[str, TickerLoadResult],
    inventory: pd.DataFrame,
    pool_tickers: list[str],
    old_provider_uri: Path | str = OLD_PROVIDER_URI,
    new_provider_uri: Path | str = NEW_PROVIDER_URI,
    logger: Any | None = None,
) -> ProviderBuildResult:
    """Copy canonical v8.2 provider and append newly onboarded growth tickers."""
    out = ensure_dir(out_dir)
    prepared_dir = ensure_dir(out / "prepared_csv")
    old_provider = Path(old_provider_uri).expanduser()
    new_provider = Path(new_provider_uri).expanduser()
    log_lines: list[str] = []
    if not old_provider.exists():
        raise FileNotFoundError(f"Old provider not found: {old_provider}")

    _replace_provider_safely(old_provider, new_provider)
    log_lines.append(f"Copied old provider: {old_provider} -> {new_provider}")
    calendar = read_provider_calendar(new_provider)
    added: list[str] = []
    failed: list[str] = []
    ready_tickers = inventory.loc[inventory["data_quality_status"].astype(str).eq("ready_for_provider"), "ticker"].astype(str).str.upper().tolist()
    for ticker in ready_tickers:
        if provider_has_ticker(new_provider, ticker):
            log_lines.append(f"{ticker}: already present in copied provider; skipped append.")
            continue
        result = loaded.get(ticker)
        if result is None or result.data.empty:
            failed.append(ticker)
            log_lines.append(f"{ticker}: no usable data frame.")
            continue
        try:
            prepared = prepare_adjusted_qlib_csv(ticker, result.data, calendar)
            save_dataframe(prepared.reset_index(drop=True), prepared_dir / f"{ticker}.csv")
            write_feature_bins(new_provider, ticker, prepared, calendar)
            added.append(ticker)
            log_lines.append(f"{ticker}: appended {len(prepared)} calendar rows.")
        except Exception as exc:
            failed.append(ticker)
            log_lines.append(f"{ticker}: append failed: {exc}")

    rewrite_instruments(new_provider, calendar)
    all_tickers = sorted(set(pool_tickers) | set(V9_1_GROWTH_TICKERS) | {"SPY", "QQQ", "QLD", "TQQQ", "SHY"})
    health, sample = local_provider_health_check(out, new_provider, tickers=all_tickers)
    save_dataframe(sample, out / "provider_sample_prices.csv")
    instruments = read_instruments(new_provider)
    save_dataframe(instruments, out / "provider_instruments.csv")
    calendar_summary = {
        "provider_uri": str(new_provider),
        "calendar_start": calendar.min().date().isoformat() if len(calendar) else "",
        "calendar_end": calendar.max().date().isoformat() if len(calendar) else "",
        "calendar_count": int(len(calendar)),
        "old_provider_uri": str(old_provider),
        "added_tickers": added,
        "failed_tickers": failed,
    }
    save_json(calendar_summary, out / "provider_calendar_summary.json")
    provider_success = bool(new_provider.exists() and health.get("provider_readable") and len(added) + count_ready_existing(inventory, new_provider) > 0)
    payload = {
        "provider_uri": str(new_provider),
        "provider_success": provider_success,
        "old_provider_uri": str(old_provider),
        "added_tickers": added,
        "failed_tickers": failed,
        "health": health,
    }
    save_json(payload, out / "v9_1_provider_build_status.json")
    save_text("\n".join(log_lines), out / "provider_build_log.txt")
    if logger is not None:
        logger.info(f"v9.1 provider build success={provider_success}; added={len(added)} failed={len(failed)}")
    return ProviderBuildResult(new_provider, provider_success, added, failed, health, sample)


def count_ready_existing(inventory: pd.DataFrame, provider_uri: Path) -> int:
    count = 0
    for ticker in inventory.loc[inventory["data_quality_status"].astype(str).eq("ready_for_provider"), "ticker"].astype(str):
        if provider_has_ticker(provider_uri, ticker):
            count += 1
    return count


def _replace_provider_safely(old_provider: Path, new_provider: Path) -> None:
    old_resolved = old_provider.resolve()
    new_resolved = new_provider.resolve()
    allowed_parent = (Path.home() / ".qlib" / "qlib_data").resolve()
    if allowed_parent not in new_resolved.parents:
        raise ValueError(f"Refusing to rebuild provider outside ~/.qlib/qlib_data: {new_resolved}")
    if old_resolved == new_resolved:
        raise ValueError("New provider path must not equal old provider path.")
    if new_resolved.exists():
        shutil.rmtree(new_resolved)
    shutil.copytree(old_resolved, new_resolved)


def prepare_adjusted_qlib_csv(ticker: str, data: pd.DataFrame, calendar: pd.DatetimeIndex) -> pd.DataFrame:
    frame = data.copy().sort_index()
    frame.index = pd.DatetimeIndex(frame.index).normalize()
    frame = frame.loc[(frame.index >= calendar.min()) & (frame.index <= calendar.max())].copy()
    frame = frame.replace([np.inf, -np.inf], np.nan)
    frame = frame.dropna(subset=["open", "high", "low", "close", "volume"])
    frame = frame.loc[(frame[["open", "high", "low", "close"]] > 0).all(axis=1)]
    if frame.empty:
        raise ValueError("no valid OHLCV rows after clipping to provider calendar")
    raw_close = frame["close"].astype(float)
    adj_close = frame["adj_close"].astype(float) if "adj_close" in frame else raw_close
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
    idx = calendar[(calendar >= adjusted.index.min()) & (calendar <= adjusted.index.max())]
    adjusted = adjusted.reindex(idx)
    adjusted["date"] = adjusted.index.strftime("%Y-%m-%d")
    adjusted["symbol"] = ticker.upper()
    adjusted[["open", "high", "low", "close", "factor"]] = adjusted[["open", "high", "low", "close", "factor"]].ffill()
    adjusted["volume"] = adjusted["volume"].fillna(0.0)
    return adjusted.loc[:, ["symbol", "date", "open", "high", "low", "close", "volume", "factor"]].dropna(subset=["close"])


def write_feature_bins(provider_uri: Path, ticker: str, prepared: pd.DataFrame, calendar: pd.DatetimeIndex) -> None:
    feature_dir = ensure_dir(provider_uri / "features" / ticker.lower())
    dates = pd.to_datetime(prepared["date"])
    if dates.empty:
        raise ValueError("prepared frame has no dates")
    offset = int(calendar.searchsorted(dates.min()))
    for field in FIELDS:
        values = pd.to_numeric(prepared[field], errors="coerce").astype("float32").to_numpy()
        arr = np.concatenate([np.array([offset], dtype="<f4"), values.astype("<f4")])
        arr.tofile(feature_dir / f"{field}.day.bin")


def read_instruments(provider_uri: Path | str) -> pd.DataFrame:
    path = Path(provider_uri).expanduser() / "instruments" / "all.txt"
    if not path.exists():
        return pd.DataFrame(columns=["symbol", "start", "end"])
    return pd.read_csv(path, sep="\t", header=None, names=["symbol", "start", "end"])


def rewrite_instruments(provider_uri: Path, calendar: pd.DatetimeIndex) -> None:
    rows = []
    features_dir = provider_uri / "features"
    for child in sorted(features_dir.iterdir()):
        if not child.is_dir():
            continue
        close_bin = child / "close.day.bin"
        if not close_bin.exists():
            continue
        arr = np.fromfile(close_bin, dtype="<f4")
        if len(arr) < 2:
            continue
        offset = int(arr[0])
        values = arr[1:]
        start_idx = max(0, min(offset, len(calendar) - 1))
        end_idx = max(start_idx, min(offset + len(values) - 1, len(calendar) - 1))
        rows.append(
            {
                "symbol": child.name.upper(),
                "start": calendar[start_idx].date().isoformat(),
                "end": calendar[end_idx].date().isoformat(),
            }
        )
    inst = pd.DataFrame(rows).sort_values("symbol")
    out = provider_uri / "instruments" / "all.txt"
    ensure_dir(out.parent)
    inst.to_csv(out, sep="\t", header=False, index=False)


def run_dynamic_eligibility(
    out_dir: Path | str,
    provider_uri: Path | str,
    tickers: list[str] | None = None,
    min_history_days: int = MIN_HISTORY_DAYS,
) -> pd.DataFrame:
    out = ensure_dir(out_dir)
    provider = Path(provider_uri).expanduser()
    calendar = read_provider_calendar(provider)
    rows: list[dict[str, Any]] = []
    requested = [t.upper() for t in (tickers or V9_1_GROWTH_TICKERS)]
    for ticker in requested:
        close_path = provider / "features" / ticker.lower() / "close.day.bin"
        if not close_path.exists():
            rows.append(
                {
                    "ticker": ticker,
                    "date_start": "",
                    "date_end": "",
                    "available_for_training": False,
                    "available_for_prediction": False,
                    "min_history_days": min_history_days,
                    "train_window_coverage": 0,
                    "prediction_window_coverage": 0,
                    "eligible_for_formal_v9": False,
                    "first_eligible_rebalance_date": "",
                    "eligible_month_count": 0,
                    "eligibility_failure_reason": "missing_provider_bin",
                }
            )
            continue
        arr = np.fromfile(close_path, dtype="<f4")
        offset = int(arr[0])
        values = arr[1:]
        idx = calendar[offset : offset + len(values)]
        close = pd.Series(values, index=idx).replace([np.inf, -np.inf], np.nan).dropna()
        if close.empty:
            rows.append(
                {
                    "ticker": ticker,
                    "date_start": "",
                    "date_end": "",
                    "available_for_training": False,
                    "available_for_prediction": False,
                    "min_history_days": min_history_days,
                    "train_window_coverage": 0,
                    "prediction_window_coverage": 0,
                    "eligible_for_formal_v9": False,
                    "first_eligible_rebalance_date": "",
                    "eligible_month_count": 0,
                    "eligibility_failure_reason": "empty_close_bin",
                }
            )
            continue
        eval_dates = month_end_dates(calendar, EVAL_START, EVAL_END)
        eligible_dates = [d for d in eval_dates if int((close.index < d).sum()) >= min_history_days and close.index.min() <= d <= close.index.max()]
        train_cov = int((close.index < EVAL_START).sum())
        pred_cov = int(((close.index >= EVAL_START) & (close.index <= EVAL_END)).sum())
        eligible = len(eligible_dates) > 0
        reasons = []
        if train_cov < min_history_days:
            reasons.append("insufficient_pre_eval_history")
        if pred_cov <= 0:
            reasons.append("no_prediction_window_data")
        rows.append(
            {
                "ticker": ticker,
                "date_start": close.index.min().date().isoformat(),
                "date_end": close.index.max().date().isoformat(),
                "available_for_training": bool(train_cov >= min_history_days),
                "available_for_prediction": bool(pred_cov > 0),
                "min_history_days": min_history_days,
                "train_window_coverage": train_cov,
                "prediction_window_coverage": pred_cov,
                "eligible_for_formal_v9": eligible,
                "first_eligible_rebalance_date": eligible_dates[0].date().isoformat() if eligible_dates else "",
                "eligible_month_count": int(len(eligible_dates)),
                "eligibility_failure_reason": "" if eligible else ";".join(reasons or ["dynamic_rule_not_satisfied"]),
            }
        )
    result = pd.DataFrame(rows)
    save_dataframe(result, out / "v9_1_eligibility_result.csv")
    return result


def month_end_dates(index: pd.DatetimeIndex, start: pd.Timestamp, end: pd.Timestamp) -> list[pd.Timestamp]:
    idx = pd.DatetimeIndex(index).sort_values()
    idx = idx[(idx >= start) & (idx <= end)]
    if idx.empty:
        return []
    positions = pd.Series(index=idx, data=np.arange(len(idx)))
    return [pd.Timestamp(idx[int(pos)]) for pos in positions.groupby(idx.to_period("M")).last().dropna().values]


def run_pool_a_reproduction_preflight(
    out_dir: Path | str,
    provider_uri: Path | str,
    v8_1_run_dir: Path | str = DEFAULT_V8_1_RUN,
    v8_2_run_dir: Path | str = DEFAULT_V8_2_RUN,
) -> tuple[pd.DataFrame, bool]:
    out = ensure_dir(out_dir)
    cfg = CanonicalReplayConfig(provider_uri=Path(provider_uri), v8_1_run_dir=Path(v8_1_run_dir), v8_2_run_dir=Path(v8_2_run_dir))
    replay = replay_formal_v82_baseline(out / "_pool_a_reproduction_internal", config=cfg)
    baseline_path = FORMAL_V82_BASELINE_RUN / "formal_v82_metrics.csv"
    baseline = pd.read_csv(baseline_path) if baseline_path.exists() else pd.DataFrame()
    reproduced = replay["metrics"]
    rows = []
    thresholds = {"cagr": 0.005, "max_drawdown": 0.005, "calmar": 0.03, "single_year_share": 0.02, "top_ticker_share": 0.02}
    if baseline.empty or reproduced.empty:
        rows.append({"metric": "missing_baseline_or_reproduction", "formal_v82_baseline": np.nan, "v91_provider_reproduction": np.nan, "diff": np.nan, "tolerance": np.nan, "pass_check": False})
    else:
        base = baseline.iloc[0].to_dict()
        rep = reproduced.iloc[0].to_dict()
        for metric, tolerance in thresholds.items():
            b = float(base.get(metric, np.nan))
            r = float(rep.get(metric, np.nan))
            rows.append({"metric": metric, "formal_v82_baseline": b, "v91_provider_reproduction": r, "diff": r - b, "tolerance": tolerance, "pass_check": abs(r - b) <= tolerance})
    check = pd.DataFrame(rows)
    save_dataframe(check, out / "preflight_pool_a_reproduction_check.csv")
    return check, bool(not check.empty and check["pass_check"].astype(bool).all())


def json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)
