# Formal MVE2 Data Quality Gate P2-A

This directory contains a lightweight data quality gate for deciding whether the audited unified adjusted OHLCV store is ready to support formal MVE2 design.

Run id: `formal_mve2_data_quality_gate_20260507_142224`

Decision: `CONDITIONAL_NEEDS_REVIEW`

The gate reads only:

- `data/unified_ohlcv/us_stock_selection`
- `outputs/us_stock_selection/limited_mve2_20260502_142702`
- `outputs/us_stock_selection/limited_mve2_validation_20260502_183555`

It does not run strategy search, train a model, start formal MVE2, start v10, or alter existing candidate decisions.

Review order:

1. `data_quality_gate_report.md`
2. `formal_mve2_readiness_decision.json`
3. `risk_flags.csv`
4. `gate_summary.csv`
5. Coverage and anomaly CSV files
6. `small_tables/`

The current formal baseline remains v8.2 frozen Pool A `top5_ytdcap80p_derisk100p`. formal v9 remains a failed branch.
