# ChatGPT Review Packet

## Run

- run_id: `v9_1_growth_data_onboarding_20260504_230014`
- run_dir: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014`
- zip_path: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\us_stock_selection_v9_1_growth_data_onboarding_20260504_230014.zip`
- published_at: `2026-05-04T23:08:10`

## 本轮目标

自动发布器未能从摘要中识别目标；请查看 RUN_SUMMARY / selected_report。

## 新增/修改文件

- `quant_lab/us_stock_selection/v9_1_growth_data_onboarding.py`
- `quant_lab/us_stock_selection/v9_1_reporting.py`
- `quant_lab/us_stock_selection/v9_1_score_provenance_builder.py`
- `scripts/us_stock_selection/40_run_v9_1_growth_data_onboarding.py`

## 核心结果 / RUN_SUMMARY

# RUN_SUMMARY

Stage: v9.1 small-growth canonical provider and frozen score provenance onboarding.

Run directory: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014`
Zip path: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\us_stock_selection_v9_1_growth_data_onboarding_20260504_230014.zip`

Conclusion:
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

Reason: Provider, Alpha360 cache, LGBModel scores, and Pool A reproduction passed; 28 incremental growth tickers are eligible and 23 entered TopK candidates.

No Nasdaq100/S&P500/full-market expansion, no v10, no trading, no broker/API/credential access, no automatic commit/push.


## 核心指标

|     cagr |   max_drawdown |   calmar |
|---------:|---------------:|---------:|
| 0.209633 |      -0.190599 | 1.09986  |
| 0.239292 |      -0.227683 | 1.05099  |
| 0.384244 |      -0.4229   | 0.908594 |
| 0.49246  |      -0.580401 | 0.848483 |

## Gate / Verdict

```json
{
  "classification": "v9_1_ready_for_formal_v9_rerun",
  "run_dir": "E:\\dzhwork\\quant\\quant_lab\\outputs\\us_stock_selection\\v9_1_growth_data_onboarding_20260504_230014",
  "provider_success": true,
  "feature_cache_success": true,
  "score_provenance_success": true,
  "incremental_data_ready_count": 28,
  "incremental_eligible_growth_count": 28,
  "growth_topk_candidate_count": 23,
  "pool_a_reproduction_aligned": true,
  "allow_formal_v9_rerun": true,
  "allow_enter_v10": false,
  "allow_trade_execution": false,
  "requires_human_review": false,
  "next_allowed_action": "Run formal v9 rerun with v9.1 provider only after human review.",
  "reason": "Provider, Alpha360 cache, LGBModel scores, and Pool A reproduction passed; 28 incremental growth tickers are eligible and 23 entered TopK candidates.",
  "zip_path": "E:\\dzhwork\\quant\\quant_lab\\outputs\\us_stock_selection\\us_stock_selection_v9_1_growth_data_onboarding_20260504_230014.zip"
}
```

## 当前分类

- classification: `v9_1_ready_for_formal_v9_rerun`
- allow_enter_v9: ``
- allow_enter_v10: `False`

## 不通过原因 / 已知限制

- verdict.reason: `Provider, Alpha360 cache, LGBModel scores, and Pool A reproduction passed; 28 incremental growth tickers are eligible and 23 entered TopK candidates.`
- "failed_tickers": [],
- "fit_failed_count": 0

## 需要 ChatGPT 审阅的问题

1. 当前 classification 是否与 gate 证据一致？
2. 是否存在未来函数、样本选择偏差、执行口径或数据质量问题？
3. 是否应批准进入下一阶段，还是要求补验证？
4. 如果进入下一阶段，边界条件是否足够明确？

## Codex 建议的下一步

# NEXT_STEPS

Current classification: `v9_1_ready_for_formal_v9_rerun`.

Allowed next action:
- `Run formal v9 rerun with v9.1 provider only after human review.`

Still forbidden:
- Do not enter v10.
- Do not expand Nasdaq100/S&P500/full market.
- Do not trade, connect brokers, place orders, or access credentials.
- Do not use observation-only tickers in formal TopK.


## 关键表格摘要

| csv                                                                                                                    |   size_mb | bridge_mode      |
|:-----------------------------------------------------------------------------------------------------------------------|----------:|:-----------------|
| outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\ABNB.csv       |     0.128 | copy_if_selected |
| outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\AFRM.csv       |     0.126 | copy_if_selected |
| outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\AMAT.csv       |     0.157 | copy_if_selected |
| outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\APP.csv        |     0.116 | copy_if_selected |
| outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\ARM.csv        |     0.06  | copy_if_selected |
| outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\ASML.csv       |     0.153 | copy_if_selected |
| outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\COIN.csv       |     0.118 | copy_if_selected |
| outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\DASH.csv       |     0.127 | copy_if_selected |
| outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\DDOG.csv       |     0.15  | copy_if_selected |
| outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\FTNT.csv       |     0.152 | copy_if_selected |
| outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\KLAC.csv       |     0.154 | copy_if_selected |
| outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\LRCX.csv       |     0.156 | copy_if_selected |
| outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\MDB.csv        |     0.145 | copy_if_selected |
| outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\MPWR.csv       |     0.153 | copy_if_selected |
| outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\MRVL.csv       |     0.155 | copy_if_selected |
| outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\OKTA.csv       |     0.148 | copy_if_selected |
| outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\ON.csv         |     0.148 | copy_if_selected |
| outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\PATH.csv       |     0.121 | copy_if_selected |
| outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\PINS.csv       |     0.152 | copy_if_selected |
| outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\RBLX.csv       |     0.122 | copy_if_selected |
| outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\ROKU.csv       |     0.149 | copy_if_selected |
| outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\S.csv          |     0.112 | copy_if_selected |
| outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\SNAP.csv       |     0.154 | copy_if_selected |
| outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\SPOT.csv       |     0.147 | copy_if_selected |
| outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\TEAM.csv       |     0.15  | copy_if_selected |
| outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\TSM.csv        |     0.155 | copy_if_selected |
| outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\U.csv          |     0.129 | copy_if_selected |
| outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\ZS.csv         |     0.146 | copy_if_selected |
| outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_feature_cache\alpha360_feature_quality.csv |     0.003 | copy_if_selected |
| outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_feature_cache\feature_cache_status.csv     |     0     | copy_if_selected |

## 重要 CSV 文件路径

- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\ABNB.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\AFRM.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\AMAT.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\APP.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\ARM.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\ASML.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\COIN.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\DASH.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\DDOG.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\FTNT.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\KLAC.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\LRCX.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\MDB.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\MPWR.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\MRVL.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\OKTA.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\ON.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\PATH.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\PINS.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\RBLX.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\ROKU.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\S.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\SNAP.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\SPOT.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\TEAM.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\TSM.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\U.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\prepared_csv\ZS.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_feature_cache\alpha360_feature_quality.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_feature_cache\feature_cache_status.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_preflight_replay\_pool_a_reproduction_internal\formal_v82_annual_returns.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_preflight_replay\_pool_a_reproduction_internal\formal_v82_benchmark_metrics.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_preflight_replay\_pool_a_reproduction_internal\formal_v82_daily_nav.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_preflight_replay\_pool_a_reproduction_internal\formal_v82_decision_ledger.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_preflight_replay\_pool_a_reproduction_internal\formal_v82_gate_detail.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_preflight_replay\_pool_a_reproduction_internal\formal_v82_metrics.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_preflight_replay\_pool_a_reproduction_internal\formal_v82_monthly_holdings.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_preflight_replay\_pool_a_reproduction_internal\formal_v82_monthly_returns.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_preflight_replay\_pool_a_reproduction_internal\formal_v82_score_rank_audit.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_preflight_replay\_pool_a_reproduction_internal\formal_v82_ticker_contribution.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_preflight_replay\_pool_a_reproduction_internal\formal_v82_trades.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_score_provenance\monthly_fit_log.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_score_provenance\monthly_score_rank_audit.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_preflight_replay\preflight_pool_a_plus_growth_candidate_coverage.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_preflight_replay\preflight_pool_a_reproduction_check.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_preflight_replay\preflight_score_availability_by_month.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_preflight_replay\preflight_topk_candidate_overlap.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\provider_instruments.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\provider_sample_prices.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_provider_build\qlib_data_sample.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_data_inventory.csv`
- `outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_eligibility_result.csv`

## selected_report.md excerpt

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
| MDB      | False                    | True                 | False                      | False                       | 2017-10-19   | 2026-04-02 |        2124 |              0 | True                  | True               | ready_for_provider    | False                           | eligible_after_dynamic_history |                    | local    | E:\dzhwork\quant\quant_lab\data\external\legacy_quant\NSDQSt

...[truncated for bridge packet]...
