# US Stock Selection v8.2 Reranking Exec Summary

- Sample completed: `True`
- Sample passed: `True`
- Full completed: `True`
- Accepted candidates: `None`
- Strong candidates: `None`
- Replace v8 best: `False`
- Allow enter v9: `False`

## Top Metrics

| rerank_candidate                      |     cagr |   cost50_cagr |   calmar |   max_drawdown |   top3_positive_month_share |   max_ticker_abs_share | candidate_status            |
|:--------------------------------------|---------:|--------------:|---------:|---------------:|----------------------------:|-----------------------:|:----------------------------|
| baseline_original_rank                | 0.653818 |     0.560843  | 1.99153  |      -0.3283   |                    0.389378 |              0.223603  | baseline_control            |
| concentration_memory_penalty          | 0.401066 |     0.333187  | 1.68561  |      -0.237936 |                    0.434008 |              0.129796  | diagnostic_only_or_rejected |
| high_beta_penalty_0p10                | 0.529158 |     0.442075  | 1.72709  |      -0.306387 |                    0.456941 |              0.16937   | diagnostic_only_or_rejected |
| high_beta_penalty_0p20                | 0.491788 |     0.407996  | 1.77125  |      -0.27765  |                    0.418419 |              0.168829  | diagnostic_only_or_rejected |
| risk_adjusted_score_vol63_lambda_0p10 | 0.196748 |     0.149629  | 1.14324  |      -0.172097 |                    0.472765 |              0.0949919 | diagnostic_only_or_rejected |
| risk_adjusted_score_vol63_lambda_0p20 | 0.120239 |     0.0891915 | 0.849712 |      -0.141505 |                    0.358776 |              0.210005  | diagnostic_only_or_rejected |
| simple_ensemble_penalty               | 0.147405 |     0.104061  | 0.843595 |      -0.174734 |                    0.431792 |              0.143053  | diagnostic_only_or_rejected |
