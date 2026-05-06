# ChatGPT Review Packet

## Run

- run_id: `score_provenance_alignment_audit_20260504_084307`
- run_dir: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\score_provenance_alignment_audit_20260504_084307`
- zip_path: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\us_stock_selection_score_provenance_alignment_audit_20260504_084307.zip`
- published_at: `2026-05-04T08:43:18`

## 本轮目标

本轮目标：score provenance 对齐审计；只比较 v8.2 frozen Pool A 与 v9 local/unified replay 的 score、feature cache、fit、label、universe、calendar、portfolio、return reconstruction、gate 和 baseline exception。

## 新增/修改文件

- `quant_lab/us_stock_selection/score_provenance_audit.py`
- `quant_lab/us_stock_selection/v9_alignment_reporting.py`
- `scripts/us_stock_selection/37_run_score_provenance_alignment_audit.py`

## 核心结果 / RUN_SUMMARY

# RUN_SUMMARY

本轮目标：score provenance 对齐审计；只比较 v8.2 frozen Pool A 与 v9 local/unified replay 的 score、feature cache、fit、label、universe、calendar、portfolio、return reconstruction、gate 和 baseline exception。

新 run 目录：`E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\score_provenance_alignment_audit_20260504_084307`
zip 路径：`E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\us_stock_selection_score_provenance_alignment_audit_20260504_084307.zip`

核心结论：
- classification: `score_provenance_mismatch`
- score_provenance_consistent: `False`
- method_window_consistent: `False`
- return_reconstruction_consistent: `False`
- baseline_exception_pollution_found: `True`
- v9_original_results_should_be_discarded: `True`
- unified_replay_usable: `False`
- allow_continue_v9: `False`
- allow_enter_v10: `False`
- requires_human_review: `True`

原因：v8.2 frozen scores come from v8.1 Alpha360 runtime score trail, while v9 local replay refits a local Alpha360-compatible score chain; score/rank overlap is insufficient and baseline-only PLTR/SNOW pollution remains.

本轮没有扩 Nasdaq100/S&P500，没有进入 v10，没有下载行情，没有连接券商，没有自动 commit/push。


## 核心指标

|     cagr | cost50_t1_cagr   |   calmar | cost50_t1_calmar   |   single_year_share |   top_ticker_share | remove_top_year_cagr   | remove_top_year_calmar   | remove_top_ticker_cagr   | remove_top_ticker_calmar   |
|---------:|:-----------------|---------:|:-------------------|--------------------:|-------------------:|:-----------------------|:-------------------------|:-------------------------|:---------------------------|
| 0.642126 | 0.540613         |  1.63397 | 1.345347           |            0.496839 |           0.137939 | 0.521587               | 1.327243                 | 0.489654                 | 1.326510                   |
| 0.122334 | 0.055684         |  0.40538 | 0.174335           |            0.430061 |           0.110614 | 0.082935               | 0.366993                 | 0.161764                 | 0.536039                   |
| 0.373453 | 0.055684         |  1.23752 | 0.174335           |            0.430061 |           0.110614 | 0.082935               | 0.366993                 | 0.161764                 | 0.536039                   |
| 0.390073 | 0.055684         |  1.29259 | 0.174335           |            0.430061 |           0.110614 | 0.082935               | 0.366993                 | 0.161764                 | 0.536039                   |
| 0.516419 | 0.437219         |  1.5313  | 1.271579           |            0.563812 |           0.123218 | 0.358438               | 1.062852                 | 0.422834                 | 1.392170                   |
| 0.105343 |                  |  0.35968 |                    |            0.514666 |           0.122014 |                        |                          |                          |                            |
| 0.317039 |                  |  1.08248 |                    |            0.514666 |           0.122014 |                        |                          |                          |                            |
| 0.330859 |                  |  1.12967 |                    |            0.514666 |           0.122014 |                        |                          |                          |                            |

## Gate / Verdict

```json
{
  "classification": "score_provenance_mismatch",
  "score_provenance_consistent": false,
  "method_window_consistent": false,
  "return_reconstruction_consistent": false,
  "baseline_exception_pollution_found": true,
  "evaluation_window_mismatch_found": true,
  "method_mismatch_found": true,
  "avg_top5_overlap_ratio": 0.2296296296296296,
  "avg_score_rank_correlation": 0.2571392989022139,
  "v9_original_results_should_be_discarded": true,
  "unified_replay_usable": false,
  "allow_continue_v9": false,
  "allow_enter_v10": false,
  "allow_expand_nasdaq100": false,
  "allow_expand_sp500": false,
  "allow_trade_execution": false,
  "requires_human_review": true,
  "next_allowed_action": "Stop and review score provenance evidence; if continuing, rerun same Pool A strategy with v8.2 score source and explicit aligned window.",
  "reason": "v8.2 frozen scores come from v8.1 Alpha360 runtime score trail, while v9 local replay refits a local Alpha360-compatible score chain; score/rank overlap is insufficient and baseline-only PLTR/SNOW pollution remains.",
  "zip_path": "E:\\dzhwork\\quant\\quant_lab\\outputs\\us_stock_selection\\us_stock_selection_score_provenance_alignment_audit_20260504_084307.zip",
  "run_dir": "E:\\dzhwork\\quant\\quant_lab\\outputs\\us_stock_selection\\score_provenance_alignment_audit_20260504_084307"
}
```

## 当前分类

- classification: `score_provenance_mismatch`
- allow_enter_v9: ``
- allow_enter_v10: `False`

## 不通过原因 / 已知限制

- verdict.reason: `v8.2 frozen scores come from v8.1 Alpha360 runtime score trail, while v9 local replay refits a local Alpha360-compatible score chain; score/rank overlap is insufficient and baseline-only PLTR/SNOW pollution remains.`
- - 不允许直接继续 v9 扩展或升级；下一步只能同池、同策略、同 gate 重新对齐 score provenance 或重跑正式 v9。
- - 不允许。

## 需要 ChatGPT 审阅的问题

1. 当前 classification 是否与 gate 证据一致？
2. 是否存在未来函数、样本选择偏差、执行口径或数据质量问题？
3. 是否应批准进入下一阶段，还是要求补验证？
4. 如果进入下一阶段，边界条件是否足够明确？

## Codex 建议的下一步

# NEXT_STEPS

当前状态：`score_provenance_mismatch`。

下一步只允许：
- 人工/ChatGPT 审阅本轮 score provenance audit。
- 若继续研究，按 v8.2 同池、同策略、同 gate、同 score source 重新定义正式 v9 口径并重跑。
- 若确认 score provenance mismatch，先修复 score/feature/model fit provenance，再回到审计。

禁止：
- 不扩 Nasdaq100/S&P500/全市场。
- 不进入 v10。
- 不交易化，不连接券商，不下单。
- 不把 v9 original full-window 指标包装为通过。


## 关键表格摘要

| csv                                                                                                                 |   size_mb | bridge_mode      |
|:--------------------------------------------------------------------------------------------------------------------|----------:|:-----------------|
| outputs\us_stock_selection\score_provenance_alignment_audit_20260504_084307\baseline_exception_pollution_detail.csv |     0.002 | copy_if_selected |
| outputs\us_stock_selection\score_provenance_alignment_audit_20260504_084307\calendar_alignment.csv                  |     0.003 | copy_if_selected |
| outputs\us_stock_selection\score_provenance_alignment_audit_20260504_084307\gate_recompute_alignment.csv            |     0.003 | copy_if_selected |
| outputs\us_stock_selection\score_provenance_alignment_audit_20260504_084307\missing_files.csv                       |     0.003 | copy_if_selected |
| outputs\us_stock_selection\score_provenance_alignment_audit_20260504_084307\model_fit_provenance.csv                |     0.007 | copy_if_selected |
| outputs\us_stock_selection\score_provenance_alignment_audit_20260504_084307\portfolio_decision_alignment.csv        |     0.418 | copy_if_selected |
| outputs\us_stock_selection\score_provenance_alignment_audit_20260504_084307\portfolio_decision_diff.csv             |     0.116 | copy_if_selected |
| outputs\us_stock_selection\score_provenance_alignment_audit_20260504_084307\return_reconstruction_check.csv         |     0.002 | copy_if_selected |
| outputs\us_stock_selection\score_provenance_alignment_audit_20260504_084307\run_manifest_alignment.csv              |     0.002 | copy_if_selected |
| outputs\us_stock_selection\score_provenance_alignment_audit_20260504_084307\score_rank_diff.csv                     |     0.122 | copy_if_selected |
| outputs\us_stock_selection\score_provenance_alignment_audit_20260504_084307\score_rank_diff_summary.csv             |     0.001 | copy_if_selected |
| outputs\us_stock_selection\score_provenance_alignment_audit_20260504_084307\score_source_alignment.csv              |     0.001 | copy_if_selected |
| outputs\us_stock_selection\score_provenance_alignment_audit_20260504_084307\universe_alignment.csv                  |     0.003 | copy_if_selected |

## 重要 CSV 文件路径

- `outputs\us_stock_selection\score_provenance_alignment_audit_20260504_084307\baseline_exception_pollution_detail.csv`
- `outputs\us_stock_selection\score_provenance_alignment_audit_20260504_084307\calendar_alignment.csv`
- `outputs\us_stock_selection\score_provenance_alignment_audit_20260504_084307\gate_recompute_alignment.csv`
- `outputs\us_stock_selection\score_provenance_alignment_audit_20260504_084307\missing_files.csv`
- `outputs\us_stock_selection\score_provenance_alignment_audit_20260504_084307\model_fit_provenance.csv`
- `outputs\us_stock_selection\score_provenance_alignment_audit_20260504_084307\portfolio_decision_alignment.csv`
- `outputs\us_stock_selection\score_provenance_alignment_audit_20260504_084307\portfolio_decision_diff.csv`
- `outputs\us_stock_selection\score_provenance_alignment_audit_20260504_084307\return_reconstruction_check.csv`
- `outputs\us_stock_selection\score_provenance_alignment_audit_20260504_084307\run_manifest_alignment.csv`
- `outputs\us_stock_selection\score_provenance_alignment_audit_20260504_084307\score_rank_diff.csv`
- `outputs\us_stock_selection\score_provenance_alignment_audit_20260504_084307\score_rank_diff_summary.csv`
- `outputs\us_stock_selection\score_provenance_alignment_audit_20260504_084307\score_source_alignment.csv`
- `outputs\us_stock_selection\score_provenance_alignment_audit_20260504_084307\universe_alignment.csv`

## selected_report.md excerpt

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



...[truncated for bridge packet]...
