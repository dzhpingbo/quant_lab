# Limited MVE2 Validation Pack Gap Audit

Generated: 2026-05-07 Asia/Shanghai

## Scope

This is P1-A: a read-only review of the limited MVE2 validation pack. It does not run a search, train a model, start formal MVE2, enter v10, modify scripts, modify outputs, or handle group4.

## 1. Current Git Baseline

- Branch: `master`
- HEAD before this audit commit: `01930f323104c5143193d448b3b2d4eada78afb2`
- `origin/master` before this audit commit: `01930f323104c5143193d448b3b2d4eada78afb2`
- Ahead/behind before this audit commit: `0 / 0`
- Staged files before this audit commit: none
- Dirty working tree before this audit commit: group4 hold artifacts only

Group4 remains local hold:

- `docs/chatgpt_bridge/runs/run_20260502_222407/`
- `docs/chatgpt_bridge/runs/run_20260503_172054/`

Group4 was not modified, staged, committed, deleted, restored, moved, or pushed by this audit.

## 2. Limited MVE2 Current Status

Relevant scripts:

- `scripts/us_stock_selection/49_run_limited_mve2_strategy_search.py`
- `scripts/us_stock_selection/50_run_limited_mve2_validation_pack.py`

Current relevant output directories:

- `outputs/us_stock_selection/limited_mve2_20260502_142702/`
- `outputs/us_stock_selection/limited_mve2_validation_20260502_183555/`

Older related output directories were observed but not treated as the current validation pack:

- `outputs/us_stock_selection/limited_mve2_20260502_142636/`
- `outputs/us_stock_selection/limited_mve2_validation_20260502_183459/`

Bridge status:

- No non-group4 `docs/chatgpt_bridge/runs/*limited_mve2*` run directory was found.

Current validation pack status:

- Validation pack exists: yes
- Latest validation pack run scope: `limited_mve2_validation`
- Candidate count: `9`
- Formal MVE2 started: `false`
- New strategy search started in validation pack: `false`
- Model training started: `false`
- Uses only unified `adj_close` / `volume`: `true`
- Formal MVE2 support flag in validation decisions: `false` for all 9 candidates

Current search run status:

- Search run scope: `limited_mve2`
- Eligible universe count: `40`
- Excluded ticker count: `11`
- Strategy-result rows: `1200`
- Formal MVE2 started: `false`
- Model training started: `false`
- Uses old Qlib or old v8 cache: `false`

Observed validation decisions:

| decision | count |
| --- | ---: |
| `pass_to_next_validation` | 1 |
| `conditional_pass` | 5 |
| `conditional_pass_leveraged_bucket` | 1 |
| `observation_only` | 2 |

Observed validation pack files:

- `README_summary.md`
- `RUN_SUMMARY.md`
- `NEXT_STEPS.md`
- `limited_mve2_validation_run_config.json`
- `validation_decision_summary.csv`
- `validation_benchmark_comparison.csv`
- `validation_cost_stress_results.csv`
- `validation_period_slice_results.csv`
- `validation_rolling_window_results.csv`
- `validation_trade_ledger.csv`
- `validation_risk_flags.csv`
- `validation_parameter_neighborhood.csv`
- `validation_top_month_sensitivity.csv`
- `frozen_candidates_limited_mve2_validation.csv`
- `rejected_or_observation_candidates.csv`
- `reports/limited_mve2_validation_report.md`
- `reports/limited_mve2_validation_summary.xlsx`
- zip package in `outputs/us_stock_selection/`

Not observed in the validation pack:

- `manifest.json`
- `key_metrics_summary.csv`
- `selected_report.md`
- `small_tables/`
- standard `README.md` filename
- explicit Git commit field in run config

## 3. Validation Pack Completeness Check

| check item | status | evidence file | gap | suggested strengthening |
| --- | --- | --- | --- | --- |
| Data source names audited unified adjusted OHLCV store | PASS | validation script, search script, validation run config | None material | Keep this source frozen for limited MVE2. |
| Core fields are `adj_close` and `volume` | PASS | validation script, search script, validation run config | None material | Preserve field contract in any P1-B output. |
| Avoids old Qlib / old v8 cache | PASS | search run config, active goals, execution gate | No direct contamination observed | Repeat this check in P1-B manifest. |
| formal v9 outputs excluded from limited MVE2 evidence | PASS | active goals, execution gate, scripts | No mixing observed | State the separation again in P1-B README. |
| Ticker universe fixed | PARTIAL | search eligible / excluded CSVs; validation frozen candidate CSV | Search universe is fixed, but validation pack does not include standalone eligible/excluded detail | Copy or summarize eligible/excluded into the validation pack. |
| Eligible ticker list available | PASS | search eligible universe CSV | Available in prior search output | Include a validation-pack-local summary for standalone review. |
| Excluded ticker list and reasons available | PASS | search excluded tickers CSV | Available in prior search output | Include exclusion reasons in P1-B package. |
| Frozen validation candidates listed | PASS | frozen candidates CSV | None material | Keep candidate roles and notes. |
| Strategy candidates and parameters listed | PASS | frozen candidates CSV, decision summary, neighborhood CSV | None material | Add a compact candidate/parameter table to key metrics. |
| Parameter neighborhood checked | PASS | validation parameter neighborhood CSV | None material | Preserve cliff-drop flags. |
| Not formal MVE2 | PASS | README summary, run config, decision summary | None material | Keep formal support flag false unless a future formal gate approves. |
| CAGR / MDD / Calmar / Sharpe / turnover metrics | PASS | decision, cost, period, rolling, benchmark CSVs | No single standard key metrics file | Add `key_metrics_summary.csv`. |
| Hit rate / win-rate style metric | PARTIAL | trade ledger can support it, but no explicit compact hit-rate summary observed | Not easy to review at pack level | Add hit-rate / trade-win summary in P1-B. |
| Benchmark comparison | PASS | validation benchmark comparison CSV | None material | Add summary to key metrics. |
| Cost / slippage assumptions | PARTIAL | validation cost stress CSV | Cost stress exists; slippage policy is not separately standardized | Document cost and slippage assumptions explicitly in P1-B README. |
| Annual or period performance | PARTIAL | period slice and rolling window CSVs | Period slices exist; annual summary table not observed | Add annual / calendar-year summary if available or mark not run. |
| Drawdown evidence | PASS | MDD fields, rolling window CSV, period slice CSV | None material | Add worst drawdown row to key metrics. |
| README | PARTIAL | `README_summary.md`, report markdown | Standard `README.md` missing | Add or alias a standard README in P1-B. |
| Manifest | MISSING | none observed | Reproducibility gap | Add `manifest.json` with run id, script, inputs, outputs, and git commit. |
| Zip | PASS | zip package in output root | None material | Include zip path in manifest. |
| Key metrics CSV | MISSING | none observed | Review and bridge gap | Add `key_metrics_summary.csv`. |
| Selected report / bridge packet | MISSING | no non-group4 bridge run found | ChatGPT bridge gap | Add selected report or bridge-compatible review packet if requested. |
| `small_tables/` for bridge review | MISSING | no bridge run found | Bridge review gap | Add small-table exports if publishing to bridge. |
| Script path recorded | PASS | copied validation script, run config | None material | Add script hash or git commit in manifest. |
| Input data path recorded | PASS | run config | Uses relative path, acceptable | Keep relative path; avoid Windows absolute-path leak. |
| Output directory recorded | PASS | run config | None material | Add output dir to manifest. |
| Run id / timestamp recorded | PASS | run config, directory name | None material | Add to manifest. |
| Git commit recorded | MISSING | none observed | Reproducibility gap | Add current git commit in P1-B manifest. |
| Risk isolation from v8.2 formal baseline | PARTIAL | active goals and execution gate | Validation pack itself should state this more directly | Add explicit isolation paragraph to P1-B README. |
| Risk isolation from formal v9 failed branch | PASS | active goals, execution gate, validation script scope | No mixing observed | Preserve as hard guardrail. |
| v10 blocked | PASS | active goals, execution gate, README summary | None material | Keep explicit v10 prohibition. |

## 4. Key Risk Judgement

| risk | judgement | rationale | next control |
| --- | --- | --- | --- |
| Data source pollution | LOW to MODERATE | Scripts and configs use audited unified `adj_close` / `volume` and record no old Qlib / old v8 cache use. | Add manifest-level data-source attestation. |
| Universe inconsistency | MODERATE | Search run has eligible/excluded files, but validation pack is not standalone on universe/exclusion evidence. | Copy or summarize eligible/excluded lists into P1-B validation pack. |
| Eligible/excluded not reproducible | MODERATE | Prior search output contains evidence, but validation package does not fully carry it forward. | Add validation-pack-local eligible/excluded summary and reasons. |
| formal v9 mixed into limited MVE2 | LOW | No evidence of formal v9 output use; scripts explicitly separate scopes. | Preserve explicit no-formal-v9 baseline rule. |
| limited MVE2 misused as formal baseline | MODERATE | Some candidates look strong, but every validation decision has `formal_mve2_supported=false`. | Keep all conclusions as limited-scope and add warning to README. |
| Missing manifest / key metrics / bridge packet | HIGH for reproducibility | Zip and reports exist, but standard manifest and compact key metrics are missing. | P1-B should add manifest, key metrics, and selected report. |
| Windows path / sensitive content risk | LOW for this audit file | This audit avoids sensitive text and Windows absolute paths. | Review future run artifacts before committing. |

## 5. Can This Move Forward?

- Can enter P1-B validation pack strengthening: **YES**.
- Can enter P2 formal MVE2 data quality gate now: **CONDITIONALLY, after P1-B or with a separate explicit data-quality goal**.
- Should enter P3 formal MVE2 search design now: **NO**.
- Can run formal MVE2 now: **NO**.
- Can run v10 now: **NO**.

Reason:

The limited MVE2 validation pack is useful and fairly rich, but it is not yet a formal-quality package. The immediate next step should strengthen evidence packaging and reproducibility before designing or running formal MVE2.

## 6. Suggested P1-B Goals Draft

P1-B should be a separate task and should not be executed as part of this audit. Suggested P1-B goals:

1. Add a standard validation-pack README.
2. Add `manifest.json` with run id, script path, input data path, output dir, zip path, run timestamp, and git commit.
3. Add `key_metrics_summary.csv` with candidate-level CAGR, MDD, Calmar, Sharpe, turnover, benchmark comparison, cost sensitivity, rolling pass rate, and decision.
4. Add eligible/excluded ticker summary copied or summarized from the prior search run.
5. Add benchmark comparison summary suitable for quick review.
6. Add reproduction instructions using relative paths only.
7. Add a bridge-friendly selected report or small-table export if publication to `docs/chatgpt_bridge/runs/` is requested.
8. Preserve `formal_mve2_supported=false` for all current validation decisions unless a future formal gate changes it.
9. Package a refreshed zip after the strengthened files are produced.

## 7. Forbidden Actions

- Do not present limited MVE2 as a formal baseline.
- Do not use formal v9 as a baseline.
- Do not enter v10.
- Do not start formal MVE2 without a separate formal data-quality gate.
- Do not mix limited MVE2 outputs with the v8.2 formal baseline evidence chain.
- Do not use `git add .`.
- Do not force push.
- Do not handle group4 in this workstream.
- Do not commit `outputs/` or `scripts/` changes for this audit.
- Do not commit run artifacts containing token/auth/secret text or Windows absolute-path risk before review.

## 8. This Audit Commit Gate

Only this file may be staged for the audit commit:

- `docs/chatgpt_bridge/LIMITED_MVE2_VALIDATION_PACK_GAP_AUDIT.md`

Do not stage:

- `docs/chatgpt_bridge/runs/`
- group4 artifacts
- `scripts/`
- `outputs/`
