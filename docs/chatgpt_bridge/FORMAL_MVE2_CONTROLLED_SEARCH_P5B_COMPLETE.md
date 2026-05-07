# Formal MVE2 Controlled Search P5-B Complete

## Current Git Baseline

| Item | Value |
|---|---|
| Branch | master |
| HEAD at start | ac278dd35bc55f7c7d3055b0c70e85183e3d4f9b |
| origin/master at start | ac278dd35bc55f7c7d3055b0c70e85183e3d4f9b |
| ahead / behind at start | 0 / 0 |
| staged files at start | none |
| dirty worktree at start | group4 hold artifacts only |

## Task Scope

P5-B completed the controlled formal MVE2 full-search implementation and reran the controlled search command:

`python scripts/us_stock_selection/57_implement_formal_mve2_search.py --mode full_search --confirm-formal-search`

This round generated candidate evidence only. It did not replace the v8.2 baseline, did not create v10, did not train a model, and did not modify raw market data or audit CSV files.

## P5-B Output

- Output directory: `outputs/us_stock_selection/formal_mve2_controlled_search_p5b_20260507_215801/`
- Zip: `outputs/us_stock_selection/formal_mve2_controlled_search_p5b_20260507_215801.zip`
- Decision: `P5B_CONTROLLED_SEARCH_COMPLETED`
- Controlled search success: `true`

## Script And Compile

- Script path: `scripts/us_stock_selection/57_implement_formal_mve2_search.py`
- Script change: implemented controlled full-search logic inside the P3/P4 guardrails
- Compile check: `PASS`

## Execution Results

| Item | Result |
|---|---|
| full_search requested | Yes |
| confirmation flag provided | Yes |
| full_search executed | Yes |
| controlled search succeeded | Yes |
| parameter combinations | 18 |
| parameter combinations over 100 | No |
| candidate_summary contains real metrics | Yes |
| selected_candidates generated | Yes, P6 validation/audit only |
| rejected_candidates generated | Yes |
| benchmark_comparison generated | Yes |
| risk_flag_exposure generated | Yes |
| search result written as baseline | No |
| v10 created | No |

## Data Source Strategy

Allowed data source:

- `data/unified_ohlcv/us_stock_selection`

Core fields:

- `date`
- `ticker`
- `adj_close`
- `volume`

Excluded as data sources:

- old qlib
- old v8 cache
- formal v9 outputs
- v8.2 formal baseline outputs
- group4 artifacts

The search read 51 price parquet files and used only eligible tickers for candidate generation.

## Universe Strategy

| Item | Count | Rule |
|---|---:|---|
| search universe | 51 | fixed by P2-C passed audited-store universe |
| eligible | 40 | only eligible tickers enter candidate pool |
| excluded | 11 | observation and audit reference only |

No excluded ticker entered the formal candidate pool.

## Search Space

The controlled grid contains 18 combinations:

- `momentum_rank`: 6
- `momentum_low_vol`: 8
- `momentum_liquidity_guard`: 4

Rebalance is monthly. Weights are equal-weight. Default transaction cost is 10 bps, with cost-stress outputs at 0, 10, and 25 bps.

## Candidate / Rejection Summary

- Candidate rows: 18
- Selected rows: 3
- Rejected rows: 15

Selected rows are selected only for P6 validation / audit. They are not selected as a baseline.

Top selected candidate ids:

- `momentum_rank__p002`
- `momentum_rank__p004`
- `momentum_liquidity_guard__p016`

Important risk note: the top selected rows still show very large drawdowns in the controlled search output. P5-B is therefore candidate evidence only and requires P6 validation / audit before any interpretation of robustness.

## Benchmark Comparison

Benchmark comparison was generated against:

- SPY
- QQQ
- equal-weight eligible universe

For the selected rows, CAGR was above these reference benchmarks in the controlled output, but drawdown remains severe. v8.2 was not used as a data source and no v8.2 replacement decision was made.

## Risk Flag Exposure

Residual flags were carried into every candidate:

- volume warning tickers: AAPL, AMD, ARKK, IGV, INTC, SHOP
- price-jump warning tickers: AAPL, AMD, MSTR, ROKU, SHOP, SOXL, UPST

Risk flag exposure output is available in `risk_flag_exposure.csv`.

## v8.2 Baseline Comparison

v8.2 frozen Pool A `top5_ytdcap80p_derisk100p` remains the formal frozen baseline. P5-B does not replace it and does not promote any MVE2 result into baseline status.

P5-B generated reference benchmark comparisons but did not perform a formal v8.2 replacement gate. That must remain a later P7-style comparison after P6 validation / audit.

## P6 Status

P5-B allows a separate P6 formal MVE2 validation / audit pack task. It does not itself validate robustness, pass a baseline gate, or permit v10.

P6 should:

1. Recompute and audit the selected-for-validation candidates.
2. Stress-test costs, drawdowns, subperiods, and risk flag exposure.
3. Compare results against v8.2 only as a formal comparison baseline.
4. Preserve formal v9 as failed-branch warning context only.
5. Keep baseline replacement and v10 forbidden.

## Group4 And Existing Evidence Chains

- group4 artifacts were not touched.
- v8.2 formal baseline outputs were not modified.
- formal v9 outputs were not modified and remain a failed branch.
- limited MVE2 outputs and conclusions were not modified.
- raw market data was not modified.
- audit CSV files were not modified.

## Risk Notes

- P5-B is controlled search evidence, not validation.
- Selected candidates are P6 validation inputs only.
- Severe drawdowns in selected rows must be treated as a major P6 audit risk.
- Do not lower gates, costs, slippage, or data-quality standards to make candidates look better.
- Do not enter v10 from P5-B.
- Do not replace v8.2 from P5-B.
