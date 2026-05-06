# v8.2 Frozen Formal Audit

Run ID: `v82_frozen_formal_audit_20260506_113454`

Audit directory: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\v82_frozen_formal_audit_20260506_113454`

Scope: v8.2 frozen Pool A `top5_ytdcap80p_derisk100p` only. No formal v9 repair, no v10, no pool expansion, no new strategy search, no trading, no broker/API workflow, no commit/push.

## 1. Executive Summary

- v8.2 formal replay completed: **True**.
- Gate result: **PASS**.
- Conclusion: **A. v8.2 formal replay audit passed; it can be upgraded to / retained as formal frozen baseline.**
- Can be formal frozen baseline: **True**.
- Current frozen mainline changed: **False**. It remains `v8.2 frozen Pool A top5_ytdcap80p_derisk100p`.
- Core metrics: CAGR **64.21%**, Calmar **1.6340**, MaxDD **-39.30%**, cost50 CAGR **54.06%**, cost50 Calmar **1.3453**.
- Main audit caveat: v8.2 score provenance is a frozen v8.1 runtime prediction trail with decision ledger and fit logs; it is not a newly trained v9.1 score source. This is acceptable for frozen-baseline audit and is not counted as a fatal provenance gap.

## 2. Evidence Availability

- Historical v8.2 run found: **True**.
- Score file found: **True**.
- Score provenance gap: **False**.
- Replay files regenerated in this audit: **True**.
- Holdings files regenerated in this audit: **True**.
- Price/volume policy check: v9.1 provider close and volume bins checked for v8.2 scored tickers.
- Optional context files missing:

| context_file                                                                     | exists | status                   | size_bytes |
| -------------------------------------------------------------------------------- | ------ | ------------------------ | ---------- |
| docs/chatgpt_bridge/context/quant_analysis_project_context_20260505.md           | False  | missing_optional_context | 0          |
| docs/chatgpt_bridge/context/us_stock_selection_best_practice_context_20260504.md | False  | missing_optional_context | 0          |

Evidence gaps:

_No data._

## 3. Formal Replay Check

| item             | formal_setting                                                               | status    | details                                                                                |
| ---------------- | ---------------------------------------------------------------------------- | --------- | -------------------------------------------------------------------------------------- |
| provider         | C:\Users\Administrator\.qlib\qlib_data\us_data_local_2026_v91_growth         | replayed  | v9.1 local Qlib provider used for current replay                                       |
| price_source     | local Qlib provider bin $close                                               | replayed  | canonical_replay_engine loaded close.day.bin                                           |
| adj_close_policy | provider $close adjusted-close policy                                        | audited   | no unified replay result used as formal output                                         |
| volume_source    | local Qlib provider bin $volume                                              | available | volume bins checked for v8.2 score tickers; volume is not used to optimize this replay |
| score_provenance | v8.1 Alpha360 LGBModel runtime score_rank_audit + decision ledger + fit logs | available | score_rows=648; score_months=18; no fit warnings in fit logs                           |
| universe         | Pool A only                                                                  | replayed  | tickers=36; no small-growth expansion                                                  |
| execution_costs  | monthly, T+1, cost=5bps, slippage=5bps; stress cost=50bps                    | replayed  | CAGR=0.6421262430680639; cost50 CAGR=0.5406128633202154                                |
| formal_gate      | v8.2 formal frozen gate                                                      | passed    | formal_gate_pass=True                                                                  |

Formal口径:

- replay engine: `canonical_replay_engine`
- provider: `C:\Users\Administrator\.qlib\qlib_data\us_data_local_2026_v91_growth`
- price source: `local Qlib provider bin $close`
- adj_close: `provider $close adjusted-close policy from v9.1 provider; unified replay not used as formal result`
- volume: `local Qlib provider bin $volume`
- universe: Pool A only, no small growth
- execution/cost: monthly, T+1, cost 5bps, slippage 5bps, cost50 stress preserved
- consistency: v8.2 frozen replay uses current formal provider/bin price chain and does not use unified replay as formal output.

## 4. Gate Check

| gate                            | value    | threshold | operator                     | pass |
| ------------------------------- | -------- | --------- | ---------------------------- | ---- |
| cagr_20                         | 0.642126 | 0.2       | >=                           | True |
| calmar_1                        | 1.63397  | 1         | >=                           | True |
| cost50_t1_cagr_20               | 0.540613 | 0.2       | >=                           | True |
| cost50_t1_calmar_1              | 1.34535  | 1         | >=                           | True |
| single_year_share_50            | 0.496839 | 0.5       | <=                           | True |
| top_ticker_share_30             | 0.137939 | 0.3       | <=                           | True |
| remove_top_year_cagr_20         | 0.521587 | 0.2       | >=                           | True |
| remove_top_year_calmar_1        | 1.32724  | 1         | >=                           | True |
| remove_top_ticker_cagr_20       | 0.489654 | 0.2       | >=                           | True |
| remove_top_ticker_calmar_1      | 1.32651  | 1         | >=                           | True |
| no_leakage                      | True     | True      | is                           | True |
| no_score_provenance_mismatch    | True     | True      | is                           | True |
| no_baseline_exception_pollution | True     | True      | is                           | True |
| coin_mstr_pltr_dependency_audit | 0.175011 | 0.4       | <= and top_ticker_not_in_set | True |

Key gate values:

- CAGR: **64.21%**
- Calmar: **1.6340**
- MaxDD: **-39.30%**
- cost50 CAGR: **54.06%**
- cost50 Calmar: **1.3453**
- single-year share: **49.68%**, top year `2024`
- top ticker share: **13.79%**, top ticker `INTC`
- remove top year CAGR/Calmar: **52.16%** / **1.3272**
- remove top ticker CAGR/Calmar: **48.97%** / **1.3265**
- COIN/MSTR/PLTR contribution share: **17.50%**; dependency gate pass: **True**

## 5. Robustness and Concentration

Concentration checks:

| check                    | value    | threshold | pass | details                                        |
| ------------------------ | -------- | --------- | ---- | ---------------------------------------------- |
| single_year_share        | 0.496839 | 0.5       | True | top year=2024                                  |
| top_ticker_share         | 0.137939 | 0.3       | True | top ticker=INTC                                |
| remove_top_year_cagr     | 0.521587 | 0.2       | True | removed year=2024                              |
| remove_top_ticker_cagr   | 0.489654 | 0.2       | True | removed ticker=INTC                            |
| coin_mstr_pltr_abs_share | 0.175011 | 0.4       | True | combined contribution share for COIN/MSTR/PLTR |
| top5_selection_frequency | 0.618026 | 0.7       | True | most frequently selected ticker=NVDA           |

Year contribution:

| year | year_return | abs_contribution_share | strategy_id               |
| ---- | ----------- | ---------------------- | ------------------------- |
| 2024 | 0.810693    | 0.496839               | top5_ytdcap80p_derisk100p |
| 2025 | 0.782045    | 0.479282               | top5_ytdcap80p_derisk100p |
| 2026 | -0.0389642  | 0.0238795              | top5_ytdcap80p_derisk100p |

Top ticker contribution:

| ticker | return_contribution | abs_share | strategy_id               |
| ------ | ------------------- | --------- | ------------------------- |
| INTC   | 0.234173            | 0.137939  | top5_ytdcap80p_derisk100p |
| PLTR   | 0.226567            | 0.133459  | top5_ytdcap80p_derisk100p |
| NVDA   | 0.209386            | 0.123338  | top5_ytdcap80p_derisk100p |
| NET    | 0.11881             | 0.0699849 | top5_ytdcap80p_derisk100p |
| MU     | 0.109643            | 0.0645851 | top5_ytdcap80p_derisk100p |
| SHOP   | 0.109017            | 0.0642161 | top5_ytdcap80p_derisk100p |
| AMD    | 0.08649             | 0.0509468 | top5_ytdcap80p_derisk100p |
| TSLA   | -0.0740877          | 0.0436413 | top5_ytdcap80p_derisk100p |
| MSTR   | 0.0705405           | 0.0415518 | top5_ytdcap80p_derisk100p |
| NOW    | 0.0665616           | 0.039208  | top5_ytdcap80p_derisk100p |
| QLD    | 0.0644834           | 0.0379839 | top5_ytdcap80p_derisk100p |
| CRWD   | 0.0637971           | 0.0375796 | top5_ytdcap80p_derisk100p |

Cost sensitivity:

| strategy_id               | universe_name            | cost_bps | slippage_bps | total_return | cagr     | max_drawdown | calmar  | sharpe  | sortino | volatility | win_rate | annual_turnover | exposure | worst_year | return_2022 | crash_2020_max_drawdown | daily_count |
| ------------------------- | ------------------------ | -------- | ------------ | ------------ | -------- | ------------ | ------- | ------- | ------- | ---------- | -------- | --------------- | -------- | ---------- | ----------- | ----------------------- | ----------- |
| top5_ytdcap80p_derisk100p | v82_frozen_formal_replay | 5        | 5            | 2.10101      | 0.642126 | -0.392985    | 1.63397 | 1.46341 | 2.5878  | 0.390596   | 0.443478 | 14.112          | 0.810435 | -0.0389642 | 0           | 0                       | 575         |
| top5_ytdcap80p_derisk100p | v82_frozen_formal_replay | 10       | 5            | 2.05137      | 0.630554 | -0.393972    | 1.6005  | 1.44508 | 2.55396 | 0.390669   | 0.443478 | 14.112          | 0.810435 | -0.0404593 | 0           | 0                       | 575         |
| top5_ytdcap80p_derisk100p | v82_frozen_formal_replay | 20       | 5            | 1.95437      | 0.607631 | -0.395944    | 1.53464 | 1.40831 | 2.48614 | 0.390848   | 0.441739 | 14.112          | 0.810435 | -0.0434459 | 0           | 0                       | 575         |
| top5_ytdcap80p_derisk100p | v82_frozen_formal_replay | 50       | 5            | 1.68083      | 0.540613 | -0.401839    | 1.34535 | 1.29734 | 2.28194 | 0.391648   | 0.44     | 14.112          | 0.810435 | -0.0523778 | 0           | 0                       | 575         |

Top5 stability / holdings overlap versus formal v9 Pool A:

| date       | v82_holdings            | formal_v9_pool_a_holdings | overlap_count | overlap_tickers | v82_only           | v9_only             |
| ---------- | ----------------------- | ------------------------- | ------------- | --------------- | ------------------ | ------------------- |
| 2024-02-01 | MSTR,NET,NVDA,PLTR,SHOP | CRWD,PANW,SHOP,TSLA,UPRO  | 1             | SHOP            | MSTR,NET,NVDA,PLTR | CRWD,PANW,TSLA,UPRO |
| 2024-02-02 | MSTR,NET,NVDA,PLTR,SHOP | CRWD,PANW,SHOP,TSLA,UPRO  | 1             | SHOP            | MSTR,NET,NVDA,PLTR | CRWD,PANW,TSLA,UPRO |
| 2024-02-05 | MSTR,NET,NVDA,PLTR,SHOP | CRWD,PANW,SHOP,TSLA,UPRO  | 1             | SHOP            | MSTR,NET,NVDA,PLTR | CRWD,PANW,TSLA,UPRO |
| 2024-02-06 | MSTR,NET,NVDA,PLTR,SHOP | CRWD,PANW,SHOP,TSLA,UPRO  | 1             | SHOP            | MSTR,NET,NVDA,PLTR | CRWD,PANW,TSLA,UPRO |
| 2024-02-07 | MSTR,NET,NVDA,PLTR,SHOP | CRWD,PANW,SHOP,TSLA,UPRO  | 1             | SHOP            | MSTR,NET,NVDA,PLTR | CRWD,PANW,TSLA,UPRO |
| 2024-02-08 | MSTR,NET,NVDA,PLTR,SHOP | CRWD,PANW,SHOP,TSLA,UPRO  | 1             | SHOP            | MSTR,NET,NVDA,PLTR | CRWD,PANW,TSLA,UPRO |
| 2024-02-09 | MSTR,NET,NVDA,PLTR,SHOP | CRWD,PANW,SHOP,TSLA,UPRO  | 1             | SHOP            | MSTR,NET,NVDA,PLTR | CRWD,PANW,TSLA,UPRO |
| 2024-02-12 | MSTR,NET,NVDA,PLTR,SHOP | CRWD,PANW,SHOP,TSLA,UPRO  | 1             | SHOP            | MSTR,NET,NVDA,PLTR | CRWD,PANW,TSLA,UPRO |
| 2024-02-13 | MSTR,NET,NVDA,PLTR,SHOP | CRWD,PANW,SHOP,TSLA,UPRO  | 1             | SHOP            | MSTR,NET,NVDA,PLTR | CRWD,PANW,TSLA,UPRO |
| 2024-02-14 | MSTR,NET,NVDA,PLTR,SHOP | CRWD,PANW,SHOP,TSLA,UPRO  | 1             | SHOP            | MSTR,NET,NVDA,PLTR | CRWD,PANW,TSLA,UPRO |

## 6. Comparison with formal v9

| case                            | source                                                                                                                   | cagr      | calmar   | max_drawdown | cost50_t1_cagr | cost50_t1_calmar | single_year_share | top_ticker | top_ticker_share | remove_top_year_cagr | remove_top_year_calmar | remove_top_ticker_cagr | remove_top_ticker_calmar | coin_mstr_pltr_share | depends_on_coin_mstr_pltr |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------ | --------- | -------- | ------------ | -------------- | ---------------- | ----------------- | ---------- | ---------------- | -------------------- | ---------------------- | ---------------------- | ------------------------ | -------------------- | ------------------------- |
| v8.2 frozen formal replay       | current audit v8.2 frozen score + v9.1 provider                                                                          | 0.642126  | 1.63397  | -0.392985    | 0.540613       | 1.34535          | 0.496839          | INTC       | 0.137939         | 0.521587             | 1.32724                | 0.489654               | 1.32651                  |                      |                           |
| formal v9 Pool A                | E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\formal_v9_20260505_224016\formal_v9\formal_v9_pool_a_reproducti... | 0.232225  | 0.55841  | -0.415868    | 0.158479       | 0.363699         | 0.521186          | PLTR       | 0.202707         | 0.195966             | 0.480855               | 0.120969               | 0.29041                  | 0.272589             | True                      |
| formal v9 Pool A + small growth | E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\formal_v9_20260505_224016\formal_v9\formal_v9_pool_a_plus_growt... | 0.0797791 | 0.186601 | -0.427538    | 0.0150012      | 0.0340095        | 0.598954          | PLTR       | 0.136202         | -0.0604458           | -0.162718              | -0.00477782            | -0.0111558               | 0.233573             | True                      |

Score/rank overlap:

| rebalance_month | v82_top5                 | v9_pool_a_top5            | overlap_count | overlap_tickers | status |
| --------------- | ------------------------ | ------------------------- | ------------- | --------------- | ------ |
| 2024-01         | PLTR,MSTR,NVDA,SHOP,NET  | PANW,TSLA,SHOP,CRWD,UPRO  | 1             | SHOP            | ok     |
| 2024-02         | UBER,ADBE,CRWD,ORCL,TSLA | MSTR,NFLX,INTC,ADBE,GOOGL | 1             | ADBE            | ok     |
| 2024-04         | TSLA,PLTR,CRWD,QLD,NVDA  | TSLA,SHOP,NET,SNOW,MU     | 1             | TSLA            | ok     |
| 2024-05         | MSTR,NET,NVDA,QLD,SHOP   | SHOP,AMZN,XLK,GLD,NET     | 2             | NET,SHOP        | ok     |
| 2024-07         | CRWD,MSTR,NVDA,SHOP,AVGO | ORCL,MU,MSTR,PLTR,TSLA    | 1             | MSTR            | ok     |
| 2024-09         | CRWD,INTC,NOW,META,MSTR  | MSTR,INTC,XLK,CRWD,UPRO   | 3             | CRWD,INTC,MSTR  | ok     |
| 2024-10         | MSTR,CRM,TSLA,PANW,NET   | MSTR,AMZN,ADBE,ORCL,TLT   | 1             | MSTR            | ok     |
| 2024-12         | PLTR,TSLA,NFLX,MSTR,NET  | PLTR,CRM,NET,SPY,CRWD     | 2             | NET,PLTR        | ok     |
| 2025-01         | TSLA,PLTR,NVDA,MSTR,INTC | TSLA,TQQQ,CRM,QLD,AMD     | 1             | TSLA            | ok     |
| 2025-02         | AVGO,AMD,UBER,TSLA,CRM   | UBER,AVGO,NOW,SOXX,GOOGL  | 2             | AVGO,UBER       | ok     |
| 2025-03         | PLTR,TSLA,TQQQ,SHOP,NOW  | PLTR,NET,SHOP,TQQQ,UPRO   | 3             | PLTR,SHOP,TQQQ  | ok     |
| 2025-04         | NOW,QLD,SHOP,NVDA,SSO    | NOW,TSLA,QLD,SHOP,INTC    | 3             | NOW,QLD,SHOP    | ok     |
| 2025-06         | TQQQ,SOXX,QQQ,SSO,CRM    | SOXX,SSO,MSTR,CRWD,PLTR   | 2             | SOXX,SSO        | ok     |
| 2025-07         | NET,INTC,PLTR,NVDA,TQQQ  | PLTR,CRWD,ORCL,NFLX,NVDA  | 2             | NVDA,PLTR       | ok     |
| 2025-09         | MU,AMD,MSTR,NET,PLTR     | UPRO,AAPL,PANW,AMD,QLD    | 1             | AMD             | ok     |
| 2025-10         | INTC,AMD,ORCL,MU,MSTR    | MU,ORCL,MSTR,SOXX,ADBE    | 3             | MSTR,MU,ORCL    | ok     |
| 2025-12         | MSTR,QLD,NFLX,NVDA,TQQQ  | MSTR,CRM,GOOGL,NET,AAPL   | 1             | MSTR            | ok     |
| 2026-03         | MSTR,GLD,SNOW,INTC,CRWD  | SNOW,SOXX,MSFT,CRWD,NET   | 2             | CRWD,SNOW       | ok     |

Main differences:

- v8.2 frozen replay keeps the historical frozen score trail and Pool A only; formal v9 uses v9.1 score provenance.
- v8.2 frozen formal replay passes CAGR/Calmar/cost50/concentration gates.
- formal v9 Pool A already drops materially versus v8.2 frozen, before adding small growth.
- formal v9 Pool A + small growth fails performance and concentration/robustness gates.
- The observed v9 failure is therefore not a reason to invalidate the v8.2 frozen baseline; it is evidence that v9.1 score/rank drift and expansion diluted the strategy.

## 7. Conclusion

**A. v8.2 formal replay audit passed; it can be upgraded to / retained as formal frozen baseline.**

The current frozen mainline remains `v8.2 frozen Pool A top5_ytdcap80p_derisk100p`. This audit does not authorize v10, pool expansion, trading, or parameter search.

## 8. Allowed Next Actions

- Stop for human review; v8.2 can be treated as the formal frozen baseline evidence packet. Do not enter v10.

## 9. Forbidden Next Actions

- v10
- Nasdaq100/S&P500/full-market expansion
- new strategy search
- parameter search or gate lowering
- trading, broker/API connection, real order workflow
- using old v9 or unified replay as formal result
- automatic commit/push
