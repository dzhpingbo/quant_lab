# US Stock Selection v8 / v8.2 Final Closeout

## 1. 研究背景

本轮为最终收口归档，不进入 v9，不扩 universe，不训练新模型，不运行 31b，不新增参数，不继续 overlay/reranking 微调。

## 2. v8 Baseline 最终结论

v8 baseline 是当前 best / return-priority version，classification 为 `current_best_return_priority`，verdict 为 `credible_but_execution_sensitive`。

## 3. v8.1 Overlay 路线为什么停止

v8.1 overlay 多轮尝试进入 plateau，未形成可替代 v8 baseline 的稳健收益/回撤改善，因此停止继续 overlay 路线。

## 4. v8.2 Stock Selection Diagnostic 发现

诊断发现原 v8 输出只保留 selected-only 信息，缺少完整 candidate score/rank 留痕，不能安全做 ex-ante reranking。

## 5. Bounded Audit Replay 为什么重要

bounded audit replay 生成完整 decision_date x candidate score/rank audit trail，并复现 baseline selection，为后续有限 reranking 提供了不含未来函数的审计基础。

## 6. Gate-Aware Reranking 发现

预注册 gate-aware reranking 未产生 accepted/strong candidate，但 high-beta penalty 显示弱窗口改善信号。

## 7. 0p05 为什么可作为 Risk-Control Variant

0p05 复现通过，无未来函数，降低 high-beta 暴露，改善 weakest 12M；avg high-beta weight 从 14.58% 降至 7.15%，max high-beta weight 从 60% 降至 20%。

## 8. 为什么 0p05 不替代 v8 Baseline

0p05 full-period CAGR/Calmar 低于 baseline，50bps CAGR 安全边际很薄，top5 positive month share 更高，remove top5 month 后基本失效，不满足 replace baseline 条件。

## 9. 两套策略口径对比

| strategy_name                            | classification               |     CAGR |   cost_50bps_CAGR |   Calmar |     MaxDD |   weakest_12m_Calmar |   weakest_12m_50bps_CAGR |   avg_high_beta_weight |   max_high_beta_weight |   top1_positive_month_share |   top3_positive_month_share |   top5_positive_month_share |   remove_top5_month_CAGR | cost_sensitivity_comment                                                     | concentration_risk_comment                                                       | recommended_usage                                                                         | replace_v8_best   | allow_enter_v9   |
|:-----------------------------------------|:-----------------------------|---------:|------------------:|---------:|----------:|---------------------:|-------------------------:|-----------------------:|-----------------------:|----------------------------:|----------------------------:|----------------------------:|-------------------------:|:-----------------------------------------------------------------------------|:---------------------------------------------------------------------------------|:------------------------------------------------------------------------------------------|:------------------|:-----------------|
| v8_baseline_return_priority              | current_best_return_priority | 0.653818 |          0.560843 |  1.99153 | -0.3283   |             0.636101 |                 0.10803  |              0.145848  |                    0.6 |                    0.168601 |                    0.389378 |                    0.541001 |                0.139524  | Stronger cost-adjusted CAGR than 0p05; still execution-sensitive.            | Higher high-beta exposure; MSTR/TQQQ/QLD/SOXL contribution must be monitored.    | Return-priority research baseline; current best, not a live trading recommendation.       | False             | False            |
| v8_2_high_beta_penalty_0p05_risk_control | risk_control_variant         | 0.540441 |          0.451554 |  1.6882  | -0.320129 |             1.07682  |                 0.208314 |              0.0714801 |                    0.2 |                    0.186514 |                    0.447073 |                    0.610805 |                0.0219566 | 50bps CAGR barely clears 0.4487 threshold; 75/100bps stress weakens quickly. | High-beta exposure lower, but top5 positive month share is higher than baseline. | Risk-control variant for human review; not return-optimal and not a baseline replacement. | False             | False            |

## 10. 当前最终建议

- 当前 best：`v8_baseline_return_priority`
- 风险控制备选：`v8_2_high_beta_penalty_0p05`
- 不自动替代 best
- 不进入 v9
- 不继续 overlay/reranking 微调

## 11. 不允许进入 v9 的原因

当前主要问题不是需要进入 v9，而是历史窗口偏短、universe 设计偏窄、ranking objective 与 validation framework 需要重构。进入 v9 前必须另行立项并重新设计研究框架。

## 12. 后续研究路线图

下一阶段应回到底层研究：更长历史数据、universe 分层设计、stock selection model 重构、严格 walk-forward/regime split、冻结策略 paper trading。

## 13. Evidence Package Index

| package_name                               | package_type   | exists   | purpose                                                                  | role_in_decision                                                                           |
|:-------------------------------------------|:---------------|:---------|:-------------------------------------------------------------------------|:-------------------------------------------------------------------------------------------|
| v8_baseline_run                            | run_dir        | True     | v8 baseline paper trading output and current return-priority reference.  | Defines current best strategy metrics and baseline holdings/NAV.                           |
| v8_final_closeout                          | zip            | True     | Original v8 closeout evidence and final baseline status at v8 milestone. | Confirms v8 baseline as credible but execution-sensitive.                                  |
| v8_1_cycle05_market_regime_overlay_plateau | zip            | True     | v8.1 overlay plateau run.                                                | Supports stopping the v8.1 overlay branch.                                                 |
| v8_2_stock_selection_layer_diagnostic      | zip            | True     | Stock selection layer diagnostic before full audit replay.               | Showed old v8 outputs were selected-only and unsafe for ex-ante reranking.                 |
| v8_2_bounded_audit_replay                  | zip            | True     | Full candidate score/rank audit replay.                                  | Created complete decision_date x candidate trail and reproduced baseline selection.        |
| v8_2_gate_aware_reranking_replay           | zip            | True     | Bounded gate-aware reranking replay.                                     | Found no accepted/strong reranking candidate; highlighted high-beta penalty as diagnostic. |
| v8_2_high_beta_penalty_robustness          | zip            | True     | Targeted high-beta penalty robustness review.                            | Identified high_beta_penalty_0p05 as accepted risk-control candidate.                      |
| v8_2_0p05_final_validation                 | zip            | True     | Final validation pack for high_beta_penalty_0p05.                        | Classified 0p05 as risk_control_variant, not baseline replacement.                         |

## 14. Output

- Output directory: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\v8_v8_2_final_closeout_20260501_190000`
- Zip: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\us_stock_selection_quant_lab_v8_v8_2_final_closeout_20260501_190000.zip`
