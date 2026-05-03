"""v8.1 model switch replay for LGBModel and Ridge.

This module keeps the v7 strategy frozen and changes only the main model away
from ElasticNet. It does not expand the universe and does not perform a new
strategy search.
"""

from __future__ import annotations

import json
import math
import shutil
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from quant_lab.us_stock_selection.feature_cache import load_feature_cache
from quant_lab.us_stock_selection.qlib_signal_backtest import compute_portfolio_metrics
from quant_lab.us_stock_selection.qlib_workflow_runner import load_close_from_provider
from quant_lab.us_stock_selection.utils import ensure_dir, nav_from_returns, save_dataframe, save_json, save_text
from quant_lab.us_stock_selection.v8_execution_sim import build_attribution, evaluate_weights, weights_from_decisions
from quant_lab.us_stock_selection.v8_paper_trading import (
    FROZEN_PORTFOLIO,
    ModelSpec,
    fit_model,
    latest_available_feature_date,
    rebalance_dates,
    run_paper_trading_replay,
    trading_offset,
)


MODEL_SPECS: dict[str, ModelSpec] = {
    "LGBModel": ModelSpec(
        "LGBModel",
        feature_set="Alpha360",
        label="label_5d",
        params={
            "n_estimators": 80,
            "learning_rate": 0.05,
            "num_leaves": 31,
            "subsample": 0.85,
            "colsample_bytree": 0.85,
        },
    ),
    "Ridge": ModelSpec("Ridge", feature_set="Alpha360", label="label_5d", params={"alpha": 1.0}),
}


def run_v8_1_model_switch(
    out_dir: Path | str,
    cache_dir: Path | str,
    provider_uri: Path | str,
    models: list[str] | None = None,
    resume: bool = True,
    logger: Any | None = None,
) -> dict[str, Any]:
    """Run full v8.1 replay/stress/attribution for selected model names."""
    out = ensure_dir(out_dir)
    models = models or ["LGBModel", "Ridge"]
    close_full = load_close_from_provider(provider_uri, start="2020-01-01")
    close_full = close_full.loc[(close_full.index >= "2020-01-01") & (close_full.index <= "2026-04-17")].ffill()

    model_outputs: dict[str, dict[str, Any]] = {}
    summary_rows: list[dict[str, Any]] = []
    for model_name in models:
        if model_name not in MODEL_SPECS:
            raise ValueError(f"Unsupported v8.1 model: {model_name}")
        spec = MODEL_SPECS[model_name]
        tag = f"{spec.feature_set}_{spec.name}"
        model_dir = ensure_dir(out / tag)
        if logger:
            logger.info(f"Running v8.1 model switch branch {tag}")

        paper = load_or_run_paper_replay(model_dir, cache_dir, provider_uri, spec, resume=resume, logger=logger)
        close = paper["close"]
        weights = paper["weights"]
        returns = paper["returns"]

        stress = load_or_run_execution_stress(model_dir, paper["decisions"], close, weights, returns, spec, cache_dir, provider_uri, resume=resume, logger=logger)
        attribution = load_or_run_attribution(model_dir, close, weights, returns, resume=resume, logger=logger)
        leave_ticker = load_or_run_leave_one_ticker(model_dir, paper["decisions"], close, attribution["ticker_contribution"], resume=resume)
        leave_year = load_or_run_leave_one_year(model_dir, weights, returns, resume=resume)
        stability = load_or_run_model_diagnostics(model_dir, cache_dir, provider_uri, spec, close_full, resume=resume, logger=logger)

        verdict = classify_model_candidate(
            model_name=tag,
            paper_metrics=paper["metrics"],
            stress=stress,
            attribution=attribution,
            leave_one_ticker=leave_ticker,
            leave_one_year=leave_year,
            stability=stability,
        )
        save_json(verdict, model_dir / "v8_1_model_verdict.json")
        model_outputs[tag] = {
            "paper": paper,
            "stress": stress,
            "attribution": attribution,
            "leave_one_ticker": leave_ticker,
            "leave_one_year": leave_year,
            "stability": stability,
            "verdict": verdict,
        }
        summary_rows.append(verdict)

    summary = pd.DataFrame(summary_rows)
    save_dataframe(summary, out / "v8_1_model_switch_summary.csv")
    cycle_verdict = classify_cycle(summary)
    save_json(cycle_verdict, out / "v8_1_cycle_verdict.json")
    return {"models": model_outputs, "summary": summary, "cycle_verdict": cycle_verdict}


def load_or_run_paper_replay(
    model_dir: Path,
    cache_dir: Path | str,
    provider_uri: Path | str,
    spec: ModelSpec,
    resume: bool,
    logger: Any | None,
) -> dict[str, Any]:
    metrics_path = model_dir / "paper_trading_metrics.csv"
    if resume and metrics_path.exists() and (model_dir / "monthly_decision_ledger.csv").exists():
        if logger:
            logger.info(f"Reusing paper replay for {model_dir.name}")
        return load_paper_outputs(model_dir, provider_uri)

    result = run_paper_trading_replay(
        model_dir,
        cache_dir=cache_dir,
        provider_uri=provider_uri,
        model_spec=spec,
        execution_delay=1,
        cost_bps=5.0,
        slippage_bps=5.0,
        max_weight=0.20,
        rebalance_timing="month_end",
        save_outputs=True,
        save_audit_trail=True,
        audit_forward_returns=True,
    )
    audit_src = model_dir / "v8_2_score_rank_audit_trail.csv"
    if audit_src.exists():
        shutil.copy2(audit_src, model_dir / "score_rank_audit_trail.csv")
    return result


def load_paper_outputs(model_dir: Path, provider_uri: Path | str) -> dict[str, Any]:
    decisions = pd.read_csv(model_dir / "monthly_decision_ledger.csv")
    daily_nav = pd.read_csv(model_dir / "daily_nav.csv")
    daily_nav["date"] = pd.to_datetime(daily_nav["date"])
    returns = pd.Series(daily_nav["return"].to_numpy(dtype=float), index=pd.DatetimeIndex(daily_nav["date"]))
    metrics_df = pd.read_csv(model_dir / "paper_trading_metrics.csv")
    metrics = metrics_df.iloc[0].to_dict()
    close = load_close_from_provider(provider_uri, start="2020-01-01")
    close = close.loc[(close.index >= "2020-01-01") & (close.index <= "2026-04-17")].ffill()
    weights = weights_from_decisions(decisions, close, execution_delay=1, max_weight=0.20)
    weights = weights.reindex(close.index).ffill().fillna(0.0)
    return {
        "metrics": metrics,
        "metrics_df": metrics_df,
        "decisions": decisions,
        "daily_nav": daily_nav,
        "monthly_holdings": pd.read_csv(model_dir / "monthly_holdings.csv") if (model_dir / "monthly_holdings.csv").exists() else pd.DataFrame(),
        "trades": pd.read_csv(model_dir / "trades.csv") if (model_dir / "trades.csv").exists() else pd.DataFrame(),
        "convergence": pd.read_csv(model_dir / "fit_convergence_log.csv") if (model_dir / "fit_convergence_log.csv").exists() else pd.DataFrame(),
        "weights": weights,
        "close": close.loc[returns.index.min() : returns.index.max(), weights.columns].ffill(),
        "returns": returns,
        "turnover": pd.Series(index=returns.index, data=np.nan),
    }


def load_or_run_execution_stress(
    model_dir: Path,
    decisions: pd.DataFrame,
    close: pd.DataFrame,
    weights: pd.DataFrame,
    primary_returns: pd.Series,
    spec: ModelSpec,
    cache_dir: Path | str,
    provider_uri: Path | str,
    resume: bool,
    logger: Any | None,
) -> pd.DataFrame:
    path = model_dir / "execution_stress_results.csv"
    if resume and path.exists():
        return pd.read_csv(path)
    rows: list[dict[str, Any]] = []
    for cost in [5, 10, 20, 50]:
        for slip in [0, 5, 10, 20]:
            for delay in [0, 1, 2]:
                for max_weight in [0.20, 0.25, 0.30]:
                    stress_weights = weights_from_decisions(decisions, close, execution_delay=delay, max_weight=max_weight)
                    metrics, _, _ = evaluate_weights(close, stress_weights, cost_bps=float(cost), slippage_bps=float(slip))
                    rows.append(
                        {
                            "model_branch": f"{spec.feature_set}_{spec.name}",
                            "test_name": f"cost{cost}_slip{slip}_delay{delay}_mw{max_weight}",
                            "stress_type": "execution_grid",
                            "cost_bps": cost,
                            "slippage_bps": slip,
                            "execution_delay": delay,
                            "max_weight": max_weight,
                            **metrics,
                        }
                    )
    # Month-start replay is a model re-run, but it keeps the same frozen rule and
    # is needed as a rebalance timing stress. Resume keeps it from repeating.
    ms_path = model_dir / "month_start_paper_trading_metrics.csv"
    if resume and ms_path.exists():
        month_start_metrics = pd.read_csv(ms_path).iloc[0].to_dict()
    else:
        if logger:
            logger.info(f"Running month-start timing stress for {spec.name}")
        month_start = run_paper_trading_replay(
            model_dir / "month_start_replay",
            cache_dir=cache_dir,
            provider_uri=provider_uri,
            model_spec=spec,
            execution_delay=1,
            cost_bps=5.0,
            slippage_bps=5.0,
            max_weight=0.20,
            rebalance_timing="month_start",
            save_outputs=False,
            save_audit_trail=False,
            audit_forward_returns=False,
        )
        month_start_metrics = month_start["metrics"]
        save_dataframe(pd.DataFrame([month_start_metrics]), ms_path)
    rows.append(
        {
            "model_branch": f"{spec.feature_set}_{spec.name}",
            "test_name": "month_start_rebalance",
            "stress_type": "rebalance_timing",
            **month_start_metrics,
        }
    )
    stress = pd.DataFrame(rows)
    save_dataframe(stress, path)
    return stress


def load_or_run_attribution(
    model_dir: Path,
    close: pd.DataFrame,
    weights: pd.DataFrame,
    returns: pd.Series,
    resume: bool,
    logger: Any | None,
) -> dict[str, pd.DataFrame]:
    ticker_path = model_dir / "attribution_ticker_contribution.csv"
    yearly_path = model_dir / "attribution_yearly_return.csv"
    if resume and ticker_path.exists() and yearly_path.exists():
        return {
            "holding_concentration": pd.read_csv(model_dir / "holding_concentration.csv") if (model_dir / "holding_concentration.csv").exists() else pd.DataFrame(),
            "ticker_contribution": pd.read_csv(ticker_path),
            "yearly": pd.read_csv(yearly_path),
            "monthly": pd.read_csv(model_dir / "attribution_monthly_return.csv") if (model_dir / "attribution_monthly_return.csv").exists() else pd.DataFrame(),
            "top_months": pd.read_csv(model_dir / "top_return_months.csv") if (model_dir / "top_return_months.csv").exists() else pd.DataFrame(),
        }
    raw = build_attribution(model_dir, close, weights, returns)
    shutil.copy2(model_dir / "ticker_contribution.csv", ticker_path)
    shutil.copy2(model_dir / "yearly_return.csv", yearly_path)
    shutil.copy2(model_dir / "monthly_return.csv", model_dir / "attribution_monthly_return.csv")
    return raw


def load_or_run_leave_one_ticker(
    model_dir: Path,
    decisions: pd.DataFrame,
    close: pd.DataFrame,
    ticker_contribution: pd.DataFrame,
    resume: bool,
) -> pd.DataFrame:
    path = model_dir / "leave_one_ticker_out.csv"
    if resume and path.exists():
        return pd.read_csv(path)
    tickers = []
    if "ticker" in ticker_contribution:
        tickers = ticker_contribution["ticker"].dropna().astype(str).tolist()
    if not tickers:
        for selected in decisions.get("selected_tickers", pd.Series(dtype=str)).dropna().astype(str):
            tickers.extend([x for x in selected.split(",") if x])
        tickers = sorted(set(tickers))
    rows = []
    for ticker in tickers:
        weights = weights_from_decisions(decisions, close, execution_delay=1, max_weight=0.20, remove_ticker=ticker)
        metrics, _, _ = evaluate_weights(close, weights, cost_bps=5.0, slippage_bps=5.0)
        rows.append({"removed_ticker": ticker, **metrics})
    df = pd.DataFrame(rows)
    save_dataframe(df, path)
    return df


def load_or_run_leave_one_year(
    model_dir: Path,
    weights: pd.DataFrame,
    returns: pd.Series,
    resume: bool,
) -> pd.DataFrame:
    path = model_dir / "leave_one_year_out.csv"
    if resume and path.exists():
        return pd.read_csv(path)
    rows = []
    for year in sorted(pd.Index(returns.index.year).unique()):
        mask = returns.index.year != int(year)
        ret = returns.loc[mask]
        w = weights.loc[weights.index.year != int(year)]
        if ret.empty or w.empty:
            continue
        turnover = w.diff().abs().sum(axis=1).fillna(w.abs().sum(axis=1))
        metrics = compute_portfolio_metrics(ret, turnover.reindex(ret.index).fillna(0.0), w.reindex(ret.index).fillna(0.0))
        rows.append({"removed_year": int(year), **metrics})
    df = pd.DataFrame(rows)
    save_dataframe(df, path)
    return df


def load_or_run_model_diagnostics(
    model_dir: Path,
    cache_dir: Path | str,
    provider_uri: Path | str,
    spec: ModelSpec,
    close: pd.DataFrame,
    resume: bool,
    logger: Any | None,
) -> dict[str, pd.DataFrame]:
    summary_path = model_dir / "model_stability_summary.csv"
    if resume and summary_path.exists():
        return {
            "summary": pd.read_csv(summary_path),
            "feature_importance": pd.read_csv(model_dir / "lgb_feature_importance_summary.csv") if (model_dir / "lgb_feature_importance_summary.csv").exists() else pd.DataFrame(),
            "ridge_coefficients": pd.read_csv(model_dir / "ridge_coefficient_summary.csv") if (model_dir / "ridge_coefficient_summary.csv").exists() else pd.DataFrame(),
            "selection_concentration": pd.read_csv(model_dir / "selection_concentration.csv") if (model_dir / "selection_concentration.csv").exists() else pd.DataFrame(),
        }
    frame, feature_cols = load_feature_cache(cache_dir, spec.feature_set)
    frame["date"] = pd.to_datetime(frame["date"])
    months = rebalance_dates(close.index, start="2024-01-01", end="2026-04-17", timing="month_end")
    rows = []
    importance_parts = []
    coef_parts = []
    warning_rows = []
    for decision_date in months:
        feature_date = latest_available_feature_date(frame, decision_date)
        train_end = trading_offset(close.index, pd.Timestamp(decision_date), -6)
        if pd.isna(feature_date) or pd.isna(train_end):
            continue
        train = frame.loc[(frame["date"] <= train_end) & frame[spec.label].notna()].copy()
        pred = frame.loc[frame["date"] == feature_date].copy()
        if len(train) < 500 or pred.empty:
            continue
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            model, fit_info = fit_model(train, pred, feature_cols, spec)
        warning_rows.append({"decision_date": pd.Timestamp(decision_date).date().isoformat(), **fit_info})
        estimator = model.steps[-1][1] if hasattr(model, "steps") else model
        if hasattr(estimator, "feature_importances_"):
            imp = pd.DataFrame(
                {
                    "decision_date": pd.Timestamp(decision_date).date().isoformat(),
                    "feature": feature_cols,
                    "importance": np.asarray(estimator.feature_importances_, dtype=float),
                }
            )
            importance_parts.append(imp)
        if hasattr(estimator, "coef_"):
            coef = pd.DataFrame(
                {
                    "decision_date": pd.Timestamp(decision_date).date().isoformat(),
                    "feature": feature_cols,
                    "coefficient": np.asarray(estimator.coef_, dtype=float),
                }
            )
            coef_parts.append(coef)
    warning_df = pd.DataFrame(warning_rows)
    save_dataframe(warning_df, model_dir / "model_fit_warning_log.csv")
    importance_summary = pd.DataFrame()
    coef_summary = pd.DataFrame()
    top_feature_share = 0.0
    if importance_parts:
        importance = pd.concat(importance_parts, ignore_index=True)
        save_dataframe(importance, model_dir / "lgb_feature_importance_by_decision.csv")
        importance_summary = (
            importance.groupby("feature", as_index=False)
            .agg(mean_importance=("importance", "mean"), std_importance=("importance", "std"))
            .sort_values("mean_importance", ascending=False)
        )
        total = float(importance_summary["mean_importance"].sum())
        top_feature_share = float(importance_summary["mean_importance"].head(10).sum() / total) if total > 0 else 0.0
        save_dataframe(importance_summary, model_dir / "lgb_feature_importance_summary.csv")
    if coef_parts:
        coef = pd.concat(coef_parts, ignore_index=True)
        save_dataframe(coef, model_dir / "ridge_coefficients_by_decision.csv")
        coef_summary = (
            coef.groupby("feature", as_index=False)
            .agg(mean_coefficient=("coefficient", "mean"), std_coefficient=("coefficient", "std"), mean_abs_coefficient=("coefficient", lambda s: float(np.mean(np.abs(s)))))
            .sort_values("mean_abs_coefficient", ascending=False)
        )
        save_dataframe(coef_summary, model_dir / "ridge_coefficient_summary.csv")
        save_dataframe(coef_summary.head(30), model_dir / "ridge_top_coefficients.csv")
    selection = selection_concentration(model_dir / "monthly_holdings.csv")
    save_dataframe(selection, model_dir / "selection_concentration.csv")
    summary = pd.DataFrame(
        [
            {
                "model": spec.name,
                "feature_set": spec.feature_set,
                "label": spec.label,
                "diagnostic_decision_count": int(len(warning_df)),
                "warning_count": int(warning_df["fit_warning_count"].sum()) if not warning_df.empty and "fit_warning_count" in warning_df else 0,
                "warning_decision_rate": float((warning_df["fit_warning_count"] > 0).mean()) if not warning_df.empty and "fit_warning_count" in warning_df else 0.0,
                "top10_feature_importance_share": top_feature_share,
                "max_ticker_selection_share": float(selection["selection_share"].max()) if not selection.empty else 0.0,
                "feature_concentration_flag": bool(top_feature_share > 0.50),
                "selection_concentration_flag": bool((selection["selection_share"].max() if not selection.empty else 0.0) > 0.50),
            }
        ]
    )
    save_dataframe(summary, summary_path)
    return {"summary": summary, "feature_importance": importance_summary, "ridge_coefficients": coef_summary, "selection_concentration": selection}


def selection_concentration(holdings_path: Path) -> pd.DataFrame:
    if not holdings_path.exists():
        return pd.DataFrame()
    holdings = pd.read_csv(holdings_path)
    if holdings.empty or "ticker" not in holdings:
        return pd.DataFrame()
    total_months = max(1, holdings["decision_date"].nunique()) if "decision_date" in holdings else max(1, len(holdings))
    out = holdings.groupby("ticker", as_index=False).agg(selected_count=("ticker", "size"), avg_weight=("weight", "mean"))
    out["selection_share"] = out["selected_count"] / float(total_months)
    return out.sort_values(["selection_share", "avg_weight"], ascending=False)


def classify_model_candidate(
    model_name: str,
    paper_metrics: dict[str, Any],
    stress: pd.DataFrame,
    attribution: dict[str, pd.DataFrame],
    leave_one_ticker: pd.DataFrame,
    leave_one_year: pd.DataFrame,
    stability: dict[str, pd.DataFrame],
) -> dict[str, Any]:
    cagr = float(paper_metrics.get("cagr", 0.0))
    calmar = float(paper_metrics.get("calmar", 0.0))
    cost50 = stress.loc[(stress["stress_type"] == "execution_grid") & (stress["cost_bps"] == 50) & (stress["slippage_bps"] == 5) & (stress["execution_delay"] == 1) & (stress["max_weight"] == 0.20)]
    cost50_cagr = float(cost50["cagr"].iloc[0]) if not cost50.empty else 0.0
    cost50_calmar = float(cost50["calmar"].iloc[0]) if not cost50.empty else 0.0
    t2 = stress.loc[(stress["stress_type"] == "execution_grid") & (stress["cost_bps"] == 5) & (stress["slippage_bps"] == 5) & (stress["execution_delay"] == 2) & (stress["max_weight"] == 0.20)]
    t2_cagr = float(t2["cagr"].iloc[0]) if not t2.empty else 0.0
    t2_calmar = float(t2["calmar"].iloc[0]) if not t2.empty else 0.0
    ticker_contrib = attribution.get("ticker_contribution", pd.DataFrame())
    top_ticker = str(ticker_contrib["ticker"].iloc[0]) if not ticker_contrib.empty and "ticker" in ticker_contrib else ""
    top_ticker_share = float(ticker_contrib["abs_share"].iloc[0]) if not ticker_contrib.empty and "abs_share" in ticker_contrib else 1.0
    remove_top = leave_one_ticker.loc[leave_one_ticker["removed_ticker"] == top_ticker] if top_ticker and "removed_ticker" in leave_one_ticker else pd.DataFrame()
    remove_top_cagr = float(remove_top["cagr"].iloc[0]) if not remove_top.empty else 0.0
    remove_top_calmar = float(remove_top["calmar"].iloc[0]) if not remove_top.empty else 0.0
    yearly = attribution.get("yearly", pd.DataFrame())
    single_year_share = 1.0
    top_year = None
    if not yearly.empty and "year_return" in yearly:
        denom = float(yearly["year_return"].abs().sum())
        if denom > 0:
            idx = yearly["year_return"].abs().idxmax()
            single_year_share = float(abs(float(yearly.loc[idx, "year_return"])) / denom)
            top_year = int(yearly.loc[idx, "year"])
    remove_year = leave_one_year.loc[leave_one_year["removed_year"] == top_year] if top_year is not None and "removed_year" in leave_one_year else pd.DataFrame()
    remove_year_cagr = float(remove_year["cagr"].iloc[0]) if not remove_year.empty else 0.0
    remove_year_calmar = float(remove_year["calmar"].iloc[0]) if not remove_year.empty else 0.0
    stability_summary = stability.get("summary", pd.DataFrame())
    warning_rate = float(stability_summary["warning_decision_rate"].iloc[0]) if not stability_summary.empty and "warning_decision_rate" in stability_summary else 0.0
    warning_ok = warning_rate == 0.0 or model_name.endswith("_Ridge")
    gates = {
        "paper_cagr_ge_20": cagr >= 0.20,
        "paper_calmar_ge_1": calmar >= 1.0,
        "cost50_cagr_ge_20": cost50_cagr >= 0.20,
        "cost50_calmar_ge_1": cost50_calmar >= 1.0,
        "t2_cagr_ge_20": t2_cagr >= 0.20,
        "t2_calmar_ge_1": t2_calmar >= 1.0,
        "remove_top_ticker_ok": remove_top_cagr >= 0.20 and remove_top_calmar >= 1.0,
        "remove_top_year_ok": remove_year_cagr >= 0.20 and remove_year_calmar >= 1.0,
        "single_year_share_lte_50": single_year_share <= 0.50,
        "top_ticker_share_lte_30": top_ticker_share <= 0.30,
        "warning_ok": warning_ok,
    }
    if all(gates.values()):
        classification = "v9_ready_research_candidate"
    elif not warning_ok:
        classification = "model_unstable_need_fix"
    elif gates["paper_cagr_ge_20"] and gates["paper_calmar_ge_1"]:
        classification = "credible_but_execution_sensitive"
    else:
        classification = "likely_overfit"
    return {
        "model_branch": model_name,
        "classification": classification,
        "allow_enter_v9": bool(classification == "v9_ready_research_candidate"),
        "paper_cagr": cagr,
        "paper_calmar": calmar,
        "paper_max_drawdown": float(paper_metrics.get("max_drawdown", 0.0)),
        "cost50_t1_cagr": cost50_cagr,
        "cost50_t1_calmar": cost50_calmar,
        "t2_cagr": t2_cagr,
        "t2_calmar": t2_calmar,
        "top_ticker": top_ticker,
        "top_ticker_share": top_ticker_share,
        "remove_top_ticker_cagr": remove_top_cagr,
        "remove_top_ticker_calmar": remove_top_calmar,
        "top_year": top_year,
        "single_year_share": single_year_share,
        "remove_top_year_cagr": remove_year_cagr,
        "remove_top_year_calmar": remove_year_calmar,
        "warning_decision_rate": warning_rate,
        "gates": gates,
    }


def classify_cycle(summary: pd.DataFrame) -> dict[str, Any]:
    if summary.empty:
        return {"classification": "invalid_due_to_missing_results", "allow_enter_v9": False}
    ready = summary.loc[summary["classification"] == "v9_ready_research_candidate"].copy()
    if not ready.empty:
        best = ready.sort_values(["paper_calmar", "paper_cagr"], ascending=[False, False]).iloc[0].to_dict()
        return {
            "classification": "v9_ready_research_candidate",
            "allow_enter_v9": True,
            "best_model_branch": best.get("model_branch"),
            "reason": "At least one v8.1 model-switch branch passed all gates.",
        }
    best = summary.sort_values(["paper_calmar", "paper_cagr"], ascending=[False, False]).iloc[0].to_dict()
    return {
        "classification": str(best.get("classification", "credible_but_execution_sensitive")),
        "allow_enter_v9": False,
        "best_model_branch": best.get("model_branch"),
        "reason": "No v8.1 branch passed all v9 readiness gates.",
    }
