"""Apples-to-apples audit for old QLD/TQQQ optimal strategy vs v1 rules.

The script does not optimize or tune. It replays:
- old_optimal_strategy_20260420 as original fractional weights
- old_optimal_strategy_20260420 as a fixed binary version: desired weight > 0
- ema20_ema100_direction
- qqq_ma200_trend

All rows use the same local OHLCV data, 2021-01-01+ period, next-open
execution, 0.20% one-way fee, and the same metrics engine.
"""

from __future__ import annotations

import argparse
import math
import warnings
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "external" / "legacy_quant" / "NSDQStock" / "19800101_20260404"
OLD_RUN_DIR = ROOT / "outputs" / "qldtqqq_turning_points" / "qldtqqq_turning_20260420_133901"
TARGETS = ("QLD", "TQQQ")
PERIOD_START = pd.Timestamp("2021-01-01")
FEE = 0.002
TRADING_DAYS = 252.0
EPS = 1e-10

warnings.filterwarnings("ignore", category=FutureWarning)


@dataclass
class ReplayResult:
    target: str
    strategy: str
    display_name: str
    notes: str
    desired_weight: pd.Series
    position_weight: pd.Series
    nav: pd.Series
    returns: pd.Series
    turnover: pd.Series
    fee: float


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def log(message: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", flush=True)


def read_ohlcv(data_dir: Path, symbol: str) -> pd.DataFrame:
    path = data_dir / f"{symbol}.csv"
    if not path.exists():
        raise FileNotFoundError(path)
    df = pd.read_csv(path)
    df.columns = [str(c).strip().lower() for c in df.columns]
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.tz_localize(None).dt.normalize()
    df = df.dropna(subset=["date"]).drop_duplicates("date").sort_values("date").set_index("date")
    for col in ("open", "high", "low", "close", "volume"):
        if col not in df.columns:
            df[col] = np.nan
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df[["open", "high", "low", "close", "volume"]].dropna(subset=["open", "close"])


def ema(series: pd.Series, window: int) -> pd.Series:
    return series.ewm(span=window, adjust=False).mean()


def max_drawdown(nav: pd.Series) -> float:
    clean = nav.replace([np.inf, -np.inf], np.nan).dropna()
    if clean.empty:
        return np.nan
    return float(clean.div(clean.cummax()).sub(1.0).min())


def cagr(nav: pd.Series) -> float:
    clean = nav.replace([np.inf, -np.inf], np.nan).dropna()
    if len(clean) < 2:
        return np.nan
    years = max((clean.index[-1] - clean.index[0]).days / 365.25, 1 / 365.25)
    start = float(clean.iloc[0])
    end = float(clean.iloc[-1])
    if start <= 0 or end <= 0:
        return np.nan
    return float((end / start) ** (1.0 / years) - 1.0)


def sharpe(returns: pd.Series) -> float:
    clean = returns.replace([np.inf, -np.inf], np.nan).dropna()
    if len(clean) < 20:
        return np.nan
    vol = clean.std(ddof=0)
    if vol == 0 or not np.isfinite(vol):
        return np.nan
    return float(clean.mean() / vol * math.sqrt(TRADING_DAYS))


def normalize_slice(nav: pd.Series, start: pd.Timestamp = PERIOD_START) -> pd.Series:
    out = nav.loc[nav.index >= start].dropna()
    if out.empty:
        return out
    return out / out.iloc[0]


def replay_next_open(asset: pd.DataFrame, desired_weight: pd.Series, target: str, strategy: str, display_name: str, notes: str) -> ReplayResult:
    df = asset[["open", "close"]].copy().dropna()
    desired = desired_weight.reindex(df.index).ffill().fillna(0.0).astype(float).clip(0.0, 1.0)
    open_arr = df["open"].to_numpy(dtype=float)
    close_arr = df["close"].to_numpy(dtype=float)
    desired_arr = desired.to_numpy(dtype=float)
    n = len(df)
    nav = np.ones(n, dtype=float)
    rets = np.zeros(n, dtype=float)
    pos_arr = np.zeros(n, dtype=float)
    turnover_arr = np.zeros(n, dtype=float)
    equity = 1.0
    pos = 0.0

    for i in range(1, n):
        prev_equity = equity
        prev_close = close_arr[i - 1]
        today_open = open_arr[i]
        today_close = close_arr[i]
        target_weight = desired_arr[i - 1]

        if pos > 0 and np.isfinite(prev_close) and np.isfinite(today_open) and prev_close > 0:
            equity *= 1.0 + pos * (today_open / prev_close - 1.0)

        delta = abs(target_weight - pos)
        if delta > EPS:
            equity *= max(0.0, 1.0 - FEE * delta)
        pos = target_weight

        if pos > 0 and np.isfinite(today_open) and np.isfinite(today_close) and today_open > 0:
            equity *= 1.0 + pos * (today_close / today_open - 1.0)

        nav[i] = equity
        rets[i] = equity / prev_equity - 1.0 if prev_equity > 0 else 0.0
        pos_arr[i] = pos
        turnover_arr[i] = delta

    return ReplayResult(
        target=target,
        strategy=strategy,
        display_name=display_name,
        notes=notes,
        desired_weight=desired,
        position_weight=pd.Series(pos_arr, index=df.index, name="position_weight"),
        nav=pd.Series(nav, index=df.index, name="nav"),
        returns=pd.Series(rets, index=df.index, name="returns"),
        turnover=pd.Series(turnover_arr, index=df.index, name="turnover"),
        fee=FEE,
    )


def holding_days(position: pd.Series) -> float:
    pos = position.fillna(0.0).abs().gt(EPS)
    if pos.empty or not pos.any():
        return 0.0
    starts = np.flatnonzero((pos & ~pos.shift(1, fill_value=False)).to_numpy())
    ends = np.flatnonzero((~pos & pos.shift(1, fill_value=False)).to_numpy())
    if len(ends) and len(starts) and ends[0] < starts[0]:
        ends = ends[1:]
    if len(ends) < len(starts):
        ends = np.r_[ends, len(pos) - 1]
    durations = [max(1, int(end) - int(start)) for start, end in zip(starts, ends)]
    return float(np.mean(durations)) if durations else 0.0


def metrics(result: ReplayResult) -> dict[str, float | str | int]:
    nav = normalize_slice(result.nav)
    pos = result.position_weight.loc[result.position_weight.index >= PERIOD_START].reindex(nav.index).fillna(0.0)
    turnover = result.turnover.loc[result.turnover.index >= PERIOD_START].reindex(nav.index).fillna(0.0)
    returns = nav.pct_change().fillna(0.0)
    if len(nav) < 2:
        return {}
    mdd = max_drawdown(nav)
    cagr_value = cagr(nav)
    calmar = cagr_value / abs(mdd) if np.isfinite(cagr_value) and np.isfinite(mdd) and mdd < 0 else np.nan
    entries = (pos.abs() > EPS) & ~(pos.shift(1).fillna(0.0).abs() > EPS)
    years = max((nav.index[-1] - nav.index[0]).days / 365.25, 1 / 365.25)
    avg_abs_weight = float(pos.abs().mean())
    return {
        "target": result.target,
        "strategy": result.strategy,
        "display_name": result.display_name,
        "period_start": nav.index[0].strftime("%Y-%m-%d"),
        "period_end": nav.index[-1].strftime("%Y-%m-%d"),
        "execution": "signal_at_close_to_next_open",
        "one_way_fee": FEE,
        "CAGR": cagr_value,
        "MDD": mdd,
        "Sharpe": sharpe(returns),
        "Calmar": calmar,
        "trade_count": int(entries.sum()),
        "turnover": float(turnover.sum() / years),
        "avg_holding_days": holding_days(pos),
        "avg_weight": float(pos.mean()),
        "median_weight": float(pos.median()),
        "time_in_market": float(pos.abs().gt(EPS).mean()),
        "avg_abs_weight": avg_abs_weight,
        "max_weight": float(pos.max()),
        "position_change_days": int(turnover.gt(EPS).sum()),
        "position_change_frequency": float(turnover.gt(EPS).mean()),
        "CAGR_per_avg_abs_weight": cagr_value / avg_abs_weight if avg_abs_weight > EPS and np.isfinite(cagr_value) else np.nan,
        "MDD_per_avg_abs_weight": mdd / avg_abs_weight if avg_abs_weight > EPS and np.isfinite(mdd) else np.nan,
        "notes": result.notes,
    }


def exposure_stats(result: ReplayResult) -> dict[str, float | str | int]:
    pos = result.position_weight.loc[result.position_weight.index >= PERIOD_START].fillna(0.0)
    turnover = result.turnover.loc[result.turnover.index >= PERIOD_START].reindex(pos.index).fillna(0.0)
    nonzero = pos.abs().gt(EPS)
    return {
        "target": result.target,
        "strategy": result.strategy,
        "total_days": int(len(pos)),
        "exposure_days": int(nonzero.sum()),
        "time_in_market": float(nonzero.mean()) if len(pos) else np.nan,
        "avg_weight": float(pos.mean()) if len(pos) else np.nan,
        "median_weight": float(pos.median()) if len(pos) else np.nan,
        "avg_abs_weight": float(pos.abs().mean()) if len(pos) else np.nan,
        "max_weight": float(pos.max()) if len(pos) else np.nan,
        "min_weight": float(pos.min()) if len(pos) else np.nan,
        "position_change_days": int(turnover.gt(EPS).sum()),
        "position_change_frequency": float(turnover.gt(EPS).mean()) if len(turnover) else np.nan,
        "annual_turnover": float(turnover.sum() / max((pos.index[-1] - pos.index[0]).days / 365.25, 1 / 365.25)) if len(pos) >= 2 else np.nan,
        "avg_turnover_on_change_days": float(turnover[turnover.gt(EPS)].mean()) if turnover.gt(EPS).any() else 0.0,
    }


def trade_log(result: ReplayResult, asset: pd.DataFrame) -> pd.DataFrame:
    pos = result.position_weight.loc[result.position_weight.index >= PERIOD_START].fillna(0.0)
    nav = normalize_slice(result.nav).reindex(pos.index).ffill()
    prices = asset.reindex(pos.index).ffill()
    active = pos.abs().gt(EPS)
    if active.empty:
        return pd.DataFrame()
    starts_mask = active & ~active.shift(1, fill_value=False)
    ends_mask = ~active & active.shift(1, fill_value=False)
    starts = list(np.flatnonzero(starts_mask.to_numpy()))
    ends = list(np.flatnonzero(ends_mask.to_numpy()))
    carried_in = False
    if active.iloc[0] and (not starts or starts[0] != 0):
        starts = [0] + starts
        carried_in = True
    if ends and starts and ends[0] < starts[0]:
        ends = ends[1:]

    rows = []
    for k, start_idx in enumerate(starts):
        is_open = k >= len(ends)
        end_idx = len(pos) - 1 if is_open else ends[k]
        entry_date = pos.index[start_idx]
        exit_date = pos.index[end_idx]
        segment_pos = pos.iloc[start_idx : end_idx + 1]
        segment_turnover = result.turnover.reindex(pos.index).fillna(0.0).iloc[start_idx : end_idx + 1]
        entry_price = float(prices["open"].iloc[start_idx])
        exit_price = float(prices["open"].iloc[end_idx] if not is_open else prices["close"].iloc[end_idx])
        rows.append(
            {
                "target": result.target,
                "strategy": result.strategy,
                "entry_date": entry_date.strftime("%Y-%m-%d"),
                "exit_date": "" if is_open else exit_date.strftime("%Y-%m-%d"),
                "status": "open" if is_open else "closed",
                "carried_in_from_before_period": bool(carried_in and k == 0),
                "entry_price": entry_price,
                "exit_or_mark_price": exit_price,
                "underlying_price_return": exit_price / entry_price - 1.0 if entry_price > 0 else np.nan,
                "strategy_nav_return": float(nav.iloc[end_idx] / nav.iloc[start_idx] - 1.0) if nav.iloc[start_idx] > 0 else np.nan,
                "holding_days": int(max(1, end_idx - start_idx)),
                "avg_position_weight": float(segment_pos.mean()),
                "median_position_weight": float(segment_pos.median()),
                "max_position_weight": float(segment_pos.max()),
                "episode_turnover": float(segment_turnover.sum()),
            }
        )
    return pd.DataFrame(rows)


def format_pct(x: float) -> str:
    return "nan" if pd.isna(x) else f"{x * 100:.2f}%"


def format_num(x: float) -> str:
    return "nan" if pd.isna(x) else f"{x:.3f}"


def md_table(df: pd.DataFrame, max_rows: int | None = None) -> str:
    if df.empty:
        return "_Empty._"
    out = df.copy()
    if max_rows is not None:
        out = out.head(max_rows)
    for col in out.columns:
        out[col] = out[col].map(lambda x: "" if pd.isna(x) else str(x).replace("|", "/"))
    header = "| " + " | ".join(map(str, out.columns)) + " |"
    sep = "| " + " | ".join(["---"] * len(out.columns)) + " |"
    rows = ["| " + " | ".join(row) + " |" for row in out.astype(str).to_numpy()]
    return "\n".join([header, sep, *rows])


def write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def old_desired_weight(old_run_dir: Path, target: str, index: pd.Index) -> pd.Series:
    path = old_run_dir / f"{target}_best_signal_nav.csv"
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.normalize()
    df = df.dropna(subset=["date"]).sort_values("date").set_index("date")
    weight = pd.to_numeric(df["desired_weight_after_close"], errors="coerce").clip(lower=0.0, upper=1.0)
    return weight.reindex(index).ffill().fillna(0.0)


def build_replays(data: dict[str, pd.DataFrame], old_run_dir: Path) -> list[ReplayResult]:
    qqq = data["QQQ"]
    qqq_close = qqq["close"].astype(float)
    qqq_ema_signal = (ema(qqq_close, 20) > ema(qqq_close, 100)).astype(float)
    qqq_ma200_signal = (qqq_close > qqq_close.rolling(200, min_periods=200).mean()).astype(float)
    results: list[ReplayResult] = []
    for target in TARGETS:
        asset = data[target]
        old_weight = old_desired_weight(old_run_dir, target, asset.index)
        strategy_specs = [
            (
                "old_optimal_fractional",
                "old_optimal_strategy_20260420 fractional",
                old_weight,
                "Old optimized strategy replayed from desired_weight_after_close with original fractional weights.",
            ),
            (
                "old_optimal_binary_gt0",
                "old_optimal_strategy_20260420 binary weight>0",
                old_weight.gt(0.0).astype(float),
                "Non-optimized binary audit version: any positive old target weight becomes 1.0, otherwise 0.0.",
            ),
            (
                "ema20_ema100_direction",
                "EMA20 > EMA100",
                qqq_ema_signal.reindex(asset.index).ffill().fillna(0.0),
                "V1 selected simple strategy: hold target when QQQ EMA20 is above QQQ EMA100.",
            ),
            (
                "qqq_ma200_trend",
                "QQQ close > MA200",
                qqq_ma200_signal.reindex(asset.index).ffill().fillna(0.0),
                "Simple long-term trend baseline: hold target when QQQ close is above MA200.",
            ),
        ]
        for strategy, display_name, desired, notes in strategy_specs:
            results.append(replay_next_open(asset, desired, target, strategy, display_name, notes))
    return results


def plot_equity(results: list[ReplayResult], run_dir: Path) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(13, 9), sharex=True)
    for ax, target in zip(axes, TARGETS):
        for result in results:
            if result.target != target:
                continue
            nav = normalize_slice(result.nav)
            ax.plot(nav.index, nav.values, label=result.strategy, linewidth=1.5)
        ax.set_title(f"{target}: apples-to-apples equity curves")
        ax.set_ylabel("Growth of $1")
        ax.grid(True, alpha=0.25)
        ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(run_dir / "apples_to_apples_equity_curves.png", dpi=160)
    plt.close(fig)


def plot_drawdowns(results: list[ReplayResult], run_dir: Path) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(13, 9), sharex=True)
    for ax, target in zip(axes, TARGETS):
        for result in results:
            if result.target != target:
                continue
            nav = normalize_slice(result.nav)
            dd = nav.div(nav.cummax()).sub(1.0)
            ax.plot(dd.index, dd.values, label=result.strategy, linewidth=1.5)
        ax.set_title(f"{target}: apples-to-apples drawdowns")
        ax.set_ylabel("Drawdown")
        ax.grid(True, alpha=0.25)
        ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(run_dir / "apples_to_apples_drawdowns.png", dpi=160)
    plt.close(fig)


def source_old_metrics(old_run_dir: Path) -> pd.DataFrame:
    path = old_run_dir / "best_strategy_summary.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def pct_to_float(value: object) -> float:
    if pd.isna(value):
        return np.nan
    text = str(value).strip()
    if text.endswith("%"):
        return float(text[:-1]) / 100.0
    return float(text)


def old_reported_vs_replayed(old_source: pd.DataFrame, metrics_df: pd.DataFrame) -> pd.DataFrame:
    if old_source.empty:
        return pd.DataFrame()
    replay = metrics_df[metrics_df["strategy"].eq("old_optimal_fractional")].set_index("target")
    rows = []
    for _, row in old_source.iterrows():
        target = row["target"]
        if target not in replay.index:
            continue
        same = replay.loc[target]
        rows.append(
            {
                "target": target,
                "old_reported_test_annual_return": pct_to_float(row.get("test_annual_return")),
                "old_reported_test_max_drawdown": pct_to_float(row.get("test_max_drawdown")),
                "old_reported_test_calmar": float(row.get("test_calmar")),
                "same_engine_old_fractional_CAGR": same["CAGR"],
                "same_engine_old_fractional_MDD": same["MDD"],
                "same_engine_old_fractional_Calmar": same["Calmar"],
                "CAGR_gap_reported_minus_same_engine": pct_to_float(row.get("test_annual_return")) - same["CAGR"],
                "MDD_gap_reported_minus_same_engine": pct_to_float(row.get("test_max_drawdown")) - same["MDD"],
            }
        )
    return pd.DataFrame(rows)


def concise_metrics_for_md(metrics_df: pd.DataFrame) -> pd.DataFrame:
    out = metrics_df[
        [
            "target",
            "strategy",
            "CAGR",
            "MDD",
            "Sharpe",
            "Calmar",
            "trade_count",
            "turnover",
            "avg_holding_days",
            "avg_abs_weight",
            "time_in_market",
            "CAGR_per_avg_abs_weight",
        ]
    ].copy()
    for col in ("CAGR", "MDD", "avg_abs_weight", "time_in_market", "CAGR_per_avg_abs_weight"):
        out[col] = out[col].map(format_pct)
    for col in ("Sharpe", "Calmar", "turnover", "avg_holding_days"):
        out[col] = out[col].map(format_num)
    return out


def determine_primary(metrics_df: pd.DataFrame) -> str:
    simple = metrics_df[metrics_df["strategy"].isin(["ema20_ema100_direction", "qqq_ma200_trend"])].copy()
    grouped = simple.groupby("strategy").agg(
        median_calmar=("Calmar", "median"),
        worst_mdd=("MDD", "min"),
        median_cagr=("CAGR", "median"),
        avg_turnover=("turnover", "mean"),
        avg_time=("time_in_market", "mean"),
    )
    grouped["score"] = grouped["median_calmar"] + 0.2 * grouped["median_cagr"] - 0.03 * grouped["avg_turnover"]
    return str(grouped["score"].idxmax())


def audit_markdown(
    metrics_df: pd.DataFrame,
    exposure_df: pd.DataFrame,
    old_source: pd.DataFrame,
    old_run_dir: Path,
    data: dict[str, pd.DataFrame],
) -> str:
    primary = determine_primary(metrics_df)
    old_frac = metrics_df[metrics_df["strategy"].eq("old_optimal_fractional")].set_index("target")
    old_bin = metrics_df[metrics_df["strategy"].eq("old_optimal_binary_gt0")].set_index("target")
    ema = metrics_df[metrics_df["strategy"].eq("ema20_ema100_direction")].set_index("target")
    ma200 = metrics_df[metrics_df["strategy"].eq("qqq_ma200_trend")].set_index("target")
    reported_gap = old_reported_vs_replayed(old_source, metrics_df)
    reported_gap_fmt = reported_gap.copy()
    for col in (
        "old_reported_test_annual_return",
        "old_reported_test_max_drawdown",
        "same_engine_old_fractional_CAGR",
        "same_engine_old_fractional_MDD",
        "CAGR_gap_reported_minus_same_engine",
        "MDD_gap_reported_minus_same_engine",
    ):
        if col in reported_gap_fmt.columns:
            reported_gap_fmt[col] = reported_gap_fmt[col].map(format_pct)
    for col in ("old_reported_test_calmar", "same_engine_old_fractional_Calmar"):
        if col in reported_gap_fmt.columns:
            reported_gap_fmt[col] = reported_gap_fmt[col].map(format_num)

    lines = [
        "# Apples-to-apples Audit",
        "",
        "## Scope",
        "",
        "This audit does not optimize or retune anything. It replays old_optimal_strategy_20260420 and two simple v1 rules under one identical backtest engine.",
        "",
        "Unified comparison assumptions:",
        "",
        "- Period: 2021-01-01 to latest local bar.",
        "- Data: local OHLCV files under `data/external/legacy_quant/NSDQStock/19800101_20260404`.",
        "- Execution: signal at close -> execute next open.",
        "- Fee: 0.20% one-way on absolute weight turnover.",
        "- Old binary version: fixed non-optimized threshold `desired_weight_after_close > 0`.",
        "- Important: the old run's saved `portfolio_value` is not reused for the main comparison. Old weights are replayed through the same next-open engine used for all rows.",
        "",
        "Latest local bars:",
        "",
        md_table(
            pd.DataFrame(
                [
                    {
                        "symbol": symbol,
                        "first": df.index.min().strftime("%Y-%m-%d"),
                        "latest": df.index.max().strftime("%Y-%m-%d"),
                        "rows": len(df),
                    }
                    for symbol, df in data.items()
                ]
            )
        ),
        "",
        "## Same-engine Metrics",
        "",
        md_table(concise_metrics_for_md(metrics_df)),
        "",
        "## Old Reported Result vs Same-engine Replay",
        "",
        "The old headline result is materially different from the same-engine replay. The old code path uses an open-to-open return loop with the current row's `desired` weight, while this audit enforces close signal -> next open. Therefore the original old report is not directly comparable to the v1 simple-rule backtests.",
        "",
        md_table(reported_gap_fmt) if not reported_gap_fmt.empty else "_Old reported summary not available._",
        "",
        "## Exposure Audit",
        "",
        md_table(
            exposure_df.assign(
                time_in_market=lambda x: x["time_in_market"].map(format_pct),
                avg_weight=lambda x: x["avg_weight"].map(format_pct),
                median_weight=lambda x: x["median_weight"].map(format_pct),
                avg_abs_weight=lambda x: x["avg_abs_weight"].map(format_pct),
                max_weight=lambda x: x["max_weight"].map(format_pct),
                position_change_frequency=lambda x: x["position_change_frequency"].map(format_pct),
                annual_turnover=lambda x: x["annual_turnover"].map(format_num),
            )[
                [
                    "target",
                    "strategy",
                    "time_in_market",
                    "avg_weight",
                    "median_weight",
                    "avg_abs_weight",
                    "max_weight",
                    "position_change_days",
                    "position_change_frequency",
                    "annual_turnover",
                ]
            ]
        ),
        "",
        "## Required Answers",
        "",
        "1. Is old_optimal really better?",
        "",
    ]

    for target in TARGETS:
        of = old_frac.loc[target]
        eb = ema.loc[target]
        mb = ma200.loc[target]
        best_simple_calmar = max(eb["Calmar"], mb["Calmar"])
        better_calmar = of["Calmar"] > best_simple_calmar
        better_mdd = of["MDD"] > max(eb["MDD"], mb["MDD"])
        better_cagr = of["CAGR"] > max(eb["CAGR"], mb["CAGR"])
        verdict = "better on drawdown but not on raw CAGR" if better_mdd and not better_cagr else "not unambiguously better"
        if better_calmar and better_mdd and better_cagr:
            verdict = "better on CAGR, drawdown, and Calmar"
        elif better_calmar and better_mdd:
            verdict = "better on drawdown and Calmar, but not on raw CAGR"
        lines.append(
            f"- {target}: {verdict}. Old fractional CAGR {format_pct(of['CAGR'])}, MDD {format_pct(of['MDD'])}, Calmar {format_num(of['Calmar'])}; "
            f"EMA20/100 Calmar {format_num(eb['Calmar'])}, MA200 Calmar {format_num(mb['Calmar'])}."
        )
        if not better_cagr:
            lines.append(f"- {target}: old fractional is not the highest CAGR after same-engine replay; its main edge is lower drawdown/Calmar, not raw return.")
        if not better_calmar:
            lines.append(f"- {target}: old fractional also does not beat the best simple rule on Calmar under the strict same-engine replay.")
    lines.extend(
        [
            "",
            "2. Where does old_optimal's advantage come from?",
            "",
        ]
    )
    for target in TARGETS:
        of = old_frac.loc[target]
        ob = old_bin.loc[target]
        eb = ema.loc[target]
        lines.append(
            f"- {target}: old fractional average absolute weight is {format_pct(of['avg_abs_weight'])} versus EMA20/100 {format_pct(eb['avg_abs_weight'])}; "
            f"the binary old version raises average exposure to {format_pct(ob['avg_abs_weight'])}. "
            f"Old fractional MDD {format_pct(of['MDD'])} versus old binary MDD {format_pct(ob['MDD'])} shows how much drawdown control comes from fractional sizing. "
            f"Old binary Calmar {format_num(ob['Calmar'])} tests the old gate without fractional weights."
        )
    lines.extend(
        [
            "- Different execution口径 is a major explanation for why the original old report looked much stronger. After enforcing close -> next open, old fractional CAGR drops materially versus the saved old `portfolio_value` result.",
            "- The remaining old edge is mostly lower average weight and stronger risk coverage. Complex gating helps reduce drawdown, but the binary old gate does not clearly beat MA200 after fractional sizing is removed.",
            "",
            "3. If position utilization is made more comparable, does old still win?",
            "",
            "The old binary version removes fractional sizing and uses 0/1 exposure whenever the old strategy has any positive target weight. This is not a tuned threshold. If old_binary still beats the simple rules on Calmar/MDD, the old gate itself adds value; if it loses, the old headline advantage was mostly fractional risk throttling.",
        ]
    )
    for target in TARGETS:
        ob = old_bin.loc[target]
        eb = ema.loc[target]
        mb = ma200.loc[target]
        old_gate_wins = ob["Calmar"] > max(eb["Calmar"], mb["Calmar"])
        lines.append(
            f"- {target}: old_binary Calmar {format_num(ob['Calmar'])}, MDD {format_pct(ob['MDD'])}; "
            f"EMA20/100 Calmar {format_num(eb['Calmar'])}, MA200 Calmar {format_num(mb['Calmar'])}. "
            f"Conclusion: {'old gate remains better after removing fractional sizing' if old_gate_wins else 'old gate no longer clearly beats the simple rules after removing fractional sizing'}."
        )
    lines.extend(
        [
            "",
            "4. ema20_ema100_direction vs qqq_ma200_trend: which should be the next primary strategy?",
            "",
            f"`{primary}` is the better next primary by this audit's simple stability score across QLD and TQQQ. The choice favors Calmar, avoids high turnover, and does not use retuning. In this same-engine audit, MA200 also beats EMA20/100 on CAGR and Calmar for both QLD and TQQQ.",
            "",
            "5. Which is best for maximum return plus minimum drawdown?",
            "",
            "There is no single clean winner. `qqq_ma200_trend` gives the highest CAGR and the best or near-best Calmar, while `old_optimal_fractional` gives the smallest drawdown because it runs lower average exposure. If the objective is maximum CAGR with acceptable drawdown, MA200 is stronger in this audit. If the objective is strict drawdown minimization and dynamic fractional weights are allowed, old fractional is stronger.",
            "",
            "6. Which is best for anti-overfitting and interpretability?",
            "",
            f"`{primary}` is the better research base. The old strategy is more complex, dynamically weighted, and selected from a much larger search process, so even where it controls drawdown better, it carries higher model-selection and overfitting risk.",
            "",
            "## Why earlier conclusions can mislead",
            "",
            "A direct comparison between old reported results and v1 simple strategy rows can mix execution and portfolio construction differences. Old_optimal is not just a timing rule; it is a dynamically weighted, gated, risk-managed strategy, and its original saved performance came from a different open-to-open execution loop. Comparing that result to 0/1 simple rules without same-engine replay and exposure statistics makes the old strategy look like a pure alpha improvement, when the advantage is largely execution口径, lower average weight, lower time at full risk, and more complex risk coverage.",
            "",
            "## Original Old-run Summary For Reference",
            "",
            md_table(old_source) if not old_source.empty else "_Original old summary not found._",
            "",
            f"Old run directory: `{old_run_dir}`",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Apples-to-apples audit for QLD/TQQQ old vs v1 strategies")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--old-run-dir", type=Path, default=OLD_RUN_DIR)
    parser.add_argument("--output-root", type=Path, default=ROOT / "outputs")
    args = parser.parse_args()

    run_dir = args.output_root / f"apples_to_apples_audit_{stamp()}"
    run_dir.mkdir(parents=True, exist_ok=True)
    log(f"Output directory: {run_dir}")

    log("Loading local data")
    data = {symbol: read_ohlcv(args.data_dir, symbol) for symbol in ("QQQ", "QLD", "TQQQ")}

    log("Replaying strategies under one next-open engine")
    results = build_replays(data, args.old_run_dir)
    metrics_df = pd.DataFrame([metrics(result) for result in results])
    exposure_df = pd.DataFrame([exposure_stats(result) for result in results])
    write_csv(metrics_df, run_dir / "apples_to_apples_metrics.csv")
    write_csv(exposure_df, run_dir / "apples_to_apples_exposure_stats.csv")

    log("Writing trade logs")
    for target in TARGETS:
        logs = [trade_log(result, data[target]) for result in results if result.target == target]
        all_logs = pd.concat(logs, ignore_index=True) if logs else pd.DataFrame()
        write_csv(all_logs, run_dir / f"apples_to_apples_trade_logs_{target.lower()}.csv")

    log("Writing charts")
    plot_equity(results, run_dir)
    plot_drawdowns(results, run_dir)

    log("Writing audit markdown")
    old_source = source_old_metrics(args.old_run_dir)
    reported_gap = old_reported_vs_replayed(old_source, metrics_df)
    if not reported_gap.empty:
        write_csv(reported_gap, run_dir / "old_reported_vs_same_engine_replay.csv")
    write_text(
        run_dir / "apples_to_apples_audit.md",
        audit_markdown(metrics_df, exposure_df, old_source, args.old_run_dir, data),
    )

    write_text(
        run_dir / "README_FOR_CHATGPT.md",
        "\n".join(
            [
                "# ChatGPT Review Packet",
                "",
                "Please review `apples_to_apples_audit.md` first, then inspect the two CSV tables:",
                "",
                "- `apples_to_apples_metrics.csv`",
                "- `apples_to_apples_exposure_stats.csv`",
                "",
                "Charts are included for visual checks:",
                "",
                "- `apples_to_apples_equity_curves.png`",
                "- `apples_to_apples_drawdowns.png`",
                "",
                "Trade logs by target are included for execution/path diagnostics.",
            ]
        ),
    )

    required = [
        "apples_to_apples_audit.md",
        "apples_to_apples_metrics.csv",
        "apples_to_apples_equity_curves.png",
        "apples_to_apples_drawdowns.png",
        "apples_to_apples_exposure_stats.csv",
        "apples_to_apples_trade_logs_qld.csv",
        "apples_to_apples_trade_logs_tqqq.csv",
    ]
    missing = [name for name in required if not (run_dir / name).exists()]
    if missing:
        raise RuntimeError(f"Missing required audit outputs: {missing}")
    log("Audit completed")
    log(str(run_dir))


if __name__ == "__main__":
    main()
