# Formal MVE2 Audit Metadata Reconciliation P2-B2

Run id: `formal_mve2_audit_metadata_reconciliation_p2b2_20260507_161429`

## Executive Summary

- Reconciliation decision: `PASS_TO_P2C_GATE_RECHECK`
- Can enter P2-C gate recheck: `true`
- Can enter P3 formal MVE2 search design: `false`
- Direct v10 remains forbidden.
- No strategy search, model training, formal MVE2, v10, raw price repair, or audit CSV repair was performed.

## Core Finding

The P2-B metadata conflict is attributable to stale `price_quality_audit.csv` rows. The audit CSV records failed refresh metadata, while price parquet files are readable and store manifest row counts reconcile with parquet row counts.

- Stale audit metadata rows: `51`
- Critical parquet evidence failures: `0`

## Reconciliation Summary

| metric | value |
| --- | --- |
| reconciliation_decision | PASS_TO_P2C_GATE_RECHECK |
| can_enter_p2c_gate_recheck | True |
| can_enter_p3_formal_search_design | False |
| direct_v10_allowed | False |
| ticker_count | 51 |
| parquet_readable_count | 51 |
| required_fields_present_count | 51 |
| audit_row_count_mismatch_count | 51 |
| manifest_row_count_match_count | 51 |
| audit_success_flag_mismatch_count | 51 |
| stale_audit_metadata_count | 51 |

## Audit CSV vs Parquet Detail

| ticker | audit_metadata_file | audit_row_count | audit_success_flag | parquet_file | parquet_exists | parquet_readable | parquet_row_count | parquet_date_min | parquet_date_max | parquet_required_fields_present | manifest_row_count | manifest_path | row_count_match | success_flag_match | conflict_type | severity | likely_explanation | recommended_action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AAPL | data/unified_ohlcv/us_stock_selection/audit/price_quality_audit.csv | 0 | False | data/unified_ohlcv/us_stock_selection/prices/AAPL.parquet | True | True | 11438 | 1980-12-12 | 2026-05-01 | True | 11438 | data/unified_ohlcv/us_stock_selection/prices/AAPL.parquet | False | False | STALE_AUDIT_METADATA;AUDIT_ROW_COUNT_MISMATCH;AUDIT_SUCCESS_FLAG_MISMATCH | WARNING | price_quality audit records a failed refresh while parquet and store manifest show readable entity data. | Allow P2-C recheck using parquet-derived metadata; regenerate audit metadata before P3. |
| ADBE | data/unified_ohlcv/us_stock_selection/audit/price_quality_audit.csv | 0 | False | data/unified_ohlcv/us_stock_selection/prices/ADBE.parquet | True | True | 10006 | 1986-08-13 | 2026-05-01 | True | 10006 | data/unified_ohlcv/us_stock_selection/prices/ADBE.parquet | False | False | STALE_AUDIT_METADATA;AUDIT_ROW_COUNT_MISMATCH;AUDIT_SUCCESS_FLAG_MISMATCH | WARNING | price_quality audit records a failed refresh while parquet and store manifest show readable entity data. | Allow P2-C recheck using parquet-derived metadata; regenerate audit metadata before P3. |
| AFRM | data/unified_ohlcv/us_stock_selection/audit/price_quality_audit.csv | 0 | False | data/unified_ohlcv/us_stock_selection/prices/AFRM.parquet | True | True | 1331 | 2021-01-13 | 2026-05-01 | True | 1331 | data/unified_ohlcv/us_stock_selection/prices/AFRM.parquet | False | False | STALE_AUDIT_METADATA;AUDIT_ROW_COUNT_MISMATCH;AUDIT_SUCCESS_FLAG_MISMATCH | WARNING | price_quality audit records a failed refresh while parquet and store manifest show readable entity data. | Allow P2-C recheck using parquet-derived metadata; regenerate audit metadata before P3. |
| AMD | data/unified_ohlcv/us_stock_selection/audit/price_quality_audit.csv | 0 | False | data/unified_ohlcv/us_stock_selection/prices/AMD.parquet | True | True | 11626 | 1980-03-17 | 2026-05-01 | True | 11626 | data/unified_ohlcv/us_stock_selection/prices/AMD.parquet | False | False | STALE_AUDIT_METADATA;AUDIT_ROW_COUNT_MISMATCH;AUDIT_SUCCESS_FLAG_MISMATCH | WARNING | price_quality audit records a failed refresh while parquet and store manifest show readable entity data. | Allow P2-C recheck using parquet-derived metadata; regenerate audit metadata before P3. |
| AMZN | data/unified_ohlcv/us_stock_selection/audit/price_quality_audit.csv | 0 | False | data/unified_ohlcv/us_stock_selection/prices/AMZN.parquet | True | True | 7286 | 1997-05-15 | 2026-05-01 | True | 7286 | data/unified_ohlcv/us_stock_selection/prices/AMZN.parquet | False | False | STALE_AUDIT_METADATA;AUDIT_ROW_COUNT_MISMATCH;AUDIT_SUCCESS_FLAG_MISMATCH | WARNING | price_quality audit records a failed refresh while parquet and store manifest show readable entity data. | Allow P2-C recheck using parquet-derived metadata; regenerate audit metadata before P3. |
| ARKK | data/unified_ohlcv/us_stock_selection/audit/price_quality_audit.csv | 0 | False | data/unified_ohlcv/us_stock_selection/prices/ARKK.parquet | True | True | 2891 | 2014-10-31 | 2026-05-01 | True | 2891 | data/unified_ohlcv/us_stock_selection/prices/ARKK.parquet | False | False | STALE_AUDIT_METADATA;AUDIT_ROW_COUNT_MISMATCH;AUDIT_SUCCESS_FLAG_MISMATCH | WARNING | price_quality audit records a failed refresh while parquet and store manifest show readable entity data. | Allow P2-C recheck using parquet-derived metadata; regenerate audit metadata before P3. |
| AVGO | data/unified_ohlcv/us_stock_selection/audit/price_quality_audit.csv | 0 | False | data/unified_ohlcv/us_stock_selection/prices/AVGO.parquet | True | True | 4210 | 2009-08-06 | 2026-05-01 | True | 4210 | data/unified_ohlcv/us_stock_selection/prices/AVGO.parquet | False | False | STALE_AUDIT_METADATA;AUDIT_ROW_COUNT_MISMATCH;AUDIT_SUCCESS_FLAG_MISMATCH | WARNING | price_quality audit records a failed refresh while parquet and store manifest show readable entity data. | Allow P2-C recheck using parquet-derived metadata; regenerate audit metadata before P3. |
| CIBR | data/unified_ohlcv/us_stock_selection/audit/price_quality_audit.csv | 0 | False | data/unified_ohlcv/us_stock_selection/prices/CIBR.parquet | True | True | 2722 | 2015-07-07 | 2026-05-01 | True | 2722 | data/unified_ohlcv/us_stock_selection/prices/CIBR.parquet | False | False | STALE_AUDIT_METADATA;AUDIT_ROW_COUNT_MISMATCH;AUDIT_SUCCESS_FLAG_MISMATCH | WARNING | price_quality audit records a failed refresh while parquet and store manifest show readable entity data. | Allow P2-C recheck using parquet-derived metadata; regenerate audit metadata before P3. |
| COIN | data/unified_ohlcv/us_stock_selection/audit/price_quality_audit.csv | 0 | False | data/unified_ohlcv/us_stock_selection/prices/COIN.parquet | True | True | 1269 | 2021-04-14 | 2026-05-01 | True | 1269 | data/unified_ohlcv/us_stock_selection/prices/COIN.parquet | False | False | STALE_AUDIT_METADATA;AUDIT_ROW_COUNT_MISMATCH;AUDIT_SUCCESS_FLAG_MISMATCH | WARNING | price_quality audit records a failed refresh while parquet and store manifest show readable entity data. | Allow P2-C recheck using parquet-derived metadata; regenerate audit metadata before P3. |
| CRM | data/unified_ohlcv/us_stock_selection/audit/price_quality_audit.csv | 0 | False | data/unified_ohlcv/us_stock_selection/prices/CRM.parquet | True | True | 5500 | 2004-06-23 | 2026-05-01 | True | 5500 | data/unified_ohlcv/us_stock_selection/prices/CRM.parquet | False | False | STALE_AUDIT_METADATA;AUDIT_ROW_COUNT_MISMATCH;AUDIT_SUCCESS_FLAG_MISMATCH | WARNING | price_quality audit records a failed refresh while parquet and store manifest show readable entity data. | Allow P2-C recheck using parquet-derived metadata; regenerate audit metadata before P3. |
| CRWD | data/unified_ohlcv/us_stock_selection/audit/price_quality_audit.csv | 0 | False | data/unified_ohlcv/us_stock_selection/prices/CRWD.parquet | True | True | 1732 | 2019-06-12 | 2026-05-01 | True | 1732 | data/unified_ohlcv/us_stock_selection/prices/CRWD.parquet | False | False | STALE_AUDIT_METADATA;AUDIT_ROW_COUNT_MISMATCH;AUDIT_SUCCESS_FLAG_MISMATCH | WARNING | price_quality audit records a failed refresh while parquet and store manifest show readable entity data. | Allow P2-C recheck using parquet-derived metadata; regenerate audit metadata before P3. |
| DIA | data/unified_ohlcv/us_stock_selection/audit/price_quality_audit.csv | 0 | False | data/unified_ohlcv/us_stock_selection/prices/DIA.parquet | True | True | 7115 | 1998-01-20 | 2026-05-01 | True | 7115 | data/unified_ohlcv/us_stock_selection/prices/DIA.parquet | False | False | STALE_AUDIT_METADATA;AUDIT_ROW_COUNT_MISMATCH;AUDIT_SUCCESS_FLAG_MISMATCH | WARNING | price_quality audit records a failed refresh while parquet and store manifest show readable entity data. | Allow P2-C recheck using parquet-derived metadata; regenerate audit metadata before P3. |
| GLD | data/unified_ohlcv/us_stock_selection/audit/price_quality_audit.csv | 0 | False | data/unified_ohlcv/us_stock_selection/prices/GLD.parquet | True | True | 5396 | 2004-11-18 | 2026-05-01 | True | 5396 | data/unified_ohlcv/us_stock_selection/prices/GLD.parquet | False | False | STALE_AUDIT_METADATA;AUDIT_ROW_COUNT_MISMATCH;AUDIT_SUCCESS_FLAG_MISMATCH | WARNING | price_quality audit records a failed refresh while parquet and store manifest show readable entity data. | Allow P2-C recheck using parquet-derived metadata; regenerate audit metadata before P3. |
| GOOGL | data/unified_ohlcv/us_stock_selection/audit/price_quality_audit.csv | 0 | False | data/unified_ohlcv/us_stock_selection/prices/GOOGL.parquet | True | True | 5460 | 2004-08-19 | 2026-05-01 | True | 5460 | data/unified_ohlcv/us_stock_selection/prices/GOOGL.parquet | False | False | STALE_AUDIT_METADATA;AUDIT_ROW_COUNT_MISMATCH;AUDIT_SUCCESS_FLAG_MISMATCH | WARNING | price_quality audit records a failed refresh while parquet and store manifest show readable entity data. | Allow P2-C recheck using parquet-derived metadata; regenerate audit metadata before P3. |
| IBB | data/unified_ohlcv/us_stock_selection/audit/price_quality_audit.csv | 0 | False | data/unified_ohlcv/us_stock_selection/prices/IBB.parquet | True | True | 6342 | 2001-02-12 | 2026-05-01 | True | 6342 | data/unified_ohlcv/us_stock_selection/prices/IBB.parquet | False | False | STALE_AUDIT_METADATA;AUDIT_ROW_COUNT_MISMATCH;AUDIT_SUCCESS_FLAG_MISMATCH | WARNING | price_quality audit records a failed refresh while parquet and store manifest show readable entity data. | Allow P2-C recheck using parquet-derived metadata; regenerate audit metadata before P3. |
| IGV | data/unified_ohlcv/us_stock_selection/audit/price_quality_audit.csv | 0 | False | data/unified_ohlcv/us_stock_selection/prices/IGV.parquet | True | True | 6235 | 2001-07-17 | 2026-05-01 | True | 6235 | data/unified_ohlcv/us_stock_selection/prices/IGV.parquet | False | False | STALE_AUDIT_METADATA;AUDIT_ROW_COUNT_MISMATCH;AUDIT_SUCCESS_FLAG_MISMATCH | WARNING | price_quality audit records a failed refresh while parquet and store manifest show readable entity data. | Allow P2-C recheck using parquet-derived metadata; regenerate audit metadata before P3. |
| INTC | data/unified_ohlcv/us_stock_selection/audit/price_quality_audit.csv | 0 | False | data/unified_ohlcv/us_stock_selection/prices/INTC.parquet | True | True | 11626 | 1980-03-17 | 2026-05-01 | True | 11626 | data/unified_ohlcv/us_stock_selection/prices/INTC.parquet | False | False | STALE_AUDIT_METADATA;AUDIT_ROW_COUNT_MISMATCH;AUDIT_SUCCESS_FLAG_MISMATCH | WARNING | price_quality audit records a failed refresh while parquet and store manifest show readable entity data. | Allow P2-C recheck using parquet-derived metadata; regenerate audit metadata before P3. |
| IWM | data/unified_ohlcv/us_stock_selection/audit/price_quality_audit.csv | 0 | False | data/unified_ohlcv/us_stock_selection/prices/IWM.parquet | True | True | 6521 | 2000-05-26 | 2026-05-01 | True | 6521 | data/unified_ohlcv/us_stock_selection/prices/IWM.parquet | False | False | STALE_AUDIT_METADATA;AUDIT_ROW_COUNT_MISMATCH;AUDIT_SUCCESS_FLAG_MISMATCH | WARNING | price_quality audit records a failed refresh while parquet and store manifest show readable entity data. | Allow P2-C recheck using parquet-derived metadata; regenerate audit metadata before P3. |
| LCID | data/unified_ohlcv/us_stock_selection/audit/price_quality_audit.csv | 0 | False | data/unified_ohlcv/us_stock_selection/prices/LCID.parquet | True | True | 1411 | 2020-09-18 | 2026-05-01 | True | 1411 | data/unified_ohlcv/us_stock_selection/prices/LCID.parquet | False | False | STALE_AUDIT_METADATA;AUDIT_ROW_COUNT_MISMATCH;AUDIT_SUCCESS_FLAG_MISMATCH | WARNING | price_quality audit records a failed refresh while parquet and store manifest show readable entity data. | Allow P2-C recheck using parquet-derived metadata; regenerate audit metadata before P3. |
| META | data/unified_ohlcv/us_stock_selection/audit/price_quality_audit.csv | 0 | False | data/unified_ohlcv/us_stock_selection/prices/META.parquet | True | True | 3508 | 2012-05-18 | 2026-05-01 | True | 3508 | data/unified_ohlcv/us_stock_selection/prices/META.parquet | False | False | STALE_AUDIT_METADATA;AUDIT_ROW_COUNT_MISMATCH;AUDIT_SUCCESS_FLAG_MISMATCH | WARNING | price_quality audit records a failed refresh while parquet and store manifest show readable entity data. | Allow P2-C recheck using parquet-derived metadata; regenerate audit metadata before P3. |

_Showing first 20 of 51 rows._

## Evidence Chain Impact

| impact_area | impact | rationale |
| --- | --- | --- |
| data_readability | NO_BLOCK | All price parquet files are readable with required fields. |
| ticker_universe_reproducibility | NO_BLOCK | Universe evidence is held in limited MVE2 eligible/excluded files, not in price_quality audit success flags. |
| eligible_excluded_reproducibility | NO_BLOCK | Eligible/excluded CSV files remain readable and are not changed by this task. |
| formal_mve2_data_source_uniqueness | NO_BLOCK | Only audited unified adjusted OHLCV store and limited MVE2 evidence were read. |
| p2a_readiness | EXPLAINS_CONDITIONAL | 51 metadata rows are attributable to stale audit metadata rather than unreadable parquet. |
| p2c_gate_recheck | ALLOW | P2-C can recheck using parquet-derived reconciliation evidence. |
| p3_search_design | BLOCK_UNTIL_P2C_PASS | P3 remains forbidden until P2-C gate recheck passes and human review accepts known exceptions. |

## Commit Metadata Timing

| scope | field_name | observed_value | pack_repository_commit | expected_value | explanation | severity | whether_blocks_p2c | whether_blocks_p3 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| limited_validation_pack | pack_generated_from_commit | 0ddd8bb8cc6772d6d6bb6fa098bd4795808fa7a9 | 2ac2b58cf2de378592c9ad18c2af08779d66391c | Generated-output commit may predate the repository commit that stores it. | This is a provenance timing difference, not a data-content mismatch. | INFO | False | False |
| p2a_gate | source_git_commit | b311cbba3ee2f205044b38402d5b90d83653bf10 | 2ac2b58cf2de378592c9ad18c2af08779d66391c | Generated-output commit may predate the repository commit that stores it. | This is a provenance timing difference, not a data-content mismatch. | INFO | False | False |
| p2b_exception_review | source_git_commit | 02e643593c92e7c0d55f28faa210a181f6454544 | 2ac2b58cf2de378592c9ad18c2af08779d66391c | Generated-output commit may predate the repository commit that stores it. | This is a provenance timing difference, not a data-content mismatch. | INFO | False | False |

## Decision Rationale

P2-C is allowed as a gate recheck because the conflict does not block data readability, ticker universe reproducibility, eligible/excluded reproducibility, or data source uniqueness. P3 remains blocked until P2-C passes and human review accepts the remaining known flags.
