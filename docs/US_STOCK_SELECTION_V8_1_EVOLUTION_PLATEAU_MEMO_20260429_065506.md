# US Stock Selection v8.1 Evolution Plateau Memo

## 结论

Cycle 05 未产生 `strong_candidate`。v8.1 overlay 路线应停止自我进化，不进入 cycle 06。

## 当前建议

1. v8 baseline 仍为当前 best。
2. v8.1 overlays 只作为风险观察项。
3. `high_beta_softcap_15` 是最有价值的风控备选，但不替代 baseline。
4. NAV throttle 和 market regime overlay 未达到 strong candidate，不进入正式版本。
5. 不建议进入 v9。
6. 不建议扩池，除非用户明确批准。
7. 后续应回到更基础的研究方向：stock selection layer、候选池、横截面 ranking 集中度惩罚、训练/验证切分、更长历史数据。

## Best Regime Candidate

`qqq_ma200_scale_50`

## Full-Period Snapshot

| candidate | cagr | cost50_cagr | calmar | max_drawdown | accepted_candidate_needs_human_review | strong_candidate |
| --- | --- | --- | --- | --- | --- | --- |
| baseline_no_overlay | 0.653818 | 0.560843 | 1.991527 | -0.328300 | False | False |
| high_beta_softcap_15 | 0.608302 | 0.517345 | 1.939737 | -0.313601 | True | False |
| cycle04_vol_throttle_nav_63d_40 | 0.546682 | 0.459564 | 1.670501 | -0.327257 | False | False |
| qqq_ma200_scale_50 | 0.573123 | 0.481626 | 2.027741 | -0.282641 | True | False |
| qqq_ma200_scale_75 | 0.614938 | 0.522570 | 2.137785 | -0.287652 | True | False |
| qqq_ma200_slope_confirm | 0.551805 | 0.463453 | 1.680795 | -0.328300 | True | False |
| qqq_spy_dual_ma200 | 0.555089 | 0.464642 | 1.963936 | -0.282641 | True | False |
| qqq_drawdown_regime | 0.525690 | 0.428488 | 1.767108 | -0.297486 | False | False |
| softcap15_plus_best_simple_regime | 0.529171 | 0.439825 | 1.922088 | -0.275311 | False | False |


## Weakest 12M Snapshot

| candidate | window_start | window_end | cagr | cost50_cagr | max_drawdown | calmar | cost50_calmar | top1_positive_month_share | top3_positive_month_share | top5_positive_month_share | avg_scale | min_scale | avg_cash_share | avg_high_beta_weight_share |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline_no_overlay | 2024-04-01 | 2025-03-31 | 0.194578 | 0.121921 | -0.282641 | 0.688429 | 0.425228 | 0.455046 | 0.802593 | 0.972440 | 1.000000 | 1.000000 | 0.000000 | 0.165737 |
| high_beta_softcap_15 | 2024-04-01 | 2025-03-31 | 0.202207 | 0.129049 | -0.275311 | 0.734470 | 0.462123 | 0.454794 | 0.805810 | 0.970075 | 1.000000 | 1.000000 | 0.000000 | 0.124303 |
| cycle04_vol_throttle_nav_63d_40 | 2024-04-01 | 2025-03-31 | 0.183884 | 0.110280 | -0.282637 | 0.650601 | 0.384633 | 0.454817 | 0.807708 | 0.977048 | 0.983406 | 0.904284 | 0.016594 | 0.164237 |
| qqq_ma200_scale_50 | 2024-04-01 | 2025-03-31 | 0.245247 | 0.161538 | -0.282641 | 0.867697 | 0.563404 | 0.455046 | 0.802593 | 0.972440 | 0.968127 | 0.500000 | 0.031873 | 0.159363 |
| qqq_ma200_scale_75 | 2024-04-01 | 2025-03-31 | 0.220225 | 0.142085 | -0.282641 | 0.779169 | 0.495555 | 0.455046 | 0.802593 | 0.972440 | 0.984064 | 0.750000 | 0.015936 | 0.162550 |
| qqq_ma200_slope_confirm | 2024-04-01 | 2025-03-31 | 0.194578 | 0.121921 | -0.282641 | 0.688429 | 0.425228 | 0.455046 | 0.802593 | 0.972440 | 1.000000 | 1.000000 | 0.000000 | 0.165737 |
| qqq_spy_dual_ma200 | 2024-04-01 | 2025-03-31 | 0.212787 | 0.131263 | -0.282641 | 0.752851 | 0.457812 | 0.455046 | 0.802593 | 0.972440 | 0.971116 | 0.500000 | 0.028884 | 0.159960 |
| qqq_drawdown_regime | 2024-04-01 | 2025-03-31 | 0.157647 | 0.078673 | -0.297486 | 0.529929 | 0.259588 | 0.453476 | 0.808831 | 0.972535 | 0.979084 | 0.750000 | 0.020916 | 0.161554 |
| softcap15_plus_best_simple_regime | 2024-04-01 | 2025-03-31 | 0.250842 | 0.166720 | -0.275311 | 0.911124 | 0.597023 | 0.454794 | 0.805810 | 0.970075 | 0.968127 | 0.500000 | 0.031873 | 0.119522 |

