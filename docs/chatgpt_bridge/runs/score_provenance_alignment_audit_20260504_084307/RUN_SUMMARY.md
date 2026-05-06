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
