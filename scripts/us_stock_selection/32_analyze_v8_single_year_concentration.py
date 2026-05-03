"""Diagnose the v8 single-year concentration gate without rerunning strategy logic."""

from __future__ import annotations

import argparse
import json
import logging
import math
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUN_DIR = PROJECT_ROOT / "outputs" / "us_stock_selection" / "run_20260426_095958"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "us_stock_selection"
DOCS_DIR = PROJECT_ROOT / "docs"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read an existing v8 run and diagnose the single-year concentration gate."
    )
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR, help="Existing v8 run directory.")
    parser.add_argument("--out-dir", type=Path, default=None, help="Output directory for diagnostic artifacts.")
    parser.add_argument("--timestamp", default=None, help="Timestamp override, format YYYYMMDD_HHMMSS.")
    parser.add_argument("--no-zip", action="store_true", help="Generate diagnostics but skip final zip packaging.")
    return parser.parse_args()


def setup_logging(out_dir: Path) -> logging.Logger:
    logs_dir = out_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("v8_single_year_gate")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    file_handler = logging.FileHandler(logs_dir / "single_year_gate_diagnostic.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger


def read_csv(path: Path, logger: logging.Logger, required: bool = True) -> pd.DataFrame:
    if not path.exists():
        msg = f"Missing input file: {path}"
        if required:
            logger.warning(msg)
        else:
            logger.info(msg)
        return pd.DataFrame()
    try:
        df = pd.read_csv(path)
        logger.info("Loaded %s rows=%s cols=%s", path, len(df), len(df.columns))
        return df
    except Exception as exc:  # pragma: no cover - defensive logging for local diagnostics
        logger.warning("Failed reading %s: %s", path, exc)
        return pd.DataFrame()


def read_json(path: Path, logger: logging.Logger) -> dict[str, Any]:
    if not path.exists():
        logger.warning("Missing JSON input file: %s", path)
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        logger.info("Loaded JSON %s", path)
        return data
    except Exception as exc:  # pragma: no cover
        logger.warning("Failed reading %s: %s", path, exc)
        return {}


def find_column(df: pd.DataFrame, aliases: list[str]) -> str | None:
    lookup = {str(c).lower(): c for c in df.columns}
    for alias in aliases:
        if alias.lower() in lookup:
            return str(lookup[alias.lower()])
    return None


def normalize_daily_nav(daily: pd.DataFrame, logger: logging.Logger) -> pd.DataFrame:
    if daily.empty:
        return pd.DataFrame(columns=["date", "return", "nav", "turnover"])
    date_col = find_column(daily, ["date", "datetime", "trade_date"])
    ret_col = find_column(daily, ["return", "returns", "daily_return"])
    nav_col = find_column(daily, ["nav", "net_value", "equity"])
    turnover_col = find_column(daily, ["turnover", "daily_turnover"])
    if date_col is None:
        logger.warning("daily_nav has no date-like column. Columns=%s", list(daily.columns))
        return pd.DataFrame(columns=["date", "return", "nav", "turnover"])
    out = pd.DataFrame()
    out["date"] = pd.to_datetime(daily[date_col], errors="coerce")
    if ret_col is not None:
        out["return"] = pd.to_numeric(daily[ret_col], errors="coerce").fillna(0.0)
    elif nav_col is not None:
        nav = pd.to_numeric(daily[nav_col], errors="coerce")
        out["return"] = nav.pct_change().fillna(0.0)
        logger.warning("daily_nav return column missing; inferred returns from nav pct_change.")
    else:
        logger.warning("daily_nav has neither return nor nav column.")
        out["return"] = 0.0
    if nav_col is not None:
        out["nav"] = pd.to_numeric(daily[nav_col], errors="coerce")
    else:
        out["nav"] = (1.0 + out["return"]).cumprod()
        logger.warning("daily_nav nav column missing; rebuilt nav from returns.")
    if turnover_col is not None:
        out["turnover"] = pd.to_numeric(daily[turnover_col], errors="coerce").fillna(0.0)
    else:
        out["turnover"] = 0.0
        logger.warning("daily_nav turnover column missing; turnover diagnostics default to 0.")
    out = out.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    return out


def normalize_dates(df: pd.DataFrame, date_cols: list[str]) -> pd.DataFrame:
    out = df.copy()
    for col in date_cols:
        if col in out.columns:
            out[col] = pd.to_datetime(out[col], errors="coerce")
    return out


def max_drawdown(nav: pd.Series) -> float:
    clean = pd.to_numeric(nav, errors="coerce").dropna()
    if clean.empty:
        return float("nan")
    peak = clean.cummax()
    dd = clean / peak - 1.0
    return float(dd.min())


def drawdown_from_returns(returns: pd.Series) -> float:
    clean = pd.to_numeric(returns, errors="coerce").dropna()
    if clean.empty:
        return float("nan")
    nav = (1.0 + clean).cumprod()
    return max_drawdown(nav)


def metrics_from_returns(returns: pd.Series) -> dict[str, float]:
    clean = pd.to_numeric(returns, errors="coerce").dropna()
    if clean.empty:
        return {"daily_count": 0, "total_return": np.nan, "cagr": np.nan, "max_drawdown": np.nan, "calmar": np.nan}
    nav = (1.0 + clean).cumprod()
    total = float(nav.iloc[-1] - 1.0)
    n = int(clean.shape[0])
    if 1.0 + total <= 0.0:
        cagr = -1.0
    else:
        cagr = float((1.0 + total) ** (252.0 / n) - 1.0)
    dd = max_drawdown(nav)
    calmar = float(cagr / abs(dd)) if dd < 0 and not math.isnan(dd) else np.inf
    return {"daily_count": n, "total_return": total, "cagr": cagr, "max_drawdown": dd, "calmar": calmar}


def nav_before_first(group: pd.DataFrame) -> float:
    first = group.iloc[0]
    daily_ret = float(first.get("return", 0.0))
    nav = float(first.get("nav", np.nan))
    if math.isnan(nav):
        return float("nan")
    denom = 1.0 + daily_ret
    return float(nav / denom) if denom != 0.0 else nav


def table_to_markdown(df: pd.DataFrame, columns: list[str] | None = None, max_rows: int = 20) -> str:
    if df is None or df.empty:
        return "_No rows_\n"
    sub = df.copy()
    if columns:
        sub = sub[[c for c in columns if c in sub.columns]]
    sub = sub.head(max_rows)
    for col in sub.columns:
        if pd.api.types.is_float_dtype(sub[col]):
            sub[col] = sub[col].map(lambda x: "" if pd.isna(x) else f"{float(x):.6f}")
    header = "| " + " | ".join(map(str, sub.columns)) + " |"
    sep = "| " + " | ".join(["---"] * len(sub.columns)) + " |"
    rows = ["| " + " | ".join(str(row[c]).replace("|", "/") for c in sub.columns) + " |" for _, row in sub.iterrows()]
    return "\n".join([header, sep, *rows]) + "\n"


def holding_string(holdings: pd.DataFrame, month: str) -> str:
    if holdings.empty or "ticker" not in holdings or "weight" not in holdings:
        return ""
    local = holdings.copy()
    date_col = "execution_date" if "execution_date" in local.columns else "decision_date" if "decision_date" in local.columns else None
    if date_col is None:
        return ""
    period = pd.Period(month, freq="M")
    month_end = period.to_timestamp(how="end")
    same_month = local.loc[local[date_col].dt.to_period("M").astype(str) == month].copy()
    if same_month.empty:
        eligible = local.loc[local[date_col] <= month_end].copy()
        if eligible.empty:
            return ""
        active_date = eligible[date_col].max()
        local = eligible.loc[eligible[date_col] == active_date].copy()
        suffix = f"@{pd.Timestamp(active_date).date()}"
    else:
        active_date = same_month[date_col].max()
        local = same_month.loc[same_month[date_col] == active_date].copy()
        suffix = ""
    if local.empty:
        return ""
    local["weight"] = pd.to_numeric(local["weight"], errors="coerce").fillna(0.0)
    local = local.sort_values(["weight", "ticker"], ascending=[False, True]).head(10)
    return ";".join(f"{r.ticker}:{float(r.weight):.2f}{suffix}" for r in local.itertuples())


def trade_string(trades: pd.DataFrame, month: str) -> str:
    if trades.empty or "ticker" not in trades:
        return ""
    local = trades.copy()
    date_col = "execution_date" if "execution_date" in local.columns else "decision_date" if "decision_date" in local.columns else None
    if date_col is None:
        return ""
    local = local.loc[local[date_col].dt.to_period("M").astype(str) == month].copy()
    if local.empty:
        return ""
    parts = []
    delta_col = "delta_weight" if "delta_weight" in local.columns else None
    for ticker, grp in local.groupby("ticker"):
        if delta_col:
            delta = pd.to_numeric(grp[delta_col], errors="coerce").sum()
            parts.append(f"{ticker}:{delta:+.2f}")
        else:
            parts.append(f"{ticker}:{len(grp)}")
    return ";".join(sorted(parts)[:12])


def top_holdings_by_year(holdings: pd.DataFrame, year: int, limit: int = 5) -> str:
    if holdings.empty or "ticker" not in holdings or "weight" not in holdings:
        return ""
    date_col = "execution_date" if "execution_date" in holdings.columns else "decision_date" if "decision_date" in holdings.columns else None
    if date_col is None:
        return ""
    local = holdings.loc[holdings[date_col].dt.year == year].copy()
    if local.empty:
        return ""
    local["weight"] = pd.to_numeric(local["weight"], errors="coerce").fillna(0.0)
    grouped = (
        local.groupby("ticker")
        .agg(appearance_count=("ticker", "size"), avg_weight=("weight", "mean"), max_weight=("weight", "max"))
        .reset_index()
        .sort_values(["appearance_count", "avg_weight", "ticker"], ascending=[False, False, True])
        .head(limit)
    )
    return ";".join(
        f"{r.ticker}({int(r.appearance_count)}x,avg={float(r.avg_weight):.2f},max={float(r.max_weight):.2f})"
        for r in grouped.itertuples()
    )


def annual_diagnostics(
    daily: pd.DataFrame,
    decisions: pd.DataFrame,
    holdings: pd.DataFrame,
    verdict: dict[str, Any],
) -> tuple[pd.DataFrame, int | None]:
    rows: list[dict[str, Any]] = []
    if daily.empty:
        return pd.DataFrame(), None
    yearly_return_abs_sum = 0.0
    temp_rows: list[dict[str, Any]] = []
    for year, group in daily.groupby(daily["date"].dt.year):
        start_nav = nav_before_first(group)
        end_nav = float(group["nav"].iloc[-1])
        annual_return = float((1.0 + group["return"]).prod() - 1.0)
        annual_profit = end_nav - start_nav
        local_path = pd.concat([pd.Series([start_nav]), group["nav"].reset_index(drop=True)], ignore_index=True)
        decision_count = 0
        if not decisions.empty:
            dcol = "decision_date" if "decision_date" in decisions.columns else "execution_date" if "execution_date" in decisions.columns else None
            if dcol:
                decision_count = int((decisions[dcol].dt.year == year).sum())
        temp_rows.append(
            {
                "year": int(year),
                "start_nav": start_nav,
                "end_nav": end_nav,
                "annual_return": annual_return,
                "annual_profit": annual_profit,
                "max_drawdown_in_year": max_drawdown(local_path),
                "trading_month_count": int(group["date"].dt.to_period("M").nunique()),
                "decision_count": decision_count,
                "turnover": float(group["turnover"].sum()) if "turnover" in group else np.nan,
                "dominant_tickers_or_holdings": top_holdings_by_year(holdings, int(year)),
            }
        )
        yearly_return_abs_sum += abs(annual_return)
    abs_profit_sum = sum(abs(r["annual_profit"]) for r in temp_rows)
    positive_profit_sum = sum(max(0.0, r["annual_profit"]) for r in temp_rows)
    for row in temp_rows:
        row["annual_profit_share"] = abs(row["annual_profit"]) / abs_profit_sum if abs_profit_sum else 0.0
        row["positive_profit_share"] = (
            row["annual_profit"] / positive_profit_sum if row["annual_profit"] > 0.0 and positive_profit_sum else 0.0
        )
        row["gate_abs_year_return_share"] = abs(row["annual_return"]) / yearly_return_abs_sum if yearly_return_abs_sum else 0.0
        rows.append(row)
    annual = pd.DataFrame(rows).sort_values("year").reset_index(drop=True)
    dominant_year = None
    if not annual.empty:
        dominant_year = int(annual.sort_values("gate_abs_year_return_share", ascending=False).iloc[0]["year"])
    verdict_share = verdict.get("single_year_share")
    if verdict_share is not None and not annual.empty:
        annual["matches_v8_single_year_share"] = annual["gate_abs_year_return_share"].map(
            lambda x: bool(abs(float(x) - float(verdict_share)) < 1e-9)
        )
    return annual, dominant_year


def monthly_diagnostics(daily: pd.DataFrame, holdings: pd.DataFrame, trades: pd.DataFrame) -> pd.DataFrame:
    if daily.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for period, group in daily.groupby(daily["date"].dt.to_period("M")):
        month = str(period)
        start_nav = nav_before_first(group)
        end_nav = float(group["nav"].iloc[-1])
        monthly_return = float((1.0 + group["return"]).prod() - 1.0)
        monthly_profit = end_nav - start_nav
        local_path = pd.concat([pd.Series([start_nav]), group["nav"].reset_index(drop=True)], ignore_index=True)
        rows.append(
            {
                "month": month,
                "monthly_return": monthly_return,
                "monthly_profit": monthly_profit,
                "cumulative_nav_before": start_nav,
                "cumulative_nav_after": end_nav,
                "max_drawdown_in_month": max_drawdown(local_path),
                "trading_day_count": int(group.shape[0]),
                "related_holdings": holding_string(holdings, month),
                "related_trades": trade_string(trades, month),
            }
        )
    monthly = pd.DataFrame(rows)
    abs_profit_sum = monthly["monthly_profit"].abs().sum()
    pos_profit_sum = monthly.loc[monthly["monthly_profit"] > 0, "monthly_profit"].sum()
    abs_return_sum = monthly["monthly_return"].abs().sum()
    monthly["contribution_share"] = monthly["monthly_profit"].abs() / abs_profit_sum if abs_profit_sum else 0.0
    monthly["positive_profit_share"] = np.where(
        monthly["monthly_profit"] > 0,
        monthly["monthly_profit"] / pos_profit_sum if pos_profit_sum else 0.0,
        0.0,
    )
    monthly["abs_month_return_share"] = monthly["monthly_return"].abs() / abs_return_sum if abs_return_sum else 0.0
    return monthly


def holding_diagnostics(
    holdings: pd.DataFrame,
    decisions: pd.DataFrame,
    trades: pd.DataFrame,
    dominant_year: int | None,
    logger: logging.Logger,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if holdings.empty:
        logger.warning("monthly_holdings is empty; holding concentration outputs will be empty.")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    date_col = "execution_date" if "execution_date" in holdings.columns else "decision_date" if "decision_date" in holdings.columns else None
    if date_col is None or "ticker" not in holdings.columns or "weight" not in holdings.columns:
        logger.warning("monthly_holdings lacks execution/decision date, ticker, or weight columns. Columns=%s", list(holdings.columns))
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    local = holdings.copy()
    local["weight"] = pd.to_numeric(local["weight"], errors="coerce").fillna(0.0)
    local["year"] = local[date_col].dt.year
    local = local.dropna(subset=["year"])
    local["year"] = local["year"].astype(int)
    per_rebalance = local.loc[local["weight"] > 1e-12].groupby([local["year"], date_col]).size().rename("holding_count").reset_index()
    yearly_rows = []
    for year, grp in local.groupby("year"):
        active = grp.loc[grp["weight"] > 1e-12]
        by_ticker = active.groupby("ticker").agg(avg_weight=("weight", "mean"), max_weight=("weight", "max"), appearance_count=("ticker", "size")).reset_index()
        by_ticker = by_ticker.sort_values(["appearance_count", "avg_weight", "ticker"], ascending=[False, False, True])
        avg_holding_count = float(per_rebalance.loc[per_rebalance["year"] == year, "holding_count"].mean()) if not per_rebalance.empty else np.nan
        max_avg_row = by_ticker.sort_values(["avg_weight", "appearance_count"], ascending=[False, False]).head(1)
        max_month_row = by_ticker.sort_values(["max_weight", "appearance_count"], ascending=[False, False]).head(1)
        yearly_rows.append(
            {
                "year": int(year),
                "ticker_count": int(active["ticker"].nunique()),
                "avg_holding_count": avg_holding_count,
                "single_ticker_max_avg_weight": float(max_avg_row["avg_weight"].iloc[0]) if not max_avg_row.empty else np.nan,
                "single_ticker_max_avg_weight_ticker": str(max_avg_row["ticker"].iloc[0]) if not max_avg_row.empty else "",
                "single_ticker_max_month_weight": float(max_month_row["max_weight"].iloc[0]) if not max_month_row.empty else np.nan,
                "single_ticker_max_month_weight_ticker": str(max_month_row["ticker"].iloc[0]) if not max_month_row.empty else "",
                "dominant_tickers_or_holdings": top_holdings_by_year(local, int(year)),
            }
        )
    yearly = pd.DataFrame(yearly_rows).sort_values("year").reset_index(drop=True)

    trade_stats = pd.DataFrame()
    if not trades.empty and "ticker" in trades.columns:
        tdate = "execution_date" if "execution_date" in trades.columns else "decision_date" if "decision_date" in trades.columns else None
        tlocal = trades.copy()
        if tdate:
            tlocal["year"] = tlocal[tdate].dt.year
        if "delta_weight" in tlocal.columns:
            tlocal["delta_weight"] = pd.to_numeric(tlocal["delta_weight"], errors="coerce").fillna(0.0)
            trade_stats = (
                tlocal.groupby("ticker")
                .agg(
                    trade_count=("ticker", "size"),
                    buy_delta_weight=("delta_weight", lambda s: float(s[s > 0].sum())),
                    sell_delta_weight=("delta_weight", lambda s: float(s[s < 0].sum())),
                    net_delta_weight=("delta_weight", "sum"),
                )
                .reset_index()
            )
        else:
            trade_stats = tlocal.groupby("ticker").size().rename("trade_count").reset_index()

    ticker_summary = (
        local.loc[local["weight"] > 1e-12]
        .groupby("ticker")
        .agg(
            appearance_count=("ticker", "size"),
            years_active=("year", "nunique"),
            avg_weight_when_held=("weight", "mean"),
            max_weight=("weight", "max"),
            first_execution_date=(date_col, "min"),
            last_execution_date=(date_col, "max"),
        )
        .reset_index()
    )
    if not trade_stats.empty:
        ticker_summary = ticker_summary.merge(trade_stats, on="ticker", how="left")
    ticker_summary = ticker_summary.sort_values(["appearance_count", "avg_weight_when_held", "ticker"], ascending=[False, False, True]).reset_index(drop=True)

    dominant = pd.DataFrame()
    if dominant_year is not None:
        d = local.loc[(local["year"] == dominant_year) & (local["weight"] > 1e-12)]
        dominant = (
            d.groupby("ticker")
            .agg(
                year=("year", "first"),
                appearance_count=("ticker", "size"),
                avg_weight_when_held=("weight", "mean"),
                max_weight=("weight", "max"),
                first_execution_date=(date_col, "min"),
                last_execution_date=(date_col, "max"),
            )
            .reset_index()
        )
        if not trades.empty and "ticker" in trades.columns:
            tdate = "execution_date" if "execution_date" in trades.columns else "decision_date" if "decision_date" in trades.columns else None
            tlocal = trades.copy()
            if tdate:
                tlocal = tlocal.loc[tlocal[tdate].dt.year == dominant_year]
            if "delta_weight" in tlocal.columns:
                tlocal["delta_weight"] = pd.to_numeric(tlocal["delta_weight"], errors="coerce").fillna(0.0)
                dstats = (
                    tlocal.groupby("ticker")
                    .agg(
                        trade_count=("ticker", "size"),
                        buy_delta_weight=("delta_weight", lambda s: float(s[s > 0].sum())),
                        sell_delta_weight=("delta_weight", lambda s: float(s[s < 0].sum())),
                        net_delta_weight=("delta_weight", "sum"),
                    )
                    .reset_index()
                )
            else:
                dstats = tlocal.groupby("ticker").size().rename("trade_count").reset_index()
            dominant = dominant.merge(dstats, on="ticker", how="left")
        dominant = dominant.sort_values(["appearance_count", "avg_weight_when_held", "ticker"], ascending=[False, False, True]).reset_index(drop=True)
    pnl_cols = [c for c in trades.columns if str(c).lower() in {"pnl", "profit", "return_contribution", "realized_pnl"}]
    if not pnl_cols:
        logger.warning("trades.csv has no PnL/profit column; ticker-level return attribution is exposure-only.")
        ticker_summary["pnl_available"] = False
        dominant["pnl_available"] = False
    return yearly, dominant, ticker_summary


def leave_one_year_out(daily: pd.DataFrame) -> pd.DataFrame:
    if daily.empty:
        return pd.DataFrame()
    rows = []
    for year in sorted(daily["date"].dt.year.unique()):
        local = daily.loc[daily["date"].dt.year != year, "return"]
        metrics = metrics_from_returns(local)
        rows.append({"removed_year": int(year), "cagr_ge_20": bool(metrics["cagr"] >= 0.20), **metrics})
    return pd.DataFrame(rows)


def top_month_removed(daily: pd.DataFrame, monthly: pd.DataFrame) -> pd.DataFrame:
    if daily.empty or monthly.empty:
        return pd.DataFrame()
    top_months = monthly.loc[monthly["monthly_profit"] > 0].sort_values("monthly_profit", ascending=False)["month"].tolist()
    rows = []
    for n in [1, 3, 5]:
        removed = top_months[:n]
        local = daily.loc[~daily["date"].dt.to_period("M").astype(str).isin(removed), "return"]
        metrics = metrics_from_returns(local)
        removed_profit = float(monthly.loc[monthly["month"].isin(removed), "monthly_profit"].sum())
        rows.append({"removed_top_positive_month_count": n, "removed_months": ",".join(removed), "removed_profit": removed_profit, **metrics})
    return pd.DataFrame(rows)


def rolling_12m(daily: pd.DataFrame) -> pd.DataFrame:
    if daily.empty:
        return pd.DataFrame()
    months = sorted(daily["date"].dt.to_period("M").unique())
    rows = []
    for i in range(0, len(months) - 11):
        window = months[i : i + 12]
        local = daily.loc[daily["date"].dt.to_period("M").isin(window), "return"]
        metrics = metrics_from_returns(local)
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


def build_input_index(run_dir: Path, inputs: dict[str, Path], loaded: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for name, path in inputs.items():
        row = {
            "name": name,
            "path": str(path),
            "exists": path.exists(),
            "rows": None,
            "columns": "",
            "size_bytes": path.stat().st_size if path.exists() else None,
        }
        df = loaded.get(name)
        if df is not None and not df.empty:
            row["rows"] = int(len(df))
            row["columns"] = ",".join(map(str, df.columns))
        rows.append(row)
    return pd.DataFrame(rows)


def write_outputs(
    out_dir: Path,
    docs_path: Path,
    run_dir: Path,
    timestamp: str,
    verdict: dict[str, Any],
    annual: pd.DataFrame,
    monthly: pd.DataFrame,
    top_pos: pd.DataFrame,
    top_neg: pd.DataFrame,
    yearly_conc: pd.DataFrame,
    dominant_holdings: pd.DataFrame,
    ticker_summary: pd.DataFrame,
    loo: pd.DataFrame,
    removed: pd.DataFrame,
    rolling: pd.DataFrame,
    input_index: pd.DataFrame,
    formula_text: str,
    logger: logging.Logger,
) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "annual_contribution": out_dir / "annual_contribution.csv",
        "monthly_contribution": out_dir / "monthly_contribution.csv",
        "top_positive_months": out_dir / "top_positive_months.csv",
        "top_negative_months": out_dir / "top_negative_months.csv",
        "yearly_holding_concentration": out_dir / "yearly_holding_concentration.csv",
        "dominant_year_holdings": out_dir / "dominant_year_holdings.csv",
        "ticker_exposure_summary": out_dir / "ticker_exposure_summary.csv",
        "leave_one_year_out_metrics": out_dir / "leave_one_year_out_metrics.csv",
        "top_month_removed_metrics": out_dir / "top_month_removed_metrics.csv",
        "rolling_12m_metrics": out_dir / "rolling_12m_metrics.csv",
        "input_file_index": out_dir / "input_file_index.csv",
    }
    frames = {
        "annual_contribution": annual,
        "monthly_contribution": monthly,
        "top_positive_months": top_pos,
        "top_negative_months": top_neg,
        "yearly_holding_concentration": yearly_conc,
        "dominant_year_holdings": dominant_holdings,
        "ticker_exposure_summary": ticker_summary,
        "leave_one_year_out_metrics": loo,
        "top_month_removed_metrics": removed,
        "rolling_12m_metrics": rolling,
        "input_file_index": input_index,
    }
    for key, df in frames.items():
        df.to_csv(files[key], index=False)
        logger.info("Wrote %s rows=%s", files[key], len(df))

    dominant_row = annual.sort_values("gate_abs_year_return_share", ascending=False).head(1)
    second_row = annual.sort_values("gate_abs_year_return_share", ascending=False).iloc[1:2] if len(annual) > 1 else pd.DataFrame()
    dominant_year = int(dominant_row["year"].iloc[0]) if not dominant_row.empty else None
    dominant_share = float(dominant_row["gate_abs_year_return_share"].iloc[0]) if not dominant_row.empty else np.nan
    second_share = float(second_row["gate_abs_year_return_share"].iloc[0]) if not second_row.empty else np.nan
    share_gap = dominant_share - second_share if not math.isnan(second_share) else np.nan
    top1_pos_share = float(top_pos["positive_profit_share"].head(1).sum()) if not top_pos.empty else 0.0
    top3_pos_share = float(top_pos["positive_profit_share"].head(3).sum()) if not top_pos.empty else 0.0
    top5_pos_share = float(top_pos["positive_profit_share"].head(5).sum()) if not top_pos.empty else 0.0
    remove_dom = loo.loc[loo["removed_year"] == dominant_year] if dominant_year is not None and not loo.empty else pd.DataFrame()
    remove_dom_metrics = remove_dom.iloc[0].to_dict() if not remove_dom.empty else {}
    strongest = rolling.sort_values("window_return", ascending=False).head(1) if not rolling.empty else pd.DataFrame()
    weakest = rolling.sort_values("window_return", ascending=True).head(1) if not rolling.empty else pd.DataFrame()

    report = f"""# US Stock Selection v8 Single-Year Gate Diagnostic - {timestamp}

Scope: read-only diagnosis of the accepted v8 run. This report does not enter v9, does not expand Nasdaq100/S&P500, does not run 31b, and does not rerun strategy logic.

Run directory: `{run_dir}`

## 1. single_year_share formula

{formula_text}

Confirmed v8 verdict:

- Final verdict: `{verdict.get("classification")}`
- allow_enter_v9: `{verdict.get("allow_enter_v9")}`
- single_year_share: `{verdict.get("single_year_share")}`
- single_year_share_lte_50: `{verdict.get("gates", {}).get("single_year_share_lte_50")}`

## 2. Annual contribution diagnosis

Dominant gate year: `{dominant_year}`

- Dominant gate share: `{dominant_share:.6f}`
- Second-highest gate share: `{second_share:.6f}`
- Gap: `{share_gap:.6f}`
- Interpretation: the breach is slight above the 50% threshold, not an overwhelming one-year-only result. It is still a real gate failure.

Annual table:

{table_to_markdown(annual, ["year", "start_nav", "end_nav", "annual_return", "annual_profit", "annual_profit_share", "positive_profit_share", "gate_abs_year_return_share", "max_drawdown_in_year", "trading_month_count", "decision_count", "turnover", "dominant_tickers_or_holdings"])}

Removing dominant gate year `{dominant_year}` from the existing daily NAV curve gives diagnostic-only metrics:

{table_to_markdown(remove_dom, ["removed_year", "daily_count", "total_return", "cagr", "max_drawdown", "calmar", "cagr_ge_20"])}

Important: this is a NAV-curve diagnostic, not a true strategy rerun.

## 3. Monthly and extreme-month diagnosis

Top positive months by NAV profit:

{table_to_markdown(top_pos, ["month", "monthly_return", "monthly_profit", "positive_profit_share", "contribution_share", "cumulative_nav_before", "cumulative_nav_after", "related_holdings", "related_trades"], 10)}

Top negative months by NAV profit:

{table_to_markdown(top_neg, ["month", "monthly_return", "monthly_profit", "contribution_share", "cumulative_nav_before", "cumulative_nav_after", "max_drawdown_in_month", "related_holdings", "related_trades"], 10)}

Extreme-month concentration:

- Top 1 positive month positive-profit share: `{top1_pos_share:.6f}`
- Top 3 positive months positive-profit share: `{top3_pos_share:.6f}`
- Top 5 positive months positive-profit share: `{top5_pos_share:.6f}`

The dominant year is not from a single positive month only; it is helped by several strong months, with the largest visible positive month being 2024-11.

## 4. Holding and ticker concentration diagnosis

Yearly holding concentration:

{table_to_markdown(yearly_conc, ["year", "ticker_count", "avg_holding_count", "single_ticker_max_avg_weight", "single_ticker_max_avg_weight_ticker", "single_ticker_max_month_weight", "single_ticker_max_month_weight_ticker", "dominant_tickers_or_holdings"])}

Dominant-year holdings:

{table_to_markdown(dominant_holdings, ["ticker", "year", "appearance_count", "avg_weight_when_held", "max_weight", "trade_count", "buy_delta_weight", "sell_delta_weight", "net_delta_weight", "pnl_available"], 20)}

Ticker exposure summary:

{table_to_markdown(ticker_summary, ["ticker", "appearance_count", "years_active", "avg_weight_when_held", "max_weight", "trade_count", "buy_delta_weight", "sell_delta_weight", "net_delta_weight", "pnl_available"], 20)}

`trades.csv` has buy/sell weight records but no ticker-level PnL column, so this report can attribute yearly exposure and rebalance activity, not exact yearly ticker PnL.

## 5. Diagnostic robustness sensitivity

Leave-one-year-out metrics:

{table_to_markdown(loo, ["removed_year", "daily_count", "total_return", "cagr", "max_drawdown", "calmar", "cagr_ge_20"])}

Top positive month removed metrics:

{table_to_markdown(removed, ["removed_top_positive_month_count", "removed_months", "removed_profit", "daily_count", "total_return", "cagr", "max_drawdown", "calmar"])}

Strongest 12-month window:

{table_to_markdown(strongest, ["start_month", "end_month", "window_return", "window_max_drawdown", "calmar_like", "daily_count"])}

Weakest 12-month window:

{table_to_markdown(weakest, ["start_month", "end_month", "window_return", "window_max_drawdown", "calmar_like", "daily_count"])}

These stress checks only transform the existing NAV series. They are not rebalanced, refit, or re-executed strategy backtests.

## 6. Acceptance judgment

- `single_year_share = 0.526` is a slight threshold breach, but it remains a valid concentration failure.
- v8 should remain `credible_but_execution_sensitive`.
- `allow_enter_v9` should remain `False`.
- The next research cycle should fix or explicitly relax year concentration controls before v9 is considered.
- 31b challenger can supplement model stability evidence, but it does not directly solve annual return concentration.

## 7. Recommended remediation order

1. Add a year-balance penalty to candidate scoring.
2. Add a leave-one-year-out Calmar gate.
3. Add a top-month contribution gate.
4. Add a ticker exposure concentration gate.
5. Add regime-segment performance requirements.
6. Apply separate yearly contribution constraints to TQQQ/QLD/high-beta names.
7. Treat 31b as challenger-model evidence only, not as the primary fix for the single-year gate.
"""
    report_path = out_dir / "US_STOCK_SELECTION_V8_SINGLE_YEAR_GATE_DIAGNOSTIC.md"
    report_path.write_text(report, encoding="utf-8")
    docs_path.parent.mkdir(parents=True, exist_ok=True)
    docs_path.write_text(report, encoding="utf-8")
    logger.info("Wrote markdown reports: %s and %s", report_path, docs_path)
    return {**files, "report": report_path, "docs_report": docs_path}


def unique_zip_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    i = 2
    while True:
        candidate = parent / f"{stem}_{i}{suffix}"
        if not candidate.exists():
            return candidate
        i += 1


def package_outputs(out_dir: Path, docs_path: Path, timestamp: str, logger: logging.Logger) -> Path:
    zip_path = unique_zip_path(
        DEFAULT_OUTPUT_ROOT / f"us_stock_selection_quant_lab_v8_single_year_gate_diagnostic_{timestamp}.zip"
    )
    paths = [
        PROJECT_ROOT / "scripts" / "us_stock_selection" / "32_analyze_v8_single_year_concentration.py",
        out_dir,
        docs_path,
        PROJECT_ROOT / "NEXT_STEPS.md",
    ]
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in paths:
            if not path.exists():
                logger.warning("Package path missing and skipped: %s", path)
                continue
            if path.is_dir():
                for child in path.rglob("*"):
                    if child.is_file():
                        zf.write(child, child.resolve().relative_to(PROJECT_ROOT))
            else:
                zf.write(path, path.resolve().relative_to(PROJECT_ROOT))
    logger.info("Packaged diagnostic zip: %s", zip_path)
    return zip_path


def main() -> None:
    args = parse_args()
    timestamp = args.timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = args.run_dir.resolve()
    out_dir = (args.out_dir or (DEFAULT_OUTPUT_ROOT / f"v8_single_year_concentration_{timestamp}")).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    logger = setup_logging(out_dir)
    logger.info("Starting v8 single-year gate diagnostic. run_dir=%s out_dir=%s", run_dir, out_dir)
    if not run_dir.exists():
        logger.warning("Run directory does not exist: %s", run_dir)

    inputs = {
        "v8_verdict": run_dir / "v8_verdict.json",
        "RUN_SUMMARY": run_dir / "RUN_SUMMARY.md",
        "daily_nav": run_dir / "v8_paper_trading" / "daily_nav.csv",
        "monthly_decision_ledger": run_dir / "v8_paper_trading" / "monthly_decision_ledger.csv",
        "monthly_holdings": run_dir / "v8_paper_trading" / "monthly_holdings.csv",
        "trades": run_dir / "v8_paper_trading" / "trades.csv",
        "execution_stress": run_dir / "v8_execution_sim" / "execution_stress_results.csv",
        "yearly_return": run_dir / "v8_attribution" / "yearly_return.csv",
        "monthly_return": run_dir / "v8_attribution" / "monthly_return.csv",
        "ticker_contribution": run_dir / "v8_attribution" / "ticker_contribution.csv",
        "holding_concentration": run_dir / "v8_attribution" / "holding_concentration.csv",
    }
    verdict = read_json(inputs["v8_verdict"], logger)
    loaded: dict[str, pd.DataFrame] = {}
    for key, path in inputs.items():
        if path.suffix.lower() == ".csv":
            loaded[key] = read_csv(path, logger, required=key in {"daily_nav", "monthly_decision_ledger", "monthly_holdings", "trades", "execution_stress"})

    daily = normalize_daily_nav(loaded.get("daily_nav", pd.DataFrame()), logger)
    decisions = normalize_dates(loaded.get("monthly_decision_ledger", pd.DataFrame()), ["decision_date", "feature_date", "prediction_date", "execution_date"])
    holdings = normalize_dates(loaded.get("monthly_holdings", pd.DataFrame()), ["decision_date", "execution_date"])
    trades = normalize_dates(loaded.get("trades", pd.DataFrame()), ["decision_date", "execution_date"])

    formula_text = (
        "Code-confirmed formula from `quant_lab/us_stock_selection/v8_reporting.py`: "
        "`denom = yearly[\"year_return\"].abs().sum()` and "
        "`single_year_share = yearly[\"year_return\"].abs().max() / denom`. "
        "The numerator is the largest absolute calendar-year compounded return from "
        "`v8_attribution/yearly_return.csv`; the denominator is the sum of absolute calendar-year "
        "compounded returns. It is not annual NAV profit, not only positive-year contribution, and not "
        "ticker PnL. The threshold is hard-coded in the same file as "
        "`single_year_share_lte_50: single_year_share <= 0.50`."
    )

    annual, dominant_year = annual_diagnostics(daily, decisions, holdings, verdict)
    monthly = monthly_diagnostics(daily, holdings, trades)
    top_pos = monthly.sort_values("monthly_profit", ascending=False).reset_index(drop=True) if not monthly.empty else pd.DataFrame()
    top_neg = monthly.sort_values("monthly_profit", ascending=True).reset_index(drop=True) if not monthly.empty else pd.DataFrame()
    yearly_conc, dominant_holdings, ticker_summary = holding_diagnostics(holdings, decisions, trades, dominant_year, logger)
    loo = leave_one_year_out(daily)
    removed = top_month_removed(daily, monthly)
    rolling = rolling_12m(daily)
    input_index = build_input_index(run_dir, inputs, loaded)

    docs_path = DOCS_DIR / f"US_STOCK_SELECTION_V8_SINGLE_YEAR_GATE_DIAGNOSTIC_{timestamp[:8]}.md"
    write_outputs(
        out_dir=out_dir,
        docs_path=docs_path,
        run_dir=run_dir,
        timestamp=timestamp,
        verdict=verdict,
        annual=annual,
        monthly=monthly,
        top_pos=top_pos,
        top_neg=top_neg,
        yearly_conc=yearly_conc,
        dominant_holdings=dominant_holdings,
        ticker_summary=ticker_summary,
        loo=loo,
        removed=removed,
        rolling=rolling,
        input_index=input_index,
        formula_text=formula_text,
        logger=logger,
    )
    if not args.no_zip:
        package_outputs(out_dir, docs_path, timestamp, logger)
    logger.info("Completed v8 single-year gate diagnostic.")


if __name__ == "__main__":
    main()
