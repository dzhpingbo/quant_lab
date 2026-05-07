from __future__ import annotations

import json
import subprocess
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "us_stock_selection"
STORE_DIR = PROJECT_ROOT / "data" / "unified_ohlcv" / "us_stock_selection"
PRICES_DIR = STORE_DIR / "prices"
ACTIONS_DIR = STORE_DIR / "actions"
P2A_RUN_ID = "formal_mve2_data_quality_gate_20260507_142224"
P2A_DIR = OUTPUT_ROOT / P2A_RUN_ID
SEARCH_RUN_ID = "limited_mve2_20260502_142702"
SEARCH_DIR = OUTPUT_ROOT / SEARCH_RUN_ID
VALIDATION_RUN_ID = "limited_mve2_validation_20260502_183555"
VALIDATION_DIR = OUTPUT_ROOT / VALIDATION_RUN_ID
SCRIPT_PATH = Path("scripts/us_stock_selection/54_review_formal_mve2_gate_exceptions.py")
JUMP_THRESHOLD = 0.50


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


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def clean(value: Any) -> str:
    if value is None:
        return "NA"
    if isinstance(value, float) and np.isnan(value):
        return "NA"
    return str(value)


def longest_true_run(values: pd.Series) -> int:
    longest = 0
    current = 0
    for value in values.fillna(False).astype(bool).tolist():
        if value:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return int(longest)


def load_price(ticker: str) -> pd.DataFrame:
    path = PRICES_DIR / f"{ticker}.parquet"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(path)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["adj_close"] = pd.to_numeric(df["adj_close"], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
    return df.sort_values("date").reset_index(drop=True)


def load_actions(ticker: str) -> pd.DataFrame:
    path = ACTIONS_DIR / f"{ticker}_actions.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for column in ["dividends", "stock_splits"]:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0.0)
    return df


def universe_maps() -> tuple[dict[str, str], set[str], set[str]]:
    eligible = read_csv(SEARCH_DIR / "eligible_universe_limited_mve2.csv")
    excluded = read_csv(SEARCH_DIR / "excluded_tickers_limited_mve2.csv")
    validation = read_csv(VALIDATION_DIR / "key_metrics_summary.csv")
    status: dict[str, str] = {}
    if "ticker" in eligible.columns:
        for ticker in eligible["ticker"].astype(str):
            status[ticker] = "eligible"
    if "ticker" in excluded.columns:
        for ticker in excluded["ticker"].astype(str):
            status[ticker] = "excluded"
    candidates = set(validation["ticker"].astype(str)) if "ticker" in validation.columns else set()
    eligible_set = {ticker for ticker, value in status.items() if value == "eligible"}
    return status, candidates, eligible_set


def volume_recommendation(eligible: bool, in_candidate: bool, rate: float, longest_run: int) -> tuple[str, str, bool]:
    if not eligible:
        return "OBSERVATION_ONLY", "Ticker is not eligible for formal MVE2 universe.", False
    if rate >= 0.01 or longest_run >= 5:
        return "NEED_DATA_VENDOR_REVIEW", "Volume issue is not isolated enough for direct formal design.", True
    if in_candidate:
        return "KEEP_WITH_FLAG", "Candidate ticker has only isolated non-positive volume rows.", False
    return "KEEP_WITH_FLAG", "Eligible ticker has isolated non-positive volume rows.", False


def build_volume_detail(status: dict[str, str], candidates: set[str]) -> pd.DataFrame:
    p2a_volume = read_csv(P2A_DIR / "volume_liquidity_summary.csv")
    tickers = []
    if "zero_or_missing_volume_count" in p2a_volume.columns:
        tickers = p2a_volume[pd.to_numeric(p2a_volume["zero_or_missing_volume_count"], errors="coerce").fillna(0) > 0]["ticker"].astype(str).tolist()
    rows: list[dict[str, Any]] = []
    for ticker in tickers:
        df = load_price(ticker)
        if df.empty:
            rows.append({"ticker": ticker, "recommendation": "NEED_DATA_VENDOR_REVIEW", "rationale": "Price file missing or unreadable."})
            continue
        volume = pd.to_numeric(df["volume"], errors="coerce")
        missing = volume.isna()
        zero = volume == 0
        negative = volume < 0
        non_positive = missing | zero | negative
        event_dates = df.loc[non_positive, "date"]
        rate = float(non_positive.mean()) if len(df) else 1.0
        longest = longest_true_run(non_positive)
        eligible = status.get(ticker) == "eligible"
        in_candidate = ticker in candidates
        recommendation, rationale, blocks = volume_recommendation(eligible, in_candidate, rate, longest)
        rows.append(
            {
                "ticker": ticker,
                "eligible_status": status.get(ticker, "not_in_search_universe"),
                "in_limited_mve2_candidate": in_candidate,
                "total_trading_days": int(len(df)),
                "volume_missing_count": int(missing.sum()),
                "volume_zero_count": int(zero.sum()),
                "volume_negative_count": int(negative.sum()),
                "non_positive_volume_count": int(non_positive.sum()),
                "non_positive_volume_rate": rate,
                "first_non_positive_volume_date": event_dates.min().date().isoformat() if not event_dates.empty else "NA",
                "last_non_positive_volume_date": event_dates.max().date().isoformat() if not event_dates.empty else "NA",
                "longest_non_positive_volume_run": longest,
                "median_volume": float(volume.median()) if volume.notna().any() else np.nan,
                "tradability_impact": "REVIEW_REQUIRED" if blocks else "LOW_FLAG_ONLY",
                "recommendation": recommendation,
                "rationale": rationale,
                "whether_blocks_p3": blocks,
            }
        )
    return pd.DataFrame(rows)


def action_evidence(ticker: str, jump_date: pd.Timestamp) -> tuple[bool, bool, bool, str]:
    actions = load_actions(ticker)
    if actions.empty or "date" not in actions.columns:
        return False, False, False, "none"
    start = jump_date - timedelta(days=5)
    end = jump_date + timedelta(days=5)
    nearby = actions[(actions["date"] >= start) & (actions["date"] <= end)].copy()
    if nearby.empty:
        return False, False, False, "none"
    has_split = bool((nearby.get("stock_splits", pd.Series(dtype=float)) > 0).any())
    has_dividend = bool((nearby.get("dividends", pd.Series(dtype=float)) != 0).any())
    detail = []
    for _, row in nearby.iterrows():
        detail.append(
            f"{row['date'].date().isoformat()}:dividend={clean(row.get('dividends'))}:split={clean(row.get('stock_splits'))}"
        )
    return True, has_split, has_dividend, ";".join(detail)


def price_recommendation(
    eligible: bool,
    in_candidate: bool,
    abs_return: float,
    has_action: bool,
    volume: float,
) -> tuple[str, str, bool, bool, bool]:
    suspected_data_issue = bool(has_action or volume <= 0 or np.isnan(volume))
    suspected_true_move = bool(not suspected_data_issue and abs_return <= 0.85)
    if not eligible:
        return "OBSERVATION_ONLY", "Ticker is not eligible for formal MVE2 universe.", False, suspected_true_move, suspected_data_issue
    if suspected_data_issue or abs_return > 0.85:
        return "NEED_DATA_VENDOR_REVIEW", "Large move needs price/action reconciliation before formal design.", True, suspected_true_move, True
    if in_candidate:
        return "KEEP_WITH_FLAG", "Candidate ticker has a large move that appears tradable but should remain flagged.", False, True, False
    return "KEEP_WITH_FLAG", "Eligible ticker has a large move that appears tradable but should remain flagged.", False, True, False


def build_price_jump_detail(status: dict[str, str], candidates: set[str]) -> pd.DataFrame:
    p2a_anomaly = read_csv(P2A_DIR / "price_anomaly_summary.csv")
    tickers = []
    if "jump_abs_gt_50pct_count" in p2a_anomaly.columns:
        tickers = p2a_anomaly[pd.to_numeric(p2a_anomaly["jump_abs_gt_50pct_count"], errors="coerce").fillna(0) > 0]["ticker"].astype(str).tolist()
    rows: list[dict[str, Any]] = []
    for ticker in tickers:
        df = load_price(ticker)
        if df.empty:
            rows.append({"ticker": ticker, "recommendation": "NEED_DATA_VENDOR_REVIEW", "rationale": "Price file missing or unreadable."})
            continue
        returns = df["adj_close"].pct_change()
        jump_idx = returns[returns.abs() > JUMP_THRESHOLD].index.tolist()
        for idx in jump_idx:
            row = df.loc[idx]
            prev = df.loc[idx - 1] if idx > 0 else None
            jump_date = row["date"]
            before = df.iloc[max(0, idx - 5):idx]
            after = df.iloc[idx + 1:min(len(df), idx + 6)]
            has_action, has_split, has_dividend, action_detail = action_evidence(ticker, jump_date)
            simple_return = float(returns.loc[idx])
            eligible = status.get(ticker) == "eligible"
            in_candidate = ticker in candidates
            recommendation, rationale, blocks, suspected_true, suspected_issue = price_recommendation(
                eligible,
                in_candidate,
                abs(simple_return),
                has_action,
                float(row["volume"]) if pd.notna(row["volume"]) else np.nan,
            )
            rows.append(
                {
                    "ticker": ticker,
                    "eligible_status": status.get(ticker, "not_in_search_universe"),
                    "in_limited_mve2_candidate": in_candidate,
                    "jump_date": jump_date.date().isoformat(),
                    "prev_adj_close": float(prev["adj_close"]) if prev is not None else np.nan,
                    "adj_close": float(row["adj_close"]),
                    "simple_return": simple_return,
                    "volume": float(row["volume"]) if pd.notna(row["volume"]) else np.nan,
                    "pre5_adj_close_min": float(before["adj_close"].min()) if not before.empty else np.nan,
                    "pre5_adj_close_max": float(before["adj_close"].max()) if not before.empty else np.nan,
                    "post5_adj_close_min": float(after["adj_close"].min()) if not after.empty else np.nan,
                    "post5_adj_close_max": float(after["adj_close"].max()) if not after.empty else np.nan,
                    "action_file_exists": (ACTIONS_DIR / f"{ticker}_actions.csv").exists(),
                    "action_nearby_plus_minus_5d": has_action,
                    "split_nearby_plus_minus_5d": has_split,
                    "dividend_nearby_plus_minus_5d": has_dividend,
                    "action_evidence": action_detail,
                    "suspected_real_volatility": suspected_true,
                    "suspected_data_anomaly": suspected_issue,
                    "affects_formal_mve2": blocks,
                    "recommendation": recommendation,
                    "rationale": rationale,
                    "whether_blocks_p3": blocks,
                }
            )
    return pd.DataFrame(rows)


def build_metadata_conflicts(current_head: str) -> pd.DataFrame:
    conflicts = read_csv(P2A_DIR / "small_tables" / "audit_metadata_conflicts.csv")
    p2a_manifest = read_json(P2A_DIR / "manifest.json")
    validation_manifest = read_json(VALIDATION_DIR / "manifest.json")
    rows: list[dict[str, Any]] = []
    for _, row in conflicts.iterrows():
        ticker = clean(row.get("ticker"))
        rows.append(
            {
                "conflict_type": "audit_csv_vs_price_parquet_row_count",
                "involved_file": rel(STORE_DIR / "audit" / "price_quality_audit.csv"),
                "ticker": ticker,
                "field_name": "n_rows;download_success",
                "observed_value": f"parquet_rows={clean(row.get('price_rows'))}; audit_rows={clean(row.get('audit_n_rows'))}; audit_success={clean(row.get('audit_download_success'))}",
                "expected_value": "audit rows and success should match readable parquet evidence",
                "severity": "WARNING",
                "affects_reproducibility": True,
                "affects_formal_mve2_gate": True,
                "recommended_fix": "Regenerate or reconcile store audit metadata before any formal MVE2 design.",
            }
        )
    if validation_manifest:
        rows.append(
            {
                "conflict_type": "pack_generation_commit_delta",
                "involved_file": rel(VALIDATION_DIR / "manifest.json"),
                "ticker": "ALL",
                "field_name": "git_commit",
                "observed_value": f"pack_generated_from_commit={clean(validation_manifest.get('git_commit'))}; pack_repository_commit={current_head}",
                "expected_value": "Difference is explainable when pack is generated before its repository commit.",
                "severity": "INFO",
                "affects_reproducibility": False,
                "affects_formal_mve2_gate": False,
                "recommended_fix": "Record as provenance context; no data repair implied.",
            }
        )
    if p2a_manifest:
        rows.append(
            {
                "conflict_type": "p2a_generation_commit_delta",
                "involved_file": rel(P2A_DIR / "manifest.json"),
                "ticker": "ALL",
                "field_name": "git_commit",
                "observed_value": f"source_git_commit={clean(p2a_manifest.get('git_commit'))}; repository_commit={current_head}",
                "expected_value": "Difference is explainable when P2-A output is generated before its repository commit.",
                "severity": "INFO",
                "affects_reproducibility": False,
                "affects_formal_mve2_gate": False,
                "recommended_fix": "Record as provenance context; no data repair implied.",
            }
        )
    return pd.DataFrame(rows)


def build_ticker_recommendations(
    status: dict[str, str],
    volume_detail: pd.DataFrame,
    price_jump_detail: pd.DataFrame,
    metadata_detail: pd.DataFrame,
) -> pd.DataFrame:
    price_tickers = sorted(path.stem for path in PRICES_DIR.glob("*.parquet")) if PRICES_DIR.exists() else []
    metadata_conflict_tickers = set(metadata_detail[metadata_detail["conflict_type"] == "audit_csv_vs_price_parquet_row_count"]["ticker"].astype(str)) if not metadata_detail.empty else set()
    volume_tickers = set(volume_detail["ticker"].astype(str)) if not volume_detail.empty else set()
    jump_tickers = set(price_jump_detail["ticker"].astype(str)) if not price_jump_detail.empty else set()
    rows: list[dict[str, Any]] = []
    for ticker in price_tickers:
        anomaly_types = []
        if ticker in volume_tickers:
            anomaly_types.append("non_positive_volume")
        if ticker in jump_tickers:
            anomaly_types.append("large_daily_price_jump")
        if ticker in metadata_conflict_tickers:
            anomaly_types.append("audit_metadata_conflict")
        subset_volume = volume_detail[volume_detail["ticker"] == ticker] if not volume_detail.empty else pd.DataFrame()
        subset_jump = price_jump_detail[price_jump_detail["ticker"] == ticker] if not price_jump_detail.empty else pd.DataFrame()
        blocks = bool(
            (not subset_volume.empty and subset_volume["whether_blocks_p3"].astype(bool).any())
            or (not subset_jump.empty and subset_jump["whether_blocks_p3"].astype(bool).any())
        )
        if blocks:
            recommendation = "NEED_DATA_VENDOR_REVIEW"
            severity = "BLOCKS_P3"
            rationale = "Ticker-level anomaly requires data review before P3."
        elif ticker in jump_tickers or ticker in volume_tickers:
            recommendation = "KEEP_WITH_FLAG" if status.get(ticker) == "eligible" else "OBSERVATION_ONLY"
            severity = "WARNING"
            rationale = "Ticker has isolated quality flags but no direct block after this review."
        elif ticker in metadata_conflict_tickers:
            recommendation = "KEEP_WITH_FLAG"
            severity = "METADATA_REVIEW"
            rationale = "Only audit metadata conflict is present; price parquet is readable."
        else:
            recommendation = "KEEP_WITH_FLAG"
            severity = "INFO"
            rationale = "No P2-B ticker-level exception."
        rows.append(
            {
                "ticker": ticker,
                "eligible_status": status.get(ticker, "not_in_search_universe"),
                "anomaly_types": ";".join(anomaly_types) if anomaly_types else "none",
                "severity": severity,
                "recommended_action": recommendation,
                "rationale": rationale,
                "whether_blocks_p3": blocks,
            }
        )
    return pd.DataFrame(rows)


def decide(
    volume_detail: pd.DataFrame,
    price_jump_detail: pd.DataFrame,
    metadata_detail: pd.DataFrame,
    missing_inputs: list[str],
) -> tuple[str, list[str], bool, bool]:
    if missing_inputs:
        return "FAIL_DO_NOT_PROCEED", [f"Missing required input: {item}" for item in missing_inputs], False, False
    vendor_review_count = 0
    if not volume_detail.empty:
        vendor_review_count += int((volume_detail["recommendation"] == "NEED_DATA_VENDOR_REVIEW").sum())
    if not price_jump_detail.empty:
        vendor_review_count += int((price_jump_detail["recommendation"] == "NEED_DATA_VENDOR_REVIEW").sum())
    metadata_warning_count = int((metadata_detail["severity"] == "WARNING").sum()) if not metadata_detail.empty else 0
    if vendor_review_count > 0 or metadata_warning_count > 0:
        reasons = [
            f"vendor_review_recommendations={vendor_review_count}",
            f"audit_metadata_warning_rows={metadata_warning_count}",
            "P3 remains blocked until exceptions are reviewed.",
        ]
        return "CONDITIONAL_NEEDS_DATA_REVIEW", reasons, False, False
    return "PASS_TO_P2C_GATE_RECHECK", ["Exceptions are non-blocking after P2-B review."], True, False


def risk_flags(decision: str, volume_detail: pd.DataFrame, price_jump_detail: pd.DataFrame, metadata_detail: pd.DataFrame) -> pd.DataFrame:
    rows = [
        {
            "flag_id": "non_positive_volume_review",
            "severity": "warning",
            "status": "PASS" if not volume_detail.empty and not volume_detail["whether_blocks_p3"].astype(bool).any() else "REVIEW",
            "affected_count": int(len(volume_detail)),
            "detail": "Non-positive volume exceptions were expanded to event-level ticker recommendations.",
        },
        {
            "flag_id": "price_jump_review",
            "severity": "warning",
            "status": "REVIEW" if not price_jump_detail.empty and price_jump_detail["whether_blocks_p3"].astype(bool).any() else "PASS",
            "affected_count": int(price_jump_detail["ticker"].nunique()) if not price_jump_detail.empty else 0,
            "detail": "Large adjusted-return jumps were checked against price windows and action files.",
        },
        {
            "flag_id": "metadata_conflict_review",
            "severity": "warning",
            "status": "REVIEW" if not metadata_detail.empty and (metadata_detail["severity"] == "WARNING").any() else "PASS",
            "affected_count": int((metadata_detail["severity"] == "WARNING").sum()) if not metadata_detail.empty else 0,
            "detail": "Audit metadata conflict appears separate from readable parquet data but still blocks P3.",
        },
        {
            "flag_id": "gate_exception_decision",
            "severity": "info",
            "status": decision,
            "affected_count": 0,
            "detail": "P2-B exception review decision.",
        },
    ]
    return pd.DataFrame(rows)


def markdown_table(df: pd.DataFrame, max_rows: int = 20) -> str:
    if df.empty:
        return "_No rows._"
    display = df.head(max_rows).copy().astype(str)
    columns = list(display.columns)
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join(["---"] * len(columns)) + " |"
    body = ["| " + " | ".join(row[column].replace("|", "/") for column in columns) + " |" for _, row in display.iterrows()]
    suffix = f"\n\n_Showing first {max_rows} of {len(df)} rows._" if len(df) > max_rows else ""
    return "\n".join([header, separator, *body]) + suffix


def write_docs(
    out_dir: Path,
    run_id: str,
    decision: str,
    can_enter_p2c: bool,
    can_enter_p3: bool,
    volume_detail: pd.DataFrame,
    price_jump_detail: pd.DataFrame,
    metadata_detail: pd.DataFrame,
    ticker_recommendations: pd.DataFrame,
) -> None:
    volume_count = int(len(volume_detail))
    jump_ticker_count = int(price_jump_detail["ticker"].nunique()) if not price_jump_detail.empty else 0
    jump_event_count = int(len(price_jump_detail))
    metadata_warning_count = int((metadata_detail["severity"] == "WARNING").sum()) if not metadata_detail.empty else 0
    blocks_count = int(ticker_recommendations["whether_blocks_p3"].astype(bool).sum()) if not ticker_recommendations.empty else 0
    report = f"""# Formal MVE2 Gate Exceptions Review P2-B

Run id: `{run_id}`

## Executive Summary

- Gate exception decision: `{decision}`
- Can enter P2-C gate recheck: `{str(can_enter_p2c).lower()}`
- Can enter P3 formal MVE2 search design: `{str(can_enter_p3).lower()}`
- Direct v10 remains forbidden.
- No strategy search, model training, formal MVE2, v10, or raw data repair was performed.

## Exception Counts

- Non-positive volume tickers: `{volume_count}`
- Large jump tickers: `{jump_ticker_count}`
- Large jump events: `{jump_event_count}`
- Audit metadata warning rows: `{metadata_warning_count}`
- Tickers blocking P3 after review: `{blocks_count}`

## Non-Positive Volume Detail

{markdown_table(volume_detail)}

## Large Daily Jump Detail

{markdown_table(price_jump_detail)}

## Metadata Conflict Detail

{markdown_table(metadata_detail)}

## Ticker-Level Recommendations

{markdown_table(ticker_recommendations)}

## Conclusion

P2-B remains conservative. It does not change any limited MVE2 decision and does not promote limited MVE2 to a formal baseline. The current formal baseline remains v8.2 frozen Pool A `top5_ytdcap80p_derisk100p`; formal v9 remains a failed branch.
"""
    (out_dir / "p2b_exception_review_report.md").write_text(report, encoding="utf-8")

    readme = f"""# Formal MVE2 Gate Exceptions Review P2-B

This directory expands the exceptions raised by P2-A into reviewable ticker and event-level tables.

Run id: `{run_id}`

Decision: `{decision}`

Read order:

1. `p2b_exception_review_report.md`
2. `formal_mve2_gate_exception_decision.json`
3. `exception_review_summary.csv`
4. `volume_exception_detail.csv`
5. `price_jump_detail.csv`
6. `metadata_conflict_detail.csv`
7. `ticker_level_recommendations.csv`

The script only reads the audited unified adjusted OHLCV store, P2-A outputs, and the limited MVE2 validation pack. It does not alter raw data or previous conclusions.
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
    run_id = f"formal_mve2_data_quality_gate_p2b_exceptions_{timestamp}"
    out_dir = OUTPUT_ROOT / run_id
    small_tables_dir = out_dir / "small_tables"
    out_dir.mkdir(parents=True, exist_ok=False)
    small_tables_dir.mkdir(parents=True, exist_ok=True)

    required_inputs = [
        P2A_DIR / "risk_flags.csv",
        P2A_DIR / "volume_liquidity_summary.csv",
        P2A_DIR / "price_anomaly_summary.csv",
        P2A_DIR / "formal_mve2_readiness_decision.json",
        VALIDATION_DIR / "manifest.json",
        VALIDATION_DIR / "key_metrics_summary.csv",
        PRICES_DIR,
        ACTIONS_DIR,
    ]
    missing_inputs = [rel(path) for path in required_inputs if not path.exists()]
    head = git_head()
    status, candidates, _eligible_set = universe_maps()

    volume_detail = pd.DataFrame()
    price_jump_detail = pd.DataFrame()
    metadata_detail = pd.DataFrame()
    ticker_recommendations = pd.DataFrame()
    if not missing_inputs:
        volume_detail = build_volume_detail(status, candidates)
        price_jump_detail = build_price_jump_detail(status, candidates)
        metadata_detail = build_metadata_conflicts(head)
        ticker_recommendations = build_ticker_recommendations(status, volume_detail, price_jump_detail, metadata_detail)

    decision, reasons, can_enter_p2c, can_enter_p3 = decide(volume_detail, price_jump_detail, metadata_detail, missing_inputs)
    flags = risk_flags(decision, volume_detail, price_jump_detail, metadata_detail)

    summary = pd.DataFrame(
        [
            {"metric": "p2a_readiness", "value": clean(read_json(P2A_DIR / "formal_mve2_readiness_decision.json").get("readiness_decision"))},
            {"metric": "p2b_decision", "value": decision},
            {"metric": "can_enter_p2c_gate_recheck", "value": can_enter_p2c},
            {"metric": "can_enter_p3_formal_search_design", "value": can_enter_p3},
            {"metric": "direct_v10_allowed", "value": False},
            {"metric": "non_positive_volume_ticker_count", "value": int(len(volume_detail))},
            {"metric": "price_jump_ticker_count", "value": int(price_jump_detail["ticker"].nunique()) if not price_jump_detail.empty else 0},
            {"metric": "price_jump_event_count", "value": int(len(price_jump_detail))},
            {"metric": "metadata_warning_rows", "value": int((metadata_detail["severity"] == "WARNING").sum()) if not metadata_detail.empty else 0},
            {"metric": "missing_required_inputs", "value": ";".join(missing_inputs) if missing_inputs else "none"},
        ]
    )
    reproducibility = pd.DataFrame(
        [
            {"item": "script_path", "status": "PASS", "value": SCRIPT_PATH.as_posix()},
            {"item": "git_commit", "status": "PASS", "value": head},
            {"item": "p2a_output_dir", "status": "PASS" if P2A_DIR.exists() else "FAIL", "value": rel(P2A_DIR)},
            {"item": "store_dir", "status": "PASS" if STORE_DIR.exists() else "FAIL", "value": rel(STORE_DIR)},
            {"item": "validation_pack_dir", "status": "PASS" if VALIDATION_DIR.exists() else "FAIL", "value": rel(VALIDATION_DIR)},
            {"item": "group4_hold_not_touched", "status": "PASS", "value": "true"},
            {"item": "raw_data_modified", "status": "PASS", "value": "false"},
            {"item": "strategy_search_executed", "status": "PASS", "value": "false"},
            {"item": "model_training_executed", "status": "PASS", "value": "false"},
            {"item": "formal_mve2_executed", "status": "PASS", "value": "false"},
            {"item": "v10_executed", "status": "PASS", "value": "false"},
        ]
    )

    summary.to_csv(out_dir / "exception_review_summary.csv", index=False)
    volume_detail.to_csv(out_dir / "volume_exception_detail.csv", index=False)
    price_jump_detail.to_csv(out_dir / "price_jump_detail.csv", index=False)
    metadata_detail.to_csv(out_dir / "metadata_conflict_detail.csv", index=False)
    ticker_recommendations.to_csv(out_dir / "ticker_level_recommendations.csv", index=False)
    reproducibility.to_csv(out_dir / "reproducibility_checklist.csv", index=False)
    flags.to_csv(out_dir / "risk_flags.csv", index=False)

    if not volume_detail.empty:
        volume_detail.groupby(["recommendation"], dropna=False).size().reset_index(name="count").to_csv(small_tables_dir / "volume_recommendation_counts.csv", index=False)
    if not price_jump_detail.empty:
        price_jump_detail.groupby(["recommendation"], dropna=False).size().reset_index(name="count").to_csv(small_tables_dir / "price_jump_recommendation_counts.csv", index=False)
        price_jump_detail.groupby(["ticker"], dropna=False).size().reset_index(name="jump_event_count").to_csv(small_tables_dir / "price_jump_event_counts_by_ticker.csv", index=False)
    if not ticker_recommendations.empty:
        ticker_recommendations.groupby(["recommended_action"], dropna=False).size().reset_index(name="count").to_csv(small_tables_dir / "ticker_action_counts.csv", index=False)
        ticker_recommendations[ticker_recommendations["whether_blocks_p3"].astype(bool)].to_csv(small_tables_dir / "p3_blocking_tickers.csv", index=False)

    decision_payload = {
        "run_id": run_id,
        "p2a_run_id": P2A_RUN_ID,
        "gate_exception_decision": decision,
        "can_enter_p2c_gate_recheck": can_enter_p2c,
        "can_enter_p3_formal_mve2_search_design": can_enter_p3,
        "direct_v10_allowed": False,
        "reasons": reasons,
        "group4_hold_not_touched": True,
        "raw_data_modified": False,
        "strategy_search_executed": False,
        "model_training_executed": False,
        "formal_mve2_executed": False,
        "v10_executed": False,
    }
    (out_dir / "formal_mve2_gate_exception_decision.json").write_text(
        json.dumps(decision_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    write_docs(out_dir, run_id, decision, can_enter_p2c, can_enter_p3, volume_detail, price_jump_detail, metadata_detail, ticker_recommendations)

    generated_files = [
        rel(out_dir / "README.md"),
        rel(out_dir / "manifest.json"),
        rel(out_dir / "p2b_exception_review_report.md"),
        rel(out_dir / "exception_review_summary.csv"),
        rel(out_dir / "volume_exception_detail.csv"),
        rel(out_dir / "price_jump_detail.csv"),
        rel(out_dir / "metadata_conflict_detail.csv"),
        rel(out_dir / "ticker_level_recommendations.csv"),
        rel(out_dir / "formal_mve2_gate_exception_decision.json"),
        rel(out_dir / "reproducibility_checklist.csv"),
        rel(out_dir / "risk_flags.csv"),
        rel(small_tables_dir),
    ]
    manifest = {
        "run_id": run_id,
        "run_type": "formal_mve2_data_quality_gate_p2b_exceptions_review",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "git_commit": head,
        "script_path": SCRIPT_PATH.as_posix(),
        "input_paths": [rel(P2A_DIR), rel(STORE_DIR), rel(VALIDATION_DIR)],
        "output_dir": rel(out_dir),
        "generated_files": generated_files,
        "explicit_exclusions": ["old qlib", "old v8 cache", "formal v9 output", "v8.2 formal baseline output"],
        "gate_exception_decision": decision,
        "can_enter_p2c_gate_recheck": can_enter_p2c,
        "can_enter_p3_formal_mve2_search_design": can_enter_p3,
        "direct_v10_allowed": False,
        "group4_hold_not_touched": True,
        "raw_data_modified": False,
        "strategy_search_executed": False,
        "model_training_executed": False,
        "formal_mve2_executed": False,
        "v10_executed": False,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    zip_path = OUTPUT_ROOT / f"{run_id}.zip"
    write_zip(out_dir, zip_path)

    print(
        json.dumps(
            {
                "run_id": run_id,
                "output_dir": rel(out_dir),
                "zip_path": rel(zip_path),
                "zip_size_bytes": zip_path.stat().st_size,
                "gate_exception_decision": decision,
                "can_enter_p2c_gate_recheck": can_enter_p2c,
                "can_enter_p3_formal_mve2_search_design": can_enter_p3,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
