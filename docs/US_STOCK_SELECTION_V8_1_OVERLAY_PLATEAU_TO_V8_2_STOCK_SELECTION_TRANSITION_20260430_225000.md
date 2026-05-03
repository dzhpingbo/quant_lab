# v8.1 Overlay Plateau To v8.2 Stock-Selection Transition

v8.1 overlay evolution is complete and should not continue. High-beta soft-cap, NAV throttle, and QQQ/SPY market-regime overlays improved some risk metrics but did not solve weakest 12M, cost-after-return, and top-month concentration gates.

The active branch is now v8.2 stock-selection layer diagnostic. The immediate blocker is not another overlay; it is missing score/rank auditability for the full monthly tradable candidate set.

Next approved direction should be one of:

1. Patch v8/v8.2 to persist monthly candidate score/rank audit trail.
2. Then run a bounded v8.2 gate-aware reranking replay.
3. If score/rank audit shows model instability rather than ranking concentration, redesign train/validation split before any v9 discussion.

No v9, no universe expansion, no 31b, and no model retraining were performed in this diagnostic.
