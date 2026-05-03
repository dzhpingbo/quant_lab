"""Run bounded v8.2 gate-aware reranking replay.

This script uses the already-generated v8.2 full score/rank audit trail. It
does not train a new model, expand the universe, run 31b, enter v9, add data
sources, or use audit_forward_* fields for ranking.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
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

from quant_lab.us_stock_selection.local_qlib_provider_builder import default_local_provider_uri
from quant_lab.us_stock_selection.portfolio_robustifier import ticker_contributions
from quant_lab.us_stock_selection.qlib_signal_backtest import compute_portfolio_metrics, portfolio_returns
from quant_lab.us_stock_selection.qlib_workflow_runner import load_close_from_provider
from quant_lab.us_stock_selection.utils import nav_from_returns, write_excel
from quant_lab.us_stock_selection.v8_1_gate_metrics import (
    annual_table_from_daily,
    leave_one_year_out_metrics,
    monthly_table_from_daily,
    rolling_12m_metrics,
    top_month_removed_metrics,
)


DEFAULT_BASELINE_RUN_DIR = PROJECT_ROOT / "outputs" / "us_stock_selection" / "run_20260426_095958"
DEFAULT_AUDIT_REPLAY_DIR = PROJECT_ROOT / "outputs" / "us_stock_selection" / "v8_2_bounded_audit_replay_20260501_113100"
OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "us_stock_selection"
DOCS_DIR = PROJECT_ROOT / "docs"
MEISTOCK_ROOT = Path("E:/dzhwork/obsydian/quant_lab/MeiStock")

BASELINE_CAGR = 0.6538182307494054
BASELINE_COST50_CAGR = 0.5608428724606129
BASELINE_CALMAR = 1.99152684432784
BASELINE_MAXDD = -0.32829998380969627
BASELINE_ALLOW_ENTER_V9 = False
SCORE_TOL = 1e-6
WEIGHT_TOL = 1e-12
HIGH_BETA_TICKERS = {"MSTR", "TQQQ", "QLD", "SOXL"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run bounded v8.2 gate-aware reranking replay.")
    parser.add_argument("--baseline-run-dir", type=Path, default=DEFAULT_BASELINE_RUN_DIR)
    parser.add_argument("--audit-replay-dir", type=Path, default=DEFAULT_AUDIT_REPLAY_DIR)
    parser.add_argument("--provider-uri", type=Path, default=default_local_provider_uri())
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--timestamp", default=None)
    parser.add_argument(
        "--candidate-list",
        default=(
            "baseline_original_rank,"
            "risk_adjusted_score_vol63_lambda_0p10,"
            "risk_adjusted_score_vol63_lambda_0p20,"
            "high_beta_penalty_0p10,"
            "high_beta_penalty_0p20,"
            "concentration_memory_penalty,"
            "regime_conditional_high_beta_penalty,"
            "simple_ensemble_penalty"
        ),
    )
    parser.add_argument("--sample-months", default="2024-10,2025-03,2025-10")
    parser.add_argument("--cost-bps", type=float, default=5.0)
    parser.add_argument("--slippage-bps", type=float, default=5.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--max-decision-dates", type=int, default=None)
    return parser.parse_args()


def setup_logger(out_dir: Path) -> logging.Logger:
    log_dir = out_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("v8_2_gate_aware_reranking")
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


def read_json(path: Path, required: bool = True) -> dict[str, Any]:
    if not path.exists():
        if required:
            raise FileNotFoundError(path)
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


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


def ensure_inputs(baseline_run_dir: Path, audit_replay_dir: Path) -> dict[str, Path]:
    paths = {
        "baseline_daily_nav": baseline_run_dir / "v8_paper_trading" / "daily_nav.csv",
        "baseline_holdings": baseline_run_dir / "v8_paper_trading" / "monthly_holdings.csv",
        "baseline_ledger": baseline_run_dir / "v8_paper_trading" / "monthly_decision_ledger.csv",
        "baseline_trades": baseline_run_dir / "v8_paper_trading" / "trades.csv",
        "baseline_metrics": baseline_run_dir / "v8_paper_trading" / "paper_trading_metrics.csv",
        "audit_trail": audit_replay_dir / "v8_2_full_score_rank_audit_trail.csv",
        "audit_quality": audit_replay_dir / "v8_2_full_audit_quality.csv",
        "selection_diff": audit_replay_dir / "v8_2_replay_vs_baseline_selection_diff.csv",
        "holdings_diff": audit_replay_dir / "v8_2_replay_vs_baseline_holdings_diff.csv",
        "readiness": audit_replay_dir / "v8_2_reranking_readiness_after_bounded_replay.json",
    }
    missing = [path for path in paths.values() if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing required input(s): " + "; ".join(str(p) for p in missing))
    return paths


def normalize_inputs(audit: pd.DataFrame, ledger: pd.DataFrame, holdings: pd.DataFrame, daily: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    a = audit.copy()
    a["decision_date"] = pd.to_datetime(a["decision_date"], errors="coerce")
    a["ticker"] = a["ticker"].astype(str).str.upper()
    for col in [
        "candidate_flag",
        "tradable_flag",
        "selected_flag",
        "high_beta_flag",
    ]:
        if col in a:
            a[col] = a[col].astype(str).str.lower().isin(["true", "1", "yes"])
    numeric_cols = [
        "raw_score",
        "adjusted_score",
        "raw_rank",
        "adjusted_rank",
        "trailing_63d_vol",
        "previous_selected_count_12m",
        "previous_avg_weight_12m",
        "previous_concentration_penalty",
    ]
    for col in numeric_cols:
        if col in a:
            a[col] = pd.to_numeric(a[col], errors="coerce")

    l = ledger.copy()
    for col in ["decision_date", "execution_date"]:
        l[col] = pd.to_datetime(l[col], errors="coerce")

    h = holdings.copy()
    for col in ["decision_date", "execution_date"]:
        h[col] = pd.to_datetime(h[col], errors="coerce")
    h["ticker"] = h["ticker"].astype(str).str.upper()
    h["weight"] = pd.to_numeric(h["weight"], errors="coerce")
    h["score"] = pd.to_numeric(h.get("score", np.nan), errors="coerce")

    d = daily.copy()
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    return a, l, h, d


def parse_candidate_list(raw: str) -> list[str]:
    candidates = [item.strip() for item in str(raw or "").split(",") if item.strip()]
    supported = set(candidate_registry().keys())
    unknown = [item for item in candidates if item not in supported]
    if unknown:
        raise ValueError("Unsupported rerank candidate(s): " + ", ".join(unknown))
    if "baseline_original_rank" not in candidates:
        candidates.insert(0, "baseline_original_rank")
    return list(dict.fromkeys(candidates))


def parse_sample_months(raw: str) -> list[str]:
    return [item.strip() for item in str(raw or "").split(",") if item.strip()]


def resolve_sample_decisions(ledger: pd.DataFrame, requested_months: list[str]) -> tuple[list[pd.Timestamp], pd.DataFrame]:
    local = ledger.dropna(subset=["decision_date"]).copy().sort_values("decision_date")
    local["month"] = local["decision_date"].dt.to_period("M").astype(str)
    decisions: list[pd.Timestamp] = []
    warnings: list[dict[str, Any]] = []
    for month in requested_months:
        exact = local.loc[local["month"] == month].head(1)
        if not exact.empty:
            decisions.append(pd.Timestamp(exact["decision_date"].iloc[0]))
            continue
        target = pd.Timestamp(f"{month}-15")
        nearest_idx = (local["decision_date"] - target).abs().sort_values().index[0]
        nearest_date = pd.Timestamp(local.loc[nearest_idx, "decision_date"])
        decisions.append(nearest_date)
        warnings.append(
            {
                "warning_type": "sample_month_resolution",
                "severity": "medium",
                "requested_month": month,
                "resolved_decision_date": date_str(nearest_date),
                "message": f"requested sample month {month} has no exact decision; using nearest valid decision date",
            }
        )
    return sorted(set(decisions)), pd.DataFrame(warnings)


def limit_dates(dates: list[pd.Timestamp], max_decision_dates: int | None) -> list[pd.Timestamp]:
    if max_decision_dates is None or max_decision_dates <= 0:
        return dates
    return dates[:max_decision_dates]


def candidate_registry() -> dict[str, dict[str, Any]]:
    return {
        "baseline_original_rank": {
            "description": "Original v8 raw score/rank, no penalties.",
            "fields": ["raw_score"],
            "status": "available",
        },
        "risk_adjusted_score_vol63_lambda_0p10": {
            "description": "Subtract 0.10 monthly zscore(trailing_63d_vol) from raw_score.",
            "fields": ["raw_score", "trailing_63d_vol"],
            "status": "available",
            "lambda": 0.10,
        },
        "risk_adjusted_score_vol63_lambda_0p20": {
            "description": "Subtract 0.20 monthly zscore(trailing_63d_vol) from raw_score.",
            "fields": ["raw_score", "trailing_63d_vol"],
            "status": "available",
            "lambda": 0.20,
        },
        "high_beta_penalty_0p10": {
            "description": "Subtract 0.10 for high_beta_flag names.",
            "fields": ["raw_score", "high_beta_flag"],
            "status": "available",
            "lambda": 0.10,
        },
        "high_beta_penalty_0p20": {
            "description": "Subtract 0.20 for high_beta_flag names.",
            "fields": ["raw_score", "high_beta_flag"],
            "status": "available",
            "lambda": 0.20,
        },
        "concentration_memory_penalty": {
            "description": "Subtract zscore penalties for previous 12m selected count and average weight.",
            "fields": ["raw_score", "previous_selected_count_12m", "previous_avg_weight_12m"],
            "status": "available",
        },
        "regime_conditional_high_beta_penalty": {
            "description": "Skipped unless ex-ante QQQ/SPY regime fields already exist in the audit trail.",
            "fields": ["raw_score", "high_beta_flag", "qqq_spy_regime"],
            "status": "conditional",
        },
        "simple_ensemble_penalty": {
            "description": "Subtract 0.10 vol zscore, 0.10 high-beta flag, and 0.05 previous selected-count zscore.",
            "fields": ["raw_score", "trailing_63d_vol", "high_beta_flag", "previous_selected_count_12m"],
            "status": "available",
        },
    }


def feature_type(feature: str) -> str:
    if feature.startswith("audit_forward_"):
        return "audit-only"
    if feature in {"raw_score", "raw_rank", "adjusted_rank", "adjusted_score"}:
        return "ex-ante-model-score"
    if feature.startswith("trailing_") or feature.startswith("previous_") or feature in {"high_beta_flag", "high_beta_group"}:
        return "ex-ante"
    if feature == "qqq_spy_regime":
        return "not_available_ex_ante"
    return "unknown"


def feature_usage_audit(candidates: list[str], audit: pd.DataFrame) -> pd.DataFrame:
    registry = candidate_registry()
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        spec = registry[candidate]
        for field in spec["fields"]:
            ftype = feature_type(field)
            exists = field in audit.columns
            allowed = bool(not field.startswith("audit_forward_") and exists)
            if field == "qqq_spy_regime":
                allowed = False
            rows.append(
                {
                    "rerank_candidate": candidate,
                    "feature_name": field,
                    "feature_type": ftype,
                    "used_in_ranking": bool(allowed and candidate != "regime_conditional_high_beta_penalty"),
                    "allowed": allowed,
                    "reason": "available ex-ante field"
                    if allowed
                    else ("audit-only fields forbidden" if field.startswith("audit_forward_") else "field not available in audit trail"),
                }
            )
    forward_used = [r for r in rows if str(r["feature_name"]).startswith("audit_forward_") and r["used_in_ranking"]]
    if forward_used:
        raise RuntimeError("audit_forward_* field detected in ranking feature usage")
    return pd.DataFrame(rows)


def zscore_by_month(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    mean = values.mean()
    std = values.std(ddof=0)
    if pd.isna(std) or std <= 1e-12:
        return pd.Series(0.0, index=series.index)
    return ((values - mean) / std).fillna(0.0)


def score_direction_check(audit: pd.DataFrame, ledger: pd.DataFrame) -> dict[str, Any]:
    rows = []
    max_score_diff = 0.0
    selected_equals_highest = True
    selected_equals_lowest = True
    rank_consistent = True
    for decision_date, group in audit.groupby("decision_date"):
        tradable = group.loc[group["tradable_flag"].astype(bool)].copy()
        selected = tradable.loc[tradable["selected_flag"].astype(bool)].copy()
        highest = tradable.sort_values("raw_score", ascending=False).head(5)["ticker"].tolist()
        lowest = tradable.sort_values("raw_score", ascending=True).head(5)["ticker"].tolist()
        selected_tickers = selected.sort_values("selected_rank")["ticker"].tolist()
        selected_equals_highest &= selected_tickers == highest
        selected_equals_lowest &= selected_tickers == lowest
        rank_order = tradable.sort_values("raw_score", ascending=False)["ticker"].tolist()
        raw_rank_order = tradable.sort_values("raw_rank", ascending=True)["ticker"].tolist()
        rank_consistent &= rank_order == raw_rank_order
        base = ledger.loc[ledger["decision_date"] == decision_date].head(1)
        if not base.empty:
            baseline_scores = parse_selected_scores(base.iloc[0].get("selected_scores"))
            for ticker, score in baseline_scores.items():
                found = selected.loc[selected["ticker"] == ticker, "raw_score"]
                if not found.empty:
                    max_score_diff = max(max_score_diff, abs(float(found.iloc[0]) - float(score)))
        rows.append(
            {
                "decision_date": date_str(decision_date),
                "selected_equals_highest_score_top5": selected_tickers == highest,
                "selected_equals_lowest_score_top5": selected_tickers == lowest,
            }
        )
    lower_score_is_better = bool(selected_equals_lowest and not selected_equals_highest)
    score_sort_ascending = bool(lower_score_is_better)
    return {
        "score_sort_ascending": score_sort_ascending,
        "lower_score_is_better": lower_score_is_better,
        "higher_score_is_better": bool(selected_equals_highest),
        "selected_equals_lowest_score_top5": bool(selected_equals_lowest),
        "selected_equals_highest_score_top5": bool(selected_equals_highest),
        "max_score_diff_vs_baseline": float(max_score_diff),
        "rank_consistency_pass": bool(rank_consistent and selected_equals_highest and max_score_diff <= SCORE_TOL),
        "per_decision_rows": rows,
    }


def parse_selected_scores(raw: Any) -> dict[str, float]:
    out: dict[str, float] = {}
    for part in str(raw or "").split(";"):
        if ":" not in part:
            continue
        ticker, value = part.split(":", 1)
        try:
            out[ticker.strip().upper()] = float(value)
        except ValueError:
            out[ticker.strip().upper()] = np.nan
    return out


def parse_tickers(raw: Any) -> list[str]:
    return [item.strip().upper() for item in str(raw or "").split(",") if item.strip()]


def candidate_available(candidate: str, audit: pd.DataFrame) -> tuple[bool, str]:
    if candidate == "regime_conditional_high_beta_penalty":
        return False, "No pre-existing QQQ/SPY regime field is present in the full audit trail."
    required = [field for field in candidate_registry()[candidate]["fields"] if field != "raw_score"]
    missing = [field for field in required if field not in audit.columns]
    if missing:
        return False, "Missing required field(s): " + ",".join(missing)
    return True, ""


def adjusted_scores(candidate: str, group: pd.DataFrame) -> pd.Series:
    score = pd.to_numeric(group["raw_score"], errors="coerce").copy()
    if candidate == "baseline_original_rank":
        return score
    if candidate == "risk_adjusted_score_vol63_lambda_0p10":
        return score - 0.10 * zscore_by_month(group["trailing_63d_vol"])
    if candidate == "risk_adjusted_score_vol63_lambda_0p20":
        return score - 0.20 * zscore_by_month(group["trailing_63d_vol"])
    if candidate == "high_beta_penalty_0p10":
        return score - 0.10 * group["high_beta_flag"].astype(float)
    if candidate == "high_beta_penalty_0p20":
        return score - 0.20 * group["high_beta_flag"].astype(float)
    if candidate == "concentration_memory_penalty":
        return score - 0.10 * zscore_by_month(group["previous_selected_count_12m"]) - 0.10 * zscore_by_month(group["previous_avg_weight_12m"])
    if candidate == "simple_ensemble_penalty":
        return (
            score
            - 0.10 * zscore_by_month(group["trailing_63d_vol"])
            - 0.10 * group["high_beta_flag"].astype(float)
            - 0.05 * zscore_by_month(group["previous_selected_count_12m"])
        )
    raise ValueError(f"Candidate is not available for adjusted scoring: {candidate}")


def build_reranking_selection(
    audit: pd.DataFrame,
    ledger: pd.DataFrame,
    candidates: list[str],
    decision_dates: list[pd.Timestamp],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    selection_rows: list[dict[str, Any]] = []
    score_rows: list[pd.DataFrame] = []
    skipped: list[dict[str, Any]] = []
    execution_map = ledger.set_index("decision_date")["execution_date"].to_dict()
    for candidate in candidates:
        ok, reason = candidate_available(candidate, audit)
        if not ok:
            skipped.append({"rerank_candidate": candidate, "status": "skipped", "reason": reason})
            continue
        for decision_date in decision_dates:
            group = audit.loc[(audit["decision_date"] == decision_date) & audit["tradable_flag"].astype(bool)].copy()
            if group.empty:
                skipped.append({"rerank_candidate": candidate, "decision_date": date_str(decision_date), "status": "skipped", "reason": "no tradable candidates"})
                continue
            group["rerank_candidate"] = candidate
            group["adjusted_score_replay"] = adjusted_scores(candidate, group)
            group["adjusted_rank_replay"] = group["adjusted_score_replay"].rank(method="first", ascending=False).astype(int)
            group["selected_flag_replay"] = group["adjusted_rank_replay"] <= 5
            score_rows.append(
                group[
                    [
                        "rerank_candidate",
                        "decision_date",
                        "ticker",
                        "raw_score",
                        "raw_rank",
                        "adjusted_score_replay",
                        "adjusted_rank_replay",
                        "selected_flag_replay",
                        "trailing_63d_vol",
                        "high_beta_flag",
                        "previous_selected_count_12m",
                        "previous_avg_weight_12m",
                    ]
                ].copy()
            )
            selected = group.loc[group["selected_flag_replay"]].sort_values("adjusted_rank_replay")
            execution_date = pd.Timestamp(execution_map[decision_date])
            for rank, item in enumerate(selected.itertuples(index=False), start=1):
                selection_rows.append(
                    {
                        "rerank_candidate": candidate,
                        "decision_date": date_str(decision_date),
                        "execution_date": date_str(execution_date),
                        "ticker": item.ticker,
                        "selected_rank": rank,
                        "weight": 0.20,
                        "raw_score": float(item.raw_score),
                        "adjusted_score": float(item.adjusted_score_replay),
                        "raw_rank": int(item.raw_rank),
                        "adjusted_rank": int(item.adjusted_rank_replay),
                    }
                )
    selection = pd.DataFrame(selection_rows)
    score_rank = pd.concat(score_rows, ignore_index=True) if score_rows else pd.DataFrame()
    skipped_df = pd.DataFrame(skipped)
    return selection, score_rank, skipped_df


def validate_sample_selection(selection: pd.DataFrame, score_rank: pd.DataFrame, baseline_ledger: pd.DataFrame, candidates: list[str]) -> tuple[pd.DataFrame, dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    available = sorted(selection["rerank_candidate"].unique().tolist()) if not selection.empty else []
    for candidate in available:
        sub = selection.loc[selection["rerank_candidate"] == candidate].copy()
        for decision_date, group in sub.groupby("decision_date"):
            duplicate_keys = int(group.duplicated(["decision_date", "ticker"]).sum())
            selected_count = int(len(group))
            score_sub = score_rank.loc[
                (score_rank["rerank_candidate"] == candidate)
                & (pd.to_datetime(score_rank["decision_date"]).dt.date.astype(str) == str(decision_date))
            ]
            selected_from_universe = bool(set(group["ticker"]).issubset(set(score_sub["ticker"])))
            adjusted_non_null_rate = float(score_sub["adjusted_score_replay"].notna().mean()) if not score_sub.empty else 0.0
            baseline_match = True
            if candidate == "baseline_original_rank":
                base = baseline_ledger.loc[baseline_ledger["decision_date"] == pd.Timestamp(decision_date)].head(1)
                baseline_match = bool(
                    not base.empty and group.sort_values("selected_rank")["ticker"].tolist() == parse_tickers(base.iloc[0].get("selected_tickers"))
                )
            quality_pass = bool(
                selected_count == 5
                and duplicate_keys == 0
                and selected_from_universe
                and adjusted_non_null_rate >= 0.95
                and baseline_match
            )
            rows.append(
                {
                    "rerank_candidate": candidate,
                    "decision_date": decision_date,
                    "selected_count": selected_count,
                    "duplicate_key_count": duplicate_keys,
                    "selected_from_candidate_universe": selected_from_universe,
                    "adjusted_score_non_null_rate": adjusted_non_null_rate,
                    "baseline_original_rank_reproduced": baseline_match,
                    "audit_forward_fields_used": False,
                    "quality_pass": quality_pass,
                }
            )
    quality = pd.DataFrame(rows)
    summary = {
        "candidate_count": len(available),
        "quality_pass_all": bool(not quality.empty and quality["quality_pass"].all()),
        "baseline_original_rank_reproduced": bool(
            not quality.loc[quality["rerank_candidate"] == "baseline_original_rank"].empty
            and quality.loc[quality["rerank_candidate"] == "baseline_original_rank", "baseline_original_rank_reproduced"].all()
        ),
        "audit_forward_fields_used": False,
        "skipped_candidates": [c for c in candidates if c not in available],
    }
    return quality, summary


def selection_diff_vs_baseline(selection: pd.DataFrame, baseline_ledger: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if selection.empty:
        return pd.DataFrame()
    for (candidate, decision_date), group in selection.groupby(["rerank_candidate", "decision_date"]):
        base = baseline_ledger.loc[baseline_ledger["decision_date"] == pd.Timestamp(decision_date)].head(1)
        baseline_tickers = parse_tickers(base.iloc[0].get("selected_tickers")) if not base.empty else []
        replay_tickers = group.sort_values("selected_rank")["ticker"].tolist()
        overlap = len(set(baseline_tickers) & set(replay_tickers))
        rows.append(
            {
                "rerank_candidate": candidate,
                "decision_date": decision_date,
                "baseline_selected_tickers": ",".join(baseline_tickers),
                "rerank_selected_tickers": ",".join(replay_tickers),
                "selected_tickers_match": baseline_tickers == replay_tickers,
                "overlap_count": overlap,
                "changed_count": 5 - overlap if baseline_tickers else np.nan,
            }
        )
    return pd.DataFrame(rows)


def build_weights_from_selection(selection: pd.DataFrame, close: pd.DataFrame) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    for candidate, group in selection.groupby("rerank_candidate"):
        weights = pd.DataFrame(np.nan, index=close.index, columns=close.columns, dtype=float)
        for execution_date, exec_group in group.groupby("execution_date"):
            date = pd.Timestamp(execution_date)
            if date not in weights.index:
                pos = weights.index.searchsorted(date, side="left")
                if pos >= len(weights.index):
                    continue
                date = pd.Timestamp(weights.index[pos])
            current = pd.Series(0.0, index=weights.columns)
            for item in exec_group.itertuples(index=False):
                if item.ticker in current.index:
                    current[item.ticker] = float(item.weight)
            weights.loc[date] = current
        out[candidate] = weights.ffill().fillna(0.0)
    return out


def evaluate_candidate(candidate: str, close: pd.DataFrame, weights: pd.DataFrame, cost_bps: float, slippage_bps: float) -> dict[str, Any]:
    weights = weights.reindex(close.index).ffill().fillna(0.0).loc[:, close.columns]
    returns, turnover = portfolio_returns(close, weights, cost_bps=cost_bps, slippage_bps=slippage_bps)
    cost50_returns, cost50_turnover = portfolio_returns(close, weights, cost_bps=50.0, slippage_bps=slippage_bps)
    nocost_returns, nocost_turnover = portfolio_returns(close, weights, cost_bps=0.0, slippage_bps=0.0)
    metrics = compute_portfolio_metrics(returns, turnover, weights)
    cost50_metrics = compute_portfolio_metrics(cost50_returns, cost50_turnover, weights)
    nocost_metrics = compute_portfolio_metrics(nocost_returns, nocost_turnover, weights)
    nav = nav_from_returns(returns)
    cost50_nav = nav_from_returns(cost50_returns)
    daily = pd.DataFrame(
        {
            "rerank_candidate": candidate,
            "date": returns.index,
            "return": returns.values,
            "nav": nav.values,
            "turnover": turnover.reindex(returns.index).values,
            "cost50_return": cost50_returns.reindex(returns.index).values,
            "cost50_nav": cost50_nav.reindex(returns.index).values,
            "nocost_return": nocost_returns.reindex(returns.index).values,
        }
    )
    daily_metrics = daily[["date", "return", "nav", "turnover"]].copy()
    annual = annual_table_from_daily(daily_metrics)
    monthly = monthly_table_from_daily(daily_metrics)
    loo = leave_one_year_out_metrics(daily_metrics)
    removed = top_month_removed_metrics(daily_metrics, monthly)
    rolling = rolling_12m_metrics(daily_metrics)
    top_summary = top_month_sensitivity(monthly, removed)
    rolling_summary = rolling_summary_row(rolling)
    ticker_summary = ticker_concentration(close, weights)
    exposure = exposure_metrics(weights)
    weak = weakest_12m_metrics(daily, rolling, cost_bps=50.0)
    trade_count = int((weights.diff().fillna(weights).abs() > WEIGHT_TOL).sum().sum())
    full_row = {
        "rerank_candidate": candidate,
        **metrics,
        "nocost_cagr": nocost_metrics.get("cagr"),
        "nocost_calmar": nocost_metrics.get("calmar"),
        "cost50_cagr": cost50_metrics.get("cagr"),
        "cost50_calmar": cost50_metrics.get("calmar"),
        "trade_count": trade_count,
        "avg_gross_exposure": exposure["avg_gross_exposure"],
        "min_gross_exposure": exposure["min_gross_exposure"],
        "max_gross_exposure": exposure["max_gross_exposure"],
        "avg_cash_share": exposure["avg_cash_share"],
        "max_cash_share": exposure["max_cash_share"],
        "gross_exposure_anomaly": exposure["gross_exposure_anomaly"],
        "leave_one_year_out_min_cagr": float(loo["cagr"].min()) if not loo.empty else np.nan,
        "leave_one_year_out_min_calmar": float(loo["calmar"].min()) if not loo.empty else np.nan,
        "leave_one_year_out_pass_cagr_20": bool(not loo.empty and loo["cagr"].min() >= 0.20),
        "leave_one_year_out_pass_calmar_1": bool(not loo.empty and loo["calmar"].min() >= 1.0),
        **rolling_summary,
        **top_summary,
        **ticker_summary,
        **weak,
    }
    return {
        "metrics": full_row,
        "daily": daily,
        "annual": annual.assign(rerank_candidate=candidate) if not annual.empty else annual,
        "monthly": monthly.assign(rerank_candidate=candidate) if not monthly.empty else monthly,
        "loo": loo.assign(rerank_candidate=candidate) if not loo.empty else loo,
        "removed": removed.assign(rerank_candidate=candidate) if not removed.empty else removed,
        "rolling": rolling.assign(rerank_candidate=candidate) if not rolling.empty else rolling,
        "ticker_concentration": pd.DataFrame([{**ticker_summary, "rerank_candidate": candidate}]),
        "weakest": pd.DataFrame([{**weak, "rerank_candidate": candidate}]),
        "weights": weights,
        "trades": trades_from_weights(candidate, weights, close),
    }


def top_month_sensitivity(monthly: pd.DataFrame, removed: pd.DataFrame) -> dict[str, Any]:
    top_pos = monthly.loc[monthly["monthly_profit"] > 0].sort_values("monthly_profit", ascending=False)
    out = {
        "top1_positive_month_share": float(top_pos["positive_profit_share"].head(1).sum()) if not top_pos.empty else np.nan,
        "top3_positive_month_share": float(top_pos["positive_profit_share"].head(3).sum()) if not top_pos.empty else np.nan,
        "top5_positive_month_share": float(top_pos["positive_profit_share"].head(5).sum()) if not top_pos.empty else np.nan,
    }
    for n in [1, 3, 5]:
        sub = removed.loc[removed["removed_top_positive_month_count"] == n] if not removed.empty else pd.DataFrame()
        out[f"remove_top{n}_month_cagr"] = float(sub["cagr"].iloc[0]) if not sub.empty else np.nan
        out[f"remove_top{n}_month_calmar"] = float(sub["calmar"].iloc[0]) if not sub.empty else np.nan
        out[f"remove_top{n}_months"] = str(sub["removed_months"].iloc[0]) if not sub.empty else ""
    return out


def rolling_summary_row(rolling: pd.DataFrame) -> dict[str, Any]:
    if rolling.empty:
        return {
            "rolling_12m_min_return": np.nan,
            "rolling_12m_min_calmar_like": np.nan,
            "rolling_12m_max_return": np.nan,
            "rolling_12m_return_gap": np.nan,
            "weakest_12m_window": "",
            "strongest_12m_window": "",
        }
    weakest = rolling.sort_values("window_return", ascending=True).iloc[0]
    strongest = rolling.sort_values("window_return", ascending=False).iloc[0]
    return {
        "rolling_12m_min_return": float(rolling["window_return"].min()),
        "rolling_12m_min_calmar_like": float(rolling["calmar_like"].min()),
        "rolling_12m_max_return": float(rolling["window_return"].max()),
        "rolling_12m_return_gap": float(rolling["window_return"].max() - rolling["window_return"].min()),
        "weakest_12m_window": f"{weakest['start_month']}:{weakest['end_month']}",
        "strongest_12m_window": f"{strongest['start_month']}:{strongest['end_month']}",
    }


def ticker_concentration(close: pd.DataFrame, weights: pd.DataFrame) -> dict[str, Any]:
    contrib = ticker_contributions(close, weights)
    top_ticker = str(contrib.iloc[0]["ticker"]) if not contrib.empty else ""
    monthly_active = (weights.abs().groupby(weights.index.to_period("M")).max() > WEIGHT_TOL)
    active_months = monthly_active.any(axis=1)
    top_count_share = (
        float(monthly_active.loc[active_months, top_ticker].mean())
        if top_ticker in monthly_active.columns and active_months.any()
        else 0.0
    )
    high_beta_cols = [col for col in weights.columns if str(col).upper() in HIGH_BETA_TICKERS]
    high_beta_weight = weights[high_beta_cols].sum(axis=1) if high_beta_cols else pd.Series(0.0, index=weights.index)
    active = weights.abs().sum(axis=1) > WEIGHT_TOL
    return {
        "top_ticker": top_ticker,
        "max_ticker_abs_share": float(contrib["abs_share"].max()) if not contrib.empty else 0.0,
        "max_ticker_month_weight": float(weights.max().max()) if not weights.empty else 0.0,
        "top_ticker_exposure_count_share": top_count_share,
        "avg_high_beta_weight_share": float(high_beta_weight.loc[active].mean()) if active.any() else 0.0,
        "max_high_beta_weight_share": float(high_beta_weight.max()) if not high_beta_weight.empty else 0.0,
    }


def exposure_metrics(weights: pd.DataFrame) -> dict[str, Any]:
    gross = weights.abs().sum(axis=1)
    active = gross > WEIGHT_TOL
    active_gross = gross.loc[active]
    cash = (1.0 - gross).clip(lower=0.0)
    return {
        "avg_gross_exposure": float(gross.mean()) if not gross.empty else 0.0,
        "min_gross_exposure": float(active_gross.min()) if not active_gross.empty else 0.0,
        "max_gross_exposure": float(gross.max()) if not gross.empty else 0.0,
        "avg_cash_share": float(cash.loc[active].mean()) if active.any() else 0.0,
        "max_cash_share": float(cash.loc[active].max()) if active.any() else 0.0,
        "gross_exposure_anomaly": bool((gross.max() > 1.000001) or (not active_gross.empty and active_gross.min() < 0.999)),
    }


def weakest_12m_metrics(daily: pd.DataFrame, rolling: pd.DataFrame, cost_bps: float) -> dict[str, Any]:
    if rolling.empty:
        return {
            "weakest_12m_CAGR": np.nan,
            "weakest_12m_50bps_CAGR": np.nan,
            "weakest_12m_MaxDD": np.nan,
            "weakest_12m_Calmar": np.nan,
            "weakest_12m_top3_positive_month_share": np.nan,
        }
    weakest = rolling.sort_values("window_return", ascending=True).iloc[0]
    start = pd.Period(str(weakest["start_month"]), freq="M")
    end = pd.Period(str(weakest["end_month"]), freq="M")
    local = daily.loc[daily["date"].dt.to_period("M").between(start, end)].copy()
    if local.empty:
        return {}
    returns = local.set_index("date")["return"]
    turnover = local.set_index("date")["turnover"]
    weights_stub = pd.DataFrame({"gross": 1.0}, index=returns.index)
    metrics = compute_portfolio_metrics(returns, turnover, weights_stub)
    cost50_returns = local.set_index("date")["cost50_return"]
    cost50_metrics = compute_portfolio_metrics(cost50_returns, turnover, weights_stub)
    monthly = monthly_table_from_daily(local[["date", "return", "nav", "turnover"]])
    top_pos = monthly.loc[monthly["monthly_profit"] > 0].sort_values("monthly_profit", ascending=False)
    return {
        "weakest_12m_CAGR": metrics.get("cagr"),
        "weakest_12m_50bps_CAGR": cost50_metrics.get("cagr"),
        "weakest_12m_MaxDD": metrics.get("max_drawdown"),
        "weakest_12m_Calmar": metrics.get("calmar"),
        "weakest_12m_top3_positive_month_share": float(top_pos["positive_profit_share"].head(3).sum()) if not top_pos.empty else np.nan,
    }


def trades_from_weights(candidate: str, weights: pd.DataFrame, close: pd.DataFrame) -> pd.DataFrame:
    delta = weights.diff().fillna(weights)
    rows: list[dict[str, Any]] = []
    for date, row in delta.iterrows():
        changed = row.loc[row.abs() > WEIGHT_TOL]
        for ticker, delta_weight in changed.items():
            rows.append(
                {
                    "rerank_candidate": candidate,
                    "date": date_str(date),
                    "ticker": ticker,
                    "delta_weight": float(delta_weight),
                    "target_weight": float(weights.loc[date, ticker]),
                    "price": float(close.loc[date, ticker]) if ticker in close.columns and pd.notna(close.loc[date, ticker]) else np.nan,
                }
            )
    return pd.DataFrame(rows)


def holdings_long(weights_by_candidate: dict[str, pd.DataFrame]) -> pd.DataFrame:
    parts = []
    for candidate, weights in weights_by_candidate.items():
        stacked = weights.stack().rename("weight").reset_index()
        stacked.columns = ["date", "ticker", "weight"]
        stacked = stacked.loc[stacked["weight"].abs() > WEIGHT_TOL].copy()
        stacked.insert(0, "rerank_candidate", candidate)
        stacked["date"] = pd.to_datetime(stacked["date"]).dt.date.astype(str)
        parts.append(stacked)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def gate_results(metrics: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    baseline = metrics.loc[metrics["rerank_candidate"] == "baseline_original_rank"].head(1)
    baseline_top3 = float(baseline["top3_positive_month_share"].iloc[0]) if not baseline.empty else np.nan
    baseline_ticker = float(baseline["max_ticker_abs_share"].iloc[0]) if not baseline.empty else np.nan
    for item in metrics.to_dict(orient="records"):
        candidate = str(item["rerank_candidate"])
        if candidate == "baseline_original_rank":
            rows.append(
                {
                    "rerank_candidate": candidate,
                    "gate_group": "baseline_control",
                    "gate_name": "baseline_reproduction_control",
                    "pass_fail": "pass",
                }
            )
            continue
        accepted_checks = {
            "full_period_cagr_ge_20": item.get("cagr", -999) >= 0.20,
            "full_period_50bps_cagr_ge_20": item.get("cost50_cagr", -999) >= 0.20,
            "full_period_calmar_ge_1": item.get("calmar", -999) >= 1.0,
            "full_period_calmar_ge_80pct_v8": item.get("calmar", -999) >= BASELINE_CALMAR * 0.80,
            "full_period_50bps_cagr_ge_80pct_v8": item.get("cost50_cagr", -999) >= BASELINE_COST50_CAGR * 0.80,
            "maxdd_not_significantly_worse_than_v8": abs(item.get("max_drawdown", 999)) <= abs(BASELINE_MAXDD) * 1.05,
            "leave_one_year_out_min_cagr_ge_20": item.get("leave_one_year_out_min_cagr", -999) >= 0.20,
            "leave_one_year_out_min_calmar_ge_1": item.get("leave_one_year_out_min_calmar", -999) >= 1.0,
            "top1_positive_month_share_lte_25": item.get("top1_positive_month_share", 999) <= 0.25,
            "top3_positive_month_share_lte_50": item.get("top3_positive_month_share", 999) <= 0.50,
            "max_ticker_abs_share_lte_30": item.get("max_ticker_abs_share", 999) <= 0.30,
            "max_ticker_month_weight_lte_30": item.get("max_ticker_month_weight", 999) <= 0.30,
            "gross_exposure_normal": not bool(item.get("gross_exposure_anomaly", True)),
            "no_future_function": True,
            "simple_explainable_rule": True,
        }
        accepted = bool(all(accepted_checks.values()))
        strong_checks = {
            "accepted_candidate_needs_human_review": accepted,
            "full_period_calmar_ge_v8": item.get("calmar", -999) >= BASELINE_CALMAR,
            "full_period_50bps_cagr_ge_90pct_v8": item.get("cost50_cagr", -999) >= BASELINE_COST50_CAGR * 0.90,
            "weakest_12m_calmar_ge_1": item.get("weakest_12m_Calmar", -999) >= 1.0,
            "weakest_12m_50bps_cagr_ge_20": item.get("weakest_12m_50bps_CAGR", -999) >= 0.20,
            "weakest_12m_top3_share_below_baseline": item.get("weakest_12m_top3_positive_month_share", 999) < baseline_top3,
            "top_month_sensitivity_not_worse": item.get("top3_positive_month_share", 999) <= baseline_top3,
            "ticker_concentration_not_worse": item.get("max_ticker_abs_share", 999) <= baseline_ticker,
        }
        strong = bool(all(strong_checks.values()))
        for gate, passed in accepted_checks.items():
            rows.append({"rerank_candidate": candidate, "gate_group": "accepted", "gate_name": gate, "pass_fail": "pass" if passed else "fail"})
        rows.append({"rerank_candidate": candidate, "gate_group": "accepted", "gate_name": "accepted_candidate_needs_human_review", "pass_fail": "pass" if accepted else "fail"})
        for gate, passed in strong_checks.items():
            rows.append({"rerank_candidate": candidate, "gate_group": "strong", "gate_name": gate, "pass_fail": "pass" if passed else "fail"})
        rows.append({"rerank_candidate": candidate, "gate_group": "strong", "gate_name": "strong_candidate", "pass_fail": "pass" if strong else "fail"})
    gates = pd.DataFrame(rows)
    status_rows = []
    for candidate, group in gates.groupby("rerank_candidate"):
        if candidate == "baseline_original_rank":
            accepted = False
            strong = False
            status = "baseline_control"
        else:
            accepted = bool(((group["gate_name"] == "accepted_candidate_needs_human_review") & (group["pass_fail"] == "pass")).any())
            strong = bool(((group["gate_name"] == "strong_candidate") & (group["pass_fail"] == "pass")).any())
            status = "strong_candidate" if strong else ("accepted_candidate_needs_human_review" if accepted else "diagnostic_only_or_rejected")
        status_rows.append({"rerank_candidate": candidate, "accepted_candidate_needs_human_review": accepted, "strong_candidate": strong, "candidate_status": status})
    return gates, pd.DataFrame(status_rows)


def load_close_for_replay(provider_uri: Path, audit: pd.DataFrame, baseline_daily: pd.DataFrame, logger: logging.Logger) -> pd.DataFrame:
    tickers = sorted(audit["ticker"].astype(str).str.upper().unique().tolist())
    start = date_str(pd.to_datetime(baseline_daily["date"]).min())
    end = date_str(pd.to_datetime(baseline_daily["date"]).max())
    logger.info("Loading close panel for reranking replay: %s tickers, %s to %s", len(tickers), start, end)
    close = load_close_from_provider(provider_uri, tickers=tickers, start=start, end=end).ffill()
    close = close.loc[(close.index >= pd.Timestamp(start)) & (close.index <= pd.Timestamp(end)), close.columns.intersection(tickers)].ffill()
    return close


def run_replay(
    selection: pd.DataFrame,
    close: pd.DataFrame,
    cost_bps: float,
    slippage_bps: float,
    logger: logging.Logger,
) -> dict[str, Any]:
    weights_by_candidate = build_weights_from_selection(selection, close)
    results = {}
    for candidate, weights in weights_by_candidate.items():
        logger.info("Evaluating rerank candidate=%s", candidate)
        results[candidate] = evaluate_candidate(candidate, close, weights, cost_bps=cost_bps, slippage_bps=slippage_bps)
    metrics = pd.DataFrame([result["metrics"] for result in results.values()])
    daily = pd.concat([result["daily"] for result in results.values()], ignore_index=True) if results else pd.DataFrame()
    trades = pd.concat([result["trades"] for result in results.values()], ignore_index=True) if results else pd.DataFrame()
    loo = pd.concat([result["loo"] for result in results.values()], ignore_index=True) if results else pd.DataFrame()
    removed = pd.concat([result["removed"] for result in results.values()], ignore_index=True) if results else pd.DataFrame()
    rolling = pd.concat([result["rolling"] for result in results.values()], ignore_index=True) if results else pd.DataFrame()
    ticker = pd.concat([result["ticker_concentration"] for result in results.values()], ignore_index=True) if results else pd.DataFrame()
    weakest = pd.concat([result["weakest"] for result in results.values()], ignore_index=True) if results else pd.DataFrame()
    holdings = holdings_long(weights_by_candidate)
    gates, statuses = gate_results(metrics) if not metrics.empty else (pd.DataFrame(), pd.DataFrame())
    metrics = metrics.merge(statuses, on="rerank_candidate", how="left") if not metrics.empty and not statuses.empty else metrics
    return {
        "weights_by_candidate": weights_by_candidate,
        "metrics": metrics,
        "daily": daily,
        "holdings": holdings,
        "trades": trades,
        "loo": loo,
        "top_month": removed,
        "rolling": rolling,
        "ticker": ticker,
        "weakest": weakest,
        "gates": gates,
        "statuses": statuses,
    }


def build_verdict(metrics: pd.DataFrame, sample_summary: dict[str, Any], full_executed: bool) -> dict[str, Any]:
    accepted = []
    strong = []
    if not metrics.empty and "accepted_candidate_needs_human_review" in metrics:
        non_baseline = metrics.loc[metrics["rerank_candidate"] != "baseline_original_rank"].copy()
        accepted = non_baseline.loc[non_baseline["accepted_candidate_needs_human_review"].astype(bool), "rerank_candidate"].tolist()
        strong = non_baseline.loc[non_baseline["strong_candidate"].astype(bool), "rerank_candidate"].tolist()
    return {
        "cycle": "v8_2_bounded_gate_aware_reranking_replay",
        "sample_completed": True,
        "sample_passed": bool(sample_summary.get("quality_pass_all")),
        "full_completed": bool(full_executed),
        "accepted_candidates": accepted,
        "strong_candidates": strong,
        "has_accepted_candidate": bool(accepted),
        "has_strong_candidate": bool(strong),
        "replace_v8_best": False,
        "allow_enter_v9": False,
        "reason": "Reranking replay is diagnostic. User/ChatGPT approval is required before any best replacement or v9 transition.",
    }


def write_reports(
    timestamp: str,
    out_dir: Path,
    zip_path: Path,
    score_direction: dict[str, Any],
    feature_usage: pd.DataFrame,
    sample_summary: dict[str, Any],
    sample_quality: pd.DataFrame,
    full_metrics: pd.DataFrame,
    weakest: pd.DataFrame,
    gates: pd.DataFrame,
    verdict: dict[str, Any],
) -> tuple[Path, Path]:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = DOCS_DIR / f"US_STOCK_SELECTION_V8_2_GATE_AWARE_RERANKING_REPLAY_{timestamp}.md"
    exec_path = DOCS_DIR / f"US_STOCK_SELECTION_V8_2_RERANKING_EXEC_SUMMARY_{timestamp}.md"
    report = f"""# US Stock Selection v8.2 Gate-Aware Reranking Replay

## 1. Background And Purpose

v8 baseline remains the current best. This run tests a small, pre-registered set of ex-ante reranking rules using the full candidate score/rank audit trail generated by bounded audit replay.

## 2. Why Bounded Reranking Is Now Allowed

Readiness from bounded audit replay is true: full candidate universe, unselected tickers, raw scores/ranks, selected_flag validation, ex-ante risk features, and baseline reproduction are available.

## 3. Inputs

- Baseline v8 run: `outputs/us_stock_selection/run_20260426_095958`
- Audit replay run: `outputs/us_stock_selection/v8_2_bounded_audit_replay_20260501_113100`

## 4. Score Direction

```json
{json.dumps(to_jsonable(score_direction), indent=2, ensure_ascii=False)}
```

## 5. Forward Field Isolation

No `audit_forward_` field was used in ranking. Feature usage:

{table_to_markdown(feature_usage, max_rows=80)}

## 6. Reranking Candidates

Candidates are limited to baseline_original_rank, two vol63 penalties, two high-beta penalties, concentration memory, skipped regime conditional, and simple ensemble. No grid search was run.

## 7. Sample Replay Result

```json
{json.dumps(to_jsonable(sample_summary), indent=2, ensure_ascii=False)}
```

{table_to_markdown(sample_quality, max_rows=40)}

## 8. Full Replay Result

{table_to_markdown(full_metrics, max_rows=40, columns=['rerank_candidate','cagr','cost50_cagr','calmar','cost50_calmar','max_drawdown','leave_one_year_out_min_cagr','leave_one_year_out_min_calmar','top3_positive_month_share','max_ticker_abs_share','avg_high_beta_weight_share','candidate_status'])}

## 9. Baseline Comparison

v8 baseline remains best until explicitly replaced by the user. `replace_v8_best` is `False`.

## 10. Weakest 12M Comparison

{table_to_markdown(weakest, max_rows=40)}

## 11. Concentration And Stability Gates

{table_to_markdown(gates, max_rows=120)}

## 12. Accepted / Strong Candidate

```json
{json.dumps(to_jsonable(verdict), indent=2, ensure_ascii=False)}
```

## 13. v9

`allow_enter_v9` remains `False`.

## 14. Next Step

Pause for user/ChatGPT decision. Do not automatically replace v8 baseline and do not enter v9.

## Outputs

- Output directory: `{out_dir}`
- Zip: `{zip_path}`
"""
    exec_summary = f"""# US Stock Selection v8.2 Reranking Exec Summary

- Sample completed: `True`
- Sample passed: `{sample_summary.get('quality_pass_all')}`
- Full completed: `{verdict.get('full_completed')}`
- Accepted candidates: `{', '.join(verdict.get('accepted_candidates', [])) or 'None'}`
- Strong candidates: `{', '.join(verdict.get('strong_candidates', [])) or 'None'}`
- Replace v8 best: `False`
- Allow enter v9: `False`

## Top Metrics

{table_to_markdown(full_metrics, max_rows=20, columns=['rerank_candidate','cagr','cost50_cagr','calmar','max_drawdown','top3_positive_month_share','max_ticker_abs_share','candidate_status'])}
"""
    report_path.write_text(report, encoding="utf-8")
    exec_path.write_text(exec_summary, encoding="utf-8")
    reports_dir = out_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(report_path, reports_dir / report_path.name)
    shutil.copy2(exec_path, reports_dir / exec_path.name)
    return report_path, exec_path


def write_workbook(out_dir: Path, timestamp: str, sheets: dict[str, pd.DataFrame]) -> Path:
    path = out_dir / "reports" / f"v8_2_gate_aware_reranking_replay_workbook_{timestamp}.xlsx"
    write_excel(sheets, path)
    return path


def update_next_steps(out_dir: Path, zip_path: Path, verdict: dict[str, Any]) -> None:
    path = PROJECT_ROOT / "NEXT_STEPS.md"
    previous = path.read_text(encoding="utf-8") if path.exists() else "# NEXT_STEPS\n"
    section = f"""

## v8.2 bounded gate-aware reranking replay

- 执行状态：completed，随后按要求暂停，不自动进入下一轮。
- 输出目录：`{out_dir}`
- zip：`{zip_path}`
- 是否完成 sample：`True`
- 是否完成 full：`{verdict.get('full_completed')}`
- 是否有 accepted candidate：`{verdict.get('has_accepted_candidate')}`
- accepted candidates：`{', '.join(verdict.get('accepted_candidates', [])) or 'None'}`
- 是否有 strong candidate：`{verdict.get('has_strong_candidate')}`
- strong candidates：`{', '.join(verdict.get('strong_candidates', [])) or 'None'}`
- 是否替代 best：`False`
- 是否允许进入 v9：`False`
- 下一步是否需要用户/ChatGPT 决策：`True`
- 本轮边界：未进入 v9，未扩 universe，未训练新模型，未运行 31b，未使用 audit_forward 字段排序。
"""
    path.write_text(previous.rstrip() + "\n" + section, encoding="utf-8")


def write_run_summary(out_dir: Path, zip_path: Path, verdict: dict[str, Any]) -> None:
    text = f"""# RUN_SUMMARY

本轮目标：bounded v8.2 gate-aware reranking replay。

新 run 目录：`{out_dir}`

zip：`{zip_path}`

是否进入 v9：`False`

是否扩 universe：`False`

是否训练新模型：`False`

是否运行 31b：`False`

是否使用 audit_forward 字段排序：`False`

是否替代 v8 baseline：`False`

accepted candidates：`{', '.join(verdict.get('accepted_candidates', [])) or 'None'}`

strong candidates：`{', '.join(verdict.get('strong_candidates', [])) or 'None'}`

后续：暂停，等待用户/ChatGPT 决策。
"""
    (out_dir / "RUN_SUMMARY.md").write_text(text, encoding="utf-8")
    (PROJECT_ROOT / "RUN_SUMMARY.md").write_text(text, encoding="utf-8")


def package_outputs(out_dir: Path, docs: list[Path], zip_path: Path) -> None:
    files = [
        PROJECT_ROOT / "scripts" / "us_stock_selection" / "41_run_v8_2_gate_aware_reranking_replay.py",
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


def sync_meistock(timestamp: str, out_dir: Path, zip_path: Path, report_path: Path, exec_path: Path, verdict: dict[str, Any]) -> None:
    if not MEISTOCK_ROOT.exists():
        return
    for sub in [
        "01_对话沉淀/Codex",
        "02_项目文档/报告章节底稿",
        "03_决策日志",
        "06_证据链",
        "07_附件索引",
        "docs/context",
    ]:
        (MEISTOCK_ROOT / sub).mkdir(parents=True, exist_ok=True)
    shutil.copy2(report_path, MEISTOCK_ROOT / "02_项目文档" / "报告章节底稿" / report_path.name)
    shutil.copy2(exec_path, MEISTOCK_ROOT / "02_项目文档" / "报告章节底稿" / exec_path.name)
    for name in [
        "v8_2_reranking_cycle_verdict.json",
        "v8_2_reranking_full_period_metrics.csv",
        "v8_2_reranking_gate_results.csv",
        "v8_2_reranking_weakest_12m_comparison.csv",
    ]:
        source = out_dir / name
        if source.exists():
            shutil.copy2(source, MEISTOCK_ROOT / "06_证据链" / f"{timestamp}_{name}")
    if zip_path.exists():
        shutil.copy2(zip_path, MEISTOCK_ROOT / "07_附件索引" / zip_path.name)
    checkpoint = f"""# Codex Checkpoint - v8.2 Gate-Aware Reranking Replay {timestamp}

- Output directory: `{out_dir}`
- Zip: `{zip_path}`
- Accepted candidates: `{', '.join(verdict.get('accepted_candidates', [])) or 'None'}`
- Strong candidates: `{', '.join(verdict.get('strong_candidates', [])) or 'None'}`
- Replace v8 best: `False`
- Allow enter v9: `False`

Pause for user/ChatGPT decision.
"""
    (MEISTOCK_ROOT / "01_对话沉淀" / "Codex" / f"{timestamp}_v8_2_gate_aware_reranking_checkpoint.md").write_text(checkpoint, encoding="utf-8")
    context = f"""# MeiStock Current Context

Last updated: {timestamp}

Latest checkpoint: v8.2 bounded gate-aware reranking replay.

Accepted candidates: `{', '.join(verdict.get('accepted_candidates', [])) or 'None'}`.

Strong candidates: `{', '.join(verdict.get('strong_candidates', [])) or 'None'}`.

v8 baseline is not automatically replaced. v9 remains false.
"""
    (MEISTOCK_ROOT / "docs" / "context" / "MeiStock_current_context.md").write_text(context, encoding="utf-8")


def date_str(value: Any) -> str:
    return "" if pd.isna(value) else pd.Timestamp(value).date().isoformat()


def main() -> None:
    args = parse_args()
    timestamp = args.timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = (args.out_dir or OUTPUT_ROOT / f"v8_2_gate_aware_reranking_replay_{timestamp}").resolve()
    (out_dir / "reports").mkdir(parents=True, exist_ok=True)
    logger = setup_logger(out_dir)
    logger.info("Starting bounded v8.2 gate-aware reranking replay.")
    logger.info("Boundaries: no v9, no universe expansion, no new model training, no 31b, no audit_forward ranking.")

    paths = ensure_inputs(args.baseline_run_dir, args.audit_replay_dir)
    readiness = read_json(paths["readiness"])
    if not readiness.get("can_run_gate_aware_reranking_replay"):
        raise RuntimeError("Bounded replay readiness is not true; refusing reranking replay.")
    audit, ledger, holdings, baseline_daily = normalize_inputs(
        read_csv(paths["audit_trail"]),
        read_csv(paths["baseline_ledger"]),
        read_csv(paths["baseline_holdings"]),
        read_csv(paths["baseline_daily_nav"]),
    )
    candidates = parse_candidate_list(args.candidate_list)
    score_direction = score_direction_check(audit, ledger)
    write_json(score_direction, out_dir / "v8_2_score_direction_check.json")
    if not score_direction.get("rank_consistency_pass"):
        raise RuntimeError("Score direction/rank consistency check failed; refusing reranking replay.")
    feature_usage = feature_usage_audit(candidates, audit)
    feature_usage.to_csv(out_dir / "v8_2_reranking_feature_usage_audit.csv", index=False, encoding="utf-8-sig")
    feature_usage.to_csv(out_dir / "v8_2_sample_reranking_feature_usage_audit.csv", index=False, encoding="utf-8-sig")

    sample_dates, sample_warnings = resolve_sample_decisions(ledger, parse_sample_months(args.sample_months))
    sample_dates = limit_dates(sample_dates, args.max_decision_dates)
    dryrun = {
        "dry_run": True,
        "baseline_run_exists": args.baseline_run_dir.exists(),
        "audit_replay_dir_exists": args.audit_replay_dir.exists(),
        "readiness_true": readiness.get("can_run_gate_aware_reranking_replay"),
        "full_audit_trail_exists": paths["audit_trail"].exists(),
        "score_direction_confirmed": score_direction.get("rank_consistency_pass"),
        "feature_usage_audit_rows": int(len(feature_usage)),
        "out_dir": str(out_dir),
        "stopped_before": "reranking_replay",
    }
    write_json(dryrun, out_dir / "v8_2_reranking_dryrun.json")
    if args.dry_run:
        logger.info("Dry-run completed: %s", dryrun)
        return

    sample_selection, sample_score_rank, sample_skipped = build_reranking_selection(audit, ledger, candidates, sample_dates)
    sample_diff = selection_diff_vs_baseline(sample_selection, ledger)
    sample_quality, sample_summary = validate_sample_selection(sample_selection, sample_score_rank, ledger, candidates)
    if not sample_warnings.empty:
        sample_summary["sample_resolution_warnings"] = sample_warnings.to_dict(orient="records")
    sample_selection.to_csv(out_dir / "v8_2_sample_reranking_selection.csv", index=False, encoding="utf-8-sig")
    sample_diff.to_csv(out_dir / "v8_2_sample_reranking_selection_diff_vs_baseline.csv", index=False, encoding="utf-8-sig")
    sample_quality.to_csv(out_dir / "v8_2_sample_reranking_quality.csv", index=False, encoding="utf-8-sig")
    sample_score_rank.to_csv(out_dir / "v8_2_sample_reranking_score_rank_by_month.csv", index=False, encoding="utf-8-sig")
    sample_skipped.to_csv(out_dir / "v8_2_sample_reranking_skipped_candidates.csv", index=False, encoding="utf-8-sig")
    write_json(sample_summary, out_dir / "v8_2_sample_reranking_summary.json")
    if not sample_summary["quality_pass_all"]:
        logger.warning("Sample reranking validation failed; full replay blocked.")
        verdict = {
            "sample_completed": True,
            "sample_passed": False,
            "full_completed": False,
            "accepted_candidates": [],
            "strong_candidates": [],
            "replace_v8_best": False,
            "allow_enter_v9": False,
            "required_patch": "fix sample reranking validation failures before full replay",
        }
        write_json(verdict, out_dir / "v8_2_reranking_cycle_verdict.json")
        zip_path = OUTPUT_ROOT / f"us_stock_selection_quant_lab_v8_2_gate_aware_reranking_replay_{timestamp}.zip"
        report_path, exec_path = write_reports(timestamp, out_dir, zip_path, score_direction, feature_usage, sample_summary, sample_quality, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), verdict)
        update_next_steps(out_dir, zip_path, verdict)
        write_run_summary(out_dir, zip_path, verdict)
        package_outputs(out_dir, [report_path, exec_path], zip_path)
        return

    full_dates = sorted(pd.to_datetime(ledger["decision_date"]).dropna().unique().tolist())
    full_dates = [pd.Timestamp(x) for x in full_dates]
    full_dates = limit_dates(full_dates, args.max_decision_dates)
    full_executed = False
    full_selection = full_score_rank = full_diff = pd.DataFrame()
    replay_outputs: dict[str, Any] = {}
    if args.full:
        full_selection, full_score_rank, full_skipped = build_reranking_selection(audit, ledger, candidates, full_dates)
        full_diff = selection_diff_vs_baseline(full_selection, ledger)
        close = load_close_for_replay(args.provider_uri, audit, baseline_daily, logger)
        replay_outputs = run_replay(full_selection, close, cost_bps=args.cost_bps, slippage_bps=args.slippage_bps, logger=logger)
        full_executed = True
        full_selection.to_csv(out_dir / "v8_2_reranking_selection_by_month.csv", index=False, encoding="utf-8-sig")
        full_diff.to_csv(out_dir / "v8_2_reranking_selection_diff_vs_baseline.csv", index=False, encoding="utf-8-sig")
        full_score_rank.to_csv(out_dir / "v8_2_reranking_score_rank_by_month.csv", index=False, encoding="utf-8-sig")
        full_skipped.to_csv(out_dir / "v8_2_reranking_skipped_candidates.csv", index=False, encoding="utf-8-sig")
        replay_outputs["metrics"].to_csv(out_dir / "v8_2_reranking_full_period_metrics.csv", index=False, encoding="utf-8-sig")
        replay_outputs["daily"].to_csv(out_dir / "v8_2_reranking_nav_by_candidate.csv", index=False, encoding="utf-8-sig")
        replay_outputs["holdings"].to_csv(out_dir / "v8_2_reranking_monthly_holdings.csv", index=False, encoding="utf-8-sig")
        replay_outputs["trades"].to_csv(out_dir / "v8_2_reranking_trades.csv", index=False, encoding="utf-8-sig")
        replay_outputs["gates"].to_csv(out_dir / "v8_2_reranking_gate_results.csv", index=False, encoding="utf-8-sig")
        replay_outputs["loo"].to_csv(out_dir / "v8_2_reranking_leave_one_year_out.csv", index=False, encoding="utf-8-sig")
        replay_outputs["top_month"].to_csv(out_dir / "v8_2_reranking_top_month_sensitivity.csv", index=False, encoding="utf-8-sig")
        replay_outputs["rolling"].to_csv(out_dir / "v8_2_reranking_rolling_12m_metrics.csv", index=False, encoding="utf-8-sig")
        replay_outputs["ticker"].to_csv(out_dir / "v8_2_reranking_ticker_concentration.csv", index=False, encoding="utf-8-sig")
        replay_outputs["weakest"].to_csv(out_dir / "v8_2_reranking_weakest_12m_comparison.csv", index=False, encoding="utf-8-sig")
    else:
        logger.info("Sample passed; --full not supplied, stopping before full replay.")
    metrics = replay_outputs.get("metrics", pd.DataFrame())
    gates = replay_outputs.get("gates", pd.DataFrame())
    weakest = replay_outputs.get("weakest", pd.DataFrame())
    verdict = build_verdict(metrics, sample_summary, full_executed)
    write_json(verdict, out_dir / "v8_2_reranking_cycle_verdict.json")
    zip_path = OUTPUT_ROOT / f"us_stock_selection_quant_lab_v8_2_gate_aware_reranking_replay_{timestamp}.zip"
    report_path, exec_path = write_reports(timestamp, out_dir, zip_path, score_direction, feature_usage, sample_summary, sample_quality, metrics, weakest, gates, verdict)
    workbook_sheets = {
        "score_direction": pd.DataFrame([to_jsonable(score_direction)]),
        "feature_usage": feature_usage,
        "sample_quality": sample_quality,
        "sample_diff": sample_diff,
        "full_metrics": metrics,
        "gate_results": gates,
        "weakest_12m": weakest,
    }
    write_workbook(out_dir, timestamp, workbook_sheets)
    update_next_steps(out_dir, zip_path, verdict)
    write_run_summary(out_dir, zip_path, verdict)
    package_outputs(out_dir, [report_path, exec_path], zip_path)
    sync_meistock(timestamp, out_dir, zip_path, report_path, exec_path, verdict)
    logger.info("Packaged v8.2 reranking replay zip: %s", zip_path)


if __name__ == "__main__":
    main()
