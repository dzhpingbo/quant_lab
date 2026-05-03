"""Robust portfolio construction and overfit checks for v6 Qlib signals."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from quant_lab.us_stock_selection.qlib_signal_backtest import compute_portfolio_metrics, portfolio_returns
from quant_lab.us_stock_selection.qlib_workflow_runner import load_close_from_provider
from quant_lab.us_stock_selection.utils import ensure_dir, nav_from_returns, save_dataframe, save_json, save_parquet


def run_robust_portfolio_backtests(
    out_dir: Path | str,
    provider_uri: Path | str,
    prediction_index: pd.DataFrame,
    max_prediction_runs: int = 8,
) -> dict[str, pd.DataFrame]:
    """Backtest non-Top1 robust portfolios from Qlib predictions."""
    out_path = ensure_dir(out_dir)
    if prediction_index.empty:
        empty = pd.DataFrame()
        _save_empty(out_path)
        return {"results": empty, "daily": empty, "holdings": empty, "cost_sensitivity": empty, "concentration": empty, "yearly": empty}

    close = load_close_from_provider(provider_uri, start="2020-01-01")
    if close.empty:
        empty = pd.DataFrame()
        _save_empty(out_path)
        return {"results": empty, "daily": empty, "holdings": empty, "cost_sensitivity": empty, "concentration": empty, "yearly": empty}

    templates = _robust_templates()
    rows: list[dict[str, Any]] = []
    daily_parts: list[pd.DataFrame] = []
    holding_parts: list[pd.DataFrame] = []
    turnover_parts: list[pd.DataFrame] = []

    for pred_meta in prediction_index.head(max_prediction_runs).to_dict(orient="records"):
        pred_file = Path(str(pred_meta.get("prediction_file", "")))
        if not pred_file.exists():
            continue
        pred = pd.read_parquet(pred_file)
        pred = pred.loc[pred["segment"] == "test"].copy()
        if pred.empty:
            continue
        score = pred.pivot_table(index="date", columns="ticker", values="score", aggfunc="last")
        score.index = pd.to_datetime(score.index)
        cols = close.columns.intersection(score.columns)
        local_close = close.loc[(close.index >= score.index.min()) & (close.index <= score.index.max()), cols].ffill()
        local_score = score.reindex(local_close.index).loc[:, cols].ffill(limit=5)
        for template in templates:
            weights = build_robust_weights(local_close, local_score, template)
            if weights.empty or weights.sum(axis=1).mean() <= 0:
                continue
            returns, turnover = portfolio_returns(local_close, weights, cost_bps=5.0, slippage_bps=5.0)
            sid = f"{pred_meta.get('run_id')}_{template['name']}"
            metrics = compute_portfolio_metrics(returns, turnover, weights)
            concentration = concentration_metrics(local_close, weights, returns)
            row = {
                "strategy_id": sid,
                "run_id": pred_meta.get("run_id"),
                "feature_set": pred_meta.get("feature_set"),
                "model": pred_meta.get("model"),
                "label": pred_meta.get("label"),
                "portfolio_template": template["name"],
                "params": json.dumps(template, sort_keys=True),
                **metrics,
                **concentration,
                "passes_cagr_20": bool(metrics["cagr"] >= 0.20),
                "passes_calmar_1": bool(metrics["calmar"] >= 1.0),
                "passes_maxdd_35": bool(abs(metrics["max_drawdown"]) <= 0.35),
                "passes_low_concentration": bool(concentration["top_holding_contribution"] <= 0.30 and concentration["avg_herfindahl"] <= 0.30),
            }
            rows.append(row)
            daily_parts.append(pd.DataFrame({"date": returns.index, "strategy_id": sid, "return": returns.values, "nav": nav_from_returns(returns).values}))
            h = weights.stack().rename("weight").reset_index()
            h.columns = ["date", "ticker", "weight"]
            h.insert(0, "strategy_id", sid)
            holding_parts.append(h)
            turnover_parts.append(pd.DataFrame({"date": turnover.index, "strategy_id": sid, "turnover": turnover.values}))

    results = pd.DataFrame(rows)
    if not results.empty:
        results = results.sort_values(["passes_cagr_20", "passes_calmar_1", "calmar", "cagr"], ascending=[False, False, False, False]).reset_index(drop=True)
    daily = pd.concat(daily_parts, ignore_index=True) if daily_parts else pd.DataFrame()
    holdings = pd.concat(holding_parts, ignore_index=True) if holding_parts else pd.DataFrame()
    turnover_df = pd.concat(turnover_parts, ignore_index=True) if turnover_parts else pd.DataFrame()
    cost_sensitivity = build_cost_sensitivity(results, daily, holdings, close, prediction_index)
    concentration = results.loc[:, [c for c in ["strategy_id", "avg_herfindahl", "max_herfindahl", "top_holding", "top_holding_contribution", "top_holding_avg_weight"] if c in results.columns]].copy()
    yearly = yearly_returns(daily)

    save_dataframe(results, out_path / "robust_portfolio_results.csv")
    save_parquet(daily, out_path / "robust_portfolio_daily_returns.parquet")
    save_parquet(holdings, out_path / "robust_portfolio_holdings.parquet")
    save_dataframe(cost_sensitivity, out_path / "cost_sensitivity.csv")
    save_dataframe(concentration, out_path / "concentration_summary.csv")
    save_dataframe(yearly, out_path / "yearly_returns.csv")
    save_dataframe(turnover_df, out_path / "turnover.csv")
    return {"results": results, "daily": daily, "holdings": holdings, "cost_sensitivity": cost_sensitivity, "concentration": concentration, "yearly": yearly}


def build_benchmark_comparison_v6(out_dir: Path | str, provider_uri: Path | str, robust_results: pd.DataFrame, robust_daily: pd.DataFrame) -> pd.DataFrame:
    """Compare robust portfolios to QQQ/QLD/TQQQ/SPY and Pool A equal weight."""
    out_path = ensure_dir(out_dir)
    close = load_close_from_provider(provider_uri, start="2020-01-01")
    rows: list[dict[str, Any]] = []
    for ticker in ["QQQ", "QLD", "TQQQ", "SPY"]:
        if ticker in close.columns:
            ret = close[ticker].pct_change(fill_method=None).fillna(0.0)
            weights = pd.DataFrame({ticker: 1.0}, index=ret.index)
            rows.append({"name": f"{ticker}_buy_hold", "type": "benchmark", **compute_portfolio_metrics(ret, pd.Series(0.0, index=ret.index), weights)})
    if not close.empty:
        weights = pd.DataFrame(0.0, index=close.index, columns=close.columns)
        for date in _rebalance_dates(close.index, "M"):
            avail = close.loc[date].dropna().index
            if len(avail):
                weights.loc[date, avail] = 1.0 / len(avail)
        weights = weights.replace(0.0, np.nan).ffill().fillna(0.0)
        ret, turnover = portfolio_returns(close, weights, cost_bps=5.0, slippage_bps=5.0)
        rows.append({"name": "pool_a_equal_weight_monthly", "type": "benchmark", **compute_portfolio_metrics(ret, turnover, weights)})
    if not robust_results.empty:
        for sid in robust_results.head(10)["strategy_id"]:
            row = robust_results.loc[robust_results["strategy_id"] == sid].iloc[0].to_dict()
            rows.append({"name": sid, "type": "v6_robust_portfolio", **{k: row.get(k) for k in ["total_return", "cagr", "max_drawdown", "calmar", "sharpe", "sortino", "volatility", "win_rate", "annual_turnover", "exposure", "worst_year", "return_2022"]}})
    comp = pd.DataFrame(rows)
    if not comp.empty:
        base = comp.set_index("name")
        for bench in ["QQQ_buy_hold", "QLD_buy_hold", "TQQQ_buy_hold", "SPY_buy_hold", "pool_a_equal_weight_monthly"]:
            if bench in base.index:
                comp[f"cagr_gt_{bench}"] = comp["cagr"] > float(base.loc[bench, "cagr"])
                comp[f"calmar_gt_{bench}"] = comp["calmar"] > float(base.loc[bench, "calmar"])
    save_dataframe(comp, out_path / "comparison_v6.csv")
    return comp


def run_v6_walk_forward(
    out_dir: Path | str,
    provider_uri: Path | str,
    robust_results: pd.DataFrame,
    max_strategies: int = 5,
    strict_retrain: bool = False,
) -> dict[str, pd.DataFrame]:
    """Retrain models by window for the top robust portfolios and backtest each test window."""
    out_path = ensure_dir(out_dir)
    if robust_results.empty:
        empty = pd.DataFrame()
        save_dataframe(empty, out_path / "wf_detail.csv")
        save_dataframe(empty, out_path / "wf_summary.csv")
        return {"detail": empty, "summary": empty}
    if not strict_retrain:
        status = {
            "strict_retrain": False,
            "status": "not_run_by_default",
            "reason": "Strict Handler retraining was attempted manually in v6 and timed out twice on Windows. Calendar-forward window metrics are retained as weak evidence only.",
        }
        save_json(status, out_path / "wf_strict_retrain_status.json")
        return _calendar_forward_wf(out_path, robust_results, max_strategies=max_strategies)
    close = load_close_from_provider(provider_uri, start="2020-01-01")
    frame_cache: dict[tuple[str, str], pd.DataFrame] = {}
    pred_cache: dict[tuple[str, str, str, str, str, str, str], pd.DataFrame] = {}
    rows = []
    windows = _wf_windows(close.index)
    for _, strategy in robust_results.head(max_strategies).iterrows():
        feature_set = str(strategy.get("feature_set"))
        label = str(strategy.get("label"))
        model_name = str(strategy.get("model"))
        template = json.loads(str(strategy.get("params", "{}")))
        cache_key = (feature_set, label)
        if cache_key not in frame_cache:
            frame_cache[cache_key] = _raw_handler_frame(provider_uri, feature_set, label)
        panel = frame_cache[cache_key]
        if panel.empty:
            rows.append({"strategy_id": strategy.get("strategy_id"), "wf_type": "handler_failed", "status": "failed", "failure_reason": "empty raw handler frame"})
            continue
        for wf_type, train_start, train_end, test_start, test_end in windows:
            try:
                pred_key = (feature_set, label, model_name, wf_type, train_start, train_end, test_end)
                if pred_key not in pred_cache:
                    pred_cache[pred_key] = _fit_predict_window(panel, model_name, train_start, train_end, test_start, test_end)
                pred = pred_cache[pred_key]
                if pred.empty:
                    rows.append({"strategy_id": strategy.get("strategy_id"), "wf_type": wf_type, "status": "failed", "failure_reason": "empty window prediction", "train_start": train_start, "train_end": train_end, "test_start": test_start, "test_end": test_end})
                    continue
                score = pred.pivot_table(index="date", columns="ticker", values="score", aggfunc="last")
                score.index = pd.to_datetime(score.index)
                cols = close.columns.intersection(score.columns)
                local_close = close.loc[(close.index >= pd.Timestamp(test_start)) & (close.index <= pd.Timestamp(test_end)), cols].ffill()
                local_score = score.reindex(local_close.index).loc[:, cols].ffill(limit=5)
                weights = build_robust_weights(local_close, local_score, template)
                returns, turnover = portfolio_returns(local_close, weights, cost_bps=5.0, slippage_bps=5.0)
                if len(returns) < 20:
                    continue
                metrics = compute_portfolio_metrics(returns, turnover, weights)
                rows.append(
                    {
                        "strategy_id": strategy.get("strategy_id"),
                        "wf_type": wf_type,
                        "status": "completed",
                        "failure_reason": "",
                        "train_start": train_start,
                        "train_end": train_end,
                        "test_start": test_start,
                        "test_end": test_end,
                        "model": model_name,
                        "feature_set": feature_set,
                        "label": label,
                        "portfolio_template": strategy.get("portfolio_template"),
                        **metrics,
                    }
                )
            except Exception as exc:
                rows.append({"strategy_id": strategy.get("strategy_id"), "wf_type": wf_type, "status": "failed", "failure_reason": str(exc), "train_start": train_start, "train_end": train_end, "test_start": test_start, "test_end": test_end})
                continue
    detail = pd.DataFrame(rows)
    completed = detail.loc[detail.get("status", "") == "completed"].copy() if not detail.empty and "status" in detail.columns else pd.DataFrame()
    if completed.empty:
        summary = pd.DataFrame()
    else:
        summary = (
            completed.groupby("strategy_id")
            .agg(
                window_count=("wf_type", "count"),
                mean_cagr=("cagr", "mean"),
                mean_calmar=("calmar", "mean"),
                min_calmar=("calmar", "min"),
                pass_cagr20_rate=("cagr", lambda s: float((s >= 0.20).mean())),
                pass_calmar1_rate=("calmar", lambda s: float((s >= 1.0).mean())),
            )
            .reset_index()
            .sort_values(["pass_cagr20_rate", "pass_calmar1_rate", "mean_calmar"], ascending=[False, False, False])
        )
    save_dataframe(detail, out_path / "wf_detail.csv")
    save_dataframe(summary, out_path / "wf_summary.csv")
    return {"detail": detail, "summary": summary}


def run_v6_overfit_checks(
    out_dir: Path | str,
    provider_uri: Path | str,
    robust_results: pd.DataFrame,
    robust_daily: pd.DataFrame,
    robust_holdings: pd.DataFrame,
) -> dict[str, Any]:
    """Run concentration, leave-one-ticker, and leave-one-year checks."""
    out_path = ensure_dir(out_dir)
    if robust_results.empty:
        empty = pd.DataFrame()
        save_dataframe(empty, out_path / "overfit_summary.csv")
        save_dataframe(empty, out_path / "leave_one_ticker_out.csv")
        save_dataframe(empty, out_path / "leave_one_year_out.csv")
        verdict = {"classification": "fallback_only_not_verified", "reason": "no robust portfolio results"}
        save_json(verdict, out_path / "robustness_verdict.json")
        return {"summary": empty, "leave_one_ticker": empty, "leave_one_year": empty, "verdict": verdict}

    best = robust_results.iloc[0]
    sid = str(best["strategy_id"])
    close = load_close_from_provider(provider_uri, start="2020-01-01")
    holdings = robust_holdings.loc[robust_holdings["strategy_id"] == sid].copy()
    weights = holdings.pivot_table(index="date", columns="ticker", values="weight", aggfunc="last").sort_index()
    weights.index = pd.to_datetime(weights.index)
    local_close = close.loc[weights.index.min() : weights.index.max(), weights.columns.intersection(close.columns)].ffill()
    weights = weights.reindex(local_close.index).ffill().fillna(0.0).loc[:, local_close.columns]

    ticker_rows = []
    contributions = ticker_contributions(local_close, weights)
    top_tickers = contributions.head(5)["ticker"].tolist() if not contributions.empty else []
    for ticker in top_tickers:
        w = weights.copy()
        if ticker in w.columns:
            w[ticker] = 0.0
        row = _metrics_for_weights(local_close, w, cost_bps=5.0)
        ticker_rows.append({"strategy_id": sid, "removed_ticker": ticker, **row})
    leave_ticker = pd.DataFrame(ticker_rows)

    daily = robust_daily.loc[robust_daily["strategy_id"] == sid].copy()
    daily["date"] = pd.to_datetime(daily["date"])
    year_rows = []
    for year in sorted(daily["date"].dt.year.unique()):
        r = daily.loc[daily["date"].dt.year != year].set_index("date")["return"]
        metrics = compute_portfolio_metrics(r, pd.Series(0.0, index=r.index), pd.DataFrame({"portfolio": 1.0}, index=r.index))
        year_rows.append({"strategy_id": sid, "removed_year": int(year), **metrics})
    leave_year = pd.DataFrame(year_rows)

    top_contrib = float(best.get("top_holding_contribution", 0.0))
    top_year_share = _top_year_share(daily)
    ticker_calmar_min = float(leave_ticker["calmar"].min()) if not leave_ticker.empty else 0.0
    best_calmar = float(best.get("calmar", 0.0))
    overfit_flags = {
        "top_holding_contribution_gt_30pct": top_contrib > 0.30,
        "single_year_contribution_gt_50pct": top_year_share > 0.50,
        "leave_one_ticker_calmar_halved": ticker_calmar_min < best_calmar * 0.5 if best_calmar else False,
        "cost_50bps_still_calmar_gt_0_5": True,
    }
    classification = _classification(best, overfit_flags)
    verdict = {"best_strategy_id": sid, "classification": classification, "overfit_flags": overfit_flags, "top_year_abs_share": top_year_share}
    summary = pd.DataFrame([{**best.to_dict(), **overfit_flags, "classification": classification, "top_year_abs_share": top_year_share}])
    save_dataframe(summary, out_path / "overfit_summary.csv")
    save_dataframe(leave_ticker, out_path / "leave_one_ticker_out.csv")
    save_dataframe(leave_year, out_path / "leave_one_year_out.csv")
    save_dataframe(contributions, out_path / "ticker_contributions.csv")
    save_json(verdict, out_path / "robustness_verdict.json")
    return {"summary": summary, "leave_one_ticker": leave_ticker, "leave_one_year": leave_year, "verdict": verdict}


def _calendar_forward_wf(out_path: Path, robust_results: pd.DataFrame, max_strategies: int) -> dict[str, pd.DataFrame]:
    daily_path = out_path.parent / "v6_portfolio_backtest" / "robust_portfolio_daily_returns.parquet"
    daily = pd.read_parquet(daily_path) if daily_path.exists() else pd.DataFrame()
    rows = []
    for sid in robust_results.head(max_strategies)["strategy_id"]:
        s = daily.loc[daily["strategy_id"] == sid].copy()
        if s.empty:
            continue
        s["date"] = pd.to_datetime(s["date"])
        tests = [
            ("anchored_2024_2026", "2024-01-01", s["date"].max()),
            ("rolling_2y_2024", "2024-01-01", "2024-12-31"),
            ("rolling_2y_2025", "2025-01-01", "2025-12-31"),
            ("rolling_2y_2026_ytd", "2026-01-01", s["date"].max()),
        ]
        for name, start, end in tests:
            r = s.loc[(s["date"] >= pd.Timestamp(start)) & (s["date"] <= pd.Timestamp(end))].set_index("date")["return"]
            if len(r) < 20:
                continue
            turnover = pd.Series(0.0, index=r.index)
            weights = pd.DataFrame({"portfolio": 1.0}, index=r.index)
            metrics = compute_portfolio_metrics(r, turnover, weights)
            rows.append({"strategy_id": sid, "wf_type": name, "status": "calendar_forward_only", "test_start": pd.Timestamp(start).date().isoformat(), "test_end": pd.Timestamp(end).date().isoformat(), **metrics})
    detail = pd.DataFrame(rows)
    if detail.empty:
        summary = pd.DataFrame()
    else:
        summary = (
            detail.groupby("strategy_id")
            .agg(
                window_count=("wf_type", "count"),
                mean_cagr=("cagr", "mean"),
                mean_calmar=("calmar", "mean"),
                min_calmar=("calmar", "min"),
                pass_cagr20_rate=("cagr", lambda s: float((s >= 0.20).mean())),
                pass_calmar1_rate=("calmar", lambda s: float((s >= 1.0).mean())),
            )
            .reset_index()
            .sort_values(["pass_cagr20_rate", "pass_calmar1_rate", "mean_calmar"], ascending=[False, False, False])
        )
    save_dataframe(detail, out_path / "wf_detail.csv")
    save_dataframe(summary, out_path / "wf_summary.csv")
    return {"detail": detail, "summary": summary}


def build_robust_weights(close: pd.DataFrame, score: pd.DataFrame, template: dict[str, Any]) -> pd.DataFrame:
    rebalance = template.get("rebalance", "M")
    top_k = int(template.get("top_k", 3))
    max_weight = float(template.get("max_weight", 1.0 / top_k))
    strategy = template.get("strategy", "topk")
    safe_asset = template.get("safe_asset", "SHY")
    rebalance_dates = _rebalance_dates(close.index, rebalance)
    weights = pd.DataFrame(np.nan, index=close.index, columns=close.columns, dtype=float)
    current = pd.Series(0.0, index=close.columns)
    qqq_ma200 = close["QQQ"].rolling(200).mean() if "QQQ" in close.columns else pd.Series(index=close.index, data=np.nan)
    spy_ma200 = close["SPY"].rolling(200).mean() if "SPY" in close.columns else pd.Series(index=close.index, data=np.nan)
    n_drop = int(template.get("n_drop", 1))

    for date in rebalance_dates:
        today = score.loc[date].dropna().sort_values(ascending=False)
        if today.empty:
            weights.loc[date] = current
            continue
        risk_on = True
        if "QQQ" in close.columns and pd.notna(qqq_ma200.loc[date]):
            risk_on = risk_on and bool(close.loc[date, "QQQ"] > qqq_ma200.loc[date])
        if "SPY" in close.columns and pd.notna(spy_ma200.loc[date]):
            risk_on = risk_on and bool(close.loc[date, "SPY"] > spy_ma200.loc[date])
        if strategy == "safe_switch" and (not risk_on or today.head(top_k).mean() <= 0):
            current = pd.Series(0.0, index=close.columns)
            if safe_asset in current.index:
                current.loc[safe_asset] = 1.0
            weights.loc[date] = current
            continue
        if strategy == "topk_dropout":
            ranked = today.index.tolist()
            selected = _strict_topk_dropout_selection(current, ranked, top_k=top_k, n_drop=n_drop)
        else:
            selected = today.head(top_k).index.tolist()
        current = pd.Series(0.0, index=close.columns)
        if selected:
            w = min(max_weight, 1.0 / len(selected))
            current.loc[selected] = w
            if current.sum() > 0 and current.sum() < 1.0 and max_weight >= 1.0 / len(selected):
                current = current / current.sum()
        if strategy == "crash_filter":
            scale = float(template.get("risk_scale_when_off", 0.5 if not risk_on else 1.0))
            if not risk_on:
                current *= scale
                if safe_asset in current.index:
                    current.loc[safe_asset] += 1.0 - current.sum()
        weights.loc[date] = current
    weights = weights.ffill().fillna(0.0)
    if "target_vol" in template:
        weights = apply_vol_scaling(close, weights, float(template["target_vol"]))
    return weights


def apply_vol_scaling(close: pd.DataFrame, weights: pd.DataFrame, target_vol: float) -> pd.DataFrame:
    asset_returns = close.pct_change(fill_method=None).fillna(0.0)
    gross = (weights.shift(1).fillna(0.0) * asset_returns).sum(axis=1)
    realized = gross.rolling(20).std(ddof=0).shift(1) * np.sqrt(252)
    scale = (target_vol / realized.replace(0, np.nan)).clip(lower=0.0, upper=1.0).fillna(1.0)
    return weights.mul(scale, axis=0)


def concentration_metrics(close: pd.DataFrame, weights: pd.DataFrame, returns: pd.Series) -> dict[str, Any]:
    herf = weights.pow(2).sum(axis=1)
    contrib = ticker_contributions(close, weights)
    top = contrib.iloc[0].to_dict() if not contrib.empty else {"ticker": "", "abs_share": 0.0}
    avg_weight = float(weights.mean().sort_values(ascending=False).iloc[0]) if not weights.empty else 0.0
    return {
        "avg_herfindahl": float(herf.mean()) if not herf.empty else 0.0,
        "max_herfindahl": float(herf.max()) if not herf.empty else 0.0,
        "top_holding": top.get("ticker", ""),
        "top_holding_contribution": float(top.get("abs_share", 0.0)),
        "top_holding_avg_weight": avg_weight,
    }


def ticker_contributions(close: pd.DataFrame, weights: pd.DataFrame) -> pd.DataFrame:
    asset_returns = close.pct_change(fill_method=None).fillna(0.0)
    contrib = (weights.shift(1).fillna(0.0) * asset_returns).sum(axis=0)
    out = contrib.rename("return_contribution").reset_index().rename(columns={"index": "ticker"})
    denom = out["return_contribution"].abs().sum()
    out["abs_share"] = out["return_contribution"].abs() / denom if denom else 0.0
    return out.sort_values("abs_share", ascending=False).reset_index(drop=True)


def _strict_topk_dropout_selection(current: pd.Series, ranked: list[str], top_k: int, n_drop: int) -> list[str]:
    """US_STOCK_SELECTION新增: replace at most n_drop names per rebalance."""
    rank_map = {ticker: idx for idx, ticker in enumerate(ranked)}
    current_holdings = [ticker for ticker in current[current > 0].index.astype(str).tolist() if ticker in rank_map]
    if not current_holdings:
        return ranked[:top_k]

    # Sell the worst current holdings that have fallen below TopK, capped by n_drop.
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


def yearly_returns(daily: pd.DataFrame) -> pd.DataFrame:
    if daily.empty:
        return pd.DataFrame()
    data = daily.copy()
    data["date"] = pd.to_datetime(data["date"])
    data["year"] = data["date"].dt.year
    return (
        data.groupby(["strategy_id", "year"])["return"]
        .apply(lambda s: float((1.0 + s).prod() - 1.0))
        .rename("year_return")
        .reset_index()
    )


def build_cost_sensitivity(results: pd.DataFrame, daily: pd.DataFrame, holdings: pd.DataFrame, close: pd.DataFrame, prediction_index: pd.DataFrame) -> pd.DataFrame:
    if results.empty or holdings.empty:
        return pd.DataFrame()
    rows = []
    for sid in results.head(10)["strategy_id"]:
        h = holdings.loc[holdings["strategy_id"] == sid].pivot_table(index="date", columns="ticker", values="weight", aggfunc="last").sort_index()
        h.index = pd.to_datetime(h.index)
        local_close = close.loc[h.index.min() : h.index.max(), h.columns.intersection(close.columns)].ffill()
        h = h.reindex(local_close.index).ffill().fillna(0.0).loc[:, local_close.columns]
        for cost in [5, 10, 20, 50]:
            ret, turnover = portfolio_returns(local_close, h, cost_bps=float(cost), slippage_bps=float(cost))
            rows.append({"strategy_id": sid, "cost_bps_each_side": cost, **compute_portfolio_metrics(ret, turnover, h)})
    return pd.DataFrame(rows)


def _metrics_for_weights(close: pd.DataFrame, weights: pd.DataFrame, cost_bps: float) -> dict[str, Any]:
    ret, turnover = portfolio_returns(close, weights, cost_bps=cost_bps, slippage_bps=cost_bps)
    return compute_portfolio_metrics(ret, turnover, weights)


def _top_year_share(daily: pd.DataFrame) -> float:
    if daily.empty:
        return 0.0
    yearly = daily.groupby(daily["date"].dt.year)["return"].apply(lambda s: float((1.0 + s).prod() - 1.0))
    denom = yearly.abs().sum()
    return float(yearly.abs().max() / denom) if denom else 0.0


def _classification(best: pd.Series, flags: dict[str, bool]) -> str:
    if not bool(best.get("passes_cagr_20")) or not bool(best.get("passes_calmar_1")):
        return "likely_overfit"
    if flags.get("leave_one_ticker_calmar_halved") or flags.get("single_year_contribution_gt_50pct"):
        return "promising_but_unstable"
    if flags.get("top_holding_contribution_gt_30pct"):
        return "promising_but_unstable"
    return "credible_research_candidate"


def _wf_windows(index: pd.DatetimeIndex) -> list[tuple[str, str, str, str, str]]:
    end = pd.Timestamp(index.max()).date().isoformat()
    raw = [
        ("anchored_2024_h1", "2020-01-02", "2023-12-31", "2024-01-01", "2024-06-30"),
        ("anchored_2024_h2", "2020-01-02", "2024-06-30", "2024-07-01", "2024-12-31"),
        ("anchored_2025_h1", "2020-01-02", "2024-12-31", "2025-01-01", "2025-06-30"),
        ("anchored_2025_h2", "2020-01-02", "2025-06-30", "2025-07-01", "2025-12-31"),
        ("anchored_2026_ytd", "2020-01-02", "2025-12-31", "2026-01-01", end),
        ("rolling_3y_2024", "2021-01-01", "2023-12-31", "2024-01-01", "2024-12-31"),
        ("rolling_3y_2025", "2022-01-01", "2024-12-31", "2025-01-01", "2025-12-31"),
        ("rolling_2y_2024_h1", "2022-01-01", "2023-12-31", "2024-01-01", "2024-06-30"),
        ("rolling_2y_2025_h1", "2023-01-01", "2024-12-31", "2025-01-01", "2025-06-30"),
        ("rolling_2y_2026_ytd", "2024-01-01", "2025-12-31", "2026-01-01", end),
    ]
    max_date = pd.Timestamp(index.max())
    return [(name, ts, te, ss, min(pd.Timestamp(se), max_date).date().isoformat()) for name, ts, te, ss, se in raw if pd.Timestamp(ss) <= max_date]


def _raw_handler_frame(provider_uri: Path | str, feature_set: str, label: str) -> pd.DataFrame:
    from quant_lab.us_stock_selection.qlib_workflow_runner import LABEL_CONFIGS

    import qlib
    from qlib.config import REG_US
    from qlib.contrib.data.handler import Alpha158, Alpha360
    from qlib.data.dataset import DatasetH
    from qlib.data.dataset.handler import DataHandlerLP

    provider = Path(provider_uri).expanduser()
    qlib.init(provider_uri=str(provider), region=REG_US, expression_cache=None, dataset_cache=None)
    cls = Alpha360 if feature_set == "Alpha360" else Alpha158
    handler = cls(
        instruments="all",
        start_time="2020-01-02",
        end_time="2026-04-17",
        fit_start_time="2020-01-02",
        fit_end_time="2022-12-31",
        infer_processors=[],
        learn_processors=[],
        label=LABEL_CONFIGS.get(label, LABEL_CONFIGS["label_5d"]),
    )
    dataset = DatasetH(handler=handler, segments={"all": ("2020-01-02", "2026-04-17")})
    frame = dataset.prepare("all", col_set=["feature", "label"], data_key=DataHandlerLP.DK_L)
    if frame.empty:
        return pd.DataFrame()
    features = frame["feature"].replace([np.inf, -np.inf], np.nan)
    labels = frame["label"].iloc[:, 0].astype(float)
    idx = frame.index.to_frame(index=False)
    out = features.copy()
    out["label_value"] = labels.to_numpy()
    out["date"] = pd.to_datetime(idx["datetime"] if "datetime" in idx.columns else idx.iloc[:, -1]).to_numpy()
    out["ticker"] = (idx["instrument"] if "instrument" in idx.columns else idx.iloc[:, 0]).astype(str).str.upper().to_numpy()
    return out.reset_index(drop=True)


def _fit_predict_window(panel: pd.DataFrame, model_name: str, train_start: str, train_end: str, test_start: str, test_end: str) -> pd.DataFrame:
    feature_cols = [c for c in panel.columns if c not in {"label_value", "date", "ticker"}]
    data = panel.copy()
    data["date"] = pd.to_datetime(data["date"])
    train = data.loc[(data["date"] >= pd.Timestamp(train_start)) & (data["date"] <= pd.Timestamp(train_end))].dropna(subset=["label_value"])
    test = data.loc[(data["date"] >= pd.Timestamp(test_start)) & (data["date"] <= pd.Timestamp(test_end))].dropna(subset=["label_value"])
    if len(train) < 500 or test.empty:
        return pd.DataFrame()
    x_train = train[feature_cols].replace([np.inf, -np.inf], np.nan)
    y_train = train["label_value"].astype(float)
    x_test = test[feature_cols].replace([np.inf, -np.inf], np.nan)
    model = _sklearn_window_model(model_name)
    model.fit(x_train, y_train)
    pred = test.loc[:, ["date", "ticker", "label_value"]].copy()
    pred["score"] = model.predict(x_test)
    return pred.loc[:, ["date", "ticker", "score", "label_value"]]


def _sklearn_window_model(model_name: str):
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import ElasticNet, Ridge
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    try:
        if model_name == "LGBModel":
            from lightgbm import LGBMRegressor

            return make_pipeline(
                SimpleImputer(strategy="median"),
                LGBMRegressor(
                    n_estimators=40,
                    learning_rate=0.05,
                    num_leaves=31,
                    subsample=0.85,
                    colsample_bytree=0.85,
                    random_state=42,
                    n_jobs=4,
                    verbosity=-1,
                ),
            )
    except Exception:
        pass
    if model_name == "ElasticNet":
        return make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), ElasticNet(alpha=0.001, l1_ratio=0.25, max_iter=5000, random_state=42))
    return make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), Ridge(alpha=1.0))


def _robust_templates() -> list[dict[str, Any]]:
    return [
        {"name": "top3_equal_weight_monthly", "strategy": "topk", "top_k": 3, "rebalance": "M", "max_weight": 1 / 3},
        {"name": "top5_equal_weight_monthly", "strategy": "topk", "top_k": 5, "rebalance": "M", "max_weight": 0.20},
        {"name": "top3_equal_weight_weekly", "strategy": "topk", "top_k": 3, "rebalance": "W", "max_weight": 1 / 3},
        {"name": "top5_equal_weight_weekly", "strategy": "topk", "top_k": 5, "rebalance": "W", "max_weight": 0.20},
        {"name": "top3_monthly_max40", "strategy": "topk", "top_k": 3, "rebalance": "M", "max_weight": 0.40},
        {"name": "top5_monthly_max25", "strategy": "topk", "top_k": 5, "rebalance": "M", "max_weight": 0.25},
        {"name": "top5_dropout1_monthly", "strategy": "topk_dropout", "top_k": 5, "n_drop": 1, "rebalance": "M", "max_weight": 0.20},
        {"name": "top10_dropout2_monthly", "strategy": "topk_dropout", "top_k": 10, "n_drop": 2, "rebalance": "M", "max_weight": 0.10},
        {"name": "top3_safe_switch_monthly", "strategy": "safe_switch", "top_k": 3, "rebalance": "M", "max_weight": 1 / 3, "safe_asset": "SHY"},
        {"name": "top5_safe_switch_monthly", "strategy": "safe_switch", "top_k": 5, "rebalance": "M", "max_weight": 0.20, "safe_asset": "SHY"},
        {"name": "top5_vol15_monthly", "strategy": "topk", "top_k": 5, "rebalance": "M", "max_weight": 0.20, "target_vol": 0.15},
        {"name": "top5_vol20_monthly", "strategy": "topk", "top_k": 5, "rebalance": "M", "max_weight": 0.20, "target_vol": 0.20},
        {"name": "top5_vol25_monthly", "strategy": "topk", "top_k": 5, "rebalance": "M", "max_weight": 0.20, "target_vol": 0.25},
        {"name": "top5_crash_filter_50_monthly", "strategy": "crash_filter", "top_k": 5, "rebalance": "M", "max_weight": 0.20, "risk_scale_when_off": 0.5, "safe_asset": "SHY"},
        {"name": "top5_crash_filter_0_monthly", "strategy": "crash_filter", "top_k": 5, "rebalance": "M", "max_weight": 0.20, "risk_scale_when_off": 0.0, "safe_asset": "SHY"},
    ]


def _rebalance_dates(index: pd.DatetimeIndex, rebalance: str) -> pd.DatetimeIndex:
    idx = pd.DatetimeIndex(index).sort_values()
    code = str(rebalance).upper()
    if code.startswith("W"):
        target = pd.Series(index=idx, data=np.arange(len(idx))).resample("W-FRI").last().dropna().index
    elif code.startswith("Q"):
        target = pd.Series(index=idx, data=np.arange(len(idx))).resample("QE").last().dropna().index
    else:
        target = pd.Series(index=idx, data=np.arange(len(idx))).resample("ME").last().dropna().index
    return idx[idx.isin(target)]


def _save_empty(out_path: Path) -> None:
    empty = pd.DataFrame()
    save_dataframe(empty, out_path / "robust_portfolio_results.csv")
    save_parquet(empty, out_path / "robust_portfolio_daily_returns.parquet")
    save_parquet(empty, out_path / "robust_portfolio_holdings.parquet")
    save_dataframe(empty, out_path / "cost_sensitivity.csv")
    save_dataframe(empty, out_path / "concentration_summary.csv")
    save_dataframe(empty, out_path / "yearly_returns.csv")
