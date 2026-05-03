# US Stock Selection v8.1 Evolution Cycle 02

## 1. 本轮目标

在既有 v8 持仓基础上，对 MSTR/TQQQ/QLD/SOXL 高 beta 暴露做 soft-cap overlay，并在最强/最弱 12M 窗口做小样本 replay。

## 2. 本轮修改内容

- `quant_lab/us_stock_selection/v8_1_gate_aware.py`
- `scripts/us_stock_selection/34_run_v8_1_gate_aware_improvement.py`

## 3. 本轮是否重跑策略

是，但仅为既有持仓 overlay 的小样本 replay；未训练模型、未重排全量候选、未运行 31b、未扩 universe。

## 4. 输入数据

- `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\run_20260426_095958\v8_paper_trading\monthly_holdings.csv`
- `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\v8_single_year_concentration_20260427_233246\rolling_12m_metrics.csv`
- `C:\Users\Administrator\.qlib\qlib_data\us_data_local_2026`

## 5. 输出目录

`E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\v8_1_cycle_02_20260428_160504`

## 6. 与 v8 baseline 对比

Baseline: CAGR `0.6538182307494054`, Calmar `1.99152684432784`, MaxDD `-0.3282999838096962`, 50bps cost CAGR `0.5608428724606129`.

| window_name | variant_id | start | end | total_return | cagr | max_drawdown | calmar | sharpe | sortino | volatility | win_rate | annual_turnover | exposure | worst_year | return_2022 | crash_2020_max_drawdown | daily_count | cost50_cagr | cost50_calmar | current_abs_return_share | leave_one_year_out_min_cagr | leave_one_year_out_min_calmar | top1_positive_month_share | top3_positive_month_share | top5_positive_month_share | rolling_12m_min_return | rolling_12m_min_calmar_like | rolling_12m_max_return | max_ticker_abs_share | max_ticker_month_weight | dominant_year_unique_ticker_count | dominant_year_avg_holding_count | high_beta_weight_share | rolling_12m_return_gap | concentration_penalty_score | year_return_concentration_penalty | top_month_concentration_penalty | ticker_exposure_penalty | rolling_12m_instability_penalty | high_beta_asset_penalty | delta_cagr_vs_window_baseline | delta_calmar_vs_window_baseline | delta_penalty_vs_window_baseline |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| strongest_12m | baseline_rebuilt | 2024-11-01 | 2025-10-31 | 1.363265 | 1.379581 | -0.328300 | 4.202198 | 2.233813 | 4.317324 | 0.429124 | 0.556000 | 14.515200 | 1.000000 | 0.291001 | 0.000000 | 0.000000 | 250 | 1.227035 | 3.494084 | 0.740542 | 1.073056 | 3.290885 | 0.258977 | 0.595593 | 0.828491 | 1.363265 | 4.202198 | 1.363265 | 0.249098 | 0.200000 | 24.000000 | 5.000000 | 0.180000 | 0.000000 | 0.445593 | 1.000000 | 0.782374 | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 |
| strongest_12m | high_beta_softcap_15 | 2024-11-01 | 2025-10-31 | 1.380673 | 1.397250 | -0.313601 | 4.455509 | 2.284218 | 4.404581 | 0.421551 | 0.564000 | 14.590800 | 1.000000 | 0.286926 | 0.000000 | 0.000000 | 250 | 1.242779 | 3.793166 | 0.747606 | 1.099468 | 3.505950 | 0.265277 | 0.604836 | 0.839440 | 1.380673 | 4.455509 | 1.380673 | 0.258567 | 0.275000 | 24.000000 | 5.000000 | 0.135000 | 0.000000 | 0.466258 | 1.000000 | 0.819345 | 0.057110 | 0.000000 | 0.000000 | 0.017669 | 0.253311 | 0.020665 |
| strongest_12m | high_beta_softcap_10 | 2024-11-01 | 2025-10-31 | 1.354988 | 1.371181 | -0.301050 | 4.554658 | 2.310580 | 4.430364 | 0.409977 | 0.560000 | 14.464800 | 0.983600 | 0.282154 | 0.000000 | 0.000000 | 250 | 1.219724 | 3.888592 | 0.747829 | 1.081491 | 3.592393 | 0.274320 | 0.608364 | 0.848813 | 1.354988 | 4.554658 | 1.354988 | 0.272818 | 0.300000 | 24.000000 | 5.000000 | 0.090000 | 0.000000 | 0.488788 | 1.000000 | 0.833456 | 0.152118 | 0.000000 | 0.000000 | -0.008401 | 0.352461 | 0.043194 |
| weakest_12m | baseline_rebuilt | 2024-04-01 | 2025-03-31 | 0.193736 | 0.194578 | -0.282641 | 0.688429 | 0.644428 | 1.104897 | 0.400312 | 0.525896 | 13.654183 | 1.000000 | -0.136433 | 0.000000 | 0.000000 | 251 | 0.121921 | 0.425228 | 0.737004 | -0.459937 | -2.082679 | 0.455046 | 0.802593 | 0.972440 | 0.193736 | 0.688429 | 0.193736 | 0.202877 | 0.200000 | 23.000000 | 5.000000 | 0.165737 | 0.000000 | 0.562314 | 1.000000 | 1.000000 | 0.000000 | 0.311571 | 0.000000 | 0.000000 | 0.000000 | 0.000000 |
| weakest_12m | high_beta_softcap_15 | 2024-04-01 | 2025-03-31 | 0.201329 | 0.202207 | -0.275311 | 0.734470 | 0.673732 | 1.149988 | 0.381444 | 0.525896 | 13.654183 | 1.000000 | -0.120236 | 0.000000 | 0.000000 | 251 | 0.129049 | 0.462123 | 0.752473 | -0.416100 | -1.981899 | 0.454794 | 0.805810 | 0.970075 | 0.201329 | 0.734470 | 0.201329 | 0.213809 | 0.212500 | 23.000000 | 5.000000 | 0.124303 | 0.000000 | 0.553106 | 1.000000 | 1.000000 | 0.000000 | 0.265530 | 0.000000 | 0.007629 | 0.046041 | -0.009208 |
| weakest_12m | high_beta_softcap_10 | 2024-04-01 | 2025-03-31 | 0.207370 | 0.208277 | -0.270578 | 0.769748 | 0.700828 | 1.192401 | 0.365296 | 0.533865 | 13.654183 | 1.000000 | -0.103858 | 0.000000 | 0.000000 | 251 | 0.134712 | 0.490993 | 0.769796 | -0.369068 | -1.854676 | 0.454922 | 0.809505 | 0.967302 | 0.207370 | 0.769748 | 0.207370 | 0.224564 | 0.225000 | 23.000000 | 5.000000 | 0.082869 | 0.000000 | 0.546050 | 1.000000 | 1.000000 | 0.000000 | 0.230252 | 0.000000 | 0.013699 | 0.081319 | -0.016264 |


## 7. hard gates 结果

| window_name | variant_id | gate_name | gate_layer | metric_value | threshold | pass_fail |
| --- | --- | --- | --- | --- | --- | --- |
| strongest_12m | baseline_rebuilt | leave_one_year_out_min_cagr | hard | 1.073056 | >= 0.2 | pass |
| strongest_12m | baseline_rebuilt | leave_one_year_out_min_calmar | hard | 3.290885 | >= 1.0 | pass |
| strongest_12m | baseline_rebuilt | top1_positive_month_share | hard | 0.258977 | <= 0.25 | fail |
| strongest_12m | baseline_rebuilt | top3_positive_month_share | hard | 0.595593 | <= 0.5 | fail |
| strongest_12m | baseline_rebuilt | max_ticker_abs_share | hard | 0.249098 | <= 0.3 | pass |
| strongest_12m | baseline_rebuilt | max_ticker_month_weight | hard | 0.200000 | <= 0.3 | pass |
| strongest_12m | high_beta_softcap_15 | leave_one_year_out_min_cagr | hard | 1.099468 | >= 0.2 | pass |
| strongest_12m | high_beta_softcap_15 | leave_one_year_out_min_calmar | hard | 3.505950 | >= 1.0 | pass |
| strongest_12m | high_beta_softcap_15 | top1_positive_month_share | hard | 0.265277 | <= 0.25 | fail |
| strongest_12m | high_beta_softcap_15 | top3_positive_month_share | hard | 0.604836 | <= 0.5 | fail |
| strongest_12m | high_beta_softcap_15 | max_ticker_abs_share | hard | 0.258567 | <= 0.3 | pass |
| strongest_12m | high_beta_softcap_15 | max_ticker_month_weight | hard | 0.275000 | <= 0.3 | pass |
| strongest_12m | high_beta_softcap_10 | leave_one_year_out_min_cagr | hard | 1.081491 | >= 0.2 | pass |
| strongest_12m | high_beta_softcap_10 | leave_one_year_out_min_calmar | hard | 3.592393 | >= 1.0 | pass |
| strongest_12m | high_beta_softcap_10 | top1_positive_month_share | hard | 0.274320 | <= 0.25 | fail |
| strongest_12m | high_beta_softcap_10 | top3_positive_month_share | hard | 0.608364 | <= 0.5 | fail |
| strongest_12m | high_beta_softcap_10 | max_ticker_abs_share | hard | 0.272818 | <= 0.3 | pass |
| strongest_12m | high_beta_softcap_10 | max_ticker_month_weight | hard | 0.300000 | <= 0.3 | pass |
| weakest_12m | baseline_rebuilt | leave_one_year_out_min_cagr | hard | -0.459937 | >= 0.2 | fail |
| weakest_12m | baseline_rebuilt | leave_one_year_out_min_calmar | hard | -2.082679 | >= 1.0 | fail |
| weakest_12m | baseline_rebuilt | top1_positive_month_share | hard | 0.455046 | <= 0.25 | fail |
| weakest_12m | baseline_rebuilt | top3_positive_month_share | hard | 0.802593 | <= 0.5 | fail |
| weakest_12m | baseline_rebuilt | max_ticker_abs_share | hard | 0.202877 | <= 0.3 | pass |
| weakest_12m | baseline_rebuilt | max_ticker_month_weight | hard | 0.200000 | <= 0.3 | pass |
| weakest_12m | high_beta_softcap_15 | leave_one_year_out_min_cagr | hard | -0.416100 | >= 0.2 | fail |
| weakest_12m | high_beta_softcap_15 | leave_one_year_out_min_calmar | hard | -1.981899 | >= 1.0 | fail |
| weakest_12m | high_beta_softcap_15 | top1_positive_month_share | hard | 0.454794 | <= 0.25 | fail |
| weakest_12m | high_beta_softcap_15 | top3_positive_month_share | hard | 0.805810 | <= 0.5 | fail |
| weakest_12m | high_beta_softcap_15 | max_ticker_abs_share | hard | 0.213809 | <= 0.3 | pass |
| weakest_12m | high_beta_softcap_15 | max_ticker_month_weight | hard | 0.212500 | <= 0.3 | pass |


## 8. observation gates 结果

| window_name | variant_id | gate_name | gate_layer | metric_value | threshold | pass_fail |
| --- | --- | --- | --- | --- | --- | --- |
| strongest_12m | baseline_rebuilt | current_abs_return_share | observation | 0.740542 | <= 0.55 | fail |
| strongest_12m | baseline_rebuilt | top5_positive_month_share | observation | 0.828491 | <= 0.6 | fail |
| strongest_12m | baseline_rebuilt | rolling_12m_min_calmar_like | observation | 4.202198 | >= 0.5 | pass |
| strongest_12m | baseline_rebuilt | dominant_year_unique_ticker_count | observation | 24.000000 | >= 10 | pass |
| strongest_12m | baseline_rebuilt | dominant_year_avg_holding_count | observation | 5.000000 | >= 3 | pass |
| strongest_12m | high_beta_softcap_15 | current_abs_return_share | observation | 0.747606 | <= 0.55 | fail |
| strongest_12m | high_beta_softcap_15 | top5_positive_month_share | observation | 0.839440 | <= 0.6 | fail |
| strongest_12m | high_beta_softcap_15 | rolling_12m_min_calmar_like | observation | 4.455509 | >= 0.5 | pass |
| strongest_12m | high_beta_softcap_15 | dominant_year_unique_ticker_count | observation | 24.000000 | >= 10 | pass |
| strongest_12m | high_beta_softcap_15 | dominant_year_avg_holding_count | observation | 5.000000 | >= 3 | pass |
| strongest_12m | high_beta_softcap_10 | current_abs_return_share | observation | 0.747829 | <= 0.55 | fail |
| strongest_12m | high_beta_softcap_10 | top5_positive_month_share | observation | 0.848813 | <= 0.6 | fail |
| strongest_12m | high_beta_softcap_10 | rolling_12m_min_calmar_like | observation | 4.554658 | >= 0.5 | pass |
| strongest_12m | high_beta_softcap_10 | dominant_year_unique_ticker_count | observation | 24.000000 | >= 10 | pass |
| strongest_12m | high_beta_softcap_10 | dominant_year_avg_holding_count | observation | 5.000000 | >= 3 | pass |
| weakest_12m | baseline_rebuilt | current_abs_return_share | observation | 0.737004 | <= 0.55 | fail |
| weakest_12m | baseline_rebuilt | top5_positive_month_share | observation | 0.972440 | <= 0.6 | fail |
| weakest_12m | baseline_rebuilt | rolling_12m_min_calmar_like | observation | 0.688429 | >= 0.5 | pass |
| weakest_12m | baseline_rebuilt | dominant_year_unique_ticker_count | observation | 23.000000 | >= 10 | pass |
| weakest_12m | baseline_rebuilt | dominant_year_avg_holding_count | observation | 5.000000 | >= 3 | pass |
| weakest_12m | high_beta_softcap_15 | current_abs_return_share | observation | 0.752473 | <= 0.55 | fail |
| weakest_12m | high_beta_softcap_15 | top5_positive_month_share | observation | 0.970075 | <= 0.6 | fail |
| weakest_12m | high_beta_softcap_15 | rolling_12m_min_calmar_like | observation | 0.734470 | >= 0.5 | pass |
| weakest_12m | high_beta_softcap_15 | dominant_year_unique_ticker_count | observation | 23.000000 | >= 10 | pass |
| weakest_12m | high_beta_softcap_15 | dominant_year_avg_holding_count | observation | 5.000000 | >= 3 | pass |
| weakest_12m | high_beta_softcap_10 | current_abs_return_share | observation | 0.769796 | <= 0.55 | fail |
| weakest_12m | high_beta_softcap_10 | top5_positive_month_share | observation | 0.967302 | <= 0.6 | fail |
| weakest_12m | high_beta_softcap_10 | rolling_12m_min_calmar_like | observation | 0.769748 | >= 0.5 | pass |
| weakest_12m | high_beta_softcap_10 | dominant_year_unique_ticker_count | observation | 23.000000 | >= 10 | pass |
| weakest_12m | high_beta_softcap_10 | dominant_year_avg_holding_count | observation | 5.000000 | >= 3 | pass |


## 9. concentration_penalty_score

`0.54605041981761`

## 10. execution stress 结果

`Sample replay evaluated 5bps+5bps and 50bps+5bps cost on existing holdings overlays.`

## 11. 是否接受为 candidate

`True`

## 12. 是否替代当前 best

`False`

## 13. 下一轮自动计划

暂停：cycle 03 需要决定是否接受 soft-cap 交易假设并批准更接近完整 replay 的验证。

## 14. 是否触发暂停条件

`True`；原因：`Cycle 03 would require broader/full replay or accepting a stability-vs-return tradeoff, which is a research decision.`
