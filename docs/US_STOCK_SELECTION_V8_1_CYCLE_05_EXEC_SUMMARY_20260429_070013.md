# US Stock Selection v8.1 Cycle 05 Exec Summary

- best_regime_candidate：`qqq_ma200_scale_50`
- accepted_candidate_needs_human_review：`True`
- strong_candidate：`False`
- plateau：`True`
- replace_best：`False`
- allow_enter_v9：`False`
- 最大风险：`full-period CAGR materially below v8 baseline; full-period 50bps CAGR materially below v8 baseline; weakest 12M Calmar remains below 1; weakest 12M 50bps CAGR remains below 20%; weakest 12M top3 month concentration not improved vs baseline`
- 建议：`停止 v8.1 overlay 自我进化；v8 baseline 仍为 best，后续回到选股层/universe/ranking/验证切分等基础研究。`

## Full-Period Snapshot

| candidate | cagr | cost50_cagr | calmar | max_drawdown | rolling_12m_min_calmar_like | top3_positive_month_share | avg_cash_share | accepted_candidate_needs_human_review | strong_candidate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline_no_overlay | 0.653818 | 0.560843 | 1.991527 | -0.328300 | 0.636101 | 0.389378 | 0.036522 | False | False |
| high_beta_softcap_15 | 0.608302 | 0.517345 | 1.939737 | -0.313601 | 0.687929 | 0.403457 | 0.036522 | True | False |
| cycle04_vol_throttle_nav_63d_40 | 0.546682 | 0.459564 | 1.670501 | -0.327257 | 0.598741 | 0.402388 | 0.081105 | False | False |
| qqq_ma200_scale_50 | 0.573123 | 0.481626 | 2.027741 | -0.282641 | 0.813150 | 0.415050 | 0.086087 | True | False |
| qqq_ma200_scale_75 | 0.614938 | 0.522570 | 2.137785 | -0.287652 | 0.725719 | 0.395561 | 0.061304 | True | False |
| qqq_ma200_slope_confirm | 0.551805 | 0.463453 | 1.680795 | -0.328300 | 0.636101 | 0.403235 | 0.053043 | True | False |
| qqq_spy_dual_ma200 | 0.555089 | 0.464642 | 1.963936 | -0.282641 | 0.699726 | 0.414195 | 0.084783 | True | False |
| qqq_drawdown_regime | 0.525690 | 0.428488 | 1.767108 | -0.297486 | 0.481750 | 0.404747 | 0.063913 | False | False |
| softcap15_plus_best_simple_regime | 0.529171 | 0.439825 | 1.922088 | -0.275311 | 0.862700 | 0.424686 | 0.086087 | False | False |

