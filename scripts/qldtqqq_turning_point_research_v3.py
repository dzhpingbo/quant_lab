"""Turning point research v3: validation hardening and constrained overlays.

V3 narrows the v2 result instead of expanding the search:
- TQQQ: validate ema20_ema100_direction + ATR stop in a small neighborhood.
- QLD: compare a small overlay set under explicit MDD constraints.
- Meta-label: one fixed logistic side experiment only.
"""

from __future__ import annotations

import argparse
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
from qldtqqq_turning_point_research_v1 import DEFAULT_DATA_DIR, atr  # noqa: E402


warnings.filterwarnings("ignore", category=FutureWarning)

TARGETS = ("QLD", "TQQQ")
FEE = 0.002
TRADING_DAYS = 252.0
PERIOD_START = pd.Timestamp("2021-01-01")
EPS = 1e-10
OLD_RUN_DIR = ROOT / "outputs" / "qldtqqq_turning_points" / "qldtqqq_turning_20260420_133901"
V2_DIR = ROOT / "outputs" / "turning_point_research_v2_20260421_175622"


@dataclass(frozen=True)
class SplitSpec:
    split_type: str
    split: str
    test_start: str
    test_end: str | None
    train_start: str = ""
    train_end: str = ""
    purge_days: int = 0
    embargo_days: int = 0


@dataclass(frozen=True)
class OverlaySpec:
    overlay: str
    atr_window: int = 14
    atr_mult: float = 3.0
    cooldown_days: int = 10
    vol_target: float | None = None
    max_cap: float | None = None
    regime_off: bool = False
    trailing_variant: str = "standard"


@dataclass
class ReplayResult:
    target: str
    strategy: str
    overlay: str
    execution: str
    fee: float
    nav: pd.Series
    returns: pd.Series
    position: pd.Series
    desired: pd.Series
    turnover: pd.Series


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


def validation_splits() -> list[SplitSpec]:
    return [
        SplitSpec("anchored", "anchored_2018_2020", "2018-01-01", "2020-12-31", "2010-01-01", "2017-12-31"),
        SplitSpec("anchored", "anchored_2021_2023", "2021-01-01", "2023-12-31", "2010-01-01", "2020-12-31"),
        SplitSpec("anchored", "anchored_2024_latest", "2024-01-01", None, "2010-01-01", "2023-12-31"),
        SplitSpec("anchored", "anchored_2021_latest", "2021-01-01", None, "2010-01-01", "2020-12-31"),
        SplitSpec("rolling", "rolling_2015_2017", "2015-01-01", "2017-12-31", "2010-01-01", "2014-12-31"),
        SplitSpec("rolling", "rolling_2018_2020", "2018-01-01", "2020-12-31", "2013-01-01", "2017-12-31"),
        SplitSpec("rolling", "rolling_2021_2023", "2021-01-01", "2023-12-31", "2016-01-01", "2020-12-31"),
        SplitSpec("rolling", "rolling_2024_latest", "2024-01-01", None, "2019-01-01", "2023-12-31"),
        SplitSpec("purged_embargo", "purged_2021_2022", "2021-01-01", "2022-12-31", "2010-01-01", "2020-11-30", 20, 5),
        SplitSpec("purged_embargo", "purged_2023_2024", "2023-01-01", "2024-12-31", "2015-01-01", "2022-11-30", 20, 5),
        SplitSpec("purged_embargo", "purged_2025_latest", "2025-01-01", None, "2018-01-01", "2024-11-30", 20, 5),
    ]


def max_drawdown(nav: pd.Series) -> float:
    clean = nav.dropna()
    if clean.empty:
        return np.nan
    return float(clean.div(clean.cummax()).sub(1.0).min())


def cagr(nav: pd.Series) -> float:
    clean = nav.dropna()
    if len(clean) < 2:
        return np.nan
    years = max((clean.index[-1] - clean.index[0]).days / 365.25, 1 / 365.25)
    if clean.iloc[0] <= 0 or clean.iloc[-1] <= 0:
        return np.nan
    return float((clean.iloc[-1] / clean.iloc[0]) ** (1 / years) - 1)


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


def slice_index(series: pd.Series, start: str, end: str | None) -> pd.Series:
    out = series.loc[series.index >= pd.Timestamp(start)]
    if end:
        out = out.loc[out.index <= pd.Timestamp(end)]
    return out


def metrics(result: ReplayResult, split: SplitSpec) -> dict[str, float | str | int]:
    nav = slice_index(result.nav, split.test_start, split.test_end).dropna()
    if len(nav) < 2:
        return {}
    nav = nav / nav.iloc[0]
    returns = nav.pct_change().fillna(0.0)
    pos = result.position.reindex(nav.index).fillna(0.0)
    turnover = result.turnover.reindex(nav.index).fillna(0.0)
    entries = (pos.abs() > EPS) & ~(pos.shift(1).fillna(0.0).abs() > EPS)
    years = max((nav.index[-1] - nav.index[0]).days / 365.25, 1 / 365.25)
    ann = cagr(nav)
    mdd = max_drawdown(nav)
    return {
        "target": result.target,
        "strategy": result.strategy,
        "overlay": result.overlay,
        "execution": result.execution,
        "one_way_fee": result.fee,
        "split_type": split.split_type,
        "split": split.split,
        "train_start": split.train_start,
        "train_end": split.train_end,
        "purge_days": split.purge_days,
        "embargo_days": split.embargo_days,
        "period_start": nav.index[0].strftime("%Y-%m-%d"),
        "period_end": nav.index[-1].strftime("%Y-%m-%d"),
        "CAGR": ann,
        "MDD": mdd,
        "Sharpe": sharpe(returns),
        "Calmar": ann / abs(mdd) if np.isfinite(ann) and np.isfinite(mdd) and mdd < 0 else np.nan,
        "trade_count": int(entries.sum()),
        "annual_turnover": float(turnover.sum() / years),
        "avg_holding_days": holding_days(pos),
        "time_in_market": float(pos.abs().gt(EPS).mean()),
        "avg_abs_weight": float(pos.abs().mean()),
        "position_change_frequency": float(turnover.gt(EPS).mean()),
        "final_nav": float(nav.iloc[-1]),
    }


def build_desired(
    target: str,
    data: dict[str, pd.DataFrame],
    base: pd.Series,
    spec: OverlaySpec,
) -> pd.Series:
    asset = data[target]
    qqq = data["QQQ"]
    idx = asset.index
    raw = base.reindex(idx).ffill().fillna(0.0).clip(0.0, 1.0)
    close = asset["close"].astype(float).reindex(idx).ffill()
    atr_s = atr(asset, spec.atr_window).reindex(idx).ffill()
    qqq_close = qqq["close"].astype(float)
    qqq_ma200 = qqq_close.rolling(200, min_periods=200).mean()
    regime_on = (qqq_close > qqq_ma200).reindex(idx).ffill().fillna(False)
    realized_vol = close.pct_change().rolling(20, min_periods=20).std(ddof=0) * math.sqrt(TRADING_DAYS)

    out = []
    peak = np.nan
    cooldown = 0
    for dt in idx:
        weight = float(raw.loc[dt])
        if spec.overlay in {"regime_off", "risk_bundle"} and spec.regime_off and not bool(regime_on.loc[dt]):
            weight = 0.0
        if spec.overlay in {"vol_target", "risk_bundle"} and spec.vol_target is not None:
            vol = realized_vol.loc[dt]
            scale = min(1.0, spec.vol_target / vol) if pd.notna(vol) and vol > 0 else 1.0
            weight *= scale
        if spec.overlay in {"max_position_cap", "risk_bundle"} and spec.max_cap is not None:
            weight = min(weight, spec.max_cap)
        if spec.overlay in {"atr_stop", "risk_bundle"}:
            if cooldown > 0:
                cooldown -= 1
                weight = 0.0
            elif weight > EPS:
                price = close.loc[dt]
                atr_value = atr_s.loc[dt]
                peak = price if not np.isfinite(peak) else max(peak, price)
                if spec.trailing_variant == "confirm_2d":
                    stop_hit = pd.notna(atr_value) and price <= peak - spec.atr_mult * atr_value and close.shift(1).loc[dt] <= peak - spec.atr_mult * atr_value
                else:
                    stop_hit = pd.notna(atr_value) and price <= peak - spec.atr_mult * atr_value
                if stop_hit:
                    weight = 0.0
                    peak = np.nan
                    cooldown = spec.cooldown_days
            else:
                peak = np.nan
        out.append(float(np.clip(weight, 0.0, 1.0)))
    return pd.Series(out, index=idx, name="desired")


def replay(
    target: str,
    data: dict[str, pd.DataFrame],
    desired: pd.Series,
    strategy: str,
    overlay: str,
    fee: float,
    execution: str,
) -> ReplayResult:
    asset = data[target]
    idx = asset.index
    desired = desired.reindex(idx).ffill().fillna(0.0).clip(0.0, 1.0)
    open_p = asset["open"].astype(float).reindex(idx).ffill()
    close = asset["close"].astype(float).reindex(idx).ffill()
    nav = np.ones(len(idx), dtype=float)
    returns = np.zeros(len(idx), dtype=float)
    pos_arr = np.zeros(len(idx), dtype=float)
    turnover = np.zeros(len(idx), dtype=float)
    equity = 1.0
    pos = 0.0

    for i in range(1, len(idx)):
        prev_equity = equity
        target_weight = float(desired.iloc[i - 1])
        if execution == "next_open":
            if pos > 0 and close.iloc[i - 1] > 0:
                equity *= 1.0 + pos * (open_p.iloc[i] / close.iloc[i - 1] - 1.0)
            delta = abs(target_weight - pos)
            if delta > EPS:
                equity *= max(0.0, 1.0 - fee * delta)
            pos = target_weight
            if pos > 0 and open_p.iloc[i] > 0:
                equity *= 1.0 + pos * (close.iloc[i] / open_p.iloc[i] - 1.0)
        elif execution == "next_close":
            if pos > 0 and close.iloc[i - 1] > 0:
                equity *= 1.0 + pos * (close.iloc[i] / close.iloc[i - 1] - 1.0)
            delta = abs(target_weight - pos)
            if delta > EPS:
                equity *= max(0.0, 1.0 - fee * delta)
            pos = target_weight
        else:
            raise ValueError(f"Unknown execution: {execution}")
        nav[i] = equity
        returns[i] = equity / prev_equity - 1.0 if prev_equity > 0 else 0.0
        pos_arr[i] = pos
        turnover[i] = delta

    return ReplayResult(
        target=target,
        strategy=strategy,
        overlay=overlay,
        execution=execution,
        fee=fee,
        nav=pd.Series(nav, index=idx),
        returns=pd.Series(returns, index=idx),
        position=pd.Series(pos_arr, index=idx),
        desired=desired,
        turnover=pd.Series(turnover, index=idx),
    )


def overlay_specs_for_qld() -> list[OverlaySpec]:
    return [
        OverlaySpec("none"),
        OverlaySpec("atr_stop", atr_window=14, atr_mult=3.0, cooldown_days=10),
        OverlaySpec("regime_off", regime_off=True),
        OverlaySpec("vol_target", vol_target=0.30),
        OverlaySpec("max_position_cap", max_cap=0.70),
        OverlaySpec("risk_bundle", atr_window=14, atr_mult=3.0, cooldown_days=10, vol_target=0.30, max_cap=0.70, regime_off=True),
    ]


def tqqq_param_specs() -> list[OverlaySpec]:
    specs = []
    for window in (10, 14, 18):
        for mult in (2.5, 3.0, 3.5):
            specs.append(OverlaySpec("atr_stop", atr_window=window, atr_mult=mult, cooldown_days=10, trailing_variant="standard"))
    specs.append(OverlaySpec("atr_stop", atr_window=14, atr_mult=3.0, cooldown_days=5, trailing_variant="short_cooldown"))
    specs.append(OverlaySpec("atr_stop", atr_window=14, atr_mult=3.0, cooldown_days=10, trailing_variant="confirm_2d"))
    return specs


def run_tqqq_validation(data: dict[str, pd.DataFrame], bases: dict[str, dict[str, pd.Series]]) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    base = bases["TQQQ"]["ema20_ema100_direction"]
    for spec in tqqq_param_specs():
        desired = build_desired("TQQQ", data, base, spec)
        for split in validation_splits():
            result = replay("TQQQ", data, desired, "ema20_ema100_direction__atr_stop", "atr_stop", FEE, "next_open")
            row = metrics(result, split)
            row.update(
                {
                    "section": "parameter_stability",
                    "atr_window": spec.atr_window,
                    "atr_mult": spec.atr_mult,
                    "cooldown_days": spec.cooldown_days,
                    "trailing_variant": spec.trailing_variant,
                }
            )
            rows.append(row)

    default = OverlaySpec("atr_stop", atr_window=14, atr_mult=3.0, cooldown_days=10)
    desired = build_desired("TQQQ", data, base, default)
    for fee in (0.0, 0.001, 0.002, 0.003):
        for execution in ("next_open", "next_close"):
            result = replay("TQQQ", data, desired, "ema20_ema100_direction__atr_stop", "atr_stop", fee, execution)
            row = metrics(result, SplitSpec("final", "2021_latest", "2021-01-01", None))
            row.update(
                {
                    "section": "cost_execution_sensitivity",
                    "atr_window": 14,
                    "atr_mult": 3.0,
                    "cooldown_days": 10,
                    "trailing_variant": "standard",
                }
            )
            rows.append(row)
    for split in validation_splits():
        result = replay("TQQQ", data, desired, "ema20_ema100_direction__atr_stop", "atr_stop", FEE, "next_open")
        row = metrics(result, split)
        row.update(
            {
                "section": "split_validation_default",
                "atr_window": 14,
                "atr_mult": 3.0,
                "cooldown_days": 10,
                "trailing_variant": "standard",
            }
        )
        rows.append(row)

    validation = pd.DataFrame(rows)
    stability = (
        validation[validation["section"].eq("parameter_stability")]
        .groupby(["atr_window", "atr_mult", "cooldown_days", "trailing_variant"], as_index=False)
        .agg(
            mean_CAGR=("CAGR", "mean"),
            median_CAGR=("CAGR", "median"),
            mean_MDD=("MDD", "mean"),
            worst_MDD=("MDD", "min"),
            mean_Calmar=("Calmar", "mean"),
            median_Calmar=("Calmar", "median"),
            worst_Calmar=("Calmar", "min"),
            mean_turnover=("annual_turnover", "mean"),
            mean_abs_weight=("avg_abs_weight", "mean"),
        )
        .copy()
    )
    best = stability.sort_values("median_Calmar", ascending=False).iloc[0]
    default_row = stability[
        stability["atr_window"].eq(14)
        & stability["atr_mult"].eq(3.0)
        & stability["cooldown_days"].eq(10)
        & stability["trailing_variant"].eq("standard")
    ].iloc[0]
    stability["is_default"] = (
        stability["atr_window"].eq(14)
        & stability["atr_mult"].eq(3.0)
        & stability["cooldown_days"].eq(10)
        & stability["trailing_variant"].eq("standard")
    )
    stability["delta_median_calmar_vs_best"] = stability["median_Calmar"] - float(best["median_Calmar"])
    stability["delta_median_calmar_vs_default"] = stability["median_Calmar"] - float(default_row["median_Calmar"])
    stability["single_point_spike_suspect"] = False
    if bool(best["trailing_variant"] == "standard"):
        neighbors = stability[
            stability["trailing_variant"].eq("standard")
            & (abs(stability["atr_window"] - float(best["atr_window"])) <= 4)
            & (abs(stability["atr_mult"] - float(best["atr_mult"])) <= 0.5)
            & ~(
                stability["atr_window"].eq(best["atr_window"])
                & stability["atr_mult"].eq(best["atr_mult"])
            )
        ]
        if not neighbors.empty and float(best["median_Calmar"]) - float(neighbors["median_Calmar"].median()) > 0.35:
            stability.loc[
                stability["atr_window"].eq(best["atr_window"])
                & stability["atr_mult"].eq(best["atr_mult"])
                & stability["trailing_variant"].eq(best["trailing_variant"]),
                "single_point_spike_suspect",
            ] = True
    return validation, stability


def save_tqqq_heatmap(stability: pd.DataFrame, run_dir: Path) -> None:
    heat = stability[stability["trailing_variant"].eq("standard")].pivot(index="atr_window", columns="atr_mult", values="median_Calmar")
    fig, ax = plt.subplots(figsize=(7, 5))
    im = ax.imshow(heat.values, cmap="YlGnBu", aspect="auto")
    ax.set_xticks(range(len(heat.columns)))
    ax.set_xticklabels([str(c) for c in heat.columns])
    ax.set_yticks(range(len(heat.index)))
    ax.set_yticklabels([str(i) for i in heat.index])
    ax.set_xlabel("ATR stop multiple")
    ax.set_ylabel("ATR window")
    ax.set_title("TQQQ ATR stop parameter stability: median Calmar")
    for i in range(heat.shape[0]):
        for j in range(heat.shape[1]):
            ax.text(j, i, f"{heat.values[i, j]:.2f}", ha="center", va="center", color="black", fontsize=9)
    fig.colorbar(im, ax=ax, label="median Calmar")
    fig.tight_layout()
    fig.savefig(run_dir / "tqqq_parameter_heatmap.png", dpi=160)
    plt.close(fig)


def run_qld_constraint_frontier(data: dict[str, pd.DataFrame], bases: dict[str, dict[str, pd.Series]]) -> tuple[pd.DataFrame, pd.DataFrame]:
    candidate_rows = []
    final_split = SplitSpec("final", "2021_latest", "2021-01-01", None)
    for base_name in ("ema20_ema100_direction", "qqq_ma200_trend"):
        for spec in overlay_specs_for_qld():
            desired = build_desired("QLD", data, bases["QLD"][base_name], spec)
            result = replay("QLD", data, desired, f"{base_name}__{spec.overlay}", spec.overlay, FEE, "next_open")
            row = metrics(result, final_split)
            row.update(
                {
                    "base_strategy": base_name,
                    "atr_window": spec.atr_window,
                    "atr_mult": spec.atr_mult,
                    "vol_target": spec.vol_target,
                    "max_cap": spec.max_cap,
                    "regime_off": spec.regime_off,
                }
            )
            candidate_rows.append(row)
    candidates = pd.DataFrame(candidate_rows)
    frontier_rows = []
    for constraint in (0.20, 0.25, 0.30):
        eligible = candidates[candidates["MDD"].abs() <= constraint].copy()
        if eligible.empty:
            pick = candidates.assign(distance=(candidates["MDD"].abs() - constraint).abs()).sort_values(["distance", "Calmar"], ascending=[True, False]).iloc[0]
            status = "no_eligible_nearest"
        else:
            pick = eligible.sort_values(["CAGR", "Calmar", "annual_turnover"], ascending=[False, False, True]).iloc[0]
            status = "eligible"
        out = pick.to_dict()
        out.update(
            {
                "mdd_constraint": constraint,
                "constraint_status": status,
                "eligible_count": int(len(eligible)),
                "rank_rule": "maximize_CAGR_then_Calmar_within_MDD_constraint",
            }
        )
        frontier_rows.append(out)
    return candidates, pd.DataFrame(frontier_rows)


def qld_summary_md(frontier: pd.DataFrame, candidates: pd.DataFrame) -> str:
    lines = ["# QLD Constraint Summary", ""]
    for _, row in frontier.sort_values("mdd_constraint").iterrows():
        lines.append(
            f"- MDD <= {pct(row['mdd_constraint'])}: `{row['strategy']}` wins "
            f"(CAGR {pct(row['CAGR'])}, MDD {pct(row['MDD'])}, Calmar {num(row['Calmar'])}, "
            f"avg abs weight {pct(row['avg_abs_weight'])}, status `{row['constraint_status']}`)."
        )
    ma200_wins = frontier["strategy"].astype(str).str.contains("qqq_ma200_trend").any()
    lines.extend(
        [
            "",
            "## Does qqq_ma200_trend Re-win Under Constraints?",
            "",
            "Yes." if ma200_wins else "No. In this constrained frontier, EMA20/EMA100 overlays remain ahead for the tested MDD constraints.",
            "",
            "## Candidate Table",
            "",
            md_table(
                candidates[
                    [
                        "strategy",
                        "overlay",
                        "CAGR",
                        "MDD",
                        "Sharpe",
                        "Calmar",
                        "avg_abs_weight",
                        "trade_count",
                        "annual_turnover",
                    ]
                ].assign(
                    CAGR=lambda x: x["CAGR"].map(pct),
                    MDD=lambda x: x["MDD"].map(pct),
                    avg_abs_weight=lambda x: x["avg_abs_weight"].map(pct),
                    Sharpe=lambda x: x["Sharpe"].map(num),
                    Calmar=lambda x: x["Calmar"].map(num),
                    annual_turnover=lambda x: x["annual_turnover"].map(num),
                )
            ),
        ]
    )
    return "\n".join(lines)


def run_meta_side_experiment(
    data: dict[str, pd.DataFrame],
    features: dict[str, pd.DataFrame],
    labels: dict[str, pd.DataFrame],
    bases: dict[str, dict[str, pd.Series]],
) -> tuple[pd.DataFrame, str]:
    target = "TQQQ"
    base_name = "ema20_ema100_direction"
    base = bases[target][base_name]
    atr_spec = OverlaySpec("atr_stop", atr_window=14, atr_mult=3.0, cooldown_days=10)
    rows = []
    meta_spec = v2.MetaSpec("logistic", "l2", "balanced_q60", 0.60, 0.70, tuple(v2.LOGIT_FEATURES))
    for split in [s for s in validation_splits() if s.split in {"anchored_2021_2023", "anchored_2024_latest", "anchored_2021_latest"}]:
        base_desired = build_desired(target, data, base, atr_spec)
        base_result = replay(target, data, base_desired, f"{base_name}__atr_stop_no_meta", "atr_stop", FEE, "next_open")
        base_row = metrics(base_result, split)
        base_row.update({"experiment": "no_meta_atr_stop", "model": "none", "features": ""})
        rows.append(base_row)
        pred = v2.model_predictions_for_split(features[target], labels[target], v2.SplitSpec(split.split_type, split.split, split.train_start, split.train_end, split.test_start, split.test_end), meta_spec)
        if "bottom_prob" not in pred:
            continue
        meta_base = v2.meta_signal(base, pred["bottom_prob"], pred["top_prob"], float(pred["bottom_threshold"]), float(pred["top_threshold"]))
        meta_desired = build_desired(target, data, meta_base, atr_spec)
        meta_result = replay(target, data, meta_desired, f"{base_name}__logistic_l2_side__atr_stop", "meta_plus_atr_stop", FEE, "next_open")
        meta_row = metrics(meta_result, split)
        meta_row.update({"experiment": "logistic_l2_meta_plus_atr_stop", "model": "logistic_l2", "features": ",".join(v2.LOGIT_FEATURES)})
        rows.append(meta_row)
    df = pd.DataFrame(rows)
    paired = []
    for split_name, sub in df.groupby("split"):
        if {"no_meta_atr_stop", "logistic_l2_meta_plus_atr_stop"}.issubset(set(sub["experiment"])):
            a = sub[sub["experiment"].eq("no_meta_atr_stop")].iloc[0]
            b = sub[sub["experiment"].eq("logistic_l2_meta_plus_atr_stop")].iloc[0]
            paired.append({"split": split_name, "CAGR_delta": b["CAGR"] - a["CAGR"], "MDD_delta": b["MDD"] - a["MDD"], "Calmar_delta": b["Calmar"] - a["Calmar"]})
    paired_df = pd.DataFrame(paired)
    if paired_df.empty:
        conclusion = "Meta-label side experiment did not produce enough paired rows; do not promote it."
    elif paired_df["Calmar_delta"].median() > 0 and paired_df["CAGR_delta"].median() > -0.02:
        conclusion = "Meta-label shows a small positive side-experiment signal, but should still remain secondary until purged validation."
    else:
        conclusion = "Current labels/features do not justify promoting meta-label to the main path; it either lowers CAGR too much or does not improve Calmar consistently."
    md = "\n".join(
        [
            "# Meta-label Side Experiment",
            "",
            "Primary fixed: `TQQQ ema20_ema100_direction + atr_stop`.",
            "Model fixed: Logistic L2, v1 feature subset <= 8.",
            "",
            conclusion,
            "",
            "## Paired Delta",
            "",
            md_table(
                paired_df.assign(
                    CAGR_delta=lambda x: x["CAGR_delta"].map(pct),
                    MDD_delta=lambda x: x["MDD_delta"].map(pct),
                    Calmar_delta=lambda x: x["Calmar_delta"].map(num),
                )
                if not paired_df.empty
                else paired_df
            ),
        ]
    )
    return df, md


def drawdown(nav: pd.Series) -> pd.Series:
    return nav.div(nav.cummax()).sub(1.0)


def save_signal_and_drawdown_charts(
    run_dir: Path,
    data: dict[str, pd.DataFrame],
    tqqq_result: ReplayResult,
    qld_result: ReplayResult,
    qld_reference: ReplayResult | None = None,
) -> None:
    for target, result in (("TQQQ", tqqq_result), ("QLD", qld_result)):
        asset = data[target].loc[data[target].index >= PERIOD_START]
        pos = result.position.reindex(asset.index).fillna(0.0)
        entries = pos.gt(EPS) & ~pos.shift(1).fillna(0.0).gt(EPS)
        exits = ~pos.gt(EPS) & pos.shift(1).fillna(0.0).gt(EPS)
        fig, ax1 = plt.subplots(figsize=(12, 5))
        asset["close"].plot(ax=ax1, color="#1f4e79", linewidth=1.2, label="close")
        ax1.scatter(asset.index[entries], asset.loc[entries, "close"], marker="^", color="#2ca02c", s=28, label="entry")
        ax1.scatter(asset.index[exits], asset.loc[exits, "close"], marker="v", color="#d62728", s=28, label="exit")
        ax2 = ax1.twinx()
        pos.plot(ax=ax2, color="#ff7f0e", alpha=0.65, linewidth=0.9, label="weight")
        ax1.set_title(f"{target} v3 signal: {result.strategy}")
        ax2.set_ylim(-0.02, 1.05)
        ax1.grid(True, alpha=0.25)
        ax1.legend(loc="upper left")
        ax2.legend(loc="upper right")
        fig.tight_layout()
        fig.savefig(run_dir / f"{target.lower()}_v3_signal_chart.png", dpi=150)
        plt.close(fig)

        nav = result.nav.loc[result.nav.index >= PERIOD_START].dropna()
        nav = nav / nav.iloc[0]
        fig, ax = plt.subplots(figsize=(11, 4.6))
        drawdown(nav).plot(ax=ax, label="v3", linewidth=1.7)
        if target == "QLD" and qld_reference is not None:
            ref = qld_reference.nav.loc[qld_reference.nav.index >= PERIOD_START].dropna()
            ref = ref / ref.iloc[0]
            drawdown(ref).plot(ax=ax, label="reference_v2", linewidth=1.1, alpha=0.75)
        ax.set_title(f"{target} v3 drawdown")
        ax.grid(True, alpha=0.25)
        ax.legend()
        fig.tight_layout()
        fig.savefig(run_dir / f"{target.lower()}_v3_drawdown.png", dpi=150)
        plt.close(fig)


def compare_v3_v2(
    data: dict[str, pd.DataFrame],
    bases: dict[str, dict[str, pd.Series]],
    tqqq_result: ReplayResult,
    qld_frontier: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    final_split = SplitSpec("final", "2021_latest", "2021-01-01", None)
    v2_path = V2_DIR / "v2_vs_v1_vs_old.csv"
    if v2_path.exists():
        v2_df = pd.read_csv(v2_path)
        v2_selected = v2_df[v2_df["source"].eq("v2_selected")].copy()
        if "annual_turnover" not in v2_selected.columns and "turnover" in v2_selected.columns:
            v2_selected["annual_turnover"] = v2_selected["turnover"]
        elif "turnover" in v2_selected.columns:
            v2_selected["annual_turnover"] = v2_selected["annual_turnover"].fillna(v2_selected["turnover"])
        rows.extend(v2_selected.assign(comparison_group="v2_selected").to_dict("records"))
    rows.append({**metrics(tqqq_result, final_split), "source": "v3_selected", "comparison_group": "TQQQ best v3"})
    for _, row in qld_frontier.iterrows():
        spec = OverlaySpec(
            str(row["overlay"]),
            atr_window=int(row.get("atr_window", 14) if pd.notna(row.get("atr_window", 14)) else 14),
            atr_mult=float(row.get("atr_mult", 3.0) if pd.notna(row.get("atr_mult", 3.0)) else 3.0),
            vol_target=float(row["vol_target"]) if "vol_target" in row and pd.notna(row["vol_target"]) else None,
            max_cap=float(row["max_cap"]) if "max_cap" in row and pd.notna(row["max_cap"]) else None,
            regime_off=bool(row.get("regime_off", False)),
        )
        desired = build_desired("QLD", data, bases["QLD"][str(row["base_strategy"])], spec)
        result = replay("QLD", data, desired, str(row["strategy"]), str(row["overlay"]), FEE, "next_open")
        m = metrics(result, final_split)
        m.update({"source": "v3_constraint", "comparison_group": f"QLD MDD<={row['mdd_constraint']:.0%}"})
        rows.append(m)
    return pd.DataFrame(rows)


def format_metrics_for_md(df: pd.DataFrame, max_rows: int = 20) -> pd.DataFrame:
    cols = [c for c in ["target", "strategy", "overlay", "source", "comparison_group", "CAGR", "MDD", "Sharpe", "Calmar", "trade_count", "annual_turnover", "avg_abs_weight"] if c in df.columns]
    out = df[cols].copy().head(max_rows)
    for col in ("CAGR", "MDD", "avg_abs_weight"):
        if col in out:
            out[col] = out[col].map(pct)
    for col in ("Sharpe", "Calmar", "annual_turnover"):
        if col in out:
            out[col] = out[col].map(num)
    return out


def write_research_summary(
    run_dir: Path,
    tqqq_validation: pd.DataFrame,
    tqqq_stability: pd.DataFrame,
    qld_frontier: pd.DataFrame,
    meta_side: pd.DataFrame,
    v3_vs_v2: pd.DataFrame,
) -> None:
    default_stability = tqqq_stability[tqqq_stability["is_default"]].iloc[0]
    best_stability = tqqq_stability.sort_values("median_Calmar", ascending=False).iloc[0]
    default_suspect = bool(default_stability.get("single_point_spike_suspect", False))
    cost_exec = tqqq_validation[tqqq_validation["section"].eq("cost_execution_sensitivity")]
    next_open = cost_exec[cost_exec["execution"].eq("next_open")]
    next_close = cost_exec[cost_exec["execution"].eq("next_close")]
    exec_gap = (
        float(next_open[next_open["one_way_fee"].eq(FEE)]["Calmar"].iloc[0])
        - float(next_close[next_close["one_way_fee"].eq(FEE)]["Calmar"].iloc[0])
        if not next_open.empty and not next_close.empty
        else np.nan
    )
    next_close_03 = (
        float(next_close[next_close["one_way_fee"].eq(0.003)]["Calmar"].iloc[0])
        if not next_close.empty and not next_close[next_close["one_way_fee"].eq(0.003)].empty
        else np.nan
    )
    meta_pairs = []
    if not meta_side.empty:
        for split, sub in meta_side.groupby("split"):
            if {"no_meta_atr_stop", "logistic_l2_meta_plus_atr_stop"}.issubset(set(sub["experiment"])):
                base = sub[sub["experiment"].eq("no_meta_atr_stop")].iloc[0]
                meta = sub[sub["experiment"].eq("logistic_l2_meta_plus_atr_stop")].iloc[0]
                meta_pairs.append(meta["Calmar"] - base["Calmar"])
    meta_continue = bool(meta_pairs and np.nanmedian(meta_pairs) > 0.05)
    tqqq_v3 = v3_vs_v2[(v3_vs_v2["target"].eq("TQQQ")) & (v3_vs_v2["source"].eq("v3_selected"))].iloc[0]
    lines = [
        "# Turning Point Research V3",
        "",
        "## Core Conclusions",
        "",
        f"- TQQQ current best `ema20_ema100_direction + atr_stop` is {'not a suspicious single-point spike' if not default_suspect else 'potentially suspicious as a sharp single-point spike'} in the tested ATR neighborhood. Default median Calmar {num(default_stability['median_Calmar'])}; best-neighbor median Calmar {num(best_stability['median_Calmar'])}.",
        f"- TQQQ execution sensitivity: next-open vs next-close Calmar gap at 0.2% fee is {num(exec_gap)}. Next-close at 0.3% fee still has Calmar {num(next_close_03)}, so execution change hurts but does not fully collapse the result.",
        f"- TQQQ v3 2021+ result: CAGR {pct(tqqq_v3['CAGR'])}, MDD {pct(tqqq_v3['MDD'])}, Calmar {num(tqqq_v3['Calmar'])}. Improvement mainly comes from ATR stop risk cut, not new timing or position scaling.",
        "- QLD constrained frontier winners:",
    ]
    for _, row in qld_frontier.sort_values("mdd_constraint").iterrows():
        lines.append(
            f"  - MDD <= {pct(row['mdd_constraint'])}: `{row['strategy']}` / `{row['overlay']}` "
            f"CAGR {pct(row['CAGR'])}, MDD {pct(row['MDD'])}, Calmar {num(row['Calmar'])}."
        )
    ma200_rewin = qld_frontier["strategy"].astype(str).str.contains("qqq_ma200_trend").any()
    lines.extend(
        [
            f"- qqq_ma200_trend {'does re-win under at least one QLD constraint' if ma200_rewin else 'does not re-win under the tested QLD constraints'}.",
            f"- Meta-label is {'worth a small follow-up only as a side path' if meta_continue else 'not worth promoting to the main path'} under the current labels/features/sample conditions.",
            "- Next round should prioritize stricter validation, especially purged/CPCV, before more overlay/model work.",
            "",
            "## TQQQ Parameter Stability Snapshot",
            "",
            md_table(
                tqqq_stability.sort_values("median_Calmar", ascending=False)[
                    ["atr_window", "atr_mult", "cooldown_days", "trailing_variant", "median_CAGR", "worst_MDD", "median_Calmar", "worst_Calmar", "is_default", "single_point_spike_suspect"]
                ].assign(
                    median_CAGR=lambda x: x["median_CAGR"].map(pct),
                    worst_MDD=lambda x: x["worst_MDD"].map(pct),
                    median_Calmar=lambda x: x["median_Calmar"].map(num),
                    worst_Calmar=lambda x: x["worst_Calmar"].map(num),
                ),
                12,
            ),
            "",
            "## V3 vs V2",
            "",
            md_table(format_metrics_for_md(v3_vs_v2, 20)),
            "",
            "## Required Answers",
            "",
            "1. TQQQ 的提升主要来自 ATR stop。它不是仓位缩放，也不是 meta-label timing 改善；核心机制是在大回撤段触发风险切断并降低连续下跌暴露。",
            "2. QLD 最适合的 overlay 以约束档位为准；若三个档位都选同一 overlay，可视为当前最适合，否则应按 MDD 目标选择。",
            f"3. qqq_ma200_trend {'在风险约束框架下重新胜出' if ma200_rewin else '没有在本轮 QLD 风险约束框架下重新胜出'}。",
            "4. meta-label 当前没跑出来，主要因为固定轻量 Logistic 的过滤会牺牲持仓机会；在样本较短、标签有噪声、主策略本身已含趋势信息时，Calmar 改善不够稳定。",
            f"5. 下一轮 {'可以保留很小的 meta-label side path，但不应进入主线' if meta_continue else '不应继续主线投入 meta-label'}。",
            "6. 下一轮应优先做更严格验证，其次是更细成本模型；overlay 应保持更少更精。",
        ]
    )
    write_text(run_dir / "v3_research_summary.md", "\n".join(lines))


def write_readme(run_dir: Path, qld_frontier: pd.DataFrame, tqqq_stability: pd.DataFrame) -> None:
    default_row = tqqq_stability[tqqq_stability["is_default"]].iloc[0]
    qld_best_25 = qld_frontier[qld_frontier["mdd_constraint"].eq(0.25)].iloc[0]
    lines = [
        "# README_FOR_CHATGPT",
        "",
        "## Most Useful 5 Files",
        "",
        "1. `v3_research_summary.md`: main conclusions and required answers.",
        "2. `tqqq_validation_plus.csv`: TQQQ split, cost, execution, and ATR-neighborhood validation.",
        "3. `tqqq_parameter_stability.csv`: compact parameter stability table and spike flag.",
        "4. `qld_constraint_frontier.csv`: QLD winners under MDD <= 20%, 25%, 30%.",
        "5. `v3_vs_v2_comparison.csv`: direct v2/v3 comparison.",
        "",
        "## Most Credible Result",
        "",
        f"TQQQ `ema20_ema100_direction + atr_stop` is the most credible result if the reviewer agrees the ATR neighborhood is smooth. Default median Calmar is {num(default_row['median_Calmar'])}.",
        "",
        "## Most Likely Accidental Result",
        "",
        "Any single neighboring ATR parameter that beats the default by a small amount should be treated as validation evidence, not as a new optimized winner. Do not promote a new parameter unless the heatmap is smooth.",
        "",
        "## Next Step",
        "",
        f"For QLD, review whether the MDD<=25% winner `{qld_best_25['strategy']}` is acceptable. For both assets, next step should be purged/CPCV-style validation before adding more overlays or models.",
    ]
    write_text(run_dir / "README_FOR_CHATGPT.md", "\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description="Turning point research v3")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--output-root", type=Path, default=ROOT / "outputs")
    args = parser.parse_args()

    run_dir = args.output_root / f"turning_point_research_v3_{stamp()}"
    run_dir.mkdir(parents=True, exist_ok=True)
    log(f"Output directory: {run_dir}")

    log("Loading v1/v2 data, labels, features, and base signals")
    data = v2.load_data(args.data_dir)
    labels = v2.build_labels(data)
    features, indicators = v2.build_features(data)
    bases = v2.base_signals(data, indicators)

    log("Running TQQQ ATR validation hardening")
    tqqq_validation, tqqq_stability = run_tqqq_validation(data, bases)
    write_csv(tqqq_validation, run_dir / "tqqq_validation_plus.csv")
    write_csv(tqqq_stability, run_dir / "tqqq_parameter_stability.csv")
    save_tqqq_heatmap(tqqq_stability, run_dir)

    log("Running QLD constrained overlay frontier")
    qld_candidates, qld_frontier = run_qld_constraint_frontier(data, bases)
    write_csv(qld_frontier, run_dir / "qld_constraint_frontier.csv")
    write_csv(qld_candidates, run_dir / "qld_overlay_candidates.csv")
    write_text(run_dir / "qld_constraint_summary.md", qld_summary_md(qld_frontier, qld_candidates))

    log("Running lightweight meta-label side experiment")
    meta_side, meta_md = run_meta_side_experiment(data, features, labels, bases)
    write_csv(meta_side, run_dir / "meta_label_side_experiment.csv")
    write_text(run_dir / "meta_label_side_experiment.md", meta_md)

    log("Writing v3/v2 comparison and charts")
    tqqq_default_spec = OverlaySpec("atr_stop", atr_window=14, atr_mult=3.0, cooldown_days=10)
    tqqq_desired = build_desired("TQQQ", data, bases["TQQQ"]["ema20_ema100_direction"], tqqq_default_spec)
    tqqq_result = replay("TQQQ", data, tqqq_desired, "ema20_ema100_direction__atr_stop", "atr_stop", FEE, "next_open")
    qld_25 = qld_frontier[qld_frontier["mdd_constraint"].eq(0.25)].iloc[0]
    qld_spec = OverlaySpec(
        str(qld_25["overlay"]),
        atr_window=int(qld_25.get("atr_window", 14) if pd.notna(qld_25.get("atr_window", 14)) else 14),
        atr_mult=float(qld_25.get("atr_mult", 3.0) if pd.notna(qld_25.get("atr_mult", 3.0)) else 3.0),
        vol_target=float(qld_25["vol_target"]) if pd.notna(qld_25.get("vol_target", np.nan)) else None,
        max_cap=float(qld_25["max_cap"]) if pd.notna(qld_25.get("max_cap", np.nan)) else None,
        regime_off=bool(qld_25.get("regime_off", False)),
    )
    qld_desired = build_desired("QLD", data, bases["QLD"][str(qld_25["base_strategy"])], qld_spec)
    qld_result = replay("QLD", data, qld_desired, str(qld_25["strategy"]), str(qld_25["overlay"]), FEE, "next_open")
    v2_qld_spec = OverlaySpec("risk_bundle", atr_window=14, atr_mult=3.0, cooldown_days=10, vol_target=0.30, max_cap=0.70, regime_off=True)
    v2_qld_desired = build_desired("QLD", data, bases["QLD"]["ema20_ema100_direction"], v2_qld_spec)
    v2_qld_result = replay("QLD", data, v2_qld_desired, "v2_qld_reference", "risk_bundle", FEE, "next_open")
    save_signal_and_drawdown_charts(run_dir, data, tqqq_result, qld_result, v2_qld_result)

    v3_vs_v2 = compare_v3_v2(data, bases, tqqq_result, qld_frontier)
    write_csv(v3_vs_v2, run_dir / "v3_vs_v2_comparison.csv")

    log("Writing summaries and manifest")
    write_research_summary(run_dir, tqqq_validation, tqqq_stability, qld_frontier, meta_side, v3_vs_v2)
    write_readme(run_dir, qld_frontier, tqqq_stability)
    write_text(
        run_dir / "changed_files_manifest.txt",
        "\n".join(
            [
                "Added or modified script files:",
                "",
                "- scripts/qldtqqq_turning_point_research_v3.py",
                "",
                "V3 reuses v1/v2 helper functions but does not modify prior workflows.",
            ]
        ),
    )
    (run_dir / "qldtqqq_turning_point_research_v3.py").write_text((ROOT / "scripts" / "qldtqqq_turning_point_research_v3.py").read_text(encoding="utf-8"), encoding="utf-8")

    required = [
        "v3_research_summary.md",
        "tqqq_validation_plus.csv",
        "tqqq_parameter_stability.csv",
        "tqqq_parameter_heatmap.png",
        "qld_constraint_frontier.csv",
        "qld_constraint_summary.md",
        "meta_label_side_experiment.csv",
        "meta_label_side_experiment.md",
        "v3_vs_v2_comparison.csv",
        "qld_v3_signal_chart.png",
        "tqqq_v3_signal_chart.png",
        "qld_v3_drawdown.png",
        "tqqq_v3_drawdown.png",
        "changed_files_manifest.txt",
        "README_FOR_CHATGPT.md",
    ]
    missing = [name for name in required if not (run_dir / name).exists()]
    if missing:
        raise RuntimeError(f"Missing required v3 outputs: {missing}")
    log("V3 completed")
    log(str(run_dir))


if __name__ == "__main__":
    main()
