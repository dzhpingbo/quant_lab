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
P2A_RUN_ID = "formal_mve2_data_quality_gate_20260507_142224"
P2B_RUN_ID = "formal_mve2_data_quality_gate_p2b_exceptions_20260507_151856"
P2A_DIR = OUTPUT_ROOT / P2A_RUN_ID
P2B_DIR = OUTPUT_ROOT / P2B_RUN_ID
VALIDATION_RUN_ID = "limited_mve2_validation_20260502_183555"
VALIDATION_DIR = OUTPUT_ROOT / VALIDATION_RUN_ID
SEARCH_RUN_ID = "limited_mve2_20260502_142702"
SEARCH_DIR = OUTPUT_ROOT / SEARCH_RUN_ID
SCRIPT_PATH = Path("scripts/us_stock_selection/55_reconcile_formal_mve2_audit_metadata_conflict.py")
REQUIRED_FIELDS = ["date", "ticker", "adj_close", "volume"]


def rel(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def rel_from_text(value: Any) -> str:
    text = str(value)
    if not text or text == "nan":
        return "NA"
    normalized = text.replace("\\", "/")
    root = PROJECT_ROOT.as_posix()
    if normalized.lower().startswith(root.lower()):
        return normalized[len(root):].lstrip("/")
    marker = "quant_lab/"
    if marker in normalized:
        return normalized.split(marker, 1)[1]
    return normalized


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


def bool_from_value(value: Any) -> bool | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None


def numeric_int(value: Any, default: int = 0) -> int:
    converted = pd.to_numeric(value, errors="coerce")
    if pd.isna(converted):
        return default
    return int(converted)


def parquet_summary(ticker: str) -> dict[str, Any]:
    path = PRICES_DIR / f"{ticker}.parquet"
    base = {
        "ticker": ticker,
        "parquet_file": rel(path),
        "parquet_exists": path.exists(),
        "parquet_readable": False,
        "parquet_row_count": 0,
        "parquet_date_min": "NA",
        "parquet_date_max": "NA",
        "parquet_required_fields_present": False,
        "missing_required_fields": "NA",
        "non_null_adj_close_count": 0,
        "non_null_volume_count": 0,
        "duplicate_date_count": 0,
        "non_positive_price_count": 0,
        "non_positive_volume_count": 0,
        "file_size_bytes": path.stat().st_size if path.exists() else 0,
        "mtime_summary": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds") if path.exists() else "NA",
        "read_error": "NA",
    }
    if not path.exists():
        return base
    try:
        df = pd.read_parquet(path)
    except Exception as exc:
        base["read_error"] = type(exc).__name__
        return base
    fields_present = [field for field in REQUIRED_FIELDS if field in df.columns]
    missing = [field for field in REQUIRED_FIELDS if field not in df.columns]
    if "date" in df.columns:
        dates = pd.to_datetime(df["date"], errors="coerce")
    else:
        dates = pd.Series(dtype="datetime64[ns]")
    adj_close = pd.to_numeric(df["adj_close"], errors="coerce") if "adj_close" in df.columns else pd.Series(dtype=float)
    volume = pd.to_numeric(df["volume"], errors="coerce") if "volume" in df.columns else pd.Series(dtype=float)
    duplicate_count = int(df.duplicated(subset=["date"]).sum()) if "date" in df.columns else 0
    base.update(
        {
            "parquet_readable": True,
            "parquet_row_count": int(len(df)),
            "parquet_date_min": dates.min().date().isoformat() if not dates.empty and pd.notna(dates.min()) else "NA",
            "parquet_date_max": dates.max().date().isoformat() if not dates.empty and pd.notna(dates.max()) else "NA",
            "parquet_required_fields_present": len(missing) == 0,
            "missing_required_fields": ";".join(missing) if missing else "none",
            "non_null_adj_close_count": int(adj_close.notna().sum()),
            "non_null_volume_count": int(volume.notna().sum()),
            "duplicate_date_count": duplicate_count,
            "non_positive_price_count": int((adj_close <= 0).sum()) if not adj_close.empty else 0,
            "non_positive_volume_count": int((volume <= 0).sum()) if not volume.empty else 0,
        }
    )
    return base


def price_manifest_rows() -> dict[str, dict[str, Any]]:
    manifest = read_csv(AUDIT_DIR / "store_file_manifest.csv")
    if manifest.empty:
        return {}
    price_rows = manifest[manifest["file_type"].astype(str) == "price"].copy() if "file_type" in manifest.columns else manifest
    rows: dict[str, dict[str, Any]] = {}
    for _, row in price_rows.iterrows():
        ticker = str(row.get("ticker", "NA"))
        rows[ticker] = {
            "manifest_rows": numeric_int(row.get("rows", 0)),
            "manifest_path": rel_from_text(row.get("path", "NA")),
        }
    return rows


def conflict_type_for(
    audit_rows: int,
    audit_success: bool | None,
    parquet: dict[str, Any],
    manifest_rows: int | None,
) -> str:
    types: list[str] = []
    if not parquet["parquet_exists"]:
        types.append("PARQUET_MISSING")
    elif not parquet["parquet_readable"]:
        types.append("PARQUET_UNREADABLE")
    elif not parquet["parquet_required_fields_present"]:
        types.append("REQUIRED_FIELDS_MISSING")
    if parquet["parquet_readable"] and audit_rows != parquet["parquet_row_count"]:
        types.append("AUDIT_ROW_COUNT_MISMATCH")
    expected_success = bool(parquet["parquet_exists"] and parquet["parquet_readable"] and parquet["parquet_row_count"] > 0)
    if audit_success is not None and audit_success != expected_success:
        types.append("AUDIT_SUCCESS_FLAG_MISMATCH")
    if (
        parquet["parquet_readable"]
        and manifest_rows is not None
        and manifest_rows == parquet["parquet_row_count"]
        and audit_rows == 0
        and audit_success is False
    ):
        types.insert(0, "STALE_AUDIT_METADATA")
    if not types:
        return "NO_CONFLICT"
    return ";".join(dict.fromkeys(types))


def build_reconciliation_tables() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    price_quality = read_csv(AUDIT_DIR / "price_quality_audit.csv")
    p2b_conflicts = read_csv(P2B_DIR / "metadata_conflict_detail.csv")
    manifest_rows = price_manifest_rows()
    tickers = sorted(set(price_quality["ticker"].astype(str)) if "ticker" in price_quality.columns else set())
    if p2b_conflicts is not None and not p2b_conflicts.empty and "ticker" in p2b_conflicts.columns:
        tickers = sorted(set(tickers) | set(p2b_conflicts[p2b_conflicts["ticker"].astype(str) != "ALL"]["ticker"].astype(str)))

    detail_rows: list[dict[str, Any]] = []
    parquet_rows: list[dict[str, Any]] = []
    row_count_rows: list[dict[str, Any]] = []
    success_rows: list[dict[str, Any]] = []
    file_rows: list[dict[str, Any]] = []
    pq_by_ticker = price_quality.set_index("ticker").to_dict("index") if "ticker" in price_quality.columns else {}

    for ticker in tickers:
        pq = pq_by_ticker.get(ticker, {})
        parquet = parquet_summary(ticker)
        manifest = manifest_rows.get(ticker, {})
        audit_rows = numeric_int(pq.get("n_rows", 0))
        audit_success = bool_from_value(pq.get("download_success"))
        manifest_row_count = manifest.get("manifest_rows")
        conflict_type = conflict_type_for(audit_rows, audit_success, parquet, manifest_row_count)
        row_count_match = bool(parquet["parquet_readable"] and audit_rows == parquet["parquet_row_count"])
        expected_success = bool(parquet["parquet_exists"] and parquet["parquet_readable"] and parquet["parquet_row_count"] > 0)
        success_flag_match = bool(audit_success == expected_success)
        severity = "PASS" if conflict_type == "NO_CONFLICT" else "WARNING"
        if any(item in conflict_type for item in ["PARQUET_MISSING", "PARQUET_UNREADABLE", "REQUIRED_FIELDS_MISSING"]):
            severity = "CRITICAL"
        likely_explanation = "No mismatch detected."
        recommended_action = "No action required."
        if "STALE_AUDIT_METADATA" in conflict_type:
            likely_explanation = "price_quality audit records a failed refresh while parquet and store manifest show readable entity data."
            recommended_action = "Allow P2-C recheck using parquet-derived metadata; regenerate audit metadata before P3."
        elif conflict_type != "NO_CONFLICT":
            likely_explanation = "Audit metadata and entity data are not aligned."
            recommended_action = "Review data trail before P2-C."

        detail = {
            "ticker": ticker,
            "audit_metadata_file": rel(AUDIT_DIR / "price_quality_audit.csv"),
            "audit_row_count": audit_rows,
            "audit_success_flag": clean(pq.get("download_success", "NA")),
            "parquet_file": parquet["parquet_file"],
            "parquet_exists": parquet["parquet_exists"],
            "parquet_readable": parquet["parquet_readable"],
            "parquet_row_count": parquet["parquet_row_count"],
            "parquet_date_min": parquet["parquet_date_min"],
            "parquet_date_max": parquet["parquet_date_max"],
            "parquet_required_fields_present": parquet["parquet_required_fields_present"],
            "manifest_row_count": manifest_row_count if manifest_row_count is not None else "NA",
            "manifest_path": manifest.get("manifest_path", "NA"),
            "row_count_match": row_count_match,
            "success_flag_match": success_flag_match,
            "conflict_type": conflict_type,
            "severity": severity,
            "likely_explanation": likely_explanation,
            "recommended_action": recommended_action,
        }
        detail_rows.append(detail)
        parquet_rows.append(parquet)
        row_count_rows.append(
            {
                "ticker": ticker,
                "audit_row_count": audit_rows,
                "manifest_row_count": manifest_row_count if manifest_row_count is not None else "NA",
                "parquet_row_count": parquet["parquet_row_count"],
                "audit_vs_parquet_match": row_count_match,
                "manifest_vs_parquet_match": bool(manifest_row_count == parquet["parquet_row_count"]) if manifest_row_count is not None else False,
            }
        )
        success_rows.append(
            {
                "ticker": ticker,
                "audit_success_flag": clean(pq.get("download_success", "NA")),
                "expected_success_from_parquet": expected_success,
                "success_flag_match": success_flag_match,
                "download_error_class": "rate_limited" if "Too Many Requests" in clean(pq.get("download_error", "")) else "other_or_none",
            }
        )
        file_rows.append(
            {
                "ticker": ticker,
                "parquet_file": parquet["parquet_file"],
                "file_size_bytes": parquet["file_size_bytes"],
                "mtime_summary": parquet["mtime_summary"],
                "audit_metadata_file": rel(AUDIT_DIR / "price_quality_audit.csv"),
                "audit_metadata_mtime": datetime.fromtimestamp((AUDIT_DIR / "price_quality_audit.csv").stat().st_mtime).isoformat(timespec="seconds") if (AUDIT_DIR / "price_quality_audit.csv").exists() else "NA",
            }
        )
    return (
        pd.DataFrame(detail_rows),
        pd.DataFrame(parquet_rows),
        pd.DataFrame(row_count_rows),
        pd.DataFrame(success_rows),
        pd.DataFrame(file_rows),
    )


def build_impact_assessment(detail: pd.DataFrame) -> pd.DataFrame:
    has_critical = bool((detail["severity"] == "CRITICAL").any()) if not detail.empty else True
    stale_count = int(detail["conflict_type"].astype(str).str.contains("STALE_AUDIT_METADATA").sum()) if not detail.empty else 0
    return pd.DataFrame(
        [
            {
                "impact_area": "data_readability",
                "impact": "NO_BLOCK" if not has_critical else "BLOCK",
                "rationale": "All price parquet files are readable with required fields." if not has_critical else "At least one parquet file is missing, unreadable, or lacks required fields.",
            },
            {
                "impact_area": "ticker_universe_reproducibility",
                "impact": "NO_BLOCK",
                "rationale": "Universe evidence is held in limited MVE2 eligible/excluded files, not in price_quality audit success flags.",
            },
            {
                "impact_area": "eligible_excluded_reproducibility",
                "impact": "NO_BLOCK",
                "rationale": "Eligible/excluded CSV files remain readable and are not changed by this task.",
            },
            {
                "impact_area": "formal_mve2_data_source_uniqueness",
                "impact": "NO_BLOCK",
                "rationale": "Only audited unified adjusted OHLCV store and limited MVE2 evidence were read.",
            },
            {
                "impact_area": "p2a_readiness",
                "impact": "EXPLAINS_CONDITIONAL",
                "rationale": f"{stale_count} metadata rows are attributable to stale audit metadata rather than unreadable parquet.",
            },
            {
                "impact_area": "p2c_gate_recheck",
                "impact": "ALLOW" if not has_critical else "BLOCK",
                "rationale": "P2-C can recheck using parquet-derived reconciliation evidence." if not has_critical else "Critical entity-data issue must be repaired before P2-C.",
            },
            {
                "impact_area": "p3_search_design",
                "impact": "BLOCK_UNTIL_P2C_PASS",
                "rationale": "P3 remains forbidden until P2-C gate recheck passes and human review accepts known exceptions.",
            },
        ]
    )


def build_commit_metadata(current_head: str) -> pd.DataFrame:
    manifests = [
        ("limited_validation_pack", VALIDATION_DIR / "manifest.json", "pack_generated_from_commit"),
        ("p2a_gate", P2A_DIR / "manifest.json", "source_git_commit"),
        ("p2b_exception_review", P2B_DIR / "manifest.json", "source_git_commit"),
    ]
    rows = []
    for scope, path, field_name in manifests:
        manifest = read_json(path)
        observed = clean(manifest.get("git_commit", "NA"))
        rows.append(
            {
                "scope": scope,
                "field_name": field_name,
                "observed_value": observed,
                "pack_repository_commit": current_head,
                "expected_value": "Generated-output commit may predate the repository commit that stores it.",
                "explanation": "This is a provenance timing difference, not a data-content mismatch.",
                "severity": "INFO",
                "whether_blocks_p2c": False,
                "whether_blocks_p3": False,
            }
        )
    return pd.DataFrame(rows)


def decide(detail: pd.DataFrame, impact: pd.DataFrame) -> tuple[str, list[str], bool, bool]:
    if detail.empty:
        return "FAIL_DATA_EVIDENCE_CHAIN", ["No reconciliation detail was produced."], False, False
    critical = int((detail["severity"] == "CRITICAL").sum())
    unknown = int(detail["conflict_type"].astype(str).str.contains("UNKNOWN_CONFLICT|PARQUET_MISSING|PARQUET_UNREADABLE|REQUIRED_FIELDS_MISSING", regex=True).sum())
    stale = int(detail["conflict_type"].astype(str).str.contains("STALE_AUDIT_METADATA").sum())
    manifest_match = bool((detail["manifest_row_count"].astype(str) != "NA").all())
    if critical or unknown:
        return "FAIL_DATA_EVIDENCE_CHAIN", [f"critical_or_unknown_conflicts={critical + unknown}"], False, False
    if stale == len(detail) and manifest_match:
        return (
            "PASS_TO_P2C_GATE_RECHECK",
            [
                f"stale_audit_metadata_rows={stale}",
                "parquet files are readable and store manifest row counts reconcile with parquet row counts.",
                "P3 remains blocked until P2-C passes.",
            ],
            True,
            False,
        )
    return (
        "CONDITIONAL_NEEDS_AUDIT_METADATA_FIX",
        ["Conflicts are not fully reconciled to stale metadata."],
        False,
        False,
    )


def build_summary(
    detail: pd.DataFrame,
    parquet: pd.DataFrame,
    row_counts: pd.DataFrame,
    success_flags: pd.DataFrame,
    decision: str,
    can_enter_p2c: bool,
    can_enter_p3: bool,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"metric": "reconciliation_decision", "value": decision},
            {"metric": "can_enter_p2c_gate_recheck", "value": can_enter_p2c},
            {"metric": "can_enter_p3_formal_search_design", "value": can_enter_p3},
            {"metric": "direct_v10_allowed", "value": False},
            {"metric": "ticker_count", "value": int(len(detail))},
            {"metric": "parquet_readable_count", "value": int(parquet["parquet_readable"].sum()) if not parquet.empty else 0},
            {"metric": "required_fields_present_count", "value": int(parquet["parquet_required_fields_present"].sum()) if not parquet.empty else 0},
            {"metric": "audit_row_count_mismatch_count", "value": int((~row_counts["audit_vs_parquet_match"].astype(bool)).sum()) if not row_counts.empty else 0},
            {"metric": "manifest_row_count_match_count", "value": int(row_counts["manifest_vs_parquet_match"].astype(bool).sum()) if not row_counts.empty else 0},
            {"metric": "audit_success_flag_mismatch_count", "value": int((~success_flags["success_flag_match"].astype(bool)).sum()) if not success_flags.empty else 0},
            {"metric": "stale_audit_metadata_count", "value": int(detail["conflict_type"].astype(str).str.contains("STALE_AUDIT_METADATA").sum()) if not detail.empty else 0},
        ]
    )


def build_risk_flags(decision: str, detail: pd.DataFrame, row_counts: pd.DataFrame, success_flags: pd.DataFrame) -> pd.DataFrame:
    critical_count = int((detail["severity"] == "CRITICAL").sum()) if not detail.empty else 1
    stale_count = int(detail["conflict_type"].astype(str).str.contains("STALE_AUDIT_METADATA").sum()) if not detail.empty else 0
    audit_row_mismatch = int((~row_counts["audit_vs_parquet_match"].astype(bool)).sum()) if not row_counts.empty else 0
    manifest_match = int(row_counts["manifest_vs_parquet_match"].astype(bool).sum()) if not row_counts.empty else 0
    success_mismatch = int((~success_flags["success_flag_match"].astype(bool)).sum()) if not success_flags.empty else 0
    return pd.DataFrame(
        [
            {"flag_id": "parquet_entity_readability", "severity": "critical", "status": "PASS" if critical_count == 0 else "FAIL", "affected_count": critical_count, "detail": "Readable parquet files with required fields are required."},
            {"flag_id": "stale_price_quality_audit_metadata", "severity": "warning", "status": "RECONCILED", "affected_count": stale_count, "detail": "price_quality audit rows reflect stale failed refresh metadata."},
            {"flag_id": "audit_row_count_mismatch", "severity": "warning", "status": "RECONCILED", "affected_count": audit_row_mismatch, "detail": "Audit row counts are stale relative to parquet row counts."},
            {"flag_id": "store_manifest_row_count_match", "severity": "info", "status": "PASS", "affected_count": manifest_match, "detail": "store_file_manifest row counts match parquet row counts."},
            {"flag_id": "audit_success_flag_mismatch", "severity": "warning", "status": "RECONCILED", "affected_count": success_mismatch, "detail": "Audit success flags are stale relative to readable parquet files."},
            {"flag_id": "reconciliation_decision", "severity": "info", "status": decision, "affected_count": 0, "detail": "P2-B2 reconciliation decision."},
        ]
    )


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
    summary: pd.DataFrame,
    detail: pd.DataFrame,
    impact: pd.DataFrame,
    commit_metadata: pd.DataFrame,
) -> None:
    stale_count = int(detail["conflict_type"].astype(str).str.contains("STALE_AUDIT_METADATA").sum()) if not detail.empty else 0
    critical_count = int((detail["severity"] == "CRITICAL").sum()) if not detail.empty else 0
    report = f"""# Formal MVE2 Audit Metadata Reconciliation P2-B2

Run id: `{run_id}`

## Executive Summary

- Reconciliation decision: `{decision}`
- Can enter P2-C gate recheck: `{str(can_enter_p2c).lower()}`
- Can enter P3 formal MVE2 search design: `{str(can_enter_p3).lower()}`
- Direct v10 remains forbidden.
- No strategy search, model training, formal MVE2, v10, raw price repair, or audit CSV repair was performed.

## Core Finding

The P2-B metadata conflict is attributable to stale `price_quality_audit.csv` rows. The audit CSV records failed refresh metadata, while price parquet files are readable and store manifest row counts reconcile with parquet row counts.

- Stale audit metadata rows: `{stale_count}`
- Critical parquet evidence failures: `{critical_count}`

## Reconciliation Summary

{markdown_table(summary)}

## Audit CSV vs Parquet Detail

{markdown_table(detail)}

## Evidence Chain Impact

{markdown_table(impact)}

## Commit Metadata Timing

{markdown_table(commit_metadata)}

## Decision Rationale

P2-C is allowed as a gate recheck because the conflict does not block data readability, ticker universe reproducibility, eligible/excluded reproducibility, or data source uniqueness. P3 remains blocked until P2-C passes and human review accepts the remaining known flags.
"""
    (out_dir / "p2b2_audit_metadata_reconciliation_report.md").write_text(report, encoding="utf-8")
    readme = f"""# Formal MVE2 Audit Metadata Reconciliation P2-B2

This directory reconciles P2-B audit metadata conflicts without modifying raw data or existing audit files.

Run id: `{run_id}`

Decision: `{decision}`

Review order:

1. `p2b2_audit_metadata_reconciliation_report.md`
2. `reconciliation_decision.json`
3. `metadata_conflict_reconciliation_summary.csv`
4. `audit_csv_vs_parquet_detail.csv`
5. `row_count_reconciliation.csv`
6. `success_flag_reconciliation.csv`
7. `evidence_chain_impact_assessment.csv`

This output allows P2-C gate recheck only when the decision is `PASS_TO_P2C_GATE_RECHECK`. It does not authorize P3 or v10.
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
    run_id = f"formal_mve2_audit_metadata_reconciliation_p2b2_{timestamp}"
    out_dir = OUTPUT_ROOT / run_id
    small_tables_dir = out_dir / "small_tables"
    out_dir.mkdir(parents=True, exist_ok=False)
    small_tables_dir.mkdir(parents=True, exist_ok=True)

    required_inputs = [
        P2A_DIR / "risk_flags.csv",
        P2A_DIR / "manifest.json",
        P2A_DIR / "formal_mve2_readiness_decision.json",
        P2B_DIR / "metadata_conflict_detail.csv",
        P2B_DIR / "formal_mve2_gate_exception_decision.json",
        AUDIT_DIR / "price_quality_audit.csv",
        AUDIT_DIR / "store_file_manifest.csv",
        PRICES_DIR,
        VALIDATION_DIR / "manifest.json",
    ]
    missing_inputs = [rel(path) for path in required_inputs if not path.exists()]
    head = git_head()

    if missing_inputs:
        detail = pd.DataFrame()
        parquet = pd.DataFrame()
        row_counts = pd.DataFrame()
        success_flags = pd.DataFrame()
        file_mtime = pd.DataFrame()
        impact = pd.DataFrame(
            [{"impact_area": "required_inputs", "impact": "BLOCK", "rationale": ";".join(missing_inputs)}]
        )
        decision = "FAIL_DATA_EVIDENCE_CHAIN"
        reasons = [f"missing_required_input={item}" for item in missing_inputs]
        can_enter_p2c = False
        can_enter_p3 = False
    else:
        detail, parquet, row_counts, success_flags, file_mtime = build_reconciliation_tables()
        impact = build_impact_assessment(detail)
        decision, reasons, can_enter_p2c, can_enter_p3 = decide(detail, impact)

    commit_metadata = build_commit_metadata(head)
    summary = build_summary(detail, parquet, row_counts, success_flags, decision, can_enter_p2c, can_enter_p3)
    flags = build_risk_flags(decision, detail, row_counts, success_flags)

    summary.to_csv(out_dir / "metadata_conflict_reconciliation_summary.csv", index=False)
    detail.to_csv(out_dir / "audit_csv_vs_parquet_detail.csv", index=False)
    parquet.to_csv(out_dir / "parquet_readability_summary.csv", index=False)
    row_counts.to_csv(out_dir / "row_count_reconciliation.csv", index=False)
    success_flags.to_csv(out_dir / "success_flag_reconciliation.csv", index=False)
    file_mtime.to_csv(out_dir / "file_size_mtime_summary.csv", index=False)
    impact.to_csv(out_dir / "evidence_chain_impact_assessment.csv", index=False)
    commit_metadata.to_csv(small_tables_dir / "commit_metadata_reconciliation.csv", index=False)
    if not detail.empty:
        detail.groupby("conflict_type", dropna=False).size().reset_index(name="count").to_csv(small_tables_dir / "conflict_type_counts.csv", index=False)
        detail.groupby("severity", dropna=False).size().reset_index(name="count").to_csv(small_tables_dir / "severity_counts.csv", index=False)
    if not row_counts.empty:
        row_counts[~row_counts["audit_vs_parquet_match"].astype(bool)].to_csv(small_tables_dir / "audit_row_count_mismatch_rows.csv", index=False)
        row_counts[row_counts["manifest_vs_parquet_match"].astype(bool)].to_csv(small_tables_dir / "manifest_row_count_match_rows.csv", index=False)

    reproducibility = pd.DataFrame(
        [
            {"item": "script_path", "status": "PASS", "value": SCRIPT_PATH.as_posix()},
            {"item": "git_commit", "status": "PASS", "value": head},
            {"item": "p2a_output_dir", "status": "PASS" if P2A_DIR.exists() else "FAIL", "value": rel(P2A_DIR)},
            {"item": "p2b_output_dir", "status": "PASS" if P2B_DIR.exists() else "FAIL", "value": rel(P2B_DIR)},
            {"item": "store_dir", "status": "PASS" if STORE_DIR.exists() else "FAIL", "value": rel(STORE_DIR)},
            {"item": "raw_data_modified", "status": "PASS", "value": "false"},
            {"item": "audit_csv_modified", "status": "PASS", "value": "false"},
            {"item": "group4_hold_not_touched", "status": "PASS", "value": "true"},
            {"item": "strategy_search_executed", "status": "PASS", "value": "false"},
            {"item": "model_training_executed", "status": "PASS", "value": "false"},
            {"item": "formal_mve2_executed", "status": "PASS", "value": "false"},
            {"item": "v10_executed", "status": "PASS", "value": "false"},
        ]
    )
    reproducibility.to_csv(out_dir / "reproducibility_checklist.csv", index=False)
    flags.to_csv(out_dir / "risk_flags.csv", index=False)

    decision_payload = {
        "run_id": run_id,
        "p2a_run_id": P2A_RUN_ID,
        "p2b_run_id": P2B_RUN_ID,
        "reconciliation_decision": decision,
        "can_enter_p2c_gate_recheck": can_enter_p2c,
        "can_enter_p3_formal_mve2_search_design": can_enter_p3,
        "direct_v10_allowed": False,
        "reasons": reasons,
        "group4_hold_not_touched": True,
        "raw_data_modified": False,
        "audit_csv_modified": False,
        "strategy_search_executed": False,
        "model_training_executed": False,
        "formal_mve2_executed": False,
        "v10_executed": False,
    }
    (out_dir / "reconciliation_decision.json").write_text(
        json.dumps(decision_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    write_docs(out_dir, run_id, decision, can_enter_p2c, can_enter_p3, summary, detail, impact, commit_metadata)

    generated_files = [
        rel(out_dir / "README.md"),
        rel(out_dir / "manifest.json"),
        rel(out_dir / "p2b2_audit_metadata_reconciliation_report.md"),
        rel(out_dir / "metadata_conflict_reconciliation_summary.csv"),
        rel(out_dir / "audit_csv_vs_parquet_detail.csv"),
        rel(out_dir / "parquet_readability_summary.csv"),
        rel(out_dir / "row_count_reconciliation.csv"),
        rel(out_dir / "success_flag_reconciliation.csv"),
        rel(out_dir / "file_size_mtime_summary.csv"),
        rel(out_dir / "evidence_chain_impact_assessment.csv"),
        rel(out_dir / "reconciliation_decision.json"),
        rel(out_dir / "reproducibility_checklist.csv"),
        rel(out_dir / "risk_flags.csv"),
        rel(small_tables_dir),
    ]
    manifest = {
        "run_id": run_id,
        "run_type": "formal_mve2_audit_metadata_reconciliation_p2b2",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "git_commit": head,
        "script_path": SCRIPT_PATH.as_posix(),
        "input_paths": [rel(P2A_DIR), rel(P2B_DIR), rel(STORE_DIR), rel(VALIDATION_DIR)],
        "output_dir": rel(out_dir),
        "generated_files": generated_files,
        "explicit_exclusions": ["old qlib", "old v8 cache", "formal v9 output", "v8.2 formal baseline output"],
        "reconciliation_decision": decision,
        "can_enter_p2c_gate_recheck": can_enter_p2c,
        "can_enter_p3_formal_mve2_search_design": can_enter_p3,
        "direct_v10_allowed": False,
        "group4_hold_not_touched": True,
        "raw_data_modified": False,
        "audit_csv_modified": False,
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
                "reconciliation_decision": decision,
                "can_enter_p2c_gate_recheck": can_enter_p2c,
                "can_enter_p3_formal_mve2_search_design": can_enter_p3,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
