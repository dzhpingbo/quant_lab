# US Stock Selection v8.1 Cycle 03 Exec Summary

- 最优候选：`high_beta_softcap_15`
- 是否通过 acceptance gates：`True`
- 是否替代 v8 baseline：`False`
- 是否建议进入 v9：`False`
- 最大风险：`full-period CAGR is below v8 baseline; full-period Calmar is below v8 baseline; weakest 12M Calmar remains below 1; weakest 12M 50bps cost CAGR remains below 20%; weakest 12M top3 month concentration remains high`
- 建议：`暂停并由用户/ChatGPT 决定是否做 v8.1 final validation；不要进入 v9，不扩 universe。`

## 与 v8 baseline 对比

| variant_id | cagr | cost50_cagr | calmar | max_drawdown | leave_one_year_out_min_cagr | leave_one_year_out_min_calmar | top3_positive_month_share | average_high_beta_weight_share |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline_no_overlay | 0.653818 | 0.560843 | 1.991527 | -0.328300 | 0.527392 | 1.617424 | 0.389378 | 0.145848 |
| high_beta_softcap_10 | 0.550519 | 0.462913 | 1.828661 | -0.301050 | 0.411174 | 1.519612 | 0.412780 | 0.072924 |
| high_beta_softcap_15 | 0.608302 | 0.517345 | 1.939737 | -0.313601 | 0.497246 | 1.730179 | 0.403457 | 0.109386 |
| high_beta_softcap_20 | 0.653818 | 0.560843 | 1.991527 | -0.328300 | 0.527392 | 1.617424 | 0.389378 | 0.145848 |

