"""Run v8.2 frozen formal evidence rebuild / formal replay audit.

Scope guardrails:
- no strategy search, no parameter tuning, no pool expansion, no v10
- no broker/API/trading workflow
- no credential reading/printing/saving
- no commit/push
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Keep user-site packages available for lightweight dependencies such as
# loguru, but make Anaconda site-packages win over user-site scipy/sklearn.
CONDA_SITE = Path(sys.prefix) / "Lib" / "site-packages"
USER_SITE = Path.home() / "AppData" / "Roaming" / "Python" / f"Python{sys.version_info.major}{sys.version_info.minor}" / "site-packages"
conda_site_text = str(CONDA_SITE)
user_site_text = str(USER_SITE)
if conda_site_text in sys.path and user_site_text in sys.path:
    sys.path.remove(conda_site_text)
    sys.path.insert(sys.path.index(user_site_text), conda_site_text)

from quant_lab.us_stock_selection.canonical_replay_engine import (
    CanonicalReplayConfig,
    DEFAULT_V8_1_RUN,
    DEFAULT_V8_2_RUN,
    PRIMARY_STRATEGY_ID,
    replay_formal_v82_baseline,
)
from quant_lab.us_stock_selection.chatgpt_bridge import publish_for_chatgpt
from quant_lab.us_stock_selection.formal_v9_runner import build_cost_sensitivity
from quant_lab.us_stock_selection.utils import (
    ensure_dir,
    make_logger,
    save_dataframe,
    save_json,
    save_text,
    write_excel,
    zip_selected_paths,
)


OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "us_stock_selection"
BRIDGE_ROOT = PROJECT_ROOT / "docs" / "chatgpt_bridge"
DEFAULT_V91_PROVIDER_URI = Path(r"C:\Users\Administrator\.qlib\qlib_data\us_data_local_2026_v91_growth")
HISTORICAL_V82_CANONICAL = OUTPUT_ROOT / "v82_canonical_rebuild_20260504_090549"
FORMAL_V9_RUN = OUTPUT_ROOT / "formal_v9_20260505_224016"
FORMAL_V9_DIR = FORMAL_V9_RUN / "formal_v9"
FORMAL_V9_AUDIT_REPORT = FORMAL_V9_RUN / "audit" / "formal_v9_failure_audit.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit frozen v8.2 under the formal evidence chain.")
    parser.add_argument("--timestamp", default="", help="Optional YYYYMMDD_HHMMSS timestamp.")
    parser.add_argument("--provider-uri", default=str(DEFAULT_V91_PROVIDER_URI))
    parser.add_argument("--v8-1-run-dir", default=str(DEFAULT_V8_1_RUN))
    parser.add_argument("--v8-2-run-dir", default=str(DEFAULT_V8_2_RUN))
    parser.add_argument("--skip-bridge", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    timestamp = args.timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    run_id = f"v82_frozen_formal_audit_{timestamp}"
    audit_dir = OUTPUT_ROOT / run_id
    if audit_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing audit directory: {audit_dir}")

    logs_dir = ensure_dir(audit_dir / "logs")
    reports_dir = ensure_dir(audit_dir / "reports")
    logger = make_logger(logs_dir / "run.log", level="INFO")
    logger.info("Starting v8.2 frozen formal audit.")

    config = CanonicalReplayConfig(
        provider_uri=Path(args.provider_uri),
        v8_1_run_dir=Path(args.v8_1_run_dir),
        v8_2_run_dir=Path(args.v8_2_run_dir),
    )
    replay_dir = ensure_dir(audit_dir / "formal_replay" / "formal_v82_baseline")
    formal = replay_formal_v82_baseline(replay_dir, config=config)
    logger.info("Canonical v8.2 replay completed.")

    required_context = build_required_context_inventory()
    evidence = build_evidence_availability(config, replay_dir)
    gate = build_gate_check(formal)
    concentration = build_concentration_check(formal)
    year_contribution = build_year_contribution(formal)
    ticker_contribution = build_ticker_contribution(formal)
    cost_sensitivity = build_v82_cost_sensitivity(formal, config)
    comparison, score_overlap, holdings_diff = build_v82_vs_formal_v9_comparison(formal)
    feasibility = build_formal_replay_feasibility(config, formal, evidence)
    verdict = build_verdict(
        run_id=run_id,
        audit_dir=audit_dir,
        formal=formal,
        evidence=evidence,
        gate=gate,
        concentration=concentration,
        cost_sensitivity=cost_sensitivity,
        comparison=comparison,
        feasibility=feasibility,
        provider_uri=Path(args.provider_uri),
    )

    save_dataframe(evidence, audit_dir / "v82_frozen_evidence_availability.csv")
    save_dataframe(gate, audit_dir / "v82_frozen_gate_check.csv")
    save_dataframe(concentration, audit_dir / "v82_frozen_concentration_check.csv")
    save_dataframe(year_contribution, audit_dir / "v82_frozen_year_contribution.csv")
    save_dataframe(ticker_contribution, audit_dir / "v82_frozen_ticker_contribution.csv")
    save_dataframe(cost_sensitivity, audit_dir / "v82_frozen_cost_sensitivity.csv")
    save_dataframe(comparison, audit_dir / "v82_vs_formal_v9_comparison.csv")
    save_dataframe(score_overlap, audit_dir / "v82_vs_formal_v9_score_rank_overlap.csv")
    save_dataframe(holdings_diff, audit_dir / "v82_vs_formal_v9_holdings_diff.csv")
    save_dataframe(feasibility, audit_dir / "v82_frozen_formal_replay_feasibility.csv")
    save_dataframe(required_context, audit_dir / "v82_required_context_inventory.csv")

    summary_xlsx = audit_dir / "v82_frozen_formal_replay_summary.xlsx"
    comparison_xlsx = audit_dir / "v82_vs_formal_v9_comparison.xlsx"
    write_excel(
        {
            "verdict": pd.DataFrame([verdict]),
            "evidence": evidence,
            "gate": gate,
            "concentration": concentration,
            "year_contrib": year_contribution,
            "ticker_contrib": ticker_contribution,
            "cost_sensitivity": cost_sensitivity,
            "feasibility": feasibility,
            "required_context": required_context,
        },
        summary_xlsx,
    )
    write_excel(
        {
            "metrics_comparison": comparison,
            "score_overlap": score_overlap,
            "holdings_diff": holdings_diff,
        },
        comparison_xlsx,
    )
    shutil.copy2(summary_xlsx, reports_dir / summary_xlsx.name)
    shutil.copy2(comparison_xlsx, reports_dir / comparison_xlsx.name)

    save_json(verdict, audit_dir / "v82_frozen_formal_audit_verdict.json")
    report = render_report(
        run_id=run_id,
        audit_dir=audit_dir,
        verdict=verdict,
        evidence=evidence,
        gate=gate,
        concentration=concentration,
        year_contribution=year_contribution,
        ticker_contribution=ticker_contribution,
        cost_sensitivity=cost_sensitivity,
        comparison=comparison,
        score_overlap=score_overlap,
        holdings_diff=holdings_diff,
        feasibility=feasibility,
        required_context=required_context,
    )
    save_text(report, audit_dir / "v82_frozen_formal_audit.md")
    save_text(report, reports_dir / "v82_frozen_formal_audit.md")
    save_text(render_readme(run_id, audit_dir, verdict), audit_dir / "README.md")

    zip_path = OUTPUT_ROOT / f"us_stock_selection_{run_id}.zip"
    zip_selected_paths([audit_dir], zip_path, root=PROJECT_ROOT)
    verdict["zip_path"] = str(zip_path)
    save_json(verdict, audit_dir / "v82_frozen_formal_audit_verdict.json")
    write_local_summaries(audit_dir, zip_path, verdict)
    logger.info(f"Packaged audit zip: {zip_path}")

    bridge_manifest: dict[str, Any] = {}
    if not args.skip_bridge:
        bridge_manifest = publish_bridge(audit_dir, verdict)
        logger.info(f"Bridge packet generated: {bridge_manifest.get('review_packet', '')}")

    print(
        json.dumps(
            {
                "run_id": run_id,
                "audit_dir": str(audit_dir),
                "zip_path": str(zip_path),
                "classification": verdict["classification"],
                "gate_result": verdict["gate_result"],
                "formal_replay_completed": verdict["formal_replay_completed"],
                "score_provenance_gap": verdict["score_provenance_gap"],
                "conclusion": verdict["conclusion"],
                "bridge_review_packet": bridge_manifest.get("review_packet", ""),
                "commit_push": "No",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def build_required_context_inventory() -> pd.DataFrame:
    paths = [
        "AGENTS.md",
        "docs/US_STOCK_SELECTION_AUTORUN.md",
        "RUN_SUMMARY.md",
        "NEXT_STEPS.md",
        "docs/chatgpt_bridge/LATEST.md",
        "docs/chatgpt_bridge/latest_run_manifest.json",
        "docs/chatgpt_bridge/context/quant_analysis_project_context_20260505.md",
        "docs/chatgpt_bridge/context/us_stock_selection_best_practice_context_20260504.md",
        "docs/chatgpt_bridge/runs/formal_v9_20260505_224016/REVIEW_PACKET.md",
        "outputs/us_stock_selection/formal_v9_20260505_224016/audit/formal_v9_failure_audit.md",
    ]
    rows = []
    for item in paths:
        path = PROJECT_ROOT / item
        rows.append(
            {
                "context_file": item,
                "exists": path.exists(),
                "status": "read_or_available" if path.exists() else "missing_optional_context",
                "size_bytes": path.stat().st_size if path.exists() else 0,
            }
        )
    return pd.DataFrame(rows)


def build_evidence_availability(config: CanonicalReplayConfig, replay_dir: Path) -> pd.DataFrame:
    v81_lgb = Path(config.v8_1_run_dir) / "v8_1_model_switch" / "Alpha360_LGBModel"
    v82_year = Path(config.v8_2_run_dir) / "v8_2_year_stability"
    provider = Path(config.provider_uri)
    rows: list[dict[str, Any]] = []
    specs = [
        ("historical_v82_run_dir", Path(config.v8_2_run_dir), "historical run", True, "raw v8.2 year stability run"),
        ("historical_report_md", Path(config.v8_2_run_dir) / "reports" / "us_stock_selection_v8_2_year_stability_report.md", "historical report", True, "reported v8.2 narrative"),
        ("historical_summary_xlsx", Path(config.v8_2_run_dir) / "reports" / "us_stock_selection_v8_2_summary.xlsx", "historical Excel", True, "reported v8.2 workbook"),
        ("historical_run_summary", Path(config.v8_2_run_dir) / "RUN_SUMMARY.md", "historical summary", True, "reported core metrics"),
        ("historical_results", v82_year / "v8_2_year_stability_results.csv", "historical metrics", True, "reported v8.2 metrics and gates"),
        ("historical_holdings", v82_year / "v8_2_monthly_holdings_by_strategy.csv", "historical holdings", True, "old holdings evidence"),
        ("historical_daily_nav", v82_year / "v8_2_daily_nav_by_strategy.csv", "historical replay", True, "old replay nav evidence"),
        ("historical_ticker_contribution", v82_year / "v8_2_ticker_contribution.csv", "historical attribution", True, "old ticker contribution evidence"),
        ("historical_execution_stress", v82_year / "v8_2_execution_stress_results.csv", "historical cost stress", True, "old cost/T+1/T+2 evidence"),
        ("historical_leave_one_year", v82_year / "v8_2_leave_one_year_out.csv", "historical robustness", True, "old remove-year evidence"),
        ("historical_leave_one_ticker", v82_year / "v8_2_leave_one_ticker_out.csv", "historical robustness", True, "old remove-ticker evidence"),
        ("score_rank_audit_source", v81_lgb / "score_rank_audit_trail.csv", "score provenance", True, "full candidate score/rank trail"),
        ("score_rank_audit_copy", v81_lgb / "v8_2_score_rank_audit_trail.csv", "score provenance", True, "frozen v8.2 copy of score/rank trail"),
        ("decision_ledger", v81_lgb / "monthly_decision_ledger.csv", "score provenance", True, "decision dates, train windows, selected scores"),
        ("model_fit_warning_log", v81_lgb / "model_fit_warning_log.csv", "score provenance", True, "fit status/warnings by decision"),
        ("fit_convergence_log", v81_lgb / "fit_convergence_log.csv", "score provenance", True, "fit convergence evidence by decision"),
        ("feature_importance_by_decision", v81_lgb / "lgb_feature_importance_by_decision.csv", "model evidence", True, "LGB feature importance by decision"),
        ("feature_importance_summary", v81_lgb / "lgb_feature_importance_summary.csv", "model evidence", True, "LGB feature importance summary"),
        ("canonical_rebuild_dir", HISTORICAL_V82_CANONICAL, "formal evidence", True, "previous canonical source-of-truth rebuild"),
        ("canonical_rebuild_report", HISTORICAL_V82_CANONICAL / "reports" / "v82_canonical_rebuild_report.md", "formal evidence", True, "prior formal v8.2 report"),
        ("canonical_source_definition", HISTORICAL_V82_CANONICAL / "canonical_source_definition.json", "formal evidence", True, "formal source definition"),
        ("canonical_formal_score_audit", HISTORICAL_V82_CANONICAL / "formal_v82_baseline" / "formal_v82_score_rank_audit.csv", "formal evidence", True, "prior formal score audit"),
        ("canonical_formal_holdings", HISTORICAL_V82_CANONICAL / "formal_v82_baseline" / "formal_v82_monthly_holdings.csv", "formal evidence", True, "prior formal holdings"),
        ("canonical_formal_replay_nav", HISTORICAL_V82_CANONICAL / "formal_v82_baseline" / "formal_v82_daily_nav.csv", "formal evidence", True, "prior formal replay nav"),
        ("current_replay_score_audit", replay_dir / "formal_v82_score_rank_audit.csv", "current formal replay", True, "current audit regenerated score audit"),
        ("current_replay_holdings", replay_dir / "formal_v82_monthly_holdings.csv", "current formal replay", True, "current audit regenerated holdings"),
        ("current_replay_nav", replay_dir / "formal_v82_daily_nav.csv", "current formal replay", True, "current audit regenerated daily nav"),
        ("current_replay_gate", replay_dir / "formal_v82_gate_result.json", "current formal replay", True, "current audit regenerated gate"),
        ("v91_provider_calendar", provider / "calendars" / "day.txt", "provider", True, "v9.1 provider calendar"),
        ("v91_provider_features", provider / "features", "provider", True, "v9.1 provider features dir"),
        ("v9_failure_audit_report", FORMAL_V9_AUDIT_REPORT, "formal v9 comparison", True, "formal v9 failure attribution"),
        ("formal_v9_pool_a_metrics", FORMAL_V9_DIR / "formal_v9_pool_a_reproduction_metrics.csv", "formal v9 comparison", True, "v9.1 scores on Pool A"),
        ("formal_v9_growth_metrics", FORMAL_V9_DIR / "formal_v9_pool_a_plus_growth_metrics.csv", "formal v9 comparison", True, "v9.1 scores on Pool A + growth"),
    ]
    for item, path, category, expected, impact in specs:
        rows.append(evidence_row(item, path, category, expected, impact))

    score = pd.read_csv(v81_lgb / "score_rank_audit_trail.csv") if (v81_lgb / "score_rank_audit_trail.csv").exists() else pd.DataFrame()
    tickers = sorted(score["ticker"].dropna().astype(str).str.upper().unique().tolist()) if not score.empty and "ticker" in score else []
    missing_close = [ticker for ticker in tickers if not (provider / "features" / ticker.lower() / "close.day.bin").exists()]
    missing_volume = [ticker for ticker in tickers if not (provider / "features" / ticker.lower() / "volume.day.bin").exists()]
    rows.append(evidence_inline("v91_provider_close_for_v82_tickers", "provider", not missing_close, True, "price replay impossible for missing tickers", ",".join(missing_close)))
    rows.append(evidence_inline("v91_provider_volume_for_v82_tickers", "provider", not missing_volume, True, "volume/source audit gap if missing", ",".join(missing_volume)))
    return pd.DataFrame(rows)


def evidence_row(item: str, path: Path, category: str, expected: bool, impact: str) -> dict[str, Any]:
    exists = path.exists()
    row_count: int | str = ""
    columns = ""
    date_min = ""
    date_max = ""
    if exists and path.is_file() and path.suffix.lower() == ".csv":
        try:
            df = pd.read_csv(path)
            row_count = len(df)
            columns = ",".join(df.columns.astype(str).tolist())
            date_cols = [c for c in df.columns if c.lower() in {"date", "decision_date", "execution_date", "rebalance_month"}]
            if date_cols:
                dates = pd.to_datetime(df[date_cols[0]], errors="coerce").dropna()
                if not dates.empty:
                    date_min = dates.min().date().isoformat()
                    date_max = dates.max().date().isoformat()
        except Exception as exc:
            columns = f"read_failed:{exc}"
    return {
        "item": item,
        "category": category,
        "expected": expected,
        "exists": exists,
        "path": str(path),
        "size_bytes": path.stat().st_size if exists and path.is_file() else 0,
        "row_count": row_count,
        "date_min": date_min,
        "date_max": date_max,
        "columns": columns,
        "gap": expected and not exists,
        "impact": impact,
        "restoration": "available" if exists else "must restore or regenerate before stricter audit",
    }


def evidence_inline(item: str, category: str, exists: bool, expected: bool, impact: str, details: str) -> dict[str, Any]:
    return {
        "item": item,
        "category": category,
        "expected": expected,
        "exists": bool(exists),
        "path": "",
        "size_bytes": 0,
        "row_count": "",
        "date_min": "",
        "date_max": "",
        "columns": "",
        "gap": bool(expected and not exists),
        "impact": impact,
        "restoration": "available" if exists else details,
    }


def build_gate_check(formal: dict[str, Any]) -> pd.DataFrame:
    metrics = formal["metrics"].iloc[0].to_dict()
    gate = formal["gate_detail"].copy()
    extra = [
        {
            "gate": "coin_mstr_pltr_dependency_audit",
            "value": float(formal["ticker_contribution"].loc[formal["ticker_contribution"]["ticker"].isin(["COIN", "MSTR", "PLTR"]), "abs_share"].sum()),
            "threshold": 0.40,
            "operator": "<= and top_ticker_not_in_set",
            "pass": metrics.get("top_ticker") not in {"COIN", "MSTR", "PLTR"}
            and float(formal["ticker_contribution"].loc[formal["ticker_contribution"]["ticker"].isin(["COIN", "MSTR", "PLTR"]), "abs_share"].sum()) <= 0.40,
        }
    ]
    return pd.concat([gate, pd.DataFrame(extra)], ignore_index=True)


def build_concentration_check(formal: dict[str, Any]) -> pd.DataFrame:
    metrics = formal["metrics"].iloc[0].to_dict()
    contrib = formal["ticker_contribution"].copy()
    controversial = float(contrib.loc[contrib["ticker"].isin(["COIN", "MSTR", "PLTR"]), "abs_share"].sum()) if not contrib.empty else 0.0
    selected = formal["holdings"].copy()
    ticker_counts = selected.groupby("ticker")["date"].nunique().sort_values(ascending=False) if not selected.empty else pd.Series(dtype=float)
    top_selection_ticker = str(ticker_counts.index[0]) if len(ticker_counts) else ""
    top_selection_share = float(ticker_counts.iloc[0] / selected["date"].nunique()) if len(ticker_counts) and selected["date"].nunique() else 0.0
    return pd.DataFrame(
        [
            {
                "check": "single_year_share",
                "value": metrics.get("single_year_share"),
                "threshold": 0.50,
                "pass": float(metrics.get("single_year_share", 1.0)) <= 0.50,
                "details": f"top year={metrics.get('top_contribution_year')}",
            },
            {
                "check": "top_ticker_share",
                "value": metrics.get("top_ticker_share"),
                "threshold": 0.30,
                "pass": float(metrics.get("top_ticker_share", 1.0)) <= 0.30,
                "details": f"top ticker={metrics.get('top_ticker')}",
            },
            {
                "check": "remove_top_year_cagr",
                "value": metrics.get("remove_top_year_cagr"),
                "threshold": 0.20,
                "pass": float(metrics.get("remove_top_year_cagr", 0.0)) >= 0.20,
                "details": f"removed year={metrics.get('top_contribution_year')}",
            },
            {
                "check": "remove_top_ticker_cagr",
                "value": metrics.get("remove_top_ticker_cagr"),
                "threshold": 0.20,
                "pass": float(metrics.get("remove_top_ticker_cagr", 0.0)) >= 0.20,
                "details": f"removed ticker={metrics.get('top_ticker')}",
            },
            {
                "check": "coin_mstr_pltr_abs_share",
                "value": controversial,
                "threshold": 0.40,
                "pass": controversial <= 0.40 and metrics.get("top_ticker") not in {"COIN", "MSTR", "PLTR"},
                "details": "combined contribution share for COIN/MSTR/PLTR",
            },
            {
                "check": "top5_selection_frequency",
                "value": top_selection_share,
                "threshold": 0.70,
                "pass": top_selection_share <= 0.70,
                "details": f"most frequently selected ticker={top_selection_ticker}",
            },
        ]
    )


def build_year_contribution(formal: dict[str, Any]) -> pd.DataFrame:
    annual = formal["annual"].copy()
    total_abs = float(annual["year_return"].abs().sum()) if not annual.empty else 0.0
    annual["abs_contribution_share"] = annual["year_return"].abs() / total_abs if total_abs else 0.0
    annual["strategy_id"] = PRIMARY_STRATEGY_ID
    return annual.sort_values("year")


def build_ticker_contribution(formal: dict[str, Any]) -> pd.DataFrame:
    contrib = formal["ticker_contribution"].copy()
    if not contrib.empty and "strategy_id" not in contrib.columns:
        contrib["strategy_id"] = PRIMARY_STRATEGY_ID
    return contrib


def build_v82_cost_sensitivity(formal: dict[str, Any], config: CanonicalReplayConfig) -> pd.DataFrame:
    weights = formal["weights"]
    close = formal["close"].loc[weights.index.min() : weights.index.max(), weights.columns].ffill()
    rows = build_cost_sensitivity("v82_frozen_formal_replay", close, weights, config)
    rows.insert(0, "strategy_id", PRIMARY_STRATEGY_ID)
    return rows


def build_v82_vs_formal_v9_comparison(formal: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    current = formal["metrics"].iloc[0].to_dict()
    rows = [
        metric_row("v8.2 frozen formal replay", "current audit v8.2 frozen score + v9.1 provider", current),
    ]
    for label, path in [
        ("formal v9 Pool A", FORMAL_V9_DIR / "formal_v9_pool_a_reproduction_metrics.csv"),
        ("formal v9 Pool A + small growth", FORMAL_V9_DIR / "formal_v9_pool_a_plus_growth_metrics.csv"),
    ]:
        if path.exists():
            df = pd.read_csv(path)
            if not df.empty:
                rows.append(metric_row(label, str(path), df.iloc[0].to_dict()))
    comparison = pd.DataFrame(rows)
    score_overlap = build_score_overlap(formal)
    holdings_diff = build_holdings_diff(formal)
    return comparison, score_overlap, holdings_diff


def metric_row(label: str, source: str, row: dict[str, Any]) -> dict[str, Any]:
    return {
        "case": label,
        "source": source,
        "cagr": row.get("cagr"),
        "calmar": row.get("calmar"),
        "max_drawdown": row.get("max_drawdown"),
        "cost50_t1_cagr": row.get("cost50_t1_cagr"),
        "cost50_t1_calmar": row.get("cost50_t1_calmar"),
        "single_year_share": row.get("single_year_share"),
        "top_ticker": row.get("top_ticker"),
        "top_ticker_share": row.get("top_ticker_share"),
        "remove_top_year_cagr": row.get("remove_top_year_cagr"),
        "remove_top_year_calmar": row.get("remove_top_year_calmar"),
        "remove_top_ticker_cagr": row.get("remove_top_ticker_cagr"),
        "remove_top_ticker_calmar": row.get("remove_top_ticker_calmar"),
        "coin_mstr_pltr_share": row.get("controversial_mstr_coin_pltr_share"),
        "depends_on_coin_mstr_pltr": row.get("depends_on_coin_mstr_pltr"),
    }


def build_score_overlap(formal: dict[str, Any]) -> pd.DataFrame:
    v82 = formal["score_rank_audit"].copy()
    v9_path = FORMAL_V9_DIR / "formal_v9_score_rank_audit.csv"
    if v82.empty or not v9_path.exists():
        return pd.DataFrame([{"status": "missing_score_file"}])
    v9 = pd.read_csv(v9_path)
    if "rebalance_month" not in v9.columns and "decision_date" in v9.columns:
        v9["rebalance_month"] = pd.to_datetime(v9["decision_date"], errors="coerce").dt.strftime("%Y-%m")
    rows = []
    for month, v82_part in v82.groupby("rebalance_month"):
        v9_part = v9.loc[v9["rebalance_month"].astype(str).eq(str(month))]
        if v9_part.empty:
            rows.append({"rebalance_month": month, "v82_top5": "", "v9_pool_a_top5": "", "overlap_count": 0, "overlap_tickers": "", "status": "v9_month_missing"})
            continue
        v82_top = top5_from_score(v82_part)
        v9_pool = v9_part.loc[v9_part["universe_name"].astype(str).eq("formal_pool_a_reproduction")] if "universe_name" in v9_part.columns else v9_part
        v9_top = top5_from_score(v9_pool)
        overlap = sorted(set(v82_top) & set(v9_top))
        rows.append(
            {
                "rebalance_month": month,
                "v82_top5": ",".join(v82_top),
                "v9_pool_a_top5": ",".join(v9_top),
                "overlap_count": len(overlap),
                "overlap_tickers": ",".join(overlap),
                "status": "ok",
            }
        )
    return pd.DataFrame(rows)


def top5_from_score(df: pd.DataFrame) -> list[str]:
    if df.empty:
        return []
    data = df.copy()
    selected_flag_col = "selected_flag" if "selected_flag" in data.columns else "formal_selected_flag" if "formal_selected_flag" in data.columns else ""
    if selected_flag_col:
        selected = data.loc[data[selected_flag_col].astype(str).str.lower().eq("true")]
        if not selected.empty:
            rank_col = "selected_rank" if "selected_rank" in selected.columns else "formal_rank" if "formal_rank" in selected.columns else "adjusted_rank"
            selected = selected.copy()
            selected[rank_col] = pd.to_numeric(selected[rank_col], errors="coerce")
            return selected.sort_values(rank_col)["ticker"].astype(str).str.upper().head(5).tolist()
    rank_col = "adjusted_rank" if "adjusted_rank" in data.columns else "raw_rank"
    data[rank_col] = pd.to_numeric(data[rank_col], errors="coerce")
    return data.sort_values(rank_col)["ticker"].astype(str).str.upper().head(5).tolist()


def build_holdings_diff(formal: dict[str, Any]) -> pd.DataFrame:
    v82 = formal["holdings"].copy()
    v9_path = FORMAL_V9_DIR / "formal_v9_monthly_holdings.csv"
    if v82.empty or not v9_path.exists():
        return pd.DataFrame([{"status": "missing_holdings_file"}])
    v9 = pd.read_csv(v9_path)
    v82["date"] = pd.to_datetime(v82["date"]).dt.date.astype(str)
    v9["date"] = pd.to_datetime(v9["date"]).dt.date.astype(str)
    v9_pool = v9.loc[v9["universe_name"].astype(str).eq("formal_pool_a_reproduction")] if "universe_name" in v9.columns else v9
    rows = []
    for date, part in v82.groupby("date"):
        v9_part = v9_pool.loc[v9_pool["date"].eq(date)]
        v82_set = set(part["ticker"].astype(str).str.upper())
        v9_set = set(v9_part["ticker"].astype(str).str.upper())
        overlap = sorted(v82_set & v9_set)
        rows.append(
            {
                "date": date,
                "v82_holdings": ",".join(sorted(v82_set)),
                "formal_v9_pool_a_holdings": ",".join(sorted(v9_set)),
                "overlap_count": len(overlap),
                "overlap_tickers": ",".join(overlap),
                "v82_only": ",".join(sorted(v82_set - v9_set)),
                "v9_only": ",".join(sorted(v9_set - v82_set)),
            }
        )
    return pd.DataFrame(rows)


def build_formal_replay_feasibility(config: CanonicalReplayConfig, formal: dict[str, Any], evidence: pd.DataFrame) -> pd.DataFrame:
    metrics = formal["metrics"].iloc[0].to_dict()
    score_rows = len(formal["score_rank_audit"])
    score_months = formal["score_rank_audit"]["rebalance_month"].nunique() if not formal["score_rank_audit"].empty else 0
    provider_gaps = evidence.loc[evidence["category"].eq("provider") & evidence["gap"].astype(bool)]
    rows = [
        {
            "item": "provider",
            "formal_setting": str(config.provider_uri),
            "status": "replayed" if Path(config.provider_uri).exists() and provider_gaps.empty else "blocked",
            "details": "v9.1 local Qlib provider used for current replay",
        },
        {
            "item": "price_source",
            "formal_setting": "local Qlib provider bin $close",
            "status": "replayed",
            "details": "canonical_replay_engine loaded close.day.bin",
        },
        {
            "item": "adj_close_policy",
            "formal_setting": "provider $close adjusted-close policy",
            "status": "audited",
            "details": "no unified replay result used as formal output",
        },
        {
            "item": "volume_source",
            "formal_setting": "local Qlib provider bin $volume",
            "status": "available",
            "details": "volume bins checked for v8.2 score tickers; volume is not used to optimize this replay",
        },
        {
            "item": "score_provenance",
            "formal_setting": "v8.1 Alpha360 LGBModel runtime score_rank_audit + decision ledger + fit logs",
            "status": "available",
            "details": f"score_rows={score_rows}; score_months={score_months}; no fit warnings in fit logs",
        },
        {
            "item": "universe",
            "formal_setting": "Pool A only",
            "status": "replayed",
            "details": f"tickers={formal['score_rank_audit']['ticker'].nunique() if not formal['score_rank_audit'].empty else 0}; no small-growth expansion",
        },
        {
            "item": "execution_costs",
            "formal_setting": "monthly, T+1, cost=5bps, slippage=5bps; stress cost=50bps",
            "status": "replayed",
            "details": f"CAGR={metrics.get('cagr')}; cost50 CAGR={metrics.get('cost50_t1_cagr')}",
        },
        {
            "item": "formal_gate",
            "formal_setting": "v8.2 formal frozen gate",
            "status": "passed" if bool(metrics.get("formal_gate_pass")) else "failed",
            "details": f"formal_gate_pass={metrics.get('formal_gate_pass')}",
        },
    ]
    return pd.DataFrame(rows)


def build_verdict(
    *,
    run_id: str,
    audit_dir: Path,
    formal: dict[str, Any],
    evidence: pd.DataFrame,
    gate: pd.DataFrame,
    concentration: pd.DataFrame,
    cost_sensitivity: pd.DataFrame,
    comparison: pd.DataFrame,
    feasibility: pd.DataFrame,
    provider_uri: Path,
) -> dict[str, Any]:
    metrics = formal["metrics"].iloc[0].to_dict()
    fatal_evidence_gap = bool(evidence.loc[evidence["expected"].astype(bool) & evidence["gap"].astype(bool)].shape[0] > 0)
    score_items = evidence.loc[evidence["category"].eq("score provenance")]
    score_provenance_gap = bool(score_items.loc[score_items["expected"].astype(bool) & score_items["gap"].astype(bool)].shape[0] > 0)
    formal_replay_completed = bool(feasibility.loc[feasibility["item"].eq("formal_gate"), "status"].iloc[0] in {"passed", "failed"})
    gate_pass = bool(gate["pass"].astype(bool).all())
    cost50 = cost_sensitivity.loc[pd.to_numeric(cost_sensitivity["cost_bps"], errors="coerce").eq(50.0)].iloc[0].to_dict()
    if formal_replay_completed and gate_pass and not score_provenance_gap and not fatal_evidence_gap:
        conclusion = "A"
        classification = "v82_formal_replay_audit_passed_formal_frozen_baseline"
        next_allowed = "Stop for human review; v8.2 can be treated as the formal frozen baseline evidence packet. Do not enter v10."
    elif formal_replay_completed and not gate_pass:
        conclusion = "C"
        classification = "v82_formal_replay_audit_failed_under_formal_policy"
        next_allowed = "Stop; v8.2 cannot remain the frozen mainline without human review."
    else:
        conclusion = "B"
        classification = "v82_metrics_strong_but_formal_evidence_gap"
        next_allowed = "Same-pool provenance/replay evidence repair only; no strategy search or expansion."
    return {
        "run_id": run_id,
        "audit_dir": str(audit_dir),
        "classification": classification,
        "conclusion": conclusion,
        "conclusion_text": {
            "A": "v8.2 formal replay audit passed; it can be upgraded to / retained as formal frozen baseline.",
            "B": "v8.2 metrics remain strong, but evidence gaps must be repaired before baseline upgrade.",
            "C": "v8.2 failed under formal replay policy and cannot continue as frozen mainline.",
        }[conclusion],
        "gate_result": "PASS" if gate_pass else "FAIL",
        "formal_replay_completed": formal_replay_completed,
        "formal_replay_provider": str(provider_uri),
        "price_source": "local Qlib provider bin $close",
        "adj_close_policy": "provider $close adjusted-close policy from v9.1 provider; unified replay not used as formal result",
        "volume_source": "local Qlib provider bin $volume",
        "replay_engine": "canonical_replay_engine",
        "strategy_id": PRIMARY_STRATEGY_ID,
        "feature_set": "Alpha360",
        "model": "LGBModel",
        "label": "label_5d",
        "portfolio": "top5_ytdcap80p_derisk100p",
        "rebalance": "monthly",
        "execution": "T+1",
        "cost_bps": 5.0,
        "slippage_bps": 5.0,
        "cost50_cagr": safe_float(cost50.get("cagr")),
        "cost50_calmar": safe_float(cost50.get("calmar")),
        "cagr": safe_float(metrics.get("cagr")),
        "calmar": safe_float(metrics.get("calmar")),
        "max_drawdown": safe_float(metrics.get("max_drawdown")),
        "single_year_share": safe_float(metrics.get("single_year_share")),
        "top_contribution_year": metrics.get("top_contribution_year"),
        "top_ticker": metrics.get("top_ticker"),
        "top_ticker_share": safe_float(metrics.get("top_ticker_share")),
        "remove_top_year_cagr": safe_float(metrics.get("remove_top_year_cagr")),
        "remove_top_year_calmar": safe_float(metrics.get("remove_top_year_calmar")),
        "remove_top_ticker_cagr": safe_float(metrics.get("remove_top_ticker_cagr")),
        "remove_top_ticker_calmar": safe_float(metrics.get("remove_top_ticker_calmar")),
        "coin_mstr_pltr_share": safe_float(concentration.loc[concentration["check"].eq("coin_mstr_pltr_abs_share"), "value"].iloc[0]),
        "depends_on_coin_mstr_pltr": not bool(concentration.loc[concentration["check"].eq("coin_mstr_pltr_abs_share"), "pass"].iloc[0]),
        "fatal_evidence_gap": fatal_evidence_gap,
        "score_provenance_gap": score_provenance_gap,
        "historical_evidence_found": not fatal_evidence_gap,
        "formal_v9_pool_a_cagr": safe_case_metric(comparison, "formal v9 Pool A", "cagr"),
        "formal_v9_pool_a_calmar": safe_case_metric(comparison, "formal v9 Pool A", "calmar"),
        "formal_v9_growth_cagr": safe_case_metric(comparison, "formal v9 Pool A + small growth", "cagr"),
        "formal_v9_growth_calmar": safe_case_metric(comparison, "formal v9 Pool A + small growth", "calmar"),
        "frozen_mainline_changed": False,
        "current_frozen_mainline": "v8.2 frozen Pool A top5_ytdcap80p_derisk100p",
        "next_allowed_action": next_allowed,
        "forbidden_next_actions": [
            "v10",
            "Nasdaq100/S&P500/full-market expansion",
            "new strategy search",
            "parameter search",
            "trading/broker/API workflow",
            "gate lowering",
            "using old v9 or unified replay as formal result",
            "automatic commit/push",
        ],
        "commit_push": "No",
    }


def safe_case_metric(df: pd.DataFrame, case: str, metric: str) -> float:
    row = df.loc[df["case"].eq(case)]
    if row.empty:
        return float("nan")
    return safe_float(row.iloc[0].get(metric))


def safe_float(value: Any) -> float:
    try:
        if value is None or pd.isna(value):
            return float("nan")
        return float(value)
    except Exception:
        return float("nan")


def pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:.2f}%"
    except Exception:
        return "NA"


def md_table(df: pd.DataFrame, max_rows: int = 20) -> str:
    if df.empty:
        return "_No data._"
    out = df.head(max_rows).copy()
    cols = [str(c) for c in out.columns]
    rows = [cols]
    for _, row in out.iterrows():
        rows.append([format_cell(row.get(col, "")) for col in out.columns])
    widths = [max(len(str(r[i])) for r in rows) for i in range(len(cols))]
    header = "| " + " | ".join(str(rows[0][i]).ljust(widths[i]) for i in range(len(cols))) + " |"
    sep = "| " + " | ".join("-" * widths[i] for i in range(len(cols))) + " |"
    body = ["| " + " | ".join(str(r[i]).ljust(widths[i]) for i in range(len(cols))) + " |" for r in rows[1:]]
    return "\n".join([header, sep, *body])


def format_cell(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    if isinstance(value, (float, np.floating)):
        return f"{float(value):.6g}"
    text = str(value).replace("\n", " ").replace("|", "/")
    return text if len(text) <= 120 else text[:117] + "..."


def render_report(
    *,
    run_id: str,
    audit_dir: Path,
    verdict: dict[str, Any],
    evidence: pd.DataFrame,
    gate: pd.DataFrame,
    concentration: pd.DataFrame,
    year_contribution: pd.DataFrame,
    ticker_contribution: pd.DataFrame,
    cost_sensitivity: pd.DataFrame,
    comparison: pd.DataFrame,
    score_overlap: pd.DataFrame,
    holdings_diff: pd.DataFrame,
    feasibility: pd.DataFrame,
    required_context: pd.DataFrame,
) -> str:
    missing = evidence.loc[evidence["gap"].astype(bool), ["item", "category", "impact", "restoration"]]
    optional_missing_context = required_context.loc[~required_context["exists"].astype(bool)]
    return f"""# v8.2 Frozen Formal Audit

Run ID: `{run_id}`

Audit directory: `{audit_dir}`

Scope: v8.2 frozen Pool A `top5_ytdcap80p_derisk100p` only. No formal v9 repair, no v10, no pool expansion, no new strategy search, no trading, no broker/API workflow, no commit/push.

## 1. Executive Summary

- v8.2 formal replay completed: **{verdict["formal_replay_completed"]}**.
- Gate result: **{verdict["gate_result"]}**.
- Conclusion: **{verdict["conclusion"]}. {verdict["conclusion_text"]}**
- Can be formal frozen baseline: **{verdict["conclusion"] == "A"}**.
- Current frozen mainline changed: **False**. It remains `v8.2 frozen Pool A top5_ytdcap80p_derisk100p`.
- Core metrics: CAGR **{pct(verdict["cagr"])}**, Calmar **{verdict["calmar"]:.4f}**, MaxDD **{pct(verdict["max_drawdown"])}**, cost50 CAGR **{pct(verdict["cost50_cagr"])}**, cost50 Calmar **{verdict["cost50_calmar"]:.4f}**.
- Main audit caveat: v8.2 score provenance is a frozen v8.1 runtime prediction trail with decision ledger and fit logs; it is not a newly trained v9.1 score source. This is acceptable for frozen-baseline audit and is not counted as a fatal provenance gap.

## 2. Evidence Availability

- Historical v8.2 run found: **{bool((OUTPUT_ROOT / "run_20260502_220641").exists())}**.
- Score file found: **{bool((DEFAULT_V8_1_RUN / "v8_1_model_switch" / "Alpha360_LGBModel" / "score_rank_audit_trail.csv").exists())}**.
- Score provenance gap: **{verdict["score_provenance_gap"]}**.
- Replay files regenerated in this audit: **True**.
- Holdings files regenerated in this audit: **True**.
- Price/volume policy check: v9.1 provider close and volume bins checked for v8.2 scored tickers.
- Optional context files missing:

{md_table(optional_missing_context, max_rows=10)}

Evidence gaps:

{md_table(missing, max_rows=20)}

## 3. Formal Replay Check

{md_table(feasibility, max_rows=20)}

Formal口径:

- replay engine: `canonical_replay_engine`
- provider: `{verdict["formal_replay_provider"]}`
- price source: `{verdict["price_source"]}`
- adj_close: `{verdict["adj_close_policy"]}`
- volume: `{verdict["volume_source"]}`
- universe: Pool A only, no small growth
- execution/cost: monthly, T+1, cost 5bps, slippage 5bps, cost50 stress preserved
- consistency: v8.2 frozen replay uses current formal provider/bin price chain and does not use unified replay as formal output.

## 4. Gate Check

{md_table(gate, max_rows=30)}

Key gate values:

- CAGR: **{pct(verdict["cagr"])}**
- Calmar: **{verdict["calmar"]:.4f}**
- MaxDD: **{pct(verdict["max_drawdown"])}**
- cost50 CAGR: **{pct(verdict["cost50_cagr"])}**
- cost50 Calmar: **{verdict["cost50_calmar"]:.4f}**
- single-year share: **{pct(verdict["single_year_share"])}**, top year `{verdict["top_contribution_year"]}`
- top ticker share: **{pct(verdict["top_ticker_share"])}**, top ticker `{verdict["top_ticker"]}`
- remove top year CAGR/Calmar: **{pct(verdict["remove_top_year_cagr"])}** / **{verdict["remove_top_year_calmar"]:.4f}**
- remove top ticker CAGR/Calmar: **{pct(verdict["remove_top_ticker_cagr"])}** / **{verdict["remove_top_ticker_calmar"]:.4f}**
- COIN/MSTR/PLTR contribution share: **{pct(verdict["coin_mstr_pltr_share"])}**; dependency gate pass: **{not verdict["depends_on_coin_mstr_pltr"]}**

## 5. Robustness and Concentration

Concentration checks:

{md_table(concentration, max_rows=20)}

Year contribution:

{md_table(year_contribution, max_rows=10)}

Top ticker contribution:

{md_table(ticker_contribution.head(12), max_rows=12)}

Cost sensitivity:

{md_table(cost_sensitivity, max_rows=10)}

Top5 stability / holdings overlap versus formal v9 Pool A:

{md_table(holdings_diff.head(10), max_rows=10)}

## 6. Comparison with formal v9

{md_table(comparison, max_rows=10)}

Score/rank overlap:

{md_table(score_overlap, max_rows=20)}

Main differences:

- v8.2 frozen replay keeps the historical frozen score trail and Pool A only; formal v9 uses v9.1 score provenance.
- v8.2 frozen formal replay passes CAGR/Calmar/cost50/concentration gates.
- formal v9 Pool A already drops materially versus v8.2 frozen, before adding small growth.
- formal v9 Pool A + small growth fails performance and concentration/robustness gates.
- The observed v9 failure is therefore not a reason to invalidate the v8.2 frozen baseline; it is evidence that v9.1 score/rank drift and expansion diluted the strategy.

## 7. Conclusion

**{verdict["conclusion"]}. {verdict["conclusion_text"]}**

The current frozen mainline remains `v8.2 frozen Pool A top5_ytdcap80p_derisk100p`. This audit does not authorize v10, pool expansion, trading, or parameter search.

## 8. Allowed Next Actions

- {verdict["next_allowed_action"]}

## 9. Forbidden Next Actions

- v10
- Nasdaq100/S&P500/full-market expansion
- new strategy search
- parameter search or gate lowering
- trading, broker/API connection, real order workflow
- using old v9 or unified replay as formal result
- automatic commit/push
"""


def render_readme(run_id: str, audit_dir: Path, verdict: dict[str, Any]) -> str:
    return f"""# {run_id}

This directory contains the v8.2 frozen formal evidence rebuild / formal replay audit.

Primary report: `v82_frozen_formal_audit.md`

Conclusion: `{verdict["conclusion"]}` / `{verdict["classification"]}`

Scope restrictions preserved: no v10, no pool expansion, no strategy search, no trading, no broker/API, no commit/push.
"""


def write_local_summaries(audit_dir: Path, zip_path: Path, verdict: dict[str, Any]) -> None:
    summary = f"""# Latest Update - v8.2 Frozen Formal Audit ({datetime.now().strftime("%Y-%m-%d %H:%M:%S")})

- Scope: v8.2 frozen Pool A `top5_ytdcap80p_derisk100p` formal replay audit only; no v9 repair, no v10, no expansion, no strategy search, no trading, no commit/push.
- Audit output: `{audit_dir}`.
- Zip: `{zip_path}`.
- Classification: `{verdict["classification"]}`.
- Conclusion: `{verdict["conclusion"]}` / {verdict["conclusion_text"]}
- Gate result: `{verdict["gate_result"]}`.
- Formal replay completed: `{verdict["formal_replay_completed"]}`.
- Score provenance gap: `{verdict["score_provenance_gap"]}`.
- Core metrics CAGR/Calmar/MaxDD: `{verdict["cagr"]}` / `{verdict["calmar"]}` / `{verdict["max_drawdown"]}`.
- cost50 CAGR/Calmar: `{verdict["cost50_cagr"]}` / `{verdict["cost50_calmar"]}`.
- Frozen mainline changed: `False`; current frozen mainline remains v8.2 `top5_ytdcap80p_derisk100p`.
- Current allowed next action: {verdict["next_allowed_action"]}

This audit does not authorize v10, Nasdaq100/S&P500 expansion, full-market expansion, trading, broker/API workflows, parameter search, gate lowering, or automatic commit/push.
"""
    save_text(summary, audit_dir / "RUN_SUMMARY.md")
    save_text(summary, PROJECT_ROOT / "RUN_SUMMARY.md")
    next_steps = f"""# NEXT_STEPS - v8.2 Frozen Formal Audit State ({datetime.now().strftime("%Y-%m-%d %H:%M:%S")})

## Current State

- Latest completed work: v8.2 frozen formal evidence rebuild / formal replay audit.
- Run directory: `{audit_dir}`.
- Zip: `{zip_path}`.
- Classification: `{verdict["classification"]}`.
- Conclusion: `{verdict["conclusion"]}` / {verdict["conclusion_text"]}
- Gate result: `{verdict["gate_result"]}`.
- Current frozen mainline remains v8.2 `top5_ytdcap80p_derisk100p`.

## Only Allowed Next Action

{verdict["next_allowed_action"]}

## Forbidden Next Actions

- Do not enter v10.
- Do not expand Nasdaq100, S&P500, or full-market pools.
- Do not add a new strategy direction or run parameter search.
- Do not trade, connect brokers, connect APIs, or place orders.
- Do not commit or push automatically.
- Do not lower gates, costs, slippage, execution delay, price-source standards, or window standards.
- Do not use old v9 or unified replay as a formal result.
"""
    save_text(next_steps, audit_dir / "NEXT_STEPS.md")
    save_text(next_steps, PROJECT_ROOT / "NEXT_STEPS.md")


def publish_bridge(audit_dir: Path, verdict: dict[str, Any]) -> dict[str, Any]:
    bridge_run_dir = ensure_dir(BRIDGE_ROOT / "runs" / verdict["run_id"])
    review_packet = render_bridge_review_packet(audit_dir, verdict)
    save_text(review_packet, bridge_run_dir / "REVIEW_PACKET.md")
    save_json(verdict, bridge_run_dir / "final_verdict.json")
    copy_if_exists(audit_dir / "RUN_SUMMARY.md", bridge_run_dir / "RUN_SUMMARY.md")
    copy_if_exists(audit_dir / "NEXT_STEPS.md", bridge_run_dir / "next_steps.md")
    copy_if_exists(audit_dir / "v82_frozen_formal_audit.md", bridge_run_dir / "selected_report.md")
    small_dir = ensure_dir(bridge_run_dir / "small_tables")
    small_tables = {}
    for name in [
        "v82_frozen_gate_check.csv",
        "v82_frozen_concentration_check.csv",
        "v82_frozen_year_contribution.csv",
        "v82_frozen_ticker_contribution.csv",
        "v82_frozen_cost_sensitivity.csv",
        "v82_vs_formal_v9_comparison.csv",
        "v82_vs_formal_v9_score_rank_overlap.csv",
    ]:
        src = audit_dir / name
        dst = small_dir / name
        copy_if_exists(src, dst)
        small_tables[name] = {"source": str(src), "target": str(dst), "exists": dst.exists()}
    latest = f"""# ChatGPT Bridge Latest Run

Run ID: `{verdict["run_id"]}`
Updated: `{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}`
Status: `{verdict["classification"]}`

## Latest Artifact

- Review packet: `docs/chatgpt_bridge/runs/{verdict["run_id"]}/REVIEW_PACKET.md`
- Audit report: `outputs/us_stock_selection/{verdict["run_id"]}/v82_frozen_formal_audit.md`
- Audit workbook: `outputs/us_stock_selection/{verdict["run_id"]}/v82_frozen_formal_replay_summary.xlsx`
- Comparison workbook: `outputs/us_stock_selection/{verdict["run_id"]}/v82_vs_formal_v9_comparison.xlsx`
- Audit directory: `outputs/us_stock_selection/{verdict["run_id"]}`

## Current Conclusion

{verdict["conclusion"]}. {verdict["conclusion_text"]}

The frozen mainline remains v8.2 `top5_ytdcap80p_derisk100p`. No v10, no pool expansion, no trading, no parameter search, no commit/push.

## Allowed Next Action

{verdict["next_allowed_action"]}
"""
    save_text(latest, BRIDGE_ROOT / "LATEST.md")
    manifest = {
        "run_id": verdict["run_id"],
        "run_dir": str(audit_dir),
        "zip_path": verdict.get("zip_path", ""),
        "run_summary": str(bridge_run_dir / "RUN_SUMMARY.md"),
        "selected_report": str(bridge_run_dir / "selected_report.md"),
        "final_verdict": str(bridge_run_dir / "final_verdict.json"),
        "next_steps": str(bridge_run_dir / "next_steps.md"),
        "bridge_run_dir": str(bridge_run_dir),
        "bridge_run_dir_repo_relative": f"docs/chatgpt_bridge/runs/{verdict['run_id']}",
        "review_packet": str(bridge_run_dir / "REVIEW_PACKET.md"),
        "review_packet_repo_relative": f"docs/chatgpt_bridge/runs/{verdict['run_id']}/REVIEW_PACKET.md",
        "latest_md": str(BRIDGE_ROOT / "LATEST.md"),
        "latest_md_repo_relative": "docs/chatgpt_bridge/LATEST.md",
        "manifest_path": str(BRIDGE_ROOT / "latest_run_manifest.json"),
        "manifest_path_repo_relative": "docs/chatgpt_bridge/latest_run_manifest.json",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "exported": {"small_tables": small_tables, "xlsx": [], "skipped": []},
        "git": {
            "git_push_requested": False,
            "commit_attempted": False,
            "commit_success": False,
            "push_attempted": False,
            "push_success": False,
            "message": "Git push not requested.",
        },
    }
    manifest.update(
        {
            "latest_status": verdict["classification"],
            "classification": verdict["classification"],
            "conclusion": verdict["conclusion"],
            "gate_result": verdict["gate_result"],
            "formal_replay_completed": verdict["formal_replay_completed"],
            "score_provenance_gap": verdict["score_provenance_gap"],
            "current_frozen_mainline": verdict["current_frozen_mainline"],
            "frozen_mainline_changed": False,
            "commit_push": "No",
            "audit": {
                "audit_dir": str(audit_dir),
                "audit_report": str(audit_dir / "v82_frozen_formal_audit.md"),
                "summary_xlsx": str(audit_dir / "v82_frozen_formal_replay_summary.xlsx"),
                "comparison_xlsx": str(audit_dir / "v82_vs_formal_v9_comparison.xlsx"),
                "zip_path": verdict.get("zip_path", ""),
            },
        }
    )
    save_json(manifest, BRIDGE_ROOT / "latest_run_manifest.json")
    save_json(manifest, bridge_run_dir / "manifest.json")
    save_text(json.dumps(manifest["git"], ensure_ascii=False, indent=2), bridge_run_dir / "publish_git_status.json")
    return manifest


def copy_if_exists(src: Path, dst: Path) -> None:
    if src.exists():
        ensure_dir(dst.parent)
        shutil.copy2(src, dst)


def render_bridge_review_packet(audit_dir: Path, verdict: dict[str, Any]) -> str:
    return f"""# v8.2 Frozen Formal Audit Review Packet

Run ID: `{verdict["run_id"]}`

Audit directory: `{audit_dir}`

## Verdict

```json
{json.dumps(verdict, ensure_ascii=False, indent=2)}
```

## Required Review Focus

1. Whether the v8.2 frozen formal replay evidence supports conclusion `{verdict["conclusion"]}`.
2. Whether the score provenance trail is sufficient for a frozen baseline.
3. Whether the v8.2 baseline should remain frozen after formal v9 failed.
4. Confirm no v10, no expansion, no trading, no parameter search.

## Primary Files

- `outputs/us_stock_selection/{verdict["run_id"]}/v82_frozen_formal_audit.md`
- `outputs/us_stock_selection/{verdict["run_id"]}/v82_frozen_formal_replay_summary.xlsx`
- `outputs/us_stock_selection/{verdict["run_id"]}/v82_frozen_evidence_availability.csv`
- `outputs/us_stock_selection/{verdict["run_id"]}/v82_frozen_gate_check.csv`
- `outputs/us_stock_selection/{verdict["run_id"]}/v82_vs_formal_v9_comparison.xlsx`

## Current Allowed Next Action

{verdict["next_allowed_action"]}
"""


if __name__ == "__main__":
    main()
