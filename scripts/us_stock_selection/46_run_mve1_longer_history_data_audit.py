"""Run MVE 1 longer-history data audit for the US stock selection rebuild.

This is not formal v9. It does not expand the formal universe, train models,
run backtests, optimize a strategy, run 31b, continue v8/v8.2 tuning, or start
MVE 2. It only audits data availability, coverage, adjustment risk, and feature
build readiness for a small pre-registered layered ticker list.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import re
import shutil
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "us_stock_selection"
DOCS_DIR = PROJECT_ROOT / "docs"
NEXT_STEPS = PROJECT_ROOT / "NEXT_STEPS.md"
RUN_SUMMARY = PROJECT_ROOT / "RUN_SUMMARY.md"
MEISTOCK_ROOT = Path("E:/dzhwork/obsydian/quant_lab/MeiStock")

V8_BOUNDED_AUDIT = OUTPUT_ROOT / "v8_2_bounded_audit_replay_20260501_113100" / "v8_2_full_score_rank_audit_trail.csv"
V8_FEATURE_CACHE = PROJECT_ROOT / "data" / "features_cache" / "us_stock_selection"
V8_RUN_FEATURE_CACHE = OUTPUT_ROOT / "run_20260426_095958" / "v7_feature_cache"
QLIB_PROVIDER = Path.home() / ".qlib" / "qlib_data" / "us_data"
V9_PRE_RESEARCH_ZIP = OUTPUT_ROOT / "us_stock_selection_quant_lab_v9_pre_research_universe_stock_selection_rebuild_20260501_193058.zip"

EXPECTED_SHORT_HISTORY = {
    "PLTR": "IPO in 2020; cannot provide 10-year listed history by 2026.",
    "SNOW": "IPO in 2020; cannot provide 10-year listed history by 2026.",
    "CRWD": "IPO in 2019; cannot provide 10-year listed history by 2026.",
    "NET": "IPO in 2019; cannot provide 10-year listed history by 2026.",
    "SHOP": "IPO in 2015; near/just above 10-year threshold depending on data end date.",
    "COIN": "IPO in 2021; cannot provide 10-year listed history by 2026.",
    "ROKU": "IPO in 2017; cannot provide 10-year listed history by 2026.",
    "AFRM": "IPO in 2021; cannot provide 10-year listed history by 2026.",
    "UPST": "IPO in 2020; cannot provide 10-year listed history by 2026.",
    "RIVN": "IPO in 2021; cannot provide 10-year listed history by 2026.",
    "LCID": "SPAC/listing history starts around 2020; cannot provide 10-year listed history by 2026.",
    "ARKK": "ETF inception in 2014; near 10-year threshold but no 15-year history.",
    "CIBR": "ETF inception in 2015; cannot provide 15-year history.",
    "SKYY": "ETF inception in 2011; no 15-year history until after 2026 if strict by date.",
    "TQQQ": "Leveraged ETF inception in 2010; path-dependent product, separate bucket required.",
    "QLD": "Leveraged ETF inception in 2006; path-dependent product, separate bucket required.",
    "SOXL": "Leveraged ETF inception in 2010; path-dependent product, separate bucket required.",
    "SSO": "Leveraged ETF inception in 2006; path-dependent product, separate bucket required.",
    "UPRO": "Leveraged ETF inception in 2009; path-dependent product, separate bucket required.",
}


PRE_REGISTERED_LAYERS: list[dict[str, str]] = [
    *[
        {
            "ticker": t,
            "layer": "Layer 1 - Mega-cap tech / core technology",
            "source": "mve1_pre_registered",
            "reason_included": "Mega-cap tech / seven majors / core technology candidate.",
            "expected_listing_constraint": EXPECTED_SHORT_HISTORY.get(t, "No known listing constraint for 10-year audit."),
            "notes": "",
        }
        for t in ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "AMD", "NFLX", "CRM", "ORCL", "ADBE", "NOW", "SHOP", "PLTR", "SNOW", "CRWD", "NET"]
    ],
    *[
        {
            "ticker": t,
            "layer": "Layer 2 - Core index ETF",
            "source": "mve1_pre_registered",
            "reason_included": "Core US equity index ETF benchmark / regime reference.",
            "expected_listing_constraint": EXPECTED_SHORT_HISTORY.get(t, "No known listing constraint for 10-year audit."),
            "notes": "",
        }
        for t in ["SPY", "QQQ", "DIA", "IWM"]
    ],
    *[
        {
            "ticker": t,
            "layer": "Layer 3 - Sector / theme ETF",
            "source": "mve1_pre_registered",
            "reason_included": "Sector or theme ETF for layer prototype audit.",
            "expected_listing_constraint": EXPECTED_SHORT_HISTORY.get(t, "ETF listing date must be checked."),
            "notes": "",
        }
        for t in ["XLK", "SMH", "SOXX", "IGV", "SKYY", "CIBR", "ARKK", "XBI", "IBB"]
    ],
    *[
        {
            "ticker": t,
            "layer": "Layer 4 - Leveraged ETF separate bucket",
            "source": "mve1_pre_registered",
            "reason_included": "Leveraged ETF must be audited as a separate path-dependent bucket.",
            "expected_listing_constraint": EXPECTED_SHORT_HISTORY.get(t, "Leveraged ETF inception and path dependence must be checked."),
            "notes": "Do not mix with ordinary stocks under the same risk assumption.",
        }
        for t in ["QLD", "TQQQ", "SOXL", "SSO", "UPRO"]
    ],
    *[
        {
            "ticker": t,
            "layer": "Layer 5 - High-beta single names",
            "source": "mve1_pre_registered",
            "reason_included": "High-beta single name requiring explicit concentration gate.",
            "expected_listing_constraint": EXPECTED_SHORT_HISTORY.get(t, "Listing date must be checked."),
            "notes": "",
        }
        for t in ["MSTR", "COIN", "ROKU", "AFRM", "UPST", "RIVN", "LCID"]
    ],
]


@dataclass
class PriceCandidate:
    ticker: str
    source_name: str
    path: Path | None
    data_format: str
    frame: pd.DataFrame
    adjusted_price_available: bool
    corporate_action_available: bool | str
    notes: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run MVE1 longer-history data audit.")
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--timestamp", default=None)
    parser.add_argument("--ticker-list", type=Path, default=None)
    parser.add_argument("--local-only", action="store_true", help="Only inspect local data sources.")
    parser.add_argument("--allow-sample-download", action="store_true", help="Allow small 3-5 ticker download feasibility test.")
    parser.add_argument("--sample-download-tickers", default="SPY,QQQ,NVDA,MSTR,TQQQ")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def setup_logger(out_dir: Path) -> logging.Logger:
    log_dir = out_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("mve1_data_audit")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    fh = logging.FileHandler(log_dir / "run.log", encoding="utf-8")
    fh.setFormatter(formatter)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(formatter)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


def sha256(path: Path) -> str:
    if not path.is_file():
        return ""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def save_json(payload: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def normalize_ticker(ticker: Any) -> str:
    return str(ticker).strip().upper().replace("-", ".")


def load_v8_candidate_tickers() -> set[str]:
    if V8_BOUNDED_AUDIT.exists():
        try:
            df = pd.read_csv(V8_BOUNDED_AUDIT, usecols=["ticker"])
            return {normalize_ticker(t) for t in df["ticker"].dropna().unique()}
        except Exception:
            pass
    if V8_FEATURE_CACHE.exists():
        return {p.name.replace("_features.parquet", "").upper() for p in V8_FEATURE_CACHE.glob("*_features.parquet")}
    return set()


def build_ticker_universe(ticker_list: Path | None = None) -> pd.DataFrame:
    rows = [dict(row) for row in PRE_REGISTERED_LAYERS]
    if ticker_list and ticker_list.exists():
        custom = pd.read_csv(ticker_list)
        for _, row in custom.iterrows():
            ticker = normalize_ticker(row.get("ticker"))
            if not ticker:
                continue
            rows.append(
                {
                    "ticker": ticker,
                    "layer": str(row.get("layer", "custom_layer")),
                    "source": str(row.get("source", "user_ticker_list")),
                    "reason_included": str(row.get("reason_included", "Provided by --ticker-list.")),
                    "expected_listing_constraint": str(row.get("expected_listing_constraint", EXPECTED_SHORT_HISTORY.get(ticker, ""))),
                    "notes": str(row.get("notes", "")),
                }
            )
    for ticker in sorted(load_v8_candidate_tickers()):
        rows.append(
            {
                "ticker": ticker,
                "layer": "v8_candidate_extension",
                "source": "v8_candidate",
                "reason_included": "Observed in v8/v8.2 full candidate audit trail.",
                "expected_listing_constraint": EXPECTED_SHORT_HISTORY.get(ticker, ""),
                "notes": "Added to MVE1 audit because v8 candidate list exists.",
            }
        )

    merged: dict[str, dict[str, Any]] = {}
    for row in rows:
        ticker = normalize_ticker(row["ticker"])
        if ticker not in merged:
            merged[ticker] = {**row, "ticker": ticker}
            continue
        old = merged[ticker]
        old["source"] = ";".join(sorted(set(str(old["source"]).split(";") + str(row["source"]).split(";"))))
        if old["layer"] == "v8_candidate_extension" and row["layer"] != "v8_candidate_extension":
            old["layer"] = row["layer"]
        old["reason_included"] = old["reason_included"] + " | " + row["reason_included"]
        if row.get("expected_listing_constraint") and not old.get("expected_listing_constraint"):
            old["expected_listing_constraint"] = row["expected_listing_constraint"]
        if row.get("notes"):
            old["notes"] = (old.get("notes", "") + " | " + row["notes"]).strip(" |")
    df = pd.DataFrame(merged.values()).sort_values(["layer", "ticker"]).reset_index(drop=True)
    return df


def lower_cols(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(c).strip().lower().replace(" ", "_") for c in out.columns]
    return out


def normalize_price_frame(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = lower_cols(df)
    if "datetime" in out.columns and "date" not in out.columns:
        out = out.rename(columns={"datetime": "date"})
    if "time" in out.columns and "date" not in out.columns:
        out = out.rename(columns={"time": "date"})
    if "adjclose" in out.columns and "adj_close" not in out.columns:
        out = out.rename(columns={"adjclose": "adj_close"})
    if "adjusted_close" in out.columns and "adj_close" not in out.columns:
        out = out.rename(columns={"adjusted_close": "adj_close"})
    if "ticker" not in out.columns:
        out["ticker"] = ticker
    if "date" not in out.columns:
        return pd.DataFrame()
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.tz_localize(None)
    out = out.dropna(subset=["date"]).sort_values("date")
    out = out.drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)
    for col in ["open", "high", "low", "close", "adj_close", "volume", "factor"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    keep = [c for c in ["date", "ticker", "open", "high", "low", "close", "adj_close", "volume", "factor"] if c in out.columns]
    return out[keep].copy()


def read_parquet_price(path: Path, ticker: str) -> pd.DataFrame:
    try:
        return normalize_price_frame(pd.read_parquet(path), ticker)
    except Exception:
        return pd.DataFrame()


def read_csv_price(path: Path, ticker: str) -> pd.DataFrame:
    try:
        return normalize_price_frame(pd.read_csv(path), ticker)
    except Exception:
        return pd.DataFrame()


def read_qlib_bin(symbol: str) -> pd.DataFrame:
    provider = QLIB_PROVIDER
    cal_path = provider / "calendars" / "day.txt"
    feature_dir = provider / "features" / symbol.lower()
    if not cal_path.exists() or not feature_dir.exists():
        return pd.DataFrame()
    try:
        cal = pd.read_csv(cal_path, header=None)[0].astype(str).tolist()
    except Exception:
        return pd.DataFrame()
    series: dict[str, pd.Series] = {}
    dates: pd.Series | None = None
    for field in ["open", "high", "low", "close", "volume", "factor"]:
        path = feature_dir / f"{field}.day.bin"
        if not path.exists():
            continue
        try:
            arr = np.fromfile(path, dtype="<f4")
            if len(arr) <= 1:
                continue
            start_idx = int(arr[0])
            vals = arr[1:]
            date_values = pd.to_datetime(cal[start_idx : start_idx + len(vals)], errors="coerce")
            if dates is None:
                dates = pd.Series(date_values)
            series[field] = pd.Series(vals[: len(date_values)])
        except Exception:
            continue
    if dates is None or not series:
        return pd.DataFrame()
    out = pd.DataFrame({"date": dates, "ticker": symbol.upper(), **series})
    return normalize_price_frame(out, symbol)


def find_updated_data_dirs() -> list[Path]:
    dirs = [p for p in (PROJECT_ROOT / "outputs").rglob("updated_data") if p.is_dir()]
    dirs.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    return dirs


def choose_updated_data(ticker: str, dirs: list[Path]) -> PriceCandidate | None:
    best: PriceCandidate | None = None
    best_rows = -1
    best_max = pd.Timestamp.min
    for directory in dirs:
        path = directory / f"{ticker}.csv"
        if not path.exists():
            continue
        frame = read_csv_price(path, ticker)
        if frame.empty:
            continue
        max_date = frame["date"].max()
        score_rows = len(frame)
        if max_date > best_max or (max_date == best_max and score_rows > best_rows):
            best_max = max_date
            best_rows = score_rows
            best = PriceCandidate(
                ticker=ticker,
                source_name=f"updated_data_csv::{directory.relative_to(PROJECT_ROOT)}",
                path=path,
                data_format="csv",
                frame=frame,
                adjusted_price_available="adj_close" in frame.columns,
                corporate_action_available=False,
                notes="Existing updated_data CSV; often yfinance-derived but adj_close is not explicit if only close exists.",
            )
    return best


def load_best_local_price(ticker: str, updated_dirs: list[Path]) -> PriceCandidate | None:
    ticker = normalize_ticker(ticker)
    feature_path = V8_FEATURE_CACHE / f"{ticker}_features.parquet"
    if feature_path.exists():
        frame = read_parquet_price(feature_path, ticker)
        if not frame.empty:
            return PriceCandidate(
                ticker=ticker,
                source_name="v8_feature_cache_parquet",
                path=feature_path,
                data_format="parquet",
                frame=frame,
                adjusted_price_available="adj_close" in frame.columns,
                corporate_action_available=False,
                notes="Best local source for v8 candidate tickers; has adjusted OHLCV-like columns but no split/dividend event table.",
            )
    updated = choose_updated_data(ticker, updated_dirs)
    if updated is not None:
        return updated
    qlib = read_qlib_bin(ticker)
    if not qlib.empty:
        return PriceCandidate(
            ticker=ticker,
            source_name="qlib_provider_us_data_bin",
            path=QLIB_PROVIDER / "features" / ticker.lower(),
            data_format="qlib_bin",
            frame=qlib,
            adjusted_price_available=False,
            corporate_action_available="factor_field_only" if "factor" in qlib.columns else False,
            notes="Local qlib provider is useful for long-history presence but appears stale versus 2026 and lacks explicit adj_close/actions.",
        )
    return None


def source_inventory(tickers: list[str], updated_dirs: list[Path], logger: logging.Logger) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    def add_row(source_name: str, path: Path, data_format: str, frames: list[pd.DataFrame], adj: Any, volume: Any, corp: Any, usable: Any, notes: str) -> None:
        non_empty = [f for f in frames if f is not None and not f.empty and "date" in f.columns]
        date_min = min((f["date"].min() for f in non_empty), default="")
        date_max = max((f["date"].max() for f in non_empty), default="")
        rows.append(
            {
                "source_name": source_name,
                "path": str(path),
                "exists": path.exists(),
                "data_format": data_format,
                "ticker_coverage_estimate": len(non_empty),
                "date_min": "" if date_min == "" else str(pd.Timestamp(date_min).date()),
                "date_max": "" if date_max == "" else str(pd.Timestamp(date_max).date()),
                "adjusted_price_available": adj,
                "volume_available": volume,
                "corporate_action_available": corp,
                "usable_for_mve1": usable,
                "notes": notes,
            }
        )
        logger.info("Source inventory: %s exists=%s coverage=%s", source_name, path.exists(), len(non_empty))

    frames = []
    if V8_FEATURE_CACHE.exists():
        for ticker in tickers:
            path = V8_FEATURE_CACHE / f"{ticker}_features.parquet"
            if path.exists():
                frames.append(read_parquet_price(path, ticker))
    add_row(
        "v8_feature_cache_parquet",
        V8_FEATURE_CACHE,
        "parquet_per_ticker",
        frames,
        True,
        True,
        False,
        bool(frames),
        "Local v8 feature cache with OHLCV/adj_close for existing v8 candidates; no corporate action event table.",
    )

    frames = []
    for path in [V8_RUN_FEATURE_CACHE / "alpha158_cache.parquet", V8_RUN_FEATURE_CACHE / "alpha360_cache.parquet"]:
        if path.exists():
            try:
                df = pd.read_parquet(path, columns=["date", "instrument"])
                df = df.loc[df["instrument"].astype(str).str.upper().isin(tickers)]
                df = df.rename(columns={"instrument": "ticker"})
                frames.append(normalize_price_frame(df, ""))
            except Exception:
                pass
    add_row(
        "v8_run_v7_feature_cache",
        V8_RUN_FEATURE_CACHE,
        "parquet_panel_features",
        frames,
        False,
        False,
        False,
        bool(frames),
        "Feature panel can confirm instrument/date coverage but does not expose adjusted OHLCV directly.",
    )

    qlib_frames = []
    if QLIB_PROVIDER.exists():
        for ticker in tickers:
            frame = read_qlib_bin(ticker)
            if not frame.empty:
                qlib_frames.append(frame)
    add_row(
        "qlib_provider_us_data_bin",
        QLIB_PROVIDER,
        "qlib_bin",
        qlib_frames,
        "not_explicit",
        True,
        "factor_field_only",
        bool(qlib_frames),
        "Local qlib provider has broad historical bin data but appears to end around 2020-11 and lacks explicit adj_close/actions.",
    )

    for source_path in [
        PROJECT_ROOT / "data" / "raw" / "us" / "us_stock_selection",
        PROJECT_ROOT / "data" / "raw" / "us",
        PROJECT_ROOT / "data" / "raw",
        PROJECT_ROOT / "data" / "processed",
        PROJECT_ROOT / "data" / "external" / "legacy_quant" / "NSDQStock",
    ]:
        frames = []
        if source_path.exists():
            for ticker in tickers:
                for path in [source_path / f"{ticker}.csv", source_path / f"{ticker.lower()}.csv"]:
                    if path.exists():
                        frames.append(read_csv_price(path, ticker))
                        break
        add_row(
            f"local_file_dir::{source_path.relative_to(PROJECT_ROOT) if source_path.is_relative_to(PROJECT_ROOT) else source_path}",
            source_path,
            "csv/parquet_directory",
            frames,
            "unknown",
            "unknown",
            "unknown",
            bool(frames),
            "Checked as requested local path.",
        )

    for directory in updated_dirs[:8]:
        frames = []
        for ticker in tickers:
            path = directory / f"{ticker}.csv"
            if path.exists():
                frames.append(read_csv_price(path, ticker))
        add_row(
            f"updated_data_csv::{directory.relative_to(PROJECT_ROOT)}",
            directory,
            "csv_per_ticker",
            frames,
            "not_explicit",
            True,
            False,
            bool(frames),
            "Existing output updated_data directory; useful mainly for ETF/local sample continuity.",
        )

    mei_context = MEISTOCK_ROOT / "docs" / "context" / "MeiStock_current_context.md"
    add_row(
        "MeiStock_context_index",
        mei_context,
        "markdown",
        [],
        False,
        False,
        False,
        False,
        "Context/checkpoint only; no local price table discovered there by this audit.",
    )
    return pd.DataFrame(rows)


def date_stats(frame: pd.DataFrame) -> dict[str, Any]:
    if frame is None or frame.empty or "date" not in frame.columns:
        return {"date_min": "", "date_max": "", "calendar_days": 0, "trading_days": 0, "years_covered": 0.0}
    dates = pd.to_datetime(frame["date"], errors="coerce").dropna().sort_values()
    if dates.empty:
        return {"date_min": "", "date_max": "", "calendar_days": 0, "trading_days": 0, "years_covered": 0.0}
    dmin, dmax = dates.iloc[0], dates.iloc[-1]
    cal_days = int((dmax - dmin).days + 1)
    return {
        "date_min": str(dmin.date()),
        "date_max": str(dmax.date()),
        "calendar_days": cal_days,
        "trading_days": int(dates.nunique()),
        "years_covered": round(cal_days / 365.25, 3),
    }


def missing_day_stats(frame: pd.DataFrame) -> tuple[int, float]:
    if frame.empty or "date" not in frame.columns:
        return 0, 1.0
    dates = pd.to_datetime(frame["date"], errors="coerce").dropna().dt.normalize().drop_duplicates()
    if dates.empty:
        return 0, 1.0
    business_days = pd.date_range(dates.min(), dates.max(), freq="B")
    missing = len(set(business_days) - set(dates))
    ratio = missing / max(len(business_days), 1)
    return int(missing), round(float(ratio), 4)


def ratio_jump_count(series: pd.Series, threshold: float = 0.2) -> int:
    s = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if len(s) < 2:
        return 0
    jumps = s.pct_change().abs()
    return int((jumps > threshold).sum())


def quality_score(frame: pd.DataFrame, has_adj_close: bool, duplicate_count: int, missing_ratio: float, zero_volume_days: int) -> float:
    score = 0.0
    if not frame.empty:
        score += 20
    stats = date_stats(frame)
    if stats["years_covered"] >= 10:
        score += 20
    elif stats["years_covered"] >= 5:
        score += 10
    if has_adj_close:
        score += 20
    if "volume" in frame.columns and frame["volume"].notna().any():
        score += 15
    if duplicate_count == 0:
        score += 10
    if missing_ratio <= 0.08:
        score += 10
    elif missing_ratio <= 0.15:
        score += 5
    if zero_volume_days == 0:
        score += 5
    elif zero_volume_days < max(len(frame) * 0.01, 5):
        score += 2
    return round(min(score, 100.0), 2)


def price_coverage(ticker_universe: pd.DataFrame, updated_dirs: list[Path], logger: logging.Logger) -> tuple[pd.DataFrame, dict[str, PriceCandidate]]:
    rows: list[dict[str, Any]] = []
    loaded: dict[str, PriceCandidate] = {}
    for _, info in ticker_universe.iterrows():
        ticker = normalize_ticker(info["ticker"])
        candidate = load_best_local_price(ticker, updated_dirs)
        if candidate is None:
            frame = pd.DataFrame()
            source_used = "missing"
            has_adj = False
            corp = False
            notes = "No readable local price data found."
        else:
            frame = candidate.frame
            loaded[ticker] = candidate
            source_used = candidate.source_name
            has_adj = bool(candidate.adjusted_price_available)
            corp = candidate.corporate_action_available
            notes = candidate.notes
        stats = date_stats(frame)
        has_cols = {col: col in frame.columns and frame[col].notna().any() for col in ["open", "high", "low", "close", "adj_close", "volume"]}
        duplicate_count = 0 if frame.empty else int(pd.to_datetime(frame["date"], errors="coerce").duplicated().sum())
        missing_count, missing_ratio = missing_day_stats(frame)
        zero_volume = 0
        if "volume" in frame.columns:
            zero_volume = int((pd.to_numeric(frame["volume"], errors="coerce").fillna(-1) == 0).sum())
        split_suspect = False
        dividend_suspect = False
        warnings: list[str] = []
        if not has_cols.get("adj_close", False):
            warnings.append("adj_close_missing_or_not_explicit")
        if not has_cols.get("volume", False):
            warnings.append("volume_missing")
        if stats["years_covered"] < 10 and not info.get("expected_listing_constraint"):
            warnings.append("less_than_10y_without_known_listing_constraint")
        if source_used == "qlib_provider_us_data_bin":
            warnings.append("qlib_provider_stale_ends_around_2020")
        if missing_ratio > 0.15:
            warnings.append("high_business_day_missing_ratio")
        score = quality_score(frame, has_cols.get("adj_close", False), duplicate_count, missing_ratio, zero_volume)
        mve2_ready = (
            stats["years_covered"] >= 10
            and has_cols.get("adj_close", False)
            and has_cols.get("volume", False)
            and duplicate_count == 0
            and missing_ratio <= 0.15
            and source_used != "qlib_provider_us_data_bin"
        )
        row = {
            "ticker": ticker,
            "layer": info["layer"],
            "source_used": source_used,
            **stats,
            "has_10y_history": stats["years_covered"] >= 10,
            "has_15y_history": stats["years_covered"] >= 15,
            "expected_short_history_reason": info.get("expected_listing_constraint", ""),
            "missing_day_count": missing_count,
            "missing_day_ratio": missing_ratio,
            "has_open": has_cols.get("open", False),
            "has_high": has_cols.get("high", False),
            "has_low": has_cols.get("low", False),
            "has_close": has_cols.get("close", False),
            "has_adj_close": has_cols.get("adj_close", False),
            "has_volume": has_cols.get("volume", False),
            "zero_volume_days": zero_volume,
            "duplicate_date_count": duplicate_count,
            "split_adjustment_suspect": split_suspect,
            "dividend_adjustment_suspect": dividend_suspect,
            "data_quality_score": score,
            "mve2_ready": bool(mve2_ready),
            "warnings": ";".join(warnings),
        }
        rows.append(row)
        logger.info("Coverage %s source=%s years=%s score=%s ready=%s", ticker, source_used, stats["years_covered"], score, mve2_ready)
    return pd.DataFrame(rows), loaded


def adjustment_sanity(loaded: dict[str, PriceCandidate], tickers: list[str]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for ticker in tickers:
        ticker = normalize_ticker(ticker)
        candidate = loaded.get(ticker)
        frame = pd.DataFrame() if candidate is None else candidate.frame
        has_close = "close" in frame.columns and frame["close"].notna().any()
        has_adj = "adj_close" in frame.columns and frame["adj_close"].notna().any()
        if has_close and has_adj:
            ratio = (pd.to_numeric(frame["adj_close"], errors="coerce") / pd.to_numeric(frame["close"], errors="coerce")).replace([np.inf, -np.inf], np.nan)
            ratio_min = ratio.min(skipna=True)
            ratio_max = ratio.max(skipna=True)
            jumps = ratio_jump_count(ratio, threshold=0.2)
        else:
            ratio_min = math.nan
            ratio_max = math.nan
            jumps = 0
        close_jump = ratio_jump_count(pd.to_numeric(frame["close"], errors="coerce"), threshold=0.8) if has_close else 0
        suspect_unadjusted = bool(close_jump > 0 and not has_adj)
        suspect_bad = bool(jumps > 5 or (has_close and has_adj and ratio_min <= 0))
        rows.append(
            {
                "ticker": ticker,
                "has_split_history_info": False if candidate is None else candidate.corporate_action_available == "factor_field_only",
                "has_dividend_info": False,
                "raw_close_available": has_close,
                "adj_close_available": has_adj,
                "close_adj_ratio_min": "" if pd.isna(ratio_min) else round(float(ratio_min), 6),
                "close_adj_ratio_max": "" if pd.isna(ratio_max) else round(float(ratio_max), 6),
                "large_ratio_jump_count": jumps,
                "suspect_unadjusted_split": suspect_unadjusted,
                "suspect_bad_adjustment": suspect_bad,
                "notes": "No explicit split/dividend event table in selected local source." if candidate is not None else "No local frame loaded.",
            }
        )
    return pd.DataFrame(rows)


def feature_build_readiness(ticker_universe: pd.DataFrame, coverage: pd.DataFrame, loaded: dict[str, PriceCandidate]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, info in ticker_universe.iterrows():
        ticker = normalize_ticker(info["ticker"])
        frame = loaded.get(ticker).frame if ticker in loaded else pd.DataFrame()
        price_col = "adj_close" if "adj_close" in frame.columns and frame["adj_close"].notna().any() else ("close" if "close" in frame.columns else None)
        has_volume = "volume" in frame.columns and frame["volume"].notna().any()
        n = len(frame)
        flags = {
            "can_build_returns_1d": price_col is not None and n > 2,
            "can_build_returns_21d": price_col is not None and n > 21,
            "can_build_returns_63d": price_col is not None and n > 63,
            "can_build_returns_126d": price_col is not None and n > 126,
            "can_build_returns_252d": price_col is not None and n > 252,
            "can_build_vol_20d": price_col is not None and n > 20,
            "can_build_vol_63d": price_col is not None and n > 63,
            "can_build_vol_126d": price_col is not None and n > 126,
            "can_build_maxdd_63d": price_col is not None and n > 63,
            "can_build_distance_to_252d_high": price_col is not None and n > 252,
            "can_build_adv_20d": has_volume and n > 20,
            "can_build_liquidity_filter": has_volume and n > 20,
            "can_build_forward_21d_audit": price_col is not None and n > 21,
            "can_build_forward_42d_audit": price_col is not None and n > 42,
            "can_build_forward_63d_audit": price_col is not None and n > 63,
        }
        if not frame.empty and n > 252:
            minimum_date = str(pd.to_datetime(frame["date"]).sort_values().iloc[min(252, n - 1)].date())
        else:
            minimum_date = ""
        blocking = [name for name, ok in flags.items() if not ok]
        score = round(sum(bool(v) for v in flags.values()) / len(flags), 4)
        if price_col != "adj_close":
            blocking.append("explicit_adj_close_missing")
        rows.append(
            {
                "ticker": ticker,
                **flags,
                "minimum_feature_ready_date": minimum_date,
                "feature_readiness_score": score,
                "blocking_fields": ";".join(blocking),
            }
        )
    return pd.DataFrame(rows)


def layer_readiness(ticker_universe: pd.DataFrame, coverage: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
    merged = ticker_universe[["ticker", "layer"]].merge(coverage, on=["ticker", "layer"], how="left").merge(
        features[["ticker", "feature_readiness_score"]], on="ticker", how="left"
    )
    rows: list[dict[str, Any]] = []
    for layer, g in merged.groupby("layer", sort=True):
        ticker_count = len(g)
        ready_10 = int(g["has_10y_history"].fillna(False).sum())
        ready_15 = int(g["has_15y_history"].fillna(False).sum())
        adj_rate = float(g["has_adj_close"].fillna(False).mean()) if ticker_count else 0.0
        vol_rate = float(g["has_volume"].fillna(False).mean()) if ticker_count else 0.0
        feature_rate = float((g["feature_readiness_score"].fillna(0) >= 0.9).mean()) if ticker_count else 0.0
        mve2_rate = float(g["mve2_ready"].fillna(False).mean()) if ticker_count else 0.0
        blockers = []
        if ready_10 < max(1, math.ceil(ticker_count * 0.4)):
            blockers.append("limited_10y_history")
        if adj_rate < 0.6:
            blockers.append("explicit_adj_close_coverage_low")
        if vol_rate < 0.8:
            blockers.append("volume_coverage_low")
        if layer == "Layer 4 - Leveraged ETF separate bucket":
            blockers.append("path_dependent_leveraged_bucket_must_remain_separate")
        mve2_ready = (
            ticker_count > 0
            and vol_rate >= 0.8
            and feature_rate >= 0.8
            and (adj_rate >= 0.6 or "Leveraged ETF" in layer)
            and (ready_10 >= 3 or "High-beta" in layer or "v8_candidate" in layer)
        )
        if "Layer 1" in layer and (ready_10 < 12 or adj_rate < 0.7):
            mve2_ready = False
        if "Layer 2" in layer and (ready_10 < 3 or adj_rate < 0.75):
            mve2_ready = False
        rows.append(
            {
                "layer": layer,
                "ticker_count": ticker_count,
                "ticker_count_10y_ready": ready_10,
                "ticker_count_15y_ready": ready_15,
                "avg_years_covered": round(float(g["years_covered"].fillna(0).mean()), 3),
                "adjusted_close_coverage_rate": round(adj_rate, 4),
                "volume_coverage_rate": round(vol_rate, 4),
                "feature_ready_rate": round(feature_rate, 4),
                "main_blockers": ";".join(blockers),
                "mve2_ready": bool(mve2_ready),
                "recommended_action": "Ready for small MVE2 prototype only if unified adjusted OHLCV store is approved."
                if mve2_ready
                else "Resolve blockers before relying on this layer in MVE2.",
            }
        )
    return pd.DataFrame(rows)


def dependency_available(module_name: str) -> tuple[bool, str]:
    try:
        __import__(module_name)
        return True, ""
    except Exception as exc:
        return False, str(exc)


def yfinance_download_feasibility(sample_tickers: list[str], allow: bool, logger: logging.Logger) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    dep_ok, dep_err = dependency_available("yfinance")
    if not allow:
        for ticker in sample_tickers:
            rows.append(
                {
                    "source_candidate": "yfinance",
                    "dependency_available": dep_ok,
                    "network_required": True,
                    "sample_ticker": ticker,
                    "download_success": False,
                    "date_min": "",
                    "date_max": "",
                    "adjusted_close_available": False,
                    "volume_available": False,
                    "corporate_action_available": False,
                    "failure_reason": "not_executed_local_only",
                    "recommended_use": "Run with --allow-sample-download if local data is insufficient.",
                }
            )
        return pd.DataFrame(rows)
    if not dep_ok:
        for ticker in sample_tickers:
            rows.append(
                {
                    "source_candidate": "yfinance",
                    "dependency_available": False,
                    "network_required": True,
                    "sample_ticker": ticker,
                    "download_success": False,
                    "date_min": "",
                    "date_max": "",
                    "adjusted_close_available": False,
                    "volume_available": False,
                    "corporate_action_available": False,
                    "failure_reason": dep_err,
                    "recommended_use": "Dependency unavailable; do not rely on yfinance until environment is fixed.",
                }
            )
        return pd.DataFrame(rows)
    import yfinance as yf

    for ticker in sample_tickers:
        failure = ""
        df = pd.DataFrame()
        actions_available = False
        try:
            logger.info("Sample download feasibility: yfinance %s", ticker)
            df = yf.download(ticker, start="2000-01-01", auto_adjust=False, actions=True, progress=False, threads=False)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
            df = df.reset_index()
            actions_available = any(str(c).lower() in {"dividends", "stock_splits", "splits"} for c in df.columns)
        except Exception as exc:
            failure = str(exc)
            df = pd.DataFrame()
        norm = normalize_price_frame(df, ticker)
        stats = date_stats(norm)
        rows.append(
            {
                "source_candidate": "yfinance",
                "dependency_available": True,
                "network_required": True,
                "sample_ticker": ticker,
                "download_success": not norm.empty,
                "date_min": stats["date_min"],
                "date_max": stats["date_max"],
                "adjusted_close_available": "adj_close" in norm.columns and norm["adj_close"].notna().any(),
                "volume_available": "volume" in norm.columns and norm["volume"].notna().any(),
                "corporate_action_available": actions_available,
                "failure_reason": failure if norm.empty else "",
                "recommended_use": "Feasible as candidate source, but should be wrapped into a unified adjusted OHLCV store with audit logs."
                if not norm.empty
                else "Not recommended until failure is resolved.",
            }
        )
    return pd.DataFrame(rows)


def recommendation(coverage: pd.DataFrame, layers: pd.DataFrame, download: pd.DataFrame) -> dict[str, Any]:
    mve2_ready_layers = layers.loc[layers["mve2_ready"], "layer"].tolist() if not layers.empty else []
    not_ready_layers = layers.loc[~layers["mve2_ready"], "layer"].tolist() if not layers.empty else []
    deferred = coverage.loc[~coverage["mve2_ready"].fillna(False), ["ticker", "layer", "warnings"]].to_dict("records")
    sample_ok = bool(download.get("download_success", pd.Series(dtype=bool)).fillna(False).any()) if not download.empty else False
    local_adj_count = int(coverage["has_adj_close"].fillna(False).sum()) if not coverage.empty else 0
    local_10y_count = int(coverage["has_10y_history"].fillna(False).sum()) if not coverage.empty else 0
    core_layers_ready = bool(
        ("Layer 1 - Mega-cap tech / core technology" in mve2_ready_layers)
        and ("Layer 2 - Core index ETF" in mve2_ready_layers)
        and local_10y_count >= 20
        and local_adj_count >= 20
    )
    sector_layer_ready = "Layer 3 - Sector / theme ETF" in mve2_ready_layers
    mve2_ready = bool(core_layers_ready and sector_layer_ready)
    blocking = []
    if not mve2_ready:
        blocking.append("Layer-level readiness is partial; Sector/theme ETF and high-beta layers need a unified adjusted OHLCV store before MVE2 is treated as reliable.")
    if sample_ok:
        primary = "local v8_feature_cache for existing v8 names + yfinance feasibility confirmed for building a unified adjusted OHLCV store"
    else:
        primary = "local v8_feature_cache only; download source not confirmed"
        blocking.append("No successful sample download feasibility check.")
    if any(coverage["source_used"].astype(str).str.contains("qlib_provider").fillna(False)):
        blocking.append("Local qlib provider is broad but stale around 2020 and lacks explicit adj_close/actions.")
    return {
        "mve1_status": "completed",
        "mve2_ready": mve2_ready,
        "mve2_ready_condition": "not_ready_strict; limited MVE2 design could be proposed only after user approval and with explicit layer exclusions",
        "recommended_primary_data_source": primary,
        "recommended_initial_layers": mve2_ready_layers,
        "not_ready_layers": not_ready_layers,
        "excluded_or_deferred_tickers": deferred[:80],
        "blocking_issues": blocking,
        "next_recommended_task": "Build unified adjusted OHLCV store / rerun MVE1 or approve limited MVE2 with explicit caveats",
        "requires_user_approval": True,
    }


def md_table(df: pd.DataFrame, max_rows: int = 30) -> str:
    if df.empty:
        return "_No rows._"
    view = df.head(max_rows).copy()
    return view.to_markdown(index=False)


def write_docs(
    timestamp: str,
    out_dir: Path,
    zip_path: Path,
    ticker_universe: pd.DataFrame,
    inventory: pd.DataFrame,
    download: pd.DataFrame,
    coverage: pd.DataFrame,
    adjustment: pd.DataFrame,
    features: pd.DataFrame,
    layers: pd.DataFrame,
    rec: dict[str, Any],
) -> list[Path]:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    report = out_dir / "reports" / f"US_STOCK_SELECTION_MVE1_LONGER_HISTORY_DATA_AUDIT_{timestamp}.md"
    summary = out_dir / "reports" / f"US_STOCK_SELECTION_MVE1_DATA_AUDIT_EXEC_SUMMARY_{timestamp}.md"
    report.parent.mkdir(parents=True, exist_ok=True)

    local_10y = int(coverage["has_10y_history"].fillna(False).sum()) if not coverage.empty else 0
    local_15y = int(coverage["has_15y_history"].fillna(False).sum()) if not coverage.empty else 0
    adj_count = int(coverage["has_adj_close"].fillna(False).sum()) if not coverage.empty else 0
    sample_success = int(download["download_success"].fillna(False).sum()) if "download_success" in download.columns else 0

    report_text = f"""# US Stock Selection MVE1 Longer-History Data Audit - {timestamp}

## 1. 背景和目的

本轮是 MVE 1：longer-history data audit。它不是正式 v9，不扩正式 universe，不训练模型，不跑回测，不做策略优化，不运行 31b，也不启动 MVE 2。

## 2. 为什么先做数据审计

v8/v8.2 已经证明当前 36 个候选池和短历史窗口存在 top-month concentration、high-beta dependence、样本短和 universe 上限问题。正式重构 stock selection 前，必须先确认 10-15 年 adjusted OHLCV、volume、corporate action 信息和基础特征是否可用。

## 3. Ticker Universe 审计清单

- 去重后 ticker 数：{len(ticker_universe)}
- 来源：预注册分层清单 + v8_candidate。

{md_table(ticker_universe, 80)}

## 4. 本地数据源检查

{md_table(inventory, 80)}

## 5. 下载可行性检查

本轮只允许小样本下载可行性测试，不做批量下载。成功样本数：{sample_success}。

{md_table(download, 20)}

## 6. 数据覆盖和质量结果

- has_10y_history ticker 数：{local_10y}
- has_15y_history ticker 数：{local_15y}
- explicit adj_close 可用 ticker 数：{adj_count}

{md_table(coverage[["ticker", "layer", "source_used", "date_min", "date_max", "years_covered", "has_10y_history", "has_adj_close", "data_quality_score", "mve2_ready", "warnings"]], 80)}

## 7. adjusted price / corporate action 风险

本地 v8 feature cache 有 `adj_close`，但没有 split/dividend event table；updated_data CSV 多为 yfinance 派生但 `adj_close` 不一定显式；qlib provider 有 factor 字段但不是完整 corporate action 审计表。后续不能直接把未明确复权的 `close` 当成正式回测价格。

{md_table(adjustment, 30)}

## 8. Feature Build Readiness

{md_table(features, 80)}

## 9. Universe Layer Readiness

{md_table(layers, 20)}

## 10. 是否具备 MVE 2 条件

`mve2_ready = {rec["mve2_ready"]}`。

## 11. 主要阻塞项

{chr(10).join(f"- {x}" for x in rec["blocking_issues"])}

## 12. 下一步建议

- 推荐主数据源：{rec["recommended_primary_data_source"]}
- 推荐先进入的 layer：{", ".join(rec["recommended_initial_layers"]) if rec["recommended_initial_layers"] else "None"}
- 下一步建议：{rec["next_recommended_task"]}
- 是否需要用户/ChatGPT 批准：{rec["requires_user_approval"]}

本轮暂停，不启动 MVE 2。
"""
    summary_text = f"""# MVE1 Data Audit Exec Summary - {timestamp}

- 本轮不是正式 v9；未训练、未回测、未启动 MVE 2。
- 审计 ticker 数：{len(ticker_universe)}。
- has_10y_history：{local_10y}；has_15y_history：{local_15y}。
- explicit adj_close 覆盖：{adj_count}。
- sample download 成功：{sample_success}。
- MVE2 ready：{rec["mve2_ready"]}。
- 下一步：{rec["next_recommended_task"]}，需用户/ChatGPT 批准。
"""
    report.write_text(report_text, encoding="utf-8")
    summary.write_text(summary_text, encoding="utf-8")
    doc_root_report = DOCS_DIR / report.name
    doc_root_summary = DOCS_DIR / summary.name
    shutil.copy2(report, doc_root_report)
    shutil.copy2(summary, doc_root_summary)
    return [doc_root_report, doc_root_summary]


def update_next_steps(out_dir: Path, zip_path: Path, rec: dict[str, Any], coverage: pd.DataFrame, layers: pd.DataFrame) -> None:
    text = NEXT_STEPS.read_text(encoding="utf-8") if NEXT_STEPS.exists() else "# NEXT_STEPS\n"
    marker = "## MVE 1 - longer-history data audit"
    section = f"""## MVE 1 - longer-history data audit

- 执行状态：completed，随后按要求暂停，不启动 MVE 2。
- 输出目录：`{out_dir}`
- zip：`{zip_path}`
- 是否找到可用 10-15 年数据：`10y={int(coverage["has_10y_history"].fillna(False).sum())}`, `15y={int(coverage["has_15y_history"].fillna(False).sum())}`
- 推荐主数据源：`{rec["recommended_primary_data_source"]}`
- ready layer：`{", ".join(layers.loc[layers["mve2_ready"], "layer"].tolist()) if not layers.empty else "None"}`
- 是否建议启动 MVE 2：`{rec["mve2_ready"]}`
- 是否需要用户/ChatGPT 批准：`{rec["requires_user_approval"]}`
- 本轮边界：未进入正式 v9，未训练模型，未跑回测，未启动 MVE 2。
"""
    pattern = re.compile(r"## MVE 1 - longer-history data audit\n.*?(?=\n## |\Z)", re.S)
    if pattern.search(text):
        text = pattern.sub(lambda _: section.strip(), text)
    else:
        text = text.rstrip() + "\n\n" + section.strip() + "\n"
    NEXT_STEPS.write_text(text, encoding="utf-8")
    shutil.copy2(NEXT_STEPS, out_dir / "NEXT_STEPS.md")


def write_run_summary(out_dir: Path, zip_path: Path, rec: dict[str, Any]) -> None:
    text = f"""# RUN_SUMMARY

本轮目标：MVE 1 - longer-history data audit。

新 run 目录：`{out_dir}`

zip：`{zip_path}`

是否正式进入 v9：`False`

是否扩正式 universe：`False`

是否训练模型：`False`

是否运行 31b：`False`

是否跑回测：`False`

是否启动 MVE 2：`False`

MVE2 ready：`{rec["mve2_ready"]}`

下一步建议：`{rec["next_recommended_task"]}`，但需用户/ChatGPT 另行批准。
"""
    RUN_SUMMARY.write_text(text, encoding="utf-8")
    (out_dir / "RUN_SUMMARY.md").write_text(text, encoding="utf-8")


def write_workbook(out_dir: Path, timestamp: str, frames: dict[str, pd.DataFrame]) -> Path:
    path = out_dir / "reports" / f"mve1_longer_history_data_audit_tables_{timestamp}.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for key, frame in frames.items():
            sheet = key[:31]
            frame.to_excel(writer, sheet_name=sheet, index=False)
    return path


def sync_meistock(timestamp: str, out_dir: Path, zip_path: Path, docs: list[Path]) -> pd.DataFrame:
    if not MEISTOCK_ROOT.exists():
        return pd.DataFrame([{"target": str(MEISTOCK_ROOT), "status": "warning", "note": "MeiStock root missing"}])
    dirs = {
        "checkpoint": MEISTOCK_ROOT / "01_对话沉淀" / "Codex",
        "reports": MEISTOCK_ROOT / "02_项目文档" / "报告章节底稿",
        "evidence": MEISTOCK_ROOT / "06_证据链",
        "attachments": MEISTOCK_ROOT / "07_附件索引",
        "control": MEISTOCK_ROOT / "00_项目总控",
        "context": MEISTOCK_ROOT / "docs" / "context",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, str]] = []
    for doc in docs:
        dest = dirs["reports"] / doc.name
        shutil.copy2(doc, dest)
        rows.append({"target": str(dest), "status": "copied", "note": "report"})
    for source in out_dir.glob("mve1_*.csv"):
        dest = dirs["evidence"] / f"{timestamp}_{source.name}"
        shutil.copy2(source, dest)
        rows.append({"target": str(dest), "status": "copied", "note": "csv"})
    for source in out_dir.glob("mve1_*.json"):
        dest = dirs["evidence"] / f"{timestamp}_{source.name}"
        shutil.copy2(source, dest)
        rows.append({"target": str(dest), "status": "copied", "note": "json"})
    shutil.copy2(NEXT_STEPS, dirs["control"] / "NEXT_STEPS.md")
    rows.append({"target": str(dirs["control"] / "NEXT_STEPS.md"), "status": "copied", "note": "NEXT_STEPS"})
    if zip_path.exists():
        dest = dirs["attachments"] / zip_path.name
        shutil.copy2(zip_path, dest)
        rows.append({"target": str(dest), "status": "copied", "note": "zip"})
    checkpoint = f"""# Codex Checkpoint - MVE1 Longer-History Data Audit {timestamp}

- This is not formal v9.
- No formal universe expansion, no model training, no backtest, no MVE2 started.
- Zip: `{zip_path}`
"""
    cp = dirs["checkpoint"] / f"{timestamp}_mve1_longer_history_data_audit_checkpoint.md"
    cp.write_text(checkpoint, encoding="utf-8")
    rows.append({"target": str(cp), "status": "written", "note": "checkpoint"})
    context = f"""# MeiStock Current Context

Last updated: {timestamp}

Latest checkpoint: MVE 1 longer-history data audit.

This is not formal v9. No formal universe expansion, no model training, no backtest, and MVE 2 was not started.

Latest zip: `{zip_path}`.
"""
    ctx = dirs["context"] / "MeiStock_current_context.md"
    ctx.write_text(context, encoding="utf-8")
    rows.append({"target": str(ctx), "status": "written", "note": "context"})
    return pd.DataFrame(rows)


def package(out_dir: Path, docs: list[Path], zip_path: Path) -> None:
    files = [
        PROJECT_ROOT / "scripts" / "us_stock_selection" / "46_run_mve1_longer_history_data_audit.py",
        NEXT_STEPS,
        RUN_SUMMARY,
        *docs,
    ]
    files.extend([p for p in out_dir.rglob("*") if p.is_file()])
    if zip_path.exists():
        zip_path.unlink()
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        seen: set[str] = set()
        for path in files:
            if not path.exists():
                continue
            arc = str(path.relative_to(PROJECT_ROOT)) if path.is_relative_to(PROJECT_ROOT) else path.name
            if arc in seen:
                continue
            seen.add(arc)
            zf.write(path, arc)


def main() -> None:
    args = parse_args()
    timestamp = args.timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = (args.out_dir or OUTPUT_ROOT / f"mve1_longer_history_data_audit_{timestamp}").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    logger = setup_logger(out_dir)
    logger.info("Starting MVE1 data audit. No v9, no training, no backtest, no MVE2.")

    sample_tickers = [normalize_ticker(x) for x in args.sample_download_tickers.split(",") if x.strip()][:5]
    ticker_universe = build_ticker_universe(args.ticker_list)
    updated_dirs = find_updated_data_dirs()
    logger.info("Ticker universe size=%s; updated_data dirs=%s", len(ticker_universe), len(updated_dirs))

    ticker_universe.to_csv(out_dir / "mve1_audit_ticker_universe.csv", index=False, encoding="utf-8-sig")

    dryrun = {
        "timestamp": timestamp,
        "ticker_count": len(ticker_universe),
        "v8_bounded_audit_exists": V8_BOUNDED_AUDIT.exists(),
        "v8_feature_cache_exists": V8_FEATURE_CACHE.exists(),
        "qlib_provider_exists": QLIB_PROVIDER.exists(),
        "updated_data_dir_count": len(updated_dirs),
        "local_only": bool(args.local_only),
        "allow_sample_download": bool(args.allow_sample_download),
        "sample_download_tickers": sample_tickers,
        "no_training": True,
        "no_backtest": True,
        "no_mve2": True,
    }
    save_json(dryrun, out_dir / "mve1_dryrun.json")
    if args.dry_run:
        logger.info("Dry-run complete. No coverage audit executed.")
        return

    tickers = ticker_universe["ticker"].tolist()
    inventory = source_inventory(tickers, updated_dirs, logger)
    coverage, loaded = price_coverage(ticker_universe, updated_dirs, logger)
    adjustment = adjustment_sanity(loaded, ["AAPL", "NVDA", "TSLA", "MSTR", "QQQ", "TQQQ"])
    features = feature_build_readiness(ticker_universe, coverage, loaded)
    layers = layer_readiness(ticker_universe, coverage, features)
    download = yfinance_download_feasibility(sample_tickers, bool(args.allow_sample_download and not args.local_only), logger)
    rec = recommendation(coverage, layers, download)

    inventory.to_csv(out_dir / "mve1_local_data_source_inventory.csv", index=False, encoding="utf-8-sig")
    download.to_csv(out_dir / "mve1_data_download_feasibility.csv", index=False, encoding="utf-8-sig")
    coverage.to_csv(out_dir / "mve1_price_data_coverage.csv", index=False, encoding="utf-8-sig")
    adjustment.to_csv(out_dir / "mve1_adjustment_sanity_check.csv", index=False, encoding="utf-8-sig")
    features.to_csv(out_dir / "mve1_feature_build_readiness.csv", index=False, encoding="utf-8-sig")
    layers.to_csv(out_dir / "mve1_universe_layer_readiness.csv", index=False, encoding="utf-8-sig")
    save_json(rec, out_dir / "mve1_recommendation.json")

    zip_path = OUTPUT_ROOT / f"us_stock_selection_quant_lab_mve1_longer_history_data_audit_{timestamp}.zip"
    docs = write_docs(timestamp, out_dir, zip_path, ticker_universe, inventory, download, coverage, adjustment, features, layers, rec)
    update_next_steps(out_dir, zip_path, rec, coverage, layers)
    write_run_summary(out_dir, zip_path, rec)
    write_workbook(
        out_dir,
        timestamp,
        {
            "ticker_universe": ticker_universe,
            "local_inventory": inventory,
            "download_feasibility": download,
            "price_coverage": coverage,
            "adjustment": adjustment,
            "feature_readiness": features,
            "layer_readiness": layers,
        },
    )
    package(out_dir, docs, zip_path)
    sync_index = sync_meistock(timestamp, out_dir, zip_path, docs)
    sync_index.to_csv(out_dir / "mve1_meistock_sync_index.csv", index=False, encoding="utf-8-sig")
    package(out_dir, docs, zip_path)
    if MEISTOCK_ROOT.exists() and zip_path.exists():
        shutil.copy2(zip_path, MEISTOCK_ROOT / "07_附件索引" / zip_path.name)
    logger.info("Packaged MVE1 data audit zip: %s", zip_path)


if __name__ == "__main__":
    main()
