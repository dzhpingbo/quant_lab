# Formal MVE2 Data Quality Gate P2-A

Run id: `formal_mve2_data_quality_gate_20260507_142224`

## Executive Summary

- Readiness decision: `CONDITIONAL_NEEDS_REVIEW`
- Can enter P3 formal MVE2 search design: `false`
- Direct v10 remains forbidden.
- No strategy search, model training, formal MVE2, or v10 execution was performed.
- group4 hold artifacts were not touched.

## Input Data Source

- Store: `data/unified_ohlcv/us_stock_selection`
- Price files: `51`
- Source universe run: `limited_mve2_20260502_142702`
- Validation pack: `limited_mve2_validation_20260502_183555`
- Excluded evidence chains: old qlib, old v8 cache, formal v9 outputs, v8.2 formal baseline outputs.

## Universe

- Eligible tickers: `40`
- Excluded tickers: `11`
- Universe and eligibility evidence is read from the limited MVE2 search run.
- Candidate decisions from the validation pack are used only for alignment checks.

## Field Coverage

Core fields are `date`, `ticker`, `adj_close`, and `volume`.

| field | required_for_p2a | present_ticker_count | missing_ticker_count | present_rate |
| --- | --- | --- | --- | --- |
| date | True | 51 | 0 | 1.0 |
| ticker | True | 51 | 0 | 1.0 |
| adj_close | True | 51 | 0 | 1.0 |
| volume | True | 51 | 0 | 1.0 |
| open | False | 51 | 0 | 1.0 |
| high | False | 51 | 0 | 1.0 |
| low | False | 51 | 0 | 1.0 |
| close | False | 51 | 0 | 1.0 |

## Time Coverage

- Global common first available date across price files: `2021-11-10`
- Global common last available date across price files: `2026-05-01`
- Per-ticker detail is in `date_coverage_summary.csv`.

## Missingness And Anomalies

- Tickers with adj_close missing rows: `0`
- Tickers with volume missing rows: `0`
- Tickers with daily adjusted-return absolute jump above `50%`: `7`
- Tickers with at least five consecutive zero or missing volume rows: `0`

## Liquidity

`volume` is checked as a quality and liquidity field. Low-volume and zero-volume indicators are warnings only and are not investment conclusions.

## Risk Flags

| flag_id | severity | status | affected_count | detail | evidence_file |
| --- | --- | --- | --- | --- | --- |
| audited_store_present | critical | PASS | 0 | Audited unified adjusted OHLCV store root and price directory checked. | data/unified_ohlcv/us_stock_selection |
| price_parquet_present | critical | PASS | 51 | Price parquet files are the only price input for this gate. | data/unified_ohlcv/us_stock_selection/prices |
| required_fields_present | critical | PASS | 0 | Required fields are date, ticker, adj_close, volume. | data/unified_ohlcv/us_stock_selection/prices |
| universe_price_alignment | warning | PASS | 0 | Search universe and price files should align. | outputs/us_stock_selection/limited_mve2_20260502_142702 |
| candidate_eligible_alignment | critical | PASS | 0 | Validation candidate tickers should remain inside the eligible universe. | outputs/us_stock_selection/limited_mve2_validation_20260502_183555/validation_decision_summary.csv |
| eligible_limited_window_coverage | warning | PASS | 0 | Eligible tickers should cover the limited MVE2 common window. | outputs/us_stock_selection/limited_mve2_20260502_142702/limited_mve2_run_config.json |
| adj_close_missingness | critical | PASS | 0 | adj_close is a core field. | data/unified_ohlcv/us_stock_selection/prices |
| volume_missingness | warning | PASS | 0 | volume is a core field. | data/unified_ohlcv/us_stock_selection/prices |
| non_positive_adj_close | critical | PASS | 0 | Non-positive adjusted prices are not acceptable for formal design. | data/unified_ohlcv/us_stock_selection/prices |
| non_positive_volume | warning | WARN | 6 | Non-positive volume is a liquidity quality warning. | data/unified_ohlcv/us_stock_selection/prices |
| duplicate_date_ticker | critical | PASS | 0 | Duplicate date-ticker rows are not acceptable. | data/unified_ohlcv/us_stock_selection/prices |
| large_daily_price_jump | warning | WARN | 7 | Daily adjusted-return absolute jump threshold is 50%. | data/unified_ohlcv/us_stock_selection/prices |
| long_zero_or_missing_volume_run | warning | PASS | 0 | Flags tickers with at least five consecutive zero or missing volume rows. | data/unified_ohlcv/us_stock_selection/prices |
| audit_metadata_conflict | warning | WARN | 51 | Audit CSV rows disagree with readable price parquet rows. | data/unified_ohlcv/us_stock_selection/audit/price_quality_audit.csv |
| evidence_chain_exclusion | critical | PASS | 0 | The gate uses only audited store plus limited MVE2 outputs; formal v9 and v8.2 baseline outputs are excluded. | outputs/us_stock_selection/limited_mve2_validation_20260502_183555/manifest.json |

## Decision Rationale

The gate is conservative. Any critical failure produces `FAIL_DATA_GATE`; any warning produces `CONDITIONAL_NEEDS_REVIEW`; a clean run produces `PASS_TO_FORMAL_MVE2_DESIGN`.

## Allowed Next Actions

- If decision is `PASS_TO_FORMAL_MVE2_DESIGN`, design P3 only after human review.
- If decision is `CONDITIONAL_NEEDS_REVIEW`, resolve or explicitly accept the listed warnings before P3.
- If decision is `FAIL_DATA_GATE`, repair the data evidence chain first.

## Forbidden Actions

- Do not treat limited MVE2 as a formal baseline.
- Do not treat formal v9 as a baseline.
- Do not start v10 from this gate.
- Do not mix this audited-store line with v8.2 or formal v9 evidence chains.
- Do not release group4 hold inside this task.
