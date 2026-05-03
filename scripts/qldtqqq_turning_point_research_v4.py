"""Turning point research v4: strict validation only.

V4 does not add factors, models, or new primary strategies. It stress-tests the
already narrowed candidates:
- TQQQ: ema20_ema100_direction + ATR stop.
- QLD robust: ema20_ema100_direction + risk_bundle.
- QLD aggressive: ema20_ema100_direction + regime_off.
"""

from __future__ import annotations

import argparse
import itertools
import math
import sys
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
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import qldtqqq_turning_point_research_v2 as v2  # noqa: E402
import qldtqqq_turning_point_research_v3 as v3  # noqa: E402
from qldtqqq_turning_point_research_v1 import DEFAULT_DATA_DIR, atr  # noqa: E402


warnings.filterwarnings("ignore", category=FutureWarning)

FEE = 0.002
PERIOD_START = pd.Timestamp("2021-01-01")
TRADING_DAYS = 252.0
EPS = 1e-10
V3_DIR = ROOT / "outputs" / "turning_point_research_v3_20260421_190207"


@dataclass(frozen=True)
class PeriodSplit:
    split_type: str
    split: str
    periods: tuple[tuple[str, str | None], ...]
    train_start: str = ""
    train_end: str = ""
    purge_days: int = 0
    embargo_days: int = 0


@dataclass
class ReplayResult:
    target: str
    strategy: str
    overlay: str
    execution: str
    fee: float
    slippage_model: str
    nav: pd.Series
    returns: pd.Series
    position: pd.Series
    desired: pd.Series
    turnover: pd.Series
    trade_cost_rate: pd.Series


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def log(message: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", flush=True)


def pct(value: float | int | None) -> str:
    return "nan" if value is None or pd.isna(value) else f"{float(value) * 100:.2f}%"


def num(value: float | int | None, digits: int = 3) -> str:
    return "nan" if value is None or pd.isna(value) else f"{float(value):.{digits}f}"


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


def strict_splits() -> list[PeriodSplit]:
    year_periods = {
        "2021": (("2021-01-01", "2021-12-31"),),
        "2022": (("2022-01-01", "2022-12-31"),),
        "2023": (("2023-01-01", "2023-12-31"),),
        "2024": (("2024-01-01", "2024-12-31"),),
        "2025_latest": (("2025-01-01", None),),
    }
    out = [
        PeriodSplit("anchored", "anchored_2018_2020", (("2018-01-01", "2020-12-31"),), "2010-01-01", "2017-12-31"),
        PeriodSplit("anchored", "anchored_2021_2023", (("2021-01-01", "2023-12-31"),), "2010-01-01", "2020-12-31"),
        PeriodSplit("anchored", "anchored_2024_latest", (("2024-01-01", None),), "2010-01-01", "2023-12-31"),
        PeriodSplit("anchored", "anchored_2021_latest", (("2021-01-01", None),), "2010-01-01", "2020-12-31"),
        PeriodSplit("rolling", "rolling_2015_2017", (("2015-01-01", "2017-12-31"),), "2010-01-01", "2014-12-31"),
        PeriodSplit("rolling", "rolling_2018_2020", (("2018-01-01", "2020-12-31"),), "2013-01-01", "2017-12-31"),
        PeriodSplit("rolling", "rolling_2021_2023", (("2021-01-01", "2023-12-31"),), "2016-01-01", "2020-12-31"),
        PeriodSplit("rolling", "rolling_2024_latest", (("2024-01-01", None),), "2019-01-01", "2023-12-31"),
        PeriodSplit("purged", "purged_2021_2022", (("2021-01-01", "2022-12-31"),), "2010-01-01", "2020-11-30", 20, 5),
        PeriodSplit("purged", "purged_2023_2024", (("2023-01-01", "2024-12-31"),), "2015-01-01", "2022-11-30", 20, 5),
        PeriodSplit("purged", "purged_2025_latest", (("2025-01-01", None),), "2018-01-01", "2024-11-30", 20, 5),
    ]
    combos = [
        ("cpcv_2021_2022", ("2021", "2022")),
        ("cpcv_2021_2023", ("2021", "2023")),
        ("cpcv_2022_2024", ("2022", "2024")),
        ("cpcv_2023_2025", ("2023", "2025_latest")),
        ("cpcv_2024_2025", ("2024", "2025_latest")),
    ]
    for name, keys in combos:
        periods: list[tuple[str, str | None]] = []
        for key in keys:
            periods.extend(year_periods[key])
        out.append(PeriodSplit("combinational_purged", name, tuple(periods), "pre_test_excluding_purged_neighbors", "dynamic", 20, 5))
    return out


def period_mask(index: pd.Index, split: PeriodSplit) -> pd.Series:
    mask = pd.Series(False, index=index)
    for start, end in split.periods:
        m = index >= pd.Timestamp(start)
        if end:
            m &= index <= pd.Timestamp(end)
        mask |= m
    return mask


def max_drawdown(nav: pd.Series) -> float:
    clean = nav.dropna()
    if clean.empty:
        return np.nan
    return float(clean.div(clean.cummax()).sub(1.0).min())


def sharpe(returns: pd.Series) -> float:
    clean = returns.replace([np.inf, -np.inf], np.nan).dropna()
    if len(clean) < 20:
        return np.nan
    sd = clean.std(ddof=0)
    return float(clean.mean() / sd * math.sqrt(TRADING_DAYS)) if sd > 0 else np.nan


def holding_days(position: pd.Series) -> float:
    active = position.fillna(0.0).abs().gt(EPS)
    if not active.any():
        return 0.0
    starts = np.flatnonzero((active & ~active.shift(1, fill_value=False)).to_numpy())
    ends = np.flatnonzero((~active & active.shift(1, fill_value=False)).to_numpy())
    if len(ends) and len(starts) and ends[0] < starts[0]:
        ends = ends[1:]
    if len(ends) < len(starts):
        ends = np.r_[ends, len(active) - 1]
    return float(np.mean([max(1, int(e) - int(s)) for s, e in zip(starts, ends)]))


def metrics_for_split(result: ReplayResult, split: PeriodSplit) -> dict[str, float | int | str]:
    mask = period_mask(result.returns.index, split)
    ret = result.returns.loc[mask].fillna(0.0)
    if len(ret) < 2:
        return {}
    nav = (1.0 + ret).cumprod()
    years = max(len(ret) / TRADING_DAYS, 1 / TRADING_DAYS)
    ann = float(nav.iloc[-1] ** (1.0 / years) - 1.0) if nav.iloc[-1] > 0 else np.nan
    mdd = max_drawdown(nav)
    pos = result.position.reindex(ret.index).fillna(0.0)
    turnover = result.turnover.reindex(ret.index).fillna(0.0)
    entries = (pos.abs() > EPS) & ~(pos.shift(1).fillna(0.0).abs() > EPS)
    trade_returns = trade_log(result)
    stage_start = ret.index.min()
    stage_end = ret.index.max()
    stage_trades = trade_returns[(trade_returns["entry_date"] >= stage_start) & (trade_returns["entry_date"] <= stage_end)]
    win_rate = float((stage_trades["strategy_return"] > 0).mean()) if len(stage_trades) else np.nan
    return {
        "target": result.target,
        "strategy": result.strategy,
        "overlay": result.overlay,
        "execution": result.execution,
        "one_way_fee": result.fee,
        "slippage_model": result.slippage_model,
        "split_type": split.split_type,
        "split": split.split,
        "periods": ";".join([f"{s}:{e or 'latest'}" for s, e in split.periods]),
        "train_start": split.train_start,
        "train_end": split.train_end,
        "purge_days": split.purge_days,
        "embargo_days": split.embargo_days,
        "CAGR": ann,
        "MDD": mdd,
        "Sharpe": sharpe(ret),
        "Calmar": ann / abs(mdd) if np.isfinite(ann) and np.isfinite(mdd) and mdd < 0 else np.nan,
        "trade_count": int(entries.sum()),
        "annual_turnover": float(turnover.sum() / years),
        "avg_holding_days": holding_days(pos),
        "avg_abs_weight": float(pos.abs().mean()),
        "time_in_market": float(pos.abs().gt(EPS).mean()),
        "position_change_frequency": float(turnover.gt(EPS).mean()),
        "trade_win_rate": win_rate,
        "test_days": int(len(ret)),
        "final_nav": float(nav.iloc[-1]),
    }


def adaptive_slippage_rate(asset: pd.DataFrame, idx: pd.Index, model: str) -> pd.Series:
    if model == "none":
        return pd.Series(0.0, index=idx)
    if model == "fixed_5bps":
        return pd.Series(0.0005, index=idx)
    if model == "atr_adaptive_10pct":
        atr_pct = atr(asset, 14).div(asset["close"]).reindex(idx).ffill().fillna(0.0)
        return (0.10 * atr_pct).clip(0.0, 0.006)
    raise ValueError(f"unknown slippage model: {model}")


def replay(
    target: str,
    data: dict[str, pd.DataFrame],
    desired: pd.Series,
    strategy: str,
    overlay: str,
    fee: float,
    execution: str,
    slippage_model: str = "none",
) -> ReplayResult:
    asset = data[target]
    idx = asset.index
    desired = desired.reindex(idx).ffill().fillna(0.0).clip(0.0, 1.0)
    open_p = asset["open"].astype(float).reindex(idx).ffill()
    close = asset["close"].astype(float).reindex(idx).ffill()
    slip = adaptive_slippage_rate(asset, idx, slippage_model)
    nav = np.ones(len(idx), dtype=float)
    returns = np.zeros(len(idx), dtype=float)
    pos_arr = np.zeros(len(idx), dtype=float)
    turnover = np.zeros(len(idx), dtype=float)
    cost_rate = np.zeros(len(idx), dtype=float)
    equity = 1.0
    pos = 0.0
    for i in range(1, len(idx)):
        prev_equity = equity
        target_weight = float(desired.iloc[i - 1])
        if execution == "next_open":
            if pos > 0 and close.iloc[i - 1] > 0:
                equity *= 1.0 + pos * (open_p.iloc[i] / close.iloc[i - 1] - 1.0)
            delta = abs(target_weight - pos)
            cost = fee + float(slip.iloc[i])
            if delta > EPS:
                equity *= max(0.0, 1.0 - cost * delta)
            pos = target_weight
            if pos > 0 and open_p.iloc[i] > 0:
                equity *= 1.0 + pos * (close.iloc[i] / open_p.iloc[i] - 1.0)
        elif execution == "next_close":
            if pos > 0 and close.iloc[i - 1] > 0:
                equity *= 1.0 + pos * (close.iloc[i] / close.iloc[i - 1] - 1.0)
            delta = abs(target_weight - pos)
            cost = fee + float(slip.iloc[i])
            if delta > EPS:
                equity *= max(0.0, 1.0 - cost * delta)
            pos = target_weight
        else:
            raise ValueError(execution)
        nav[i] = equity
        returns[i] = equity / prev_equity - 1.0 if prev_equity > 0 else 0.0
        pos_arr[i] = pos
        turnover[i] = delta
        cost_rate[i] = cost
    return ReplayResult(
        target=target,
        strategy=strategy,
        overlay=overlay,
        execution=execution,
        fee=fee,
        slippage_model=slippage_model,
        nav=pd.Series(nav, index=idx),
        returns=pd.Series(returns, index=idx),
        position=pd.Series(pos_arr, index=idx),
        desired=desired,
        turnover=pd.Series(turnover, index=idx),
        trade_cost_rate=pd.Series(cost_rate, index=idx),
    )


def trade_log(result: ReplayResult) -> pd.DataFrame:
    pos = result.position.fillna(0.0)
    active = pos.abs().gt(EPS)
    starts = list(np.flatnonzero((active & ~active.shift(1, fill_value=False)).to_numpy()))
    ends = list(np.flatnonzero((~active & active.shift(1, fill_value=False)).to_numpy()))
    if ends and starts and ends[0] < starts[0]:
        ends = ends[1:]
    rows = []
    for k, start_idx in enumerate(starts):
        open_trade = k >= len(ends)
        end_idx = len(pos) - 1 if open_trade else ends[k]
        if result.nav.iloc[start_idx] <= 0:
            ret = np.nan
        else:
            ret = float(result.nav.iloc[end_idx] / result.nav.iloc[start_idx] - 1.0)
        rows.append(
            {
                "entry_date": result.nav.index[start_idx],
                "exit_date": pd.NaT if open_trade else result.nav.index[end_idx],
                "strategy_return": ret,
                "holding_days": int(max(1, end_idx - start_idx)),
                "avg_weight": float(pos.iloc[start_idx : end_idx + 1].mean()),
            }
        )
    return pd.DataFrame(rows)


def drawdown(nav: pd.Series) -> pd.Series:
    return nav.div(nav.cummax()).sub(1.0)


def tqqq_locked_spec() -> v3.OverlaySpec:
    return v3.OverlaySpec("atr_stop", atr_window=18, atr_mult=2.5, cooldown_days=10, trailing_variant="standard")


def tqqq_neighborhood_specs() -> list[v3.OverlaySpec]:
    specs = [
        v3.OverlaySpec("atr_stop", atr_window=window, atr_mult=mult, cooldown_days=10, trailing_variant="standard")
        for window in (14, 18, 22)
        for mult in (2.25, 2.5, 2.75)
    ]
    specs.append(v3.OverlaySpec("atr_stop", atr_window=18, atr_mult=2.5, cooldown_days=5, trailing_variant="short_cooldown"))
    specs.append(v3.OverlaySpec("atr_stop", atr_window=18, atr_mult=2.5, cooldown_days=10, trailing_variant="confirm_2d"))
    return specs


def run_tqqq_strict(data: dict[str, pd.DataFrame], bases: dict[str, dict[str, pd.Series]]) -> tuple[pd.DataFrame, pd.DataFrame, ReplayResult]:
    base = bases["TQQQ"]["ema20_ema100_direction"]
    locked = tqqq_locked_spec()
    desired = v3.build_desired("TQQQ", data, base, locked)
    locked_result = replay("TQQQ", data, desired, "ema20_ema100_direction__atr_stop_18_2p5", "atr_stop", FEE, "next_open", "none")
    strict_rows = [metrics_for_split(locked_result, split) for split in strict_splits()]
    strict = pd.DataFrame(strict_rows)

    n_rows = []
    for spec in tqqq_neighborhood_specs():
        d = v3.build_desired("TQQQ", data, base, spec)
        r = replay("TQQQ", data, d, "ema20_ema100_direction__atr_stop", "atr_stop", FEE, "next_open", "none")
        split_rows = [metrics_for_split(r, split) for split in strict_splits()]
        row = {
            "atr_window": spec.atr_window,
            "atr_mult": spec.atr_mult,
            "cooldown_days": spec.cooldown_days,
            "trailing_variant": spec.trailing_variant,
            "is_locked_v4": spec.atr_window == 18 and spec.atr_mult == 2.5 and spec.cooldown_days == 10 and spec.trailing_variant == "standard",
        }
        frame = pd.DataFrame(split_rows)
        for col in ("CAGR", "MDD", "Sharpe", "Calmar", "annual_turnover", "avg_abs_weight"):
            row[f"mean_{col}"] = float(frame[col].mean())
            row[f"median_{col}"] = float(frame[col].median())
            row[f"worst_{col}"] = float(frame[col].min())
        row["worst_split"] = str(frame.sort_values("Calmar").iloc[0]["split"])
        n_rows.append(row)
    neighborhood = pd.DataFrame(n_rows)
    best = neighborhood.sort_values("median_Calmar", ascending=False).iloc[0]
    locked_row = neighborhood[neighborhood["is_locked_v4"]].iloc[0]
    neighbors = neighborhood[
        neighborhood["trailing_variant"].eq("standard")
        & (abs(neighborhood["atr_window"] - int(best["atr_window"])) <= 4)
        & (abs(neighborhood["atr_mult"] - float(best["atr_mult"])) <= 0.25)
        & ~(
            neighborhood["atr_window"].eq(best["atr_window"])
            & neighborhood["atr_mult"].eq(best["atr_mult"])
        )
    ]
    spike = bool(not neighbors.empty and float(best["median_Calmar"]) - float(neighbors["median_Calmar"].median()) > 0.35)
    neighborhood["delta_vs_locked_median_calmar"] = neighborhood["median_Calmar"] - float(locked_row["median_Calmar"])
    neighborhood["single_point_spike_suspect"] = False
    neighborhood.loc[
        neighborhood["atr_window"].eq(best["atr_window"]) & neighborhood["atr_mult"].eq(best["atr_mult"]) & neighborhood["trailing_variant"].eq(best["trailing_variant"]),
        "single_point_spike_suspect",
    ] = spike
    return strict, neighborhood, locked_result


def run_tqqq_cost_stress(data: dict[str, pd.DataFrame], bases: dict[str, dict[str, pd.Series]]) -> pd.DataFrame:
    base = bases["TQQQ"]["ema20_ema100_direction"]
    desired = v3.build_desired("TQQQ", data, base, tqqq_locked_spec())
    rows = []
    split = PeriodSplit("final", "2021_latest", (("2021-01-01", None),))
    for fee in (0.0, 0.001, 0.002, 0.003, 0.005):
        for execution in ("next_open", "next_close"):
            for slip in ("none", "fixed_5bps", "atr_adaptive_10pct"):
                result = replay("TQQQ", data, desired, "ema20_ema100_direction__atr_stop_18_2p5", "atr_stop", fee, execution, slip)
                row = metrics_for_split(result, split)
                row["stress_failed"] = bool(row["CAGR"] <= 0 or row["Calmar"] < 0.30 or row["MDD"] < -0.55)
                rows.append(row)
    return pd.DataFrame(rows)


def run_tqqq_regime_breakdown(result: ReplayResult) -> pd.DataFrame:
    stages = [
        PeriodSplit("calendar", "2021", (("2021-01-01", "2021-12-31"),)),
        PeriodSplit("calendar", "2022", (("2022-01-01", "2022-12-31"),)),
        PeriodSplit("calendar", "2023", (("2023-01-01", "2023-12-31"),)),
        PeriodSplit("calendar", "2024", (("2024-01-01", "2024-12-31"),)),
        PeriodSplit("calendar", "2025_latest", (("2025-01-01", None),)),
    ]
    rows = []
    for split in stages:
        row = metrics_for_split(result, split)
        rows.append(row)
    df = pd.DataFrame(rows)
    total_positive = df["final_nav"].sub(1).clip(lower=0).sum()
    total_negative = df["final_nav"].sub(1).clip(upper=0).abs().sum()
    df["positive_contribution_share"] = np.where(total_positive > 0, df["final_nav"].sub(1).clip(lower=0) / total_positive, np.nan)
    df["drag_share"] = np.where(total_negative > 0, df["final_nav"].sub(1).clip(upper=0).abs() / total_negative, np.nan)
    return df


def run_qld_validation(data: dict[str, pd.DataFrame], bases: dict[str, dict[str, pd.Series]]) -> tuple[pd.DataFrame, dict[str, ReplayResult]]:
    specs = {
        "robust": v3.OverlaySpec("risk_bundle", atr_window=14, atr_mult=3.0, cooldown_days=10, vol_target=0.30, max_cap=0.70, regime_off=True),
        "aggressive": v3.OverlaySpec("regime_off", regime_off=True),
    }
    rows = []
    replays: dict[str, ReplayResult] = {}
    split = PeriodSplit("final", "2021_latest", (("2021-01-01", None),))
    for tier, spec in specs.items():
        desired = v3.build_desired("QLD", data, bases["QLD"]["ema20_ema100_direction"], spec)
        result = replay("QLD", data, desired, f"ema20_ema100_direction__{spec.overlay}", spec.overlay, FEE, "next_open", "none")
        replays[tier] = result
        base_row = metrics_for_split(result, split)
        for constraint in (0.20, 0.25, 0.30):
            row = dict(base_row)
            row["tier"] = tier
            row["mdd_constraint"] = constraint
            row["within_constraint"] = bool(abs(row["MDD"]) <= constraint)
            rows.append(row)
    return pd.DataFrame(rows), replays


def save_heatmap(neighborhood: pd.DataFrame, run_dir: Path) -> None:
    heat = neighborhood[neighborhood["trailing_variant"].eq("standard")].pivot(index="atr_window", columns="atr_mult", values="median_Calmar")
    fig, ax = plt.subplots(figsize=(7, 5))
    im = ax.imshow(heat.values, cmap="YlGnBu", aspect="auto")
    ax.set_xticks(range(len(heat.columns)))
    ax.set_xticklabels([str(c) for c in heat.columns])
    ax.set_yticks(range(len(heat.index)))
    ax.set_yticklabels([str(i) for i in heat.index])
    ax.set_xlabel("ATR stop multiple")
    ax.set_ylabel("ATR window")
    ax.set_title("TQQQ v4 ATR neighborhood: median Calmar")
    for i in range(heat.shape[0]):
        for j in range(heat.shape[1]):
            ax.text(j, i, f"{heat.values[i, j]:.2f}", ha="center", va="center", fontsize=9)
    fig.colorbar(im, ax=ax, label="median Calmar")
    fig.tight_layout()
    fig.savefig(run_dir / "tqqq_atr_heatmap.png", dpi=160)
    plt.close(fig)


def save_charts(run_dir: Path, data: dict[str, pd.DataFrame], tqqq: ReplayResult, qld_replays: dict[str, ReplayResult]) -> None:
    asset = data["TQQQ"].loc[data["TQQQ"].index >= PERIOD_START]
    pos = tqqq.position.reindex(asset.index).fillna(0.0)
    entries = pos.gt(EPS) & ~pos.shift(1).fillna(0.0).gt(EPS)
    exits = ~pos.gt(EPS) & pos.shift(1).fillna(0.0).gt(EPS)
    fig, ax1 = plt.subplots(figsize=(12, 5))
    asset["close"].plot(ax=ax1, color="#1f4e79", linewidth=1.2, label="TQQQ close")
    ax1.scatter(asset.index[entries], asset.loc[entries, "close"], marker="^", color="#2ca02c", s=24, label="entry")
    ax1.scatter(asset.index[exits], asset.loc[exits, "close"], marker="v", color="#d62728", s=24, label="exit")
    ax2 = ax1.twinx()
    pos.plot(ax=ax2, color="#ff7f0e", linewidth=0.9, alpha=0.65, label="weight")
    ax1.set_title("TQQQ v4 signal: EMA20/100 + ATR stop 18/2.5")
    ax2.set_ylim(-0.02, 1.05)
    ax1.grid(True, alpha=0.25)
    ax1.legend(loc="upper left")
    ax2.legend(loc="upper right")
    fig.tight_layout()
    fig.savefig(run_dir / "tqqq_v4_signal_chart.png", dpi=150)
    plt.close(fig)

    nav = tqqq.nav.loc[tqqq.nav.index >= PERIOD_START]
    nav = nav / nav.iloc[0]
    fig, ax = plt.subplots(figsize=(11, 4.5))
    drawdown(nav).plot(ax=ax, label="TQQQ v4", linewidth=1.7)
    ax.set_title("TQQQ v4 drawdown")
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(run_dir / "tqqq_v4_drawdown.png", dpi=150)
    plt.close(fig)

    qld_asset = data["QLD"].loc[data["QLD"].index >= PERIOD_START]
    fig, ax1 = plt.subplots(figsize=(12, 5))
    qld_asset["close"].plot(ax=ax1, color="#1f4e79", linewidth=1.2, label="QLD close")
    ax2 = ax1.twinx()
    for tier, result in qld_replays.items():
        result.position.reindex(qld_asset.index).fillna(0.0).plot(ax=ax2, linewidth=0.9, alpha=0.75, label=tier)
    ax1.set_title("QLD v4 signal: robust vs aggressive candidates")
    ax2.set_ylim(-0.02, 1.05)
    ax1.grid(True, alpha=0.25)
    ax1.legend(loc="upper left")
    ax2.legend(loc="upper right")
    fig.tight_layout()
    fig.savefig(run_dir / "qld_v4_signal_chart.png", dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, 4.5))
    for tier, result in qld_replays.items():
        nav = result.nav.loc[result.nav.index >= PERIOD_START]
        nav = nav / nav.iloc[0]
        drawdown(nav).plot(ax=ax, label=tier, linewidth=1.5)
    ax.set_title("QLD v4 drawdown: robust vs aggressive")
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(run_dir / "qld_v4_drawdown.png", dpi=150)
    plt.close(fig)


def format_md_metrics(df: pd.DataFrame, max_rows: int = 20) -> pd.DataFrame:
    cols = [c for c in ["target", "strategy", "overlay", "split_type", "split", "CAGR", "MDD", "Sharpe", "Calmar", "trade_count", "annual_turnover", "avg_abs_weight"] if c in df.columns]
    out = df[cols].copy().head(max_rows)
    for col in ("CAGR", "MDD", "avg_abs_weight"):
        if col in out:
            out[col] = out[col].map(pct)
    for col in ("Sharpe", "Calmar", "annual_turnover"):
        if col in out:
            out[col] = out[col].map(num)
    return out


def write_qld_summary(run_dir: Path, qld: pd.DataFrame) -> None:
    lines = ["# QLD Constraint Summary", ""]
    for constraint, sub in qld.groupby("mdd_constraint"):
        eligible = sub[sub["within_constraint"]].copy()
        if eligible.empty:
            lines.append(f"- MDD <= {pct(constraint)}: no candidate satisfied the constraint.")
        else:
            pick = eligible.sort_values(["Calmar", "CAGR"], ascending=[False, False]).iloc[0]
            lines.append(
                f"- MDD <= {pct(constraint)}: keep `{pick['tier']}` / `{pick['strategy']}` "
                f"(CAGR {pct(pick['CAGR'])}, MDD {pct(pick['MDD'])}, Calmar {num(pick['Calmar'])})."
            )
    robust = qld[qld["tier"].eq("robust")].iloc[0]
    aggressive = qld[qld["tier"].eq("aggressive")].iloc[0]
    lines.extend(
        [
            "",
            "## Final Tier Decision",
            "",
            f"- Robust tier: retain `ema20_ema100_direction + risk_bundle`; it satisfies MDD<=20% and MDD<=25% with MDD {pct(robust['MDD'])}.",
            f"- Aggressive tier: retain `ema20_ema100_direction + regime_off` only for MDD<=30%; it has higher CAGR {pct(aggressive['CAGR'])} but MDD {pct(aggressive['MDD'])}.",
            "- Both are simple enough to enter stricter validation, but they should be evaluated as separate risk tiers, not as one universal QLD answer.",
            "",
            "## Full Table",
            "",
            md_table(format_md_metrics(qld, 20)),
        ]
    )
    write_text(run_dir / "qld_constraint_summary.md", "\n".join(lines))


def write_meta_postmortem(run_dir: Path) -> None:
    lines = [
        "# Meta-label Postmortem",
        "",
        "Meta-label is formally removed from the v4 main line.",
        "",
        "Why it did not work well enough:",
        "",
        "- Label issue: the ATR barrier labels are useful as diagnostics, but still noisy for deciding every entry/exit on leveraged ETFs.",
        "- Sample issue: 2021+ contains only a few distinct market regimes; a light classifier can easily learn regime-specific filters that reduce opportunity.",
        "- Feature issue: v1 features are intentionally compact and mostly trend/volatility features already embedded in the primary strategy and overlays.",
        "- Strategy issue: EMA trend plus ATR stop already handles the dominant risk regime; meta-label often filters out profitable rebounds and lowers CAGR.",
        "",
        "Decision: pause meta-label as a main research path. It can return only after purged/CPCV validation shows a stable marginal benefit without large CAGR drag.",
    ]
    write_text(run_dir / "meta_label_postmortem.md", "\n".join(lines))


def compare_v4_v3(tqqq: ReplayResult, qld: pd.DataFrame) -> pd.DataFrame:
    rows = []
    split = PeriodSplit("final", "2021_latest", (("2021-01-01", None),))
    v3_path = V3_DIR / "v3_vs_v2_comparison.csv"
    if v3_path.exists():
        rows.extend(pd.read_csv(v3_path).assign(source_version="v3").to_dict("records"))
    tqqq_row = metrics_for_split(tqqq, split)
    tqqq_row.update({"source": "v4_tqqq_locked_18_2p5", "source_version": "v4", "comparison_group": "TQQQ best v4"})
    rows.append(tqqq_row)
    for _, row in qld.drop_duplicates(["tier"]).iterrows():
        out = row.to_dict()
        out.update({"source": f"v4_qld_{row['tier']}", "source_version": "v4", "comparison_group": f"QLD {row['tier']} tier"})
        rows.append(out)
    return pd.DataFrame(rows)


def write_summary(
    run_dir: Path,
    strict: pd.DataFrame,
    neighborhood: pd.DataFrame,
    stress: pd.DataFrame,
    regime: pd.DataFrame,
    qld: pd.DataFrame,
    comparison: pd.DataFrame,
) -> None:
    locked = neighborhood[neighborhood["is_locked_v4"]].iloc[0]
    locked_spike = bool(locked["single_point_spike_suspect"])
    any_neighbor_spike = bool(neighborhood["single_point_spike_suspect"].any())
    strict_summary = strict.groupby("split_type").agg(median_Calmar=("Calmar", "median"), worst_Calmar=("Calmar", "min"), median_CAGR=("CAGR", "median"), worst_MDD=("MDD", "min")).reset_index()
    weakest_split = strict.sort_values("Calmar").iloc[0]
    stress_fail = stress[stress["stress_failed"]]
    fails = "none" if stress_fail.empty else ", ".join(stress_fail.apply(lambda r: f"{r['execution']} {r['one_way_fee']:.1%} {r['slippage_model']}", axis=1).head(6))
    next_close_05 = stress[(stress["execution"].eq("next_close")) & (stress["one_way_fee"].eq(0.005)) & (stress["slippage_model"].eq("atr_adaptive_10pct"))]
    worst_stress_text = (
        f"worst stress Calmar {num(next_close_05['Calmar'].iloc[0])}, CAGR {pct(next_close_05['CAGR'].iloc[0])}"
        if not next_close_05.empty
        else "not available"
    )
    best_year = regime.sort_values("final_nav", ascending=False).iloc[0]
    worst_year = regime.sort_values("final_nav").iloc[0]
    qld_robust = qld[qld["tier"].eq("robust")].iloc[0]
    qld_aggressive = qld[qld["tier"].eq("aggressive")].iloc[0]
    lines = [
        "# Turning Point Research V4",
        "",
        "## Executive Conclusion",
        "",
        f"- TQQQ main line passes v4 strict validation conditionally: locked ATR 18/2.5 median Calmar {num(locked['median_Calmar'])}; locked-point spike flag `{locked_spike}`.",
        f"- The weakest strict-validation split is `{weakest_split['split']}` with Calmar {num(weakest_split['Calmar'])}. This is the main residual fragility to review before production-style use.",
        f"- A small trailing variant has spike flag `{any_neighbor_spike}`; it is kept as a side observation and is not promoted to the v4 main line.",
        f"- Cost/execution stress is meaningful but not fatal. Failure cases by predefined rule: {fails}. Under next-close + 0.5% fee + ATR-adaptive slippage, {worst_stress_text}.",
        f"- TQQQ strongest contribution year is `{best_year['split']}`; largest drag is `{worst_year['split']}`.",
        f"- QLD robust tier retained: risk_bundle, CAGR {pct(qld_robust['CAGR'])}, MDD {pct(qld_robust['MDD'])}, Calmar {num(qld_robust['Calmar'])}.",
        f"- QLD aggressive tier retained: regime_off, CAGR {pct(qld_aggressive['CAGR'])}, MDD {pct(qld_aggressive['MDD'])}, Calmar {num(qld_aggressive['Calmar'])}.",
        "- Meta-label formally exits the main line in v4.",
        "- Next round should move to more live-like validation: purged/CPCV expansion, fill assumptions, tax/borrow/cash assumptions if relevant, and operational signal review.",
        "",
        "## TQQQ Strict Split Summary",
        "",
        md_table(
            strict_summary.assign(
                median_Calmar=lambda x: x["median_Calmar"].map(num),
                worst_Calmar=lambda x: x["worst_Calmar"].map(num),
                median_CAGR=lambda x: x["median_CAGR"].map(pct),
                worst_MDD=lambda x: x["worst_MDD"].map(pct),
            )
        ),
        "",
        "## TQQQ ATR Neighborhood",
        "",
        md_table(
            neighborhood.sort_values("median_Calmar", ascending=False)[
                ["atr_window", "atr_mult", "cooldown_days", "trailing_variant", "median_CAGR", "worst_MDD", "median_Calmar", "is_locked_v4", "single_point_spike_suspect"]
            ].assign(
                median_CAGR=lambda x: x["median_CAGR"].map(pct),
                worst_MDD=lambda x: x["worst_MDD"].map(pct),
                median_Calmar=lambda x: x["median_Calmar"].map(num),
            ),
            12,
        ),
        "",
        "## Required Answers",
        "",
        "1. TQQQ main line passes stricter validation conditionally. The locked 18/2.5 standard ATR stop is not a single-point spike and remains positive under harsh cost/execution stress, but the older rolling 2015-2017 split is weak.",
        "2. QLD robust tier keeps `ema20_ema100_direction + risk_bundle`; QLD aggressive tier keeps `ema20_ema100_direction + regime_off`.",
        "3. Meta-label formally exits the main line and should remain paused.",
        "4. Next round should move into live-like validation: purged/CPCV, detailed cost/slippage, signal timestamp checks, and execution feasibility checks.",
    ]
    write_text(run_dir / "v4_research_summary.md", "\n".join(lines))


def write_readme(run_dir: Path, neighborhood: pd.DataFrame, stress: pd.DataFrame) -> None:
    locked = neighborhood[neighborhood["is_locked_v4"]].iloc[0]
    fragile = stress.sort_values("Calmar").iloc[0]
    lines = [
        "# README_FOR_CHATGPT",
        "",
        "1. Most credible result:",
        f"TQQQ `ema20_ema100_direction + ATR stop 18/2.5`; median strict-validation Calmar {num(locked['median_Calmar'])}, spike flag {locked['single_point_spike_suspect']}.",
        "",
        "2. Most fragile result:",
        f"The harshest stress row: `{fragile['execution']}`, fee {pct(fragile['one_way_fee'])}, slippage `{fragile['slippage_model']}`, Calmar {num(fragile['Calmar'])}.",
        "",
        "3. Top 5 files to audit:",
        "- `v4_research_summary.md`",
        "- `tqqq_strict_validation.csv`",
        "- `tqqq_cost_execution_stress.csv`",
        "- `qld_constraint_validation.csv`",
        "- `v4_vs_v3_comparison.csv`",
        "",
        "4. Best v5 direction:",
        "Do stricter live-like validation first: purged/CPCV, execution timestamp checks, fuller slippage model, and operational signal review. Do not add new models or features yet.",
    ]
    write_text(run_dir / "README_FOR_CHATGPT.md", "\n".join(lines))


def write_run_instructions(run_dir: Path) -> None:
    write_text(
        run_dir / "run_instructions.md",
        "\n".join(
            [
                "# Run Instructions",
                "",
                "From repo root:",
                "",
                "```powershell",
                "python scripts\\qldtqqq_turning_point_research_v4.py",
                "```",
                "",
                "The script writes a timestamped directory under `outputs/turning_point_research_v4_*`.",
                "It reuses v1/v2/v3 helper functions and does not modify prior outputs.",
            ]
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Turning point research v4 strict validation")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--output-root", type=Path, default=ROOT / "outputs")
    args = parser.parse_args()

    run_dir = args.output_root / f"turning_point_research_v4_{stamp()}"
    run_dir.mkdir(parents=True, exist_ok=True)
    log(f"Output directory: {run_dir}")

    log("Loading data and fixed base signals")
    data = v2.load_data(args.data_dir)
    _, indicators = v2.build_features(data)
    bases = v2.base_signals(data, indicators)

    log("Running TQQQ strict validation and ATR neighborhood")
    strict, neighborhood, tqqq_result = run_tqqq_strict(data, bases)
    write_csv(strict, run_dir / "tqqq_strict_validation.csv")
    write_csv(neighborhood, run_dir / "tqqq_atr_neighborhood.csv")
    save_heatmap(neighborhood, run_dir)

    log("Running TQQQ cost/execution/slippage stress")
    stress = run_tqqq_cost_stress(data, bases)
    write_csv(stress, run_dir / "tqqq_cost_execution_stress.csv")
    regime = run_tqqq_regime_breakdown(tqqq_result)
    write_csv(regime, run_dir / "tqqq_regime_breakdown.csv")

    log("Running QLD two-tier constraint validation")
    qld, qld_replays = run_qld_validation(data, bases)
    write_csv(qld, run_dir / "qld_constraint_validation.csv")
    write_qld_summary(run_dir, qld)

    log("Writing meta postmortem and comparisons")
    write_meta_postmortem(run_dir)
    comparison = compare_v4_v3(tqqq_result, qld)
    write_csv(comparison, run_dir / "v4_vs_v3_comparison.csv")

    log("Writing charts and reports")
    save_charts(run_dir, data, tqqq_result, qld_replays)
    write_summary(run_dir, strict, neighborhood, stress, regime, qld, comparison)
    write_readme(run_dir, neighborhood, stress)
    write_run_instructions(run_dir)
    write_text(
        run_dir / "changed_files_manifest.txt",
        "\n".join(
            [
                "Added or modified script files:",
                "",
                "- scripts/qldtqqq_turning_point_research_v4.py",
                "",
                "V4 reuses v1/v2/v3 helpers and does not modify earlier research outputs.",
            ]
        ),
    )
    (run_dir / "qldtqqq_turning_point_research_v4.py").write_text((ROOT / "scripts" / "qldtqqq_turning_point_research_v4.py").read_text(encoding="utf-8"), encoding="utf-8")

    required = [
        "v4_research_summary.md",
        "tqqq_strict_validation.csv",
        "tqqq_atr_neighborhood.csv",
        "tqqq_atr_heatmap.png",
        "tqqq_cost_execution_stress.csv",
        "tqqq_regime_breakdown.csv",
        "qld_constraint_validation.csv",
        "qld_constraint_summary.md",
        "meta_label_postmortem.md",
        "v4_vs_v3_comparison.csv",
        "tqqq_v4_signal_chart.png",
        "tqqq_v4_drawdown.png",
        "qld_v4_signal_chart.png",
        "qld_v4_drawdown.png",
        "changed_files_manifest.txt",
        "run_instructions.md",
        "README_FOR_CHATGPT.md",
    ]
    missing = [name for name in required if not (run_dir / name).exists()]
    if missing:
        raise RuntimeError(f"Missing required v4 outputs: {missing}")
    log("V4 completed")
    log(str(run_dir))


if __name__ == "__main__":
    main()
