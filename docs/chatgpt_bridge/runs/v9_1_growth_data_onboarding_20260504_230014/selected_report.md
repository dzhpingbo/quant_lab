# v9.1 Growth Data Onboarding Report

## Verdict

- classification: `v9_1_ready_for_formal_v9_rerun`
- new provider success: `True`
- Alpha360 cache success: `True`
- LGBModel score provenance success: `True`
- incremental data ready count: `28`
- incremental eligible growth count: `28`
- growth TopK candidate count: `23`
- Pool A reproduction aligned: `True`
- allow formal v9 rerun: `True`
- allow enter v10: `False`
- requires human review: `False`
- zip_path: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\us_stock_selection_v9_1_growth_data_onboarding_20260504_230014.zip`

## Required Answers

1. Which growth tickers have data?
   - Ready count: `28`. See `v9_1_data_inventory.csv`.
2. Which still miss data?
   - Missing/quality issue count: `1`. See `v9_1_data_inventory.csv`.
3. Which satisfy dynamic eligibility?
   - Eligible count: `28`. See `v9_1_eligibility_result.csv`.
4. Which are observation-only?
   - Rows with `eligible_for_formal_v9=False` in `v9_1_eligibility_result.csv`.
5. Did the new provider succeed?
   - `True`. Provider URI: `C:\Users\Administrator\.qlib\qlib_data\us_data_local_2026_v91_growth`.
6. Did Alpha360 cache succeed?
   - `True`. Rows: `96872`; features: `361`.
7. Did LGBModel score provenance succeed?
   - `True`. Score months: `18`; score rows: `1147`.
8. Does Pool A reproduction still align?
   - `True`. See `preflight_pool_a_reproduction_check.csv`.
9. Can new tickers enter TopK candidates?
   - Growth TopK candidate count: `23`. See `preflight_topk_candidate_overlap.csv`.
10. Is formal v9 rerun allowed?
    - `True`.
11. Is v10 allowed?
    - No.
12. Is human review required?
    - `False`.

## Provider Status

```json
{
  "provider_uri": "C:\\Users\\Administrator\\.qlib\\qlib_data\\us_data_local_2026_v91_growth",
  "provider_success": true,
  "added_tickers": [
    "ABNB",
    "AFRM",
    "AMAT",
    "APP",
    "ARM",
    "ASML",
    "COIN",
    "DASH",
    "DDOG",
    "FTNT",
    "KLAC",
    "LRCX",
    "MDB",
    "MPWR",
    "MRVL",
    "OKTA",
    "ON",
    "PATH",
    "PINS",
    "RBLX",
    "ROKU",
    "S",
    "SNAP",
    "SPOT",
    "TEAM",
    "TSM",
    "U",
    "ZS"
  ],
  "failed_tickers": [],
  "health": {
    "provider_uri": "C:\\Users\\Administrator\\.qlib\\qlib_data\\us_data_local_2026_v91_growth",
    "provider_exists": true,
    "provider_readable": true,
    "calendar_start": "2020-01-02",
    "calendar_end": "2026-04-17",
    "calendar_count": 1581,
    "instrument_count": 64,
    "pool_a_available_count": 64,
    "pool_a_missing": [
      "SQ"
    ],
    "missing_rate": 0.0,
    "covers_2022_to_2026": true,
    "sample_rows": 1000,
    "error": ""
  }
}
```

## Feature Cache Status

```json
{
  "row_count": 96872,
  "feature_count": 361,
  "instrument_count": 64,
  "date_min": "2020-01-02",
  "date_max": "2026-04-17",
  "missing_rate": 0.0,
  "generated_at": "2026-05-04T23:03:55.763825",
  "provider_uri": "C:\\Users\\Administrator\\.qlib\\qlib_data\\us_data_local_2026_v91_growth",
  "feature_set": "Alpha360",
  "cache_path": "E:\\dzhwork\\quant\\quant_lab\\outputs\\us_stock_selection\\v9_1_growth_data_onboarding_20260504_230014\\v9_1_feature_cache\\alpha360_feature_cache.parquet",
  "status": "completed"
}
```

## Score Provenance Status

```json
{
  "status": "completed",
  "provider_uri": "C:\\Users\\Administrator\\.qlib\\qlib_data\\us_data_local_2026_v91_growth",
  "feature_cache_dir": "E:\\dzhwork\\quant\\quant_lab\\outputs\\us_stock_selection\\v9_1_growth_data_onboarding_20260504_230014\\v9_1_feature_cache",
  "feature_set": "Alpha360",
  "model": "LGBModel",
  "label": "label_5d",
  "random_seed": 42,
  "decision_month_count": 18,
  "score_month_count": 18,
  "score_row_count": 1147,
  "growth_scored_count": 28,
  "growth_scored_tickers": [
    "ABNB",
    "AFRM",
    "AMAT",
    "APP",
    "ARM",
    "ASML",
    "COIN",
    "DASH",
    "DDOG",
    "FTNT",
    "KLAC",
    "LRCX",
    "MDB",
    "MPWR",
    "MRVL",
    "OKTA",
    "ON",
    "PATH",
    "PINS",
    "RBLX",
    "ROKU",
    "S",
    "SNAP",
    "SPOT",
    "TEAM",
    "TSM",
    "U",
    "ZS"
  ],
  "growth_top5_candidate_count": 23,
  "growth_top5_candidate_tickers": [
    "ABNB",
    "AFRM",
    "AMAT",
    "APP",
    "ARM",
    "ASML",
    "COIN",
    "DDOG",
    "FTNT",
    "KLAC",
    "LRCX",
    "MDB",
    "MPWR",
    "OKTA",
    "ON",
    "PATH",
    "PINS",
    "RBLX",
    "ROKU",
    "SNAP",
    "SPOT",
    "TEAM",
    "U"
  ],
  "fit_completed_count": 18,
  "fit_failed_count": 0
}
```

## Pool A Reproduction Check

| metric            |   formal_v82_baseline |   v91_provider_reproduction |         diff |   tolerance | pass_check   |
|:------------------|----------------------:|----------------------------:|-------------:|------------:|:-------------|
| cagr              |              0.642126 |                    0.642126 |  0           |       0.005 | True         |
| max_drawdown      |             -0.392985 |                   -0.392985 | -5.55112e-17 |       0.005 | True         |
| calmar            |              1.63397  |                    1.63397  |  0           |       0.03  | True         |
| single_year_share |              0.496839 |                    0.496839 |  0           |       0.02  | True         |
| top_ticker_share  |              0.137939 |                    0.137939 |  0           |       0.02  | True         |

## Data Ready Tickers

| ticker   | in_local_qlib_provider   | in_local_raw_ohlcv   | yfinance_download_needed   | yfinance_download_success   | date_start   | date_end   |   row_count |   missing_rate | adj_close_available   | volume_available   | data_quality_status   | listed_after_2020_train_start   | eligibility_status             | exclusion_reason   | source   | path                                                                                       |
|:---------|:-------------------------|:---------------------|:---------------------------|:----------------------------|:-------------|:-----------|------------:|---------------:|:----------------------|:-------------------|:----------------------|:--------------------------------|:-------------------------------|:-------------------|:---------|:-------------------------------------------------------------------------------------------|
| ABNB     | False                    | True                 | False                      | False                       | 2020-12-10   | 2026-04-02 |        1333 |              0 | True                  | True               | ready_for_provider    | True                            | eligible_after_dynamic_history |                    | local    | E:\dzhwork\quant\quant_lab\data\external\legacy_quant\NSDQStock\19800101_20260404\ABNB.csv |
| AFRM     | False                    | True                 | False                      | False                       | 2021-01-13   | 2026-04-02 |        1311 |              0 | True                  | True               | ready_for_provider    | True                            | eligible_after_dynamic_history |                    | local    | E:\dzhwork\quant\quant_lab\data\external\legacy_quant\NSDQStock\19800101_20260404\AFRM.csv |
| AMAT     | False                    | True                 | False                      | False                       | 1980-03-17   | 2026-04-02 |       11606 |              0 | True                  | True               | ready_for_provider    | False                           | eligible_after_dynamic_history |                    | local    | E:\dzhwork\quant\quant_lab\data\external\legacy_quant\NSDQStock\19800101_20260404\AMAT.csv |
| APP      | False                    | True                 | False                      | False                       | 2021-04-15   | 2026-04-02 |        1248 |              0 | True                  | True               | ready_for_provider    | True                            | eligible_after_dynamic_history |                    | local    | E:\dzhwork\quant\quant_lab\data\external\legacy_quant\NSDQStock\19800101_20260404\APP.csv  |
| ARM      | False                    | True                 | False                      | False                       | 2023-09-14   | 2026-04-02 |         640 |              0 | True                  | True               | ready_for_provider    | True                            | observation_until_min_history  |                    | local    | E:\dzhwork\quant\quant_lab\data\external\legacy_quant\NSDQStock\19800101_20260404\ARM.csv  |
| ASML     | False                    | True                 | False                      | False                       | 1995-03-15   | 2026-04-02 |        7815 |              0 | True                  | True               | ready_for_provider    | False                           | eligible_after_dynamic_history |                    | local    | E:\dzhwork\quant\quant_lab\data\external\legacy_quant\NSDQStock\19800101_20260404\ASML.csv |
| COIN     | False                    | True                 | False                      | False                       | 2021-04-14   | 2026-04-02 |        1249 |              0 | True                  | True               | ready_for_provider    | True                            | eligible_after_dynamic_history |                    | local    | E:\dzhwork\quant\quant_lab\data\external\legacy_quant\NSDQStock\19800101_20260404\COIN.csv |
| DASH     | False                    | True                 | False                      | False                       | 2020-12-09   | 2026-04-02 |        1334 |              0 | True                  | True               | ready_for_provider    | True                            | eligible_after_dynamic_history |                    | local    | E:\dzhwork\quant\quant_lab\data\external\legacy_quant\NSDQStock\19800101_20260404\DASH.csv |
| DDOG     | False                    | True                 | False                      | False                       | 2019-09-19   | 2026-04-02 |        1643 |              0 | True                  | True               | ready_for_provider    | False                           | eligible_after_dynamic_history |                    | local    | E:\dzhwork\quant\quant_lab\data\external\legacy_quant\NSDQStock\19800101_20260404\DDOG.csv |
| FTNT     | False                    | True                 | False                      | False                       | 2009-11-18   | 2026-04-02 |        4117 |              0 | True                  | True               | ready_for_provider    | False                           | eligible_after_dynamic_history |                    | local    | E:\dzhwork\quant\quant_lab\data\external\legacy_quant\NSDQStock\19800101_20260404\FTNT.csv |
| KLAC     | False                    | True                 | False                      | False                       | 1980-10-08   | 2026-04-02 |       11463 |              0 | True                  | True               | ready_for_provider    | False                           | eligible_after_dynamic_history |                    | local    | E:\dzhwork\quant\quant_lab\data\external\legacy_quant\NSDQStock\19800101_20260404\KLAC.csv |
| LRCX     | False                    | True                 | False                      | False                       | 1984-05-04   | 2026-04-02 |       10560 |              0 | True                  | True               | ready_for_provider    | False                           | eligible_after_dynamic_history |                    | local    | E:\dzhwork\quant\quant_lab\data\external\legacy_quant\NSDQStock\19800101_20260404\LRCX.csv |
| MDB      | False                    | True                 | False                      | False                       | 2017-10-19   | 2026-04-02 |        2124 |              0 | True                  | True               | ready_for_provider    | False                           | eligible_after_dynamic_history |                    | local    | E:\dzhwork\quant\quant_lab\data\external\legacy_quant\NSDQStock\19800101_20260404\MDB.csv  |
| MPWR     | False                    | True                 | False                      | False                       | 2004-11-19   | 2026-04-02 |        5375 |              0 | True                  | True               | ready_for_provider    | False                           | eligible_after_dynamic_history |                    | local    | E:\dzhwork\quant\quant_lab\data\external\legacy_quant\NSDQStock\19800101_20260404\MPWR.csv |
| MRVL     | False                    | True                 | False                      | False                       | 2000-06-30   | 2026-04-02 |        6477 |              0 | True                  | True               | ready_for_provider    | False                           | eligible_after_dynamic_history |                    | local    | E:\dzhwork\quant\quant_lab\data\external\legacy_quant\NSDQStock\19800101_20260404\MRVL.csv |
| OKTA     | False                    | True                 | False                      | False                       | 2017-04-07   | 2026-04-02 |        2259 |              0 | True                  | True               | ready_for_provider    | False                           | eligible_after_dynamic_history |                    | local    | E:\dzhwork\quant\quant_lab\data\external\legacy_quant\NSDQStock\19800101_20260404\OKTA.csv |
| ON       | False                    | True                 | False                      | False                       | 2000-05-02   | 2026-04-02 |        6519 |              0 | True                  | True               | ready_for_provider    | False                           | eligible_after_dynamic_history |                    | local    | E:\dzhwork\quant\quant_lab\data\external\legacy_quant\NSDQStock\19800101_20260404\ON.csv   |
| PATH     | False                    | True                 | False                      | False                       | 2021-04-21   | 2026-04-02 |        1244 |              0 | True                  | True               | ready_for_provider    | True                            | eligible_after_dynamic_history |                    | local    | E:\dzhwork\quant\quant_lab\data\external\legacy_quant\NSDQStock\19800101_20260404\PATH.csv |
| PINS     | False                    | True                 | False                      | False                       | 2019-04-18   | 2026-04-02 |        1749 |              0 | True                  | True               | ready_for_provider    | False                           | eligible_after_dynamic_history |                    | local    | E:\dzhwork\quant\quant_lab\data\external\legacy_quant\NSDQStock\19800101_20260404\PINS.csv |
| RBLX     | False                    | True                 | False                      | False                       | 2021-03-10   | 2026-04-02 |        1273 |              0 | True                  | True               | ready_for_provider    | True                            | eligible_after_dynamic_history |                    | local    | E:\dzhwork\quant\quant_lab\data\external\legacy_quant\NSDQStock\19800101_20260404\RBLX.csv |
| ROKU     | False                    | True                 | False                      | False                       | 2017-09-28   | 2026-04-02 |        2139 |              0 | True                  | True               | ready_for_provider    | False                           | eligible_after_dynamic_history |                    | local    | E:\dzhwork\quant\quant_lab\data\external\legacy_quant\NSDQStock\19800101_20260404\ROKU.csv |
| S        | False                    | True                 | False                      | False                       | 2021-06-30   | 2026-04-02 |        1195 |              0 | True                  | True               | ready_for_provider    | True                            | eligible_after_dynamic_history |                    | local    | E:\dzhwork\quant\quant_lab\data\external\legacy_quant\NSDQStock\19800101_20260404\S.csv    |
| SNAP     | False                    | True                 | False                      | False                       | 2017-03-02   | 2026-04-02 |        2285 |              0 | True                  | True               | ready_for_provider    | False                           | eligible_after_dynamic_history |                    | local    | E:\dzhwork\quant\quant_lab\data\external\legacy_quant\NSDQStock\19800101_20260404\SNAP.csv |
| SPOT     | False                    | True                 | False                      | False                       | 2018-04-03   | 2026-04-02 |        2012 |              0 | True                  | True               | ready_for_provider    | False                           | eligible_after_dynamic_history |                    | local    | E:\dzhwork\quant\quant_lab\data\external\legacy_quant\NSDQStock\19800101_20260404\SPOT.csv |
| TEAM     | False                    | True                 | False                      | False                       | 2015-12-09   | 2026-04-02 |        2593 |              0 | True                  | True               | ready_for_provider    | False                           | eligible_after_dynamic_history |                    | local    | E:\dzhwork\quant\quant_lab\data\external\legacy_quant\NSDQStock\19800101_20260404\TEAM.csv |
| TSM      | False                    | True                 | False                      | False                       | 1997-10-09   | 2026-04-02 |        7164 |              0 | True                  | True               | ready_for_provider    | False                           | eligible_after_dynamic_history |                    | local    | E:\dzhwork\quant\quant_lab\data\external\legacy_quant\NSDQStock\19800101_20260404\TSM.csv  |
| U        | False                    | True                 | False                      | False                       | 2020-09-18   | 2026-04-02 |        1391 |              0 | True                  | True               | ready_for_provider    | True                            | eligible_after_dynamic_history |                    | local    | E:\dzhwork\quant\quant_lab\data\external\legacy_quant\NSDQStock\19800101_20260404\U.csv    |
| ZS       | False                    | True                 | False                      | False                       | 2018-03-16   | 2026-04-02 |        2023 |              0 | True                  | True               | ready_for_provider    | False                           | eligible_after_dynamic_history |                    | local    | E:\dzhwork\quant\quant_lab\data\external\legacy_quant\NSDQStock\19800101_20260404\ZS.csv   |

## Eligibility

| ticker   | date_start   | date_end   | available_for_training   | available_for_prediction   |   min_history_days |   train_window_coverage |   prediction_window_coverage | eligible_for_formal_v9   | first_eligible_rebalance_date   |   eligible_month_count | eligibility_failure_reason   |
|:---------|:-------------|:-----------|:-------------------------|:---------------------------|-------------------:|------------------------:|-----------------------------:|:-------------------------|:--------------------------------|-----------------------:|:-----------------------------|
| ABNB     | 2020-12-10   | 2026-04-02 | True                     | True                       |                252 |                     768 |                          565 | True                     | 2024-01-31                      |                     27 |                              |
| AFRM     | 2021-01-13   | 2026-04-02 | True                     | True                       |                252 |                     746 |                          565 | True                     | 2024-01-31                      |                     27 |                              |
| AMAT     | 2020-01-02   | 2026-04-02 | True                     | True                       |                252 |                    1006 |                          565 | True                     | 2024-01-31                      |                     27 |                              |
| APP      | 2021-04-15   | 2026-04-02 | True                     | True                       |                252 |                     683 |                          565 | True                     | 2024-01-31                      |                     27 |                              |
| ARM      | 2023-09-14   | 2026-04-02 | False                    | True                       |                252 |                      75 |                          565 | True                     | 2024-09-30                      |                     19 |                              |
| ASML     | 2020-01-02   | 2026-04-02 | True                     | True                       |                252 |                    1006 |                          565 | True                     | 2024-01-31                      |                     27 |                              |
| COIN     | 2021-04-14   | 2026-04-02 | True                     | True                       |                252 |                     684 |                          565 | True                     | 2024-01-31                      |                     27 |                              |
| DASH     | 2020-12-09   | 2026-04-02 | True                     | True                       |                252 |                     769 |                          565 | True                     | 2024-01-31                      |                     27 |                              |
| DDOG     | 2020-01-02   | 2026-04-02 | True                     | True                       |                252 |                    1006 |                          565 | True                     | 2024-01-31                      |                     27 |                              |
| FTNT     | 2020-01-02   | 2026-04-02 | True                     | True                       |                252 |                    1006 |                          565 | True                     | 2024-01-31                      |                     27 |                              |
| KLAC     | 2020-01-02   | 2026-04-02 | True                     | True                       |                252 |                    1006 |                          565 | True                     | 2024-01-31                      |                     27 |                              |
| LRCX     | 2020-01-02   | 2026-04-02 | True                     | True                       |                252 |                    1006 |                          565 | True                     | 2024-01-31                      |                     27 |                              |
| MDB      | 2020-01-02   | 2026-04-02 | True                     | True                       |                252 |                    1006 |                          565 | True                     | 2024-01-31                      |                     27 |                              |
| MPWR     | 2020-01-02   | 2026-04-02 | True                     | True                       |                252 |                    1006 |                          565 | True                     | 2024-01-31                      |                     27 |                              |
| MRVL     | 2020-01-02   | 2026-04-02 | True                     | True                       |                252 |                    1006 |                          565 | True                     | 2024-01-31                      |                     27 |                              |
| OKTA     | 2020-01-02   | 2026-04-02 | True                     | True                       |                252 |                    1006 |                          565 | True                     | 2024-01-31                      |                     27 |                              |
| ON       | 2020-01-02   | 2026-04-02 | True                     | True                       |                252 |                    1006 |                          565 | True                     | 2024-01-31                      |                     27 |                              |
| PATH     | 2021-04-21   | 2026-04-02 | True                     | True                       |                252 |                     679 |                          565 | True                     | 2024-01-31                      |                     27 |                              |
| PINS     | 2020-01-02   | 2026-04-02 | True                     | True                       |                252 |                    1006 |                          565 | True                     | 2024-01-31                      |                     27 |                              |
| RBLX     | 2021-03-10   | 2026-04-02 | True                     | True                       |                252 |                     708 |                          565 | True                     | 2024-01-31                      |                     27 |                              |
| ROKU     | 2020-01-02   | 2026-04-02 | True                     | True                       |                252 |                    1006 |                          565 | True                     | 2024-01-31                      |                     27 |                              |
| S        | 2021-06-30   | 2026-04-02 | True                     | True                       |                252 |                     630 |                          565 | True                     | 2024-01-31                      |                     27 |                              |
| SNAP     | 2020-01-02   | 2026-04-02 | True                     | True                       |                252 |                    1006 |                          565 | True                     | 2024-01-31                      |                     27 |                              |
| SPOT     | 2020-01-02   | 2026-04-02 | True                     | True                       |                252 |                    1006 |                          565 | True                     | 2024-01-31                      |                     27 |                              |
| SQ       |              |            | False                    | False                      |                252 |                       0 |                            0 | False                    |                                 |                      0 | missing_provider_bin         |
| TEAM     | 2020-01-02   | 2026-04-02 | True                     | True                       |                252 |                    1006 |                          565 | True                     | 2024-01-31                      |                     27 |                              |
| TSM      | 2020-01-02   | 2026-04-02 | True                     | True                       |                252 |                    1006 |                          565 | True                     | 2024-01-31                      |                     27 |                              |
| U        | 2020-09-18   | 2026-04-02 | True                     | True                       |                252 |                     826 |                          565 | True                     | 2024-01-31                      |                     27 |                              |
| ZS       | 2020-01-02   | 2026-04-02 | True                     | True                       |                252 |                    1006 |                          565 | True                     | 2024-01-31                      |                     27 |                              |

## Candidate Coverage

| ticker   | data_quality_status   | date_start   | date_end   | eligible_for_formal_v9   | first_eligible_rebalance_date   |   eligible_month_count |   score_month_count |   score_row_count |   top5_candidate_count | entered_topk_candidate   | observation_only   |
|:---------|:----------------------|:-------------|:-----------|:-------------------------|:--------------------------------|-----------------------:|--------------------:|------------------:|-----------------------:|:-------------------------|:-------------------|
| ABNB     | ready_for_provider    | 2020-12-10   | 2026-04-02 | True                     | 2024-01-31                      |                     27 |                  18 |                18 |                      1 | True                     | False              |
| AFRM     | ready_for_provider    | 2021-01-13   | 2026-04-02 | True                     | 2024-01-31                      |                     27 |                  18 |                18 |                      5 | True                     | False              |
| AMAT     | ready_for_provider    | 1980-03-17   | 2026-04-02 | True                     | 2024-01-31                      |                     27 |                  18 |                18 |                      1 | True                     | False              |
| APP      | ready_for_provider    | 2021-04-15   | 2026-04-02 | True                     | 2024-01-31                      |                     27 |                  18 |                18 |                      4 | True                     | False              |
| ARM      | ready_for_provider    | 2023-09-14   | 2026-04-02 | True                     | 2024-09-30                      |                     19 |                  13 |                13 |                      3 | True                     | False              |
| ASML     | ready_for_provider    | 1995-03-15   | 2026-04-02 | True                     | 2024-01-31                      |                     27 |                  18 |                18 |                      1 | True                     | False              |
| COIN     | ready_for_provider    | 2021-04-14   | 2026-04-02 | True                     | 2024-01-31                      |                     27 |                  18 |                18 |                      3 | True                     | False              |
| DASH     | ready_for_provider    | 2020-12-09   | 2026-04-02 | True                     | 2024-01-31                      |                     27 |                  18 |                18 |                      0 | False                    | False              |
| DDOG     | ready_for_provider    | 2019-09-19   | 2026-04-02 | True                     | 2024-01-31                      |                     27 |                  18 |                18 |                      4 | True                     | False              |
| FTNT     | ready_for_provider    | 2009-11-18   | 2026-04-02 | True                     | 2024-01-31                      |                     27 |                  18 |                18 |                      1 | True                     | False              |
| KLAC     | ready_for_provider    | 1980-10-08   | 2026-04-02 | True                     | 2024-01-31                      |                     27 |                  18 |                18 |                      1 | True                     | False              |
| LRCX     | ready_for_provider    | 1984-05-04   | 2026-04-02 | True                     | 2024-01-31                      |                     27 |                  18 |                18 |                      1 | True                     | False              |
| MDB      | ready_for_provider    | 2017-10-19   | 2026-04-02 | True                     | 2024-01-31                      |                     27 |                  18 |                18 |                      2 | True                     | False              |
| MPWR     | ready_for_provider    | 2004-11-19   | 2026-04-02 | True                     | 2024-01-31                      |                     27 |                  18 |                18 |                      1 | True                     | False              |
| MRVL     | ready_for_provider    | 2000-06-30   | 2026-04-02 | True                     | 2024-01-31                      |                     27 |                  18 |                18 |                      0 | False                    | False              |
| OKTA     | ready_for_provider    | 2017-04-07   | 2026-04-02 | True                     | 2024-01-31                      |                     27 |                  18 |                18 |                      5 | True                     | False              |
| ON       | ready_for_provider    | 2000-05-02   | 2026-04-02 | True                     | 2024-01-31                      |                     27 |                  18 |                18 |                      2 | True                     | False              |
| PATH     | ready_for_provider    | 2021-04-21   | 2026-04-02 | True                     | 2024-01-31                      |                     27 |                  18 |                18 |                      2 | True                     | False              |
| PINS     | ready_for_provider    | 2019-04-18   | 2026-04-02 | True                     | 2024-01-31                      |                     27 |                  18 |                18 |                      2 | True                     | False              |
| RBLX     | ready_for_provider    | 2021-03-10   | 2026-04-02 | True                     | 2024-01-31                      |                     27 |                  18 |                18 |                      4 | True                     | False              |
| ROKU     | ready_for_provider    | 2017-09-28   | 2026-04-02 | True                     | 2024-01-31                      |                     27 |                  18 |                18 |                      1 | True                     | False              |
| S        | ready_for_provider    | 2021-06-30   | 2026-04-02 | True                     | 2024-01-31                      |                     27 |                  18 |                18 |                      0 | False                    | False              |
| SNAP     | ready_for_provider    | 2017-03-02   | 2026-04-02 | True                     | 2024-01-31                      |                     27 |                  18 |                18 |                      1 | True                     | False              |
| SPOT     | ready_for_provider    | 2018-04-03   | 2026-04-02 | True                     | 2024-01-31                      |                     27 |                  18 |                18 |                      1 | True                     | False              |
| SQ       | missing               |              |            | False                    |                                 |                      0 |                   0 |                 0 |                      0 | False                    | True               |
| TEAM     | ready_for_provider    | 2015-12-09   | 2026-04-02 | True                     | 2024-01-31                      |                     27 |                  18 |                18 |                      3 | True                     | False              |
| TSM      | ready_for_provider    | 1997-10-09   | 2026-04-02 | True                     | 2024-01-31                      |                     27 |                  18 |                18 |                      0 | False                    | False              |
| U        | ready_for_provider    | 2020-09-18   | 2026-04-02 | True                     | 2024-01-31                      |                     27 |                  18 |                18 |                      3 | True                     | False              |
| ZS       | ready_for_provider    | 2018-03-16   | 2026-04-02 | True                     | 2024-01-31                      |                     27 |                  18 |                18 |                      0 | False                    | False              |

## Score Availability By Month

| rebalance_date   |   total_score_count |   growth_score_count |   growth_top5_count |
|:-----------------|--------------------:|---------------------:|--------------------:|
| 2024-01-31       |                  63 |                   27 |                   2 |
| 2024-02-29       |                  63 |                   27 |                   4 |
| 2024-04-30       |                  63 |                   27 |                   2 |
| 2024-05-31       |                  63 |                   27 |                   4 |
| 2024-07-31       |                  63 |                   27 |                   1 |
| 2024-09-30       |                  64 |                   28 |                   3 |
| 2024-10-31       |                  64 |                   28 |                   3 |
| 2024-12-31       |                  64 |                   28 |                   4 |
| 2025-01-31       |                  64 |                   28 |                   3 |
| 2025-02-28       |                  64 |                   28 |                   3 |
| 2025-03-31       |                  64 |                   28 |                   3 |
| 2025-04-30       |                  64 |                   28 |                   3 |
| 2025-06-30       |                  64 |                   28 |                   4 |
| 2025-07-31       |                  64 |                   28 |                   1 |
| 2025-09-30       |                  64 |                   28 |                   3 |
| 2025-10-31       |                  64 |                   28 |                   2 |
| 2025-12-31       |                  64 |                   28 |                   3 |
| 2026-03-31       |                  64 |                   28 |                   4 |

## TopK Candidate Overlap

| rebalance_date   | top5_tickers             | growth_top5_tickers   |   growth_top5_count |
|:-----------------|:-------------------------|:----------------------|--------------------:|
| 2024-01-31       | AFRM,OKTA,PANW,TSLA,SHOP | AFRM,OKTA             |                   2 |
| 2024-02-29       | MSTR,AFRM,APP,COIN,TEAM  | AFRM,APP,COIN,TEAM    |                   4 |
| 2024-04-30       | TSLA,COIN,OKTA,SHOP,NET  | COIN,OKTA             |                   2 |
| 2024-05-31       | SHOP,PATH,U,PINS,AFRM    | PATH,U,PINS,AFRM      |                   4 |
| 2024-07-31       | ORCL,MU,MSTR,PLTR,SNAP   | SNAP                  |                   1 |
| 2024-09-30       | MSTR,APP,OKTA,INTC,RBLX  | APP,OKTA,RBLX         |                   3 |
| 2024-10-31       | ASML,MSTR,RBLX,AMZN,ROKU | ASML,RBLX,ROKU        |                   3 |
| 2024-12-31       | COIN,PLTR,APP,RBLX,MPWR  | COIN,APP,RBLX,MPWR    |                   4 |
| 2025-01-31       | TSLA,OKTA,ON,MDB,TQQQ    | OKTA,ON,MDB           |                   3 |
| 2025-02-28       | UBER,DDOG,ARM,AVGO,TEAM  | DDOG,ARM,TEAM         |                   3 |
| 2025-03-31       | PLTR,PINS,NET,APP,PATH   | PINS,APP,PATH         |                   3 |
| 2025-04-30       | U,NOW,MDB,AFRM,TSLA      | U,MDB,AFRM            |                   3 |
| 2025-06-30       | LRCX,ON,KLAC,SOXX,OKTA   | LRCX,ON,KLAC,OKTA     |                   4 |
| 2025-07-31       | PLTR,ABNB,CRWD,ORCL,NFLX | ABNB                  |                   1 |
| 2025-09-30       | RBLX,DDOG,AFRM,UPRO,AAPL | RBLX,DDOG,AFRM        |                   3 |
| 2025-10-31       | MU,ORCL,MSTR,FTNT,AMAT   | FTNT,AMAT             |                   2 |
| 2025-12-31       | DDOG,ARM,MSTR,U,CRM      | DDOG,ARM,U            |                   3 |
| 2026-03-31       | TEAM,DDOG,ARM,SNOW,SPOT  | TEAM,DDOG,ARM,SPOT    |                   4 |
