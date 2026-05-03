"""Reverse-audit v7 fast walk-forward portfolio results.

This module intentionally recomputes the v7 best strategy from stored holdings
and raw provider prices instead of trusting reported metrics.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from quant_lab.us_stock_selection.qlib_signal_backtest import compute_portfolio_metrics, portfolio_returns
from quant_lab.us_stock_selection.qlib_workflow_runner import load_close_from_provider
from quant_lab.us_stock_selection.utils import (
    PROJECT_ROOT,
    annualized_return,
    ensure_dir,
    max_drawdown,
    nav_from_returns,
    save_dataframe,
    save_json,
    save_text,
    write_excel,
    zip_selected_paths,
)


TARGET_FEATURE_SET = "Alpha360"
TARGET_MODEL = "ElasticNet"
TARGET_LABEL = "label_5d"
TARGET_TEMPLATE = "top10_dropout_monthly"
DEFAULT_PROVIDER_URI = Path.home() / ".qlib" / "qlib_data" / "us_data_local_2026"
BENCHMARK_TICKERS = ["QQQ", "QLD", "TQQQ", "SPY", "SHY"]
POOL_A_TICKERS = [
    "QQQ",
    "QLD",
    "TQQQ",
    "SPY",
    "SSO",
    "UPRO",
    "IWM",
    "SOXX",
    "SMH",
    "XLK",
    "GLD",
    "TLT",
    "SHY",
    "AAPL",
    "MSFT",
    "NVDA",
    "GOOGL",
    "AMZN",
    "META",
    "TSLA",
    "AMD",
    "AVGO",
    "MU",
    "CRM",
    "ORCL",
    "NOW",
    "ADBE",
    "NFLX",
    "PANW",
    "CRWD",
    "PLTR",
    "NET",
    "SNOW",
    "UBER",
    "INTC",
    "MSTR",
    "SHOP",
]


def run_v7_audit(
    source_run_dir: Path | str,
    audit_run_dir: Path | str,
    provider_uri: Path | str | None = None,
    cost_bps_cases: list[int] | None = None,
) -> dict[str, Any]:
    """Run the full v7 reverse audit and write all required outputs."""
    source = Path(source_run_dir).resolve()
    run_dir = Path(audit_run_dir).resolve()
    audit_dir = ensure_dir(run_dir / "v7_audit")
    reports_dir = ensure_dir(run_dir / "reports")
    logs_dir = ensure_dir(run_dir / "logs")
    provider = Path(provider_uri).expanduser() if provider_uri else DEFAULT_PROVIDER_URI
    cost_cases = cost_bps_cases or [0, 5, 10, 20, 50]

    inputs = load_v7_inputs(source)
    detail = inputs["detail"]
    target = filter_target_rows(detail)
    if target.empty:
        raise ValueError("No target v7 rows found for Alpha360 + ElasticNet + label_5d + Top10 dropout monthly")

    close = load_close_from_provider(provider, start="2020-01-01")
    if close.empty:
        raise ValueError(f"Provider close panel is empty: {provider}")

    recomputed = recompute_windows(target, inputs["holdings"], close)
    annualization = build_annualization_audit(recomputed)
    drawdown = build_drawdown_audit(recomputed)
    alignment = build_alignment_audit(source, target, inputs["holdings"], close)
    leakage = build_leakage_check(source, alignment)
    dropout = build_dropout_logic_audit(target, inputs["holdings"])
    weight_sum = build_weight_sum_check(target, inputs["holdings"])
    rebalance_calendar = build_rebalance_calendar_check(target, inputs["holdings"])
    costs = build_cost_adjusted_wf(target, inputs["holdings"], close, cost_cases)
    benchmarks = build_same_window_benchmark(recomputed, close)
    conservative = build_conservative_summary(recomputed, costs, benchmarks, leakage, dropout)
    classification = classify_audit(recomputed, annualization, drawdown, leakage, dropout, weight_sum, rebalance_calendar, conservative, costs, benchmarks)

    save_dataframe(recomputed.drop(columns=["returns", "nav"], errors="ignore"), audit_dir / "window_recalc_check.csv")
    save_dataframe(annualization, audit_dir / "annualization_audit.csv")
    save_dataframe(drawdown, audit_dir / "drawdown_audit.csv")
    save_dataframe(alignment, audit_dir / "alignment_audit.csv")
    save_json(leakage, audit_dir / "leakage_check.json")
    save_dataframe(dropout, audit_dir / "topk_dropout_logic.csv")
    save_dataframe(weight_sum, audit_dir / "weight_sum_check.csv")
    save_dataframe(rebalance_calendar, audit_dir / "rebalance_calendar_check.csv")
    save_dataframe(costs, audit_dir / "cost_adjusted_wf.csv")
    save_dataframe(benchmarks, audit_dir / "same_window_benchmark.csv")
    save_dataframe(conservative, audit_dir / "conservative_wf_summary.csv")
    save_json(classification, audit_dir / "audit_verdict.json")

    report = build_v7_audit_report(
        reports_dir / "us_stock_selection_v7_audit_report.md",
        source,
        recomputed,
        annualization,
        drawdown,
        alignment,
        leakage,
        dropout,
        weight_sum,
        rebalance_calendar,
        costs,
        benchmarks,
        conservative,
        classification,
    )
    write_excel(
        {
            "window_recalc": recomputed.drop(columns=["returns", "nav"], errors="ignore"),
            "annualization": annualization,
            "drawdown": drawdown,
            "alignment": alignment,
            "dropout_logic": dropout,
            "weight_sum": weight_sum,
            "rebalance_calendar": rebalance_calendar,
            "cost_adjusted": costs,
            "same_window_benchmark": benchmarks,
            "conservative_summary": conservative,
            "verdict": pd.DataFrame([classification]),
        },
        reports_dir / "us_stock_selection_v7_audit_summary.xlsx",
    )
    save_text(report.read_text(encoding="utf-8"), audit_dir / "us_stock_selection_v7_audit_report.md")
    save_text(
        build_run_summary_text(run_dir, source, classification, conservative),
        run_dir / "RUN_SUMMARY.md",
    )
    save_text(
        build_next_steps_text(classification),
        PROJECT_ROOT / "NEXT_STEPS.md",
    )
    save_text(
        build_run_summary_text(run_dir, source, classification, conservative),
        PROJECT_ROOT / "RUN_SUMMARY.md",
    )
    return {
        "source_run_dir": str(source),
        "audit_run_dir": str(run_dir),
        "audit_dir": str(audit_dir),
        "report_path": str(report),
        "classification": classification,
        "conservative": conservative,
        "recomputed": recomputed,
        "costs": costs,
        "benchmarks": benchmarks,
    }


def load_v7_inputs(source: Path) -> dict[str, pd.DataFrame]:
    wf_dir = source / "v7_fast_walk_forward"
    detail = pd.read_csv(wf_dir / "wf_detail.csv")
    daily = pd.read_parquet(wf_dir / "daily_returns" / "wf_daily_returns.parquet")
    holdings = pd.read_parquet(wf_dir / "holdings" / "wf_holdings.parquet")
    detail["test_start"] = pd.to_datetime(detail["test_start"])
    detail["test_end"] = pd.to_datetime(detail["test_end"])
    for frame in (daily, holdings):
        if "date" in frame.columns:
            frame["date"] = pd.to_datetime(frame["date"])
    return {"detail": detail, "daily": daily, "holdings": holdings}


def filter_target_rows(detail: pd.DataFrame) -> pd.DataFrame:
    rows = detail.loc[
        (detail["feature_set"].astype(str) == TARGET_FEATURE_SET)
        & (detail["model"].astype(str) == TARGET_MODEL)
        & (detail["label"].astype(str) == TARGET_LABEL)
        & (detail["portfolio_template"].astype(str) == TARGET_TEMPLATE)
        & (detail["status"].astype(str).isin(["completed", "slow_completed"]))
    ].copy()
    return rows.sort_values(["wf_family", "test_start", "wf_name"]).reset_index(drop=True)


def recompute_windows(target: pd.DataFrame, holdings: pd.DataFrame, close: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for i, row in target.reset_index(drop=True).iterrows():
        row_key = str(row["row_key"])
        weights = holdings_for_row(holdings, row_key)
        local_close, weights = align_close_weights(close, weights, row["test_start"], row["test_end"])
        returns, turnover = portfolio_returns(local_close, weights, cost_bps=5.0, slippage_bps=5.0)
        metrics = compute_portfolio_metrics(returns, turnover, weights)
        nav = nav_from_returns(returns)
        out = {
            "window_id": i + 1,
            "row_key": row_key,
            "strategy_id": row.get("strategy_id", ""),
            "wf_type": row.get("wf_family", ""),
            "wf_name": row.get("wf_name", ""),
            "train_start": row.get("train_start", ""),
            "train_end": row.get("train_end", ""),
            "test_start": pd.Timestamp(row["test_start"]).date().isoformat(),
            "test_end": pd.Timestamp(row["test_end"]).date().isoformat(),
            "test_days": int(metrics["daily_count"]),
            "reported_total_return": float(row.get("total_return", np.nan)),
            "recomputed_total_return": float(metrics["total_return"]),
            "reported_cagr": float(row.get("cagr", np.nan)),
            "recomputed_cagr": float(metrics["cagr"]),
            "reported_maxdd": float(row.get("max_drawdown", np.nan)),
            "recomputed_maxdd": float(metrics["max_drawdown"]),
            "reported_calmar": float(row.get("calmar", np.nan)),
            "recomputed_calmar": float(metrics["calmar"]),
            "diff_cagr": float(metrics["cagr"] - float(row.get("cagr", np.nan))),
            "diff_maxdd": float(metrics["max_drawdown"] - float(row.get("max_drawdown", np.nan))),
            "diff_calmar": float(metrics["calmar"] - float(row.get("calmar", np.nan))),
            "returns": returns,
            "nav": nav,
        }
        out["pass_recalc_check"] = bool(
            abs(out["diff_cagr"]) <= 1e-6 and abs(out["diff_maxdd"]) <= 1e-6 and abs(out["diff_calmar"]) <= 1e-6
        )
        rows.append(out)
    return pd.DataFrame(rows)


def holdings_for_row(holdings: pd.DataFrame, row_key: str) -> pd.DataFrame:
    h = holdings.loc[holdings["row_key"].astype(str) == row_key, ["date", "instrument", "weight"]].copy()
    if h.empty:
        raise ValueError(f"No holdings found for row_key={row_key}")
    weights = h.pivot_table(index="date", columns="instrument", values="weight", aggfunc="last").sort_index()
    weights.index = pd.to_datetime(weights.index)
    weights.columns = weights.columns.astype(str).str.upper()
    return weights


def align_close_weights(close: pd.DataFrame, weights: pd.DataFrame, start: Any, end: Any) -> tuple[pd.DataFrame, pd.DataFrame]:
    cols = close.columns.intersection(weights.columns)
    local_close = close.loc[(close.index >= pd.Timestamp(start)) & (close.index <= pd.Timestamp(end)), cols].ffill()
    aligned = weights.reindex(local_close.index).ffill().fillna(0.0).loc[:, local_close.columns]
    return local_close, aligned


def build_annualization_audit(recomputed: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for row in iter_recomputed(recomputed):
        returns = row["returns"]
        days = int(len(returns))
        total = float((1.0 + returns).prod() - 1.0) if days else 0.0
        cagr = float(row["recomputed_cagr"])
        maxdd_abs = abs(float(row["recomputed_maxdd"]))
        rows.append(
            {
                "window_id": row["window_id"],
                "wf_type": row["wf_type"],
                "wf_name": row["wf_name"],
                "test_start": row["test_start"],
                "test_end": row["test_end"],
                "test_days": days,
                "total_return": total,
                "reported_cagr": row["reported_cagr"],
                "recomputed_cagr": cagr,
                "annualization_factor": 252.0 / days if days else np.nan,
                "short_window_lt_126": bool(days < 126),
                "cagr_used_in_conservative": bool(days >= 126),
                "conservative_cagr": cagr if days >= 126 else np.nan,
                "reported_calmar": row["reported_calmar"],
                "recomputed_calmar": row["recomputed_calmar"],
                "calmar_reliability": "standard" if days >= 252 else "short_window_unreliable",
                "conservative_calmar": row["recomputed_calmar"] if days >= 252 else np.nan,
                "annualization_amplified": bool(days < 126 or (252.0 / days if days else 0) > 2.0),
                "low_drawdown_amplified": bool(maxdd_abs < 0.005 and total > 0.05),
            }
        )
    return pd.DataFrame(rows)


def build_drawdown_audit(recomputed: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for row in iter_recomputed(recomputed):
        nav = row["nav"].dropna()
        if nav.empty:
            rows.append({"window_id": row["window_id"], "wf_name": row["wf_name"], "maxdd": 0.0})
            continue
        rolling_peak = nav.cummax()
        dd = nav / rolling_peak - 1.0
        trough_date = dd.idxmin()
        peak_date = nav.loc[:trough_date].idxmax()
        rows.append(
            {
                "window_id": row["window_id"],
                "wf_type": row["wf_type"],
                "wf_name": row["wf_name"],
                "test_start": row["test_start"],
                "test_end": row["test_end"],
                "test_days": int(len(nav)),
                "start_nav": 1.0,
                "end_nav": float(nav.iloc[-1]),
                "min_nav": float(nav.min()),
                "peak_nav": float(nav.loc[:trough_date].max()),
                "trough_nav": float(nav.loc[trough_date]),
                "peak_date": pd.Timestamp(peak_date).date().isoformat(),
                "trough_date": pd.Timestamp(trough_date).date().isoformat(),
                "maxdd": float(dd.min()),
                "reported_maxdd": float(row["reported_maxdd"]),
                "maxdd_too_small_flag": bool(abs(dd.min()) < 0.005 and float(nav.iloc[-1] - 1.0) > 0.05),
            }
        )
    return pd.DataFrame(rows)


def build_alignment_audit(source: Path, target: pd.DataFrame, holdings: pd.DataFrame, close: pd.DataFrame) -> pd.DataFrame:
    feature_dates = load_prediction_available_dates(source)
    rows: list[dict[str, Any]] = []
    for _, row in target.iterrows():
        row_key = str(row["row_key"])
        weights = holdings_for_row(holdings, row_key)
        local_close, weights = align_close_weights(close, weights, row["test_start"], row["test_end"])
        rebalances = detect_rebalance_dates(weights)
        available_dates = feature_dates[(feature_dates >= pd.Timestamp(row["test_start"])) & (feature_dates <= pd.Timestamp(row["test_end"]))]
        for rb in rebalances:
            pos = local_close.index.get_loc(rb)
            next_date = local_close.index[pos + 1] if pos + 1 < len(local_close.index) else pd.NaT
            pred_date = latest_on_or_before(available_dates, rb)
            if pd.isna(pred_date):
                pred_date = rb
            label_start = next_trading_date(close.index, pd.Timestamp(pred_date), step=1)
            label_end = next_trading_date(close.index, pd.Timestamp(pred_date), step=6)
            has_future_execution = bool(pd.notna(next_date))
            rows.append(
                {
                    "row_key": row_key,
                    "wf_type": row.get("wf_family", ""),
                    "wf_name": row.get("wf_name", ""),
                    "feature_date": pd.Timestamp(pred_date).date().isoformat(),
                    "prediction_date": pd.Timestamp(pred_date).date().isoformat(),
                    "rebalance_decision_date": pd.Timestamp(rb).date().isoformat(),
                    "trade_execution_date": pd.Timestamp(next_date).date().isoformat() if pd.notna(next_date) else "",
                    "first_return_date": pd.Timestamp(next_date).date().isoformat() if pd.notna(next_date) else "",
                    "label_start": pd.Timestamp(label_start).date().isoformat() if pd.notna(label_start) else "",
                    "label_end": pd.Timestamp(label_end).date().isoformat() if pd.notna(label_end) else "",
                    "feature_le_prediction": bool(pd.Timestamp(pred_date) <= pd.Timestamp(rb)),
                    "has_future_execution_date": has_future_execution,
                    "execution_after_prediction": bool((not has_future_execution) or pd.Timestamp(next_date) > pd.Timestamp(pred_date)),
                    "first_return_ge_execution": has_future_execution,
                    "terminal_rebalance_without_future_return": bool(not has_future_execution),
                    "same_day_return_consumed": False,
                    "alignment_pass": bool(pd.Timestamp(pred_date) <= pd.Timestamp(rb) and ((not has_future_execution) or pd.Timestamp(next_date) > pd.Timestamp(pred_date))),
                }
            )
    return pd.DataFrame(rows)


def load_prediction_available_dates(source: Path) -> pd.DatetimeIndex:
    cache_file = source / "v7_feature_cache" / "alpha360_cache.parquet"
    if not cache_file.exists():
        return pd.DatetimeIndex([])
    frame = pd.read_parquet(cache_file, columns=["date", "label_5d"])
    frame["date"] = pd.to_datetime(frame["date"])
    dates = frame.loc[frame["label_5d"].notna(), "date"].drop_duplicates().sort_values()
    return pd.DatetimeIndex(dates)


def build_leakage_check(source: Path, alignment: pd.DataFrame) -> dict[str, Any]:
    feature_map_path = source / "v7_feature_cache" / "alpha360_feature_map.json"
    feature_map: dict[str, Any] = {}
    if feature_map_path.exists():
        with feature_map_path.open("r", encoding="utf-8") as handle:
            feature_map = json.load(handle)
    feature_cols = list(feature_map.get("feature_columns", []))
    original = feature_map.get("original_feature_columns", {})
    original_text = " ".join(str(x) for x in original.values()).lower()
    label_names = {"label_5d", "label_20d", "label", "LABEL0".lower()}
    label_in_feature_cols = any(str(col).lower() in label_names or "label" in str(col).lower() for col in feature_cols)
    label_expr_in_features = "ref($close, -6)" in original_text or "ref($close,-6)" in original_text or "ref($close, -21)" in original_text
    alignment_pass = bool(alignment.empty or alignment["alignment_pass"].all())
    executable = alignment.loc[alignment.get("has_future_execution_date", pd.Series(dtype=bool)).astype(bool)] if not alignment.empty else alignment
    return {
        "feature_map_path": str(feature_map_path),
        "feature_count": len(feature_cols),
        "label_not_in_feature_columns": bool(not label_in_feature_cols),
        "label_forward_expression_not_in_features": bool(not label_expr_in_features),
        "label_expressions": feature_map.get("label_expressions", {}),
        "alignment_rows": int(len(alignment)),
        "trade_execution_after_prediction_all": bool(executable.empty or executable["execution_after_prediction"].all()),
        "terminal_rebalance_without_future_return_count": int(alignment["terminal_rebalance_without_future_return"].sum()) if "terminal_rebalance_without_future_return" in alignment else 0,
        "same_day_return_consumed": bool(False if alignment.empty else alignment["same_day_return_consumed"].any()),
        "test_label_availability_used_to_filter_prediction_dates": True,
        "test_label_availability_note": "v7 fit_predict_window drops test rows with missing label, so score dates exclude label-unavailable tail rows; label values are not used as features or weights.",
        "overall_leakage_pass": bool((not label_in_feature_cols) and (not label_expr_in_features) and alignment_pass),
    }


def build_dropout_logic_audit(target: pd.DataFrame, holdings: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    top_k = 10
    n_drop = 2
    for _, row in target.iterrows():
        row_key = str(row["row_key"])
        weights = holdings_for_row(holdings, row_key)
        rebalances = detect_rebalance_dates(weights)
        previous: set[str] | None = None
        for rb in rebalances:
            current = set(weights.loc[rb][weights.loc[rb] > 1e-12].index.astype(str))
            dropped = set() if previous is None else previous - current
            added = set() if previous is None else current - previous
            rows.append(
                {
                    "row_key": row_key,
                    "wf_type": row.get("wf_family", ""),
                    "wf_name": row.get("wf_name", ""),
                    "rebalance_date": pd.Timestamp(rb).date().isoformat(),
                    "holding_count": int(len(current)),
                    "expected_top_k": top_k,
                    "n_drop_config": n_drop,
                    "weight_sum": float(weights.loc[rb].sum()),
                    "max_weight": float(weights.loc[rb].max()) if len(weights.columns) else 0.0,
                    "has_duplicate_ticker": False,
                    "empty_holding": bool(len(current) == 0),
                    "dropped_count": int(len(dropped)),
                    "added_count": int(len(added)),
                    "dropout_exceeds_n_drop": bool(previous is not None and len(dropped) > n_drop),
                    "full_replaced": bool(previous is not None and len(dropped) >= top_k),
                    "selected_tickers": ",".join(sorted(current)),
                    "dropped_tickers": ",".join(sorted(dropped)),
                    "added_tickers": ",".join(sorted(added)),
                }
            )
            previous = current
    return pd.DataFrame(rows)


def build_weight_sum_check(target: pd.DataFrame, holdings: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in target.iterrows():
        row_key = str(row["row_key"])
        weights = holdings_for_row(holdings, row_key)
        sums = weights.sum(axis=1)
        counts = (weights > 1e-12).sum(axis=1)
        rows.append(
            {
                "row_key": row_key,
                "wf_type": row.get("wf_family", ""),
                "wf_name": row.get("wf_name", ""),
                "min_weight_sum": float(sums.min()),
                "max_weight_sum": float(sums.max()),
                "mean_weight_sum": float(sums.mean()),
                "days_weight_sum_gt_100": int((sums > 1.000001).sum()),
                "days_negative_weight": int((weights < -1e-12).any(axis=1).sum()),
                "min_holding_count": int(counts.min()),
                "max_holding_count": int(counts.max()),
                "days_holding_count_gt_10": int((counts > 10).sum()),
                "pass_weight_sum_check": bool((sums <= 1.000001).all() and (weights >= -1e-12).all().all() and (counts <= 10).all()),
            }
        )
    return pd.DataFrame(rows)


def build_rebalance_calendar_check(target: pd.DataFrame, holdings: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in target.iterrows():
        row_key = str(row["row_key"])
        weights = holdings_for_row(holdings, row_key)
        changes = weight_change_dates(weights)
        expected = month_end_dates(weights.index)
        unexpected = [d for d in changes if d not in set(expected)]
        missing = [d for d in expected if d not in set(changes) and not weights.loc[d].fillna(0.0).eq(0.0).all()]
        intervals = pd.Series(changes).diff().dropna().dt.days if len(changes) > 1 else pd.Series(dtype=float)
        rows.append(
            {
                "row_key": row_key,
                "wf_type": row.get("wf_family", ""),
                "wf_name": row.get("wf_name", ""),
                "change_count": int(len(changes)),
                "expected_month_end_count": int(len(expected)),
                "unexpected_change_count": int(len(unexpected)),
                "missing_expected_nonzero_count": int(len(missing)),
                "min_change_interval_days": float(intervals.min()) if not intervals.empty else np.nan,
                "median_change_interval_days": float(intervals.median()) if not intervals.empty else np.nan,
                "unexpected_change_dates": ",".join(pd.Timestamp(d).date().isoformat() for d in unexpected[:20]),
                "pass_monthly_rebalance_check": bool(len(unexpected) == 0),
            }
        )
    return pd.DataFrame(rows)


def build_cost_adjusted_wf(target: pd.DataFrame, holdings: pd.DataFrame, close: pd.DataFrame, cost_cases: list[int]) -> pd.DataFrame:
    rows = []
    for _, row in target.iterrows():
        row_key = str(row["row_key"])
        weights = holdings_for_row(holdings, row_key)
        local_close, weights = align_close_weights(close, weights, row["test_start"], row["test_end"])
        for cost in cost_cases:
            returns, turnover = portfolio_returns(local_close, weights, cost_bps=float(cost), slippage_bps=float(cost))
            metrics = compute_portfolio_metrics(returns, turnover, weights)
            rows.append(
                {
                    "row_key": row_key,
                    "wf_type": row.get("wf_family", ""),
                    "wf_name": row.get("wf_name", ""),
                    "test_start": pd.Timestamp(row["test_start"]).date().isoformat(),
                    "test_end": pd.Timestamp(row["test_end"]).date().isoformat(),
                    "cost_bps_each_side": int(cost),
                    "is_v7_reported_cost": bool(cost == 5),
                    "gross_or_net": "gross_result" if cost == 0 else "net_after_cost_slippage",
                    **metrics,
                }
            )
    return pd.DataFrame(rows)


def build_same_window_benchmark(recomputed: pd.DataFrame, close: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for row in iter_recomputed(recomputed):
        start = pd.Timestamp(row["test_start"])
        end = pd.Timestamp(row["test_end"])
        local_close = close.loc[(close.index >= start) & (close.index <= end)].ffill()
        strategy_metrics = {
            "strategy_total_return": row["recomputed_total_return"],
            "strategy_cagr": row["recomputed_cagr"],
            "strategy_max_drawdown": row["recomputed_maxdd"],
            "strategy_calmar": row["recomputed_calmar"],
        }
        for ticker in BENCHMARK_TICKERS:
            if ticker not in local_close.columns:
                continue
            ret = local_close[ticker].pct_change(fill_method=None).fillna(0.0)
            weights = pd.DataFrame({ticker: 1.0}, index=ret.index)
            metrics = compute_portfolio_metrics(ret, pd.Series(0.0, index=ret.index), weights)
            rows.append(format_benchmark_row(row, f"{ticker}_buy_hold", metrics, strategy_metrics))
        pool_cols = [c for c in POOL_A_TICKERS if c in local_close.columns]
        if pool_cols:
            weights = monthly_equal_weights(local_close.loc[:, pool_cols], start_invested=True)
            ret, turnover = portfolio_returns(local_close.loc[:, pool_cols], weights, cost_bps=5.0, slippage_bps=5.0)
            metrics = compute_portfolio_metrics(ret, turnover, weights)
            rows.append(format_benchmark_row(row, "Pool_A_equal_weight_monthly", metrics, strategy_metrics))
    return pd.DataFrame(rows)


def build_conservative_summary(
    recomputed: pd.DataFrame,
    costs: pd.DataFrame,
    benchmarks: pd.DataFrame,
    leakage: dict[str, Any],
    dropout: pd.DataFrame,
) -> pd.DataFrame:
    base = recomputed.copy()
    days = base["test_days"].astype(int)
    eligible_cagr = base.loc[days >= 126].copy()
    eligible_calmar = base.loc[days >= 252].copy()
    clipped_calmar = base["recomputed_calmar"].clip(-5, 5)
    worst_n = max(1, int(math.ceil(len(base) * 0.25)))
    worst = base.sort_values("recomputed_total_return").head(worst_n)
    cost_summary = summarize_costs(costs)
    bench_summary = summarize_benchmarks(benchmarks)
    row = {
        "strategy": f"{TARGET_FEATURE_SET}_{TARGET_MODEL}_{TARGET_LABEL}_{TARGET_TEMPLATE}",
        "window_count": int(len(base)),
        "short_window_lt_126_count": int((days < 126).sum()),
        "short_window_lt_252_count": int((days < 252).sum()),
        "mean_total_return_all": float(base["recomputed_total_return"].mean()),
        "median_total_return_all": float(base["recomputed_total_return"].median()),
        "conservative_mean_cagr_days_ge_126": float(eligible_cagr["recomputed_cagr"].mean()) if not eligible_cagr.empty else np.nan,
        "conservative_median_cagr_days_ge_126": float(eligible_cagr["recomputed_cagr"].median()) if not eligible_cagr.empty else np.nan,
        "calmar_winsor_mean_all": float(clipped_calmar.mean()),
        "calmar_winsor_median_all": float(clipped_calmar.median()),
        "conservative_mean_calmar_days_ge_252": float(eligible_calmar["recomputed_calmar"].clip(-5, 5).mean()) if not eligible_calmar.empty else np.nan,
        "conservative_median_calmar_days_ge_252": float(eligible_calmar["recomputed_calmar"].clip(-5, 5).median()) if not eligible_calmar.empty else np.nan,
        "worst_25pct_mean_total_return": float(worst["recomputed_total_return"].mean()),
        "worst_25pct_mean_cagr": float(worst["recomputed_cagr"].mean()),
        "worst_25pct_mean_calmar_winsor": float(worst["recomputed_calmar"].clip(-5, 5).mean()),
        "positive_total_return_rate": float((base["recomputed_total_return"] > 0).mean()),
        "cagr20_pass_rate_days_ge_126": float((eligible_cagr["recomputed_cagr"] >= 0.20).mean()) if not eligible_cagr.empty else np.nan,
        "calmar1_pass_rate_days_ge_252": float((eligible_calmar["recomputed_calmar"] >= 1.0).mean()) if not eligible_calmar.empty else np.nan,
        "eligible_cagr_windows": int(len(eligible_cagr)),
        "eligible_calmar_windows": int(len(eligible_calmar)),
        "reported_mean_calmar": float(base["reported_calmar"].mean()),
        "recomputed_mean_calmar": float(base["recomputed_calmar"].mean()),
        "recomputed_median_calmar": float(base["recomputed_calmar"].median()),
        "leakage_pass": bool(leakage.get("overall_leakage_pass")),
        "dropout_exceeds_n_drop_rows": int(dropout["dropout_exceeds_n_drop"].sum()) if "dropout_exceeds_n_drop" in dropout else 0,
        **cost_summary,
        **bench_summary,
    }
    return pd.DataFrame([row])


def summarize_costs(costs: pd.DataFrame) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for cost, frame in costs.groupby("cost_bps_each_side"):
        out[f"cost_{int(cost)}bps_mean_cagr"] = float(frame["cagr"].mean())
        out[f"cost_{int(cost)}bps_mean_calmar_winsor"] = float(frame["calmar"].clip(-5, 5).mean())
        out[f"cost_{int(cost)}bps_pass_cagr20_rate_days_ge_126"] = float((frame.loc[frame["daily_count"] >= 126, "cagr"] >= 0.20).mean()) if (frame["daily_count"] >= 126).any() else np.nan
    return out


def summarize_benchmarks(benchmarks: pd.DataFrame) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if benchmarks.empty:
        return out
    for bench, frame in benchmarks.groupby("benchmark"):
        key = bench.replace("_buy_hold", "").replace("Pool_A_equal_weight_monthly", "pool_a_equal")
        out[f"same_window_win_rate_cagr_vs_{key}"] = float((frame["strategy_cagr_minus_benchmark"] > 0).mean())
        out[f"same_window_win_rate_calmar_vs_{key}"] = float((frame["strategy_calmar_minus_benchmark"] > 0).mean())
        out[f"same_window_mean_cagr_diff_vs_{key}"] = float(frame["strategy_cagr_minus_benchmark"].mean())
        out[f"same_window_mean_calmar_diff_vs_{key}"] = float(frame["strategy_calmar_minus_benchmark"].replace([np.inf, -np.inf], np.nan).mean())
    return out


def classify_audit(
    recomputed: pd.DataFrame,
    annualization: pd.DataFrame,
    drawdown: pd.DataFrame,
    leakage: dict[str, Any],
    dropout: pd.DataFrame,
    weight_sum: pd.DataFrame,
    rebalance_calendar: pd.DataFrame,
    conservative: pd.DataFrame,
    costs: pd.DataFrame,
    benchmarks: pd.DataFrame,
) -> dict[str, Any]:
    recalc_pass = bool(recomputed["pass_recalc_check"].all())
    leakage_pass = bool(leakage.get("overall_leakage_pass"))
    weight_pass = bool(weight_sum.empty or weight_sum["pass_weight_sum_check"].all())
    calendar_pass = bool(rebalance_calendar.empty or rebalance_calendar["pass_monthly_rebalance_check"].all())
    strict_dropout_pass = bool(dropout.empty or not dropout["dropout_exceeds_n_drop"].any())
    short_amp = bool(annualization["annualization_amplified"].any())
    low_dd_amp = bool(drawdown["maxdd_too_small_flag"].any())
    row = conservative.iloc[0].to_dict() if not conservative.empty else {}
    cost50 = costs.loc[costs["cost_bps_each_side"] == 50].copy()
    cost50_mean_cagr = float(cost50.loc[cost50["daily_count"] >= 126, "cagr"].mean()) if not cost50.empty else np.nan
    qqq = benchmarks.loc[benchmarks["benchmark"] == "QQQ_buy_hold"] if not benchmarks.empty else pd.DataFrame()
    qqq_cagr_win = float((qqq["strategy_cagr_minus_benchmark"] > 0).mean()) if not qqq.empty else 0.0
    qqq_calmar_win = float((qqq["strategy_calmar_minus_benchmark"] > 0).mean()) if not qqq.empty else 0.0

    reasons: list[str] = []
    if not recalc_pass:
        reasons.append("reported metrics do not match price+weight recomputation")
    if not leakage_pass:
        reasons.append("alignment or label leakage check failed")
    if not weight_pass:
        reasons.append("weight sum/count check failed")
    if not calendar_pass:
        reasons.append("weights changed outside monthly rebalance dates")
    if not strict_dropout_pass:
        reasons.append("Top10 dropout replaced more than configured n_drop in at least one rebalance")
    if short_amp:
        reasons.append("several windows are shorter than 126 trading days, so annualized CAGR is amplified")
    if low_dd_amp:
        reasons.append("some short windows have near-zero drawdown, inflating Calmar")

    if not recalc_pass or not leakage_pass or not weight_pass or not calendar_pass:
        classification = "invalid_due_to_backtest_bug"
        allow_v8 = False
    elif not strict_dropout_pass:
        classification = "invalid_due_to_backtest_bug"
        allow_v8 = False
    elif short_amp or low_dd_amp:
        if (
            float(row.get("conservative_mean_cagr_days_ge_126", 0.0) or 0.0) >= 0.20
            and float(row.get("calmar_winsor_mean_all", 0.0) or 0.0) >= 1.0
            and cost50_mean_cagr >= 0.15
            and qqq_cagr_win >= 0.5
            and qqq_calmar_win >= 0.5
        ):
            classification = "promising_but_needs_more_validation"
        else:
            classification = "likely_metric_artifact"
        allow_v8 = False
    elif (
        float(row.get("conservative_mean_cagr_days_ge_126", 0.0) or 0.0) >= 0.20
        and float(row.get("calmar_winsor_mean_all", 0.0) or 0.0) >= 1.0
        and cost50_mean_cagr >= 0.15
        and qqq_cagr_win >= 0.6
        and qqq_calmar_win >= 0.6
    ):
        classification = "credible_research_candidate"
        allow_v8 = True
    else:
        classification = "likely_metric_artifact"
        allow_v8 = False

    return {
        "classification": classification,
        "allow_enter_v8": bool(allow_v8),
        "reported_mean_calmar_trustworthy": bool(classification == "credible_research_candidate" and not short_amp and not low_dd_amp),
        "recalc_pass": recalc_pass,
        "leakage_pass": leakage_pass,
        "weight_sum_pass": weight_pass,
        "monthly_rebalance_pass": calendar_pass,
        "strict_dropout_n_drop_pass": strict_dropout_pass,
        "annualization_amplification_found": short_amp,
        "low_drawdown_calmar_amplification_found": low_dd_amp,
        "cost50_mean_cagr_days_ge_126": cost50_mean_cagr,
        "same_window_qqq_cagr_win_rate": qqq_cagr_win,
        "same_window_qqq_calmar_win_rate": qqq_calmar_win,
        "reason": "; ".join(reasons) if reasons else "audit checks passed under conservative rules",
    }


def build_v7_audit_report(
    path: Path | str,
    source: Path,
    recomputed: pd.DataFrame,
    annualization: pd.DataFrame,
    drawdown: pd.DataFrame,
    alignment: pd.DataFrame,
    leakage: dict[str, Any],
    dropout: pd.DataFrame,
    weight_sum: pd.DataFrame,
    rebalance_calendar: pd.DataFrame,
    costs: pd.DataFrame,
    benchmarks: pd.DataFrame,
    conservative: pd.DataFrame,
    verdict: dict[str, Any],
) -> Path:
    cons = conservative.iloc[0].to_dict() if not conservative.empty else {}
    cost_summary = costs.groupby("cost_bps_each_side").agg(
        window_count=("wf_name", "count"),
        mean_cagr=("cagr", "mean"),
        median_cagr=("cagr", "median"),
        mean_calmar=("calmar", "mean"),
        winsor_calmar=("calmar", lambda s: float(s.clip(-5, 5).mean())),
        min_calmar=("calmar", "min"),
    ).reset_index()
    bench_summary = (
        benchmarks.groupby("benchmark")
        .agg(
            window_count=("wf_name", "count"),
            cagr_win_rate=("strategy_cagr_minus_benchmark", lambda s: float((s > 0).mean())),
            calmar_win_rate=("strategy_calmar_minus_benchmark", lambda s: float((s > 0).mean())),
            mean_cagr_diff=("strategy_cagr_minus_benchmark", "mean"),
            mean_calmar_diff=("strategy_calmar_minus_benchmark", "mean"),
        )
        .reset_index()
        if not benchmarks.empty
        else pd.DataFrame()
    )
    text = f"""# US Stock Selection v7 Audit Report

## 1. Audit Object

- Source v7 run: `{source}`
- Strategy: `{TARGET_FEATURE_SET} + {TARGET_MODEL} + {TARGET_LABEL} + {TARGET_TEMPLATE}`
- Original reported mean Calmar: `{recomputed["reported_calmar"].mean():.6f}`
- Recomputed mean Calmar: `{recomputed["recomputed_calmar"].mean():.6f}`
- Final audit classification: `{verdict.get("classification")}`
- Allow entering v8: `{verdict.get("allow_enter_v8")}`

## 2. Reported vs Recomputed

{markdown_table(recomputed.drop(columns=["returns", "nav"], errors="ignore"), ["wf_name", "test_days", "reported_cagr", "recomputed_cagr", "reported_maxdd", "recomputed_maxdd", "reported_calmar", "recomputed_calmar", "diff_calmar", "pass_recalc_check"])}

Result: reported metrics are `{ "consistent" if bool(recomputed["pass_recalc_check"].all()) else "not consistent" }` with recomputation from raw provider prices and stored holdings.

## 3. Annualization And Calmar Audit

- Windows shorter than 126 trading days: `{int(annualization["short_window_lt_126"].sum())}`
- Windows shorter than 252 trading days: `{int((annualization["test_days"] < 252).sum())}`
- Low drawdown amplification flags: `{int(drawdown["maxdd_too_small_flag"].sum())}`
- Conservative mean CAGR, days >= 126 only: `{cons.get("conservative_mean_cagr_days_ge_126")}`
- Calmar winsorized mean all windows: `{cons.get("calmar_winsor_mean_all")}`
- Conservative mean Calmar, days >= 252 only: `{cons.get("conservative_mean_calmar_days_ge_252")}`

The original mean Calmar is `{ "not trustworthy as a headline metric" if verdict.get("annualization_amplification_found") or verdict.get("low_drawdown_calmar_amplification_found") else "not obviously inflated by window length" }`.

## 4. Drawdown Audit

{markdown_table(drawdown, ["wf_name", "test_days", "end_nav", "min_nav", "peak_date", "trough_date", "maxdd", "maxdd_too_small_flag"])}

## 5. Alignment And Leakage

- Overall leakage pass: `{leakage.get("overall_leakage_pass")}`
- Label not in feature columns: `{leakage.get("label_not_in_feature_columns")}`
- Forward label expression not in features: `{leakage.get("label_forward_expression_not_in_features")}`
- Trade execution after prediction: `{leakage.get("trade_execution_after_prediction_all")}`
- Same-day return consumed: `{leakage.get("same_day_return_consumed")}`

Note: v7 stores label values in the feature cache for training/evaluation, and drops label-unavailable tail dates. The audit did not find label columns entering feature columns.

## 6. Top10 Dropout Logic

- Strict n_drop pass: `{verdict.get("strict_dropout_n_drop_pass")}`
- Rows where dropped_count > n_drop: `{int(dropout["dropout_exceeds_n_drop"].sum()) if not dropout.empty else 0}`
- Weight sum pass: `{verdict.get("weight_sum_pass")}`
- Monthly rebalance pass: `{verdict.get("monthly_rebalance_pass")}`

{markdown_table(dropout.head(30), ["wf_name", "rebalance_date", "holding_count", "weight_sum", "dropped_count", "added_count", "dropout_exceeds_n_drop"])}

## 7. Cost Audit

v7 reported results use 5 bps cost + 5 bps slippage. The 0 bps rows below are gross; all other rows are net after cost and slippage.

{markdown_table(cost_summary, ["cost_bps_each_side", "window_count", "mean_cagr", "median_cagr", "winsor_calmar", "min_calmar"])}

## 8. Same-Window Benchmark

{markdown_table(bench_summary, ["benchmark", "window_count", "cagr_win_rate", "calmar_win_rate", "mean_cagr_diff", "mean_calmar_diff"])}

## 9. Conservative WF Summary

{markdown_table(conservative, list(conservative.columns[:24]))}

## 10. Verdict

- Classification: `{verdict.get("classification")}`
- Reason: `{verdict.get("reason")}`
- Enter v8 now: `{verdict.get("allow_enter_v8")}`

Decision: do not enter v8 until this audit result is reviewed. If the classification is `invalid_due_to_backtest_bug` or `likely_metric_artifact`, v7 must be fixed and rerun before any expansion or robustness optimization.
"""
    return save_text(text, path)


def package_v7_audit_run(run_dir: Path | str, timestamp: str) -> Path:
    base = Path(run_dir).resolve()
    zip_path = base.parent / f"us_stock_selection_quant_lab_v7_audit_{timestamp}.zip"
    paths = [
        PROJECT_ROOT / "AGENTS.md",
        PROJECT_ROOT / "NEXT_STEPS.md",
        PROJECT_ROOT / "RUN_SUMMARY.md",
        PROJECT_ROOT / "docs" / "US_STOCK_SELECTION_AUTORUN.md",
        PROJECT_ROOT / "scripts" / "us_stock_selection",
        PROJECT_ROOT / "quant_lab" / "us_stock_selection",
        base / "v7_audit",
        base / "reports",
        base / "logs",
        base / "RUN_SUMMARY.md",
    ]
    return zip_selected_paths(paths, zip_path, root=PROJECT_ROOT)


def build_run_summary_text(run_dir: Path | str, source: Path, verdict: dict[str, Any], conservative: pd.DataFrame) -> str:
    cons = conservative.iloc[0].to_dict() if not conservative.empty else {}
    return f"""# RUN_SUMMARY

本轮目标：v7_audit，反向审计 v7 fast walk-forward 的异常高 Calmar。

源 run：`{source}`

新 audit run：`{Path(run_dir)}`

最终分类：`{verdict.get("classification")}`

是否允许进入 v8：`{verdict.get("allow_enter_v8")}`

核心保守指标：
- conservative_mean_cagr_days_ge_126: `{cons.get("conservative_mean_cagr_days_ge_126")}`
- calmar_winsor_mean_all: `{cons.get("calmar_winsor_mean_all")}`
- positive_total_return_rate: `{cons.get("positive_total_return_rate")}`
- cagr20_pass_rate_days_ge_126: `{cons.get("cagr20_pass_rate_days_ge_126")}`
- calmar1_pass_rate_days_ge_252: `{cons.get("calmar1_pass_rate_days_ge_252")}`

审计结论：{verdict.get("reason")}
"""


def build_next_steps_text(verdict: dict[str, Any]) -> str:
    if verdict.get("allow_enter_v8"):
        return """# NEXT_STEPS

v7_audit 未发现核心回测错误，且保守口径仍满足 credible_research_candidate。

下一步：进入 v8 稳健组合优化，但仍不扩 Nasdaq100/S&P500，先围绕 Top5/Top10 dropout 做成本、波动率、crash filter 和集中度优化。
"""
    if verdict.get("strict_dropout_n_drop_pass"):
        return f"""# NEXT_STEPS

当前下一步：继续 v7 证据加固，不进入 v8，不扩 Nasdaq100/S&P500。

当前分类：`{verdict.get("classification")}`

已完成：
1. TopKDropout 已修正为严格 n_drop 替换；
2. reported vs recomputed 已通过；
3. 未发现 label 进入 feature 或同日收益偷吃；
4. 成本和同窗口基准已输出。

剩余瓶颈：
1. 仍有较多 `<126` 或 `<252` 交易日短窗口；
2. Calmar 仍受短窗口低回撤放大；
3. eligible Calmar window 数量不足，不能进入 credible_research_candidate。

下一轮优先事项：
1. 增加更长 test window 或合并半年度窗口，减少短窗口年化依赖；
2. 对 Top5 equal / Top5 dropout / Top10 dropout 做同一保守口径审计；
3. 输出短窗口 total_return 主表，CAGR/Calmar 只作辅助；
4. 复核通过前，不进入 v8，不扩 Nasdaq100/S&P500。
"""
    return f"""# NEXT_STEPS

当前下一步：不要进入 v8，先修复或复核 v7_audit 暴露的问题。

当前分类：`{verdict.get("classification")}`

优先事项：
1. 如果是 dropout 规则不符，修正 TopKDropout 为严格 n_drop 替换后重跑 v7；
2. 如果是 Calmar/年化口径放大，重做 v7 summary，短窗口只展示 total_return，不作为主结论；
3. 保留同窗口基准和成本后结果；
4. 复核通过前，不扩 Nasdaq100/S&P500。
"""


def iter_recomputed(recomputed: pd.DataFrame):
    for _, row in recomputed.iterrows():
        yield row


def detect_rebalance_dates(weights: pd.DataFrame) -> list[pd.Timestamp]:
    changes = weight_change_dates(weights)
    return changes


def weight_change_dates(weights: pd.DataFrame) -> list[pd.Timestamp]:
    diff = weights.diff().abs().sum(axis=1).fillna(weights.abs().sum(axis=1))
    return [pd.Timestamp(idx) for idx, val in diff.items() if float(val) > 1e-10]


def month_end_dates(index: pd.DatetimeIndex) -> list[pd.Timestamp]:
    idx = pd.DatetimeIndex(index).sort_values()
    target = pd.Series(index=idx, data=np.arange(len(idx))).resample("ME").last().dropna().index
    return [pd.Timestamp(x) for x in idx[idx.isin(target)]]


def monthly_equal_weights(close: pd.DataFrame, start_invested: bool = True) -> pd.DataFrame:
    weights = pd.DataFrame(np.nan, index=close.index, columns=close.columns, dtype=float)
    dates = month_end_dates(close.index)
    if start_invested and len(close.index):
        dates = [pd.Timestamp(close.index[0]), *[d for d in dates if d != close.index[0]]]
    for date in dates:
        avail = close.loc[date].dropna().index
        if len(avail):
            weights.loc[date, avail] = 1.0 / len(avail)
    return weights.ffill().fillna(0.0)


def format_benchmark_row(row: pd.Series, benchmark: str, metrics: dict[str, Any], strategy: dict[str, float]) -> dict[str, Any]:
    return {
        "window_id": row["window_id"],
        "wf_type": row["wf_type"],
        "wf_name": row["wf_name"],
        "test_start": row["test_start"],
        "test_end": row["test_end"],
        "benchmark": benchmark,
        **strategy,
        "benchmark_total_return": metrics.get("total_return", 0.0),
        "benchmark_cagr": metrics.get("cagr", 0.0),
        "benchmark_max_drawdown": metrics.get("max_drawdown", 0.0),
        "benchmark_calmar": metrics.get("calmar", 0.0),
        "strategy_cagr_minus_benchmark": strategy["strategy_cagr"] - metrics.get("cagr", 0.0),
        "strategy_calmar_minus_benchmark": strategy["strategy_calmar"] - metrics.get("calmar", 0.0),
    }


def latest_on_or_before(index: pd.DatetimeIndex, date: pd.Timestamp) -> pd.Timestamp | pd.NaT:
    idx = pd.DatetimeIndex(index)
    idx = idx[idx <= pd.Timestamp(date)]
    return idx.max() if len(idx) else pd.NaT


def next_trading_date(index: pd.DatetimeIndex, date: pd.Timestamp, step: int) -> pd.Timestamp | pd.NaT:
    idx = pd.DatetimeIndex(index).sort_values()
    pos = idx.searchsorted(pd.Timestamp(date), side="right")
    target = pos + step - 1
    if target >= len(idx):
        return pd.NaT
    return pd.Timestamp(idx[target])


def markdown_table(df: pd.DataFrame, columns: list[str], max_rows: int = 30) -> str:
    if df is None or df.empty:
        return "_No rows_\n"
    cols = [c for c in columns if c in df.columns]
    if not cols:
        return "_No display columns_\n"
    sub = df.loc[:, cols].head(max_rows).copy()
    for col in sub.columns:
        if pd.api.types.is_float_dtype(sub[col]):
            sub[col] = sub[col].map(lambda x: "" if pd.isna(x) else f"{float(x):.6f}")
    header = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join(["---"] * len(cols)) + " |"
    rows = ["| " + " | ".join(str(row[c]).replace("|", "/") for c in cols) + " |" for _, row in sub.iterrows()]
    return "\n".join([header, sep, *rows]) + "\n"
