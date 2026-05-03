#!/usr/bin/env python
"""Run limited MVE2 strategy search on the audited unified OHLCV store.

Scope guard:
- limited_mve2 only, not formal v9/MVE2.
- Uses only audited unified store prices: date, adj_close, volume.
- Excludes tickers without 10y/MVE2 readiness.
- Keeps leveraged ETFs in a separate bucket.
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
from typing import Callable, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd


MANDATORY_EXCLUDED = {
    "CRWD",
    "NET",
    "PLTR",
    "SNOW",
    "AFRM",
    "COIN",
    "LCID",
    "RIVN",
    "ROKU",
    "UPST",
    "UBER",
}
MANDATORY_EXCLUDE_REASON = "listed_history_lt_10y_or_mve2_not_ready"

DEFAULT_STORE_DIR = Path("data/unified_ohlcv/us_stock_selection")
DEFAULT_READINESS_DIR = Path(
    "outputs/us_stock_selection/unified_adjusted_ohlcv_store_20260502_103643/audit"
)
DEFAULT_OUTPUT_ROOT = Path("outputs/us_stock_selection")
TRADING_DAYS = 252
MIN_SLICE_DAYS = 60
RUN_SCOPE = "limited_mve2"


@dataclass(frozen=True)
class StrategySpec:
    family: str
    name: str
    parameters: Dict[str, object]
    runner: Callable[[pd.DataFrame, Dict[str, object]], pd.Series]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run limited MVE2 strategy search using unified adjusted OHLCV store."
    )
    parser.add_argument("--store-dir", type=Path, default=DEFAULT_STORE_DIR)
    parser.add_argument("--readiness-dir", type=Path, default=DEFAULT_READINESS_DIR)
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--timestamp", type=str, default=None)
    parser.add_argument("--start-date", type=str, default="2016-01-01")
    parser.add_argument("--benchmark-tickers", type=str, default="SPY,QQQ")
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--no-zip", action="store_true")
    return parser.parse_args()


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


def bool_series(s: pd.Series) -> pd.Series:
    if s.dtype == bool:
        return s
    return s.astype(str).str.lower().isin({"true", "1", "yes", "y"})


def load_readiness(readiness_dir: Path) -> pd.DataFrame:
    path = readiness_dir / "ticker_readiness_after_unified_store.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing readiness file: {path}")
    df = pd.read_csv(path)
    required = {"ticker", "layer", "mve2_ready_price_data"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Readiness file missing columns: {sorted(missing)}")
    df["ticker"] = df["ticker"].astype(str).str.upper().str.strip()
    df["mve2_ready_price_data"] = bool_series(df["mve2_ready_price_data"])
    if "mve2_ready_reason" not in df.columns:
        df["mve2_ready_reason"] = ""
    return df


def bucket_for_row(ticker: str, layer: str) -> Optional[Tuple[str, str, str]]:
    layer_text = str(layer)
    if "Layer 1" in layer_text:
        return ("Bucket A", "Layer1 Mega-cap / core equity", "ordinary_equity")
    if "Layer 2" in layer_text:
        return ("Bucket B", "Layer2 Core ETF", "core_etf")
    if "Layer 3" in layer_text:
        return ("Bucket C", "Layer3 Sector/theme ETF", "sector_theme_etf")
    if "Layer 4" in layer_text:
        return ("Bucket D", "Layer4 Leveraged ETF", "leveraged_etf")
    if "v8_candidate_extension" in layer_text:
        return ("Bucket E", "v8 extension ready subset", "v8_extension")
    if ticker == "MSTR":
        return ("Bucket F", "High-beta observation bucket", "high_beta_observation")
    return None


def build_universe(readiness: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rows = []
    excluded_rows = []
    for _, row in readiness.sort_values("ticker").iterrows():
        ticker = str(row["ticker"]).upper()
        ready = bool(row["mve2_ready_price_data"])
        layer = str(row["layer"])
        reason = str(row.get("mve2_ready_reason", ""))
        if ticker in MANDATORY_EXCLUDED:
            excluded_rows.append(
                {
                    "ticker": ticker,
                    "layer": layer,
                    "source_reason": reason,
                    "exclusion_reason": MANDATORY_EXCLUDE_REASON,
                    "run_scope": RUN_SCOPE,
                }
            )
            continue
        if not ready:
            excluded_rows.append(
                {
                    "ticker": ticker,
                    "layer": layer,
                    "source_reason": reason,
                    "exclusion_reason": "mve2_ready_price_data_false",
                    "run_scope": RUN_SCOPE,
                }
            )
            continue
        bucket = bucket_for_row(ticker, layer)
        if bucket is None:
            excluded_rows.append(
                {
                    "ticker": ticker,
                    "layer": layer,
                    "source_reason": reason,
                    "exclusion_reason": "layer_not_allowed_for_limited_mve2",
                    "run_scope": RUN_SCOPE,
                }
            )
            continue
        rows.append(
            {
                "ticker": ticker,
                "layer": layer,
                "bucket_id": bucket[0],
                "bucket": bucket[1],
                "bucket_type": bucket[2],
                "mve2_ready_price_data": True,
                "eligibility_reason": "ready_10y_plus_unified_adj_close_volume",
                "run_scope": RUN_SCOPE,
            }
        )

    eligible = pd.DataFrame(rows).sort_values(["bucket_id", "ticker"]).reset_index(drop=True)
    excluded = pd.DataFrame(excluded_rows).sort_values("ticker").reset_index(drop=True)
    bucket_rows = []
    if not eligible.empty:
        for (bucket_id, bucket, bucket_type), g in eligible.groupby(["bucket_id", "bucket", "bucket_type"]):
            notes = ""
            if bucket_id == "Bucket D":
                notes = "Leveraged ETFs are ranked separately and not mixed with ordinary tickers."
            elif bucket_id == "Bucket F":
                notes = "Observation bucket only; MSTR does not represent full Layer5 readiness."
            bucket_rows.append(
                {
                    "bucket_id": bucket_id,
                    "bucket": bucket,
                    "bucket_type": bucket_type,
                    "ticker_count": int(g["ticker"].nunique()),
                    "tickers": ",".join(sorted(g["ticker"].unique())),
                    "run_scope": RUN_SCOPE,
                    "notes": notes,
                }
            )
    bucket_def = pd.DataFrame(bucket_rows).sort_values("bucket_id").reset_index(drop=True)
    return eligible, excluded, bucket_def


def read_price(store_dir: Path, ticker: str) -> pd.DataFrame:
    path = store_dir / "prices" / f"{ticker}.parquet"
    if not path.exists():
        csv_path = store_dir / "prices" / f"{ticker}.csv"
        if csv_path.exists():
            path = csv_path
        else:
            raise FileNotFoundError(f"Missing price file for {ticker}: {path}")

    if path.suffix.lower() == ".parquet":
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path)
    required = {"date", "adj_close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{ticker} price file missing required columns: {sorted(missing)}")
    df = df[["date", "adj_close", "volume"]].copy()
    df["date"] = pd.to_datetime(df["date"])
    df["adj_close"] = pd.to_numeric(df["adj_close"], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
    df = df.dropna(subset=["date"]).drop_duplicates("date").sort_values("date")
    df = df[df["adj_close"].notna() & df["volume"].notna()]
    df = df[(df["adj_close"] > 0) & (df["volume"] >= 0)]
    df = df.reset_index(drop=True)
    if df.empty:
        raise ValueError(f"{ticker} has no usable adj_close/volume rows")
    return df


def common_backtest_window(price_data: Dict[str, pd.DataFrame], requested_start: str) -> Tuple[pd.Timestamp, pd.Timestamp]:
    first_dates = [df["date"].min() for df in price_data.values()]
    last_dates = [df["date"].max() for df in price_data.values()]
    common_start = max(first_dates)
    requested = pd.Timestamp(requested_start)
    start = max(common_start, requested)
    end = min(last_dates)
    if start >= end:
        raise ValueError(f"Invalid common backtest window: {start} to {end}")
    return start, end


def prepare_price_frame(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    out = df[(df["date"] >= start) & (df["date"] <= end)].copy()
    out = out.sort_values("date").reset_index(drop=True)
    out["return"] = out["adj_close"].pct_change().fillna(0.0)
    return out


def run_buy_hold(df: pd.DataFrame, params: Dict[str, object]) -> pd.Series:
    return pd.Series(1.0, index=df.index)


def run_sma_cross(df: pd.DataFrame, params: Dict[str, object]) -> pd.Series:
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
    ret = df["return"]
    vol = ret.rolling(window, min_periods=window).std() * math.sqrt(TRADING_DAYS)
    threshold = vol.rolling(252, min_periods=60).median()
    mom = df["adj_close"].pct_change(63) > 0
    signal = (vol <= threshold) & mom
    return signal.astype(float).fillna(0.0)


def run_drawdown_stop(df: pd.DataFrame, params: Dict[str, object]) -> pd.Series:
    stop = float(params["stop"])
    price = df["adj_close"]
    peak = price.cummax()
    drawdown = price / peak - 1.0
    signal = drawdown >= -stop
    return signal.astype(float).fillna(0.0)


def run_atr_proxy_stop(df: pd.DataFrame, params: Dict[str, object]) -> pd.Series:
    window = int(params["window"])
    multiplier = float(params["multiplier"])
    price = df["adj_close"]
    # The unified limited MVE2 scope permits adj_close and volume only.
    # This is therefore an audited adj_close ATR proxy, not raw high/low ATR.
    atr_proxy = price.diff().abs().rolling(window, min_periods=window).mean()
    trailing_peak = price.cummax()
    stop_line = trailing_peak - multiplier * atr_proxy
    signal = price > stop_line
    return signal.astype(float).fillna(0.0)


def apply_confirm_cooldown(raw_signal: pd.Series, confirm_days: int, cooldown_days: int) -> pd.Series:
    raw_bool = raw_signal.astype(bool).fillna(False).to_numpy()
    out = np.zeros(len(raw_bool), dtype=float)
    cooldown_left = 0
    true_streak = 0
    in_position = False
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
    fast = int(params.get("fast", 50))
    slow = int(params.get("slow", 200))
    cooldown = int(params["cooldown"])
    confirm = int(params["confirm"])
    raw = run_sma_cross(df, {"fast": fast, "slow": slow})
    return apply_confirm_cooldown(raw, confirm, cooldown)


def make_strategy_specs() -> List[StrategySpec]:
    specs: List[StrategySpec] = [
        StrategySpec("buy_and_hold", "buy_and_hold", {}, run_buy_hold),
    ]
    for fast, slow in [(50, 200), (100, 200), (20, 120)]:
        specs.append(StrategySpec("sma_trend_following", f"sma_{fast}_{slow}", {"fast": fast, "slow": slow}, run_sma_cross))
    for window in [63, 126, 252]:
        specs.append(StrategySpec("time_series_momentum", f"ts_mom_{window}d", {"window": window}, run_time_series_momentum))
    for window in [20, 63]:
        specs.append(
            StrategySpec(
                "volatility_filter",
                f"vol_filter_{window}d",
                {"window": window, "threshold": "rolling_median_252", "requires_positive_63d_momentum": True},
                run_volatility_filter,
            )
        )
    for stop in [0.10, 0.15, 0.20]:
        specs.append(StrategySpec("drawdown_trailing_stop_filter", f"trailing_stop_{int(stop*100)}pct", {"stop": stop}, run_drawdown_stop))
    for window in [14, 18, 22]:
        for multiplier in [2.0, 2.5, 3.0]:
            specs.append(
                StrategySpec(
                    "atr_trailing_stop_adj_close_proxy",
                    f"atr_proxy_{window}_{str(multiplier).replace('.', 'p')}",
                    {"window": window, "multiplier": multiplier, "price_input": "adj_close_only"},
                    run_atr_proxy_stop,
                )
            )
    for cooldown in [0, 5, 10]:
        for confirm in [0, 1, 2]:
            specs.append(
                StrategySpec(
                    "cooldown_confirmation",
                    f"sma50_200_cooldown_{cooldown}_confirm_{confirm}",
                    {"fast": 50, "slow": 200, "cooldown": cooldown, "confirm": confirm},
                    run_cooldown_confirmation,
                )
            )
    return specs


def max_drawdown(equity: pd.Series) -> Tuple[float, Optional[pd.Timestamp], Optional[pd.Timestamp]]:
    if equity.empty:
        return np.nan, None, None
    running_peak = equity.cummax()
    dd = equity / running_peak - 1.0
    trough_idx = dd.idxmin()
    peak_idx = equity.loc[:trough_idx].idxmax() if trough_idx in equity.index else None
    return float(dd.min()), peak_idx, trough_idx


def average_holding_days(position: pd.Series) -> float:
    pos = position.fillna(0).astype(int).to_numpy()
    lengths = []
    current = 0
    for value in pos:
        if value == 1:
            current += 1
        elif current > 0:
            lengths.append(current)
            current = 0
    if current > 0:
        lengths.append(current)
    return float(np.mean(lengths)) if lengths else 0.0


def compute_metrics(
    dates: pd.Series,
    daily_returns: pd.Series,
    position: pd.Series,
    benchmark_returns: Optional[pd.Series] = None,
) -> Dict[str, object]:
    rets = daily_returns.fillna(0.0)
    pos = position.fillna(0.0)
    n = int(len(rets))
    if n <= 1:
        return {}
    equity = (1.0 + rets).cumprod()
    total_return = float(equity.iloc[-1] - 1.0)
    years = n / TRADING_DAYS
    cagr = float(equity.iloc[-1] ** (1.0 / years) - 1.0) if years > 0 and equity.iloc[-1] > 0 else np.nan
    annual_return = float(rets.mean() * TRADING_DAYS)
    annual_vol = float(rets.std(ddof=0) * math.sqrt(TRADING_DAYS))
    sharpe = float(annual_return / annual_vol) if annual_vol > 0 else np.nan
    downside = rets[rets < 0]
    downside_vol = float(downside.std(ddof=0) * math.sqrt(TRADING_DAYS)) if len(downside) else 0.0
    sortino = float(annual_return / downside_vol) if downside_vol > 0 else np.nan
    mdd, mdd_peak, mdd_trough = max_drawdown(equity)
    def resolve_metric_date(index_value: object) -> str:
        if index_value is None:
            return ""
        if hasattr(index_value, "date"):
            return index_value.date().isoformat()
        try:
            idx = int(index_value)
            if 0 <= idx < len(dates):
                return pd.Timestamp(dates.iloc[idx]).date().isoformat()
        except Exception:
            return ""
        return ""
    calmar = float(cagr / abs(mdd)) if pd.notna(cagr) and pd.notna(mdd) and mdd < 0 else np.nan
    active_rets = rets[pos > 0]
    win_rate = float((active_rets > 0).mean()) if len(active_rets) else np.nan
    changes = pos.diff().abs().fillna(pos.iloc[0] if len(pos) else 0.0)
    trade_count = int((changes > 0).sum())
    turnover = float(changes.sum() / years) if years > 0 else np.nan
    exposure_ratio = float(pos.mean()) if n else np.nan

    bench_cagr = np.nan
    bench_mdd = np.nan
    if benchmark_returns is not None and len(benchmark_returns) == n:
        bench_equity = (1.0 + benchmark_returns.fillna(0.0)).cumprod()
        bench_cagr = (
            float(bench_equity.iloc[-1] ** (1.0 / years) - 1.0)
            if years > 0 and bench_equity.iloc[-1] > 0
            else np.nan
        )
        bench_mdd, _, _ = max_drawdown(bench_equity)

    return {
        "start_date": dates.iloc[0].date().isoformat(),
        "end_date": dates.iloc[-1].date().isoformat(),
        "n_trading_days": n,
        "CAGR": cagr,
        "annual_return": annual_return,
        "annual_volatility": annual_vol,
        "Sharpe": sharpe,
        "Sortino": sortino,
        "max_drawdown": mdd,
        "Calmar": calmar,
        "win_rate": win_rate,
        "turnover": turnover,
        "average_holding_days": average_holding_days(pos),
        "trade_count": trade_count,
        "exposure_ratio": exposure_ratio,
        "benchmark_CAGR": bench_cagr,
        "benchmark_MDD": bench_mdd,
        "excess_CAGR_vs_benchmark": cagr - bench_cagr if pd.notna(cagr) and pd.notna(bench_cagr) else np.nan,
        "MDD_reduction_vs_benchmark": abs(bench_mdd) - abs(mdd) if pd.notna(bench_mdd) and pd.notna(mdd) else np.nan,
        "total_return": total_return,
        "max_drawdown_peak_date": resolve_metric_date(mdd_peak),
        "max_drawdown_trough_date": resolve_metric_date(mdd_trough),
    }


def strategy_returns(df: pd.DataFrame, position: pd.Series) -> pd.Series:
    # Position is known after close; returns are earned from the next trading day.
    shifted = position.fillna(0.0).shift(1).fillna(0.0)
    return shifted * df["return"].fillna(0.0)


def choose_primary_benchmark(bucket_id: str, ticker: str) -> str:
    if ticker == "QQQ":
        return "SPY"
    if bucket_id == "Bucket B":
        return "SPY"
    return "QQQ"


def make_candidate_id(bucket_id: str, ticker: str, spec: StrategySpec) -> str:
    params = json.dumps(spec.parameters, sort_keys=True, separators=(",", ":"))
    safe = params.replace("{", "").replace("}", "").replace('"', "").replace(":", "_").replace(",", "_").replace(".", "p")
    safe = safe.replace(" ", "")
    return f"{RUN_SCOPE}|{bucket_id}|{ticker}|{spec.family}|{spec.name}|{safe}"


def run_all_strategies(
    eligible: pd.DataFrame,
    price_data: Dict[str, pd.DataFrame],
    benchmarks: Dict[str, pd.Series],
    specs: List[StrategySpec],
) -> Tuple[pd.DataFrame, Dict[str, Dict[str, object]]]:
    results = []
    detail_cache: Dict[str, Dict[str, object]] = {}
    benchmark_names = list(benchmarks.keys())

    for _, row in eligible.iterrows():
        ticker = row["ticker"]
        bucket_id = row["bucket_id"]
        bucket = row["bucket"]
        df = price_data[ticker].reset_index(drop=True)
        buy_hold_returns = df["return"].fillna(0.0)
        bh_metrics = compute_metrics(df["date"], buy_hold_returns, pd.Series(1.0, index=df.index))
        primary_benchmark = choose_primary_benchmark(bucket_id, ticker)
        primary_bench_rets = benchmarks.get(primary_benchmark)
        spy_metrics = {}
        qqq_metrics = {}
        if "SPY" in benchmarks:
            spy_metrics = compute_metrics(df["date"], benchmarks["SPY"], pd.Series(1.0, index=df.index))
        if "QQQ" in benchmarks:
            qqq_metrics = compute_metrics(df["date"], benchmarks["QQQ"], pd.Series(1.0, index=df.index))

        for spec in specs:
            try:
                position = spec.runner(df, spec.parameters).reindex(df.index).fillna(0.0).clip(0.0, 1.0)
                rets = strategy_returns(df, position)
                metrics = compute_metrics(df["date"], rets, position, primary_bench_rets)
                if not metrics:
                    continue
                candidate_id = make_candidate_id(bucket_id, ticker, spec)
                row_out = {
                    "run_scope": RUN_SCOPE,
                    "candidate_id": candidate_id,
                    "bucket_id": bucket_id,
                    "bucket": bucket,
                    "bucket_type": row["bucket_type"],
                    "ticker": ticker,
                    "ticker_group": ticker,
                    "strategy_family": spec.family,
                    "strategy_name": spec.name,
                    "parameters": json.dumps(spec.parameters, sort_keys=True),
                    "benchmark_name": primary_benchmark,
                    "notes": "limited_mve2;uses_unified_store_adj_close_and_volume_only",
                }
                row_out.update(metrics)
                row_out.update(
                    {
                        "buy_hold_CAGR": bh_metrics.get("CAGR", np.nan),
                        "buy_hold_MDD": bh_metrics.get("max_drawdown", np.nan),
                        "buy_hold_Calmar": bh_metrics.get("Calmar", np.nan),
                        "excess_CAGR_vs_buy_hold": metrics.get("CAGR", np.nan) - bh_metrics.get("CAGR", np.nan),
                        "MDD_reduction_vs_buy_hold": abs(bh_metrics.get("max_drawdown", np.nan)) - abs(metrics.get("max_drawdown", np.nan)),
                        "spy_CAGR": spy_metrics.get("CAGR", np.nan),
                        "spy_MDD": spy_metrics.get("max_drawdown", np.nan),
                        "qqq_CAGR": qqq_metrics.get("CAGR", np.nan),
                        "qqq_MDD": qqq_metrics.get("max_drawdown", np.nan),
                    }
                )
                results.append(row_out)
                detail_cache[candidate_id] = {
                    "dates": df["date"].copy(),
                    "returns": rets.copy(),
                    "position": position.copy(),
                    "ticker_returns": df["return"].copy(),
                    "ticker": ticker,
                    "bucket_id": bucket_id,
                    "bucket": bucket,
                    "spec": spec,
                }
            except Exception as exc:  # noqa: BLE001 - audit must continue per ticker/strategy.
                candidate_id = make_candidate_id(bucket_id, ticker, spec)
                results.append(
                    {
                        "run_scope": RUN_SCOPE,
                        "candidate_id": candidate_id,
                        "bucket_id": bucket_id,
                        "bucket": bucket,
                        "bucket_type": row["bucket_type"],
                        "ticker": ticker,
                        "ticker_group": ticker,
                        "strategy_family": spec.family,
                        "strategy_name": spec.name,
                        "parameters": json.dumps(spec.parameters, sort_keys=True),
                        "notes": f"strategy_failed:{exc}",
                    }
                )
    return pd.DataFrame(results), detail_cache


def select_candidates(results: pd.DataFrame, set_name: str, mdd_limit: float, rank_cols: List[str], top_n: int) -> pd.DataFrame:
    df = results.copy()
    df = df[pd.to_numeric(df["max_drawdown"], errors="coerce").abs() <= mdd_limit]
    df = df[pd.to_numeric(df["CAGR"], errors="coerce").notna()]
    selected = []
    for bucket_id, g in df.groupby("bucket_id"):
        sort_ascending = [False for _ in rank_cols]
        out = g.sort_values(rank_cols, ascending=sort_ascending).head(top_n).copy()
        out.insert(0, "candidate_set", set_name)
        out["rank_within_bucket"] = range(1, len(out) + 1)
        selected.append(out)
    return pd.concat(selected, ignore_index=True) if selected else pd.DataFrame()


def benchmark_results(price_data: Dict[str, pd.DataFrame], benchmark_tickers: Iterable[str]) -> pd.DataFrame:
    rows = []
    for ticker in benchmark_tickers:
        if ticker not in price_data:
            continue
        df = price_data[ticker]
        pos = pd.Series(1.0, index=df.index)
        metrics = compute_metrics(df["date"], df["return"], pos)
        row = {
            "run_scope": RUN_SCOPE,
            "benchmark_ticker": ticker,
            "strategy": "buy_and_hold",
            "notes": "benchmark_from_unified_store_adj_close",
        }
        row.update(metrics)
        rows.append(row)
    return pd.DataFrame(rows)


def period_slices() -> Dict[str, Tuple[str, str]]:
    return {
        "full_period": ("1900-01-01", "2100-01-01"),
        "2016_2020": ("2016-01-01", "2020-12-31"),
        "2021_2026": ("2021-01-01", "2026-12-31"),
        "covid_crash": ("2020-02-19", "2020-03-23"),
        "bear_market_2022": ("2022-01-03", "2022-12-30"),
        "recovery_ai_bull_2023_2026": ("2023-01-01", "2026-12-31"),
    }


def make_period_slice_results(results: pd.DataFrame, detail_cache: Dict[str, Dict[str, object]]) -> pd.DataFrame:
    rows = []
    slices = period_slices()
    for _, row in results.iterrows():
        cid = row.get("candidate_id")
        if cid not in detail_cache:
            continue
        detail = detail_cache[cid]
        dates = detail["dates"]
        rets = detail["returns"]
        pos = detail["position"]
        for slice_name, (start_s, end_s) in slices.items():
            start = pd.Timestamp(start_s)
            end = pd.Timestamp(end_s)
            mask = (dates >= start) & (dates <= end)
            if slice_name == "full_period":
                mask = pd.Series(True, index=dates.index)
            if int(mask.sum()) < MIN_SLICE_DAYS:
                rows.append(
                    {
                        "run_scope": RUN_SCOPE,
                        "candidate_id": cid,
                        "bucket_id": row.get("bucket_id"),
                        "bucket": row.get("bucket"),
                        "ticker": row.get("ticker"),
                        "strategy_family": row.get("strategy_family"),
                        "strategy_name": row.get("strategy_name"),
                        "period_slice": slice_name,
                        "slice_status": "insufficient_slice_data",
                        "n_trading_days": int(mask.sum()),
                    }
                )
                continue
            metrics = compute_metrics(dates[mask].reset_index(drop=True), rets[mask].reset_index(drop=True), pos[mask].reset_index(drop=True))
            out = {
                "run_scope": RUN_SCOPE,
                "candidate_id": cid,
                "bucket_id": row.get("bucket_id"),
                "bucket": row.get("bucket"),
                "ticker": row.get("ticker"),
                "strategy_family": row.get("strategy_family"),
                "strategy_name": row.get("strategy_name"),
                "period_slice": slice_name,
                "slice_status": "ok",
            }
            out.update(metrics)
            rows.append(out)
    return pd.DataFrame(rows)


def yearly_returns(dates: pd.Series, returns: pd.Series) -> pd.Series:
    df = pd.DataFrame({"date": dates, "return": returns})
    df["year"] = df["date"].dt.year
    return df.groupby("year")["return"].apply(lambda x: (1.0 + x).prod() - 1.0)


def robustness_checks(top_rows: pd.DataFrame, detail_cache: Dict[str, Dict[str, object]]) -> pd.DataFrame:
    rows = []
    for _, row in top_rows.drop_duplicates("candidate_id").iterrows():
        cid = row["candidate_id"]
        if cid not in detail_cache:
            continue
        detail = detail_cache[cid]
        dates = detail["dates"]
        rets = detail["returns"]
        pos = detail["position"]
        yr = yearly_returns(dates, rets)
        positive = yr[yr > 0]
        pos_sum = float(positive.sum()) if len(positive) else 0.0
        top_year_share = float(positive.max() / pos_sum) if pos_sum > 0 else np.nan
        share_2020 = float(yr.get(2020, 0.0) / pos_sum) if pos_sum > 0 and yr.get(2020, 0.0) > 0 else 0.0
        share_2023_2025 = float(yr.loc[[y for y in [2023, 2024, 2025] if y in yr.index]].clip(lower=0).sum() / pos_sum) if pos_sum > 0 else np.nan
        equity = (1.0 + rets.fillna(0.0)).cumprod()
        mdd, mdd_peak, mdd_trough = max_drawdown(equity)
        def resolve_detail_date(index_value: object) -> str:
            if index_value is None:
                return ""
            if hasattr(index_value, "date"):
                return index_value.date().isoformat()
            try:
                idx = int(index_value)
                if 0 <= idx < len(dates):
                    return pd.Timestamp(dates.iloc[idx]).date().isoformat()
            except Exception:
                return ""
            return ""
        trade_count = int(row.get("trade_count", 0))
        turnover = float(row.get("turnover", np.nan))
        cagr = float(row.get("CAGR", np.nan))
        bh_cagr = float(row.get("buy_hold_CAGR", np.nan))
        mdd_reduction = float(row.get("MDD_reduction_vs_buy_hold", np.nan))
        flags = []
        if top_year_share > 0.50:
            flags.append("positive_return_concentrated_in_top_year")
        if share_2020 > 0.35:
            flags.append("depends_on_2020")
        if share_2023_2025 > 0.75:
            flags.append("depends_on_2023_2025")
        if trade_count < 3 and row.get("strategy_family") != "buy_and_hold":
            flags.append("trade_count_too_low")
        if turnover > 20:
            flags.append("turnover_high")
        if pd.notna(cagr) and pd.notna(bh_cagr) and cagr < bh_cagr and mdd_reduction < 0.05:
            flags.append("lower_return_without_material_mdd_reduction")
        rows.append(
            {
                "run_scope": RUN_SCOPE,
                "candidate_id": cid,
                "bucket_id": row.get("bucket_id"),
                "bucket": row.get("bucket"),
                "ticker": row.get("ticker"),
                "strategy_family": row.get("strategy_family"),
                "strategy_name": row.get("strategy_name"),
                "parameters": row.get("parameters"),
                "CAGR": cagr,
                "Calmar": row.get("Calmar"),
                "max_drawdown": row.get("max_drawdown"),
                "top_positive_year_share": top_year_share,
                "positive_return_share_2020": share_2020,
                "positive_return_share_2023_2025": share_2023_2025,
                "trade_count": trade_count,
                "turnover": turnover,
                "mdd_peak_date": resolve_detail_date(mdd_peak),
                "mdd_trough_date": resolve_detail_date(mdd_trough),
                "robustness_flags": ";".join(flags) if flags else "no_major_flag",
                "notes": "limited_mve2_top_candidate_screen",
            }
        )
    return pd.DataFrame(rows)


def make_neighbor_specs(spec: StrategySpec) -> List[StrategySpec]:
    p = dict(spec.parameters)
    family = spec.family
    neighbors: List[StrategySpec] = []
    if family == "sma_trend_following" or family == "cooldown_confirmation":
        fast = int(p.get("fast", 50))
        slow = int(p.get("slow", 200))
        for nf, ns in [(max(5, fast - 10), slow), (fast + 10, slow), (fast, max(fast + 20, slow - 20)), (fast, slow + 20)]:
            np_ = dict(p)
            np_["fast"] = nf
            np_["slow"] = ns
            name = f"neighbor_sma_{nf}_{ns}"
            runner = run_cooldown_confirmation if family == "cooldown_confirmation" else run_sma_cross
            neighbors.append(StrategySpec(family, name, np_, runner))
    elif family == "time_series_momentum":
        window = int(p["window"])
        for nw in sorted({max(21, window - 21), window + 21}):
            neighbors.append(StrategySpec(family, f"neighbor_ts_mom_{nw}d", {"window": nw}, run_time_series_momentum))
    elif family == "volatility_filter":
        window = int(p["window"])
        for nw in sorted({max(10, window - 10), window + 10}):
            neighbors.append(
                StrategySpec(
                    family,
                    f"neighbor_vol_filter_{nw}d",
                    {"window": nw, "threshold": "rolling_median_252", "requires_positive_63d_momentum": True},
                    run_volatility_filter,
                )
            )
    elif family == "drawdown_trailing_stop_filter":
        stop = float(p["stop"])
        for ns in sorted({max(0.05, stop - 0.05), min(0.35, stop + 0.05)}):
            neighbors.append(StrategySpec(family, f"neighbor_trailing_stop_{int(ns*100)}pct", {"stop": ns}, run_drawdown_stop))
    elif family == "atr_trailing_stop_adj_close_proxy":
        window = int(p["window"])
        multiplier = float(p["multiplier"])
        for nw, nm in [(max(5, window - 4), multiplier), (window + 4, multiplier), (window, max(1.0, multiplier - 0.5)), (window, multiplier + 0.5)]:
            neighbors.append(
                StrategySpec(
                    family,
                    f"neighbor_atr_proxy_{nw}_{str(nm).replace('.', 'p')}",
                    {"window": nw, "multiplier": nm, "price_input": "adj_close_only"},
                    run_atr_proxy_stop,
                )
            )
    return neighbors


def parameter_neighborhood_checks(top_rows: pd.DataFrame, detail_cache: Dict[str, Dict[str, object]]) -> pd.DataFrame:
    rows = []
    for _, row in top_rows.drop_duplicates("candidate_id").iterrows():
        cid = row["candidate_id"]
        if cid not in detail_cache:
            continue
        detail = detail_cache[cid]
        base_spec: StrategySpec = detail["spec"]
        if base_spec.family == "buy_and_hold":
            continue
        df = pd.DataFrame(
            {
                "date": detail["dates"].reset_index(drop=True),
                "return": detail["ticker_returns"].reset_index(drop=True),
            }
        )
        # Reconstruct adj_close from returns for neighbor signal functions.
        df["adj_close"] = (1.0 + df["return"]).cumprod()
        df["volume"] = 1.0
        base_cagr = float(row.get("CAGR", np.nan))
        base_calmar = float(row.get("Calmar", np.nan))
        neighbors = make_neighbor_specs(base_spec)
        if not neighbors:
            rows.append(
                {
                    "run_scope": RUN_SCOPE,
                    "candidate_id": cid,
                    "neighbor_name": "",
                    "neighbor_parameters": "",
                    "neighbor_status": "no_neighbor_defined",
                }
            )
            continue
        for spec in neighbors:
            try:
                pos = spec.runner(df, spec.parameters).fillna(0.0).clip(0.0, 1.0)
                rets = strategy_returns(df, pos)
                metrics = compute_metrics(df["date"], rets, pos)
                cagr_drop = base_cagr - metrics.get("CAGR", np.nan)
                calmar_drop_ratio = (
                    metrics.get("Calmar", np.nan) / base_calmar
                    if pd.notna(base_calmar) and base_calmar != 0 and pd.notna(metrics.get("Calmar", np.nan))
                    else np.nan
                )
                cliff = bool(
                    (pd.notna(cagr_drop) and cagr_drop > 0.20)
                    or (pd.notna(calmar_drop_ratio) and calmar_drop_ratio < 0.50)
                )
                rows.append(
                    {
                        "run_scope": RUN_SCOPE,
                        "candidate_id": cid,
                        "ticker": row.get("ticker"),
                        "bucket_id": row.get("bucket_id"),
                        "base_strategy": row.get("strategy_name"),
                        "base_parameters": row.get("parameters"),
                        "base_CAGR": base_cagr,
                        "base_Calmar": base_calmar,
                        "neighbor_name": spec.name,
                        "neighbor_parameters": json.dumps(spec.parameters, sort_keys=True),
                        "neighbor_CAGR": metrics.get("CAGR", np.nan),
                        "neighbor_Calmar": metrics.get("Calmar", np.nan),
                        "neighbor_max_drawdown": metrics.get("max_drawdown", np.nan),
                        "CAGR_drop_vs_base": cagr_drop,
                        "Calmar_ratio_vs_base": calmar_drop_ratio,
                        "cliff_drop_flag": cliff,
                        "neighbor_status": "ok",
                    }
                )
            except Exception as exc:  # noqa: BLE001
                rows.append(
                    {
                        "run_scope": RUN_SCOPE,
                        "candidate_id": cid,
                        "neighbor_name": spec.name,
                        "neighbor_parameters": json.dumps(spec.parameters, sort_keys=True),
                        "neighbor_status": f"failed:{exc}",
                    }
                )
    return pd.DataFrame(rows)


def bucket_summary(results: pd.DataFrame, bucket_def: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, b in bucket_def.iterrows():
        bucket_id = b["bucket_id"]
        g = results[results["bucket_id"] == bucket_id].copy()
        if g.empty:
            continue
        g_valid = g[pd.to_numeric(g["CAGR"], errors="coerce").notna()]
        best_cagr = g_valid.sort_values("CAGR", ascending=False).head(1)
        best_calmar = g_valid.sort_values("Calmar", ascending=False).head(1)
        best_conservative = g_valid[g_valid["max_drawdown"].abs() <= 0.30].sort_values(["Calmar", "Sharpe"], ascending=False).head(1)
        rows.append(
            {
                "run_scope": RUN_SCOPE,
                "bucket_id": bucket_id,
                "bucket": b["bucket"],
                "ticker_count": int(b["ticker_count"]),
                "strategy_count": int(len(g_valid)),
                "best_CAGR_candidate": best_cagr.iloc[0]["candidate_id"] if len(best_cagr) else "",
                "best_CAGR": best_cagr.iloc[0]["CAGR"] if len(best_cagr) else np.nan,
                "best_CAGR_MDD": best_cagr.iloc[0]["max_drawdown"] if len(best_cagr) else np.nan,
                "best_Calmar_candidate": best_calmar.iloc[0]["candidate_id"] if len(best_calmar) else "",
                "best_Calmar": best_calmar.iloc[0]["Calmar"] if len(best_calmar) else np.nan,
                "best_Calmar_CAGR": best_calmar.iloc[0]["CAGR"] if len(best_calmar) else np.nan,
                "best_conservative_candidate": best_conservative.iloc[0]["candidate_id"] if len(best_conservative) else "",
                "best_conservative_Calmar": best_conservative.iloc[0]["Calmar"] if len(best_conservative) else np.nan,
                "notes": b.get("notes", ""),
            }
        )
    return pd.DataFrame(rows)


def not_recommended(results: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in results.iterrows():
        reasons = []
        mdd = row.get("max_drawdown", np.nan)
        cagr = row.get("CAGR", np.nan)
        calmar = row.get("Calmar", np.nan)
        exposure = row.get("exposure_ratio", np.nan)
        trade_count = row.get("trade_count", np.nan)
        if pd.notna(mdd) and abs(mdd) > 0.50:
            reasons.append("max_drawdown_gt_50pct")
        if pd.notna(cagr) and cagr < 0:
            reasons.append("negative_CAGR")
        if pd.notna(calmar) and calmar < 0.5:
            reasons.append("low_Calmar")
        if pd.notna(exposure) and exposure < 0.10:
            reasons.append("exposure_too_low")
        if row.get("strategy_family") != "buy_and_hold" and pd.notna(trade_count) and trade_count < 2:
            reasons.append("trade_count_too_low")
        if reasons:
            out = row[[
                "run_scope",
                "candidate_id",
                "bucket_id",
                "bucket",
                "ticker",
                "strategy_family",
                "strategy_name",
                "parameters",
                "CAGR",
                "max_drawdown",
                "Calmar",
                "trade_count",
                "turnover",
            ]].to_dict()
            out["not_recommended_reason"] = ";".join(reasons)
            rows.append(out)
    return pd.DataFrame(rows)


def write_readme(
    out_dir: Path,
    eligible: pd.DataFrame,
    excluded: pd.DataFrame,
    bucket_def: pd.DataFrame,
    bucket_sum: pd.DataFrame,
    return_max: pd.DataFrame,
    risk_adj: pd.DataFrame,
    conservative: pd.DataFrame,
    robustness: pd.DataFrame,
    neighborhood: pd.DataFrame,
) -> None:
    layer4 = bucket_sum[bucket_sum["bucket_id"] == "Bucket D"]
    layer3 = bucket_sum[bucket_sum["bucket_id"] == "Bucket C"]
    cliff_count = int(neighborhood.get("cliff_drop_flag", pd.Series(dtype=bool)).fillna(False).sum()) if not neighborhood.empty else 0
    top_return = return_max.head(10)[["bucket_id", "ticker", "strategy_name", "CAGR", "max_drawdown", "Calmar"]] if not return_max.empty else pd.DataFrame()
    top_risk = risk_adj.head(10)[["bucket_id", "ticker", "strategy_name", "CAGR", "max_drawdown", "Calmar"]] if not risk_adj.empty else pd.DataFrame()
    top_cons = conservative.head(10)[["bucket_id", "ticker", "strategy_name", "CAGR", "max_drawdown", "Calmar"]] if not conservative.empty else pd.DataFrame()

    def table(df: pd.DataFrame) -> str:
        if df.empty:
            return "无。"
        return df.to_markdown(index=False, floatfmt=".4f")

    readme = f"""# limited MVE2 初筛摘要

## 1. 本轮任务目标

本轮只启动受限版 `limited_mve2`，在统一 adjusted OHLCV store 中已通过 10 年以上价格数据 readiness 的 ticker 上做初步策略搜索。所有收益、波动、回撤和信号均基于 `adj_close` 和 `volume`，不使用旧 qlib provider、旧 v8 cache 或未审计数据。

## 2. 为什么是 limited MVE2，而不是 formal MVE2

本轮仍属于预研后的最小实验：只使用 40 个 ready ticker，排除上市历史不足 10 年或 MVE2 not ready 的 ticker，不做正式 universe 扩张，不训练模型，不做全量参数寻优，也不把结果外推到被排除 ticker。

## 3. eligible / excluded universe

- eligible ticker 数量：{eligible['ticker'].nunique()}
- excluded ticker 数量：{excluded['ticker'].nunique()}
- excluded ticker：{', '.join(excluded['ticker'].tolist())}
- 排除原因：`{MANDATORY_EXCLUDE_REASON}` 或非本轮允许 layer / readiness 不通过。

## 4. Bucket 数量

{table(bucket_def[['bucket_id', 'bucket', 'ticker_count', 'tickers']])}

## 5. 每个 bucket 的最优候选

{table(bucket_sum[['bucket_id', 'bucket', 'ticker_count', 'best_CAGR_candidate', 'best_CAGR', 'best_Calmar_candidate', 'best_Calmar']])}

## 6. Layer4 leveraged ETF 单独结论

Layer4 杠杆 ETF 已单独成桶，未与普通股票/ETF 混排。该桶适合继续做单独风险预算和回撤约束验证；不能把其高 CAGR 直接与普通 equity bucket 混合解读。

{table(layer4[['bucket_id', 'best_CAGR_candidate', 'best_CAGR', 'best_CAGR_MDD', 'best_Calmar_candidate', 'best_Calmar']] if not layer4.empty else pd.DataFrame())}

## 7. Layer3 Sector/theme ETF 改善后结论

Layer3 在统一 store 后已可纳入 limited MVE2，9/9 ready。本轮结果可作为下一步 validation 的候选来源，但仍需要更严格切片、成本和样本外验证。

{table(layer3[['bucket_id', 'best_CAGR_candidate', 'best_CAGR', 'best_Calmar_candidate', 'best_Calmar']] if not layer3.empty else pd.DataFrame())}

## 8. High-beta observation bucket 限制说明

Bucket F 仅包含 ready 的 MSTR，属于观察桶，不代表完整 Layer5 high-beta single names。Layer5 大部分 ticker 仍因上市历史不足 10 年被排除，因此不能形成 Layer5 整体策略结论。

## 9. 收益最大化候选 Top 10

{table(top_return)}

## 10. 风险调整候选 Top 10

{table(top_risk)}

## 11. 保守候选 Top 10

{table(top_cons)}

## 12. Top candidates 主要风险

稳健性检查输出在 `top_candidate_robustness_checks_limited_mve2.csv`。需要重点关注：正收益是否集中在少数年份、是否依赖 2020 或 2023-2025、交易次数过少、换手过高、相对 buy-and-hold 是否只是降低收益但没有实质降低回撤。

## 13. 参数邻域稳定性

- 参数邻域检查行数：{len(neighborhood)}
- cliff_drop_flag 数量：{cliff_count}

若存在 cliff drop，下一步 validation 必须优先排查该候选是否为窄参数偶然结果。

## 14. 是否建议进入下一步 MVE2 validation

建议进入“受限版 MVE2 validation”，不建议进入 formal MVE2。下一步只应验证本轮筛出的少量候选，并继续保持 Layer4 单独成桶、Layer5 仅 MSTR 观察、不扩入 excluded ticker。

## 15. 建议重点验证候选

优先验证各 bucket 中 Calmar 较高且 MDD 受控、参数邻域没有明显 cliff drop 的候选；对 Layer4 仅做单独风险控制验证，不与普通股票策略混合排名。
"""
    out_dir.joinpath("README_summary.md").write_text(readme, encoding="utf-8")


def copy_script(out_dir: Path) -> None:
    src = Path(__file__).resolve()
    dst = out_dir / src.name
    if src != dst:
        shutil.copy2(src, dst)


def zip_output(out_dir: Path, timestamp: str) -> Path:
    zip_path = out_dir.parent / f"us_stock_selection_limited_mve2_{timestamp}.zip"
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
        logger.log(f"MeiStock sync skipped; missing path: {target_root}")
        return
    sync_dir = target_root / "checkpoint" / f"limited_mve2_{timestamp}"
    try:
        sync_dir.mkdir(parents=True, exist_ok=True)
        for name in [
            "README_summary.md",
            "eligible_universe_limited_mve2.csv",
            "excluded_tickers_limited_mve2.csv",
            "bucket_summary_limited_mve2.csv",
            "return_max_candidates_limited_mve2.csv",
            "risk_adjusted_candidates_limited_mve2.csv",
            "conservative_candidates_limited_mve2.csv",
        ]:
            src = out_dir / name
            if src.exists():
                shutil.copy2(src, sync_dir / name)
        index = pd.DataFrame(
            [
                {
                    "checkpoint": f"limited_mve2_{timestamp}",
                    "output_dir": str(out_dir.resolve()),
                    "zip_path": str(zip_path.resolve()),
                    "run_scope": RUN_SCOPE,
                    "notes": "limited MVE2 initial strategy screen; formal MVE2 not started",
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
    out_dir = args.out_dir or (DEFAULT_OUTPUT_ROOT / f"limited_mve2_{timestamp}")
    out_dir.mkdir(parents=True, exist_ok=False)
    logger = RunLogger(out_dir / "limited_mve2_run_log.txt")
    logger.log("Starting limited MVE2 strategy search.")
    logger.log(f"Store dir: {args.store_dir}")
    logger.log(f"Readiness dir: {args.readiness_dir}")
    logger.log("Scope guard: limited_mve2 only; no formal MVE2, no model training, no qlib/v8 cache.")

    readiness = load_readiness(args.readiness_dir)
    eligible, excluded, bucket_def = build_universe(readiness)
    logger.log(f"Eligible tickers: {eligible['ticker'].nunique()}; excluded: {excluded['ticker'].nunique()}")

    eligible.to_csv(out_dir / "eligible_universe_limited_mve2.csv", index=False, encoding="utf-8-sig")
    excluded.to_csv(out_dir / "excluded_tickers_limited_mve2.csv", index=False, encoding="utf-8-sig")
    bucket_def.to_csv(out_dir / "bucket_definition_limited_mve2.csv", index=False, encoding="utf-8-sig")

    price_data_raw: Dict[str, pd.DataFrame] = {}
    failed_price_rows = []
    for ticker in eligible["ticker"].tolist():
        try:
            price_data_raw[ticker] = read_price(args.store_dir, ticker)
        except Exception as exc:  # noqa: BLE001
            logger.log(f"WARNING: price load failed for {ticker}: {exc}")
            failed_price_rows.append({"ticker": ticker, "load_error": str(exc), "exclusion_reason": "price_load_failed"})
    if failed_price_rows:
        failed_df = pd.DataFrame(failed_price_rows)
        failed_df.to_csv(out_dir / "price_load_failures_limited_mve2.csv", index=False, encoding="utf-8-sig")
        eligible = eligible[~eligible["ticker"].isin(failed_df["ticker"])].reset_index(drop=True)
    if eligible.empty:
        raise RuntimeError("No eligible ticker with readable unified-store price data.")

    start, end = common_backtest_window(price_data_raw, args.start_date)
    logger.log(f"Common backtest window: {start.date()} to {end.date()}")
    price_data = {ticker: prepare_price_frame(df, start, end) for ticker, df in price_data_raw.items() if ticker in set(eligible["ticker"])}

    benchmark_tickers = [x.strip().upper() for x in args.benchmark_tickers.split(",") if x.strip()]
    missing_bench = [x for x in benchmark_tickers if x not in price_data]
    if missing_bench:
        raise RuntimeError(f"Missing benchmark ticker(s) in eligible price data: {missing_bench}")
    benchmarks = {ticker: price_data[ticker]["return"].reset_index(drop=True) for ticker in benchmark_tickers}
    bench_df = benchmark_results(price_data, benchmark_tickers)
    bench_df.to_csv(out_dir / "benchmark_results_limited_mve2.csv", index=False, encoding="utf-8-sig")

    specs = make_strategy_specs()
    logger.log(f"Strategy specs: {len(specs)} per ticker.")
    results, detail_cache = run_all_strategies(eligible, price_data, benchmarks, specs)
    results.to_csv(out_dir / "all_strategy_results_limited_mve2.csv", index=False, encoding="utf-8-sig")
    logger.log(f"All strategy result rows: {len(results)}")

    return_max = select_candidates(results, "return_max_candidates", 0.50, ["CAGR", "Calmar"], args.top_n)
    risk_adj = select_candidates(results, "risk_adjusted_candidates", 0.40, ["Calmar", "CAGR"], args.top_n)
    conservative = select_candidates(results, "conservative_candidates", 0.30, ["Calmar", "Sharpe"], args.top_n)
    return_max.to_csv(out_dir / "return_max_candidates_limited_mve2.csv", index=False, encoding="utf-8-sig")
    risk_adj.to_csv(out_dir / "risk_adjusted_candidates_limited_mve2.csv", index=False, encoding="utf-8-sig")
    conservative.to_csv(out_dir / "conservative_candidates_limited_mve2.csv", index=False, encoding="utf-8-sig")

    bucket_sum = bucket_summary(results, bucket_def)
    bucket_sum.to_csv(out_dir / "bucket_summary_limited_mve2.csv", index=False, encoding="utf-8-sig")

    period_df = make_period_slice_results(results, detail_cache)
    period_df.to_csv(out_dir / "period_slice_results_limited_mve2.csv", index=False, encoding="utf-8-sig")
    logger.log(f"Period-slice result rows: {len(period_df)}")

    top_union = pd.concat([return_max, risk_adj, conservative], ignore_index=True) if not (return_max.empty and risk_adj.empty and conservative.empty) else pd.DataFrame()
    if not top_union.empty:
        top_union = top_union.drop_duplicates("candidate_id").head(60)
    robust_df = robustness_checks(top_union, detail_cache) if not top_union.empty else pd.DataFrame()
    robust_df.to_csv(out_dir / "top_candidate_robustness_checks_limited_mve2.csv", index=False, encoding="utf-8-sig")

    neighborhood_df = parameter_neighborhood_checks(top_union, detail_cache) if not top_union.empty else pd.DataFrame()
    neighborhood_df.to_csv(out_dir / "parameter_neighborhood_checks_limited_mve2.csv", index=False, encoding="utf-8-sig")

    nr = not_recommended(results)
    nr.to_csv(out_dir / "not_recommended_candidates_limited_mve2.csv", index=False, encoding="utf-8-sig")

    run_config = {
        "run_scope": RUN_SCOPE,
        "timestamp": timestamp,
        "store_dir": str(args.store_dir),
        "readiness_dir": str(args.readiness_dir),
        "out_dir": str(out_dir),
        "common_start": start.date().isoformat(),
        "common_end": end.date().isoformat(),
        "eligible_ticker_count": int(eligible["ticker"].nunique()),
        "excluded_ticker_count": int(excluded["ticker"].nunique()),
        "strategy_specs_per_ticker": len(specs),
        "formal_mve2_started": False,
        "model_training_started": False,
        "uses_qlib_or_v8_cache": False,
    }
    (out_dir / "limited_mve2_run_config.json").write_text(json.dumps(run_config, indent=2), encoding="utf-8")

    write_readme(out_dir, eligible, excluded, bucket_def, bucket_sum, return_max, risk_adj, conservative, robust_df, neighborhood_df)
    copy_script(out_dir)

    zip_path = Path("")
    if not args.no_zip:
        zip_path = zip_output(out_dir, timestamp)
        logger.log(f"Zip written: {zip_path}")
    sync_meistock(out_dir, zip_path, timestamp, logger)
    logger.log("limited MVE2 strategy search completed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
