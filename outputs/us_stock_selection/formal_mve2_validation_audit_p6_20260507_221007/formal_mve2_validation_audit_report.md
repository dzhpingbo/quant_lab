# Formal MVE2 Validation Audit Report

## Decision

`FAIL_VALIDATION_AUDIT`

## Reasons

- 3 selected candidates fail MDD/Calmar risk audit.

## Selected Candidate Risk Audit

```json
[
  {
    "candidate_id": "momentum_rank__p002",
    "MDD": -0.964252563596958,
    "Calmar": 0.6974799218982968,
    "MDD_audit": "FAIL_RISK",
    "Calmar_audit": "CONDITIONAL",
    "recommend_enter_p7_baseline_comparison": false
  },
  {
    "candidate_id": "momentum_rank__p004",
    "MDD": -0.9561956563695192,
    "Calmar": 0.6760345413161931,
    "MDD_audit": "FAIL_RISK",
    "Calmar_audit": "CONDITIONAL",
    "recommend_enter_p7_baseline_comparison": false
  },
  {
    "candidate_id": "momentum_liquidity_guard__p016",
    "MDD": -0.9561956563695192,
    "Calmar": 0.6709167099224483,
    "MDD_audit": "FAIL_RISK",
    "Calmar_audit": "CONDITIONAL",
    "recommend_enter_p7_baseline_comparison": false
  }
]
```

## Interpretation

P6 found that selected P5-B candidates are candidate evidence only. The severe drawdown profile blocks baseline-comparison promotion in this audit package.

v8.2 remains the formal frozen baseline. formal v9 remains a failed branch. v10 remains forbidden.
