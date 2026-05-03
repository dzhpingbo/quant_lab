# US Stock Selection v8.1 Evolution Cycle 04

## 1. 本轮目标

验证事前可执行的 volatility / drawdown throttle overlay 是否能改善 weakest 12M、回撤、top-month concentration 和成本后稳定性。

## 2. 为什么不直接接受 softcap_15

Cycle 03 的 `high_beta_softcap_15` 通过 full-period gates，但 full-period CAGR/Calmar 低于 v8 baseline，且 weakest 12M 的 Calmar、50bps CAGR 和 top-month concentration 仍不足。因此本轮只做进一步 overlay replay，不替代 best。

## 3. 数据可用性检查

```json
{
  "has_strategy_daily_nav": true,
  "has_ticker_daily_returns": true,
  "has_market_regime_data": true,
  "market_regime_columns_found": [
    "QQQ",
    "SPY"
  ],
  "chosen_overlay_signal_source": "strategy_daily_nav_lagged_63d_vol_and_lagged_equity_drawdown",
  "ticker_return_use": "used_for_replay_and_exposure_metrics_only_not_for_throttle_signal",
  "lookahead_risk_assessment": "low: throttle scale uses v8 strategy returns/nav shifted by one trading day; no future top month, future drawdown, future realized return, or label is used",
  "forbidden_overlay_skipped": [],
  "existing_v8_ticker_count": 27,
  "start": "2024-01-02",
  "end": "2026-04-17"
}
```

## 4. overlay 是否存在未来函数风险

本轮 throttle scale 只使用 v8 baseline strategy NAV/returns 的 lag-1 信息：63 日 trailing vol 使用 `.shift(1)`，drawdown 使用 prior NAV 与 prior peak。未使用未来 top month、未来 drawdown、未来收益或 label。

## 5. 各候选 full-period 结果

| candidate | cagr | cost50_cagr | calmar | cost50_calmar | max_drawdown | annual_turnover | trade_count | avg_gross_exposure | avg_cash_share | avg_scale | min_scale | avg_high_beta_weight_share | accepted_candidate_needs_human_review | strong_candidate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline_no_overlay | 0.653818 | 0.560843 | 1.991527 | 1.597047 | -0.328300 | 12.709565 | 145 | 0.963478 | 0.036522 | 1.000000 | 1.000000 | 0.145848 | False | False |
| high_beta_softcap_15 | 0.608302 | 0.517345 | 1.939737 | 1.579022 | -0.313601 | 12.786261 | 150 | 0.963478 | 0.036522 | 1.000000 | 1.000000 | 0.109386 | True | False |
| vol_throttle_nav_63d_25 | 0.412310 | 0.345902 | 1.812766 | 1.409044 | -0.227448 | 10.653842 | 2569 | 0.676946 | 0.323054 | 0.713468 | 0.394818 | 0.087928 | False | False |
| vol_throttle_nav_63d_30 | 0.445794 | 0.369783 | 1.663351 | 1.279798 | -0.268009 | 11.920012 | 2253 | 0.782607 | 0.217393 | 0.819129 | 0.473781 | 0.103604 | False | False |
| vol_throttle_nav_63d_35 | 0.483662 | 0.399321 | 1.572986 | 1.207995 | -0.307480 | 12.897622 | 1931 | 0.867761 | 0.132239 | 0.904283 | 0.552745 | 0.117690 | False | False |
| vol_throttle_nav_63d_40 | 0.546682 | 0.459564 | 1.670501 | 1.311262 | -0.327257 | 12.755015 | 934 | 0.918895 | 0.081105 | 0.955417 | 0.631708 | 0.127929 | True | False |
| drawdown_throttle_nav | 0.456694 | 0.349977 | 1.803134 | 1.237630 | -0.253278 | 16.807304 | 424 | 0.835652 | 0.164348 | 0.872174 | 0.250000 | 0.123466 | False | False |
| softcap_15_plus_vol_throttle_30 | 0.408649 | 0.334297 | 1.588026 | 1.238711 | -0.257332 | 11.966691 | 2253 | 0.782607 | 0.217393 | 0.819129 | 0.473781 | 0.077703 | False | False |
| softcap_15_plus_drawdown_throttle | 0.416219 | 0.311983 | 1.797640 | 1.191147 | -0.231537 | 16.884000 | 429 | 0.835652 | 0.164348 | 0.872174 | 0.250000 | 0.092599 | False | False |
| softcap_15_plus_vol_and_drawdown_30 | 0.340373 | 0.257785 | 1.617711 | 1.133069 | -0.210404 | 14.056090 | 1693 | 0.719168 | 0.280832 | 0.755689 | 0.250000 | 0.068774 | False | False |


## 6. weakest 12M 对比

| candidate | window_start | window_end | cagr | cost50_cagr | max_drawdown | calmar | cost50_calmar | top1_positive_month_share | top3_positive_month_share | top5_positive_month_share | avg_scale | min_scale | avg_cash_share | avg_high_beta_weight_share |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline_no_overlay | 2024-04-01 | 2025-03-31 | 0.194578 | 0.121921 | -0.282641 | 0.688429 | 0.425228 | 0.455046 | 0.802593 | 0.972440 | 1.000000 | 1.000000 | 0.000000 | 0.165737 |
| high_beta_softcap_15 | 2024-04-01 | 2025-03-31 | 0.202207 | 0.129049 | -0.275311 | 0.734470 | 0.462123 | 0.454794 | 0.805810 | 0.970075 | 1.000000 | 1.000000 | 0.000000 | 0.124303 |
| vol_throttle_nav_63d_25 | 2024-04-01 | 2025-03-31 | 0.080602 | 0.030284 | -0.206168 | 0.390951 | 0.144048 | 0.441241 | 0.811967 | 0.978011 | 0.651410 | 0.565177 | 0.348590 | 0.109944 |
| vol_throttle_nav_63d_30 | 2024-04-01 | 2025-03-31 | 0.089246 | 0.028650 | -0.242786 | 0.367591 | 0.115770 | 0.446418 | 0.813883 | 0.978576 | 0.781196 | 0.678213 | 0.218804 | 0.131834 |
| vol_throttle_nav_63d_35 | 2024-04-01 | 2025-03-31 | 0.116259 | 0.045399 | -0.277080 | 0.419587 | 0.161046 | 0.451593 | 0.815778 | 0.979139 | 0.902845 | 0.791248 | 0.097155 | 0.152096 |
| vol_throttle_nav_63d_40 | 2024-04-01 | 2025-03-31 | 0.183884 | 0.110280 | -0.282637 | 0.650601 | 0.384633 | 0.454817 | 0.807708 | 0.977048 | 0.983406 | 0.904284 | 0.016594 | 0.164237 |
| drawdown_throttle_nav | 2024-04-01 | 2025-03-31 | 0.062701 | -0.029040 | -0.212613 | 0.294906 | -0.120867 | 0.517785 | 0.910252 | 0.989386 | 0.803785 | 0.250000 | 0.196215 | 0.128884 |
| softcap_15_plus_vol_throttle_30 | 2024-04-01 | 2025-03-31 | 0.096694 | 0.035675 | -0.238662 | 0.405151 | 0.146677 | 0.447809 | 0.817828 | 0.976711 | 0.781196 | 0.678213 | 0.218804 | 0.098876 |
| softcap_15_plus_drawdown_throttle | 2024-04-01 | 2025-03-31 | 0.068117 | -0.024154 | -0.205116 | 0.332088 | -0.110962 | 0.515825 | 0.915619 | 0.988187 | 0.803785 | 0.250000 | 0.196215 | 0.096663 |
| softcap_15_plus_vol_and_drawdown_30 | 2024-04-01 | 2025-03-31 | 0.047974 | -0.028344 | -0.187764 | 0.255500 | -0.143888 | 0.473214 | 0.859465 | 0.977869 | 0.672821 | 0.250000 | 0.327179 | 0.082743 |


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
| vol_throttle_nav_63d_25 | leave_one_year_out_min_cagr | hard | 0.2991184872263706 | >= 0.2 | pass |
| vol_throttle_nav_63d_25 | leave_one_year_out_min_calmar | hard | 1.315107401872687 | >= 1.0 | pass |
| vol_throttle_nav_63d_25 | top1_positive_month_share | hard | 0.20008527331144288 | <= 0.25 | pass |
| vol_throttle_nav_63d_25 | top3_positive_month_share | hard | 0.4237916371389857 | <= 0.5 | pass |
| vol_throttle_nav_63d_25 | max_ticker_abs_share | hard | 0.25166234240550067 | <= 0.3 | pass |
| vol_throttle_nav_63d_25 | max_ticker_month_weight | hard | 0.2 | <= 0.3 | pass |
| vol_throttle_nav_63d_25 | current_abs_return_share | observation | 0.5785129987887037 | <= 0.55 | fail |
| vol_throttle_nav_63d_25 | top5_positive_month_share | observation | 0.5800133592927712 | <= 0.6 | pass |
| vol_throttle_nav_63d_25 | rolling_12m_min_calmar_like | observation | 0.33555181718854915 | >= 0.5 | fail |
| vol_throttle_nav_63d_25 | dominant_year_unique_ticker_count | observation | 20.0 | >= 10 | pass |
| vol_throttle_nav_63d_25 | dominant_year_avg_holding_count | observation | 4.583333333333333 | >= 3 | pass |
| vol_throttle_nav_63d_30 | leave_one_year_out_min_cagr | hard | 0.31210080259642137 | >= 0.2 | pass |
| vol_throttle_nav_63d_30 | leave_one_year_out_min_calmar | hard | 1.165277667149397 | >= 1.0 | pass |
| vol_throttle_nav_63d_30 | top1_positive_month_share | hard | 0.18556645698883728 | <= 0.25 | pass |
| vol_throttle_nav_63d_30 | top3_positive_month_share | hard | 0.4114567216866538 | <= 0.5 | pass |
| vol_throttle_nav_63d_30 | max_ticker_abs_share | hard | 0.23732603197909607 | <= 0.3 | pass |
| vol_throttle_nav_63d_30 | max_ticker_month_weight | hard | 0.2 | <= 0.3 | pass |
| vol_throttle_nav_63d_30 | current_abs_return_share | observation | 0.5890435102164987 | <= 0.55 | fail |
| vol_throttle_nav_63d_30 | top5_positive_month_share | observation | 0.5538651350206705 | <= 0.6 | pass |
| vol_throttle_nav_63d_30 | rolling_12m_min_calmar_like | observation | 0.3120453704278499 | >= 0.5 | fail |
| vol_throttle_nav_63d_30 | dominant_year_unique_ticker_count | observation | 20.0 | >= 10 | pass |
| vol_throttle_nav_63d_30 | dominant_year_avg_holding_count | observation | 4.583333333333333 | >= 3 | pass |
| vol_throttle_nav_63d_35 | leave_one_year_out_min_cagr | hard | 0.3237393794099144 | >= 0.2 | pass |
| vol_throttle_nav_63d_35 | leave_one_year_out_min_calmar | hard | 1.0558944765358953 | >= 1.0 | pass |
| vol_throttle_nav_63d_35 | top1_positive_month_share | hard | 0.17393248247012186 | <= 0.25 | pass |
| vol_throttle_nav_63d_35 | top3_positive_month_share | hard | 0.4042664562734616 | <= 0.5 | pass |
| vol_throttle_nav_63d_35 | max_ticker_abs_share | hard | 0.22951350973415763 | <= 0.3 | pass |
| vol_throttle_nav_63d_35 | max_ticker_month_weight | hard | 0.2 | <= 0.3 | pass |
| vol_throttle_nav_63d_35 | current_abs_return_share | observation | 0.6040940406489705 | <= 0.55 | fail |
| vol_throttle_nav_63d_35 | top5_positive_month_share | observation | 0.5361981441571094 | <= 0.6 | pass |
| vol_throttle_nav_63d_35 | rolling_12m_min_calmar_like | observation | 0.36970864602812686 | >= 0.5 | fail |
| vol_throttle_nav_63d_35 | dominant_year_unique_ticker_count | observation | 20.0 | >= 10 | pass |
| vol_throttle_nav_63d_35 | dominant_year_avg_holding_count | observation | 4.583333333333333 | >= 3 | pass |
| vol_throttle_nav_63d_40 | leave_one_year_out_min_cagr | hard | 0.36177405887728376 | >= 0.2 | pass |
| vol_throttle_nav_63d_40 | leave_one_year_out_min_calmar | hard | 1.1164229559187369 | >= 1.0 | pass |
| vol_throttle_nav_63d_40 | top1_positive_month_share | hard | 0.16995723747758623 | <= 0.25 | pass |
| vol_throttle_nav_63d_40 | top3_positive_month_share | hard | 0.4023877877144685 | <= 0.5 | pass |
| vol_throttle_nav_63d_40 | max_ticker_abs_share | hard | 0.2296057331620555 | <= 0.3 | pass |
| vol_throttle_nav_63d_40 | max_ticker_month_weight | hard | 0.2 | <= 0.3 | pass |
| vol_throttle_nav_63d_40 | current_abs_return_share | observation | 0.616254753302019 | <= 0.55 | fail |
| vol_throttle_nav_63d_40 | top5_positive_month_share | observation | 0.5279781776592447 | <= 0.6 | pass |
| vol_throttle_nav_63d_40 | rolling_12m_min_calmar_like | observation | 0.598741091105613 | >= 0.5 | pass |
| vol_throttle_nav_63d_40 | dominant_year_unique_ticker_count | observation | 20.0 | >= 10 | pass |
| vol_throttle_nav_63d_40 | dominant_year_avg_holding_count | observation | 4.583333333333333 | >= 3 | pass |
| drawdown_throttle_nav | leave_one_year_out_min_cagr | hard | 0.3489269629517995 | >= 0.2 | pass |
| drawdown_throttle_nav | leave_one_year_out_min_calmar | hard | 1.4959035063488066 | >= 1.0 | pass |
| drawdown_throttle_nav | top1_positive_month_share | hard | 0.1866536688444841 | <= 0.25 | pass |
| drawdown_throttle_nav | top3_positive_month_share | hard | 0.4319289730103341 | <= 0.5 | pass |
| drawdown_throttle_nav | max_ticker_abs_share | hard | 0.20686437460972032 | <= 0.3 | pass |
| drawdown_throttle_nav | max_ticker_month_weight | hard | 0.2 | <= 0.3 | pass |
| drawdown_throttle_nav | current_abs_return_share | observation | 0.5087849948779355 | <= 0.55 | pass |
| drawdown_throttle_nav | top5_positive_month_share | observation | 0.5878888416219146 | <= 0.6 | pass |
| drawdown_throttle_nav | rolling_12m_min_calmar_like | observation | 0.23302317010331422 | >= 0.5 | fail |
| drawdown_throttle_nav | dominant_year_unique_ticker_count | observation | 20.0 | >= 10 | pass |
| drawdown_throttle_nav | dominant_year_avg_holding_count | observation | 4.583333333333333 | >= 3 | pass |
| softcap_15_plus_vol_throttle_30 | leave_one_year_out_min_cagr | hard | 0.3251605740354233 | >= 0.2 | pass |
| softcap_15_plus_vol_throttle_30 | leave_one_year_out_min_calmar | hard | 1.2635862354314769 | >= 1.0 | pass |
| softcap_15_plus_vol_throttle_30 | top1_positive_month_share | hard | 0.19607777830757772 | <= 0.25 | pass |
| softcap_15_plus_vol_throttle_30 | top3_positive_month_share | hard | 0.42385929109361603 | <= 0.5 | pass |
| softcap_15_plus_vol_throttle_30 | max_ticker_abs_share | hard | 0.1855668150925102 | <= 0.3 | pass |
| softcap_15_plus_vol_throttle_30 | max_ticker_month_weight | hard | 0.21250000000000002 | <= 0.3 | pass |
| softcap_15_plus_vol_throttle_30 | current_abs_return_share | observation | 0.532957066572327 | <= 0.55 | pass |
| softcap_15_plus_vol_throttle_30 | top5_positive_month_share | observation | 0.5504464797601542 | <= 0.6 | pass |
| softcap_15_plus_vol_throttle_30 | rolling_12m_min_calmar_like | observation | 0.35617496661607206 | >= 0.5 | fail |
| softcap_15_plus_vol_throttle_30 | dominant_year_unique_ticker_count | observation | 20.0 | >= 10 | pass |
| softcap_15_plus_vol_throttle_30 | dominant_year_avg_holding_count | observation | 4.583333333333333 | >= 3 | pass |
| softcap_15_plus_drawdown_throttle | leave_one_year_out_min_cagr | hard | 0.31389493711892014 | >= 0.2 | pass |
| softcap_15_plus_drawdown_throttle | leave_one_year_out_min_calmar | hard | 1.530325601158088 | >= 1.0 | pass |
| softcap_15_plus_drawdown_throttle | top1_positive_month_share | hard | 0.19698962792811553 | <= 0.25 | pass |
| softcap_15_plus_drawdown_throttle | top3_positive_month_share | hard | 0.45067625334485695 | <= 0.5 | pass |
| softcap_15_plus_drawdown_throttle | max_ticker_abs_share | hard | 0.16128961333004382 | <= 0.3 | pass |
| softcap_15_plus_drawdown_throttle | max_ticker_month_weight | hard | 0.2750000000000001 | <= 0.3 | pass |
| softcap_15_plus_drawdown_throttle | current_abs_return_share | observation | 0.5090383916752014 | <= 0.55 | pass |
| softcap_15_plus_drawdown_throttle | top5_positive_month_share | observation | 0.6126207159861653 | <= 0.6 | fail |
| softcap_15_plus_drawdown_throttle | rolling_12m_min_calmar_like | observation | 0.2765867047085134 | >= 0.5 | fail |
| softcap_15_plus_drawdown_throttle | dominant_year_unique_ticker_count | observation | 24.0 | >= 10 | pass |
| softcap_15_plus_drawdown_throttle | dominant_year_avg_holding_count | observation | 5.0 | >= 3 | pass |
| softcap_15_plus_vol_and_drawdown_30 | leave_one_year_out_min_cagr | hard | 0.26637743753959264 | >= 0.2 | pass |
| softcap_15_plus_vol_and_drawdown_30 | leave_one_year_out_min_calmar | hard | 1.2660282864140144 | >= 1.0 | pass |
| softcap_15_plus_vol_and_drawdown_30 | top1_positive_month_share | hard | 0.20751240371954702 | <= 0.25 | pass |
| softcap_15_plus_vol_and_drawdown_30 | top3_positive_month_share | hard | 0.4465907964288617 | <= 0.5 | pass |
| softcap_15_plus_vol_and_drawdown_30 | max_ticker_abs_share | hard | 0.1806256811502605 | <= 0.3 | pass |
| softcap_15_plus_vol_and_drawdown_30 | max_ticker_month_weight | hard | 0.21250000000000002 | <= 0.3 | pass |
| softcap_15_plus_vol_and_drawdown_30 | current_abs_return_share | observation | 0.5084137500238426 | <= 0.55 | pass |
| softcap_15_plus_vol_and_drawdown_30 | top5_positive_month_share | observation | 0.5899396797400711 | <= 0.6 | pass |
| softcap_15_plus_vol_and_drawdown_30 | rolling_12m_min_calmar_like | observation | 0.1960134662730343 | >= 0.5 | fail |
| softcap_15_plus_vol_and_drawdown_30 | dominant_year_unique_ticker_count | observation | 20.0 | >= 10 | pass |
| softcap_15_plus_vol_and_drawdown_30 | dominant_year_avg_holding_count | observation | 4.583333333333333 | >= 3 | pass |
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


## 8. 成本压力结果

50bps cost stress 已对每个候选独立 replay。Scale 摘要：

| candidate | avg_scale | min_scale | max_scale | scale_lt_100_day_count | scale_lte_75_day_count | scale_lte_50_day_count | scale_lte_25_day_count |
| --- | --- | --- | --- | --- | --- | --- | --- |
| baseline_no_overlay | 1.000000 | 1.000000 | 1.000000 | 0 | 0 | 0 | 0 |
| high_beta_softcap_15 | 1.000000 | 1.000000 | 1.000000 | 0 | 0 | 0 | 0 |
| vol_throttle_nav_63d_25 | 0.713468 | 0.394818 | 1.000000 | 496 | 386 | 63 | 0 |
| vol_throttle_nav_63d_30 | 0.819129 | 0.473781 | 1.000000 | 431 | 155 | 35 | 0 |
| vol_throttle_nav_63d_35 | 0.904283 | 0.552745 | 1.000000 | 361 | 63 | 0 | 0 |
| vol_throttle_nav_63d_40 | 0.955417 | 0.631708 | 1.000000 | 155 | 63 | 0 | 0 |
| drawdown_throttle_nav | 0.872174 | 0.250000 | 1.000000 | 168 | 168 | 84 | 42 |
| softcap_15_plus_vol_throttle_30 | 0.819129 | 0.473781 | 1.000000 | 431 | 155 | 35 | 0 |
| softcap_15_plus_drawdown_throttle | 0.872174 | 0.250000 | 1.000000 | 168 | 168 | 84 | 42 |
| softcap_15_plus_vol_and_drawdown_30 | 0.755689 | 0.250000 | 1.000000 | 431 | 288 | 118 | 42 |


## 9. 是否有 accepted_candidate

`True`

## 10. 是否有 strong_candidate

`False`

## 11. 是否替代 best

`False`

## 12. 是否允许进入 v9

`False`

## 13. 后续建议

暂停并由用户/ChatGPT 决定是否做 v8.1 final validation；不要进入 v9，不扩 universe。
