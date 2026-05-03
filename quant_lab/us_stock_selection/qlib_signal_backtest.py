"""Convert Qlib-style scores into vectorbt-audited portfolio backtests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from quant_lab.us_stock_selection.utils import (
    annualized_return,
    annualized_volatility,
    calmar_ratio,
    compact_params,
    ensure_dir,
    max_drawdown,
    nav_from_returns,
    save_dataframe,
    save_parquet,
)


def run_qlib_signal_backtests(
    predictions_index: pd.DataFrame,
    loaded_data: dict[str, pd.DataFrame],
    out_dir: Path | str,
    config: dict[str, Any],
    logger: Any,
) -> dict[str, pd.DataFrame]:
    """Backtest TopK, TopKDropout, safe-switch, and guardrail portfolios."""
    out_path = ensure_dir(out_dir)
    close = build_close_panel(loaded_data)
    if close.empty or predictions_index.empty:
        empty = pd.DataFrame()
        save_dataframe(empty, out_path / "qlib_signal_strategy_results.csv")
        save_dataframe(empty, out_path / "qlib_signal_portfolio_daily.csv")
        save_dataframe(empty, out_path / "qlib_signal_turnover.csv")
        save_parquet(empty, out_path / "qlib_signal_holdings.parquet")
        return {"results": empty, "daily": empty, "turnover": empty, "holdings": empty}

    cfg = config.get("qlib_v4", {}).get("signal_backtest", {})
    rebalances = cfg.get("rebalance", ["W", "M"])
    top_ks = cfg.get("top_k", [1, 3, 5, 10])
    max_weights = cfg.get("max_weight", [0.2, 0.33, 0.5, 1.0])
    n_drops = cfg.get("n_drop", [1, 2])
    max_runs = int(cfg.get("max_backtest_runs", 120))
    cost_bps = float(cfg.get("transaction_cost_bps", 5.0))
    slippage_bps = float(cfg.get("slippage_bps", 5.0))

    result_rows: list[dict[str, Any]] = []
    daily_rows: list[pd.DataFrame] = []
    turnover_rows: list[pd.DataFrame] = []
    holding_rows: list[pd.DataFrame] = []
    completed = 0

    pred_rows = predictions_index.to_dict(orient="records")
    for pred_meta in pred_rows:
        if completed >= max_runs:
            break
        pred_file = Path(str(pred_meta.get("prediction_file", "")))
        if not pred_file.exists():
            continue
        pred_df = pd.read_parquet(pred_file)
        if "segment" in pred_df.columns:
            pred_df = pred_df.loc[pred_df["segment"].isin(["test", "walk_forward_test"])].copy()
        if pred_df.empty:
            continue
        score = pred_df.pivot_table(index="date", columns="ticker", values="score", aggfunc="last")
        score.index = pd.to_datetime(score.index)
        score = score.sort_index().reindex(close.index).ffill(limit=3)
        local_close = close.loc[(close.index >= score.dropna(how="all").index.min()) & (close.index <= score.dropna(how="all").index.max()), score.columns.intersection(close.columns)].ffill()
        if local_close.empty:
            continue
        local_score = score.reindex(local_close.index).loc[:, local_close.columns]

        for rebalance in rebalances:
            if completed >= max_runs:
                break
            for top_k in top_ks:
                for max_weight in max_weights:
                    strategy_specs = [
                        ("topk_equal_weight", {"top_k": int(top_k), "max_weight": float(max_weight)}),
                        ("safe_switch", {"top_k": int(top_k), "max_weight": float(max_weight), "safe_asset": cfg.get("safe_asset", "SHY")}),
                        ("guardrail", {"top_k": int(top_k), "max_weight": float(max_weight), "safe_asset": cfg.get("safe_asset", "SHY")}),
                    ]
                    for n_drop in n_drops:
                        strategy_specs.append(("topk_dropout", {"top_k": int(top_k), "max_weight": float(max_weight), "n_drop": int(n_drop)}))
                    for strategy_name, params in strategy_specs:
                        if completed >= max_runs:
                            break
                        weights = build_weights(
                            close=local_close,
                            score=local_score,
                            strategy_name=strategy_name,
                            rebalance=str(rebalance),
                            params=params,
                        )
                        if weights.empty or weights.sum(axis=1).mean() <= 0.0:
                            continue
                        returns, turnover = portfolio_returns(local_close, weights, cost_bps=cost_bps, slippage_bps=slippage_bps)
                        strategy_id = f"{pred_meta.get('run_id')}_{strategy_name}_{rebalance}_k{params.get('top_k')}_mw{params.get('max_weight')}_d{params.get('n_drop', 0)}"
                        metrics = compute_portfolio_metrics(returns, turnover, weights)
                        result_rows.append(
                            {
                                "strategy_id": strategy_id,
                                "run_id": pred_meta.get("run_id"),
                                "feature_set": pred_meta.get("feature_set"),
                                "model": pred_meta.get("model"),
                                "label": pred_meta.get("label"),
                                "portfolio_template": strategy_name,
                                "params": compact_params({"rebalance": rebalance, **params, "cost_bps": cost_bps, "slippage_bps": slippage_bps}),
                                **metrics,
                                "passes_cagr_20": bool(metrics["cagr"] >= 0.20),
                                "passes_calmar_1": bool(metrics["calmar"] > 1.0),
                                "passes_maxdd_35": bool(abs(metrics["max_drawdown"]) <= 0.35),
                                "passes_maxdd_45": bool(abs(metrics["max_drawdown"]) <= 0.45),
                            }
                        )
                        daily_rows.append(pd.DataFrame({"date": returns.index, "strategy_id": strategy_id, "return": returns.to_numpy(), "nav": nav_from_returns(returns).to_numpy()}))
                        turnover_rows.append(pd.DataFrame({"date": turnover.index, "strategy_id": strategy_id, "turnover": turnover.to_numpy()}))
                        holdings = weights.stack().rename("weight").reset_index()
                        holdings.columns = ["date", "ticker", "weight"]
                        holdings.insert(0, "strategy_id", strategy_id)
                        holding_rows.append(holdings)
                        completed += 1
                        if completed >= max_runs:
                            break

    results = pd.DataFrame(result_rows).sort_values(["calmar", "cagr"], ascending=[False, False]) if result_rows else pd.DataFrame()
    daily = pd.concat(daily_rows, ignore_index=True) if daily_rows else pd.DataFrame()
    turnover_df = pd.concat(turnover_rows, ignore_index=True) if turnover_rows else pd.DataFrame()
    holdings_df = pd.concat(holding_rows, ignore_index=True) if holding_rows else pd.DataFrame()
    save_dataframe(results, out_path / "qlib_signal_strategy_results.csv")
    save_dataframe(daily, out_path / "qlib_signal_portfolio_daily.csv")
    save_dataframe(turnover_df, out_path / "qlib_signal_turnover.csv")
    save_parquet(holdings_df, out_path / "qlib_signal_holdings.parquet")
    logger.info(f"v4 signal backtest complete: {len(results)} strategies.")
    return {"results": results, "daily": daily, "turnover": turnover_df, "holdings": holdings_df}


def build_close_panel(loaded_data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    panels = {}
    for ticker, frame in loaded_data.items():
        if frame is None or frame.empty:
            continue
        price = frame["adj_close"] if "adj_close" in frame.columns else frame["close"]
        panels[ticker] = price.astype(float)
    if not panels:
        return pd.DataFrame()
    close = pd.DataFrame(panels).sort_index().ffill()
    close.index = pd.to_datetime(close.index)
    close.index.name = "date"
    return close


def build_weights(
    close: pd.DataFrame,
    score: pd.DataFrame,
    strategy_name: str,
    rebalance: str,
    params: dict[str, Any],
) -> pd.DataFrame:
    top_k = int(params.get("top_k", 3))
    max_weight = float(params.get("max_weight", 1.0))
    rebalance_dates = _rebalance_dates(close.index, rebalance)
    weights = pd.DataFrame(np.nan, index=close.index, columns=close.columns, dtype=float)
    current = pd.Series(0.0, index=close.columns)
    n_drop = int(params.get("n_drop", 1))
    safe_asset = str(params.get("safe_asset", "SHY"))
    qqq_ma200 = close["QQQ"].rolling(200).mean() if "QQQ" in close.columns else pd.Series(index=close.index, data=np.nan)

    for date in rebalance_dates:
        today_score = score.loc[date].dropna().sort_values(ascending=False)
        if today_score.empty:
            weights.loc[date] = current
            continue
        risk_on = True
        if strategy_name in {"safe_switch", "guardrail"} and "QQQ" in close.columns and pd.notna(qqq_ma200.loc[date]):
            risk_on = bool(close.loc[date, "QQQ"] > qqq_ma200.loc[date])
        if strategy_name == "safe_switch" and (not risk_on or today_score.head(top_k).mean() <= 0.0):
            current = pd.Series(0.0, index=close.columns)
            if safe_asset in current.index:
                current.loc[safe_asset] = 1.0
            weights.loc[date] = current
            continue
        if strategy_name == "topk_dropout":
            ranked = today_score.index.tolist()
            selected = _strict_topk_dropout_selection(current, ranked, top_k=top_k, n_drop=n_drop)
        else:
            selected = today_score.head(top_k).index.tolist()
        if strategy_name == "guardrail":
            filtered = []
            ma200 = close.rolling(200).mean()
            for ticker in selected:
                if not risk_on:
                    continue
                if pd.notna(ma200.loc[date, ticker]) and close.loc[date, ticker] > ma200.loc[date, ticker]:
                    filtered.append(ticker)
            selected = filtered
            if not selected and safe_asset in close.columns:
                selected = [safe_asset]
        current = pd.Series(0.0, index=close.columns)
        if selected:
            raw_weight = min(max_weight, 1.0 / len(selected))
            current.loc[selected] = raw_weight
            total = current.sum()
            if total > 0 and total < 0.999 and max_weight >= 1.0 / len(selected):
                current = current / total
        weights.loc[date] = current
    return weights.ffill().fillna(0.0)


def portfolio_returns(
    close: pd.DataFrame,
    weights: pd.DataFrame,
    cost_bps: float,
    slippage_bps: float,
) -> tuple[pd.Series, pd.Series]:
    asset_returns = close.pct_change(fill_method=None).fillna(0.0)
    shifted = weights.shift(1).fillna(0.0)
    gross = (shifted * asset_returns).sum(axis=1)
    turnover = weights.diff().abs().sum(axis=1).fillna(weights.abs().sum(axis=1))
    cost = turnover * ((cost_bps + slippage_bps) / 10000.0)
    return (gross - cost).fillna(0.0), turnover


def compute_portfolio_metrics(
    returns: pd.Series,
    turnover: pd.Series,
    weights: pd.DataFrame,
) -> dict[str, Any]:
    returns = returns.dropna()
    nav = nav_from_returns(returns)
    yearly = returns.groupby(returns.index.year).apply(lambda s: float((1.0 + s).prod() - 1.0)) if not returns.empty else pd.Series(dtype=float)
    crash_2020 = returns.loc[(returns.index >= "2020-02-15") & (returns.index <= "2020-04-30")]
    ret_2022 = returns.loc[(returns.index >= "2022-01-01") & (returns.index <= "2022-12-31")]
    exposure = weights.sum(axis=1).reindex(returns.index).fillna(0.0)
    return {
        "total_return": float(nav.iloc[-1] - 1.0) if not nav.empty else 0.0,
        "cagr": annualized_return(returns),
        "max_drawdown": max_drawdown(nav),
        "calmar": calmar_ratio(returns),
        "sharpe": _sharpe(returns),
        "sortino": _sortino(returns),
        "volatility": annualized_volatility(returns),
        "win_rate": float((returns > 0).mean()) if not returns.empty else 0.0,
        "annual_turnover": float(turnover.sum() / max(len(returns) / 252.0, 1e-9)) if not returns.empty else 0.0,
        "exposure": float(exposure.mean()) if not exposure.empty else 0.0,
        "worst_year": float(yearly.min()) if not yearly.empty else 0.0,
        "return_2022": float((1.0 + ret_2022).prod() - 1.0) if not ret_2022.empty else 0.0,
        "crash_2020_max_drawdown": max_drawdown(nav_from_returns(crash_2020)) if not crash_2020.empty else 0.0,
        "daily_count": int(len(returns)),
    }


def build_benchmark_comparison_v4(
    loaded_data: dict[str, pd.DataFrame],
    qlib_results: pd.DataFrame,
    qlib_daily: pd.DataFrame,
    out_dir: Path | str,
    config: dict[str, Any],
) -> pd.DataFrame:
    """Build QQQ/QLD/TQQQ/SPY/equal-weight/v2-top comparisons."""
    out_path = ensure_dir(out_dir)
    close = build_close_panel(loaded_data)
    rows: list[dict[str, Any]] = []
    for ticker in ["QQQ", "QLD", "TQQQ", "SPY"]:
        if ticker in close.columns:
            returns = close[ticker].pct_change(fill_method=None).fillna(0.0)
            rows.append({"name": f"{ticker}_buy_hold", "type": "benchmark", **compute_portfolio_metrics(returns, pd.Series(0.0, index=returns.index), pd.DataFrame({ticker: 1.0}, index=returns.index))})
    if not close.empty:
        monthly_dates = _rebalance_dates(close.index, "M")
        weights = pd.DataFrame(np.nan, index=close.index, columns=close.columns)
        for date in monthly_dates:
            available = close.loc[date].dropna().index
            weights.loc[date, available] = 1.0 / len(available)
        weights = weights.ffill().fillna(0.0)
        returns, turnover = portfolio_returns(close, weights, cost_bps=5.0, slippage_bps=5.0)
        rows.append({"name": "pool_a_equal_weight_monthly", "type": "benchmark", **compute_portfolio_metrics(returns, turnover, weights)})
    if not qlib_results.empty and not qlib_daily.empty:
        top_ids = qlib_results.head(10)["strategy_id"].tolist()
        for strategy_id in top_ids:
            row = qlib_results.loc[qlib_results["strategy_id"] == strategy_id].head(1)
            if row.empty:
                continue
            metrics = {
                key: row.iloc[0].get(key, 0.0)
                for key in [
                    "total_return",
                    "cagr",
                    "max_drawdown",
                    "calmar",
                    "sharpe",
                    "sortino",
                    "volatility",
                    "win_rate",
                    "annual_turnover",
                    "exposure",
                    "worst_year",
                    "return_2022",
                    "crash_2020_max_drawdown",
                ]
            }
            rows.append({"name": strategy_id, "type": "qlib_signal_strategy", **metrics})
    comparison = pd.DataFrame(rows)
    if not comparison.empty:
        baseline = comparison.set_index("name")
        for benchmark in ("QQQ_buy_hold", "QLD_buy_hold", "TQQQ_buy_hold", "SPY_buy_hold"):
            if benchmark in baseline.index:
                comparison[f"calmar_gt_{benchmark}"] = comparison["calmar"] > float(baseline.loc[benchmark, "calmar"])
                comparison[f"cagr_gt_{benchmark}"] = comparison["cagr"] > float(baseline.loc[benchmark, "cagr"])
    save_dataframe(comparison, out_path / "comparison_v4.csv")
    return comparison


def _rebalance_dates(index: pd.DatetimeIndex, rebalance: str) -> pd.DatetimeIndex:
    idx = pd.DatetimeIndex(index).sort_values()
    code = str(rebalance).upper()
    if code in {"2W", "BIWEEKLY"}:
        target = pd.Series(index=idx, data=np.arange(len(idx))).resample("2W-FRI").last().dropna().index
    elif code.startswith("W"):
        target = pd.Series(index=idx, data=np.arange(len(idx))).resample("W-FRI").last().dropna().index
    elif code.startswith("Q"):
        target = pd.Series(index=idx, data=np.arange(len(idx))).resample("QE").last().dropna().index
    else:
        target = pd.Series(index=idx, data=np.arange(len(idx))).resample("ME").last().dropna().index
    return idx[idx.isin(target)]


def _strict_topk_dropout_selection(current: pd.Series, ranked: list[str], top_k: int, n_drop: int) -> list[str]:
    """US_STOCK_SELECTION新增: replace at most n_drop holdings per rebalance."""
    rank_map = {ticker: idx for idx, ticker in enumerate(ranked)}
    current_holdings = [ticker for ticker in current[current > 0].index.astype(str).tolist() if ticker in rank_map]
    if not current_holdings:
        return ranked[:top_k]
    sell_candidates = sorted(
        [ticker for ticker in current_holdings if rank_map.get(ticker, 10**9) >= top_k],
        key=lambda ticker: rank_map.get(ticker, 10**9),
        reverse=True,
    )
    sell = set(sell_candidates[: max(0, n_drop)])
    keep = [ticker for ticker in current_holdings if ticker not in sell]
    keep = sorted(keep, key=lambda ticker: rank_map.get(ticker, 10**9))[:top_k]
    slots = max(0, top_k - len(keep))
    buys = [ticker for ticker in ranked if ticker not in keep][:slots]
    return (keep + buys)[:top_k]


def _sharpe(returns: pd.Series) -> float:
    vol = returns.std(ddof=0)
    return float(returns.mean() / vol * np.sqrt(252)) if vol else 0.0


def _sortino(returns: pd.Series) -> float:
    downside = returns.where(returns < 0, 0.0).std(ddof=0)
    return float(returns.mean() / downside * np.sqrt(252)) if downside else 0.0
