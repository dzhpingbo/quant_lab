"""v8.2 score/rank audit-trail helpers.

The helpers in this module are instrumentation only. They do not fit models,
change selection logic, expand the universe, or run any reranking. Forward
columns are prefixed with ``audit_forward_`` and must remain audit-only.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


HIGH_BETA_TICKERS = {"MSTR", "TQQQ", "QLD", "SOXL"}
ETF_TICKERS = {"QQQ", "QLD", "TQQQ", "SPY", "SSO", "UPRO", "SOXL", "XLK", "SHY", "TLT"}

KEY_COLUMNS = ["run_id", "decision_date", "rebalance_month", "ticker"]

EX_ANTE_COLUMNS = [
    "candidate_flag",
    "tradable_flag",
    "exclusion_reason",
    "raw_score",
    "adjusted_score",
    "raw_rank",
    "adjusted_rank",
    "selected_flag",
    "selected_rank",
    "target_weight_before_overlay",
    "target_weight_after_overlay",
    "final_weight",
    "selection_rule",
    "model_name",
    "score_source",
    "feature_snapshot_date",
]

RISK_COLUMNS = [
    "trailing_20d_return",
    "trailing_63d_return",
    "trailing_126d_return",
    "trailing_252d_return",
    "trailing_20d_vol",
    "trailing_63d_vol",
    "trailing_126d_vol",
    "trailing_63d_maxdd",
    "distance_to_252d_high",
    "high_beta_flag",
    "high_beta_group",
    "previous_selected_count_12m",
    "previous_avg_weight_12m",
    "previous_concentration_penalty",
]

FORWARD_AUDIT_COLUMNS = [
    "audit_forward_21d_return",
    "audit_forward_42d_return",
    "audit_forward_63d_return",
    "audit_forward_selected_period_return",
    "audit_forward_realized_vol",
    "audit_forward_maxdd",
]

AUDIT_TRAIL_COLUMNS = (
    KEY_COLUMNS
    + ["asset_type", "universe_layer"]
    + EX_ANTE_COLUMNS
    + RISK_COLUMNS
    + FORWARD_AUDIT_COLUMNS
    + [
        "reconstruction_scope",
        "current_pipeline_cannot_reconstruct_full_unselected_scores",
        "original_tradable_count",
        "warning",
    ]
)


def schema_rows() -> pd.DataFrame:
    """Return the documented v8.2 audit-trail schema."""
    rows: list[dict[str, Any]] = []
    for group, columns, audit_only in [
        ("key", KEY_COLUMNS + ["asset_type", "universe_layer"], False),
        ("ex_ante_selection", EX_ANTE_COLUMNS, False),
        ("ex_ante_risk_concentration", RISK_COLUMNS, False),
        ("forward_audit", FORWARD_AUDIT_COLUMNS, True),
    ]:
        for col in columns:
            rows.append(
                {
                    "field_name": col,
                    "field_group": group,
                    "audit_only": bool(audit_only),
                    "lookahead_allowed": bool(audit_only),
                    "description": _field_description(col),
                }
            )
    return pd.DataFrame(rows)


def _field_description(field: str) -> str:
    descriptions = {
        "run_id": "Research run identifier or source run directory name.",
        "decision_date": "Date when the monthly selection decision is made.",
        "rebalance_month": "Decision month in YYYY-MM format.",
        "ticker": "Candidate ticker.",
        "asset_type": "Best-effort stock/ETF tag.",
        "universe_layer": "Best-effort source layer for the candidate universe.",
        "candidate_flag": "True when the ticker exists in the prediction snapshot.",
        "tradable_flag": "True when the ticker passes v8 tradability filters.",
        "exclusion_reason": "Reason a candidate is excluded before ranking/selection.",
        "raw_score": "Raw model prediction score from the v8 scoring step.",
        "adjusted_score": "Score after ex-ante reranking penalties; equal to raw score for v8 baseline.",
        "raw_rank": "Rank by raw score.",
        "adjusted_rank": "Rank after tradability/adjustment; v8 selection uses this ordering.",
        "selected_flag": "True when the ticker is selected for the target holdings.",
        "selected_rank": "1-based rank among selected tickers.",
        "target_weight_before_overlay": "Target weight from selection before any overlay.",
        "target_weight_after_overlay": "Target weight after overlay; same as before overlay for v8 baseline.",
        "final_weight": "Final target weight for the replay.",
        "selection_rule": "Selection rule name.",
        "model_name": "Model used to produce score.",
        "score_source": "Score source artifact or runtime step.",
        "feature_snapshot_date": "Feature date used for scoring.",
        "previous_concentration_penalty": "Simple lagged concentration proxy from prior selected history.",
    }
    if field.startswith("trailing_"):
        return "Lagged risk/momentum feature computed using data no later than decision_date."
    if field.startswith("audit_forward_"):
        return "Audit-only forward outcome field. Must never enter score/rank/selection."
    if field == "high_beta_flag":
        return "True for configured high-beta tickers."
    if field == "high_beta_group":
        return "High-beta group label when available."
    if field.startswith("previous_"):
        return "Lagged selection-history feature computed from prior decisions only."
    return descriptions.get(field, "")


def parse_selected_scores(raw: Any) -> dict[str, float]:
    """Parse v8 selected_scores text like ``AAPL:0.1;MSFT:0.2``."""
    out: dict[str, float] = {}
    if raw is None or (isinstance(raw, float) and math.isnan(raw)):
        return out
    for part in str(raw).split(";"):
        if ":" not in part:
            continue
        ticker, score = part.split(":", 1)
        ticker = ticker.strip().upper()
        if not ticker:
            continue
        try:
            out[ticker] = float(score)
        except ValueError:
            out[ticker] = np.nan
    return out


def build_score_rank_audit_for_decision(
    *,
    run_id: str,
    decision_date: pd.Timestamp,
    feature_date: pd.Timestamp,
    execution_date: pd.Timestamp,
    pred: pd.DataFrame,
    tradable: list[str],
    selected: pd.DataFrame,
    current_weights: pd.Series,
    close: pd.DataFrame,
    dollar_volume: pd.DataFrame | None = None,
    selection_history: pd.DataFrame | None = None,
    selected_period_end_date: pd.Timestamp | None = None,
    model_name: str = "",
    feature_set: str = "",
    label: str = "",
    selection_rule: str = "top5_equal_monthly",
    score_source: str = "runtime_model_prediction",
    audit_forward_returns: bool = True,
) -> pd.DataFrame:
    """Build full candidate-level audit rows during a future replay.

    ``pred`` should be the full prediction snapshot before the tradability
    filter. This function keeps non-tradable candidate rows and labels their
    exclusion reason, so future diagnostics can see what was not selected.
    """
    if pred.empty:
        return empty_audit_frame()
    local = pred.copy()
    if "instrument" not in local.columns and "ticker" in local.columns:
        local = local.rename(columns={"ticker": "instrument"})
    local["ticker"] = local["instrument"].astype(str).str.upper()
    local["raw_score"] = pd.to_numeric(local.get("score", np.nan), errors="coerce")
    tradable_set = {str(t).upper() for t in tradable}
    selected_tickers = selected.get("instrument", pd.Series(dtype=str)).astype(str).str.upper().tolist() if not selected.empty else []
    selected_set = set(selected_tickers)
    raw_rank = local["raw_score"].rank(method="first", ascending=False)
    local["raw_rank"] = raw_rank

    tradable_rank = (
        local.loc[local["ticker"].isin(tradable_set), ["ticker", "raw_score"]]
        .sort_values("raw_score", ascending=False)
        .assign(adjusted_rank=lambda x: np.arange(1, len(x) + 1))
        .set_index("ticker")["adjusted_rank"]
    )
    selected_rank = {ticker: idx + 1 for idx, ticker in enumerate(selected_tickers)}
    rows: list[dict[str, Any]] = []
    for item in local.itertuples(index=False):
        ticker = str(item.ticker).upper()
        tradable_flag = ticker in tradable_set
        selected_flag = ticker in selected_set
        risk = trailing_risk_features(close, ticker, decision_date)
        prev = previous_selection_features(selection_history, ticker, decision_date)
        forward = (
            forward_audit_features(close, ticker, execution_date, selected_period_end_date)
            if audit_forward_returns
            else {col: np.nan for col in FORWARD_AUDIT_COLUMNS}
        )
        weight = float(current_weights.get(ticker, 0.0)) if current_weights is not None else 0.0
        row = {
            "run_id": run_id,
            "decision_date": date_str(decision_date),
            "rebalance_month": pd.Timestamp(decision_date).to_period("M").strftime("%Y-%m"),
            "ticker": ticker,
            "asset_type": asset_type_for_ticker(ticker),
            "universe_layer": "v8_alpha360_prediction_snapshot",
            "candidate_flag": True,
            "tradable_flag": bool(tradable_flag),
            "exclusion_reason": "" if tradable_flag else "not_tradable_liquidity_or_close_filter",
            "raw_score": float(item.raw_score) if pd.notna(item.raw_score) else np.nan,
            "adjusted_score": float(item.raw_score) if tradable_flag and pd.notna(item.raw_score) else np.nan,
            "raw_rank": int(getattr(item, "raw_rank")) if pd.notna(getattr(item, "raw_rank")) else np.nan,
            "adjusted_rank": int(tradable_rank.get(ticker)) if ticker in tradable_rank.index else np.nan,
            "selected_flag": bool(selected_flag),
            "selected_rank": selected_rank.get(ticker, np.nan),
            "target_weight_before_overlay": weight,
            "target_weight_after_overlay": weight,
            "final_weight": weight,
            "selection_rule": selection_rule,
            "model_name": model_name,
            "score_source": score_source,
            "feature_snapshot_date": date_str(feature_date),
            **risk,
            **prev,
            **forward,
            "reconstruction_scope": "full_runtime_candidate_snapshot",
            "current_pipeline_cannot_reconstruct_full_unselected_scores": False,
            "original_tradable_count": int(len(tradable_set)),
            "warning": "",
        }
        rows.append(row)
    return order_audit_columns(pd.DataFrame(rows))


def build_selected_only_audit_from_existing(
    *,
    run_id: str,
    ledger: pd.DataFrame,
    holdings: pd.DataFrame,
    close: pd.DataFrame | None = None,
    sample_months: list[str] | None = None,
    audit_forward_returns: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reconstruct the maximum honest audit trail available from old v8 outputs.

    Existing v8 artifacts contain selected tickers and selected scores only.
    This function deliberately does not fabricate unselected candidate rows.
    """
    if ledger.empty or holdings.empty:
        return empty_audit_frame(), pd.DataFrame(
            [
                {
                    "warning_type": "missing_inputs",
                    "severity": "high",
                    "message": "monthly_decision_ledger or monthly_holdings is empty",
                }
            ]
        )

    local_ledger = ledger.copy()
    local_holdings = holdings.copy()
    for col in ["decision_date", "feature_date", "execution_date"]:
        if col in local_ledger.columns:
            local_ledger[col] = pd.to_datetime(local_ledger[col], errors="coerce")
    for col in ["decision_date", "execution_date"]:
        if col in local_holdings.columns:
            local_holdings[col] = pd.to_datetime(local_holdings[col], errors="coerce")
    local_holdings["ticker"] = local_holdings["ticker"].astype(str).str.upper()
    local_holdings["weight"] = pd.to_numeric(local_holdings.get("weight", 0.0), errors="coerce").fillna(0.0)

    if sample_months:
        wanted = set(sample_months)
        local_ledger = local_ledger.loc[local_ledger["decision_date"].dt.to_period("M").astype(str).isin(wanted)].copy()
        if local_ledger.empty:
            local_ledger = choose_representative_ledger_rows(ledger, sample_months)

    rows: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for _, decision in local_ledger.iterrows():
        decision_date = pd.Timestamp(decision.get("decision_date"))
        execution_date = pd.Timestamp(decision.get("execution_date")) if pd.notna(decision.get("execution_date")) else decision_date
        feature_date = pd.Timestamp(decision.get("feature_date")) if pd.notna(decision.get("feature_date")) else decision_date
        selected_scores = parse_selected_scores(decision.get("selected_scores"))
        selected_tickers = [ticker.strip().upper() for ticker in str(decision.get("selected_tickers", "")).split(",") if ticker.strip()]
        selected_month = decision_date.to_period("M").strftime("%Y-%m")
        history = local_holdings.loc[local_holdings["decision_date"] < decision_date].copy()
        holding_group = local_holdings.loc[local_holdings["decision_date"] == decision_date].copy()
        original_tradable_count = int(decision.get("tradable_count", len(selected_tickers))) if pd.notna(decision.get("tradable_count", np.nan)) else len(selected_tickers)
        next_date = next_execution_date(local_ledger, decision_date)
        for selected_rank, ticker in enumerate(selected_tickers, start=1):
            holding = holding_group.loc[holding_group["ticker"] == ticker].head(1)
            final_weight = float(holding["weight"].iloc[0]) if not holding.empty else np.nan
            risk = trailing_risk_features(close, ticker, decision_date) if close is not None else empty_risk_features(ticker)
            prev = previous_selection_features(history, ticker, decision_date)
            forward = (
                forward_audit_features(close, ticker, execution_date, next_date)
                if audit_forward_returns and close is not None
                else {col: np.nan for col in FORWARD_AUDIT_COLUMNS}
            )
            rows.append(
                {
                    "run_id": run_id,
                    "decision_date": date_str(decision_date),
                    "rebalance_month": selected_month,
                    "ticker": ticker,
                    "asset_type": asset_type_for_ticker(ticker),
                    "universe_layer": "reconstructed_from_selected_v8_outputs",
                    "candidate_flag": True,
                    "tradable_flag": True,
                    "exclusion_reason": "",
                    "raw_score": selected_scores.get(ticker, np.nan),
                    "adjusted_score": selected_scores.get(ticker, np.nan),
                    "raw_rank": selected_rank,
                    "adjusted_rank": selected_rank,
                    "selected_flag": True,
                    "selected_rank": selected_rank,
                    "target_weight_before_overlay": final_weight,
                    "target_weight_after_overlay": final_weight,
                    "final_weight": final_weight,
                    "selection_rule": "top5_equal_monthly",
                    "model_name": str(decision.get("model", "")),
                    "score_source": "selected_scores_from_monthly_decision_ledger_only",
                    "feature_snapshot_date": date_str(feature_date),
                    **risk,
                    **prev,
                    **forward,
                    "reconstruction_scope": "selected_only_existing_v8_artifact",
                    "current_pipeline_cannot_reconstruct_full_unselected_scores": True,
                    "original_tradable_count": original_tradable_count,
                    "warning": "unselected candidate scores/ranks were not persisted in the original v8 run",
                }
            )
        if original_tradable_count <= len(selected_tickers):
            severity = "high"
            msg = "candidate_count is not greater than selected_count; this audit is selected-only"
        else:
            severity = "high"
            msg = f"original v8 ledger reports tradable_count={original_tradable_count}, but only {len(selected_tickers)} selected rows can be reconstructed"
        warnings.append(
            {
                "decision_date": date_str(decision_date),
                "warning_type": "selected_only_reconstruction",
                "severity": severity,
                "message": msg,
                "missing_dependency": "full runtime pred/ranked candidate snapshot was not saved",
                "required_upstream_patch": "save v8_2_score_rank_audit_trail.csv inside run_paper_trading_replay when pred/ranked exists",
            }
        )
    return order_audit_columns(pd.DataFrame(rows)), pd.DataFrame(warnings)


def choose_representative_ledger_rows(ledger: pd.DataFrame, requested_months: list[str]) -> pd.DataFrame:
    local = ledger.copy()
    local["decision_date"] = pd.to_datetime(local["decision_date"], errors="coerce")
    local = local.dropna(subset=["decision_date"]).sort_values("decision_date")
    if local.empty:
        return local
    rows = []
    for month in requested_months:
        match = local.loc[local["decision_date"].dt.to_period("M").astype(str) == month].head(1)
        if not match.empty:
            rows.append(match)
    if rows:
        return pd.concat(rows, ignore_index=True).drop_duplicates("decision_date")
    idx = sorted({0, len(local) // 2, len(local) - 1})
    return local.iloc[idx].copy()


def validate_audit_quality(audit: pd.DataFrame, holdings: pd.DataFrame, ledger: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Validate decision-date x ticker key integrity and selected consistency."""
    if audit.empty:
        return pd.DataFrame(), pd.DataFrame(
            [{"warning_type": "empty_audit", "severity": "high", "message": "audit trail is empty"}]
        )
    local = audit.copy()
    local["decision_date"] = pd.to_datetime(local["decision_date"], errors="coerce")
    h = holdings.copy()
    if not h.empty:
        h["decision_date"] = pd.to_datetime(h["decision_date"], errors="coerce")
        h["ticker"] = h["ticker"].astype(str).str.upper()
    l = ledger.copy()
    if not l.empty:
        l["decision_date"] = pd.to_datetime(l["decision_date"], errors="coerce")
    rows: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for decision_date, group in local.groupby("decision_date"):
        selected = group.loc[group["selected_flag"].astype(bool)].copy()
        key_dupes = int(group.duplicated(["decision_date", "ticker"]).sum())
        holding_tickers = set(h.loc[h["decision_date"] == decision_date, "ticker"].astype(str).str.upper()) if not h.empty else set()
        selected_tickers = set(selected["ticker"].astype(str).str.upper())
        selected_consistent = bool(selected_tickers == holding_tickers)
        selected_count_matches = bool(len(selected_tickers) == len(holding_tickers))
        original_tradable_count = int(pd.to_numeric(group.get("original_tradable_count", pd.Series([len(group)])), errors="coerce").dropna().max()) if "original_tradable_count" in group else len(group)
        candidate_count = int(len(group))
        selected_count = int(len(selected))
        unselected_count = int((~group["selected_flag"].astype(bool)).sum())
        score_missing_count = int(group["raw_score"].isna().sum()) if "raw_score" in group else candidate_count
        rank_missing_count = int(group["raw_rank"].isna().sum()) if "raw_rank" in group else candidate_count
        raw_score_non_null_rate = float(group["raw_score"].notna().mean()) if "raw_score" in group and candidate_count else 0.0
        raw_rank_non_null_rate = float(group["raw_rank"].notna().mean()) if "raw_rank" in group and candidate_count else 0.0
        adjusted_score_non_null_rate = float(group["adjusted_score"].notna().mean()) if "adjusted_score" in group and candidate_count else 0.0
        adjusted_rank_non_null_rate = float(group["adjusted_rank"].notna().mean()) if "adjusted_rank" in group and candidate_count else 0.0
        missing_ticker_count = int(group["ticker"].isna().sum() + (group["ticker"].astype(str).str.len() == 0).sum())
        quality_pass = bool(
            key_dupes == 0
            and selected_consistent
            and selected_count_matches
            and candidate_count > selected_count
            and raw_score_non_null_rate > 0.95
            and raw_rank_non_null_rate > 0.95
            and missing_ticker_count == 0
        )
        if candidate_count <= selected_count:
            warnings.append(
                {
                    "decision_date": date_str(decision_date),
                    "warning_type": "selected_only_quality_fail",
                    "severity": "high",
                    "message": "candidate_count is not greater than selected_count; full unselected candidates are missing",
                }
            )
        rows.append(
            {
                "decision_date": date_str(decision_date),
                "candidate_count": candidate_count,
                "original_tradable_count": original_tradable_count,
                "selected_count": selected_count,
                "unselected_count": unselected_count,
                "raw_score_non_null_rate": raw_score_non_null_rate,
                "raw_rank_non_null_rate": raw_rank_non_null_rate,
                "adjusted_score_non_null_rate": adjusted_score_non_null_rate,
                "adjusted_rank_non_null_rate": adjusted_rank_non_null_rate,
                "selected_flag_consistent_with_holdings": selected_consistent,
                "selected_count_matches_holdings": selected_count_matches,
                "duplicate_key_count": key_dupes,
                "missing_ticker_count": missing_ticker_count,
                "score_missing_count": score_missing_count,
                "rank_missing_count": rank_missing_count,
                "quality_pass": quality_pass,
                "warnings": "selected-only audit trail" if candidate_count <= selected_count else "",
            }
        )
    return pd.DataFrame(rows), pd.DataFrame(warnings)


def reranking_readiness(audit: pd.DataFrame, quality: pd.DataFrame) -> dict[str, Any]:
    if audit.empty:
        blockers = ["audit trail is empty"]
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
            "can_run_gate_aware_reranking_replay": False,
            "blockers": blockers,
            "next_required_patch": "generate non-empty score/rank audit trail",
        }
    has_full_candidate_universe = bool(not quality.empty and (quality["candidate_count"] > quality["selected_count"]).all())
    has_unselected_tickers = bool((~audit["selected_flag"].astype(bool)).any()) if "selected_flag" in audit else False
    has_full_raw_score = bool(has_full_candidate_universe and audit["raw_score"].notna().mean() > 0.95) if "raw_score" in audit else False
    has_full_raw_rank = bool(has_full_candidate_universe and audit["raw_rank"].notna().mean() > 0.95) if "raw_rank" in audit else False
    has_adjusted_score = bool(has_full_candidate_universe and audit["adjusted_score"].notna().mean() > 0.95) if "adjusted_score" in audit else False
    has_adjusted_rank = bool(has_full_candidate_universe and audit["adjusted_rank"].notna().mean() > 0.95) if "adjusted_rank" in audit else False
    selected_flag_validated = bool(not quality.empty and quality["selected_flag_consistent_with_holdings"].all() and quality["selected_count_matches_holdings"].all())
    risk_cols = [c for c in RISK_COLUMNS if c in audit.columns and not c.startswith("previous_") and c not in {"high_beta_flag", "high_beta_group"}]
    has_ex_ante_risk_features = bool(risk_cols and audit[risk_cols].notna().mean().mean() > 0.50)
    has_forward_audit_fields = bool(all(c in audit.columns for c in FORWARD_AUDIT_COLUMNS) and audit[FORWARD_AUDIT_COLUMNS].notna().any().any())
    blockers: list[str] = []
    if not has_full_candidate_universe:
        blockers.append("full candidate universe rows are missing; audit remains selected-only")
    if not has_unselected_tickers:
        blockers.append("unselected tickers are absent")
    if not (has_full_raw_score or has_adjusted_score):
        blockers.append("full candidate raw/adjusted scores are missing")
    if not selected_flag_validated:
        blockers.append("selected_flag consistency did not validate")
    if not has_ex_ante_risk_features:
        blockers.append("ex-ante risk feature coverage is insufficient")
    can_run = bool(
        has_full_candidate_universe
        and has_unselected_tickers
        and (has_full_raw_score or has_adjusted_score)
        and "selected_flag" in audit.columns
        and selected_flag_validated
        and has_ex_ante_risk_features
    )
    return {
        "has_full_candidate_universe": has_full_candidate_universe,
        "has_unselected_tickers": has_unselected_tickers,
        "has_raw_score": has_full_raw_score,
        "has_raw_rank": has_full_raw_rank,
        "has_adjusted_score": has_adjusted_score,
        "has_adjusted_rank": has_adjusted_rank,
        "has_selected_flag": "selected_flag" in audit.columns,
        "selected_flag_validated": selected_flag_validated,
        "has_ex_ante_risk_features": has_ex_ante_risk_features,
        "has_forward_audit_fields": has_forward_audit_fields,
        "has_selected_only_raw_score": bool("raw_score" in audit.columns and audit["raw_score"].notna().any()),
        "can_run_gate_aware_reranking_replay": can_run,
        "blockers": blockers,
        "next_required_patch": "continue upstream logging: persist full pred/tradable/ranked snapshot from run_paper_trading_replay without retraining current v8 baseline",
    }


def trailing_risk_features(close: pd.DataFrame | None, ticker: str, decision_date: pd.Timestamp) -> dict[str, Any]:
    out = empty_risk_features(ticker)
    if close is None or close.empty or ticker not in close.columns:
        return out
    series = pd.to_numeric(close[ticker], errors="coerce").loc[:pd.Timestamp(decision_date)].dropna()
    if series.empty:
        return out
    for window in [20, 63, 126, 252]:
        out[f"trailing_{window}d_return"] = trailing_return(series, window)
    returns = series.pct_change(fill_method=None).dropna()
    for window in [20, 63, 126]:
        local = returns.tail(window)
        out[f"trailing_{window}d_vol"] = float(local.std(ddof=0) * math.sqrt(252.0)) if len(local) >= 5 else np.nan
    out["trailing_63d_maxdd"] = max_drawdown(series.tail(64))
    if len(series.tail(252)) >= 20:
        high = float(series.tail(252).max())
        out["distance_to_252d_high"] = float(series.iloc[-1] / high - 1.0) if high else np.nan
    return out


def empty_risk_features(ticker: str) -> dict[str, Any]:
    return {
        "trailing_20d_return": np.nan,
        "trailing_63d_return": np.nan,
        "trailing_126d_return": np.nan,
        "trailing_252d_return": np.nan,
        "trailing_20d_vol": np.nan,
        "trailing_63d_vol": np.nan,
        "trailing_126d_vol": np.nan,
        "trailing_63d_maxdd": np.nan,
        "distance_to_252d_high": np.nan,
        "high_beta_flag": ticker in HIGH_BETA_TICKERS,
        "high_beta_group": "high_beta_proxy" if ticker in HIGH_BETA_TICKERS else "",
    }


def previous_selection_features(selection_history: pd.DataFrame | None, ticker: str, decision_date: pd.Timestamp) -> dict[str, Any]:
    if selection_history is None or selection_history.empty:
        return {"previous_selected_count_12m": 0, "previous_avg_weight_12m": 0.0, "previous_concentration_penalty": 0.0}
    local = selection_history.copy()
    if "decision_date" not in local.columns or "ticker" not in local.columns:
        return {"previous_selected_count_12m": 0, "previous_avg_weight_12m": 0.0, "previous_concentration_penalty": 0.0}
    local["decision_date"] = pd.to_datetime(local["decision_date"], errors="coerce")
    local["ticker"] = local["ticker"].astype(str).str.upper()
    start = pd.Timestamp(decision_date) - pd.DateOffset(months=12)
    local = local.loc[(local["decision_date"] < pd.Timestamp(decision_date)) & (local["decision_date"] >= start) & (local["ticker"] == ticker)]
    count = int(local["decision_date"].dt.to_period("M").nunique()) if not local.empty else 0
    avg_weight = float(pd.to_numeric(local.get("weight", 0.0), errors="coerce").mean()) if not local.empty else 0.0
    return {
        "previous_selected_count_12m": count,
        "previous_avg_weight_12m": avg_weight,
        "previous_concentration_penalty": float(min(1.0, max(0.0, count / 12.0 + avg_weight))),
    }


def forward_audit_features(
    close: pd.DataFrame | None,
    ticker: str,
    execution_date: pd.Timestamp,
    selected_period_end_date: pd.Timestamp | None = None,
) -> dict[str, Any]:
    out = {col: np.nan for col in FORWARD_AUDIT_COLUMNS}
    if close is None or close.empty or ticker not in close.columns:
        return out
    series = pd.to_numeric(close[ticker], errors="coerce").dropna()
    if series.empty:
        return out
    idx = pd.DatetimeIndex(series.index)
    start_pos = idx.searchsorted(pd.Timestamp(execution_date), side="left")
    if start_pos >= len(idx):
        return out
    start_price = float(series.iloc[start_pos])
    if not start_price:
        return out
    for horizon in [21, 42, 63]:
        end_pos = start_pos + horizon
        if end_pos < len(series):
            out[f"audit_forward_{horizon}d_return"] = float(series.iloc[end_pos] / start_price - 1.0)
    end_pos = start_pos + 63 if start_pos + 63 < len(series) else len(series) - 1
    window = series.iloc[start_pos : end_pos + 1]
    returns = window.pct_change(fill_method=None).dropna()
    out["audit_forward_realized_vol"] = float(returns.std(ddof=0) * math.sqrt(252.0)) if len(returns) >= 5 else np.nan
    out["audit_forward_maxdd"] = max_drawdown(window)
    if selected_period_end_date is not None and pd.notna(selected_period_end_date):
        period_end = idx.searchsorted(pd.Timestamp(selected_period_end_date), side="left")
        if period_end < len(series) and period_end > start_pos:
            out["audit_forward_selected_period_return"] = float(series.iloc[period_end] / start_price - 1.0)
    return out


def trailing_return(series: pd.Series, window: int) -> float:
    if len(series) <= window:
        return np.nan
    start = float(series.iloc[-window - 1])
    end = float(series.iloc[-1])
    return float(end / start - 1.0) if start else np.nan


def max_drawdown(series: pd.Series) -> float:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty:
        return np.nan
    peak = clean.cummax()
    return float((clean / peak - 1.0).min())


def next_execution_date(ledger: pd.DataFrame, decision_date: pd.Timestamp) -> pd.Timestamp | None:
    if ledger.empty or "execution_date" not in ledger.columns or "decision_date" not in ledger.columns:
        return None
    local = ledger.copy()
    local["decision_date"] = pd.to_datetime(local["decision_date"], errors="coerce")
    local["execution_date"] = pd.to_datetime(local["execution_date"], errors="coerce")
    future = local.loc[local["decision_date"] > pd.Timestamp(decision_date)].sort_values("decision_date")
    if future.empty:
        return None
    return pd.Timestamp(future["execution_date"].iloc[0])


def asset_type_for_ticker(ticker: str) -> str:
    return "ETF" if ticker.upper() in ETF_TICKERS else "stock"


def order_audit_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return empty_audit_frame()
    for col in AUDIT_TRAIL_COLUMNS:
        if col not in df.columns:
            df[col] = np.nan
    return df.loc[:, AUDIT_TRAIL_COLUMNS + [c for c in df.columns if c not in AUDIT_TRAIL_COLUMNS]]


def empty_audit_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=AUDIT_TRAIL_COLUMNS)


def date_str(value: Any) -> str:
    return "" if pd.isna(value) else pd.Timestamp(value).date().isoformat()


def write_schema_markdown(path: Path, title_date: str) -> None:
    rows = schema_rows()
    text = f"""# US Stock Selection v8.2 Score/Rank Audit Schema {title_date}

This schema separates ex-ante selection fields from audit-only forward outcome fields. Any column with the `audit_forward_` prefix is strictly audit-only and must never be used to compute score, rank, selected_flag, or target weight.

## Field Schema

{rows.to_markdown(index=False)}
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
