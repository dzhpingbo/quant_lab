# Active Project Goals

Generated: 2026-05-07 Asia/Shanghai

## Purpose

This file is the active handoff anchor for continuing the quant analysis project in goals-driven mode. Future work should start by reading the current goal, translating it into a scoped execution plan, running only the allowed actions, verifying the result, and reporting the evidence.

## Current Git Anchor

- Branch: `master`
- HEAD before this goals commit: `df8443730a1300804a6e7e076dcc829959c0fa78`
- `origin/master` before this goals commit: `df8443730a1300804a6e7e076dcc829959c0fa78`
- Ahead/behind before this goals commit: `0 / 0`
- Staged files before this goals commit: none
- Dirty working tree before this goals commit: group4 hold artifacts only
- Force push status: not used

## Primary Research Objective

The US stock selection project is a Qlib + vectorbt research system for finding tradable candidates within the current strategy capability set. The goal is not to select the highest historical return stocks. The goal is to identify instruments and portfolios that the current data, feature, model, and replay framework can evaluate with high Calmar, strong CAGR, controlled drawdown, and acceptable robustness evidence.

Core framework split:

- Qlib: data, factors, model training, cross-sectional prediction scores.
- vectorbt / `canonical_replay_engine`: portfolio replay, execution assumptions, cost stress, concentration checks, and formal replay evidence.

## Current Formal Baseline

The current formal frozen baseline is:

- Strategy: v8.2 frozen Pool A `top5_ytdcap80p_derisk100p`
- Feature set: `Alpha360`
- Model: `LGBModel`
- Label: `label_5d`
- Portfolio: Top5 monthly with YTD return cap 80% and 100% derisk after trigger
- Execution: monthly rebalance, T+1
- Cost/slippage: 5 bps cost and 5 bps slippage
- Formal replay engine: `canonical_replay_engine`
- Formal price source: local Qlib provider bin `$close`
- Volume source: local Qlib provider bin `$volume`
- Universe: Pool A only

Formal v8.2 evidence status:

- Run id: `v82_frozen_formal_audit_20260506_113454`
- Conclusion: `A`
- Gate result: `PASS`
- Classification: `v82_formal_replay_audit_passed_formal_frozen_baseline`
- Frozen mainline changed: `False`

Important caveat:

- v8.2 score provenance is a v8.1 frozen runtime prediction trail.
- It is not a newly trained v9.1 score source.
- The conclusion is limited to formal replay / formal evidence audit PASS.
- It does not mean v9.1 retrain can reproduce the v8.2 score/rank path.

## Formal v9 Status

Formal v9 is a failed branch, not a baseline:

- Run id: `formal_v9_20260505_224016`
- Classification: `formal_v9_failed_due_to_concentration`
- Formal v9 gate pass: `False`
- Pool A reproduction pass: `True`
- Pool A + small growth gate pass: `False`
- Allow enter v10: `False`
- Requires human review: `True`

Audited failure drivers:

- v9.1 score/rank drift versus v8.2 frozen
- Pool A signal degradation under v9.1 score provenance
- Small-growth dilution
- Cost fragility
- Elevated single-year contribution
- PLTR/MSTR/COIN dependency

Formal v9 must not be used as the frozen baseline. Old v9 and unified replay must not be used as formal results.

## Limited MVE2 Context

Limited MVE2 is a separate audited-data research lane. It uses the audited unified adjusted OHLCV store and explicitly avoids old Qlib data, old v8 cache, unreviewed data, formal v9, broad expansion, and trading claims.

Relevant scripts:

- `scripts/us_stock_selection/49_run_limited_mve2_strategy_search.py`
- `scripts/us_stock_selection/50_run_limited_mve2_validation_pack.py`

Current rule:

- Do not mix limited MVE2 conclusions into the v8.2 formal frozen baseline or formal v9 evidence chain.
- If continuing limited MVE2, keep it as a separate goal with its own outputs, report, zip, and gate language.

## Active Allowed Work

Allowed only when explicitly requested by a goal:

- Same-pool audit/repair of formal v9 evidence.
- Score/rank drift audit between v8.2 frozen and formal v9 on identical Pool A dates.
- Cost/turnover/concentration attribution under `canonical_replay_engine`.
- Documentation and bridge context maintenance that does not alter run evidence.
- Separate limited MVE2 validation/reporting tasks within the audited unified-store scope.
- Separate group4 hold review task, if explicitly requested.

## Forbidden Work

The following remain forbidden unless the user explicitly approves a new stage:

- v10
- Nasdaq100 expansion
- S&P500 expansion
- Full-market expansion
- New strategy search
- Parameter search or gate lowering
- Trading, broker/API connection, or real orders
- Using old v9 or unified replay as formal results
- Claiming formal v9 passed
- Letting observation-only tickers enter formal TopK
- Hiding failures, warnings, missing data, or evidence gaps
- Force push
- Committing group4 hold artifacts as part of unrelated commits

## Group4 Hold Status

Group4 remains local hold and must not be modified, deleted, restored, moved, overwritten, staged, committed, or pushed unless a dedicated group4 task is opened.

Group4 paths:

- `docs/chatgpt_bridge/runs/run_20260502_222407/`
- `docs/chatgpt_bridge/runs/run_20260503_172054/`

Current audit summary:

- `run_20260502_222407`: 13 files in the run directory, 3 modified files in working tree.
- `run_20260503_172054`: 13 untracked files.
- Common real token shape matches: `0`.
- Secret/auth/token keyword signal files: `2`.
- Windows local path signal files: `6`.

Decision:

- Continue hold.
- Review group4 only in a separate task.
- Do not mix group4 into bridge documentation, research, or infrastructure commits.

## Commit Discipline

Before every commit:

1. Run `git status --short`.
2. Run `git diff --cached --name-only`.
3. Confirm staged files are exactly the files authorized by the goal.
4. Never use `git add .`.
5. Never use `git add docs/chatgpt_bridge/runs/` unless the goal is explicitly about a reviewed run archive.
6. If unauthorized files are staged, unstage them and stop for review.

Before every push:

1. Confirm ahead/behind.
2. Use normal push only.
3. Do not force push or force-with-lease.
4. If push is rejected, fetch and report the new ahead/behind and remote-only commit; do not force push.

## Suggested Next Goal Options

1. Keep group4 hold and proceed with the next research audit only after a fresh goal is provided.
2. Open a separate group4 archive/cleanup review if those historical run artifacts need a final disposition.
3. Run a same-pool formal v9 score/rank drift audit if the user wants to explain v9 failure more deeply.
4. Continue limited MVE2 only as a separate audited-store goal, not as part of formal v9.
5. Maintain `LATEST.md`, manifests, and bridge context only when a goal explicitly requests documentation sync.

## Read-First Context For New Sessions

Recommended read order:

1. `AGENTS.md`
2. `docs/US_STOCK_SELECTION_AUTORUN.md`
3. `RUN_SUMMARY.md`
4. `NEXT_STEPS.md`
5. `docs/chatgpt_bridge/LATEST.md`
6. `docs/chatgpt_bridge/latest_run_manifest.json`
7. `docs/chatgpt_bridge/PROJECT_HANDOFF_AFTER_PUSH_SYNC.md`
8. `docs/chatgpt_bridge/GROUP4_HOLD_AUDIT.md`
9. `docs/chatgpt_bridge/ACTIVE_PROJECT_GOALS.md`

Then read the latest run-specific `REVIEW_PACKET.md` named by `LATEST.md`.
