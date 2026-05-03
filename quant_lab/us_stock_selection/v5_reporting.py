"""v5 report and packaging helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from quant_lab.us_stock_selection.utils import PROJECT_ROOT, save_text, write_excel, zip_selected_paths


def build_v5_report(
    report_path: Path | str,
    provider_health: dict[str, Any],
    local_conversion: dict[str, Any],
    true_results: pd.DataFrame,
    fallback_audit_summary: dict[str, Any],
    leakage: dict[str, Any],
    holdings: pd.DataFrame,
    yearly_return: pd.DataFrame,
    wf_summary: pd.DataFrame,
    stress: dict[str, pd.DataFrame],
) -> Path:
    true_best = true_results.head(10)
    top_holdings = holdings.head(10)
    top_years = yearly_return.sort_values("abs_return_contribution_share", ascending=False).head(10) if not yearly_return.empty else yearly_return
    classification = fallback_audit_summary.get("classification", "unknown")
    base = fallback_audit_summary.get("base_metrics", {})
    text = f"""# US Stock Selection v5 True Qlib + Audit Report

## 1. True Qlib Provider Status

- Provider URI: `{provider_health.get("provider_uri")}`
- Provider exists: `{provider_health.get("provider_exists")}`
- Provider readable: `{provider_health.get("provider_readable")}`
- Calendar: `{provider_health.get("calendar_start")}` to `{provider_health.get("calendar_end")}`, count `{provider_health.get("calendar_count")}`
- Pool A available: `{provider_health.get("pool_a_available_count")}`
- Missing Pool A names: `{provider_health.get("pool_a_missing")}`

结论：true Qlib US provider 已下载并可读取，但官方样例数据截止到 `{provider_health.get("calendar_end")}`，无法覆盖 v4 的 2022-2026 test 区间。因此 true provider 结果只能做 2019-2020 的双轨 sanity check，不能直接证明 v4 的 2022-2026 表现。

## 2. Local Qlib Bin Conversion Fallback

- CSV export count: `{local_conversion.get("exported_count")}`
- Missing count: `{local_conversion.get("missing_count")}`
- factor note: `{local_conversion.get("factor_note")}`
- dump command: `{local_conversion.get("dump_bin_command")}`

## 3. True Provider Lab Best Results

{_table(true_best, ["strategy_id", "portfolio", "cagr", "max_drawdown", "calmar", "sharpe", "annual_turnover", "passes_cagr_20", "passes_calmar_1"])}

## 4. v4 Best Strategy Audit Summary

- Strategy: `alpha158_like + ridge + forward_return_5d + safe_switch monthly Top1`
- v4 reproduced CAGR: `{base.get("cagr")}`
- v4 reproduced MaxDD: `{base.get("max_drawdown")}`
- v4 reproduced Calmar: `{base.get("calmar")}`
- Leakage detected: `{fallback_audit_summary.get("leakage_detected")}`
- Final classification: `{classification}`

## 5. Leakage And Alignment

```json
{leakage}
```

## 6. Holding Concentration

{_table(top_holdings, ["ticker", "average_weight", "max_weight", "holding_days", "holding_day_share", "herfindahl_total"])}

## 7. Return Sources By Year

{_table(top_years, ["year", "year_return", "abs_return_contribution_share"])}

## 8. Walk-Forward

{_table(wf_summary, ["test_name", "window_count", "mean_cagr", "mean_calmar", "min_calmar", "pass_cagr20_rate", "pass_calmar1_rate"])}

## 9. Stress Tests

### Cost
{_table(stress.get("cost_sensitivity", pd.DataFrame()), ["cost_bps_each_side", "cagr", "max_drawdown", "calmar", "annual_turnover"])}

### Rebalance
{_table(stress.get("rebalance_sensitivity", pd.DataFrame()), ["rebalance", "cagr", "max_drawdown", "calmar", "annual_turnover"])}

### TopK
{_table(stress.get("topk_sensitivity", pd.DataFrame()), ["top_k", "cagr", "max_drawdown", "calmar", "annual_turnover"])}

### Safe Asset
{_table(stress.get("safe_asset_sensitivity", pd.DataFrame()), ["safe_asset", "cagr", "max_drawdown", "calmar", "annual_turnover"])}

### Remove Top Contributors
{_table(stress.get("remove_top_contributor_test", pd.DataFrame()), ["removed", "cagr", "max_drawdown", "calmar"])}

### Leave One Year Out
{_table(stress.get("leave_one_year_out", pd.DataFrame()), ["removed_year", "cagr", "max_drawdown", "calmar"])}

## 10. Conclusion

v4 best result has no obvious leakage in the implemented audit, and trade execution is after prediction. However, walk-forward pass rates and Top1 concentration remain weak points. The correct classification is `{classification}`.

Next step: do not expand Nasdaq100 yet unless true provider is updated past 2022 or local qlib bin provider is built from current quant_lab data and produces close results under the same audit.
"""
    return save_text(text, report_path)


def build_v5_excel(path: Path | str, sheets: dict[str, pd.DataFrame]) -> Path:
    return write_excel(sheets, path)


def package_v5_run(run_dir: Path | str, timestamp: str) -> Path:
    base = Path(run_dir).resolve()
    zip_path = base.parent / f"us_stock_selection_quant_lab_v5_true_qlib_audit_{timestamp}.zip"
    paths = [
        PROJECT_ROOT / "configs" / "us_stock_selection",
        PROJECT_ROOT / "scripts" / "us_stock_selection",
        PROJECT_ROOT / "quant_lab" / "us_stock_selection",
        PROJECT_ROOT / "README_US_STOCK_SELECTION.md",
        base / "qlib_data_true_provider",
        base / "qlib_true_provider_lab",
        base / "v5_audit",
        base / "v5_walk_forward",
        base / "v5_stress_test",
        base / "benchmark",
        base / "ranking",
        base / "reports",
        base / "logs",
    ]
    return zip_selected_paths(paths, zip_path, root=PROJECT_ROOT)


def _table(df: pd.DataFrame, columns: list[str]) -> str:
    if df is None or df.empty:
        return "_No rows_\n"
    cols = [col for col in columns if col in df.columns]
    if not cols:
        return "_No display columns_\n"
    subset = df.loc[:, cols].copy().fillna("")
    header = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join(["---"] * len(cols)) + " |"
    rows = ["| " + " | ".join(str(row[col]).replace("|", "/") for col in cols) + " |" for _, row in subset.iterrows()]
    return "\n".join([header, sep, *rows]) + "\n"
