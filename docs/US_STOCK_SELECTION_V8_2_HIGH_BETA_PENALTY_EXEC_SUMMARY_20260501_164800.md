# v8.2 High-Beta Penalty Robustness Exec Summary

- Completed: `True`
- Accepted risk-control candidates: `high_beta_penalty_0p05`
- Diagnostic-only candidates: `high_beta_penalty_0p08, high_beta_penalty_0p10, high_beta_penalty_0p12`
- Closest candidate to accepted gate: `high_beta_penalty_0p05`
- Replace v8 best: `False`
- Allow enter v9: `False`
- Stop v8.2 reranking route recommended: `False`

## Metrics

| rerank_candidate       |   lambda |     cagr |   cost50_cagr |   calmar |   max_drawdown |   weakest_12m_Calmar |   weakest_12m_50bps_CAGR |   avg_high_beta_weight_share | candidate_status                |
|:-----------------------|---------:|---------:|--------------:|---------:|---------------:|---------------------:|-------------------------:|-----------------------------:|:--------------------------------|
| baseline_original_rank |     0    | 0.653818 |      0.560843 |  1.99153 |      -0.3283   |             0.636101 |                 0.10803  |                    0.145848  | baseline_control                |
| high_beta_penalty_0p05 |     0.05 | 0.540441 |      0.451554 |  1.6882  |      -0.320129 |             1.07682  |                 0.208314 |                    0.0714801 | accepted_risk_control_candidate |
| high_beta_penalty_0p08 |     0.08 | 0.529158 |      0.442075 |  1.72709 |      -0.306387 |             1.15171  |                 0.201497 |                    0.0444043 | diagnostic_only                 |
| high_beta_penalty_0p10 |     0.1  | 0.529158 |      0.442075 |  1.72709 |      -0.306387 |             1.15171  |                 0.201497 |                    0.0444043 | diagnostic_only                 |
| high_beta_penalty_0p12 |     0.12 | 0.529158 |      0.442075 |  1.72709 |      -0.306387 |             1.15171  |                 0.201497 |                    0.0444043 | diagnostic_only                 |
| high_beta_penalty_0p15 |     0.15 | 0.491788 |      0.407996 |  1.77125 |      -0.27765  |             0.862872 |                 0.13744  |                    0.0227437 | rejected                        |
