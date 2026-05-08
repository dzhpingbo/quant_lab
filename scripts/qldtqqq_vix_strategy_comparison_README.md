# QLD/TQQQ VIX Strategy Comparison

## Purpose

`qldtqqq_vix_strategy_comparison.py` is an independent research helper for comparing:

- QQQ / QLD / TQQQ buy-and-hold references
- QLD/TQQQ lab turning strategy outputs from an existing `qldtqqq_turning_*` run
- VIX 35/15 panic-buy timing rules
- VIX price-ladder timing rules

It reads an existing qldtqqq turning-point run and produces a comparison packet with Markdown, CSV, XLSX, JSON, log, summary, and zip outputs.

## Chain Boundary

This script is not part of FORMAL_MVE2.

It must not be used to replace the v8.2 frozen baseline.

It must not create v10.

It is research-only, is not trading advice, and does not connect to broker/API services.

Use it as a side packet for QLD/TQQQ/VIX research only. Do not mix it into the formal MVE2, P6, P7, v8.2, formal v9, or v10 evidence chain.

## Recommended Usage

Dry-run / no-write plan:

```powershell
python scripts/qldtqqq_vix_strategy_comparison.py --dry-run
python scripts/qldtqqq_vix_strategy_comparison.py --no-write
```

Explicit source run for reproducibility:

```powershell
python scripts/qldtqqq_vix_strategy_comparison.py --input-run outputs/qldtqqq_turning_points/qldtqqq_turning_<STAMP> --dry-run
```

Write an output packet after checking the dry-run plan:

```powershell
python scripts/qldtqqq_vix_strategy_comparison.py --input-run outputs/qldtqqq_turning_points/qldtqqq_turning_<STAMP> --stamp <NEW_STAMP>
```

Overwrite is off by default. If the output directory or zip already exists, the script exits before writing. Use `--overwrite` only after confirming the target run is safe to reuse.

## Outputs

The script writes a run directory like:

```text
outputs/qldtqqq_turning_points/vix_vs_lab_strategy_<STAMP>/
```

Expected files include:

- `logs/run.log`
- `reports/comparison_report.md`
- `reports/comparison_metrics.xlsx`
- `strategy_period_metrics.csv`
- `canonical_comparison.csv`
- `trade_log.csv`
- `trade_summary.csv`
- `vix_threshold_counts.csv`
- `vix_regime_counts.csv`
- `data_latest_dates.csv`
- `ranking_test_2021_latest.csv`
- `RUN_SUMMARY.json`
- `RUN_SUMMARY.md`
- `NEXT_STEPS.md`
- `manifest.json`
- zip archive next to the run directory

## Reproducibility Notes

If `--input-run` is omitted, the script selects the newest `qldtqqq_turning_*` directory by modified time. This is convenient but not fully reproducible.

For any formal reuse, pass `--input-run` explicitly and keep the output packet as an independent research artifact.

## Commit Hygiene

If this script is accepted into the repository, commit it separately from group4 bridge runtime files and separately from FORMAL_MVE2 artifacts.

Do not use `git add .` for this script.
