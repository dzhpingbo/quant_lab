"""Run v8.1 cycle 03 full-period overlay replay.

This script only replays existing v8 holdings with deterministic weight
overlays. It does not train models, alter v8 selection signals, enter v9, or
expand the universe.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from quant_lab.us_stock_selection.local_qlib_provider_builder import default_local_provider_uri
from quant_lab.us_stock_selection.portfolio_robustifier import ticker_contributions
from quant_lab.us_stock_selection.qlib_signal_backtest import compute_portfolio_metrics, portfolio_returns
from quant_lab.us_stock_selection.qlib_workflow_runner import load_close_from_provider
from quant_lab.us_stock_selection.utils import nav_from_returns
from quant_lab.us_stock_selection.v8_1_gate_aware import (
    HIGH_BETA_TICKERS,
    apply_high_beta_softcap,
    build_weights_from_holdings,
)
from quant_lab.us_stock_selection.v8_1_gate_metrics import (
    annual_table_from_daily,
    concentration_penalty_score,
    gate_results_from_metrics,
    leave_one_year_out_metrics,
    monthly_table_from_daily,
    rolling_12m_metrics,
    top_month_removed_metrics,
)
from quant_lab.us_stock_selection.v8_1_reporting import table_to_markdown, write_json


DEFAULT_RUN_DIR = PROJECT_ROOT / "outputs" / "us_stock_selection" / "run_20260426_095958"
OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "us_stock_selection"
DOCS_DIR = PROJECT_ROOT / "docs"

BASELINE_CAGR = 0.6538182307494054
BASELINE_CALMAR = 1.99152684432784
BASELINE_MAXDD = -0.32829998380969627
BASELINE_COST50_CAGR = 0.5608428724606129
BASELINE_VERDICT = "credible_but_execution_sensitive"
BASELINE_ALLOW_ENTER_V9 = False
CALMAR_85PCT_THRESHOLD = BASELINE_CALMAR * 0.85

OVERLAY_SEMANTICS = {
    "high_beta_tickers": sorted(HIGH_BETA_TICKERS),
    "cap_type": "single_ticker_cap_for_each_high_beta_name",
    "redistribution": "released_weight_goes_to_non_high_beta_active_holdings_up_to_max_other_weight_0.30",
    "cash_residual": "possible_only_if_non_high_beta_receivers_have_insufficient_room",
    "target_gross_exposure": "kept_at_1.0_when_receiver_room_is_available",
    "signal_impact": "does_not_change_v8_selection_signal_or_model_predictions",
    "turnover_impact": "can_change_weight_deltas_at_existing_v8_execution_dates_only",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run v8.1 cycle 03 full-period overlay replay.")
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument("--provider-uri", type=Path, default=default_local_provider_uri())
    parser.add_argument(
        "--candidate-list",
        default="baseline_no_overlay,high_beta_softcap_10,high_beta_softcap_15,high_beta_softcap_20",
        help="Comma-separated candidates. Supported: baseline_no_overlay, high_beta_softcap_10/15/20.",
    )
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--timestamp", default=None)
    parser.add_argument("--cost-bps", type=float, default=5.0)
    parser.add_argument("--slippage-bps", type=float, default=5.0)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def setup_logger(out_dir: Path) -> logging.Logger:
    log_dir = out_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("v8_1_cycle03")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    fh = logging.FileHandler(log_dir / "run.log", encoding="utf-8")
    sh = logging.StreamHandler()
    fh.setFormatter(fmt)
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def read_csv(path: Path, required: bool = True) -> pd.DataFrame:
    if not path.exists():
        if required:
            raise FileNotFoundError(path)
        return pd.DataFrame()
    return pd.read_csv(path)


def ensure_inputs(run_dir: Path) -> list[Path]:
    required = [
        run_dir / "v8_verdict.json",
        run_dir / "v8_paper_trading" / "daily_nav.csv",
        run_dir / "v8_paper_trading" / "monthly_holdings.csv",
        run_dir / "v8_paper_trading" / "trades.csv",
        run_dir / "v8_paper_trading" / "monthly_decision_ledger.csv",
        run_dir / "v8_paper_trading" / "paper_trading_metrics.csv",
    ]
    missing = [p for p in required if not p.exists()]
    if missing:
        raise FileNotFoundError("Missing required v8 artifact(s): " + "; ".join(str(p) for p in missing))
    return required


def parse_candidates(raw: str) -> list[str]:
    candidates = [item.strip() for item in raw.split(",") if item.strip()]
    if not candidates:
        raise ValueError("--candidate-list resolved to no candidates")
    supported = {"baseline_no_overlay", "high_beta_softcap_10", "high_beta_softcap_15", "high_beta_softcap_20"}
    unknown = [c for c in candidates if c not in supported]
    if unknown:
        raise ValueError("Unsupported candidate(s): " + ", ".join(unknown))
    if "baseline_no_overlay" not in candidates:
        candidates.insert(0, "baseline_no_overlay")
    return candidates


def candidate_weights(candidate_id: str, base_weights: pd.DataFrame) -> pd.DataFrame:
    if candidate_id == "baseline_no_overlay":
        return base_weights.copy()
    if candidate_id == "high_beta_softcap_10":
        return apply_high_beta_softcap(base_weights, cap=0.10, max_other_weight=0.30)
    if candidate_id == "high_beta_softcap_15":
        return apply_high_beta_softcap(base_weights, cap=0.15, max_other_weight=0.30)
    if candidate_id == "high_beta_softcap_20":
        return apply_high_beta_softcap(base_weights, cap=0.20, max_other_weight=0.30)
    raise ValueError(candidate_id)


def evaluate_variant(
    candidate_id: str,
    close: pd.DataFrame,
    weights: pd.DataFrame,
    cost_bps: float,
    slippage_bps: float,
) -> dict[str, Any]:
    weights = weights.reindex(close.index).ffill().fillna(0.0).loc[:, close.columns]
    returns, turnover = portfolio_returns(close, weights, cost_bps=cost_bps, slippage_bps=slippage_bps)
    cost50_returns, cost50_turnover = portfolio_returns(close, weights, cost_bps=50.0, slippage_bps=slippage_bps)
    metrics = compute_portfolio_metrics(returns, turnover, weights)
    cost50 = compute_portfolio_metrics(cost50_returns, cost50_turnover, weights)
    nav = nav_from_returns(returns)
    cost50_nav = nav_from_returns(cost50_returns)
    daily = pd.DataFrame(
        {
            "variant_id": candidate_id,
            "date": returns.index,
            "return": returns.values,
            "nav": nav.values,
            "turnover": turnover.reindex(returns.index).values,
            "cost50_return": cost50_returns.reindex(returns.index).values,
            "cost50_nav": cost50_nav.reindex(returns.index).values,
            "cost50_turnover": cost50_turnover.reindex(returns.index).values,
        }
    )
    annual = annual_table_from_daily(daily[["date", "return", "nav", "turnover"]])
    monthly = monthly_table_from_daily(daily[["date", "return", "nav", "turnover"]])
    loo = leave_one_year_out_metrics(daily[["date", "return", "nav", "turnover"]])
    removed = top_month_removed_metrics(daily[["date", "return", "nav", "turnover"]], monthly)
    rolling = rolling_12m_metrics(daily[["date", "return", "nav", "turnover"]])
    contrib = ticker_contributions(close, weights)
    exposure = exposure_summary(candidate_id, weights, contrib, annual)
    monthly_sensitivity = top_month_sensitivity_summary(candidate_id, monthly, removed)
    rolling_summary = rolling_summary_row(candidate_id, rolling)
    ticker_summary = ticker_concentration_summary(candidate_id, weights, contrib, annual)
    gross = weights.abs().sum(axis=1)
    active = gross > 1e-12
    trade_matrix = weights.diff().fillna(weights).abs()
    trade_count = int((trade_matrix > 1e-12).sum().sum())
    high_beta_cols = [c for c in weights.columns if str(c).upper() in HIGH_BETA_TICKERS]
    high_beta_weight = weights[high_beta_cols].sum(axis=1) if high_beta_cols else pd.Series(0.0, index=weights.index)
    gate_metric_row: dict[str, Any] = {
        "current_abs_return_share": float(annual["gate_abs_year_return_share"].max()) if not annual.empty else np.nan,
        "leave_one_year_out_min_cagr": float(loo["cagr"].min()) if not loo.empty else np.nan,
        "leave_one_year_out_min_calmar": float(loo["calmar"].min()) if not loo.empty else np.nan,
        "top1_positive_month_share": monthly_sensitivity["top1_positive_month_share"],
        "top3_positive_month_share": monthly_sensitivity["top3_positive_month_share"],
        "top5_positive_month_share": monthly_sensitivity["top5_positive_month_share"],
        "rolling_12m_min_return": rolling_summary["rolling_12m_min_return"],
        "rolling_12m_min_calmar_like": rolling_summary["rolling_12m_min_calmar_like"],
        "rolling_12m_max_return": rolling_summary["rolling_12m_max_return"],
        "max_ticker_abs_share": ticker_summary["max_ticker_abs_share"],
        "max_ticker_month_weight": ticker_summary["max_ticker_month_weight"],
        "dominant_year_unique_ticker_count": ticker_summary["dominant_year_unique_ticker_count"],
        "dominant_year_avg_holding_count": ticker_summary["dominant_year_avg_holding_count"],
        "high_beta_weight_share": float(high_beta_weight.loc[active].mean()) if active.any() else 0.0,
    }
    gate_metric_row["rolling_12m_return_gap"] = (
        gate_metric_row["rolling_12m_max_return"] - gate_metric_row["rolling_12m_min_return"]
        if pd.notna(gate_metric_row["rolling_12m_max_return"]) and pd.notna(gate_metric_row["rolling_12m_min_return"])
        else np.nan
    )
    penalty, penalty_parts = concentration_penalty_score(gate_metric_row)
    gate_metric_row["concentration_penalty_score"] = penalty
    gate_metric_row.update(penalty_parts)
    full_row = {
        "variant_id": candidate_id,
        **metrics,
        "cost50_cagr": cost50.get("cagr"),
        "cost50_calmar": cost50.get("calmar"),
        "trade_count": trade_count,
        "average_monthly_gross_exposure": exposure["average_monthly_gross_exposure_active"],
        "max_monthly_gross_exposure": exposure["max_monthly_gross_exposure"],
        "average_monthly_net_exposure": exposure["average_monthly_net_exposure_active"],
        "max_monthly_net_exposure": exposure["max_monthly_net_exposure"],
        "average_high_beta_weight_share": exposure["average_high_beta_weight_share_active"],
        "max_high_beta_weight_share": exposure["max_high_beta_weight_share"],
        "gross_exposure_anomaly": exposure["gross_exposure_anomaly"],
        "cash_residual_avg_active": exposure["cash_residual_avg_active"],
        "cash_residual_max": exposure["cash_residual_max"],
        **high_beta_individual_weight_stats(weights),
        **gate_metric_row,
        "weakest_12m_window": rolling_summary["weakest_12m_window"],
        "strongest_12m_window": rolling_summary["strongest_12m_window"],
        "leave_one_year_out_pass_cagr_20": bool(gate_metric_row["leave_one_year_out_min_cagr"] >= 0.20),
        "leave_one_year_out_pass_calmar_1": bool(gate_metric_row["leave_one_year_out_min_calmar"] >= 1.0),
    }
    return {
        "metrics": full_row,
        "daily": daily,
        "monthly": monthly.insert(0, "variant_id", candidate_id) or monthly,
        "annual": annual.insert(0, "variant_id", candidate_id) or annual,
        "loo": loo.insert(0, "variant_id", candidate_id) or loo,
        "removed": removed.insert(0, "variant_id", candidate_id) or removed,
        "rolling": rolling.insert(0, "variant_id", candidate_id) or rolling,
        "ticker_contrib": contrib.insert(0, "variant_id", candidate_id) or contrib,
        "exposure": exposure,
        "top_month_summary": monthly_sensitivity,
        "ticker_summary": ticker_summary,
        "weights": weights,
        "trades": trades_from_weights(candidate_id, weights, close),
    }


def exposure_summary(candidate_id: str, weights: pd.DataFrame, contrib: pd.DataFrame, annual: pd.DataFrame) -> dict[str, Any]:
    gross = weights.abs().sum(axis=1)
    net = weights.sum(axis=1)
    high_beta_cols = [c for c in weights.columns if str(c).upper() in HIGH_BETA_TICKERS]
    high_beta_weight = weights[high_beta_cols].sum(axis=1) if high_beta_cols else pd.Series(0.0, index=weights.index)
    active = gross > 1e-12
    monthly = pd.DataFrame({"gross": gross, "net": net, "high_beta_weight": high_beta_weight}).groupby(weights.index.to_period("M")).agg(
        gross_mean=("gross", "mean"),
        gross_max=("gross", "max"),
        net_mean=("net", "mean"),
        net_max=("net", "max"),
        high_beta_mean=("high_beta_weight", "mean"),
        high_beta_max=("high_beta_weight", "max"),
    )
    active_monthly = monthly.loc[monthly["gross_max"] > 1e-12].copy()
    active_gross = gross.loc[active]
    cash_residual = (1.0 - gross).clip(lower=0.0)
    active_cash_residual = cash_residual.loc[active]
    return {
        "variant_id": candidate_id,
        "average_monthly_gross_exposure_all": float(monthly["gross_mean"].mean()) if not monthly.empty else 0.0,
        "average_monthly_gross_exposure_active": float(active_monthly["gross_mean"].mean()) if not active_monthly.empty else 0.0,
        "max_monthly_gross_exposure": float(monthly["gross_max"].max()) if not monthly.empty else 0.0,
        "average_monthly_net_exposure_all": float(monthly["net_mean"].mean()) if not monthly.empty else 0.0,
        "average_monthly_net_exposure_active": float(active_monthly["net_mean"].mean()) if not active_monthly.empty else 0.0,
        "max_monthly_net_exposure": float(monthly["net_max"].max()) if not monthly.empty else 0.0,
        "average_high_beta_weight_share_all": float(monthly["high_beta_mean"].mean()) if not monthly.empty else 0.0,
        "average_high_beta_weight_share_active": float(high_beta_weight.loc[active].mean()) if active.any() else 0.0,
        "max_high_beta_weight_share": float(high_beta_weight.max()) if not high_beta_weight.empty else 0.0,
        "cash_residual_avg_active": float(active_cash_residual.mean()) if not active_cash_residual.empty else 0.0,
        "cash_residual_max": float(active_cash_residual.max()) if not active_cash_residual.empty else 0.0,
        "cash_residual_max_all_days": float(cash_residual.max()) if not cash_residual.empty else 0.0,
        "inactive_month_count": int((monthly["gross_max"] <= 1e-12).sum()) if not monthly.empty else 0,
        "active_day_min_gross_exposure": float(active_gross.min()) if not active_gross.empty else 0.0,
        "gross_exposure_anomaly": bool((gross.max() > 1.000001) or (not active_gross.empty and active_gross.min() < 0.99) or gross.isna().any()),
        "top_contribution_ticker": str(contrib.iloc[0]["ticker"]) if not contrib.empty else "",
        "dominant_year": int(annual.sort_values("gate_abs_year_return_share", ascending=False).iloc[0]["year"]) if not annual.empty else 0,
    }


def high_beta_individual_weight_stats(weights: pd.DataFrame) -> dict[str, float]:
    out: dict[str, float] = {}
    gross = weights.abs().sum(axis=1)
    active = gross > 1e-12
    for ticker in sorted(HIGH_BETA_TICKERS):
        col = weights[ticker] if ticker in weights.columns else pd.Series(0.0, index=weights.index)
        out[f"{ticker}_avg_weight"] = float(col.loc[active].mean()) if active.any() else 0.0
        out[f"{ticker}_max_weight"] = float(col.max()) if not col.empty else 0.0
    return out


def top_month_sensitivity_summary(candidate_id: str, monthly: pd.DataFrame, removed: pd.DataFrame) -> dict[str, Any]:
    top_pos = monthly.loc[monthly["monthly_profit"] > 0].sort_values("monthly_profit", ascending=False)
    row: dict[str, Any] = {
        "variant_id": candidate_id,
        "top1_positive_month_share": float(top_pos["positive_profit_share"].head(1).sum()) if not top_pos.empty else np.nan,
        "top3_positive_month_share": float(top_pos["positive_profit_share"].head(3).sum()) if not top_pos.empty else np.nan,
        "top5_positive_month_share": float(top_pos["positive_profit_share"].head(5).sum()) if not top_pos.empty else np.nan,
    }
    for n in [1, 3, 5]:
        sub = removed.loc[removed["removed_top_positive_month_count"] == n] if not removed.empty else pd.DataFrame()
        if sub.empty:
            row[f"remove_top{n}_month_cagr"] = np.nan
            row[f"remove_top{n}_month_calmar"] = np.nan
            row[f"remove_top{n}_months"] = ""
        else:
            item = sub.iloc[0]
            row[f"remove_top{n}_month_cagr"] = float(item.get("cagr", np.nan))
            row[f"remove_top{n}_month_calmar"] = float(item.get("calmar", np.nan))
            row[f"remove_top{n}_months"] = str(item.get("removed_months", ""))
    return row


def rolling_summary_row(candidate_id: str, rolling: pd.DataFrame) -> dict[str, Any]:
    if rolling.empty:
        return {
            "variant_id": candidate_id,
            "rolling_12m_min_return": np.nan,
            "rolling_12m_min_calmar_like": np.nan,
            "rolling_12m_max_return": np.nan,
            "rolling_12m_return_gap": np.nan,
            "weakest_12m_window": "",
            "strongest_12m_window": "",
        }
    weakest = rolling.sort_values("window_return", ascending=True).iloc[0]
    strongest = rolling.sort_values("window_return", ascending=False).iloc[0]
    return {
        "variant_id": candidate_id,
        "rolling_12m_min_return": float(rolling["window_return"].min()),
        "rolling_12m_min_calmar_like": float(rolling["calmar_like"].min()),
        "rolling_12m_max_return": float(rolling["window_return"].max()),
        "rolling_12m_return_gap": float(rolling["window_return"].max() - rolling["window_return"].min()),
        "weakest_12m_window": f"{weakest['start_month']}:{weakest['end_month']}",
        "strongest_12m_window": f"{strongest['start_month']}:{strongest['end_month']}",
    }


def ticker_concentration_summary(candidate_id: str, weights: pd.DataFrame, contrib: pd.DataFrame, annual: pd.DataFrame) -> dict[str, Any]:
    max_ticker_abs_share = float(contrib["abs_share"].max()) if not contrib.empty and "abs_share" in contrib else 0.0
    top_ticker = str(contrib.sort_values("abs_share", ascending=False).iloc[0]["ticker"]) if not contrib.empty else ""
    monthly_active = (weights.abs().groupby(weights.index.to_period("M")).max() > 1e-12)
    active_months = monthly_active.any(axis=1)
    top_exposure_count = float(monthly_active.loc[active_months, top_ticker].mean()) if top_ticker in monthly_active.columns and active_months.any() else 0.0
    dominant_year = int(annual.sort_values("gate_abs_year_return_share", ascending=False).iloc[0]["year"]) if not annual.empty else 0
    year_weights = weights.loc[weights.index.year == dominant_year] if dominant_year else weights.iloc[0:0]
    return {
        "variant_id": candidate_id,
        "top_ticker": top_ticker,
        "max_ticker_abs_share": max_ticker_abs_share,
        "max_ticker_month_weight": float(weights.max().max()) if not weights.empty else 0.0,
        "top_ticker_exposure_count_share": top_exposure_count,
        "dominant_year": dominant_year,
        "dominant_year_unique_ticker_count": float((year_weights.max(axis=0) > 1e-12).sum()) if not year_weights.empty else 0.0,
        "dominant_year_avg_holding_count": float((year_weights > 1e-12).sum(axis=1).mean()) if not year_weights.empty else 0.0,
    }


def trades_from_weights(candidate_id: str, weights: pd.DataFrame, close: pd.DataFrame) -> pd.DataFrame:
    delta = weights.diff().fillna(weights)
    rows: list[dict[str, Any]] = []
    for date, row in delta.iterrows():
        changed = row.loc[row.abs() > 1e-12]
        for ticker, delta_weight in changed.items():
            rows.append(
                {
                    "variant_id": candidate_id,
                    "date": pd.Timestamp(date).date().isoformat(),
                    "ticker": ticker,
                    "delta_weight": float(delta_weight),
                    "target_weight": float(weights.loc[date, ticker]),
                    "price": float(close.loc[date, ticker]) if ticker in close.columns and pd.notna(close.loc[date, ticker]) else np.nan,
                }
            )
    return pd.DataFrame(rows)


def holdings_long(candidate_id: str, weights: pd.DataFrame) -> pd.DataFrame:
    out = weights.stack().rename("weight").reset_index()
    out.columns = ["date", "ticker", "weight"]
    out = out.loc[out["weight"].abs() > 1e-12].copy()
    out.insert(0, "variant_id", candidate_id)
    out["date"] = pd.to_datetime(out["date"]).dt.date.astype(str)
    return out


def turnover_summary(candidate_id: str, weights: pd.DataFrame, turnover: pd.Series | None = None) -> dict[str, Any]:
    trade_matrix = weights.diff().fillna(weights).abs()
    gross_turnover = trade_matrix.sum(axis=1)
    nonzero_days = gross_turnover.loc[gross_turnover > 1e-12]
    return {
        "variant_id": candidate_id,
        "trade_day_count": int(len(nonzero_days)),
        "trade_count": int((trade_matrix > 1e-12).sum().sum()),
        "total_turnover": float(gross_turnover.sum()),
        "average_trade_day_turnover": float(nonzero_days.mean()) if not nonzero_days.empty else 0.0,
        "max_daily_turnover": float(gross_turnover.max()) if not gross_turnover.empty else 0.0,
        "annualized_turnover_from_weight_deltas": float(gross_turnover.sum() / max(len(gross_turnover) / 252.0, 1e-9)) if not gross_turnover.empty else 0.0,
    }


def acceptance_table(metrics: pd.DataFrame, baseline_high_beta: float) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for item in metrics.to_dict(orient="records"):
        variant_id = str(item["variant_id"])
        if variant_id == "baseline_no_overlay":
            continue
        checks = {
            "full_period_cagr_ge_20": bool(item.get("cagr", -999) >= 0.20),
            "full_period_cost50_cagr_ge_20": bool(item.get("cost50_cagr", -999) >= 0.20),
            "full_period_calmar_ge_1": bool(item.get("calmar", -999) >= 1.0),
            "full_period_calmar_ge_85pct_v8": bool(item.get("calmar", -999) >= CALMAR_85PCT_THRESHOLD),
            "maxdd_not_significantly_worse_than_v8": bool(abs(item.get("max_drawdown", 999)) <= abs(BASELINE_MAXDD) * 1.05),
            "leave_one_year_out_min_cagr_ge_20": bool(item.get("leave_one_year_out_min_cagr", -999) >= 0.20),
            "leave_one_year_out_min_calmar_ge_1": bool(item.get("leave_one_year_out_min_calmar", -999) >= 1.0),
            "top1_positive_month_share_lte_25": bool(item.get("top1_positive_month_share", 999) <= 0.25),
            "top3_positive_month_share_lte_50": bool(item.get("top3_positive_month_share", 999) <= 0.50),
            "max_ticker_abs_share_lte_30": bool(item.get("max_ticker_abs_share", 999) <= 0.30),
            "max_ticker_month_weight_lte_30": bool(item.get("max_ticker_month_weight", 999) <= 0.30),
            "high_beta_weight_share_meaningfully_down": bool(
                item.get("average_high_beta_weight_share", 999) <= baseline_high_beta * 0.80
                and item.get("average_high_beta_weight_share", 999) <= baseline_high_beta - 0.02
            ),
            "gross_exposure_normal": bool(not item.get("gross_exposure_anomaly", True)),
        }
        accepted = all(checks.values())
        for gate, passed in checks.items():
            rows.append({"variant_id": variant_id, "gate_name": gate, "pass_fail": "pass" if passed else "fail"})
        rows.append({"variant_id": variant_id, "gate_name": "accepted_candidate", "pass_fail": "pass" if accepted else "fail"})
    return pd.DataFrame(rows)


def build_weakest_window_comparison(
    close: pd.DataFrame,
    weights_by_variant: dict[str, pd.DataFrame],
    full_metrics: pd.DataFrame,
    cost_bps: float,
    slippage_bps: float,
) -> pd.DataFrame:
    base = full_metrics.loc[full_metrics["variant_id"] == "baseline_no_overlay"].head(1)
    if base.empty or not str(base.iloc[0].get("weakest_12m_window", "")):
        return pd.DataFrame()
    start_month, end_month = str(base.iloc[0]["weakest_12m_window"]).split(":")
    start = pd.Period(start_month, freq="M").to_timestamp(how="start")
    end = pd.Period(end_month, freq="M").to_timestamp(how="end")
    rows = []
    for variant_id, weights in weights_by_variant.items():
        local_close = close.loc[(close.index >= start) & (close.index <= end), weights.columns]
        local_weights = weights.reindex(local_close.index).ffill().fillna(0.0)
        ret, turnover = portfolio_returns(local_close, local_weights, cost_bps=cost_bps, slippage_bps=slippage_bps)
        cost50_ret, cost50_turnover = portfolio_returns(local_close, local_weights, cost_bps=50.0, slippage_bps=slippage_bps)
        metrics = compute_portfolio_metrics(ret, turnover, local_weights)
        cost50_metrics = compute_portfolio_metrics(cost50_ret, cost50_turnover, local_weights)
        daily = pd.DataFrame({"date": ret.index, "return": ret.values, "nav": nav_from_returns(ret).values, "turnover": turnover.values})
        monthly = monthly_table_from_daily(daily)
        top = top_month_sensitivity_summary(variant_id, monthly, top_month_removed_metrics(daily, monthly))
        high_beta_cols = [c for c in local_weights.columns if str(c).upper() in HIGH_BETA_TICKERS]
        high_beta = local_weights[high_beta_cols].sum(axis=1) if high_beta_cols else pd.Series(0.0, index=local_weights.index)
        loo = leave_one_year_out_metrics(daily)
        rows.append(
            {
                "variant_id": variant_id,
                "window_start": start.date().isoformat(),
                "window_end": end.date().isoformat(),
                "cagr": metrics.get("cagr"),
                "max_drawdown": metrics.get("max_drawdown"),
                "calmar": metrics.get("calmar"),
                "cost50_cagr": cost50_metrics.get("cagr"),
                "cost50_calmar": cost50_metrics.get("calmar"),
                "high_beta_weight_share": float(high_beta.loc[high_beta.index.isin(local_weights.index[local_weights.abs().sum(axis=1) > 1e-12])].mean()) if not high_beta.empty else 0.0,
                "top1_positive_month_share": top["top1_positive_month_share"],
                "top3_positive_month_share": top["top3_positive_month_share"],
                "top5_positive_month_share": top["top5_positive_month_share"],
                "leave_one_year_out_like_min_cagr": float(loo["cagr"].min()) if not loo.empty else np.nan,
                "leave_one_year_out_like_min_calmar": float(loo["calmar"].min()) if not loo.empty else np.nan,
            }
        )
    return pd.DataFrame(rows)


def build_largest_risk(best_row: dict[str, Any], weakest: pd.DataFrame) -> str:
    if not best_row:
        return "no overlay candidate available"
    variant_id = str(best_row.get("variant_id", ""))
    risks: list[str] = []
    if float(best_row.get("cagr", 0.0)) < BASELINE_CAGR:
        risks.append("full-period CAGR is below v8 baseline")
    if float(best_row.get("calmar", 0.0)) < BASELINE_CALMAR:
        risks.append("full-period Calmar is below v8 baseline")
    weak = weakest.loc[weakest["variant_id"] == variant_id].head(1) if not weakest.empty and "variant_id" in weakest.columns else pd.DataFrame()
    if not weak.empty:
        item = weak.iloc[0]
        if float(item.get("calmar", 0.0)) < 1.0:
            risks.append("weakest 12M Calmar remains below 1")
        if float(item.get("cost50_cagr", 0.0)) < 0.20:
            risks.append("weakest 12M 50bps cost CAGR remains below 20%")
        if float(item.get("top3_positive_month_share", 0.0)) > 0.50:
            risks.append("weakest 12M top3 month concentration remains high")
    return "; ".join(risks) if risks else "accepted gates passed, still needs human validation"


def write_reports(
    timestamp: str,
    out_dir: Path,
    candidates: list[str],
    full_metrics: pd.DataFrame,
    exposure_summary_df: pd.DataFrame,
    turnover_summary_df: pd.DataFrame,
    top_month_df: pd.DataFrame,
    rolling_summary_df: pd.DataFrame,
    ticker_concentration_df: pd.DataFrame,
    gate_results: pd.DataFrame,
    weakest: pd.DataFrame,
    verdict: dict[str, Any],
) -> tuple[Path, Path, Path]:
    doc_path = DOCS_DIR / f"US_STOCK_SELECTION_V8_1_EVOLUTION_CYCLE_03_{timestamp}.md"
    exec_path = DOCS_DIR / f"US_STOCK_SELECTION_V8_1_CYCLE_03_EXEC_SUMMARY_{timestamp}.md"
    reports_dir = out_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    local_report = reports_dir / f"US_STOCK_SELECTION_V8_1_EVOLUTION_CYCLE_03_{timestamp}.md"
    best = verdict.get("best_overlay_candidate", {})
    report = f"""# US Stock Selection v8.1 Evolution Cycle 03

## 1. 本轮目标

在完整 v8 区间，对既有 v8 monthly holdings 应用 high-beta soft-cap overlay replay，判断 overlay 是否具备全周期价值。

## 2. 为什么批准 cycle 03

Cycle 02 在 weakest 12M sample 中显示 high_beta_softcap_10 对 CAGR、Calmar、MaxDD 和 high-beta exposure 有局部改善，但 sample 的 top-month concentration 和 leave-one-year-out 仍严重失败。因此本轮只批准更接近完整区间的 overlay replay，不进入 v9。

## 3. overlay 真实实现说明

- High-beta ticker 列表：`{', '.join(sorted(HIGH_BETA_TICKERS))}`
- Soft cap 类型：对每个 high-beta ticker 单独设权重上限，不是 high-beta 总权重 cap。
- 权重处理：超过 cap 的权重释放后，按剩余 room 分配给同日非 high-beta active holdings，单个非 high-beta ticker 上限为 0.30。
- 现金残留：仅当非 high-beta active holdings 没有足够 room 时才可能残留；本轮输出了 cash residual。
- Gross exposure：目标是在 receiver room 足够时保持 active gross exposure = 1。
- Turnover：只会改变已有 v8 execution date 的权重 delta，不新增 rebalance date。
- 是否影响原 v8 选股信号：否。

## 4. 是否重训模型

否。

## 5. 是否改变选股信号

否。

## 6. 是否只是 overlay replay

是。候选为：`{', '.join(candidates)}`。

## 7. full-period 结果

v8 baseline reference: CAGR `{BASELINE_CAGR}`, Calmar `{BASELINE_CALMAR}`, MaxDD `{BASELINE_MAXDD}`, 50bps cost CAGR `{BASELINE_COST50_CAGR}`, verdict `{BASELINE_VERDICT}`, allow_enter_v9 `{BASELINE_ALLOW_ENTER_V9}`.

{table_to_markdown(full_metrics, columns=['variant_id','cagr','cost50_cagr','calmar','cost50_calmar','max_drawdown','annual_turnover','trade_count','average_high_beta_weight_share','max_high_beta_weight_share','concentration_penalty_score'], max_rows=20)}

## 8. weakest 12M 结果

{table_to_markdown(weakest, max_rows=20)}

## 9. concentration gate 结果

{table_to_markdown(gate_results, max_rows=80)}

## 10. execution stress / cost 结果

50bps cost replay 使用 `cost_bps=50.0` 且 slippage 沿用 `{verdict.get('slippage_bps')}` bps。Turnover 摘要：

{table_to_markdown(turnover_summary_df, max_rows=20)}

## 11. 是否接受 candidate

`{verdict.get('accepted_candidate')}`。最优 overlay 观察候选：`{best.get('variant_id', '')}`。

## 12. 是否替代当前 best

`False`。Cycle 03 被要求完成后暂停，不自动替代 v8 baseline。

## 13. 是否允许进入 v9

`False`。

## 14. 后续建议

{verdict.get('next_recommendation')}
"""
    summary = f"""# US Stock Selection v8.1 Cycle 03 Exec Summary

- 最优候选：`{best.get('variant_id', '')}`
- 是否通过 acceptance gates：`{verdict.get('accepted_candidate')}`
- 是否替代 v8 baseline：`False`
- 是否建议进入 v9：`False`
- 最大风险：`{verdict.get('largest_risk')}`
- 建议：`{verdict.get('next_recommendation')}`

## 与 v8 baseline 对比

{table_to_markdown(full_metrics, columns=['variant_id','cagr','cost50_cagr','calmar','max_drawdown','leave_one_year_out_min_cagr','leave_one_year_out_min_calmar','top3_positive_month_share','average_high_beta_weight_share'], max_rows=20)}
"""
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    doc_path.write_text(report, encoding="utf-8")
    local_report.write_text(report, encoding="utf-8")
    exec_path.write_text(summary, encoding="utf-8")
    return doc_path, exec_path, local_report


def write_workbook(path: Path, sheets: dict[str, pd.DataFrame]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path) as writer:
        for name, df in sheets.items():
            safe_name = name[:31]
            df.to_excel(writer, sheet_name=safe_name, index=False)


def update_next_steps(path: Path, timestamp: str, out_dir: Path, zip_path: Path, verdict: dict[str, Any]) -> None:
    old = path.read_text(encoding="utf-8") if path.exists() else "# NEXT_STEPS\n"
    section = f"""

## v8.1 cycle 03 overlay full-period replay

- 执行状态：completed，随后按要求暂停，不自动进入 cycle 04。
- 输出目录：`{out_dir}`
- zip：`{zip_path}`
- 测试候选：`baseline_no_overlay`, `high_beta_softcap_10`, `high_beta_softcap_15`, `high_beta_softcap_20`
- accepted_candidate：`{verdict.get('accepted_candidate')}`
- best_overlay_candidate：`{verdict.get('best_overlay_candidate', {}).get('variant_id', '')}`
- replace_best：`False`
- allow_enter_v9：`False`
- verdict：`{verdict.get('final_cycle_verdict')}`
- 下一步建议：{verdict.get('next_recommendation')}
"""
    path.write_text(old.rstrip() + "\n" + section, encoding="utf-8")


def update_run_summary(path: Path, timestamp: str, out_dir: Path, zip_path: Path, verdict: dict[str, Any]) -> None:
    text = f"""# RUN_SUMMARY

本轮目标：v8.1 cycle 03 high-beta soft-cap overlay full-period replay。

新 run 目录：`{out_dir}`

zip：`{zip_path}`

当前分类：`{verdict.get('final_cycle_verdict')}`

是否允许进入 v9：`False`

是否替代当前 best：`False`

是否重训模型：`False`

是否扩 universe：`False`

最优 overlay 观察候选：`{verdict.get('best_overlay_candidate', {}).get('variant_id', '')}`

accepted_candidate：`{verdict.get('accepted_candidate')}`

后续：cycle 03 已完成并按用户要求暂停，等待用户/ChatGPT 决策。
"""
    path.write_text(text, encoding="utf-8")


def package(zip_path: Path, paths: list[Path]) -> Path:
    zip_path = unique_path(zip_path)
    seen: set[str] = set()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in paths:
            if not path.exists():
                continue
            if path.is_dir():
                for child in path.rglob("*"):
                    if child.is_file():
                        arcname = str(child.resolve().relative_to(PROJECT_ROOT))
                        if arcname in seen:
                            continue
                        seen.add(arcname)
                        zf.write(child, arcname)
            else:
                arcname = str(path.resolve().relative_to(PROJECT_ROOT))
                if arcname in seen:
                    continue
                seen.add(arcname)
                zf.write(path, arcname)
    return zip_path


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    i = 2
    while (path.parent / f"{stem}_{i}{path.suffix}").exists():
        i += 1
    return path.parent / f"{stem}_{i}{path.suffix}"


def safe_json_dict(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, (np.bool_, bool)):
            out[key] = bool(value)
        elif isinstance(value, (np.integer, int)):
            out[key] = int(value)
        elif isinstance(value, (np.floating, float)):
            out[key] = None if math.isnan(float(value)) else float(value)
        else:
            out[key] = value
    return out


def main() -> None:
    args = parse_args()
    timestamp = args.timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = (args.out_dir or OUTPUT_ROOT / f"v8_1_cycle_03_overlay_full_replay_{timestamp}").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    logger = setup_logger(out_dir)
    candidates = parse_candidates(args.candidate_list)
    inputs = ensure_inputs(args.run_dir)
    logger.info("Prepared cycle 03 out_dir=%s candidates=%s", out_dir, candidates)
    logger.info("Overlay semantics: %s", json.dumps(OVERLAY_SEMANTICS, ensure_ascii=False, sort_keys=True))

    if args.dry_run:
        write_json(
            out_dir / "dry_run_status.json",
            {
                "dry_run": True,
                "cycle": "03",
                "out_dir": str(out_dir),
                "checked_inputs": [str(p) for p in inputs],
                "candidate_list": candidates,
                "overlay_semantics": OVERLAY_SEMANTICS,
                "stopped_before": "full_period_replay",
            },
        )
        logger.info("Dry-run completed before replay.")
        print({"dry_run": True, "out_dir": str(out_dir), "candidate_count": len(candidates)})
        return

    daily_v8 = read_csv(args.run_dir / "v8_paper_trading" / "daily_nav.csv")
    holdings = read_csv(args.run_dir / "v8_paper_trading" / "monthly_holdings.csv")
    daily_v8["date"] = pd.to_datetime(daily_v8["date"], errors="coerce")
    v8_index = pd.DatetimeIndex(daily_v8.dropna(subset=["date"])["date"]).sort_values()
    start = pd.Timestamp(v8_index.min()).date().isoformat()
    end = pd.Timestamp(v8_index.max()).date().isoformat()
    tickers = sorted(holdings["ticker"].astype(str).str.upper().unique().tolist())
    logger.info("Loading close panel for %s existing v8 tickers from %s to %s.", len(tickers), start, end)
    close_raw = load_close_from_provider(args.provider_uri, tickers=tickers, start=start, end=end)
    if close_raw.empty:
        raise RuntimeError("Close panel is empty; cannot run cycle 03.")
    close = close_raw.reindex(v8_index).ffill().loc[:, tickers]
    base_weights = build_weights_from_holdings(close, holdings).loc[:, tickers]

    weights_by_variant: dict[str, pd.DataFrame] = {}
    results: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        logger.info("Evaluating candidate=%s", candidate)
        weights = candidate_weights(candidate, base_weights).loc[:, tickers].reindex(close.index).ffill().fillna(0.0)
        weights_by_variant[candidate] = weights
        results[candidate] = evaluate_variant(candidate, close, weights, cost_bps=args.cost_bps, slippage_bps=args.slippage_bps)

    full_metrics = pd.DataFrame([results[c]["metrics"] for c in candidates])
    baseline_high_beta = float(full_metrics.loc[full_metrics["variant_id"] == "baseline_no_overlay", "average_high_beta_weight_share"].iloc[0])
    acceptance = acceptance_table(full_metrics, baseline_high_beta=baseline_high_beta)
    full_metrics["accepted_candidate"] = full_metrics["variant_id"].map(
        lambda vid: bool(
            not acceptance.loc[(acceptance["variant_id"] == vid) & (acceptance["gate_name"] == "accepted_candidate") & (acceptance["pass_fail"] == "fail")].shape[0]
        )
        if vid != "baseline_no_overlay"
        else False
    )
    full_metrics["replace_best"] = False

    daily_nav = pd.concat([results[c]["daily"] for c in candidates], ignore_index=True)
    holdings_long_df = pd.concat([holdings_long(c, results[c]["weights"]) for c in candidates], ignore_index=True)
    trades_df = pd.concat([results[c]["trades"] for c in candidates], ignore_index=True)
    exposure_summary_df = pd.DataFrame([results[c]["exposure"] for c in candidates])
    turnover_summary_df = pd.DataFrame([turnover_summary(c, results[c]["weights"]) for c in candidates])
    monthly_returns = pd.concat([results[c]["monthly"] for c in candidates], ignore_index=True)
    annual_returns = pd.concat([results[c]["annual"] for c in candidates], ignore_index=True)
    loo = pd.concat([results[c]["loo"] for c in candidates], ignore_index=True)
    top_month = pd.DataFrame([results[c]["top_month_summary"] for c in candidates])
    rolling = pd.concat([results[c]["rolling"] for c in candidates], ignore_index=True)
    rolling_summary = pd.DataFrame([rolling_summary_row(c, results[c]["rolling"]) for c in candidates])
    ticker_concentration = pd.DataFrame([results[c]["ticker_summary"] for c in candidates])
    ticker_contrib = pd.concat([results[c]["ticker_contrib"] for c in candidates], ignore_index=True)
    weakest = build_weakest_window_comparison(close, weights_by_variant, full_metrics, cost_bps=args.cost_bps, slippage_bps=args.slippage_bps)

    gate_frames: list[pd.DataFrame] = []
    for row in full_metrics.to_dict(orient="records"):
        gates = gate_results_from_metrics(row)
        gates.insert(0, "variant_id", row["variant_id"])
        gate_frames.append(gates)
    gate_results = pd.concat(gate_frames + [acceptance.assign(gate_layer="acceptance", metric_value="", threshold="")], ignore_index=True)

    full_metrics.to_csv(out_dir / "cycle03_full_period_metrics.csv", index=False)
    daily_nav.to_csv(out_dir / "cycle03_full_period_nav.csv", index=False)
    holdings_long_df.to_csv(out_dir / "cycle03_full_period_holdings.csv", index=False)
    trades_df.to_csv(out_dir / "cycle03_full_period_trades.csv", index=False)
    exposure_summary_df.to_csv(out_dir / "cycle03_overlay_exposure_summary.csv", index=False)
    turnover_summary_df.to_csv(out_dir / "cycle03_overlay_turnover_summary.csv", index=False)
    monthly_returns.to_csv(out_dir / "cycle03_monthly_return_table.csv", index=False)
    annual_returns.to_csv(out_dir / "cycle03_annual_return_table.csv", index=False)
    loo.to_csv(out_dir / "cycle03_leave_one_year_out.csv", index=False)
    top_month.to_csv(out_dir / "cycle03_top_month_sensitivity.csv", index=False)
    rolling.to_csv(out_dir / "cycle03_rolling_12m_metrics.csv", index=False)
    rolling_summary.to_csv(out_dir / "cycle03_rolling_12m_summary.csv", index=False)
    ticker_concentration.to_csv(out_dir / "cycle03_ticker_concentration.csv", index=False)
    ticker_contrib.to_csv(out_dir / "cycle03_ticker_contribution.csv", index=False)
    gate_results.to_csv(out_dir / "cycle03_gate_results.csv", index=False)
    weakest.to_csv(out_dir / "weakest_12m_baseline_vs_overlay.csv", index=False)

    overlay_rows = full_metrics.loc[full_metrics["variant_id"] != "baseline_no_overlay"].copy()
    if not overlay_rows.empty:
        overlay_rows["accepted_rank"] = overlay_rows["accepted_candidate"].astype(int)
        best_row = overlay_rows.sort_values(
            ["accepted_rank", "cost50_calmar", "calmar", "average_high_beta_weight_share"],
            ascending=[False, False, False, True],
        ).iloc[0].to_dict()
    else:
        best_row = {}
    accepted_any = bool(full_metrics.loc[full_metrics["variant_id"] != "baseline_no_overlay", "accepted_candidate"].any())
    largest_risk = build_largest_risk(best_row, weakest)
    verdict = {
        "cycle_id": "03",
        "cycle_type": "full_period_overlay_replay_existing_v8_holdings",
        "run_dir": str(args.run_dir),
        "candidate_list": candidates,
        "overlay_semantics": OVERLAY_SEMANTICS,
        "model_retrained": False,
        "selection_signal_changed": False,
        "overlay_replay_only": True,
        "expanded_universe": False,
        "entered_v9": False,
        "ran_31b": False,
        "baseline_v8_verdict": read_json(args.run_dir / "v8_verdict.json"),
        "baseline_reference_metrics": {
            "cagr": BASELINE_CAGR,
            "calmar": BASELINE_CALMAR,
            "max_drawdown": BASELINE_MAXDD,
            "cost50_cagr": BASELINE_COST50_CAGR,
            "classification": BASELINE_VERDICT,
            "allow_enter_v9": BASELINE_ALLOW_ENTER_V9,
        },
        "accepted_candidate": accepted_any,
        "replace_best": False,
        "allow_enter_v9": False,
        "best_overlay_candidate": safe_json_dict(best_row),
        "largest_risk": largest_risk,
        "slippage_bps": args.slippage_bps,
        "cost_bps": args.cost_bps,
        "execution_stress_summary": "Full-period replay evaluated primary cost plus 50bps cost stress without retraining or changing signals.",
        "pause_triggered": True,
        "pause_reason": "Cycle 03 completed; user explicitly required pausing before cycle 04 or any best-strategy decision.",
        "final_cycle_verdict": "accepted_candidate_needs_human_review" if accepted_any else "diagnostic_only_or_rejected_needs_human_review",
        "next_recommendation": "暂停并由用户/ChatGPT 决定是否做 v8.1 final validation；不要进入 v9，不扩 universe。",
    }
    write_json(out_dir / "cycle03_verdict.json", verdict)
    write_json(out_dir / "cycle_verdict.json", verdict)
    write_json(
        out_dir / "best_candidate_index.json",
        {
            "best_candidate_id": "v8_baseline",
            "best_source": str(args.run_dir),
            "last_cycle_id": "03",
            "last_cycle_status": verdict["final_cycle_verdict"],
            "best_overlay_candidate": safe_json_dict(best_row),
            "accepted_candidate": accepted_any,
            "replace_best": False,
            "allow_enter_v9": False,
        },
    )

    doc_path, exec_path, local_report = write_reports(
        timestamp,
        out_dir,
        candidates,
        full_metrics,
        exposure_summary_df,
        turnover_summary_df,
        top_month,
        rolling_summary,
        ticker_concentration,
        gate_results,
        weakest,
        verdict,
    )
    write_workbook(
        out_dir / "reports" / "cycle03_overlay_full_replay.xlsx",
        {
            "full_metrics": full_metrics,
            "weakest_12m": weakest,
            "gates": gate_results,
            "exposure": exposure_summary_df,
            "turnover": turnover_summary_df,
            "top_month": top_month,
            "rolling_summary": rolling_summary,
            "ticker_conc": ticker_concentration,
            "loo": loo,
        },
    )
    zip_target = unique_path(OUTPUT_ROOT / f"us_stock_selection_quant_lab_v8_1_cycle03_overlay_full_replay_{timestamp}.zip")
    update_next_steps(PROJECT_ROOT / "NEXT_STEPS.md", timestamp, out_dir, zip_target, verdict)
    update_run_summary(PROJECT_ROOT / "RUN_SUMMARY.md", timestamp, out_dir, zip_target, verdict)
    zip_path = package(
        zip_target,
        [
            PROJECT_ROOT / "scripts" / "us_stock_selection" / "35_run_v8_1_cycle03_overlay_full_replay.py",
            PROJECT_ROOT / "quant_lab" / "us_stock_selection" / "v8_1_gate_aware.py",
            PROJECT_ROOT / "quant_lab" / "us_stock_selection" / "v8_1_gate_metrics.py",
            PROJECT_ROOT / "quant_lab" / "us_stock_selection" / "v8_1_reporting.py",
            out_dir,
            doc_path,
            exec_path,
            local_report,
            PROJECT_ROOT / "NEXT_STEPS.md",
            PROJECT_ROOT / "RUN_SUMMARY.md",
        ],
    )
    logger.info("Cycle 03 packaged: %s", zip_path)
    print({"out_dir": str(out_dir), "zip_path": str(zip_path), "verdict": verdict["final_cycle_verdict"]})


if __name__ == "__main__":
    main()
