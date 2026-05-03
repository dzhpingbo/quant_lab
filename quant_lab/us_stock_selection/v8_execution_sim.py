"""Execution realism, stress tests, and attribution for v8."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from quant_lab.us_stock_selection.portfolio_robustifier import ticker_contributions
from quant_lab.us_stock_selection.qlib_signal_backtest import compute_portfolio_metrics, portfolio_returns
from quant_lab.us_stock_selection.utils import ensure_dir, nav_from_returns, save_dataframe
from quant_lab.us_stock_selection.v8_paper_trading import date_str, trading_offset


def weights_from_decisions(
    decisions: pd.DataFrame,
    close: pd.DataFrame,
    execution_delay: int,
    max_weight: float = 0.20,
    remove_ticker: str | None = None,
) -> pd.DataFrame:
    weights = pd.DataFrame(np.nan, index=close.index, columns=close.columns)
    for _, row in decisions.iterrows():
        decision_date = pd.Timestamp(row["decision_date"])
        execution_date = trading_offset(close.index, decision_date, execution_delay)
        if pd.isna(execution_date) or execution_date > close.index.max():
            continue
        selected = [ticker for ticker in str(row["selected_tickers"]).split(",") if ticker and ticker in close.columns and ticker != remove_ticker]
        selected = selected[:5]
        if not selected:
            continue
        current = pd.Series(0.0, index=close.columns)
        w = min(max_weight, 1.0 / len(selected))
        current.loc[selected] = w
        if current.sum() > 0 and current.sum() < 0.999 and max_weight >= 1.0 / len(selected):
            current = current / current.sum()
        weights.loc[execution_date] = current
    return weights.ffill().fillna(0.0)


def evaluate_weights(close: pd.DataFrame, weights: pd.DataFrame, cost_bps: float, slippage_bps: float) -> tuple[dict[str, Any], pd.Series, pd.Series]:
    local_close = close.loc[weights.index.min() : weights.index.max(), weights.columns].ffill()
    weights = weights.reindex(local_close.index).ffill().fillna(0.0)
    returns, turnover = portfolio_returns(local_close, weights, cost_bps=cost_bps, slippage_bps=slippage_bps)
    return compute_portfolio_metrics(returns, turnover, weights), returns, turnover


def run_execution_stress_tests(
    out_dir: Path | str,
    decisions: pd.DataFrame,
    close: pd.DataFrame,
    primary_weights: pd.DataFrame,
    primary_returns: pd.Series,
) -> dict[str, pd.DataFrame]:
    out = ensure_dir(out_dir)
    rows: list[dict[str, Any]] = []
    for cost in [5, 10, 20, 50]:
        for slip in [0, 5, 10, 20]:
            for delay in [0, 1, 2]:
                for max_weight in [0.20, 0.25, 0.30]:
                    weights = weights_from_decisions(decisions, close, execution_delay=delay, max_weight=max_weight)
                    metrics, _, _ = evaluate_weights(close, weights, cost_bps=float(cost), slippage_bps=float(slip))
                    rows.append(
                        {
                            "test_name": f"cost{cost}_slip{slip}_delay{delay}_mw{max_weight}",
                            "stress_type": "execution_grid",
                            "cost_bps": cost,
                            "slippage_bps": slip,
                            "execution_delay": delay,
                            "max_weight": max_weight,
                            **metrics,
                        }
                    )
    contrib = ticker_contributions(close.loc[primary_weights.index.min() : primary_weights.index.max(), primary_weights.columns], primary_weights)
    top_ticker = str(contrib.iloc[0]["ticker"]) if not contrib.empty else ""
    if top_ticker:
        weights = weights_from_decisions(decisions, close, execution_delay=1, max_weight=0.20, remove_ticker=top_ticker)
        metrics, _, _ = evaluate_weights(close, weights, cost_bps=5.0, slippage_bps=5.0)
        rows.append({"test_name": f"remove_top_ticker_{top_ticker}", "stress_type": "remove_top_contributor", "removed_ticker": top_ticker, **metrics})
    yearly = yearly_returns(primary_returns)
    for year in yearly["year"].tolist() if not yearly.empty else []:
        ret = primary_returns.loc[primary_returns.index.year != int(year)]
        temp_weights = primary_weights.loc[primary_weights.index.year != int(year)]
        if ret.empty or temp_weights.empty:
            continue
        nav = nav_from_returns(ret)
        turnover = temp_weights.diff().abs().sum(axis=1).fillna(temp_weights.abs().sum(axis=1))
        metrics = compute_portfolio_metrics(ret, turnover.reindex(ret.index).fillna(0.0), temp_weights.reindex(ret.index).fillna(0.0))
        rows.append({"test_name": f"remove_year_{year}", "stress_type": "leave_one_year_out", "removed_year": int(year), **metrics})
    stress = pd.DataFrame(rows)
    save_dataframe(stress, out / "execution_stress_results.csv")
    return {"stress": stress, "ticker_contribution": contrib, "yearly": yearly}


def build_attribution(
    out_dir: Path | str,
    close: pd.DataFrame,
    weights: pd.DataFrame,
    returns: pd.Series,
) -> dict[str, pd.DataFrame]:
    out = ensure_dir(out_dir)
    local_close = close.loc[weights.index.min() : weights.index.max(), weights.columns].ffill()
    weights = weights.reindex(local_close.index).ffill().fillna(0.0)
    herf = weights.pow(2).sum(axis=1)
    holding_concentration = pd.DataFrame(
        {
            "date": weights.index,
            "holding_count": (weights > 1e-12).sum(axis=1).values,
            "weight_sum": weights.sum(axis=1).values,
            "herfindahl": herf.values,
            "max_weight": weights.max(axis=1).values,
            "top_holding": weights.idxmax(axis=1).values,
        }
    )
    ticker_contrib = ticker_contributions(local_close, weights)
    yearly = yearly_returns(returns)
    monthly = monthly_returns(returns)
    top_months = monthly.sort_values("monthly_return", ascending=False).head(12)
    save_dataframe(holding_concentration, out / "holding_concentration.csv")
    save_dataframe(ticker_contrib, out / "ticker_contribution.csv")
    save_dataframe(yearly, out / "yearly_return.csv")
    save_dataframe(monthly, out / "monthly_return.csv")
    save_dataframe(top_months, out / "top_return_months.csv")
    return {
        "holding_concentration": holding_concentration,
        "ticker_contribution": ticker_contrib,
        "yearly": yearly,
        "monthly": monthly,
        "top_months": top_months,
    }


def yearly_returns(returns: pd.Series) -> pd.DataFrame:
    if returns.empty:
        return pd.DataFrame(columns=["year", "year_return"])
    out = returns.groupby(returns.index.year).apply(lambda s: float((1.0 + s).prod() - 1.0)).rename("year_return").reset_index()
    out.columns = ["year", "year_return"]
    return out


def monthly_returns(returns: pd.Series) -> pd.DataFrame:
    if returns.empty:
        return pd.DataFrame(columns=["month", "monthly_return"])
    series = returns.groupby(returns.index.to_period("M")).apply(lambda s: float((1.0 + s).prod() - 1.0))
    return pd.DataFrame({"month": series.index.astype(str), "monthly_return": series.values})
