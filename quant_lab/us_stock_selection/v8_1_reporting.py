"""Reporting and packaging helpers for v8.1 model switch."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from quant_lab.us_stock_selection.utils import PROJECT_ROOT, save_text, write_excel, zip_selected_paths


def build_v8_1_report(
    path: Path | str,
    summary: pd.DataFrame,
    cycle_verdict: dict[str, Any],
    lgb_stability: pd.DataFrame,
    ridge_stability: pd.DataFrame,
) -> Path:
    text = f"""# US Stock Selection v8.1 Model Switch Report

## Objective

v8.1 does not enter v9, does not expand Nasdaq100/S&P500, and does not trade-live. It freezes the v7 best strategy shape and switches the main model away from ElasticNet:

- Alpha360 + LGBModel + label_5d + Top5 equal monthly
- Alpha360 + Ridge + label_5d + Top5 equal monthly

ElasticNet is retained only as historical context because the v8 convergence warning rate remained 1.0.

## Cycle Verdict

- Classification: `{cycle_verdict.get("classification")}`
- Allow entering v9: `{cycle_verdict.get("allow_enter_v9")}`
- Best model branch: `{cycle_verdict.get("best_model_branch")}`
- Reason: `{cycle_verdict.get("reason")}`

## Model Summary

{_table(summary, [
    "model_branch",
    "classification",
    "allow_enter_v9",
    "paper_cagr",
    "paper_calmar",
    "paper_max_drawdown",
    "cost50_t1_cagr",
    "cost50_t1_calmar",
    "t2_cagr",
    "t2_calmar",
    "top_ticker",
    "top_ticker_share",
    "single_year_share",
    "remove_top_ticker_cagr",
    "remove_top_year_cagr",
    "warning_decision_rate",
])}

## LGBModel Stability

{_table(lgb_stability, [
    "model",
    "diagnostic_decision_count",
    "warning_count",
    "warning_decision_rate",
    "top10_feature_importance_share",
    "max_ticker_selection_share",
    "feature_concentration_flag",
    "selection_concentration_flag",
])}

## Ridge Stability

{_table(ridge_stability, [
    "model",
    "diagnostic_decision_count",
    "warning_count",
    "warning_decision_rate",
    "max_ticker_selection_share",
    "selection_concentration_flag",
])}

## Required Answers

1. LGBModel can replace ElasticNet: `{_model_class(summary, "Alpha360_LGBModel")}`.
2. Ridge can replace ElasticNet: `{_model_class(summary, "Alpha360_Ridge")}`.
3. More stable model: `{cycle_verdict.get("best_model_branch")}` by current gate ranking.
4. Convergence warning bottleneck: LGBModel has no ElasticNet convergence issue; Ridge warnings, if any, are recorded separately.
5. Single-year share below 50%: see `single_year_share` in the model summary.
6. Remove top year still effective: see `remove_top_year_cagr` and per-branch `leave_one_year_out.csv`.
7. Allow v9: `{cycle_verdict.get("allow_enter_v9")}`.
8. If v9 is allowed later, it must remain a small tech-growth expansion, not Nasdaq100/S&P500 expansion.

## Caveats

This is still a research validation package. It is not a trading recommendation and it does not claim production readiness.
"""
    return save_text(text, path)


def build_v8_1_excel(path: Path | str, sheets: dict[str, pd.DataFrame]) -> Path:
    return write_excel(sheets, path)


def package_v8_1_run(run_dir: Path | str, timestamp: str) -> Path:
    base = Path(run_dir).resolve()
    zip_path = base.parent / f"us_stock_selection_quant_lab_v8_1_model_switch_{timestamp}.zip"
    paths = [
        PROJECT_ROOT / "AGENTS.md",
        PROJECT_ROOT / "NEXT_STEPS.md",
        PROJECT_ROOT / "RUN_SUMMARY.md",
        PROJECT_ROOT / "scripts" / "us_stock_selection" / "32_run_v8_1_model_switch.py",
        PROJECT_ROOT / "quant_lab" / "us_stock_selection" / "v8_1_model_switch.py",
        PROJECT_ROOT / "quant_lab" / "us_stock_selection" / "v8_1_reporting.py",
        base / "v8_1_model_switch",
        base / "reports",
        base / "logs",
        base / "RUN_SUMMARY.md",
        base / "run_config.yaml",
    ]
    return zip_selected_paths(paths, zip_path, root=PROJECT_ROOT)


def _model_class(summary: pd.DataFrame, branch: str) -> str:
    if summary is None or summary.empty or "model_branch" not in summary:
        return "no_result"
    row = summary.loc[summary["model_branch"] == branch]
    if row.empty:
        return "not_run"
    return str(row.iloc[0].get("classification", "unknown"))


def _table(df: pd.DataFrame, columns: list[str], max_rows: int = 30) -> str:
    if df is None or df.empty:
        return "_No rows_\n"
    cols = [c for c in columns if c in df.columns]
    sub = df.loc[:, cols].head(max_rows).copy()
    for col in cols:
        if pd.api.types.is_float_dtype(sub[col]):
            sub[col] = sub[col].map(lambda x: "" if pd.isna(x) else f"{float(x):.6f}")
    header = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join(["---"] * len(cols)) + " |"
    rows = ["| " + " | ".join(str(row[c]).replace("|", "/") for c in cols) + " |" for _, row in sub.iterrows()]
    return "\n".join([header, sep, *rows]) + "\n"

