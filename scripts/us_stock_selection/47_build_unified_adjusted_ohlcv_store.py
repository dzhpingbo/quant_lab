"""Build a unified adjusted OHLCV store for MVE1 readiness rerun.

This is not formal v9. It does not expand the formal universe, train models,
run backtests, optimize strategies, run 31b, or start MVE2. It reads the
previous MVE1 ticker universe and downloads per-ticker yfinance history with
auto_adjust=False so raw OHLCV, Adj Close, dividends, and splits remain auditable.
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "us_stock_selection"
DEFAULT_PREVIOUS_MVE1_DIR = OUTPUT_ROOT / "mve1_longer_history_data_audit_20260501_225200"
DEFAULT_STORE_DIR = PROJECT_ROOT / "data" / "unified_ohlcv" / "us_stock_selection"

PRICE_COLUMNS = [
    "date",
    "open",
    "high",
    "low",
    "close",
    "adj_close",
    "volume",
    "dividends",
    "stock_splits",
    "ticker",
    "source",
    "download_timestamp",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build unified adjusted OHLCV store from yfinance.")
    parser.add_argument("--ticker-universe", type=Path, default=None)
    parser.add_argument("--previous-mve1-dir", type=Path, default=DEFAULT_PREVIOUS_MVE1_DIR)
    parser.add_argument("--store-dir", type=Path, default=DEFAULT_STORE_DIR)
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--timestamp", default=None)
    parser.add_argument("--sleep-sec", type=float, default=0.2)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def setup_logger(out_dir: Path) -> logging.Logger:
    out_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("build_unified_adjusted_ohlcv_store")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    fh = logging.FileHandler(out_dir / "unified_store_build_log.txt", encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


def write_json(payload: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def normalize_ticker(ticker: Any) -> str:
    return str(ticker).strip().upper()


def locate_ticker_universe(explicit: Path | None, previous_dir: Path) -> Path:
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit)
    candidates.append(previous_dir / "mve1_audit_ticker_universe.csv")
    candidates.extend(
        sorted(
            OUTPUT_ROOT.glob("mve1_longer_history_data_audit_*/mve1_audit_ticker_universe.csv"),
            key=lambda p: p.stat().st_mtime if p.exists() else 0,
            reverse=True,
        )
    )
    candidates.extend(
        sorted(
            OUTPUT_ROOT.glob("**/mve1_audit_ticker_universe.csv"),
            key=lambda p: p.stat().st_mtime if p.exists() else 0,
            reverse=True,
        )
    )
    for path in candidates:
        if not path.exists():
            continue
        try:
            df = pd.read_csv(path)
        except Exception:
            continue
        required = {"ticker", "layer", "source"}
        if required.issubset(set(df.columns)):
            return path
    raise FileNotFoundError(
        "Cannot locate a valid ticker universe with columns ticker/layer/source. "
        "Provide --ticker-universe or rerun MVE1 audit first."
    )


def load_ticker_universe(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = {"ticker", "layer", "source"} - set(df.columns)
    if missing:
        raise ValueError(f"Ticker universe is missing required columns: {sorted(missing)}")
    out = df.copy()
    out["ticker"] = out["ticker"].map(normalize_ticker)
    out["layer"] = out["layer"].astype(str)
    out["source"] = out["source"].astype(str)
    out = out.drop_duplicates("ticker").sort_values(["layer", "ticker"]).reset_index(drop=True)
    if out.empty:
        raise ValueError("Ticker universe is empty.")
    return out


def flatten_yfinance_columns(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    out = df.copy()
    if isinstance(out.columns, pd.MultiIndex):
        levels0 = [str(x) for x in out.columns.get_level_values(0)]
        levels1 = [str(x) for x in out.columns.get_level_values(1)]
        if ticker in {x.upper() for x in levels1}:
            out.columns = out.columns.get_level_values(0)
        elif ticker in {x.upper() for x in levels0}:
            out.columns = out.columns.get_level_values(1)
        else:
            out.columns = ["_".join(str(v) for v in tup if str(v) != "") for tup in out.columns.to_flat_index()]
    return out


def normalize_price_download(df: pd.DataFrame, ticker: str, timestamp: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=PRICE_COLUMNS)
    out = flatten_yfinance_columns(df, ticker).reset_index()
    rename = {}
    for col in out.columns:
        key = str(col).strip().lower().replace(" ", "_")
        if key in {"date", "datetime"}:
            rename[col] = "date"
        elif key == "open":
            rename[col] = "open"
        elif key == "high":
            rename[col] = "high"
        elif key == "low":
            rename[col] = "low"
        elif key == "close":
            rename[col] = "close"
        elif key in {"adj_close", "adjclose", "adjusted_close"}:
            rename[col] = "adj_close"
        elif key == "volume":
            rename[col] = "volume"
        elif key == "dividends":
            rename[col] = "dividends"
        elif key in {"stock_splits", "stock_splits_", "splits"}:
            rename[col] = "stock_splits"
    out = out.rename(columns=rename)
    if "date" not in out.columns:
        return pd.DataFrame(columns=PRICE_COLUMNS)
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.tz_localize(None)
    out = out.dropna(subset=["date"]).sort_values("date")
    out = out.drop_duplicates("date", keep="last").reset_index(drop=True)
    for col in ["open", "high", "low", "close", "adj_close", "volume", "dividends", "stock_splits"]:
        if col not in out.columns:
            out[col] = 0.0 if col in {"dividends", "stock_splits"} else np.nan
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out["ticker"] = ticker
    out["source"] = "yfinance"
    out["download_timestamp"] = timestamp
    return out[PRICE_COLUMNS].copy()


def normalize_actions(actions: pd.DataFrame, price_df: pd.DataFrame, ticker: str, timestamp: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if actions is not None and not actions.empty:
        act = flatten_yfinance_columns(actions, ticker).reset_index()
        cols = {str(c).strip().lower().replace(" ", "_"): c for c in act.columns}
        date_col = cols.get("date") or cols.get("datetime")
        div_col = cols.get("dividends")
        split_col = cols.get("stock_splits") or cols.get("splits")
        if date_col is not None:
            for _, row in act.iterrows():
                dividend = float(pd.to_numeric(pd.Series([row.get(div_col, 0.0)]), errors="coerce").fillna(0.0).iloc[0]) if div_col is not None else 0.0
                split = float(pd.to_numeric(pd.Series([row.get(split_col, 0.0)]), errors="coerce").fillna(0.0).iloc[0]) if split_col is not None else 0.0
                if dividend != 0.0 or split != 0.0:
                    rows.append(
                        {
                            "date": pd.to_datetime(row[date_col], errors="coerce"),
                            "ticker": ticker,
                            "dividends": dividend,
                            "stock_splits": split,
                            "source": "yfinance.Ticker.actions",
                            "download_timestamp": timestamp,
                        }
                    )
    if not rows and not price_df.empty:
        event_rows = price_df.loc[(price_df["dividends"].fillna(0) != 0) | (price_df["stock_splits"].fillna(0) != 0)]
        for _, row in event_rows.iterrows():
            rows.append(
                {
                    "date": row["date"],
                    "ticker": ticker,
                    "dividends": float(row.get("dividends", 0.0) or 0.0),
                    "stock_splits": float(row.get("stock_splits", 0.0) or 0.0),
                    "source": "yfinance.download.actions_columns",
                    "download_timestamp": timestamp,
                }
            )
    columns = ["date", "ticker", "dividends", "stock_splits", "source", "download_timestamp"]
    out = pd.DataFrame(rows, columns=columns)
    if not out.empty:
        out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.tz_localize(None)
        out = out.dropna(subset=["date"]).sort_values("date").drop_duplicates(["date", "ticker", "dividends", "stock_splits"])
    return out


def download_one(ticker: str, timestamp: str, max_retries: int, sleep_sec: float, logger: logging.Logger) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    try:
        import yfinance as yf
    except Exception as exc:
        return pd.DataFrame(columns=PRICE_COLUMNS), pd.DataFrame(), f"yfinance import failed: {exc}"

    last_error = ""
    for attempt in range(max_retries + 1):
        try:
            raw = yf.download(
                ticker,
                period="max",
                auto_adjust=False,
                actions=True,
                progress=False,
                threads=False,
            )
            price_df = normalize_price_download(raw, ticker, timestamp)
            if price_df.empty:
                raise ValueError("yfinance returned no usable price rows")
            if "adj_close" not in price_df.columns or price_df["adj_close"].isna().all():
                raise ValueError("Adj Close missing; refusing to mark ticker ready")
            actions = pd.DataFrame()
            try:
                actions = yf.Ticker(ticker).actions
            except Exception as exc:
                logger.warning("%s actions table fetch failed: %s", ticker, exc)
            action_df = normalize_actions(actions, price_df, ticker, timestamp)
            return price_df, action_df, ""
        except Exception as exc:
            last_error = str(exc)
            logger.warning("%s download attempt %s/%s failed: %s", ticker, attempt + 1, max_retries + 1, last_error)
            time.sleep(sleep_sec * (attempt + 1))
    return pd.DataFrame(columns=PRICE_COLUMNS), pd.DataFrame(), last_error


def date_stats(price_df: pd.DataFrame) -> dict[str, Any]:
    if price_df.empty:
        return {"first_date": "", "last_date": "", "n_rows": 0, "years": 0.0}
    dates = pd.to_datetime(price_df["date"], errors="coerce").dropna().sort_values()
    if dates.empty:
        return {"first_date": "", "last_date": "", "n_rows": 0, "years": 0.0}
    first, last = dates.iloc[0], dates.iloc[-1]
    return {
        "first_date": str(first.date()),
        "last_date": str(last.date()),
        "n_rows": int(dates.nunique()),
        "years": round(float((last - first).days + 1) / 365.25, 4),
    }


def missing_rate(price_df: pd.DataFrame, col: str) -> float:
    if price_df.empty or col not in price_df.columns:
        return 1.0
    return round(float(price_df[col].isna().mean()), 6)


def price_quality_row(ticker: str, price_df: pd.DataFrame, today: pd.Timestamp) -> dict[str, Any]:
    stats = date_stats(price_df)
    notes: list[str] = []
    if price_df.empty:
        notes.append("download_failed_or_empty")
    close_missing = missing_rate(price_df, "close")
    adj_missing = missing_rate(price_df, "adj_close")
    volume_missing = missing_rate(price_df, "volume")
    duplicated = int(pd.to_datetime(price_df["date"], errors="coerce").duplicated().sum()) if not price_df.empty else 0
    monotonic = bool(pd.to_datetime(price_df["date"], errors="coerce").is_monotonic_increasing) if not price_df.empty else False
    latest_lag = ""
    if stats["last_date"]:
        latest_lag = int((today.normalize() - pd.Timestamp(stats["last_date"])).days)
    non_positive_close = int((pd.to_numeric(price_df.get("close", pd.Series(dtype=float)), errors="coerce") <= 0).sum()) if not price_df.empty else 0
    non_positive_adj = int((pd.to_numeric(price_df.get("adj_close", pd.Series(dtype=float)), errors="coerce") <= 0).sum()) if not price_df.empty else 0
    non_positive_vol = int((pd.to_numeric(price_df.get("volume", pd.Series(dtype=float)), errors="coerce") < 0).sum()) if not price_df.empty else 0
    if adj_missing > 0:
        notes.append("adj_close_missing")
    if volume_missing > 0:
        notes.append("volume_missing")
    if duplicated:
        notes.append("duplicate_dates")
    if latest_lag != "" and latest_lag > 14:
        notes.append("latest_trade_stale")
    if non_positive_close:
        notes.append("non_positive_close")
    if non_positive_adj:
        notes.append("non_positive_adj_close")
    ready = bool(
        not price_df.empty
        and close_missing <= 0.01
        and adj_missing == 0
        and volume_missing <= 0.01
        and non_positive_close == 0
        and non_positive_adj == 0
        and non_positive_vol == 0
        and duplicated == 0
        and monotonic
        and (latest_lag == "" or latest_lag <= 14)
        and stats["years"] >= 10.0
    )
    return {
        "ticker": ticker,
        "first_date": stats["first_date"],
        "last_date": stats["last_date"],
        "n_rows": stats["n_rows"],
        "close_missing_rate": close_missing,
        "adj_close_missing_rate": adj_missing,
        "volume_missing_rate": volume_missing,
        "non_positive_close_count": non_positive_close,
        "non_positive_adj_close_count": non_positive_adj,
        "non_positive_volume_count": non_positive_vol,
        "duplicated_date_count": duplicated,
        "date_monotonic_increasing": monotonic,
        "latest_trade_lag_days": latest_lag,
        "has_10y_history": stats["years"] >= 10.0,
        "has_15y_history": stats["years"] >= 15.0,
        "price_quality_ready": ready,
        "price_quality_notes": ";".join(notes) if notes else "ok",
    }


def nearest_price(price_df: pd.DataFrame, split_date: pd.Timestamp) -> dict[str, Any]:
    before = price_df.loc[pd.to_datetime(price_df["date"]) < split_date].tail(1)
    after = price_df.loc[pd.to_datetime(price_df["date"]) >= split_date].head(1)
    if before.empty or after.empty:
        return {
            "raw_close_before_split": "",
            "raw_close_after_split": "",
            "adj_close_before_split": "",
            "adj_close_after_split": "",
            "raw_close_jump_ratio": "",
            "adj_close_jump_ratio": "",
        }
    raw_before = float(before["close"].iloc[0])
    raw_after = float(after["close"].iloc[0])
    adj_before = float(before["adj_close"].iloc[0])
    adj_after = float(after["adj_close"].iloc[0])
    return {
        "raw_close_before_split": raw_before,
        "raw_close_after_split": raw_after,
        "adj_close_before_split": adj_before,
        "adj_close_after_split": adj_after,
        "raw_close_jump_ratio": raw_after / raw_before if raw_before else "",
        "adj_close_jump_ratio": adj_after / adj_before if adj_before else "",
    }


def corporate_action_rows(ticker: str, price_df: pd.DataFrame, action_df: pd.DataFrame) -> list[dict[str, Any]]:
    has_table = action_df is not None
    empty = action_df is None or action_df.empty
    div_count = 0 if empty else int((pd.to_numeric(action_df["dividends"], errors="coerce").fillna(0) != 0).sum())
    split_events = pd.DataFrame() if empty else action_df.loc[pd.to_numeric(action_df["stock_splits"], errors="coerce").fillna(0) != 0]
    split_count = len(split_events)
    first_action = "" if empty else str(pd.to_datetime(action_df["date"]).min().date())
    last_action = "" if empty else str(pd.to_datetime(action_df["date"]).max().date())
    base = {
        "ticker": ticker,
        "has_action_table": bool(has_table),
        "action_table_empty": bool(empty),
        "dividend_event_count": div_count,
        "split_event_count": split_count,
        "first_action_date": first_action,
        "last_action_date": last_action,
    }
    if split_count == 0:
        return [
            {
                **base,
                "action_notes": "no_split_event" if not empty else "no_action_event",
                "split_date": "",
                "split_ratio": "",
                "raw_close_before_split": "",
                "raw_close_after_split": "",
                "adj_close_before_split": "",
                "adj_close_after_split": "",
                "raw_close_jump_ratio": "",
                "adj_close_jump_ratio": "",
                "split_sanity_pass": "",
                "split_sanity_notes": "no_split_event",
            }
        ]
    rows = []
    for _, event in split_events.iterrows():
        split_date = pd.Timestamp(event["date"])
        ratio = float(event["stock_splits"])
        near = nearest_price(price_df, split_date)
        adj_jump = near.get("adj_close_jump_ratio", "")
        pass_check = bool(adj_jump != "" and np.isfinite(float(adj_jump)) and 0.2 < float(adj_jump) < 5.0)
        rows.append(
            {
                **base,
                "action_notes": "split_event_checked",
                "split_date": str(split_date.date()),
                "split_ratio": ratio,
                **near,
                "split_sanity_pass": pass_check,
                "split_sanity_notes": "pass" if pass_check else "check_manually",
            }
        )
    return rows


def copy_current_store_to_output(store_dir: Path, out_dir: Path, tickers: list[str]) -> None:
    for sub in ["prices", "actions", "audit"]:
        (out_dir / sub).mkdir(parents=True, exist_ok=True)
    for ticker in tickers:
        for suffix, sub in [(f"{ticker}.parquet", "prices"), (f"{ticker}_actions.csv", "actions")]:
            src = store_dir / sub / suffix
            if src.exists():
                shutil.copy2(src, out_dir / sub / src.name)
    for src in (store_dir / "audit").glob("*.csv"):
        shutil.copy2(src, out_dir / "audit" / src.name)


def main() -> None:
    args = parse_args()
    timestamp = args.timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = (args.out_dir or OUTPUT_ROOT / f"unified_adjusted_ohlcv_store_{timestamp}").resolve()
    store_dir = args.store_dir.resolve()
    for sub in ["prices", "actions", "audit"]:
        (store_dir / sub).mkdir(parents=True, exist_ok=True)
    logger = setup_logger(out_dir)
    logger.info("Starting unified adjusted OHLCV store build. No training, no backtest, no MVE2.")

    universe_path = locate_ticker_universe(args.ticker_universe, args.previous_mve1_dir)
    universe = load_ticker_universe(universe_path)
    tickers = universe["ticker"].tolist()
    logger.info("Ticker universe loaded: %s (%s tickers)", universe_path, len(tickers))
    shutil.copy2(universe_path, out_dir / "mve1_audit_ticker_universe.csv")
    write_json(
        {
            "timestamp": timestamp,
            "universe_path": str(universe_path),
            "store_dir": str(store_dir),
            "out_dir": str(out_dir),
            "ticker_count": len(tickers),
            "dry_run": bool(args.dry_run),
            "auto_adjust": False,
            "no_training": True,
            "no_backtest": True,
            "no_mve2": True,
        },
        out_dir / "build_config.json",
    )
    if args.dry_run:
        logger.info("Dry-run complete.")
        return

    today = pd.Timestamp.today().tz_localize(None)
    download_rows: list[dict[str, Any]] = []
    quality_rows: list[dict[str, Any]] = []
    action_rows: list[dict[str, Any]] = []
    store_files: list[dict[str, Any]] = []

    for _, info in universe.iterrows():
        ticker = info["ticker"]
        layer = info["layer"]
        source_tag = info["source"]
        logger.info("Downloading %s (%s)", ticker, layer)
        price_df, action_df, error = download_one(ticker, timestamp, args.max_retries, args.sleep_sec, logger)
        success = bool(error == "" and not price_df.empty and price_df["adj_close"].notna().any())
        price_path = store_dir / "prices" / f"{ticker}.parquet"
        action_path = store_dir / "actions" / f"{ticker}_actions.csv"
        if success:
            price_df.to_parquet(price_path, index=False)
            action_df.to_csv(action_path, index=False, encoding="utf-8-sig")
            store_files.append({"ticker": ticker, "file_type": "price", "path": str(price_path), "rows": len(price_df)})
            store_files.append({"ticker": ticker, "file_type": "actions", "path": str(action_path), "rows": len(action_df)})
        else:
            logger.warning("%s failed; stale store files, if any, are not counted in this run. error=%s", ticker, error)
        stats = date_stats(price_df)
        has_dividends = bool(not action_df.empty and (pd.to_numeric(action_df["dividends"], errors="coerce").fillna(0) != 0).any())
        has_splits = bool(not action_df.empty and (pd.to_numeric(action_df["stock_splits"], errors="coerce").fillna(0) != 0).any())
        download_rows.append(
            {
                "ticker": ticker,
                "layer": layer,
                "source_tag": source_tag,
                "download_success": success,
                "error_message": error,
                "first_date": stats["first_date"],
                "last_date": stats["last_date"],
                "n_rows": stats["n_rows"],
                "has_adj_close": bool(success and price_df["adj_close"].notna().any()),
                "has_actions": bool(not action_df.empty),
                "has_dividends": has_dividends,
                "has_splits": has_splits,
                "download_timestamp": timestamp,
                "data_source": "yfinance(auto_adjust=False,period=max,actions=True)",
            }
        )
        qrow = price_quality_row(ticker, price_df, today)
        quality_rows.append(qrow)
        action_rows.extend(corporate_action_rows(ticker, price_df, action_df))

    download_df = pd.DataFrame(download_rows)
    quality_df = pd.DataFrame(quality_rows)
    corp_df = pd.DataFrame(action_rows)
    store_file_df = pd.DataFrame(store_files)

    download_df.to_csv(store_dir / "audit" / "download_audit.csv", index=False, encoding="utf-8-sig")
    quality_df.to_csv(store_dir / "audit" / "price_quality_audit.csv", index=False, encoding="utf-8-sig")
    corp_df.to_csv(store_dir / "audit" / "corporate_action_audit.csv", index=False, encoding="utf-8-sig")
    store_file_df.to_csv(store_dir / "audit" / "store_file_manifest.csv", index=False, encoding="utf-8-sig")

    copy_current_store_to_output(store_dir, out_dir, tickers)
    for src in [out_dir / "unified_store_build_log.txt", out_dir / "build_config.json"]:
        if src.exists():
            # already in root; keep a copy in audit for zip readers that start there
            shutil.copy2(src, out_dir / "audit" / src.name)

    shutil.copy2(Path(__file__), out_dir / Path(__file__).name)
    summary = {
        "timestamp": timestamp,
        "ticker_count": len(tickers),
        "download_success_count": int(download_df["download_success"].sum()),
        "download_failed_count": int((~download_df["download_success"]).sum()),
        "has_10y_count": int(quality_df["has_10y_history"].sum()),
        "has_15y_count": int(quality_df["has_15y_history"].sum()),
        "has_corporate_action_count": int(download_df["has_actions"].sum()),
        "has_split_count": int(download_df["has_splits"].sum()),
        "store_dir": str(store_dir),
        "out_dir": str(out_dir),
    }
    write_json(summary, out_dir / "unified_store_build_summary.json")
    logger.info("Unified store build complete: %s", summary)


if __name__ == "__main__":
    main()
