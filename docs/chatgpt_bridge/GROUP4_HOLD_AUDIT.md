# Group4 Hold Audit

Generated: 2026-05-07 Asia/Shanghai

## Scope

This is a read-only audit of the current group4 hold artifacts. The audit did not modify, stage, commit, delete, restore, move, overwrite, or rerun any group4 files.

Group4 hold paths:

- `docs/chatgpt_bridge/runs/run_20260502_222407/`
- `docs/chatgpt_bridge/runs/run_20260503_172054/`

## Git Context Before This Audit Commit

- Branch: `master`
- HEAD commit: `4185ba01c7498fe1d0469382bbb8aa57d0faf1f8`
- `origin/master` commit: `4185ba01c7498fe1d0469382bbb8aa57d0faf1f8`
- Ahead/behind: `0 / 0`
- Staged files before audit report staging: none
- Remaining dirty files before this report: group4 hold artifacts only

## Group4 File Summary

### `run_20260502_222407`

- Run directory file count: `13`
- File types: `.csv`, `.json`, `.md`
- Total size: `72764` bytes
- Run id: `run_20260502_222407`
- Stage: `v9_growth_pool_pre_research`
- Classification: `not_v10_ready_growth_pool_sensitive`
- Current dirty status: `3` modified files

Modified files:

- `docs/chatgpt_bridge/runs/run_20260502_222407/REVIEW_PACKET.md`
- `docs/chatgpt_bridge/runs/run_20260502_222407/manifest.json`
- `docs/chatgpt_bridge/runs/run_20260502_222407/publish_git_status.json`

### `run_20260503_172054`

- Run directory file count: `13`
- File types: `.csv`, `.json`, `.md`
- Total size: `84707` bytes
- Run id: `run_20260503_172054`
- Stage: `v9_reverse_audit_no_expansion`
- Classification: `invalid_or_needs_human_review`
- Current dirty status: `13` untracked files

Untracked files:

- `docs/chatgpt_bridge/runs/run_20260503_172054/REVIEW_PACKET.md`
- `docs/chatgpt_bridge/runs/run_20260503_172054/RUN_SUMMARY.md`
- `docs/chatgpt_bridge/runs/run_20260503_172054/final_verdict.json`
- `docs/chatgpt_bridge/runs/run_20260503_172054/key_metrics.csv`
- `docs/chatgpt_bridge/runs/run_20260503_172054/manifest.json`
- `docs/chatgpt_bridge/runs/run_20260503_172054/next_steps.md`
- `docs/chatgpt_bridge/runs/run_20260503_172054/publish_git_status.json`
- `docs/chatgpt_bridge/runs/run_20260503_172054/selected_report.md`
- `docs/chatgpt_bridge/runs/run_20260503_172054/small_tables/attribution.csv`
- `docs/chatgpt_bridge/runs/run_20260503_172054/small_tables/benchmark.csv`
- `docs/chatgpt_bridge/runs/run_20260503_172054/small_tables/holdings_summary.csv`
- `docs/chatgpt_bridge/runs/run_20260503_172054/small_tables/stress_test.csv`
- `docs/chatgpt_bridge/runs/run_20260503_172054/small_tables/yearly_return.csv`

## Risk Signal Summary

The scan reported only file-level signals and did not print sensitive source text.

- Common real token shape matches: `0`
- Secret/auth/token keyword signal files: `2`
- Windows local path signal files: `6`

Files with secret/auth/token keyword signals:

- `docs/chatgpt_bridge/runs/run_20260503_172054/next_steps.md`
- `docs/chatgpt_bridge/runs/run_20260503_172054/REVIEW_PACKET.md`

Files with Windows local path signals:

- `docs/chatgpt_bridge/runs/run_20260502_222407/manifest.json`
- `docs/chatgpt_bridge/runs/run_20260502_222407/REVIEW_PACKET.md`
- `docs/chatgpt_bridge/runs/run_20260503_172054/manifest.json`
- `docs/chatgpt_bridge/runs/run_20260503_172054/next_steps.md`
- `docs/chatgpt_bridge/runs/run_20260503_172054/REVIEW_PACKET.md`
- `docs/chatgpt_bridge/runs/run_20260503_172054/RUN_SUMMARY.md`

## Hold Decision

Group4 should remain on local hold. These artifacts have historical audit value, but they also contain local-path and keyword-level risk signals. They should not be mixed into unrelated commits.

## Recommended Next Steps

- Keep group4 hold unchanged.
- Open a separate task if group4 needs archive, cleanup, restore, deletion, or commit review.
- Before any group4 commit, explicitly list staged files with `git diff --cached --name-only`.
- Do not commit group4 files until risk signals are reviewed and any required path or sensitive-field cleanup is approved.
- Do not force push.
- Do not delete unconfirmed `runs` directories.
