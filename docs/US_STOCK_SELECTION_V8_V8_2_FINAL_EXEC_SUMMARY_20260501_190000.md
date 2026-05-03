# US Stock Selection v8 / v8.2 Final Exec Summary

- 当前 best：`v8_baseline_return_priority`
- 风险控制备选：`v8_2_high_beta_penalty_0p05`
- 是否替代 best：`False`
- 是否进入 v9：`False`
- 是否继续 overlay/reranking 微调：`False`
- 是否自动扩 universe：`False`

## 快速结论

v8 baseline 仍是收益优先版本；0p05 是 risk-control variant，不是收益最优策略。后续如继续，应新立项：更长历史、更合理 universe、stock selection model 重构与更严格 validation framework。

## 对比

| strategy_name                            | classification               |     CAGR |   cost_50bps_CAGR |   Calmar |     MaxDD |   weakest_12m_Calmar |   weakest_12m_50bps_CAGR |   avg_high_beta_weight |   max_high_beta_weight |   top1_positive_month_share |   top3_positive_month_share |   top5_positive_month_share |   remove_top5_month_CAGR | cost_sensitivity_comment                                                     | concentration_risk_comment                                                       | recommended_usage                                                                         | replace_v8_best   | allow_enter_v9   |
|:-----------------------------------------|:-----------------------------|---------:|------------------:|---------:|----------:|---------------------:|-------------------------:|-----------------------:|-----------------------:|----------------------------:|----------------------------:|----------------------------:|-------------------------:|:-----------------------------------------------------------------------------|:---------------------------------------------------------------------------------|:------------------------------------------------------------------------------------------|:------------------|:-----------------|
| v8_baseline_return_priority              | current_best_return_priority | 0.653818 |          0.560843 |  1.99153 | -0.3283   |             0.636101 |                 0.10803  |              0.145848  |                    0.6 |                    0.168601 |                    0.389378 |                    0.541001 |                0.139524  | Stronger cost-adjusted CAGR than 0p05; still execution-sensitive.            | Higher high-beta exposure; MSTR/TQQQ/QLD/SOXL contribution must be monitored.    | Return-priority research baseline; current best, not a live trading recommendation.       | False             | False            |
| v8_2_high_beta_penalty_0p05_risk_control | risk_control_variant         | 0.540441 |          0.451554 |  1.6882  | -0.320129 |             1.07682  |                 0.208314 |              0.0714801 |                    0.2 |                    0.186514 |                    0.447073 |                    0.610805 |                0.0219566 | 50bps CAGR barely clears 0.4487 threshold; 75/100bps stress weakens quickly. | High-beta exposure lower, but top5 positive month share is higher than baseline. | Risk-control variant for human review; not return-optimal and not a baseline replacement. | False             | False            |
