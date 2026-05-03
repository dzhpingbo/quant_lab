# US Stock Selection v8 Executive Summary - 2026-04-26

Final verdict: `credible_but_execution_sensitive`

Allow entering v9: `False`

Complete run: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\run_20260426_095958`

Original zip: `E:\dzhwork\quant\quant_lab\outputs\us_stock_selection\us_stock_selection_quant_lab_v8_paper_trading_20260426_095958.zip`

## Key metrics

- CAGR: `0.6538182307494054`
- Calmar: `1.99152684432784`
- MaxDD: `-0.32829998380969627`
- 50bps cost CAGR: `0.5608428724606129`

## What was validated

- 31a proved paper replay reproducibility: `run_20260426_212133` reproduced the complete run's six core paper replay CSVs field-by-field.
- 31c proved operational protection: sampled ElasticNet fits can be terminated by per-fit subprocess timeout and global timeout, with status/elapsed logging.
- 31d proved rebuildability: report/xlsx/verdict/zip can be rebuilt by reading existing result files, without core backtests.

## Main remaining gate

- `single_year_share_lte_50=False`
- Single-year share: `0.5260274868858267`

## Next recommendation

Close v8 as a credible but execution-sensitive research artifact. Do not enter v9 and do not expand Nasdaq100/S&P500. Optional later supplement: run 31b standalone challenger validation, then rebuild reports with 31d if needed.
