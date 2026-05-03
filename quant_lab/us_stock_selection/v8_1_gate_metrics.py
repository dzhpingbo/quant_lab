"""v8.1 gate-aware concentration metrics.

These helpers operate on existing v8 artifacts or already-built return/weight
series. They do not fit models, expand the universe, or overwrite v8 verdicts.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from quant_lab.us_stock_selection.qlib_signal_backtest import compute_portfolio_metrics
from quant_lab.us_stock_selection.utils import nav_from_returns


HARD_GATE_THRESHOLDS = {
    "leave_one_year_out_min_cagr": (">=", 0.20),
    "leave_one_year_out_min_calmar": (">=", 1.0),
    "top1_positive_month_share": ("<=", 0.25),
    "top3_positive_month_share": ("<=", 0.50),
    "max_ticker_abs_share": ("<=", 0.30),
    "max_ticker_month_weight": ("<=", 0.30),
}

OBSERVATION_GATE_THRESHOLDS = {
    "current_abs_return_share": ("<=", 0.55),
    "top5_positive_month_share": ("<=", 0.60),
    "rolling_12m_min_calmar_like": (">=", 0.5),
    "dominant_year_unique_ticker_count": (">=", 10),
    "dominant_year_avg_holding_count": (">=", 3),
}


def read_csv(path: Path, required: bool = True) -> pd.DataFrame:
    if not path.exists():
        if required:
            raise FileNotFoundError(path)
        return pd.DataFrame()
    return pd.read_csv(path)


def normalize_daily_nav(daily: pd.DataFrame) -> pd.DataFrame:
    out = daily.copy()
    if out.empty:
        return pd.DataFrame(columns=["date", "return", "nav", "turnover"])
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out["return"] = pd.to_numeric(out.get("return", 0.0), errors="coerce").fillna(0.0)
    if "nav" not in out:
        out["nav"] = nav_from_returns(out.set_index("date")["return"]).values
    out["nav"] = pd.to_numeric(out["nav"], errors="coerce")
    out["turnover"] = pd.to_numeric(out.get("turnover", 0.0), errors="coerce").fillna(0.0)
    return out.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)


def max_drawdown(nav: pd.Series) -> float:
    clean = pd.to_numeric(nav, errors="coerce").dropna()
    if clean.empty:
        return float("nan")
    peak = clean.cummax()
    return float((clean / peak - 1.0).min())


def metrics_from_returns(returns: pd.Series, turnover: pd.Series | None = None, weights: pd.DataFrame | None = None) -> dict[str, Any]:
    returns = pd.to_numeric(returns, errors="coerce").dropna()
    turnover = turnover.reindex(returns.index).fillna(0.0) if turnover is not None else pd.Series(0.0, index=returns.index)
    weights = weights.reindex(returns.index).fillna(0.0) if weights is not None else pd.DataFrame({"cash": 0.0}, index=returns.index)
    return compute_portfolio_metrics(returns, turnover, weights)


def annual_table_from_daily(daily: pd.DataFrame) -> pd.DataFrame:
    daily = normalize_daily_nav(daily)
    rows: list[dict[str, Any]] = []
    for year, group in daily.groupby(daily["date"].dt.year):
        first = group.iloc[0]
        start_nav = float(first["nav"] / (1.0 + first["return"])) if 1.0 + float(first["return"]) != 0 else float(first["nav"])
        end_nav = float(group["nav"].iloc[-1])
        annual_return = float((1.0 + group["return"]).prod() - 1.0)
        local_nav = pd.concat([pd.Series([start_nav]), group["nav"].reset_index(drop=True)], ignore_index=True)
        rows.append(
            {
                "year": int(year),
                "start_nav": start_nav,
                "end_nav": end_nav,
                "annual_return": annual_return,
                "annual_profit": end_nav - start_nav,
                "max_drawdown_in_year": max_drawdown(local_nav),
                "trading_month_count": int(group["date"].dt.to_period("M").nunique()),
            }
        )
    annual = pd.DataFrame(rows)
    if annual.empty:
        return annual
    abs_ret_sum = annual["annual_return"].abs().sum()
    abs_profit_sum = annual["annual_profit"].abs().sum()
    pos_profit_sum = annual.loc[annual["annual_profit"] > 0, "annual_profit"].sum()
    annual["gate_abs_year_return_share"] = annual["annual_return"].abs() / abs_ret_sum if abs_ret_sum else 0.0
    annual["annual_profit_share"] = annual["annual_profit"].abs() / abs_profit_sum if abs_profit_sum else 0.0
    annual["positive_profit_share"] = np.where(
        annual["annual_profit"] > 0,
        annual["annual_profit"] / pos_profit_sum if pos_profit_sum else 0.0,
        0.0,
    )
    return annual


def monthly_table_from_daily(daily: pd.DataFrame) -> pd.DataFrame:
    daily = normalize_daily_nav(daily)
    rows: list[dict[str, Any]] = []
    for period, group in daily.groupby(daily["date"].dt.to_period("M")):
        first = group.iloc[0]
        start_nav = float(first["nav"] / (1.0 + first["return"])) if 1.0 + float(first["return"]) != 0 else float(first["nav"])
        end_nav = float(group["nav"].iloc[-1])
        local_nav = pd.concat([pd.Series([start_nav]), group["nav"].reset_index(drop=True)], ignore_index=True)
        rows.append(
            {
                "month": str(period),
                "monthly_return": float((1.0 + group["return"]).prod() - 1.0),
                "monthly_profit": end_nav - start_nav,
                "cumulative_nav_before": start_nav,
                "cumulative_nav_after": end_nav,
                "max_drawdown_in_month": max_drawdown(local_nav),
            }
        )
    monthly = pd.DataFrame(rows)
    if monthly.empty:
        return monthly
    pos_sum = monthly.loc[monthly["monthly_profit"] > 0, "monthly_profit"].sum()
    abs_sum = monthly["monthly_profit"].abs().sum()
    monthly["positive_profit_share"] = np.where(
        monthly["monthly_profit"] > 0,
        monthly["monthly_profit"] / pos_sum if pos_sum else 0.0,
        0.0,
    )
    monthly["contribution_share"] = monthly["monthly_profit"].abs() / abs_sum if abs_sum else 0.0
    return monthly


def leave_one_year_out_metrics(daily: pd.DataFrame) -> pd.DataFrame:
    daily = normalize_daily_nav(daily)
    rows: list[dict[str, Any]] = []
    for year in sorted(daily["date"].dt.year.unique()):
        local = daily.loc[daily["date"].dt.year != year].copy()
        metrics = metrics_from_returns(local.set_index("date")["return"], local.set_index("date")["turnover"])
        rows.append({"removed_year": int(year), "cagr_ge_20": bool(metrics["cagr"] >= 0.20), **metrics})
    return pd.DataFrame(rows)


def top_month_removed_metrics(daily: pd.DataFrame, monthly: pd.DataFrame | None = None) -> pd.DataFrame:
    daily = normalize_daily_nav(daily)
    monthly = monthly_table_from_daily(daily) if monthly is None or monthly.empty else monthly
    top_months = monthly.loc[monthly["monthly_profit"] > 0].sort_values("monthly_profit", ascending=False)["month"].tolist()
    rows: list[dict[str, Any]] = []
    for n in [1, 3, 5]:
        removed = top_months[:n]
        local = daily.loc[~daily["date"].dt.to_period("M").astype(str).isin(removed)].copy()
        metrics = metrics_from_returns(local.set_index("date")["return"], local.set_index("date")["turnover"])
        rows.append({"removed_top_positive_month_count": n, "removed_months": ",".join(removed), **metrics})
    return pd.DataFrame(rows)


def rolling_12m_metrics(daily: pd.DataFrame) -> pd.DataFrame:
    daily = normalize_daily_nav(daily)
    months = sorted(daily["date"].dt.to_period("M").unique())
    rows: list[dict[str, Any]] = []
    for i in range(0, len(months) - 11):
        window = months[i : i + 12]
        local = daily.loc[daily["date"].dt.to_period("M").isin(window)].copy()
        metrics = metrics_from_returns(local.set_index("date")["return"], local.set_index("date")["turnover"])
        rows.append(
            {
                "start_month": str(window[0]),
                "end_month": str(window[-1]),
                "window_month_count": 12,
                "window_return": metrics["total_return"],
                "window_max_drawdown": metrics["max_drawdown"],
                "calmar_like": metrics["calmar"],
                "daily_count": metrics["daily_count"],
            }
        )
    return pd.DataFrame(rows)


def concentration_penalty_score(metrics: dict[str, float]) -> tuple[float, dict[str, float]]:
    parts = {
        "year_return_concentration_penalty": clipped((metrics.get("current_abs_return_share", 0.0) - 0.50) / 0.15),
        "top_month_concentration_penalty": clipped((metrics.get("top3_positive_month_share", 0.0) - 0.40) / 0.25),
        "ticker_exposure_penalty": clipped((metrics.get("max_ticker_abs_share", 0.0) - 0.25) / 0.15),
        "rolling_12m_instability_penalty": clipped((1.00 - metrics.get("rolling_12m_min_calmar_like", 1.0)) / 1.0),
        "high_beta_asset_penalty": clipped((metrics.get("high_beta_weight_share", 0.0) - 0.25) / 0.25),
    }
    weights = {
        "year_return_concentration_penalty": 0.25,
        "top_month_concentration_penalty": 0.25,
        "ticker_exposure_penalty": 0.20,
        "rolling_12m_instability_penalty": 0.20,
        "high_beta_asset_penalty": 0.10,
    }
    return float(sum(parts[k] * weights[k] for k in parts)), parts


def clipped(value: float) -> float:
    if value is None or math.isnan(float(value)):
        return 0.0
    return float(min(1.0, max(0.0, value)))


def summarize_gate_metrics(
    daily: pd.DataFrame,
    ticker_abs_share: float,
    max_ticker_month_weight: float,
    dominant_year_unique_ticker_count: float,
    dominant_year_avg_holding_count: float,
    high_beta_weight_share: float = 0.0,
) -> dict[str, Any]:
    annual = annual_table_from_daily(daily)
    monthly = monthly_table_from_daily(daily)
    loo = leave_one_year_out_metrics(daily)
    removed = top_month_removed_metrics(daily, monthly)
    rolling = rolling_12m_metrics(daily)
    top_pos = monthly.sort_values("monthly_profit", ascending=False)
    metrics = {
        "current_abs_return_share": float(annual["gate_abs_year_return_share"].max()) if not annual.empty else np.nan,
        "leave_one_year_out_min_cagr": float(loo["cagr"].min()) if not loo.empty else np.nan,
        "leave_one_year_out_min_calmar": float(loo["calmar"].min()) if not loo.empty else np.nan,
        "top1_positive_month_share": float(top_pos["positive_profit_share"].head(1).sum()) if not top_pos.empty else np.nan,
        "top3_positive_month_share": float(top_pos["positive_profit_share"].head(3).sum()) if not top_pos.empty else np.nan,
        "top5_positive_month_share": float(top_pos["positive_profit_share"].head(5).sum()) if not top_pos.empty else np.nan,
        "rolling_12m_min_return": float(rolling["window_return"].min()) if not rolling.empty else np.nan,
        "rolling_12m_min_calmar_like": float(rolling["calmar_like"].min()) if not rolling.empty else np.nan,
        "rolling_12m_max_return": float(rolling["window_return"].max()) if not rolling.empty else np.nan,
        "max_ticker_abs_share": float(ticker_abs_share),
        "max_ticker_month_weight": float(max_ticker_month_weight),
        "dominant_year_unique_ticker_count": float(dominant_year_unique_ticker_count),
        "dominant_year_avg_holding_count": float(dominant_year_avg_holding_count),
        "high_beta_weight_share": float(high_beta_weight_share),
    }
    metrics["rolling_12m_return_gap"] = metrics["rolling_12m_max_return"] - metrics["rolling_12m_min_return"]
    score, parts = concentration_penalty_score(metrics)
    metrics["concentration_penalty_score"] = score
    metrics.update(parts)
    return metrics


def gate_results_from_metrics(metrics: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for layer, thresholds in [("hard", HARD_GATE_THRESHOLDS), ("observation", OBSERVATION_GATE_THRESHOLDS)]:
        for gate_name, (direction, threshold) in thresholds.items():
            value = float(metrics.get(gate_name, np.nan))
            if math.isnan(value):
                status = "unknown"
            elif direction == ">=":
                status = "pass" if value >= threshold else "fail"
            else:
                status = "pass" if value <= threshold else "fail"
            rows.append(
                {
                    "gate_name": gate_name,
                    "gate_layer": layer,
                    "metric_value": value,
                    "threshold": f"{direction} {threshold}",
                    "pass_fail": status,
                }
            )
    return pd.DataFrame(rows)
