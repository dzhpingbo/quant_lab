# ChatGPT Review Packet

## Run

- run_id: `run_20260502_220641`
- run_dir: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\run_20260502_220641`
- zip_path: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\us_stock_selection_quant_lab_v8_2_year_stability_20260502_220641.zip`
- published_at: `2026-05-03T06:19:02`

## 本轮目标

本轮目标：执行 v8.2 year stability，不进入 v9，不扩 Nasdaq100/S&P500，不交易化。

## 新增/修改文件

- `quant_lab/us_stock_selection/v8_2_reporting.py`
- `quant_lab/us_stock_selection/v8_2_year_stability.py`
- `scripts/us_stock_selection/33_run_v8_2_year_stability.py`

## 核心结果 / RUN_SUMMARY

# RUN_SUMMARY

本轮目标：执行 v8.2 year stability，不进入 v9，不扩 Nasdaq100/S&P500，不交易化。

新 run 目录：`E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\run_20260502_220641`

最佳组合：`top5_ytdcap80p_derisk100p`
最终分类：`v9_ready_research_candidate`
是否允许进入 v9：`True`

最佳组合核心指标：
- CAGR: `0.6421259587785142`
- Calmar: `1.6339692500103946`
- MaxDD: `-0.39298533847832773`
- 50bps/T+1 CAGR: `0.5406125968868938`
- 50bps/T+1 Calmar: `1.3453472351463647`
- single-year share: `0.49683866511988606`
- top ticker share: `0.13793940593213985`
- remove top year CAGR: `0.5215869085057856`
- remove top year Calmar: `1.3272426664196029`
- remove top ticker CAGR: `0.4896536228676063`
- remove top ticker Calmar: `1.3265095931979178`

结论：本轮只做研究级 replay。即使 allow_enter_v9=True，也不自动进入 v9；必须用户另行批准。


## 核心指标

| strategy_id                 | classification                   | allow_enter_v9   |     cagr |   cost50_t1_cagr |   max_drawdown |   calmar |   cost50_t1_calmar |   single_year_share | top_ticker   |   top_ticker_share |   remove_top_year_cagr |   remove_top_year_calmar |   remove_top_ticker_cagr |   remove_top_ticker_calmar |
|:----------------------------|:---------------------------------|:-----------------|---------:|-----------------:|---------------:|---------:|-------------------:|--------------------:|:-------------|-------------------:|-----------------------:|-------------------------:|-------------------------:|---------------------------:|
| top5_ytdcap80p_derisk100p   | v9_ready_research_candidate      | True             | 0.642126 |         0.540613 |      -0.392985 |  1.63397 |            1.34535 |            0.496839 | INTC         |           0.137939 |               0.521587 |                  1.32724 |                 0.489654 |                    1.32651 |
| top10_ytdcap60p_derisk100p  | v9_ready_research_candidate      | True             | 0.545957 |         0.448799 |      -0.337242 |  1.61889 |            1.30526 |            0.491534 | PLTR         |           0.125087 |               0.443484 |                  2.22694 |                 0.448343 |                    1.47616 |
| top10_ytdcap60p_derisk75p   | v9_ready_research_candidate      | True             | 0.528814 |         0.441149 |      -0.337242 |  1.56805 |            1.28301 |            0.489769 | PLTR         |           0.12744  |               0.433782 |                  1.28626 |                 0.43254  |                    1.42413 |
| top10_ytdcap60p_derisk50p   | v9_ready_research_candidate      | True             | 0.510336 |         0.432047 |      -0.337242 |  1.51326 |            1.25654 |            0.499037 | PLTR         |           0.127878 |               0.409829 |                  1.21524 |                 0.415668 |                    1.36858 |
| top10_roll6mcap80p_derisk50 | v9_ready_research_candidate      | True             | 0.490016 |         0.423477 |      -0.337242 |  1.45301 |            1.23161 |            0.499506 | PLTR         |           0.126401 |               0.392319 |                  1.16332 |                 0.395882 |                    1.30343 |
| top10_roll3mcap30p_derisk50 | v9_ready_research_candidate      | True             | 0.438622 |         0.357871 |      -0.337242 |  1.30061 |            1.04081 |            0.486239 | PLTR         |           0.125431 |               0.359175 |                  1.06504 |                 0.355538 |                    1.1706  |
| top5_dropout_mw20p          | credible_but_execution_sensitive | False            | 0.889728 |         0.860729 |      -0.32347  |  2.75058 |            2.64083 |            0.5879   | MSTR         |           0.225358 |               0.6657   |                  2.058   |                 0.646176 |                    2.23625 |
| top5_roll6mcap80p_derisk50  | credible_but_execution_sensitive | False            | 0.825834 |         0.730898 |      -0.325076 |  2.54043 |            2.17229 |            0.639575 | PLTR         |           0.145191 |               0.489198 |                  1.50487 |                 0.645328 |                    2.30798 |
| top5_roll6mcap50p_derisk50  | credible_but_execution_sensitive | False            | 0.752507 |         0.653423 |      -0.303677 |  2.47798 |            2.06898 |            0.714423 | NVDA         |           0.133103 |               0.354797 |                  1.16833 |                 0.604937 |                    2.08746 |
| top5_voltarget20p_w60       | credible_but_execution_sensitive | False            | 0.468262 |         0.41726  |      -0.19944  |  2.34788 |            2.03179 |            0.71252  | PLTR         |           0.151433 |               0.228195 |                  1.14418 |                 0.372066 |                    2.31259 |
| top5_voltarget25p_w60       | credible_but_execution_sensitive | False            | 0.542323 |         0.480861 |      -0.244108 |  2.22165 |            1.91493 |            0.702274 | PLTR         |           0.146015 |               0.270654 |                  1.10874 |                 0.431381 |                    2.17892 |
| top5_equal_mw20p            | credible_but_execution_sensitive | False            | 0.803999 |         0.722266 |      -0.392985 |  2.04587 |            1.7974  |            0.657774 | PLTR         |           0.141455 |               0.452836 |                  1.1523  |                 0.634528 |                    1.92909 |
| top5_voltarget20p_w20       | credible_but_execution_sensitive | False            | 0.429937 |         0.358403 |      -0.210451 |  2.04293 |            1.64662 |            0.63699  | PLTR         |           0.153306 |               0.241945 |                  1.14965 |                 0.335519 |                    2.01612 |
| top5_voltarget25p_w20       | credible_but_execution_sensitive | False            | 0.516449 |         0.433827 |      -0.257091 |  2.00882 |            1.63352 |            0.647818 | PLTR         |           0.141216 |               0.277963 |                  1.08119 |                 0.411001 |                    2.00942 |
| top5_roll3mcap50p_derisk50  | credible_but_execution_sensitive | False            | 0.780623 |         0.673209 |      -0.392985 |  1.98639 |            1.67532 |            0.653399 | PLTR         |           0.137623 |               0.443893 |                  1.12954 |                 0.621225 |                    1.88864 |
| top5_equal_mw15p            | credible_but_execution_sensitive | False            | 0.583407 |         0.529361 |      -0.308471 |  1.89129 |            1.67514 |            0.639777 | PLTR         |           0.141455 |               0.348893 |                  1.13104 |                 0.466579 |                    1.82679 |
| top5_ytdcap80p_derisk50p    | credible_but_execution_sensitive | False            | 0.728209 |         0.635662 |      -0.392985 |  1.85302 |            1.58188 |            0.583858 | PLTR         |           0.141878 |               0.491149 |                  1.24979 |                 0.576652 |                    1.75313 |
| top5_ytdcap80p_derisk75p    | credible_but_execution_sensitive | False            | 0.686351 |         0.589081 |      -0.392985 |  1.7465  |            1.46596 |            0.542201 | PLTR         |           0.13888  |               0.507382 |                  1.2911  |                 0.544054 |                    1.65403 |
| top5_equal_mw10p            | credible_but_execution_sensitive | False            | 0.374152 |         0.34274  |      -0.215162 |  1.73894 |            1.55193 |            0.622835 | PLTR         |           0.141455 |               0.236611 |                  1.09969 |                 0.303359 |                    1.72158 |
| top10_ytdcap80p_derisk100p  | credible_but_execution_sensitive | False            | 0.516419 |         0.437219 |      -0.337242 |  1.5313  |            1.27158 |            0.563812 | PLTR         |           0.123218 |               0.358438 |                  1.06285 |                 0.422834 |                    1.39217 |

## Gate / Verdict

```json
{
  "stage": "v8.2_year_stability",
  "mainline": "Alpha360 + LGBModel + label_5d",
  "variant_count": 53,
  "result_count": 53,
  "best_strategy_id": "top5_ytdcap80p_derisk100p",
  "classification": "v9_ready_research_candidate",
  "allow_enter_v9": true,
  "reason": "All v8.2 gates passed, but this run still does not enter v9 automatically.",
  "no_v9_this_round": true,
  "no_universe_expansion": true,
  "no_model_training": true,
  "no_trading_claim": true
}
```

## 当前分类

- classification: `v9_ready_research_candidate`
- allow_enter_v9: `True`
- allow_enter_v10: ``

## 不通过原因 / 已知限制

- verdict.reason: `All v8.2 gates passed, but this run still does not enter v9 automatically.`
- 8. 如果允许，v9 也只能考虑小幅科技成长池，不允许 Nasdaq100/S&P500 扩池。
- 9. 如果不允许，下一步应继续集中度修复或停止扩展，不能扩池补救。
- ## Caveats

## 需要 ChatGPT 审阅的问题

1. 当前 classification 是否与 gate 证据一致？
2. 是否存在未来函数、样本选择偏差、执行口径或数据质量问题？
3. 是否应批准进入下一阶段，还是要求补验证？
4. 如果进入下一阶段，边界条件是否足够明确？

## Codex 建议的下一步

# NEXT_STEPS

当前状态：v9 small growth-pool pre-research 已完成。

- Run：`E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\run_20260502_222407`
- Classification：`not_v10_ready_growth_pool_sensitive`
- Allow v10：`False`

硬边界：

1. 本轮只验证小幅科技成长池。
2. 不扩 Nasdaq100，不扩 S&P500，不做全市场扩池。
3. 不交易化。
4. 是否进入 v10 需要用户另行批准。
5. 即使进入 v10，也应优先行业主题池/更严格 universe 设计，不应直接扩 Nasdaq100。


## 关键表格摘要

| csv                                                                                                      |   size_mb | bridge_mode         |
|:---------------------------------------------------------------------------------------------------------|----------:|:--------------------|
| outputs\us_stock_selection\run_20260502_220641\v8_2_year_stability\v8_2_annual_return_table.csv          |     0.008 | copy_if_selected    |
| outputs\us_stock_selection\run_20260502_220641\v8_2_year_stability\v8_2_benchmark_comparison.csv         |     0.001 | copy_if_selected    |
| outputs\us_stock_selection\run_20260502_220641\v8_2_year_stability\v8_2_daily_nav_by_strategy.csv        |     2.38  | copy_if_selected    |
| outputs\us_stock_selection\run_20260502_220641\v8_2_year_stability\v8_2_execution_stress_results.csv     |     0.148 | copy_if_selected    |
| outputs\us_stock_selection\run_20260502_220641\v8_2_year_stability\v8_2_leave_one_ticker_out.csv         |     0.013 | copy_if_selected    |
| outputs\us_stock_selection\run_20260502_220641\v8_2_year_stability\v8_2_leave_one_year_out.csv           |     0.013 | copy_if_selected    |
| outputs\us_stock_selection\run_20260502_220641\v8_2_year_stability\v8_2_monthly_holdings_by_strategy.csv |     9.825 | summary_if_selected |
| outputs\us_stock_selection\run_20260502_220641\v8_2_year_stability\v8_2_monthly_return_table.csv         |     0.075 | copy_if_selected    |
| outputs\us_stock_selection\run_20260502_220641\v8_2_year_stability\v8_2_ticker_contribution.csv          |     0.116 | copy_if_selected    |
| outputs\us_stock_selection\run_20260502_220641\v8_2_year_stability\v8_2_variant_config.csv               |     0.005 | copy_if_selected    |
| outputs\us_stock_selection\run_20260502_220641\v8_2_year_stability\v8_2_year_stability_results.csv       |     0.045 | copy_if_selected    |

## 重要 CSV 文件路径

- `outputs\us_stock_selection\run_20260502_220641\v8_2_year_stability\v8_2_annual_return_table.csv`
- `outputs\us_stock_selection\run_20260502_220641\v8_2_year_stability\v8_2_benchmark_comparison.csv`
- `outputs\us_stock_selection\run_20260502_220641\v8_2_year_stability\v8_2_daily_nav_by_strategy.csv`
- `outputs\us_stock_selection\run_20260502_220641\v8_2_year_stability\v8_2_execution_stress_results.csv`
- `outputs\us_stock_selection\run_20260502_220641\v8_2_year_stability\v8_2_leave_one_ticker_out.csv`
- `outputs\us_stock_selection\run_20260502_220641\v8_2_year_stability\v8_2_leave_one_year_out.csv`
- `outputs\us_stock_selection\run_20260502_220641\v8_2_year_stability\v8_2_monthly_holdings_by_strategy.csv`
- `outputs\us_stock_selection\run_20260502_220641\v8_2_year_stability\v8_2_monthly_return_table.csv`
- `outputs\us_stock_selection\run_20260502_220641\v8_2_year_stability\v8_2_ticker_contribution.csv`
- `outputs\us_stock_selection\run_20260502_220641\v8_2_year_stability\v8_2_variant_config.csv`
- `outputs\us_stock_selection\run_20260502_220641\v8_2_year_stability\v8_2_year_stability_results.csv`

## selected_report.md excerpt

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

