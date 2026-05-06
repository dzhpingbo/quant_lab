# RUN_SUMMARY

本轮目标：v8.2 canonical source-of-truth 重建与 formal v9 前置修复。

新 run 目录：`E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\v82_canonical_rebuild_20260504_090549`
zip 路径：`E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\us_stock_selection_v82_canonical_rebuild_20260504_090549.zip`

核心结论：
- classification: `formal_v82_valid_ready_for_formal_v9`
- v82_reported_vs_recomputed_consistent: `True`
- root_cause: `price_source_mismatch; baseline_pollution_isolated`
- formal_v82_gate_pass: `True`
- formal_v82_cagr: `0.6421262430680639`
- formal_v82_calmar: `1.6339698829869318`
- formal_v82_max_drawdown: `-0.39298536022845376`
- PLTR/SNOW pollution isolated: `True`
- v9 original discarded: `True`
- unified replay role: `audit_evidence_only_not_formal_result`
- formal_v9_run_plan_generated: `True`
- allow_execute_formal_v9: `False`
- allow_enter_v10: `False`

原因：Canonical provider-bin replay matches v8.2 reported metrics and formal v8.2 gate passes; prior mismatch was caused by using noncanonical unified parquet prices for reconstruction.

本轮没有扩 Nasdaq100/S&P500，没有进入 v10，没有下载行情，没有连接券商，没有自动 commit/push。
