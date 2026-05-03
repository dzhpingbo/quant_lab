"""Report and packaging helpers for the v4 Qlib-first research path."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from quant_lab.us_stock_selection.utils import (
    PROJECT_ROOT,
    save_text,
    write_excel,
    zip_selected_paths,
)


def build_v4_report(
    report_path: Path | str,
    config: dict[str, Any],
    qlib_env_status: dict[str, Any],
    qlib_data_status: dict[str, Any],
    model_runs: pd.DataFrame,
    signal_quality: pd.DataFrame,
    strategy_results: pd.DataFrame,
    benchmark_comparison: pd.DataFrame,
    walk_forward_summary: pd.DataFrame,
    overfit_summary: pd.DataFrame,
    universe_df: pd.DataFrame,
) -> Path:
    """Build the mandatory v4 markdown report."""
    best_strategy = strategy_results.head(1).copy()
    best_quality = signal_quality.head(1).copy()
    qqq_compare = _comparison_slice(benchmark_comparison)
    cagr20_count = int(strategy_results.get("passes_cagr_20", pd.Series(dtype=bool)).fillna(False).sum()) if not strategy_results.empty else 0
    calmar1_count = int(strategy_results.get("passes_calmar_1", pd.Series(dtype=bool)).fillna(False).sum()) if not strategy_results.empty else 0
    both_count = int((strategy_results.get("passes_cagr_20", pd.Series(dtype=bool)).fillna(False) & strategy_results.get("passes_calmar_1", pd.Series(dtype=bool)).fillna(False)).sum()) if not strategy_results.empty else 0
    runtime_true = bool(qlib_env_status.get("qlib_import_ok"))
    data_true = bool(qlib_data_status.get("true_qlib_data_used"))
    report = f"""# US Stock Selection v4 Qlib-First Report

## 1. Qlib Runtime And Data

- Qlib runtime import: `{runtime_true}`
- pyqlib version: `{qlib_env_status.get("qlib_version")}`
- Python executable: `{qlib_env_status.get("python_executable")}`
- Qlib provider URI: `{qlib_data_status.get("provider_uri")}`
- True Qlib US provider used: `{data_true}`
- Data mode: `{qlib_data_status.get("data_mode")}`

本轮会如实区分 runtime 和 provider：runtime 已安装并不等于已经完成 Qlib 官方 US 数据训练。若 provider 不存在，本轮使用 quant_lab 本地 OHLCV/因子缓存构造 qlib-like panel 跑横截面 fallback，并在结果中标注。

## 2. Universe

- 本轮 Pool A: core_etf + mag7 + growth_expansion。
- Nasdaq100/S&P500: 未盲目扩展；只有在 Qlib provider 数据可读且 Pool A 信号有效后再建议扩展。

{_table(universe_df.head(40), ["ticker", "universe_name", "asset_type", "theme", "is_leveraged"])}

## 3. Feature Sets And Models

- 尝试特征集：Alpha158-like、Alpha360-like、Alpha158+custom。
- 若 true Qlib provider 缺失，上述为基于本地因子工程的等价 fallback，不冒充 Qlib Alpha158/Alpha360 handler 训练。
- 模型运行数：{len(model_runs)}

{_table(model_runs.head(20), ["run_id", "feature_set", "model", "label", "status", "runtime_backend", "train_rows", "valid_rows", "test_rows"])}

## 4. Best Feature Set / Model / Label

{_table(best_quality, ["run_id", "feature_set", "model", "label", "test_rank_ic_mean", "test_rank_icir", "long_short_spread", "turnover", "runtime_backend"])}

## 5. Signal IC Quality

{_table(signal_quality.head(20), ["run_id", "feature_set", "model", "label", "valid_rank_ic_mean", "test_rank_ic_mean", "test_rank_icir", "top_quantile_forward_return", "bottom_quantile_forward_return", "long_short_spread"])}

## 6. Qlib Signal Portfolio Backtests

{_table(strategy_results.head(20), ["strategy_id", "feature_set", "model", "label", "portfolio_template", "cagr", "max_drawdown", "calmar", "sharpe", "annual_turnover", "passes_cagr_20", "passes_calmar_1"])}

## 7. Benchmark Comparison

{_table(qqq_compare, ["name", "type", "cagr", "max_drawdown", "calmar", "sharpe", "annual_turnover", "return_2022", "crash_2020_max_drawdown"])}

## 8. Acceptance Questions

- 是否出现 test CAGR >= 20%: `{cagr20_count > 0}`，数量 `{cagr20_count}`。
- 是否出现 Calmar > 1: `{calmar1_count > 0}`，数量 `{calmar1_count}`。
- 是否同时满足 CAGR >= 20% 且 Calmar > 1: `{both_count > 0}`，数量 `{both_count}`。
- 是否跑赢 QQQ/QLD/TQQQ/SPY: 见 `benchmark/comparison_v4.csv` 的 `cagr_gt_*` 与 `calmar_gt_*` 字段。

## 9. Walk-Forward

本轮对前 5 个 Qlib signal strategy 使用 anchored expanding retrain。它比全样本一次训练更严格，但仍比完整滚动多模型大网格便宜，后续可加大成本做完整滚动训练。

{_table(walk_forward_summary.head(20), ["strategy_id", "wf_window_count", "wf_mean_cagr", "wf_mean_calmar", "wf_pass_cagr20_rate", "wf_pass_calmar1_rate"])}

## 10. Overfit Checks

{_table(overfit_summary.head(20), ["strategy_id", "overfit_label", "overfit_penalty", "ic_decay_risk", "single_year_contribution_risk", "turnover_risk", "holding_concentration_risk", "max_average_ticker", "nvda_tqqq_average_weight"])}

## 11. Qlib Portfolio vs Single-Asset Timing

v1/v2/v3 的主要瓶颈是单票择时大多变成 risk reducer，难以在 test CAGR 上超过 buy-and-hold。v4 重点改为横截面打分和组合构建，更适合回答“在当前策略能力范围内，哪些标的/组合更容易被挖掘”。单票择时仍可作为 guardrail，而不是主引擎。

## 12. Current Research Recommendation

- 若本轮有稳定 IC 且组合 Calmar > 1：下一轮优先扩大 Pool A 到 Nasdaq100，并保留同一审计框架。
- 若只有 Calmar 改善但 CAGR 不强：优先增强 feature set 和 Qlib provider 数据，而不是继续堆单票模板。
- 若结果集中买入 NVDA/TQQQ 或单一年份贡献过高：先处理集中度和过拟合，再谈实盘。
- 财务数据、新闻情绪、期权波动率、宏观数据建议作为下一阶段扩因子方向；当前结果仍应视作研究候选，不直接视为可交易系统。
"""
    return save_text(report, report_path)


def build_v4_excel(
    output_path: Path | str,
    sheets: dict[str, pd.DataFrame],
) -> Path:
    return write_excel(sheets, output_path)


def package_v4_run(run_dir: Path | str, timestamp: str) -> Path:
    base = Path(run_dir).resolve()
    zip_path = base.parent / f"us_stock_selection_quant_lab_v4_qlib_first_{timestamp}.zip"
    paths = [
        PROJECT_ROOT / "configs" / "us_stock_selection",
        PROJECT_ROOT / "scripts" / "us_stock_selection",
        PROJECT_ROOT / "quant_lab" / "us_stock_selection",
        PROJECT_ROOT / "README_US_STOCK_SELECTION.md",
        base / "qlib_env",
        base / "qlib_data",
        base / "qlib_model_lab",
        base / "qlib_signal_backtest",
        base / "qlib_walk_forward",
        base / "qlib_overfit",
        base / "benchmark",
        base / "ranking",
        base / "reports",
        base / "logs",
        PROJECT_ROOT / "outputs" / "us_stock_selection" / "qlib_setup_instructions.md",
    ]
    return zip_selected_paths(paths, zip_path, root=PROJECT_ROOT)


def _comparison_slice(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    benchmark = df.loc[df.get("type", pd.Series(index=df.index, dtype=str)).eq("benchmark")]
    qlib = df.loc[df.get("type", pd.Series(index=df.index, dtype=str)).eq("qlib_signal_strategy")].head(10)
    return pd.concat([benchmark, qlib], ignore_index=True)


def _table(df: pd.DataFrame, columns: list[str] | None = None) -> str:
    if df is None or df.empty:
        return "_No rows_\n"
    cols = [col for col in (columns or list(df.columns)) if col in df.columns]
    if not cols:
        return "_No display columns_\n"
    subset = df.loc[:, cols].copy().fillna("")
    header = "| " + " | ".join(cols) + " |"
    separator = "| " + " | ".join(["---"] * len(cols)) + " |"
    rows = []
    for _, row in subset.iterrows():
        rows.append("| " + " | ".join(str(row[col]).replace("|", "/") for col in cols) + " |")
    return "\n".join([header, separator, *rows]) + "\n"
