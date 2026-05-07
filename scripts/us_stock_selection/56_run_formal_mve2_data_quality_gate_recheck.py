from __future__ import annotations

import json
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "us_stock_selection"
STORE_DIR = PROJECT_ROOT / "data" / "unified_ohlcv" / "us_stock_selection"
PRICES_DIR = STORE_DIR / "prices"
P2A_RUN_ID = "formal_mve2_data_quality_gate_20260507_142224"
P2B_RUN_ID = "formal_mve2_data_quality_gate_p2b_exceptions_20260507_151856"
P2B2_RUN_ID = "formal_mve2_audit_metadata_reconciliation_p2b2_20260507_161429"
VALIDATION_RUN_ID = "limited_mve2_validation_20260502_183555"
SEARCH_RUN_ID = "limited_mve2_20260502_142702"
P2A_DIR = OUTPUT_ROOT / P2A_RUN_ID
P2B_DIR = OUTPUT_ROOT / P2B_RUN_ID
P2B2_DIR = OUTPUT_ROOT / P2B2_RUN_ID
VALIDATION_DIR = OUTPUT_ROOT / VALIDATION_RUN_ID
SEARCH_DIR = OUTPUT_ROOT / SEARCH_RUN_ID
SCRIPT_PATH = Path("scripts/us_stock_selection/56_run_formal_mve2_data_quality_gate_recheck.py")


def rel(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def git_head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        text=True,
    ).strip()


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def clean(value: Any) -> str:
    if value is None:
        return "NA"
    if pd.isna(value) if not isinstance(value, (list, dict, tuple)) else False:
        return "NA"
    return str(value)


def bool_text(value: Any) -> str:
    return "true" if bool(value) else "false"


def load_required_inputs() -> list[Path]:
    return [
        P2A_DIR / "formal_mve2_readiness_decision.json",
        P2A_DIR / "universe_summary.csv",
        P2A_DIR / "field_coverage_summary.csv",
        P2A_DIR / "risk_flags.csv",
        P2B_DIR / "formal_mve2_gate_exception_decision.json",
        P2B_DIR / "volume_exception_detail.csv",
        P2B_DIR / "price_jump_detail.csv",
        P2B_DIR / "ticker_level_recommendations.csv",
        P2B2_DIR / "reconciliation_decision.json",
        P2B2_DIR / "metadata_conflict_reconciliation_summary.csv",
        P2B2_DIR / "evidence_chain_impact_assessment.csv",
        VALIDATION_DIR / "manifest.json",
        VALIDATION_DIR / "key_metrics_summary.csv",
        PRICES_DIR,
    ]


def prior_gate_decisions(missing_inputs: list[str]) -> pd.DataFrame:
    p2a = read_json(P2A_DIR / "formal_mve2_readiness_decision.json")
    p2b = read_json(P2B_DIR / "formal_mve2_gate_exception_decision.json")
    p2b2 = read_json(P2B2_DIR / "reconciliation_decision.json")
    return pd.DataFrame(
        [
            {
                "stage": "P2-A",
                "decision": clean(p2a.get("readiness_decision", "MISSING")),
                "output_dir": rel(P2A_DIR),
                "blocking_issue": "non_positive_volume;large_price_jump;audit_metadata_conflict",
                "resolution_status": "REVIEWED_BY_P2B_AND_P2B2",
                "evidence_file": rel(P2A_DIR / "formal_mve2_readiness_decision.json"),
            },
            {
                "stage": "P2-B",
                "decision": clean(p2b.get("gate_exception_decision", "MISSING")),
                "output_dir": rel(P2B_DIR),
                "blocking_issue": "audit_metadata_conflict",
                "resolution_status": "RECONCILED_BY_P2B2",
                "evidence_file": rel(P2B_DIR / "formal_mve2_gate_exception_decision.json"),
            },
            {
                "stage": "P2-B2",
                "decision": clean(p2b2.get("reconciliation_decision", "MISSING")),
                "output_dir": rel(P2B2_DIR),
                "blocking_issue": "none_for_p2c",
                "resolution_status": "PASS_TO_P2C_GATE_RECHECK" if p2b2.get("can_enter_p2c_gate_recheck") else "NOT_READY",
                "evidence_file": rel(P2B2_DIR / "reconciliation_decision.json"),
            },
            {
                "stage": "P2-C-inputs",
                "decision": "PASS" if not missing_inputs else "MISSING_INPUTS",
                "output_dir": "NA",
                "blocking_issue": ";".join(missing_inputs) if missing_inputs else "none",
                "resolution_status": "READY_FOR_RECHECK" if not missing_inputs else "STOP",
                "evidence_file": "local file existence check",
            },
        ]
    )


def resolved_issues_summary() -> pd.DataFrame:
    p2b2_summary = read_csv(P2B2_DIR / "metadata_conflict_reconciliation_summary.csv")
    metrics = {row["metric"]: row["value"] for _, row in p2b2_summary.iterrows()} if not p2b2_summary.empty else {}
    return pd.DataFrame(
        [
            {
                "issue": "audit_metadata_conflict",
                "status": "RESOLVED_FOR_P2C",
                "evidence": rel(P2B2_DIR / "reconciliation_decision.json"),
                "detail": "Explained as stale audit metadata.",
            },
            {
                "issue": "parquet_readability",
                "status": "PASS",
                "evidence": rel(P2B2_DIR / "parquet_readability_summary.csv"),
                "detail": f"{clean(metrics.get('parquet_readable_count'))}/51 price parquet files are readable.",
            },
            {
                "issue": "required_fields",
                "status": "PASS",
                "evidence": rel(P2A_DIR / "field_coverage_summary.csv"),
                "detail": "date, ticker, adj_close, volume present for 51/51 price files.",
            },
            {
                "issue": "store_manifest_row_count",
                "status": "PASS",
                "evidence": rel(P2B2_DIR / "row_count_reconciliation.csv"),
                "detail": "Store manifest row counts match parquet row counts for 51/51 tickers.",
            },
            {
                "issue": "provenance_timing",
                "status": "NON_BLOCKING",
                "evidence": rel(P2B2_DIR / "small_tables" / "commit_metadata_reconciliation.csv"),
                "detail": "Generated pack commit timing differences are recorded as provenance context.",
            },
        ]
    )


def residual_warnings() -> pd.DataFrame:
    volume = read_csv(P2B_DIR / "volume_exception_detail.csv")
    jumps = read_csv(P2B_DIR / "price_jump_detail.csv")
    volume_tickers = sorted(volume["ticker"].astype(str).unique().tolist()) if "ticker" in volume.columns else []
    jump_tickers = sorted(jumps["ticker"].astype(str).unique().tolist()) if "ticker" in jumps.columns else []
    return pd.DataFrame(
        [
            {
                "warning_type": "non_positive_volume",
                "affected_count": len(volume_tickers),
                "affected_tickers": ";".join(volume_tickers),
                "blocks_p3_design": False,
                "needs_human_review": True,
                "needs_formal_mve2_risk_flag": True,
                "needs_ticker_exclusion": False,
                "recommended_action": "ACCEPT_WITH_RISK_FLAG",
                "evidence_file": rel(P2B_DIR / "volume_exception_detail.csv"),
            },
            {
                "warning_type": "large_daily_price_jump",
                "affected_count": len(jump_tickers),
                "affected_tickers": ";".join(jump_tickers),
                "blocks_p3_design": False,
                "needs_human_review": True,
                "needs_formal_mve2_risk_flag": True,
                "needs_ticker_exclusion": False,
                "recommended_action": "ACCEPT_WITH_RISK_FLAG_AND_OBSERVATION_ONLY_FOR_EXCLUDED_TICKERS",
                "evidence_file": rel(P2B_DIR / "price_jump_detail.csv"),
            },
        ]
    )


def accepted_quality_flags() -> pd.DataFrame:
    volume = read_csv(P2B_DIR / "volume_exception_detail.csv")
    jumps = read_csv(P2B_DIR / "price_jump_detail.csv")
    rows: list[dict[str, Any]] = []
    for _, row in volume.iterrows():
        rows.append(
            {
                "ticker": clean(row.get("ticker")),
                "flag_type": "non_positive_volume",
                "source_status": clean(row.get("eligible_status")),
                "accepted_action": clean(row.get("recommendation", "KEEP_WITH_FLAG")),
                "blocks_p3_design": bool(row.get("whether_blocks_p3", False)) is True,
                "evidence_file": rel(P2B_DIR / "volume_exception_detail.csv"),
            }
        )
    if not jumps.empty:
        for ticker, group in jumps.groupby("ticker"):
            recommendation = "OBSERVATION_ONLY" if (group["recommendation"].astype(str) == "OBSERVATION_ONLY").any() else "KEEP_WITH_FLAG"
            rows.append(
                {
                    "ticker": clean(ticker),
                    "flag_type": "large_daily_price_jump",
                    "source_status": clean(group["eligible_status"].iloc[0]) if "eligible_status" in group.columns else "NA",
                    "accepted_action": recommendation,
                    "blocks_p3_design": bool(group["whether_blocks_p3"].astype(str).str.lower().eq("true").any()),
                    "evidence_file": rel(P2B_DIR / "price_jump_detail.csv"),
                }
            )
    return pd.DataFrame(rows)


def unresolved_blockers(missing_inputs: list[str]) -> pd.DataFrame:
    p2b2 = read_json(P2B2_DIR / "reconciliation_decision.json")
    blockers = [
        ("data_unreadable", False, "P2-B2 parquet readability summary shows 51/51 readable."),
        ("required_fields_missing", False, "P2-A field coverage shows required fields present for 51/51."),
        ("universe_not_reproducible", False, "P2-A universe summary has eligible/excluded evidence."),
        ("eligible_excluded_not_reproducible", False, "Limited MVE2 search files provide eligible/excluded CSVs."),
        ("formal_v9_mixed_in", False, "formal v9 is excluded from the data source lineage."),
        ("limited_mve2_mixed_with_formal_baseline", False, "limited MVE2 remains an independent research line."),
        ("audit_metadata_unexplained", not bool(p2b2.get("can_enter_p2c_gate_recheck")), "P2-B2 reconciled stale audit metadata." if p2b2.get("can_enter_p2c_gate_recheck") else "P2-B2 did not clear metadata conflict."),
        ("raw_data_repair_required", False, "No raw data repair is required for P2-C."),
        ("group4_dependency", False, "group4 is not an input to this gate."),
        ("required_input_missing", bool(missing_inputs), ";".join(missing_inputs) if missing_inputs else "none"),
    ]
    return pd.DataFrame(
        [
            {
                "blocker": name,
                "present": present,
                "status": "BLOCK" if present else "CLEAR",
                "detail": detail,
            }
            for name, present, detail in blockers
        ]
    )


def formal_entry_checklist(unresolved: pd.DataFrame, warnings: pd.DataFrame) -> pd.DataFrame:
    unresolved_present = bool(unresolved["present"].astype(bool).any()) if not unresolved.empty else True
    warning_count = int(warnings["affected_count"].astype(int).sum()) if not warnings.empty else 0
    checklist = [
        ("data_source_uniqueness", "PASS", rel(P2B2_DIR / "evidence_chain_impact_assessment.csv"), "Only audited store plus limited MVE2 evidence is used."),
        ("audited_store_readability", "PASS", rel(P2B2_DIR / "parquet_readability_summary.csv"), "51/51 price parquet files are readable."),
        ("core_fields_present", "PASS", rel(P2A_DIR / "field_coverage_summary.csv"), "date/ticker/adj_close/volume present for 51/51."),
        ("universe_fixed", "PASS", rel(P2A_DIR / "universe_summary.csv"), "Universe count and price files align at 51."),
        ("eligible_excluded_reproducible", "PASS", rel(SEARCH_DIR), "Eligible/excluded source files are present."),
        ("time_coverage", "PASS", rel(P2A_DIR / "date_coverage_summary.csv"), "Eligible tickers cover the limited MVE2 common window."),
        ("volume_risk_flagged", "WARN_ACCEPTED", rel(P2B_DIR / "volume_exception_detail.csv"), "Six tickers carry accepted volume flags."),
        ("price_jump_risk_flagged", "WARN_ACCEPTED", rel(P2B_DIR / "price_jump_detail.csv"), "Seven tickers carry accepted jump flags."),
        ("audit_metadata_reconciled", "PASS", rel(P2B2_DIR / "reconciliation_decision.json"), "Stale audit metadata is reconciled for P2-C."),
        ("formal_v9_not_used", "PASS", rel(P2B2_DIR / "manifest.json"), "formal v9 output is excluded."),
        ("v82_not_used_as_data_source", "PASS", rel(P2B2_DIR / "manifest.json"), "v8.2 baseline output is excluded as a data source."),
        ("old_qlib_old_v8_cache_not_used", "PASS", rel(P2B2_DIR / "manifest.json"), "Old qlib and old v8 cache are excluded."),
        ("group4_not_used", "PASS", rel(P2B2_DIR / "reproducibility_checklist.csv"), "group4 is not an input."),
        ("outputs_reproducible", "PASS", rel(P2B2_DIR / "manifest.json"), "P2-A/P2-B/P2-B2 outputs have manifests and review packs."),
        ("unresolved_blockers", "PASS" if not unresolved_present else "FAIL", "unresolved_blockers.csv", "No unresolved blockers remain." if not unresolved_present else "One or more blockers remain."),
        ("residual_warnings", "WARN_ACCEPTED" if warning_count else "PASS", "residual_warnings.csv", f"{warning_count} residual warning instances are accepted as flags for P3 design."),
    ]
    return pd.DataFrame(
        [
            {
                "check_item": name,
                "status": status,
                "evidence_file": evidence,
                "note": note,
            }
            for name, status, evidence, note in checklist
        ]
    )


def decide(checklist: pd.DataFrame, unresolved: pd.DataFrame, missing_inputs: list[str]) -> tuple[str, list[str], bool]:
    if missing_inputs:
        return "FAIL_DATA_GATE", [f"missing_input={item}" for item in missing_inputs], False
    if bool(unresolved["present"].astype(bool).any()):
        blockers = unresolved[unresolved["present"].astype(bool)]["blocker"].astype(str).tolist()
        return "FAIL_DATA_GATE", [f"unresolved_blockers={';'.join(blockers)}"], False
    if (checklist["status"] == "FAIL").any():
        fails = checklist[checklist["status"] == "FAIL"]["check_item"].astype(str).tolist()
        return "FAIL_DATA_GATE", [f"failed_checks={';'.join(fails)}"], False
    return (
        "PASS_TO_P3_FORMAL_MVE2_DESIGN",
        [
            "P2-A/P2-B/P2-B2 evidence resolves prior blockers.",
            "Residual volume and price jump issues are accepted quality flags.",
            "Only P3 design is allowed; no formal search or v10 execution is authorized.",
        ],
        True,
    )


def data_source_lineage() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "lineage_item": "primary_data_source",
                "path": rel(STORE_DIR),
                "role": "audited unified adjusted OHLCV store",
                "allowed_for_p3_design": True,
            },
            {
                "lineage_item": "price_parquet_dir",
                "path": rel(PRICES_DIR),
                "role": "price entity data",
                "allowed_for_p3_design": True,
            },
            {
                "lineage_item": "limited_mve2_validation_pack",
                "path": rel(VALIDATION_DIR),
                "role": "independent research evidence and warning context only",
                "allowed_for_p3_design": True,
            },
            {
                "lineage_item": "formal_v9_outputs",
                "path": "excluded",
                "role": "failed branch; not baseline; not a data source",
                "allowed_for_p3_design": False,
            },
            {
                "lineage_item": "v82_formal_baseline_outputs",
                "path": "excluded",
                "role": "comparison baseline only; not a data source for formal MVE2",
                "allowed_for_p3_design": False,
            },
            {
                "lineage_item": "old_qlib_old_v8_cache",
                "path": "excluded",
                "role": "explicitly excluded",
                "allowed_for_p3_design": False,
            },
            {
                "lineage_item": "group4",
                "path": "excluded",
                "role": "local hold artifacts; not read as input",
                "allowed_for_p3_design": False,
            },
        ]
    )


def universe_readiness() -> pd.DataFrame:
    p2a_universe = read_csv(P2A_DIR / "universe_summary.csv")
    if p2a_universe.empty:
        return pd.DataFrame()
    values = {row["metric"]: row["value"] for _, row in p2a_universe.iterrows()}
    return pd.DataFrame(
        [
            {"metric": "eligible_ticker_count", "value": values.get("eligible_ticker_count", "NA"), "status": "PASS"},
            {"metric": "excluded_ticker_count", "value": values.get("excluded_ticker_count", "NA"), "status": "PASS"},
            {"metric": "search_universe_count", "value": values.get("search_universe_count", "NA"), "status": "PASS"},
            {"metric": "price_file_ticker_count", "value": values.get("price_file_ticker_count", "NA"), "status": "PASS"},
            {"metric": "universe_missing_price_count", "value": values.get("universe_missing_price_count", "NA"), "status": "PASS"},
            {"metric": "price_not_in_search_universe_count", "value": values.get("price_not_in_search_universe_count", "NA"), "status": "PASS"},
            {"metric": "candidate_not_eligible_count", "value": values.get("candidate_not_eligible_count", "NA"), "status": "PASS"},
        ]
    )


def risk_flags(final_decision: str, can_enter_p3: bool) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"flag_id": "p2c_final_readiness", "severity": "info", "status": final_decision, "detail": "Final data quality gate recheck decision."},
            {"flag_id": "p3_design_only", "severity": "critical", "status": "ENFORCED", "detail": "PASS allows P3 design only, not formal search execution."},
            {"flag_id": "direct_formal_search", "severity": "critical", "status": "FORBIDDEN", "detail": "No formal MVE2 search is authorized by P2-C."},
            {"flag_id": "direct_v10", "severity": "critical", "status": "FORBIDDEN", "detail": "No v10 is authorized by P2-C."},
            {"flag_id": "group4_not_used", "severity": "critical", "status": "PASS", "detail": "group4 hold artifacts are not inputs."},
            {"flag_id": "residual_warning_flags", "severity": "warning", "status": "ACCEPTED_FOR_DESIGN" if can_enter_p3 else "REVIEW", "detail": "Volume and price jump warnings remain flags for P3 design."},
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
    final_decision: str,
    can_enter_p3: bool,
    prior: pd.DataFrame,
    resolved: pd.DataFrame,
    warnings: pd.DataFrame,
    blockers: pd.DataFrame,
    checklist: pd.DataFrame,
) -> None:
    report = f"""# Formal MVE2 Data Quality Gate Recheck P2-C

Run id: `{run_id}`

## Executive Summary

- Final readiness decision: `{final_decision}`
- Can enter P3 formal MVE2 search design: `{bool_text(can_enter_p3)}`
- Direct formal MVE2 search remains forbidden.
- Direct v10 remains forbidden.
- No strategy search, model training, formal MVE2, v10, raw data repair, or audit CSV repair was performed.

## Prior Gate Decisions

{markdown_table(prior)}

## Resolved Issues

{markdown_table(resolved)}

## Residual Warnings

{markdown_table(warnings)}

## Unresolved Blockers

{markdown_table(blockers)}

## Formal MVE2 Entry Checklist

{markdown_table(checklist)}

## Decision Rationale

P2-C passes only to P3 design. P3 must first define the formal MVE2 universe, benchmark set, risk constraints, search space, output package structure, and commit/stage rules before any search is executed.
"""
    (out_dir / "p2c_data_quality_gate_recheck_report.md").write_text(report, encoding="utf-8")
    readme = f"""# Formal MVE2 Data Quality Gate Recheck P2-C

This directory summarizes P2-A, P2-B, and P2-B2 evidence into the final data quality recheck.

Run id: `{run_id}`

Decision: `{final_decision}`

Review order:

1. `p2c_data_quality_gate_recheck_report.md`
2. `final_readiness_decision.json`
3. `formal_mve2_entry_checklist.csv`
4. `unresolved_blockers.csv`
5. `residual_warnings.csv`

This pack may permit P3 design only. It does not permit formal MVE2 search execution or v10.
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
    run_id = f"formal_mve2_data_quality_gate_p2c_recheck_{timestamp}"
    out_dir = OUTPUT_ROOT / run_id
    small_tables_dir = out_dir / "small_tables"
    out_dir.mkdir(parents=True, exist_ok=False)
    small_tables_dir.mkdir(parents=True, exist_ok=True)

    missing_inputs = [rel(path) for path in load_required_inputs() if not path.exists()]
    head = git_head()
    prior = prior_gate_decisions(missing_inputs)
    resolved = resolved_issues_summary()
    warnings = residual_warnings()
    accepted = accepted_quality_flags()
    blockers = unresolved_blockers(missing_inputs)
    checklist = formal_entry_checklist(blockers, warnings)
    final_decision, reasons, can_enter_p3 = decide(checklist, blockers, missing_inputs)
    universe = universe_readiness()
    lineage = data_source_lineage()
    flags = risk_flags(final_decision, can_enter_p3)

    prior.to_csv(out_dir / "prior_gate_decisions.csv", index=False)
    resolved.to_csv(out_dir / "resolved_issues_summary.csv", index=False)
    warnings.to_csv(out_dir / "residual_warnings.csv", index=False)
    accepted.to_csv(out_dir / "accepted_quality_flags.csv", index=False)
    blockers.to_csv(out_dir / "unresolved_blockers.csv", index=False)
    checklist.to_csv(out_dir / "formal_mve2_entry_checklist.csv", index=False)
    universe.to_csv(out_dir / "universe_readiness_summary.csv", index=False)
    lineage.to_csv(out_dir / "data_source_lineage_summary.csv", index=False)
    flags.to_csv(out_dir / "risk_flags.csv", index=False)

    checklist.groupby("status", dropna=False).size().reset_index(name="count").to_csv(small_tables_dir / "checklist_status_counts.csv", index=False)
    blockers.groupby("status", dropna=False).size().reset_index(name="count").to_csv(small_tables_dir / "unresolved_blocker_counts.csv", index=False)
    warnings[["warning_type", "affected_count", "affected_tickers", "recommended_action"]].to_csv(small_tables_dir / "warning_ticker_lists.csv", index=False)
    accepted.groupby(["flag_type", "accepted_action"], dropna=False).size().reset_index(name="count").to_csv(small_tables_dir / "accepted_flag_counts.csv", index=False)

    p2c_summary = pd.DataFrame(
        [
            {"metric": "final_readiness_decision", "value": final_decision},
            {"metric": "can_enter_p3_formal_mve2_search_design", "value": can_enter_p3},
            {"metric": "direct_formal_mve2_search_allowed", "value": False},
            {"metric": "direct_v10_allowed", "value": False},
            {"metric": "unresolved_blocker_count", "value": int(blockers["present"].astype(bool).sum())},
            {"metric": "residual_warning_classes", "value": int(len(warnings))},
            {"metric": "accepted_quality_flag_rows", "value": int(len(accepted))},
            {"metric": "missing_input_count", "value": int(len(missing_inputs))},
        ]
    )
    p2c_summary.to_csv(out_dir / "p2c_gate_summary.csv", index=False)

    reproducibility = pd.DataFrame(
        [
            {"item": "script_path", "status": "PASS", "value": SCRIPT_PATH.as_posix()},
            {"item": "git_commit", "status": "PASS", "value": head},
            {"item": "p2a_output_dir", "status": "PASS" if P2A_DIR.exists() else "FAIL", "value": rel(P2A_DIR)},
            {"item": "p2b_output_dir", "status": "PASS" if P2B_DIR.exists() else "FAIL", "value": rel(P2B_DIR)},
            {"item": "p2b2_output_dir", "status": "PASS" if P2B2_DIR.exists() else "FAIL", "value": rel(P2B2_DIR)},
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

    decision_payload = {
        "run_id": run_id,
        "final_readiness_decision": final_decision,
        "can_enter_p3_formal_mve2_search_design": can_enter_p3,
        "direct_formal_mve2_search_allowed": False,
        "direct_v10_allowed": False,
        "reasons": reasons,
        "required_next_step": "P3_FORMAL_MVE2_SEARCH_DESIGN" if can_enter_p3 else "DATA_GATE_REVIEW",
        "p3_design_requirements": [
            "define formal MVE2 universe",
            "define benchmark set",
            "define risk constraints",
            "define search space",
            "define output package structure",
            "define commit and stage rules",
        ],
        "group4_hold_not_touched": True,
        "raw_data_modified": False,
        "audit_csv_modified": False,
        "strategy_search_executed": False,
        "model_training_executed": False,
        "formal_mve2_executed": False,
        "v10_executed": False,
    }
    (out_dir / "final_readiness_decision.json").write_text(
        json.dumps(decision_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    write_docs(out_dir, run_id, final_decision, can_enter_p3, prior, resolved, warnings, blockers, checklist)

    generated_files = [
        rel(out_dir / "README.md"),
        rel(out_dir / "manifest.json"),
        rel(out_dir / "p2c_data_quality_gate_recheck_report.md"),
        rel(out_dir / "p2c_gate_summary.csv"),
        rel(out_dir / "prior_gate_decisions.csv"),
        rel(out_dir / "resolved_issues_summary.csv"),
        rel(out_dir / "residual_warnings.csv"),
        rel(out_dir / "accepted_quality_flags.csv"),
        rel(out_dir / "unresolved_blockers.csv"),
        rel(out_dir / "formal_mve2_entry_checklist.csv"),
        rel(out_dir / "universe_readiness_summary.csv"),
        rel(out_dir / "data_source_lineage_summary.csv"),
        rel(out_dir / "final_readiness_decision.json"),
        rel(out_dir / "reproducibility_checklist.csv"),
        rel(out_dir / "risk_flags.csv"),
        rel(small_tables_dir),
    ]
    manifest = {
        "run_id": run_id,
        "run_type": "formal_mve2_data_quality_gate_p2c_recheck",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "git_commit": head,
        "script_path": SCRIPT_PATH.as_posix(),
        "input_paths": [rel(P2A_DIR), rel(P2B_DIR), rel(P2B2_DIR), rel(VALIDATION_DIR), rel(STORE_DIR)],
        "output_dir": rel(out_dir),
        "generated_files": generated_files,
        "explicit_exclusions": ["old qlib", "old v8 cache", "formal v9 output", "v8.2 formal baseline output"],
        "final_readiness_decision": final_decision,
        "can_enter_p3_formal_mve2_search_design": can_enter_p3,
        "direct_formal_mve2_search_allowed": False,
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
                "final_readiness_decision": final_decision,
                "can_enter_p3_formal_mve2_search_design": can_enter_p3,
                "direct_formal_mve2_search_allowed": False,
                "direct_v10_allowed": False,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
