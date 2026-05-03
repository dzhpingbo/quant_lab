"""Search 588200 TD9 overlay strategies with technical and VIX filters."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from longrun_588200_factor_strategy_search import (  # noqa: E402
    DEFAULT_ASTOCK_ROOT,
    TARGET_CODE,
    aggregate_metrics,
    build_breadth_features,
    buy_hold_returns,
    factor_breadth_features,
    load_etfs,
    load_price_csv,
    load_stock_pool,
    select_similar_etfs,
)
from src.strategies.etf_588200 import (  # noqa: E402
    TD9ComboSpec,
    build_td9_combo_cache as build_cache,
    make_td9_combo_specs as make_specs,
    td9_combo_signal_from_cache as signal_from_cache,
    td9_combo_spec_from_row as spec_from_row,
)
from src.strategies.safety import (  # noqa: E402
    backtest_binary_position,
    compute_performance_metrics,
)

DEFAULT_VIX_PATH = (
    PROJECT_ROOT
    / "data"
    / "external"
    / "legacy_quant"
    / "NSDQStock"
    / "19800101_20260404"
    / "_VIX.csv"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="588200 TD9 + indicator combination search.")
    parser.add_argument("--astock-root", default=str(DEFAULT_ASTOCK_ROOT))
    parser.add_argument("--target", default=TARGET_CODE)
    parser.add_argument("--start", default="2022-10-26")
    parser.add_argument("--train-end", default="2024-12-31")
    parser.add_argument("--end", default="2026-04-08")
    parser.add_argument("--max-similar-etfs", type=int, default=18)
    parser.add_argument("--min-overlap", type=int, default=180)
    parser.add_argument("--min-corr", type=float, default=0.45)
    parser.add_argument("--cost-rate", type=float, default=0.001)
    parser.add_argument("--risk-free", type=float, default=0.02)
    parser.add_argument("--checkpoint-every", type=int, default=100)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--run-dir", default=None)
    parser.add_argument("--vix-path", default=str(DEFAULT_VIX_PATH))
    parser.add_argument("--output-dir", default=str(PROJECT_ROOT / "outputs" / "588200_td9_indicator_combo"))
    return parser.parse_args()


def load_vix(path: Path, index: pd.Index) -> Tuple[pd.DataFrame, Optional[str]]:
    if not path.exists():
        return pd.DataFrame(index=index), None
    raw = load_price_csv(path)
    close = raw["close"].rename("vix_close").reindex(index).ffill()
    out = pd.DataFrame(index=index)
    out["vix_close"] = close
    out["vix_ma20"] = close.rolling(20).mean()
    out["vix_chg5"] = close.pct_change(5, fill_method=None)
    return out, raw.index.max().date().isoformat()


def evaluate_spec(
    spec: TD9ComboSpec,
    selected_codes: Iterable[str],
    etfs: Dict[str, pd.DataFrame],
    caches: Dict[str, Dict[str, object]],
    start: pd.Timestamp,
    train_end: pd.Timestamp,
    test_start: pd.Timestamp,
    end: pd.Timestamp,
    cost_rate: float,
    risk_free: float,
) -> Dict[str, object]:
    train_rows = []
    test_rows = []
    for code in selected_codes:
        desired = signal_from_cache(caches[code], spec)
        _nav, returns, _position = backtest_binary_position(etfs[code].loc[start:end].copy(), desired, cost_rate)
        train = compute_performance_metrics(returns, start, train_end, risk_free)
        test = compute_performance_metrics(returns, test_start, end, risk_free)
        train["code"] = code
        test["code"] = code
        train_rows.append(train)
        test_rows.append(test)
    row: Dict[str, object] = asdict(spec)
    row["strategy"] = spec.name
    row.update(aggregate_metrics(train_rows, "pool_train"))
    row.update(aggregate_metrics(test_rows, "pool_test"))
    return row


def flatten(prefix: str, metrics: Dict[str, float]) -> Dict[str, float]:
    return {f"{prefix}_{key}": value for key, value in metrics.items()}


def robust_score(row: pd.Series) -> float:
    score = float(row.get("target_test_sharpe", -999.0))
    score += 0.35 * float(row.get("pool_test_median_sharpe", 0.0))
    score += 0.20 * float(row.get("target_train_sharpe", 0.0))
    drawdown = row.get("target_test_max_drawdown", np.nan)
    if pd.notna(drawdown):
        score -= max(0.0, abs(float(drawdown)) - 0.16)
    if row.get("target_test_exposure", 1.0) < 0.08:
        score -= 0.30
    return score


def trade_log(asset: pd.DataFrame, desired: pd.Series) -> pd.DataFrame:
    idx = list(desired.index)
    events = [(dt, int(desired.loc[dt])) for dt in desired.index[desired.diff().fillna(desired) != 0]]
    rows = []
    entry = None
    for signal_dt, state in events:
        pos = idx.index(signal_dt)
        exec_dt = idx[pos + 1] if pos + 1 < len(idx) else None
        signal_close = float(asset.loc[signal_dt, "close"])
        exec_open = float(asset.loc[exec_dt, "open"]) if exec_dt is not None else np.nan
        if state == 1:
            entry = {
                "entry_signal_date": signal_dt.date().isoformat(),
                "entry_exec_date": exec_dt.date().isoformat() if exec_dt is not None else "",
                "entry_signal_close": signal_close,
                "entry_open": exec_open,
            }
        elif entry is not None:
            gross = exec_open / entry["entry_open"] - 1 if entry["entry_open"] and exec_dt is not None else np.nan
            rows.append(
                {
                    **entry,
                    "exit_signal_date": signal_dt.date().isoformat(),
                    "exit_exec_date": exec_dt.date().isoformat() if exec_dt is not None else "",
                    "exit_signal_close": signal_close,
                    "exit_open": exec_open,
                    "gross_return": gross,
                    "net_approx": gross - 0.002 if pd.notna(gross) else np.nan,
                }
            )
            entry = None
    return pd.DataFrame(rows)


def load_checkpoint(path: Path) -> Tuple[List[Dict[str, object]], set[str]]:
    if not path.exists():
        return [], set()
    df = pd.read_csv(path)
    if df.empty:
        return [], set()
    return df.to_dict("records"), set(df["strategy"].astype(str))


def main() -> None:
    args = parse_args()
    start = pd.to_datetime(args.start)
    train_end = pd.to_datetime(args.train_end)
    test_start = train_end + pd.Timedelta(days=1)
    end = pd.to_datetime(args.end)
    run_dir = Path(args.run_dir) if args.run_dir else Path(args.output_dir) / f"td9_combo_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    run_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = run_dir / "strategy_summary_checkpoint.csv"

    print("Loading data...", flush=True)
    astock_root = Path(args.astock_root)
    etfs = load_etfs(astock_root)
    stocks, missing = load_stock_pool(astock_root)
    stocks = {code: df.loc[start:end].copy() for code, df in stocks.items()}
    breadth = build_breadth_features(stocks)
    factor_breadths, _corr = factor_breadth_features(stocks)
    selected = select_similar_etfs(etfs, args.target, start, train_end, args.min_overlap, args.min_corr, args.max_similar_etfs)
    selected_codes = selected["code"].tolist()
    specs = make_specs(factor_breadths)
    target_asset = etfs[args.target].loc[start:end].copy()
    vix, vix_last_date = load_vix(Path(args.vix_path), target_asset.index)

    print(f"ETF series loaded: {len(etfs)}", flush=True)
    print(f"Stock pool loaded: {len(stocks)}, missing: {len(missing)}", flush=True)
    print(f"Similar ETFs: {len(selected_codes)}", flush=True)
    print(f"Strategy specs: {len(specs)}", flush=True)
    print(f"VIX latest date: {vix_last_date}", flush=True)
    print("Building signal cache...", flush=True)
    caches = {
        code: build_cache(etfs[code].loc[start:end].copy(), breadth, factor_breadths, vix, specs)
        for code in selected_codes
    }
    caches[args.target] = build_cache(target_asset, breadth, factor_breadths, vix, specs)

    print("Stage 1: target-only scan...", flush=True)
    target_rows = []
    for i, spec in enumerate(specs, start=1):
        desired = signal_from_cache(caches[args.target], spec)
        _nav, target_returns, _position = backtest_binary_position(target_asset, desired, args.cost_rate)
        row: Dict[str, object] = asdict(spec)
        row["strategy"] = spec.name
        row.update(flatten("target_train", compute_performance_metrics(target_returns, start, train_end, args.risk_free)))
        row.update(flatten("target_test", compute_performance_metrics(target_returns, test_start, end, args.risk_free)))
        row.update(flatten("target_full", compute_performance_metrics(target_returns, start, end, args.risk_free)))
        target_rows.append(row)
        if i % 1000 == 0 or i == len(specs):
            print(f"Target scan: {i}/{len(specs)}", flush=True)

    target_summary = pd.DataFrame(target_rows).sort_values(
        ["target_test_sharpe", "target_test_annual_return"],
        ascending=False,
    ).reset_index(drop=True)
    target_stage_path = run_dir / "target_only_stage.csv"
    target_summary.to_csv(target_stage_path, index=False, encoding="utf-8-sig")
    stable_target = target_summary[
        (target_summary["target_train_sharpe"] > 0)
        & (target_summary["target_test_sharpe"] > 0)
        & (target_summary["target_test_exposure"] >= 0.08)
    ]
    pool_names = list(dict.fromkeys(
        target_summary.head(1500)["strategy"].tolist()
        + stable_target.head(1000)["strategy"].tolist()
    ))
    spec_by_name = {spec.name: spec for spec in specs}
    target_by_name = {str(row["strategy"]): row for row in target_summary.to_dict("records")}
    pool_specs = [spec_by_name[name] for name in pool_names if name in spec_by_name]

    print(f"Stage 2: pool robustness scan for {len(pool_specs)} candidates...", flush=True)
    rows, done = load_checkpoint(checkpoint_path) if args.resume else ([], set())
    remaining = [spec for spec in pool_specs if spec.name not in done]
    for i, spec in enumerate(remaining, start=1):
        row = evaluate_spec(spec, selected_codes, etfs, caches, start, train_end, test_start, end, args.cost_rate, args.risk_free)
        row.update(target_by_name[spec.name])
        row["robust_score"] = robust_score(pd.Series(row))
        rows.append(row)
        if args.checkpoint_every > 0 and (i % args.checkpoint_every == 0 or i == len(remaining)):
            pd.DataFrame(rows).to_csv(checkpoint_path, index=False, encoding="utf-8-sig")
            print(f"Checkpoint saved: {len(rows)}/{len(pool_specs)} -> {checkpoint_path}", flush=True)

    summary = pd.DataFrame(rows).sort_values(["target_test_sharpe", "target_test_annual_return"], ascending=False).reset_index(drop=True)
    robust = summary[
        (summary["pool_train_median_sharpe"] > 0)
        & (summary["pool_test_median_sharpe"] > 0)
        & (summary["target_train_sharpe"] > 0)
        & (summary["target_test_sharpe"] > 0)
        & (summary["target_test_exposure"] >= 0.08)
    ].copy()
    robust = robust.sort_values(["robust_score", "target_test_sharpe"], ascending=False).reset_index(drop=True)
    best = summary.iloc[0]
    robust_best = robust.iloc[0] if not robust.empty else best
    best_spec = spec_from_row(best)

    best_desired = signal_from_cache(caches[args.target], best_spec)
    nav, returns, position = backtest_binary_position(target_asset, best_desired, args.cost_rate)
    hold_returns = buy_hold_returns(target_asset)
    trades = trade_log(target_asset, best_desired)
    out_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary_path = run_dir / f"strategy_summary_{out_ts}.csv"
    signal_path = run_dir / f"target_588200_signal_{out_ts}.csv"
    trades_path = run_dir / f"target_588200_trades_{out_ts}.csv"
    config_path = run_dir / f"best_config_{out_ts}.json"
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(
        {
            "open": target_asset["open"],
            "close": target_asset["close"],
            "desired_after_close": best_desired,
            "position_next_open": position,
            "strategy_return": returns,
            "strategy_nav": nav,
            "buy_hold_nav": (1 + hold_returns).cumprod(),
            "vix_close": vix["vix_close"] if "vix_close" in vix else np.nan,
        }
    ).to_csv(signal_path, index=True, index_label="date", encoding="utf-8-sig")
    trades.to_csv(trades_path, index=False, encoding="utf-8-sig")
    last_date = best_desired.index[-1]
    latest = {
        "signal_date": last_date.date().isoformat(),
        "close": float(target_asset.loc[last_date, "close"]),
        "next_action": "BUY_OR_HOLD_588200" if bool(best_desired.loc[last_date]) else "EMPTY_OR_SELL_588200",
    }
    config = {
        "target_best_strategy": asdict(best_spec),
        "robust_strategy": asdict(spec_from_row(robust_best)),
        "latest_signal": latest,
        "candidate_count": int(len(specs)),
        "pool_eval_count": int(len(summary)),
        "selected_etfs": selected_codes,
        "missing_stock_codes": missing,
        "vix_path": str(Path(args.vix_path)),
        "vix_last_date": vix_last_date,
        "summary": str(summary_path),
        "target_only_stage": str(target_stage_path),
        "signal": str(signal_path),
        "trades": str(trades_path),
        "checkpoint": str(checkpoint_path),
    }
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

    hold_test = compute_performance_metrics(hold_returns, test_start, end, args.risk_free)
    print("\nTD9 indicator combo search completed", flush=True)
    print(f"best_strategy: {best_spec.name}", flush=True)
    print(f"candidate_count: {len(specs)}", flush=True)
    print(f"pool_eval_count: {len(summary)}", flush=True)
    print(f"588200 test annual return: {best['target_test_annual_return'] * 100:.2f}%", flush=True)
    print(f"588200 test Sharpe: {best['target_test_sharpe']:.3f}", flush=True)
    print(f"588200 test max drawdown: {best['target_test_max_drawdown'] * 100:.2f}%", flush=True)
    print(f"588200 test exposure: {best['target_test_exposure'] * 100:.2f}%", flush=True)
    print(f"robust_strategy: {robust_best['strategy']}", flush=True)
    print(f"robust test annual return: {robust_best['target_test_annual_return'] * 100:.2f}%", flush=True)
    print(f"robust test Sharpe: {robust_best['target_test_sharpe']:.3f}", flush=True)
    print(f"robust test max drawdown: {robust_best['target_test_max_drawdown'] * 100:.2f}%", flush=True)
    print(f"buy-hold test annual return: {hold_test['annual_return'] * 100:.2f}%", flush=True)
    print(f"buy-hold test Sharpe: {hold_test['sharpe']:.3f}", flush=True)
    print(f"buy-hold test max drawdown: {hold_test['max_drawdown'] * 100:.2f}%", flush=True)
    print(f"latest plan: {latest['next_action']} as of {latest['signal_date']}", flush=True)
    print(f"summary: {summary_path}", flush=True)
    print(f"config: {config_path}", flush=True)


if __name__ == "__main__":
    main()
