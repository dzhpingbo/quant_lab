# Formal MVE2 Search Implementation P4 Complete

## Current Git Baseline

| Item | Value |
|---|---|
| Branch | master |
| HEAD at start | 9fead14a16b5acf4cf5f3c0c6a60a3335d8c81a6 |
| origin/master at start | 9fead14a16b5acf4cf5f3c0c6a60a3335d8c81a6 |
| ahead / behind at start | 0 / 0 |
| staged files at start | none |
| dirty worktree at start | group4 hold artifacts only |

## Task Scope

This round implemented the P4 formal MVE2 search scaffold and ran dry-run / smoke-test only.

It did not:

- execute full search
- execute formal MVE2 production search
- run broad strategy search
- run `scripts/us_stock_selection/49_run_limited_mve2_strategy_search.py`
- train a model
- create v10
- create a selected formal candidate
- create a formal candidate ranking
- replace or challenge the v8.2 frozen baseline
- modify raw market data
- modify audit CSV files
- modify v8.2 formal baseline outputs
- modify formal v9 outputs
- modify limited MVE2 conclusions
- touch group4 artifacts

## P4 Dry-Run Output

- Output directory: `outputs/us_stock_selection/formal_mve2_search_implementation_p4_dryrun_20260507_194318/`
- Zip: `outputs/us_stock_selection/formal_mve2_search_implementation_p4_dryrun_20260507_194318.zip`
- Dry-run result: `success`

## Script

- Script path: `scripts/us_stock_selection/57_implement_formal_mve2_search.py`
- Compile check: `PASS`
- Default mode: `--mode dry_run`
- Future full-search mode requires separate explicit task approval and was not run in P4.

## Execution Checks

| Check | Result |
|---|---|
| Only dry-run executed | Yes |
| full_search executed | No |
| formal MVE2 production search executed | No |
| model training executed | No |
| formal candidate ranking generated | No |
| selected formal candidate generated | No |
| v10 executed | No |

## Data Source Strategy

Formal MVE2 data source is limited to the audited unified adjusted OHLCV store:

- `data/unified_ohlcv/us_stock_selection`
- core fields: `date`, `ticker`, `adj_close`, `volume`

Excluded as data sources:

- old qlib
- old v8 cache
- formal v9 outputs
- v8.2 formal baseline outputs
- group4 artifacts

v8.2 may be used only as comparison baseline metadata. Formal v9 may be used only as failed-branch warning context. Limited MVE2 may be used only as independent research context.

## Universe Strategy

| Item | Count | Rule |
|---|---:|---|
| search universe | 51 | fixed by P2-C passed audited-store universe |
| eligible | 40 | only eligible tickers may enter future formal candidate pool |
| excluded | 11 | observation and audit reference only |

Excluded tickers are not allowed in the future formal candidate pool.

## Benchmark Strategy

Allowed:

- v8.2 frozen Pool A `top5_ytdcap80p_derisk100p` as formal comparison baseline
- SPY and QQQ as reference benchmarks when supported by audited-store data
- equal-weight eligible universe as a reference benchmark in future P5

Not allowed:

- formal v9 as benchmark or baseline
- limited MVE2 as formal baseline

## Risk Flag Strategy

Residual warnings are carried forward into future formal search design and output packages:

- volume warning tickers: AAPL, AMD, ARKK, IGV, INTC, SHOP
- price-jump warning tickers: AAPL, AMD, MSTR, ROKU, SHOP, SOXL, UPST

These flags do not block P4 dry-run. They must remain visible in P5 if a controlled search run is later approved.

## Search Space Scaffold

The script defines but does not execute:

- trend-following families
- time-series momentum families
- volatility filters
- drawdown guardrails
- ranking rules
- monthly / quarterly rebalance options
- max position constraints
- turnover constraints
- transaction cost grids
- slippage grids
- walk-forward design
- overfitting and multiple-testing controls
- candidate promotion / rejection rules

## Output Package Schema

P4 defines the future P5 output package schema, including:

- README
- manifest
- formal search report
- candidate summary
- selected / rejected candidate files
- benchmark comparison
- yearly and subperiod performance
- drawdown and turnover summaries
- cost-stress summary
- risk-flag exposure
- parameter grid summary
- run config
- reproducibility checklist
- formal search decision file
- small tables
- zip package

P4 itself does not create formal result files for selected candidates.

## Guardrails

P4 guardrails record:

- dry_run_only = true
- full_search_not_executed = true
- no_candidate_selected = true
- no_formal_candidate_ranking = true
- no_baseline_replacement = true
- no_v10 = true
- no_training = true
- no_original_data_modified = true
- audit_csv_not_modified = true
- group4_not_touched = true
- formal_v9_not_used_as_baseline = true
- limited_mve2_not_used_as_formal_baseline = true

## P5 Eligibility

P4 dry-run succeeded, so the project may proceed to P5 only as a separately approved controlled formal MVE2 search run task.

P5 must still:

- explicitly approve controlled search execution
- keep direct v10 forbidden
- keep baseline replacement forbidden
- keep group4 untouched
- stage only approved P5 files
- preserve v8.2 as comparison baseline
- preserve formal v9 as a failed branch

## Risk Notes

- P4 is an implementation scaffold, not evidence that any formal MVE2 candidate works.
- No formal MVE2 result should be promoted from P4.
- Residual volume and price-jump flags must stay in future output packages.
- Future P5 must not lower gates, costs, slippage, or data-quality standards after seeing results.
- Files containing private access material or local machine path details must not be committed.

## Next P5 Goals Draft

Recommended next task: P5 controlled formal MVE2 search run.

P5 should:

1. Start with Git and group4 safety checks.
2. Explicitly approve controlled search execution before using any mode beyond dry-run.
3. Use `scripts/us_stock_selection/57_implement_formal_mve2_search.py` as the implementation base.
4. Use only audited-store eligible tickers.
5. Produce the full output package schema defined in P4.
6. Record all tested candidates and rejected candidates.
7. Keep v8.2 as comparison baseline only.
8. Keep formal v9 as failed-branch warning context only.
9. Keep limited MVE2 as independent research context only.
10. Keep v10 and baseline replacement forbidden until later validation and human review.
