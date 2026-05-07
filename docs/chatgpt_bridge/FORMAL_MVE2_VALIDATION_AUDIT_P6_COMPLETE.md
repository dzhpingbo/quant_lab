# Formal MVE2 Validation Audit P6 Complete

## Current Git Baseline

- Branch: master
- HEAD: cb2a6c38ce8f6a8211b23b77a15f2fb642bdaff0
- origin/master: cb2a6c38ce8f6a8211b23b77a15f2fb642bdaff0
- Ahead / behind: 0 / 0 at task start
- Staged files at task start: none
- Dirty local hold: group4 bridge run artifacts remain local hold and were not touched

## Scope

This P6 task validates and audits the P5-B controlled formal MVE2 search package:

- P5-B package: outputs/us_stock_selection/formal_mve2_controlled_search_p5b_20260507_215801/
- P6 output: outputs/us_stock_selection/formal_mve2_validation_audit_p6_20260507_221007/
- P6 script: scripts/us_stock_selection/58_validate_formal_mve2_p5b_audit_pack.py
- py_compile: PASS

This task did not run a new search, expand the parameter grid, train a model, create v10, replace the v8.2 frozen baseline, or modify P5-B outputs.

## P5-B Package Completeness Audit

- Required package files checked: 19
- Missing package files: 0
- Package completeness result: PASS
- P5-B package zip exists and was included as input evidence only.

The P5-B package contains README, manifest, run_config, candidate and rejection tables, benchmark comparison, yearly and subperiod performance, drawdown, turnover, cost stress, risk flag exposure, parameter grid, execution summary, decision JSON, reproducibility checklist, risk flags, and zip.

## Candidate Metrics Audit

- Candidate rows audited: 18
- Selected rows audited: 3
- Rejected rows audited: 15
- Core metric coverage: PASS
- Missing core columns: 0
- NA core metrics: 0
- Infinite values: 0
- MDD direction errors: 0
- Extreme CAGR / Sharpe / Calmar flags: 0

Core metric fields checked include CAGR, MDD, Calmar, Sharpe, volatility, and turnover. Cost stress, benchmark comparison, and risk flag exposure evidence were present for the candidate set.

## Selected Candidates Audit

Selected candidates remain selected for validation only:

- momentum_rank__p002
- momentum_rank__p004
- momentum_liquidity_guard__p016

All three selected candidates keep `selected_for_validation_only=true` and are not written as baseline replacements.

Selected candidate risk findings:

- momentum_rank__p002: MDD = -0.964252563596958, Calmar = 0.6974799218982968, MDD audit = FAIL_RISK, Calmar audit = CONDITIONAL
- momentum_rank__p004: MDD = -0.9561956563695192, Calmar = 0.6760345413161931, MDD audit = FAIL_RISK, Calmar audit = CONDITIONAL
- momentum_liquidity_guard__p016: MDD = -0.9561956563695192, Calmar = 0.6709167099224483, MDD audit = FAIL_RISK, Calmar audit = CONDITIONAL

The selected rows have high CAGR but drawdowns are too large for promotion to P7 baseline comparison.

## Independent Recomputation Check

Independent recomputation used the audited unified adjusted OHLCV store and did not use old qlib, old v8 cache, formal v9 outputs, limited MVE2 outputs, or P5-B outputs as strategy data sources.

- Recompute possible for selected candidates: 3 / 3
- CAGR match within tolerance: 3 / 3
- MDD match within tolerance: 3 / 3
- Turnover match within tolerance: 3 / 3

The recomputation supports metric reproducibility for the selected candidates, but it also confirms the severe drawdown risk.

## MDD / Calmar / Risk Threshold Audit

Audit thresholds:

- MDD <= 35%: PASS
- 35% < MDD <= 45%: CONDITIONAL
- MDD > 45%: FAIL_RISK
- Calmar >= 1.0: PASS
- 0.5 <= Calmar < 1.0: CONDITIONAL
- Calmar < 0.5: FAIL_RISK

Result:

- Selected candidates with MDD FAIL_RISK: 3 / 3
- Selected candidates with Calmar CONDITIONAL: 3 / 3
- Selected candidates recommended for P7 baseline comparison: 0 / 3

## Benchmark Audit

Benchmark evidence was present for SPY, QQQ, and equal-weight eligible universe references. Several candidate rows show benchmark-relative excess return, but benchmark outperformance does not override the selected candidates' drawdown failures.

v8.2 frozen remains a comparison baseline only. It was not used as the formal MVE2 data source and was not replaced.

formal v9 remains a failed branch and was not used as baseline or benchmark.

## Guardrail Audit

Guardrails passed:

- no_baseline_replacement = true
- no_v10 = true
- requires_p6_validation = true
- selected_for_validation_only = true
- formal v9 not baseline
- limited MVE2 not formal baseline
- group4 not touched
- original data not modified
- audit CSV not modified
- P5-B outputs not modified

## P6 Decision

Decision: FAIL_VALIDATION_AUDIT

Reasons:

- 3 selected candidates fail the MDD / Calmar risk audit.
- Independent recomputation confirms the selected candidates' severe drawdown risk.
- No selected candidate is recommended for P7 baseline comparison in the current P6 evidence.

P6 does not permit entering P7 baseline comparison from this result.

## Current Project State

- v8.2 frozen Pool A top5_ytdcap80p_derisk100p remains the formal frozen baseline.
- P5-B selected candidates remain candidate evidence only and are not baselines.
- formal v9 remains a failed branch.
- limited MVE2 remains an independent audited-store research line.
- v10 remains forbidden.

## Next Goals Draft

Recommended next task:

1. Review P6 failure evidence and decide whether to stop the current formal MVE2 search branch or design a constrained remediation plan.
2. If remediation is approved, it must be a new goals-driven task and must not alter P5-B evidence.
3. Do not enter P7 baseline comparison unless a later validation/audit package explicitly permits it.
4. Continue to keep group4 artifacts on local hold unless a separate group4 handling task is opened.

## Risk Notes

- Do not replace the v8.2 formal frozen baseline with P5-B or P6 outputs.
- Do not start v10 from this branch.
- Do not use formal v9 as a baseline or benchmark.
- Do not mix limited MVE2 evidence with the formal baseline evidence chain.
- Do not touch group4 local hold artifacts.
- Do not modify original price data, audit CSV files, P5-B outputs, v8.2 outputs, formal v9 outputs, or limited MVE2 existing outputs.
