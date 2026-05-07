# Formal MVE2 Search Design P3

This document is the P3 design gate for the formal MVE2 research lane. It is documentation only. It does not execute formal MVE2 search, does not train a model, does not create v10, and does not replace the current v8.2 frozen baseline.

## Current Git Baseline

| Item | Value |
|---|---|
| Branch | master |
| HEAD at design start | 7ae7e67a85fcd9b5649a052219a20382d941d186 |
| origin/master at design start | 7ae7e67a85fcd9b5649a052219a20382d941d186 |
| ahead / behind at design start | 0 / 0 |
| staged files at design start | none |
| dirty worktree at design start | group4 hold artifacts only |

Group4 remains local hold and is not an input to this design. It must not be modified, deleted, restored, moved, overwritten, staged, committed, or pushed unless a separate group4 task explicitly opens that scope.

## P3 Entry Basis

P3 is allowed because the P2-C final readiness decision is `PASS_TO_P3_FORMAL_MVE2_DESIGN`.

| Stage | Decision | Blocking issue | Resolution status | Evidence |
|---|---|---|---|---|
| P2-A | CONDITIONAL_NEEDS_REVIEW | non-positive volume, large price jumps, audit metadata conflict | reviewed by P2-B and P2-B2 | outputs/us_stock_selection/formal_mve2_data_quality_gate_20260507_142224/ |
| P2-B | CONDITIONAL_NEEDS_DATA_REVIEW | audit metadata conflict | reconciled by P2-B2 | outputs/us_stock_selection/formal_mve2_data_quality_gate_p2b_exceptions_20260507_151856/ |
| P2-B2 | PASS_TO_P2C_GATE_RECHECK | none for P2-C | passed to P2-C | outputs/us_stock_selection/formal_mve2_audit_metadata_reconciliation_p2b2_20260507_161429/ |
| P2-C | PASS_TO_P3_FORMAL_MVE2_DESIGN | none | P3 design allowed | outputs/us_stock_selection/formal_mve2_data_quality_gate_p2c_recheck_20260507_170809/ |

P2-C reports unresolved blockers = `0`. The remaining volume and price-jump items are accepted quality flags for design only. They do not permit a formal search run.

## Formal MVE2 Target

P3 defines the future formal MVE2 search task. It is not:

- a formal MVE2 search run
- a model training run
- a v10 task
- a replacement for the v8.2 frozen baseline
- a promotion of limited MVE2 into a formal baseline
- a use of the formal v9 failed branch as a baseline

The next executable stage, if approved, should be P4 formal MVE2 search implementation.

## Evidence Chain Boundaries

### A. v8.2 Frozen Formal Baseline

The current formal comparison baseline is v8.2 frozen Pool A `top5_ytdcap80p_derisk100p`.

Allowed use:

- comparison baseline
- formal audit reference
- guardrail for promotion decisions

Forbidden use:

- do not use v8.2 outputs as the formal MVE2 data source
- do not mix v8.2 evidence into the limited MVE2 evidence chain
- do not claim v9.1 retraining reproduced v8.2 score/rank

Important caveat: the v8.2 score trail is a frozen v8.1 runtime prediction trail. The v8.2 formal audit pass is a formal replay and evidence audit pass, not proof that v9.1 retraining can reproduce the v8.2 score/rank path.

### B. Formal v9 Failed Branch

Formal v9 / v9.1 is a failed branch. It cannot be used as a baseline, benchmark, or v10 entry point.

Failure drivers include:

- v9.1 score/rank drift versus v8.2 frozen
- small-growth dilution
- cost fragility
- elevated single-year contribution
- PLTR/MSTR/COIN dependency

Allowed use:

- failure case
- risk warning
- design anti-pattern reference

Forbidden use:

- do not use formal v9 as a formal MVE2 baseline
- do not use formal v9 outputs as a data source
- do not use old v9 or unified replay as formal evidence

### C. Limited MVE2 Independent Research Line

Limited MVE2 is an independent audited-store research lane. It uses the audited unified adjusted OHLCV store and remains separate from v8.2 and formal v9 evidence chains.

Current status:

- validation pack exists at `outputs/us_stock_selection/limited_mve2_validation_20260502_183555/`
- candidate count: 9
- decision distribution: 1 pass-to-next-validation, 6 conditional, 2 observation-only
- all candidates have `formal_mve2_supported=false`
- limited MVE2 has not entered formal MVE2

Allowed use:

- research context
- evidence about candidate behavior inside the audited-store lane
- warning context for formal MVE2 design

Forbidden use:

- do not promote limited MVE2 directly into a formal baseline
- do not use limited MVE2 as a v10 entry point
- do not mix limited MVE2 outputs into v8.2 formal baseline evidence

### D. Formal MVE2 Search Design

Formal MVE2 search design is a new formal design lane. Its data source is limited to the audited unified adjusted OHLCV store and explicitly excludes old Qlib, old v8 cache, formal v9 output, v8.2 formal baseline output, and group4.

P3 can define what P4 should implement. P3 cannot execute that implementation.

## Data Source Design

Formal MVE2 must use:

- data root: `data/unified_ohlcv/us_stock_selection`
- price entity directory: `data/unified_ohlcv/us_stock_selection/prices`
- audit support directory: `data/unified_ohlcv/us_stock_selection/audit`
- core fields: `date`, `ticker`, `adj_close`, `volume`

Optional fields may be read and summarized when present:

- `open`
- `high`
- `low`
- `close`
- corporate action fields when available

Explicit exclusions:

- old Qlib data
- old v8 cache
- formal v9 outputs
- v8.2 formal baseline outputs as data source
- group4 artifacts
- broad universe expansion not approved by a separate task

Residual warnings from P2-C must become formal risk flags in P4:

- non-positive volume flags
- large adjusted-price jump flags

## Universe Design

Formal MVE2 should start from the P2-C passed audited-store universe.

| Universe item | Count | Design rule |
|---|---:|---|
| search universe | 51 | fixed by audited store and limited MVE2 universe evidence |
| eligible | 40 | allowed formal candidate pool |
| excluded | 11 | observation and audit reference only |

Formal search should use eligible tickers only. Excluded tickers cannot enter the formal candidate pool.

Eligible tickers:

`AAPL`, `ADBE`, `AMD`, `AMZN`, `ARKK`, `AVGO`, `CIBR`, `CRM`, `DIA`, `GLD`, `GOOGL`, `IBB`, `IGV`, `INTC`, `IWM`, `META`, `MSFT`, `MSTR`, `MU`, `NFLX`, `NOW`, `NVDA`, `ORCL`, `PANW`, `QLD`, `QQQ`, `SHOP`, `SHY`, `SKYY`, `SMH`, `SOXL`, `SOXX`, `SPY`, `SSO`, `TLT`, `TQQQ`, `TSLA`, `UPRO`, `XBI`, `XLK`.

Excluded tickers:

`AFRM`, `COIN`, `CRWD`, `LCID`, `NET`, `PLTR`, `RIVN`, `ROKU`, `SNOW`, `UBER`, `UPST`.

Excluded reason recorded in the limited MVE2 universe evidence: listed history below the 10-year readiness requirement or not ready for MVE2.

Residual warning handling:

| Warning type | Tickers | P4 design action |
|---|---|---|
| non-positive volume | AAPL, AMD, ARKK, IGV, INTC, SHOP | keep with risk flag; do not exclude automatically |
| large adjusted-price jump | AAPL, AMD, MSTR, ROKU, SHOP, SOXL, UPST | keep eligible tickers with risk flag; excluded tickers remain observation-only |

## Benchmark Design

Required formal comparison baseline:

- v8.2 frozen Pool A `top5_ytdcap80p_derisk100p`

Reference benchmarks, subject to audited-store data availability:

- SPY
- QQQ
- equal-weight eligible universe
- cash or low-risk proxy when used only for drawdown context, such as SHY or TLT

Limited MVE2 candidates may be used only as research references. Formal v9 must not be used as a benchmark.

## Search Space Design

P4 should implement a controlled search space before any full run is approved.

Strategy families to consider:

- trend following using `adj_close`
- time-series momentum using `adj_close`
- volatility filter using `adj_close` and realized volatility
- drawdown or trailing stop guardrail using `adj_close`
- cross-sectional rank blend using audited-store price and volume features
- defensive allocation rule using eligible ETF proxies

Signal candidates:

- 20/120, 50/200, and related moving-average states
- 63-day and 126-day momentum states
- realized volatility filter over 20, 63, and 252 trading days
- drawdown from rolling high
- volume availability and liquidity flags
- price-jump risk flag exposure

Ranking rules:

- rank by risk-adjusted return on validation windows
- penalize high drawdown, high turnover, low liquidity, and warning-flag concentration
- separate raw performance rank from robustness rank
- require benchmark-relative context

Rebalance frequency candidates:

- monthly
- quarterly
- event-driven exits only where rules are deterministic and predeclared

Holding constraints:

- use eligible universe only
- no excluded ticker in formal candidate pool
- no single ticker over 20% unless a later design gate explicitly changes this
- prefer diversified baskets over single-name concentration
- require position count and cash exposure reporting

Transaction assumptions:

- base transaction cost should be explicitly set in run_config
- slippage should be explicitly set in run_config
- cost-stress scenarios must include at least 0, 5, 10, 20, and 50 bps where feasible
- P4 must not lower costs or slippage to make results pass

Parameter ranges:

- moving average fast window: 20, 50, 63
- moving average slow window: 120, 200, 252
- momentum window: 21, 63, 126, 252
- volatility window: 20, 63, 252
- trailing drawdown stop: 10%, 15%, 20%, 25%
- max position weight: 10%, 15%, 20%
- rebalance frequency: monthly, quarterly

Train / validation / holdout design:

- keep a predeclared split before search execution
- use walk-forward or fixed out-of-sample windows
- reserve a final holdout that is not used for selection
- record candidate count and parameter count for multiple-testing context

Overfitting controls:

- predeclare parameter grid
- record every tested candidate
- use selection thresholds that penalize complexity
- require subperiod robustness
- require cost-stress robustness
- report rejected candidates, not only selected candidates
- require human review before any baseline promotion

Candidate promotion / rejection:

- promotion requires gate pass on return, drawdown, risk-adjusted return, cost stress, concentration, liquidity, and subperiod robustness
- conditional candidates must stay conditional until a validation pack and audit pass
- observation-only candidates cannot enter the formal portfolio candidate pool

## Risk Constraint Design

P4 must implement or explicitly report these constraints:

- maximum drawdown limit
- Calmar threshold
- Sharpe threshold
- turnover upper bound
- concentration limit
- single ticker contribution limit
- liquidity filter
- volume risk flag handling
- price jump risk flag handling
- cost-stress robustness
- subperiod robustness
- benchmark-relative performance
- crash-period robustness where data supports it

Suggested initial thresholds for design discussion, not execution approval:

- Calmar >= 1.0
- Sharpe >= 0.8
- maximum drawdown no worse than the approved gate threshold
- annual turnover within a predeclared upper bound
- no single ticker dominance in contribution
- cost50 results remain positive and risk-adjusted metrics remain acceptable

P4 must not silently change these thresholds after seeing results.

## Evaluation Metrics

P4 output should include:

- CAGR
- maximum drawdown
- Calmar
- Sharpe
- Sortino if feasible
- volatility
- turnover
- win rate or hit rate if feasible
- benchmark excess return
- benchmark tracking and correlation if feasible
- yearly return
- subperiod return
- drawdown duration
- cost-stress sensitivity
- concentration metrics
- risk flag exposure
- eligible/excluded compliance

## Output Package Design

If P4 later implements formal MVE2 search, its suggested output directory is:

`outputs/us_stock_selection/formal_mve2_search_YYYYMMDD_HHMMSS/`

The output package should include at least:

- `README.md`
- `manifest.json`
- `formal_mve2_search_report.md`
- `candidate_summary.csv`
- `selected_candidates.csv`
- `rejected_candidates.csv`
- `benchmark_comparison.csv`
- `yearly_performance.csv`
- `subperiod_performance.csv`
- `drawdown_summary.csv`
- `turnover_summary.csv`
- `cost_stress_summary.csv`
- `risk_flag_exposure.csv`
- `parameter_grid_summary.csv`
- `run_config.json`
- `reproducibility_checklist.csv`
- `formal_mve2_search_decision.json`
- `small_tables/`
- zip package

Minimum manifest fields:

- run_id
- run_type
- generated_at
- git_commit
- script_path
- input_paths
- output_dir
- data_source_policy
- universe_count
- eligible_count
- excluded_count
- parameter_grid_summary
- generated_files
- explicit_exclusions
- direct_v10_allowed=false
- formal_baseline_replaced=false
- group4_hold_not_touched=true

## Promotion / Gate Rules

Formal MVE2 search results cannot automatically become a baseline.

The minimum path before baseline candidacy is:

1. P4: formal MVE2 search implementation
2. P5: formal MVE2 search run
3. P6: formal MVE2 validation / audit pack
4. P7: comparison against v8.2 frozen baseline
5. P8: decision gate

Only after those stages can a human review decide whether a formal MVE2 result becomes a new baseline candidate.

## Commit And Stage Rules

Every commit in this lane must:

- list staged files before commit
- avoid `git add .`
- avoid staging group4
- avoid staging unrelated scripts or outputs
- avoid staging formal v9 output
- avoid staging v8.2 baseline output unless the task explicitly targets those artifacts
- avoid files containing sensitive access material
- avoid force push

## Forbidden Actions

- Do not execute P3 search.
- Do not execute formal MVE2 search before a later approved run stage.
- Do not enter v10.
- Do not use formal v9 as a baseline.
- Do not use limited MVE2 as a formal baseline.
- Do not use old Qlib or old v8 cache.
- Do not use group4.
- Do not modify raw market data.
- Do not modify audit CSV files.
- Do not use `git add .`.
- Do not force push.

## Next P4 Goals Draft

Recommended next task: P4 formal MVE2 search implementation.

P4 should:

1. Start with the same Git and group4 safety checks used in P1/P2/P3.
2. Add `scripts/us_stock_selection/57_run_formal_mve2_search.py` or a similarly numbered script.
3. Implement the P3 design as a reproducible, config-driven script.
4. Support a dry-run or smoke-test mode that verifies inputs and writes a minimal run_config without performing a full search unless explicitly approved.
5. Use only the audited unified adjusted OHLCV store and the eligible universe.
6. Record all explicit exclusions.
7. Produce the output package structure described above.
8. Keep formal baseline replacement forbidden.
9. Keep direct v10 forbidden.
10. Commit only the P4 script and approved P4 outputs after staged-file verification.

P4 should not run a full formal search unless the next task explicitly approves that execution.
