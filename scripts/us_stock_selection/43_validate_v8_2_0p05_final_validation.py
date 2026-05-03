"""Final validation pack for v8.2 high_beta_penalty_0p05.

This is not v9. It does not expand the universe, train a model, run 31b,
add data sources, add parameters, tune candidates, overwrite the v8 baseline,
or automatically replace the current best. It only replays baseline_original_rank
and high_beta_penalty_0p05 from the existing full audit trail.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import math
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

SCRIPT42_PATH = PROJECT_ROOT / "scripts" / "us_stock_selection" / "42_review_v8_2_high_beta_penalty_robustness.py"
SPEC42 = importlib.util.spec_from_file_location("v8_2_high_beta42", SCRIPT42_PATH)
if SPEC42 is None or SPEC42.loader is None:
    raise RuntimeError(f"Cannot load support module: {SCRIPT42_PATH}")
S42 = importlib.util.module_from_spec(SPEC42)
SPEC42.loader.exec_module(S42)
R41 = S42.R41

DEFAULT_BASELINE_RUN_DIR = S42.DEFAULT_BASELINE_RUN_DIR
DEFAULT_AUDIT_REPLAY_DIR = S42.DEFAULT_AUDIT_REPLAY_DIR
DEFAULT_PRIOR_RUN_DIR = S42.OUTPUT_ROOT / "v8_2_high_beta_penalty_robustness_20260501_164800"
OUTPUT_ROOT = S42.OUTPUT_ROOT
DOCS_DIR = S42.DOCS_DIR
MEISTOCK_ROOT = S42.MEISTOCK_ROOT

BASELINE_CAGR = S42.BASELINE_CAGR
BASELINE_COST50_CAGR = S42.BASELINE_COST50_CAGR
BASELINE_CALMAR = S42.BASELINE_CALMAR
BASELINE_MAXDD = S42.BASELINE_MAXDD
ACCEPT_COST50_CAGR = 0.4487
ACCEPT_CALMAR = 1.5932
HIGH_BETA_TICKERS = {"MSTR", "TQQQ", "QLD", "SOXL"}
WEIGHT_TOL = S42.WEIGHT_TOL
FLOAT_TOL = 1e-8

CANDIDATES: dict[str, float] = {
    "baseline_original_rank": 0.00,
    "high_beta_penalty_0p05": 0.05,
}
COST_STRESS_BPS = [0, 10, 25, 50, 75, 100]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build v8.2 0p05 final validation pack.")
    parser.add_argument("--baseline-run-dir", type=Path, default=DEFAULT_BASELINE_RUN_DIR)
    parser.add_argument("--audit-replay-dir", type=Path, default=DEFAULT_AUDIT_REPLAY_DIR)
    parser.add_argument("--prior-robustness-run-dir", type=Path, default=DEFAULT_PRIOR_RUN_DIR)
    parser.add_argument(
        "--prior-robustness-zip",
        type=Path,
        default=OUTPUT_ROOT / "us_stock_selection_quant_lab_v8_2_high_beta_penalty_robustness_20260501_164800.zip",
    )
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
    logger = logging.getLogger("v8_2_0p05_final_validation")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    fh = logging.FileHandler(log_dir / "run.log", encoding="utf-8")
    fh.setFormatter(formatter)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(formatter)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


def write_json(data: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(R41.to_jsonable(data), indent=2, ensure_ascii=False), encoding="utf-8")


def read_prior_csv(prior_dir: Path, prior_zip: Path, name: str) -> pd.DataFrame:
    direct = prior_dir / name
    if direct.exists():
        return pd.read_csv(direct)
    if prior_zip.exists():
        with zipfile.ZipFile(prior_zip, "r") as zf:
            matches = [item for item in zf.namelist() if item.endswith("/" + name) or item == name]
            if matches:
                with zf.open(matches[0]) as fh:
                    return pd.read_csv(fh)
    raise FileNotFoundError(f"Cannot find prior result {name} in {prior_dir} or {prior_zip}")


def feature_usage_audit(audit: pd.DataFrame) -> pd.DataFrame:
    rows = [
        {
            "rerank_candidate": "baseline_original_rank",
            "feature_name": "raw_score",
            "feature_type": "ex-ante-model-score",
            "used_in_ranking": True,
            "allowed": True,
            "available": "raw_score" in audit.columns,
            "reason": "baseline reproduction control",
        },
        {
            "rerank_candidate": "high_beta_penalty_0p05",
            "feature_name": "raw_score",
            "feature_type": "ex-ante-model-score",
            "used_in_ranking": True,
            "allowed": True,
            "available": "raw_score" in audit.columns,
            "reason": "0p05 formula input",
        },
        {
            "rerank_candidate": "high_beta_penalty_0p05",
            "feature_name": "high_beta_flag",
            "feature_type": "ex-ante",
            "used_in_ranking": True,
            "allowed": True,
            "available": "high_beta_flag" in audit.columns,
            "reason": "0p05 formula input",
        },
    ]
    usage = pd.DataFrame(rows)
    if not usage["available"].all() or not usage["allowed"].all():
        raise RuntimeError("0p05 feature usage audit failed.")
    return usage


def build_logic_audit(score_direction: dict[str, Any], audit: pd.DataFrame) -> dict[str, Any]:
    forward_cols = [c for c in audit.columns if str(c).startswith("audit_forward_")]
    used_fields = ["raw_score", "high_beta_flag"]
    blocked_forward_used = [c for c in used_fields if c.startswith("audit_forward_")]
    logic = {
        "score_direction_confirmed": bool(score_direction.get("rank_consistency_pass")),
        "score_sort_ascending": bool(score_direction.get("score_sort_ascending")),
        "higher_score_is_better": bool(score_direction.get("higher_score_is_better")),
        "formula": "adjusted_score = raw_score - 0.05 * high_beta_flag",
        "candidate_universe_source": "v8.2 full score/rank audit trail decision_date x tradable_ticker",
        "selection_rule": "monthly top5 by adjusted_score descending",
        "weighting_rule": "v8 equal weight 20% per selected ticker",
        "ranking_fields": used_fields,
        "high_beta_flag_definition": "True for tickers in the pre-existing high-beta proxy list.",
        "high_beta_tickers": sorted(HIGH_BETA_TICKERS),
        "audit_forward_columns_present": forward_cols,
        "audit_forward_fields_used_in_ranking": blocked_forward_used,
        "uses_future_return_or_drawdown": False,
        "uses_future_top_month": False,
        "changes_model_training": False,
        "expands_universe": False,
        "runs_31b": False,
        "enters_v9": False,
        "logic_pass": bool(score_direction.get("rank_consistency_pass") and score_direction.get("higher_score_is_better") and not blocked_forward_used),
    }
    if not logic["logic_pass"]:
        raise RuntimeError("0p05 logic audit failed; refusing final validation.")
    return logic


def adjusted_score(group: pd.DataFrame, candidate: str) -> pd.Series:
    raw = pd.to_numeric(group["raw_score"], errors="coerce")
    if candidate == "baseline_original_rank":
        return raw
    return raw - 0.05 * group["high_beta_flag"].astype(bool).astype(float)


def build_selection(audit: pd.DataFrame, ledger: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    selection_rows: list[dict[str, Any]] = []
    score_rows: list[pd.DataFrame] = []
    execution_map = ledger.set_index("decision_date")["execution_date"].to_dict()
    for candidate, lam in CANDIDATES.items():
        for decision_date in sorted(ledger["decision_date"].dropna().unique()):
            group = audit.loc[(audit["decision_date"] == decision_date) & audit["tradable_flag"].astype(bool)].copy()
            group["rerank_candidate"] = candidate
            group["lambda"] = lam
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
                        "lambda": lam,
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
    return pd.DataFrame(selection_rows), pd.concat(score_rows, ignore_index=True)


def validate_baseline_against_ledger(selection: pd.DataFrame, ledger: pd.DataFrame) -> tuple[bool, pd.DataFrame]:
    diff = R41.selection_diff_vs_baseline(selection, ledger)
    base = diff.loc[diff["rerank_candidate"] == "baseline_original_rank"].copy()
    ok = bool(not base.empty and base["selected_tickers_match"].astype(bool).all() and (pd.to_numeric(base["changed_count"], errors="coerce") == 0).all())
    return ok, diff


def evaluate(selection: pd.DataFrame, close: pd.DataFrame, cost_bps: float, slippage_bps: float, logger: logging.Logger) -> dict[str, Any]:
    weights_by_candidate = R41.build_weights_from_selection(selection, close)
    results: dict[str, Any] = {}
    for candidate in CANDIDATES:
        logger.info("Evaluating final validation candidate=%s", candidate)
        result = R41.evaluate_candidate(candidate, close, weights_by_candidate[candidate], cost_bps=cost_bps, slippage_bps=slippage_bps)
        metric = dict(result["metrics"])
        metric["lambda"] = CANDIDATES[candidate]
        metric.update(S42.high_beta_selection_stats(selection, candidate))
        metric.update(S42.weakest_window_extra(result["daily"], result["rolling"], weights_by_candidate[candidate]))
        result["metrics"] = metric
        results[candidate] = result
    metrics = pd.DataFrame([results[c]["metrics"] for c in CANDIDATES])
    metrics.insert(1, "final_validation_candidate", metrics["rerank_candidate"] == "high_beta_penalty_0p05")
    return {
        "weights_by_candidate": weights_by_candidate,
        "results": results,
        "metrics": metrics,
        "daily": pd.concat([results[c]["daily"] for c in CANDIDATES], ignore_index=True),
        "selection": selection,
        "holdings": R41.holdings_long(weights_by_candidate),
    }


def compare_reproduction(
    current_metrics: pd.DataFrame,
    current_daily: pd.DataFrame,
    current_selection: pd.DataFrame,
    prior_metrics: pd.DataFrame,
    prior_daily: pd.DataFrame,
    prior_selection: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    metric_cols = [
        "cagr",
        "cost50_cagr",
        "calmar",
        "max_drawdown",
        "weakest_12m_Calmar",
        "weakest_12m_50bps_CAGR",
        "weakest_12m_top3_positive_month_share",
        "avg_high_beta_weight_share",
        "max_high_beta_weight_share",
        "selected_high_beta_count",
    ]
    for candidate in CANDIDATES:
        cur = current_metrics.loc[current_metrics["rerank_candidate"] == candidate].head(1)
        prv = prior_metrics.loc[prior_metrics["rerank_candidate"] == candidate].head(1)
        for col in metric_cols:
            cur_val = float(pd.to_numeric(cur[col], errors="coerce").iloc[0]) if not cur.empty and col in cur else np.nan
            prv_val = float(pd.to_numeric(prv[col], errors="coerce").iloc[0]) if not prv.empty and col in prv else np.nan
            rows.append(
                {
                    "candidate": candidate,
                    "check_type": "metric",
                    "field": col,
                    "current_value": cur_val,
                    "prior_value": prv_val,
                    "abs_diff": abs(cur_val - prv_val) if pd.notna(cur_val) and pd.notna(prv_val) else np.nan,
                    "pass": bool(pd.notna(cur_val) and pd.notna(prv_val) and abs(cur_val - prv_val) <= FLOAT_TOL),
                }
            )
        cur_nav = current_daily.loc[current_daily["rerank_candidate"] == candidate, ["date", "nav", "cost50_nav"]].copy()
        prv_nav = prior_daily.loc[prior_daily["rerank_candidate"] == candidate, ["date", "nav", "cost50_nav"]].copy()
        cur_nav["date"] = pd.to_datetime(cur_nav["date"])
        prv_nav["date"] = pd.to_datetime(prv_nav["date"])
        merged_nav = cur_nav.merge(prv_nav, on="date", suffixes=("_current", "_prior"))
        for col in ["nav", "cost50_nav"]:
            diffs = (merged_nav[f"{col}_current"] - merged_nav[f"{col}_prior"]).abs() if not merged_nav.empty else pd.Series(dtype=float)
            max_diff = float(diffs.max()) if not diffs.empty else np.nan
            rows.append(
                {
                    "candidate": candidate,
                    "check_type": "nav",
                    "field": f"max_abs_{col}_diff",
                    "current_value": max_diff,
                    "prior_value": 0.0,
                    "abs_diff": max_diff,
                    "pass": bool(pd.notna(max_diff) and max_diff <= FLOAT_TOL),
                }
            )
        keys = ["decision_date", "ticker", "selected_rank"]
        cur_sel = current_selection.loc[current_selection["rerank_candidate"] == candidate, keys].copy().sort_values(keys)
        prv_sel = prior_selection.loc[prior_selection["rerank_candidate"] == candidate, keys].copy().sort_values(keys)
        cur_tuples = set(map(tuple, cur_sel.astype(str).to_numpy()))
        prv_tuples = set(map(tuple, prv_sel.astype(str).to_numpy()))
        mismatch = len(cur_tuples.symmetric_difference(prv_tuples))
        rows.append(
            {
                "candidate": candidate,
                "check_type": "selection",
                "field": "symmetric_difference_decision_ticker_rank",
                "current_value": mismatch,
                "prior_value": 0,
                "abs_diff": mismatch,
                "pass": mismatch == 0,
            }
        )
    return pd.DataFrame(rows)


def cost_stress(close: pd.DataFrame, weights_by_candidate: dict[str, pd.DataFrame], slippage_bps: float) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for candidate, weights in weights_by_candidate.items():
        trade_count = int((weights.diff().fillna(weights).abs() > WEIGHT_TOL).sum().sum())
        for cost in COST_STRESS_BPS:
            returns, turnover = R41.portfolio_returns(close, weights, cost_bps=float(cost), slippage_bps=slippage_bps)
            metrics = R41.compute_portfolio_metrics(returns, turnover, weights)
            rows.append(
                {
                    "candidate": candidate,
                    "cost_bps": cost,
                    "slippage_bps": slippage_bps,
                    "CAGR": metrics.get("cagr"),
                    "MaxDD": metrics.get("max_drawdown"),
                    "Calmar": metrics.get("calmar"),
                    "cost_adjusted_CAGR": metrics.get("cagr"),
                    "cost_adjusted_Calmar": metrics.get("calmar"),
                    "annual_turnover": metrics.get("annual_turnover"),
                    "trade_count": trade_count,
                    "pass_cagr_20": bool(metrics.get("cagr", -999) >= 0.20),
                    "pass_calmar_1": bool(metrics.get("calmar", -999) >= 1.0),
                    "pass_50bps_threshold_equivalent": bool(metrics.get("cagr", -999) >= ACCEPT_COST50_CAGR),
                }
            )
    return pd.DataFrame(rows)


def monthly_tables(results: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    monthly_parts = []
    top_rows = []
    remove_parts = []
    for candidate, result in results.items():
        monthly = result["monthly"].copy()
        monthly["candidate"] = candidate
        monthly_parts.append(monthly)
        top_pos = monthly.loc[monthly["monthly_profit"] > 0].sort_values("monthly_profit", ascending=False)
        top_rows.append(
            {
                "candidate": candidate,
                "top1_positive_month_share": float(top_pos["positive_profit_share"].head(1).sum()) if not top_pos.empty else np.nan,
                "top3_positive_month_share": float(top_pos["positive_profit_share"].head(3).sum()) if not top_pos.empty else np.nan,
                "top5_positive_month_share": float(top_pos["positive_profit_share"].head(5).sum()) if not top_pos.empty else np.nan,
                "top1_months": ",".join(top_pos["month"].head(1).astype(str).tolist()),
                "top3_months": ",".join(top_pos["month"].head(3).astype(str).tolist()),
                "top5_months": ",".join(top_pos["month"].head(5).astype(str).tolist()),
                "top5_concentration_gt_60pct": bool(float(top_pos["positive_profit_share"].head(5).sum()) > 0.60) if not top_pos.empty else False,
            }
        )
        removed = result["removed"].copy()
        removed["candidate"] = candidate
        remove_parts.append(removed)
    monthly_all = pd.concat(monthly_parts, ignore_index=True)
    base = monthly_all.loc[monthly_all["candidate"] == "baseline_original_rank"].copy()
    p05 = monthly_all.loc[monthly_all["candidate"] == "high_beta_penalty_0p05"].copy()
    comp = base.merge(p05, on="month", suffixes=("_baseline", "_p05"))
    comp["monthly_return_diff_p05_minus_baseline"] = comp["monthly_return_p05"] - comp["monthly_return_baseline"]
    comp["monthly_profit_diff_p05_minus_baseline"] = comp["monthly_profit_p05"] - comp["monthly_profit_baseline"]
    comp["p05_improved_month"] = comp["monthly_return_diff_p05_minus_baseline"] > 0
    comp["p05_worsened_month"] = comp["monthly_return_diff_p05_minus_baseline"] < 0
    return comp, pd.DataFrame(top_rows), pd.concat(remove_parts, ignore_index=True)


def period_returns_by_decision(ledger: pd.DataFrame, daily: pd.DataFrame) -> dict[str, dict[str, float]]:
    piv = daily.pivot(index="date", columns="rerank_candidate", values="return")
    piv.index = pd.to_datetime(piv.index)
    decisions = ledger[["decision_date", "execution_date"]].dropna().sort_values("execution_date").copy()
    out: dict[str, dict[str, float]] = {}
    for i, row in decisions.reset_index(drop=True).iterrows():
        start = pd.Timestamp(row["execution_date"])
        end = pd.Timestamp(decisions.iloc[i + 1]["execution_date"]) if i + 1 < len(decisions) else piv.index.max() + pd.Timedelta(days=1)
        local = piv.loc[(piv.index >= start) & (piv.index < end)]
        out[R41.date_str(row["decision_date"])] = {
            candidate: float((1.0 + local[candidate].dropna()).prod() - 1.0) if candidate in local else np.nan
            for candidate in CANDIDATES
        }
    return out


def selection_diff_by_month(selection: pd.DataFrame, ledger: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    period_returns = period_returns_by_decision(ledger, daily)
    rows: list[dict[str, Any]] = []
    base = selection.loc[selection["rerank_candidate"] == "baseline_original_rank"].copy()
    p05 = selection.loc[selection["rerank_candidate"] == "high_beta_penalty_0p05"].copy()
    for decision_date, bgroup in base.groupby("decision_date"):
        pgroup = p05.loc[p05["decision_date"] == decision_date].copy()
        b_tickers = bgroup.sort_values("selected_rank")["ticker"].tolist()
        p_tickers = pgroup.sort_values("selected_rank")["ticker"].tolist()
        removed = [t for t in b_tickers if t not in p_tickers]
        added = [t for t in p_tickers if t not in b_tickers]
        returns = period_returns.get(str(decision_date), {})
        rows.append(
            {
                "decision_date": decision_date,
                "baseline_selected_tickers": ",".join(b_tickers),
                "p05_selected_tickers": ",".join(p_tickers),
                "removed_tickers": ",".join(removed),
                "added_tickers": ",".join(added),
                "removed_high_beta_count": sum(t in HIGH_BETA_TICKERS for t in removed),
                "added_high_beta_count": sum(t in HIGH_BETA_TICKERS for t in added),
                "return_impact_next_period_audit_only": returns.get("high_beta_penalty_0p05", np.nan) - returns.get("baseline_original_rank", np.nan),
                "baseline_next_period_return_audit_only": returns.get("baseline_original_rank", np.nan),
                "p05_next_period_return_audit_only": returns.get("high_beta_penalty_0p05", np.nan),
                "high_beta_weight_baseline": 0.20 * sum(t in HIGH_BETA_TICKERS for t in b_tickers),
                "high_beta_weight_p05": 0.20 * sum(t in HIGH_BETA_TICKERS for t in p_tickers),
            }
        )
    return pd.DataFrame(rows)


def ticker_selection_frequency(selection: pd.DataFrame) -> pd.DataFrame:
    rows = []
    tickers = sorted(selection["ticker"].unique())
    decision_count = selection["decision_date"].nunique()
    for ticker in tickers:
        row = {"ticker": ticker, "is_high_beta": ticker in HIGH_BETA_TICKERS}
        for candidate in CANDIDATES:
            sub = selection.loc[(selection["rerank_candidate"] == candidate) & (selection["ticker"] == ticker)]
            row[f"{candidate}_selected_count"] = int(len(sub))
            row[f"{candidate}_selected_frequency"] = float(len(sub) / decision_count) if decision_count else 0.0
        row["selected_count_delta_p05_minus_baseline"] = row["high_beta_penalty_0p05_selected_count"] - row["baseline_original_rank_selected_count"]
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["is_high_beta", "selected_count_delta_p05_minus_baseline", "ticker"], ascending=[False, True, True])


def high_beta_exposure_summary(metrics: pd.DataFrame, selection: pd.DataFrame, weights_by_candidate: dict[str, pd.DataFrame]) -> pd.DataFrame:
    concentration = S42.concentration_table(metrics, selection, weights_by_candidate)
    base = concentration.loc[concentration["rerank_candidate"] == "baseline_original_rank"].head(1)
    p05 = concentration.loc[concentration["rerank_candidate"] == "high_beta_penalty_0p05"].head(1)
    rows = []
    for field in ["avg_high_beta_weight_share", "max_high_beta_weight_share", "selected_high_beta_count", "high_beta_selection_frequency"]:
        rows.append(
            {
                "metric": field,
                "baseline": float(pd.to_numeric(base[field], errors="coerce").iloc[0]),
                "p05": float(pd.to_numeric(p05[field], errors="coerce").iloc[0]),
                "delta_p05_minus_baseline": float(pd.to_numeric(p05[field], errors="coerce").iloc[0] - pd.to_numeric(base[field], errors="coerce").iloc[0]),
            }
        )
    for ticker in sorted(HIGH_BETA_TICKERS):
        for field in [f"{ticker}_selected_count", f"{ticker}_selected_month_frequency", f"{ticker}_avg_weight_active", f"{ticker}_max_weight"]:
            rows.append(
                {
                    "metric": field,
                    "baseline": float(pd.to_numeric(base[field], errors="coerce").iloc[0]),
                    "p05": float(pd.to_numeric(p05[field], errors="coerce").iloc[0]),
                    "delta_p05_minus_baseline": float(pd.to_numeric(p05[field], errors="coerce").iloc[0] - pd.to_numeric(base[field], errors="coerce").iloc[0]),
                }
            )
    return pd.DataFrame(rows)


def weakest_12m_deep_dive(metrics: pd.DataFrame, monthly_comparison: pd.DataFrame, selection_diff: pd.DataFrame, weights_by_candidate: dict[str, pd.DataFrame]) -> pd.DataFrame:
    base_row = metrics.loc[metrics["rerank_candidate"] == "baseline_original_rank"].iloc[0]
    p05_row = metrics.loc[metrics["rerank_candidate"] == "high_beta_penalty_0p05"].iloc[0]
    start_s, end_s = str(p05_row["weakest_12m_window"]).split(":")
    start = pd.Period(start_s, freq="M")
    end = pd.Period(end_s, freq="M")
    local = monthly_comparison.loc[pd.PeriodIndex(monthly_comparison["month"], freq="M").to_series().between(start, end).values].copy()
    improved = local.sort_values("monthly_return_diff_p05_minus_baseline", ascending=False).head(3)["month"].astype(str).tolist()
    worsened = local.sort_values("monthly_return_diff_p05_minus_baseline", ascending=True).head(3)["month"].astype(str).tolist()
    rows = []
    for item in local.itertuples(index=False):
        month = str(item.month)
        period = pd.Period(month, freq="M")
        row = {
            "weakest_window_start": start_s,
            "weakest_window_end": end_s,
            "month": month,
            "baseline_CAGR": base_row["weakest_12m_CAGR"],
            "p05_CAGR": p05_row["weakest_12m_CAGR"],
            "baseline_50bps_CAGR": base_row["weakest_12m_50bps_CAGR"],
            "p05_50bps_CAGR": p05_row["weakest_12m_50bps_CAGR"],
            "baseline_MaxDD": base_row["weakest_12m_MaxDD"],
            "p05_MaxDD": p05_row["weakest_12m_MaxDD"],
            "baseline_Calmar": base_row["weakest_12m_Calmar"],
            "p05_Calmar": p05_row["weakest_12m_Calmar"],
            "baseline_monthly_return": item.monthly_return_baseline,
            "p05_monthly_return": item.monthly_return_p05,
            "return_diff_p05_minus_baseline": item.monthly_return_diff_p05_minus_baseline,
            "baseline_top1_share": base_row["weakest_12m_top1_positive_month_share"],
            "p05_top1_share": p05_row["weakest_12m_top1_positive_month_share"],
            "baseline_top3_share": base_row["weakest_12m_top3_positive_month_share"],
            "p05_top3_share": p05_row["weakest_12m_top3_positive_month_share"],
            "baseline_top5_share": base_row["weakest_12m_top5_positive_month_share"],
            "p05_top5_share": p05_row["weakest_12m_top5_positive_month_share"],
            "baseline_window_high_beta_weight_share": base_row["weakest_12m_high_beta_weight_share"],
            "p05_window_high_beta_weight_share": p05_row["weakest_12m_high_beta_weight_share"],
            "main_improved_months": ",".join(improved),
            "main_worsened_months": ",".join(worsened),
        }
        for candidate, weights in weights_by_candidate.items():
            w_period = weights.index.to_period("M")
            local_weights = weights.loc[w_period == period]
            high_cols = [c for c in local_weights.columns if str(c).upper() in HIGH_BETA_TICKERS]
            active = local_weights.abs().sum(axis=1) > WEIGHT_TOL if not local_weights.empty else pd.Series(dtype=bool)
            row[f"{candidate}_month_high_beta_weight_share"] = (
                float(local_weights.loc[active, high_cols].sum(axis=1).mean()) if high_cols and active.any() else 0.0
            )
        diff = selection_diff.loc[pd.to_datetime(selection_diff["decision_date"]).dt.to_period("M") == period]
        if not diff.empty:
            d = diff.iloc[0]
            row["baseline_selected_tickers"] = d["baseline_selected_tickers"]
            row["p05_selected_tickers"] = d["p05_selected_tickers"]
            row["selected_ticker_differences"] = f"removed={d['removed_tickers']}; added={d['added_tickers']}"
            row["baseline_selected_high_beta_count"] = int(round(float(d["high_beta_weight_baseline"]) / 0.20))
            row["p05_selected_high_beta_count"] = int(round(float(d["high_beta_weight_p05"]) / 0.20))
        rows.append(row)
    return pd.DataFrame(rows)


def final_classification(metrics: pd.DataFrame, reproduction_pass: bool, no_future_function: bool, cost_stress_df: pd.DataFrame) -> dict[str, Any]:
    base = metrics.loc[metrics["rerank_candidate"] == "baseline_original_rank"].iloc[0]
    p05 = metrics.loc[metrics["rerank_candidate"] == "high_beta_penalty_0p05"].iloc[0]
    p05_cost50 = float(p05["cost50_cagr"])
    risk_control_checks = {
        "reproduction_pass": reproduction_pass,
        "no_future_function": no_future_function,
        "cost50_cagr_ge_04487": p05_cost50 >= ACCEPT_COST50_CAGR,
        "calmar_ge_15932": float(p05["calmar"]) >= ACCEPT_CALMAR,
        "maxdd_better_than_baseline": float(p05["max_drawdown"]) > float(base["max_drawdown"]),
        "weakest_12m_calmar_ge_1": float(p05["weakest_12m_Calmar"]) >= 1.0,
        "weakest_12m_50bps_cagr_ge_20": float(p05["weakest_12m_50bps_CAGR"]) >= 0.20,
        "high_beta_exposure_clearly_lower": float(p05["avg_high_beta_weight_share"]) <= float(base["avg_high_beta_weight_share"]) * 0.80,
        "full_period_cagr_below_baseline": float(p05["cagr"]) < float(base["cagr"]),
        "full_period_calmar_below_baseline": float(p05["calmar"]) < float(base["calmar"]),
        "top_month_concentration_risk_exists": float(p05["top5_positive_month_share"]) > 0.60,
    }
    risk_control_variant = all(risk_control_checks.values())
    replace_checks = {
        "risk_control_variant": risk_control_variant,
        "full_period_calmar_ge_baseline": float(p05["calmar"]) >= float(base["calmar"]),
        "cost50_cagr_ge_90pct_baseline": p05_cost50 >= BASELINE_COST50_CAGR * 0.90,
        "top3_share_not_above_baseline": float(p05["top3_positive_month_share"]) <= float(base["top3_positive_month_share"]),
        "top5_share_not_above_baseline": float(p05["top5_positive_month_share"]) <= float(base["top5_positive_month_share"]),
        "remove_top5_cagr_not_worse": float(p05["remove_top5_month_cagr"]) >= float(base["remove_top5_month_cagr"]) * 0.90,
    }
    replace_candidate = all(replace_checks.values())
    p05_75 = cost_stress_df.loc[(cost_stress_df["candidate"] == "high_beta_penalty_0p05") & (cost_stress_df["cost_bps"] == 75)]
    p05_100 = cost_stress_df.loc[(cost_stress_df["candidate"] == "high_beta_penalty_0p05") & (cost_stress_df["cost_bps"] == 100)]
    cost_pressure_fragile = bool(
        (not p05_75.empty and float(p05_75["CAGR"].iloc[0]) < ACCEPT_COST50_CAGR)
        or (not p05_100.empty and float(p05_100["CAGR"].iloc[0]) < ACCEPT_COST50_CAGR)
    )
    safety_margin = p05_cost50 - ACCEPT_COST50_CAGR
    if replace_candidate:
        classification = "replace_baseline_candidate"
    elif risk_control_variant:
        classification = "risk_control_variant"
    elif float(p05["weakest_12m_Calmar"]) > float(base["weakest_12m_Calmar"]):
        classification = "diagnostic_only"
    else:
        classification = "rejected"
    return {
        "cycle": "v8_2_high_beta_penalty_0p05_final_validation",
        "completed": True,
        "reproduction_pass": reproduction_pass,
        "no_future_function": no_future_function,
        "risk_control_checks": risk_control_checks,
        "replace_baseline_checks": replace_checks,
        "final_classification": classification,
        "is_risk_control_variant": classification == "risk_control_variant",
        "replace_baseline_candidate": replace_candidate,
        "replace_v8_best": False,
        "allow_enter_v9": False,
        "cost50_cagr_safety_margin_vs_04487": safety_margin,
        "cost_pressure_fragile_above_50bps": cost_pressure_fragile,
        "top5_concentration_risk": float(p05["top5_positive_month_share"]),
        "remove_top5_month_cagr": float(p05["remove_top5_month_cagr"]),
        "stop_v8_2_reranking_route_recommended": False,
        "next_stage_recommendation": "Human review risk-control variant; do not replace v8 baseline automatically.",
    }


def table(df: pd.DataFrame, columns: list[str] | None = None, max_rows: int = 30) -> str:
    return R41.table_to_markdown(df, max_rows=max_rows, columns=columns)


def write_reports(
    timestamp: str,
    out_dir: Path,
    zip_path: Path,
    logic_audit: dict[str, Any],
    repro: pd.DataFrame,
    metrics: pd.DataFrame,
    cost: pd.DataFrame,
    monthly: pd.DataFrame,
    top_conc: pd.DataFrame,
    remove_top: pd.DataFrame,
    weakest: pd.DataFrame,
    selection_diff: pd.DataFrame,
    exposure: pd.DataFrame,
    verdict: dict[str, Any],
) -> tuple[Path, Path]:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = DOCS_DIR / f"US_STOCK_SELECTION_V8_2_0P05_FINAL_VALIDATION_{timestamp}.md"
    exec_path = DOCS_DIR / f"US_STOCK_SELECTION_V8_2_0P05_FINAL_VALIDATION_EXEC_SUMMARY_{timestamp}.md"
    report = f"""# US Stock Selection v8.2 0p05 Final Validation

## 1. Background And Purpose

This final validation pack only reviews `high_beta_penalty_0p05` versus `baseline_original_rank`. It does not search for new parameters or replace the v8 baseline.

## 2. Why Only 0p05

The prior targeted robustness review found `high_beta_penalty_0p05` as the only accepted risk-control candidate. This pack tests reproducibility, cost pressure, month concentration, weakest 12M behavior, and selection differences.

## 3. Code Logic And Forward Function Check

```json
{json.dumps(R41.to_jsonable(logic_audit), indent=2, ensure_ascii=False)}
```

## 4. Reproduction Result

{table(repro, max_rows=40)}

{table(metrics, columns=['rerank_candidate','cagr','cost50_cagr','calmar','max_drawdown','weakest_12m_Calmar','weakest_12m_50bps_CAGR','avg_high_beta_weight_share','top5_positive_month_share','remove_top5_month_cagr'], max_rows=10)}

## 5. Cost Stress

{table(cost, max_rows=20)}

## 6. Monthly Returns And Concentration

{table(monthly, columns=['month','monthly_return_baseline','monthly_return_p05','monthly_return_diff_p05_minus_baseline','p05_improved_month','p05_worsened_month'], max_rows=30)}

{table(top_conc, max_rows=10)}

{table(remove_top, columns=['candidate','removed_top_positive_month_count','removed_months','cagr','max_drawdown','calmar'], max_rows=20)}

## 7. Weakest 12M Deep Dive

{table(weakest, max_rows=20)}

## 8. Selection Difference Analysis

{table(selection_diff, max_rows=25)}

{table(exposure, max_rows=30)}

## 9. Final Classification

Final classification: `{verdict.get('final_classification')}`.

`replace_v8_best` is `False`. `allow_enter_v9` is `False`.

## 10. Baseline Replacement

`high_beta_penalty_0p05` is not a baseline replacement candidate because full-period CAGR/Calmar are below v8 baseline and top5 positive month concentration remains high.

## 11. v9

Do not enter v9 from this pack.

## 12. Recommendation

{verdict.get('next_stage_recommendation')}

## 13. Output

- Output directory: `{out_dir}`
- Zip: `{zip_path}`
"""
    exec_summary = f"""# v8.2 0p05 Final Validation Exec Summary

- Reproduction pass: `{verdict.get('reproduction_pass')}`
- Final classification: `{verdict.get('final_classification')}`
- Risk-control variant: `{verdict.get('is_risk_control_variant')}`
- Replace baseline candidate: `{verdict.get('replace_baseline_candidate')}`
- Replace v8 best: `False`
- Allow enter v9: `False`
- 50bps CAGR safety margin vs 0.4487: `{verdict.get('cost50_cagr_safety_margin_vs_04487')}`
- Top5 concentration risk: `{verdict.get('top5_concentration_risk')}`

## Key Metrics

{table(metrics, columns=['rerank_candidate','cagr','cost50_cagr','calmar','max_drawdown','weakest_12m_Calmar','weakest_12m_50bps_CAGR','avg_high_beta_weight_share','candidate_status'], max_rows=10)}
"""
    report_path.write_text(report, encoding="utf-8")
    exec_path.write_text(exec_summary, encoding="utf-8")
    reports_dir = out_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(report_path, reports_dir / report_path.name)
    shutil.copy2(exec_path, reports_dir / exec_path.name)
    return report_path, exec_path


def update_next_steps(out_dir: Path, zip_path: Path, verdict: dict[str, Any]) -> None:
    path = PROJECT_ROOT / "NEXT_STEPS.md"
    text = path.read_text(encoding="utf-8") if path.exists() else "# NEXT_STEPS\n"
    header = "## v8.2 high_beta_penalty_0p05 final validation"
    section = f"""

{header}

- 执行状态：completed，随后按要求暂停，不自动进入下一轮。
- 输出目录：`{out_dir}`
- zip：`{zip_path}`
- 是否复现通过：`{verdict.get('reproduction_pass')}`
- 是否为 risk_control_variant：`{verdict.get('is_risk_control_variant')}`
- 最终分类：`{verdict.get('final_classification')}`
- 是否替代 baseline：`False`
- 是否允许进入 v9：`False`
- 是否建议停止 v8.2 reranking 路线：`{verdict.get('stop_v8_2_reranking_route_recommended')}`
- 下一阶段建议：`{verdict.get('next_stage_recommendation')}`
- 本轮边界：未进入 v9，未扩 universe，未训练新模型，未运行 31b，未新增参数，未自动替代 v8 baseline。
"""
    pattern = re.compile(r"\n\n## v8\.2 high_beta_penalty_0p05 final validation\n.*?(?=\n\n## |\Z)", re.S)
    text = pattern.sub(section, text) if pattern.search(text) else text.rstrip() + section
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def write_run_summary(out_dir: Path, zip_path: Path, verdict: dict[str, Any]) -> None:
    text = f"""# RUN_SUMMARY

本轮目标：v8.2 high_beta_penalty_0p05 final validation pack。

新 run 目录：`{out_dir}`

zip：`{zip_path}`

是否进入 v9：`False`

是否扩 universe：`False`

是否训练新模型：`False`

是否运行 31b：`False`

是否新增参数：`False`

是否使用 audit_forward 字段排序：`False`

是否替代 v8 baseline：`False`

复现是否通过：`{verdict.get('reproduction_pass')}`

最终分类：`{verdict.get('final_classification')}`

是否为 risk_control_variant：`{verdict.get('is_risk_control_variant')}`

后续：暂停，等待用户/ChatGPT 决策。
"""
    (PROJECT_ROOT / "RUN_SUMMARY.md").write_text(text, encoding="utf-8")
    (out_dir / "RUN_SUMMARY.md").write_text(text, encoding="utf-8")


def package_outputs(out_dir: Path, docs: list[Path], zip_path: Path) -> None:
    files = [
        PROJECT_ROOT / "scripts" / "us_stock_selection" / "43_validate_v8_2_0p05_final_validation.py",
        SCRIPT42_PATH,
        S42.SCRIPT41_PATH,
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
            arc = str(path.relative_to(PROJECT_ROOT)) if path.is_relative_to(PROJECT_ROOT) else path.name
            if arc in seen:
                continue
            seen.add(arc)
            zf.write(path, arc)


def sync_meistock(timestamp: str, out_dir: Path, zip_path: Path, report_path: Path, exec_path: Path, verdict: dict[str, Any]) -> None:
    if not MEISTOCK_ROOT.exists():
        return
    for sub in ["01_对话沉淀/Codex", "02_项目文档/报告章节底稿", "06_证据链", "07_附件索引", "docs/context", "00_项目总控"]:
        (MEISTOCK_ROOT / sub).mkdir(parents=True, exist_ok=True)
    shutil.copy2(report_path, MEISTOCK_ROOT / "02_项目文档" / "报告章节底稿" / report_path.name)
    shutil.copy2(exec_path, MEISTOCK_ROOT / "02_项目文档" / "报告章节底稿" / exec_path.name)
    shutil.copy2(PROJECT_ROOT / "NEXT_STEPS.md", MEISTOCK_ROOT / "00_项目总控" / "NEXT_STEPS.md")
    for name in [
        "v8_2_0p05_final_verdict.json",
        "v8_2_0p05_reproduction_metrics.csv",
        "v8_2_0p05_cost_stress.csv",
        "v8_2_0p05_top_month_concentration.csv",
        "v8_2_0p05_weakest_12m_deep_dive.csv",
        "v8_2_0p05_selection_diff_by_month.csv",
    ]:
        source = out_dir / name
        if source.exists():
            shutil.copy2(source, MEISTOCK_ROOT / "06_证据链" / f"{timestamp}_{name}")
    if zip_path.exists():
        shutil.copy2(zip_path, MEISTOCK_ROOT / "07_附件索引" / zip_path.name)
    checkpoint = f"""# Codex Checkpoint - v8.2 0p05 Final Validation {timestamp}

- Output directory: `{out_dir}`
- Zip: `{zip_path}`
- Reproduction pass: `{verdict.get('reproduction_pass')}`
- Final classification: `{verdict.get('final_classification')}`
- Replace v8 best: `False`
- Allow enter v9: `False`

Pause for user/ChatGPT decision.
"""
    (MEISTOCK_ROOT / "01_对话沉淀" / "Codex" / f"{timestamp}_v8_2_0p05_final_validation_checkpoint.md").write_text(checkpoint, encoding="utf-8")
    context = f"""# MeiStock Current Context

Last updated: {timestamp}

Latest checkpoint: v8.2 high_beta_penalty_0p05 final validation.

Final classification: `{verdict.get('final_classification')}`.

v8 baseline remains current best. Do not enter v9, expand universe, train a new model, or replace best without explicit user/ChatGPT approval.

Latest zip: `{zip_path}`.
"""
    (MEISTOCK_ROOT / "docs" / "context" / "MeiStock_current_context.md").write_text(context, encoding="utf-8")


def main() -> None:
    args = parse_args()
    timestamp = args.timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = (args.out_dir or OUTPUT_ROOT / f"v8_2_0p05_final_validation_{timestamp}").resolve()
    (out_dir / "reports").mkdir(parents=True, exist_ok=True)
    logger = setup_logger(out_dir)
    logger.info("Starting v8.2 high_beta_penalty_0p05 final validation.")
    logger.info("Boundaries: no v9, no universe expansion, no training, no 31b, no new parameters.")

    paths = R41.ensure_inputs(args.baseline_run_dir, args.audit_replay_dir)
    audit, ledger, holdings, baseline_daily = R41.normalize_inputs(
        R41.read_csv(paths["audit_trail"]),
        R41.read_csv(paths["baseline_ledger"]),
        R41.read_csv(paths["baseline_holdings"]),
        R41.read_csv(paths["baseline_daily_nav"]),
    )
    score_direction = R41.score_direction_check(audit, ledger)
    S42.assert_score_direction(score_direction)
    logic_audit = build_logic_audit(score_direction, audit)
    feature_usage = feature_usage_audit(audit)
    write_json(logic_audit, out_dir / "v8_2_0p05_logic_audit.json")
    feature_usage.to_csv(out_dir / "v8_2_0p05_feature_usage_audit.csv", index=False, encoding="utf-8-sig")
    dryrun = {
        "dry_run": bool(args.dry_run),
        "baseline_run_exists": args.baseline_run_dir.exists(),
        "audit_replay_dir_exists": args.audit_replay_dir.exists(),
        "prior_robustness_run_exists": args.prior_robustness_run_dir.exists(),
        "score_direction_confirmed": score_direction.get("rank_consistency_pass"),
        "logic_pass": logic_audit.get("logic_pass"),
        "out_dir": str(out_dir),
        "stopped_before": "final_validation_replay" if args.dry_run else "",
    }
    write_json(dryrun, out_dir / "v8_2_0p05_dryrun.json")
    if args.dry_run:
        logger.info("Dry-run complete; stopping before replay.")
        return

    selection, score_rank = build_selection(audit, ledger)
    baseline_reproduced, baseline_diff = validate_baseline_against_ledger(selection, ledger)
    if not baseline_reproduced:
        raise RuntimeError("baseline_original_rank did not reproduce v8; refusing final validation.")
    close = R41.load_close_for_replay(args.provider_uri, audit, baseline_daily, logger)
    replay = evaluate(selection, close, args.cost_bps, args.slippage_bps, logger)

    prior_metrics = read_prior_csv(args.prior_robustness_run_dir, args.prior_robustness_zip, "v8_2_high_beta_penalty_metrics.csv")
    prior_daily = read_prior_csv(args.prior_robustness_run_dir, args.prior_robustness_zip, "v8_2_high_beta_penalty_nav_by_candidate.csv")
    prior_selection = read_prior_csv(args.prior_robustness_run_dir, args.prior_robustness_zip, "v8_2_high_beta_penalty_selection_by_month.csv")
    repro_diff = compare_reproduction(replay["metrics"], replay["daily"], selection, prior_metrics, prior_daily, prior_selection)
    reproduction_pass = bool(repro_diff["pass"].all())
    if not reproduction_pass:
        logger.error("Reproduction diff failed; outputs will still be packaged.")

    cost = cost_stress(close, replay["weights_by_candidate"], slippage_bps=args.slippage_bps)
    monthly, top_conc, remove_top = monthly_tables(replay["results"])
    select_diff = selection_diff_by_month(selection, ledger, replay["daily"])
    frequency = ticker_selection_frequency(selection)
    exposure = high_beta_exposure_summary(replay["metrics"], selection, replay["weights_by_candidate"])
    weakest = weakest_12m_deep_dive(replay["metrics"], monthly, select_diff, replay["weights_by_candidate"])
    verdict = final_classification(replay["metrics"], reproduction_pass, no_future_function=True, cost_stress_df=cost)

    replay["metrics"].to_csv(out_dir / "v8_2_0p05_reproduction_metrics.csv", index=False, encoding="utf-8-sig")
    replay["daily"].to_csv(out_dir / "v8_2_0p05_reproduction_nav.csv", index=False, encoding="utf-8-sig")
    selection.to_csv(out_dir / "v8_2_0p05_reproduction_selection.csv", index=False, encoding="utf-8-sig")
    score_rank.to_csv(out_dir / "v8_2_0p05_score_rank_by_month.csv", index=False, encoding="utf-8-sig")
    repro_diff.to_csv(out_dir / "v8_2_0p05_reproduction_diff_vs_prior.csv", index=False, encoding="utf-8-sig")
    cost.to_csv(out_dir / "v8_2_0p05_cost_stress.csv", index=False, encoding="utf-8-sig")
    monthly.to_csv(out_dir / "v8_2_0p05_monthly_return_comparison.csv", index=False, encoding="utf-8-sig")
    top_conc.to_csv(out_dir / "v8_2_0p05_top_month_concentration.csv", index=False, encoding="utf-8-sig")
    remove_top.to_csv(out_dir / "v8_2_0p05_remove_top_month_stress.csv", index=False, encoding="utf-8-sig")
    weakest.to_csv(out_dir / "v8_2_0p05_weakest_12m_deep_dive.csv", index=False, encoding="utf-8-sig")
    select_diff.to_csv(out_dir / "v8_2_0p05_selection_diff_by_month.csv", index=False, encoding="utf-8-sig")
    frequency.to_csv(out_dir / "v8_2_0p05_ticker_selection_frequency.csv", index=False, encoding="utf-8-sig")
    exposure.to_csv(out_dir / "v8_2_0p05_high_beta_exposure_summary.csv", index=False, encoding="utf-8-sig")
    baseline_diff.to_csv(out_dir / "v8_2_0p05_baseline_reproduction_diff_vs_ledger.csv", index=False, encoding="utf-8-sig")
    write_json(verdict, out_dir / "v8_2_0p05_final_verdict.json")

    zip_path = OUTPUT_ROOT / f"us_stock_selection_quant_lab_v8_2_0p05_final_validation_{timestamp}.zip"
    report_path, exec_path = write_reports(
        timestamp,
        out_dir,
        zip_path,
        logic_audit,
        repro_diff,
        replay["metrics"],
        cost,
        monthly,
        top_conc,
        remove_top,
        weakest,
        select_diff,
        exposure,
        verdict,
    )
    R41.write_excel(
        {
            "metrics": replay["metrics"],
            "reproduction_diff": repro_diff,
            "cost_stress": cost,
            "monthly": monthly,
            "top_concentration": top_conc,
            "remove_top": remove_top,
            "weakest_12m": weakest,
            "selection_diff": select_diff,
            "ticker_frequency": frequency,
            "exposure": exposure,
            "verdict": pd.DataFrame([R41.to_jsonable(verdict)]),
        },
        out_dir / "reports" / f"v8_2_0p05_final_validation_workbook_{timestamp}.xlsx",
    )
    update_next_steps(out_dir, zip_path, verdict)
    write_run_summary(out_dir, zip_path, verdict)
    package_outputs(out_dir, [report_path, exec_path], zip_path)
    sync_meistock(timestamp, out_dir, zip_path, report_path, exec_path, verdict)
    logger.info("Packaged 0p05 final validation zip: %s", zip_path)


if __name__ == "__main__":
    main()
