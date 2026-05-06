"""Reporting and packaging helpers for v9.1 growth onboarding."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from quant_lab.us_stock_selection.utils import PROJECT_ROOT, save_text, write_excel, zip_selected_paths


def build_v9_1_report(path: Path | str, result: dict[str, Any], zip_path: Path | str | None = None) -> Path:
    verdict = dict(result.get("verdict", {}))
    inventory = result.get("inventory", pd.DataFrame())
    eligibility = result.get("eligibility", pd.DataFrame())
    feature_status = result.get("feature_status", {})
    score_status = result.get("score_status", {})
    provider_status = result.get("provider_status", {})
    pool_check = result.get("pool_a_reproduction_check", pd.DataFrame())
    coverage = result.get("candidate_coverage", pd.DataFrame())
    by_month = result.get("score_availability_by_month", pd.DataFrame())
    topk = result.get("topk_candidate_overlap", pd.DataFrame())
    excluded = inventory.loc[~inventory.get("data_quality_status", pd.Series(dtype=str)).astype(str).eq("ready_for_provider")].copy() if not inventory.empty else pd.DataFrame()
    ready = inventory.loc[inventory.get("data_quality_status", pd.Series(dtype=str)).astype(str).eq("ready_for_provider")].copy() if not inventory.empty else pd.DataFrame()

    text = f"""# v9.1 Growth Data Onboarding Report

## Verdict

- classification: `{verdict.get("classification")}`
- new provider success: `{verdict.get("provider_success")}`
- Alpha360 cache success: `{verdict.get("feature_cache_success")}`
- LGBModel score provenance success: `{verdict.get("score_provenance_success")}`
- incremental data ready count: `{verdict.get("incremental_data_ready_count")}`
- incremental eligible growth count: `{verdict.get("incremental_eligible_growth_count")}`
- growth TopK candidate count: `{verdict.get("growth_topk_candidate_count")}`
- Pool A reproduction aligned: `{verdict.get("pool_a_reproduction_aligned")}`
- allow formal v9 rerun: `{verdict.get("allow_formal_v9_rerun")}`
- allow enter v10: `{verdict.get("allow_enter_v10")}`
- requires human review: `{verdict.get("requires_human_review")}`
- zip_path: `{zip_path or verdict.get("zip_path", "")}`

## Required Answers

1. Which growth tickers have data?
   - Ready count: `{len(ready)}`. See `v9_1_data_inventory.csv`.
2. Which still miss data?
   - Missing/quality issue count: `{len(excluded)}`. See `v9_1_data_inventory.csv`.
3. Which satisfy dynamic eligibility?
   - Eligible count: `{verdict.get("incremental_eligible_growth_count")}`. See `v9_1_eligibility_result.csv`.
4. Which are observation-only?
   - Rows with `eligible_for_formal_v9=False` in `v9_1_eligibility_result.csv`.
5. Did the new provider succeed?
   - `{verdict.get("provider_success")}`. Provider URI: `{provider_status.get("provider_uri", "")}`.
6. Did Alpha360 cache succeed?
   - `{verdict.get("feature_cache_success")}`. Rows: `{feature_status.get("row_count", 0)}`; features: `{feature_status.get("feature_count", 0)}`.
7. Did LGBModel score provenance succeed?
   - `{verdict.get("score_provenance_success")}`. Score months: `{score_status.get("score_month_count", 0)}`; score rows: `{score_status.get("score_row_count", 0)}`.
8. Does Pool A reproduction still align?
   - `{verdict.get("pool_a_reproduction_aligned")}`. See `preflight_pool_a_reproduction_check.csv`.
9. Can new tickers enter TopK candidates?
   - Growth TopK candidate count: `{verdict.get("growth_topk_candidate_count")}`. See `preflight_topk_candidate_overlap.csv`.
10. Is formal v9 rerun allowed?
    - `{verdict.get("allow_formal_v9_rerun")}`.
11. Is v10 allowed?
    - No.
12. Is human review required?
    - `{verdict.get("requires_human_review")}`.

## Provider Status

```json
{json_dump(provider_status)}
```

## Feature Cache Status

```json
{json_dump(feature_status)}
```

## Score Provenance Status

```json
{json_dump(score_status)}
```

## Pool A Reproduction Check

{to_markdown(pool_check)}

## Data Ready Tickers

{to_markdown(ready, max_rows=80)}

## Eligibility

{to_markdown(eligibility, max_rows=80)}

## Candidate Coverage

{to_markdown(coverage, max_rows=80)}

## Score Availability By Month

{to_markdown(by_month, max_rows=40)}

## TopK Candidate Overlap

{to_markdown(topk, max_rows=40)}
"""
    return save_text(text, path)


def build_v9_1_excel(path: Path | str, result: dict[str, Any]) -> Path:
    sheets = {
        "verdict": pd.DataFrame([result.get("verdict", {})]),
        "inventory": result.get("inventory", pd.DataFrame()),
        "eligibility": result.get("eligibility", pd.DataFrame()),
        "provider": pd.DataFrame([result.get("provider_status", {})]),
        "feature_status": pd.DataFrame([result.get("feature_status", {})]),
        "score_status": pd.DataFrame([result.get("score_status", {})]),
        "pool_check": result.get("pool_a_reproduction_check", pd.DataFrame()),
        "coverage": result.get("candidate_coverage", pd.DataFrame()),
        "score_by_month": result.get("score_availability_by_month", pd.DataFrame()),
        "topk": result.get("topk_candidate_overlap", pd.DataFrame()),
        "fit_log": result.get("fit_log", pd.DataFrame()),
        "score_audit_sample": result.get("score_audit", pd.DataFrame()).head(5000),
    }
    return write_excel(sheets, path)


def package_v9_1_run(run_dir: Path | str, timestamp: str) -> Path:
    base = Path(run_dir)
    zip_path = PROJECT_ROOT / "outputs" / "us_stock_selection" / f"us_stock_selection_v9_1_growth_data_onboarding_{timestamp}.zip"
    paths = [
        base,
        PROJECT_ROOT / "RUN_SUMMARY.md",
        PROJECT_ROOT / "NEXT_STEPS.md",
        PROJECT_ROOT / "quant_lab" / "us_stock_selection" / "v9_1_growth_data_onboarding.py",
        PROJECT_ROOT / "quant_lab" / "us_stock_selection" / "v9_1_score_provenance_builder.py",
        PROJECT_ROOT / "quant_lab" / "us_stock_selection" / "v9_1_reporting.py",
        PROJECT_ROOT / "scripts" / "us_stock_selection" / "40_run_v9_1_growth_data_onboarding.py",
    ]
    return zip_selected_paths(paths, zip_path, root=PROJECT_ROOT)


def to_markdown(df: pd.DataFrame, max_rows: int = 30) -> str:
    if df is None or df.empty:
        return "_No rows._"
    clipped = df.head(max_rows).copy()
    try:
        return clipped.to_markdown(index=False)
    except Exception:
        return clipped.to_csv(index=False)


def json_dump(data: Any) -> str:
    import json

    return json.dumps(data, ensure_ascii=False, indent=2, default=str)
