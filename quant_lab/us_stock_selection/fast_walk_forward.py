"""Fast strict walk-forward using precomputed Qlib feature parquet caches."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from quant_lab.us_stock_selection.feature_cache import load_feature_cache
from quant_lab.us_stock_selection.portfolio_robustifier import build_robust_weights, concentration_metrics
from quant_lab.us_stock_selection.qlib_signal_backtest import compute_portfolio_metrics, portfolio_returns
from quant_lab.us_stock_selection.qlib_workflow_runner import load_close_from_provider
from quant_lab.us_stock_selection.utils import ensure_dir, nav_from_returns, save_dataframe, save_json, save_parquet


PORTFOLIO_TEMPLATES = [
    {"name": "top5_equal_monthly", "strategy": "topk", "top_k": 5, "rebalance": "M", "max_weight": 0.20},
    {"name": "top5_dropout_monthly", "strategy": "topk_dropout", "top_k": 5, "n_drop": 1, "rebalance": "M", "max_weight": 0.20},
    {"name": "top10_dropout_monthly", "strategy": "topk_dropout", "top_k": 10, "n_drop": 2, "rebalance": "M", "max_weight": 0.10},
]


def run_fast_walk_forward(
    out_dir: Path | str,
    cache_dir: Path | str,
    provider_uri: Path | str,
    feature_sets: list[str] | None = None,
    models: list[str] | None = None,
    labels: list[str] | None = None,
    wf_modes: list[str] | None = None,
    custom_windows: list[dict[str, str]] | None = None,
    resume: bool = True,
    max_seconds_per_fit: int = 300,
) -> dict[str, pd.DataFrame | dict[str, Any]]:
    """Run strict WF retraining directly from cached features."""
    out_path = ensure_dir(out_dir)
    daily_dir = ensure_dir(out_path / "daily_returns")
    holdings_dir = ensure_dir(out_path / "holdings")
    feature_sets = feature_sets or ["Alpha158", "Alpha360"]
    models = models or ["LightGBM", "Ridge", "ElasticNet"]
    labels = labels or ["label_5d", "label_20d"]
    wf_modes = wf_modes or ["anchored", "rolling_2y_6m", "rolling_3y_1y"]
    windows = custom_windows if custom_windows is not None else [w for w in build_wf_windows() if w["wf_family"] in set(wf_modes)]
    close = load_close_from_provider(provider_uri, start="2020-01-01")

    detail_path = out_path / "wf_detail.csv"
    existing = pd.read_csv(detail_path) if resume and detail_path.exists() else pd.DataFrame()
    completed_keys = set(existing["row_key"].tolist()) if "row_key" in existing.columns else set()
    detail_rows = existing.to_dict(orient="records") if not existing.empty else []
    daily_parts: list[pd.DataFrame] = []
    holding_parts: list[pd.DataFrame] = []
    failures: list[dict[str, Any]] = []

    for feature_set in feature_sets:
        try:
            frame, feature_cols = load_feature_cache(cache_dir, feature_set)
        except Exception as exc:
            failures.append({"feature_set": feature_set, "stage": "load_cache", "error": str(exc)})
            continue
        frame = frame.replace([np.inf, -np.inf], np.nan)
        for label in labels:
            if label not in frame.columns:
                failures.append({"feature_set": feature_set, "label": label, "stage": "label_missing", "error": f"{label} not in cache"})
                continue
            for model_name in models:
                for window in windows:
                    base_key = f"{feature_set}|{model_name}|{label}|{window['wf_name']}"
                    pred = pd.DataFrame()
                    fit_status = "completed"
                    fit_error = ""
                    elapsed = 0.0
                    try:
                        tic = time.perf_counter()
                        pred = fit_predict_window(frame, feature_cols, label, model_name, window)
                        elapsed = time.perf_counter() - tic
                        if elapsed > max_seconds_per_fit:
                            fit_status = "slow_completed"
                    except Exception as exc:
                        fit_status = "failed"
                        fit_error = str(exc)
                        failures.append({"row_key": base_key, "feature_set": feature_set, "model": model_name, "label": label, **window, "error": str(exc)})
                    for template in PORTFOLIO_TEMPLATES:
                        row_key = f"{base_key}|{template['name']}"
                        if row_key in completed_keys:
                            continue
                        if fit_status == "failed" or pred.empty:
                            detail_rows.append(
                                {
                                    "row_key": row_key,
                                    "strategy_id": strategy_id(feature_set, model_name, label, template["name"], window["wf_name"]),
                                    "feature_set": feature_set,
                                    "model": model_name,
                                    "label": label,
                                    "portfolio_template": template["name"],
                                    **window,
                                    "status": fit_status,
                                    "failure_reason": fit_error or "empty prediction",
                                    "fit_seconds": elapsed,
                                }
                            )
                            continue
                        score = pred.pivot_table(index="date", columns="instrument", values="score", aggfunc="last")
                        score.index = pd.to_datetime(score.index)
                        cols = close.columns.intersection(score.columns)
                        local_close = close.loc[(close.index >= pd.Timestamp(window["test_start"])) & (close.index <= pd.Timestamp(window["test_end"])), cols].ffill()
                        local_score = score.reindex(local_close.index).loc[:, cols].ffill(limit=5)
                        weights = build_robust_weights(local_close, local_score, template)
                        returns, turnover = portfolio_returns(local_close, weights, cost_bps=5.0, slippage_bps=5.0)
                        metrics = compute_portfolio_metrics(returns, turnover, weights)
                        concentration = concentration_metrics(local_close, weights, returns)
                        sid = strategy_id(feature_set, model_name, label, template["name"], window["wf_name"])
                        detail_rows.append(
                            {
                                "row_key": row_key,
                                "strategy_id": sid,
                                "feature_set": feature_set,
                                "model": model_name,
                                "label": label,
                                "portfolio_template": template["name"],
                                **window,
                                "status": fit_status,
                                "failure_reason": fit_error,
                                "fit_seconds": elapsed,
                                **metrics,
                                **concentration,
                                "passes_cagr20": bool(metrics["cagr"] >= 0.20),
                                "passes_calmar1": bool(metrics["calmar"] >= 1.0),
                            }
                        )
                        daily = pd.DataFrame(
                            {
                                "date": returns.index,
                                "strategy_id": sid,
                                "row_key": row_key,
                                "return": returns.values,
                                "nav": nav_from_returns(returns).values,
                            }
                        )
                        daily_parts.append(daily)
                        h = weights.stack().rename("weight").reset_index()
                        h.columns = ["date", "instrument", "weight"]
                        h.insert(0, "row_key", row_key)
                        h.insert(0, "strategy_id", sid)
                        holding_parts.append(h)
                    if len(detail_rows) % 25 == 0:
                        save_dataframe(pd.DataFrame(detail_rows), detail_path)
                        save_dataframe(pd.DataFrame(failures), out_path / "wf_failures.csv")

    detail = pd.DataFrame(detail_rows)
    if not detail.empty:
        detail = detail.drop_duplicates(subset=["row_key"], keep="last")
    summary = summarize_wf(detail)
    conservative_summary = summarize_wf_conservative(detail)
    assessment = assess_v7(summary, detail, conservative_summary)
    daily_df = pd.concat(daily_parts, ignore_index=True) if daily_parts else pd.DataFrame()
    holdings_df = pd.concat(holding_parts, ignore_index=True) if holding_parts else pd.DataFrame()
    save_dataframe(detail, detail_path)
    save_dataframe(summary, out_path / "wf_summary.csv")
    save_dataframe(conservative_summary, out_path / "conservative_wf_summary.csv")
    save_dataframe(pd.DataFrame(failures), out_path / "wf_failures.csv")
    save_json(assessment, out_path / "v7_assessment.json")
    save_parquet(daily_df, daily_dir / "wf_daily_returns.parquet")
    save_parquet(holdings_df, holdings_dir / "wf_holdings.parquet")
    return {"detail": detail, "summary": summary, "conservative_summary": conservative_summary, "assessment": assessment, "daily": daily_df, "holdings": holdings_df}


def build_wf_windows() -> list[dict[str, str]]:
    """Define v7 strict retrain walk-forward windows."""
    return [
        {"wf_family": "anchored", "wf_name": "anchored_2024_h1", "train_start": "2020-01-02", "train_end": "2023-12-31", "test_start": "2024-01-01", "test_end": "2024-06-30"},
        {"wf_family": "anchored", "wf_name": "anchored_2024_h2", "train_start": "2020-01-02", "train_end": "2024-06-30", "test_start": "2024-07-01", "test_end": "2024-12-31"},
        {"wf_family": "anchored", "wf_name": "anchored_2025_h1", "train_start": "2020-01-02", "train_end": "2024-12-31", "test_start": "2025-01-01", "test_end": "2025-06-30"},
        {"wf_family": "anchored", "wf_name": "anchored_2025_h2", "train_start": "2020-01-02", "train_end": "2025-06-30", "test_start": "2025-07-01", "test_end": "2025-12-31"},
        {"wf_family": "anchored", "wf_name": "anchored_2026_ytd", "train_start": "2020-01-02", "train_end": "2025-12-31", "test_start": "2026-01-01", "test_end": "2026-04-17"},
        {"wf_family": "rolling_2y_6m", "wf_name": "rolling2y_2024_h1", "train_start": "2022-01-01", "train_end": "2023-12-31", "test_start": "2024-01-01", "test_end": "2024-06-30"},
        {"wf_family": "rolling_2y_6m", "wf_name": "rolling2y_2024_h2", "train_start": "2022-07-01", "train_end": "2024-06-30", "test_start": "2024-07-01", "test_end": "2024-12-31"},
        {"wf_family": "rolling_2y_6m", "wf_name": "rolling2y_2025_h1", "train_start": "2023-01-01", "train_end": "2024-12-31", "test_start": "2025-01-01", "test_end": "2025-06-30"},
        {"wf_family": "rolling_2y_6m", "wf_name": "rolling2y_2025_h2", "train_start": "2023-07-01", "train_end": "2025-06-30", "test_start": "2025-07-01", "test_end": "2025-12-31"},
        {"wf_family": "rolling_2y_6m", "wf_name": "rolling2y_2026_ytd", "train_start": "2024-01-01", "train_end": "2025-12-31", "test_start": "2026-01-01", "test_end": "2026-04-17"},
        {"wf_family": "rolling_3y_1y", "wf_name": "rolling3y_2024", "train_start": "2021-01-01", "train_end": "2023-12-31", "test_start": "2024-01-01", "test_end": "2024-12-31"},
        {"wf_family": "rolling_3y_1y", "wf_name": "rolling3y_2025", "train_start": "2022-01-01", "train_end": "2024-12-31", "test_start": "2025-01-01", "test_end": "2025-12-31"},
        {"wf_family": "rolling_3y_1y", "wf_name": "rolling3y_2026_ytd", "train_start": "2023-01-01", "train_end": "2025-12-31", "test_start": "2026-01-01", "test_end": "2026-04-17"},
    ]


def fit_predict_window(frame: pd.DataFrame, feature_cols: list[str], label: str, model_name: str, window: dict[str, str]) -> pd.DataFrame:
    """Fit one model on a train slice and predict one test slice."""
    data = frame.loc[:, ["date", "instrument", label, *feature_cols]].copy()
    train = data.loc[(data["date"] >= pd.Timestamp(window["train_start"])) & (data["date"] <= pd.Timestamp(window["train_end"]))].dropna(subset=[label])
    test = data.loc[(data["date"] >= pd.Timestamp(window["test_start"])) & (data["date"] <= pd.Timestamp(window["test_end"]))].dropna(subset=[label])
    if len(train) < 500 or len(test) < 20:
        raise ValueError(f"insufficient rows train={len(train)} test={len(test)}")
    model = make_model(model_name)
    x_train = train[feature_cols]
    y_train = train[label].astype(float)
    x_test = test[feature_cols]
    model.fit(x_train, y_train)
    pred = test.loc[:, ["date", "instrument", label]].rename(columns={label: "label_value"}).copy()
    pred["score"] = model.predict(x_test)
    return pred


def make_model(model_name: str):
    """Create an sklearn-compatible model."""
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import ElasticNet, Ridge
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    if model_name == "LightGBM":
        try:
            from lightgbm import LGBMRegressor

            return make_pipeline(
                SimpleImputer(strategy="median"),
                LGBMRegressor(
                    n_estimators=60,
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
            model_name = "Ridge"
    if model_name == "ElasticNet":
        return make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), ElasticNet(alpha=0.001, l1_ratio=0.25, max_iter=3000, random_state=42))
    return make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), Ridge(alpha=1.0))


def summarize_wf(detail: pd.DataFrame) -> pd.DataFrame:
    """Aggregate WF windows by strategy and WF family."""
    if detail.empty or "status" not in detail.columns:
        return pd.DataFrame()
    ok = detail.loc[detail["status"].isin(["completed", "slow_completed"])].copy()
    if ok.empty:
        return pd.DataFrame()
    group_cols = ["feature_set", "model", "label", "portfolio_template", "wf_family"]
    summary = (
        ok.groupby(group_cols)
        .agg(
            window_count=("wf_name", "count"),
            mean_cagr=("cagr", "mean"),
            median_cagr=("cagr", "median"),
            mean_calmar=("calmar", "mean"),
            median_calmar=("calmar", "median"),
            min_calmar=("calmar", "min"),
            mean_max_drawdown=("max_drawdown", "mean"),
            pass_cagr20_rate=("passes_cagr20", "mean"),
            pass_calmar1_rate=("passes_calmar1", "mean"),
            avg_herfindahl=("avg_herfindahl", "mean"),
            top_holding_contribution=("top_holding_contribution", "mean"),
            avg_turnover=("annual_turnover", "mean"),
        )
        .reset_index()
    )
    summary["strategy_key"] = summary[["feature_set", "model", "label", "portfolio_template"]].agg("_".join, axis=1)
    summary = summary.sort_values(["pass_cagr20_rate", "pass_calmar1_rate", "mean_calmar", "mean_cagr"], ascending=[False, False, False, False])
    return summary


def summarize_wf_conservative(detail: pd.DataFrame) -> pd.DataFrame:
    """Summarize v7 with short-window annualization safeguards."""
    if detail.empty or "status" not in detail.columns:
        return pd.DataFrame()
    ok = detail.loc[detail["status"].isin(["completed", "slow_completed"])].copy()
    if ok.empty:
        return pd.DataFrame()
    ok["daily_count"] = pd.to_numeric(ok.get("daily_count", 0), errors="coerce").fillna(0).astype(int)
    ok["calmar_winsor"] = pd.to_numeric(ok["calmar"], errors="coerce").clip(-5, 5)
    ok["eligible_cagr"] = ok["daily_count"] >= 126
    ok["eligible_calmar"] = ok["daily_count"] >= 252
    group_cols = ["feature_set", "model", "label", "portfolio_template"]
    rows: list[dict[str, Any]] = []
    for keys, frame in ok.groupby(group_cols):
        eligible_cagr = frame.loc[frame["eligible_cagr"]]
        eligible_calmar = frame.loc[frame["eligible_calmar"]]
        worst_n = max(1, int(np.ceil(len(frame) * 0.25)))
        worst = frame.sort_values("total_return").head(worst_n)
        row = dict(zip(group_cols, keys))
        row.update(
            {
                "strategy_key": "_".join(str(x) for x in keys),
                "wf_family_count": int(frame["wf_family"].nunique()),
                "window_count": int(len(frame)),
                "short_window_lt_126_count": int((frame["daily_count"] < 126).sum()),
                "short_window_lt_252_count": int((frame["daily_count"] < 252).sum()),
                "eligible_cagr_windows": int(len(eligible_cagr)),
                "eligible_calmar_windows": int(len(eligible_calmar)),
                "mean_total_return_all": float(frame["total_return"].mean()),
                "median_total_return_all": float(frame["total_return"].median()),
                "conservative_mean_cagr_days_ge_126": float(eligible_cagr["cagr"].mean()) if not eligible_cagr.empty else np.nan,
                "conservative_median_cagr_days_ge_126": float(eligible_cagr["cagr"].median()) if not eligible_cagr.empty else np.nan,
                "cagr20_pass_rate_days_ge_126": float((eligible_cagr["cagr"] >= 0.20).mean()) if not eligible_cagr.empty else np.nan,
                "calmar_winsor_mean_all": float(frame["calmar_winsor"].mean()),
                "calmar_winsor_median_all": float(frame["calmar_winsor"].median()),
                "conservative_mean_calmar_days_ge_252": float(eligible_calmar["calmar_winsor"].mean()) if not eligible_calmar.empty else np.nan,
                "calmar1_pass_rate_days_ge_252": float((eligible_calmar["calmar"] >= 1.0).mean()) if not eligible_calmar.empty else np.nan,
                "worst_25pct_mean_total_return": float(worst["total_return"].mean()),
                "worst_25pct_mean_cagr": float(worst["cagr"].mean()),
                "worst_25pct_mean_calmar_winsor": float(worst["calmar_winsor"].mean()),
                "avg_herfindahl": float(frame["avg_herfindahl"].mean()) if "avg_herfindahl" in frame else 0.0,
                "top_holding_contribution": float(frame["top_holding_contribution"].mean()) if "top_holding_contribution" in frame else 0.0,
                "avg_turnover": float(frame["annual_turnover"].mean()) if "annual_turnover" in frame else 0.0,
            }
        )
        rows.append(row)
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values(
        ["cagr20_pass_rate_days_ge_126", "calmar_winsor_mean_all", "conservative_mean_cagr_days_ge_126"],
        ascending=[False, False, False],
    ).reset_index(drop=True)


def assess_v7(summary: pd.DataFrame, detail: pd.DataFrame, conservative_summary: pd.DataFrame | None = None) -> dict[str, Any]:
    """Classify v7 based on strict WF evidence."""
    if summary.empty:
        return {"classification": "fallback_only_not_verified", "reason": "no completed fast WF rows", "strict_walk_forward_passed": False}
    conservative_summary = conservative_summary if conservative_summary is not None else summarize_wf_conservative(detail)
    combined = (
        summary.groupby(["feature_set", "model", "label", "portfolio_template", "strategy_key"])
        .agg(
            wf_family_count=("wf_family", "nunique"),
            window_count=("window_count", "sum"),
            mean_cagr=("mean_cagr", "mean"),
            mean_calmar=("mean_calmar", "mean"),
            min_calmar=("min_calmar", "min"),
            pass_cagr20_rate=("pass_cagr20_rate", "mean"),
            pass_calmar1_rate=("pass_calmar1_rate", "mean"),
            avg_herfindahl=("avg_herfindahl", "mean"),
            top_holding_contribution=("top_holding_contribution", "mean"),
            avg_turnover=("avg_turnover", "mean"),
        )
        .reset_index()
        .sort_values(["pass_cagr20_rate", "pass_calmar1_rate", "mean_calmar", "mean_cagr"], ascending=[False, False, False, False])
    )
    if conservative_summary is not None and not conservative_summary.empty:
        top = conservative_summary.iloc[0].to_dict()
        raw_match = combined.loc[combined["strategy_key"] == top["strategy_key"]]
        if not raw_match.empty:
            top.update({f"raw_{k}": v for k, v in raw_match.iloc[0].to_dict().items() if k not in top})
        top["mean_cagr"] = top.get("conservative_mean_cagr_days_ge_126", top.get("raw_mean_cagr", np.nan))
        top["mean_calmar"] = top.get("calmar_winsor_mean_all", top.get("raw_mean_calmar", np.nan))
        top["pass_cagr20_rate"] = top.get("cagr20_pass_rate_days_ge_126", top.get("raw_pass_cagr20_rate", np.nan))
        top["pass_calmar1_rate"] = top.get("calmar1_pass_rate_days_ge_252", top.get("raw_pass_calmar1_rate", np.nan))
    else:
        top = combined.iloc[0].to_dict()
    strict_passed = bool(top["wf_family_count"] >= 2 and top["window_count"] >= 8)
    strong = bool(
        strict_passed
        and top.get("eligible_cagr_windows", 0) >= 5
        and top.get("eligible_calmar_windows", 0) >= 2
        and top.get("conservative_mean_cagr_days_ge_126", 0.0) >= 0.20
        and top.get("conservative_mean_calmar_days_ge_252", 0.0) >= 1.0
        and top.get("cagr20_pass_rate_days_ge_126", 0.0) >= 0.60
        and top.get("calmar1_pass_rate_days_ge_252", 0.0) >= 0.60
        and top["top_holding_contribution"] <= 0.30
        and top["avg_herfindahl"] <= 0.25
    )
    if strong:
        classification = "credible_research_candidate"
        reason = "strict fast WF completed with conservative CAGR/Calmar and concentration thresholds met"
    elif top.get("conservative_mean_cagr_days_ge_126", 0.0) >= 0.15 and top.get("calmar_winsor_mean_all", 0.0) >= 0.5:
        classification = "promising_but_needs_more_validation"
        reason = "fast WF remains promising, but short-window Calmar or eligible Calmar-window count is insufficient for credible status"
    else:
        classification = "likely_overfit"
        reason = "fast WF did not preserve enough conservative CAGR/Calmar"
    return {
        "classification": classification,
        "reason": reason,
        "strict_walk_forward_passed": strict_passed,
        "best": top,
        "combined_summary_rows": int(len(combined)),
    }


def strategy_id(feature_set: str, model_name: str, label: str, portfolio: str, wf_name: str) -> str:
    return f"v7_{feature_set}_{model_name}_{label}_{portfolio}_{wf_name}"
