# US Stock Selection v8.2 High-Beta Penalty Robustness Review

## 1. Background And Purpose

v8 baseline remains the current best. This review is a narrow, pre-registered robustness check around high-beta penalty candidates that showed diagnostic value in the previous v8.2 replay.

## 2. Why Only High-Beta Penalty

The previous bounded reranking replay found no accepted or strong candidate. The only rule with a clear weak-window signal was `high_beta_penalty_0p10`, so this review tests only nearby fixed lambdas.

## 3. Pre-Registered Candidates

Candidates: `baseline_original_rank, high_beta_penalty_0p05, high_beta_penalty_0p08, high_beta_penalty_0p10, high_beta_penalty_0p12, high_beta_penalty_0p15`. No grid search, no external data, no ensemble, no regime provider.

## 4. Score Direction Confirmation

```json
{
  "score_sort_ascending": false,
  "lower_score_is_better": false,
  "higher_score_is_better": true,
  "selected_equals_lowest_score_top5": false,
  "selected_equals_highest_score_top5": true,
  "max_score_diff_vs_baseline": 4.9823569991946925e-09,
  "rank_consistency_pass": true,
  "per_decision_rows": [
    {
      "decision_date": "2024-01-31",
      "selected_equals_highest_score_top5": true,
      "selected_equals_lowest_score_top5": false
    },
    {
      "decision_date": "2024-02-29",
      "selected_equals_highest_score_top5": true,
      "selected_equals_lowest_score_top5": false
    },
    {
      "decision_date": "2024-04-30",
      "selected_equals_highest_score_top5": true,
      "selected_equals_lowest_score_top5": false
    },
    {
      "decision_date": "2024-05-31",
      "selected_equals_highest_score_top5": true,
      "selected_equals_lowest_score_top5": false
    },
    {
      "decision_date": "2024-07-31",
      "selected_equals_highest_score_top5": true,
      "selected_equals_lowest_score_top5": false
    },
    {
      "decision_date": "2024-09-30",
      "selected_equals_highest_score_top5": true,
      "selected_equals_lowest_score_top5": false
    },
    {
      "decision_date": "2024-10-31",
      "selected_equals_highest_score_top5": true,
      "selected_equals_lowest_score_top5": false
    },
    {
      "decision_date": "2024-12-31",
      "selected_equals_highest_score_top5": true,
      "selected_equals_lowest_score_top5": false
    },
    {
      "decision_date": "2025-01-31",
      "selected_equals_highest_score_top5": true,
      "selected_equals_lowest_score_top5": false
    },
    {
      "decision_date": "2025-02-28",
      "selected_equals_highest_score_top5": true,
      "selected_equals_lowest_score_top5": false
    },
    {
      "decision_date": "2025-03-31",
      "selected_equals_highest_score_top5": true,
      "selected_equals_lowest_score_top5": false
    },
    {
      "decision_date": "2025-04-30",
      "selected_equals_highest_score_top5": true,
      "selected_equals_lowest_score_top5": false
    },
    {
      "decision_date": "2025-06-30",
      "selected_equals_highest_score_top5": true,
      "selected_equals_lowest_score_top5": false
    },
    {
      "decision_date": "2025-07-31",
      "selected_equals_highest_score_top5": true,
      "selected_equals_lowest_score_top5": false
    },
    {
      "decision_date": "2025-09-30",
      "selected_equals_highest_score_top5": true,
      "selected_equals_lowest_score_top5": false
    },
    {
      "decision_date": "2025-10-31",
      "selected_equals_highest_score_top5": true,
      "selected_equals_lowest_score_top5": false
    },
    {
      "decision_date": "2025-12-31",
      "selected_equals_highest_score_top5": true,
      "selected_equals_lowest_score_top5": false
    },
    {
      "decision_date": "2026-03-31",
      "selected_equals_highest_score_top5": true,
      "selected_equals_lowest_score_top5": false
    }
  ]
}
```

## 5. Forward Field Isolation

Only `raw_score` and `high_beta_flag` are used in ranking. No `audit_forward_*` field is used.

| rerank_candidate       | feature_name   | feature_type        | used_in_ranking   | allowed   | available   | reason                                |
|:-----------------------|:---------------|:--------------------|:------------------|:----------|:------------|:--------------------------------------|
| baseline_original_rank | raw_score      | ex-ante-model-score | True              | True      | True        | pre-registered high-beta review input |
| high_beta_penalty_0p05 | raw_score      | ex-ante-model-score | True              | True      | True        | pre-registered high-beta review input |
| high_beta_penalty_0p05 | high_beta_flag | ex-ante             | True              | True      | True        | pre-registered high-beta review input |
| high_beta_penalty_0p08 | raw_score      | ex-ante-model-score | True              | True      | True        | pre-registered high-beta review input |
| high_beta_penalty_0p08 | high_beta_flag | ex-ante             | True              | True      | True        | pre-registered high-beta review input |
| high_beta_penalty_0p10 | raw_score      | ex-ante-model-score | True              | True      | True        | pre-registered high-beta review input |
| high_beta_penalty_0p10 | high_beta_flag | ex-ante             | True              | True      | True        | pre-registered high-beta review input |
| high_beta_penalty_0p12 | raw_score      | ex-ante-model-score | True              | True      | True        | pre-registered high-beta review input |
| high_beta_penalty_0p12 | high_beta_flag | ex-ante             | True              | True      | True        | pre-registered high-beta review input |
| high_beta_penalty_0p15 | raw_score      | ex-ante-model-score | True              | True      | True        | pre-registered high-beta review input |
| high_beta_penalty_0p15 | high_beta_flag | ex-ante             | True              | True      | True        | pre-registered high-beta review input |

## 6. Full-Period Results

| rerank_candidate       |   lambda |     cagr |   cost50_cagr |   calmar |   cost50_calmar |   max_drawdown |   annual_turnover |   trade_count |   avg_high_beta_weight_share |   max_high_beta_weight_share |   selected_high_beta_count |   high_beta_selection_frequency | candidate_status                |
|:-----------------------|---------:|---------:|--------------:|---------:|----------------:|---------------:|------------------:|--------------:|-----------------------------:|-----------------------------:|---------------------------:|--------------------------------:|:--------------------------------|
| baseline_original_rank |     0    | 0.653818 |      0.560843 |  1.99153 |         1.59705 |      -0.3283   |           12.7096 |           145 |                    0.145848  |                          0.6 |                         13 |                       0.144444  | baseline_control                |
| high_beta_penalty_0p05 |     0.05 | 0.540441 |      0.451554 |  1.6882  |         1.31537 |      -0.320129 |           13.0602 |           149 |                    0.0714801 |                          0.2 |                          7 |                       0.0777778 | accepted_risk_control_candidate |
| high_beta_penalty_0p08 |     0.08 | 0.529158 |      0.442075 |  1.72709 |         1.34446 |      -0.306387 |           12.8849 |           147 |                    0.0444043 |                          0.2 |                          4 |                       0.0444444 | diagnostic_only                 |
| high_beta_penalty_0p10 |     0.1  | 0.529158 |      0.442075 |  1.72709 |         1.34446 |      -0.306387 |           12.8849 |           147 |                    0.0444043 |                          0.2 |                          4 |                       0.0444444 | diagnostic_only                 |
| high_beta_penalty_0p12 |     0.12 | 0.529158 |      0.442075 |  1.72709 |         1.34446 |      -0.306387 |           12.8849 |           147 |                    0.0444043 |                          0.2 |                          4 |                       0.0444444 | diagnostic_only                 |
| high_beta_penalty_0p15 |     0.15 | 0.491788 |      0.407996 |  1.77125 |         1.41622 |      -0.27765  |           12.7096 |           145 |                    0.0227437 |                          0.2 |                          2 |                       0.0222222 | rejected                        |

## 7. Weakest 12M Results

| rerank_candidate       |   lambda | weakest_12m_window   |   weakest_12m_CAGR |   weakest_12m_50bps_CAGR |   weakest_12m_MaxDD |   weakest_12m_Calmar |   weakest_12m_top1_positive_month_share |   weakest_12m_top3_positive_month_share |   weakest_12m_top5_positive_month_share |   weakest_12m_high_beta_weight_share |
|:-----------------------|---------:|:---------------------|-------------------:|-------------------------:|--------------------:|---------------------:|----------------------------------------:|----------------------------------------:|----------------------------------------:|-------------------------------------:|
| baseline_original_rank |     0    | 2024-04:2025-03      |           0.179788 |                 0.10803  |           -0.282641 |             0.636101 |                                0.455046 |                                0.802593 |                                0.97244  |                            0.165737  |
| high_beta_penalty_0p05 |     0.05 | 2024-04:2025-03      |           0.288863 |                 0.208314 |           -0.268256 |             1.07682  |                                0.460414 |                                0.800264 |                                0.972115 |                            0.0988048 |
| high_beta_penalty_0p08 |     0.08 | 2024-04:2025-03      |           0.281579 |                 0.201497 |           -0.244487 |             1.15171  |                                0.481261 |                                0.83851  |                                0.966539 |                            0.0653386 |
| high_beta_penalty_0p10 |     0.1  | 2024-04:2025-03      |           0.281579 |                 0.201497 |           -0.244487 |             1.15171  |                                0.481261 |                                0.83851  |                                0.966539 |                            0.0653386 |
| high_beta_penalty_0p12 |     0.12 | 2024-04:2025-03      |           0.281579 |                 0.201497 |           -0.244487 |             1.15171  |                                0.481261 |                                0.83851  |                                0.966539 |                            0.0653386 |
| high_beta_penalty_0p15 |     0.15 | 2024-04:2025-03      |           0.210961 |                 0.13744  |           -0.244487 |             0.862872 |                                0.344961 |                                0.797596 |                                0.957605 |                            0.0175299 |

## 8. Concentration / Stability Gate

| rerank_candidate       | gate_group            | gate_name                                 | pass_fail   | threshold            |   observed |
|:-----------------------|:----------------------|:------------------------------------------|:------------|:---------------------|-----------:|
| baseline_original_rank | baseline_control      | baseline_reproduction_control             | pass        |                      |  1         |
| high_beta_penalty_0p05 | accepted_risk_control | full_period_cagr_ge_20                    | pass        | 0.2                  |  0.540441  |
| high_beta_penalty_0p05 | accepted_risk_control | full_period_50bps_cagr_ge_04487           | pass        | 0.4487               |  0.451554  |
| high_beta_penalty_0p05 | accepted_risk_control | full_period_calmar_ge_15932               | pass        | 1.5932               |  1.6882    |
| high_beta_penalty_0p05 | accepted_risk_control | maxdd_better_than_v8                      | pass        | -0.32829998380969627 | -0.320129  |
| high_beta_penalty_0p05 | accepted_risk_control | leave_one_year_out_min_cagr_ge_20         | pass        | 0.2                  |  0.343693  |
| high_beta_penalty_0p05 | accepted_risk_control | leave_one_year_out_min_calmar_ge_1        | pass        | 1.0                  |  1.28121   |
| high_beta_penalty_0p05 | accepted_risk_control | top1_positive_month_share_lte_25          | pass        | 0.25                 |  0.186514  |
| high_beta_penalty_0p05 | accepted_risk_control | top3_positive_month_share_lte_50          | pass        | 0.5                  |  0.447073  |
| high_beta_penalty_0p05 | accepted_risk_control | max_ticker_abs_share_lte_30               | pass        | 0.3                  |  0.159463  |
| high_beta_penalty_0p05 | accepted_risk_control | max_ticker_month_weight_lte_30            | pass        | 0.3                  |  0.2       |
| high_beta_penalty_0p05 | accepted_risk_control | weakest_12m_calmar_ge_1                   | pass        | 1.0                  |  1.07682   |
| high_beta_penalty_0p05 | accepted_risk_control | weakest_12m_50bps_cagr_ge_20              | pass        | 0.2                  |  0.208314  |
| high_beta_penalty_0p05 | accepted_risk_control | weakest_12m_top3_share_lte_baseline       | pass        | 0.8025927915911051   |  0.800264  |
| high_beta_penalty_0p05 | accepted_risk_control | avg_high_beta_weight_share_20pct_below_v8 | pass        | 0.11667870036101083  |  0.0714801 |
| high_beta_penalty_0p05 | accepted_risk_control | no_future_function                        | pass        | True                 |  1         |
| high_beta_penalty_0p05 | accepted_risk_control | gross_exposure_normal                     | pass        | True                 |  1         |
| high_beta_penalty_0p05 | accepted_risk_control | accepted_risk_control_candidate           | pass        | all gates pass       |  1         |
| high_beta_penalty_0p05 | hard_reject           | baseline_reproduced                       | pass        | must pass            |  1         |
| high_beta_penalty_0p05 | hard_reject           | full_period_calmar_ge_1                   | pass        | must pass            |  1         |
| high_beta_penalty_0p05 | hard_reject           | full_period_50bps_cagr_ge_20              | pass        | must pass            |  1         |
| high_beta_penalty_0p05 | hard_reject           | loo_min_cagr_ge_20                        | pass        | must pass            |  1         |
| high_beta_penalty_0p05 | hard_reject           | loo_min_calmar_ge_1                       | pass        | must pass            |  1         |
| high_beta_penalty_0p05 | hard_reject           | gross_exposure_normal                     | pass        | must pass            |  1         |
| high_beta_penalty_0p05 | hard_reject           | not_extreme_top_month_dependency          | pass        | must pass            |  1         |
| high_beta_penalty_0p08 | accepted_risk_control | full_period_cagr_ge_20                    | pass        | 0.2                  |  0.529158  |
| high_beta_penalty_0p08 | accepted_risk_control | full_period_50bps_cagr_ge_04487           | fail        | 0.4487               |  0.442075  |
| high_beta_penalty_0p08 | accepted_risk_control | full_period_calmar_ge_15932               | pass        | 1.5932               |  1.72709   |
| high_beta_penalty_0p08 | accepted_risk_control | maxdd_better_than_v8                      | pass        | -0.32829998380969627 | -0.306387  |
| high_beta_penalty_0p08 | accepted_risk_control | leave_one_year_out_min_cagr_ge_20         | pass        | 0.2                  |  0.343443  |
| high_beta_penalty_0p08 | accepted_risk_control | leave_one_year_out_min_calmar_ge_1        | pass        | 1.0                  |  1.40475   |
| high_beta_penalty_0p08 | accepted_risk_control | top1_positive_month_share_lte_25          | pass        | 0.25                 |  0.188618  |
| high_beta_penalty_0p08 | accepted_risk_control | top3_positive_month_share_lte_50          | pass        | 0.5                  |  0.456941  |
| high_beta_penalty_0p08 | accepted_risk_control | max_ticker_abs_share_lte_30               | pass        | 0.3                  |  0.16937   |
| high_beta_penalty_0p08 | accepted_risk_control | max_ticker_month_weight_lte_30            | pass        | 0.3                  |  0.2       |
| high_beta_penalty_0p08 | accepted_risk_control | weakest_12m_calmar_ge_1                   | pass        | 1.0                  |  1.15171   |
| high_beta_penalty_0p08 | accepted_risk_control | weakest_12m_50bps_cagr_ge_20              | pass        | 0.2                  |  0.201497  |
| high_beta_penalty_0p08 | accepted_risk_control | weakest_12m_top3_share_lte_baseline       | fail        | 0.8025927915911051   |  0.83851   |
| high_beta_penalty_0p08 | accepted_risk_control | avg_high_beta_weight_share_20pct_below_v8 | pass        | 0.11667870036101083  |  0.0444043 |
| high_beta_penalty_0p08 | accepted_risk_control | no_future_function                        | pass        | True                 |  1         |
| high_beta_penalty_0p08 | accepted_risk_control | gross_exposure_normal                     | pass        | True                 |  1         |
| high_beta_penalty_0p08 | accepted_risk_control | accepted_risk_control_candidate           | fail        | all gates pass       |  0         |
| high_beta_penalty_0p08 | hard_reject           | baseline_reproduced                       | pass        | must pass            |  1         |
| high_beta_penalty_0p08 | hard_reject           | full_period_calmar_ge_1                   | pass        | must pass            |  1         |
| high_beta_penalty_0p08 | hard_reject           | full_period_50bps_cagr_ge_20              | pass        | must pass            |  1         |
| high_beta_penalty_0p08 | hard_reject           | loo_min_cagr_ge_20                        | pass        | must pass            |  1         |
| high_beta_penalty_0p08 | hard_reject           | loo_min_calmar_ge_1                       | pass        | must pass            |  1         |
| high_beta_penalty_0p08 | hard_reject           | gross_exposure_normal                     | pass        | must pass            |  1         |
| high_beta_penalty_0p08 | hard_reject           | not_extreme_top_month_dependency          | pass        | must pass            |  1         |
| high_beta_penalty_0p10 | accepted_risk_control | full_period_cagr_ge_20                    | pass        | 0.2                  |  0.529158  |
| high_beta_penalty_0p10 | accepted_risk_control | full_period_50bps_cagr_ge_04487           | fail        | 0.4487               |  0.442075  |
| high_beta_penalty_0p10 | accepted_risk_control | full_period_calmar_ge_15932               | pass        | 1.5932               |  1.72709   |
| high_beta_penalty_0p10 | accepted_risk_control | maxdd_better_than_v8                      | pass        | -0.32829998380969627 | -0.306387  |
| high_beta_penalty_0p10 | accepted_risk_control | leave_one_year_out_min_cagr_ge_20         | pass        | 0.2                  |  0.343443  |
| high_beta_penalty_0p10 | accepted_risk_control | leave_one_year_out_min_calmar_ge_1        | pass        | 1.0                  |  1.40475   |
| high_beta_penalty_0p10 | accepted_risk_control | top1_positive_month_share_lte_25          | pass        | 0.25                 |  0.188618  |
| high_beta_penalty_0p10 | accepted_risk_control | top3_positive_month_share_lte_50          | pass        | 0.5                  |  0.456941  |
| high_beta_penalty_0p10 | accepted_risk_control | max_ticker_abs_share_lte_30               | pass        | 0.3                  |  0.16937   |
| high_beta_penalty_0p10 | accepted_risk_control | max_ticker_month_weight_lte_30            | pass        | 0.3                  |  0.2       |
| high_beta_penalty_0p10 | accepted_risk_control | weakest_12m_calmar_ge_1                   | pass        | 1.0                  |  1.15171   |
| high_beta_penalty_0p10 | accepted_risk_control | weakest_12m_50bps_cagr_ge_20              | pass        | 0.2                  |  0.201497  |
| high_beta_penalty_0p10 | accepted_risk_control | weakest_12m_top3_share_lte_baseline       | fail        | 0.8025927915911051   |  0.83851   |
| high_beta_penalty_0p10 | accepted_risk_control | avg_high_beta_weight_share_20pct_below_v8 | pass        | 0.11667870036101083  |  0.0444043 |
| high_beta_penalty_0p10 | accepted_risk_control | no_future_function                        | pass        | True                 |  1         |
| high_beta_penalty_0p10 | accepted_risk_control | gross_exposure_normal                     | pass        | True                 |  1         |
| high_beta_penalty_0p10 | accepted_risk_control | accepted_risk_control_candidate           | fail        | all gates pass       |  0         |
| high_beta_penalty_0p10 | hard_reject           | baseline_reproduced                       | pass        | must pass            |  1         |
| high_beta_penalty_0p10 | hard_reject           | full_period_calmar_ge_1                   | pass        | must pass            |  1         |
| high_beta_penalty_0p10 | hard_reject           | full_period_50bps_cagr_ge_20              | pass        | must pass            |  1         |
| high_beta_penalty_0p10 | hard_reject           | loo_min_cagr_ge_20                        | pass        | must pass            |  1         |
| high_beta_penalty_0p10 | hard_reject           | loo_min_calmar_ge_1                       | pass        | must pass            |  1         |
| high_beta_penalty_0p10 | hard_reject           | gross_exposure_normal                     | pass        | must pass            |  1         |
| high_beta_penalty_0p10 | hard_reject           | not_extreme_top_month_dependency          | pass        | must pass            |  1         |
| high_beta_penalty_0p12 | accepted_risk_control | full_period_cagr_ge_20                    | pass        | 0.2                  |  0.529158  |
| high_beta_penalty_0p12 | accepted_risk_control | full_period_50bps_cagr_ge_04487           | fail        | 0.4487               |  0.442075  |
| high_beta_penalty_0p12 | accepted_risk_control | full_period_calmar_ge_15932               | pass        | 1.5932               |  1.72709   |
| high_beta_penalty_0p12 | accepted_risk_control | maxdd_better_than_v8                      | pass        | -0.32829998380969627 | -0.306387  |
| high_beta_penalty_0p12 | accepted_risk_control | leave_one_year_out_min_cagr_ge_20         | pass        | 0.2                  |  0.343443  |
| high_beta_penalty_0p12 | accepted_risk_control | leave_one_year_out_min_calmar_ge_1        | pass        | 1.0                  |  1.40475   |
| high_beta_penalty_0p12 | accepted_risk_control | top1_positive_month_share_lte_25          | pass        | 0.25                 |  0.188618  |
| high_beta_penalty_0p12 | accepted_risk_control | top3_positive_month_share_lte_50          | pass        | 0.5                  |  0.456941  |
| high_beta_penalty_0p12 | accepted_risk_control | max_ticker_abs_share_lte_30               | pass        | 0.3                  |  0.16937   |
| high_beta_penalty_0p12 | accepted_risk_control | max_ticker_month_weight_lte_30            | pass        | 0.3                  |  0.2       |
| high_beta_penalty_0p12 | accepted_risk_control | weakest_12m_calmar_ge_1                   | pass        | 1.0                  |  1.15171   |
| high_beta_penalty_0p12 | accepted_risk_control | weakest_12m_50bps_cagr_ge_20              | pass        | 0.2                  |  0.201497  |
| high_beta_penalty_0p12 | accepted_risk_control | weakest_12m_top3_share_lte_baseline       | fail        | 0.8025927915911051   |  0.83851   |
| high_beta_penalty_0p12 | accepted_risk_control | avg_high_beta_weight_share_20pct_below_v8 | pass        | 0.11667870036101083  |  0.0444043 |
| high_beta_penalty_0p12 | accepted_risk_control | no_future_function                        | pass        | True                 |  1         |
| high_beta_penalty_0p12 | accepted_risk_control | gross_exposure_normal                     | pass        | True                 |  1         |
| high_beta_penalty_0p12 | accepted_risk_control | accepted_risk_control_candidate           | fail        | all gates pass       |  0         |
| high_beta_penalty_0p12 | hard_reject           | baseline_reproduced                       | pass        | must pass            |  1         |
| high_beta_penalty_0p12 | hard_reject           | full_period_calmar_ge_1                   | pass        | must pass            |  1         |
| high_beta_penalty_0p12 | hard_reject           | full_period_50bps_cagr_ge_20              | pass        | must pass            |  1         |
| high_beta_penalty_0p12 | hard_reject           | loo_min_cagr_ge_20                        | pass        | must pass            |  1         |
| high_beta_penalty_0p12 | hard_reject           | loo_min_calmar_ge_1                       | pass        | must pass            |  1         |
| high_beta_penalty_0p12 | hard_reject           | gross_exposure_normal                     | pass        | must pass            |  1         |
| high_beta_penalty_0p12 | hard_reject           | not_extreme_top_month_dependency          | pass        | must pass            |  1         |
| high_beta_penalty_0p15 | accepted_risk_control | full_period_cagr_ge_20                    | pass        | 0.2                  |  0.491788  |
| high_beta_penalty_0p15 | accepted_risk_control | full_period_50bps_cagr_ge_04487           | fail        | 0.4487               |  0.407996  |
| high_beta_penalty_0p15 | accepted_risk_control | full_period_calmar_ge_15932               | pass        | 1.5932               |  1.77125   |
| high_beta_penalty_0p15 | accepted_risk_control | maxdd_better_than_v8                      | pass        | -0.32829998380969627 | -0.27765   |
| high_beta_penalty_0p15 | accepted_risk_control | leave_one_year_out_min_cagr_ge_20         | pass        | 0.2                  |  0.244411  |
| high_beta_penalty_0p15 | accepted_risk_control | leave_one_year_out_min_calmar_ge_1        | fail        | 1.0                  |  0.999687  |
| high_beta_penalty_0p15 | accepted_risk_control | top1_positive_month_share_lte_25          | pass        | 0.25                 |  0.198747  |
| high_beta_penalty_0p15 | accepted_risk_control | top3_positive_month_share_lte_50          | pass        | 0.5                  |  0.418419  |
| high_beta_penalty_0p15 | accepted_risk_control | max_ticker_abs_share_lte_30               | pass        | 0.3                  |  0.168829  |
| high_beta_penalty_0p15 | accepted_risk_control | max_ticker_month_weight_lte_30            | pass        | 0.3                  |  0.2       |
| high_beta_penalty_0p15 | accepted_risk_control | weakest_12m_calmar_ge_1                   | fail        | 1.0                  |  0.862872  |
| high_beta_penalty_0p15 | accepted_risk_control | weakest_12m_50bps_cagr_ge_20              | fail        | 0.2                  |  0.13744   |
| high_beta_penalty_0p15 | accepted_risk_control | weakest_12m_top3_share_lte_baseline       | pass        | 0.8025927915911051   |  0.797596  |
| high_beta_penalty_0p15 | accepted_risk_control | avg_high_beta_weight_share_20pct_below_v8 | pass        | 0.11667870036101083  |  0.0227437 |
| high_beta_penalty_0p15 | accepted_risk_control | no_future_function                        | pass        | True                 |  1         |
| high_beta_penalty_0p15 | accepted_risk_control | gross_exposure_normal                     | pass        | True                 |  1         |
| high_beta_penalty_0p15 | accepted_risk_control | accepted_risk_control_candidate           | fail        | all gates pass       |  0         |
| high_beta_penalty_0p15 | hard_reject           | baseline_reproduced                       | pass        | must pass            |  1         |
| high_beta_penalty_0p15 | hard_reject           | full_period_calmar_ge_1                   | pass        | must pass            |  1         |
| high_beta_penalty_0p15 | hard_reject           | full_period_50bps_cagr_ge_20              | pass        | must pass            |  1         |
| high_beta_penalty_0p15 | hard_reject           | loo_min_cagr_ge_20                        | pass        | must pass            |  1         |
| high_beta_penalty_0p15 | hard_reject           | loo_min_calmar_ge_1                       | fail        | must pass            |  0         |
| high_beta_penalty_0p15 | hard_reject           | gross_exposure_normal                     | pass        | must pass            |  1         |

## 9. Accepted Risk-Control Candidate

Accepted risk-control candidates: `high_beta_penalty_0p05`.

Diagnostic-only candidates: `high_beta_penalty_0p08, high_beta_penalty_0p10, high_beta_penalty_0p12`.

Closest candidate to accepted gate: `high_beta_penalty_0p05`.

## 10. Replace Baseline

`replace_v8_best` is `False`. v8 baseline remains current best unless the user explicitly approves a replacement.

## 11. v9

`allow_enter_v9` remains `False`.

## 12. Stop v8.2 Reranking Route

`stop_v8_2_reranking_route_recommended` is `False`. If no accepted risk-control candidate exists after this targeted review, the v8.2 reranking path should stop unless a new hypothesis is explicitly approved.

## 13. Required Questions

1. Risk-return monotonicity: cost50 CAGR values by lambda are `[0.4515543469348158, 0.44207545347574984, 0.44207545347574984, 0.44207545347574984, 0.40799582030030845]`; monotonic decreasing is `True`. Avg high-beta weight values are `[0.07148014440433213, 0.0444043321299639, 0.0444043321299639, 0.0444043321299639, 0.022743682310469318]`; monotonic decreasing is `True`.
2. High-beta exposure: see concentration table for MSTR/TQQQ/QLD/SOXL selected counts and weights.
3. Closest lambda: `high_beta_penalty_0p05`.
4. Why 0p10 improved weakest 12M: it reduced high-beta exposure during the weak window while keeping enough original score signal to preserve positive weak-window CAGR.
5. Why weakest 12M top3 share can worsen: drawdown improves, but positive weak-window gains remain concentrated in a few rebound months.
6. Recommended role: diagnostic conclusion or risk-control backup only, not formal baseline replacement.
7. Stop route: `False`.

## 14. Output

- Output directory: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\v8_2_high_beta_penalty_robustness_20260501_164800`
- Zip: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\us_stock_selection_quant_lab_v8_2_high_beta_penalty_robustness_20260501_164800.zip`
