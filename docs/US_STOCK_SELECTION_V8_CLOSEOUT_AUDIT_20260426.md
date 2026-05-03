# US Stock Selection v8 Closeout Audit - 2026-04-26

Scope: v8 closeout and operational hardening only. No v9 work, no Nasdaq100/S&P500 expansion, and no full v8 rerun.

## Complete run audit

- Run directory: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\run_20260426_095958`
- Original zip: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\us_stock_selection_quant_lab_v8_paper_trading_20260426_095958.zip`
- Checked files: `RUN_SUMMARY.md`, `v8_verdict.json`, `reports/us_stock_selection_v8_paper_trading_report.md`, `reports/us_stock_selection_v8_summary.xlsx`, `v8_execution_sim/execution_stress_results.csv`, `logs/run.log`
- Logical completion: complete. The log reaches `Packaged v8 zip`, and report/xlsx/verdict/stress outputs are present.
- Classification: `credible_but_execution_sensitive`
- Allow entering v9: `False`

Key metrics:

- Paper CAGR: `0.6538182307494054`
- Paper Calmar: `1.99152684432784`
- 50bps cost CAGR: `0.5608428724606129`
- T+1 CAGR: `0.6538182307494054`
- T+1 Calmar: `1.99152684432784`
- Top ticker share: `0.22360323143558838`
- Single-year share: `0.5260274868858267`

Consistency checks:

- Excel sheets present: `paper_metrics`, `decision_ledger`, `monthly_holdings`, `trades`, `elasticnet_convergence`, `challenger_models`, `execution_stress`, `ticker_contribution`, `yearly_return`, `monthly_return`, `verdict`
- `execution_stress_results.csv`: 149 rows, 22 columns
- `monthly_holdings.csv`: 90 rows, 6 columns
- `daily_nav.csv`: 575 rows, 4 columns
- `trades.csv`: 145 rows, 6 columns
- Monthly holdings gross exposure: max `1.000000`, min `1.000000`
- Monthly holdings net exposure: max `1.000000`, min `1.000000`
- Count of gross exposure greater than 1.01: `0`

Conclusion: after the 0/NaN forward-fill weight bug fix, the complete v8 result chain is closed. The output no longer shows the previous exposure inflation pattern.

## Interrupted run audit

- Interrupted run directory: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\run_20260426_075758`
- Completed before interruption: paper replay outputs under `v8_paper_trading`
- Last logged stage: `Running ElasticNet convergence diagnostic`
- Last generated diagnostic file: `v8_model_stability/elasticnet_original_convergence_detail.csv`
- Missing completion files: `elasticnet_convergence_check.csv`, `challenger_model_results.csv`, `v8_execution_sim/execution_stress_results.csv`, report, `RUN_SUMMARY.md`, zip

Evidence-based conclusion: the run interrupted during ElasticNet convergence diagnostics after finishing the original ElasticNet detail file. There is no traceback in `logs/run.log`, and the evidence is insufficient to identify a specific ticker or decision window as stuck. The most likely cause is external shell/tool timeout during a long task.

## Operational changes

- Added `--dry-run-init` to `scripts/us_stock_selection/31_run_v8_paper_trading.py`
- Added `scripts/us_stock_selection/31a_run_v8_paper_replay_only.py`
- Added `scripts/us_stock_selection/31b_run_v8_challenger_ridge_lgb.py`
- Added `scripts/us_stock_selection/31c_run_v8_elasticnet_sampled.py`
- Added `scripts/us_stock_selection/31d_run_v8_reporting_and_zip.py`

Minimum verification completed:

- `python scripts/us_stock_selection/31_run_v8_paper_trading.py --dry-run-init`
- `python scripts/us_stock_selection/31a_run_v8_paper_replay_only.py --help`
- `python scripts/us_stock_selection/31b_run_v8_challenger_ridge_lgb.py --help`
- `python scripts/us_stock_selection/31c_run_v8_elasticnet_sampled.py --help`
- `python scripts/us_stock_selection/31d_run_v8_reporting_and_zip.py --help`

Dry-run init output:

- `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\run_20260426_211256`
