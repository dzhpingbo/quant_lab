# US Stock Selection v9 Small Growth Pool Pre-Research Report

## Scope

本轮已获批准进入 v9，但范围仅限“小幅科技成长池预研”。

Hard constraints:

- 不扩 Nasdaq100。
- 不扩 S&P500。
- 不做全市场扩池。
- 不重新搜索模型。
- 不重新选择策略。
- 不交易化。

Frozen strategy:

- Feature set: Alpha360
- Model: LGBModel
- Label: label_5d
- Portfolio: top5_ytdcap80p_derisk100p
- Execution: T+1
- Cost/slippage: 5bps + 5bps
- Max single weight: 20%
- YTD return cap: 80%
- Derisk after trigger: 100%

## Data Quality

- Excluded ticker count: `13`
- Excluded tickers: `PLTR, SNOW, APP, PATH, U, S, AFRM, COIN, SQ, ABNB, DASH, RBLX, ARM`

## Core Results

### Pool A reproduction

- universe_name: `pool_a_v8_2_reproduction`
- ticker_count: `36`
- cagr: `0.642126`
- calmar: `1.633969`
- max_drawdown: `-0.392985`
- cost50_t1_cagr: `0.540613`
- cost50_t1_calmar: `1.345347`
- single_year_share: `0.496839`
- top_ticker: `INTC`
- top_ticker_share: `0.137939`
- remove_top_year_cagr: `0.521587`
- remove_top_year_calmar: `1.327243`
- remove_top_ticker_cagr: `0.489654`
- remove_top_ticker_calmar: `1.326510`
- v9_gate_pass: `False`
- classification: `not_v10_ready_growth_pool_sensitive`


### Pool A + small growth

- universe_name: `pool_a_plus_small_growth`
- ticker_count: `52`
- cagr: `0.072584`
- calmar: `0.199302`
- max_drawdown: `-0.364192`
- cost50_t1_cagr: `0.039016`
- cost50_t1_calmar: `0.102023`
- single_year_share: `0.536168`
- top_ticker: `TSLA`
- top_ticker_share: `0.115285`
- remove_top_year_cagr: `0.040730`
- remove_top_year_calmar: `0.117206`
- remove_top_ticker_cagr: `0.044683`
- remove_top_ticker_calmar: `0.124256`
- v9_gate_pass: `False`
- classification: `not_v10_ready_growth_pool_sensitive`


### Small growth only

- universe_name: `small_growth_only`
- ticker_count: `18`
- cagr: `-0.021140`
- calmar: `-0.048876`
- max_drawdown: `-0.432523`
- cost50_t1_cagr: `-0.047269`
- cost50_t1_calmar: `-0.098444`
- single_year_share: `0.962359`
- top_ticker: `ZS`
- top_ticker_share: `0.190893`
- remove_top_year_cagr: `-0.000900`
- remove_top_year_calmar: `-0.002326`
- remove_top_ticker_cagr: `0.016902`
- remove_top_ticker_calmar: `0.040345`
- v9_gate_pass: `False`
- classification: `not_v10_ready_growth_pool_sensitive`


### Pool A + small growth excluding extreme-vol names

- universe_name: `pool_a_plus_small_growth_ex_extreme_vol`
- ticker_count: `50`
- cagr: `0.116580`
- calmar: `0.321321`
- max_drawdown: `-0.362814`
- cost50_t1_cagr: `0.081103`
- cost50_t1_calmar: `0.208002`
- single_year_share: `0.617822`
- top_ticker: `MRVL`
- top_ticker_share: `0.098060`
- remove_top_year_cagr: `0.055825`
- remove_top_year_calmar: `0.273823`
- remove_top_ticker_cagr: `0.090346`
- remove_top_ticker_calmar: `0.272025`
- v9_gate_pass: `False`
- classification: `not_v10_ready_growth_pool_sensitive`


## New Ticker Contribution / Selection

| universe_name | ticker | return_contribution | abs_share |
| --- | --- | --- | --- |
| small_growth_only | ZS | -0.217652 | 0.190893 |
| small_growth_only | ROKU | 0.145348 | 0.127478 |
| small_growth_only_top10_control | ZS | -0.105816 | 0.123799 |
| pool_a_plus_small_growth_top10_control | MSTR | 0.164509 | 0.122920 |
| small_growth_only_top10_control | TSM | 0.101142 | 0.118331 |
| pool_a_plus_small_growth | TSLA | 0.189892 | 0.115285 |
| pool_a_plus_small_growth_ex_extreme_vol | MRVL | 0.173533 | 0.098060 |
| small_growth_only_top10_control | SPOT | 0.080314 | 0.093962 |
| pool_a_plus_small_growth_ex_extreme_vol_top10_control | MRVL | 0.126341 | 0.093359 |
| small_growth_only | ASML | 0.105234 | 0.092296 |
| small_growth_only | TSM | 0.102842 | 0.090198 |
| small_growth_only | TEAM | -0.100312 | 0.087979 |
| small_growth_only_top10_control | MRVL | 0.070808 | 0.082841 |
| pool_a_plus_small_growth_ex_extreme_vol_top10_control | TSLA | 0.111472 | 0.082372 |
| small_growth_only_top10_control | ASML | 0.069846 | 0.081716 |
| pool_a_plus_small_growth_ex_extreme_vol | TSLA | 0.143273 | 0.080961 |
| pool_a_plus_small_growth_ex_extreme_vol | TQQQ | 0.139264 | 0.078696 |
| small_growth_only | MDB | 0.089352 | 0.078367 |
| pool_a_plus_small_growth_top10_control | MRVL | 0.104481 | 0.078067 |
| pool_a_plus_small_growth_top10_control | TSLA | 0.099909 | 0.074651 |


## All Universe Results

| universe_name | ticker_count | top_k | cagr | max_drawdown | calmar | cost50_t1_cagr | cost50_t1_calmar | single_year_share | top_ticker | top_ticker_share | remove_top_year_cagr | remove_top_year_calmar | remove_top_ticker_cagr | remove_top_ticker_calmar | v9_gate_pass | classification |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| pool_a_plus_small_growth | 52 | 5 | 0.072584 | -0.364192 | 0.199302 | 0.039016 | 0.102023 | 0.536168 | TSLA | 0.115285 | 0.040730 | 0.117206 | 0.044683 | 0.124256 | False | not_v10_ready_growth_pool_sensitive |
| pool_a_plus_small_growth_ex_extreme_vol | 50 | 5 | 0.116580 | -0.362814 | 0.321321 | 0.081103 | 0.208002 | 0.617822 | MRVL | 0.098060 | 0.055825 | 0.273823 | 0.090346 | 0.272025 | False | not_v10_ready_growth_pool_sensitive |
| pool_a_plus_small_growth_ex_extreme_vol_top10_control | 50 | 10 | 0.103678 | -0.362876 | 0.285711 | 0.072881 | 0.191209 | 0.545598 | MRVL | 0.093359 | 0.057164 | 0.288474 | 0.084099 | 0.246096 | False | not_v10_ready_growth_pool_sensitive |
| pool_a_plus_small_growth_top10_control | 52 | 10 | 0.086156 | -0.349307 | 0.246648 | 0.054282 | 0.149165 | 0.409211 | MSTR | 0.122920 | 0.060324 | 0.243166 | 0.061208 | 0.175228 | False | not_v10_ready_growth_pool_sensitive |
| pool_a_v8_2_reproduction | 36 | 5 | 0.642126 | -0.392985 | 1.633969 | 0.540613 | 1.345347 | 0.496839 | INTC | 0.137939 | 0.521587 | 1.327243 | 0.489654 | 1.326510 | False | not_v10_ready_growth_pool_sensitive |
| pool_a_v8_2_reproduction_top10_control | 36 | 10 | 0.516419 | -0.337242 | 1.531302 | 0.437219 | 1.271579 | 0.563812 | PLTR | 0.123218 | 0.358438 | 1.062852 | 0.422834 | 1.392170 | False | not_v10_ready_growth_pool_sensitive |
| small_growth_only | 18 | 5 | -0.021140 | -0.432523 | -0.048876 | -0.047269 | -0.098444 | 0.962359 | ZS | 0.190893 | -0.000900 | -0.002326 | 0.016902 | 0.040345 | False | not_v10_ready_growth_pool_sensitive |
| small_growth_only_top10_control | 18 | 10 | 0.032727 | -0.349309 | 0.093690 | 0.015003 | 0.042301 | 0.667090 | ZS | 0.123799 | 0.009485 | 0.039677 | 0.052238 | 0.147852 | False | not_v10_ready_growth_pool_sensitive |


## Required Answers

1. 扩科技成长池是否提升，还是降低稳健性：见 Pool A 与 Pool A + small growth 对比；gate 使用 80% Pool A 保真阈值。
2. 新增股票中哪些被选入/贡献最多：见 `v9_ticker_contribution.csv` 与 `v9_monthly_holdings.csv`。
3. 是否依赖 MSTR/COIN/PLTR：见 `extreme_vol_contribution_share`、top ticker share 和 ex-extreme-vol 对照。
4. small growth only 是否可行：见 `small_growth_only` 行。
5. 剔除极高波动票后是否仍有效：见 `pool_a_plus_small_growth_ex_extreme_vol` 行。
6. 是否允许进入 v10：`False`。
7. v10 是否可以扩 Nasdaq100：不可以自动扩；如继续，应优先行业主题池或更严格 universe 设计，不应直接扩 Nasdaq100/S&P500。

## Cycle Verdict

- Classification: `not_v10_ready_growth_pool_sensitive`
- Allow entering v10: `False`
- Effective small-growth count: `18`
- Excluded ticker count: `13`

This remains a research pre-validation package and is not a live trading recommendation.
