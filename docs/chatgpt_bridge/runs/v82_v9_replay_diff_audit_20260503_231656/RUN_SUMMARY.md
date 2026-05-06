# RUN_SUMMARY

本轮目标：执行 v8.2 frozen Pool A 与 v9 local replay 的本地反向差异审计；只做同池、只读、非优化审计。

新 run 目录：`E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\v82_v9_replay_diff_audit_20260503_231656`
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
