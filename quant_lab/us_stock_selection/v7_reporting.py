"""Reporting, run summaries, and packaging for v7 fast walk-forward."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from quant_lab.us_stock_selection.utils import PROJECT_ROOT, save_text, write_excel, zip_selected_paths


def build_v7_report(
    report_path: Path | str,
    cache_status: pd.DataFrame,
    wf_detail: pd.DataFrame,
    wf_summary: pd.DataFrame,
    assessment: dict[str, Any],
) -> Path:
    """Write the v7 markdown report."""
    best = assessment.get("best", {}) if isinstance(assessment, dict) else {}
    text = f"""# US Stock Selection v7 Fast Walk-Forward Report

## 1. Objective

v7 addresses the v6 bottleneck: strict Handler retrain walk-forward timed out on Windows because every WF window reinitialized Qlib Handler. v7 precomputes Alpha158/Alpha360 Handler output into parquet once, then slices parquet for each retrain window.

## 2. Feature Cache

{_table(cache_status, ["feature_set", "status", "rows", "date_start", "date_end", "instrument_count", "feature_count", "label_5d_non_na", "label_20d_non_na", "error"])}

## 3. Fast Strict Walk-Forward

Each row in `v7_fast_walk_forward/wf_detail.csv` is a retrained model for one train/test window and one robust portfolio template. Top1 is not used.

{_table(wf_summary.head(30), ["feature_set", "model", "label", "portfolio_template", "wf_family", "window_count", "mean_cagr", "mean_calmar", "min_calmar", "pass_cagr20_rate", "pass_calmar1_rate", "avg_herfindahl", "top_holding_contribution"])}

## 4. Best Combined Candidate

- Classification: `{assessment.get("classification")}`
- Reason: `{assessment.get("reason")}`
- Strict WF passed: `{assessment.get("strict_walk_forward_passed")}`
- Best strategy key: `{best.get("strategy_key")}`
- Mean CAGR: `{best.get("mean_cagr")}`
- Mean Calmar: `{best.get("mean_calmar")}`
- CAGR>=20 pass rate: `{best.get("pass_cagr20_rate")}`
- Calmar>=1 pass rate: `{best.get("pass_calmar1_rate")}`
- Eligible CAGR windows (>=126d): `{best.get("eligible_cagr_windows")}`
- Eligible Calmar windows (>=252d): `{best.get("eligible_calmar_windows")}`
- Raw mean Calmar before conservative clipping: `{best.get("raw_mean_calmar")}`
- Conservative Calmar winsor mean: `{best.get("calmar_winsor_mean_all")}`
- Avg Herfindahl: `{best.get("avg_herfindahl")}`
- Top holding contribution: `{best.get("top_holding_contribution")}`

## 5. Portfolio Focus

v7 only evaluates:

- Top5 equal monthly
- Top5 dropout monthly
- Top10 dropout monthly

This follows the v6 conclusion that Top1 should not be the main research line.

## 6. Interpretation

- `credible_research_candidate` means the result should be sent to ChatGPT/user review before expanding the pool.
- `promising_but_needs_more_validation` means do not enter v8 yet; fix/audit the weak evidence first.
- `promising_but_unstable` means continue robustness work without expanding Nasdaq100.
- `likely_overfit` means do not expand; perform failure review or change research route.
"""
    return save_text(text, report_path)


def build_v7_excel(path: Path | str, sheets: dict[str, pd.DataFrame]) -> Path:
    return write_excel(sheets, path)


def build_run_summary(path: Path | str, run_dir: Path | str, zip_path: Path | str, assessment: dict[str, Any]) -> Path:
    best = assessment.get("best", {}) if isinstance(assessment, dict) else {}
    text = f"""# RUN_SUMMARY

本轮目标：v7 fast walk-forward，通过 parquet feature cache 避免重复 Qlib Handler 重算。

新 run 目录：`{Path(run_dir)}`

zip 路径：`{Path(zip_path)}`

当前分类：`{assessment.get("classification")}`

原因：{assessment.get("reason")}

最佳策略：`{best.get("strategy_key")}`

核心指标：
- mean_cagr: `{best.get("mean_cagr")}`
- mean_calmar: `{best.get("mean_calmar")}`
- raw_mean_calmar: `{best.get("raw_mean_calmar")}`
- eligible_cagr_windows: `{best.get("eligible_cagr_windows")}`
- eligible_calmar_windows: `{best.get("eligible_calmar_windows")}`
- pass_cagr20_rate: `{best.get("pass_cagr20_rate")}`
- pass_calmar1_rate: `{best.get("pass_calmar1_rate")}`
- avg_herfindahl: `{best.get("avg_herfindahl")}`
- top_holding_contribution: `{best.get("top_holding_contribution")}`

严格 WF 是否通过：`{assessment.get("strict_walk_forward_passed")}`
"""
    return save_text(text, path)


def update_next_steps(path: Path | str, assessment: dict[str, Any]) -> Path:
    classification = assessment.get("classification")
    if classification == "promising_but_needs_more_validation":
        body = """# NEXT_STEPS

当前下一步：继续 v7 修复/审计，不进入 v8，不扩 Nasdaq100/S&P500。

优先事项：
1. 复核严格 TopKDropout 替换规则；
2. 用 v7_audit 检查 reported vs recomputed、成本、同窗口基准；
3. 短窗口只作为辅助证据，不把年化 Calmar 当主结论；
4. 只有审计转为 credible_research_candidate 后，才讨论 v8。
"""
        return save_text(body, path)
    if classification == "credible_research_candidate":
        body = """# NEXT_STEPS

v7 fast walk-forward 达到 credible_research_candidate。

下一步：暂停自动扩池，把 RUN_SUMMARY.md 和 v7 报告发给 ChatGPT/用户审阅后再决定是否进入 v8。
"""
    elif classification == "promising_but_unstable":
        body = """# NEXT_STEPS

当前下一步：执行 v8 稳健组合优化，但仍不扩 Nasdaq100/S&P500。

优先事项：
1. 围绕 v7 最佳 Top5/Top10 组合做 vol targeting、turnover penalty、crash filter；
2. 做成本 5/10/20/50 bps 压力测试；
3. 做 leave-one-ticker 和 leave-one-window 复验；
4. 若 v8 改善，再考虑科技成长池扩展；
5. 若 v8 不改善，生成失败复盘。
"""
    else:
        body = """# NEXT_STEPS

当前下一步：v7 未通过，暂不扩池。

优先事项：
1. 复盘 fast WF 失败窗口；
2. 检查 Alpha158/Alpha360 标签和交易对齐；
3. 降低模型复杂度或改用更稳健的 Top10；
4. 若下一轮仍无改进，准备失败复盘。
"""
    return save_text(body, path)


def package_v7_run(run_dir: Path | str, timestamp: str) -> Path:
    base = Path(run_dir).resolve()
    zip_path = base.parent / f"us_stock_selection_quant_lab_v7_fast_wf_{timestamp}.zip"
    paths = [
        PROJECT_ROOT / "AGENTS.md",
        PROJECT_ROOT / "NEXT_STEPS.md",
        PROJECT_ROOT / "RUN_SUMMARY.md",
        PROJECT_ROOT / "docs" / "US_STOCK_SELECTION_AUTORUN.md",
        PROJECT_ROOT / "configs" / "us_stock_selection",
        PROJECT_ROOT / "scripts" / "us_stock_selection",
        PROJECT_ROOT / "quant_lab" / "us_stock_selection",
        PROJECT_ROOT / "README_US_STOCK_SELECTION.md",
        base / "v7_feature_cache",
        base / "v7_fast_walk_forward",
        base / "v7_reports",
        base / "benchmark",
        base / "ranking",
        base / "reports",
        base / "logs",
        base / "RUN_SUMMARY.md",
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
