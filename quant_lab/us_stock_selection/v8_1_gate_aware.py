"""v8.1 gate-aware scoring and lightweight replay helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from quant_lab.us_stock_selection.portfolio_robustifier import ticker_contributions
from quant_lab.us_stock_selection.qlib_signal_backtest import compute_portfolio_metrics, portfolio_returns
from quant_lab.us_stock_selection.utils import nav_from_returns
from quant_lab.us_stock_selection.v8_1_gate_metrics import summarize_gate_metrics


HIGH_BETA_TICKERS = {"TQQQ", "QLD", "SOXL", "MSTR"}


def score_weight_grid(base_metrics: dict[str, Any]) -> pd.DataFrame:
    """Simulate final scoring under different concentration penalty weights."""
    rows: list[dict[str, Any]] = []
    base_cagr = float(base_metrics.get("paper_cagr", base_metrics.get("cagr", 0.0)))
    base_calmar = float(base_metrics.get("paper_calmar", base_metrics.get("calmar", 0.0)))
    penalty = float(base_metrics.get("concentration_penalty_score", 0.0))
    for penalty_weight in [0.00, 0.10, 0.20, 0.30, 0.40, 0.50]:
        score = 0.55 * base_calmar + 0.25 * base_cagr - penalty_weight * penalty
        rows.append(
            {
                "candidate_id": "v8_baseline_score_only",
                "penalty_weight": penalty_weight,
                "cagr": base_cagr,
                "calmar": base_calmar,
                "concentration_penalty_score": penalty,
                "gate_aware_score": score,
                "ranking_effect": "baseline unchanged; score-layer diagnostic only",
            }
        )
    return pd.DataFrame(rows)


def build_weights_from_holdings(close: pd.DataFrame, holdings: pd.DataFrame) -> pd.DataFrame:
    """Rebuild daily weights from v8 monthly_holdings without changing decisions."""
    if holdings.empty:
        return pd.DataFrame(index=close.index, columns=close.columns).fillna(0.0)
    local = holdings.copy()
    local["execution_date"] = pd.to_datetime(local["execution_date"], errors="coerce")
    local["ticker"] = local["ticker"].astype(str).str.upper()
    local["weight"] = pd.to_numeric(local["weight"], errors="coerce").fillna(0.0)
    weights = pd.DataFrame(np.nan, index=close.index, columns=close.columns, dtype=float)
    for execution_date, group in local.dropna(subset=["execution_date"]).groupby("execution_date"):
        if execution_date not in weights.index:
            pos = weights.index.searchsorted(execution_date)
            if pos >= len(weights.index):
                continue
            execution_date = weights.index[pos]
        row = pd.Series(0.0, index=weights.columns)
        for item in group.itertuples():
            if item.ticker in row.index:
                row.loc[item.ticker] = float(item.weight)
        weights.loc[execution_date] = row
    return weights.ffill().fillna(0.0)


def apply_high_beta_softcap(weights: pd.DataFrame, cap: float = 0.15, max_other_weight: float = 0.30) -> pd.DataFrame:
    """Cap each high-beta ticker and redistribute released weight to other active holdings."""
    out = weights.copy().astype(float)
    high_beta_cols = [c for c in out.columns if str(c).upper() in HIGH_BETA_TICKERS]
    if not high_beta_cols:
        return out
    for idx in out.index:
        row = out.loc[idx].copy()
        active = row[row > 1e-12]
        if active.empty:
            continue
        before_sum = float(active.sum())
        for ticker in high_beta_cols:
            if row.get(ticker, 0.0) > cap:
                row.loc[ticker] = cap
        released = before_sum - float(row[row > 1e-12].sum())
        receivers = [c for c in active.index if c not in high_beta_cols and row.get(c, 0.0) < max_other_weight]
        while released > 1e-12 and receivers:
            room = pd.Series({c: max_other_weight - row.loc[c] for c in receivers})
            total_room = float(room.clip(lower=0.0).sum())
            if total_room <= 1e-12:
                break
            add = room / total_room * min(released, total_room)
            for c, value in add.items():
                row.loc[c] += float(value)
            released -= float(add.sum())
            receivers = [c for c in receivers if row.get(c, 0.0) < max_other_weight - 1e-12]
        out.loc[idx] = row
    return out.fillna(0.0)


def evaluate_replay_variant(
    variant_id: str,
    close: pd.DataFrame,
    weights: pd.DataFrame,
    start: str,
    end: str,
    cost_bps: float = 5.0,
    slippage_bps: float = 5.0,
) -> dict[str, Any]:
    """Evaluate a prebuilt weight overlay over a limited sample window."""
    local_close = close.loc[(close.index >= pd.Timestamp(start)) & (close.index <= pd.Timestamp(end)), weights.columns].ffill()
    local_weights = weights.reindex(local_close.index).ffill().fillna(0.0)
    returns, turnover = portfolio_returns(local_close, local_weights, cost_bps=cost_bps, slippage_bps=slippage_bps)
    metrics = compute_portfolio_metrics(returns, turnover, local_weights)
    contrib = ticker_contributions(local_close, local_weights)
    ticker_abs_share = float(contrib["abs_share"].max()) if not contrib.empty and "abs_share" in contrib else 0.0
    max_month_weight = float(local_weights.max().max()) if not local_weights.empty else 0.0
    high_beta_weight_share = float(local_weights[[c for c in local_weights.columns if c in HIGH_BETA_TICKERS]].sum(axis=1).mean()) if any(c in HIGH_BETA_TICKERS for c in local_weights.columns) else 0.0
    daily = pd.DataFrame({"date": returns.index, "return": returns.values, "nav": nav_from_returns(returns).values, "turnover": turnover.values})
    gate_metrics = summarize_gate_metrics(
        daily,
        ticker_abs_share=ticker_abs_share,
        max_ticker_month_weight=max_month_weight,
        dominant_year_unique_ticker_count=float((local_weights.max(axis=0) > 0).sum()),
        dominant_year_avg_holding_count=float((local_weights > 1e-12).sum(axis=1).mean()),
        high_beta_weight_share=high_beta_weight_share,
    )
    cost50_returns, cost50_turnover = portfolio_returns(local_close, local_weights, cost_bps=50.0, slippage_bps=5.0)
    cost50 = compute_portfolio_metrics(cost50_returns, cost50_turnover, local_weights)
    return {
        "variant_id": variant_id,
        "start": start,
        "end": end,
        **metrics,
        "cost50_cagr": cost50.get("cagr"),
        "cost50_calmar": cost50.get("calmar"),
        **gate_metrics,
        "daily_nav": daily,
        "ticker_contribution": contrib,
    }
