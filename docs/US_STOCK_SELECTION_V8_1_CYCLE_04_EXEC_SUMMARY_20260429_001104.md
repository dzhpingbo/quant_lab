# US Stock Selection v8.1 Cycle 04 Exec Summary

- 最优 overlay 候选：`high_beta_softcap_15`
- 最优 throttle 候选：`vol_throttle_nav_63d_40`
- accepted_candidate_needs_human_review：`True`
- throttle_accepted_candidate：`True`
- strong_candidate：`False`
- 是否替代 v8 baseline：`False`
- 是否允许进入 v9：`False`
- 最大风险：`weakest 12M Calmar remains below 1; weakest 12M 50bps CAGR remains below 20%; weakest 12M top3 month concentration not improved vs baseline`
- 建议：`暂停并由用户/ChatGPT 决定是否做 v8.1 final validation；不要进入 v9，不扩 universe。`

## Full-Period Snapshot

| candidate | cagr | cost50_cagr | calmar | max_drawdown | rolling_12m_min_calmar_like | top3_positive_month_share | avg_cash_share | accepted_candidate_needs_human_review | strong_candidate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline_no_overlay | 0.653818 | 0.560843 | 1.991527 | -0.328300 | 0.636101 | 0.389378 | 0.036522 | False | False |
| high_beta_softcap_15 | 0.608302 | 0.517345 | 1.939737 | -0.313601 | 0.687929 | 0.403457 | 0.036522 | True | False |
| vol_throttle_nav_63d_25 | 0.412310 | 0.345902 | 1.812766 | -0.227448 | 0.335552 | 0.423792 | 0.323054 | False | False |
| vol_throttle_nav_63d_30 | 0.445794 | 0.369783 | 1.663351 | -0.268009 | 0.312045 | 0.411457 | 0.217393 | False | False |
| vol_throttle_nav_63d_35 | 0.483662 | 0.399321 | 1.572986 | -0.307480 | 0.369709 | 0.404266 | 0.132239 | False | False |
| vol_throttle_nav_63d_40 | 0.546682 | 0.459564 | 1.670501 | -0.327257 | 0.598741 | 0.402388 | 0.081105 | True | False |
| drawdown_throttle_nav | 0.456694 | 0.349977 | 1.803134 | -0.253278 | 0.233023 | 0.431929 | 0.164348 | False | False |
| softcap_15_plus_vol_throttle_30 | 0.408649 | 0.334297 | 1.588026 | -0.257332 | 0.356175 | 0.423859 | 0.217393 | False | False |
| softcap_15_plus_drawdown_throttle | 0.416219 | 0.311983 | 1.797640 | -0.231537 | 0.276587 | 0.450676 | 0.164348 | False | False |
| softcap_15_plus_vol_and_drawdown_30 | 0.340373 | 0.257785 | 1.617711 | -0.210404 | 0.196013 | 0.446591 | 0.280832 | False | False |

