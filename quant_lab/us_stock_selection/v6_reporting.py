"""Reporting and packaging for v6 local Qlib provider workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from quant_lab.us_stock_selection.utils import PROJECT_ROOT, save_text, write_excel, zip_selected_paths


def build_v6_report(
    report_path: Path | str,
    source_status: dict[str, Any],
    provider_status: dict[str, Any],
    workflow_outputs: dict[str, pd.DataFrame],
    portfolio_outputs: dict[str, pd.DataFrame],
    benchmark: pd.DataFrame,
    wf_outputs: dict[str, pd.DataFrame],
    overfit_outputs: dict[str, Any],
) -> Path:
    """Write the v6 markdown report."""
    health = provider_status.get("provider_health", {})
    alpha = provider_status.get("alpha_handler_check", {})
    dump_bin = provider_status.get("dump_bin", {})
    model_runs = workflow_outputs.get("model_runs", pd.DataFrame())
    signal_quality = workflow_outputs.get("signal_quality", pd.DataFrame())
    robust = portfolio_outputs.get("results", pd.DataFrame())
    yearly = portfolio_outputs.get("yearly", pd.DataFrame())
    cost = portfolio_outputs.get("cost_sensitivity", pd.DataFrame())
    concentration = portfolio_outputs.get("concentration", pd.DataFrame())
    wf_summary = wf_outputs.get("summary", pd.DataFrame())
    overfit_summary = overfit_outputs.get("summary", pd.DataFrame())
    verdict = overfit_outputs.get("verdict", {})
    best = robust.head(1)
    text = f"""# US Stock Selection v6 Local Qlib Workflow Report

## 1. Local Qlib Bin Provider

- qlib source: `{source_status.get("selected_source")}`
- dump_bin exists: `{source_status.get("dump_bin_exists")}`
- dump_bin returncode: `{dump_bin.get("returncode")}`
- local provider: `{health.get("provider_uri")}`
- provider readable: `{health.get("provider_readable")}`
- calendar: `{health.get("calendar_start")}` to `{health.get("calendar_end")}`, count `{health.get("calendar_count")}`
- covers 2022-2026: `{health.get("covers_2022_to_2026")}`
- Pool A available: `{health.get("pool_a_available_count")}`
- missing tickers: `{health.get("pool_a_missing")}`

## 2. Alpha Handler Check

| handler | success | rows | columns | label_non_na | error |
| --- | --- | ---: | ---: | ---: | --- |
| Alpha158 | {alpha.get("Alpha158", {}).get("success")} | {alpha.get("Alpha158", {}).get("rows")} | {alpha.get("Alpha158", {}).get("columns")} | {alpha.get("Alpha158", {}).get("label_non_na")} | {alpha.get("Alpha158", {}).get("error", "")} |
| Alpha360 | {alpha.get("Alpha360", {}).get("success")} | {alpha.get("Alpha360", {}).get("rows")} | {alpha.get("Alpha360", {}).get("columns")} | {alpha.get("Alpha360", {}).get("label_non_na")} | {alpha.get("Alpha360", {}).get("error", "")} |

## 3. Qlib Workflow

qrun status is recorded in `qlib_workflow/qrun_status.json`. Workflow-by-code is the primary v6 path and uses Qlib Handler + DatasetH + model.fit/model.predict. SignalRecord is attempted for Qlib-native models.

{_table(model_runs.head(20), ["run_id", "feature_set", "model", "label", "status", "workflow_by_code", "qrun_attempted", "qrun_success", "signal_record_success", "failure_reason"])}

## 4. Signal Quality

{_table(signal_quality.head(15), ["run_id", "feature_set", "model", "label", "test_ic_mean", "test_icir", "test_rank_ic_mean", "test_rank_icir", "top_quantile_forward_return", "long_short_spread"])}

## 5. Robust Portfolio Results

Top1 is not used as the main conclusion in v6. The table below focuses on Top3/Top5, capped weights, dropout, safe switch, volatility scaling, and crash filter portfolios.

{_table(robust.head(15), ["strategy_id", "feature_set", "model", "label", "portfolio_template", "cagr", "max_drawdown", "calmar", "sharpe", "annual_turnover", "avg_herfindahl", "top_holding", "top_holding_contribution", "passes_cagr_20", "passes_calmar_1"])}

## 6. Benchmarks

{_table(benchmark.head(20), ["name", "type", "cagr", "max_drawdown", "calmar", "sharpe", "annual_turnover"])}

## 7. Yearly Returns

{_table(yearly.head(30), ["strategy_id", "year", "year_return"])}

## 8. Cost Sensitivity

{_table(cost.head(30), ["strategy_id", "cost_bps_each_side", "cagr", "max_drawdown", "calmar", "annual_turnover"])}

## 9. Concentration

{_table(concentration.head(20), ["strategy_id", "avg_herfindahl", "max_herfindahl", "top_holding", "top_holding_contribution", "top_holding_avg_weight"])}

## 10. Walk-Forward

The saved `wf_summary.csv` is a calendar-forward window check for the already trained signal. A stricter Handler retrain walk-forward was attempted after the main v6 run, but it timed out twice on Windows; therefore this section is weak evidence, not a final tradability proof.

{_table(wf_summary.head(20), ["strategy_id", "window_count", "mean_cagr", "mean_calmar", "min_calmar", "pass_cagr20_rate", "pass_calmar1_rate"])}

## 11. Overfit Verdict

{_table(overfit_summary.head(5), ["strategy_id", "cagr", "max_drawdown", "calmar", "top_holding", "top_holding_contribution", "top_year_abs_share", "classification"])}

Final classification: `{verdict.get("classification")}`

## 12. Answers

1. local qlib bin provider: `{provider_status.get("local_provider_success")}`.
2. Alpha158/Alpha360 Handler: Alpha158 `{alpha.get("Alpha158", {}).get("success")}`, Alpha360 `{alpha.get("Alpha360", {}).get("success")}`.
3. qrun success: see `qrun_status.json`; workflow-by-code success is reflected in completed rows of `model_runs.csv`.
4. v4 35% CAGR replication: v6 uses true local qlib bin + Handler, so it is a stricter re-test. Compare robust rows to v4; Top1 is intentionally not promoted.
5. CAGR >= 20% and Calmar >= 1: `{bool((not robust.empty) and ((robust["cagr"] >= 0.20) & (robust["calmar"] >= 1.0)).any())}`.
6. Expansion recommendation: do not expand Nasdaq100 until local-provider Handler workflow is stable under Top3/Top5 and walk-forward.
"""
    return save_text(text, report_path)


def build_v6_excel(path: Path | str, sheets: dict[str, pd.DataFrame]) -> Path:
    return write_excel(sheets, path)


def package_v6_run(run_dir: Path | str, timestamp: str) -> Path:
    base = Path(run_dir).resolve()
    zip_path = base.parent / f"us_stock_selection_quant_lab_v6_local_qlib_workflow_{timestamp}.zip"
    paths = [
        PROJECT_ROOT / "configs" / "us_stock_selection",
        PROJECT_ROOT / "scripts" / "us_stock_selection",
        PROJECT_ROOT / "quant_lab" / "us_stock_selection",
        PROJECT_ROOT / "README_US_STOCK_SELECTION.md",
        base / "qlib_source",
        base / "qlib_local_provider",
        base / "qlib_workflow",
        base / "v6_portfolio_backtest",
        base / "v6_walk_forward",
        base / "v6_overfit",
        base / "benchmark",
        base / "ranking",
        base / "reports",
        base / "logs",
    ]
    return zip_selected_paths(paths, zip_path, root=PROJECT_ROOT)


def _table(df: pd.DataFrame, columns: list[str]) -> str:
    if df is None or df.empty:
        return "_No rows_\n"
    cols = [c for c in columns if c in df.columns]
    if not cols:
        return "_No display columns_\n"
    sub = df.loc[:, cols].copy().fillna("")
    header = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join(["---"] * len(cols)) + " |"
    rows = ["| " + " | ".join(str(row[c]).replace("|", "/") for c in cols) + " |" for _, row in sub.iterrows()]
    return "\n".join([header, sep, *rows]) + "\n"
