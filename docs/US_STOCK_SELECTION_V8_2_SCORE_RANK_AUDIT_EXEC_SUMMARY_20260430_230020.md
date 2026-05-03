# US Stock Selection v8.2 Score/Rank Audit Exec Summary

- Instrumentation completed: `True`
- Existing run full candidate score/rank recovered: `False`
- Existing run remains selected-only: `True`
- Can run gate-aware reranking replay: `False`
- Main blocker: `full candidate universe rows are missing; audit remains selected-only; unselected tickers are absent; full candidate raw/adjusted scores are missing`
- Next required patch: `continue upstream logging: persist full pred/tradable/ranked snapshot from run_paper_trading_replay without retraining current v8 baseline`

## Quality Snapshot

| decision_date   |   candidate_count |   original_tradable_count |   selected_count |   unselected_count | selected_flag_consistent_with_holdings   | quality_pass   | warnings                  |
|:----------------|------------------:|--------------------------:|-----------------:|-------------------:|:-----------------------------------------|:---------------|:--------------------------|
| 2025-03-31      |                 5 |                        36 |                5 |                  0 | True                                     | False          | selected-only audit trail |
| 2025-10-31      |                 5 |                        36 |                5 |                  0 | True                                     | False          | selected-only audit trail |
