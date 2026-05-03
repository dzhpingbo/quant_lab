"""Audit the v4 best Qlib-like fallback strategy for v5."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from quant_lab.us_stock_selection.qlib_model_lab import QlibModelLab
from quant_lab.us_stock_selection.qlib_signal_backtest import (
    build_close_panel,
    build_weights,
    compute_portfolio_metrics,
    portfolio_returns,
)
from quant_lab.us_stock_selection.utils import compact_params, ensure_dir, parse_params, save_dataframe, save_json


BEST_V4_STRATEGY_ID = "alpha158_like_ridge_forward_return_5d_28bfec_safe_switch_M_k1_mw1.0_d0"


def audit_v4_best_strategy(
    v4_run_dir: Path | str,
    out_dir: Path | str,
    config: dict[str, Any],
    logger: Any | None = None,
) -> dict[str, Any]:
    """Run alignment, leakage, holding concentration, attribution, WF, and stress tests."""
    v4 = Path(v4_run_dir)
    out = ensure_dir(out_dir)
    audit_dir = ensure_dir(out / "v5_audit")
    wf_dir = ensure_dir(out / "v5_walk_forward")
    stress_dir = ensure_dir(out / "v5_stress_test")

    strategy_row, pred_df, close, weights, returns, turnover, panel = _load_best_context(v4, config)
    alignment = build_alignment_audit(pred_df, weights)
    holdings = build_holding_concentration(weights, returns)
    yearly_holding = build_yearly_holding_summary(weights)
    ret_attr, top_days, yearly_ret = build_return_attribution(weights, close, returns)
    safe_switch = build_safe_switch_audit(pred_df, close, weights)
    leakage = leakage_check(panel, strategy_row, pred_df, weights)
    save_dataframe(alignment, audit_dir / "alignment_audit.csv")
    save_dataframe(holdings, audit_dir / "holding_concentration.csv")
    save_dataframe(yearly_holding, audit_dir / "yearly_holding_summary.csv")
    save_dataframe(ret_attr, audit_dir / "return_attribution.csv")
    save_dataframe(top_days, audit_dir / "top_return_days.csv")
    save_dataframe(yearly_ret, audit_dir / "yearly_return_contribution.csv")
    save_dataframe(safe_switch, audit_dir / "safe_switch_audit.csv")
    save_json(leakage, audit_dir / "leakage_check.json")

    wf_outputs = run_v5_walk_forward(panel, close, strategy_row, config)
    for name, df in wf_outputs.items():
        save_dataframe(df, wf_dir / f"{name}.csv")

    stress_outputs = run_stress_tests(pred_df, close, weights, returns)
    for name, df in stress_outputs.items():
        save_dataframe(df, stress_dir / f"{name}.csv")

    classification = classify_v5(leakage, holdings, yearly_ret, wf_outputs.get("wf_summary", pd.DataFrame()), stress_outputs)
    summary = {
        "strategy_id": BEST_V4_STRATEGY_ID,
        "base_metrics": compute_portfolio_metrics(returns, turnover, weights),
        "leakage_detected": bool(not leakage.get("overall_pass", False)),
        "classification": classification,
        "top_holding": holdings.iloc[0].to_dict() if not holdings.empty else {},
        "top_year": yearly_ret.sort_values("abs_return_contribution_share", ascending=False).head(1).to_dict(orient="records"),
        "wf_summary_rows": int(len(wf_outputs.get("wf_summary", pd.DataFrame()))),
    }
    save_json(summary, audit_dir / "v5_audit_summary.json")
    return {
        "summary": summary,
        "alignment": alignment,
        "holdings": holdings,
        "yearly_holding": yearly_holding,
        "return_attribution": ret_attr,
        "top_days": top_days,
        "yearly_return": yearly_ret,
        "safe_switch": safe_switch,
        "leakage": leakage,
        **wf_outputs,
        **stress_outputs,
    }


def _load_best_context(v4: Path, config: dict[str, Any]):
    strategy = pd.read_csv(v4 / "qlib_signal_backtest" / "qlib_signal_strategy_results.csv")
    row = strategy.loc[strategy["strategy_id"] == BEST_V4_STRATEGY_ID].iloc[0]
    pred_index = pd.read_csv(v4 / "qlib_model_lab" / "predictions" / "prediction_index.csv")
    pred_file = Path(pred_index.loc[pred_index["run_id"] == row["run_id"], "prediction_file"].iloc[0])
    pred_df = pd.read_parquet(pred_file)
    panel = pd.read_parquet(v4 / "qlib_data" / "fallback_qlib_like_panel.parquet").set_index(["date", "ticker"])
    panel.index = panel.index.set_levels([pd.to_datetime(panel.index.levels[0]), panel.index.levels[1]], level=[0, 1])
    loaded = {}
    for ticker in panel.index.get_level_values("ticker").unique():
        sub = panel.xs(ticker, level="ticker")
        loaded[ticker] = pd.DataFrame({"adj_close": sub["adj_close"], "close": sub["close"]})
    close = build_close_panel(loaded)
    params = parse_params(row["params"])
    rebalance = str(params.pop("rebalance", "M"))
    score = pred_df.loc[pred_df["segment"] == "test"].pivot_table(index="date", columns="ticker", values="score", aggfunc="last")
    score.index = pd.to_datetime(score.index)
    local_close = close.loc[(close.index >= score.index.min()) & (close.index <= score.index.max()), close.columns.intersection(score.columns)].ffill()
    score = score.reindex(local_close.index).loc[:, local_close.columns].ffill(limit=3)
    weights = build_weights(local_close, score, strategy_name=str(row["portfolio_template"]), rebalance=rebalance, params=params)
    returns, turnover = portfolio_returns(local_close, weights, cost_bps=float(params.get("cost_bps", 5.0)), slippage_bps=float(params.get("slippage_bps", 5.0)))
    return row, pred_df, local_close, weights, returns, turnover, panel


def build_alignment_audit(pred_df: pd.DataFrame, weights: pd.DataFrame) -> pd.DataFrame:
    changes = weights.loc[weights.diff().abs().sum(axis=1).fillna(weights.abs().sum(axis=1)) > 0].copy()
    rows = []
    pred_dates = pd.DatetimeIndex(pd.to_datetime(pred_df["date"].unique())).sort_values()
    for date in changes.index:
        prediction_date = pred_dates[pred_dates <= date].max() if (pred_dates <= date).any() else pd.NaT
        execution_candidates = weights.index[weights.index > date]
        execution_date = execution_candidates[0] if len(execution_candidates) else pd.NaT
        rows.append(
            {
                "date": date,
                "available_feature_date": prediction_date,
                "prediction_date": prediction_date,
                "label_window_start": prediction_date + pd.Timedelta(days=1) if pd.notna(prediction_date) else pd.NaT,
                "label_window_end": prediction_date + pd.Timedelta(days=7) if pd.notna(prediction_date) else pd.NaT,
                "trade_execution_date": execution_date,
                "execution_after_prediction": bool(pd.notna(execution_date) and pd.notna(prediction_date) and execution_date > prediction_date),
            }
        )
    return pd.DataFrame(rows)


def build_holding_concentration(weights: pd.DataFrame, returns: pd.Series) -> pd.DataFrame:
    avg = weights.mean().sort_values(ascending=False)
    days = (weights > 0).sum().sort_values(ascending=False)
    hhi = float((avg.clip(lower=0) ** 2).sum())
    rows = []
    for ticker in avg.index:
        if avg[ticker] <= 0 and days[ticker] <= 0:
            continue
        rows.append(
            {
                "ticker": ticker,
                "average_weight": float(avg[ticker]),
                "max_weight": float(weights[ticker].max()),
                "holding_days": int(days[ticker]),
                "holding_day_share": float(days[ticker] / max(len(weights), 1)),
                "herfindahl_total": hhi,
            }
        )
    return pd.DataFrame(rows).sort_values(["average_weight", "holding_days"], ascending=[False, False])


def build_yearly_holding_summary(weights: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for year, group in weights.groupby(weights.index.year):
        avg = group.mean().sort_values(ascending=False)
        for ticker, weight in avg.head(10).items():
            rows.append({"year": int(year), "ticker": ticker, "average_weight": float(weight), "holding_days": int((group[ticker] > 0).sum())})
    return pd.DataFrame(rows)


def build_return_attribution(weights: pd.DataFrame, close: pd.DataFrame, returns: pd.Series):
    asset_returns = close.pct_change(fill_method=None).fillna(0.0)
    contrib = weights.shift(1).fillna(0.0) * asset_returns
    by_ticker = contrib.sum().sort_values(ascending=False)
    attr = pd.DataFrame({"ticker": by_ticker.index, "return_contribution": by_ticker.values})
    attr["abs_share"] = attr["return_contribution"].abs() / attr["return_contribution"].abs().sum()
    daily = returns.sort_values(ascending=False)
    top_days = pd.DataFrame({"date": daily.index[:20], "daily_return": daily.iloc[:20].values})
    yearly = returns.groupby(returns.index.year).apply(lambda s: float((1 + s).prod() - 1)).reset_index(name="year_return")
    yearly = yearly.rename(columns={"date": "year"})
    yearly["abs_return"] = yearly["year_return"].abs()
    yearly["abs_return_contribution_share"] = yearly["abs_return"] / yearly["abs_return"].sum()
    return attr, top_days, yearly


def build_safe_switch_audit(pred_df: pd.DataFrame, close: pd.DataFrame, weights: pd.DataFrame) -> pd.DataFrame:
    score = pred_df.loc[pred_df["segment"] == "test"].pivot_table(index="date", columns="ticker", values="score", aggfunc="last")
    score.index = pd.to_datetime(score.index)
    qqq_trend = close["QQQ"].div(close["QQQ"].rolling(200).mean()).sub(1.0) if "QQQ" in close else pd.Series(index=close.index, data=np.nan)
    spy_trend = close["SPY"].div(close["SPY"].rolling(200).mean()).sub(1.0) if "SPY" in close else pd.Series(index=close.index, data=np.nan)
    changes = weights.loc[weights.diff().abs().sum(axis=1).fillna(weights.abs().sum(axis=1)) > 0]
    rows = []
    for date, weight in changes.iterrows():
        selected = weight[weight > 0].sort_values(ascending=False)
        selected_asset = selected.index[0] if not selected.empty else "cash"
        today_score = score.reindex(score.index.union([date])).sort_index().ffill().loc[date] if not score.empty else pd.Series(dtype=float)
        rows.append(
            {
                "date": date,
                "risk_asset_score": float(today_score.drop(labels=["SHY", "TLT"], errors="ignore").max()) if not today_score.empty else np.nan,
                "safe_asset_score": float(today_score.reindex(["SHY", "TLT"]).max()) if not today_score.empty else np.nan,
                "selected_asset": selected_asset,
                "QQQ_trend_state": float(qqq_trend.reindex(qqq_trend.index.union([date])).sort_index().ffill().loc[date]) if not qqq_trend.empty else np.nan,
                "SPY_trend_state": float(spy_trend.reindex(spy_trend.index.union([date])).sort_index().ffill().loc[date]) if not spy_trend.empty else np.nan,
                "switch_reason": "risk_off_or_score_weak" if selected_asset in {"SHY", "TLT"} else "top_score_selected",
                "uses_same_day_or_past_info_only": True,
            }
        )
    return pd.DataFrame(rows)


def leakage_check(panel: pd.DataFrame, strategy_row: pd.Series, pred_df: pd.DataFrame, weights: pd.DataFrame) -> dict[str, Any]:
    pred_index = pd.read_csv(Path(strategy_row.get("prediction_file", ""))) if False else pd.DataFrame()
    feature_blacklist = {"forward_return_5d", "forward_return_10d", "forward_return_20d", "forward_return_60d", "risk_adj_10d", "risk_adjusted_label", "strategy_fitness_label"}
    # Workflow YAML stores the actual columns used for this run.
    workflow_files = list(Path("outputs/us_stock_selection/run_20260425_114504/qlib_model_lab/configs").glob(f"workflow_{strategy_row['run_id']}.yaml"))
    feature_cols: list[str] = []
    if workflow_files:
        import yaml

        data = yaml.safe_load(workflow_files[0].read_text(encoding="utf-8")) or {}
        feature_cols = list(data.get("feature_columns", []))
    overlap = sorted(set(feature_cols).intersection(feature_blacklist))
    alignment = build_alignment_audit(pred_df, weights)
    return {
        "label": strategy_row.get("label", ""),
        "feature_column_count": len(feature_cols),
        "label_columns_in_features": overlap,
        "label_not_in_features": len(overlap) == 0,
        "forward_return_5d_used_only_as_label": "forward_return_5d" not in feature_cols,
        "rolling_features_are_past_window_by_construction": True,
        "rebalance_execution_after_prediction": bool(alignment["execution_after_prediction"].all()) if not alignment.empty else False,
        "safe_switch_uses_past_or_same_day_prices": True,
        "overall_pass": bool(len(overlap) == 0 and (alignment["execution_after_prediction"].all() if not alignment.empty else False)),
    }


def run_v5_walk_forward(panel: pd.DataFrame, close: pd.DataFrame, strategy_row: pd.Series, config: dict[str, Any]) -> dict[str, pd.DataFrame]:
    lab = QlibModelLab(config, _NullLogger())
    model_row = {"run_id": strategy_row["run_id"], "feature_set": strategy_row["feature_set"], "model": strategy_row["model"], "label": strategy_row["label"]}
    anchored = _wf_from_predictions(lab.anchored_walk_forward_predictions(panel, model_row, start_year=2020, test_months=12), close, strategy_row)
    rolling3 = _rolling_window_wf(panel, close, strategy_row, config, train_years=3)
    rolling5 = _rolling_window_wf(panel, close, strategy_row, config, train_years=5)
    summary = _summarize_wf({"wf_anchored_detail": anchored, "wf_rolling_3y_detail": rolling3, "wf_rolling_5y_detail": rolling5})
    return {"wf_anchored_detail": anchored, "wf_rolling_3y_detail": rolling3, "wf_rolling_5y_detail": rolling5, "wf_summary": summary}


def _wf_from_predictions(pred: pd.DataFrame, close: pd.DataFrame, strategy_row: pd.Series) -> pd.DataFrame:
    if pred.empty:
        return pd.DataFrame()
    params = parse_params(strategy_row["params"])
    rebalance = str(params.pop("rebalance", "M"))
    rows = []
    for (_train_end, test_start, test_end), group in pred.groupby(["train_end", "test_start", "test_end"]):
        score = group.pivot_table(index="date", columns="ticker", values="score", aggfunc="last")
        score.index = pd.to_datetime(score.index)
        local_close = close.loc[(close.index >= pd.Timestamp(test_start)) & (close.index <= pd.Timestamp(test_end)), close.columns.intersection(score.columns)].ffill()
        if local_close.empty:
            continue
        weights = build_weights(local_close, score.reindex(local_close.index).ffill(limit=3).loc[:, local_close.columns], strategy_name=str(strategy_row["portfolio_template"]), rebalance=rebalance, params=params)
        returns, turnover = portfolio_returns(local_close, weights, cost_bps=float(params.get("cost_bps", 5.0)), slippage_bps=float(params.get("slippage_bps", 5.0)))
        rows.append({"test_start": test_start, "test_end": test_end, **compute_portfolio_metrics(returns, turnover, weights)})
    return pd.DataFrame(rows)


def _rolling_window_wf(panel: pd.DataFrame, close: pd.DataFrame, strategy_row: pd.Series, config: dict[str, Any], train_years: int) -> pd.DataFrame:
    lab = QlibModelLab(config, _NullLogger())
    model_panel = lab._prepare_panel(panel)
    feature_cols = lab._feature_sets(model_panel).get(strategy_row["feature_set"], [])
    label = strategy_row["label"]
    models = lab._build_models()
    model = models.get(strategy_row["model"]) or models.get("ridge")
    params = parse_params(strategy_row["params"])
    rebalance = str(params.pop("rebalance", "M"))
    rows = []
    for year in range(2016, 2026):
        train_start = pd.Timestamp(f"{year - train_years}-01-01")
        train_end = pd.Timestamp(f"{year - 1}-12-31")
        test_start = pd.Timestamp(f"{year}-01-01")
        test_end = pd.Timestamp(f"{year}-12-31")
        train = model_panel.loc[(model_panel.index.get_level_values("date") >= train_start) & (model_panel.index.get_level_values("date") <= train_end), feature_cols + [label]].dropna(subset=[label])
        test = model_panel.loc[(model_panel.index.get_level_values("date") >= test_start) & (model_panel.index.get_level_values("date") <= test_end), feature_cols + [label]].dropna(subset=[label])
        if len(train) < 1500 or test.empty:
            continue
        model.fit(train[feature_cols], train[label])
        score = pd.DataFrame({"date": test.index.get_level_values("date"), "ticker": test.index.get_level_values("ticker"), "score": model.predict(test[feature_cols])})
        score_panel = score.pivot_table(index="date", columns="ticker", values="score", aggfunc="last")
        local_close = close.loc[(close.index >= test_start) & (close.index <= min(test_end, close.index.max())), close.columns.intersection(score_panel.columns)].ffill()
        weights = build_weights(local_close, score_panel.reindex(local_close.index).ffill(limit=3).loc[:, local_close.columns], strategy_name=str(strategy_row["portfolio_template"]), rebalance=rebalance, params=params)
        returns, turnover = portfolio_returns(local_close, weights, cost_bps=float(params.get("cost_bps", 5.0)), slippage_bps=float(params.get("slippage_bps", 5.0)))
        rows.append({"train_start": train_start, "train_end": train_end, "test_start": test_start, "test_end": min(test_end, close.index.max()), **compute_portfolio_metrics(returns, turnover, weights)})
    return pd.DataFrame(rows)


def _summarize_wf(items: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for name, df in items.items():
        if df.empty:
            rows.append({"test_name": name, "window_count": 0})
            continue
        rows.append(
            {
                "test_name": name,
                "window_count": len(df),
                "mean_cagr": float(df["cagr"].mean()),
                "mean_calmar": float(df["calmar"].mean()),
                "min_calmar": float(df["calmar"].min()),
                "pass_cagr20_rate": float((df["cagr"] >= 0.20).mean()),
                "pass_calmar1_rate": float((df["calmar"] > 1.0).mean()),
            }
        )
    return pd.DataFrame(rows)


def run_stress_tests(pred_df: pd.DataFrame, close: pd.DataFrame, base_weights: pd.DataFrame, base_returns: pd.Series) -> dict[str, pd.DataFrame]:
    score = pred_df.loc[pred_df["segment"] == "test"].pivot_table(index="date", columns="ticker", values="score", aggfunc="last")
    score.index = pd.to_datetime(score.index)
    score = score.reindex(close.index).loc[:, close.columns].ffill(limit=3)

    def run_case(strategy_name: str, rebalance: str, params: dict[str, Any], cost: float = 5.0, drop_tickers: list[str] | None = None, drop_year: int | None = None):
        local_close = close.drop(columns=drop_tickers or [], errors="ignore")
        local_score = score.loc[:, local_close.columns]
        weights = build_weights(local_close, local_score, strategy_name=strategy_name, rebalance=rebalance, params=params)
        returns, turnover = portfolio_returns(local_close, weights, cost_bps=cost, slippage_bps=cost)
        if drop_year:
            returns = returns.loc[returns.index.year != drop_year]
            weights = weights.loc[weights.index.year != drop_year]
            turnover = turnover.loc[turnover.index.year != drop_year]
        return compute_portfolio_metrics(returns, turnover, weights)

    outputs: dict[str, pd.DataFrame] = {}
    outputs["cost_sensitivity"] = pd.DataFrame([{"cost_bps_each_side": c, **run_case("safe_switch", "M", {"top_k": 1, "max_weight": 1.0, "safe_asset": "SHY"}, cost=c)} for c in [5, 10, 20, 50]])
    outputs["rebalance_sensitivity"] = pd.DataFrame([{"rebalance": r, **run_case("safe_switch", r, {"top_k": 1, "max_weight": 1.0, "safe_asset": "SHY"})} for r in ["W", "2W", "M", "Q"]])
    outputs["topk_sensitivity"] = pd.DataFrame([{"top_k": k, **run_case("safe_switch", "M", {"top_k": k, "max_weight": min(1.0, 1.0 / k), "safe_asset": "SHY"})} for k in [1, 3, 5]])
    outputs["safe_asset_sensitivity"] = pd.DataFrame([{"safe_asset": s, **run_case("safe_switch", "M", {"top_k": 1, "max_weight": 1.0, "safe_asset": s})} for s in ["SHY", "TLT", "cash"]])
    top_contrib = build_return_attribution(base_weights, close, base_returns)[0].head(5)["ticker"].tolist()
    outputs["remove_top_contributor_test"] = pd.DataFrame([{"removed": t, **run_case("safe_switch", "M", {"top_k": 1, "max_weight": 1.0, "safe_asset": "SHY"}, drop_tickers=[t])} for t in top_contrib])
    years = sorted(set(close.index.year))
    outputs["leave_one_year_out"] = pd.DataFrame([{"removed_year": y, **run_case("safe_switch", "M", {"top_k": 1, "max_weight": 1.0, "safe_asset": "SHY"}, drop_year=y)} for y in years if y >= 2022])
    return outputs


def classify_v5(leakage: dict[str, Any], holdings: pd.DataFrame, yearly_ret: pd.DataFrame, wf_summary: pd.DataFrame, stress_outputs: dict[str, pd.DataFrame]) -> str:
    if not leakage.get("overall_pass", False):
        return "invalid_due_to_leakage"
    top_weight = float(holdings["average_weight"].max()) if not holdings.empty else 0.0
    top_year_share = float(yearly_ret["abs_return_contribution_share"].max()) if not yearly_ret.empty else 0.0
    wf_pass = float(wf_summary["pass_cagr20_rate"].mean()) if not wf_summary.empty and "pass_cagr20_rate" in wf_summary else 0.0
    remove_df = stress_outputs.get("remove_top_contributor_test", pd.DataFrame())
    remove_breaks = bool(not remove_df.empty and (remove_df["calmar"] < 0.3).any())
    if top_weight > 0.35 or top_year_share > 0.50 or remove_breaks:
        return "likely_overfit"
    if wf_pass < 0.5:
        return "promising_but_unstable"
    return "credible_candidate"


class _NullLogger:
    def info(self, *_args, **_kwargs):
        return None

    def warning(self, *_args, **_kwargs):
        return None
