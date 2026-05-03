"""Run a bounded v8.2 score/rank audit replay.

This is audit instrumentation only. It replays the frozen v8 paper-trading
prediction path with the same feature cache, model parameters, tradability
filter, top-5 selection rule, weights, costs, and execution delay. It does not
enter v9, expand the universe, run 31b, optimize strategy rules, or run a
reranking replay.
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from quant_lab.us_stock_selection.feature_cache import load_feature_cache
from quant_lab.us_stock_selection.local_qlib_provider_builder import default_local_provider_uri
from quant_lab.us_stock_selection.qlib_workflow_runner import load_close_from_provider
from quant_lab.us_stock_selection.utils import write_excel
from quant_lab.us_stock_selection.v8_2_audit_trail import (
    FORWARD_AUDIT_COLUMNS,
    RISK_COLUMNS,
    build_score_rank_audit_for_decision,
    parse_selected_scores,
    validate_audit_quality,
)
from quant_lab.us_stock_selection.v8_paper_trading import (
    FROZEN_PORTFOLIO,
    fit_model,
    frozen_model_spec,
    latest_available_feature_date,
    load_field_from_provider,
    trading_offset,
    tradable_universe,
)


DEFAULT_RUN_DIR = PROJECT_ROOT / "outputs" / "us_stock_selection" / "run_20260426_095958"
OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "us_stock_selection"
DOCS_DIR = PROJECT_ROOT / "docs"
MEISTOCK_ROOT = Path("E:/dzhwork/obsydian/quant_lab/MeiStock")
SCORE_TOLERANCE = 1e-6
WEIGHT_TOLERANCE = 1e-12


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run v8.2 bounded full score/rank audit replay.")
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument("--provider-uri", type=Path, default=default_local_provider_uri())
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--timestamp", default=None)
    parser.add_argument("--sample-months", default="2024-10,2025-03,2025-10")
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--audit-forward-returns", default="true")
    parser.add_argument("--max-decision-dates", type=int, default=None)
    return parser.parse_args()


def bool_arg(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def setup_logger(out_dir: Path) -> logging.Logger:
    log_dir = out_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("v8_2_bounded_audit_replay")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    file_handler = logging.FileHandler(log_dir / "run.log", encoding="utf-8")
    stream_handler = logging.StreamHandler()
    file_handler.setFormatter(formatter)
    stream_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger


def read_csv(path: Path, required: bool = True) -> pd.DataFrame:
    if not path.exists():
        if required:
            raise FileNotFoundError(path)
        return pd.DataFrame()
    return pd.read_csv(path)


def write_json(data: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(to_jsonable(data), handle, indent=2, ensure_ascii=False)


def to_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_jsonable(v) for v in value]
    if isinstance(value, tuple):
        return [to_jsonable(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if pd.isna(value) else float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, float) and pd.isna(value):
        return None
    return value


def table_to_markdown(df: pd.DataFrame, max_rows: int = 20, columns: list[str] | None = None) -> str:
    if df is None or df.empty:
        return "_No rows._"
    view = df.copy()
    if columns:
        view = view.loc[:, [c for c in columns if c in view.columns]]
    return view.head(max_rows).to_markdown(index=False)


def ensure_inputs(run_dir: Path) -> dict[str, Path]:
    paths = {
        "run_config": run_dir / "run_config.yaml",
        "feature_cache": run_dir / "v7_feature_cache" / "alpha360_cache.parquet",
        "feature_map": run_dir / "v7_feature_cache" / "alpha360_feature_map.json",
        "ledger": run_dir / "v8_paper_trading" / "monthly_decision_ledger.csv",
        "holdings": run_dir / "v8_paper_trading" / "monthly_holdings.csv",
        "daily_nav": run_dir / "v8_paper_trading" / "daily_nav.csv",
        "metrics": run_dir / "v8_paper_trading" / "paper_trading_metrics.csv",
    }
    missing = [path for path in paths.values() if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing required v8 input(s): " + "; ".join(str(p) for p in missing))
    return paths


def normalize_baseline(ledger: pd.DataFrame, holdings: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    l = ledger.copy()
    h = holdings.copy()
    for col in ["decision_date", "feature_date", "prediction_date", "execution_date", "train_start", "train_end_label_safe"]:
        if col in l.columns:
            l[col] = pd.to_datetime(l[col], errors="coerce")
    for col in ["decision_date", "execution_date"]:
        if col in h.columns:
            h[col] = pd.to_datetime(h[col], errors="coerce")
    if "ticker" in h.columns:
        h["ticker"] = h["ticker"].astype(str).str.upper()
    if "weight" in h.columns:
        h["weight"] = pd.to_numeric(h["weight"], errors="coerce")
    if "score" in h.columns:
        h["score"] = pd.to_numeric(h["score"], errors="coerce")
    return l.sort_values("decision_date").reset_index(drop=True), h


def parse_sample_months(raw: str) -> list[str]:
    return [item.strip() for item in str(raw or "").split(",") if item.strip()]


def resolve_sample_decisions(ledger: pd.DataFrame, requested_months: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[pd.DataFrame] = []
    warnings: list[dict[str, Any]] = []
    available = ledger.dropna(subset=["decision_date"]).copy()
    available["month"] = available["decision_date"].dt.to_period("M").astype(str)
    for requested in requested_months:
        exact = available.loc[available["month"] == requested].head(1)
        if not exact.empty:
            rows.append(exact.drop(columns=["month"]))
            continue
        requested_date = pd.Timestamp(f"{requested}-15")
        nearest_idx = (available["decision_date"] - requested_date).abs().sort_values().index[0]
        nearest = available.loc[[nearest_idx]]
        replacement = nearest["decision_date"].iloc[0].to_period("M").strftime("%Y-%m")
        rows.append(nearest.drop(columns=["month"]))
        warnings.append(
            {
                "warning_type": "sample_month_resolution",
                "severity": "medium",
                "requested_month": requested,
                "resolved_month": replacement,
                "decision_date": date_str(nearest["decision_date"].iloc[0]),
                "message": f"requested sample month {requested} has no decision row; using nearest available {replacement}",
            }
        )
    selected = pd.concat(rows, ignore_index=True).drop_duplicates("decision_date").sort_values("decision_date")
    return selected.reset_index(drop=True), pd.DataFrame(warnings)


def limit_decisions(decisions: pd.DataFrame, max_decision_dates: int | None) -> pd.DataFrame:
    if max_decision_dates is None or max_decision_dates <= 0:
        return decisions
    return decisions.head(max_decision_dates).copy()


def selected_tickers_from_raw(raw: Any) -> list[str]:
    return [item.strip().upper() for item in str(raw or "").split(",") if item.strip()]


def format_selected_scores(selected: pd.DataFrame) -> str:
    return ";".join(f"{row.instrument}:{float(row.score):.8f}" for row in selected.itertuples(index=False))


def load_replay_context(run_dir: Path, provider_uri: Path, end: pd.Timestamp, logger: logging.Logger) -> dict[str, Any]:
    spec = frozen_model_spec()
    cache_dir = run_dir / "v7_feature_cache"
    logger.info("Loading frozen v8 feature cache from %s", cache_dir)
    frame, feature_cols = load_feature_cache(cache_dir, spec.feature_set)
    frame = frame.replace([np.inf, -np.inf], np.nan).copy()
    frame["date"] = pd.to_datetime(frame["date"])
    logger.info("Loading close/volume from local qlib provider %s", provider_uri)
    close = load_close_from_provider(provider_uri, start="2020-01-01")
    volume = load_field_from_provider(provider_uri, "$volume", start="2020-01-01", tickers=list(close.columns))
    close = close.loc[(close.index >= "2020-01-01") & (close.index <= end)].ffill()
    volume = volume.reindex(close.index).loc[:, close.columns].ffill()
    return {
        "spec": spec,
        "frame": frame,
        "feature_cols": feature_cols,
        "close": close,
        "volume": volume,
        "dollar_volume": close * volume,
    }


def replay_decisions(
    *,
    run_id: str,
    audit_replay_id: str,
    decisions: pd.DataFrame,
    baseline_ledger: pd.DataFrame,
    baseline_holdings: pd.DataFrame,
    context: dict[str, Any],
    audit_forward_returns: bool,
    logger: logging.Logger,
) -> dict[str, pd.DataFrame]:
    frame = context["frame"]
    feature_cols = context["feature_cols"]
    close = context["close"]
    dollar_volume = context["dollar_volume"]
    spec = context["spec"]
    audit_parts: list[pd.DataFrame] = []
    decision_rows: list[dict[str, Any]] = []
    holding_rows: list[dict[str, Any]] = []
    convergence_rows: list[dict[str, Any]] = []

    for _, baseline_row in decisions.sort_values("decision_date").iterrows():
        decision_date = pd.Timestamp(baseline_row["decision_date"])
        feature_date = latest_available_feature_date(frame, decision_date)
        train_end = trading_offset(close.index, decision_date, -6)
        if pd.isna(feature_date) or pd.isna(train_end):
            logger.warning("Skipping %s because feature_date or train_end is missing", date_str(decision_date))
            continue
        train = frame.loc[(frame["date"] <= train_end) & frame[spec.label].notna()].copy()
        pred_frame = frame.loc[frame["date"] == feature_date].copy()
        if len(train) < 500 or pred_frame.empty:
            logger.warning(
                "Skipping %s because train rows=%s pred rows=%s",
                date_str(decision_date),
                len(train),
                len(pred_frame),
            )
            continue
        model, fit_info = fit_model(train, pred_frame, feature_cols, spec)
        pred = pred_frame.loc[:, ["date", "instrument"]].copy()
        pred["score"] = model.predict(pred_frame[feature_cols])
        pred["instrument"] = pred["instrument"].astype(str).str.upper()
        tradable = tradable_universe(close, dollar_volume, pred["instrument"].tolist(), decision_date, 20_000_000.0)
        ranked = pred.loc[pred["instrument"].isin(tradable)].sort_values("score", ascending=False)
        selected = ranked.head(5).copy()
        execution_date = trading_offset(close.index, decision_date, 1)
        if selected.empty or pd.isna(execution_date) or execution_date > close.index.max():
            logger.warning("Skipping %s because selection or execution_date is unavailable", date_str(decision_date))
            continue
        current = pd.Series(0.0, index=close.columns)
        current.loc[selected["instrument"].tolist()] = 0.20
        next_execution_date = next_baseline_execution_date(baseline_ledger, decision_date)
        history = baseline_holdings.loc[baseline_holdings["decision_date"] < decision_date].copy()
        audit = build_score_rank_audit_for_decision(
            run_id=run_id,
            decision_date=decision_date,
            feature_date=pd.Timestamp(feature_date),
            execution_date=pd.Timestamp(execution_date),
            pred=pred,
            tradable=tradable,
            selected=selected,
            current_weights=current,
            close=close,
            dollar_volume=dollar_volume,
            selection_history=history,
            selected_period_end_date=next_execution_date,
            model_name=spec.name,
            feature_set=spec.feature_set,
            label=spec.label,
            selection_rule=FROZEN_PORTFOLIO,
            score_source="bounded_audit_replay_runtime_prediction",
            audit_forward_returns=audit_forward_returns,
        )
        audit.insert(1, "audit_replay_id", audit_replay_id)
        audit_parts.append(audit)
        selected_scores = dict(zip(selected["instrument"], selected["score"]))
        decision_rows.append(
            {
                "decision_date": date_str(decision_date),
                "feature_date": date_str(feature_date),
                "prediction_date": date_str(feature_date),
                "train_start": date_str(train["date"].min()),
                "train_end_label_safe": date_str(train_end),
                "execution_date": date_str(execution_date),
                "execution_delay_days": 1,
                "feature_set": spec.feature_set,
                "model": spec.name,
                "label": spec.label,
                "selected_tickers": ",".join(selected["instrument"].tolist()),
                "selected_scores": format_selected_scores(selected),
                "tradable_count": int(len(tradable)),
                "cost_bps": 5.0,
                "slippage_bps": 5.0,
                **fit_info,
            }
        )
        for ticker in selected["instrument"].tolist():
            holding_rows.append(
                {
                    "decision_date": date_str(decision_date),
                    "execution_date": date_str(execution_date),
                    "ticker": ticker,
                    "weight": float(current[ticker]),
                    "score": float(selected_scores[ticker]),
                    "avg_dollar_volume_20d": float(dollar_volume[ticker].loc[:decision_date].tail(20).mean())
                    if ticker in dollar_volume
                    else np.nan,
                }
            )
        convergence_rows.append({"decision_date": date_str(decision_date), **fit_info})
        logger.info(
            "replayed decision_date=%s candidates=%s tradable=%s selected=%s",
            date_str(decision_date),
            len(pred),
            len(tradable),
            ",".join(selected["instrument"].tolist()),
        )
    return {
        "audit": pd.concat(audit_parts, ignore_index=True) if audit_parts else pd.DataFrame(),
        "decisions": pd.DataFrame(decision_rows),
        "holdings": pd.DataFrame(holding_rows),
        "convergence": pd.DataFrame(convergence_rows),
    }


def next_baseline_execution_date(ledger: pd.DataFrame, decision_date: pd.Timestamp) -> pd.Timestamp | None:
    future = ledger.loc[ledger["decision_date"] > decision_date].sort_values("decision_date")
    if future.empty:
        return None
    return pd.Timestamp(future["execution_date"].iloc[0])


def selection_diff(replay_decisions_df: pd.DataFrame, baseline_ledger: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if replay_decisions_df.empty:
        return pd.DataFrame()
    replay = replay_decisions_df.copy()
    replay["decision_date"] = pd.to_datetime(replay["decision_date"], errors="coerce")
    for _, row in replay.sort_values("decision_date").iterrows():
        decision_date = pd.Timestamp(row["decision_date"])
        base = baseline_ledger.loc[baseline_ledger["decision_date"] == decision_date].head(1)
        if base.empty:
            rows.append(
                {
                    "decision_date": date_str(decision_date),
                    "diff_type": "missing_baseline_decision",
                    "is_match": False,
                    "severity": "high",
                }
            )
            continue
        base_row = base.iloc[0]
        replay_tickers = selected_tickers_from_raw(row.get("selected_tickers"))
        baseline_tickers = selected_tickers_from_raw(base_row.get("selected_tickers"))
        replay_scores = parse_selected_scores(row.get("selected_scores"))
        baseline_scores = parse_selected_scores(base_row.get("selected_scores"))
        score_diffs = [
            abs(float(replay_scores.get(t, np.nan)) - float(baseline_scores.get(t, np.nan)))
            for t in baseline_tickers
            if t in replay_scores and t in baseline_scores
        ]
        max_abs_score_diff = max(score_diffs) if score_diffs else np.nan
        rows.append(
            {
                "decision_date": date_str(decision_date),
                "baseline_selected_tickers": ",".join(baseline_tickers),
                "replay_selected_tickers": ",".join(replay_tickers),
                "selected_tickers_match": replay_tickers == baseline_tickers,
                "max_abs_score_diff": max_abs_score_diff,
                "selected_scores_match": bool(pd.notna(max_abs_score_diff) and max_abs_score_diff <= SCORE_TOLERANCE),
                "baseline_tradable_count": int(base_row.get("tradable_count", 0)),
                "replay_tradable_count": int(row.get("tradable_count", 0)),
                "tradable_count_match": int(base_row.get("tradable_count", 0)) == int(row.get("tradable_count", 0)),
                "is_match": bool(
                    replay_tickers == baseline_tickers
                    and pd.notna(max_abs_score_diff)
                    and max_abs_score_diff <= SCORE_TOLERANCE
                    and int(base_row.get("tradable_count", 0)) == int(row.get("tradable_count", 0))
                ),
                "severity": "none"
                if replay_tickers == baseline_tickers
                and pd.notna(max_abs_score_diff)
                and max_abs_score_diff <= SCORE_TOLERANCE
                and int(base_row.get("tradable_count", 0)) == int(row.get("tradable_count", 0))
                else "high",
            }
        )
    return pd.DataFrame(rows)


def holdings_diff(replay_holdings: pd.DataFrame, baseline_holdings: pd.DataFrame, decisions: pd.DataFrame) -> pd.DataFrame:
    if replay_holdings.empty:
        return pd.DataFrame()
    r = replay_holdings.copy()
    b = baseline_holdings.copy()
    r["decision_date"] = pd.to_datetime(r["decision_date"], errors="coerce")
    r["ticker"] = r["ticker"].astype(str).str.upper()
    b["decision_date"] = pd.to_datetime(b["decision_date"], errors="coerce")
    b["ticker"] = b["ticker"].astype(str).str.upper()
    wanted = set(pd.to_datetime(decisions["decision_date"]).dt.date)
    b = b.loc[b["decision_date"].dt.date.isin(wanted)].copy()
    merged = b.merge(r, on=["decision_date", "ticker"], how="outer", suffixes=("_baseline", "_replay"), indicator=True)
    merged["weight_diff"] = pd.to_numeric(merged.get("weight_replay"), errors="coerce") - pd.to_numeric(
        merged.get("weight_baseline"), errors="coerce"
    )
    merged["score_diff"] = pd.to_numeric(merged.get("score_replay"), errors="coerce") - pd.to_numeric(
        merged.get("score_baseline"), errors="coerce"
    )
    merged["is_match"] = (
        (merged["_merge"] == "both")
        & (merged["weight_diff"].abs() <= WEIGHT_TOLERANCE)
        & (merged["score_diff"].abs() <= SCORE_TOLERANCE)
    )
    merged["severity"] = np.where(merged["is_match"], "none", "high")
    return merged.sort_values(["decision_date", "ticker"]).reset_index(drop=True)


def quality_with_replay_checks(
    audit: pd.DataFrame,
    baseline_holdings: pd.DataFrame,
    baseline_ledger: pd.DataFrame,
    replay_decisions_df: pd.DataFrame,
    selection_diff_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    quality, warnings = validate_audit_quality(audit, baseline_holdings, baseline_ledger)
    if quality.empty:
        return quality, warnings
    selection_ok = selection_diff_df.set_index("decision_date")["is_match"].to_dict() if not selection_diff_df.empty else {}
    tradable_match = (
        selection_diff_df.set_index("decision_date")["tradable_count_match"].to_dict() if not selection_diff_df.empty else {}
    )
    quality["baseline_selection_reproduced"] = quality["decision_date"].map(selection_ok).fillna(False).astype(bool)
    quality["tradable_count_matches_baseline"] = quality["decision_date"].map(tradable_match).fillna(False).astype(bool)
    quality["candidate_count_gt_selected_count"] = quality["candidate_count"] > quality["selected_count"]
    quality["audit_forward_fields_used_in_selection"] = False
    quality["quality_pass"] = (
        quality["quality_pass"].astype(bool)
        & quality["baseline_selection_reproduced"]
        & quality["tradable_count_matches_baseline"]
        & quality["candidate_count_gt_selected_count"]
        & (~quality["audit_forward_fields_used_in_selection"])
    )
    for row in quality.loc[~quality["quality_pass"]].to_dict(orient="records"):
        warnings = pd.concat(
            [
                warnings,
                pd.DataFrame(
                    [
                        {
                            "decision_date": row.get("decision_date"),
                            "warning_type": "bounded_replay_quality_fail",
                            "severity": "high",
                            "message": "bounded audit replay quality checks failed",
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )
    return quality, warnings


def readiness_after_bounded_replay(
    audit: pd.DataFrame,
    quality: pd.DataFrame,
    selection_diff_df: pd.DataFrame,
) -> dict[str, Any]:
    if audit.empty or quality.empty:
        blockers = ["audit trail or quality frame is empty"]
        return {
            "has_full_candidate_universe": False,
            "has_unselected_tickers": False,
            "has_raw_score": False,
            "has_raw_rank": False,
            "has_adjusted_score": False,
            "has_adjusted_rank": False,
            "has_selected_flag": False,
            "selected_flag_validated": False,
            "has_ex_ante_risk_features": False,
            "has_forward_audit_fields": False,
            "candidate_count_gt_selected_count_all_dates": False,
            "baseline_selection_reproduced": False,
            "can_run_gate_aware_reranking_replay": False,
            "blockers": blockers,
            "next_required_patch": "produce non-empty bounded audit replay outputs",
        }
    has_full_candidate_universe = bool((quality["candidate_count"] > quality["selected_count"]).all())
    has_unselected_tickers = bool((~audit["selected_flag"].astype(bool)).any())
    has_raw_score = bool(audit["raw_score"].notna().mean() > 0.95)
    has_raw_rank = bool(audit["raw_rank"].notna().mean() > 0.95)
    tradable = audit.loc[audit["tradable_flag"].astype(bool)].copy()
    has_adjusted_score = bool(not tradable.empty and tradable["adjusted_score"].notna().mean() > 0.95)
    has_adjusted_rank = bool(not tradable.empty and tradable["adjusted_rank"].notna().mean() > 0.95)
    selected_flag_validated = bool(
        quality["selected_flag_consistent_with_holdings"].all() and quality["selected_count_matches_holdings"].all()
    )
    risk_cols = [col for col in RISK_COLUMNS if col in audit.columns and not col.startswith("previous_")]
    risk_cols = [col for col in risk_cols if col not in {"high_beta_flag", "high_beta_group"}]
    has_ex_ante_risk_features = bool(risk_cols and audit[risk_cols].notna().mean().mean() > 0.50)
    has_forward_audit_fields = bool(
        all(col in audit.columns for col in FORWARD_AUDIT_COLUMNS) and audit[FORWARD_AUDIT_COLUMNS].notna().any().any()
    )
    candidate_count_gt_selected_count_all_dates = bool(quality["candidate_count_gt_selected_count"].all())
    baseline_selection_reproduced = bool(not selection_diff_df.empty and selection_diff_df["is_match"].all())
    blockers: list[str] = []
    checks = {
        "has_full_candidate_universe": has_full_candidate_universe,
        "has_unselected_tickers": has_unselected_tickers,
        "has_raw_score": has_raw_score,
        "has_raw_rank": has_raw_rank,
        "has_selected_flag": "selected_flag" in audit.columns,
        "selected_flag_validated": selected_flag_validated,
        "has_ex_ante_risk_features": has_ex_ante_risk_features,
        "candidate_count_gt_selected_count_all_dates": candidate_count_gt_selected_count_all_dates,
        "baseline_selection_reproduced": baseline_selection_reproduced,
    }
    for key, passed in checks.items():
        if not passed:
            blockers.append(key)
    can_run = bool(all(checks.values()))
    return {
        "has_full_candidate_universe": has_full_candidate_universe,
        "has_unselected_tickers": has_unselected_tickers,
        "has_raw_score": has_raw_score,
        "has_raw_rank": has_raw_rank,
        "has_adjusted_score": has_adjusted_score,
        "has_adjusted_rank": has_adjusted_rank,
        "has_selected_flag": "selected_flag" in audit.columns,
        "selected_flag_validated": selected_flag_validated,
        "has_ex_ante_risk_features": has_ex_ante_risk_features,
        "has_forward_audit_fields": has_forward_audit_fields,
        "candidate_count_gt_selected_count_all_dates": candidate_count_gt_selected_count_all_dates,
        "baseline_selection_reproduced": baseline_selection_reproduced,
        "can_run_gate_aware_reranking_replay": can_run,
        "blockers": blockers,
        "next_required_patch": "pause for user/ChatGPT approval before any bounded gate-aware reranking replay"
        if can_run
        else "fix bounded audit replay quality blockers before reranking",
    }


def summarize_phase(
    *,
    phase: str,
    audit: pd.DataFrame,
    quality: pd.DataFrame,
    selection_diff_df: pd.DataFrame,
    holdings_diff_df: pd.DataFrame,
    warnings: pd.DataFrame,
    requested_sample_months: list[str] | None = None,
    resolved_decisions: pd.DataFrame | None = None,
) -> dict[str, Any]:
    return {
        "phase": phase,
        "requested_sample_months": requested_sample_months or [],
        "resolved_decision_dates": []
        if resolved_decisions is None or resolved_decisions.empty
        else [date_str(x) for x in resolved_decisions["decision_date"].tolist()],
        "audit_row_count": int(len(audit)),
        "decision_count": int(audit["decision_date"].nunique()) if not audit.empty else 0,
        "candidate_count_min": int(quality["candidate_count"].min()) if not quality.empty else 0,
        "candidate_count_max": int(quality["candidate_count"].max()) if not quality.empty else 0,
        "selected_count_min": int(quality["selected_count"].min()) if not quality.empty else 0,
        "selected_count_max": int(quality["selected_count"].max()) if not quality.empty else 0,
        "quality_pass_all": bool(not quality.empty and quality["quality_pass"].all()),
        "selection_diff_count": int((~selection_diff_df["is_match"]).sum()) if not selection_diff_df.empty else 0,
        "holdings_diff_count": int((~holdings_diff_df["is_match"]).sum()) if not holdings_diff_df.empty else 0,
        "warning_count": int(len(warnings)),
        "audit_forward_fields_used_in_selection": False,
    }


def run_phase(
    *,
    phase: str,
    run_id: str,
    audit_replay_id: str,
    decisions: pd.DataFrame,
    baseline_ledger: pd.DataFrame,
    baseline_holdings: pd.DataFrame,
    context: dict[str, Any],
    audit_forward_returns: bool,
    out_dir: Path,
    logger: logging.Logger,
) -> dict[str, Any]:
    replay = replay_decisions(
        run_id=run_id,
        audit_replay_id=audit_replay_id,
        decisions=decisions,
        baseline_ledger=baseline_ledger,
        baseline_holdings=baseline_holdings,
        context=context,
        audit_forward_returns=audit_forward_returns,
        logger=logger,
    )
    audit = replay["audit"]
    replay_decisions_df = replay["decisions"]
    replay_holdings_df = replay["holdings"]
    sel_diff = selection_diff(replay_decisions_df, baseline_ledger)
    hold_diff = holdings_diff(replay_holdings_df, baseline_holdings, decisions)
    quality, warnings = quality_with_replay_checks(audit, baseline_holdings, baseline_ledger, replay_decisions_df, sel_diff)
    prefix = "sample" if phase == "sample" else "full"
    if phase == "sample":
        audit.to_csv(out_dir / "v8_2_sample_full_score_rank_audit_trail.csv", index=False, encoding="utf-8-sig")
        quality.to_csv(out_dir / "v8_2_sample_audit_quality.csv", index=False, encoding="utf-8-sig")
        sel_diff.to_csv(out_dir / "v8_2_sample_replay_vs_baseline_selection_diff.csv", index=False, encoding="utf-8-sig")
        hold_diff.to_csv(out_dir / "v8_2_sample_replay_vs_baseline_holdings_diff.csv", index=False, encoding="utf-8-sig")
    else:
        audit.to_csv(out_dir / "v8_2_full_score_rank_audit_trail.csv", index=False, encoding="utf-8-sig")
        quality.to_csv(out_dir / "v8_2_full_audit_quality.csv", index=False, encoding="utf-8-sig")
        sel_diff.to_csv(out_dir / "v8_2_replay_vs_baseline_selection_diff.csv", index=False, encoding="utf-8-sig")
        hold_diff.to_csv(out_dir / "v8_2_replay_vs_baseline_holdings_diff.csv", index=False, encoding="utf-8-sig")
    replay_decisions_df.to_csv(out_dir / f"v8_2_{prefix}_replay_decision_ledger.csv", index=False, encoding="utf-8-sig")
    replay_holdings_df.to_csv(out_dir / f"v8_2_{prefix}_replay_holdings.csv", index=False, encoding="utf-8-sig")
    replay["convergence"].to_csv(out_dir / f"v8_2_{prefix}_fit_convergence_log.csv", index=False, encoding="utf-8-sig")
    if not warnings.empty:
        warnings.to_csv(out_dir / f"v8_2_{prefix}_audit_warnings.csv", index=False, encoding="utf-8-sig")
    for row in quality.to_dict(orient="records"):
        logger.info(
            "%s quality decision_date=%s candidate_count=%s selected_count=%s raw_score_rate=%.4f raw_rank_rate=%.4f baseline_match=%s quality_pass=%s",
            phase,
            row.get("decision_date"),
            row.get("candidate_count"),
            row.get("selected_count"),
            float(row.get("raw_score_non_null_rate", 0.0)),
            float(row.get("raw_rank_non_null_rate", 0.0)),
            row.get("baseline_selection_reproduced"),
            row.get("quality_pass"),
        )
    return {
        "audit": audit,
        "quality": quality,
        "selection_diff": sel_diff,
        "holdings_diff": hold_diff,
        "warnings": warnings,
        "replay_decisions": replay_decisions_df,
        "replay_holdings": replay_holdings_df,
    }


def write_reports(
    *,
    timestamp: str,
    out_dir: Path,
    zip_path: Path,
    sample_summary: dict[str, Any],
    full_summary: dict[str, Any] | None,
    sample_quality: pd.DataFrame,
    full_quality: pd.DataFrame,
    sample_diff: pd.DataFrame,
    full_diff: pd.DataFrame,
    readiness: dict[str, Any],
    sample_passed: bool,
    full_executed: bool,
) -> tuple[Path, Path]:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = DOCS_DIR / f"US_STOCK_SELECTION_V8_2_BOUNDED_AUDIT_REPLAY_{timestamp}.md"
    exec_path = DOCS_DIR / f"US_STOCK_SELECTION_V8_2_BOUNDED_AUDIT_REPLAY_EXEC_SUMMARY_{timestamp}.md"
    full_result_text = (
        table_to_markdown(full_quality, max_rows=40)
        if full_executed
        else "Full bounded audit replay was not executed because sample validation did not pass or --full was not requested."
    )
    full_diff_text = table_to_markdown(full_diff, max_rows=40) if full_executed else "_Not executed._"
    report = f"""# US Stock Selection v8.2 Bounded Audit Replay

## 1. Background And Purpose

The prior v8.2 instrumentation proved that the original v8 baseline can only reconstruct selected-only scores from persisted artifacts. This run performs a bounded audit replay of the frozen v8 paper-trading prediction path to persist full decision_date x candidate score/rank rows.

## 2. Why The Old Run Cannot Recover Full Score/Rank

The old run saved selected_tickers, selected_scores, tradable_count, holdings, trades, and nav. It did not save the runtime pred/tradable/ranked snapshots or fitted monthly model artifacts, so unselected candidate scores cannot be recovered honestly from the old files alone.

## 3. What Bounded Audit Replay Means

Bounded audit replay means rerunning the original v8 scoring path with the same Alpha360 cache, ElasticNet parameters, liquidity filter, top5_equal_monthly selection, 20 percent weights, 1-day execution delay, and 5bps cost/slippage assumptions only to capture audit rows.

## 4. Strategy Logic Changed

No.

## 5. New Model Strategy Trained

No. The frozen v8 model class and parameters were refit only as part of reproducing the original audit replay path. No new model family, target, optimization, or strategy rule was introduced.

## 6. Sample Months Validation

Sample passed: `{sample_passed}`

{table_to_markdown(sample_quality, max_rows=20)}

## 7. Sample Baseline Selection Diff

{table_to_markdown(sample_diff, max_rows=20)}

## 8. Full Bounded Audit Replay Result

Full executed: `{full_executed}`

{full_result_text}

## 9. Full Baseline Selection Diff

{full_diff_text}

## 10. Full Candidate Audit Trail Generated

`{bool(full_executed and readiness.get('has_full_candidate_universe'))}`

## 11. Reranking Readiness

```json
{json.dumps(to_jsonable(readiness), indent=2, ensure_ascii=False)}
```

## 12. Remaining Gaps

Even if readiness is true, this run is not reranking replay and does not authorize v9. The next step requires user/ChatGPT approval before any gate-aware reranking replay.

## 13. Outputs

- Output directory: `{out_dir}`
- Zip: `{zip_path}`
"""
    exec_summary = f"""# US Stock Selection v8.2 Bounded Audit Replay Exec Summary

- Sample completed: `True`
- Sample passed: `{sample_passed}`
- Full completed: `{full_executed}`
- Full candidate score/rank generated: `{bool(full_executed and readiness.get('has_full_candidate_universe'))}`
- Baseline selection reproduced: `{readiness.get('baseline_selection_reproduced')}`
- Can run gate-aware reranking replay: `{readiness.get('can_run_gate_aware_reranking_replay')}`
- Next required patch: `{readiness.get('next_required_patch')}`

## Sample Summary

```json
{json.dumps(to_jsonable(sample_summary), indent=2, ensure_ascii=False)}
```

## Full Summary

```json
{json.dumps(to_jsonable(full_summary or {}), indent=2, ensure_ascii=False)}
```
"""
    report_path.write_text(report, encoding="utf-8")
    exec_path.write_text(exec_summary, encoding="utf-8")
    reports_dir = out_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(report_path, reports_dir / report_path.name)
    shutil.copy2(exec_path, reports_dir / exec_path.name)
    return report_path, exec_path


def write_workbook(
    out_dir: Path,
    timestamp: str,
    sample: dict[str, pd.DataFrame],
    full: dict[str, pd.DataFrame] | None,
    readiness: dict[str, Any],
    sample_summary: dict[str, Any],
    full_summary: dict[str, Any] | None,
) -> Path:
    sheets = {
        "sample_quality": sample["quality"],
        "sample_selection_diff": sample["selection_diff"],
        "sample_holdings_diff": sample["holdings_diff"],
        "sample_audit_head": sample["audit"].head(5000),
        "readiness": pd.DataFrame([to_jsonable(readiness)]),
        "sample_summary": pd.DataFrame([to_jsonable(sample_summary)]),
    }
    if full:
        sheets.update(
            {
                "full_quality": full["quality"],
                "full_selection_diff": full["selection_diff"],
                "full_holdings_diff": full["holdings_diff"],
                "full_audit_head": full["audit"].head(5000),
                "full_summary": pd.DataFrame([to_jsonable(full_summary or {})]),
            }
        )
    path = out_dir / "reports" / f"v8_2_bounded_audit_replay_workbook_{timestamp}.xlsx"
    write_excel(sheets, path)
    return path


def update_next_steps(
    out_dir: Path,
    zip_path: Path,
    sample_summary: dict[str, Any],
    full_summary: dict[str, Any] | None,
    readiness: dict[str, Any],
) -> None:
    path = PROJECT_ROOT / "NEXT_STEPS.md"
    previous = path.read_text(encoding="utf-8") if path.exists() else "# NEXT_STEPS\n"
    section = f"""

## v8.2 bounded audit replay

- 执行状态：completed，随后按要求暂停，不自动进入 reranking replay。
- 输出目录：`{out_dir}`
- zip：`{zip_path}`
- 是否完成 sample：`True`
- sample 是否通过：`{sample_summary.get('quality_pass_all')}`
- 是否完成 full：`{bool(full_summary)}`
- full 是否生成 full candidate score/rank：`{readiness.get('has_full_candidate_universe')}`
- 是否复现 baseline selection：`{readiness.get('baseline_selection_reproduced')}`
- 是否具备 gate-aware reranking replay 条件：`{readiness.get('can_run_gate_aware_reranking_replay')}`
- 下一步是否需要用户/ChatGPT 批准：`True`
- 本轮边界：未进入 v9，未扩 universe，未运行 31b，未做 reranking replay，未改变 v8 选股逻辑。
"""
    path.write_text(previous.rstrip() + "\n" + section, encoding="utf-8")


def write_run_summary(out_dir: Path, zip_path: Path, readiness: dict[str, Any]) -> None:
    text = f"""# RUN_SUMMARY

本轮目标：v8.2 bounded score/rank audit replay。

新 run 目录：`{out_dir}`

zip：`{zip_path}`

是否进入 v9：`False`

是否扩 universe：`False`

是否运行 31b：`False`

是否做 reranking replay：`False`

是否改变 v8 选股逻辑：`False`

是否生成 full candidate score/rank：`{readiness.get('has_full_candidate_universe')}`

baseline_selection_reproduced：`{readiness.get('baseline_selection_reproduced')}`

can_run_gate_aware_reranking_replay：`{readiness.get('can_run_gate_aware_reranking_replay')}`

后续：暂停，等待用户/ChatGPT 是否批准 bounded gate-aware reranking replay。
"""
    (out_dir / "RUN_SUMMARY.md").write_text(text, encoding="utf-8")
    (PROJECT_ROOT / "RUN_SUMMARY.md").write_text(text, encoding="utf-8")


def package_outputs(out_dir: Path, docs: list[Path], zip_path: Path) -> None:
    files = [
        PROJECT_ROOT / "scripts" / "us_stock_selection" / "40_run_v8_2_bounded_audit_replay.py",
        PROJECT_ROOT / "quant_lab" / "us_stock_selection" / "v8_paper_trading.py",
        PROJECT_ROOT / "quant_lab" / "us_stock_selection" / "v8_2_audit_trail.py",
        PROJECT_ROOT / "NEXT_STEPS.md",
        PROJECT_ROOT / "RUN_SUMMARY.md",
    ]
    files.extend(docs)
    files.extend([p for p in out_dir.rglob("*") if p.is_file()])
    seen: set[str] = set()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            if not path.exists():
                continue
            arcname = str(path.relative_to(PROJECT_ROOT)) if path.is_relative_to(PROJECT_ROOT) else path.name
            if arcname in seen:
                continue
            seen.add(arcname)
            archive.write(path, arcname)


def sync_meistock(
    timestamp: str,
    out_dir: Path,
    zip_path: Path,
    report_path: Path,
    exec_path: Path,
    readiness: dict[str, Any],
) -> None:
    if not MEISTOCK_ROOT.exists():
        return
    targets = [
        MEISTOCK_ROOT / "01_对话沉淀" / "Codex",
        MEISTOCK_ROOT / "02_项目文档" / "报告章节底稿",
        MEISTOCK_ROOT / "03_决策日志",
        MEISTOCK_ROOT / "06_证据链",
        MEISTOCK_ROOT / "07_附件索引",
        MEISTOCK_ROOT / "docs" / "context",
    ]
    for target in targets:
        target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(report_path, MEISTOCK_ROOT / "02_项目文档" / "报告章节底稿" / report_path.name)
    shutil.copy2(exec_path, MEISTOCK_ROOT / "02_项目文档" / "报告章节底稿" / exec_path.name)
    for name in [
        "v8_2_reranking_readiness_after_bounded_replay.json",
        "v8_2_full_audit_quality.csv",
        "v8_2_replay_vs_baseline_selection_diff.csv",
        "v8_2_sample_audit_quality.csv",
    ]:
        source = out_dir / name
        if source.exists():
            shutil.copy2(source, MEISTOCK_ROOT / "06_证据链" / f"{timestamp}_{name}")
    if zip_path.exists():
        shutil.copy2(zip_path, MEISTOCK_ROOT / "07_附件索引" / zip_path.name)
    checkpoint = f"""# Codex Checkpoint - v8.2 Bounded Audit Replay {timestamp}

## Result

- Output directory: `{out_dir}`
- Zip: `{zip_path}`
- can_run_gate_aware_reranking_replay: `{readiness.get('can_run_gate_aware_reranking_replay')}`
- baseline_selection_reproduced: `{readiness.get('baseline_selection_reproduced')}`

## Boundary

No v9, no universe expansion, no 31b, no reranking replay, no strategy optimization.
"""
    (MEISTOCK_ROOT / "01_对话沉淀" / "Codex" / f"{timestamp}_v8_2_bounded_audit_replay_checkpoint.md").write_text(
        checkpoint,
        encoding="utf-8",
    )
    context = f"""# MeiStock Current Context

Last updated: {timestamp}

Latest checkpoint: v8.2 bounded score/rank audit replay.

Reranking readiness: `{readiness.get('can_run_gate_aware_reranking_replay')}`.

Next action requires user/ChatGPT approval. Do not enter reranking replay automatically.
"""
    (MEISTOCK_ROOT / "docs" / "context" / "MeiStock_current_context.md").write_text(context, encoding="utf-8")


def date_str(value: Any) -> str:
    return "" if pd.isna(value) else pd.Timestamp(value).date().isoformat()


def main() -> None:
    args = parse_args()
    timestamp = args.timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = (args.out_dir or OUTPUT_ROOT / f"v8_2_bounded_audit_replay_{timestamp}").resolve()
    (out_dir / "reports").mkdir(parents=True, exist_ok=True)
    logger = setup_logger(out_dir)
    logger.info("Starting v8.2 bounded score/rank audit replay.")
    logger.info("Boundaries: no v9, no universe expansion, no 31b, no reranking replay, no strategy optimization.")
    paths = ensure_inputs(args.run_dir)
    baseline_ledger, baseline_holdings = normalize_baseline(read_csv(paths["ledger"]), read_csv(paths["holdings"]))
    sample_requested = parse_sample_months(args.sample_months)
    sample_decisions, sample_resolution_warnings = resolve_sample_decisions(baseline_ledger, sample_requested)
    sample_decisions = limit_decisions(sample_decisions, args.max_decision_dates)
    dryrun = {
        "dry_run": True,
        "run_dir": args.run_dir,
        "run_dir_exists": args.run_dir.exists(),
        "run_config_readable": paths["run_config"].exists(),
        "feature_cache_readable": paths["feature_cache"].exists(),
        "monthly_ledger_readable": paths["ledger"].exists(),
        "monthly_holdings_readable": paths["holdings"].exists(),
        "audit_hook_callable": callable(build_score_rank_audit_for_decision),
        "out_dir": out_dir,
        "sample_requested_months": sample_requested,
        "sample_resolved_decision_dates": [date_str(x) for x in sample_decisions["decision_date"].tolist()],
        "stopped_before": "bounded_replay_computation",
    }
    write_json(dryrun, out_dir / "v8_2_bounded_audit_replay_dryrun.json")
    if args.dry_run:
        logger.info("Dry-run completed: %s", dryrun)
        return

    max_end = pd.Timestamp(baseline_ledger["decision_date"].max()) + pd.Timedelta(days=100)
    context = load_replay_context(args.run_dir, args.provider_uri, max_end, logger)
    audit_replay_id = f"v8_2_bounded_audit_replay_{timestamp}"
    sample = run_phase(
        phase="sample",
        run_id=args.run_dir.name,
        audit_replay_id=audit_replay_id,
        decisions=sample_decisions,
        baseline_ledger=baseline_ledger,
        baseline_holdings=baseline_holdings,
        context=context,
        audit_forward_returns=bool_arg(args.audit_forward_returns),
        out_dir=out_dir,
        logger=logger,
    )
    if not sample_resolution_warnings.empty:
        sample["warnings"] = pd.concat([sample_resolution_warnings, sample["warnings"]], ignore_index=True)
        sample["warnings"].to_csv(out_dir / "v8_2_sample_audit_warnings.csv", index=False, encoding="utf-8-sig")
    sample_summary = summarize_phase(
        phase="sample",
        audit=sample["audit"],
        quality=sample["quality"],
        selection_diff_df=sample["selection_diff"],
        holdings_diff_df=sample["holdings_diff"],
        warnings=sample["warnings"],
        requested_sample_months=sample_requested,
        resolved_decisions=sample_decisions,
    )
    write_json(sample_summary, out_dir / "v8_2_sample_replay_summary.json")
    sample_passed = bool(sample_summary["quality_pass_all"] and sample_summary["selection_diff_count"] == 0)
    full: dict[str, pd.DataFrame] | None = None
    full_summary: dict[str, Any] | None = None
    readiness_source = sample
    full_executed = False
    if sample_passed and args.full:
        full_decisions = baseline_ledger.copy()
        full_decisions = limit_decisions(full_decisions, args.max_decision_dates)
        full = run_phase(
            phase="full",
            run_id=args.run_dir.name,
            audit_replay_id=audit_replay_id,
            decisions=full_decisions,
            baseline_ledger=baseline_ledger,
            baseline_holdings=baseline_holdings,
            context=context,
            audit_forward_returns=bool_arg(args.audit_forward_returns),
            out_dir=out_dir,
            logger=logger,
        )
        full_summary = summarize_phase(
            phase="full",
            audit=full["audit"],
            quality=full["quality"],
            selection_diff_df=full["selection_diff"],
            holdings_diff_df=full["holdings_diff"],
            warnings=full["warnings"],
            resolved_decisions=full_decisions,
        )
        write_json(full_summary, out_dir / "v8_2_bounded_audit_replay_summary.json")
        readiness_source = full
        full_executed = True
    elif not sample_passed:
        logger.warning("Sample validation failed; full bounded audit replay is blocked.")
        write_json(
            {
                "full_executed": False,
                "blocked_by": "sample validation failed",
                "required_patch": "fix bounded audit replay sample differences before full replay",
                "sample_summary": sample_summary,
            },
            out_dir / "v8_2_bounded_audit_replay_summary.json",
        )
    else:
        write_json(
            {
                "full_executed": False,
                "blocked_by": "--full not supplied",
                "sample_summary": sample_summary,
            },
            out_dir / "v8_2_bounded_audit_replay_summary.json",
        )
    readiness = readiness_after_bounded_replay(
        readiness_source["audit"],
        readiness_source["quality"],
        readiness_source["selection_diff"],
    )
    write_json(readiness, out_dir / "v8_2_reranking_readiness_after_bounded_replay.json")
    zip_path = OUTPUT_ROOT / f"us_stock_selection_quant_lab_v8_2_bounded_audit_replay_{timestamp}.zip"
    report_path, exec_path = write_reports(
        timestamp=timestamp,
        out_dir=out_dir,
        zip_path=zip_path,
        sample_summary=sample_summary,
        full_summary=full_summary,
        sample_quality=sample["quality"],
        full_quality=full["quality"] if full else pd.DataFrame(),
        sample_diff=sample["selection_diff"],
        full_diff=full["selection_diff"] if full else pd.DataFrame(),
        readiness=readiness,
        sample_passed=sample_passed,
        full_executed=full_executed,
    )
    workbook_path = write_workbook(out_dir, timestamp, sample, full, readiness, sample_summary, full_summary)
    logger.info("Wrote bounded audit replay workbook: %s", workbook_path)
    update_next_steps(out_dir, zip_path, sample_summary, full_summary, readiness)
    write_run_summary(out_dir, zip_path, readiness)
    package_outputs(out_dir, [report_path, exec_path], zip_path)
    sync_meistock(timestamp, out_dir, zip_path, report_path, exec_path, readiness)
    logger.info("Packaged bounded audit replay zip: %s", zip_path)


if __name__ == "__main__":
    main()
