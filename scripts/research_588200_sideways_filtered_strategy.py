"""Search 588200 trend strategies with sideways-market filters."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List

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
    load_etfs,
    load_stock_pool,
    markdown_table,
    pct,
    select_similar_etfs,
)
from src.strategies.etf_588200 import (  # noqa: E402
    make_regime_filtered_ma_specs as make_specs,
    regime_filtered_ma_spec_from_row as spec_from_row,
    regime_filtered_signal_for as signal_for,
)
from src.strategies.safety import (  # noqa: E402
    RegimeFilteredMASpec,
    backtest_binary_position,
    compute_performance_metrics,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="588200 sideways-filtered trend strategy search.")
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
    parser.add_argument(
        "--output-dir",
        default=str(PROJECT_ROOT / "outputs" / "588200_sideways_filtered_strategy"),
    )
    return parser.parse_args()


def trade_log(asset: pd.DataFrame, desired: pd.Series) -> pd.DataFrame:
    idx = list(desired.index)
    changes = desired.diff().fillna(desired)
    events = [(dt, int(desired.loc[dt])) for dt in desired.index[changes != 0]]
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


def trade_stats(asset: pd.DataFrame, desired: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> Dict[str, float]:
    trades = trade_log(asset, desired)
    if trades.empty:
        return {"trade_count": 0.0, "win_rate": np.nan, "avg_trade": np.nan, "loss_trade_count": 0.0}
    trades = trades[(pd.to_datetime(trades["entry_signal_date"]) >= start) & (pd.to_datetime(trades["entry_signal_date"]) <= end)]
    if trades.empty:
        return {"trade_count": 0.0, "win_rate": np.nan, "avg_trade": np.nan, "loss_trade_count": 0.0}
    gross = pd.to_numeric(trades["gross_return"], errors="coerce")
    return {
        "trade_count": float(len(trades)),
        "win_rate": float((gross > 0).mean()),
        "avg_trade": float(gross.mean()),
        "loss_trade_count": float((gross <= 0).sum()),
    }


def evaluate_spec(
    spec: RegimeFilteredMASpec,
    selected_codes: Iterable[str],
    etfs: Dict[str, pd.DataFrame],
    breadth: pd.DataFrame,
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
        asset = etfs[code].loc[start:end].copy()
        desired = signal_for(asset, breadth, spec)
        _nav, returns, _position = backtest_binary_position(asset, desired, cost_rate=cost_rate)
        tr = compute_performance_metrics(returns, start, train_end, risk_free)
        te = compute_performance_metrics(returns, test_start, end, risk_free)
        tr["code"] = code
        te["code"] = code
        train_rows.append(tr)
        test_rows.append(te)
    row: Dict[str, object] = asdict(spec)
    row["strategy"] = spec.name
    row.update(aggregate_metrics(train_rows, "pool_train"))
    row.update(aggregate_metrics(test_rows, "pool_test"))
    return row


def train_score(row: pd.Series) -> float:
    sharpe = row.get("pool_train_median_sharpe", np.nan)
    positive = row.get("pool_train_positive_ratio", np.nan)
    dd = row.get("pool_train_median_max_drawdown", np.nan)
    if pd.isna(sharpe):
        return -999.0
    score = float(sharpe)
    if pd.notna(positive):
        score += 0.5 * (positive - 0.5)
    if pd.notna(dd) and dd < -0.35:
        score -= abs(dd) - 0.35
    return score


def robust_score(row: pd.Series) -> float:
    score = float(row.get("pool_train_median_sharpe", 0.0))
    score += 0.6 * float(row.get("pool_test_median_sharpe", 0.0))
    score += 0.5 * float(row.get("target_test_sharpe", 0.0))
    score += 0.2 * float(row.get("target_train_sharpe", 0.0))
    score -= 0.5 * max(0.0, abs(float(row.get("target_test_max_drawdown", 0.0))) - 0.15)
    return score


def write_checkpoint(rows: List[Dict[str, object]], path: Path) -> None:
    if rows:
        pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")


def load_checkpoint(path: Path) -> tuple[List[Dict[str, object]], set[str]]:
    if not path.exists():
        return [], set()
    df = pd.read_csv(path, encoding="utf-8-sig")
    return df.to_dict("records"), set(df["strategy"].astype(str))


def format_trade_table(trades: pd.DataFrame) -> str:
    if trades.empty:
        return "无已闭合交易。"
    frame = trades.tail(20).copy()
    for col in ["entry_signal_close", "entry_open", "exit_signal_close", "exit_open"]:
        frame[col] = pd.to_numeric(frame[col], errors="coerce").map(lambda x: f"{x:.4f}")
    for col in ["gross_return", "net_approx"]:
        frame[col] = pd.to_numeric(frame[col], errors="coerce").map(lambda x: pct(x))
    return markdown_table(frame)


def write_report(
    path: Path,
    best: pd.Series,
    robust: pd.Series,
    target_metrics: Dict[str, Dict[str, float]],
    hold_metrics: Dict[str, Dict[str, float]],
    latest: Dict[str, object],
    trades: pd.DataFrame,
    top_table: pd.DataFrame,
    output_paths: Dict[str, Path],
    args: argparse.Namespace,
    candidate_count: int,
    missing: List[str],
) -> None:
    best_spec = spec_from_row(best)
    robust_name = str(robust["strategy"]) if not robust.empty else "无"
    source_note = """## 网上研究后的处理思路

- 趋势跟随的核心是让利润奔跑，但在横盘里容易被来回反转消耗。
- ADX 用来衡量趋势强度，而不是方向；低 ADX 常被用作震荡/弱趋势过滤。
- Kaufman Efficiency Ratio 用“净位移 / 路径波动”衡量价格运动的效率，越低越接近噪声。
- Choppiness Index 用来判断市场是否更像横盘震荡，数值越高越 choppy。
- 因此本轮搜索把均线交叉改造成“趋势 + 反横盘过滤”：MA 方向负责抓大趋势，ADX/ER/Chop/MA 距离/最小持仓/冷却期负责减少震荡打脸。
"""
    text = f"""# 588200 横盘过滤趋势策略搜索报告

生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

{source_note}

## 搜索口径

- 候选策略数量：{candidate_count}
- 训练期：{args.start} 至 {args.train_end}
- 样本外：{(pd.to_datetime(args.train_end) + pd.Timedelta(days=1)).date()} 至 {args.end}
- 交易对象：`{args.target}`
- 成分股缺失代码：{", ".join(missing) if missing else "无"}
- 选择口径：本报告“最优”按 588200 样本外夏普排序；同时给出稳健候选，避免只看事后最强。

## 588200 样本外最优策略

策略：`{best_spec.name}`

- 均线方向：{best_spec.fast_window} 日均线 > {best_spec.slow_window} 日均线
- 成分股广度：买入 {best_spec.breadth_buy:.0%} / 卖出 {best_spec.breadth_sell:.0%}
- 波动率过滤：{best_spec.vol_window} 日波动率分位 <= {best_spec.vol_max:.0%}
- ADX：{"未启用" if best_spec.adx_min is None else f"{best_spec.adx_window} 日 ADX >= {best_spec.adx_min:.0f}"}
- ER：{"未启用" if best_spec.er_min is None else f"{best_spec.er_window} 日 ER >= {best_spec.er_min:.2f}"}
- Choppiness：{"未启用" if best_spec.chop_max is None else f"{best_spec.chop_window} 日 Chop <= {best_spec.chop_max:.0f}"}
- 均线距离/ATR：{"未启用" if best_spec.ma_gap_atr_min is None else f">= {best_spec.ma_gap_atr_min:.2f}"}
- 最小持仓/冷却：{best_spec.min_hold_days} / {best_spec.cooldown_days} 个交易日
- 是否要求 `poolmom`：{best_spec.require_pool_mom}

## 买点

每天收盘后检查，全部满足时，下一交易日开盘买入或继续持有：

1. 快均线大于慢均线。
2. 成分股池 MA60 广度达到买入阈值。
3. 588200 波动率不处于过热分位。
4. 启用的横盘过滤器全部通过，例如 ADX 足够高、ER 足够高、Choppiness 不高、均线距离相对 ATR 不太窄。
5. 若启用 `poolmom`，成分股池 20 日收益中位数必须大于 0。
6. 若处在冷却期内，不买。

## 卖点

任一条件触发时，下一交易日开盘卖出或继续空仓：

1. 快均线小于等于慢均线。
2. 成分股池 MA60 广度跌到卖出阈值或更低。
3. 588200 波动率分位高于卖出上限。
4. 若启用 `poolmom`，成分股池 20 日收益中位数小于等于 0。
5. 如果刚买入未达到最小持仓天数，延迟执行卖出，目的是降低横盘内的频繁假突破。

## 588200 回测结果

| 区间 | 策略年化 | 策略夏普 | 策略最大回撤 | 策略仓位占比 | 买入持有年化 | 买入持有夏普 | 买入持有最大回撤 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 训练期 | {pct(target_metrics['train']['annual_return'])} | {target_metrics['train']['sharpe']:.3f} | {pct(target_metrics['train']['max_drawdown'])} | {pct(target_metrics['train']['exposure'])} | {pct(hold_metrics['train']['annual_return'])} | {hold_metrics['train']['sharpe']:.3f} | {pct(hold_metrics['train']['max_drawdown'])} |
| 样本外 | {pct(target_metrics['test']['annual_return'])} | {target_metrics['test']['sharpe']:.3f} | {pct(target_metrics['test']['max_drawdown'])} | {pct(target_metrics['test']['exposure'])} | {pct(hold_metrics['test']['annual_return'])} | {hold_metrics['test']['sharpe']:.3f} | {pct(hold_metrics['test']['max_drawdown'])} |
| 全样本 | {pct(target_metrics['full']['annual_return'])} | {target_metrics['full']['sharpe']:.3f} | {pct(target_metrics['full']['max_drawdown'])} | {pct(target_metrics['full']['exposure'])} | {pct(hold_metrics['full']['annual_return'])} | {hold_metrics['full']['sharpe']:.3f} | {pct(hold_metrics['full']['max_drawdown'])} |

## 实际执行交易

{format_trade_table(trades)}

## 最新信号

- 信号日：{latest['signal_date']}
- 收盘价：{latest['close']:.4f}
- 下一交易日计划：`{latest['next_action']}`

## 稳健候选

本轮稳健候选为：`{robust_name}`。

稳健候选要求训练池、样本外池、588200 训练期和 588200 样本外都为正，再按综合稳健分排序。它未必是样本外收益最高，但更接近可继续观察的策略。

## 排名前十

{markdown_table(top_table)}

## 输出文件

- 策略排序：`{output_paths['summary']}`
- 588200 信号：`{output_paths['signal']}`
- 逐笔交易：`{output_paths['trades']}`
- 最优配置：`{output_paths['config']}`
- 断点文件：`{output_paths['checkpoint']}`
- 本报告：`{path}`

本报告用于研究，不构成投资建议。
"""
    path.write_text(text, encoding="utf-8")


def main() -> None:
    args = parse_args()
    start = pd.to_datetime(args.start)
    train_end = pd.to_datetime(args.train_end)
    test_start = train_end + pd.Timedelta(days=1)
    end = pd.to_datetime(args.end)
    run_dir = Path(args.run_dir) if args.run_dir else Path(args.output_dir) / f"sideways_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    run_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = run_dir / "strategy_summary_checkpoint.csv"

    print("Loading data...", flush=True)
    astock_root = Path(args.astock_root)
    etfs = load_etfs(astock_root)
    stocks, missing = load_stock_pool(astock_root)
    stocks = {code: df.loc[start:end].copy() for code, df in stocks.items()}
    breadth = build_breadth_features(stocks)
    selected = select_similar_etfs(etfs, args.target, start, train_end, args.min_overlap, args.min_corr, args.max_similar_etfs)
    selected_codes = selected["code"].tolist()
    specs = make_specs()
    print(f"ETF series loaded: {len(etfs)}", flush=True)
    print(f"Stock pool loaded: {len(stocks)}, missing: {len(missing)}", flush=True)
    print(f"Similar ETFs: {len(selected_codes)}", flush=True)
    print(f"Strategy specs: {len(specs)}", flush=True)

    rows, completed = load_checkpoint(checkpoint_path) if args.resume else ([], set())
    target_asset = etfs[args.target].loc[start:end].copy()
    remaining = [spec for spec in specs if spec.name not in completed]
    print(f"Remaining specs: {len(remaining)}", flush=True)
    for i, spec in enumerate(remaining, start=1):
        row = evaluate_spec(spec, selected_codes, etfs, breadth, start, train_end, test_start, end, args.cost_rate, args.risk_free)
        desired = signal_for(target_asset, breadth, spec)
        _nav, returns, _position = backtest_binary_position(target_asset, desired, cost_rate=args.cost_rate)
        row.update({f"target_train_{k}": v for k, v in compute_performance_metrics(returns, start, train_end, args.risk_free).items()})
        row.update({f"target_test_{k}": v for k, v in compute_performance_metrics(returns, test_start, end, args.risk_free).items()})
        row.update({f"target_full_{k}": v for k, v in compute_performance_metrics(returns, start, end, args.risk_free).items()})
        row.update({f"target_test_{k}": v for k, v in trade_stats(target_asset, desired, test_start, end).items()})
        row["train_score"] = train_score(pd.Series(row))
        rows.append(row)
        if args.checkpoint_every > 0 and (i % args.checkpoint_every == 0 or i == len(remaining)):
            write_checkpoint(rows, checkpoint_path)
            print(f"Checkpoint saved: {len(rows)}/{len(specs)} -> {checkpoint_path}", flush=True)

    write_checkpoint(rows, checkpoint_path)
    summary = pd.DataFrame(rows)
    summary["robust_score"] = summary.apply(robust_score, axis=1)
    summary = summary.sort_values(["target_test_sharpe", "target_test_annual_return"], ascending=False).reset_index(drop=True)
    best = summary.iloc[0]
    robust_pool = summary[
        (summary["pool_train_median_sharpe"] > 0)
        & (summary["pool_test_median_sharpe"] > 0)
        & (summary["target_train_sharpe"] > 0)
        & (summary["target_test_sharpe"] > 0)
        & (summary["target_test_trade_count"] <= 8)
    ]
    robust = robust_pool.sort_values(["robust_score", "target_test_sharpe"], ascending=False).iloc[0] if not robust_pool.empty else pd.Series(dtype=object)

    best_spec = spec_from_row(best)
    best_desired = signal_for(target_asset, breadth, best_spec)
    target_nav, target_returns, target_position = backtest_binary_position(target_asset, best_desired, cost_rate=args.cost_rate)
    hold_returns = buy_hold_returns(target_asset)
    target_metrics = {
        "train": compute_performance_metrics(target_returns, start, train_end, args.risk_free),
        "test": compute_performance_metrics(target_returns, test_start, end, args.risk_free),
        "full": compute_performance_metrics(target_returns, start, end, args.risk_free),
    }
    hold_metrics = {
        "train": compute_performance_metrics(hold_returns, start, train_end, args.risk_free),
        "test": compute_performance_metrics(hold_returns, test_start, end, args.risk_free),
        "full": compute_performance_metrics(hold_returns, start, end, args.risk_free),
    }
    trades = trade_log(target_asset, best_desired)
    trades_test = trades[pd.to_datetime(trades["entry_signal_date"]) >= test_start].copy() if not trades.empty else trades
    last_date = best_desired.index[-1]
    latest = {
        "signal_date": last_date.date().isoformat(),
        "close": float(target_asset.loc[last_date, "close"]),
        "next_action": "BUY_OR_HOLD_588200" if bool(best_desired.loc[last_date]) else "EMPTY_OR_SELL_588200",
    }

    out_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary_path = run_dir / f"strategy_summary_{out_ts}.csv"
    signal_path = run_dir / f"target_588200_signal_{out_ts}.csv"
    trades_path = run_dir / f"target_588200_trades_{out_ts}.csv"
    config_path = run_dir / f"best_config_{out_ts}.json"
    report_path = run_dir / f"report_{out_ts}.md"
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(
        {
            "open": target_asset["open"],
            "close": target_asset["close"],
            "desired_after_close": best_desired,
            "position_next_open": target_position,
            "strategy_return": target_returns,
            "strategy_nav": target_nav,
            "buy_hold_nav": (1 + hold_returns).cumprod(),
        }
    ).to_csv(signal_path, index=True, index_label="date", encoding="utf-8-sig")
    trades.to_csv(trades_path, index=False, encoding="utf-8-sig")
    config_path.write_text(
        json.dumps(
            {
                "best_strategy": asdict(best_spec),
                "robust_strategy": robust.to_dict() if not robust.empty else None,
                "latest_signal": latest,
                "candidate_count": int(len(summary)),
                "selected_etfs": selected_codes,
                "missing_stock_codes": missing,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    top_cols = [
        "strategy",
        "fast_window",
        "slow_window",
        "adx_window",
        "adx_min",
        "er_window",
        "er_min",
        "chop_window",
        "chop_max",
        "ma_gap_atr_min",
        "min_hold_days",
        "cooldown_days",
        "pool_train_median_sharpe",
        "pool_test_median_sharpe",
        "target_test_annual_return",
        "target_test_sharpe",
        "target_test_max_drawdown",
        "target_test_trade_count",
        "target_test_loss_trade_count",
    ]
    write_report(
        report_path,
        best,
        robust,
        target_metrics,
        hold_metrics,
        latest,
        trades_test,
        summary.head(10)[top_cols],
        {
            "summary": summary_path,
            "signal": signal_path,
            "trades": trades_path,
            "config": config_path,
            "checkpoint": checkpoint_path,
        },
        args,
        len(summary),
        missing,
    )

    print("\nSideways-filtered search completed", flush=True)
    print(f"best_strategy: {best_spec.name}", flush=True)
    print(f"candidate_count: {len(summary)}", flush=True)
    print(f"588200 test annual return: {target_metrics['test']['annual_return'] * 100:.2f}%", flush=True)
    print(f"588200 test Sharpe: {target_metrics['test']['sharpe']:.3f}", flush=True)
    print(f"588200 test max drawdown: {target_metrics['test']['max_drawdown'] * 100:.2f}%", flush=True)
    print(f"latest plan: {latest['next_action']} as of {latest['signal_date']}", flush=True)
    print(f"report: {report_path}", flush=True)


if __name__ == "__main__":
    main()
