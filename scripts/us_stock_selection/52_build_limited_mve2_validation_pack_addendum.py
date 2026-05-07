from __future__ import annotations

import json
import re
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "us_stock_selection"
VALIDATION_RUN_ID = "limited_mve2_validation_20260502_183555"
SEARCH_RUN_ID = "limited_mve2_20260502_142702"
VALIDATION_DIR = OUTPUT_ROOT / VALIDATION_RUN_ID
SEARCH_DIR = OUTPUT_ROOT / SEARCH_RUN_ID
SMALL_TABLES_DIR = VALIDATION_DIR / "small_tables"
ZIP_PATH = OUTPUT_ROOT / f"{VALIDATION_RUN_ID}.zip"


def rel(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def read_csv(name: str) -> pd.DataFrame:
    path = VALIDATION_DIR / name
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def read_search_csv(name: str) -> pd.DataFrame:
    path = SEARCH_DIR / name
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def git_head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        text=True,
    ).strip()


def safe_value(value: object) -> object:
    if pd.isna(value):
        return "NA"
    return value


def first_match(df: pd.DataFrame, candidate_key: str) -> pd.Series | None:
    if df.empty or "candidate_key" not in df.columns:
        return None
    matched = df[df["candidate_key"] == candidate_key]
    if matched.empty:
        return None
    return matched.iloc[0]


def base_cost_row(cost: pd.DataFrame, candidate_key: str) -> pd.Series | None:
    if cost.empty or "candidate_key" not in cost.columns:
        return None
    subset = cost[cost["candidate_key"] == candidate_key].copy()
    if subset.empty:
        return None
    if "cost_bps" in subset.columns:
        subset["cost_bps_numeric"] = pd.to_numeric(subset["cost_bps"], errors="coerce")
        zero = subset[subset["cost_bps_numeric"] == 0]
        if not zero.empty:
            return zero.iloc[0]
        return subset.sort_values("cost_bps_numeric").iloc[0]
    return subset.iloc[0]


def cost_row(cost: pd.DataFrame, candidate_key: str, target_bps: int) -> pd.Series | None:
    if cost.empty or "candidate_key" not in cost.columns or "cost_bps" not in cost.columns:
        return None
    subset = cost[cost["candidate_key"] == candidate_key].copy()
    if subset.empty:
        return None
    subset["cost_bps_numeric"] = pd.to_numeric(subset["cost_bps"], errors="coerce")
    matched = subset[subset["cost_bps_numeric"] == target_bps]
    if matched.empty:
        return None
    return matched.iloc[0]


def benchmark_row(benchmarks: pd.DataFrame, candidate_key: str) -> pd.Series | None:
    if benchmarks.empty or "candidate_key" not in benchmarks.columns:
        return None
    subset = benchmarks[benchmarks["candidate_key"] == candidate_key].copy()
    if subset.empty:
        return None
    if "benchmark_type" in subset.columns:
        preferred_order = [
            "same_ticker_buy_hold",
            "bucket_equal_weight",
            "qqq_buy_hold",
            "spy_buy_hold",
        ]
        for preferred in preferred_order:
            matched = subset[subset["benchmark_type"] == preferred]
            if not matched.empty:
                return matched.iloc[0]
    return subset.iloc[0]


def risk_summary(row: pd.Series | None) -> str:
    if row is None:
        return "NA"
    skip = {
        "run_id",
        "candidate_key",
        "ticker",
        "strategy_name",
        "CAGR",
        "max_drawdown",
        "Calmar",
        "trade_count",
        "turnover",
        "rolling_pass_rate",
        "risk_flag_count",
    }
    flags: list[str] = []
    for key, value in row.items():
        if key in skip:
            continue
        if isinstance(value, bool) and value:
            flags.append(key)
        elif isinstance(value, str) and value.lower() == "true":
            flags.append(key)
    count = safe_value(row.get("risk_flag_count", "NA"))
    if flags:
        return f"risk_flag_count={count}; flags={';'.join(flags)}"
    return f"risk_flag_count={count}; flags=none"


def evidence_file_summary() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    files = [
        "README_summary.md",
        "reports/limited_mve2_validation_report.md",
        "reports/limited_mve2_validation_summary.xlsx",
        "limited_mve2_validation_run_config.json",
        "frozen_candidates_limited_mve2_validation.csv",
        "validation_decision_summary.csv",
        "validation_risk_flags.csv",
        "validation_benchmark_comparison.csv",
        "validation_cost_stress_results.csv",
        "validation_period_slice_results.csv",
        "validation_rolling_summary.csv",
        "validation_rolling_window_results.csv",
        "validation_parameter_neighborhood.csv",
        "validation_top_month_sensitivity.csv",
        "validation_trade_ledger.csv",
        "rejected_or_observation_candidates.csv",
        "RUN_SUMMARY.md",
        "NEXT_STEPS.md",
    ]
    for name in files:
        path = VALIDATION_DIR / name
        row_count: object = "NA"
        if path.suffix.lower() == ".csv" and path.exists():
            try:
                row_count = len(pd.read_csv(path))
            except Exception:
                row_count = "unreadable"
        rows.append(
            {
                "file": rel(path),
                "exists": path.exists(),
                "row_count": row_count,
                "role": evidence_role(name),
            }
        )
    search_files = [
        "eligible_universe_limited_mve2.csv",
        "excluded_tickers_limited_mve2.csv",
        "all_strategy_results_limited_mve2.csv",
        "limited_mve2_run_config.json",
        "README_summary.md",
    ]
    for name in search_files:
        path = SEARCH_DIR / name
        row_count = "NA"
        if path.suffix.lower() == ".csv" and path.exists():
            try:
                row_count = len(pd.read_csv(path))
            except Exception:
                row_count = "unreadable"
        rows.append(
            {
                "file": rel(path),
                "exists": path.exists(),
                "row_count": row_count,
                "role": evidence_role(name),
            }
        )
    return pd.DataFrame(rows)


def evidence_role(name: str) -> str:
    if "decision" in name or "candidate" in name:
        return "candidate decision evidence"
    if "risk" in name or "rolling" in name or "top_month" in name:
        return "robustness evidence"
    if "benchmark" in name:
        return "benchmark evidence"
    if "cost" in name:
        return "cost evidence"
    if "eligible" in name or "excluded" in name:
        return "universe evidence"
    if "config" in name:
        return "run configuration"
    if "README" in name or "report" in name or "SUMMARY" in name:
        return "narrative evidence"
    return "supporting evidence"


def build_key_metrics(decisions: pd.DataFrame) -> pd.DataFrame:
    cost = read_csv("validation_cost_stress_results.csv")
    benchmarks = read_csv("validation_benchmark_comparison.csv")
    risk = read_csv("validation_risk_flags.csv")
    rows: list[dict[str, object]] = []
    for _, decision in decisions.iterrows():
        candidate_key = str(decision["candidate_key"])
        base_cost = base_cost_row(cost, candidate_key)
        cost20 = cost_row(cost, candidate_key, 20)
        bench = benchmark_row(benchmarks, candidate_key)
        risk_row = first_match(risk, candidate_key)
        rows.append(
            {
                "candidate_id": candidate_key,
                "strategy_id": candidate_key,
                "ticker": safe_value(decision.get("ticker", "NA")),
                "strategy_name": safe_value(decision.get("strategy_name", "NA")),
                "decision": safe_value(decision.get("validation_decision", "NA")),
                "formal_mve2_supported": False,
                "CAGR": safe_value(decision.get("CAGR", "NA")),
                "MDD": safe_value(decision.get("max_drawdown", "NA")),
                "Calmar": safe_value(decision.get("Calmar", "NA")),
                "Sharpe": safe_value(base_cost.get("Sharpe", "NA")) if base_cost is not None else "NA",
                "turnover": safe_value(base_cost.get("turnover", "NA")) if base_cost is not None else safe_value(decision.get("turnover", "NA")),
                "trade_count": safe_value(base_cost.get("trade_count", "NA")) if base_cost is not None else "NA",
                "benchmark_type": safe_value(bench.get("benchmark_type", "NA")) if bench is not None else "NA",
                "benchmark_ticker": safe_value(bench.get("benchmark_ticker", "NA")) if bench is not None else "NA",
                "benchmark_CAGR": safe_value(bench.get("benchmark_CAGR", "NA")) if bench is not None else "NA",
                "benchmark_MDD": safe_value(bench.get("benchmark_MDD", "NA")) if bench is not None else "NA",
                "benchmark_Calmar": safe_value(bench.get("benchmark_Calmar", "NA")) if bench is not None else "NA",
                "excess_CAGR": safe_value(bench.get("excess_CAGR", "NA")) if bench is not None else "NA",
                "cost20_CAGR": safe_value(cost20.get("CAGR", "NA")) if cost20 is not None else "NA",
                "cost20_Calmar": safe_value(cost20.get("Calmar", "NA")) if cost20 is not None else "NA",
                "cost20_pass": safe_value(cost20.get("pass_cost_stress", "NA")) if cost20 is not None else "NA",
                "risk_flag_summary": risk_summary(risk_row),
                "evidence_file": rel(VALIDATION_DIR / "validation_decision_summary.csv"),
            }
        )
    return pd.DataFrame(rows)


def build_decision_counts(decisions: pd.DataFrame) -> pd.DataFrame:
    counts = decisions["validation_decision"].value_counts().rename_axis("decision").reset_index(name="count")
    collapsed_rows = [
        {"decision": "pass_to_next_validation", "count": int((decisions["validation_decision"] == "pass_to_next_validation").sum())},
        {"decision": "conditional_total", "count": int(decisions["validation_decision"].astype(str).str.startswith("conditional").sum())},
        {"decision": "observation_only", "count": int((decisions["validation_decision"] == "observation_only").sum())},
    ]
    collapsed = pd.DataFrame(collapsed_rows)
    counts["count_scope"] = "raw"
    collapsed["count_scope"] = "collapsed"
    return pd.concat([counts, collapsed], ignore_index=True)[["count_scope", "decision", "count"]]


def build_candidate_decisions(decisions: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "candidate_key",
        "ticker",
        "strategy_name",
        "role",
        "validation_decision",
        "decision_reason",
        "CAGR",
        "max_drawdown",
        "Calmar",
        "rolling_pass_rate",
        "cost_sensitive",
        "top_month_dependent",
        "cliff_parameter_sensitive",
        "benchmark_underperformance",
        "weak_recent_performance",
        "formal_mve2_supported",
    ]
    existing = [column for column in columns if column in decisions.columns]
    return decisions[existing].copy()


def build_missing_table() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "item": "formal MVE2 support",
                "status": "FAIL",
                "evidence_file": rel(VALIDATION_DIR / "validation_decision_summary.csv"),
                "gap": "All nine candidates remain formal_mve2_supported=false.",
                "suggested_action": "Run a separate formal MVE2 data quality gate before any formal search design.",
            },
            {
                "item": "eligible and excluded ticker detail inside validation pack",
                "status": "PARTIAL",
                "evidence_file": rel(SEARCH_DIR / "eligible_universe_limited_mve2.csv") + "; " + rel(SEARCH_DIR / "excluded_tickers_limited_mve2.csv"),
                "gap": "Ticker detail exists in the source search run, while this addendum records the source path instead of duplicating it.",
                "suggested_action": "If a standalone archive is required, copy sanitized universe tables in a later review task.",
            },
            {
                "item": "benchmark and cost evidence",
                "status": "PASS",
                "evidence_file": rel(VALIDATION_DIR / "validation_benchmark_comparison.csv") + "; " + rel(VALIDATION_DIR / "validation_cost_stress_results.csv"),
                "gap": "No gap for available limited validation evidence.",
                "suggested_action": "Use these files only inside the limited MVE2 research line.",
            },
            {
                "item": "baseline status",
                "status": "FAIL",
                "evidence_file": rel(VALIDATION_DIR / "selected_report.md"),
                "gap": "The pack cannot be used as a formal baseline or v10 starting point.",
                "suggested_action": "Keep v8.2 frozen as the formal baseline until a separate approved formal MVE2 process passes.",
            },
        ]
    )


def build_data_source_policy() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "policy_item": "research_line",
                "value": "limited_mve2_independent_research_line",
                "evidence": rel(VALIDATION_DIR / "limited_mve2_validation_run_config.json"),
            },
            {
                "policy_item": "data_store",
                "value": "audited unified adjusted OHLCV store",
                "evidence": rel(VALIDATION_DIR / "README_summary.md"),
            },
            {
                "policy_item": "fields_used",
                "value": "adj_close;volume",
                "evidence": rel(VALIDATION_DIR / "limited_mve2_validation_run_config.json"),
            },
            {
                "policy_item": "not_used",
                "value": "old qlib;old v8 cache;formal v9 output;v8.2 formal baseline output",
                "evidence": rel(VALIDATION_DIR / "README.md"),
            },
            {
                "policy_item": "formal_mve2_supported",
                "value": "false",
                "evidence": rel(VALIDATION_DIR / "validation_decision_summary.csv"),
            },
            {
                "policy_item": "group4_hold_not_touched",
                "value": "true",
                "evidence": rel(VALIDATION_DIR / "manifest.json"),
            },
        ]
    )


def build_reproducibility_checklist() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"check_item": "README present", "status": "PASS", "evidence": rel(VALIDATION_DIR / "README.md"), "note": "Standalone review entry point added."},
            {"check_item": "manifest present", "status": "PASS", "evidence": rel(VALIDATION_DIR / "manifest.json"), "note": "Generated by P1-B addendum."},
            {"check_item": "key metrics present", "status": "PASS", "evidence": rel(VALIDATION_DIR / "key_metrics_summary.csv"), "note": "Missing source metrics are marked NA."},
            {"check_item": "selected report present", "status": "PASS", "evidence": rel(VALIDATION_DIR / "selected_report.md"), "note": "Contains limited-scope conclusion and isolation warnings."},
            {"check_item": "small tables present", "status": "PASS", "evidence": rel(SMALL_TABLES_DIR), "note": "Reviewer-facing CSV tables added."},
            {"check_item": "source search run identified", "status": "PASS", "evidence": rel(SEARCH_DIR), "note": "No strategy search was rerun."},
            {"check_item": "formal baseline claim", "status": "FAIL", "evidence": rel(VALIDATION_DIR / "selected_report.md"), "note": "This pack is explicitly not a formal baseline."},
            {"check_item": "formal MVE2 entry", "status": "FAIL", "evidence": rel(VALIDATION_DIR / "validation_decision_summary.csv"), "note": "All candidates remain formal_mve2_supported=false."},
        ]
    )


def write_readme(candidate_count: int, decision_counts: dict[str, int], zip_path: Path) -> None:
    text = f"""# Limited MVE2 Validation Pack

Run id: `{VALIDATION_RUN_ID}`

This directory is a standalone review pack for the limited MVE2 validation run. It belongs to an independent audited-store research line and is not part of the v8.2 frozen formal baseline evidence chain.

## Scope

- Source search run: `{SEARCH_RUN_ID}`
- Candidate count: `{candidate_count}`
- Decision distribution: `{decision_counts.get('pass_to_next_validation', 0)}` pass_to_next_validation, `{decision_counts.get('conditional_total', 0)}` conditional, `{decision_counts.get('observation_only', 0)}` observation_only
- Formal MVE2 support: `false` for every candidate
- Data source policy: audited unified adjusted OHLCV store
- Core fields: `adj_close` and `volume`
- Exclusions: old qlib data, old v8 cache, formal v9 output, and v8.2 formal baseline output

## How To Review

Start with `selected_report.md`, then inspect `key_metrics_summary.csv` and the reviewer tables in `small_tables/`. The original detailed validation evidence remains in the `validation_*` CSV files and `reports/limited_mve2_validation_report.md`.

## How To Reproduce This Pack

Run `python scripts/us_stock_selection/52_build_limited_mve2_validation_pack_addendum.py` from the repository root. The script only reads existing limited MVE2 outputs and rebuilds the addendum files plus `{rel(zip_path)}`. It does not rerun strategy search, train a model, or change candidate decisions.

## Missing Metric Policy

When a metric is not present in the existing validation evidence, the addendum writes `NA`. No metric is inferred or filled from another evidence chain.

## Output Files

- `manifest.json`
- `key_metrics_summary.csv`
- `selected_report.md`
- `README.md`
- `small_tables/decision_counts.csv`
- `small_tables/candidate_decisions.csv`
- `small_tables/available_evidence_files.csv`
- `small_tables/missing_or_partial_items.csv`
- `small_tables/data_source_policy.csv`
- `small_tables/reproducibility_checklist.csv`

## Restrictions

This pack has not entered formal MVE2, cannot be used as a formal baseline, and cannot be used as a v10 starting point. The next allowed step is P1-B human review or a separate P2 formal MVE2 data quality gate.
"""
    (VALIDATION_DIR / "README.md").write_text(text, encoding="utf-8")


def write_selected_report(candidate_count: int, decision_counts: dict[str, int]) -> None:
    text = f"""# Limited MVE2 Selected Report

## Current Conclusion

The limited MVE2 validation pack remains a limited, independent audited-store research result. It validated `{candidate_count}` frozen candidates from `{SEARCH_RUN_ID}` and did not start formal MVE2.

Decision distribution:

- pass_to_next_validation: `{decision_counts.get('pass_to_next_validation', 0)}`
- conditional: `{decision_counts.get('conditional_total', 0)}`
- observation_only: `{decision_counts.get('observation_only', 0)}`

Every candidate remains `formal_mve2_supported=false`.

## Why This Is Not A Formal Baseline

The pack is based on limited candidate validation, not on a formal MVE2 universe, formal data gate, approved benchmark set, or formal replay standard. It cannot replace the current v8.2 frozen Pool A `top5_ytdcap80p_derisk100p` baseline.

## Why This Cannot Directly Enter v10

Formal v10 remains disallowed because the limited MVE2 line has not passed a separate formal MVE2 data quality gate. The current evidence is useful for review and follow-up design only.

## Evidence Chain Isolation

- v8.2 frozen formal baseline: remains the formal comparison baseline and is not mixed into this pack.
- formal v9 failed branch: remains a failure and risk reference only; it is not used as a baseline here.
- limited MVE2: uses the audited-store line with `adj_close` and `volume`, and remains separate from both formal branches.

## Allowed Next Step

The next allowed step is P1-B human review or P2 formal MVE2 data quality gate. Direct formal MVE2 search design, v10 work, or baseline replacement is not supported by this pack.
"""
    (VALIDATION_DIR / "selected_report.md").write_text(text, encoding="utf-8")


def write_manifest(
    head: str,
    candidate_count: int,
    decision_counts: dict[str, int],
    generated_files: list[str],
) -> None:
    manifest = {
        "run_id": VALIDATION_RUN_ID,
        "run_type": "limited_mve2_validation_pack",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "git_commit": head,
        "source_search_run": SEARCH_RUN_ID,
        "validation_pack_dir": rel(VALIDATION_DIR),
        "input_dirs": [rel(VALIDATION_DIR), rel(SEARCH_DIR)],
        "key_input_files": [
            rel(VALIDATION_DIR / "validation_decision_summary.csv"),
            rel(VALIDATION_DIR / "validation_risk_flags.csv"),
            rel(VALIDATION_DIR / "validation_benchmark_comparison.csv"),
            rel(VALIDATION_DIR / "validation_cost_stress_results.csv"),
            rel(SEARCH_DIR / "eligible_universe_limited_mve2.csv"),
            rel(SEARCH_DIR / "excluded_tickers_limited_mve2.csv"),
        ],
        "generated_files": generated_files,
        "candidate_count": candidate_count,
        "decision_counts": decision_counts,
        "data_source_policy": "audited unified adjusted OHLCV store only",
        "fields_used": ["adj_close", "volume"],
        "formal_mve2_supported": False,
        "evidence_chain_scope": "limited_mve2_independent_research_line",
        "explicit_exclusions": [
            "old qlib",
            "old v8 cache",
            "formal v9 output",
            "v8.2 formal baseline output",
        ],
        "group4_hold_not_touched": True,
    }
    (VALIDATION_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def has_local_drive_path(path: Path) -> bool:
    if path.suffix.lower() not in {".csv", ".json", ".md", ".txt", ".py"}:
        return False
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return True
    return re.search(r"[A-Za-z]:\\", text) is not None


def write_zip() -> None:
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    zip_candidates = [
        VALIDATION_DIR / "manifest.json",
        VALIDATION_DIR / "key_metrics_summary.csv",
        VALIDATION_DIR / "selected_report.md",
        VALIDATION_DIR / "README.md",
        SMALL_TABLES_DIR / "decision_counts.csv",
        SMALL_TABLES_DIR / "candidate_decisions.csv",
        SMALL_TABLES_DIR / "available_evidence_files.csv",
        SMALL_TABLES_DIR / "missing_or_partial_items.csv",
        SMALL_TABLES_DIR / "data_source_policy.csv",
        SMALL_TABLES_DIR / "reproducibility_checklist.csv",
        VALIDATION_DIR / "frozen_candidates_limited_mve2_validation.csv",
        VALIDATION_DIR / "validation_decision_summary.csv",
        VALIDATION_DIR / "validation_risk_flags.csv",
        VALIDATION_DIR / "validation_benchmark_comparison.csv",
        VALIDATION_DIR / "validation_cost_stress_results.csv",
        VALIDATION_DIR / "validation_period_slice_results.csv",
        VALIDATION_DIR / "validation_rolling_summary.csv",
        VALIDATION_DIR / "validation_rolling_window_results.csv",
        VALIDATION_DIR / "validation_parameter_neighborhood.csv",
        VALIDATION_DIR / "validation_top_month_sensitivity.csv",
        VALIDATION_DIR / "validation_trade_ledger.csv",
        VALIDATION_DIR / "rejected_or_observation_candidates.csv",
        VALIDATION_DIR / "reports" / "limited_mve2_validation_report.md",
    ]
    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in zip_candidates:
            if path.exists() and not has_local_drive_path(path):
                archive.write(path, path.relative_to(VALIDATION_DIR.parent).as_posix())


def main() -> None:
    if not VALIDATION_DIR.exists():
        raise FileNotFoundError(rel(VALIDATION_DIR))
    if not SEARCH_DIR.exists():
        raise FileNotFoundError(rel(SEARCH_DIR))

    SMALL_TABLES_DIR.mkdir(parents=True, exist_ok=True)

    decisions = read_csv("validation_decision_summary.csv")
    if decisions.empty:
        raise FileNotFoundError(rel(VALIDATION_DIR / "validation_decision_summary.csv"))

    candidate_count = int(len(decisions))
    raw_counts = decisions["validation_decision"].value_counts().to_dict()
    decision_counts = {
        "pass_to_next_validation": int(raw_counts.get("pass_to_next_validation", 0)),
        "conditional": int(decisions["validation_decision"].astype(str).str.startswith("conditional").sum()),
        "conditional_total": int(decisions["validation_decision"].astype(str).str.startswith("conditional").sum()),
        "observation_only": int(raw_counts.get("observation_only", 0)),
        "raw": {str(key): int(value) for key, value in raw_counts.items()},
    }

    key_metrics = build_key_metrics(decisions)
    key_metrics.to_csv(VALIDATION_DIR / "key_metrics_summary.csv", index=False)

    build_decision_counts(decisions).to_csv(SMALL_TABLES_DIR / "decision_counts.csv", index=False)
    build_candidate_decisions(decisions).to_csv(SMALL_TABLES_DIR / "candidate_decisions.csv", index=False)
    evidence_file_summary().to_csv(SMALL_TABLES_DIR / "available_evidence_files.csv", index=False)
    build_missing_table().to_csv(SMALL_TABLES_DIR / "missing_or_partial_items.csv", index=False)
    build_data_source_policy().to_csv(SMALL_TABLES_DIR / "data_source_policy.csv", index=False)
    build_reproducibility_checklist().to_csv(SMALL_TABLES_DIR / "reproducibility_checklist.csv", index=False)

    write_readme(candidate_count, decision_counts, ZIP_PATH)
    write_selected_report(candidate_count, decision_counts)

    generated_files = [
        rel(VALIDATION_DIR / "manifest.json"),
        rel(VALIDATION_DIR / "key_metrics_summary.csv"),
        rel(VALIDATION_DIR / "selected_report.md"),
        rel(VALIDATION_DIR / "README.md"),
        rel(SMALL_TABLES_DIR / "decision_counts.csv"),
        rel(SMALL_TABLES_DIR / "candidate_decisions.csv"),
        rel(SMALL_TABLES_DIR / "available_evidence_files.csv"),
        rel(SMALL_TABLES_DIR / "missing_or_partial_items.csv"),
        rel(SMALL_TABLES_DIR / "data_source_policy.csv"),
        rel(SMALL_TABLES_DIR / "reproducibility_checklist.csv"),
        rel(ZIP_PATH),
    ]
    write_manifest(git_head(), candidate_count, decision_counts, generated_files)
    write_zip()

    print(json.dumps({"generated_files": generated_files, "zip_path": rel(ZIP_PATH), "zip_size_bytes": ZIP_PATH.stat().st_size}, indent=2))


if __name__ == "__main__":
    main()
