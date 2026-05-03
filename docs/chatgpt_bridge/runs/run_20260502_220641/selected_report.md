# US Stock Selection v8.2 Year Stability Report

## Scope

v8.2 does not enter v9, does not expand Nasdaq100/S&P500, and does not trade-live.  The stock-selection mainline is frozen as:

- Alpha360 + LGBModel + label_5d

This run replays portfolio construction and ex-ante risk-control variants from the v8.1 LGBModel full score/rank audit trail.  It does not train a new model and it does not use future-year information.

## Cycle Verdict

- Best strategy: `top5_ytdcap80p_derisk100p`
- Classification: `v9_ready_research_candidate`
- Allow entering v9: `True`
- Reason: `All v8.2 gates passed, but this run still does not enter v9 automatically.`
- Variants tested: `53`
- Variants passing single-year share <= 50%: `10`
- Variants passing all v9 gates: `6`

## Best Variant

- strategy_id: `top5_ytdcap80p_derisk100p`
- portfolio_template: `topk_equal_monthly_year_neutral_risk_cap`
- top_k: `5`
- max_weight: `0.200000`
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
- allow_enter_v9: `True`
- classification: `v9_ready_research_candidate`


## Top Results

| strategy_id | portfolio_template | cagr | calmar | max_drawdown | cost50_t1_cagr | cost50_t1_calmar | single_year_share | top_ticker_share | remove_top_year_cagr | remove_top_year_calmar | remove_top_ticker_cagr | remove_top_ticker_calmar | gate_pass_count | allow_enter_v9 | classification |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| top5_ytdcap80p_derisk100p | topk_equal_monthly_year_neutral_risk_cap | 0.642126 | 1.633969 | -0.392985 | 0.540613 | 1.345347 | 0.496839 | 0.137939 | 0.521587 | 1.327243 | 0.489654 | 1.326510 | 15 | True | v9_ready_research_candidate |
| top10_ytdcap60p_derisk100p | topk_equal_monthly_year_neutral_risk_cap | 0.545957 | 1.618889 | -0.337242 | 0.448799 | 1.305259 | 0.491534 | 0.125087 | 0.443484 | 2.226942 | 0.448343 | 1.476157 | 15 | True | v9_ready_research_candidate |
| top10_ytdcap60p_derisk75p | topk_equal_monthly_year_neutral_risk_cap | 0.528814 | 1.568055 | -0.337242 | 0.441149 | 1.283011 | 0.489769 | 0.127440 | 0.433782 | 1.286265 | 0.432540 | 1.424126 | 15 | True | v9_ready_research_candidate |
| top10_ytdcap60p_derisk50p | topk_equal_monthly_year_neutral_risk_cap | 0.510336 | 1.513264 | -0.337242 | 0.432047 | 1.256538 | 0.499037 | 0.127878 | 0.409829 | 1.215236 | 0.415668 | 1.368575 | 15 | True | v9_ready_research_candidate |
| top10_roll6mcap80p_derisk50 | topk_equal_monthly_year_neutral_risk_cap | 0.490016 | 1.453011 | -0.337242 | 0.423477 | 1.231613 | 0.499506 | 0.126401 | 0.392319 | 1.163317 | 0.395882 | 1.303431 | 15 | True | v9_ready_research_candidate |
| top10_roll3mcap30p_derisk50 | topk_equal_monthly_year_neutral_risk_cap | 0.438622 | 1.300614 | -0.337242 | 0.357871 | 1.040809 | 0.486239 | 0.125431 | 0.359175 | 1.065037 | 0.355538 | 1.170598 | 15 | True | v9_ready_research_candidate |
| top5_dropout_mw20p | topk_dropout_monthly | 0.889728 | 2.750576 | -0.323470 | 0.860729 | 2.640832 | 0.587900 | 0.225358 | 0.665700 | 2.057998 | 0.646176 | 2.236246 | 14 | False | credible_but_execution_sensitive |
| top5_roll6mcap80p_derisk50 | topk_equal_monthly_year_neutral_risk_cap | 0.825834 | 2.540435 | -0.325076 | 0.730898 | 2.172289 | 0.639575 | 0.145191 | 0.489198 | 1.504873 | 0.645328 | 2.307984 | 14 | False | credible_but_execution_sensitive |
| top5_roll6mcap50p_derisk50 | topk_equal_monthly_year_neutral_risk_cap | 0.752507 | 2.477982 | -0.303677 | 0.653423 | 2.068984 | 0.714423 | 0.133103 | 0.354797 | 1.168333 | 0.604937 | 2.087461 | 14 | False | credible_but_execution_sensitive |
| top5_voltarget20p_w60 | topk_equal_monthly_vol_target | 0.468262 | 2.347880 | -0.199440 | 0.417260 | 2.031789 | 0.712520 | 0.151433 | 0.228195 | 1.144179 | 0.372066 | 2.312587 | 14 | False | credible_but_execution_sensitive |
| top5_voltarget25p_w60 | topk_equal_monthly_vol_target | 0.542323 | 2.221650 | -0.244108 | 0.480861 | 1.914929 | 0.702274 | 0.146015 | 0.270654 | 1.108744 | 0.431381 | 2.178924 | 14 | False | credible_but_execution_sensitive |
| top5_equal_mw20p | topk_equal_monthly | 0.803999 | 2.045874 | -0.392985 | 0.722266 | 1.797403 | 0.657774 | 0.141455 | 0.452836 | 1.152296 | 0.634528 | 1.929087 | 14 | False | credible_but_execution_sensitive |
| top5_voltarget20p_w20 | topk_equal_monthly_vol_target | 0.429937 | 2.042927 | -0.210451 | 0.358403 | 1.646622 | 0.636990 | 0.153306 | 0.241945 | 1.149648 | 0.335519 | 2.016115 | 14 | False | credible_but_execution_sensitive |
| top5_voltarget25p_w20 | topk_equal_monthly_vol_target | 0.516449 | 2.008821 | -0.257091 | 0.433827 | 1.633519 | 0.647818 | 0.141216 | 0.277963 | 1.081186 | 0.411001 | 2.009425 | 14 | False | credible_but_execution_sensitive |
| top5_roll3mcap50p_derisk50 | topk_equal_monthly_year_neutral_risk_cap | 0.780623 | 1.986391 | -0.392985 | 0.673209 | 1.675320 | 0.653399 | 0.137623 | 0.443893 | 1.129542 | 0.621225 | 1.888644 | 14 | False | credible_but_execution_sensitive |
| top5_equal_mw15p | topk_equal_monthly | 0.583407 | 1.891287 | -0.308471 | 0.529361 | 1.675137 | 0.639777 | 0.141455 | 0.348893 | 1.131040 | 0.466579 | 1.826786 | 14 | False | credible_but_execution_sensitive |
| top5_ytdcap80p_derisk50p | topk_equal_monthly_year_neutral_risk_cap | 0.728209 | 1.853018 | -0.392985 | 0.635662 | 1.581884 | 0.583858 | 0.141878 | 0.491149 | 1.249789 | 0.576652 | 1.753133 | 14 | False | credible_but_execution_sensitive |
| top5_ytdcap80p_derisk75p | topk_equal_monthly_year_neutral_risk_cap | 0.686351 | 1.746505 | -0.392985 | 0.589081 | 1.465964 | 0.542201 | 0.138880 | 0.507382 | 1.291097 | 0.544054 | 1.654030 | 14 | False | credible_but_execution_sensitive |
| top5_equal_mw10p | topk_equal_monthly | 0.374152 | 1.738937 | -0.215162 | 0.342740 | 1.551930 | 0.622835 | 0.141455 | 0.236611 | 1.099688 | 0.303359 | 1.721584 | 14 | False | credible_but_execution_sensitive |
| top10_ytdcap80p_derisk100p | topk_equal_monthly_year_neutral_risk_cap | 0.516419 | 1.531302 | -0.337242 | 0.437219 | 1.271579 | 0.563812 | 0.123218 | 0.358438 | 1.062852 | 0.422834 | 1.392170 | 14 | False | credible_but_execution_sensitive |


## Benchmark Calmar

| benchmark | cagr | max_drawdown | calmar |
| --- | --- | --- | --- |
| SPY | 0.209634 | -0.190599 | 1.099868 |
| QQQ | 0.239292 | -0.227683 | 1.050987 |
| QLD | 0.384245 | -0.422900 | 0.908594 |
| TQQQ | 0.492460 | -0.580401 | 0.848483 |


## Required Answers

1. 是否找到 single-year share <= 50% 的 LGBModel 稳健组合：`True`。
2. 稳定化后 CAGR/Calmar 下降多少：见 `v8_2_year_stability_results.csv`；报告首行是当前 gate 排序下最佳组合。
3. Top10 是否优于 Top5：查看 TopK variant 行；本报告不因单一 CAGR 自动择优。
4. volatility targeting 是否有效：查看 `top*_voltarget*` 行的 single-year share、Calmar 和 50bps/T+1 指标。
5. YTD/rolling return cap 是否有效：查看 `top*_ytdcap*`、`top*_roll*cap*` 行。
6. 最佳组合是否满足 v9 gate：`True`。
7. 是否允许进入 v9：`True`。即使为 True，也需要用户另行批准；本轮不自动进入 v9。
8. 如果允许，v9 也只能考虑小幅科技成长池，不允许 Nasdaq100/S&P500 扩池。
9. 如果不允许，下一步应继续集中度修复或停止扩展，不能扩池补救。

## Caveats

This is a research validation replay.  It is not a live trading recommendation.  All caps and regime filters are computed from information available before or on the trading date, and audit-forward fields are not used.
