"""Walk-forward stability checks for the selected TQQQ/QLD strategies."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Mapping

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.research_us_leveraged_etf_full_strategy import (  # noqa: E402
    CONTEXT_ETFS,
    CORE_SYMBOLS,
    Candidate,
    dual_thrust_signal,
    load_local_symbol,
    pct,
    write_json,
)
from src.strategies.safety import backtest_binary_position, compute_performance_metrics  # noqa: E402


OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "us_leveraged_etf_walk_forward"
FEE = 0.001
RISK_FREE = 0.02


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def checkpoint(run_dir: Path, stage: str, payload: Mapping[str, object], next_step: str) -> None:
    body = {
        "stage": stage,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "payload": payload,
        "next_step": next_step,
    }
    write_json(run_dir / f"checkpoint_{stage}.json", body)
    lines = [
        f"# Walk-Forward Checkpoint {stage}",
        "",
        f"- Time: {body['time']}",
        f"- Next step: {next_step}",
        "",
        "```json",
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        "```",
        "",
    ]
    (run_dir / f"checkpoint_{stage}.md").write_text("\n".join(lines), encoding="utf-8")


def load_data() -> dict[str, pd.DataFrame]:
    symbols = list(dict.fromkeys([*CORE_SYMBOLS, *CONTEXT_ETFS]))
    data = {symbol: load_local_symbol(symbol) for symbol in symbols}
    return {symbol: frame for symbol, frame in data.items() if not frame.empty}


def calendar_folds(
    eval_start: pd.Timestamp,
    latest: pd.Timestamp,
    train_years: int,
    first_test_year: int | None = None,
) -> list[dict[str, pd.Timestamp]]:
    min_year = eval_start.year + train_years
    start_year = max(first_test_year or min_year, min_year)
    folds = []
    for year in range(start_year, latest.year + 1):
        test_start = pd.Timestamp(f"{year}-01-01")
        test_end = min(pd.Timestamp(f"{year}-12-31"), latest)
        train_start = test_start - pd.DateOffset(years=train_years)
        train_end = test_start - pd.Timedelta(days=1)
        if train_start < eval_start or test_start > latest:
            continue
        folds.append(
            {
                "year": year,
                "train_start": train_start,
                "train_end": train_end,
                "test_start": test_start,
                "test_end": test_end,
            }
        )
    return folds


def score_metrics(metrics: Mapping[str, float]) -> float:
    if pd.isna(metrics.get("sharpe", np.nan)) or pd.isna(metrics.get("calmar", np.nan)):
        return -999.0
    calmar = float(np.clip(metrics.get("calmar", np.nan), -1.0, 2.5))
    sharpe = float(np.clip(metrics.get("sharpe", np.nan), -2.0, 2.5))
    annual = float(metrics.get("annual_return", 0.0))
    max_dd = float(metrics.get("max_drawdown", 0.0))
    exposure = float(metrics.get("exposure", 0.0))
    score = 0.35 * calmar + 0.30 * sharpe + 0.25 * annual
    if max_dd < -0.45:
        score -= 0.35 * abs(max_dd + 0.45)
    if exposure < 0.10:
        score -= 0.50 * (0.10 - exposure)
    return float(score)


def evaluate_signal(
    asset: pd.DataFrame,
    signal: pd.Series,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> tuple[dict[str, float], pd.Series, pd.Series]:
    nav, returns, position = backtest_binary_position(asset, signal, cost_rate=FEE)
    metrics = compute_performance_metrics(returns, start, end, risk_free=RISK_FREE)
    segment = returns.loc[start:end].dropna()
    pos_segment = position.loc[start:end].dropna()
    metrics["trades"] = float(pos_segment.diff().abs().fillna(0).sum())
    metrics["trades_per_year"] = float(metrics["trades"] / max(len(segment) / 252.0, 1e-9))
    return metrics, returns, position


def metrics_to_row(prefix: str, metrics: Mapping[str, float]) -> dict[str, float]:
    return {f"{prefix}_{key}": value for key, value in metrics.items()}


def return_skew_panel(data: Mapping[str, pd.DataFrame], window: int) -> pd.DataFrame:
    values = {}
    for symbol, frame in data.items():
        if symbol == "_VIX":
            continue
        values[symbol] = frame["close"].pct_change(fill_method=None).rolling(window).skew()
    return pd.DataFrame(values).sort_index()


def skew_cross_section_signal(
    panel: pd.DataFrame,
    target: str,
    direction: str,
    top_q: float,
    index: pd.Index,
    name: str,
) -> pd.Series:
    ranks = panel.reindex(index).rank(axis=1, pct=True)
    good = ranks[target] if direction == "high" else 1.0 - ranks[target]
    return (good >= 1.0 - top_q).astype(float).rename(name)


def param_key(params: Mapping[str, object]) -> str:
    return ",".join(f"{key}={params[key]}" for key in sorted(params))


def run_walk_forward(
    name: str,
    symbol: str,
    asset: pd.DataFrame,
    folds: list[dict[str, pd.Timestamp]],
    param_grid: list[dict[str, object]],
    fixed_params: dict[str, object],
    signal_builder: Callable[[dict[str, object]], pd.Series],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    selected_oos_returns = []
    fixed_oos_returns = []
    signal_cache: dict[str, pd.Series] = {}

    def get_signal(params: dict[str, object]) -> pd.Series:
        key = param_key(params)
        if key not in signal_cache:
            signal_cache[key] = signal_builder(params)
        return signal_cache[key]

    for fold in folds:
        train_scores = []
        for params in param_grid:
            signal = get_signal(params)
            train_metrics, _, _ = evaluate_signal(
                asset,
                signal,
                fold["train_start"],
                fold["train_end"],
            )
            train_scores.append((score_metrics(train_metrics), params, train_metrics))
        train_scores.sort(key=lambda item: item[0], reverse=True)
        selected_score, selected_params, selected_train_metrics = train_scores[0]

        selected_signal = get_signal(selected_params)
        fixed_signal = get_signal(fixed_params)
        selected_test_metrics, selected_returns, _ = evaluate_signal(
            asset,
            selected_signal,
            fold["test_start"],
            fold["test_end"],
        )
        fixed_test_metrics, fixed_returns, _ = evaluate_signal(
            asset,
            fixed_signal,
            fold["test_start"],
            fold["test_end"],
        )
        selected_oos_returns.append(selected_returns.loc[fold["test_start"] : fold["test_end"]])
        fixed_oos_returns.append(fixed_returns.loc[fold["test_start"] : fold["test_end"]])

        common = {
            "strategy_group": name,
            "symbol": symbol,
            "year": fold["year"],
            "train_start": fold["train_start"].strftime("%Y-%m-%d"),
            "train_end": fold["train_end"].strftime("%Y-%m-%d"),
            "test_start": fold["test_start"].strftime("%Y-%m-%d"),
            "test_end": fold["test_end"].strftime("%Y-%m-%d"),
        }
        rows.append(
            {
                **common,
                "mode": "walk_forward_selected",
                "params": param_key(selected_params),
                "train_score": selected_score,
                **metrics_to_row("train", selected_train_metrics),
                **metrics_to_row("test", selected_test_metrics),
            }
        )
        rows.append(
            {
                **common,
                "mode": "fixed_current_best",
                "params": param_key(fixed_params),
                "train_score": np.nan,
                **metrics_to_row("test", fixed_test_metrics),
            }
        )

    fold_df = pd.DataFrame(rows)
    stitched_rows = []
    for mode, returns_list in (
        ("walk_forward_selected", selected_oos_returns),
        ("fixed_current_best", fixed_oos_returns),
    ):
        stitched = pd.concat(returns_list).sort_index()
        stitched = stitched[~stitched.index.duplicated(keep="last")]
        stitched_metrics = compute_performance_metrics(
            stitched,
            stitched.index.min(),
            stitched.index.max(),
            risk_free=RISK_FREE,
        )
        subset = fold_df[(fold_df["strategy_group"] == name) & (fold_df["mode"] == mode)]
        param_counts = Counter(subset["params"])
        stitched_rows.append(
            {
                "strategy_group": name,
                "symbol": symbol,
                "mode": mode,
                "folds": int(len(subset)),
                "positive_year_rate": float((subset["test_annual_return"] > 0).mean()),
                "mean_test_annual_return": float(subset["test_annual_return"].mean()),
                "median_test_annual_return": float(subset["test_annual_return"].median()),
                "mean_test_sharpe": float(subset["test_sharpe"].mean()),
                "mean_test_calmar": float(subset["test_calmar"].mean()),
                "worst_test_max_drawdown": float(subset["test_max_drawdown"].min()),
                "mean_test_exposure": float(subset["test_exposure"].mean()),
                "stitched_annual_return": stitched_metrics["annual_return"],
                "stitched_total_return": stitched_metrics["total_return"],
                "stitched_sharpe": stitched_metrics["sharpe"],
                "stitched_max_drawdown": stitched_metrics["max_drawdown"],
                "most_common_params": "; ".join(
                    f"{key} ({count})" for key, count in param_counts.most_common(4)
                ),
            }
        )
    return fold_df, pd.DataFrame(stitched_rows)


def write_report(run_dir: Path, summary: pd.DataFrame, folds: pd.DataFrame) -> None:
    lines = [
        f"Run dir: {run_dir}",
        "Method: 5-year rolling train, next calendar-year out-of-sample test.",
        f"Fee: one-way {FEE:.2%}; signal after close, rebalance next open.",
        "",
        "## Summary",
        "",
        "| strategy | mode | folds | positive years | stitched annual | stitched maxDD | mean OOS annual | worst OOS maxDD | common params |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for _, row in summary.iterrows():
        lines.append(
            "| {strategy} | {mode} | {folds} | {pos} | {ann} | {dd} | {mean_ann} | {worst_dd} | {params} |".format(
                strategy=row["strategy_group"],
                mode=row["mode"],
                folds=int(row["folds"]),
                pos=pct(row["positive_year_rate"]),
                ann=pct(row["stitched_annual_return"]),
                dd=pct(row["stitched_max_drawdown"]),
                mean_ann=pct(row["mean_test_annual_return"]),
                worst_dd=pct(row["worst_test_max_drawdown"]),
                params=str(row["most_common_params"]).replace("|", "/"),
            )
        )
    lines += [
        "",
        "## Notes",
        "",
        "- `walk_forward_selected` means each fold selects parameters using only the prior 5 years, then tests the next year.",
        "- `fixed_current_best` means the exact parameter from the main report is held fixed through all folds.",
        "- Stronger stability means positive-year rate is high, stitched drawdown is acceptable, and selected params cluster near the reported fixed params.",
        "",
        "## Files",
        "",
        "- `walk_forward_fold_results.csv`",
        "- `walk_forward_summary.csv`",
        "- `checkpoint_01_data.json/md`",
        "- `checkpoint_02_results.json/md`",
    ]
    (run_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-name", default=f"wf_us_{now_stamp()}")
    parser.add_argument("--train-years", type=int, default=5)
    parser.add_argument("--first-test-year", type=int, default=2016)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_dir = OUTPUT_ROOT / args.run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    data = load_data()
    latest = min(data["TQQQ"].index.max(), data["QLD"].index.max(), data["QQQ"].index.max())
    checkpoint(
        run_dir,
        "01_data",
        {
            "symbols": sorted(data),
            "latest_common_target_date": latest.strftime("%Y-%m-%d"),
            "train_years": args.train_years,
            "first_test_year": args.first_test_year,
        },
        "Run rolling train/test folds for selected candidates.",
    )

    all_folds = []
    all_summaries = []

    dual_grid = [
        {"window": window, "k": k}
        for window in (10, 20, 40, 60, 80)
        for k in (0.2, 0.3, 0.4, 0.5, 0.7)
    ]
    tqqq_folds = calendar_folds(
        pd.Timestamp("2011-02-23"),
        latest,
        args.train_years,
        args.first_test_year,
    )
    tqqq_fold_df, tqqq_summary = run_walk_forward(
        "TQQQ_QQQ_DualThrust",
        "TQQQ",
        data["TQQQ"],
        tqqq_folds,
        dual_grid,
        {"window": 40, "k": 0.3},
        lambda params: dual_thrust_signal(
            data["QQQ"],
            int(params["window"]),
            float(params["k"]),
            f"qqq_dual_thrust_w{params['window']}_k{params['k']}",
        ).reindex(data["TQQQ"].index).ffill().fillna(0.0),
    )
    all_folds.append(tqqq_fold_df)
    all_summaries.append(tqqq_summary)

    qld_folds = calendar_folds(
        pd.Timestamp("2007-07-05"),
        latest,
        args.train_years,
        args.first_test_year,
    )
    qld_dual_fold_df, qld_dual_summary = run_walk_forward(
        "QLD_Asset_DualThrust",
        "QLD",
        data["QLD"],
        qld_folds,
        dual_grid,
        {"window": 40, "k": 0.3},
        lambda params: dual_thrust_signal(
            data["QLD"],
            int(params["window"]),
            float(params["k"]),
            f"qld_dual_thrust_w{params['window']}_k{params['k']}",
        ),
    )
    all_folds.append(qld_dual_fold_df)
    all_summaries.append(qld_dual_summary)

    skew_cache: dict[int, pd.DataFrame] = {}

    def skew_builder(params: dict[str, object]) -> pd.Series:
        window = int(params["window"])
        if window not in skew_cache:
            skew_cache[window] = return_skew_panel(data, window)
        return skew_cross_section_signal(
            skew_cache[window],
            "QLD",
            str(params["direction"]),
            float(params["top_q"]),
            data["QLD"].index,
            f"qld_skew_w{window}_{params['direction']}_top{params['top_q']}",
        )

    skew_grid = [
        {"window": window, "direction": direction, "top_q": top_q}
        for window in (40, 60, 90, 120)
        for direction in ("high", "low")
        for top_q in (0.25, 0.35, 0.50)
    ]
    qld_skew_fold_df, qld_skew_summary = run_walk_forward(
        "QLD_ReturnSkew_CS",
        "QLD",
        data["QLD"],
        qld_folds,
        skew_grid,
        {"window": 60, "direction": "high", "top_q": 0.35},
        skew_builder,
    )
    all_folds.append(qld_skew_fold_df)
    all_summaries.append(qld_skew_summary)

    folds = pd.concat(all_folds, ignore_index=True)
    summary = pd.concat(all_summaries, ignore_index=True)
    folds.to_csv(run_dir / "walk_forward_fold_results.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(run_dir / "walk_forward_summary.csv", index=False, encoding="utf-8-sig")
    checkpoint(
        run_dir,
        "02_results",
        {
            "fold_rows": int(len(folds)),
            "summary_rows": int(len(summary)),
            "summary": summary.to_dict("records"),
        },
        "Review report.md and compare fixed vs walk-forward selected stability.",
    )
    write_report(run_dir, summary, folds)
    print(run_dir)


if __name__ == "__main__":
    main()
