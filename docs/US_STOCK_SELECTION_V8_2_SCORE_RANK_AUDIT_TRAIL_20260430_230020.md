# US Stock Selection v8.2 Score/Rank Audit Trail

## 1. Background And Purpose

v8.1 overlay evolution is stopped. This branch instruments the stock-selection layer so future diagnostics can inspect why each monthly candidate was selected or not selected.

## 2. Why Score/Rank Audit Is Required

The existing v8 baseline keeps selected tickers and selected scores only. Without `decision_date x tradable_ticker` score/rank rows, any reranking replay would be selected-only and biased.

## 3. v8 Selection Pipeline Location

| file_path                                                  | function_or_class                       | role                                                                                                                                                      | whether_generates_candidate_universe   | whether_generates_score   | whether_generates_rank   | whether_generates_selection   | whether_selected_only   | notes                                                                                                                                                |
|:-----------------------------------------------------------|:----------------------------------------|:----------------------------------------------------------------------------------------------------------------------------------------------------------|:---------------------------------------|:--------------------------|:-------------------------|:------------------------------|:------------------------|:-----------------------------------------------------------------------------------------------------------------------------------------------------|
| quant_lab/us_stock_selection/v8_paper_trading.py           | run_paper_trading_replay                | Frozen v8 monthly pseudo-live replay; orchestrates feature cache load, model fit, scoring, tradability filter, ranking, selection, holdings, trades, NAV. | True                                   | True                      | True                     | True                          | True                    | Full pred/tradable/ranked exists at runtime; original v8 persisted only selected tickers/scores. Patched to save full audit trail in future replays. |
| quant_lab/us_stock_selection/v8_paper_trading.py           | fit_model                               | Fits ElasticNet/Ridge/LGB fallback and returns the model used to predict one monthly snapshot.                                                            | False                                  | False                     | False                    | False                         | False                   | No fitted model artifact is persisted; old full scores cannot be regenerated without retraining.                                                     |
| quant_lab/us_stock_selection/v8_paper_trading.py           | tradable_universe                       | Filters prediction instruments by available close history and 20d average dollar volume.                                                                  | True                                   | False                     | False                    | False                         | False                   | Original v8 saves only tradable_count, not the tradable ticker list.                                                                                 |
| scripts/us_stock_selection/31_run_v8_paper_trading.py      | main                                    | Full v8 run entry point; calls run_paper_trading_replay then execution stress, attribution, reporting, zip.                                               | False                                  | False                     | False                    | False                         | False                   | Not used in this instrumentation run because it would retrain/replay.                                                                                |
| scripts/us_stock_selection/31a_run_v8_paper_replay_only.py | main                                    | Paper replay only entry point; can use patched run_paper_trading_replay in a future approved replay.                                                      | False                                  | False                     | False                    | False                         | False                   | Future bounded replay can produce full audit trail after user approval.                                                                              |
| quant_lab/us_stock_selection/v8_2_audit_trail.py           | build_score_rank_audit_for_decision     | New instrumentation builder for full runtime decision_date x candidate score/rank audit rows.                                                             | False                                  | False                     | True                     | False                         | False                   | Instrumentation only; does not affect selection.                                                                                                     |
| quant_lab/us_stock_selection/v8_2_audit_trail.py           | build_selected_only_audit_from_existing | Honest fallback for old v8 runs where only selected tickers/scores were saved.                                                                            | False                                  | False                     | False                    | False                         | True                    | Does not fabricate unselected rows; readiness must remain false.                                                                                     |

## 4. Audit Trail Schema

| field_name                           | field_group                | audit_only   | lookahead_allowed   | description                                                                   |
|:-------------------------------------|:---------------------------|:-------------|:--------------------|:------------------------------------------------------------------------------|
| run_id                               | key                        | False        | False               | Research run identifier or source run directory name.                         |
| decision_date                        | key                        | False        | False               | Date when the monthly selection decision is made.                             |
| rebalance_month                      | key                        | False        | False               | Decision month in YYYY-MM format.                                             |
| ticker                               | key                        | False        | False               | Candidate ticker.                                                             |
| asset_type                           | key                        | False        | False               | Best-effort stock/ETF tag.                                                    |
| universe_layer                       | key                        | False        | False               | Best-effort source layer for the candidate universe.                          |
| candidate_flag                       | ex_ante_selection          | False        | False               | True when the ticker exists in the prediction snapshot.                       |
| tradable_flag                        | ex_ante_selection          | False        | False               | True when the ticker passes v8 tradability filters.                           |
| exclusion_reason                     | ex_ante_selection          | False        | False               | Reason a candidate is excluded before ranking/selection.                      |
| raw_score                            | ex_ante_selection          | False        | False               | Raw model prediction score from the v8 scoring step.                          |
| adjusted_score                       | ex_ante_selection          | False        | False               | Score after ex-ante reranking penalties; equal to raw score for v8 baseline.  |
| raw_rank                             | ex_ante_selection          | False        | False               | Rank by raw score.                                                            |
| adjusted_rank                        | ex_ante_selection          | False        | False               | Rank after tradability/adjustment; v8 selection uses this ordering.           |
| selected_flag                        | ex_ante_selection          | False        | False               | True when the ticker is selected for the target holdings.                     |
| selected_rank                        | ex_ante_selection          | False        | False               | 1-based rank among selected tickers.                                          |
| target_weight_before_overlay         | ex_ante_selection          | False        | False               | Target weight from selection before any overlay.                              |
| target_weight_after_overlay          | ex_ante_selection          | False        | False               | Target weight after overlay; same as before overlay for v8 baseline.          |
| final_weight                         | ex_ante_selection          | False        | False               | Final target weight for the replay.                                           |
| selection_rule                       | ex_ante_selection          | False        | False               | Selection rule name.                                                          |
| model_name                           | ex_ante_selection          | False        | False               | Model used to produce score.                                                  |
| score_source                         | ex_ante_selection          | False        | False               | Score source artifact or runtime step.                                        |
| feature_snapshot_date                | ex_ante_selection          | False        | False               | Feature date used for scoring.                                                |
| trailing_20d_return                  | ex_ante_risk_concentration | False        | False               | Lagged risk/momentum feature computed using data no later than decision_date. |
| trailing_63d_return                  | ex_ante_risk_concentration | False        | False               | Lagged risk/momentum feature computed using data no later than decision_date. |
| trailing_126d_return                 | ex_ante_risk_concentration | False        | False               | Lagged risk/momentum feature computed using data no later than decision_date. |
| trailing_252d_return                 | ex_ante_risk_concentration | False        | False               | Lagged risk/momentum feature computed using data no later than decision_date. |
| trailing_20d_vol                     | ex_ante_risk_concentration | False        | False               | Lagged risk/momentum feature computed using data no later than decision_date. |
| trailing_63d_vol                     | ex_ante_risk_concentration | False        | False               | Lagged risk/momentum feature computed using data no later than decision_date. |
| trailing_126d_vol                    | ex_ante_risk_concentration | False        | False               | Lagged risk/momentum feature computed using data no later than decision_date. |
| trailing_63d_maxdd                   | ex_ante_risk_concentration | False        | False               | Lagged risk/momentum feature computed using data no later than decision_date. |
| distance_to_252d_high                | ex_ante_risk_concentration | False        | False               |                                                                               |
| high_beta_flag                       | ex_ante_risk_concentration | False        | False               | True for configured high-beta tickers.                                        |
| high_beta_group                      | ex_ante_risk_concentration | False        | False               | High-beta group label when available.                                         |
| previous_selected_count_12m          | ex_ante_risk_concentration | False        | False               | Lagged selection-history feature computed from prior decisions only.          |
| previous_avg_weight_12m              | ex_ante_risk_concentration | False        | False               | Lagged selection-history feature computed from prior decisions only.          |
| previous_concentration_penalty       | ex_ante_risk_concentration | False        | False               | Lagged selection-history feature computed from prior decisions only.          |
| audit_forward_21d_return             | forward_audit              | True         | True                | Audit-only forward outcome field. Must never enter score/rank/selection.      |
| audit_forward_42d_return             | forward_audit              | True         | True                | Audit-only forward outcome field. Must never enter score/rank/selection.      |
| audit_forward_63d_return             | forward_audit              | True         | True                | Audit-only forward outcome field. Must never enter score/rank/selection.      |
| audit_forward_selected_period_return | forward_audit              | True         | True                | Audit-only forward outcome field. Must never enter score/rank/selection.      |
| audit_forward_realized_vol           | forward_audit              | True         | True                | Audit-only forward outcome field. Must never enter score/rank/selection.      |
| audit_forward_maxdd                  | forward_audit              | True         | True                | Audit-only forward outcome field. Must never enter score/rank/selection.      |

## 5. Implementation

- Added `quant_lab/us_stock_selection/v8_2_audit_trail.py`.
- Patched `quant_lab/us_stock_selection/v8_paper_trading.py` so future replays can save full runtime candidate audit rows while `pred`, `tradable`, `ranked`, and `selected` still exist.
- Added `scripts/us_stock_selection/39_generate_v8_2_score_rank_audit_trail.py`.
- This run did not train a model and did not rerun v8 baseline.

## 6. Dry-Run Result

Dry-run validates argparse, run path, required inputs, output directory creation, and pipeline-map generation. The final run reused the same checks before selected-only reconstruction.

## 7. Sample-Month Validation

| decision_date   |   candidate_count |   original_tradable_count |   selected_count |   unselected_count |   raw_score_non_null_rate |   raw_rank_non_null_rate |   adjusted_score_non_null_rate |   adjusted_rank_non_null_rate | selected_flag_consistent_with_holdings   | selected_count_matches_holdings   |   duplicate_key_count |   missing_ticker_count |   score_missing_count |   rank_missing_count | quality_pass   | warnings                  |
|:----------------|------------------:|--------------------------:|-----------------:|-------------------:|--------------------------:|-------------------------:|-------------------------------:|------------------------------:|:-----------------------------------------|:----------------------------------|----------------------:|-----------------------:|----------------------:|---------------------:|:---------------|:--------------------------|
| 2025-03-31      |                 5 |                        36 |                5 |                  0 |                         1 |                        1 |                              1 |                             1 | True                                     | True                              |                     0 |                      0 |                     0 |                    0 | False          | selected-only audit trail |
| 2025-10-31      |                 5 |                        36 |                5 |                  0 |                         1 |                        1 |                              1 |                             1 | True                                     | True                              |                     0 |                      0 |                     0 |                    0 | False          | selected-only audit trail |

## 8. Data Quality Issues

| decision_date   | warning_type                 | severity   | message                                                                                     | missing_dependency                                        | required_upstream_patch                                                                      |
|:----------------|:-----------------------------|:-----------|:--------------------------------------------------------------------------------------------|:----------------------------------------------------------|:---------------------------------------------------------------------------------------------|
| 2025-03-31      | selected_only_reconstruction | high       | original v8 ledger reports tradable_count=36, but only 5 selected rows can be reconstructed | full runtime pred/ranked candidate snapshot was not saved | save v8_2_score_rank_audit_trail.csv inside run_paper_trading_replay when pred/ranked exists |
| 2025-10-31      | selected_only_reconstruction | high       | original v8 ledger reports tradable_count=36, but only 5 selected rows can be reconstructed | full runtime pred/ranked candidate snapshot was not saved | save v8_2_score_rank_audit_trail.csv inside run_paper_trading_replay when pred/ranked exists |
| 2025-03-31      | selected_only_quality_fail   | high       | candidate_count is not greater than selected_count; full unselected candidates are missing  | nan                                                       | nan                                                                                          |
| 2025-10-31      | selected_only_quality_fail   | high       | candidate_count is not greater than selected_count; full unselected candidates are missing  | nan                                                       | nan                                                                                          |

## 9. Reranking Readiness

```json
{
  "has_full_candidate_universe": false,
  "has_unselected_tickers": false,
  "has_raw_score": false,
  "has_raw_rank": false,
  "has_adjusted_score": false,
  "has_adjusted_rank": false,
  "has_selected_flag": true,
  "selected_flag_validated": true,
  "has_ex_ante_risk_features": true,
  "has_forward_audit_fields": true,
  "has_selected_only_raw_score": true,
  "can_run_gate_aware_reranking_replay": false,
  "blockers": [
    "full candidate universe rows are missing; audit remains selected-only",
    "unselected tickers are absent",
    "full candidate raw/adjusted scores are missing"
  ],
  "next_required_patch": "continue upstream logging: persist full pred/tradable/ranked snapshot from run_paper_trading_replay without retraining current v8 baseline"
}
```

## 10. Missing Items If Not Ready

The existing v8 run is selected-only. Full candidate score/rank rows require an upstream replay with the new instrumentation hook enabled.

## 11. Next Step

Do not run reranking yet. Continue upstream logging by producing a full `v8_2_score_rank_audit_trail.csv` from an approved bounded replay, then reassess readiness.

## Outputs

- Output directory: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\v8_2_score_rank_audit_trail_20260430_230020`
- Zip: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\us_stock_selection_quant_lab_v8_2_score_rank_audit_trail_20260430_230020.zip`
