# ChatGPT Review Packet

## Run

- run_id: `formal_v9_20260504_215420`
- run_dir: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\formal_v9_20260504_215420`
- zip_path: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\us_stock_selection_formal_v9_20260504_215420.zip`
- published_at: `2026-05-04T21:54:40`

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

新 run 目录：`E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\formal_v9_20260504_215420`
zip 路径：`E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\us_stock_selection_formal_v9_20260504_215420.zip`

核心结论：
- classification: `formal_v9_failed_due_to_eligibility`
- Pool A reproduction pass: `True`
- Formal v9 gate pass: `False`
- Performance gate pass: `True`
- Effective universe count: `36`
- Effective small-growth count: `17`
- Effective new growth count: `0`
- Excluded ticker count: `29`
- Allow enter v10: `False`

Pool A reproduction CAGR/Calmar/MaxDD：`0.6421262430680639` / `1.6339698829869318` / `-0.39298536022845376`
Pool A + growth CAGR/Calmar/MaxDD：`0.6421262430680639` / `1.6339698829869318` / `-0.39298536022845376`
Small growth only CAGR/Calmar/MaxDD：`0.6064557583507033` / `1.721970035377187` / `-0.3521871727679994`
Ex-high-vol CAGR/Calmar/MaxDD：`0.6566465156253447` / `1.9533577446623147` / `-0.3361629570516086`

原因：Pool A reproduction passed, but no new small-growth ticker beyond Pool A had both canonical provider data and formal frozen score provenance, so the formal main universe degenerates to Pool A.

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
  "classification": "formal_v9_failed_due_to_eligibility",
  "pool_a_reproduction_pass": true,
  "pool_a_reproduction_cagr": 0.6421262430680639,
  "pool_a_reproduction_calmar": 1.6339698829869318,
  "pool_a_reproduction_max_drawdown": -0.39298536022845376,
  "pool_a_plus_growth_cagr": 0.6421262430680639,
  "pool_a_plus_growth_calmar": 1.6339698829869318,
  "pool_a_plus_growth_max_drawdown": -0.39298536022845376,
  "small_growth_only_cagr": 0.6064557583507033,
  "small_growth_only_calmar": 1.721970035377187,
  "small_growth_only_max_drawdown": -0.3521871727679994,
  "ex_high_vol_cagr": 0.6566465156253447,
  "ex_high_vol_calmar": 1.9533577446623147,
  "ex_high_vol_max_drawdown": -0.3361629570516086,
  "formal_v9_gate_pass": false,
  "formal_v9_performance_gate_pass": true,
  "single_year_share": 0.4968386021801039,
  "top_ticker": "INTC",
  "top_ticker_share": 0.137939380670818,
  "remove_top_year_cagr": 0.5215872877272436,
  "remove_top_year_calmar": 1.3272435579382131,
  "remove_top_ticker_cagr": 0.4896538831502253,
  "remove_top_ticker_calmar": 1.3265102205318462,
  "depends_on_coin_mstr_pltr": false,
  "controversial_mstr_coin_pltr_share": 0.1750111368026543,
  "effective_universe_count": 36,
  "effective_small_growth_count": 17,
  "effective_new_growth_count": 0,
  "effective_new_growth_tickers": "",
  "excluded_ticker_count": 29,
  "excluded_tickers": "ABNB,AFRM,AMAT,APP,ARM,ASML,COIN,DASH,DDOG,FTNT,KLAC,LRCX,MDB,MPWR,MRVL,OKTA,ON,PATH,PINS,RBLX,ROKU,S,SNAP,SPOT,SQ,TEAM,TSM,U,ZS",
  "v9_original_results_discarded": true,
  "unified_replay_role": "audit_evidence_only_not_formal_result",
  "allow_enter_v10": false,
  "allow_trade_execution": false,
  "requires_human_review": true,
  "next_allowed_action": "Stop for human review. Formal v9 did not authorize v10; missing canonical provider/score evidence blocks most new small-growth tickers.",
  "reason": "Pool A reproduction passed, but no new small-growth ticker beyond Pool A had both canonical provider data and formal frozen score provenance, so the formal main universe degenerates to Pool A.",
  "zip_path": "E:\\dzhwork\\quant\\quant_lab\\outputs\\us_stock_selection\\us_stock_selection_formal_v9_20260504_215420.zip",
  "run_dir": "E:\\dzhwork\\quant\\quant_lab\\outputs\\us_stock_selection\\formal_v9_20260504_215420"
}
```

## 当前分类

- classification: `formal_v9_failed_due_to_eligibility`
- allow_enter_v9: ``
- allow_enter_v10: `False`

## 不通过原因 / 已知限制

- verdict.reason: `Pool A reproduction passed, but no new small-growth ticker beyond Pool A had both canonical provider data and formal frozen score provenance, so the formal main universe degenerates to Pool A.`
- - classification: `formal_v9_failed_due_to_eligibility`
- - classification: `formal_v9_failed_due_to_eligibility`
- - 不允许。

## 需要 ChatGPT 审阅的问题

1. 当前 classification 是否与 gate 证据一致？
2. 是否存在未来函数、样本选择偏差、执行口径或数据质量问题？
3. 是否应批准进入下一阶段，还是要求补验证？
4. 如果进入下一阶段，边界条件是否足够明确？

## Codex 建议的下一步

# NEXT_STEPS

当前状态：`formal_v9_failed_due_to_eligibility`。

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
| outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\_pool_a_reproduction_internal\formal_v82_annual_returns.csv      |     0     | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\_pool_a_reproduction_internal\formal_v82_benchmark_metrics.csv   |     0.001 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\_pool_a_reproduction_internal\formal_v82_daily_nav.csv           |     0.043 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\_pool_a_reproduction_internal\formal_v82_decision_ledger.csv     |     0.007 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\_pool_a_reproduction_internal\formal_v82_gate_detail.csv         |     0.001 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\_pool_a_reproduction_internal\formal_v82_metrics.csv             |     0.001 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\_pool_a_reproduction_internal\formal_v82_monthly_holdings.csv    |     0.104 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\_pool_a_reproduction_internal\formal_v82_monthly_returns.csv     |     0.001 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\_pool_a_reproduction_internal\formal_v82_score_rank_audit.csv    |     0.401 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\_pool_a_reproduction_internal\formal_v82_ticker_contribution.csv |     0.002 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\_pool_a_reproduction_internal\formal_v82_trades.csv              |     0.009 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\formal_v9_benchmark_comparison.csv                               |     0.001 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\formal_v9_cost_sensitivity.csv                                   |     0.004 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\formal_v9_daily_nav.csv                                          |     0.187 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\formal_v9_decision_ledger.csv                                    |     0.018 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\formal_v9_derisk_log.csv                                         |     0.169 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\formal_v9_ex_high_vol_metrics.csv                                |     0.001 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\formal_v9_excluded_tickers.csv                                   |     0.005 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\formal_v9_gate_detail.csv                                        |     0.001 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\formal_v9_growth_only_metrics.csv                                |     0.001 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\formal_v9_monthly_holdings.csv                                   |     0.499 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\formal_v9_pool_a_plus_growth_metrics.csv                         |     0.001 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\formal_v9_pool_a_reproduction_check.csv                          |     0     | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\formal_v9_pool_a_reproduction_metrics.csv                        |     0.001 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\formal_v9_remove_top_ticker.csv                                  |     0.001 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\formal_v9_remove_top_year.csv                                    |     0.001 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\formal_v9_score_rank_audit.csv                                   |     0.31  | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\formal_v9_ticker_contribution.csv                                |     0.009 | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\formal_v9_trades.csv                                             |     0.04  | copy_if_selected |
| outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\formal_v9_universe_eligibility.csv                               |     0.011 | copy_if_selected |

## 重要 CSV 文件路径

- `outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\_pool_a_reproduction_internal\formal_v82_annual_returns.csv`
- `outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\_pool_a_reproduction_internal\formal_v82_benchmark_metrics.csv`
- `outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\_pool_a_reproduction_internal\formal_v82_daily_nav.csv`
- `outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\_pool_a_reproduction_internal\formal_v82_decision_ledger.csv`
- `outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\_pool_a_reproduction_internal\formal_v82_gate_detail.csv`
- `outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\_pool_a_reproduction_internal\formal_v82_metrics.csv`
- `outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\_pool_a_reproduction_internal\formal_v82_monthly_holdings.csv`
- `outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\_pool_a_reproduction_internal\formal_v82_monthly_returns.csv`
- `outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\_pool_a_reproduction_internal\formal_v82_score_rank_audit.csv`
- `outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\_pool_a_reproduction_internal\formal_v82_ticker_contribution.csv`
- `outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\_pool_a_reproduction_internal\formal_v82_trades.csv`
- `outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\formal_v9_benchmark_comparison.csv`
- `outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\formal_v9_cost_sensitivity.csv`
- `outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\formal_v9_daily_nav.csv`
- `outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\formal_v9_decision_ledger.csv`
- `outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\formal_v9_derisk_log.csv`
- `outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\formal_v9_ex_high_vol_metrics.csv`
- `outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\formal_v9_excluded_tickers.csv`
- `outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\formal_v9_gate_detail.csv`
- `outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\formal_v9_growth_only_metrics.csv`
- `outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\formal_v9_monthly_holdings.csv`
- `outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\formal_v9_pool_a_plus_growth_metrics.csv`
- `outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\formal_v9_pool_a_reproduction_check.csv`
- `outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\formal_v9_pool_a_reproduction_metrics.csv`
- `outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\formal_v9_remove_top_ticker.csv`
- `outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\formal_v9_remove_top_year.csv`
- `outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\formal_v9_score_rank_audit.csv`
- `outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\formal_v9_ticker_contribution.csv`
- `outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\formal_v9_trades.csv`
- `outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\formal_v9_universe_eligibility.csv`
- `outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\formal_v9_yearly_return.csv`
- `outputs\us_stock_selection\formal_v9_20260504_215420\formal_v9\formal_v9_ytd_cap_triggers.csv`

## selected_report.md excerpt

# Formal v9 Report

## Verdict

- classification: `formal_v9_failed_due_to_eligibility`
- formal_v9_gate_pass: `False`
- formal_v9_performance_gate_pass: `True`
- Pool A reproduction pass: `True`
- effective universe count: `36`
- effective small-growth count: `17`
- effective new growth count: `0`
- allow_enter_v10: `False`
- requires_human_review: `True`
- zip_path: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\us_stock_selection_formal_v9_20260504_215420.zip`

## Required Answers

1. Pool A reproduction 是否复现 v8.2 canonical？
   - `True`。复现检查见 `formal_v9_pool_a_reproduction_check.csv`。
2. v9 使用的正式 universe 是什么？
   - `formal_pool_a_plus_small_growth`。由于当前 canonical provider/score source 中没有新的 small-growth 增量 ticker，主 universe 实际退化为 Pool A。
3. 哪些 ticker 被剔除？原因是什么？
   - 见 `formal_v9_excluded_tickers.csv`；主要原因是缺少 canonical Qlib provider bin 或缺少 formal Alpha360/LGB score source。
4. Pool A + small growth 是否通过 v9 gate？
   - 最终 formal gate：`False`；性能 gate：`True`。最终 gate 因有效新增 growth 数为 0 被阻断。
5. small growth only 是否有价值？
   - 只能作为观察项；核心指标见下方 `formal_small_growth_only`，不能作为主结论。
6. 剔除高波动票后结果如何？
   - 见 `formal_pool_a_plus_small_growth_ex_high_vol`。
7. 扩池是否提升了 CAGR / Calmar / 稳定性？
   - 没有形成真实扩池，Pool A + growth 与 Pool A reproduction 指标相同。
8. 是否增加了 single-year share 或 top ticker share？
   - 没有，主结果与 Pool A reproduction 相同。
9. 是否依赖 MSTR / COIN / PLTR？
   - `False`；贡献 share `0.1750111368026543`。
10. remove top year / remove top ticker 后是否仍有效？
    - remove top year CAGR/Calmar：`0.5215872877272436` / `1.3272435579382131`。
    - remove top ticker CAGR/Calmar：`0.4896538831502253` / `1.3265102205318462`。
11. 成本压力是否仍过关？
    - Pool A + growth cost50 CAGR/Calmar：`0.5406128633202154` / `1.3453478263901464`。
12. 是否允许进入 v10？
    - 不允许。
13. 是否需要人工审阅？
    - 需要。
14. 下一步应扩科技成长池、行业主题池、还是停止扩池？
    - 先补 canonical provider/score evidence 或重新定义 formal v9 数据覆盖；在当前证据下不应进入 v10，也不应扩 Nasdaq100/S&P500。

## Core Metrics

### Pool A Reproduction

- universe_name: `formal_pool_a_reproduction`
- ticker_count: `36`
- cagr: `0.642126`
- calmar: `1.633970`
- max_drawdown: `-0.392985`
- cost50_t1_cagr: `0.540613`
- cost50_t1_calmar: `1.345348`
- single_year_share: `0.496839`
- top_ticker: `INTC`
- top_ticker_share: `0.137939`
- remove_top_year_cagr: `0.521587`
- remove_top_year_calmar: `1.327244`
- remove_top_ticker_cagr: `0.489654`
- remove_top_ticker_calmar: `1.326510`
- depends_on_coin_mstr_pltr: `False`
- controversial_mstr_coin_pltr_share: `0.175011`


### Pool A + Small Growth

- universe_name: `formal_pool_a_plus_small_growth`
- ticker_count: `36`
- cagr: `0.642126`
- calmar: `1.633970`
- max_drawdown: `-0.392985`
- cost50_t1_cagr: `0.540613`
- cost50_t1_calmar: `1.345348`
- single_year_share: `0.496839`
- top_ticker: `INTC`
- top_ticker_share: `0.137939`
- remove_top_year_cagr: `0.521587`
- remove_top_year_calmar: `1.327244`
- remove_top_ticker_cagr: `0.489654`
- remove_top_ticker_calmar: `1.326510`
- depends_on_coin_mstr_pltr: `False`
- controversial_mstr_coin_pltr_share: `0.175011`


### Small Growth Only

- universe_name: `formal_small_growth_only`
- ticker_count: `17`
- cagr: `0.606456`
- calmar: `1.721970`
- max_drawdown: `-0.352187`
- cost50_t1_cagr: `0.508466`
- cost50_t1_calmar: `1.415431`
- single_year_share: `0.489521`
- top_ticker: `MSTR`
- top_ticker_share: `0.171530`
- remove_top_year_cagr: `0.447578`
- remove_top_year_calmar: `1.771774`
- remove_top_ticker_cagr: `0.451152`
- remove_top_ticker_calmar: `1.434998`
- depends_on_coin_mstr_pltr: `True`
- controversial_mstr_coin_pltr_share: `0.325189`


### Ex High Vol

- universe_name: `formal_pool_a_plus_small_growth_ex_high_vol`
- ticker_count: `34`
- cagr: `0.656647`
- calmar: `1.953358`
- max_drawdown: `-0.336163`
- cost50_t1_cagr: `0.552874`
- cost50_t1_calmar: `1.604352`
- single_year_share: `0.617194`
- top_ticker: `NVDA`
- top_ticker_share: `0.154176`
- remove_top_year_cagr: `0.396557`
- remove_top_year_calmar: `1.770879`
- remove_top_ticker_cagr: `0.508920`
- remove_top_ticker_calmar: `1.646990`
- depends_on_coin_mstr_pltr: `False`
- controversial_mstr_coin_pltr_share: `0.000000`


## Pool A Reproduction Check

| metric            |   formal_v82_baseline |   formal_pool_a_reproduction |         diff |   tolerance | pass_check   |
|:------------------|----------------------:|-----------------------------:|-------------:|------------:|:-------------|
| cagr              |              0.642126 |                     0.642126 |  0           |       0.005 | True         |
| max_drawdown      |             -0.392985 |                    -0.392985 | -5.55112e-17 |       0.005 | True         |
| calmar            |              1.63397  |                     1.63397  |  0           |       0.03  | True         |
| single_year_share |              0.496839 |                     0.496839 |  0           |       0.02  | True         |
| top_ticker_share  |              0.137939 |                     0.137939 |  0           |       0.02  | True         |

## Gate Detail

| gate                                |    value |   threshold | operator   | pass   |
|:------------------------------------|---------:|------------:|:-----------|:-------|
| cagr_20                             | 0.642126 |    0.2      | >=         | True   |
| calmar_1                            | 1.63397  |    1        | >=         | True   |
| cost50_t1_cagr_20                   | 0.540613 |    0.2      | >=         | True   |
| cost50_t1_calmar_1                  | 1.34535  |    1        | >=         | True   |
| single_year_share_50                | 0.496839 |    0.5      | <=         | True   |
| top_ticker_share_30                 | 0.137939 |    0.3      | <=         | True   |
| remove_top_year_cagr_20             | 0.521587 |    0.2      | >=         | True   |
| remove_top_year_calmar_1            | 1.32724  |    1        | >=         | True   |
| remove_top_ticker_cagr_20           | 0.489654 |    0.2      | >=         | True   |
| remove_top_ticker_calmar_1          | 1.32651  |    1        | >=         | True   |
| no_leakage                          | 1        |    1        | is         | True   |
| no_score_provenance_mismatch        | 1        |    1        | is         | True   |
| no_baseline_exception_pollution     | 1        |    1        | is         | True   |
| pool_a_reproduction_pass            | 1        |    1        | is         | True   |
| not_weaker_than_pool_a_cagr         | 0.642126 |    0.642126 | >=         | True   |
| not_weaker_than_pool_a_calmar       | 1.63397  |    1.63397  | >=         | True   |
| not_dependent_on_coin_mstr_pltr     | 0.175011 |    0.4      | <=         | True   |
| not_single_year_only                | 0.496839 |    0.5      | <=         | True   |
| no_method_window_mismatch           | 1        |    1        | is         | True   |
| no_price_source_mismatch            | 1        |    1        | is         | True   |
| effective_new_growth_count_positive | 0        |    1        | >=         | False  |

## Eligibility

| ticker   | small_growth_category    | is_pool_a   | is_small_growth_candidate   | in_canonical_provider   | in_formal_score_source   | first_provider_date   | last_provider_date   |   obs_before_first_decision |   eligible_decision_count | first_score_decision   | last_score_decision   | has_trailing_252d_score_evidence   | passes_dynamic_eligibility   | eligible_for_formal_v9   | exclude_reason                                                               | eligibility_evidence                                      | high_vol_note                         |
|:---------|:-------------------------|:------------|:----------------------------|:------------------------|:-------------------------|:----------------------|:---------------------|----------------------------:|--------------------------:|:-----------------------|:----------------------|:-----------------------------------|:-----------------------------|:-------------------------|:-----------------------------------------------------------------------------|:----------------------------------------------------------|:--------------------------------------|
| AAPL     | pool_a                   | True        | False                       | True                    | True                     | 2024-01-02            | 2026-04-17           |                         252 |                        18 | 2024-01-31             | 2026-03-31            | True                               | True                         | True                     |                                                                              | candidate_tradable_score_trail_with_trailing_252d_feature |                                       |
| ABNB     | platform_internet        | False       | True                        | False                   | False                    |                       |                      |                           0 |                         0 |                        |                       | False                              | False                        | False                    | missing_canonical_qlib_provider_bin;missing_formal_alpha360_lgb_score_source | not_eligible_for_formal_v9                                |                                       |
| ADBE     | ai_software_cloud,pool_a | True        | True                        | True                    | True                     | 2024-01-02            | 2026-04-17           |                         252 |                        18 | 2024-01-31             | 2026-03-31            | True                               | True                         | True                     |                                                                              | candidate_tradable_score_trail_with_trailing_252d_feature |                                       |
| AFRM     | high_vol_theme           | False       | True                        | False                   | False                    |                       |                      |                           0 |                         0 |                        |                       | False                              | False                        | False                    | missing_canonical_qlib_provider_bin;missing_formal_alpha360_lgb_score_source | not_eligible_for_formal_v9                                | high_vol_or_controversial_observation |
| AMAT     | semiconductor            | False       | True                        | False                   | False                    |                       |                      |                           0 |                         0 |                        |                       | False                              | False                        | False                    | missing_canonical_qlib_provider_bin;missing_formal_alpha360_lgb_score_source | not_eligible_for_formal_v9                                |                                       |
| AMD      | pool_a,semiconductor     | True        | True                        | True                    | True                     | 2024-01-02            | 2026-04-17           |                         252 |                        18 | 2024-01-31             | 2026-03-31            | True                               | True                         | True                     |                                                                              | candidate_tradable_score_trail_with_trailing_252d_feature |                                       |
| AMZN     | pool_a                   | True        | False                       | True                    | True                     | 2024-01-02            | 2026-04-17           |                         252 |                        18 | 2024-01-31             | 2026-03-31            | True                               | True                         | True                     |                                                                              | candidate_tr

...[truncated for bridge packet]...
