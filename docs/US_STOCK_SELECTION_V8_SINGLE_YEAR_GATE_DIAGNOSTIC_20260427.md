# US Stock Selection v8 Single-Year Gate Diagnostic - 20260427_233246

Scope: read-only diagnosis of the accepted v8 run. This report does not enter v9, does not expand Nasdaq100/S&P500, does not run 31b, and does not rerun strategy logic.

Run directory: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\run_20260426_095958`

## 1. single_year_share formula

Code-confirmed formula from `quant_lab/us_stock_selection/v8_reporting.py`: `denom = yearly["year_return"].abs().sum()` and `single_year_share = yearly["year_return"].abs().max() / denom`. The numerator is the largest absolute calendar-year compounded return from `v8_attribution/yearly_return.csv`; the denominator is the sum of absolute calendar-year compounded returns. It is not annual NAV profit, not only positive-year contribution, and not ticker PnL. The threshold is hard-coded in the same file as `single_year_share_lte_50: single_year_share <= 0.50`.

Confirmed v8 verdict:

- Final verdict: `credible_but_execution_sensitive`
- allow_enter_v9: `False`
- single_year_share: `0.5260274868858267`
- single_year_share_lte_50: `False`

## 2. Annual contribution diagnosis

Dominant gate year: `2024`

- Dominant gate share: `0.526027`
- Second-highest gate share: `0.467495`
- Gap: `0.058532`
- Interpretation: the breach is slight above the 50% threshold, not an overwhelming one-year-only result. It is still a real gate failure.

Annual table:

| year | start_nav | end_nav | annual_return | annual_profit | annual_profit_share | positive_profit_share | gate_abs_year_return_share | max_drawdown_in_year | trading_month_count | decision_count | turnover | dominant_tickers_or_holdings |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2024 | 1.000000 | 1.831285 | 0.831285 | 0.831285 | 0.374992 | 0.380588 | 0.526027 | -0.282641 | 12 | 8 | 10.600000 | MSTR(5x,avg=0.20,max=0.20);AMD(3x,avg=0.20,max=0.20);CRWD(3x,avg=0.20,max=0.20);NET(3x,avg=0.20,max=0.20);AVGO(2x,avg=0.20,max=0.20) |
| 2025 | 1.831285 | 3.184213 | 0.738786 | 1.352928 | 0.610305 | 0.619412 | 0.467495 | -0.326069 | 12 | 9 | 16.000000 | AVGO(3x,avg=0.20,max=0.20);MSTR(3x,avg=0.20,max=0.20);MU(3x,avg=0.20,max=0.20);NET(3x,avg=0.20,max=0.20);PLTR(3x,avg=0.20,max=0.20) |
| 2026 | 3.184213 | 3.151618 | -0.010236 | -0.032594 | 0.014703 | 0.000000 | 0.006477 | -0.190006 | 4 | 1 | 2.400000 | AMD(2x,avg=0.20,max=0.20);INTC(2x,avg=0.20,max=0.20);MU(2x,avg=0.20,max=0.20);CRM(1x,avg=0.20,max=0.20);MSTR(1x,avg=0.20,max=0.20) |


Removing dominant gate year `2024` from the existing daily NAV curve gives diagnostic-only metrics:

| removed_year | daily_count | total_return | cagr | max_drawdown | calmar | cagr_ge_20 |
| --- | --- | --- | --- | --- | --- | --- |
| 2024 | 323 | 0.720987 | 0.527392 | -0.326069 | 1.617424 | True |


Important: this is a NAV-curve diagnostic, not a true strategy rerun.

## 3. Monthly and extreme-month diagnosis

Top positive months by NAV profit:

| month | monthly_return | monthly_profit | positive_profit_share | contribution_share | cumulative_nav_before | cumulative_nav_after | related_holdings | related_trades |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2025-10 | 0.218031 | 0.600071 | 0.168601 | 0.120821 | 2.752222 | 3.352293 | AMD:0.20;AVGO:0.20;NET:0.20;NOW:0.20;SHOP:0.20 | ADBE:-0.20;AMD:+0.20;AVGO:+0.20;CRM:-0.20;MU:-0.20;NET:+0.20;NOW:+0.20;PANW:-0.20;PLTR:-0.20;SHOP:+0.20 |
| 2024-11 | 0.347773 | 0.491298 | 0.138039 | 0.098920 | 1.412697 | 1.903995 | AMD:0.20;MSTR:0.20;ORCL:0.20;PLTR:0.20;TSLA:0.20 | AMD:+0.20;AVGO:-0.20;MSTR:+0.20;NET:-0.20;NVDA:-0.20;ORCL:+0.20;PLTR:+0.20;SHOP:-0.20;TSLA:+0.20;XLK:-0.20 |
| 2025-05 | 0.157961 | 0.294474 | 0.082738 | 0.059291 | 1.864225 | 2.158699 | MSTR:0.20;QLD:0.20;TQQQ:0.20;TSLA:0.20;UPRO:0.20 | NET:-0.20;PLTR:-0.20;QLD:+0.20;SNOW:-0.20;TQQQ:+0.20;UPRO:+0.20 |
| 2025-04 | 0.178816 | 0.282787 | 0.079454 | 0.056938 | 1.581438 | 1.864225 | MSTR:0.20;NET:0.20;PLTR:0.20;SNOW:0.20;TSLA:0.20 | AVGO:-0.20;GOOGL:-0.20;MSTR:+0.20;NET:+0.20;NOW:-0.20;NVDA:-0.20;PLTR:+0.20;SNOW:+0.20;TQQQ:-0.20;TSLA:+0.20 |
| 2025-09 | 0.102933 | 0.256857 | 0.072169 | 0.051717 | 2.495366 | 2.752222 | ADBE:0.20@2025-08-01;CRM:0.20@2025-08-01;MU:0.20@2025-08-01;PANW:0.20@2025-08-01;PLTR:0.20@2025-08-01 |  |
| 2024-06 | 0.154517 | 0.203816 | 0.057266 | 0.041037 | 1.319051 | 1.522867 | CRM:0.20;CRWD:0.20;MU:0.20;NET:0.20;TQQQ:0.20 | AMD:-0.20;CRM:+0.20;INTC:-0.20;MSTR:-0.20;MU:+0.20;NET:+0.20;TQQQ:+0.20;UPRO:-0.20 |
| 2025-06 | 0.092456 | 0.199584 | 0.056077 | 0.040185 | 2.158699 | 2.358283 | MSTR:0.20@2025-05-01;QLD:0.20@2025-05-01;TQQQ:0.20@2025-05-01;TSLA:0.20@2025-05-01;UPRO:0.20@2025-05-01 |  |
| 2024-03 | 0.148005 | 0.172928 | 0.048587 | 0.034818 | 1.168394 | 1.341322 | AVGO:0.20;MSTR:0.20;NET:0.20;SSO:0.20;UPRO:0.20 | AAPL:-0.20;AVGO:+0.20;NET:+0.20;NFLX:-0.20;ORCL:-0.20;SSO:+0.20;UPRO:+0.20;XLK:-0.20 |
| 2024-05 | 0.149367 | 0.171418 | 0.048163 | 0.034514 | 1.147632 | 1.319051 | AMD:0.20;CRWD:0.20;INTC:0.20;MSTR:0.20;UPRO:0.20 | AMD:+0.20;AVGO:-0.20;CRWD:+0.20;INTC:+0.20;NET:-0.20;SSO:-0.20 |
| 2024-02 | 0.168394 | 0.168394 | 0.047313 | 0.033905 | 1.000000 | 1.168394 | AAPL:0.20;MSTR:0.20;NFLX:0.20;ORCL:0.20;XLK:0.20 | AAPL:+0.20;MSTR:+0.20;NFLX:+0.20;ORCL:+0.20;XLK:+0.20 |


Top negative months by NAV profit:

| month | monthly_return | monthly_profit | contribution_share | cumulative_nav_before | cumulative_nav_after | max_drawdown_in_month | related_holdings | related_trades |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2025-03 | -0.128318 | -0.232799 | 0.046873 | 1.814237 | 1.581438 | -0.128318 | AVGO:0.20;GOOGL:0.20;NOW:0.20;NVDA:0.20;TQQQ:0.20 | AAPL:-0.20;AVGO:+0.20;GOOGL:+0.20;MSTR:-0.20;NOW:+0.20;NVDA:+0.20;SHOP:-0.20;SNOW:-0.20;TQQQ:+0.20;UBER:-0.20 |
| 2025-11 | -0.066809 | -0.223963 | 0.045094 | 3.352293 | 3.128330 | -0.129919 | ADBE:0.20;AVGO:0.20;MU:0.20;ORCL:0.20;PANW:0.20 | ADBE:+0.20;AMD:-0.20;MU:+0.20;NET:-0.20;NOW:-0.20;ORCL:+0.20;PANW:+0.20;SHOP:-0.20 |
| 2024-07 | -0.144599 | -0.220206 | 0.044337 | 1.522867 | 1.302661 | -0.204592 | CRM:0.20@2024-06-03;CRWD:0.20@2024-06-03;MU:0.20@2024-06-03;NET:0.20@2024-06-03;TQQQ:0.20@2024-06-03 |  |
| 2026-02 | -0.059919 | -0.200026 | 0.040274 | 3.338270 | 3.138243 | -0.122055 | AMD:0.20@2026-01-02;CRM:0.20@2026-01-02;INTC:0.20@2026-01-02;MU:0.20@2026-01-02;SHOP:0.20@2026-01-02 |  |
| 2024-04 | -0.144402 | -0.193690 | 0.038998 | 1.341322 | 1.147632 | -0.164235 | AVGO:0.20@2024-03-01;MSTR:0.20@2024-03-01;NET:0.20@2024-03-01;SSO:0.20@2024-03-01;UPRO:0.20@2024-03-01 |  |
| 2026-03 | -0.045872 | -0.143958 | 0.028985 | 3.138243 | 2.994285 | -0.117925 | AMD:0.20@2026-01-02;CRM:0.20@2026-01-02;INTC:0.20@2026-01-02;MU:0.20@2026-01-02;SHOP:0.20@2026-01-02 |  |
| 2025-02 | -0.041110 | -0.077781 | 0.015661 | 1.892018 | 1.814237 | -0.130089 | AAPL:0.20;MSTR:0.20;SHOP:0.20;SNOW:0.20;UBER:0.20 | AAPL:+0.20;INTC:-0.20;IWM:-0.20;MSTR:+0.20;MU:-0.20;SNOW:+0.20;UBER:+0.20;UPRO:-0.20 |
| 2024-12 | -0.038188 | -0.072710 | 0.014640 | 1.903995 | 1.831285 | -0.100729 | AMD:0.20@2024-11-01;MSTR:0.20@2024-11-01;ORCL:0.20@2024-11-01;PLTR:0.20@2024-11-01;TSLA:0.20@2024-11-01 |  |
| 2024-08 | -0.032522 | -0.042365 | 0.008530 | 1.302661 | 1.260296 | -0.125296 | AMD:0.20;CRWD:0.20;MSTR:0.20;MU:0.20;SNOW:0.20 | AMD:+0.20;CRM:-0.20;MSTR:+0.20;NET:-0.20;SNOW:+0.20;TQQQ:-0.20 |
| 2024-01 | 0.000000 | 0.000000 | 0.000000 | 1.000000 | 1.000000 | 0.000000 |  |  |


Extreme-month concentration:

- Top 1 positive month positive-profit share: `0.168601`
- Top 3 positive months positive-profit share: `0.389378`
- Top 5 positive months positive-profit share: `0.541001`

The dominant year is not from a single positive month only; it is helped by several strong months, with the largest visible positive month being 2024-11.

## 4. Holding and ticker concentration diagnosis

Yearly holding concentration:

| year | ticker_count | avg_holding_count | single_ticker_max_avg_weight | single_ticker_max_avg_weight_ticker | single_ticker_max_month_weight | single_ticker_max_month_weight_ticker | dominant_tickers_or_holdings |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2024 | 20 | 5.000000 | 0.200000 | AMD | 0.200000 | MSTR | MSTR(5x,avg=0.20,max=0.20);AMD(3x,avg=0.20,max=0.20);CRWD(3x,avg=0.20,max=0.20);NET(3x,avg=0.20,max=0.20);AVGO(2x,avg=0.20,max=0.20) |
| 2025 | 24 | 5.000000 | 0.200000 | AVGO | 0.200000 | AVGO | AVGO(3x,avg=0.20,max=0.20);MSTR(3x,avg=0.20,max=0.20);MU(3x,avg=0.20,max=0.20);NET(3x,avg=0.20,max=0.20);PLTR(3x,avg=0.20,max=0.20) |
| 2026 | 7 | 5.000000 | 0.200000 | AMD | 0.200000 | AMD | AMD(2x,avg=0.20,max=0.20);INTC(2x,avg=0.20,max=0.20);MU(2x,avg=0.20,max=0.20);CRM(1x,avg=0.20,max=0.20);MSTR(1x,avg=0.20,max=0.20) |


Dominant-year holdings:

| ticker | year | appearance_count | avg_weight_when_held | max_weight | trade_count | buy_delta_weight | sell_delta_weight | net_delta_weight | pnl_available |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| MSTR | 2024 | 5 | 0.200000 | 0.200000 | 5 | 0.600000 | -0.400000 | 0.200000 | False |
| AMD | 2024 | 3 | 0.200000 | 0.200000 | 5 | 0.600000 | -0.400000 | 0.200000 | False |
| CRWD | 2024 | 3 | 0.200000 | 0.200000 | 2 | 0.200000 | -0.200000 | 0.000000 | False |
| NET | 2024 | 3 | 0.200000 | 0.200000 | 6 | 0.600000 | -0.600000 | 0.000000 | False |
| AVGO | 2024 | 2 | 0.200000 | 0.200000 | 4 | 0.400000 | -0.400000 | 0.000000 | False |
| MU | 2024 | 2 | 0.200000 | 0.200000 | 2 | 0.200000 | -0.200000 | 0.000000 | False |
| ORCL | 2024 | 2 | 0.200000 | 0.200000 | 3 | 0.400000 | -0.200000 | 0.200000 | False |
| UPRO | 2024 | 2 | 0.200000 | 0.200000 | 2 | 0.200000 | -0.200000 | 0.000000 | False |
| XLK | 2024 | 2 | 0.200000 | 0.200000 | 4 | 0.400000 | -0.400000 | 0.000000 | False |
| AAPL | 2024 | 1 | 0.200000 | 0.200000 | 2 | 0.200000 | -0.200000 | 0.000000 | False |
| CRM | 2024 | 1 | 0.200000 | 0.200000 | 2 | 0.200000 | -0.200000 | 0.000000 | False |
| INTC | 2024 | 1 | 0.200000 | 0.200000 | 2 | 0.200000 | -0.200000 | 0.000000 | False |
| NFLX | 2024 | 1 | 0.200000 | 0.200000 | 2 | 0.200000 | -0.200000 | 0.000000 | False |
| NVDA | 2024 | 1 | 0.200000 | 0.200000 | 2 | 0.200000 | -0.200000 | 0.000000 | False |
| PLTR | 2024 | 1 | 0.200000 | 0.200000 | 1 | 0.200000 | 0.000000 | 0.200000 | False |
| SHOP | 2024 | 1 | 0.200000 | 0.200000 | 2 | 0.200000 | -0.200000 | 0.000000 | False |
| SNOW | 2024 | 1 | 0.200000 | 0.200000 | 2 | 0.200000 | -0.200000 | 0.000000 | False |
| SSO | 2024 | 1 | 0.200000 | 0.200000 | 2 | 0.200000 | -0.200000 | 0.000000 | False |
| TQQQ | 2024 | 1 | 0.200000 | 0.200000 | 2 | 0.200000 | -0.200000 | 0.000000 | False |
| TSLA | 2024 | 1 | 0.200000 | 0.200000 | 1 | 0.200000 | 0.000000 | 0.200000 | False |


Ticker exposure summary:

| ticker | appearance_count | years_active | avg_weight_when_held | max_weight | trade_count | buy_delta_weight | sell_delta_weight | net_delta_weight | pnl_available |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| MSTR | 9 | 3 | 0.200000 | 0.200000 | 11 | 1.200000 | -1.000000 | 0.200000 | False |
| MU | 7 | 3 | 0.200000 | 0.200000 | 7 | 0.800000 | -0.600000 | 0.200000 | False |
| AMD | 6 | 3 | 0.200000 | 0.200000 | 9 | 1.000000 | -0.800000 | 0.200000 | False |
| NET | 6 | 2 | 0.200000 | 0.200000 | 12 | 1.200000 | -1.200000 | 0.000000 | False |
| AVGO | 5 | 2 | 0.200000 | 0.200000 | 8 | 0.800000 | -0.800000 | 0.000000 | False |
| SHOP | 5 | 3 | 0.200000 | 0.200000 | 8 | 0.800000 | -0.800000 | 0.000000 | False |
| CRWD | 4 | 2 | 0.200000 | 0.200000 | 4 | 0.400000 | -0.400000 | 0.000000 | False |
| INTC | 4 | 3 | 0.200000 | 0.200000 | 5 | 0.600000 | -0.400000 | 0.200000 | False |
| PLTR | 4 | 2 | 0.200000 | 0.200000 | 6 | 0.600000 | -0.600000 | 0.000000 | False |
| UPRO | 4 | 2 | 0.200000 | 0.200000 | 6 | 0.600000 | -0.600000 | 0.000000 | False |
| CRM | 3 | 3 | 0.200000 | 0.200000 | 6 | 0.600000 | -0.600000 | 0.000000 | False |
| ORCL | 3 | 2 | 0.200000 | 0.200000 | 6 | 0.600000 | -0.600000 | 0.000000 | False |
| SNOW | 3 | 2 | 0.200000 | 0.200000 | 6 | 0.600000 | -0.600000 | 0.000000 | False |
| TQQQ | 3 | 2 | 0.200000 | 0.200000 | 6 | 0.600000 | -0.600000 | 0.000000 | False |
| TSLA | 3 | 2 | 0.200000 | 0.200000 | 4 | 0.400000 | -0.400000 | 0.000000 | False |
| UBER | 3 | 2 | 0.200000 | 0.200000 | 5 | 0.600000 | -0.400000 | 0.200000 | False |
| AAPL | 2 | 2 | 0.200000 | 0.200000 | 4 | 0.400000 | -0.400000 | 0.000000 | False |
| ADBE | 2 | 1 | 0.200000 | 0.200000 | 4 | 0.400000 | -0.400000 | 0.000000 | False |
| GOOGL | 2 | 1 | 0.200000 | 0.200000 | 4 | 0.400000 | -0.400000 | 0.000000 | False |
| NOW | 2 | 1 | 0.200000 | 0.200000 | 4 | 0.400000 | -0.400000 | 0.000000 | False |


`trades.csv` has buy/sell weight records but no ticker-level PnL column, so this report can attribute yearly exposure and rebalance activity, not exact yearly ticker PnL.

## 5. Diagnostic robustness sensitivity

Leave-one-year-out metrics:

| removed_year | daily_count | total_return | cagr | max_drawdown | calmar | cagr_ge_20 |
| --- | --- | --- | --- | --- | --- | --- |
| 2024 | 323 | 0.720987 | 0.527392 | -0.326069 | 1.617424 | True |
| 2025 | 325 | 0.812540 | 0.585887 | -0.282641 | 2.072901 | True |
| 2026 | 502 | 2.184213 | 0.788558 | -0.328300 | 2.401943 | True |


Top positive month removed metrics:

| removed_top_positive_month_count | removed_months | removed_profit | daily_count | total_return | cagr | max_drawdown | calmar |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2025-10 | 0.600071 | 552 | 1.587469 | 0.543428 | -0.328300 | 1.655280 |
| 3 | 2025-10,2024-11,2025-05 | 1.385843 | 511 | 0.657923 | 0.283153 | -0.358771 | 0.789229 |
| 5 | 2025-10,2024-11,2025-05,2025-04,2025-09 | 1.925487 | 469 | 0.275173 | 0.139524 | -0.282641 | 0.493645 |


Strongest 12-month window:

| start_month | end_month | window_return | window_max_drawdown | calmar_like | daily_count |
| --- | --- | --- | --- | --- | --- |
| 2024-11 | 2025-10 | 1.372974 | -0.328300 | 4.232215 | 250 |


Weakest 12-month window:

| start_month | end_month | window_return | window_max_drawdown | calmar_like | daily_count |
| --- | --- | --- | --- | --- | --- |
| 2024-04 | 2025-03 | 0.179015 | -0.282641 | 0.636101 | 251 |


These stress checks only transform the existing NAV series. They are not rebalanced, refit, or re-executed strategy backtests.

## 6. Acceptance judgment

- `single_year_share = 0.526` is a slight threshold breach, but it remains a valid concentration failure.
- v8 should remain `credible_but_execution_sensitive`.
- `allow_enter_v9` should remain `False`.
- The next research cycle should fix or explicitly relax year concentration controls before v9 is considered.
- 31b challenger can supplement model stability evidence, but it does not directly solve annual return concentration.

## 7. Recommended remediation order

1. Add a year-balance penalty to candidate scoring.
2. Add a leave-one-year-out Calmar gate.
3. Add a top-month contribution gate.
4. Add a ticker exposure concentration gate.
5. Add regime-segment performance requirements.
6. Apply separate yearly contribution constraints to TQQQ/QLD/high-beta names.
7. Treat 31b as challenger-model evidence only, not as the primary fix for the single-year gate.
