# US Stock Selection v8 Final Acceptance - 2026-04-26

Scope: final closeout for v8 only. No v9 work, no Nasdaq100/S&P500 expansion, and no new long-running formal backtest task.

## 1. Final conclusion

v8 is accepted as a reproducible and operationally improved research result, but it is not accepted as a v9-ready candidate.

- Final classification: `credible_but_execution_sensitive`
- Allow entering v9: `False`
- Complete run: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\run_20260426_095958`
- Original complete zip: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\us_stock_selection_quant_lab_v8_paper_trading_20260426_095958.zip`

Core metrics from the complete run:

- CAGR: `0.6538182307494054`
- Calmar: `1.99152684432784`
- Max drawdown: `-0.32829998380969627`
- 50bps cost CAGR: `0.5608428724606129`
- T+1 CAGR: `0.6538182307494054`
- T+1 Calmar: `1.99152684432784`

## 2. Why the result is credible

The result is credible as a research artifact because the complete v8 run has the expected end-to-end outputs and the main paper replay can be independently reproduced by the new staged entry point.

Evidence:

- `run_20260426_095958/logs/run.log` reaches the final packaging step.
- `RUN_SUMMARY.md`, `v8_verdict.json`, markdown report, xlsx summary, execution stress CSV, attribution CSVs, and original zip are present.
- The final verdict is explicit and conservative: `credible_but_execution_sensitive`, `allow_enter_v9=False`.
- Execution stress, concentration checks, cost stress, T+1 replay, challenger evidence, and leave-one tests are included rather than hidden.
- The main blocking gate remains visible: `single_year_share_lte_50=False`.

## 3. Reproducibility, rebuildability, and operability evidence

Reproducibility:

- 31a formal validation run: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\run_20260426_212133`
- The 31a paper replay output matches the complete run `run_20260426_095958` field-by-field for:
  - `paper_trading_metrics.csv`
  - `monthly_decision_ledger.csv`
  - `monthly_holdings.csv`
  - `trades.csv`
  - `daily_nav.csv`
  - `fit_convergence_log.csv`

Rebuildability:

- 31d rebuilt report/xlsx/verdict/zip from existing results only.
- Rebuilt zip: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\us_stock_selection_quant_lab_v8_paper_trading_20260426_095958_31d_rebuild.zip`
- Rebuilt verdict matches the original conclusion: `credible_but_execution_sensitive`, `allow_enter_v9=False`, same paper CAGR and Calmar.

Operability:

- `--dry-run-init` now verifies argparse, config loading, logging, run directory creation, v8 subdirectory creation, and `run_config.yaml` writing before any heavy computation.
- 31a, 31b, 31c, and 31d provide staged execution boundaries.
- 31c sampled ElasticNet diagnostic now has per-fit subprocess timeout protection and a global runtime ceiling.
- 31c validation run: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\run_20260426_220735`
- 31c verified `timeout_terminated` and `global_timeout_not_started` states with fit start/end/elapsed/status logging.

## 4. 0/NaN forward-fill bug

Problem:

The earlier weight matrix handling treated `0` like a missing value during forward fill. That could preserve stale nonzero positions and inflate portfolio exposure to about 4x, making reported returns and risk invalid.

Fix approach:

- Keep true zero weights as explicit zero allocations.
- Only forward-fill actual missing rows that represent dates before or between rebalance assignments.
- Reindex weights to the trading calendar and fill remaining missing values with `0.0`.

Post-fix evidence:

- In the complete run, `monthly_holdings.csv` has max gross exposure `1.000000` and min gross exposure `1.000000`.
- Max net exposure is `1.000000` and min net exposure is `1.000000`.
- Count of gross exposure greater than `1.01` is `0`.
- 31a independently reproduced the same paper replay CSVs as the complete run.

Conclusion: the previous exposure inflation pattern is not present in the accepted v8 result chain.

## 5. Why v9 is still not allowed

v9 remains blocked because the result is still execution/concentration sensitive.

Main failed gate:

- `single_year_share_lte_50=False`
- Single-year share: `0.5260274868858267`

Additional caution:

- ElasticNet convergence warnings remain visible.
- `min_convergence_warning_rate` is `1.0`.
- Challenger results are helpful but do not erase the concentration and year-dependence concern.
- The result is research-credible, not trade-ready.

## 6. Remaining risks and limits

- Single-year contribution remains slightly above the 50% gate.
- Model convergence is not clean for ElasticNet.
- 31b Ridge/LGB challenger stage has not been formally re-run as a standalone long task in this final closeout.
- Execution stress is acceptable enough for research closeout, but the classification remains `credible_but_execution_sensitive`.
- No Nasdaq100/S&P500 expansion has been tested or approved.
- No v9 claim should be made from these v8 materials.

## 7. 31b status and role

31b was not formally run in the latest validation round because the instruction was to avoid new long-running formal tasks. Its entry point and parameters were checked, and it remains the optional next standalone validation stage.

Role of 31b:

- Re-run Ridge and LGB challenger checks as an isolated stage.
- Confirm whether challenger support remains close under the same staged workflow.
- Produce `v8_model_stability/challenger_model_results.csv` without coupling to the paper replay or reporting stage.

31b is not required to accept the current v8 closeout, because the full v8 run already contains challenger evidence and 31a/31d/31c validate reproducibility, rebuildability, and operability.

## 8. Recommended next order

If no more v8 work is desired:

1. Treat v8 as closed with classification `credible_but_execution_sensitive`.
2. Do not enter v9.
3. Do not expand universe.
4. Keep the complete run, original zip, staged validation zip, and final closeout zip as acceptance artifacts.

If one optional v8 supplement is desired later:

1. Run 31b as a standalone challenger validation.
2. Review `challenger_model_results.csv`.
3. Re-run 31d only if reporting needs to incorporate new 31b output.
4. Keep `allow_enter_v9=False` unless the single-year gate and execution sensitivity are explicitly resolved in a future approved research cycle.
