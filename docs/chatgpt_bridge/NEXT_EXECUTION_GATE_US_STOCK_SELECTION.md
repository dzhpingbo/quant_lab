# Next Execution Gate: US Stock Selection

Generated: 2026-05-07 Asia/Shanghai

## Purpose

This gate file defines the next safe execution boundary for `us_stock_selection`. It is documentation only: no strategy search, no model training, no formal v10, no script changes, and no group4 handling were performed to create it.

## 1. Current Git Baseline

- Branch: `master`
- HEAD before this gate commit: `d219dc903bae923830346e30580b5db48f7e2487`
- `origin/master` before this gate commit: `d219dc903bae923830346e30580b5db48f7e2487`
- Ahead/behind before this gate commit: `0 / 0`
- Staged files before this gate commit: none
- Dirty working tree before this gate commit: group4 hold artifacts only

Group4 remains local hold:

- `docs/chatgpt_bridge/runs/run_20260502_222407/`
- `docs/chatgpt_bridge/runs/run_20260503_172054/`

Group4 must not be modified, deleted, restored, moved, overwritten, staged, committed, or pushed unless a separate group4 task explicitly approves it.

## 2. Current Project Mainline

### v8.2 Frozen Formal Baseline

The current formal frozen baseline is v8.2 frozen Pool A `top5_ytdcap80p_derisk100p`.

- Source run: `v82_frozen_formal_audit_20260506_113454`
- Baseline source: v8.2 frozen score trail replayed under the formal evidence chain
- Key output directory: `outputs/us_stock_selection/v82_frozen_formal_audit_20260506_113454/`
- Bridge packet: `docs/chatgpt_bridge/runs/v82_frozen_formal_audit_20260506_113454/REVIEW_PACKET.md`
- Gate result: `PASS`
- Conclusion: `A`, can be retained as the formal frozen baseline
- Current use: official comparison baseline and frozen evidence anchor

Caveat:

- The v8.2 score trail is a v8.1 frozen runtime prediction trail.
- It is not a newly trained v9.1 score source.
- The pass conclusion is a formal replay / evidence audit pass, not proof that v9.1 retraining reproduces v8.2 score/rank.

Allowed usage:

- Use as the current formal baseline.
- Use as the anchor for future comparisons.
- Use only with the documented replay engine, execution assumptions, cost assumptions, and Pool A scope.

### Formal v9 Failed Branch

Formal v9 is a failed branch and must not be promoted to baseline.

- Source run: `formal_v9_20260505_224016`
- Bridge packet: `docs/chatgpt_bridge/runs/formal_v9_20260505_224016/REVIEW_PACKET.md`
- Audit report: `outputs/us_stock_selection/formal_v9_20260505_224016/audit/formal_v9_failure_audit.md`
- Gate result: failed
- Classification: `formal_v9_failed_due_to_concentration`
- v10 authorization: not allowed

Failure summary:

- v9.1 score/rank drift versus v8.2 frozen
- Pool A signal degradation under v9.1 score provenance
- Small-growth dilution
- Cost fragility
- Elevated single-year / regime contribution
- PLTR/MSTR/COIN dependency

Why it cannot be baseline:

- It fails the formal v9 performance and robustness gates.
- The small-growth expansion weakens results.
- Removing the top year or top ticker breaks the result.
- The audited failure is strategy-validity related, not a hidden engineering pass.

Allowed usage:

- Use only as a failed-case audit record and risk warning.
- Use for same-pool drift attribution if a future goal explicitly requests it.
- Do not use old v9 or unified replay as formal results.

### Limited MVE2 Independent Research Line

Limited MVE2 is a separate audited-store research lane.

- Search script: `scripts/us_stock_selection/49_run_limited_mve2_strategy_search.py`
- Validation script: `scripts/us_stock_selection/50_run_limited_mve2_validation_pack.py`
- Data source: audited unified adjusted OHLCV store
- Core fields: `date`, `adj_close`, `volume`
- Scope: limited MVE2 only
- Formal status: not formal MVE2

Boundary versus v8.2 / formal v9:

- It does not use the v8.2 formal baseline evidence chain.
- It does not use formal v9 as a baseline.
- It must not use old Qlib, old v8 cache, or unaudited data.
- It should produce separate reports, manifests, metrics, and zip outputs.

Formal MVE2 is not authorized yet. Before formal MVE2, the project must pass the formal MVE2 prerequisites below.

## 3. Data Quality Gate

Before any next execution step, verify:

- Data source is unique and explicitly named for the task.
- Audited store is used where required by the task.
- Old Qlib, old v8 cache, and unaudited data are excluded unless the task is explicitly an evidence comparison.
- `adj_close` and `volume` are available where the audited-store scripts require them.
- For formal replay, provider-bin `$close` and `$volume` source policy is documented.
- Ticker universe is fixed before execution.
- Eligible and excluded ticker lists are reproducible.
- Observation-only tickers cannot enter formal TopK.
- Output directory is new and not overwritten.
- README, manifest, zip, key metrics, and decision/gate evidence are generated when the task is a run.
- Failures, warnings, missing data, and exclusions are preserved in the report.
- No result is reclassified as passing without gate evidence.

## 4. Formal MVE2 Prerequisites

Formal MVE2 may be designed only after a separate approval gate. At minimum it must define:

- Formal MVE2 universe
- Data source and data quality inventory
- Time interval and train/test or validation windows
- Rebalance frequency
- Execution assumptions
- Cost and slippage assumptions
- Risk constraints and max drawdown context
- Benchmarks
- Validation metrics
- Concentration tests
- Recent-window degradation tests
- Cost sensitivity tests
- Excluded and observation-only ticker policy
- Failed-branch isolation rules
- Output package structure
- README / manifest / zip / key metrics requirements
- Commit/stage rules, including explicit `git diff --cached --name-only`

Formal MVE2 must not inherit formal v9's failed branch as a baseline and must not mix limited MVE2 evidence into the v8.2 formal baseline.

## 5. Recommended Next Execution Plan

### P1: limited MVE2 validation pack review and strengthening

Reason: limited MVE2 already has an audited-store lane and frozen validation pack structure. The safest next action is to review, explain, and strengthen validation evidence without converting it to formal MVE2.

Allowed shape:

- Review existing validation output.
- Identify missing README / manifest / zip / key metrics gaps.
- Add evidence checks only if explicitly requested.
- Do not run broad searches or new model training.

### P2: formal MVE2 data quality gate

Reason: formal MVE2 requires a separate data-quality gate before any formal search or candidate declaration.

Allowed shape:

- Define formal universe.
- Verify audited data source, `adj_close`, `volume`, eligibility, exclusions, and output package requirements.
- Produce a gate report before any formal MVE2 search.

### P3: formal MVE2 search task design

Reason: search design should happen only after P2 passes. It must specify exact universe, metrics, windows, benchmark, and failure handling before execution.

Allowed shape:

- Draft formal MVE2 search plan.
- Define fixed parameters and gates.
- Do not execute until explicitly approved.

### P4: group4 separate handling

Reason: group4 artifacts have historical value and risk signals. They should remain on local hold until a dedicated task reviews archive, cleanup, restore, or deletion.

Allowed shape:

- Separate group4 review only.
- No mixing with research or documentation commits.

### Why not run v10 now

- formal v9 failed its gate.
- v8.2 remains the baseline, but v9.1 retrain did not reproduce the v8.2 score/rank path.
- Small-growth expansion diluted results.
- v10, expansion, and new strategy search require explicit human approval and a new gate.

## 6. Forbidden Actions

- Do not use formal v9 as a baseline.
- Do not mix limited MVE2 evidence with the v8.2 formal baseline evidence chain.
- Do not enter v10.
- Do not expand Nasdaq100, S&P500, or full-market pools.
- Do not run broad strategy search or parameter search.
- Do not lower gates, costs, slippage, execution delay, or price-source standards.
- Do not trade, connect brokers/APIs, or place orders.
- Do not use `git add .`.
- Do not force push.
- Do not handle group4 in unrelated tasks.
- Do not submit run artifacts with token/auth/secret keyword risk or Windows absolute-path risk before review.

## 7. Commit Gate For This File

This file is the only allowed staged file for its commit:

- `docs/chatgpt_bridge/NEXT_EXECUTION_GATE_US_STOCK_SELECTION.md`

Do not stage:

- `docs/chatgpt_bridge/runs/`
- `outputs/`
- `scripts/`
- group4 artifacts
