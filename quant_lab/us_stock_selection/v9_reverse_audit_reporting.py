"""Reporting helpers for the v9 reverse audit package."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from quant_lab.us_stock_selection.utils import PROJECT_ROOT, save_text, write_excel, zip_selected_paths


def build_v9_reverse_audit_report(path: Path | str, result: dict[str, Any]) -> Path:
    verdict = result["verdict"]
    pool = result["pool_a_replay_audit"]
    negatives = result["negative_controls"]
    timing = result["execution_timing_sensitivity"]
    benchmark = result["benchmark"]
    stress = result["stress_test"]
    time_alignment = result["time_alignment"]
    universe = result["universe_policy_audit"]
    sources = result["source_manifest"]

    failed_time = time_alignment.loc[~time_alignment["pass"].astype(bool)].copy() if not time_alignment.empty else pd.DataFrame()
    suspicious_neg = (
        negatives.loc[negatives["leakage_or_backtest_bug_suspected"].astype(bool)].copy()
        if not negatives.empty and "leakage_or_backtest_bug_suspected" in negatives
        else pd.DataFrame()
    )
    policy_exceptions = universe.loc[universe["baseline_reproduction_only"].astype(bool)].copy() if not universe.empty else pd.DataFrame()

    text = f"""# US Stock Selection v9 Reverse Audit Report

## Scope

Task: execute `v9_reverse_audit_no_expansion`.

Hard boundaries:

- No real trading.
- No broker API.
- No Nasdaq100 / S&P500 / full-market expansion.
- No v10 entry.
- No ranking-weight or gate changes.
- No mainline strategy replacement.

## Sources Read

{_table(sources.loc[:, ["source", "exists", "read_status"]], max_rows=80)}

## Verdict

- classification: `{verdict.get("classification")}`
- allow_enter_v10: `{verdict.get("allow_enter_v10")}`
- allow_expand_nasdaq100: `{verdict.get("allow_expand_nasdaq100")}`
- allow_expand_sp500: `{verdict.get("allow_expand_sp500")}`
- allow_trade_execution: `{verdict.get("allow_trade_execution")}`
- leakage_or_backtest_bug_suspected: `{verdict.get("leakage_or_backtest_bug_suspected")}`
- requires_human_review: `{verdict.get("requires_human_review")}`
- reason: `{verdict.get("reason")}`

## Time Alignment And Label Audit

- Rows: `{len(time_alignment)}`
- Failed rows: `{len(failed_time)}`
- label fields in feature columns: `{_label_feature_status(time_alignment)}`

{_table(time_alignment, columns=[
    "universe_name",
    "score_package",
    "decision_date",
    "feature_date",
    "train_end_label_safe",
    "label_window_end",
    "execution_date",
    "feature_date_lte_decision",
    "execution_gt_decision",
    "label_window_end_lte_decision",
    "pass",
    "issue",
], max_rows=40)}

## Pool A Reverse Replay Audit

{_table(pool, max_rows=10)}

Interpretation: `v9_loaded_reproduction_*` is the v9 bridge row loaded from v8.2 frozen artifacts. `v9_local_replay_*` is the independent local Alpha360-compatible replay run in this audit only on Pool A top5/top10.

## Negative Controls

{_table(negatives, max_rows=20)}

Suspicious negative controls:

{_table(suspicious_neg, max_rows=20)}

## Execution Timing Sensitivity

{_table(timing, max_rows=10)}

Current implementation interpretation: the original v9 local replay assigns weights on the T+1 execution date, then `portfolio_returns` shifts weights one bar. It is therefore closer to T+1 close execution with returns captured from T+1 close to T+2 close. The no-shift case is diagnostic only and is not a strategy result.

## Benchmark

{_table(benchmark, max_rows=20)}

## Stress Test

{_table(stress, max_rows=40)}

## Universe And Data Governance

Baseline-only exceptions:

{_table(policy_exceptions, columns=[
    "ticker",
    "in_pool_a_reproduction",
    "v9_ready",
    "v9_exclude_reason",
    "baseline_reproduction_only",
    "eligible_for_new_expansion",
    "price_source",
    "policy_issue",
], max_rows=40)}

Full universe policy sample:

{_table(universe, columns=[
    "ticker",
    "source",
    "price_source",
    "in_pool_a_reproduction",
    "v9_ready",
    "baseline_reproduction_only",
    "eligible_for_new_expansion",
    "mixed_unified_store_yfinance_data_source_risk",
    "policy_issue",
], max_rows=80)}

## Required Answers

1. v9 local replay future/label audit: see `time_alignment_audit.csv`; failed rows force downgrade.
2. Pool A abnormal result: see `pool_a_replay_audit.csv`; material local-vs-frozen differences require human review.
3. Benchmark/stress: `benchmark.csv` and `stress_test.csv` are generated and bridge-copyable.
4. Classification: `{verdict.get("classification")}`.

This package remains a research audit artifact and is not a live trading recommendation.
"""
    return save_text(text, path)


def build_v9_reverse_audit_excel(path: Path | str, result: dict[str, Any]) -> Path:
    sheets = {
        "verdict": pd.DataFrame([result["verdict"]]),
        "pool_a_replay": result["pool_a_replay_audit"],
        "negative_controls": result["negative_controls"],
        "time_alignment": result["time_alignment"].head(5000),
        "execution_timing": result["execution_timing_sensitivity"],
        "benchmark": result["benchmark"],
        "stress_test": result["stress_test"].head(5000),
        "universe_policy": result["universe_policy_audit"].head(5000),
        "yearly_return": result["yearly_return"].head(5000),
        "attribution": result["attribution"].head(5000),
        "source_manifest": result["source_manifest"].head(5000),
    }
    return write_excel({k[:31]: v for k, v in sheets.items()}, path)


def package_v9_reverse_audit_run(run_dir: Path | str, timestamp: str) -> Path:
    base = Path(run_dir).resolve()
    zip_path = base.parent / f"us_stock_selection_quant_lab_v9_reverse_audit_{timestamp}.zip"
    paths = [
        PROJECT_ROOT / "AGENTS.md",
        PROJECT_ROOT / "NEXT_STEPS.md",
        PROJECT_ROOT / "RUN_SUMMARY.md",
        PROJECT_ROOT / "docs" / "US_STOCK_SELECTION_AUTORUN.md",
        PROJECT_ROOT / "docs" / "chatgpt_bridge" / "codex_inbox" / "TASK.md",
        PROJECT_ROOT / "scripts" / "us_stock_selection" / "35_run_v9_reverse_audit.py",
        PROJECT_ROOT / "quant_lab" / "us_stock_selection" / "v9_reverse_audit.py",
        PROJECT_ROOT / "quant_lab" / "us_stock_selection" / "v9_reverse_audit_reporting.py",
        base / "v9_reverse_audit",
        base / "reports",
        base / "logs",
        base / "RUN_SUMMARY.md",
        base / "NEXT_STEPS.md",
        base / "v9_reverse_audit_verdict.json",
        base / "run_config.yaml",
    ]
    return zip_selected_paths(paths, zip_path, root=PROJECT_ROOT)


def _label_feature_status(time_alignment: pd.DataFrame) -> str:
    if time_alignment.empty or "label_cols_in_feature_cols" not in time_alignment:
        return "unknown"
    values = sorted(
        {
            str(x)
            for x in time_alignment["label_cols_in_feature_cols"].fillna("").astype(str).tolist()
            if str(x).strip()
        }
    )
    return ",".join(values) if values else "none"


def _table(df: pd.DataFrame, columns: list[str] | None = None, max_rows: int = 30) -> str:
    if df is None or df.empty:
        return "_No rows._\n"
    cols = [c for c in (columns or list(df.columns)) if c in df.columns]
    data = df.loc[:, cols].head(max_rows).copy()
    for col in cols:
        if pd.api.types.is_float_dtype(data[col]):
            data[col] = data[col].map(lambda x: "" if pd.isna(x) else f"{float(x):.6f}")
    header = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join(["---"] * len(cols)) + " |"
    rows = ["| " + " | ".join(str(row[c]).replace("|", "/") for c in cols) + " |" for _, row in data.iterrows()]
    return "\n".join([header, sep, *rows]) + "\n"
