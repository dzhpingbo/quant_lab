"""Build v9.1 Alpha360 feature cache and LGBModel score provenance."""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline

from quant_lab.us_stock_selection.feature_cache import build_feature_cache, load_feature_cache
from quant_lab.us_stock_selection.qlib_workflow_runner import load_close_from_provider
from quant_lab.us_stock_selection.utils import ensure_dir, save_dataframe, save_json, save_parquet
from quant_lab.us_stock_selection.v8_paper_trading import latest_available_feature_date, rebalance_dates, trading_offset
from quant_lab.us_stock_selection.v9_1_growth_data_onboarding import EVAL_END, EVAL_START, MIN_HISTORY_DAYS, V9_1_GROWTH_TICKERS


MODEL_PARAMS = {
    "n_estimators": 80,
    "learning_rate": 0.05,
    "num_leaves": 31,
    "subsample": 0.85,
    "colsample_bytree": 0.85,
    "random_state": 42,
    "n_jobs": 4,
    "verbosity": -1,
}
LABEL_DEFINITION = {
    "label_name": "label_5d",
    "qlib_expression": "Ref($close, -6) / Ref($close, -1) - 1",
    "alignment_note": "Use monthly train_end_label_safe = trading_offset(decision_date, -6), then predict on latest feature date <= decision_date.",
}


def build_v9_1_feature_cache(
    out_dir: Path | str,
    provider_uri: Path | str,
    logger: Any | None = None,
) -> dict[str, Any]:
    """Generate Qlib Alpha360 cache and v9.1 metadata files."""
    out = ensure_dir(out_dir)
    status = build_feature_cache(
        out,
        provider_uri=provider_uri,
        feature_sets=["Alpha360"],
        start_time="2020-01-02",
        end_time=EVAL_END.date().isoformat(),
        fit_start_time="2020-01-02",
        fit_end_time="2022-12-31",
        overwrite=True,
    )
    cache_file = out / "alpha360_cache.parquet"
    target_cache = out / "alpha360_feature_cache.parquet"
    if cache_file.exists():
        frame = pd.read_parquet(cache_file)
        save_parquet(frame, target_cache)
        feature_cols = [c for c in frame.columns if _is_feature_col(c)]
        quality = (
            frame.groupby("instrument", as_index=False)
            .agg(
                row_count=("date", "size"),
                date_min=("date", "min"),
                date_max=("date", "max"),
                label_5d_non_na=("label_5d", lambda s: int(pd.Series(s).notna().sum())),
            )
            .sort_values("instrument")
        )
        quality["missing_rate"] = [
            float(frame.loc[frame["instrument"].eq(inst), feature_cols].isna().mean().mean()) if feature_cols else 1.0
            for inst in quality["instrument"]
        ]
        quality["date_min"] = pd.to_datetime(quality["date_min"]).dt.date.astype(str)
        quality["date_max"] = pd.to_datetime(quality["date_max"]).dt.date.astype(str)
        save_dataframe(quality, out / "alpha360_feature_quality.csv")
        metadata = {
            "row_count": int(len(frame)),
            "feature_count": int(len(feature_cols)),
            "instrument_count": int(frame["instrument"].nunique()) if "instrument" in frame else 0,
            "date_min": pd.to_datetime(frame["date"]).min().date().isoformat() if not frame.empty else "",
            "date_max": pd.to_datetime(frame["date"]).max().date().isoformat() if not frame.empty else "",
            "missing_rate": float(frame[feature_cols].isna().mean().mean()) if feature_cols else 1.0,
            "generated_at": pd.Timestamp.now().isoformat(),
            "provider_uri": str(provider_uri),
            "feature_set": "Alpha360",
            "cache_path": str(target_cache),
            "status": "completed",
        }
    else:
        quality = pd.DataFrame()
        metadata = {
            "row_count": 0,
            "feature_count": 0,
            "instrument_count": 0,
            "date_min": "",
            "date_max": "",
            "missing_rate": 1.0,
            "generated_at": pd.Timestamp.now().isoformat(),
            "provider_uri": str(provider_uri),
            "feature_set": "Alpha360",
            "cache_path": "",
            "status": "failed",
            "error": status["status"].to_dict(orient="records") if "status" in status else "missing alpha360_cache.parquet",
        }
        save_dataframe(quality, out / "alpha360_feature_quality.csv")
    save_json(metadata, out / "alpha360_feature_cache_metadata.json")
    if logger is not None:
        logger.info(f"Alpha360 feature cache status={metadata.get('status')} rows={metadata.get('row_count')}")
    return {"status": metadata, "quality": quality, "cache_dir": str(out)}


def build_v9_1_score_provenance(
    out_dir: Path | str,
    cache_dir: Path | str,
    provider_uri: Path | str,
    universe_tickers: list[str],
    growth_tickers: list[str] | None = None,
    logger: Any | None = None,
) -> dict[str, Any]:
    """Fit fixed LGBModel monthly and export frozen score/rank provenance."""
    out = ensure_dir(out_dir)
    growth_set = {t.upper() for t in (growth_tickers or V9_1_GROWTH_TICKERS)}
    save_json(MODEL_PARAMS, out / "model_params.json")
    save_json(LABEL_DEFINITION, out / "label_definition.json")
    try:
        from lightgbm import LGBMRegressor
    except Exception as exc:
        empty = _write_empty_score_outputs(out, f"lightgbm_unavailable: {exc}")
        return empty

    frame, feature_cols = load_feature_cache(cache_dir, "Alpha360")
    frame = frame.replace([np.inf, -np.inf], np.nan).copy()
    frame["date"] = pd.to_datetime(frame["date"])
    frame["instrument"] = frame["instrument"].astype(str).str.upper()
    universe = sorted({t.upper() for t in universe_tickers})
    close = load_close_from_provider(provider_uri, tickers=universe, start="2020-01-01", end=EVAL_END.date().isoformat())
    if close.empty:
        return _write_empty_score_outputs(out, "empty_close_panel")

    first_eligible = first_eligible_dates(close, MIN_HISTORY_DAYS)
    decision_dates = rebalance_dates(close.index, start=EVAL_START.date().isoformat(), end=EVAL_END.date().isoformat(), timing="month_end")
    fit_rows: list[dict[str, Any]] = []
    score_parts: list[pd.DataFrame] = []
    audit_parts: list[pd.DataFrame] = []

    for decision_date in decision_dates:
        decision_date = pd.Timestamp(decision_date)
        train_end = trading_offset(close.index, decision_date, -6)
        feature_date = latest_available_feature_date(frame, decision_date)
        if pd.isna(train_end) or pd.isna(feature_date):
            fit_rows.append(fit_log_row(decision_date, train_end, feature_date, "skipped_missing_calendar_or_feature", 0, 0, len(feature_cols), 0, ""))
            continue
        eligible_now = eligible_tickers_on_date(first_eligible, close, decision_date, universe)
        local_frame = frame.loc[frame["instrument"].isin(universe)].copy()
        train = local_frame.loc[(local_frame["date"] <= train_end) & local_frame["label_5d"].notna()].copy()
        train = train.loc[train.apply(lambda r: pd.Timestamp(r["date"]) >= first_eligible.get(str(r["instrument"]), pd.Timestamp.max), axis=1)].copy()
        pred_frame = local_frame.loc[(local_frame["date"].eq(feature_date)) & (local_frame["instrument"].isin(eligible_now))].copy()
        if len(train) < 500 or pred_frame.empty or len(eligible_now) == 0:
            fit_rows.append(fit_log_row(decision_date, train_end, feature_date, "skipped_insufficient_train_or_pred", len(eligible_now), len(train), len(feature_cols), 0, ""))
            continue
        model = make_lgb_model(LGBMRegressor)
        warning_texts: list[str] = []
        fit_status = "completed"
        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                model.fit(train[feature_cols], train["label_5d"].astype(float))
                warning_texts = [str(w.message) for w in caught]
            scores = model.predict(pred_frame[feature_cols])
            if warning_texts:
                fit_status = "completed_with_warning"
        except Exception as exc:
            fit_rows.append(fit_log_row(decision_date, train_end, feature_date, "failed", len(eligible_now), len(train), len(feature_cols), 1, str(exc)))
            continue
        pred = pred_frame.loc[:, ["date", "instrument"]].copy()
        pred["rebalance_date"] = decision_date.date().isoformat()
        pred["ticker"] = pred["instrument"].astype(str).str.upper()
        pred["score"] = pd.Series(scores, index=pred.index).astype(float)
        pred["eligible"] = pred["ticker"].isin(eligible_now)
        pred = pred.drop(columns=["instrument"])
        ranked = pred.sort_values("score", ascending=False).reset_index(drop=True)
        ranked["rank"] = np.arange(1, len(ranked) + 1)
        ranked["selected_top5_candidate"] = ranked["rank"].le(5)
        ranked["is_growth_ticker"] = ranked["ticker"].isin(growth_set)
        ranked["is_incremental_growth_ticker"] = ranked["is_growth_ticker"]
        ranked["exclusion_reason_if_any"] = np.where(ranked["eligible"], "", "not_dynamic_eligible")
        score_parts.append(ranked.loc[:, ["rebalance_date", "date", "ticker", "score", "rank", "eligible", "selected_top5_candidate", "is_growth_ticker", "is_incremental_growth_ticker"]])
        audit_parts.append(ranked.loc[:, ["rebalance_date", "ticker", "score", "rank", "selected_top5_candidate", "eligible", "exclusion_reason_if_any", "is_growth_ticker", "is_incremental_growth_ticker"]])
        fit_rows.append(fit_log_row(decision_date, train_end, feature_date, fit_status, len(eligible_now), len(train), len(feature_cols), len(warning_texts), " | ".join(warning_texts[:5])))
        if logger is not None:
            logger.info(f"Score provenance {decision_date.date()} eligible={len(eligible_now)} train={len(train)}")

    fit_log = pd.DataFrame(fit_rows)
    scores_df = pd.concat(score_parts, ignore_index=True) if score_parts else pd.DataFrame(columns=["rebalance_date", "date", "ticker", "score", "rank", "eligible", "selected_top5_candidate", "is_growth_ticker", "is_incremental_growth_ticker"])
    audit = pd.concat(audit_parts, ignore_index=True) if audit_parts else pd.DataFrame(columns=["rebalance_date", "ticker", "score", "rank", "selected_top5_candidate", "eligible", "exclusion_reason_if_any"])
    save_dataframe(fit_log, out / "monthly_fit_log.csv")
    save_parquet(scores_df, out / "monthly_prediction_scores.parquet")
    save_dataframe(audit, out / "monthly_score_rank_audit.csv")
    score_months = int(scores_df["rebalance_date"].nunique()) if not scores_df.empty else 0
    growth_scored = sorted(scores_df.loc[scores_df["ticker"].isin(growth_set), "ticker"].dropna().astype(str).unique().tolist()) if not scores_df.empty else []
    growth_topk = sorted(scores_df.loc[scores_df["ticker"].isin(growth_set) & scores_df["selected_top5_candidate"].astype(bool), "ticker"].dropna().astype(str).unique().tolist()) if not scores_df.empty else []
    metadata = {
        "status": "completed" if score_months > 0 else "failed",
        "provider_uri": str(provider_uri),
        "feature_cache_dir": str(cache_dir),
        "feature_set": "Alpha360",
        "model": "LGBModel",
        "label": "label_5d",
        "random_seed": 42,
        "decision_month_count": int(len(decision_dates)),
        "score_month_count": score_months,
        "score_row_count": int(len(scores_df)),
        "growth_scored_count": int(len(growth_scored)),
        "growth_scored_tickers": growth_scored,
        "growth_top5_candidate_count": int(len(growth_topk)),
        "growth_top5_candidate_tickers": growth_topk,
        "fit_completed_count": int(fit_log["fit_status"].astype(str).str.startswith("completed").sum()) if not fit_log.empty else 0,
        "fit_failed_count": int(fit_log["fit_status"].astype(str).eq("failed").sum()) if not fit_log.empty else 0,
    }
    save_json(metadata, out / "score_source_metadata.json")
    return {"status": metadata, "fit_log": fit_log, "scores": scores_df, "audit": audit}


def make_lgb_model(lgb_cls: Any):
    return make_pipeline(SimpleImputer(strategy="median"), lgb_cls(**MODEL_PARAMS))


def _is_feature_col(column: Any) -> bool:
    text = str(column)
    return len(text) == 5 and text.startswith("f") and text[1:].isdigit()


def first_eligible_dates(close: pd.DataFrame, min_history_days: int) -> dict[str, pd.Timestamp]:
    out: dict[str, pd.Timestamp] = {}
    for ticker in close.columns:
        valid = close[ticker].dropna().index
        if len(valid) >= min_history_days:
            out[str(ticker).upper()] = pd.Timestamp(valid[min_history_days - 1])
    return out


def eligible_tickers_on_date(first_eligible: dict[str, pd.Timestamp], close: pd.DataFrame, decision_date: pd.Timestamp, universe: list[str]) -> list[str]:
    eligible: list[str] = []
    for ticker in universe:
        start = first_eligible.get(ticker)
        if start is None or start > decision_date:
            continue
        if ticker not in close.columns:
            continue
        latest = close[ticker].loc[:decision_date].dropna()
        if latest.empty:
            continue
        eligible.append(ticker)
    return eligible


def fit_log_row(
    decision_date: pd.Timestamp,
    train_end: Any,
    feature_date: Any,
    fit_status: str,
    eligible_ticker_count: int,
    sample_count: int,
    feature_count: int,
    warning_count: int,
    warnings_text: str,
) -> dict[str, Any]:
    return {
        "rebalance_date": pd.Timestamp(decision_date).date().isoformat(),
        "train_start": "2020-01-02",
        "train_end": "" if pd.isna(train_end) else pd.Timestamp(train_end).date().isoformat(),
        "prediction_date": "" if pd.isna(feature_date) else pd.Timestamp(feature_date).date().isoformat(),
        "eligible_ticker_count": int(eligible_ticker_count),
        "sample_count": int(sample_count),
        "feature_count": int(feature_count),
        "model_name": "LGBModel",
        "model_params": json.dumps(MODEL_PARAMS, ensure_ascii=False, sort_keys=True),
        "fit_status": fit_status,
        "warning_count": int(warning_count),
        "warnings": warnings_text,
        "random_seed": 42,
    }


def _write_empty_score_outputs(out: Path, error: str) -> dict[str, Any]:
    fit_log = pd.DataFrame(columns=["rebalance_date", "train_start", "train_end", "eligible_ticker_count", "sample_count", "feature_count", "model_name", "model_params", "fit_status", "warning_count", "random_seed"])
    scores = pd.DataFrame(columns=["rebalance_date", "date", "ticker", "score", "rank", "eligible", "selected_top5_candidate"])
    audit = pd.DataFrame(columns=["rebalance_date", "ticker", "score", "rank", "selected_top5_candidate", "eligible", "exclusion_reason_if_any"])
    save_dataframe(fit_log, out / "monthly_fit_log.csv")
    save_parquet(scores, out / "monthly_prediction_scores.parquet")
    save_dataframe(audit, out / "monthly_score_rank_audit.csv")
    metadata = {"status": "failed", "error": error, "feature_set": "Alpha360", "model": "LGBModel", "label": "label_5d"}
    save_json(metadata, out / "score_source_metadata.json")
    save_json(MODEL_PARAMS, out / "model_params.json")
    save_json(LABEL_DEFINITION, out / "label_definition.json")
    return {"status": metadata, "fit_log": fit_log, "scores": scores, "audit": audit}
