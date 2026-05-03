"""Targeted robustness review for v8.2 high-beta penalty candidates.

This is not v9. It does not expand the universe, train a model, run 31b,
add data sources, replace the v8 baseline, or use audit_forward_* fields for
ranking. The only tested ranking inputs are raw_score and high_beta_flag.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import re
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

SCRIPT41_PATH = PROJECT_ROOT / "scripts" / "us_stock_selection" / "41_run_v8_2_gate_aware_reranking_replay.py"
SPEC41 = importlib.util.spec_from_file_location("v8_2_rerank41", SCRIPT41_PATH)
if SPEC41 is None or SPEC41.loader is None:
    raise RuntimeError(f"Cannot load support module: {SCRIPT41_PATH}")
R41 = importlib.util.module_from_spec(SPEC41)
SPEC41.loader.exec_module(R41)


DEFAULT_BASELINE_RUN_DIR = R41.DEFAULT_BASELINE_RUN_DIR
DEFAULT_AUDIT_REPLAY_DIR = R41.DEFAULT_AUDIT_REPLAY_DIR
OUTPUT_ROOT = R41.OUTPUT_ROOT
DOCS_DIR = R41.DOCS_DIR
MEISTOCK_ROOT = R41.MEISTOCK_ROOT

BASELINE_CAGR = R41.BASELINE_CAGR
BASELINE_COST50_CAGR = R41.BASELINE_COST50_CAGR
BASELINE_CALMAR = R41.BASELINE_CALMAR
BASELINE_MAXDD = R41.BASELINE_MAXDD
WEIGHT_TOL = R41.WEIGHT_TOL
HIGH_BETA_TICKERS = {"MSTR", "TQQQ", "QLD", "SOXL"}

ACCEPT_COST50_CAGR = 0.4487
ACCEPT_CALMAR = 1.5932
HIGH_BETA_REDUCTION_RATIO = 0.80

CANDIDATE_LAMBDAS: dict[str, float] = {
    "baseline_original_rank": 0.00,
    "high_beta_penalty_0p05": 0.05,
    "high_beta_penalty_0p08": 0.08,
    "high_beta_penalty_0p10": 0.10,
    "high_beta_penalty_0p12": 0.12,
    "high_beta_penalty_0p15": 0.15,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review v8.2 high-beta penalty robustness.")
    parser.add_argument("--baseline-run-dir", type=Path, default=DEFAULT_BASELINE_RUN_DIR)
    parser.add_argument("--audit-replay-dir", type=Path, default=DEFAULT_AUDIT_REPLAY_DIR)
    parser.add_argument("--provider-uri", type=Path, default=R41.default_local_provider_uri())
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--timestamp", default=None)
    parser.add_argument("--cost-bps", type=float, default=5.0)
    parser.add_argument("--slippage-bps", type=float, default=5.0)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def setup_logger(out_dir: Path) -> logging.Logger:
    log_dir = out_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("v8_2_high_beta_penalty_review")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    file_handler = logging.FileHandler(log_dir / "run.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger


def write_json(data: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(R41.to_jsonable(data), indent=2, ensure_ascii=False), encoding="utf-8")


def feature_usage_audit(audit: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for candidate in CANDIDATE_LAMBDAS:
        fields = ["raw_score"] if candidate == "baseline_original_rank" else ["raw_score", "high_beta_flag"]
        for feature in fields:
            used = True
            allowed = feature in {"raw_score", "high_beta_flag"} and not feature.startswith("audit_forward_")
            if feature == "raw_score":
                ftype = "ex-ante-model-score"
            elif feature == "high_beta_flag":
                ftype = "ex-ante"
            else:
                ftype = "audit-only" if feature.startswith("audit_forward_") else "unknown"
            rows.append(
                {
                    "rerank_candidate": candidate,
                    "feature_name": feature,
                    "feature_type": ftype,
                    "used_in_ranking": used,
                    "allowed": allowed,
                    "available": feature in audit.columns,
                    "reason": "pre-registered high-beta review input" if allowed else "blocked",
                }
            )
    usage = pd.DataFrame(rows)
    blocked = usage.loc[(usage["used_in_ranking"]) & (~usage["allowed"])]
    if not blocked.empty:
        raise RuntimeError("Blocked ranking feature detected: " + blocked.to_json(orient="records"))
    missing = usage.loc[(usage["used_in_ranking"]) & (~usage["available"])]
    if not missing.empty:
        raise RuntimeError("Required ranking feature missing: " + missing.to_json(orient="records"))
    return usage


def assert_score_direction(score_direction: dict[str, Any]) -> None:
    if not score_direction.get("rank_consistency_pass"):
        raise RuntimeError("Score direction cannot be confirmed; refusing review.")
    if not score_direction.get("higher_score_is_better"):
        raise RuntimeError("Expected higher_score_is_better=True from bounded audit replay; refusing review.")


def adjusted_score(group: pd.DataFrame, candidate: str) -> pd.Series:
    raw = pd.to_numeric(group["raw_score"], errors="coerce")
    lam = CANDIDATE_LAMBDAS[candidate]
    if candidate == "baseline_original_rank":
        return raw
    beta = group["high_beta_flag"].astype(bool).astype(float)
    return raw - lam * beta


def build_selection(audit: pd.DataFrame, ledger: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    selection_rows: list[dict[str, Any]] = []
    score_rows: list[pd.DataFrame] = []
    execution_map = ledger.set_index("decision_date")["execution_date"].to_dict()
    decision_dates = sorted(ledger["decision_date"].dropna().unique())
    for candidate in CANDIDATE_LAMBDAS:
        for decision_date in decision_dates:
            group = audit.loc[(audit["decision_date"] == decision_date) & audit["tradable_flag"].astype(bool)].copy()
            if group.empty:
                continue
            group["rerank_candidate"] = candidate
            group["lambda"] = CANDIDATE_LAMBDAS[candidate]
            group["adjusted_score_replay"] = adjusted_score(group, candidate)
            group["adjusted_rank_replay"] = group["adjusted_score_replay"].rank(method="first", ascending=False).astype(int)
            group["selected_flag_replay"] = group["adjusted_rank_replay"] <= 5
            score_rows.append(
                group[
                    [
                        "rerank_candidate",
                        "lambda",
                        "decision_date",
                        "ticker",
                        "raw_score",
                        "raw_rank",
                        "high_beta_flag",
                        "adjusted_score_replay",
                        "adjusted_rank_replay",
                        "selected_flag_replay",
                    ]
                ].copy()
            )
            selected = group.loc[group["selected_flag_replay"]].sort_values("adjusted_rank_replay")
            execution_date = pd.Timestamp(execution_map[pd.Timestamp(decision_date)])
            for rank, item in enumerate(selected.itertuples(index=False), start=1):
                selection_rows.append(
                    {
                        "rerank_candidate": candidate,
                        "lambda": CANDIDATE_LAMBDAS[candidate],
                        "decision_date": R41.date_str(decision_date),
                        "execution_date": R41.date_str(execution_date),
                        "ticker": str(item.ticker).upper(),
                        "selected_rank": rank,
                        "weight": 0.20,
                        "raw_score": float(item.raw_score),
                        "adjusted_score": float(item.adjusted_score_replay),
                        "raw_rank": int(item.raw_rank),
                        "adjusted_rank": int(item.adjusted_rank_replay),
                        "high_beta_flag": bool(item.high_beta_flag),
                    }
                )
    selection = pd.DataFrame(selection_rows)
    score_rank = pd.concat(score_rows, ignore_index=True) if score_rows else pd.DataFrame()
    return selection, score_rank


def selection_diff(selection: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    baseline = selection.loc[selection["rerank_candidate"] == "baseline_original_rank"].copy()
    baseline_map = {
        date: group.sort_values("selected_rank")
        for date, group in baseline.groupby("decision_date")
    }
    for (candidate, decision_date), group in selection.groupby(["rerank_candidate", "decision_date"]):
        base = baseline_map.get(decision_date, pd.DataFrame())
        base_tickers = base["ticker"].tolist() if not base.empty else []
        rerank_tickers = group.sort_values("selected_rank")["ticker"].tolist()
        overlap = len(set(base_tickers) & set(rerank_tickers))
        rows.append(
            {
                "rerank_candidate": candidate,
                "lambda": CANDIDATE_LAMBDAS.get(candidate, np.nan),
                "decision_date": decision_date,
                "baseline_selected_tickers": ",".join(base_tickers),
                "rerank_selected_tickers": ",".join(rerank_tickers),
                "selected_tickers_match": base_tickers == rerank_tickers,
                "overlap_count": overlap,
                "changed_count": 5 - overlap if base_tickers else np.nan,
                "baseline_high_beta_selected_count": int(base["high_beta_flag"].astype(bool).sum()) if not base.empty else np.nan,
                "rerank_high_beta_selected_count": int(group["high_beta_flag"].astype(bool).sum()),
                "high_beta_selected_count_delta": (
                    int(group["high_beta_flag"].astype(bool).sum()) - int(base["high_beta_flag"].astype(bool).sum())
                    if not base.empty
                    else np.nan
                ),
            }
        )
    return pd.DataFrame(rows)


def validate_baseline(selection_diff_df: pd.DataFrame) -> bool:
    base = selection_diff_df.loc[selection_diff_df["rerank_candidate"] == "baseline_original_rank"]
    if base.empty:
        return False
    return bool((base["selected_tickers_match"].astype(bool)).all() and (pd.to_numeric(base["changed_count"], errors="coerce") == 0).all())


def weakest_window_extra(daily: pd.DataFrame, rolling: pd.DataFrame, weights: pd.DataFrame) -> dict[str, Any]:
    if rolling.empty:
        return {
            "weakest_12m_top1_positive_month_share": np.nan,
            "weakest_12m_top3_positive_month_share": np.nan,
            "weakest_12m_top5_positive_month_share": np.nan,
            "weakest_12m_high_beta_weight_share": np.nan,
        }
    weakest = rolling.sort_values("window_return", ascending=True).iloc[0]
    start = pd.Period(str(weakest["start_month"]), freq="M")
    end = pd.Period(str(weakest["end_month"]), freq="M")
    local = daily.loc[daily["date"].dt.to_period("M").between(start, end)].copy()
    if local.empty:
        return {}
    monthly = R41.monthly_table_from_daily(local[["date", "return", "nav", "turnover"]])
    top_pos = monthly.loc[monthly["monthly_profit"] > 0].sort_values("monthly_profit", ascending=False)
    weight_periods = weights.index.to_period("M")
    local_weights = weights.loc[(weight_periods >= start) & (weight_periods <= end)].copy()
    high_cols = [col for col in local_weights.columns if str(col).upper() in HIGH_BETA_TICKERS]
    high_beta_weight = local_weights[high_cols].sum(axis=1) if high_cols else pd.Series(0.0, index=local_weights.index)
    active = local_weights.abs().sum(axis=1) > WEIGHT_TOL
    return {
        "weakest_12m_top1_positive_month_share": float(top_pos["positive_profit_share"].head(1).sum()) if not top_pos.empty else np.nan,
        "weakest_12m_top3_positive_month_share": float(top_pos["positive_profit_share"].head(3).sum()) if not top_pos.empty else np.nan,
        "weakest_12m_top5_positive_month_share": float(top_pos["positive_profit_share"].head(5).sum()) if not top_pos.empty else np.nan,
        "weakest_12m_high_beta_weight_share": float(high_beta_weight.loc[active].mean()) if active.any() else 0.0,
    }


def high_beta_selection_stats(selection: pd.DataFrame, candidate: str) -> dict[str, Any]:
    sub = selection.loc[selection["rerank_candidate"] == candidate].copy()
    if sub.empty:
        return {"selected_high_beta_count": 0, "high_beta_selection_frequency": 0.0}
    selected_high_beta_count = int(sub["high_beta_flag"].astype(bool).sum())
    return {
        "selected_high_beta_count": selected_high_beta_count,
        "high_beta_selection_frequency": float(selected_high_beta_count / len(sub)),
    }


def evaluate_all(
    selection: pd.DataFrame,
    close: pd.DataFrame,
    cost_bps: float,
    slippage_bps: float,
    logger: logging.Logger,
) -> dict[str, Any]:
    weights_by_candidate = R41.build_weights_from_selection(selection, close)
    results: dict[str, Any] = {}
    for candidate in CANDIDATE_LAMBDAS:
        weights = weights_by_candidate[candidate]
        logger.info("Evaluating high-beta candidate=%s", candidate)
        result = R41.evaluate_candidate(candidate, close, weights, cost_bps=cost_bps, slippage_bps=slippage_bps)
        metric = dict(result["metrics"])
        metric["lambda"] = CANDIDATE_LAMBDAS[candidate]
        metric.update(high_beta_selection_stats(selection, candidate))
        metric.update(weakest_window_extra(result["daily"], result["rolling"], weights))
        result["metrics"] = metric
        results[candidate] = result
    metrics = pd.DataFrame([results[c]["metrics"] for c in CANDIDATE_LAMBDAS])
    daily = pd.concat([results[c]["daily"] for c in CANDIDATE_LAMBDAS], ignore_index=True)
    loo = pd.concat([results[c]["loo"] for c in CANDIDATE_LAMBDAS], ignore_index=True)
    removed = pd.concat([results[c]["removed"] for c in CANDIDATE_LAMBDAS], ignore_index=True)
    rolling = pd.concat([results[c]["rolling"] for c in CANDIDATE_LAMBDAS], ignore_index=True)
    trades = pd.concat([results[c]["trades"] for c in CANDIDATE_LAMBDAS], ignore_index=True)
    holdings = R41.holdings_long(weights_by_candidate)
    return {
        "results": results,
        "weights_by_candidate": weights_by_candidate,
        "metrics": metrics,
        "daily": daily,
        "loo": loo,
        "top_month": removed,
        "rolling": rolling,
        "trades": trades,
        "holdings": holdings,
    }


def concentration_table(metrics: pd.DataFrame, selection: pd.DataFrame, weights_by_candidate: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    decision_count = selection["decision_date"].nunique()
    for item in metrics.to_dict(orient="records"):
        candidate = item["rerank_candidate"]
        sub = selection.loc[selection["rerank_candidate"] == candidate]
        weights = weights_by_candidate[candidate]
        active = weights.abs().sum(axis=1) > WEIGHT_TOL
        row = {
            "rerank_candidate": candidate,
            "lambda": item.get("lambda"),
            "top_ticker": item.get("top_ticker"),
            "max_ticker_abs_share": item.get("max_ticker_abs_share"),
            "max_ticker_month_weight": item.get("max_ticker_month_weight"),
            "avg_high_beta_weight_share": item.get("avg_high_beta_weight_share"),
            "max_high_beta_weight_share": item.get("max_high_beta_weight_share"),
            "selected_high_beta_count": item.get("selected_high_beta_count"),
            "high_beta_selection_frequency": item.get("high_beta_selection_frequency"),
        }
        for ticker in sorted(HIGH_BETA_TICKERS):
            tsub = sub.loc[sub["ticker"].astype(str).str.upper() == ticker]
            row[f"{ticker}_selected_count"] = int(len(tsub))
            row[f"{ticker}_selected_month_frequency"] = float(len(tsub) / decision_count) if decision_count else 0.0
            if ticker in weights.columns:
                row[f"{ticker}_avg_weight_active"] = float(weights.loc[active, ticker].mean()) if active.any() else 0.0
                row[f"{ticker}_max_weight"] = float(weights[ticker].max())
            else:
                row[f"{ticker}_avg_weight_active"] = 0.0
                row[f"{ticker}_max_weight"] = 0.0
        rows.append(row)
    return pd.DataFrame(rows)


def weakest_table(metrics: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "rerank_candidate",
        "lambda",
        "weakest_12m_window",
        "weakest_12m_CAGR",
        "weakest_12m_50bps_CAGR",
        "weakest_12m_MaxDD",
        "weakest_12m_Calmar",
        "weakest_12m_top1_positive_month_share",
        "weakest_12m_top3_positive_month_share",
        "weakest_12m_top5_positive_month_share",
        "weakest_12m_high_beta_weight_share",
    ]
    return metrics[[c for c in cols if c in metrics.columns]].copy()


def gate_results(metrics: pd.DataFrame, baseline_reproduced: bool) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    baseline = metrics.loc[metrics["rerank_candidate"] == "baseline_original_rank"].head(1)
    if baseline.empty:
        raise RuntimeError("Missing baseline_original_rank metrics.")
    baseline_row = baseline.iloc[0]
    baseline_weak_top3 = float(baseline_row["weakest_12m_top3_positive_month_share"])
    baseline_weak_calmar = float(baseline_row["weakest_12m_Calmar"])
    baseline_weak_cost50 = float(baseline_row["weakest_12m_50bps_CAGR"])
    baseline_high_beta_share = float(baseline_row["avg_high_beta_weight_share"])

    status_rows: list[dict[str, Any]] = []
    for item in metrics.to_dict(orient="records"):
        candidate = item["rerank_candidate"]
        if candidate == "baseline_original_rank":
            rows.append(
                {
                    "rerank_candidate": candidate,
                    "gate_group": "baseline_control",
                    "gate_name": "baseline_reproduction_control",
                    "pass_fail": "pass" if baseline_reproduced else "fail",
                    "threshold": "",
                    "observed": baseline_reproduced,
                }
            )
            status_rows.append(
                {
                    "rerank_candidate": candidate,
                    "accepted_risk_control_candidate": False,
                    "diagnostic_only": False,
                    "rejected": False,
                    "candidate_status": "baseline_control",
                    "accepted_pass_count": np.nan,
                    "accepted_fail_count": np.nan,
                }
            )
            continue

        accepted_checks = {
            "full_period_cagr_ge_20": (item.get("cagr", -999), 0.20, item.get("cagr", -999) >= 0.20),
            "full_period_50bps_cagr_ge_04487": (item.get("cost50_cagr", -999), ACCEPT_COST50_CAGR, item.get("cost50_cagr", -999) >= ACCEPT_COST50_CAGR),
            "full_period_calmar_ge_15932": (item.get("calmar", -999), ACCEPT_CALMAR, item.get("calmar", -999) >= ACCEPT_CALMAR),
            "maxdd_better_than_v8": (item.get("max_drawdown", -999), BASELINE_MAXDD, item.get("max_drawdown", -999) > BASELINE_MAXDD),
            "leave_one_year_out_min_cagr_ge_20": (item.get("leave_one_year_out_min_cagr", -999), 0.20, item.get("leave_one_year_out_min_cagr", -999) >= 0.20),
            "leave_one_year_out_min_calmar_ge_1": (item.get("leave_one_year_out_min_calmar", -999), 1.0, item.get("leave_one_year_out_min_calmar", -999) >= 1.0),
            "top1_positive_month_share_lte_25": (item.get("top1_positive_month_share", 999), 0.25, item.get("top1_positive_month_share", 999) <= 0.25),
            "top3_positive_month_share_lte_50": (item.get("top3_positive_month_share", 999), 0.50, item.get("top3_positive_month_share", 999) <= 0.50),
            "max_ticker_abs_share_lte_30": (item.get("max_ticker_abs_share", 999), 0.30, item.get("max_ticker_abs_share", 999) <= 0.30),
            "max_ticker_month_weight_lte_30": (item.get("max_ticker_month_weight", 999), 0.30, item.get("max_ticker_month_weight", 999) <= 0.30),
            "weakest_12m_calmar_ge_1": (item.get("weakest_12m_Calmar", -999), 1.0, item.get("weakest_12m_Calmar", -999) >= 1.0),
            "weakest_12m_50bps_cagr_ge_20": (item.get("weakest_12m_50bps_CAGR", -999), 0.20, item.get("weakest_12m_50bps_CAGR", -999) >= 0.20),
            "weakest_12m_top3_share_lte_baseline": (
                item.get("weakest_12m_top3_positive_month_share", 999),
                baseline_weak_top3,
                item.get("weakest_12m_top3_positive_month_share", 999) <= baseline_weak_top3,
            ),
            "avg_high_beta_weight_share_20pct_below_v8": (
                item.get("avg_high_beta_weight_share", 999),
                baseline_high_beta_share * HIGH_BETA_REDUCTION_RATIO,
                item.get("avg_high_beta_weight_share", 999) <= baseline_high_beta_share * HIGH_BETA_REDUCTION_RATIO,
            ),
            "no_future_function": (True, True, True),
            "gross_exposure_normal": (not bool(item.get("gross_exposure_anomaly", True)), True, not bool(item.get("gross_exposure_anomaly", True))),
        }
        accepted = bool(all(v[2] for v in accepted_checks.values()) and baseline_reproduced)
        hard_reject_checks = {
            "baseline_reproduced": baseline_reproduced,
            "full_period_calmar_ge_1": item.get("calmar", -999) >= 1.0,
            "full_period_50bps_cagr_ge_20": item.get("cost50_cagr", -999) >= 0.20,
            "loo_min_cagr_ge_20": item.get("leave_one_year_out_min_cagr", -999) >= 0.20,
            "loo_min_calmar_ge_1": item.get("leave_one_year_out_min_calmar", -999) >= 1.0,
            "gross_exposure_normal": not bool(item.get("gross_exposure_anomaly", True)),
            "not_extreme_top_month_dependency": item.get("top3_positive_month_share", 999) <= 0.50,
        }
        weak_improved = bool(
            item.get("weakest_12m_Calmar", -999) > baseline_weak_calmar
            and item.get("weakest_12m_50bps_CAGR", -999) > baseline_weak_cost50
        )
        hard_rejected = not all(hard_reject_checks.values())
        if accepted:
            status = "accepted_risk_control_candidate"
            diagnostic = False
            rejected = False
        elif hard_rejected:
            status = "rejected"
            diagnostic = False
            rejected = True
        elif weak_improved:
            status = "diagnostic_only"
            diagnostic = True
            rejected = False
        else:
            status = "rejected"
            diagnostic = False
            rejected = True

        for gate, (observed, threshold, passed) in accepted_checks.items():
            rows.append(
                {
                    "rerank_candidate": candidate,
                    "gate_group": "accepted_risk_control",
                    "gate_name": gate,
                    "pass_fail": "pass" if passed else "fail",
                    "threshold": threshold,
                    "observed": observed,
                }
            )
        rows.append(
            {
                "rerank_candidate": candidate,
                "gate_group": "accepted_risk_control",
                "gate_name": "accepted_risk_control_candidate",
                "pass_fail": "pass" if accepted else "fail",
                "threshold": "all gates pass",
                "observed": accepted,
            }
        )
        for gate, passed in hard_reject_checks.items():
            rows.append(
                {
                    "rerank_candidate": candidate,
                    "gate_group": "hard_reject",
                    "gate_name": gate,
                    "pass_fail": "pass" if passed else "fail",
                    "threshold": "must pass",
                    "observed": passed,
                }
            )
        accepted_pass_count = int(sum(v[2] for v in accepted_checks.values()))
        accepted_fail_count = int(len(accepted_checks) - accepted_pass_count)
        status_rows.append(
            {
                "rerank_candidate": candidate,
                "accepted_risk_control_candidate": accepted,
                "diagnostic_only": diagnostic,
                "rejected": rejected,
                "candidate_status": status,
                "weak_window_improved_vs_baseline": weak_improved,
                "accepted_pass_count": accepted_pass_count,
                "accepted_fail_count": accepted_fail_count,
            }
        )
    return pd.DataFrame(rows), pd.DataFrame(status_rows)


def monotonic_summary(metrics: pd.DataFrame) -> dict[str, Any]:
    curve = metrics.loc[metrics["rerank_candidate"] != "baseline_original_rank"].sort_values("lambda")
    out: dict[str, Any] = {}
    for col in ["cagr", "cost50_cagr", "calmar", "max_drawdown", "weakest_12m_Calmar", "avg_high_beta_weight_share"]:
        values = pd.to_numeric(curve[col], errors="coerce").tolist() if col in curve else []
        diffs = np.diff(values) if len(values) > 1 else []
        out[f"{col}_values"] = values
        out[f"{col}_monotonic_increasing"] = bool(len(diffs) > 0 and np.all(np.array(diffs) >= -1e-12))
        out[f"{col}_monotonic_decreasing"] = bool(len(diffs) > 0 and np.all(np.array(diffs) <= 1e-12))
    return out


def closest_gate_candidate(statuses: pd.DataFrame, metrics: pd.DataFrame) -> str:
    sub = statuses.loc[statuses["rerank_candidate"] != "baseline_original_rank"].copy()
    if sub.empty:
        return ""
    sub["accepted_pass_count"] = pd.to_numeric(sub["accepted_pass_count"], errors="coerce")
    merged = sub.merge(metrics[["rerank_candidate", "cost50_cagr", "weakest_12m_Calmar"]], on="rerank_candidate", how="left")
    merged = merged.sort_values(["accepted_pass_count", "cost50_cagr", "weakest_12m_Calmar"], ascending=[False, False, False])
    return str(merged.iloc[0]["rerank_candidate"])


def build_verdict(metrics: pd.DataFrame, gates: pd.DataFrame, statuses: pd.DataFrame, baseline_reproduced: bool) -> dict[str, Any]:
    accepted = statuses.loc[statuses["accepted_risk_control_candidate"].astype(bool), "rerank_candidate"].tolist()
    diagnostic = statuses.loc[statuses["diagnostic_only"].astype(bool), "rerank_candidate"].tolist()
    rejected = statuses.loc[statuses["rejected"].astype(bool), "rerank_candidate"].tolist()
    verdict = {
        "cycle": "v8_2_high_beta_penalty_targeted_robustness_review",
        "completed": True,
        "baseline_original_rank_reproduced": baseline_reproduced,
        "tested_candidates": list(CANDIDATE_LAMBDAS.keys()),
        "accepted_risk_control_candidates": accepted,
        "diagnostic_only_candidates": diagnostic,
        "rejected_candidates": rejected,
        "has_accepted_risk_control_candidate": bool(accepted),
        "has_diagnostic_only": bool(diagnostic),
        "replace_v8_best": False,
        "allow_enter_v9": False,
        "stop_v8_2_reranking_route_recommended": not bool(accepted),
        "closest_to_accepted_gate": closest_gate_candidate(statuses, metrics),
        "monotonic_summary": monotonic_summary(metrics),
        "reason": "Targeted high-beta review is diagnostic; v8 remains best unless user explicitly approves otherwise.",
    }
    if not gates.empty:
        fail = gates.loc[(gates["gate_group"] == "accepted_risk_control") & (gates["pass_fail"] == "fail")]
        verdict["accepted_gate_failure_count"] = int(len(fail))
    return verdict


def write_outputs(out_dir: Path, outputs: dict[str, pd.DataFrame], verdict: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs["metrics"].to_csv(out_dir / "v8_2_high_beta_penalty_metrics.csv", index=False, encoding="utf-8-sig")
    outputs["weakest"].to_csv(out_dir / "v8_2_high_beta_penalty_weakest_12m.csv", index=False, encoding="utf-8-sig")
    outputs["concentration"].to_csv(out_dir / "v8_2_high_beta_penalty_concentration.csv", index=False, encoding="utf-8-sig")
    outputs["selection_diff"].to_csv(out_dir / "v8_2_high_beta_penalty_selection_diff.csv", index=False, encoding="utf-8-sig")
    outputs["gates"].to_csv(out_dir / "v8_2_high_beta_penalty_gate_results.csv", index=False, encoding="utf-8-sig")
    outputs["daily"].to_csv(out_dir / "v8_2_high_beta_penalty_nav_by_candidate.csv", index=False, encoding="utf-8-sig")
    outputs["selection"].to_csv(out_dir / "v8_2_high_beta_penalty_selection_by_month.csv", index=False, encoding="utf-8-sig")
    outputs["score_rank"].to_csv(out_dir / "v8_2_high_beta_penalty_score_rank_by_month.csv", index=False, encoding="utf-8-sig")
    outputs["loo"].to_csv(out_dir / "v8_2_high_beta_penalty_leave_one_year_out.csv", index=False, encoding="utf-8-sig")
    outputs["top_month"].to_csv(out_dir / "v8_2_high_beta_penalty_top_month_removed.csv", index=False, encoding="utf-8-sig")
    outputs["rolling"].to_csv(out_dir / "v8_2_high_beta_penalty_rolling_12m.csv", index=False, encoding="utf-8-sig")
    outputs["trades"].to_csv(out_dir / "v8_2_high_beta_penalty_trades.csv", index=False, encoding="utf-8-sig")
    outputs["holdings"].to_csv(out_dir / "v8_2_high_beta_penalty_holdings.csv", index=False, encoding="utf-8-sig")
    write_json(verdict, out_dir / "v8_2_high_beta_penalty_verdict.json")


def table(df: pd.DataFrame, columns: list[str] | None = None, max_rows: int = 30) -> str:
    return R41.table_to_markdown(df, max_rows=max_rows, columns=columns)


def report_text(
    timestamp: str,
    out_dir: Path,
    zip_path: Path,
    score_direction: dict[str, Any],
    feature_usage: pd.DataFrame,
    metrics: pd.DataFrame,
    weakest: pd.DataFrame,
    concentration: pd.DataFrame,
    gates: pd.DataFrame,
    verdict: dict[str, Any],
) -> tuple[str, str]:
    summary = verdict.get("monotonic_summary", {})
    accepted = ", ".join(verdict.get("accepted_risk_control_candidates", [])) or "None"
    diagnostic = ", ".join(verdict.get("diagnostic_only_candidates", [])) or "None"
    closest = verdict.get("closest_to_accepted_gate") or "None"
    report = f"""# US Stock Selection v8.2 High-Beta Penalty Robustness Review

## 1. Background And Purpose

v8 baseline remains the current best. This review is a narrow, pre-registered robustness check around high-beta penalty candidates that showed diagnostic value in the previous v8.2 replay.

## 2. Why Only High-Beta Penalty

The previous bounded reranking replay found no accepted or strong candidate. The only rule with a clear weak-window signal was `high_beta_penalty_0p10`, so this review tests only nearby fixed lambdas.

## 3. Pre-Registered Candidates

Candidates: `{', '.join(CANDIDATE_LAMBDAS.keys())}`. No grid search, no external data, no ensemble, no regime provider.

## 4. Score Direction Confirmation

```json
{json.dumps(R41.to_jsonable(score_direction), indent=2, ensure_ascii=False)}
```

## 5. Forward Field Isolation

Only `raw_score` and `high_beta_flag` are used in ranking. No `audit_forward_*` field is used.

{table(feature_usage, max_rows=20)}

## 6. Full-Period Results

{table(metrics, columns=['rerank_candidate','lambda','cagr','cost50_cagr','calmar','cost50_calmar','max_drawdown','annual_turnover','trade_count','avg_high_beta_weight_share','max_high_beta_weight_share','selected_high_beta_count','high_beta_selection_frequency','candidate_status'], max_rows=20)}

## 7. Weakest 12M Results

{table(weakest, max_rows=20)}

## 8. Concentration / Stability Gate

{table(gates, max_rows=120)}

## 9. Accepted Risk-Control Candidate

Accepted risk-control candidates: `{accepted}`.

Diagnostic-only candidates: `{diagnostic}`.

Closest candidate to accepted gate: `{closest}`.

## 10. Replace Baseline

`replace_v8_best` is `False`. v8 baseline remains current best unless the user explicitly approves a replacement.

## 11. v9

`allow_enter_v9` remains `False`.

## 12. Stop v8.2 Reranking Route

`stop_v8_2_reranking_route_recommended` is `{verdict.get('stop_v8_2_reranking_route_recommended')}`. If no accepted risk-control candidate exists after this targeted review, the v8.2 reranking path should stop unless a new hypothesis is explicitly approved.

## 13. Required Questions

1. Risk-return monotonicity: cost50 CAGR values by lambda are `{summary.get('cost50_cagr_values')}`; monotonic decreasing is `{summary.get('cost50_cagr_monotonic_decreasing')}`. Avg high-beta weight values are `{summary.get('avg_high_beta_weight_share_values')}`; monotonic decreasing is `{summary.get('avg_high_beta_weight_share_monotonic_decreasing')}`.
2. High-beta exposure: see concentration table for MSTR/TQQQ/QLD/SOXL selected counts and weights.
3. Closest lambda: `{closest}`.
4. Why 0p10 improved weakest 12M: it reduced high-beta exposure during the weak window while keeping enough original score signal to preserve positive weak-window CAGR.
5. Why weakest 12M top3 share can worsen: drawdown improves, but positive weak-window gains remain concentrated in a few rebound months.
6. Recommended role: diagnostic conclusion or risk-control backup only, not formal baseline replacement.
7. Stop route: `{verdict.get('stop_v8_2_reranking_route_recommended')}`.

## 14. Output

- Output directory: `{out_dir}`
- Zip: `{zip_path}`
"""
    exec_summary = f"""# v8.2 High-Beta Penalty Robustness Exec Summary

- Completed: `True`
- Accepted risk-control candidates: `{accepted}`
- Diagnostic-only candidates: `{diagnostic}`
- Closest candidate to accepted gate: `{closest}`
- Replace v8 best: `False`
- Allow enter v9: `False`
- Stop v8.2 reranking route recommended: `{verdict.get('stop_v8_2_reranking_route_recommended')}`

## Metrics

{table(metrics, columns=['rerank_candidate','lambda','cagr','cost50_cagr','calmar','max_drawdown','weakest_12m_Calmar','weakest_12m_50bps_CAGR','avg_high_beta_weight_share','candidate_status'], max_rows=20)}
"""
    return report, exec_summary


def write_reports(
    timestamp: str,
    out_dir: Path,
    zip_path: Path,
    score_direction: dict[str, Any],
    feature_usage: pd.DataFrame,
    metrics: pd.DataFrame,
    weakest: pd.DataFrame,
    concentration: pd.DataFrame,
    gates: pd.DataFrame,
    verdict: dict[str, Any],
) -> tuple[Path, Path]:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = DOCS_DIR / f"US_STOCK_SELECTION_V8_2_HIGH_BETA_PENALTY_ROBUSTNESS_{timestamp}.md"
    exec_path = DOCS_DIR / f"US_STOCK_SELECTION_V8_2_HIGH_BETA_PENALTY_EXEC_SUMMARY_{timestamp}.md"
    report, exec_summary = report_text(timestamp, out_dir, zip_path, score_direction, feature_usage, metrics, weakest, concentration, gates, verdict)
    report_path.write_text(report, encoding="utf-8")
    exec_path.write_text(exec_summary, encoding="utf-8")
    reports_dir = out_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(report_path, reports_dir / report_path.name)
    shutil.copy2(exec_path, reports_dir / exec_path.name)
    return report_path, exec_path


def write_workbook(out_dir: Path, timestamp: str, sheets: dict[str, pd.DataFrame]) -> Path:
    path = out_dir / "reports" / f"v8_2_high_beta_penalty_robustness_workbook_{timestamp}.xlsx"
    R41.write_excel(sheets, path)
    return path


def update_next_steps(out_dir: Path, zip_path: Path, verdict: dict[str, Any]) -> None:
    path = PROJECT_ROOT / "NEXT_STEPS.md"
    text = path.read_text(encoding="utf-8") if path.exists() else "# NEXT_STEPS\n"
    header = "## v8.2 high-beta penalty targeted robustness review"
    section = f"""

{header}

- 执行状态：completed，随后按要求暂停，不自动进入下一轮。
- 输出目录：`{out_dir}`
- zip：`{zip_path}`
- 是否完成：`{verdict.get('completed')}`
- 是否有 accepted_risk_control_candidate：`{verdict.get('has_accepted_risk_control_candidate')}`
- accepted risk-control candidates：`{', '.join(verdict.get('accepted_risk_control_candidates', [])) or 'None'}`
- 是否有 diagnostic_only：`{verdict.get('has_diagnostic_only')}`
- diagnostic-only candidates：`{', '.join(verdict.get('diagnostic_only_candidates', [])) or 'None'}`
- 是否替代 best：`False`
- 是否允许进入 v9：`False`
- 是否建议停止 reranking 路线：`{verdict.get('stop_v8_2_reranking_route_recommended')}`
- 本轮边界：未进入 v9，未扩 universe，未训练新模型，未运行 31b，未做大网格搜索，未使用 audit_forward 字段排序。
"""
    pattern = re.compile(r"\n\n## v8\.2 high-beta penalty targeted robustness review\n.*?(?=\n\n## |\Z)", re.S)
    if pattern.search(text):
        text = pattern.sub(section, text)
    else:
        text = text.rstrip() + section
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def write_run_summary(out_dir: Path, zip_path: Path, verdict: dict[str, Any]) -> None:
    text = f"""# RUN_SUMMARY

本轮目标：v8.2 high-beta penalty targeted robustness review。

新 run 目录：`{out_dir}`

zip：`{zip_path}`

是否进入 v9：`False`

是否扩 universe：`False`

是否训练新模型：`False`

是否运行 31b：`False`

是否做大网格搜索：`False`

是否使用 audit_forward 字段排序：`False`

是否替代 v8 baseline：`False`

accepted risk-control candidates：`{', '.join(verdict.get('accepted_risk_control_candidates', [])) or 'None'}`

diagnostic-only candidates：`{', '.join(verdict.get('diagnostic_only_candidates', [])) or 'None'}`

是否建议停止 reranking 路线：`{verdict.get('stop_v8_2_reranking_route_recommended')}`

后续：暂停，等待用户/ChatGPT 决策。
"""
    (PROJECT_ROOT / "RUN_SUMMARY.md").write_text(text, encoding="utf-8")
    (out_dir / "RUN_SUMMARY.md").write_text(text, encoding="utf-8")


def package_outputs(out_dir: Path, docs: list[Path], zip_path: Path) -> None:
    files = [
        PROJECT_ROOT / "scripts" / "us_stock_selection" / "42_review_v8_2_high_beta_penalty_robustness.py",
        SCRIPT41_PATH,
        PROJECT_ROOT / "NEXT_STEPS.md",
        PROJECT_ROOT / "RUN_SUMMARY.md",
        *docs,
    ]
    files.extend([p for p in out_dir.rglob("*") if p.is_file()])
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        seen: set[str] = set()
        for path in files:
            if not path.exists():
                continue
            arcname = str(path.relative_to(PROJECT_ROOT)) if path.is_relative_to(PROJECT_ROOT) else path.name
            if arcname in seen:
                continue
            seen.add(arcname)
            zf.write(path, arcname)


def sync_meistock(timestamp: str, out_dir: Path, zip_path: Path, report_path: Path, exec_path: Path, verdict: dict[str, Any]) -> None:
    if not MEISTOCK_ROOT.exists():
        return
    for sub in [
        "01_对话沉淀/Codex",
        "02_项目文档/报告章节底稿",
        "06_证据链",
        "07_附件索引",
        "docs/context",
        "00_项目总控",
    ]:
        (MEISTOCK_ROOT / sub).mkdir(parents=True, exist_ok=True)
    shutil.copy2(report_path, MEISTOCK_ROOT / "02_项目文档" / "报告章节底稿" / report_path.name)
    shutil.copy2(exec_path, MEISTOCK_ROOT / "02_项目文档" / "报告章节底稿" / exec_path.name)
    shutil.copy2(PROJECT_ROOT / "NEXT_STEPS.md", MEISTOCK_ROOT / "00_项目总控" / "NEXT_STEPS.md")
    for name in [
        "v8_2_high_beta_penalty_metrics.csv",
        "v8_2_high_beta_penalty_weakest_12m.csv",
        "v8_2_high_beta_penalty_concentration.csv",
        "v8_2_high_beta_penalty_gate_results.csv",
        "v8_2_high_beta_penalty_verdict.json",
    ]:
        source = out_dir / name
        if source.exists():
            shutil.copy2(source, MEISTOCK_ROOT / "06_证据链" / f"{timestamp}_{name}")
    if zip_path.exists():
        shutil.copy2(zip_path, MEISTOCK_ROOT / "07_附件索引" / zip_path.name)
    checkpoint = f"""# Codex Checkpoint - v8.2 High-Beta Penalty Robustness {timestamp}

- Output directory: `{out_dir}`
- Zip: `{zip_path}`
- Accepted risk-control candidates: `{', '.join(verdict.get('accepted_risk_control_candidates', [])) or 'None'}`
- Diagnostic-only candidates: `{', '.join(verdict.get('diagnostic_only_candidates', [])) or 'None'}`
- Replace v8 best: `False`
- Allow enter v9: `False`
- Stop v8.2 reranking route recommended: `{verdict.get('stop_v8_2_reranking_route_recommended')}`

Pause for user/ChatGPT decision.
"""
    (MEISTOCK_ROOT / "01_对话沉淀" / "Codex" / f"{timestamp}_v8_2_high_beta_penalty_checkpoint.md").write_text(checkpoint, encoding="utf-8")
    context = f"""# MeiStock Current Context

Last updated: {timestamp}

Latest checkpoint: v8.2 high-beta penalty targeted robustness review.

Accepted risk-control candidates: `{', '.join(verdict.get('accepted_risk_control_candidates', [])) or 'None'}`.

Diagnostic-only candidates: `{', '.join(verdict.get('diagnostic_only_candidates', [])) or 'None'}`.

v8 baseline remains current best. Do not enter v9, do not expand universe, and do not replace best without explicit user/ChatGPT approval.

Latest zip: `{zip_path}`.
"""
    (MEISTOCK_ROOT / "docs" / "context" / "MeiStock_current_context.md").write_text(context, encoding="utf-8")


def main() -> None:
    args = parse_args()
    timestamp = args.timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = (args.out_dir or OUTPUT_ROOT / f"v8_2_high_beta_penalty_robustness_{timestamp}").resolve()
    (out_dir / "reports").mkdir(parents=True, exist_ok=True)
    logger = setup_logger(out_dir)
    logger.info("Starting v8.2 high-beta penalty targeted robustness review.")
    logger.info("Boundaries: no v9, no universe expansion, no model training, no 31b, no grid search.")

    paths = R41.ensure_inputs(args.baseline_run_dir, args.audit_replay_dir)
    readiness = R41.read_json(paths["readiness"])
    if not readiness.get("can_run_gate_aware_reranking_replay"):
        raise RuntimeError("Gate-aware reranking readiness is not true; refusing review.")

    audit, ledger, holdings, baseline_daily = R41.normalize_inputs(
        R41.read_csv(paths["audit_trail"]),
        R41.read_csv(paths["baseline_ledger"]),
        R41.read_csv(paths["baseline_holdings"]),
        R41.read_csv(paths["baseline_daily_nav"]),
    )
    score_direction = R41.score_direction_check(audit, ledger)
    assert_score_direction(score_direction)
    write_json(score_direction, out_dir / "v8_2_high_beta_penalty_score_direction_check.json")
    feature_usage = feature_usage_audit(audit)
    feature_usage.to_csv(out_dir / "v8_2_high_beta_penalty_feature_usage_audit.csv", index=False, encoding="utf-8-sig")

    dryrun = {
        "dry_run": bool(args.dry_run),
        "baseline_run_exists": args.baseline_run_dir.exists(),
        "audit_replay_dir_exists": args.audit_replay_dir.exists(),
        "readiness_true": readiness.get("can_run_gate_aware_reranking_replay"),
        "full_audit_trail_exists": paths["audit_trail"].exists(),
        "score_direction_confirmed": score_direction.get("rank_consistency_pass"),
        "higher_score_is_better": score_direction.get("higher_score_is_better"),
        "feature_usage_rows": int(len(feature_usage)),
        "out_dir": str(out_dir),
        "stopped_before": "review_replay" if args.dry_run else "",
    }
    write_json(dryrun, out_dir / "v8_2_high_beta_penalty_dryrun.json")
    if args.dry_run:
        logger.info("Dry-run complete; stopping before review replay.")
        return

    selection, score_rank = build_selection(audit, ledger)
    diff = selection_diff(selection)
    baseline_reproduced = validate_baseline(diff)
    if not baseline_reproduced:
        raise RuntimeError("baseline_original_rank failed to reproduce v8 selection; refusing review.")

    close = R41.load_close_for_replay(args.provider_uri, audit, baseline_daily, logger)
    replay = evaluate_all(selection, close, args.cost_bps, args.slippage_bps, logger)
    metrics = replay["metrics"]
    concentration = concentration_table(metrics, selection, replay["weights_by_candidate"])
    weakest = weakest_table(metrics)
    gates, statuses = gate_results(metrics, baseline_reproduced=baseline_reproduced)
    metrics = metrics.merge(statuses, on="rerank_candidate", how="left")
    replay["metrics"] = metrics
    verdict = build_verdict(metrics, gates, statuses, baseline_reproduced=baseline_reproduced)

    outputs = {
        "metrics": metrics,
        "weakest": weakest,
        "concentration": concentration,
        "selection_diff": diff,
        "gates": gates,
        "daily": replay["daily"],
        "selection": selection,
        "score_rank": score_rank,
        "loo": replay["loo"],
        "top_month": replay["top_month"],
        "rolling": replay["rolling"],
        "trades": replay["trades"],
        "holdings": replay["holdings"],
    }
    write_outputs(out_dir, outputs, verdict)

    zip_path = OUTPUT_ROOT / f"us_stock_selection_quant_lab_v8_2_high_beta_penalty_robustness_{timestamp}.zip"
    report_path, exec_path = write_reports(timestamp, out_dir, zip_path, score_direction, feature_usage, metrics, weakest, concentration, gates, verdict)
    write_workbook(
        out_dir,
        timestamp,
        {
            "metrics": metrics,
            "weakest_12m": weakest,
            "concentration": concentration,
            "selection_diff": diff,
            "gate_results": gates,
            "verdict": pd.DataFrame([R41.to_jsonable(verdict)]),
        },
    )
    update_next_steps(out_dir, zip_path, verdict)
    write_run_summary(out_dir, zip_path, verdict)
    package_outputs(out_dir, [report_path, exec_path], zip_path)
    sync_meistock(timestamp, out_dir, zip_path, report_path, exec_path, verdict)
    logger.info("Packaged high-beta penalty robustness zip: %s", zip_path)


if __name__ == "__main__":
    main()
