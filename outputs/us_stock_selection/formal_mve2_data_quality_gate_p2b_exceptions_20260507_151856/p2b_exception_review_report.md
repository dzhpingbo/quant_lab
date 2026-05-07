# Formal MVE2 Gate Exceptions Review P2-B

Run id: `formal_mve2_data_quality_gate_p2b_exceptions_20260507_151856`

## Executive Summary

- Gate exception decision: `CONDITIONAL_NEEDS_DATA_REVIEW`
- Can enter P2-C gate recheck: `false`
- Can enter P3 formal MVE2 search design: `false`
- Direct v10 remains forbidden.
- No strategy search, model training, formal MVE2, v10, or raw data repair was performed.

## Exception Counts

- Non-positive volume tickers: `6`
- Large jump tickers: `7`
- Large jump events: `9`
- Audit metadata warning rows: `51`
- Tickers blocking P3 after review: `0`

## Non-Positive Volume Detail

| ticker | eligible_status | in_limited_mve2_candidate | total_trading_days | volume_missing_count | volume_zero_count | volume_negative_count | non_positive_volume_count | non_positive_volume_rate | first_non_positive_volume_date | last_non_positive_volume_date | longest_non_positive_volume_run | median_volume | tradability_impact | recommendation | rationale | whether_blocks_p3 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AAPL | eligible | False | 11438 | 0 | 1 | 0 | 1 | 8.742787200559538e-05 | 1981-08-10 | 1981-08-10 | 1 | 196924000.0 | LOW_FLAG_ONLY | KEEP_WITH_FLAG | Eligible ticker has isolated non-positive volume rows. | False |
| AMD | eligible | False | 11626 | 0 | 2 | 0 | 2 | 0.0001720282126268708 | 1982-10-05 | 2015-01-02 | 1 | 8119000.0 | LOW_FLAG_ONLY | KEEP_WITH_FLAG | Eligible ticker has isolated non-positive volume rows. | False |
| ARKK | eligible | False | 2891 | 0 | 8 | 0 | 8 | 0.002767208578346593 | 2016-03-23 | 2016-11-16 | 1 | 1758100.0 | LOW_FLAG_ONLY | KEEP_WITH_FLAG | Eligible ticker has isolated non-positive volume rows. | False |
| IGV | eligible | False | 6235 | 0 | 7 | 0 | 7 | 0.0011226944667201283 | 2001-07-23 | 2001-10-19 | 1 | 775500.0 | LOW_FLAG_ONLY | KEEP_WITH_FLAG | Eligible ticker has isolated non-positive volume rows. | False |
| INTC | eligible | False | 11626 | 0 | 1 | 0 | 1 | 8.60141063134354e-05 | 1981-08-10 | 1981-08-10 | 1 | 45568600.0 | LOW_FLAG_ONLY | KEEP_WITH_FLAG | Eligible ticker has isolated non-positive volume rows. | False |
| SHOP | eligible | False | 2754 | 0 | 1 | 0 | 1 | 0.00036310820624546115 | 2015-05-20 | 2015-05-20 | 1 | 12128550.0 | LOW_FLAG_ONLY | KEEP_WITH_FLAG | Eligible ticker has isolated non-positive volume rows. | False |

## Large Daily Jump Detail

| ticker | eligible_status | in_limited_mve2_candidate | jump_date | prev_adj_close | adj_close | simple_return | volume | pre5_adj_close_min | pre5_adj_close_max | post5_adj_close_min | post5_adj_close_max | action_file_exists | action_nearby_plus_minus_5d | split_nearby_plus_minus_5d | dividend_nearby_plus_minus_5d | action_evidence | suspected_real_volatility | suspected_data_anomaly | affects_formal_mve2 | recommendation | rationale | whether_blocks_p3 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AAPL | eligible | False | 2000-09-29 | 0.8015104532241821 | 0.38577333092689514 | -0.518692077720171 | 7421640800.0 | 0.7331575751304626 | 0.8015104532241821 | 0.33052927255630493 | 0.36330175399780273 | True | False | False | False | none | True | False | False | KEEP_WITH_FLAG | Eligible ticker has a large move that appears tradable but should remain flagged. | False |
| AMD | eligible | False | 2016-04-22 | 2.619999885559082 | 3.990000009536743 | 0.5229008335186689 | 143265300.0 | 2.619999885559082 | 2.759999990463257 | 3.450000047683716 | 3.7300000190734863 | True | False | False | False | none | True | False | False | KEEP_WITH_FLAG | Eligible ticker has a large move that appears tradable but should remain flagged. | False |
| MSTR | eligible | True | 2000-03-20 | 226.75 | 86.75 | -0.61742006615215 | 17325600.0 | 226.75 | 294.359375 | 72.3125 | 129.0 | True | False | False | False | none | True | False | False | KEEP_WITH_FLAG | Candidate ticker has a large move that appears tradable but should remain flagged. | False |
| MSTR | eligible | True | 2001-04-19 | 2.9700000286102295 | 5.239999771118164 | 0.7643096702494476 | 10046600.0 | 2.4800000190734863 | 2.9700000286102295 | 4.099999904632568 | 5.639999866485596 | True | False | False | False | none | True | False | False | KEEP_WITH_FLAG | Candidate ticker has a large move that appears tradable but should remain flagged. | False |
| ROKU | excluded | False | 2017-11-09 | 18.84000015258789 | 29.190000534057617 | 0.5493630731233319 | 33372100.0 | 18.84000015258789 | 19.75 | 33.25 | 42.709999084472656 | True | False | False | False | none | True | False | False | OBSERVATION_ONLY | Ticker is not eligible for formal MVE2 universe. | False |
| SHOP | eligible | False | 2015-05-21 | 1.7000000476837158 | 2.568000078201294 | 0.5105882389240197 | 123039000.0 | 1.7000000476837158 | 1.7000000476837158 | 2.7200000286102295 | 2.9649999141693115 | True | False | False | False | none | True | False | False | KEEP_WITH_FLAG | Eligible ticker has a large move that appears tradable but should remain flagged. | False |
| SOXL | eligible | False | 2025-04-09 | 8.221614837646484 | 12.72606372833252 | 0.5478788510087242 | 787748800.0 | 8.221614837646484 | 16.204055786132812 | 9.30786418914795 | 10.563529968261719 | True | False | False | False | none | True | False | False | KEEP_WITH_FLAG | Eligible ticker has a large move that appears tradable but should remain flagged. | False |
| UPST | excluded | False | 2021-03-18 | 60.790000915527344 | 115.08999633789062 | 0.8932389308205069 | 21497900.0 | 58.0 | 62.93000030517578 | 112.27999877929688 | 164.8699951171875 | True | False | False | False | none | False | False | False | OBSERVATION_ONLY | Ticker is not eligible for formal MVE2 universe. | False |
| UPST | excluded | False | 2022-05-10 | 77.12999725341797 | 33.61000061035156 | -0.5642421650823778 | 68822500.0 | 77.12999725341797 | 93.56999969482422 | 28.0 | 46.65999984741211 | True | False | False | False | none | True | False | False | OBSERVATION_ONLY | Ticker is not eligible for formal MVE2 universe. | False |

## Metadata Conflict Detail

| conflict_type | involved_file | ticker | field_name | observed_value | expected_value | severity | affects_reproducibility | affects_formal_mve2_gate | recommended_fix |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| audit_csv_vs_price_parquet_row_count | data/unified_ohlcv/us_stock_selection/audit/price_quality_audit.csv | AAPL | n_rows;download_success | parquet_rows=11438; audit_rows=0; audit_success=False | audit rows and success should match readable parquet evidence | WARNING | True | True | Regenerate or reconcile store audit metadata before any formal MVE2 design. |
| audit_csv_vs_price_parquet_row_count | data/unified_ohlcv/us_stock_selection/audit/price_quality_audit.csv | ADBE | n_rows;download_success | parquet_rows=10006; audit_rows=0; audit_success=False | audit rows and success should match readable parquet evidence | WARNING | True | True | Regenerate or reconcile store audit metadata before any formal MVE2 design. |
| audit_csv_vs_price_parquet_row_count | data/unified_ohlcv/us_stock_selection/audit/price_quality_audit.csv | AMD | n_rows;download_success | parquet_rows=11626; audit_rows=0; audit_success=False | audit rows and success should match readable parquet evidence | WARNING | True | True | Regenerate or reconcile store audit metadata before any formal MVE2 design. |
| audit_csv_vs_price_parquet_row_count | data/unified_ohlcv/us_stock_selection/audit/price_quality_audit.csv | AMZN | n_rows;download_success | parquet_rows=7286; audit_rows=0; audit_success=False | audit rows and success should match readable parquet evidence | WARNING | True | True | Regenerate or reconcile store audit metadata before any formal MVE2 design. |
| audit_csv_vs_price_parquet_row_count | data/unified_ohlcv/us_stock_selection/audit/price_quality_audit.csv | AVGO | n_rows;download_success | parquet_rows=4210; audit_rows=0; audit_success=False | audit rows and success should match readable parquet evidence | WARNING | True | True | Regenerate or reconcile store audit metadata before any formal MVE2 design. |
| audit_csv_vs_price_parquet_row_count | data/unified_ohlcv/us_stock_selection/audit/price_quality_audit.csv | CRM | n_rows;download_success | parquet_rows=5500; audit_rows=0; audit_success=False | audit rows and success should match readable parquet evidence | WARNING | True | True | Regenerate or reconcile store audit metadata before any formal MVE2 design. |
| audit_csv_vs_price_parquet_row_count | data/unified_ohlcv/us_stock_selection/audit/price_quality_audit.csv | CRWD | n_rows;download_success | parquet_rows=1732; audit_rows=0; audit_success=False | audit rows and success should match readable parquet evidence | WARNING | True | True | Regenerate or reconcile store audit metadata before any formal MVE2 design. |
| audit_csv_vs_price_parquet_row_count | data/unified_ohlcv/us_stock_selection/audit/price_quality_audit.csv | GOOGL | n_rows;download_success | parquet_rows=5460; audit_rows=0; audit_success=False | audit rows and success should match readable parquet evidence | WARNING | True | True | Regenerate or reconcile store audit metadata before any formal MVE2 design. |
| audit_csv_vs_price_parquet_row_count | data/unified_ohlcv/us_stock_selection/audit/price_quality_audit.csv | META | n_rows;download_success | parquet_rows=3508; audit_rows=0; audit_success=False | audit rows and success should match readable parquet evidence | WARNING | True | True | Regenerate or reconcile store audit metadata before any formal MVE2 design. |
| audit_csv_vs_price_parquet_row_count | data/unified_ohlcv/us_stock_selection/audit/price_quality_audit.csv | MSFT | n_rows;download_success | parquet_rows=10112; audit_rows=0; audit_success=False | audit rows and success should match readable parquet evidence | WARNING | True | True | Regenerate or reconcile store audit metadata before any formal MVE2 design. |
| audit_csv_vs_price_parquet_row_count | data/unified_ohlcv/us_stock_selection/audit/price_quality_audit.csv | NET | n_rows;download_success | parquet_rows=1667; audit_rows=0; audit_success=False | audit rows and success should match readable parquet evidence | WARNING | True | True | Regenerate or reconcile store audit metadata before any formal MVE2 design. |
| audit_csv_vs_price_parquet_row_count | data/unified_ohlcv/us_stock_selection/audit/price_quality_audit.csv | NFLX | n_rows;download_success | parquet_rows=6024; audit_rows=0; audit_success=False | audit rows and success should match readable parquet evidence | WARNING | True | True | Regenerate or reconcile store audit metadata before any formal MVE2 design. |
| audit_csv_vs_price_parquet_row_count | data/unified_ohlcv/us_stock_selection/audit/price_quality_audit.csv | NOW | n_rows;download_success | parquet_rows=3479; audit_rows=0; audit_success=False | audit rows and success should match readable parquet evidence | WARNING | True | True | Regenerate or reconcile store audit metadata before any formal MVE2 design. |
| audit_csv_vs_price_parquet_row_count | data/unified_ohlcv/us_stock_selection/audit/price_quality_audit.csv | NVDA | n_rows;download_success | parquet_rows=6861; audit_rows=0; audit_success=False | audit rows and success should match readable parquet evidence | WARNING | True | True | Regenerate or reconcile store audit metadata before any formal MVE2 design. |
| audit_csv_vs_price_parquet_row_count | data/unified_ohlcv/us_stock_selection/audit/price_quality_audit.csv | ORCL | n_rows;download_success | parquet_rows=10113; audit_rows=0; audit_success=False | audit rows and success should match readable parquet evidence | WARNING | True | True | Regenerate or reconcile store audit metadata before any formal MVE2 design. |
| audit_csv_vs_price_parquet_row_count | data/unified_ohlcv/us_stock_selection/audit/price_quality_audit.csv | PLTR | n_rows;download_success | parquet_rows=1403; audit_rows=0; audit_success=False | audit rows and success should match readable parquet evidence | WARNING | True | True | Regenerate or reconcile store audit metadata before any formal MVE2 design. |
| audit_csv_vs_price_parquet_row_count | data/unified_ohlcv/us_stock_selection/audit/price_quality_audit.csv | SHOP | n_rows;download_success | parquet_rows=2754; audit_rows=0; audit_success=False | audit rows and success should match readable parquet evidence | WARNING | True | True | Regenerate or reconcile store audit metadata before any formal MVE2 design. |
| audit_csv_vs_price_parquet_row_count | data/unified_ohlcv/us_stock_selection/audit/price_quality_audit.csv | SNOW | n_rows;download_success | parquet_rows=1413; audit_rows=0; audit_success=False | audit rows and success should match readable parquet evidence | WARNING | True | True | Regenerate or reconcile store audit metadata before any formal MVE2 design. |
| audit_csv_vs_price_parquet_row_count | data/unified_ohlcv/us_stock_selection/audit/price_quality_audit.csv | TSLA | n_rows;download_success | parquet_rows=3985; audit_rows=0; audit_success=False | audit rows and success should match readable parquet evidence | WARNING | True | True | Regenerate or reconcile store audit metadata before any formal MVE2 design. |
| audit_csv_vs_price_parquet_row_count | data/unified_ohlcv/us_stock_selection/audit/price_quality_audit.csv | DIA | n_rows;download_success | parquet_rows=7115; audit_rows=0; audit_success=False | audit rows and success should match readable parquet evidence | WARNING | True | True | Regenerate or reconcile store audit metadata before any formal MVE2 design. |

_Showing first 20 of 53 rows._

## Ticker-Level Recommendations

| ticker | eligible_status | anomaly_types | severity | recommended_action | rationale | whether_blocks_p3 |
| --- | --- | --- | --- | --- | --- | --- |
| AAPL | eligible | non_positive_volume;large_daily_price_jump;audit_metadata_conflict | WARNING | KEEP_WITH_FLAG | Ticker has isolated quality flags but no direct block after this review. | False |
| ADBE | eligible | audit_metadata_conflict | METADATA_REVIEW | KEEP_WITH_FLAG | Only audit metadata conflict is present; price parquet is readable. | False |
| AFRM | excluded | audit_metadata_conflict | METADATA_REVIEW | KEEP_WITH_FLAG | Only audit metadata conflict is present; price parquet is readable. | False |
| AMD | eligible | non_positive_volume;large_daily_price_jump;audit_metadata_conflict | WARNING | KEEP_WITH_FLAG | Ticker has isolated quality flags but no direct block after this review. | False |
| AMZN | eligible | audit_metadata_conflict | METADATA_REVIEW | KEEP_WITH_FLAG | Only audit metadata conflict is present; price parquet is readable. | False |
| ARKK | eligible | non_positive_volume;audit_metadata_conflict | WARNING | KEEP_WITH_FLAG | Ticker has isolated quality flags but no direct block after this review. | False |
| AVGO | eligible | audit_metadata_conflict | METADATA_REVIEW | KEEP_WITH_FLAG | Only audit metadata conflict is present; price parquet is readable. | False |
| CIBR | eligible | audit_metadata_conflict | METADATA_REVIEW | KEEP_WITH_FLAG | Only audit metadata conflict is present; price parquet is readable. | False |
| COIN | excluded | audit_metadata_conflict | METADATA_REVIEW | KEEP_WITH_FLAG | Only audit metadata conflict is present; price parquet is readable. | False |
| CRM | eligible | audit_metadata_conflict | METADATA_REVIEW | KEEP_WITH_FLAG | Only audit metadata conflict is present; price parquet is readable. | False |
| CRWD | excluded | audit_metadata_conflict | METADATA_REVIEW | KEEP_WITH_FLAG | Only audit metadata conflict is present; price parquet is readable. | False |
| DIA | eligible | audit_metadata_conflict | METADATA_REVIEW | KEEP_WITH_FLAG | Only audit metadata conflict is present; price parquet is readable. | False |
| GLD | eligible | audit_metadata_conflict | METADATA_REVIEW | KEEP_WITH_FLAG | Only audit metadata conflict is present; price parquet is readable. | False |
| GOOGL | eligible | audit_metadata_conflict | METADATA_REVIEW | KEEP_WITH_FLAG | Only audit metadata conflict is present; price parquet is readable. | False |
| IBB | eligible | audit_metadata_conflict | METADATA_REVIEW | KEEP_WITH_FLAG | Only audit metadata conflict is present; price parquet is readable. | False |
| IGV | eligible | non_positive_volume;audit_metadata_conflict | WARNING | KEEP_WITH_FLAG | Ticker has isolated quality flags but no direct block after this review. | False |
| INTC | eligible | non_positive_volume;audit_metadata_conflict | WARNING | KEEP_WITH_FLAG | Ticker has isolated quality flags but no direct block after this review. | False |
| IWM | eligible | audit_metadata_conflict | METADATA_REVIEW | KEEP_WITH_FLAG | Only audit metadata conflict is present; price parquet is readable. | False |
| LCID | excluded | audit_metadata_conflict | METADATA_REVIEW | KEEP_WITH_FLAG | Only audit metadata conflict is present; price parquet is readable. | False |
| META | eligible | audit_metadata_conflict | METADATA_REVIEW | KEEP_WITH_FLAG | Only audit metadata conflict is present; price parquet is readable. | False |

_Showing first 20 of 51 rows._

## Conclusion

P2-B remains conservative. It does not change any limited MVE2 decision and does not promote limited MVE2 to a formal baseline. The current formal baseline remains v8.2 frozen Pool A `top5_ytdcap80p_derisk100p`; formal v9 remains a failed branch.
