"""Reporting and packaging helpers for v9 small growth-pool pre-research."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from quant_lab.us_stock_selection.utils import PROJECT_ROOT, save_text, write_excel, zip_selected_paths


def build_v9_report(
    path: Path | str,
    results: pd.DataFrame,
    excluded: pd.DataFrame,
    ticker_contribution: pd.DataFrame,
    verdict: dict[str, Any],
) -> Path:
    pool = _row(results, "pool_a_v8_2_reproduction")
    expanded = _row(results, "pool_a_plus_small_growth")
    small = _row(results, "small_growth_only")
    no_extreme = _row(results, "pool_a_plus_small_growth_ex_extreme_vol")
    top_new = _top_new_tickers(ticker_contribution)
    text = f"""# US Stock Selection v9 Small Growth Pool Pre-Research Report

## Scope

本轮已获批准进入 v9，但范围仅限“小幅科技成长池预研”。

Hard constraints:

- 不扩 Nasdaq100。
- 不扩 S&P500。
- 不做全市场扩池。
- 不重新搜索模型。
- 不重新选择策略。
- 不交易化。

Frozen strategy:

- Feature set: Alpha360
- Model: LGBModel
- Label: label_5d
- Portfolio: top5_ytdcap80p_derisk100p
- Execution: T+1
- Cost/slippage: 5bps + 5bps
- Max single weight: 20%
- YTD return cap: 80%
- Derisk after trigger: 100%

## Data Quality

- Excluded ticker count: `{len(excluded)}`
- Excluded tickers: `{", ".join(excluded.get("ticker", pd.Series(dtype=str)).astype(str).tolist()) if not excluded.empty else ""}`

## Core Results

### Pool A reproduction

{_kv(pool)}

### Pool A + small growth

{_kv(expanded)}

### Small growth only

{_kv(small)}

### Pool A + small growth excluding extreme-vol names

{_kv(no_extreme)}

## New Ticker Contribution / Selection

{_table(top_new, ["universe_name", "ticker", "return_contribution", "abs_share"], max_rows=20)}

## All Universe Results

{_table(results, [
    "universe_name",
    "ticker_count",
    "top_k",
    "cagr",
    "max_drawdown",
    "calmar",
    "cost50_t1_cagr",
    "cost50_t1_calmar",
    "single_year_share",
    "top_ticker",
    "top_ticker_share",
    "remove_top_year_cagr",
    "remove_top_year_calmar",
    "remove_top_ticker_cagr",
    "remove_top_ticker_calmar",
    "v9_gate_pass",
    "classification",
], max_rows=20)}

## Required Answers

1. 扩科技成长池是否提升，还是降低稳健性：见 Pool A 与 Pool A + small growth 对比；gate 使用 80% Pool A 保真阈值。
2. 新增股票中哪些被选入/贡献最多：见 `v9_ticker_contribution.csv` 与 `v9_monthly_holdings.csv`。
3. 是否依赖 MSTR/COIN/PLTR：见 `extreme_vol_contribution_share`、top ticker share 和 ex-extreme-vol 对照。
4. small growth only 是否可行：见 `small_growth_only` 行。
5. 剔除极高波动票后是否仍有效：见 `pool_a_plus_small_growth_ex_extreme_vol` 行。
6. 是否允许进入 v10：`{verdict.get("allow_enter_v10")}`。
7. v10 是否可以扩 Nasdaq100：不可以自动扩；如继续，应优先行业主题池或更严格 universe 设计，不应直接扩 Nasdaq100/S&P500。

## Cycle Verdict

- Classification: `{verdict.get("classification")}`
- Allow entering v10: `{verdict.get("allow_enter_v10")}`
- Effective small-growth count: `{verdict.get("effective_small_growth_count")}`
- Excluded ticker count: `{verdict.get("excluded_ticker_count")}`

This remains a research pre-validation package and is not a live trading recommendation.
"""
    return save_text(text, path)


def build_v9_excel(path: Path | str, sheets: dict[str, pd.DataFrame]) -> Path:
    return write_excel(sheets, path)


def package_v9_run(run_dir: Path | str, timestamp: str) -> Path:
    base = Path(run_dir).resolve()
    zip_path = base.parent / f"us_stock_selection_quant_lab_v9_growth_pool_{timestamp}.zip"
    paths = [
        PROJECT_ROOT / "AGENTS.md",
        PROJECT_ROOT / "NEXT_STEPS.md",
        PROJECT_ROOT / "RUN_SUMMARY.md",
        PROJECT_ROOT / "scripts" / "us_stock_selection" / "34_run_v9_growth_pool.py",
        PROJECT_ROOT / "quant_lab" / "us_stock_selection" / "v9_growth_pool.py",
        PROJECT_ROOT / "quant_lab" / "us_stock_selection" / "v9_reporting.py",
        base / "v9_growth_pool",
        base / "reports",
        base / "logs",
        base / "RUN_SUMMARY.md",
        base / "run_config.yaml",
    ]
    return zip_selected_paths(paths, zip_path, root=PROJECT_ROOT)


def _row(df: pd.DataFrame, universe_name: str) -> dict[str, Any]:
    if df is None or df.empty or "universe_name" not in df:
        return {}
    rows = df.loc[(df["universe_name"] == universe_name) & (df["top_k"] == 5)]
    if rows.empty:
        rows = df.loc[df["universe_name"] == universe_name]
    return rows.iloc[0].to_dict() if not rows.empty else {}


def _kv(row: dict[str, Any]) -> str:
    if not row:
        return "_No result_\n"
    keys = [
        "universe_name",
        "ticker_count",
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
        "v9_gate_pass",
        "classification",
    ]
    out = []
    for key in keys:
        value = row.get(key, "")
        if isinstance(value, float):
            value = f"{value:.6f}"
        out.append(f"- {key}: `{value}`")
    return "\n".join(out) + "\n"


def _top_new_tickers(contrib: pd.DataFrame) -> pd.DataFrame:
    if contrib is None or contrib.empty:
        return pd.DataFrame()
    return contrib.loc[contrib["universe_name"].astype(str).str.contains("small_growth", na=False)].sort_values("abs_share", ascending=False)


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
