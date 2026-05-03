# US Stock Selection v8.1 Evolution Cycle 05

## 1. 本轮目标

验证基于 QQQ/SPY 的事前 market regime filter overlay 是否能改善 weakest 12M、rolling stability、top-month concentration、MaxDD 和成本后表现。

## 2. 为什么 cycle 04 不足

Cycle 04 的 NAV vol/drawdown throttle 未形成 strong candidate。最佳 throttle `vol_throttle_nav_63d_40` 没有改善 weakest 12M，且主要通过降仓换取风险变化，因此本轮只测试市场 regime filter。

## 3. 市场 regime 数据可用性

```json
{
  "has_QQQ": true,
  "has_SPY": true,
  "has_VIX_or_equivalent": false,
  "VIX_or_equivalent_symbols_found": [],
  "QQQ_date_range": [
    "2020-01-02",
    "2026-04-17"
  ],
  "SPY_date_range": [
    "2020-01-02",
    "2026-04-17"
  ],
  "chosen_regime_sources": [
    "QQQ",
    "SPY"
  ],
  "regime_source_use": "QQQ/SPY close-derived lagged MA200 and QQQ lagged drawdown scales",
  "lookahead_risk_assessment": "low: every regime decision uses close/MA/drawdown values shifted by one trading day; no future returns, future drawdown, future top month, model label, or retrained signal is used",
  "provider_uri": "C:\\Users\\Administrator\\.qlib\\qlib_data\\us_data_local_2026",
  "start": "2024-01-02",
  "end": "2026-04-17"
}
```

## 4. 所有 regime 规则是否 lagged

是。QQQ/SPY close、MA200、MA200 slope、QQQ 252D drawdown 全部使用 `.shift(1)` 后的 t-1 或更早数据。

## 5. 各候选 full-period 结果

| candidate | cagr | cost50_cagr | calmar | cost50_calmar | max_drawdown | annual_turnover | trade_count | avg_gross_exposure | avg_cash_share | avg_scale | min_scale | scale_change_count | accepted_candidate_needs_human_review | strong_candidate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline_no_overlay | 0.653818 | 0.560843 | 1.991527 | 1.597047 | -0.328300 | 12.709565 | 145 | 0.963478 | 0.036522 | 1.000000 | 1.000000 | 0 | False | False |
| high_beta_softcap_15 | 0.608302 | 0.517345 | 1.939737 | 1.579022 | -0.313601 | 12.786261 | 150 | 0.963478 | 0.036522 | 1.000000 | 1.000000 | 0 | True | False |
| cycle04_vol_throttle_nav_63d_40 | 0.546682 | 0.459564 | 1.670501 | 1.311262 | -0.327257 | 12.755015 | 934 | 0.918895 | 0.081105 | 0.955417 | 0.631708 | 163 | False | False |
| qqq_ma200_scale_50 | 0.573123 | 0.481626 | 2.027741 | 1.679788 | -0.282641 | 13.147826 | 175 | 0.913913 | 0.086087 | 0.950435 | 0.500000 | 6 | True | False |
| qqq_ma200_scale_75 | 0.614938 | 0.522570 | 2.137785 | 1.670948 | -0.287652 | 12.928696 | 175 | 0.938696 | 0.061304 | 0.975217 | 0.750000 | 6 | True | False |
| qqq_ma200_slope_confirm | 0.551805 | 0.463453 | 1.680795 | 1.319721 | -0.328300 | 12.884870 | 155 | 0.946957 | 0.053043 | 0.983478 | 0.500000 | 2 | True | False |
| qqq_spy_dual_ma200 | 0.555089 | 0.464642 | 1.963936 | 1.590110 | -0.282641 | 13.147826 | 185 | 0.915217 | 0.084783 | 0.951739 | 0.500000 | 8 | True | False |
| qqq_drawdown_regime | 0.525690 | 0.428488 | 1.767108 | 1.337241 | -0.297486 | 14.462609 | 238 | 0.936087 | 0.063913 | 0.972609 | 0.250000 | 19 | False | False |
| softcap15_plus_best_simple_regime | 0.529171 | 0.439825 | 1.922088 | 1.575015 | -0.275311 | 13.208087 | 180 | 0.913913 | 0.086087 | 0.950435 | 0.500000 | 6 | False | False |


## 6. weakest 12M 对比

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


## 7. concentration / stability gate

| candidate | gate_name | gate_layer | metric_value | threshold | pass_fail |
| --- | --- | --- | --- | --- | --- |
| baseline_no_overlay | leave_one_year_out_min_cagr | hard | 0.527391568038992 | >= 0.2 | pass |
| baseline_no_overlay | leave_one_year_out_min_calmar | hard | 1.617423567224566 | >= 1.0 | pass |
| baseline_no_overlay | top1_positive_month_share | hard | 0.16860106413893422 | <= 0.25 | pass |
| baseline_no_overlay | top3_positive_month_share | hard | 0.3893784301688419 | <= 0.5 | pass |
| baseline_no_overlay | max_ticker_abs_share | hard | 0.22360323143558838 | <= 0.3 | pass |
| baseline_no_overlay | max_ticker_month_weight | hard | 0.2 | <= 0.3 | pass |
| baseline_no_overlay | current_abs_return_share | observation | 0.5260274868858267 | <= 0.55 | pass |
| baseline_no_overlay | top5_positive_month_share | observation | 0.5410013606918052 | <= 0.6 | pass |
| baseline_no_overlay | rolling_12m_min_calmar_like | observation | 0.6361012879701722 | >= 0.5 | pass |
| baseline_no_overlay | dominant_year_unique_ticker_count | observation | 20.0 | >= 10 | pass |
| baseline_no_overlay | dominant_year_avg_holding_count | observation | 4.583333333333333 | >= 3 | pass |
| high_beta_softcap_15 | leave_one_year_out_min_cagr | hard | 0.49724601090290776 | >= 0.2 | pass |
| high_beta_softcap_15 | leave_one_year_out_min_calmar | hard | 1.7301791316093436 | >= 1.0 | pass |
| high_beta_softcap_15 | top1_positive_month_share | hard | 0.17621114832414206 | <= 0.25 | pass |
| high_beta_softcap_15 | top3_positive_month_share | hard | 0.4034568950860635 | <= 0.5 | pass |
| high_beta_softcap_15 | max_ticker_abs_share | hard | 0.174122879932513 | <= 0.3 | pass |
| high_beta_softcap_15 | max_ticker_month_weight | hard | 0.2750000000000001 | <= 0.3 | pass |
| high_beta_softcap_15 | current_abs_return_share | observation | 0.5179308368731944 | <= 0.55 | pass |
| high_beta_softcap_15 | top5_positive_month_share | observation | 0.5592932259647505 | <= 0.6 | pass |
| high_beta_softcap_15 | rolling_12m_min_calmar_like | observation | 0.6879289617697246 | >= 0.5 | pass |
| high_beta_softcap_15 | dominant_year_unique_ticker_count | observation | 24.0 | >= 10 | pass |
| high_beta_softcap_15 | dominant_year_avg_holding_count | observation | 5.0 | >= 3 | pass |
| cycle04_vol_throttle_nav_63d_40 | leave_one_year_out_min_cagr | hard | 0.36177405887728376 | >= 0.2 | pass |
| cycle04_vol_throttle_nav_63d_40 | leave_one_year_out_min_calmar | hard | 1.1164229559187369 | >= 1.0 | pass |
| cycle04_vol_throttle_nav_63d_40 | top1_positive_month_share | hard | 0.16995723747758623 | <= 0.25 | pass |
| cycle04_vol_throttle_nav_63d_40 | top3_positive_month_share | hard | 0.4023877877144685 | <= 0.5 | pass |
| cycle04_vol_throttle_nav_63d_40 | max_ticker_abs_share | hard | 0.2296057331620555 | <= 0.3 | pass |
| cycle04_vol_throttle_nav_63d_40 | max_ticker_month_weight | hard | 0.2 | <= 0.3 | pass |
| cycle04_vol_throttle_nav_63d_40 | current_abs_return_share | observation | 0.616254753302019 | <= 0.55 | fail |
| cycle04_vol_throttle_nav_63d_40 | top5_positive_month_share | observation | 0.5279781776592447 | <= 0.6 | pass |
| cycle04_vol_throttle_nav_63d_40 | rolling_12m_min_calmar_like | observation | 0.598741091105613 | >= 0.5 | pass |
| cycle04_vol_throttle_nav_63d_40 | dominant_year_unique_ticker_count | observation | 20.0 | >= 10 | pass |
| cycle04_vol_throttle_nav_63d_40 | dominant_year_avg_holding_count | observation | 4.583333333333333 | >= 3 | pass |
| qqq_ma200_scale_50 | leave_one_year_out_min_cagr | hard | 0.39725443005057737 | >= 0.2 | pass |
| qqq_ma200_scale_50 | leave_one_year_out_min_calmar | hard | 1.6319089912101026 | >= 1.0 | pass |
| qqq_ma200_scale_50 | top1_positive_month_share | hard | 0.17717393551128152 | <= 0.25 | pass |
| qqq_ma200_scale_50 | top3_positive_month_share | hard | 0.4150500552221717 | <= 0.5 | pass |
| qqq_ma200_scale_50 | max_ticker_abs_share | hard | 0.22357757089490876 | <= 0.3 | pass |
| qqq_ma200_scale_50 | max_ticker_month_weight | hard | 0.2 | <= 0.3 | pass |
| qqq_ma200_scale_50 | current_abs_return_share | observation | 0.5931350365552279 | <= 0.55 | fail |
| qqq_ma200_scale_50 | top5_positive_month_share | observation | 0.5411998974853646 | <= 0.6 | pass |
| qqq_ma200_scale_50 | rolling_12m_min_calmar_like | observation | 0.8131503675975843 | >= 0.5 | pass |
| qqq_ma200_scale_50 | dominant_year_unique_ticker_count | observation | 20.0 | >= 10 | pass |
| qqq_ma200_scale_50 | dominant_year_avg_holding_count | observation | 4.583333333333333 | >= 3 | pass |
| qqq_ma200_scale_75 | leave_one_year_out_min_cagr | hard | 0.4640554145753788 | >= 0.2 | pass |
| qqq_ma200_scale_75 | leave_one_year_out_min_calmar | hard | 1.6266339109728103 | >= 1.0 | pass |
| qqq_ma200_scale_75 | top1_positive_month_share | hard | 0.17264564095170648 | <= 0.25 | pass |
| qqq_ma200_scale_75 | top3_positive_month_share | hard | 0.395561193630657 | <= 0.5 | pass |
| qqq_ma200_scale_75 | max_ticker_abs_share | hard | 0.22359101795866024 | <= 0.3 | pass |
| qqq_ma200_scale_75 | max_ticker_month_weight | hard | 0.2 | <= 0.3 | pass |
| qqq_ma200_scale_75 | current_abs_return_share | observation | 0.5570376710055361 | <= 0.55 | fail |
| qqq_ma200_scale_75 | top5_positive_month_share | observation | 0.5267151882045769 | <= 0.6 | pass |
| qqq_ma200_scale_75 | rolling_12m_min_calmar_like | observation | 0.7257185584910183 | >= 0.5 | pass |
| qqq_ma200_scale_75 | dominant_year_unique_ticker_count | observation | 20.0 | >= 10 | pass |
| qqq_ma200_scale_75 | dominant_year_avg_holding_count | observation | 4.583333333333333 | >= 3 | pass |
| qqq_ma200_slope_confirm | leave_one_year_out_min_cagr | hard | 0.3637258371132115 | >= 0.2 | pass |
| qqq_ma200_slope_confirm | leave_one_year_out_min_calmar | hard | 1.1154875743328094 | >= 1.0 | pass |
| qqq_ma200_slope_confirm | top1_positive_month_share | hard | 0.1697979258344096 | <= 0.25 | pass |
| qqq_ma200_slope_confirm | top3_positive_month_share | hard | 0.40323481331640776 | <= 0.5 | pass |
| qqq_ma200_slope_confirm | max_ticker_abs_share | hard | 0.22171237949231556 | <= 0.3 | pass |
| qqq_ma200_slope_confirm | max_ticker_month_weight | hard | 0.2 | <= 0.3 | pass |
| qqq_ma200_slope_confirm | current_abs_return_share | observation | 0.6179650641850607 | <= 0.55 | fail |
| qqq_ma200_slope_confirm | top5_positive_month_share | observation | 0.526507982683887 | <= 0.6 | pass |
| qqq_ma200_slope_confirm | rolling_12m_min_calmar_like | observation | 0.6361012879701722 | >= 0.5 | pass |
| qqq_ma200_slope_confirm | dominant_year_unique_ticker_count | observation | 20.0 | >= 10 | pass |
| qqq_ma200_slope_confirm | dominant_year_avg_holding_count | observation | 4.583333333333333 | >= 3 | pass |
| qqq_spy_dual_ma200 | leave_one_year_out_min_cagr | hard | 0.3688675842033793 | >= 0.2 | pass |
| qqq_spy_dual_ma200 | leave_one_year_out_min_calmar | hard | 1.4021446783477816 | >= 1.0 | pass |
| qqq_spy_dual_ma200 | top1_positive_month_share | hard | 0.17498774543518023 | <= 0.25 | pass |
| qqq_spy_dual_ma200 | top3_positive_month_share | hard | 0.41419487182602277 | <= 0.5 | pass |
| qqq_spy_dual_ma200 | max_ticker_abs_share | hard | 0.22510678191194114 | <= 0.3 | pass |
| qqq_spy_dual_ma200 | max_ticker_month_weight | hard | 0.2 | <= 0.3 | pass |
| qqq_spy_dual_ma200 | current_abs_return_share | observation | 0.610747924608317 | <= 0.55 | fail |
| qqq_spy_dual_ma200 | top5_positive_month_share | observation | 0.5405579695008422 | <= 0.6 | pass |
| qqq_spy_dual_ma200 | rolling_12m_min_calmar_like | observation | 0.6997259040379787 | >= 0.5 | pass |
| qqq_spy_dual_ma200 | dominant_year_unique_ticker_count | observation | 20.0 | >= 10 | pass |
| qqq_spy_dual_ma200 | dominant_year_avg_holding_count | observation | 4.583333333333333 | >= 3 | pass |
| qqq_drawdown_regime | leave_one_year_out_min_cagr | hard | 0.34991268357847827 | >= 0.2 | pass |
| qqq_drawdown_regime | leave_one_year_out_min_calmar | hard | 1.1997161420146578 | >= 1.0 | pass |
| qqq_drawdown_regime | top1_positive_month_share | hard | 0.17012682573426882 | <= 0.25 | pass |
| qqq_drawdown_regime | top3_positive_month_share | hard | 0.4047465923088802 | <= 0.5 | pass |
| qqq_drawdown_regime | max_ticker_abs_share | hard | 0.22226941201493264 | <= 0.3 | pass |
| qqq_drawdown_regime | max_ticker_month_weight | hard | 0.2 | <= 0.3 | pass |
| qqq_drawdown_regime | current_abs_return_share | observation | 0.5891600576152992 | <= 0.55 | fail |
| qqq_drawdown_regime | top5_positive_month_share | observation | 0.5455598408280737 | <= 0.6 | pass |
| qqq_drawdown_regime | rolling_12m_min_calmar_like | observation | 0.4817502197538611 | >= 0.5 | fail |
| qqq_drawdown_regime | dominant_year_unique_ticker_count | observation | 20.0 | >= 10 | pass |
| qqq_drawdown_regime | dominant_year_avg_holding_count | observation | 4.583333333333333 | >= 3 | pass |
| softcap15_plus_best_simple_regime | leave_one_year_out_min_cagr | hard | 0.41007552666985814 | >= 0.2 | pass |
| softcap15_plus_best_simple_regime | leave_one_year_out_min_calmar | hard | 1.76351015510606 | >= 1.0 | pass |
| softcap15_plus_best_simple_regime | top1_positive_month_share | hard | 0.1867128586472138 | <= 0.25 | pass |
| softcap15_plus_best_simple_regime | top3_positive_month_share | hard | 0.4246858023449914 | <= 0.5 | pass |
| softcap15_plus_best_simple_regime | max_ticker_abs_share | hard | 0.17484675129153626 | <= 0.3 | pass |
| softcap15_plus_best_simple_regime | max_ticker_month_weight | hard | 0.2750000000000001 | <= 0.3 | pass |
| softcap15_plus_best_simple_regime | current_abs_return_share | observation | 0.5432425434302403 | <= 0.55 | pass |
| softcap15_plus_best_simple_regime | top5_positive_month_share | observation | 0.5466721388979986 | <= 0.6 | pass |
| softcap15_plus_best_simple_regime | rolling_12m_min_calmar_like | observation | 0.8627003240654441 | >= 0.5 | pass |
| softcap15_plus_best_simple_regime | dominant_year_unique_ticker_count | observation | 20.0 | >= 10 | pass |
| softcap15_plus_best_simple_regime | dominant_year_avg_holding_count | observation | 4.583333333333333 | >= 3 | pass |
| high_beta_softcap_15 | full_period_cagr_ge_20 | acceptance |  |  | pass |
| high_beta_softcap_15 | full_period_cost50_cagr_ge_20 | acceptance |  |  | pass |
| high_beta_softcap_15 | full_period_calmar_ge_1 | acceptance |  |  | pass |
| high_beta_softcap_15 | full_period_calmar_ge_80pct_v8 | acceptance |  |  | pass |
| high_beta_softcap_15 | full_period_cost50_cagr_ge_80pct_v8 | acceptance |  |  | pass |
| high_beta_softcap_15 | maxdd_not_significantly_worse_than_v8 | acceptance |  |  | pass |
| high_beta_softcap_15 | leave_one_year_out_min_cagr_ge_20 | acceptance |  |  | pass |
| high_beta_softcap_15 | leave_one_year_out_min_calmar_ge_1 | acceptance |  |  | pass |
| high_beta_softcap_15 | top1_positive_month_share_lte_25 | acceptance |  |  | pass |
| high_beta_softcap_15 | top3_positive_month_share_lte_50 | acceptance |  |  | pass |
| high_beta_softcap_15 | max_ticker_abs_share_lte_30 | acceptance |  |  | pass |
| high_beta_softcap_15 | max_ticker_month_weight_lte_30 | acceptance |  |  | pass |
| high_beta_softcap_15 | gross_exposure_normal | acceptance |  |  | pass |
| high_beta_softcap_15 | regime_decision_lookahead_free | acceptance |  |  | pass |
| high_beta_softcap_15 | not_long_term_low_exposure_pseudo_improvement | acceptance |  |  | pass |
| high_beta_softcap_15 | accepted_candidate_needs_human_review | acceptance |  |  | pass |
| high_beta_softcap_15 | accepted_candidate_needs_human_review | strong |  |  | pass |
| high_beta_softcap_15 | weakest_12m_calmar_ge_1 | strong |  |  | fail |
| high_beta_softcap_15 | weakest_12m_cost50_cagr_ge_20 | strong |  |  | fail |
| high_beta_softcap_15 | weakest_12m_top3_share_below_baseline | strong |  |  | fail |
| high_beta_softcap_15 | full_period_calmar_ge_90pct_v8 | strong |  |  | pass |
| high_beta_softcap_15 | full_period_cost50_cagr_ge_90pct_v8 | strong |  |  | pass |
| high_beta_softcap_15 | simple_explainable_non_overfit_rule | strong |  |  | pass |
| high_beta_softcap_15 | strong_candidate | strong |  |  | fail |
| cycle04_vol_throttle_nav_63d_40 | full_period_cagr_ge_20 | acceptance |  |  | pass |
| cycle04_vol_throttle_nav_63d_40 | full_period_cost50_cagr_ge_20 | acceptance |  |  | pass |
| cycle04_vol_throttle_nav_63d_40 | full_period_calmar_ge_1 | acceptance |  |  | pass |
| cycle04_vol_throttle_nav_63d_40 | full_period_calmar_ge_80pct_v8 | acceptance |  |  | pass |
| cycle04_vol_throttle_nav_63d_40 | full_period_cost50_cagr_ge_80pct_v8 | acceptance |  |  | pass |
| cycle04_vol_throttle_nav_63d_40 | maxdd_not_significantly_worse_than_v8 | acceptance |  |  | pass |
| cycle04_vol_throttle_nav_63d_40 | leave_one_year_out_min_cagr_ge_20 | acceptance |  |  | pass |
| cycle04_vol_throttle_nav_63d_40 | leave_one_year_out_min_calmar_ge_1 | acceptance |  |  | pass |
| cycle04_vol_throttle_nav_63d_40 | top1_positive_month_share_lte_25 | acceptance |  |  | pass |
| cycle04_vol_throttle_nav_63d_40 | top3_positive_month_share_lte_50 | acceptance |  |  | pass |
| cycle04_vol_throttle_nav_63d_40 | max_ticker_abs_share_lte_30 | acceptance |  |  | pass |
| cycle04_vol_throttle_nav_63d_40 | max_ticker_month_weight_lte_30 | acceptance |  |  | pass |
| cycle04_vol_throttle_nav_63d_40 | gross_exposure_normal | acceptance |  |  | pass |
| cycle04_vol_throttle_nav_63d_40 | regime_decision_lookahead_free | acceptance |  |  | pass |
| cycle04_vol_throttle_nav_63d_40 | not_long_term_low_exposure_pseudo_improvement | acceptance |  |  | pass |
| cycle04_vol_throttle_nav_63d_40 | accepted_candidate_needs_human_review | acceptance |  |  | fail |
| cycle04_vol_throttle_nav_63d_40 | accepted_candidate_needs_human_review | strong |  |  | fail |


## 8. 成本压力结果

50bps cost stress 已对每个候选独立 replay。Scale 摘要：

| avg_scale | min_scale | max_scale | scale_change_count | scale_change_turnover | scale_lt_100_day_count | scale_lte_75_day_count | scale_lte_50_day_count | scale_lte_25_day_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1.000000 | 1.000000 | 1.000000 | 0 | 0.000000 | 0 | 0 | 0 | 0 |
| 1.000000 | 1.000000 | 1.000000 | 0 | 0.000000 | 0 | 0 | 0 | 0 |
| 0.955417 | 0.631708 | 1.000000 | 163 | 1.539765 | 155 | 63 | 0 | 0 |
| 0.950435 | 0.500000 | 1.000000 | 6 | 3.000000 | 57 | 57 | 57 | 0 |
| 0.975217 | 0.750000 | 1.000000 | 6 | 1.500000 | 57 | 57 | 0 | 0 |
| 0.983478 | 0.500000 | 1.000000 | 2 | 1.000000 | 19 | 19 | 19 | 0 |
| 0.951739 | 0.500000 | 1.000000 | 8 | 3.000000 | 57 | 57 | 54 | 0 |
| 0.972609 | 0.250000 | 1.000000 | 19 | 5.000000 | 48 | 48 | 12 | 3 |
| 0.950435 | 0.500000 | 1.000000 | 6 | 3.000000 | 57 | 57 | 57 | 0 |


## 9. 是否有 accepted_candidate

`True`. Best market regime candidate: `qqq_ma200_scale_50`.

## 10. 是否有 strong_candidate

`False`

## 11. 是否替代 best

`False`

## 12. 是否允许进入 v9

`False`

## 13. 是否进入 plateau

`True`
