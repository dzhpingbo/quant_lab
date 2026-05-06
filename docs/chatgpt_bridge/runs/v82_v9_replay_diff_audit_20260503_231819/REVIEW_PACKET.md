# ChatGPT Review Packet

## Run

- run_id: `v82_v9_replay_diff_audit_20260503_231819`
- run_dir: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\v82_v9_replay_diff_audit_20260503_231819`
- zip_path: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\us_stock_selection_v82_v9_replay_diff_audit_20260503_231819.zip`
- published_at: `2026-05-03T23:23:51`

## 本轮目标

本轮目标：执行 v8.2 frozen Pool A 与 v9 local replay 的本地反向差异审计；只做同池、只读、非优化审计。

## 新增/修改文件

- `scripts/us_stock_selection/36_run_v82_v9_replay_diff_audit.py`

## 核心结果 / RUN_SUMMARY

# RUN_SUMMARY

本轮目标：执行 v8.2 frozen Pool A 与 v9 local replay 的本地反向差异审计；只做同池、只读、非优化审计。

新 run 目录：`E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\v82_v9_replay_diff_audit_20260503_231819`
最终分类：`invalid_or_needs_human_review`
Requires human review：`True`
是否允许扩池：`False`
是否允许进入 v10：`False`
是否允许交易执行：`False`

核心发现：
- Evaluation window mismatch：`True`
- Method mismatch：`True`
- Leakage risk found：`False`
- Baseline exception pollution：`True`
- Top5 v8.2 unified CAGR/Calmar：`64.21%` / `1.6340`
- Top5 v9 local unified CAGR/Calmar：`37.35%` / `1.2375`
- Top10 v8.2 unified CAGR/Calmar：`51.64%` / `1.5313`
- Top10 v9 local unified CAGR/Calmar：`31.70%` / `1.0825`

结论：v9 local official/full CAGR 因 2020-2023 零仓位期计入而不可与 575 天 v8.2 frozen 直接比较；统一窗口后仍不能接近复现 v8.2 frozen 高收益，且 PLTR/SNOW baseline-only exception 污染 Pool A 复现结论。不得扩池，不得进入 v10。


## 核心指标

| strategy_id                |     cagr |   max_drawdown |   calmar |   single_year_share | top_ticker   |
|:---------------------------|---------:|---------------:|---------:|--------------------:|:-------------|
| top5_ytdcap80p_derisk100p  | 0.642126 |      -0.392985 |  1.63397 |            0.496839 | INTC         |
| top5_ytdcap80p_derisk100p  | 0.122334 |      -0.301776 |  0.40538 |            0.430061 | MSTR         |
| top5_ytdcap80p_derisk100p  | 0.373453 |      -0.301776 |  1.23752 |            0.430061 | MSTR         |
| top5_ytdcap80p_derisk100p  | 0.390073 |      -0.301776 |  1.29259 |            0.430061 | MSTR         |
| top10_ytdcap80p_derisk100p | 0.516419 |      -0.337242 |  1.5313  |            0.563812 | PLTR         |
| top10_ytdcap80p_derisk100p | 0.105343 |      -0.292881 |  0.35968 |            0.514666 | PLTR         |
| top10_ytdcap80p_derisk100p | 0.317039 |      -0.292881 |  1.08248 |            0.514666 | PLTR         |
| top10_ytdcap80p_derisk100p | 0.330859 |      -0.292881 |  1.12967 |            0.514666 | PLTR         |

## Gate / Verdict

```json
{
  "classification": "invalid_or_needs_human_review",
  "requires_human_review": true,
  "allow_expand_universe": false,
  "allow_expand_nasdaq100": false,
  "allow_expand_sp500": false,
  "allow_enter_v10": false,
  "allow_trade_execution": false,
  "method_mismatch_found": true,
  "leakage_risk_found": false,
  "evaluation_window_mismatch_found": true,
  "pool_a_replay_close_to_v8_2_on_unified_window": false,
  "baseline_exception_pollution_found": true,
  "missing_required_inputs": [],
  "v9_top5_original_daily_count": 1581,
  "v9_top5_unified_daily_count": 575,
  "v9_top5_original_cagr": 0.12233370971203095,
  "v9_top5_unified_cagr": 0.3734527647492101,
  "v9_top10_original_daily_count": 1581,
  "v9_top10_unified_daily_count": 575,
  "v9_top10_original_cagr": 0.10534343408965197,
  "v9_top10_unified_cagr": 0.3170385487736407,
  "static_scan_rows": 194,
  "static_scan_high_risk_rows": 42,
  "reason": "v9 local replay used a 2020-01-02 full daily_nav with zero-exposure 2020-2023 rows, while v8.2 frozen and loaded reproduction use the 2024-01-02 to 2026-04-17 window; after window alignment the local replay still does not closely reproduce v8.2, and PLTR/SNOW remain baseline-only exceptions.",
  "zip_path": "E:\\dzhwork\\quant\\quant_lab\\outputs\\us_stock_selection\\us_stock_selection_v82_v9_replay_diff_audit_20260503_231819.zip",
  "run_dir": "E:\\dzhwork\\quant\\quant_lab\\outputs\\us_stock_selection\\v82_v9_replay_diff_audit_20260503_231819"
}
```

## 当前分类

- classification: `invalid_or_needs_human_review`
- allow_enter_v9: ``
- allow_enter_v10: `False`

## 不通过原因 / 已知限制

- verdict.reason: `v9 local replay used a 2020-01-02 full daily_nav with zero-exposure 2020-2023 rows, while v8.2 frozen and loaded reproduction use the 2024-01-02 to 2026-04-17 window; after window alignment the local replay still does not closely reproduce v8.2, and PLTR/SNOW remain baseline-only exceptions.`
- ## 风险评级
- - 评估窗口风险：高。v9 local official/full CAGR 把 2020-2023 零仓位期纳入 annualization，不能与 v8.2 的 575 天口径直接比较。
- - 方法口径风险：高。v8.2 frozen、v9 loaded reproduction、v9 local replay 的 score provenance 和 feature source 不一致。
- - 复现风险：高。统一窗口后 v9 local replay 仍未在 CAGR/Calmar/MaxDD 阈值内接近 v8.2 frozen。
- - baseline-only 污染风险：高。PLTR/SNOW 明确为 v9 baseline-only exception 且有选择/贡献记录。
- - 静态扫描：194 条风险命中，其中 high=42；未据此确认未来函数或标签泄露。

## 需要 ChatGPT 审阅的问题

1. 当前 classification 是否与 gate 证据一致？
2. 是否存在未来函数、样本选择偏差、执行口径或数据质量问题？
3. 是否应批准进入下一阶段，还是要求补验证？
4. 如果进入下一阶段，边界条件是否足够明确？

## Codex 建议的下一步

# NEXT_STEPS

当前状态：v8.2/v9 replay diff audit 已完成。

- Run：`E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\v82_v9_replay_diff_audit_20260503_231819`
- Classification：`invalid_or_needs_human_review`
- Requires human review：`True`
- Allow expand universe：`False`
- Allow v10：`False`
- Allow trade execution：`False`

硬边界：

1. 不扩 Nasdaq100，不扩 S&P500，不做全市场扩池。
2. 不进入 v10。
3. 不接券商 API，不做真实交易或任何执行接入。
4. 不联网下载行情，不使用 key/secret/token/credential。
5. 不通过调 gate、ranking 权重、指标口径或主线策略改善结果。

下一步允许事项：

1. 只允许同池、同策略、同 gate、统一 2024-01-02 到 2026-04-17 评估窗口继续复核。
2. 优先复核 `monthly_selection_diff.csv` 中 v8.1/v8.2/v9 loaded/v9 local 的逐月 Top5/Top10 score/rank/weight 差异。
3. 复核 `baseline_exception_audit.csv` 中 PLTR/SNOW baseline-only exception 是否应从任何独立复现结论中剔除或单独标注。
4. 若继续编码，只能做 score provenance 对齐 replay；不得优化策略，不得扩池，不得进入 v10。


## 关键表格摘要

| csv                                                                                                     |   size_mb | bridge_mode      |
|:--------------------------------------------------------------------------------------------------------|----------:|:-----------------|
| outputs\us_stock_selection\v82_v9_replay_diff_audit_20260503_231819\active_window_metrics.csv           |     0.003 | copy_if_selected |
| outputs\us_stock_selection\v82_v9_replay_diff_audit_20260503_231819\baseline_exception_audit.csv        |     0.001 | copy_if_selected |
| outputs\us_stock_selection\v82_v9_replay_diff_audit_20260503_231819\candidate_replay_diff.csv           |     0.004 | copy_if_selected |
| outputs\us_stock_selection\v82_v9_replay_diff_audit_20260503_231819\candidate_replay_diff_by_ticker.csv |     0.022 | copy_if_selected |
| outputs\us_stock_selection\v82_v9_replay_diff_audit_20260503_231819\data_lineage_audit.csv              |     0.018 | copy_if_selected |
| outputs\us_stock_selection\v82_v9_replay_diff_audit_20260503_231819\leakage_static_scan.csv             |     0.04  | copy_if_selected |
| outputs\us_stock_selection\v82_v9_replay_diff_audit_20260503_231819\monthly_selection_diff.csv          |     1.495 | copy_if_selected |
| outputs\us_stock_selection\v82_v9_replay_diff_audit_20260503_231819\required_input_manifest.csv         |     0.03  | copy_if_selected |
| outputs\us_stock_selection\v82_v9_replay_diff_audit_20260503_231819\v82_v9_method_diff.csv              |     0.003 | copy_if_selected |

## 重要 CSV 文件路径

- `outputs\us_stock_selection\v82_v9_replay_diff_audit_20260503_231819\active_window_metrics.csv`
- `outputs\us_stock_selection\v82_v9_replay_diff_audit_20260503_231819\baseline_exception_audit.csv`
- `outputs\us_stock_selection\v82_v9_replay_diff_audit_20260503_231819\candidate_replay_diff.csv`
- `outputs\us_stock_selection\v82_v9_replay_diff_audit_20260503_231819\candidate_replay_diff_by_ticker.csv`
- `outputs\us_stock_selection\v82_v9_replay_diff_audit_20260503_231819\data_lineage_audit.csv`
- `outputs\us_stock_selection\v82_v9_replay_diff_audit_20260503_231819\leakage_static_scan.csv`
- `outputs\us_stock_selection\v82_v9_replay_diff_audit_20260503_231819\monthly_selection_diff.csv`
- `outputs\us_stock_selection\v82_v9_replay_diff_audit_20260503_231819\required_input_manifest.csv`
- `outputs\us_stock_selection\v82_v9_replay_diff_audit_20260503_231819\v82_v9_method_diff.csv`

## selected_report.md excerpt

# v8.2 frozen Pool A 与 v9 local replay 反向差异审计

## 结论

- Classification：`invalid_or_needs_human_review`
- requires_human_review：`True`
- allow_expand_universe：`False`
- allow_enter_v10：`False`
- allow_trade_execution：`False`

本轮发现明确评估窗口不一致：v9 local replay 的 `daily_nav.csv` 从 2020-01-02 开始，但 first non-zero weight date 为 2024-02-01；v8.2 frozen / v9 loaded reproduction 使用 2024-01-02 到 2026-04-17 的 575 天窗口。因此 v9 local official/full CAGR 不能与 v8.2 frozen CAGR 直接比较。

统一到 2024-01-02 后，v9 local replay 的 CAGR 会被重新年化到 575 天口径，但 Top5/Top10 仍未接近复现 v8.2 frozen 高收益；差异从“窗口口径错误”进一步落到 score provenance、feature/data source、loaded reproduction 非独立复算和 baseline-only exception 污染。

## 必答问题

1. v9 local replay official/full CAGR 是否因 2020-2023 零仓位期被计入而不可直接比较：是。full daily_count=1581，统一窗口 daily_count=575。
2. v8.2 frozen 高收益是否能在统一 2024-01-02 起算窗口由 v9 local replay 接近复现：不能。Top5 v8.2 CAGR=64.21% vs v9 local=37.35%；Top10 v8.2 CAGR=51.64% vs v9 local=31.70%。
3. PLTR/SNOW baseline-only exception 是否污染 Pool A 复现结论：是。见 `baseline_exception_audit.csv` 和 `candidate_replay_diff_by_ticker.csv`。
4. 是否发现未来函数、标签泄露、执行时点错误或测试集筛选证据：未发现已确认的未来函数/标签泄露证据；`time_alignment_audit.csv` 在上一轮为 pass。静态扫描发现 audit-forward 字段、历史结果加载、下载路径和执行时点逻辑需要继续人工复核，但本脚本未调用外部数据下载。
5. v8.2 frozen loaded reproduction 是否独立复算：不是。v9 loaded reproduction 来自 `load_v8_2_reproduction` 读取历史 v8.2 daily/holdings/metrics。

## 证据链

- v9 local Top5 official/full daily_count=1581，CAGR=12.23%；统一 2024-01-02 窗口 daily_count=575，CAGR=37.35%。
- v8.2 frozen Top5 统一窗口 CAGR=64.21%，Calmar=1.6340；v9 local Top5 统一窗口 CAGR=37.35%，Calmar=1.2375，仍未接近复现。
- v8.2 frozen Top10 统一窗口 CAGR=51.64%，Calmar=1.5313；v9 local Top10 统一窗口 CAGR=31.70%，Calmar=1.0825。
- v9 loaded reproduction 的 score_source 是 loaded_from_v8_2_reproduction，属于读取历史 v8.2 结果，不是独立复算。
- PLTR/SNOW 在 v9 数据质量中为 baseline-only exception，但仍出现在 Pool A reproduction 和本地 replay 持仓/贡献中。

## 风险评级

- 评估窗口风险：高。v9 local official/full CAGR 把 2020-2023 零仓位期纳入 annualization，不能与 v8.2 的 575 天口径直接比较。
- 方法口径风险：高。v8.2 frozen、v9 loaded reproduction、v9 local replay 的 score provenance 和 feature source 不一致。
- 复现风险：高。统一窗口后 v9 local replay 仍未在 CAGR/Calmar/MaxDD 阈值内接近 v8.2 frozen。
- baseline-only 污染风险：高。PLTR/SNOW 明确为 v9 baseline-only exception 且有选择/贡献记录。
- 静态扫描：194 条风险命中，其中 high=42；未据此确认未来函数或标签泄露。

## 关键输出

- Run：`E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\v82_v9_replay_diff_audit_20260503_231819`
- `audit_summary.json`
- `v82_v9_method_diff.csv`
- `candidate_replay_diff.csv`
- `active_window_metrics.csv`
- `monthly_selection_diff.csv`
- `candidate_replay_diff_by_ticker.csv`
- `data_lineage_audit.csv`
- `leakage_static_scan.csv`
- `baseline_exception_audit.csv`
- `reports/v82_v9_replay_diff_audit_summary.xlsx`

## 下一步建议

下一轮仍不得扩池、不得进入 v10、不得做任何执行接入。只允许同池、同策略、同 gate，在统一 2024-01-02 窗口下补一个真正 score-provenance 对齐的 replay：要么用 v8.1 score/rank audit trail 独立重算 v8.2 Top5/Top10，并与 v9 local 的 score/rank 逐月逐 ticker 对齐；要么证明 v8.2 原始 score 生成链可从本地 raw feature + model 完整复现。

