from __future__ import annotations

"""Independent QLD/TQQQ/VIX research comparison script.

This script is not part of FORMAL_MVE2, must not replace the v8.2 frozen
baseline, must not create v10, is not trading advice, and does not connect to
broker/API services.
"""

import argparse
import json
import logging
import math
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_ROOT = ROOT / "outputs" / "qldtqqq_turning_points"
DEFAULT_OUTPUT_ROOT = ROOT / "outputs" / "qldtqqq_turning_points"
SYMBOLS = ("QQQ", "QLD", "TQQQ")
WF_START = "2014-01-01"
TEST_START = "2021-01-01"
SCRIPT_ROLE = "independent_qldtqqq_vix_research"
RESEARCH_ONLY_WARNING = (
    "Independent QLD/TQQQ/VIX research only; not FORMAL_MVE2, not a v8.2 "
    "baseline replacement, not v10, not trading advice, and no broker/API use."
)
LATEST_RUN_REPRO_WARNING = (
    "Using latest run by mtime is convenient but not fully reproducible. "
    "For formal reuse, pass --input-run explicitly."
)
PLANNED_OUTPUT_FILES = [
    "logs/run.log",
    "reports/comparison_report.md",
    "reports/comparison_metrics.xlsx",
    "strategy_period_metrics.csv",
    "canonical_comparison.csv",
    "trade_log.csv",
    "trade_summary.csv",
    "vix_threshold_counts.csv",
    "vix_regime_counts.csv",
    "data_latest_dates.csv",
    "ranking_test_2021_latest.csv",
    "RUN_SUMMARY.json",
    "RUN_SUMMARY.md",
    "NEXT_STEPS.md",
    "manifest.json",
]


def latest_turning_run() -> Path:
    runs = sorted(
        [p for p in DEFAULT_INPUT_ROOT.glob("qldtqqq_turning_*") if p.is_dir()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not runs:
        raise FileNotFoundError(f"No qldtqqq_turning_* runs found under {DEFAULT_INPUT_ROOT}")
    return runs[0]


def read_price_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [c.lower() for c in df.columns]
    if "date" not in df:
        raise ValueError(f"{path} has no date column")
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").drop_duplicates("date").set_index("date")
    for col in ("open", "high", "low", "close"):
        if col not in df:
            raise ValueError(f"{path} has no {col} column")
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def read_signal_nav(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").drop_duplicates("date").set_index("date")
    return df


def metrics_from_result(
    result: Mapping[str, pd.Series],
    start: str | None = None,
    end: str | None = None,
) -> dict[str, float | int]:
    ret = result["returns"].copy()
    pos = result["position"].copy()
    entries = result["entries"].copy()
    if start:
        mask = ret.index >= pd.Timestamp(start)
        ret, pos, entries = ret.loc[mask], pos.loc[mask], entries.loc[mask]
    if end:
        mask = ret.index <= pd.Timestamp(end)
        ret, pos, entries = ret.loc[mask], pos.loc[mask], entries.loc[mask]
    ret = ret.dropna()
    if ret.empty:
        return {
            "total_return": np.nan,
            "CAGR": np.nan,
            "MDD": np.nan,
            "Calmar": np.nan,
            "Sharpe": np.nan,
            "Sortino": np.nan,
            "exposure": np.nan,
            "avg_weight": np.nan,
            "trades": 0,
            "years": 0.0,
        }
    nav = (1.0 + ret.fillna(0.0)).cumprod()
    nav.iloc[0] = 1.0
    years = len(ret) / 252.0
    total = float(nav.iloc[-1] - 1.0)
    cagr = (1.0 + total) ** (1.0 / years) - 1.0 if years > 0 and total > -1 else np.nan
    sd = float(ret.std(ddof=0))
    sharpe = float(ret.mean() / sd * math.sqrt(252)) if sd > 0 else np.nan
    downside_sd = float(ret[ret < 0].std(ddof=0))
    sortino = float(ret.mean() / downside_sd * math.sqrt(252)) if downside_sd > 0 else np.nan
    dd = nav / nav.cummax() - 1.0
    mdd = float(dd.min())
    calmar = float(cagr / abs(mdd)) if mdd < 0 and not pd.isna(cagr) else np.nan
    pos_aligned = pos.reindex(ret.index).fillna(0.0)
    return {
        "total_return": total,
        "CAGR": float(cagr),
        "MDD": mdd,
        "Calmar": calmar,
        "Sharpe": sharpe,
        "Sortino": sortino,
        "exposure": float((pos_aligned > 0.01).mean()),
        "avg_weight": float(pos_aligned.mean()),
        "trades": int(entries.reindex(ret.index).fillna(False).sum()),
        "years": years,
    }


def backtest_open_to_open(
    asset: pd.DataFrame,
    target_weight_at_open: pd.Series,
    cost: float,
) -> dict[str, pd.Series]:
    open_price = asset["open"].astype(float).ffill()
    target = target_weight_at_open.reindex(asset.index).ffill().fillna(0.0).clip(0.0, 1.0)
    returns: list[float] = []
    positions: list[float] = []
    prev_weight = 0.0
    prev_open = np.nan
    for dt, wanted in target.items():
        opn = open_price.loc[dt]
        if pd.isna(prev_open) or prev_open <= 0 or pd.isna(opn) or opn <= 0:
            period_ret = 0.0
        else:
            period_ret = prev_weight * (opn / prev_open - 1.0)
        trade = abs(float(wanted) - prev_weight)
        period_ret -= trade * cost
        returns.append(float(period_ret))
        positions.append(float(wanted))
        prev_weight = float(wanted)
        prev_open = opn

    ret_s = pd.Series(returns, index=asset.index, name="returns")
    pos_s = pd.Series(positions, index=asset.index, name="position")
    in_pos = pos_s > 0.01
    prev = in_pos.shift(1).fillna(False).astype(bool)
    entries = in_pos & ~prev
    exits = ~in_pos & prev
    return {
        "returns": ret_s,
        "position": pos_s,
        "entries": entries,
        "exits": exits,
        "value": (1.0 + ret_s.fillna(0.0)).cumprod(),
    }


def buy_hold_result(asset: pd.DataFrame) -> dict[str, pd.Series]:
    ret = asset["open"].astype(float).ffill().pct_change(fill_method=None).fillna(0.0)
    pos = pd.Series(1.0, index=asset.index, name="position")
    entries = pd.Series(False, index=asset.index, name="entries")
    exits = pd.Series(False, index=asset.index, name="exits")
    return {
        "returns": ret,
        "position": pos,
        "entries": entries,
        "exits": exits,
        "value": (1.0 + ret.fillna(0.0)).cumprod(),
    }


def signal_nav_result(nav: pd.DataFrame) -> dict[str, pd.Series]:
    ret = pd.to_numeric(nav["portfolio_return"], errors="coerce").fillna(0.0)
    pos = pd.to_numeric(nav["position_weight_at_open"], errors="coerce").fillna(0.0)
    entries = pd.to_numeric(nav["entry_at_open"], errors="coerce").fillna(0.0).astype(bool)
    exits = pd.to_numeric(nav["exit_at_open"], errors="coerce").fillna(0.0).astype(bool)
    return {
        "returns": ret,
        "position": pos,
        "entries": entries,
        "exits": exits,
        "value": (1.0 + ret.fillna(0.0)).cumprod(),
    }


def vix_state_after_close(vix: pd.DataFrame, trigger_col: str, trigger: float, exit_level: float) -> pd.Series:
    state = False
    out = []
    for _, row in vix.iterrows():
        if not state and float(row[trigger_col]) > trigger:
            state = True
        elif state and float(row["close"]) < exit_level:
            state = False
        out.append(1.0 if state else 0.0)
    return pd.Series(out, index=vix.index, name=f"vix_{trigger_col}_gt_{trigger:g}_exit_{exit_level:g}")


def vix_all_in_weight_at_open(
    asset: pd.DataFrame,
    vix: pd.DataFrame,
    trigger_col: str,
    trigger: float = 35.0,
    exit_level: float = 15.0,
) -> pd.Series:
    state = vix_state_after_close(vix, trigger_col, trigger, exit_level)
    return state.reindex(asset.index).ffill().shift(1).fillna(0.0).rename("target_weight_at_open")


def vix_price_ladder_after_close(
    asset: pd.DataFrame,
    vix: pd.DataFrame,
    trigger_col: str,
    trigger: float = 35.0,
    exit_level: float = 15.0,
) -> pd.Series:
    vix_aligned = vix.reindex(asset.index).ffill()
    state = False
    anchor = np.nan
    max_weight = 0.0
    out = []
    for dt, row in asset.iterrows():
        vrow = vix_aligned.loc[dt]
        price = float(row["close"])
        if not state and float(vrow[trigger_col]) > trigger:
            state = True
            anchor = price
            max_weight = 0.25
        if state:
            drawdown = price / anchor - 1.0 if anchor > 0 else 0.0
            if drawdown <= -0.15:
                max_weight = max(max_weight, 1.00)
            elif drawdown <= -0.10:
                max_weight = max(max_weight, 0.75)
            elif drawdown <= -0.05:
                max_weight = max(max_weight, 0.50)
            wanted = max_weight
            if float(vrow["close"]) < exit_level:
                wanted = 0.0
                state = False
                anchor = np.nan
                max_weight = 0.0
        else:
            wanted = 0.0
        out.append(wanted)
    after_close = pd.Series(out, index=asset.index, name="vix_price_ladder_after_close")
    return after_close.shift(1).fillna(0.0).rename("target_weight_at_open")


def trade_log(result: Mapping[str, pd.Series], label: str, symbol: str) -> pd.DataFrame:
    pos = result["position"].copy()
    nav = result["value"].copy()
    in_pos = pos > 0.01
    entries = in_pos & ~in_pos.shift(1).fillna(False)
    exits = ~in_pos & in_pos.shift(1).fillna(False)
    rows = []
    exit_dates = list(exits[exits].index)
    for entry_dt in entries[entries].index:
        possible_exits = [dt for dt in exit_dates if dt > entry_dt]
        closed = bool(possible_exits)
        exit_dt = possible_exits[0] if closed else nav.index[-1]
        prev_idx = nav.index.get_loc(entry_dt) - 1
        start_nav = float(nav.iloc[prev_idx]) if prev_idx >= 0 else 1.0
        end_nav = float(nav.loc[exit_dt])
        rows.append(
            {
                "symbol": symbol,
                "strategy": label,
                "entry_date": entry_dt.strftime("%Y-%m-%d"),
                "exit_date": exit_dt.strftime("%Y-%m-%d"),
                "closed": closed,
                "bars": int((pos.loc[entry_dt:exit_dt].index.size)),
                "cycle_return": end_nav / start_nav - 1.0 if start_nav > 0 else np.nan,
                "max_weight": float(pos.loc[entry_dt:exit_dt].max()),
            }
        )
    return pd.DataFrame(rows)


def vix_episode_counts(vix: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for col in ("close", "high"):
        for threshold in (35, 40, 50, 80):
            flag = vix[col] > threshold
            starts = flag & ~flag.shift(1).fillna(False)
            episodes = int(starts.sum())
            days = int(flag.sum())
            max_value = float(vix.loc[flag, col].max()) if flag.any() else np.nan
            rows.append(
                {
                    "vix_field": col,
                    "threshold": threshold,
                    "episodes": episodes,
                    "trading_days": days,
                    "max_value": max_value,
                    "first_date": vix.loc[flag].index.min().strftime("%Y-%m-%d") if flag.any() else "",
                    "last_date": vix.loc[flag].index.max().strftime("%Y-%m-%d") if flag.any() else "",
                }
            )
    return pd.DataFrame(rows)


def vix_regime_counts(vix: pd.DataFrame, exit_level: float = 15.0) -> pd.DataFrame:
    rows = []
    for col in ("close", "high"):
        for threshold in (35, 40, 50, 80):
            state = False
            starts = []
            exits = []
            max_values = []
            current_max = np.nan
            for dt, row in vix.iterrows():
                value = float(row[col])
                if not state and value > threshold:
                    state = True
                    starts.append(dt)
                    current_max = value
                elif state:
                    current_max = max(current_max, value)
                if state and float(row["close"]) < exit_level:
                    exits.append(dt)
                    max_values.append(current_max)
                    state = False
                    current_max = np.nan
            if state:
                max_values.append(current_max)
            rows.append(
                {
                    "vix_field": col,
                    "trigger_threshold": threshold,
                    "exit_level_close_lt": exit_level,
                    "regimes": len(starts),
                    "closed_regimes": len(exits),
                    "open_regimes": len(starts) - len(exits),
                    "first_start": starts[0].strftime("%Y-%m-%d") if starts else "",
                    "last_start": starts[-1].strftime("%Y-%m-%d") if starts else "",
                    "max_regime_value": float(np.nanmax(max_values)) if max_values else np.nan,
                }
            )
    return pd.DataFrame(rows)


def fmt_pct(x: float | int | None) -> str:
    if x is None or pd.isna(x):
        return ""
    return f"{float(x):.2%}"


def fmt_num(x: float | int | None, digits: int = 3) -> str:
    if x is None or pd.isna(x):
        return ""
    return f"{float(x):.{digits}f}"


def df_to_markdown(df: pd.DataFrame) -> str:
    if df.empty:
        return "_No rows._"
    text = df.copy()
    text = text.fillna("")
    text = text.astype(str)
    headers = list(text.columns)
    rows = text.values.tolist()
    out = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        out.append("| " + " | ".join(str(v).replace("\n", " ") for v in row) + " |")
    return "\n".join(out)


def build_report(
    run_dir: Path,
    input_run: Path,
    source_run_selection: str,
    reproducibility_warning: str,
    period_metrics: pd.DataFrame,
    trade_summary: pd.DataFrame,
    vix_counts: pd.DataFrame,
    vix_regimes: pd.DataFrame,
    latest_dates: pd.DataFrame,
    canonical: pd.DataFrame,
    zip_path: Path,
) -> str:
    lines: list[str] = []
    lines += [
        "# VIX 35/15 Strategy vs Lab Turning Strategy",
        "",
        f"- Run directory: `{run_dir}`",
        f"- Source QLD/TQQQ run: `{input_run}`",
        f"- Source run selection: `{source_run_selection}`",
        "- Data source: latest qldtqqq updated_data files; VIX source in that run points to Cboe VIX history.",
        "- Execution: signal after close, position adjusted at next open.",
        "- Cost model: one-way 0.20% for all timed strategies; buy-and-hold has no rebalance cost.",
        f"- Research-only warning: {RESEARCH_ONLY_WARNING}",
        f"- Reproducibility warning: {reproducibility_warning}",
        "- Main online rule implementation: VIX close > 35 enters 100% at next open; VIX close < 15 exits at next open.",
        "- Sensitivity: VIX high > 35 all-in; fixed 25/50/75/100 price ladder after VIX close > 35.",
        "- Lab QQQ row is a transfer test using the QLD best timing/weights on QQQ, because the source run has native best rows only for QLD and TQQQ.",
        "",
        "## Data Latest Dates",
        "",
        df_to_markdown(latest_dates),
        "",
        "## Canonical Comparison",
        "",
    ]
    display_cols = [
        "symbol",
        "strategy",
        "period",
        "CAGR",
        "MDD",
        "Calmar",
        "Sharpe",
        "exposure",
        "avg_weight",
        "trades",
    ]
    canon_fmt = canonical[display_cols].copy()
    for col in ("CAGR", "MDD", "exposure", "avg_weight"):
        canon_fmt[col] = canon_fmt[col].map(fmt_pct)
    for col in ("Calmar", "Sharpe"):
        canon_fmt[col] = canon_fmt[col].map(fmt_num)
    lines += [df_to_markdown(canon_fmt), ""]

    lines += [
        "## VIX Threshold Frequency",
        "",
        df_to_markdown(vix_counts),
        "",
        "## VIX Regimes Until Close < 15",
        "",
        df_to_markdown(vix_regimes),
        "",
        "## Trade Cycle Summary",
        "",
    ]
    if trade_summary.empty:
        lines.append("No closed trade cycles found.")
    else:
        ts = trade_summary.copy()
        for col in ("win_rate", "avg_cycle_return", "median_cycle_return", "worst_cycle_return", "best_cycle_return"):
            ts[col] = ts[col].map(fmt_pct)
        lines.append(df_to_markdown(ts))
    lines += [
        "",
        "## Interpretation",
        "",
        "- The online VIX rule is sparse crisis re-entry. It can have high trade win rates because it waits for rare panic and exits only after volatility normalizes, but capital may sit idle for long stretches.",
        "- The lab strategy is a continuous risk-managed Nasdaq trend strategy. It tries to keep partial trend exposure, add on bottom pressure, trim on top pressure, and reduce drawdown with volatility sizing and hard exits.",
        "- The VIX rule is easier to understand and less model-dependent, but the number of independent crisis samples is small. It also depends heavily on surviving the one path where panic keeps worsening.",
        "- The lab strategy has better day-to-day capital use and explicit drawdown control, but it is more complex and has historical-selection risk.",
        "",
        "## Files",
        "",
        "- `reports/comparison_report.md`",
        "- `reports/comparison_metrics.xlsx`",
        "- `strategy_period_metrics.csv`",
        "- `canonical_comparison.csv`",
        "- `trade_log.csv`",
        "- `trade_summary.csv`",
        "- `vix_threshold_counts.csv`",
        "- `vix_regime_counts.csv`",
        f"- Zip: `{zip_path}`",
        "",
    ]
    return "\n".join(lines)


def summarize_trades(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    rows = []
    grouped = trades.groupby(["symbol", "strategy"], dropna=False)
    for (symbol, strategy), g in grouped:
        closed = g[g["closed"]].copy()
        base = closed if not closed.empty else g
        rows.append(
            {
                "symbol": symbol,
                "strategy": strategy,
                "closed_cycles": int(closed.shape[0]),
                "all_cycles": int(g.shape[0]),
                "win_rate": float((base["cycle_return"] > 0).mean()) if not base.empty else np.nan,
                "avg_cycle_return": float(base["cycle_return"].mean()) if not base.empty else np.nan,
                "median_cycle_return": float(base["cycle_return"].median()) if not base.empty else np.nan,
                "worst_cycle_return": float(base["cycle_return"].min()) if not base.empty else np.nan,
                "best_cycle_return": float(base["cycle_return"].max()) if not base.empty else np.nan,
                "avg_bars": float(base["bars"].mean()) if not base.empty else np.nan,
            }
        )
    return pd.DataFrame(rows).sort_values(["symbol", "strategy"])


def make_zip(run_dir: Path, overwrite: bool) -> Path:
    zip_path = run_dir.with_suffix(".zip")
    if zip_path.exists():
        if not overwrite:
            raise FileExistsError(f"Refusing to overwrite existing zip without --overwrite: {zip_path}")
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in run_dir.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(run_dir.parent))
    return zip_path


def planned_outputs(run_dir: Path) -> list[Path]:
    return [run_dir / name for name in PLANNED_OUTPUT_FILES] + [run_dir.with_suffix(".zip")]


def print_dry_run_plan(input_run: Path, source_run_selection: str, run_dir: Path, args: argparse.Namespace) -> None:
    zip_path = run_dir.with_suffix(".zip")
    plan = {
        "status": "DRY_RUN_NO_FILES_WRITTEN",
        "script_name": Path(__file__).name,
        "script_role": SCRIPT_ROLE,
        "formal_mve2_related": False,
        "replace_v82_baseline": False,
        "create_v10": False,
        "source_run_selection": source_run_selection,
        "source_run_path": str(input_run),
        "output_run_dir": str(run_dir),
        "output_zip": str(zip_path),
        "dry_run": True,
        "overwrite": bool(args.overwrite),
        "would_block_without_overwrite": {
            "run_dir_exists": run_dir.exists(),
            "zip_exists": zip_path.exists(),
        },
        "would_read": [
            str(input_run / "updated_data" / f"{symbol}.csv") for symbol in SYMBOLS
        ] + [
            str(input_run / "updated_data" / "_VIX.csv"),
            str(input_run / "QLD_best_signal_nav.csv"),
            str(input_run / "TQQQ_best_signal_nav.csv"),
        ],
        "would_write": [str(path) for path in planned_outputs(run_dir)],
        "reproducibility_warning": (
            LATEST_RUN_REPRO_WARNING
            if source_run_selection == "latest_by_mtime"
            else "Explicit --input-run was provided; source run selection is reproducible."
        ),
        "research_only_warning": RESEARCH_ONLY_WARNING,
    }
    print(json.dumps(plan, indent=2))
    print("DRY_RUN_NO_FILES_WRITTEN")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Compare VIX 35/15 timing against latest QLD/TQQQ lab strategy. "
            "Independent research only; not FORMAL_MVE2, not v8.2 baseline replacement, not v10."
        )
    )
    parser.add_argument("--input-run", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--stamp", default=None)
    parser.add_argument("--cost", type=float, default=0.002)
    parser.add_argument("--dry-run", action="store_true", help="Print input/output plan only; write no files.")
    parser.add_argument("--no-write", action="store_true", help="Alias for --dry-run.")
    parser.add_argument("--overwrite", action="store_true", help="Allow reusing an existing output run dir or zip.")
    args = parser.parse_args()

    source_run_selection = "explicit_input_run" if args.input_run else "latest_by_mtime"
    input_run = args.input_run or latest_turning_run()
    stamp = args.stamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = args.output_root / f"vix_vs_lab_strategy_{stamp}"
    zip_path = run_dir.with_suffix(".zip")
    run_dir_preexisted = run_dir.exists()
    zip_preexisted = zip_path.exists()
    if args.dry_run or args.no_write:
        print_dry_run_plan(input_run, source_run_selection, run_dir, args)
        return
    if run_dir_preexisted and not args.overwrite:
        raise FileExistsError(f"Refusing to overwrite existing output run directory without --overwrite: {run_dir}")
    if zip_preexisted and not args.overwrite:
        raise FileExistsError(f"Refusing to overwrite existing output zip without --overwrite: {zip_path}")

    reports_dir = run_dir / "reports"
    logs_dir = run_dir / "logs"
    reports_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(logs_dir / "run.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    logging.info("Input run: %s", input_run)
    logging.info("Output run: %s", run_dir)
    logging.info("Source run selection: %s", source_run_selection)
    logging.info("Overwrite enabled: %s", bool(args.overwrite))
    logging.info("Output run dir preexisted: %s", run_dir_preexisted)
    logging.info("Output zip preexisted: %s", zip_preexisted)
    if source_run_selection == "latest_by_mtime":
        logging.warning("%s", LATEST_RUN_REPRO_WARNING)
    logging.warning("%s", RESEARCH_ONLY_WARNING)

    data_dir = input_run / "updated_data"
    prices = {symbol: read_price_csv(data_dir / f"{symbol}.csv") for symbol in SYMBOLS}
    vix = read_price_csv(data_dir / "_VIX.csv")
    qld_nav = read_signal_nav(input_run / "QLD_best_signal_nav.csv")
    tqqq_nav = read_signal_nav(input_run / "TQQQ_best_signal_nav.csv")

    latest_dates = pd.DataFrame(
        [
            {
                "series": symbol,
                "first_date": df.index.min().strftime("%Y-%m-%d"),
                "last_date": df.index.max().strftime("%Y-%m-%d"),
                "rows": int(df.shape[0]),
            }
            for symbol, df in {**prices, "VIX": vix}.items()
        ]
    )

    strategies: dict[tuple[str, str], dict[str, pd.Series]] = {}
    for symbol, asset in prices.items():
        strategies[(symbol, "buy_hold")] = buy_hold_result(asset)
        close_weight = vix_all_in_weight_at_open(asset, vix, "close", 35.0, 15.0)
        high_weight = vix_all_in_weight_at_open(asset, vix, "high", 35.0, 15.0)
        ladder_weight = vix_price_ladder_after_close(asset, vix, "close", 35.0, 15.0)
        strategies[(symbol, "online_vix_close35_exit15_allin")] = backtest_open_to_open(asset, close_weight, args.cost)
        strategies[(symbol, "online_vix_high35_exit15_allin")] = backtest_open_to_open(asset, high_weight, args.cost)
        strategies[(symbol, "online_vix_close35_price_ladder")] = backtest_open_to_open(asset, ladder_weight, args.cost)

    strategies[("QLD", "lab_best_native")] = signal_nav_result(qld_nav)
    strategies[("TQQQ", "lab_best_native")] = signal_nav_result(tqqq_nav)
    strategies[("QQQ", "lab_qld_best_timing_transfer")] = backtest_open_to_open(
        prices["QQQ"],
        pd.to_numeric(qld_nav["position_weight_at_open"], errors="coerce").reindex(prices["QQQ"].index).ffill().fillna(0.0),
        args.cost,
    )
    strategies[("QQQ", "lab_tqqq_best_timing_transfer")] = backtest_open_to_open(
        prices["QQQ"],
        pd.to_numeric(tqqq_nav["position_weight_at_open"], errors="coerce").reindex(prices["QQQ"].index).ffill().fillna(0.0),
        args.cost,
    )

    periods = {
        "full": (None, None),
        "wf_2014_latest": (WF_START, None),
        "test_2021_latest": (TEST_START, None),
    }
    metric_rows = []
    for (symbol, strategy), result in strategies.items():
        for period, (start, end) in periods.items():
            m = metrics_from_result(result, start, end)
            metric_rows.append({"symbol": symbol, "strategy": strategy, "period": period, **m})
    period_metrics = pd.DataFrame(metric_rows).sort_values(["symbol", "period", "Calmar"], ascending=[True, True, False])

    canonical_names = {
        "QQQ": {"buy_hold", "online_vix_close35_exit15_allin", "online_vix_close35_price_ladder", "lab_qld_best_timing_transfer"},
        "QLD": {"buy_hold", "online_vix_close35_exit15_allin", "online_vix_close35_price_ladder", "lab_best_native"},
        "TQQQ": {"buy_hold", "online_vix_close35_exit15_allin", "online_vix_close35_price_ladder", "lab_best_native"},
    }
    canonical = period_metrics[
        period_metrics.apply(lambda r: r["strategy"] in canonical_names.get(r["symbol"], set()), axis=1)
    ].copy()
    strategy_order = {
        "buy_hold": 0,
        "online_vix_close35_exit15_allin": 1,
        "online_vix_close35_price_ladder": 2,
        "lab_qld_best_timing_transfer": 3,
        "lab_best_native": 3,
    }
    period_order = {"full": 0, "wf_2014_latest": 1, "test_2021_latest": 2}
    canonical["strategy_order"] = canonical["strategy"].map(strategy_order).fillna(9)
    canonical["period_order"] = canonical["period"].map(period_order).fillna(9)
    canonical = canonical.sort_values(["symbol", "period_order", "strategy_order"]).drop(columns=["strategy_order", "period_order"])

    all_trades = []
    for (symbol, strategy), result in strategies.items():
        if strategy == "buy_hold":
            continue
        all_trades.append(trade_log(result, strategy, symbol))
    trades = pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame()
    trade_summary = summarize_trades(trades)
    vix_counts = vix_episode_counts(vix)
    vix_regimes = vix_regime_counts(vix)

    period_metrics.to_csv(run_dir / "strategy_period_metrics.csv", index=False)
    canonical.to_csv(run_dir / "canonical_comparison.csv", index=False)
    trades.to_csv(run_dir / "trade_log.csv", index=False)
    trade_summary.to_csv(run_dir / "trade_summary.csv", index=False)
    vix_counts.to_csv(run_dir / "vix_threshold_counts.csv", index=False)
    vix_regimes.to_csv(run_dir / "vix_regime_counts.csv", index=False)
    latest_dates.to_csv(run_dir / "data_latest_dates.csv", index=False)

    ranking = (
        period_metrics[period_metrics["period"].eq("test_2021_latest")]
        .sort_values(["symbol", "Calmar", "CAGR"], ascending=[True, False, False])
        .copy()
    )
    ranking.to_csv(run_dir / "ranking_test_2021_latest.csv", index=False)

    xlsx_path = reports_dir / "comparison_metrics.xlsx"
    with pd.ExcelWriter(xlsx_path) as writer:
        canonical.to_excel(writer, sheet_name="canonical", index=False)
        period_metrics.to_excel(writer, sheet_name="all_period_metrics", index=False)
        ranking.to_excel(writer, sheet_name="test_ranking", index=False)
        trade_summary.to_excel(writer, sheet_name="trade_summary", index=False)
        trades.to_excel(writer, sheet_name="trade_log", index=False)
        vix_counts.to_excel(writer, sheet_name="vix_counts", index=False)
        vix_regimes.to_excel(writer, sheet_name="vix_regimes", index=False)
        latest_dates.to_excel(writer, sheet_name="data_dates", index=False)

    zip_placeholder = run_dir.with_suffix(".zip")
    report = build_report(
        run_dir,
        input_run,
        source_run_selection,
        LATEST_RUN_REPRO_WARNING
        if source_run_selection == "latest_by_mtime"
        else "Explicit --input-run was provided; source run selection is reproducible.",
        period_metrics,
        trade_summary,
        vix_counts,
        vix_regimes,
        latest_dates,
        canonical,
        zip_placeholder,
    )
    (reports_dir / "comparison_report.md").write_text(report, encoding="utf-8")

    summary = {
        "script_name": Path(__file__).name,
        "script_role": SCRIPT_ROLE,
        "formal_mve2_related": False,
        "replace_v82_baseline": False,
        "create_v10": False,
        "run_dir": str(run_dir),
        "zip_path": str(zip_placeholder),
        "input_run": str(input_run),
        "source_run_selection": source_run_selection,
        "source_run_path": str(input_run),
        "dry_run": False,
        "overwrite": bool(args.overwrite),
        "overwrite_behavior": {
            "run_dir_preexisted": bool(run_dir_preexisted),
            "zip_preexisted": bool(zip_preexisted),
            "zip_recreated": bool(args.overwrite and zip_preexisted),
            "output_root_cleared": False,
            "historical_run_deleted": False,
        },
        "reproducibility_warning": (
            LATEST_RUN_REPRO_WARNING
            if source_run_selection == "latest_by_mtime"
            else "Explicit --input-run was provided; source run selection is reproducible."
        ),
        "research_only_warning": RESEARCH_ONLY_WARNING,
        "latest_data": latest_dates.to_dict(orient="records"),
        "cost": args.cost,
        "canonical_test_rows": canonical[canonical["period"].eq("test_2021_latest")].to_dict(orient="records"),
        "classification": "comparison_only_research_packet",
        "strict_walk_forward": {
            "lab_strategy": "passed in source qldtqqq run for QLD/TQQQ ML probability folds",
            "online_vix_rule": "not applicable as a fixed rule; threshold choice remains sparse-event historical-selection risk",
        },
    }
    (run_dir / "RUN_SUMMARY.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    run_summary_md = [
        "# RUN SUMMARY",
        "",
        f"- Goal: compare online VIX 35/15 panic-buy rule with latest lab QLD/TQQQ turning strategy.",
        f"- Input run: `{input_run}`",
        f"- Source run selection: `{source_run_selection}`",
        f"- Run directory: `{run_dir}`",
        f"- Cost: `{args.cost:.2%}` one-way for timed strategies.",
        f"- Main conclusion: see `reports/comparison_report.md` and `canonical_comparison.csv`.",
        "- Classification: `comparison_only_research_packet`.",
        f"- Research-only warning: {RESEARCH_ONLY_WARNING}",
        f"- Reproducibility warning: {summary['reproducibility_warning']}",
        "- Strict walk-forward: lab source has walk-forward ML folds for QLD/TQQQ; online VIX rule has no training loop and should not be counted as strict WF-passed.",
        "",
    ]
    (run_dir / "RUN_SUMMARY.md").write_text("\n".join(run_summary_md), encoding="utf-8")

    next_steps = [
        "# NEXT STEPS",
        "",
        "1. If this comparison is used in the main US-stock-selection track, keep it as an ETF timing side packet; do not let it replace the frozen v8.2 baseline.",
        "2. Add an intraday/high-based VIX variant only if intraday execution data is available; daily close/high tests are not the same as live threshold alerts.",
        "3. Stress-test the VIX rule with delayed entry, partial fills, and no averaging down, because sparse crisis entries are sensitive to one or two events.",
        "4. For a tradable ETF sleeve, prefer the lab strategy only after reviewing 2025-2026 churn and cost sensitivity; otherwise keep it as research-only.",
        "",
    ]
    (run_dir / "NEXT_STEPS.md").write_text("\n".join(next_steps), encoding="utf-8")

    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "script_name": Path(__file__).name,
        "script_role": SCRIPT_ROLE,
        "formal_mve2_related": False,
        "replace_v82_baseline": False,
        "create_v10": False,
        "script": str(Path(__file__).relative_to(ROOT)),
        "source_run_selection": source_run_selection,
        "source_run_path": str(input_run),
        "input_run": str(input_run),
        "dry_run": False,
        "overwrite": bool(args.overwrite),
        "overwrite_behavior": summary["overwrite_behavior"],
        "reproducibility_warning": summary["reproducibility_warning"],
        "research_only_warning": RESEARCH_ONLY_WARNING,
        "outputs": sorted(str(p.relative_to(run_dir)) for p in run_dir.rglob("*") if p.is_file()),
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    zip_path = make_zip(run_dir, bool(args.overwrite))
    report = report.replace(str(zip_placeholder), str(zip_path))
    (reports_dir / "comparison_report.md").write_text(report, encoding="utf-8")
    summary["zip_path"] = str(zip_path)
    (run_dir / "RUN_SUMMARY.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    logging.info("Wrote zip: %s", zip_path)
    print(str(run_dir))
    print(str(zip_path))


if __name__ == "__main__":
    main()
