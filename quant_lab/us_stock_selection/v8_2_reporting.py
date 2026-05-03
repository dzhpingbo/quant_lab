"""Reporting and packaging helpers for v8.2 year-stability replay."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from quant_lab.us_stock_selection.utils import PROJECT_ROOT, save_text, write_excel, zip_selected_paths


def build_v8_2_report(
    path: Path | str,
    results: pd.DataFrame,
    verdict: dict[str, Any],
    benchmark: pd.DataFrame,
) -> Path:
    best = results.iloc[0].to_dict() if results is not None and not results.empty else {}
    v9_ready_count = int(results["allow_enter_v9"].sum()) if results is not None and not results.empty and "allow_enter_v9" in results else 0
    stable_count = int((results["single_year_share"] <= 0.50).sum()) if results is not None and not results.empty and "single_year_share" in results else 0
    text = f"""# US Stock Selection v8.2 Year Stability Report

## Scope

v8.2 does not enter v9, does not expand Nasdaq100/S&P500, and does not trade-live.  The stock-selection mainline is frozen as:

- Alpha360 + LGBModel + label_5d

This run replays portfolio construction and ex-ante risk-control variants from the v8.1 LGBModel full score/rank audit trail.  It does not train a new model and it does not use future-year information.

## Cycle Verdict

- Best strategy: `{verdict.get("best_strategy_id")}`
- Classification: `{verdict.get("classification")}`
- Allow entering v9: `{verdict.get("allow_enter_v9")}`
- Reason: `{verdict.get("reason")}`
- Variants tested: `{verdict.get("variant_count")}`
- Variants passing single-year share <= 50%: `{stable_count}`
- Variants passing all v9 gates: `{v9_ready_count}`

## Best Variant

{_kv(best, [
    "strategy_id",
    "portfolio_template",
    "top_k",
    "max_weight",
    "cagr",
    "calmar",
    "max_drawdown",
    "cost50_t1_cagr",
    "cost50_t1_calmar",
    "single_year_share",
    "top_ticker",
    "top_ticker_share",
    "remove_top_year_cagr",
    "remove_top_year_calmar",
    "remove_top_ticker_cagr",
    "remove_top_ticker_calmar",
    "allow_enter_v9",
    "classification",
])}

## Top Results

{_table(results, [
    "strategy_id",
    "portfolio_template",
    "cagr",
    "calmar",
    "max_drawdown",
    "cost50_t1_cagr",
    "cost50_t1_calmar",
    "single_year_share",
    "top_ticker_share",
    "remove_top_year_cagr",
    "remove_top_year_calmar",
    "remove_top_ticker_cagr",
    "remove_top_ticker_calmar",
    "gate_pass_count",
    "allow_enter_v9",
    "classification",
], max_rows=20)}

## Benchmark Calmar

{_table(benchmark, ["benchmark", "cagr", "max_drawdown", "calmar"], max_rows=10)}

## Required Answers

1. 是否找到 single-year share <= 50% 的 LGBModel 稳健组合：`{stable_count > 0}`。
2. 稳定化后 CAGR/Calmar 下降多少：见 `v8_2_year_stability_results.csv`；报告首行是当前 gate 排序下最佳组合。
3. Top10 是否优于 Top5：查看 TopK variant 行；本报告不因单一 CAGR 自动择优。
4. volatility targeting 是否有效：查看 `top*_voltarget*` 行的 single-year share、Calmar 和 50bps/T+1 指标。
5. YTD/rolling return cap 是否有效：查看 `top*_ytdcap*`、`top*_roll*cap*` 行。
6. 最佳组合是否满足 v9 gate：`{best.get("allow_enter_v9", False)}`。
7. 是否允许进入 v9：`{verdict.get("allow_enter_v9")}`。即使为 True，也需要用户另行批准；本轮不自动进入 v9。
8. 如果允许，v9 也只能考虑小幅科技成长池，不允许 Nasdaq100/S&P500 扩池。
9. 如果不允许，下一步应继续集中度修复或停止扩展，不能扩池补救。

## Caveats

This is a research validation replay.  It is not a live trading recommendation.  All caps and regime filters are computed from information available before or on the trading date, and audit-forward fields are not used.
"""
    return save_text(text, path)


def build_v8_2_excel(path: Path | str, sheets: dict[str, pd.DataFrame]) -> Path:
    return write_excel(sheets, path)


def package_v8_2_run(run_dir: Path | str, timestamp: str) -> Path:
    base = Path(run_dir).resolve()
    zip_path = base.parent / f"us_stock_selection_quant_lab_v8_2_year_stability_{timestamp}.zip"
    paths = [
        PROJECT_ROOT / "AGENTS.md",
        PROJECT_ROOT / "NEXT_STEPS.md",
        PROJECT_ROOT / "RUN_SUMMARY.md",
        PROJECT_ROOT / "scripts" / "us_stock_selection" / "33_run_v8_2_year_stability.py",
        PROJECT_ROOT / "quant_lab" / "us_stock_selection" / "v8_2_year_stability.py",
        PROJECT_ROOT / "quant_lab" / "us_stock_selection" / "v8_2_reporting.py",
        base / "v8_2_year_stability",
        base / "reports",
        base / "logs",
        base / "RUN_SUMMARY.md",
        base / "run_config.yaml",
    ]
    return zip_selected_paths(paths, zip_path, root=PROJECT_ROOT)


def _kv(row: dict[str, Any], keys: list[str]) -> str:
    if not row:
        return "_No result_\n"
    lines = []
    for key in keys:
        value = row.get(key, "")
        if isinstance(value, float):
            value = f"{value:.6f}"
        lines.append(f"- {key}: `{value}`")
    return "\n".join(lines) + "\n"


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
