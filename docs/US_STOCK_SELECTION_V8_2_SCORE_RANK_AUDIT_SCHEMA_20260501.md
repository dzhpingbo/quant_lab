# US Stock Selection v8.2 Score/Rank Audit Schema 20260501

This schema separates ex-ante selection fields from audit-only forward outcome fields. Any column with the `audit_forward_` prefix is strictly audit-only and must never be used to compute score, rank, selected_flag, or target weight.

## Field Schema

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
