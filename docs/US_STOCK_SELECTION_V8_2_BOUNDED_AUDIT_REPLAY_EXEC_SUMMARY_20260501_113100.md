# US Stock Selection v8.2 Bounded Audit Replay Exec Summary

- Sample completed: `True`
- Sample passed: `True`
- Full completed: `True`
- Full candidate score/rank generated: `True`
- Baseline selection reproduced: `True`
- Can run gate-aware reranking replay: `True`
- Next required patch: `pause for user/ChatGPT approval before any bounded gate-aware reranking replay`

## Sample Summary

```json
{
  "phase": "sample",
  "requested_sample_months": [
    "2024-10",
    "2025-03",
    "2025-10"
  ],
  "resolved_decision_dates": [
    "2024-10-31",
    "2025-03-31",
    "2025-10-31"
  ],
  "audit_row_count": 108,
  "decision_count": 3,
  "candidate_count_min": 36,
  "candidate_count_max": 36,
  "selected_count_min": 5,
  "selected_count_max": 5,
  "quality_pass_all": true,
  "selection_diff_count": 0,
  "holdings_diff_count": 0,
  "warning_count": 0,
  "audit_forward_fields_used_in_selection": false
}
```

## Full Summary

```json
{
  "phase": "full",
  "requested_sample_months": [],
  "resolved_decision_dates": [
    "2024-01-31",
    "2024-02-29",
    "2024-04-30",
    "2024-05-31",
    "2024-07-31",
    "2024-09-30",
    "2024-10-31",
    "2024-12-31",
    "2025-01-31",
    "2025-02-28",
    "2025-03-31",
    "2025-04-30",
    "2025-06-30",
    "2025-07-31",
    "2025-09-30",
    "2025-10-31",
    "2025-12-31",
    "2026-03-31"
  ],
  "audit_row_count": 648,
  "decision_count": 18,
  "candidate_count_min": 36,
  "candidate_count_max": 36,
  "selected_count_min": 5,
  "selected_count_max": 5,
  "quality_pass_all": true,
  "selection_diff_count": 0,
  "holdings_diff_count": 0,
  "warning_count": 0,
  "audit_forward_fields_used_in_selection": false
}
```
