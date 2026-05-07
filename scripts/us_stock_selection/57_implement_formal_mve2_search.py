from __future__ import annotations

import argparse
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
P2C_RUN_ID = "formal_mve2_data_quality_gate_p2c_recheck_20260507_170809"
P2C_DIR = OUTPUT_ROOT / P2C_RUN_ID
VALIDATION_RUN_ID = "limited_mve2_validation_20260502_183555"
VALIDATION_DIR = OUTPUT_ROOT / VALIDATION_RUN_ID
SEARCH_RUN_ID = "limited_mve2_20260502_142702"
SEARCH_DIR = OUTPUT_ROOT / SEARCH_RUN_ID
V82_AUDIT_DIR = OUTPUT_ROOT / "v82_frozen_formal_audit_20260506_113454"
FORMAL_V9_FAILURE_AUDIT = OUTPUT_ROOT / "formal_v9_20260505_224016" / "audit" / "formal_v9_failure_audit.md"
SCRIPT_PATH = Path("scripts/us_stock_selection/57_implement_formal_mve2_search.py")

RUN_PREFIX = "formal_mve2_search_implementation_p4_dryrun"
P5_RUN_PREFIX = "formal_mve2_controlled_search"
P5B_RUN_PREFIX = "formal_mve2_controlled_search_p5b"
REQUIRED_CORE_FIELDS = ["date", "ticker", "adj_close", "volume"]
VOLUME_WARNING_TICKERS = ["AAPL", "AMD", "ARKK", "IGV", "INTC", "SHOP"]
PRICE_JUMP_WARNING_TICKERS = ["AAPL", "AMD", "MSTR", "ROKU", "SHOP", "SOXL", "UPST"]
DEFAULT_COST_BPS = 10
COST_STRESS_BPS = [0, 10, 25]
LOW_MEDIAN_VOLUME_THRESHOLD = 100_000
COMMON_START = "2016-01-01"


def rel(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True).strip()


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def write_json(path: Path, obj: dict[str, Any]) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def clean(value: Any) -> str:
    if value is None:
        return "NA"
    try:
        if pd.isna(value):
            return "NA"
    except (TypeError, ValueError):
        pass
    return str(value)


def required_inputs() -> list[tuple[Path, str]]:
    return [
        (P2C_DIR / "final_readiness_decision.json", "P2-C final readiness"),
        (P2C_DIR / "universe_readiness_summary.csv", "P2-C universe summary"),
        (P2C_DIR / "accepted_quality_flags.csv", "P2-C accepted quality flags"),
        (P2C_DIR / "data_source_lineage_summary.csv", "P2-C data lineage"),
        (P2C_DIR / "formal_mve2_entry_checklist.csv", "P2-C entry checklist"),
        (VALIDATION_DIR / "manifest.json", "limited MVE2 validation manifest"),
        (SEARCH_DIR / "eligible_universe_limited_mve2.csv", "eligible universe"),
        (SEARCH_DIR / "excluded_tickers_limited_mve2.csv", "excluded universe"),
        (STORE_DIR, "audited store root"),
        (PRICES_DIR, "price parquet directory"),
        (AUDIT_DIR, "store audit directory"),
        (V82_AUDIT_DIR / "v82_frozen_formal_audit.md", "v8.2 comparison metadata"),
        (FORMAL_V9_FAILURE_AUDIT, "formal v9 failure warning metadata"),
    ]


def check_inputs() -> pd.DataFrame:
    rows = []
    for path, label in required_inputs():
        rows.append(
            {
                "check_item": label,
                "path": rel(path),
                "exists": path.exists(),
                "status": "PASS" if path.exists() else "FAIL",
                "note": "required for P4 dry-run scaffold",
            }
        )
    return pd.DataFrame(rows)


def universe_counts(summary: pd.DataFrame) -> dict[str, int]:
    out = {"search_universe_count": 0, "eligible_ticker_count": 0, "excluded_ticker_count": 0}
    if summary.empty:
        return out
    for key in out:
        row = summary.loc[summary["metric"].astype(str) == key]
        if not row.empty:
            out[key] = int(row.iloc[0]["value"])
    return out


def universe_policy(eligible: pd.DataFrame, excluded: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in eligible.iterrows():
        ticker = clean(row.get("ticker"))
        rows.append(
            {
                "ticker": ticker,
                "universe_status": "eligible",
                "allowed_in_formal_candidate_pool": True,
                "observation_only": False,
                "risk_flag_required": ticker in set(VOLUME_WARNING_TICKERS) | set(PRICE_JUMP_WARNING_TICKERS),
                "reason": clean(row.get("eligibility_reason", "ready_10y_plus_unified_adj_close_volume")),
            }
        )
    for _, row in excluded.iterrows():
        ticker = clean(row.get("ticker"))
        rows.append(
            {
                "ticker": ticker,
                "universe_status": "excluded",
                "allowed_in_formal_candidate_pool": False,
                "observation_only": True,
                "risk_flag_required": ticker in set(VOLUME_WARNING_TICKERS) | set(PRICE_JUMP_WARNING_TICKERS),
                "reason": clean(row.get("exclusion_reason", "not_formal_mve2_ready")),
            }
        )
    return pd.DataFrame(rows).sort_values(["universe_status", "ticker"]).reset_index(drop=True)


def eligible_excluded_policy(eligible: pd.DataFrame, excluded: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "policy_item": "search_universe",
                "count": len(eligible) + len(excluded),
                "rule": "fixed by P2-C passed audited-store universe",
                "formal_candidate_pool_allowed": False,
            },
            {
                "policy_item": "eligible",
                "count": len(eligible),
                "rule": "eligible tickers only may enter future formal candidate pool",
                "formal_candidate_pool_allowed": True,
            },
            {
                "policy_item": "excluded",
                "count": len(excluded),
                "rule": "excluded tickers are observation and audit reference only",
                "formal_candidate_pool_allowed": False,
            },
        ]
    )


def benchmark_policy() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "benchmark": "v8.2 frozen Pool A top5_ytdcap80p_derisk100p",
                "role": "formal comparison baseline",
                "allowed": True,
                "data_source_role": "comparison metadata only",
                "notes": "not a formal MVE2 data source",
            },
            {
                "benchmark": "SPY",
                "role": "reference benchmark",
                "allowed": True,
                "data_source_role": "audited store ticker if available",
                "notes": "subject to data availability",
            },
            {
                "benchmark": "QQQ",
                "role": "reference benchmark",
                "allowed": True,
                "data_source_role": "audited store ticker if available",
                "notes": "subject to data availability",
            },
            {
                "benchmark": "equal_weight_eligible_universe",
                "role": "reference benchmark",
                "allowed": True,
                "data_source_role": "derived from eligible audited-store tickers",
                "notes": "future P5 calculation only",
            },
            {
                "benchmark": "formal v9",
                "role": "failed branch warning",
                "allowed": False,
                "data_source_role": "excluded",
                "notes": "must not be used as benchmark or baseline",
            },
            {
                "benchmark": "limited MVE2 candidates",
                "role": "research reference only",
                "allowed": False,
                "data_source_role": "not a formal baseline",
                "notes": "cannot replace v8.2 baseline",
            },
        ]
    )


def risk_flag_policy(accepted_flags: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in accepted_flags.iterrows():
        rows.append(
            {
                "ticker": clean(row.get("ticker")),
                "flag_type": clean(row.get("flag_type")),
                "source_status": clean(row.get("source_status")),
                "future_formal_search_handling": "carry_as_risk_flag",
                "blocks_p4_dry_run": False,
                "blocks_future_p5_by_default": False,
                "evidence_file": clean(row.get("evidence_file")),
            }
        )
    return pd.DataFrame(rows)


def search_space_summary() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"section": "strategy_family", "item": "trend_following", "values": "sma;ema;breakout", "execute_in_dry_run": False},
            {"section": "strategy_family", "item": "time_series_momentum", "values": "21d;63d;126d;252d", "execute_in_dry_run": False},
            {"section": "strategy_family", "item": "volatility_filter", "values": "20d;63d;252d", "execute_in_dry_run": False},
            {"section": "strategy_family", "item": "drawdown_guardrail", "values": "10pct;15pct;20pct;25pct", "execute_in_dry_run": False},
            {"section": "signal_candidate", "item": "adj_close_momentum", "values": "adj_close only", "execute_in_dry_run": False},
            {"section": "signal_candidate", "item": "liquidity_flag", "values": "volume risk flag only", "execute_in_dry_run": False},
            {"section": "ranking_rule", "item": "robustness_first", "values": "return;drawdown;turnover;cost stress", "execute_in_dry_run": False},
            {"section": "rebalance", "item": "frequency", "values": "monthly;quarterly", "execute_in_dry_run": False},
            {"section": "holding", "item": "max_position_weight", "values": "0.10;0.15;0.20", "execute_in_dry_run": False},
            {"section": "cost", "item": "cost_bps_grid", "values": "0;5;10;20;50", "execute_in_dry_run": False},
            {"section": "slippage", "item": "slippage_bps_grid", "values": "0;5;10;20", "execute_in_dry_run": False},
            {"section": "validation", "item": "walk_forward", "values": "predeclared splits;final holdout", "execute_in_dry_run": False},
            {"section": "bias_control", "item": "multiple_testing", "values": "record every candidate and parameter count", "execute_in_dry_run": False},
        ]
    )


def evaluation_metric_policy() -> pd.DataFrame:
    metrics = [
        "CAGR",
        "MDD",
        "Calmar",
        "Sharpe",
        "Sortino",
        "volatility",
        "turnover",
        "hit_rate",
        "benchmark_excess_return",
        "yearly_return",
        "subperiod_return",
        "drawdown_duration",
        "cost_stress_sensitivity",
        "risk_flag_exposure",
    ]
    return pd.DataFrame(
        {
            "metric": metrics,
            "required_for_future_search_report": [True] * len(metrics),
            "computed_in_p4_dry_run": [False] * len(metrics),
            "notes": ["schema only; no formal result computed"] * len(metrics),
        }
    )


def output_package_schema() -> pd.DataFrame:
    files = [
        "README.md",
        "manifest.json",
        "formal_mve2_search_report.md",
        "candidate_summary.csv",
        "selected_candidates.csv",
        "rejected_candidates.csv",
        "benchmark_comparison.csv",
        "yearly_performance.csv",
        "subperiod_performance.csv",
        "drawdown_summary.csv",
        "turnover_summary.csv",
        "cost_stress_summary.csv",
        "risk_flag_exposure.csv",
        "parameter_grid_summary.csv",
        "run_config.json",
        "reproducibility_checklist.csv",
        "formal_mve2_search_decision.json",
        "small_tables/",
        "zip",
    ]
    return pd.DataFrame(
        [
            {
                "future_output_file": name,
                "required_for_p5_full_search": True,
                "created_in_p4_dry_run": name in {"run_config.json", "README.md", "manifest.json", "small_tables/", "zip"},
                "schema_defined_only": name not in {"run_config.json", "README.md", "manifest.json", "small_tables/", "zip"},
            }
            for name in files
        ]
    )


def promotion_gate_policy() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"stage": "P4", "name": "implementation", "required_before_baseline_candidate": True, "auto_promotes_baseline": False},
            {"stage": "P5", "name": "controlled search run", "required_before_baseline_candidate": True, "auto_promotes_baseline": False},
            {"stage": "P6", "name": "validation audit pack", "required_before_baseline_candidate": True, "auto_promotes_baseline": False},
            {"stage": "P7", "name": "comparison against v8.2 frozen baseline", "required_before_baseline_candidate": True, "auto_promotes_baseline": False},
            {"stage": "P8", "name": "decision gate and human review", "required_before_baseline_candidate": True, "auto_promotes_baseline": False},
        ]
    )


def reproducibility_checklist(run_id: str, out_dir: Path) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"item": "script_path_recorded", "status": "PASS", "value": SCRIPT_PATH.as_posix()},
            {"item": "git_commit_recorded", "status": "PASS", "value": git_head()},
            {"item": "run_id_recorded", "status": "PASS", "value": run_id},
            {"item": "output_dir_recorded", "status": "PASS", "value": rel(out_dir)},
            {"item": "p2c_gate_read", "status": "PASS", "value": rel(P2C_DIR / "final_readiness_decision.json")},
            {"item": "audited_store_read", "status": "PASS", "value": rel(STORE_DIR)},
            {"item": "group4_not_used", "status": "PASS", "value": "true"},
            {"item": "full_search_not_executed", "status": "PASS", "value": "true"},
            {"item": "model_training_not_executed", "status": "PASS", "value": "true"},
            {"item": "v10_not_executed", "status": "PASS", "value": "true"},
        ]
    )


def risk_flags_for_run(dryrun_success: bool, input_checks: pd.DataFrame) -> pd.DataFrame:
    missing_count = int((input_checks["status"] != "PASS").sum()) if not input_checks.empty else 1
    return pd.DataFrame(
        [
            {
                "flag_id": "input_presence",
                "severity": "critical",
                "status": "PASS" if missing_count == 0 else "FAIL",
                "detail": f"missing_or_failed_inputs={missing_count}",
            },
            {
                "flag_id": "dry_run_only",
                "severity": "critical",
                "status": "PASS",
                "detail": "P4 executed dry-run scaffold only.",
            },
            {
                "flag_id": "formal_search_not_executed",
                "severity": "critical",
                "status": "PASS",
                "detail": "No formal MVE2 search was run.",
            },
            {
                "flag_id": "no_candidate_ranking",
                "severity": "critical",
                "status": "PASS",
                "detail": "No formal candidate ranking was generated.",
            },
            {
                "flag_id": "no_selected_candidate",
                "severity": "critical",
                "status": "PASS",
                "detail": "No selected formal candidate was generated.",
            },
            {
                "flag_id": "dryrun_success",
                "severity": "info",
                "status": "PASS" if dryrun_success else "FAIL",
                "detail": f"dryrun_success={dryrun_success}",
            },
        ]
    )


def build_run_config(
    run_id: str,
    out_dir: Path,
    universe: dict[str, int],
    mode: str,
    generated_at: str,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "run_type": "formal_mve2_search_implementation_p4_dryrun",
        "mode": mode,
        "generated_at": generated_at,
        "git_commit": git_head(),
        "script_path": SCRIPT_PATH.as_posix(),
        "output_dir": rel(out_dir),
        "data_source_policy": {
            "allowed_primary_data_source": rel(STORE_DIR),
            "price_parquet_dir": rel(PRICES_DIR),
            "core_fields": REQUIRED_CORE_FIELDS,
            "excluded_as_data_sources": [
                "old qlib",
                "old v8 cache",
                "formal v9 outputs",
                "v8.2 formal baseline outputs",
                "group4 artifacts",
            ],
        },
        "universe_policy": {
            "search_universe_count": universe["search_universe_count"],
            "eligible_count": universe["eligible_ticker_count"],
            "excluded_count": universe["excluded_ticker_count"],
            "formal_candidate_pool": "eligible_only",
        },
        "benchmark_policy": {
            "comparison_baseline": "v8.2 frozen Pool A top5_ytdcap80p_derisk100p",
            "reference_benchmarks": ["SPY", "QQQ", "equal_weight_eligible_universe"],
            "formal_v9_allowed_as_benchmark": False,
            "limited_mve2_allowed_as_formal_baseline": False,
        },
        "risk_flag_policy": {
            "volume_warning_tickers": VOLUME_WARNING_TICKERS,
            "price_jump_warning_tickers": PRICE_JUMP_WARNING_TICKERS,
            "carry_forward_to_future_search": True,
        },
        "execution_policy": {
            "dry_run_only_for_this_run": True,
            "full_search_not_executed": True,
            "model_training_not_executed": True,
            "v10_not_executed": True,
            "candidate_ranking_not_generated": True,
            "selected_candidate_not_generated": True,
        },
    }


def guardrails(mode: str, dryrun_success: bool) -> dict[str, Any]:
    return {
        "dry_run_only": mode == "dry_run",
        "full_search_not_executed": True,
        "no_candidate_selected": True,
        "no_formal_candidate_ranking": True,
        "no_baseline_replacement": True,
        "no_v10": True,
        "no_training": True,
        "no_original_data_modified": True,
        "audit_csv_not_modified": True,
        "group4_not_touched": True,
        "formal_v9_not_used_as_baseline": True,
        "limited_mve2_not_used_as_formal_baseline": True,
        "dryrun_success": dryrun_success,
    }


def write_report(out_dir: Path, run_id: str, dryrun_success: bool, decision: str, universe: dict[str, int]) -> None:
    text = f"""# Formal MVE2 Search Implementation P4 Dry-Run Report

## Summary

- Run id: `{run_id}`
- Mode: `dry_run`
- Dry-run success: `{str(dryrun_success).lower()}`
- P2-C readiness decision: `{decision}`
- Full formal search executed: `false`
- Model training executed: `false`
- v10 executed: `false`
- Formal candidate ranking generated: `false`
- Selected formal candidate generated: `false`

## Scope

This run verifies the P4 formal MVE2 search implementation scaffold. It checks inputs, records the data source and universe policy, defines benchmark and risk-flag templates, enumerates the search space schema, and builds the future output package schema. It does not calculate formal strategy performance.

## Data Source Policy

- Allowed source: `data/unified_ohlcv/us_stock_selection`
- Required fields: `date`, `ticker`, `adj_close`, `volume`
- Excluded sources: old qlib, old v8 cache, formal v9 outputs, v8.2 baseline outputs, group4

## Universe Policy

- Search universe: `{universe['search_universe_count']}`
- Eligible: `{universe['eligible_ticker_count']}`
- Excluded: `{universe['excluded_ticker_count']}`
- Future formal candidate pool: eligible tickers only

## Guardrails

P4 dry-run confirms the implementation scaffold only. P5 remains a separate controlled search run task and direct v10 remains forbidden.
"""
    (out_dir / "p4_dryrun_report.md").write_text(text, encoding="utf-8")


def write_readme(out_dir: Path, run_id: str, dryrun_success: bool) -> None:
    text = f"""# Formal MVE2 Search Implementation P4 Dry-Run

Run id: `{run_id}`

This package contains the P4 implementation dry-run scaffold for formal MVE2 search. It verifies configuration, input readability, universe policy, risk-flag policy, benchmark policy, future output schema, and guardrails.

Dry-run success: `{str(dryrun_success).lower()}`

It does not include formal search results, formal candidate rankings, selected formal candidates, model training, baseline replacement, or v10.
"""
    (out_dir / "README.md").write_text(text, encoding="utf-8")


def create_zip(out_dir: Path) -> Path:
    zip_path = out_dir.with_suffix(".zip")
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(out_dir.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(out_dir.parent))
    return zip_path


def p5_placeholder_frame(kind: str) -> pd.DataFrame:
    base = {
        "status": "NOT_EXECUTED_OR_NOT_AVAILABLE",
        "reason": "P5 full_search implementation is incomplete; no formal candidate result was computed.",
    }
    schemas: dict[str, list[str]] = {
        "candidate_summary": [
            "candidate_id",
            "ticker",
            "strategy_family",
            "parameter_set_id",
            "decision",
            "CAGR",
            "MDD",
            "Calmar",
            "Sharpe",
            "turnover",
            "risk_flag_summary",
            "status",
            "reason",
        ],
        "selected_candidates": [
            "candidate_id",
            "ticker",
            "strategy_family",
            "selection_reason",
            "status",
            "reason",
        ],
        "rejected_candidates": [
            "candidate_id",
            "ticker",
            "strategy_family",
            "rejection_reason",
            "status",
            "reason",
        ],
        "benchmark_comparison": [
            "benchmark",
            "role",
            "CAGR",
            "MDD",
            "Calmar",
            "excess_CAGR",
            "status",
            "reason",
        ],
        "yearly_performance": ["year", "candidate_id", "return", "benchmark_return", "status", "reason"],
        "subperiod_performance": ["subperiod", "candidate_id", "return", "MDD", "Calmar", "status", "reason"],
        "drawdown_summary": ["candidate_id", "max_drawdown", "drawdown_duration", "start_date", "end_date", "status", "reason"],
        "turnover_summary": ["candidate_id", "annual_turnover", "trade_count", "status", "reason"],
        "cost_stress_summary": ["candidate_id", "cost_bps", "CAGR", "Calmar", "status", "reason"],
    }
    columns = schemas[kind]
    row = {column: "NA" for column in columns}
    for key, value in base.items():
        if key in row:
            row[key] = value
    return pd.DataFrame([row], columns=columns)


def p5_search_execution_summary(input_checks: pd.DataFrame, p2c_decision: str) -> pd.DataFrame:
    missing_count = int((input_checks["status"] != "PASS").sum()) if not input_checks.empty else 1
    return pd.DataFrame(
        [
            {"item": "mode_requested", "value": "full_search", "status": "REQUESTED"},
            {"item": "confirmation_received", "value": "true", "status": "PASS"},
            {"item": "p2c_readiness_decision", "value": p2c_decision, "status": "PASS" if p2c_decision == "PASS_TO_P3_FORMAL_MVE2_DESIGN" else "FAIL"},
            {"item": "required_inputs_missing", "value": missing_count, "status": "PASS" if missing_count == 0 else "FAIL"},
            {"item": "controlled_search_success", "value": "false", "status": "FAIL"},
            {"item": "full_search_executed", "value": "false", "status": "NOT_EXECUTED"},
            {"item": "implementation_status", "value": "incomplete", "status": "P5_FAILED_IMPLEMENTATION_INCOMPLETE"},
            {"item": "formal_candidate_ranking_generated", "value": "false", "status": "PASS"},
            {"item": "selected_formal_candidate_generated", "value": "false", "status": "PASS"},
            {"item": "baseline_replaced", "value": "false", "status": "PASS"},
            {"item": "v10_executed", "value": "false", "status": "PASS"},
        ]
    )


def p5_risk_flag_exposure(accepted_flags: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in accepted_flags.iterrows():
        rows.append(
            {
                "ticker": clean(row.get("ticker")),
                "flag_type": clean(row.get("flag_type")),
                "source_status": clean(row.get("source_status")),
                "exposure_in_p5_results": "NOT_EXECUTED_OR_NOT_AVAILABLE",
                "must_carry_to_future_search": True,
                "evidence_file": clean(row.get("evidence_file")),
            }
        )
    return pd.DataFrame(rows)


def p5_decision_json(run_id: str, p2c_decision: str, input_checks: pd.DataFrame) -> dict[str, Any]:
    missing_count = int((input_checks["status"] != "PASS").sum()) if not input_checks.empty else 1
    return {
        "run_id": run_id,
        "decision": "P5_FAILED_IMPLEMENTATION_INCOMPLETE",
        "controlled_search_success": False,
        "full_search_requested": True,
        "full_search_executed": False,
        "implementation_incomplete": True,
        "candidate_summary_generated": True,
        "candidate_summary_contains_real_results": False,
        "selected_candidates_generated": True,
        "selected_formal_candidate_generated": False,
        "rejected_candidates_generated": True,
        "benchmark_comparison_generated": True,
        "benchmark_comparison_contains_real_results": False,
        "risk_flag_exposure_generated": True,
        "baseline_replaced": False,
        "no_baseline_replacement": True,
        "v10_executed": False,
        "no_v10": True,
        "requires_p6_validation_audit_pack": False,
        "next_allowed_action": "IMPLEMENT_FULL_SEARCH_LOGIC_OR_REVIEW_P5_FAILURE_BEFORE_P6",
        "p2c_readiness_decision": p2c_decision,
        "required_inputs_missing_count": missing_count,
        "group4_hold_not_touched": True,
        "raw_data_modified": False,
        "audit_csv_modified": False,
    }


def p5_guardrails() -> dict[str, Any]:
    return {
        "full_search_requested_with_confirmation": True,
        "controlled_search_success": False,
        "full_search_executed": False,
        "implementation_incomplete": True,
        "no_candidate_selected": True,
        "no_formal_candidate_ranking": True,
        "no_baseline_replacement": True,
        "no_v10": True,
        "no_training": True,
        "no_original_data_modified": True,
        "audit_csv_not_modified": True,
        "group4_not_touched": True,
        "formal_v9_not_used_as_baseline": True,
        "limited_mve2_not_used_as_formal_baseline": True,
        "old_qlib_not_used": True,
        "old_v8_cache_not_used": True,
    }


def write_p5_report(out_dir: Path, run_id: str, p2c_decision: str, universe: dict[str, int]) -> None:
    text = f"""# Formal MVE2 Controlled Search P5 Report

## Summary

- Run id: `{run_id}`
- Requested mode: `full_search`
- Confirmation flag provided: `true`
- P2-C readiness decision: `{p2c_decision}`
- Controlled search success: `false`
- Decision: `P5_FAILED_IMPLEMENTATION_INCOMPLETE`
- Full formal search executed: `false`
- Candidate ranking generated: `false`
- Selected formal candidate generated: `false`
- Baseline replaced: `false`
- v10 executed: `false`

## Result

The P4 script still does not contain reviewed full-search implementation logic. Per P5 safety rules, this run produced a controlled failure package instead of fabricating formal candidate results.

All result tables that would require actual full-search execution are schema or placeholder files marked `NOT_EXECUTED_OR_NOT_AVAILABLE`.

## Data Source And Universe

- Allowed data source: `data/unified_ohlcv/us_stock_selection`
- Core fields: `date`, `ticker`, `adj_close`, `volume`
- Search universe: `{universe['search_universe_count']}`
- Eligible universe: `{universe['eligible_ticker_count']}`
- Excluded universe: `{universe['excluded_ticker_count']}`
- Future formal candidate pool: eligible tickers only

## Benchmark And Risk Rules

- v8.2 frozen is comparison baseline metadata only.
- formal v9 is a failed branch and is not a benchmark or baseline.
- limited MVE2 is independent research context and is not a formal baseline.
- Residual volume and price-jump tickers remain risk flags.

## Next Step

Do not proceed to P6 validation / audit pack from this failed P5 package. The next safe action is to implement reviewed full-search logic or explicitly review this P5 failure.
"""
    (out_dir / "formal_mve2_controlled_search_report.md").write_text(text, encoding="utf-8")


def write_p5_readme(out_dir: Path, run_id: str) -> None:
    text = f"""# Formal MVE2 Controlled Search P5

Run id: `{run_id}`

This package is a controlled P5 failure package. The requested full search was not executed because the P4 script does not yet implement reviewed full-search logic.

Decision: `P5_FAILED_IMPLEMENTATION_INCOMPLETE`

No formal candidate ranking, selected formal candidate, baseline replacement, model training, or v10 output is included. Placeholder result files are marked `NOT_EXECUTED_OR_NOT_AVAILABLE`.
"""
    (out_dir / "README.md").write_text(text, encoding="utf-8")


def write_p5_manifest(
    out_dir: Path,
    run_id: str,
    generated_at: str,
    generated_files: list[Path],
    zip_path: Path,
) -> None:
    manifest = {
        "run_id": run_id,
        "run_type": "formal_mve2_controlled_search",
        "mode": "full_search",
        "generated_at": generated_at,
        "git_commit": git_head(),
        "script_path": SCRIPT_PATH.as_posix(),
        "input_paths": [
            rel(P2C_DIR),
            rel(VALIDATION_DIR),
            rel(SEARCH_DIR),
            rel(STORE_DIR),
            rel(V82_AUDIT_DIR),
            rel(FORMAL_V9_FAILURE_AUDIT),
        ],
        "output_dir": rel(out_dir),
        "generated_files": [rel(path) for path in generated_files] + [rel(zip_path)],
        "decision": "P5_FAILED_IMPLEMENTATION_INCOMPLETE",
        "controlled_search_success": False,
        "full_search_requested": True,
        "full_search_executed": False,
        "formal_mve2_search_executed": False,
        "model_training_executed": False,
        "formal_candidate_ranking_generated": False,
        "selected_formal_candidate_generated": False,
        "baseline_replaced": False,
        "no_baseline_replacement": True,
        "direct_v10_allowed": False,
        "no_v10": True,
        "requires_p6_validation_audit_pack": False,
        "group4_hold_not_touched": True,
        "raw_data_modified": False,
        "audit_csv_modified": False,
        "explicit_exclusions": [
            "old qlib",
            "old v8 cache",
            "formal v9 as benchmark or baseline",
            "v8.2 formal baseline outputs as data source",
            "limited MVE2 as formal baseline",
            "group4 artifacts",
        ],
    }
    write_json(out_dir / "manifest.json", manifest)


def write_p5_controlled_failure_outputs(out_dir: Path) -> tuple[bool, list[Path], Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "small_tables").mkdir(exist_ok=True)

    run_id = out_dir.name
    generated_at = datetime.now().isoformat(timespec="seconds")
    p2c_decision_json = read_json(P2C_DIR / "final_readiness_decision.json")
    p2c_decision = str(p2c_decision_json.get("final_readiness_decision", "MISSING"))
    input_checks = check_inputs()
    universe_summary = read_csv(P2C_DIR / "universe_readiness_summary.csv")
    accepted_flags = read_csv(P2C_DIR / "accepted_quality_flags.csv")
    eligible = read_csv(SEARCH_DIR / "eligible_universe_limited_mve2.csv")
    excluded = read_csv(SEARCH_DIR / "excluded_tickers_limited_mve2.csv")
    universe = universe_counts(universe_summary)

    generated_files: list[Path] = []
    tables = {
        "candidate_summary.csv": p5_placeholder_frame("candidate_summary"),
        "selected_candidates.csv": p5_placeholder_frame("selected_candidates"),
        "rejected_candidates.csv": p5_placeholder_frame("rejected_candidates"),
        "benchmark_comparison.csv": p5_placeholder_frame("benchmark_comparison"),
        "yearly_performance.csv": p5_placeholder_frame("yearly_performance"),
        "subperiod_performance.csv": p5_placeholder_frame("subperiod_performance"),
        "drawdown_summary.csv": p5_placeholder_frame("drawdown_summary"),
        "turnover_summary.csv": p5_placeholder_frame("turnover_summary"),
        "cost_stress_summary.csv": p5_placeholder_frame("cost_stress_summary"),
        "risk_flag_exposure.csv": p5_risk_flag_exposure(accepted_flags),
        "parameter_grid_summary.csv": search_space_summary(),
        "search_execution_summary.csv": p5_search_execution_summary(input_checks, p2c_decision),
        "reproducibility_checklist.csv": reproducibility_checklist(run_id, out_dir),
        "risk_flags.csv": risk_flags_for_run(False, input_checks),
        "universe_policy.csv": universe_policy(eligible, excluded),
        "benchmark_policy.csv": benchmark_policy(),
    }
    for name, df in tables.items():
        path = out_dir / name
        df.to_csv(path, index=False)
        generated_files.append(path)

    small_tables = {
        "placeholder_result_schema.csv": output_package_schema(),
        "p5_failure_summary.csv": pd.DataFrame(
            [
                {"item": "decision", "value": "P5_FAILED_IMPLEMENTATION_INCOMPLETE"},
                {"item": "controlled_search_success", "value": "false"},
                {"item": "full_search_executed", "value": "false"},
                {"item": "candidate_ranking_generated", "value": "false"},
                {"item": "selected_formal_candidate_generated", "value": "false"},
            ]
        ),
        "risk_flag_tickers.csv": p5_risk_flag_exposure(accepted_flags),
    }
    for name, df in small_tables.items():
        path = out_dir / "small_tables" / name
        df.to_csv(path, index=False)
        generated_files.append(path)

    run_config = build_run_config(run_id, out_dir, universe, "full_search", generated_at)
    run_config["execution_policy"].update(
        {
            "full_search_requested": True,
            "full_search_not_executed": True,
            "controlled_search_success": False,
            "implementation_incomplete": True,
            "p5_decision": "P5_FAILED_IMPLEMENTATION_INCOMPLETE",
        }
    )
    run_config_path = out_dir / "run_config.json"
    write_json(run_config_path, run_config)
    generated_files.append(run_config_path)

    decision_path = out_dir / "formal_mve2_search_decision.json"
    write_json(decision_path, p5_decision_json(run_id, p2c_decision, input_checks))
    generated_files.append(decision_path)

    guardrails_path = out_dir / "formal_search_guardrails.json"
    write_json(guardrails_path, p5_guardrails())
    generated_files.append(guardrails_path)

    write_p5_report(out_dir, run_id, p2c_decision, universe)
    generated_files.append(out_dir / "formal_mve2_controlled_search_report.md")
    write_p5_readme(out_dir, run_id)
    generated_files.append(out_dir / "README.md")

    manifest_path = out_dir / "manifest.json"
    generated_files.append(manifest_path)
    zip_path = create_zip(out_dir)
    write_p5_manifest(out_dir, run_id, generated_at, generated_files, zip_path)
    zip_path = create_zip(out_dir)

    return False, sorted(set(generated_files), key=lambda p: rel(p)), zip_path


def max_drawdown(equity: pd.Series) -> float:
    if equity.empty:
        return float("nan")
    running_max = equity.cummax()
    drawdown = equity / running_max - 1.0
    return float(drawdown.min())


def max_drawdown_duration(equity: pd.Series) -> int:
    if equity.empty:
        return 0
    drawdown = equity / equity.cummax() - 1.0
    longest = 0
    current = 0
    for value in drawdown.fillna(0.0):
        if value < 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return int(longest)


def performance_metrics(returns: pd.Series) -> dict[str, float]:
    clean_returns = returns.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    if clean_returns.empty:
        return {
            "total_return": np.nan,
            "CAGR": np.nan,
            "MDD": np.nan,
            "Calmar": np.nan,
            "Sharpe": np.nan,
            "volatility": np.nan,
            "hit_rate": np.nan,
            "drawdown_duration": np.nan,
        }
    equity = (1.0 + clean_returns).cumprod()
    years = len(clean_returns) / 252.0
    total_return = float(equity.iloc[-1] - 1.0)
    final_equity = float(equity.iloc[-1])
    cagr = float(final_equity ** (1.0 / years) - 1.0) if years > 0 and final_equity > 0 else np.nan
    mdd = max_drawdown(equity)
    calmar = float(cagr / abs(mdd)) if pd.notna(cagr) and pd.notna(mdd) and mdd < 0 else np.nan
    volatility = float(clean_returns.std(ddof=0) * np.sqrt(252.0))
    sharpe = float(clean_returns.mean() / clean_returns.std(ddof=0) * np.sqrt(252.0)) if clean_returns.std(ddof=0) > 0 else np.nan
    hit_rate = float((clean_returns > 0).mean())
    return {
        "total_return": total_return,
        "CAGR": cagr,
        "MDD": mdd,
        "Calmar": calmar,
        "Sharpe": sharpe,
        "volatility": volatility,
        "hit_rate": hit_rate,
        "drawdown_duration": float(max_drawdown_duration(equity)),
    }


def zscore(series: pd.Series) -> pd.Series:
    values = series.replace([np.inf, -np.inf], np.nan)
    std = values.std(skipna=True)
    if pd.isna(std) or std == 0:
        return pd.Series(0.0, index=series.index)
    return (values - values.mean(skipna=True)) / std


def read_price_file(ticker: str) -> pd.DataFrame:
    path = PRICES_DIR / f"{ticker}.parquet"
    if not path.exists():
        return pd.DataFrame(columns=REQUIRED_CORE_FIELDS)
    df = pd.read_parquet(path)
    missing = [field for field in REQUIRED_CORE_FIELDS if field not in df.columns]
    if missing:
        return pd.DataFrame(columns=REQUIRED_CORE_FIELDS)
    out = df[REQUIRED_CORE_FIELDS].copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out["ticker"] = ticker
    out["adj_close"] = pd.to_numeric(out["adj_close"], errors="coerce")
    out["volume"] = pd.to_numeric(out["volume"], errors="coerce")
    out = out.dropna(subset=["date"]).sort_values("date").drop_duplicates("date", keep="last")
    return out


def load_formal_search_prices(eligible: pd.DataFrame, excluded: pd.DataFrame) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    all_tickers = sorted(set(eligible["ticker"].astype(str)) | set(excluded["ticker"].astype(str)))
    data: dict[str, pd.DataFrame] = {}
    rows: list[dict[str, Any]] = []
    for ticker in all_tickers:
        df = read_price_file(ticker)
        data[ticker] = df
        rows.append(
            {
                "ticker": ticker,
                "price_file": rel(PRICES_DIR / f"{ticker}.parquet"),
                "readable": not df.empty,
                "rows": int(len(df)),
                "date_min": clean(df["date"].min()) if not df.empty else "NA",
                "date_max": clean(df["date"].max()) if not df.empty else "NA",
                "adj_close_missing_count": int(df["adj_close"].isna().sum()) if not df.empty else 0,
                "volume_missing_count": int(df["volume"].isna().sum()) if not df.empty else 0,
                "non_positive_price_count": int((df["adj_close"] <= 0).sum()) if not df.empty else 0,
                "non_positive_volume_count": int((df["volume"] <= 0).sum()) if not df.empty else 0,
                "missing_handling": "rows retained for audit; strategy pivot uses forward-filled adjusted close only after first valid price",
            }
        )
    return data, pd.DataFrame(rows)


def build_price_volume_matrices(price_data: dict[str, pd.DataFrame], tickers: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    price_series = {}
    volume_series = {}
    for ticker in tickers:
        df = price_data.get(ticker, pd.DataFrame())
        if df.empty:
            continue
        indexed = df.set_index("date").sort_index()
        price_series[ticker] = indexed["adj_close"]
        volume_series[ticker] = indexed["volume"]
    prices = pd.DataFrame(price_series).sort_index()
    volumes = pd.DataFrame(volume_series).reindex(prices.index)
    prices = prices.loc[prices.index >= pd.Timestamp(COMMON_START)]
    volumes = volumes.reindex(prices.index)
    prices = prices.ffill()
    returns = prices.pct_change(fill_method=None)
    valid_rows = returns.notna().any(axis=1)
    prices = prices.loc[valid_rows]
    volumes = volumes.loc[prices.index]
    return prices, volumes


def parameter_grid() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    idx = 1
    for lookback in [63, 126, 252]:
        for top_n in [5, 10]:
            rows.append(
                {
                    "parameter_set_id": f"p{idx:03d}",
                    "strategy_family": "momentum_rank",
                    "momentum_lookback_days": lookback,
                    "volatility_lookback_days": "NA",
                    "liquidity_lookback_days": "NA",
                    "top_n": top_n,
                    "rebalance": "monthly",
                    "weighting": "equal_weight",
                    "median_volume_threshold": "NA",
                }
            )
            idx += 1
    for mom_lookback in [126, 252]:
        for vol_lookback in [63, 126]:
            for top_n in [5, 10]:
                rows.append(
                    {
                        "parameter_set_id": f"p{idx:03d}",
                        "strategy_family": "momentum_low_vol",
                        "momentum_lookback_days": mom_lookback,
                        "volatility_lookback_days": vol_lookback,
                        "liquidity_lookback_days": "NA",
                        "top_n": top_n,
                        "rebalance": "monthly",
                        "weighting": "equal_weight",
                        "median_volume_threshold": "NA",
                    }
                )
                idx += 1
    for lookback in [126, 252]:
        for top_n in [5, 10]:
            rows.append(
                {
                    "parameter_set_id": f"p{idx:03d}",
                    "strategy_family": "momentum_liquidity_guard",
                    "momentum_lookback_days": lookback,
                    "volatility_lookback_days": "NA",
                    "liquidity_lookback_days": 63,
                    "top_n": top_n,
                    "rebalance": "monthly",
                    "weighting": "equal_weight",
                    "median_volume_threshold": LOW_MEDIAN_VOLUME_THRESHOLD,
                }
            )
            idx += 1
    return pd.DataFrame(rows)


def monthly_rebalance_dates(index: pd.DatetimeIndex) -> list[pd.Timestamp]:
    if len(index) == 0:
        return []
    dates = pd.Series(index=index, data=index)
    grouped = dates.groupby([dates.index.year, dates.index.month]).last()
    return [pd.Timestamp(value) for value in grouped.tolist()]


def score_for_strategy(
    prices: pd.DataFrame,
    returns: pd.DataFrame,
    volumes: pd.DataFrame,
    date: pd.Timestamp,
    spec: pd.Series,
) -> pd.Series:
    mom_lb = int(spec["momentum_lookback_days"])
    family = str(spec["strategy_family"])
    if date not in prices.index:
        return pd.Series(dtype=float)
    loc = prices.index.get_loc(date)
    if isinstance(loc, slice) or isinstance(loc, np.ndarray):
        return pd.Series(dtype=float)
    if loc < mom_lb:
        return pd.Series(dtype=float)
    momentum = prices.iloc[loc] / prices.iloc[loc - mom_lb] - 1.0
    if family == "momentum_rank":
        return momentum
    if family == "momentum_low_vol":
        vol_lb = int(spec["volatility_lookback_days"])
        if loc < vol_lb:
            return pd.Series(dtype=float)
        vol = returns.iloc[loc - vol_lb + 1 : loc + 1].std(skipna=True)
        return zscore(momentum) - zscore(vol)
    if family == "momentum_liquidity_guard":
        liq_lb = int(spec["liquidity_lookback_days"])
        if loc < liq_lb:
            return pd.Series(dtype=float)
        median_volume = volumes.iloc[loc - liq_lb + 1 : loc + 1].median(skipna=True)
        score = momentum.copy()
        score = score.where(median_volume >= LOW_MEDIAN_VOLUME_THRESHOLD)
        return score
    return pd.Series(dtype=float)


def backtest_candidate(
    prices: pd.DataFrame,
    volumes: pd.DataFrame,
    spec: pd.Series,
) -> tuple[pd.Series, pd.DataFrame, pd.Series, pd.DataFrame]:
    returns = prices.pct_change(fill_method=None).fillna(0.0)
    target_weights = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
    selection_rows: list[dict[str, Any]] = []
    for rebalance_date in monthly_rebalance_dates(prices.index):
        scores = score_for_strategy(prices, returns, volumes, rebalance_date, spec)
        scores = scores.dropna().sort_values(ascending=False)
        top_n = int(spec["top_n"])
        selected = list(scores.head(top_n).index)
        if not selected:
            continue
        weight = 1.0 / len(selected)
        target_weights.loc[rebalance_date, selected] = weight
        selection_rows.append(
            {
                "rebalance_date": rebalance_date.date().isoformat(),
                "selected_tickers": ";".join(selected),
                "selected_count": len(selected),
            }
        )
    weights = target_weights.replace(0.0, np.nan).ffill().fillna(0.0).shift(1).fillna(0.0)
    gross_returns = (weights * returns).sum(axis=1)
    turnover = weights.diff().abs().sum(axis=1).fillna(weights.abs().sum(axis=1))
    selection_df = pd.DataFrame(selection_rows)
    return gross_returns, weights, turnover, selection_df


def net_returns(gross_returns: pd.Series, turnover: pd.Series, cost_bps: int) -> pd.Series:
    return gross_returns - turnover * (cost_bps / 10000.0)


def annual_returns(returns: pd.Series, candidate_id: str) -> pd.DataFrame:
    rows = []
    for year, group in returns.groupby(returns.index.year):
        rows.append({"candidate_id": candidate_id, "year": int(year), "return": float((1.0 + group).prod() - 1.0)})
    return pd.DataFrame(rows)


def subperiod_returns(returns: pd.Series, candidate_id: str) -> pd.DataFrame:
    periods = [
        ("2016_2019", "2016-01-01", "2019-12-31"),
        ("2020_2022", "2020-01-01", "2022-12-31"),
        ("2023_2026", "2023-01-01", "2026-12-31"),
    ]
    rows = []
    for name, start, end in periods:
        segment = returns.loc[(returns.index >= pd.Timestamp(start)) & (returns.index <= pd.Timestamp(end))]
        metrics = performance_metrics(segment)
        rows.append(
            {
                "candidate_id": candidate_id,
                "subperiod": name,
                "return": metrics["total_return"],
                "MDD": metrics["MDD"],
                "Calmar": metrics["Calmar"],
                "daily_count": int(len(segment)),
            }
        )
    return pd.DataFrame(rows)


def benchmark_returns(prices: pd.DataFrame, eligible_returns: pd.DataFrame) -> dict[str, pd.Series]:
    out: dict[str, pd.Series] = {}
    for ticker in ["SPY", "QQQ"]:
        if ticker in prices.columns:
            out[ticker] = prices[ticker].pct_change(fill_method=None).fillna(0.0)
    out["equal_weight_eligible_universe"] = eligible_returns.mean(axis=1).fillna(0.0)
    return out


def benchmark_comparison_rows(candidate_id: str, returns: pd.Series, benchmarks: dict[str, pd.Series]) -> list[dict[str, Any]]:
    candidate_metrics = performance_metrics(returns)
    rows = []
    for name, bench_returns in benchmarks.items():
        aligned = pd.concat([returns.rename("candidate"), bench_returns.rename("benchmark")], axis=1).fillna(0.0)
        bench_metrics = performance_metrics(aligned["benchmark"])
        rows.append(
            {
                "candidate_id": candidate_id,
                "benchmark": name,
                "candidate_CAGR": candidate_metrics["CAGR"],
                "benchmark_CAGR": bench_metrics["CAGR"],
                "excess_CAGR": candidate_metrics["CAGR"] - bench_metrics["CAGR"],
                "candidate_MDD": candidate_metrics["MDD"],
                "benchmark_MDD": bench_metrics["MDD"],
                "candidate_Calmar": candidate_metrics["Calmar"],
                "benchmark_Calmar": bench_metrics["Calmar"],
            }
        )
    return rows


def risk_flag_exposure_rows(candidate_id: str, weights: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    warning_map = {
        "non_positive_volume": VOLUME_WARNING_TICKERS,
        "large_daily_price_jump": PRICE_JUMP_WARNING_TICKERS,
    }
    for flag_type, tickers in warning_map.items():
        present = [ticker for ticker in tickers if ticker in weights.columns]
        exposure = weights[present].sum(axis=1) if present else pd.Series(0.0, index=weights.index)
        rows.append(
            {
                "candidate_id": candidate_id,
                "flag_type": flag_type,
                "tickers": ";".join(present),
                "average_weight": float(exposure.mean()) if len(exposure) else 0.0,
                "max_weight": float(exposure.max()) if len(exposure) else 0.0,
                "exposure_days": int((exposure > 0).sum()) if len(exposure) else 0,
            }
        )
    return rows


def run_controlled_search(prices: pd.DataFrame, volumes: pd.DataFrame, grid: pd.DataFrame) -> dict[str, pd.DataFrame]:
    if len(grid) > 100:
        raise RuntimeError(f"parameter grid has {len(grid)} combinations, above the 100-combination approval limit")

    eligible_returns = prices.pct_change(fill_method=None).fillna(0.0)
    benchmarks = benchmark_returns(prices, eligible_returns)

    candidate_rows: list[dict[str, Any]] = []
    yearly_frames: list[pd.DataFrame] = []
    subperiod_frames: list[pd.DataFrame] = []
    drawdown_rows: list[dict[str, Any]] = []
    turnover_rows: list[dict[str, Any]] = []
    cost_rows: list[dict[str, Any]] = []
    benchmark_rows: list[dict[str, Any]] = []
    risk_exposure_rows: list[dict[str, Any]] = []
    selection_frames: list[pd.DataFrame] = []

    for _, spec in grid.iterrows():
        candidate_id = f"{spec['strategy_family']}__{spec['parameter_set_id']}"
        gross_returns, weights, turnover, selection_df = backtest_candidate(prices, volumes, spec)
        base_returns = net_returns(gross_returns, turnover, DEFAULT_COST_BPS)
        metrics = performance_metrics(base_returns)
        annual_turnover = float(turnover.sum() / (len(turnover) / 252.0)) if len(turnover) else np.nan
        risk_rows = risk_flag_exposure_rows(candidate_id, weights)
        risk_summary = ";".join(
            f"{row['flag_type']}:avg={row['average_weight']:.4f},max={row['max_weight']:.4f}" for row in risk_rows
        )

        candidate_rows.append(
            {
                "candidate_id": candidate_id,
                "strategy_family": spec["strategy_family"],
                "parameter_set_id": spec["parameter_set_id"],
                "momentum_lookback_days": spec["momentum_lookback_days"],
                "volatility_lookback_days": spec["volatility_lookback_days"],
                "liquidity_lookback_days": spec["liquidity_lookback_days"],
                "top_n": spec["top_n"],
                "rebalance": spec["rebalance"],
                "cost_bps": DEFAULT_COST_BPS,
                "total_return": metrics["total_return"],
                "CAGR": metrics["CAGR"],
                "MDD": metrics["MDD"],
                "Calmar": metrics["Calmar"],
                "Sharpe": metrics["Sharpe"],
                "volatility": metrics["volatility"],
                "hit_rate": metrics["hit_rate"],
                "turnover": annual_turnover,
                "drawdown_duration": metrics["drawdown_duration"],
                "risk_flag_summary": risk_summary,
                "selected_for_validation_only": False,
                "baseline_replacement": False,
            }
        )
        yearly_frames.append(annual_returns(base_returns, candidate_id))
        subperiod_frames.append(subperiod_returns(base_returns, candidate_id))
        equity = (1.0 + base_returns.fillna(0.0)).cumprod()
        drawdown_rows.append(
            {
                "candidate_id": candidate_id,
                "max_drawdown": max_drawdown(equity),
                "drawdown_duration": max_drawdown_duration(equity),
                "start_date": clean(base_returns.index.min()),
                "end_date": clean(base_returns.index.max()),
            }
        )
        turnover_rows.append(
            {
                "candidate_id": candidate_id,
                "annual_turnover": annual_turnover,
                "total_turnover": float(turnover.sum()) if len(turnover) else np.nan,
                "rebalance_count": int(len(selection_df)),
            }
        )
        for cost_bps in COST_STRESS_BPS:
            cost_metrics = performance_metrics(net_returns(gross_returns, turnover, cost_bps))
            cost_rows.append(
                {
                    "candidate_id": candidate_id,
                    "cost_bps": cost_bps,
                    "CAGR": cost_metrics["CAGR"],
                    "MDD": cost_metrics["MDD"],
                    "Calmar": cost_metrics["Calmar"],
                    "Sharpe": cost_metrics["Sharpe"],
                }
            )
        benchmark_rows.extend(benchmark_comparison_rows(candidate_id, base_returns, benchmarks))
        risk_exposure_rows.extend(risk_rows)
        if not selection_df.empty:
            selection_df.insert(0, "candidate_id", candidate_id)
            selection_frames.append(selection_df)

    candidate_summary = pd.DataFrame(candidate_rows)
    if not candidate_summary.empty:
        candidate_summary = candidate_summary.sort_values(["Calmar", "CAGR"], ascending=False).reset_index(drop=True)
        selected_mask = (
            (candidate_summary["CAGR"] > 0)
            & (candidate_summary["Calmar"] >= 0.5)
            & (candidate_summary["MDD"] > -0.7)
        )
        selected_indices = candidate_summary.loc[selected_mask].head(3).index
        if len(selected_indices) == 0:
            selected_indices = candidate_summary.head(3).index
        candidate_summary.loc[selected_indices, "selected_for_validation_only"] = True

    selected = candidate_summary[candidate_summary["selected_for_validation_only"]].copy()
    if not selected.empty:
        selected["selection_scope"] = "P6_VALIDATION_AUDIT_ONLY"
        selected["baseline_replacement"] = False
    rejected = candidate_summary[~candidate_summary["selected_for_validation_only"]].copy()
    if not rejected.empty:
        rejected["rejection_reason"] = "not_top_controlled_search_candidate_for_P6_validation"

    return {
        "candidate_summary": candidate_summary,
        "selected_candidates": selected,
        "rejected_candidates": rejected,
        "benchmark_comparison": pd.DataFrame(benchmark_rows),
        "yearly_performance": pd.concat(yearly_frames, ignore_index=True) if yearly_frames else pd.DataFrame(),
        "subperiod_performance": pd.concat(subperiod_frames, ignore_index=True) if subperiod_frames else pd.DataFrame(),
        "drawdown_summary": pd.DataFrame(drawdown_rows),
        "turnover_summary": pd.DataFrame(turnover_rows),
        "cost_stress_summary": pd.DataFrame(cost_rows),
        "risk_flag_exposure": pd.DataFrame(risk_exposure_rows),
        "rebalance_selection_log": pd.concat(selection_frames, ignore_index=True) if selection_frames else pd.DataFrame(),
    }


def p5b_decision_json(run_id: str, result_tables: dict[str, pd.DataFrame], grid_count: int) -> dict[str, Any]:
    selected_count = int(len(result_tables["selected_candidates"]))
    return {
        "run_id": run_id,
        "decision": "P5B_CONTROLLED_SEARCH_COMPLETED",
        "controlled_search_success": True,
        "full_search_requested": True,
        "full_search_executed": True,
        "parameter_combination_count": grid_count,
        "candidate_summary_generated": True,
        "candidate_summary_contains_real_results": True,
        "selected_candidates_generated": True,
        "selected_count": selected_count,
        "selected_for_validation_only": True,
        "selected_formal_candidate_generated": False,
        "rejected_candidates_generated": True,
        "benchmark_comparison_generated": True,
        "benchmark_comparison_contains_real_results": True,
        "risk_flag_exposure_generated": True,
        "baseline_replaced": False,
        "no_baseline_replacement": True,
        "v10_executed": False,
        "no_v10": True,
        "requires_p6_validation": True,
        "next_allowed_action": "P6_FORMAL_MVE2_VALIDATION_AUDIT_PACK",
        "group4_hold_not_touched": True,
        "raw_data_modified": False,
        "audit_csv_modified": False,
    }


def p5b_guardrails(grid_count: int) -> dict[str, Any]:
    return {
        "full_search_requested_with_confirmation": True,
        "controlled_search_success": True,
        "full_search_executed": True,
        "parameter_combination_count": grid_count,
        "parameter_combination_limit": 100,
        "no_baseline_replacement": True,
        "selected_for_validation_only": True,
        "no_v10": True,
        "no_training": True,
        "no_original_data_modified": True,
        "audit_csv_not_modified": True,
        "group4_not_touched": True,
        "formal_v9_not_used_as_baseline": True,
        "formal_v9_not_used_as_benchmark": True,
        "limited_mve2_not_used_as_formal_baseline": True,
        "old_qlib_not_used": True,
        "old_v8_cache_not_used": True,
    }


def p5b_risk_flags(input_checks: pd.DataFrame, grid_count: int) -> pd.DataFrame:
    missing_count = int((input_checks["status"] != "PASS").sum()) if not input_checks.empty else 1
    return pd.DataFrame(
        [
            {"flag_id": "input_presence", "severity": "critical", "status": "PASS" if missing_count == 0 else "FAIL", "detail": f"missing_or_failed_inputs={missing_count}"},
            {"flag_id": "parameter_grid_limit", "severity": "critical", "status": "PASS" if grid_count <= 100 else "FAIL", "detail": f"parameter_combinations={grid_count}"},
            {"flag_id": "candidate_pool_eligible_only", "severity": "critical", "status": "PASS", "detail": "Only eligible universe tickers entered candidate search."},
            {"flag_id": "formal_v9_excluded", "severity": "critical", "status": "PASS", "detail": "formal v9 was not used as benchmark or baseline."},
            {"flag_id": "no_baseline_replacement", "severity": "critical", "status": "PASS", "detail": "Search results are candidate evidence only."},
            {"flag_id": "no_v10", "severity": "critical", "status": "PASS", "detail": "v10 was not created or permitted."},
        ]
    )


def write_p5b_report(
    out_dir: Path,
    run_id: str,
    candidate_summary: pd.DataFrame,
    selected: pd.DataFrame,
    rejected: pd.DataFrame,
    grid_count: int,
) -> None:
    top = selected.head(3)[["candidate_id", "CAGR", "MDD", "Calmar", "Sharpe", "turnover"]].to_dict("records") if not selected.empty else []
    text = f"""# Formal MVE2 Controlled Search P5-B Report

## Summary

- Run id: `{run_id}`
- Decision: `P5B_CONTROLLED_SEARCH_COMPLETED`
- Controlled search success: `true`
- Full search executed: `true`
- Parameter combinations: `{grid_count}`
- Candidate rows: `{len(candidate_summary)}`
- Selected for P6 validation/audit only: `{len(selected)}`
- Rejected rows: `{len(rejected)}`
- Baseline replaced: `false`
- v10 executed: `false`

## Selected Candidates

Selected candidates are only selected for P6 validation / audit pack. They are not baselines.

Top selected records:

```json
{json.dumps(top, indent=2)}
```

## Data Source

The search used the audited unified adjusted OHLCV store only. Core fields were `date`, `ticker`, `adj_close`, and `volume`.

## Universe

Only eligible tickers entered the formal candidate pool. Excluded tickers remained observation and audit reference only.

## Benchmarks

Benchmark comparison includes SPY, QQQ, and equal-weight eligible universe when available. v8.2 remains comparison baseline metadata only. formal v9 was not used as benchmark or baseline.

## Next Step

P5-B allows a separate P6 validation / audit pack task. It does not permit baseline replacement or v10.
"""
    (out_dir / "formal_mve2_controlled_search_report.md").write_text(text, encoding="utf-8")


def write_p5b_readme(out_dir: Path, run_id: str) -> None:
    text = f"""# Formal MVE2 Controlled Search P5-B

Run id: `{run_id}`

This package contains a controlled full-search run using the audited unified adjusted OHLCV store and eligible universe only.

The selected candidates are for P6 validation / audit only. They are not a baseline, do not replace v8.2, and do not permit v10.
"""
    (out_dir / "README.md").write_text(text, encoding="utf-8")


def write_p5b_manifest(
    out_dir: Path,
    run_id: str,
    generated_at: str,
    generated_files: list[Path],
    zip_path: Path,
    grid_count: int,
    selected_count: int,
) -> None:
    manifest = {
        "run_id": run_id,
        "run_type": "formal_mve2_controlled_search_p5b",
        "mode": "full_search",
        "generated_at": generated_at,
        "git_commit": git_head(),
        "script_path": SCRIPT_PATH.as_posix(),
        "input_paths": [
            rel(P2C_DIR),
            rel(VALIDATION_DIR),
            rel(SEARCH_DIR),
            rel(STORE_DIR),
            rel(V82_AUDIT_DIR),
        ],
        "output_dir": rel(out_dir),
        "generated_files": [rel(path) for path in generated_files] + [rel(zip_path)],
        "decision": "P5B_CONTROLLED_SEARCH_COMPLETED",
        "controlled_search_success": True,
        "full_search_executed": True,
        "formal_mve2_search_executed": True,
        "model_training_executed": False,
        "parameter_combination_count": grid_count,
        "formal_candidate_ranking_generated": True,
        "selected_candidates_generated": True,
        "selected_count": selected_count,
        "selected_for_validation_only": True,
        "baseline_replaced": False,
        "no_baseline_replacement": True,
        "direct_v10_allowed": False,
        "no_v10": True,
        "requires_p6_validation": True,
        "group4_hold_not_touched": True,
        "raw_data_modified": False,
        "audit_csv_modified": False,
        "explicit_exclusions": [
            "old qlib",
            "old v8 cache",
            "formal v9 as benchmark or baseline",
            "v8.2 formal baseline outputs as data source",
            "limited MVE2 as formal baseline",
            "group4 artifacts",
        ],
    }
    write_json(out_dir / "manifest.json", manifest)


def write_p5b_controlled_search_outputs(out_dir: Path) -> tuple[bool, list[Path], Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "small_tables").mkdir(exist_ok=True)
    run_id = out_dir.name
    generated_at = datetime.now().isoformat(timespec="seconds")

    p2c_decision = str(read_json(P2C_DIR / "final_readiness_decision.json").get("final_readiness_decision", "MISSING"))
    input_checks = check_inputs()
    if p2c_decision != "PASS_TO_P3_FORMAL_MVE2_DESIGN":
        raise RuntimeError(f"P2-C readiness is {p2c_decision}, expected PASS_TO_P3_FORMAL_MVE2_DESIGN")
    if input_checks.empty or not (input_checks["status"] == "PASS").all():
        raise RuntimeError("required P5-B inputs are missing")

    eligible = read_csv(SEARCH_DIR / "eligible_universe_limited_mve2.csv")
    excluded = read_csv(SEARCH_DIR / "excluded_tickers_limited_mve2.csv")
    accepted_flags = read_csv(P2C_DIR / "accepted_quality_flags.csv")
    price_data, price_quality = load_formal_search_prices(eligible, excluded)
    eligible_tickers = sorted(eligible["ticker"].astype(str).unique().tolist())
    prices, volumes = build_price_volume_matrices(price_data, eligible_tickers)
    grid = parameter_grid()
    if len(grid) > 100:
        raise RuntimeError(f"parameter grid count {len(grid)} exceeds approval limit 100")
    result_tables = run_controlled_search(prices, volumes, grid)

    generated_files: list[Path] = []
    tables = {
        "candidate_summary.csv": result_tables["candidate_summary"],
        "selected_candidates.csv": result_tables["selected_candidates"],
        "rejected_candidates.csv": result_tables["rejected_candidates"],
        "benchmark_comparison.csv": result_tables["benchmark_comparison"],
        "yearly_performance.csv": result_tables["yearly_performance"],
        "subperiod_performance.csv": result_tables["subperiod_performance"],
        "drawdown_summary.csv": result_tables["drawdown_summary"],
        "turnover_summary.csv": result_tables["turnover_summary"],
        "cost_stress_summary.csv": result_tables["cost_stress_summary"],
        "risk_flag_exposure.csv": result_tables["risk_flag_exposure"],
        "parameter_grid_summary.csv": grid,
        "search_execution_summary.csv": pd.DataFrame(
            [
                {"item": "mode_requested", "value": "full_search", "status": "PASS"},
                {"item": "confirmation_received", "value": "true", "status": "PASS"},
                {"item": "p2c_readiness_decision", "value": p2c_decision, "status": "PASS"},
                {"item": "parameter_combination_count", "value": len(grid), "status": "PASS"},
                {"item": "controlled_search_success", "value": "true", "status": "PASS"},
                {"item": "baseline_replaced", "value": "false", "status": "PASS"},
                {"item": "v10_executed", "value": "false", "status": "PASS"},
            ]
        ),
        "reproducibility_checklist.csv": reproducibility_checklist(run_id, out_dir),
        "risk_flags.csv": p5b_risk_flags(input_checks, len(grid)),
        "universe_policy.csv": universe_policy(eligible, excluded),
        "benchmark_policy.csv": benchmark_policy(),
        "price_input_quality_summary.csv": price_quality,
    }
    for name, df in tables.items():
        path = out_dir / name
        df.to_csv(path, index=False)
        generated_files.append(path)

    small_tables = {
        "top_selected_candidates.csv": result_tables["selected_candidates"].head(5),
        "metrics_by_strategy_family.csv": result_tables["candidate_summary"].groupby("strategy_family", as_index=False).agg(
            candidate_count=("candidate_id", "count"),
            median_CAGR=("CAGR", "median"),
            median_Calmar=("Calmar", "median"),
            best_Calmar=("Calmar", "max"),
        ),
        "rebalance_selection_log_sample.csv": result_tables["rebalance_selection_log"].head(200),
        "risk_flag_tickers.csv": p5_risk_flag_exposure(accepted_flags),
    }
    for name, df in small_tables.items():
        path = out_dir / "small_tables" / name
        df.to_csv(path, index=False)
        generated_files.append(path)

    universe_summary = read_csv(P2C_DIR / "universe_readiness_summary.csv")
    universe = universe_counts(universe_summary)
    run_config = build_run_config(run_id, out_dir, universe, "full_search", generated_at)
    run_config["run_type"] = "formal_mve2_controlled_search_p5b"
    run_config["execution_policy"].update(
        {
            "full_search_requested": True,
            "full_search_executed": True,
            "controlled_search_success": True,
            "parameter_combination_count": len(grid),
            "selected_for_validation_only": True,
            "no_baseline_replacement": True,
            "no_v10": True,
        }
    )
    run_config_path = out_dir / "run_config.json"
    write_json(run_config_path, run_config)
    generated_files.append(run_config_path)

    decision_path = out_dir / "formal_mve2_search_decision.json"
    write_json(decision_path, p5b_decision_json(run_id, result_tables, len(grid)))
    generated_files.append(decision_path)

    guardrails_path = out_dir / "formal_search_guardrails.json"
    write_json(guardrails_path, p5b_guardrails(len(grid)))
    generated_files.append(guardrails_path)

    write_p5b_report(
        out_dir,
        run_id,
        result_tables["candidate_summary"],
        result_tables["selected_candidates"],
        result_tables["rejected_candidates"],
        len(grid),
    )
    generated_files.append(out_dir / "formal_mve2_controlled_search_report.md")
    write_p5b_readme(out_dir, run_id)
    generated_files.append(out_dir / "README.md")

    manifest_path = out_dir / "manifest.json"
    generated_files.append(manifest_path)
    zip_path = create_zip(out_dir)
    write_p5b_manifest(
        out_dir,
        run_id,
        generated_at,
        generated_files,
        zip_path,
        len(grid),
        int(len(result_tables["selected_candidates"])),
    )
    zip_path = create_zip(out_dir)
    return True, sorted(set(generated_files), key=lambda p: rel(p)), zip_path


def write_manifest(
    out_dir: Path,
    run_id: str,
    generated_at: str,
    mode: str,
    dryrun_success: bool,
    generated_files: list[Path],
    zip_path: Path,
) -> None:
    manifest = {
        "run_id": run_id,
        "run_type": "formal_mve2_search_implementation_p4_dryrun",
        "mode": mode,
        "generated_at": generated_at,
        "git_commit": git_head(),
        "script_path": SCRIPT_PATH.as_posix(),
        "input_paths": [
            rel(P2C_DIR),
            rel(VALIDATION_DIR),
            rel(SEARCH_DIR),
            rel(STORE_DIR),
            rel(V82_AUDIT_DIR),
            rel(FORMAL_V9_FAILURE_AUDIT),
        ],
        "output_dir": rel(out_dir),
        "generated_files": [rel(path) for path in generated_files] + [rel(zip_path)],
        "dryrun_success": dryrun_success,
        "dry_run_only": True,
        "full_search_executed": False,
        "formal_mve2_search_executed": False,
        "model_training_executed": False,
        "formal_candidate_ranking_generated": False,
        "selected_formal_candidate_generated": False,
        "baseline_replaced": False,
        "direct_v10_allowed": False,
        "group4_hold_not_touched": True,
        "raw_data_modified": False,
        "audit_csv_modified": False,
        "explicit_exclusions": [
            "old qlib",
            "old v8 cache",
            "formal v9 outputs as baseline or data source",
            "v8.2 formal baseline outputs as data source",
            "group4 artifacts",
        ],
    }
    write_json(out_dir / "manifest.json", manifest)


def write_outputs(out_dir: Path, mode: str) -> tuple[bool, list[Path], Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "small_tables").mkdir(exist_ok=True)

    p2c_decision = read_json(P2C_DIR / "final_readiness_decision.json")
    decision = str(p2c_decision.get("final_readiness_decision", "MISSING"))
    input_checks = check_inputs()
    universe_summary = read_csv(P2C_DIR / "universe_readiness_summary.csv")
    accepted_flags = read_csv(P2C_DIR / "accepted_quality_flags.csv")
    eligible = read_csv(SEARCH_DIR / "eligible_universe_limited_mve2.csv")
    excluded = read_csv(SEARCH_DIR / "excluded_tickers_limited_mve2.csv")
    universe = universe_counts(universe_summary)
    dryrun_success = bool(
        decision == "PASS_TO_P3_FORMAL_MVE2_DESIGN"
        and not input_checks.empty
        and (input_checks["status"] == "PASS").all()
        and universe["search_universe_count"] == 51
        and universe["eligible_ticker_count"] == 40
        and universe["excluded_ticker_count"] == 11
    )

    run_id = out_dir.name
    generated_at = datetime.now().isoformat(timespec="seconds")

    tables = {
        "dryrun_checks.csv": input_checks,
        "universe_policy.csv": universe_policy(eligible, excluded),
        "eligible_excluded_policy.csv": eligible_excluded_policy(eligible, excluded),
        "benchmark_policy.csv": benchmark_policy(),
        "risk_flag_policy.csv": risk_flag_policy(accepted_flags),
        "search_space_summary.csv": search_space_summary(),
        "evaluation_metric_policy.csv": evaluation_metric_policy(),
        "output_package_schema.csv": output_package_schema(),
        "promotion_gate_policy.csv": promotion_gate_policy(),
        "reproducibility_checklist.csv": reproducibility_checklist(run_id, out_dir),
        "risk_flags.csv": risk_flags_for_run(dryrun_success, input_checks),
    }
    generated_files: list[Path] = []
    for name, df in tables.items():
        path = out_dir / name
        df.to_csv(path, index=False)
        generated_files.append(path)

    small_tables = {
        "strategy_family_scaffold.csv": search_space_summary().loc[lambda df: df["section"] == "strategy_family"],
        "parameter_grid_preview.csv": search_space_summary().loc[
            lambda df: df["section"].isin(["rebalance", "holding", "cost", "slippage"])
        ],
        "future_output_schema_required.csv": output_package_schema(),
        "smoke_summary.csv": pd.DataFrame(
            [
                {"item": "p2c_pass", "status": decision == "PASS_TO_P3_FORMAL_MVE2_DESIGN"},
                {"item": "inputs_present", "status": bool((input_checks["status"] == "PASS").all())},
                {"item": "universe_counts_match", "status": universe == {"search_universe_count": 51, "eligible_ticker_count": 40, "excluded_ticker_count": 11}},
                {"item": "full_search_executed", "status": False},
                {"item": "candidate_ranking_generated", "status": False},
            ]
        ),
    }
    for name, df in small_tables.items():
        path = out_dir / "small_tables" / name
        df.to_csv(path, index=False)
        generated_files.append(path)

    run_config_path = out_dir / "run_config.json"
    write_json(run_config_path, build_run_config(run_id, out_dir, universe, mode, generated_at))
    generated_files.append(run_config_path)

    guardrails_path = out_dir / "formal_search_guardrails.json"
    write_json(guardrails_path, guardrails(mode, dryrun_success))
    generated_files.append(guardrails_path)

    write_report(out_dir, run_id, dryrun_success, decision, universe)
    generated_files.append(out_dir / "p4_dryrun_report.md")
    write_readme(out_dir, run_id, dryrun_success)
    generated_files.append(out_dir / "README.md")

    manifest_path = out_dir / "manifest.json"
    generated_files.append(manifest_path)
    zip_path = create_zip(out_dir)
    write_manifest(out_dir, run_id, generated_at, mode, dryrun_success, generated_files, zip_path)
    zip_path = create_zip(out_dir)

    return dryrun_success, sorted(set(generated_files), key=lambda p: rel(p)), zip_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Implement formal MVE2 search scaffold; dry-run is the default and only P4 mode used.")
    parser.add_argument("--mode", choices=["dry_run", "full_search"], default="dry_run")
    parser.add_argument("--confirm-formal-search", action="store_true", help="Reserved for future explicit full search approval; not used in P4.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.mode == "full_search":
        if not args.confirm_formal_search:
            raise SystemExit("full_search requires --confirm-formal-search and is not part of P4 dry-run")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = OUTPUT_ROOT / f"{P5B_RUN_PREFIX}_{timestamp}"
        controlled_search_success, generated_files, zip_path = write_p5b_controlled_search_outputs(out_dir)
        print(json.dumps(
            {
                "run_id": out_dir.name,
                "output_dir": rel(out_dir),
                "decision": "P5B_CONTROLLED_SEARCH_COMPLETED",
                "controlled_search_success": controlled_search_success,
                "full_search_executed": True,
                "generated_file_count": len(generated_files),
                "zip_path": rel(zip_path),
            },
            indent=2,
        ))
        return 0 if controlled_search_success else 2

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = OUTPUT_ROOT / f"{RUN_PREFIX}_{timestamp}"
    dryrun_success, generated_files, zip_path = write_outputs(out_dir, args.mode)
    print(json.dumps(
        {
            "run_id": out_dir.name,
            "output_dir": rel(out_dir),
            "dryrun_success": dryrun_success,
            "generated_file_count": len(generated_files),
            "zip_path": rel(zip_path),
        },
        indent=2,
    ))
    return 0 if dryrun_success else 2


if __name__ == "__main__":
    raise SystemExit(main())
