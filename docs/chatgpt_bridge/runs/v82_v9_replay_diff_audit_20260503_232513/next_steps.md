# NEXT_STEPS

当前状态：v8.2/v9 replay diff audit 已完成。

- Run：`E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\v82_v9_replay_diff_audit_20260503_232513`
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
