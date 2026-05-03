"""Overfit diagnostics for v4 Qlib-style portfolio research."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from quant_lab.us_stock_selection.utils import ensure_dir, save_dataframe


def run_qlib_overfit_checks(
    signal_quality: pd.DataFrame,
    strategy_results: pd.DataFrame,
    portfolio_daily: pd.DataFrame,
    holdings: pd.DataFrame,
    out_dir: Path | str,
) -> dict[str, pd.DataFrame]:
    """Check IC decay, year concentration, turnover, and holdings concentration."""
    out_path = ensure_dir(out_dir)
    summary_rows: list[dict[str, Any]] = []
    yearly = yearly_return_contribution(portfolio_daily)
    concentration = holding_concentration(holdings)

    for _, row in strategy_results.head(50).iterrows() if not strategy_results.empty else []:
        strategy_id = row.get("strategy_id", "")
        run_id = row.get("run_id", "")
        quality = signal_quality.loc[signal_quality.get("run_id", pd.Series(dtype=str)) == run_id].head(1) if not signal_quality.empty else pd.DataFrame()
        train_rank_ic = float(quality["train_rank_ic_mean"].iloc[0]) if not quality.empty and "train_rank_ic_mean" in quality else 0.0
        test_rank_ic = float(quality["test_rank_ic_mean"].iloc[0]) if not quality.empty and "test_rank_ic_mean" in quality else 0.0
        max_year_share = yearly.loc[yearly["strategy_id"] == strategy_id, "abs_return_contribution_share"].max() if not yearly.empty else 0.0
        conc = concentration.loc[concentration["strategy_id"] == strategy_id].head(1)
        max_ticker_weight = float(conc["max_average_ticker_weight"].iloc[0]) if not conc.empty else 0.0
        max_ticker = str(conc["max_average_ticker"].iloc[0]) if not conc.empty and "max_average_ticker" in conc else ""
        nvda_tqqq_weight = float(conc["nvda_tqqq_average_weight"].iloc[0]) if not conc.empty else 0.0
        high_turnover = float(row.get("annual_turnover", 0.0)) > 24.0
        ic_decay = train_rank_ic > 0 and test_rank_ic < train_rank_ic * 0.25
        single_year_risk = bool(pd.notna(max_year_share) and float(max_year_share) > 0.65)
        concentration_risk = max_ticker_weight > 0.65 or nvda_tqqq_weight > 0.65
        overfit_score = 0
        overfit_score += 25 if ic_decay else 0
        overfit_score += 20 if single_year_risk else 0
        overfit_score += 20 if high_turnover else 0
        overfit_score += 20 if concentration_risk else 0
        overfit_score += 15 if int(row.get("daily_count", 0)) < 252 else 0
        summary_rows.append(
            {
                "strategy_id": strategy_id,
                "run_id": run_id,
                "train_rank_ic_mean": train_rank_ic,
                "test_rank_ic_mean": test_rank_ic,
                "ic_decay_risk": bool(ic_decay),
                "single_year_contribution_risk": bool(single_year_risk),
                "turnover_risk": bool(high_turnover),
                "holding_concentration_risk": bool(concentration_risk),
                "max_abs_year_contribution_share": float(max_year_share) if pd.notna(max_year_share) else 0.0,
                "max_average_ticker": max_ticker,
                "max_average_ticker_weight": max_ticker_weight,
                "nvda_tqqq_average_weight": nvda_tqqq_weight,
                "overfit_penalty": float(overfit_score),
                "overfit_label": "overfit_suspect" if overfit_score >= 40 else "watch" if overfit_score >= 20 else "acceptable",
            }
        )
    summary = pd.DataFrame(summary_rows)
    save_dataframe(summary, out_path / "overfit_check_summary.csv")
    save_dataframe(yearly, out_path / "yearly_return_contribution.csv")
    save_dataframe(concentration, out_path / "holding_concentration.csv")
    return {"summary": summary, "yearly": yearly, "concentration": concentration}


def yearly_return_contribution(portfolio_daily: pd.DataFrame) -> pd.DataFrame:
    if portfolio_daily.empty:
        return pd.DataFrame()
    daily = portfolio_daily.copy()
    daily["date"] = pd.to_datetime(daily["date"])
    daily["year"] = daily["date"].dt.year
    annual = (
        daily.groupby(["strategy_id", "year"])["return"]
        .apply(lambda s: float((1.0 + s).prod() - 1.0))
        .reset_index(name="year_return")
    )
    annual["abs_year_return"] = annual["year_return"].abs()
    total_abs = annual.groupby("strategy_id")["abs_year_return"].transform("sum").replace(0.0, np.nan)
    annual["abs_return_contribution_share"] = annual["abs_year_return"].div(total_abs).fillna(0.0)
    return annual


def holding_concentration(holdings: pd.DataFrame) -> pd.DataFrame:
    if holdings.empty:
        return pd.DataFrame()
    hold = holdings.copy()
    hold["weight"] = hold["weight"].astype(float)
    avg = hold.groupby(["strategy_id", "ticker"])["weight"].mean().reset_index()
    rows = []
    for strategy_id, group in avg.groupby("strategy_id"):
        weights = group.set_index("ticker")["weight"].clip(lower=0.0)
        hhi = float((weights**2).sum())
        rows.append(
            {
                "strategy_id": strategy_id,
                "max_average_ticker": weights.idxmax() if not weights.empty else "",
                "max_average_ticker_weight": float(weights.max()) if not weights.empty else 0.0,
                "holding_hhi": hhi,
                "nvda_tqqq_average_weight": float(weights.reindex(["NVDA", "TQQQ"]).fillna(0.0).sum()),
                "ticker_count_with_weight": int((weights > 0).sum()),
            }
        )
    return pd.DataFrame(rows)
