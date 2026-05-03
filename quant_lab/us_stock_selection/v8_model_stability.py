"""Model convergence and challenger checks for v8."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from quant_lab.us_stock_selection.feature_cache import load_feature_cache
from quant_lab.us_stock_selection.qlib_workflow_runner import load_close_from_provider
from quant_lab.us_stock_selection.utils import ensure_dir, save_dataframe
from quant_lab.us_stock_selection.v8_paper_trading import ModelSpec, fit_model, latest_available_feature_date, rebalance_dates, run_paper_trading_replay, trading_offset


ELASTICNET_CONFIGS = [
    ("elasticnet_original", {"alpha": 0.001, "l1_ratio": 0.25, "max_iter": 3000, "tol": 1e-4}),
    ("elasticnet_max_iter_10000", {"alpha": 0.001, "l1_ratio": 0.25, "max_iter": 10000, "tol": 1e-4}),
    ("elasticnet_max_iter_50000_tol_1e3", {"alpha": 0.001, "l1_ratio": 0.25, "max_iter": 50000, "tol": 1e-3}),
]


def run_elasticnet_convergence_check(
    out_dir: Path | str,
    cache_dir: Path | str,
    provider_uri: Path | str,
) -> pd.DataFrame:
    """Check three ElasticNet solver settings on representative monthly decisions."""
    out = ensure_dir(out_dir)
    frame, feature_cols = load_feature_cache(cache_dir, "Alpha360")
    frame["date"] = pd.to_datetime(frame["date"])
    close = load_close_from_provider(provider_uri, start="2020-01-01")
    all_months = rebalance_dates(close.index, start="2024-01-01", end="2026-04-17", timing="month_end")
    # Representative sample keeps this diagnostic fast while still spanning all years.
    if len(all_months) >= 3:
        sample_months = [all_months[0], all_months[len(all_months) // 2], all_months[-1]]
    else:
        sample_months = all_months
    rows: list[dict[str, Any]] = []
    for name, params in ELASTICNET_CONFIGS:
        spec = ModelSpec("ElasticNet", feature_set="Alpha360", label="label_5d", params=params)
        detail_rows = []
        for decision_date in sample_months:
            feature_date = latest_available_feature_date(frame, decision_date)
            train_end = trading_offset(close.index, decision_date, -6)
            if pd.isna(feature_date) or pd.isna(train_end):
                continue
            train = frame.loc[(frame["date"] <= train_end) & frame[spec.label].notna()].copy()
            pred = frame.loc[frame["date"] == feature_date].copy()
            if len(train) < 500 or pred.empty:
                continue
            try:
                _, fit_info = fit_model(train, pred, feature_cols, spec)
            except Exception as exc:
                fit_info = {"fit_status": "failed", "fit_warning_count": 1, "fit_warnings": str(exc), "train_rows": len(train), "predict_rows": len(pred)}
            detail_rows.append({"config": name, "decision_date": decision_date.date().isoformat(), **fit_info})
        detail = pd.DataFrame(detail_rows)
        save_dataframe(detail, out / f"{name}_convergence_detail.csv")
        warning_count = int(detail["fit_warning_count"].sum()) if not detail.empty else 0
        rows.append(
            {
                "config": name,
                "params": str(params),
                "decision_count": int(len(detail)),
                "warning_count": warning_count,
                "warning_decision_rate": float((detail["fit_warning_count"] > 0).mean()) if not detail.empty else 0.0,
                "sample_warning": " | ".join(detail.loc[detail["fit_warning_count"] > 0, "fit_warnings"].dropna().astype(str).head(3)),
            }
        )
    df = pd.DataFrame(rows)
    save_dataframe(df, out / "elasticnet_convergence_check.csv")
    return df


def run_challenger_models(
    out_dir: Path | str,
    cache_dir: Path | str,
    provider_uri: Path | str,
) -> pd.DataFrame:
    """Run same frozen Top5 monthly rule with Ridge, LGBM, and Alpha158 ElasticNet."""
    out = ensure_dir(out_dir)
    specs = [
        ModelSpec("Ridge", feature_set="Alpha360", label="label_5d", params={"alpha": 1.0}),
        ModelSpec("LGBModel", feature_set="Alpha360", label="label_5d", params={"n_estimators": 80}),
        ModelSpec("ElasticNet", feature_set="Alpha158", label="label_5d", params={"alpha": 0.001, "l1_ratio": 0.25, "max_iter": 10000, "tol": 1e-4}),
    ]
    rows: list[dict[str, Any]] = []
    for spec in specs:
        tag = f"{spec.feature_set}_{spec.name}"
        result = run_paper_trading_replay(out / tag, cache_dir=cache_dir, provider_uri=provider_uri, model_spec=spec, save_outputs=False)
        conv = result["convergence"]
        rows.append(
            {
                "run_id": tag,
                "feature_set": spec.feature_set,
                "model": spec.name,
                "label": spec.label,
                "decision_count": int(len(result["decisions"])),
                "warning_count": int(conv["fit_warning_count"].sum()) if not conv.empty else 0,
                **result["metrics"],
            }
        )
    df = pd.DataFrame(rows).sort_values(["calmar", "cagr"], ascending=[False, False])
    save_dataframe(df, out / "challenger_model_results.csv")
    return df
