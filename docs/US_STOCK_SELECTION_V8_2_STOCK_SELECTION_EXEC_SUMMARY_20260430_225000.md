# US Stock Selection v8.2 Stock-Selection Exec Summary

- Branch: `v8.2 stock-selection layer root-cause diagnostic`
- Overlay line: stopped / plateau
- v8 baseline remains best: `True`
- Current classification: `credible_but_execution_sensitive`
- allow_enter_v9: `False`
- Ex-ante monthly score/rank available: `False`
- Light reranking simulation: `False`
- Main blocker: full monthly candidate score/rank audit trail is missing.
- Recommended next: `Patch v8/v8.2 to persist monthly candidate score/rank audit trail, then run a bounded gate-aware reranking replay before any v9 or universe expansion.`

## Window Snapshot

| window_name                 |       CAGR |    Calmar |     MaxDD |   high_beta_weight_share |   top_month_contribution_share | dominant_ticker_list   |
|:----------------------------|-----------:|----------:|----------:|-------------------------:|-------------------------------:|:-----------------------|
| full_period                 |  0.653818  |  1.99153  | -0.3283   |                0.140522  |                       0.168601 | MSTR,MU,AMD,TSLA,PLTR  |
| weakest_12m                 |  0.179788  |  0.636101 | -0.282641 |                0.165737  |                       0.455046 | MSTR,MU,CRWD,AMD,TQQQ  |
| rolling_min_12m_observation |  0.179788  |  0.636101 | -0.282641 |                0.165737  |                       0.455046 | MSTR,MU,CRWD,AMD,TQQQ  |
| strongest_12m               |  1.38944   |  4.23221  | -0.3283   |                0.18      |                       0.25833  | MSTR,TSLA,PLTR,MU,TQQQ |
| 2024                        |  0.831285  |  2.94113  | -0.282641 |                0.165079  |                       0.361181 | MSTR,CRWD,MU,AMD,NET   |
| 2025                        |  0.746498  |  2.28939  | -0.326069 |                0.1472    |                       0.317923 | MU,MSTR,TSLA,PLTR,AVGO |
| 2026                        | -0.0348947 | -0.18365  | -0.190006 |                0.0328767 |                       0.50526  | MU,INTC,SHOP,AMD,CRM   |
