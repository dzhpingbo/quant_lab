# ChatGPT Review Packet

## Run

- run_id: `formal_v9_20260505_223858`
- run_dir: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\formal_v9_20260505_223858`
- zip_path: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\us_stock_selection_formal_v9_20260505_223858.zip`
- published_at: `2026-05-05T22:39:08`

## 本轮目标

本轮目标：执行 formal v9；仅小幅科技成长池，不扩 Nasdaq100/S&P500，不进入 v10，不交易化。

## 新增/修改文件

- `quant_lab/us_stock_selection/canonical_replay_engine.py`
- `quant_lab/us_stock_selection/formal_v9_reporting.py`
- `quant_lab/us_stock_selection/formal_v9_runner.py`
- `scripts/us_stock_selection/39_run_formal_v9.py`

## 核心结果 / RUN_SUMMARY

# RUN_SUMMARY

本轮目标：执行 formal v9；仅小幅科技成长池，不扩 Nasdaq100/S&P500，不进入 v10，不交易化。

新 run 目录：`E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\formal_v9_20260505_223858`
zip 路径：`E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\us_stock_selection_formal_v9_20260505_223858.zip`

核心结论：
- classification: `formal_v9_failed_due_to_concentration`
- Pool A reproduction pass: `True`
- Formal v9 gate pass: `False`
- Performance gate pass: `False`
- Effective universe count: `64`
- Effective small-growth count: `45`
- Effective new growth count: `28`
- Excluded ticker count: `1`
- Allow enter v10: `False`

Pool A reproduction CAGR/Calmar/MaxDD：`0.23222486228552475` / `0.5584103684950428` / `-0.41586774778446167`
Pool A + growth CAGR/Calmar/MaxDD：`0.07977910174833758` / `0.1866013926654182` / `-0.4275375473289412`
Small growth only CAGR/Calmar/MaxDD：`0.06344030769851905` / `0.1439953649418388` / `-0.4405718734359487`
Ex-high-vol CAGR/Calmar/MaxDD：`-0.05862532569319279` / `-0.15263030265773103` / `-0.38410017324448575`

原因：Formal v9.1 score replay is too concentrated or depends too much on MSTR/COIN/PLTR.

本轮没有扩 Nasdaq100/S&P500，没有进入 v10，没有下载行情，没有连接券商，没有自动 commit/push。


## 核心指标

|     cagr |   max_drawdown |   calmar |
|---------:|---------------:|---------:|
| 0.209633 |      -0.190599 | 1.09986  |
| 0.239292 |      -0.227683 | 1.05099  |
| 0.384244 |      -0.4229   | 0.908594 |
| 0.49246  |      -0.580401 | 0.848483 |

## Gate / Verdict

```json
{
  "classification": "formal_v9_failed_due_to_concentration",
  "run_scope": "formal_v9_rerun_v9_1_provider_alpha360_cache_lgbmodel_score_provenance",
  "formal_provider_uri": "C:\\Users\\Administrator\\.qlib\\qlib_data\\us_data_local_2026_v91_growth",
  "formal_feature_cache_dir": "E:\\dzhwork\\quant\\quant_lab\\outputs\\us_stock_selection\\v9_1_growth_data_onboarding_20260504_230014\\v9_1_feature_cache",
  "formal_score_audit_path": "E:\\dzhwork\\quant\\quant_lab\\outputs\\us_stock_selection\\v9_1_growth_data_onboarding_20260504_230014\\v9_1_score_provenance\\monthly_score_rank_audit.csv",
  "price_source": "local Qlib provider bin $close",
  "adj_close_policy": "provider $close is adjusted close from v9.1 provider build; no unified replay result is used",
  "volume_source": "local Qlib provider bin $volume",
  "replay_engine": "canonical_replay_engine",
  "frozen_mainline": "Alpha360 + LGBModel + label_5d + top5_ytdcap80p_derisk100p",
  "latest_gate_passed_strategy": "v8.2 frozen Pool A top5_ytdcap80p_derisk100p",
  "pool_a_reproduction_pass": true,
  "pool_a_reproduction_cagr": 0.23222486228552475,
  "pool_a_reproduction_calmar": 0.5584103684950428,
  "pool_a_reproduction_max_drawdown": -0.41586774778446167,
  "pool_a_plus_growth_cagr": 0.07977910174833758,
  "pool_a_plus_growth_calmar": 0.1866013926654182,
  "pool_a_plus_growth_max_drawdown": -0.4275375473289412,
  "small_growth_only_cagr": 0.06344030769851905,
  "small_growth_only_calmar": 0.1439953649418388,
  "small_growth_only_max_drawdown": -0.4405718734359487,
  "ex_high_vol_cagr": -0.05862532569319279,
  "ex_high_vol_calmar": -0.15263030265773103,
  "ex_high_vol_max_drawdown": -0.38410017324448575,
  "formal_v9_gate_pass": false,
  "formal_v9_performance_gate_pass": false,
  "single_year_share": 0.5989535092606022,
  "top_ticker": "PLTR",
  "top_ticker_share": 0.13620150759157185,
  "remove_top_year_cagr": -0.060445817431014404,
  "remove_top_year_calmar": -0.1627179943643681,
  "remove_top_ticker_cagr": -0.0047778226770731624,
  "remove_top_ticker_calmar": -0.011155839528131069,
  "depends_on_coin_mstr_pltr": true,
  "controversial_mstr_coin_pltr_share": 0.23357283786103467,
  "effective_universe_count": 64,
  "effective_small_growth_count": 45,
  "effective_new_growth_count": 28,
  "effective_new_growth_tickers": "ABNB,AFRM,AMAT,APP,ARM,ASML,COIN,DASH,DDOG,FTNT,KLAC,LRCX,MDB,MPWR,MRVL,OKTA,ON,PATH,PINS,RBLX,ROKU,S,SNAP,SPOT,TEAM,TSM,U,ZS",
  "excluded_ticker_count": 1,
  "excluded_tickers": "SQ",
  "v9_original_results_discarded": true,
  "unified_replay_role": "audit_evidence_only_not_formal_result",
  "allow_enter_v10": false,
  "allow_trade_execution": false,
  "requires_human_review": true,
  "next_allowed_action": "Stop for human review. Formal v9 did not authorize v10; only review the v9.1 formal rerun evidence and, if approved, continue v9 audit/repair within the same pool.",
  "reason": "Formal v9.1 score replay is too concentrated or depends too much on MSTR/COIN/PLTR.",
  "zip_path": "E:\\dzhwork\\quant\\quant_lab\\outputs\\us_stock_selection\\us_stock_selection_formal_v9_20260505_223858.zip",
  "run_dir": "E:\\dzhwork\\quant\\quant_lab\\outputs\\us_stock_selection\\formal_v9_20260505_223858"
}
```

## 当前分类

- classification: `formal_v9_failed_due_to_concentration`
- allow_enter_v9: ``
- allow_enter_v10: `False`

## 不通过原因 / 已知限制

- verdict.reason: `Formal v9.1 score replay is too concentrated or depends too much on MSTR/COIN/PLTR.`
- - classification: `formal_v9_failed_due_to_concentration`
- - classification: `formal_v9_failed_due_to_concentration`
- - 见 `formal_v9_excluded_tickers.csv`；剔除行不允许进入 formal TopK。
- - 不允许。
- | fit_failed_count_zero                 | True   | 0                                                                                                                                                    | 0                                                                                                                    | hard_block |

## 需要 ChatGPT 审阅的问题

1. 当前 classification 是否与 gate 证据一致？
2. 是否存在未来函数、样本选择偏差、执行口径或数据质量问题？
3. 是否应批准进入下一阶段，还是要求补验证？
4. 如果进入下一阶段，边界条件是否足够明确？

## Codex 建议的下一步

# NEXT_STEPS

当前状态：`formal_v9_failed_due_to_concentration`。

下一步只允许：
- 审阅 formal v9 结果和 eligibility 缺口。
- 若要继续 v9，先补 canonical provider/score evidence 或缩小为当前有证据 universe。

禁止：
- 不进入 v10。
- 不扩 Nasdaq100/S&P500/全市场。
- 不交易化，不连接券商，不下单。
- 不复用旧 v9 original metrics 或 unified replay 作为正式结果。


## 关键表格摘要

| csv                                                                                                                             |   size_mb | bridge_mode      |
|:--------------------------------------------------------------------------------------------------------------------------------|----------:|:-----------------|
| outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\_pool_a_reproduction_internal\formal_v82_annual_returns.csv      |     0     | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\_pool_a_reproduction_internal\formal_v82_benchmark_metrics.csv   |     0.001 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\_pool_a_reproduction_internal\formal_v82_daily_nav.csv           |     0.043 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\_pool_a_reproduction_internal\formal_v82_decision_ledger.csv     |     0.007 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\_pool_a_reproduction_internal\formal_v82_gate_detail.csv         |     0.001 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\_pool_a_reproduction_internal\formal_v82_metrics.csv             |     0.001 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\_pool_a_reproduction_internal\formal_v82_monthly_holdings.csv    |     0.104 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\_pool_a_reproduction_internal\formal_v82_monthly_returns.csv     |     0.001 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\_pool_a_reproduction_internal\formal_v82_score_rank_audit.csv    |     0.401 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\_pool_a_reproduction_internal\formal_v82_ticker_contribution.csv |     0.002 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\_pool_a_reproduction_internal\formal_v82_trades.csv              |     0.009 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\formal_v9_benchmark_comparison.csv                               |     0.001 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\formal_v9_cost_sensitivity.csv                                   |     0.004 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\formal_v9_daily_nav.csv                                          |     0.19  | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\formal_v9_decision_ledger.csv                                    |     0.018 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\formal_v9_derisk_log.csv                                         |     0.171 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\formal_v9_ex_high_vol_metrics.csv                                |     0.001 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\formal_v9_excluded_tickers.csv                                   |     0.001 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\formal_v9_gate_detail.csv                                        |     0.001 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\formal_v9_growth_only_metrics.csv                                |     0.001 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\formal_v9_input_audit_checks.csv                                 |     0.003 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\formal_v9_monthly_holdings.csv                                   |     0.556 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\formal_v9_pool_a_plus_growth_metrics.csv                         |     0.001 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\formal_v9_pool_a_reproduction_check.csv                          |     0     | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\formal_v9_pool_a_reproduction_metrics.csv                        |     0.001 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\formal_v9_remove_top_ticker.csv                                  |     0.001 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\formal_v9_remove_top_year.csv                                    |     0.001 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\formal_v9_score_rank_audit.csv                                   |     0.564 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\formal_v9_ticker_contribution.csv                                |     0.014 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\formal_v9_trades.csv                                             |     0.039 | copy_if_selected |

## 重要 CSV 文件路径

- `outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\_pool_a_reproduction_internal\formal_v82_annual_returns.csv`
- `outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\_pool_a_reproduction_internal\formal_v82_benchmark_metrics.csv`
- `outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\_pool_a_reproduction_internal\formal_v82_daily_nav.csv`
- `outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\_pool_a_reproduction_internal\formal_v82_decision_ledger.csv`
- `outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\_pool_a_reproduction_internal\formal_v82_gate_detail.csv`
- `outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\_pool_a_reproduction_internal\formal_v82_metrics.csv`
- `outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\_pool_a_reproduction_internal\formal_v82_monthly_holdings.csv`
- `outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\_pool_a_reproduction_internal\formal_v82_monthly_returns.csv`
- `outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\_pool_a_reproduction_internal\formal_v82_score_rank_audit.csv`
- `outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\_pool_a_reproduction_internal\formal_v82_ticker_contribution.csv`
- `outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\_pool_a_reproduction_internal\formal_v82_trades.csv`
- `outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\formal_v9_benchmark_comparison.csv`
- `outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\formal_v9_cost_sensitivity.csv`
- `outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\formal_v9_daily_nav.csv`
- `outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\formal_v9_decision_ledger.csv`
- `outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\formal_v9_derisk_log.csv`
- `outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\formal_v9_ex_high_vol_metrics.csv`
- `outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\formal_v9_excluded_tickers.csv`
- `outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\formal_v9_gate_detail.csv`
- `outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\formal_v9_growth_only_metrics.csv`
- `outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\formal_v9_input_audit_checks.csv`
- `outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\formal_v9_monthly_holdings.csv`
- `outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\formal_v9_pool_a_plus_growth_metrics.csv`
- `outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\formal_v9_pool_a_reproduction_check.csv`
- `outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\formal_v9_pool_a_reproduction_metrics.csv`
- `outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\formal_v9_remove_top_ticker.csv`
- `outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\formal_v9_remove_top_year.csv`
- `outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\formal_v9_score_rank_audit.csv`
- `outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\formal_v9_ticker_contribution.csv`
- `outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\formal_v9_trades.csv`
- `outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\formal_v9_universe_eligibility.csv`
- `outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\formal_v9_yearly_return.csv`
- `outputs\us_stock_selection\formal_v9_20260505_223858\formal_v9\formal_v9_ytd_cap_triggers.csv`

## selected_report.md excerpt

# Formal v9 Report

## Verdict

- classification: `formal_v9_failed_due_to_concentration`
- formal_v9_gate_pass: `False`
- formal_v9_performance_gate_pass: `False`
- Pool A reproduction pass: `True`
- effective universe count: `64`
- effective small-growth count: `45`
- effective new growth count: `28`
- allow_enter_v10: `False`
- requires_human_review: `True`
- zip_path: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\us_stock_selection_formal_v9_20260505_223858.zip`
- provider_uri: `C:\Users\Administrator\.qlib\qlib_data\us_data_local_2026_v91_growth`
- feature_cache: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_feature_cache\alpha360_feature_cache.parquet`
- score_audit: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_score_provenance\monthly_score_rank_audit.csv`
- replay_engine: `canonical_replay_engine`

## Required Answers

1. Pool A reproduction 是否复现 v8.2 canonical？
   - `True`。这是 v9.1 provider 下的 canonical v8.2 anchor 复现检查，见 `formal_v9_pool_a_reproduction_check.csv`。
2. v9 使用的正式 universe 是什么？
   - `formal_pool_a_plus_small_growth`。有效新增 growth ticker 数：`28`；ticker：`ABNB,AFRM,AMAT,APP,ARM,ASML,COIN,DASH,DDOG,FTNT,KLAC,LRCX,MDB,MPWR,MRVL,OKTA,ON,PATH,PINS,RBLX,ROKU,S,SNAP,SPOT,TEAM,TSM,U,ZS`。
3. 哪些 ticker 被剔除？原因是什么？
   - 见 `formal_v9_excluded_tickers.csv`；剔除行不允许进入 formal TopK。
4. Pool A + small growth 是否通过 v9 gate？
   - 最终 formal gate：`False`；性能 gate：`False`。细节见 `formal_v9_gate_detail.csv`。
5. small growth only 是否有价值？
   - 只能作为观察项；核心指标见下方 `formal_small_growth_only`，不能作为主结论。
6. 剔除高波动票后结果如何？
   - 见 `formal_pool_a_plus_small_growth_ex_high_vol`。
7. 扩池是否提升了 CAGR / Calmar / 稳定性？
   - 对比 `formal_pool_a_reproduction` 与 `formal_pool_a_plus_small_growth` 的 CAGR / Calmar / concentration / stress gate。
8. 是否增加了 single-year share 或 top ticker share？
   - 没有，主结果与 Pool A reproduction 相同。
9. 是否依赖 MSTR / COIN / PLTR？
   - `True`；贡献 share `0.23357283786103467`。
10. remove top year / remove top ticker 后是否仍有效？
    - remove top year CAGR/Calmar：`-0.060445817431014404` / `-0.1627179943643681`。
    - remove top ticker CAGR/Calmar：`-0.0047778226770731624` / `-0.011155839528131069`。
11. 成本压力是否仍过关？
    - Pool A + growth cost50 CAGR/Calmar：`0.015001217824288648` / `0.03400949915062373`。
12. 是否允许进入 v10？
    - 不允许。
13. 是否需要人工审阅？
    - 需要。
14. 下一步应扩科技成长池、行业主题池、还是停止扩池？
    - `Stop for human review. Formal v9 did not authorize v10; only review the v9.1 formal rerun evidence and, if approved, continue v9 audit/repair within the same pool.`。不得进入 v10，也不得扩 Nasdaq100/S&P500。

## Input Audit

| check                                 | pass   | value                                                                                                                                                | expected                                                                                                             | severity   |
|:--------------------------------------|:-------|:-----------------------------------------------------------------------------------------------------------------------------------------------------|:---------------------------------------------------------------------------------------------------------------------|:-----------|
| provider_uri_is_v9_1                  | True   | C:\Users\Administrator\.qlib\qlib_data\us_data_local_2026_v91_growth                                                                                 | C:\Users\Administrator\.qlib\qlib_data\us_data_local_2026_v91_growth                                                 | hard_block |
| provider_exists                       | True   | C:\Users\Administrator\.qlib\qlib_data\us_data_local_2026_v91_growth                                                                                 | exists                                                                                                               | hard_block |
| provider_calendar_exists              | True   | C:\Users\Administrator\.qlib\qlib_data\us_data_local_2026_v91_growth\calendars\day.txt                                                               | exists                                                                                                               | hard_block |
| provider_features_exists              | True   | C:\Users\Administrator\.qlib\qlib_data\us_data_local_2026_v91_growth\features                                                                        | exists                                                                                                               | hard_block |
| provider_health_ok                    | True   | True                                                                                                                                                 | True                                                                                                                 | hard_block |
| provider_calendar_end                 | True   | 2026-04-17                                                                                                                                           | 2026-04-17                                                                                                           | hard_block |
| feature_cache_status_completed        | True   | completed                                                                                                                                            | completed                                                                                                            | hard_block |
| feature_cache_provider_match          | True   | C:\Users\Administrator\.qlib\qlib_data\us_data_local_2026_v91_growth                                                                                 | C:\Users\Administrator\.qlib\qlib_data\us_data_local_2026_v91_growth                                                 | hard_block |
| feature_set_alpha360                  | True   | Alpha360                                                                                                                                             | Alpha360                                                                                                             | hard_block |
| feature_count_360                     | True   | 360                                                                                                                                                  | 360                                                                                                                  | hard_block |
| feature_cache_rows_positive           | True   | 96872                                                                                                                                                | >0                                                                                                                   | hard_block |
| feature_missing_rate_zero             | True   | 0.0                                                                                                                                                  | 0.0                                                                                                                  | hard_block |
| label_5d_available_in_cache           | True   | 96762                                                                                                                                                | >0                                                                                                                   | hard_block |
| score_source_status_completed         | True   | completed                                                                                                                                            | completed                                                                                                            | hard_block |
| score_source_provider_match           | True   | C:\Users\Administrator\.qlib\qlib_data\us_data_local_2026_v91_growth                                                                                 | C:\Users\Administrator\.qlib\qlib_data\us_data_local_2026_v91_growth                                                 | hard_block |
| score_source_feature_cache_match      | True   | E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_feature_cache                                 | E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_feature_cache | hard_block |
| score_source_alpha360                 | True   | Alpha360                                                                                                                                             | Alpha360                                                                                                             | hard_block |
| score_source_lgbmodel                 | True   | LGBModel                                                                                                                                             | LGBModel                                                                                                             | hard_block |
| score_source_label_5d                 | True   | label_5d                                                                                                                                             | label_5d                                                                                                             | hard_block |
| score_month_count_18                  | True   | 18                                                                                                                                                   | 18                                                                                                                   | hard_block |
| score_row_count_positive              | True   | 1147                                                                                                                                                 | >0                                                                                                                   | hard_block |
| fit_failed_count_zero                 | True   | 0                                                                                                                                                    | 0                                                                                                                    | hard_block |
| fit_warning_count_zero                | True   | 0                                                                                                                                                    | 0                                                                                                                    | hard_block |
| score_audit_exists                    | True   | E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\v9_1_growth_data_onboarding_20260504_230014\v9_1_score_provenance\monthly_score_rank_audit.csv | exists                                                                                                               | hard_block |
| score_audit_rows_match_metadata       | True   | 1147                                                                                                                                                 | 1147                                                                                                                 | hard_block |
| score_audit_months_match_metadata     | True   | 18                                                                                                                                                   | 18                                                                                                                   | hard_block |
| eligibility_file_

...[truncated for bridge packet]...
