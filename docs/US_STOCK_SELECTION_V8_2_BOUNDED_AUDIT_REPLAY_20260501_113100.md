# US Stock Selection v8.2 Bounded Audit Replay

## 1. Background And Purpose

The prior v8.2 instrumentation proved that the original v8 baseline can only reconstruct selected-only scores from persisted artifacts. This run performs a bounded audit replay of the frozen v8 paper-trading prediction path to persist full decision_date x candidate score/rank rows.

## 2. Why The Old Run Cannot Recover Full Score/Rank

The old run saved selected_tickers, selected_scores, tradable_count, holdings, trades, and nav. It did not save the runtime pred/tradable/ranked snapshots or fitted monthly model artifacts, so unselected candidate scores cannot be recovered honestly from the old files alone.

## 3. What Bounded Audit Replay Means

Bounded audit replay means rerunning the original v8 scoring path with the same Alpha360 cache, ElasticNet parameters, liquidity filter, top5_equal_monthly selection, 20 percent weights, 1-day execution delay, and 5bps cost/slippage assumptions only to capture audit rows.

## 4. Strategy Logic Changed

No.

## 5. New Model Strategy Trained

No. The frozen v8 model class and parameters were refit only as part of reproducing the original audit replay path. No new model family, target, optimization, or strategy rule was introduced.

## 6. Sample Months Validation

Sample passed: `True`

| decision_date   |   candidate_count |   original_tradable_count |   selected_count |   unselected_count |   raw_score_non_null_rate |   raw_rank_non_null_rate |   adjusted_score_non_null_rate |   adjusted_rank_non_null_rate | selected_flag_consistent_with_holdings   | selected_count_matches_holdings   |   duplicate_key_count |   missing_ticker_count |   score_missing_count |   rank_missing_count | quality_pass   | warnings   | baseline_selection_reproduced   | tradable_count_matches_baseline   | candidate_count_gt_selected_count   | audit_forward_fields_used_in_selection   |
|:----------------|------------------:|--------------------------:|-----------------:|-------------------:|--------------------------:|-------------------------:|-------------------------------:|------------------------------:|:-----------------------------------------|:----------------------------------|----------------------:|-----------------------:|----------------------:|---------------------:|:---------------|:-----------|:--------------------------------|:----------------------------------|:------------------------------------|:-----------------------------------------|
| 2024-10-31      |                36 |                        36 |                5 |                 31 |                         1 |                        1 |                              1 |                             1 | True                                     | True                              |                     0 |                      0 |                     0 |                    0 | True           |            | True                            | True                              | True                                | False                                    |
| 2025-03-31      |                36 |                        36 |                5 |                 31 |                         1 |                        1 |                              1 |                             1 | True                                     | True                              |                     0 |                      0 |                     0 |                    0 | True           |            | True                            | True                              | True                                | False                                    |
| 2025-10-31      |                36 |                        36 |                5 |                 31 |                         1 |                        1 |                              1 |                             1 | True                                     | True                              |                     0 |                      0 |                     0 |                    0 | True           |            | True                            | True                              | True                                | False                                    |

## 7. Sample Baseline Selection Diff

| decision_date   | baseline_selected_tickers   | replay_selected_tickers   | selected_tickers_match   |   max_abs_score_diff | selected_scores_match   |   baseline_tradable_count |   replay_tradable_count | tradable_count_match   | is_match   | severity   |
|:----------------|:----------------------------|:--------------------------|:-------------------------|---------------------:|:------------------------|--------------------------:|------------------------:|:-----------------------|:-----------|:-----------|
| 2024-10-31      | MSTR,TSLA,PLTR,AMD,ORCL     | MSTR,TSLA,PLTR,AMD,ORCL   | True                     |                    0 | True                    |                        36 |                      36 | True                   | True       | none       |
| 2025-03-31      | NET,MSTR,TSLA,PLTR,SNOW     | NET,MSTR,TSLA,PLTR,SNOW   | True                     |                    0 | True                    |                        36 |                      36 | True                   | True       | none       |
| 2025-10-31      | ORCL,AVGO,PANW,ADBE,MU      | ORCL,AVGO,PANW,ADBE,MU    | True                     |                    0 | True                    |                        36 |                      36 | True                   | True       | none       |

## 8. Full Bounded Audit Replay Result

Full executed: `True`

| decision_date   |   candidate_count |   original_tradable_count |   selected_count |   unselected_count |   raw_score_non_null_rate |   raw_rank_non_null_rate |   adjusted_score_non_null_rate |   adjusted_rank_non_null_rate | selected_flag_consistent_with_holdings   | selected_count_matches_holdings   |   duplicate_key_count |   missing_ticker_count |   score_missing_count |   rank_missing_count | quality_pass   | warnings   | baseline_selection_reproduced   | tradable_count_matches_baseline   | candidate_count_gt_selected_count   | audit_forward_fields_used_in_selection   |
|:----------------|------------------:|--------------------------:|-----------------:|-------------------:|--------------------------:|-------------------------:|-------------------------------:|------------------------------:|:-----------------------------------------|:----------------------------------|----------------------:|-----------------------:|----------------------:|---------------------:|:---------------|:-----------|:--------------------------------|:----------------------------------|:------------------------------------|:-----------------------------------------|
| 2024-01-31      |                36 |                        36 |                5 |                 31 |                         1 |                        1 |                              1 |                             1 | True                                     | True                              |                     0 |                      0 |                     0 |                    0 | True           |            | True                            | True                              | True                                | False                                    |
| 2024-02-29      |                36 |                        36 |                5 |                 31 |                         1 |                        1 |                              1 |                             1 | True                                     | True                              |                     0 |                      0 |                     0 |                    0 | True           |            | True                            | True                              | True                                | False                                    |
| 2024-04-30      |                36 |                        36 |                5 |                 31 |                         1 |                        1 |                              1 |                             1 | True                                     | True                              |                     0 |                      0 |                     0 |                    0 | True           |            | True                            | True                              | True                                | False                                    |
| 2024-05-31      |                36 |                        36 |                5 |                 31 |                         1 |                        1 |                              1 |                             1 | True                                     | True                              |                     0 |                      0 |                     0 |                    0 | True           |            | True                            | True                              | True                                | False                                    |
| 2024-07-31      |                36 |                        36 |                5 |                 31 |                         1 |                        1 |                              1 |                             1 | True                                     | True                              |                     0 |                      0 |                     0 |                    0 | True           |            | True                            | True                              | True                                | False                                    |
| 2024-09-30      |                36 |                        36 |                5 |                 31 |                         1 |                        1 |                              1 |                             1 | True                                     | True                              |                     0 |                      0 |                     0 |                    0 | True           |            | True                            | True                              | True                                | False                                    |
| 2024-10-31      |                36 |                        36 |                5 |                 31 |                         1 |                        1 |                              1 |                             1 | True                                     | True                              |                     0 |                      0 |                     0 |                    0 | True           |            | True                            | True                              | True                                | False                                    |
| 2024-12-31      |                36 |                        36 |                5 |                 31 |                         1 |                        1 |                              1 |                             1 | True                                     | True                              |                     0 |                      0 |                     0 |                    0 | True           |            | True                            | True                              | True                                | False                                    |
| 2025-01-31      |                36 |                        36 |                5 |                 31 |                         1 |                        1 |                              1 |                             1 | True                                     | True                              |                     0 |                      0 |                     0 |                    0 | True           |            | True                            | True                              | True                                | False                                    |
| 2025-02-28      |                36 |                        36 |                5 |                 31 |                         1 |                        1 |                              1 |                             1 | True                                     | True                              |                     0 |                      0 |                     0 |                    0 | True           |            | True                            | True                              | True                                | False                                    |
| 2025-03-31      |                36 |                        36 |                5 |                 31 |                         1 |                        1 |                              1 |                             1 | True                                     | True                              |                     0 |                      0 |                     0 |                    0 | True           |            | True                            | True                              | True                                | False                                    |
| 2025-04-30      |                36 |                        36 |                5 |                 31 |                         1 |                        1 |                              1 |                             1 | True                                     | True                              |                     0 |                      0 |                     0 |                    0 | True           |            | True                            | True                              | True                                | False                                    |
| 2025-06-30      |                36 |                        36 |                5 |                 31 |                         1 |                        1 |                              1 |                             1 | True                                     | True                              |                     0 |                      0 |                     0 |                    0 | True           |            | True                            | True                              | True                                | False                                    |
| 2025-07-31      |                36 |                        36 |                5 |                 31 |                         1 |                        1 |                              1 |                             1 | True                                     | True                              |                     0 |                      0 |                     0 |                    0 | True           |            | True                            | True                              | True                                | False                                    |
| 2025-09-30      |                36 |                        36 |                5 |                 31 |                         1 |                        1 |                              1 |                             1 | True                                     | True                              |                     0 |                      0 |                     0 |                    0 | True           |            | True                            | True                              | True                                | False                                    |
| 2025-10-31      |                36 |                        36 |                5 |                 31 |                         1 |                        1 |                              1 |                             1 | True                                     | True                              |                     0 |                      0 |                     0 |                    0 | True           |            | True                            | True                              | True                                | False                                    |
| 2025-12-31      |                36 |                        36 |                5 |                 31 |                         1 |                        1 |                              1 |                             1 | True                                     | True                              |                     0 |                      0 |                     0 |                    0 | True           |            | True                            | True                              | True                                | False                                    |
| 2026-03-31      |                36 |                        36 |                5 |                 31 |                         1 |                        1 |                              1 |                             1 | True                                     | True                              |                     0 |                      0 |                     0 |                    0 | True           |            | True                            | True                              | True                                | False                                    |

## 9. Full Baseline Selection Diff

| decision_date   | baseline_selected_tickers   | replay_selected_tickers   | selected_tickers_match   |   max_abs_score_diff | selected_scores_match   |   baseline_tradable_count |   replay_tradable_count | tradable_count_match   | is_match   | severity   |
|:----------------|:----------------------------|:--------------------------|:-------------------------|---------------------:|:------------------------|--------------------------:|------------------------:|:-----------------------|:-----------|:-----------|
| 2024-01-31      | ORCL,MSTR,NFLX,AAPL,XLK     | ORCL,MSTR,NFLX,AAPL,XLK   | True                     |                    0 | True                    |                        36 |                      36 | True                   | True       | none       |
| 2024-02-29      | MSTR,NET,AVGO,UPRO,SSO      | MSTR,NET,AVGO,UPRO,SSO    | True                     |                    0 | True                    |                        36 |                      36 | True                   | True       | none       |
| 2024-04-30      | MSTR,INTC,AMD,CRWD,UPRO     | MSTR,INTC,AMD,CRWD,UPRO   | True                     |                    0 | True                    |                        36 |                      36 | True                   | True       | none       |
| 2024-05-31      | NET,CRWD,TQQQ,MU,CRM        | NET,CRWD,TQQQ,MU,CRM      | True                     |                    0 | True                    |                        36 |                      36 | True                   | True       | none       |
| 2024-07-31      | AMD,MSTR,MU,CRWD,SNOW       | AMD,MSTR,MU,CRWD,SNOW     | True                     |                    0 | True                    |                        36 |                      36 | True                   | True       | none       |
| 2024-09-30      | SHOP,NVDA,AVGO,NET,XLK      | SHOP,NVDA,AVGO,NET,XLK    | True                     |                    0 | True                    |                        36 |                      36 | True                   | True       | none       |
| 2024-10-31      | MSTR,TSLA,PLTR,AMD,ORCL     | MSTR,TSLA,PLTR,AMD,ORCL   | True                     |                    0 | True                    |                        36 |                      36 | True                   | True       | none       |
| 2024-12-31      | INTC,UPRO,SHOP,IWM,MU       | INTC,UPRO,SHOP,IWM,MU     | True                     |                    0 | True                    |                        36 |                      36 | True                   | True       | none       |
| 2025-01-31      | MSTR,SNOW,AAPL,SHOP,UBER    | MSTR,SNOW,AAPL,SHOP,UBER  | True                     |                    0 | True                    |                        36 |                      36 | True                   | True       | none       |
| 2025-02-28      | AVGO,NVDA,NOW,GOOGL,TQQQ    | AVGO,NVDA,NOW,GOOGL,TQQQ  | True                     |                    0 | True                    |                        36 |                      36 | True                   | True       | none       |
| 2025-03-31      | NET,MSTR,TSLA,PLTR,SNOW     | NET,MSTR,TSLA,PLTR,SNOW   | True                     |                    0 | True                    |                        36 |                      36 | True                   | True       | none       |
| 2025-04-30      | TQQQ,TSLA,UPRO,QLD,MSTR     | TQQQ,TSLA,UPRO,QLD,MSTR   | True                     |                    0 | True                    |                        36 |                      36 | True                   | True       | none       |
| 2025-06-30      | PLTR,UBER,NET,CRWD,GOOGL    | PLTR,UBER,NET,CRWD,GOOGL  | True                     |                    0 | True                    |                        36 |                      36 | True                   | True       | none       |
| 2025-07-31      | PANW,MU,ADBE,PLTR,CRM       | PANW,MU,ADBE,PLTR,CRM     | True                     |                    0 | True                    |                        36 |                      36 | True                   | True       | none       |
| 2025-09-30      | NET,AMD,SHOP,NOW,AVGO       | NET,AMD,SHOP,NOW,AVGO     | True                     |                    0 | True                    |                        36 |                      36 | True                   | True       | none       |
| 2025-10-31      | ORCL,AVGO,PANW,ADBE,MU      | ORCL,AVGO,PANW,ADBE,MU    | True                     |                    0 | True                    |                        36 |                      36 | True                   | True       | none       |
| 2025-12-31      | CRM,INTC,MU,SHOP,AMD        | CRM,INTC,MU,SHOP,AMD      | True                     |                    0 | True                    |                        36 |                      36 | True                   | True       | none       |
| 2026-03-31      | INTC,MU,AMD,MSTR,UBER       | INTC,MU,AMD,MSTR,UBER     | True                     |                    0 | True                    |                        36 |                      36 | True                   | True       | none       |

## 10. Full Candidate Audit Trail Generated

`True`

## 11. Reranking Readiness

```json
{
  "has_full_candidate_universe": true,
  "has_unselected_tickers": true,
  "has_raw_score": true,
  "has_raw_rank": true,
  "has_adjusted_score": true,
  "has_adjusted_rank": true,
  "has_selected_flag": true,
  "selected_flag_validated": true,
  "has_ex_ante_risk_features": true,
  "has_forward_audit_fields": true,
  "candidate_count_gt_selected_count_all_dates": true,
  "baseline_selection_reproduced": true,
  "can_run_gate_aware_reranking_replay": true,
  "blockers": [],
  "next_required_patch": "pause for user/ChatGPT approval before any bounded gate-aware reranking replay"
}
```

## 12. Remaining Gaps

Even if readiness is true, this run is not reranking replay and does not authorize v9. The next step requires user/ChatGPT approval before any gate-aware reranking replay.

## 13. Outputs

- Output directory: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\v8_2_bounded_audit_replay_20260501_113100`
- Zip: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\us_stock_selection_quant_lab_v8_2_bounded_audit_replay_20260501_113100.zip`
