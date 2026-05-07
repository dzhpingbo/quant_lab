# Formal MVE2 Gate Exceptions Review P2-B

This directory expands the exceptions raised by P2-A into reviewable ticker and event-level tables.

Run id: `formal_mve2_data_quality_gate_p2b_exceptions_20260507_151856`

Decision: `CONDITIONAL_NEEDS_DATA_REVIEW`

Read order:

1. `p2b_exception_review_report.md`
2. `formal_mve2_gate_exception_decision.json`
3. `exception_review_summary.csv`
4. `volume_exception_detail.csv`
5. `price_jump_detail.csv`
6. `metadata_conflict_detail.csv`
7. `ticker_level_recommendations.csv`

The script only reads the audited unified adjusted OHLCV store, P2-A outputs, and the limited MVE2 validation pack. It does not alter raw data or previous conclusions.
