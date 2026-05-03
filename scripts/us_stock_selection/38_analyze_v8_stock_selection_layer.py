"""v8.2 stock-selection layer root-cause diagnostic.

This diagnostic is intentionally read-only with respect to v8 trading logic. It
does not retrain models, expand the universe, run 31b, enter v9, or continue the
v8.1 overlay line. It inventories existing artifacts, attributes the frozen v8
baseline at holdings/trade/nav level, checks whether full monthly score/rank
audit trails exist, and designs the next stock-selection-layer work.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import shutil
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
from quant_lab.us_stock_selection.qlib_signal_backtest import compute_portfolio_metrics
from quant_lab.us_stock_selection.qlib_workflow_runner import load_close_from_provider
from quant_lab.us_stock_selection.utils import nav_from_returns
from quant_lab.us_stock_selection.v8_1_gate_aware import HIGH_BETA_TICKERS, build_weights_from_holdings
from quant_lab.us_stock_selection.v8_1_gate_metrics import monthly_table_from_daily, normalize_daily_nav, rolling_12m_metrics


DEFAULT_RUN_DIR = PROJECT_ROOT / "outputs" / "us_stock_selection" / "run_20260426_095958"
DEFAULT_CYCLE05_DIR = PROJECT_ROOT / "outputs" / "us_stock_selection" / "v8_1_cycle_05_market_regime_overlay_20260429_070013"
OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "us_stock_selection"
DOCS_DIR = PROJECT_ROOT / "docs"
WEAK_START = "2024-04-01"
WEAK_END = "2025-03-31"

BASELINE_METRICS = {
    "cagr": 0.6538182307494054,
    "cost50_cagr": 0.5608428724606129,
    "calmar": 1.99152684432784,
    "max_drawdown": -0.32829998380969627,
    "verdict": "credible_but_execution_sensitive",
    "allow_enter_v9": False,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze v8 stock-selection layer root causes.")
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument("--cycle05-dir", type=Path, default=DEFAULT_CYCLE05_DIR)
    parser.add_argument("--provider-uri", type=Path, default=default_local_provider_uri())
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--timestamp", default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def setup_logger(out_dir: Path) -> logging.Logger:
    log_dir = out_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("v8_2_stock_selection_diagnostic")
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


def read_csv_safe(path: Path, logger: logging.Logger | None = None, required: bool = False) -> pd.DataFrame:
    if not path.exists():
        if required:
            raise FileNotFoundError(path)
        if logger:
            logger.warning("Missing optional CSV: %s", path)
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception as exc:
        if required:
            raise
        if logger:
            logger.warning("Could not read %s: %s", path, exc)
        return pd.DataFrame()


def write_json(data: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(to_jsonable(data), handle, indent=2, ensure_ascii=False)


def to_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_jsonable(v) for v in value]
    if isinstance(value, tuple):
        return [to_jsonable(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if math.isnan(float(value)) else float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def table_to_markdown(df: pd.DataFrame, columns: list[str] | None = None, max_rows: int = 20) -> str:
    if df is None or df.empty:
        return "_No rows._"
    view = df.copy()
    if columns:
        view = view.loc[:, [c for c in columns if c in view.columns]]
    view = view.head(max_rows)
    return view.to_markdown(index=False)


def normalize_dates(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    out = df.copy()
    for col in cols:
        if col in out.columns:
            out[col] = pd.to_datetime(out[col], errors="coerce")
    return out


def first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def inventory_paths(run_dir: Path, cycle05_dir: Path) -> list[Path]:
    paths: list[Path] = [
        PROJECT_ROOT / "NEXT_STEPS.md",
        PROJECT_ROOT / "RUN_SUMMARY.md",
        run_dir / "v8_paper_trading" / "daily_nav.csv",
        run_dir / "v8_paper_trading" / "monthly_holdings.csv",
        run_dir / "v8_paper_trading" / "monthly_decision_ledger.csv",
        run_dir / "v8_paper_trading" / "trades.csv",
        run_dir / "v8_paper_trading" / "paper_trading_metrics.csv",
        run_dir / "v8_paper_trading" / "fit_convergence_log.csv",
        run_dir / "v8_attribution" / "monthly_return.csv",
        run_dir / "v8_attribution" / "ticker_contribution.csv",
        run_dir / "v8_attribution" / "holding_concentration.csv",
        run_dir / "v8_attribution" / "top_return_months.csv",
        run_dir / "v8_attribution" / "yearly_return.csv",
        run_dir / "v8_execution_sim" / "execution_stress_results.csv",
        run_dir / "v8_execution_sim" / "v8_verdict.json",
        run_dir / "v8_verdict.json",
        run_dir / "v7_feature_cache" / "alpha158_cache.parquet",
        run_dir / "v7_feature_cache" / "alpha360_cache.parquet",
        run_dir / "v7_feature_cache" / "feature_cache_status.csv",
        run_dir / "v7_feature_cache" / "feature_cache_status.json",
        cycle05_dir / "cycle05_verdict.json",
        cycle05_dir / "cycle05_full_period_metrics.csv",
        cycle05_dir / "cycle05_weakest_12m_comparison.csv",
        cycle05_dir / "cycle05_ticker_and_high_beta_exposure.csv",
        DOCS_DIR / "US_STOCK_SELECTION_V8_FINAL_ACCEPTANCE_20260426.md",
        DOCS_DIR / "US_STOCK_SELECTION_V8_GATE_CALIBRATION_REVIEW_20260428.md",
        DOCS_DIR / "US_STOCK_SELECTION_V8_SINGLE_YEAR_GATE_DIAGNOSTIC_20260427.md",
        DOCS_DIR / "US_STOCK_SELECTION_V8_1_EVOLUTION_CYCLE_03_20260428_170412.md",
        DOCS_DIR / "US_STOCK_SELECTION_V8_1_EVOLUTION_CYCLE_04_20260429_001104.md",
        DOCS_DIR / "US_STOCK_SELECTION_V8_1_EVOLUTION_CYCLE_05_20260429_070013.md",
        DOCS_DIR / "US_STOCK_SELECTION_V8_1_EVOLUTION_PLATEAU_MEMO_20260429_070013.md",
    ]
    for folder in [run_dir / "ranking", run_dir / "qlib_signal_backtest", run_dir / "qlib_model_lab"]:
        if folder.exists():
            paths.extend(sorted(folder.rglob("*")))
    return list(dict.fromkeys([p for p in paths if p.is_file() or p.suffix]))


def inspect_file(path: Path) -> dict[str, Any]:
    row: dict[str, Any] = {
        "file_path": str(path),
        "exists": path.exists(),
        "row_count": np.nan,
        "column_count": np.nan,
        "key_columns": "",
        "date_min": "",
        "date_max": "",
        "ticker_count": np.nan,
        "usable_for_attribution": False,
        "usable_for_ranking_diagnostic": False,
        "warnings": "",
    }
    if not path.exists():
        row["warnings"] = "missing"
        return row

    suffix = path.suffix.lower()
    try:
        if suffix == ".csv":
            df = pd.read_csv(path)
            update_inventory_row(row, df)
        elif suffix == ".parquet":
            df = pd.read_parquet(path)
            update_inventory_row(row, df)
        elif suffix == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                row["row_count"] = len(data)
                keys = sorted({str(k) for item in data if isinstance(item, dict) for k in item.keys()})
            elif isinstance(data, dict):
                row["row_count"] = 1
                keys = sorted(data.keys())
            else:
                keys = []
            row["column_count"] = len(keys)
            row["key_columns"] = ",".join(keys[:30])
        elif suffix in {".md", ".txt", ".yaml", ".yml", ".log"}:
            text = path.read_text(encoding="utf-8", errors="ignore")
            row["row_count"] = len(text.splitlines())
            row["column_count"] = 1
            row["key_columns"] = "text"
        else:
            row["warnings"] = "uninspected_file_type"
    except Exception as exc:
        row["warnings"] = f"inspect_failed: {exc}"

    name = path.name.lower()
    cols = str(row.get("key_columns", "")).lower()
    row["usable_for_attribution"] = any(token in name for token in ["daily_nav", "monthly_holdings", "trades", "monthly_return", "ticker_contribution"]) or (
        "ticker" in cols and "weight" in cols
    )
    row["usable_for_ranking_diagnostic"] = any(token in name for token in ["decision", "holding", "score", "rank", "prediction", "candidate", "feature_cache"]) or any(
        token in cols for token in ["score", "rank", "prediction", "instrument", "label"]
    )
    return row


def update_inventory_row(row: dict[str, Any], df: pd.DataFrame) -> None:
    row["row_count"] = int(len(df))
    row["column_count"] = int(len(df.columns))
    row["key_columns"] = ",".join(map(str, df.columns[:40]))
    date_cols = [c for c in df.columns if str(c).lower() in {"date", "datetime", "decision_date", "execution_date", "month"} or "date" in str(c).lower()]
    dates: list[pd.Series] = []
    for col in date_cols[:4]:
        vals = pd.to_datetime(df[col], errors="coerce")
        if vals.notna().any():
            dates.append(vals.dropna())
    if dates:
        all_dates = pd.concat(dates)
        row["date_min"] = str(all_dates.min().date())
        row["date_max"] = str(all_dates.max().date())
    ticker_cols = [c for c in df.columns if str(c).lower() in {"ticker", "instrument", "symbol"}]
    if ticker_cols:
        row["ticker_count"] = int(df[ticker_cols[0]].astype(str).str.upper().nunique())


def build_data_inventory(run_dir: Path, cycle05_dir: Path) -> pd.DataFrame:
    return pd.DataFrame([inspect_file(path) for path in inventory_paths(run_dir, cycle05_dir)])


def load_core_inputs(run_dir: Path, logger: logging.Logger) -> dict[str, pd.DataFrame]:
    paper = run_dir / "v8_paper_trading"
    inputs = {
        "daily": normalize_daily_nav(read_csv_safe(paper / "daily_nav.csv", logger, required=True)),
        "holdings": normalize_dates(read_csv_safe(paper / "monthly_holdings.csv", logger, required=True), ["decision_date", "execution_date"]),
        "ledger": normalize_dates(read_csv_safe(paper / "monthly_decision_ledger.csv", logger, required=True), ["decision_date", "feature_date", "prediction_date", "execution_date"]),
        "trades": normalize_dates(read_csv_safe(paper / "trades.csv", logger, required=True), ["decision_date", "execution_date"]),
        "metrics": read_csv_safe(paper / "paper_trading_metrics.csv", logger, required=True),
    }
    return inputs


def load_close_for_attribution(provider_uri: Path, holdings: pd.DataFrame, daily: pd.DataFrame, logger: logging.Logger) -> pd.DataFrame:
    tickers = sorted(set(holdings.get("ticker", pd.Series(dtype=str)).astype(str).str.upper().dropna()) | {"QQQ", "SPY"})
    start = str(pd.to_datetime(daily["date"]).min().date())
    end = str(pd.to_datetime(daily["date"]).max().date())
    logger.info("Loading close panel for attribution: %s tickers, %s to %s.", len(tickers), start, end)
    close = load_close_from_provider(provider_uri, tickers=tickers, start=start, end=end)
    close.index = pd.to_datetime(close.index)
    return close.loc[(close.index >= pd.Timestamp(start)) & (close.index <= pd.Timestamp(end))].sort_index().ffill()


def compute_contribution_panel(close: pd.DataFrame, weights: pd.DataFrame) -> pd.DataFrame:
    cols = close.columns.intersection(weights.columns)
    local_close = close.loc[:, cols].ffill()
    local_weights = weights.reindex(local_close.index).loc[:, cols].ffill().fillna(0.0)
    asset_returns = local_close.pct_change(fill_method=None).fillna(0.0)
    shifted_weights = local_weights.shift(1).fillna(0.0)
    contrib = shifted_weights * asset_returns
    contrib.index.name = "date"
    return contrib


def strategy_metrics_from_daily(daily: pd.DataFrame, weights: pd.DataFrame | None = None) -> dict[str, Any]:
    local = normalize_daily_nav(daily)
    returns = local.set_index("date")["return"]
    turnover = local.set_index("date")["turnover"] if "turnover" in local else pd.Series(0.0, index=returns.index)
    if weights is None or weights.empty:
        weights = pd.DataFrame({"strategy": 1.0}, index=returns.index)
    else:
        weights = weights.reindex(returns.index).ffill().fillna(0.0)
    return compute_portfolio_metrics(returns, turnover, weights)


def month_key(date_series: pd.Series) -> pd.Series:
    return pd.to_datetime(date_series, errors="coerce").dt.to_period("M").astype(str)


def monthly_selection_attribution(daily: pd.DataFrame, weights: pd.DataFrame, holdings: pd.DataFrame, trades: pd.DataFrame, contrib: pd.DataFrame) -> pd.DataFrame:
    daily = normalize_daily_nav(daily)
    monthly = monthly_table_from_daily(daily)
    if monthly.empty:
        return monthly
    weight_month = []
    local_weights = weights.reindex(pd.to_datetime(daily["date"])).ffill().fillna(0.0)
    local_weights.index = pd.to_datetime(daily["date"])
    for month, group in local_weights.groupby(local_weights.index.to_period("M").astype(str)):
        avg = group.mean()
        active = avg[avg.abs() > 1e-12].sort_values(ascending=False)
        high_beta_cols = [c for c in group.columns if c in HIGH_BETA_TICKERS]
        weight_month.append(
            {
                "month": month,
                "selected_ticker_count": int((active > 1e-12).sum()),
                "high_beta_selected_count": int(sum(1 for ticker in active.index if ticker in HIGH_BETA_TICKERS)),
                "high_beta_weight_share": float(group[high_beta_cols].sum(axis=1).mean()) if high_beta_cols else 0.0,
                "top_weight_ticker": str(active.index[0]) if not active.empty else "",
                "top_weight": float(active.iloc[0]) if not active.empty else 0.0,
            }
        )
    weight_month_df = pd.DataFrame(weight_month)

    contrib_rows = []
    for month, group in contrib.groupby(contrib.index.to_period("M").astype(str)):
        sums = group.sum().sort_values(ascending=False)
        abs_sum = group.abs().sum().sort_values(ascending=False)
        contrib_rows.append(
            {
                "month": month,
                "best_contributing_ticker": str(sums.index[0]) if not sums.empty else "",
                "best_ticker_contribution": float(sums.iloc[0]) if not sums.empty else 0.0,
                "worst_contributing_ticker": str(sums.index[-1]) if not sums.empty else "",
                "worst_ticker_contribution": float(sums.iloc[-1]) if not sums.empty else 0.0,
                "top_abs_ticker_contribution": str(abs_sum.index[0]) if not abs_sum.empty else "",
                "top_abs_ticker_contribution_abs": float(abs_sum.iloc[0]) if not abs_sum.empty else 0.0,
            }
        )
    contrib_df = pd.DataFrame(contrib_rows)

    trade_df = trades.copy()
    if not trade_df.empty:
        trade_df["month"] = month_key(trade_df["execution_date"])
        trade_summary = (
            trade_df.assign(abs_delta=lambda x: pd.to_numeric(x.get("delta_weight", 0.0), errors="coerce").abs())
            .groupby("month", as_index=False)
            .agg(turnover=("abs_delta", "sum"), trade_count=("ticker", "count"))
        )
    else:
        trade_summary = pd.DataFrame(columns=["month", "turnover", "trade_count"])

    out = monthly.merge(weight_month_df, on="month", how="left").merge(contrib_df, on="month", how="left").merge(trade_summary, on="month", how="left")
    out["contribution_share"] = pd.to_numeric(out.get("contribution_share", 0.0), errors="coerce").fillna(0.0)
    out = out.rename(columns={"max_drawdown_in_month": "drawdown_in_month"})
    return out.fillna({"turnover": 0.0, "trade_count": 0})


def ticker_selection_attribution(holdings: pd.DataFrame, contrib: pd.DataFrame) -> pd.DataFrame:
    h = holdings.copy()
    if h.empty:
        return pd.DataFrame()
    h["ticker"] = h["ticker"].astype(str).str.upper()
    h["weight"] = pd.to_numeric(h.get("weight", 0.0), errors="coerce").fillna(0.0)
    h["month"] = month_key(h["execution_date"])
    contrib_month = contrib.copy()
    contrib_month["month"] = contrib_month.index.to_period("M").astype(str)
    monthly_ticker = contrib_month.groupby("month").sum(numeric_only=True)
    rows: list[dict[str, Any]] = []
    total_abs = float(monthly_ticker.abs().sum().sum()) if not monthly_ticker.empty else 0.0
    for ticker, group in h.groupby("ticker"):
        selected_months = sorted(group["month"].dropna().astype(str).unique())
        ticker_series = monthly_ticker[ticker].reindex(selected_months).fillna(0.0) if ticker in monthly_ticker.columns else pd.Series(0.0, index=selected_months)
        rows.append(
            {
                "ticker": ticker,
                "selected_month_count": int(len(selected_months)),
                "avg_weight": float(group["weight"].mean()),
                "max_weight": float(group["weight"].max()),
                "approximate_return_contribution": float(ticker_series.sum()),
                "positive_month_count": int((ticker_series > 0).sum()),
                "negative_month_count": int((ticker_series < 0).sum()),
                "avg_return_when_selected": float(ticker_series.mean()) if len(ticker_series) else 0.0,
                "worst_month_when_selected": float(ticker_series.min()) if len(ticker_series) else 0.0,
                "best_month_when_selected": float(ticker_series.max()) if len(ticker_series) else 0.0,
                "high_beta_flag": ticker in HIGH_BETA_TICKERS,
                "concentration_share": float(ticker_series.abs().sum() / total_abs) if total_abs else 0.0,
            }
        )
    return pd.DataFrame(rows).sort_values("concentration_share", ascending=False).reset_index(drop=True)


def window_slice(daily: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    local = normalize_daily_nav(daily)
    return local.loc[(local["date"] >= pd.Timestamp(start)) & (local["date"] <= pd.Timestamp(end))].copy()


def build_window_definitions(daily: pd.DataFrame) -> list[dict[str, str]]:
    local = normalize_daily_nav(daily)
    rolling = rolling_12m_metrics(local)
    if not rolling.empty:
        strongest = rolling.sort_values("window_return", ascending=False).iloc[0]
        rolling_weakest = rolling.sort_values("calmar_like").iloc[0]
        rolling_weak_start = f"{rolling_weakest['start_month']}-01"
        rolling_weak_end = month_end(str(rolling_weakest["end_month"]))
        strong_start = f"{strongest['start_month']}-01"
        strong_end = month_end(str(strongest["end_month"]))
    else:
        rolling_weak_start, rolling_weak_end = WEAK_START, WEAK_END
        strong_start, strong_end = "2024-11-01", "2025-10-31"
    start = str(local["date"].min().date())
    end = str(local["date"].max().date())
    defs = [
        {"window_name": "full_period", "start": start, "end": end},
        {"window_name": "weakest_12m", "start": WEAK_START, "end": WEAK_END},
        {"window_name": "rolling_min_12m_observation", "start": rolling_weak_start, "end": rolling_weak_end},
        {"window_name": "strongest_12m", "start": strong_start, "end": strong_end},
        {"window_name": "2024", "start": "2024-01-01", "end": "2024-12-31"},
        {"window_name": "2025", "start": "2025-01-01", "end": "2025-12-31"},
        {"window_name": "2026", "start": "2026-01-01", "end": "2026-12-31"},
    ]
    return defs


def month_end(period: str) -> str:
    return str(pd.Period(period, freq="M").end_time.date())


def window_selection_attribution(daily: pd.DataFrame, weights: pd.DataFrame, contrib: pd.DataFrame, monthly_attr: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for spec in build_window_definitions(daily):
        local_daily = window_slice(daily, spec["start"], spec["end"])
        if local_daily.empty:
            continue
        start_ts = pd.Timestamp(spec["start"])
        end_ts = pd.Timestamp(spec["end"])
        local_weights = weights.loc[(weights.index >= start_ts) & (weights.index <= end_ts)].copy()
        local_contrib = contrib.loc[(contrib.index >= start_ts) & (contrib.index <= end_ts)].copy()
        metrics = strategy_metrics_from_daily(local_daily, local_weights)
        avg_weight = local_weights.abs().mean().sort_values(ascending=False) if not local_weights.empty else pd.Series(dtype=float)
        total_avg = float(avg_weight.sum())
        contrib_sum = local_contrib.sum().sort_values(ascending=False) if not local_contrib.empty else pd.Series(dtype=float)
        contrib_abs = local_contrib.abs().sum().sort_values(ascending=False) if not local_contrib.empty else pd.Series(dtype=float)
        month_mask = monthly_attr["month"].between(pd.Period(spec["start"], "M").strftime("%Y-%m"), pd.Period(spec["end"], "M").strftime("%Y-%m")) if not monthly_attr.empty else pd.Series(dtype=bool)
        local_monthly = monthly_attr.loc[month_mask].copy() if not monthly_attr.empty else pd.DataFrame()
        pos_profit = local_monthly.loc[local_monthly["monthly_profit"] > 0, "monthly_profit"].sum() if "monthly_profit" in local_monthly else 0.0
        top_month_share = float(local_monthly.loc[local_monthly["monthly_profit"] > 0, "monthly_profit"].max() / pos_profit) if pos_profit else 0.0
        high_beta_cols = [c for c in local_weights.columns if c in HIGH_BETA_TICKERS] if not local_weights.empty else []
        rows.append(
            {
                "window_name": spec["window_name"],
                "start": spec["start"],
                "end": spec["end"],
                "CAGR": metrics.get("cagr"),
                "Calmar": metrics.get("calmar"),
                "MaxDD": metrics.get("max_drawdown"),
                "selected_ticker_count": int((avg_weight > 1e-12).sum()) if not avg_weight.empty else 0,
                "top5_ticker_exposure_share": float(avg_weight.head(5).sum() / total_avg) if total_avg else 0.0,
                "high_beta_weight_share": float(local_weights[high_beta_cols].sum(axis=1).mean()) if high_beta_cols else 0.0,
                "top_month_contribution_share": top_month_share,
                "dominant_ticker_list": ",".join(map(str, contrib_abs.head(5).index.tolist())),
                "top_positive_contributor": str(contrib_sum.index[0]) if not contrib_sum.empty else "",
                "top_negative_contributor": str(contrib_sum.index[-1]) if not contrib_sum.empty else "",
                "top_abs_contribution_share": float(contrib_abs.iloc[0] / contrib_abs.sum()) if not contrib_abs.empty and contrib_abs.sum() else 0.0,
            }
        )
    return pd.DataFrame(rows)


def window_selection_detail(window_name: str, start: str, end: str, weights: pd.DataFrame, contrib: pd.DataFrame) -> pd.DataFrame:
    start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
    local_weights = weights.loc[(weights.index >= start_ts) & (weights.index <= end_ts)].copy()
    local_contrib = contrib.loc[(contrib.index >= start_ts) & (contrib.index <= end_ts)].copy()
    if local_weights.empty:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    contrib_month = local_contrib.copy()
    contrib_month["month"] = contrib_month.index.to_period("M").astype(str)
    monthly = contrib_month.groupby("month").sum(numeric_only=True)
    for ticker in local_weights.columns:
        avg_weight = float(local_weights[ticker].mean())
        if abs(avg_weight) <= 1e-12 and (ticker not in local_contrib.columns or abs(float(local_contrib[ticker].sum())) <= 1e-12):
            continue
        series = monthly[ticker] if ticker in monthly.columns else pd.Series(dtype=float)
        rows.append(
            {
                "window_name": window_name,
                "window_start": start,
                "window_end": end,
                "ticker": ticker,
                "avg_weight": avg_weight,
                "max_weight": float(local_weights[ticker].max()),
                "approximate_return_contribution": float(local_contrib[ticker].sum()) if ticker in local_contrib else 0.0,
                "abs_contribution": float(local_contrib[ticker].abs().sum()) if ticker in local_contrib else 0.0,
                "positive_month_count": int((series > 0).sum()) if not series.empty else 0,
                "negative_month_count": int((series < 0).sum()) if not series.empty else 0,
                "best_month": str(series.idxmax()) if not series.empty else "",
                "best_month_contribution": float(series.max()) if not series.empty else 0.0,
                "worst_month": str(series.idxmin()) if not series.empty else "",
                "worst_month_contribution": float(series.min()) if not series.empty else 0.0,
                "high_beta_flag": ticker in HIGH_BETA_TICKERS,
            }
        )
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values("abs_contribution", ascending=False).reset_index(drop=True)
    return out


def benchmark_window_returns(close: pd.DataFrame, start: str, end: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for ticker in ["QQQ", "SPY"]:
        if ticker not in close.columns:
            continue
        local = close[ticker].loc[(close.index >= pd.Timestamp(start)) & (close.index <= pd.Timestamp(end))].dropna()
        if len(local) > 1:
            out[f"{ticker}_window_return"] = float(local.iloc[-1] / local.iloc[0] - 1.0)
    return out


def build_root_cause(
    monthly_attr: pd.DataFrame,
    ticker_attr: pd.DataFrame,
    window_attr: pd.DataFrame,
    weak_detail: pd.DataFrame,
    strongest_detail: pd.DataFrame,
    rerank_feasibility: dict[str, Any],
    close: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    weak = window_attr.loc[window_attr["window_name"] == "weakest_12m"].head(1)
    strong = window_attr.loc[window_attr["window_name"] == "strongest_12m"].head(1)
    bench = benchmark_window_returns(close, WEAK_START, WEAK_END)
    weak_months = monthly_attr.loc[(monthly_attr["month"] >= "2024-04") & (monthly_attr["month"] <= "2025-03")].copy()
    worst_months = weak_months.sort_values("monthly_return").head(3)["month"].astype(str).tolist() if not weak_months.empty else []
    top_months = weak_months.sort_values("monthly_profit", ascending=False).head(3)["month"].astype(str).tolist() if not weak_months.empty else []
    weak_top3 = float(weak_months.loc[weak_months["monthly_profit"] > 0].sort_values("monthly_profit", ascending=False)["monthly_profit"].head(3).sum())
    weak_pos = float(weak_months.loc[weak_months["monthly_profit"] > 0, "monthly_profit"].sum())
    weak_top3_share = weak_top3 / weak_pos if weak_pos else 0.0
    weak_hb = float(weak["high_beta_weight_share"].iloc[0]) if not weak.empty else 0.0
    strong_hb = float(strong["high_beta_weight_share"].iloc[0]) if not strong.empty else 0.0
    weak_tickers = weak_detail.head(5)["ticker"].astype(str).tolist() if not weak_detail.empty else []
    strong_tickers = strongest_detail.head(5)["ticker"].astype(str).tolist() if not strongest_detail.empty else []
    top_ticker = ticker_attr.head(1)["ticker"].iloc[0] if not ticker_attr.empty else ""
    top_ticker_share = float(ticker_attr.head(1)["concentration_share"].iloc[0]) if not ticker_attr.empty else 0.0
    qqq_ret = bench.get("QQQ_window_return", np.nan)
    spy_ret = bench.get("SPY_window_return", np.nan)

    rows.append(
        {
            "root_cause_type": "top_month_concentration",
            "evidence": f"weakest 12M top3 positive month profit share is {weak_top3_share:.3f}; top months={','.join(top_months)}",
            "severity": "high",
            "affected_months": ",".join(top_months),
            "affected_tickers": ",".join(weak_tickers),
            "impact_estimate": f"weakest 12M Calmar remains below 1 despite positive window CAGR; positive profit depends on a few months",
            "whether_actionable_ex_ante": "partly",
            "recommended_fix": "Add top-month and ticker concentration penalties to stock-selection ranking, not a post-selection overlay.",
        }
    )
    rows.append(
        {
            "root_cause_type": "score_rank_audit_gap",
            "evidence": "Existing v8 artifacts keep selected tickers and selected scores only; full monthly candidate scores/ranks and unselected flags are not persisted.",
            "severity": "high",
            "affected_months": "all",
            "affected_tickers": "all candidate universe",
            "impact_estimate": "Cannot prove ex-ante reranking improvement or diagnose missed alternatives without rerunning/training.",
            "whether_actionable_ex_ante": "yes",
            "recommended_fix": "First add score/rank audit trail output to v8/v8.2 replay: one row per decision_date x tradable ticker with score, rank, selected_flag, lagged risk features.",
        }
    )
    rows.append(
        {
            "root_cause_type": "high_beta_style_exposure",
            "evidence": f"weakest high-beta avg weight share={weak_hb:.3f}; strongest high-beta avg weight share={strong_hb:.3f}; cycle 03-05 overlays lowered exposure but did not create a strong candidate.",
            "severity": "medium",
            "affected_months": "2024-04:2025-03",
            "affected_tickers": ",".join([t for t in weak_tickers if t in HIGH_BETA_TICKERS]),
            "impact_estimate": "High beta is a contributor but not a sufficient standalone fix; overlay evidence plateaued.",
            "whether_actionable_ex_ante": "yes",
            "recommended_fix": "Move beta/volatility controls into ranking: lower high-beta names only when their score edge does not compensate for lagged risk.",
        }
    )
    rows.append(
        {
            "root_cause_type": "dominant_ticker_dependency",
            "evidence": f"top full-period contribution concentration ticker={top_ticker}, abs contribution share={top_ticker_share:.3f}; weak-window dominant tickers={','.join(weak_tickers)}.",
            "severity": "medium",
            "affected_months": ",".join(worst_months + top_months),
            "affected_tickers": ",".join(weak_tickers),
            "impact_estimate": "The strategy remains sensitive to a small set of selected names even though max monthly weight is capped at 20%.",
            "whether_actionable_ex_ante": "yes",
            "recommended_fix": "Use rolling selected-count/contribution proxy and same-ticker repeat penalty in cross-sectional reranking.",
        }
    )
    rows.append(
        {
            "root_cause_type": "market_regime_not_sufficient_explanation",
            "evidence": f"QQQ weak-window return={qqq_ret:.3f} and SPY weak-window return={spy_ret:.3f} when available; cycle 05 market regime overlay improved drawdown but not strong-candidate gates.",
            "severity": "medium",
            "affected_months": "2024-04:2025-03",
            "affected_tickers": "portfolio",
            "impact_estimate": "The weak window is not solved by broad de-risking; stock choice inside the regime matters more than cash scaling.",
            "whether_actionable_ex_ante": "yes",
            "recommended_fix": "Use regime as a ranking conditioner, not a portfolio-level scale. Penalize high-vol/high-beta candidates under weak QQQ/SPY regimes.",
        }
    )
    rows.append(
        {
            "root_cause_type": "existing_score_reranking_blocked",
            "evidence": f"can_do_ex_ante_reranking={rerank_feasibility.get('can_do_ex_ante_reranking')}; missing={';'.join(rerank_feasibility.get('missing_files', []))}",
            "severity": "high",
            "affected_months": "all",
            "affected_tickers": "unselected candidates",
            "impact_estimate": "No safe light reranking simulation was run in this diagnostic.",
            "whether_actionable_ex_ante": "yes",
            "recommended_fix": rerank_feasibility.get("recommended_next_action", ""),
        }
    )
    return pd.DataFrame(rows)


def analyze_reranking_feasibility(run_dir: Path, inventory: pd.DataFrame, ledger: pd.DataFrame, holdings: pd.DataFrame) -> dict[str, Any]:
    files = inventory.loc[inventory["exists"] == True, "file_path"].astype(str).tolist() if not inventory.empty else []
    names = [Path(p).name.lower() for p in files]
    has_candidate_file = any("candidate" in n or "universe" in n for n in names)
    has_prediction_file = any("prediction" in n or "pred" in n for n in names)
    has_rank_file = any("rank" in n for n in names)
    has_feature_cache = any("alpha360_cache.parquet" in n or "alpha158_cache.parquet" in n for n in names)
    selected_scores_only = bool("selected_scores" in ledger.columns and "selected_tickers" in ledger.columns)
    missing = []
    if not has_candidate_file:
        missing.append("monthly_candidate_universe_with_unselected_tickers")
    if not has_prediction_file:
        missing.append("raw_monthly_prediction_scores_for_all_tradable_tickers")
    if not has_rank_file:
        missing.append("rank_before_selection_for_all_tradable_tickers")
    missing.append("selected_flag_and_forward_return_for_unselected_candidates")
    can_ex_ante = bool(has_candidate_file and has_prediction_file and has_rank_file)
    return {
        "has_monthly_candidate_universe": bool(has_candidate_file),
        "has_raw_prediction_score": bool(has_prediction_file),
        "has_rank_before_selection": bool(has_rank_file),
        "has_selected_flag": bool(False),
        "has_forward_return": bool(has_feature_cache),
        "has_selected_only_scores": selected_scores_only,
        "selected_score_source": str(run_dir / "v8_paper_trading" / "monthly_decision_ledger.csv") if selected_scores_only else "",
        "can_do_ex_post_reranking": False,
        "can_do_ex_ante_reranking": can_ex_ante,
        "missing_files": missing,
        "recommended_next_action": "Do not run reranking replay yet. Patch v8/v8.2 replay to persist monthly candidate score/rank audit trail before any stock-selection reranking simulation.",
    }


def ranking_improvement_design() -> pd.DataFrame:
    rows = [
        {
            "proposal_name": "A_concentration_aware_reranking",
            "required_inputs": "monthly full candidate score/rank, selected history through t-1, ticker exposure/contribution proxies",
            "ex_ante_feasible": True,
            "expected_benefit": "Reduce dominant ticker and top-month dependence without changing model training.",
            "expected_cost": "May give up some explosive winners and lower full-period CAGR.",
            "implementation_complexity": "medium",
            "lookahead_risk": "low if selected history and realized returns are lagged to t-1",
            "recommended_priority": 1,
            "suggested_next_script": "39_add_v8_2_score_rank_audit_trail_then_rerank_replay.py",
        },
        {
            "proposal_name": "B_risk_adjusted_score",
            "required_inputs": "monthly full scores plus trailing volatility/downside volatility/beta computed up to t-1",
            "ex_ante_feasible": True,
            "expected_benefit": "Prefer score per unit of risk and target weakest-window drawdown/cost fragility.",
            "expected_cost": "Can underweight high-conviction momentum names during strong tapes.",
            "implementation_complexity": "medium",
            "lookahead_risk": "low if all risk features are lagged",
            "recommended_priority": 2,
            "suggested_next_script": "39_add_v8_2_score_rank_audit_trail_then_rerank_replay.py",
        },
        {
            "proposal_name": "C_regime_conditional_ranking",
            "required_inputs": "monthly scores, QQQ/SPY lagged regime state, candidate beta/volatility through t-1",
            "ex_ante_feasible": True,
            "expected_benefit": "Use market regime to choose different stocks rather than bluntly lowering total exposure.",
            "expected_cost": "More degrees of freedom; needs strict parameter limits.",
            "implementation_complexity": "medium_high",
            "lookahead_risk": "medium unless regime and candidate risk are explicitly shifted",
            "recommended_priority": 3,
            "suggested_next_script": "40_v8_2_regime_conditional_ranking_sample.py",
        },
        {
            "proposal_name": "D_stability_ensemble_ranking",
            "required_inputs": "monthly scores across horizons/models or saved challenger scores, score volatility across recent fits",
            "ex_ante_feasible": True,
            "expected_benefit": "Lower reliance on one unstable ElasticNet score and reduce single-month bursts.",
            "expected_cost": "Needs score audit trail from multiple models/horizons; may require extra computation later.",
            "implementation_complexity": "high",
            "lookahead_risk": "low if only historical score dispersion is used",
            "recommended_priority": 4,
            "suggested_next_script": "41_v8_2_score_stability_audit.py",
        },
        {
            "proposal_name": "E_longer_history_training_split",
            "required_inputs": "longer clean daily history, consistent features, explicit train/valid/test chronology",
            "ex_ante_feasible": True,
            "expected_benefit": "Expose model to more regimes and reduce overfit to 2024-2026 behavior.",
            "expected_cost": "Not a light diagnostic; may require data work before any v9-like expansion.",
            "implementation_complexity": "high",
            "lookahead_risk": "medium if validation split is not frozen before search",
            "recommended_priority": 5,
            "suggested_next_script": "research_design_only_until_user_approval",
        },
    ]
    return pd.DataFrame(rows)


def skipped_reranking_outputs(feasibility: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    sim = pd.DataFrame(
        [
            {
                "simulation_id": "not_run",
                "status": "skipped",
                "reason": "missing ex-ante monthly full score/rank audit trail",
                "can_do_ex_ante_reranking": feasibility.get("can_do_ex_ante_reranking"),
                "can_do_ex_post_reranking": feasibility.get("can_do_ex_post_reranking"),
            }
        ]
    )
    verdict = {
        "light_reranking_simulation_run": False,
        "reason": "本轮未做 reranking simulation，原因是缺少 ex-ante monthly score/rank 留痕。",
        "lookahead_risk_if_forced": "high",
        "required_before_simulation": feasibility.get("missing_files", []),
    }
    return sim, verdict


def write_reports(
    timestamp: str,
    out_dir: Path,
    inventory: pd.DataFrame,
    monthly_attr: pd.DataFrame,
    ticker_attr: pd.DataFrame,
    window_attr: pd.DataFrame,
    weak_root: pd.DataFrame,
    feasibility: dict[str, Any],
    design: pd.DataFrame,
    sim_verdict: dict[str, Any],
    verdict: dict[str, Any],
) -> tuple[Path, Path, Path]:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = DOCS_DIR / f"US_STOCK_SELECTION_V8_2_STOCK_SELECTION_LAYER_DIAGNOSTIC_{timestamp}.md"
    summary_path = DOCS_DIR / f"US_STOCK_SELECTION_V8_2_STOCK_SELECTION_EXEC_SUMMARY_{timestamp}.md"
    transition_path = DOCS_DIR / f"US_STOCK_SELECTION_V8_1_OVERLAY_PLATEAU_TO_V8_2_STOCK_SELECTION_TRANSITION_{timestamp}.md"

    inv_summary = pd.DataFrame(
        [
            {
                "files_checked": int(len(inventory)),
                "usable_for_attribution": int(inventory["usable_for_attribution"].sum()) if not inventory.empty else 0,
                "usable_for_ranking_diagnostic": int(inventory["usable_for_ranking_diagnostic"].sum()) if not inventory.empty else 0,
                "score_rank_available": bool(feasibility.get("can_do_ex_ante_reranking")),
            }
        ]
    )
    top_tickers = ticker_attr.head(10).copy()
    windows = window_attr.copy()
    weak_causes = weak_root.copy()

    report = f"""# US Stock Selection v8.2 Stock-Selection Layer Diagnostic

## Scope

This is not v9. No universe expansion, no 31b, no model retraining, no new long full replay, and no continuation of v8.1 overlays.

## 1. File And Field Inventory

{table_to_markdown(inv_summary)}

Key finding: v8 persists selected holdings and selected scores, but does not persist full monthly candidate score/rank rows for unselected tradable names.

## 2. Stock-Selection Attribution

Monthly attribution sample:

{table_to_markdown(monthly_attr, columns=['month','monthly_return','monthly_profit','selected_ticker_count','high_beta_weight_share','top_weight_ticker','best_contributing_ticker','worst_contributing_ticker','turnover'], max_rows=30)}

Ticker attribution top rows:

{table_to_markdown(top_tickers, columns=['ticker','selected_month_count','avg_weight','max_weight','approximate_return_contribution','positive_month_count','negative_month_count','high_beta_flag','concentration_share'])}

## 3. Weakest 12M Root Cause

{table_to_markdown(weak_causes, columns=['root_cause_type','severity','evidence','whether_actionable_ex_ante','recommended_fix'], max_rows=20)}

## 4. Strongest 12M Comparison

{table_to_markdown(windows, columns=['window_name','start','end','CAGR','Calmar','MaxDD','selected_ticker_count','top5_ticker_exposure_share','high_beta_weight_share','top_month_contribution_share','dominant_ticker_list'])}

## 5. Existing-Score Reranking Feasibility

```json
{json.dumps(to_jsonable(feasibility), indent=2, ensure_ascii=False)}
```

## 6. Light Reranking Simulation

```json
{json.dumps(to_jsonable(sim_verdict), indent=2, ensure_ascii=False)}
```

## 7. v8.2 Ranking Improvement Design

{table_to_markdown(design, max_rows=10)}

## 8. Final Judgment

- Overlay line stopped: `{verdict['overlay_line_stopped']}`
- v8 baseline remains current best: `{verdict['v8_baseline_remains_best']}`
- v8 verdict remains: `{verdict['v8_current_classification']}`
- allow_enter_v9: `{verdict['allow_enter_v9']}`
- Recommended next action: `{verdict['recommended_next_action']}`

## 9. Outputs

- Output directory: `{out_dir}`
- Zip: `{verdict['zip_path']}`
"""
    report_path.write_text(report, encoding="utf-8")

    summary = f"""# US Stock Selection v8.2 Stock-Selection Exec Summary

- Branch: `v8.2 stock-selection layer root-cause diagnostic`
- Overlay line: stopped / plateau
- v8 baseline remains best: `{verdict['v8_baseline_remains_best']}`
- Current classification: `{verdict['v8_current_classification']}`
- allow_enter_v9: `{verdict['allow_enter_v9']}`
- Ex-ante monthly score/rank available: `{feasibility.get('can_do_ex_ante_reranking')}`
- Light reranking simulation: `{sim_verdict.get('light_reranking_simulation_run')}`
- Main blocker: full monthly candidate score/rank audit trail is missing.
- Recommended next: `{verdict['recommended_next_action']}`

## Window Snapshot

{table_to_markdown(windows, columns=['window_name','CAGR','Calmar','MaxDD','high_beta_weight_share','top_month_contribution_share','dominant_ticker_list'])}
"""
    summary_path.write_text(summary, encoding="utf-8")

    transition = f"""# v8.1 Overlay Plateau To v8.2 Stock-Selection Transition

v8.1 overlay evolution is complete and should not continue. High-beta soft-cap, NAV throttle, and QQQ/SPY market-regime overlays improved some risk metrics but did not solve weakest 12M, cost-after-return, and top-month concentration gates.

The active branch is now v8.2 stock-selection layer diagnostic. The immediate blocker is not another overlay; it is missing score/rank auditability for the full monthly tradable candidate set.

Next approved direction should be one of:

1. Patch v8/v8.2 to persist monthly candidate score/rank audit trail.
2. Then run a bounded v8.2 gate-aware reranking replay.
3. If score/rank audit shows model instability rather than ranking concentration, redesign train/validation split before any v9 discussion.

No v9, no universe expansion, no 31b, and no model retraining were performed in this diagnostic.
"""
    transition_path.write_text(transition, encoding="utf-8")
    shutil.copy2(report_path, out_dir / "reports" / report_path.name)
    shutil.copy2(summary_path, out_dir / "reports" / summary_path.name)
    shutil.copy2(transition_path, out_dir / "reports" / transition_path.name)
    return report_path, summary_path, transition_path


def update_next_steps(timestamp: str, out_dir: Path, zip_path: Path, feasibility: dict[str, Any], verdict: dict[str, Any]) -> None:
    next_path = PROJECT_ROOT / "NEXT_STEPS.md"
    previous = next_path.read_text(encoding="utf-8") if next_path.exists() else "# NEXT_STEPS\n"
    section = f"""

## v8.2 stock-selection layer root-cause diagnostic

- 执行状态：completed，随后按要求暂停，不自动进入下一轮。
- 输出目录：`{out_dir}`
- zip：`{zip_path}`
- v8.1 overlay plateau：已确认停止，不继续 high-beta soft-cap / NAV throttle / QQQ MA200 overlay。
- v8 baseline 是否仍是当前 best：`{verdict['v8_baseline_remains_best']}`
- 当前分类：`{verdict['v8_current_classification']}`
- allow_enter_v9：`{verdict['allow_enter_v9']}`
- 是否扩 universe：`False`
- 是否训练新模型：`False`
- 是否运行 31b：`False`
- 是否存在 ex-ante monthly score/rank 留痕：`{feasibility.get('can_do_ex_ante_reranking')}`
- 本轮主要发现：已有 v8 输出可做 holdings/trade/nav 层近似归因，但没有保存完整每月候选池、原始预测分数、全量排名和未入选标的 selected_flag，因此不能安全执行选股层 reranking simulation。
- 下一步建议：先补 `monthly candidate score/rank audit trail`，再做 v8.2 gate-aware reranking replay；不要进入 v9，不扩池。
- 是否需要用户/ChatGPT 决策：`True`，需要批准先补 score/rank 留痕，还是转向更长历史/训练验证切分设计。
"""
    next_path.write_text(previous.rstrip() + "\n" + section, encoding="utf-8")


def write_run_summary(out_dir: Path, zip_path: Path, verdict: dict[str, Any], feasibility: dict[str, Any]) -> None:
    text = f"""# RUN_SUMMARY

本轮目标：v8.2 stock-selection layer root-cause diagnostic。

新 run 目录：`{out_dir}`

zip：`{zip_path}`

当前分类：`{verdict['v8_current_classification']}`

是否允许进入 v9：`{verdict['allow_enter_v9']}`

是否替代当前 best：`False`

是否继续 v8.1 overlay：`False`

是否重训模型：`False`

是否扩 universe：`False`

是否运行 31b：`False`

是否存在 ex-ante monthly score/rank 留痕：`{feasibility.get('can_do_ex_ante_reranking')}`

轻量 reranking simulation：`not_run_missing_score_rank_audit_trail`

后续：先补全每月候选池/score/rank/selected_flag 留痕，再决定是否做 v8.2 gate-aware reranking replay。
"""
    (out_dir / "RUN_SUMMARY.md").write_text(text, encoding="utf-8")
    (PROJECT_ROOT / "RUN_SUMMARY.md").write_text(text, encoding="utf-8")


def package_outputs(out_dir: Path, docs: list[Path], zip_path: Path) -> None:
    files: list[Path] = [
        PROJECT_ROOT / "scripts" / "us_stock_selection" / "38_analyze_v8_stock_selection_layer.py",
        PROJECT_ROOT / "NEXT_STEPS.md",
        PROJECT_ROOT / "RUN_SUMMARY.md",
    ]
    files.extend(docs)
    files.extend([p for p in out_dir.rglob("*") if p.is_file()])
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        seen: set[str] = set()
        for path in files:
            if not path.exists():
                continue
            arcname = str(path.relative_to(PROJECT_ROOT)) if path.is_relative_to(PROJECT_ROOT) else path.name
            if arcname in seen:
                continue
            seen.add(arcname)
            zf.write(path, arcname)


def main() -> None:
    args = parse_args()
    timestamp = args.timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = args.out_dir or (OUTPUT_ROOT / f"v8_2_stock_selection_layer_diagnostic_{timestamp}")
    (out_dir / "reports").mkdir(parents=True, exist_ok=True)
    logger = setup_logger(out_dir)
    logger.info("Starting v8.2 stock-selection diagnostic. out_dir=%s", out_dir)
    logger.info("Boundaries: no v9, no universe expansion, no retraining, no 31b, no overlay evolution.")

    inventory = build_data_inventory(args.run_dir, args.cycle05_dir)
    inventory.to_csv(out_dir / "cycle_v8_2_data_inventory.csv", index=False, encoding="utf-8-sig")
    if args.dry_run:
        logger.info("Dry-run requested; stopping after data inventory.")
        return

    inputs = load_core_inputs(args.run_dir, logger)
    daily = inputs["daily"]
    holdings = inputs["holdings"]
    trades = inputs["trades"]
    ledger = inputs["ledger"]
    close = load_close_for_attribution(args.provider_uri, holdings, daily, logger)
    weights = build_weights_from_holdings(close, holdings)
    weights = weights.reindex(pd.to_datetime(daily["date"])).ffill().fillna(0.0)
    weights.index = pd.to_datetime(daily["date"])
    close = close.reindex(weights.index).ffill()
    contrib = compute_contribution_panel(close, weights)

    monthly_attr = monthly_selection_attribution(daily, weights, holdings, trades, contrib)
    ticker_attr = ticker_selection_attribution(holdings, contrib)
    window_attr = window_selection_attribution(daily, weights, contrib, monthly_attr)
    weakest_row = window_attr.loc[window_attr["window_name"] == "weakest_12m"].head(1)
    strongest_row = window_attr.loc[window_attr["window_name"] == "strongest_12m"].head(1)
    weak_start = str(weakest_row["start"].iloc[0]) if not weakest_row.empty else WEAK_START
    weak_end = str(weakest_row["end"].iloc[0]) if not weakest_row.empty else WEAK_END
    strong_start = str(strongest_row["start"].iloc[0]) if not strongest_row.empty else "2024-11-01"
    strong_end = str(strongest_row["end"].iloc[0]) if not strongest_row.empty else "2025-10-31"
    weak_detail = window_selection_detail("weakest_12m", weak_start, weak_end, weights, contrib)
    strong_detail = window_selection_detail("strongest_12m", strong_start, strong_end, weights, contrib)
    feasibility = analyze_reranking_feasibility(args.run_dir, inventory, ledger, holdings)
    root_cause = build_root_cause(monthly_attr, ticker_attr, window_attr, weak_detail, strong_detail, feasibility, close)
    design = ranking_improvement_design()
    sim, sim_verdict = skipped_reranking_outputs(feasibility)

    monthly_attr.to_csv(out_dir / "cycle_v8_2_monthly_selection_attribution.csv", index=False, encoding="utf-8-sig")
    ticker_attr.to_csv(out_dir / "cycle_v8_2_ticker_selection_attribution.csv", index=False, encoding="utf-8-sig")
    window_attr.to_csv(out_dir / "cycle_v8_2_window_selection_attribution.csv", index=False, encoding="utf-8-sig")
    weak_detail.to_csv(out_dir / "cycle_v8_2_weakest_12m_selection_detail.csv", index=False, encoding="utf-8-sig")
    strong_detail.to_csv(out_dir / "cycle_v8_2_strongest_12m_selection_detail.csv", index=False, encoding="utf-8-sig")
    root_cause.to_csv(out_dir / "cycle_v8_2_weak_window_root_cause.csv", index=False, encoding="utf-8-sig")
    write_json(feasibility, out_dir / "cycle_v8_2_reranking_feasibility.json")
    design.to_csv(out_dir / "cycle_v8_2_ranking_improvement_design.csv", index=False, encoding="utf-8-sig")
    sim.to_csv(out_dir / "cycle_v8_2_light_reranking_simulation.csv", index=False, encoding="utf-8-sig")
    write_json(sim_verdict, out_dir / "cycle_v8_2_light_reranking_verdict.json")

    zip_path = OUTPUT_ROOT / f"us_stock_selection_quant_lab_v8_2_stock_selection_layer_diagnostic_{timestamp}.zip"
    verdict = {
        "cycle_id": "v8.2_stock_selection_layer_diagnostic",
        "run_dir": str(args.run_dir),
        "out_dir": str(out_dir),
        "zip_path": str(zip_path),
        "overlay_line_stopped": True,
        "v8_baseline_remains_best": True,
        "v8_current_classification": BASELINE_METRICS["verdict"],
        "allow_enter_v9": False,
        "expanded_universe": False,
        "trained_new_model": False,
        "ran_31b": False,
        "continued_v8_1_overlay": False,
        "light_reranking_simulation_run": False,
        "score_rank_audit_trail_available": bool(feasibility.get("can_do_ex_ante_reranking")),
        "root_cause_summary": "Holdings/trade/nav attribution is possible, but full stock-selection reranking diagnosis is blocked by missing full monthly score/rank audit trail.",
        "recommended_next_action": "Patch v8/v8.2 to persist monthly candidate score/rank audit trail, then run a bounded gate-aware reranking replay before any v9 or universe expansion.",
    }
    write_json(verdict, out_dir / "cycle_v8_2_verdict.json")

    report_path, summary_path, transition_path = write_reports(
        timestamp=timestamp,
        out_dir=out_dir,
        inventory=inventory,
        monthly_attr=monthly_attr,
        ticker_attr=ticker_attr,
        window_attr=window_attr,
        weak_root=root_cause,
        feasibility=feasibility,
        design=design,
        sim_verdict=sim_verdict,
        verdict=verdict,
    )
    update_next_steps(timestamp, out_dir, zip_path, feasibility, verdict)
    write_run_summary(out_dir, zip_path, verdict, feasibility)
    package_outputs(out_dir, [report_path, summary_path, transition_path], zip_path)
    logger.info("v8.2 diagnostic packaged: %s", zip_path)


if __name__ == "__main__":
    main()
