# Formal MVE2 Controlled Search P5-B Report

## Summary

- Run id: `formal_mve2_controlled_search_p5b_20260507_215801`
- Decision: `P5B_CONTROLLED_SEARCH_COMPLETED`
- Controlled search success: `true`
- Full search executed: `true`
- Parameter combinations: `18`
- Candidate rows: `18`
- Selected for P6 validation/audit only: `3`
- Rejected rows: `15`
- Baseline replaced: `false`
- v10 executed: `false`

## Selected Candidates

Selected candidates are only selected for P6 validation / audit pack. They are not baselines.

Top selected records:

```json
[
  {
    "candidate_id": "momentum_rank__p002",
    "CAGR": 0.6725468027478387,
    "MDD": -0.964252563596958,
    "Calmar": 0.6974799218982968,
    "Sharpe": 1.0281822511720433,
    "turnover": 0.37858243451463797
  },
  {
    "candidate_id": "momentum_rank__p004",
    "CAGR": 0.646421291962304,
    "MDD": -0.9561956563695191,
    "Calmar": 0.6760345413161931,
    "Sharpe": 1.010064275302066,
    "turnover": 0.3882896764252696
  },
  {
    "candidate_id": "momentum_liquidity_guard__p016",
    "CAGR": 0.6415276438135737,
    "MDD": -0.9561956563695191,
    "Calmar": 0.6709167099224483,
    "Sharpe": 1.0070624654866847,
    "turnover": 0.3882896764252696
  }
]
```

## Data Source

The search used the audited unified adjusted OHLCV store only. Core fields were `date`, `ticker`, `adj_close`, and `volume`.

## Universe

Only eligible tickers entered the formal candidate pool. Excluded tickers remained observation and audit reference only.

## Benchmarks

Benchmark comparison includes SPY, QQQ, and equal-weight eligible universe when available. v8.2 remains comparison baseline metadata only. formal v9 was not used as benchmark or baseline.

## Next Step

P5-B allows a separate P6 validation / audit pack task. It does not permit baseline replacement or v10.
