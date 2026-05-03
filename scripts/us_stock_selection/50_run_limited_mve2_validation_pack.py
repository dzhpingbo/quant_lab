#!/usr/bin/env python
"""Build a limited MVE2 validation pack for frozen candidates.

This script validates a fixed candidate list from the prior limited MVE2
screen. It is intentionally not a new search:
- no universe expansion
- no excluded tickers
- no ML training
- no formal MVE2/v9
- no broad parameter grid
- prices/signals use only unified-store date, adj_close, volume
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd


RUN_SCOPE = "limited_mve2_validation"
TRADING_DAYS = 252
DEFAULT_STORE_DIR = Path("data/unified_ohlcv/us_stock_selection")
DEFAULT_PRIOR_DIR = Path("outputs/us_stock_selection/limited_mve2_20260502_142702")
DEFAULT_OUTPUT_ROOT = Path("outputs/us_stock_selection")
MIN_SLICE_DAYS = 20


@dataclass(frozen=True)
class FrozenCandidate:
    ticker: str
    strategy_name: str
    strategy_family: str
    params: Dict[str, object]
    role: str
    notes: str


FROZEN_CANDIDATES: List[FrozenCandidate] = [
    FrozenCandidate("NVDA", "sma50_200_cooldown_5_confirm_1", "cooldown_confirmation", {"fast": 50, "slow": 200, "cooldown": 5, "confirm": 1}, "main_candidate", "Layer1 risk-adjusted candidate"),
    FrozenCandidate("NVDA", "ts_mom_63d", "time_series_momentum", {"window": 63}, "main_candidate", "Layer1 return-max candidate"),
    FrozenCandidate("SOXX", "sma_20_120", "sma_trend_following", {"fast": 20, "slow": 120}, "main_candidate", "Layer3 sector/theme ETF candidate"),
    FrozenCandidate("UPRO", "vol_filter_63d", "volatility_filter", {"window": 63, "threshold_window": 252, "requires_positive_63d_momentum": True}, "leveraged_bucket_candidate", "Layer4 leveraged ETF separate-bucket candidate"),
    FrozenCandidate("SPY", "vol_filter_63d", "volatility_filter", {"window": 63, "threshold_window": 252, "requires_positive_63d_momentum": True}, "defensive_candidate", "Core ETF defensive candidate"),
    FrozenCandidate("GOOGL", "vol_filter_20d", "volatility_filter", {"window": 20, "threshold_window": 252, "requires_positive_63d_momentum": True}, "main_candidate", "Layer1 conservative risk-control candidate"),
    FrozenCandidate("MSFT", "sma_50_200", "sma_trend_following", {"fast": 50, "slow": 200}, "main_candidate", "Layer1 stable mega-cap candidate"),
    FrozenCandidate("MSTR", "sma50_200_cooldown_10_confirm_2", "cooldown_confirmation", {"fast": 50, "slow": 200, "cooldown": 10, "confirm": 2}, "observation_only", "High-beta observation only; does not represent Layer5"),
    FrozenCandidate("QQQ", "trailing_stop_15pct", "drawdown_trailing_stop_filter", {"stop": 0.15}, "negative_case_observation", "Risk observation: prior neighborhood cliff case"),
]


class RunLogger:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("", encoding="utf-8")

    def log(self, message: str) -> None:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{stamp}] {message}"
        print(line)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run limited MVE2 validation pack for frozen candidates.")
    parser.add_argument("--store-dir", type=Path, default=DEFAULT_STORE_DIR)
    parser.add_argument("--prior-limited-mve2-dir", type=Path, default=DEFAULT_PRIOR_DIR)
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--timestamp", type=str, default=None)
    parser.add_argument("--no-zip", action="store_true")
    return parser.parse_args()


def read_prior_results(prior_dir: Path) -> pd.DataFrame:
    path = prior_dir / "all_strategy_results_limited_mve2.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing prior limited MVE2 results: {path}")
    df = pd.read_csv(path)
    required = {"ticker", "strategy_name", "bucket_id", "bucket", "strategy_family", "parameters"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Prior results missing columns: {sorted(missing)}")
    return df


def find_prior_row(prior: pd.DataFrame, cand: FrozenCandidate) -> Dict[str, object]:
    rows = prior[(prior["ticker"] == cand.ticker) & (prior["strategy_name"] == cand.strategy_name)]
    if rows.empty:
        raise ValueError(f"Frozen candidate not found in prior results: {cand.ticker} / {cand.strategy_name}")
    if len(rows) > 1:
        rows = rows.head(1)
    return rows.iloc[0].to_dict()


def read_price(store_dir: Path, ticker: str) -> pd.DataFrame:
    path = store_dir / "prices" / f"{ticker}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Missing unified-store parquet for {ticker}: {path}")
    df = pd.read_parquet(path)
    required = {"date", "adj_close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{ticker} price file missing columns: {sorted(missing)}")
    out = df[["date", "adj_close", "volume"]].copy()
    out["date"] = pd.to_datetime(out["date"])
    out["adj_close"] = pd.to_numeric(out["adj_close"], errors="coerce")
    out["volume"] = pd.to_numeric(out["volume"], errors="coerce")
    out = out.dropna(subset=["date", "adj_close", "volume"])
    out = out[(out["adj_close"] > 0) & (out["volume"] >= 0)]
    out = out.drop_duplicates("date").sort_values("date").reset_index(drop=True)
    out["return"] = out["adj_close"].pct_change().fillna(0.0)
    if out.empty:
        raise ValueError(f"No usable adj_close/volume data for {ticker}")
    return out


def align_price_data(price_data: Dict[str, pd.DataFrame], start: pd.Timestamp, end: pd.Timestamp) -> Dict[str, pd.DataFrame]:
    aligned = {}
    for ticker, df in price_data.items():
        out = df[(df["date"] >= start) & (df["date"] <= end)].copy().reset_index(drop=True)
        out["return"] = out["adj_close"].pct_change().fillna(0.0)
        aligned[ticker] = out
    return aligned


def common_window(price_data: Dict[str, pd.DataFrame], prior_dir: Path) -> Tuple[pd.Timestamp, pd.Timestamp]:
    config_path = prior_dir / "limited_mve2_run_config.json"
    if config_path.exists():
        config = json.loads(config_path.read_text(encoding="utf-8"))
        return pd.Timestamp(config["common_start"]), pd.Timestamp(config["common_end"])
    start = max(df["date"].min() for df in price_data.values())
    end = min(df["date"].max() for df in price_data.values())
    return max(start, pd.Timestamp("2016-01-01")), end


def run_sma(df: pd.DataFrame, params: Dict[str, object]) -> pd.Series:
    fast = int(params["fast"])
    slow = int(params["slow"])
    price = df["adj_close"]
    signal = price.rolling(fast, min_periods=fast).mean() > price.rolling(slow, min_periods=slow).mean()
    return signal.astype(float).fillna(0.0)


def run_time_series_momentum(df: pd.DataFrame, params: Dict[str, object]) -> pd.Series:
    window = int(params["window"])
    signal = df["adj_close"].pct_change(window) > 0
    return signal.astype(float).fillna(0.0)


def run_volatility_filter(df: pd.DataFrame, params: Dict[str, object]) -> pd.Series:
    window = int(params["window"])
    threshold_window = int(params.get("threshold_window", 252))
    ret = df["return"]
    vol = ret.rolling(window, min_periods=window).std() * math.sqrt(TRADING_DAYS)
    threshold = vol.rolling(threshold_window, min_periods=max(30, min(60, threshold_window // 2))).median()
    signal = vol <= threshold
    if bool(params.get("requires_positive_63d_momentum", True)):
        signal = signal & (df["adj_close"].pct_change(63) > 0)
    return signal.astype(float).fillna(0.0)


def run_drawdown_stop(df: pd.DataFrame, params: Dict[str, object]) -> pd.Series:
    stop = float(params["stop"])
    price = df["adj_close"]
    drawdown = price / price.cummax() - 1.0
    signal = drawdown >= -stop
    return signal.astype(float).fillna(0.0)


def apply_confirm_cooldown(raw_signal: pd.Series, confirm_days: int, cooldown_days: int) -> pd.Series:
    raw_bool = raw_signal.astype(bool).fillna(False).to_numpy()
    out = np.zeros(len(raw_bool), dtype=float)
    in_position = False
    cooldown_left = 0
    true_streak = 0
    for i, flag in enumerate(raw_bool):
        true_streak = true_streak + 1 if flag else 0
        if in_position:
            if not flag:
                in_position = False
                cooldown_left = cooldown_days
        else:
            if cooldown_left > 0:
                cooldown_left -= 1
            elif flag and true_streak >= confirm_days + 1:
                in_position = True
        out[i] = 1.0 if in_position else 0.0
    return pd.Series(out, index=raw_signal.index)


def run_cooldown_confirmation(df: pd.DataFrame, params: Dict[str, object]) -> pd.Series:
    raw = run_sma(df, params)
    return apply_confirm_cooldown(raw, int(params.get("confirm", 0)), int(params.get("cooldown", 0)))


def generate_signal(df: pd.DataFrame, family: str, params: Dict[str, object]) -> pd.Series:
    if family == "sma_trend_following":
        return run_sma(df, params)
    if family == "cooldown_confirmation":
        return run_cooldown_confirmation(df, params)
    if family == "time_series_momentum":
        return run_time_series_momentum(df, params)
    if family == "volatility_filter":
        return run_volatility_filter(df, params)
    if family == "drawdown_trailing_stop_filter":
        return run_drawdown_stop(df, params)
    raise ValueError(f"Unsupported frozen strategy family: {family}")


def gross_strategy_returns(df: pd.DataFrame, position: pd.Series) -> pd.Series:
    shifted = position.fillna(0.0).shift(1).fillna(0.0)
    return shifted * df["return"].fillna(0.0)


def net_returns_with_cost(df: pd.DataFrame, position: pd.Series, cost_bps: float) -> Tuple[pd.Series, pd.Series]:
    gross = gross_strategy_returns(df, position)
    turnover = position.fillna(0.0).diff().abs().fillna(position.iloc[0] if len(position) else 0.0)
    cost = turnover * (cost_bps / 10000.0)
    return gross - cost, turnover


def max_drawdown(equity: pd.Series) -> Tuple[float, int, int]:
    peak = equity.cummax()
    dd = equity / peak - 1.0
    trough = int(dd.idxmin())
    peak_idx = int(equity.loc[:trough].idxmax())
    return float(dd.min()), peak_idx, trough


def avg_holding_days(position: pd.Series) -> float:
    values = position.fillna(0.0).astype(int).to_numpy()
    lengths = []
    cur = 0
    for value in values:
        if value == 1:
            cur += 1
        elif cur > 0:
            lengths.append(cur)
            cur = 0
    if cur > 0:
        lengths.append(cur)
    return float(np.mean(lengths)) if lengths else 0.0


def compute_metrics(dates: pd.Series, returns: pd.Series, position: pd.Series) -> Dict[str, object]:
    returns = returns.fillna(0.0).reset_index(drop=True)
    position = position.fillna(0.0).reset_index(drop=True)
    dates = pd.to_datetime(dates).reset_index(drop=True)
    n = int(len(returns))
    if n <= 1:
        return {
            "start_date": "",
            "end_date": "",
            "n_trading_days": n,
            "CAGR": np.nan,
            "max_drawdown": np.nan,
            "Calmar": np.nan,
            "Sharpe": np.nan,
            "total_return": np.nan,
            "turnover": np.nan,
            "trade_count": 0,
            "exposure_ratio": np.nan,
        }
    equity = (1.0 + returns).cumprod()
    years = n / TRADING_DAYS
    total = float(equity.iloc[-1] - 1.0)
    cagr = float(equity.iloc[-1] ** (1.0 / years) - 1.0) if years > 0 and equity.iloc[-1] > 0 else np.nan
    ann_ret = float(returns.mean() * TRADING_DAYS)
    ann_vol = float(returns.std(ddof=0) * math.sqrt(TRADING_DAYS))
    sharpe = float(ann_ret / ann_vol) if ann_vol > 0 else np.nan
    mdd, peak_idx, trough_idx = max_drawdown(equity)
    calmar = float(cagr / abs(mdd)) if pd.notna(cagr) and mdd < 0 else np.nan
    turnover_daily = position.diff().abs().fillna(position.iloc[0] if len(position) else 0.0)
    return {
        "start_date": dates.iloc[0].date().isoformat(),
        "end_date": dates.iloc[-1].date().isoformat(),
        "n_trading_days": n,
        "CAGR": cagr,
        "annual_return": ann_ret,
        "annual_volatility": ann_vol,
        "Sharpe": sharpe,
        "max_drawdown": mdd,
        "Calmar": calmar,
        "total_return": total,
        "turnover": float(turnover_daily.sum() / years) if years > 0 else np.nan,
        "trade_count": int((turnover_daily > 0).sum()),
        "exposure_ratio": float(position.mean()),
        "average_holding_days": avg_holding_days(position),
        "mdd_peak_date": dates.iloc[peak_idx].date().isoformat(),
        "mdd_trough_date": dates.iloc[trough_idx].date().isoformat(),
    }


def candidate_key(cand: FrozenCandidate) -> str:
    return f"{cand.ticker}/{cand.strategy_name}"


def primary_benchmark(bucket_id: str, ticker: str) -> str:
    if bucket_id == "Bucket B":
        return "SPY" if ticker != "SPY" else "QQQ"
    return "QQQ"


def bucket_benchmark(bucket_id: str, ticker: str) -> str:
    if bucket_id == "Bucket B":
        return "SPY"
    if bucket_id == "Bucket C":
        return "QQQ"
    if bucket_id == "Bucket D":
        return "QQQ"
    if bucket_id == "Bucket E":
        return "SPY"
    if bucket_id == "Bucket F":
        return "QQQ"
    return "QQQ"


def build_frozen_candidates(prior: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for cand in FROZEN_CANDIDATES:
        prior_row = find_prior_row(prior, cand)
        row = {
            "run_scope": RUN_SCOPE,
            "candidate_key": candidate_key(cand),
            "ticker": cand.ticker,
            "strategy_name": cand.strategy_name,
            "strategy_family": cand.strategy_family,
            "parameters": json.dumps(cand.params, sort_keys=True),
            "role": cand.role,
            "freeze_notes": cand.notes,
            "prior_candidate_id": prior_row.get("candidate_id", ""),
            "bucket_id": prior_row.get("bucket_id", ""),
            "bucket": prior_row.get("bucket", ""),
            "prior_CAGR": prior_row.get("CAGR", np.nan),
            "prior_max_drawdown": prior_row.get("max_drawdown", np.nan),
            "prior_Calmar": prior_row.get("Calmar", np.nan),
            "prior_trade_count": prior_row.get("trade_count", np.nan),
            "prior_turnover": prior_row.get("turnover", np.nan),
            "prior_benchmark_name": prior_row.get("benchmark_name", ""),
        }
        rows.append(row)
    return pd.DataFrame(rows)


def run_cost_stress(
    candidates: pd.DataFrame,
    price_data: Dict[str, pd.DataFrame],
    signals: Dict[str, pd.Series],
) -> pd.DataFrame:
    rows = []
    costs = [0, 5, 10, 20, 50]
    base_by_candidate: Dict[str, Dict[str, object]] = {}
    for _, row in candidates.iterrows():
        key = row["candidate_key"]
        ticker = row["ticker"]
        df = price_data[ticker]
        pos = signals[key]
        for cost in costs:
            rets, turnover_daily = net_returns_with_cost(df, pos, cost)
            metrics = compute_metrics(df["date"], rets, pos)
            if cost == 0:
                base_by_candidate[key] = metrics
            base = base_by_candidate.get(key, metrics)
            cost_drag_cagr = base["CAGR"] - metrics["CAGR"] if pd.notna(base["CAGR"]) and pd.notna(metrics["CAGR"]) else np.nan
            cost_drag_total = base["total_return"] - metrics["total_return"] if pd.notna(base["total_return"]) and pd.notna(metrics["total_return"]) else np.nan
            pass_stress = True
            if cost == 10 and pd.notna(cost_drag_cagr) and cost_drag_cagr > 0.05:
                pass_stress = False
            if cost == 20 and pd.notna(metrics["Calmar"]) and pd.notna(base["Calmar"]) and metrics["Calmar"] < 0.65 * base["Calmar"]:
                pass_stress = False
            if cost == 50 and pd.notna(metrics["CAGR"]) and metrics["CAGR"] < 0:
                pass_stress = False
            out = {
                "run_scope": RUN_SCOPE,
                "candidate_key": key,
                "ticker": ticker,
                "strategy_name": row["strategy_name"],
                "bucket_id": row["bucket_id"],
                "cost_bps": cost,
                "cost_scenario": f"cost_{cost}bps",
                "cost_drag_CAGR": cost_drag_cagr,
                "cost_drag_total_return": cost_drag_total,
                "pass_cost_stress": pass_stress,
            }
            out.update(metrics)
            rows.append(out)
    return pd.DataFrame(rows)


def slice_specs(end_date: pd.Timestamp) -> Dict[str, Tuple[pd.Timestamp, pd.Timestamp]]:
    return {
        "full_period": (pd.Timestamp("1900-01-01"), pd.Timestamp("2100-01-01")),
        "2016_2020": (pd.Timestamp("2016-01-01"), pd.Timestamp("2020-12-31")),
        "2021_2026": (pd.Timestamp("2021-01-01"), pd.Timestamp("2026-12-31")),
        "covid_crash": (pd.Timestamp("2020-02-19"), pd.Timestamp("2020-03-23")),
        "2022_bear": (pd.Timestamp("2022-01-03"), pd.Timestamp("2022-12-30")),
        "2023_2026_ai_bull": (pd.Timestamp("2023-01-01"), pd.Timestamp("2026-12-31")),
        "latest_12m": (end_date - pd.DateOffset(months=12), end_date),
        "latest_24m": (end_date - pd.DateOffset(months=24), end_date),
        "latest_36m": (end_date - pd.DateOffset(months=36), end_date),
    }


def run_period_slices(
    candidates: pd.DataFrame,
    price_data: Dict[str, pd.DataFrame],
    signals: Dict[str, pd.Series],
) -> pd.DataFrame:
    rows = []
    end_date = min(df["date"].max() for df in price_data.values())
    specs = slice_specs(end_date)
    for _, row in candidates.iterrows():
        key = row["candidate_key"]
        ticker = row["ticker"]
        bucket_id = row["bucket_id"]
        bench = primary_benchmark(bucket_id, ticker)
        df = price_data[ticker]
        pos = signals[key]
        strat_rets = gross_strategy_returns(df, pos)
        bench_df = price_data[bench]
        bench_pos = pd.Series(1.0, index=bench_df.index)
        for slice_name, (start, end) in specs.items():
            mask = (df["date"] >= start) & (df["date"] <= end)
            if slice_name == "full_period":
                mask = pd.Series(True, index=df.index)
            n = int(mask.sum())
            if n < MIN_SLICE_DAYS:
                rows.append(
                    {
                        "run_scope": RUN_SCOPE,
                        "candidate_key": key,
                        "ticker": ticker,
                        "strategy_name": row["strategy_name"],
                        "period_slice": slice_name,
                        "n_trading_days": n,
                        "slice_pass_flag": False,
                        "slice_notes": "insufficient_slice_data",
                    }
                )
                continue
            s_dates = df.loc[mask, "date"].reset_index(drop=True)
            s_rets = strat_rets.loc[mask].reset_index(drop=True)
            s_pos = pos.loc[mask].reset_index(drop=True)
            metrics = compute_metrics(s_dates, s_rets, s_pos)
            bench_mask = (bench_df["date"] >= s_dates.iloc[0]) & (bench_df["date"] <= s_dates.iloc[-1])
            bench_metrics = compute_metrics(bench_df.loc[bench_mask, "date"].reset_index(drop=True), bench_df.loc[bench_mask, "return"].reset_index(drop=True), bench_pos.loc[bench_mask].reset_index(drop=True))
            excess = metrics["CAGR"] - bench_metrics["CAGR"] if pd.notna(metrics["CAGR"]) and pd.notna(bench_metrics["CAGR"]) else np.nan
            mdd_reduction = abs(bench_metrics["max_drawdown"]) - abs(metrics["max_drawdown"]) if pd.notna(metrics["max_drawdown"]) and pd.notna(bench_metrics["max_drawdown"]) else np.nan
            notes = []
            if metrics["CAGR"] < 0:
                notes.append("negative_CAGR")
            if excess < -0.10 and mdd_reduction < 0.05:
                notes.append("underperforms_without_mdd_benefit")
            if slice_name in {"latest_12m", "latest_24m"} and metrics["CAGR"] < 0:
                notes.append("weak_recent_performance")
            pass_flag = (pd.notna(metrics["CAGR"]) and metrics["CAGR"] > 0) or (pd.notna(mdd_reduction) and mdd_reduction > 0.10)
            out = {
                "run_scope": RUN_SCOPE,
                "candidate_key": key,
                "ticker": ticker,
                "strategy_name": row["strategy_name"],
                "bucket_id": bucket_id,
                "period_slice": slice_name,
                "benchmark_ticker": bench,
                "benchmark_CAGR": bench_metrics["CAGR"],
                "benchmark_MDD": bench_metrics["max_drawdown"],
                "excess_CAGR_vs_benchmark": excess,
                "MDD_reduction_vs_benchmark": mdd_reduction,
                "slice_pass_flag": bool(pass_flag),
                "slice_notes": ";".join(notes) if notes else "ok",
            }
            out.update(metrics)
            rows.append(out)
    return pd.DataFrame(rows)


def monthly_returns(dates: pd.Series, returns: pd.Series) -> pd.Series:
    df = pd.DataFrame({"date": pd.to_datetime(dates), "return": returns.fillna(0.0)})
    df["month"] = df["date"].dt.to_period("M")
    return df.groupby("month")["return"].apply(lambda x: (1.0 + x).prod() - 1.0)


def metrics_from_period_returns(period_returns: pd.Series, periods_per_year: int = 12) -> Dict[str, float]:
    rets = period_returns.fillna(0.0)
    n = len(rets)
    if n == 0:
        return {"CAGR": np.nan, "total_return": np.nan, "max_drawdown": np.nan, "Calmar": np.nan}
    equity = (1.0 + rets).cumprod()
    years = n / periods_per_year
    total = float(equity.iloc[-1] - 1.0)
    cagr = float(equity.iloc[-1] ** (1.0 / years) - 1.0) if years > 0 and equity.iloc[-1] > 0 else np.nan
    mdd, _, _ = max_drawdown(equity.reset_index(drop=True))
    calmar = float(cagr / abs(mdd)) if pd.notna(cagr) and mdd < 0 else np.nan
    return {"CAGR": cagr, "total_return": total, "max_drawdown": mdd, "Calmar": calmar}


def run_top_month_sensitivity(candidates: pd.DataFrame, price_data: Dict[str, pd.DataFrame], signals: Dict[str, pd.Series]) -> pd.DataFrame:
    rows = []
    removals = {
        "best_1_month": ("best", 1),
        "best_3_months": ("best", 3),
        "best_5_months": ("best", 5),
        "worst_1_month": ("worst", 1),
        "worst_3_months": ("worst", 3),
        "worst_5_months": ("worst", 5),
    }
    for _, row in candidates.iterrows():
        key = row["candidate_key"]
        ticker = row["ticker"]
        df = price_data[ticker]
        rets = gross_strategy_returns(df, signals[key])
        mret = monthly_returns(df["date"], rets)
        base_metrics = metrics_from_period_returns(mret)
        positive_sum = float(mret[mret > 0].sum())
        top3_sum = float(mret.sort_values(ascending=False).head(3).clip(lower=0).sum())
        concentration = top3_sum / positive_sum if positive_sum > 0 else np.nan
        for label, (kind, n) in removals.items():
            if kind == "best":
                remove_idx = mret.sort_values(ascending=False).head(n).index
            else:
                remove_idx = mret.sort_values(ascending=True).head(n).index
            reduced = mret.drop(remove_idx)
            metrics = metrics_from_period_returns(reduced)
            cagr_drop = base_metrics["CAGR"] - metrics["CAGR"] if pd.notna(base_metrics["CAGR"]) and pd.notna(metrics["CAGR"]) else np.nan
            calmar_ratio = metrics["Calmar"] / base_metrics["Calmar"] if pd.notna(metrics["Calmar"]) and pd.notna(base_metrics["Calmar"]) and base_metrics["Calmar"] != 0 else np.nan
            top_dep = bool(kind == "best" and n >= 3 and ((pd.notna(cagr_drop) and cagr_drop > 0.20) or (pd.notna(calmar_ratio) and calmar_ratio < 0.50)))
            out = {
                "run_scope": RUN_SCOPE,
                "candidate_key": key,
                "ticker": ticker,
                "strategy_name": row["strategy_name"],
                "removal_case": label,
                "removed_months": ",".join(str(x) for x in remove_idx),
                "base_CAGR": base_metrics["CAGR"],
                "base_Calmar": base_metrics["Calmar"],
                "CAGR_drop_vs_base": cagr_drop,
                "Calmar_ratio_vs_base": calmar_ratio,
                "monthly_return_concentration_ratio": concentration,
                "top_month_dependency_flag": top_dep,
            }
            out.update(metrics)
            rows.append(out)
    return pd.DataFrame(rows)


def run_rolling_validation(candidates: pd.DataFrame, price_data: Dict[str, pd.DataFrame], signals: Dict[str, pd.Series]) -> Tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    summary_rows = []
    windows = {"3Y": 3 * TRADING_DAYS, "5Y": 5 * TRADING_DAYS}
    step = 21
    for _, row in candidates.iterrows():
        key = row["candidate_key"]
        ticker = row["ticker"]
        bench = primary_benchmark(row["bucket_id"], ticker)
        df = price_data[ticker]
        bench_df = price_data[bench]
        pos = signals[key]
        strat = gross_strategy_returns(df, pos)
        for window_name, window_len in windows.items():
            window_rows = []
            if len(df) < window_len:
                continue
            for start_idx in range(0, len(df) - window_len + 1, step):
                end_idx = start_idx + window_len
                s_dates = df["date"].iloc[start_idx:end_idx].reset_index(drop=True)
                s_rets = strat.iloc[start_idx:end_idx].reset_index(drop=True)
                s_pos = pos.iloc[start_idx:end_idx].reset_index(drop=True)
                metrics = compute_metrics(s_dates, s_rets, s_pos)
                bmask = (bench_df["date"] >= s_dates.iloc[0]) & (bench_df["date"] <= s_dates.iloc[-1])
                bmetrics = compute_metrics(bench_df.loc[bmask, "date"].reset_index(drop=True), bench_df.loc[bmask, "return"].reset_index(drop=True), pd.Series(1.0, index=bench_df.loc[bmask].index).reset_index(drop=True))
                pass_flag = bool(
                    pd.notna(metrics["CAGR"])
                    and metrics["CAGR"] > 0
                    and (
                        metrics["CAGR"] >= bmetrics["CAGR"]
                        or abs(bmetrics["max_drawdown"]) - abs(metrics["max_drawdown"]) > 0.10
                    )
                )
                out = {
                    "run_scope": RUN_SCOPE,
                    "candidate_key": key,
                    "ticker": ticker,
                    "strategy_name": row["strategy_name"],
                    "rolling_window": window_name,
                    "window_start": s_dates.iloc[0].date().isoformat(),
                    "window_end": s_dates.iloc[-1].date().isoformat(),
                    "benchmark_ticker": bench,
                    "benchmark_CAGR": bmetrics["CAGR"],
                    "benchmark_MDD": bmetrics["max_drawdown"],
                    "pass_flag": pass_flag,
                }
                out.update(metrics)
                rows.append(out)
                window_rows.append(out)
            wdf = pd.DataFrame(window_rows)
            if not wdf.empty:
                pass_rate = float(wdf["pass_flag"].mean())
                notes = []
                if pass_rate < 0.50:
                    notes.append("rolling_pass_rate_below_50pct")
                if (wdf["CAGR"] < 0).any():
                    notes.append("has_negative_rolling_CAGR")
                summary_rows.append(
                    {
                        "run_scope": RUN_SCOPE,
                        "candidate_key": key,
                        "ticker": ticker,
                        "strategy_name": row["strategy_name"],
                        "rolling_window": window_name,
                        "rolling_window_count": int(len(wdf)),
                        "positive_CAGR_window_count": int((wdf["CAGR"] > 0).sum()),
                        "outperform_benchmark_window_count": int((wdf["CAGR"] > wdf["benchmark_CAGR"]).sum()),
                        "MDD_better_than_benchmark_window_count": int((wdf["max_drawdown"].abs() < wdf["benchmark_MDD"].abs()).sum()),
                        "rolling_pass_rate": pass_rate,
                        "worst_rolling_CAGR": float(wdf["CAGR"].min()),
                        "worst_rolling_MDD": float(wdf["max_drawdown"].min()),
                        "rolling_validation_notes": ";".join(notes) if notes else "ok",
                    }
                )
    return pd.DataFrame(rows), pd.DataFrame(summary_rows)


def neighbor_specs(cand: FrozenCandidate) -> List[Tuple[str, str, Dict[str, object]]]:
    specs: List[Tuple[str, str, Dict[str, object]]] = []
    if cand.strategy_family in {"sma_trend_following", "cooldown_confirmation"}:
        base_fast = int(cand.params.get("fast", 50))
        base_slow = int(cand.params.get("slow", 200))
        for fast in sorted({max(5, base_fast - 10), base_fast, base_fast + 10}):
            for slow in sorted({max(fast + 20, base_slow - 20), base_slow, base_slow + 20}):
                for cooldown in [0, 5, 10]:
                    for confirm in [0, 1, 2]:
                        params = {"fast": fast, "slow": slow, "cooldown": cooldown, "confirm": confirm}
                        name = f"sma{fast}_{slow}_cooldown_{cooldown}_confirm_{confirm}"
                        specs.append(("cooldown_confirmation", name, params))
    elif cand.strategy_family == "time_series_momentum":
        for window in [42, 63, 84, 126]:
            specs.append(("time_series_momentum", f"ts_mom_{window}d", {"window": window}))
    elif cand.strategy_family == "volatility_filter":
        for window in [20, 42, 63, 84]:
            for threshold_window in [126, 252]:
                params = {"window": window, "threshold_window": threshold_window, "requires_positive_63d_momentum": True}
                specs.append(("volatility_filter", f"vol_filter_{window}d_threshold_{threshold_window}", params))
    elif cand.strategy_family == "drawdown_trailing_stop_filter":
        for stop in [0.10, 0.15, 0.20, 0.25]:
            specs.append(("drawdown_trailing_stop_filter", f"trailing_stop_{int(stop * 100)}pct", {"stop": stop}))
    return specs


def run_parameter_neighborhood(
    candidates: pd.DataFrame,
    price_data: Dict[str, pd.DataFrame],
    signals: Dict[str, pd.Series],
    frozen_by_key: Dict[str, FrozenCandidate],
) -> pd.DataFrame:
    rows = []
    for _, row in candidates.iterrows():
        key = row["candidate_key"]
        cand = frozen_by_key[key]
        df = price_data[cand.ticker]
        base_pos = signals[key]
        base_rets = gross_strategy_returns(df, base_pos)
        base_metrics = compute_metrics(df["date"], base_rets, base_pos)
        for family, name, params in neighbor_specs(cand):
            pos = generate_signal(df, family, params)
            rets = gross_strategy_returns(df, pos)
            metrics = compute_metrics(df["date"], rets, pos)
            cagr_drop = base_metrics["CAGR"] - metrics["CAGR"] if pd.notna(base_metrics["CAGR"]) and pd.notna(metrics["CAGR"]) else np.nan
            calmar_ratio = metrics["Calmar"] / base_metrics["Calmar"] if pd.notna(metrics["Calmar"]) and pd.notna(base_metrics["Calmar"]) and base_metrics["Calmar"] != 0 else np.nan
            cliff = bool((pd.notna(cagr_drop) and cagr_drop > 0.15) or (pd.notna(calmar_ratio) and calmar_ratio < 0.50))
            rows.append(
                {
                    "run_scope": RUN_SCOPE,
                    "base_candidate": key,
                    "neighbor_candidate": f"{cand.ticker}/{name}",
                    "ticker": cand.ticker,
                    "neighbor_family": family,
                    "neighbor_parameters": json.dumps(params, sort_keys=True),
                    "base_CAGR": base_metrics["CAGR"],
                    "neighbor_CAGR": metrics["CAGR"],
                    "base_Calmar": base_metrics["Calmar"],
                    "neighbor_Calmar": metrics["Calmar"],
                    "base_MDD": base_metrics["max_drawdown"],
                    "neighbor_MDD": metrics["max_drawdown"],
                    "CAGR_drop_vs_base": cagr_drop,
                    "Calmar_ratio_vs_base": calmar_ratio,
                    "cliff_drop_flag": cliff,
                    "neighborhood_pass_flag": not cliff,
                }
            )
    return pd.DataFrame(rows)


def run_benchmark_comparison(candidates: pd.DataFrame, price_data: Dict[str, pd.DataFrame], signals: Dict[str, pd.Series]) -> pd.DataFrame:
    rows = []
    for _, row in candidates.iterrows():
        key = row["candidate_key"]
        ticker = row["ticker"]
        bucket_id = row["bucket_id"]
        df = price_data[ticker]
        pos = signals[key]
        strat_metrics = compute_metrics(df["date"], gross_strategy_returns(df, pos), pos)
        bench_defs = [
            ("same_ticker_buy_hold", ticker),
            ("SPY_buy_hold", "SPY"),
            ("QQQ_buy_hold", "QQQ"),
            ("bucket_benchmark", bucket_benchmark(bucket_id, ticker)),
        ]
        seen = set()
        for bench_type, bench_ticker in bench_defs:
            unique_key = (bench_type, bench_ticker)
            if unique_key in seen or bench_ticker not in price_data:
                continue
            seen.add(unique_key)
            bdf = price_data[bench_ticker]
            bmetrics = compute_metrics(bdf["date"], bdf["return"], pd.Series(1.0, index=bdf.index))
            excess = strat_metrics["CAGR"] - bmetrics["CAGR"] if pd.notna(strat_metrics["CAGR"]) and pd.notna(bmetrics["CAGR"]) else np.nan
            mdd_reduction = abs(bmetrics["max_drawdown"]) - abs(strat_metrics["max_drawdown"]) if pd.notna(strat_metrics["max_drawdown"]) and pd.notna(bmetrics["max_drawdown"]) else np.nan
            pass_flag = bool(
                (pd.notna(excess) and excess >= 0)
                or (pd.notna(mdd_reduction) and mdd_reduction > 0.10 and excess > -0.15)
            )
            rows.append(
                {
                    "run_scope": RUN_SCOPE,
                    "candidate_key": key,
                    "ticker": ticker,
                    "strategy_name": row["strategy_name"],
                    "benchmark_type": bench_type,
                    "benchmark_ticker": bench_ticker,
                    "strategy_CAGR": strat_metrics["CAGR"],
                    "strategy_MDD": strat_metrics["max_drawdown"],
                    "strategy_Calmar": strat_metrics["Calmar"],
                    "benchmark_CAGR": bmetrics["CAGR"],
                    "benchmark_MDD": bmetrics["max_drawdown"],
                    "benchmark_Calmar": bmetrics["Calmar"],
                    "excess_CAGR": excess,
                    "MDD_reduction": mdd_reduction,
                    "benchmark_pass_flag": pass_flag,
                }
            )
    return pd.DataFrame(rows)


def build_trade_ledger(candidates: pd.DataFrame, price_data: Dict[str, pd.DataFrame], signals: Dict[str, pd.Series]) -> pd.DataFrame:
    rows = []
    for _, row in candidates.iterrows():
        key = row["candidate_key"]
        ticker = row["ticker"]
        df = price_data[ticker]
        pos = signals[key].fillna(0.0)
        rets = gross_strategy_returns(df, pos)
        equity = (1.0 + rets).cumprod()
        prev = pos.shift(1).fillna(0.0)
        changes = pos - prev
        entry_idx: Optional[int] = None
        entry_price = np.nan
        for i, change in enumerate(changes):
            if abs(change) < 1e-12:
                continue
            action = "BUY" if change > 0 else "SELL"
            price = float(df["adj_close"].iloc[i])
            holding_days = ""
            trade_return = ""
            if action == "BUY":
                entry_idx = i
                entry_price = price
            elif action == "SELL" and entry_idx is not None and pd.notna(entry_price) and entry_price > 0:
                holding_days = int(i - entry_idx)
                trade_return = float(price / entry_price - 1.0)
                entry_idx = None
                entry_price = np.nan
            rows.append(
                {
                    "run_scope": RUN_SCOPE,
                    "candidate_key": key,
                    "ticker": ticker,
                    "strategy_name": row["strategy_name"],
                    "signal_date": df["date"].iloc[i].date().isoformat(),
                    "action": action,
                    "price": price,
                    "position_before": float(prev.iloc[i]),
                    "position_after": float(pos.iloc[i]),
                    "reason": "signal_cross_or_filter_change",
                    "holding_days": holding_days,
                    "trade_return": trade_return,
                    "cumulative_return_after_trade": float(equity.iloc[i] - 1.0),
                }
            )
    return pd.DataFrame(rows)


def yearly_positive_share(dates: pd.Series, returns: pd.Series, years: Iterable[int]) -> float:
    df = pd.DataFrame({"date": pd.to_datetime(dates), "return": returns.fillna(0.0)})
    df["year"] = df["date"].dt.year
    yr = df.groupby("year")["return"].apply(lambda x: (1.0 + x).prod() - 1.0)
    positive_sum = float(yr[yr > 0].sum())
    if positive_sum <= 0:
        return np.nan
    return float(yr.loc[[y for y in years if y in yr.index]].clip(lower=0).sum() / positive_sum)


def run_risk_flags_and_decisions(
    candidates: pd.DataFrame,
    price_data: Dict[str, pd.DataFrame],
    signals: Dict[str, pd.Series],
    cost_df: pd.DataFrame,
    slice_df: pd.DataFrame,
    rolling_summary: pd.DataFrame,
    top_month_df: pd.DataFrame,
    neigh_df: pd.DataFrame,
    bench_df: pd.DataFrame,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    risk_rows = []
    decision_rows = []
    for _, row in candidates.iterrows():
        key = row["candidate_key"]
        ticker = row["ticker"]
        df = price_data[ticker]
        pos = signals[key]
        rets = gross_strategy_returns(df, pos)
        full_metrics = compute_metrics(df["date"], rets, pos)
        cost20 = cost_df[(cost_df["candidate_key"] == key) & (cost_df["cost_bps"] == 20)]
        cost0 = cost_df[(cost_df["candidate_key"] == key) & (cost_df["cost_bps"] == 0)]
        cost_sensitive = False
        if not cost20.empty and not cost0.empty:
            c0 = float(cost0.iloc[0]["CAGR"])
            c20 = float(cost20.iloc[0]["CAGR"])
            cal0 = float(cost0.iloc[0]["Calmar"])
            cal20 = float(cost20.iloc[0]["Calmar"])
            cost_sensitive = (c0 - c20 > 0.05) or (pd.notna(cal0) and cal0 > 0 and cal20 < 0.70 * cal0) or (full_metrics["turnover"] > 8 and c0 - c20 > 0.02)
        roll = rolling_summary[rolling_summary["candidate_key"] == key]
        rolling_pass_rate = float(roll["rolling_pass_rate"].mean()) if not roll.empty else 0.0
        latest = slice_df[(slice_df["candidate_key"] == key) & (slice_df["period_slice"].isin(["latest_12m", "latest_24m"]))]
        weak_recent = bool((latest["CAGR"] < 0).any()) if not latest.empty and "CAGR" in latest else False
        top_dep = bool(top_month_df[(top_month_df["candidate_key"] == key) & (top_month_df["top_month_dependency_flag"] == True)].shape[0] > 0)
        cliff = bool(neigh_df[(neigh_df["base_candidate"] == key) & (neigh_df["cliff_drop_flag"] == True)].shape[0] > 0)
        same_bench = bench_df[(bench_df["candidate_key"] == key) & (bench_df["benchmark_type"] == "same_ticker_buy_hold")]
        bench_under = bool(not same_bench.empty and not bool(same_bench.iloc[0]["benchmark_pass_flag"]))
        ai_share = yearly_positive_share(df["date"], rets, [2023, 2024, 2025, 2026])
        ai_bull = bool(pd.notna(ai_share) and ai_share > 0.65)
        low_trade = bool(full_metrics["trade_count"] < 5 and row["strategy_name"] != "buy_and_hold")
        high_turnover = bool(full_metrics["turnover"] > 8)
        leveraged = bool(row["bucket_id"] == "Bucket D")
        observation = bool(row["role"] in {"observation_only", "negative_case_observation"})
        flags = {
            "single_ticker_concentration": True,
            "ai_bull_dependency": ai_bull,
            "low_trade_count": low_trade,
            "high_turnover": high_turnover,
            "cost_sensitive": cost_sensitive,
            "cliff_parameter_sensitive": cliff,
            "benchmark_underperformance": bench_under,
            "weak_recent_performance": weak_recent,
            "leveraged_etf_special_risk": leveraged,
            "observation_only": observation,
            "not_formal_mve2_ready": True,
            "top_month_dependent": top_dep,
        }
        risk_row = {
            "run_scope": RUN_SCOPE,
            "candidate_key": key,
            "ticker": ticker,
            "strategy_name": row["strategy_name"],
            "bucket_id": row["bucket_id"],
            "CAGR": full_metrics["CAGR"],
            "max_drawdown": full_metrics["max_drawdown"],
            "Calmar": full_metrics["Calmar"],
            "trade_count": full_metrics["trade_count"],
            "turnover": full_metrics["turnover"],
            "rolling_pass_rate": rolling_pass_rate,
            "ai_bull_positive_return_share": ai_share,
        }
        risk_row.update(flags)
        risk_row["risk_flag_count"] = int(sum(bool(v) for k, v in flags.items() if k != "not_formal_mve2_ready"))
        risk_rows.append(risk_row)

        if row["role"] == "observation_only":
            decision = "observation_only"
            reason = "MSTR is high-beta observation only and cannot represent Layer5."
        elif row["role"] == "negative_case_observation":
            decision = "observation_only"
            reason = "Risk observation candidate retained to document parameter sensitivity."
        elif leveraged:
            decision = "conditional_pass_leveraged_bucket"
            reason = "Leveraged ETF bucket must remain separate; any pass is conditional to leveraged-bucket validation."
        elif cliff:
            decision = "conditional_pass"
            reason = "Parameter neighborhood includes cliff drop."
        elif cost_sensitive:
            decision = "conditional_pass"
            reason = "Cost stress weakens edge."
        elif top_dep:
            decision = "conditional_pass"
            reason = "Top-month dependency is material."
        elif rolling_pass_rate >= 0.55 and not bench_under:
            decision = "pass_to_next_validation"
            reason = "Passes basic benchmark, rolling, cost, and neighborhood checks within limited scope."
        elif rolling_pass_rate >= 0.40:
            decision = "conditional_pass"
            reason = "Mixed rolling or benchmark evidence; needs portfolio/K-line validation."
        else:
            decision = "reject"
            reason = "Validation evidence is too weak for next-stage candidate refinement."
        decision_rows.append(
            {
                "run_scope": RUN_SCOPE,
                "candidate_key": key,
                "ticker": ticker,
                "strategy_name": row["strategy_name"],
                "bucket_id": row["bucket_id"],
                "role": row["role"],
                "validation_decision": decision,
                "decision_reason": reason,
                "CAGR": full_metrics["CAGR"],
                "max_drawdown": full_metrics["max_drawdown"],
                "Calmar": full_metrics["Calmar"],
                "rolling_pass_rate": rolling_pass_rate,
                "cost_sensitive": cost_sensitive,
                "top_month_dependent": top_dep,
                "cliff_parameter_sensitive": cliff,
                "benchmark_underperformance": bench_under,
                "weak_recent_performance": weak_recent,
                "formal_mve2_supported": False,
            }
        )
    risk_df = pd.DataFrame(risk_rows)
    decision_df = pd.DataFrame(decision_rows)
    rejected = decision_df[decision_df["validation_decision"].isin(["reject", "observation_only"])].copy()
    return risk_df, decision_df, rejected


def write_readme(
    out_dir: Path,
    candidates: pd.DataFrame,
    decision_df: pd.DataFrame,
    cost_df: pd.DataFrame,
    slice_df: pd.DataFrame,
    rolling_summary: pd.DataFrame,
    top_month_df: pd.DataFrame,
    neigh_df: pd.DataFrame,
    bench_df: pd.DataFrame,
) -> None:
    def table(df: pd.DataFrame, cols: Optional[List[str]] = None, n: int = 20) -> str:
        if df.empty:
            return "无。"
        show = df[cols].head(n) if cols else df.head(n)
        return show.to_markdown(index=False, floatfmt=".4f")

    decision_cols = ["candidate_key", "validation_decision", "decision_reason", "CAGR", "max_drawdown", "Calmar", "rolling_pass_rate"]
    cost20 = cost_df[cost_df["cost_bps"] == 20][["candidate_key", "CAGR", "Calmar", "cost_drag_CAGR", "pass_cost_stress"]]
    top_dep = top_month_df[top_month_df["top_month_dependency_flag"] == True][["candidate_key", "removal_case", "CAGR", "Calmar", "monthly_return_concentration_ratio"]]
    cliff = neigh_df[neigh_df["cliff_drop_flag"] == True][["base_candidate", "neighbor_candidate", "CAGR_drop_vs_base", "Calmar_ratio_vs_base"]]
    latest = slice_df[slice_df["period_slice"].isin(["latest_12m", "latest_24m"])][["candidate_key", "period_slice", "CAGR", "Calmar", "slice_notes"]]
    same_bench = bench_df[bench_df["benchmark_type"] == "same_ticker_buy_hold"][["candidate_key", "strategy_CAGR", "benchmark_CAGR", "strategy_MDD", "benchmark_MDD", "excess_CAGR", "MDD_reduction", "benchmark_pass_flag"]]

    readme = f"""# limited MVE2 validation pack 摘要

## 1. 本轮任务目标

本轮只对上一轮 limited MVE2 初筛中冻结的 9 个候选做 validation pack：成本压力、period slice、top-month sensitivity、rolling validation、小邻域参数复核、benchmark 对比和 trade ledger/signal audit。

## 2. 为什么不是新一轮搜索

本轮不扩 universe，不纳入 excluded tickers，不新增大范围参数搜索，不训练机器学习模型，不启动 formal MVE2。所有输出标记为 `{RUN_SCOPE}`，所有价格、收益、波动和信号只使用统一 store 的 `adj_close` 和 `volume`。

## 3. 冻结候选清单

{table(candidates, ["candidate_key", "bucket_id", "role", "parameters"])}

## 4. 每个候选 validation 结论

{table(decision_df, decision_cols)}

## 5. 成本压力测试结论

20bps 成本结果如下。高换手的 momentum / volatility filter 候选更容易变成 cost_sensitive，后续不能直接进入组合构建。

{table(cost20)}

## 6. Period slice 结论

latest_12m / latest_24m 是当前最重要的近期退化检查。若这些窗口为负或明显弱于 benchmark，应降级为 conditional。

{table(latest, n=30)}

## 7. Rolling validation 结论

{table(rolling_summary, ["candidate_key", "rolling_window", "rolling_window_count", "rolling_pass_rate", "worst_rolling_CAGR", "worst_rolling_MDD", "rolling_validation_notes"], n=30)}

## 8. Top-month sensitivity 结论

出现 top-month dependency 的候选如下。若剔除 best 3/5 months 后 CAGR 或 Calmar 塌陷，不能直接 pass。

{table(top_dep, n=30)}

## 9. 参数邻域复核结论

小邻域复核未做新搜索，只围绕冻结候选的局部参数变化。cliff drop 如下：

{table(cliff, n=30)}

## 10. Benchmark 对比结论

特别是 NVDA 候选，buy-and-hold CAGR 更高，但择时策略显著降低 MDD，因此不能只看 CAGR。

{table(same_bench, n=30)}

## 11. NVDA 候选是否只是 AI bull / 单票集中

NVDA 两个候选仍然是单 ticker，存在 AI bull 与单票集中风险。SMA/cooldown 版本的核心价值在于降低回撤，而不是超越 NVDA buy-and-hold 的 CAGR。下一步若继续，必须做 portfolio construction，不能把单票候选直接当最终策略。

## 12. SOXX 候选是否可代表 Layer3

SOXX `sma_20_120` 可以作为 Layer3 Sector/theme ETF 的一个可验证候选，但不能代表整个 Layer3。下一步应与 SMH/SOXX/XLK 等同层候选做组合级验证。

## 13. UPRO 候选是否只能作为 leveraged ETF 单独策略

是。UPRO `vol_filter_63d` 即使进入下一步，也只能作为 leveraged ETF separate bucket，不能和普通 equity/ETF 混排。

## 14. MSTR 为什么只能 observation

MSTR 属于 High-beta observation bucket。Layer5 大部分 ticker 因上市历史不足 10 年仍被排除，所以 MSTR 不代表完整 Layer5，且自身回撤/波动特征极端。

## 15. 下一步建议

建议进入有限的 `portfolio construction test` 和 `K 线买卖点可视化`，对象仅限本轮 pass/conditional 的少量候选。仍不建议 formal MVE2，不建议扩 universe，也不建议继续大范围搜索。

## 16. Formal MVE2 结论

本轮仍不支持 formal MVE2。当前只支持 limited MVE2 后续验证链条。
"""
    (out_dir / "README_summary.md").write_text(readme, encoding="utf-8")


def copy_script(out_dir: Path) -> None:
    src = Path(__file__).resolve()
    shutil.copy2(src, out_dir / src.name)


def zip_output(out_dir: Path, timestamp: str) -> Path:
    zip_path = out_dir.parent / f"us_stock_selection_limited_mve2_validation_{timestamp}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in out_dir.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(out_dir))
    return zip_path


def sync_meistock(out_dir: Path, zip_path: Path, timestamp: str, logger: RunLogger) -> None:
    target_root = Path(r"E:\dzhwork\obsydian\quant_lab\MeiStock")
    if not target_root.exists():
        logger.log(f"MeiStock sync skipped; path missing: {target_root}")
        return
    sync_dir = target_root / "checkpoint" / f"limited_mve2_validation_{timestamp}"
    try:
        sync_dir.mkdir(parents=True, exist_ok=True)
        for name in [
            "README_summary.md",
            "frozen_candidates_limited_mve2_validation.csv",
            "validation_decision_summary.csv",
            "validation_risk_flags.csv",
            "validation_benchmark_comparison.csv",
            "validation_trade_ledger.csv",
        ]:
            src = out_dir / name
            if src.exists():
                shutil.copy2(src, sync_dir / name)
        index = pd.DataFrame(
            [
                {
                    "checkpoint": f"limited_mve2_validation_{timestamp}",
                    "output_dir": str(out_dir.resolve()),
                    "zip_path": str(zip_path.resolve()),
                    "run_scope": RUN_SCOPE,
                    "formal_mve2_supported": False,
                }
            ]
        )
        index.to_csv(sync_dir / "meistock_sync_index.csv", index=False, encoding="utf-8-sig")
        logger.log(f"MeiStock sync completed: {sync_dir}")
    except Exception as exc:  # noqa: BLE001
        logger.log(f"WARNING: MeiStock sync failed: {exc}")


def main() -> int:
    args = parse_args()
    timestamp = args.timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = args.out_dir or (DEFAULT_OUTPUT_ROOT / f"limited_mve2_validation_{timestamp}")
    out_dir.mkdir(parents=True, exist_ok=False)
    logger = RunLogger(out_dir / "limited_mve2_validation_run_log.txt")
    logger.log("Starting limited MVE2 validation pack.")
    logger.log(f"Prior limited MVE2 dir: {args.prior_limited_mve2_dir}")
    logger.log(f"Unified store dir: {args.store_dir}")
    logger.log("Scope guard: validation pack only; no new full search; no formal MVE2; no model training.")

    prior = read_prior_results(args.prior_limited_mve2_dir)
    candidates = build_frozen_candidates(prior)
    candidates.to_csv(out_dir / "frozen_candidates_limited_mve2_validation.csv", index=False, encoding="utf-8-sig")
    logger.log(f"Frozen candidates: {len(candidates)}")

    tickers = sorted(set(candidates["ticker"]) | {"SPY", "QQQ"})
    price_raw = {ticker: read_price(args.store_dir, ticker) for ticker in tickers}
    start, end = common_window(price_raw, args.prior_limited_mve2_dir)
    price_data = align_price_data(price_raw, start, end)
    logger.log(f"Validation window: {start.date()} to {end.date()}; tickers loaded: {len(price_data)}")

    frozen_by_key = {candidate_key(c): c for c in FROZEN_CANDIDATES}
    signals: Dict[str, pd.Series] = {}
    for _, row in candidates.iterrows():
        key = row["candidate_key"]
        cand = frozen_by_key[key]
        signals[key] = generate_signal(price_data[cand.ticker], cand.strategy_family, cand.params).reset_index(drop=True)

    cost_df = run_cost_stress(candidates, price_data, signals)
    cost_df.to_csv(out_dir / "validation_cost_stress_results.csv", index=False, encoding="utf-8-sig")
    logger.log(f"Cost stress rows: {len(cost_df)}")

    slice_df = run_period_slices(candidates, price_data, signals)
    slice_df.to_csv(out_dir / "validation_period_slice_results.csv", index=False, encoding="utf-8-sig")
    logger.log(f"Period slice rows: {len(slice_df)}")

    top_month_df = run_top_month_sensitivity(candidates, price_data, signals)
    top_month_df.to_csv(out_dir / "validation_top_month_sensitivity.csv", index=False, encoding="utf-8-sig")

    rolling_df, rolling_summary = run_rolling_validation(candidates, price_data, signals)
    rolling_df.to_csv(out_dir / "validation_rolling_window_results.csv", index=False, encoding="utf-8-sig")
    rolling_summary.to_csv(out_dir / "validation_rolling_summary.csv", index=False, encoding="utf-8-sig")
    logger.log(f"Rolling rows: {len(rolling_df)}; summary rows: {len(rolling_summary)}")

    neigh_df = run_parameter_neighborhood(candidates, price_data, signals, frozen_by_key)
    neigh_df.to_csv(out_dir / "validation_parameter_neighborhood.csv", index=False, encoding="utf-8-sig")
    logger.log(f"Neighborhood rows: {len(neigh_df)}")

    bench_df = run_benchmark_comparison(candidates, price_data, signals)
    bench_df.to_csv(out_dir / "validation_benchmark_comparison.csv", index=False, encoding="utf-8-sig")

    ledger_df = build_trade_ledger(candidates, price_data, signals)
    ledger_df.to_csv(out_dir / "validation_trade_ledger.csv", index=False, encoding="utf-8-sig")
    logger.log(f"Trade ledger rows: {len(ledger_df)}")

    risk_df, decision_df, rejected_df = run_risk_flags_and_decisions(
        candidates,
        price_data,
        signals,
        cost_df,
        slice_df,
        rolling_summary,
        top_month_df,
        neigh_df,
        bench_df,
    )
    risk_df.to_csv(out_dir / "validation_risk_flags.csv", index=False, encoding="utf-8-sig")
    decision_df.to_csv(out_dir / "validation_decision_summary.csv", index=False, encoding="utf-8-sig")
    rejected_df.to_csv(out_dir / "rejected_or_observation_candidates.csv", index=False, encoding="utf-8-sig")

    run_config = {
        "run_scope": RUN_SCOPE,
        "timestamp": timestamp,
        "prior_limited_mve2_dir": str(args.prior_limited_mve2_dir),
        "store_dir": str(args.store_dir),
        "out_dir": str(out_dir),
        "candidate_count": int(len(candidates)),
        "formal_mve2_started": False,
        "new_strategy_search_started": False,
        "model_training_started": False,
        "uses_only_unified_adj_close_volume": True,
    }
    (out_dir / "limited_mve2_validation_run_config.json").write_text(json.dumps(run_config, indent=2), encoding="utf-8")

    write_readme(out_dir, candidates, decision_df, cost_df, slice_df, rolling_summary, top_month_df, neigh_df, bench_df)
    reports = out_dir / "reports"
    reports.mkdir(exist_ok=True)
    shutil.copy2(out_dir / "README_summary.md", reports / "limited_mve2_validation_report.md")
    with pd.ExcelWriter(reports / "limited_mve2_validation_summary.xlsx") as writer:
        candidates.to_excel(writer, sheet_name="frozen", index=False)
        decision_df.to_excel(writer, sheet_name="decisions", index=False)
        risk_df.to_excel(writer, sheet_name="risk_flags", index=False)
        cost_df.to_excel(writer, sheet_name="cost", index=False)
        rolling_summary.to_excel(writer, sheet_name="rolling_summary", index=False)
        bench_df.to_excel(writer, sheet_name="benchmark", index=False)

    copy_script(out_dir)
    zip_path = Path("")
    if not args.no_zip:
        zip_path = zip_output(out_dir, timestamp)
        logger.log(f"Zip written: {zip_path}")
    sync_meistock(out_dir, zip_path, timestamp, logger)
    logger.log("limited MVE2 validation pack completed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
