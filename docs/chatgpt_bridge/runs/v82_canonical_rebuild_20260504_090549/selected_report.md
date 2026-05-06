# v8.2 Canonical Rebuild Report

## Verdict

- classification: `formal_v82_valid_ready_for_formal_v9`
- v82_reported_vs_recomputed_consistent: `True`
- formal_v82_gate_pass: `True`
- formal_v9_run_plan_generated: `True`
- allow_execute_formal_v9: `False`
- allow_enter_v10: `False`
- requires_human_review: `False`
- zip_path: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\us_stock_selection_v82_canonical_rebuild_20260504_090549.zip`

## Required Answers

1. v8.2 原报告是否可信？
   - 是。按 canonical Qlib provider bin + frozen score audit + T+1 + 5bps/5bps 重新复算后，与原报告在阈值内一致。
2. v8.2 本地价格+持仓复算为何有差异？
   - 根因是 `price_source_mismatch`。上一轮使用 `data/unified_ohlcv/.../prices` 复算；v8.2 原始引擎使用 local Qlib provider `$close`，两者在若干 ticker/日期上不同。
3. 差异来自价格、持仓、执行日、成本、YTD cap、derisk、还是 stale report？
   - 主要来自价格源；canonical holdings、执行日、成本、YTD cap、derisk 与原引擎一致。没有证据表明 v8.2 原报告是 stale metric。
4. formal_v82_baseline 重新跑后是否仍通过 gate？
   - `True`。
5. v8.2 是否仍可作为 formal v9 的基准？
   - 是，但只能以 canonical source definition 为准。
6. PLTR/SNOW baseline reproduction only 问题是否已隔离？
   - 是。formal replay 禁止 loaded reproduction / benchmark-only rows 污染正式指标，并定义同一套动态 eligibility rule。
7. v9 原始结果是否继续废弃？
   - 是。
8. formal v9 应如何重跑？
   - 使用 `canonical_replay_engine.py`、同一 Qlib provider、同一 eligibility rule、同一 train/predict/rebalance/execution/gate 口径，生成独立 formal v9 score/rank audit 后重跑。
9. 是否允许执行 formal v9？
   - 当前不允许；本轮默认 `explicit_allow_run_formal_v9=false`，只生成 run plan。
10. 是否允许进入 v10？
    - 不允许。
11. 是否仍需人工审阅？
    - `False`；即使 classification ready，也需要先审阅 formal v9 plan。

## Reported vs Recomputed

| strategy_id               |   reported_cagr |   recomputed_cagr |   diff_cagr | pass_cagr   |   reported_max_drawdown |   recomputed_max_drawdown |   diff_max_drawdown | pass_max_drawdown   |   reported_calmar |   recomputed_calmar |   diff_calmar | pass_calmar   |   reported_single_year_share |   recomputed_single_year_share |   diff_single_year_share | pass_single_year_share   |   reported_top_ticker_share |   recomputed_top_ticker_share |   diff_top_ticker_share | pass_top_ticker_share   | reported_top_ticker   | recomputed_top_ticker   | pass_recalc_check   |   local_unified_recomputed_cagr |   local_unified_recomputed_calmar |   local_unified_recomputed_maxdd | canonical_price_source                                    | noncanonical_price_source                                               |
|:--------------------------|----------------:|------------------:|------------:|:------------|------------------------:|--------------------------:|--------------------:|:--------------------|------------------:|--------------------:|--------------:|:--------------|-----------------------------:|-------------------------------:|-------------------------:|:-------------------------|----------------------------:|------------------------------:|------------------------:|:------------------------|:----------------------|:------------------------|:--------------------|--------------------------------:|----------------------------------:|---------------------------------:|:----------------------------------------------------------|:------------------------------------------------------------------------|
| top5_ytdcap80p_derisk100p |        0.642126 |          0.642126 |  2.8429e-07 | True        |               -0.392985 |                 -0.392985 |        -2.17501e-08 | True                |           1.63397 |             1.63397 |   6.32977e-07 | True          |                     0.496839 |                       0.496839 |             -6.29398e-08 | True                     |                    0.137939 |                      0.137939 |            -2.52613e-08 | True                    | INTC                  | INTC                    | True                |                        0.817481 |                           2.08018 |                        -0.392985 | C:\Users\Administrator\.qlib\qlib_data\us_data_local_2026 | E:\dzhwork\quant\quant_lab\data\unified_ohlcv\us_stock_selection\prices |

## Difference Root Cause

| issue_type                  | affected_metric                     | evidence_file                                                                                                                                  | evidence_row                          | description                                                                                                                                                                                                          | severity   | fix_recommendation                                                                                                                           |
|:----------------------------|:------------------------------------|:-----------------------------------------------------------------------------------------------------------------------------------------------|:--------------------------------------|:---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|:-----------|:---------------------------------------------------------------------------------------------------------------------------------------------|
| price_source_mismatch       | previous local price recompute only | E:\dzhwork\quant\quant_lab\data\unified_ohlcv\us_stock_selection\prices                                                                        | local_unified_recomputed_vs_canonical | Canonical Qlib provider bin replay matches v8.2 reported metrics within tolerance; the prior mismatch came from recomputing v8.2 holdings on noncanonical unified parquet prices.                                    | medium     | Use local Qlib provider close bin as formal source-of-truth for v8.2 and formal v9; keep unified parquet replay only as diagnostic evidence. |
| baseline_pollution_isolated | formal_v82/formal_v9 gate           | E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\score_provenance_alignment_audit_20260504_084307\baseline_exception_pollution_detail.csv | PLTR/SNOW policy                      | Prior PLTR/SNOW pollution came from baseline reproduction / v9 local replay classification. Formal replay defines an explicit dynamic eligibility rule and blocks loaded-reproduction-only rows from formal metrics. | medium     | Formal v9 must apply the same dynamic min-history rule and isolate PLTR/SNOW as formal candidates only if independently eligible.            |

## Formal v82 Metrics

| strategy_id               | feature_set   | model    | label    | portfolio                 | rebalance   | execution   |   cost_bps |   slippage_bps |   max_weight |   ytd_return_cap |   derisk_after_trigger |   single_year_share |   top_contribution_year |   top_contribution_year_abs_share | top_ticker   |   top_ticker_share |   cost50_t1_cagr |   cost50_t1_calmar |   remove_top_year_cagr |   remove_top_year_calmar |   remove_top_ticker_cagr |   remove_top_ticker_calmar |   t2_cagr |   t2_calmar |   total_return |     cagr |   max_drawdown |   calmar |   sharpe |   sortino |   volatility |   win_rate |   annual_turnover |   exposure |   worst_year |   return_2022 |   crash_2020_max_drawdown |   daily_count | formal_gate_pass   | inherited_v82_allow_enter_v9   |
|:--------------------------|:--------------|:---------|:---------|:--------------------------|:------------|:------------|-----------:|---------------:|-------------:|-----------------:|-----------------------:|--------------------:|------------------------:|----------------------------------:|:-------------|-------------------:|-----------------:|-------------------:|-----------------------:|-------------------------:|-------------------------:|---------------------------:|----------:|------------:|---------------:|---------:|---------------:|---------:|---------:|----------:|-------------:|-----------:|------------------:|-----------:|-------------:|--------------:|--------------------------:|--------------:|:-------------------|:-------------------------------|
| top5_ytdcap80p_derisk100p | Alpha360      | LGBModel | label_5d | top5_ytdcap80p_derisk100p | monthly     | T+1         |          5 |              5 |          0.2 |              0.8 |                      1 |            0.496839 |                    2024 |                          0.496839 | INTC         |           0.137939 |         0.540613 |            1.34535 |               0.521587 |                  1.32724 |                 0.489654 |                    1.32651 |  0.616055 |     1.56502 |        2.10101 | 0.642126 |      -0.392985 |  1.63397 |  1.46341 |    2.5878 |     0.390596 |   0.443478 |            14.112 |   0.810435 |   -0.0389642 |             0 |                         0 |           575 | True               | True                           |

## Formal v82 Gate Detail

| gate                            |    value |   threshold | operator   | pass   |
|:--------------------------------|---------:|------------:|:-----------|:-------|
| cagr_20                         | 0.642126 |         0.2 | >=         | True   |
| calmar_1                        | 1.63397  |         1   | >=         | True   |
| cost50_t1_cagr_20               | 0.540613 |         0.2 | >=         | True   |
| cost50_t1_calmar_1              | 1.34535  |         1   | >=         | True   |
| single_year_share_50            | 0.496839 |         0.5 | <=         | True   |
| top_ticker_share_30             | 0.137939 |         0.3 | <=         | True   |
| remove_top_year_cagr_20         | 0.521587 |         0.2 | >=         | True   |
| remove_top_year_calmar_1        | 1.32724  |         1   | >=         | True   |
| remove_top_ticker_cagr_20       | 0.489654 |         0.2 | >=         | True   |
| remove_top_ticker_calmar_1      | 1.32651  |         1   | >=         | True   |
| no_leakage                      | 1        |         1   | is         | True   |
| no_score_provenance_mismatch    | 1        |         1   | is         | True   |
| no_baseline_exception_pollution | 1        |         1   | is         | True   |

## Formal v9 Blockers

| blocker                            | severity      | description                                                                    | resolution                                                                     |
|:-----------------------------------|:--------------|:-------------------------------------------------------------------------------|:-------------------------------------------------------------------------------|
| explicit_allow_run_formal_v9_false | control_block | This round only generates a formal v9 run plan; it does not execute formal v9. | Set explicit_allow_run_formal_v9=true in a future controlled run after review. |
