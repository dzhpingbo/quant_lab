# Formal MVE2 P6 Failure Closure And Worktree Audit

## Current Git Baseline

- Branch: master
- HEAD: e00ded0ce9eab7fa1666902425f0de823f289a32
- origin/master: e00ded0ce9eab7fa1666902425f0de823f289a32
- Ahead / behind: 0 / 0
- Staged files before this closure task: none

## P6 Failure Conclusion

P6 decision: FAIL_VALIDATION_AUDIT

The P6 package confirmed that the P5-B controlled formal MVE2 search results are reproducible, but the selected candidates fail the risk audit. Therefore the formal MVE2 upgrade path stops at P6 for the current evidence chain.

P6 evidence summary:

- 18 candidate rows passed metric completeness checks.
- 3 / 3 selected candidates were independently recomputed from the audited unified adjusted OHLCV store.
- Recomputed selected-candidate metrics matched P5-B evidence.
- 3 / 3 selected candidates triggered MDD FAIL_RISK.
- Calmar audit status for selected candidates was CONDITIONAL.
- Benchmark outperformance evidence does not override the drawdown failure.

## Selected Candidate Failure Summary

| candidate_id | MDD | Calmar | MDD audit | Calmar audit | P7 baseline comparison |
| --- | ---: | ---: | --- | --- | --- |
| momentum_rank__p002 | -0.964252563596958 | 0.6974799218982968 | FAIL_RISK | CONDITIONAL | No |
| momentum_rank__p004 | -0.9561956563695192 | 0.6760345413161931 | FAIL_RISK | CONDITIONAL | No |
| momentum_liquidity_guard__p016 | -0.9561956563695192 | 0.6709167099224483 | FAIL_RISK | CONDITIONAL | No |

## Formal Chain Closure

- Enter P7 baseline comparison: No
- Replace v8.2 frozen baseline: No
- Create v10: No
- Continue current formal MVE2 baseline upgrade path: No

The current formal frozen baseline remains:

v8.2 frozen Pool A top5_ytdcap80p_derisk100p

formal v9 / v9.1 remains a failed branch and is not a baseline or benchmark.

limited MVE2 remains an independent audited-store research line and is not a formal baseline.

## Dirty Worktree Audit

Current dirty worktree items are outside the P6 closure commit scope.

### Group4 Local Hold

Tracked local-hold modifications remain under:

- docs/chatgpt_bridge/runs/run_20260502_222407/REVIEW_PACKET.md
- docs/chatgpt_bridge/runs/run_20260502_222407/manifest.json
- docs/chatgpt_bridge/runs/run_20260502_222407/publish_git_status.json

Untracked local-hold run directory remains:

- docs/chatgpt_bridge/runs/run_20260503_172054/

These group4 items were not modified, staged, restored, deleted, moved, or committed by this closure task.

### Non-Group4 Untracked File

File:

- scripts/qldtqqq_vix_strategy_comparison.py

Read-only audit:

- Exists: Yes
- Size: 28,298 bytes
- Recent local modified time observed: 2026-05-07 22:11:27 local time
- First-30-line summary: imports standard Python modules for CLI, JSON, logging, math, archive handling, date/time, path handling, and mapping types; defines a `latest_turning_run` helper early in the file.
- Sensitive private-key wording scan: no hit in the file text.
- Windows drive-path scan: no hit in the file text.
- Formal MVE2 workflow match: No clear match.
- QLD/TQQQ/VIX workflow match: Yes.

Ownership recommendation:

- NON_GROUP4_UNTRACKED_HOLD
- SEPARATE_TASK_REQUIRED
- SAFE_TO_IGNORE_FOR_CURRENT_CHAIN
- NEED_USER_DECISION

This file is not a group4 artifact and is not part of P6. It should not be staged or committed with formal MVE2 chain updates until the user explicitly confirms its ownership.

## Risk Warnings

- Before any later commit, explicitly handle or keep holding `scripts/qldtqqq_vix_strategy_comparison.py`.
- Do not use `git add .`.
- Do not accidentally commit `scripts/qldtqqq_vix_strategy_comparison.py`.
- Do not release group4 local hold unless a separate group4 task is opened.
- Do not force push.
- Do not enter P7 from the current P6 evidence.
- Do not replace v8.2 frozen baseline.
- Do not create v10.

## Recommended Next Steps

1. Decide ownership of `scripts/qldtqqq_vix_strategy_comparison.py` in a separate task.
2. Optionally run a read-only postmortem on why P5-B selected candidates experienced severe drawdowns.
3. Keep the formal MVE2 baseline upgrade path paused after P6 failure.
4. Keep v8.2 frozen Pool A top5_ytdcap80p_derisk100p as the current formal frozen baseline.
5. Keep group4 artifacts on local hold until a separate explicit task resolves them.
