# Limited MVE2 Validation Pack

Run id: `limited_mve2_validation_20260502_183555`

This directory is a standalone review pack for the limited MVE2 validation run. It belongs to an independent audited-store research line and is not part of the v8.2 frozen formal baseline evidence chain.

## Scope

- Source search run: `limited_mve2_20260502_142702`
- Candidate count: `9`
- Decision distribution: `1` pass_to_next_validation, `6` conditional, `2` observation_only
- Formal MVE2 support: `false` for every candidate
- Data source policy: audited unified adjusted OHLCV store
- Core fields: `adj_close` and `volume`
- Exclusions: old qlib data, old v8 cache, formal v9 output, and v8.2 formal baseline output

## How To Review

Start with `selected_report.md`, then inspect `key_metrics_summary.csv` and the reviewer tables in `small_tables/`. The original detailed validation evidence remains in the `validation_*` CSV files and `reports/limited_mve2_validation_report.md`.

## How To Reproduce This Pack

Run `python scripts/us_stock_selection/52_build_limited_mve2_validation_pack_addendum.py` from the repository root. The script only reads existing limited MVE2 outputs and rebuilds the addendum files plus `outputs/us_stock_selection/limited_mve2_validation_20260502_183555.zip`. It does not rerun strategy search, train a model, or change candidate decisions.

## Missing Metric Policy

When a metric is not present in the existing validation evidence, the addendum writes `NA`. No metric is inferred or filled from another evidence chain.

## Output Files

- `manifest.json`
- `key_metrics_summary.csv`
- `selected_report.md`
- `README.md`
- `small_tables/decision_counts.csv`
- `small_tables/candidate_decisions.csv`
- `small_tables/available_evidence_files.csv`
- `small_tables/missing_or_partial_items.csv`
- `small_tables/data_source_policy.csv`
- `small_tables/reproducibility_checklist.csv`

## Restrictions

This pack has not entered formal MVE2, cannot be used as a formal baseline, and cannot be used as a v10 starting point. The next allowed step is P1-B human review or a separate P2 formal MVE2 data quality gate.
