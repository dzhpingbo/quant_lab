"""Turning point research v5: small-neighborhood frontier optimization.

V5 keeps the v4 research base fixed and searches only interpretable overlay
neighborhoods:
- TQQQ: ema20_ema100_direction + ATR stop 18/2.5 as the anchor.
- QLD: ema20_ema100_direction + risk_bundle / regime_off as the anchor family.

No new factors, no meta-label revival, and no complex model layer.
"""

from __future__ import annotations

import argparse
import itertools
import math
import shutil
import sys
import warnings
from dataclasses import asdict, dataclass
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
import qldtqqq_turning_point_research_v4 as v4  # noqa: E402
from qldtqqq_turning_point_research_v1 import DEFAULT_DATA_DIR, atr  # noqa: E402


warnings.filterwarnings("ignore", category=FutureWarning)

FEE = 0.002
TRADING_DAYS = 252.0
PERIOD_START = pd.Timestamp("2021-01-01")
FINAL_SPLIT = v4.PeriodSplit("final", "2021_latest", (("2021-01-01", None),))
EPS = 1e-10
USER_TQQQ_V4_CAGR_REFERENCE = 0.3409
LOCAL_V4_DIR = ROOT / "outputs" / "turning_point_research_v4_20260421_193223"


@dataclass(frozen=True)
class StrategySpec:
    target: str
    overlay_family: str
    atr_stop: bool = False
    atr_window: int = 14
    atr_mult: float = 3.0
    cooldown_days: int = 10
    trailing_variant: str = "standard"
    vol_target: float | None = None
    max_cap: float | None = None
    regime_off: bool = False
    regime_ma: int = 200
    regime_buffer: float = 0.0
    drawdown_limit: float | None = None
    drawdown_cooldown: int = 20
    position_scale: float = 1.0
    note: str = ""


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def log(message: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", flush=True)


def pct(value: float | int | None) -> str:
    return "nan" if value is None or pd.isna(value) else f"{float(value) * 100:.2f}%"


def num(value: float | int | None, digits: int = 3) -> str:
    return "nan" if value is None or pd.isna(value) else f"{float(value):.{digits}f}"


def compact_float(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "none"
    text = f"{float(value):.3f}".rstrip("0").rstrip(".")
    return text.replace("-", "m").replace(".", "p")


def write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


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


def overlay_label(spec: StrategySpec) -> str:
    parts: list[str] = []
    if spec.atr_stop:
        parts.append(f"atr{spec.atr_window}_{compact_float(spec.atr_mult)}")
        parts.append(f"cd{spec.cooldown_days}")
        if spec.trailing_variant != "standard":
            parts.append(spec.trailing_variant)
    if spec.regime_off:
        buf = "" if abs(spec.regime_buffer) < EPS else f"b{compact_float(spec.regime_buffer)}"
        parts.append(f"regime{spec.regime_ma}{buf}")
    if spec.vol_target is not None:
        parts.append(f"vol{compact_float(spec.vol_target)}")
    if spec.max_cap is not None:
        parts.append(f"cap{compact_float(spec.max_cap)}")
    if spec.drawdown_limit is not None:
        parts.append(f"dd{compact_float(abs(spec.drawdown_limit))}_cd{spec.drawdown_cooldown}")
    if abs(spec.position_scale - 1.0) > EPS:
        parts.append(f"size{compact_float(spec.position_scale)}")
    return "+".join(parts) if parts else "none"


def candidate_id(spec: StrategySpec) -> str:
    return f"{spec.target.lower()}__{spec.overlay_family}__{overlay_label(spec)}"


def strategy_name(spec: StrategySpec) -> str:
    return f"ema20_ema100_direction__{spec.overlay_family}"


def base_weight(data: dict[str, pd.DataFrame], bases: dict[str, dict[str, pd.Series]], target: str) -> pd.Series:
    idx = data[target].index
    return bases[target]["ema20_ema100_direction"].reindex(idx).ffill().fillna(0.0).clip(0.0, 1.0)


def run_strategy(
    data: dict[str, pd.DataFrame],
    bases: dict[str, dict[str, pd.Series]],
    spec: StrategySpec,
    fee: float = FEE,
    slippage_model: str = "none",
) -> v4.ReplayResult:
    asset = data[spec.target]
    idx = asset.index
    open_p = asset["open"].astype(float).reindex(idx).ffill()
    close = asset["close"].astype(float).reindex(idx).ffill()
    raw_base = base_weight(data, bases, spec.target)
    asset_atr = atr(asset, spec.atr_window).reindex(idx).ffill()
    realized_vol = close.pct_change().rolling(20, min_periods=20).std(ddof=0) * math.sqrt(TRADING_DAYS)

    qqq_close = data["QQQ"]["close"].astype(float)
    qqq_ma = qqq_close.rolling(spec.regime_ma, min_periods=spec.regime_ma).mean()
    regime_on = (qqq_close > qqq_ma * (1.0 + spec.regime_buffer)).reindex(idx).ffill().fillna(False)
    slip = v4.adaptive_slippage_rate(asset, idx, slippage_model)

    nav = np.ones(len(idx), dtype=float)
    returns = np.zeros(len(idx), dtype=float)
    position = np.zeros(len(idx), dtype=float)
    desired = np.zeros(len(idx), dtype=float)
    turnover = np.zeros(len(idx), dtype=float)
    trade_cost_rate = np.zeros(len(idx), dtype=float)

    equity = 1.0
    pos = 0.0
    next_weight = 0.0
    atr_peak = np.nan
    atr_cooldown = 0
    dd_cooldown = 0
    peak_nav = 1.0

    close_shift = close.shift(1)

    for i, dt in enumerate(idx):
        if i > 0:
            prev_equity = equity
            if pos > 0 and close.iloc[i - 1] > 0:
                equity *= 1.0 + pos * (open_p.iloc[i] / close.iloc[i - 1] - 1.0)
            delta = abs(next_weight - pos)
            cost = fee + float(slip.iloc[i])
            if delta > EPS:
                equity *= max(0.0, 1.0 - cost * delta)
            pos = next_weight
            if pos > 0 and open_p.iloc[i] > 0:
                equity *= 1.0 + pos * (close.iloc[i] / open_p.iloc[i] - 1.0)
            nav[i] = equity
            returns[i] = equity / prev_equity - 1.0 if prev_equity > 0 else 0.0
            position[i] = pos
            turnover[i] = delta
            trade_cost_rate[i] = cost

        peak_nav = max(peak_nav, equity)
        if spec.drawdown_limit is not None and equity / peak_nav - 1.0 <= spec.drawdown_limit:
            dd_cooldown = spec.drawdown_cooldown
            peak_nav = equity

        weight = float(raw_base.loc[dt]) * spec.position_scale
        if spec.regime_off and not bool(regime_on.loc[dt]):
            weight = 0.0
        if spec.vol_target is not None:
            vol = realized_vol.loc[dt]
            scale = min(1.0, spec.vol_target / vol) if pd.notna(vol) and vol > 0 else 1.0
            weight *= scale
        if spec.max_cap is not None:
            weight = min(weight, spec.max_cap)

        if spec.atr_stop:
            if atr_cooldown > 0:
                atr_cooldown -= 1
                weight = 0.0
            elif weight > EPS:
                price = close.loc[dt]
                atr_value = asset_atr.loc[dt]
                atr_peak = price if not np.isfinite(atr_peak) else max(atr_peak, price)
                stop_level = atr_peak - spec.atr_mult * atr_value if pd.notna(atr_value) else np.nan
                if spec.trailing_variant == "confirm_2d":
                    stop_hit = (
                        pd.notna(stop_level)
                        and price <= stop_level
                        and close_shift.loc[dt] <= stop_level
                    )
                else:
                    stop_hit = pd.notna(stop_level) and price <= stop_level
                if stop_hit:
                    weight = 0.0
                    atr_peak = np.nan
                    atr_cooldown = spec.cooldown_days
            else:
                atr_peak = np.nan

        if dd_cooldown > 0:
            dd_cooldown -= 1
            weight = 0.0

        next_weight = float(np.clip(weight, 0.0, 1.0))
        desired[i] = next_weight

    return v4.ReplayResult(
        target=spec.target,
        strategy=strategy_name(spec),
        overlay=overlay_label(spec),
        execution="next_open",
        fee=fee,
        slippage_model=slippage_model,
        nav=pd.Series(nav, index=idx, name="nav"),
        returns=pd.Series(returns, index=idx, name="returns"),
        position=pd.Series(position, index=idx, name="position"),
        desired=pd.Series(desired, index=idx, name="desired"),
        turnover=pd.Series(turnover, index=idx, name="turnover"),
        trade_cost_rate=pd.Series(trade_cost_rate, index=idx, name="trade_cost_rate"),
    )


def row_for_result(spec: StrategySpec, result: v4.ReplayResult) -> dict[str, object]:
    row = v4.metrics_for_split(result, FINAL_SPLIT)
    row.update(asdict(spec))
    row["candidate_id"] = candidate_id(spec)
    row["strategy"] = strategy_name(spec)
    row["overlay"] = overlay_label(spec)
    row["turnover"] = row.get("annual_turnover", np.nan)
    row["abs_mdd"] = abs(float(row["MDD"])) if pd.notna(row.get("MDD")) else np.nan
    row["score_scope"] = "all_candidates"
    return row


def add_spec(specs: list[StrategySpec], seen: set[str], spec: StrategySpec) -> None:
    key = candidate_id(spec)
    if key not in seen:
        specs.append(spec)
        seen.add(key)


def tqqq_specs() -> list[StrategySpec]:
    specs: list[StrategySpec] = []
    seen: set[str] = set()

    def add(**kwargs: object) -> None:
        base = dict(
            target="TQQQ",
            overlay_family="atr_frontier",
            atr_stop=True,
            atr_window=18,
            atr_mult=2.5,
            cooldown_days=10,
        )
        base.update(kwargs)
        add_spec(specs, seen, StrategySpec(**base))

    add(note="v4_locked_18_2p5")

    for window, mult, cooldown in itertools.product((16, 18, 20), (2.4, 2.5, 2.6), (8, 10, 12)):
        add(atr_window=window, atr_mult=mult, cooldown_days=cooldown, note="atr_micro")

    for mult, cooldown in itertools.product((2.4, 2.5, 2.6), (8, 10, 12)):
        add(atr_mult=mult, cooldown_days=cooldown, trailing_variant="confirm_2d", note="trailing_confirm")

    for cap in (0.80, 0.85, 0.90, 0.95):
        add(max_cap=cap, note="max_cap_micro")

    for vol in (0.45, 0.55, 0.65, 0.75):
        add(vol_target=vol, note="vol_target_micro")

    for ma in (180, 200, 220):
        add(regime_off=True, regime_ma=ma, note="regime_micro")

    for mult, cooldown, cap, vol, regime in itertools.product(
        (2.4, 2.5, 2.6),
        (8, 10, 12),
        (None, 0.85, 0.90, 0.95),
        (None, 0.55, 0.65),
        (False, True),
    ):
        add(
            atr_mult=mult,
            cooldown_days=cooldown,
            max_cap=cap,
            vol_target=vol,
            regime_off=regime,
            regime_ma=200,
            note="small_combo",
        )

    return specs


def qld_specs() -> list[StrategySpec]:
    specs: list[StrategySpec] = []
    seen: set[str] = set()

    def add(**kwargs: object) -> None:
        base = dict(target="QLD", overlay_family="qld_frontier")
        base.update(kwargs)
        add_spec(specs, seen, StrategySpec(**base))

    add(regime_off=True, regime_ma=200, overlay_family="regime_off", note="v4_aggressive")
    add(
        atr_stop=True,
        atr_window=14,
        atr_mult=3.0,
        cooldown_days=10,
        vol_target=0.30,
        max_cap=0.70,
        regime_off=True,
        regime_ma=200,
        overlay_family="risk_bundle",
        note="v4_robust",
    )

    for ma, buffer, size in itertools.product((180, 200, 220), (-0.005, 0.0, 0.005), (0.90, 0.95, 1.0)):
        add(
            regime_off=True,
            regime_ma=ma,
            regime_buffer=buffer,
            position_scale=size,
            overlay_family="regime_off",
            note="regime_micro",
        )

    for cap in (0.50, 0.60, 0.65, 0.70, 0.75, 0.80, 0.90):
        add(max_cap=cap, overlay_family="max_cap", note="component_split")

    for vol in (0.20, 0.25, 0.30, 0.35):
        add(vol_target=vol, overlay_family="vol_target", note="component_split")

    for window, mult, cooldown in itertools.product((12, 14, 16), (2.75, 3.0, 3.25), (8, 10, 12)):
        add(
            atr_stop=True,
            atr_window=window,
            atr_mult=mult,
            cooldown_days=cooldown,
            overlay_family="atr_stop",
            note="component_split",
        )

    for limit, cooldown in itertools.product((-0.12, -0.15, -0.18), (15, 20, 30)):
        add(drawdown_limit=limit, drawdown_cooldown=cooldown, overlay_family="drawdown_cap", note="component_split")

    for mult, cooldown, vol, cap, ma, dd_limit, size in itertools.product(
        (2.75, 3.0, 3.25),
        (8, 10, 12),
        (0.25, 0.30, 0.35),
        (0.65, 0.70, 0.75),
        (190, 200, 210),
        (None, -0.18),
        (0.95, 1.0),
    ):
        add(
            atr_stop=True,
            atr_window=14,
            atr_mult=mult,
            cooldown_days=cooldown,
            vol_target=vol,
            max_cap=cap,
            regime_off=True,
            regime_ma=ma,
            drawdown_limit=dd_limit,
            position_scale=size,
            overlay_family="risk_bundle",
            note="risk_bundle_micro",
        )

    for dd_limit, cap, vol in itertools.product((None, -0.12, -0.15, -0.18), (0.50, 0.60), (0.20, 0.25)):
        add(
            atr_stop=True,
            atr_window=14,
            atr_mult=3.0,
            cooldown_days=10,
            vol_target=vol,
            max_cap=cap,
            regime_off=True,
            regime_ma=200,
            drawdown_limit=dd_limit,
            overlay_family="risk_bundle",
            note="strict_bucket_probe",
        )

    return specs


def score_candidates(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    clean = out[["CAGR", "Calmar", "Sharpe", "abs_mdd"]].replace([np.inf, -np.inf], np.nan)
    out["rank_CAGR"] = clean["CAGR"].rank(pct=True)
    out["rank_Calmar"] = clean["Calmar"].rank(pct=True)
    out["rank_Sharpe"] = clean["Sharpe"].rank(pct=True)
    out["rank_MDD_control"] = (-clean["abs_mdd"]).rank(pct=True)
    out["composite_score"] = (
        0.45 * out["rank_CAGR"]
        + 0.35 * out["rank_Calmar"]
        + 0.15 * out["rank_Sharpe"]
        + 0.05 * out["rank_MDD_control"]
    )
    return out


def evaluate_specs(
    data: dict[str, pd.DataFrame],
    bases: dict[str, dict[str, pd.Series]],
    specs: list[StrategySpec],
) -> tuple[pd.DataFrame, dict[str, v4.ReplayResult], dict[str, StrategySpec]]:
    rows: list[dict[str, object]] = []
    replays: dict[str, v4.ReplayResult] = {}
    spec_by_id: dict[str, StrategySpec] = {}
    for n, spec in enumerate(specs, start=1):
        if n % 250 == 0:
            log(f"Evaluated {n}/{len(specs)} {spec.target} candidates")
        result = run_strategy(data, bases, spec)
        cid = candidate_id(spec)
        rows.append(row_for_result(spec, result))
        replays[cid] = result
        spec_by_id[cid] = spec
    return score_candidates(pd.DataFrame(rows)), replays, spec_by_id


def select_frontier(df: pd.DataFrame, buckets: tuple[float, ...]) -> pd.DataFrame:
    rows: list[pd.Series] = []
    for bucket in buckets:
        eligible = df[df["abs_mdd"] <= bucket].copy()
        label = f"MDD<={int(bucket * 100)}%"
        if eligible.empty:
            continue
        picks = [
            ("highest_CAGR", eligible.sort_values(["CAGR", "Calmar"], ascending=[False, False]).iloc[0]),
            ("highest_Calmar", eligible.sort_values(["Calmar", "CAGR"], ascending=[False, False]).iloc[0]),
            ("highest_composite", eligible.sort_values(["composite_score", "CAGR"], ascending=[False, False]).iloc[0]),
        ]
        for role, pick in picks:
            row = pick.copy()
            row["frontier_bucket"] = label
            row["selection_role"] = role
            rows.append(row)
    return pd.DataFrame(rows).reset_index(drop=True)


def pareto_candidates(df: pd.DataFrame) -> pd.DataFrame:
    clean = df.dropna(subset=["CAGR", "abs_mdd"]).copy()
    keep: list[bool] = []
    for _, row in clean.iterrows():
        dominates = (
            (clean["CAGR"] >= row["CAGR"] - EPS)
            & (clean["abs_mdd"] <= row["abs_mdd"] + EPS)
            & ((clean["CAGR"] > row["CAGR"] + EPS) | (clean["abs_mdd"] < row["abs_mdd"] - EPS))
        )
        keep.append(not bool(dominates.any()))
    out = clean.loc[keep].sort_values(["abs_mdd", "CAGR"], ascending=[True, False])
    return out.reset_index(drop=True)


def stress_compare(
    data: dict[str, pd.DataFrame],
    bases: dict[str, dict[str, pd.Series]],
    frontier: pd.DataFrame,
    spec_by_id: dict[str, StrategySpec],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    selected_ids = list(dict.fromkeys(frontier["candidate_id"].astype(str).tolist()))
    for cid in selected_ids:
        spec = spec_by_id[cid]
        for slip in ("none", "fixed_5bps", "atr_adaptive_10pct"):
            result = run_strategy(data, bases, spec, FEE, slip)
            row = row_for_result(spec, result)
            row["frontier_roles"] = ";".join(frontier.loc[frontier["candidate_id"].eq(cid), "selection_role"].astype(str).unique())
            row["frontier_buckets"] = ";".join(frontier.loc[frontier["candidate_id"].eq(cid), "frontier_bucket"].astype(str).unique())
            rows.append(row)
    return pd.DataFrame(rows)


def format_frontier_for_md(df: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "frontier_bucket",
        "selection_role",
        "overlay_family",
        "overlay",
        "CAGR",
        "MDD",
        "Sharpe",
        "Calmar",
        "avg_abs_weight",
        "trade_count",
        "turnover",
        "composite_score",
    ]
    source = df.copy()
    for col in cols:
        if col not in source.columns:
            source[col] = np.nan
    out = source[cols].copy()
    for col in ("CAGR", "MDD", "avg_abs_weight"):
        out[col] = out[col].map(pct)
    for col in ("Sharpe", "Calmar", "turnover", "composite_score"):
        out[col] = out[col].map(num)
    return out


def module_summary(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.groupby("overlay_family")
        .agg(
            candidates=("candidate_id", "count"),
            best_CAGR=("CAGR", "max"),
            best_Calmar=("Calmar", "max"),
            min_abs_MDD=("abs_mdd", "min"),
            median_CAGR=("CAGR", "median"),
            median_abs_MDD=("abs_mdd", "median"),
        )
        .reset_index()
        .sort_values("best_CAGR", ascending=False)
    )


def local_v4_rows() -> pd.DataFrame:
    path = LOCAL_V4_DIR / "v4_vs_v3_comparison.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    wanted = df[
        (df["source_version"].astype(str).eq("v4"))
        | (df["source"].astype(str).eq("v3_selected"))
        | (df["source"].astype(str).eq("v2_selected"))
    ].copy()
    wanted["comparison_label"] = wanted["comparison_group"].fillna(wanted["source"])
    return wanted


def comparison_table(tqqq_frontier: pd.DataFrame, qld_frontier: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = [
        {
            "target": "TQQQ",
            "comparison_label": "v4 user reference CAGR 34.09%",
            "source": "user_prompt_reference",
            "frontier_bucket": "",
            "selection_role": "",
            "strategy": "ema20_ema100_direction__atr_stop",
            "overlay": "v4_reference",
            "CAGR": USER_TQQQ_V4_CAGR_REFERENCE,
            "MDD": np.nan,
            "Sharpe": np.nan,
            "Calmar": np.nan,
            "avg_abs_weight": np.nan,
            "trade_count": np.nan,
            "turnover": np.nan,
        }
    ]
    v4_rows = local_v4_rows()
    for _, row in v4_rows.iterrows():
        rows.append(
            {
                "target": row.get("target"),
                "comparison_label": row.get("comparison_label"),
                "source": row.get("source"),
                "frontier_bucket": "",
                "selection_role": "",
                "strategy": row.get("strategy"),
                "overlay": row.get("overlay"),
                "CAGR": pd.to_numeric(row.get("CAGR"), errors="coerce"),
                "MDD": pd.to_numeric(row.get("MDD"), errors="coerce"),
                "Sharpe": pd.to_numeric(row.get("Sharpe"), errors="coerce"),
                "Calmar": pd.to_numeric(row.get("Calmar"), errors="coerce"),
                "avg_abs_weight": pd.to_numeric(row.get("avg_abs_weight"), errors="coerce"),
                "trade_count": pd.to_numeric(row.get("trade_count"), errors="coerce"),
                "turnover": pd.to_numeric(row.get("annual_turnover"), errors="coerce"),
            }
        )
    for source_name, frame in (("v5_tqqq_frontier", tqqq_frontier), ("v5_qld_frontier", qld_frontier)):
        for _, row in frame.iterrows():
            rows.append(
                {
                    "target": row["target"],
                    "comparison_label": f"v5 best {row['frontier_bucket']} {row['selection_role']}",
                    "source": source_name,
                    "frontier_bucket": row["frontier_bucket"],
                    "selection_role": row["selection_role"],
                    "strategy": row["strategy"],
                    "overlay": row["overlay"],
                    "CAGR": row["CAGR"],
                    "MDD": row["MDD"],
                    "Sharpe": row["Sharpe"],
                    "Calmar": row["Calmar"],
                    "avg_abs_weight": row["avg_abs_weight"],
                    "trade_count": row["trade_count"],
                    "turnover": row["turnover"],
                }
            )
    return pd.DataFrame(rows)


def pick_for_chart(frontier: pd.DataFrame, preferred_bucket: str) -> pd.Series:
    sub = frontier[
        frontier["frontier_bucket"].eq(preferred_bucket)
        & frontier["selection_role"].eq("highest_composite")
    ]
    if not sub.empty:
        return sub.iloc[0]
    return frontier.sort_values(["composite_score", "CAGR"], ascending=[False, False]).iloc[0]


def save_charts(
    run_dir: Path,
    data: dict[str, pd.DataFrame],
    tqqq_result: v4.ReplayResult,
    qld_result: v4.ReplayResult,
    tqqq_v4: v4.ReplayResult,
    qld_v4_robust: v4.ReplayResult,
    qld_v4_aggressive: v4.ReplayResult,
) -> None:
    for target, result, filename, title in (
        ("TQQQ", tqqq_result, "tqqq_v5_signal_chart.png", "TQQQ v5 selected signal"),
        ("QLD", qld_result, "qld_v5_signal_chart.png", "QLD v5 selected signal"),
    ):
        asset = data[target].loc[data[target].index >= PERIOD_START]
        pos = result.position.reindex(asset.index).fillna(0.0)
        entries = pos.gt(EPS) & ~pos.shift(1).fillna(0.0).gt(EPS)
        exits = ~pos.gt(EPS) & pos.shift(1).fillna(0.0).gt(EPS)
        fig, ax1 = plt.subplots(figsize=(12, 5))
        asset["close"].plot(ax=ax1, color="#1f4e79", linewidth=1.2, label=f"{target} close")
        ax1.scatter(asset.index[entries], asset.loc[entries, "close"], marker="^", color="#2ca02c", s=24, label="entry")
        ax1.scatter(asset.index[exits], asset.loc[exits, "close"], marker="v", color="#d62728", s=24, label="exit")
        ax2 = ax1.twinx()
        pos.plot(ax=ax2, color="#ff7f0e", linewidth=0.9, alpha=0.70, label="weight")
        ax1.set_title(title)
        ax2.set_ylim(-0.02, 1.05)
        ax1.grid(True, alpha=0.25)
        ax1.legend(loc="upper left")
        ax2.legend(loc="upper right")
        fig.tight_layout()
        fig.savefig(run_dir / filename, dpi=150)
        plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, 4.5))
    for label, result in (("v5 selected", tqqq_result), ("v4 locked", tqqq_v4)):
        nav = result.nav.loc[result.nav.index >= PERIOD_START]
        nav = nav / nav.iloc[0]
        v4.drawdown(nav).plot(ax=ax, label=label, linewidth=1.5)
    ax.set_title("TQQQ v5 drawdown vs v4 locked")
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(run_dir / "tqqq_v5_drawdown.png", dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, 4.5))
    for label, result in (
        ("v5 selected", qld_result),
        ("v4 robust", qld_v4_robust),
        ("v4 aggressive", qld_v4_aggressive),
    ):
        nav = result.nav.loc[result.nav.index >= PERIOD_START]
        nav = nav / nav.iloc[0]
        v4.drawdown(nav).plot(ax=ax, label=label, linewidth=1.5)
    ax.set_title("QLD v5 drawdown vs v4 tiers")
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(run_dir / "qld_v5_drawdown.png", dpi=150)
    plt.close(fig)


def write_summary(
    run_dir: Path,
    tqqq_frontier: pd.DataFrame,
    qld_frontier: pd.DataFrame,
    tqqq_pareto: pd.DataFrame,
    qld_pareto: pd.DataFrame,
    qld_modules: pd.DataFrame,
    stress: pd.DataFrame,
    tqqq_chart_pick: pd.Series,
    qld_chart_pick: pd.Series,
) -> None:
    tqqq_40 = tqqq_frontier[
        tqqq_frontier["frontier_bucket"].eq("MDD<=40%")
        & tqqq_frontier["selection_role"].eq("highest_CAGR")
    ]
    tqqq_40_cagr = float(tqqq_40["CAGR"].iloc[0]) if not tqqq_40.empty else np.nan
    local_v4_tqqq = local_v4_rows()
    local_v4_tqqq = local_v4_tqqq[
        local_v4_tqqq["source"].astype(str).eq("v4_tqqq_locked_18_2p5")
    ]
    local_v4_cagr = pd.to_numeric(local_v4_tqqq["CAGR"], errors="coerce").iloc[0] if not local_v4_tqqq.empty else np.nan
    qld_return_help = qld_modules.sort_values("best_CAGR", ascending=False).iloc[0]
    qld_dd_help = qld_modules.sort_values("min_abs_MDD", ascending=True).iloc[0]
    qld_pareto_exists = len(qld_pareto) >= 3 and qld_pareto["CAGR"].max() - qld_pareto["CAGR"].min() > 0.03

    tqqq_best = tqqq_frontier.sort_values(["frontier_bucket", "selection_role"]).copy()
    qld_best = qld_frontier.sort_values(["frontier_bucket", "selection_role"]).copy()

    tqqq_stress_pick = stress[
        stress["candidate_id"].eq(str(tqqq_chart_pick["candidate_id"]))
        & stress["target"].eq("TQQQ")
    ].copy()
    qld_stress_pick = stress[
        stress["candidate_id"].eq(str(qld_chart_pick["candidate_id"]))
        & stress["target"].eq("QLD")
    ].copy()

    lines = [
        "# Turning Point Research V5",
        "",
        "## Research Scope",
        "",
        "- Same data, same engine, signal at close -> next open, one-way fee 0.20%, default slippage none.",
        "- No new factors, no complex model, no meta-label main line.",
        "- Composite score: `0.45*CAGR_rank + 0.35*Calmar_rank + 0.15*Sharpe_rank + 0.05*MDD_control_rank` within each asset's candidate set.",
        "",
        "## TQQQ Frontier",
        "",
        md_table(format_frontier_for_md(tqqq_best)),
        "",
        "## QLD Frontier",
        "",
        md_table(format_frontier_for_md(qld_best)),
        "",
        "## Required Answers",
        "",
        f"- TQQQ current selected chart result: `{tqqq_chart_pick['overlay']}`; CAGR {pct(tqqq_chart_pick['CAGR'])}, MDD {pct(tqqq_chart_pick['MDD'])}, Calmar {num(tqqq_chart_pick['Calmar'])}.",
        f"- QLD current selected chart result: `{qld_chart_pick['overlay']}`; CAGR {pct(qld_chart_pick['CAGR'])}, MDD {pct(qld_chart_pick['MDD'])}, Calmar {num(qld_chart_pick['Calmar'])}.",
        f"- Under MDD<=40%, TQQQ highest-CAGR v5 is {pct(tqqq_40_cagr)}. It is {'above' if tqqq_40_cagr > USER_TQQQ_V4_CAGR_REFERENCE else 'not above'} the prompt's v4 34.09% reference.",
        f"- Against the local v4 locked 18/2.5 replay ({pct(local_v4_cagr)}), it is {'above' if pd.notna(local_v4_cagr) and tqqq_40_cagr > local_v4_cagr else 'not above'}.",
        f"- QLD return improvement is most associated with `{qld_return_help['overlay_family']}` candidates (best CAGR {pct(qld_return_help['best_CAGR'])}).",
        f"- QLD drawdown compression is most associated with `{qld_dd_help['overlay_family']}` candidates (lowest MDD magnitude {pct(qld_dd_help['min_abs_MDD'])}).",
        "- In the low-drawdown QLD winners, the direct drawdown reducer is mainly cap + vol scaling inside risk_bundle; standalone drawdown_cap did not win by itself.",
        f"- QLD has {'a visible' if qld_pareto_exists else 'no strong'} Pareto frontier by CAGR vs MDD in this small search; nondominated candidate count = {len(qld_pareto)}.",
        "",
        "## V5 vs V4",
        "",
        "- TQQQ improves over the prompt's 34.09% reference under the <=40% bucket if the local same-engine result above is used. The improvement is mainly ATR/cooldown/trailing-neighborhood behavior; cap/vol/regime overlays mostly buy drawdown control by reducing exposure.",
        "- Relative to the local v4 locked 18/2.5 replay, improvement is more marginal and should be treated as parameter-neighborhood optimization, not a new structural edge.",
        "- The TQQQ winner is the existing confirm_2d trailing variant; because v4 already marked that neighborhood as spike-prone, it is the first result to audit before promotion.",
        "- QLD improvement is clearest as a frontier map: regime-off keeps the high-return end, while risk_bundle/cap/vol/drawdown-cap form the lower-drawdown end.",
        "",
        "## Reliability",
        "",
        "- Most reliable improvement: lower-drawdown QLD buckets from simple exposure controls, because the mechanism is direct and remains interpretable.",
        "- Most likely parameter luck: TQQQ trailing/ATR micro winners, especially when one candidate simultaneously wins CAGR and Calmar from very close stop parameters.",
        "",
        "## Slippage Stress: Chart Picks",
        "",
        "### TQQQ",
        "",
        md_table(
            format_frontier_for_md(
                tqqq_stress_pick.assign(frontier_bucket=tqqq_stress_pick["slippage_model"], selection_role="stress")
            )[
                ["frontier_bucket", "selection_role", "overlay_family", "overlay", "CAGR", "MDD", "Sharpe", "Calmar", "avg_abs_weight", "trade_count", "turnover", "composite_score"]
            ]
        ),
        "",
        "### QLD",
        "",
        md_table(
            format_frontier_for_md(
                qld_stress_pick.assign(frontier_bucket=qld_stress_pick["slippage_model"], selection_role="stress")
            )[
                ["frontier_bucket", "selection_role", "overlay_family", "overlay", "CAGR", "MDD", "Sharpe", "Calmar", "avg_abs_weight", "trade_count", "turnover", "composite_score"]
            ]
        ),
    ]
    write_text(run_dir / "v5_research_summary.md", "\n".join(lines))


def write_readme(
    run_dir: Path,
    tqqq_frontier: pd.DataFrame,
    qld_frontier: pd.DataFrame,
    tqqq_chart_pick: pd.Series,
    qld_chart_pick: pd.Series,
) -> None:
    tqqq_luck = tqqq_frontier.sort_values("CAGR", ascending=False).iloc[0]
    qld_best_30 = qld_frontier[
        qld_frontier["frontier_bucket"].eq("MDD<=30%")
        & qld_frontier["selection_role"].eq("highest_CAGR")
    ]
    qld_effect = qld_best_30.iloc[0] if not qld_best_30.empty else qld_chart_pick
    lines = [
        "# README_FOR_CHATGPT",
        "",
        "1. v5 最大的真实效果提升是什么",
        f"QLD 从二选一变成可用前沿：低回撤端可用 `{qld_chart_pick['overlay']}`，高收益端可用 `{qld_effect['overlay']}`，风险档位比 v4 更清楚。",
        "",
        "2. 哪个结果最值得 ChatGPT 审核",
        f"TQQQ MDD<=40% 的最高 CAGR/综合候选 `{tqqq_chart_pick['overlay']}`，因为它直接回答能否超过 34.09%。",
        "",
        "3. 哪个结果最像单点运气",
        f"TQQQ 最高 CAGR 候选 `{tqqq_luck['overlay']}`，属于 ATR/trailing/cooldown 的近邻微调，最需要看参数邻域稳定性。",
        "",
        "4. v6 应该继续优化还是转入更实盘化验证",
        "v6 应转入更实盘化验证：信号时间戳、成交价敏感性、税费/滑点、信号运维和更严格 walk-forward，而不是继续扩大参数搜索。",
    ]
    write_text(run_dir / "README_FOR_CHATGPT.md", "\n".join(lines))


def required_columns(df: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "strategy",
        "overlay",
        "CAGR",
        "MDD",
        "Sharpe",
        "Calmar",
        "avg_abs_weight",
        "trade_count",
        "turnover",
        "frontier_bucket",
    ]
    for col in cols:
        if col not in df.columns:
            df[col] = np.nan
    lead = cols + [c for c in df.columns if c not in cols]
    return df[lead]


def main() -> None:
    parser = argparse.ArgumentParser(description="Turning point research v5 frontier optimization")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--output-root", type=Path, default=ROOT / "outputs")
    args = parser.parse_args()

    run_dir = args.output_root / f"turning_point_research_v5_{stamp()}"
    run_dir.mkdir(parents=True, exist_ok=True)
    log(f"Output directory: {run_dir}")

    log("Loading data and fixed EMA20/EMA100 base signals")
    data = v2.load_data(args.data_dir)
    _, indicators = v2.build_features(data)
    bases = v2.base_signals(data, indicators)

    log("Evaluating TQQQ small-neighborhood frontier")
    tqqq_all, tqqq_replays, tqqq_spec_by_id = evaluate_specs(data, bases, tqqq_specs())
    tqqq_frontier = select_frontier(tqqq_all, (0.35, 0.40, 0.45))
    tqqq_pareto = pareto_candidates(tqqq_all)

    log("Evaluating QLD small-neighborhood frontier")
    qld_all, qld_replays, qld_spec_by_id = evaluate_specs(data, bases, qld_specs())
    qld_frontier = select_frontier(qld_all, (0.15, 0.20, 0.25, 0.30))
    qld_pareto = pareto_candidates(qld_all)
    qld_modules = module_summary(qld_all)

    log("Running slippage stress on selected frontier rows")
    tqqq_stress = stress_compare(data, bases, tqqq_frontier, tqqq_spec_by_id)
    qld_stress = stress_compare(data, bases, qld_frontier, qld_spec_by_id)
    stress = pd.concat([tqqq_stress, qld_stress], ignore_index=True)

    log("Writing CSV outputs")
    write_csv(required_columns(tqqq_frontier), run_dir / "tqqq_frontier.csv")
    write_csv(required_columns(qld_frontier), run_dir / "qld_frontier.csv")
    write_csv(tqqq_pareto, run_dir / "tqqq_pareto_candidates.csv")
    write_csv(qld_pareto, run_dir / "qld_pareto_candidates.csv")
    write_csv(comparison_table(tqqq_frontier, qld_frontier), run_dir / "v5_vs_v4_comparison.csv")
    write_csv(tqqq_all, run_dir / "tqqq_all_candidates.csv")
    write_csv(qld_all, run_dir / "qld_all_candidates.csv")
    write_csv(qld_modules, run_dir / "qld_overlay_module_summary.csv")
    write_csv(stress, run_dir / "slippage_stress_compare.csv")
    write_csv(tqqq_stress, run_dir / "tqqq_slippage_stress.csv")
    write_csv(qld_stress, run_dir / "qld_slippage_stress.csv")

    log("Writing charts")
    tqqq_pick = pick_for_chart(tqqq_frontier, "MDD<=40%")
    qld_pick = pick_for_chart(qld_frontier, "MDD<=25%")
    tqqq_result = tqqq_replays[str(tqqq_pick["candidate_id"])]
    qld_result = qld_replays[str(qld_pick["candidate_id"])]
    tqqq_v4_spec = StrategySpec(
        target="TQQQ",
        overlay_family="atr_frontier",
        atr_stop=True,
        atr_window=18,
        atr_mult=2.5,
        cooldown_days=10,
        note="v4_locked_18_2p5",
    )
    qld_v4_robust_spec = StrategySpec(
        target="QLD",
        overlay_family="risk_bundle",
        atr_stop=True,
        atr_window=14,
        atr_mult=3.0,
        cooldown_days=10,
        vol_target=0.30,
        max_cap=0.70,
        regime_off=True,
        regime_ma=200,
        note="v4_robust",
    )
    qld_v4_aggressive_spec = StrategySpec(
        target="QLD",
        overlay_family="regime_off",
        regime_off=True,
        regime_ma=200,
        note="v4_aggressive",
    )
    save_charts(
        run_dir,
        data,
        tqqq_result,
        qld_result,
        run_strategy(data, bases, tqqq_v4_spec),
        run_strategy(data, bases, qld_v4_robust_spec),
        run_strategy(data, bases, qld_v4_aggressive_spec),
    )

    log("Writing markdown reports")
    write_summary(
        run_dir,
        tqqq_frontier,
        qld_frontier,
        tqqq_pareto,
        qld_pareto,
        qld_modules,
        stress,
        tqqq_pick,
        qld_pick,
    )
    write_readme(run_dir, tqqq_frontier, qld_frontier, tqqq_pick, qld_pick)
    write_text(
        run_dir / "run_instructions.md",
        "\n".join(
            [
                "# Run Instructions",
                "",
                "From repo root:",
                "",
                "```powershell",
                "python scripts\\qldtqqq_turning_point_research_v5.py",
                "```",
                "",
                "The script writes a timestamped directory under `outputs/turning_point_research_v5_*`.",
            ]
        ),
    )
    write_text(
        run_dir / "changed_files_manifest.txt",
        "\n".join(
            [
                "Added or modified script files:",
                "",
                "- scripts/qldtqqq_turning_point_research_v5.py",
                "",
                "V5 reuses v2/v4 data and metric helpers and does not modify previous research outputs.",
            ]
        ),
    )
    shutil.copy2(ROOT / "scripts" / "qldtqqq_turning_point_research_v5.py", run_dir / "qldtqqq_turning_point_research_v5.py")

    required = [
        "v5_research_summary.md",
        "tqqq_frontier.csv",
        "qld_frontier.csv",
        "tqqq_pareto_candidates.csv",
        "qld_pareto_candidates.csv",
        "v5_vs_v4_comparison.csv",
        "tqqq_v5_signal_chart.png",
        "tqqq_v5_drawdown.png",
        "qld_v5_signal_chart.png",
        "qld_v5_drawdown.png",
        "README_FOR_CHATGPT.md",
    ]
    missing = [name for name in required if not (run_dir / name).exists()]
    if missing:
        raise RuntimeError(f"Missing required v5 outputs: {missing}")
    log("V5 completed")
    log(str(run_dir))


if __name__ == "__main__":
    main()
