"""Turning point research v6: anti-luck audit and product lock.

V6 does not expand the research space. It audits the v5 TQQQ champion and
locks three QLD product tiers from the already discovered simple overlays.
"""

from __future__ import annotations

import argparse
import itertools
import math
import shutil
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
import qldtqqq_turning_point_research_v4 as v4  # noqa: E402
import qldtqqq_turning_point_research_v5 as v5  # noqa: E402
from qldtqqq_turning_point_research_v1 import DEFAULT_DATA_DIR, atr  # noqa: E402


warnings.filterwarnings("ignore", category=FutureWarning)

FEE = 0.002
TRADING_DAYS = 252.0
PERIOD_START = pd.Timestamp("2021-01-01")
FINAL_SPLIT = v4.PeriodSplit("final", "2021_latest", (("2021-01-01", None),))
EPS = 1e-10
V5_DIR = ROOT / "outputs" / "turning_point_research_v5_20260421_223153"


@dataclass(frozen=True)
class TqqqAuditSpec:
    atr_window: int = 18
    atr_mult: float = 2.5
    cooldown_days: int = 10
    confirm_days: int = 2


@dataclass(frozen=True)
class QldTier:
    tier: str
    mdd_limit: float
    spec: v5.StrategySpec
    reason: str
    adjacent: str
    main_driver: str


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def log(message: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", flush=True)


def pct(value: float | int | None) -> str:
    return "nan" if value is None or pd.isna(value) else f"{float(value) * 100:.2f}%"


def num(value: float | int | None, digits: int = 3) -> str:
    return "nan" if value is None or pd.isna(value) else f"{float(value):.{digits}f}"


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


def tqqq_overlay(spec: TqqqAuditSpec) -> str:
    mult = f"{spec.atr_mult:.2f}".rstrip("0").rstrip(".").replace(".", "p")
    return f"atr{spec.atr_window}_{mult}+cd{spec.cooldown_days}+confirm_{spec.confirm_days}d"


def tqqq_strategy() -> str:
    return "ema20_ema100_direction__atr_stop_confirm"


def slippage_rate(asset: pd.DataFrame, idx: pd.Index, model: str) -> pd.Series:
    if model == "none":
        return pd.Series(0.0, index=idx)
    if model == "fixed_5bps":
        return pd.Series(0.0005, index=idx)
    if model == "fixed_10bps":
        return pd.Series(0.0010, index=idx)
    if model == "atr_adaptive":
        atr_pct = atr(asset, 14).div(asset["close"]).reindex(idx).ffill().fillna(0.0)
        return (0.10 * atr_pct).clip(0.0, 0.006)
    raise ValueError(f"unknown slippage model: {model}")


def build_tqqq_desired(
    data: dict[str, pd.DataFrame],
    bases: dict[str, dict[str, pd.Series]],
    spec: TqqqAuditSpec,
) -> pd.Series:
    asset = data["TQQQ"]
    idx = asset.index
    raw = bases["TQQQ"]["ema20_ema100_direction"].reindex(idx).ffill().fillna(0.0).clip(0.0, 1.0)
    close = asset["close"].astype(float).reindex(idx).ffill()
    asset_atr = atr(asset, spec.atr_window).reindex(idx).ffill()

    desired: list[float] = []
    peak = np.nan
    cooldown = 0
    below_stop_streak = 0
    for dt in idx:
        weight = float(raw.loc[dt])
        if cooldown > 0:
            cooldown -= 1
            weight = 0.0
            below_stop_streak = 0
        elif weight > EPS:
            price = close.loc[dt]
            atr_value = asset_atr.loc[dt]
            peak = price if not np.isfinite(peak) else max(peak, price)
            stop_level = peak - spec.atr_mult * atr_value if pd.notna(atr_value) else np.nan
            if pd.notna(stop_level) and price <= stop_level:
                below_stop_streak += 1
            else:
                below_stop_streak = 0
            if below_stop_streak >= spec.confirm_days:
                weight = 0.0
                peak = np.nan
                cooldown = spec.cooldown_days
                below_stop_streak = 0
        else:
            peak = np.nan
            below_stop_streak = 0
        desired.append(float(np.clip(weight, 0.0, 1.0)))
    return pd.Series(desired, index=idx, name="desired")


def replay_desired(
    target: str,
    data: dict[str, pd.DataFrame],
    desired: pd.Series,
    strategy: str,
    overlay: str,
    fee: float = FEE,
    execution: str = "next_open",
    slippage_model: str = "none",
) -> v4.ReplayResult:
    asset = data[target]
    idx = asset.index
    desired = desired.reindex(idx).ffill().fillna(0.0).clip(0.0, 1.0)
    open_p = asset["open"].astype(float).reindex(idx).ffill()
    close = asset["close"].astype(float).reindex(idx).ffill()
    slip = slippage_rate(asset, idx, slippage_model)
    nav = np.ones(len(idx), dtype=float)
    returns = np.zeros(len(idx), dtype=float)
    position = np.zeros(len(idx), dtype=float)
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
            raise ValueError(f"unknown execution: {execution}")
        nav[i] = equity
        returns[i] = equity / prev_equity - 1.0 if prev_equity > 0 else 0.0
        position[i] = pos
        turnover[i] = delta
        cost_rate[i] = cost
    return v4.ReplayResult(
        target=target,
        strategy=strategy,
        overlay=overlay,
        execution=execution,
        fee=fee,
        slippage_model=slippage_model,
        nav=pd.Series(nav, index=idx, name="nav"),
        returns=pd.Series(returns, index=idx, name="returns"),
        position=pd.Series(position, index=idx, name="position"),
        desired=desired,
        turnover=pd.Series(turnover, index=idx, name="turnover"),
        trade_cost_rate=pd.Series(cost_rate, index=idx, name="trade_cost_rate"),
    )


def run_tqqq(
    data: dict[str, pd.DataFrame],
    bases: dict[str, dict[str, pd.Series]],
    spec: TqqqAuditSpec,
    fee: float = FEE,
    execution: str = "next_open",
    slippage_model: str = "none",
) -> v4.ReplayResult:
    desired = build_tqqq_desired(data, bases, spec)
    return replay_desired("TQQQ", data, desired, tqqq_strategy(), tqqq_overlay(spec), fee, execution, slippage_model)


def metric_row(result: v4.ReplayResult, split: v4.PeriodSplit = FINAL_SPLIT) -> dict[str, object]:
    row = v4.metrics_for_split(result, split)
    row["turnover"] = row.get("annual_turnover", np.nan)
    row["abs_mdd"] = abs(float(row["MDD"])) if pd.notna(row.get("MDD")) else np.nan
    return row


def stage_metric(result: v4.ReplayResult, name: str, start: str, end: str | None) -> dict[str, object]:
    mask = result.returns.index >= pd.Timestamp(start)
    if end:
        mask &= result.returns.index <= pd.Timestamp(end)
    idx = result.returns.index[mask]
    ret = result.returns.loc[idx].fillna(0.0)
    nav = (1.0 + ret).cumprod()
    years = max(len(ret) / TRADING_DAYS, 1 / TRADING_DAYS)
    ann = float(nav.iloc[-1] ** (1.0 / years) - 1.0) if len(nav) and nav.iloc[-1] > 0 else np.nan
    total = float(nav.iloc[-1] - 1.0) if len(nav) else np.nan
    pos = result.position.reindex(idx).fillna(0.0)
    turnover = result.turnover.reindex(idx).fillna(0.0)
    entries = (pos.abs() > EPS) & ~(pos.shift(1).fillna(0.0).abs() > EPS)
    return {
        "stage": name,
        "start": start,
        "end": end or "latest",
        "CAGR": ann,
        "total_return": total,
        "MDD": v4.max_drawdown(nav),
        "trade_count": int(entries.sum()),
        "avg_holding_days": v4.holding_days(pos),
        "avg_abs_weight": float(pos.abs().mean()),
        "time_in_market": float(pos.abs().gt(EPS).mean()),
        "turnover": float(turnover.sum() / years),
        "final_nav": float(nav.iloc[-1]) if len(nav) else np.nan,
    }


def tqqq_neighborhood_specs() -> list[TqqqAuditSpec]:
    return [
        TqqqAuditSpec(window, mult, cooldown, confirm)
        for window, mult, cooldown, confirm in itertools.product(
            (17, 18, 19),
            (2.4, 2.5, 2.6),
            (8, 10, 12),
            (1, 2, 3),
        )
    ]


def neighborhood_continuity(
    data: dict[str, pd.DataFrame],
    bases: dict[str, dict[str, pd.Series]],
) -> tuple[pd.DataFrame, dict[str, v4.ReplayResult]]:
    rows: list[dict[str, object]] = []
    replays: dict[str, v4.ReplayResult] = {}
    champion = TqqqAuditSpec()
    champ_key = tqqq_overlay(champion)
    for spec in tqqq_neighborhood_specs():
        result = run_tqqq(data, bases, spec)
        key = tqqq_overlay(spec)
        row = metric_row(result)
        row.update(
            {
                "candidate_id": key,
                "atr_window": spec.atr_window,
                "atr_mult": spec.atr_mult,
                "cooldown_days": spec.cooldown_days,
                "confirm_days": spec.confirm_days,
                "is_champion": key == champ_key,
                "param_distance": abs(spec.atr_window - 18)
                + round(abs(spec.atr_mult - 2.5) / 0.1)
                + abs(spec.cooldown_days - 10) / 2
                + abs(spec.confirm_days - 2),
            }
        )
        rows.append(row)
        replays[key] = result
    df = pd.DataFrame(rows)
    champ = df[df["is_champion"]].iloc[0]
    df["delta_CAGR_vs_champion"] = df["CAGR"] - float(champ["CAGR"])
    df["delta_Calmar_vs_champion"] = df["Calmar"] - float(champ["Calmar"])
    df["delta_MDD_vs_champion"] = df["MDD"] - float(champ["MDD"])
    df["rank_CAGR"] = df["CAGR"].rank(ascending=False, method="min").astype(int)
    df["rank_Calmar"] = df["Calmar"].rank(ascending=False, method="min").astype(int)
    return df.sort_values(["confirm_days", "cooldown_days", "atr_window", "atr_mult"]).reset_index(drop=True), replays


def sensitivity_summary(neighborhood: pd.DataFrame) -> pd.DataFrame:
    dims = [
        ("atr_window", 18),
        ("atr_mult", 2.5),
        ("cooldown_days", 10),
        ("confirm_days", 2),
    ]
    rows: list[dict[str, object]] = []
    for dim, base_value in dims:
        mask = pd.Series(True, index=neighborhood.index)
        for other_dim, other_base in dims:
            if other_dim != dim:
                mask &= neighborhood[other_dim].eq(other_base)
        sub = neighborhood[mask].copy()
        rows.append(
            {
                "dimension": dim,
                "values": ",".join(sub[dim].astype(str)),
                "CAGR_range": float(sub["CAGR"].max() - sub["CAGR"].min()),
                "Calmar_range": float(sub["Calmar"].max() - sub["Calmar"].min()),
                "MDD_range": float(sub["MDD"].max() - sub["MDD"].min()),
                "best_value_by_Calmar": sub.sort_values("Calmar", ascending=False).iloc[0][dim],
                "worst_value_by_Calmar": sub.sort_values("Calmar", ascending=True).iloc[0][dim],
            }
        )
    return pd.DataFrame(rows).sort_values("Calmar_range", ascending=False)


def save_neighborhood_heatmap(neighborhood: pd.DataFrame, run_dir: Path) -> None:
    heat = neighborhood[
        neighborhood["cooldown_days"].eq(10) & neighborhood["confirm_days"].eq(2)
    ].pivot(index="atr_window", columns="atr_mult", values="Calmar")
    fig, ax = plt.subplots(figsize=(7.5, 5.2))
    im = ax.imshow(heat.values, cmap="YlGnBu", aspect="auto")
    ax.set_xticks(range(len(heat.columns)))
    ax.set_xticklabels([str(c) for c in heat.columns])
    ax.set_yticks(range(len(heat.index)))
    ax.set_yticklabels([str(i) for i in heat.index])
    ax.set_xlabel("ATR multiple")
    ax.set_ylabel("ATR window")
    ax.set_title("TQQQ v6 neighborhood Calmar: cooldown=10, confirm_days=2")
    for i in range(heat.shape[0]):
        for j in range(heat.shape[1]):
            ax.text(j, i, f"{heat.values[i, j]:.2f}", ha="center", va="center", fontsize=9)
    fig.colorbar(im, ax=ax, label="Calmar")
    fig.tight_layout()
    fig.savefig(run_dir / "tqqq_neighborhood_heatmap.png", dpi=160)
    plt.close(fig)


def execution_stress(
    data: dict[str, pd.DataFrame],
    bases: dict[str, dict[str, pd.Series]],
    spec: TqqqAuditSpec,
) -> pd.DataFrame:
    cases = [
        ("next_open", "none", FEE, "next_open"),
        ("next_close", "none", FEE, "next_close"),
        ("next_open_fixed_5bps", "fixed_5bps", FEE, "next_open"),
        ("next_open_fixed_10bps", "fixed_10bps", FEE, "next_open"),
        ("next_open_atr_adaptive", "atr_adaptive", FEE, "next_open"),
        ("next_close_fee_0p5pct_atr_adaptive", "atr_adaptive", 0.005, "next_close"),
    ]
    rows: list[dict[str, object]] = []
    for name, slip, fee, execution in cases:
        result = run_tqqq(data, bases, spec, fee, execution, slip)
        row = metric_row(result)
        row.update({"stress_case": name, "execution": execution, "slippage_model": slip, "one_way_fee": fee})
        rows.append(row)
    df = pd.DataFrame(rows)
    base = df[df["stress_case"].eq("next_open")].iloc[0]
    df["CAGR_delta_vs_base"] = df["CAGR"] - float(base["CAGR"])
    df["Calmar_delta_vs_base"] = df["Calmar"] - float(base["Calmar"])
    df["MDD_delta_vs_base"] = df["MDD"] - float(base["MDD"])
    return df


def purged_validation(
    data: dict[str, pd.DataFrame],
    bases: dict[str, dict[str, pd.Series]],
    specs: list[TqqqAuditSpec],
) -> pd.DataFrame:
    splits = [s for s in v4.strict_splits() if s.split_type in {"purged", "combinational_purged"}]
    rows: list[dict[str, object]] = []
    for spec in specs:
        result = run_tqqq(data, bases, spec)
        for split in splits:
            row = metric_row(result, split)
            row.update(
                {
                    "candidate_id": tqqq_overlay(spec),
                    "atr_window": spec.atr_window,
                    "atr_mult": spec.atr_mult,
                    "cooldown_days": spec.cooldown_days,
                    "confirm_days": spec.confirm_days,
                    "is_champion": spec == TqqqAuditSpec(),
                }
            )
            rows.append(row)
    df = pd.DataFrame(rows)
    df["rank_Calmar_in_split"] = df.groupby("split")["Calmar"].rank(ascending=False, method="min")
    df["rank_CAGR_in_split"] = df.groupby("split")["CAGR"].rank(ascending=False, method="min")
    return df.sort_values(["split_type", "split", "rank_Calmar_in_split"]).reset_index(drop=True)


def trade_contribution(result: v4.ReplayResult) -> pd.DataFrame:
    trades = v4.trade_log(result)
    if trades.empty:
        return trades
    trades = trades.sort_values("entry_date").reset_index(drop=True)
    trades["trade_no"] = np.arange(1, len(trades) + 1)
    trades["profit_rank"] = trades["strategy_return"].rank(ascending=False, method="min")
    trades["loss_rank"] = trades["strategy_return"].rank(ascending=True, method="min")
    positive = trades.loc[trades["strategy_return"] > 0, "strategy_return"]
    negative = trades.loc[trades["strategy_return"] < 0, "strategy_return"]
    total_positive = float(positive.sum())
    total_loss = float(negative.abs().sum())
    net_trade_sum = float(trades["strategy_return"].sum())
    top5_profit = float(positive.sort_values(ascending=False).head(5).sum())
    top10_profit = float(positive.sort_values(ascending=False).head(10).sum())
    top10_loss = float(negative.sort_values().head(10).abs().sum())
    trades["positive_contribution_share"] = np.where(
        total_positive > 0,
        trades["strategy_return"].clip(lower=0) / total_positive,
        np.nan,
    )
    trades["loss_contribution_share"] = np.where(
        total_loss > 0,
        trades["strategy_return"].clip(upper=0).abs() / total_loss,
        np.nan,
    )
    trades["top5_profit_share_of_net_trade_sum"] = top5_profit / net_trade_sum if net_trade_sum > 0 else np.nan
    trades["top10_profit_share_of_net_trade_sum"] = top10_profit / net_trade_sum if net_trade_sum > 0 else np.nan
    trades["top10_profit_share_of_total_positive"] = top10_profit / total_positive if total_positive > 0 else np.nan
    trades["top10_loss_share_of_total_loss"] = top10_loss / total_loss if total_loss > 0 else np.nan
    trades["net_trade_sum"] = net_trade_sum
    trades["total_positive_trade_return"] = total_positive
    trades["total_loss_trade_return_abs"] = total_loss
    return trades


def qld_tiers() -> list[QldTier]:
    conservative = v5.StrategySpec(
        target="QLD",
        overlay_family="risk_bundle",
        atr_stop=True,
        atr_window=14,
        atr_mult=2.75,
        cooldown_days=10,
        vol_target=0.35,
        max_cap=0.65,
        regime_off=True,
        regime_ma=190,
        position_scale=0.95,
        note="v6_conservative_lock",
    )
    stable = v5.StrategySpec(
        target="QLD",
        overlay_family="risk_bundle",
        atr_stop=True,
        atr_window=14,
        atr_mult=2.75,
        cooldown_days=10,
        vol_target=0.35,
        max_cap=0.75,
        regime_off=True,
        regime_ma=200,
        note="v6_stable_lock",
    )
    aggressive = v5.StrategySpec(
        target="QLD",
        overlay_family="regime_off",
        regime_off=True,
        regime_ma=180,
        regime_buffer=-0.005,
        note="v6_aggressive_lock",
    )
    return [
        QldTier(
            "conservative",
            0.15,
            conservative,
            "Keeps the lowest drawdown/highest-Calmar v5 frontier family under 15% MDD.",
            "It gives up about 2 points of CAGR versus the 15% highest-CAGR row, but has lower MDD and better Calmar.",
            "risk_bundle: cap + vol scaling, with ATR stop as a secondary guard",
        ),
        QldTier(
            "stable",
            0.20,
            stable,
            "Uses the v5 highest-composite low-drawdown candidate; strong CAGR while still inside the 15% actual MDD area.",
            "It avoids the <=20% highest-CAGR row because that row adds drawdown cap and worsens Calmar for a small CAGR gain.",
            "risk_bundle: vol scaling + cap, then ATR stop",
        ),
        QldTier(
            "aggressive",
            0.30,
            aggressive,
            "Locks the high-return end with the simplest overlay that stays below 30% MDD.",
            "It beats risk_bundle on CAGR and turnover simplicity; the tradeoff is weaker drawdown control.",
            "regime_off",
        ),
    ]


def qld_product_lock(
    data: dict[str, pd.DataFrame],
    bases: dict[str, dict[str, pd.Series]],
) -> tuple[pd.DataFrame, dict[str, v4.ReplayResult], list[QldTier]]:
    rows: list[dict[str, object]] = []
    replays: dict[str, v4.ReplayResult] = {}
    tiers = qld_tiers()
    for tier in tiers:
        result = v5.run_strategy(data, bases, tier.spec)
        key = tier.tier
        replays[key] = result
        row = v5.row_for_result(tier.spec, result)
        row.update(
            {
                "product_tier": tier.tier,
                "mdd_limit": tier.mdd_limit,
                "selected_strategy_name": v5.strategy_name(tier.spec),
                "final_overlay": v5.overlay_label(tier.spec),
                "selection_reason": tier.reason,
                "adjacent_candidate_comparison": tier.adjacent,
                "main_contribution": tier.main_driver,
                "within_mdd_limit": bool(abs(row["MDD"]) <= tier.mdd_limit),
                "annual_turnover": row.get("annual_turnover", row.get("turnover", np.nan)),
            }
        )
        rows.append(row)
    return pd.DataFrame(rows), replays, tiers


def save_charts(
    run_dir: Path,
    data: dict[str, pd.DataFrame],
    tqqq_result: v4.ReplayResult,
    qld_replays: dict[str, v4.ReplayResult],
) -> None:
    asset = data["TQQQ"].loc[data["TQQQ"].index >= PERIOD_START]
    pos = tqqq_result.position.reindex(asset.index).fillna(0.0)
    entries = pos.gt(EPS) & ~pos.shift(1).fillna(0.0).gt(EPS)
    exits = ~pos.gt(EPS) & pos.shift(1).fillna(0.0).gt(EPS)
    fig, ax1 = plt.subplots(figsize=(12, 5))
    asset["close"].plot(ax=ax1, color="#1f4e79", linewidth=1.2, label="TQQQ close")
    ax1.scatter(asset.index[entries], asset.loc[entries, "close"], marker="^", color="#2ca02c", s=24, label="entry")
    ax1.scatter(asset.index[exits], asset.loc[exits, "close"], marker="v", color="#d62728", s=24, label="exit")
    ax2 = ax1.twinx()
    pos.plot(ax=ax2, color="#ff7f0e", linewidth=0.9, alpha=0.70, label="weight")
    ax1.set_title("TQQQ v6 champion signal: ATR18 2.5 cooldown10 confirm2d")
    ax2.set_ylim(-0.02, 1.05)
    ax1.grid(True, alpha=0.25)
    ax1.legend(loc="upper left")
    ax2.legend(loc="upper right")
    fig.tight_layout()
    fig.savefig(run_dir / "tqqq_v6_signal_chart.png", dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, 4.5))
    nav = tqqq_result.nav.loc[tqqq_result.nav.index >= PERIOD_START]
    v4.drawdown(nav / nav.iloc[0]).plot(ax=ax, label="TQQQ champion", linewidth=1.7)
    ax.set_title("TQQQ v6 champion drawdown")
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(run_dir / "tqqq_v6_drawdown.png", dpi=150)
    plt.close(fig)

    qld_asset = data["QLD"].loc[data["QLD"].index >= PERIOD_START]
    fig, ax1 = plt.subplots(figsize=(12, 5))
    qld_asset["close"].plot(ax=ax1, color="#1f4e79", linewidth=1.2, label="QLD close")
    ax2 = ax1.twinx()
    for tier, result in qld_replays.items():
        result.position.reindex(qld_asset.index).fillna(0.0).plot(ax=ax2, linewidth=0.95, alpha=0.78, label=tier)
    ax1.set_title("QLD v6 product tiers: target weights")
    ax2.set_ylim(-0.02, 1.05)
    ax1.grid(True, alpha=0.25)
    ax1.legend(loc="upper left")
    ax2.legend(loc="upper right")
    fig.tight_layout()
    fig.savefig(run_dir / "qld_v6_signal_chart.png", dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, 4.5))
    for tier, result in qld_replays.items():
        nav = result.nav.loc[result.nav.index >= PERIOD_START]
        v4.drawdown(nav / nav.iloc[0]).plot(ax=ax, label=tier, linewidth=1.5)
    ax.set_title("QLD v6 product tiers drawdown")
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(run_dir / "qld_v6_drawdown.png", dpi=150)
    plt.close(fig)


def fmt_metrics_for_md(df: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "product_tier",
        "final_overlay",
        "CAGR",
        "MDD",
        "Sharpe",
        "Calmar",
        "trade_count",
        "annual_turnover",
        "avg_abs_weight",
        "time_in_market",
    ]
    out = df[cols].copy()
    for col in ("CAGR", "MDD", "avg_abs_weight", "time_in_market"):
        out[col] = out[col].map(pct)
    for col in ("Sharpe", "Calmar", "annual_turnover"):
        out[col] = out[col].map(num)
    return out


def write_qld_summary(run_dir: Path, lock: pd.DataFrame) -> None:
    lines = ["# QLD Product Lock Summary", ""]
    lines.append(md_table(fmt_metrics_for_md(lock)))
    lines.append("")
    for _, row in lock.iterrows():
        lines.extend(
            [
                f"## {row['product_tier']}",
                "",
                f"- Final: `{row['final_overlay']}`.",
                f"- Why: {row['selection_reason']}",
                f"- Adjacent comparison: {row['adjacent_candidate_comparison']}",
                f"- Main contribution: {row['main_contribution']}.",
                f"- Limit check: MDD {pct(row['MDD'])} vs limit {pct(row['mdd_limit'])}; within limit = `{row['within_mdd_limit']}`.",
                "",
            ]
        )
    write_text(run_dir / "qld_product_lock_summary.md", "\n".join(lines))


def formatted_stage_table(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in ("CAGR", "total_return", "MDD", "avg_abs_weight", "time_in_market"):
        out[col] = out[col].map(pct)
    for col in ("avg_holding_days", "turnover"):
        out[col] = out[col].map(num)
    return out[["stage", "CAGR", "total_return", "MDD", "trade_count", "avg_holding_days", "avg_abs_weight", "turnover"]]


def write_tqqq_audit(
    run_dir: Path,
    neighborhood: pd.DataFrame,
    sensitivity: pd.DataFrame,
    regimes: pd.DataFrame,
    trades: pd.DataFrame,
    stress: pd.DataFrame,
    purged: pd.DataFrame,
) -> tuple[bool, bool, str]:
    champion = neighborhood[neighborhood["is_champion"]].iloc[0]
    direct = neighborhood[(neighborhood["param_distance"] > 0) & (neighborhood["param_distance"] <= 1.01)]
    calmar_gap = float(champion["Calmar"] - direct["Calmar"].median()) if not direct.empty else np.nan
    cagr_gap = float(champion["CAGR"] - direct["CAGR"].median()) if not direct.empty else np.nan
    single_point_spike = bool(pd.notna(calmar_gap) and (calmar_gap > 0.25 or cagr_gap > 0.05))
    sensitive_dim = str(sensitivity.sort_values("Calmar_range", ascending=False).iloc[0]["dimension"])
    smooth = not single_point_spike and float(sensitivity["Calmar_range"].max()) < 0.45

    total_return_by_stage = regimes["total_return"].copy()
    positive_total = total_return_by_stage.clip(lower=0).sum()
    top_stage_share = float(total_return_by_stage.clip(lower=0).max() / positive_total) if positive_total > 0 else np.nan
    relies_on_few_years = bool(pd.notna(top_stage_share) and top_stage_share > 0.60)
    hard_2022 = regimes[regimes["stage"].eq("2022")].iloc[0]
    hard_2025 = regimes[regimes["stage"].eq("2025+")].iloc[0]

    top5_net = float(trades["top5_profit_share_of_net_trade_sum"].iloc[0]) if not trades.empty else np.nan
    top10_pos = float(trades["top10_profit_share_of_total_positive"].iloc[0]) if not trades.empty else np.nan
    super_trade_risk = bool((pd.notna(top5_net) and top5_net > 0.75) or (pd.notna(top10_pos) and top10_pos > 0.80))

    worst_stress = stress.sort_values("Calmar").iloc[0]
    stress_collapse = bool(stress["CAGR"].min() <= 0 or stress["Calmar"].min() < 0.30)

    champion_purged = purged[purged["is_champion"]].copy()
    median_purged_rank = float(champion_purged["rank_Calmar_in_split"].median())
    top_quartile_limit = max(1.0, math.ceil(len(neighborhood) * 0.25))
    strict_pass = bool((not single_point_spike) and (not stress_collapse) and median_purged_rank <= top_quartile_limit)
    quasi_live_ready = bool((not stress_collapse) and median_purged_rank <= top_quartile_limit and not super_trade_risk)

    stress_md = stress[
        ["stress_case", "CAGR", "MDD", "Sharpe", "Calmar", "trade_count", "turnover", "CAGR_delta_vs_base", "Calmar_delta_vs_base"]
    ].copy()
    for col in ("CAGR", "MDD", "CAGR_delta_vs_base"):
        stress_md[col] = stress_md[col].map(pct)
    for col in ("Sharpe", "Calmar", "turnover", "Calmar_delta_vs_base"):
        stress_md[col] = stress_md[col].map(num)

    sens_md = sensitivity.copy()
    for col in ("CAGR_range", "Calmar_range", "MDD_range"):
        sens_md[col] = sens_md[col].map(num)

    champion_purged_md = champion_purged[
        ["split_type", "split", "CAGR", "MDD", "Calmar", "rank_Calmar_in_split", "rank_CAGR_in_split"]
    ].copy()
    for col in ("CAGR", "MDD"):
        champion_purged_md[col] = champion_purged_md[col].map(pct)
    champion_purged_md["Calmar"] = champion_purged_md["Calmar"].map(num)

    lines = [
        "# TQQQ Anti-Luck Audit",
        "",
        "## A1 Parameter Continuity",
        "",
        f"- Champion: `{champion['candidate_id']}`; CAGR {pct(champion['CAGR'])}, MDD {pct(champion['MDD'])}, Calmar {num(champion['Calmar'])}.",
        f"- Single-point spike flag: `{single_point_spike}`. Gap vs direct-neighbor median: Calmar {num(calmar_gap)}, CAGR {pct(cagr_gap)}.",
        f"- Neighborhood smooth flag: `{smooth}`.",
        f"- Most sensitive dimension by Calmar range: `{sensitive_dim}`.",
        "",
        md_table(sens_md),
        "",
        "## A2 Stage Attribution",
        "",
        md_table(formatted_stage_table(regimes)),
        "",
        f"- Top positive stage contribution share: {pct(top_stage_share)}; relies on few years = `{relies_on_few_years}`.",
        f"- 2022 result: CAGR {pct(hard_2022['CAGR'])}, total return {pct(hard_2022['total_return'])}, MDD {pct(hard_2022['MDD'])}.",
        f"- 2025+ result: CAGR {pct(hard_2025['CAGR'])}, total return {pct(hard_2025['total_return'])}, MDD {pct(hard_2025['MDD'])}.",
        "",
        "## A3 Trade Attribution",
        "",
        f"- Top 10 profitable trades / total positive trade return: {pct(top10_pos)}.",
        f"- Top 10 loss trades / total loss trade return: {pct(trades['top10_loss_share_of_total_loss'].iloc[0] if not trades.empty else np.nan)}.",
        f"- Top 5 profitable trades / net trade return sum: {pct(top5_net)}.",
        f"- Top 10 profitable trades / net trade return sum: {pct(trades['top10_profit_share_of_net_trade_sum'].iloc[0] if not trades.empty else np.nan)}.",
        f"- Few-super-trades risk flag: `{super_trade_risk}`.",
        "",
        "## A4 Execution Stress",
        "",
        md_table(stress_md),
        "",
        f"- Most fragile assumption: `{worst_stress['stress_case']}` with CAGR {pct(worst_stress['CAGR'])}, MDD {pct(worst_stress['MDD'])}, Calmar {num(worst_stress['Calmar'])}.",
        f"- Collapse under light execution change: `{stress_collapse}`.",
        "",
        "## A5 Purged Validation",
        "",
        md_table(champion_purged_md),
        "",
        f"- Median Calmar rank across purged/combinational splits: {num(median_purged_rank)} / {len(neighborhood)} candidates.",
        "",
        "## Final Audit Answer",
        "",
        f"- Anti-luck audit pass: `{strict_pass}`.",
        f"- Worth entering quasi-live validation: `{quasi_live_ready}`.",
    ]
    write_text(run_dir / "tqqq_anti_luck_audit.md", "\n".join(lines))
    return strict_pass, quasi_live_ready, sensitive_dim


def write_meta_short(run_dir: Path) -> None:
    write_text(
        run_dir / "meta_label_postmortem_short.md",
        "\n".join(
            [
                "# Meta-Label Short Postmortem",
                "",
                "Meta-label remains out of the main line in v6.",
                "",
                "- It did not show stable marginal benefit over the simple EMA trend plus risk overlays.",
                "- The 2021+ sample has too few independent regimes, so a light classifier can easily remove profitable rebound exposure.",
                "- Current labels are useful diagnostics, but still noisy for entry/exit gating on leveraged ETFs.",
                "",
                "Restart condition: only revisit meta-label if purged/CPCV validation shows stable out-of-sample lift after costs, without large CAGR drag or hidden complexity.",
            ]
        ),
    )


def v6_vs_v5(
    champion_row: dict[str, object],
    qld_lock: pd.DataFrame,
    stress: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for path, label in ((V5_DIR / "tqqq_frontier.csv", "v5_tqqq_frontier"), (V5_DIR / "qld_frontier.csv", "v5_qld_frontier")):
        if path.exists():
            df = pd.read_csv(path)
            for _, row in df.iterrows():
                rows.append(
                    {
                        "source": label,
                        "target": row.get("target"),
                        "bucket_or_tier": row.get("frontier_bucket"),
                        "role": row.get("selection_role"),
                        "strategy": row.get("strategy"),
                        "overlay": row.get("overlay"),
                        "CAGR": row.get("CAGR"),
                        "MDD": row.get("MDD"),
                        "Sharpe": row.get("Sharpe"),
                        "Calmar": row.get("Calmar"),
                        "trade_count": row.get("trade_count"),
                        "turnover": row.get("turnover"),
                        "avg_abs_weight": row.get("avg_abs_weight"),
                    }
                )
    rows.append(
        {
            "source": "v6_tqqq_audit_champion",
            "target": "TQQQ",
            "bucket_or_tier": "anti_luck_audit",
            "role": "champion",
            "strategy": champion_row.get("strategy"),
            "overlay": champion_row.get("overlay"),
            "CAGR": champion_row.get("CAGR"),
            "MDD": champion_row.get("MDD"),
            "Sharpe": champion_row.get("Sharpe"),
            "Calmar": champion_row.get("Calmar"),
            "trade_count": champion_row.get("trade_count"),
            "turnover": champion_row.get("turnover"),
            "avg_abs_weight": champion_row.get("avg_abs_weight"),
        }
    )
    for _, row in qld_lock.iterrows():
        rows.append(
            {
                "source": "v6_qld_product_lock",
                "target": "QLD",
                "bucket_or_tier": row.get("product_tier"),
                "role": "locked",
                "strategy": row.get("strategy"),
                "overlay": row.get("final_overlay"),
                "CAGR": row.get("CAGR"),
                "MDD": row.get("MDD"),
                "Sharpe": row.get("Sharpe"),
                "Calmar": row.get("Calmar"),
                "trade_count": row.get("trade_count"),
                "turnover": row.get("turnover"),
                "avg_abs_weight": row.get("avg_abs_weight"),
            }
        )
    worst = stress.sort_values("Calmar").iloc[0]
    rows.append(
        {
            "source": "v6_tqqq_worst_execution_stress",
            "target": "TQQQ",
            "bucket_or_tier": worst.get("stress_case"),
            "role": "stress",
            "strategy": worst.get("strategy"),
            "overlay": worst.get("overlay"),
            "CAGR": worst.get("CAGR"),
            "MDD": worst.get("MDD"),
            "Sharpe": worst.get("Sharpe"),
            "Calmar": worst.get("Calmar"),
            "trade_count": worst.get("trade_count"),
            "turnover": worst.get("turnover"),
            "avg_abs_weight": worst.get("avg_abs_weight"),
        }
    )
    return pd.DataFrame(rows)


def write_summary(
    run_dir: Path,
    tqqq_pass: bool,
    quasi_live_ready: bool,
    sensitive_dim: str,
    champion_row: pd.Series,
    stress: pd.DataFrame,
    qld_lock: pd.DataFrame,
) -> None:
    qld_short = qld_lock[["product_tier", "final_overlay", "CAGR", "MDD", "Calmar"]].copy()
    for col in ("CAGR", "MDD"):
        qld_short[col] = qld_short[col].map(pct)
    qld_short["Calmar"] = qld_short["Calmar"].map(num)
    worst_stress = stress.sort_values("Calmar").iloc[0]
    lines = [
        "# Turning Point Research V6",
        "",
        "## Executive Answer",
        "",
        f"- TQQQ champion `{champion_row['candidate_id']}` anti-luck audit pass: `{tqqq_pass}`.",
        f"- It is {'worth' if quasi_live_ready else 'not yet clearly worth'} entering quasi-live validation. The largest uncertainty is `{sensitive_dim}` sensitivity plus confirm-trailing parameter luck.",
        f"- Worst stress case: `{worst_stress['stress_case']}`; CAGR {pct(worst_stress['CAGR'])}, MDD {pct(worst_stress['MDD'])}, Calmar {num(worst_stress['Calmar'])}.",
        "- QLD product locks:",
        "",
        md_table(qld_short),
        "",
        "## V7 Direction",
        "",
        "V7 should lean toward quasi-live validation rather than more optimization: timestamp checks, next-open fill realism, slippage/fee sensitivity, signal operations, and paper-trading style monitoring.",
    ]
    write_text(run_dir / "v6_research_summary.md", "\n".join(lines))


def write_readme(
    run_dir: Path,
    tqqq_pass: bool,
    champion_row: pd.Series,
    qld_lock: pd.DataFrame,
) -> None:
    qld_items = "; ".join([f"{r.product_tier}: {r.final_overlay}" for r in qld_lock.itertuples()])
    write_text(
        run_dir / "README_FOR_CHATGPT.md",
        "\n".join(
            [
                "# README_FOR_CHATGPT",
                "",
                "1. 本轮最可信的结果是什么",
                "QLD 三档产品化锁定最可信，因为它从 v5 前沿中按风险档位选取，并优先简单、稳健、成本不敏感。",
                "",
                "2. TQQQ 冠军最大的不确定性是什么",
                f"`{champion_row['candidate_id']}` 是否是 confirm-trailing 参数运气；本轮 anti-luck pass = `{tqqq_pass}`。",
                "",
                "3. QLD 三档最终方案分别是什么",
                qld_items,
                "",
                "4. v7 最建议做什么",
                "转入准实盘化验证：信号时间戳、成交假设、滑点压力、运行监控、纸面交易，而不是扩大搜索空间。",
            ]
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Turning point research v6 anti-luck audit")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--output-root", type=Path, default=ROOT / "outputs")
    args = parser.parse_args()

    run_dir = args.output_root / f"turning_point_research_v6_{stamp()}"
    run_dir.mkdir(parents=True, exist_ok=True)
    log(f"Output directory: {run_dir}")

    log("Loading data and fixed base signals")
    data = v2.load_data(args.data_dir)
    _, indicators = v2.build_features(data)
    bases = v2.base_signals(data, indicators)

    champion = TqqqAuditSpec()
    log("Running TQQQ anti-luck neighborhood")
    neighborhood, tqqq_replays = neighborhood_continuity(data, bases)
    save_neighborhood_heatmap(neighborhood, run_dir)
    sensitivity = sensitivity_summary(neighborhood)

    champion_key = tqqq_overlay(champion)
    champion_result = tqqq_replays[champion_key]
    champion_row = neighborhood[neighborhood["is_champion"]].iloc[0]

    log("Running TQQQ stage, trade, stress, and purged checks")
    regimes = pd.DataFrame(
        [
            stage_metric(champion_result, "2021", "2021-01-01", "2021-12-31"),
            stage_metric(champion_result, "2022", "2022-01-01", "2022-12-31"),
            stage_metric(champion_result, "2023", "2023-01-01", "2023-12-31"),
            stage_metric(champion_result, "2024", "2024-01-01", "2024-12-31"),
            stage_metric(champion_result, "2025+", "2025-01-01", None),
        ]
    )
    trades = trade_contribution(champion_result)
    stress = execution_stress(data, bases, champion)
    purged = purged_validation(data, bases, tqqq_neighborhood_specs())

    log("Locking QLD product tiers")
    qld_lock, qld_replays, _ = qld_product_lock(data, bases)

    log("Writing CSV outputs")
    write_csv(neighborhood, run_dir / "tqqq_neighborhood_continuity.csv")
    write_csv(regimes, run_dir / "tqqq_regime_attribution.csv")
    write_csv(trades, run_dir / "tqqq_trade_contribution.csv")
    write_csv(stress, run_dir / "tqqq_execution_stress.csv")
    write_csv(purged, run_dir / "tqqq_purged_validation.csv")
    write_csv(qld_lock, run_dir / "qld_product_lock_table.csv")

    log("Writing markdown reports")
    tqqq_pass, quasi_live_ready, sensitive_dim = write_tqqq_audit(
        run_dir,
        neighborhood,
        sensitivity,
        regimes,
        trades,
        stress,
        purged,
    )
    write_qld_summary(run_dir, qld_lock)
    write_meta_short(run_dir)
    comparison = v6_vs_v5(champion_row, qld_lock, stress)
    write_csv(comparison, run_dir / "v6_vs_v5_comparison.csv")

    log("Writing charts")
    save_charts(run_dir, data, champion_result, qld_replays)
    write_summary(run_dir, tqqq_pass, quasi_live_ready, sensitive_dim, champion_row, stress, qld_lock)
    write_readme(run_dir, tqqq_pass, champion_row, qld_lock)

    write_text(
        run_dir / "run_instructions.md",
        "\n".join(
            [
                "# Run Instructions",
                "",
                "From repo root:",
                "",
                "```powershell",
                "python scripts\\qldtqqq_turning_point_research_v6.py",
                "```",
                "",
                "The script writes a timestamped directory under `outputs/turning_point_research_v6_*`.",
            ]
        ),
    )
    write_text(
        run_dir / "changed_files_manifest.txt",
        "\n".join(
            [
                "Added or modified script files:",
                "",
                "- scripts/qldtqqq_turning_point_research_v6.py",
                "",
                "V6 reuses v2/v4/v5 helpers and does not modify previous research outputs.",
            ]
        ),
    )
    shutil.copy2(ROOT / "scripts" / "qldtqqq_turning_point_research_v6.py", run_dir / "qldtqqq_turning_point_research_v6.py")

    required = [
        "v6_research_summary.md",
        "tqqq_anti_luck_audit.md",
        "tqqq_neighborhood_continuity.csv",
        "tqqq_neighborhood_heatmap.png",
        "tqqq_regime_attribution.csv",
        "tqqq_trade_contribution.csv",
        "tqqq_execution_stress.csv",
        "tqqq_purged_validation.csv",
        "qld_product_lock_table.csv",
        "qld_product_lock_summary.md",
        "meta_label_postmortem_short.md",
        "v6_vs_v5_comparison.csv",
        "tqqq_v6_signal_chart.png",
        "tqqq_v6_drawdown.png",
        "qld_v6_signal_chart.png",
        "qld_v6_drawdown.png",
        "changed_files_manifest.txt",
        "run_instructions.md",
        "README_FOR_CHATGPT.md",
    ]
    missing = [name for name in required if not (run_dir / name).exists()]
    if missing:
        raise RuntimeError(f"Missing required v6 outputs: {missing}")
    log("V6 completed")
    log(str(run_dir))


if __name__ == "__main__":
    main()
