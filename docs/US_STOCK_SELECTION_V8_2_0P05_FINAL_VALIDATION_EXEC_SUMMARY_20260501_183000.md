# v8.2 0p05 Final Validation Exec Summary

- Reproduction pass: `True`
- Final classification: `risk_control_variant`
- Risk-control variant: `True`
- Replace baseline candidate: `False`
- Replace v8 best: `False`
- Allow enter v9: `False`
- 50bps CAGR safety margin vs 0.4487: `0.002854346934815788`
- Top5 concentration risk: `0.6108045896766657`

## Key Metrics

| rerank_candidate       |     cagr |   cost50_cagr |   calmar |   max_drawdown |   weakest_12m_Calmar |   weakest_12m_50bps_CAGR |   avg_high_beta_weight_share |
|:-----------------------|---------:|--------------:|---------:|---------------:|---------------------:|-------------------------:|-----------------------------:|
| baseline_original_rank | 0.653818 |      0.560843 |  1.99153 |      -0.3283   |             0.636101 |                 0.10803  |                    0.145848  |
| high_beta_penalty_0p05 | 0.540441 |      0.451554 |  1.6882  |      -0.320129 |             1.07682  |                 0.208314 |                    0.0714801 |
