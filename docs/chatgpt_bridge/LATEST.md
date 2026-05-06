# ChatGPT Bridge Latest Run

Run ID: `v82_frozen_formal_audit_20260506_113454`
Updated: `2026-05-06 11:34:57`
Status: `v82_formal_replay_audit_passed_formal_frozen_baseline`

## Latest Artifact

- Review packet: `docs/chatgpt_bridge/runs/v82_frozen_formal_audit_20260506_113454/REVIEW_PACKET.md`
- Audit report: `outputs/us_stock_selection/v82_frozen_formal_audit_20260506_113454/v82_frozen_formal_audit.md`
- Audit workbook: `outputs/us_stock_selection/v82_frozen_formal_audit_20260506_113454/v82_frozen_formal_replay_summary.xlsx`
- Comparison workbook: `outputs/us_stock_selection/v82_frozen_formal_audit_20260506_113454/v82_vs_formal_v9_comparison.xlsx`
- Audit directory: `outputs/us_stock_selection/v82_frozen_formal_audit_20260506_113454`

## Current Conclusion

A. v8.2 formal replay audit passed; it can be upgraded to / retained as formal frozen baseline.

The frozen mainline remains v8.2 `top5_ytdcap80p_derisk100p`. No v10, no pool expansion, no trading, no parameter search, no commit/push.

## Formal v9 Failed Branch

`formal_v9_20260505_224016` did not pass the formal gate. The audited failure reasons include v9.1 score/rank drift, small-growth dilution, cost fragility, elevated single-year contribution, and PLTR/MSTR/COIN dependency.

formal v9 is not allowed as the frozen baseline. Old v9 and unified replay must not be used as formal results.

## Baseline Caveat

The v8.2 score provenance is a v8.1 frozen runtime prediction trail, not a newly trained v9.1 score source. This conclusion is limited to formal replay / formal evidence audit PASS and does not mean v9.1 retrain can reproduce v8.2 score/rank.

## Allowed Next Action

Stop for human review; v8.2 can be treated as the formal frozen baseline evidence packet. Do not enter v10.
