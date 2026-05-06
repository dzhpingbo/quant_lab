# Score Provenance Alignment Audit Report

## Executive verdict

- classification: `score_provenance_mismatch`
- score_provenance_consistent: `False`
- method_window_consistent: `False`
- return_reconstruction_consistent: `False`
- baseline_exception_pollution_found: `True`
- requires_human_review: `True`
- allow_enter_v10: `False`
- allow_trade_execution: `False`
- zip_path: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\us_stock_selection_score_provenance_alignment_audit_20260504_084307.zip`

本轮结论：v8.2 冻结主线与 v9 local replay 不是可直接等价比较的 score provenance。v9 原始 full-window 指标应废弃；unified replay 只适合作为审计证据，不足以作为正式 v9 通过结果。

## Required answers

1. v8.2 与 v9 的 score 是不是同源？
   - 不是。v8.2 来自 v8.1 Alpha360/LGBModel runtime score trail；v9 local replay 重新构造本地 Alpha360-compatible feature frame 并重新 fit。平均 Top5 overlap `0.2296296296296296`，平均 score/rank correlation `0.2571392989022139`。
2. v8.2 与 v9 的训练窗口是否一致？
   - 不完全一致。两者都声明从 2020-01-02 起训，但 v8.2 使用导出的 `train_end_label_safe` 和冻结 score trail，v9 使用 reverse audit 中本地 refit 的 label-safe cutoff；模型 provenance 不同。
3. label_5d 定义是否一致？
   - 名义上一致，均记录为 `adj_close.shift(-6) / adj_close.shift(-1) - 1` / one-day lag 后 5d forward return；但 feature/cache 与 model fit 链路不同。
4. Alpha360 feature cache 是否一致？
   - 不一致。v8.2 指向 v8.1 Alpha360/Qlib provider artifact；本地 `data/features_cache/us_stock_selection` 是 legacy feature_builder cache，并不是 v8.2 Alpha360 cache。
5. v9 原始 CAGR 12.23% / 10.53% 为什么低？
   - v9 original daily_nav 从 2020-01-02 起算，包含 2020-2023 大量 zero-exposure 天数，摊薄 CAGR 与 Calmar；且 score provenance 与 v8.2 不同。
6. 统一窗口后 37.35% / 31.70% 为什么高？
   - unified window 截到 2024-01-02 至 2026-04-17，剔除了 zero-exposure 2020-2023，因此年化指标显著抬升；但仍未贴近 v8.2 冻结主线。
7. 是窗口差异、方法差异、score 差异、还是 exception pollution？
   - 同时存在窗口差异、方法/score provenance 差异和 baseline exception pollution；核心阻断是 score/method provenance 不一致。
8. baseline_exception_pollution 的具体来源是什么？
   - PLTR/SNOW 是 baseline reproduction only ticker，因 listed_after_2020_train_start 被标记为 v9 not ready，却出现在 Pool A reproduction/local replay 贡献中。
9. v9 原始结果是否应废弃？
   - 是。原始 full-window 指标不能与 v8.2 575-day 冻结窗口比较。
10. unified replay 是否可作为有效结果？
    - 不能作为正式通过结果；只能作为审计证据。它证明窗口对指标影响很大，但未证明 score provenance 对齐。
11. 是否允许继续 v9？
    - 不允许直接继续 v9 扩展或升级；下一步只能同池、同策略、同 gate 重新对齐 score provenance 或重跑正式 v9。
12. 是否允许进入 v10？
    - 不允许。
13. 是否仍需人工审阅？
    - 需要。当前 classification 要求人工复核或按 v8.2 score source 重跑。

## Score source alignment

| source_name                    | feature_cache_path                                                                                                                            | feature_set                                | feature_count                                          |   row_count | date_min   | date_max   |   instruments_count | hash_or_fingerprint   | label_definition                                         | label_shift                  | fit_window_definition                 | prediction_window_definition   |
|:-------------------------------|:----------------------------------------------------------------------------------------------------------------------------------------------|:-------------------------------------------|:-------------------------------------------------------|------------:|:-----------|:-----------|--------------------:|:----------------------|:---------------------------------------------------------|:-----------------------------|:--------------------------------------|:-------------------------------|
| v8_2_score_rank_audit_trail    | E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\run_20260502_210856\v8_1_model_switch\Alpha360_LGBModel\v8_2_score_rank_audit_trail.csv | Alpha360                                   | Alpha360 feature matrix not exported in score trail    |         648 | 2024-01-31 | 2026-03-31 |                  36 | 8bcae07970e4711c      | label_5d = adj_close.shift(-6) / adj_close.shift(-1) - 1 | 5d forward after one-day lag | 2020-01-02 to train_end_label_safe    | decision_date candidate scores |
| v9_local_score_rank_audit      | E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\run_20260503_172054\v9_reverse_audit\score_rank_audit.csv                               | local Alpha360-compatible                  | local refit feature matrix not exported in score trail |         972 | 2024-01-31 | 2026-03-31 |                  36 | 351dfcf4d093b568      | label_5d = adj_close.shift(-6) / adj_close.shift(-1) - 1 | 5d forward after one-day lag | 2020-01-02 to decision-6 trading days | decision_date candidate scores |
| local_features_cache_directory | E:\dzhwork\quant\quant_lab\data\features_cache\us_stock_selection                                                                             | legacy feature_builder cache, not Alpha360 | 83                                                     |      136717 | 2010-01-04 | 2026-04-17 |                  38 | e52b876c817ea319      | contains forward_return labels, not v8.2 Alpha360 cache  | various forward labels       | metadata only                         | metadata only                  |

## Score/rank monthly summary

| rebalance_date   |   rank_correlation |   selected_overlap |   top5_overlap_ratio |   top10_overlap_ratio |   score_missing_count |   rank_inversion_count |
|:-----------------|-------------------:|-------------------:|---------------------:|----------------------:|----------------------:|-----------------------:|
| 2024-01-31       |          0.191507  |                  3 |                  0.6 |                   0.6 |                     0 |                     16 |
| 2024-02-29       |         -0.110638  |                  1 |                  0.2 |                   0.3 |                     0 |                     14 |
| 2024-03-28       |        nan         |                  0 |                  0   |                   0   |                    36 |                      0 |
| 2024-04-30       |          0.378588  |                  2 |                  0.4 |                   0.6 |                     0 |                     19 |
| 2024-05-31       |          0.217238  |                  1 |                  0.2 |                   0.5 |                     0 |                     18 |
| 2024-06-28       |        nan         |                  0 |                  0   |                   0   |                    36 |                      0 |
| 2024-07-31       |          0.350553  |                  3 |                  0.6 |                   0.5 |                     0 |                     17 |
| 2024-08-30       |        nan         |                  0 |                  0   |                   0   |                    36 |                      0 |
| 2024-09-30       |         -0.201697  |                  1 |                  0.2 |                   0.3 |                     0 |                     19 |
| 2024-10-31       |          0.476134  |                  1 |                  0.2 |                   0.5 |                     0 |                     17 |
| 2024-11-29       |        nan         |                  0 |                  0   |                   0   |                    36 |                      0 |
| 2024-12-31       |          0.584973  |                  3 |                  0.6 |                   0.4 |                     0 |                     18 |
| 2025-01-31       |         -0.0517245 |                  1 |                  0.2 |                   0.5 |                     0 |                     16 |
| 2025-02-28       |          0.379449  |                  2 |                  0.4 |                   0.6 |                     0 |                     11 |
| 2025-03-31       |          0.562134  |                  2 |                  0.4 |                   0.7 |                     0 |                      6 |
| 2025-04-30       |          0.218064  |                  0 |                  0   |                   0.4 |                     0 |                     19 |
| 2025-05-30       |        nan         |                  0 |                  0   |                   0   |                    36 |                      0 |
| 2025-06-30       |          0.556268  |                  1 |                  0.2 |                   0.4 |                     0 |                     14 |
| 2025-07-31       |          0.324702  |                  2 |                  0.4 |                   0.5 |                     0 |                     18 |
| 2025-08-29       |        nan         |                  0 |                  0   |                   0   |                    36 |                      0 |
| 2025-09-30       |         -0.311481  |                  1 |                  0.2 |                   0.3 |                     0 |                     18 |
| 2025-10-31       |          0.294087  |                  2 |                  0.4 |                   0.4 |                     0 |                     10 |
| 2025-11-28       |        nan         |                  0 |                  0   |                   0   |                    36 |                      0 |
| 2025-12-31       |          0.561405  |                  2 |                  0.4 |                   0.2 |                     0 |                     16 |
| 2026-01-30       |        nan         |                  0 |                  0   |                   0   |                    36 |                      0 |
| 2026-02-27       |        nan         |                  0 |                  0   |                   0   |                    36 |                      0 |
| 2026-03-31       |          0.208947  |                  3 |                  0.6 |                   0.5 |                     0 |                     19 |

## Return reconstruction

| source_name             | start_date   | end_date   |   reported_cagr |   recomputed_cagr |   reported_maxdd |   recomputed_maxdd |   reported_calmar |   recomputed_calmar |   diff_cagr |   diff_maxdd |   diff_calmar | pass_recalc   | recompute_status                         |
|:------------------------|:-------------|:-----------|----------------:|------------------:|-----------------:|-------------------:|------------------:|--------------------:|------------:|-------------:|--------------:|:--------------|:-----------------------------------------|
| v8_2_top5               | 2024-01-02   | 2026-04-17 |        0.642126 |          0.777474 |        -0.392985 |          -0.392985 |           1.63397 |             1.97838 | 0.135348    | -2.32392e-08 |   0.344409    | False         | recomputed_from_local_price_and_holdings |
| v8_2_top10              | 2024-01-02   | 2026-04-17 |        0.516419 |          0.526076 |        -0.337242 |          -0.33731  |           1.5313  |             1.55962 | 0.00965663  | -6.83841e-05 |   0.0283179   | True          | recomputed_from_local_price_and_holdings |
| v9_local_top5_original  | 2020-01-02   | 2026-04-17 |        0.122334 |          0.122334 |        -0.301776 |          -0.301776 |           0.40538 |             0.40538 | 1.15186e-15 |  1.11022e-16 |   3.83027e-15 | True          | recomputed_from_local_price_and_holdings |
| v9_local_top5_unified   | 2024-01-02   | 2026-04-17 |        0.373453 |          0.373453 |        -0.301776 |          -0.301776 |           1.23752 |             1.23752 | 3.33067e-15 |  1.11022e-16 |   1.15463e-14 | True          | recomputed_from_local_price_and_holdings |
| v9_local_top10_original | 2020-01-02   | 2026-04-17 |        0.105343 |          0.105343 |        -0.292881 |          -0.292881 |           0.35968 |             0.35968 | 5.13478e-16 | -1.66533e-16 |   1.38778e-15 | True          | recomputed_from_local_price_and_holdings |
| v9_local_top10_unified  | 2024-01-02   | 2026-04-17 |        0.317039 |          0.317039 |        -0.292881 |          -0.292881 |           1.08248 |             1.08248 | 1.77636e-15 | -1.66533e-16 |   5.55112e-15 | True          | recomputed_from_local_price_and_holdings |

## Unified gate recompute

| source_name                                           |     cagr |   calmar |     maxdd |   cost50_t1_cagr |   cost50_t1_calmar |   single_year_share |   top_ticker_share |   remove_top_year_cagr |   remove_top_year_calmar |   remove_top_ticker_cagr |   remove_top_ticker_calmar | pass_cagr20   | pass_calmar1   | pass_cost50   | pass_single_year_share   | pass_top_ticker_share   | pass_remove_top_year   | pass_remove_top_ticker   | final_gate_pass   | gate_validity_note                                       |
|:------------------------------------------------------|---------:|---------:|----------:|-----------------:|-------------------:|--------------------:|-------------------:|-----------------------:|-------------------------:|-------------------------:|---------------------------:|:--------------|:---------------|:--------------|:-------------------------|:------------------------|:-----------------------|:-------------------------|:------------------|:---------------------------------------------------------|
| top5_v8_2_frozen_v8_2_frozen_reference_2024_01_02     | 0.642126 |  1.63397 | -0.392985 |        0.540613  |           1.34535  |            0.496839 |           0.137939 |              0.521587  |                 1.32724  |                 0.489654 |                   1.32651  | True          | True           | True          | True                     | True                    | True                   | True                     | True              | computed on reported/unified window                      |
| top5_v9_local_replay_v9_local_original_2020_01_02     | 0.122334 |  0.40538 | -0.301776 |        0.0556838 |           0.174335 |            0.430061 |           0.110614 |              0.0829353 |                 0.366993 |                 0.161764 |                   0.536039 | False         | False          | False         | True                     | True                    | False                  | False                    | False             | original v9 full-window gate invalid for v8.2 comparison |
| top5_v9_local_replay_v9_local_unified_2024_01_02      | 0.373453 |  1.23752 | -0.301776 |        0.0556838 |           0.174335 |            0.430061 |           0.110614 |              0.0829353 |                 0.366993 |                 0.161764 |                   0.536039 | True          | True           | False         | True                     | True                    | False                  | False                    | False             | computed on reported/unified window                      |
| top5_v9_local_replay_v9_local_active_from_2024-02-01  | 0.390073 |  1.29259 | -0.301776 |        0.0556838 |           0.174335 |            0.430061 |           0.110614 |              0.0829353 |                 0.366993 |                 0.161764 |                   0.536039 | True          | True           | False         | True                     | True                    | False                  | False                    | False             | computed on reported/unified window                      |
| top10_v8_2_frozen_v8_2_frozen_reference_2024_01_02    | 0.516419 |  1.5313  | -0.337242 |        0.437219  |           1.27158  |            0.563812 |           0.123218 |              0.358438  |                 1.06285  |                 0.422834 |                   1.39217  | True          | True           | True          | False                    | True                    | True                   | True                     | False             | computed on reported/unified window                      |
| top10_v9_local_replay_v9_local_original_2020_01_02    | 0.105343 |  0.35968 | -0.292881 |      nan         |         nan        |            0.514666 |           0.122014 |            nan         |               nan        |               nan        |                 nan        | False         | False          | False         | False                    | True                    | False                  | False                    | False             | original v9 full-window gate invalid for v8.2 comparison |
| top10_v9_local_replay_v9_local_unified_2024_01_02     | 0.317039 |  1.08248 | -0.292881 |      nan         |         nan        |            0.514666 |           0.122014 |            nan         |               nan        |               nan        |                 nan        | True          | True           | False         | False                    | True                    | False                  | False                    | False             | computed on reported/unified window                      |
| top10_v9_local_replay_v9_local_active_from_2024-02-01 | 0.330859 |  1.12967 | -0.292881 |      nan         |         nan        |            0.514666 |           0.122014 |            nan         |               nan        |               nan        |                 nan        | True          | True           | False         | False                    | True                    | False                  | False                    | False             | computed on reported/unified window                      |

## Baseline exception pollution detail

| file_path                                                                                                                   | row_id_or_section            | exception_type                      | affected_metric                                          | affected_source        | description                                                                                                                                                                                                                                                                                                               | severity   | fix_recommendation                                                                                                                     |
|:----------------------------------------------------------------------------------------------------------------------------|:-----------------------------|:------------------------------------|:---------------------------------------------------------|:-----------------------|:--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|:-----------|:---------------------------------------------------------------------------------------------------------------------------------------|
| E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\v82_v9_replay_diff_audit_20260503_232513\baseline_exception_audit.csv | 0                            | baseline_only_ticker_in_pool_a      | Pool A reproduction and local replay ticker contribution | PLTR                   | top10 v8_2_frozen: count=272, abs_share=0.1232; top10 v9_loaded_reproduction: count=272, abs_share=0.1232; top10 v9_local_replay: count=270, abs_share=0.1220; top5 v8_2_frozen: count=150, abs_share=0.1335; top5 v9_loaded_reproduction: count=150, abs_share=0.1335; top5 v9_local_replay: count=165, abs_share=0.0916 | high       | separate baseline reproduction from v9-eligible universe and rerun same-window score provenance audit without baseline-only exceptions |
| E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\v82_v9_replay_diff_audit_20260503_232513\baseline_exception_audit.csv | 1                            | baseline_only_ticker_in_pool_a      | Pool A reproduction and local replay ticker contribution | SNOW                   | top10 v8_2_frozen: count=117, abs_share=0.0237; top10 v9_loaded_reproduction: count=117, abs_share=0.0237; top10 v9_local_replay: count=298, abs_share=0.0666; top5 v8_2_frozen: count=12, abs_share=0.0010; top5 v9_loaded_reproduction: count=12, abs_share=0.0010; top5 v9_local_replay: count=155, abs_share=0.0309   | high       | separate baseline reproduction from v9-eligible universe and rerun same-window score provenance audit without baseline-only exceptions |
| E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\v82_v9_replay_diff_audit_20260503_232513\active_window_metrics.csv    | v9_local_original_2020_01_02 | evaluation_window_mismatch          | v9 original CAGR 12.23% / 10.53%                         | v9_local_replay        | v9 original daily_nav includes 2020-2023 zero-exposure rows; unified 575-day window raises CAGR but still does not match v8.2 frozen.                                                                                                                                                                                     | high       | discard original full-window v9 CAGR for v8.2 comparison; rerun official v9 on explicit 2024-01-02 aligned window                      |
| E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\v82_v9_replay_diff_audit_20260503_232513\v82_v9_method_diff.csv       | v9_loaded_reproduction       | loaded_reproduction_not_independent | v9 loaded reproduction mirrors v8.2 frozen               | v9_loaded_reproduction | loaded reproduction reads historical v8.2 artifacts and is not independent score/model/feature reconstruction.                                                                                                                                                                                                            | high       | do not use loaded reproduction as evidence of v9 score provenance alignment                                                            |

## Missing inputs

| input_name         | file_path                                                                                                                                     | exists   | status   |
|:-------------------|:----------------------------------------------------------------------------------------------------------------------------------------------|:---------|:---------|
| v82_results        | E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\run_20260502_220641\v8_2_year_stability\v8_2_year_stability_results.csv                 | True     | found    |
| v82_holdings       | E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\run_20260502_220641\v8_2_year_stability\v8_2_monthly_holdings_by_strategy.csv           | True     | found    |
| v82_daily          | E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\run_20260502_220641\v8_2_year_stability\v8_2_daily_nav_by_strategy.csv                  | True     | found    |
| v82_variant_config | E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\run_20260502_220641\v8_2_year_stability\v8_2_variant_config.csv                         | True     | found    |
| v81_score          | E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\run_20260502_210856\v8_1_model_switch\Alpha360_LGBModel\v8_2_score_rank_audit_trail.csv | True     | found    |
| v81_ledger         | E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\run_20260502_210856\v8_1_model_switch\Alpha360_LGBModel\monthly_decision_ledger.csv     | True     | found    |
| v9_holdings        | E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\run_20260503_172054\v9_reverse_audit\monthly_holdings.csv                               | True     | found    |
| v9_daily           | E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\run_20260503_172054\v9_reverse_audit\daily_nav.csv                                      | True     | found    |
| v9_score           | E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\run_20260503_172054\v9_reverse_audit\score_rank_audit.csv                               | True     | found    |
| v9_time            | E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\run_20260503_172054\v9_reverse_audit\time_alignment_audit.csv                           | True     | found    |
| diff_active        | E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\v82_v9_replay_diff_audit_20260503_232513\active_window_metrics.csv                      | True     | found    |
| diff_candidate     | E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\v82_v9_replay_diff_audit_20260503_232513\candidate_replay_diff.csv                      | True     | found    |
| diff_monthly       | E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\v82_v9_replay_diff_audit_20260503_232513\monthly_selection_diff.csv                     | True     | found    |
| diff_by_ticker     | E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\v82_v9_replay_diff_audit_20260503_232513\candidate_replay_diff_by_ticker.csv            | True     | found    |
| diff_method        | E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\v82_v9_replay_diff_audit_20260503_232513\v82_v9_method_diff.csv                         | True     | found    |
| baseline_exception | E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\v82_v9_replay_diff_audit_20260503_232513\baseline_exception_audit.csv                   | True     | found    |
| audit_summary      | E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\v82_v9_replay_diff_audit_20260503_232513\audit_summary.json                             | True     | found    |
| bridge_manifest    | E:\dzhwork\quant\quant_lab\docs\chatgpt_bridge\latest_run_manifest.json                                                                       | True     | found    |
| bridge_latest      | E:\dzhwork\quant\quant_lab\docs\chatgpt_bridge\LATEST.md                                                                                      | True     | found    |

## Next allowed action

Stop and review score provenance evidence; if continuing, rerun same Pool A strategy with v8.2 score source and explicit aligned window.
