from __future__ import annotations

import argparse
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
REQUIRED_CORE_FIELDS = ["date", "ticker", "adj_close", "volume"]
VOLUME_WARNING_TICKERS = ["AAPL", "AMD", "ARKK", "IGV", "INTC", "SHOP"]
PRICE_JUMP_WARNING_TICKERS = ["AAPL", "AMD", "MSTR", "ROKU", "SHOP", "SOXL", "UPST"]


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
        raise SystemExit("full_search is intentionally not implemented in P4")

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
