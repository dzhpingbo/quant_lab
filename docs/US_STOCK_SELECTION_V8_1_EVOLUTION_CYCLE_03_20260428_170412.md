# US Stock Selection v8.1 Evolution Cycle 03

## 1. 本轮目标

在完整 v8 区间，对既有 v8 monthly holdings 应用 high-beta soft-cap overlay replay，判断 overlay 是否具备全周期价值。

## 2. 为什么批准 cycle 03

Cycle 02 在 weakest 12M sample 中显示 high_beta_softcap_10 对 CAGR、Calmar、MaxDD 和 high-beta exposure 有局部改善，但 sample 的 top-month concentration 和 leave-one-year-out 仍严重失败。因此本轮只批准更接近完整区间的 overlay replay，不进入 v9。

## 3. overlay 真实实现说明

- High-beta ticker 列表：`MSTR, QLD, SOXL, TQQQ`
- Soft cap 类型：对每个 high-beta ticker 单独设权重上限，不是 high-beta 总权重 cap。
- 权重处理：超过 cap 的权重释放后，按剩余 room 分配给同日非 high-beta active holdings，单个非 high-beta ticker 上限为 0.30。
- 现金残留：仅当非 high-beta active holdings 没有足够 room 时才可能残留；本轮输出了 cash residual。
- Gross exposure：目标是在 receiver room 足够时保持 active gross exposure = 1。
- Turnover：只会改变已有 v8 execution date 的权重 delta，不新增 rebalance date。
- 是否影响原 v8 选股信号：否。

## 4. 是否重训模型

否。

## 5. 是否改变选股信号

否。

## 6. 是否只是 overlay replay

是。候选为：`baseline_no_overlay, high_beta_softcap_10, high_beta_softcap_15, high_beta_softcap_20`。

## 7. full-period 结果

v8 baseline reference: CAGR `0.6538182307494054`, Calmar `1.99152684432784`, MaxDD `-0.32829998380969627`, 50bps cost CAGR `0.5608428724606129`, verdict `credible_but_execution_sensitive`, allow_enter_v9 `False`.

| variant_id | cagr | cost50_cagr | calmar | cost50_calmar | max_drawdown | annual_turnover | trade_count | average_high_beta_weight_share | max_high_beta_weight_share | concentration_penalty_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline_no_overlay | 0.653818 | 0.560843 | 1.991527 | 1.597047 | -0.328300 | 12.709565 | 145 | 0.145848 | 0.600000 | 0.116159 |
| high_beta_softcap_10 | 0.550519 | 0.462913 | 1.828661 | 1.475810 | -0.301050 | 12.775304 | 150 | 0.072924 | 0.300000 | 0.174374 |
| high_beta_softcap_15 | 0.608302 | 0.517345 | 1.939737 | 1.579022 | -0.313601 | 12.786261 | 150 | 0.109386 | 0.450000 | 0.095756 |
| high_beta_softcap_20 | 0.653818 | 0.560843 | 1.991527 | 1.597047 | -0.328300 | 12.709565 | 145 | 0.145848 | 0.600000 | 0.116159 |


## 8. weakest 12M 结果

| variant_id | window_start | window_end | cagr | max_drawdown | calmar | cost50_cagr | cost50_calmar | high_beta_weight_share | top1_positive_month_share | top3_positive_month_share | top5_positive_month_share | leave_one_year_out_like_min_cagr | leave_one_year_out_like_min_calmar |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline_no_overlay | 2024-04-01 | 2025-03-31 | 0.194578 | -0.282641 | 0.688429 | 0.121921 | 0.425228 | 0.165737 | 0.455046 | 0.802593 | 0.972440 | -0.459937 | -2.082679 |
| high_beta_softcap_10 | 2024-04-01 | 2025-03-31 | 0.208277 | -0.270578 | 0.769748 | 0.134712 | 0.490993 | 0.082869 | 0.454922 | 0.809505 | 0.967302 | -0.369068 | -1.854676 |
| high_beta_softcap_15 | 2024-04-01 | 2025-03-31 | 0.202207 | -0.275311 | 0.734470 | 0.129049 | 0.462123 | 0.124303 | 0.454794 | 0.805810 | 0.970075 | -0.416100 | -1.981899 |
| high_beta_softcap_20 | 2024-04-01 | 2025-03-31 | 0.194578 | -0.282641 | 0.688429 | 0.121921 | 0.425228 | 0.165737 | 0.455046 | 0.802593 | 0.972440 | -0.459937 | -2.082679 |


## 9. concentration gate 结果

| variant_id | gate_name | gate_layer | metric_value | threshold | pass_fail |
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
| high_beta_softcap_10 | leave_one_year_out_min_cagr | hard | 0.41117389861335507 | >= 0.2 | pass |
| high_beta_softcap_10 | leave_one_year_out_min_calmar | hard | 1.5196121465822967 | >= 1.0 | pass |
| high_beta_softcap_10 | top1_positive_month_share | hard | 0.18531709144740097 | <= 0.25 | pass |
| high_beta_softcap_10 | top3_positive_month_share | hard | 0.4127800509910332 | <= 0.5 | pass |
| high_beta_softcap_10 | max_ticker_abs_share | hard | 0.18658139384472042 | <= 0.3 | pass |
| high_beta_softcap_10 | max_ticker_month_weight | hard | 0.3 | <= 0.3 | pass |
| high_beta_softcap_10 | current_abs_return_share | observation | 0.5645381486362246 | <= 0.55 | fail |
| high_beta_softcap_10 | top5_positive_month_share | observation | 0.5752157314961812 | <= 0.6 | pass |
| high_beta_softcap_10 | rolling_12m_min_calmar_like | observation | 0.7298465134488573 | >= 0.5 | pass |
| high_beta_softcap_10 | dominant_year_unique_ticker_count | observation | 24.0 | >= 10 | pass |
| high_beta_softcap_10 | dominant_year_avg_holding_count | observation | 5.0 | >= 3 | pass |
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
| high_beta_softcap_20 | leave_one_year_out_min_cagr | hard | 0.527391568038992 | >= 0.2 | pass |
| high_beta_softcap_20 | leave_one_year_out_min_calmar | hard | 1.617423567224566 | >= 1.0 | pass |
| high_beta_softcap_20 | top1_positive_month_share | hard | 0.16860106413893422 | <= 0.25 | pass |
| high_beta_softcap_20 | top3_positive_month_share | hard | 0.3893784301688419 | <= 0.5 | pass |
| high_beta_softcap_20 | max_ticker_abs_share | hard | 0.22360323143558838 | <= 0.3 | pass |
| high_beta_softcap_20 | max_ticker_month_weight | hard | 0.2 | <= 0.3 | pass |
| high_beta_softcap_20 | current_abs_return_share | observation | 0.5260274868858267 | <= 0.55 | pass |
| high_beta_softcap_20 | top5_positive_month_share | observation | 0.5410013606918052 | <= 0.6 | pass |
| high_beta_softcap_20 | rolling_12m_min_calmar_like | observation | 0.6361012879701722 | >= 0.5 | pass |
| high_beta_softcap_20 | dominant_year_unique_ticker_count | observation | 20.0 | >= 10 | pass |
| high_beta_softcap_20 | dominant_year_avg_holding_count | observation | 4.583333333333333 | >= 3 | pass |
| high_beta_softcap_10 | full_period_cagr_ge_20 | acceptance |  |  | pass |
| high_beta_softcap_10 | full_period_cost50_cagr_ge_20 | acceptance |  |  | pass |
| high_beta_softcap_10 | full_period_calmar_ge_1 | acceptance |  |  | pass |
| high_beta_softcap_10 | full_period_calmar_ge_85pct_v8 | acceptance |  |  | pass |
| high_beta_softcap_10 | maxdd_not_significantly_worse_than_v8 | acceptance |  |  | pass |
| high_beta_softcap_10 | leave_one_year_out_min_cagr_ge_20 | acceptance |  |  | pass |
| high_beta_softcap_10 | leave_one_year_out_min_calmar_ge_1 | acceptance |  |  | pass |
| high_beta_softcap_10 | top1_positive_month_share_lte_25 | acceptance |  |  | pass |
| high_beta_softcap_10 | top3_positive_month_share_lte_50 | acceptance |  |  | pass |
| high_beta_softcap_10 | max_ticker_abs_share_lte_30 | acceptance |  |  | pass |
| high_beta_softcap_10 | max_ticker_month_weight_lte_30 | acceptance |  |  | pass |
| high_beta_softcap_10 | high_beta_weight_share_meaningfully_down | acceptance |  |  | pass |
| high_beta_softcap_10 | gross_exposure_normal | acceptance |  |  | fail |
| high_beta_softcap_10 | accepted_candidate | acceptance |  |  | fail |
| high_beta_softcap_15 | full_period_cagr_ge_20 | acceptance |  |  | pass |
| high_beta_softcap_15 | full_period_cost50_cagr_ge_20 | acceptance |  |  | pass |
| high_beta_softcap_15 | full_period_calmar_ge_1 | acceptance |  |  | pass |
| high_beta_softcap_15 | full_period_calmar_ge_85pct_v8 | acceptance |  |  | pass |
| high_beta_softcap_15 | maxdd_not_significantly_worse_than_v8 | acceptance |  |  | pass |
| high_beta_softcap_15 | leave_one_year_out_min_cagr_ge_20 | acceptance |  |  | pass |
| high_beta_softcap_15 | leave_one_year_out_min_calmar_ge_1 | acceptance |  |  | pass |
| high_beta_softcap_15 | top1_positive_month_share_lte_25 | acceptance |  |  | pass |
| high_beta_softcap_15 | top3_positive_month_share_lte_50 | acceptance |  |  | pass |
| high_beta_softcap_15 | max_ticker_abs_share_lte_30 | acceptance |  |  | pass |
| high_beta_softcap_15 | max_ticker_month_weight_lte_30 | acceptance |  |  | pass |
| high_beta_softcap_15 | high_beta_weight_share_meaningfully_down | acceptance |  |  | pass |
| high_beta_softcap_15 | gross_exposure_normal | acceptance |  |  | pass |
| high_beta_softcap_15 | accepted_candidate | acceptance |  |  | pass |
| high_beta_softcap_20 | full_period_cagr_ge_20 | acceptance |  |  | pass |
| high_beta_softcap_20 | full_period_cost50_cagr_ge_20 | acceptance |  |  | pass |
| high_beta_softcap_20 | full_period_calmar_ge_1 | acceptance |  |  | pass |
| high_beta_softcap_20 | full_period_calmar_ge_85pct_v8 | acceptance |  |  | pass |
| high_beta_softcap_20 | maxdd_not_significantly_worse_than_v8 | acceptance |  |  | pass |
| high_beta_softcap_20 | leave_one_year_out_min_cagr_ge_20 | acceptance |  |  | pass |
| high_beta_softcap_20 | leave_one_year_out_min_calmar_ge_1 | acceptance |  |  | pass |
| high_beta_softcap_20 | top1_positive_month_share_lte_25 | acceptance |  |  | pass |


## 10. execution stress / cost 结果

50bps cost replay 使用 `cost_bps=50.0` 且 slippage 沿用 `5.0` bps。Turnover 摘要：

| variant_id | trade_day_count | trade_count | total_turnover | average_trade_day_turnover | max_daily_turnover | annualized_turnover_from_weight_deltas |
| --- | --- | --- | --- | --- | --- | --- |
| baseline_no_overlay | 18 | 145 | 29.000000 | 1.611111 | 2.000000 | 12.709565 |
| high_beta_softcap_10 | 18 | 150 | 29.150000 | 1.619444 | 2.000000 | 12.775304 |
| high_beta_softcap_15 | 18 | 150 | 29.175000 | 1.620833 | 2.000000 | 12.786261 |
| high_beta_softcap_20 | 18 | 145 | 29.000000 | 1.611111 | 2.000000 | 12.709565 |


## 11. 是否接受 candidate

`True`。最优 overlay 观察候选：`high_beta_softcap_15`。

## 12. 是否替代当前 best

`False`。Cycle 03 被要求完成后暂停，不自动替代 v8 baseline。

## 13. 是否允许进入 v9

`False`。

## 14. 后续建议

暂停并由用户/ChatGPT 决定是否做 v8.1 final validation；不要进入 v9，不扩 universe。
