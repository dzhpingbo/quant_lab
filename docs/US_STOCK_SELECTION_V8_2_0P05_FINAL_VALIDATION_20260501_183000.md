# US Stock Selection v8.2 0p05 Final Validation

## 1. Background And Purpose

This final validation pack only reviews `high_beta_penalty_0p05` versus `baseline_original_rank`. It does not search for new parameters or replace the v8 baseline.

## 2. Why Only 0p05

The prior targeted robustness review found `high_beta_penalty_0p05` as the only accepted risk-control candidate. This pack tests reproducibility, cost pressure, month concentration, weakest 12M behavior, and selection differences.

## 3. Code Logic And Forward Function Check

```json
{
  "score_direction_confirmed": true,
  "score_sort_ascending": false,
  "higher_score_is_better": true,
  "formula": "adjusted_score = raw_score - 0.05 * high_beta_flag",
  "candidate_universe_source": "v8.2 full score/rank audit trail decision_date x tradable_ticker",
  "selection_rule": "monthly top5 by adjusted_score descending",
  "weighting_rule": "v8 equal weight 20% per selected ticker",
  "ranking_fields": [
    "raw_score",
    "high_beta_flag"
  ],
  "high_beta_flag_definition": "True for tickers in the pre-existing high-beta proxy list.",
  "high_beta_tickers": [
    "MSTR",
    "QLD",
    "SOXL",
    "TQQQ"
  ],
  "audit_forward_columns_present": [
    "audit_forward_21d_return",
    "audit_forward_42d_return",
    "audit_forward_63d_return",
    "audit_forward_selected_period_return",
    "audit_forward_realized_vol",
    "audit_forward_maxdd"
  ],
  "audit_forward_fields_used_in_ranking": [],
  "uses_future_return_or_drawdown": false,
  "uses_future_top_month": false,
  "changes_model_training": false,
  "expands_universe": false,
  "runs_31b": false,
  "enters_v9": false,
  "logic_pass": true
}
```

## 4. Reproduction Result

| candidate              | check_type   | field                                     |   current_value |   prior_value |    abs_diff | pass   |
|:-----------------------|:-------------|:------------------------------------------|----------------:|--------------:|------------:|:-------|
| baseline_original_rank | metric       | cagr                                      |     0.653818    |     0.653818  | 0           | True   |
| baseline_original_rank | metric       | cost50_cagr                               |     0.560843    |     0.560843  | 0           | True   |
| baseline_original_rank | metric       | calmar                                    |     1.99153     |     1.99153   | 0           | True   |
| baseline_original_rank | metric       | max_drawdown                              |    -0.3283      |    -0.3283    | 5.55112e-17 | True   |
| baseline_original_rank | metric       | weakest_12m_Calmar                        |     0.636101    |     0.636101  | 0           | True   |
| baseline_original_rank | metric       | weakest_12m_50bps_CAGR                    |     0.10803     |     0.10803   | 1.38778e-17 | True   |
| baseline_original_rank | metric       | weakest_12m_top3_positive_month_share     |     0.802593    |     0.802593  | 0           | True   |
| baseline_original_rank | metric       | avg_high_beta_weight_share                |     0.145848    |     0.145848  | 2.77556e-17 | True   |
| baseline_original_rank | metric       | max_high_beta_weight_share                |     0.6         |     0.6       | 0           | True   |
| baseline_original_rank | metric       | selected_high_beta_count                  |    13           |    13         | 0           | True   |
| baseline_original_rank | nav          | max_abs_nav_diff                          |     4.44089e-16 |     0         | 4.44089e-16 | True   |
| baseline_original_rank | nav          | max_abs_cost50_nav_diff                   |     4.44089e-16 |     0         | 4.44089e-16 | True   |
| baseline_original_rank | selection    | symmetric_difference_decision_ticker_rank |     0           |     0         | 0           | True   |
| high_beta_penalty_0p05 | metric       | cagr                                      |     0.540441    |     0.540441  | 0           | True   |
| high_beta_penalty_0p05 | metric       | cost50_cagr                               |     0.451554    |     0.451554  | 0           | True   |
| high_beta_penalty_0p05 | metric       | calmar                                    |     1.6882      |     1.6882    | 0           | True   |
| high_beta_penalty_0p05 | metric       | max_drawdown                              |    -0.320129    |    -0.320129  | 5.55112e-17 | True   |
| high_beta_penalty_0p05 | metric       | weakest_12m_Calmar                        |     1.07682     |     1.07682   | 0           | True   |
| high_beta_penalty_0p05 | metric       | weakest_12m_50bps_CAGR                    |     0.208314    |     0.208314  | 2.77556e-17 | True   |
| high_beta_penalty_0p05 | metric       | weakest_12m_top3_positive_month_share     |     0.800264    |     0.800264  | 0           | True   |
| high_beta_penalty_0p05 | metric       | avg_high_beta_weight_share                |     0.0714801   |     0.0714801 | 2.77556e-17 | True   |
| high_beta_penalty_0p05 | metric       | max_high_beta_weight_share                |     0.2         |     0.2       | 0           | True   |
| high_beta_penalty_0p05 | metric       | selected_high_beta_count                  |     7           |     7         | 0           | True   |
| high_beta_penalty_0p05 | nav          | max_abs_nav_diff                          |     4.44089e-16 |     0         | 4.44089e-16 | True   |
| high_beta_penalty_0p05 | nav          | max_abs_cost50_nav_diff                   |     4.44089e-16 |     0         | 4.44089e-16 | True   |
| high_beta_penalty_0p05 | selection    | symmetric_difference_decision_ticker_rank |     0           |     0         | 0           | True   |

| rerank_candidate       |     cagr |   cost50_cagr |   calmar |   max_drawdown |   weakest_12m_Calmar |   weakest_12m_50bps_CAGR |   avg_high_beta_weight_share |   top5_positive_month_share |   remove_top5_month_cagr |
|:-----------------------|---------:|--------------:|---------:|---------------:|---------------------:|-------------------------:|-----------------------------:|----------------------------:|-------------------------:|
| baseline_original_rank | 0.653818 |      0.560843 |  1.99153 |      -0.3283   |             0.636101 |                 0.10803  |                    0.145848  |                    0.541001 |                0.139524  |
| high_beta_penalty_0p05 | 0.540441 |      0.451554 |  1.6882  |      -0.320129 |             1.07682  |                 0.208314 |                    0.0714801 |                    0.610805 |                0.0219566 |

## 5. Cost Stress

| candidate              |   cost_bps |   slippage_bps |     CAGR |     MaxDD |   Calmar |   cost_adjusted_CAGR |   cost_adjusted_Calmar |   annual_turnover |   trade_count | pass_cagr_20   | pass_calmar_1   | pass_50bps_threshold_equivalent   |
|:-----------------------|-----------:|---------------:|---------:|----------:|---------:|---------------------:|-----------------------:|------------------:|--------------:|:---------------|:----------------|:----------------------------------|
| baseline_original_rank |          0 |              5 | 0.664439 | -0.325722 | 2.0399   |             0.664439 |               2.0399   |           12.7096 |           145 | True           | True            | True                              |
| baseline_original_rank |         10 |              5 | 0.643256 | -0.330871 | 1.94413  |             0.643256 |               1.94413  |           12.7096 |           145 | True           | True            | True                              |
| baseline_original_rank |         25 |              5 | 0.61192  | -0.33854  | 1.80753  |             0.61192  |               1.80753  |           12.7096 |           145 | True           | True            | True                              |
| baseline_original_rank |         50 |              5 | 0.560843 | -0.351175 | 1.59705  |             0.560843 |               1.59705  |           12.7096 |           145 | True           | True            | True                              |
| baseline_original_rank |         75 |              5 | 0.511173 | -0.363629 | 1.40576  |             0.511173 |               1.40576  |           12.7096 |           145 | True           | True            | True                              |
| baseline_original_rank |        100 |              5 | 0.462877 | -0.375903 | 1.23138  |             0.462877 |               1.23138  |           12.7096 |           145 | True           | True            | True                              |
| high_beta_penalty_0p05 |          0 |              5 | 0.550603 | -0.317518 | 1.73408  |             0.550603 |               1.73408  |           13.0602 |           149 | True           | True            | True                              |
| high_beta_penalty_0p05 |         10 |              5 | 0.530338 | -0.322732 | 1.64327  |             0.530338 |               1.64327  |           13.0602 |           149 | True           | True            | True                              |
| high_beta_penalty_0p05 |         25 |              5 | 0.50037  | -0.330497 | 1.51399  |             0.50037  |               1.51399  |           13.0602 |           149 | True           | True            | True                              |
| high_beta_penalty_0p05 |         50 |              5 | 0.451554 | -0.34329  | 1.31537  |             0.451554 |               1.31537  |           13.0602 |           149 | True           | True            | True                              |
| high_beta_penalty_0p05 |         75 |              5 | 0.404121 | -0.355899 | 1.13549  |             0.404121 |               1.13549  |           13.0602 |           149 | True           | True            | False                             |
| high_beta_penalty_0p05 |        100 |              5 | 0.358036 | -0.368326 | 0.972063 |             0.358036 |               0.972063 |           13.0602 |           149 | True           | False           | False                             |

## 6. Monthly Returns And Concentration

| month   |   monthly_return_baseline |   monthly_return_p05 |   monthly_return_diff_p05_minus_baseline | p05_improved_month   | p05_worsened_month   |
|:--------|--------------------------:|---------------------:|-----------------------------------------:|:---------------------|:---------------------|
| 2024-01 |                 0         |          0           |                               0          | False                | False                |
| 2024-02 |                 0.168394  |          0.0053909   |                              -0.163003   | False                | True                 |
| 2024-03 |                 0.148005  |         -0.000187176 |                              -0.148192   | False                | True                 |
| 2024-04 |                -0.144402  |         -0.075327    |                               0.0690751  | True                 | False                |
| 2024-05 |                 0.149367  |          0.158556    |                               0.00918866 | True                 | False                |
| 2024-06 |                 0.154517  |          0.135103    |                              -0.0194138  | False                | True                 |
| 2024-07 |                -0.144599  |         -0.140333    |                               0.00426681 | True                 | False                |
| 2024-08 |                -0.0325222 |         -0.0314397   |                               0.00108251 | True                 | False                |
| 2024-09 |                 0.0973145 |          0.0973145   |                               0          | False                | False                |
| 2024-10 |                 0.0215163 |          0.0215163   |                               0          | False                | False                |
| 2024-11 |                 0.347773  |          0.347773    |                               0          | False                | False                |
| 2024-12 |                -0.0381881 |         -0.0381881   |                               0          | False                | False                |
| 2025-01 |                 0.0331642 |          0.0331642   |                               0          | False                | False                |
| 2025-02 |                -0.0411099 |         -0.0411099   |                               0          | False                | False                |
| 2025-03 |                -0.128318  |         -0.116615    |                               0.011703   | True                 | False                |
| 2025-04 |                 0.178816  |          0.177349    |                              -0.00146707 | False                | True                 |
| 2025-05 |                 0.157961  |          0.207463    |                               0.049502   | True                 | False                |
| 2025-06 |                 0.0924556 |          0.0819211   |                              -0.0105345  | False                | True                 |
| 2025-07 |                 0.0174601 |          0.0250395   |                               0.00757941 | True                 | False                |
| 2025-08 |                 0.0399702 |          0.0399702   |                               0          | False                | False                |
| 2025-09 |                 0.102933  |          0.102933    |                               0          | False                | False                |
| 2025-10 |                 0.218031  |          0.218031    |                               0          | False                | False                |
| 2025-11 |                -0.0668089 |         -0.0668089   |                               0          | False                | False                |
| 2025-12 |                 0.0178634 |          0.0178634   |                               0          | False                | False                |
| 2026-01 |                 0.0483816 |          0.0483816   |                               0          | False                | False                |
| 2026-02 |                -0.0599191 |         -0.0599191   |                               0          | False                | False                |
| 2026-03 |                -0.0458722 |         -0.0458722   |                               0          | False                | False                |
| 2026-04 |                 0.0525444 |          0.0525444   |                               0          | False                | False                |

| candidate              |   top1_positive_month_share |   top3_positive_month_share |   top5_positive_month_share | top1_months   | top3_months             | top5_months                             | top5_concentration_gt_60pct   |
|:-----------------------|----------------------------:|----------------------------:|----------------------------:|:--------------|:------------------------|:----------------------------------------|:------------------------------|
| baseline_original_rank |                    0.168601 |                    0.389378 |                    0.541001 | 2025-10       | 2025-10,2024-11,2025-05 | 2025-10,2024-11,2025-05,2025-04,2025-09 | False                         |
| high_beta_penalty_0p05 |                    0.186514 |                    0.447073 |                    0.610805 | 2025-10       | 2025-10,2024-11,2025-05 | 2025-10,2024-11,2025-05,2025-04,2025-09 | True                          |

| candidate              |   removed_top_positive_month_count | removed_months                          |      cagr |   max_drawdown |    calmar |
|:-----------------------|-----------------------------------:|:----------------------------------------|----------:|---------------:|----------:|
| baseline_original_rank |                                  1 | 2025-10                                 | 0.543428  |      -0.3283   | 1.65528   |
| baseline_original_rank |                                  3 | 2025-10,2024-11,2025-05                 | 0.283153  |      -0.358771 | 0.789229  |
| baseline_original_rank |                                  5 | 2025-10,2024-11,2025-05,2025-04,2025-09 | 0.139524  |      -0.282641 | 0.493645  |
| high_beta_penalty_0p05 |                                  1 | 2025-10                                 | 0.433371  |      -0.320129 | 1.35374   |
| high_beta_penalty_0p05 |                                  3 | 2025-10,2024-11,2025-05                 | 0.160399  |      -0.337956 | 0.474615  |
| high_beta_penalty_0p05 |                                  5 | 2025-10,2024-11,2025-05,2025-04,2025-09 | 0.0219566 |      -0.268256 | 0.0818494 |

## 7. Weakest 12M Deep Dive

| weakest_window_start   | weakest_window_end   | month   |   baseline_CAGR |   p05_CAGR |   baseline_50bps_CAGR |   p05_50bps_CAGR |   baseline_MaxDD |   p05_MaxDD |   baseline_Calmar |   p05_Calmar |   baseline_monthly_return |   p05_monthly_return |   return_diff_p05_minus_baseline |   baseline_top1_share |   p05_top1_share |   baseline_top3_share |   p05_top3_share |   baseline_top5_share |   p05_top5_share |   baseline_window_high_beta_weight_share |   p05_window_high_beta_weight_share | main_improved_months    | main_worsened_months    |   baseline_original_rank_month_high_beta_weight_share |   high_beta_penalty_0p05_month_high_beta_weight_share | baseline_selected_tickers   | p05_selected_tickers     | selected_ticker_differences   |   baseline_selected_high_beta_count |   p05_selected_high_beta_count |
|:-----------------------|:---------------------|:--------|----------------:|-----------:|----------------------:|-----------------:|-----------------:|------------:|------------------:|-------------:|--------------------------:|---------------------:|---------------------------------:|----------------------:|-----------------:|----------------------:|-----------------:|----------------------:|-----------------:|-----------------------------------------:|------------------------------------:|:------------------------|:------------------------|------------------------------------------------------:|------------------------------------------------------:|:----------------------------|:-------------------------|:------------------------------|------------------------------------:|-------------------------------:|
| 2024-04                | 2025-03              | 2024-04 |        0.179788 |   0.288863 |               0.10803 |         0.208314 |        -0.282641 |   -0.268256 |          0.636101 |      1.07682 |                -0.144402  |           -0.075327  |                       0.0690751  |              0.455046 |         0.460414 |              0.802593 |         0.800264 |               0.97244 |         0.972115 |                                 0.165737 |                           0.0988048 | 2024-04,2025-03,2024-05 | 2024-06,2024-09,2024-10 |                                                   0.2 |                                                   0   | MSTR,INTC,AMD,CRWD,UPRO     | MSTR,INTC,AMD,CRWD,UPRO  | removed=; added=              |                                   1 |                              1 |
| 2024-04                | 2025-03              | 2024-05 |        0.179788 |   0.288863 |               0.10803 |         0.208314 |        -0.282641 |   -0.268256 |          0.636101 |      1.07682 |                 0.149367  |            0.158556  |                       0.00918866 |              0.455046 |         0.460414 |              0.802593 |         0.800264 |               0.97244 |         0.972115 |                                 0.165737 |                           0.0988048 | 2024-04,2025-03,2024-05 | 2024-06,2024-09,2024-10 |                                                   0.2 |                                                   0.2 | NET,CRWD,TQQQ,MU,CRM        | NET,CRWD,MU,CRM,NVDA     | removed=TQQQ; added=NVDA      |                                   1 |                              0 |
| 2024-04                | 2025-03              | 2024-06 |        0.179788 |   0.288863 |               0.10803 |         0.208314 |        -0.282641 |   -0.268256 |          0.636101 |      1.07682 |                 0.154517  |            0.135103  |                      -0.0194138  |              0.455046 |         0.460414 |              0.802593 |         0.800264 |               0.97244 |         0.972115 |                                 0.165737 |                           0.0988048 | 2024-04,2025-03,2024-05 | 2024-06,2024-09,2024-10 |                                                   0.2 |                                                   0   | nan                         | nan                      | nan                           |                                 nan |                            nan |
| 2024-04                | 2025-03              | 2024-07 |        0.179788 |   0.288863 |               0.10803 |         0.208314 |        -0.282641 |   -0.268256 |          0.636101 |      1.07682 |                -0.144599  |           -0.140333  |                       0.00426681 |              0.455046 |         0.460414 |              0.802593 |         0.800264 |               0.97244 |         0.972115 |                                 0.165737 |                           0.0988048 | 2024-04,2025-03,2024-05 | 2024-06,2024-09,2024-10 |                                                   0.2 |                                                   0   | AMD,MSTR,MU,CRWD,SNOW       | AMD,MU,MSTR,CRWD,SNOW    | removed=; added=              |                                   1 |                              1 |
| 2024-04                | 2025-03              | 2024-08 |        0.179788 |   0.288863 |               0.10803 |         0.208314 |        -0.282641 |   -0.268256 |          0.636101 |      1.07682 |                -0.0325222 |           -0.0314397 |                       0.00108251 |              0.455046 |         0.460414 |              0.802593 |         0.800264 |               0.97244 |         0.972115 |                                 0.165737 |                           0.0988048 | 2024-04,2025-03,2024-05 | 2024-06,2024-09,2024-10 |                                                   0.2 |                                                   0.2 | nan                         | nan                      | nan                           |                                 nan |                            nan |
| 2024-04                | 2025-03              | 2024-09 |        0.179788 |   0.288863 |               0.10803 |         0.208314 |        -0.282641 |   -0.268256 |          0.636101 |      1.07682 |                 0.0973145 |            0.0973145 |                       0          |              0.455046 |         0.460414 |              0.802593 |         0.800264 |               0.97244 |         0.972115 |                                 0.165737 |                           0.0988048 | 2024-04,2025-03,2024-05 | 2024-06,2024-09,2024-10 |                                                   0.2 |                                                   0.2 | SHOP,NVDA,AVGO,NET,XLK      | SHOP,NVDA,AVGO,NET,XLK   | removed=; added=              |                                   0 |                              0 |
| 2024-04                | 2025-03              | 2024-10 |        0.179788 |   0.288863 |               0.10803 |         0.208314 |        -0.282641 |   -0.268256 |          0.636101 |      1.07682 |                 0.0215163 |            0.0215163 |                       0          |              0.455046 |         0.460414 |              0.802593 |         0.800264 |               0.97244 |         0.972115 |                                 0.165737 |                           0.0988048 | 2024-04,2025-03,2024-05 | 2024-06,2024-09,2024-10 |                                                   0   |                                                   0   | MSTR,TSLA,PLTR,AMD,ORCL     | MSTR,TSLA,PLTR,AMD,ORCL  | removed=; added=              |                                   1 |                              1 |
| 2024-04                | 2025-03              | 2024-11 |        0.179788 |   0.288863 |               0.10803 |         0.208314 |        -0.282641 |   -0.268256 |          0.636101 |      1.07682 |                 0.347773  |            0.347773  |                       0          |              0.455046 |         0.460414 |              0.802593 |         0.800264 |               0.97244 |         0.972115 |                                 0.165737 |                           0.0988048 | 2024-04,2025-03,2024-05 | 2024-06,2024-09,2024-10 |                                                   0.2 |                                                   0.2 | nan                         | nan                      | nan                           |                                 nan |                            nan |
| 2024-04                | 2025-03              | 2024-12 |        0.179788 |   0.288863 |               0.10803 |         0.208314 |        -0.282641 |   -0.268256 |          0.636101 |      1.07682 |                -0.0381881 |           -0.0381881 |                       0          |              0.455046 |         0.460414 |              0.802593 |         0.800264 |               0.97244 |         0.972115 |                                 0.165737 |                           0.0988048 | 2024-04,2025-03,2024-05 | 2024-06,2024-09,2024-10 |                                                   0.2 |                                                   0.2 | INTC,UPRO,SHOP,IWM,MU       | INTC,UPRO,SHOP,IWM,MU    | removed=; added=              |                                   0 |                              0 |
| 2024-04                | 2025-03              | 2025-01 |        0.179788 |   0.288863 |               0.10803 |         0.208314 |        -0.282641 |   -0.268256 |          0.636101 |      1.07682 |                 0.0331642 |            0.0331642 |                       0          |              0.455046 |         0.460414 |              0.802593 |         0.800264 |               0.97244 |         0.972115 |                                 0.165737 |                           0.0988048 | 2024-04,2025-03,2024-05 | 2024-06,2024-09,2024-10 |                                                   0   |                                                   0   | MSTR,SNOW,AAPL,SHOP,UBER    | SNOW,MSTR,AAPL,SHOP,UBER | removed=; added=              |                                   1 |                              1 |
| 2024-04                | 2025-03              | 2025-02 |        0.179788 |   0.288863 |               0.10803 |         0.208314 |        -0.282641 |   -0.268256 |          0.636101 |      1.07682 |                -0.0411099 |           -0.0411099 |                       0          |              0.455046 |         0.460414 |              0.802593 |         0.800264 |               0.97244 |         0.972115 |                                 0.165737 |                           0.0988048 | 2024-04,2025-03,2024-05 | 2024-06,2024-09,2024-10 |                                                   0.2 |                                                   0.2 | AVGO,NVDA,NOW,GOOGL,TQQQ    | AVGO,NVDA,NOW,GOOGL,META | removed=TQQQ; added=META      |                                   1 |                              0 |
| 2024-04                | 2025-03              | 2025-03 |        0.179788 |   0.288863 |               0.10803 |         0.208314 |        -0.282641 |   -0.268256 |          0.636101 |      1.07682 |                -0.128318  |           -0.116615  |                       0.011703   |              0.455046 |         0.460414 |              0.802593 |         0.800264 |               0.97244 |         0.972115 |                                 0.165737 |                           0.0988048 | 2024-04,2025-03,2024-05 | 2024-06,2024-09,2024-10 |                                                   0.2 |                                                   0   | NET,MSTR,TSLA,PLTR,SNOW     | NET,TSLA,PLTR,MSTR,SNOW  | removed=; added=              |                                   1 |                              1 |

## 8. Selection Difference Analysis

| decision_date   | baseline_selected_tickers   | p05_selected_tickers     | removed_tickers   | added_tickers   |   removed_high_beta_count |   added_high_beta_count |   return_impact_next_period_audit_only |   baseline_next_period_return_audit_only |   p05_next_period_return_audit_only |   high_beta_weight_baseline |   high_beta_weight_p05 |
|:----------------|:----------------------------|:-------------------------|:------------------|:----------------|--------------------------:|------------------------:|---------------------------------------:|-----------------------------------------:|------------------------------------:|----------------------------:|-----------------------:|
| 2024-01-31      | ORCL,MSTR,NFLX,AAPL,XLK     | ORCL,NFLX,AAPL,XLK,NOW   | MSTR              | NOW             |                         1 |                       0 |                            -0.163003   |                                0.168394  |                           0.0053909 |                         0.2 |                    0   |
| 2024-02-29      | MSTR,NET,AVGO,UPRO,SSO      | NET,AVGO,UPRO,SSO,PLTR   | MSTR              | PLTR            |                         1 |                       0 |                            -0.057731   |                               -0.0177691 |                          -0.0755001 |                         0.2 |                    0   |
| 2024-04-30      | MSTR,INTC,AMD,CRWD,UPRO     | MSTR,INTC,AMD,CRWD,UPRO  |                   |                 |                         0 |                       0 |                             0.00918866 |                                0.149367  |                           0.158556  |                         0.2 |                    0.2 |
| 2024-05-31      | NET,CRWD,TQQQ,MU,CRM        | NET,CRWD,MU,CRM,NVDA     | TQQQ              | NVDA            |                         1 |                       0 |                            -0.0117633  |                               -0.0124252 |                          -0.0241885 |                         0.2 |                    0   |
| 2024-07-31      | AMD,MSTR,MU,CRWD,SNOW       | AMD,MU,MSTR,CRWD,SNOW    |                   |                 |                         0 |                       0 |                             0.00118786 |                                0.0616274 |                           0.0628153 |                         0.2 |                    0.2 |
| 2024-09-30      | SHOP,NVDA,AVGO,NET,XLK      | SHOP,NVDA,AVGO,NET,XLK   |                   |                 |                         0 |                       0 |                             0          |                                0.0215163 |                           0.0215163 |                         0   |                    0   |
| 2024-10-31      | MSTR,TSLA,PLTR,AMD,ORCL     | MSTR,TSLA,PLTR,AMD,ORCL  |                   |                 |                         0 |                       0 |                             0          |                                0.296304  |                           0.296304  |                         0.2 |                    0.2 |
| 2024-12-31      | INTC,UPRO,SHOP,IWM,MU       | INTC,UPRO,SHOP,IWM,MU    |                   |                 |                         0 |                       0 |                             0          |                                0.0331642 |                           0.0331642 |                         0   |                    0   |
| 2025-01-31      | MSTR,SNOW,AAPL,SHOP,UBER    | SNOW,MSTR,AAPL,SHOP,UBER |                   |                 |                         0 |                       0 |                             0          |                               -0.0411099 |                          -0.0411099 |                         0.2 |                    0.2 |
| 2025-02-28      | AVGO,NVDA,NOW,GOOGL,TQQQ    | AVGO,NVDA,NOW,GOOGL,META | TQQQ              | META            |                         1 |                       0 |                             0.011703   |                               -0.128318  |                          -0.116615  |                         0.2 |                    0   |
| 2025-03-31      | NET,MSTR,TSLA,PLTR,SNOW     | NET,TSLA,PLTR,MSTR,SNOW  |                   |                 |                         0 |                       0 |                            -0.00146707 |                                0.178816  |                           0.177349  |                         0.2 |                    0.2 |
| 2025-04-30      | TQQQ,TSLA,UPRO,QLD,MSTR     | TSLA,TQQQ,UPRO,SHOP,SNOW | QLD,MSTR          | SHOP,SNOW       |                         2 |                       0 |                             0.0413587  |                                0.26502   |                           0.306379  |                         0.6 |                    0.2 |
| 2025-06-30      | PLTR,UBER,NET,CRWD,GOOGL    | PLTR,UBER,NET,CRWD,GOOGL |                   |                 |                         0 |                       0 |                             0.00757941 |                                0.0174601 |                           0.0250395 |                         0   |                    0   |
| 2025-07-31      | PANW,MU,ADBE,PLTR,CRM       | PANW,MU,ADBE,PLTR,CRM    |                   |                 |                         0 |                       0 |                             0          |                                0.147018  |                           0.147018  |                         0   |                    0   |
| 2025-09-30      | NET,AMD,SHOP,NOW,AVGO       | NET,AMD,SHOP,NOW,AVGO    |                   |                 |                         0 |                       0 |                             0          |                                0.218031  |                           0.218031  |                         0   |                    0   |
| 2025-10-31      | ORCL,AVGO,PANW,ADBE,MU      | ORCL,AVGO,PANW,ADBE,MU   |                   |                 |                         0 |                       0 |                             0          |                               -0.050139  |                          -0.050139  |                         0   |                    0   |
| 2025-12-31      | CRM,INTC,MU,SHOP,AMD        | CRM,INTC,MU,SHOP,AMD     |                   |                 |                         0 |                       0 |                             0          |                               -0.0596465 |                          -0.0596465 |                         0   |                    0   |
| 2026-03-31      | INTC,MU,AMD,MSTR,UBER       | INTC,MU,AMD,MSTR,UBER    |                   |                 |                         0 |                       0 |                             0          |                                0.0525444 |                           0.0525444 |                         0.2 |                    0.2 |

| metric                        |   baseline |       p05 |   delta_p05_minus_baseline |
|:------------------------------|-----------:|----------:|---------------------------:|
| avg_high_beta_weight_share    |  0.145848  | 0.0714801 |                 -0.0743682 |
| max_high_beta_weight_share    |  0.6       | 0.2       |                 -0.4       |
| selected_high_beta_count      | 13         | 7         |                 -6         |
| high_beta_selection_frequency |  0.144444  | 0.0777778 |                 -0.0666667 |
| MSTR_selected_count           |  9         | 6         |                 -3         |
| MSTR_selected_month_frequency |  0.5       | 0.333333  |                 -0.166667  |
| MSTR_avg_weight_active        |  0.0938628 | 0.0566787 |                 -0.0371841 |
| MSTR_max_weight               |  0.2       | 0.2       |                  0         |
| QLD_selected_count            |  1         | 0         |                 -1         |
| QLD_selected_month_frequency  |  0.0555556 | 0         |                 -0.0555556 |
| QLD_avg_weight_active         |  0.0148014 | 0         |                 -0.0148014 |
| QLD_max_weight                |  0.2       | 0         |                 -0.2       |
| SOXL_selected_count           |  0         | 0         |                  0         |
| SOXL_selected_month_frequency |  0         | 0         |                  0         |
| SOXL_avg_weight_active        |  0         | 0         |                  0         |
| SOXL_max_weight               |  0         | 0         |                  0         |
| TQQQ_selected_count           |  3         | 1         |                 -2         |
| TQQQ_selected_month_frequency |  0.166667  | 0.0555556 |                 -0.111111  |
| TQQQ_avg_weight_active        |  0.0371841 | 0.0148014 |                 -0.0223827 |
| TQQQ_max_weight               |  0.2       | 0.2       |                  0         |

## 9. Final Classification

Final classification: `risk_control_variant`.

`replace_v8_best` is `False`. `allow_enter_v9` is `False`.

## 10. Baseline Replacement

`high_beta_penalty_0p05` is not a baseline replacement candidate because full-period CAGR/Calmar are below v8 baseline and top5 positive month concentration remains high.

## 11. v9

Do not enter v9 from this pack.

## 12. Recommendation

Human review risk-control variant; do not replace v8 baseline automatically.

## 13. Output

- Output directory: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\v8_2_0p05_final_validation_20260501_183000`
- Zip: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\us_stock_selection_quant_lab_v8_2_0p05_final_validation_20260501_183000.zip`
