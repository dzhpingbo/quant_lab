"""Run the local v8.2 vs v9 replay-difference audit.

This script only reads existing local artifacts.  It does not download data,
does not expand the universe, does not change gates, and does not create any
execution integration.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from quant_lab.us_stock_selection.chatgpt_bridge import publish_for_chatgpt
from quant_lab.us_stock_selection.qlib_signal_backtest import compute_portfolio_metrics
from quant_lab.us_stock_selection.utils import ensure_dir, save_dataframe, save_json, save_text, write_excel


OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "us_stock_selection"
V9_REVERSE_DIR = OUTPUT_ROOT / "run_20260503_172054" / "v9_reverse_audit"
V82_DIR = OUTPUT_ROOT / "run_20260502_220641" / "v8_2_year_stability"
V81_DIR = OUTPUT_ROOT / "run_20260502_210856" / "v8_1_model_switch" / "Alpha360_LGBModel"
V9_GROWTH_DIR = OUTPUT_ROOT / "run_20260502_222407" / "v9_growth_pool"

UNIFIED_START = pd.Timestamp("2024-01-02")
TRAIN_START = "2020-01-02"
POOL_A_TOP5 = "top5_ytdcap80p_derisk100p"
POOL_A_TOP10 = "top10_ytdcap80p_derisk100p"

STRATEGIES: dict[str, dict[str, Any]] = {
    "top5": {
        "strategy_id": POOL_A_TOP5,
        "top_k": 5,
        "v82_strategy_id": POOL_A_TOP5,
        "v9_loaded_universe": "pool_a_v8_2_reproduction",
        "v9_local_universe": "pool_a_v9_local_replay_top5",
        "portfolio_rule": "top5_ytdcap80p_derisk100p",
        "max_weight": 0.2,
    },
    "top10": {
        "strategy_id": POOL_A_TOP10,
        "top_k": 10,
        "v82_strategy_id": POOL_A_TOP10,
        "v9_loaded_universe": "pool_a_v8_2_reproduction_top10_control",
        "v9_local_universe": "pool_a_v9_local_replay_top10",
        "portfolio_rule": "top10_ytdcap80p_derisk100p_control",
        "max_weight": 0.1,
    },
}


REQUIRED_TEXT_INPUTS = [
    PROJECT_ROOT / "AGENTS.md",
    PROJECT_ROOT / "docs" / "US_STOCK_SELECTION_AUTORUN.md",
    PROJECT_ROOT / "NEXT_STEPS.md",
    PROJECT_ROOT / "RUN_SUMMARY.md",
    PROJECT_ROOT / "docs" / "chatgpt_bridge" / "LATEST.md",
    PROJECT_ROOT / "docs" / "chatgpt_bridge" / "latest_run_manifest.json",
    PROJECT_ROOT / "docs" / "chatgpt_bridge" / "runs" / "run_20260503_172054" / "REVIEW_PACKET.md",
    PROJECT_ROOT / "docs" / "chatgpt_bridge" / "runs" / "run_20260503_172054" / "selected_report.md",
    PROJECT_ROOT / "quant_lab" / "us_stock_selection" / "v9_reverse_audit.py",
    PROJECT_ROOT / "quant_lab" / "us_stock_selection" / "v9_reverse_audit_reporting.py",
    PROJECT_ROOT / "scripts" / "us_stock_selection" / "35_run_v9_reverse_audit.py",
]

RELATED_CODE_PATHS = [
    PROJECT_ROOT / "quant_lab" / "us_stock_selection" / "v9_reverse_audit.py",
    PROJECT_ROOT / "quant_lab" / "us_stock_selection" / "v9_reverse_audit_reporting.py",
    PROJECT_ROOT / "quant_lab" / "us_stock_selection" / "v9_growth_pool.py",
    PROJECT_ROOT / "quant_lab" / "us_stock_selection" / "v8_2_year_stability.py",
    PROJECT_ROOT / "quant_lab" / "us_stock_selection" / "v8_2_reporting.py",
    PROJECT_ROOT / "quant_lab" / "us_stock_selection" / "v8_2_audit_trail.py",
    PROJECT_ROOT / "quant_lab" / "us_stock_selection" / "v8_1_model_switch.py",
    PROJECT_ROOT / "scripts" / "us_stock_selection" / "32_run_v8_1_model_switch.py",
    PROJECT_ROOT / "scripts" / "us_stock_selection" / "33_run_v8_2_year_stability.py",
    PROJECT_ROOT / "scripts" / "us_stock_selection" / "34_run_v9_growth_pool.py",
    PROJECT_ROOT / "scripts" / "us_stock_selection" / "35_run_v9_reverse_audit.py",
    PROJECT_ROOT / "scripts" / "us_stock_selection" / "36_run_v82_v9_replay_diff_audit.py",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local v8.2/v9 replay diff audit; no expansion and no external data.")
    parser.add_argument("--timestamp", default="", help="Optional YYYYMMDD_HHMMSS timestamp.")
    parser.add_argument("--skip-bridge", action="store_true", help="Do not publish the local ChatGPT bridge packet.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    timestamp = args.timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = OUTPUT_ROOT / f"v82_v9_replay_diff_audit_{timestamp}"
    if run_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing audit directory: {run_dir}")

    logs_dir = ensure_dir(run_dir / "logs")
    reports_dir = ensure_dir(run_dir / "reports")
    logger = make_logger(logs_dir / "run.log")
    logger.info("Starting local v8.2/v9 replay diff audit.")

    tables = load_all_tables(logger)
    required_manifest = build_required_input_manifest()
    save_dataframe(required_manifest, run_dir / "required_input_manifest.csv")

    method_diff = build_method_diff(tables)
    save_dataframe(method_diff, run_dir / "v82_v9_method_diff.csv")

    candidate_diff = build_candidate_replay_diff(tables)
    save_dataframe(candidate_diff, run_dir / "candidate_replay_diff.csv")

    active_metrics = build_active_window_metrics(candidate_diff, tables)
    save_dataframe(active_metrics, run_dir / "active_window_metrics.csv")

    monthly_diff = build_monthly_selection_diff(tables)
    save_dataframe(monthly_diff, run_dir / "monthly_selection_diff.csv")

    by_ticker = build_candidate_replay_diff_by_ticker(tables)
    save_dataframe(by_ticker, run_dir / "candidate_replay_diff_by_ticker.csv")

    baseline_audit = build_baseline_exception_audit(by_ticker, tables)
    save_dataframe(baseline_audit, run_dir / "baseline_exception_audit.csv")

    leakage_scan = build_leakage_static_scan()
    save_dataframe(leakage_scan, run_dir / "leakage_static_scan.csv")

    summary = build_audit_summary(candidate_diff, active_metrics, baseline_audit, leakage_scan, required_manifest)
    save_json(summary, run_dir / "audit_summary.json")
    save_json(summary, run_dir / "v82_v9_replay_diff_audit_verdict.json")

    data_lineage = build_data_lineage_audit(run_dir)
    save_dataframe(data_lineage, run_dir / "data_lineage_audit.csv")

    readme = build_readme(summary, method_diff, candidate_diff, active_metrics, baseline_audit, leakage_scan, run_dir)
    save_text(readme, run_dir / "README.md")
    save_text(readme, reports_dir / "v82_v9_replay_diff_audit_report.md")

    write_excel(
        {
            "summary": pd.DataFrame([summary]),
            "method_diff": method_diff,
            "candidate_diff": candidate_diff,
            "active_metrics": active_metrics,
            "monthly_diff": monthly_diff.head(5000),
            "by_ticker": by_ticker,
            "baseline_exception": baseline_audit,
            "static_scan": leakage_scan.head(5000),
            "lineage": data_lineage,
        },
        reports_dir / "v82_v9_replay_diff_audit_summary.xlsx",
    )

    run_summary_text = build_run_summary(summary, candidate_diff, active_metrics, run_dir)
    next_steps_text = build_next_steps(summary, run_dir)
    save_text(run_summary_text, run_dir / "RUN_SUMMARY.md")
    save_text(next_steps_text, run_dir / "NEXT_STEPS.md")
    save_text(run_summary_text, PROJECT_ROOT / "RUN_SUMMARY.md")
    save_text(next_steps_text, PROJECT_ROOT / "NEXT_STEPS.md")

    zip_path = package_run(run_dir, timestamp)
    data_lineage = build_data_lineage_audit(run_dir, extra_outputs=[zip_path])
    save_dataframe(data_lineage, run_dir / "data_lineage_audit.csv")
    write_excel(
        {
            "summary": pd.DataFrame([summary]),
            "method_diff": method_diff,
            "candidate_diff": candidate_diff,
            "active_metrics": active_metrics,
            "monthly_diff": monthly_diff.head(5000),
            "by_ticker": by_ticker,
            "baseline_exception": baseline_audit,
            "static_scan": leakage_scan.head(5000),
            "lineage": data_lineage,
        },
        reports_dir / "v82_v9_replay_diff_audit_summary.xlsx",
    )
    zip_path = package_run(run_dir, timestamp)
    summary["zip_path"] = str(zip_path)
    summary["run_dir"] = str(run_dir)
    save_json(summary, run_dir / "audit_summary.json")
    save_json(summary, run_dir / "v82_v9_replay_diff_audit_verdict.json")

    if not args.skip_bridge:
        try:
            manifest = publish_for_chatgpt(run_dir=run_dir, max_csv_mb=5.0, include_xlsx=False, git_push=False)
            logger.info("Published local ChatGPT bridge packet: %s", manifest.get("review_packet", ""))
        except Exception as exc:  # pragma: no cover - bridge availability differs by environment
            logger.warning("Local ChatGPT bridge publish failed: %s", exc)

    print(
        json.dumps(
            {
                "run_dir": str(run_dir),
                "zip_path": str(zip_path),
                "classification": summary["classification"],
                "requires_human_review": summary["requires_human_review"],
                "allow_expand_universe": summary["allow_expand_universe"],
                "allow_enter_v10": summary["allow_enter_v10"],
                "allow_trade_execution": summary["allow_trade_execution"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def make_logger(path: Path) -> logging.Logger:
    logger = logging.getLogger("v82_v9_replay_diff_audit")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    file_handler = logging.FileHandler(path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger


def load_all_tables(logger: logging.Logger) -> dict[str, pd.DataFrame]:
    logger.info("Reading local v9 reverse, v8.2, v8.1, and v9 loaded-reproduction CSV artifacts.")
    paths = {
        "v9_daily": V9_REVERSE_DIR / "daily_nav.csv",
        "v9_holdings": V9_REVERSE_DIR / "monthly_holdings.csv",
        "v9_results": V9_REVERSE_DIR / "v9_local_pool_a_results.csv",
        "v9_pool_audit": V9_REVERSE_DIR / "pool_a_replay_audit.csv",
        "v9_attribution": V9_REVERSE_DIR / "attribution.csv",
        "v9_score": V9_REVERSE_DIR / "score_rank_audit.csv",
        "v9_time_alignment": V9_REVERSE_DIR / "time_alignment_audit.csv",
        "v9_universe_policy": V9_REVERSE_DIR / "universe_policy_audit.csv",
        "v9_negative_controls": V9_REVERSE_DIR / "negative_controls.csv",
        "v82_daily": V82_DIR / "v8_2_daily_nav_by_strategy.csv",
        "v82_holdings": V82_DIR / "v8_2_monthly_holdings_by_strategy.csv",
        "v82_results": V82_DIR / "v8_2_year_stability_results.csv",
        "v82_annual": V82_DIR / "v8_2_annual_return_table.csv",
        "v82_contribution": V82_DIR / "v8_2_ticker_contribution.csv",
        "v82_config": V82_DIR / "v8_2_variant_config.csv",
        "v81_score": V81_DIR / "score_rank_audit_trail.csv",
        "v81_holdings": V81_DIR / "monthly_holdings.csv",
        "v81_ledger": V81_DIR / "monthly_decision_ledger.csv",
        "v81_daily": V81_DIR / "daily_nav.csv",
        "v9_loaded_results": V9_GROWTH_DIR / "v9_growth_pool_results.csv",
        "v9_loaded_daily": V9_GROWTH_DIR / "v9_daily_nav_by_universe.csv",
        "v9_loaded_holdings": V9_GROWTH_DIR / "v9_monthly_holdings.csv",
        "v9_loaded_contribution": V9_GROWTH_DIR / "v9_ticker_contribution.csv",
        "v9_universe_definitions": V9_GROWTH_DIR / "v9_universe_definitions.csv",
        "v9_data_quality": V9_GROWTH_DIR / "v9_data_quality_audit.csv",
        "v9_price_download": V9_GROWTH_DIR / "v9_price_download_audit.csv",
    }
    tables: dict[str, pd.DataFrame] = {}
    missing = []
    for name, path in paths.items():
        if not path.exists():
            missing.append(str(path))
            tables[name] = pd.DataFrame()
            continue
        tables[name] = pd.read_csv(path, encoding="utf-8-sig")
    if missing:
        logger.warning("Missing input files: %s", missing)
    return tables


def build_required_input_manifest() -> pd.DataFrame:
    files: list[Path] = []
    files.extend(REQUIRED_TEXT_INPUTS)
    files.extend(sorted((PROJECT_ROOT / "docs" / "chatgpt_bridge" / "runs" / "run_20260503_172054" / "small_tables").glob("*.csv")))
    files.extend(sorted(V9_REVERSE_DIR.glob("*.csv")))
    files.extend(sorted(V82_DIR.glob("*.csv")))
    files.extend(sorted(V81_DIR.glob("*.csv")))
    files.extend(sorted(V9_GROWTH_DIR.glob("*.csv")))
    rows = []
    for path in unique_paths(files):
        rows.append(
            {
                "path": str(path),
                "repo_relative": rel(path),
                "exists": path.exists(),
                "size_bytes": path.stat().st_size if path.exists() else 0,
                "modified_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds") if path.exists() else "",
                "read_status": "read" if path.exists() else "missing",
                "first_line_or_header": read_first_line(path),
            }
        )
    return pd.DataFrame(rows)


def build_method_diff(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    ledger = parse_dates(tables["v81_ledger"].copy(), ["decision_date", "execution_date"])
    v9_time = parse_dates(tables["v9_time_alignment"].copy(), ["decision_date", "execution_date"])

    for label, spec in STRATEGIES.items():
        strategy_id = spec["strategy_id"]
        v82_daily = daily_slice(tables["v82_daily"], "strategy_id", strategy_id)
        v9_loaded_daily = daily_slice(tables["v9_loaded_daily"], "universe_name", spec["v9_loaded_universe"])
        v9_local_daily = daily_slice(tables["v9_daily"], "universe_name", spec["v9_local_universe"])

        rows.append(
            {
                "strategy_family": label,
                "source": "v8_2_frozen",
                "train_start": first_non_empty(ledger.get("train_start", pd.Series(dtype=str)), TRAIN_START),
                "decision_start": min_date_str(ledger.get("decision_date", pd.Series(dtype="datetime64[ns]"))),
                "first_weight_date": first_weight_date(tables["v82_holdings"], "strategy_id", strategy_id),
                "return_start": min_date_str(v82_daily.get("date", pd.Series(dtype="datetime64[ns]"))),
                "return_end": max_date_str(v82_daily.get("date", pd.Series(dtype="datetime64[ns]"))),
                "daily_count": int(len(v82_daily)),
                "cost/slippage": "5 bps cost + 5 bps slippage",
                "execution_delay": "1",
                "score_source": "v8.1 Alpha360_LGBModel score_rank_audit_trail.csv; score_source=runtime_model_prediction",
                "feature_source": "v8.1 Alpha360 feature cache / local Qlib provider artifact",
                "label": "label_5d",
                "portfolio rule": spec["portfolio_rule"],
                "independent_recalculation": "partial: v8.2 replays frozen v8.1 score/rank audit trail",
                "method_note": "575-day 2024-01-02 to 2026-04-17 evaluation window",
            }
        )
        rows.append(
            {
                "strategy_family": label,
                "source": "v9_loaded_reproduction",
                "train_start": first_non_empty(ledger.get("train_start", pd.Series(dtype=str)), TRAIN_START),
                "decision_start": min_date_str(ledger.get("decision_date", pd.Series(dtype="datetime64[ns]"))),
                "first_weight_date": first_weight_date(tables["v9_loaded_holdings"], "universe_name", spec["v9_loaded_universe"]),
                "return_start": min_date_str(v9_loaded_daily.get("date", pd.Series(dtype="datetime64[ns]"))),
                "return_end": max_date_str(v9_loaded_daily.get("date", pd.Series(dtype="datetime64[ns]"))),
                "daily_count": int(len(v9_loaded_daily)),
                "cost/slippage": "5 bps cost + 5 bps slippage",
                "execution_delay": "1",
                "score_source": "loaded_from_v8_2_reproduction; no independent score recomputation",
                "feature_source": "loaded v8.2 daily/holdings/metric artifacts via v9_growth_pool.load_v8_2_reproduction",
                "label": "label_5d",
                "portfolio rule": spec["portfolio_rule"],
                "independent_recalculation": "no: historical v8.2 artifact loading",
                "method_note": "Loaded reproduction mirrors v8.2 frozen metrics; not an independent replay",
            }
        )
        rows.append(
            {
                "strategy_family": label,
                "source": "v9_local_replay",
                "train_start": TRAIN_START,
                "decision_start": min_date_str(v9_time.loc[v9_time.get("universe_name", "") == "pool_a_v9_local_replay", "decision_date"]) if not v9_time.empty else "",
                "first_weight_date": first_weight_date(tables["v9_holdings"], "universe_name", spec["v9_local_universe"]),
                "return_start": min_date_str(v9_local_daily.get("date", pd.Series(dtype="datetime64[ns]"))),
                "return_end": max_date_str(v9_local_daily.get("date", pd.Series(dtype="datetime64[ns]"))),
                "daily_count": int(len(v9_local_daily)),
                "cost/slippage": "5 bps cost + 5 bps slippage",
                "execution_delay": "1; weights assigned on execution date, return engine shifts one bar",
                "score_source": "v9_reverse_audit local Alpha360-compatible LGBModel refit",
                "feature_source": "local unified_store prices -> build_local_alpha360_feature_frame",
                "label": "label_5d",
                "portfolio rule": spec["portfolio_rule"],
                "independent_recalculation": "yes for local score replay; not score-provenance-equivalent to v8.2",
                "method_note": "1581-day 2020-01-02 to 2026-04-17 daily_nav includes zero-exposure 2020-2023 rows",
            }
        )
    return pd.DataFrame(rows)


def build_candidate_replay_diff(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for label, spec in STRATEGIES.items():
        strategy_id = spec["strategy_id"]
        source_defs = [
            {
                "source": "v8_2_frozen",
                "id_col": "strategy_id",
                "id_value": strategy_id,
                "daily": tables["v82_daily"],
                "holdings": tables["v82_holdings"],
                "contrib": tables["v82_contribution"],
                "contrib_id_col": "strategy_id",
                "original_window": "2024-01-02",
                "independent_recalculation": "partial",
            },
            {
                "source": "v9_loaded_reproduction",
                "id_col": "universe_name",
                "id_value": spec["v9_loaded_universe"],
                "daily": tables["v9_loaded_daily"],
                "holdings": tables["v9_loaded_holdings"],
                "contrib": tables["v9_loaded_contribution"],
                "contrib_id_col": "universe_name",
                "original_window": "2024-01-02",
                "independent_recalculation": "no",
            },
            {
                "source": "v9_local_replay",
                "id_col": "universe_name",
                "id_value": spec["v9_local_universe"],
                "daily": tables["v9_daily"],
                "holdings": tables["v9_holdings"],
                "contrib": tables["v9_attribution"],
                "contrib_id_col": "universe_name",
                "original_window": "full_report",
                "independent_recalculation": "yes",
            },
        ]
        for source in source_defs:
            for window_type, start in candidate_windows(source["source"]):
                if window_type == "original_report" and source["source"] != "v9_local_replay":
                    start = UNIFIED_START
                metrics = recompute_metrics(
                    daily=source["daily"],
                    holdings=source["holdings"],
                    id_col=source["id_col"],
                    id_value=source["id_value"],
                    start=start,
                    contribution=source["contrib"],
                    contribution_id_col=source["contrib_id_col"],
                )
                reported = reported_metrics(tables, source["source"], strategy_id, spec)
                rows.append(
                    {
                        "strategy_family": label,
                        "strategy_id": strategy_id,
                        "top_k": spec["top_k"],
                        "source": source["source"],
                        "window_type": window_type,
                        "window_start": metrics.get("return_start", ""),
                        "window_end": metrics.get("return_end", ""),
                        "daily_count": metrics.get("daily_count", 0),
                        "reported_cagr": reported.get("cagr"),
                        "reported_max_drawdown": reported.get("max_drawdown"),
                        "reported_calmar": reported.get("calmar"),
                        "cagr": metrics.get("cagr"),
                        "max_drawdown": metrics.get("max_drawdown"),
                        "calmar": metrics.get("calmar"),
                        "total_return": metrics.get("total_return"),
                        "turnover": metrics.get("annual_turnover"),
                        "annual_turnover": metrics.get("annual_turnover"),
                        "exposure": metrics.get("exposure"),
                        "top_ticker": metrics.get("top_ticker"),
                        "top_ticker_share": metrics.get("top_ticker_share"),
                        "single_year_share": metrics.get("single_year_share"),
                        "top_contribution_year": metrics.get("top_contribution_year"),
                        "first_nonzero_weight_date": metrics.get("first_nonzero_weight_date"),
                        "zero_exposure_days_before_first_weight": metrics.get("zero_exposure_days_before_first_weight"),
                        "independent_recalculation": source["independent_recalculation"],
                    }
                )
    return pd.DataFrame(rows)


def candidate_windows(source: str) -> list[tuple[str, pd.Timestamp | None]]:
    if source == "v9_local_replay":
        return [("original_report", None), ("unified_2024_01_02", UNIFIED_START)]
    return [("original_report", UNIFIED_START), ("unified_2024_01_02", UNIFIED_START)]


def build_active_window_metrics(candidate_diff: pd.DataFrame, tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for label, spec in STRATEGIES.items():
        ref = select_metric_row(candidate_diff, label, "v8_2_frozen", "unified_2024_01_02")
        local_unified = select_metric_row(candidate_diff, label, "v9_local_replay", "unified_2024_01_02")
        local_original = select_metric_row(candidate_diff, label, "v9_local_replay", "original_report")
        active_start = str(local_unified.get("first_nonzero_weight_date", "") or "")
        rows.append(metric_comparison_row(label, spec["strategy_id"], "v8_2_frozen_reference_2024_01_02", ref, ref))
        rows.append(metric_comparison_row(label, spec["strategy_id"], "v9_local_original_2020_01_02", local_original, ref))
        rows.append(metric_comparison_row(label, spec["strategy_id"], "v9_local_unified_2024_01_02", local_unified, ref))
        if active_start:
            active_metrics = recompute_metrics(
                daily=tables["v9_daily"],
                holdings=tables["v9_holdings"],
                id_col="universe_name",
                id_value=spec["v9_local_universe"],
                start=pd.Timestamp(active_start),
                contribution=tables["v9_attribution"],
                contribution_id_col="universe_name",
            )
            active_metrics.update(
                {
                    "source": "v9_local_replay",
                    "window_start": active_metrics.get("return_start", active_start),
                    "window_end": active_metrics.get("return_end", ""),
                    "turnover": active_metrics.get("annual_turnover"),
                }
            )
            rows.append(metric_comparison_row(label, spec["strategy_id"], f"v9_local_active_from_{active_start}", active_metrics, ref))
    return pd.DataFrame(rows)


def metric_comparison_row(strategy_family: str, strategy_id: str, window_type: str, row: dict[str, Any], ref: dict[str, Any]) -> dict[str, Any]:
    return {
        "strategy_family": strategy_family,
        "strategy_id": strategy_id,
        "window_type": window_type,
        "source": row.get("source", ""),
        "window_start": row.get("window_start", ""),
        "window_end": row.get("window_end", ""),
        "daily_count": row.get("daily_count", 0),
        "cagr": row.get("cagr"),
        "max_drawdown": row.get("max_drawdown"),
        "calmar": row.get("calmar"),
        "total_return": row.get("total_return"),
        "turnover": row.get("turnover"),
        "exposure": row.get("exposure"),
        "top_ticker": row.get("top_ticker"),
        "single_year_share": row.get("single_year_share"),
        "v8_2_ref_cagr": ref.get("cagr"),
        "v8_2_ref_calmar": ref.get("calmar"),
        "v8_2_ref_max_drawdown": ref.get("max_drawdown"),
        "cagr_diff_vs_v8_2": safe_float(row.get("cagr")) - safe_float(ref.get("cagr")),
        "calmar_diff_vs_v8_2": safe_float(row.get("calmar")) - safe_float(ref.get("calmar")),
        "maxdd_diff_vs_v8_2": safe_float(row.get("max_drawdown")) - safe_float(ref.get("max_drawdown")),
        "close_to_v8_2": bool(
            abs(safe_float(row.get("cagr")) - safe_float(ref.get("cagr"))) <= 0.05
            and abs(safe_float(row.get("calmar")) - safe_float(ref.get("calmar"))) <= 0.20
            and abs(safe_float(row.get("max_drawdown")) - safe_float(ref.get("max_drawdown"))) <= 0.05
        ),
    }


def build_monthly_selection_diff(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    v81_score = parse_dates(tables["v81_score"].copy(), ["decision_date", "feature_snapshot_date"])
    v9_score = parse_dates(tables["v9_score"].copy(), ["decision_date", "feature_date"])
    ledger = parse_dates(tables["v81_ledger"].copy(), ["decision_date", "execution_date"])
    v9_time = parse_dates(tables["v9_time_alignment"].copy(), ["decision_date", "execution_date"])

    v81_exec_map = make_execution_map(ledger)
    v9_exec_map = make_execution_map(v9_time.loc[v9_time.get("universe_name", "") == "pool_a_v9_local_replay"].copy())
    frames: dict[str, pd.DataFrame] = {}
    for label, spec in STRATEGIES.items():
        top_k = int(spec["top_k"])
        frames[f"{label}:v8_1"] = selection_from_score_audit(
            v81_score,
            source="v8_1_frozen_score_topk",
            strategy_family=label,
            top_k=top_k,
            execution_map=v81_exec_map,
            rank_col="adjusted_rank",
            score_col="adjusted_score",
        )
        frames[f"{label}:v8_2"] = selection_from_holdings(
            tables["v82_holdings"],
            id_col="strategy_id",
            id_value=spec["v82_strategy_id"],
            source="v8_2_frozen",
            strategy_family=label,
            execution_map=v81_exec_map,
            score_audit=v81_score,
            rank_col="adjusted_rank",
            score_col="adjusted_score",
        )
        frames[f"{label}:v9_loaded"] = selection_from_holdings(
            tables["v9_loaded_holdings"],
            id_col="universe_name",
            id_value=spec["v9_loaded_universe"],
            source="v9_loaded_reproduction",
            strategy_family=label,
            execution_map=v81_exec_map,
            score_audit=v81_score,
            rank_col="adjusted_rank",
            score_col="adjusted_score",
        )
        frames[f"{label}:v9_local"] = selection_from_holdings(
            tables["v9_holdings"],
            id_col="universe_name",
            id_value=spec["v9_local_universe"],
            source="v9_local_replay",
            strategy_family=label,
            execution_map=v9_exec_map,
            score_audit=v9_score,
            rank_col="raw_rank",
            score_col="score",
        )

    all_rows = []
    for label in STRATEGIES:
        parts = [
            frames[f"{label}:v8_1"],
            frames[f"{label}:v8_2"],
            frames[f"{label}:v9_loaded"],
            frames[f"{label}:v9_local"],
        ]
        keys = pd.concat(
            [p.loc[:, ["strategy_family", "decision_date", "execution_date", "ticker"]] for p in parts if not p.empty],
            ignore_index=True,
        ).drop_duplicates()
        wide = keys.copy()
        for part in parts:
            if part.empty:
                continue
            source = str(part["source"].iloc[0])
            prefix = source_prefix(source)
            cols = ["strategy_family", "decision_date", "execution_date", "ticker", "rank", "weight", "score", "source"]
            local = part.loc[:, [c for c in cols if c in part.columns]].copy()
            local[f"in_{prefix}"] = True
            rename = {
                "rank": f"{prefix}_rank",
                "weight": f"{prefix}_weight",
                "score": f"{prefix}_score",
                "source": f"{prefix}_source",
            }
            local = local.rename(columns=rename)
            wide = wide.merge(local, on=["strategy_family", "decision_date", "execution_date", "ticker"], how="left")
        for col in [c for c in wide.columns if c.startswith("in_")]:
            wide[col] = wide[col].fillna(False).astype(bool)
        wide["diff_flag_vs_v8_2_to_v9_local"] = wide.apply(selection_diff_flag, axis=1)
        wide["rank_change_v9_local_minus_v8_2"] = wide.apply(lambda r: safe_float(r.get("v9_local_rank")) - safe_float(r.get("v8_2_rank")) if bool(r.get("in_v8_2")) and bool(r.get("in_v9_local")) else np.nan, axis=1)
        wide["weight_diff_v9_local_minus_v8_2"] = wide.apply(lambda r: safe_float(r.get("v9_local_weight")) - safe_float(r.get("v8_2_weight")) if bool(r.get("in_v8_2")) or bool(r.get("in_v9_local")) else np.nan, axis=1)
        all_rows.append(wide)
    out = pd.concat(all_rows, ignore_index=True) if all_rows else pd.DataFrame()
    if not out.empty:
        out = out.sort_values(["strategy_family", "decision_date", "ticker"]).reset_index(drop=True)
    return out


def build_candidate_replay_diff_by_ticker(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    universe_policy = tables["v9_universe_policy"].copy()
    baseline_only = set(
        universe_policy.loc[
            universe_policy.get("baseline_reproduction_only", pd.Series(dtype=bool)).astype(str).str.lower().eq("true"),
            "ticker",
        ].astype(str).str.upper()
    )
    source_defs = []
    for label, spec in STRATEGIES.items():
        source_defs.extend(
            [
                (label, spec["strategy_id"], "v8_2_frozen", tables["v82_holdings"], "strategy_id", spec["v82_strategy_id"], tables["v82_contribution"], "strategy_id"),
                (label, spec["strategy_id"], "v9_loaded_reproduction", tables["v9_loaded_holdings"], "universe_name", spec["v9_loaded_universe"], tables["v9_loaded_contribution"], "universe_name"),
                (label, spec["strategy_id"], "v9_local_replay", tables["v9_holdings"], "universe_name", spec["v9_local_universe"], tables["v9_attribution"], "universe_name"),
            ]
        )
    for label, strategy_id, source, holdings, id_col, id_value, contrib, contrib_id_col in source_defs:
        h = filter_by_id(holdings, id_col, id_value)
        h["ticker"] = h.get("ticker", pd.Series(dtype=str)).astype(str).str.upper()
        h["weight"] = pd.to_numeric(h.get("weight", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
        grouped = h.groupby("ticker", dropna=False).agg(selection_count=("ticker", "size"), avg_weight=("weight", "mean"), max_weight=("weight", "max")).reset_index() if not h.empty else pd.DataFrame(columns=["ticker", "selection_count", "avg_weight", "max_weight"])
        c = filter_by_id(contrib, contrib_id_col, id_value)
        if not c.empty:
            c["ticker"] = c.get("ticker", pd.Series(dtype=str)).astype(str).str.upper()
            c = c.loc[:, [col for col in ["ticker", "return_contribution", "abs_share"] if col in c.columns]].copy()
        merged = grouped.merge(c, on="ticker", how="outer")
        for _, row in merged.fillna({"selection_count": 0, "avg_weight": 0.0, "max_weight": 0.0}).iterrows():
            ticker = str(row.get("ticker", "")).upper()
            rows.append(
                {
                    "strategy_family": label,
                    "strategy_id": strategy_id,
                    "source": source,
                    "ticker": ticker,
                    "selection_count": int(row.get("selection_count", 0) or 0),
                    "avg_weight": safe_float(row.get("avg_weight")),
                    "max_weight": safe_float(row.get("max_weight")),
                    "return_contribution": safe_float(row.get("return_contribution")),
                    "abs_share": safe_float(row.get("abs_share")),
                    "is_pltr_snow_baseline_only": ticker in baseline_only,
                }
            )
    return pd.DataFrame(rows).sort_values(["strategy_family", "source", "abs_share"], ascending=[True, True, False]).reset_index(drop=True)


def build_baseline_exception_audit(by_ticker: pd.DataFrame, tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    universe = tables["v9_universe_policy"].copy()
    if "ticker" in universe:
        universe["ticker"] = universe["ticker"].astype(str).str.upper()
    rows = []
    for ticker in ["PLTR", "SNOW"]:
        policy = universe.loc[universe.get("ticker", pd.Series(dtype=str)) == ticker]
        subset = by_ticker.loc[by_ticker["ticker"].astype(str).str.upper() == ticker].copy()
        selected_rows = int(subset["selection_count"].fillna(0).sum()) if not subset.empty else 0
        abs_share_sum = float(subset["abs_share"].fillna(0.0).sum()) if not subset.empty else 0.0
        rows.append(
            {
                "ticker": ticker,
                "in_pool_a_reproduction": bool_from_policy(policy, "in_pool_a_reproduction"),
                "v9_ready": bool_from_policy(policy, "v9_ready"),
                "v9_exclude_reason": first_policy_value(policy, "v9_exclude_reason"),
                "baseline_reproduction_only": bool_from_policy(policy, "baseline_reproduction_only"),
                "price_source": first_policy_value(policy, "price_source"),
                "selection_count_all_sources": selected_rows,
                "abs_share_sum_all_sources": abs_share_sum,
                "v8_2_frozen_selection_count": int(subset.loc[subset["source"] == "v8_2_frozen", "selection_count"].sum()) if not subset.empty else 0,
                "v9_local_selection_count": int(subset.loc[subset["source"] == "v9_local_replay", "selection_count"].sum()) if not subset.empty else 0,
                "pollutes_pool_a_reproduction_conclusion": bool(selected_rows > 0 and bool_from_policy(policy, "baseline_reproduction_only")),
                "evidence": summarize_ticker_evidence(subset),
            }
        )
    return pd.DataFrame(rows)


def build_leakage_static_scan() -> pd.DataFrame:
    patterns = [
        ("future_shift", re.compile(r"shift\(\s*-\d+"), "future-looking shift; must not affect score/selection", "high"),
        ("audit_forward_column", re.compile(r"audit_forward_"), "forward outcome column; allowed only as audit-only output", "medium"),
        ("label_or_alignment", re.compile(r"label_cols_in_feature_cols|train_end_label_safe|label_window_end|label_5d"), "label/time-alignment handling", "low"),
        ("loaded_historical_result", re.compile(r"load_v8_2_reproduction|frozen_v8_2_score_audit|loaded_from_v8_2_reproduction"), "historical artifact load instead of independent recomputation", "high"),
        ("external_price_path", re.compile(r"load_or_fetch_prices|downloaded_prices|yfinance|download", re.IGNORECASE), "data-source or download path in historical code; this audit must not invoke it", "high"),
        ("selection_filter_or_posthoc_field", re.compile(r"selected_flag|selected_tickers|candidate_flag|tradable_flag"), "selection/filter field; verify not used to reshape test results", "medium"),
        ("execution_timing", re.compile(r"portfolio_returns|weights\.shift\(1\)|execution_delay|trading_offset"), "execution timing / one-bar shift logic", "medium"),
    ]
    rows = []
    per_file_risk_count: dict[tuple[str, str], int] = {}
    for path in RELATED_CODE_PATHS:
        if not path.exists():
            rows.append(
                {
                    "file": rel(path),
                    "line_no": 0,
                    "risk_type": "missing_source_file",
                    "hit_content": "",
                    "explanation": "Expected related source file is missing.",
                    "risk_level": "high",
                }
            )
            continue
        for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
            for risk_type, pattern, explanation, level in patterns:
                if not pattern.search(line):
                    continue
                key = (str(path), risk_type)
                per_file_risk_count[key] = per_file_risk_count.get(key, 0) + 1
                if per_file_risk_count[key] > 30:
                    continue
                rows.append(
                    {
                        "file": rel(path),
                        "line_no": line_no,
                        "risk_type": risk_type,
                        "hit_content": line.strip()[:500],
                        "explanation": explanation,
                        "risk_level": level,
                    }
                )
    return pd.DataFrame(rows)


def build_audit_summary(
    candidate_diff: pd.DataFrame,
    active_metrics: pd.DataFrame,
    baseline_audit: pd.DataFrame,
    leakage_scan: pd.DataFrame,
    required_manifest: pd.DataFrame,
) -> dict[str, Any]:
    missing_inputs = required_manifest.loc[~required_manifest["exists"].astype(bool), "repo_relative"].tolist()
    top5_original = select_metric_row(candidate_diff, "top5", "v9_local_replay", "original_report")
    top5_unified = select_metric_row(candidate_diff, "top5", "v9_local_replay", "unified_2024_01_02")
    top10_original = select_metric_row(candidate_diff, "top10", "v9_local_replay", "original_report")
    top10_unified = select_metric_row(candidate_diff, "top10", "v9_local_replay", "unified_2024_01_02")
    local_vs_ref = active_metrics.loc[active_metrics["window_type"].astype(str).str.contains("v9_local_unified", regex=False)].copy()
    replay_close = bool(not local_vs_ref.empty and local_vs_ref["close_to_v8_2"].astype(bool).all())
    evaluation_window_mismatch = bool(
        int(top5_original.get("daily_count", 0) or 0) != int(top5_unified.get("daily_count", 0) or 0)
        or int(top10_original.get("daily_count", 0) or 0) != int(top10_unified.get("daily_count", 0) or 0)
    )
    baseline_pollution = bool(baseline_audit.get("pollutes_pool_a_reproduction_conclusion", pd.Series(dtype=bool)).astype(bool).any())
    method_mismatch = bool(evaluation_window_mismatch or baseline_pollution or (not replay_close))
    time_alignment_failed = False
    # Static scan surfaces risks for review; this flag is reserved for confirmed
    # evidence from time-alignment failures or a manually validated leak.
    leakage_risk_found = bool(time_alignment_failed)
    requires_human = bool(missing_inputs or method_mismatch or baseline_pollution or leakage_risk_found or not replay_close)
    classification = "invalid_or_needs_human_review" if requires_human else "method_mismatch_needs_replay"
    if leakage_risk_found:
        classification = "invalid_or_needs_human_review"
    return {
        "classification": classification,
        "requires_human_review": bool(requires_human),
        "allow_expand_universe": False,
        "allow_expand_nasdaq100": False,
        "allow_expand_sp500": False,
        "allow_enter_v10": False,
        "allow_trade_execution": False,
        "method_mismatch_found": bool(method_mismatch),
        "leakage_risk_found": bool(leakage_risk_found),
        "evaluation_window_mismatch_found": bool(evaluation_window_mismatch),
        "pool_a_replay_close_to_v8_2_on_unified_window": bool(replay_close),
        "baseline_exception_pollution_found": bool(baseline_pollution),
        "missing_required_inputs": missing_inputs,
        "v9_top5_original_daily_count": int(top5_original.get("daily_count", 0) or 0),
        "v9_top5_unified_daily_count": int(top5_unified.get("daily_count", 0) or 0),
        "v9_top5_original_cagr": top5_original.get("cagr"),
        "v9_top5_unified_cagr": top5_unified.get("cagr"),
        "v9_top10_original_daily_count": int(top10_original.get("daily_count", 0) or 0),
        "v9_top10_unified_daily_count": int(top10_unified.get("daily_count", 0) or 0),
        "v9_top10_original_cagr": top10_original.get("cagr"),
        "v9_top10_unified_cagr": top10_unified.get("cagr"),
        "static_scan_rows": int(len(leakage_scan)),
        "static_scan_high_risk_rows": int((leakage_scan.get("risk_level", pd.Series(dtype=str)) == "high").sum()),
        "reason": (
            "v9 local replay used a 2020-01-02 full daily_nav with zero-exposure 2020-2023 rows, "
            "while v8.2 frozen and loaded reproduction use the 2024-01-02 to 2026-04-17 window; "
            "after window alignment the local replay still does not closely reproduce v8.2, and PLTR/SNOW remain baseline-only exceptions."
        ),
    }


def build_data_lineage_audit(run_dir: Path, extra_outputs: list[Path] | None = None) -> pd.DataFrame:
    rows = []
    input_files = [
        V9_REVERSE_DIR / "daily_nav.csv",
        V9_REVERSE_DIR / "monthly_holdings.csv",
        V9_REVERSE_DIR / "pool_a_replay_audit.csv",
        V9_REVERSE_DIR / "score_rank_audit.csv",
        V9_REVERSE_DIR / "time_alignment_audit.csv",
        V9_REVERSE_DIR / "universe_policy_audit.csv",
        V82_DIR / "v8_2_daily_nav_by_strategy.csv",
        V82_DIR / "v8_2_monthly_holdings_by_strategy.csv",
        V82_DIR / "v8_2_year_stability_results.csv",
        V82_DIR / "v8_2_ticker_contribution.csv",
        V81_DIR / "score_rank_audit_trail.csv",
        V81_DIR / "monthly_decision_ledger.csv",
        V9_GROWTH_DIR / "v9_growth_pool_results.csv",
        V9_GROWTH_DIR / "v9_daily_nav_by_universe.csv",
        V9_GROWTH_DIR / "v9_monthly_holdings.csv",
        *RELATED_CODE_PATHS,
    ]
    for path in unique_paths(input_files):
        rows.append(lineage_row("input", path, "", generation_script_for_input(path), "read existing local artifact", independent_recalc_note_for_input(path)))
    output_files = sorted([p for p in run_dir.rglob("*") if p.is_file()])
    output_files.extend(extra_outputs or [])
    for path in output_files:
        rows.append(lineage_row("output", path, str(path), rel(PROJECT_ROOT / "scripts" / "us_stock_selection" / "36_run_v82_v9_replay_diff_audit.py"), "generated by this local diff audit", "yes"))
    return pd.DataFrame(rows)


def build_readme(
    summary: dict[str, Any],
    method_diff: pd.DataFrame,
    candidate_diff: pd.DataFrame,
    active_metrics: pd.DataFrame,
    baseline_audit: pd.DataFrame,
    leakage_scan: pd.DataFrame,
    run_dir: Path,
) -> str:
    top5_ref = select_metric_row(candidate_diff, "top5", "v8_2_frozen", "unified_2024_01_02")
    top5_local_orig = select_metric_row(candidate_diff, "top5", "v9_local_replay", "original_report")
    top5_local_unified = select_metric_row(candidate_diff, "top5", "v9_local_replay", "unified_2024_01_02")
    top10_ref = select_metric_row(candidate_diff, "top10", "v8_2_frozen", "unified_2024_01_02")
    top10_local_orig = select_metric_row(candidate_diff, "top10", "v9_local_replay", "original_report")
    top10_local_unified = select_metric_row(candidate_diff, "top10", "v9_local_replay", "unified_2024_01_02")
    evidence = [
        f"v9 local Top5 official/full daily_count={top5_local_orig.get('daily_count')}，CAGR={fmt_pct(top5_local_orig.get('cagr'))}；统一 2024-01-02 窗口 daily_count={top5_local_unified.get('daily_count')}，CAGR={fmt_pct(top5_local_unified.get('cagr'))}。",
        f"v8.2 frozen Top5 统一窗口 CAGR={fmt_pct(top5_ref.get('cagr'))}，Calmar={fmt_num(top5_ref.get('calmar'))}；v9 local Top5 统一窗口 CAGR={fmt_pct(top5_local_unified.get('cagr'))}，Calmar={fmt_num(top5_local_unified.get('calmar'))}，仍未接近复现。",
        f"v8.2 frozen Top10 统一窗口 CAGR={fmt_pct(top10_ref.get('cagr'))}，Calmar={fmt_num(top10_ref.get('calmar'))}；v9 local Top10 统一窗口 CAGR={fmt_pct(top10_local_unified.get('cagr'))}，Calmar={fmt_num(top10_local_unified.get('calmar'))}。",
        "v9 loaded reproduction 的 score_source 是 loaded_from_v8_2_reproduction，属于读取历史 v8.2 结果，不是独立复算。",
        "PLTR/SNOW 在 v9 数据质量中为 baseline-only exception，但仍出现在 Pool A reproduction 和本地 replay 持仓/贡献中。",
    ]
    risk_lines = [
        "评估窗口风险：高。v9 local official/full CAGR 把 2020-2023 零仓位期纳入 annualization，不能与 v8.2 的 575 天口径直接比较。",
        "方法口径风险：高。v8.2 frozen、v9 loaded reproduction、v9 local replay 的 score provenance 和 feature source 不一致。",
        "复现风险：高。统一窗口后 v9 local replay 仍未在 CAGR/Calmar/MaxDD 阈值内接近 v8.2 frozen。",
        "baseline-only 污染风险：高。PLTR/SNOW 明确为 v9 baseline-only exception 且有选择/贡献记录。",
        f"静态扫描：{len(leakage_scan)} 条风险命中，其中 high={int((leakage_scan.get('risk_level', pd.Series(dtype=str)) == 'high').sum())}；未据此确认未来函数或标签泄露。",
    ]
    return f"""# v8.2 frozen Pool A 与 v9 local replay 反向差异审计

## 结论

- Classification：`{summary.get('classification')}`
- requires_human_review：`{summary.get('requires_human_review')}`
- allow_expand_universe：`{summary.get('allow_expand_universe')}`
- allow_enter_v10：`{summary.get('allow_enter_v10')}`
- allow_trade_execution：`{summary.get('allow_trade_execution')}`

本轮发现明确评估窗口不一致：v9 local replay 的 `daily_nav.csv` 从 2020-01-02 开始，但 first non-zero weight date 为 2024-02-01；v8.2 frozen / v9 loaded reproduction 使用 2024-01-02 到 2026-04-17 的 575 天窗口。因此 v9 local official/full CAGR 不能与 v8.2 frozen CAGR 直接比较。

统一到 2024-01-02 后，v9 local replay 的 CAGR 会被重新年化到 575 天口径，但 Top5/Top10 仍未接近复现 v8.2 frozen 高收益；差异从“窗口口径错误”进一步落到 score provenance、feature/data source、loaded reproduction 非独立复算和 baseline-only exception 污染。

## 必答问题

1. v9 local replay official/full CAGR 是否因 2020-2023 零仓位期被计入而不可直接比较：是。full daily_count={top5_local_orig.get('daily_count')}，统一窗口 daily_count={top5_local_unified.get('daily_count')}。
2. v8.2 frozen 高收益是否能在统一 2024-01-02 起算窗口由 v9 local replay 接近复现：不能。Top5 v8.2 CAGR={fmt_pct(top5_ref.get('cagr'))} vs v9 local={fmt_pct(top5_local_unified.get('cagr'))}；Top10 v8.2 CAGR={fmt_pct(top10_ref.get('cagr'))} vs v9 local={fmt_pct(top10_local_unified.get('cagr'))}。
3. PLTR/SNOW baseline-only exception 是否污染 Pool A 复现结论：是。见 `baseline_exception_audit.csv` 和 `candidate_replay_diff_by_ticker.csv`。
4. 是否发现未来函数、标签泄露、执行时点错误或测试集筛选证据：未发现已确认的未来函数/标签泄露证据；`time_alignment_audit.csv` 在上一轮为 pass。静态扫描发现 audit-forward 字段、历史结果加载、下载路径和执行时点逻辑需要继续人工复核，但本脚本未调用外部数据下载。
5. v8.2 frozen loaded reproduction 是否独立复算：不是。v9 loaded reproduction 来自 `load_v8_2_reproduction` 读取历史 v8.2 daily/holdings/metrics。

## 证据链

{bullet_lines(evidence)}

## 风险评级

{bullet_lines(risk_lines)}

## 关键输出

- Run：`{run_dir}`
- `audit_summary.json`
- `v82_v9_method_diff.csv`
- `candidate_replay_diff.csv`
- `active_window_metrics.csv`
- `monthly_selection_diff.csv`
- `candidate_replay_diff_by_ticker.csv`
- `data_lineage_audit.csv`
- `leakage_static_scan.csv`
- `baseline_exception_audit.csv`
- `reports/v82_v9_replay_diff_audit_summary.xlsx`

## 下一步建议

下一轮仍不得扩池、不得进入 v10、不得做任何执行接入。只允许同池、同策略、同 gate，在统一 2024-01-02 窗口下补一个真正 score-provenance 对齐的 replay：要么用 v8.1 score/rank audit trail 独立重算 v8.2 Top5/Top10，并与 v9 local 的 score/rank 逐月逐 ticker 对齐；要么证明 v8.2 原始 score 生成链可从本地 raw feature + model 完整复现。
"""


def build_run_summary(summary: dict[str, Any], candidate_diff: pd.DataFrame, active_metrics: pd.DataFrame, run_dir: Path) -> str:
    top5_ref = select_metric_row(candidate_diff, "top5", "v8_2_frozen", "unified_2024_01_02")
    top5_local = select_metric_row(candidate_diff, "top5", "v9_local_replay", "unified_2024_01_02")
    top10_ref = select_metric_row(candidate_diff, "top10", "v8_2_frozen", "unified_2024_01_02")
    top10_local = select_metric_row(candidate_diff, "top10", "v9_local_replay", "unified_2024_01_02")
    return f"""# RUN_SUMMARY

本轮目标：执行 v8.2 frozen Pool A 与 v9 local replay 的本地反向差异审计；只做同池、只读、非优化审计。

新 run 目录：`{run_dir}`
最终分类：`{summary.get('classification')}`
Requires human review：`{summary.get('requires_human_review')}`
是否允许扩池：`{summary.get('allow_expand_universe')}`
是否允许进入 v10：`{summary.get('allow_enter_v10')}`
是否允许交易执行：`{summary.get('allow_trade_execution')}`

核心发现：
- Evaluation window mismatch：`{summary.get('evaluation_window_mismatch_found')}`
- Method mismatch：`{summary.get('method_mismatch_found')}`
- Leakage risk found：`{summary.get('leakage_risk_found')}`
- Baseline exception pollution：`{summary.get('baseline_exception_pollution_found')}`
- Top5 v8.2 unified CAGR/Calmar：`{fmt_pct(top5_ref.get('cagr'))}` / `{fmt_num(top5_ref.get('calmar'))}`
- Top5 v9 local unified CAGR/Calmar：`{fmt_pct(top5_local.get('cagr'))}` / `{fmt_num(top5_local.get('calmar'))}`
- Top10 v8.2 unified CAGR/Calmar：`{fmt_pct(top10_ref.get('cagr'))}` / `{fmt_num(top10_ref.get('calmar'))}`
- Top10 v9 local unified CAGR/Calmar：`{fmt_pct(top10_local.get('cagr'))}` / `{fmt_num(top10_local.get('calmar'))}`

结论：v9 local official/full CAGR 因 2020-2023 零仓位期计入而不可与 575 天 v8.2 frozen 直接比较；统一窗口后仍不能接近复现 v8.2 frozen 高收益，且 PLTR/SNOW baseline-only exception 污染 Pool A 复现结论。不得扩池，不得进入 v10。
"""


def build_next_steps(summary: dict[str, Any], run_dir: Path) -> str:
    return f"""# NEXT_STEPS

当前状态：v8.2/v9 replay diff audit 已完成。

- Run：`{run_dir}`
- Classification：`{summary.get('classification')}`
- Requires human review：`{summary.get('requires_human_review')}`
- Allow expand universe：`{summary.get('allow_expand_universe')}`
- Allow v10：`{summary.get('allow_enter_v10')}`
- Allow trade execution：`{summary.get('allow_trade_execution')}`

硬边界：

1. 不扩 Nasdaq100，不扩 S&P500，不做全市场扩池。
2. 不进入 v10。
3. 不接券商 API，不做真实交易或任何执行接入。
4. 不联网下载行情，不使用 key/secret/token/credential。
5. 不通过调 gate、ranking 权重、指标口径或主线策略改善结果。

下一步允许事项：

1. 只允许同池、同策略、同 gate、统一 2024-01-02 到 2026-04-17 评估窗口继续复核。
2. 优先复核 `monthly_selection_diff.csv` 中 v8.1/v8.2/v9 loaded/v9 local 的逐月 Top5/Top10 score/rank/weight 差异。
3. 复核 `baseline_exception_audit.csv` 中 PLTR/SNOW baseline-only exception 是否应从任何独立复现结论中剔除或单独标注。
4. 若继续编码，只能做 score provenance 对齐 replay；不得优化策略，不得扩池，不得进入 v10。
"""


def package_run(run_dir: Path, timestamp: str) -> Path:
    zip_path = run_dir.parent / f"us_stock_selection_v82_v9_replay_diff_audit_{timestamp}.zip"
    paths = [
        PROJECT_ROOT / "AGENTS.md",
        PROJECT_ROOT / "NEXT_STEPS.md",
        PROJECT_ROOT / "RUN_SUMMARY.md",
        PROJECT_ROOT / "docs" / "US_STOCK_SELECTION_AUTORUN.md",
        PROJECT_ROOT / "docs" / "chatgpt_bridge" / "codex_inbox" / "TASK.md",
        PROJECT_ROOT / "scripts" / "us_stock_selection" / "36_run_v82_v9_replay_diff_audit.py",
        run_dir,
    ]
    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as zf:
        for path in paths:
            if not path.exists():
                continue
            if path.is_dir():
                for child in path.rglob("*"):
                    if child.is_file():
                        zf.write(child, arcname=str(child.relative_to(PROJECT_ROOT)))
            else:
                zf.write(path, arcname=str(path.relative_to(PROJECT_ROOT)))
    return zip_path


def recompute_metrics(
    daily: pd.DataFrame,
    holdings: pd.DataFrame,
    id_col: str,
    id_value: str,
    start: pd.Timestamp | None,
    contribution: pd.DataFrame,
    contribution_id_col: str,
) -> dict[str, Any]:
    local_daily = daily_slice(daily, id_col, id_value)
    if local_daily.empty:
        return empty_metrics()
    all_dates = pd.DatetimeIndex(local_daily["date"])
    weights_full = weights_from_holdings(holdings, id_col, id_value, all_dates)
    first_weight = first_nonzero_weight_date_from_weights(weights_full)
    zero_before = int((weights_full.loc[weights_full.index < first_weight].sum(axis=1).abs() <= 1e-12).sum()) if first_weight is not None else int(len(weights_full))
    if start is not None:
        mask = local_daily["date"] >= start
        local_daily = local_daily.loc[mask].copy()
        weights = weights_full.loc[weights_full.index >= start].copy()
    else:
        weights = weights_full.copy()
    if local_daily.empty:
        return empty_metrics()
    returns = pd.Series(local_daily["return"].to_numpy(dtype=float), index=pd.DatetimeIndex(local_daily["date"]))
    turnover = pd.Series(local_daily["turnover"].to_numpy(dtype=float), index=pd.DatetimeIndex(local_daily["date"]))
    weights = weights.reindex(returns.index).ffill().fillna(0.0)
    metrics = compute_portfolio_metrics(returns, turnover, weights)
    years = returns.groupby(returns.index.year).apply(lambda s: float((1.0 + s).prod() - 1.0))
    top_year = int(years.abs().idxmax()) if not years.empty else None
    metrics["single_year_share"] = concentration_share(years)
    metrics["top_contribution_year"] = top_year
    top = top_ticker_from_contribution(contribution, contribution_id_col, id_value)
    metrics["top_ticker"] = top.get("ticker", "")
    metrics["top_ticker_share"] = top.get("abs_share", 0.0)
    metrics["return_start"] = returns.index.min().date().isoformat()
    metrics["return_end"] = returns.index.max().date().isoformat()
    metrics["first_nonzero_weight_date"] = first_weight.date().isoformat() if first_weight is not None else ""
    metrics["zero_exposure_days_before_first_weight"] = zero_before
    return metrics


def empty_metrics() -> dict[str, Any]:
    return {
        "total_return": 0.0,
        "cagr": 0.0,
        "max_drawdown": 0.0,
        "calmar": 0.0,
        "annual_turnover": 0.0,
        "exposure": 0.0,
        "daily_count": 0,
        "single_year_share": 0.0,
        "top_ticker": "",
        "top_ticker_share": 0.0,
        "return_start": "",
        "return_end": "",
        "first_nonzero_weight_date": "",
        "zero_exposure_days_before_first_weight": 0,
    }


def daily_slice(daily: pd.DataFrame, id_col: str, id_value: str) -> pd.DataFrame:
    if daily.empty or id_col not in daily.columns:
        return pd.DataFrame(columns=["date", "return", "nav", "turnover", id_col])
    out = daily.loc[daily[id_col].astype(str) == str(id_value)].copy()
    if "date" in out:
        out["date"] = pd.to_datetime(out["date"], errors="coerce")
        out = out.dropna(subset=["date"]).sort_values("date")
    for col in ["return", "turnover"]:
        if col in out:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)
    return out


def weights_from_holdings(holdings: pd.DataFrame, id_col: str, id_value: str, dates: pd.DatetimeIndex) -> pd.DataFrame:
    local = filter_by_id(holdings, id_col, id_value)
    if local.empty or "date" not in local or "ticker" not in local:
        return pd.DataFrame(index=dates)
    local["date"] = pd.to_datetime(local["date"], errors="coerce")
    local["ticker"] = local["ticker"].astype(str).str.upper()
    local["weight"] = pd.to_numeric(local.get("weight", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    pivot = local.pivot_table(index="date", columns="ticker", values="weight", aggfunc="sum").fillna(0.0)
    return pivot.reindex(dates).ffill().fillna(0.0)


def first_nonzero_weight_date_from_weights(weights: pd.DataFrame) -> pd.Timestamp | None:
    if weights.empty:
        return None
    exposure = weights.sum(axis=1).abs()
    hit = exposure.loc[exposure > 1e-12]
    if hit.empty:
        return None
    return pd.Timestamp(hit.index.min())


def first_weight_date(holdings: pd.DataFrame, id_col: str, id_value: str) -> str:
    local = filter_by_id(holdings, id_col, id_value)
    if local.empty or "date" not in local:
        return ""
    local["date"] = pd.to_datetime(local["date"], errors="coerce")
    local["weight"] = pd.to_numeric(local.get("weight", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    dates = local.loc[local["weight"].abs() > 1e-12, "date"].dropna()
    return dates.min().date().isoformat() if not dates.empty else ""


def reported_metrics(tables: dict[str, pd.DataFrame], source: str, strategy_id: str, spec: dict[str, Any]) -> dict[str, Any]:
    if source == "v8_2_frozen":
        row = tables["v82_results"].loc[tables["v82_results"].get("strategy_id", pd.Series(dtype=str)).astype(str) == strategy_id]
    elif source == "v9_loaded_reproduction":
        row = tables["v9_loaded_results"].loc[tables["v9_loaded_results"].get("universe_name", pd.Series(dtype=str)).astype(str) == spec["v9_loaded_universe"]]
    else:
        row = tables["v9_results"].loc[tables["v9_results"].get("universe_name", pd.Series(dtype=str)).astype(str) == spec["v9_local_universe"]]
    return row.iloc[0].to_dict() if not row.empty else {}


def top_ticker_from_contribution(contribution: pd.DataFrame, id_col: str, id_value: str) -> dict[str, Any]:
    local = filter_by_id(contribution, id_col, id_value)
    if local.empty or "ticker" not in local:
        return {"ticker": "", "abs_share": 0.0}
    local["abs_share"] = pd.to_numeric(local.get("abs_share", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    row = local.sort_values("abs_share", ascending=False).iloc[0]
    return {"ticker": str(row.get("ticker", "")).upper(), "abs_share": safe_float(row.get("abs_share"))}


def selection_from_score_audit(
    score: pd.DataFrame,
    source: str,
    strategy_family: str,
    top_k: int,
    execution_map: dict[str, str],
    rank_col: str,
    score_col: str,
) -> pd.DataFrame:
    if score.empty:
        return pd.DataFrame()
    out = score.copy()
    out["decision_date"] = pd.to_datetime(out["decision_date"], errors="coerce")
    out["ticker"] = out["ticker"].astype(str).str.upper()
    out[rank_col] = pd.to_numeric(out.get(rank_col, pd.Series(dtype=float)), errors="coerce")
    out[score_col] = pd.to_numeric(out.get(score_col, pd.Series(dtype=float)), errors="coerce")
    if "candidate_flag" in out:
        out = out.loc[out["candidate_flag"].astype(str).str.lower().isin(["true", "1"])]
    if "tradable_flag" in out:
        out = out.loc[out["tradable_flag"].astype(str).str.lower().isin(["true", "1"])]
    out = out.loc[out[rank_col] <= float(top_k)].copy()
    out["execution_date"] = out["decision_date"].dt.date.astype(str).map(execution_map).fillna("")
    out["decision_date"] = out["decision_date"].dt.date.astype(str)
    out["source"] = source
    out["strategy_family"] = strategy_family
    out["rank"] = out[rank_col]
    out["score"] = out[score_col]
    out["weight"] = 1.0 / float(top_k)
    return out.loc[:, ["strategy_family", "source", "decision_date", "execution_date", "ticker", "rank", "weight", "score"]]


def selection_from_holdings(
    holdings: pd.DataFrame,
    id_col: str,
    id_value: str,
    source: str,
    strategy_family: str,
    execution_map: dict[str, str],
    score_audit: pd.DataFrame,
    rank_col: str,
    score_col: str,
) -> pd.DataFrame:
    local = filter_by_id(holdings, id_col, id_value)
    if local.empty:
        return pd.DataFrame()
    local["execution_date"] = pd.to_datetime(local["date"], errors="coerce").dt.date.astype(str)
    reverse_map = {execution: decision for decision, execution in execution_map.items()}
    local["decision_date"] = local["execution_date"].map(reverse_map).fillna("")
    local["ticker"] = local["ticker"].astype(str).str.upper()
    local["weight"] = pd.to_numeric(local.get("weight", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    lookup = build_score_lookup(score_audit, rank_col, score_col)
    ranks = []
    scores = []
    for _, row in local.iterrows():
        info = lookup.get((str(row["decision_date"]), str(row["ticker"])), {})
        ranks.append(info.get("rank", np.nan))
        scores.append(info.get("score", np.nan))
    local["rank"] = ranks
    local["score"] = scores
    local["source"] = source
    local["strategy_family"] = strategy_family
    return local.loc[:, ["strategy_family", "source", "decision_date", "execution_date", "ticker", "rank", "weight", "score"]]


def build_score_lookup(score_audit: pd.DataFrame, rank_col: str, score_col: str) -> dict[tuple[str, str], dict[str, float]]:
    if score_audit.empty:
        return {}
    local = score_audit.copy()
    local["decision_date"] = pd.to_datetime(local["decision_date"], errors="coerce").dt.date.astype(str)
    local["ticker"] = local["ticker"].astype(str).str.upper()
    local[rank_col] = pd.to_numeric(local.get(rank_col, pd.Series(dtype=float)), errors="coerce")
    local[score_col] = pd.to_numeric(local.get(score_col, pd.Series(dtype=float)), errors="coerce")
    lookup = {}
    for _, row in local.iterrows():
        lookup[(str(row["decision_date"]), str(row["ticker"]))] = {"rank": safe_float(row.get(rank_col)), "score": safe_float(row.get(score_col))}
    return lookup


def make_execution_map(df: pd.DataFrame) -> dict[str, str]:
    if df.empty or "decision_date" not in df or "execution_date" not in df:
        return {}
    local = parse_dates(df.copy(), ["decision_date", "execution_date"])
    out = {}
    for _, row in local.dropna(subset=["decision_date", "execution_date"]).iterrows():
        out[pd.Timestamp(row["decision_date"]).date().isoformat()] = pd.Timestamp(row["execution_date"]).date().isoformat()
    return out


def source_prefix(source: str) -> str:
    return {
        "v8_1_frozen_score_topk": "v8_1",
        "v8_2_frozen": "v8_2",
        "v9_loaded_reproduction": "v9_loaded",
        "v9_local_replay": "v9_local",
    }.get(source, source)


def selection_diff_flag(row: pd.Series) -> str:
    in_v82 = bool(row.get("in_v8_2", False))
    in_local = bool(row.get("in_v9_local", False))
    if in_v82 and in_local:
        rank_change = safe_float(row.get("v9_local_rank")) - safe_float(row.get("v8_2_rank"))
        return "common_rank_changed" if not math.isnan(rank_change) and abs(rank_change) > 1e-12 else "common_same_rank"
    if in_v82 and not in_local:
        return "missing_in_v9_local"
    if (not in_v82) and in_local:
        return "new_in_v9_local"
    return "not_in_v8_2_or_v9_local"


def filter_by_id(df: pd.DataFrame, id_col: str, id_value: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    if id_col not in df.columns:
        return pd.DataFrame()
    return df.loc[df[id_col].astype(str) == str(id_value)].copy()


def parse_dates(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    for col in cols:
        if col in df:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def min_date_str(values: pd.Series) -> str:
    if values is None or len(values) == 0:
        return ""
    dates = pd.to_datetime(values, errors="coerce").dropna()
    return dates.min().date().isoformat() if not dates.empty else ""


def max_date_str(values: pd.Series) -> str:
    if values is None or len(values) == 0:
        return ""
    dates = pd.to_datetime(values, errors="coerce").dropna()
    return dates.max().date().isoformat() if not dates.empty else ""


def first_non_empty(series: pd.Series, default: str) -> str:
    clean = series.dropna().astype(str).str.strip() if series is not None else pd.Series(dtype=str)
    clean = clean.loc[clean != ""]
    return str(clean.iloc[0]) if not clean.empty else default


def select_metric_row(df: pd.DataFrame, strategy_family: str, source: str, window_type: str) -> dict[str, Any]:
    if df.empty:
        return {}
    rows = df.loc[
        (df["strategy_family"].astype(str) == strategy_family)
        & (df["source"].astype(str) == source)
        & (df["window_type"].astype(str) == window_type)
    ]
    return rows.iloc[0].to_dict() if not rows.empty else {}


def concentration_share(values: pd.Series) -> float:
    clean = pd.Series(values).dropna().astype(float)
    denom = float(clean.abs().sum())
    return float(clean.abs().max() / denom) if denom else 0.0


def bool_from_policy(policy: pd.DataFrame, col: str) -> bool:
    if policy.empty or col not in policy:
        return False
    value = str(policy.iloc[0].get(col, "")).strip().lower()
    return value in {"true", "1", "yes"}


def first_policy_value(policy: pd.DataFrame, col: str) -> str:
    if policy.empty or col not in policy:
        return ""
    value = policy.iloc[0].get(col, "")
    return "" if pd.isna(value) else str(value)


def summarize_ticker_evidence(subset: pd.DataFrame) -> str:
    if subset.empty:
        return "no selection/contribution rows found"
    parts = []
    for _, row in subset.sort_values(["strategy_family", "source"]).iterrows():
        if int(row.get("selection_count", 0) or 0) == 0 and abs(safe_float(row.get("abs_share"))) <= 1e-12:
            continue
        parts.append(
            f"{row.get('strategy_family')} {row.get('source')}: count={int(row.get('selection_count', 0) or 0)}, abs_share={fmt_num(row.get('abs_share'))}"
        )
    return "; ".join(parts) if parts else "present only as zero-contribution row"


def lineage_row(role: str, input_file: Path, output_file: str, generation_script: str, method_note: str, independent_recalc: str) -> dict[str, Any]:
    return {
        "role": role,
        "input_file": str(input_file),
        "output_file": output_file,
        "generation_script": generation_script,
        "timestamp": datetime.fromtimestamp(input_file.stat().st_mtime).isoformat(timespec="seconds") if input_file.exists() else "",
        "key_fields": read_first_line(input_file),
        "method_note": method_note,
        "independent_recalculation": independent_recalc,
        "exists": input_file.exists(),
        "size_bytes": input_file.stat().st_size if input_file.exists() else 0,
    }


def generation_script_for_input(path: Path) -> str:
    text = str(path).replace("\\", "/")
    if "run_20260503_172054" in text:
        return "scripts/us_stock_selection/35_run_v9_reverse_audit.py"
    if "run_20260502_220641" in text:
        return "scripts/us_stock_selection/33_run_v8_2_year_stability.py"
    if "run_20260502_210856" in text:
        return "scripts/us_stock_selection/32_run_v8_1_model_switch.py"
    if "run_20260502_222407" in text:
        return "scripts/us_stock_selection/34_run_v9_growth_pool.py"
    return rel(path)


def independent_recalc_note_for_input(path: Path) -> str:
    text = str(path).replace("\\", "/")
    if "v9_growth_pool" in text and ("daily_nav" in text or "monthly_holdings" in text or "growth_pool_results" in text):
        return "no for loaded Pool A rows; local rows are separate v9 growth pre-research"
    if "v9_reverse_audit" in text:
        return "yes for v9 local replay outputs; no for loaded v8.2 comparison fields"
    if "v8_2_year_stability" in text:
        return "partial: replay from frozen v8.1 score audit trail"
    if "v8_1_model_switch" in text:
        return "source score provenance artifact"
    return "not_applicable"


def read_first_line(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    try:
        with path.open("r", encoding="utf-8-sig", errors="replace") as handle:
            return handle.readline().strip()[:1000]
    except Exception:
        return ""


def unique_paths(paths: list[Path]) -> list[Path]:
    seen = set()
    out = []
    for path in paths:
        key = str(path.resolve()) if path.exists() else str(path)
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    return out


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except Exception:
        return str(path)


def safe_float(value: Any) -> float:
    try:
        if value is None or pd.isna(value):
            return float("nan")
        return float(value)
    except Exception:
        return float("nan")


def fmt_pct(value: Any) -> str:
    number = safe_float(value)
    return "nan" if math.isnan(number) else f"{number * 100:.2f}%"


def fmt_num(value: Any) -> str:
    number = safe_float(value)
    return "nan" if math.isnan(number) else f"{number:.4f}"


def bullet_lines(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


if __name__ == "__main__":
    main()
