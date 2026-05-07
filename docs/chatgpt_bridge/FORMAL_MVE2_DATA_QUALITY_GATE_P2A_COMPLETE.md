# Formal MVE2 Data Quality Gate P2-A Complete

## Current Git Baseline

- Branch: `master`
- HEAD at start of P2-A: `b311cbba3ee2f205044b38402d5b90d83653bf10`
- origin/master at start of P2-A: `b311cbba3ee2f205044b38402d5b90d83653bf10`
- ahead/behind at start: `0 / 0`
- Staged files at start: none
- Dirty worktree at start: group4 hold artifacts only

## Task Scope

This round ran a lightweight formal MVE2 data quality gate. It did not run strategy search, train a model, start formal MVE2, start v10, or change any prior candidate decision.

New script:

- `scripts/us_stock_selection/53_run_formal_mve2_data_quality_gate.py`

Successful output directory:

- `outputs/us_stock_selection/formal_mve2_data_quality_gate_20260507_142224/`

Output zip:

- `outputs/us_stock_selection/formal_mve2_data_quality_gate_20260507_142224.zip`
- Size: `16901` bytes

Operational note: an earlier run in this task stopped at report rendering because the local markdown helper dependency was too old. The script was patched to use an internal table renderer, and only the successful output directory above is intended for commit.

## Input Data Source Summary

- Data source: audited unified adjusted OHLCV store
- Store path: `data/unified_ohlcv/us_stock_selection`
- Price files checked: `51`
- Source search run: `outputs/us_stock_selection/limited_mve2_20260502_142702/`
- Validation pack used for alignment checks: `outputs/us_stock_selection/limited_mve2_validation_20260502_183555/`
- Explicitly excluded: old qlib, old v8 cache, formal v9 output, v8.2 formal baseline output

## Universe / Eligible / Excluded Summary

- Eligible tickers: `40`
- Excluded tickers: `11`
- Search universe count: `51`
- Price file ticker count: `51`
- Universe missing price count: `0`
- Price tickers outside search universe: `0`
- Validation candidate tickers outside eligible universe: `0`
- Validation candidate rows remain unchanged from the P1-B pack.

## Field Coverage Summary

All `51` price tickers include the required fields:

- `date`
- `ticker`
- `adj_close`
- `volume`

Optional OHLC fields are also present for all checked price tickers.

## Time Coverage Summary

- All price-file common interval starts at `2021-11-10` because shorter-history excluded tickers are included in the full store check.
- Eligible-only common interval starts at `2015-07-07`.
- Eligible-only common end date is `2026-05-01`.
- Eligible tickers not covering the limited MVE2 common window: `0`.

## Missingness And Anomaly Summary

- Tickers with `adj_close` missing rows: `0`
- Tickers with `volume` missing rows: `0`
- Tickers with non-positive adjusted prices: `0`
- Tickers with non-positive volume rows: `6`
- Duplicate date-ticker rows: `0`
- Tickers with daily adjusted-return absolute jump above `50%`: `7`
- Maximum observed absolute daily adjusted return: `0.893238930820507`

## Liquidity Summary

- Tickers with zero or missing volume rows: `6`
- Tickers with at least five consecutive zero or missing volume rows: `0`
- Minimum median volume across checked tickers: `135250`
- Liquidity checks are data quality warnings only, not investment conclusions.

## Readiness Decision

Decision: `CONDITIONAL_NEEDS_REVIEW`

Primary reasons:

- Non-positive volume rows affect `6` tickers.
- Large daily adjusted-return jumps affect `7` tickers.
- Store audit CSV rows disagree with readable price parquet rows for `51` tickers, indicating audit metadata should be reviewed before formal design.

## P3 / v10 Status

- Can enter P3 formal MVE2 search design now: `false`
- Recommended next step: review or resolve P2-A warnings, especially audit metadata conflict and price/volume anomaly notes.
- Direct v10 remains forbidden.

## Boundary Checks

- group4 hold artifacts were not touched.
- v8.2 formal baseline outputs were not modified.
- formal v9 outputs were not modified and remain a failed branch.
- limited MVE2 conclusions were not changed.
- limited MVE2 was not promoted to formal baseline.

## Risk Notes

- Do not use this gate as permission to start v10.
- Do not treat limited MVE2 as a formal baseline.
- Do not treat formal v9 as a baseline.
- Do not mix limited MVE2 outputs with v8.2 formal baseline evidence.
- Do not use `git add .`.
- Do not use force push.
- Do not release group4 hold without a separate task.
- Do not commit private material or local drive paths in run artifacts.

## Next GOALS Draft

P2-B should be a review and repair-planning task, not a search task:

1. Inspect audit metadata conflict between price parquet files and store audit CSVs.
2. Review the six tickers with non-positive volume rows.
3. Review the seven tickers with daily adjusted-return absolute jumps above `50%`.
4. Decide whether the warnings are acceptable for formal MVE2 design or require store audit regeneration.
5. Keep v8.2 frozen as the formal baseline until a separate approved formal MVE2 process passes.
