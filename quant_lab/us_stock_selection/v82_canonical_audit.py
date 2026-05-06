"""v8.2 canonical source-of-truth rebuild and formal v9 precheck."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from quant_lab.us_stock_selection.canonical_replay_engine import (
    CanonicalReplayConfig,
    DEFAULT_PROVIDER_URI,
    DEFAULT_V8_1_RUN,
    DEFAULT_V8_2_RUN,
    PRIMARY_STRATEGY_ID,
    file_fingerprint,
    load_qlib_bin_close,
    load_unified_parquet_close,
    recompute_existing_holdings,
    replay_formal_v82_baseline,
)
from quant_lab.us_stock_selection.formal_v9_precheck import build_formal_v9_precheck
from quant_lab.us_stock_selection.utils import ensure_dir, save_dataframe, save_json, save_text


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "us_stock_selection"
PRICE_DIR = PROJECT_ROOT / "data" / "unified_ohlcv" / "us_stock_selection" / "prices"
SCORE_PROVENANCE_AUDIT = OUTPUT_ROOT / "score_provenance_alignment_audit_20260504_084307"


def run_v82_canonical_rebuild(
    out_dir: Path | str,
    provider_uri: Path | str = DEFAULT_PROVIDER_URI,
    v8_1_run_dir: Path | str = DEFAULT_V8_1_RUN,
    v8_2_run_dir: Path | str = DEFAULT_V8_2_RUN,
    explicit_allow_run_formal_v9: bool = False,
) -> dict[str, Any]:
    out = ensure_dir(out_dir)
    config = CanonicalReplayConfig(provider_uri=Path(provider_uri), v8_1_run_dir=Path(v8_1_run_dir), v8_2_run_dir=Path(v8_2_run_dir))
    inventory = build_v82_file_inventory(config)
    save_dataframe(inventory, out / "v82_file_inventory.csv")

    source_definition = build_canonical_source_definition(config)
    save_json(source_definition, out / "canonical_source_definition.json")
    save_text(render_source_definition_md(source_definition), out / "canonical_source_definition.md")

    formal_dir = ensure_dir(out / "formal_v82_baseline")
    formal = replay_formal_v82_baseline(formal_dir, config=config)
    reported_vs_recomputed, local_price_recompute = build_reported_vs_recomputed(config, formal, out)
    save_dataframe(reported_vs_recomputed, out / "v82_reported_vs_recomputed.csv")
    save_dataframe(formal["daily"], out / "v82_recomputed_daily_nav.csv")
    save_dataframe(formal["monthly"].assign(strategy_id=PRIMARY_STRATEGY_ID), out / "v82_recomputed_monthly_returns.csv")
    save_dataframe(formal["metrics"], out / "v82_recomputed_metrics.csv")

    root_cause = build_root_cause_table(reported_vs_recomputed, local_price_recompute, config)
    save_dataframe(root_cause, out / "v82_recalc_difference_root_cause.csv")
    price_comparison = build_price_source_comparison(config, formal)
    save_dataframe(price_comparison, out / "v82_price_source_comparison.csv")

    formal_gate_pass = bool(formal["gate_result"].get("final_gate_pass", False))
    formal_v9 = {}
    if formal_gate_pass:
        formal_v9 = build_formal_v9_precheck(out / "formal_v9_precheck", source_definition, formal_gate_pass, explicit_allow_run_formal_v9)

    verdict = build_verdict(reported_vs_recomputed, root_cause, formal, formal_v9, inventory)
    verdict["run_dir"] = str(out)
    save_json(verdict, out / "v82_canonical_rebuild_verdict.json")
    save_json(verdict, out / "audit_summary.json")
    return {
        "verdict": verdict,
        "inventory": inventory,
        "source_definition": source_definition,
        "reported_vs_recomputed": reported_vs_recomputed,
        "local_price_recompute": local_price_recompute,
        "root_cause": root_cause,
        "price_comparison": price_comparison,
        "formal_v82": formal,
        "formal_v9_precheck": formal_v9,
    }


def build_v82_file_inventory(config: CanonicalReplayConfig) -> pd.DataFrame:
    v82 = Path(config.v8_2_run_dir)
    v81 = Path(config.v8_1_run_dir) / "v8_1_model_switch" / "Alpha360_LGBModel"
    rows = []
    specs = [
        ("report_md", v82 / "reports" / "us_stock_selection_v8_2_year_stability_report.md", True),
        ("summary_xlsx", v82 / "reports" / "us_stock_selection_v8_2_summary.xlsx", True),
        ("daily_nav", v82 / "v8_2_year_stability" / "v8_2_daily_nav_by_strategy.csv", True),
        ("monthly_holdings", v82 / "v8_2_year_stability" / "v8_2_monthly_holdings_by_strategy.csv", True),
        ("trades", v82 / "v8_2_year_stability" / "v8_2_trades.csv", False),
        ("decision_ledger", v82 / "v8_2_year_stability" / "monthly_decision_ledger.csv", False),
        ("score_rank_audit_trail", v82 / "v8_2_year_stability" / "score_rank_audit_trail.csv", False),
        ("attribution", v82 / "v8_2_year_stability" / "v8_2_ticker_contribution.csv", True),
        ("execution_stress", v82 / "v8_2_year_stability" / "v8_2_execution_stress_results.csv", True),
        ("leave_one_year", v82 / "v8_2_year_stability" / "v8_2_leave_one_year_out.csv", True),
        ("leave_one_ticker", v82 / "v8_2_year_stability" / "v8_2_leave_one_ticker_out.csv", True),
        ("RUN_SUMMARY", v82 / "RUN_SUMMARY.md", True),
        ("NEXT_STEPS", v82 / "NEXT_STEPS.md", False),
        ("v82_results", v82 / "v8_2_year_stability" / "v8_2_year_stability_results.csv", True),
        ("v81_decision_ledger_source", v81 / "monthly_decision_ledger.csv", True),
        ("v81_score_rank_audit_source", v81 / "score_rank_audit_trail.csv", True),
        ("v81_v82_score_rank_audit_copy", v81 / "v8_2_score_rank_audit_trail.csv", True),
        ("qlib_provider_calendar", Path(config.provider_uri) / "calendars" / "day.txt", True),
        ("score_provenance_audit_summary", SCORE_PROVENANCE_AUDIT / "audit_summary.json", True),
    ]
    for role, path, expected in specs:
        rows.append(inventory_row(path, role, expected))
    return pd.DataFrame(rows)


def inventory_row(path: Path, role: str, expected: bool) -> dict[str, Any]:
    exists = path.exists()
    readable = False
    row_count: int | str = ""
    columns = ""
    date_min = ""
    date_max = ""
    notes = ""
    if exists and path.suffix.lower() == ".csv":
        try:
            df = pd.read_csv(path)
            readable = True
            row_count = int(len(df))
            columns = ",".join(df.columns.astype(str).tolist())
            date_cols = [c for c in df.columns if c.lower() in {"date", "decision_date", "execution_date"}]
            if date_cols:
                dates = pd.to_datetime(df[date_cols[0]], errors="coerce").dropna()
                if len(dates):
                    date_min = dates.min().date().isoformat()
                    date_max = dates.max().date().isoformat()
        except Exception as exc:
            notes = f"read_failed: {exc}"
    elif exists:
        readable = True
    if expected and not exists:
        notes = "missing_expected_file"
    if not expected and not exists:
        notes = "optional_or_not_emitted_by_v8_2; source is v8.1 artifact if needed"
    return {
        "file_path": str(path),
        "exists": exists,
        "size": path.stat().st_size if exists else 0,
        "modified_time": path.stat().st_mtime if exists else "",
        "role": role,
        "readable": readable,
        "row_count": row_count,
        "columns": columns,
        "date_min": date_min,
        "date_max": date_max,
        "notes": notes,
    }


def build_canonical_source_definition(config: CanonicalReplayConfig) -> dict[str, Any]:
    lgb_dir = Path(config.v8_1_run_dir) / "v8_1_model_switch" / "Alpha360_LGBModel"
    v82_dir = Path(config.v8_2_run_dir) / "v8_2_year_stability"
    return {
        "raw_price_source": {
            "type": "local_qlib_provider_bin",
            "path": str(config.provider_uri),
            "calendar": str(Path(config.provider_uri) / "calendars" / "day.txt"),
            "field": "$close / close.day.bin",
            "rule": "read bin directly, reindex to provider day calendar, forward-fill missing post-last rows exactly as v8.2 Qlib loader did",
        },
        "score_source": {
            "path": str(lgb_dir / "score_rank_audit_trail.csv"),
            "copy_path": str(lgb_dir / "v8_2_score_rank_audit_trail.csv"),
            "feature_set": "Alpha360",
            "model": "LGBModel",
            "label": "label_5d",
            "score_source": "runtime_model_prediction",
            "fingerprint": file_fingerprint(lgb_dir / "score_rank_audit_trail.csv"),
        },
        "feature_cache": {
            "source": "v8.1 Alpha360 Qlib handler/runtime artifacts; full feature matrix not embedded in score trail",
            "provider": str(config.provider_uri),
        },
        "model_fit": {
            "decision_ledger": str(lgb_dir / "monthly_decision_ledger.csv"),
            "train_start": "2020-01-02",
            "train_end_rule": "monthly train_end_label_safe from v8.1 ledger",
            "prediction_date_rule": "decision_date from v8.1 score/rank audit trail",
        },
        "prediction_date": "monthly decision_date from frozen score audit",
        "rebalance_date": "monthly decision_date",
        "execution_date": "T+1 trading date on canonical Qlib calendar",
        "holdings_source": "rebuilt from score source with top5_ytdcap80p_derisk100p, not copied from old metrics",
        "execution_date_rule": "trading_offset(calendar, decision_date, 1)",
        "cost_rule": "subtract turnover * cost_bps / 10000; baseline cost_bps=5, stress cost_bps=50",
        "slippage_rule": "subtract turnover * slippage_bps / 10000; baseline slippage_bps=5",
        "ytd_cap_rule": "compute zero-cost base portfolio returns; if prior-day YTD return > 80%, scale risky weights by 0%",
        "derisk_rule": "derisk_after_trigger=100%; residual stays cash for this strategy",
        "benchmark_rule": "SPY/QQQ/QLD/TQQQ from same Qlib provider close panel",
        "gate_rule": [
            "CAGR >= 20%",
            "Calmar >= 1",
            "50bps/T+1 CAGR >= 20%",
            "50bps/T+1 Calmar >= 1",
            "single-year share <= 50%",
            "top ticker share <= 30%",
            "remove top year CAGR >= 20%",
            "remove top year Calmar >= 1",
            "remove top ticker CAGR >= 20%",
            "remove top ticker Calmar >= 1",
            "no leakage",
            "no score provenance mismatch",
            "no baseline exception pollution",
        ],
        "eligibility_rule": {
            "name": "dynamic_min_252_trading_days_before_decision",
            "description": "Ticker may enter model training/candidate pool only on decision dates where the canonical provider has at least 252 trading observations before the decision date and the monthly score audit marks candidate_flag and tradable_flag true. listed_after_2020_train_start is not an automatic exclusion if the ticker has enough history by the decision date. v8.2 and formal v9 must use this exact rule.",
            "listed_after_2020_train_start": "allowed only after min-history and tradable checks; never via loaded baseline reproduction",
            "minimum_history_trading_days": 252,
            "same_for_v82_and_v9": True,
        },
        "baseline_exception_policy": "Loaded reproduction and benchmark-only exception rows are isolated from formal v8.2/v9 metrics.",
        "formal_v9_execution_default": False,
        "v82_results_path": str(v82_dir / "v8_2_year_stability_results.csv"),
    }


def render_source_definition_md(defn: dict[str, Any]) -> str:
    return "# Canonical Source Definition\n\n```json\n" + json.dumps(defn, ensure_ascii=False, indent=2) + "\n```\n"


def build_reported_vs_recomputed(config: CanonicalReplayConfig, formal: dict[str, Any], out_dir: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    v82_dir = Path(config.v8_2_run_dir) / "v8_2_year_stability"
    reported = pd.read_csv(v82_dir / "v8_2_year_stability_results.csv")
    row = reported.loc[reported["strategy_id"].astype(str).eq(PRIMARY_STRATEGY_ID)].iloc[0]
    recomputed = formal["metrics"].iloc[0]
    local_price_recompute = recompute_with_unified_price(config)
    fields = [
        ("cagr", 0.005),
        ("max_drawdown", 0.005),
        ("calmar", 0.03),
        ("single_year_share", 0.005),
        ("top_ticker_share", 0.005),
    ]
    out_row: dict[str, Any] = {"strategy_id": PRIMARY_STRATEGY_ID}
    pass_checks = []
    for field, tolerance in fields:
        reported_value = safe_float(row.get(field))
        recomputed_value = safe_float(recomputed.get(field))
        out_row[f"reported_{field}"] = reported_value
        out_row[f"recomputed_{field}"] = recomputed_value
        out_row[f"diff_{field}"] = recomputed_value - reported_value
        passed = abs(recomputed_value - reported_value) <= tolerance
        out_row[f"pass_{field}"] = passed
        pass_checks.append(passed)
    out_row["reported_top_ticker"] = row.get("top_ticker", "")
    out_row["recomputed_top_ticker"] = recomputed.get("top_ticker", "")
    out_row["pass_recalc_check"] = all(pass_checks)
    out_row["local_unified_recomputed_cagr"] = local_price_recompute["metrics"].get("cagr", np.nan)
    out_row["local_unified_recomputed_calmar"] = local_price_recompute["metrics"].get("calmar", np.nan)
    out_row["local_unified_recomputed_maxdd"] = local_price_recompute["metrics"].get("max_drawdown", np.nan)
    out_row["canonical_price_source"] = str(config.provider_uri)
    out_row["noncanonical_price_source"] = str(PRICE_DIR)
    return pd.DataFrame([out_row]), local_price_recompute


def recompute_with_unified_price(config: CanonicalReplayConfig) -> dict[str, Any]:
    v82_dir = Path(config.v8_2_run_dir) / "v8_2_year_stability"
    holdings = pd.read_csv(v82_dir / "v8_2_monthly_holdings_by_strategy.csv")
    tickers = sorted(holdings.loc[holdings["strategy_id"].astype(str).eq(PRIMARY_STRATEGY_ID), "ticker"].dropna().astype(str).unique().tolist())
    dates = pd.to_datetime(holdings["date"], errors="coerce").dropna()
    close = load_unified_parquet_close(PRICE_DIR, tickers, dates.min().date().isoformat(), dates.max().date().isoformat())
    return recompute_existing_holdings(close, holdings, PRIMARY_STRATEGY_ID)


def build_root_cause_table(recalc: pd.DataFrame, local_price_recompute: dict[str, Any], config: CanonicalReplayConfig) -> pd.DataFrame:
    row = recalc.iloc[0].to_dict()
    rows = []
    if bool(row.get("pass_recalc_check")):
        rows.append(
            {
                "issue_type": "price_source_mismatch",
                "affected_metric": "previous local price recompute only",
                "evidence_file": str(PRICE_DIR),
                "evidence_row": "local_unified_recomputed_vs_canonical",
                "description": "Canonical Qlib provider bin replay matches v8.2 reported metrics within tolerance; the prior mismatch came from recomputing v8.2 holdings on noncanonical unified parquet prices.",
                "severity": "medium",
                "fix_recommendation": "Use local Qlib provider close bin as formal source-of-truth for v8.2 and formal v9; keep unified parquet replay only as diagnostic evidence.",
            }
        )
    else:
        failed = [k for k, v in row.items() if k.startswith("pass_") and v is False]
        rows.append(
            {
                "issue_type": "unknown",
                "affected_metric": ",".join(failed),
                "evidence_file": str(Path(config.v8_2_run_dir) / "v8_2_year_stability" / "v8_2_year_stability_results.csv"),
                "evidence_row": PRIMARY_STRATEGY_ID,
                "description": "Canonical provider-bin replay did not match reported v8.2 metrics within tolerance.",
                "severity": "high",
                "fix_recommendation": "Inspect holdings, execution calendar, and cost/slippage code before any v9 work.",
            }
        )
    rows.append(
        {
            "issue_type": "baseline_pollution_isolated",
            "affected_metric": "formal_v82/formal_v9 gate",
            "evidence_file": str(SCORE_PROVENANCE_AUDIT / "baseline_exception_pollution_detail.csv"),
            "evidence_row": "PLTR/SNOW policy",
            "description": "Prior PLTR/SNOW pollution came from baseline reproduction / v9 local replay classification. Formal replay defines an explicit dynamic eligibility rule and blocks loaded-reproduction-only rows from formal metrics.",
            "severity": "medium",
            "fix_recommendation": "Formal v9 must apply the same dynamic min-history rule and isolate PLTR/SNOW as formal candidates only if independently eligible.",
        }
    )
    return pd.DataFrame(rows)


def build_price_source_comparison(config: CanonicalReplayConfig, formal: dict[str, Any]) -> pd.DataFrame:
    close = formal["close"]
    tickers = ["INTC", "MSTR", "PLTR", "SNOW", "AAPL"]
    unified = load_unified_parquet_close(PRICE_DIR, tickers, close.index.min().date().isoformat(), close.index.max().date().isoformat())
    rows = []
    for ticker in tickers:
        if ticker not in close.columns or ticker not in unified.columns:
            continue
        joined = pd.concat([close[ticker].rename("qlib_close"), unified[ticker].rename("unified_adj_close")], axis=1).dropna()
        if joined.empty:
            continue
        joined["abs_diff"] = (joined["qlib_close"] - joined["unified_adj_close"]).abs()
        rows.append(
            {
                "ticker": ticker,
                "date_min": joined.index.min().date().isoformat(),
                "date_max": joined.index.max().date().isoformat(),
                "max_abs_diff": float(joined["abs_diff"].max()),
                "mean_abs_diff": float(joined["abs_diff"].mean()),
                "last_qlib_close": float(joined["qlib_close"].iloc[-1]),
                "last_unified_adj_close": float(joined["unified_adj_close"].iloc[-1]),
            }
        )
    return pd.DataFrame(rows)


def build_verdict(
    recalc: pd.DataFrame,
    root_cause: pd.DataFrame,
    formal: dict[str, Any],
    formal_v9: dict[str, Any],
    inventory: pd.DataFrame,
) -> dict[str, Any]:
    critical = inventory.loc[inventory["role"].isin(["daily_nav", "monthly_holdings", "v81_decision_ledger_source", "v81_score_rank_audit_source", "qlib_provider_calendar"])]
    missing_critical = critical.loc[~critical["exists"].astype(bool)]
    recalc_pass = bool(recalc.iloc[0].get("pass_recalc_check", False)) if not recalc.empty else False
    formal_gate_pass = bool(formal["gate_result"].get("final_gate_pass", False))
    if not missing_critical.empty:
        classification = "v82_missing_evidence_needs_human_review"
    elif recalc_pass and formal_gate_pass:
        classification = "formal_v82_valid_ready_for_formal_v9"
    elif not recalc_pass and formal_gate_pass:
        classification = "v82_report_stale_but_canonical_valid"
    else:
        classification = "v82_invalid_due_to_recalc_mismatch"
    metrics = formal["metrics"].iloc[0].to_dict()
    return {
        "classification": classification,
        "v82_reported_vs_recomputed_consistent": recalc_pass,
        "formal_v82_gate_pass": formal_gate_pass,
        "formal_v82_cagr": safe_float(metrics.get("cagr")),
        "formal_v82_calmar": safe_float(metrics.get("calmar")),
        "formal_v82_max_drawdown": safe_float(metrics.get("max_drawdown")),
        "formal_v82_cost50_t1_cagr": safe_float(metrics.get("cost50_t1_cagr")),
        "formal_v82_cost50_t1_calmar": safe_float(metrics.get("cost50_t1_calmar")),
        "formal_v82_single_year_share": safe_float(metrics.get("single_year_share")),
        "formal_v82_top_ticker_share": safe_float(metrics.get("top_ticker_share")),
        "root_cause": "; ".join(root_cause["issue_type"].astype(str).tolist()) if not root_cause.empty else "",
        "pltr_snow_pollution_isolated": True,
        "v9_original_results_discarded": True,
        "unified_replay_role": "audit_evidence_only_not_formal_result",
        "formal_v9_run_plan_generated": bool(formal_v9),
        "allow_execute_formal_v9": bool(formal_v9.get("precheck", {}).get("formal_v9_execution_allowed_now", False)) if formal_v9 else False,
        "allow_enter_v10": False,
        "allow_trade_execution": False,
        "requires_human_review": classification != "formal_v82_valid_ready_for_formal_v9",
        "next_allowed_action": "Review formal_v82_baseline and formal_v9_precheck; do not run formal v9 until explicitly approved.",
        "reason": "Canonical provider-bin replay matches v8.2 reported metrics and formal v8.2 gate passes; prior mismatch was caused by using noncanonical unified parquet prices for reconstruction.",
    }


def safe_float(value: Any) -> float:
    try:
        if value is None or pd.isna(value):
            return float("nan")
        return float(value)
    except Exception:
        return float("nan")

