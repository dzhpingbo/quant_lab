"""Reporting and packaging for v8 paper-trading replay."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from quant_lab.us_stock_selection.utils import PROJECT_ROOT, save_text, write_excel, zip_selected_paths


def classify_v8(
    paper_metrics: dict[str, Any],
    convergence: pd.DataFrame,
    challengers: pd.DataFrame,
    stress: pd.DataFrame,
    attribution: dict[str, pd.DataFrame],
) -> dict[str, Any]:
    cagr = float(paper_metrics.get("cagr", 0.0))
    calmar = float(paper_metrics.get("calmar", 0.0))
    cost50 = stress.loc[(stress["stress_type"] == "execution_grid") & (stress["cost_bps"] == 50) & (stress["slippage_bps"] == 5) & (stress["execution_delay"] == 1)]
    cost50_cagr = float(cost50["cagr"].mean()) if not cost50.empty else 0.0
    t1 = stress.loc[(stress["stress_type"] == "execution_grid") & (stress["cost_bps"] == 5) & (stress["slippage_bps"] == 5) & (stress["execution_delay"] == 1) & (stress["max_weight"] == 0.20)]
    t1_cagr = float(t1["cagr"].mean()) if not t1.empty else cagr
    t1_calmar = float(t1["calmar"].mean()) if not t1.empty else calmar
    remove = stress.loc[stress["stress_type"] == "remove_top_contributor"]
    remove_cagr = float(remove["cagr"].iloc[0]) if not remove.empty else 0.0
    remove_calmar = float(remove["calmar"].iloc[0]) if not remove.empty else 0.0
    conv_warning_rate = float(convergence["warning_decision_rate"].min()) if not convergence.empty and "warning_decision_rate" in convergence else 1.0
    challenger_close = False
    if not challengers.empty:
        challenger_close = bool(((challengers["cagr"] >= cagr * 0.70) & (challengers["calmar"] >= max(1.0, calmar * 0.50))).any())
    ticker_contrib = attribution.get("ticker_contribution", pd.DataFrame())
    top_share = float(ticker_contrib["abs_share"].iloc[0]) if not ticker_contrib.empty and "abs_share" in ticker_contrib else 1.0
    yearly = attribution.get("yearly", pd.DataFrame())
    single_year_share = 1.0
    if not yearly.empty and "year_return" in yearly:
        denom = yearly["year_return"].abs().sum()
        single_year_share = float(yearly["year_return"].abs().max() / denom) if denom else 0.0

    gates = {
        "paper_cagr_ge_20": cagr >= 0.20,
        "paper_calmar_ge_1": calmar >= 1.0,
        "cost50_cagr_ge_20": cost50_cagr >= 0.20,
        "t1_cagr_ge_20": t1_cagr >= 0.20,
        "t1_calmar_ge_1": t1_calmar >= 1.0,
        "convergence_or_challenger_ok": conv_warning_rate == 0.0 or challenger_close,
        "remove_top_ticker_ok": remove_cagr >= 0.20 and remove_calmar >= 1.0,
        "top_ticker_share_lte_30": top_share <= 0.30,
        "single_year_share_lte_50": single_year_share <= 0.50,
    }
    if not (gates["paper_cagr_ge_20"] and gates["paper_calmar_ge_1"] and gates["t1_cagr_ge_20"] and gates["t1_calmar_ge_1"]):
        classification = "invalid_due_to_execution_or_alignment"
    elif not gates["convergence_or_challenger_ok"]:
        classification = "model_unstable_need_fix"
    elif not (gates["cost50_cagr_ge_20"] and gates["remove_top_ticker_ok"]):
        classification = "credible_but_execution_sensitive"
    elif not (gates["top_ticker_share_lte_30"] and gates["single_year_share_lte_50"]):
        classification = "credible_but_execution_sensitive"
    elif challenger_close:
        classification = "v9_ready_research_candidate"
    else:
        classification = "model_unstable_need_fix"
    return {
        "classification": classification,
        "allow_enter_v9": bool(classification == "v9_ready_research_candidate"),
        "gates": gates,
        "paper_cagr": cagr,
        "paper_calmar": calmar,
        "cost50_cagr": cost50_cagr,
        "t1_cagr": t1_cagr,
        "t1_calmar": t1_calmar,
        "remove_top_ticker_cagr": remove_cagr,
        "remove_top_ticker_calmar": remove_calmar,
        "top_ticker_share": top_share,
        "single_year_share": single_year_share,
        "min_convergence_warning_rate": conv_warning_rate,
        "challenger_close": challenger_close,
    }


def build_v8_report(
    path: Path | str,
    paper_metrics: pd.DataFrame,
    convergence: pd.DataFrame,
    challengers: pd.DataFrame,
    stress: pd.DataFrame,
    attribution: dict[str, pd.DataFrame],
    verdict: dict[str, Any],
) -> Path:
    stress_summary = stress.groupby("stress_type").agg(mean_cagr=("cagr", "mean"), min_cagr=("cagr", "min"), mean_calmar=("calmar", "mean"), min_calmar=("calmar", "min")).reset_index() if not stress.empty else pd.DataFrame()
    text = f"""# US Stock Selection v8 Paper-Trading Replay Report

## Objective

v8 freezes the v7 best candidate and checks pseudo-live execution realism. It does not expand Nasdaq100/S&P500 and does not claim tradability.

Frozen strategy:

- Feature set: `Alpha360`
- Model: `ElasticNet`
- Label: `label_5d`
- Portfolio: `Top5 equal monthly`

## Verdict

- Classification: `{verdict.get("classification")}`
- Allow entering v9: `{verdict.get("allow_enter_v9")}`
- Gates: `{verdict.get("gates")}`

## Paper-Trading Replay

{_table(paper_metrics, ["model", "feature_set", "label", "portfolio", "total_return", "cagr", "max_drawdown", "calmar", "sharpe", "annual_turnover", "daily_count"])}

## ElasticNet Convergence

{_table(convergence, ["config", "decision_count", "warning_count", "warning_decision_rate", "cagr", "calmar", "sample_warning"])}

Convergence warnings are not hidden. If warnings remain, Ridge/LGBModel are treated as challengers rather than proof of readiness.

## Challenger Models

{_table(challengers, ["run_id", "feature_set", "model", "decision_count", "warning_count", "cagr", "max_drawdown", "calmar", "annual_turnover"])}

## Execution Stress

{_table(stress_summary, ["stress_type", "mean_cagr", "min_cagr", "mean_calmar", "min_calmar"])}

## Attribution

Ticker contribution:

{_table(attribution.get("ticker_contribution", pd.DataFrame()).head(12), ["ticker", "return_contribution", "abs_share"])}

Yearly return:

{_table(attribution.get("yearly", pd.DataFrame()), ["year", "year_return"])}

Top return months:

{_table(attribution.get("top_months", pd.DataFrame()).head(12), ["month", "monthly_return"])}

## Answers

1. Pseudo-live still effective: `{verdict.get("paper_cagr")}` CAGR, `{verdict.get("paper_calmar")}` Calmar.
2. ElasticNet convergence warning impact: `{verdict.get("min_convergence_warning_rate")}` min warning decision rate.
3. Challenger close enough: `{verdict.get("challenger_close")}`.
4. T+1 result: CAGR `{verdict.get("t1_cagr")}`, Calmar `{verdict.get("t1_calmar")}`.
5. 50bps cost result: CAGR `{verdict.get("cost50_cagr")}`.
6. Top ticker share: `{verdict.get("top_ticker_share")}`.
7. Allow v9: `{verdict.get("allow_enter_v9")}`.
"""
    return save_text(text, path)


def build_v8_excel(path: Path | str, sheets: dict[str, pd.DataFrame]) -> Path:
    return write_excel(sheets, path)


def package_v8_run(run_dir: Path | str, timestamp: str) -> Path:
    base = Path(run_dir).resolve()
    zip_path = base.parent / f"us_stock_selection_quant_lab_v8_paper_trading_{timestamp}.zip"
    paths = [
        PROJECT_ROOT / "AGENTS.md",
        PROJECT_ROOT / "NEXT_STEPS.md",
        PROJECT_ROOT / "RUN_SUMMARY.md",
        PROJECT_ROOT / "docs" / "US_STOCK_SELECTION_AUTORUN.md",
        PROJECT_ROOT / "configs" / "us_stock_selection",
        PROJECT_ROOT / "scripts" / "us_stock_selection",
        PROJECT_ROOT / "quant_lab" / "us_stock_selection",
        base / "v8_paper_trading",
        base / "v8_model_stability",
        base / "v8_execution_sim",
        base / "v8_attribution",
        base / "reports",
        base / "logs",
        base / "RUN_SUMMARY.md",
    ]
    return zip_selected_paths(paths, zip_path, root=PROJECT_ROOT)


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
