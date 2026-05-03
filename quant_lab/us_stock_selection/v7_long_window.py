"""Long-window v7 validation to reduce short-window Calmar artifacts."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from quant_lab.us_stock_selection.fast_walk_forward import run_fast_walk_forward
from quant_lab.us_stock_selection.feature_cache import build_feature_cache
from quant_lab.us_stock_selection.qlib_signal_backtest import compute_portfolio_metrics, portfolio_returns
from quant_lab.us_stock_selection.qlib_workflow_runner import load_close_from_provider
from quant_lab.us_stock_selection.utils import (
    PROJECT_ROOT,
    ensure_dir,
    nav_from_returns,
    save_dataframe,
    save_json,
    save_text,
    write_excel,
    zip_selected_paths,
)
from quant_lab.us_stock_selection.v7_audit import (
    align_close_weights,
    build_dropout_logic_audit,
    build_rebalance_calendar_check,
    build_weight_sum_check,
    holdings_for_row,
    markdown_table,
    monthly_equal_weights,
)


LONG_WINDOW_TEMPLATES = ["top5_equal_monthly", "top5_dropout_monthly", "top10_dropout_monthly"]
BENCHMARKS = ["QQQ", "QLD", "TQQQ", "SPY", "SHY"]


def build_long_windows() -> list[dict[str, str]]:
    """Annual and two-year OOS windows; no 2026 YTD short window."""
    return [
        {"wf_family": "anchored_1y", "wf_name": "anchored_2024", "train_start": "2020-01-02", "train_end": "2023-12-31", "test_start": "2024-01-01", "test_end": "2024-12-31"},
        {"wf_family": "anchored_1y", "wf_name": "anchored_2025", "train_start": "2020-01-02", "train_end": "2024-12-31", "test_start": "2025-01-01", "test_end": "2025-12-31"},
        {"wf_family": "rolling_2y_1y", "wf_name": "rolling2y_2024", "train_start": "2022-01-01", "train_end": "2023-12-31", "test_start": "2024-01-01", "test_end": "2024-12-31"},
        {"wf_family": "rolling_2y_1y", "wf_name": "rolling2y_2025", "train_start": "2023-01-01", "train_end": "2024-12-31", "test_start": "2025-01-01", "test_end": "2025-12-31"},
        {"wf_family": "rolling_3y_1y", "wf_name": "rolling3y_2024", "train_start": "2021-01-01", "train_end": "2023-12-31", "test_start": "2024-01-01", "test_end": "2024-12-31"},
        {"wf_family": "rolling_3y_1y", "wf_name": "rolling3y_2025", "train_start": "2022-01-01", "train_end": "2024-12-31", "test_start": "2025-01-01", "test_end": "2025-12-31"},
        {"wf_family": "anchored_2y", "wf_name": "anchored_2024_2025", "train_start": "2020-01-02", "train_end": "2023-12-31", "test_start": "2024-01-01", "test_end": "2025-12-31"},
    ]


def run_v7_long_window_validation(
    run_dir: Path | str,
    provider_uri: Path | str,
    source_cache_run: Path | str | None = None,
    rebuild_cache: bool = False,
) -> dict[str, Any]:
    """Run annual/long-window WF and write conservative audit outputs."""
    base = Path(run_dir).resolve()
    cache_dir = ensure_dir(base / "v7_feature_cache")
    wf_dir = ensure_dir(base / "v7_long_window")
    reports_dir = ensure_dir(base / "reports")
    source_cache = Path(source_cache_run).resolve() / "v7_feature_cache" if source_cache_run else None

    cache_status = pd.DataFrame()
    if source_cache and source_cache.exists() and not rebuild_cache:
        shutil.copytree(source_cache, cache_dir, dirs_exist_ok=True)
        status_path = cache_dir / "feature_cache_status.csv"
        if status_path.exists():
            cache_status = pd.read_csv(status_path)
            cache_status = cache_status.loc[cache_status["feature_set"].astype(str) == "Alpha360"].copy()
    if cache_status.empty:
        cache_status = build_feature_cache(cache_dir, provider_uri=provider_uri, feature_sets=["Alpha360"], overwrite=rebuild_cache)["status"]

    wf_outputs = run_fast_walk_forward(
        wf_dir,
        cache_dir=cache_dir,
        provider_uri=provider_uri,
        feature_sets=["Alpha360"],
        models=["ElasticNet"],
        labels=["label_5d"],
        custom_windows=build_long_windows(),
        resume=False,
    )
    detail = wf_outputs["detail"]
    summary = wf_outputs["summary"]
    conservative = build_long_conservative_summary(detail)
    save_dataframe(conservative, wf_dir / "long_window_conservative_summary.csv")

    close = load_close_from_provider(provider_uri, start="2020-01-01")
    holdings = pd.read_parquet(wf_dir / "holdings" / "wf_holdings.parquet")
    holdings["date"] = pd.to_datetime(holdings["date"])
    recomputed = recompute_all_strategies(detail, holdings, close)
    save_dataframe(recomputed.drop(columns=["returns", "nav"], errors="ignore"), wf_dir / "long_window_recalc_check.csv")
    costs = build_multi_strategy_costs(detail, holdings, close)
    benchmarks = build_multi_strategy_benchmarks(recomputed, close)
    dropout_rows = detail.loc[detail["portfolio_template"].astype(str).str.contains("dropout", case=False, na=False)].copy()
    dropout_logic = build_dropout_logic_audit(dropout_rows, holdings) if not dropout_rows.empty else pd.DataFrame()
    weight_sum = build_weight_sum_check(detail, holdings)
    calendar = build_rebalance_calendar_check(detail, holdings)
    verdict = classify_long_window(conservative, recomputed, costs, benchmarks, dropout_logic, weight_sum, calendar)

    save_dataframe(costs, wf_dir / "long_window_cost_sensitivity.csv")
    save_dataframe(benchmarks, wf_dir / "long_window_same_window_benchmark.csv")
    save_dataframe(dropout_logic, wf_dir / "long_window_dropout_logic.csv")
    save_dataframe(weight_sum, wf_dir / "long_window_weight_sum_check.csv")
    save_dataframe(calendar, wf_dir / "long_window_rebalance_calendar_check.csv")
    save_json(verdict, wf_dir / "long_window_verdict.json")
    report_path = build_long_window_report(
        reports_dir / "us_stock_selection_v7_long_window_report.md",
        cache_status,
        detail,
        summary,
        conservative,
        recomputed,
        costs,
        benchmarks,
        dropout_logic,
        verdict,
    )
    write_excel(
        {
            "wf_detail": detail,
            "wf_summary": summary,
            "conservative_summary": conservative,
            "recalc": recomputed.drop(columns=["returns", "nav"], errors="ignore"),
            "cost_sensitivity": costs,
            "same_window_benchmark": benchmarks,
            "dropout_logic": dropout_logic,
            "weight_sum": weight_sum,
            "rebalance_calendar": calendar,
            "verdict": pd.DataFrame([verdict]),
        },
        reports_dir / "us_stock_selection_v7_long_window_summary.xlsx",
    )
    return {
        "cache_status": cache_status,
        "detail": detail,
        "summary": summary,
        "conservative": conservative,
        "recomputed": recomputed,
        "costs": costs,
        "benchmarks": benchmarks,
        "dropout_logic": dropout_logic,
        "verdict": verdict,
        "report_path": str(report_path),
    }


def build_long_conservative_summary(detail: pd.DataFrame) -> pd.DataFrame:
    ok = detail.loc[detail["status"].isin(["completed", "slow_completed"])].copy()
    if ok.empty:
        return pd.DataFrame()
    ok["daily_count"] = pd.to_numeric(ok["daily_count"], errors="coerce").fillna(0).astype(int)
    ok["annual_like"] = ok["daily_count"] >= 240
    ok["calmar_winsor"] = pd.to_numeric(ok["calmar"], errors="coerce").clip(-5, 5)
    rows: list[dict[str, Any]] = []
    group_cols = ["feature_set", "model", "label", "portfolio_template"]
    for keys, frame in ok.groupby(group_cols):
        annual = frame.loc[frame["annual_like"]].copy()
        worst_n = max(1, int(np.ceil(len(frame) * 0.25)))
        worst = frame.sort_values("total_return").head(worst_n)
        row = dict(zip(group_cols, keys))
        row.update(
            {
                "strategy_key": "_".join(str(x) for x in keys),
                "window_count": int(len(frame)),
                "annual_like_window_count": int(len(annual)),
                "short_window_lt_240_count": int((~frame["annual_like"]).sum()),
                "mean_total_return": float(frame["total_return"].mean()),
                "median_total_return": float(frame["total_return"].median()),
                "annual_like_mean_cagr": float(annual["cagr"].mean()) if not annual.empty else np.nan,
                "annual_like_median_cagr": float(annual["cagr"].median()) if not annual.empty else np.nan,
                "annual_like_cagr20_pass_rate": float((annual["cagr"] >= 0.20).mean()) if not annual.empty else np.nan,
                "annual_like_mean_calmar_winsor": float(annual["calmar_winsor"].mean()) if not annual.empty else np.nan,
                "annual_like_median_calmar_winsor": float(annual["calmar_winsor"].median()) if not annual.empty else np.nan,
                "annual_like_calmar1_pass_rate": float((annual["calmar"] >= 1.0).mean()) if not annual.empty else np.nan,
                "min_calmar": float(frame["calmar"].min()),
                "max_drawdown_mean": float(frame["max_drawdown"].mean()),
                "worst_25pct_mean_total_return": float(worst["total_return"].mean()),
                "worst_25pct_mean_cagr": float(worst["cagr"].mean()),
                "avg_herfindahl": float(frame["avg_herfindahl"].mean()),
                "top_holding_contribution": float(frame["top_holding_contribution"].mean()),
                "avg_turnover": float(frame["annual_turnover"].mean()),
            }
        )
        rows.append(row)
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values(["annual_like_cagr20_pass_rate", "annual_like_mean_calmar_winsor", "annual_like_mean_cagr"], ascending=[False, False, False]).reset_index(drop=True)


def recompute_all_strategies(detail: pd.DataFrame, holdings: pd.DataFrame, close: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for i, row in detail.loc[detail["status"].isin(["completed", "slow_completed"])].reset_index(drop=True).iterrows():
        weights = holdings_for_row(holdings, str(row["row_key"]))
        local_close, weights = align_close_weights(close, weights, row["test_start"], row["test_end"])
        returns, turnover = portfolio_returns(local_close, weights, cost_bps=5.0, slippage_bps=5.0)
        metrics = compute_portfolio_metrics(returns, turnover, weights)
        out = {
            "window_id": i + 1,
            "row_key": row["row_key"],
            "strategy_id": row["strategy_id"],
            "portfolio_template": row["portfolio_template"],
            "wf_type": row["wf_family"],
            "wf_name": row["wf_name"],
            "train_start": row["train_start"],
            "train_end": row["train_end"],
            "test_start": row["test_start"],
            "test_end": row["test_end"],
            "test_days": int(metrics["daily_count"]),
            "reported_total_return": float(row["total_return"]),
            "recomputed_total_return": float(metrics["total_return"]),
            "reported_cagr": float(row["cagr"]),
            "recomputed_cagr": float(metrics["cagr"]),
            "reported_maxdd": float(row["max_drawdown"]),
            "recomputed_maxdd": float(metrics["max_drawdown"]),
            "reported_calmar": float(row["calmar"]),
            "recomputed_calmar": float(metrics["calmar"]),
            "diff_cagr": float(metrics["cagr"] - row["cagr"]),
            "diff_maxdd": float(metrics["max_drawdown"] - row["max_drawdown"]),
            "diff_calmar": float(metrics["calmar"] - row["calmar"]),
            "pass_recalc_check": bool(abs(metrics["cagr"] - row["cagr"]) <= 1e-6 and abs(metrics["max_drawdown"] - row["max_drawdown"]) <= 1e-6 and abs(metrics["calmar"] - row["calmar"]) <= 1e-6),
            "returns": returns,
            "nav": nav_from_returns(returns),
        }
        rows.append(out)
    return pd.DataFrame(rows)


def build_multi_strategy_costs(detail: pd.DataFrame, holdings: pd.DataFrame, close: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in detail.loc[detail["status"].isin(["completed", "slow_completed"])].iterrows():
        weights = holdings_for_row(holdings, str(row["row_key"]))
        local_close, weights = align_close_weights(close, weights, row["test_start"], row["test_end"])
        for cost in [0, 5, 10, 20, 50]:
            returns, turnover = portfolio_returns(local_close, weights, cost_bps=float(cost), slippage_bps=float(cost))
            metrics = compute_portfolio_metrics(returns, turnover, weights)
            rows.append(
                {
                    "row_key": row["row_key"],
                    "portfolio_template": row["portfolio_template"],
                    "wf_name": row["wf_name"],
                    "cost_bps_each_side": cost,
                    **metrics,
                }
            )
    return pd.DataFrame(rows)


def build_multi_strategy_benchmarks(recomputed: pd.DataFrame, close: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in recomputed.iterrows():
        start = pd.Timestamp(row["test_start"])
        end = pd.Timestamp(row["test_end"])
        local_close = close.loc[(close.index >= start) & (close.index <= end)].ffill()
        for ticker in BENCHMARKS:
            if ticker not in local_close:
                continue
            ret = local_close[ticker].pct_change(fill_method=None).fillna(0.0)
            weights = pd.DataFrame({ticker: 1.0}, index=ret.index)
            metrics = compute_portfolio_metrics(ret, pd.Series(0.0, index=ret.index), weights)
            rows.append(_benchmark_row(row, f"{ticker}_buy_hold", metrics))
        pool_cols = [c for c in close.columns if c in local_close.columns]
        if pool_cols:
            weights = monthly_equal_weights(local_close.loc[:, pool_cols], start_invested=True)
            ret, turnover = portfolio_returns(local_close.loc[:, pool_cols], weights, cost_bps=5.0, slippage_bps=5.0)
            metrics = compute_portfolio_metrics(ret, turnover, weights)
            rows.append(_benchmark_row(row, "Pool_A_equal_weight_monthly", metrics))
    return pd.DataFrame(rows)


def classify_long_window(
    conservative: pd.DataFrame,
    recomputed: pd.DataFrame,
    costs: pd.DataFrame,
    benchmarks: pd.DataFrame,
    dropout_logic: pd.DataFrame,
    weight_sum: pd.DataFrame,
    calendar: pd.DataFrame,
) -> dict[str, Any]:
    best = conservative.iloc[0].to_dict() if not conservative.empty else {}
    recalc_pass = bool(recomputed.empty or recomputed["pass_recalc_check"].all())
    dropout_pass = bool(dropout_logic.empty or not dropout_logic["dropout_exceeds_n_drop"].any())
    weight_pass = bool(weight_sum.empty or weight_sum["pass_weight_sum_check"].all())
    calendar_pass = bool(calendar.empty or calendar["pass_monthly_rebalance_check"].all())
    cost50 = costs.loc[(costs["portfolio_template"] == best.get("portfolio_template")) & (costs["cost_bps_each_side"] == 50)].copy() if not costs.empty else pd.DataFrame()
    cost50_mean_cagr = float(cost50["cagr"].mean()) if not cost50.empty else np.nan
    bench = benchmarks.loc[(benchmarks["portfolio_template"] == best.get("portfolio_template")) & (benchmarks["benchmark"] == "QQQ_buy_hold")].copy() if not benchmarks.empty else pd.DataFrame()
    qqq_cagr_win = float((bench["strategy_cagr_minus_benchmark"] > 0).mean()) if not bench.empty else 0.0
    qqq_calmar_win = float((bench["strategy_calmar_minus_benchmark"] > 0).mean()) if not bench.empty else 0.0
    eligible = int(best.get("annual_like_window_count", 0) or 0)
    strong = bool(
        recalc_pass
        and dropout_pass
        and weight_pass
        and calendar_pass
        and eligible >= 5
        and float(best.get("annual_like_mean_cagr", 0.0) or 0.0) >= 0.20
        and float(best.get("annual_like_mean_calmar_winsor", 0.0) or 0.0) >= 1.0
        and float(best.get("annual_like_cagr20_pass_rate", 0.0) or 0.0) >= 0.60
        and float(best.get("annual_like_calmar1_pass_rate", 0.0) or 0.0) >= 0.60
        and float(best.get("top_holding_contribution", 1.0) or 1.0) <= 0.30
        and qqq_cagr_win >= 0.60
        and qqq_calmar_win >= 0.60
        and cost50_mean_cagr >= 0.15
    )
    if not (recalc_pass and dropout_pass and weight_pass and calendar_pass):
        classification = "invalid_due_to_backtest_bug"
    elif strong:
        classification = "credible_research_candidate"
    elif eligible >= 5 and float(best.get("annual_like_mean_cagr", 0.0) or 0.0) >= 0.15:
        classification = "promising_but_needs_more_validation"
    else:
        classification = "likely_overfit"
    return {
        "classification": classification,
        "allow_enter_v8": False,
        "must_send_to_chatgpt": bool(classification == "credible_research_candidate"),
        "reason": _verdict_reason(classification, best, recalc_pass, dropout_pass, weight_pass, calendar_pass, qqq_cagr_win, qqq_calmar_win, cost50_mean_cagr),
        "best": best,
        "recalc_pass": recalc_pass,
        "strict_dropout_n_drop_pass": dropout_pass,
        "weight_sum_pass": weight_pass,
        "monthly_rebalance_pass": calendar_pass,
        "same_window_qqq_cagr_win_rate": qqq_cagr_win,
        "same_window_qqq_calmar_win_rate": qqq_calmar_win,
        "cost50_mean_cagr": cost50_mean_cagr,
    }


def build_long_window_report(
    path: Path | str,
    cache_status: pd.DataFrame,
    detail: pd.DataFrame,
    summary: pd.DataFrame,
    conservative: pd.DataFrame,
    recomputed: pd.DataFrame,
    costs: pd.DataFrame,
    benchmarks: pd.DataFrame,
    dropout_logic: pd.DataFrame,
    verdict: dict[str, Any],
) -> Path:
    cost_summary = (
        costs.groupby(["portfolio_template", "cost_bps_each_side"]).agg(mean_cagr=("cagr", "mean"), winsor_calmar=("calmar", lambda s: float(s.clip(-5, 5).mean()))).reset_index()
        if not costs.empty
        else pd.DataFrame()
    )
    bench_summary = (
        benchmarks.groupby(["portfolio_template", "benchmark"]).agg(cagr_win_rate=("strategy_cagr_minus_benchmark", lambda s: float((s > 0).mean())), calmar_win_rate=("strategy_calmar_minus_benchmark", lambda s: float((s > 0).mean()))).reset_index()
        if not benchmarks.empty
        else pd.DataFrame()
    )
    text = f"""# US Stock Selection v7 Long-Window Validation Report

## Objective

This run keeps v7 in evidence-hardening mode. It does not enter v8 and does not expand the universe. The purpose is to replace short half-year/YTD evidence with annual and two-year OOS windows.

## Verdict

- Classification: `{verdict.get("classification")}`
- Allow entering v8: `{verdict.get("allow_enter_v8")}`
- Must send to ChatGPT/user: `{verdict.get("must_send_to_chatgpt")}`
- Reason: `{verdict.get("reason")}`

## Feature Cache

{markdown_table(cache_status, ["feature_set", "status", "rows", "date_start", "date_end", "instrument_count", "feature_count"])}

## Long-Window WF Summary

{markdown_table(conservative, ["portfolio_template", "window_count", "annual_like_window_count", "annual_like_mean_cagr", "annual_like_mean_calmar_winsor", "annual_like_cagr20_pass_rate", "annual_like_calmar1_pass_rate", "worst_25pct_mean_total_return", "avg_herfindahl", "top_holding_contribution", "avg_turnover"])}

## Reported vs Recomputed

All rows should pass exactly because recomputation uses raw provider close and stored holdings.

{markdown_table(recomputed.drop(columns=["returns", "nav"], errors="ignore"), ["portfolio_template", "wf_name", "test_days", "reported_cagr", "recomputed_cagr", "reported_maxdd", "recomputed_maxdd", "reported_calmar", "recomputed_calmar", "pass_recalc_check"])}

## Cost Sensitivity

{markdown_table(cost_summary, ["portfolio_template", "cost_bps_each_side", "mean_cagr", "winsor_calmar"], max_rows=50)}

## Same-Window Benchmarks

{markdown_table(bench_summary, ["portfolio_template", "benchmark", "cagr_win_rate", "calmar_win_rate"], max_rows=80)}

## Dropout Logic

- Dropout rows exceeding n_drop: `{int(dropout_logic["dropout_exceeds_n_drop"].sum()) if not dropout_logic.empty else 0}`

## Decision

This report is still part of v7 validation. If classification is `credible_research_candidate`, stop and send results to ChatGPT/user review before any v8 work. Otherwise continue v7 evidence hardening.
"""
    return save_text(text, path)


def package_v7_long_window_run(run_dir: Path | str, timestamp: str) -> Path:
    base = Path(run_dir).resolve()
    zip_path = base.parent / f"us_stock_selection_quant_lab_v7_long_window_{timestamp}.zip"
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
        base / "v7_long_window",
        base / "reports",
        base / "logs",
        base / "RUN_SUMMARY.md",
    ]
    return zip_selected_paths(paths, zip_path, root=PROJECT_ROOT)


def _benchmark_row(row: pd.Series, benchmark: str, metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        "row_key": row["row_key"],
        "portfolio_template": row["portfolio_template"],
        "wf_name": row["wf_name"],
        "benchmark": benchmark,
        "strategy_cagr": row["recomputed_cagr"],
        "strategy_calmar": row["recomputed_calmar"],
        "benchmark_cagr": metrics.get("cagr", 0.0),
        "benchmark_calmar": metrics.get("calmar", 0.0),
        "strategy_cagr_minus_benchmark": row["recomputed_cagr"] - metrics.get("cagr", 0.0),
        "strategy_calmar_minus_benchmark": row["recomputed_calmar"] - metrics.get("calmar", 0.0),
    }


def _verdict_reason(classification: str, best: dict[str, Any], recalc_pass: bool, dropout_pass: bool, weight_pass: bool, calendar_pass: bool, qqq_cagr_win: float, qqq_calmar_win: float, cost50_mean_cagr: float) -> str:
    if classification == "invalid_due_to_backtest_bug":
        return f"validation failed: recalc={recalc_pass}, dropout={dropout_pass}, weight={weight_pass}, calendar={calendar_pass}"
    if classification == "credible_research_candidate":
        return "annual-like long-window evidence meets CAGR/Calmar/cost/benchmark/concentration gates; stop for ChatGPT/user review before v8"
    return (
        "long-window evidence improved but did not meet all gates: "
        f"top_holding_contribution={best.get('top_holding_contribution')}, "
        f"qqq_cagr_win={qqq_cagr_win}, qqq_calmar_win={qqq_calmar_win}, cost50_mean_cagr={cost50_mean_cagr}"
    )
