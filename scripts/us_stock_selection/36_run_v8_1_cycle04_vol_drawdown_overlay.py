"""Run v8.1 cycle 04 ex-ante volatility/drawdown throttle overlays.

This script replays deterministic overlays on top of existing v8 holdings. It
does not retrain models, alter selection signals, run 31b, enter v9, or expand
the universe.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import re
import sys
import zipfile
from dataclasses import dataclass
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
ACCEPT_CALMAR_FLOOR = BASELINE_CALMAR * 0.80
ACCEPT_COST50_CAGR_FLOOR = BASELINE_COST50_CAGR * 0.80
STRONG_CALMAR_FLOOR = BASELINE_CALMAR * 0.90

DEFAULT_CANDIDATES = ",".join(
    [
        "baseline_no_overlay",
        "high_beta_softcap_15",
        "vol_throttle_nav_63d_25",
        "vol_throttle_nav_63d_30",
        "vol_throttle_nav_63d_35",
        "vol_throttle_nav_63d_40",
        "drawdown_throttle_nav",
        "softcap_15_plus_vol_throttle_30",
        "softcap_15_plus_drawdown_throttle",
        "softcap_15_plus_vol_and_drawdown_30",
    ]
)


@dataclass(frozen=True)
class CandidateSpec:
    candidate_id: str
    softcap_15: bool = False
    vol_target: float | None = None
    drawdown_throttle: bool = False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run v8.1 cycle 04 ex-ante vol/drawdown overlays.")
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument("--provider-uri", type=Path, default=default_local_provider_uri())
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--timestamp", default=None)
    parser.add_argument("--cost-bps", type=float, default=5.0)
    parser.add_argument("--slippage-bps", type=float, default=5.0)
    parser.add_argument("--candidate-list", default=DEFAULT_CANDIDATES)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def setup_logger(out_dir: Path) -> logging.Logger:
    log_dir = out_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("v8_1_cycle04")
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
    missing = [path for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing required v8 artifact(s): " + "; ".join(str(p) for p in missing))
    return required


def parse_candidate_list(raw: str) -> list[CandidateSpec]:
    ids = [item.strip() for item in raw.split(",") if item.strip()]
    if not ids:
        raise ValueError("--candidate-list resolved to no candidates")
    if "baseline_no_overlay" not in ids:
        ids.insert(0, "baseline_no_overlay")
    specs: list[CandidateSpec] = []
    for candidate_id in ids:
        specs.append(parse_candidate(candidate_id))
    return specs


def parse_candidate(candidate_id: str) -> CandidateSpec:
    if candidate_id == "baseline_no_overlay":
        return CandidateSpec(candidate_id)
    if candidate_id == "high_beta_softcap_15":
        return CandidateSpec(candidate_id, softcap_15=True)
    if candidate_id == "drawdown_throttle_nav":
        return CandidateSpec(candidate_id, drawdown_throttle=True)
    if candidate_id == "softcap_15_plus_drawdown_throttle":
        return CandidateSpec(candidate_id, softcap_15=True, drawdown_throttle=True)
    vol_match = re.fullmatch(r"vol_throttle_nav_63d_(25|30|35|40)", candidate_id)
    if vol_match:
        return CandidateSpec(candidate_id, vol_target=float(vol_match.group(1)) / 100.0)
    combo_match = re.fullmatch(r"softcap_15_plus_vol_throttle_(25|30|35|40)", candidate_id)
    if combo_match:
        return CandidateSpec(candidate_id, softcap_15=True, vol_target=float(combo_match.group(1)) / 100.0)
    combo_both = re.fullmatch(r"softcap_15_plus_vol_and_drawdown_(25|30|35|40)", candidate_id)
    if combo_both:
        return CandidateSpec(
            candidate_id,
            softcap_15=True,
            vol_target=float(combo_both.group(1)) / 100.0,
            drawdown_throttle=True,
        )
    raise ValueError(f"Unsupported cycle04 candidate: {candidate_id}")


def normalize_daily_nav(daily: pd.DataFrame) -> pd.DataFrame:
    out = daily.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out["return"] = pd.to_numeric(out.get("return", 0.0), errors="coerce").fillna(0.0)
    if "nav" not in out:
        out["nav"] = nav_from_returns(out.set_index("date")["return"]).values
    out["nav"] = pd.to_numeric(out["nav"], errors="coerce")
    out["turnover"] = pd.to_numeric(out.get("turnover", 0.0), errors="coerce").fillna(0.0)
    return out.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)


def build_signal_frame(daily_v8: pd.DataFrame) -> pd.DataFrame:
    daily = normalize_daily_nav(daily_v8)
    returns = daily.set_index("date")["return"].astype(float)
    nav = daily.set_index("date")["nav"].astype(float)
    trailing_vol = returns.rolling(63, min_periods=20).std(ddof=0).shift(1) * np.sqrt(252)
    prior_nav = nav.shift(1)
    prior_peak = nav.cummax().shift(1)
    trailing_dd = prior_nav / prior_peak - 1.0
    signal = pd.DataFrame(
        {
            "date": returns.index,
            "signal_return_lag1_source": returns.shift(1).values,
            "trailing_vol_63d_lag1": trailing_vol.values,
            "trailing_drawdown_lag1": trailing_dd.fillna(0.0).values,
        }
    ).set_index("date")
    signal["scale_drawdown"] = drawdown_scale(signal["trailing_drawdown_lag1"])
    for target in [0.25, 0.30, 0.35, 0.40]:
        signal[f"scale_vol_{int(target * 100)}"] = vol_scale(signal["trailing_vol_63d_lag1"], target)
    return signal


def vol_scale(trailing_vol: pd.Series, target_vol: float) -> pd.Series:
    clean = pd.to_numeric(trailing_vol, errors="coerce")
    scale = (target_vol / clean.replace(0.0, np.nan)).clip(lower=0.0, upper=1.0)
    return scale.fillna(1.0)


def drawdown_scale(trailing_drawdown: pd.Series) -> pd.Series:
    dd = pd.to_numeric(trailing_drawdown, errors="coerce").fillna(0.0)
    scale = pd.Series(1.0, index=dd.index)
    scale.loc[dd <= -0.10] = 0.75
    scale.loc[dd <= -0.15] = 0.50
    scale.loc[dd <= -0.20] = 0.25
    return scale


def candidate_scale(spec: CandidateSpec, signal: pd.DataFrame) -> pd.Series:
    scale = pd.Series(1.0, index=signal.index)
    if spec.vol_target is not None:
        key = f"scale_vol_{int(spec.vol_target * 100)}"
        scale = np.minimum(scale, signal[key])
    if spec.drawdown_throttle:
        scale = np.minimum(scale, signal["scale_drawdown"])
    return pd.Series(scale, index=signal.index).astype(float).clip(lower=0.0, upper=1.0)


def candidate_weights(spec: CandidateSpec, base_weights: pd.DataFrame, signal: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    weights = apply_high_beta_softcap(base_weights, cap=0.15, max_other_weight=0.30) if spec.softcap_15 else base_weights.copy()
    scale = candidate_scale(spec, signal).reindex(weights.index).ffill().fillna(1.0)
    return weights.mul(scale, axis=0).fillna(0.0), scale


def data_availability_check(
    run_dir: Path,
    provider_uri: Path,
    tickers: list[str],
    start: str,
    end: str,
    close: pd.DataFrame | None = None,
) -> dict[str, Any]:
    has_strategy_daily_nav = (run_dir / "v8_paper_trading" / "daily_nav.csv").exists()
    has_ticker_daily_returns = close is not None and not close.empty and len(close.columns) > 0
    market_regime_symbols = ["QQQ", "SPY"]
    market_regime_columns: list[str] = []
    try:
        regime = load_close_from_provider(provider_uri, tickers=market_regime_symbols, start=start, end=end)
        market_regime_columns = [c for c in regime.columns if c in market_regime_symbols]
    except Exception:
        market_regime_columns = []
    chosen = "strategy_daily_nav_lagged_63d_vol_and_lagged_equity_drawdown"
    return {
        "has_strategy_daily_nav": bool(has_strategy_daily_nav),
        "has_ticker_daily_returns": bool(has_ticker_daily_returns),
        "has_market_regime_data": bool(len(market_regime_columns) > 0),
        "market_regime_columns_found": market_regime_columns,
        "chosen_overlay_signal_source": chosen,
        "ticker_return_use": "used_for_replay_and_exposure_metrics_only_not_for_throttle_signal",
        "lookahead_risk_assessment": (
            "low: throttle scale uses v8 strategy returns/nav shifted by one trading day; "
            "no future top month, future drawdown, future realized return, or label is used"
        ),
        "forbidden_overlay_skipped": [],
        "existing_v8_ticker_count": int(len(tickers)),
        "start": start,
        "end": end,
    }


def evaluate_candidate(
    spec: CandidateSpec,
    close: pd.DataFrame,
    weights: pd.DataFrame,
    scale: pd.Series,
    baseline_high_beta: float,
    cost_bps: float,
    slippage_bps: float,
) -> dict[str, Any]:
    weights = weights.reindex(close.index).ffill().fillna(0.0).loc[:, close.columns]
    scale = scale.reindex(close.index).ffill().fillna(1.0)
    returns, turnover = portfolio_returns(close, weights, cost_bps=cost_bps, slippage_bps=slippage_bps)
    cost50_returns, cost50_turnover = portfolio_returns(close, weights, cost_bps=50.0, slippage_bps=slippage_bps)
    metrics = compute_portfolio_metrics(returns, turnover, weights)
    cost50 = compute_portfolio_metrics(cost50_returns, cost50_turnover, weights)
    nav = nav_from_returns(returns)
    cost50_nav = nav_from_returns(cost50_returns)
    daily = pd.DataFrame(
        {
            "candidate": spec.candidate_id,
            "date": returns.index,
            "return": returns.values,
            "nav": nav.values,
            "turnover": turnover.reindex(returns.index).values,
            "cost50_return": cost50_returns.reindex(returns.index).values,
            "cost50_nav": cost50_nav.reindex(returns.index).values,
            "cost50_turnover": cost50_turnover.reindex(returns.index).values,
            "scale": scale.reindex(returns.index).values,
        }
    )
    daily_for_metrics = daily.rename(columns={"candidate": "variant_id"})[["date", "return", "nav", "turnover"]]
    annual = annual_table_from_daily(daily_for_metrics)
    monthly = monthly_table_from_daily(daily_for_metrics)
    loo = leave_one_year_out_metrics(daily_for_metrics)
    removed = top_month_removed_metrics(daily_for_metrics, monthly)
    rolling = rolling_12m_metrics(daily_for_metrics)
    contrib = ticker_contributions(close, weights)
    exposure = exposure_summary(spec.candidate_id, weights, scale, contrib, annual, baseline_high_beta)
    top_month = top_month_sensitivity_summary(spec.candidate_id, monthly, removed)
    rolling_summary = rolling_summary_row(spec.candidate_id, rolling)
    ticker_summary = ticker_summary_row(spec.candidate_id, weights, contrib, baseline_high_beta)
    gate_metric_row = {
        "current_abs_return_share": float(annual["gate_abs_year_return_share"].max()) if not annual.empty else np.nan,
        "leave_one_year_out_min_cagr": float(loo["cagr"].min()) if not loo.empty else np.nan,
        "leave_one_year_out_min_calmar": float(loo["calmar"].min()) if not loo.empty else np.nan,
        "top1_positive_month_share": top_month["top1_positive_month_share"],
        "top3_positive_month_share": top_month["top3_positive_month_share"],
        "top5_positive_month_share": top_month["top5_positive_month_share"],
        "rolling_12m_min_return": rolling_summary["rolling_12m_min_return"],
        "rolling_12m_min_calmar_like": rolling_summary["rolling_12m_min_calmar_like"],
        "rolling_12m_max_return": rolling_summary["rolling_12m_max_return"],
        "max_ticker_abs_share": ticker_summary["max_ticker_abs_share"],
        "max_ticker_month_weight": ticker_summary["max_ticker_month_weight"],
        "dominant_year_unique_ticker_count": dominant_year_unique_ticker_count(weights, annual),
        "dominant_year_avg_holding_count": dominant_year_avg_holding_count(weights, annual),
        "high_beta_weight_share": exposure["avg_high_beta_weight_share"],
    }
    gate_metric_row["rolling_12m_return_gap"] = (
        gate_metric_row["rolling_12m_max_return"] - gate_metric_row["rolling_12m_min_return"]
        if pd.notna(gate_metric_row["rolling_12m_max_return"]) and pd.notna(gate_metric_row["rolling_12m_min_return"])
        else np.nan
    )
    penalty, penalty_parts = concentration_penalty_score(gate_metric_row)
    gate_metric_row["concentration_penalty_score"] = penalty
    gate_metric_row.update(penalty_parts)
    trade_count = int((weights.diff().fillna(weights).abs() > 1e-12).sum().sum())
    row = {
        "candidate": spec.candidate_id,
        "softcap_15": spec.softcap_15,
        "vol_target": spec.vol_target if spec.vol_target is not None else np.nan,
        "drawdown_throttle": spec.drawdown_throttle,
        **metrics,
        "cost50_cagr": cost50.get("cagr"),
        "cost50_calmar": cost50.get("calmar"),
        "trade_count": trade_count,
        **exposure,
        **scale_summary(spec.candidate_id, scale),
        **gate_metric_row,
        "weakest_12m_window": rolling_summary["weakest_12m_window"],
        "strongest_12m_window": rolling_summary["strongest_12m_window"],
        "leave_one_year_out_pass_cagr_20": bool(gate_metric_row["leave_one_year_out_min_cagr"] >= 0.20),
        "leave_one_year_out_pass_calmar_1": bool(gate_metric_row["leave_one_year_out_min_calmar"] >= 1.0),
        "lookahead_free": True,
    }
    monthly = monthly.copy()
    annual = annual.copy()
    loo = loo.copy()
    removed = removed.copy()
    rolling = rolling.copy()
    contrib = contrib.copy()
    for frame in [monthly, annual, loo, removed, rolling, contrib]:
        frame.insert(0, "candidate", spec.candidate_id)
    return {
        "metrics": row,
        "daily": daily,
        "monthly": monthly,
        "annual": annual,
        "loo": loo,
        "removed": removed,
        "rolling": rolling,
        "ticker_contrib": contrib,
        "top_month": top_month,
        "rolling_summary": rolling_summary,
        "ticker_summary": ticker_summary,
        "exposure": exposure,
        "scale_summary": scale_summary(spec.candidate_id, scale),
        "weights": weights,
    }


def exposure_summary(
    candidate: str,
    weights: pd.DataFrame,
    scale: pd.Series,
    contrib: pd.DataFrame,
    annual: pd.DataFrame,
    baseline_high_beta: float,
) -> dict[str, Any]:
    gross = weights.abs().sum(axis=1)
    active = gross > 1e-12
    net = weights.sum(axis=1)
    cash = (1.0 - gross).clip(lower=0.0)
    high_beta_cols = [c for c in weights.columns if str(c).upper() in HIGH_BETA_TICKERS]
    high_beta = weights[high_beta_cols].sum(axis=1) if high_beta_cols else pd.Series(0.0, index=weights.index)
    return {
        "candidate": candidate,
        "avg_gross_exposure": float(gross.mean()) if not gross.empty else 0.0,
        "min_gross_exposure": float(gross.min()) if not gross.empty else 0.0,
        "max_gross_exposure": float(gross.max()) if not gross.empty else 0.0,
        "avg_net_exposure": float(net.mean()) if not net.empty else 0.0,
        "min_net_exposure": float(net.min()) if not net.empty else 0.0,
        "max_net_exposure": float(net.max()) if not net.empty else 0.0,
        "avg_cash_share": float(cash.mean()) if not cash.empty else 0.0,
        "max_cash_share": float(cash.max()) if not cash.empty else 0.0,
        "avg_high_beta_weight_share": float(high_beta.loc[active].mean()) if active.any() else 0.0,
        "max_high_beta_weight_share": float(high_beta.max()) if not high_beta.empty else 0.0,
        "high_beta_weight_reduction_vs_baseline": float(baseline_high_beta - high_beta.loc[active].mean()) if active.any() else baseline_high_beta,
        "gross_exposure_anomaly": bool(gross.isna().any() or (gross.max() > 1.000001) or (gross.min() < -1e-12)),
        "top_contribution_ticker": str(contrib.iloc[0]["ticker"]) if not contrib.empty else "",
        "dominant_year": dominant_year_from_annual(annual),
    }


def scale_summary(candidate: str, scale: pd.Series) -> dict[str, Any]:
    clean = pd.to_numeric(scale, errors="coerce").dropna()
    if clean.empty:
        clean = pd.Series([1.0])
    return {
        "candidate": candidate,
        "avg_scale": float(clean.mean()),
        "min_scale": float(clean.min()),
        "max_scale": float(clean.max()),
        "scale_lt_100_day_count": int((clean < 0.999999).sum()),
        "scale_lte_75_day_count": int((clean <= 0.750001).sum()),
        "scale_lte_50_day_count": int((clean <= 0.500001).sum()),
        "scale_lte_25_day_count": int((clean <= 0.250001).sum()),
    }


def top_month_sensitivity_summary(candidate: str, monthly: pd.DataFrame, removed: pd.DataFrame) -> dict[str, Any]:
    top_pos = monthly.loc[monthly["monthly_profit"] > 0].sort_values("monthly_profit", ascending=False)
    row: dict[str, Any] = {
        "candidate": candidate,
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


def rolling_summary_row(candidate: str, rolling: pd.DataFrame) -> dict[str, Any]:
    if rolling.empty:
        return {
            "candidate": candidate,
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
        "candidate": candidate,
        "rolling_12m_min_return": float(rolling["window_return"].min()),
        "rolling_12m_min_calmar_like": float(rolling["calmar_like"].min()),
        "rolling_12m_max_return": float(rolling["window_return"].max()),
        "rolling_12m_return_gap": float(rolling["window_return"].max() - rolling["window_return"].min()),
        "weakest_12m_window": f"{weakest['start_month']}:{weakest['end_month']}",
        "strongest_12m_window": f"{strongest['start_month']}:{strongest['end_month']}",
    }


def ticker_summary_row(candidate: str, weights: pd.DataFrame, contrib: pd.DataFrame, baseline_high_beta: float) -> dict[str, Any]:
    gross = weights.abs().sum(axis=1)
    active = gross > 1e-12
    high_beta_cols = [c for c in weights.columns if str(c).upper() in HIGH_BETA_TICKERS]
    high_beta = weights[high_beta_cols].sum(axis=1) if high_beta_cols else pd.Series(0.0, index=weights.index)
    return {
        "candidate": candidate,
        "top_ticker": str(contrib.iloc[0]["ticker"]) if not contrib.empty else "",
        "max_ticker_abs_share": float(contrib["abs_share"].max()) if not contrib.empty and "abs_share" in contrib else 0.0,
        "max_ticker_month_weight": float(weights.max().max()) if not weights.empty else 0.0,
        "avg_high_beta_weight_share": float(high_beta.loc[active].mean()) if active.any() else 0.0,
        "max_high_beta_weight_share": float(high_beta.max()) if not high_beta.empty else 0.0,
        "high_beta_weight_reduction_vs_baseline": float(baseline_high_beta - high_beta.loc[active].mean()) if active.any() else baseline_high_beta,
    }


def dominant_year_from_annual(annual: pd.DataFrame) -> int:
    if annual.empty or "gate_abs_year_return_share" not in annual:
        return 0
    return int(annual.sort_values("gate_abs_year_return_share", ascending=False).iloc[0]["year"])


def dominant_year_unique_ticker_count(weights: pd.DataFrame, annual: pd.DataFrame) -> float:
    year = dominant_year_from_annual(annual)
    if not year:
        return 0.0
    local = weights.loc[weights.index.year == year]
    return float((local.max(axis=0) > 1e-12).sum()) if not local.empty else 0.0


def dominant_year_avg_holding_count(weights: pd.DataFrame, annual: pd.DataFrame) -> float:
    year = dominant_year_from_annual(annual)
    if not year:
        return 0.0
    local = weights.loc[weights.index.year == year]
    return float((local > 1e-12).sum(axis=1).mean()) if not local.empty else 0.0


def acceptance_and_strength(
    metrics: pd.DataFrame,
    weakest: pd.DataFrame,
    data_check: dict[str, Any],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    baseline_weak = weakest.loc[weakest["candidate"] == "baseline_no_overlay"].head(1)
    baseline_weak_top3 = float(baseline_weak.iloc[0]["top3_positive_month_share"]) if not baseline_weak.empty else np.nan
    for item in metrics.to_dict(orient="records"):
        candidate = str(item["candidate"])
        if candidate == "baseline_no_overlay":
            continue
        weak = weakest.loc[weakest["candidate"] == candidate].head(1)
        weak_row = weak.iloc[0].to_dict() if not weak.empty else {}
        checks = {
            "full_period_cagr_ge_20": bool(item.get("cagr", -999) >= 0.20),
            "full_period_cost50_cagr_ge_20": bool(item.get("cost50_cagr", -999) >= 0.20),
            "full_period_calmar_ge_1": bool(item.get("calmar", -999) >= 1.0),
            "full_period_calmar_ge_80pct_v8": bool(item.get("calmar", -999) >= ACCEPT_CALMAR_FLOOR),
            "full_period_cost50_cagr_ge_80pct_v8": bool(item.get("cost50_cagr", -999) >= ACCEPT_COST50_CAGR_FLOOR),
            "maxdd_not_significantly_worse_than_v8": bool(abs(item.get("max_drawdown", 999)) <= abs(BASELINE_MAXDD) * 1.05),
            "leave_one_year_out_min_cagr_ge_20": bool(item.get("leave_one_year_out_min_cagr", -999) >= 0.20),
            "leave_one_year_out_min_calmar_ge_1": bool(item.get("leave_one_year_out_min_calmar", -999) >= 1.0),
            "top1_positive_month_share_lte_25": bool(item.get("top1_positive_month_share", 999) <= 0.25),
            "top3_positive_month_share_lte_50": bool(item.get("top3_positive_month_share", 999) <= 0.50),
            "max_ticker_abs_share_lte_30": bool(item.get("max_ticker_abs_share", 999) <= 0.30),
            "max_ticker_month_weight_lte_30": bool(item.get("max_ticker_month_weight", 999) <= 0.30),
            "gross_exposure_normal": bool(not item.get("gross_exposure_anomaly", True)),
            "lookahead_free": bool(data_check.get("lookahead_risk_assessment", "").startswith("low") and item.get("lookahead_free", False)),
        }
        accepted = all(checks.values())
        strong_checks = {
            "accepted_candidate_needs_human_review": accepted,
            "weakest_12m_calmar_ge_1": bool(weak_row.get("calmar", -999) >= 1.0),
            "weakest_12m_cost50_cagr_ge_20": bool(weak_row.get("cost50_cagr", -999) >= 0.20),
            "weakest_12m_top3_share_below_baseline": bool(
                pd.notna(baseline_weak_top3) and weak_row.get("top3_positive_month_share", 999) < baseline_weak_top3
            ),
            "full_period_calmar_ge_90pct_v8": bool(item.get("calmar", -999) >= STRONG_CALMAR_FLOOR),
        }
        strong = all(strong_checks.values())
        for gate, passed in checks.items():
            rows.append({"candidate": candidate, "gate_layer": "acceptance", "gate_name": gate, "pass_fail": "pass" if passed else "fail"})
        rows.append({"candidate": candidate, "gate_layer": "acceptance", "gate_name": "accepted_candidate_needs_human_review", "pass_fail": "pass" if accepted else "fail"})
        for gate, passed in strong_checks.items():
            rows.append({"candidate": candidate, "gate_layer": "strong", "gate_name": gate, "pass_fail": "pass" if passed else "fail"})
        rows.append({"candidate": candidate, "gate_layer": "strong", "gate_name": "strong_candidate", "pass_fail": "pass" if strong else "fail"})
    return pd.DataFrame(rows)


def build_weakest_window_comparison(
    close: pd.DataFrame,
    candidate_weights_map: dict[str, pd.DataFrame],
    candidate_scales: dict[str, pd.Series],
    full_metrics: pd.DataFrame,
    cost_bps: float,
    slippage_bps: float,
) -> pd.DataFrame:
    base = full_metrics.loc[full_metrics["candidate"] == "baseline_no_overlay"].head(1)
    if base.empty or not str(base.iloc[0].get("weakest_12m_window", "")):
        return pd.DataFrame()
    start_month, end_month = str(base.iloc[0]["weakest_12m_window"]).split(":")
    start = pd.Period(start_month, freq="M").to_timestamp(how="start")
    end = pd.Period(end_month, freq="M").to_timestamp(how="end")
    rows: list[dict[str, Any]] = []
    for candidate, weights in candidate_weights_map.items():
        local_close = close.loc[(close.index >= start) & (close.index <= end), weights.columns]
        local_weights = weights.reindex(local_close.index).ffill().fillna(0.0)
        scale = candidate_scales[candidate].reindex(local_close.index).ffill().fillna(1.0)
        returns, turnover = portfolio_returns(local_close, local_weights, cost_bps=cost_bps, slippage_bps=slippage_bps)
        cost50_returns, cost50_turnover = portfolio_returns(local_close, local_weights, cost_bps=50.0, slippage_bps=slippage_bps)
        metrics = compute_portfolio_metrics(returns, turnover, local_weights)
        cost50 = compute_portfolio_metrics(cost50_returns, cost50_turnover, local_weights)
        daily = pd.DataFrame({"date": returns.index, "return": returns.values, "nav": nav_from_returns(returns).values, "turnover": turnover.values})
        monthly = monthly_table_from_daily(daily)
        top_month = top_month_sensitivity_summary(candidate, monthly, top_month_removed_metrics(daily, monthly))
        gross = local_weights.abs().sum(axis=1)
        cash = (1.0 - gross).clip(lower=0.0)
        high_beta_cols = [c for c in local_weights.columns if str(c).upper() in HIGH_BETA_TICKERS]
        high_beta = local_weights[high_beta_cols].sum(axis=1) if high_beta_cols else pd.Series(0.0, index=local_weights.index)
        rows.append(
            {
                "candidate": candidate,
                "window_start": start.date().isoformat(),
                "window_end": end.date().isoformat(),
                "cagr": metrics.get("cagr"),
                "cost50_cagr": cost50.get("cagr"),
                "max_drawdown": metrics.get("max_drawdown"),
                "calmar": metrics.get("calmar"),
                "cost50_calmar": cost50.get("calmar"),
                "top1_positive_month_share": top_month["top1_positive_month_share"],
                "top3_positive_month_share": top_month["top3_positive_month_share"],
                "top5_positive_month_share": top_month["top5_positive_month_share"],
                "avg_scale": float(scale.mean()) if not scale.empty else 1.0,
                "min_scale": float(scale.min()) if not scale.empty else 1.0,
                "avg_cash_share": float(cash.mean()) if not cash.empty else 0.0,
                "avg_high_beta_weight_share": float(high_beta.loc[gross > 1e-12].mean()) if (gross > 1e-12).any() else 0.0,
            }
        )
    return pd.DataFrame(rows)


def add_acceptance_columns(full_metrics: pd.DataFrame, gate_results: pd.DataFrame) -> pd.DataFrame:
    out = full_metrics.copy()
    accepted = set(
        gate_results.loc[
            (gate_results["gate_name"] == "accepted_candidate_needs_human_review") & (gate_results["pass_fail"] == "pass"),
            "candidate",
        ].astype(str)
    )
    strong = set(
        gate_results.loc[(gate_results["gate_name"] == "strong_candidate") & (gate_results["pass_fail"] == "pass"), "candidate"].astype(str)
    )
    out["accepted_candidate_needs_human_review"] = out["candidate"].astype(str).isin(accepted)
    out["strong_candidate"] = out["candidate"].astype(str).isin(strong)
    out["replace_best"] = False
    return out


def choose_best_overlay(full_metrics: pd.DataFrame) -> dict[str, Any]:
    overlay = full_metrics.loc[full_metrics["candidate"] != "baseline_no_overlay"].copy()
    if overlay.empty:
        return {}
    overlay["strong_rank"] = overlay["strong_candidate"].astype(int)
    overlay["accepted_rank"] = overlay["accepted_candidate_needs_human_review"].astype(int)
    overlay["weakness_rank"] = overlay["rolling_12m_min_calmar_like"].fillna(-999)
    row = overlay.sort_values(
        ["strong_rank", "accepted_rank", "weakness_rank", "cost50_calmar", "calmar", "avg_cash_share"],
        ascending=[False, False, False, False, False, True],
    ).iloc[0]
    return safe_json_dict(row.to_dict())


def choose_best_throttle_overlay(full_metrics: pd.DataFrame) -> dict[str, Any]:
    throttle = full_metrics.loc[
        (full_metrics["candidate"] != "baseline_no_overlay") & (full_metrics["candidate"] != "high_beta_softcap_15")
    ].copy()
    if throttle.empty:
        return {}
    throttle["strong_rank"] = throttle["strong_candidate"].astype(int)
    throttle["accepted_rank"] = throttle["accepted_candidate_needs_human_review"].astype(int)
    throttle["weakness_rank"] = throttle["rolling_12m_min_calmar_like"].fillna(-999)
    row = throttle.sort_values(
        ["strong_rank", "accepted_rank", "weakness_rank", "cost50_calmar", "calmar", "avg_cash_share"],
        ascending=[False, False, False, False, False, True],
    ).iloc[0]
    return safe_json_dict(row.to_dict())


def build_largest_risk(best: dict[str, Any], weakest: pd.DataFrame) -> str:
    if not best:
        return "no overlay candidate available"
    candidate = str(best.get("candidate", ""))
    risks: list[str] = []
    if float(best.get("cagr", 0.0)) < BASELINE_CAGR * 0.90:
        risks.append("full-period CAGR materially below v8 baseline")
    if float(best.get("cost50_cagr", 0.0)) < BASELINE_COST50_CAGR * 0.90:
        risks.append("full-period 50bps CAGR materially below v8 baseline")
    weak = weakest.loc[weakest["candidate"] == candidate].head(1) if not weakest.empty else pd.DataFrame()
    if not weak.empty:
        item = weak.iloc[0]
        if float(item.get("calmar", 0.0)) < 1.0:
            risks.append("weakest 12M Calmar remains below 1")
        if float(item.get("cost50_cagr", 0.0)) < 0.20:
            risks.append("weakest 12M 50bps CAGR remains below 20%")
        if float(item.get("top3_positive_month_share", 0.0)) >= float(
            weakest.loc[weakest["candidate"] == "baseline_no_overlay", "top3_positive_month_share"].iloc[0]
        ):
            risks.append("weakest 12M top3 month concentration not improved vs baseline")
    return "; ".join(risks) if risks else "accepted gates passed, still needs human validation"


def write_workbook(path: Path, sheets: dict[str, pd.DataFrame]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path) as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name[:31], index=False)


def write_reports(
    timestamp: str,
    out_dir: Path,
    candidates: list[str],
    data_check: dict[str, Any],
    full_metrics: pd.DataFrame,
    weakest: pd.DataFrame,
    gate_results: pd.DataFrame,
    scale_summary_df: pd.DataFrame,
    verdict: dict[str, Any],
) -> tuple[Path, Path, Path]:
    doc_path = DOCS_DIR / f"US_STOCK_SELECTION_V8_1_EVOLUTION_CYCLE_04_{timestamp}.md"
    exec_path = DOCS_DIR / f"US_STOCK_SELECTION_V8_1_CYCLE_04_EXEC_SUMMARY_{timestamp}.md"
    reports_dir = out_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    local_doc = reports_dir / f"US_STOCK_SELECTION_V8_1_EVOLUTION_CYCLE_04_{timestamp}.md"
    best = verdict.get("best_overlay_candidate", {})
    best_throttle = verdict.get("best_throttle_candidate", {})
    report = f"""# US Stock Selection v8.1 Evolution Cycle 04

## 1. 本轮目标

验证事前可执行的 volatility / drawdown throttle overlay 是否能改善 weakest 12M、回撤、top-month concentration 和成本后稳定性。

## 2. 为什么不直接接受 softcap_15

Cycle 03 的 `high_beta_softcap_15` 通过 full-period gates，但 full-period CAGR/Calmar 低于 v8 baseline，且 weakest 12M 的 Calmar、50bps CAGR 和 top-month concentration 仍不足。因此本轮只做进一步 overlay replay，不替代 best。

## 3. 数据可用性检查

```json
{json.dumps(data_check, indent=2, ensure_ascii=False)}
```

## 4. overlay 是否存在未来函数风险

本轮 throttle scale 只使用 v8 baseline strategy NAV/returns 的 lag-1 信息：63 日 trailing vol 使用 `.shift(1)`，drawdown 使用 prior NAV 与 prior peak。未使用未来 top month、未来 drawdown、未来收益或 label。

## 5. 各候选 full-period 结果

{table_to_markdown(full_metrics, columns=['candidate','cagr','cost50_cagr','calmar','cost50_calmar','max_drawdown','annual_turnover','trade_count','avg_gross_exposure','avg_cash_share','avg_scale','min_scale','avg_high_beta_weight_share','accepted_candidate_needs_human_review','strong_candidate'], max_rows=40)}

## 6. weakest 12M 对比

{table_to_markdown(weakest, max_rows=40)}

## 7. concentration / stability gate

{table_to_markdown(gate_results, max_rows=120)}

## 8. 成本压力结果

50bps cost stress 已对每个候选独立 replay。Scale 摘要：

{table_to_markdown(scale_summary_df, max_rows=40)}

## 9. 是否有 accepted_candidate

`{verdict.get('accepted_candidate')}`

Best overall overlay candidate: `{best.get('candidate', '')}`. Best newly tested throttle candidate: `{best_throttle.get('candidate', '')}`.

## 10. 是否有 strong_candidate

`{verdict.get('strong_candidate')}`

## 11. 是否替代 best

`False`

## 12. 是否允许进入 v9

`False`

## 13. 后续建议

{verdict.get('next_recommendation')}
"""
    summary = f"""# US Stock Selection v8.1 Cycle 04 Exec Summary

- 最优 overlay 候选：`{best.get('candidate', '')}`
- 最优 throttle 候选：`{best_throttle.get('candidate', '')}`
- accepted_candidate_needs_human_review：`{verdict.get('accepted_candidate')}`
- throttle_accepted_candidate：`{verdict.get('throttle_accepted_candidate')}`
- strong_candidate：`{verdict.get('strong_candidate')}`
- 是否替代 v8 baseline：`False`
- 是否允许进入 v9：`False`
- 最大风险：`{verdict.get('largest_risk')}`
- 建议：`{verdict.get('next_recommendation')}`

## Full-Period Snapshot

{table_to_markdown(full_metrics, columns=['candidate','cagr','cost50_cagr','calmar','max_drawdown','rolling_12m_min_calmar_like','top3_positive_month_share','avg_cash_share','accepted_candidate_needs_human_review','strong_candidate'], max_rows=40)}
"""
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    doc_path.write_text(report, encoding="utf-8")
    local_doc.write_text(report, encoding="utf-8")
    exec_path.write_text(summary, encoding="utf-8")
    return doc_path, exec_path, local_doc


def update_next_steps(path: Path, out_dir: Path, zip_path: Path, verdict: dict[str, Any], candidates: list[str]) -> None:
    old = path.read_text(encoding="utf-8") if path.exists() else "# NEXT_STEPS\n"
    section = f"""

## v8.1 cycle 04 vol/drawdown overlay replay

- 执行状态：completed，随后按要求暂停，不自动进入 cycle 05。
- 输出目录：`{out_dir}`
- zip：`{zip_path}`
- 测试候选：`{', '.join(candidates)}`
- accepted_candidate：`{verdict.get('accepted_candidate')}`
- throttle_accepted_candidate：`{verdict.get('throttle_accepted_candidate')}`
- strong_candidate：`{verdict.get('strong_candidate')}`
- best_overlay_candidate：`{verdict.get('best_overlay_candidate', {}).get('candidate', '')}`
- best_throttle_candidate：`{verdict.get('best_throttle_candidate', {}).get('candidate', '')}`
- replace_best：`False`
- allow_enter_v9：`False`
- verdict：`{verdict.get('final_cycle_verdict')}`
- 下一步建议：{verdict.get('next_recommendation')}
"""
    path.write_text(old.rstrip() + "\n" + section, encoding="utf-8")


def update_run_summary(path: Path, out_dir: Path, zip_path: Path, verdict: dict[str, Any]) -> None:
    text = f"""# RUN_SUMMARY

本轮目标：v8.1 cycle 04 ex-ante volatility / drawdown throttle overlay replay。

新 run 目录：`{out_dir}`

zip：`{zip_path}`

当前分类：`{verdict.get('final_cycle_verdict')}`

是否允许进入 v9：`False`

是否替代当前 best：`False`

是否重训模型：`False`

是否扩 universe：`False`

最优 overlay 观察候选：`{verdict.get('best_overlay_candidate', {}).get('candidate', '')}`

最优 throttle 观察候选：`{verdict.get('best_throttle_candidate', {}).get('candidate', '')}`

accepted_candidate：`{verdict.get('accepted_candidate')}`

throttle_accepted_candidate：`{verdict.get('throttle_accepted_candidate')}`

strong_candidate：`{verdict.get('strong_candidate')}`

后续：cycle 04 已完成并按用户要求暂停，等待用户/ChatGPT 决策。
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
    out_dir = (args.out_dir or OUTPUT_ROOT / f"v8_1_cycle_04_vol_drawdown_overlay_{timestamp}").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    logger = setup_logger(out_dir)
    specs = parse_candidate_list(args.candidate_list)
    candidate_ids = [spec.candidate_id for spec in specs]
    inputs = ensure_inputs(args.run_dir)
    logger.info("Prepared cycle 04 out_dir=%s candidates=%s", out_dir, candidate_ids)

    if args.dry_run:
        status = {
            "dry_run": True,
            "cycle": "04",
            "out_dir": str(out_dir),
            "checked_inputs": [str(p) for p in inputs],
            "candidate_list": candidate_ids,
            "stopped_before": "provider_load_and_replay",
        }
        write_json(out_dir / "dry_run_status.json", status)
        logger.info("Dry-run completed before provider load and replay.")
        print({"dry_run": True, "out_dir": str(out_dir), "candidate_count": len(candidate_ids)})
        return

    daily_v8 = normalize_daily_nav(read_csv(args.run_dir / "v8_paper_trading" / "daily_nav.csv"))
    holdings = read_csv(args.run_dir / "v8_paper_trading" / "monthly_holdings.csv")
    v8_index = pd.DatetimeIndex(daily_v8["date"]).sort_values()
    start = pd.Timestamp(v8_index.min()).date().isoformat()
    end = pd.Timestamp(v8_index.max()).date().isoformat()
    tickers = sorted(holdings["ticker"].astype(str).str.upper().unique().tolist())
    logger.info("Loading close panel for %s existing v8 tickers from %s to %s.", len(tickers), start, end)
    close_raw = load_close_from_provider(args.provider_uri, tickers=tickers, start=start, end=end)
    if close_raw.empty:
        raise RuntimeError("Close panel is empty; cannot run cycle 04.")
    close = close_raw.reindex(v8_index).ffill().loc[:, tickers]
    data_check = data_availability_check(args.run_dir, args.provider_uri, tickers, start, end, close=close)
    write_json(out_dir / "cycle04_data_availability_check.json", data_check)

    base_weights = build_weights_from_holdings(close, holdings).loc[:, tickers]
    signal = build_signal_frame(daily_v8).reindex(close.index).ffill().fillna({"trailing_drawdown_lag1": 0.0})
    baseline_hb_cols = [c for c in base_weights.columns if str(c).upper() in HIGH_BETA_TICKERS]
    baseline_gross = base_weights.abs().sum(axis=1)
    baseline_high_beta = float(base_weights[baseline_hb_cols].sum(axis=1).loc[baseline_gross > 1e-12].mean()) if baseline_hb_cols else 0.0

    candidate_weights_map: dict[str, pd.DataFrame] = {}
    candidate_scales: dict[str, pd.Series] = {}
    results: dict[str, dict[str, Any]] = {}
    for spec in specs:
        weights, scale = candidate_weights(spec, base_weights, signal)
        candidate_weights_map[spec.candidate_id] = weights
        candidate_scales[spec.candidate_id] = scale
        logger.info(
            "Candidate %s scale avg=%.6f min=%.6f max=%.6f days_lt_1=%s",
            spec.candidate_id,
            float(scale.mean()),
            float(scale.min()),
            float(scale.max()),
            int((scale < 0.999999).sum()),
        )
        results[spec.candidate_id] = evaluate_candidate(
            spec,
            close,
            weights,
            scale,
            baseline_high_beta=baseline_high_beta,
            cost_bps=args.cost_bps,
            slippage_bps=args.slippage_bps,
        )

    full_metrics = pd.DataFrame([results[c]["metrics"] for c in candidate_ids])
    nav = pd.concat([results[c]["daily"] for c in candidate_ids], ignore_index=True)
    scale_summary_df = pd.DataFrame([results[c]["scale_summary"] for c in candidate_ids])
    exposure_summary_df = pd.DataFrame([results[c]["exposure"] for c in candidate_ids])
    loo = pd.concat([results[c]["loo"] for c in candidate_ids], ignore_index=True)
    top_month = pd.DataFrame([results[c]["top_month"] for c in candidate_ids])
    rolling = pd.concat([results[c]["rolling"] for c in candidate_ids], ignore_index=True)
    ticker_exposure = pd.DataFrame([results[c]["ticker_summary"] for c in candidate_ids])
    monthly = pd.concat([results[c]["monthly"] for c in candidate_ids], ignore_index=True)
    annual = pd.concat([results[c]["annual"] for c in candidate_ids], ignore_index=True)
    ticker_contrib = pd.concat([results[c]["ticker_contrib"] for c in candidate_ids], ignore_index=True)
    weakest = build_weakest_window_comparison(
        close,
        candidate_weights_map,
        candidate_scales,
        full_metrics,
        cost_bps=args.cost_bps,
        slippage_bps=args.slippage_bps,
    )

    gate_frames: list[pd.DataFrame] = []
    for row in full_metrics.to_dict(orient="records"):
        gates = gate_results_from_metrics(row)
        gates.insert(0, "candidate", row["candidate"])
        gate_frames.append(gates)
    acceptance = acceptance_and_strength(full_metrics, weakest, data_check)
    gate_results = pd.concat(gate_frames + [acceptance.assign(metric_value="", threshold="")], ignore_index=True)
    full_metrics = add_acceptance_columns(full_metrics, gate_results)
    best = choose_best_overlay(full_metrics)
    best_throttle = choose_best_throttle_overlay(full_metrics)
    accepted_any = bool(full_metrics.loc[full_metrics["candidate"] != "baseline_no_overlay", "accepted_candidate_needs_human_review"].any())
    throttle_mask = (full_metrics["candidate"] != "baseline_no_overlay") & (full_metrics["candidate"] != "high_beta_softcap_15")
    throttle_accepted_any = bool(full_metrics.loc[throttle_mask, "accepted_candidate_needs_human_review"].any())
    strong_any = bool(full_metrics.loc[full_metrics["candidate"] != "baseline_no_overlay", "strong_candidate"].any())
    largest_risk = build_largest_risk(best, weakest)

    full_metrics.to_csv(out_dir / "cycle04_full_period_metrics.csv", index=False)
    nav.to_csv(out_dir / "cycle04_nav_by_candidate.csv", index=False)
    scale_summary_df.to_csv(out_dir / "cycle04_overlay_scale_summary.csv", index=False)
    exposure_summary_df.to_csv(out_dir / "cycle04_exposure_summary.csv", index=False)
    loo.to_csv(out_dir / "cycle04_leave_one_year_out.csv", index=False)
    top_month.to_csv(out_dir / "cycle04_top_month_sensitivity.csv", index=False)
    rolling.to_csv(out_dir / "cycle04_rolling_12m_metrics.csv", index=False)
    ticker_exposure.to_csv(out_dir / "cycle04_ticker_and_high_beta_exposure.csv", index=False)
    gate_results.to_csv(out_dir / "cycle04_gate_results.csv", index=False)
    weakest.to_csv(out_dir / "cycle04_weakest_12m_comparison.csv", index=False)
    monthly.to_csv(out_dir / "cycle04_monthly_return_table.csv", index=False)
    annual.to_csv(out_dir / "cycle04_annual_return_table.csv", index=False)
    ticker_contrib.to_csv(out_dir / "cycle04_ticker_contribution.csv", index=False)

    verdict = {
        "cycle_id": "04",
        "cycle_type": "ex_ante_vol_drawdown_throttle_overlay_replay",
        "run_dir": str(args.run_dir),
        "candidate_list": candidate_ids,
        "model_retrained": False,
        "selection_signal_changed": False,
        "overlay_replay_only": True,
        "expanded_universe": False,
        "entered_v9": False,
        "ran_31b": False,
        "data_availability_check": data_check,
        "accepted_candidate": accepted_any,
        "throttle_accepted_candidate": throttle_accepted_any,
        "strong_candidate": strong_any,
        "replace_best": False,
        "allow_enter_v9": False,
        "best_overlay_candidate": best,
        "best_throttle_candidate": best_throttle,
        "largest_risk": largest_risk,
        "baseline_reference_metrics": {
            "cagr": BASELINE_CAGR,
            "calmar": BASELINE_CALMAR,
            "max_drawdown": BASELINE_MAXDD,
            "cost50_cagr": BASELINE_COST50_CAGR,
            "classification": BASELINE_VERDICT,
            "allow_enter_v9": BASELINE_ALLOW_ENTER_V9,
        },
        "pause_triggered": True,
        "pause_reason": "Cycle 04 completed; user explicitly required pausing before cycle 05 or any best-strategy decision.",
        "final_cycle_verdict": "strong_candidate_needs_human_review"
        if strong_any
        else ("accepted_candidate_needs_human_review" if accepted_any else "diagnostic_only_or_rejected_needs_human_review"),
        "next_recommendation": "暂停并由用户/ChatGPT 决定是否做 v8.1 final validation；不要进入 v9，不扩 universe。",
    }
    write_json(out_dir / "cycle04_verdict.json", verdict)
    write_json(out_dir / "cycle_verdict.json", verdict)
    write_json(
        out_dir / "best_candidate_index.json",
        {
            "best_candidate_id": "v8_baseline",
            "best_source": str(args.run_dir),
            "last_cycle_id": "04",
            "last_cycle_status": verdict["final_cycle_verdict"],
            "best_overlay_candidate": best,
            "best_throttle_candidate": best_throttle,
            "accepted_candidate": accepted_any,
            "throttle_accepted_candidate": throttle_accepted_any,
            "strong_candidate": strong_any,
            "replace_best": False,
            "allow_enter_v9": False,
        },
    )

    doc_path, exec_path, local_doc = write_reports(
        timestamp,
        out_dir,
        candidate_ids,
        data_check,
        full_metrics,
        weakest,
        gate_results,
        scale_summary_df,
        verdict,
    )
    write_workbook(
        out_dir / "reports" / "cycle04_vol_drawdown_overlay.xlsx",
        {
            "full_metrics": full_metrics,
            "weakest_12m": weakest,
            "gates": gate_results,
            "scale_summary": scale_summary_df,
            "exposure": exposure_summary_df,
            "top_month": top_month,
            "loo": loo,
            "ticker_exposure": ticker_exposure,
        },
    )
    zip_target = unique_path(OUTPUT_ROOT / f"us_stock_selection_quant_lab_v8_1_cycle04_vol_drawdown_overlay_{timestamp}.zip")
    update_next_steps(PROJECT_ROOT / "NEXT_STEPS.md", out_dir, zip_target, verdict, candidate_ids)
    update_run_summary(PROJECT_ROOT / "RUN_SUMMARY.md", out_dir, zip_target, verdict)
    zip_path = package(
        zip_target,
        [
            PROJECT_ROOT / "scripts" / "us_stock_selection" / "36_run_v8_1_cycle04_vol_drawdown_overlay.py",
            PROJECT_ROOT / "quant_lab" / "us_stock_selection" / "v8_1_gate_aware.py",
            PROJECT_ROOT / "quant_lab" / "us_stock_selection" / "v8_1_gate_metrics.py",
            PROJECT_ROOT / "quant_lab" / "us_stock_selection" / "v8_1_reporting.py",
            out_dir,
            doc_path,
            exec_path,
            local_doc,
            PROJECT_ROOT / "NEXT_STEPS.md",
            PROJECT_ROOT / "RUN_SUMMARY.md",
        ],
    )
    logger.info("Cycle 04 packaged: %s", zip_path)
    print({"out_dir": str(out_dir), "zip_path": str(zip_path), "verdict": verdict["final_cycle_verdict"]})


if __name__ == "__main__":
    main()
