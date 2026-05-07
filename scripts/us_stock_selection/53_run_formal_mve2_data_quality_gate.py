from __future__ import annotations

import json
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "us_stock_selection"
STORE_DIR = PROJECT_ROOT / "data" / "unified_ohlcv" / "us_stock_selection"
PRICES_DIR = STORE_DIR / "prices"
AUDIT_DIR = STORE_DIR / "audit"
SEARCH_RUN_ID = "limited_mve2_20260502_142702"
VALIDATION_RUN_ID = "limited_mve2_validation_20260502_183555"
SEARCH_DIR = OUTPUT_ROOT / SEARCH_RUN_ID
VALIDATION_DIR = OUTPUT_ROOT / VALIDATION_RUN_ID
SCRIPT_PATH = Path("scripts/us_stock_selection/53_run_formal_mve2_data_quality_gate.py")
REQUIRED_FIELDS = ["date", "ticker", "adj_close", "volume"]
OPTIONAL_FIELDS = ["open", "high", "low", "close"]
JUMP_THRESHOLD = 0.50
LOW_VOLUME_THRESHOLD = 100_000


def rel(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def git_head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        text=True,
    ).strip()


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def clean_str(value: Any) -> str:
    if value is None:
        return "NA"
    if isinstance(value, float) and np.isnan(value):
        return "NA"
    return str(value)


def max_true_run(values: pd.Series) -> int:
    longest = 0
    current = 0
    for value in values.fillna(False).astype(bool).tolist():
        if value:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return int(longest)


def file_row(path: Path, role: str) -> dict[str, Any]:
    if not path.exists():
        return {
            "path": rel(path),
            "role": role,
            "exists": False,
            "size_bytes": 0,
            "mtime": "NA",
        }
    stat = path.stat()
    return {
        "path": rel(path),
        "role": role,
        "exists": True,
        "size_bytes": int(stat.st_size),
        "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
    }


def build_input_inventory() -> pd.DataFrame:
    paths: list[tuple[Path, str]] = [
        (STORE_DIR, "audited store root"),
        (PRICES_DIR, "price parquet directory"),
        (AUDIT_DIR, "store audit directory"),
        (SEARCH_DIR / "limited_mve2_run_config.json", "limited search config"),
        (SEARCH_DIR / "eligible_universe_limited_mve2.csv", "eligible universe"),
        (SEARCH_DIR / "excluded_tickers_limited_mve2.csv", "excluded universe"),
        (VALIDATION_DIR / "manifest.json", "validation pack manifest"),
        (VALIDATION_DIR / "key_metrics_summary.csv", "validation key metrics"),
        (VALIDATION_DIR / "selected_report.md", "validation selected report"),
    ]
    if PRICES_DIR.exists():
        for path in sorted(PRICES_DIR.glob("*.parquet")):
            paths.append((path, "price parquet"))
    if AUDIT_DIR.exists():
        for path in sorted(AUDIT_DIR.glob("*.csv")):
            paths.append((path, "store audit csv"))
    return pd.DataFrame([file_row(path, role) for path, role in paths])


def load_price_summaries() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    coverage_rows: list[dict[str, Any]] = []
    missing_rows: list[dict[str, Any]] = []
    liquidity_rows: list[dict[str, Any]] = []
    anomaly_rows: list[dict[str, Any]] = []

    price_files = sorted(PRICES_DIR.glob("*.parquet")) if PRICES_DIR.exists() else []
    for path in price_files:
        ticker = path.stem
        try:
            df = pd.read_parquet(path)
        except Exception as exc:
            coverage_rows.append(
                {
                    "ticker": ticker,
                    "price_file": rel(path),
                    "readable": False,
                    "read_error": type(exc).__name__,
                    "rows": 0,
                    "first_date": "NA",
                    "last_date": "NA",
                    "columns": "NA",
                    "has_date": False,
                    "has_ticker": False,
                    "has_adj_close": False,
                    "has_volume": False,
                }
            )
            continue

        columns = list(df.columns)
        has = {field: field in columns for field in REQUIRED_FIELDS + OPTIONAL_FIELDS}
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
        else:
            df["date"] = pd.NaT
        if "ticker" not in df.columns:
            df["ticker"] = ticker
        df = df.sort_values("date")
        rows = int(len(df))
        duplicate_pairs = int(df.duplicated(subset=["date", "ticker"]).sum()) if rows else 0
        first_date = df["date"].min()
        last_date = df["date"].max()
        adj_close = pd.to_numeric(df["adj_close"], errors="coerce") if "adj_close" in df.columns else pd.Series(dtype=float)
        volume = pd.to_numeric(df["volume"], errors="coerce") if "volume" in df.columns else pd.Series(dtype=float)
        returns = adj_close.pct_change()
        jump_mask = returns.abs() > JUMP_THRESHOLD
        zero_or_missing_volume = volume.isna() | (volume <= 0)
        low_volume = volume.notna() & (volume > 0) & (volume < LOW_VOLUME_THRESHOLD)

        coverage_rows.append(
            {
                "ticker": ticker,
                "price_file": rel(path),
                "readable": True,
                "read_error": "NA",
                "rows": rows,
                "first_date": first_date.date().isoformat() if pd.notna(first_date) else "NA",
                "last_date": last_date.date().isoformat() if pd.notna(last_date) else "NA",
                "columns": ";".join(columns),
                "has_date": has["date"],
                "has_ticker": has["ticker"],
                "has_adj_close": has["adj_close"],
                "has_volume": has["volume"],
                "has_open": has["open"],
                "has_high": has["high"],
                "has_low": has["low"],
                "has_close": has["close"],
                "duplicate_date_ticker_count": duplicate_pairs,
            }
        )
        missing_rows.append(
            {
                "ticker": ticker,
                "rows": rows,
                "adj_close_missing_count": int(adj_close.isna().sum()) if rows else 0,
                "adj_close_missing_rate": float(adj_close.isna().mean()) if rows else 1.0,
                "volume_missing_count": int(volume.isna().sum()) if rows else 0,
                "volume_missing_rate": float(volume.isna().mean()) if rows else 1.0,
                "non_positive_adj_close_count": int((adj_close <= 0).sum()) if rows else 0,
                "non_positive_volume_count": int((volume <= 0).sum()) if rows else 0,
            }
        )
        liquidity_rows.append(
            {
                "ticker": ticker,
                "rows": rows,
                "volume_available_rate": float((volume.notna() & (volume > 0)).mean()) if rows else 0.0,
                "zero_or_missing_volume_count": int(zero_or_missing_volume.sum()) if rows else 0,
                "max_zero_or_missing_volume_run": max_true_run(zero_or_missing_volume) if rows else 0,
                "low_volume_count_lt_100k": int(low_volume.sum()) if rows else 0,
                "low_volume_rate_lt_100k": float(low_volume.mean()) if rows else 0.0,
                "median_volume": float(volume.median()) if rows and volume.notna().any() else np.nan,
            }
        )
        anomaly_rows.append(
            {
                "ticker": ticker,
                "rows": rows,
                "duplicate_date_ticker_count": duplicate_pairs,
                "non_positive_price_count": int((adj_close <= 0).sum()) if rows else 0,
                "jump_abs_gt_50pct_count": int(jump_mask.sum()) if rows else 0,
                "max_abs_daily_return": float(returns.abs().max()) if rows and returns.notna().any() else np.nan,
            }
        )

    return (
        pd.DataFrame(coverage_rows),
        pd.DataFrame(missing_rows),
        pd.DataFrame(liquidity_rows),
        pd.DataFrame(anomaly_rows),
    )


def build_field_coverage(date_coverage: pd.DataFrame) -> pd.DataFrame:
    rows = []
    ticker_count = int(len(date_coverage))
    for field in REQUIRED_FIELDS + OPTIONAL_FIELDS:
        column = f"has_{field}"
        present = int(date_coverage[column].sum()) if column in date_coverage.columns and ticker_count else 0
        rows.append(
            {
                "field": field,
                "required_for_p2a": field in REQUIRED_FIELDS,
                "present_ticker_count": present,
                "missing_ticker_count": ticker_count - present,
                "present_rate": present / ticker_count if ticker_count else 0.0,
            }
        )
    return pd.DataFrame(rows)


def build_universe_tables(date_coverage: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    eligible = read_csv(SEARCH_DIR / "eligible_universe_limited_mve2.csv")
    excluded = read_csv(SEARCH_DIR / "excluded_tickers_limited_mve2.csv")
    validation = read_csv(VALIDATION_DIR / "validation_decision_summary.csv")

    eligible_tickers = set(eligible["ticker"].astype(str)) if "ticker" in eligible.columns else set()
    excluded_tickers = set(excluded["ticker"].astype(str)) if "ticker" in excluded.columns else set()
    search_universe = eligible_tickers | excluded_tickers
    price_tickers = set(date_coverage["ticker"].astype(str)) if "ticker" in date_coverage.columns else set()
    candidate_tickers = set(validation["ticker"].astype(str)) if "ticker" in validation.columns else set()

    universe_summary = pd.DataFrame(
        [
            {
                "metric": "eligible_ticker_count",
                "value": len(eligible_tickers),
                "evidence": rel(SEARCH_DIR / "eligible_universe_limited_mve2.csv"),
            },
            {
                "metric": "excluded_ticker_count",
                "value": len(excluded_tickers),
                "evidence": rel(SEARCH_DIR / "excluded_tickers_limited_mve2.csv"),
            },
            {
                "metric": "search_universe_count",
                "value": len(search_universe),
                "evidence": rel(SEARCH_DIR),
            },
            {
                "metric": "price_file_ticker_count",
                "value": len(price_tickers),
                "evidence": rel(PRICES_DIR),
            },
            {
                "metric": "validation_candidate_ticker_count",
                "value": len(candidate_tickers),
                "evidence": rel(VALIDATION_DIR / "validation_decision_summary.csv"),
            },
            {
                "metric": "universe_missing_price_count",
                "value": len(search_universe - price_tickers),
                "evidence": ";".join(sorted(search_universe - price_tickers)) if search_universe - price_tickers else "none",
            },
            {
                "metric": "price_not_in_search_universe_count",
                "value": len(price_tickers - search_universe),
                "evidence": ";".join(sorted(price_tickers - search_universe)) if price_tickers - search_universe else "none",
            },
            {
                "metric": "candidate_not_eligible_count",
                "value": len(candidate_tickers - eligible_tickers),
                "evidence": ";".join(sorted(candidate_tickers - eligible_tickers)) if candidate_tickers - eligible_tickers else "none",
            },
        ]
    )

    rows: list[dict[str, Any]] = []
    coverage_by_ticker = date_coverage.set_index("ticker").to_dict("index") if "ticker" in date_coverage.columns else {}
    for _, row in eligible.iterrows():
        ticker = str(row.get("ticker", "NA"))
        coverage = coverage_by_ticker.get(ticker, {})
        rows.append(
            {
                "ticker": ticker,
                "universe_status": "eligible",
                "layer": clean_str(row.get("layer")),
                "bucket": clean_str(row.get("bucket")),
                "reason": clean_str(row.get("eligibility_reason")),
                "price_file_exists": bool(coverage),
                "rows": coverage.get("rows", 0),
                "first_date": coverage.get("first_date", "NA"),
                "last_date": coverage.get("last_date", "NA"),
            }
        )
    for _, row in excluded.iterrows():
        ticker = str(row.get("ticker", "NA"))
        coverage = coverage_by_ticker.get(ticker, {})
        rows.append(
            {
                "ticker": ticker,
                "universe_status": "excluded",
                "layer": clean_str(row.get("layer")),
                "bucket": "NA",
                "reason": clean_str(row.get("exclusion_reason")),
                "price_file_exists": bool(coverage),
                "rows": coverage.get("rows", 0),
                "first_date": coverage.get("first_date", "NA"),
                "last_date": coverage.get("last_date", "NA"),
            }
        )
    return universe_summary, pd.DataFrame(rows)


def add_limited_window(date_coverage: pd.DataFrame, common_start: str, common_end: str) -> pd.DataFrame:
    if date_coverage.empty:
        return date_coverage
    start = pd.Timestamp(common_start)
    end = pd.Timestamp(common_end)
    result = date_coverage.copy()
    first = pd.to_datetime(result["first_date"], errors="coerce")
    last = pd.to_datetime(result["last_date"], errors="coerce")
    result["covers_limited_start"] = first <= start
    result["covers_limited_end"] = last >= end
    result["covers_limited_window"] = result["covers_limited_start"] & result["covers_limited_end"]
    return result


def audit_metadata_conflicts(date_coverage: pd.DataFrame) -> pd.DataFrame:
    audit = read_csv(AUDIT_DIR / "price_quality_audit.csv")
    if audit.empty or date_coverage.empty or "ticker" not in audit.columns:
        return pd.DataFrame(columns=["ticker", "price_rows", "audit_n_rows", "audit_download_success", "conflict"])
    rows_by_ticker = date_coverage.set_index("ticker")["rows"].to_dict()
    rows = []
    for _, row in audit.iterrows():
        ticker = str(row.get("ticker", "NA"))
        price_rows = int(rows_by_ticker.get(ticker, 0))
        audit_rows = int(pd.to_numeric(row.get("n_rows", 0), errors="coerce") or 0)
        download_success = str(row.get("download_success", "")).lower() == "true"
        conflict = price_rows > 0 and (audit_rows == 0 or not download_success)
        if conflict:
            rows.append(
                {
                    "ticker": ticker,
                    "price_rows": price_rows,
                    "audit_n_rows": audit_rows,
                    "audit_download_success": download_success,
                    "conflict": True,
                }
            )
    return pd.DataFrame(rows)


def risk_row(flag: str, severity: str, status: str, affected_count: int, detail: str, evidence: str) -> dict[str, Any]:
    return {
        "flag_id": flag,
        "severity": severity,
        "status": status,
        "affected_count": int(affected_count),
        "detail": detail,
        "evidence_file": evidence,
    }


def build_risk_flags(
    input_inventory: pd.DataFrame,
    field_coverage: pd.DataFrame,
    universe_summary: pd.DataFrame,
    date_coverage: pd.DataFrame,
    missingness: pd.DataFrame,
    liquidity: pd.DataFrame,
    anomalies: pd.DataFrame,
    conflicts: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    price_files = input_inventory[input_inventory["role"] == "price parquet"]
    missing_required = int(field_coverage[(field_coverage["required_for_p2a"]) & (field_coverage["missing_ticker_count"] > 0)]["missing_ticker_count"].sum()) if not field_coverage.empty else 1
    universe_missing_price = int(universe_summary.loc[universe_summary["metric"] == "universe_missing_price_count", "value"].iloc[0]) if not universe_summary.empty else 1
    price_not_in_universe = int(universe_summary.loc[universe_summary["metric"] == "price_not_in_search_universe_count", "value"].iloc[0]) if not universe_summary.empty else 0
    candidate_not_eligible = int(universe_summary.loc[universe_summary["metric"] == "candidate_not_eligible_count", "value"].iloc[0]) if not universe_summary.empty else 1
    short_eligible = 0
    if "universe_status" in date_coverage.columns and "covers_limited_window" in date_coverage.columns:
        short_eligible = int(((date_coverage["universe_status"] == "eligible") & (~date_coverage["covers_limited_window"])).sum())

    rows.append(risk_row("audited_store_present", "critical", "PASS" if STORE_DIR.exists() and PRICES_DIR.exists() else "FAIL", 0 if STORE_DIR.exists() and PRICES_DIR.exists() else 1, "Audited unified adjusted OHLCV store root and price directory checked.", rel(STORE_DIR)))
    rows.append(risk_row("price_parquet_present", "critical", "PASS" if len(price_files) > 0 else "FAIL", len(price_files), "Price parquet files are the only price input for this gate.", rel(PRICES_DIR)))
    rows.append(risk_row("required_fields_present", "critical", "PASS" if missing_required == 0 else "FAIL", missing_required, "Required fields are date, ticker, adj_close, volume.", rel(PRICES_DIR)))
    rows.append(risk_row("universe_price_alignment", "warning", "PASS" if universe_missing_price == 0 and price_not_in_universe == 0 else "WARN", universe_missing_price + price_not_in_universe, "Search universe and price files should align.", rel(SEARCH_DIR)))
    rows.append(risk_row("candidate_eligible_alignment", "critical", "PASS" if candidate_not_eligible == 0 else "FAIL", candidate_not_eligible, "Validation candidate tickers should remain inside the eligible universe.", rel(VALIDATION_DIR / "validation_decision_summary.csv")))
    rows.append(risk_row("eligible_limited_window_coverage", "warning", "PASS" if short_eligible == 0 else "WARN", short_eligible, "Eligible tickers should cover the limited MVE2 common window.", rel(SEARCH_DIR / "limited_mve2_run_config.json")))

    adj_missing = int((missingness["adj_close_missing_count"] > 0).sum()) if not missingness.empty else 1
    vol_missing = int((missingness["volume_missing_count"] > 0).sum()) if not missingness.empty else 1
    non_positive_price = int(missingness["non_positive_adj_close_count"].sum()) if not missingness.empty else 1
    non_positive_volume_tickers = int((missingness["non_positive_volume_count"] > 0).sum()) if not missingness.empty else 0
    duplicate_count = int(anomalies["duplicate_date_ticker_count"].sum()) if not anomalies.empty else 1
    jump_tickers = int((anomalies["jump_abs_gt_50pct_count"] > 0).sum()) if not anomalies.empty else 0
    zero_volume_runs = int((liquidity["max_zero_or_missing_volume_run"] >= 5).sum()) if not liquidity.empty else 0

    rows.append(risk_row("adj_close_missingness", "critical", "PASS" if adj_missing == 0 else "FAIL", adj_missing, "adj_close is a core field.", rel(PRICES_DIR)))
    rows.append(risk_row("volume_missingness", "warning", "PASS" if vol_missing == 0 else "WARN", vol_missing, "volume is a core field.", rel(PRICES_DIR)))
    rows.append(risk_row("non_positive_adj_close", "critical", "PASS" if non_positive_price == 0 else "FAIL", non_positive_price, "Non-positive adjusted prices are not acceptable for formal design.", rel(PRICES_DIR)))
    rows.append(risk_row("non_positive_volume", "warning", "PASS" if non_positive_volume_tickers == 0 else "WARN", non_positive_volume_tickers, "Non-positive volume is a liquidity quality warning.", rel(PRICES_DIR)))
    rows.append(risk_row("duplicate_date_ticker", "critical", "PASS" if duplicate_count == 0 else "FAIL", duplicate_count, "Duplicate date-ticker rows are not acceptable.", rel(PRICES_DIR)))
    rows.append(risk_row("large_daily_price_jump", "warning", "PASS" if jump_tickers == 0 else "WARN", jump_tickers, f"Daily adjusted-return absolute jump threshold is {JUMP_THRESHOLD:.0%}.", rel(PRICES_DIR)))
    rows.append(risk_row("long_zero_or_missing_volume_run", "warning", "PASS" if zero_volume_runs == 0 else "WARN", zero_volume_runs, "Flags tickers with at least five consecutive zero or missing volume rows.", rel(PRICES_DIR)))
    rows.append(risk_row("audit_metadata_conflict", "warning", "PASS" if len(conflicts) == 0 else "WARN", len(conflicts), "Audit CSV rows disagree with readable price parquet rows.", rel(AUDIT_DIR / "price_quality_audit.csv")))
    rows.append(risk_row("evidence_chain_exclusion", "critical", "PASS", 0, "The gate uses only audited store plus limited MVE2 outputs; formal v9 and v8.2 baseline outputs are excluded.", rel(VALIDATION_DIR / "manifest.json")))
    return pd.DataFrame(rows)


def merge_universe_status(date_coverage: pd.DataFrame, eligible_excluded: pd.DataFrame) -> pd.DataFrame:
    if date_coverage.empty:
        return date_coverage
    status = eligible_excluded[["ticker", "universe_status"]].drop_duplicates() if not eligible_excluded.empty else pd.DataFrame(columns=["ticker", "universe_status"])
    result = date_coverage.merge(status, on="ticker", how="left")
    result["universe_status"] = result["universe_status"].fillna("not_in_search_universe")
    return result


def decision_from_risks(risk_flags: pd.DataFrame) -> tuple[str, list[str], bool]:
    critical_fail = risk_flags[(risk_flags["severity"] == "critical") & (risk_flags["status"] == "FAIL")]
    warnings = risk_flags[risk_flags["status"] == "WARN"]
    if not critical_fail.empty:
        reasons = [f"{row.flag_id}: {row.detail}" for row in critical_fail.itertuples()]
        return "FAIL_DATA_GATE", reasons, False
    if not warnings.empty:
        reasons = [f"{row.flag_id}: {row.affected_count} affected" for row in warnings.itertuples()]
        return "CONDITIONAL_NEEDS_REVIEW", reasons, False
    return "PASS_TO_FORMAL_MVE2_DESIGN", ["No critical failures or warnings in this light gate."], True


def gate_summary_rows(decision: str, risk_flags: pd.DataFrame) -> pd.DataFrame:
    critical_fail_count = int(((risk_flags["severity"] == "critical") & (risk_flags["status"] == "FAIL")).sum())
    warning_count = int((risk_flags["status"] == "WARN").sum())
    rows = [
        {"check": "data_source_unique", "status": "PASS", "detail": "Only audited unified adjusted OHLCV store plus limited MVE2 outputs are used."},
        {"check": "required_fields", "status": "PASS" if critical_fail_count == 0 else "FAIL", "detail": "date, ticker, adj_close, volume checked."},
        {"check": "universe_reproducibility", "status": "PASS" if not (risk_flags["flag_id"] == "universe_price_alignment").any() else "SEE_RISK_FLAGS", "detail": "Eligible and excluded CSV files are present and summarized."},
        {"check": "risk_flag_count", "status": "INFO", "detail": f"critical_fail={critical_fail_count}; warnings={warning_count}"},
        {"check": "readiness_decision", "status": decision, "detail": "P2-A gate decision."},
        {"check": "direct_v10", "status": "FORBIDDEN", "detail": "This gate does not authorize v10."},
    ]
    return pd.DataFrame(rows)


def markdown_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_No rows._"
    display = df.copy().astype(str)
    columns = list(display.columns)
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join(["---"] * len(columns)) + " |"
    body = ["| " + " | ".join(row[column].replace("|", "/") for column in columns) + " |" for _, row in display.iterrows()]
    return "\n".join([header, separator, *body])


def write_report(
    out_dir: Path,
    run_id: str,
    decision: str,
    can_enter_p3: bool,
    universe_summary: pd.DataFrame,
    field_coverage: pd.DataFrame,
    date_coverage: pd.DataFrame,
    missingness: pd.DataFrame,
    liquidity: pd.DataFrame,
    anomalies: pd.DataFrame,
    risk_flags: pd.DataFrame,
) -> None:
    eligible_count = int(universe_summary.loc[universe_summary["metric"] == "eligible_ticker_count", "value"].iloc[0])
    excluded_count = int(universe_summary.loc[universe_summary["metric"] == "excluded_ticker_count", "value"].iloc[0])
    price_count = int(universe_summary.loc[universe_summary["metric"] == "price_file_ticker_count", "value"].iloc[0])
    common_start = date_coverage["first_date"].max() if not date_coverage.empty else "NA"
    common_end = date_coverage["last_date"].min() if not date_coverage.empty else "NA"
    adj_missing_tickers = int((missingness["adj_close_missing_count"] > 0).sum()) if not missingness.empty else 0
    volume_missing_tickers = int((missingness["volume_missing_count"] > 0).sum()) if not missingness.empty else 0
    jump_tickers = int((anomalies["jump_abs_gt_50pct_count"] > 0).sum()) if not anomalies.empty else 0
    long_zero_volume = int((liquidity["max_zero_or_missing_volume_run"] >= 5).sum()) if not liquidity.empty else 0
    warning_rows = risk_flags[risk_flags["status"] == "WARN"]

    report = f"""# Formal MVE2 Data Quality Gate P2-A

Run id: `{run_id}`

## Executive Summary

- Readiness decision: `{decision}`
- Can enter P3 formal MVE2 search design: `{str(can_enter_p3).lower()}`
- Direct v10 remains forbidden.
- No strategy search, model training, formal MVE2, or v10 execution was performed.
- group4 hold artifacts were not touched.

## Input Data Source

- Store: `data/unified_ohlcv/us_stock_selection`
- Price files: `{price_count}`
- Source universe run: `{SEARCH_RUN_ID}`
- Validation pack: `{VALIDATION_RUN_ID}`
- Excluded evidence chains: old qlib, old v8 cache, formal v9 outputs, v8.2 formal baseline outputs.

## Universe

- Eligible tickers: `{eligible_count}`
- Excluded tickers: `{excluded_count}`
- Universe and eligibility evidence is read from the limited MVE2 search run.
- Candidate decisions from the validation pack are used only for alignment checks.

## Field Coverage

Core fields are `date`, `ticker`, `adj_close`, and `volume`.

{markdown_table(field_coverage)}

## Time Coverage

- Global common first available date across price files: `{common_start}`
- Global common last available date across price files: `{common_end}`
- Per-ticker detail is in `date_coverage_summary.csv`.

## Missingness And Anomalies

- Tickers with adj_close missing rows: `{adj_missing_tickers}`
- Tickers with volume missing rows: `{volume_missing_tickers}`
- Tickers with daily adjusted-return absolute jump above `{JUMP_THRESHOLD:.0%}`: `{jump_tickers}`
- Tickers with at least five consecutive zero or missing volume rows: `{long_zero_volume}`

## Liquidity

`volume` is checked as a quality and liquidity field. Low-volume and zero-volume indicators are warnings only and are not investment conclusions.

## Risk Flags

{markdown_table(risk_flags)}

## Decision Rationale

The gate is conservative. Any critical failure produces `FAIL_DATA_GATE`; any warning produces `CONDITIONAL_NEEDS_REVIEW`; a clean run produces `PASS_TO_FORMAL_MVE2_DESIGN`.

## Allowed Next Actions

- If decision is `PASS_TO_FORMAL_MVE2_DESIGN`, design P3 only after human review.
- If decision is `CONDITIONAL_NEEDS_REVIEW`, resolve or explicitly accept the listed warnings before P3.
- If decision is `FAIL_DATA_GATE`, repair the data evidence chain first.

## Forbidden Actions

- Do not treat limited MVE2 as a formal baseline.
- Do not treat formal v9 as a baseline.
- Do not start v10 from this gate.
- Do not mix this audited-store line with v8.2 or formal v9 evidence chains.
- Do not release group4 hold inside this task.
"""
    (out_dir / "data_quality_gate_report.md").write_text(report, encoding="utf-8")

    readme = f"""# Formal MVE2 Data Quality Gate P2-A

This directory contains a lightweight data quality gate for deciding whether the audited unified adjusted OHLCV store is ready to support formal MVE2 design.

Run id: `{run_id}`

Decision: `{decision}`

The gate reads only:

- `data/unified_ohlcv/us_stock_selection`
- `outputs/us_stock_selection/{SEARCH_RUN_ID}`
- `outputs/us_stock_selection/{VALIDATION_RUN_ID}`

It does not run strategy search, train a model, start formal MVE2, start v10, or alter existing candidate decisions.

Review order:

1. `data_quality_gate_report.md`
2. `formal_mve2_readiness_decision.json`
3. `risk_flags.csv`
4. `gate_summary.csv`
5. Coverage and anomaly CSV files
6. `small_tables/`

The current formal baseline remains v8.2 frozen Pool A `top5_ytdcap80p_derisk100p`. formal v9 remains a failed branch.
"""
    (out_dir / "README.md").write_text(readme, encoding="utf-8")


def write_zip(out_dir: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(out_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(out_dir.parent).as_posix())


def main() -> None:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_id = f"formal_mve2_data_quality_gate_{timestamp}"
    out_dir = OUTPUT_ROOT / run_id
    small_tables_dir = out_dir / "small_tables"
    out_dir.mkdir(parents=True, exist_ok=False)
    small_tables_dir.mkdir(parents=True, exist_ok=True)

    head = git_head()
    config = json.loads((SEARCH_DIR / "limited_mve2_run_config.json").read_text(encoding="utf-8")) if (SEARCH_DIR / "limited_mve2_run_config.json").exists() else {}
    common_start = config.get("common_start", "2016-01-01")
    common_end = config.get("common_end", "2026-05-01")

    input_inventory = build_input_inventory()
    date_coverage, missingness, liquidity, anomalies = load_price_summaries()
    field_coverage = build_field_coverage(date_coverage)
    universe_summary, eligible_excluded = build_universe_tables(date_coverage)
    date_coverage = merge_universe_status(date_coverage, eligible_excluded)
    date_coverage = add_limited_window(date_coverage, common_start, common_end)
    conflicts = audit_metadata_conflicts(date_coverage)
    risk_flags = build_risk_flags(
        input_inventory,
        field_coverage,
        universe_summary,
        date_coverage,
        missingness,
        liquidity,
        anomalies,
        conflicts,
    )
    decision, reasons, can_enter_p3 = decision_from_risks(risk_flags)
    gate_summary = gate_summary_rows(decision, risk_flags)

    input_inventory.to_csv(small_tables_dir / "input_file_inventory.csv", index=False)
    conflicts.to_csv(small_tables_dir / "audit_metadata_conflicts.csv", index=False)
    date_coverage[["ticker", "universe_status", "rows", "first_date", "last_date", "covers_limited_window"]].to_csv(small_tables_dir / "ticker_gate_matrix.csv", index=False)
    field_coverage.to_csv(small_tables_dir / "field_presence_matrix.csv", index=False)

    gate_summary.to_csv(out_dir / "gate_summary.csv", index=False)
    universe_summary.to_csv(out_dir / "universe_summary.csv", index=False)
    eligible_excluded.to_csv(out_dir / "eligible_excluded_summary.csv", index=False)
    field_coverage.to_csv(out_dir / "field_coverage_summary.csv", index=False)
    date_coverage.to_csv(out_dir / "date_coverage_summary.csv", index=False)
    missingness.to_csv(out_dir / "missingness_summary.csv", index=False)
    liquidity.to_csv(out_dir / "volume_liquidity_summary.csv", index=False)
    anomalies.to_csv(out_dir / "price_anomaly_summary.csv", index=False)
    risk_flags.to_csv(out_dir / "risk_flags.csv", index=False)

    reproducibility = pd.DataFrame(
        [
            {"item": "script_path", "status": "PASS", "value": SCRIPT_PATH.as_posix()},
            {"item": "git_commit", "status": "PASS", "value": head},
            {"item": "store_dir", "status": "PASS" if STORE_DIR.exists() else "FAIL", "value": rel(STORE_DIR)},
            {"item": "search_run_dir", "status": "PASS" if SEARCH_DIR.exists() else "FAIL", "value": rel(SEARCH_DIR)},
            {"item": "validation_pack_dir", "status": "PASS" if VALIDATION_DIR.exists() else "FAIL", "value": rel(VALIDATION_DIR)},
            {"item": "output_dir", "status": "PASS", "value": rel(out_dir)},
            {"item": "group4_hold_not_touched", "status": "PASS", "value": "true"},
            {"item": "strategy_search_executed", "status": "PASS", "value": "false"},
            {"item": "model_training_executed", "status": "PASS", "value": "false"},
            {"item": "formal_mve2_executed", "status": "PASS", "value": "false"},
            {"item": "v10_executed", "status": "PASS", "value": "false"},
        ]
    )
    reproducibility.to_csv(out_dir / "reproducibility_checklist.csv", index=False)

    readiness = {
        "run_id": run_id,
        "readiness_decision": decision,
        "can_enter_p3_formal_mve2_search_design": can_enter_p3,
        "direct_v10_allowed": False,
        "reasons": reasons,
        "group4_hold_not_touched": True,
        "strategy_search_executed": False,
        "model_training_executed": False,
        "formal_mve2_executed": False,
        "v10_executed": False,
    }
    (out_dir / "formal_mve2_readiness_decision.json").write_text(
        json.dumps(readiness, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    write_report(
        out_dir,
        run_id,
        decision,
        can_enter_p3,
        universe_summary,
        field_coverage,
        date_coverage,
        missingness,
        liquidity,
        anomalies,
        risk_flags,
    )

    generated_files = [
        rel(out_dir / "README.md"),
        rel(out_dir / "manifest.json"),
        rel(out_dir / "data_quality_gate_report.md"),
        rel(out_dir / "gate_summary.csv"),
        rel(out_dir / "universe_summary.csv"),
        rel(out_dir / "eligible_excluded_summary.csv"),
        rel(out_dir / "field_coverage_summary.csv"),
        rel(out_dir / "date_coverage_summary.csv"),
        rel(out_dir / "missingness_summary.csv"),
        rel(out_dir / "volume_liquidity_summary.csv"),
        rel(out_dir / "price_anomaly_summary.csv"),
        rel(out_dir / "reproducibility_checklist.csv"),
        rel(out_dir / "risk_flags.csv"),
        rel(out_dir / "formal_mve2_readiness_decision.json"),
        rel(small_tables_dir / "input_file_inventory.csv"),
        rel(small_tables_dir / "audit_metadata_conflicts.csv"),
        rel(small_tables_dir / "ticker_gate_matrix.csv"),
        rel(small_tables_dir / "field_presence_matrix.csv"),
    ]
    manifest = {
        "run_id": run_id,
        "run_type": "formal_mve2_data_quality_gate",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "git_commit": head,
        "script_path": SCRIPT_PATH.as_posix(),
        "input_paths": [rel(STORE_DIR), rel(SEARCH_DIR), rel(VALIDATION_DIR)],
        "output_dir": rel(out_dir),
        "generated_files": generated_files,
        "data_source_policy": "audited unified adjusted OHLCV store only",
        "fields_required": REQUIRED_FIELDS,
        "fields_optional": OPTIONAL_FIELDS,
        "jump_threshold_abs_return": JUMP_THRESHOLD,
        "low_volume_threshold": LOW_VOLUME_THRESHOLD,
        "explicit_exclusions": ["old qlib", "old v8 cache", "formal v9 output", "v8.2 formal baseline output"],
        "readiness_decision": decision,
        "can_enter_p3_formal_mve2_search_design": can_enter_p3,
        "direct_v10_allowed": False,
        "group4_hold_not_touched": True,
        "strategy_search_executed": False,
        "model_training_executed": False,
        "formal_mve2_executed": False,
        "v10_executed": False,
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    zip_path = OUTPUT_ROOT / f"{run_id}.zip"
    write_zip(out_dir, zip_path)

    print(
        json.dumps(
            {
                "run_id": run_id,
                "output_dir": rel(out_dir),
                "zip_path": rel(zip_path),
                "zip_size_bytes": zip_path.stat().st_size,
                "readiness_decision": decision,
                "can_enter_p3_formal_mve2_search_design": can_enter_p3,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
