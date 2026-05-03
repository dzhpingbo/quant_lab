"""Generate v8.2 score/rank audit-trail instrumentation outputs.

This script does not train models, run 31b, enter v9, expand the universe, or
run a reranking replay. For the existing v8 baseline run, it reconstructs only
the selected-only score trail that was actually persisted and marks the missing
full candidate/rank trail as a blocker. The source instrumentation in
``v8_paper_trading`` can persist the full trail during a future replay.
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

from quant_lab.us_stock_selection.local_qlib_provider_builder import default_local_provider_uri
from quant_lab.us_stock_selection.qlib_workflow_runner import load_close_from_provider
from quant_lab.us_stock_selection.utils import write_excel
from quant_lab.us_stock_selection.v8_2_audit_trail import (
    build_selected_only_audit_from_existing,
    reranking_readiness,
    schema_rows,
    validate_audit_quality,
    write_schema_markdown,
)


DEFAULT_RUN_DIR = PROJECT_ROOT / "outputs" / "us_stock_selection" / "run_20260426_095958"
OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "us_stock_selection"
DOCS_DIR = PROJECT_ROOT / "docs"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate v8.2 score/rank audit-trail instrumentation outputs.")
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument("--provider-uri", type=Path, default=default_local_provider_uri())
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--timestamp", default=None)
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--sample-months", default="2024-11,2025-03,2025-10")
    parser.add_argument("--audit-forward-returns", default="true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def bool_arg(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def setup_logger(out_dir: Path) -> logging.Logger:
    log_dir = out_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("v8_2_score_rank_audit_trail")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    fh = logging.FileHandler(log_dir / "run.log", encoding="utf-8")
    sh = logging.StreamHandler()
    fh.setFormatter(fmt)
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
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


def ensure_inputs(run_dir: Path) -> list[Path]:
    required = [
        run_dir / "v8_paper_trading" / "monthly_decision_ledger.csv",
        run_dir / "v8_paper_trading" / "monthly_holdings.csv",
        run_dir / "v8_paper_trading" / "daily_nav.csv",
        run_dir / "v8_paper_trading" / "trades.csv",
        run_dir / "v8_paper_trading" / "paper_trading_metrics.csv",
        run_dir / "v7_feature_cache" / "alpha360_cache.parquet",
    ]
    missing = [p for p in required if not p.exists()]
    if missing:
        raise FileNotFoundError("Missing required v8 input(s): " + "; ".join(str(p) for p in missing))
    return required


def pipeline_map() -> pd.DataFrame:
    rows = [
        {
            "file_path": "quant_lab/us_stock_selection/v8_paper_trading.py",
            "function_or_class": "run_paper_trading_replay",
            "role": "Frozen v8 monthly pseudo-live replay; orchestrates feature cache load, model fit, scoring, tradability filter, ranking, selection, holdings, trades, NAV.",
            "input_files": "v7_feature_cache/alpha360_cache.parquet; local qlib close/volume provider",
            "output_files": "monthly_decision_ledger.csv; daily_nav.csv; monthly_holdings.csv; trades.csv; paper_trading_metrics.csv; fit_convergence_log.csv; future v8_2_score_rank_audit_trail.csv",
            "key_columns": "decision_date,feature_date,instrument,score,selected_tickers,selected_scores,tradable_count",
            "whether_generates_candidate_universe": True,
            "whether_generates_score": True,
            "whether_generates_rank": True,
            "whether_generates_selection": True,
            "whether_selected_only": True,
            "notes": "Full pred/tradable/ranked exists at runtime; original v8 persisted only selected tickers/scores. Patched to save full audit trail in future replays.",
        },
        {
            "file_path": "quant_lab/us_stock_selection/v8_paper_trading.py",
            "function_or_class": "fit_model",
            "role": "Fits ElasticNet/Ridge/LGB fallback and returns the model used to predict one monthly snapshot.",
            "input_files": "feature cache frame filtered through train_end_label_safe",
            "output_files": "runtime fitted model; fit warning metadata",
            "key_columns": "feature_cols,label_5d",
            "whether_generates_candidate_universe": False,
            "whether_generates_score": False,
            "whether_generates_rank": False,
            "whether_generates_selection": False,
            "whether_selected_only": False,
            "notes": "No fitted model artifact is persisted; old full scores cannot be regenerated without retraining.",
        },
        {
            "file_path": "quant_lab/us_stock_selection/v8_paper_trading.py",
            "function_or_class": "tradable_universe",
            "role": "Filters prediction instruments by available close history and 20d average dollar volume.",
            "input_files": "local qlib close and volume provider",
            "output_files": "runtime tradable ticker list",
            "key_columns": "ticker,decision_date,avg_dollar_volume_20d",
            "whether_generates_candidate_universe": True,
            "whether_generates_score": False,
            "whether_generates_rank": False,
            "whether_generates_selection": False,
            "whether_selected_only": False,
            "notes": "Original v8 saves only tradable_count, not the tradable ticker list.",
        },
        {
            "file_path": "scripts/us_stock_selection/31_run_v8_paper_trading.py",
            "function_or_class": "main",
            "role": "Full v8 run entry point; calls run_paper_trading_replay then execution stress, attribution, reporting, zip.",
            "input_files": "source run feature cache; provider URI",
            "output_files": "v8 run directory",
            "key_columns": "n/a",
            "whether_generates_candidate_universe": False,
            "whether_generates_score": False,
            "whether_generates_rank": False,
            "whether_generates_selection": False,
            "whether_selected_only": False,
            "notes": "Not used in this instrumentation run because it would retrain/replay.",
        },
        {
            "file_path": "scripts/us_stock_selection/31a_run_v8_paper_replay_only.py",
            "function_or_class": "main",
            "role": "Paper replay only entry point; can use patched run_paper_trading_replay in a future approved replay.",
            "input_files": "v7_feature_cache; provider URI",
            "output_files": "v8_paper_trading outputs",
            "key_columns": "decision_date,ticker,score,weight",
            "whether_generates_candidate_universe": False,
            "whether_generates_score": False,
            "whether_generates_rank": False,
            "whether_generates_selection": False,
            "whether_selected_only": False,
            "notes": "Future bounded replay can produce full audit trail after user approval.",
        },
        {
            "file_path": "quant_lab/us_stock_selection/v8_2_audit_trail.py",
            "function_or_class": "build_score_rank_audit_for_decision",
            "role": "New instrumentation builder for full runtime decision_date x candidate score/rank audit rows.",
            "input_files": "runtime pred/tradable/selected/current_weights/close/dollar_volume",
            "output_files": "v8_2_score_rank_audit_trail.csv during future replay",
            "key_columns": "run_id,decision_date,rebalance_month,ticker,raw_score,raw_rank,selected_flag",
            "whether_generates_candidate_universe": False,
            "whether_generates_score": False,
            "whether_generates_rank": True,
            "whether_generates_selection": False,
            "whether_selected_only": False,
            "notes": "Instrumentation only; does not affect selection.",
        },
        {
            "file_path": "quant_lab/us_stock_selection/v8_2_audit_trail.py",
            "function_or_class": "build_selected_only_audit_from_existing",
            "role": "Honest fallback for old v8 runs where only selected tickers/scores were saved.",
            "input_files": "monthly_decision_ledger.csv; monthly_holdings.csv; provider close for risk/audit fields",
            "output_files": "selected-only v8_2_score_rank_audit_trail.csv; quality fail warnings",
            "key_columns": "decision_date,ticker,selected_flag,raw_score",
            "whether_generates_candidate_universe": False,
            "whether_generates_score": False,
            "whether_generates_rank": False,
            "whether_generates_selection": False,
            "whether_selected_only": True,
            "notes": "Does not fabricate unselected rows; readiness must remain false.",
        },
    ]
    return pd.DataFrame(rows)


def write_pipeline_map_md(path: Path, frame: pd.DataFrame) -> None:
    text = f"""# v8.2 Selection Pipeline Map

## Where The Pieces Are

1. Candidate universe is formed inside `run_paper_trading_replay`: `pred_frame` is loaded from Alpha360 feature cache for `feature_date`, then `pred` contains one row per instrument in that snapshot.
2. Score is formed in `run_paper_trading_replay`: `model.predict(pred_frame[feature_cols])` writes `pred["score"]`.
3. Rank is formed in `run_paper_trading_replay`: `ranked = pred.loc[pred["instrument"].isin(tradable)].sort_values("score", ascending=False)`.
4. Selected tickers are formed by `selected = ranked.head(5)`.
5. Monthly holdings are formed immediately after selection from `selected["instrument"]` and equal target weights.
6. Current v8 only left selected-only information because `monthly_decision_ledger.csv` stores `selected_tickers`, `selected_scores`, and `tradable_count`, while `monthly_holdings.csv` stores selected holdings only. It did not save `pred`, `tradable`, or `ranked`.
7. To get complete auditability, the patch point is inside `run_paper_trading_replay` while `pred`, `tradable`, `ranked`, `selected`, and `current` still exist in memory. This run adds that instrumentation hook for future replays, but it does not retrain the existing v8 baseline.

## Pipeline Table

{frame.to_markdown(index=False)}
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def parse_sample_months(raw: str) -> list[str] | None:
    value = str(raw or "").strip()
    if not value or value.lower() in {"all", "*"}:
        return None
    return [item.strip() for item in value.split(",") if item.strip()]


def resolve_sample_months(ledger: pd.DataFrame, requested: list[str] | None) -> tuple[list[str] | None, pd.DataFrame]:
    if requested is None:
        return None, pd.DataFrame()
    local = ledger.copy()
    local["decision_date"] = pd.to_datetime(local["decision_date"], errors="coerce")
    available = sorted(local["decision_date"].dropna().dt.to_period("M").astype(str).unique().tolist())
    if not available:
        return requested, pd.DataFrame(
            [{"warning_type": "sample_month_resolution", "severity": "high", "message": "no available decision months in ledger"}]
        )
    resolved: list[str] = []
    warnings: list[dict[str, Any]] = []
    for month in requested:
        if month in available:
            resolved.append(month)
            continue
        previous = [item for item in available if item <= month]
        replacement = previous[-1] if previous else available[0]
        resolved.append(replacement)
        warnings.append(
            {
                "warning_type": "sample_month_resolution",
                "severity": "medium",
                "message": f"requested sample month {month} has no decision row; using available decision month {replacement}",
                "requested_month": month,
                "resolved_month": replacement,
            }
        )
    # Preserve order while removing duplicates; then top up to at least three rows
    # when the ledger has enough months.
    resolved = list(dict.fromkeys(resolved))
    for candidate in available:
        if len(resolved) >= min(3, len(available)):
            break
        if candidate not in resolved:
            resolved.append(candidate)
            warnings.append(
                {
                    "warning_type": "sample_month_resolution",
                    "severity": "low",
                    "message": f"added extra available decision month {candidate} to keep sample validation broad",
                    "requested_month": "",
                    "resolved_month": candidate,
                }
            )
    return resolved, pd.DataFrame(warnings)


def filter_dates(ledger: pd.DataFrame, holdings: pd.DataFrame, start_date: str | None, end_date: str | None) -> tuple[pd.DataFrame, pd.DataFrame]:
    ledger_out = ledger.copy()
    holdings_out = holdings.copy()
    for frame in [ledger_out, holdings_out]:
        if "decision_date" in frame.columns:
            frame["decision_date"] = pd.to_datetime(frame["decision_date"], errors="coerce")
    if start_date:
        ledger_out = ledger_out.loc[ledger_out["decision_date"] >= pd.Timestamp(start_date)].copy()
        holdings_out = holdings_out.loc[holdings_out["decision_date"] >= pd.Timestamp(start_date)].copy()
    if end_date:
        ledger_out = ledger_out.loc[ledger_out["decision_date"] <= pd.Timestamp(end_date)].copy()
        holdings_out = holdings_out.loc[holdings_out["decision_date"] <= pd.Timestamp(end_date)].copy()
    return ledger_out, holdings_out


def load_close_for_selected(provider_uri: Path, holdings: pd.DataFrame, ledger: pd.DataFrame, logger: logging.Logger) -> pd.DataFrame:
    tickers = sorted(holdings["ticker"].astype(str).str.upper().unique().tolist())
    start = str(pd.to_datetime(ledger["decision_date"]).min().date() - pd.Timedelta(days=370))
    end = str(pd.to_datetime(ledger["decision_date"]).max().date() + pd.Timedelta(days=100))
    logger.info("Loading close panel for selected-only audit risk/forward fields: %s tickers, %s to %s", len(tickers), start, end)
    return load_close_from_provider(provider_uri, tickers=tickers, start=start, end=end).ffill()


def build_summary(
    run_dir: Path,
    audit: pd.DataFrame,
    quality: pd.DataFrame,
    warnings: pd.DataFrame,
    readiness: dict[str, Any],
    sample_months: list[str] | None,
    requested_sample_months: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "run_dir": str(run_dir),
        "requested_sample_months": requested_sample_months or "all",
        "resolved_sample_months": sample_months or "all",
        "audit_row_count": int(len(audit)),
        "decision_count": int(audit["decision_date"].nunique()) if not audit.empty else 0,
        "current_pipeline_cannot_reconstruct_full_unselected_scores": True,
        "missing_dependency": "Original v8 baseline did not persist runtime pred/tradable/ranked candidate snapshots or fitted monthly models.",
        "required_upstream_patch": "Use patched run_paper_trading_replay instrumentation to save v8_2_score_rank_audit_trail.csv during a future approved replay.",
        "selected_only_scores_available": bool("raw_score" in audit.columns and audit["raw_score"].notna().any()),
        "quality_pass_all": bool(not quality.empty and quality["quality_pass"].all()),
        "warning_count": int(len(warnings)),
        "readiness": readiness,
    }


def write_reports(
    timestamp: str,
    out_dir: Path,
    pipeline: pd.DataFrame,
    schema: pd.DataFrame,
    quality: pd.DataFrame,
    warnings: pd.DataFrame,
    readiness: dict[str, Any],
    summary: dict[str, Any],
    zip_path: Path,
) -> tuple[Path, Path]:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = DOCS_DIR / f"US_STOCK_SELECTION_V8_2_SCORE_RANK_AUDIT_TRAIL_{timestamp}.md"
    summary_path = DOCS_DIR / f"US_STOCK_SELECTION_V8_2_SCORE_RANK_AUDIT_EXEC_SUMMARY_{timestamp}.md"

    report = f"""# US Stock Selection v8.2 Score/Rank Audit Trail

## 1. Background And Purpose

v8.1 overlay evolution is stopped. This branch instruments the stock-selection layer so future diagnostics can inspect why each monthly candidate was selected or not selected.

## 2. Why Score/Rank Audit Is Required

The existing v8 baseline keeps selected tickers and selected scores only. Without `decision_date x tradable_ticker` score/rank rows, any reranking replay would be selected-only and biased.

## 3. v8 Selection Pipeline Location

{table_to_markdown(pipeline, max_rows=20, columns=['file_path','function_or_class','role','whether_generates_candidate_universe','whether_generates_score','whether_generates_rank','whether_generates_selection','whether_selected_only','notes'])}

## 4. Audit Trail Schema

{table_to_markdown(schema, max_rows=80)}

## 5. Implementation

- Added `quant_lab/us_stock_selection/v8_2_audit_trail.py`.
- Patched `quant_lab/us_stock_selection/v8_paper_trading.py` so future replays can save full runtime candidate audit rows while `pred`, `tradable`, `ranked`, and `selected` still exist.
- Added `scripts/us_stock_selection/39_generate_v8_2_score_rank_audit_trail.py`.
- This run did not train a model and did not rerun v8 baseline.

## 6. Dry-Run Result

Dry-run validates argparse, run path, required inputs, output directory creation, and pipeline-map generation. The final run reused the same checks before selected-only reconstruction.

## 7. Sample-Month Validation

{table_to_markdown(quality, max_rows=20)}

## 8. Data Quality Issues

{table_to_markdown(warnings, max_rows=20)}

## 9. Reranking Readiness

```json
{json.dumps(to_jsonable(readiness), indent=2, ensure_ascii=False)}
```

## 10. Missing Items If Not Ready

The existing v8 run is selected-only. Full candidate score/rank rows require an upstream replay with the new instrumentation hook enabled.

## 11. Next Step

Do not run reranking yet. Continue upstream logging by producing a full `v8_2_score_rank_audit_trail.csv` from an approved bounded replay, then reassess readiness.

## Outputs

- Output directory: `{out_dir}`
- Zip: `{zip_path}`
"""
    report_path.write_text(report, encoding="utf-8")

    exec_summary = f"""# US Stock Selection v8.2 Score/Rank Audit Exec Summary

- Instrumentation completed: `True`
- Existing run full candidate score/rank recovered: `False`
- Existing run remains selected-only: `True`
- Can run gate-aware reranking replay: `{readiness.get('can_run_gate_aware_reranking_replay')}`
- Main blocker: `{'; '.join(readiness.get('blockers', []))}`
- Next required patch: `{readiness.get('next_required_patch')}`

## Quality Snapshot

{table_to_markdown(quality, max_rows=20, columns=['decision_date','candidate_count','original_tradable_count','selected_count','unselected_count','selected_flag_consistent_with_holdings','quality_pass','warnings'])}
"""
    summary_path.write_text(exec_summary, encoding="utf-8")
    shutil.copy2(report_path, out_dir / "reports" / report_path.name)
    shutil.copy2(summary_path, out_dir / "reports" / summary_path.name)
    return report_path, summary_path


def update_next_steps(out_dir: Path, zip_path: Path, readiness: dict[str, Any]) -> None:
    path = PROJECT_ROOT / "NEXT_STEPS.md"
    previous = path.read_text(encoding="utf-8") if path.exists() else "# NEXT_STEPS\n"
    section = f"""

## v8.2 score/rank audit trail instrumentation

- 执行状态：completed，随后按要求暂停，不自动进入 reranking。
- 输出目录：`{out_dir}`
- zip：`{zip_path}`
- 是否生成 full candidate score/rank：`False`
- 是否仍是 selected-only：`True`
- 是否具备 reranking replay 条件：`{readiness.get('can_run_gate_aware_reranking_replay')}`
- has_full_candidate_universe：`{readiness.get('has_full_candidate_universe')}`
- has_unselected_tickers：`{readiness.get('has_unselected_tickers')}`
- has_raw_score：`{readiness.get('has_raw_score')}`
- selected_flag_validated：`{readiness.get('selected_flag_validated')}`
- 本轮结论：源码已补未来 replay 的完整 audit trail hook，但既有 v8 baseline 只能恢复 selected-only score/rank，不能安全做 reranking replay。
- 下一步：继续补 upstream logging，运行一次用户批准的 bounded audit replay 以生成完整 `decision_date x candidate` score/rank 留痕；在 readiness 为 true 前不得进入 reranking、v9 或扩池。
"""
    path.write_text(previous.rstrip() + "\n" + section, encoding="utf-8")


def write_run_summary(out_dir: Path, zip_path: Path, readiness: dict[str, Any]) -> None:
    text = f"""# RUN_SUMMARY

本轮目标：v8.2 score/rank audit trail instrumentation。

新 run 目录：`{out_dir}`

zip：`{zip_path}`

是否进入 v9：`False`

是否扩 universe：`False`

是否训练新模型：`False`

是否运行 31b：`False`

是否做 reranking replay：`False`

是否生成 full candidate score/rank：`False`

是否仍是 selected-only：`True`

can_run_gate_aware_reranking_replay：`{readiness.get('can_run_gate_aware_reranking_replay')}`

后续：继续补 upstream logging，生成完整 decision_date x candidate score/rank 留痕后再判断 reranking readiness。
"""
    (out_dir / "RUN_SUMMARY.md").write_text(text, encoding="utf-8")
    (PROJECT_ROOT / "RUN_SUMMARY.md").write_text(text, encoding="utf-8")


def write_audit_workbook(
    out_dir: Path,
    timestamp: str,
    pipeline: pd.DataFrame,
    schema: pd.DataFrame,
    audit: pd.DataFrame,
    quality: pd.DataFrame,
    warnings: pd.DataFrame,
    readiness: dict[str, Any],
    summary: dict[str, Any],
) -> Path:
    workbook_path = out_dir / "reports" / f"v8_2_score_rank_audit_workbook_{timestamp}.xlsx"
    write_excel(
        {
            "pipeline_map": pipeline,
            "schema": schema,
            "audit_sample": audit,
            "quality": quality,
            "warnings": warnings,
            "readiness": pd.DataFrame([to_jsonable(readiness)]),
            "summary": pd.DataFrame([to_jsonable(summary)]),
        },
        workbook_path,
    )
    return workbook_path


def package_outputs(out_dir: Path, docs: list[Path], zip_path: Path) -> None:
    files = [
        PROJECT_ROOT / "quant_lab" / "us_stock_selection" / "v8_2_audit_trail.py",
        PROJECT_ROOT / "quant_lab" / "us_stock_selection" / "v8_paper_trading.py",
        PROJECT_ROOT / "scripts" / "us_stock_selection" / "39_generate_v8_2_score_rank_audit_trail.py",
        PROJECT_ROOT / "NEXT_STEPS.md",
        PROJECT_ROOT / "RUN_SUMMARY.md",
    ]
    files.extend(docs)
    files.extend([p for p in out_dir.rglob("*") if p.is_file()])
    seen: set[str] = set()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            if not path.exists():
                continue
            arcname = str(path.relative_to(PROJECT_ROOT)) if path.is_relative_to(PROJECT_ROOT) else path.name
            if arcname in seen:
                continue
            seen.add(arcname)
            zf.write(path, arcname)


def main() -> None:
    args = parse_args()
    timestamp = args.timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = args.out_dir or OUTPUT_ROOT / f"v8_2_score_rank_audit_trail_{timestamp}"
    (out_dir / "reports").mkdir(parents=True, exist_ok=True)
    logger = setup_logger(out_dir)
    logger.info("Starting v8.2 score/rank audit trail instrumentation.")
    logger.info("Boundaries: no v9, no universe expansion, no training, no 31b, no reranking replay.")

    ensure_inputs(args.run_dir)
    pipe = pipeline_map()
    pipe.to_csv(out_dir / "v8_2_selection_pipeline_map.csv", index=False, encoding="utf-8-sig")
    write_pipeline_map_md(out_dir / "v8_2_selection_pipeline_map.md", pipe)
    schema = schema_rows()
    schema_date = timestamp[:8]
    schema_doc = DOCS_DIR / f"US_STOCK_SELECTION_V8_2_SCORE_RANK_AUDIT_SCHEMA_{schema_date}.md"
    write_schema_markdown(schema_doc, schema_date)
    shutil.copy2(schema_doc, out_dir / "reports" / schema_doc.name)

    if args.dry_run:
        summary = {
            "dry_run": True,
            "run_dir_exists": args.run_dir.exists(),
            "required_inputs_present": True,
            "output_dir": str(out_dir),
            "pipeline_map_rows": int(len(pipe)),
            "stopped_before": "provider_close_load_and_selected_only_audit_reconstruction",
        }
        write_json(summary, out_dir / "v8_2_score_rank_audit_summary.json")
        logger.info("Dry-run completed: %s", summary)
        return

    ledger = read_csv(args.run_dir / "v8_paper_trading" / "monthly_decision_ledger.csv")
    holdings = read_csv(args.run_dir / "v8_paper_trading" / "monthly_holdings.csv")
    ledger, holdings = filter_dates(ledger, holdings, args.start_date, args.end_date)
    requested_sample_months = parse_sample_months(args.sample_months)
    sample_months, sample_resolution_warnings = resolve_sample_months(ledger, requested_sample_months)
    close = load_close_for_selected(args.provider_uri, holdings, ledger, logger)
    audit, build_warnings = build_selected_only_audit_from_existing(
        run_id=args.run_dir.name,
        ledger=ledger,
        holdings=holdings,
        close=close,
        sample_months=sample_months,
        audit_forward_returns=bool_arg(args.audit_forward_returns),
    )
    quality, quality_warnings = validate_audit_quality(audit, holdings, ledger)
    warnings = pd.concat([build_warnings, quality_warnings], ignore_index=True) if not quality_warnings.empty else build_warnings
    if not sample_resolution_warnings.empty:
        warnings = pd.concat([sample_resolution_warnings, warnings], ignore_index=True)
    readiness = reranking_readiness(audit, quality)
    summary = build_summary(args.run_dir, audit, quality, warnings, readiness, sample_months, requested_sample_months)

    audit.to_csv(out_dir / "v8_2_score_rank_audit_trail.csv", index=False, encoding="utf-8-sig")
    quality.to_csv(out_dir / "v8_2_score_rank_audit_quality.csv", index=False, encoding="utf-8-sig")
    warnings.to_csv(out_dir / "v8_2_score_rank_audit_warnings.csv", index=False, encoding="utf-8-sig")
    quality.to_csv(out_dir / "v8_2_score_rank_audit_sample_validation.csv", index=False, encoding="utf-8-sig")
    write_json(summary, out_dir / "v8_2_score_rank_audit_summary.json")
    write_json(readiness, out_dir / "v8_2_reranking_readiness.json")

    for row in quality.to_dict(orient="records"):
        logger.info(
            "decision_date=%s candidate_count=%s selected_count=%s score_missing_count=%s rank_missing_count=%s quality_pass=%s",
            row.get("decision_date"),
            row.get("candidate_count"),
            row.get("selected_count"),
            row.get("score_missing_count"),
            row.get("rank_missing_count"),
            row.get("quality_pass"),
        )

    zip_path = OUTPUT_ROOT / f"us_stock_selection_quant_lab_v8_2_score_rank_audit_trail_{timestamp}.zip"
    report_path, exec_summary_path = write_reports(
        timestamp=timestamp,
        out_dir=out_dir,
        pipeline=pipe,
        schema=schema,
        quality=quality,
        warnings=warnings,
        readiness=readiness,
        summary=summary,
        zip_path=zip_path,
    )
    update_next_steps(out_dir, zip_path, readiness)
    write_run_summary(out_dir, zip_path, readiness)
    workbook_path = write_audit_workbook(out_dir, timestamp, pipe, schema, audit, quality, warnings, readiness, summary)
    logger.info("Wrote v8.2 score/rank audit workbook: %s", workbook_path)
    package_outputs(out_dir, [schema_doc, report_path, exec_summary_path], zip_path)
    logger.info("Packaged v8.2 score/rank audit trail zip: %s", zip_path)


if __name__ == "__main__":
    main()
