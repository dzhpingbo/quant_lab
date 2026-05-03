# US Stock Selection v8.1 Evolution Cycle 01

## 1. 本轮目标

新增 v8.1 gate-aware score 层，基于既有 v8 输出计算 concentration_penalty_score 并模拟 penalty weight 对排名分数的影响。

## 2. 本轮修改内容

- `quant_lab/us_stock_selection/v8_1_gate_metrics.py`
- `quant_lab/us_stock_selection/v8_1_gate_aware.py`
- `quant_lab/us_stock_selection/v8_1_reporting.py`
- `scripts/us_stock_selection/34_run_v8_1_gate_aware_improvement.py`

## 3. 本轮是否重跑策略

否。cycle 01 不重跑策略、不训练模型、不改交易结果，只复算 gate/score。

## 4. 输入数据

- `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\run_20260426_095958\v8_verdict.json`
- `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\run_20260426_095958\v8_paper_trading\paper_trading_metrics.csv`
- `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\v8_single_year_concentration_20260427_233246\annual_contribution.csv`
- `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\v8_single_year_concentration_20260427_233246\top_month_removed_metrics.csv`
- `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\v8_gate_calibration_review_20260428_111439\v8_concentration_metric_snapshot.json`
- `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\v8_gate_calibration_review_20260428_111439\v8_concentration_gate_comparison.csv`

## 5. 输出目录

`E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\v8_1_cycle_01_20260428_160436`

## 6. 与 v8 baseline 对比

Baseline: CAGR `0.6538182307494054`, Calmar `1.99152684432784`, MaxDD `-0.3282999838096962`, 50bps cost CAGR `0.5608428724606129`.

| candidate_id | penalty_weight | cagr | calmar | concentration_penalty_score | gate_aware_score | ranking_effect | baseline_cagr | baseline_calmar | delta_cagr | delta_calmar |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| v8_baseline_score_only | 0.000000 | 0.653818 | 1.991527 | 0.116159 | 1.258794 | baseline unchanged; score-layer diagnostic only | 0.653818 | 1.991527 | 0.000000 | 0.000000 |
| v8_baseline_score_only | 0.100000 | 0.653818 | 1.991527 | 0.116159 | 1.247178 | baseline unchanged; score-layer diagnostic only | 0.653818 | 1.991527 | 0.000000 | 0.000000 |
| v8_baseline_score_only | 0.200000 | 0.653818 | 1.991527 | 0.116159 | 1.235563 | baseline unchanged; score-layer diagnostic only | 0.653818 | 1.991527 | 0.000000 | 0.000000 |
| v8_baseline_score_only | 0.300000 | 0.653818 | 1.991527 | 0.116159 | 1.223947 | baseline unchanged; score-layer diagnostic only | 0.653818 | 1.991527 | 0.000000 | 0.000000 |
| v8_baseline_score_only | 0.400000 | 0.653818 | 1.991527 | 0.116159 | 1.212331 | baseline unchanged; score-layer diagnostic only | 0.653818 | 1.991527 | 0.000000 | 0.000000 |
| v8_baseline_score_only | 0.500000 | 0.653818 | 1.991527 | 0.116159 | 1.200715 | baseline unchanged; score-layer diagnostic only | 0.653818 | 1.991527 | 0.000000 | 0.000000 |


## 7. hard gates 结果

| gate_name | gate_layer | metric_value | threshold | pass_fail |
| --- | --- | --- | --- | --- |
| leave_one_year_out_min_cagr | hard | 0.527392 | >= 0.2 | pass |
| leave_one_year_out_min_calmar | hard | 1.617424 | >= 1.0 | pass |
| top1_positive_month_share | hard | 0.168601 | <= 0.25 | pass |
| top3_positive_month_share | hard | 0.389378 | <= 0.5 | pass |
| max_ticker_abs_share | hard | 0.223603 | <= 0.3 | pass |
| max_ticker_month_weight | hard | 0.200000 | <= 0.3 | pass |


## 8. observation gates 结果

| gate_name | gate_layer | metric_value | threshold | pass_fail |
| --- | --- | --- | --- | --- |
| current_abs_return_share | observation | 0.526027 | <= 0.55 | pass |
| top5_positive_month_share | observation | 0.541001 | <= 0.6 | pass |
| rolling_12m_min_calmar_like | observation | 0.636101 | >= 0.5 | pass |
| dominant_year_unique_ticker_count | observation | 20.000000 | >= 10 | pass |
| dominant_year_avg_holding_count | observation | 5.000000 | >= 3 | pass |


## 9. concentration_penalty_score

`0.1161588872156791`

## 10. execution stress 结果

`No new execution replay; inherited v8 execution stress and 50bps CAGR.`

## 11. 是否接受为 candidate

`False`

## 12. 是否替代当前 best

`False`

## 13. 下一轮自动计划

自动进入 cycle 02：在既有持仓基础上，对高 beta 暴露做 soft-cap 小样本 replay。

## 14. 是否触发暂停条件

`False`；原因：``
