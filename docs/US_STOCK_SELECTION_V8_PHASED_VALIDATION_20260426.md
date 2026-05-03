# US Stock Selection v8 Phased Validation - 2026-04-26

Scope: small formal validation of the v8 phased scripts. No v9 work, no Nasdaq100/S&P500 expansion, and no full v8 rerun.

## A. 31a paper replay only

Command:

```powershell
python scripts/us_stock_selection/31a_run_v8_paper_replay_only.py
```

Result:

- Run directory: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\run_20260426_212133`
- Log: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\run_20260426_212133\logs\31a_paper_replay_only.log`
- Started: `2026-04-26 21:21:33`
- Completed: `2026-04-26 22:04:31`
- Stage isolation: only paper replay ran; no challenger, ElasticNet sampled diagnostic, execution stress, reporting, or zip stage was launched.

Key metrics:

- Total return: `2.15161830078071`
- CAGR: `0.6538182307494054`
- Max drawdown: `-0.32829998380969627`
- Calmar: `1.99152684432784`
- Sharpe: `1.487422627422491`
- Annual turnover: `12.709565217391305`
- Exposure: `0.9634782608695652`
- Daily count: `575`

Output files:

- `v8_paper_trading/paper_trading_metrics.csv`
- `v8_paper_trading/monthly_decision_ledger.csv`
- `v8_paper_trading/monthly_holdings.csv`
- `v8_paper_trading/trades.csv`
- `v8_paper_trading/daily_nav.csv`
- `v8_paper_trading/fit_convergence_log.csv`

Comparison with complete run `run_20260426_095958`:

- `paper_trading_metrics.csv`: match
- `monthly_decision_ledger.csv`: match
- `monthly_holdings.csv`: match
- `trades.csv`: match
- `daily_nav.csv`: match
- `fit_convergence_log.csv`: match

Conclusion: 31a is a real executable stage and reproduces the complete v8 paper replay outputs exactly under the current data/provider state.

## B. 31d reporting and zip only

Command:

```powershell
python scripts/us_stock_selection/31d_run_v8_reporting_and_zip.py --run-dir outputs/us_stock_selection/run_20260426_095958 --timestamp 20260426_095958_31d_rebuild
```

Result:

- Input run: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\run_20260426_095958`
- 31d log: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\run_20260426_095958\logs\31d_reporting_and_zip.log`
- Rebuilt zip: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\us_stock_selection_quant_lab_v8_paper_trading_20260426_095958_31d_rebuild.zip`
- Original zip: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\us_stock_selection_quant_lab_v8_paper_trading_20260426_095958.zip`

Zip comparison:

- Original zip entries: `189`
- Rebuilt zip entries: `198`
- Original zip size: `737071` bytes
- Rebuilt zip size: `767866` bytes
- Reason for difference: the rebuilt package includes the newly added phased scripts and 31d stage log/marker files. Core verdict fields match.

Verdict consistency:

- Classification: `credible_but_execution_sensitive`
- Allow entering v9: `False`
- Paper CAGR: `0.6538182307494054`
- Paper Calmar: `1.99152684432784`

Conclusion: 31d can rebuild report/xlsx/verdict/zip from existing files without launching core backtests.

## C. 31c sampled ElasticNet timeout validation

Command:

```powershell
python scripts/us_stock_selection/31c_run_v8_elasticnet_sampled.py --sample-mode representative --max-sample-months 1 --per-fit-timeout-seconds 5 --max-seconds 8
```

Result:

- Run directory: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\run_20260426_220735`
- Log: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\run_20260426_220735\logs\31c_elasticnet_sampled.log`
- Sample month: `2024-01-31`
- Summary file: `v8_model_stability/elasticnet_convergence_check.csv`
- Detail files:
  - `v8_model_stability/elasticnet_original_sampled_convergence_detail.csv`
  - `v8_model_stability/elasticnet_max_iter_10000_sampled_convergence_detail.csv`
  - `v8_model_stability/elasticnet_max_iter_50000_tol_1e3_sampled_convergence_detail.csv`

Timeout validation:

- `elasticnet_original`: `timeout_terminated`, elapsed `5.094` seconds
- `elasticnet_max_iter_10000`: `timeout_terminated`, elapsed `3.047` seconds
- `elasticnet_max_iter_50000_tol_1e3`: `global_timeout_not_started`

Conclusion: 31c successfully generated sampled result files and verified both per-fit subprocess termination and global timeout protection. The log records each fit start, finish/skip, elapsed time, status, and warning count.

## D. 31b status

31b was not formally run in this validation, by instruction. The entry point and parameters were checked with `--help`.

Recommended future command:

```powershell
python scripts/us_stock_selection/31b_run_v8_challenger_ridge_lgb.py --run-dir E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\run_20260426_212133
```

Risk and monitoring points:

- Monitor `logs/31b_challenger_ridge_lgb.log`
- Confirm `v8_model_stability/challenger_model_results.csv` is generated
- Confirm LGBModel is genuinely available; if LightGBM import fails, the model factory falls back to Ridge-like behavior
- Watch `decision_count`, `warning_count`, `cagr`, `calmar`, runtime, CPU, and memory
